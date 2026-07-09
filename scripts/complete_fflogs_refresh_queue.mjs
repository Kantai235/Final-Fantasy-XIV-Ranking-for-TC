import { appendFileSync, existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
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
const DEFAULT_MAX_ROWS = 500;
const REPORT_CODE_PATTERN = /^[A-Za-z0-9]{8,32}$/;
const QUEUED_STATUSES = new Set(["queued", "pending", "retry"]);

function normalizeHeader(value) {
  return String(value || "").trim().toLowerCase();
}

function normalizeReportCode(value) {
  return String(value || "").trim().replace(/^a:/i, "");
}

function parsePositiveInteger(value) {
  const text = String(value || "").trim();
  if (!/^\d+$/.test(text)) {
    return null;
  }
  const number = Number(text);
  return Number.isSafeInteger(number) && number > 0 ? number : null;
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

function addReportStatusIndex(index, reportCodeToFights) {
  const reportColumns = index?.report_columns || [];
  const fightColumns = index?.fight_columns || [];
  for (const row of index?.reports || []) {
    const report = rowToObject(row, reportColumns);
    const reportCode = normalizeReportCode(report.report_code);
    if (!REPORT_CODE_PATTERN.test(reportCode)) {
      continue;
    }
    if (!reportCodeToFights.has(reportCode)) {
      reportCodeToFights.set(reportCode, new Set());
    }
    const fightIds = reportCodeToFights.get(reportCode);
    for (const fightRow of report.fights || []) {
      const fight = rowToObject(fightRow, fightColumns);
      const fightId = Number(fight.fight_id);
      if (Number.isSafeInteger(fightId) && fightId > 0) {
        fightIds.add(fightId);
      }
    }
  }
}

async function buildIndexedReportMap({ statusIndexPath, hiddenStatusIndexPath, includeHidden }) {
  const reportCodeToFights = new Map();
  addReportStatusIndex(await readJsonIfExists(statusIndexPath), reportCodeToFights);
  if (includeHidden) {
    addReportStatusIndex(await readJsonIfExists(hiddenStatusIndexPath), reportCodeToFights);
  }
  return reportCodeToFights;
}

function isRowIndexed(row, reportCodeToFights) {
  const reportCode = normalizeReportCode(row.report_code);
  if (!REPORT_CODE_PATTERN.test(reportCode) || !reportCodeToFights.has(reportCode)) {
    return false;
  }

  const requestedFightId = parsePositiveInteger(row.fight_text);
  if (!requestedFightId) {
    return true;
  }
  return reportCodeToFights.get(reportCode).has(requestedFightId);
}

function buildUpdateRanges({ headers, rows, sheetName, nowIso, maxRows }) {
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
    const hasRequestedFight = Boolean(parsePositiveInteger(row.fight_text));
    const message = hasRequestedFight
      ? "workflow 已確認公開索引收錄指定 fight。"
      : "workflow 已確認公開索引收錄 report。";

    return [
      {
        range: quoteSheetRange(sheetName, statusCell),
        values: [["done"]],
      },
      {
        range: quoteSheetRange(sheetName, updatedAtCell),
        values: [[nowIso]],
      },
      {
        range: quoteSheetRange(sheetName, lastMessageCell),
        values: [[message]],
      },
    ];
  });
}

function writeStepSummary({ skippedReason, rowsRead, completedRows, includeHidden }) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (!summaryPath) {
    return;
  }

  const lines = [
    "### FFLogs 待收錄名單收尾",
    "",
    skippedReason ? `- 略過：${skippedReason}` : "- 已檢查 Google Sheet 待收錄名單。",
    `- 讀取列數：${rowsRead}`,
    `- 標記完成列數：${completedRows}`,
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
  const serviceAccount = parseServiceAccountJson();

  let skippedReason = "";
  let rowsRead = 0;
  let completedRows = 0;

  if (!spreadsheetId) {
    skippedReason = "未設定 FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID。";
  } else if (!serviceAccount.clientEmail || !serviceAccount.privateKey) {
    skippedReason = "未設定 Google Sheets service account。";
  } else if (!existsSync(statusIndexPath)) {
    skippedReason = `找不到公開索引 ${path.relative(rootDir, statusIndexPath)}。`;
  }

  if (skippedReason) {
    writeStepSummary({ skippedReason, rowsRead, completedRows, includeHidden });
    console.log(`略過 FFLogs 待收錄名單收尾：${skippedReason}`);
    return;
  }

  const accessToken = await requestAccessToken(serviceAccount, SHEETS_WRITE_SCOPE);
  const values = await readSheetValues({ spreadsheetId, sheetName, columns, accessToken });
  const { headers, rows } = rowsToObjects(values);
  rowsRead = rows.length;
  const indexedReports = await buildIndexedReportMap({ statusIndexPath, hiddenStatusIndexPath, includeHidden });
  const completed = rows.filter((row) => {
    const status = normalizeHeader(row.status || "queued");
    return QUEUED_STATUSES.has(status) && isRowIndexed(row, indexedReports);
  });
  const limitedCompleted = completed.slice(0, maxRows);
  const updates = buildUpdateRanges({
    headers,
    rows: limitedCompleted,
    sheetName,
    nowIso: new Date().toISOString(),
    maxRows,
  });

  if (updates.length > 0) {
    await batchUpdateSheetValues({ spreadsheetId, accessToken, data: updates });
  }

  completedRows = limitedCompleted.length;
  writeStepSummary({ rowsRead, completedRows, includeHidden });
  console.log(`已標記 FFLogs 待收錄完成列數：${completedRows}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
