<script setup>
import { computed, onMounted, ref, watch } from "vue";

const 排行榜資料 = ref(null);
const 副本清單 = ref([]);
const 副本鍵值 = ref("savage_m1s");
const 副本選單開啟 = ref(false);
const 讀取中 = ref(true);
const 錯誤訊息 = ref("");
const 伺服器篩選 = ref("");
const 職業類型篩選 = ref("");
const 職業篩選 = ref("");
const 職業選單開啟 = ref(false);
const 主色模式 = ref("default");
const 搜尋關鍵字 = ref("");
const 排序欄位 = ref("rdps");
const 目前頁碼 = ref(1);
const 每頁筆數 = 100;
const 主題模式 = ref("dark");
const 主題儲存鍵 = "ffxiv-tc-rankings-theme";
const 頁面模式 = ref("ranking");
const 使用者索引 = ref(null);
const 使用者資料 = ref(null);
const 使用者搜尋關鍵字 = ref("");
const 使用者伺服器篩選 = ref("");
const 使用者讀取中 = ref(false);
const 使用者錯誤訊息 = ref("");
const 比較角色左輸入 = ref("");
const 比較角色右輸入 = ref("");
const 比較角色左資料 = ref(null);
const 比較角色右資料 = ref(null);
const 比較角色左伺服器 = ref("");
const 比較角色右伺服器 = ref("");
const 比較讀取中 = ref(false);
const 比較錯誤訊息 = ref("");
const 全服統計資料 = ref(null);
const 全服統計讀取中 = ref(false);
const 全服統計錯誤訊息 = ref("");
const 統計副本鍵值 = ref("all");
const 統計副本選單開啟 = ref(false);
const 統計伺服器篩選 = ref("");
const 統計職業範圍 = ref("all");
const 伺服器拆分模式 = ref("none");
const 職業分析職業 = ref("");
const 職業分析職業類型 = ref("");
const 職業分析選單開啟 = ref(false);

const 副本清單網址 = `${import.meta.env.BASE_URL}data/encounters.json`;
const 使用者索引網址 = `${import.meta.env.BASE_URL}data/users/index.json`;
const 全服統計網址 = `${import.meta.env.BASE_URL}data/global_stats.json`;

const 目前副本 = computed(() => {
  return 副本清單.value.find((副本) => 副本.key === 副本鍵值.value) || 副本清單.value[0] || null;
});

const 資料網址 = computed(() => {
  return `${import.meta.env.BASE_URL}${目前副本.value?.data_path || "data/rankings/savage_m1s.json"}`;
});

const 排序選項 = [
  { value: "active", label: "Active 高到低" },
  { value: "dps", label: "DPS 高到低" },
  { value: "rdps", label: "rDPS 高到低" },
  { value: "adps", label: "aDPS 高到低" },
  { value: "clearTime", label: "通關時間短到長" },
  { value: "recordedAt", label: "紀錄時間新到舊" },
];

const 副本分類順序 = ["零式", "極", "幻", "絕"];

const 副本分組 = computed(() => {
  const 分組索引 = new Map();

  for (const 分類 of 副本分類順序) {
    分組索引.set(分類, []);
  }

  for (const 副本 of 副本清單.value) {
    const 分類 = 副本.category || "其他";
    if (!分組索引.has(分類)) {
      分組索引.set(分類, []);
    }
    分組索引.get(分類).push(副本);
  }

  return Array.from(分組索引.entries())
    .map(([分類, 副本列表]) => ({
      分類,
      副本列表,
    }))
    .filter((分組) => 分組.副本列表.length > 0);
});

const 副本選單文字 = computed(() => {
  return 目前副本.value?.name || "選擇副本";
});

function 偵測初始主題() {
  if (typeof window === "undefined") {
    return "dark";
  }

  const 已儲存主題 = window.localStorage.getItem(主題儲存鍵);
  if (已儲存主題 === "light" || 已儲存主題 === "dark") {
    return 已儲存主題;
  }

  if (window.matchMedia?.("(prefers-color-scheme: light)").matches) {
    return "light";
  }

  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }

  return "dark";
}

function 套用主題(主題) {
  const 有效主題 = 主題 === "light" ? "light" : "dark";
  主題模式.value = 有效主題;

  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = 有效主題;
    document.documentElement.style.colorScheme = 有效主題;
  }

  if (typeof window !== "undefined") {
    window.localStorage.setItem(主題儲存鍵, 有效主題);
  }
}

function 切換主題() {
  套用主題(主題模式.value === "dark" ? "light" : "dark");
}

const 主題按鈕文字 = computed(() => {
  return 主題模式.value === "dark" ? "亮色" : "暗色";
});

const 目前主題文字 = computed(() => {
  return 主題模式.value === "dark" ? "暗色模式" : "亮色模式";
});

const 職業繁中名稱 = {
  Paladin: "騎士",
  Warrior: "戰士",
  DarkKnight: "暗黑騎士",
  Gunbreaker: "絕槍戰士",
  WhiteMage: "白魔道士",
  Scholar: "學者",
  Astrologian: "占星術師",
  Sage: "賢者",
  Monk: "武僧",
  Dragoon: "龍騎士",
  Ninja: "忍者",
  Samurai: "武士",
  Reaper: "奪魂者",
  Viper: "毒蛇劍士",
  Bard: "吟遊詩人",
  Machinist: "機工士",
  Dancer: "舞者",
  BlackMage: "黑魔道士",
  Summoner: "召喚士",
  RedMage: "赤魔道士",
  Pictomancer: "繪靈法師",
  BlueMage: "青魔法師",
};

const 職業群組設定 = [
  {
    代碼: "role:tank",
    名稱: "防護職業",
    色彩: "tank",
    職業: ["Paladin", "Warrior", "DarkKnight", "Gunbreaker"],
  },
  {
    代碼: "role:healer",
    名稱: "治療職業",
    色彩: "healer",
    職業: ["WhiteMage", "Scholar", "Astrologian", "Sage"],
  },
  {
    代碼: "role:melee",
    名稱: "近戰職業",
    色彩: "dps",
    職業: ["Monk", "Dragoon", "Ninja", "Samurai", "Reaper", "Viper"],
  },
  {
    代碼: "role:physical_ranged",
    名稱: "遠程物理職業",
    色彩: "dps",
    職業: ["Bard", "Machinist", "Dancer"],
  },
  {
    代碼: "role:magical_ranged",
    名稱: "遠程魔法職業",
    色彩: "dps",
    職業: ["BlackMage", "Summoner", "RedMage", "Pictomancer"],
  },
];

const 職業群組索引 = 職業群組設定.reduce((索引, 群組) => {
  索引[群組.代碼] = new Set(群組.職業);
  return 索引;
}, {});

const 職業Icon檔名 = {
  Paladin: "Paladin.png",
  Warrior: "Warrior.png",
  DarkKnight: "DarkKnight.png",
  Gunbreaker: "Gunbreaker.png",
  WhiteMage: "WhiteMage.png",
  Scholar: "Scholar.png",
  Astrologian: "Astrologian.png",
  Sage: "Sage.png",
  Monk: "Monk.png",
  Dragoon: "Dragoon.png",
  Ninja: "Ninja.png",
  Samurai: "Samurai.png",
  Reaper: "Reaper.png",
  Viper: "Viper.png",
  Bard: "Bard.png",
  Machinist: "Machinist.png",
  Dancer: "Dancer.png",
  BlackMage: "BlackMage.png",
  Summoner: "Summoner.png",
  RedMage: "RedMage.png",
  Pictomancer: "Pictomancer.png",
  BlueMage: "BlueMage.png",
};

const 職業類型Icon檔名 = {
  "role:tank": "RoleTank.png",
  "role:healer": "RoleHealer.png",
  "role:melee": "RoleMelee.png",
  "role:physical_ranged": "RolePhysicalRanged.png",
  "role:magical_ranged": "RoleMagicalRanged.png",
};

function 顯示職業名稱(職業代碼) {
  return 職業繁中名稱[職業代碼] || 職業代碼 || "-";
}

function 職業Icon路徑(職業代碼) {
  const 檔名 = 職業Icon檔名[職業代碼];
  return 檔名 ? `${import.meta.env.BASE_URL}icons/jobs/${檔名}` : "";
}

function 職業類型Icon路徑(類型代碼) {
  const 檔名 = 職業類型Icon檔名[類型代碼];
  return 檔名 ? `${import.meta.env.BASE_URL}icons/jobs/${檔名}` : "";
}

function 隱藏載入失敗圖片(event) {
  event.currentTarget.style.display = "none";
}

function 職業色彩類別(色彩) {
  return {
    防護色: 色彩 === "tank",
    治療色: 色彩 === "healer",
    輸出色: 色彩 === "dps",
  };
}

function 職業代碼色彩(職業代碼) {
  return 職業群組設定.find((群組) => 群組.職業.includes(職業代碼))?.色彩 || "";
}

function 職業類型色彩(類型代碼) {
  return 職業群組設定.find((群組) => 群組.代碼 === 類型代碼)?.色彩 || "";
}

function 職業所屬類型(職業代碼) {
  return 職業群組設定.find((群組) => 群組.職業.includes(職業代碼)) || null;
}

function 目前職業主色() {
  if (職業篩選.value) {
    return 職業代碼色彩(職業篩選.value) || "default";
  }

  return 職業群組設定.find((群組) => 群組.代碼 === 職業類型篩選.value)?.色彩 || "default";
}

function 排名色彩類別(排名) {
  return {
    第一名: 排名 === 1,
    第二名: 排名 === 2,
    第三名: 排名 === 3,
  };
}

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
  職業分析選單開啟.value = false;
  職業選單開啟.value = !職業選單開啟.value;
}

function 處理職業選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    職業選單開啟.value = false;
  }
}

function 切換副本選單() {
  職業選單開啟.value = false;
  統計副本選單開啟.value = false;
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

function 切換職業分析選單() {
  副本選單開啟.value = false;
  統計副本選單開啟.value = false;
  職業選單開啟.value = false;
  職業分析選單開啟.value = !職業分析選單開啟.value;
}

function 選擇職業分析類型(類型代碼) {
  職業分析職業類型.value = 類型代碼;
}

function 選擇職業分析職業(職業代碼) {
  職業分析職業.value = 職業代碼;
  職業分析職業類型.value = 職業所屬類型(職業代碼)?.代碼 || 職業分析職業類型.value;
  職業分析選單開啟.value = false;
}

function 處理職業分析選單失焦(event) {
  if (!event.currentTarget.contains(event.relatedTarget)) {
    職業分析選單開啟.value = false;
  }
}

function 格式化傷害數值(數值) {
  if (typeof 數值 !== "number" || Number.isNaN(數值)) {
    return "-";
  }

  return new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: 0,
  }).format(數值);
}

function 格式化Active(active) {
  if (typeof active !== "number" || Number.isNaN(active)) {
    return "-";
  }

  return `${active.toFixed(2)}%`;
}

function 格式化整數(數值) {
  const 數字 = 轉為數字(數值);
  if (數字 === null) {
    return "-";
  }

  return new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: 0,
  }).format(數字);
}

function 格式化帶號整數(數值) {
  const 數字 = 轉為數字(數值);
  if (數字 === null) {
    return "-";
  }

  const 格式化數字 = new Intl.NumberFormat("zh-TW", {
    maximumFractionDigits: 0,
  }).format(Math.abs(數字));
  if (數字 > 0) {
    return `+${格式化數字}`;
  }
  if (數字 < 0) {
    return `-${格式化數字}`;
  }
  return "0";
}

function 格式化百分比(數值) {
  const 數字 = 轉為數字(數值);
  if (數字 === null) {
    return "-";
  }

  return `${數字.toFixed(2)}%`;
}

function 格式化前段百分位(排名, 總數) {
  const 排名數值 = 轉為數字(排名);
  const 總數值 = 轉為數字(總數);
  if (排名數值 === null || 總數值 === null || 總數值 <= 0) {
    return "-";
  }

  return `前 ${Math.min(100, Math.max(0.01, (排名數值 / 總數值) * 100)).toFixed(2)}%`;
}

function 格式化通關時間(秒數) {
  if (typeof 秒數 !== "number" || Number.isNaN(秒數)) {
    return "-";
  }

  const 分鐘 = Math.floor(秒數 / 60);
  const 秒 = Math.floor(秒數 % 60);

  return `${分鐘}:${String(秒).padStart(2, "0")}`;
}

function 格式化紀錄時間(iso時間) {
  if (!iso時間) {
    return "-";
  }

  const 日期 = new Date(iso時間);
  if (Number.isNaN(日期.getTime())) {
    return "-";
  }

  return new Intl.DateTimeFormat("zh-TW", {
    timeZone: "Asia/Taipei",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(日期);
}

function 格式化排名(排名) {
  const 排名數值 = 轉為數字(排名);
  return 排名數值 === null ? "-" : `#${排名數值}`;
}

function 建立公開資料網址(相對路徑) {
  return `${import.meta.env.BASE_URL}${String(相對路徑)
    .split("/")
    .map((片段) => encodeURIComponent(片段))
    .join("/")}`;
}

function 建立使用者預設資料網址(角色名稱) {
  return 建立公開資料網址(`data/users/${角色名稱}.json`);
}

function 轉為數字(值) {
  const 數值 = Number(值);
  return Number.isFinite(數值) ? 數值 : null;
}

function 比例條樣式(比例) {
  const 數值 = Math.min(Math.max(轉為數字(比例) ?? 0, 0), 100);
  return {
    width: `${數值}%`,
  };
}

function 趨勢點樣式(點) {
  return {
    left: `${點.x}%`,
    top: `${(點.y / 52) * 100}%`,
  };
}

function 計算Active百分比(activeTimeMs, 通關秒數) {
  const activeTime = 轉為數字(activeTimeMs);
  if (activeTime === null || typeof 通關秒數 !== "number" || 通關秒數 <= 0) {
    return null;
  }

  return Number(((activeTime / (通關秒數 * 1000)) * 100).toFixed(2));
}

function 排序數值(列, 欄位) {
  if (欄位 === "active") {
    return 列.active ?? -Infinity;
  }
  if (欄位 === "dps") {
    return 列.dps ?? -Infinity;
  }
  if (欄位 === "rdps") {
    return 列.rdps ?? 列.dps ?? -Infinity;
  }
  if (欄位 === "adps") {
    return 列.adps ?? -Infinity;
  }
  if (欄位 === "clearTime") {
    return 列.通關秒數 ?? Infinity;
  }
  if (欄位 === "recordedAt") {
    const 時間 = new Date(列.紀錄時間).getTime();
    return Number.isNaN(時間) ? -Infinity : 時間;
  }

  return 列.rdps ?? 列.dps ?? -Infinity;
}

function 比較排行列(前一筆, 後一筆) {
  const 欄位 = 排序欄位.value;
  const 前值 = 排序數值(前一筆, 欄位);
  const 後值 = 排序數值(後一筆, 欄位);

  if (前值 !== 後值) {
    return 欄位 === "clearTime" ? 前值 - 後值 : 後值 - 前值;
  }

  const 前rDPS = 前一筆.rdps ?? 前一筆.dps ?? 0;
  const 後rDPS = 後一筆.rdps ?? 後一筆.dps ?? 0;
  if (前rDPS !== 後rDPS) {
    return 後rDPS - 前rDPS;
  }

  return 前一筆.角色名稱.localeCompare(後一筆.角色名稱, "zh-Hant-TW");
}

function 建立排行列(條目) {
  const 職業代碼 = 條目.job || "-";
  const 通關秒數 = 轉為數字(條目.clear_time_seconds);
  const active = 轉為數字(條目.active_percent) ?? 計算Active百分比(條目.active_time_ms, 通關秒數);

  return {
    id: 條目.id || `${條目.report_code}-${條目.fight_id}-${條目.character_name}-${條目.server}`,
    reportCode: 條目.report_code,
    reportUrl: 條目.report_url,
    角色名稱: 條目.character_name || 條目.name || "未知角色",
    伺服器: 條目.server || "未知伺服器",
    職業代碼,
    職業: 顯示職業名稱(職業代碼),
    rdps: 轉為數字(條目.rdps ?? 條目.dps),
    adps: 轉為數字(條目.adps),
    dps: 轉為數字(條目.dps),
    active,
    activeTimeMs: 轉為數字(條目.active_time_ms),
    通關秒數,
    紀錄時間: 條目.recorded_at_iso || 條目.report_start_time_iso,
    重複來源數: 轉為數字(條目.duplicate_count) || 1,
    原始排名: 轉為數字(條目.rank),
    職業排名: 轉為數字(條目.job_rank ?? 條目.rank),
  };
}

function 成績是否較佳(候選, 目前最佳) {
  if (!目前最佳) {
    return true;
  }

  if ((候選.rdps ?? 0) !== (目前最佳.rdps ?? 0)) {
    return (候選.rdps ?? 0) > (目前最佳.rdps ?? 0);
  }

  if ((候選.通關秒數 ?? Infinity) !== (目前最佳.通關秒數 ?? Infinity)) {
    return (候選.通關秒數 ?? Infinity) < (目前最佳.通關秒數 ?? Infinity);
  }

  if ((候選.adps ?? 0) !== (目前最佳.adps ?? 0)) {
    return (候選.adps ?? 0) > (目前最佳.adps ?? 0);
  }

  return 候選.角色名稱.localeCompare(目前最佳.角色名稱, "zh-Hant-TW") < 0;
}

function 使用者成績是否較佳(候選, 目前最佳) {
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

function 只保留角色最佳成績(排行列) {
  const 最佳成績索引 = new Map();

  for (const 列 of 排行列) {
    const 鍵值 = `${列.角色名稱}@${列.伺服器}:${列.職業代碼}`;
    const 目前最佳 = 最佳成績索引.get(鍵值);

    if (成績是否較佳(列, 目前最佳)) {
      最佳成績索引.set(鍵值, 列);
    }
  }

  return Array.from(最佳成績索引.values());
}

function 展開排行榜列(原始資料) {
  if (Array.isArray(原始資料?.ranking_entries)) {
    return 原始資料.ranking_entries.map(建立排行列);
  }

  const 報告集合 = 原始資料?.reports ?? {};
  const 報告列表 = Array.isArray(報告集合) ? 報告集合 : Object.values(報告集合);

  const 攤平排行列 = 報告列表.flatMap((報告) => {
    const 戰鬥列表 = Array.isArray(報告?.fights) ? 報告.fights : [];

    return 戰鬥列表.flatMap((戰鬥) => {
      const 玩家列表 = Array.isArray(戰鬥?.players) ? 戰鬥.players : [];
      const 通關秒數 = 轉為數字(戰鬥?.clear_time_seconds);

      return 玩家列表.map((玩家) => ({
        id: `${報告.report_code}-${戰鬥.fight_id}-${玩家.name}-${玩家.server}`,
        reportCode: 報告.report_code,
        reportUrl: 報告.url,
        角色名稱: 玩家.name || "未知角色",
        伺服器: 玩家.server || "未知伺服器",
        職業代碼: 玩家.job || "-",
        職業: 顯示職業名稱(玩家.job),
        rdps: 轉為數字(玩家.rdps ?? 玩家.dps),
        adps: 轉為數字(玩家.adps),
        dps: 轉為數字(玩家.dps),
        active: 計算Active百分比(玩家.active_time_ms, 通關秒數),
        activeTimeMs: 轉為數字(玩家.active_time_ms),
        通關秒數,
        紀錄時間: 戰鬥.recorded_at_iso || 報告.report_start_time_iso,
        重複來源數: 1,
      }));
    });
  });

  return 只保留角色最佳成績(攤平排行列);
}

const 所有排行列 = computed(() => {
  return 展開排行榜列(排行榜資料.value).sort(比較排行列);
});

const 伺服器選項 = computed(() => {
  const 名稱集合 = new Set(
    所有排行列.value.map((列) => 列.伺服器).filter((伺服器) => 伺服器 && 伺服器 !== "未知伺服器"),
  );

  return Array.from(名稱集合).sort((前一個, 後一個) => 前一個.localeCompare(後一個, "zh-Hant-TW"));
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
      職業: 群組.職業.filter((職業代碼) => 目前有資料職業.has(職業代碼)).map((職業代碼) => ({
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
    .filter((群組) => 群組.職業.some((職業代碼) => 目前有資料職業.has(職業代碼)))
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

const 顯示零式進度漏斗 = computed(() => {
  return !目前統計副本.value || 目前統計副本.value.encounter_category === "零式";
});

const 顯示副本通關概覽 = computed(() => {
  return !目前統計副本.value;
});

const 目前統計來源 = computed(() => {
  return 目前統計副本.value || 全服統計資料.value || null;
});

function 職業範圍類型(範圍) {
  if (!範圍 || 範圍 === "all") {
    return "all";
  }
  return String(範圍).startsWith("role:") ? "role" : "job";
}

function 取得統計計數(統計項目, 職業範圍 = 統計職業範圍.value) {
  if (!統計項目) {
    return 0;
  }

  const 類型 = 職業範圍類型(職業範圍);
  if (類型 === "role") {
    return 轉為數字((統計項目.role_stats || []).find((項目) => 項目.role === 職業範圍)?.clear_count) || 0;
  }
  if (類型 === "job") {
    return 轉為數字((統計項目.job_stats || []).find((項目) => 項目.job === 職業範圍)?.clear_count) || 0;
  }

  return 轉為數字(統計項目.character_count ?? 統計項目.clear_count) || 0;
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
  return (目前統計來源.value?.server_stats || [])
    .map((項目) => 項目.server)
    .filter(Boolean)
    .sort((前一個, 後一個) => 前一個.localeCompare(後一個, "zh-Hant-TW"));
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

const 統計伺服器文字 = computed(() => {
  return 統計伺服器篩選.value || "全部伺服器";
});

const 統計條件文字 = computed(() => {
  return `${統計範圍文字.value}・${統計伺服器文字.value}・${取得職業範圍文字()}`;
});

const 全服概要項目 = computed(() => {
  const 統計 = 全服統計資料.value;
  const 副本 = 目前統計副本.value;
  if (!統計) {
    return [];
  }

  if (副本) {
    return [
      { 標籤: "通關角色", 數值: 格式化整數(副本.character_count) },
      { 標籤: "職業紀錄", 數值: 格式化整數(副本.job_record_count) },
      { 標籤: "公開成績", 數值: 格式化整數(副本.entry_count) },
      { 標籤: "公開角色覆蓋率", 數值: 格式化百分比(副本.clear_share_percent) },
    ];
  }

  return [
    { 標籤: "全服公開角色", 數值: 格式化整數(統計.total_character_count) },
    { 標籤: "副本通關人次", 數值: 格式化整數(統計.total_encounter_clear_count) },
    { 標籤: "職業通關紀錄", 數值: 格式化整數(統計.total_job_clear_count) },
    { 標籤: "公開成績", 數值: 格式化整數(統計.total_entry_count) },
  ];
});

const 統計詞彙說明 = {
  全服公開角色: "目前公開資料中出現過的唯一角色數，不代表遊戲內完整人口。",
  副本通關人次: "各副本的通關角色數加總；同一角色跨副本會分別計入。",
  職業通關紀錄: "同一角色若用不同職業留下通關成績，會各自計為一筆職業紀錄。",
  公開成績: "目前抓取到且可公開呈現的 FFLogs 成績筆數。",
  通關角色: "同一角色在同一副本會去重計算。",
  職業紀錄: "同一角色在同一副本使用不同職業時，會分別計入。",
  公開角色覆蓋率: "單一副本的通關角色數除以目前公開資料中出現過的唯一角色數。",
  伺服器佔比: "在目前副本與職業範圍下，各伺服器佔全部符合條件紀錄的比例。",
  職業佔比: "在目前副本與伺服器範圍下，各職業或職業類型佔全部符合條件紀錄的比例。",
  隊友關係: "依公開通關同場資料整理常同場隊友、職能組成與副本聚集；不等同實際固定隊名單。",
  伺服器生態比較: "以各伺服器內部的職能通關紀錄比例呈現，顏色越深代表該職能在該伺服器占比越高。",
  通關紀錄: "套用職業範圍時，以符合職業條件的通關紀錄計算。",
  範圍佔比: "套用伺服器或職業範圍後，副本通關概覽會改以目前篩選範圍作為分母。",
  零式進度漏斗: "以目前伺服器與職業範圍計算各零式層數的公開通關規模；套用單一職業時，代表該職業留下的通關紀錄。",
  Active: "有效輸出時間比例。數值越高，代表角色在戰鬥中維持輸出或行動的時間越完整。",
  DPS: "原始每秒傷害，包含自身傷害以及吃到外部增益後造成的傷害。",
  rDPS: "團隊貢獻 DPS。公式：DPS - 他人團輔 + 自體團輔，用來衡量你實際為團隊帶來的傷害。",
  nDPS: "純淨 DPS。公式：DPS - 他人團輔，用來看移除外部增益後自己的輸出表現。",
  aDPS: "調整後 DPS。公式：DPS - 被選取的單體增益，會移除標舞、舞伴、占星卡與龍眼等單體填充傷害。",
  cDPS: "綜合 DPS。公式：DPS - 被選取的單體增益 + 自體團輔，用來同時觀察自身爆發與你提供給團隊的增益價值。",
  "最佳 rDPS": "此角色目前公開成績中最高的團隊貢獻 DPS。",
};

function 統計說明文字(詞彙) {
  return 統計詞彙說明[詞彙] || "";
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
  return `${統計範圍文字.value}・${統計伺服器文字.value}`;
});

const 職業佔比分組 = computed(() => {
  const 來源 = 職業佔比來源.value;
  const 範圍類型 = 職業範圍類型(統計職業範圍.value);
  const 職業列表 = (來源?.job_stats || []).filter((項目) => {
    if (範圍類型 === "role") {
      return 項目.role === 統計職業範圍.value;
    }
    if (範圍類型 === "job") {
      return 項目.job === 統計職業範圍.value;
    }
    return true;
  });

  return 職業群組設定
    .map((群組) => {
      const jobs = 職業列表.filter((項目) => 項目.role === 群組.代碼);
      if (jobs.length === 0) {
        return null;
      }
      const roleStats = (來源?.role_stats || []).find((項目) => 項目.role === 群組.代碼);
      const clearCount = 範圍類型 === "job" ? jobs.reduce((總數, 項目) => 總數 + 項目.clear_count, 0) : roleStats?.clear_count;
      const percentage = 範圍類型 === "job" ? jobs.reduce((總數, 項目) => 總數 + 項目.percentage, 0) : roleStats?.percentage;

      return {
        role: 群組.代碼,
        role_name: 群組.名稱,
        色彩: 群組.色彩,
        clear_count: clearCount ?? jobs.reduce((總數, 項目) => 總數 + 項目.clear_count, 0),
        percentage: percentage ?? 0,
        jobs,
      };
    })
    .filter(Boolean);
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

function 熱力格樣式(比例) {
  const 數值 = Math.min(Math.max(轉為數字(比例) ?? 0, 0), 100);
  return {
    "--熱度": `${Math.round(8 + (數值 / 100) * 50)}%`,
  };
}

const 職業分析職業選項 = computed(() => {
  const 職業列表 = Array.isArray(全服統計資料.value?.job_stats) ? 全服統計資料.value.job_stats : [];
  return 職業列表.map((項目) => ({
    ...項目,
    label: 顯示職業名稱(項目.job),
  }));
});

const 職業分析目前職業代碼 = computed(() => {
  return 職業分析職業.value || 職業分析職業選項.value[0]?.job || "";
});

const 職業分析目前職業 = computed(() => {
  return 職業分析職業選項.value.find((項目) => 項目.job === 職業分析目前職業代碼.value) || null;
});

const 職業分析有資料職業 = computed(() => {
  return new Set(職業分析職業選項.value.map((職業) => 職業.job).filter(Boolean));
});

const 職業分析類型選項 = computed(() => {
  return 職業群組設定
    .filter((群組) => 群組.職業.some((職業代碼) => 職業分析有資料職業.value.has(職業代碼)))
    .map((群組) => ({
      代碼: 群組.代碼,
      名稱: 群組.名稱,
      色彩: 群組.色彩,
    }));
});

const 職業分析目前類型代碼 = computed(() => {
  return (
    職業分析職業類型.value ||
    職業所屬類型(職業分析目前職業代碼.value)?.代碼 ||
    職業分析類型選項.value[0]?.代碼 ||
    ""
  );
});

const 職業分析目前類型 = computed(() => {
  return 職業群組設定.find((群組) => 群組.代碼 === 職業分析目前類型代碼.value) || null;
});

const 職業分析可選職業 = computed(() => {
  const 群組 = 職業群組設定.find((項目) => 項目.代碼 === 職業分析目前類型代碼.value);
  if (!群組) {
    return [];
  }

  return 群組.職業
    .filter((職業代碼) => 職業分析有資料職業.value.has(職業代碼))
    .map((職業代碼) => ({
      代碼: 職業代碼,
      名稱: 顯示職業名稱(職業代碼),
      色彩: 群組.色彩,
    }));
});

const 職業分析選單文字 = computed(() => {
  if (!職業分析目前職業代碼.value) {
    return "選擇職業";
  }

  return 職業分析目前類型.value
    ? `${職業分析目前類型.value.名稱} / ${顯示職業名稱(職業分析目前職業代碼.value)}`
    : 顯示職業名稱(職業分析目前職業代碼.value);
});

const 職業分析選單Icon路徑 = computed(() => {
  if (職業分析目前職業代碼.value) {
    return 職業Icon路徑(職業分析目前職業代碼.value);
  }

  return 職業類型Icon路徑(職業分析目前類型代碼.value);
});

const 職業分析副本列 = computed(() => {
  const 職業 = 職業分析目前職業代碼.value;
  const 總數 = 轉為數字(職業分析目前職業.value?.clear_count) || 0;

  return 全服統計副本列表.value
    .map((副本) => {
      const 統計 = (副本.job_stats || []).find((項目) => 項目.job === 職業);
      const 數量 = 轉為數字(統計?.clear_count) || 0;
      return {
        ...副本,
        數量,
        副本內佔比: 轉為數字(統計?.percentage) || 0,
        職業內佔比: 總數 > 0 ? Number(((數量 / 總數) * 100).toFixed(2)) : 0,
      };
    })
    .filter((副本) => 副本.數量 > 0)
    .sort((前一個, 後一個) => {
      const 順序差 = 取得副本排序值(前一個.encounter_key) - 取得副本排序值(後一個.encounter_key);
      return 順序差 || 前一個.encounter_name.localeCompare(後一個.encounter_name, "zh-Hant-TW");
    });
});

const 職業分析伺服器列 = computed(() => {
  const 職業 = 職業分析目前職業代碼.value;
  const 總數 = 轉為數字(職業分析目前職業.value?.clear_count) || 0;

  return (全服統計資料.value?.server_stats || [])
    .map((伺服器) => {
      const 統計 = (伺服器.job_stats || []).find((項目) => 項目.job === 職業);
      const 數量 = 轉為數字(統計?.clear_count) || 0;
      return {
        server: 伺服器.server,
        數量,
        全職業佔比: 總數 > 0 ? Number(((數量 / 總數) * 100).toFixed(2)) : 0,
        伺服器內佔比: 轉為數字(統計?.percentage) || 0,
      };
    })
    .filter((伺服器) => 伺服器.數量 > 0)
    .sort((前一個, 後一個) => 後一個.數量 - 前一個.數量 || 前一個.server.localeCompare(後一個.server, "zh-Hant-TW"));
});

const 職業分析概要 = computed(() => {
  const 職業 = 職業分析目前職業.value;
  if (!職業) {
    return [];
  }

  const 主要副本 = 職業分析副本列.value.slice().sort((前一個, 後一個) => 後一個.數量 - 前一個.數量)[0] || null;
  const 主要伺服器 = 職業分析伺服器列.value[0] || null;

  return [
    { 標籤: "通關紀錄", 數值: 格式化整數(職業.clear_count) },
    { 標籤: "公開成績", 數值: 格式化整數(職業.entry_count) },
    { 標籤: "全職業佔比", 數值: 格式化百分比(職業.percentage) },
    { 標籤: "主要伺服器", 數值: 主要伺服器 ? `${主要伺服器.server} ${格式化百分比(主要伺服器.全職業佔比)}` : "-" },
    { 標籤: "主要副本", 數值: 主要副本 ? `${主要副本.encounter_name} ${格式化百分比(主要副本.職業內佔比)}` : "-" },
  ];
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

const 近期動態基準時間 = computed(() => {
  const 使用者時間 = 使用者索引列表.value
    .map((使用者) => new Date(使用者.last_recorded_at_iso || 0).getTime())
    .filter(Number.isFinite)
    .sort((前一個, 後一個) => 後一個 - 前一個)[0];
  const 索引時間 = new Date(使用者索引.value?.rankings_updated_at_iso || 0).getTime();
  return 使用者時間 || (Number.isNaN(索引時間) ? Date.now() : 索引時間);
});

const 近期動態角色列表 = computed(() => {
  return 使用者索引列表.value
    .filter((使用者) => 使用者.last_recorded_at_iso)
    .slice()
    .sort((前一個, 後一個) => {
      const 時間差 = new Date(後一個.last_recorded_at_iso || 0).getTime() - new Date(前一個.last_recorded_at_iso || 0).getTime();
      return 時間差 || (後一個.best_rdps || 0) - (前一個.best_rdps || 0);
    })
    .slice(0, 24);
});

const 近期動態概要 = computed(() => {
  const 七天前 = 近期動態基準時間.value - 7 * 24 * 60 * 60 * 1000;
  const 近七天角色數 = 使用者索引列表.value.filter((使用者) => {
    const 時間 = new Date(使用者.last_recorded_at_iso || 0).getTime();
    return Number.isFinite(時間) && 時間 >= 七天前;
  }).length;
  const 最新角色 = 近期動態角色列表.value[0] || null;

  return [
    { 標籤: "收錄角色", 數值: 格式化整數(使用者索引.value?.total_users || 使用者索引列表.value.length) },
    { 標籤: "近七天活躍", 數值: 格式化整數(近七天角色數) },
    { 標籤: "最新角色", 數值: 最新角色?.character_name || "-" },
    { 標籤: "最新紀錄", 數值: 格式化紀錄時間(最新角色?.last_recorded_at_iso) },
  ];
});

function 取得成績職業總數(成績) {
  if (!成績?.encounter_key || !成績?.job) {
    return null;
  }

  const 副本 = (全服統計資料.value?.encounters || []).find((項目) => 項目.encounter_key === 成績.encounter_key);
  const 職業 = (副本?.job_stats || []).find((項目) => 項目.job === 成績.job);
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
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "角色比較資料";
  }

  if (頁面模式.value === "jobs") {
    const 更新時間 = 全服統計資料.value?.rankings_updated_at_iso || 全服統計資料.value?.generated_at_iso;
    return 更新時間 ? `統計更新時間 ${格式化紀錄時間(更新時間)}` : "職業分析資料";
  }

  if (頁面模式.value === "activity") {
    const 更新時間 = 使用者索引.value?.rankings_updated_at_iso || 使用者索引.value?.generated_at_iso;
    return 更新時間 ? `資料更新時間 ${格式化紀錄時間(更新時間)}` : "近期動態資料";
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
    return "Final Fantasy XIV 繁中服・角色比較";
  }

  if (頁面模式.value === "jobs") {
    return "Final Fantasy XIV 繁中服・職業分析";
  }

  if (頁面模式.value === "activity") {
    return "Final Fantasy XIV 繁中服・近期動態";
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
    return "角色比較";
  }

  if (頁面模式.value === "jobs") {
    return 職業分析目前職業代碼.value ? `${顯示職業名稱(職業分析目前職業代碼.value)} 職業分析` : "職業分析";
  }

  if (頁面模式.value === "activity") {
    return "近期動態";
  }

  return 目前副本.value?.name ? `${目前副本.value.name} 排行榜` : "排行榜";
});

const 使用者索引列表 = computed(() => {
  return Array.isArray(使用者索引.value?.users) ? 使用者索引.value.users : [];
});

function 建立使用者搜尋建議列表(搜尋文字) {
  const 關鍵字 = String(搜尋文字 || "")
    .trim()
    .toLocaleLowerCase("zh-TW");
  if (!關鍵字) {
    return [];
  }

  return 使用者索引列表.value
    .flatMap((使用者) => {
      const 伺服器列表 = 使用者.servers?.length ? 使用者.servers : [""];
      return 伺服器列表.map((伺服器) => {
        const 顯示文字 = 格式化使用者搜尋文字(使用者.character_name, 伺服器);
        return {
          value: 顯示文字,
          label: `${使用者.encounter_count || 0} 副本 / ${使用者.public_entry_count || 0} 筆公開成績`,
          character_name: 使用者.character_name,
          server: 伺服器,
        };
      });
    })
    .filter((建議) => {
      const 名稱符合 = 建議.character_name?.toLocaleLowerCase("zh-TW").includes(關鍵字);
      const 伺服器符合 = 建議.server?.toLocaleLowerCase("zh-TW").includes(關鍵字);
      const 顯示文字符合 = 建議.value.toLocaleLowerCase("zh-TW").includes(關鍵字);
      return 名稱符合 || 伺服器符合 || 顯示文字符合;
    })
    .slice(0, 8);
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

function 取得使用者副本成績(資料, 伺服器 = "") {
  const 副本列表 = Array.isArray(資料?.encounters) ? 資料.encounters : [];

  return 副本列表
    .map((副本) => {
      const 公開成績 = (副本.public_entries || []).filter((成績) => !伺服器 || 成績.server === 伺服器);
      if (公開成績.length === 0) {
        return null;
      }

      const 最佳成績 = 公開成績.reduce((目前最佳, 成績) => (使用者成績是否較佳(成績, 目前最佳) ? 成績 : 目前最佳), null);
      return {
        ...副本,
        best_entry: 最佳成績,
        public_entries: 公開成績,
      };
    })
    .filter(Boolean);
}

const 使用者副本成績 = computed(() => {
  return 取得使用者副本成績(使用者資料.value, 使用者伺服器篩選.value);
});

function 建立使用者統計(副本成績) {
  const 公開成績數 = 副本成績.reduce((總數, 副本) => 總數 + 副本.public_entries.length, 0);
  const 最佳成績 = 副本成績.reduce(
    (目前最佳, 副本) => (使用者成績是否較佳(副本.best_entry, 目前最佳) ? 副本.best_entry : 目前最佳),
    null,
  );
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
    最後紀錄時間,
  };
}

const 使用者統計 = computed(() => {
  return 建立使用者統計(使用者副本成績.value);
});

const 使用者成績趨勢 = computed(() => {
  return 使用者副本成績.value
    .map((副本) => {
      const 成績列表 = (副本.public_entries || [])
        .filter((成績) => 轉為數字(成績.rdps) !== null)
        .sort((前一個, 後一個) => {
          const 時間差 = new Date(前一個.recorded_at_iso || 0).getTime() - new Date(後一個.recorded_at_iso || 0).getTime();
          return 時間差 || (前一個.rdps ?? 0) - (後一個.rdps ?? 0);
        });

      if (成績列表.length === 0) {
        return null;
      }

      const 數值列表 = 成績列表.map((成績) => 轉為數字(成績.rdps) || 0);
      const 最低 = Math.min(...數值列表);
      const 最高 = Math.max(...數值列表);
      const 第一筆 = 成績列表[0];
      const 最新 = 成績列表.at(-1);
      const 最佳 = 成績列表.reduce((目前最佳, 成績) => (使用者成績是否較佳(成績, 目前最佳) ? 成績 : 目前最佳), null);
      const 點列表 = 成績列表.map((成績, index) => {
        const rdps = 轉為數字(成績.rdps) || 0;
        const x = 成績列表.length === 1 ? 50 : (index / (成績列表.length - 1)) * 100;
        const y = 最高 === 最低 ? 26 : 42 - ((rdps - 最低) / (最高 - 最低)) * 32;
        return {
          id: 成績.id,
          rdps,
          recorded_at_iso: 成績.recorded_at_iso,
          x: Number(x.toFixed(2)),
          y: Number(y.toFixed(2)),
        };
      });
      const 折線路徑 = 點列表.length > 1 ? 點列表.map((點, index) => `${index === 0 ? "M" : "L"} ${點.x} ${點.y}`).join(" ") : "";
      const 填色路徑 =
        點列表.length > 1 ? `${折線路徑} L ${點列表.at(-1).x} 46 L ${點列表[0].x} 46 Z` : "";

      return {
        encounter_key: 副本.encounter_key,
        encounter_name: 副本.encounter_name,
        encounter_category: 副本.encounter_category,
        最新,
        最佳,
        變化: (轉為數字(最新?.rdps) || 0) - (轉為數字(第一筆?.rdps) || 0),
        最低,
        最高,
        折線路徑,
        填色路徑,
        點列表,
      };
    })
    .filter(Boolean);
});

function 建立比較角色項目(資料, 伺服器 = "") {
  if (!資料) {
    return null;
  }

  const 副本成績 = 取得使用者副本成績(資料, 伺服器);
  return {
    character_name: 資料.character_name || "未知角色",
    server: 伺服器 || 資料.servers?.[0] || "",
    副本成績,
    統計: 建立使用者統計(副本成績),
  };
}

const 比較角色左 = computed(() => 建立比較角色項目(比較角色左資料.value, 比較角色左伺服器.value));
const 比較角色右 = computed(() => 建立比較角色項目(比較角色右資料.value, 比較角色右伺服器.value));

const 角色比較已完成 = computed(() => Boolean(比較角色左.value && 比較角色右.value));

function 取得副本排序值(副本鍵值) {
  const 清單索引 = 副本清單.value.findIndex((副本) => 副本.key === 副本鍵值);
  return 清單索引 >= 0 ? 清單索引 : Number.MAX_SAFE_INTEGER;
}

const 角色比較列 = computed(() => {
  if (!角色比較已完成.value) {
    return [];
  }

  const 左副本 = new Map(比較角色左.value.副本成績.map((副本) => [副本.encounter_key, 副本]));
  const 右副本 = new Map(比較角色右.value.副本成績.map((副本) => [副本.encounter_key, 副本]));
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

      return {
        encounter_key: 副本鍵值,
        encounter_name: 左?.encounter_name || 右?.encounter_name || 副本鍵值,
        encounter_category: 左?.encounter_category || 右?.encounter_category || "",
        左,
        右,
        差異,
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
  let 說明 = "公開同場資料多落在不同角色或單次紀錄，較像副本野團或短期組隊紀錄。";

  if (高頻隊友數 >= 7 || (最常同場隊友?.同場次數 || 0) >= 4) {
    關係型態 = "重複同場明顯";
    說明 = "已有多位角色重複同場，適合觀察主要副本、職能組成與近期合作軌跡。";
  } else if (高頻隊友數 >= 3) {
    關係型態 = "小隊輪廓";
    說明 = "有少數角色重複出現，但還不到穩定名單，更適合用副本聚集與職能分布判讀。";
  } else if (主要副本?.teammate_count >= 7) {
    關係型態 = "副本聚集";
    說明 = "隊友主要集中在特定副本，代表該場公開紀錄對目前關係圖的影響較高。";
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

  const 副本集合 = new Set(使用者副本成績.value.map((副本) => 副本.encounter_key));
  const 成績列表 = 使用者副本成績.value.flatMap((副本) => 副本.public_entries || []);
  const 職業集合 = new Set(成績列表.map((成績) => 成績.job).filter(Boolean));
  const 職能集合 = new Set(
    Array.from(職業集合)
      .map((職業) => 職業所屬類型(職業)?.代碼)
      .filter(Boolean),
  );
  const 基準時間 = 近期動態基準時間.value;
  const 最後紀錄時間 = new Date(使用者統計.value.最後紀錄時間 || 0).getTime();
  const 徽章 = [];

  if (["savage_m1s", "savage_m2s", "savage_m3s", "savage_m4s"].every((副本) => 副本集合.has(副本))) {
    徽章.push({ 名稱: "零式全通", 說明: "目前收錄的四層零式皆有公開成績" });
  }
  if (職業集合.size >= 3) {
    徽章.push({ 名稱: "多職玩家", 說明: `公開成績中出現 ${職業集合.size} 個職業` });
  }
  if (職能集合.size >= 3) {
    徽章.push({ 名稱: "跨職能", 說明: `公開成績橫跨 ${職能集合.size} 種職能` });
  }
  if (使用者統計.value.公開成績數 >= 20) {
    徽章.push({ 名稱: "高活躍", 說明: `公開成績 ${使用者統計.value.公開成績數} 筆` });
  }
  if (使用者隊友列表.value.length >= 50) {
    徽章.push({ 名稱: "社群核心", 說明: `與 ${使用者隊友列表.value.length} 位角色有公開同場紀錄` });
  }
  if (Number.isFinite(最後紀錄時間) && 最後紀錄時間 >= 基準時間 - 7 * 24 * 60 * 60 * 1000) {
    徽章.push({ 名稱: "近期活躍", 說明: "近七天內有公開紀錄" });
  }

  return 徽章;
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
  const 關鍵字 = 搜尋關鍵字.value.trim().toLocaleLowerCase("zh-TW");

  return 所有排行列.value.filter((列) => {
    const 符合伺服器 = !伺服器篩選.value || 列.伺服器 === 伺服器篩選.value;
    const 符合職業 = 符合職業篩選(列.職業代碼);
    const 符合角色名稱 = !關鍵字 || 列.角色名稱.toLocaleLowerCase("zh-TW").includes(關鍵字);

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

async function 讀取副本清單() {
  const 回應 = await fetch(副本清單網址, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!回應.ok) {
    throw new Error(`讀取副本清單失敗：HTTP ${回應.status}`);
  }

  const 清單 = await 回應.json();
  副本清單.value = Array.isArray(清單) ? 清單.filter((副本) => 副本.enabled !== false) : [];

  if (!目前副本.value && 副本清單.value[0]) {
    副本鍵值.value = 副本清單.value[0].key;
  }
}

async function 讀取排行榜資料() {
  讀取中.value = true;
  錯誤訊息.value = "";

  try {
    const 回應 = await fetch(資料網址.value, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!回應.ok) {
      throw new Error(`讀取失敗：HTTP ${回應.status}`);
    }

    排行榜資料.value = await 回應.json();
  } catch (錯誤) {
    錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取排行榜資料";
  } finally {
    讀取中.value = false;
  }
}

async function 讀取使用者索引() {
  if (使用者索引.value) {
    return 使用者索引.value;
  }

  const 回應 = await fetch(使用者索引網址, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!回應.ok) {
    throw new Error(`讀取個人成績單索引失敗：HTTP ${回應.status}`);
  }

  使用者索引.value = await 回應.json();
  return 使用者索引.value;
}

async function 讀取全服統計() {
  if (全服統計資料.value) {
    return 全服統計資料.value;
  }

  全服統計讀取中.value = true;
  全服統計錯誤訊息.value = "";

  try {
    const 回應 = await fetch(全服統計網址, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!回應.ok) {
      throw new Error(`讀取全服統計失敗：HTTP ${回應.status}`);
    }

    全服統計資料.value = await 回應.json();
    return 全服統計資料.value;
  } catch (錯誤) {
    全服統計錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取全服統計";
    return null;
  } finally {
    全服統計讀取中.value = false;
  }
}

function 尋找使用者索引項目(角色名稱) {
  const 正規化名稱 = 角色名稱.trim().toLocaleLowerCase("zh-TW");
  return 使用者索引列表.value.find((使用者) => 使用者.character_name.toLocaleLowerCase("zh-TW") === 正規化名稱) || null;
}

function 格式化使用者搜尋文字(角色名稱, 伺服器 = "") {
  const 名稱 = String(角色名稱 || "").trim();
  const 伺服器名稱 = String(伺服器 || "").trim();
  return 伺服器名稱 ? `${名稱} @ ${伺服器名稱}` : 名稱;
}

function 解析使用者搜尋輸入(輸入文字) {
  const 文字 = String(輸入文字 || "").trim();
  const 分隔結果 = 文字.match(/^(.*?)\s*[@＠]\s*(.+)$/);
  if (!分隔結果) {
    return {
      角色名稱: 文字,
      伺服器: "",
    };
  }

  return {
    角色名稱: 分隔結果[1].trim(),
    伺服器: 分隔結果[2].trim(),
  };
}

function 更新網址為使用者(角色名稱, 伺服器 = "") {
  if (typeof window === "undefined") {
    return;
  }

  const 網址 = new URL(window.location.href);
  網址.searchParams.set("user", 角色名稱);
  if (伺服器) {
    網址.searchParams.set("server", 伺服器);
  } else {
    網址.searchParams.delete("server");
  }
  window.history.pushState(null, "", 網址);
}

function 更新網址為排行榜() {
  if (typeof window === "undefined") {
    return;
  }

  const 網址 = new URL(window.location.href);
  網址.searchParams.delete("user");
  網址.searchParams.delete("server");
  window.history.pushState(null, "", 網址);
}

async function 載入使用者成績(角色名稱, 伺服器 = "", 選項 = {}) {
  const 查詢名稱 = String(角色名稱 || "").trim();
  if (!查詢名稱) {
    使用者錯誤訊息.value = "請輸入角色名稱";
    return;
  }

  頁面模式.value = "user";
  使用者讀取中.value = true;
  使用者錯誤訊息.value = "";
  使用者搜尋關鍵字.value = 查詢名稱;

  try {
    await 讀取使用者索引();
    const 索引項目 = 尋找使用者索引項目(查詢名稱);
    const 資料網址 = 索引項目?.file_path ? 建立公開資料網址(索引項目.file_path) : 建立使用者預設資料網址(查詢名稱);
    const 回應 = await fetch(資料網址, {
      headers: {
        Accept: "application/json",
      },
    });

    if (!回應.ok) {
      throw new Error(`找不到「${查詢名稱}」的個人成績單`);
    }

    使用者資料.value = await 回應.json();
    const 伺服器列表 = Array.isArray(使用者資料.value?.servers) ? 使用者資料.value.servers : [];
    使用者伺服器篩選.value = 伺服器列表.includes(伺服器) ? 伺服器 : 伺服器列表[0] || "";
    使用者搜尋關鍵字.value = 格式化使用者搜尋文字(使用者資料.value.character_name || 查詢名稱, 使用者伺服器篩選.value);

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
    throw new Error("請輸入兩個角色名稱");
  }

  await 讀取使用者索引();
  const 索引項目 = 尋找使用者索引項目(查詢.角色名稱);
  const 資料網址 = 索引項目?.file_path ? 建立公開資料網址(索引項目.file_path) : 建立使用者預設資料網址(查詢.角色名稱);
  const 回應 = await fetch(資料網址, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!回應.ok) {
    throw new Error(`找不到「${查詢.角色名稱}」的個人成績單`);
  }

  const 資料 = await 回應.json();
  const 伺服器列表 = Array.isArray(資料?.servers) ? 資料.servers : [];
  const 伺服器 = 伺服器列表.includes(查詢.伺服器) ? 查詢.伺服器 : 伺服器列表[0] || "";
  return {
    資料,
    伺服器,
  };
}

async function 提交角色比較() {
  const 左輸入 = 比較角色左輸入.value.trim();
  const 右輸入 = 比較角色右輸入.value.trim();
  if (!左輸入 || !右輸入) {
    比較錯誤訊息.value = "請輸入兩個角色名稱";
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
  } catch (錯誤) {
    比較角色左資料.value = null;
    比較角色右資料.value = null;
    比較錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取角色比較資料";
  } finally {
    比較讀取中.value = false;
  }
}

function 切換到排行榜() {
  頁面模式.value = "ranking";
  更新網址為排行榜();
}

function 切換到全服統計() {
  頁面模式.value = "stats";
  更新網址為排行榜();
  讀取全服統計();
}

function 切換到個人成績單() {
  頁面模式.value = "user";
  讀取使用者索引().catch((錯誤) => {
    使用者錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單索引";
  });
}

function 切換到角色比較() {
  頁面模式.value = "compare";
  更新網址為排行榜();
  讀取使用者索引().catch((錯誤) => {
    比較錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取個人成績單索引";
  });
}

function 切換到職業分析() {
  頁面模式.value = "jobs";
  更新網址為排行榜();
  讀取全服統計();
}

function 切換到近期動態() {
  頁面模式.value = "activity";
  更新網址為排行榜();
  使用者錯誤訊息.value = "";
  讀取使用者索引().catch((錯誤) => {
    使用者錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取近期動態索引";
  });
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

watch(副本鍵值, () => {
  伺服器篩選.value = "";
  職業類型篩選.value = "";
  職業篩選.value = "";
  搜尋關鍵字.value = "";
  目前頁碼.value = 1;
  讀取排行榜資料();
});

watch(職業類型篩選, () => {
  職業篩選.value = "";
});

watch([伺服器篩選, 職業類型篩選, 職業篩選, 搜尋關鍵字, 排序欄位], () => {
  目前頁碼.value = 1;
});

watch([職業類型篩選, 職業篩選], () => {
  主色模式.value = 目前職業主色();
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

watch(使用者伺服器篩選, (伺服器) => {
  if (頁面模式.value === "user" && 使用者資料.value?.character_name) {
    更新網址為使用者(使用者資料.value.character_name, 伺服器);
  }
});

watch([統計副本鍵值, 全服統計資料], () => {
  if (統計伺服器篩選.value && !統計伺服器選項.value.includes(統計伺服器篩選.value)) {
    統計伺服器篩選.value = "";
  }

  if (!統計職業範圍選項.value.some((選項) => 選項.value === 統計職業範圍.value)) {
    統計職業範圍.value = "all";
  }
});

watch([全服統計資料, 職業分析職業選項], () => {
  if (職業分析職業.value && !職業分析職業選項.value.some((職業) => 職業.job === 職業分析職業.value)) {
    職業分析職業.value = "";
  }
  if (職業分析職業類型.value && !職業分析類型選項.value.some((類型) => 類型.代碼 === 職業分析職業類型.value)) {
    職業分析職業類型.value = "";
  }
});

onMounted(() => {
  套用主題(偵測初始主題());
  const 網址參數 = typeof window === "undefined" ? new URLSearchParams() : new URL(window.location.href).searchParams;
  const 初始使用者 = 網址參數.get("user");
  const 初始伺服器 = 網址參數.get("server") || "";

  if (初始使用者) {
    載入使用者成績(初始使用者, 初始伺服器, { 更新網址: false });
  }

  讀取中.value = true;
  錯誤訊息.value = "";
  讀取副本清單()
    .then(() => 讀取排行榜資料())
    .catch((錯誤) => {
      錯誤訊息.value = 錯誤 instanceof Error ? 錯誤.message : "無法讀取副本清單";
      讀取中.value = false;
    });
});
</script>

<template>
  <main class="頁面" :data-accent="主色模式">
    <section class="標題區">
      <div>
        <p class="副標">{{ 頁面副標 }}</p>
        <h1>{{ 頁面標題 }}</h1>
      </div>
      <p class="更新時間">
        {{ 更新時間文字 }}
      </p>
      <button class="主題切換" type="button" :aria-label="`切換為${主題按鈕文字}模式`" @click="切換主題">
        {{ 目前主題文字 }}
      </button>
    </section>

    <nav class="頁面切換" aria-label="頁面切換">
      <button type="button" :class="{ 作用中: 頁面模式 === 'ranking' }" @click="切換到排行榜">排行榜</button>
      <button type="button" :class="{ 作用中: 頁面模式 === 'stats' }" @click="切換到全服統計">全服統計</button>
      <button type="button" :class="{ 作用中: 頁面模式 === 'user' }" @click="切換到個人成績單">個人成績單</button>
      <button type="button" :class="{ 作用中: 頁面模式 === 'compare' }" @click="切換到角色比較">角色比較</button>
      <button type="button" :class="{ 作用中: 頁面模式 === 'jobs' }" @click="切換到職業分析">職業分析</button>
      <button type="button" :class="{ 作用中: 頁面模式 === 'activity' }" @click="切換到近期動態">近期動態</button>
    </nav>

    <template v-if="頁面模式 === 'ranking'">
    <section class="工具列" aria-label="排行榜篩選">
      <div class="欄位 副本選單欄位" @focusout="處理副本選單失焦">
        <span>副本</span>
        <div class="副本選單">
          <button
            class="副本選單按鈕"
            type="button"
            :aria-expanded="副本選單開啟"
            aria-haspopup="true"
            @click="切換副本選單"
          >
            <span class="副本選單目前值">{{ 副本選單文字 }}</span>
            <span class="選單箭頭">▾</span>
          </button>

          <div v-if="副本選單開啟" class="副本選單面板" role="menu" aria-label="副本">
            <section v-for="分組 in 副本分組" :key="分組.分類" class="副本分類群">
              <p class="副本分類標題">{{ 分組.分類 }}</p>
              <button
                v-for="副本 in 分組.副本列表"
                :key="副本.key"
                class="副本選單項"
                type="button"
                :class="{ 已選取: 副本鍵值 === 副本.key }"
                @click="選擇副本(副本)"
              >
                {{ 副本.name }}
              </button>
            </section>
          </div>
        </div>
      </div>

      <label class="欄位">
        <span>排序</span>
        <select v-model="排序欄位">
          <option v-for="選項 in 排序選項" :key="選項.value" :value="選項.value">
            {{ 選項.label }}
          </option>
        </select>
      </label>

      <label class="欄位">
        <span>伺服器</span>
        <select v-model="伺服器篩選">
          <option value="">全部伺服器</option>
          <option v-for="伺服器 in 伺服器選項" :key="伺服器" :value="伺服器">
            {{ 伺服器 }}
          </option>
        </select>
      </label>

      <div class="欄位 職業選單欄位" @focusout="處理職業選單失焦">
        <span>職業</span>
        <div class="職業選單">
          <button
            class="職業選單按鈕"
            type="button"
            :aria-expanded="職業選單開啟"
            aria-haspopup="true"
            @click="切換職業選單"
          >
            <span class="職業選單目前值">
              <img
                v-if="職業選單Icon路徑"
                class="職業圖示"
                :src="職業選單Icon路徑"
                alt=""
                loading="lazy"
                @error="隱藏載入失敗圖片"
              />
              <span>{{ 職業選單文字 }}</span>
            </span>
            <span class="選單箭頭">▾</span>
          </button>

          <div v-if="職業選單開啟" class="職業選單面板">
            <div class="職業選單分類欄" role="menu" aria-label="職業類型">
              <button
                class="職業選單項"
                type="button"
                :class="{ 已選取: !職業類型篩選 && !職業篩選 }"
                @click="清除職業篩選"
              >
                全部職業
              </button>
              <button
                v-for="類型 in 職業類型選項"
                :key="類型.代碼"
                class="職業選單項"
                type="button"
                :class="[職業色彩類別(類型.色彩), { 已選取: 職業類型篩選 === 類型.代碼 }]"
                @click="選擇職業類型(類型.代碼)"
              >
                <img
                  v-if="職業類型Icon路徑(類型.代碼)"
                  class="職業圖示"
                  :src="職業類型Icon路徑(類型.代碼)"
                  alt=""
                  loading="lazy"
                  @error="隱藏載入失敗圖片"
                />
                <span>{{ 類型.名稱 }}</span>
              </button>
            </div>

            <div class="職業選單職業欄" role="menu" aria-label="職業">
              <template v-if="職業類型篩選 && 職業選項.length > 0">
                <button
                  v-for="職業 in 職業選項"
                  :key="職業.代碼"
                  class="職業選單項"
                  type="button"
                  :class="[職業色彩類別(職業.色彩), { 已選取: 職業篩選 === 職業.代碼 }]"
                  @click="選擇職業(職業.代碼)"
                >
                  <img
                    v-if="職業Icon路徑(職業.代碼)"
                    class="職業圖示"
                    :src="職業Icon路徑(職業.代碼)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                  <span>{{ 職業.名稱 }}</span>
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <label class="欄位 搜尋欄位">
        <span>角色名稱</span>
        <input v-model="搜尋關鍵字" type="search" placeholder="搜尋角色名稱" />
      </label>
    </section>

    <section class="表格區" aria-live="polite">
      <div v-if="讀取中" class="狀態列">讀取排行榜資料中</div>
      <div v-else-if="錯誤訊息" class="狀態列 錯誤">{{ 錯誤訊息 }}</div>
      <div v-else-if="過濾後排行列.length === 0" class="狀態列">目前沒有符合條件的排行榜資料</div>

      <template v-else>
        <div class="分頁資訊列">
          <p>顯示第 {{ 顯示起始排名 }}-{{ 顯示結束排名 }} 名，共 {{ 過濾後排行列.length }} 筆</p>
          <div class="分頁控制" aria-label="排行榜分頁">
            <button type="button" :disabled="!有上一頁" @click="前一頁">上一頁</button>
            <label>
              <span>頁碼</span>
              <input
                v-model.number="目前頁碼"
                type="number"
                min="1"
                :max="總頁數"
                inputmode="numeric"
                @change="前往頁碼(目前頁碼)"
              />
            </label>
            <span class="頁數文字">/ {{ 總頁數 }}</span>
            <button type="button" :disabled="!有下一頁" @click="下一頁">下一頁</button>
          </div>
        </div>

        <table>
          <thead>
            <tr>
              <th scope="col">排名</th>
              <th scope="col">角色名稱</th>
              <th scope="col">伺服器</th>
              <th scope="col">職業</th>
              <th scope="col" class="數字">
                <span class="表頭說明標籤">
                  <span>Active</span>
                  <span class="說明提示">
                    <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                    <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                  </span>
                </span>
              </th>
              <th scope="col" class="數字">
                <span class="表頭說明標籤">
                  <span>DPS</span>
                  <span class="說明提示">
                    <button class="說明提示按鈕" type="button" aria-label="DPS 說明">?</button>
                    <span class="說明提示內容" role="tooltip">{{ 統計說明文字("DPS") }}</span>
                  </span>
                </span>
              </th>
              <th scope="col" class="數字">
                <span class="表頭說明標籤">
                  <span>rDPS</span>
                  <span class="說明提示">
                    <button class="說明提示按鈕" type="button" aria-label="rDPS 說明">?</button>
                    <span class="說明提示內容" role="tooltip">{{ 統計說明文字("rDPS") }}</span>
                  </span>
                </span>
              </th>
              <th scope="col" class="數字">
                <span class="表頭說明標籤">
                  <span>aDPS</span>
                  <span class="說明提示">
                    <button class="說明提示按鈕" type="button" aria-label="aDPS 說明">?</button>
                    <span class="說明提示內容" role="tooltip">{{ 統計說明文字("aDPS") }}</span>
                  </span>
                </span>
              </th>
              <th scope="col" class="數字">通關時間</th>
              <th scope="col">紀錄時間</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(列, index) in 當頁排行列" :key="列.id">
              <td class="排名" :class="排名色彩類別(當頁起始索引 + index + 1)">
                #{{ 當頁起始索引 + index + 1 }}
              </td>
              <td>
                <button class="文字連結" type="button" @click="開啟個人成績單(列)">
                  {{ 列.角色名稱 }}
                </button>
                <a v-if="列.reportUrl" class="次要連結" :href="列.reportUrl" target="_blank" rel="noreferrer">報告</a>
              </td>
              <td>{{ 列.伺服器 }}</td>
              <td>
                <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.職業代碼))">
                  <img
                    v-if="職業Icon路徑(列.職業代碼)"
                    class="職業圖示 職業標籤圖示"
                    :src="職業Icon路徑(列.職業代碼)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                  <span>{{ 列.職業 }}</span>
                </span>
              </td>
              <td class="數字">{{ 格式化Active(列.active) }}</td>
              <td class="數字">{{ 格式化傷害數值(列.dps) }}</td>
              <td class="數字">{{ 格式化傷害數值(列.rdps) }}</td>
              <td class="數字">{{ 格式化傷害數值(列.adps) }}</td>
              <td class="數字">{{ 格式化通關時間(列.通關秒數) }}</td>
              <td>{{ 格式化紀錄時間(列.紀錄時間) }}</td>
            </tr>
          </tbody>
        </table>

        <div class="分頁資訊列 分頁資訊列底部">
          <p>每頁 {{ 每頁筆數 }} 筆</p>
          <div class="分頁控制" aria-label="排行榜底部分頁">
            <button type="button" :disabled="!有上一頁" @click="前一頁">上一頁</button>
            <span class="頁數文字">第 {{ 安全目前頁碼 }} / {{ 總頁數 }} 頁</span>
            <button type="button" :disabled="!有下一頁" @click="下一頁">下一頁</button>
          </div>
        </div>
      </template>
    </section>
    </template>
    <template v-else-if="頁面模式 === 'stats'">
      <section class="統計工具列" aria-label="全服統計篩選">
        <div class="欄位 副本選單欄位" @focusout="處理統計副本選單失焦">
          <span>統計範圍</span>
          <div class="副本選單">
            <button
              class="副本選單按鈕"
              type="button"
              :aria-expanded="統計副本選單開啟"
              aria-haspopup="true"
              @click="切換統計副本選單"
            >
              <span class="副本選單目前值">{{ 統計副本選單文字 }}</span>
              <span class="選單箭頭">▾</span>
            </button>

            <div v-if="統計副本選單開啟" class="副本選單面板" role="menu" aria-label="統計範圍">
              <section class="副本分類群">
                <p class="副本分類標題">全部</p>
                <button
                  class="副本選單項"
                  type="button"
                  :class="{ 已選取: 統計副本鍵值 === 'all' }"
                  @click="選擇統計副本(null)"
                >
                  全部副本
                </button>
              </section>
              <section v-for="分組 in 副本分組" :key="分組.分類" class="副本分類群">
                <p class="副本分類標題">{{ 分組.分類 }}</p>
                <button
                  v-for="副本 in 分組.副本列表"
                  :key="副本.key"
                  class="副本選單項"
                  type="button"
                  :class="{ 已選取: 統計副本鍵值 === 副本.key }"
                  @click="選擇統計副本(副本)"
                >
                  {{ 副本.name }}
                </button>
              </section>
            </div>
          </div>
        </div>
        <label class="欄位">
          <span>伺服器</span>
          <select v-model="統計伺服器篩選">
            <option value="">全部伺服器</option>
            <option v-for="伺服器 in 統計伺服器選項" :key="伺服器" :value="伺服器">
              {{ 伺服器 }}
            </option>
          </select>
        </label>
        <label class="欄位">
          <span>職業範圍</span>
          <select v-model="統計職業範圍">
            <option v-for="選項 in 統計職業範圍選項" :key="選項.value" :value="選項.value">
              {{ 選項.label }}
            </option>
          </select>
        </label>
        <label class="欄位">
          <span>伺服器佔比拆分</span>
          <select v-model="伺服器拆分模式">
            <option value="none">不拆分</option>
            <option value="role">依職業類型</option>
            <option value="job">依各職業</option>
          </select>
        </label>
      </section>

      <section class="全服統計區" aria-live="polite">
        <div v-if="全服統計讀取中" class="狀態列">讀取全服統計中</div>
        <div v-else-if="全服統計錯誤訊息" class="狀態列 錯誤">{{ 全服統計錯誤訊息 }}</div>
        <div v-else-if="!全服統計資料" class="狀態列">正在準備全服統計資料</div>

        <template v-else>
          <section class="統計概要" aria-label="全服統計概要">
            <div v-for="項目 in 全服概要項目" :key="項目.標籤" class="概要項">
              <span class="說明標籤">
                <span>{{ 項目.標籤 }}</span>
                <span v-if="統計說明文字(項目.標籤)" class="說明提示">
                  <button class="說明提示按鈕" type="button" :aria-label="`${項目.標籤}說明`">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字(項目.標籤) }}</span>
                </span>
              </span>
              <strong>{{ 項目.數值 }}</strong>
            </div>
          </section>

          <section
            v-if="顯示零式進度漏斗 && 零式進度漏斗.length > 0"
            class="統計面板 統計面板寬 零式漏斗面板"
            aria-label="零式進度漏斗"
          >
            <header class="統計面板標題">
              <h2 class="說明標籤">
                <span>零式進度漏斗</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="零式進度漏斗說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("零式進度漏斗") }}</span>
                </span>
              </h2>
              <span>{{ 零式漏斗條件文字 }}</span>
            </header>
            <div class="零式漏斗列表">
              <article v-for="項目 in 零式進度漏斗" :key="項目.encounter_key" class="零式漏斗項">
                <div class="漏斗副本列">
                  <span class="漏斗層級">{{ 項目.層級文字 }}</span>
                  <strong>{{ 項目.encounter_name }}</strong>
                </div>
                <div class="漏斗數值列">
                  <strong>{{ 格式化整數(項目.顯示數量) }} {{ 零式漏斗單位 }}</strong>
                  <span>相對首層 {{ 格式化百分比(項目.相對首層比例) }}</span>
                </div>
                <div class="漏斗條" aria-hidden="true">
                  <span :style="比例條樣式(項目.相對首層比例)"></span>
                </div>
                <div class="漏斗補充列">
                  <span v-if="項目.索引 === 0">基準層</span>
                  <span v-else>較上一層 {{ 格式化帶號整數(項目.較上一層差異) }}・{{ 格式化百分比(項目.上一層比例) }}</span>
                </div>
              </article>
            </div>
          </section>

          <section class="統計版面" aria-label="伺服器與職業佔比">
            <article class="統計面板">
              <header class="統計面板標題">
                <h2 class="說明標籤">
                  <span>伺服器佔比</span>
                  <span class="說明提示">
                    <button class="說明提示按鈕" type="button" aria-label="伺服器佔比說明">?</button>
                    <span class="說明提示內容" role="tooltip">{{ 統計說明文字("伺服器佔比") }}</span>
                  </span>
                </h2>
                <span>{{ 統計條件文字 }}</span>
              </header>
              <div class="分布列表">
                <div v-for="項目 in 伺服器佔比列表" :key="項目.server" class="分布項">
                  <div class="分布列">
                    <strong>{{ 項目.server }}</strong>
                    <span>{{ 格式化整數(項目.顯示數量) }} {{ 伺服器佔比單位 }}・{{ 格式化百分比(項目.顯示比例) }}</span>
                  </div>
                  <div class="分布條" aria-hidden="true">
                    <span class="分布條填滿" :style="比例條樣式(項目.顯示比例)"></span>
                  </div>
                  <div v-if="取得伺服器拆分列表(項目).length > 0" class="分布子列表">
                    <span
                      v-for="拆分 in 取得伺服器拆分列表(項目)"
                      :key="拆分.role || 拆分.job"
                      class="分布子項"
                      :class="職業色彩類別(拆分.job ? 職業代碼色彩(拆分.job) : 職業類型色彩(拆分.role))"
                    >
                      <img
                        v-if="拆分.job && 職業Icon路徑(拆分.job)"
                        class="職業圖示"
                        :src="職業Icon路徑(拆分.job)"
                        alt=""
                        loading="lazy"
                        @error="隱藏載入失敗圖片"
                      />
                      <span>{{ 拆分.顯示名稱 }}</span>
                      <em>{{ 格式化百分比(拆分.顯示比例) }}</em>
                    </span>
                  </div>
                </div>
              </div>
            </article>

            <article class="統計面板">
              <header class="統計面板標題">
                <h2 class="說明標籤">
                  <span>職業佔比</span>
                  <span class="說明提示">
                    <button class="說明提示按鈕" type="button" aria-label="職業佔比說明">?</button>
                    <span class="說明提示內容" role="tooltip">{{ 統計說明文字("職業佔比") }}</span>
                  </span>
                </h2>
                <span>{{ 職業佔比標題文字 }}</span>
              </header>
              <div class="職業佔比分組">
                <article v-for="群組 in 職業佔比分組" :key="群組.role" class="職業佔比群組" :class="職業色彩類別(群組.色彩)">
                  <header class="職業佔比群組標題">
                    <strong>{{ 群組.role_name }}</strong>
                    <span>{{ 格式化整數(群組.clear_count) }} 紀錄・{{ 格式化百分比(群組.percentage) }}</span>
                  </header>
                  <div class="分布條" aria-hidden="true">
                    <span
                      class="分布條填滿"
                      :class="職業色彩類別(群組.色彩)"
                      :style="比例條樣式(群組.percentage)"
                    ></span>
                  </div>
                  <div class="職業佔比職業列表">
                    <div v-for="職業 in 群組.jobs" :key="職業.job" class="職業佔比職業">
                      <span class="分布職業">
                        <img
                          v-if="職業Icon路徑(職業.job)"
                          class="職業圖示"
                          :src="職業Icon路徑(職業.job)"
                          alt=""
                          loading="lazy"
                          @error="隱藏載入失敗圖片"
                        />
                        <span>{{ 顯示職業名稱(職業.job) }}</span>
                      </span>
                      <strong>{{ 格式化整數(職業.clear_count) }}</strong>
                      <small>{{ 格式化百分比(職業.percentage) }}</small>
                    </div>
                  </div>
                </article>
              </div>
            </article>
          </section>

          <section v-if="伺服器生態矩陣.length > 0" class="統計面板 統計面板寬" aria-label="伺服器生態比較">
            <header class="統計面板標題">
              <h2 class="說明標籤">
                <span>伺服器生態比較</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="伺服器生態比較說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("伺服器生態比較") }}</span>
                </span>
              </h2>
              <span>{{ 統計範圍文字 }}</span>
            </header>
            <div class="生態矩陣外框">
              <table class="生態矩陣">
                <thead>
                  <tr>
                    <th scope="col">伺服器</th>
                    <th v-for="欄位 in 伺服器生態欄位" :key="欄位.role" scope="col">{{ 欄位.label }}</th>
                    <th scope="col">主要傾向</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="列 in 伺服器生態矩陣" :key="列.server">
                    <th scope="row">{{ 列.server }}</th>
                    <td v-for="欄位 in 列.欄位" :key="欄位.role">
                      <span class="熱力格" :class="職業色彩類別(欄位.色彩)" :style="熱力格樣式(欄位.比例)">
                        <strong>{{ 格式化百分比(欄位.比例) }}</strong>
                        <small>{{ 格式化整數(欄位.數量) }}</small>
                      </span>
                    </td>
                    <td>
                      <span v-if="列.最高欄位" class="職業標籤" :class="職業色彩類別(列.最高欄位.色彩)">
                        {{ 列.最高欄位.label }}
                      </span>
                      <span v-else>-</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section v-if="顯示副本通關概覽" class="統計面板 統計面板寬" aria-label="副本通關概覽">
            <header class="統計面板標題">
              <h2>副本通關概覽</h2>
              <span>{{ 統計條件文字 }}</span>
            </header>
            <div class="統計表格外框">
              <table class="統計表格">
                <thead>
                  <tr>
                    <th scope="col">副本</th>
                    <th scope="col">分類</th>
                    <th scope="col" class="數字">
                      <span class="表頭說明標籤">
                        <span>{{ 職業範圍類型(統計職業範圍) === "all" ? "通關角色" : "通關紀錄" }}</span>
                        <span class="說明提示">
                          <button
                            class="說明提示按鈕"
                            type="button"
                            :aria-label="`${職業範圍類型(統計職業範圍) === 'all' ? '通關角色' : '通關紀錄'}說明`"
                          >
                            ?
                          </button>
                          <span class="說明提示內容" role="tooltip">
                            {{ 統計說明文字(職業範圍類型(統計職業範圍) === "all" ? "通關角色" : "通關紀錄") }}
                          </span>
                        </span>
                      </span>
                    </th>
                    <th scope="col" class="數字">
                      <span class="表頭說明標籤">
                        <span>範圍佔比</span>
                        <span class="說明提示">
                          <button class="說明提示按鈕" type="button" aria-label="範圍佔比說明">?</button>
                          <span class="說明提示內容" role="tooltip">{{ 統計說明文字("範圍佔比") }}</span>
                        </span>
                      </span>
                    </th>
                    <th scope="col">最高伺服器</th>
                    <th scope="col">最高職業</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="副本 in 副本通關概覽" :key="副本.encounter_key">
                    <td>
                      <button class="文字連結" type="button" @click="統計副本鍵值 = 副本.encounter_key">
                        {{ 副本.encounter_name }}
                      </button>
                    </td>
                    <td>{{ 副本.encounter_category || "-" }}</td>
                    <td class="數字">{{ 格式化整數(副本.顯示數量) }}</td>
                    <td class="數字">{{ 格式化百分比(副本.顯示比例) }}</td>
                    <td>
                      <span v-if="統計伺服器篩選">{{ 統計伺服器篩選 }}</span>
                      <span v-else-if="副本.最高伺服器">
                        {{ 副本.最高伺服器.server }}・{{ 格式化百分比(副本.最高伺服器.顯示比例) }}
                      </span>
                      <span v-else>-</span>
                    </td>
                    <td>
                      <span v-if="副本.最高職業" class="職業標籤" :class="職業色彩類別(職業代碼色彩(副本.最高職業.job))">
                        <img
                          v-if="職業Icon路徑(副本.最高職業.job)"
                          class="職業圖示 職業標籤圖示"
                          :src="職業Icon路徑(副本.最高職業.job)"
                          alt=""
                          loading="lazy"
                          @error="隱藏載入失敗圖片"
                        />
                        <span>{{ 顯示職業名稱(副本.最高職業.job) }}</span>
                      </span>
                      <span v-else>-</span>
                    </td>
                  </tr>
                  <tr v-if="副本通關概覽.length === 0">
                    <td colspan="6" class="統計空列">目前沒有符合條件的副本統計</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>

          <section class="統計面板 統計面板寬" aria-label="資料收集狀態">
            <header class="統計面板標題">
              <h2>資料收集狀態</h2>
              <span>{{ 格式化整數(資料狀態列表.filter((副本) => 副本.有資料).length) }} / {{ 格式化整數(資料狀態列表.length) }} 副本已有資料</span>
            </header>
            <div class="資料狀態分組列表">
              <section v-for="分組 in 資料狀態分組" :key="分組.分類" class="資料狀態分組">
                <header class="資料狀態分組標題">
                  <span>
                    <strong>{{ 分組.分類 }}</strong>
                    <small>{{ 格式化整數(分組.已收錄數) }} / {{ 格式化整數(分組.總數) }} 已收錄</small>
                  </span>
                  <em>{{ 格式化百分比(分組.收錄比例) }}</em>
                </header>
                <div class="分布條" aria-hidden="true">
                  <span class="分布條填滿" :style="比例條樣式(分組.收錄比例)"></span>
                </div>
                <div class="資料狀態列表">
                  <article
                    v-for="副本 in 分組.副本列表"
                    :key="副本.encounter_key"
                    class="資料狀態項"
                    :class="{ 已收錄: 副本.有資料 }"
                  >
                    <span>
                      <small>{{ 副本.encounter_category || "副本" }}</small>
                      <strong>{{ 副本.encounter_name }}</strong>
                    </span>
                    <em>{{ 副本.狀態文字 }}</em>
                    <small>{{ 副本.有資料 ? `${格式化整數(副本.character_count)} 角色` : "尚無公開成績" }}</small>
                  </article>
                </div>
              </section>
            </div>
          </section>
        </template>
      </section>
    </template>
    <template v-else-if="頁面模式 === 'jobs'">
      <section class="職業分析工具列" aria-label="職業分析篩選">
        <div class="欄位 職業選單欄位" @focusout="處理職業分析選單失焦">
          <span>職業</span>
          <div class="職業選單">
            <button
              class="職業選單按鈕"
              type="button"
              :aria-expanded="職業分析選單開啟"
              aria-haspopup="true"
              @click="切換職業分析選單"
            >
              <span class="職業選單目前值">
                <img
                  v-if="職業分析選單Icon路徑"
                  class="職業圖示"
                  :src="職業分析選單Icon路徑"
                  alt=""
                  loading="lazy"
                  @error="隱藏載入失敗圖片"
                />
                <span>{{ 職業分析選單文字 }}</span>
              </span>
              <span class="選單箭頭">▾</span>
            </button>

            <div v-if="職業分析選單開啟" class="職業選單面板">
              <div class="職業選單分類欄" role="menu" aria-label="職業類型">
                <button
                  v-for="類型 in 職業分析類型選項"
                  :key="類型.代碼"
                  class="職業選單項"
                  type="button"
                  :class="[職業色彩類別(類型.色彩), { 已選取: 職業分析目前類型代碼 === 類型.代碼 }]"
                  @click="選擇職業分析類型(類型.代碼)"
                >
                  <img
                    v-if="職業類型Icon路徑(類型.代碼)"
                    class="職業圖示"
                    :src="職業類型Icon路徑(類型.代碼)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                  <span>{{ 類型.名稱 }}</span>
                </button>
              </div>

              <div class="職業選單職業欄" role="menu" aria-label="職業">
                <button
                  v-for="職業 in 職業分析可選職業"
                  :key="職業.代碼"
                  class="職業選單項"
                  type="button"
                  :class="[職業色彩類別(職業.色彩), { 已選取: 職業分析目前職業代碼 === 職業.代碼 }]"
                  @click="選擇職業分析職業(職業.代碼)"
                >
                  <img
                    v-if="職業Icon路徑(職業.代碼)"
                    class="職業圖示"
                    :src="職業Icon路徑(職業.代碼)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                  <span>{{ 職業.名稱 }}</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="職業分析區" aria-live="polite">
        <div v-if="全服統計讀取中" class="狀態列">讀取職業分析資料中</div>
        <div v-else-if="全服統計錯誤訊息" class="狀態列 錯誤">{{ 全服統計錯誤訊息 }}</div>
        <div v-else-if="!全服統計資料" class="狀態列">正在準備職業分析資料</div>
        <div v-else-if="!職業分析目前職業" class="狀態列">目前沒有可分析的職業資料</div>

        <template v-else>
          <section class="職業焦點卡" aria-label="職業概要">
            <header class="職業焦點標題">
              <span class="職業焦點圖示" :class="職業色彩類別(職業代碼色彩(職業分析目前職業.job))">
                <img
                  v-if="職業Icon路徑(職業分析目前職業.job)"
                  :src="職業Icon路徑(職業分析目前職業.job)"
                  :alt="顯示職業名稱(職業分析目前職業.job)"
                  loading="lazy"
                  @error="隱藏載入失敗圖片"
                />
              </span>
              <span>
                <small>{{ 職業分析目前職業.role_name }}</small>
                <strong>{{ 顯示職業名稱(職業分析目前職業.job) }}</strong>
              </span>
            </header>

            <div class="職業分析概要">
              <div v-for="項目 in 職業分析概要" :key="項目.標籤" class="概要項">
                <span>{{ 項目.標籤 }}</span>
                <strong>{{ 項目.數值 }}</strong>
              </div>
            </div>
          </section>

          <section class="統計版面" aria-label="職業副本與伺服器分析">
            <article class="統計面板">
              <header class="統計面板標題">
                <h2>副本分布</h2>
                <span>該職業公開通關分布</span>
              </header>
              <div class="分布列表">
                <div v-for="副本 in 職業分析副本列" :key="副本.encounter_key" class="分布項">
                  <div class="分布列">
                    <strong>{{ 副本.encounter_name }}</strong>
                    <span>{{ 格式化整數(副本.數量) }} 紀錄・{{ 格式化百分比(副本.職業內佔比) }}</span>
                  </div>
                  <div class="分布條" aria-hidden="true">
                    <span
                      class="分布條填滿"
                      :class="職業色彩類別(職業代碼色彩(職業分析目前職業.job))"
                      :style="比例條樣式(副本.職業內佔比)"
                    ></span>
                  </div>
                  <small class="職業分析補充">副本內佔比 {{ 格式化百分比(副本.副本內佔比) }}</small>
                </div>
              </div>
            </article>

            <article class="統計面板">
              <header class="統計面板標題">
                <h2>伺服器分布</h2>
                <span>該職業全服落點</span>
              </header>
              <div class="分布列表">
                <div v-for="伺服器 in 職業分析伺服器列" :key="伺服器.server" class="分布項">
                  <div class="分布列">
                    <strong>{{ 伺服器.server }}</strong>
                    <span>{{ 格式化整數(伺服器.數量) }} 紀錄・{{ 格式化百分比(伺服器.全職業佔比) }}</span>
                  </div>
                  <div class="分布條" aria-hidden="true">
                    <span
                      class="分布條填滿"
                      :class="職業色彩類別(職業代碼色彩(職業分析目前職業.job))"
                      :style="比例條樣式(伺服器.全職業佔比)"
                    ></span>
                  </div>
                  <small class="職業分析補充">伺服器內佔比 {{ 格式化百分比(伺服器.伺服器內佔比) }}</small>
                </div>
              </div>
            </article>
          </section>
        </template>
      </section>
    </template>
    <template v-else-if="頁面模式 === 'activity'">
      <section class="近期動態區" aria-live="polite">
        <div v-if="!使用者索引 && !使用者錯誤訊息" class="狀態列">讀取近期動態中</div>
        <div v-else-if="使用者錯誤訊息" class="狀態列 錯誤">{{ 使用者錯誤訊息 }}</div>

        <template v-else>
          <section class="統計概要" aria-label="近期動態概要">
            <div v-for="項目 in 近期動態概要" :key="項目.標籤" class="概要項">
              <span>{{ 項目.標籤 }}</span>
              <strong>{{ 項目.數值 }}</strong>
            </div>
          </section>

          <section class="統計面板 統計面板寬" aria-label="最近有紀錄的角色">
            <header class="統計面板標題">
              <h2>最近有紀錄的角色</h2>
              <span>依公開紀錄時間排序</span>
            </header>
            <div class="統計表格外框">
              <table class="統計表格 近期動態表格">
                <thead>
                  <tr>
                    <th scope="col">角色</th>
                    <th scope="col">伺服器</th>
                    <th scope="col" class="數字">副本數</th>
                    <th scope="col" class="數字">公開成績</th>
                    <th scope="col" class="數字">最佳 rDPS</th>
                    <th scope="col">最後紀錄</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="使用者 in 近期動態角色列表" :key="使用者.character_name">
                    <td>
                      <button class="文字連結" type="button" @click="載入使用者成績(使用者.character_name, 使用者.servers?.[0] || '')">
                        {{ 使用者.character_name }}
                      </button>
                    </td>
                    <td>{{ (使用者.servers || []).join(" / ") || "-" }}</td>
                    <td class="數字">{{ 格式化整數(使用者.encounter_count) }}</td>
                    <td class="數字">{{ 格式化整數(使用者.public_entry_count) }}</td>
                    <td class="數字">{{ 格式化傷害數值(使用者.best_rdps) }}</td>
                    <td>{{ 格式化紀錄時間(使用者.last_recorded_at_iso) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </section>
    </template>
    <template v-else-if="頁面模式 === 'user'">
      <section class="使用者搜尋區" aria-label="個人成績單查詢">
        <form class="使用者搜尋表單" @submit.prevent="提交使用者搜尋">
          <label class="欄位 使用者搜尋欄位">
            <span>角色 / 伺服器</span>
            <input
              v-model="使用者搜尋關鍵字"
              type="search"
              list="使用者搜尋建議"
              placeholder="輸入角色名稱，或選擇「角色 @ 伺服器」"
            />
            <datalist id="使用者搜尋建議">
              <option v-for="建議 in 使用者搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
                {{ 建議.label }}
              </option>
            </datalist>
          </label>

          <button type="submit">查詢</button>
        </form>
      </section>

      <section class="個人成績區" aria-live="polite">
        <div v-if="使用者讀取中" class="狀態列">讀取個人成績單中</div>
        <div v-else-if="使用者錯誤訊息" class="狀態列 錯誤">{{ 使用者錯誤訊息 }}</div>
        <div v-else-if="!使用者資料" class="狀態列">輸入角色名稱後即可查看個人成績單</div>
        <div v-else-if="使用者副本成績.length === 0" class="狀態列">目前沒有符合伺服器的公開成績</div>

        <template v-else>
          <section class="個人成績概要" aria-label="個人成績概要">
            <div class="概要項">
              <span>副本數</span>
              <strong>{{ 使用者統計.副本數 }}</strong>
            </div>
            <div class="概要項">
              <span>公開成績</span>
              <strong>{{ 使用者統計.公開成績數 }}</strong>
            </div>
            <div class="概要項">
              <span class="說明標籤">
                <span>最佳 rDPS</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="最佳 rDPS 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("最佳 rDPS") }}</span>
                </span>
              </span>
              <strong>{{ 格式化傷害數值(使用者統計.最佳成績?.rdps) }}</strong>
            </div>
            <div class="概要項">
              <span>最後紀錄</span>
              <strong>{{ 格式化紀錄時間(使用者統計.最後紀錄時間) }}</strong>
            </div>
          </section>

          <section v-if="使用者徽章.length > 0" class="使用者徽章區" aria-label="個人徽章">
            <article v-for="徽章 in 使用者徽章" :key="徽章.名稱" class="使用者徽章">
              <strong>{{ 徽章.名稱 }}</strong>
              <span>{{ 徽章.說明 }}</span>
            </article>
          </section>

          <section v-if="使用者成績趨勢.length > 0" class="成績趨勢區" aria-label="成績趨勢">
            <header class="成績趨勢標題">
              <h2>成績趨勢</h2>
              <span>公開 rDPS 歷史</span>
            </header>
            <div class="成績趨勢列表">
              <article v-for="趨勢 in 使用者成績趨勢" :key="趨勢.encounter_key" class="趨勢項">
                <header class="趨勢項標題">
                  <span>
                    <small>{{ 趨勢.encounter_category || "副本" }}</small>
                    <strong>{{ 趨勢.encounter_name }}</strong>
                  </span>
                  <em :class="{ 上升: 趨勢.變化 > 0, 下降: 趨勢.變化 < 0 }">{{ 格式化帶號整數(趨勢.變化) }}</em>
                </header>
                <div class="趨勢摘要">
                  <span>最新 {{ 格式化傷害數值(趨勢.最新?.rdps) }}</span>
                  <span>最佳 {{ 格式化傷害數值(趨勢.最佳?.rdps) }}</span>
                  <span>{{ 趨勢.點列表.length }} 筆</span>
                </div>
                <div class="趨勢圖" role="img" :aria-label="`${趨勢.encounter_name} rDPS 趨勢`">
                  <svg class="趨勢曲線圖" viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                    <line class="趨勢格線" x1="0" y1="10" x2="100" y2="10"></line>
                    <line class="趨勢格線" x1="0" y1="26" x2="100" y2="26"></line>
                    <line class="趨勢格線" x1="0" y1="42" x2="100" y2="42"></line>
                    <path v-if="趨勢.填色路徑" class="趨勢面積" :d="趨勢.填色路徑"></path>
                    <path v-if="趨勢.折線路徑" class="趨勢折線" :d="趨勢.折線路徑"></path>
                  </svg>
                  <span class="趨勢點層" aria-hidden="true">
                    <span
                      v-for="點 in 趨勢.點列表"
                      :key="點.id"
                      class="趨勢點"
                      :style="趨勢點樣式(點)"
                      :title="`${格式化紀錄時間(點.recorded_at_iso)}・rDPS ${格式化傷害數值(點.rdps)}`"
                    ></span>
                  </span>
                  <div class="趨勢刻度" aria-hidden="true">
                    <span>{{ 格式化傷害數值(趨勢.最高) }}</span>
                    <span>{{ 格式化傷害數值(趨勢.最低) }}</span>
                  </div>
                </div>
              </article>
            </div>
          </section>

          <section v-if="使用者隊友列表.length > 0" class="隊友關係區" aria-label="隊友關係">
            <header class="隊友關係標題">
              <h2 class="說明標籤">
                <span>隊友關係</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="隊友關係說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("隊友關係") }}</span>
                </span>
              </h2>
              <span>{{ 使用者隊友列表.length }} 位公開同場角色</span>
            </header>

            <div class="隊友關係版面">
              <article class="常同場隊友卡">
                <header class="隊友子面板標題">
                  <h3>常同場隊友</h3>
                  <span>前 {{ 常見隊友.length }} 位</span>
                </header>
                <div class="常同場隊友列表">
                  <button
                    v-for="隊友 in 常見隊友"
                    :key="`${隊友.character_name}@${隊友.server}`"
                    class="常同場隊友項"
                    type="button"
                    @click="開啟隊友成績單(隊友)"
                  >
                    <span class="常同場隊友主列">
                      <strong>{{ 隊友.character_name }}</strong>
                      <em>{{ 隊友.同場次數 }} 場</em>
                    </span>
                    <span class="隊友強度條" aria-hidden="true">
                      <span :style="比例條樣式(隊友.強度)"></span>
                    </span>
                    <span class="常同場隊友資訊">
                      <small>{{ 隊友.server }}</small>
                      <small>{{ 隊友.職業文字 || "多職業" }}</small>
                      <small v-if="隊友.副本文字">{{ 隊友.副本文字 }}</small>
                    </span>
                  </button>
                </div>
              </article>

              <article class="隊友洞察卡">
                <header class="隊友子面板標題">
                  <h3>關係輪廓</h3>
                  <span>{{ 隊友關係摘要.關係型態 }}</span>
                </header>
                <div class="隊友摘要格">
                  <div class="隊友摘要項">
                    <small>同場紀錄</small>
                    <strong>{{ 格式化整數(隊友關係摘要.總同場次數) }}</strong>
                    <em>{{ 使用者隊友列表.length }} 位角色</em>
                  </div>
                  <div class="隊友摘要項">
                    <small>重複同場</small>
                    <strong>{{ 格式化整數(隊友關係摘要.高頻隊友數) }}</strong>
                    <em>2 場以上</em>
                  </div>
                  <div class="隊友摘要項">
                    <small>主要聚集</small>
                    <strong>{{ 隊友關係摘要.主要副本?.encounter_name || "-" }}</strong>
                    <em v-if="隊友關係摘要.主要副本">
                      {{ 格式化整數(隊友關係摘要.主要副本.teammate_count) }} 位隊友
                    </em>
                    <em v-else>-</em>
                  </div>
                  <div class="隊友摘要項">
                    <small>最近同場</small>
                    <strong>{{ 格式化紀錄時間(隊友關係摘要.最近同場時間) }}</strong>
                    <em>{{ 格式化整數(隊友關係摘要.伺服器數) }} 伺服器</em>
                  </div>
                </div>
                <p class="隊友洞察文字">{{ 隊友關係摘要.說明 }}</p>
                <div v-if="隊友職能分布.length > 0" class="隊友職能分布">
                  <div v-for="職能 in 隊友職能分布" :key="職能.代碼" class="隊友職能項">
                    <span class="隊友職能名稱">
                      <img
                        v-if="職業類型Icon路徑(職能.代碼)"
                        class="職業圖示"
                        :src="職業類型Icon路徑(職能.代碼)"
                        :alt="職能.名稱"
                        loading="lazy"
                        @error="隱藏載入失敗圖片"
                      />
                      <strong>{{ 職能.名稱 }}</strong>
                    </span>
                    <em>{{ 格式化整數(職能.人數) }} 位</em>
                    <span class="分布條" aria-hidden="true">
                      <span
                        class="分布條填滿"
                        :class="職業色彩類別(職能.色彩)"
                        :style="比例條樣式(職能.強度)"
                      ></span>
                    </span>
                  </div>
                </div>
              </article>
            </div>

            <div v-if="隊友副本交集.length > 0" class="隊友副本區">
              <header class="隊友副本標題">
                <h3>同場副本聚集</h3>
                <span>以所有隊友的副本交集彙整</span>
              </header>
              <div class="隊友副本交集">
                <article v-for="副本 in 隊友副本交集" :key="副本.encounter_key" class="隊友副本項">
                  <div class="分布列">
                    <strong>{{ 副本.encounter_name }}</strong>
                    <span>{{ 格式化整數(副本.co_clear_count) }} 場・{{ 格式化整數(副本.teammate_count) }} 位隊友</span>
                  </div>
                  <div class="分布條" aria-hidden="true">
                    <span class="分布條填滿" :style="比例條樣式(副本.強度)"></span>
                  </div>
                </article>
              </div>
            </div>
          </section>

          <section class="個人成績列表" aria-label="各副本成績">
            <details v-for="副本 in 使用者副本成績" :key="副本.encounter_key" class="個人成績列">
              <summary class="成績列摘要">
                <span class="成績列副本">
                  <small>{{ 副本.encounter_category || "副本" }}</small>
                  <strong>{{ 副本.encounter_name }}</strong>
                </span>
                <span class="職業標籤 成績列職業" :class="職業色彩類別(職業代碼色彩(副本.best_entry.job))">
                  <img
                    v-if="職業Icon路徑(副本.best_entry.job)"
                    class="職業圖示 職業標籤圖示"
                    :src="職業Icon路徑(副本.best_entry.job)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                  <span>{{ 顯示職業名稱(副本.best_entry.job) }}</span>
                </span>
                <span class="成績列數值">
                  <small>職業 Rank</small>
                  <strong>{{ 格式化排名(副本.best_entry.job_rank ?? 副本.best_entry.rank) }}</strong>
                  <em>{{ 格式化前段百分位(副本.best_entry.job_rank ?? 副本.best_entry.rank, 取得成績職業總數(副本.best_entry)) }}</em>
                </span>
                <span class="成績列數值">
                  <small class="說明標籤">
                    <span>Active</span>
                    <span class="說明提示">
                      <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                      <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                    </span>
                  </small>
                  <strong>{{ 格式化Active(副本.best_entry.active_percent) }}</strong>
                </span>
                <span class="成績列數值">
                  <small class="說明標籤">
                    <span>DPS</span>
                    <span class="說明提示">
                      <button class="說明提示按鈕" type="button" aria-label="DPS 說明">?</button>
                      <span class="說明提示內容" role="tooltip">{{ 統計說明文字("DPS") }}</span>
                    </span>
                  </small>
                  <strong>{{ 格式化傷害數值(副本.best_entry.dps) }}</strong>
                </span>
                <span class="成績列數值">
                  <small class="說明標籤">
                    <span>rDPS</span>
                    <span class="說明提示">
                      <button class="說明提示按鈕" type="button" aria-label="rDPS 說明">?</button>
                      <span class="說明提示內容" role="tooltip">{{ 統計說明文字("rDPS") }}</span>
                    </span>
                  </small>
                  <strong>{{ 格式化傷害數值(副本.best_entry.rdps) }}</strong>
                </span>
                <span class="成績列數值">
                  <small class="說明標籤">
                    <span>aDPS</span>
                    <span class="說明提示">
                      <button class="說明提示按鈕" type="button" aria-label="aDPS 說明">?</button>
                      <span class="說明提示內容" role="tooltip">{{ 統計說明文字("aDPS") }}</span>
                    </span>
                  </small>
                  <strong>{{ 格式化傷害數值(副本.best_entry.adps) }}</strong>
                </span>
                <span class="成績列展開">{{ 副本.public_entries.length }} 筆</span>
              </summary>

              <div class="歷史表格外框">
                <table class="歷史表格">
                  <thead>
                    <tr>
                      <th scope="col">紀錄時間</th>
                      <th scope="col">職業</th>
                      <th scope="col" class="數字">
                        <span class="表頭說明標籤">
                          <span>Active</span>
                          <span class="說明提示">
                            <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                            <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                          </span>
                        </span>
                      </th>
                      <th scope="col" class="數字">
                        <span class="表頭說明標籤">
                          <span>DPS</span>
                          <span class="說明提示">
                            <button class="說明提示按鈕" type="button" aria-label="DPS 說明">?</button>
                            <span class="說明提示內容" role="tooltip">{{ 統計說明文字("DPS") }}</span>
                          </span>
                        </span>
                      </th>
                      <th scope="col" class="數字">
                        <span class="表頭說明標籤">
                          <span>rDPS</span>
                          <span class="說明提示">
                            <button class="說明提示按鈕" type="button" aria-label="rDPS 說明">?</button>
                            <span class="說明提示內容" role="tooltip">{{ 統計說明文字("rDPS") }}</span>
                          </span>
                        </span>
                      </th>
                      <th scope="col" class="數字">
                        <span class="表頭說明標籤">
                          <span>aDPS</span>
                          <span class="說明提示">
                            <button class="說明提示按鈕" type="button" aria-label="aDPS 說明">?</button>
                            <span class="說明提示內容" role="tooltip">{{ 統計說明文字("aDPS") }}</span>
                          </span>
                        </span>
                      </th>
                      <th scope="col" class="數字">通關時間</th>
                      <th scope="col">報告</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="成績 in 副本.public_entries" :key="成績.id">
                      <td>{{ 格式化紀錄時間(成績.recorded_at_iso) }}</td>
                      <td>
                        <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
                          <img
                            v-if="職業Icon路徑(成績.job)"
                            class="職業圖示 職業標籤圖示"
                            :src="職業Icon路徑(成績.job)"
                            alt=""
                            loading="lazy"
                            @error="隱藏載入失敗圖片"
                          />
                          <span>{{ 顯示職業名稱(成績.job) }}</span>
                        </span>
                      </td>
                      <td class="數字">{{ 格式化Active(成績.active_percent) }}</td>
                      <td class="數字">{{ 格式化傷害數值(成績.dps) }}</td>
                      <td class="數字">{{ 格式化傷害數值(成績.rdps) }}</td>
                      <td class="數字">{{ 格式化傷害數值(成績.adps) }}</td>
                      <td class="數字">{{ 格式化通關時間(成績.clear_time_seconds) }}</td>
                      <td>
                        <a v-if="成績.report_url" :href="成績.report_url" target="_blank" rel="noreferrer">FFLogs</a>
                        <span v-else>-</span>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </details>
          </section>
        </template>
      </section>
    </template>
    <template v-else-if="頁面模式 === 'compare'">
      <section class="使用者搜尋區" aria-label="角色比較查詢">
        <form class="使用者搜尋表單 比較搜尋表單" @submit.prevent="提交角色比較">
          <label class="欄位 使用者搜尋欄位">
            <span>角色 A</span>
            <input
              v-model="比較角色左輸入"
              type="search"
              list="比較角色左搜尋建議"
              placeholder="輸入角色名稱，或選擇「角色 @ 伺服器」"
            />
            <datalist id="比較角色左搜尋建議">
              <option v-for="建議 in 比較角色左搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
                {{ 建議.label }}
              </option>
            </datalist>
          </label>

          <label class="欄位 使用者搜尋欄位">
            <span>角色 B</span>
            <input
              v-model="比較角色右輸入"
              type="search"
              list="比較角色右搜尋建議"
              placeholder="輸入角色名稱，或選擇「角色 @ 伺服器」"
            />
            <datalist id="比較角色右搜尋建議">
              <option v-for="建議 in 比較角色右搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
                {{ 建議.label }}
              </option>
            </datalist>
          </label>

          <button type="submit">比較</button>
        </form>
      </section>

      <section class="角色比較區" aria-live="polite">
        <div v-if="比較讀取中" class="狀態列">讀取角色比較資料中</div>
        <div v-else-if="比較錯誤訊息" class="狀態列 錯誤">{{ 比較錯誤訊息 }}</div>
        <div v-else-if="!角色比較已完成" class="狀態列">輸入兩個角色後即可比較公開成績</div>

        <template v-else>
          <section class="角色比較概要" aria-label="角色比較概要">
            <article class="比較角色卡">
              <header>
                <span>角色 A</span>
                <strong>{{ 比較角色左.character_name }}</strong>
                <em>{{ 比較角色左.server }}</em>
              </header>
              <div class="比較角色數據">
                <span>副本數 <strong>{{ 比較角色左.統計.副本數 }}</strong></span>
                <span>公開成績 <strong>{{ 比較角色左.統計.公開成績數 }}</strong></span>
                <span>最佳 rDPS <strong>{{ 格式化傷害數值(比較角色左.統計.最佳成績?.rdps) }}</strong></span>
                <span>最後紀錄 <strong>{{ 格式化紀錄時間(比較角色左.統計.最後紀錄時間) }}</strong></span>
              </div>
            </article>

            <article class="比較角色卡">
              <header>
                <span>角色 B</span>
                <strong>{{ 比較角色右.character_name }}</strong>
                <em>{{ 比較角色右.server }}</em>
              </header>
              <div class="比較角色數據">
                <span>副本數 <strong>{{ 比較角色右.統計.副本數 }}</strong></span>
                <span>公開成績 <strong>{{ 比較角色右.統計.公開成績數 }}</strong></span>
                <span>最佳 rDPS <strong>{{ 格式化傷害數值(比較角色右.統計.最佳成績?.rdps) }}</strong></span>
                <span>最後紀錄 <strong>{{ 格式化紀錄時間(比較角色右.統計.最後紀錄時間) }}</strong></span>
              </div>
            </article>
          </section>

          <section class="統計面板 統計面板寬" aria-label="副本成績比較">
            <header class="統計面板標題">
              <h2>副本成績比較</h2>
              <span>{{ 比較角色左.character_name }}・{{ 比較角色右.character_name }}</span>
            </header>
            <div class="統計表格外框">
              <table class="統計表格 比較表格">
                <thead>
                  <tr>
                    <th scope="col">副本</th>
                    <th scope="col">{{ 比較角色左.character_name }}</th>
                    <th scope="col">{{ 比較角色右.character_name }}</th>
                    <th scope="col" class="數字">rDPS 差</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="列 in 角色比較列" :key="列.encounter_key">
                    <td>
                      <span class="比較副本">
                        <small>{{ 列.encounter_category || "副本" }}</small>
                        <strong>{{ 列.encounter_name }}</strong>
                      </span>
                    </td>
                    <td>
                      <div v-if="列.左" class="比較成績格">
                        <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.左.best_entry.job))">
                          <img
                            v-if="職業Icon路徑(列.左.best_entry.job)"
                            class="職業圖示 職業標籤圖示"
                            :src="職業Icon路徑(列.左.best_entry.job)"
                            alt=""
                            loading="lazy"
                            @error="隱藏載入失敗圖片"
                          />
                          <span>{{ 顯示職業名稱(列.左.best_entry.job) }}</span>
                        </span>
                        <strong>{{ 格式化傷害數值(列.左.best_entry.rdps) }}</strong>
                        <small>Active {{ 格式化Active(列.左.best_entry.active_percent) }}・{{ 格式化排名(列.左.best_entry.job_rank ?? 列.左.best_entry.rank) }}</small>
                      </div>
                      <span v-else>-</span>
                    </td>
                    <td>
                      <div v-if="列.右" class="比較成績格">
                        <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.右.best_entry.job))">
                          <img
                            v-if="職業Icon路徑(列.右.best_entry.job)"
                            class="職業圖示 職業標籤圖示"
                            :src="職業Icon路徑(列.右.best_entry.job)"
                            alt=""
                            loading="lazy"
                            @error="隱藏載入失敗圖片"
                          />
                          <span>{{ 顯示職業名稱(列.右.best_entry.job) }}</span>
                        </span>
                        <strong>{{ 格式化傷害數值(列.右.best_entry.rdps) }}</strong>
                        <small>Active {{ 格式化Active(列.右.best_entry.active_percent) }}・{{ 格式化排名(列.右.best_entry.job_rank ?? 列.右.best_entry.rank) }}</small>
                      </div>
                      <span v-else>-</span>
                    </td>
                    <td class="數字">
                      <span class="比較差異" :class="{ 左領先: 列.差異 > 0, 右領先: 列.差異 < 0 }">
                        {{ 列.差異 === null ? "-" : 格式化帶號整數(列.差異) }}
                      </span>
                    </td>
                  </tr>
                  <tr v-if="角色比較列.length === 0">
                    <td colspan="4" class="統計空列">兩個角色目前沒有可比較的共同資料</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </template>
      </section>
    </template>
  </main>
</template>

<style scoped>
:global(*) {
  box-sizing: border-box;
}

:global(:root) {
  color-scheme: dark;
  --頁面背景: #101214;
  --表面背景: #171b1f;
  --表面背景柔和: #20262c;
  --表頭背景: #232a32;
  --列hover背景: #1f262d;
  --主要文字: #f4f1ea;
  --次要文字: #b7b1a8;
  --靜音文字: #8d857a;
  --邊框色: #303842;
  --邊框柔和色: #272e36;
  --輸入背景: #12161a;
  --輸入邊框: #3d4854;
  --重點色: #d6a354;
  --重點色深: #b9853d;
  --重點文字: #1b1408;
  --錯誤文字: #ff8176;
  --停用背景: #252c2a;
  --停用文字: #7f877f;
  --焦點陰影: rgba(214, 163, 84, 0.26);
  --防護色: #68a8ff;
  --防護色深: #4f8ee0;
  --防護色柔和: rgba(104, 168, 255, 0.17);
  --防護焦點陰影: rgba(104, 168, 255, 0.26);
  --治療色: #55d98c;
  --治療色深: #3dbd72;
  --治療色柔和: rgba(85, 217, 140, 0.17);
  --治療焦點陰影: rgba(85, 217, 140, 0.26);
  --輸出色: #ff766f;
  --輸出色深: #d95d56;
  --輸出色柔和: rgba(255, 118, 111, 0.17);
  --輸出焦點陰影: rgba(255, 118, 111, 0.26);
  --職業重點文字: #0b1116;
  --第一名色: #f0c766;
  --第一名柔和: rgba(240, 199, 102, 0.18);
  --第二名色: #bfc8d6;
  --第二名柔和: rgba(191, 200, 214, 0.16);
  --第三名色: #d79765;
  --第三名柔和: rgba(215, 151, 101, 0.17);
}

:global(:root[data-theme="light"]) {
  color-scheme: light;
  --頁面背景: #f5f6f8;
  --表面背景: #ffffff;
  --表面背景柔和: #f0f3f7;
  --表頭背景: #eef2f7;
  --列hover背景: #f3f6fa;
  --主要文字: #1d2026;
  --次要文字: #5d6673;
  --靜音文字: #747d89;
  --邊框色: #d7dde6;
  --邊框柔和色: #e5eaf0;
  --輸入背景: #ffffff;
  --輸入邊框: #cbd3dd;
  --重點色: #9a620e;
  --重點色深: #80500d;
  --重點文字: #fffaf0;
  --錯誤文字: #a8332e;
  --停用背景: #edf1f5;
  --停用文字: #8a939e;
  --焦點陰影: rgba(154, 98, 14, 0.22);
  --防護色: #1f68c6;
  --防護色深: #18539e;
  --防護色柔和: rgba(31, 104, 198, 0.13);
  --防護焦點陰影: rgba(31, 104, 198, 0.2);
  --治療色: #267d48;
  --治療色深: #1d6338;
  --治療色柔和: rgba(38, 125, 72, 0.13);
  --治療焦點陰影: rgba(38, 125, 72, 0.2);
  --輸出色: #c6423d;
  --輸出色深: #9f332f;
  --輸出色柔和: rgba(198, 66, 61, 0.13);
  --輸出焦點陰影: rgba(198, 66, 61, 0.2);
  --職業重點文字: #ffffff;
  --第一名色: #9a690f;
  --第一名柔和: rgba(154, 105, 15, 0.14);
  --第二名色: #657284;
  --第二名柔和: rgba(101, 114, 132, 0.13);
  --第三名色: #9d5f30;
  --第三名柔和: rgba(157, 95, 48, 0.13);
}

:global(body) {
  margin: 0;
  min-width: 320px;
  min-height: 100vh;
  color: var(--主要文字);
  background: var(--頁面背景);
  font-family:
    Inter, "Noto Sans TC", "PingFang TC", "Microsoft JhengHei", system-ui, -apple-system, BlinkMacSystemFont,
    "Segoe UI", sans-serif;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
}

:global(a) {
  color: inherit;
}

.頁面 {
  width: min(1120px, calc(100% - 32px));
  margin: 0 auto;
  padding: 32px 0 48px;
}

.頁面[data-accent="tank"] {
  --重點色: var(--防護色);
  --重點色深: var(--防護色深);
  --重點文字: var(--職業重點文字);
  --焦點陰影: var(--防護焦點陰影);
}

.頁面[data-accent="healer"] {
  --重點色: var(--治療色);
  --重點色深: var(--治療色深);
  --重點文字: var(--職業重點文字);
  --焦點陰影: var(--治療焦點陰影);
}

.頁面[data-accent="dps"] {
  --重點色: var(--輸出色);
  --重點色深: var(--輸出色深);
  --重點文字: var(--職業重點文字);
  --焦點陰影: var(--輸出焦點陰影);
}

.標題區 {
  display: flex;
  align-items: end;
  justify-content: space-between;
  gap: 24px;
  margin-bottom: 24px;
  border-bottom: 1px solid var(--邊框色);
  padding-bottom: 20px;
}

.副標,
.更新時間 {
  margin: 0;
  color: var(--次要文字);
  font-size: 0.92rem;
}

h1 {
  margin: 6px 0 0;
  color: var(--主要文字);
  font-size: 2rem;
  font-weight: 760;
  line-height: 1.15;
  letter-spacing: 0;
}

.主題切換 {
  min-width: 94px;
}

.頁面切換 {
  display: flex;
  gap: 10px;
  margin-bottom: 18px;
}

.頁面切換 button {
  border-color: var(--輸入邊框);
  color: var(--次要文字);
  background: var(--輸入背景);
}

.頁面切換 button:hover:not(:disabled),
.頁面切換 button.作用中 {
  border-color: var(--重點色);
  color: var(--重點文字);
  background: var(--重點色);
}

.工具列 {
  display: grid;
  grid-template-columns:
    minmax(210px, 1.2fr) minmax(155px, 0.95fr) minmax(145px, 0.9fr) minmax(170px, 1fr)
    minmax(220px, 1.25fr);
  gap: 16px;
  margin-bottom: 18px;
}

.欄位 {
  display: grid;
  gap: 8px;
  color: var(--次要文字);
  font-size: 0.9rem;
  font-weight: 650;
}

select,
input {
  width: 100%;
  min-height: 42px;
  border: 1px solid var(--輸入邊框);
  border-radius: 8px;
  padding: 0 12px;
  color: var(--主要文字);
  background: var(--輸入背景);
  font: inherit;
}

select:focus,
input:focus {
  border-color: var(--重點色);
  outline: 3px solid var(--焦點陰影);
}

button {
  min-height: 38px;
  border: 1px solid var(--重點色);
  border-radius: 8px;
  padding: 0 14px;
  color: var(--重點文字);
  background: var(--重點色);
  font: inherit;
  font-weight: 720;
  cursor: pointer;
}

button:hover:not(:disabled) {
  background: var(--重點色深);
}

button:focus {
  outline: 3px solid var(--焦點陰影);
}

button:disabled {
  border-color: var(--邊框色);
  color: var(--停用文字);
  background: var(--停用背景);
  cursor: not-allowed;
}

.副本選單欄位 {
  position: relative;
}

.副本選單 {
  position: relative;
}

.副本選單按鈕 {
  width: 100%;
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-color: var(--輸入邊框);
  padding: 0 12px;
  color: var(--主要文字);
  background: var(--輸入背景);
  font-weight: 650;
  text-align: left;
}

.副本選單按鈕:hover:not(:disabled) {
  border-color: var(--重點色);
  background: var(--表面背景柔和);
}

.副本選單目前值 {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.副本選單面板 {
  position: absolute;
  z-index: 24;
  top: calc(100% + 8px);
  left: 0;
  width: min(380px, calc(100vw - 32px));
  max-height: min(560px, calc(100vh - 180px));
  overflow-y: auto;
  display: grid;
  gap: 10px;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  padding: 10px;
  background: var(--表面背景);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
}

.副本分類群 {
  display: grid;
  gap: 6px;
}

.副本分類標題 {
  margin: 0;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 2px 4px 7px;
  color: var(--靜音文字);
  font-size: 0.78rem;
  font-weight: 780;
}

.副本選單項 {
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  border-color: transparent;
  padding: 7px 10px;
  color: var(--次要文字);
  background: transparent;
  font-weight: 680;
  line-height: 1.35;
  text-align: left;
}

.副本選單項:hover:not(:disabled) {
  color: var(--主要文字);
  background: var(--表面背景柔和);
}

.副本選單項.已選取,
.副本選單項.已選取:hover:not(:disabled) {
  color: var(--重點文字);
  background: var(--重點色);
}

.職業選單欄位 {
  position: relative;
}

.職業選單 {
  position: relative;
}

.職業選單按鈕 {
  width: 100%;
  min-height: 42px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  border-color: var(--輸入邊框);
  padding: 0 12px;
  color: var(--主要文字);
  background: var(--輸入背景);
  font-weight: 650;
  text-align: left;
}

.職業選單按鈕:hover:not(:disabled) {
  border-color: var(--重點色);
  background: var(--表面背景柔和);
}

.職業選單目前值 {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.職業選單目前值 span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.選單箭頭 {
  flex: 0 0 auto;
  color: var(--次要文字);
  font-size: 0.86rem;
}

.職業選單面板 {
  position: absolute;
  z-index: 20;
  top: calc(100% + 8px);
  left: 0;
  width: min(520px, calc(100vw - 32px));
  display: grid;
  grid-template-columns: minmax(150px, 0.9fr) minmax(170px, 1fr);
  gap: 8px;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  padding: 8px;
  background: var(--表面背景);
  box-shadow: 0 18px 42px rgba(0, 0, 0, 0.28);
}

.職業選單分類欄,
.職業選單職業欄 {
  display: grid;
  align-content: start;
  gap: 6px;
}

.職業選單職業欄 {
  border-left: 1px solid var(--邊框柔和色);
  padding-left: 8px;
}

.職業選單項 {
  min-height: 36px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 8px;
  border-color: transparent;
  padding: 0 10px;
  color: var(--次要文字);
  background: transparent;
  font-weight: 680;
  text-align: left;
}

.職業圖示 {
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  object-fit: contain;
}

.職業選單項:hover:not(:disabled) {
  color: var(--主要文字);
  background: var(--表面背景柔和);
}

.職業選單項.防護色 {
  border-left: 3px solid var(--防護色);
  color: var(--防護色);
}

.職業選單項.治療色 {
  border-left: 3px solid var(--治療色);
  color: var(--治療色);
}

.職業選單項.輸出色 {
  border-left: 3px solid var(--輸出色);
  color: var(--輸出色);
}

.職業選單項.防護色:hover:not(:disabled) {
  background: var(--防護色柔和);
}

.職業選單項.治療色:hover:not(:disabled) {
  background: var(--治療色柔和);
}

.職業選單項.輸出色:hover:not(:disabled) {
  background: var(--輸出色柔和);
}

.職業選單項.已選取,
.職業選單項.已選取:hover:not(:disabled) {
  color: var(--重點文字);
  background: var(--重點色);
}

.職業選單項.防護色.已選取,
.職業選單項.防護色.已選取:hover:not(:disabled) {
  color: var(--職業重點文字);
  background: var(--防護色);
}

.職業選單項.治療色.已選取,
.職業選單項.治療色.已選取:hover:not(:disabled) {
  color: var(--職業重點文字);
  background: var(--治療色);
}

.職業選單項.輸出色.已選取,
.職業選單項.輸出色.已選取:hover:not(:disabled) {
  color: var(--職業重點文字);
  background: var(--輸出色);
}

.職業標籤 {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 26px;
  border-radius: 999px;
  padding: 0 10px;
  font-size: 0.88rem;
  font-weight: 760;
}

.職業標籤圖示 {
  width: 18px;
  height: 18px;
}

.職業標籤.防護色 {
  color: var(--防護色);
  background: var(--防護色柔和);
}

.職業標籤.治療色 {
  color: var(--治療色);
  background: var(--治療色柔和);
}

.職業標籤.輸出色 {
  color: var(--輸出色);
  background: var(--輸出色柔和);
}

.表格區 {
  overflow-x: auto;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  padding-top: 2px;
  background: var(--表面背景);
}

.使用者搜尋區 {
  margin-bottom: 18px;
}

.使用者搜尋表單 {
  display: grid;
  grid-template-columns: minmax(280px, 1fr) auto;
  align-items: end;
  gap: 16px;
}

.比較搜尋表單 {
  grid-template-columns: minmax(220px, 1fr) minmax(220px, 1fr) auto;
}

.使用者搜尋欄位 input {
  min-width: 0;
}

.統計工具列 {
  display: grid;
  grid-template-columns: minmax(220px, 1.2fr) minmax(150px, 0.8fr) minmax(220px, 1.1fr) minmax(170px, 0.8fr);
  gap: 16px;
  margin-bottom: 18px;
}

.職業分析工具列 {
  display: grid;
  grid-template-columns: minmax(220px, 360px);
  gap: 16px;
  margin-bottom: 18px;
}

.職業分析區 {
  display: grid;
  gap: 16px;
}

.職業焦點卡 {
  overflow: hidden;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--表面背景);
}

.職業焦點標題 {
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 14px;
}

.職業焦點圖示 {
  width: 54px;
  height: 54px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--表面背景柔和);
}

.職業焦點圖示.防護色 {
  background: var(--防護色柔和);
}

.職業焦點圖示.治療色 {
  background: var(--治療色柔和);
}

.職業焦點圖示.輸出色 {
  background: var(--輸出色柔和);
}

.職業焦點圖示 img {
  width: 38px;
  height: 38px;
  object-fit: contain;
}

.職業焦點標題 span:last-child {
  min-width: 0;
  display: grid;
  gap: 4px;
}

.職業焦點標題 small,
.職業分析補充 {
  color: var(--次要文字);
  font-size: 0.8rem;
  font-weight: 720;
}

.職業焦點標題 strong {
  color: var(--主要文字);
  font-size: 1.22rem;
  font-weight: 850;
}

.職業分析概要 {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.職業分析補充 {
  display: block;
}

.近期動態區 {
  display: grid;
  gap: 16px;
}

.近期動態表格 {
  min-width: 900px;
}

.全服統計區 {
  display: grid;
  gap: 16px;
}

.統計概要 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: visible;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--邊框柔和色);
}

.統計版面 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.統計面板 {
  overflow: visible;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--表面背景);
}

.統計面板寬 {
  width: 100%;
}

.統計面板標題 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 12px 14px;
}

.統計面板標題 h2 {
  margin: 0;
  color: var(--主要文字);
  font-size: 1rem;
  font-weight: 820;
}

.統計面板標題 span {
  min-width: 0;
  overflow: hidden;
  color: var(--次要文字);
  font-size: 0.82rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.零式漏斗列表 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.零式漏斗項 {
  min-width: 0;
  display: grid;
  align-content: start;
  gap: 12px;
  padding: 14px;
  background: var(--表面背景);
}

.漏斗副本列,
.漏斗數值列,
.漏斗補充列 {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.漏斗副本列 {
  align-items: flex-start;
}

.漏斗層級 {
  flex: 0 0 auto;
  border: 1px solid var(--邊框柔和色);
  border-radius: 999px;
  padding: 3px 8px;
  color: var(--重點色);
  background: var(--表面背景柔和);
  font-size: 0.76rem;
  font-weight: 850;
  line-height: 1.2;
}

.漏斗副本列 strong {
  min-width: 0;
  color: var(--主要文字);
  font-size: 0.9rem;
  font-weight: 800;
  line-height: 1.35;
  text-align: right;
}

.漏斗數值列 strong {
  min-width: 0;
  color: var(--主要文字);
  font-size: 1.16rem;
  font-weight: 840;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

.漏斗數值列 span,
.漏斗補充列 span {
  flex: 0 0 auto;
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.漏斗條 {
  height: 10px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--表面背景柔和);
}

.漏斗條 span {
  display: block;
  width: 0;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, var(--重點色), var(--防護色));
}

.分布列表 {
  display: grid;
  gap: 1px;
  background: var(--邊框柔和色);
}

.分布項 {
  display: grid;
  gap: 8px;
  padding: 11px 14px;
  background: var(--表面背景);
}

.分布列 {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.分布列 strong,
.分布列 span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.分布列 strong {
  color: var(--主要文字);
  font-size: 0.92rem;
  font-weight: 800;
}

.分布列 span {
  color: var(--次要文字);
  font-size: 0.82rem;
  font-weight: 700;
  font-variant-numeric: tabular-nums;
}

.分布職業 {
  display: inline-flex;
  align-items: center;
  gap: 7px;
}

.分布條 {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--表面背景柔和);
}

.分布條填滿 {
  display: block;
  width: 0;
  height: 100%;
  border-radius: inherit;
  background: var(--重點色);
}

.分布條填滿.防護色 {
  background: var(--防護色);
}

.分布條填滿.治療色 {
  background: var(--治療色);
}

.分布條填滿.輸出色 {
  background: var(--輸出色);
}

.分布子列表 {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.分布子項 {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  border: 1px solid var(--邊框柔和色);
  border-radius: 999px;
  padding: 4px 8px;
  color: var(--次要文字);
  background: var(--表面背景柔和);
  font-size: 0.76rem;
  font-weight: 740;
}

.分布子項.防護色 {
  border-color: var(--防護色);
  color: var(--防護色);
  background: var(--防護色柔和);
}

.分布子項.治療色 {
  border-color: var(--治療色);
  color: var(--治療色);
  background: var(--治療色柔和);
}

.分布子項.輸出色 {
  border-color: var(--輸出色);
  color: var(--輸出色);
  background: var(--輸出色柔和);
}

.分布子項 span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.分布子項 em {
  color: inherit;
  font-style: normal;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.分布子項 .職業圖示 {
  width: 16px;
  height: 16px;
}

.職業佔比分組 {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  align-items: start;
  gap: 10px;
  padding: 12px;
  background: var(--表面背景);
}

.職業佔比群組 {
  min-width: 0;
  align-self: start;
  display: grid;
  gap: 10px;
  border: 1px solid var(--邊框柔和色);
  border-radius: 8px;
  padding: 11px 12px;
  background: var(--表面背景);
}

.職業佔比群組.防護色 {
  border-color: rgba(104, 168, 255, 0.42);
  background: linear-gradient(180deg, var(--防護色柔和), var(--表面背景) 54px);
}

.職業佔比群組.治療色 {
  border-color: rgba(85, 217, 140, 0.42);
  background: linear-gradient(180deg, var(--治療色柔和), var(--表面背景) 54px);
}

.職業佔比群組.輸出色 {
  border-color: rgba(255, 118, 111, 0.38);
  background: linear-gradient(180deg, var(--輸出色柔和), var(--表面背景) 54px);
}

.職業佔比群組標題 {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.職業佔比群組標題 strong,
.職業佔比群組標題 span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.職業佔比群組標題 strong {
  color: var(--主要文字);
  font-size: 0.92rem;
  font-weight: 820;
}

.職業佔比群組標題 span {
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
}

.職業佔比職業列表 {
  display: grid;
  gap: 7px;
}

.職業佔比職業 {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  align-items: center;
  gap: 8px;
  color: var(--次要文字);
  font-size: 0.8rem;
  font-weight: 700;
}

.職業佔比職業 .分布職業 {
  min-width: 0;
}

.職業佔比職業 .分布職業 span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.職業佔比職業 strong {
  color: var(--主要文字);
  font-size: 0.84rem;
  font-variant-numeric: tabular-nums;
}

.職業佔比職業 small {
  color: var(--靜音文字);
  font-size: 0.76rem;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.生態矩陣外框 {
  overflow-x: auto;
  padding-top: 2px;
}

.生態矩陣 {
  width: 100%;
  min-width: 880px;
}

.生態矩陣 th,
.生態矩陣 td {
  padding: 10px 12px;
}

.生態矩陣 thead th {
  text-align: center;
}

.生態矩陣 td {
  text-align: center;
}

.熱力格 {
  --熱力色: var(--重點色);
  min-height: 54px;
  display: grid;
  align-content: center;
  gap: 2px;
  border: 1px solid color-mix(in srgb, var(--熱力色) 34%, var(--邊框柔和色));
  border-radius: 8px;
  padding: 8px;
  background: color-mix(in srgb, var(--熱力色) var(--熱度), var(--表面背景));
}

.熱力格.防護色 {
  --熱力色: var(--防護色);
}

.熱力格.治療色 {
  --熱力色: var(--治療色);
}

.熱力格.輸出色 {
  --熱力色: var(--輸出色);
}

.熱力格 strong {
  color: var(--主要文字);
  font-size: 0.88rem;
  font-weight: 840;
  font-variant-numeric: tabular-nums;
}

.熱力格 small {
  color: var(--次要文字);
  font-size: 0.72rem;
  font-weight: 720;
  font-variant-numeric: tabular-nums;
}

.資料狀態分組列表 {
  display: grid;
  gap: 12px;
  padding: 12px;
  background: var(--表面背景柔和);
}

.資料狀態分組 {
  overflow: hidden;
  border: 1px solid var(--邊框柔和色);
  border-radius: 8px;
  background: var(--表面背景);
}

.資料狀態分組標題 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 14px 10px;
}

.資料狀態分組標題 span {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.資料狀態分組標題 strong {
  color: var(--主要文字);
  font-size: 0.98rem;
  font-weight: 840;
}

.資料狀態分組標題 small {
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 720;
}

.資料狀態分組標題 em {
  flex: 0 0 auto;
  color: var(--重點色);
  font-size: 0.82rem;
  font-style: normal;
  font-weight: 850;
  font-variant-numeric: tabular-nums;
}

.資料狀態分組 > .分布條 {
  margin: 0 14px 12px;
}

.資料狀態列表 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  border-top: 1px solid var(--邊框柔和色);
  background: var(--邊框柔和色);
}

.資料狀態項 {
  min-width: 0;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 4px 10px;
  padding: 12px 14px;
  background: var(--表面背景);
}

.資料狀態項 span {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.資料狀態項 small,
.資料狀態項 strong {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.資料狀態項 small {
  color: var(--次要文字);
  font-size: 0.76rem;
  font-weight: 700;
}

.資料狀態項 strong {
  color: var(--主要文字);
  font-size: 0.9rem;
  font-weight: 810;
}

.資料狀態項 > small {
  grid-column: 1 / -1;
}

.資料狀態項 em {
  border-radius: 999px;
  padding: 4px 8px;
  color: var(--次要文字);
  background: var(--表面背景柔和);
  font-size: 0.74rem;
  font-style: normal;
  font-weight: 820;
  white-space: nowrap;
}

.資料狀態項.已收錄 em {
  color: var(--職業重點文字);
  background: var(--治療色);
}

.統計表格外框 {
  overflow-x: auto;
  padding-top: 2px;
}

.統計表格 {
  min-width: 860px;
}

.比較表格 {
  min-width: 940px;
}

.統計表格 th,
.統計表格 td {
  padding: 12px 14px;
}

.比較副本,
.比較成績格 {
  min-width: 0;
  display: grid;
  gap: 6px;
}

.比較副本 small,
.比較成績格 small {
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 700;
}

.比較副本 strong,
.比較成績格 strong {
  color: var(--主要文字);
  font-weight: 820;
}

.比較成績格 {
  justify-items: start;
}

.比較成績格 strong {
  font-size: 1.02rem;
  font-variant-numeric: tabular-nums;
}

.比較差異 {
  color: var(--次要文字);
  font-weight: 840;
  font-variant-numeric: tabular-nums;
}

.比較差異.左領先 {
  color: var(--治療色);
}

.比較差異.右領先 {
  color: var(--輸出色);
}

.統計空列 {
  color: var(--次要文字);
  text-align: center;
}

.個人成績區 {
  display: grid;
  gap: 16px;
  overflow: visible;
}

.角色比較區 {
  display: grid;
  gap: 16px;
  overflow: visible;
}

.角色比較概要 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.比較角色卡 {
  overflow: hidden;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--表面背景);
}

.比較角色卡 header {
  display: grid;
  gap: 3px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 13px 14px;
}

.比較角色卡 header span,
.比較角色卡 header em {
  color: var(--次要文字);
  font-size: 0.82rem;
  font-style: normal;
  font-weight: 720;
}

.比較角色卡 header strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--主要文字);
  font-size: 1.12rem;
  font-weight: 840;
}

.比較角色數據 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.比較角色數據 span {
  min-width: 0;
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  color: var(--次要文字);
  background: var(--表面背景);
  font-size: 0.8rem;
  font-weight: 720;
}

.比較角色數據 strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--主要文字);
  font-size: 0.96rem;
  font-weight: 820;
  font-variant-numeric: tabular-nums;
}

.成績趨勢區 {
  overflow: hidden;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--表面背景);
}

.成績趨勢標題 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 12px 14px;
}

.成績趨勢標題 h2 {
  margin: 0;
  color: var(--主要文字);
  font-size: 1rem;
  font-weight: 820;
}

.成績趨勢標題 span {
  color: var(--次要文字);
  font-size: 0.82rem;
  font-weight: 700;
}

.成績趨勢列表 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.使用者徽章區 {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.使用者徽章 {
  min-width: min(230px, 100%);
  display: grid;
  gap: 3px;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  padding: 10px 12px;
  background: var(--表面背景);
}

.使用者徽章 strong {
  color: var(--重點色);
  font-size: 0.9rem;
  font-weight: 840;
}

.使用者徽章 span {
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.35;
}

.趨勢項 {
  display: grid;
  gap: 12px;
  padding: 13px 14px;
  background: var(--表面背景);
}

.趨勢項標題 {
  min-width: 0;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.趨勢項標題 span {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.趨勢項標題 small,
.趨勢摘要 {
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 700;
}

.趨勢項標題 strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--主要文字);
  font-size: 0.94rem;
  font-weight: 820;
}

.趨勢項標題 em {
  flex: 0 0 auto;
  color: var(--次要文字);
  font-style: normal;
  font-size: 0.86rem;
  font-weight: 850;
  font-variant-numeric: tabular-nums;
}

.趨勢項標題 em.上升 {
  color: var(--治療色);
}

.趨勢項標題 em.下降 {
  color: var(--輸出色);
}

.趨勢摘要 {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  font-variant-numeric: tabular-nums;
}

.趨勢圖 {
  position: relative;
  height: 118px;
  overflow: hidden;
  border-radius: 8px;
  background: var(--表面背景柔和);
}

.趨勢曲線圖 {
  width: 100%;
  height: 100%;
  display: block;
}

.趨勢格線 {
  stroke: var(--邊框柔和色);
  stroke-width: 0.8;
}

.趨勢面積 {
  fill: color-mix(in srgb, var(--重點色) 18%, transparent);
}

.趨勢折線 {
  fill: none;
  stroke: var(--重點色);
  stroke-linecap: round;
  stroke-linejoin: round;
  stroke-width: 2.1;
  vector-effect: non-scaling-stroke;
}

.趨勢點層 {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.趨勢點 {
  position: absolute;
  width: 8px;
  height: 8px;
  transform: translate(-50%, -50%);
  border: 2px solid var(--重點色);
  border-radius: 999px;
  background: var(--表面背景);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--表面背景) 70%, transparent);
}

.趨勢刻度 {
  position: absolute;
  inset: 8px 10px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  pointer-events: none;
}

.趨勢刻度 span {
  align-self: flex-end;
  border-radius: 999px;
  padding: 2px 6px;
  color: var(--次要文字);
  background: color-mix(in srgb, var(--表面背景) 78%, transparent);
  font-size: 0.68rem;
  font-weight: 760;
  font-variant-numeric: tabular-nums;
}

.個人成績概要 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  overflow: visible;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--邊框柔和色);
}

.概要項 {
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  background: var(--表面背景);
}

.概要項 span {
  color: var(--次要文字);
  font-size: 0.84rem;
  font-weight: 700;
}

.說明標籤,
.表頭說明標籤 {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  vertical-align: middle;
}

.表頭說明標籤 {
  justify-content: flex-end;
}

.說明提示 {
  position: relative;
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  overflow: visible;
}

.說明提示按鈕 {
  width: 18px;
  min-width: 18px;
  height: 18px;
  min-height: 18px;
  border-radius: 999px;
  padding: 0;
  color: var(--重點色);
  background: var(--表面背景柔和);
  border-color: var(--邊框柔和色);
  font-size: 0.72rem;
  font-weight: 850;
  line-height: 1;
}

.說明提示按鈕:hover:not(:disabled),
.說明提示按鈕:focus {
  color: var(--重點文字);
  background: var(--重點色);
}

.說明提示內容 {
  position: absolute;
  z-index: 40;
  left: 50%;
  bottom: calc(100% + 8px);
  width: min(260px, calc(100vw - 40px));
  transform: translateX(-50%);
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  padding: 9px 10px;
  color: var(--主要文字);
  background: var(--表面背景);
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.28);
  font-size: 0.78rem;
  font-weight: 650;
  line-height: 1.45;
  text-align: left;
  white-space: normal;
  overflow: visible;
  text-overflow: clip;
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
}

.概要項 .說明提示,
.統計面板標題 .說明提示,
.成績列數值 .說明提示,
th .說明提示,
.概要項 .說明提示內容,
.統計面板標題 .說明提示內容,
.成績列數值 .說明提示內容,
th .說明提示內容 {
  color: var(--主要文字);
  font-size: 0.78rem;
  font-weight: 650;
  line-height: 1.45;
  overflow: visible;
  text-overflow: clip;
  white-space: normal;
}

.表格區 th .說明提示內容,
.歷史表格外框 th .說明提示內容,
.成績列數值 .說明提示內容,
.統計表格 th .說明提示內容 {
  top: calc(100% + 8px);
  bottom: auto;
}

.說明提示:hover .說明提示內容,
.說明提示:focus-within .說明提示內容 {
  opacity: 1;
  visibility: visible;
}

.概要項 strong {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--主要文字);
  font-size: 1.02rem;
  font-weight: 800;
  font-variant-numeric: tabular-nums;
}

.隊友關係區,
.常見隊友區 {
  overflow: hidden;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--表面背景);
}

.隊友關係標題,
.常見隊友標題 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 10px 14px;
}

.隊友關係標題 h2,
.常見隊友標題 h2 {
  margin: 0;
  color: var(--主要文字);
  font-size: 0.98rem;
  font-weight: 820;
}

.隊友關係標題 span,
.常見隊友標題 span {
  color: var(--次要文字);
  font-size: 0.82rem;
  font-weight: 700;
}

.隊友關係版面 {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(320px, 0.9fr);
  gap: 1px;
  background: var(--邊框柔和色);
}

.常同場隊友卡,
.隊友洞察卡 {
  display: grid;
  align-content: start;
  background: var(--表面背景);
}

.隊友子面板標題 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 13px 14px;
}

.隊友子面板標題 h3 {
  margin: 0;
  color: var(--主要文字);
  font-size: 0.96rem;
  font-weight: 830;
}

.隊友子面板標題 span {
  color: var(--次要文字);
  font-size: 0.8rem;
  font-weight: 720;
}

.常同場隊友列表 {
  display: grid;
}

.常同場隊友項 {
  min-height: 68px;
  display: grid;
  gap: 7px;
  border-width: 0 0 1px;
  border-color: var(--邊框柔和色);
  border-radius: 0;
  padding: 10px 14px;
  color: var(--主要文字);
  background: transparent;
  text-align: left;
}

.常同場隊友項:hover:not(:disabled) {
  background: var(--表面背景柔和);
}

.常同場隊友主列 {
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.常同場隊友主列 strong {
  min-width: 0;
  overflow: hidden;
  color: var(--主要文字);
  font-size: 0.92rem;
  font-weight: 820;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.常同場隊友主列 em {
  flex: 0 0 auto;
  color: var(--重點色);
  font-size: 0.8rem;
  font-style: normal;
  font-weight: 840;
  font-variant-numeric: tabular-nums;
}

.隊友強度條 {
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--表面背景柔和);
}

.隊友強度條 span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--重點色);
}

.常同場隊友資訊 {
  display: flex;
  flex-wrap: wrap;
  gap: 5px 10px;
}

.常同場隊友資訊 small {
  max-width: 100%;
  overflow: hidden;
  color: var(--次要文字);
  font-size: 0.76rem;
  font-weight: 700;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.隊友摘要格 {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.隊友摘要項 {
  min-width: 0;
  display: grid;
  gap: 4px;
  padding: 12px 14px;
  background: var(--表面背景);
}

.隊友摘要項 small,
.隊友摘要項 em {
  min-width: 0;
  overflow: hidden;
  color: var(--次要文字);
  font-size: 0.74rem;
  font-style: normal;
  font-weight: 720;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.隊友摘要項 strong {
  min-width: 0;
  overflow: hidden;
  color: var(--主要文字);
  font-size: 0.96rem;
  font-weight: 830;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.隊友洞察文字 {
  margin: 0;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 12px 14px;
  color: var(--次要文字);
  background: var(--表面背景柔和);
  font-size: 0.82rem;
  font-weight: 700;
  line-height: 1.55;
}

.隊友職能分布 {
  display: grid;
}

.隊友職能項 {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
  gap: 7px 12px;
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 10px 14px;
}

.隊友職能項 .分布條 {
  grid-column: 1 / -1;
}

.隊友職能名稱 {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.隊友職能名稱 strong {
  min-width: 0;
  overflow: hidden;
  color: var(--主要文字);
  font-size: 0.84rem;
  font-weight: 790;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.隊友職能項 em {
  flex: 0 0 auto;
  color: var(--次要文字);
  font-size: 0.76rem;
  font-style: normal;
  font-weight: 760;
  font-variant-numeric: tabular-nums;
}

.隊友副本區 {
  border-top: 1px solid var(--邊框柔和色);
}

.隊友副本標題 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
}

.隊友副本標題 h3 {
  margin: 0;
  color: var(--主要文字);
  font-size: 0.94rem;
  font-weight: 820;
}

.隊友副本標題 span {
  color: var(--次要文字);
  font-size: 0.8rem;
  font-weight: 720;
}

.隊友副本交集 {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.隊友副本項 {
  display: grid;
  gap: 8px;
  padding: 11px 14px;
  background: var(--表面背景);
}

.常見隊友列表 {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  background: var(--邊框柔和色);
}

.隊友項 {
  min-width: 0;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 3px 10px;
  padding: 10px 12px;
  background: var(--表面背景);
}

.隊友項 .隊友連結,
.隊友項 span,
.隊友項 small {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.隊友項 .隊友連結 {
  justify-self: start;
  max-width: 100%;
  font-size: 0.94rem;
  line-height: 1.25;
}

.隊友項 span,
.隊友項 small {
  color: var(--次要文字);
  font-size: 0.78rem;
  font-weight: 680;
}

.隊友項 .隊友副本 {
  grid-column: 1 / -1;
}

.隊友項 em {
  grid-column: 2;
  grid-row: 1 / span 2;
  align-self: center;
  border-radius: 999px;
  padding: 4px 8px;
  color: var(--重點文字);
  background: var(--重點色);
  font-size: 0.78rem;
  font-style: normal;
  font-weight: 820;
  white-space: nowrap;
}

.個人成績列表 {
  display: grid;
  gap: 8px;
  overflow: visible;
}

.個人成績列 {
  overflow: visible;
  border: 1px solid var(--邊框色);
  border-radius: 8px;
  background: var(--表面背景);
}

.個人成績列[open] {
  box-shadow: 0 14px 30px rgba(0, 0, 0, 0.1);
}

.成績列摘要 {
  min-height: 64px;
  display: grid;
  grid-template-columns:
    minmax(170px, 1.45fr) minmax(104px, 0.72fr) minmax(76px, 0.48fr) minmax(76px, 0.48fr)
    minmax(82px, 0.52fr) minmax(82px, 0.52fr) minmax(82px, 0.52fr) auto;
  align-items: center;
  gap: 12px;
  padding: 9px 14px;
  color: var(--次要文字);
  cursor: pointer;
  list-style: none;
}

.成績列摘要::-webkit-details-marker {
  display: none;
}

.成績列摘要:hover {
  background: var(--列hover背景);
}

.個人成績列[open] .成績列摘要 {
  border-bottom: 1px solid var(--邊框柔和色);
  background: var(--表面背景柔和);
}

.成績列副本,
.成績列數值 {
  min-width: 0;
  display: grid;
  gap: 3px;
}

.成績列副本 small,
.成績列數值 small,
.成績列數值 em {
  color: var(--靜音文字);
  font-size: 0.72rem;
  font-weight: 760;
}

.成績列數值 em {
  color: var(--重點色);
  font-style: normal;
}

.成績列副本 strong,
.成績列數值 strong {
  min-width: 0;
  overflow: hidden;
  color: var(--主要文字);
  font-size: 0.92rem;
  font-weight: 820;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.成績列副本 strong {
  font-size: 0.98rem;
}

.成績列職業 {
  justify-self: start;
}

.成績列展開 {
  justify-self: end;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--邊框柔和色);
  border-radius: 999px;
  padding: 6px 10px;
  color: var(--次要文字);
  background: var(--表面背景柔和);
  font-size: 0.82rem;
  font-weight: 760;
  white-space: nowrap;
}

.成績列展開::after {
  content: "展開";
  color: var(--重點色);
}

.個人成績列[open] .成績列展開::after {
  content: "收合";
}

.歷史表格外框 {
  overflow-x: auto;
  border-top: 1px solid var(--邊框柔和色);
  padding-top: 2px;
}

.歷史表格 {
  min-width: 980px;
}

.歷史表格 th,
.歷史表格 td {
  padding: 11px 14px;
}

.分頁資訊列 {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  min-width: 720px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--邊框柔和色);
  color: var(--次要文字);
}

.分頁資訊列底部 {
  border-top: 1px solid var(--邊框柔和色);
  border-bottom: 0;
}

.分頁資訊列 p {
  margin: 0;
  font-size: 0.92rem;
  font-weight: 650;
}

.分頁控制 {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
}

.分頁控制 label {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--次要文字);
  font-size: 0.9rem;
  font-weight: 650;
}

.分頁控制 input {
  width: 74px;
  min-height: 38px;
  text-align: center;
}

.頁數文字 {
  color: var(--次要文字);
  font-size: 0.92rem;
  font-weight: 680;
  white-space: nowrap;
}

table {
  width: 100%;
  min-width: 1120px;
  border-collapse: collapse;
}

th,
td {
  border-bottom: 1px solid var(--邊框柔和色);
  padding: 14px 16px;
  text-align: left;
  white-space: nowrap;
}

th {
  color: var(--重點色);
  background: var(--表頭背景);
  font-size: 0.84rem;
  font-weight: 760;
}

tbody tr:hover {
  background: var(--列hover背景);
}

tbody tr:last-child td {
  border-bottom: 0;
}

td a {
  color: var(--重點色);
  font-weight: 680;
  text-decoration: none;
}

td a:hover {
  text-decoration: underline;
}

.文字連結 {
  min-height: 0;
  border: 0;
  padding: 0;
  color: var(--重點色);
  background: transparent;
  font-weight: 760;
  text-align: left;
}

.文字連結:hover:not(:disabled) {
  color: var(--重點色深);
  background: transparent;
  text-decoration: underline;
}

.次要連結 {
  display: inline-block;
  margin-left: 10px;
  color: var(--次要文字);
  font-size: 0.82rem;
  font-weight: 680;
}

.排名 {
  color: var(--靜音文字);
  font-weight: 720;
}

.排名.第一名,
.排名.第二名,
.排名.第三名 {
  border-radius: 999px;
  font-weight: 820;
}

.排名.第一名 {
  color: var(--第一名色);
  background: var(--第一名柔和);
}

.排名.第二名 {
  color: var(--第二名色);
  background: var(--第二名柔和);
}

.排名.第三名 {
  color: var(--第三名色);
  background: var(--第三名柔和);
}

.數字 {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.狀態列 {
  padding: 32px 18px;
  color: var(--次要文字);
  text-align: center;
}

.錯誤 {
  color: var(--錯誤文字);
}

@media (max-width: 720px) {
  .頁面 {
    width: min(100% - 20px, 1120px);
    padding-top: 22px;
  }

  .標題區 {
    display: grid;
    gap: 10px;
    align-items: start;
  }

  h1 {
    font-size: 1.55rem;
  }

  .工具列 {
    grid-template-columns: 1fr;
  }

  .頁面切換,
  .使用者搜尋表單 {
    display: grid;
  }

  .使用者搜尋表單 {
    grid-template-columns: 1fr;
  }

  .個人成績概要 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .角色比較概要 {
    grid-template-columns: 1fr;
  }

  .比較角色數據 {
    grid-template-columns: 1fr;
  }

  .成績趨勢列表 {
    grid-template-columns: 1fr;
  }

  .資料狀態列表 {
    grid-template-columns: 1fr;
  }

  .資料狀態分組列表 {
    padding: 10px;
  }

  .資料狀態分組標題 {
    display: grid;
    gap: 6px;
  }

  .成績趨勢標題 {
    display: grid;
    gap: 4px;
  }

  .統計工具列 {
    grid-template-columns: 1fr;
  }

  .職業分析工具列,
  .職業分析概要 {
    grid-template-columns: 1fr;
  }

  .統計概要 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .統計版面 {
    grid-template-columns: 1fr;
  }

  .零式漏斗列表 {
    grid-template-columns: 1fr;
  }

  .漏斗副本列,
  .漏斗數值列,
  .漏斗補充列 {
    align-items: flex-start;
  }

  .漏斗副本列,
  .漏斗數值列 {
    display: grid;
    gap: 6px;
  }

  .漏斗副本列 strong {
    text-align: left;
  }

  .職業佔比分組 {
    grid-template-columns: 1fr;
    padding: 10px;
  }

  .統計面板標題 {
    display: grid;
    gap: 4px;
  }

  .隊友關係版面 {
    grid-template-columns: 1fr;
  }

  .隊友摘要格 {
    grid-template-columns: 1fr;
  }

  .隊友副本交集 {
    grid-template-columns: 1fr;
  }

  .常見隊友列表 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .隊友關係標題,
  .隊友子面板標題,
  .隊友副本標題,
  .常見隊友標題 {
    display: grid;
    gap: 4px;
  }

  .成績列摘要 {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 10px;
    padding: 12px;
  }

  .成績列副本,
  .成績列日期,
  .成績列展開 {
    grid-column: 1 / -1;
  }

  .成績列展開 {
    justify-self: start;
  }

  .分頁資訊列 {
    min-width: 0;
    display: grid;
    justify-items: start;
  }

  .分頁控制 {
    width: 100%;
    justify-content: space-between;
  }
}
</style>
