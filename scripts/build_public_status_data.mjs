import { existsSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceStatusPath = path.join(rootDir, "data", "update_status.json");
const globalStatsPath = path.join(rootDir, "public", "data", "global_stats.json");
const publicStatusPath = path.join(rootDir, "public", "data", "update_status.json");

const workflowSchedule = Object.freeze({
  workflow_cron_utc: "17,47 * * * *",
  interval_minutes: 30,
  incremental_lookback_hours: 24,
  no_clear_retry_hours: 24,
  delayed_scan_recent_gap_hours: 24,
  delayed_scan_lookback_hours: 72,
  history_scan_window_hours: 168,
  history_scan_windows_per_run: 1,
  history_max_deep_reports_per_run: 600,
  history_max_deep_reports_per_group_per_run: 150,
});

async function readJson(filePath, fallback = null) {
  if (!existsSync(filePath)) {
    return fallback;
  }

  return JSON.parse(await readFile(filePath, "utf8"));
}

function firstText(...values) {
  for (const value of values) {
    const text = String(value || "").trim();
    if (text) {
      return text;
    }
  }
  return null;
}

const sourceStatus = await readJson(sourceStatusPath, {});
const globalStats = await readJson(globalStatsPath, {});
const rankingsUpdatedAtIso = firstText(
  globalStats?.rankings_updated_at_iso,
  sourceStatus?.rankings_updated_at_iso,
  globalStats?.generated_at_iso,
);
const updatedAtIso = firstText(sourceStatus?.updated_at_iso, rankingsUpdatedAtIso);

const publicStatus = {
  schema_version: 1,
  format: "public_update_status_v1",
  updated_at_iso: updatedAtIso,
  rankings_updated_at_iso: rankingsUpdatedAtIso,
  event: firstText(sourceStatus?.event),
  branch: firstText(sourceStatus?.branch),
  run_id: firstText(sourceStatus?.run_id),
  run_attempt: Number(sourceStatus?.run_attempt) || null,
  run_url: firstText(sourceStatus?.run_url),
  total_character_count: Number(globalStats?.total_character_count ?? sourceStatus?.total_character_count) || 0,
  total_entry_count: Number(globalStats?.total_entry_count ?? sourceStatus?.total_entry_count) || 0,
  schedule: workflowSchedule,
};

await mkdir(path.dirname(publicStatusPath), { recursive: true });
await writeFile(publicStatusPath, `${JSON.stringify(publicStatus, null, 2)}\n`, "utf8");
console.log(`已產生公開更新狀態：${path.relative(rootDir, publicStatusPath)}`);
