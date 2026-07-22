import { computed, onMounted, onUnmounted, ref, watch } from "vue";
import {
  比較職能設定,
  比較職能索引,
  取得比較職能,
  職業Icon路徑,
  職業代碼色彩,
  職業所屬類型,
  職業比較圖色彩,
  職業群組設定,
  職業群組索引,
  職業繁中名稱,
  職業色彩類別,
  職業類型Icon路徑,
  職業類型排序值,
  職業類型色彩,
  顯示職業名稱,
} from "../domain/jobs";
import { 建立副本選單分組 } from "../domain/encounters";
import { 讀取Json } from "../utils/fetchJson";
import {
  解析紀錄日期,
  格式化Active,
  格式化Gcd覆蓋率,
  格式化PR值,
  格式化傷害數值,
  格式化前段百分位,
  格式化同職分位,
  格式化排名分位,
  格式化帶號整數,
  格式化排名,
  格式化整數,
  格式化百分比,
  格式化紀錄日期,
  格式化紀錄時刻,
  格式化紀錄時間,
  格式化通關時間,
  分位顯示模式PR,
  分位顯示模式前段,
  取得PR色彩類別,
  計算Active百分比,
  計算排名PR值,
  正規化分位顯示模式,
  預設分位顯示模式,
  轉為數字,
} from "../utils/formatters";
import {
  全服統計網址,
  副本清單網址,
  使用者索引網址,
  近期動態網址,
  隊伍榜網址,
  伺服器對比網址,
  蜂蜂粉絲榜網址,
  建立公開資料網址,
  建立排行榜表格資料網址,
} from "../utils/publicData";
import { 建立目前分享網址, 正規化分享描述, 預設分享標題 } from "../utils/shareMeta";
import {
  尋找使用者索引條目 as 尋找使用者索引條目於列表,
  格式化使用者搜尋文字,
  取得使用者主要伺服器,
  取得使用者伺服器列表,
  新增玩家搜尋歷史,
  正規化玩家搜尋歷史紀錄,
  玩家搜尋歷史顯示上限,
  解析使用者搜尋輸入,
  解析使用者搜尋目標,
  刪除玩家搜尋歷史,
  清除玩家搜尋歷史,
  讀取玩家搜尋歷史,
  讀取使用者資料Json,
  讀取使用者資料檔,
} from "../utils/userData";
import {
  個人成績代表是否較佳,
  比較個人成績分位顯示排序,
} from "../utils/userProfileSorting";
import { 建立個人成績徽章 } from "../utils/userProfileBadges";
import {
  建立個人成績簡表可選版本,
  建立個人成績簡表群組,
  成績符合個人成績簡表版本,
  預設個人成績簡表版本,
  正規化個人成績簡表版本,
} from "../utils/userProfileClearSummary";
import { 建立職業佔比分組, 取得統計範圍計數, 職業範圍類型 } from "../utils/statsDisplay";
import { 顯示Honey粉絲榜, 顯示Gcd覆蓋率, 顯示作者相關標示 } from "../utils/siteFeatures";
import { 寫入網址狀態, 讀取目前網址狀態 } from "../utils/urlState";
import { 排名色彩類別, 比例條樣式, 熱力格樣式, 趨勢點樣式, 隱藏載入失敗圖片 } from "../utils/viewHelpers";
import {
  作者角色名稱,
  作者說明文字,
  傷害比較指標選項,
  版本紀錄範圍選項,
  副本分類順序,
  排序欄位標籤,
  排序預設方向,
  預設伺服器拆分模式,
  預設副本鍵值,
  預設排序方向,
  預設排序欄位,
  預設比較副本鍵值,
  預設比較職能,
  預設版本紀錄範圍,
  預設統計傷害指標,
  預設統計副本鍵值,
  預設統計職業範圍,
  預設職業分析範圍,
  預設隊伍榜副本鍵值,
} from "./rankingApp/defaults";
import { useRankingData } from "./rankingApp/useRankingData";
export { injectRankingApp, rankingAppKey } from "./rankingApp/context";
import { useTheme } from "./useTheme";

const 蜂蜂背景音樂偏好儲存鍵 = "ffxiv-tc-rankings-honey-bgm";
const 蜂蜂背景音樂影片Id = "07V_j5a9kHw";
const 蜂蜂背景音樂嵌入網址 = `https://www.youtube.com/embed/${蜂蜂背景音樂影片Id}`;
const 分位顯示偏好儲存鍵 = "ffxiv-tc-rankings-percentile-display-mode";
const 說明提示顯示偏好儲存鍵 = "ffxiv-tc-rankings-show-help-tooltips";
const 分位顯示模式選項 = [
  { value: 分位顯示模式前段, label: "前 N%" },
  { value: 分位顯示模式PR, label: "PR" },
];

const activityLogMobileMediaQuery = "(max-width: 720px)";
const activityLogMobileDefaultRange = "30";
const activityLogDesktopDefaultRange = "90";
// 這裡保存時間軸脈絡事件，僅用於前端標註，不參與 Logs 或通關場次統計。
// 台服開放節點維持主要標籤；國際服版本只提供日誌量判讀脈絡，因此用次要標籤呈現。
const activityLogTimelineAnnotations = [
  {
    date: "2025-12-16",
    title: "國際服 7.4",
    detail: "霧中奇境",
    importance: "secondary",
  },
  {
    date: "2026-01-27",
    title: "國際服 7.41",
    detail: "霧中奇境",
    importance: "secondary",
  },
  {
    date: "2026-02-10",
    title: "繁中服 7.01",
    detail: "輕量級",
  },
  {
    date: "2026-03-03",
    title: "國際服 7.45",
    detail: "霧中奇境",
    importance: "secondary",
  },
  {
    date: "2026-03-10",
    title: "繁中服 7.05",
    detail: "零式 輕量級",
  },
  {
    date: "2026-04-21",
    title: "繁中服 7.1",
    detail: "極 永恆女王、幻 白虎",
  },
  {
    date: "2026-04-28",
    title: "國際服 7.5",
    detail: "天際的行路",
    importance: "secondary",
  },
  {
    date: "2026-05-26",
    title: "繁中服 7.11",
    detail: "絕 伊甸",
  },
  {
    date: "2026-06-02",
    title: "國際服 7.51",
    detail: "天際的行路",
    importance: "secondary",
  },
  {
    date: "2026-06-23",
    title: "繁中服 7.15",
    detail: "滅 黑暗之雲",
  },
  {
    date: "2026-07-28",
    title: "國際服 7.55",
    detail: "天際的行路",
    importance: "secondary",
  },
  {
    date: "2026-07-28",
    title: "繁中服 7.2",
    detail: "極 澤蓮尼亞、次重量級",
    importance: "secondary",
  },
  {
    date: "2026-08-04",
    title: "繁中服 7.2",
    detail: "零式 次重量級",
    importance: "secondary",
  },
  {
    date: "2026-09-08",
    title: "國際服 7.56",
    detail: "天際的行路",
    importance: "secondary",
  },
];
const activityLogCategoryColorClasses = new Map([
  ["零式", "近期日誌分類色彩零式"],
  ["極", "近期日誌分類色彩極"],
  ["幻", "近期日誌分類色彩幻"],
  ["滅", "近期日誌分類色彩滅"],
  ["絕", "近期日誌分類色彩絕"],
]);

function getActivityLogDefaultTimeRange() {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return activityLogDesktopDefaultRange;
  }

  return window.matchMedia(activityLogMobileMediaQuery).matches
    ? activityLogMobileDefaultRange
    : activityLogDesktopDefaultRange;
}

export function useRankingApp() {

// 核心 Vue 狀態只保留畫面會變動的資料；不隨操作變動的職業定義、
// 格式化與 URL 規則已抽到 domain/utils，避免這個 composable 繼續膨脹。
const 排行榜資料 = ref(null);
const 副本清單 = ref([]);
const 副本鍵值 = ref(預設副本鍵值);
const 副本選單開啟 = ref(false);
const 讀取中 = ref(true);
const 錯誤訊息 = ref("");
const 伺服器篩選 = ref("");
const 職業類型篩選 = ref("");
const 職業篩選 = ref("");
const 職業選單開啟 = ref(false);
const 搜尋關鍵字 = ref("");
const 玩家搜尋歷史 = ref([]);
const 目前玩家搜尋歷史欄位 = ref("");
const 玩家搜尋歷史管理彈窗開啟 = ref(false);
const 排序欄位 = ref(預設排序欄位);
const 排序方向 = ref(預設排序方向);
const 排行榜版本範圍 = ref(預設版本紀錄範圍);
const 目前頁碼 = ref(1);
const 每頁筆數 = 100;
const {
  主題模式,
  主題儲存鍵,
  主題按鈕文字,
  目前主題文字,
  初始化主題,
  套用主題,
  套用暫時主題,
  切換主題: 切換使用者主題,
} = useTheme();
const 頁面模式 = ref("ranking");
const 停用主題切換 = computed(() => 顯示Honey粉絲榜 && 頁面模式.value === "honey-fans");
const 啟用Honey粉絲榜 = computed(() => 顯示Honey粉絲榜);
const 蜂蜂背景音樂啟用 = ref(false);
const 蜂蜂背景音樂偏好已設定 = ref(false);
const 顯示蜂蜂背景音樂詢問 = ref(false);
const 分位顯示模式 = ref(預設分位顯示模式);
const 顯示說明提示 = ref(true);
const 使用者索引 = ref(null);
const 使用者資料 = ref(null);
const 使用者搜尋關鍵字 = ref("");
const 使用者伺服器篩選 = ref("");
const 使用者職業類型篩選 = ref("");
const 使用者職業篩選 = ref("");
const 使用者職業選單開啟 = ref(false);
const 使用者趨勢職業選擇 = ref({});
const 使用者簡表模式 = ref(false);
const 使用者簡表版本 = ref(預設個人成績簡表版本);
const 使用者簡表零式量級 = ref("");
const 個人成績簡表版本選項 = computed(() => 建立個人成績簡表可選版本());
const 使用者讀取中 = ref(false);
const 使用者錯誤訊息 = ref("");
const 比較角色左輸入 = ref("");
const 比較角色右輸入 = ref("");
const 比較角色左資料 = ref(null);
const 比較角色右資料 = ref(null);
const 比較角色左伺服器 = ref("");
const 比較角色右伺服器 = ref("");
const 比較職能篩選 = ref(預設比較職能);
const 比較副本鍵值 = ref(預設比較副本鍵值);
const 比較副本選單開啟 = ref(false);
const 比較版本範圍 = ref(預設版本紀錄範圍);
const 比較讀取中 = ref(false);
const 比較錯誤訊息 = ref("");
const 全服統計資料 = ref(null);
const 全服統計讀取中 = ref(false);
const 全服統計錯誤訊息 = ref("");
const 統計副本鍵值 = ref(預設統計副本鍵值);
const 統計副本選單開啟 = ref(false);
const 統計版本範圍 = ref(預設版本紀錄範圍);
const 統計伺服器篩選 = ref("");
const 統計職業範圍 = ref(預設統計職業範圍);
const 統計職業選單開啟 = ref(false);
const 伺服器拆分模式 = ref(預設伺服器拆分模式);
const 統計傷害指標 = ref(預設統計傷害指標);
const 職業傷害提示鎖定職業 = ref("");
const 職業傷害提示互動職業 = ref("");
const 職業分析職業 = ref(預設職業分析範圍);
const 職業分析展示類型 = ref("");
const 職業分析選單開啟 = ref(false);
const 近期動態資料 = ref(null);
const 近期動態讀取中 = ref(false);
const 近期動態錯誤訊息 = ref("");
const 近期動態日誌副本鍵值 = ref("all");
const 近期動態日誌副本選單開啟 = ref(false);
const 近期動態日誌時間範圍 = ref(getActivityLogDefaultTimeRange());
const 近期動態日誌指標 = ref("unique_report_count");
const 近期動態日誌自訂開始日期 = ref("");
const 近期動態日誌自訂結束日期 = ref("");
const 近期動態日誌提示點 = ref(null);
const 近期動態日誌提示鎖定 = ref(false);
const 隊伍榜資料 = ref(null);
const 隊伍榜讀取中 = ref(false);
const 隊伍榜錯誤訊息 = ref("");
const 隊伍榜副本鍵值 = ref(預設隊伍榜副本鍵值);
const 隊伍榜副本選單開啟 = ref(false);
const 隊伍榜版本範圍 = ref(預設版本紀錄範圍);
const 伺服器對比資料 = ref(null);
const 伺服器對比讀取中 = ref(false);
const 伺服器對比錯誤訊息 = ref("");
const 伺服器對比左伺服器 = ref("");
const 伺服器對比右伺服器 = ref("");
const 蜂蜂粉絲榜資料 = ref(null);
const 蜂蜂粉絲榜讀取中 = ref(false);
const 蜂蜂粉絲榜錯誤訊息 = ref("");
const 分享狀態訊息 = ref("");
const 正在分享 = ref(false);
const 排行榜詳細資料快取 = new Map();
const 個人成績報告詳細資料快取 = new Map();
let 正在套用網址狀態 = false;
let 分享狀態計時器 = null;

const 近期動態日誌時間範圍選項 = [
  { value: "7", label: "近 7 天" },
  { value: "14", label: "近 14 天" },
  { value: "30", label: "近 30 天" },
  { value: "90", label: "近 90 天" },
  { value: "all", label: "全部資料" },
  { value: "custom", label: "自訂日期" },
];

const 目前副本 = computed(() => {
  return 副本清單.value.find((副本) => 副本.key === 副本鍵值.value) || 副本清單.value[0] || null;
});

const 資料網址 = computed(() => {
  return 建立公開資料網址(目前副本.value?.data_path || "data/rankings/savage_m1s.json");
});

const 排行榜表格資料網址 = computed(() => {
  return 建立排行榜表格資料網址(目前副本.value?.key || 副本鍵值.value || 預設副本鍵值);
});

function 正規化版本紀錄範圍(版本範圍) {
  return 版本紀錄範圍選項.some((選項) => 選項.value === 版本範圍) ? 版本範圍 : 預設版本紀錄範圍;
}

function 取得版本紀錄範圍文字(版本範圍) {
  return 版本紀錄範圍選項.find((選項) => 選項.value === 正規化版本紀錄範圍(版本範圍))?.label || "全部版本";
}

function 取得副本版本規則(副本) {
  if (副本?.version_cutoff?.obsolete_after_iso) {
    return 副本.version_cutoff;
  }

  if (副本?.version_rule?.obsolete_after_iso) {
    return 副本.version_rule;
  }

  const 副本鍵值 = 副本?.key || 副本?.encounter_key;
  return 副本清單.value.find((項目) => 項目.key === 副本鍵值)?.version_cutoff || null;
}

function 副本支援版本篩選(副本) {
  const 規則 = 取得副本版本規則(副本);
  return Boolean(規則?.obsolete_after_iso && !Number.isNaN(new Date(規則.obsolete_after_iso).getTime()));
}

function 取得有效版本紀錄範圍(副本, 版本範圍) {
  return 副本支援版本篩選(副本) ? 正規化版本紀錄範圍(版本範圍) : 預設版本紀錄範圍;
}

function 取得紀錄版本狀態(紀錄, 副本) {
  if (typeof 紀錄?.is_obsolete_record === "boolean") {
    return {
      is_obsolete_record: 紀錄.is_obsolete_record,
      version_status: 紀錄.version_status || (紀錄.is_obsolete_record ? "obsolete" : "valid"),
      version_cutoff_iso: 紀錄.version_cutoff_iso || 取得副本版本規則(副本)?.obsolete_after_iso || null,
    };
  }

  const 規則 = 取得副本版本規則(副本);
  if (!規則?.obsolete_after_iso) {
    return {
      is_obsolete_record: false,
      version_status: null,
      version_cutoff_iso: null,
    };
  }

  const 紀錄時間 = new Date(紀錄?.recorded_at_iso || 紀錄?.紀錄時間 || 0).getTime();
  const 截止時間 = new Date(規則.obsolete_after_iso).getTime();
  const 是否過版 = 紀錄時間 > 0 && !Number.isNaN(截止時間) && 紀錄時間 >= 截止時間;
  return {
    is_obsolete_record: 是否過版,
    version_status: 是否過版 ? "obsolete" : "valid",
    version_cutoff_iso: 規則.obsolete_after_iso,
  };
}

function 紀錄符合版本範圍(紀錄, 版本範圍) {
  const 範圍 = 正規化版本紀錄範圍(版本範圍);
  if (範圍 === "all") {
    return true;
  }

  return 範圍 === "obsolete" ? Boolean(紀錄?.is_obsolete_record) : !紀錄?.is_obsolete_record;
}

function 取得版本切片來源(來源, 版本範圍) {
  const 範圍 = 取得有效版本紀錄範圍(來源, 版本範圍);
  if (範圍 === "all") {
    return 來源;
  }

  return 來源?.version_slices?.[範圍] || 來源;
}

function 版本紀錄說明文字(副本) {
  if (!副本支援版本篩選(副本)) {
    return "";
  }

  const 規則 = 取得副本版本規則(副本);
  const 本地切點 = 規則?.obsolete_after_local || "04/21 18:00";
  const 改版文字 = `${規則?.patch || "改版"} 改版後（${本地切點}）`;
  return `全部版本紀錄會納入所有的紀錄資訊，因此排名可能並不準確。過時版本紀錄為 ${改版文字} 的紀錄；因玩家裝備品級提升，可能存在跳過機制的可能性，較難準確反映玩家當時的副本實力。有效版本紀錄為 ${規則?.patch || "改版"} 改版前的紀錄。`;
}

const 副本清單索引 = computed(() => new Map(副本清單.value.map((副本) => [副本.key, 副本])));

function 取得零式量級(副本, 副本鍵值) {
  return 副本?.profile_summary_savage_tier
    || 副本清單索引.value.get(副本鍵值)?.profile_summary_savage_tier
    || null;
}

function 建立公開副本選單分組({ 包含全部 = false } = {}) {
  const 選項 = 包含全部
    ? [{ key: "all", name: "全部副本", category: "全部" }, ...副本清單.value]
    : 副本清單.value;

  return 建立副本選單分組(選項, {
    取鍵值: (副本) => 副本.key,
    取名稱: (副本) => 副本.name,
    取分類: (副本) => 副本.category,
    取零式量級: (副本) => 取得零式量級(副本, 副本.key),
  });
}

const 副本分組 = computed(() => 建立公開副本選單分組());
const 統計副本分組 = computed(() => 建立公開副本選單分組({ 包含全部: true }));
const 比較副本分組 = computed(() => 建立公開副本選單分組({ 包含全部: true }));

const 副本選單文字 = computed(() => {
  return 目前副本.value?.name || "選擇副本";
});

const 顯示排行榜版本篩選 = computed(() => 副本支援版本篩選(目前副本.value));
const 有效排行榜版本範圍 = computed(() => 取得有效版本紀錄範圍(目前副本.value, 排行榜版本範圍.value));
const 排行榜版本說明文字 = computed(() => 版本紀錄說明文字(目前副本.value));

function 主色由職業選擇(職業代碼, 類型代碼) {
  if (職業代碼) {
    return 職業代碼色彩(職業代碼) || "default";
  }

  return 職業類型色彩(類型代碼) || "default";
}

function 主色由職業範圍(職業範圍) {
  if (!職業範圍 || 職業範圍 === "all") {
    return "default";
  }

  if (String(職業範圍).startsWith("role:")) {
    return 職業類型色彩(職業範圍) || "default";
  }

  return 職業代碼色彩(職業範圍) || "default";
}

function 目前職業主色() {
  return 主色由職業選擇(職業篩選.value, 職業類型篩選.value);
}

function 目前頁面主色() {
  if (頁面模式.value === "stats") {
    return 主色由職業範圍(統計職業範圍.value);
  }
  if (頁面模式.value === "user") {
    return 主色由職業選擇(使用者職業篩選.value, 使用者職業類型篩選.value);
  }
  if (頁面模式.value === "compare") {
    return 主色由職業範圍(比較職能篩選.value);
  }
  if (頁面模式.value === "jobs") {
    return 主色由職業範圍(職業分析目前範圍代碼.value);
  }
  if (頁面模式.value === "honey-fans") {
    return "honey";
  }
  if (頁面模式.value === "activity" || 頁面模式.value === "teams" || 頁面模式.value === "servers" || 頁面模式.value === "faq" || 頁面模式.value === "logs") {
    return "default";
  }

  return 目前職業主色();
}

const 主色模式 = computed(() => 目前頁面主色());

function 符合職業篩選(職業代碼) {
  if (職業類型篩選.value) {
    const 群組職業 = 職業群組索引[職業類型篩選.value];
    if (!群組職業?.has(職業代碼)) {
      return false;
    }
  }

  return !職業篩選.value || 職業代碼 === 職業篩選.value;
}

function 清除職業篩選() {
  職業類型篩選.value = "";
  職業篩選.value = "";
  職業選單開啟.value = false;
}

function 選擇職業類型(類型代碼) {
  職業類型篩選.value = 類型代碼;
  職業篩選.value = "";
}

function 選擇職業(職業代碼) {
  職業篩選.value = 職業篩選.value === 職業代碼 ? "" : 職業代碼;
  職業選單開啟.value = false;
}

function 切換職業選單() {
  副本選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  近期動態日誌副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  使用者職業選單開啟.value = false;
  職業選單開啟.value = !職業選單開啟.value;
}

function 處理職業選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    職業選單開啟.value = false;
  }
}

function 清除使用者職業篩選() {
  使用者職業類型篩選.value = "";
  使用者職業篩選.value = "";
  使用者職業選單開啟.value = false;
}

function 選擇使用者職業類型(類型代碼) {
  使用者職業類型篩選.value = 類型代碼;
  使用者職業篩選.value = "";
}

function 選擇使用者職業(職業代碼) {
  使用者職業篩選.value = 使用者職業篩選.value === 職業代碼 ? "" : 職業代碼;
  使用者職業選單開啟.value = false;
}

function 選擇使用者趨勢職業(副本鍵值, 職業代碼) {
  if (!副本鍵值 || !職業代碼) {
    return;
  }

  使用者趨勢職業選擇.value = {
    ...使用者趨勢職業選擇.value,
    [副本鍵值]: 職業代碼,
  };
}

function 切換使用者簡表模式() {
  使用者簡表模式.value = !使用者簡表模式.value;
}

function 設定使用者簡表版本(版本) {
  使用者簡表版本.value = 正規化個人成績簡表版本(版本);
  // 量級是版本快照的一部分；切換版本後回到該版本最新已開放量級，
  // 避免把上一個版本的手動選擇錯誤沿用到新版本。
  使用者簡表零式量級.value = "";
}

function 設定使用者簡表零式量級(量級鍵值) {
  使用者簡表零式量級.value = typeof 量級鍵值 === "string" ? 量級鍵值 : "";
}

function 切換使用者職業選單() {
  副本選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  近期動態日誌副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  使用者職業選單開啟.value = !使用者職業選單開啟.value;
}

function 處理使用者職業選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    使用者職業選單開啟.value = false;
  }
}

function 切換副本選單() {
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  近期動態日誌副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  副本選單開啟.value = !副本選單開啟.value;
}

function 選擇副本(副本) {
  if (!副本?.key) {
    return;
  }

  副本鍵值.value = 副本.key;
  副本選單開啟.value = false;
}

function 處理副本選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    副本選單開啟.value = false;
  }
}

function 切換統計副本選單() {
  副本選單開啟.value = false;
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  近期動態日誌副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  統計副本選單開啟.value = !統計副本選單開啟.value;
}

function 選擇統計副本(副本) {
  統計副本鍵值.value = 副本?.key || "all";
  統計副本選單開啟.value = false;
}

function 處理統計副本選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    統計副本選單開啟.value = false;
  }
}

function 切換比較副本選單() {
  副本選單開啟.value = false;
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  統計副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  近期動態日誌副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  比較副本選單開啟.value = !比較副本選單開啟.value;
}

function 選擇比較副本(副本) {
  比較副本鍵值.value = 副本?.key || "all";
  比較副本選單開啟.value = false;
}

function 處理比較副本選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    比較副本選單開啟.value = false;
  }
}

function 切換隊伍榜副本選單() {
  副本選單開啟.value = false;
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  近期動態日誌副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  隊伍榜副本選單開啟.value = !隊伍榜副本選單開啟.value;
}

function 處理隊伍榜副本選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    隊伍榜副本選單開啟.value = false;
  }
}

function 切換近期動態日誌副本選單() {
  副本選單開啟.value = false;
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  近期動態日誌副本選單開啟.value = !近期動態日誌副本選單開啟.value;
}

function 選擇近期動態日誌副本(副本鍵值) {
  if (!副本鍵值) {
    return;
  }
  近期動態日誌副本鍵值.value = 副本鍵值;
  近期動態日誌副本選單開啟.value = false;
  清除近期動態日誌提示();
}

function 處理近期動態日誌副本選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    近期動態日誌副本選單開啟.value = false;
  }
}

function 清除統計職業範圍() {
  統計職業範圍.value = "all";
  統計職業選單開啟.value = false;
}

function 選擇統計職業類型(類型代碼) {
  統計職業範圍.value = 類型代碼;
}

function 選擇統計職業(職業代碼) {
  統計職業範圍.value = 統計職業範圍.value === 職業代碼 ? 職業所屬類型(職業代碼)?.代碼 || "all" : 職業代碼;
  統計職業選單開啟.value = false;
}

function 切換統計職業選單() {
  副本選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  職業分析選單開啟.value = false;
  統計職業選單開啟.value = !統計職業選單開啟.value;
}

function 處理統計職業選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    統計職業選單開啟.value = false;
  }
}

function 切換職業分析選單() {
  副本選單開啟.value = false;
  統計副本選單開啟.value = false;
  比較副本選單開啟.value = false;
  隊伍榜副本選單開啟.value = false;
  統計職業選單開啟.value = false;
  職業選單開啟.value = false;
  使用者職業選單開啟.value = false;
  const 即將開啟 = !職業分析選單開啟.value;
  if (即將開啟) {
    職業分析展示類型.value = 職業分析目前類型代碼.value;
  }
  職業分析選單開啟.value = 即將開啟;
}

function 選擇職業分析類型(類型代碼) {
  if (職業分析職業分組.value.some((群組) => 群組.代碼 === 類型代碼)) {
    職業分析職業.value = 類型代碼;
    職業分析展示類型.value = 類型代碼;
  }
}

function 選擇職業分析職業(職業代碼) {
  職業分析職業.value = 職業代碼;
  職業分析展示類型.value = 職業所屬類型(職業代碼)?.代碼 || 職業分析展示類型.value;
  職業分析選單開啟.value = false;
}

function 處理職業分析選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    職業分析選單開啟.value = false;
  }
}

function 保留目前文字選項(選項列表, 目前值) {
  const 選項集合 = new Set(選項列表.filter(Boolean));
  const 目前文字 = String(目前值 || "").trim();
  if (目前文字) {
    // 副本切換後可能暫時沒有這個伺服器的成績；仍保留選項，讓使用者知道篩選條件沒有被悄悄重設。
    選項集合.add(目前文字);
  }

  return Array.from(選項集合).sort((前一個, 後一個) => 前一個.localeCompare(後一個, "zh-Hant-TW"));
}

const {
  排序欄位預設方向,
  排序方向文字,
  下一個排序方向,
  切換排序,
  是否目前排序,
  排序方向圖示,
  排序ARIA,
  排序按鈕標籤,
  排序數值,
  比較排行列,
  建立排行列,
  解析排行榜資料格式,
  解析排行榜詳細資料格式,
  成績是否較佳,
  只保留角色最佳成績,
  展開排行榜列,
} = useRankingData({
  排序欄位,
  排序方向,
  目前副本,
  取得紀錄版本狀態,
  取得有效版本紀錄範圍,
  紀錄符合版本範圍,
  預設版本紀錄範圍,
});

const 所有排行列 = computed(() => {
  return 展開排行榜列(排行榜資料.value, 目前副本.value, 有效排行榜版本範圍.value).sort(比較排行列);
});

const 伺服器選項 = computed(() => {
  const 名稱列表 = 所有排行列.value.map((列) => 列.伺服器).filter((伺服器) => 伺服器 && 伺服器 !== "未知伺服器");
  return 保留目前文字選項(名稱列表, 伺服器篩選.value);
});

const 職業選項 = computed(() => {
  const 目前有資料職業 = new Set();

  for (const 列 of 所有排行列.value) {
    if (列.職業代碼 && 列.職業代碼 !== "-") {
      目前有資料職業.add(列.職業代碼);
    }
  }

  const 群組選項 = 職業群組設定
    .map((群組) => ({
      代碼: 群組.代碼,
      名稱: 群組.名稱,
      色彩: 群組.色彩,
      職業: 群組.職業.filter((職業代碼) => {
        return 目前有資料職業.has(職業代碼) || (職業類型篩選.value === 群組.代碼 && 職業篩選.value === 職業代碼);
      }).map((職業代碼) => ({
        代碼: 職業代碼,
        名稱: 顯示職業名稱(職業代碼),
        色彩: 群組.色彩,
      })),
    }))
    .filter((群組) => 群組.職業.length > 0);

  if (!職業類型篩選.value) {
    return [];
  }

  return 群組選項.find((群組) => 群組.代碼 === 職業類型篩選.value)?.職業 || [];
});

const 職業類型選項 = computed(() => {
  const 目前有資料職業 = new Set();

  for (const 列 of 所有排行列.value) {
    if (列.職業代碼 && 列.職業代碼 !== "-") {
      目前有資料職業.add(列.職業代碼);
    }
  }

  return 職業群組設定
    .filter((群組) => 群組.職業.some((職業代碼) => 目前有資料職業.has(職業代碼)) || 職業類型篩選.value === 群組.代碼)
    .map((群組) => ({
      代碼: 群組.代碼,
      名稱: 群組.名稱,
      色彩: 群組.色彩,
    }));
});

const 目前職業類型 = computed(() => {
  return 職業群組設定.find((群組) => 群組.代碼 === 職業類型篩選.value) || null;
});

const 職業選單文字 = computed(() => {
  if (職業篩選.value) {
    return 目前職業類型.value
      ? `${目前職業類型.value.名稱} / ${顯示職業名稱(職業篩選.value)}`
      : 顯示職業名稱(職業篩選.value);
  }

  return 目前職業類型.value?.名稱 || "全部職業";
});

const 職業選單Icon路徑 = computed(() => {
  if (職業篩選.value) {
    return 職業Icon路徑(職業篩選.value);
  }

  if (職業類型篩選.value) {
    return 職業類型Icon路徑(職業類型篩選.value);
  }

  return "";
});

const 全服統計副本列表 = computed(() => {
  return Array.isArray(全服統計資料.value?.encounters) ? 全服統計資料.value.encounters : [];
});

const 目前統計副本 = computed(() => {
  if (統計副本鍵值.value === "all") {
    return null;
  }

  return 全服統計副本列表.value.find((副本) => 副本.encounter_key === 統計副本鍵值.value) || null;
});

const 統計範圍文字 = computed(() => {
  return 目前統計副本.value?.encounter_name || "全部副本";
});

const 統計副本選單文字 = computed(() => {
  return 統計範圍文字.value;
});

const 顯示統計版本篩選 = computed(() => 副本支援版本篩選(目前統計副本.value));
const 有效統計版本範圍 = computed(() => 取得有效版本紀錄範圍(目前統計副本.value, 統計版本範圍.value));

const 顯示零式進度漏斗 = computed(() => {
  return !目前統計副本.value || 目前統計副本.value.encounter_category === "零式";
});

const 顯示副本通關概覽 = computed(() => {
  return !目前統計副本.value;
});

const 目前統計來源 = computed(() => {
  if (目前統計副本.value) {
    return 取得版本切片來源(目前統計副本.value, 有效統計版本範圍.value);
  }

  return 全服統計資料.value || null;
});

const 傷害比較指標標籤 = computed(() => {
  return 傷害比較指標選項.find((選項) => 選項.value === 統計傷害指標.value)?.label || "rDPS";
});

const 職業傷害提示作用職業 = computed(() => {
  return 職業傷害提示互動職業.value || 職業傷害提示鎖定職業.value;
});

const 職業傷害比較資料來源 = computed(() => {
  const 伺服器 = 統計伺服器篩選.value;

  if (目前統計副本.value) {
    const 來源 = 目前統計來源.value;
    if (伺服器) {
      return (來源?.server_stats || []).find((項目) => 項目.server === 伺服器)?.damage_stats || [];
    }
    return 來源?.damage_stats || [];
  }

  if (伺服器) {
    return (全服統計資料.value?.savage_server_damage_stats || []).find((項目) => 項目.server === 伺服器)?.damage_stats || [];
  }

  return 全服統計資料.value?.savage_damage_stats || [];
});

// 箱型圖資料由 build_user_data.mjs 預先聚合，前端只依目前篩選挑選指標與換算座標。
// 保留這個邊界很重要：排序、分位數與樣本統計都應在 Data Building Layer 完成。
const 職業傷害比較條件文字 = computed(() => {
  const 範圍 = 目前統計副本.value ? 統計範圍文字.value : "零式 M1S-M4S";
  const 版本文字 = 顯示統計版本篩選.value ? `・${取得版本紀錄範圍文字(有效統計版本範圍.value)}` : "";
  return `${範圍}${版本文字}・${統計伺服器文字.value}`;
});

const 職業傷害比較基礎列 = computed(() => {
  const 指標 = 統計傷害指標.value;

  return 職業傷害比較資料來源.value
    .map((項目) => {
      const 指標統計 = 項目.metrics?.[指標];
      if (!指標統計?.count) {
        return null;
      }

      const 最小值 = 轉為數字(指標統計.min);
      const 第一四分位 = 轉為數字(指標統計.q1);
      const 中位數 = 轉為數字(指標統計.median);
      const 第三四分位 = 轉為數字(指標統計.q3);
      const 最大值 = 轉為數字(指標統計.max);
      const 平均值 = 轉為數字(指標統計.average);
      if ([最小值, 第一四分位, 中位數, 第三四分位, 最大值].some((數值) => 數值 === null)) {
        return null;
      }

      return {
        job: 項目.job,
        role: 項目.role,
        role_name: 項目.role_name,
        count: 指標統計.count,
        min: 最小值,
        q1: 第一四分位,
        median: 中位數,
        q3: 第三四分位,
        max: 最大值,
        average: 平均值 ?? 中位數,
        色彩: 職業比較圖色彩(項目.job),
      };
    })
    .filter(Boolean)
    .sort((前一個, 後一個) => 後一個.median - 前一個.median || 後一個.max - 前一個.max || 前一個.job.localeCompare(後一個.job));
});

const 職業傷害比較值域 = computed(() => {
  const 數值列表 = 職業傷害比較基礎列.value.flatMap((列) => [列.min, 列.q1, 列.median, 列.q3, 列.max]);
  if (數值列表.length === 0) {
    return {
      min: 0,
      max: 1,
      ticks: [],
    };
  }

  const 原始最小值 = Math.min(...數值列表);
  const 原始最大值 = Math.max(...數值列表);
  const 差距 = Math.max(原始最大值 - 原始最小值, 原始最大值 * 0.08, 1);
  const min = Math.max(0, Math.floor((原始最小值 - 差距 * 0.08) / 500) * 500);
  const max = Math.ceil((原始最大值 + 差距 * 0.08) / 500) * 500 || 1;
  const tickCount = 5;
  const ticks = Array.from({ length: tickCount }, (_, 索引) => min + ((max - min) * 索引) / (tickCount - 1));

  return {
    min,
    max: max <= min ? min + 1 : max,
    ticks,
  };
});

function 職業傷害位置(數值) {
  const { min, max } = 職業傷害比較值域.value;
  const 比例 = ((數值 - min) / (max - min)) * 100;
  return `${Math.min(100, Math.max(0, 比例))}%`;
}

const 職業傷害比較刻度 = computed(() => {
  return 職業傷害比較值域.value.ticks.map((數值) => ({
    數值,
    位置: 職業傷害位置(數值),
  }));
});

const 職業傷害比較列 = computed(() => {
  return 職業傷害比較基礎列.value.map((列) => ({
    ...列,
    樣式: {
      "--職業比較色": 列.色彩,
      "--最小值": 職業傷害位置(列.min),
      "--第一四分位": 職業傷害位置(列.q1),
      "--中位數": 職業傷害位置(列.median),
      "--第三四分位": 職業傷害位置(列.q3),
      "--最大值": 職業傷害位置(列.max),
      "--平均值": 職業傷害位置(列.average),
    },
  }));
});

function 職業傷害提示文字(列) {
  return `${顯示職業名稱(列.job)} ${傷害比較指標標籤.value}：最小 ${格式化傷害數值(列.min)}，中位數 ${格式化傷害數值(列.median)}，平均 ${格式化傷害數值(列.average)}，最大 ${格式化傷害數值(列.max)}，樣本 ${格式化整數(列.count)} 筆`;
}

function 顯示職業傷害提示(職業代碼) {
  職業傷害提示互動職業.value = 職業代碼;
}

function 隱藏職業傷害提示(職業代碼) {
  if (職業傷害提示互動職業.value === 職業代碼) {
    職業傷害提示互動職業.value = "";
  }
}

function 切換職業傷害提示(職業代碼) {
  const 已鎖定 = 職業傷害提示鎖定職業.value === 職業代碼;
  職業傷害提示鎖定職業.value = 已鎖定 ? "" : 職業代碼;
  職業傷害提示互動職業.value = 已鎖定 ? "" : 職業代碼;
}

function 取得統計計數(統計項目, 職業範圍 = 統計職業範圍.value) {
  return 取得統計範圍計數(統計項目, 職業範圍);
}

function 取得職業範圍文字(範圍 = 統計職業範圍.value) {
  const 類型 = 職業範圍類型(範圍);
  if (類型 === "role") {
    return 職業群組設定.find((群組) => 群組.代碼 === 範圍)?.名稱 || "職業類型";
  }
  if (類型 === "job") {
    const 群組 = 職業所屬類型(範圍);
    return 群組 ? `${群組.名稱} / ${顯示職業名稱(範圍)}` : 顯示職業名稱(範圍);
  }
  return "全部職業";
}

const 伺服器佔比單位 = computed(() => {
  if (職業範圍類型(統計職業範圍.value) !== "all") {
    return "紀錄";
  }
  return 目前統計副本.value ? "人" : "人次";
});

const 統計伺服器選項 = computed(() => {
  const 名稱列表 = (目前統計來源.value?.server_stats || []).map((項目) => 項目.server).filter(Boolean);
  return 保留目前文字選項(名稱列表, 統計伺服器篩選.value);
});

const 統計職業範圍選項 = computed(() => {
  const 來源 = 目前統計來源.value || 全服統計資料.value;
  const 角色類型選項 = (來源?.role_stats || []).map((項目) => ({
    value: 項目.role,
    label: 項目.role_name,
    group: "職業類型",
  }));
  const 職業選項 = (來源?.job_stats || []).map((項目) => ({
    value: 項目.job,
    label: `${項目.role_name || "職業"} / ${顯示職業名稱(項目.job)}`,
    group: "各職業",
  }));

  return [{ value: "all", label: "全部職業", group: "全部" }, ...角色類型選項, ...職業選項];
});

const 統計職業範圍類型代碼 = computed(() => {
  const 類型 = 職業範圍類型(統計職業範圍.value);
  if (類型 === "role") {
    return 統計職業範圍.value;
  }
  if (類型 === "job") {
    return 職業所屬類型(統計職業範圍.value)?.代碼 || "";
  }
  return "";
});

const 統計職業範圍職業代碼 = computed(() => {
  return 職業範圍類型(統計職業範圍.value) === "job" ? 統計職業範圍.value : "";
});

const 統計職業類型選項 = computed(() => {
  const 來源 = 目前統計來源.value || 全服統計資料.value;
  const 可用類型 = new Set((來源?.role_stats || []).map((項目) => 項目.role).filter(Boolean));
  return 職業群組設定
    .filter((群組) => 可用類型.has(群組.代碼) || 統計職業範圍類型代碼.value === 群組.代碼)
    .map((群組) => ({
      ...群組,
      clear_count: 轉為數字((來源?.role_stats || []).find((項目) => 項目.role === 群組.代碼)?.clear_count) || 0,
    }));
});

const 統計職業選項 = computed(() => {
  const 來源 = 目前統計來源.value || 全服統計資料.value;
  const 類型代碼 = 統計職業範圍類型代碼.value;
  if (!類型代碼) {
    return [];
  }

  const 選項列表 = (來源?.job_stats || [])
    .filter((項目) => 項目.role === 類型代碼)
    .map((項目) => ({
      代碼: 項目.job,
      名稱: 顯示職業名稱(項目.job),
      色彩: 職業代碼色彩(項目.job),
      clear_count: 轉為數字(項目.clear_count) || 0,
    }));

  const 目前職業 = 統計職業範圍職業代碼.value;
  if (目前職業 && 職業所屬類型(目前職業)?.代碼 === 類型代碼 && !選項列表.some((選項) => 選項.代碼 === 目前職業)) {
    選項列表.push({
      代碼: 目前職業,
      名稱: 顯示職業名稱(目前職業),
      色彩: 職業代碼色彩(目前職業),
      clear_count: 0,
    });
  }

  return 選項列表;
});

function 統計伺服器可識別(伺服器) {
  const 伺服器名稱 = String(伺服器 || "").trim();
  if (!伺服器名稱 || !全服統計資料.value) {
    return true;
  }

  return (全服統計資料.value.server_stats || []).some((項目) => 項目.server === 伺服器名稱);
}

function 統計職業範圍可識別(範圍) {
  const 類型 = 職業範圍類型(範圍);
  if (類型 === "all") {
    return true;
  }
  if (類型 === "role") {
    return 職業群組設定.some((群組) => 群組.代碼 === 範圍);
  }

  return Boolean(職業所屬類型(範圍));
}

const 統計職業選單文字 = computed(() => 取得職業範圍文字());

const 統計職業選單Icon路徑 = computed(() => {
  if (統計職業範圍職業代碼.value) {
    return 職業Icon路徑(統計職業範圍職業代碼.value);
  }

  if (統計職業範圍類型代碼.value) {
    return 職業類型Icon路徑(統計職業範圍類型代碼.value);
  }

  return "";
});

const 統計伺服器文字 = computed(() => {
  return 統計伺服器篩選.value || "全部伺服器";
});

const 統計條件文字 = computed(() => {
  const 版本文字 = 顯示統計版本篩選.value ? `・${取得版本紀錄範圍文字(有效統計版本範圍.value)}` : "";
  return `${統計範圍文字.value}${版本文字}・${統計伺服器文字.value}・${取得職業範圍文字()}`;
});

const 全服概要項目 = computed(() => {
  const 統計 = 全服統計資料.value;
  const 副本 = 目前統計副本.value ? 目前統計來源.value : null;
  if (!統計) {
    return [];
  }

  if (副本) {
    return [
      { 標籤: "通關玩家", 數值: 格式化整數(副本.character_count) },
      { 標籤: "職業紀錄", 數值: 格式化整數(副本.job_record_count) },
      { 標籤: "公開成績", 數值: 格式化整數(副本.entry_count) },
      { 標籤: "公開玩家覆蓋率", 數值: 格式化百分比(副本.clear_share_percent) },
    ];
  }

  return [
    { 標籤: "全服公開玩家", 數值: 格式化整數(統計.total_character_count) },
    { 標籤: "副本通關人次", 數值: 格式化整數(統計.total_encounter_clear_count) },
    { 標籤: "職業通關紀錄", 數值: 格式化整數(統計.total_job_clear_count) },
    { 標籤: "公開成績", 數值: 格式化整數(統計.total_entry_count) },
  ];
});

const 統計詞彙說明 = {
  全服公開玩家: "目前公開資料中出現過的唯一玩家數，不代表遊戲內完整人口。",
  副本通關人次: "各副本的通關玩家數加總；同一玩家跨副本會分別計入。",
  職業通關紀錄: "同一玩家若用不同職業留下通關成績，會各自計為一筆職業紀錄。",
  公開成績: "目前抓取到且可公開呈現的 FFLogs 成績筆數。",
  通關玩家: "同一玩家在同一副本會去重計算。",
  職業紀錄: "同一玩家在同一副本使用不同職業時，會分別計入。",
  公開玩家覆蓋率: "單一副本的通關玩家數除以目前公開資料中出現過的唯一玩家數。",
  伺服器佔比: "在目前副本與職業範圍下，各伺服器佔全部符合條件紀錄的比例。",
  職業佔比: "在目前副本與伺服器範圍下，各職業或職業類型佔全部符合條件紀錄的比例。",
  隊友關係: "依公開通關同場資料整理常同場隊友、職能組成與副本聚集；不等同實際長期組隊名單。",
  同場副本聚集: "把此玩家與隊友一起出現在同一筆公開通關紀錄的資料依副本彙整；場數是同場通關次數，隊友數是曾在該副本同場的不同玩家數，用來看同場關係主要集中在哪些副本。",
  伺服器生態比較: "以各伺服器內部的職能通關紀錄比例呈現，顏色越深代表該職能在該伺服器占比越高。",
  通關紀錄: "套用職業範圍時，以符合職業條件的通關紀錄計算。",
  範圍佔比: "套用伺服器或職業範圍後，副本通關概覽會改以目前篩選範圍作為分母。",
  零式進度漏斗: "以目前伺服器與職業範圍計算各零式層數的公開通關規模；套用單一職業時，代表該職業留下的通關紀錄。",
  全職業輸出比較: "以公開成績統計每個職業的傷害分布；全部副本時固定使用 M1S、M2S、M3S、M4S。",
  Active: "有效輸出時間比例。數值越高，代表玩家在戰鬥中維持輸出或行動的時間越完整。",
  DPS: "原始每秒傷害，包含自身傷害以及吃到外部增益後造成的傷害。",
  rDPS: "團隊貢獻 DPS。公式：DPS - 他人團輔 + 自體團輔，用來衡量你實際為團隊帶來的傷害。",
  nDPS: "純淨 DPS。公式：DPS - 他人團輔，用來看移除外部增益後自己的輸出表現。",
  aDPS: "調整後 DPS。公式：DPS - 被選取的單體增益，會移除標舞、舞伴、占星卡與龍眼等單體填充傷害。",
  cDPS: "綜合 DPS。公式：DPS - 被選取的單體增益 + 自體團輔，用來同時觀察自身爆發與你提供給團隊的增益價值。",
  "GCD 覆蓋率": "以 FFLogs Casts graph 與本地規則補算玩家在扣除停手視窗後，GCD 技能覆蓋有效輸出時間的比例。由於停手、轉場與部分職業技能判定仍可能與實際狀況有落差，精準度有限，請只作為參考；尚未補齊或 report 無法存取時會顯示 -。",
  "最佳 rDPS": "此玩家目前公開成績中最高的團隊貢獻 DPS。",
  "職業 Rank": "同副本、同職業的有效版本排行榜名次；會以角色、伺服器與職業去重保留最佳紀錄。下方前 N% / PR 由此名次與該職業通關數換算，母體不等同同職分位。",
  同職分位: "同副本、同職業、非過版且 Active 達 50% 的 rDPS 比較分位；低 Active 或缺少 rDPS 的紀錄不列入樣本，所以可能與職業 Rank 的前 N% / PR 不同。",
};

function 統計說明文字(詞彙) {
  return 統計詞彙說明[詞彙] || "";
}

function 取得Gcd覆蓋率數值(gcdCoverage) {
  return typeof gcdCoverage === "number" ? 轉為數字(gcdCoverage) : 轉為數字(gcdCoverage?.percent);
}

function 格式化帶號百分比(數值) {
  const 數字 = 轉為數字(數值);
  if (數字 === null) {
    return "-";
  }

  const 絕對值文字 = `${Math.abs(數字).toFixed(2)}%`;
  if (數字 > 0) {
    return `+${絕對值文字}`;
  }
  if (數字 < 0) {
    return `-${絕對值文字}`;
  }
  return "0.00%";
}

const 使用PR分位顯示 = computed(() => 分位顯示模式.value === 分位顯示模式PR);
const 目前分位顯示模式文字 = computed(() => (使用PR分位顯示.value ? "PR" : "前 N%"));
const 前段四分位標籤 = computed(() => (使用PR分位顯示.value ? "PR 75" : "前段 25%"));
const 分位顯示切換標籤 = computed(() => `同職分位顯示：${目前分位顯示模式文字.value}`);

function 格式化目前同職分位(performance) {
  return 格式化同職分位(performance, 分位顯示模式.value);
}

function 格式化目前排名分位(排名, 總數) {
  return 格式化排名分位(排名, 總數, 分位顯示模式.value);
}

function 同職分位色彩類別(performance) {
  return 使用PR分位顯示.value ? 取得PR色彩類別(performance) : "";
}

function 簡表PR色彩類別(PR值) {
  // 簡表固定顯示 PR，不應受到完整成績單「前 N%／PR」顯示偏好的影響。
  // 直接沿用全站的 PR 分級，讓 PR 95、99、100 等門檻在所有畫面保持一致。
  return 取得PR色彩類別(PR值);
}

function 排名分位色彩類別(排名, 總數) {
  return 使用PR分位顯示.value ? 取得PR色彩類別(計算排名PR值(排名, 總數)) : "";
}

const 伺服器佔比列表 = computed(() => {
  const 伺服器列表 = 目前統計來源.value?.server_stats || [];
  const 加總 = 伺服器列表.reduce((總數, 項目) => 總數 + 取得統計計數(項目), 0);

  return 伺服器列表
    .map((項目) => {
      const 顯示數量 = 取得統計計數(項目);
      return {
        ...項目,
        顯示數量,
        顯示比例: 加總 > 0 ? Number(((顯示數量 / 加總) * 100).toFixed(2)) : 0,
      };
    })
    .filter((項目) => 項目.顯示數量 > 0);
});

function 取得伺服器拆分列表(伺服器項目) {
  if (!伺服器項目 || 伺服器拆分模式.value === "none") {
    return [];
  }

  const 範圍類型 = 職業範圍類型(統計職業範圍.value);
  const 原始列表 = 伺服器拆分模式.value === "role" ? 伺服器項目.role_stats || [] : 伺服器項目.job_stats || [];
  const 過濾列表 = 原始列表.filter((項目) => {
    if (範圍類型 === "role") {
      return 伺服器拆分模式.value === "role" ? 項目.role === 統計職業範圍.value : 項目.role === 統計職業範圍.value;
    }
    if (範圍類型 === "job") {
      return 伺服器拆分模式.value === "role"
        ? 項目.role === 職業所屬類型(統計職業範圍.value)?.代碼
        : 項目.job === 統計職業範圍.value;
    }
    return true;
  });
  const 加總 = 過濾列表.reduce((總數, 項目) => 總數 + (轉為數字(項目.clear_count) || 0), 0);

  return 過濾列表.map((項目) => ({
    ...項目,
    顯示名稱: 項目.role_name || 顯示職業名稱(項目.job),
    顯示比例: 加總 > 0 ? Number((((轉為數字(項目.clear_count) || 0) / 加總) * 100).toFixed(2)) : 0,
  }));
}

const 職業佔比來源 = computed(() => {
  if (!統計伺服器篩選.value) {
    return 目前統計來源.value;
  }

  return (目前統計來源.value?.server_stats || []).find((項目) => 項目.server === 統計伺服器篩選.value) || null;
});

const 職業佔比標題文字 = computed(() => {
  const 版本文字 = 顯示統計版本篩選.value ? `・${取得版本紀錄範圍文字(有效統計版本範圍.value)}` : "";
  return `${統計範圍文字.value}${版本文字}・${統計伺服器文字.value}`;
});

const 職業佔比分組 = computed(() => {
  return 建立職業佔比分組(職業佔比來源.value, 統計職業範圍.value);
});

const 伺服器生態欄位 = computed(() => {
  return 職業群組設定.map((群組) => ({
    role: 群組.代碼,
    label: 群組.名稱,
    色彩: 群組.色彩,
  }));
});

const 伺服器生態矩陣 = computed(() => {
  const 伺服器列表 = 目前統計來源.value?.server_stats || [];

  return 伺服器列表
    .map((伺服器項目) => {
      const roleStats = Array.isArray(伺服器項目.role_stats) ? 伺服器項目.role_stats : [];
      const 加總 = roleStats.reduce((總數, 項目) => 總數 + (轉為數字(項目.clear_count) || 0), 0);
      const 欄位 = 伺服器生態欄位.value.map((欄位項目) => {
        const 統計 = roleStats.find((項目) => 項目.role === 欄位項目.role);
        const 數量 = 轉為數字(統計?.clear_count) || 0;
        return {
          ...欄位項目,
          數量,
          比例: 加總 > 0 ? Number(((數量 / 加總) * 100).toFixed(2)) : 0,
        };
      });
      const 最高欄位 = 欄位.slice().sort((前一個, 後一個) => 後一個.比例 - 前一個.比例)[0] || null;

      return {
        server: 伺服器項目.server,
        欄位,
        最高欄位,
        加總,
      };
    })
    .filter((列) => 列.加總 > 0);
});

const 職業分析職業選項 = computed(() => {
  const 職業列表 = Array.isArray(全服統計資料.value?.job_stats) ? 全服統計資料.value.job_stats : [];
  return 職業列表.map((項目) => ({
    ...項目,
    label: 顯示職業名稱(項目.job),
  }));
});

const 職業分析有資料職業 = computed(() => {
  return new Set(職業分析職業選項.value.map((職業) => 職業.job).filter(Boolean));
});

const 職業分析職業分組 = computed(() => {
  // 職業分析現在有 role / job 兩種範圍。職能本身是可分享、可分析的狀態；
  // 右欄職業列表則讓使用者能從同一個選單繼續鑽到單一職業。
  return 職業群組設定
    .map((群組) => {
      const 職業列表 = 群組.職業
        .filter((職業代碼) => 職業分析有資料職業.value.has(職業代碼))
        .map((職業代碼) => ({
          代碼: 職業代碼,
          名稱: 顯示職業名稱(職業代碼),
          色彩: 群組.色彩,
        }));

      return {
        代碼: 群組.代碼,
        名稱: 群組.名稱,
        色彩: 群組.色彩,
        職業列表,
      };
    })
    .filter((群組) => 群組.職業列表.length > 0);
});

const 職業分析預設範圍代碼 = computed(() => {
  if (職業分析職業分組.value.some((群組) => 群組.代碼 === 預設職業分析範圍)) {
    return 預設職業分析範圍;
  }

  return 職業分析職業分組.value[0]?.代碼 || "";
});

const 職業分析目前範圍代碼 = computed(() => {
  const 範圍 = String(職業分析職業.value || "").trim();
  if (!範圍) {
    return 職業分析預設範圍代碼.value;
  }
  if (範圍.startsWith("role:") && 職業分析職業分組.value.some((群組) => 群組.代碼 === 範圍)) {
    return 範圍;
  }
  if (職業分析職業選項.value.some((職業) => 職業.job === 範圍)) {
    return 範圍;
  }

  return 職業分析預設範圍代碼.value;
});

const 職業分析目前範圍類型 = computed(() => {
  const 範圍代碼 = 職業分析目前範圍代碼.value;
  if (範圍代碼.startsWith("role:")) {
    return "role";
  }

  return 範圍代碼 ? "job" : "";
});

const 職業分析目前職業代碼 = computed(() => {
  return 職業分析目前範圍類型.value === "job" ? 職業分析目前範圍代碼.value : "";
});

const 職業分析目前職業 = computed(() => {
  return 職業分析職業選項.value.find((項目) => 項目.job === 職業分析目前職業代碼.value) || null;
});

const 職業分析目前類型代碼 = computed(() => {
  if (職業分析目前範圍類型.value === "role") {
    return 職業分析目前範圍代碼.value;
  }

  return (
    職業所屬類型(職業分析目前職業代碼.value)?.代碼 ||
    職業分析職業分組.value[0]?.代碼 ||
    ""
  );
});

const 職業分析目前類型 = computed(() => {
  return 職業群組設定.find((群組) => 群組.代碼 === 職業分析目前類型代碼.value) || null;
});

const 職業分析展示類型代碼 = computed(() => {
  if (職業分析職業分組.value.some((群組) => 群組.代碼 === 職業分析展示類型.value)) {
    return 職業分析展示類型.value;
  }

  return 職業分析目前類型代碼.value;
});

const 職業分析展示職業 = computed(() => {
  return 職業分析職業分組.value.find((群組) => 群組.代碼 === 職業分析展示類型代碼.value)?.職業列表 || [];
});

function 取得來源範圍統計(來源, 範圍代碼) {
  const 類型 = 職業範圍類型(範圍代碼);
  if (類型 === "role") {
    return (來源?.role_stats || []).find((項目) => 項目.role === 範圍代碼) || null;
  }
  if (類型 === "job") {
    return (來源?.job_stats || []).find((項目) => 項目.job === 範圍代碼) || null;
  }

  return null;
}

function 建立職業分析職能職業分布列(來源, 範圍代碼) {
  if (職業範圍類型(範圍代碼) !== "role") {
    return [];
  }

  const 職業順序 = new Map(
    (職業分析職業分組.value.find((群組) => 群組.代碼 === 範圍代碼)?.職業列表 || [])
      .map((職業, index) => [職業.代碼, index]),
  );

  return (來源?.job_stats || [])
    .filter((項目) => 項目?.role === 範圍代碼 && 職業順序.has(項目.job))
    .map((項目) => {
      const 佔比 = 轉為數字(項目.percentage) || 0;
      const 安全佔比 = Math.min(Math.max(佔比, 0), 100);

      return {
        job: 項目.job,
        數量: 轉為數字(項目.clear_count) || 0,
        佔比,
        樣式: {
          "--職能職業分布色": 職業比較圖色彩(項目.job),
          "--職能職業分布寬度": `${安全佔比}%`,
        },
      };
    })
    .filter((項目) => 項目.數量 > 0)
    .sort((前一個, 後一個) => {
      const 順序差 = (職業順序.get(前一個.job) ?? Number.MAX_SAFE_INTEGER) - (職業順序.get(後一個.job) ?? Number.MAX_SAFE_INTEGER);
      return 順序差 || 後一個.數量 - 前一個.數量 || 顯示職業名稱(前一個.job).localeCompare(顯示職業名稱(後一個.job), "zh-Hant-TW");
    });
}

const 職業分析目前範圍 = computed(() => {
  const 範圍代碼 = 職業分析目前範圍代碼.value;
  const 範圍類型 = 職業分析目前範圍類型.value;

  if (範圍類型 === "role") {
    const 群組 = 職業群組設定.find((項目) => 項目.代碼 === 範圍代碼);
    if (!群組) {
      return null;
    }

    return {
      類型: "role",
      代碼: 群組.代碼,
      名稱: 群組.名稱,
      副標: "職能",
      色彩: 群組.色彩,
      Icon路徑: 職業類型Icon路徑(群組.代碼),
    };
  }

  const 職業 = 職業分析目前職業.value;
  if (!職業) {
    return null;
  }

  return {
    類型: "job",
    代碼: 職業.job,
    名稱: 顯示職業名稱(職業.job),
    副標: 職業.role_name,
    色彩: 職業代碼色彩(職業.job),
    Icon路徑: 職業Icon路徑(職業.job),
  };
});

const 職業分析選單文字 = computed(() => {
  if (!職業分析目前範圍.value) {
    return "選擇分析範圍";
  }

  return 職業分析目前範圍.value.類型 === "job"
    ? `${職業分析目前範圍.value.副標} / ${職業分析目前範圍.value.名稱}`
    : 職業分析目前範圍.value.名稱;
});

const 職業分析選單Icon路徑 = computed(() => {
  return 職業分析目前範圍.value?.Icon路徑 || "";
});

const 職業分析分位來源 = computed(() => {
  const 零式分位 = Array.isArray(全服統計資料.value?.savage_damage_stats)
    ? 全服統計資料.value.savage_damage_stats
    : [];

  if (零式分位.length > 0) {
    return {
      標籤: "零式 M1S-M4S",
      列表: 零式分位,
    };
  }

  return {
    標籤: "全部副本",
    列表: Array.isArray(全服統計資料.value?.damage_stats) ? 全服統計資料.value.damage_stats : [],
  };
});

const 職業分析分位亮點條件文字 = computed(() => {
  return `${職業分析分位來源.value.標籤}・Active 達標樣本・rDPS`;
});

function 建立職業分析分位亮點列(項目) {
  const 指標統計 = 項目?.metrics?.rdps;
  const 樣本數 = 轉為數字(指標統計?.count) || 0;
  const 中位數 = 轉為數字(指標統計?.median);
  const 前段值 = 轉為數字(指標統計?.q3) ?? 中位數;
  const 最高值 = 轉為數字(指標統計?.max);

  if (!項目?.job || 樣本數 <= 0 || 前段值 === null) {
    return null;
  }

  return {
    job: 項目.job,
    role: 項目.role,
    role_name: 項目.role_name,
    樣本數,
    中位數,
    前段值,
    最高值,
  };
}

const 職業分析分位亮點基礎列 = computed(() => {
  const 原始列表 = 職業分析分位來源.value.列表
    .map((項目) => {
      const 指標統計 = 項目?.metrics?.rdps;
      const 前段值 = 轉為數字(指標統計?.q3) ?? 轉為數字(指標統計?.median);
      return {
        項目,
        前段值,
      };
    })
    .filter((列) => 列.項目?.job && 列.前段值 !== null);
  return 原始列表
    .map((列) => 建立職業分析分位亮點列(列.項目))
    .filter(Boolean)
    .sort((前一個, 後一個) => {
      const 前段差 = 後一個.前段值 - 前一個.前段值;
      if (前段差) {
        return 前段差;
      }
      const 中位差 = (後一個.中位數 || 0) - (前一個.中位數 || 0);
      return 中位差 || 顯示職業名稱(前一個.job).localeCompare(顯示職業名稱(後一個.job), "zh-Hant-TW");
    });
});

const 職業分析分位亮點標題 = computed(() => {
  if (!職業分析目前範圍.value) {
    return "rDPS 分位";
  }

  return `${職業分析目前範圍.value.名稱} rDPS 分位`;
});

const 職業分析分位亮點列 = computed(() => {
  const 範圍類型 = 職業分析目前範圍類型.value;
  const 範圍代碼 = 職業分析目前範圍代碼.value;
  if (範圍類型 !== "role") {
    return [];
  }

  const 顯示列表 = 職業分析分位亮點基礎列.value.filter((列) => 列.role === 範圍代碼);
  const 最大前段值 = Math.max(...顯示列表.map((列) => 列.前段值), 0);

  // 這裡只排列 build_user_data.mjs 已完成的分位摘要，不在 Vue 重新掃描成績明細。
  // 分位亮點只在職能範圍顯示，單一職業頁則保留給副本、伺服器與代表紀錄等深入資訊。
  return 顯示列表.map((列) => ({
    ...列,
    樣式: {
      "--職業分位色": 職業比較圖色彩(列.job),
      "--職業分位強度": `${最大前段值 > 0 ? Number(((列.前段值 / 最大前段值) * 100).toFixed(2)) : 0}%`,
    },
  }));
});

const 職業分析副本列 = computed(() => {
  const 範圍代碼 = 職業分析目前範圍代碼.value;
  const 是職能範圍 = 職業分析目前範圍類型.value === "role";
  const 總數 = 轉為數字(取得來源範圍統計(全服統計資料.value, 範圍代碼)?.clear_count) || 0;

  return 全服統計副本列表.value
    .map((副本) => {
      const 統計 = 取得來源範圍統計(副本, 範圍代碼);
      const 數量 = 轉為數字(統計?.clear_count) || 0;
      const 範圍內佔比 = 總數 > 0 ? Number(((數量 / 總數) * 100).toFixed(2)) : 0;
      return {
        ...副本,
        數量,
        範圍內佔比,
        職業內佔比: 範圍內佔比,
        主要百分比文字: 是職能範圍 ? `職能分布 ${格式化百分比(範圍內佔比)}` : 格式化百分比(範圍內佔比),
        補充: 是職能範圍
          ? `副本內${職業分析目前範圍.value?.名稱 || "職能"}合計 ${格式化百分比(統計?.percentage)}`
          : `副本內佔比 ${格式化百分比(統計?.percentage)}`,
        職業分布列: 是職能範圍 ? 建立職業分析職能職業分布列(副本, 範圍代碼) : [],
      };
    })
    .filter((副本) => 副本.數量 > 0)
    .sort((前一個, 後一個) => {
      const 順序差 = 取得副本排序值(前一個.encounter_key) - 取得副本排序值(後一個.encounter_key);
      return 順序差 || 前一個.encounter_name.localeCompare(後一個.encounter_name, "zh-Hant-TW");
    });
});

const 職業分析伺服器列 = computed(() => {
  const 範圍代碼 = 職業分析目前範圍代碼.value;
  const 是職能範圍 = 職業分析目前範圍類型.value === "role";
  const 總數 = 轉為數字(取得來源範圍統計(全服統計資料.value, 範圍代碼)?.clear_count) || 0;

  return (全服統計資料.value?.server_stats || [])
    .map((伺服器) => {
      const 統計 = 取得來源範圍統計(伺服器, 範圍代碼);
      const 數量 = 轉為數字(統計?.clear_count) || 0;
      const 範圍內佔比 = 總數 > 0 ? Number(((數量 / 總數) * 100).toFixed(2)) : 0;
      return {
        server: 伺服器.server,
        數量,
        全職業佔比: 範圍內佔比,
        主要百分比文字: 是職能範圍 ? `職能落點 ${格式化百分比(範圍內佔比)}` : 格式化百分比(範圍內佔比),
        補充: 是職能範圍
          ? `伺服器內${職業分析目前範圍.value?.名稱 || "職能"}合計 ${格式化百分比(統計?.percentage)}`
          : `伺服器內佔比 ${格式化百分比(統計?.percentage)}`,
        職業分布列: 是職能範圍 ? 建立職業分析職能職業分布列(伺服器, 範圍代碼) : [],
      };
    })
    .filter((伺服器) => 伺服器.數量 > 0)
    .sort((前一個, 後一個) => 後一個.數量 - 前一個.數量 || 前一個.server.localeCompare(後一個.server, "zh-Hant-TW"));
});

const 職業分析概要 = computed(() => {
  const 範圍 = 職業分析目前範圍.value;
  const 統計 = 取得來源範圍統計(全服統計資料.value, 職業分析目前範圍代碼.value);
  if (!範圍 || !統計) {
    return [];
  }

  const 主要副本 = 職業分析副本列.value.slice().sort((前一個, 後一個) => 後一個.數量 - 前一個.數量)[0] || null;
  const 主要伺服器 = 職業分析伺服器列.value[0] || null;
  const 主要職業 = 職業分析職業選項.value
    .filter((職業) => 範圍.類型 !== "role" || 職業.role === 範圍.代碼)
    .slice()
    .sort((前一個, 後一個) => (後一個.clear_count || 0) - (前一個.clear_count || 0))[0] || null;

  if (範圍.類型 === "role") {
    return [
      { 標籤: "職能紀錄", 數值: 格式化整數(統計.clear_count) },
      { 標籤: "公開成績", 數值: 格式化整數(統計.entry_count) },
      { 標籤: "全職業佔比", 數值: 格式化百分比(統計.percentage) },
      { 標籤: "主要職業", 數值: 主要職業 ? `${顯示職業名稱(主要職業.job)} ${格式化百分比(主要職業.percentage)}` : "-" },
      { 標籤: "主要伺服器", 數值: 主要伺服器 ? `${主要伺服器.server} ${格式化百分比(主要伺服器.全職業佔比)}` : "-" },
    ];
  }

  return [
    { 標籤: "通關紀錄", 數值: 格式化整數(統計.clear_count) },
    { 標籤: "公開成績", 數值: 格式化整數(統計.entry_count) },
    { 標籤: "全職業佔比", 數值: 格式化百分比(統計.percentage) },
    { 標籤: "主要伺服器", 數值: 主要伺服器 ? `${主要伺服器.server} ${格式化百分比(主要伺服器.全職業佔比)}` : "-" },
    { 標籤: "主要副本", 數值: 主要副本 ? `${主要副本.encounter_name} ${格式化百分比(主要副本.職業內佔比)}` : "-" },
  ];
});

const 職業分析詳細 = computed(() => {
  const 職業 = 職業分析目前職業代碼.value;
  return (全服統計資料.value?.job_profiles || []).find((項目) => 項目.job === 職業) || null;
});

function 建立職業副本輸出項(副本) {
  const 指標統計 = 副本?.damage_profile?.rdps;
  if (!指標統計?.count) {
    return null;
  }

  return {
    key: 副本.encounter_key,
    名稱: 副本.encounter_name,
    分類: 副本.encounter_category || "副本",
    樣本數: 指標統計.count,
    中位數: 指標統計.median,
    上四分位: 指標統計.q3,
    最高值: 指標統計.max,
  };
}

const 職業分析副本輸出列 = computed(() => {
  const 詳細 = 職業分析詳細.value;
  if (!詳細) {
    return [];
  }

  const 列表 = (詳細.encounters || []).map(建立職業副本輸出項).filter(Boolean);
  const 最高中位數 = Math.max(...列表.map((項目) => 轉為數字(項目.中位數) || 0), 0);

  return 列表.map((項目) => ({
    ...項目,
    強度: 最高中位數 > 0 ? Number((((轉為數字(項目.中位數) || 0) / 最高中位數) * 100).toFixed(2)) : 0,
  }));
});

const 職業分析代表紀錄 = computed(() => {
  const 詳細 = 職業分析詳細.value;
  if (!詳細) {
    return [];
  }

  return [
    {
      標籤: "最高 rDPS",
      成績: 詳細.best_entry,
      主要數值: 格式化傷害數值(詳細.best_entry?.rdps),
      補充: 詳細.best_entry ? `${詳細.best_entry.character_name} @ ${詳細.best_entry.server}` : "-",
    },
    {
      標籤: "最速通關",
      成績: 詳細.fastest_entry,
      主要數值: 格式化通關時間(詳細.fastest_entry?.clear_time_seconds),
      補充: 詳細.fastest_entry ? `${詳細.fastest_entry.server || "未知伺服器"}・該職業公開紀錄` : "-",
    },
  ].filter((項目) => 項目.成績);
});

const 資料狀態列表 = computed(() => {
  const 副本列表 = 目前統計副本.value ? [目前統計副本.value] : 全服統計副本列表.value;

  return 副本列表.map((副本) => ({
    ...副本,
    有資料: (轉為數字(副本.character_count) || 0) > 0,
    狀態文字: (轉為數字(副本.character_count) || 0) > 0 ? "已收錄" : "待收集",
  }));
});

const 資料狀態分組 = computed(() => {
  const 分組索引 = new Map();

  for (const 分類 of 副本分類順序) {
    分組索引.set(分類, {
      分類,
      副本列表: [],
    });
  }

  for (const 副本 of 資料狀態列表.value) {
    const 分類 = 副本.encounter_category || "其他";
    if (!分組索引.has(分類)) {
      分組索引.set(分類, {
        分類,
        副本列表: [],
      });
    }
    分組索引.get(分類).副本列表.push(副本);
  }

  return Array.from(分組索引.values())
    .map((分組) => {
      const 總數 = 分組.副本列表.length;
      const 已收錄數 = 分組.副本列表.filter((副本) => 副本.有資料).length;
      return {
        ...分組,
        總數,
        已收錄數,
        收錄比例: 總數 > 0 ? Number(((已收錄數 / 總數) * 100).toFixed(2)) : 0,
      };
    })
    .filter((分組) => 分組.總數 > 0);
});

const 近期動態來源 = computed(() => 近期動態資料.value || {});

function 台灣日期字串轉時間(日期字串) {
  const 時間 = new Date(`${日期字串 || ""}T00:00:00+08:00`).getTime();
  return Number.isFinite(時間) ? 時間 : null;
}

function 時間轉台灣日期字串(時間) {
  if (!Number.isFinite(時間)) {
    return "";
  }
  return new Date(時間 + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
}

function 台灣日期字串加天數(日期字串, 天數) {
  const 時間 = 台灣日期字串轉時間(日期字串);
  return 時間 === null ? "" : 時間轉台灣日期字串(時間 + 天數 * 24 * 60 * 60 * 1000);
}

function 台灣日期相差天數(開始日期, 結束日期) {
  const 開始時間 = 台灣日期字串轉時間(開始日期);
  const 結束時間 = 台灣日期字串轉時間(結束日期);
  if (開始時間 === null || 結束時間 === null) {
    return 0;
  }
  return Math.round((結束時間 - 開始時間) / (24 * 60 * 60 * 1000));
}

function 台灣月份第一天(日期字串) {
  return /^\d{4}-\d{2}-\d{2}$/.test(日期字串 || "") ? `${日期字串.slice(0, 7)}-01` : "";
}

function 台灣月份加一個月(月份第一天) {
  const 年 = Number(月份第一天.slice(0, 4));
  const 月 = Number(月份第一天.slice(5, 7));
  if (!Number.isFinite(年) || !Number.isFinite(月)) {
    return "";
  }
  const 下一月 = 月 === 12 ? 1 : 月 + 1;
  const 下一年 = 月 === 12 ? 年 + 1 : 年;
  return `${下一年}-${String(下一月).padStart(2, "0")}-01`;
}

function 近期動態日誌月份標籤(日期字串) {
  return /^\d{4}-\d{2}/.test(日期字串 || "") ? 日期字串.slice(0, 7).replace("-", "/") : "";
}

function 近期動態日誌日期標籤(日期字串) {
  return 日期字串 ? 格式化紀錄日期(`${日期字串}T00:00:00+08:00`) : "-";
}

function 取近期動態日誌數值(點, 指標) {
  return 轉為數字(點?.[指標]) ?? 0;
}

function 建立近期動態日誌每日點(原始點列表, 指標, 開始日期, 結束日期) {
  const 點索引 = new Map((原始點列表 || []).map((點) => [點.date, 點]));
  const 每日點 = [];
  let 游標日期 = 開始日期;

  while (游標日期 && 游標日期 <= 結束日期) {
    const 原始點 = 點索引.get(游標日期);
    每日點.push({
      key: 游標日期,
      label: 近期動態日誌日期標籤(游標日期),
      start_date: 游標日期,
      end_date: 游標日期,
      count: 取近期動態日誌數值(原始點, 指標),
      unique_report_count: 取近期動態日誌數值(原始點, "unique_report_count"),
      unique_fight_count: 取近期動態日誌數值(原始點, "unique_fight_count"),
    });
    游標日期 = 台灣日期字串加天數(游標日期, 1);
  }

  return 每日點;
}

function 建立近期動態日誌月份刻度(開始日期, 結束日期) {
  const 總天數 = Math.max(台灣日期相差天數(開始日期, 結束日期), 0);
  const 刻度列表 = [];
  let 游標月份 = 台灣月份第一天(開始日期);

  while (游標月份 && 游標月份 <= 結束日期) {
    const 刻度日期 = 游標月份 < 開始日期 ? 開始日期 : 游標月份;
    const 位移天數 = 總天數 <= 0 ? 0 : 台灣日期相差天數(開始日期, 刻度日期);
    const x = 總天數 <= 0 ? 0 : (位移天數 / 總天數) * 100;
    const 位置 = Number(Math.min(Math.max(x, 0), 100).toFixed(2));
    刻度列表.push({
      key: 游標月份,
      label: 近期動態日誌月份標籤(游標月份),
      x: 位置,
      align: 位置 <= 6 ? "start" : 位置 >= 94 ? "end" : "center",
    });
    游標月份 = 台灣月份加一個月(游標月份);
  }

  return 刻度列表;
}

function 建立近期動態日誌時間標註(開始日期, 結束日期) {
  const 總天數 = Math.max(台灣日期相差天數(開始日期, 結束日期), 0);
  return activityLogTimelineAnnotations
    .filter((標註) => 標註.date >= 開始日期 && 標註.date <= 結束日期)
    .map((標註) => {
      const 位移天數 = 總天數 <= 0 ? 0 : 台灣日期相差天數(開始日期, 標註.date);
      const x = 總天數 <= 0 ? 50 : (位移天數 / 總天數) * 100;
      const 位置 = Number(Math.min(Math.max(x, 0), 100).toFixed(2));
      const classNames = [];
      if (標註.importance === "secondary") {
        classNames.push("近期日誌時間標註次要");
      }
      if (位置 <= 9) {
        classNames.push("近期日誌時間標註靠起點");
      } else if (位置 >= 91) {
        classNames.push("近期日誌時間標註靠終點");
      }
      return {
        key: `${標註.date}:${標註.title}`,
        date: 標註.date,
        title: 標註.title,
        detail: 標註.detail,
        importance: 標註.importance || "primary",
        class_names: classNames,
        x: 位置,
      };
    });
}

function 近期動態日誌分類色彩類別(分類) {
  return activityLogCategoryColorClasses.get(分類) || "近期日誌分類色彩其他";
}

function 排序近期動態日誌分類序列(分類系列列表) {
  const 分類順序索引 = new Map(副本分類順序.map((分類, index) => [分類, index]));
  return (Array.isArray(分類系列列表) ? 分類系列列表 : [])
    .filter((系列) => 系列?.category && Array.isArray(系列.points))
    .slice()
    .sort((前一個, 後一個) => {
      const 前一個順序 = 分類順序索引.get(前一個.category) ?? 副本分類順序.length;
      const 後一個順序 = 分類順序索引.get(後一個.category) ?? 副本分類順序.length;
      return 前一個順序 - 後一個順序 || String(前一個.category).localeCompare(String(後一個.category), "zh-Hant-TW");
    });
}

function 建立近期動態日誌分類堆疊(分類系列列表, 指標, 總量點列表, 繪圖最大值) {
  const 日期列表 = 總量點列表.map((點) => 點.key);
  const 分類列表 = 排序近期動態日誌分類序列(分類系列列表).map((系列) => {
    const 點索引 = new Map((系列.points || []).map((點) => [點.date, 點]));
    const 每日數值 = 日期列表.map((日期) => 取近期動態日誌數值(點索引.get(日期), 指標));
    return {
      category: 系列.category,
      label: 系列.label || 系列.category,
      color_class: 近期動態日誌分類色彩類別(系列.category),
      values: 每日數值,
      total_count: 每日數值.reduce((總和, 數值) => 總和 + 數值, 0),
      top: [],
      bottom: [],
    };
  });

  if (分類列表.length === 0 || 日期列表.length === 0) {
    return { layers: [], legend: [] };
  }

  總量點列表.forEach((總量點, index) => {
    const 分類總和 = 分類列表.reduce((總和, 分類) => 總和 + 分類.values[index], 0);
    let 累計高度值 = 0;

    for (const 分類 of 分類列表) {
      const 正規化高度值 = 分類總和 > 0 ? (總量點.count * 分類.values[index]) / 分類總和 : 0;
      const y0 = 44 - (累計高度值 / 繪圖最大值) * 34;
      累計高度值 += 正規化高度值;
      const y1 = 44 - (累計高度值 / 繪圖最大值) * 34;
      分類.bottom.push({ x: 總量點.x, y: Number(y0.toFixed(2)) });
      分類.top.push({ x: 總量點.x, y: Number(y1.toFixed(2)) });
    }
  });

  const 分類總數 = 分類列表.reduce((總和, 分類) => 總和 + 分類.total_count, 0);
  const layers = 分類列表
    .filter((分類) => 分類.total_count > 0)
    .map((分類) => {
      const 上緣 = 分類.top.map((點, index) => `${index === 0 ? "M" : "L"} ${點.x} ${點.y}`).join(" ");
      const 下緣 = 分類.bottom.slice().reverse().map((點) => `L ${點.x} ${點.y}`).join(" ");
      return {
        category: 分類.category,
        label: 分類.label,
        color_class: 分類.color_class,
        total_count: 分類.total_count,
        percentage: 分類總數 > 0 ? (分類.total_count / 分類總數) * 100 : 0,
        path: `${上緣} ${下緣} Z`,
      };
    });

  return {
    layers,
    legend: layers.map((分類) => ({
      category: 分類.category,
      label: 分類.label,
      color_class: 分類.color_class,
      value_text: 格式化整數(分類.total_count),
      percentage_text: 格式化百分比(分類.percentage),
    })),
  };
}

const 近期動態日誌來源 = computed(() => 近期動態來源.value.log_activity || {});

const 近期動態日誌副本選項 = computed(() => {
  const 系列列表 = Array.isArray(近期動態日誌來源.value.series) ? 近期動態日誌來源.value.series : [];
  return 系列列表
    .map((系列) => ({
      value: 系列.encounter_key,
      label: 系列.encounter_key === "all" ? "全部副本" : 系列.encounter_name || 系列.encounter_key,
      category: 系列.encounter_category || "",
    }))
    .filter((選項) => 選項.value);
});

const 近期動態日誌副本分組 = computed(() => {
  return 建立副本選單分組(近期動態日誌副本選項.value, {
    取鍵值: (選項) => 選項.value,
    取名稱: (選項) => 選項.label,
    取分類: (選項) => (選項.value === "all" ? "全部" : 選項.category),
    取零式量級: (選項) => 取得零式量級(選項, 選項.value),
  });
});

const 近期動態日誌指標選項 = computed(() => {
  const 指標列表 = Array.isArray(近期動態日誌來源.value.metrics) ? 近期動態日誌來源.value.metrics : [];
  return 指標列表.length > 0
    ? 指標列表
    : [
        { key: "unique_report_count", label: "Logs" },
        { key: "unique_fight_count", label: "通關場次" },
      ];
});

const 近期動態日誌有效副本鍵值 = computed(() => {
  return 近期動態日誌副本選項.value.some((選項) => 選項.value === 近期動態日誌副本鍵值.value)
    ? 近期動態日誌副本鍵值.value
    : "all";
});

const 近期動態日誌有效指標 = computed(() => {
  return 近期動態日誌指標選項.value.some((選項) => 選項.key === 近期動態日誌指標.value)
    ? 近期動態日誌指標.value
    : "unique_report_count";
});

const 近期動態日誌指標標籤 = computed(() => {
  return 近期動態日誌指標選項.value.find((選項) => 選項.key === 近期動態日誌有效指標.value)?.label || "Logs";
});

const 近期動態日誌副本選單文字 = computed(() => {
  return 近期動態日誌副本選項.value.find((選項) => 選項.value === 近期動態日誌有效副本鍵值.value)?.label || "全部副本";
});

const 近期動態日誌選取系列 = computed(() => {
  const 系列列表 = Array.isArray(近期動態日誌來源.value.series) ? 近期動態日誌來源.value.series : [];
  return 系列列表.find((系列) => 系列.encounter_key === 近期動態日誌有效副本鍵值.value) || 系列列表[0] || null;
});

const 顯示近期動態日誌自訂日期 = computed(() => 近期動態日誌時間範圍.value === "custom");

const 近期動態日誌日期範圍 = computed(() => {
  const 可用結束日期 = 近期動態日誌來源.value.available_end_date || "";
  const 可用開始日期 = 近期動態日誌來源.value.available_start_date || 可用結束日期;
  if (!可用結束日期) {
    return { start: "", end: "" };
  }

  if (近期動態日誌時間範圍.value === "custom") {
    const 自訂開始 = 近期動態日誌自訂開始日期.value || 可用開始日期;
    const 自訂結束 = 近期動態日誌自訂結束日期.value || 可用結束日期;
    return 自訂開始 <= 自訂結束
      ? { start: 自訂開始, end: 自訂結束 }
      : { start: 自訂結束, end: 自訂開始 };
  }

  if (近期動態日誌時間範圍.value === "all") {
    return { start: 可用開始日期, end: 可用結束日期 };
  }

  const 天數 = Math.max(1, 轉為數字(近期動態日誌時間範圍.value) ?? 近期動態日誌來源.value.default_window_days ?? 30);
  const 請求開始日期 = 台灣日期字串加天數(可用結束日期, -(天數 - 1));
  return {
    start: 請求開始日期 && 請求開始日期 < 可用開始日期 ? 可用開始日期 : 請求開始日期,
    end: 可用結束日期,
  };
});

const 近期動態日誌圖表資料 = computed(() => {
  const 系列 = 近期動態日誌選取系列.value;
  const 日期範圍 = 近期動態日誌日期範圍.value;
  if (!系列 || !日期範圍.start || !日期範圍.end) {
    return null;
  }

  const 區段點 = 建立近期動態日誌每日點(系列.points || [], 近期動態日誌有效指標.value, 日期範圍.start, 日期範圍.end);
  const 最大值 = Math.max(...區段點.map((點) => 點.count), 0);
  const 繪圖最大值 = Math.max(最大值, 1);
  const 點列表 = 區段點.map((點, index) => {
    const x = 區段點.length <= 1 ? 50 : (index / (區段點.length - 1)) * 100;
    const y = 44 - (點.count / 繪圖最大值) * 34;
    return {
      ...點,
      id: `${點.key}:${近期動態日誌有效指標.value}`,
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
    };
  });
  const 折線路徑 = 點列表.length > 0
    ? 點列表.map((點, index) => `${index === 0 ? "M" : "L"} ${點.x} ${點.y}`).join(" ")
    : "";
  const 面積路徑 = 點列表.length > 1 ? `${折線路徑} L 100 48 L 0 48 Z` : "";
  const 月份刻度 = 建立近期動態日誌月份刻度(日期範圍.start, 日期範圍.end);
  const 時間標註 = 建立近期動態日誌時間標註(日期範圍.start, 日期範圍.end);
  const 分類堆疊 = 系列.encounter_key === "all"
    ? 建立近期動態日誌分類堆疊(
        近期動態日誌來源.value.category_series,
        近期動態日誌有效指標.value,
        點列表,
        繪圖最大值,
      )
    : { layers: [], legend: [] };
  const 總數 = 區段點.reduce((總和, 點) => 總和 + 點.count, 0);
  const 高峰 = 區段點.slice().sort((前一個, 後一個) => 後一個.count - 前一個.count)[0] || null;
  const 最新 = 區段點.at(-1) || null;

  return {
    encounter_key: 系列.encounter_key,
    encounter_name: 系列.encounter_name,
    metric: 近期動態日誌有效指標.value,
    metric_label: 近期動態日誌指標標籤.value,
    start_date: 日期範圍.start,
    end_date: 日期範圍.end,
    total_count: 總數,
    max_count: 最大值,
    latest_count: 最新?.count ?? 0,
    peak: 高峰,
    line_path: 折線路徑,
    area_path: 面積路徑,
    points: 點列表,
    month_ticks: 月份刻度,
    annotations: 時間標註,
    category_layers: 分類堆疊.layers,
    category_legend: 分類堆疊.legend,
  };
});

const 近期動態日誌摘要 = computed(() => {
  const 圖表 = 近期動態日誌圖表資料.value;
  if (!圖表) {
    return [];
  }

  return [
    { 標籤: "總數", 數值: 格式化整數(圖表.total_count) },
    { 標籤: "高峰", 數值: 圖表.peak ? `${格式化整數(圖表.peak.count)}・${圖表.peak.label}` : "-" },
    { 標籤: "最新日期", 數值: 格式化整數(圖表.latest_count) },
  ];
});

const 近期動態日誌提示資料 = computed(() => {
  const 圖表 = 近期動態日誌圖表資料.value;
  const 目前點 = 近期動態日誌提示點.value;
  if (!圖表 || !目前點) {
    return null;
  }

  const 圖表點 = 圖表.points.find((點) => 點.id === 目前點.id);
  if (!圖表點) {
    return null;
  }

  const 水平位置 = Math.min(Math.max(圖表點.x, 8), 92);
  const 垂直百分比 = (圖表點.y / 52) * 100;
  const 顯示在下方 = 圖表點.y < 17;

  return {
    ...圖表點,
    metric_label: 圖表.metric_label,
    value_text: 格式化整數(圖表點.count),
    style: {
      left: `${水平位置}%`,
      top: `${垂直百分比}%`,
      "--近期日誌提示位移Y": 顯示在下方 ? "14px" : "calc(-100% - 12px)",
    },
  };
});

function 顯示近期動態日誌提示(點) {
  if (!點) {
    return;
  }
  if (近期動態日誌提示鎖定.value) {
    return;
  }
  近期動態日誌提示點.value = 點;
}

function 隱藏近期動態日誌提示() {
  if (!近期動態日誌提示鎖定.value) {
    近期動態日誌提示點.value = null;
  }
}

function 固定近期動態日誌提示(點) {
  if (!點) {
    return;
  }
  const 同一點 = 近期動態日誌提示鎖定.value && 近期動態日誌提示點.value?.id === 點.id;
  近期動態日誌提示點.value = 同一點 ? null : 點;
  近期動態日誌提示鎖定.value = !同一點;
}

function 清除近期動態日誌提示() {
  近期動態日誌提示點.value = null;
  近期動態日誌提示鎖定.value = false;
}

watch(近期動態日誌圖表資料, () => {
  if (近期動態日誌提示點.value && !近期動態日誌提示資料.value) {
    清除近期動態日誌提示();
  }
});

const 近期動態日誌範圍文字 = computed(() => {
  const 圖表 = 近期動態日誌圖表資料.value;
  if (!圖表) {
    return "尚無 Logs 趨勢資料";
  }

  return `${近期動態日誌日期標籤(圖表.start_date)} 至 ${近期動態日誌日期標籤(圖表.end_date)}`;
});

const 近期動態基準時間 = computed(() => {
  const 動態基準時間 = new Date(近期動態來源.value.baseline_at_iso || 0).getTime();
  if (Number.isFinite(動態基準時間) && 動態基準時間 > 0) {
    return 動態基準時間;
  }

  const 使用者時間 = 使用者索引列表.value
    .map((使用者) => new Date(使用者.last_recorded_at_iso || 0).getTime())
    .filter(Number.isFinite)
    .sort((前一個, 後一個) => 後一個 - 前一個)[0];
  const 索引時間 = new Date(使用者索引.value?.rankings_updated_at_iso || 0).getTime();
  return 使用者時間 || (Number.isNaN(索引時間) ? Date.now() : 索引時間);
});

const 近期動態最新成績列表 = computed(() => {
  const 新版清單 = Array.isArray(近期動態來源.value.recent_entries) ? 近期動態來源.value.recent_entries : [];
  if (新版清單.length > 0) {
    return 新版清單.slice(0, 24);
  }

  return 使用者索引列表.value
    .filter((使用者) => 使用者.last_recorded_at_iso)
    .slice()
    .sort((前一個, 後一個) => {
      const 時間差 = new Date(後一個.last_recorded_at_iso || 0).getTime() - new Date(前一個.last_recorded_at_iso || 0).getTime();
      return 時間差 || (後一個.best_rdps || 0) - (前一個.best_rdps || 0);
    })
    .slice(0, 24)
    .map((使用者) => ({
      character_name: 使用者.character_name,
      server: 取得使用者主要伺服器(使用者),
      rdps: 使用者.best_rdps,
      recorded_at_iso: 使用者.last_recorded_at_iso,
      encounter_name: `${格式化整數(使用者.encounter_count)} 副本`,
      job: "",
    }));
});

const 近期刷新紀錄列表 = computed(() => {
  return Array.isArray(近期動態來源.value.personal_bests) ? 近期動態來源.value.personal_bests.slice(0, 12) : [];
});

const 近期新角色列表 = computed(() => {
  return Array.isArray(近期動態來源.value.new_characters) ? 近期動態來源.value.new_characters.slice(0, 12) : [];
});

const 近期伺服器活躍列表 = computed(() => {
  return Array.isArray(近期動態來源.value.server_activity) ? 近期動態來源.value.server_activity.slice(0, 7) : [];
});

const 近期副本活躍列表 = computed(() => {
  return Array.isArray(近期動態來源.value.encounter_activity) ? 近期動態來源.value.encounter_activity.slice(0, 8) : [];
});

const 近期動態角色列表 = computed(() => 近期動態最新成績列表.value);

const 近期動態概要 = computed(() => {
  const 動態摘要 = 近期動態來源.value.summary;
  if (動態摘要) {
    return [
      { 標籤: `近 ${近期動態來源.value.window_days || 7} 天紀錄`, 數值: 格式化整數(動態摘要.recent_entry_count) },
      { 標籤: "刷新個人最佳", 數值: 格式化整數(動態摘要.personal_best_count) },
      { 標籤: "新收錄玩家", 數值: 格式化整數(動態摘要.new_character_count) },
      { 標籤: "最活躍伺服器", 數值: 動態摘要.top_server?.server || "-" },
    ];
  }

  const 七天前 = 近期動態基準時間.value - 7 * 24 * 60 * 60 * 1000;
  const 近七天角色數 = 使用者索引列表.value.filter((使用者) => {
    const 時間 = new Date(使用者.last_recorded_at_iso || 0).getTime();
    return Number.isFinite(時間) && 時間 >= 七天前;
  }).length;
  const 最新角色 = 近期動態最新成績列表.value[0] || null;

  return [
    { 標籤: "收錄玩家", 數值: 格式化整數(使用者索引.value?.total_users || 使用者索引列表.value.length) },
    { 標籤: "近七天活躍", 數值: 格式化整數(近七天角色數) },
    { 標籤: "最新玩家", 數值: 最新角色?.character_name || "-" },
    { 標籤: "最新紀錄", 數值: 格式化紀錄時間(最新角色?.recorded_at_iso || 最新角色?.last_recorded_at_iso) },
  ];
});

const 蜂蜂粉絲榜來源 = computed(() => 蜂蜂粉絲榜資料.value || {});

const 頭號粉絲列表 = computed(() => {
  return Array.isArray(蜂蜂粉絲榜來源.value.top_fans) ? 蜂蜂粉絲榜來源.value.top_fans.slice(0, 50) : [];
});

const 最新粉絲紀錄列表 = computed(() => {
  return Array.isArray(蜂蜂粉絲榜來源.value.latest_records) ? 蜂蜂粉絲榜來源.value.latest_records.slice(0, 5) : [];
});

const 最新加入粉絲列表 = computed(() => {
  return Array.isArray(蜂蜂粉絲榜來源.value.latest_fans) ? 蜂蜂粉絲榜來源.value.latest_fans.slice(0, 16) : [];
});

const 蜂蜂粉絲榜概要 = computed(() => {
  const summary = 蜂蜂粉絲榜來源.value.summary || {};
  const 榜單天數 = summary.leaderboard_window_days || 蜂蜂粉絲榜來源.value.leaderboard_window?.days || 7;

  return [
    { 標籤: `近 ${榜單天數} 天吃心心`, 數值: 格式化整數(summary.total_event_count) },
    { 標籤: "本期粉絲", 數值: 格式化整數(summary.fan_count) },
    { 標籤: "歷史紀錄", 數值: 格式化整數(summary.historical_total_event_count ?? summary.total_event_count) },
  ];
});

function 蜂蜂粉絲雜湊(文字) {
  return Array.from(String(文字 || "")).reduce((總和, 字元) => (總和 * 31 + 字元.charCodeAt(0)) % 1000003, 17);
}

const 蜂蜂觀眾粉絲列表 = computed(() => {
  const 候選 = [...頭號粉絲列表.value, ...最新加入粉絲列表.value];
  const 已加入 = new Set();
  const 唯一粉絲 = [];

  for (const 粉絲 of 候選) {
    const id = 粉絲?.id || `${粉絲?.character_name || ""}@${粉絲?.server || ""}`;
    if (!粉絲?.character_name || 已加入.has(id)) {
      continue;
    }
    已加入.add(id);
    唯一粉絲.push(粉絲);
  }

  const 抽樣粉絲 = 唯一粉絲
    .map((粉絲) => ({ 粉絲, 排序值: 蜂蜂粉絲雜湊(`${粉絲.id}:${蜂蜂粉絲榜來源.value.generated_at_iso || ""}`) }))
    .sort((左, 右) => 左.排序值 - 右.排序值)
    .slice(0, 84);
  const 欄數 = 12;
  const 列數 = Math.max(1, Math.ceil(抽樣粉絲.length / 欄數));

  return 抽樣粉絲.map(({ 粉絲, 排序值 }, index) => {
    const 欄 = index % 欄數;
    const 列 = Math.floor(index / 欄數);
    const 基礎x = 欄數 > 1 ? (欄 / (欄數 - 1)) * 100 : 50;
    const 基礎y = 列數 > 1 ? (列 / (列數 - 1)) * 100 : 50;
    const 偏移x = ((排序值 >> 4) % 7) - 3;
    const 偏移y = ((排序值 >> 8) % 9) - 4;

    return {
      id: `audience:${粉絲.id}`,
      character_name: 粉絲.character_name,
      style: {
        "--觀眾x": `${Math.max(0, Math.min(100, 基礎x + 偏移x)).toFixed(1)}%`,
        "--觀眾y": `${Math.max(0, Math.min(100, 基礎y + 偏移y)).toFixed(1)}%`,
        "--觀眾大小": (0.78 + ((排序值 >> 5) % 34) / 100).toFixed(2),
        "--觀眾延遲": `${-1 * (((排序值 >> 7) % 90) / 10).toFixed(1)}s`,
        "--觀眾週期": `${(5.8 + ((排序值 >> 11) % 38) / 10).toFixed(1)}s`,
        "--觀眾層": String(10 + index),
      },
    };
  });
});

function 建立粉絲榜愛心陰影(圖層索引, 數量) {
  let seed = 7919 + 圖層索引 * 104729;
  const 陰影 = [];

  for (let index = 0; index < 數量; index += 1) {
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    const x = ((seed % 10800) / 100 - 4).toFixed(2);
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    const y = ((seed % 10800) / 100 - 4).toFixed(2);
    seed = (seed * 1664525 + 1013904223) % 4294967296;
    const 模糊 = ((seed % 3) / 2).toFixed(1);
    const 透明度 = (0.44 + (seed % 18) / 100).toFixed(2);
    陰影.push(`${x}vw ${y}vh ${模糊}px rgba(255, 121, 180, ${透明度})`);
  }

  return 陰影.join(", ");
}

const 粉絲榜愛心列表 = Array.from({ length: 10 }, (_, index) => ({
  id: `honey-heart-layer:${index}`,
  style: {
    "--愛心尺寸": `${18 + ((index * 7) % 18)}px`,
    "--愛心陰影": 建立粉絲榜愛心陰影(index, 84),
    "--愛心透明度": (0.3 - index * 0.012).toFixed(2),
    "--愛心延遲": `${-1 * (index * 2.4).toFixed(1)}s`,
    "--愛心週期": `${(9.5 + index * 1.6).toFixed(1)}s`,
  },
}));

const 隊伍榜副本列表 = computed(() => {
  return Array.isArray(隊伍榜資料.value?.encounters) ? 隊伍榜資料.value.encounters : [];
});

const 隊伍榜副本分組 = computed(() => {
  return 建立副本選單分組(隊伍榜副本列表.value, {
    取鍵值: (副本) => 副本.encounter_key,
    取名稱: (副本) => 副本.encounter_name,
    取分類: (副本) => 副本.encounter_category,
    取零式量級: (副本) => 取得零式量級(副本, 副本.encounter_key),
  });
});

const 目前隊伍榜副本 = computed(() => {
  return 隊伍榜副本列表.value.find((副本) => 副本.encounter_key === 隊伍榜副本鍵值.value) || null;
});

const 隊伍榜副本選單文字 = computed(() => 目前隊伍榜副本.value?.encounter_name || "選擇副本");

const 顯示隊伍榜版本篩選 = computed(() => 副本支援版本篩選(目前隊伍榜副本.value));
const 有效隊伍榜版本範圍 = computed(() => 取得有效版本紀錄範圍(目前隊伍榜副本.value, 隊伍榜版本範圍.value));
const 目前隊伍榜來源 = computed(() => 取得版本切片來源(目前隊伍榜副本.value, 有效隊伍榜版本範圍.value));

const 隊伍榜列 = computed(() => {
  return (目前隊伍榜來源.value?.records || []).map((紀錄, 索引) => ({
    ...紀錄,
    顯示排名: 索引 + 1,
  }));
});

const 隊伍榜概要 = computed(() => {
  const 副本 = 目前隊伍榜來源.value || 目前隊伍榜副本.value;
  const 最速 = 隊伍榜列.value[0] || null;

  return [
    {
      標籤: "隊伍紀錄",
      數值: 格式化整數(副本 ? 副本.record_count : 隊伍榜資料.value?.total_team_record_count),
    },
    {
      標籤: "副本數",
      數值: 格式化整數(隊伍榜資料.value?.encounter_count),
    },
    {
      標籤: "最速通關",
      數值: 格式化通關時間(最速?.clear_time_seconds),
    },
    {
      標籤: "最速副本",
      數值: 最速?.encounter_name || 副本?.encounter_name || "-",
    },
  ];
});

const 伺服器對比伺服器列表 = computed(() => {
  return Array.isArray(伺服器對比資料.value?.servers) ? 伺服器對比資料.value.servers : [];
});

const 伺服器對比選項 = computed(() => 伺服器對比伺服器列表.value.map((項目) => 項目.server).filter(Boolean));

const 伺服器對比左資料 = computed(() => {
  return 伺服器對比伺服器列表.value.find((項目) => 項目.server === 伺服器對比左伺服器.value) || null;
});

const 伺服器對比右資料 = computed(() => {
  return 伺服器對比伺服器列表.value.find((項目) => 項目.server === 伺服器對比右伺服器.value) || null;
});

const 伺服器對比已完成 = computed(() => Boolean(伺服器對比左資料.value && 伺服器對比右資料.value));

function 判斷對比勝方(左值, 右值, 越低越好 = false) {
  const 左數值 = 轉為數字(左值);
  const 右數值 = 轉為數字(右值);
  if (左數值 === null || 右數值 === null || 左數值 === 右數值) {
    return "平手";
  }
  const 左勝 = 越低越好 ? 左數值 < 右數值 : 左數值 > 右數值;
  return 左勝 ? "left" : "right";
}

function 建立伺服器對比指標({ 標籤, 左值, 右值, 格式化 = 格式化整數, 越低越好 = false }) {
  const 勝方 = 判斷對比勝方(左值, 右值, 越低越好);
  return {
    標籤,
    左值,
    右值,
    左文字: 格式化(左值),
    右文字: 格式化(右值),
    勝方,
  };
}

const 伺服器對比概要 = computed(() => {
  const 左 = 伺服器對比左資料.value;
  const 右 = 伺服器對比右資料.value;
  if (!左 || !右) {
    return [];
  }

  const 指標列表 = [
    建立伺服器對比指標({ 標籤: "收錄玩家", 左值: 左.unique_player_count, 右值: 右.unique_player_count }),
    建立伺服器對比指標({ 標籤: "副本通關", 左值: 左.encounter_clear_count, 右值: 右.encounter_clear_count }),
    建立伺服器對比指標({ 標籤: "職業紀錄", 左值: 左.job_record_count, 右值: 右.job_record_count }),
    建立伺服器對比指標({
      標籤: "rDPS 中位",
      左值: 左.rdps_stats?.median,
      右值: 右.rdps_stats?.median,
      格式化: 格式化傷害數值,
    }),
    建立伺服器對比指標({
      標籤: "最快通關",
      左值: 左.fastest_entry?.clear_time_seconds,
      右值: 右.fastest_entry?.clear_time_seconds,
      格式化: 格式化通關時間,
      越低越好: true,
    }),
  ];

  if (顯示Gcd覆蓋率) {
    指標列表.push(建立伺服器對比指標({
      標籤: "最速紀錄 GCD",
      左值: 左.fastest_entry?.gcd_coverage?.percent,
      右值: 右.fastest_entry?.gcd_coverage?.percent,
      格式化: 格式化Gcd覆蓋率,
    }));
  }

  return 指標列表;
});

const 伺服器對比職能列 = computed(() => {
  const 左 = 伺服器對比左資料.value;
  const 右 = 伺服器對比右資料.value;
  if (!左 || !右) {
    return [];
  }

  return 職業群組設定
    .map((群組) => {
      const 左職能 = (左.role_stats || []).find((項目) => 項目.role === 群組.代碼);
      const 右職能 = (右.role_stats || []).find((項目) => 項目.role === 群組.代碼);
      const 左比例 = 轉為數字(左職能?.percentage) || 0;
      const 右比例 = 轉為數字(右職能?.percentage) || 0;
      return {
        role: 群組.代碼,
        名稱: 群組.名稱,
        色彩: 群組.色彩,
        左數量: 轉為數字(左職能?.clear_count) || 0,
        右數量: 轉為數字(右職能?.clear_count) || 0,
        左比例,
        右比例,
        勝方: 判斷對比勝方(左比例, 右比例),
      };
    })
    .filter((項目) => 項目.左數量 > 0 || 項目.右數量 > 0);
});

function 建立伺服器職業亮點(伺服器資料) {
  return (伺服器資料?.job_stats || []).slice(0, 5).map((職業) => ({
    ...職業,
    名稱: 顯示職業名稱(職業.job),
    色彩: 職業代碼色彩(職業.job),
  }));
}

const 伺服器對比職業亮點 = computed(() => ({
  left: 建立伺服器職業亮點(伺服器對比左資料.value),
  right: 建立伺服器職業亮點(伺服器對比右資料.value),
}));

const 伺服器對比副本列 = computed(() => {
  const 左 = 伺服器對比左資料.value;
  const 右 = 伺服器對比右資料.value;
  if (!左 || !右) {
    return [];
  }

  const 副本索引 = new Map();
  for (const 副本 of 左.encounters || []) {
    副本索引.set(副本.encounter_key, { encounter_key: 副本.encounter_key, encounter_name: 副本.encounter_name, encounter_category: 副本.encounter_category, left: 副本, right: null });
  }
  for (const 副本 of 右.encounters || []) {
    const 目前 = 副本索引.get(副本.encounter_key) || {
      encounter_key: 副本.encounter_key,
      encounter_name: 副本.encounter_name,
      encounter_category: 副本.encounter_category,
      left: null,
      right: null,
    };
    目前.right = 副本;
    副本索引.set(副本.encounter_key, 目前);
  }

  return Array.from(副本索引.values()).sort((前一個, 後一個) => {
    const 順序差 = 取得副本排序值(前一個.encounter_key) - 取得副本排序值(後一個.encounter_key);
    return 順序差 || 前一個.encounter_name.localeCompare(後一個.encounter_name, "zh-Hant-TW");
  });
});

function 取得成績職業總數(成績) {
  if (!成績?.encounter_key || !成績?.job) {
    return null;
  }

  const 副本 = (全服統計資料.value?.encounters || []).find((項目) => 項目.encounter_key === 成績.encounter_key);
  const 統計來源 = 副本支援版本篩選(副本) && !成績.is_obsolete_record ? 取得版本切片來源(副本, "valid") : 副本;
  const 職業 = (統計來源?.job_stats || []).find((項目) => 項目.job === 成績.job);
  return 轉為數字(職業?.clear_count);
}

function 取得最高伺服器(副本) {
  const 伺服器列表 = 副本?.server_stats || [];
  const 加總 = 伺服器列表.reduce((總數, 項目) => 總數 + 取得統計計數(項目), 0);
  return 伺服器列表
    .map((項目) => {
      const 顯示數量 = 取得統計計數(項目);
      return {
        ...項目,
        顯示數量,
        顯示比例: 加總 > 0 ? Number(((顯示數量 / 加總) * 100).toFixed(2)) : 0,
      };
    })
    .filter((項目) => 項目.顯示數量 > 0)
    .sort((前一個, 後一個) => 後一個.顯示數量 - 前一個.顯示數量 || 前一個.server.localeCompare(後一個.server, "zh-Hant-TW"))[0];
}

function 取得最高職業(統計項目) {
  const 範圍類型 = 職業範圍類型(統計職業範圍.value);
  const 職業列表 = (統計項目?.job_stats || []).filter((項目) => {
    if (範圍類型 === "role") {
      return 項目.role === 統計職業範圍.value;
    }
    if (範圍類型 === "job") {
      return 項目.job === 統計職業範圍.value;
    }
    return true;
  });

  return 職業列表.sort((前一個, 後一個) => 後一個.clear_count - 前一個.clear_count || 前一個.job.localeCompare(後一個.job, "zh-Hant-TW"))[0];
}

const 副本通關概覽 = computed(() => {
  const 總範圍來源 = 統計伺服器篩選.value
    ? (全服統計資料.value?.server_stats || []).find((項目) => 項目.server === 統計伺服器篩選.value)
    : 全服統計資料.value;
  const 分母 = 取得統計計數(總範圍來源);

  return 全服統計副本列表.value
    .map((副本) => {
      const 來源 = 統計伺服器篩選.value
        ? (副本.server_stats || []).find((項目) => 項目.server === 統計伺服器篩選.value)
        : 副本;
      const 顯示數量 = 取得統計計數(來源);
      const 顯示比例 = 分母 > 0 ? Number(((顯示數量 / 分母) * 100).toFixed(2)) : 0;
      const 最高伺服器 = 統計伺服器篩選.value ? null : 取得最高伺服器(副本);
      const 最高職業 = 取得最高職業(來源);

      return {
        ...副本,
        顯示數量,
        顯示比例,
        最高伺服器,
        最高職業,
      };
    })
    .filter((副本) => 副本.顯示數量 > 0);
});

function 零式副本排序值(副本) {
  const 清單索引 = 副本清單.value.findIndex((項目) => 項目.key === 副本.encounter_key);
  if (清單索引 >= 0) {
    return 清單索引;
  }

  const 層數 = String(副本.encounter_key || 副本.encounter_name || "").match(/m(\d+)s/i);
  return 層數 ? Number(層數[1]) : Number.MAX_SAFE_INTEGER;
}

function 取得零式層級文字(副本, 索引) {
  const 名稱層數 = String(副本.encounter_name || "").match(/M\d+S/i);
  if (名稱層數) {
    return 名稱層數[0].toUpperCase();
  }

  const 鍵值層數 = String(副本.encounter_key || "").match(/m\d+s/i);
  if (鍵值層數) {
    return 鍵值層數[0].toUpperCase();
  }

  return `第 ${索引 + 1} 層`;
}

function 取得副本統計篩選來源(副本) {
  if (!統計伺服器篩選.value) {
    return 副本;
  }

  return (副本?.server_stats || []).find((項目) => 項目.server === 統計伺服器篩選.value) || null;
}

const 零式漏斗單位 = computed(() => {
  return 職業範圍類型(統計職業範圍.value) === "all" ? "人" : "紀錄";
});

const 零式漏斗條件文字 = computed(() => {
  return `${統計伺服器文字.value}・${取得職業範圍文字()}`;
});

const 零式進度漏斗 = computed(() => {
  const 零式副本列表 = 全服統計副本列表.value
    .filter((副本) => 副本.encounter_category === "零式")
    .sort((前一個, 後一個) => {
      const 順序差 = 零式副本排序值(前一個) - 零式副本排序值(後一個);
      return 順序差 || String(前一個.encounter_name || "").localeCompare(String(後一個.encounter_name || ""), "zh-Hant-TW");
    });

  const 基準數量 = 取得統計計數(取得副本統計篩選來源(零式副本列表[0]));
  let 上一層數量 = null;

  return 零式副本列表
    .map((副本, 索引) => {
      const 來源 = 取得副本統計篩選來源(副本);
      const 顯示數量 = 取得統計計數(來源);
      const 相對首層比例 = 基準數量 > 0 ? Number(((顯示數量 / 基準數量) * 100).toFixed(2)) : 0;
      const 上一層比例 =
        上一層數量 === null ? 100 : 上一層數量 > 0 ? Number(((顯示數量 / 上一層數量) * 100).toFixed(2)) : 0;
      const 較上一層差異 = 上一層數量 === null ? 0 : 顯示數量 - 上一層數量;
      上一層數量 = 顯示數量;

      return {
        ...副本,
        索引,
        層級文字: 取得零式層級文字(副本, 索引),
        顯示數量,
        相對首層比例,
        上一層比例,
        較上一層差異,
      };
    })
    .filter((項目) => 項目.顯示數量 > 0);
});

const 更新時間文字 = computed(() => {
  if (頁面模式.value === "user") {
    const 更新時間 = 使用者索引.value?.rankings_updated_at_iso || 使用者資料.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "個人成績單資料";
  }

  if (頁面模式.value === "stats") {
    const 更新時間 = 全服統計資料.value?.rankings_updated_at_iso || 全服統計資料.value?.generated_at_iso;
    return 更新時間 ? `統計更新時間 ${格式化紀錄時間(更新時間)}` : "全服統計資料";
  }

  if (頁面模式.value === "compare") {
    const 更新時間 = 使用者索引.value?.rankings_updated_at_iso || 比較角色左資料.value?.generated_at_iso || 比較角色右資料.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "玩家比較資料";
  }

  if (頁面模式.value === "jobs") {
    const 更新時間 = 全服統計資料.value?.rankings_updated_at_iso || 全服統計資料.value?.generated_at_iso;
    return 更新時間 ? `統計更新時間 ${格式化紀錄時間(更新時間)}` : "職業分析資料";
  }

  if (頁面模式.value === "activity") {
    const 更新時間 = 近期動態資料.value?.rankings_updated_at_iso || 近期動態資料.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "近期動態資料";
  }

  if (頁面模式.value === "teams") {
    const 更新時間 = 隊伍榜資料.value?.rankings_updated_at_iso || 隊伍榜資料.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "隊伍榜資料";
  }

  if (頁面模式.value === "servers") {
    const 更新時間 = 伺服器對比資料.value?.rankings_updated_at_iso || 伺服器對比資料.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "伺服器對比資料";
  }

  if (頁面模式.value === "faq" || 頁面模式.value === "logs") {
    return "常見問題";
  }

  if (頁面模式.value === "honey-fans") {
    const 更新時間 = 蜂蜂粉絲榜資料.value?.source_updated_at_iso || 蜂蜂粉絲榜資料.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "Honey B. Lovely 粉絲榜資料";
  }

  const 更新時間 = 排行榜資料.value?.updated_at_iso;
  return 更新時間 ? `更新時間 ${格式化紀錄時間(更新時間)}` : "尚未取得更新時間";
});

const 頁面副標 = computed(() => {
  if (頁面模式.value === "user") {
    return "Final Fantasy XIV 繁中服・個人成績單";
  }

  if (頁面模式.value === "stats") {
    return "Final Fantasy XIV 繁中服・全服統計";
  }

  if (頁面模式.value === "compare") {
    return "Final Fantasy XIV 繁中服・玩家比較";
  }

  if (頁面模式.value === "jobs") {
    return "Final Fantasy XIV 繁中服・職業分析";
  }

  if (頁面模式.value === "activity") {
    return "Final Fantasy XIV 繁中服・近期動態";
  }

  if (頁面模式.value === "teams") {
    return "Final Fantasy XIV 繁中服・隊伍榜";
  }

  if (頁面模式.value === "servers") {
    return "Final Fantasy XIV 繁中服・伺服器對比";
  }

  if (頁面模式.value === "faq" || 頁面模式.value === "logs") {
    return "Final Fantasy XIV 繁中服・常見問題";
  }

  if (頁面模式.value === "honey-fans") {
    return "Final Fantasy XIV 繁中服・趣味榜單";
  }

  return 目前副本.value?.category ? `Final Fantasy XIV 繁中服・${目前副本.value.category}` : "Final Fantasy XIV 繁中服";
});

const 頁面標題 = computed(() => {
  if (頁面模式.value === "user") {
    return 使用者資料.value?.character_name ? `${使用者資料.value.character_name} 個人成績單` : "個人成績單";
  }

  if (頁面模式.value === "stats") {
    return 目前統計副本.value ? `${目前統計副本.value.encounter_name} 全服統計` : "全服統計";
  }

  if (頁面模式.value === "compare") {
    if (角色比較已完成.value) {
      return `${比較角色左.value.character_name} vs ${比較角色右.value.character_name}`;
    }
    return "玩家比較";
  }

  if (頁面模式.value === "jobs") {
    return 職業分析目前範圍.value ? `${職業分析目前範圍.value.名稱} 職業分析` : "職業分析";
  }

  if (頁面模式.value === "activity") {
    return "近期動態";
  }

  if (頁面模式.value === "teams") {
    return 目前隊伍榜副本.value ? `${目前隊伍榜副本.value.encounter_name} 隊伍榜` : "隊伍榜";
  }

  if (頁面模式.value === "servers") {
    return 伺服器對比已完成.value ? `${伺服器對比左資料.value.server} vs ${伺服器對比右資料.value.server}` : "伺服器對比";
  }

  if (頁面模式.value === "faq" || 頁面模式.value === "logs") {
    return "常見問題";
  }

  if (頁面模式.value === "honey-fans") {
    return "Honey B. Lovely 粉絲榜";
  }

  return 目前副本.value?.name ? `${目前副本.value.name} 排行榜` : "排行榜";
});

function 分享數量文字(數值, 單位) {
  const 數字 = 轉為數字(數值);
  return 數字 && 數字 > 0 ? `${格式化整數(數字)} ${單位}` : "";
}

function 排行榜分享條件文字() {
  const 條件 = [];
  if (伺服器篩選.value) {
    條件.push(`${伺服器篩選.value}伺服器`);
  }
  if (職業篩選.value) {
    條件.push(顯示職業名稱(職業篩選.value));
  } else if (目前職業類型.value?.名稱) {
    條件.push(目前職業類型.value.名稱);
  }
  if (搜尋關鍵字.value.trim()) {
    條件.push(`關鍵字「${搜尋關鍵字.value.trim()}」`);
  }
  if (顯示排行榜版本篩選.value && 有效排行榜版本範圍.value !== "all") {
    條件.push(取得版本紀錄範圍文字(有效排行榜版本範圍.value));
  }

  return 條件.length > 0 ? `（${條件.join("、")}）` : "";
}

function 全服統計分享描述() {
  const 統計 = 全服統計資料.value;
  const 版本文字 = 顯示統計版本篩選.value ? `（${取得版本紀錄範圍文字(有效統計版本範圍.value)}）` : "";
  const 範圍 = `${統計範圍文字.value}${版本文字}`;
  const 角色數 = 分享數量文字(統計?.total_character_count, "名玩家");
  const 成績數 = 分享數量文字(統計?.total_entry_count, "筆公開成績");
  const 基礎 = [角色數, 成績數].filter(Boolean).join("、");
  const 篩選 = `${統計伺服器文字.value}、${取得職業範圍文字()}、${傷害比較指標標籤.value}`;

  return 正規化分享描述(
    `${範圍}全服統計${基礎 ? `，目前收錄 ${基礎}` : ""}，可查看伺服器分布、職業分布、零式進度與 ${篩選} 分析。`,
  );
}

function 個人成績單分享描述() {
  if (!使用者資料.value) {
    return "搜尋 FFXIV 繁中服玩家個人成績單，查看各副本最佳 rDPS、aDPS、分位表現、歷史紀錄與常同場隊友。";
  }

  const 伺服器文字 = 使用者伺服器篩選.value ? `（${使用者伺服器篩選.value}）` : "";
  const 副本數 = 分享數量文字(使用者統計.value.副本數, "個副本");
  const 成績數 = 分享數量文字(使用者統計.value.公開成績數, "筆公開成績");
  const 代表職業 = 使用者統計.value.代表成績?.job ? 顯示職業名稱(使用者統計.value.代表成績.job) : "";
  const 代表描述 = 代表職業 ? `，代表職業為 ${代表職業}` : "";

  return 正規化分享描述(
    `${使用者資料.value.character_name}${伺服器文字}的 FFXIV 繁中服個人成績單，收錄 ${[副本數, 成績數].filter(Boolean).join("、") || "公開成績"}${代表描述}，並整理分位表現與常同場隊友。`,
  );
}

function 玩家比較分享描述() {
  if (角色比較已完成.value) {
    const 版本文字 = 顯示比較版本篩選.value ? `、${取得版本紀錄範圍文字(有效比較版本範圍.value)}` : "";
    return 正規化分享描述(
      `比較 ${比較角色左.value.character_name} 與 ${比較角色右.value.character_name} 在${比較範圍文字.value}${版本文字}、${目前比較職能.value?.名稱 || "指定職能"}的公開成績，並排查看最佳紀錄、rDPS 與通關表現。`,
    );
  }

  return "輸入兩名 FFXIV 繁中服玩家，依防護、治療、近戰、遠程物理或遠程魔法職能比較公開成績。";
}

function 職業分析分享描述() {
  const 範圍名稱 = 職業分析目前範圍.value?.名稱 || "指定範圍";
  const 代表紀錄數 = 分享數量文字(職業分析代表紀錄.value.length, "筆代表紀錄");

  return 正規化分享描述(
    `${範圍名稱}職業分析整理 rDPS 分位、各副本與伺服器分布${代表紀錄數 ? `，目前列出 ${代表紀錄數}` : ""}，協助查看繁中服公開紀錄中的職業落點。`,
  );
}

function 近期動態分享描述() {
  const 最新數 = 分享數量文字(近期動態最新成績列表.value.length, "筆最新成績");
  const 刷新數 = 分享數量文字(近期刷新紀錄列表.value.length, "筆刷新紀錄");
  return 正規化分享描述(
    `近期動態整理 FFXIV 繁中服最新公開成績、新收錄玩家、伺服器活躍與副本活躍${[最新數, 刷新數].filter(Boolean).length ? `，目前顯示 ${[最新數, 刷新數].filter(Boolean).join("、")}` : ""}。`,
  );
}

function 隊伍榜分享描述() {
  const 範圍 = 目前隊伍榜副本.value?.encounter_name || "指定副本";
  const 版本文字 = 顯示隊伍榜版本篩選.value ? `（${取得版本紀錄範圍文字(有效隊伍榜版本範圍.value)}）` : "";
  const 隊伍數 = 分享數量文字(隊伍榜列.value.length, "組隊伍紀錄");
  return 正規化分享描述(
    `${範圍}${版本文字}隊伍榜整理同場 8 人公開紀錄的通關時間、隊伍 rDPS 與成員組成${隊伍數 ? `，目前收錄 ${隊伍數}` : ""}。`,
  );
}

function 伺服器對比分享描述() {
  if (伺服器對比已完成.value) {
    return 正規化分享描述(
      `比較 ${伺服器對比左資料.value.server} 與 ${伺服器對比右資料.value.server} 的收錄玩家、副本通關、職能比例、熱門職業與副本落點。`,
    );
  }

  return "並排比較兩個 FFXIV 繁中服伺服器的收錄玩家、副本通關、職能比例、熱門職業與副本落點。";
}

function 蜂蜂粉絲榜分享描述() {
  const summary = 蜂蜂粉絲榜來源.value.summary || {};
  const 榜單天數 = summary.leaderboard_window_days || 蜂蜂粉絲榜來源.value.leaderboard_window?.days || 7;
  const eventCount = 分享數量文字(summary.total_event_count, "筆粉絲紀錄");
  const fanCount = 分享數量文字(summary.fan_count, "名粉絲");
  const historicalEventCount = 分享數量文字(summary.historical_total_event_count, "筆歷史紀錄");
  const topFan = summary.top_fan_name ? `，目前頭號粉絲是 ${summary.top_fan_name}` : "";
  return 正規化分享描述(
    `Honey B. Lovely 粉絲榜統計近 ${榜單天數} 天 M2S 通關與 wipe 戰鬥中吃到第 4 顆愛心、進入「心醉魂迷：奴役」的趣味資料${[eventCount, fanCount].filter(Boolean).length ? `，本期收錄 ${[eventCount, fanCount].filter(Boolean).join("、")}` : ""}${historicalEventCount ? `，歷史累計 ${historicalEventCount}` : ""}${topFan}。`,
  );
}

const 分享標題 = computed(() => {
  const 標題 = 頁面標題.value || 預設分享標題;
  if (標題 === "排行榜" || 標題 === 預設分享標題) {
    return 預設分享標題;
  }
  return `${標題} | ${預設分享標題}`;
});

const 分享描述 = computed(() => {
  if (頁面模式.value === "stats") {
    return 全服統計分享描述();
  }
  if (頁面模式.value === "user") {
    return 個人成績單分享描述();
  }
  if (頁面模式.value === "compare") {
    return 玩家比較分享描述();
  }
  if (頁面模式.value === "jobs") {
    return 職業分析分享描述();
  }
  if (頁面模式.value === "activity") {
    return 近期動態分享描述();
  }
  if (頁面模式.value === "teams") {
    return 隊伍榜分享描述();
  }
  if (頁面模式.value === "servers") {
    return 伺服器對比分享描述();
  }
  if (頁面模式.value === "faq" || 頁面模式.value === "logs") {
    return "整理 FFXIV 繁中服排行榜常見問題，並提供 FFLogs report 收錄狀態檢查工具。";
  }
  if (頁面模式.value === "honey-fans") {
    return 蜂蜂粉絲榜分享描述();
  }

  const 副本名稱 = 目前副本.value?.name || "高難度副本";
  const 成績數 = 分享數量文字(所有排行列.value.length, "筆公開成績");
  return 正規化分享描述(
    `${副本名稱}${排行榜分享條件文字()}排行榜${成績數 ? `，目前收錄 ${成績數}` : ""}，可查看 rDPS、aDPS、Active、通關時間與 FFLogs 來源紀錄。`,
  );
});

const 分享資訊 = computed(() => ({
  title: 分享標題.value,
  description: 分享描述.value,
  url: 建立目前分享網址(),
}));

const 使用者索引列表 = computed(() => {
  return Array.isArray(使用者索引.value?.users) ? 使用者索引.value.users : [];
});
const 使用者搜尋建議索引 = ref([]);

function 正規化搜尋比對文字(文字) {
  return String(文字 || "").trim().toLocaleLowerCase("zh-TW");
}

function 建立使用者搜尋建議索引條目(使用者) {
  const 伺服器 = 取得使用者主要伺服器(使用者);
  const 伺服器列表 = 取得使用者伺服器列表(使用者);
  const 顯示文字 = 格式化使用者搜尋文字(使用者.character_name, 伺服器);
  const 搜尋候選文字 = [
    使用者.character_name,
    伺服器,
    顯示文字,
    ...伺服器列表,
    ...伺服器列表.map((伺服器名稱) => 格式化使用者搜尋文字(使用者.character_name, 伺服器名稱)),
  ];

  return {
    value: 顯示文字,
    label: `${使用者.encounter_count || 0} 副本 / ${使用者.public_entry_count || 0} 筆公開成績`,
    character_name: 使用者.character_name,
    server: 伺服器,
    搜尋文字: Array.from(new Set(搜尋候選文字.map(正規化搜尋比對文字).filter(Boolean))).join("\n"),
  };
}

function 重建使用者搜尋建議索引() {
  // users/index.json 會隨玩家數量持續成長；搜尋建議只需要查詢用字串與顯示欄位。
  // 在索引載入時先完成正規化，避免使用者每打一個字就重建上萬筆候選資料。
  使用者搜尋建議索引.value = 使用者索引列表.value.map(建立使用者搜尋建議索引條目);
}

function 初始化玩家搜尋歷史() {
  玩家搜尋歷史.value = 讀取玩家搜尋歷史();
}

function 記錄玩家搜尋歷史(角色名稱, 伺服器 = "") {
  const 更新後歷史 = 新增玩家搜尋歷史({
    character_name: 角色名稱,
    server: 伺服器,
  });
  玩家搜尋歷史.value = 更新後歷史;
  return 更新後歷史;
}

function 開啟玩家搜尋歷史(欄位) {
  目前玩家搜尋歷史欄位.value = 欄位;
}

function 處理玩家搜尋歷史失焦(event, 欄位) {
  if (目前玩家搜尋歷史欄位.value !== 欄位) {
    return;
  }

  if (!event.currentTarget.contains(event.relatedTarget)) {
    目前玩家搜尋歷史欄位.value = "";
  }
}

function 建立玩家搜尋歷史顯示列表(輸入文字) {
  if (String(輸入文字 || "").trim()) {
    return [];
  }

  return 建立玩家搜尋歷史詳細列表(玩家搜尋歷史.value).slice(0, 玩家搜尋歷史顯示上限);
}

function 格式化搜尋歷史時間(時間Iso) {
  return 時間Iso ? 格式化紀錄時間(時間Iso) : "未記錄時間";
}

function 格式化搜尋歷史日期(時間Iso) {
  return 時間Iso ? 格式化紀錄日期(時間Iso) : "未記錄日期";
}

function 格式化搜尋歷史時刻(時間Iso) {
  return 時間Iso ? 格式化紀錄時刻(時間Iso) : "";
}

function 建立玩家搜尋歷史詳細列表(列表) {
  return (Array.isArray(列表) ? 列表 : []).map((紀錄) => {
    const 索引條目 = 尋找使用者索引條目(紀錄.character_name, 紀錄.server);
    const 搜尋時間Iso = 紀錄.searched_at_iso || "";
    return {
      ...紀錄,
      value: 格式化使用者搜尋文字(紀錄.character_name, 紀錄.server),
      key: `${紀錄.character_name}@${紀錄.server}`,
      label: 索引條目
        ? `${索引條目.encounter_count || 0} 副本 / ${索引條目.public_entry_count || 0} 筆公開成績`
        : "最近搜尋",
      搜尋時間Iso,
      搜尋時間文字: 格式化搜尋歷史時間(搜尋時間Iso),
      搜尋日期文字: 格式化搜尋歷史日期(搜尋時間Iso),
      搜尋時刻文字: 格式化搜尋歷史時刻(搜尋時間Iso),
    };
  });
}

const 排行榜最近搜尋玩家 = computed(() => 建立玩家搜尋歷史顯示列表(搜尋關鍵字.value));
const 使用者最近搜尋玩家 = computed(() => 建立玩家搜尋歷史顯示列表(使用者搜尋關鍵字.value));
const 比較角色左最近搜尋玩家 = computed(() => 建立玩家搜尋歷史顯示列表(比較角色左輸入.value));
const 比較角色右最近搜尋玩家 = computed(() => 建立玩家搜尋歷史顯示列表(比較角色右輸入.value));
const 顯示排行榜最近搜尋玩家 = computed(() => 目前玩家搜尋歷史欄位.value === "ranking" && 排行榜最近搜尋玩家.value.length > 0);
const 顯示使用者最近搜尋玩家 = computed(() => 目前玩家搜尋歷史欄位.value === "user" && 使用者最近搜尋玩家.value.length > 0);
const 顯示比較角色左最近搜尋玩家 = computed(
  () => 目前玩家搜尋歷史欄位.value === "compare-left" && 比較角色左最近搜尋玩家.value.length > 0,
);
const 顯示比較角色右最近搜尋玩家 = computed(
  () => 目前玩家搜尋歷史欄位.value === "compare-right" && 比較角色右最近搜尋玩家.value.length > 0,
);
const 玩家搜尋歷史管理列表 = computed(() => 建立玩家搜尋歷史詳細列表(玩家搜尋歷史.value));

function 開啟玩家搜尋歷史管理彈窗() {
  目前玩家搜尋歷史欄位.value = "";
  玩家搜尋歷史管理彈窗開啟.value = true;
}

function 關閉玩家搜尋歷史管理彈窗() {
  玩家搜尋歷史管理彈窗開啟.value = false;
}

function 刪除單筆玩家搜尋歷史(紀錄) {
  玩家搜尋歷史.value = 刪除玩家搜尋歷史(紀錄);
}

function 清除所有玩家搜尋歷史() {
  玩家搜尋歷史.value = 清除玩家搜尋歷史();
}

function 找出排行榜搜尋歷史紀錄(輸入文字) {
  const 查詢 = 解析使用者搜尋輸入(輸入文字);
  const 查詢名稱 = 正規化搜尋比對文字(查詢.角色名稱);
  const 查詢伺服器 = 正規化搜尋比對文字(查詢.伺服器);
  if (!查詢名稱) {
    return null;
  }

  const 索引條目 = 尋找使用者索引條目(查詢.角色名稱, 查詢.伺服器);
  if (索引條目) {
    return {
      character_name: 索引條目.character_name,
      server: 取得使用者主要伺服器(索引條目) || 查詢.伺服器 || "",
    };
  }

  const 完全符合列 = 所有排行列.value.find((列) => {
    const 名稱符合 = 正規化搜尋比對文字(列.角色名稱) === 查詢名稱;
    const 伺服器符合 = !查詢伺服器 || 正規化搜尋比對文字(列.伺服器) === 查詢伺服器;
    return 名稱符合 && 伺服器符合;
  });

  return 完全符合列
    ? {
        character_name: 完全符合列.角色名稱,
        server: 完全符合列.伺服器,
      }
    : null;
}

function 記錄排行榜搜尋歷史() {
  const 歷史紀錄 = 找出排行榜搜尋歷史紀錄(搜尋關鍵字.value);
  if (歷史紀錄) {
    記錄玩家搜尋歷史(歷史紀錄.character_name, 歷史紀錄.server);
  }
}

function 選擇最近搜尋玩家(欄位, 紀錄) {
  const 歷史紀錄 = 正規化玩家搜尋歷史紀錄(紀錄);
  if (!歷史紀錄) {
    return;
  }

  記錄玩家搜尋歷史(歷史紀錄.character_name, 歷史紀錄.server);
  目前玩家搜尋歷史欄位.value = "";
  const 顯示文字 = 格式化使用者搜尋文字(歷史紀錄.character_name, 歷史紀錄.server);

  if (欄位 === "ranking") {
    搜尋關鍵字.value = 顯示文字;
    return;
  }

  if (欄位 === "user") {
    使用者搜尋關鍵字.value = 顯示文字;
    載入使用者成績(歷史紀錄.character_name, 歷史紀錄.server);
    return;
  }

  if (欄位 === "compare-left") {
    比較角色左輸入.value = 顯示文字;
    return;
  }

  if (欄位 === "compare-right") {
    比較角色右輸入.value = 顯示文字;
  }
}

function 建立使用者搜尋建議列表(搜尋文字) {
  const 關鍵字 = 正規化搜尋比對文字(搜尋文字);
  if (!關鍵字) {
    return [];
  }

  if (使用者索引列表.value.length > 0 && 使用者搜尋建議索引.value.length === 0) {
    重建使用者搜尋建議索引();
  }

  const 建議列表 = [];
  for (const 建議 of 使用者搜尋建議索引.value) {
    if (!建議.搜尋文字.includes(關鍵字)) {
      continue;
    }

    const { 搜尋文字, ...顯示建議 } = 建議;
    建議列表.push(顯示建議);
    if (建議列表.length >= 8) {
      break;
    }
  }

  return 建議列表;
}

const 使用者搜尋建議 = computed(() => {
  return 建立使用者搜尋建議列表(使用者搜尋關鍵字.value);
});

const 比較角色左搜尋建議 = computed(() => {
  return 建立使用者搜尋建議列表(比較角色左輸入.value);
});

const 比較角色右搜尋建議 = computed(() => {
  return 建立使用者搜尋建議列表(比較角色右輸入.value);
});

const 比較副本列表 = computed(() => [
  { key: "all", name: "全部副本", category: "全部" },
  ...副本清單.value.map((副本) => ({
    key: 副本.key,
    name: 副本.name,
    category: 副本.category || "副本",
    version_cutoff: 副本.version_cutoff || null,
  })),
]);

const 目前比較副本 = computed(() => {
  if (比較副本鍵值.value === "all") {
    return null;
  }

  return 比較副本列表.value.find((副本) => 副本.key === 比較副本鍵值.value) || null;
});

const 比較範圍文字 = computed(() => 目前比較副本.value?.name || "全部副本");
const 比較副本選單文字 = computed(() => 比較範圍文字.value);
const 顯示比較版本篩選 = computed(() => 副本支援版本篩選(目前比較副本.value));
const 有效比較版本範圍 = computed(() => 取得有效版本紀錄範圍(目前比較副本.value, 比較版本範圍.value));

// 個人成績單內的「最佳」要以 rDPS 優先，平手才比較通關時間與 aDPS。
// 這和排行榜去重規則保持一致，讓玩家頁、比較頁和排行榜對最佳成績的判斷一致。
function 使用者成績是否較佳(候選, 目前最佳) {
  if (!候選) {
    return false;
  }
  if (!目前最佳) {
    return true;
  }

  const 候選rDPS = 候選.rdps ?? 候選.dps ?? 0;
  const 目前rDPS = 目前最佳.rdps ?? 目前最佳.dps ?? 0;
  if (候選rDPS !== 目前rDPS) {
    return 候選rDPS > 目前rDPS;
  }

  const 候選通關時間 = 候選.clear_time_seconds ?? Infinity;
  const 目前通關時間 = 目前最佳.clear_time_seconds ?? Infinity;
  if (候選通關時間 !== 目前通關時間) {
    return 候選通關時間 < 目前通關時間;
  }

  const 候選aDPS = 候選.adps ?? 候選.dps ?? 0;
  const 目前aDPS = 目前最佳.adps ?? 目前最佳.dps ?? 0;
  if (候選aDPS !== 目前aDPS) {
    return 候選aDPS > 目前aDPS;
  }

  return new Date(候選.recorded_at_iso || 0).getTime() > new Date(目前最佳.recorded_at_iso || 0).getTime();
}

function 使用者代表成績是否較佳(候選, 目前最佳) {
  // 個人成績單未套用職業篩選時，代表列不能直接跨職業比 raw rDPS。
  // 前 N% 模式保留既有 Rank/top_percent 口徑；PR 模式則改用 score_percentile，
  // 讓不同職業樣本數差異不會讓「排名較前但 PR 較低」的職業被誤放在第一順位。
  return 個人成績代表是否較佳(候選, 目前最佳, 分位顯示模式.value, 使用者成績是否較佳);
}

function 排序使用者公開成績(公開成績) {
  if (分位顯示模式.value !== 分位顯示模式PR) {
    return 公開成績;
  }

  return 公開成績
    .map((成績, 原始索引) => ({ 成績, 原始索引 }))
    .sort((左, 右) => {
      const 分位差 = 比較個人成績分位顯示排序(左.成績, 右.成績, 分位顯示模式.value);
      if (分位差 !== 0) {
        return 分位差;
      }
      if (使用者成績是否較佳(左.成績, 右.成績)) {
        return -1;
      }
      if (使用者成績是否較佳(右.成績, 左.成績)) {
        return 1;
      }
      return 左.原始索引 - 右.原始索引;
    })
    .map(({ 成績 }) => 成績);
}

function 取得使用者副本成績(資料, 伺服器 = "", 成績篩選 = () => true, 最佳成績比較 = 使用者成績是否較佳) {
  const 副本列表 = Array.isArray(資料?.encounters) ? 資料.encounters : [];

  return 副本列表
    .map((副本) => {
      const 公開成績 = 排序使用者公開成績(
        (副本.public_entries || []).filter((成績) => (!伺服器 || 成績.server === 伺服器) && 成績篩選(成績)),
      );
      if (公開成績.length === 0) {
        return null;
      }

      const 有效成績 = 公開成績.filter((成績) => !成績.is_obsolete_record);
      const 最佳成績 = 有效成績.reduce((目前最佳, 成績) => (最佳成績比較(成績, 目前最佳) ? 成績 : 目前最佳), null);
      return {
        ...副本,
        best_entry: 最佳成績,
        public_entries: 公開成績,
      };
    })
    .filter(Boolean);
}

const 使用者完整副本成績 = computed(() => {
  return 取得使用者副本成績(使用者資料.value, 使用者伺服器篩選.value, () => true, 使用者代表成績是否較佳);
});
const 使用者徽章副本成績 = computed(() => {
  // 徽章描述角色累積的公開成就，不是目前表格套用的檢視範圍。特別是選取單一
  // 職業時，不能讓多職、三色豆或量級踏破等已取得的徽章暫時消失；伺服器篩選
  // 亦同。因此這裡刻意不傳入伺服器或職業條件，與頁面顯示資料分開維護。
  return 取得使用者副本成績(使用者資料.value, "", () => true, 使用者代表成績是否較佳);
});


const 使用者簡表版本副本成績 = computed(() => {
  // 使用者檔保留完整歷史，簡表才依版本切片。這可避免增加每位玩家 JSON 的重複資料，
  // 也保留一般個人成績頁與報告彈窗的完整追溯能力。
  return 取得使用者副本成績(
    使用者資料.value,
    使用者伺服器篩選.value,
    (成績) => 成績符合個人成績簡表版本(成績, 使用者簡表版本.value),
    使用者代表成績是否較佳,
  );
});

const 使用者簡表群組 = computed(() => {
  // 簡表的問題是角色是否有已收錄通關，而不是某個職業是否有成績；
  // 因此必須使用未套職業篩選的完整副本成績，避免切換職業後把既有通關誤標為未收錄。
  return 建立個人成績簡表群組(
    副本清單.value,
    使用者簡表版本副本成績.value,
    使用者簡表版本.value,
    使用者簡表零式量級.value,
  );
});

const 使用者簡表目標副本數 = computed(() => {
  return 使用者簡表群組.value.reduce((總數, 群組) => 總數 + 群組.encounters.length, 0);
});

const 使用者簡表已收錄通關數 = computed(() => {
  return 使用者簡表群組.value.reduce(
    (總數, 群組) => 總數 + 群組.encounters.filter((副本) => 副本.已收錄通關).length,
    0,
  );
});

const 使用者可用職業列表 = computed(() => {
  const 職業集合 = new Set(
    使用者完整副本成績.value
      .flatMap((副本) =>副本.public_entries || [])
      .map((成績) => 成績.job)
      .filter(Boolean),
  );

  return Array.from(職業集合).sort((前一個, 後一個) => {
    const 類型差 = 職業類型排序值(職業所屬類型(前一個)?.代碼) - 職業類型排序值(職業所屬類型(後一個)?.代碼);
    return 類型差 || 顯示職業名稱(前一個).localeCompare(顯示職業名稱(後一個), "zh-Hant-TW");
  });
});

const 使用者職業類型選項 = computed(() => {
  return 職業群組設定.filter((群組) => 使用者可用職業列表.value.some((職業) => 群組.職業.includes(職業)));
});

const 使用者職業選項 = computed(() => {
  return 使用者可用職業列表.value
    .filter((職業) => !使用者職業類型篩選.value || 職業所屬類型(職業)?.代碼 === 使用者職業類型篩選.value)
    .map((職業) => ({
      代碼: 職業,
      名稱: 顯示職業名稱(職業),
      job: 職業,
      job_name: 顯示職業名稱(職業),
      role: 職業所屬類型(職業)?.代碼 || "",
      色彩: 職業代碼色彩(職業),
    }));
});

const 目前使用者職業類型 = computed(() => {
  return 職業群組設定.find((群組) => 群組.代碼 === 使用者職業類型篩選.value) || null;
});

const 使用者職業選單文字 = computed(() => {
  if (使用者職業篩選.value) {
    return 目前使用者職業類型.value
      ? `${目前使用者職業類型.value.名稱} / ${顯示職業名稱(使用者職業篩選.value)}`
      : 顯示職業名稱(使用者職業篩選.value);
  }

  return 目前使用者職業類型.value?.名稱 || "全部職業";
});

const 使用者職業選單Icon路徑 = computed(() => {
  if (使用者職業篩選.value) {
    return 職業Icon路徑(使用者職業篩選.value);
  }

  if (使用者職業類型篩選.value) {
    return 職業類型Icon路徑(使用者職業類型篩選.value);
  }

  return "";
});

function 符合使用者職業篩選(成績) {
  if (使用者職業類型篩選.value && 職業所屬類型(成績.job)?.代碼 !== 使用者職業類型篩選.value) {
    return false;
  }

  return !使用者職業篩選.value || 成績.job === 使用者職業篩選.value;
}

const 使用者副本成績 = computed(() => {
  return 取得使用者副本成績(使用者資料.value, 使用者伺服器篩選.value, 符合使用者職業篩選, 使用者代表成績是否較佳);
});

function 建立使用者統計(副本成績) {
  const 公開成績數 = 副本成績.reduce((總數, 副本) => 總數 + 副本.public_entries.length, 0);
  const 所有公開成績 = 副本成績.flatMap((副本) => 副本.public_entries || []);
  const 有效公開成績 = 所有公開成績.filter((成績) => !成績.is_obsolete_record);
  const 最佳成績 = 有效公開成績.reduce(
    (目前最佳, 成績) => (使用者成績是否較佳(成績, 目前最佳) ? 成績 : 目前最佳),
    null,
  );
  const 代表成績 = 副本成績.reduce(
    (目前最佳, 副本) => (使用者代表成績是否較佳(副本.best_entry, 目前最佳) ? 副本.best_entry : 目前最佳),
    null,
  );
  const 最高Gcd成績 = 有效公開成績.reduce((目前最佳, 成績) => {
    const 目前Gcd = 取得Gcd覆蓋率數值(目前最佳?.gcd_coverage);
    const 候選Gcd = 取得Gcd覆蓋率數值(成績?.gcd_coverage);
    if (候選Gcd === null) {
      return 目前最佳;
    }
    if (目前Gcd === null || 候選Gcd > 目前Gcd) {
      return 成績;
    }
    return 目前最佳;
  }, null);
  const 最後紀錄時間 = 副本成績
    .flatMap((副本) => 副本.public_entries)
    .map((成績) => 成績.recorded_at_iso)
    .filter(Boolean)
    .sort()
    .at(-1);

  return {
    副本數: 副本成績.length,
    公開成績數,
    最佳成績,
    代表成績,
    最高Gcd成績,
    最後紀錄時間,
  };
}

const 使用者統計 = computed(() => {
  return 建立使用者統計(使用者副本成績.value);
});

const 使用者分位亮點 = computed(() => {
  return 使用者副本成績.value
    .map((副本) =>
      副本.best_entry
        ? {
            ...副本.best_entry,
            encounter_name: 副本.encounter_name,
            encounter_category: 副本.encounter_category,
          }
        : null,
    )
    .filter((成績) => 成績?.performance?.qualified)
    .sort((前一個, 後一個) => {
      const 分位差 = 比較個人成績分位顯示排序(前一個, 後一個, 分位顯示模式.value);
      return 分位差 || (後一個.rdps ?? 0) - (前一個.rdps ?? 0);
    })
    .slice(0, 4);
});

function 比較使用者趨勢職業預設排序(前一個, 後一個) {
  // 同副本合併後，預設職業以玩家最常遊玩的紀錄數為主，平手才用近期與最佳成績穩定排序。
  const 紀錄數差 = 後一個.點列表.length - 前一個.點列表.length;
  if (紀錄數差 !== 0) {
    return 紀錄數差;
  }

  const 最新時間差 =
    new Date(後一個.最新?.recorded_at_iso || 0).getTime() - new Date(前一個.最新?.recorded_at_iso || 0).getTime();
  if (最新時間差 !== 0) {
    return 最新時間差;
  }

  if (使用者成績是否較佳(前一個.最佳, 後一個.最佳)) {
    return -1;
  }
  if (使用者成績是否較佳(後一個.最佳, 前一個.最佳)) {
    return 1;
  }

  const 職能順序差 = 職業類型排序值(前一個.職能?.代碼) - 職業類型排序值(後一個.職能?.代碼);
  return 職能順序差 || 前一個.job_name.localeCompare(後一個.job_name, "zh-Hant-TW");
}

function 建立使用者成績趨勢項(副本, 職業代碼, 成績列表) {
  const 職能 = 職業所屬類型(職業代碼);
  const 數值列表 = 成績列表.map((成績) => 轉為數字(成績.rdps) || 0);
  const 最低 = Math.min(...數值列表);
  const 最高 = Math.max(...數值列表);
  const 第一筆 = 成績列表[0];
  const 最新 = 成績列表.at(-1);
  const 有效成績列表 = 成績列表.filter((成績) => !成績.is_obsolete_record);
  const 最佳 = 有效成績列表.reduce((目前最佳, 成績) => (使用者成績是否較佳(成績, 目前最佳) ? 成績 : 目前最佳), null);
  const 點列表 = 成績列表.map((成績, index) => {
    const rdps = 轉為數字(成績.rdps) || 0;
    const x = 成績列表.length === 1 ? 50 : (index / (成績列表.length - 1)) * 100;
    const y = 最高 === 最低 ? 26 : 42 - ((rdps - 最低) / (最高 - 最低)) * 32;
    return {
      id: 成績.id,
      job: 成績.job,
      rdps,
      gcd_coverage: 成績.gcd_coverage ?? null,
      recorded_at_iso: 成績.recorded_at_iso,
      過版紀錄: Boolean(成績.is_obsolete_record),
      x: Number(x.toFixed(2)),
      y: Number(y.toFixed(2)),
    };
  });
  const 折線路徑 = 點列表.length > 1 ? 點列表.map((點, index) => `${index === 0 ? "M" : "L"} ${點.x} ${點.y}`).join(" ") : "";
  const 線段列表 = 點列表.slice(1).map((點, index) => {
    const 前一點 = 點列表[index];
    return {
      key: `${前一點.id}-${點.id}`,
      path: `M ${前一點.x} ${前一點.y} L ${點.x} ${點.y}`,
      過版紀錄: 前一點.過版紀錄 || 點.過版紀錄,
    };
  });
  // 面積填色跟折線使用同一個版本判定：有效版本維持原色，碰到過版點的區段改用灰色。
  // 這讓混合有效/過版紀錄的趨勢圖仍保有面積色塊，不會只剩幾條線而難以掃讀。
  const 填色區塊列表 = 線段列表.map((線段, index) => {
    const 起點 = 點列表[index];
    const 終點 = 點列表[index + 1];
    return {
      key: `area-${線段.key}`,
      path: `M ${起點.x} ${起點.y} L ${終點.x} ${終點.y} L ${終點.x} 46 L ${起點.x} 46 Z`,
      過版紀錄: 線段.過版紀錄,
    };
  });

  return {
    key: `${副本.encounter_key}::${職業代碼}`,
    encounter_key: 副本.encounter_key,
    encounter_name: 副本.encounter_name,
    encounter_category: 副本.encounter_category,
    job: 職業代碼,
    job_name: 顯示職業名稱(職業代碼),
    job_color: 職業代碼色彩(職業代碼),
    職能,
    最新,
    最佳,
    變化: (轉為數字(最新?.rdps) || 0) - (轉為數字(第一筆?.rdps) || 0),
    最低,
    最高,
    折線路徑,
    填色區塊列表,
    線段列表,
    點列表,
  };
}

const 使用者成績趨勢 = computed(() => {
  return 使用者副本成績.value
    .map((副本) => {
      const 職業成績索引 = new Map();
      for (const 成績 of 副本.public_entries || []) {
        const 職業代碼 = 成績.job;
        if (!職業代碼 || 轉為數字(成績.rdps) === null) {
          continue;
        }

        if (!職業成績索引.has(職業代碼)) {
          職業成績索引.set(職業代碼, {
            職業代碼,
            成績列表: [],
          });
        }
        職業成績索引.get(職業代碼).成績列表.push(成績);
      }

      const 職業趨勢列表 = Array.from(職業成績索引.values()).map(({ 職業代碼, 成績列表 }) => {
        const 排序後成績 = 成績列表.sort((前一個, 後一個) => {
          const 時間差 = new Date(前一個.recorded_at_iso || 0).getTime() - new Date(後一個.recorded_at_iso || 0).getTime();
          return 時間差 || (前一個.rdps ?? 0) - (後一個.rdps ?? 0);
        });

        return 建立使用者成績趨勢項(副本, 職業代碼, 排序後成績);
      }).sort(比較使用者趨勢職業預設排序);

      if (職業趨勢列表.length === 0) {
        return null;
      }

      const 已選職業 = 使用者趨勢職業選擇.value[副本.encounter_key];
      const 目前趨勢 = 職業趨勢列表.find((趨勢) => 趨勢.job === 已選職業) || 職業趨勢列表[0];
      const 職業選項 = 職業趨勢列表.map((趨勢) => ({
        代碼: 趨勢.job,
        名稱: 趨勢.job_name,
        色彩: 趨勢.job_color,
        職能: 趨勢.職能,
        紀錄數: 趨勢.點列表.length,
        已選取: 趨勢.job === 目前趨勢.job,
      }));

      return {
        ...目前趨勢,
        key: 副本.encounter_key,
        趨勢key: 目前趨勢.key,
        職業趨勢列表,
        職業選項,
        目前職業代碼: 目前趨勢.job,
        多職業: 職業趨勢列表.length > 1,
      };
    })
    .filter(Boolean)
    .sort((前一個, 後一個) => {
      const 副本順序差 = 取得副本排序值(前一個.encounter_key) - 取得副本排序值(後一個.encounter_key);
      return 副本順序差 || 前一個.encounter_name.localeCompare(後一個.encounter_name, "zh-Hant-TW");
    });
});

function 建立比較角色項目(資料, 伺服器 = "") {
  if (!資料) {
    return null;
  }

  const 副本成績 = 取得使用者副本成績(資料, 伺服器);
  return {
    character_name: 資料.character_name || "未知玩家",
    server: 伺服器 || 取得使用者主要伺服器(資料),
    副本成績,
    統計: 建立使用者統計(副本成績),
  };
}

const 比較角色左 = computed(() => 建立比較角色項目(比較角色左資料.value, 比較角色左伺服器.value));
const 比較角色右 = computed(() => 建立比較角色項目(比較角色右資料.value, 比較角色右伺服器.value));

const 角色比較已完成 = computed(() => Boolean(比較角色左.value && 比較角色右.value));
const 目前比較職能 = computed(() => 比較職能索引.get(比較職能篩選.value) || 比較職能設定[0]);

function 取得副本排序值(副本鍵值) {
  const 清單索引 = 副本清單.value.findIndex((副本) => 副本.key === 副本鍵值);
  return 清單索引 >= 0 ? 清單索引 : Number.MAX_SAFE_INTEGER;
}

function 建立比較副本職能索引(副本成績列表, 職能代碼, 副本鍵值 = "all", 版本範圍 = 預設版本紀錄範圍) {
  const 索引 = new Map();

  for (const 副本 of 副本成績列表) {
    if (副本鍵值 !== "all" && 副本.encounter_key !== 副本鍵值) {
      continue;
    }

    const 公開成績 = Array.isArray(副本.public_entries) ? 副本.public_entries : [];
    for (const 成績 of 公開成績) {
      const 職能 = 取得比較職能(成績.job);
      if (!職能 || 職能.代碼 !== 職能代碼) {
        continue;
      }
      if (!紀錄符合版本範圍(成績, 版本範圍)) {
        continue;
      }

      const 鍵值 = 副本.encounter_key;
      const 目前 = 索引.get(鍵值);
      if (!目前 || 使用者成績是否較佳(成績, 目前.best_entry)) {
        索引.set(鍵值, {
          ...副本,
          best_entry: 成績,
          comparison_role: 職能,
        });
      }
    }
  }

  return 索引;
}

const 角色比較列 = computed(() => {
  if (!角色比較已完成.value) {
    return [];
  }

  const 職能 = 目前比較職能.value;
  const 左副本 = 建立比較副本職能索引(
    比較角色左.value.副本成績,
    職能?.代碼,
    比較副本鍵值.value,
    有效比較版本範圍.value,
  );
  const 右副本 = 建立比較副本職能索引(
    比較角色右.value.副本成績,
    職能?.代碼,
    比較副本鍵值.value,
    有效比較版本範圍.value,
  );
  const 副本鍵值列表 = Array.from(new Set([...左副本.keys(), ...右副本.keys()]));

  return 副本鍵值列表
    .map((副本鍵值) => {
      const 左 = 左副本.get(副本鍵值) || null;
      const 右 = 右副本.get(副本鍵值) || null;
      const 左成績 = 左?.best_entry || null;
      const 右成績 = 右?.best_entry || null;
      const 左Rdps = 轉為數字(左成績?.rdps);
      const 右Rdps = 轉為數字(右成績?.rdps);
      const 差異 = 左Rdps !== null && 右Rdps !== null ? 左Rdps - 右Rdps : null;
      const 左Gcd = 取得Gcd覆蓋率數值(左成績?.gcd_coverage);
      const 右Gcd = 取得Gcd覆蓋率數值(右成績?.gcd_coverage);
      const GCD差異 = 左Gcd !== null && 右Gcd !== null ? Number((左Gcd - 右Gcd).toFixed(2)) : null;

      return {
        key: `${副本鍵值}::${職能?.代碼 || "role"}`,
        encounter_key: 副本鍵值,
        encounter_name: 左?.encounter_name || 右?.encounter_name || 副本鍵值,
        encounter_category: 左?.encounter_category || 右?.encounter_category || "",
        職能,
        左,
        右,
        差異,
        GCD差異,
      };
    })
    .sort((前一個, 後一個) => {
      const 順序差 = 取得副本排序值(前一個.encounter_key) - 取得副本排序值(後一個.encounter_key);
      return 順序差 || 前一個.encounter_name.localeCompare(後一個.encounter_name, "zh-Hant-TW");
    });
});

const 使用者隊友列表 = computed(() => {
  const 伺服器 = 使用者伺服器篩選.value;
  const 隊友列表 = Array.isArray(使用者資料.value?.frequent_teammates) ? 使用者資料.value.frequent_teammates : [];
  const 整理後列表 = 隊友列表
    .map((隊友) => {
      const 伺服器同場資料 = 伺服器 ? (隊友.user_servers || []).find((項目) => 項目.server === 伺服器) : null;
      const 同場次數 = 伺服器 ? (伺服器同場資料?.co_clear_count ?? 0) : (隊友.co_clear_count ?? 0);
      const 副本列表 = Array.isArray(隊友.encounters) ? 隊友.encounters : [];
      const 主要副本 = 副本列表
        .slice()
        .sort((前一個, 後一個) => (後一個.co_clear_count || 0) - (前一個.co_clear_count || 0))
        .slice(0, 2);

      return {
        ...隊友,
        同場次數,
        職業列表: (隊友.jobs || []).slice(0, 4),
        職業文字: (隊友.jobs || []).map(顯示職業名稱).slice(0, 3).join(" / "),
        主要副本,
        副本文字: 主要副本.map((副本) => 副本.encounter_name).join(" / "),
      };
    })
    .filter((隊友) => 隊友.同場次數 > 0)
    .sort((前一個, 後一個) => {
      if (前一個.同場次數 !== 後一個.同場次數) {
        return 後一個.同場次數 - 前一個.同場次數;
      }

      return 前一個.character_name.localeCompare(後一個.character_name, "zh-Hant-TW");
    });

  const 最高同場次數 = 整理後列表[0]?.同場次數 || 0;
  return 整理後列表.map((隊友) => ({
    ...隊友,
    強度: 最高同場次數 > 0 ? Number(((隊友.同場次數 / 最高同場次數) * 100).toFixed(2)) : 0,
  }));
});

const 常見隊友 = computed(() => 使用者隊友列表.value.slice(0, 8));

const 隊友職能分布 = computed(() => {
  const 職能索引 = new Map(
    職業群組設定.map((群組) => [
      群組.代碼,
      {
        代碼: 群組.代碼,
        名稱: 群組.名稱,
        色彩: 群組.色彩,
        人數: 0,
        同場次數: 0,
      },
    ]),
  );

  for (const 隊友 of 使用者隊友列表.value) {
    const 隊友職能集合 = new Set(
      (隊友.jobs || [])
        .map((職業) => 職業所屬類型(職業)?.代碼)
        .filter(Boolean),
    );

    for (const 職能代碼 of 隊友職能集合) {
      const bucket = 職能索引.get(職能代碼);
      if (!bucket) {
        continue;
      }
      bucket.人數 += 1;
      bucket.同場次數 += 隊友.同場次數;
    }
  }

  const 列表 = Array.from(職能索引.values()).filter((職能) => 職能.人數 > 0);
  const 最高人數 = Math.max(...列表.map((職能) => 職能.人數), 0);

  return 列表.map((職能) => ({
    ...職能,
    強度: 最高人數 > 0 ? Number(((職能.人數 / 最高人數) * 100).toFixed(2)) : 0,
  }));
});

const 隊友關係摘要 = computed(() => {
  const 隊友列表 = 使用者隊友列表.value;
  const 最常同場隊友 = 隊友列表[0] || null;
  const 高頻隊友數 = 隊友列表.filter((隊友) => 隊友.同場次數 >= 2).length;
  const 總同場次數 = 隊友列表.reduce((總數, 隊友) => 總數 + 隊友.同場次數, 0);
  const 伺服器列表 = 隊友列表.map((隊友) => 隊友.server).filter(Boolean);
  const 伺服器數 = new Set(伺服器列表).size;
  const 主要副本 = 隊友副本交集.value[0] || null;
  const 最近同場時間 = 隊友列表
    .map((隊友) => 隊友.last_recorded_at_iso)
    .filter(Boolean)
    .sort()
    .at(-1);

  let 關係型態 = "同場分散";
  let 說明 = "公開同場資料多落在不同玩家或單次紀錄，較像副本野團或短期組隊紀錄。";

  if (高頻隊友數 >= 7 || (最常同場隊友?.同場次數 || 0) >= 4) {
    關係型態 = "重複同場明顯";
    說明 = "已有多位玩家重複同場，適合觀察主要副本、職能組成與近期合作軌跡。";
  } else if (高頻隊友數 >= 3) {
    關係型態 = "小隊輪廓";
    說明 = "有少數玩家重複出現，但還不到穩定名單，更適合用副本聚集與職能分布判讀。";
  } else if (主要副本?.teammate_count >= 7) {
    關係型態 = "副本聚集";
    說明 = "隊友主要集中在特定副本，代表該場公開紀錄對目前隊友關係的影響較高。";
  }

  return {
    最常同場隊友,
    高頻隊友數,
    總同場次數,
    伺服器數,
    主要副本,
    最近同場時間,
    關係型態,
    說明,
    職能種類數: 隊友職能分布.value.length,
  };
});

const 使用者徽章 = computed(() => {
  if (!使用者資料.value) {
    return [];
  }

  const 完整公開成績 = 使用者徽章副本成績.value.flatMap((副本) => 副本.public_entries || []);
  return 建立個人成績徽章({
    角色名稱: 使用者資料.value.character_name,
    公開成績: 完整公開成績,
    公開同場玩家數: 使用者資料.value.summary?.teammate_count,
    最後紀錄時間: 使用者資料.value.summary?.last_recorded_at_iso,
    近期動態基準時間: 近期動態基準時間.value,
    顯示作者徽章: 顯示作者相關標示,
    是網站作者,
    作者說明: 作者說明文字,
    取得職能代碼: (職業) => 職業所屬類型(職業)?.代碼 || "",
  });
});

const 隊友副本交集 = computed(() => {
  const 副本索引 = new Map();

  for (const 隊友 of 使用者隊友列表.value) {
    for (const 副本 of 隊友.encounters || []) {
      const key = 副本.encounter_key;
      if (!key) {
        continue;
      }

      const bucket = 副本索引.get(key) || {
        encounter_key: key,
        encounter_name: 副本.encounter_name || key,
        co_clear_count: 0,
        teammate_count: 0,
      };
      bucket.co_clear_count += 轉為數字(副本.co_clear_count) || 0;
      bucket.teammate_count += 1;
      副本索引.set(key, bucket);
    }
  }

  const 列表 = Array.from(副本索引.values()).sort((前一個, 後一個) => {
    if (前一個.co_clear_count !== 後一個.co_clear_count) {
      return 後一個.co_clear_count - 前一個.co_clear_count;
    }
    return 後一個.teammate_count - 前一個.teammate_count;
  });
  const 最高同場 = 列表[0]?.co_clear_count || 0;

  return 列表.slice(0, 6).map((副本) => ({
    ...副本,
    強度: 最高同場 > 0 ? Number(((副本.co_clear_count / 最高同場) * 100).toFixed(2)) : 0,
  }));
});

const 過濾後排行列 = computed(() => {
  const 查詢 = 解析使用者搜尋輸入(搜尋關鍵字.value);
  const 關鍵字 = 正規化搜尋比對文字(查詢.角色名稱);
  const 搜尋伺服器 = 正規化搜尋比對文字(查詢.伺服器);

  return 所有排行列.value.filter((列) => {
    const 符合伺服器 = (!伺服器篩選.value || 列.伺服器 === 伺服器篩選.value) && (!搜尋伺服器 || 正規化搜尋比對文字(列.伺服器) === 搜尋伺服器);
    const 符合職業 = 符合職業篩選(列.職業代碼);
    const 符合角色名稱 = !關鍵字 || 正規化搜尋比對文字(列.角色名稱).includes(關鍵字);

    return 符合伺服器 && 符合職業 && 符合角色名稱;
  });
});

const 總頁數 = computed(() => {
  return Math.max(Math.ceil(過濾後排行列.value.length / 每頁筆數), 1);
});

const 安全目前頁碼 = computed(() => {
  const 頁碼 = Number(目前頁碼.value);
  const 有效頁碼 = Number.isFinite(頁碼) ? Math.trunc(頁碼) : 1;
  return Math.min(Math.max(有效頁碼, 1), 總頁數.value);
});

const 有上一頁 = computed(() => 安全目前頁碼.value > 1);
const 有下一頁 = computed(() => 安全目前頁碼.value < 總頁數.value);

const 當頁起始索引 = computed(() => {
  return (安全目前頁碼.value - 1) * 每頁筆數;
});

const 當頁排行列 = computed(() => {
  return 過濾後排行列.value.slice(當頁起始索引.value, 當頁起始索引.value + 每頁筆數);
});

const 顯示起始排名 = computed(() => {
  return 過濾後排行列.value.length === 0 ? 0 : 當頁起始索引.value + 1;
});

const 顯示結束排名 = computed(() => {
  return Math.min(當頁起始索引.value + 當頁排行列.value.length, 過濾後排行列.value.length);
});

function 排行列顯示排名(index) {
  return 當頁起始索引.value + index + 1;
}

function 前往頁碼(頁碼) {
  const 目標頁碼 = Number(頁碼);
  if (!Number.isFinite(目標頁碼)) {
    return;
  }

  目前頁碼.value = Math.min(Math.max(Math.trunc(目標頁碼), 1), 總頁數.value);
}

function 前一頁() {
  前往頁碼(目前頁碼.value - 1);
}

function 下一頁() {
  前往頁碼(目前頁碼.value + 1);
}

// 下面的讀取函式只拿 Vite 靜態資源，不直接呼叫 FFLogs。
// FFLogs API 存取必須留在 Python Data Fetching Layer，避免前端洩漏憑證或繞過資料管線。
async function 讀取副本清單() {
  const 清單 = await 讀取Json(副本清單網址, "讀取副本清單失敗");
  副本清單.value = Array.isArray(清單) ? 清單.filter((副本) => 副本.enabled !== false) : [];

  const 副本鍵值有效 = 副本清單.value.some((副本) => 副本.key === 副本鍵值.value);
  if (!副本鍵值有效 && 副本清單.value[0]) {
    副本鍵值.value = 副本清單.value[0].key;
  }
}

async function 讀取排行榜資料() {
  讀取中.value = true;
  錯誤訊息.value = "";

  try {
    try {
      排行榜資料.value = await 解析排行榜資料格式(await 讀取Json(排行榜表格資料網址.value, "讀取排行榜薄索引失敗"));
    } catch {
      排行榜資料.value = await 解析排行榜資料格式(await 讀取Json(資料網址.value, "讀取失敗"));
    }
  } catch (錯誤) {
    錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取排行榜資料";
  } finally {
    讀取中.value = false;
  }
}

async function 讀取排行榜詳細資料檔(相對路徑) {
  if (!排行榜詳細資料快取.has(相對路徑)) {
    const 讀取Promise = 讀取Json(建立公開資料網址(相對路徑), "讀取排行榜報告細節失敗")
      .then(解析排行榜詳細資料格式)
      .catch((錯誤) => {
        排行榜詳細資料快取.delete(相對路徑);
        throw 錯誤;
      });
    排行榜詳細資料快取.set(相對路徑, 讀取Promise);
  }

  return 排行榜詳細資料快取.get(相對路徑);
}

async function 讀取排行列報告詳細資料(列) {
  const 相對路徑 = 排行榜資料.value?.detail_path;
  const detailId = 列?.detailId || 列?.id;
  if (!相對路徑 || !detailId) {
    return null;
  }

  const 詳細資料 = await 讀取排行榜詳細資料檔(相對路徑);
  return 詳細資料?.entries?.[detailId] || null;
}

async function 解析個人成績報告詳細資料格式(資料) {
  if (資料?.format && 資料.format !== "user_entry_details_v1") {
    throw new Error("個人成績報告細節格式不支援");
  }
  return 資料;
}

async function 讀取個人成績報告詳細資料檔(相對路徑) {
  if (!個人成績報告詳細資料快取.has(相對路徑)) {
    const 讀取Promise = 讀取使用者資料Json(相對路徑, "讀取個人成績報告細節失敗")
      .then(解析個人成績報告詳細資料格式)
      .catch((錯誤) => {
        個人成績報告詳細資料快取.delete(相對路徑);
        throw 錯誤;
      });
    個人成績報告詳細資料快取.set(相對路徑, 讀取Promise);
  }

  return 個人成績報告詳細資料快取.get(相對路徑);
}

async function 讀取個人成績報告詳細資料(成績) {
  const 相對路徑 = 成績?.report_detail_path;
  const detailId = 成績?.report_detail_id || 成績?.id;
  if (!相對路徑 || !detailId) {
    return null;
  }

  const 詳細資料 = await 讀取個人成績報告詳細資料檔(相對路徑);
  return 詳細資料?.entries?.[detailId] || null;
}

async function 讀取使用者索引() {
  if (使用者索引.value) {
    if (使用者搜尋建議索引.value.length === 0) {
      重建使用者搜尋建議索引();
    }
    return 使用者索引.value;
  }

  使用者索引.value = await 讀取Json(使用者索引網址, "讀取個人成績單索引失敗");
  重建使用者搜尋建議索引();
  return 使用者索引.value;
}

async function 讀取全服統計() {
  if (全服統計資料.value) {
    return 全服統計資料.value;
  }

  全服統計讀取中.value = true;
  全服統計錯誤訊息.value = "";

  try {
    全服統計資料.value = await 讀取Json(全服統計網址, "讀取全服統計失敗");
    return 全服統計資料.value;
  } catch (錯誤) {
    全服統計錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取全服統計";
    return null;
  } finally {
    全服統計讀取中.value = false;
  }
}

async function 讀取近期動態資料() {
  if (近期動態資料.value) {
    return 近期動態資料.value;
  }

  近期動態讀取中.value = true;
  近期動態錯誤訊息.value = "";

  try {
    近期動態資料.value = await 讀取Json(近期動態網址, "讀取近期動態失敗");
    return 近期動態資料.value;
  } catch (錯誤) {
    近期動態錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取近期動態";
    return null;
  } finally {
    近期動態讀取中.value = false;
  }
}

async function 讀取隊伍榜資料() {
  if (隊伍榜資料.value) {
    return 隊伍榜資料.value;
  }

  隊伍榜讀取中.value = true;
  隊伍榜錯誤訊息.value = "";

  try {
    隊伍榜資料.value = await 讀取Json(隊伍榜網址, "讀取隊伍榜失敗");
    套用隊伍榜有效副本鍵值();
    return 隊伍榜資料.value;
  } catch (錯誤) {
    隊伍榜錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取隊伍榜";
    return null;
  } finally {
    隊伍榜讀取中.value = false;
  }
}

function 套用伺服器對比預設值() {
  const 選項 = 伺服器對比選項.value;
  if (選項.length === 0) {
    伺服器對比左伺服器.value = "";
    伺服器對比右伺服器.value = "";
    return;
  }

  if (!選項.includes(伺服器對比左伺服器.value)) {
    伺服器對比左伺服器.value = 選項[0] || "";
  }
  if (!選項.includes(伺服器對比右伺服器.value) || (選項.length > 1 && 伺服器對比右伺服器.value === 伺服器對比左伺服器.value)) {
    伺服器對比右伺服器.value = 選項.find((伺服器) => 伺服器 !== 伺服器對比左伺服器.value) || 選項[0] || "";
  }
}

async function 讀取伺服器對比資料() {
  if (伺服器對比資料.value) {
    套用伺服器對比預設值();
    return 伺服器對比資料.value;
  }

  伺服器對比讀取中.value = true;
  伺服器對比錯誤訊息.value = "";

  try {
    伺服器對比資料.value = await 讀取Json(伺服器對比網址, "讀取伺服器對比失敗");
    套用伺服器對比預設值();
    return 伺服器對比資料.value;
  } catch (錯誤) {
    伺服器對比錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取伺服器對比資料";
    return null;
  } finally {
    伺服器對比讀取中.value = false;
  }
}

async function 讀取蜂蜂粉絲榜資料() {
  if (蜂蜂粉絲榜資料.value) {
    return 蜂蜂粉絲榜資料.value;
  }

  蜂蜂粉絲榜讀取中.value = true;
  蜂蜂粉絲榜錯誤訊息.value = "";

  try {
    蜂蜂粉絲榜資料.value = await 讀取Json(蜂蜂粉絲榜網址, "讀取 Honey B. Lovely 粉絲榜失敗");
    return 蜂蜂粉絲榜資料.value;
  } catch (錯誤) {
    蜂蜂粉絲榜錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取 Honey B. Lovely 粉絲榜資料";
    return null;
  } finally {
    蜂蜂粉絲榜讀取中.value = false;
  }
}

function 尋找使用者索引條目(角色名稱, 伺服器 = "") {
  return 尋找使用者索引條目於列表(使用者索引列表.value, 角色名稱, 伺服器);
}

function 更新分享網址(頁面, 額外狀態 = {}, 選項 = {}) {
  if (正在套用網址狀態 && !選項.強制) {
    return;
  }

  寫入網址狀態({ page: 頁面, ...額外狀態 }, 選項);
}

function 非預設分享值(值, 預設值) {
  const 文字 = String(值 ?? "").trim();
  return 文字 && 文字 !== 預設值 ? 文字 : "";
}

function 預設排行榜副本鍵值() {
  return 副本清單.value.some((副本) => 副本.key === 預設副本鍵值)
    ? 預設副本鍵值
    : 副本清單.value[0]?.key || 預設副本鍵值;
}

function 隊伍榜副本鍵值有效(副本鍵值) {
  return 隊伍榜副本列表.value.some((副本) => 副本.encounter_key === 副本鍵值);
}

function 套用隊伍榜有效副本鍵值() {
  if (隊伍榜副本鍵值有效(隊伍榜副本鍵值.value)) {
    return;
  }

  // 「全部副本最速」已從 UI 移除；舊分享網址或空值進來時一律回到
  // 目前指定的隊伍榜預設副本，避免使用者停在已不存在的選項。
  隊伍榜副本鍵值.value = 隊伍榜副本鍵值有效(預設隊伍榜副本鍵值)
    ? 預設隊伍榜副本鍵值
    : 隊伍榜副本列表.value[0]?.encounter_key || 預設隊伍榜副本鍵值;
}

function 排行榜排序分享狀態() {
  const 欄位 = 排序欄位.value;
  const 方向 = 排序方向.value;
  if (!顯示Gcd覆蓋率 && 欄位 === "gcdCoverage") {
    return {
      sort: "",
      order: "",
    };
  }
  const 是否預設排序 = 欄位 === 預設排序欄位 && 方向 === 預設排序方向;
  if (是否預設排序) {
    return {
      sort: "",
      order: "",
    };
  }

  return {
    sort: 欄位,
    order: 方向 === 排序欄位預設方向(欄位) ? "" : 方向,
  };
}

function 更新網址為使用者(角色名稱, 伺服器 = "", 選項 = {}) {
  更新分享網址("user", {
    user: 角色名稱,
    server: 伺服器,
  }, 選項);
}

function 更新網址為排行榜(選項 = {}) {
  更新分享網址("ranking", {
    encounter: 非預設分享值(副本鍵值.value, 預設排行榜副本鍵值()),
    server: 伺服器篩選.value,
    jobType: 職業類型篩選.value,
    job: 職業篩選.value,
    q: 搜尋關鍵字.value,
    ...排行榜排序分享狀態(),
    pageNo: 目前頁碼.value > 1 ? 目前頁碼.value : "",
    version: 非預設分享值(有效排行榜版本範圍.value, 預設版本紀錄範圍),
  }, 選項);
}

function 更新網址為全服統計(選項 = {}) {
  更新分享網址("stats", {
    encounter: 非預設分享值(統計副本鍵值.value, 預設統計副本鍵值),
    server: 統計伺服器篩選.value,
    jobScope: 非預設分享值(統計職業範圍.value, 預設統計職業範圍),
    split: 非預設分享值(伺服器拆分模式.value, 預設伺服器拆分模式),
    metric: 非預設分享值(統計傷害指標.value, 預設統計傷害指標),
    version: 非預設分享值(有效統計版本範圍.value, 預設版本紀錄範圍),
  }, 選項);
}

function 更新網址為角色比較(選項 = {}) {
  更新分享網址("compare", {
    left: 比較角色左輸入.value,
    right: 比較角色右輸入.value,
    role: 非預設分享值(比較職能篩選.value, 預設比較職能),
    encounter: 非預設分享值(比較副本鍵值.value, 預設比較副本鍵值),
    version: 非預設分享值(有效比較版本範圍.value, 預設版本紀錄範圍),
  }, 選項);
}

function 更新網址為職業分析(選項 = {}) {
  const 範圍類型 = 職業分析目前範圍類型.value;
  更新分享網址("jobs", {
    job: 範圍類型 === "job" ? 職業分析目前職業代碼.value : "",
    jobScope: 範圍類型 === "role" ? 職業分析目前範圍代碼.value : "",
  }, 選項);
}

function 更新網址為近期動態(選項 = {}) {
  更新分享網址("activity", {}, 選項);
}

function 更新網址為隊伍榜(選項 = {}) {
  更新分享網址("teams", {
    encounter: 非預設分享值(隊伍榜副本鍵值.value, 預設隊伍榜副本鍵值),
    version: 非預設分享值(有效隊伍榜版本範圍.value, 預設版本紀錄範圍),
  }, 選項);
}

function 更新網址為伺服器對比(選項 = {}) {
  更新分享網址("servers", {
    left: 伺服器對比左伺服器.value,
    right: 伺服器對比右伺服器.value,
  }, 選項);
}

function 更新網址為蜂蜂粉絲榜(選項 = {}) {
  if (!啟用Honey粉絲榜.value) {
    更新網址為排行榜(選項);
    return;
  }
  更新分享網址("honey-fans", {}, 選項);
}

function 設定分享狀態(訊息) {
  分享狀態訊息.value = 訊息;
  if (typeof window !== "undefined" && 分享狀態計時器) {
    window.clearTimeout(分享狀態計時器);
    分享狀態計時器 = null;
  }

  if (typeof window !== "undefined" && 訊息) {
    分享狀態計時器 = window.setTimeout(() => {
      分享狀態訊息.value = "";
      分享狀態計時器 = null;
    }, 2600);
  }
}

async function 分享目前頁面() {
  if (正在分享.value) {
    return;
  }

  const 分享內容 = {
    title: 分享資訊.value.title,
    text: 分享資訊.value.description,
    url: 建立目前分享網址(),
  };

  正在分享.value = true;
  try {
    if (typeof navigator !== "undefined" && typeof navigator.share === "function") {
      await navigator.share(分享內容);
      設定分享狀態("已開啟系統分享面板");
      return;
    }

    if (typeof navigator !== "undefined" && navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(分享內容.url);
      設定分享狀態("已複製分享連結");
      return;
    }

    if (typeof window !== "undefined") {
      window.prompt("複製分享連結", 分享內容.url);
      設定分享狀態("已開啟複製視窗");
    }
  } catch (錯誤) {
    if (錯誤?.name !== "AbortError") {
      設定分享狀態("無法自動分享，請手動複製網址");
    }
  } finally {
    正在分享.value = false;
  }
}

async function 載入使用者成績(角色名稱, 伺服器 = "", 選項 = {}) {
  const 查詢名稱 = String(角色名稱 || "").trim();
  if (!查詢名稱) {
    使用者錯誤訊息.value = "請輸入玩家名稱";
    return;
  }

  const 原始搜尋文字 = 伺服器 ? 格式化使用者搜尋文字(查詢名稱, 伺服器) : 查詢名稱;
  頁面模式.value = "user";
  使用者讀取中.value = true;
  使用者錯誤訊息.value = "";
  使用者搜尋關鍵字.value = 原始搜尋文字;

  try {
    await 讀取使用者索引();
    const 搜尋目標 = 解析使用者搜尋目標(原始搜尋文字, 使用者索引列表.value);
    使用者資料.value = await 讀取使用者資料檔(搜尋目標.角色名稱, 使用者索引列表.value, 搜尋目標.伺服器);
    const 伺服器列表 = Array.isArray(使用者資料.value?.servers) ? 使用者資料.value.servers : [];
    使用者伺服器篩選.value = 伺服器列表.includes(搜尋目標.伺服器) ? 搜尋目標.伺服器 : 伺服器列表[0] || "";
    使用者搜尋關鍵字.value = 格式化使用者搜尋文字(使用者資料.value.character_name || 查詢名稱, 使用者伺服器篩選.value);
    記錄玩家搜尋歷史(使用者資料.value.character_name || 查詢名稱, 使用者伺服器篩選.value);

    if (選項.更新網址 !== false) {
      更新網址為使用者(使用者資料.value.character_name || 查詢名稱, 使用者伺服器篩選.value);
    }
    讀取全服統計();
  } catch (錯誤) {
    使用者資料.value = null;
    使用者錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單";
  } finally {
    使用者讀取中.value = false;
  }
}

async function 載入比較角色資料(輸入文字) {
  const 查詢 = 解析使用者搜尋輸入(輸入文字);
  if (!查詢.角色名稱) {
    throw new Error("請輸入兩個玩家名稱");
  }

  await 讀取使用者索引();
  const 搜尋目標 = 解析使用者搜尋目標(輸入文字, 使用者索引列表.value);
  const 資料 = await 讀取使用者資料檔(搜尋目標.角色名稱, 使用者索引列表.value, 搜尋目標.伺服器);
  const 伺服器列表 = Array.isArray(資料?.servers) ? 資料.servers : [];
  const 伺服器 = 伺服器列表.includes(搜尋目標.伺服器) ? 搜尋目標.伺服器 : 伺服器列表[0] || "";
  return {
    資料,
    伺服器,
  };
}

async function 提交角色比較(選項 = {}) {
  const 左輸入 = 比較角色左輸入.value.trim();
  const 右輸入 = 比較角色右輸入.value.trim();
  if (!左輸入 || !右輸入) {
    比較錯誤訊息.value = "請輸入兩個玩家名稱";
    return;
  }

  比較讀取中.value = true;
  比較錯誤訊息.value = "";

  try {
    const [左結果, 右結果] = await Promise.all([載入比較角色資料(左輸入), 載入比較角色資料(右輸入)]);
    比較角色左資料.value = 左結果.資料;
    比較角色右資料.value = 右結果.資料;
    比較角色左伺服器.value = 左結果.伺服器;
    比較角色右伺服器.value = 右結果.伺服器;
    比較角色左輸入.value = 格式化使用者搜尋文字(左結果.資料.character_name || 左輸入, 左結果.伺服器);
    比較角色右輸入.value = 格式化使用者搜尋文字(右結果.資料.character_name || 右輸入, 右結果.伺服器);
    記錄玩家搜尋歷史(左結果.資料.character_name || 左輸入, 左結果.伺服器);
    記錄玩家搜尋歷史(右結果.資料.character_name || 右輸入, 右結果.伺服器);
    if (選項.更新網址 !== false) {
      更新網址為角色比較();
    }
  } catch (錯誤) {
    比較角色左資料.value = null;
    比較角色右資料.value = null;
    比較錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取玩家比較資料";
  } finally {
    比較讀取中.value = false;
  }
}

function 切換主題() {
  if (停用主題切換.value) {
    return;
  }

  切換使用者主題();
}

function 讀取分位顯示偏好() {
  if (typeof window === "undefined") {
    return 預設分位顯示模式;
  }

  return 正規化分位顯示模式(window.localStorage.getItem(分位顯示偏好儲存鍵));
}

function 套用分位顯示模式(模式, { 寫入偏好 = true } = {}) {
  const 有效模式 = 正規化分位顯示模式(模式);
  分位顯示模式.value = 有效模式;

  if (寫入偏好 && typeof window !== "undefined") {
    window.localStorage.setItem(分位顯示偏好儲存鍵, 有效模式);
  }
}

function 初始化分位顯示偏好() {
  套用分位顯示模式(讀取分位顯示偏好(), { 寫入偏好: false });
}

function 設定分位顯示模式(模式) {
  套用分位顯示模式(模式, { 寫入偏好: true });
}

function 切換分位顯示模式() {
  設定分位顯示模式(使用PR分位顯示.value ? 分位顯示模式前段 : 分位顯示模式PR);
}

function 讀取說明提示顯示偏好() {
  if (typeof window === "undefined") {
    return true;
  }

  // 舊訪客沒有這個鍵值時維持顯示，讓新功能不會意外拿走既有的欄位說明。
  return window.localStorage.getItem(說明提示顯示偏好儲存鍵) !== "disabled";
}

function 套用說明提示顯示(啟用, { 寫入偏好 = true } = {}) {
  const 顯示提示 = Boolean(啟用);
  顯示說明提示.value = 顯示提示;

  // 說明提示也會出現在 Teleport 到 body 的報告彈窗中；寫到根節點可讓一般頁面與彈窗同步套用同一個偏好。
  if (typeof document !== "undefined") {
    document.documentElement.dataset.showHelpTooltips = String(顯示提示);
  }

  if (寫入偏好 && typeof window !== "undefined") {
    window.localStorage.setItem(說明提示顯示偏好儲存鍵, 顯示提示 ? "enabled" : "disabled");
  }
}

function 初始化說明提示顯示偏好() {
  套用說明提示顯示(讀取說明提示顯示偏好(), { 寫入偏好: false });
}

function 設定說明提示顯示(啟用) {
  套用說明提示顯示(啟用, { 寫入偏好: true });
}

function 讀取蜂蜂背景音樂偏好() {
  if (typeof window === "undefined") {
    return null;
  }

  const 已儲存偏好 = window.localStorage.getItem(蜂蜂背景音樂偏好儲存鍵);
  if (已儲存偏好 === "enabled") {
    return true;
  }
  if (已儲存偏好 === "disabled") {
    return false;
  }
  return null;
}

function 套用蜂蜂背景音樂偏好(啟用, { 寫入偏好 = false } = {}) {
  蜂蜂背景音樂啟用.value = Boolean(啟用);
  蜂蜂背景音樂偏好已設定.value = true;
  顯示蜂蜂背景音樂詢問.value = false;

  if (寫入偏好 && typeof window !== "undefined") {
    window.localStorage.setItem(蜂蜂背景音樂偏好儲存鍵, 啟用 ? "enabled" : "disabled");
  }
}

function 準備蜂蜂背景音樂偏好() {
  const 已儲存偏好 = 讀取蜂蜂背景音樂偏好();
  if (已儲存偏好 === null) {
    蜂蜂背景音樂啟用.value = false;
    蜂蜂背景音樂偏好已設定.value = false;
    顯示蜂蜂背景音樂詢問.value = true;
    return;
  }

  套用蜂蜂背景音樂偏好(已儲存偏好);
}

function 設定蜂蜂背景音樂偏好(啟用) {
  套用蜂蜂背景音樂偏好(啟用, { 寫入偏好: true });
}

function 切換蜂蜂背景音樂() {
  設定蜂蜂背景音樂偏好(!蜂蜂背景音樂啟用.value);
}

function 切換到排行榜() {
  頁面模式.value = "ranking";
  更新網址為排行榜();
}

function 切換到全服統計() {
  頁面模式.value = "stats";
  更新網址為全服統計();
  讀取全服統計();
}

function 切換到個人成績單() {
  頁面模式.value = "user";
  更新分享網址("user", {});
  讀取使用者索引().catch((錯誤) => {
    使用者錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單索引";
  });
}

function 切換到角色比較() {
  頁面模式.value = "compare";
  更新網址為角色比較();
  讀取使用者索引().catch((錯誤) => {
    比較錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單索引";
  });
}

function 切換到職業分析() {
  頁面模式.value = "jobs";
  更新網址為職業分析();
  讀取全服統計();
}

function 切換到近期動態() {
  頁面模式.value = "activity";
  更新網址為近期動態();
  近期動態錯誤訊息.value = "";
  讀取近期動態資料();
  讀取使用者索引().catch(() => {});
}

function 切換到隊伍榜() {
  頁面模式.value = "teams";
  更新網址為隊伍榜();
  讀取隊伍榜資料();
}

function 切換到伺服器對比() {
  頁面模式.value = "servers";
  更新網址為伺服器對比();
  讀取伺服器對比資料();
}

function 切換到常見問題() {
  頁面模式.value = "faq";
  更新分享網址("faq", {});
}

function 切換到Logs檢查() {
  切換到常見問題();
}

function 切換到蜂蜂粉絲榜() {
  if (!啟用Honey粉絲榜.value) {
    切換到排行榜();
    return;
  }
  頁面模式.value = "honey-fans";
  更新網址為蜂蜂粉絲榜();
  蜂蜂粉絲榜錯誤訊息.value = "";
  準備蜂蜂背景音樂偏好();
  讀取蜂蜂粉絲榜資料();
}

function 選擇隊伍榜副本(副本鍵值) {
  隊伍榜副本鍵值.value = 副本鍵值 || 預設隊伍榜副本鍵值;
  隊伍榜副本選單開啟.value = false;
  if (隊伍榜資料.value) {
    套用隊伍榜有效副本鍵值();
  }
  if (頁面模式.value === "teams") {
    更新網址為隊伍榜({ replace: true });
  }
}

function 交換伺服器對比() {
  const 原左 = 伺服器對比左伺服器.value;
  伺服器對比左伺服器.value = 伺服器對比右伺服器.value;
  伺服器對比右伺服器.value = 原左;
  if (頁面模式.value === "servers") {
    更新網址為伺服器對比({ replace: true });
  }
}

function 提交使用者搜尋() {
  const 查詢 = 解析使用者搜尋輸入(使用者搜尋關鍵字.value);
  載入使用者成績(查詢.角色名稱, 查詢.伺服器);
}

function 開啟個人成績單(列) {
  載入使用者成績(列.角色名稱, 列.伺服器);
}

function 開啟隊友成績單(隊友) {
  載入使用者成績(隊友.character_name, 隊友.server);
}

function 是網站作者(角色名稱) {
  return String(角色名稱 || "").trim() === 作者角色名稱;
}

function 套用排行榜網址狀態(網址狀態) {
  頁面模式.value = "ranking";
  副本鍵值.value = 網址狀態.encounter || 預設排行榜副本鍵值();
  伺服器篩選.value = 網址狀態.server || "";
  職業類型篩選.value = 網址狀態.jobType || "";
  職業篩選.value = 網址狀態.job || "";
  搜尋關鍵字.value = 網址狀態.q || "";
  排行榜版本範圍.value = 正規化版本紀錄範圍(網址狀態.version);

  if (排序欄位標籤[網址狀態.sort] && (顯示Gcd覆蓋率 || 網址狀態.sort !== "gcdCoverage")) {
    排序欄位.value = 網址狀態.sort;
    排序方向.value = ["asc", "desc"].includes(網址狀態.order) ? 網址狀態.order : 排序欄位預設方向(網址狀態.sort);
  } else {
    排序欄位.value = 預設排序欄位;
    排序方向.value = ["asc", "desc"].includes(網址狀態.order) ? 網址狀態.order : 預設排序方向;
  }

  const 分享頁碼 = Number.parseInt(網址狀態.pageNo, 10);
  目前頁碼.value = Number.isFinite(分享頁碼) && 分享頁碼 > 0 ? 分享頁碼 : 1;
}

async function 套用統計網址狀態(網址狀態) {
  頁面模式.value = "stats";
  統計副本鍵值.value = 網址狀態.encounter || 預設統計副本鍵值;
  統計版本範圍.value = 正規化版本紀錄範圍(網址狀態.version);
  統計伺服器篩選.value = 網址狀態.server || "";
  統計職業範圍.value = 網址狀態.jobScope || 預設統計職業範圍;
  伺服器拆分模式.value = ["none", "role", "job"].includes(網址狀態.split) ? 網址狀態.split : 預設伺服器拆分模式;
  統計傷害指標.value = ["dps", "rdps", "adps"].includes(網址狀態.metric) ? 網址狀態.metric : 預設統計傷害指標;
  await 讀取全服統計();
}

async function 套用個人成績單網址狀態(網址狀態) {
  頁面模式.value = "user";
  if (網址狀態.user) {
    await 載入使用者成績(網址狀態.user, 網址狀態.server, { 更新網址: false });
    return;
  }

  await 讀取使用者索引().catch((錯誤) => {
    使用者錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單索引";
  });
}

async function 套用角色比較網址狀態(網址狀態) {
  頁面模式.value = "compare";
  比較角色左輸入.value = 網址狀態.left || "";
  比較角色右輸入.value = 網址狀態.right || "";
  比較副本鍵值.value = 網址狀態.encounter || 預設比較副本鍵值;
  比較版本範圍.value = 正規化版本紀錄範圍(網址狀態.version);
  if (比較職能索引.has(網址狀態.role)) {
    比較職能篩選.value = 網址狀態.role;
  } else {
    比較職能篩選.value = 預設比較職能;
  }

  if (網址狀態.left && 網址狀態.right) {
    await 提交角色比較({ 更新網址: false });
    return;
  }

  比較角色左資料.value = null;
  比較角色右資料.value = null;
  await 讀取使用者索引().catch((錯誤) => {
    比較錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單索引";
  });
}

async function 套用職業分析網址狀態(網址狀態) {
  頁面模式.value = "jobs";
  職業分析職業.value = 網址狀態.job || 網址狀態.jobScope || 預設職業分析範圍;
  await 讀取全服統計();
  if (職業分析目前範圍代碼.value !== String(職業分析職業.value || "").trim() && 職業分析預設範圍代碼.value) {
    職業分析職業.value = 職業分析預設範圍代碼.value;
  }
  更新網址為職業分析({ replace: true, 強制: true });
}

async function 套用近期動態網址狀態() {
  頁面模式.value = "activity";
  近期動態錯誤訊息.value = "";
  await 讀取近期動態資料();
  讀取使用者索引().catch(() => {});
}

async function 套用隊伍榜網址狀態(網址狀態) {
  頁面模式.value = "teams";
  隊伍榜副本鍵值.value = 網址狀態.encounter || 預設隊伍榜副本鍵值;
  隊伍榜版本範圍.value = 正規化版本紀錄範圍(網址狀態.version);
  await 讀取隊伍榜資料();
  套用隊伍榜有效副本鍵值();
  更新網址為隊伍榜({ replace: true, 強制: true });
}

async function 套用伺服器對比網址狀態(網址狀態) {
  頁面模式.value = "servers";
  伺服器對比左伺服器.value = 網址狀態.left || "";
  伺服器對比右伺服器.value = 網址狀態.right || "";
  await 讀取伺服器對比資料();
  更新網址為伺服器對比({ replace: true, 強制: true });
}

async function 套用蜂蜂粉絲榜網址狀態() {
  if (!啟用Honey粉絲榜.value) {
    切換到排行榜();
    return;
  }
  頁面模式.value = "honey-fans";
  蜂蜂粉絲榜錯誤訊息.value = "";
  準備蜂蜂背景音樂偏好();
  await 讀取蜂蜂粉絲榜資料();
}

async function 套用網址狀態(網址狀態 = 讀取目前網址狀態()) {
  // URL 是分享入口，也是瀏覽器上一頁/下一頁的狀態來源。套用期間暫停寫回，
  // 避免 popstate 讀取舊網址後又立刻 push 一筆新歷史紀錄。
  正在套用網址狀態 = true;
  try {
    if (網址狀態.page === "stats") {
      await 套用統計網址狀態(網址狀態);
    } else if (網址狀態.page === "user") {
      await 套用個人成績單網址狀態(網址狀態);
    } else if (網址狀態.page === "compare") {
      await 套用角色比較網址狀態(網址狀態);
    } else if (網址狀態.page === "jobs") {
      await 套用職業分析網址狀態(網址狀態);
    } else if (網址狀態.page === "activity") {
      await 套用近期動態網址狀態();
    } else if (網址狀態.page === "teams") {
      await 套用隊伍榜網址狀態(網址狀態);
    } else if (網址狀態.page === "servers") {
      await 套用伺服器對比網址狀態(網址狀態);
    } else if (網址狀態.page === "faq" || 網址狀態.page === "logs") {
      頁面模式.value = "faq";
    } else if (網址狀態.page === "honey-fans" && 啟用Honey粉絲榜.value) {
      await 套用蜂蜂粉絲榜網址狀態();
    } else if (網址狀態.page === "honey-fans") {
      切換到排行榜();
    } else {
      套用排行榜網址狀態(網址狀態);
    }
  } finally {
    await Promise.resolve();
    正在套用網址狀態 = false;
  }
}

function 處理瀏覽紀錄變更() {
  套用網址狀態();
}

watch(副本鍵值, () => {
  if (!正在套用網址狀態) {
    if (!副本支援版本篩選(目前副本.value)) {
      排行榜版本範圍.value = 預設版本紀錄範圍;
    }
    // 伺服器與職業是玩家刻意設定的跨副本觀察條件，切副本時只回到第一頁，不主動清空篩選。
    目前頁碼.value = 1;
  }
  if (副本清單.value.length > 0) {
    讀取排行榜資料();
  }
  if (頁面模式.value === "ranking") {
    更新網址為排行榜({ replace: true });
  }
});

watch(排行榜版本範圍, () => {
  if (!正在套用網址狀態) {
    目前頁碼.value = 1;
  }
  if (頁面模式.value === "ranking") {
    更新網址為排行榜({ replace: true });
  }
});

watch(職業類型篩選, () => {
  if (!正在套用網址狀態) {
    職業篩選.value = "";
  }
});

watch([伺服器篩選, 職業類型篩選, 職業篩選, 搜尋關鍵字, 排序欄位, 排序方向], () => {
  if (!正在套用網址狀態) {
    目前頁碼.value = 1;
  }
  if (頁面模式.value === "ranking") {
    更新網址為排行榜({ replace: true });
  }
});

watch(總頁數, (新總頁數) => {
  if (!Number.isFinite(Number(目前頁碼.value)) || 目前頁碼.value < 1) {
    目前頁碼.value = 1;
    return;
  }

  if (目前頁碼.value > 新總頁數) {
    目前頁碼.value = 新總頁數;
  }
});

watch(目前頁碼, () => {
  if (頁面模式.value === "ranking") {
    更新網址為排行榜({ replace: true });
  }
});

watch(使用者伺服器篩選, (伺服器) => {
  if (頁面模式.value === "user" && 使用者資料.value?.character_name) {
    更新網址為使用者(使用者資料.value.character_name, 伺服器, { replace: true });
  }
});

watch([使用者資料, 使用者伺服器篩選, 使用者職業類型篩選, 使用者職業篩選], () => {
  使用者趨勢職業選擇.value = {};
});

watch([使用者資料, 使用者伺服器篩選, 使用者職業類型選項], () => {
  if (使用者職業類型篩選.value && !使用者職業類型選項.value.some((職能) => 職能.代碼 === 使用者職業類型篩選.value)) {
    使用者職業類型篩選.value = "";
  }
});

watch([使用者職業類型篩選, 使用者職業選項], () => {
  if (使用者職業篩選.value && !使用者職業選項.value.some((職業) => 職業.job === 使用者職業篩選.value)) {
    使用者職業篩選.value = "";
  }
});

watch([統計副本鍵值, 全服統計資料], () => {
  if (!正在套用網址狀態 && !副本支援版本篩選(目前統計副本.value)) {
    統計版本範圍.value = 預設版本紀錄範圍;
  }

  if (統計伺服器篩選.value && !統計伺服器可識別(統計伺服器篩選.value)) {
    統計伺服器篩選.value = "";
  }

  if (!統計職業範圍可識別(統計職業範圍.value)) {
    統計職業範圍.value = "all";
  }

  if (頁面模式.value === "stats") {
    更新網址為全服統計({ replace: true });
  }
});

watch([統計副本鍵值, 統計版本範圍, 統計伺服器篩選, 統計職業範圍, 伺服器拆分模式, 統計傷害指標], () => {
  if (頁面模式.value === "stats") {
    更新網址為全服統計({ replace: true });
  }
});

watch([全服統計資料, 職業分析職業選項], () => {
  if (職業分析目前範圍代碼.value !== String(職業分析職業.value || "").trim() && 職業分析預設範圍代碼.value) {
    職業分析職業.value = 職業分析預設範圍代碼.value;
  }
  if (職業分析展示類型.value && !職業分析職業分組.value.some((群組) => 群組.代碼 === 職業分析展示類型.value)) {
    職業分析展示類型.value = "";
  }
  if (頁面模式.value === "jobs" && 職業分析目前範圍代碼.value) {
    更新網址為職業分析({ replace: true });
  }
});

watch([比較職能篩選, 比較副本鍵值, 比較版本範圍], () => {
  if (!正在套用網址狀態 && !副本支援版本篩選(目前比較副本.value)) {
    比較版本範圍.value = 預設版本紀錄範圍;
  }
  if (頁面模式.value === "compare") {
    更新網址為角色比較({ replace: true });
  }
});

watch(職業分析職業, () => {
  if (頁面模式.value === "jobs") {
    更新網址為職業分析({ replace: true });
  }
});

watch(隊伍榜副本鍵值, () => {
  if (!正在套用網址狀態 && !副本支援版本篩選(目前隊伍榜副本.value)) {
    隊伍榜版本範圍.value = 預設版本紀錄範圍;
  }
  if (頁面模式.value === "teams") {
    更新網址為隊伍榜({ replace: true });
  }
});

watch(隊伍榜版本範圍, () => {
  if (頁面模式.value === "teams") {
    更新網址為隊伍榜({ replace: true });
  }
});

watch([伺服器對比左伺服器, 伺服器對比右伺服器], () => {
  if (伺服器對比左伺服器.value === 伺服器對比右伺服器.value && 伺服器對比選項.value.length > 1) {
    伺服器對比右伺服器.value = 伺服器對比選項.value.find((伺服器) => 伺服器 !== 伺服器對比左伺服器.value) || "";
    return;
  }
  if (頁面模式.value === "servers") {
    更新網址為伺服器對比({ replace: true });
  }
});

watch(頁面模式, (目前頁面模式) => {
  if (目前頁面模式 === "honey-fans" && !啟用Honey粉絲榜.value) {
    切換到排行榜();
    return;
  }
  if (目前頁面模式 === "honey-fans") {
    準備蜂蜂背景音樂偏好();
    return;
  }

  顯示蜂蜂背景音樂詢問.value = false;
});

onMounted(() => {
  初始化主題();
  初始化分位顯示偏好();
  初始化說明提示顯示偏好();
  初始化玩家搜尋歷史();
  if (typeof window !== "undefined") {
    window.addEventListener("popstate", 處理瀏覽紀錄變更);
  }
  套用網址狀態();

  讀取中.value = true;
  錯誤訊息.value = "";
  讀取副本清單()
    .then(() => 讀取排行榜資料())
    .catch((錯誤) => {
      錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取副本清單";
      讀取中.value = false;
    });
});

onUnmounted(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("popstate", 處理瀏覽紀錄變更);
    if (分享狀態計時器) {
      window.clearTimeout(分享狀態計時器);
      分享狀態計時器 = null;
    }
  }
});

  return {
    排行榜資料,
    副本清單,
    副本鍵值,
    副本選單開啟,
    讀取中,
    錯誤訊息,
    伺服器篩選,
    職業類型篩選,
    職業篩選,
    職業選單開啟,
    主色模式,
    搜尋關鍵字,
    玩家搜尋歷史,
    目前玩家搜尋歷史欄位,
    玩家搜尋歷史管理彈窗開啟,
    排序欄位,
    排序方向,
    排行榜版本範圍,
    目前頁碼,
    每頁筆數,
    主題模式,
    主題儲存鍵,
    頁面模式,
    顯示作者相關標示,
    顯示Gcd覆蓋率,
    分位顯示偏好儲存鍵,
    說明提示顯示偏好儲存鍵,
    分位顯示模式選項,
    分位顯示模式,
    顯示說明提示,
    使用PR分位顯示,
    作者說明文字,
    使用者索引,
    使用者資料,
    使用者搜尋關鍵字,
    使用者伺服器篩選,
    使用者職業類型篩選,
    使用者職業篩選,
    使用者職業選單開啟,
    使用者趨勢職業選擇,
    使用者簡表模式,
    使用者簡表版本,
    使用者簡表零式量級,
    使用者讀取中,
    使用者錯誤訊息,
    比較角色左輸入,
    比較角色右輸入,
    比較角色左資料,
    比較角色右資料,
    比較角色左伺服器,
    比較角色右伺服器,
    比較職能篩選,
    比較副本鍵值,
    比較副本選單開啟,
    比較版本範圍,
    比較讀取中,
    比較錯誤訊息,
    全服統計資料,
    全服統計讀取中,
    全服統計錯誤訊息,
    統計副本鍵值,
    統計副本選單開啟,
    統計版本範圍,
    統計伺服器篩選,
    統計職業範圍,
    統計職業選單開啟,
    伺服器拆分模式,
    統計傷害指標,
    職業傷害提示鎖定職業,
    職業傷害提示互動職業,
    職業分析職業,
    職業分析選單開啟,
    近期動態資料,
    近期動態讀取中,
    近期動態錯誤訊息,
    近期動態日誌副本鍵值,
    近期動態日誌副本選單開啟,
    近期動態日誌時間範圍,
    近期動態日誌指標,
    近期動態日誌自訂開始日期,
    近期動態日誌自訂結束日期,
    近期動態日誌提示鎖定,
    隊伍榜資料,
    隊伍榜讀取中,
    隊伍榜錯誤訊息,
    隊伍榜副本鍵值,
    隊伍榜副本選單開啟,
    隊伍榜版本範圍,
    伺服器對比資料,
    伺服器對比讀取中,
    伺服器對比錯誤訊息,
    伺服器對比左伺服器,
    伺服器對比右伺服器,
    蜂蜂粉絲榜資料,
    蜂蜂粉絲榜讀取中,
    蜂蜂粉絲榜錯誤訊息,
    蜂蜂背景音樂啟用,
    蜂蜂背景音樂偏好已設定,
    顯示蜂蜂背景音樂詢問,
    蜂蜂背景音樂偏好儲存鍵,
    蜂蜂背景音樂影片Id,
    蜂蜂背景音樂嵌入網址,
    分享狀態訊息,
    正在分享,
    副本清單網址,
    使用者索引網址,
    全服統計網址,
    近期動態網址,
    隊伍榜網址,
    伺服器對比網址,
    蜂蜂粉絲榜網址,
    目前副本,
    資料網址,
    排行榜表格資料網址,
    傷害比較指標選項,
    版本紀錄範圍選項,
    個人成績簡表版本選項,
    副本分類順序,
    副本分組,
    統計副本分組,
    比較副本分組,
    副本選單文字,
    顯示排行榜版本篩選,
    有效排行榜版本範圍,
    排行榜版本說明文字,
    取得版本紀錄範圍文字,
    套用主題,
    套用暫時主題,
    停用主題切換,
    切換主題,
    主題按鈕文字,
    目前主題文字,
    目前分位顯示模式文字,
    分位顯示切換標籤,
    前段四分位標籤,
    設定分位顯示模式,
    切換分位顯示模式,
    設定說明提示顯示,
    職業繁中名稱,
    職業群組設定,
    職業群組索引,
    比較職能設定,
    比較職能索引,
    顯示職業名稱,
    職業Icon路徑,
    職業類型Icon路徑,
    隱藏載入失敗圖片,
    職業色彩類別,
    職業代碼色彩,
    職業比較圖色彩,
    職業類型色彩,
    職業類型排序值,
    職業所屬類型,
    取得比較職能,
    目前職業主色,
    排名色彩類別,
    符合職業篩選,
    清除職業篩選,
    選擇職業類型,
    選擇職業,
    切換職業選單,
    處理職業選單失焦,
    清除使用者職業篩選,
    選擇使用者職業類型,
    選擇使用者職業,
    選擇使用者趨勢職業,
    切換使用者簡表模式,
    設定使用者簡表版本,
    設定使用者簡表零式量級,
    切換使用者職業選單,
    處理使用者職業選單失焦,
    切換副本選單,
    選擇副本,
    處理副本選單失焦,
    切換統計副本選單,
    選擇統計副本,
    處理統計副本選單失焦,
    切換比較副本選單,
    選擇比較副本,
    處理比較副本選單失焦,
    清除統計職業範圍,
    選擇統計職業類型,
    選擇統計職業,
    切換統計職業選單,
    處理統計職業選單失焦,
    切換職業分析選單,
    選擇職業分析類型,
    選擇職業分析職業,
    處理職業分析選單失焦,
    格式化傷害數值,
    格式化Active,
    格式化Gcd覆蓋率,
    格式化整數,
    格式化帶號整數,
    格式化帶號百分比,
    格式化百分比,
    格式化前段百分位,
    格式化PR值,
    格式化目前同職分位,
    格式化目前排名分位,
    同職分位色彩類別,
    簡表PR色彩類別,
    排名分位色彩類別,
    格式化通關時間,
    解析紀錄日期,
    格式化紀錄時間,
    格式化紀錄日期,
    格式化紀錄時刻,
    格式化排名,
    建立公開資料網址,
    轉為數字,
    比例條樣式,
    趨勢點樣式,
    計算Active百分比,
    排序欄位標籤,
    排序預設方向,
    排序欄位預設方向,
    排序方向文字,
    下一個排序方向,
    切換排序,
    是否目前排序,
    排序方向圖示,
    排序ARIA,
    排序按鈕標籤,
    排序數值,
    比較排行列,
    建立排行列,
    讀取排行列報告詳細資料,
    讀取個人成績報告詳細資料,
    成績是否較佳,
    使用者成績是否較佳,
    只保留角色最佳成績,
    展開排行榜列,
    所有排行列,
    伺服器選項,
    職業選項,
    職業類型選項,
    目前職業類型,
    職業選單文字,
    職業選單Icon路徑,
    全服統計副本列表,
    目前統計副本,
    統計範圍文字,
    統計副本選單文字,
    顯示統計版本篩選,
    有效統計版本範圍,
    顯示零式進度漏斗,
    顯示副本通關概覽,
    目前統計來源,
    傷害比較指標標籤,
    職業傷害提示作用職業,
    職業傷害比較資料來源,
    職業傷害比較條件文字,
    職業傷害比較基礎列,
    職業傷害比較值域,
    職業傷害位置,
    職業傷害比較刻度,
    職業傷害比較列,
    職業傷害提示文字,
    顯示職業傷害提示,
    隱藏職業傷害提示,
    切換職業傷害提示,
    職業範圍類型,
    取得統計計數,
    取得職業範圍文字,
    伺服器佔比單位,
    統計伺服器選項,
    統計職業範圍選項,
    統計職業範圍類型代碼,
    統計職業範圍職業代碼,
    統計職業類型選項,
    統計職業選項,
    統計職業選單文字,
    統計職業選單Icon路徑,
    統計伺服器文字,
    統計條件文字,
    全服概要項目,
    統計詞彙說明,
    統計說明文字,
    伺服器佔比列表,
    取得伺服器拆分列表,
    職業佔比來源,
    職業佔比標題文字,
    職業佔比分組,
    伺服器生態欄位,
    伺服器生態矩陣,
    熱力格樣式,
    職業分析職業選項,
    職業分析目前範圍代碼,
    職業分析目前範圍類型,
    職業分析目前範圍,
    職業分析目前職業代碼,
    職業分析目前職業,
    職業分析有資料職業,
    職業分析目前類型代碼,
    職業分析目前類型,
    職業分析職業分組,
    職業分析展示類型代碼,
    職業分析展示職業,
    職業分析選單文字,
    職業分析選單Icon路徑,
    職業分析分位亮點條件文字,
    職業分析分位亮點標題,
    職業分析分位亮點列,
    職業分析副本列,
    職業分析伺服器列,
    職業分析概要,
    職業分析詳細,
    職業分析副本輸出列,
    職業分析代表紀錄,
    資料狀態列表,
    資料狀態分組,
    近期動態來源,
    近期動態基準時間,
    近期動態日誌時間範圍選項,
    近期動態日誌副本選項,
    近期動態日誌副本分組,
    近期動態日誌副本選單文字,
    近期動態日誌有效副本鍵值,
    近期動態日誌指標選項,
    近期動態日誌圖表資料,
    近期動態日誌摘要,
    近期動態日誌提示資料,
    近期動態日誌範圍文字,
    近期動態日誌指標標籤,
    顯示近期動態日誌自訂日期,
    切換近期動態日誌副本選單,
    選擇近期動態日誌副本,
    處理近期動態日誌副本選單失焦,
    顯示近期動態日誌提示,
    隱藏近期動態日誌提示,
    固定近期動態日誌提示,
    清除近期動態日誌提示,
    近期動態最新成績列表,
    近期刷新紀錄列表,
    近期新角色列表,
    近期伺服器活躍列表,
    近期副本活躍列表,
    近期動態角色列表,
    近期動態概要,
    蜂蜂粉絲榜來源,
    頭號粉絲列表,
    最新粉絲紀錄列表,
    最新加入粉絲列表,
    蜂蜂粉絲榜概要,
    蜂蜂觀眾粉絲列表,
    粉絲榜愛心列表,
    隊伍榜副本列表,
    隊伍榜副本分組,
    目前隊伍榜副本,
    隊伍榜副本選單文字,
    顯示隊伍榜版本篩選,
    有效隊伍榜版本範圍,
    目前隊伍榜來源,
    隊伍榜列,
    隊伍榜概要,
    伺服器對比伺服器列表,
    伺服器對比選項,
    伺服器對比左資料,
    伺服器對比右資料,
    伺服器對比已完成,
    伺服器對比概要,
    伺服器對比職能列,
    伺服器對比職業亮點,
    伺服器對比副本列,
    取得成績職業總數,
    取得最高伺服器,
    取得最高職業,
    副本通關概覽,
    零式副本排序值,
    取得零式層級文字,
    取得副本統計篩選來源,
    零式漏斗單位,
    零式漏斗條件文字,
    零式進度漏斗,
    更新時間文字,
    頁面副標,
    頁面標題,
    分享資訊,
    使用者索引列表,
    排行榜最近搜尋玩家,
    使用者最近搜尋玩家,
    比較角色左最近搜尋玩家,
    比較角色右最近搜尋玩家,
    顯示排行榜最近搜尋玩家,
    顯示使用者最近搜尋玩家,
    顯示比較角色左最近搜尋玩家,
    顯示比較角色右最近搜尋玩家,
    玩家搜尋歷史管理列表,
    開啟玩家搜尋歷史,
    處理玩家搜尋歷史失焦,
    開啟玩家搜尋歷史管理彈窗,
    關閉玩家搜尋歷史管理彈窗,
    刪除單筆玩家搜尋歷史,
    清除所有玩家搜尋歷史,
    記錄排行榜搜尋歷史,
    選擇最近搜尋玩家,
    建立使用者搜尋建議列表,
    使用者搜尋建議,
    比較角色左搜尋建議,
    比較角色右搜尋建議,
    比較副本列表,
    目前比較副本,
    比較範圍文字,
    比較副本選單文字,
    顯示比較版本篩選,
    有效比較版本範圍,
    取得使用者副本成績,
    使用者完整副本成績,
    使用者簡表版本副本成績,
    使用者簡表群組,
    使用者簡表目標副本數,
    使用者簡表已收錄通關數,
    使用者可用職業列表,
    使用者職業類型選項,
    使用者職業選項,
    目前使用者職業類型,
    使用者職業選單文字,
    使用者職業選單Icon路徑,
    符合使用者職業篩選,
    使用者副本成績,
    建立使用者統計,
    使用者統計,
    使用者分位亮點,
    建立使用者成績趨勢項,
    使用者成績趨勢,
    建立比較角色項目,
    比較角色左,
    比較角色右,
    角色比較已完成,
    目前比較職能,
    取得副本排序值,
    建立比較副本職能索引,
    角色比較列,
    使用者隊友列表,
    常見隊友,
    隊友職能分布,
    隊友關係摘要,
    使用者徽章,
    隊友副本交集,
    過濾後排行列,
    總頁數,
    安全目前頁碼,
    有上一頁,
    有下一頁,
    當頁起始索引,
    當頁排行列,
    顯示起始排名,
    顯示結束排名,
    排行列顯示排名,
    前往頁碼,
    前一頁,
    下一頁,
    讀取副本清單,
    讀取排行榜資料,
    讀取使用者索引,
    讀取全服統計,
    讀取近期動態資料,
    讀取隊伍榜資料,
    讀取伺服器對比資料,
    讀取蜂蜂粉絲榜資料,
    準備蜂蜂背景音樂偏好,
    設定蜂蜂背景音樂偏好,
    切換蜂蜂背景音樂,
    尋找使用者索引條目,
    格式化使用者搜尋文字,
    解析使用者搜尋輸入,
    更新網址為使用者,
    更新網址為排行榜,
    更新網址為隊伍榜,
    更新網址為伺服器對比,
    更新網址為蜂蜂粉絲榜,
    分享目前頁面,
    載入使用者成績,
    載入比較角色資料,
    提交角色比較,
    切換到排行榜,
    切換到全服統計,
    切換到個人成績單,
    切換到角色比較,
    切換到職業分析,
    切換到近期動態,
    切換到隊伍榜,
    切換到伺服器對比,
    切換到常見問題,
    切換到Logs檢查,
    切換到蜂蜂粉絲榜,
    切換隊伍榜副本選單,
    處理隊伍榜副本選單失焦,
    選擇隊伍榜副本,
    交換伺服器對比,
    提交使用者搜尋,
    開啟個人成績單,
    開啟隊友成績單,
    是網站作者,
  };
}
