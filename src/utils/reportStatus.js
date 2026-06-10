const reportCodePattern = /^[A-Za-z0-9]{8,32}$/;

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

function 讀取Cron分鐘(cronText) {
  const minuteText = String(cronText || "").trim().split(/\s+/)[0];
  const minute = Number.parseInt(minuteText, 10);
  return Number.isInteger(minute) && minute >= 0 && minute <= 59 ? minute : 17;
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

export function 取得下一輪排程時間(目前時間 = new Date(), 分鐘 = 17) {
  const now = new Date(目前時間);
  const next = new Date(now);
  const normalizedMinute = Number.isInteger(分鐘) && 分鐘 >= 0 && 分鐘 <= 59 ? 分鐘 : 17;
  next.setUTCMinutes(normalizedMinute, 0, 0);
  if (next.getTime() <= now.getTime()) {
    next.setUTCHours(next.getUTCHours() + 1);
  }
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
  const nextRun = 取得下一輪排程時間(目前時間, 讀取Cron分鐘(schedule.workflow_cron_utc));
  const delayedStartHours = Number(schedule.delayed_scan_recent_gap_hours) || 24;
  const delayedLookbackHours = Number(schedule.delayed_scan_lookback_hours) || 72;
  const historyWindowHours = Number(schedule.history_scan_window_hours) || 168;

  return {
    next_run_at_iso: nextRun.toISOString(),
    next_run_wait_text: 格式化相對等待時間(nextRun, 目前時間),
    notes: [
      `如果這是剛上傳且已公開的通關紀錄，通常下一次每小時排程後就會被掃到；下一輪約 ${格式化相對等待時間(nextRun, 目前時間)}。`,
      `如果 FFLogs 還沒匯出通關 fight，近期重查窗會在最近 ${Number(schedule.no_clear_retry_hours) || 24} 小時內反覆補查。`,
      `如果是上傳時間落在 ${delayedStartHours}-${delayedLookbackHours} 小時前、後來才公開或延後出現在 reports 列表的紀錄，延遲掃描會嘗試補抓。`,
      `更舊的歷史戰鬥會進入歷史補查輪巡；目前每輪推進 ${historyWindowHours} 小時視窗，實際等待時間取決於候選量與 FFLogs 回應狀態。`,
      "如果 report 是 Private、已刪除、不含繁中服玩家、不屬於目前支援副本，或沒有可採計通關場次，就不會出現在公開排行榜。",
    ],
  };
}
