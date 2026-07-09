import { appendFileSync } from "node:fs";
import {
  parseServiceAccountJson,
  readEnv,
  readSheetValues,
  requestAccessToken,
  SHEETS_READONLY_SCOPE,
} from "./google_sheets_service_account.mjs";

const DEFAULT_SHEET_NAME = "pending";
const DEFAULT_RANGE_COLUMNS = "A:Z";
const DEFAULT_MAX_CODES = 50;
const REPORT_CODE_PATTERN = /^[A-Za-z0-9]{8,32}$/;
const QUEUED_STATUSES = new Set(["queued", "pending", "retry"]);

function splitReportCodes(value) {
  return String(value || "")
    .split(/[,\s]+/)
    .map((code) => code.trim().replace(/^a:/i, ""))
    .filter((code) => REPORT_CODE_PATTERN.test(code));
}

function uniqueReportCodes(codes) {
  return Array.from(new Set(codes));
}

function normalizeHeader(value) {
  return String(value || "").trim().toLowerCase();
}

function rowsToObjects(values) {
  if (!Array.isArray(values) || values.length < 2) {
    return [];
  }

  const headers = values[0].map(normalizeHeader);
  return values.slice(1).map((row, index) => {
    const item = { _row_number: index + 2 };
    headers.forEach((header, columnIndex) => {
      if (header) {
        item[header] = row[columnIndex] ?? "";
      }
    });
    return item;
  });
}

function selectQueuedReportCodes(rows, maxCodes) {
  const selected = [];
  for (const row of rows) {
    const status = normalizeHeader(row.status || "queued");
    const reportCode = String(row.report_code || "").trim().replace(/^a:/i, "");
    if (!QUEUED_STATUSES.has(status) || !REPORT_CODE_PATTERN.test(reportCode)) {
      continue;
    }
    selected.push(reportCode);
    if (selected.length >= maxCodes) {
      break;
    }
  }
  return uniqueReportCodes(selected);
}

function writeGithubValue(filePath, name, value) {
  if (!filePath) {
    return;
  }
  appendFileSync(filePath, `${name}=${value}\n`, "utf8");
}

function writeStepSummary({ codes, rowsRead, spreadsheetId, sheetName, skippedReason }) {
  const summaryPath = process.env.GITHUB_STEP_SUMMARY;
  if (!summaryPath) {
    return;
  }

  const lines = [
    "### FFLogs 待收錄名單",
    "",
    skippedReason
      ? `- 狀態：${skippedReason}`
      : `- 來源：Google Sheet \`${spreadsheetId}\` / \`${sheetName}\``,
    `- 讀取列數：${rowsRead}`,
    `- 本輪送入 retry_report_codes：${codes.length}`,
  ];
  if (codes.length > 0) {
    lines.push(`- Report codes：${codes.slice(0, 20).join(", ")}${codes.length > 20 ? " ..." : ""}`);
  }
  appendFileSync(summaryPath, `${lines.join("\n")}\n`, "utf8");
}

async function main() {
  const spreadsheetId = readEnv("FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID") || readEnv("FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID_SECRET");
  const sheetName = readEnv("FFLOGS_REFRESH_QUEUE_SHEET_NAME", DEFAULT_SHEET_NAME);
  const columns = readEnv("FFLOGS_REFRESH_QUEUE_RANGE_COLUMNS", DEFAULT_RANGE_COLUMNS);
  const maxCodes = Math.max(1, Number.parseInt(readEnv("FFLOGS_REFRESH_QUEUE_MAX_CODES", String(DEFAULT_MAX_CODES)), 10) || DEFAULT_MAX_CODES);
  const extraCodes = splitReportCodes(readEnv("FFLOGS_REFRESH_QUEUE_EXTRA_REPORT_CODES"));
  const serviceAccount = parseServiceAccountJson();

  let rowsRead = 0;
  let queuedCodes = [];
  let skippedReason = "";

  if (!spreadsheetId) {
    skippedReason = "未設定 FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID，略過 Google Sheet 待收錄名單。";
  } else if (!serviceAccount.clientEmail || !serviceAccount.privateKey) {
    skippedReason = "未設定 Google Sheets service account，略過 Google Sheet 待收錄名單。";
  } else {
    const accessToken = await requestAccessToken(serviceAccount, SHEETS_READONLY_SCOPE);
    const values = await readSheetValues({ spreadsheetId, sheetName, columns, accessToken });
    const rows = rowsToObjects(values);
    rowsRead = rows.length;
    queuedCodes = selectQueuedReportCodes(rows, maxCodes);
  }

  const codes = uniqueReportCodes([...extraCodes, ...queuedCodes]).slice(0, maxCodes);
  const joinedCodes = codes.join(",");
  writeGithubValue(process.env.GITHUB_ENV, "FFLOGS_RETRY_REPORT_CODES", joinedCodes);
  writeGithubValue(process.env.GITHUB_OUTPUT, "report_codes", joinedCodes);
  writeGithubValue(process.env.GITHUB_OUTPUT, "report_count", String(codes.length));
  writeStepSummary({ codes, rowsRead, spreadsheetId, sheetName, skippedReason });

  if (skippedReason) {
    console.log(skippedReason);
  }
  console.log(`本輪 FFLogs 待收錄 report code：${codes.length > 0 ? joinedCodes : "無"}`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
