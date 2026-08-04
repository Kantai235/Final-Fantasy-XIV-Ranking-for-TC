import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { 可快取職業Icon路徑清單, 職業Icon路徑, 職業類型Icon路徑 } from "../src/domain/jobs.js";
import {
  取得主動公告列表,
  取得公告狀態,
  正規化公告資料,
  讀取已關閉公告,
  寫入已關閉公告,
  解析公告Markdown,
} from "../src/utils/announcements.js";
import { buildReportExternalLinks } from "../src/utils/reportLinks.js";
import { 預設副本鍵值 } from "../src/composables/rankingApp/defaults.js";
import { publicDataContracts, validateSchemaContract } from "../schemas/public_data_contracts.mjs";
import { 建立職業佔比分組, 取得統計範圍計數 } from "../src/utils/statsDisplay.js";
import {
  分位顯示模式PR,
  分位顯示模式前段,
  預設分位顯示模式,
  取得PR色彩類別,
  格式化同職分位,
  格式化排名分位,
  正規化分位顯示模式,
} from "../src/utils/formatters.js";
import {
  個人成績代表是否較佳,
  比較個人成績分位顯示排序,
} from "../src/utils/userProfileSorting.js";
import {
  建立個人成績徽章,
  六絕踏破稱號,
  建立零式量級踏破徽章,
} from "../src/utils/userProfileBadges.js";
import {
  建立個人成績趨勢版本切點,
  建立個人成績簡表群組,
  建立個人成績簡表可選版本,
  成績符合個人成績簡表版本,
  個人成績簡表版本已開放,
  個人成績簡表版本選項,
  預設個人成績簡表版本,
  取得個人成績紀錄版本,
  副本符合個人成績簡表版本,
  是個人成績簡表目標副本,
} from "../src/utils/userProfileClearSummary.js";
import {
  建立Fflogs即時狀態顯示,
  建立報告索引Map,
  建立未收錄提示,
  Fflogs目前公開可讀,
  Fflogs目前明確不可公開,
  取得Fflogs即時狀態查詢網址,
  取得下一輪排程時間,
  解析Fflogs網址,
} from "../src/utils/reportStatus.js";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(rootDir, "src");
const publicDataDir = path.join(rootDir, "public", "data");

const issues = [];

function reportIssue(message) {
  issues.push(message);
}

async function readText(filePath) {
  // Git 在 Windows 工作區可能保留 CRLF；靜態契約只驗證結構，不應因換行格式不同而誤判。
  return (await readFile(filePath, "utf8")).replace(/\r\n/g, "\n");
}

async function readJson(filePath, label) {
  try {
    return JSON.parse(await readText(filePath));
  } catch (error) {
    reportIssue(`${label} 不是可讀取的 JSON：${error.message}`);
    return null;
  }
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

function assert(condition, message) {
  if (!condition) {
    reportIssue(message);
  }
}

function 暫時固定現在時間(時間戳記, callback) {
  const 原始DateNow = Date.now;
  Date.now = () => 時間戳記;
  try {
    return callback();
  } finally {
    Date.now = 原始DateNow;
  }
}

function validatePercentileDisplayFormatting() {
  const performance = {
    qualified: true,
    active_threshold: 90,
    sample_count: 100,
    rank: 6,
    top_percent: 6,
    score_percentile: 95.4,
  };

  assert(預設分位顯示模式 === 分位顯示模式PR, "尚未設定分位偏好時應預設使用 PR 模式。");
  assert(正規化分位顯示模式(null) === 分位顯示模式PR, "缺少已儲存偏好時應回退至 PR 模式。");
  assert(正規化分位顯示模式(分位顯示模式前段) === 分位顯示模式前段, "既有前 N% 偏好應繼續保留。");
  assert(格式化同職分位(performance, 分位顯示模式前段) === "前 6.00%", "前 N% 模式應顯示 top_percent 到小數兩位。");
  assert(格式化同職分位(performance, 分位顯示模式PR) === "PR 95", "PR 模式應四捨五入為整數。");
  assert(格式化排名分位(1, 1, 分位顯示模式PR) === "PR 100", "排名分位 PR 應支援單筆樣本。");
  assert(格式化同職分位({ rank: 2, sample_count: 4 }, 分位顯示模式PR) === "PR 75", "缺少 score_percentile 時應由 rank/sample_count 回推 PR。");
  assert(格式化同職分位({ rank: null, sample_count: 10 }, 分位顯示模式PR) === "-", "缺少排名時不可把 null 誤判為 PR 0。");

  const expectedClasses = [
    [0, "分位PR0"],
    [24, "分位PR0"],
    [25, "分位PR25"],
    [49, "分位PR25"],
    [50, "分位PR50"],
    [74, "分位PR50"],
    [75, "分位PR75"],
    [94, "分位PR75"],
    [95, "分位PR95"],
    [98, "分位PR95"],
    [99, "分位PR99"],
    [100, "分位PR100"],
  ];

  for (const [score, className] of expectedClasses) {
    assert(取得PR色彩類別(score) === className, `PR ${score} 應套用 ${className} 色彩類別。`);
  }
}

function validateRankingDefaults() {
  assert(預設副本鍵值 === "savage_m5s", "排行榜目前必須預設顯示零式 M5S／熱舞綠光。");
}

function validateUserProfilePercentileSorting() {
  const rankAheadButLowerPr = {
    job: "Summoner",
    job_rank: 1,
    rank: 1,
    rdps: 1000,
    performance: {
      qualified: true,
      sample_count: 5,
      rank: 3,
      top_percent: 60,
      score_percentile: 60,
    },
  };
  const rankBehindButHigherPr = {
    job: "Machinist",
    job_rank: 20,
    rank: 20,
    rdps: 900,
    performance: {
      qualified: true,
      sample_count: 200,
      rank: 10,
      top_percent: 5,
      score_percentile: 95.5,
    },
  };
  const fallbackCompare = (candidate, currentBest) => (candidate?.rdps ?? 0) > (currentBest?.rdps ?? 0);

  assert(
    個人成績代表是否較佳(rankAheadButLowerPr, rankBehindButHigherPr, 分位顯示模式前段, fallbackCompare),
    "前 N% 模式應保留既有代表列排序：職業 Rank 較前者優先。",
  );
  assert(
    個人成績代表是否較佳(rankBehindButHigherPr, rankAheadButLowerPr, 分位顯示模式PR, fallbackCompare),
    "PR 模式代表列應以 PR 值較高者優先。",
  );
  assert(
    比較個人成績分位顯示排序(rankBehindButHigherPr, rankAheadButLowerPr, 分位顯示模式PR) < 0,
    "PR 模式展開列與亮點排序應把 PR 較高者排在前面。",
  );
  assert(
    比較個人成績分位顯示排序(rankBehindButHigherPr, rankAheadButLowerPr, 分位顯示模式前段) < 0,
    "前 N% 模式的分位亮點仍應依 top_percent 較低者排在前面。",
  );
}

function validateUserProfileBadges() {
  const 零式副本鍵值 = [
    "savage_m1s", "savage_m2s", "savage_m3s", "savage_m4s",
    "savage_m5s", "savage_m6s", "savage_m7s", "savage_m8s",
  ];
  const 六絕副本鍵值 = [
    "ultimate_bahamut",
    "ultimate_ultima_weapon",
    "ultimate_alexander",
    "ultimate_dragonsong",
    "ultimate_omega",
    "ultimate_futures_rewritten",
  ];
  const 職業職能 = {
    Paladin: "role:tank",
    WhiteMage: "role:healer",
    Monk: "role:melee",
    Bard: "role:physical_ranged",
    BlackMage: "role:magical_ranged",
    Warrior: "role:tank",
  };
  const 公開成績 = [
    ...零式副本鍵值.map((encounterKey) => ({ encounter_key: encounterKey, job: "Paladin" })),
    ...六絕副本鍵值.map((encounterKey) => ({ encounter_key: encounterKey, job: "Paladin" })),
    ...Object.keys(職業職能).flatMap((job) => Array.from({ length: 10 }, () => ({
      encounter_key: "savage_m1s",
      job,
    }))),
    ...Array.from({ length: 32 }, () => ({ encounter_key: "savage_m2s", job: "Paladin" })),
  ];
  const 徽章 = 建立個人成績徽章({
    角色名稱: "測試角色",
    公開成績,
    公開同場玩家數: 50,
    最後紀錄時間: "2026-07-21T00:00:00.000Z",
    近期動態基準時間: Date.parse("2026-07-22T00:00:00.000Z"),
    顯示作者徽章: true,
    是網站作者: () => true,
    作者說明: "作者識別測試",
    取得職能代碼: (job) => 職業職能[job] || "",
  });
  const 徽章名稱 = new Set(徽章.map((徽章) => 徽章.名稱));
  const 多職說明 = 徽章.find((徽章) => 徽章.名稱 === "多職玩家")?.說明 || "";
  const 三色豆說明 = 徽章.find((徽章) => 徽章.名稱 === "三色豆")?.說明 || "";

  for (const 名稱 of ["輕量級踏破", "次重量級踏破", 六絕踏破稱號, "多職玩家", "三色豆", "高活躍", "社群核心", "近期活躍"]) {
    assert(徽章名稱.has(名稱), `完整公開成績應取得「${名稱}」徽章。`);
  }
  assert(
    徽章.find((徽章) => 徽章.名稱 === 六絕踏破稱號)?.樣式類別 === "六絕傳奇稱號",
    "六絕全通稱號必須帶有專屬的傳奇樣式類別。",
  );
  assert(
    徽章[0]?.名稱 === 六絕踏破稱號,
    "六絕全通稱號必須排在包含作者識別在內的所有徽章最前方。",
  );
  assert(!徽章名稱.has("零式全通"), "零式成就應改為依量級命名，不可保留固定的「零式全通」。");
  assert(多職說明.includes("6 個職業各有至少 10 場"), "多職玩家應要求至少六職各有十場公開通關紀錄。");
  assert(三色豆說明.includes("5 種職能各有至少 10 場"), "三色豆應以各職能的十場公開通關紀錄判定。");

  const 未完整量級 = 建立零式量級踏破徽章(公開成績.filter((成績) => 成績.encounter_key !== "savage_m8s"));
  assert(
    !未完整量級.some((徽章) => 徽章.名稱 === "次重量級踏破"),
    "少任一 M5S～M8S 有效版本公開成績時，不可發放次重量級踏破徽章。",
  );

  const M8過版成績 = 公開成績.map((成績) => (
    成績.encounter_key === "savage_m8s" ? { ...成績, is_obsolete_record: true } : 成績
  ));
  const 過版量級 = 建立零式量級踏破徽章(M8過版成績);
  assert(
    !過版量級.some((徽章) => 徽章.名稱 === "次重量級踏破"),
    "M5S～M8S 任一層只有過版紀錄時，不可發放次重量級踏破徽章。",
  );

  const 六絕含過版紀錄 = 建立個人成績徽章({
    公開成績: 公開成績.map((成績) => (
      成績.encounter_key === "ultimate_bahamut" ? { ...成績, is_obsolete_record: true } : 成績
    )),
    取得職能代碼: (job) => 職業職能[job] || "",
  });
  assert(
    六絕含過版紀錄.some((徽章) => 徽章.名稱 === 六絕踏破稱號),
    "六絕全通稱號是歷史成就，任一絕本標記過版後仍須保留。",
  );

  const 缺少一絕稱號 = 建立個人成績徽章({
    公開成績: 公開成績.filter((成績) => 成績.encounter_key !== "ultimate_omega"),
    取得職能代碼: (job) => 職業職能[job] || "",
  });
  assert(
    !缺少一絕稱號.some((徽章) => 徽章.名稱 === 六絕踏破稱號),
    "缺少任一絕本公開通關紀錄時，不可發放六絕全通稱號。",
  );

  const 第一筆詩人成績索引 = 公開成績.findIndex((成績) => 成績.job === "Bard");
  const 少一場詩人 = 公開成績.filter((_, index) => index !== 第一筆詩人成績索引);
  const 未達職業門檻徽章 = 建立個人成績徽章({
    公開成績: 少一場詩人,
    取得職能代碼: (job) => 職業職能[job] || "",
  });
  assert(
    !未達職業門檻徽章.some((徽章) => 徽章.名稱 === "多職玩家"),
    "任一達標職業少於十場時，不可被算入多職玩家的六職門檻。",
  );
}

async function validateUserProfileBadgeDataScope() {
  const [source, profileSource, profileStyles] = await Promise.all([
    readText(path.join(srcDir, "composables", "useRankingApp.js")),
    readText(path.join(srcDir, "pages", "UserProfilePage.vue")),
    readText(path.join(srcDir, "styles", "pages-profile.css")),
  ]);
  assert(
    source.includes('取得使用者副本成績(使用者資料.value, "", () => true, 使用者代表成績是否較佳)'),
    "個人成績徽章應使用未套用伺服器或職業篩選的完整公開成績。",
  );
  assert(
    source.includes("公開同場玩家數: 使用者資料.value.summary?.teammate_count"),
    "社群核心應使用完整的 summary.teammate_count，而非最多二十位的 frequent_teammates。",
  );
  assert(
    profileSource.includes(':class="徽章.樣式類別"')
      && profileStyles.includes(".使用者徽章.六絕傳奇稱號")
      && profileStyles.includes("@property --六絕虹彩角度")
      && profileStyles.includes("from var(--六絕虹彩角度)")
      && profileStyles.includes(':root[data-theme="light"] .使用者徽章.六絕傳奇稱號')
      && profileStyles.includes("--六絕稱號文字色")
      && profileStyles.includes("--六絕虹彩光暈不透明度")
      && profileStyles.includes("@keyframes 六絕傳奇虹彩流轉")
      && profileStyles.includes("@media (prefers-reduced-motion: reduce)"),
    "六絕全通稱號必須套用虹彩循環邊框，並尊重減少動態效果偏好。",
  );
}

async function validateUserProfileGameVersionFilter() {
  const [source, profileSource, headerSource, controlsStyles, profileStyles, responsiveStyles] = await Promise.all([
    readText(path.join(srcDir, "composables", "useRankingApp.js")),
    readText(path.join(srcDir, "pages", "UserProfilePage.vue")),
    readText(path.join(srcDir, "components", "AppHeader.vue")),
    readText(path.join(srcDir, "styles", "controls.css")),
    readText(path.join(srcDir, "styles", "pages-profile.css")),
    readText(path.join(srcDir, "styles", "responsive.css")),
  ]);

  assert(
    profileSource.includes('v-if="!使用者簡表模式 && 顯示版本紀錄"')
      && profileSource.includes('v-model="使用者版本篩選"')
      && !profileSource.includes('<option value="">全部版本</option>'),
    "開啟版本紀錄後，個人成績單查詢列必須提供版本快照選單，且不應另設全部版本。",
  );
  assert(
    source.includes('const 使用者版本篩選 = ref("");')
      && source.includes("const 使用者版本選項 = computed(() => {")
      && source.includes("function 符合使用者版本篩選(成績)"),
    "個人成績單的版本篩選必須由共享狀態依目前伺服器的公開紀錄產生。",
  );
  assert(
    source.includes("return 符合使用者職業篩選(成績) && 符合使用者版本篩選(成績);")
      && source.includes("function 成績屬於使用者版本快照(成績, 目標版本)")
      && source.includes("比較個人成績版本(紀錄版本, 目標版本) >= 0")
      && source.includes("return Boolean(目標版本) && 成績屬於使用者版本快照(成績, 目標版本);")
      && source.includes(".map((成績) => 取得個人成績紀錄版本(成績))"),
    "版本選擇必須與職業篩選交集，並以截至目標版本的累積快照篩選相容的版本紀錄。",
  );
  assert(
    profileSource.includes("取得個人成績紀錄版本(成績) || \"—\"")
      && profileSource.includes("個人分位版本"),
    "個人分位亮點與歷史紀錄必須使用相同的版本解析結果，避免舊資料顯示空白。",
  );
  assert(
    profileSource.includes('v-if="顯示版本紀錄" class="成績列數值 成績列數值版本"')
      && profileSource.includes('副本.best_entry ? 取得個人成績紀錄版本(副本.best_entry) || "—" : "-"')
      && profileStyles.includes(".個人成績列.個人成績列顯示版本")
      && responsiveStyles.includes(".成績列數值版本 {"),
    "開啟版本資料時，成績列摘要必須顯示代表成績的版本，且桌面與手機版版面都要保留欄位空間。",
  );
  assert(
    profileStyles.includes("minmax(80px, 0.52fr)")
      && profileStyles.includes("--個人成績欄距: 8px;")
      && profileStyles.includes(".成績列數值 .說明標籤 {")
      && profileStyles.includes(".成績列數值 .說明提示按鈕 {")
      && profileStyles.includes("width: 16px;"),
    "成績列摘要的說明標籤與提示按鈕必須保留足夠間距，避免開啟版本欄後擁擠。",
  );
  assert(
    source.includes("watch([顯示版本紀錄, 使用者版本選項], () => {")
      && source.includes('const 最新可用版本 = 使用者版本選項.value[0]?.value || "";')
      && source.includes("使用者版本篩選.value = 最新可用版本;"),
    "開啟版本顯示或切換到沒有原選版本的伺服器時，必須預設回到最新版本快照。",
  );
  assert(
    controlsStyles.includes(".個人成績搜尋表單.個人成績搜尋表單版本篩選")
      && controlsStyles.includes(".個人成績版本欄位 select"),
    "版本欄位必須有桌面版查詢列配置與可讀取的選單寬度。",
  );
  assert(
    headerSource.includes('<h3 id="版本紀錄設定標題">版本紀錄</h3>')
      && headerSource.includes("設定版本紀錄顯示(true)")
      && source.includes("const 版本紀錄顯示偏好儲存鍵")
      && source.includes("const 顯示版本紀錄 = ref(false);"),
    "設定視窗必須將個人成績單版本改為共用的版本紀錄偏好。",
  );
  assert(
    source.includes("建立個人成績趨勢版本切點")
      && source.includes("使用時間橫軸")
      && profileSource.includes("趨勢版本切點層")
      && profileSource.includes("趨勢.版本切點列表")
      && profileStyles.includes("趨勢版本切點"),
    "開啟版本資料時，成績趨勢必須以時間軸標示繁中服版本切點。",
  );
  assert(
    source.includes("const 使用者趨勢選取點 = ref({});")
      && source.includes("function 取得使用者趨勢顯示數值標記(趨勢)")
      && source.includes("function 清除所有使用者趨勢選取點()")
      && source.includes("使用者趨勢選取點.value = {};")
      && profileSource.includes("趨勢數值標記層")
      && profileSource.includes("取得使用者趨勢顯示數值標記(趨勢)")
      && !profileSource.includes("<small>{{ 點.標籤 }}</small>")
      && profileSource.includes("@mouseenter=\"設定使用者趨勢選取點")
      && profileSource.includes("@click.stop=\"設定使用者趨勢選取點")
      && profileSource.includes("@mouseleave=\"清除使用者趨勢選取點")
      && profileSource.includes("window.addEventListener(\"pointerdown\", 處理趨勢圖外部觸控)")
      && !profileSource.includes('class="趨勢摘要"')
      && !profileSource.includes('class="趨勢刻度"')
      && profileStyles.includes(".趨勢點::after")
      && profileStyles.includes(".趨勢點.選取中::after"),
    "趨勢預設只顯示最高／最低數值；懸停或點擊資料點時，必須改顯示選取紀錄並可回復預設標記。",
  );
  const 歷史排序欄位 = ["recordedAt", "performance", "active", "gcdCoverage", "dps", "rdps", "adps", "gameVersion", "clearTime"];
  assert(
    source.includes("const 使用者歷史排序設定 = ref({});")
      && source.includes("function 排序使用者歷史成績(副本)")
      && source.includes("function 取得使用者歷史排序數值(成績, 欄位)")
      && source.includes("使用者歷史排序設定.value = {};"),
    "個人成績歷史表格必須以各副本獨立的排序狀態處理，並在篩選結果更換時重設。",
  );
  assert(
    歷史排序欄位.every((欄位) => profileSource.includes(`切換使用者歷史排序(副本.encounter_key, '${欄位}')`))
      && profileSource.includes('v-for="成績 in 排序使用者歷史成績(副本)"')
      && profileSource.includes("使用者歷史排序ARIA")
      && profileSource.includes("使用者歷史排序方向圖示"),
    "歷史表格必須讓紀錄時間、同職分位、Active、GCD、DPS、rDPS、aDPS、版本與通關時間欄位可點擊排序。",
  );
  assert(
    source.includes('欄位 === "performance" && 分位顯示模式.value !== 分位顯示模式PR')
      && source.includes('case "gameVersion":')
      && source.includes("return 左側數值 === null ? 1 : -1;")
      && source.includes("watch(分位顯示模式, () => {")
      && source.includes('設定?.欄位 !== "performance"'),
    "同職分位排序必須配合 PR／前 N% 顯示方向，切換顯示模式時保留高低排序意圖，缺少數值或版本的紀錄則固定排在最後。",
  );
  assert(
    profileSource.includes('class="歷史排序控制"')
      && responsiveStyles.includes(".歷史排序控制 {")
      && profileStyles.includes(".歷史排序控制 {\n  display: none;"),
    "手機版隱藏表頭時，歷史表格必須提供排序選單與方向按鈕。",
  );
}

async function validateHelpTooltipPreference() {
  const [source, headerSource, profileStyles] = await Promise.all([
    readText(path.join(srcDir, "composables", "useRankingApp.js")),
    readText(path.join(srcDir, "components", "AppHeader.vue")),
    readText(path.join(srcDir, "styles", "pages-profile.css")),
  ]);

  assert(
    source.includes('const 顯示說明提示 = ref(true);')
      && source.includes('return window.localStorage.getItem(說明提示顯示偏好儲存鍵) !== "disabled";')
      && source.includes('document.documentElement.dataset.showHelpTooltips = String(顯示提示);')
      && source.includes("function 設定說明提示顯示(啟用)"),
    "說明提示按鈕必須預設顯示，並將使用者偏好保存至瀏覽器與根節點狀態。",
  );
  assert(
    headerSource.includes('aria-labelledby="說明提示設定標題"')
      && headerSource.includes("設定說明提示顯示(false)")
      && headerSource.includes("設定說明提示顯示(true)"),
    "設定視窗必須提供說明提示按鈕的顯示與隱藏切換。",
  );
  assert(
    profileStyles.includes(':root[data-show-help-tooltips="false"] .說明提示 {'),
    "關閉說明提示按鈕時，所有頁面與 Teleport 彈窗中的提示都必須一併隱藏。",
  );
}

function validateUserProfileGameVersionFallback() {
  assert(
    取得個人成績紀錄版本({ recorded_at_iso: "2026-03-10T09:59:59.000Z" }) === "7.0"
      && 取得個人成績紀錄版本({ recorded_at_iso: "2026-03-10T10:00:00.000Z" }) === "7.05"
      && 取得個人成績紀錄版本({ recorded_at_iso: "2026-06-23T10:00:00.000Z" }) === "7.15"
      && 取得個人成績紀錄版本({ recorded_at_iso: "2026-07-28T05:00:00.000Z" }) === "7.2",
    "缺少 game_version 的既有個人成績必須依繁中服改版時間正確回推版本。",
  );
  assert(
    取得個人成績紀錄版本({ game_version: "7.1", recorded_at_iso: "2026-07-21T00:00:00.000Z" }) === "7.1"
      && 取得個人成績紀錄版本({ recorded_at_iso: "not-a-date" }) === "",
    "明確寫入的 game_version 必須優先，無法判讀時間的資料則不可臆測版本。",
  );

  const 趨勢切點 = 建立個人成績趨勢版本切點(
    Date.parse("2026-03-01T00:00:00.000Z"),
    Date.parse("2026-07-01T00:00:00.000Z"),
  );
  assert(
    趨勢切點.map((切點) => 切點.label).join(",") === "7.05,7.1,7.15"
      && 趨勢切點.every((切點) => 切點.x > 0 && 切點.x < 100),
    "成績趨勢必須只標示圖形時間範圍內的繁中服版本切點。",
  );
  assert(
    建立個人成績趨勢版本切點(NaN, Date.parse("2026-07-01T00:00:00.000Z")).length === 0,
    "無法解析成績時間時，不可顯示可能錯位的版本切點。",
  );
}

function validateGcdCoverageDiagnosticFields() {
  const rankingEntry = {
    id: "sample-gcd-entry",
    character_name: "測試角色",
    server: "陸行鳥",
    job: "Bard",
    dps: 1000,
    rdps: 1000,
    adps: 1000,
    active_time_ms: 600000,
    active_percent: 99.5,
    gcd_coverage: {
      percent: 98.82,
      covered_time_ms: 593000,
      denominator_ms: 600000,
      downtime_ms: 0,
      gcd_cast_count: 240,
      calculation_version: 1,
      source: "raw_events",
      speed_stat_source: "estimated",
      estimated_speed_below_minimum: true,
      fallback_selection: "bard_raw_events_with_casts_graph_lock_blend",
      downtime_selection: "casts_graph_encounter_gap",
      raw_events_percent: 98.49,
      raw_events_denominator_ms: 282847,
      casts_graph_percent: 100,
      casts_graph_denominator_ms: 414286,
      raw_targetability_percent: 95.04,
      raw_targetability_denominator_ms: 482477,
    },
    clear_time_ms: 600000,
    clear_time_seconds: 600,
    damage_downtime_ms: null,
    damage_downtime_seconds: null,
    damage_time_ms: 600000,
    damage_time_seconds: 600,
    recorded_at_iso: "2026-01-01T00:00:00.000Z",
    report_code: "sample",
    report_url: "https://www.fflogs.com/reports/sample",
    fight_id: 1,
    duplicate_count: 1,
    rank: 1,
  };

  const contractIssues = validateSchemaContract(
    rankingEntry,
    publicDataContracts.rankingEntry,
    "GCD 覆蓋率診斷欄位範例",
  );
  assert(
    contractIssues.length === 0,
    `GCD 覆蓋率診斷欄位應符合公開資料契約：${contractIssues.join("；")}`,
  );
}

function validateJobIconCacheKeys() {
  const paladinIcon = 職業Icon路徑("Paladin");
  const tankIcon = 職業類型Icon路徑("role:tank");
  const uniqueIconCount = new Set(可快取職業Icon路徑清單).size;

  assert(paladinIcon === "/icons/jobs/Paladin.png", "騎士職業圖示路徑應維持既有公開 URL，避免破壞舊快取。");
  assert(tankIcon === "/icons/jobs/RoleTank.png", "防護職能圖示路徑應維持既有公開 URL，避免破壞舊快取。");
  assert(職業Icon路徑("Paladin") === paladinIcon, "職業圖示路徑應從穩定索引重用同一個 cache key。");
  assert(
    可快取職業Icon路徑清單.includes(paladinIcon) && 可快取職業Icon路徑清單.includes(tankIcon),
    "職業圖示預熱清單應包含職業與職能圖示，讓各頁面切換可重用瀏覽器快取。",
  );
  assert(uniqueIconCount === 可快取職業Icon路徑清單.length, "職業圖示預熱清單不應包含重複 URL。");
}

function addImportedBindings(source, bindings) {
  const namedImportPattern = /import\s*\{([\s\S]*?)\}\s*from\s*["'][^"']+["']/g;
  for (const match of source.matchAll(namedImportPattern)) {
    for (const rawPart of match[1].split(",")) {
      const part = rawPart.trim();
      if (!part) {
        continue;
      }
      const aliasMatch = part.match(/\s+as\s+(.+)$/);
      bindings.add((aliasMatch?.[1] || part).trim());
    }
  }

  const defaultImportPattern = /import\s+([^\s{},*][^\s{},]*)\s+from\s*["'][^"']+["']/g;
  for (const match of source.matchAll(defaultImportPattern)) {
    bindings.add(match[1].trim());
  }

  const namespaceImportPattern = /import\s+\*\s+as\s+([^\s]+)\s+from\s*["'][^"']+["']/g;
  for (const match of source.matchAll(namespaceImportPattern)) {
    bindings.add(match[1].trim());
  }
}

function addDeclaredBindings(source, bindings) {
  const declarationPattern = /^\s*(?:(?:async\s+)?function|const|let|var|class)\s+([^\s=({]+)/gmu;
  for (const match of source.matchAll(declarationPattern)) {
    bindings.add(match[1].trim());
  }

  const objectDestructurePattern = /^\s*(?:const|let|var)\s*\{([\s\S]*?)\}\s*=/gmu;
  for (const match of source.matchAll(objectDestructurePattern)) {
    for (const rawPart of match[1].split(",")) {
      const part = rawPart.trim();
      if (!part || part.startsWith("...")) {
        continue;
      }
      const withoutDefault = part.split("=")[0].trim();
      const alias = withoutDefault.includes(":") ? withoutDefault.split(":").at(-1).trim() : withoutDefault;
      if (alias) {
        bindings.add(alias);
      }
    }
  }
}

function findMatchingBrace(source, openIndex) {
  let depth = 0;
  let inString = "";
  let escaped = false;

  for (let index = openIndex; index < source.length; index += 1) {
    const char = source[index];
    const previous = source[index - 1];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === inString && !(inString === "`" && previous === "$")) {
        inString = "";
      }
      continue;
    }

    if (char === "\"" || char === "'" || char === "`") {
      inString = char;
      continue;
    }

    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return index;
      }
    }
  }

  return -1;
}

function extractUseRankingAppReturnBlock(source) {
  const returnIndex = source.lastIndexOf("\n  return {");
  if (returnIndex === -1) {
    reportIssue("useRankingApp.js 找不到 useRankingApp() 的 return 物件");
    return "";
  }

  const openIndex = source.indexOf("{", returnIndex);
  const closeIndex = findMatchingBrace(source, openIndex);
  if (closeIndex === -1) {
    reportIssue("useRankingApp.js 的 return 物件大括號不完整");
    return "";
  }

  return source.slice(openIndex + 1, closeIndex);
}

async function validateUseRankingAppReturnBindings() {
  const filePath = path.join(srcDir, "composables", "useRankingApp.js");
  const source = await readText(filePath);
  const bindings = new Set();
  addImportedBindings(source, bindings);
  addDeclaredBindings(source, bindings);

  const returnBlock = extractUseRankingAppReturnBlock(source);
  const shorthandNames = [];
  for (const line of returnBlock.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.includes(":") || trimmed.startsWith("//")) {
      continue;
    }
    const match = trimmed.match(/^([\p{L}\p{N}_$\u200c\u200d]+),?$/u);
    if (match) {
      shorthandNames.push(match[1]);
    }
  }

  for (const name of shorthandNames) {
    if (!bindings.has(name)) {
      reportIssue(`useRankingApp() return 了未定義的資料或函式：${name}`);
    }
  }
}

async function validateFrontendFetchBoundary() {
  const allowedFetchFiles = new Set([
    normalizePath(path.join(srcDir, "utils", "fetchJson.js")),
    normalizePath(path.join(srcDir, "utils", "userData.js")),
  ]);
  const files = [
    "analytics.js",
    "main.js",
    "composables/useRankingApp.js",
    "composables/rankingApp/context.js",
    "composables/rankingApp/defaults.js",
    "composables/rankingApp/useRankingData.js",
    "domain/jobs.js",
    "utils/announcements.js",
    "utils/fetchJson.js",
    "utils/publicData.js",
    "utils/reportStatus.js",
    "utils/shareMeta.js",
    "utils/siteFeatures.js",
    "utils/statsDisplay.js",
    "utils/urlState.js",
    "utils/userData.js",
    "utils/viewHelpers.js",
  ];

  for (const relativePath of files) {
    const filePath = path.join(srcDir, relativePath);
    const source = await readText(filePath);
    if (source.includes("fetch(") && !allowedFetchFiles.has(normalizePath(filePath))) {
      reportIssue(`${relativePath} 直接呼叫 fetch，前端資料讀取應集中在 utils/fetchJson.js 或 utils/userData.js`);
    }
    if (/fflogs\.com\/api|api\/v2|graphql/i.test(source)) {
      reportIssue(`${relativePath} 看起來直接碰到 FFLogs API，前端不得繞過資料管線`);
    }
  }
}

async function validateSiteFeatureFlags() {
  const source = await readText(path.join(srcDir, "utils", "siteFeatures.js"));
  assert(
    /export\s+const\s+顯示Gcd覆蓋率\s*=\s*true\s*;/.test(source),
    "目前營運設定應透過 src/utils/siteFeatures.js 開啟 GCD 覆蓋率顯示",
  );
  assert(
    source.includes("這些旗標只影響 UI 呈現"),
    "siteFeatures.js 應保留旗標只影響 UI 呈現的註解，避免誤改資料管線",
  );
}

async function validateStaticSeoBuildOptions() {
  const source = await readText(path.join(rootDir, "scripts", "build_spa_fallback.mjs"));
  assert(source.includes("resize(1200, 630"), "SEO/OG 靜態圖必須維持 1200x630 輸出。");
  assert(source.includes("image/png"), "SEO/OG meta 必須維持 crawler-safe PNG。");
  assert(source.includes("colors: 128"), "OG PNG 應限制 palette 色數，避免玩家分享圖讓 Pages payload 膨脹。");
}

function extractSourceSection(source, startText, endText, label) {
  const startIndex = source.indexOf(startText);
  const endIndex = source.indexOf(endText, startIndex + startText.length);
  if (startIndex === -1 || endIndex === -1) {
    reportIssue(`${label} 區段定位失敗，無法驗證副本切換篩選狀態`);
    return "";
  }

  return source.slice(startIndex, endIndex);
}

async function validateEncounterSwitchFilterPersistence() {
  const filePath = path.join(srcDir, "composables", "useRankingApp.js");
  const source = await readText(filePath);
  const rankingWatcher = extractSourceSection(source, "watch(副本鍵值", "watch(職業類型篩選", "排行榜副本切換 watcher");
  const statsWatcher = extractSourceSection(
    source,
    "watch([統計副本鍵值, 全服統計資料]",
    "watch([統計副本鍵值, 統計版本範圍",
    "全服統計副本切換 watcher",
  );

  for (const resetExpression of ['伺服器篩選.value = ""', '職業類型篩選.value = ""', '職業篩選.value = ""']) {
    assert(!rankingWatcher.includes(resetExpression), `排行榜切換副本時不可清空既有篩選：${resetExpression}`);
  }

  assert(
    statsWatcher.includes("統計伺服器可識別"),
    "全服統計切換副本時應以全域伺服器清單判斷有效性，避免只因目前副本沒有資料就清空伺服器篩選",
  );
  assert(
    statsWatcher.includes("統計職業範圍可識別"),
    "全服統計切換副本時應以職業定義判斷有效性，避免只因目前副本沒有資料就清空職業篩選",
  );
}

function validateUserProfileClearSummary() {
  const lightHeavyweight = { key: "light-heavyweight", label: "輕量級", order: 1 };
  const cruiserweight = { key: "cruiserweight", label: "次重量級", order: 2 };
  const version72OpenedAt = Date.parse("2026-07-28T05:00:00.000Z");
  assert(預設個人成績簡表版本 === "7.2", "個人成績簡表目前必須預設顯示 7.2。");
  const encounters = [
    {
      key: "savage_m1s",
      name: "零式 M1S / 黑貓",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.05",
      profile_summary_savage_tier: { ...lightHeavyweight, floor: 1 },
    },
    {
      key: "savage_m2s",
      name: "零式 M2S / 蜂蜂小甜心",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.05",
      profile_summary_savage_tier: { ...lightHeavyweight, floor: 2 },
    },
    {
      key: "savage_m3s",
      name: "零式 M3S / 野蠻炸彈",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.05",
      profile_summary_savage_tier: { ...lightHeavyweight, floor: 3 },
    },
    {
      key: "savage_m4s",
      name: "零式 M4S / 狡雷",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.05",
      profile_summary_savage_tier: { ...lightHeavyweight, floor: 4 },
    },
    {
      key: "savage_m5s",
      name: "零式 M5S / 熱舞綠光",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.2",
      profile_summary_savage_tier: { ...cruiserweight, floor: 1 },
    },
    {
      key: "savage_m6s",
      name: "零式 M6S / 糖彩狂潮",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.2",
      profile_summary_savage_tier: { ...cruiserweight, floor: 2 },
    },
    {
      key: "savage_m7s",
      name: "零式 M7S / 野蠻憎惡",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.2",
      profile_summary_savage_tier: { ...cruiserweight, floor: 3 },
    },
    {
      key: "savage_m8s",
      name: "零式 M8S / 呼嘯之劍",
      category: "零式",
      current_high_end: true,
      profile_summary_available_from: "7.2",
      profile_summary_savage_tier: { ...cruiserweight, floor: 4 },
    },
    { key: "ultimate", name: "絕 測試", category: "絕", profile_summary_available_from: "7.0" },
    { key: "current-extreme", name: "極 測試", category: "極", current_high_end: true, profile_summary_available_from: "7.1" },
    {
      key: "unreal_byakko",
      name: "幻 白虎",
      category: "幻",
      current_high_end: true,
      profile_summary_available_from: "7.1",
      profile_summary_available_until: "7.15",
    },
    { key: "unreal_suzaku", name: "幻 朱雀", category: "幻", current_high_end: true, profile_summary_available_from: "7.2" },
    { key: "current-chaotic", name: "滅 測試", category: "滅", current_high_end: true, profile_summary_available_from: "7.15" },
    { key: "old-extreme", name: "極 舊副本", category: "極", profile_summary_available_from: "7.0" },
  ];
  const groups = 暫時固定現在時間(version72OpenedAt, () => 建立個人成績簡表群組(encounters, [
    {
      encounter_key: "savage_m5s",
      public_entries: [
        { job: "WhiteMage", performance: { score_percentile: 82 } },
        { job: "BlackMage", performance: { score_percentile: 96 } },
      ],
    },
    { encounter_key: "savage_m6s", public_entries: [{ job: "WhiteMage" }] },
    { encounter_key: "savage_m7s", public_entries: [{ job: "BlackMage", performance: { score_percentile: 91 } }] },
    { encounter_key: "savage_m8s", public_entries: [{ job: "WhiteMage" }] },
    { encounter_key: "ultimate", public_entries: [{ job: "WhiteMage", is_obsolete_record: true }] },
    { encounter_key: "current-extreme", public_entries: [{ job: "BlackMage" }] },
    { encounter_key: "old-extreme", public_entries: [{ job: "BlackMage", is_obsolete_record: true }] },
  ], "7.2"));
  const savageGroup = groups.find((group) => group.key === "savage");
  const ultimateGroup = groups.find((group) => group.key === "ultimate");
  const extremeGroup = groups.find((group) => group.key === "extreme");
  const unrealGroup = groups.find((group) => group.key === "unreal");
  const chaoticGroup = groups.find((group) => group.key === "chaotic");
  const ultimateEncounter = encounters.find((encounter) => encounter.key === "ultimate");
  const currentExtremeEncounter = encounters.find((encounter) => encounter.key === "current-extreme");
  const oldExtremeEncounter = encounters.find((encounter) => encounter.key === "old-extreme");
  const byakkoEncounter = encounters.find((encounter) => encounter.key === "unreal_byakko");
  const suzakuEncounter = encounters.find((encounter) => encounter.key === "unreal_suzaku");

  assert(是個人成績簡表目標副本(ultimateEncounter), "所有絕本都必須成為個人成績簡表目標。");
  assert(是個人成績簡表目標副本(encounters[0]), "current_high_end=true 的副本必須成為個人成績簡表目標。");
  assert(是個人成績簡表目標副本(oldExtremeEncounter), "極本即使不是目前高難也必須保留在個人成績簡表。");
  assert(
    savageGroup?.name === "零式"
      && savageGroup.selected_tier_key === "cruiserweight"
      && savageGroup.tiers?.map((tier) => tier.label).join(",") === "輕量級,次重量級"
      && savageGroup.tiers?.find((tier) => tier.key === "cruiserweight")?.is_current_version_complete
      && savageGroup.encounters.map((encounter) => encounter.name).join(",") === "M5S / 熱舞綠光,M6S / 糖彩狂潮,M7S / 野蠻憎惡,M8S / 呼嘯之劍",
    "零式簡表必須列出所選版本已開放量級、預設選取最新量級，並在四層皆有效通關時標示完成。",
  );
  assert(ultimateGroup?.encounters.length === 1, "簡表必須保留所有絕本。");
  assert(
    extremeGroup?.encounters.length === 2
      && unrealGroup?.encounters.map((encounter) => encounter.name).join(",") === "朱雀"
      && chaoticGroup?.encounters.length === 1,
    "7.2 簡表應完整列出極本，並以朱雀取代已關閉的白虎，保留目前高難的滅本。",
  );
  assert(
    savageGroup?.encounters[0]?.狀態 === "pr" && savageGroup.encounters[0]?.pr_value === 96 && savageGroup.encounters[0]?.job === "BlackMage",
    "有效成績應顯示跨職業最高 PR 與對應職業。",
  );
  const selectedLightSavage = 暫時固定現在時間(
    version72OpenedAt,
    () => 建立個人成績簡表群組(encounters, [], "7.2", "light-heavyweight"),
  ).find((group) => group.key === "savage");
  assert(
    selectedLightSavage?.selected_tier_key === "light-heavyweight"
      && selectedLightSavage.encounters.map((encounter) => encounter.name).join(",") === "M1S / 黑貓,M2S / 蜂蜂小甜心,M3S / 野蠻炸彈,M4S / 狡雷"
      && !selectedLightSavage.tiers?.find((tier) => tier.key === "light-heavyweight")?.is_current_version_complete,
    "手動選擇已開放的舊量級時，零式簡表必須切換對應四層，且不能把未完成量級誤標為全通。",
  );
  assert(ultimateGroup?.encounters[0]?.狀態 === "obsolete-clear", "僅有過版成績時應改顯示灰色通關勾勾。");
  assert(extremeGroup?.encounters[0]?.狀態 === "valid-clear", "有效通關缺少 PR 時仍應保留有效通關勾勾。");
  assert(extremeGroup?.encounters[1]?.狀態 === "obsolete-clear", "過版極本有公開成績時應顯示灰色通關勾勾。");
  assert(!unrealGroup?.encounters[0]?.已收錄通關 && !chaoticGroup?.encounters[0]?.已收錄通關, "沒有公開成績的目標副本應標示為尚未收錄。");

  const version70Groups = 建立個人成績簡表群組(encounters, [
    { encounter_key: "old-extreme", public_entries: [{ job: "BlackMage", recorded_at_iso: "2026-03-09T23:59:59.000Z" }] },
    { encounter_key: "current-extreme", public_entries: [{ job: "BlackMage", recorded_at_iso: "2026-03-09T23:59:59.000Z" }] },
  ], "7.0");
  assert(version70Groups.some((group) => group.key === "extreme") && !version70Groups.some((group) => group.key === "savage"), "7.0 簡表只能列出 7.0 時已開放的副本。");
  assert(!副本符合個人成績簡表版本(encounters[0], "7.0"), "7.05 才開放的零式不可出現在 7.0 簡表。");
  assert(!副本符合個人成績簡表版本(currentExtremeEncounter, "7.0"), "7.1 才開放的極本不可出現在 7.0 簡表。");
  assert(成績符合個人成績簡表版本({ recorded_at_iso: "2026-03-10T09:59:59.000Z" }, "7.0"), "7.0 應保留 7.05 開放前的戰鬥。");
  assert(!成績符合個人成績簡表版本({ recorded_at_iso: "2026-03-10T10:00:00.000Z" }, "7.0"), "7.0 不可混入 7.05 開放後的戰鬥。");
  const version705Savage = 建立個人成績簡表群組(encounters, [], "7.05").find((group) => group.key === "savage");
  assert(
    version705Savage?.name === "零式"
      && version705Savage.selected_tier_key === "light-heavyweight"
      && version705Savage.tiers?.length === 1
      && version705Savage.encounters.length === 4
      && version705Savage.encounters.map((encounter) => encounter.name).join(",") === "M1S / 黑貓,M2S / 蜂蜂小甜心,M3S / 野蠻炸彈,M4S / 狡雷",
    "較新的次重量級尚未開放時，7.05 零式簡表必須只提供輕量級，並以各樓層副本名稱顯示。",
  );
  const version715Savage = 建立個人成績簡表群組(encounters, [], "7.15").find((group) => group.key === "savage");
  assert(
    version715Savage?.tiers?.map((tier) => tier.key).join(",") === "light-heavyweight"
      && !副本符合個人成績簡表版本(encounters.find((encounter) => encounter.key === "savage_m5s"), "7.15"),
    "7.15 簡表不可提早顯示 7.2 的次重量級。",
  );
  const version715Unreal = 暫時固定現在時間(
    version72OpenedAt,
    () => 建立個人成績簡表群組(encounters, [], "7.15").find((group) => group.key === "unreal"),
  );
  assert(
    version715Unreal?.encounters.map((encounter) => encounter.name).join(",") === "白虎"
      && 暫時固定現在時間(
        version72OpenedAt,
        () => 副本符合個人成績簡表版本(byakkoEncounter, "7.15")
          && !副本符合個人成績簡表版本(byakkoEncounter, "7.2")
          && !副本符合個人成績簡表版本(suzakuEncounter, "7.15")
          && 副本符合個人成績簡表版本(suzakuEncounter, "7.2"),
      ),
    "幻白虎只應保留至 7.15 快照，7.2 必須改由幻朱雀呈現。",
  );
  assert(成績符合個人成績簡表版本({ recorded_at_iso: "2026-07-28T04:59:59.000Z" }, "7.15"), "7.15 應保留 7.2 開放前的戰鬥。");
  assert(!成績符合個人成績簡表版本({ recorded_at_iso: "2026-07-28T05:00:00.000Z" }, "7.15"), "7.15 不可混入 7.2 開放後的戰鬥。");
  const version72 = 個人成績簡表版本選項.find((版本) => 版本.value === "7.2");
  assert(version72?.available_from_iso === "2026-07-28T05:00:00.000Z", "7.2 必須保存繁中服的確認開放時間。");
  assert(!個人成績簡表版本已開放(version72, version72OpenedAt - 1), "7.2 在開放前必須維持待開放狀態。");
  assert(個人成績簡表版本已開放(version72, version72OpenedAt), "7.2 在開放時間當下必須可選取。");
  assert(
    建立個人成績簡表可選版本(version72OpenedAt - 1).find((版本) => 版本.value === "7.2")?.available === false
      && 建立個人成績簡表可選版本(version72OpenedAt).find((版本) => 版本.value === "7.2")?.available === true,
    "簡表選單必須依 7.2 開放時間自動切換待開放與可選狀態。",
  );
}

async function validateSavageProfileSummaryPresentation() {
  const source = await readText(path.join(srcDir, "pages", "UserProfilePage.vue"));
  const composableSource = await readText(path.join(srcDir, "composables", "useRankingApp.js"));
  const profileStyles = await readText(path.join(srcDir, "styles", "pages-profile.css"));
  const percentileStyles = await readText(path.join(srcDir, "styles", "tables-dialogs.css"));

  assert(
    source.includes('v-if="副本.job"') && !source.includes("群組.key !== 'savage' && 副本.job"),
    "零式量級內各樓層有職業時，必須和其他副本一樣顯示職業。",
  );
  assert(
    source.includes('<template v-if="副本.狀態 === \'pr\'">{{ 格式化PR值(副本.pr_value) }}</template>'),
    "零式量級內各樓層有有效 PR 時，必須顯示 PR。",
  );
  assert(
    source.includes("簡表PR色彩類別(副本.pr_value)")
      && composableSource.includes("function 簡表PR色彩類別(PR值)")
      && composableSource.includes("return 取得PR色彩類別(PR值);"),
    "簡表顯示 PR 時必須直接套用全站 PR 色彩分級，不受前 N% 顯示偏好影響。",
  );
  assert(
    profileStyles.includes("var(--分位PR色, var(--簡表群組文字))")
      && profileStyles.includes("var(--分位PR色, var(--簡表群組色))")
      && percentileStyles.includes("--分位PR色: #ff8000;")
      && percentileStyles.includes("--分位PR色: #e268a8;")
      && percentileStyles.includes("--分位PR色: #e5cc80;"),
    "簡表 PR 徽章必須重用 PR 95、99、100 等既有色彩，而非另建不同色票。",
  );
  assert(
    source.includes("量級.is_current_version_complete") && source.includes("零式量級完成圖示"),
    "四層全通的彩色勾勾必須保留在零式量級大項目。",
  );
  assert(
    source.includes("</header>\n            <div\n              v-if=\"群組.key === 'savage' && 群組.tiers?.length\"")
      && source.includes("</div>\n            <ul class=\"簡表副本列表\">"),
    "零式量級大項目必須位於零式標題下方、樓層小項目上方。",
  );
}

async function validateUserProfileSummaryJobFilter() {
  const pageSource = await readText(path.join(srcDir, "pages", "UserProfilePage.vue"));
  const composableSource = await readText(path.join(srcDir, "composables", "useRankingApp.js"));
  const controlStyles = await readText(path.join(srcDir, "styles", "controls.css"));

  assert(
    pageSource.includes('v-if="!使用者簡表模式 || 使用者有多個職業"')
      && pageSource.includes("個人成績搜尋表單簡表職業篩選: 使用者簡表模式 && 使用者有多個職業"),
    "簡表職能／職業選單只應在玩家有多個職業時顯示，並套用對應的桌面欄位配置。",
  );
  assert(
    composableSource.includes("const 使用者有多個職業 = computed(() => 使用者可用職業列表.value.length > 1);"),
    "簡表必須依目前玩家與伺服器實際收錄的職業數判斷是否顯示選單。",
  );
  assert(
    composableSource.includes("成績符合個人成績簡表版本(成績, 使用者簡表版本.value)")
      && composableSource.includes("&& 符合使用者職業篩選(成績)"),
    "簡表成績必須同時套用遊戲版本與職能／職業條件。",
  );
  assert(
    composableSource.includes('const 使用者職業類型篩選 = ref("");')
      && composableSource.includes('const 使用者職業篩選 = ref("");')
      && composableSource.includes('目前使用者職業類型.value?.名稱 || "全部職業"'),
    "簡表與一般成績單共用的職業條件必須預設為全部職業。",
  );
  assert(
    controlStyles.includes(
      ".個人成績搜尋表單.個人成績搜尋表單簡表職業篩選 {\n  grid-template-columns: minmax(220px, 1.1fr) minmax(200px, 0.82fr) minmax(128px, 0.42fr) auto auto;",
    ),
    "桌面版多職業簡表必須為玩家、職業、版本與操作按鈕保留可收縮欄位。",
  );
}

async function validateMobileProfileSummaryLayout() {
  const source = await readText(path.join(srcDir, "styles", "responsive.css"));
  const mobileStyleStart = source.indexOf("@media (max-width: 720px)");
  const mobileStyles = source.slice(mobileStyleStart);

  assert(mobileStyleStart >= 0, "responsive.css 必須保留手機版斷點。");
  assert(
    mobileStyles.includes(".個人成績簡表標題 > div {\n    min-width: 0;")
      && mobileStyles.includes(".個人成績簡表標題 > strong {\n    max-width: 100%;\n    white-space: normal;"),
    "手機版簡表標題與通關數摘要必須可以在窄寬度內收縮與換行。",
  );
  assert(
    mobileStyles.includes(".零式量級切換 {\n    display: grid;")
      && mobileStyles.includes(".零式量級按鈕 {\n    min-width: 0;\n    min-height: 44px;"),
    "手機版零式量級切換必須使用可收縮欄位，且保留足夠的觸控高度。",
  );
  assert(
    mobileStyles.includes(".簡表副本列表 {\n    display: grid;")
      && mobileStyles.includes(".簡表副本項 {\n    min-width: 0;\n    min-height: 44px;\n    display: grid;")
      && mobileStyles.includes(".簡表副本名稱 {\n    min-width: 0;\n    line-height: 1.35;\n    white-space: normal;\n    overflow-wrap: anywhere;"),
    "手機版簡表副本必須改為可換行的單列，避免長副本名稱造成水平溢出。",
  );
  assert(
    mobileStyles.includes(".使用者徽章區 {\n    display: grid;\n    grid-template-columns: minmax(0, 1fr);")
      && mobileStyles.includes(".使用者徽章 {\n    min-width: 0;"),
    "手機版個人徽章必須使用滿寬單欄，避免最後一張徽章留下突兀空白。",
  );
}

function expectedRankingGameVersion(recordedAtIso, gameVersions) {
  const recordedAt = new Date(recordedAtIso || "").getTime();
  if (!Number.isFinite(recordedAt)) {
    return null;
  }

  let matchedPatch = null;
  for (const version of gameVersions) {
    const startsAt = version.starts_at_iso === null ? null : new Date(version.starts_at_iso).getTime();
    if (startsAt === null || recordedAt >= startsAt) {
      matchedPatch = version.patch;
      continue;
    }
    break;
  }
  return matchedPatch;
}

function expectedDefaultRankingGameVersion(gameVersions, currentTime) {
  let latestOpenedPatch = "";
  for (const version of gameVersions) {
    const startsAt = version.starts_at_iso === null ? null : new Date(version.starts_at_iso).getTime();
    if (startsAt === null || (Number.isFinite(startsAt) && startsAt <= currentTime)) {
      latestOpenedPatch = version.patch;
    }
  }
  return latestOpenedPatch || gameVersions.at(-1)?.patch || "";
}

async function validateMobileUserSearchFormLayout() {
  const source = await readText(path.join(srcDir, "styles", "responsive.css"));
  const mobileStyleStart = source.indexOf("@media (max-width: 720px)");
  const mobileStyles = source.slice(mobileStyleStart);

  assert(
    mobileStyles.includes(
      ".使用者搜尋表單,\n  .個人成績搜尋表單.個人成績搜尋表單簡表模式,\n  .個人成績搜尋表單.個人成績搜尋表單版本篩選 {\n    grid-template-columns: minmax(0, 1fr);",
    ),
    "手機版簡表與版本篩選搜尋表單必須以同等權重覆寫桌面多欄設定，改為可收縮的單欄。",
  );
  assert(
    mobileStyles.includes(".個人成績搜尋表單 > * {\n    min-width: 0;")
      && mobileStyles.includes(".個人成績搜尋表單 > button {\n    width: 100%;\n    min-width: 0;\n    min-height: 44px;"),
    "手機版個人成績搜尋表單的欄位與按鈕必須可收縮，並保留足夠的觸控高度。",
  );
}

async function validatePublicDataForFrontend() {
  const encounters = await readJson(path.join(publicDataDir, "encounters.json"), "public/data/encounters.json");
  const encounterConfig = await readJson(path.join(rootDir, "config", "encounters.json"), "config/encounters.json");
  const announcements = await readJson(path.join(publicDataDir, "announcements.json"), "public/data/announcements.json");
  const globalStats = await readJson(path.join(publicDataDir, "global_stats.json"), "public/data/global_stats.json");
  const serverCompare = await readJson(path.join(publicDataDir, "server_compare.json"), "public/data/server_compare.json");
  const reportStatusIndex = await readJson(path.join(publicDataDir, "report_status_index.json"), "public/data/report_status_index.json");
  const updateStatus = await readJson(path.join(publicDataDir, "update_status.json"), "public/data/update_status.json");
  const honeyFans = await readJson(path.join(publicDataDir, "fun", "honey_b_fans.json"), "public/data/fun/honey_b_fans.json");
  const userIndex = await readJson(path.join(publicDataDir, "users", "index.json"), "public/data/users/index.json");
  const versionedEncounterKeys = new Set((encounters || []).filter((encounter) => encounter?.version_cutoff).map((encounter) => encounter.key));
  const profileSummaryVersions = new Set(個人成績簡表版本選項.map((version) => version.value));

  assert(Array.isArray(encounters) && encounters.length > 0, "public/data/encounters.json 必須提供前端副本清單");
  const configuredCurrentHighEndKeys = new Set(
    (Array.isArray(encounterConfig) ? encounterConfig : [])
      .filter((encounter) => encounter?.current_high_end === true)
      .map((encounter) => encounter.key),
  );
  const publicCurrentHighEndKeys = new Set(
    (encounters || []).filter((encounter) => encounter?.current_high_end === true).map((encounter) => encounter.key),
  );
  assert(configuredCurrentHighEndKeys.size > 0, "config/encounters.json 必須標記至少一個目前高難副本。");
  for (const key of configuredCurrentHighEndKeys) {
    const hasRanking = existsSync(path.join(rootDir, "data", "rankings", `${key}.json`))
      || existsSync(path.join(publicDataDir, "rankings", `${key}.json`));
    if (hasRanking) {
      assert(publicCurrentHighEndKeys.has(key), `${key} 的 current_high_end 標記必須寫入 public/data/encounters.json。`);
    }
  }
  for (const key of publicCurrentHighEndKeys) {
    assert(configuredCurrentHighEndKeys.has(key), `${key} 不可只在 public/data/encounters.json 標記 current_high_end。`);
  }
  for (const encounter of encounterConfig || []) {
    assert(
      typeof encounter?.profile_summary_available_from === "string" && profileSummaryVersions.has(encounter.profile_summary_available_from),
      `${encounter?.key || "未知副本"} 必須設定個人成績簡表的首次可見版本。`,
    );
    if (encounter?.profile_summary_available_until !== undefined) {
      assert(
        typeof encounter.profile_summary_available_until === "string"
          && profileSummaryVersions.has(encounter.profile_summary_available_until)
          && 個人成績簡表版本選項.findIndex((version) => version.value === encounter.profile_summary_available_from)
            <= 個人成績簡表版本選項.findIndex((version) => version.value === encounter.profile_summary_available_until),
        `${encounter?.key || "未知副本"} 的個人成績簡表最後可見版本必須是有效且不早於首次可見版本的遊戲版本。`,
      );
    }
    if (encounter?.category === "零式") {
      assert(
        typeof encounter?.profile_summary_savage_tier?.key === "string"
          && typeof encounter.profile_summary_savage_tier.label === "string"
          && Number.isInteger(encounter.profile_summary_savage_tier.order)
          && Number.isInteger(encounter.profile_summary_savage_tier.floor)
          && encounter.profile_summary_savage_tier.floor >= 1
          && encounter.profile_summary_savage_tier.floor <= 4,
        `${encounter?.key || "未知副本"} 必須設定完整的個人成績簡表零式量級。`,
      );
    }
  }
  for (const encounter of encounters || []) {
    assert(
      typeof encounter?.profile_summary_available_from === "string" && profileSummaryVersions.has(encounter.profile_summary_available_from),
      `${encounter?.key || "未知副本"} 的首次可見版本必須寫入 public/data/encounters.json。`,
    );
    if (encounter?.profile_summary_available_until !== undefined) {
      assert(
        typeof encounter.profile_summary_available_until === "string"
          && profileSummaryVersions.has(encounter.profile_summary_available_until),
        `${encounter?.key || "未知副本"} 的最後可見版本必須正確寫入 public/data/encounters.json。`,
      );
    }
    if (encounter?.category === "零式") {
      assert(
        typeof encounter?.profile_summary_savage_tier?.key === "string"
          && typeof encounter.profile_summary_savage_tier.label === "string"
          && Number.isInteger(encounter.profile_summary_savage_tier.order)
          && Number.isInteger(encounter.profile_summary_savage_tier.floor),
        `${encounter?.key || "未知副本"} 的零式量級必須寫入 public/data/encounters.json。`,
      );
    }
  }
  assert(announcements?.schema_version === 1, "public/data/announcements.json schema_version 必須是 1");
  assert(Array.isArray(announcements?.announcements), "public/data/announcements.json 必須包含 announcements");
  for (const announcement of announcements?.announcements || []) {
    assert(Boolean(announcement?.id), "每則公告必須有穩定 id，讓使用者關閉狀態可保存。");
    assert(Boolean(announcement?.summary), `${announcement?.id || "未知公告"} 必須有右上角摘要。`);
    assert(Boolean(announcement?.details_markdown), `${announcement?.id || "未知公告"} 必須有 Markdown 詳細內容。`);
  }
  assert(globalStats?.schema_version === 1, "public/data/global_stats.json schema_version 必須是 1");
  assert(Array.isArray(globalStats?.server_stats), "public/data/global_stats.json 必須包含 server_stats");
  assert(Array.isArray(globalStats?.role_stats), "public/data/global_stats.json 必須包含 role_stats");
  assert(Array.isArray(globalStats?.job_stats), "public/data/global_stats.json 必須包含 job_stats");
  assert(Array.isArray(globalStats?.damage_stats), "public/data/global_stats.json 必須包含 damage_stats");
  assert(Array.isArray(globalStats?.job_profiles), "public/data/global_stats.json 必須包含 job_profiles");
  assert(Array.isArray(globalStats?.encounters), "public/data/global_stats.json 必須包含 encounters");
  assert(serverCompare?.schema_version === 1, "public/data/server_compare.json schema_version 必須是 1");
  assert(Array.isArray(serverCompare?.servers), "public/data/server_compare.json 必須包含 servers");
  assert(reportStatusIndex?.format === "report_status_index_v1", "public/data/report_status_index.json format 必須是 report_status_index_v1");
  assert(Array.isArray(reportStatusIndex?.reports), "public/data/report_status_index.json 必須包含 reports");
  assert(reportStatusIndex?.report_count === reportStatusIndex?.reports?.length, "public/data/report_status_index.json report_count 必須等於 reports 長度");
  const normalizedReportStatusReports = Array.from(建立報告索引Map(reportStatusIndex).values());
  assert(
    normalizedReportStatusReports.every((report) => report.report_code && Array.isArray(report.fights) && Array.isArray(report.encounters)),
    "public/data/report_status_index.json 每筆 report 必須保留 fights 與 encounters 摘要",
  );
  assert(updateStatus?.format === "public_update_status_v1", "public/data/update_status.json format 必須是 public_update_status_v1");
  assert(Number.isFinite(updateStatus?.schedule?.interval_minutes), "public/data/update_status.json 必須公開排程摘要");
  assert(honeyFans?.schema_version === 1, "public/data/fun/honey_b_fans.json schema_version 必須是 1");
  assert(honeyFans?.feature === "honey_b_lovely_fans", "public/data/fun/honey_b_fans.json feature 必須是 honey_b_lovely_fans");
  assert(Array.isArray(honeyFans?.top_fans), "public/data/fun/honey_b_fans.json 必須包含 top_fans");
  assert(Array.isArray(honeyFans?.latest_records), "public/data/fun/honey_b_fans.json 必須包含 latest_records");
  assert(Array.isArray(honeyFans?.team_rankings), "public/data/fun/honey_b_fans.json 必須包含 team_rankings");
  assert((honeyFans?.latest_records || []).length <= 5, "public/data/fun/honey_b_fans.json latest_records 最多顯示 5 筆");
  assert((honeyFans?.latest_fans || []).length <= 16, "public/data/fun/honey_b_fans.json latest_fans 最多顯示 16 筆");
  assert(Number.isFinite(honeyFans?.summary?.leaderboard_window_days), "public/data/fun/honey_b_fans.json 必須標示粉絲榜榜單天數");
  assert(Number.isFinite(honeyFans?.summary?.historical_total_event_count), "public/data/fun/honey_b_fans.json 必須保留歷史粉絲紀錄總數");
  assert(Number.isFinite(honeyFans?.summary?.historical_team_record_count), "public/data/fun/honey_b_fans.json 必須保留歷史團隊榜場次");
  assert(Number.isFinite(honeyFans?.summary?.team_ranking_record_count), "public/data/fun/honey_b_fans.json 必須標示活動團隊榜場次");
  assert(Number.isFinite(honeyFans?.summary?.team_ranking_event_count), "public/data/fun/honey_b_fans.json 必須標示活動團隊榜事件數");
  assert(Number.isFinite(new Date(honeyFans?.summary?.team_ranking_window_start_at_iso).getTime()), "public/data/fun/honey_b_fans.json 必須標示活動團隊榜起始時間");
  for (const fan of honeyFans?.top_fans || []) {
    assert(Number.isFinite(fan?.current_streak_weeks), `${fan?.id || "未知粉絲"} 必須包含 current_streak_weeks`);
    assert(Number.isFinite(fan?.historical_total_event_count), `${fan?.id || "未知粉絲"} 必須包含 historical_total_event_count`);
  }
  const teamRankingStartAt = new Date(honeyFans?.summary?.team_ranking_window_start_at_iso).getTime();
  for (const teamRecord of honeyFans?.team_rankings || []) {
    assert(teamRecord?.fight_status === "kill", `${teamRecord?.id || "未知團隊紀錄"} 必須是通關場次`);
    assert(Number.isFinite(teamRecord?.total_event_count), `${teamRecord?.id || "未知團隊紀錄"} 必須包含 total_event_count`);
    assert(Array.isArray(teamRecord?.members), `${teamRecord?.id || "未知團隊紀錄"} 必須包含 members`);
    assert(
      new Date(teamRecord?.fight_completed_at_iso).getTime() >= teamRankingStartAt,
      `${teamRecord?.id || "未知團隊紀錄"} 必須落在活動團隊榜起始時間之後`,
    );
  }
  assert(Array.isArray(userIndex?.users) && userIndex.users.length > 0, "public/data/users/index.json 必須包含 users");
  assert(userIndex?.total_users === userIndex?.users?.length, "public/data/users/index.json total_users 必須等於 users 長度");
  const userDetailCache = new Map();
  const gameVersionsConfig = await readJson(path.join(rootDir, "config", "game_versions.json"), "config/game_versions.json");
  const gameVersions = Array.isArray(gameVersionsConfig?.versions)
    ? gameVersionsConfig.versions.map((version) => ({
      patch: String(version?.patch || "").trim(),
      label: String(version?.label || version?.patch || "").trim(),
      starts_at_iso: version?.starts_at_iso ?? null,
    }))
    : [];
  const gameVersionPatches = new Set(gameVersions.map((version) => version.patch));
  assert(gameVersions.length > 0 && gameVersions.every((version) => version.patch && version.label), "config/game_versions.json 必須提供完整的排行榜版本設定。");
  assert(
    expectedDefaultRankingGameVersion(gameVersions, Date.parse("2026-07-22T00:00:00+08:00")) === "7.15",
    "排行榜在 7.2 開放前必須預設選擇 7.15。",
  );
  assert(
    expectedDefaultRankingGameVersion(gameVersions, Date.parse("2026-07-28T13:00:00+08:00")) === "7.2",
    "排行榜在 7.2 開放時間起必須預設選擇 7.2。",
  );

  for (const encounter of encounters || []) {
    const key = encounter?.key;
    const dataPath = encounter?.data_path || `data/rankings/${key}.json`;
    const publicRankingPath = path.join(publicDataDir, dataPath.replace(/^data\//, ""));
    const rankingTablePath = path.join(publicDataDir, "ranking-tables", `${key}.json`);
    const rankingDetailPath = path.join(publicDataDir, "ranking-details", `${key}.json`);
    assert(Boolean(key), "public/data/encounters.json 的每筆副本都必須有 key");
    assert(existsSync(publicRankingPath), `${key} 的公開排行榜檔案不存在：${dataPath}`);
    const ranking = await readJson(publicRankingPath, `${key} 公開排行榜`);
    assert(ranking?.schema_version === 1, `${key} 公開排行榜 schema_version 必須是 1`);
    assert(Array.isArray(ranking?.ranking_entries), `${key} 公開排行榜必須包含 ranking_entries`);
    assert(!ranking?.reports && !ranking?.report_shards, `${key} 公開排行榜不可包含 reports 或 report_shards`);
    assert(!ranking?.version_ranking_entries, `${key} 公開排行榜不可再輸出紀錄時效的 version_ranking_entries`);
    if (encounter?.version_cutoff) {
      assert(ranking?.version_cutoff?.obsolete_after_iso, `${key} 公開排行榜必須保留 version_cutoff.obsolete_after_iso`);
      assert(
        ranking.ranking_entries.some((entry) => typeof entry.is_obsolete_record === "boolean"),
        `${key} 公開排行榜條目必須標記 is_obsolete_record`,
      );
    }

    assert(existsSync(rankingTablePath), `${key} 必須提供排行榜薄索引`);
    const table = await readJson(rankingTablePath, `${key} 排行榜薄索引`);
    assert(table?.format === "ranking_table_index_v1", `${key} 排行榜薄索引 format 必須正確`);
    assert(Array.isArray(table?.table_columns), `${key} 排行榜薄索引必須包含 table_columns`);
    assert(Array.isArray(table?.table_rows), `${key} 排行榜薄索引必須包含 table_rows`);
    assert(!table?.version_table_rows, `${key} 排行榜薄索引不可再複製紀錄時效的 version_table_rows`);
    assert(table.table_columns.includes("has_report_detail"), `${key} 排行榜薄索引必須標記可按需載入報告細節`);
    assert(table.table_columns.includes("game_version"), `${key} 排行榜薄索引必須標記每筆繁中服遊戲版本`);
    assert(
      JSON.stringify(table?.game_versions || []) === JSON.stringify(gameVersions),
      `${key} 排行榜薄索引的 game_versions 必須完全對齊 config/game_versions.json`,
    );
    const recordedAtIndex = table.table_columns.indexOf("recorded_at_iso");
    const gameVersionIndex = table.table_columns.indexOf("game_version");
    for (const row of table.table_rows || []) {
      const recordedAtIso = Array.isArray(row) ? row[recordedAtIndex] : row?.recorded_at_iso;
      const gameVersion = Array.isArray(row) ? row[gameVersionIndex] : row?.game_version;
      assert(
        gameVersionPatches.has(gameVersion) && gameVersion === expectedRankingGameVersion(recordedAtIso, gameVersions),
        `${key} 排行榜薄索引的 game_version 必須由 recorded_at_iso 正確推得。`,
      );
    }
    assert(table.detail_path === `data/ranking-details/${key}.json`, `${key} 排行榜薄索引 detail_path 必須指向報告細節檔`);
    assert(existsSync(rankingDetailPath), `${key} 必須提供排行榜報告細節檔`);
    const details = await readJson(rankingDetailPath, `${key} 排行榜報告細節`);
    assert(details?.format === "ranking_detail_entries_v1", `${key} 排行榜報告細節 format 必須正確`);
    assert(details?.entries && typeof details.entries === "object", `${key} 排行榜報告細節必須包含 entries 索引`);
  }

  for (const encounter of globalStats?.encounters || []) {
    if (!encounter?.version_cutoff) {
      continue;
    }
    for (const versionMode of ["all", "valid", "obsolete"]) {
      assert(
        encounter.version_slices?.[versionMode]?.version_mode === versionMode,
        `${encounter.encounter_key} 全服統計必須包含 version_slices.${versionMode}`,
      );
    }
  }

  for (const user of (userIndex?.users || []).slice(0, 20)) {
    const userPath = path.join(rootDir, "public", user.file_path || "");
    assert(existsSync(userPath), `使用者索引指向不存在的檔案：${user.file_path}`);
    const userData = await readJson(userPath, `使用者檔案 ${user.file_path}`);
    assert(userData?.schema_version === 1, `${user.file_path} schema_version 必須是 1`);
    assert(Array.isArray(userData?.servers), `${user.file_path} 必須包含 servers`);
    assert(Array.isArray(userData?.encounters), `${user.file_path} 必須包含 encounters`);
    assert(Array.isArray(userData?.frequent_teammates), `${user.file_path} 必須包含 frequent_teammates`);
    assert(userData?.summary && typeof userData.summary === "object", `${user.file_path} 必須包含 summary`);
  }

  for (const user of userIndex?.users || []) {
    const userPath = path.join(rootDir, "public", user.file_path || "");
    if (!existsSync(userPath)) {
      continue;
    }

    const userData = await readJson(userPath, `使用者檔案 ${user.file_path}`);
    for (const encounter of userData?.encounters || []) {
      const allEntries = [
        encounter?.best_entry,
        ...(encounter?.best_by_job || []),
        ...(encounter?.public_entries || []),
      ].filter(Boolean);
      for (const entry of allEntries) {
        const duplicateCount = Number(entry?.duplicate_count) || 0;
        const inlineVariants = Array.isArray(entry?.report_variants) ? entry.report_variants : [];
        if (duplicateCount <= 1 || inlineVariants.length > 1) {
          continue;
        }
        assert(Boolean(entry?.report_detail_path && entry?.report_detail_id), `${user.file_path} 的多來源成績必須保留 report_detail_path/report_detail_id`);
        if (!entry?.report_detail_path) {
          continue;
        }
        const detailPath = path.join(rootDir, "public", entry.report_detail_path);
        assert(existsSync(detailPath), `${user.file_path} 的個人成績報告細節檔不存在：${entry.report_detail_path}`);
        if (!userDetailCache.has(entry.report_detail_path) && existsSync(detailPath)) {
          userDetailCache.set(entry.report_detail_path, await readJson(detailPath, `個人成績報告細節 ${entry.report_detail_path}`));
        }
        const details = userDetailCache.get(entry.report_detail_path);
        assert(details?.format === "user_entry_details_v1", `${entry.report_detail_path} format 必須是 user_entry_details_v1`);
        assert(Boolean(details?.entries?.[entry.report_detail_id]), `${entry.report_detail_path} 必須包含 ${entry.report_detail_id}`);
      }

      if (!versionedEncounterKeys.has(encounter?.encounter_key)) {
        continue;
      }

      const entries = Array.isArray(encounter.public_entries) ? encounter.public_entries : [];
      const validEntries = entries.filter((entry) => !entry.is_obsolete_record);
      const obsoleteEntries = entries.filter((entry) => entry.is_obsolete_record);
      if (obsoleteEntries.length === 0) {
        continue;
      }

      for (const entry of obsoleteEntries) {
        assert(entry.rank === null && entry.job_rank === null, `${user.file_path} 的過版紀錄不可保留職業 Rank`);
        assert(entry.performance?.reason === "obsolete_record", `${user.file_path} 的過版紀錄同職分位必須標記 obsolete_record`);
      }

      if (validEntries.length > 0) {
        assert(encounter.best_entry && !encounter.best_entry.is_obsolete_record, `${user.file_path} 混合有效與過版紀錄時，最佳紀錄必須取有效版本`);
        assert(Number(encounter.best_entry?.job_rank) > 0, `${user.file_path} 的有效最佳紀錄必須有正數職業 Rank`);
      } else {
        assert(encounter.best_entry === null, `${user.file_path} 只有過版紀錄時不可標示最佳紀錄`);
      }
    }
  }
}

async function validateHiddenDeltaDataForFrontend() {
  const allDataDir = path.join(publicDataDir, "all");
  const allUserIndexPath = path.join(allDataDir, "users", "index.json");
  if (!existsSync(allUserIndexPath)) {
    return;
  }

  const useRankingAppSource = await readText(path.join(srcDir, "composables", "useRankingApp.js"));
  const rankingDataSource = await readText(path.join(srcDir, "composables", "rankingApp", "useRankingData.js"));
  const rankingPageSource = await readText(path.join(srcDir, "pages", "RankingPage.vue"));
  const userDataSource = await readText(path.join(srcDir, "utils", "userData.js"));
  assert(rankingDataSource.includes("ranking_table_hidden_delta_v1"), "前端排行榜讀取端必須支援 hidden delta 薄索引");
  assert(rankingDataSource.includes("ranking_detail_hidden_delta_v1"), "前端排行榜讀取端必須支援 hidden delta 報告細節");
  assert(rankingDataSource.includes("gameVersion: 條目.game_version"), "前端排行榜列必須保留薄索引的 game_version。");
  assert(
    rankingPageSource.includes('<col v-show="顯示版本紀錄" class="版本欄" />')
      && rankingPageSource.includes('<th v-show="顯示版本紀錄" scope="col">版本</th>')
      && rankingPageSource.includes('v-show="顯示版本紀錄" class="數字 排行榜版本欄">{{ 列.gameVersion || "—" }}</td>')
      && rankingPageSource.includes('<span v-show="顯示版本紀錄">\n                  <em>版本</em>'),
    "開啟版本紀錄時，排行榜桌面表格與手機排行卡都必須顯示每筆紀錄的遊戲版本。",
  );
  assert(!rankingDataSource.includes("version_table_rows"), "前端排行榜不可再讀取紀錄時效的 version_table_rows。");
  assert(
    useRankingAppSource.includes("紀錄符合排行榜遊戲版本")
      && useRankingAppSource.includes("顯示排行榜版本紀錄")
      && useRankingAppSource.includes("顯示排行榜紀錄時效"),
    "排行榜必須依共用偏好切換累積版本紀錄與紀錄時效模式。",
  );
  assert(
    useRankingAppSource.includes("const 排行榜版本範圍 = ref(預設版本紀錄範圍);")
      && useRankingAppSource.includes("紀錄符合版本範圍(")
      && useRankingAppSource.includes("{ is_obsolete_record: 列.過版紀錄 }"),
    "關閉版本紀錄後，排行榜必須以既有過版標記提供紀錄時效篩選。",
  );
  assert(
    useRankingAppSource.includes("gameVersion: 顯示排行榜版本紀錄.value ? 排行榜遊戲版本.value : \"\"")
      && useRankingAppSource.includes("version: !顯示排行榜版本紀錄.value && 顯示排行榜紀錄時效.value"),
    "排行榜分享網址必須只保留目前模式對應的版本條件。",
  );
  assert(useRankingAppSource.includes("排行榜版本早於副本開放"), "排行榜必須辨識早於副本開放版本的選擇。");
  assert(
    rankingPageSource.includes('v-if="顯示排行榜版本紀錄"')
      && rankingPageSource.includes('v-model="排行榜遊戲版本選取值"')
      && rankingPageSource.includes('v-if="顯示排行榜紀錄時效"')
      && rankingPageSource.includes('v-model="排行榜版本範圍"')
      && rankingPageSource.includes("<span>紀錄時效</span>"),
    "排行榜介面必須在開啟版本紀錄時顯示版本選單，關閉時改顯示紀錄時效。",
  );
  assert(rankingPageSource.includes("排行榜空狀態訊息"), "排行榜必須顯示早於副本開放版本的專屬提示。");
  assert(useRankingAppSource.includes("讀取個人成績報告詳細資料"), "前端個人成績單必須支援按需載入報告細節");
  assert(useRankingAppSource.includes("user_entry_details_v1"), "前端個人成績單必須辨識個人成績報告細節格式");
  assert(userDataSource.includes("user_profile_hidden_delta_v1"), "前端個人成績單讀取端必須支援 hidden delta");

  const allUserIndex = await readJson(allUserIndexPath, "public/data/all/users/index.json");
  const deltaUser = (allUserIndex?.users || []).find((user) => String(user?.file_path || "").startsWith("data/all/users/"));
  assert(deltaUser, "public/data/all/users/index.json 應至少包含一筆 hidden delta 使用者檔");
  if (deltaUser?.file_path) {
    const deltaPath = path.join(rootDir, "public", deltaUser.file_path);
    assert(existsSync(deltaPath), `hidden delta 使用者檔不存在：${deltaUser.file_path}`);
    const delta = await readJson(deltaPath, `hidden delta 使用者檔 ${deltaUser.file_path}`);
    assert(delta?.format === "user_profile_hidden_delta_v1", `${deltaUser.file_path} format 必須是 user_profile_hidden_delta_v1`);
    assert(delta?.base_path?.startsWith("data/users/"), `${deltaUser.file_path} 必須指回公開使用者底稿`);
    assert(existsSync(path.join(rootDir, "public", delta.base_path || "")), `${deltaUser.file_path} 指向的公開底稿不存在`);
  }

  const encounters = await readJson(path.join(publicDataDir, "encounters.json"), "public/data/encounters.json");
  for (const encounter of encounters || []) {
    const key = encounter?.key;
    if (!key) {
      continue;
    }
    const allRanking = await readJson(path.join(allDataDir, "rankings", `${key}.json`), `${key} hidden ranking delta`);
    const allTable = await readJson(path.join(allDataDir, "ranking-tables", `${key}.json`), `${key} hidden table delta`);
    const allDetails = await readJson(path.join(allDataDir, "ranking-details", `${key}.json`), `${key} hidden details delta`);
    assert(allRanking?.format === "ranking_hidden_delta_v1", `${key} hidden ranking delta format 必須正確`);
    assert(allRanking?.base_path === `data/rankings/${key}.json`, `${key} hidden ranking delta 必須指回公開排行榜`);
    assert(allTable?.format === "ranking_table_hidden_delta_v1", `${key} hidden table delta format 必須正確`);
    assert(allTable?.base_path === `data/ranking-tables/${key}.json`, `${key} hidden table delta 必須指回公開薄索引`);
    assert(allTable?.detail_path === `data/all/ranking-details/${key}.json`, `${key} hidden table delta 必須指向 hidden 報告細節`);
    assert(Array.isArray(allTable?.table_row_order), `${key} hidden table delta 必須保留完整排序 ID`);
    assert(allDetails?.format === "ranking_detail_hidden_delta_v1", `${key} hidden details delta format 必須正確`);
    assert(allDetails?.base_path === `data/ranking-details/${key}.json`, `${key} hidden details delta 必須指回公開報告細節`);
  }
}

function validateScopedJobShareRecalculation() {
  const source = {
    role_stats: [
      { role: "role:tank", role_name: "防護職業", clear_count: 3, percentage: 25 },
      { role: "role:healer", role_name: "治療職業", clear_count: 9, percentage: 75 },
    ],
    job_stats: [
      { job: "Paladin", role: "role:tank", role_name: "防護職業", clear_count: 3, percentage: 20 },
      { job: "Warrior", role: "role:tank", role_name: "防護職業", clear_count: 1, percentage: 6.67 },
      { job: "WhiteMage", role: "role:healer", role_name: "治療職業", clear_count: 8, percentage: 53.33 },
      { job: "Sage", role: "role:healer", role_name: "治療職業", clear_count: 1, percentage: 6.67 },
    ],
  };

  const allGroups = 建立職業佔比分組(source, "all");
  const allTankGroup = allGroups.find((group) => group.role === "role:tank");
  assert(allTankGroup?.percentage === 25, "全部職業範圍應沿用資料建置層已算好的職能佔比。");
  assert(
    allTankGroup?.jobs.find((job) => job.job === "Paladin")?.percentage === 20,
    "全部職業範圍應沿用資料建置層已算好的職業佔比。",
  );

  const tankGroups = 建立職業佔比分組(source, "role:tank");
  const tankGroup = tankGroups[0];
  assert(tankGroups.length === 1 && tankGroup?.role === "role:tank", "職能範圍應只顯示該職能的職業佔比群組。");
  assert(tankGroup?.percentage === 100, "職能範圍的群組佔比應以目前職能作為 100% 分母。");
  assert(
    tankGroup?.jobs.find((job) => job.job === "Paladin")?.percentage === 75,
    "職能範圍內的職業佔比應依該職能的職業紀錄總數重算。",
  );
  assert(
    tankGroup?.jobs.find((job) => job.job === "Warrior")?.percentage === 25,
    "職能範圍內的第二個職業也應依該職能分母重算。",
  );

  const paladinGroup = 建立職業佔比分組(source, "Paladin")[0];
  assert(paladinGroup?.percentage === 100, "單一職業範圍的群組佔比應以目前職業作為 100% 分母。");
  assert(paladinGroup?.jobs[0]?.percentage === 100, "單一職業範圍的職業佔比應顯示為 100%。");
}

function validateGlobalStatsOverviewDenominator() {
  const globalStats = {
    total_character_count: 10,
    total_encounter_clear_count: 25,
    role_stats: [{ role: "role:tank", role_name: "防護職業", clear_count: 6 }],
    job_stats: [{ job: "Paladin", role: "role:tank", role_name: "防護職業", clear_count: 4 }],
  };

  assert(
    取得統計範圍計數(globalStats, "all") === 10,
    "副本通關概覽在全服全職業範圍下，分母應使用全服公開玩家數，避免範圍佔比變成 0%。",
  );
  assert(取得統計範圍計數(globalStats, "role:tank") === 6, "職能範圍分母應使用該職能通關紀錄數。");
  assert(取得統計範圍計數(globalStats, "Paladin") === 4, "單一職業範圍分母應使用該職業通關紀錄數。");
  assert(
    取得統計範圍計數({ character_count: 3, clear_count: 2 }, "all") === 3,
    "單一副本統計仍應優先使用 character_count 作為通關玩家分母。",
  );
}

function validateAnnouncementRules() {
  const payload = {
    announcements: [
      {
        id: "always",
        title: "永久公告",
        summary: "沒有期限",
        details_markdown: "支援 **Markdown** 與 [連結](https://ranking.init.engineer)。",
        links: [{ label: "站台", url: "https://ranking.init.engineer" }],
      },
      {
        id: "future",
        title: "未來公告",
        summary: "尚未開始",
        details_markdown: "尚未開始前不可主動顯示。",
        starts_at_iso: "2026-06-01T00:00:00.000Z",
      },
      {
        id: "expired",
        title: "過期公告",
        summary: "已過期",
        details_markdown: "超過有效期限後不可主動顯示。",
        expires_at_iso: "2026-05-01T00:00:00.000Z",
      },
    ],
  };

  const announcements = 正規化公告資料(payload);
  const now = new Date("2026-05-24T00:00:00.000Z").getTime();
  assert(announcements.length === 3, "公告正規化應保留合法公告。");
  assert(取得公告狀態(announcements.find((item) => item.id === "always"), now) === "active", "未設定期限的公告應立即主動顯示。");
  assert(取得公告狀態(announcements.find((item) => item.id === "future"), now) === "scheduled", "未到 starts_at_iso 的公告不可主動顯示。");
  assert(取得公告狀態(announcements.find((item) => item.id === "expired"), now) === "expired", "超過 expires_at_iso 的公告不可主動顯示。");

  const activeIds = 取得主動公告列表(announcements, [], now).map((item) => item.id);
  assert(activeIds.length === 1 && activeIds[0] === "always", "主動公告列表只應包含生效且未關閉的公告。");
  assert(取得主動公告列表(announcements, ["always"], now).length === 0, "已關閉公告不應再次主動顯示。");

  const storage = {
    value: "",
    getItem() {
      return this.value;
    },
    setItem(_key, value) {
      this.value = value;
    },
  };
  寫入已關閉公告(new Set(["always"]), storage);
  assert(讀取已關閉公告(storage).has("always"), "公告關閉狀態應可寫入並從 localStorage 還原。");

  const blocks = 解析公告Markdown(payload.announcements[0].details_markdown);
  assert(blocks.some((block) => block.parts?.some((part) => part.type === "strong")), "公告詳細內容應解析 Markdown 粗體。");
  assert(blocks.some((block) => block.parts?.some((part) => part.type === "link")), "公告詳細內容應解析 Markdown 連結。");
}

async function loadUrlStateTestModule({ honeyFansEnabled = true } = {}) {
  const filePath = path.join(srcDir, "utils", "urlState.js");
  let source = await readText(filePath);
  const importMatch = source.match(/import\s*\{\s*([^}]+?)\s*\}\s*from\s*["']\.\/shareMeta(?:\.js)?["'];\r?\n/);
  const siteFeaturesImportMatch = source.match(/import\s*\{\s*[^}]*顯示Honey粉絲榜[^}]*\}\s*from\s*["']\.\/siteFeatures(?:\.js)?["'];\r?\n/);
  const exportedFunctions = [...source.matchAll(/export function\s+([^\s(]+)\s*\(/g)].map((match) => match[1]);

  assert(Boolean(importMatch), "urlState.js 必須明確匯入分享網址變更事件，讓網址寫入後可同步 SEO/OG meta");
  assert(Boolean(siteFeaturesImportMatch), "urlState.js 必須明確匯入 Honey B. Lovely 功能旗標，讓分享網址與舊路由可分開控管");
  assert(exportedFunctions.length >= 2, "urlState.js 必須匯出讀取與寫入網址狀態函式");
  if (!importMatch || !siteFeaturesImportMatch || exportedFunctions.length < 2) {
    return null;
  }

  const importedEventName = importMatch[1].trim();
  source = source.replace(importMatch[0], 'const shareUrlChangeEvent = "ffxivtc:urlchange";\n');
  source = source.replace(siteFeaturesImportMatch[0], `const 顯示Honey粉絲榜 = ${honeyFansEnabled ? "true" : "false"};\n`);
  source = source.split(importedEventName).join("shareUrlChangeEvent");
  source = source.replace(/export const /g, "const ");
  source = source.replace(/export function /g, "function ");
  source += `\nexport { ${exportedFunctions[0]} as readState, ${exportedFunctions[1]} as writeState };\n`;

  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;
  return import(moduleUrl);
}

async function loadUserDataTestModule() {
  const filePath = path.join(srcDir, "utils", "userData.js");
  let source = await readText(filePath);
  source = source.replace(
    /import\s*\{[\s\S]*?\}\s*from\s*["']\.\/publicData(?:\.js)?["'];/,
    `
const 建立使用者資料網址 = (相對路徑) => \`/mock/\${String(相對路徑)}\`;
const 建立使用者資料網址列表 = (相對路徑) => [\`/mock/\${String(相對路徑)}\`, \`/fallback/\${String(相對路徑)}\`];
const 建立使用者預設資料網址 = (角色名稱) => \`/mock/data/users/\${String(角色名稱)}.json\`;
const 建立使用者預設資料網址列表 = (角色名稱) => [\`/mock/data/users/\${String(角色名稱)}.json\`, \`/fallback/data/users/\${String(角色名稱)}.json\`];
`,
  );

  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;
  return import(moduleUrl);
}

async function loadPublicDataTestModule(href, basePath = "./") {
  globalThis.window = {
    location: new URL(href),
  };

  const filePath = path.join(srcDir, "utils", "publicData.js");
  const source = (await readText(filePath))
    .replace(/import\.meta\.env\?\.BASE_URL/g, JSON.stringify(basePath))
    .replace(
      /import\s*\{[\s\S]*?\}\s*from\s*["']\.\/siteFeatures(?:\.js)?["'];?/,
      "const 顯示Honey粉絲榜 = true;\n",
    );
  const cacheKey = Buffer.from(`${href}|${basePath}`, "utf8").toString("base64url");
  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}#${cacheKey}`;
  return import(moduleUrl);
}

async function validateUserSearchResolution() {
  const module = await loadUserDataTestModule();
  const users = [
    {
      character_name: "Shibe柴",
      canonical_server: "利維坦",
      servers: ["利維坦"],
      server_aliases: [],
      file_path: "data/users/Shibe柴.json",
    },
    {
      character_name: "Shibe柴",
      canonical_server: "巴哈姆特",
      servers: ["巴哈姆特"],
      server_aliases: [],
      file_path: "data/users/Shibe柴-2.json",
    },
  ];

  const pureNameTarget = module.解析使用者搜尋目標("Shibe柴", users);
  assert(pureNameTarget.角色名稱 === "Shibe柴", "純玩家名稱搜尋應解析到索引中的正式玩家名稱");
  assert(pureNameTarget.伺服器 === "利維坦", "純玩家名稱搜尋應由使用者索引補上主要伺服器");
  assert(
    module.格式化使用者搜尋文字(pureNameTarget.角色名稱, pureNameTarget.伺服器) === "Shibe柴 @ 利維坦",
    "純玩家名稱搜尋成功後應能正規化為「玩家 @ 伺服器」格式",
  );

  const formattedTarget = module.解析使用者搜尋目標("Shibe柴 @ 利維坦", users);
  assert(formattedTarget.角色名稱 === "Shibe柴" && formattedTarget.伺服器 === "利維坦", "已含伺服器的搜尋文字仍應解析成功");
  const compactTarget = module.解析使用者搜尋目標("Shibe柴@利維坦", users);
  assert(compactTarget.角色名稱 === "Shibe柴" && compactTarget.伺服器 === "利維坦", "沒有空白的玩家伺服器格式仍應解析成功");
  const sameNameTarget = module.解析使用者搜尋目標("Shibe柴 @ 巴哈姆特", users);
  assert(
    sameNameTarget.角色名稱 === "Shibe柴" && sameNameTarget.伺服器 === "巴哈姆特",
    "同名跨服查詢應保留使用者指定的伺服器身分。",
  );
  assert(module.取得使用者主要伺服器(users[0]) === "利維坦", "使用者工具應優先回傳 canonical_server。");
  const serverList = module.取得使用者伺服器列表(users[0]);
  assert(
    serverList.length === 1 && serverList[0] === "利維坦",
    "使用者工具不應把另一個同名角色所在伺服器列為查詢 alias。",
  );

  const indexEntry = module.尋找使用者索引條目(users, "shibe柴");
  assert(indexEntry?.file_path === "data/users/Shibe柴.json", "使用者索引查找應支援純玩家名稱大小寫差異");
  const sameNameEntry = module.尋找使用者索引條目(users, "Shibe柴", "巴哈姆特");
  assert(sameNameEntry?.file_path === "data/users/Shibe柴-2.json", "使用者索引查找應支援同名角色用伺服器拆分。");
  const missingServerTarget = module.解析使用者搜尋目標("Shibe柴 @ 奧汀", users);
  assert(
    missingServerTarget.伺服器 === "奧汀" && !missingServerTarget.索引條目,
    "指定伺服器沒有索引命中時，搜尋目標仍應保留使用者輸入的伺服器。",
  );

  const originalFetch = globalThis.fetch;
  let fetchedUrl = "";
  globalThis.fetch = async (url) => {
    fetchedUrl = String(url);
    return {
      ok: true,
      async json() {
        return {};
      },
    };
  };
  try {
    await module.讀取使用者資料檔("Shibe柴", users, "巴哈姆特");
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert(fetchedUrl === "/mock/data/users/Shibe柴-2.json", "讀取使用者資料檔應保留伺服器條件，避免同名角色讀到第一筆索引。");

  const fallbackFetchedUrls = [];
  globalThis.fetch = async (url) => {
    fallbackFetchedUrls.push(String(url));
    if (fallbackFetchedUrls.length === 1) {
      return {
        ok: false,
        status: 429,
      };
    }
    return {
      ok: true,
      async json() {
        return { fallback_loaded: true };
      },
    };
  };
  let fallbackData = null;
  try {
    fallbackData = await module.讀取使用者資料檔("Shibe柴", users, "巴哈姆特");
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert(fallbackData?.fallback_loaded === true, "個別玩家成績單遇到 raw GitHub 429 時，應改讀備援靜態資料來源。");
  assert(
    fallbackFetchedUrls.join("|") === "/mock/data/users/Shibe柴-2.json|/fallback/data/users/Shibe柴-2.json",
    "個別玩家成績單備援讀取應沿用同一個索引 file_path，避免同名跨服角色讀錯檔案。",
  );

  const notFoundFetchedUrls = [];
  let notFoundError = "";
  globalThis.fetch = async (url) => {
    notFoundFetchedUrls.push(String(url));
    return {
      ok: false,
      status: 404,
    };
  };
  try {
    await module.讀取使用者資料檔("Shibe柴", users, "巴哈姆特");
  } catch (error) {
    notFoundError = error instanceof Error ? error.message : String(error);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert(notFoundFetchedUrls.length === 1, "個別玩家成績單 404 應視為檔案不存在，不應再嘗試其它鏡像。");
  assert(
    notFoundError === "找不到「Shibe柴 @ 巴哈姆特」的個人成績單",
    "個別玩家成績單 404 應維持找不到訊息，避免遮蔽真正的資料缺口。",
  );

  const rateLimitedFetchedUrls = [];
  let rateLimitedError = "";
  globalThis.fetch = async (url) => {
    rateLimitedFetchedUrls.push(String(url));
    return {
      ok: false,
      status: 429,
    };
  };
  try {
    await module.讀取使用者資料檔("Shibe柴", users, "巴哈姆特");
  } catch (error) {
    rateLimitedError = error instanceof Error ? error.message : String(error);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert(rateLimitedFetchedUrls.length === 2, "所有個人成績單靜態來源都被限流前，應先完整嘗試可用備援。");
  assert(
    rateLimitedError.startsWith("暫時無法讀取") && rateLimitedError.includes("HTTP 429"),
    "所有靜態來源都回 429 時，搜尋錯誤應說明是暫時限流，而不是玩家不存在。",
  );

  const fallbackUnsyncedFetchedUrls = [];
  let fallbackUnsyncedError = "";
  globalThis.fetch = async (url) => {
    fallbackUnsyncedFetchedUrls.push(String(url));
    return {
      ok: false,
      status: fallbackUnsyncedFetchedUrls.length === 1 ? 429 : 404,
    };
  };
  try {
    await module.讀取使用者資料檔("Shibe柴", users, "巴哈姆特");
  } catch (error) {
    fallbackUnsyncedError = error instanceof Error ? error.message : String(error);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert(fallbackUnsyncedFetchedUrls.length === 2, "raw GitHub 429 後應嘗試備援來源，即使備援來源尚未同步該檔案。");
  assert(
    fallbackUnsyncedError.startsWith("暫時無法讀取") && fallbackUnsyncedError.includes("HTTP 429"),
    "raw GitHub 429 且備援來源 404 時，錯誤仍應維持暫時限流，不應改成找不到玩家。",
  );

  let missingServerError = "";
  let missingServerFetchCalled = false;
  globalThis.fetch = async () => {
    missingServerFetchCalled = true;
    return {
      ok: true,
      async json() {
        return {};
      },
    };
  };
  try {
    await module.讀取使用者資料檔("Shibe柴", users, "奧汀");
  } catch (error) {
    missingServerError = error instanceof Error ? error.message : String(error);
  } finally {
    globalThis.fetch = originalFetch;
  }
  assert(!missingServerFetchCalled, "指定伺服器沒有索引命中時，不應退回純玩家名稱檔案。");
  assert(
    missingServerError === "找不到「Shibe柴 @ 奧汀」的個人成績單",
    "指定伺服器搜尋失敗時，錯誤訊息應保留完整「玩家 @ 伺服器」查詢。",
  );

  const storage = {
    value: "",
    getItem() {
      return this.value;
    },
    setItem(_key, value) {
      this.value = value;
    },
  };
  let history = module.新增玩家搜尋歷史({ character_name: "乾太", server: "奧汀" }, storage, "2026-05-23T01:00:00.000Z");
  history = module.新增玩家搜尋歷史("Shibe柴 @ 利維坦", storage, "2026-05-23T02:00:00.000Z");
  history = module.新增玩家搜尋歷史({ character_name: "乾太", server: "奧汀" }, storage, "2026-05-23T03:00:00.000Z");

  assert(history.length === 2, "玩家搜尋歷史應以玩家與伺服器去重。");
  assert(history[0]?.value === "乾太 @ 奧汀", "重複搜尋的玩家應移到最近搜尋最前面。");
  assert(history[0]?.searched_at_iso === "2026-05-23T03:00:00.000Z", "重複搜尋的玩家應更新搜尋時間。");
  assert(module.讀取玩家搜尋歷史(storage)[1]?.value === "Shibe柴 @ 利維坦", "玩家搜尋歷史應可從 localStorage 格式還原。");

  history = module.刪除玩家搜尋歷史({ character_name: "乾太", server: "奧汀" }, storage);
  assert(history.length === 1 && history[0]?.value === "Shibe柴 @ 利維坦", "玩家搜尋歷史應支援單筆刪除。");
  history = module.清除玩家搜尋歷史(storage);
  assert(history.length === 0 && module.讀取玩家搜尋歷史(storage).length === 0, "玩家搜尋歷史應支援全部清除。");

  assert(module.玩家搜尋歷史顯示上限 === 8, "玩家搜尋下拉清單應最多顯示 8 筆。");
  assert(module.玩家搜尋歷史保存上限 === 100, "玩家搜尋歷程編輯清單應最多保存 100 筆。");
  const manyUsers = Array.from({ length: 120 }, (_item, index) => ({ character_name: `玩家${index}`, server: "奧汀" }));
  const limitedHistory = module.正規化玩家搜尋歷史列表(manyUsers);
  assert(limitedHistory.length === 100, "玩家搜尋歷史最多只應保存 100 筆。");
  assert(module.正規化玩家搜尋歷史列表(["", { server: "奧汀" }]).length === 0, "玩家搜尋歷史不應保存空白玩家名稱。");
}

async function validatePublicDataRouteBase() {
  const directUserRoute = await loadPublicDataTestModule("https://ranking.init.engineer/user/");
  assert(
    directUserRoute.副本清單網址 === "/data/encounters.json",
    "直接開啟 /user/ 時，公開資料應讀取部署根目錄的 /data/encounters.json。",
  );
  assert(
    directUserRoute.使用者索引網址 === "/data/users/index.json",
    "個人成績單索引是所有訪客共用的高頻入口，預設應由主站 /data/users/index.json 載入以套用 CDN 快取。",
  );
  assert(
    directUserRoute.建立使用者資料網址("data/users/篝之霧枝-2.json") ===
      "https://raw.githubusercontent.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users/refs/heads/main/data/users/%E7%AF%9D%E4%B9%8B%E9%9C%A7%E6%9E%9D-2.json",
    "直接開啟 /user/ 時，個別玩家成績單檔案仍應由專用 users repo 載入。",
  );
  const userDataUrls = directUserRoute.建立使用者資料網址列表("data/users/篝之霧枝-2.json");
  assert(
    userDataUrls[0] ===
      "https://raw.githubusercontent.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users/refs/heads/main/data/users/%E7%AF%9D%E4%B9%8B%E9%9C%A7%E6%9E%9D-2.json" &&
      userDataUrls[1] ===
        "https://cdn.jsdelivr.net/gh/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users@main/data/users/%E7%AF%9D%E4%B9%8B%E9%9C%A7%E6%9E%9D-2.json",
    "個別玩家成績單應保留 raw GitHub 主來源，並提供 jsDelivr CDN 作為限流備援。",
  );

  const subpathRoute = await loadPublicDataTestModule("https://example.test/repo/user/Aa?server=%E5%A5%A7%E6%B1%80");
  assert(
    subpathRoute.副本清單網址 === "/repo/data/encounters.json",
    "子路徑部署直接開啟 /repo/user/{玩家} 時，公開資料 URL 應保留 /repo/ 部署基底。",
  );
  assert(
    subpathRoute.使用者索引網址 === "/repo/data/users/index.json",
    "子路徑部署直接開啟 /repo/user/{玩家} 時，個人成績單索引也應保留 /repo/ 部署基底。",
  );

  const configuredBase = await loadPublicDataTestModule("https://example.test/user/", "/custom/");
  assert(
    configuredBase.副本清單網址 === "/custom/data/encounters.json",
    "Vite base_path 已指定絕對路徑時，公開資料 URL 應優先使用設定值。",
  );

  const directFaqRoute = await loadPublicDataTestModule("https://ranking.init.engineer/faq");
  assert(
    directFaqRoute.報告狀態索引網址 === "/data/report_status_index.json",
    "直接開啟 /faq 時，Logs 狀態索引應讀取部署根目錄的 /data/report_status_index.json。",
  );

  const directLogsRoute = await loadPublicDataTestModule("https://ranking.init.engineer/logs");
  assert(
    directLogsRoute.報告狀態索引網址 === "/data/report_status_index.json",
    "直接開啟舊版 /logs 時，Logs 狀態索引仍應讀取部署根目錄的 /data/report_status_index.json。",
  );

  delete globalThis.window;
}

function validateReportStatusUrlParsing() {
  const hashFight = 解析Fflogs網址("https://www.fflogs.com/reports/BAgFha92HkfQ4vKP#fight=15&type=damage-done");
  assert(hashFight.valid && hashFight.report_code === "BAgFha92HkfQ4vKP", "Logs 檢查應能解析 hash fight 格式的 FFLogs 網址。");
  assert(hashFight.fight_id === 15, "Logs 檢查應能解析 hash 中的 fight id。");

  const queryFight = 解析Fflogs網址("https://www.fflogs.com/reports/a:BAgFha92HkfQ4vKP?fight=last");
  assert(queryFight.valid && queryFight.report_code === "BAgFha92HkfQ4vKP", "Logs 檢查應支援 FFLogs a: report code 格式。");
  assert(queryFight.fight_id === null && queryFight.fight_text === "last", "fight=last 不應被誤判為數字 fight。");

  const pureCode = 解析Fflogs網址("BAgFha92HkfQ4vKP");
  assert(pureCode.valid && pureCode.normalized_url.endsWith("/BAgFha92HkfQ4vKP"), "Logs 檢查應支援只貼 report code。");

  const invalidHost = 解析Fflogs網址("https://example.test/reports/BAgFha92HkfQ4vKP");
  assert(!invalidHost.valid && invalidHost.error.includes("fflogs.com"), "Logs 檢查應拒絕非 FFLogs 網址。");

  const lookalikeHost = 解析Fflogs網址("https://evilfflogs.com/reports/BAgFha92HkfQ4vKP");
  assert(!lookalikeHost.valid, "Logs 檢查不可接受只是字尾相同的非 FFLogs 主機。");
}

function validateFflogsLiveStatusDisplay() {
  const endpoint = 取得Fflogs即時狀態查詢網址();
  assert(endpoint.includes("script.google.com/macros/s/"), "FFLogs 即時狀態查詢應有 Apps Script Web App 預設網址。");

  const publicStatus = 建立Fflogs即時狀態顯示({
    ok: true,
    fflogs_access: "accessible",
    visibility: "public",
    archive_accessible: true,
  });
  assert(publicStatus.status === "public", "FFLogs 即時狀態應把 accessible + public 顯示為公開。");
  assert(publicStatus.title.includes("公開"), "公開 report 的即時狀態標題應明確告知公開。");
  assert(Fflogs目前公開可讀({
    ok: true,
    fflogs_access: "accessible",
    visibility: "public",
  }), "只有 accessible + public 可送出一般待收錄需求。");

  const privateStatus = 建立Fflogs即時狀態顯示({
    ok: true,
    fflogs_access: "private_or_deleted",
  });
  assert(privateStatus.status === "private", "FFLogs 即時狀態應把 private_or_deleted 顯示為不可公開讀取。");
  assert(privateStatus.description.includes("Private"), "不可讀 report 應保留 Private 作為常見原因。");
  assert(Fflogs目前明確不可公開({
    ok: true,
    fflogs_access: "private_or_deleted",
  }), "private_or_deleted 可觸發已收錄 report 的公開狀態重新排查。");

  const unlistedStatus = 建立Fflogs即時狀態顯示({
    ok: true,
    fflogs_access: "accessible",
    visibility: "unlisted",
  });
  assert(unlistedStatus.status === "private", "非 Public visibility 不可顯示為公開可讀。");
  assert(Fflogs目前明確不可公開({
    ok: true,
    fflogs_access: "accessible",
    visibility: "unlisted",
  }), "可讀但非 Public 的 report 也可觸發公開狀態重新排查。");
  assert(!Fflogs目前明確不可公開({
    ok: true,
    fflogs_access: "accessible",
  }), "缺少 visibility 的可讀結果不能直接視為隱藏依據。");

  const configErrorStatus = 建立Fflogs即時狀態顯示({
    ok: false,
    error_code: "server_config_error",
  });
  assert(configErrorStatus.status === "error", "即時查詢服務設定錯誤應顯示為查詢錯誤。");
  assert(configErrorStatus.description.includes("即時查詢服務"), "即時查詢服務設定錯誤應顯示使用者可理解的提示。");
}

function validateReportStatusScheduleParsing() {
  const halfHourlySchedule = {
    schedule: {
      workflow_cron_utc: "17,47 * * * *",
      interval_minutes: 30,
    },
  };
  const hint = 建立未收錄提示(halfHourlySchedule, new Date("2026-07-07T10:20:00.000Z"));
  assert(hint.next_run_at_iso === "2026-07-07T10:47:00.000Z", "17,47 cron 應推算同小時第 47 分為下一輪排程。");
  assert(hint.next_run_wait_text === "約 27 分鐘", "17,47 cron 的等待時間應依下一個觸發分鐘計算。");
  assert(hint.notes[0].includes("每 30 分鐘排程"), "未收錄提示應顯示目前 workflow 的 30 分鐘排程頻率。");

  const afterSecondRun = 取得下一輪排程時間(new Date("2026-07-07T10:48:00.000Z"), [17, 47]);
  assert(afterSecondRun.toISOString() === "2026-07-07T11:17:00.000Z", "超過第 47 分後應推到下一小時第 17 分。");

  const stepScheduleHint = 建立未收錄提示(
    { schedule: { workflow_cron_utc: "*/30 * * * *", interval_minutes: 30 } },
    new Date("2026-07-07T10:20:00.000Z"),
  );
  assert(stepScheduleHint.next_run_at_iso === "2026-07-07T10:30:00.000Z", "*/30 cron 應支援推算下一個半小時排程。");
}

function installUrlStateWindow(href, events) {
  globalThis.CustomEvent = class CustomEvent {
    constructor(type) {
      this.type = type;
    }
  };
  globalThis.window = {
    location: new URL(href),
    history: {
      replaceState(_state, _title, nextUrl) {
        globalThis.window.location = new URL(nextUrl, globalThis.window.location.href);
      },
      pushState(_state, _title, nextUrl) {
        globalThis.window.location = new URL(nextUrl, globalThis.window.location.href);
      },
    },
    dispatchEvent(event) {
      events.push(event.type);
    },
  };
}

function validateReportExternalLinks() {
  const links = buildReportExternalLinks({
    report_code: "BAgFha92HkfQ4vKP",
    fight_id: 15,
    fflogs_source_id: 26,
  });
  const linksByKey = new Map(links.map((link) => [link.key, link.url]));
  const labelsByKey = new Map(links.map((link) => [link.key, link.label]));

  assert(
    linksByKey.get("fflogs") === "https://www.fflogs.com/reports/BAgFha92HkfQ4vKP?fight=15",
    "報告工具連結應把 FFLogs 指到實際通關 fight。",
  );
  assert(
    linksByKey.get("xivanalysis") === "https://xivanalysis.com/fflogs/BAgFha92HkfQ4vKP/15/26",
    "報告工具連結應用 FFLogs sourceID 組出 xivanalysis 玩家深連結。",
  );
  assert(labelsByKey.get("xivanalysis") === "XIV Analysis", "報告工具連結應顯示 XIV Analysis。");
  assert(
    linksByKey.get("ffreplay") ===
      "https://ffreplay.vjoi.cn/ffreplay.html?url=https%3A%2F%2Fwww.fflogs.com%2Freports%2FBAgFha92HkfQ4vKP%3Ffight%3D15",
    "報告工具連結應把含 fight 的 FFLogs URL 編碼後交給 ffreplay。",
  );
  assert(labelsByKey.get("ffreplay") === "FF Repley", "報告工具連結應顯示 FF Repley。");

  const teamLinks = buildReportExternalLinks({
    report_code: "BAgFha92HkfQ4vKP",
    fight_id: 15,
  });
  const teamLinksByKey = new Map(teamLinks.map((link) => [link.key, link.url]));
  assert(
    teamLinksByKey.get("xivanalysis") === "https://xivanalysis.com/fflogs/BAgFha92HkfQ4vKP/15",
    "隊伍榜報告工具連結不帶 FFLogs sourceID 時，XIV Analysis 應只指到 fight 場次頁。",
  );
}

async function validateShareUrlStateCompatibility() {
  const module = await loadUrlStateTestModule();
  if (!module) {
    return;
  }

  const cases = [
    {
      label: "舊版個人成績單 query",
      href: "https://ranking.init.engineer/?user=Aa&server=%E5%A5%A7%E6%B1%80",
      expected: { page: "user", user: "Aa", server: "奧汀" },
    },
    {
      label: "個人成績單乾淨路徑",
      href: "https://ranking.init.engineer/user/Aa?server=%E5%A5%A7%E6%B1%80",
      expected: { page: "user", user: "Aa", server: "奧汀" },
    },
    {
      label: "副本全服統計乾淨路徑",
      href: "https://ranking.init.engineer/stats/savage_m1s?server=%E9%B3%B3%E5%87%B0&metric=rdps&version=valid",
      expected: { page: "stats", encounter: "savage_m1s", server: "鳳凰", metric: "rdps", version: "valid" },
    },
    {
      label: "排行榜累積版本紀錄 query",
      href: "https://ranking.init.engineer/?encounter=savage_m1s&gameVersion=7.1",
      expected: { page: "ranking", encounter: "savage_m1s", gameVersion: "7.1" },
    },
    {
      label: "排行榜紀錄時效 query",
      href: "https://ranking.init.engineer/?encounter=savage_m1s&version=obsolete",
      expected: { page: "ranking", encounter: "savage_m1s", version: "obsolete" },
    },
    {
      label: "玩家比較版本 query",
      href: "https://ranking.init.engineer/compare?left=Aa&right=Bb&encounter=extreme_zoraal_ja&version=obsolete",
      expected: { page: "compare", left: "Aa", right: "Bb", encounter: "extreme_zoraal_ja", version: "obsolete" },
    },
    {
      label: "隊伍榜版本 query",
      href: "https://ranking.init.engineer/teams?encounter=extreme_valigarmanda&version=valid",
      expected: { page: "teams", encounter: "extreme_valigarmanda", version: "valid" },
    },
    {
      label: "職業分析乾淨路徑",
      href: "https://ranking.init.engineer/jobs/Paladin",
      expected: { page: "jobs", job: "Paladin" },
    },
    {
      label: "職業分析職能 query",
      href: "https://ranking.init.engineer/jobs?jobScope=role%3Atank",
      expected: { page: "jobs", jobScope: "role:tank" },
    },
    {
      label: "伺服器對比乾淨路徑",
      href: "https://ranking.init.engineer/servers/%E9%B3%B3%E5%87%B0/vs/%E4%BC%8A%E5%BC%97%E5%88%A9%E7%89%B9",
      expected: { page: "servers", left: "鳳凰", right: "伊弗利特" },
    },
    {
      label: "舊版伺服器對比 query",
      href: "https://ranking.init.engineer/servers?left=%E9%B3%B3%E5%87%B0&right=%E4%BC%8A%E5%BC%97%E5%88%A9%E7%89%B9",
      expected: { page: "servers", left: "鳳凰", right: "伊弗利特" },
    },
    {
      label: "Honey B. Lovely 粉絲榜乾淨路徑",
      href: "https://ranking.init.engineer/honey-fans",
      expected: { page: "honey-fans" },
    },
    {
      label: "常見問題乾淨路徑",
      href: "https://ranking.init.engineer/faq",
      expected: { page: "faq" },
    },
    {
      label: "舊版 Logs 檢查乾淨路徑",
      href: "https://ranking.init.engineer/logs",
      expected: { page: "faq" },
    },
  ];

  const events = [];
  for (const testCase of cases) {
    installUrlStateWindow(testCase.href, events);
    const state = module.readState();
    for (const [key, value] of Object.entries(testCase.expected)) {
      assert(state[key] === value, `${testCase.label} 解析失敗：${key} 應為 ${value}，實際為 ${state[key]}`);
    }
  }

  const disabledHoneyModule = await loadUrlStateTestModule({ honeyFansEnabled: false });
  installUrlStateWindow("https://ranking.init.engineer/honey-fans", events);
  const disabledHoneyState = disabledHoneyModule?.readState();
  assert(
    disabledHoneyState?.page === "honey-fans",
    "Honey B. Lovely 關閉時仍應辨識 /honey-fans 舊路由，讓 app 層能 replace 回排行榜",
  );

  installUrlStateWindow("https://example.test/repo/stats/savage_m1s?server=x", events);
  module.writeState({ page: "jobs", job: "Paladin" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://example.test/repo/jobs/Paladin",
    "子路徑部署下從 /stats/{副本} 寫入 /jobs/{職業} 時，必須保留部署基底路徑",
  );
  assert(events.includes("ffxivtc:urlchange"), "寫入分享網址後必須送出自訂事件，讓 SEO/OG meta 同步更新");

  installUrlStateWindow("https://example.test/repo/jobs/Paladin", events);
  module.writeState({ page: "jobs", jobScope: "role:tank" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://example.test/repo/jobs?jobScope=role%3Atank",
    "職業分析寫入職能範圍時，應保留 /jobs 路徑並以 jobScope query 表示職能",
  );

  installUrlStateWindow("https://ranking.init.engineer/?encounter=savage_m1s&version=valid", events);
  module.writeState({ page: "ranking", encounter: "extreme_zoraal_ja", gameVersion: "7.1" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/?encounter=extreme_zoraal_ja&gameVersion=7.1",
    "排行榜處於版本紀錄模式時，分享網址必須只保留累積版本紀錄 query。",
  );

  installUrlStateWindow("https://ranking.init.engineer/?encounter=savage_m1s&gameVersion=7.1", events);
  module.writeState({ page: "ranking", encounter: "extreme_zoraal_ja", version: "obsolete" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/?encounter=extreme_zoraal_ja&version=obsolete",
    "排行榜處於紀錄時效模式時，分享網址必須只保留 version query。",
  );

  installUrlStateWindow("https://ranking.init.engineer/?encounter=savage_m1s&server=%E9%B3%B3%E5%87%B0&jobType=role%3Ahealer&job=WhiteMage", events);
  module.writeState(
    { page: "ranking", encounter: "savage_m2s", server: "鳳凰", jobType: "role:healer", job: "WhiteMage" },
    { replace: true },
  );
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/?encounter=savage_m2s&server=%E9%B3%B3%E5%87%B0&jobType=role%3Ahealer&job=WhiteMage",
    "排行榜切換副本後的分享網址必須保留伺服器與職業篩選 query",
  );

  installUrlStateWindow("https://ranking.init.engineer/stats/savage_m1s?server=%E9%B3%B3%E5%87%B0&jobScope=WhiteMage", events);
  module.writeState({ page: "stats", encounter: "savage_m2s", server: "鳳凰", jobScope: "WhiteMage" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/stats/savage_m2s?server=%E9%B3%B3%E5%87%B0&jobScope=WhiteMage",
    "全服統計切換副本後的分享網址必須保留伺服器與職業範圍 query",
  );

  installUrlStateWindow("https://ranking.init.engineer/servers?left=a&right=b", events);
  module.writeState({ page: "servers", left: "鳳凰", right: "伊弗利特" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/servers/%E9%B3%B3%E5%87%B0/vs/%E4%BC%8A%E5%BC%97%E5%88%A9%E7%89%B9",
    "伺服器對比分享網址必須寫成 /servers/{left}/vs/{right}",
  );

  installUrlStateWindow("https://ranking.init.engineer/activity", events);
  module.writeState({ page: "faq" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://ranking.init.engineer/faq",
    "常見問題分享網址必須寫成 /faq",
  );

  installUrlStateWindow("https://ranking.init.engineer/activity", events);
  module.writeState({ page: "logs" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://ranking.init.engineer/faq",
    "舊版 logs 狀態寫入分享網址時應正規化為 /faq",
  );

  installUrlStateWindow("https://ranking.init.engineer/activity", events);
  module.writeState({ page: "honey-fans" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://ranking.init.engineer/honey-fans",
    "Honey B. Lovely 粉絲榜分享網址必須寫成 /honey-fans",
  );

  delete globalThis.window;
  delete globalThis.CustomEvent;
}

async function main() {
  await validateUseRankingAppReturnBindings();
  await validateFrontendFetchBoundary();
  await validateStaticSeoBuildOptions();
  await validateSiteFeatureFlags();
  validateRankingDefaults();
  validatePercentileDisplayFormatting();
  validateUserProfilePercentileSorting();
  validateUserProfileBadges();
  await validateUserProfileBadgeDataScope();
  await validateUserProfileGameVersionFilter();
  await validateHelpTooltipPreference();
  validateUserProfileGameVersionFallback();
  validateUserProfileClearSummary();
  await validateSavageProfileSummaryPresentation();
  await validateUserProfileSummaryJobFilter();
  await validateMobileProfileSummaryLayout();
  await validateMobileUserSearchFormLayout();
  validateGcdCoverageDiagnosticFields();
  validateJobIconCacheKeys();
  await validateEncounterSwitchFilterPersistence();
  await validatePublicDataForFrontend();
  await validateHiddenDeltaDataForFrontend();
  validateReportExternalLinks();
  validateReportStatusUrlParsing();
  validateFflogsLiveStatusDisplay();
  validateReportStatusScheduleParsing();
  validateScopedJobShareRecalculation();
  validateGlobalStatsOverviewDenominator();
  validateAnnouncementRules();
  await validateUserSearchResolution();
  await validatePublicDataRouteBase();
  await validateShareUrlStateCompatibility();

  if (issues.length > 0) {
    console.error(`前端資料契約測試失敗：${issues.length} 個問題`);
    for (const issue of issues) {
      console.error(`- ${issue}`);
    }
    process.exit(1);
  }

  console.log("frontend data contract test passed.");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
