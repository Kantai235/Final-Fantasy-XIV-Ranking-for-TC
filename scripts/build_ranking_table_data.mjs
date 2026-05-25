import { existsSync } from "node:fs";
import { mkdir, readdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicAllDataDir = path.join(publicDataDir, "all");
const rankingInputDir = path.join(publicDataDir, "rankings");
const allRankingInputDir = path.join(publicAllDataDir, "rankings");
const rankingTableDirName = "ranking-tables";
const rankingDetailDirName = "ranking-details";

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
  await writeFile(filePath, `${JSON.stringify(data)}\n`, "utf8");
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

function collectDetailEntries(ranking) {
  const details = {};
  const groups = [
    ranking?.ranking_entries,
    ...Object.values(ranking?.version_ranking_entries || {}),
  ];

  for (const group of groups) {
    for (const entry of Array.isArray(group) ? group : []) {
      if (!entry || typeof entry !== "object" || !entry.id) {
        continue;
      }
      details[entry.id] = entry;
    }
  }

  return details;
}

async function buildDataset({ label, inputDir, outputBaseDir, detailPathPrefix }) {
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
    const ranking = await readJson(path.join(inputDir, fileName), null);
    if (!ranking || typeof ranking !== "object") {
      continue;
    }

    const detailPath = `${detailPathPrefix}/${rankingDetailDirName}/${fileName}`;
    const tablePayload = {
      schema_version: 1,
      format: "ranking_table_index_v1",
      encounter: ranking.encounter || null,
      updated_at: ranking.updated_at ?? null,
      updated_at_iso: ranking.updated_at_iso ?? null,
      hidden_reports_included: Boolean(ranking.hidden_reports_included),
      detail_path: detailPath,
      table_columns: tableColumns,
      table_rows: buildTableRows(ranking.ranking_entries),
    };
    totalRows += tablePayload.table_rows.length;

    if (ranking.version_cutoff) {
      tablePayload.version_cutoff = ranking.version_cutoff;
    }
    if (ranking.version_ranking_entries && typeof ranking.version_ranking_entries === "object") {
      tablePayload.version_table_rows = Object.fromEntries(
        Object.entries(ranking.version_ranking_entries).map(([versionMode, entries]) => [
          versionMode,
          buildTableRows(entries),
        ]),
      );
    }

    await writeJson(path.join(tableOutputDir, fileName), tablePayload);
    await writeJson(path.join(detailOutputDir, fileName), {
      schema_version: 1,
      format: "ranking_detail_entries_v1",
      encounter: ranking.encounter || null,
      updated_at: ranking.updated_at ?? null,
      updated_at_iso: ranking.updated_at_iso ?? null,
      hidden_reports_included: Boolean(ranking.hidden_reports_included),
      entries: collectDetailEntries(ranking),
    });
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
  label: "完整鏡像",
  inputDir: allRankingInputDir,
  outputBaseDir: publicAllDataDir,
  detailPathPrefix: "data/all",
});
