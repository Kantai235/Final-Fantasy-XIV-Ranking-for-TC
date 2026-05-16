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

export function 格式化前段百分位(排名, 總數) {
  const 排名數值 = 轉為數字(排名);
  const 總數值 = 轉為數字(總數);
  if (排名數值 === null || 總數值 === null || 總數值 <= 0) {
    return "-";
  }

  return `前 ${Math.min(100, Math.max(0.01, (排名數值 / 總數值) * 100)).toFixed(2)}%`;
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
