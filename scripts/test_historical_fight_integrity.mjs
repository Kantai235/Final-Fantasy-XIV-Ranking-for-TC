import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { isHistoricalIntegrityHidden, isHistoricalIntegrityAnomaly } from "./historical_fight_integrity.mjs";

// 相同案例同時交給 Python 排行榜與 Node 建置規則，驗證跨層不會再次放行舊判定。
const cases = [
  [{ recorded_at_iso: "2026-10-11T00:00:00Z" }, false],
  [{ data_integrity: null }, true],
  ...[4, 7, 8, 9, 10, 11, 12, 13, 14].map((version) => [
    { data_integrity: { calculation_version: version, status: "valid", hidden_from_public: false } },
    version < 8 || version > 13,
  ]),
  ...["excluded", "suspected", "unverifiable", "unknown"].map((status) => [
    { data_integrity: { calculation_version: 13, status, hidden_from_public: false } }, true,
  ]),
  [{ data_integrity: { calculation_version: 13, status: "valid", hidden_from_public: true } }, true],
];
for (const [fight, hidden] of cases) assert.equal(isHistoricalIntegrityHidden(fight), hidden);
assert(isHistoricalIntegrityAnomaly({ data_integrity: { status: "suspected" } }));
assert(isHistoricalIntegrityAnomaly({ data_integrity: { status: "excluded", hidden_from_public: false } }));
assert(!isHistoricalIntegrityAnomaly({ data_integrity: { status: "unverifiable" } }));

const root = fileURLToPath(new URL("../", import.meta.url));
const result = spawnSync(process.execPath, ["scripts/run_python.mjs", "-c", [
  "import json, sys",
  "sys.path.insert(0, 'scripts')",
  "import fetch_fflogs as f",
  "cases = json.load(sys.stdin)",
  "for fight, hidden in cases:",
  "    assert f.戰鬥已標記資料完整性隱藏(fight) == hidden, fight",
  "assert f.戰鬥已確認資料完整性異常({'data_integrity': {'status': 'suspected'}})",
  "assert not f.讀取戰鬥完整性檢核設定().enabled",
].join("\n")], { cwd: root, input: JSON.stringify(cases), encoding: "utf8" });
assert.equal(result.status, 0, result.stderr || result.stdout);
console.log("歷史完整性跨層回歸測試通過。");
