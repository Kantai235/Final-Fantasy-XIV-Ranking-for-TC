import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicAllDataDir = path.join(publicDataDir, "all");

const issues = [];
const counters = {
  publicUsers: 0,
  allUsers: 0,
  userEntries: 0,
  duplicateEntries: 0,
  rankingRows: 0,
  rankingDetailRows: 0,
  allHiddenRankingEntries: 0,
};

function reportIssue(message) {
  issues.push(message);
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

async function readJson(filePath, label) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    reportIssue(`${label} 不是可讀取的 JSON：${error.message}`);
    return null;
  }
}

function assertInside(parent, target, label) {
  const relative = path.relative(parent, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    reportIssue(`${label} 指向允許目錄外：${normalizePath(path.relative(rootDir, target))}`);
    return false;
  }
  return true;
}

function rowToObject(row, columns) {
  if (!Array.isArray(row)) {
    return row && typeof row === "object" ? row : null;
  }
  return Object.fromEntries((columns || []).map((column, index) => [column, row[index]]));
}

function collectTableRows(table) {
  const rows = [];
  const columns = Array.isArray(table?.table_columns) ? table.table_columns : [];
  for (const row of Array.isArray(table?.table_rows) ? table.table_rows : []) {
    const item = rowToObject(row, columns);
    if (item) {
      rows.push(item);
    }
  }
  return rows;
}

function entryHasReportVariantCoverage(entry) {
  const duplicateCount = Number(entry?.duplicate_count) || 0;
  if (duplicateCount <= 1) {
    return true;
  }

  const reportVariants = Array.isArray(entry?.report_variants) ? entry.report_variants : [];
  const sourceReports = Array.isArray(entry?.source_reports) ? entry.source_reports : [];
  // 後續若把 report_variants 拆成按需載入，請讓 entry 保留 detail_path/detail_id 之類的線索，
  // 這個守恆檢查才能確認多來源報告仍可追溯，而不是被瘦身時默默丟失。
  const hasLazyDetailPointer = Boolean(entry?.report_variants_path || entry?.report_detail_path || entry?.report_detail_id);
  return reportVariants.length >= Math.min(duplicateCount, 2) || sourceReports.length >= Math.min(duplicateCount, 2) || hasLazyDetailPointer;
}

async function readUserEntryDetails(detailCache, pathText, label) {
  if (typeof pathText !== "string" || !pathText) {
    reportIssue(`${label} 缺少 report_detail_path`);
    return null;
  }

  const detailPath = path.resolve(publicDataDir, pathText.replace(/^data\//, ""));
  const allowedDir = pathText.startsWith("data/all/")
    ? path.join(publicAllDataDir, "user-entry-details")
    : path.join(publicDataDir, "user-entry-details");
  if (!assertInside(allowedDir, detailPath, `${label} report_detail_path`)) {
    return null;
  }
  if (!existsSync(detailPath)) {
    reportIssue(`${label} 指向不存在的個人成績報告細節檔：${pathText}`);
    return null;
  }

  if (!detailCache.has(pathText)) {
    detailCache.set(pathText, await readJson(detailPath, `${label} ${pathText}`));
  }
  return detailCache.get(pathText);
}

async function validateEntryReportVariantCoverage(entry, label, detailCache) {
  const duplicateCount = Number(entry?.duplicate_count) || 0;
  if (duplicateCount <= 1) {
    return true;
  }

  const reportVariants = Array.isArray(entry?.report_variants) ? entry.report_variants : [];
  const sourceReports = Array.isArray(entry?.source_reports) ? entry.source_reports : [];
  if (reportVariants.length >= Math.min(duplicateCount, 2) || sourceReports.length >= Math.min(duplicateCount, 2)) {
    return true;
  }

  if (!entryHasReportVariantCoverage(entry)) {
    return false;
  }

  const detailId = entry?.report_detail_id || entry?.id;
  const details = await readUserEntryDetails(detailCache, entry?.report_detail_path, `${label} 的 ${entry?.id || "(未知成績)"}`);
  const detailEntry = details?.entries?.[detailId];
  if (!detailEntry) {
    reportIssue(`${label} 的 ${entry?.id || "(未知成績)"} 指向 ${entry?.report_detail_path || "(缺少路徑)"}，但細節檔缺少 ${detailId || "(缺少 id)"}`);
    return false;
  }

  const detailVariants = Array.isArray(detailEntry.report_variants) ? detailEntry.report_variants : [];
  const detailSources = Array.isArray(detailEntry.source_reports) ? detailEntry.source_reports : [];
  return detailVariants.length >= Math.min(duplicateCount, 2) || detailSources.length >= Math.min(duplicateCount, 2);
}

function collectProfileEntries(profile) {
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

async function resolveRankingPayload(ranking) {
  if (ranking?.format !== "ranking_hidden_delta_v1") {
    return ranking;
  }
  const basePath = path.resolve(publicDataDir, ranking.base_path.replace(/^data\//, ""));
  const base = await readJson(basePath, `hidden delta base ${ranking.base_path}`);
  const merged = {
    ...base,
    ...ranking,
    hidden_reports_included: true,
    ranking_entries: mergeEntriesByOrder(base?.ranking_entries, ranking.ranking_entries, ranking.ranking_entry_order),
  };
  return merged;
}

async function resolveRankingTablePayload(table) {
  if (table?.format !== "ranking_table_hidden_delta_v1") {
    return table;
  }
  const basePath = path.resolve(publicDataDir, table.base_path.replace(/^data\//, ""));
  const base = await readJson(basePath, `hidden table delta base ${table.base_path}`);
  const columns = Array.isArray(table.table_columns) ? table.table_columns : base?.table_columns || [];
  const merged = {
    ...base,
    ...table,
    format: "ranking_table_index_v1",
    hidden_reports_included: true,
    table_columns: columns,
    table_rows: mergeRowsByOrder(base?.table_rows, table.table_rows, table.table_row_order, columns),
  };
  return merged;
}

async function resolveRankingDetailsPayload(details) {
  if (details?.format !== "ranking_detail_hidden_delta_v1") {
    return details;
  }
  const basePath = path.resolve(publicDataDir, details.base_path.replace(/^data\//, ""));
  const base = await readJson(basePath, `hidden detail delta base ${details.base_path}`);
  return {
    ...base,
    ...details,
    format: "ranking_detail_entries_v1",
    hidden_reports_included: true,
    entries: {
      ...(base?.entries || {}),
      ...(details.entries || {}),
    },
  };
}

async function resolveUserProfile(profile) {
  if (profile?.format !== "user_profile_hidden_delta_v1") {
    return profile;
  }

  const basePath = path.resolve(publicDataDir, profile.base_path.replace(/^data\//, ""));
  const base = await readJson(basePath, `hidden user delta base ${profile.base_path}`);
  const encountersByKey = new Map((base?.encounters || []).map((encounter) => [encounter.encounter_key, { ...encounter }]));
  for (const deltaEncounter of profile.encounters || []) {
    const baseEncounter = encountersByKey.get(deltaEncounter.encounter_key) || {
      encounter_key: deltaEncounter.encounter_key,
      encounter_name: deltaEncounter.encounter_name,
      encounter_category: deltaEncounter.encounter_category ?? null,
      updated_at_iso: deltaEncounter.updated_at_iso ?? null,
      best_entry: null,
      best_by_job: [],
      public_entries: [],
    };
    encountersByKey.set(deltaEncounter.encounter_key, {
      ...baseEncounter,
      encounter_name: deltaEncounter.encounter_name || baseEncounter.encounter_name,
      encounter_category: deltaEncounter.encounter_category ?? baseEncounter.encounter_category ?? null,
      updated_at_iso: deltaEncounter.updated_at_iso ?? baseEncounter.updated_at_iso ?? null,
      best_entry: deltaEncounter.best_entry ?? baseEncounter.best_entry ?? null,
      best_by_job: Array.isArray(deltaEncounter.best_by_job) ? deltaEncounter.best_by_job : baseEncounter.best_by_job || [],
      public_entries: mergeEntriesByOrder(baseEncounter.public_entries, deltaEncounter.public_entries, deltaEncounter.public_entry_order),
    });
  }

  const encounters = [];
  const usedKeys = new Set();
  for (const key of profile.encounter_order || []) {
    const encounter = encountersByKey.get(key);
    if (encounter) {
      encounters.push(encounter);
      usedKeys.add(key);
    }
  }
  for (const encounter of encountersByKey.values()) {
    if (!usedKeys.has(encounter.encounter_key)) {
      encounters.push(encounter);
    }
  }

  return {
    ...base,
    schema_version: 1,
    generated_at_iso: profile.generated_at_iso,
    character_name: profile.character_name || base?.character_name || "",
    canonical_server: profile.canonical_server ?? base?.canonical_server ?? null,
    servers: profile.servers || base?.servers || [],
    server_aliases: profile.server_aliases || base?.server_aliases || [],
    summary: profile.summary || base?.summary || {},
    frequent_teammates: profile.frequent_teammates || base?.frequent_teammates || [],
    encounters,
  };
}

async function validateUserDataset(dataDir, label) {
  const usersDir = path.join(dataDir, "users");
  const indexPath = path.join(usersDir, "index.json");
  const index = await readJson(indexPath, `${label}/users/index.json`);
  const users = Array.isArray(index?.users) ? index.users : [];

  if (index?.total_users !== users.length) {
    reportIssue(`${label}/users/index.json total_users=${index?.total_users} 與 users 長度 ${users.length} 不一致`);
  }

  const seenFiles = new Set();
  const seenIdentities = new Set();
  const detailCache = new Map();
  for (const user of users) {
    const filePathText = user?.file_path;
    if (!filePathText) {
      reportIssue(`${label}/users/index.json 有使用者缺少 file_path`);
      continue;
    }
    if (seenFiles.has(filePathText)) {
      reportIssue(`${label}/users/index.json 出現重複 file_path：${filePathText}`);
    }
    seenFiles.add(filePathText);
    seenIdentities.add(`${user?.character_name || ""}\u0000${(user?.servers || []).join("|")}`);

    const userPath = path.resolve(publicDataDir, filePathText.replace(/^data\//, ""));
    if (!assertInside(publicDataDir, userPath, `${label} 使用者檔 ${filePathText}`)) {
      continue;
    }
    if (!existsSync(userPath)) {
      reportIssue(`${label} 使用者索引指向不存在檔案：${filePathText}`);
      continue;
    }

    const profile = await resolveUserProfile(await readJson(userPath, `${label}/${filePathText}`));
    const encounters = Array.isArray(profile?.encounters) ? profile.encounters : [];
    const publicEntryCount = encounters.reduce(
      (sum, encounter) => sum + (Array.isArray(encounter?.public_entries) ? encounter.public_entries.length : 0),
      0,
    );

    if (profile?.summary?.public_entry_count !== publicEntryCount) {
      reportIssue(`${label}/${filePathText} summary.public_entry_count=${profile?.summary?.public_entry_count} 與 public_entries 總數 ${publicEntryCount} 不一致`);
    }
    if (profile?.summary?.encounter_count !== encounters.length) {
      reportIssue(`${label}/${filePathText} summary.encounter_count=${profile?.summary?.encounter_count} 與 encounters 長度 ${encounters.length} 不一致`);
    }
    if (user.public_entry_count !== profile?.summary?.public_entry_count) {
      reportIssue(`${label}/users/index.json 的 ${user.character_name} public_entry_count 與使用者檔不一致`);
    }
    if (user.encounter_count !== profile?.summary?.encounter_count) {
      reportIssue(`${label}/users/index.json 的 ${user.character_name} encounter_count 與使用者檔不一致`);
    }

    for (const entry of collectProfileEntries(profile)) {
      counters.userEntries += 1;
      const duplicateCount = Number(entry?.duplicate_count) || 0;
      if (duplicateCount > 1) {
        counters.duplicateEntries += 1;
      }
      if (!(await validateEntryReportVariantCoverage(entry, `${label}/${filePathText}`, detailCache))) {
        reportIssue(`${label}/${filePathText} 的 ${entry?.id || "(未知成績)"} duplicate_count=${duplicateCount}，但缺少 report_variants/source_reports 或按需載入細節線索`);
      }
    }
  }

  return {
    index,
    users,
    filePaths: seenFiles,
    identities: seenIdentities,
  };
}

async function validateRankingDataset(dataDir, label, publicReference = null) {
  const encountersPath = path.join(publicDataDir, "encounters.json");
  const encounters = await readJson(encountersPath, "public/data/encounters.json");
  if (!Array.isArray(encounters)) {
    reportIssue("public/data/encounters.json 必須是陣列，無法檢查排行榜守恆");
    return new Map();
  }

  const countsByEncounter = new Map();
  for (const encounter of encounters) {
    const key = encounter?.key;
    if (!key) {
      continue;
    }

    const rankingPath = path.join(dataDir, "rankings", `${key}.json`);
    const tablePath = path.join(dataDir, "ranking-tables", `${key}.json`);
    const detailPath = path.join(dataDir, "ranking-details", `${key}.json`);
    const ranking = await resolveRankingPayload(await readJson(rankingPath, `${label}/rankings/${key}.json`));
    const table = await resolveRankingTablePayload(await readJson(tablePath, `${label}/ranking-tables/${key}.json`));
    const details = await resolveRankingDetailsPayload(await readJson(detailPath, `${label}/ranking-details/${key}.json`));
    const rankingEntries = Array.isArray(ranking?.ranking_entries) ? ranking.ranking_entries : [];
    const tableRows = Array.isArray(table?.table_rows) ? table.table_rows : [];
    const detailEntries = details?.entries && typeof details.entries === "object" && !Array.isArray(details.entries)
      ? details.entries
      : {};

    counters.rankingRows += tableRows.length;
    counters.rankingDetailRows += Object.keys(detailEntries).length;
    counters.allHiddenRankingEntries += rankingEntries.filter((entry) => entry?.report_hidden).length;
    countsByEncounter.set(key, rankingEntries.length);

    if (tableRows.length !== rankingEntries.length) {
      reportIssue(`${label}/${key} ranking-tables 列數 ${tableRows.length} 與 ranking_entries ${rankingEntries.length} 不一致`);
    }

    const rowsNeedingDetails = collectTableRows(table).filter((row) => row?.has_report_detail);
    for (const row of rowsNeedingDetails) {
      if (!row?.id || !detailEntries[row.id]) {
        reportIssue(`${label}/${key} 的薄索引列 ${row?.id || "(缺少 id)"} 標記 has_report_detail，但 ranking-details 找不到對應 entry`);
        break;
      }
    }

    if (publicReference) {
      const publicCount = publicReference.get(key) || 0;
      if (rankingEntries.length < publicCount) {
        reportIssue(`${label}/${key} ranking_entries ${rankingEntries.length} 少於公開資料 ${publicCount}`);
      }
    }
  }

  return countsByEncounter;
}

async function validateAllMirrorCoverage(publicUsers, allUsers) {
  if (!allUsers?.filePaths) {
    return;
  }

  for (const identity of publicUsers.identities) {
    if (!allUsers.identities.has(identity)) {
      reportIssue("public/data/all/users/index.json 缺少公開使用者身分");
      break;
    }
  }

  if ((allUsers.index?.total_users || 0) < (publicUsers.index?.total_users || 0)) {
    reportIssue(`public/data/all/users/index.json total_users=${allUsers.index?.total_users} 少於公開 total_users=${publicUsers.index?.total_users}`);
  }
}

async function main() {
  const publicRankingCounts = await validateRankingDataset(publicDataDir, "public/data");
  await validateRankingDataset(publicAllDataDir, "public/data/all", publicRankingCounts);
  const publicUsers = await validateUserDataset(publicDataDir, "public/data");
  counters.publicUsers = publicUsers.users.length;
  const allUsers = existsSync(path.join(publicAllDataDir, "users", "index.json"))
    ? await validateUserDataset(publicAllDataDir, "public/data/all")
    : null;
  counters.allUsers = allUsers?.users?.length || 0;
  await validateAllMirrorCoverage(publicUsers, allUsers);

  if (issues.length > 0) {
    console.error(`資料守恆檢查失敗：${issues.length} 個問題`);
    for (const issue of issues.slice(0, 50)) {
      console.error(`- ${issue}`);
    }
    if (issues.length > 50) {
      console.error(`...還有 ${issues.length - 50} 個問題`);
    }
    process.exit(1);
  }

  console.log(
    `資料守恆檢查通過：公開使用者 ${counters.publicUsers}、完整鏡像使用者 ${counters.allUsers}、使用者成績檢查 ${counters.userEntries} 筆、重複來源成績 ${counters.duplicateEntries} 筆、排行榜薄索引列 ${counters.rankingRows} 筆、細節 entries ${counters.rankingDetailRows} 筆、完整鏡像 hidden 排行榜條目 ${counters.allHiddenRankingEntries} 筆。`,
  );
}

main().catch((error) => {
  console.error(`資料守恆檢查失敗：${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
