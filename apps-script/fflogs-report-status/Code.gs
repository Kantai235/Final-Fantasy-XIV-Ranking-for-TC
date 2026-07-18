const SCRIPT_VERSION = "fflogs-report-status-v4";
const FFLOGS_TOKEN_URL = "https://www.fflogs.com/oauth/token";
const FFLOGS_API_URL = "https://www.fflogs.com/api/v2/client";
const REPORT_CODE_PATTERN = /^[A-Za-z0-9]{8,32}$/;
const JSONP_CALLBACK_PATTERN = /^[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*){0,3}$/;
const REPORT_STATUS_CACHE_SECONDS = 180;
const TOKEN_CACHE_SECONDS_FALLBACK = 3300;
const TOKEN_CACHE_SAFETY_SECONDS = 120;
const QUEUE_SHEET_NAME_DEFAULT = "pending";
const QUEUE_SUBMIT_CACHE_SECONDS = 20;
const QUEUE_HEADERS = Object.freeze([
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

const REPORT_STATUS_QUERY = `
query ReportStatus($code: String!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      visibility
      archiveStatus {
        isArchived
        isAccessible
        archiveDate
      }
    }
  }
}
`;

function doGet(event) {
  const startedAt = new Date();
  const params = event && event.parameter ? event.parameter : {};
  let callback = "";

  try {
    callback = normalizeJsonpCallback_(params.callback || params.prefix);
    const reportCode = parseReportCode_(params.report || params.code || params.url || "");
    const action = normalizeAction_(params.action);
    const result = action === "enqueue"
      ? enqueueReportRefresh_(reportCode, params, startedAt)
      : checkReportStatus_(reportCode, startedAt);
    return output_(result, callback);
  } catch (error) {
    return output_(buildErrorResult_(error, startedAt), callback);
  }
}

function checkReportStatus_(reportCode, startedAt) {
  const cache = CacheService.getScriptCache();
  const cacheKey = `report-status:${reportCode}`;
  const cachedText = cache.get(cacheKey);
  if (cachedText) {
    const cached = JSON.parse(cachedText);
    cached.cache_hit = true;
    cached.checked_at_iso = new Date().toISOString();
    return cached;
  }

  const fflogsResult = fetchReportStatusFromFflogs_(reportCode);
  const result = normalizeFflogsReportResult_(reportCode, fflogsResult, startedAt);
  cache.put(cacheKey, JSON.stringify(result), REPORT_STATUS_CACHE_SECONDS);
  return result;
}

function fetchReportStatusFromFflogs_(reportCode) {
  const token = getFflogsBearerToken_();
  const response = UrlFetchApp.fetch(FFLOGS_API_URL, {
    method: "post",
    contentType: "application/json",
    headers: {
      Authorization: `Bearer ${token}`,
    },
    payload: JSON.stringify({
      query: REPORT_STATUS_QUERY,
      variables: { code: reportCode },
    }),
    muteHttpExceptions: true,
  });

  const statusCode = response.getResponseCode();
  const bodyText = response.getContentText();
  if (statusCode === 429) {
    throw new PublicStatusError_("rate_limited", "FFLogs 目前回傳限流，請稍後再試。", statusCode);
  }
  if ([500, 502, 503, 504].indexOf(statusCode) >= 0) {
    throw new PublicStatusError_("temporary_error", "FFLogs 目前暫時無法查詢，請稍後再試。", statusCode);
  }
  if (statusCode < 200 || statusCode >= 300) {
    throw new PublicStatusError_("temporary_error", "FFLogs 查詢失敗，請稍後再試。", statusCode);
  }

  const payload = parseJson_(bodyText, "FFLogs 回應不是有效 JSON。");
  if (Array.isArray(payload.errors) && payload.errors.length > 0) {
    if (isReportAccessError_(payload.errors)) {
      return {
        report: null,
        access_error: true,
        graph_errors: payload.errors,
      };
    }
    throw new PublicStatusError_("temporary_error", "FFLogs 回傳 GraphQL 錯誤，請稍後再試。", statusCode);
  }

  const report = payload
    && payload.data
    && payload.data.reportData
    && payload.data.reportData.report;
  if (!report || typeof report !== "object") {
    return {
      report: null,
      access_error: true,
      graph_errors: [],
    };
  }

  return {
    report,
    access_error: false,
    graph_errors: [],
  };
}

function normalizeFflogsReportResult_(reportCode, fflogsResult, startedAt) {
  if (fflogsResult.access_error) {
    return {
      ok: true,
      script_version: SCRIPT_VERSION,
      report_code: reportCode,
      checked_at_iso: new Date().toISOString(),
      elapsed_ms: new Date().getTime() - startedAt.getTime(),
      cache_hit: false,
      fflogs_access: "private_or_deleted",
      visibility: null,
      archive_accessible: null,
      report_title: null,
      report_start_time: null,
      report_end_time: null,
      report_url: `https://www.fflogs.com/reports/${reportCode}`,
      message: "FFLogs API 目前無法讀取這份 report。常見原因是 Private、已刪除、不存在，或 OAuth client 沒有存取權限。",
    };
  }

  const report = fflogsResult.report;
  const archiveStatus = report.archiveStatus || {};
  const archiveAccessible = archiveStatus.isAccessible !== false;
  const fflogsAccess = archiveAccessible ? "accessible" : "archived_inaccessible";
  return {
    ok: true,
    script_version: SCRIPT_VERSION,
    report_code: reportCode,
    checked_at_iso: new Date().toISOString(),
    elapsed_ms: new Date().getTime() - startedAt.getTime(),
    cache_hit: false,
    fflogs_access: fflogsAccess,
    visibility: report.visibility || null,
    archive_accessible: archiveAccessible,
    report_title: report.title || null,
    report_start_time: Number(report.startTime) || null,
    report_end_time: Number(report.endTime) || null,
    report_url: `https://www.fflogs.com/reports/${reportCode}`,
    message: archiveAccessible
      ? "FFLogs API 目前可讀取這份 report。是否收錄仍需等待排行榜資料管線確認繁中服玩家、支援副本與通關 fight。"
      : "FFLogs API 找到這份 report，但封存狀態目前不可存取。",
  };
}

function enqueueReportRefresh_(reportCode, params, startedAt) {
  const cache = CacheService.getScriptCache();
  const submitCacheKey = `queue-submit:${reportCode}`;
  if (cache.get(submitCacheKey)) {
    return {
      ok: false,
      script_version: SCRIPT_VERSION,
      report_code: reportCode,
      checked_at_iso: new Date().toISOString(),
      elapsed_ms: new Date().getTime() - startedAt.getTime(),
      error_code: "rate_limited",
      queue_status: "rate_limited",
      message: "這份 report 剛剛已經送出過，請稍候再試。",
    };
  }

  const fflogsResult = fetchReportStatusFromFflogs_(reportCode);
  const statusResult = normalizeFflogsReportResult_(reportCode, fflogsResult, startedAt);
  const requestedAction = normalizeRequestedAction_(params.request_type || params.requested_action);
  const siteStatus = normalizeSiteStatus_(params.site_status);
  const isVisibilityReview = requestedAction === "review_existing_visibility"
    && (siteStatus === "found" || siteStatus === "fight_missing");
  const isPublicReadable = statusResult.ok === true
    && statusResult.fflogs_access === "accessible"
    && String(statusResult.visibility || "").toLowerCase() === "public";

  // 新收錄與一般重查都只能處理 Public report，避免把目前無權存取的內容送進
  // 補抓管線。唯一例外是本站已收錄、且前端剛確認 FFLogs 不再公開可讀的紀錄：
  // 此時把 report code 送進既有重查入口，讓下一輪 fetch_fflogs.py 再以受保護的
  // client 確認；若仍不可存取，資料管線才會在來源分片加上 hidden 標記。
  if (
    !isPublicReadable
    && !isVisibilityReview
  ) {
    return {
      ...statusResult,
      queue_status: "rejected_not_public",
      message: "這份 FFLogs 目前不是 Public 且可讀狀態；只有本站已收錄的 report 才可要求伺服器重新確認公開狀態。",
    };
  }

  const fightText = normalizeFightText_(params.fight || params.fight_text);
  const source = normalizeSource_(params.source);
  let queueResult = null;
  try {
    queueResult = upsertQueueRow_({
      reportCode,
      reportUrl: statusResult.report_url,
      requestedAction,
      siteStatus,
      fightText,
      fflogsAccess: statusResult.fflogs_access,
      visibility: statusResult.visibility,
      archiveAccessible: statusResult.archive_accessible,
      source,
    });
  } catch (error) {
    if (error instanceof PublicStatusError_) {
      throw error;
    }
    throw new PublicStatusError_(
      "queue_write_error",
      "本站伺服器暫時無法安排這份 report 的排查，請稍後再試。",
      null,
      buildSafeDebugMessage_(error),
    );
  }

  cache.put(submitCacheKey, "1", QUEUE_SUBMIT_CACHE_SECONDS);
  return {
    ...statusResult,
    queue_status: queueResult.created ? "queued" : "updated",
    queue_row: queueResult.row,
    request_count: queueResult.requestCount,
    requested_action: requestedAction,
    site_status: siteStatus,
    message: queueResult.created
      ? (isVisibilityReview
        ? "已安排伺服器重新確認公開狀態；後續資料更新時會確認 report 是否仍不可公開讀取。"
        : "已安排伺服器排查，會在後續資料更新時嘗試抓取。")
      : (isVisibilityReview
        ? "這份 report 已交由伺服器重新確認公開狀態，已更新送出時間與重查次數。"
        : "這份 report 已交由伺服器排查，已更新送出時間與重查次數。"),
  };
}

function upsertQueueRow_(entry) {
  const spreadsheetId = String(PropertiesService.getScriptProperties().getProperty("FFLOGS_QUEUE_SPREADSHEET_ID") || "").trim();
  if (!spreadsheetId) {
    throw new PublicStatusError_("server_config_error", "即時查詢服務暫時無法使用，請稍後再試。", null);
  }

  const sheetName = String(PropertiesService.getScriptProperties().getProperty("FFLOGS_QUEUE_SHEET_NAME") || QUEUE_SHEET_NAME_DEFAULT).trim();
  const lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
    const sheet = spreadsheet.getSheetByName(sheetName) || spreadsheet.insertSheet(sheetName);
    ensureQueueHeader_(sheet);

    const values = sheet.getDataRange().getValues();
    const headers = values[0].map((header) => String(header || "").trim());
    const reportCodeIndex = headers.indexOf("report_code");
    const nowIso = new Date().toISOString();
    const existingRowIndex = values.findIndex((row, index) =>
      index > 0 && String(row[reportCodeIndex] || "").trim() === entry.reportCode
    );
    const rowValues = buildQueueRowValues_(headers, entry, nowIso, existingRowIndex >= 0 ? values[existingRowIndex] : null);

    if (existingRowIndex >= 0) {
      const sheetRow = existingRowIndex + 1;
      sheet.getRange(sheetRow, 1, 1, headers.length).setValues([rowValues]);
      return {
        created: false,
        row: sheetRow,
        requestCount: Number(rowValues[headers.indexOf("request_count")]) || 1,
      };
    }

    sheet.appendRow(rowValues);
    return {
      created: true,
      row: sheet.getLastRow(),
      requestCount: 1,
    };
  } finally {
    lock.releaseLock();
  }
}

function ensureQueueHeader_(sheet) {
  const headerValues = sheet.getRange(1, 1, 1, QUEUE_HEADERS.length).getValues()[0];
  const hasAnyHeader = headerValues.some((value) => String(value || "").trim());
  if (!hasAnyHeader) {
    sheet.getRange(1, 1, 1, QUEUE_HEADERS.length).setValues([QUEUE_HEADERS]);
    sheet.setFrozenRows(1);
    return;
  }

  const normalizedHeaders = headerValues.map((value) => String(value || "").trim());
  const hasExpectedSchema = QUEUE_HEADERS.every((header, index) => normalizedHeaders[index] === header);
  if (!hasExpectedSchema) {
    // 僅回復標題列的 A:N 固定 schema，絕不改寫既有 report 資料。舊版只把缺少
    // 欄位加在尾端，若有人把 last_message 改成第二個 request_count，後續寫入便會
    // 把計數值放進訊息欄；以固定位置回復才能保留每列既有欄位語意。
    sheet.getRange(1, 1, 1, QUEUE_HEADERS.length).setValues([QUEUE_HEADERS]);
  }
  sheet.setFrozenRows(1);
}

function buildQueueRowValues_(headers, entry, nowIso, existingRow) {
  const existing = existingRow || [];
  const requestCountIndex = headers.indexOf("request_count");
  const previousRequestCount = requestCountIndex >= 0 ? Number(existing[requestCountIndex]) || 0 : 0;
  const valuesByHeader = {
    submitted_at_iso: existing[headers.indexOf("submitted_at_iso")] || nowIso,
    updated_at_iso: nowIso,
    report_code: entry.reportCode,
    report_url: entry.reportUrl,
    requested_action: entry.requestedAction,
    site_status: entry.siteStatus,
    fight_text: entry.fightText,
    fflogs_access: entry.fflogsAccess,
    visibility: entry.visibility || "",
    archive_accessible: entry.archiveAccessible === true ? "TRUE" : entry.archiveAccessible === false ? "FALSE" : "",
    status: "queued",
    request_count: previousRequestCount + 1,
    last_message: "等待伺服器處理。",
    source: entry.source,
  };

  return headers.map((header, index) =>
    Object.prototype.hasOwnProperty.call(valuesByHeader, header) ? valuesByHeader[header] : existing[index] || ""
  );
}

function getFflogsBearerToken_() {
  const cache = CacheService.getScriptCache();
  const cachedToken = cache.get("fflogs:bearer-token");
  if (cachedToken) {
    return cachedToken;
  }

  const props = PropertiesService.getScriptProperties();
  const clientId = String(props.getProperty("FFLOGS_CLIENT_ID") || "").trim();
  const clientSecret = String(props.getProperty("FFLOGS_CLIENT_SECRET") || "").trim();
  if (!clientId || !clientSecret) {
    throw new PublicStatusError_("server_config_error", "即時查詢服務暫時無法使用，請稍後再試。", null);
  }

  const response = UrlFetchApp.fetch(FFLOGS_TOKEN_URL, {
    method: "post",
    headers: {
      Authorization: `Basic ${Utilities.base64Encode(`${clientId}:${clientSecret}`)}`,
    },
    payload: {
      grant_type: "client_credentials",
    },
    muteHttpExceptions: true,
  });

  const statusCode = response.getResponseCode();
  const bodyText = response.getContentText();
  if (statusCode === 429) {
    throw new PublicStatusError_("rate_limited", "FFLogs OAuth 目前回傳限流，請稍後再試。", statusCode);
  }
  if ([500, 502, 503, 504].indexOf(statusCode) >= 0) {
    throw new PublicStatusError_("temporary_error", "FFLogs OAuth 暫時無法取得 token，請稍後再試。", statusCode);
  }
  if (statusCode < 200 || statusCode >= 300) {
    throw new PublicStatusError_("server_config_error", "FFLogs 即時查詢服務暫時無法使用，請稍後再試。", statusCode);
  }

  const payload = parseJson_(bodyText, "FFLogs OAuth 回應不是有效 JSON。");
  const token = String(payload.access_token || "").trim();
  if (!token) {
    throw new PublicStatusError_("server_config_error", "FFLogs OAuth 回應缺少 access_token。", statusCode);
  }

  const expiresIn = Number(payload.expires_in) || TOKEN_CACHE_SECONDS_FALLBACK;
  const cacheSeconds = Math.max(60, Math.min(TOKEN_CACHE_SECONDS_FALLBACK, expiresIn - TOKEN_CACHE_SAFETY_SECONDS));
  cache.put("fflogs:bearer-token", token, cacheSeconds);
  return token;
}

function parseReportCode_(input) {
  const rawText = String(input || "").trim();
  if (!rawText) {
    throw new PublicStatusError_("invalid_report_code", "請輸入 FFLogs report code 或 report 網址。", null);
  }

  const directCode = rawText.replace(/^a:/i, "");
  if (REPORT_CODE_PATTERN.test(directCode)) {
    return directCode;
  }

  const urlMatch = rawText.match(/^(?:https?:\/\/)?([A-Za-z0-9.-]+)\/reports\/(?:a:)?([A-Za-z0-9]{8,32})(?:[/?#]|$)/i);
  if (!urlMatch) {
    throw new PublicStatusError_("invalid_report_code", "無法解析 FFLogs report 網址。", null);
  }

  const hostname = String(urlMatch[1] || "").toLowerCase();
  if (hostname !== "fflogs.com" && !hostname.endsWith(".fflogs.com")) {
    throw new PublicStatusError_("invalid_report_code", "請輸入 fflogs.com 的 report 網址。", null);
  }

  const code = String(urlMatch[2] || "").replace(/^a:/i, "");
  if (!REPORT_CODE_PATTERN.test(code)) {
    throw new PublicStatusError_("invalid_report_code", "網址中找不到有效的 FFLogs report code。", null);
  }
  return code;
}

function isReportAccessError_(errors) {
  return errors.some((error) => {
    if (!error || typeof error !== "object") {
      return false;
    }
    const message = String(error.message || "").toLowerCase();
    const path = Array.isArray(error.path) ? error.path : [];
    const isReportPath = path.indexOf("report") >= 0;
    return isReportPath && (
      message.indexOf("permission to view this report") >= 0
      || message.indexOf("permission to view the report") >= 0
      || message.indexOf("report does not exist") >= 0
      || message.indexOf("not found") >= 0
      || message.indexOf("private") >= 0
      || message.indexOf("deleted") >= 0
    );
  });
}

function output_(payload, callback) {
  const jsonText = JSON.stringify(payload);
  if (callback) {
    return ContentService
      .createTextOutput(`${callback}(${jsonText});`)
      .setMimeType(ContentService.MimeType.JAVASCRIPT);
  }
  return ContentService
    .createTextOutput(jsonText)
    .setMimeType(ContentService.MimeType.JSON);
}

function normalizeJsonpCallback_(callback) {
  const text = String(callback || "").trim();
  if (!text) {
    return "";
  }
  if (!JSONP_CALLBACK_PATTERN.test(text)) {
    throw new PublicStatusError_("invalid_callback", "JSONP callback 名稱不合法。", null);
  }
  return text;
}

function normalizeAction_(action) {
  const text = String(action || "status").trim().toLowerCase();
  return text === "enqueue" ? "enqueue" : "status";
}

function normalizeRequestedAction_(action) {
  const text = String(action || "").trim().toLowerCase();
  if (text === "retry_existing" || text === "review_existing_visibility") {
    return text;
  }
  return "queue_missing";
}

function normalizeSiteStatus_(status) {
  const text = String(status || "").trim().toLowerCase();
  const allowed = ["found", "fight_missing", "hidden", "missing", "invalid", "empty"];
  return allowed.indexOf(text) >= 0 ? text : "missing";
}

function normalizeFightText_(fightText) {
  const text = String(fightText || "").trim();
  if (!text) {
    return "";
  }
  return /^[A-Za-z0-9_-]{1,24}$/.test(text) ? text : "";
}

function normalizeSource_(source) {
  const text = String(source || "faq").trim().toLowerCase();
  return /^[a-z0-9_-]{1,32}$/.test(text) ? text : "faq";
}

function parseJson_(text, message) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new PublicStatusError_("temporary_error", message, null);
  }
}

function buildErrorResult_(error, startedAt) {
  if (error instanceof PublicStatusError_) {
    return {
      ok: false,
      script_version: SCRIPT_VERSION,
      checked_at_iso: new Date().toISOString(),
      elapsed_ms: new Date().getTime() - startedAt.getTime(),
      error_code: error.code,
      http_status: error.httpStatus,
      message: error.publicMessage,
      ...(error.debugMessage ? { debug_message: error.debugMessage } : {}),
    };
  }

  return {
    ok: false,
    script_version: SCRIPT_VERSION,
    checked_at_iso: new Date().toISOString(),
    elapsed_ms: new Date().getTime() - startedAt.getTime(),
    error_code: "unexpected_error",
    http_status: null,
    message: "FFLogs 即時查詢服務發生未預期錯誤，請稍後再試。",
  };
}

class PublicStatusError_ extends Error {
  constructor(code, publicMessage, httpStatus, debugMessage) {
    super(publicMessage);
    this.code = code;
    this.publicMessage = publicMessage;
    this.httpStatus = httpStatus;
    this.debugMessage = debugMessage || "";
  }
}

function buildSafeDebugMessage_(error) {
  if (!error) {
    return "";
  }
  const name = String(error.name || "Error").replace(/[\r\n]+/g, " ").slice(0, 80);
  const message = String(error.message || error).replace(/[\r\n]+/g, " ").slice(0, 240);
  return `${name}: ${message}`;
}
