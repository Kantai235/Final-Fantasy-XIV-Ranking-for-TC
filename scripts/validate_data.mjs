import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicAllDataDir = path.join(publicDataDir, "all");
const sourceRankingsDir = path.join(rootDir, "data", "rankings");
const publicRankingsDir = path.join(publicDataDir, "rankings");
const publicRankingTablesDir = path.join(publicDataDir, "ranking-tables");
const publicRankingDetailsDir = path.join(publicDataDir, "ranking-details");
const publicAllRankingsDir = path.join(publicAllDataDir, "rankings");
const publicAllRankingTablesDir = path.join(publicAllDataDir, "ranking-tables");
const publicAllRankingDetailsDir = path.join(publicAllDataDir, "ranking-details");
const rawFieldNames = new Set(["fflogs_raw", "master_data", "matched_players"]);

const issues = [];
let checkedSourceReports = 0;
let checkedUserFiles = 0;
let checkedActivityItems = 0;
let checkedTeamRecords = 0;
let checkedServerCompareRows = 0;

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

function isFiniteNumber(value) {
  return Number.isFinite(Number(value));
}

function isObjectRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value);
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

    const tablePath = path.join(publicRankingTablesDir, `${key}.json`);
    const detailPath = path.join(publicRankingDetailsDir, `${key}.json`);
    if (!existsSync(tablePath)) {
      reportIssue(`${key} 缺少排行榜薄索引：public/data/ranking-tables/${key}.json`);
    } else {
      const table = await readJson(tablePath, `${key} 排行榜薄索引`);
      if (table?.format !== "ranking_table_index_v1") {
        reportIssue(`${key} 排行榜薄索引 format 必須是 ranking_table_index_v1`);
      }
      if (!Array.isArray(table?.table_columns) || !Array.isArray(table?.table_rows)) {
        reportIssue(`${key} 排行榜薄索引必須包含 table_columns 與 table_rows`);
      }
      if (table?.detail_path !== `data/ranking-details/${key}.json`) {
        reportIssue(`${key} 排行榜薄索引 detail_path 不正確`);
      }
      if (table?.table_rows?.length !== publicRanking?.ranking_entries?.length) {
        reportIssue(`${key} 排行榜薄索引列數需等於公開 ranking_entries`);
      }
    }
    if (!existsSync(detailPath)) {
      reportIssue(`${key} 缺少排行榜報告細節檔：public/data/ranking-details/${key}.json`);
    } else {
      const details = await readJson(detailPath, `${key} 排行榜報告細節`);
      if (details?.format !== "ranking_detail_entries_v1") {
        reportIssue(`${key} 排行榜報告細節 format 必須是 ranking_detail_entries_v1`);
      }
      if (!details?.entries || typeof details.entries !== "object" || Array.isArray(details.entries)) {
        reportIssue(`${key} 排行榜報告細節必須包含 entries 索引物件`);
      }
    }

    const allRankingPath = path.join(publicAllRankingsDir, `${key}.json`);
    if (!existsSync(allRankingPath)) {
      reportIssue(`${key} 缺少完整排行榜鏡像：public/data/all/rankings/${key}.json`);
    } else {
      const allRanking = await readJson(allRankingPath, `${key} 完整排行榜鏡像`);
      if (!hasRankingData(allRanking)) {
        reportIssue(`${key} 完整排行榜鏡像缺少 ranking_entries`);
      }
      if (allRanking?.hidden_reports_included !== true) {
        reportIssue(`${key} 完整排行榜鏡像必須標記 hidden_reports_included=true`);
      }
      if (allRanking?.reports || allRanking?.report_shards) {
        reportIssue(`${key} 完整排行榜鏡像不應包含完整 reports 或 report_shards`);
      }
    }

    const allTablePath = path.join(publicAllRankingTablesDir, `${key}.json`);
    const allDetailPath = path.join(publicAllRankingDetailsDir, `${key}.json`);
    if (!existsSync(allTablePath)) {
      reportIssue(`${key} 缺少完整鏡像排行榜薄索引：public/data/all/ranking-tables/${key}.json`);
    } else {
      const allTable = await readJson(allTablePath, `${key} 完整鏡像排行榜薄索引`);
      if (allTable?.hidden_reports_included !== true) {
        reportIssue(`${key} 完整鏡像排行榜薄索引必須標記 hidden_reports_included=true`);
      }
      if (allTable?.detail_path !== `data/all/ranking-details/${key}.json`) {
        reportIssue(`${key} 完整鏡像排行榜薄索引 detail_path 不正確`);
      }
    }
    if (!existsSync(allDetailPath)) {
      reportIssue(`${key} 缺少完整鏡像排行榜報告細節檔：public/data/all/ranking-details/${key}.json`);
    } else {
      const allDetails = await readJson(allDetailPath, `${key} 完整鏡像排行榜報告細節`);
      if (allDetails?.format !== "ranking_detail_entries_v1") {
        reportIssue(`${key} 完整鏡像排行榜報告細節 format 必須是 ranking_detail_entries_v1`);
      }
      if (!allDetails?.entries || typeof allDetails.entries !== "object" || Array.isArray(allDetails.entries)) {
        reportIssue(`${key} 完整鏡像排行榜報告細節必須包含 entries 索引物件`);
      }
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

async function validateActivity() {
  const activityPath = path.join(publicDataDir, "activity.json");
  if (!existsSync(activityPath)) {
    reportIssue("缺少 public/data/activity.json，請先執行 npm run build:user-data");
    return;
  }

  const activity = await readJson(activityPath, "public/data/activity.json");
  if (activity?.schema_version !== 1) {
    reportIssue("public/data/activity.json 的 schema_version 必須是 1");
  }
  if (!isObjectRecord(activity?.summary)) {
    reportIssue("public/data/activity.json 缺少 summary");
  }
  if (!isFiniteNumber(activity?.summary?.recent_entry_count)) {
    reportIssue("public/data/activity.json 缺少 summary.recent_entry_count");
  }

  const listNames = ["recent_entries", "personal_bests", "new_characters", "server_activity", "encounter_activity"];
  for (const listName of listNames) {
    if (!Array.isArray(activity?.[listName])) {
      reportIssue(`public/data/activity.json 的 ${listName} 必須是陣列`);
      continue;
    }
    checkedActivityItems += activity[listName].length;
  }

  for (const entry of activity?.recent_entries || []) {
    if (!entry?.character_name || !entry?.server || !entry?.encounter_key || !entry?.job) {
      reportIssue("public/data/activity.json 的 recent_entries 有條目缺少角色、伺服器、副本或職業");
      break;
    }
  }
}

function isOptionalIsoTimestamp(value) {
  if (value === null || value === undefined || value === "") {
    return true;
  }
  return Number.isFinite(new Date(value).getTime());
}

function validateAnnouncementLinks(links, label) {
  if (links === undefined) {
    return;
  }
  if (!Array.isArray(links)) {
    reportIssue(`${label} 的 links 必須是陣列`);
    return;
  }

  for (const [index, link] of links.entries()) {
    if (!link?.label || !link?.url) {
      reportIssue(`${label} 的 links[${index}] 必須包含 label 與 url`);
      continue;
    }

    try {
      const url = new URL(link.url, "https://ranking.init.engineer");
      if (!["http:", "https:", "mailto:"].includes(url.protocol)) {
        reportIssue(`${label} 的 links[${index}] 使用不允許的連結協定：${url.protocol}`);
      }
    } catch (error) {
      reportIssue(`${label} 的 links[${index}] 不是有效 URL：${error.message}`);
    }
  }
}

function validateAnnouncementPayload(payload, label) {
  if (payload?.schema_version !== 1) {
    reportIssue(`${label} 的 schema_version 必須是 1`);
  }
  if (!Array.isArray(payload?.announcements)) {
    reportIssue(`${label} 必須包含 announcements 陣列`);
    return;
  }

  ensureUniqueKeys(payload.announcements, "id", `${label} announcements`);
  for (const announcement of payload.announcements) {
    const announcementLabel = `${label} 公告 ${announcement?.id || "(缺少 id)"}`;
    if (!announcement?.title || !announcement?.summary || !announcement?.details_markdown) {
      reportIssue(`${announcementLabel} 必須包含 title、summary 與 details_markdown`);
    }
    if (!isOptionalIsoTimestamp(announcement?.starts_at_iso)) {
      reportIssue(`${announcementLabel} 的 starts_at_iso 必須是有效 ISO 時間或空值`);
    }
    if (!isOptionalIsoTimestamp(announcement?.expires_at_iso)) {
      reportIssue(`${announcementLabel} 的 expires_at_iso 必須是有效 ISO 時間或空值`);
    }

    const startsAt = announcement?.starts_at_iso ? new Date(announcement.starts_at_iso).getTime() : null;
    const expiresAt = announcement?.expires_at_iso ? new Date(announcement.expires_at_iso).getTime() : null;
    if (Number.isFinite(startsAt) && Number.isFinite(expiresAt) && expiresAt < startsAt) {
      reportIssue(`${announcementLabel} 的 expires_at_iso 不可早於 starts_at_iso`);
    }

    validateAnnouncementLinks(announcement?.links, announcementLabel);
  }
}

async function validateAnnouncements() {
  const announcementsPath = path.join(publicDataDir, "announcements.json");
  const announcementsMirrorPath = path.join(publicAllDataDir, "announcements.json");
  if (!existsSync(announcementsPath)) {
    reportIssue("缺少 public/data/announcements.json");
    return;
  }

  const announcements = await readJson(announcementsPath, "public/data/announcements.json");
  validateAnnouncementPayload(announcements, "public/data/announcements.json");

  if (existsSync(announcementsMirrorPath)) {
    const mirror = await readJson(announcementsMirrorPath, "public/data/all/announcements.json");
    validateAnnouncementPayload(mirror, "public/data/all/announcements.json");
    if (JSON.stringify(announcements) !== JSON.stringify(mirror)) {
      reportIssue("public/data/all/announcements.json 必須與 public/data/announcements.json 同步");
    }
  }
}

async function validateTeamRankings() {
  const teamRankingsPath = path.join(publicDataDir, "team_rankings.json");
  if (!existsSync(teamRankingsPath)) {
    reportIssue("缺少 public/data/team_rankings.json，請先執行 npm run build:user-data");
    return;
  }

  const teamRankings = await readJson(teamRankingsPath, "public/data/team_rankings.json");
  if (teamRankings?.schema_version !== 1) {
    reportIssue("public/data/team_rankings.json 的 schema_version 必須是 1");
  }
  if (!Array.isArray(teamRankings?.encounters)) {
    reportIssue("public/data/team_rankings.json 的 encounters 必須是陣列");
    return;
  }
  if (!Array.isArray(teamRankings?.overall_fastest)) {
    reportIssue("public/data/team_rankings.json 的 overall_fastest 必須是陣列");
  }
  if (teamRankings?.encounter_count !== teamRankings.encounters.length) {
    reportIssue(`public/data/team_rankings.json 的 encounter_count=${teamRankings?.encounter_count} 與 encounters 長度 ${teamRankings.encounters.length} 不一致`);
  }

  ensureUniqueKeys(teamRankings.encounters, "encounter_key", "public/data/team_rankings.json encounters");
  const totalRecordCount = teamRankings.encounters.reduce((sum, encounter) => sum + (Number(encounter?.record_count) || 0), 0);
  if (teamRankings?.total_team_record_count !== totalRecordCount) {
    reportIssue(`public/data/team_rankings.json 的 total_team_record_count=${teamRankings?.total_team_record_count} 與副本紀錄總數 ${totalRecordCount} 不一致`);
  }

  for (const encounter of teamRankings.encounters) {
    if (!Array.isArray(encounter?.records)) {
      reportIssue(`隊伍榜副本 ${encounter?.encounter_key || "(未知)"} 的 records 必須是陣列`);
      continue;
    }
    if ((Number(encounter.record_count) || 0) < encounter.records.length) {
      reportIssue(`隊伍榜副本 ${encounter.encounter_key} 的 record_count 小於 records 長度`);
    }

    for (const record of encounter.records) {
      checkedTeamRecords += 1;
      if (!record?.id || !isFiniteNumber(record?.clear_time_seconds)) {
        reportIssue(`隊伍榜副本 ${encounter.encounter_key} 有紀錄缺少 id 或 clear_time_seconds`);
        continue;
      }
      if (!Array.isArray(record.players) || record.players.length !== 8) {
        reportIssue(`隊伍榜紀錄 ${record.id} 的 players 必須剛好是 8 人`);
        continue;
      }
      if (record.players.some((player) => !player?.character_name || !player?.server || !player?.job)) {
        reportIssue(`隊伍榜紀錄 ${record.id} 有隊員缺少角色、伺服器或職業`);
      }
    }
  }
}

async function validateServerCompare() {
  const serverComparePath = path.join(publicDataDir, "server_compare.json");
  if (!existsSync(serverComparePath)) {
    reportIssue("缺少 public/data/server_compare.json，請先執行 npm run build:user-data");
    return;
  }

  const serverCompare = await readJson(serverComparePath, "public/data/server_compare.json");
  if (serverCompare?.schema_version !== 1) {
    reportIssue("public/data/server_compare.json 的 schema_version 必須是 1");
  }
  if (!isObjectRecord(serverCompare?.summary)) {
    reportIssue("public/data/server_compare.json 缺少 summary");
  }
  if (!Array.isArray(serverCompare?.servers)) {
    reportIssue("public/data/server_compare.json 的 servers 必須是陣列");
    return;
  }
  if (serverCompare?.summary?.server_count !== serverCompare.servers.length) {
    reportIssue(`public/data/server_compare.json 的 summary.server_count=${serverCompare?.summary?.server_count} 與 servers 長度 ${serverCompare.servers.length} 不一致`);
  }

  ensureUniqueKeys(serverCompare.servers, "server", "public/data/server_compare.json servers");
  for (const server of serverCompare.servers) {
    checkedServerCompareRows += 1;
    if (!server?.server || !isFiniteNumber(server?.unique_player_count) || !isFiniteNumber(server?.encounter_clear_count)) {
      reportIssue("public/data/server_compare.json 有伺服器缺少 server、unique_player_count 或 encounter_clear_count");
      continue;
    }
    if (!Array.isArray(server.role_stats) || !Array.isArray(server.job_stats) || !Array.isArray(server.encounters)) {
      reportIssue(`伺服器對比 ${server.server} 缺少 role_stats、job_stats 或 encounters 陣列`);
    }
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

async function validateAllDataMirror() {
  const requiredMirrorFiles = [
    "announcements.json",
    "encounters.json",
    "global_stats.json",
    "activity.json",
    "team_rankings.json",
    "server_compare.json",
    "users/index.json",
  ];

  for (const relativePath of requiredMirrorFiles) {
    const mirrorPath = path.join(publicAllDataDir, relativePath);
    if (!existsSync(mirrorPath)) {
      reportIssue(`缺少完整資料鏡像：public/data/all/${normalizePath(relativePath)}`);
      continue;
    }
    await readJson(mirrorPath, `public/data/all/${normalizePath(relativePath)}`);
  }
}

async function main() {
  const publicEncounters = await validateEncounters();
  await validateRankings(publicEncounters);
  await validateGlobalStats();
  await validateActivity();
  await validateAnnouncements();
  await validateTeamRankings();
  await validateServerCompare();
  await validateUsers();
  await validateAllDataMirror();

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
    `資料驗證通過：${publicEncounters.length} 個公開副本、${checkedSourceReports} 份來源 report、${checkedUserFiles} 份使用者檔案、${checkedActivityItems} 筆近期動態項目、${checkedTeamRecords} 筆隊伍榜紀錄、${checkedServerCompareRows} 筆伺服器對比資料。`,
  );
}

main().catch((error) => {
  console.error(`資料驗證失敗：${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
