import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { 建置追趕推測 } from "./version_progress_forecast.mjs";

const 設定網址 = new URL("../config/version_progress.json", import.meta.url);
const 模組名稱 = "virtual:version-progress";

/** 日期代表公告的當地日曆日；轉 UTC 日序只為避免時區與日光節約影響天數。 */
export function 日序(日期) {
  if (typeof 日期 !== "string" || !/^\d{4}-\d{2}-\d{2}$/.test(日期)) {
    throw new Error(`版本日期格式錯誤：${日期}`);
  }
  const 毫秒 = Date.parse(`${日期}T00:00:00Z`);
  if (!Number.isFinite(毫秒) || new Date(毫秒).toISOString().slice(0, 10) !== 日期) {
    throw new Error(`版本日期不存在：${日期}`);
  }
  return 毫秒 / 86400000;
}

/**
 * @typedef {{patch: string, major: boolean, title: string, international: string,
 * international_source?: string, tc: string|null, tc_source?: string,
 * merged_into?: string, tc_version_omitted?: boolean, note?: string,
 * tc_forecast_skip?: boolean, tc_plan?: {date:string, attribution:string, source?:string},
 * note_sources?: {label: string, source: string}[]}} 版本設定
 * @param {{schema_version: number, verified_through: string, launch_date: string,
 * early_access_date: string, sources: Record<string, string>, patches: 版本設定[],
 * international_plans?: {patch: string, title: string, month: string, source: string}[],
 * international_history?: {source:string, patches:{patch:string, date:string}[]},
 * forecast_policy?: {tc_main_cycle_days:number, tc_update_weekday:number, tc_skipped_patches?:string[],
 * shared_minor_intervals?: {from_expansion:number, steps:{from:string, to:string, days:number}[]}}}} 設定
 *
 * 版本是有序的名稱，不是小數。清單順序由維護者依官方發布順序明確維護；
 * 節點差只描述版本標籤的距離，不能視為內容完成率或待更新次數。
 * 統計、發布日期差與圖表日序在 Node 建置；畫面依持續中標記補經過天數。
 */
export function 建置版本進度(設定) {
  if (設定.schema_version !== 1) throw new Error("不支援的版本進度設定格式");
  const 推測規則 = 設定.forecast_policy;
  if (推測規則 !== undefined && (!推測規則 || !Number.isSafeInteger(推測規則.tc_main_cycle_days)
    || 推測規則.tc_main_cycle_days < 7 || !Number.isInteger(推測規則.tc_update_weekday)
    || 推測規則.tc_update_weekday < 0 || 推測規則.tc_update_weekday > 6)) {
    throw new Error("推測規則須包含至少 7 天的整數主版週期，以及 0 至 6 的更新星期");
  }
  const 情境跳版 = 推測規則?.tc_skipped_patches ?? [];
  if (推測規則?.tc_skipped_patches === null || !Array.isArray(情境跳版)
    || 情境跳版.some((版本) => typeof 版本 !== "string" || !/^[1-9]\d*\.[0-5]\d$/.test(版本))
    || new Set(情境跳版).size !== 情境跳版.length) {
    throw new Error("推測跳版清單須為不重複的小版本字串");
  }
  const 固定間隔 = 推測規則?.shared_minor_intervals;
  if (固定間隔 !== undefined && (!固定間隔 || !Number.isSafeInteger(固定間隔.from_expansion)
    || 固定間隔.from_expansion < 1 || !Array.isArray(固定間隔.steps) || !固定間隔.steps.length
    || 固定間隔.steps.some((段) => !段 || typeof 段.from !== "string" || typeof 段.to !== "string"
      || !/^[0-5]\d?$/.test(段.from) || !/^[0-5]\d$/.test(段.to) || 段.from[0] !== 段.to[0]
      || Number(段.from) >= Number(段.to) || !Number.isSafeInteger(段.days) || 段.days < 7 || 段.days % 7 !== 0)
    || new Set(固定間隔.steps.map((段) => 段.from)).size !== 固定間隔.steps.length
    || new Set(固定間隔.steps.map((段) => 段.to)).size !== 固定間隔.steps.length)) {
    throw new Error("固定小版間隔須指定起始資料片、同主版內不重複且向後的版本段，以及正整週天數");
  }
  const 截止日 = 日序(設定.verified_through);
  const 開服日 = 日序(設定.launch_date);
  if (開服日 > 截止日 || 日序(設定.early_access_date) > 開服日) throw new Error("開服日期順序錯誤");
  const 已見版本 = new Set();
  let 前國際日 = -Infinity;
  let 前繁中日 = -Infinity;
  let 前繁中排程日 = -Infinity;
  const 來源 = (鍵) => {
    const 網址 = 設定.sources[鍵];
    if (!網址 || new URL(網址).protocol !== "https:") throw new Error(`缺少有效版本來源：${鍵}`);
    return 網址;
  };
  const 版本列 = 設定.patches.map((列, 順序) => {
    if (!/^\d+\.\d+$/.test(列.patch) || 已見版本.has(列.patch)) throw new Error("版本鍵值重複或格式錯誤");
    if (typeof 列.major !== "boolean" || !列.title) throw new Error("缺少版本分類或標題");
    已見版本.add(列.patch);
    const 國際日 = 日序(列.international);
    const 繁中日 = 列.tc === null ? null : 日序(列.tc);
    if (國際日 < 前國際日 || (繁中日 !== null && 繁中日 < 前繁中日)) throw new Error("版本發布順序錯誤");
    if (繁中日 !== null && 繁中日 < 開服日) throw new Error("繁中版本早於正式開服");
    if (列.merged_into && (列.tc !== null || !列.note || !列.tc_source)) throw new Error("合併內容必須有說明、來源且不可冒充同版本上線");
    if (列.tc_version_omitted !== undefined && typeof 列.tc_version_omitted !== "boolean") throw new Error("繁中版本號省略標記必須為布林值");
    if (列.tc_version_omitted && !列.merged_into) throw new Error("無獨立繁中版本號必須指定合併版本");
    if (列.tc_forecast_skip !== undefined && typeof 列.tc_forecast_skip !== "boolean") throw new Error("推測跳版標記必須為布林值");
    if (列.tc_forecast_skip && (列.major || 列.tc !== null || 列.tc_plan || 列.tc_version_omitted)) throw new Error("推測跳版只適用未定日期且未確認省略的小版本");
    // 活動預告與已核對發布日分開保存；日期經過也不能自行升格成已上線。
    // 未附連結時必須留下明確歸因，不能借用無關的官方版本頁冒充日期來源。
    let 繁中預定日 = null;
    if (列.tc_plan !== undefined) {
      if (!列.tc_plan || 列.tc !== null || 列.tc_version_omitted || typeof 列.tc_plan.attribution !== "string" || !列.tc_plan.attribution.trim()) throw new Error("繁中預告必須有歸因且與正式日期分開");
      if (列.tc_plan.source !== undefined && (typeof 列.tc_plan.source !== "string" || !列.tc_plan.source.trim())) throw new Error("繁中預告來源鍵值無效");
      繁中預定日 = 日序(列.tc_plan.date);
      if (繁中預定日 < 開服日) throw new Error("繁中預告早於正式開服");
    }
    const 排程日 = 繁中日 ?? 繁中預定日;
    if (排程日 !== null && 排程日 < 前繁中排程日) throw new Error("繁中預告與已知發布日期順序衝突");
    if (排程日 !== null) 前繁中排程日 = 排程日;
    if (列.note !== undefined && (typeof 列.note !== "string" || !列.note.trim())) throw new Error("版本說明必須為非空白文字");
    if (列.note_sources !== undefined && (!列.note || !Array.isArray(列.note_sources) || !列.note_sources.length)) {
      throw new Error("內容對照來源必須附有版本說明與非空白來源清單");
    }
    // 內容可能來自較後面的版本或回溯公告，與發布日期的來源分開保存，避免誤改時間軸。
    const 說明連結 = (列.note_sources || []).map((項) => {
      if (!項 || typeof 項.label !== "string" || !項.label.trim() || typeof 項.source !== "string") {
        throw new Error("內容對照來源缺少標籤或來源鍵值");
      }
      return { label: 項.label, url: 來源(項.source) };
    });
    前國際日 = 國際日;
    if (繁中日 !== null) 前繁中日 = 繁中日;
    return {
      ...列, order: 順序, international_day: 國際日, tc_day: 繁中日,
      tc_plan_day: 繁中預定日, tc_plan_url: 列.tc_plan?.source ? 來源(列.tc_plan.source) : null,
      international_url: 來源(列.international_source || "international"),
      tc_url: 列.tc_source ? 來源(列.tc_source) : null,
      note_links: 說明連結,
      international_released: 國際日 <= 截止日,
      tc_released: 繁中日 !== null && 繁中日 <= 截止日,
      // 未來已公告日期也不納入「已上線間隔」，避免未到日期就提升目前版本。
      lag_days: 繁中日 !== null && 繁中日 <= 截止日 && 國際日 <= 截止日 ? 繁中日 - 國際日 : null,
    };
  });
  for (const 列 of 版本列) {
    // 尚未產生的版本可在情境設定中指定；日後補入正式列時，須先解決與公告的衝突。
    if (情境跳版.includes(列.patch) && (列.major || 列.tc !== null || 列.tc_plan || 列.tc_version_omitted)) {
      throw new Error("推測跳版只適用未定日期且未確認省略的小版本");
    }
    if (列.tc !== null && !列.tc_url) throw new Error("繁中上線日期必須有來源");
    if (列.merged_into && !版本列.some((目標) => 目標.patch === 列.merged_into && 目標.tc_released)) {
      throw new Error("合併內容必須對應已發布的繁中版本");
    }
    // 小版內容也可能提前併入主版（例如 7.21 → 7.2）；目標須已發布且位於被省略版之前。
    if (列.tc_version_omitted && (列.major || !版本列.some((目標) => 目標.patch === 列.merged_into && 目標.order < 列.order))) {
      throw new Error("僅可省略已合併至先前繁中版本的小版本號");
    }
  }
  const 繁中目前 = 版本列.findLast((列) => 列.tc_released);
  const 國際目前 = 版本列.findLast((列) => 列.international_released);
  if (!繁中目前 || !國際目前 || !版本列.some((列) => 列.tc_day === 開服日)) throw new Error("缺少已發布版本或開服節點");
  const 可比較 = 版本列.filter((列) => 列.lag_days !== null);
  // 僅公告月份的未來資料片另存，不虛構正式上線日，也不參與歷史樣本。
  if (設定.international_plans !== undefined && !Array.isArray(設定.international_plans)) throw new Error("國際服預定時程必須為清單");
  let 前預定日 = 前國際日;
  const 國際預定 = (設定.international_plans || []).map((計畫) => {
    if (!/^\d+\.0$/.test(計畫.patch) || 已見版本.has(計畫.patch) || !計畫.title || !/^\d{4}-(0[1-9]|1[0-2])$/.test(計畫.month)) throw new Error("國際服預定版本或月份無效");
    const 開始日 = 日序(`${計畫.month}-01`);
    if (開始日 <= 前預定日) throw new Error("預定時程必須依序位於已收錄版本之後");
    已見版本.add(計畫.patch);
    前預定日 = 開始日;
    const [年, 月] = 計畫.month.split("-").map(Number);
    return { ...計畫, url: 來源(計畫.source), start_day: 開始日, end_day: Date.UTC(年, 月, 0) / 86400000 };
  });
  // 摘要比較繁中最近兩次獨立更新；合併版與未上線公告不算前版，且不受主版篩選影響。
  const 上次比較 = 可比較.at(-2) ?? null;
  const 本次比較 = 可比較.at(-1);
  // 舊資料片只補充推測樣本，不放入繁中開服後的表格、節點差或實際時長。
  const 歷史 = 設定.international_history;
  if (歷史 !== undefined && (!歷史 || !Array.isArray(歷史.patches) || !歷史.patches.length)) throw new Error("國際歷史樣本必須為非空白清單");
  let 前歷史日 = -Infinity;
  const 國際歷史 = 歷史 ? { url: 來源(歷史.source), patches: 歷史.patches.map((列) => {
    if (!列 || !/^\d+\.[0-5]\d?$/.test(列.patch) || 已見版本.has(列.patch)) throw new Error("國際歷史版本鍵值重複或格式錯誤");
    const day = 日序(列.date);
    if (day <= 前歷史日 || day >= 版本列[0].international_day || day > 截止日) throw new Error("國際歷史日期必須依序早於已收錄版本與核對日");
    已見版本.add(列.patch); 前歷史日 = day;
    return { patch: 列.patch, day };
  }) } : undefined;
  const 推測 = 建置追趕推測(版本列, 國際預定, 開服日, 截止日, 推測規則, 國際歷史);
  const 視圖 = Object.fromEntries(["all", "major"].map((範圍) => {
    /** @type {{days: number, ongoing: boolean}|null} */
    const 空白時長 = null;
    const 列表 = 版本列.filter((列) => 範圍 === "all" || 列.major).map((列) => ({
      ...列, international_duration: 空白時長, tc_duration: 空白時長,
    }));
    // 各服只使用自己已上線的版本；沒有獨立繁中日期的合併版不能截斷前版時長。
    // 先依顯示範圍計算，主要版本可涵蓋整個主版週期；圖表省略的國際小版仍是更新切點。
    for (const 地區 of ["international", "tc"]) {
      const 已上線 = 列表.filter((列) => 列[`${地區}_released`]);
      已上線.forEach((列, i) => {
        const 下一版 = 已上線[i + 1];
        列[`${地區}_duration`] = {
          days: (下一版?.[`${地區}_day`] ?? 截止日) - 列[`${地區}_day`],
          ongoing: !下一版,
        };
      });
    }
    const 已發布階段 = 列表.filter((列) => 列.international_released || 列.tc_released);
    // 7.16、7.18、7.21 無獨立繁中版本號，圖表省略其刻度與節點。
    // 對照表、選單及版本標籤差仍使用完整資料；不可由「部分內容合併」推論整版省略。
    const 階段 = 已發布階段.filter((列) => !列.tc_version_omitted);
    const 時間線 = (地區) => {
      const 已發布 = 階段.filter((列) => 列[`${地區}_released`]);
      const 起點 = 已發布.findLast((列) => 列[`${地區}_day`] <= 開服日);
      if (!起點) throw new Error("缺少時間軸起始版本");
      return [起點, ...已發布.filter((列) => 列[`${地區}_day`] > 開服日)].map((列) => ({
        patch: 列.patch, date: 列[地區], day: Math.max(開服日, 列[`${地區}_day`]),
        stage: 階段.indexOf(列), carried: 列[`${地區}_day`] < 開服日,
      }));
    };
    return [範圍, {
      forecast: 推測[範圍],
      rows: 列表, stages: 階段.map((列) => 列.patch),
      gap_count: 已發布階段.filter((列) => 列.order > 繁中目前.order && 列.order <= 國際目前.order).length,
      tc: 時間線("tc"), international: 時間線("international"),
    }];
  }));
  // 用明確的主要版本標記切分連續區間，不用字串前綴或小數推測歸屬。
  // 分組保留全部小版（包含圖表省略的版本），總時長直接沿用主版週期，避免重複加總。
  for (const 子視圖 of Object.values(視圖)) {
    子視圖.groups = 視圖.major.rows.map((主版, i) => ({
      patch: 主版.patch,
      rows: 子視圖.rows.filter((列) => 列.order >= 主版.order && 列.order < (視圖.major.rows[i + 1]?.order ?? Infinity)),
      international_duration: 主版.international_duration,
      tc_duration: 主版.tc_duration,
    }));
  }
  return {
    verified_through: 設定.verified_through, launch_date: 設定.launch_date,
    early_access_date: 設定.early_access_date, start_day: 開服日, end_day: 截止日,
    elapsed_days: 截止日 - 開服日, current_tc: 繁中目前.patch, current_international: 國際目前.patch,
    previous_comparable: 上次比較, latest_comparable: 本次比較,
    lag_reduction: 上次比較 ? 上次比較.lag_days - 本次比較.lag_days : null,
    international_plans: 國際預定, views: 視圖,
  };
}

export function 讀取版本進度() {
  return 建置版本進度(JSON.parse(readFileSync(設定網址, "utf8")));
}

/** Vite 在 Node 端產生唯讀 JSON 模組，不寫入受管理的歷史資料或 public/data 快照。 */
export function 版本進度資料插件() {
  return {
    name: "version-progress-data",
    resolveId(id) { return id === 模組名稱 ? `\0${模組名稱}` : null; },
    load(id) {
      if (id !== `\0${模組名稱}`) return null;
      this.addWatchFile(fileURLToPath(設定網址));
      return `export default ${JSON.stringify(讀取版本進度())};`;
    },
    handleHotUpdate({ file, server }) {
      // Vite 事件路徑使用正斜線，Windows 的 fileURLToPath 則使用反斜線。
      if (file.replaceAll("\\", "/") === fileURLToPath(設定網址).replaceAll("\\", "/")) {
        const 模組 = server.moduleGraph.getModuleById(`\0${模組名稱}`);
        if (模組) server.moduleGraph.invalidateModule(模組);
        server.ws.send({ type: "full-reload" });
        return [];
      }
    },
  };
}
