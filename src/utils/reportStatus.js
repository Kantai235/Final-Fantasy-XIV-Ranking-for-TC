const reportCodePattern = /^[A-Za-z0-9]{8,32}$/;
const 預設排程分鐘列表 = Object.freeze([17, 47]);
const 預設Fflogs即時狀態查詢網址 = "https://script.google.com/macros/s/AKfycbw_GPuIIrR84Bse1uCiXz1BM2CzgtzvXqhn8dmbbgIQLs-6Etjw6L2BXxerAx5vcXg-zQ/exec";
const AppsScriptJsonpCallbackRoot = "__ffxivTcFflogsReportStatusCallbacks";
const AppsScriptJsonp逾時Ms = 12000;
let AppsScriptJsonp序號 = 0;

function 清理ReportCode(片段) {
  const 文字 = String(片段 || "").trim().replace(/^a:/i, "");
  return reportCodePattern.test(文字) ? 文字 : "";
}

function 讀取Fight參數(網址) {
  const 查詢Fight = String(網址.searchParams.get("fight") || "").trim();
  if (查詢Fight) {
    return 查詢Fight;
  }

  const hash = String(網址.hash || "").replace(/^#/, "");
  if (!hash) {
    return "";
  }

  const hash參數 = new URLSearchParams(hash);
  return String(hash參數.get("fight") || "").trim();
}

function 是Fflogs主機(hostname) {
  const 主機 = String(hostname || "").toLocaleLowerCase("en-US");
  return 主機 === "fflogs.com" || 主機.endsWith(".fflogs.com");
}

function 讀取ImportMetaEnv值(key) {
  try {
    return String(import.meta.env?.[key] || "").trim();
  } catch (error) {
    return "";
  }
}

function 建立Jsonp網址(endpoint, params, callbackName) {
  const 網址 = new URL(endpoint);
  Object.entries(params || {}).forEach(([key, value]) => {
    const text = String(value ?? "").trim();
    if (text) {
      網址.searchParams.set(key, text);
    }
  });
  網址.searchParams.set("callback", callbackName);
  return 網址.href;
}

function 取得全域物件() {
  if (typeof window !== "undefined") {
    return window;
  }
  if (typeof globalThis !== "undefined") {
    return globalThis;
  }
  return null;
}

function 建立分鐘數列(起點, 終點, 間隔 = 1) {
  const 分鐘列表 = [];
  const safeStep = Number.isInteger(間隔) && 間隔 > 0 ? 間隔 : 1;
  for (let minute = 起點; minute <= 終點; minute += safeStep) {
    分鐘列表.push(minute);
  }
  return 分鐘列表;
}

function 解析Cron分鐘片段(片段文字) {
  const 片段 = String(片段文字 || "").trim();
  if (!片段) {
    return [];
  }

  const stepMatch = 片段.match(/^(.+)\/(\d+)$/);
  const baseText = stepMatch ? stepMatch[1] : 片段;
  const step = stepMatch ? Number.parseInt(stepMatch[2], 10) : 1;
  if (!Number.isInteger(step) || step <= 0) {
    return [];
  }

  if (baseText === "*") {
    return 建立分鐘數列(0, 59, step);
  }

  const rangeMatch = baseText.match(/^(\d{1,2})-(\d{1,2})$/);
  if (rangeMatch) {
    const start = Number.parseInt(rangeMatch[1], 10);
    const end = Number.parseInt(rangeMatch[2], 10);
    if (start >= 0 && end <= 59 && start <= end) {
      return 建立分鐘數列(start, end, step);
    }
    return [];
  }

  const singleMinuteMatch = baseText.match(/^\d{1,2}$/);
  const minute = singleMinuteMatch ? Number.parseInt(baseText, 10) : null;
  if (Number.isInteger(minute) && minute >= 0 && minute <= 59) {
    return stepMatch ? 建立分鐘數列(minute, 59, step) : [minute];
  }

  return [];
}

function 正規化排程分鐘列表(分鐘列表) {
  const 原始列表 = Array.isArray(分鐘列表) ? 分鐘列表 : [分鐘列表];
  const minutes = Array.from(
    new Set(
      原始列表
        .map((minute) => Number(minute))
        .filter((minute) => Number.isInteger(minute) && minute >= 0 && minute <= 59),
    ),
  ).sort((a, b) => a - b);
  return minutes.length > 0 ? minutes : [...預設排程分鐘列表];
}

function 讀取Cron分鐘列表(cronText) {
  const minuteText = String(cronText || "").trim().split(/\s+/)[0];
  const minutes = minuteText.split(",").flatMap((片段) => 解析Cron分鐘片段(片段));
  return 正規化排程分鐘列表(minutes);
}

function 解析Fight文字(fightText) {
  const 數字 = Number.parseInt(fightText, 10);
  return Number.isFinite(數字) && 數字 > 0 && String(數字) === String(fightText).trim()
    ? 數字
    : null;
}

function 從路徑讀取ReportCode(網址) {
  const 片段列表 = String(網址.pathname || "").split("/").filter(Boolean);
  const reportIndex = 片段列表.findIndex((片段) => 片段.toLocaleLowerCase("en-US") === "reports");
  if (reportIndex < 0) {
    return "";
  }

  return 清理ReportCode(片段列表[reportIndex + 1]);
}

export function 解析Fflogs網址(輸入) {
  const 原始文字 = String(輸入 || "").trim();
  if (!原始文字) {
    return {
      valid: false,
      empty: true,
      report_code: "",
      fight_id: null,
      fight_text: "",
      normalized_url: "",
      error: "",
    };
  }

  const 純Code = 清理ReportCode(原始文字);
  if (純Code) {
    return {
      valid: true,
      empty: false,
      report_code: 純Code,
      fight_id: null,
      fight_text: "",
      normalized_url: `https://www.fflogs.com/reports/${純Code}`,
      error: "",
    };
  }

  try {
    const 補齊協定文字 = /^([a-z][a-z\d+.-]*:)?\/\//i.test(原始文字) ? 原始文字 : `https://${原始文字}`;
    const 網址 = new URL(補齊協定文字);
    if (!是Fflogs主機(網址.hostname)) {
      throw new Error("請貼上 fflogs.com 的 report 網址");
    }

    const reportCode = 從路徑讀取ReportCode(網址);
    if (!reportCode) {
      throw new Error("網址中找不到 FFLogs report code");
    }

    const fightText = 讀取Fight參數(網址);
    const fightId = 解析Fight文字(fightText);
    const normalizedUrl = new URL(`https://www.fflogs.com/reports/${reportCode}`);
    if (fightText) {
      normalizedUrl.searchParams.set("fight", fightText);
    }

    return {
      valid: true,
      empty: false,
      report_code: reportCode,
      fight_id: fightId,
      fight_text: fightText,
      normalized_url: normalizedUrl.href,
      error: "",
    };
  } catch (error) {
    return {
      valid: false,
      empty: false,
      report_code: "",
      fight_id: null,
      fight_text: "",
      normalized_url: "",
      error: error instanceof Error ? error.message : "無法解析 FFLogs 網址",
    };
  }
}

export function 取得Fflogs即時狀態查詢網址() {
  return 讀取ImportMetaEnv值("VITE_FFLOGS_REPORT_STATUS_WEB_APP_URL") || 預設Fflogs即時狀態查詢網址;
}

export function 建立Fflogs即時狀態顯示(payload) {
  if (!payload || typeof payload !== "object") {
    return {
      status: "idle",
      badge: "未查詢",
      title: "尚未查詢 FFLogs 公開狀態",
      description: "按下查詢公開狀態後，會透過站務 Apps Script 確認 FFLogs API 目前是否可讀取這份 report。",
    };
  }

  if (payload.ok !== true) {
    const errorCode = String(payload.error_code || "temporary_error");
    const serverConfigMessage = "即時查詢服務尚未完成設定，請站務確認 Apps Script 的 FFLogs OAuth 憑證。";
    const rateLimitMessage = "FFLogs 目前回傳限流，請稍後再試。站內排行榜仍會依照既有 workflow 排程更新。";
    return {
      status: "error",
      badge: "查詢失敗",
      title: errorCode === "server_config_error" ? "即時查詢服務尚未設定完成" : "暫時無法確認 FFLogs 公開狀態",
      description: errorCode === "server_config_error"
        ? serverConfigMessage
        : errorCode === "rate_limited"
          ? rateLimitMessage
          : payload.message || "Apps Script 或 FFLogs API 暫時無法回應，請稍後再試。",
    };
  }

  const access = String(payload.fflogs_access || "");
  const visibility = String(payload.visibility || "").toLocaleLowerCase("en-US");
  if (access === "accessible") {
    const isPublic = visibility === "public";
    return {
      status: isPublic ? "public" : "accessible",
      badge: isPublic ? "公開" : "可讀",
      title: isPublic ? "FFLogs 目前是公開可讀" : "FFLogs API 目前可讀取這份 report",
      description: "這只代表 report 對站務 Apps Script 可讀；是否收錄仍需等待資料管線確認繁中服玩家、支援副本與通關 fight。",
    };
  }

  if (access === "private_or_deleted") {
    return {
      status: "private",
      badge: "私人或不可讀",
      title: "FFLogs 目前不是公開可讀",
      description: "FFLogs API 無法讀取這份 report。常見原因是 Private、已刪除、不存在，或站務 OAuth client 沒有存取權限。",
    };
  }

  if (access === "archived_inaccessible") {
    return {
      status: "archived",
      badge: "封存不可讀",
      title: "FFLogs 找到 report，但封存狀態不可存取",
      description: "這份 report 目前無法由 API 讀取完整內容，站內 workflow 也可能無法補抓或重新整理。",
    };
  }

  return {
    status: "unknown",
    badge: "未知",
    title: "FFLogs 回傳未知狀態",
    description: payload.message || "即時查詢已完成，但回傳內容不屬於目前支援的狀態，請稍後再試或回報站務。",
  };
}

function 執行FflogsAppsScriptJsonp(params, options = {}) {
  const endpoint = String(options.endpoint || 取得Fflogs即時狀態查詢網址()).trim();
  if (!endpoint) {
    return Promise.reject(new Error("尚未設定 FFLogs 即時狀態查詢 Web App URL。"));
  }

  const 全域物件 = 取得全域物件();
  if (!全域物件 || typeof document === "undefined") {
    return Promise.reject(new Error("即時狀態查詢只能在瀏覽器中執行。"));
  }

  return new Promise((resolve, reject) => {
    const callbackKey = `cb${Date.now()}${AppsScriptJsonp序號++}`;
    const callbackRoot = 全域物件[AppsScriptJsonpCallbackRoot] || {};
    全域物件[AppsScriptJsonpCallbackRoot] = callbackRoot;
    const callbackName = `window.${AppsScriptJsonpCallbackRoot}.${callbackKey}`;
    const script = document.createElement("script");
    let settled = false;

    function cleanup() {
      delete callbackRoot[callbackKey];
      script.remove();
    }

    function settle(handler, value) {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeoutId);
      cleanup();
      handler(value);
    }

    callbackRoot[callbackKey] = (payload) => {
      settle(resolve, payload);
    };

    const timeoutMs = Number(options.timeoutMs) > 0 ? Number(options.timeoutMs) : AppsScriptJsonp逾時Ms;
    const timeoutId = setTimeout(() => {
      settle(reject, new Error("FFLogs Apps Script 查詢逾時，請稍後再試。"));
    }, timeoutMs);

    try {
      script.async = true;
      script.src = 建立Jsonp網址(endpoint, params, callbackName);
      script.onerror = () => {
        settle(reject, new Error("無法載入 FFLogs Apps Script 服務。"));
      };
      (document.head || document.documentElement).appendChild(script);
    } catch (error) {
      settle(reject, error instanceof Error ? error : new Error("FFLogs Apps Script 查詢失敗。"));
    }
  });
}

export function 查詢Fflogs即時狀態(reportCode, options = {}) {
  const code = 清理ReportCode(reportCode);
  if (!code) {
    return Promise.reject(new Error("請先輸入有效的 FFLogs report code。"));
  }
  return 執行FflogsAppsScriptJsonp({ report: code }, options);
}

export function 送出Fflogs待收錄({ reportCode, requestType, siteStatus, fightText } = {}, options = {}) {
  const code = 清理ReportCode(reportCode);
  if (!code) {
    return Promise.reject(new Error("請先輸入有效的 FFLogs report code。"));
  }
  return 執行FflogsAppsScriptJsonp({
    action: "enqueue",
    report: code,
    request_type: requestType || "queue_missing",
    site_status: siteStatus || "missing",
    fight: fightText || "",
    source: "faq",
  }, options);
}

export function 建立報告索引Map(索引資料) {
  const encounterByKey = new Map(
    (索引資料?.encounter_metadata || []).map((encounter) => [encounter.key, encounter]),
  );
  const reports = (索引資料?.reports || []).map((report) => 正規化Report索引列(report, 索引資料, encounterByKey));
  return new Map(reports.filter((report) => report.report_code).map((report) => [report.report_code, report]));
}

function 物件由欄位列(row, columns) {
  if (!Array.isArray(row)) {
    return row && typeof row === "object" ? row : {};
  }

  return Object.fromEntries((columns || []).map((column, index) => [column, row[index]]));
}

function 正規化Encounter列(row, 索引資料, encounterByKey) {
  const encounter = 物件由欄位列(row, 索引資料?.encounter_columns);
  const metadata = encounterByKey.get(encounter.encounter_key) || {};
  return {
    encounter_key: encounter.encounter_key || "",
    encounter_name: encounter.encounter_name || metadata.name || encounter.encounter_key || "",
    encounter_category: encounter.encounter_category || metadata.category || "其他",
    entry_count: Number(encounter.entry_count) || 0,
    hidden_entry_count: Number(encounter.hidden_entry_count) || 0,
    character_count: Number(encounter.character_count) || 0,
    fight_ids: Array.isArray(encounter.fight_ids) ? encounter.fight_ids : [],
    latest_recorded_at_iso: encounter.latest_recorded_at_iso || null,
  };
}

function 正規化Fight列(row, 索引資料) {
  const fight = 物件由欄位列(row, 索引資料?.fight_columns);
  return {
    fight_id: Number(fight.fight_id) || null,
    entry_count: Number(fight.entry_count) || 0,
    hidden_entry_count: Number(fight.hidden_entry_count) || 0,
    character_count: Number(fight.character_count) || 0,
    encounter_keys: Array.isArray(fight.encounter_keys) ? fight.encounter_keys : [],
    latest_recorded_at_iso: fight.latest_recorded_at_iso || null,
  };
}

function 正規化Report索引列(row, 索引資料, encounterByKey) {
  const report = 物件由欄位列(row, 索引資料?.report_columns);
  const reportCode = String(report.report_code || "").trim();
  return {
    report_code: reportCode,
    report_url: report.report_url || (reportCode ? `https://www.fflogs.com/reports/${reportCode}` : ""),
    first_recorded_at_iso: report.first_recorded_at_iso || null,
    latest_recorded_at_iso: report.latest_recorded_at_iso || null,
    entry_count: Number(report.entry_count) || 0,
    hidden_entry_count: Number(report.hidden_entry_count) || 0,
    character_count: Number(report.character_count) || 0,
    encounters: (report.encounters || []).map((encounter) => 正規化Encounter列(encounter, 索引資料, encounterByKey)),
    fights: (report.fights || []).map((fight) => 正規化Fight列(fight, 索引資料)),
  };
}

export function 尋找指定Fight(report, fightId) {
  if (!report || !Number.isFinite(Number(fightId))) {
    return null;
  }

  return (report.fights || []).find((fight) => Number(fight.fight_id) === Number(fightId)) || null;
}

export function 建立Report檢查結果({ 解析結果, 公開索引Map, hidden索引Map }) {
  if (!解析結果 || 解析結果.empty) {
    return { status: "empty", report: null, fight: null };
  }

  if (!解析結果.valid) {
    return { status: "invalid", report: null, fight: null };
  }

  const 公開Report = 公開索引Map.get(解析結果.report_code) || null;
  const hiddenReport = hidden索引Map?.get(解析結果.report_code) || null;
  if (公開Report) {
    const 指定Fight = Number.isFinite(Number(解析結果.fight_id)) ? 尋找指定Fight(公開Report, 解析結果.fight_id) : null;
    if (解析結果.fight_id && !指定Fight) {
      return { status: "fight_missing", report: 公開Report, fight: null };
    }

    return { status: "found", report: 公開Report, fight: 指定Fight };
  }

  if (hiddenReport) {
    const 指定Fight = Number.isFinite(Number(解析結果.fight_id)) ? 尋找指定Fight(hiddenReport, 解析結果.fight_id) : null;
    return { status: "hidden", report: hiddenReport, fight: 指定Fight };
  }

  return { status: "missing", report: null, fight: null };
}

export function 取得下一輪排程時間(目前時間 = new Date(), 分鐘列表 = 預設排程分鐘列表) {
  const now = new Date(目前時間);
  const normalizedMinutes = 正規化排程分鐘列表(分鐘列表);
  for (const minute of normalizedMinutes) {
    const sameHourRun = new Date(now);
    sameHourRun.setUTCMinutes(minute, 0, 0);
    if (sameHourRun.getTime() > now.getTime()) {
      return sameHourRun;
    }
  }

  const next = new Date(now);
  next.setUTCHours(next.getUTCHours() + 1);
  next.setUTCMinutes(normalizedMinutes[0], 0, 0);
  return next;
}

export function 格式化相對等待時間(目標時間, 目前時間 = new Date()) {
  const diffMs = new Date(目標時間).getTime() - new Date(目前時間).getTime();
  if (!Number.isFinite(diffMs) || diffMs <= 0) {
    return "即將開始";
  }

  const totalMinutes = Math.ceil(diffMs / 60000);
  if (totalMinutes < 60) {
    return `約 ${totalMinutes} 分鐘`;
  }

  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  return minutes > 0 ? `約 ${hours} 小時 ${minutes} 分鐘` : `約 ${hours} 小時`;
}

export function 建立未收錄提示(更新狀態, 目前時間 = new Date()) {
  const schedule = 更新狀態?.schedule || {};
  const nextRun = 取得下一輪排程時間(目前時間, 讀取Cron分鐘列表(schedule.workflow_cron_utc));
  const workflowIntervalMinutes = Number(schedule.interval_minutes) || 30;
  const delayedStartHours = Number(schedule.delayed_scan_recent_gap_hours) || 24;
  const delayedLookbackHours = Number(schedule.delayed_scan_lookback_hours) || 72;
  const historyWindowHours = Number(schedule.history_scan_window_hours) || 168;

  return {
    next_run_at_iso: nextRun.toISOString(),
    next_run_wait_text: 格式化相對等待時間(nextRun, 目前時間),
    notes: [
      `如果這是剛上傳且已公開的通關紀錄，通常下一次每 ${workflowIntervalMinutes} 分鐘排程後就會被掃到；下一輪約 ${格式化相對等待時間(nextRun, 目前時間)}。`,
      `如果 FFLogs 還沒匯出通關 fight，近期重查窗會在最近 ${Number(schedule.no_clear_retry_hours) || 24} 小時內反覆補查。`,
      `如果是上傳時間落在 ${delayedStartHours}-${delayedLookbackHours} 小時前、後來才公開或延後出現在 reports 列表的紀錄，延遲掃描會嘗試補抓。`,
      `更舊的歷史戰鬥會進入歷史補查輪巡；目前每輪推進 ${historyWindowHours} 小時視窗，實際等待時間取決於候選量與 FFLogs 回應狀態。`,
      "如果 report 是 Private、已刪除、不含繁中服玩家、不屬於目前支援副本，或沒有可採計通關場次，就不會出現在公開排行榜。",
    ],
  };
}
