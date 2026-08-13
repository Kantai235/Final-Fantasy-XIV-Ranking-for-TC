import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileWithRetry } from "./write_file_with_retry.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicAllDataDir = path.join(publicDataDir, "all");
const rankingSourceDir = path.join(rootDir, "data", "rankings");
const rankingInputDir = path.join(publicDataDir, "rankings");
const allRankingInputDir = path.join(publicAllDataDir, "rankings");
const rankingTableDirName = "ranking-tables";
const rankingDetailDirName = "ranking-details";
const gameVersionsConfigPath = path.join(rootDir, "config", "game_versions.json");

export const tableColumns = [
  "id",
  "character_name",
  "server",
  "original_server",
  "job",
  "dps",
  "rdps",
  "adps",
  "active_percent",
  "gcd_coverage",
  "healing_stats",
  "tank_stats",
  "co_healer",
  "co_tank",
  "clear_time_seconds",
  "recorded_at_iso",
  "game_version",
  "duplicate_count",
  "rank",
  "is_obsolete_record",
  "version_status",
  "version_cutoff_iso",
  "has_report_detail",
];

const healerJobs = new Set(["WhiteMage", "Scholar", "Astrologian", "Sage"]);
const tankJobs = new Set(["Paladin", "Warrior", "DarkKnight", "Gunbreaker"]);
const supportRoleJobs = {
  healer: healerJobs,
  tank: tankJobs,
};
const rankingSupportContextCache = new Map();

function assertInside(parent, target) {
  const relative = path.relative(parent, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`輸出路徑超出允許目錄：${path.relative(rootDir, target)}`);
  }
}

async function readJson(filePath, fallback = null) {
  if (!existsSync(filePath)) {
    return fallback;
  }

  return JSON.parse(await readFile(filePath, "utf8"));
}

async function writeJson(filePath, data) {
  assertInside(publicDataDir, filePath);
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFileWithRetry(filePath, `${JSON.stringify(data)}\n`, "utf8");
}

function normalizeGameVersions(config) {
  const sourceVersions = Array.isArray(config?.versions) ? config.versions : [];
  if (sourceVersions.length === 0) {
    throw new Error("config/game_versions.json 必須提供至少一個繁中服版本區間。");
  }

  const seenPatches = new Set();
  let previousStartAt = -Infinity;

  return sourceVersions.map((version, index) => {
    const patch = String(version?.patch || "").trim();
    const label = String(version?.label || patch).trim();
    const startsAtIso = version?.starts_at_iso ?? null;
    const startsAt = startsAtIso === null ? null : new Date(startsAtIso).getTime();

    if (!patch || !label) {
      throw new Error(`config/game_versions.json 的 versions[${index}] 缺少 patch 或 label。`);
    }
    if (seenPatches.has(patch)) {
      throw new Error(`config/game_versions.json 的 patch 不可重複：${patch}`);
    }
    if (index === 0 && startsAtIso !== null) {
      throw new Error("config/game_versions.json 的第一個版本必須以 starts_at_iso: null 表示最早的已收錄版本。");
    }
    if (index > 0 && (!Number.isFinite(startsAt) || startsAt <= previousStartAt)) {
      throw new Error("config/game_versions.json 的版本開放時間必須依序遞增。");
    }

    seenPatches.add(patch);
    if (startsAt !== null) {
      previousStartAt = startsAt;
    }
    return {
      patch,
      label,
      starts_at_iso: startsAtIso,
    };
  });
}

const gameVersions = normalizeGameVersions(await readJson(gameVersionsConfigPath));

function resolveEntryGameVersion(entry) {
  const explicitPatch = String(entry?.game_version || "").trim();
  if (gameVersions.some((version) => version.patch === explicitPatch)) {
    return explicitPatch;
  }

  const recordedAt = new Date(entry?.recorded_at_iso || entry?.report_start_time_iso || "").getTime();
  if (!Number.isFinite(recordedAt)) {
    return null;
  }

  // 排行榜來源是 append-only 的 fight 紀錄，不能依今天的副本狀態或 scan_start_date 推測。
  // 唯一可靠的競技版本依據是該場紀錄時間落在哪一個繁中服改版區間；這也讓未來新增
  // 版本時只要更新 config/game_versions.json，就能在重建薄索引時自動補上新分類。
  let matchedVersion = null;
  for (const version of gameVersions) {
    const startsAt = version.starts_at_iso === null ? null : new Date(version.starts_at_iso).getTime();
    if (startsAt === null || recordedAt >= startsAt) {
      matchedVersion = version;
      continue;
    }
    break;
  }

  return matchedVersion?.patch || null;
}

function normalizeGcdCoverageForTable(value) {
  if (typeof value === "number") {
    return value;
  }
  if (value && typeof value === "object" && Number.isFinite(Number(value.percent))) {
    return Number(value.percent);
  }
  return null;
}

function toFiniteNumber(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function compactHealingStats(value) {
  if (!value || typeof value !== "object") {
    return null;
  }

  return {
    hps: toFiniteNumber(value.hps),
    pure_healing: toFiniteNumber(value.pure_healing),
    protection: toFiniteNumber(value.protection),
    overheal_percent: toFiniteNumber(value.overheal_percent),
  };
}

export function compactTankStats(value) {
  if (!value || typeof value !== "object") {
    return null;
  }

  return {
    damage_taken: toFiniteNumber(value.damage_taken),
    self_healing: toFiniteNumber(value.self_healing),
    personal_protection: toFiniteNumber(value.personal_protection),
    team_protection: toFiniteNumber(value.team_protection),
    // 「減傷覆蓋」目前採有效 activation 比例：只有減傷狀態時窗內真的發生傷害，
    // 該次啟用才算有效。這不是單招實際減免量，也不是 buff 持續時間占整場的比例；
    // 前端提示必須保留這個口徑，避免把不同意義的百分比混為一談。
    mitigation_coverage_percent: toFiniteNumber(value.mitigation_coverage?.effective_activation_percent),
  };
}

function calculateActivePercent(player, fight) {
  const activeTimeMs = toFiniteNumber(player?.active_time_ms);
  const durationMs =
    toFiniteNumber(fight?.fflogs_total_time_ms)
    ?? toFiniteNumber(fight?.clear_time_ms)
    ?? ((toFiniteNumber(fight?.clear_time_seconds) ?? 0) * 1000);
  if (activeTimeMs === null || durationMs <= 0) {
    return null;
  }
  return Number(((activeTimeMs / durationMs) * 100).toFixed(2));
}

function playerMatchesEntry(player, entry) {
  const entrySourceId = entry.fflogs_source_id ?? entry.fflogs_id ?? entry.source_id;
  const playerSourceId = player?.fflogs_source_id ?? player?.fflogs_id ?? player?.source_id;
  if (entrySourceId !== null && entrySourceId !== undefined && playerSourceId !== null && playerSourceId !== undefined) {
    return String(entrySourceId) === String(playerSourceId);
  }

  return (player?.name || player?.character_name) === entry.character_name
    && player?.server === entry.server
    && player?.job === entry.job;
}

function buildSupportCompanion(player, fight, role) {
  const healingStats = role === "healer" ? compactHealingStats(player?.healing_stats) : null;
  const tankStats = role === "tank" ? compactTankStats(player?.tank_stats) : null;
  if (!healingStats && !tankStats) {
    return null;
  }

  return {
    character_name: player?.name || player?.character_name || "",
    server: player?.server || "",
    job: player?.job || "",
    active_percent: toFiniteNumber(player?.active_percent) ?? calculateActivePercent(player, fight),
    gcd_coverage: normalizeGcdCoverageForTable(player?.gcd_coverage),
    rdps: toFiniteNumber(player?.rdps ?? player?.dps),
    ...(healingStats ? { healing_stats: healingStats } : {}),
    ...(tankStats ? { tank_stats: tankStats } : {}),
  };
}

function supportCompanionCandidateScore(candidate, targetEntry, reportCode, fightId) {
  let score = 0;
  if (String(targetEntry.report_code || "") === String(reportCode || "") && String(targetEntry.fight_id ?? "") === String(fightId ?? "")) {
    score += 100;
  }
  for (const value of [
    candidate.active_percent,
    candidate.gcd_coverage,
    candidate.rdps,
    candidate.healing_stats?.hps,
    candidate.healing_stats?.pure_healing,
    candidate.healing_stats?.protection,
    candidate.healing_stats?.overheal_percent,
    candidate.tank_stats?.damage_taken,
    candidate.tank_stats?.self_healing,
    candidate.tank_stats?.personal_protection,
    candidate.tank_stats?.team_protection,
    candidate.tank_stats?.mitigation_coverage_percent,
  ]) {
    if (value !== null && value !== undefined) {
      score += 1;
    }
  }
  return score;
}

function addSupportTarget(index, key, target) {
  if (!key) {
    return;
  }
  const targets = index.get(key) || new Set();
  targets.add(target);
  index.set(key, targets);
}

function collectReports(shard) {
  if (Array.isArray(shard)) {
    return shard;
  }
  if (Array.isArray(shard?.reports)) {
    return shard.reports;
  }
  if (shard?.reports && typeof shard.reports === "object") {
    return Object.values(shard.reports);
  }
  return Object.values(shard || {}).filter((report) => report && typeof report === "object" && Array.isArray(report.fights));
}

function collectSupportCompanionCandidates(context, report) {
  const reportCode = report?.report_code || "";
  for (const fight of report?.fights || []) {
    const targets = new Set([
      ...(context.companionTargetsByFightHash.get(fight?.fight_hash) || []),
      ...(context.companionTargetsByReportFight.get(`${reportCode}:${fight?.fight_id ?? ""}`) || []),
    ]);
    if (targets.size === 0) {
      continue;
    }

    for (const target of targets) {
      const rolePlayers = (fight?.players || []).filter((player) => supportRoleJobs[target.role]?.has(player?.job));
      // 標準八人高難度副本的雙坦、雙補都能唯一互相配對。滅本等聯盟戰同場會有
      // 多名同職能玩家，來源又沒有聯盟小隊編號；此時不能依陣列順序猜測搭檔。
      if (rolePlayers.length !== 2) {
        continue;
      }
      const playerIndex = rolePlayers.findIndex((player) => playerMatchesEntry(player, target));
      if (playerIndex < 0) {
        continue;
      }
      const candidate = buildSupportCompanion(rolePlayers[playerIndex === 0 ? 1 : 0], fight, target.role);
      if (!candidate) {
        continue;
      }
      const score = supportCompanionCandidateScore(candidate, target, reportCode, fight?.fight_id);
      const current = context.companionCandidates.get(target.id);
      if (!current || score > current.score) {
        context.companionCandidates.set(target.id, { role: target.role, score, value: candidate });
      }
    }
  }
}

export function createRankingSupportContext(sourceRanking) {
  const context = {
    supportByEntryId: new Map(),
    companionTargetsByFightHash: new Map(),
    companionTargetsByReportFight: new Map(),
    companionCandidates: new Map(),
    coHealerByEntryId: new Map(),
    coTankByEntryId: new Map(),
  };

  for (const entry of sourceRanking?.ranking_entries || []) {
    if (!entry?.id) {
      continue;
    }
    const healingStats = compactHealingStats(entry.healing_stats);
    const tankStats = compactTankStats(entry.tank_stats);
    if (healingStats || tankStats) {
      context.supportByEntryId.set(entry.id, { healing_stats: healingStats, tank_stats: tankStats });
    }
    const role = healingStats && healerJobs.has(entry.job)
      ? "healer"
      : tankStats && tankJobs.has(entry.job)
        ? "tank"
        : null;
    if (!role) {
      continue;
    }
    const target = {
      id: entry.id,
      character_name: entry.character_name || entry.name || "",
      server: entry.server || "",
      job: entry.job || "",
      fflogs_source_id: entry.fflogs_source_id ?? entry.fflogs_id ?? entry.source_id ?? null,
      report_code: entry.report_code || "",
      fight_id: entry.fight_id ?? null,
      role,
    };
    addSupportTarget(context.companionTargetsByFightHash, entry.fight_hash, target);
    addSupportTarget(context.companionTargetsByReportFight, `${target.report_code}:${target.fight_id ?? ""}`, target);
  }

  return context;
}

export function addRankingSupportReportShard(context, shard) {
  for (const report of collectReports(shard)) {
    collectSupportCompanionCandidates(context, report);
  }
}

export function finalizeRankingSupportContext(context) {
  for (const [entryId, candidate] of context.companionCandidates) {
    const output = candidate.role === "tank" ? context.coTankByEntryId : context.coHealerByEntryId;
    output.set(entryId, candidate.value);
  }
  delete context.companionTargetsByFightHash;
  delete context.companionTargetsByReportFight;
  delete context.companionCandidates;
  return context;
}

export async function buildRankingSupportContext(fileName) {
  if (rankingSupportContextCache.has(fileName)) {
    return rankingSupportContextCache.get(fileName);
  }

  const [sourceRanking, hiddenRanking] = await Promise.all([
    readJson(path.join(rankingSourceDir, fileName), null),
    readJson(path.join(allRankingInputDir, fileName), null),
  ]);
  // Hidden delta 的排行列不一定存在於一般公開 ranking_entries，但仍來自同一批權威
  // report 分片。先把兩邊目標合併後只掃描一次分片，才能讓額外檢視與公開頁面使用
  // 相同的雙坦／雙補配對規則，也避免為兩份輸出重複讀取數萬份 report JSON。
  const context = createRankingSupportContext({
    ranking_entries: [
      ...(sourceRanking?.ranking_entries || []),
      ...(hiddenRanking?.ranking_entries || []),
    ],
  });

  if (context.companionTargetsByFightHash.size > 0 || context.companionTargetsByReportFight.size > 0) {
    const reportDir = path.join(rankingSourceDir, `${path.basename(fileName, ".json")}.reports`);
    if (existsSync(reportDir)) {
      const shardFiles = (await readdir(reportDir)).filter((name) => name.endsWith(".json")).sort();
      for (const shardFile of shardFiles) {
        const shard = await readJson(path.join(reportDir, shardFile), null);
        addRankingSupportReportShard(context, shard);
      }
    }
  }

  finalizeRankingSupportContext(context);
  rankingSupportContextCache.set(fileName, context);
  return context;
}

export function buildTableEntry(entry, supportContext = null) {
  const support = supportContext?.supportByEntryId?.get(entry?.id) || {};
  const compact = {
    id: entry?.id || "",
    character_name: entry?.character_name || entry?.name || "",
    server: entry?.server || "",
    original_server: entry?.original_server || undefined,
    job: entry?.job || "",
    dps: entry?.dps ?? null,
    rdps: entry?.rdps ?? entry?.dps ?? null,
    adps: entry?.adps ?? null,
    active_percent: entry?.active_percent ?? null,
    gcd_coverage: normalizeGcdCoverageForTable(entry?.gcd_coverage),
    healing_stats: support.healing_stats ?? compactHealingStats(entry?.healing_stats),
    tank_stats: support.tank_stats ?? compactTankStats(entry?.tank_stats),
    co_healer: supportContext?.coHealerByEntryId?.get(entry?.id) ?? null,
    co_tank: supportContext?.coTankByEntryId?.get(entry?.id) ?? null,
    clear_time_seconds: entry?.clear_time_seconds ?? null,
    recorded_at_iso: entry?.recorded_at_iso || entry?.report_start_time_iso || null,
    game_version: resolveEntryGameVersion(entry),
    duplicate_count: entry?.duplicate_count ?? 1,
    rank: entry?.rank ?? null,
    is_obsolete_record: typeof entry?.is_obsolete_record === "boolean" ? entry.is_obsolete_record : undefined,
    version_status: entry?.version_status || undefined,
    version_cutoff_iso: entry?.version_cutoff_iso || undefined,
    has_report_detail: Boolean(entry?.report_code || entry?.report_url || entry?.fight_id || entry?.fflogs_source_id),
  };

  return tableColumns.map((column) => compact[column] ?? null);
}

function buildTableRows(entries, supportContext) {
  return (entries || [])
    .filter((entry) => entry && typeof entry === "object")
    .map((entry) => buildTableEntry(entry, supportContext));
}

function isHiddenEntry(entry) {
  return Boolean(entry?.report_hidden || entry?.hidden_report);
}

function tableRowId(row, columns) {
  if (Array.isArray(row)) {
    const idIndex = columns.indexOf("id");
    return idIndex >= 0 ? row[idIndex] : null;
  }
  return row?.id || null;
}

function filterRowsByIds(rows, columns, idSet) {
  return (Array.isArray(rows) ? rows : []).filter((row) => idSet.has(tableRowId(row, columns)));
}

function collectRowOrder(rows, columns) {
  return (Array.isArray(rows) ? rows : []).map((row) => tableRowId(row, columns)).filter(Boolean);
}

function collectDetailEntries(ranking) {
  const details = {};
  for (const entry of Array.isArray(ranking?.ranking_entries) ? ranking.ranking_entries : []) {
    if (!entry || typeof entry !== "object" || !entry.id) {
      continue;
    }
    details[entry.id] = entry;
  }

  return details;
}

function mergeEntriesByOrder(baseEntries, deltaEntries, order) {
  const entriesById = new Map();
  for (const entry of [...(baseEntries || []), ...(deltaEntries || [])]) {
    if (entry?.id) {
      entriesById.set(entry.id, entry);
    }
  }

  const orderedEntries = [];
  const usedIds = new Set();
  for (const id of Array.isArray(order) ? order : []) {
    const entry = entriesById.get(id);
    if (entry) {
      orderedEntries.push(entry);
      usedIds.add(id);
    }
  }
  if (Array.isArray(order) && order.length > 0) {
    return orderedEntries;
  }

  for (const entry of [...(baseEntries || []), ...(deltaEntries || [])]) {
    if (entry?.id && !usedIds.has(entry.id)) {
      orderedEntries.push(entry);
      usedIds.add(entry.id);
    }
  }

  return orderedEntries;
}

async function resolveRankingDelta(ranking, fileName) {
  if (ranking?.format !== "ranking_hidden_delta_v1") {
    return ranking;
  }

  const basePathText = ranking.base_path || `data/rankings/${fileName}`;
  const basePath = path.join(publicDataDir, basePathText.replace(/^data\//, ""));
  const baseRanking = await readJson(basePath, null);
  if (!baseRanking || typeof baseRanking !== "object") {
    throw new Error(`找不到 hidden delta 的公開排行榜底稿：${basePathText}`);
  }

  const merged = {
    ...baseRanking,
    schema_version: ranking.schema_version || baseRanking.schema_version || 1,
    encounter: ranking.encounter || baseRanking.encounter || null,
    updated_at: ranking.updated_at ?? baseRanking.updated_at ?? null,
    updated_at_iso: ranking.updated_at_iso ?? baseRanking.updated_at_iso ?? null,
    hidden_reports_included: true,
    ranking_entries: mergeEntriesByOrder(
      baseRanking.ranking_entries,
      ranking.ranking_entries,
      ranking.ranking_entry_order,
    ),
  };

  return merged;
}

function buildRankingDeltaPayload(ranking, fileName) {
  return {
    schema_version: ranking.schema_version || 1,
    format: "ranking_hidden_delta_v1",
    base_path: `data/rankings/${fileName}`,
    encounter: ranking.encounter || null,
    updated_at: ranking.updated_at ?? null,
    updated_at_iso: ranking.updated_at_iso ?? null,
    hidden_reports_included: true,
    ranking_entry_order: (ranking.ranking_entries || []).map((entry) => entry?.id).filter(Boolean),
    ranking_entries: (ranking.ranking_entries || []).filter(isHiddenEntry),
  };
}

async function buildDataset({ label, inputDir, outputBaseDir, detailPathPrefix, deltaMode = false }) {
  if (!existsSync(inputDir)) {
    console.log(`略過 ${label} 排行榜薄索引，找不到 ${path.relative(rootDir, inputDir)}。`);
    return;
  }

  const tableOutputDir = path.join(outputBaseDir, rankingTableDirName);
  const detailOutputDir = path.join(outputBaseDir, rankingDetailDirName);
  assertInside(publicDataDir, tableOutputDir);
  assertInside(publicDataDir, detailOutputDir);
  await rm(tableOutputDir, { recursive: true, force: true });
  await rm(detailOutputDir, { recursive: true, force: true });
  await mkdir(tableOutputDir, { recursive: true });
  await mkdir(detailOutputDir, { recursive: true });

  const rankingFiles = (await readdir(inputDir)).filter((fileName) => fileName.endsWith(".json")).sort();
  let totalRows = 0;

  for (const fileName of rankingFiles) {
    const encounterKey = path.basename(fileName, ".json");
    const rawRanking = await readJson(path.join(inputDir, fileName), null);
    const ranking = await resolveRankingDelta(rawRanking, fileName);
    if (!ranking || typeof ranking !== "object") {
      continue;
    }

    const detailPath = `${detailPathPrefix}/${rankingDetailDirName}/${fileName}`;
    const supportContext = await buildRankingSupportContext(fileName);
    const tableRows = buildTableRows(ranking.ranking_entries, supportContext);
    const detailEntries = collectDetailEntries(ranking);
    const hiddenEntryIds = new Set(
      Object.entries(detailEntries)
        .filter(([, entry]) => isHiddenEntry(entry))
        .map(([id]) => id),
    );
    const tablePayload = {
      schema_version: 1,
      format: deltaMode ? "ranking_table_hidden_delta_v1" : "ranking_table_index_v1",
      encounter: ranking.encounter || null,
      updated_at: ranking.updated_at ?? null,
      updated_at_iso: ranking.updated_at_iso ?? null,
      hidden_reports_included: Boolean(ranking.hidden_reports_included),
      detail_path: detailPath,
      // 版本設定只在每個已載入的薄索引附帶一份極小中繼資料；前端以列上的 game_version
      // 做累積篩選，不輸出 7.0、7.05…等多套完整排行榜，避免 GitHub Pages payload 成倍成長。
      game_versions: gameVersions,
      ...(deltaMode ? { base_path: `data/${rankingTableDirName}/${fileName}` } : {}),
      table_columns: tableColumns,
      table_rows: deltaMode ? filterRowsByIds(tableRows, tableColumns, hiddenEntryIds) : tableRows,
    };
    totalRows += tablePayload.table_rows.length;

    if (deltaMode) {
      tablePayload.table_row_order = collectRowOrder(tableRows, tableColumns);
    }

    await writeJson(path.join(tableOutputDir, fileName), tablePayload);
    await writeJson(path.join(detailOutputDir, fileName), {
      schema_version: 1,
      format: deltaMode ? "ranking_detail_hidden_delta_v1" : "ranking_detail_entries_v1",
      encounter: ranking.encounter || null,
      updated_at: ranking.updated_at ?? null,
      updated_at_iso: ranking.updated_at_iso ?? null,
      hidden_reports_included: Boolean(ranking.hidden_reports_included),
      ...(deltaMode ? { base_path: `data/${rankingDetailDirName}/${fileName}` } : {}),
      entries: deltaMode
        ? Object.fromEntries(Object.entries(detailEntries).filter(([id]) => hiddenEntryIds.has(id)))
        : detailEntries,
    });
    if (deltaMode) {
      await writeJson(path.join(inputDir, fileName), buildRankingDeltaPayload(ranking, fileName));
    }
    console.log(`已產生 ${label} 排行榜薄索引：${encounterKey}`);
  }

  console.log(`已產生 ${label} 排行榜薄索引：${rankingFiles.length} 個副本、${totalRows} 列。`);
}

async function main() {
  await buildDataset({
    label: "預設公開",
    inputDir: rankingInputDir,
    outputBaseDir: publicDataDir,
    detailPathPrefix: "data",
  });

  await buildDataset({
    label: "Hidden delta",
    inputDir: allRankingInputDir,
    outputBaseDir: publicAllDataDir,
    detailPathPrefix: "data/all",
    deltaMode: true,
  });
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await main();
}
