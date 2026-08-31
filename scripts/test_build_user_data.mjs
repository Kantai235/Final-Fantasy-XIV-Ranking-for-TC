import { spawnSync } from "node:child_process";
import { mkdtemp, readFile, rm, writeFile, mkdir } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { publicDataContracts, validateSchemaContract } from "../schemas/public_data_contracts.mjs";
import {
  calculatePhysicalFightHash,
  physicalFightHashVersion,
  resolvePhysicalFightHash,
} from "./fight_identity.mjs";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const buildScriptPath = path.join(repoRoot, "scripts", "build_user_data.mjs");
const fightIntegrityScriptPath = path.join(repoRoot, "scripts", "fight_integrity.py");

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertPhysicalFightHashContract() {
  const baseFight = {
    encounter_id: 96,
    difficulty: 101,
    clear_time_ms: 610000,
    damage_time_ms: 600000,
    recorded_at_iso: "2026-06-08T00:00:00+00:00",
    players: [
      {
        name: "測試角色",
        server: "巴哈姆特",
        job: "BlackMage",
        dps: 21000,
        rdps: 20000,
        adps: 20500,
        total_damage: 12000000,
      },
    ],
  };
  const driftedFight = structuredClone(baseFight);
  Object.assign(driftedFight, {
    clear_time_ms: 610001,
    damage_time_ms: 600002,
  });
  Object.assign(driftedFight.players[0], {
    dps: 21000.01,
    rdps: 19999.98,
    adps: 20500.02,
    total_damage: 12000007,
  });

  const expectedHash = "a150b4d498855002880c7dd0c9211377d52d708bae5141d3a2dfe8bd864b77ce";
  assert(physicalFightHashVersion === 2, "物理戰鬥簽章版本應為 v2。");
  assert(calculatePhysicalFightHash(baseFight) === expectedHash, "Node.js 產生的 v2 簽章未與 Python 契約一致。");
  assert(calculatePhysicalFightHash(driftedFight) === expectedHash, "FFLogs 時間或 DPS 微小漂移不得拆分同一場戰鬥。");

  const differentTimeFight = structuredClone(baseFight);
  differentTimeFight.recorded_at_iso = "2026-06-08T00:00:00.001+00:00";
  const differentRosterFight = structuredClone(baseFight);
  differentRosterFight.players[0].server = "鳳凰";
  const incompleteRosterFight = structuredClone(baseFight);
  incompleteRosterFight.players.push({ name: "缺欄角色", job: "Monk" });
  assert(calculatePhysicalFightHash(differentTimeFight) !== expectedHash, "不同開戰時間不得被誤合併。");
  assert(calculatePhysicalFightHash(differentRosterFight) !== expectedHash, "不同玩家名單不得被誤合併。");
  assert(calculatePhysicalFightHash(incompleteRosterFight) === null, "名單不完整時不得以玩家子集猜測同場。");
  assert(
    resolvePhysicalFightHash({ ...baseFight, fight_hash: "legacy-v1-hash" }) === expectedHash,
    "未標記 v2 的歷史戰鬥必須由建置層以穩定欄位重算。",
  );
}

async function writeJson(filePath, data) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(data)}\n`, "utf8");
}

async function readJson(filePath) {
  return JSON.parse(await readFile(filePath, "utf8"));
}

async function assertFightIntegrityVersionContract() {
  // 戰鬥完整性判定由 Python 寫入、Node.js 消費；兩邊版號若不同步，valid fight 會只出現在
  // 排行榜，卻被個人成績、隊伍榜與統計誤當成未知版本排除。直接比對兩個執行入口的常數，
  // 讓下一次規則升版時必須在同一筆變更中更新資料建置層，而不是等部署後才由玩家回報。
  const [pythonSource, nodeSource] = await Promise.all([
    readFile(fightIntegrityScriptPath, "utf8"),
    readFile(buildScriptPath, "utf8"),
  ]);
  const pythonCurrentMatch = pythonSource.match(/^CALCULATION_VERSION\s*=\s*(\d+)/m);
  const pythonLegacyMatch = pythonSource.match(
    /^LEGACY_PUBLIC_COMPATIBLE_VERSIONS\s*=\s*frozenset\(\{([^}]*)\}\)/m,
  );
  const nodeCurrentMatch = nodeSource.match(
    /^const currentFightIntegrityCalculationVersion\s*=\s*(\d+);/m,
  );
  const nodeLegacyMatch = nodeSource.match(
    /^const legacyPublicCompatibleFightIntegrityVersions\s*=\s*new Set\(\[([^\]]*)\]\);/m,
  );

  assert(pythonCurrentMatch && pythonLegacyMatch, "無法解析 Python 戰鬥完整性版本契約。");
  assert(nodeCurrentMatch && nodeLegacyMatch, "無法解析 Node.js 戰鬥完整性版本契約。");

  const parseVersionList = (rawVersions) => rawVersions
    .split(",")
    .map((value) => Number(value.trim()))
    .filter(Number.isFinite)
    .sort((left, right) => left - right);
  const pythonCurrentVersion = Number(pythonCurrentMatch[1]);
  const nodeCurrentVersion = Number(nodeCurrentMatch[1]);
  const pythonLegacyVersions = parseVersionList(pythonLegacyMatch[1]);
  const nodeLegacyVersions = parseVersionList(nodeLegacyMatch[1]);

  assert(
    nodeCurrentVersion === pythonCurrentVersion,
    `Node.js 現行完整性版號 v${nodeCurrentVersion} 未與 Python v${pythonCurrentVersion} 同步。`,
  );
  assert(
    JSON.stringify(nodeLegacyVersions) === JSON.stringify(pythonLegacyVersions),
    `Node.js 舊版相容清單 ${JSON.stringify(nodeLegacyVersions)} 未與 Python ${JSON.stringify(pythonLegacyVersions)} 同步。`,
  );
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
  const achievementEncounters = [
    {
      key: "savage_m4s",
      name: "輕量級第四層互斥測試",
      category: "零式",
      enabled: true,
      data_path: "data/rankings/savage_m4s.json",
    },
    {
      key: "savage_m8s",
      name: "次重量級第四層互斥測試",
      category: "零式",
      enabled: true,
      data_path: "data/rankings/savage_m8s.json",
    },
  ];
  const encounters = [encounter, ...achievementEncounters];
  await writeJson(path.join(tempRoot, "public", "data", "encounters.json"), encounters);
  await writeJson(path.join(tempRoot, "config", "encounters.json"), encounters.map((item, index) => ({
    ...item,
    zone_id: 999 + index,
    encounter_id: 888 + index,
    difficulty: index === 0 ? 100 : 101,
    scan_start_date: "2026-01-01",
  })));
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

  // 兩筆末層成績都落在次週之後、首月截止以前。全站統計必須只替同一玩家
  // 增加「首月踏破」，不可同時累加首週、次週、一般踏破或四層通關的人數。
  for (const [index, achievementEncounter] of achievementEncounters.entries()) {
    const recordedAtIso = achievementEncounter.key === "savage_m4s"
      ? "2026-04-01T07:50:00.000Z"
      : "2026-08-20T07:50:00.000Z";
    await writeJson(path.join(tempRoot, "data", "rankings", `${achievementEncounter.key}.json`), {
      schema_version: 1,
      encounter: {
        key: achievementEncounter.key,
        name: achievementEncounter.name,
        category: achievementEncounter.category,
        zone_id: 1000 + index,
        encounter_id: 889 + index,
        difficulty: 101,
      },
      updated_at_iso: "2026-01-02T03:04:05.000Z",
      ranking_entries: [
        {
          id: `${achievementEncounter.key}:achievement-exclusive-player`,
          character_name: "測試角色",
          server: "鳳凰",
          job: "Paladin",
          dps: 100,
          rdps: 90,
          adps: 95,
          clear_time_ms: 600000,
          clear_time_seconds: 600,
          recorded_at_iso: recordedAtIso,
          report_code: `ACHIEVEMENT_${achievementEncounter.key.toUpperCase()}`,
          report_url: `https://www.fflogs.com/reports/ACHIEVEMENT${index}`,
          fight_id: 1,
          rank: 1,
          is_obsolete_record: false,
        },
      ],
    });
  }

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
              tank_stats: {
                damage_taken: 5619043,
                self_healing: 1461615,
                personal_protection: 425482,
                team_protection: 733260,
                mitigation_coverage: {
                  effective_activation_percent: 96.15,
                },
              },
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
              // 同場搭檔需要保留展示數值，但缺少 dps，故不會成為另一份玩家成績單。
              name: "坦克隊友",
              server: "泰坦",
              job: "Warrior",
              rdps: 80,
              fflogs_id: 104,
              active_time_ms: 495000,
              active_percent: 90,
              tank_stats: {
                damage_taken: 5000000,
                self_healing: 1200000,
                personal_protection: 360000,
                team_protection: 680000,
                mitigation_coverage: {
                  effective_activation_percent: 92.5,
                },
              },
              gcd_coverage: {
                percent: 93.5,
                calculation_version: 1,
                source: "fflogs_casts_graph",
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
              fflogs_id: 102,
              active_time_ms: 480000,
              active_percent: 87.27,
              healing_stats: {
                hps: 17731,
                pure_healing: 7500000,
                protection: 3300000,
                overheal_percent: 46.14,
              },
            },
            {
              // 同角色的另一職業只用來建立雙補關聯；缺少 DPS 時不會成為額外公開成績，
              // 也不會改變 fixture 原本的玩家數與隊友統計。
              name: "測試角色",
              server: "鳳凰",
              job: "Scholar",
              fflogs_id: 103,
              rdps: 55,
              active_percent: 88,
              healing_stats: {
                hps: 16000,
                pure_healing: 7000000,
                protection: 3600000,
                overheal_percent: 42.5,
              },
              gcd_coverage: {
                percent: 92.25,
                calculation_version: 1,
                source: "fflogs_casts_graph",
              },
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
          // 歷史 v1 會把這些 FFLogs table 漂移算成另一個 hash；
          // 建置層必須以 v2 穩定欄位重算，並保留 report variant。
          fight_hash: "fixture-fight-drifted-v1",
          clear_time_ms: 600001,
          clear_time_seconds: 600.001,
          damage_time_ms: 550001,
          damage_time_seconds: 550.001,
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
              tank_stats: {
                damage_taken: 5619043,
                self_healing: 1461615,
                personal_protection: 425482,
                team_protection: 733260,
                mitigation_coverage: {
                  effective_activation_percent: 96.15,
                },
              },
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
              name: "坦克隊友",
              server: "泰坦",
              job: "Warrior",
              rdps: 81,
              fflogs_id: 306,
              active_time_ms: 496000,
              active_percent: 90.18,
              tank_stats: {
                damage_taken: 5001000,
                self_healing: 1201000,
                personal_protection: 361000,
                team_protection: 681000,
                mitigation_coverage: {
                  effective_activation_percent: 92.75,
                },
              },
              gcd_coverage: {
                percent: 93.75,
                calculation_version: 1,
                source: "fflogs_casts_graph",
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
              fflogs_id: 304,
              active_time_ms: 480000,
              active_percent: 87.27,
              healing_stats: {
                hps: 17731,
                pure_healing: 7500000,
                protection: 3300000,
                overheal_percent: 46.14,
              },
            },
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Scholar",
              fflogs_id: 305,
              rdps: 55.5,
              active_percent: 88.1,
              healing_stats: {
                hps: 16050,
                pure_healing: 7005000,
                protection: 3605000,
                overheal_percent: 42.4,
              },
              gcd_coverage: {
                percent: 92.5,
                calculation_version: 1,
                source: "fflogs_casts_graph",
              },
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
          fight_hash_version: 2,
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
          fight_hash_version: 2,
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
    INTEGRITY_V12_VALID: {
      report_code: "INTEGRITY_V12_VALID",
      title: "Fixture v12 compatible integrity result",
      url: "https://www.fflogs.com/reports/INTEGRITY_V12_VALID",
      report_start_time_iso: "2026-07-29T09:50:00.000Z",
      fights: [
        {
          fight_id: 16,
          fight_hash: "integrity-v12-valid-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785319200000,
          recorded_at_iso: "2026-07-29T10:00:00.000Z",
          data_integrity: {
            calculation_version: 12,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Paladin",
              dps: 77,
              rdps: 77,
              adps: 77,
              total_damage: 34650,
              active_time_ms: 430000,
              active_percent: 95.56,
            },
          ],
        },
      ],
    },
    INTEGRITY_V13_VALID: {
      report_code: "INTEGRITY_V13_VALID",
      title: "Fixture v13 current integrity result",
      url: "https://www.fflogs.com/reports/INTEGRITY_V13_VALID",
      report_start_time_iso: "2026-07-29T10:50:00.000Z",
      fights: [
        {
          fight_id: 17,
          fight_hash: "integrity-v13-valid-fixture-fight",
          clear_time_ms: 500000,
          clear_time_seconds: 500,
          damage_time_ms: 450000,
          damage_time_seconds: 450,
          recorded_at: 1785322800000,
          recorded_at_iso: "2026-07-29T11:00:00.000Z",
          data_integrity: {
            calculation_version: 13,
            status: "valid",
            hidden_from_public: false,
          },
          players: [
            {
              name: "測試角色",
              server: "鳳凰",
              job: "Paladin",
              dps: 76,
              rdps: 76,
              adps: 76,
              total_damage: 34200,
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
  assert(usersIndex.achievements?.length === 18, "使用者索引應輸出十八項成就手冊統計。");
  const recentAchievement = usersIndex.achievements.find((achievement) => achievement.id === "recently-active");
  const highActivityAchievement = usersIndex.achievements.find((achievement) => achievement.id === "high-activity");
  const lightStockTraderAchievement = usersIndex.achievements.find(
    (achievement) => achievement.id === "savage-light-heavyweight-stock-trader",
  );
  const cruiserStockTraderAchievement = usersIndex.achievements.find(
    (achievement) => achievement.id === "savage-cruiserweight-stock-trader",
  );
  const lightMonthOneAchievement = usersIndex.achievements.find(
    (achievement) => achievement.id === "savage-light-heavyweight-month-one",
  );
  const cruiserMonthOneAchievement = usersIndex.achievements.find(
    (achievement) => achievement.id === "savage-cruiserweight-month-one",
  );
  const mutuallyExclusiveStageIds = [
    "savage-light-heavyweight-week-one",
    "savage-light-heavyweight-week-two",
    "savage-light-heavyweight-clear",
    "savage-light-heavyweight-all-floors-clear",
    "savage-cruiserweight-week-one",
    "savage-cruiserweight-week-two",
    "savage-cruiserweight-clear",
    "savage-cruiserweight-all-floors-clear",
  ];
  assert(recentAchievement?.holder_count > 0, "fixture 的最近公開紀錄應取得近期活躍成就。");
  assert(
    recentAchievement?.holder_percentage
      === Number(((recentAchievement.holder_count / usersIndex.total_users) * 100).toFixed(2)),
    "成就獲得占比應以使用者索引總人數為分母。",
  );
  assert(highActivityAchievement?.holder_count === 0, "fixture 沒有玩家達到一百筆公開成績，不可取得高活躍成就。");
  assert(
    lightStockTraderAchievement?.holder_count === 0 && cruiserStockTraderAchievement?.holder_count === 0,
    "fixture 沒有完整零式量級成績，兩項炒股仔仍須輸出目錄但獲得人數應為零。",
  );
  assert(
    lightMonthOneAchievement?.holder_count === 1 && cruiserMonthOneAchievement?.holder_count === 1,
    "兩個量級各有一位玩家符合首月踏破，獲得人數都應為一。",
  );
  assert(
    lightMonthOneAchievement?.holder_percentage === 14.29
      && cruiserMonthOneAchievement?.holder_percentage === 14.29,
    "首月踏破占比應以七位索引玩家為分母重新計算為 14.29%。",
  );
  assert(
    mutuallyExclusiveStageIds.every((achievementId) => (
      usersIndex.achievements.find((achievement) => achievement.id === achievementId)?.holder_count === 0
    )),
    "取得首月踏破時，不可再把同一玩家計入首週、次週、一般踏破或通關人數。",
  );
  assert(globalStats.total_character_count === 5, `全服角色數應把同名跨服角色視為不同玩家，實際 ${globalStats.total_character_count}。`);
  assert(globalStats.total_entry_count === 13, "全服 entry 數應包含既有成績、v8／v10～v13 正常成績與兩筆首月互斥測試成績。");
  const hiddenUser = usersIndex.users.find((user) => user.character_name === "隱藏角色");
  assert(hiddenUser, "預設使用者索引應保留空白成績單入口。");
  assert(hiddenUser.servers.includes("鳳凰"), "空白入口應保留伺服器，讓同名角色查詢仍可辨識。");
  assert(hiddenUser.best_rdps === null, "空白入口不可帶入最佳 rDPS。");
  assert(hiddenUser.last_recorded_at_iso === null, "空白入口不可帶入最後紀錄時間。");
  assert(allUsersIndex.total_users === 7, "完整鏡像應保留所有公開索引角色。");
  assert(allUsersIndex.achievements?.length === usersIndex.achievements.length, "Hidden delta 索引也必須輸出完整成就手冊目錄。");
  assert(allGlobalStats.total_character_count === 6, "完整全服統計應納入所有 fixture 角色。");
  assert(allGlobalStats.total_entry_count === 14, "完整全服統計應納入所有 fixture 成績。");
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
  const mainFixtureEncounter = mainUserData.encounters.find((item) => item.encounter_key === "fixture_encounter");
  assert(mainFixtureEncounter, "測試角色應保留原始 fixture 副本資料。");
  assert(mainUserData.summary.best_rdps === 250, "測試角色最佳 rDPS 應正確彙整。");
  assert(mainUserData.summary.public_entry_count === 9, "重複 report 應合併，且既有正常戰鬥與兩筆首月互斥測試成績都應維持公開。");
  assert(
    mainFixtureEncounter.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V8_VALID"),
    "個人成績單必須保留 v8 已驗證正常的戰鬥。",
  );
  assert(
    mainFixtureEncounter.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V10_VALID"),
    "個人成績單必須保留 v10 已驗證正常的戰鬥。",
  );
  assert(
    mainFixtureEncounter.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V11_VALID"),
    "個人成績單必須保留 v11 已驗證正常的戰鬥。",
  );
  assert(
    mainFixtureEncounter.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V12_VALID"),
    "個人成績單必須保留 v12 已驗證正常的戰鬥。",
  );
  assert(
    mainFixtureEncounter.public_entries?.some((entry) => entry.report_code === "INTEGRITY_V13_VALID"),
    "個人成績單必須保留 v13 現行規則已驗證正常的戰鬥。",
  );
  assert(mainUserData.summary.profile_job === "Paladin", "個人成績單代表職業應優先採用同職排名最高的職業。");
  assert(mainUserData.summary.profile_job_rank === 1, "個人成績單代表職業應保留最高職業 Rank。");
  assert(mainFixtureEncounter.best_entry?.job === "Paladin", "個人成績單副本代表列應優先顯示最高排名職業。");
  assert(mainFixtureEncounter.best_entry?.fflogs_source_id === 101, "個人成績單代表列應保留 FFLogs sourceID。");
  assert(
    mainFixtureEncounter.best_entry?.tank_stats?.mitigation_coverage_percent === 96.15,
    "個人成績單副本代表列應保留坦克支援統計。",
  );
  assert(
    mainFixtureEncounter.best_entry?.co_tank?.character_name === "坦克隊友"
      && mainFixtureEncounter.best_entry?.co_tank?.job === "Warrior",
    "坦克個人成績副本代表列應保留唯一可辨識的同場另一坦。",
  );
  const mirroredPhysicalFightEntries = mainFixtureEncounter.public_entries?.filter(
    (entry) => entry.job === "Paladin" && entry.recorded_at_iso === "2026-01-02T03:00:00.000Z",
  ) || [];
  assert(
    mirroredPhysicalFightEntries.length === 1,
    "同一物理戰鬥的時間／DPS 漂移不得增加個人成績筆數或同職 PR 樣本。",
  );
  assert(mainFixtureEncounter.best_entry?.duplicate_count === 2, "合併後的個人成績應保留來源 report 數。");
  assert(mainFixtureEncounter.best_entry?.report_detail_path?.startsWith("data/user-entry-details/"), "合併後的個人成績應保留按需載入報告細節路徑。");
  assert(mainFixtureEncounter.best_entry?.report_detail_id === mainFixtureEncounter.best_entry?.id, "合併後的個人成績應保留報告細節 id。");
  assert(!mainFixtureEncounter.best_entry?.report_variants, "個人成績單主檔不應直接內嵌 report_variants。");
  const mainUserEntryDetails = await readJson(path.join(tempRoot, "public", mainFixtureEncounter.best_entry.report_detail_path));
  const mainUserBestDetail = mainUserEntryDetails.entries?.[mainFixtureEncounter.best_entry.report_detail_id];
  assert(mainUserBestDetail?.source_reports?.length === 2, "合併後的個人成績細節應保留來源 report code。");
  assert(mainUserBestDetail?.report_variants?.length === 2, "合併後的個人成績細節應輸出報告彈窗分頁資料。");
  assert(
    mainUserBestDetail?.report_variants?.some((variant) => variant.report_code === "RPT1B" && variant.fight_id === 9),
    "報告分頁資料應包含另一位上傳者的 report 與 fight。",
  );
  assert(
    mainUserBestDetail?.report_variants?.some((variant) => (
      variant.report_code === "RPT1B"
      && variant.co_tank?.rdps === 81
      && variant.co_tank?.tank_stats?.mitigation_coverage_percent === 92.75
    )),
    "同一場不同 report 的另一坦摘要有差異時，報告分頁必須保存該變體。",
  );
  assert(
    !mainUserBestDetail?.report_variants?.some((variant) => Object.hasOwn(variant.gcd_coverage || {}, "raw_graph_downtime_percent")),
    "報告分頁資料不應輸出 GCD 內部診斷欄位。",
  );
  const mainUserBlackMageEntry = mainFixtureEncounter.public_entries?.find((entry) => entry.job === "BlackMage");
  assert(mainUserBlackMageEntry?.job_rank === 2, "fixture 需保留較高 rDPS 但職業 Rank 較低的輸出紀錄。");
  assert(mainUserBlackMageEntry?.fflogs_source_id === 202, "個人成績歷史列應保留 FFLogs sourceID 供外部工具深連結使用。");
  assert(mainUserBlackMageEntry?.game_version === "7.0", "版本切點前的個人成績應保留舊版本。");
  const mainUserEntry = mainFixtureEncounter.public_entries?.find((entry) => entry.report_code === "RPT1");
  assert(mainUserEntry?.game_version === "7.05", "版本切點當下的個人成績應歸入新版本。");
  assert(mainUserEntry?.gcd_coverage?.percent === 94.43, "個人成績單應保留 GCD 覆蓋率。");
  assert(
    mainUserEntry?.tank_stats?.damage_taken === 5619043
      && mainUserEntry?.tank_stats?.self_healing === 1461615
      && mainUserEntry?.tank_stats?.personal_protection === 425482
      && mainUserEntry?.tank_stats?.team_protection === 733260
      && mainUserEntry?.tank_stats?.mitigation_coverage_percent === 96.15,
    "坦克個人成績應保留精簡後的承傷、自補、防護與有效減傷覆蓋率。",
  );
  assert(
    mainUserEntry?.co_tank?.character_name === "坦克隊友"
      && mainUserEntry?.co_tank?.server === "泰坦"
      && mainUserEntry?.co_tank?.job === "Warrior"
      && mainUserEntry?.co_tank?.rdps === 80
      && mainUserEntry?.co_tank?.active_percent === 90
      && mainUserEntry?.co_tank?.gcd_coverage?.percent === 93.5
      && mainUserEntry?.co_tank?.tank_stats?.team_protection === 680000,
    "標準雙坦場次應保存另一坦身分、rDPS、Active、GCD 與坦克支援摘要。",
  );
  assert(!Object.hasOwn(mainUserEntry.gcd_coverage || {}, "raw_graph_downtime_percent"), "個人成績單不應輸出 GCD 內部診斷欄位。");
  assert(!Object.hasOwn(mainUserEntry, "gcd_coverage_status"), "個人成績單不應輸出 GCD 診斷狀態，避免首屏 payload 膨脹。");
  const fixtureHealerTeammate = mainUserData.frequent_teammates.find(
    (teammate) => teammate.character_name === "治療隊友",
  );
  assert(fixtureHealerTeammate, "測試角色應彙整同場隊友。");
  assert(fixtureHealerTeammate?.co_clear_count === 1, "同一場戰鬥的重複 report 不應灌水常同場隊友次數。");

  const healerUser = usersIndex.users.find((user) => user.character_name === "治療隊友");
  assert(healerUser, "fixture 應產生治療隊友的個人成績單。");
  const healerUserData = await readJson(path.join(tempRoot, "public", healerUser.file_path));
  assert(
    healerUserData.encounters[0]?.best_entry?.healing_stats?.pure_healing === 7500000
      && healerUserData.encounters[0]?.best_entry?.co_healer?.job === "Scholar",
    "治療個人成績副本代表列應保留支援統計與同場另一補。",
  );
  const healerEntry = healerUserData.encounters[0]?.public_entries?.find((entry) => entry.report_code === "RPT1");
  assert(
    healerEntry?.healing_stats?.hps === 17731
      && healerEntry?.healing_stats?.pure_healing === 7500000
      && healerEntry?.healing_stats?.protection === 3300000
      && healerEntry?.healing_stats?.overheal_percent === 46.14,
    "治療個人成績應保留 HPS、純治療、防護量與 OH%。",
  );
  assert(
    healerEntry?.co_healer?.character_name === "測試角色"
      && healerEntry?.co_healer?.server === "鳳凰"
      && healerEntry?.co_healer?.job === "Scholar"
      && healerEntry?.co_healer?.rdps === 55
      && healerEntry?.co_healer?.active_percent === 88
      && healerEntry?.co_healer?.gcd_coverage?.percent === 92.25
      && healerEntry?.co_healer?.healing_stats?.protection === 3600000,
    "標準雙補場次應保存另一補身分、rDPS、Active、GCD 與治療支援摘要。",
  );
  const serverCompareEntries = serverCompare.servers.flatMap((server) => [
    server.best_entry,
    server.fastest_entry,
    ...(server.encounters || []).flatMap((encounter) => [encounter.best_entry, encounter.fastest_entry]),
  ]).filter(Boolean);
  assert(
    serverCompareEntries.every((entry) =>
      !Object.hasOwn(entry, "healing_stats")
      && !Object.hasOwn(entry, "tank_stats")
      && !Object.hasOwn(entry, "co_healer")
      && !Object.hasOwn(entry, "co_tank")),
    "伺服器對比的共用成績摘要不得夾帶排行榜或個人成績專用的坦補詳細欄位。",
  );
  const serverCompareContractIssues = validateSchemaContract(
    serverCompare,
    publicDataContracts.serverComparePayload,
    "fixture/public/data/server_compare.json",
  );
  assert(
    serverCompareContractIssues.length === 0,
    `伺服器對比 fixture 必須符合公開資料契約：${serverCompareContractIssues.join("；")}`,
  );

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
  assertPhysicalFightHashContract();
  await assertFightIntegrityVersionContract();
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
