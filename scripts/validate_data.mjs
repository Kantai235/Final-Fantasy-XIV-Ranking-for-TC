import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { publicDataContracts, validateSchemaContract } from "../schemas/public_data_contracts.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicAllDataDir = path.join(publicDataDir, "all");
const sourceRankingsDir = path.join(rootDir, "data", "rankings");
const publicRankingsDir = path.join(publicDataDir, "rankings");
const publicRankingTablesDir = path.join(publicDataDir, "ranking-tables");
const publicRankingDetailsDir = path.join(publicDataDir, "ranking-details");
const publicUserEntryDetailsDir = path.join(publicDataDir, "user-entry-details");
const publicAllRankingsDir = path.join(publicAllDataDir, "rankings");
const publicAllRankingTablesDir = path.join(publicAllDataDir, "ranking-tables");
const publicAllRankingDetailsDir = path.join(publicAllDataDir, "ranking-details");
const publicAllUserEntryDetailsDir = path.join(publicAllDataDir, "user-entry-details");
const rawFieldNames = new Set(["fflogs_raw", "master_data", "matched_players"]);
const rawFieldPattern = new RegExp(`"(${[...rawFieldNames].join("|")})"\\s*:`);
const 個人成績簡表遊戲版本順序 = ["7.0", "7.05", "7.1", "7.15", "7.2"];
const 個人成績簡表遊戲版本 = new Set(個人成績簡表遊戲版本順序);
const 個人成績簡表遊戲版本索引 = new Map(個人成績簡表遊戲版本順序.map((version, index) => [version, index]));

const issues = [];
let checkedSourceReports = 0;
let checkedUserFiles = 0;
let checkedActivityItems = 0;
let checkedTeamRecords = 0;
let checkedServerCompareRows = 0;
let checkedUserEntryDetails = 0;
let checkedHoneyFanRows = 0;
let checkedReportStatusRows = 0;

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

function rawFieldFromJsonText(jsonText) {
  const match = jsonText.match(rawFieldPattern);
  return match ? match[1] : null;
}

function parseJsonText(jsonText, label) {
  try {
    return JSON.parse(jsonText);
  } catch (error) {
    reportIssue(`${label} 不是可讀取的 JSON：${error.message}`);
    return null;
  }
}

async function readJsonAndCheckNoRawFields(filePath, label) {
  let jsonText;
  try {
    jsonText = await readFile(filePath, "utf8");
  } catch (error) {
    reportIssue(`${label} 不是可讀取的 JSON：${error.message}`);
    return null;
  }

  const rawField = rawFieldFromJsonText(jsonText);
  if (rawField) {
    reportIssue(`${label} 仍包含可重查的大型 raw 欄位：${rawField}`);
  }
  return parseJsonText(jsonText, label);
}

function validateContract(value, schema, label) {
  for (const issue of validateSchemaContract(value, schema, label)) {
    reportIssue(issue);
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

function collectProfileSummarySavageTiers(encounters, label) {
  const tiersByEncounter = new Map();
  const tiersByKey = new Map();
  const tierKeysByOrder = new Map();
  const floors = new Set();

  for (const encounter of Array.isArray(encounters) ? encounters : []) {
    if (encounter?.category !== "零式") {
      continue;
    }

    const tier = encounter?.profile_summary_savage_tier;
    const encounterLabel = `${label} ${encounter?.key || "未知零式副本"}`;
    if (
      !tier
      || typeof tier.key !== "string"
      || typeof tier.label !== "string"
      || !Number.isInteger(tier.order)
      || tier.order < 1
      || !Number.isInteger(tier.floor)
      || tier.floor < 1
      || tier.floor > 4
    ) {
      reportIssue(`${encounterLabel} 的 profile_summary_savage_tier 必須包含 key、label、正整數 order 與 1 至 4 的 floor`);
      continue;
    }

    const knownTier = tiersByKey.get(tier.key);
    if (knownTier && (knownTier.label !== tier.label || knownTier.order !== tier.order)) {
      reportIssue(`${encounterLabel} 的零式量級 label 與 order 必須和同一 key 的其他副本一致`);
    }
    const knownTierKey = tierKeysByOrder.get(tier.order);
    if (knownTierKey && knownTierKey !== tier.key) {
      reportIssue(`${encounterLabel} 的零式量級 order 不可與 ${knownTierKey} 重複`);
    }
    const floorKey = `${tier.key}:${tier.floor}`;
    if (floors.has(floorKey)) {
      reportIssue(`${encounterLabel} 的零式量級 floor 不可在同一量級重複`);
    }

    tiersByEncounter.set(encounter.key, tier);
    tiersByKey.set(tier.key, tier);
    tierKeysByOrder.set(tier.order, tier.key);
    floors.add(floorKey);
  }

  return tiersByEncounter;
}

function hasRankingData(ranking) {
  return Array.isArray(ranking?.ranking_entries) || Array.isArray(ranking?.report_shards) || ranking?.reports;
}

function mergeEntriesByOrder(baseEntries = [], deltaEntries = [], order = []) {
  const entriesById = new Map();
  for (const entry of [...baseEntries, ...deltaEntries]) {
    if (entry?.id) {
      entriesById.set(entry.id, entry);
    }
  }

  const merged = [];
  const usedIds = new Set();
  for (const id of Array.isArray(order) ? order : []) {
    const entry = entriesById.get(id);
    if (entry) {
      merged.push(entry);
      usedIds.add(id);
    }
  }
  if (Array.isArray(order) && order.length > 0) {
    return merged;
  }
  for (const entry of [...baseEntries, ...deltaEntries]) {
    if (entry?.id && !usedIds.has(entry.id)) {
      merged.push(entry);
      usedIds.add(entry.id);
    }
  }
  return merged;
}

function tableRowId(row, columns) {
  if (Array.isArray(row)) {
    const idIndex = columns.indexOf("id");
    return idIndex >= 0 ? row[idIndex] : null;
  }
  return row?.id || null;
}

function mergeRowsByOrder(baseRows = [], deltaRows = [], order = [], columns = []) {
  const rowsById = new Map();
  for (const row of [...baseRows, ...deltaRows]) {
    const id = tableRowId(row, columns);
    if (id) {
      rowsById.set(id, row);
    }
  }

  const merged = [];
  const usedIds = new Set();
  for (const id of Array.isArray(order) ? order : []) {
    const row = rowsById.get(id);
    if (row) {
      merged.push(row);
      usedIds.add(id);
    }
  }
  if (Array.isArray(order) && order.length > 0) {
    return merged;
  }
  for (const row of [...baseRows, ...deltaRows]) {
    const id = tableRowId(row, columns);
    if (id && !usedIds.has(id)) {
      merged.push(row);
      usedIds.add(id);
    }
  }
  return merged;
}

async function resolveRankingPayload(ranking, label) {
  if (ranking?.format !== "ranking_hidden_delta_v1") {
    return ranking;
  }

  validateContract(ranking, publicDataContracts.rankingHiddenDeltaPayload, label);
  const basePath = path.resolve(publicDataDir, ranking.base_path.replace(/^data\//, ""));
  if (!assertInside(publicDataDir, basePath, `${label} base_path`)) {
    return ranking;
  }
  const baseRanking = await readJson(basePath, `${label} 公開底稿`);
  const merged = {
    ...baseRanking,
    ...ranking,
    hidden_reports_included: true,
    ranking_entries: mergeEntriesByOrder(baseRanking?.ranking_entries, ranking.ranking_entries, ranking.ranking_entry_order),
  };
  delete merged.format;
  delete merged.base_path;
  delete merged.ranking_entry_order;
  return merged;
}

async function resolveRankingTablePayload(table, label) {
  if (table?.format !== "ranking_table_hidden_delta_v1") {
    return table;
  }

  const basePath = path.resolve(publicDataDir, table.base_path.replace(/^data\//, ""));
  if (!assertInside(publicDataDir, basePath, `${label} base_path`)) {
    return table;
  }
  const baseTable = await readJson(basePath, `${label} 公開底稿`);
  const columns = Array.isArray(table.table_columns) ? table.table_columns : baseTable?.table_columns || [];
  const merged = {
    ...baseTable,
    ...table,
    format: "ranking_table_index_v1",
    hidden_reports_included: true,
    table_columns: columns,
    table_rows: mergeRowsByOrder(baseTable?.table_rows, table.table_rows, table.table_row_order, columns),
  };
  return merged;
}

async function resolveRankingDetailsPayload(details, label) {
  if (details?.format !== "ranking_detail_hidden_delta_v1") {
    return details;
  }

  validateContract(details, publicDataContracts.rankingDetailsHiddenDeltaPayload, label);
  const basePath = path.resolve(publicDataDir, details.base_path.replace(/^data\//, ""));
  if (!assertInside(publicDataDir, basePath, `${label} base_path`)) {
    return details;
  }
  const baseDetails = await readJson(basePath, `${label} 公開底稿`);
  const merged = {
    ...baseDetails,
    ...details,
    format: "ranking_detail_entries_v1",
    hidden_reports_included: true,
    entries: {
      ...(baseDetails?.entries || {}),
      ...(details.entries || {}),
    },
  };
  delete merged.base_path;
  return merged;
}

function isFiniteNumber(value) {
  return Number.isFinite(Number(value));
}

function isObjectRecord(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function collectUserProfileEntries(profile) {
  const entries = [];
  for (const encounter of profile?.encounters || []) {
    if (encounter?.best_entry) {
      entries.push(encounter.best_entry);
    }
    entries.push(...(Array.isArray(encounter?.best_by_job) ? encounter.best_by_job : []));
    entries.push(...(Array.isArray(encounter?.public_entries) ? encounter.public_entries : []));
  }
  return entries;
}

async function readUserEntryDetails(detailCache, pathText, label) {
  if (typeof pathText !== "string" || !pathText) {
    reportIssue(`${label} 缺少 report_detail_path`);
    return null;
  }

  const detailPath = path.resolve(publicDataDir, pathText.replace(/^data\//, ""));
  const allowedDir = pathText.startsWith("data/all/")
    ? publicAllUserEntryDetailsDir
    : publicUserEntryDetailsDir;
  if (!assertInside(allowedDir, detailPath, `${label} report_detail_path`)) {
    return null;
  }
  if (!existsSync(detailPath)) {
    reportIssue(`${label} 指向不存在的個人成績報告細節檔：${pathText}`);
    return null;
  }

  if (!detailCache.has(pathText)) {
    const details = await readJson(detailPath, `${label} ${pathText}`);
    validateContract(details, publicDataContracts.userEntryDetailsPayload, `${label} ${pathText}`);
    if (details?.format !== "user_entry_details_v1") {
      reportIssue(`${label} ${pathText} format 必須是 user_entry_details_v1`);
    }
    const entryCount = Object.keys(details?.entries || {}).length;
    if (details?.entry_count !== entryCount) {
      reportIssue(`${label} ${pathText} entry_count=${details?.entry_count} 與 entries 數量 ${entryCount} 不一致`);
    }
    detailCache.set(pathText, details);
  }

  return detailCache.get(pathText);
}

async function validateUserProfileReportDetails(profile, label, detailCache) {
  for (const entry of collectUserProfileEntries(profile)) {
    const duplicateCount = Number(entry?.duplicate_count) || 0;
    if (duplicateCount <= 1) {
      continue;
    }

    const inlineVariants = Array.isArray(entry?.report_variants) ? entry.report_variants : [];
    const inlineSources = Array.isArray(entry?.source_reports) ? entry.source_reports : [];
    if (inlineVariants.length >= Math.min(duplicateCount, 2) || inlineSources.length >= Math.min(duplicateCount, 2)) {
      continue;
    }

    const detailId = entry?.report_detail_id || entry?.id;
    if (!entry?.report_detail_path || !detailId) {
      reportIssue(`${label} 的 ${entry?.id || "(未知成績)"} duplicate_count=${duplicateCount}，但缺少 report_variants/source_reports 或 report_detail_path/report_detail_id`);
      continue;
    }

    const details = await readUserEntryDetails(detailCache, entry.report_detail_path, `${label} 的 ${entry.id}`);
    const detailEntry = details?.entries?.[detailId];
    if (!detailEntry) {
      reportIssue(`${label} 的 ${entry.id} 指向 ${entry.report_detail_path}，但細節檔缺少 ${detailId}`);
      continue;
    }
    checkedUserEntryDetails += 1;

    const detailVariants = Array.isArray(detailEntry.report_variants) ? detailEntry.report_variants : [];
    const detailSources = Array.isArray(detailEntry.source_reports) ? detailEntry.source_reports : [];
    if (detailVariants.length < Math.min(duplicateCount, 2) && detailSources.length < Math.min(duplicateCount, 2)) {
      reportIssue(`${label} 的 ${entry.id} 細節檔來源數不足：duplicate_count=${duplicateCount}`);
    }
  }
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

    const shard = await readJsonAndCheckNoRawFields(shardPath, `${rankingLabel} 分片 ${normalizePath(shardPathText)}`);
    if (shard && typeof shard === "object" && !Array.isArray(shard)) {
      Object.assign(reports, shard);
    } else {
      reportIssue(`${rankingLabel} 分片必須是 report code 索引物件：${normalizePath(shardPathText)}`);
    }
  }

  return reports;
}

async function validateEncounters() {
  const configPath = path.join(rootDir, "config", "encounters.json");
  const publicPath = path.join(publicDataDir, "encounters.json");
  const configEncounters = await readJson(configPath, "config/encounters.json");
  const publicEncounters = await readJson(publicPath, "public/data/encounters.json");

  let configSavageTiers = new Map();
  if (!Array.isArray(configEncounters)) {
    reportIssue("config/encounters.json 必須是陣列");
  } else {
    ensureUniqueKeys(configEncounters, "key", "config/encounters.json");
    for (const encounter of configEncounters) {
      const profileSummaryVersion = encounter?.profile_summary_available_from;
      if (!個人成績簡表遊戲版本.has(profileSummaryVersion)) {
        reportIssue(`${encounter?.key || "未知副本"} 的 profile_summary_available_from 必須是受支援的個人成績簡表遊戲版本`);
      }
      const profileSummaryLastVersion = encounter?.profile_summary_available_until;
      if (
        profileSummaryLastVersion !== undefined
        && (
          !個人成績簡表遊戲版本.has(profileSummaryLastVersion)
          || 個人成績簡表遊戲版本索引.get(profileSummaryLastVersion) < 個人成績簡表遊戲版本索引.get(profileSummaryVersion)
        )
      ) {
        reportIssue(`${encounter?.key || "未知副本"} 的 profile_summary_available_until 必須是受支援且不早於首次可見版本的遊戲版本`);
      }
    }
    configSavageTiers = collectProfileSummarySavageTiers(configEncounters, "config/encounters.json");
  }

  if (!Array.isArray(publicEncounters)) {
    reportIssue("public/data/encounters.json 必須是陣列");
    return [];
  }

  ensureUniqueKeys(publicEncounters, "key", "public/data/encounters.json");
  const publicSavageTiers = collectProfileSummarySavageTiers(publicEncounters, "public/data/encounters.json");
  const configProfileSummaryVersions = new Map(
    Array.isArray(configEncounters)
      ? configEncounters.map((encounter) => [encounter?.key, {
        first: encounter?.profile_summary_available_from,
        last: encounter?.profile_summary_available_until,
      }])
      : [],
  );
  for (const encounter of publicEncounters) {
    const profileSummaryVersion = encounter?.profile_summary_available_from;
    if (!個人成績簡表遊戲版本.has(profileSummaryVersion)) {
      reportIssue(`${encounter?.key || "未知副本"} 的公開 profile_summary_available_from 必須是受支援的個人成績簡表遊戲版本`);
      continue;
    }
    const profileSummaryLastVersion = encounter?.profile_summary_available_until;
    if (profileSummaryLastVersion !== undefined && !個人成績簡表遊戲版本.has(profileSummaryLastVersion)) {
      reportIssue(`${encounter?.key || "未知副本"} 的公開 profile_summary_available_until 必須是受支援的個人成績簡表遊戲版本`);
      continue;
    }
    const configProfileSummaryVersion = configProfileSummaryVersions.get(encounter?.key);
    if (configProfileSummaryVersion && configProfileSummaryVersion.first !== profileSummaryVersion) {
      reportIssue(`${encounter.key} 的公開 profile_summary_available_from 必須與 config/encounters.json 一致`);
    }
    if (configProfileSummaryVersion && configProfileSummaryVersion.last !== profileSummaryLastVersion) {
      reportIssue(`${encounter.key} 的公開 profile_summary_available_until 必須與 config/encounters.json 一致`);
    }
    const configSavageTier = configSavageTiers.get(encounter?.key);
    const publicSavageTier = publicSavageTiers.get(encounter?.key);
    if (
      configSavageTier
      && (
        !publicSavageTier
        || configSavageTier.key !== publicSavageTier.key
        || configSavageTier.label !== publicSavageTier.label
        || configSavageTier.order !== publicSavageTier.order
        || configSavageTier.floor !== publicSavageTier.floor
      )
    ) {
      reportIssue(`${encounter.key} 的公開 profile_summary_savage_tier 必須與 config/encounters.json 一致`);
    }
  }
  return publicEncounters;
}

async function validateRankings(publicEncounters) {
  const gameVersionsConfig = await readJson(path.join(rootDir, "config", "game_versions.json"), "config/game_versions.json");
  const gameVersions = Array.isArray(gameVersionsConfig?.versions)
    ? gameVersionsConfig.versions.map((version) => ({
      patch: String(version?.patch || "").trim(),
      label: String(version?.label || version?.patch || "").trim(),
      starts_at_iso: version?.starts_at_iso ?? null,
    }))
    : [];
  const gameVersionPatches = new Set(gameVersions.map((version) => version.patch).filter(Boolean));

  if (gameVersions.length === 0 || gameVersions.some((version) => !version.patch || !version.label)) {
    reportIssue("config/game_versions.json 必須提供可用的繁中服版本設定，才能驗證排行榜版本紀錄。");
  }

  function expectedGameVersion(recordedAtIso) {
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

  function validateTableGameVersions(table, label) {
    if (!Array.isArray(table?.game_versions)) {
      reportIssue(`${label} 必須包含 game_versions，讓前端以繁中服版本日期篩選。`);
      return;
    }

    const tableVersions = table.game_versions.map((version) => ({
      patch: String(version?.patch || "").trim(),
      label: String(version?.label || "").trim(),
      starts_at_iso: version?.starts_at_iso ?? null,
    }));
    if (JSON.stringify(tableVersions) !== JSON.stringify(gameVersions)) {
      reportIssue(`${label} 的 game_versions 必須與 config/game_versions.json 一致。`);
    }

    const columns = Array.isArray(table?.table_columns) ? table.table_columns : [];
    const gameVersionIndex = columns.indexOf("game_version");
    const recordedAtIndex = columns.indexOf("recorded_at_iso");
    if (gameVersionIndex < 0 || recordedAtIndex < 0) {
      reportIssue(`${label} 的 table_columns 必須包含 recorded_at_iso 與 game_version。`);
      return;
    }

    for (const row of table.table_rows || []) {
      const recordedAtIso = Array.isArray(row) ? row[recordedAtIndex] : row?.recorded_at_iso;
      const gameVersion = Array.isArray(row) ? row[gameVersionIndex] : row?.game_version;
      const expected = expectedGameVersion(recordedAtIso);
      if (!gameVersionPatches.has(gameVersion) || gameVersion !== expected) {
        reportIssue(`${label} 有一筆列的 game_version 與 recorded_at_iso 對應的繁中服版本不一致。`);
        break;
      }
    }
  }

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
    validateContract(publicRanking, publicDataContracts.rankingPayload, `${key} 公開排行榜`);
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
      validateTableGameVersions(table, `${key} 排行榜薄索引`);
    }
    if (!existsSync(detailPath)) {
      reportIssue(`${key} 缺少排行榜報告細節檔：public/data/ranking-details/${key}.json`);
    } else {
      const details = await readJson(detailPath, `${key} 排行榜報告細節`);
      validateContract(details, publicDataContracts.rankingDetailsPayload, `${key} 排行榜報告細節`);
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
      const rawAllRanking = await readJson(allRankingPath, `${key} 完整排行榜鏡像`);
      const allRanking = await resolveRankingPayload(rawAllRanking, `${key} 完整排行榜鏡像`);
      validateContract(allRanking, publicDataContracts.rankingPayload, `${key} 完整排行榜鏡像`);
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
      const rawAllTable = await readJson(allTablePath, `${key} 完整鏡像排行榜薄索引`);
      const allTable = await resolveRankingTablePayload(rawAllTable, `${key} 完整鏡像排行榜薄索引`);
      if (allTable?.hidden_reports_included !== true) {
        reportIssue(`${key} 完整鏡像排行榜薄索引必須標記 hidden_reports_included=true`);
      }
      if (allTable?.detail_path !== `data/all/ranking-details/${key}.json`) {
        reportIssue(`${key} 完整鏡像排行榜薄索引 detail_path 不正確`);
      }
      validateTableGameVersions(allTable, `${key} 完整鏡像排行榜薄索引`);
    }
    if (!existsSync(allDetailPath)) {
      reportIssue(`${key} 缺少完整鏡像排行榜報告細節檔：public/data/all/ranking-details/${key}.json`);
    } else {
      const rawAllDetails = await readJson(allDetailPath, `${key} 完整鏡像排行榜報告細節`);
      const allDetails = await resolveRankingDetailsPayload(rawAllDetails, `${key} 完整鏡像排行榜報告細節`);
      validateContract(allDetails, publicDataContracts.rankingDetailsPayload, `${key} 完整鏡像排行榜報告細節`);
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

    const sourceRanking = await readJsonAndCheckNoRawFields(sourceRankingPath, `${key} 來源排行榜`);
    if (!hasRankingData(sourceRanking)) {
      reportIssue(`${key} 來源排行榜缺少 ranking_entries、report_shards 或 reports`);
      continue;
    }

    const sourceReports = await loadSourceReports(sourceRanking, key);
    for (const reportCode of Object.keys(sourceReports)) {
      checkedSourceReports += 1;
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

  const logActivity = activity?.log_activity;
  if (!isObjectRecord(logActivity)) {
    reportIssue("public/data/activity.json 缺少 log_activity");
    return;
  }
  if (!Array.isArray(logActivity.series) || logActivity.series.length === 0) {
    reportIssue("public/data/activity.json 的 log_activity.series 必須是非空陣列");
    return;
  }
  if (!Array.isArray(logActivity.category_series) || logActivity.category_series.length === 0) {
    reportIssue("public/data/activity.json 的 log_activity.category_series 必須是非空陣列");
    return;
  }
  const allSeries = logActivity.series.find((series) => series?.encounter_key === "all");
  if (!allSeries) {
    reportIssue("public/data/activity.json 的 log_activity.series 必須包含全部副本系列");
  }
  if (!isFiniteNumber(logActivity?.summary?.total_unique_report_count)) {
    reportIssue("public/data/activity.json 缺少 log_activity.summary.total_unique_report_count");
  }

  for (const series of logActivity.series) {
    if (!series?.encounter_key || !series?.encounter_name || !Array.isArray(series.points)) {
      reportIssue("public/data/activity.json 的 log_activity.series 有條目缺少副本或 points");
      break;
    }
    checkedActivityItems += series.points.length;
    for (const point of series.points) {
      if (
        typeof point?.date !== "string" ||
        !isFiniteNumber(point.unique_report_count) ||
        !isFiniteNumber(point.unique_fight_count)
      ) {
        reportIssue("public/data/activity.json 的 log_activity point 缺少日期或數量欄位");
        return;
      }
    }
  }

  for (const series of logActivity.category_series) {
    if (!series?.category || !series?.label || !Array.isArray(series.points)) {
      reportIssue("public/data/activity.json 的 log_activity.category_series 有條目缺少分類或 points");
      break;
    }
    checkedActivityItems += series.points.length;
    for (const point of series.points) {
      if (
        typeof point?.date !== "string" ||
        !isFiniteNumber(point.unique_report_count) ||
        !isFiniteNumber(point.unique_fight_count)
      ) {
        reportIssue("public/data/activity.json 的 log_activity category point 缺少日期或數量欄位");
        return;
      }
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
  validateContract(teamRankings, publicDataContracts.teamRankingsPayload, "public/data/team_rankings.json");
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
  validateContract(serverCompare, publicDataContracts.serverComparePayload, "public/data/server_compare.json");
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

function indexOfColumn(columns, columnName, label) {
  const index = Array.isArray(columns) ? columns.indexOf(columnName) : -1;
  if (index < 0) {
    reportIssue(`${label} 缺少 ${columnName} 欄位`);
  }
  return index;
}

function validateReportStatusRows(payload, label) {
  const reportColumns = payload?.report_columns || [];
  const reportCodeIndex = indexOfColumn(reportColumns, "report_code", label);
  const entryCountIndex = indexOfColumn(reportColumns, "entry_count", label);
  const hiddenEntryCountIndex = indexOfColumn(reportColumns, "hidden_entry_count", label);
  const encountersIndex = indexOfColumn(reportColumns, "encounters", label);
  const fightsIndex = indexOfColumn(reportColumns, "fights", label);

  if (!Array.isArray(payload?.reports)) {
    reportIssue(`${label} reports 必須是陣列`);
    return;
  }
  if (payload.report_count !== payload.reports.length) {
    reportIssue(`${label} report_count=${payload.report_count} 與 reports 長度 ${payload.reports.length} 不一致`);
  }

  let totalEntryCount = 0;
  let totalHiddenEntryCount = 0;
  const seenReportCodes = new Set();
  for (const [index, report] of payload.reports.entries()) {
    if (!Array.isArray(report)) {
      reportIssue(`${label} reports[${index}] 必須是欄位陣列`);
      continue;
    }

    const reportCode = reportCodeIndex >= 0 ? report[reportCodeIndex] : null;
    if (typeof reportCode !== "string" || !reportCode) {
      reportIssue(`${label} reports[${index}] 缺少 report_code`);
    } else if (seenReportCodes.has(reportCode)) {
      reportIssue(`${label} 出現重複 report_code：${reportCode}`);
    } else {
      seenReportCodes.add(reportCode);
    }

    const entryCount = Number(report[entryCountIndex]);
    const hiddenEntryCount = Number(report[hiddenEntryCountIndex]);
    if (!Number.isInteger(entryCount) || entryCount < 0) {
      reportIssue(`${label} ${reportCode || `reports[${index}]`} entry_count 必須是非負整數`);
    } else {
      totalEntryCount += entryCount;
    }
    if (!Number.isInteger(hiddenEntryCount) || hiddenEntryCount < 0) {
      reportIssue(`${label} ${reportCode || `reports[${index}]`} hidden_entry_count 必須是非負整數`);
    } else {
      totalHiddenEntryCount += hiddenEntryCount;
    }
    if (!Array.isArray(report[encountersIndex]) || !Array.isArray(report[fightsIndex])) {
      reportIssue(`${label} ${reportCode || `reports[${index}]`} 必須包含 encounters 與 fights 摘要`);
    }
  }

  if (payload.entry_count !== totalEntryCount) {
    reportIssue(`${label} entry_count=${payload.entry_count} 與 report rows 加總 ${totalEntryCount} 不一致`);
  }
  if (payload.hidden_entry_count !== totalHiddenEntryCount) {
    reportIssue(`${label} hidden_entry_count=${payload.hidden_entry_count} 與 report rows 加總 ${totalHiddenEntryCount} 不一致`);
  }
  checkedReportStatusRows += payload.reports.length;
}

async function validateReportStatusIndex() {
  const reportStatusPath = path.join(publicDataDir, "report_status_index.json");
  if (!existsSync(reportStatusPath)) {
    reportIssue("缺少 public/data/report_status_index.json，請先執行 npm run build:report-status");
    return;
  }

  const reportStatus = await readJson(reportStatusPath, "public/data/report_status_index.json");
  validateContract(reportStatus, publicDataContracts.reportStatusIndexPayload, "public/data/report_status_index.json");
  validateReportStatusRows(reportStatus, "public/data/report_status_index.json");

  const hiddenReportStatusPath = path.join(publicAllDataDir, "report_status_index.json");
  if (existsSync(publicAllRankingDetailsDir) && !existsSync(hiddenReportStatusPath)) {
    reportIssue("缺少 public/data/all/report_status_index.json，請先執行 npm run build:report-status");
    return;
  }
  if (!existsSync(hiddenReportStatusPath)) {
    return;
  }

  const hiddenReportStatus = await readJson(hiddenReportStatusPath, "public/data/all/report_status_index.json");
  validateContract(hiddenReportStatus, publicDataContracts.reportStatusHiddenDeltaPayload, "public/data/all/report_status_index.json");
  if (hiddenReportStatus?.base_path !== "data/report_status_index.json") {
    reportIssue("public/data/all/report_status_index.json base_path 必須指向 data/report_status_index.json");
  }
  validateReportStatusRows(hiddenReportStatus, "public/data/all/report_status_index.json");
}

async function validatePublicUpdateStatus() {
  const updateStatusPath = path.join(publicDataDir, "update_status.json");
  if (!existsSync(updateStatusPath)) {
    reportIssue("缺少 public/data/update_status.json，請先執行 npm run build:public-status");
    return;
  }

  const updateStatus = await readJson(updateStatusPath, "public/data/update_status.json");
  validateContract(updateStatus, publicDataContracts.publicUpdateStatusPayload, "public/data/update_status.json");
  if ((Number(updateStatus?.schedule?.interval_minutes) || 0) <= 0) {
    reportIssue("public/data/update_status.json schedule.interval_minutes 必須大於 0");
  }
}

async function validateHoneyFans() {
  const honeyFansPath = path.join(publicDataDir, "fun", "honey_b_fans.json");
  if (!existsSync(honeyFansPath)) {
    reportIssue("缺少 public/data/fun/honey_b_fans.json，請先執行 npm run build:honey-fans");
    return;
  }

  const honeyFans = await readJson(honeyFansPath, "public/data/fun/honey_b_fans.json");
  if (honeyFans?.schema_version !== 1) {
    reportIssue("public/data/fun/honey_b_fans.json 的 schema_version 必須是 1");
  }
  if (honeyFans?.feature !== "honey_b_lovely_fans") {
    reportIssue("public/data/fun/honey_b_fans.json 的 feature 必須是 honey_b_lovely_fans");
  }
  if (!isObjectRecord(honeyFans?.summary)) {
    reportIssue("public/data/fun/honey_b_fans.json 缺少 summary");
  }
  if (!isFiniteNumber(honeyFans?.summary?.leaderboard_window_days) || honeyFans.summary.leaderboard_window_days < 1) {
    reportIssue("public/data/fun/honey_b_fans.json summary.leaderboard_window_days 必須是正數");
  }
  if (!isFiniteNumber(honeyFans?.summary?.historical_total_event_count)) {
    reportIssue("public/data/fun/honey_b_fans.json summary.historical_total_event_count 必須是數字");
  }
  if (!isFiniteNumber(honeyFans?.summary?.team_ranking_record_count)) {
    reportIssue("public/data/fun/honey_b_fans.json summary.team_ranking_record_count 必須是數字");
  }
  if (!isFiniteNumber(honeyFans?.summary?.team_ranking_event_count)) {
    reportIssue("public/data/fun/honey_b_fans.json summary.team_ranking_event_count 必須是數字");
  }
  const teamRankingStartAt = new Date(honeyFans?.summary?.team_ranking_window_start_at_iso).getTime();
  if (!Number.isFinite(teamRankingStartAt)) {
    reportIssue("public/data/fun/honey_b_fans.json summary.team_ranking_window_start_at_iso 必須是有效 ISO 時間");
  }
  for (const listName of ["top_fans", "latest_records", "latest_fans", "team_rankings", "records"]) {
    if (!Array.isArray(honeyFans?.[listName])) {
      reportIssue(`public/data/fun/honey_b_fans.json 的 ${listName} 必須是陣列`);
    }
  }
  if ((honeyFans?.latest_records || []).length > 5) {
    reportIssue("public/data/fun/honey_b_fans.json 的 latest_records 最多只能輸出 5 筆");
  }
  if ((honeyFans?.latest_fans || []).length > 16) {
    reportIssue("public/data/fun/honey_b_fans.json 的 latest_fans 最多只能輸出 16 筆");
  }

  for (const fan of honeyFans?.top_fans || []) {
    checkedHoneyFanRows += 1;
    if (!fan?.character_name || !fan?.server || !isFiniteNumber(fan?.total_event_count)) {
      reportIssue("Honey B. Lovely 粉絲榜 top_fans 有粉絲缺少角色、伺服器或次數");
      break;
    }
    if (!isFiniteNumber(fan?.historical_total_event_count) || !isFiniteNumber(fan?.current_streak_weeks)) {
      reportIssue("Honey B. Lovely 粉絲榜 top_fans 有粉絲缺少歷史總數或連續入榜週數");
      break;
    }
  }
  for (const teamRecord of honeyFans?.team_rankings || []) {
    if (!isFiniteNumber(teamRecord?.total_event_count) || !isFiniteNumber(teamRecord?.unique_fan_count)) {
      reportIssue("Honey B. Lovely 團隊榜 team_rankings 有紀錄缺少 total_event_count 或 unique_fan_count");
      break;
    }
    if (teamRecord?.fight_status !== "kill" || teamRecord?.is_kill !== true) {
      reportIssue("Honey B. Lovely 團隊榜 team_rankings 只能包含通關場次");
      break;
    }
    if (!Array.isArray(teamRecord?.members) || !Array.isArray(teamRecord?.source_reports)) {
      reportIssue("Honey B. Lovely 團隊榜 team_rankings 有紀錄缺少 members 或 source_reports");
      break;
    }
    if (Number.isFinite(teamRankingStartAt) && new Date(teamRecord?.fight_completed_at_iso).getTime() < teamRankingStartAt) {
      reportIssue("Honey B. Lovely 團隊榜 team_rankings 有紀錄早於活動起始時間");
      break;
    }
  }
}

async function validateUserDataset(dataDir, label, { countFiles = false } = {}) {
  const usersDir = path.join(dataDir, "users");
  const userIndexPath = path.join(usersDir, "index.json");
  const detailCache = new Map();
  if (!existsSync(userIndexPath)) {
    reportIssue(`缺少 ${label}/users/index.json，請先執行 npm run build:user-data`);
    return;
  }

  const index = await readJson(userIndexPath, `${label}/users/index.json`);
  validateContract(index, publicDataContracts.userIndexPayload, `${label}/users/index.json`);
  const users = Array.isArray(index?.users) ? index.users : [];
  if (index?.total_users !== users.length) {
    reportIssue(`${label}/users/index.json 的 total_users=${index?.total_users} 與 users 長度 ${users.length} 不一致`);
  }
  const achievements = Array.isArray(index?.achievements) ? index.achievements : [];
  const achievementIds = new Set();
  if (achievements.length === 0) {
    reportIssue(`${label}/users/index.json 缺少成就手冊統計`);
  }
  for (const achievement of achievements) {
    if (achievementIds.has(achievement?.id)) {
      reportIssue(`${label}/users/index.json 的成就 ID 重複：${achievement?.id || "(空白)"}`);
      continue;
    }
    achievementIds.add(achievement?.id);

    const holderCount = achievement?.holder_count;
    const holderPercentage = achievement?.holder_percentage;
    if (!Number.isInteger(holderCount) || holderCount < 0 || holderCount > users.length) {
      reportIssue(`${label}/users/index.json 的成就 ${achievement?.id || "(未知)"} holder_count 超出玩家總數`);
      continue;
    }
    const expectedPercentage = users.length > 0 ? Number(((holderCount / users.length) * 100).toFixed(2)) : 0;
    if (!isFiniteNumber(holderPercentage) || Math.abs(holderPercentage - expectedPercentage) > 0.001) {
      reportIssue(
        `${label}/users/index.json 的成就 ${achievement?.id || "(未知)"} holder_percentage 與 holder_count 不一致`,
      );
    }
  }

  for (const user of users) {
    const filePathText = user?.file_path;
    if (typeof filePathText !== "string" || !filePathText) {
      reportIssue(`使用者索引 ${user?.character_name || "(未知)"} 缺少 file_path`);
      continue;
    }

    const userPath = path.resolve(publicDataDir, filePathText.replace(/^data\//, ""));
    if (!assertInside(publicDataDir, userPath, `使用者索引 ${user?.character_name || filePathText}`)) {
      continue;
    }
    if (!existsSync(userPath)) {
      reportIssue(`使用者索引指向不存在檔案：${filePathText}`);
      continue;
    }
    const profile = await readJson(userPath, `${label}/${filePathText}`);
    if (profile?.format === "user_profile_hidden_delta_v1") {
      validateContract(profile, publicDataContracts.userProfileHiddenDelta, `${label}/${filePathText}`);
      const basePath = path.resolve(publicDataDir, profile.base_path.replace(/^data\//, ""));
      if (assertInside(publicDataDir, basePath, `${label}/${filePathText} base_path`) && !existsSync(basePath)) {
        reportIssue(`${label}/${filePathText} 指向不存在的公開成績單底稿：${profile.base_path}`);
      }
    } else {
      validateContract(profile, publicDataContracts.userProfile, `${label}/${filePathText}`);
    }
    await validateUserProfileReportDetails(profile, `${label}/${filePathText}`, detailCache);
    if (countFiles) {
      checkedUserFiles += 1;
    }
  }
}

async function validateUsers() {
  await validateUserDataset(publicDataDir, "public/data", { countFiles: true });
  if (existsSync(path.join(publicAllDataDir, "users", "index.json"))) {
    await validateUserDataset(publicAllDataDir, "public/data/all");
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
  const mirrorContracts = {
    "team_rankings.json": publicDataContracts.teamRankingsPayload,
    "server_compare.json": publicDataContracts.serverComparePayload,
  };

  for (const relativePath of requiredMirrorFiles) {
    const mirrorPath = path.join(publicAllDataDir, relativePath);
    if (!existsSync(mirrorPath)) {
      reportIssue(`缺少完整資料鏡像：public/data/all/${normalizePath(relativePath)}`);
      continue;
    }
    const mirror = await readJson(mirrorPath, `public/data/all/${normalizePath(relativePath)}`);
    const contract = mirrorContracts[relativePath];
    if (contract) {
      validateContract(mirror, contract, `public/data/all/${normalizePath(relativePath)}`);
    }
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
  await validateReportStatusIndex();
  await validatePublicUpdateStatus();
  await validateHoneyFans();
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
    `資料驗證通過：${publicEncounters.length} 個公開副本、${checkedSourceReports} 份來源 report、${checkedReportStatusRows} 份 Logs 狀態索引 report、${checkedUserFiles} 份使用者檔案、${checkedUserEntryDetails} 筆個人成績報告細節、${checkedActivityItems} 筆近期動態項目、${checkedTeamRecords} 筆隊伍榜紀錄、${checkedServerCompareRows} 筆伺服器對比資料、${checkedHoneyFanRows} 筆蜂蜂粉絲資料。`,
  );
}

main().catch((error) => {
  console.error(`資料驗證失敗：${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
