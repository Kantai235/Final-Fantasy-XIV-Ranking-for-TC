import { existsSync } from "node:fs";
import { mkdir, readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { writeFileWithRetry } from "./write_file_with_retry.mjs";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const publicDataDir = path.join(rootDir, "public", "data");
const publicDetailDir = path.join(publicDataDir, "ranking-details");
const hiddenDetailDir = path.join(publicDataDir, "all", "ranking-details");
const reportColumns = [
  "report_code",
  "first_recorded_at_iso",
  "latest_recorded_at_iso",
  "entry_count",
  "hidden_entry_count",
  "character_count",
  "encounters",
  "fights",
];
const encounterColumns = [
  "encounter_key",
  "entry_count",
  "hidden_entry_count",
  "character_count",
  "fight_ids",
  "latest_recorded_at_iso",
];
const fightColumns = [
  "fight_id",
  "entry_count",
  "hidden_entry_count",
  "character_count",
  "encounter_keys",
  "latest_recorded_at_iso",
];

async function readJson(filePath, fallback = null) {
  if (!existsSync(filePath)) {
    return fallback;
  }

  return JSON.parse(await readFile(filePath, "utf8"));
}

async function writeJson(filePath, data) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFileWithRetry(filePath, `${JSON.stringify(data)}\n`, "utf8");
}

function normalizeReportCode(value) {
  return String(value || "").trim();
}

function updateIsoRange(target, isoText) {
  const text = String(isoText || "").trim();
  if (!text) {
    return;
  }

  if (!target.first_recorded_at_iso || text < target.first_recorded_at_iso) {
    target.first_recorded_at_iso = text;
  }
  if (!target.latest_recorded_at_iso || text > target.latest_recorded_at_iso) {
    target.latest_recorded_at_iso = text;
  }
}

function ensureReport(reportsByCode, reportCode) {
  if (!reportsByCode.has(reportCode)) {
    reportsByCode.set(reportCode, {
      report_code: reportCode,
      first_recorded_at_iso: null,
      latest_recorded_at_iso: null,
      entry_count: 0,
      hidden_entry_count: 0,
      character_keys: new Set(),
      encounters: new Map(),
      fights: new Map(),
    });
  }

  return reportsByCode.get(reportCode);
}

function ensureEncounter(report, encounter) {
  if (!report.encounters.has(encounter.key)) {
    report.encounters.set(encounter.key, {
      encounter_key: encounter.key,
      encounter_name: encounter.name,
      encounter_category: encounter.category,
      entry_count: 0,
      hidden_entry_count: 0,
      character_keys: new Set(),
      fight_ids: new Set(),
      latest_recorded_at_iso: null,
    });
  }

  return report.encounters.get(encounter.key);
}

function ensureFight(report, fightId) {
  const key = String(fightId || "");
  if (!report.fights.has(key)) {
    report.fights.set(key, {
      fight_id: Number(fightId) || null,
      entry_count: 0,
      hidden_entry_count: 0,
      character_keys: new Set(),
      encounter_keys: new Set(),
      latest_recorded_at_iso: null,
    });
  }

  return report.fights.get(key);
}

function finalizeReport(report) {
  const encounters = Array.from(report.encounters.values())
    .map((encounter) => [
      encounter.encounter_key,
      encounter.entry_count,
      encounter.hidden_entry_count,
      encounter.character_keys.size,
      Array.from(encounter.fight_ids).sort((left, right) => left - right),
      encounter.latest_recorded_at_iso,
    ])
    .sort((left, right) => {
      const timeCompare = String(right[5] || "").localeCompare(String(left[5] || ""));
      return timeCompare || String(left[0]).localeCompare(String(right[0]));
    });

  const fights = Array.from(report.fights.values())
    .map((fight) => [
      fight.fight_id,
      fight.entry_count,
      fight.hidden_entry_count,
      fight.character_keys.size,
      Array.from(fight.encounter_keys).sort(),
      fight.latest_recorded_at_iso,
    ])
    .sort((left, right) => {
      if (left[0] === null) {
        return 1;
      }
      if (right[0] === null) {
        return -1;
      }
      return left[0] - right[0];
    });

  return [
    report.report_code,
    report.first_recorded_at_iso,
    report.latest_recorded_at_iso,
    report.entry_count,
    report.hidden_entry_count,
    report.character_keys.size,
    encounters,
    fights,
  ];
}

async function buildIndex({ label, detailDir, outputPath, hiddenDelta = false }) {
  if (!existsSync(detailDir)) {
    console.log(`略過 ${label} Logs 狀態索引，找不到 ${path.relative(rootDir, detailDir)}。`);
    return;
  }

  const encounters = await readJson(path.join(publicDataDir, "encounters.json"), []);
  const encounterByKey = new Map(
    (Array.isArray(encounters) ? encounters : []).map((encounter) => [
      encounter.key,
      {
        key: encounter.key,
        name: encounter.name || encounter.key,
        category: encounter.category || "其他",
      },
    ]),
  );
  const files = (await readdir(detailDir)).filter((fileName) => fileName.endsWith(".json")).sort();
  const reportsByCode = new Map();

  for (const fileName of files) {
    const encounterKey = path.basename(fileName, ".json");
    const encounter = encounterByKey.get(encounterKey) || {
      key: encounterKey,
      name: encounterKey,
      category: "其他",
    };
    const payload = await readJson(path.join(detailDir, fileName), null);
    const entries = Object.values(payload?.entries || {});

    for (const entry of entries) {
      const reportCode = normalizeReportCode(entry?.report_code);
      if (!reportCode) {
        continue;
      }

      const report = ensureReport(reportsByCode, reportCode);
      const fight = ensureFight(report, entry.fight_id);
      const encounterBucket = ensureEncounter(report, encounter);
      const characterKey = `${entry.character_name || ""}@${entry.server || ""}`;
      const isHidden = Boolean(entry.report_hidden || entry.hidden_report);

      report.entry_count += 1;
      report.hidden_entry_count += isHidden ? 1 : 0;
      report.character_keys.add(characterKey);
      updateIsoRange(report, entry.recorded_at_iso);

      encounterBucket.entry_count += 1;
      encounterBucket.hidden_entry_count += isHidden ? 1 : 0;
      encounterBucket.character_keys.add(characterKey);
      if (Number.isFinite(Number(entry.fight_id))) {
        encounterBucket.fight_ids.add(Number(entry.fight_id));
      }
      if (!encounterBucket.latest_recorded_at_iso || String(entry.recorded_at_iso || "") > encounterBucket.latest_recorded_at_iso) {
        encounterBucket.latest_recorded_at_iso = entry.recorded_at_iso || null;
      }

      fight.entry_count += 1;
      fight.hidden_entry_count += isHidden ? 1 : 0;
      fight.character_keys.add(characterKey);
      fight.encounter_keys.add(encounter.key);
      if (!fight.latest_recorded_at_iso || String(entry.recorded_at_iso || "") > fight.latest_recorded_at_iso) {
        fight.latest_recorded_at_iso = entry.recorded_at_iso || null;
      }
    }
  }

  const reports = Array.from(reportsByCode.values())
    .map(finalizeReport)
    .sort((left, right) => {
      const timeCompare = String(right[2] || "").localeCompare(String(left[2] || ""));
      return timeCompare || String(left[0]).localeCompare(String(right[0]));
    });

  const output = {
    schema_version: 1,
    format: hiddenDelta ? "report_status_hidden_delta_v1" : "report_status_index_v1",
    ...(hiddenDelta ? { base_path: "data/report_status_index.json" } : {}),
    generated_at_iso: reports.reduce(
      (latest, report) => (report[2] && report[2] > latest ? report[2] : latest),
      "",
    ) || null,
    encounter_metadata: Array.from(encounterByKey.values()).sort((left, right) => left.key.localeCompare(right.key)),
    report_columns: reportColumns,
    encounter_columns: encounterColumns,
    fight_columns: fightColumns,
    report_count: reports.length,
    entry_count: reports.reduce((total, report) => total + report[3], 0),
    hidden_entry_count: reports.reduce((total, report) => total + report[4], 0),
    reports,
  };

  await writeJson(outputPath, output);
  console.log(`已產生 ${label} Logs 狀態索引：${reports.length} 份 report。`);
}

await buildIndex({
  label: "公開",
  detailDir: publicDetailDir,
  outputPath: path.join(publicDataDir, "report_status_index.json"),
});

await buildIndex({
  label: "Hidden delta",
  detailDir: hiddenDetailDir,
  outputPath: path.join(publicDataDir, "all", "report_status_index.json"),
  hiddenDelta: true,
});
