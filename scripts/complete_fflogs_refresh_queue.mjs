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

// Apps Script 與 workflow 都以這組欄位順序存取同一份 Sheet。工作表可能曾被
// 手動編修；若標題被覆蓋為重複欄位，依欄位名稱組裝的資料會把值寫進錯誤語意。
// 因此 workflow 收尾時也會校正 A:N 的既有 schema，但不碰任何歷史資料列。
export const QUEUE_HEADERS = Object.freeze([
  "submitted_at_iso",
  "updated_at_iso",
  "report_code",
  "report_url",
  "requested_action",
  "site_status",
  "fight_text",
  "fflogs_access",
  "visibility",
  "archive_accessible",
  "status",
  "request_count",
  "last_message",
  "source",
]);

const QUEUE_OUTCOME = {
  COLLECTED: "collected",
  HIDDEN: "hidden",
  NO_CLEAR: "no_clear",
  NO_TRADITIONAL_CHINESE_PLAYERS: "no_traditional_chinese_players",
};
const VISIBILITY_REVIEW_ACTION = "review_existing_visibility";

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

export function rowsToObjects(values, { headersOverride } = {}) {
  if (!Array.isArray(values) || values.length === 0) {
    return { headers: [], rows: [] };
  }

  const headers = Array.isArray(headersOverride)
    ? headersOverride.map(normalizeHeader)
    : values[0].map(normalizeHeader);
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

export function canonicalizeQueueHeaders(headers) {
  const normalizedHeaders = Array.isArray(headers) ? headers.map(normalizeHeader) : [];
  return Array.from(
    { length: Math.max(normalizedHeaders.length, QUEUE_HEADERS.length) },
    (_value, index) => QUEUE_HEADERS[index] || normalizedHeaders[index] || "",
  );
}

export function buildHeaderRepairRanges({ headers, sheetName }) {
  return QUEUE_HEADERS.flatMap((expectedHeader, index) => {
    if (normalizeHeader(headers?.[index]) === expectedHeader) {
      return [];
    }
    return [{
      range: quoteSheetRange(sheetName, `${columnNameFromIndex(index)}1`),
      values: [[expectedHeader]],
    }];
  });
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
  return [ranking?.ranking_entries].filter(Array.isArray);
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

export async function buildHiddenReportSet({ hiddenStatusIndexPath }) {
  // 公開狀態重新排查只會由「本站已收錄」的 report 發起。workflow 已在本步驟前
  // 重建 hidden delta 索引，因此只需讀取它就能確認這次重查是否真的把 report
  // 從一般公開資料移除；不能用 FFLogs 即時查詢結果直接結束 queue，以免暫時性
  // 錯誤或前端偽造參數就被當成隱藏成功。
  const hiddenReportCodes = new Set();
  addReportStatusIndex(await readJsonIfExists(hiddenStatusIndexPath), hiddenReportCodes);
  return hiddenReportCodes;
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

function isVisibilityReviewRequest(row) {
  return normalizeHeader(row?.requested_action || row?.request_type) === VISIBILITY_REVIEW_ACTION;
}

export function resolveQueueOutcome(row, indexedReportCodes, statusesByCode, hiddenReportCodes = new Set()) {
  if (isVisibilityReviewRequest(row) && isRowIndexed(row, hiddenReportCodes)) {
    return QUEUE_OUTCOME.HIDDEN;
  }

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
    case QUEUE_OUTCOME.HIDDEN:
      return "hidden";
    case QUEUE_OUTCOME.NO_CLEAR:
      return "not_eligible_no_clear";
    case QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS:
      return "not_eligible_no_traditional_chinese_players";
    default:
      return "";
  }
}

function queueOutcomeMessage(row, outcome) {
  if (outcome === QUEUE_OUTCOME.HIDDEN) {
    return "workflow 已重新確認 FFLogs 不可公開讀取，既有公開紀錄已標記為 hidden。";
  }
  if (outcome === QUEUE_OUTCOME.COLLECTED) {
    // 現行 Apps Script 欄位是 requested_action；保留 request_type fallback，讓舊的
    // 手動匯入列仍可呈現正確的重掃結果，而不是一律退回首次收錄訊息。
    const requestedAction = normalizeHeader(row.requested_action || row.request_type);
    return requestedAction === "retry_existing"
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

function queueOutcomeFromTerminalStatus(status) {
  switch (normalizeHeader(status)) {
    case "done":
      return QUEUE_OUTCOME.COLLECTED;
    case "hidden":
      return QUEUE_OUTCOME.HIDDEN;
    case "not_eligible_no_clear":
      return QUEUE_OUTCOME.NO_CLEAR;
    case "not_eligible_no_traditional_chinese_players":
      return QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS;
    default:
      return null;
  }
}

function hasMalformedLastMessage(row) {
  // last_message 為人工可讀的處理摘要，不應是純數字。這也能修正舊版重複
  // request_count 標題造成的歷史值，例如 "1"；不改寫非空的人工備註。
  return /^\d+$/.test(String(row.last_message || "").trim());
}

export function buildUpdateRanges({
  headers,
  rows,
  sheetName,
  nowIso,
  maxRows,
  indexedReportCodes,
  statusesByCode,
  hiddenReportCodes,
}) {
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
    const outcome = resolveQueueOutcome(row, indexedReportCodes, statusesByCode, hiddenReportCodes);
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

export function buildMalformedMessageRepairRanges({
  headers,
  rows,
  sheetName,
  indexedReportCodes,
  statusesByCode,
  hiddenReportCodes,
  updatedRowNumbers = new Set(),
}) {
  const lastMessageIndex = headers.indexOf("last_message");
  if (lastMessageIndex < 0) {
    throw new Error("Google Sheet 待收錄名單缺少 last_message 欄位。");
  }

  return rows.flatMap((row) => {
    if (updatedRowNumbers.has(row._row_number) || !hasMalformedLastMessage(row)) {
      return [];
    }
    const outcome = queueOutcomeFromTerminalStatus(row.status)
      || resolveQueueOutcome(row, indexedReportCodes, statusesByCode, hiddenReportCodes);
    if (!outcome) {
      return [];
    }
    const lastMessageCell = `${columnNameFromIndex(lastMessageIndex)}${row._row_number}`;
    return [{
      range: quoteSheetRange(sheetName, lastMessageCell),
      values: [[queueOutcomeMessage(row, outcome)]],
    }];
  });
}

function writeStepSummary({ skippedReason, rowsRead, outcomeCounts, includeHidden, repairedHeaderCount = 0, repairedMessageCount = 0 }) {
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
    `- 已隱藏完成列數：${outcomeCounts[QUEUE_OUTCOME.HIDDEN] || 0}`,
    `- 無通關終止列數：${outcomeCounts[QUEUE_OUTCOME.NO_CLEAR] || 0}`,
    `- 無繁中服玩家終止列數：${outcomeCounts[QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS] || 0}`,
    `- 修正欄位標題數：${repairedHeaderCount}`,
    `- 修正錯置訊息列數：${repairedMessageCount}`,
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
  const { headers: rawHeaders } = rowsToObjects(values);
  const headers = canonicalizeQueueHeaders(rawHeaders);
  const { rows } = rowsToObjects(values, { headersOverride: headers });
  rowsRead = rows.length;
  const indexedReports = await buildIndexedReportSet({
    statusIndexPath,
    hiddenStatusIndexPath,
    sourceRankingsDir,
    includeHidden,
  });
  const hiddenReportCodes = await buildHiddenReportSet({ hiddenStatusIndexPath });
  const queuedRows = rows.filter((row) => {
    const status = normalizeHeader(row.status || "queued");
    return QUEUED_STATUSES.has(status);
  });
  const statusesByCode = buildReportStatusesByCode(
    await readJsonIfExists(statePath),
    queuedRows.map((row) => row.report_code),
  );
  const rowsToUpdate = queuedRows
    .filter((row) => resolveQueueOutcome(row, indexedReports, statusesByCode, hiddenReportCodes))
    .slice(0, maxRows);
  const outcomeUpdates = buildUpdateRanges({
    headers,
    rows: rowsToUpdate,
    sheetName,
    nowIso: new Date().toISOString(),
    maxRows,
    indexedReportCodes: indexedReports,
    statusesByCode,
    hiddenReportCodes,
  });
  const updatedRowNumbers = new Set(rowsToUpdate.map((row) => row._row_number));
  const headerUpdates = buildHeaderRepairRanges({ headers: rawHeaders, sheetName });
  const malformedMessageUpdates = buildMalformedMessageRepairRanges({
    headers,
    rows,
    sheetName,
    indexedReportCodes: indexedReports,
    statusesByCode,
    hiddenReportCodes,
    updatedRowNumbers,
  });
  const updates = [...headerUpdates, ...outcomeUpdates, ...malformedMessageUpdates];

  if (updates.length > 0) {
    await batchUpdateSheetValues({ spreadsheetId, accessToken, data: updates });
  }

  for (const row of rowsToUpdate) {
    const outcome = resolveQueueOutcome(row, indexedReports, statusesByCode, hiddenReportCodes);
    outcomeCounts[outcome] = (outcomeCounts[outcome] || 0) + 1;
  }
  writeStepSummary({
    rowsRead,
    outcomeCounts,
    includeHidden,
    repairedHeaderCount: headerUpdates.length,
    repairedMessageCount: malformedMessageUpdates.length,
  });
  console.log(
    "已更新 FFLogs 待收錄列："
      + `已收錄 ${outcomeCounts[QUEUE_OUTCOME.COLLECTED] || 0}、`
      + `已隱藏 ${outcomeCounts[QUEUE_OUTCOME.HIDDEN] || 0}、`
      + `無通關 ${outcomeCounts[QUEUE_OUTCOME.NO_CLEAR] || 0}、`
      + `無繁中服玩家 ${outcomeCounts[QUEUE_OUTCOME.NO_TRADITIONAL_CHINESE_PLAYERS] || 0}、`
      + `修正欄位 ${headerUpdates.length}、修正訊息 ${malformedMessageUpdates.length}`,
  );
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((error) => {
    console.error(error instanceof Error ? error.message : error);
    process.exitCode = 1;
  });
}
