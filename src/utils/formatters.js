const 台灣整數格式 = new Intl.NumberFormat("zh-TW", {
  maximumFractionDigits: 0,
});

const 台灣完整時間格式 = new Intl.DateTimeFormat("zh-TW", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

const 台灣日期格式 = new Intl.DateTimeFormat("zh-TW", {
  timeZone: "Asia/Taipei",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const 台灣時刻格式 = new Intl.DateTimeFormat("zh-TW", {
  timeZone: "Asia/Taipei",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

export const 分位顯示模式前段 = "topPercent";
export const 分位顯示模式PR = "pr";
export const 預設分位顯示模式 = 分位顯示模式PR;

export function 轉為數字(值) {
  const 數值 = Number(值);
  return Number.isFinite(數值) ? 數值 : null;
}

export function 格式化傷害數值(數值) {
  if (typeof 數值 !== "number" || Number.isNaN(數值)) {
    return "-";
  }

  return 台灣整數格式.format(數值);
}

export function 格式化Active(active) {
  if (typeof active !== "number" || Number.isNaN(active)) {
    return "-";
  }

  return `${active.toFixed(2)}%`;
}

export function 格式化Gcd覆蓋率(gcdCoverage) {
  const 數值 = typeof gcdCoverage === "number" ? 轉為數字(gcdCoverage) : 轉為數字(gcdCoverage?.percent);
  return 數值 === null ? "-" : `${數值.toFixed(2)}%`;
}

export function 格式化整數(數值) {
  const 數字 = 轉為數字(數值);
  return 數字 === null ? "-" : 台灣整數格式.format(數字);
}

export function 格式化帶號整數(數值) {
  const 數字 = 轉為數字(數值);
  if (數字 === null) {
    return "-";
  }

  const 格式化數字 = 台灣整數格式.format(Math.abs(數字));
  if (數字 > 0) {
    return `+${格式化數字}`;
  }
  if (數字 < 0) {
    return `-${格式化數字}`;
  }
  return "0";
}

export function 格式化百分比(數值) {
  const 數字 = 轉為數字(數值);
  return 數字 === null ? "-" : `${數字.toFixed(2)}%`;
}

function 夾住百分比(數值, 下限 = 0, 上限 = 100) {
  return Math.min(上限, Math.max(下限, 數值));
}

function 轉為分位數字(值) {
  if (值 === null || 值 === undefined || 值 === "") {
    return null;
  }

  return 轉為數字(值);
}

export function 正規化分位顯示模式(模式) {
  if (模式 === 分位顯示模式前段 || 模式 === 分位顯示模式PR) {
    return 模式;
  }

  return 預設分位顯示模式;
}

export function 計算前段百分位(排名, 總數) {
  const 排名數值 = 轉為分位數字(排名);
  const 總數值 = 轉為分位數字(總數);
  if (排名數值 === null || 總數值 === null || 總數值 <= 0) {
    return null;
  }

  return 夾住百分比((排名數值 / 總數值) * 100, 0.01, 100);
}

export function 格式化前段百分位(排名, 總數) {
  const 百分位 = 計算前段百分位(排名, 總數);
  if (百分位 === null) {
    return "-";
  }

  return `前 ${百分位.toFixed(2)}%`;
}

export function 計算PR值(來源) {
  if (來源 === null || 來源 === undefined || 來源 === "") {
    return null;
  }

  if (typeof 來源 !== "object") {
    const 數值 = 轉為分位數字(來源);
    return 數值 === null ? null : 夾住百分比(數值);
  }

  const 既有PR = 轉為分位數字(來源.score_percentile);
  if (既有PR !== null) {
    return 夾住百分比(既有PR);
  }

  const 排名數值 = 轉為分位數字(來源.rank);
  const 總數值 = 轉為分位數字(來源.sample_count);
  if (排名數值 === null || 總數值 === null || 總數值 <= 0) {
    return null;
  }

  return 夾住百分比(((總數值 - 排名數值 + 1) / 總數值) * 100);
}

export function 計算排名PR值(排名, 總數) {
  return 計算PR值({ rank: 排名, sample_count: 總數 });
}

export function 格式化PR值(數值) {
  const PR值 = 計算PR值(數值);
  return PR值 === null ? "-" : `PR ${Math.round(PR值)}`;
}

export function 取得PR色彩類別(數值) {
  const PR值 = 計算PR值(數值);
  if (PR值 === null) {
    return "";
  }

  const 顯示PR = Math.round(PR值);
  if (顯示PR >= 100) {
    return "分位PR100";
  }
  if (顯示PR >= 99) {
    return "分位PR99";
  }
  if (顯示PR >= 95) {
    return "分位PR95";
  }
  if (顯示PR >= 75) {
    return "分位PR75";
  }
  if (顯示PR >= 50) {
    return "分位PR50";
  }
  if (顯示PR >= 25) {
    return "分位PR25";
  }
  return "分位PR0";
}

export function 格式化排名分位(排名, 總數, 顯示模式 = 預設分位顯示模式) {
  if (正規化分位顯示模式(顯示模式) === 分位顯示模式PR) {
    return 格式化PR值(計算排名PR值(排名, 總數));
  }

  return 格式化前段百分位(排名, 總數);
}

export function 格式化同職分位(performance, 顯示模式 = 預設分位顯示模式) {
  if (正規化分位顯示模式(顯示模式) === 分位顯示模式PR) {
    return 格式化PR值(performance);
  }

  const 既有前段百分位 = 轉為數字(performance?.top_percent);
  if (既有前段百分位 !== null) {
    return `前 ${夾住百分比(既有前段百分位, 0.01, 100).toFixed(2)}%`;
  }

  return 格式化前段百分位(performance?.rank, performance?.sample_count);
}

export function 格式化通關時間(秒數) {
  if (typeof 秒數 !== "number" || Number.isNaN(秒數)) {
    return "-";
  }

  const 分鐘 = Math.floor(秒數 / 60);
  const 秒 = Math.floor(秒數 % 60);
  return `${分鐘}:${String(秒).padStart(2, "0")}`;
}

export function 解析紀錄日期(iso時間) {
  if (!iso時間) {
    return null;
  }

  const 日期 = new Date(iso時間);
  return Number.isNaN(日期.getTime()) ? null : 日期;
}

export function 格式化紀錄時間(iso時間) {
  const 日期 = 解析紀錄日期(iso時間);
  return 日期 ? 台灣完整時間格式.format(日期) : "-";
}

export function 格式化紀錄日期(iso時間) {
  const 日期 = 解析紀錄日期(iso時間);
  return 日期 ? 台灣日期格式.format(日期) : "-";
}

export function 格式化紀錄時刻(iso時間) {
  const 日期 = 解析紀錄日期(iso時間);
  return 日期 ? 台灣時刻格式.format(日期) : "";
}

export function 格式化排名(排名) {
  const 排名數值 = 轉為數字(排名);
  return 排名數值 === null || 排名數值 <= 0 ? "-" : `#${排名數值}`;
}

export function 計算Active百分比(activeTimeMs, 通關秒數) {
  const activeTime = 轉為數字(activeTimeMs);
  if (activeTime === null || typeof 通關秒數 !== "number" || 通關秒數 <= 0) {
    return null;
  }

  // FFLogs 的 activeTime 以毫秒記錄，通關時間在本專案資料中以秒儲存；
  // 這裡統一轉成百分比，避免各頁重複處理單位轉換。
  return Number(((activeTime / (通關秒數 * 1000)) * 100).toFixed(2));
}
