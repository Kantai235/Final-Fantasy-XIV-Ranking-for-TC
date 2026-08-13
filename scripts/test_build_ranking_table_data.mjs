import assert from "node:assert/strict";
import {
  addRankingSupportReportShard,
  buildTableEntry,
  createRankingSupportContext,
  finalizeRankingSupportContext,
  tableColumns,
} from "./build_ranking_table_data.mjs";

function rowToObject(row) {
  return Object.fromEntries(tableColumns.map((column, index) => [column, row[index]]));
}

const healerStats = {
  calculation_version: 1,
  source: "fflogs_healing_table",
  hps: 12_345.67,
  pure_healing: 1_000_000,
  protection: 200_000,
  overheal: 500_000,
  overheal_percent: 33.33,
};
const tankStats = {
  calculation_version: 1,
  damage_taken: 9_000_000,
  self_healing: null,
  personal_protection: 300_000,
  team_protection: 500_000,
  mitigation_coverage: {
    effective_activation_percent: 88.89,
    skills: [{ key: "rampart", activation_count: 3 }],
  },
};

const sourceRanking = {
  ranking_entries: [
    {
      id: "healer-main",
      character_name: "主補師",
      server: "巴哈姆特",
      job: "Scholar",
      report_code: "PAIR",
      fight_id: 7,
      fight_hash: "pair-fight",
      fflogs_source_id: 10,
      healing_stats: healerStats,
    },
    {
      id: "tank-main",
      character_name: "主坦克",
      server: "巴哈姆特",
      job: "Paladin",
      report_code: "PAIR",
      fight_id: 7,
      fight_hash: "pair-fight",
      fflogs_source_id: 30,
      tank_stats: tankStats,
    },
    {
      id: "alliance-healer",
      character_name: "聯盟補師",
      server: "鳳凰",
      job: "Sage",
      report_code: "ALLIANCE",
      fight_id: 2,
      fight_hash: "alliance-fight",
      fflogs_source_id: 20,
      healing_stats: healerStats,
    },
    {
      id: "alliance-tank",
      character_name: "聯盟坦克",
      server: "巴哈姆特",
      job: "Warrior",
      report_code: "ALLIANCE",
      fight_id: 2,
      fight_hash: "alliance-fight",
      fflogs_source_id: 40,
      tank_stats: tankStats,
    },
  ],
};

const context = createRankingSupportContext(sourceRanking);
addRankingSupportReportShard(context, {
  PAIR: {
    report_code: "PAIR",
    fights: [
      {
        fight_id: 7,
        fight_hash: "pair-fight",
        fflogs_total_time_ms: 10_000,
        players: [
          {
            name: "主補師",
            server: "巴哈姆特",
            job: "Scholar",
            fflogs_id: 10,
            healing_stats: healerStats,
          },
          {
            name: "另一補師",
            server: "鳳凰",
            job: "WhiteMage",
            fflogs_id: 11,
            active_time_ms: 9_500,
            gcd_coverage: { percent: 97.25, calculation_version: 1 },
            rdps: 9_876.54,
            healing_stats: {
              ...healerStats,
              hps: 11_111.11,
              pure_healing: 900_000,
            },
          },
          {
            name: "主坦克",
            server: "巴哈姆特",
            job: "Paladin",
            fflogs_id: 30,
            tank_stats: tankStats,
          },
          {
            name: "另一坦克",
            server: "泰坦",
            job: "Gunbreaker",
            fflogs_id: 31,
            active_time_ms: 9_800,
            gcd_coverage: { percent: 96.5, calculation_version: 1 },
            rdps: 10_876.54,
            tank_stats: {
              ...tankStats,
              damage_taken: 8_000_000,
              team_protection: 600_000,
            },
          },
          { name: "輸出", server: "泰坦", job: "Monk" },
        ],
      },
    ],
  },
  ALLIANCE: {
    report_code: "ALLIANCE",
    fights: [
      {
        fight_id: 2,
        fight_hash: "alliance-fight",
        fflogs_total_time_ms: 10_000,
        players: [
          { name: "聯盟補師", server: "鳳凰", job: "Sage", fflogs_id: 20, healing_stats: healerStats },
          { name: "聯盟補師二", server: "泰坦", job: "Scholar", fflogs_id: 21, healing_stats: healerStats },
          { name: "聯盟補師三", server: "奧汀", job: "WhiteMage", fflogs_id: 22, healing_stats: healerStats },
          { name: "聯盟坦克", server: "巴哈姆特", job: "Warrior", fflogs_id: 40, tank_stats: tankStats },
          { name: "聯盟坦克二", server: "泰坦", job: "Paladin", fflogs_id: 41, tank_stats: tankStats },
          { name: "聯盟坦克三", server: "奧汀", job: "DarkKnight", fflogs_id: 42, tank_stats: tankStats },
        ],
      },
    ],
  },
});
finalizeRankingSupportContext(context);

const healerRow = rowToObject(buildTableEntry({
  id: "healer-main",
  character_name: "主補師",
  server: "巴哈姆特",
  job: "Scholar",
}, context));
assert.deepEqual(healerRow.healing_stats, {
  hps: 12_345.67,
  pure_healing: 1_000_000,
  protection: 200_000,
  overheal_percent: 33.33,
});
assert.equal(healerRow.co_healer.character_name, "另一補師");
assert.equal(healerRow.co_healer.active_percent, 95);
assert.equal(healerRow.co_healer.gcd_coverage, 97.25);
assert.equal(healerRow.co_healer.healing_stats.hps, 11_111.11);
assert(!Object.hasOwn(healerRow.healing_stats, "source"), "薄索引不應輸出來源診斷欄位");
assert(!Object.hasOwn(healerRow.healing_stats, "overheal"), "薄索引只保留 UI 需要的 OH% 而非過量治療 raw 總量");

const tankRow = rowToObject(buildTableEntry({
  id: "tank-main",
  character_name: "主坦克",
  server: "巴哈姆特",
  job: "Paladin",
}, context));
assert.deepEqual(tankRow.tank_stats, {
  damage_taken: 9_000_000,
  self_healing: null,
  personal_protection: 300_000,
  team_protection: 500_000,
  mitigation_coverage_percent: 88.89,
});
assert.equal(tankRow.co_tank.character_name, "另一坦克");
assert.equal(tankRow.co_tank.active_percent, 98);
assert.equal(tankRow.co_tank.gcd_coverage, 96.5);
assert.equal(tankRow.co_tank.tank_stats.damage_taken, 8_000_000);
assert.equal(tankRow.co_tank.tank_stats.team_protection, 600_000);
assert(!Object.hasOwn(tankRow.tank_stats, "skills"), "薄索引不得帶入減傷技能明細");

const allianceRow = rowToObject(buildTableEntry({
  id: "alliance-healer",
  character_name: "聯盟補師",
  server: "鳳凰",
  job: "Sage",
}, context));
assert.equal(allianceRow.co_healer, null, "同場超過兩名補師且沒有小隊編號時不可猜測另一補");

const allianceTankRow = rowToObject(buildTableEntry({
  id: "alliance-tank",
  character_name: "聯盟坦克",
  server: "巴哈姆特",
  job: "Warrior",
}, context));
assert.equal(allianceTankRow.co_tank, null, "同場超過兩名坦克且沒有小隊編號時不可猜測另一坦");

console.log("ranking table support metrics test passed.");
