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
