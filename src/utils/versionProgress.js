/** 只正規化顯示狀態；版本順序與統計一律使用 Node 建置後的靜態結果。 */
export function 正規化版本進度選取(資料, 狀態 = {}) {
  const patchScope = 狀態.patchScope === "major" ? "major" : "all";
  const guess = 狀態.guess === true || 狀態.guess === "1";
  const 列表 = (guess && 資料.views[patchScope].forecast.rows) || 資料.views[patchScope].rows;
  const 全部列 = (guess && 資料.views.all.forecast.rows) || 資料.views.all.rows;
  const 要求版本 = String(狀態.patch || 資料.current_tc);
  // 切到主要版本時，7.11 等小版本回到其所屬主要版本；不把版本字串轉成浮點數。
  const 主要版本 = 全部列.findLast((列) =>
    列.major && 列.order <= (全部列.find((項) => 項.patch === 要求版本)?.order ?? -1));
  const patch = 列表.find((列) => 列.patch === 要求版本)?.patch
    || 列表.find((列) => 列.patch === 主要版本?.patch)?.patch || 列表.findLast((列) => 列.tc_released)?.patch || 列表[0].patch;
  return { patchScope, patch, guess };
}

export function 格式化版本日期(日期) {
  return 日期 ? 日期.replaceAll("-", "/") : "—";
}

/** 使用台灣日曆日對齊建置層的 UTC 日序，不受瀏覽者所在地時區影響。 */
export function 取得台灣當日日序(目前時間 = Date.now()) {
  return Math.floor((目前時間 + 8 * 60 * 60 * 1000) / 86400000);
}

/**
 * 建置層提供核對日當下的時長與是否持續中；畫面只補經過的日曆天數。
 * 不重新判定版序或發布狀態，也不把推測週期改成已經過的時間。
 * @param {{days:number, ongoing:boolean, estimated?:boolean, through_horizon?:boolean}|null} 時長
 * @param {number} 核對日
 * @param {number} 目前日
 * @returns {number|null}
 */
export function 取得版本顯示時長(時長, 核對日, 目前日) {
  if (!時長) return null;
  return 時長.ongoing && !時長.estimated && !時長.through_horizon
    ? Math.max(0, 時長.days + 目前日 - 核對日) : 時長.days;
}

/**
 * 版本列比較固定的兩服發布日；繁中仍在遊玩此版本，不代表發布間隔仍在增加。
 * 推測列同樣沿用模型日期差，只補「約」字；無獨立日期時不虛構間隔。
 * @param {{lag_days:number|null, lag_estimated?:boolean}} 列
 * @returns {string}
 */
export function 格式化版本間隔(列) {
  return 列.lag_days !== null ? `${列.lag_estimated ? '約 ' : ''}${列.lag_days} 天` : '—';
}

/**
 * 只描述今天相對於既有日期的位置，不把預告或推測自動升格成實際上線。
 * 月份公告使用建置層提供的月底；不能拿月中錨點當確切更新日。
 * @param {number|null|undefined} 目標日
 * @param {number} 目前日
 * @param {'planned'|'announced'|'estimated'|'month'} 種類
 * @param {boolean} 倒數 未來倒數只放在下一版，避免每個遙遠版本都重複增加提示。
 * @returns {{text:string, overdue:boolean}|null}
 */
export function 取得版本日期提示(目標日, 目前日, 種類, 倒數 = false) {
  if (!Number.isFinite(目標日)) return null;
  const 天數 = 目標日 - 目前日;
  if (種類 === 'month') return 天數 < 0 ? { text: '預定月份已過，待核對實際更新。', overdue: true } : null;
  if (天數 > 0) return 倒數 ? { text: `還有 ${天數} 天`, overdue: false } : null;
  if (天數 === 0) return { text: `${種類 === 'planned' ? '預定' : 種類 === 'announced' ? '公告於' : '推測'}今日更新，實際更新待核對。`, overdue: false };
  return { text: `${種類 === 'planned' ? '預告' : 種類 === 'announced' ? '公告' : '推測'}日期已過，${種類 === 'estimated' ? '待重新核對排程。' : '待核對實際更新。'}`, overdue: true };
}

/**
 * 追上日期由模型固定，只有剩餘天數隨今天減少；超過日期時提示過期，不宣稱已追上。
 * @param {{day:number, already?:boolean}|null|undefined} 交點
 * @param {number} 目前日
 * @returns {{text:string, overdue:boolean}|null}
 */
export function 取得版本追上提示(交點, 目前日) {
  if (!交點 || 交點.already || !Number.isFinite(交點.day)) return null;
  const 天數 = 交點.day - 目前日;
  return { text: 天數 > 0 ? `距今天約 ${天數} 天`
    : 天數 === 0 ? '推測於今日追上，實際進度待核對。'
      : `原推測追上日期已過 ${-天數} 天，待重新核對。`, overdue: 天數 < 0 };
}

/**
 * 遙遠的同步候選只呈現可能性，模型日期仍供座標及前版時長計算。
 * 後續若已有正式日期或活動預告，必須回到一般日期顯示。
 * @param {{tc_sync_candidate?: boolean, international?: string|null, tc?: string|null, tc_plan?: object|null}|undefined} 列
 */
export function 僅顯示版本同步(列) {
  return Boolean(列?.tc_sync_candidate && !列.international && !列.tc && !列.tc_plan);
}

export function 格式化版本星期(星期) {
  return Number.isInteger(星期) && 星期 >= 0 && 星期 <= 6 ? `星期${'日一二三四五六'[星期]}` : '';
}
