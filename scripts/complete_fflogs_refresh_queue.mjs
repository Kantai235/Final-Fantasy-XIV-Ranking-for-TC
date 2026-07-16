import { appendFileSync, existsSync } from "node:fs";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  batchUpdateSheetValues,
  parseServiceAccountJson,
  quoteSheetRange,
  readEnv,
  readSheetValues,
  requestAccessToken,
  SHEETS_WRITE_SCOPE,
} from "./google_sheets_service_account.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DEFAULT_SHEET_NAME = "pending";
const DEFAULT_RANGE_COLUMNS = "A:Z";
const DEFAULT_STATUS_INDEX_PATH = path.join(rootDir, "public", "data", "report_status_index.json");
const DEFAULT_HIDDEN_STATUS_INDEX_PATH = path.join(rootDir, "public", "data", "all", "report_status_index.json");
const DEFAULT_SOURCE_RANKINGS_DIR = path.join(rootDir, "data", "rankings");
const DEFAULT_STATE_PATH = path.join(rootDir, "data", "state.json");
const DEFAULT_MAX_ROWS = 500;
const REPORT_CODE_PATTERN = /^[A-Za-z0-9]{8,32}$/;
const QUEUED_STATUSES = new Set(["queued", "pending", "retry"]);
const STATE_STATUS_NO_CLEAR = "skipped_no_clear";
const STATE_STATUS_NO_TRADITIONAL_CHINESE_PLAYERS = "skipped_no_traditional_chinese_players";

const QUEUE_OUTCOME = {
  COLLECTED: "collected",
  NO_CLEAR: "no_clear",
  NO_TRADITIONAL_CHINESE_PLAYERS: "no_traditional_chinese_players",
};

function normalizeHeader(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeReportCode(value) {
  return String(value || "").trim().replace(/^a:/i, "");
}

function columnNameFromIndex(index) {
  let value = index + 1;
  let name = "";
  while (value > 0) {
    value -= 1;
    name = String.fromCharCode(65 + (value % 26)) + name;
    value = Math.floor(value / 26);
  }
  return name;
}

function rowsToObjects(values) {
  if (!Array.isArray(values) || values.length < 2) {
    return { headers: [], rows: [] };
  }

  const headers = values[0].map(normalizeHeader);
  const rows = values.slice(1).map((row, index) => {
    const item = {
      _row_number: index + 2,
      _raw: row,
    };
    headers.forEach((header, columnIndex) => {
      if (header) {
        item[header] = row[columnIndex] ?? "";
      }
    });
    return item;
  });
  return { headers, rows };
}

async function readJsonIfExists(filePath) {
  if (!filePath || !existsSync(filePath)) {
    return null;
  }
  return JSON.parse(await readFile(filePath, "utf8"));
}

function rowToObject(row, columns) {
  if (!Array.isArray(row)) {
    return row && typeof row === "object" ? row : {};
  }
  return Object.fromEntries((columns || []).map((column, index) => [column, row[index]]));
}

export function addReportStatusIndex(index, indexedReportCodes) {
  const reportColumns = index?.report_columns || [];
  for (const row of index?.reports || []) {
    const report = rowToObject(row, reportColumns);
    const reportCode = normalizeReportCode(report.report_code);
    if (!REPORT_CODE_PATTERN.test(reportCode)) {
      continue;
    }
    indexedReportCodes.add(reportCode);
  }
}

export function addReportCode(indexedReportCodes, value) {
  const reportCode = normalizeReportCode(value);
  if (REPORT_CODE_PATTERN.test(reportCode)) {
    indexedReportCodes.add(reportCode);
  }
}

export function isHiddenEntry(entry) {
  return Boolean(entry?.report_hidden || entry?.hidden_report);
}

export function rankingEntryGroups(ranking) {
  return [
    ranking?.ranking_entries,
    ...Object.values(ranking?.version_ranking_entries || {}),
  ].filter(Array.isArray);
}

export function addSourceReportCodesFromRanking(ranking, indexedReportCodes, { includeHidden }) {
  for (const entries of rankingEntryGroups(ranking)) {
    for (const entry of entries) {
      if (!entry || typeof entry !== "object") {
        continue;
      }
      if (!includeHidden && isHiddenEntry(entry)) {
        continue;
      }

      addReportCode(indexedReportCodes, entry.report_code);
      for (const reportCode of Array.isArray(entry.source_reports) ? entry.source_reports : []) {
        addReportCode(indexedReportCodes, reportCode);
      }
    }
  }
}

async function addReportShardCodesFromRanking(
  ranking,
  indexedReportCodes,
  { includeHidden, repositoryRoot, loadedShardPaths },
) {
  for (const reportShardPath of Array.isArray(ranking?.report_shards) ? ranking.report_shards : []) {
    if (typeof reportShardPath !== "string" || !reportShardPath.trim()) {
      continue;
    }
    const resolvedShardPath = path.resolve(repositoryRoot, reportShardPath);
    if (loadedShardPaths.has(resolvedShardPath)) {
      continue;
    }
    loadedShardPaths.add(resolvedShardPath);

    const shard = await readJsonIfExists(resolvedShardPath);
    if (!shard || typeof shard !== "object" || Array.isArray(shard)) {
      continue;
    }

    for (const [reportCode, report] of Object.entries(shard)) {
      if (!report || typeof report !== "object") {
        continue;
      }
      if (!includeHidden && isHiddenEntry(report)) {
        continue;
      }
      // report 分片是 reports -> fights -> players 的權威來源。即使其中任何玩家的成績
      // 都沒有進入 ranking_entries，使用者送出的公開 report 仍已被成功收錄，必須結束 queue。
      addReportCode(indexedReportCodes, report.report_code || reportCode);
    }
  }
}

export async function addSourceRankingReportCodes({
  sourceRankingsDir,
  indexedReportCodes,
  includeHidden,
  repositoryRoot = rootDir,
}) {
  if (!sourceRankingsDir || !existsSync(sourceRankingsDir)) {
    return;
  }

  const loadedShardPaths = new Set();
  const fileNames = (await readdir(sourceRankingsDir))
    .filter((fileName) => fileName.endsWith(".json"))
    .sort();
  for (const fileName of fileNames) {
    const ranking = await readJsonIfExists(path.join(sourceRankingsDir, fileName));
    if (!ranking || typeof ranking !== "object") {
      continue;
    }
    addSourceReportCodesFromRanking(ranking, indexedReportCodes, { includeHidden });
    await addReportShardCodesFromRanking(ranking, indexedReportCodes, {
      includeHidden,
      repositoryRoot,
      loadedShardPaths,
    });
  }
}

export async function buildIndexedReportSet({
  statusIndexPath,
  hiddenStatusIndexPath,
  sourceRankingsDir,
  includeHidden,
  repositoryRoot = rootDir,
}) {
  const indexedReportCodes = new Set();
  addReportStatusIndex(await readJsonIfExists(statusIndexPath), indexedReportCodes);
  if (includeHidden) {
    addReportStatusIndex(await readJsonIfExists(hiddenStatusIndexPath), indexedReportCodes);
  }
  await addSourceRankingReportCodes({
    sourceRankingsDir,
    indexedReportCodes,
    includeHidden,
    repositoryRoot,
  });
  return indexedReportCodes;
}

export function isRowIndexed(row, indexedReportCodes) {
  const reportCode = normalizeReportCode(row.report_code);
  return REPORT_CODE_PATTERN.test(reportCode) && indexedReportCodes.has(reportCode);
}

export function buildReportStatusesByCode(state, reportCodes) {
  const requestedCodes = new Set(
    Array.from(reportCodes || [], normalizeReportCode)
      .filter((reportCode) => REPORT_CODE_PATTERN.test(reportCode)),
  );
  const statusesByCode = new Map();
  if (requestedCodes.size === 0 || !state || typeof state !== "object") {
    return statusesByCode;
  }

  for (const encounterState of Object.values(state.encounters || {})) {
    if (!encounterState || typeof encounterState !== "object") {
      continue;
    }
    // checked_reports 是跨輪權威快取；processed_reports 則保留當輪尚未 compact 的結果。
    // 兩者都讀取，避免 workflow 收尾時因 checkpoint 生命週期不同而漏掉剛完成的排查結論。
    for (const checkpointName of ["checked_reports", "processed_reports"]) {
      const checkpoints = encounterState[checkpointName];
      if (!checkpoints || typeof checkpoints !== "object") {
        continue;
      }
      for (const reportCode of requestedCodes) {
        const status = normalizeHeader(checkpoints[reportCode]?.status);
        if (!status) {
          continue;
        }
        const statuses = statusesByCode.get(reportCode) || new Set();
        statuses.add(status);
        statusesByCode.set(reportCode, statuses);
      }
    }
  }
  return statusesByCode;
}

export function resolveQueueOutcome(row, indexedReportCodes, statusesByCode) {
  if (isRowIndexed(row, indexedReportCodes)) {
    return QUEUE_OUTCOME.COLLECTED;
  }

  const reportCode = normalizeReportCode(row.report_code);
  const statuses = statusesByCode.get(reportCode) || new Set();
  // 是否含有繁中服玩家是整份 report 層級的結論，優先於各 encounter 的 no-clear checkpoint。
  if (statuses.has(STATE_STATUS_NO_TRADITIONAL_CHINESE_PLAYERS)) {
    return QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS;
  }
  if (statuses.has(STATE_STATUS_NO_CLEAR)) {
    return QUEUE_OUTCOME.NO_CLEAR;
  }
  return null;
}

function queueOutcomeStatus(outcome) {
  switch (outcome) {
    case QUEUE_OUTCOME.COLLECTED:
      return "done";
    case QUEUE_OUTCOME.NO_CLEAR:
      return "not_eligible_no_clear";
    case QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS:
      return "not_eligible_no_traditional_chinese_players";
    default:
      return "";
  }
}

function queueOutcomeMessage(row, outcome) {
  if (outcome === QUEUE_OUTCOME.COLLECTED) {
    return normalizeHeader(row.request_type) === "retry_existing"
      ? "workflow 已送出整份 report 重掃，公開資料已收錄此 report。"
      : "workflow 已確認公開資料收錄 report。";
  }
  if (outcome === QUEUE_OUTCOME.NO_CLEAR) {
    return "workflow 已完成排查：未找到本站支援副本的通關戰鬥，因此不符合收錄條件。";
  }
  if (outcome === QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS) {
    return "workflow 已完成排查：未發現繁中服玩家，因此不符合收錄條件。";
  }
  return "";
}

export function buildUpdateRanges({ headers, rows, sheetName, nowIso, maxRows, indexedReportCodes, statusesByCode }) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return [];
  }

  const statusIndex = headers.indexOf("status");
  const updatedAtIndex = headers.indexOf("updated_at_iso");
  const lastMessageIndex = headers.indexOf("last_message");
  if (statusIndex < 0 || updatedAtIndex < 0 || lastMessageIndex < 0) {
    throw new Error("Google Sheet 待收錄名單缺少 status、updated_at_iso 或 last_message 欄位。");
  }

  return rows.slice(0, maxRows).flatMap((row) => {
    const rowNumber = row._row_number;
    const statusCell = `${columnNameFromIndex(statusIndex)}${rowNumber}`;
    const updatedAtCell = `${columnNameFromIndex(updatedAtIndex)}${rowNumber}`;
    const lastMessageCell = `${columnNameFromIndex(lastMessageIndex)}${rowNumber}`;
    const outcome = resolveQueueOutcome(row, indexedReportCodes, statusesByCode);
    if (!outcome) {
      return [];
    }

    return [
      {
        range: quoteSheetRange(sheetName, statusCell),
        values: [[queueOutcomeStatus(outcome)]],
      },
      {
        range: quoteSheetRange(sheetName, updatedAtCell),
        values: [[nowIso]],
      },
      {
        range: quoteSheetRange(sheetName, lastMessageCell),
        values: [[queueOutcomeMessage(row, outcome)]],
      },
    ];
  });
}

function writeStepSummary({ skippedReason, rowsRead, outcomeCounts, includeHidden }) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (!summaryPath) {
    return;
  }

  const lines = [
    "### FFLogs 待收錄名單收尾",
    "",
    skippedReason ? `- 略過：${skippedReason}` : "- 已檢查 Google Sheet 待收錄名單與公開資料來源。",
    `- 讀取列數：${rowsRead}`,
    `- 已收錄完成列數：${outcomeCounts[QUEUE_OUTCOME.COLLECTED] || 0}`,
    `- 無通關終止列數：${outcomeCounts[QUEUE_OUTCOME.NO_CLEAR] || 0}`,
    `- 無繁中服玩家終止列數：${outcomeCounts[QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS] || 0}`,
    `- 是否納入 hidden delta：${includeHidden ? "是" : "否"}`,
  ];
  appendFileSync(summaryPath, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const spreadsheetId = readEnv("FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID") || readEnv("FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID_SECRET");
  const sheetName = readEnv("FFLOGS_REFRESH_QUEUE_SHEET_NAME", DEFAULT_SHEET_NAME);
  const columns = readEnv("FFLOGS_REFRESH_QUEUE_RANGE_COLUMNS", DEFAULT_RANGE_COLUMNS);
  const maxRows = Math.max(1, Number.parseInt(readEnv("FFLOGS_REFRESH_QUEUE_COMPLETE_MAX_ROWS", String(DEFAULT_MAX_ROWS)), 10) || DEFAULT_MAX_ROWS);
  const includeHidden = readEnv("FFLOGS_REFRESH_QUEUE_COMPLETE_INCLUDE_HIDDEN").toLowerCase() === "true";
  const statusIndexPath = path.resolve(rootDir, readEnv("FFLOGS_REFRESH_QUEUE_STATUS_INDEX_PATH", DEFAULT_STATUS_INDEX_PATH));
  const hiddenStatusIndexPath = path.resolve(rootDir, readEnv("FFLOGS_REFRESH_QUEUE_HIDDEN_STATUS_INDEX_PATH", DEFAULT_HIDDEN_STATUS_INDEX_PATH));
  const sourceRankingsDir = path.resolve(rootDir, readEnv("FFLOGS_REFRESH_QUEUE_SOURCE_RANKINGS_DIR", DEFAULT_SOURCE_RANKINGS_DIR));
  const statePath = DEFAULT_STATE_PATH;
  const serviceAccount = parseServiceAccountJson();

  let skippedReason = "";
  let rowsRead = 0;
  const outcomeCounts = {};

  if (!spreadsheetId) {
    skippedReason = "未設定 FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID。";
  } else if (!serviceAccount.clientEmail || !serviceAccount.privateKey) {
    skippedReason = "未設定 Google Sheets service account。";
  } else if (!existsSync(statusIndexPath)) {
    skippedReason = `找不到公開索引 ${path.relative(rootDir, statusIndexPath)}。`;
  }

  if (skippedReason) {
    writeStepSummary({ skippedReason, rowsRead, outcomeCounts, includeHidden });
    console.log(`略過 FFLogs 待收錄名單收尾：${skippedReason}`);
    return;
  }

  const accessToken = await requestAccessToken(serviceAccount, SHEETS_WRITE_SCOPE);
  const values = await readSheetValues({ spreadsheetId, sheetName, columns, accessToken });
  const { headers, rows } = rowsToObjects(values);
  rowsRead = rows.length;
  const indexedReports = await buildIndexedReportSet({
    statusIndexPath,
    hiddenStatusIndexPath,
    sourceRankingsDir,
    includeHidden,
  });
  const queuedRows = rows.filter((row) => {
    const status = normalizeHeader(row.status || "queued");
    return QUEUED_STATUSES.has(status);
  });
  const statusesByCode = buildReportStatusesByCode(
    await readJsonIfExists(statePath),
    queuedRows.map((row) => row.report_code),
  );
  const rowsToUpdate = queuedRows
    .filter((row) => resolveQueueOutcome(row, indexedReports, statusesByCode))
    .slice(0, maxRows);
  const updates = buildUpdateRanges({
    headers,
    rows: rowsToUpdate,
    sheetName,
    nowIso: new Date().toISOString(),
    maxRows,
    indexedReportCodes: indexedReports,
    statusesByCode,
  });

  if (updates.length > 0) {
    await batchUpdateSheetValues({ spreadsheetId, accessToken, data: updates });
  }

  for (const row of rowsToUpdate) {
    const outcome = resolveQueueOutcome(row, indexedReports, statusesByCode);
    outcomeCounts[outcome] = (outcomeCounts[outcome] || 0) + 1;
  }
  writeStepSummary({ rowsRead, outcomeCounts, includeHidden });
  console.log(
    "已更新 FFLogs 待收錄列："
      + `已收錄 ${outcomeCounts[QUEUE_OUTCOME.COLLECTED] || 0}、`
      + `無通關 ${outcomeCounts[QUEUE_OUTCOME.NO_CLEAR] || 0}、`
      + `無繁中服玩家 ${outcomeCounts[QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS] || 0}`,
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
