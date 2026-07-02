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
import { publicDataContracts, validateSchemaContract } from "../schemas/public_data_contracts.mjs";
import { 建立職業佔比分組, 取得統計範圍計數 } from "../src/utils/statsDisplay.js";
import {
  分位顯示模式PR,
  分位顯示模式前段,
  取得PR色彩類別,
  格式化同職分位,
  格式化排名分位,
} from "../src/utils/formatters.js";
import {
  個人成績代表是否較佳,
  比較個人成績分位顯示排序,
} from "../src/utils/userProfileSorting.js";
import { 建立報告索引Map, 解析Fflogs網址 } from "../src/utils/reportStatus.js";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(rootDir, "src");
const publicDataDir = path.join(rootDir, "public", "data");

const issues = [];

function reportIssue(message) {
  issues.push(message);
}

async function readText(filePath) {
  return readFile(filePath, "utf8");
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

function validatePercentileDisplayFormatting() {
  const performance = {
    qualified: true,
    active_threshold: 90,
    sample_count: 100,
    rank: 6,
    top_percent: 6,
    score_percentile: 95.4,
  };

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
      calculation_version: 5,
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
  const rankingWatcher = extractSourceSection(source, "watch(副本鍵值", "watch(排行榜版本範圍", "排行榜副本切換 watcher");
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

async function validatePublicDataForFrontend() {
  const encounters = await readJson(path.join(publicDataDir, "encounters.json"), "public/data/encounters.json");
  const announcements = await readJson(path.join(publicDataDir, "announcements.json"), "public/data/announcements.json");
  const globalStats = await readJson(path.join(publicDataDir, "global_stats.json"), "public/data/global_stats.json");
  const serverCompare = await readJson(path.join(publicDataDir, "server_compare.json"), "public/data/server_compare.json");
  const reportStatusIndex = await readJson(path.join(publicDataDir, "report_status_index.json"), "public/data/report_status_index.json");
  const updateStatus = await readJson(path.join(publicDataDir, "update_status.json"), "public/data/update_status.json");
  const honeyFans = await readJson(path.join(publicDataDir, "fun", "honey_b_fans.json"), "public/data/fun/honey_b_fans.json");
  const userIndex = await readJson(path.join(publicDataDir, "users", "index.json"), "public/data/users/index.json");
  const versionedEncounterKeys = new Set((encounters || []).filter((encounter) => encounter?.version_cutoff).map((encounter) => encounter.key));

  assert(Array.isArray(encounters) && encounters.length > 0, "public/data/encounters.json 必須提供前端副本清單");
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
    if (encounter?.version_cutoff) {
      assert(ranking?.version_cutoff?.obsolete_after_iso, `${key} 公開排行榜必須保留 version_cutoff.obsolete_after_iso`);
      for (const versionMode of ["all", "valid", "obsolete"]) {
        assert(
          Array.isArray(ranking?.version_ranking_entries?.[versionMode]),
          `${key} 公開排行榜必須包含 version_ranking_entries.${versionMode}`,
        );
      }
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
    assert(table.table_columns.includes("has_report_detail"), `${key} 排行榜薄索引必須標記可按需載入報告細節`);
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
  const userDataSource = await readText(path.join(srcDir, "utils", "userData.js"));
  assert(rankingDataSource.includes("ranking_table_hidden_delta_v1"), "前端排行榜讀取端必須支援 hidden delta 薄索引");
  assert(rankingDataSource.includes("ranking_detail_hidden_delta_v1"), "前端排行榜讀取端必須支援 hidden delta 報告細節");
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
const 建立使用者預設資料網址 = (角色名稱) => \`/mock/data/users/\${String(角色名稱)}.json\`;
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
    directUserRoute.使用者索引網址 ===
      "https://raw.githubusercontent.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users/refs/heads/main/data/users/index.json",
    "個人成績單索引預設應由專用 users repo 載入，避免主站 Pages artifact 重新放回大型使用者 JSON。",
  );
  assert(
    directUserRoute.建立使用者資料網址("data/users/篝之霧枝-2.json") ===
      "https://raw.githubusercontent.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users/refs/heads/main/data/users/%E7%AF%9D%E4%B9%8B%E9%9C%A7%E6%9E%9D-2.json",
    "直接開啟 /user/ 時，個人成績單檔案也應由專用 users repo 載入。",
  );

  const subpathRoute = await loadPublicDataTestModule("https://example.test/repo/user/Aa?server=%E5%A5%A7%E6%B1%80");
  assert(
    subpathRoute.副本清單網址 === "/repo/data/encounters.json",
    "子路徑部署直接開啟 /repo/user/{玩家} 時，公開資料 URL 應保留 /repo/ 部署基底。",
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
  module.writeState({ page: "ranking", encounter: "extreme_zoraal_ja", version: "obsolete" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/?encounter=extreme_zoraal_ja&version=obsolete",
    "排行榜分享網址必須保留版本篩選 query",
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
  validatePercentileDisplayFormatting();
  validateUserProfilePercentileSorting();
  validateGcdCoverageDiagnosticFields();
  validateJobIconCacheKeys();
  await validateEncounterSwitchFilterPersistence();
  await validatePublicDataForFrontend();
  await validateHiddenDeltaDataForFrontend();
  validateReportExternalLinks();
  validateReportStatusUrlParsing();
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
