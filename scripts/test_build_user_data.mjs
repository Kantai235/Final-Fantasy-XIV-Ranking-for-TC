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
  await writeJson(path.join(tempRoot, "config", "game_versions.json"), {
    schema_version: 1,
    timezone: "Asia/Taipei",
    versions: [
      { patch: "7.0", label: "7.0", starts_at_iso: null },
      { patch: "7.05", label: "7.05", starts_at_iso: "2026-01-02T03:00:00.000Z" },
    ],
  });

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
                raw_graph_downtime_percent: 94.4,
                raw_graph_downtime_denominator_ms: 551000,
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
                raw_graph_downtime_percent: 94.4,
                raw_graph_downtime_denominator_ms: 551000,
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
    INTEGRITY1: {
      report_code: "INTEGRITY1",
      title: "Fixture integrity-hidden fight",
      url: "https://www.fflogs.com/reports/INTEGRITY1",
      report_start_time_iso: "2026-01-03T04:50:00.000Z",
      fights: [
        {
          fight_id: 10,
          fight_hash: "integrity-hidden-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1767416400000,
          recorded_at_iso: "2026-01-03T05:00:00.000Z",
          // 即使輸出到 public/data/all 的 hidden delta，也不得讓暫時性資料品質檢核
          // 已判定異常的 pull 回流；原始 report 分片仍完整保留以供日後追溯。
          data_integrity: {
            calculation_version: 1,
            status: "excluded",
            hidden_from_public: true,
            reasons: ["enemy_damage_exceeds_hp_ratio_threshold"],
          },
          players: [
            {
              name: "異常角色",
              server: "鳳凰",
              job: "BlackMage",
              dps: 9999,
              rdps: 9999,
              adps: 9999,
              total_damage: 4499550,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY1_MIRROR: {
      report_code: "INTEGRITY1_MIRROR",
      title: "Fixture mirrored integrity-hidden fight",
      url: "https://www.fflogs.com/reports/INTEGRITY1_MIRROR",
      report_start_time_iso: "2026-01-03T04:51:00.000Z",
      fights: [
        {
          fight_id: 18,
          fight_hash: "integrity-hidden-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1767416400000,
          recorded_at_iso: "2026-01-03T05:00:00.000Z",
          // 另一份上傳本身看似正常，但 fight_hash 已由 INTEGRITY1 證實為同一場異常戰鬥。
          data_integrity: {
            calculation_version: 10,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "異常鏡像角色",
              server: "鳳凰",
              job: "Monk",
              dps: 8888,
              rdps: 8888,
              adps: 8888,
              total_damage: 3999600,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY_PENDING: {
      report_code: "INTEGRITY_PENDING",
      title: "Fixture unchecked post-cutoff fight",
      url: "https://www.fflogs.com/reports/INTEGRITY_PENDING",
      report_start_time_iso: "2026-07-29T04:50:00.000Z",
      // 來源為 private，但唯一 fight 尚未完成 07/28 後的完整性檢核。
      // 兩個索引都必須保留可回退至公開空白底稿的角色入口。
      report_hidden: true,
      fights: [
        {
          fight_id: 11,
          fight_hash: "integrity-pending-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785301200000,
          recorded_at_iso: "2026-07-29T05:00:00.000Z",
          players: [
            {
              name: "待檢核角色",
              server: "鳳凰",
              job: "Monk",
              dps: 9999,
              rdps: 9999,
              adps: 9999,
              total_damage: 4499550,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY_STALE: {
      report_code: "INTEGRITY_STALE",
      title: "Fixture stale integrity result",
      url: "https://www.fflogs.com/reports/INTEGRITY_STALE",
      report_start_time_iso: "2026-07-29T05:50:00.000Z",
      fights: [
        {
          fight_id: 12,
          fight_hash: "integrity-stale-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785304800000,
          recorded_at_iso: "2026-07-29T06:00:00.000Z",
          // 舊版曾判為 valid 並明示不隱藏；規則升版後仍必須 fail-closed。
          data_integrity: {
            calculation_version: 4,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "舊版檢核角色",
              server: "曉月",
              job: "Monk",
              dps: 9999,
              rdps: 9999,
              adps: 9999,
              total_damage: 4499550,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY_V8_VALID: {
      report_code: "INTEGRITY_V8_VALID",
      title: "Fixture v8 compatible integrity result",
      url: "https://www.fflogs.com/reports/INTEGRITY_V8_VALID",
      report_start_time_iso: "2026-07-29T06:50:00.000Z",
      fights: [
        {
          fight_id: 13,
          fight_hash: "integrity-v8-valid-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785308400000,
          recorded_at_iso: "2026-07-29T07:00:00.000Z",
          // v9 僅重判 v8 失敗案例；v8 已確認正常的戰鬥必須維持公開。
          data_integrity: {
            calculation_version: 8,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Paladin",
              dps: 80,
              rdps: 80,
              adps: 80,
              total_damage: 36000,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY_V10_VALID: {
      report_code: "INTEGRITY_V10_VALID",
      title: "Fixture v10 compatible integrity result",
      url: "https://www.fflogs.com/reports/INTEGRITY_V10_VALID",
      report_start_time_iso: "2026-07-29T07:50:00.000Z",
      fights: [
        {
          fight_id: 14,
          fight_hash: "integrity-v10-valid-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785312000000,
          recorded_at_iso: "2026-07-29T08:00:00.000Z",
          data_integrity: {
            calculation_version: 10,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Paladin",
              dps: 79,
              rdps: 79,
              adps: 79,
              total_damage: 35550,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY_V11_VALID: {
      report_code: "INTEGRITY_V11_VALID",
      title: "Fixture v11 current integrity result",
      url: "https://www.fflogs.com/reports/INTEGRITY_V11_VALID",
      report_start_time_iso: "2026-07-29T08:50:00.000Z",
      fights: [
        {
          fight_id: 15,
          fight_hash: "integrity-v11-valid-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785315600000,
          recorded_at_iso: "2026-07-29T09:00:00.000Z",
          data_integrity: {
            calculation_version: 11,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Paladin",
              dps: 78,
              rdps: 78,
              adps: 78,
              total_damage: 35100,
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

  assert(
    !usersIndex.users.some((user) => user.character_name === "舊版檢核角色"),
    "舊版完整性 valid 結果不得重新進入公開使用者索引。",
  );

  assert(usersIndex.generated_at_iso === "2026-01-02T03:04:05.000Z", "使用者索引應使用 ranking 更新時間作為 generated_at_iso。");
  assert(globalStats.generated_at_iso === "2026-01-02T03:04:05.000Z", "全服統計應使用 ranking 更新時間作為 generated_at_iso。");
  assert(usersIndex.total_users === 7, "fixture 應產生五位有公開成績的使用者與兩位空白入口。");
  assert(usersIndex.achievements?.length === 12, "使用者索引應輸出十二項成就手冊統計。");
  const recentAchievement = usersIndex.achievements.find((achievement) => achievement.id === "recently-active");
  const highActivityAchievement = usersIndex.achievements.find((achievement) => achievement.id === "high-activity");
  assert(recentAchievement?.holder_count > 0, "fixture 的最近公開紀錄應取得近期活躍成就。");
  assert(
    recentAchievement?.holder_percentage
      === Number(((recentAchievement.holder_count / usersIndex.total_users) * 100).toFixed(2)),
    "成就獲得占比應以使用者索引總人數為分母。",
  );
  assert(highActivityAchievement?.holder_count === 0, "fixture 沒有玩家達到一百筆公開成績，不可取得高活躍成就。");
  assert(globalStats.total_character_count === 5, `全服角色數應把同名跨服角色視為不同玩家，實際 ${globalStats.total_character_count}。`);
  assert(globalStats.total_entry_count === 9, "全服 entry 數應包含六筆既有成績與 v8／v10／v11 正常成績。");
  const hiddenUser = usersIndex.users.find((user) => user.character_name === "隱藏角色");
  assert(hiddenUser, "預設使用者索引應保留空白成績單入口。");
  assert(hiddenUser.servers.includes("鳳凰"), "空白入口應保留伺服器，讓同名角色查詢仍可辨識。");
  assert(hiddenUser.best_rdps === null, "空白入口不可帶入最佳 rDPS。");
  assert(hiddenUser.last_recorded_at_iso === null, "空白入口不可帶入最後紀錄時間。");
  assert(allUsersIndex.total_users === 7, "完整鏡像應保留所有公開索引角色。");
  assert(allUsersIndex.achievements?.length === usersIndex.achievements.length, "Hidden delta 索引也必須輸出完整成就手冊目錄。");
  assert(allGlobalStats.total_character_count === 6, "完整全服統計應納入所有 fixture 角色。");
  assert(allGlobalStats.total_entry_count === 10, "完整全服統計應納入所有 fixture 成績。");
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
  assert(!usersIndex.users.some((user) => user.character_name === "異常角色"), "完整性檢核隱藏的 fight 不可產生公開角色入口。");
  assert(!allUsersIndex.users.some((user) => user.character_name === "異常角色"), "完整性檢核隱藏的 fight 不可回流到 hidden delta。");
  assert(
    !usersIndex.users.some((user) => user.character_name === "異常鏡像角色"),
    "同一 fight_hash 的其他 report 變體不可把已確認異常的戰鬥帶回公開索引。",
  );
  assert(
    !allUsersIndex.users.some((user) => user.character_name === "異常鏡像角色"),
    "同一 fight_hash 的異常戰鬥也不可回流到 hidden delta。",
  );
  const pendingIntegrityUser = usersIndex.users.find((user) => user.character_name === "待檢核角色");
  const allPendingIntegrityUser = allUsersIndex.users.find((user) => user.character_name === "待檢核角色");
  assert(pendingIntegrityUser, "private 且未檢核的來源仍應保留公開空白使用者入口。");
  assert(allPendingIntegrityUser, "完整鏡像索引不得遺漏公開空白使用者入口。");
  assert(pendingIntegrityUser.public_entry_count === 0, "未檢核戰鬥不可成為公開成績。");
  assert(
    allPendingIntegrityUser.file_path === pendingIntegrityUser.file_path,
    "完整鏡像沒有可補資料時應直接回退公開空白成績單，而非產生不完整 delta。",
  );

  const allHiddenUserData = await readJson(
    path.join(tempRoot, "public", allHiddenUser.file_path),
  );
  const allHiddenEntry = allHiddenUserData.encounters[0]?.public_entries?.[0];
  assert(allHiddenUser.file_path.startsWith("data/all/users/"), "含 hidden 成績的完整鏡像索引應指向 hidden delta 檔。");
  assert(allHiddenUserData.format === "user_profile_hidden_delta_v1", "完整鏡像成績單應以 hidden delta 格式輸出。");
  assert(allHiddenUserData.base_path === hiddenUser.file_path, "hidden delta 應指回公開空白成績單底稿。");
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
  assert(mainUserData.summary.public_entry_count === 5, "重複 report 應合併，且 v8／v10／v11 已驗證正常的戰鬥應維持公開。");
  assert(
    mainUserData.encounters[0]?.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V8_VALID"),
    "個人成績單必須保留 v8 已驗證正常的戰鬥。",
  );
  assert(
    mainUserData.encounters[0]?.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V10_VALID"),
    "個人成績單必須保留 v10 已驗證正常的戰鬥。",
  );
  assert(
    mainUserData.encounters[0]?.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V11_VALID"),
    "個人成績單必須保留 v11 現行規則已驗證正常的戰鬥。",
  );
  assert(mainUserData.summary.profile_job === "Paladin", "個人成績單代表職業應優先採用同職排名最高的職業。");
  assert(mainUserData.summary.profile_job_rank === 1, "個人成績單代表職業應保留最高職業 Rank。");
  assert(mainUserData.encounters[0]?.best_entry?.job === "Paladin", "個人成績單副本代表列應優先顯示最高排名職業。");
  assert(mainUserData.encounters[0]?.best_entry?.fflogs_source_id === 101, "個人成績單代表列應保留 FFLogs sourceID。");
  assert(mainUserData.encounters[0]?.best_entry?.duplicate_count === 2, "合併後的個人成績應保留來源 report 數。");
  assert(mainUserData.encounters[0]?.best_entry?.report_detail_path?.startsWith("data/user-entry-details/"), "合併後的個人成績應保留按需載入報告細節路徑。");
  assert(mainUserData.encounters[0]?.best_entry?.report_detail_id === mainUserData.encounters[0]?.best_entry?.id, "合併後的個人成績應保留報告細節 id。");
  assert(!mainUserData.encounters[0]?.best_entry?.report_variants, "個人成績單主檔不應直接內嵌 report_variants。");
  const mainUserEntryDetails = await readJson(path.join(tempRoot, "public", mainUserData.encounters[0].best_entry.report_detail_path));
  const mainUserBestDetail = mainUserEntryDetails.entries?.[mainUserData.encounters[0].best_entry.report_detail_id];
  assert(mainUserBestDetail?.source_reports?.length === 2, "合併後的個人成績細節應保留來源 report code。");
  assert(mainUserBestDetail?.report_variants?.length === 2, "合併後的個人成績細節應輸出報告彈窗分頁資料。");
  assert(
    mainUserBestDetail?.report_variants?.some((variant) => variant.report_code === "RPT1B" && variant.fight_id === 9),
    "報告分頁資料應包含另一位上傳者的 report 與 fight。",
  );
  assert(
    !mainUserBestDetail?.report_variants?.some((variant) => Object.hasOwn(variant.gcd_coverage || {}, "raw_graph_downtime_percent")),
    "報告分頁資料不應輸出 GCD 內部診斷欄位。",
  );
  const mainUserBlackMageEntry = mainUserData.encounters[0]?.public_entries?.find((entry) => entry.job === "BlackMage");
  assert(mainUserBlackMageEntry?.job_rank === 2, "fixture 需保留較高 rDPS 但職業 Rank 較低的輸出紀錄。");
  assert(mainUserBlackMageEntry?.fflogs_source_id === 202, "個人成績歷史列應保留 FFLogs sourceID 供外部工具深連結使用。");
  assert(mainUserBlackMageEntry?.game_version === "7.0", "版本切點前的個人成績應保留舊版本。");
  const mainUserEntry = mainUserData.encounters[0]?.public_entries?.find((entry) => entry.report_code === "RPT1");
  assert(mainUserEntry?.game_version === "7.05", "版本切點當下的個人成績應歸入新版本。");
  assert(mainUserEntry?.gcd_coverage?.percent === 94.43, "個人成績單應保留 GCD 覆蓋率。");
  assert(!Object.hasOwn(mainUserEntry.gcd_coverage || {}, "raw_graph_downtime_percent"), "個人成績單不應輸出 GCD 內部診斷欄位。");
  assert(!Object.hasOwn(mainUserEntry, "gcd_coverage_status"), "個人成績單不應輸出 GCD 診斷狀態，避免首屏 payload 膨脹。");
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
