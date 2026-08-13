import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileWithRetry } from "./write_file_with_retry.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicAllDataDir = path.join(publicDataDir, "all");
const rankingInputDir = path.join(publicDataDir, "rankings");
const allRankingInputDir = path.join(publicAllDataDir, "rankings");
const rankingTableDirName = "ranking-tables";
const rankingDetailDirName = "ranking-details";
const gameVersionsConfigPath = path.join(rootDir, "config", "game_versions.json");

const tableColumns = [
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

function buildTableEntry(entry) {
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

function buildTableRows(entries) {
  return (entries || []).filter((entry) => entry && typeof entry === "object").map(buildTableEntry);
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
    const tableRows = buildTableRows(ranking.ranking_entries);
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
