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
              fflogs_id: 101,
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
    RPT1B: {
      report_code: "RPT1B",
      title: "Fixture mirrored report",
      url: "https://www.fflogs.com/reports/RPT1B",
      report_start_time_iso: "2026-01-02T02:51:00.000Z",
      fights: [
        {
          fight_id: 9,
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
              dps: 100.5,
              rdps: 90,
              adps: 95,
              total_damage: 55275,
              fflogs_id: 303,
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
    RPT2: {
      report_code: "RPT2",
      title: "Fixture DPS report",
      url: "https://www.fflogs.com/reports/RPT2",
      report_start_time_iso: "2026-01-02T02:45:00.000Z",
      fights: [
        {
          fight_id: 3,
          fight_hash: "fixture-dps-fight",
          clear_time_ms: 620000,
          clear_time_seconds: 620,
          damage_time_ms: 560000,
          damage_time_seconds: 560,
          recorded_at: 1767322500000,
          recorded_at_iso: "2026-01-02T02:55:00.000Z",
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "BlackMage",
              dps: 250,
              rdps: 250,
              adps: 250,
              total_damage: 140000,
              fflogs_id: 202,
              active_time_ms: 520000,
              active_percent: 92.86,
            },
            {
              name: "黑魔對手",
              server: "鳳凰",
              job: "BlackMage",
              dps: 300,
              rdps: 300,
              adps: 300,
              total_damage: 168000,
              active_time_ms: 530000,
              active_percent: 94.64,
            },
          ],
        },
      ],
    },
    RPT3: {
      report_code: "RPT3",
      title: "Fixture transfer old server",
      url: "https://www.fflogs.com/reports/RPT3",
      report_start_time_iso: "2026-01-01T01:50:00.000Z",
      fights: [
        {
          fight_id: 7,
          fight_hash: "fixture-transfer-old",
          clear_time_ms: 590000,
          clear_time_seconds: 590,
          damage_time_ms: 540000,
          damage_time_seconds: 540,
          recorded_at: 1767232800000,
          recorded_at_iso: "2026-01-01T02:00:00.000Z",
          players: [
            {
              name: "同名角色",
              server: "巴哈姆特",
              job: "Warrior",
              dps: 210,
              rdps: 200,
              adps: 205,
              total_damage: 113400,
              fflogs_id: 404,
              active_time_ms: 500000,
              active_percent: 92.59,
            },
          ],
        },
      ],
    },
    RPT4: {
      report_code: "RPT4",
      title: "Fixture transfer new server",
      url: "https://www.fflogs.com/reports/RPT4",
      report_start_time_iso: "2026-01-03T03:50:00.000Z",
      fights: [
        {
          fight_id: 8,
          fight_hash: "fixture-transfer-new",
          clear_time_ms: 595000,
          clear_time_seconds: 595,
          damage_time_ms: 545000,
          damage_time_seconds: 545,
          recorded_at: 1767499200000,
          recorded_at_iso: "2026-01-04T04:00:00.000Z",
          players: [
            {
              name: "同名角色",
              server: "泰坦",
              job: "Warrior",
              dps: 190,
              rdps: 180,
              adps: 185,
              total_damage: 103550,
              fflogs_id: 405,
              active_time_ms: 490000,
              active_percent: 89.91,
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
  assert(usersIndex.total_users === 6, "fixture 應產生五位有公開成績的使用者與一位空白入口。");
  assert(globalStats.total_character_count === 5, `全服角色數應把同名跨服角色視為不同玩家，實際 ${globalStats.total_character_count}。`);
  assert(globalStats.total_entry_count === 6, "全服 entry 數應包含六筆公開玩家成績。");
  const hiddenUser = usersIndex.users.find((user) => user.character_name === "隱藏角色");
  assert(hiddenUser, "預設使用者索引應保留空白成績單入口。");
  assert(hiddenUser.servers.includes("鳳凰"), "空白入口應保留伺服器，讓同名角色查詢仍可辨識。");
  assert(hiddenUser.best_rdps === null, "空白入口不可帶入最佳 rDPS。");
  assert(hiddenUser.last_recorded_at_iso === null, "空白入口不可帶入最後紀錄時間。");
  assert(allUsersIndex.total_users === 6, "完整鏡像應納入所有 fixture 角色。");
  assert(allGlobalStats.total_character_count === 6, "完整全服統計應納入所有 fixture 角色。");
  assert(allGlobalStats.total_entry_count === 7, "完整全服統計應納入所有 fixture 成績。");
  const allHiddenUser = allUsersIndex.users.find((user) => user.character_name === "隱藏角色");
  assert(allHiddenUser, "完整鏡像使用者索引應包含對應角色。");
  assert(Array.isArray(globalStats.job_profiles) && globalStats.job_profiles.length === 4, "全服統計應產生職業專頁資料。");
  assert(serverCompare.summary.server_count === 4, "伺服器對比應分別納入同名角色所在的伺服器。");
  assert(serverCompare.servers.some((server) => server.server === "鳳凰"), "伺服器對比應包含鳳凰。");
  assert(serverCompare.servers.some((server) => server.server === "巴哈姆特"), "伺服器對比應包含同名角色所在的巴哈姆特。");
  assert(serverCompare.servers.some((server) => server.server === "泰坦"), "伺服器對比應包含同名角色所在的泰坦。");

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

  const sameNameUsers = usersIndex.users
    .filter((user) => user.character_name === "同名角色")
    .sort((left, right) => String(left.canonical_server).localeCompare(String(right.canonical_server), "zh-Hant-TW"));
  assert(sameNameUsers.length === 2, "使用者索引應把同名跨服角色拆成兩份個人成績單。");
  const bahamutUser = sameNameUsers.find((user) => user.canonical_server === "巴哈姆特");
  const titanUser = sameNameUsers.find((user) => user.canonical_server === "泰坦");
  assert(bahamutUser && titanUser, "同名角色應分別保留巴哈姆特與泰坦身分。");
  assert(bahamutUser.servers.length === 1 && bahamutUser.servers[0] === "巴哈姆特", "巴哈姆特同名角色只能列出自己的伺服器。");
  assert(titanUser.servers.length === 1 && titanUser.servers[0] === "泰坦", "泰坦同名角色只能列出自己的伺服器。");
  assert(bahamutUser.server_aliases.length === 0 && titanUser.server_aliases.length === 0, "同名跨服角色不應互相成為搜尋 alias。");

  const bahamutUserData = await readJson(path.join(tempRoot, "public", bahamutUser.file_path));
  const titanUserData = await readJson(path.join(tempRoot, "public", titanUser.file_path));
  const bahamutEntries = bahamutUserData.encounters[0]?.public_entries || [];
  const titanEntries = titanUserData.encounters[0]?.public_entries || [];
  assert(bahamutEntries.length === 1 && bahamutEntries[0].server === "巴哈姆特", "巴哈姆特同名角色只應保留巴哈姆特成績。");
  assert(titanEntries.length === 1 && titanEntries[0].server === "泰坦", "泰坦同名角色只應保留泰坦成績。");
  assert(
    !bahamutEntries.some((entry) => entry.original_server) && !titanEntries.some((entry) => entry.original_server),
    "同名跨服拆分後不應輸出 original_server。",
  );

  const mainUser = usersIndex.users.find((user) => user.character_name === "測試角色");
  assert(mainUser, "使用者索引應包含測試角色。");
  const mainUserData = await readJson(path.join(tempRoot, "public", mainUser.file_path));
  assert(mainUserData.summary.best_rdps === 250, "測試角色最佳 rDPS 應正確彙整。");
  assert(mainUserData.summary.public_entry_count === 2, "同一場戰鬥由多份 report 上傳時，個人成績單只能保留一筆公開成績。");
  assert(mainUserData.summary.profile_job === "Paladin", "個人成績單代表職業應優先採用同職排名最高的職業。");
  assert(mainUserData.summary.profile_job_rank === 1, "個人成績單代表職業應保留最高職業 Rank。");
  assert(mainUserData.encounters[0]?.best_entry?.job === "Paladin", "個人成績單副本代表列應優先顯示最高排名職業。");
  assert(mainUserData.encounters[0]?.best_entry?.fflogs_source_id === 101, "個人成績單代表列應保留 FFLogs sourceID。");
  assert(mainUserData.encounters[0]?.best_entry?.duplicate_count === 2, "合併後的個人成績應保留來源 report 數。");
  assert(mainUserData.encounters[0]?.best_entry?.source_reports?.length === 2, "合併後的個人成績應保留來源 report code。");
  assert(mainUserData.encounters[0]?.best_entry?.report_variants?.length === 2, "合併後的個人成績應輸出報告彈窗分頁資料。");
  assert(
    mainUserData.encounters[0]?.best_entry?.report_variants?.some((variant) => variant.report_code === "RPT1B" && variant.fight_id === 9),
    "報告分頁資料應包含另一位上傳者的 report 與 fight。",
  );
  const mainUserBlackMageEntry = mainUserData.encounters[0]?.public_entries?.find((entry) => entry.job === "BlackMage");
  assert(mainUserBlackMageEntry?.job_rank === 2, "fixture 需保留較高 rDPS 但職業 Rank 較低的輸出紀錄。");
  assert(mainUserBlackMageEntry?.fflogs_source_id === 202, "個人成績歷史列應保留 FFLogs sourceID 供外部工具深連結使用。");
  const mainUserEntry = mainUserData.encounters[0]?.public_entries?.[0];
  assert(mainUserEntry?.gcd_coverage?.percent === 94.43, "個人成績單應保留 GCD 覆蓋率。");
  assert(mainUserEntry?.gcd_coverage_status?.state === "ok", "個人成績單應保留 GCD 覆蓋率狀態。");
  assert(mainUserData.frequent_teammates[0]?.character_name === "治療隊友", "測試角色應彙整同場隊友。");
  assert(mainUserData.frequent_teammates[0]?.co_clear_count === 1, "同一場戰鬥的重複 report 不應灌水常同場隊友次數。");

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
