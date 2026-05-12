import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const sourceRankingsDir = path.join(rootDir, "data", "rankings");
const publicRankingsDir = path.join(publicDataDir, "rankings");
const rawFieldNames = new Set(["fflogs_raw", "master_data", "matched_players"]);

const issues = [];
let checkedSourceReports = 0;
let checkedUserFiles = 0;

function reportIssue(message) {
  issues.push(message);
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

function assertInside(parent, target, label) {
  const relative = path.relative(parent, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    reportIssue(`${label} 指向允許目錄外：${normalizePath(path.relative(rootDir, target))}`);
    return false;
  }
  return true;
}

async function readJson(filePath, label) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    reportIssue(`${label} 不是可讀取的 JSON：${error.message}`);
    return null;
  }
}

function ensureUniqueKeys(items, keyName, label) {
  const seen = new Set();
  for (const item of items) {
    const key = item?.[keyName];
    if (!key) {
      reportIssue(`${label} 有條目缺少 ${keyName}`);
      continue;
    }
    if (seen.has(key)) {
      reportIssue(`${label} 出現重複 ${keyName}：${key}`);
    }
    seen.add(key);
  }
}

function hasRankingData(ranking) {
  return Array.isArray(ranking?.ranking_entries) || Array.isArray(ranking?.report_shards) || ranking?.reports;
}

async function loadSourceReports(ranking, rankingLabel) {
  const reports = {};
  if (ranking?.reports && typeof ranking.reports === "object" && !Array.isArray(ranking.reports)) {
    Object.assign(reports, ranking.reports);
  }

  for (const shardPathText of ranking?.report_shards || []) {
    if (typeof shardPathText !== "string" || !shardPathText) {
      reportIssue(`${rankingLabel} 的 report_shards 含有無效路徑`);
      continue;
    }

    const shardPath = path.resolve(rootDir, shardPathText);
    if (!assertInside(sourceRankingsDir, shardPath, `${rankingLabel} 分片`)) {
      continue;
    }
    if (!existsSync(shardPath)) {
      reportIssue(`${rankingLabel} 分片不存在：${normalizePath(shardPathText)}`);
      continue;
    }

    const shard = await readJson(shardPath, `${rankingLabel} 分片 ${normalizePath(shardPathText)}`);
    if (shard && typeof shard === "object" && !Array.isArray(shard)) {
      Object.assign(reports, shard);
    } else {
      reportIssue(`${rankingLabel} 分片必須是 report code 索引物件：${normalizePath(shardPathText)}`);
    }
  }

  return reports;
}

function checkNoRawFields(value, label, depth = 0) {
  if (!value || typeof value !== "object") {
    return;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      checkNoRawFields(item, label, depth + 1);
    }
    return;
  }

  for (const key of Object.keys(value)) {
    if (rawFieldNames.has(key)) {
      reportIssue(`${label} 仍包含可重查的大型 raw 欄位：${key}`);
      return;
    }
  }

  // report/fight/player 樹狀資料可能很大；找到 raw 欄位後立刻回報即可，不需要收集每個重複位置。
  for (const child of Object.values(value)) {
    if (depth > 8) {
      continue;
    }
    checkNoRawFields(child, label, depth + 1);
    if (issues.some((issue) => issue.startsWith(label) && issue.includes("raw 欄位"))) {
      return;
    }
  }
}

async function validateEncounters() {
  const configPath = path.join(rootDir, "config", "encounters.json");
  const publicPath = path.join(publicDataDir, "encounters.json");
  const configEncounters = await readJson(configPath, "config/encounters.json");
  const publicEncounters = await readJson(publicPath, "public/data/encounters.json");

  if (!Array.isArray(configEncounters)) {
    reportIssue("config/encounters.json 必須是陣列");
  } else {
    ensureUniqueKeys(configEncounters, "key", "config/encounters.json");
  }

  if (!Array.isArray(publicEncounters)) {
    reportIssue("public/data/encounters.json 必須是陣列");
    return [];
  }

  ensureUniqueKeys(publicEncounters, "key", "public/data/encounters.json");
  return publicEncounters;
}

async function validateRankings(publicEncounters) {
  for (const encounter of publicEncounters) {
    const key = encounter?.key;
    if (!key) {
      continue;
    }

    const dataPathText = encounter.data_path || `data/rankings/${key}.json`;
    const publicRankingPath = path.resolve(publicDataDir, dataPathText.replace(/^data\//, ""));
    if (!assertInside(publicRankingsDir, publicRankingPath, `${key} 公開排行榜`)) {
      continue;
    }
    if (!existsSync(publicRankingPath)) {
      reportIssue(`${key} 已列在 public/data/encounters.json，但缺少公開排行榜：${dataPathText}`);
      continue;
    }

    const publicRanking = await readJson(publicRankingPath, `${key} 公開排行榜`);
    if (!hasRankingData(publicRanking)) {
      reportIssue(`${key} 公開排行榜缺少 ranking_entries 或 reports`);
    }
    if (publicRanking?.reports || publicRanking?.report_shards) {
      reportIssue(`${key} 公開排行榜不應包含完整 reports 或 report_shards`);
    }

    const sourceRankingPath = path.join(sourceRankingsDir, `${key}.json`);
    if (!existsSync(sourceRankingPath)) {
      reportIssue(`${key} 缺少來源排行榜：data/rankings/${key}.json`);
      continue;
    }

    const sourceRanking = await readJson(sourceRankingPath, `${key} 來源排行榜`);
    if (!hasRankingData(sourceRanking)) {
      reportIssue(`${key} 來源排行榜缺少 ranking_entries、report_shards 或 reports`);
      continue;
    }

    const sourceReports = await loadSourceReports(sourceRanking, key);
    for (const [reportCode, report] of Object.entries(sourceReports)) {
      checkedSourceReports += 1;
      checkNoRawFields(report, `${key}/${reportCode}`);
    }
  }
}

async function validateGlobalStats() {
  const globalStatsPath = path.join(publicDataDir, "global_stats.json");
  if (!existsSync(globalStatsPath)) {
    reportIssue("缺少 public/data/global_stats.json");
    return;
  }

  const stats = await readJson(globalStatsPath, "public/data/global_stats.json");
  if (stats?.schema_version !== 1) {
    reportIssue("public/data/global_stats.json 的 schema_version 必須是 1");
  }
  if (!Number.isFinite(Number(stats?.total_character_count))) {
    reportIssue("public/data/global_stats.json 缺少 total_character_count");
  }
}

async function validateUsers() {
  const usersDir = path.join(publicDataDir, "users");
  const userIndexPath = path.join(usersDir, "index.json");
  if (!existsSync(userIndexPath)) {
    reportIssue("缺少 public/data/users/index.json，請先執行 npm run build:user-data");
    return;
  }

  const index = await readJson(userIndexPath, "public/data/users/index.json");
  const users = Array.isArray(index?.users) ? index.users : [];
  if (index?.total_users !== users.length) {
    reportIssue(`public/data/users/index.json 的 total_users=${index?.total_users} 與 users 長度 ${users.length} 不一致`);
  }

  for (const user of users) {
    const filePathText = user?.file_path;
    if (typeof filePathText !== "string" || !filePathText) {
      reportIssue(`使用者索引 ${user?.character_name || "(未知)"} 缺少 file_path`);
      continue;
    }

    const userPath = path.resolve(publicDataDir, filePathText.replace(/^data\//, ""));
    if (!assertInside(usersDir, userPath, `使用者索引 ${user?.character_name || filePathText}`)) {
      continue;
    }
    if (!existsSync(userPath)) {
      reportIssue(`使用者索引指向不存在檔案：${filePathText}`);
      continue;
    }
    checkedUserFiles += 1;
  }
}

async function main() {
  const publicEncounters = await validateEncounters();
  await validateRankings(publicEncounters);
  await validateGlobalStats();
  await validateUsers();

  if (issues.length > 0) {
    console.error(`資料驗證失敗：${issues.length} 個問題`);
    for (const issue of issues.slice(0, 50)) {
      console.error(`- ${issue}`);
    }
    if (issues.length > 50) {
      console.error(`...還有 ${issues.length - 50} 個問題`);
    }
    process.exit(1);
  }

  console.log(
    `資料驗證通過：${publicEncounters.length} 個公開副本、${checkedSourceReports} 份來源 report、${checkedUserFiles} 份使用者檔案。`,
  );
}

main().catch((error) => {
  console.error(`資料驗證失敗：${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
