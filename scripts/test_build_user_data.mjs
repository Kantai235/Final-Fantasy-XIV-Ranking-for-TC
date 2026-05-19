import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const buildScriptPath = path.join(repoRoot, "scripts", "build_user_data.mjs");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function writeJson(filePath, data) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(data)}\n`, "utf8");
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

function runBuild(tempRoot) {
  const result = spawnSync(process.execPath, [buildScriptPath], {
    cwd: repoRoot,
    encoding: "utf8",
    env: {
      ...process.env,
      FFXIV_TC_ROOT_DIR: tempRoot,
    },
    windowsHide: true,
  });

  if (result.status !== 0) {
    throw new Error(`build_user_data.mjs failed\nstdout:\n${result.stdout}\nstderr:\n${result.stderr}`);
  }
}

async function createFixture(tempRoot) {
  const encounter = {
    key: "fixture_encounter",
    name: "測試副本",
    category: "零式",
    enabled: true,
    data_path: "data/rankings/fixture_encounter.json",
  };
  await writeJson(path.join(tempRoot, "public", "data", "encounters.json"), [encounter]);
  await writeJson(path.join(tempRoot, "config", "encounters.json"), [
    {
      ...encounter,
      zone_id: 999,
      encounter_id: 888,
      difficulty: 100,
      scan_start_date: "2026-01-01",
    },
  ]);

  await writeJson(path.join(tempRoot, "data", "rankings", "fixture_encounter.json"), {
    schema_version: 1,
    encounter: {
      key: encounter.key,
      name: encounter.name,
      category: encounter.category,
      zone_id: 999,
      encounter_id: 888,
      difficulty: 100,
    },
    updated_at_iso: "2026-01-02T03:04:05.000Z",
    ranking_entries: [
      {
        character_name: "測試角色",
        server: "鳳凰",
        job: "Paladin",
        dps: 100,
        rdps: 90,
        adps: 95,
        clear_time_ms: 600000,
        recorded_at_iso: "2026-01-02T03:00:00.000Z",
        rank: 1,
      },
    ],
    report_shards: ["data/rankings/fixture_encounter.reports/000.json"],
  });

  await writeJson(path.join(tempRoot, "data", "rankings", "fixture_encounter.reports", "000.json"), {
    RPT1: {
      report_code: "RPT1",
      title: "Fixture report",
      url: "https://www.fflogs.com/reports/RPT1",
      report_start_time_iso: "2026-01-02T02:50:00.000Z",
      fights: [
        {
          fight_id: 1,
          fight_hash: "fixture-fight",
          clear_time_ms: 600000,
          clear_time_seconds: 600,
          damage_time_ms: 550000,
          damage_time_seconds: 550,
          recorded_at: 1767322800000,
          recorded_at_iso: "2026-01-02T03:00:00.000Z",
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Paladin",
              dps: 100,
              rdps: 90,
              adps: 95,
              total_damage: 55000,
              active_time_ms: 500000,
              active_percent: 90.91,
              gcd_coverage: {
                percent: 94.43,
                covered_time_ms: 519365,
                denominator_ms: 550000,
                gcd_cast_count: 220,
                calculation_version: 1,
                source: "fflogs_casts_graph",
              },
              gcd_coverage_status: {
                state: "ok",
                calculation_version: 1,
                checked_at_iso: "2026-01-02T03:10:00.000Z",
              },
            },
            {
              name: "治療隊友",
              server: "伊弗利特",
              job: "WhiteMage",
              dps: 50,
              rdps: 60,
              adps: 55,
              total_damage: 27500,
              active_time_ms: 480000,
              active_percent: 87.27,
            },
          ],
        },
      ],
    },
    HIDDEN1: {
      report_code: "HIDDEN1",
      report_hidden: true,
      hidden_reason: "private_or_deleted",
      hidden_detected_at_iso: "2026-01-03T03:10:00.000Z",
      hidden_source: "fixture",
      title: "Hidden fixture report",
      url: "https://www.fflogs.com/reports/HIDDEN1",
      report_start_time_iso: "2026-01-03T02:50:00.000Z",
      fights: [
        {
          fight_id: 2,
          fight_hash: "hidden-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1767409200000,
          recorded_at_iso: "2026-01-03T03:00:00.000Z",
          players: [
            {
              name: "隱藏角色",
              server: "鳳凰",
              job: "BlackMage",
              dps: 999,
              rdps: 999,
              adps: 999,
              total_damage: 449550,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
  });
}

async function assertFixtureOutput(tempRoot, expectedGlobalStatsText, expectedServerCompareText) {
  const usersIndexPath = path.join(tempRoot, "public", "data", "users", "index.json");
  const allUsersIndexPath = path.join(tempRoot, "public", "data", "all", "users", "index.json");
  const globalStatsPath = path.join(tempRoot, "public", "data", "global_stats.json");
  const allGlobalStatsPath = path.join(tempRoot, "public", "data", "all", "global_stats.json");
  const serverComparePath = path.join(tempRoot, "public", "data", "server_compare.json");
  const usersIndex = await readJson(usersIndexPath);
  const allUsersIndex = await readJson(allUsersIndexPath);
  const globalStatsText = await readFile(globalStatsPath, "utf8");
  const globalStats = JSON.parse(globalStatsText);
  const allGlobalStats = await readJson(allGlobalStatsPath);
  const serverCompareText = await readFile(serverComparePath, "utf8");
  const serverCompare = JSON.parse(serverCompareText);

  assert(usersIndex.generated_at_iso === "2026-01-02T03:04:05.000Z", "使用者索引應使用 ranking 更新時間作為 generated_at_iso。");
  assert(globalStats.generated_at_iso === "2026-01-02T03:04:05.000Z", "全服統計應使用 ranking 更新時間作為 generated_at_iso。");
  assert(usersIndex.total_users === 3, "fixture 應產生兩位有公開成績的使用者與一位空白入口。");
  assert(globalStats.total_character_count === 2, "全服角色數應包含同場兩位玩家。");
  assert(globalStats.total_entry_count === 2, "全服 entry 數應包含兩筆玩家成績。");
  const hiddenUser = usersIndex.users.find((user) => user.character_name === "隱藏角色");
  assert(hiddenUser, "預設使用者索引應保留空白成績單入口。");
  assert(hiddenUser.servers.includes("鳳凰"), "空白入口應保留伺服器，讓同名角色查詢仍可辨識。");
  assert(hiddenUser.best_rdps === null, "空白入口不可帶入最佳 rDPS。");
  assert(hiddenUser.last_recorded_at_iso === null, "空白入口不可帶入最後紀錄時間。");
  assert(allUsersIndex.total_users === 3, "完整鏡像應納入所有 fixture 角色。");
  assert(allGlobalStats.total_character_count === 3, "完整全服統計應納入所有 fixture 角色。");
  assert(allGlobalStats.total_entry_count === 3, "完整全服統計應納入所有 fixture 成績。");
  const allHiddenUser = allUsersIndex.users.find((user) => user.character_name === "隱藏角色");
  assert(allHiddenUser, "完整鏡像使用者索引應包含對應角色。");
  assert(Array.isArray(globalStats.job_profiles) && globalStats.job_profiles.length === 2, "全服統計應產生職業專頁資料。");
  assert(serverCompare.summary.server_count === 2, "伺服器對比應包含兩個伺服器。");
  assert(serverCompare.servers.some((server) => server.server === "鳳凰"), "伺服器對比應包含鳳凰。");

  const hiddenUserData = await readJson(path.join(tempRoot, "public", hiddenUser.file_path));
  assert(hiddenUserData.summary.public_entry_count === 0, "空白成績單不可包含公開成績筆數。");
  assert(hiddenUserData.summary.encounter_count === 0, "空白成績單不可包含副本資料。");
  assert(hiddenUserData.summary.best_rdps === null, "空白成績單不可包含最佳分數。");
  assert(hiddenUserData.summary.last_recorded_at_iso === null, "空白成績單不可包含紀錄時間。");
  assert(hiddenUserData.encounters.length === 0, "空白成績單不可輸出副本成績。");
  assert(hiddenUserData.frequent_teammates.length === 0, "空白成績單不可輸出隊友資料。");

  const allHiddenUserData = await readJson(
    path.join(tempRoot, "public", "data", "all", "users", path.basename(allHiddenUser.file_path)),
  );
  const allHiddenEntry = allHiddenUserData.encounters[0]?.public_entries?.[0];
  assert(allHiddenUserData.summary.public_entry_count === 1, "完整鏡像成績單應包含對應成績。");
  assert(allHiddenEntry?.report_hidden === true, "完整鏡像成績單應保留來源狀態欄位。");
  assert(allHiddenEntry?.rdps === 999, "完整鏡像成績單應保留實際 rDPS。");

  const mainUser = usersIndex.users.find((user) => user.character_name === "測試角色");
  assert(mainUser, "使用者索引應包含測試角色。");
  const mainUserData = await readJson(path.join(tempRoot, "public", mainUser.file_path));
  assert(mainUserData.summary.best_rdps === 90, "測試角色最佳 rDPS 應正確彙整。");
  const mainUserEntry = mainUserData.encounters[0]?.public_entries?.[0];
  assert(mainUserEntry?.gcd_coverage?.percent === 94.43, "個人成績單應保留 GCD 覆蓋率。");
  assert(mainUserEntry?.gcd_coverage_status?.state === "ok", "個人成績單應保留 GCD 覆蓋率狀態。");
  assert(mainUserData.frequent_teammates[0]?.character_name === "治療隊友", "測試角色應彙整同場隊友。");

  if (expectedGlobalStatsText !== null) {
    assert(globalStatsText === expectedGlobalStatsText, "同一批 ranking 重建時 global_stats.json 應完全一致。");
  }
  if (expectedServerCompareText !== null) {
    assert(serverCompareText === expectedServerCompareText, "同一批 ranking 重建時 server_compare.json 應完全一致。");
  }

  return {
    globalStatsText,
    serverCompareText,
  };
}

async function main() {
  const tempRoot = await mkdtemp(path.join(os.tmpdir(), "ffxiv-tc-build-user-data-"));
  try {
    await createFixture(tempRoot);
    runBuild(tempRoot);
    const firstOutput = await assertFixtureOutput(tempRoot, null, null);
    runBuild(tempRoot);
    await assertFixtureOutput(tempRoot, firstOutput.globalStatsText, firstOutput.serverCompareText);
    console.log("build_user_data fixture test passed.");
  } finally {
    await rm(tempRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
