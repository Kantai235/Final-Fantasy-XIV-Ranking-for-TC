from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fetch_fflogs as fflogs
import fight_integrity_m8s as m8s
import fight_integrity_known_capacity as known_capacity


def make_mechanic_summary(stone_overkill: int = 0, wind_overkill: int = 0) -> dict:
    """匿名測量 fixture；基準來自已確認的三次 2,103,687 機制傷害。"""
    return {"version": "m8s_wolf_surges_v1", "targets": [
        {"guid": guid, "hit_count": 3, "effective_damage": 6_311_061 - overkill,
         "overkill": overkill, "overkill_hit_count": int(overkill > 0),
         "nominal_min": 2_103_687, "nominal_max": 2_103_687,
         "invalid_hit_count": 0, "source_npc_guids": [source], "ability_ids": abilities}
        for guid, source, abilities, overkill in (
            (18219, 18262, [41966, 43520], wind_overkill),
            (18225, 18261, [41965, 43137], stone_overkill),
        )
    ]}


class M8SWolfMechanicTest(unittest.TestCase):
    actors = {11: 18219, 12: 18225, 21: 18262, 22: 18261, 23: 18215}
    fight = {"fight_id": 9, "encounter_id": 100, "difficulty": 101,
             "start_time": 2_000, "end_time": 820_000, "recorded_at": 1_800_000_000_000}

    @staticmethod
    def events() -> list[dict]:
        return [{"type": "damage", "targetID": target, "sourceID": source,
                 "abilityGameID": ability, "amount": 2_103_687, "overkill": -1}
                for target, source, ability in ((11, 21, 41966), (12, 22, 41965))
                for _ in range(3)]

    def response(self, events: list[dict], next_page: float | None = None) -> dict:
        return {"reportData": {"report": {
            "fights": [{"id": 9, "encounterID": 100, "difficulty": 101,
                        "enemyNPCs": [{"id": k, "gameID": v} for k, v in self.actors.items()]}],
            "events": {"data": events, "nextPageTimestamp": next_page},
        }}}

    def test_overkill_adjusts_only_effective_mechanic_damage(self) -> None:
        events = self.events()
        events[-1].update(amount=1_851_511, overkill=252_176)
        accumulator = m8s.MechanicAccumulator(self.actors)
        accumulator.add(events + [{**events[0], "type": "calculateddamage"},
                                  {**events[0], "sourceID": 99, "abilityGameID": 7}])
        result = accumulator.summary()
        self.assertEqual(m8s.summary_status(result), "valid")
        self.assertEqual(m8s.expected_wolf_damage(result), {18219: 4_207_377, 18225: 4_459_553})
        self.assertEqual(result["targets"][1]["hit_count"], 3)

    def test_wrong_source_skill_and_nominal_damage_remain_suspected(self) -> None:
        for change in ({"sourceID": 23}, {"abilityGameID": 999}, {"amount": 2_149_147},
                       {"amount": float("nan")}, {"overkill": -2}):
            with self.subTest(change=change):
                events = self.events()
                events[0].update(change)
                accumulator = m8s.MechanicAccumulator(self.actors)
                accumulator.add(events)
                self.assertEqual(m8s.summary_status(accumulator.summary()), "suspected")
                self.assertEqual(m8s.expected_wolf_damage(accumulator.summary()), {})

    def test_missing_or_extra_hits_do_not_pass(self) -> None:
        for events, status in (([], "unverifiable"), (self.events()[:-1], "unverifiable"),
                               (self.events() + self.events()[:1], "suspected")):
            accumulator = m8s.MechanicAccumulator(self.actors)
            accumulator.add(events)
            self.assertEqual(m8s.summary_status(accumulator.summary()), status)

    def test_overkill_before_last_hit_and_canceling_nominal_errors_are_rejected(self) -> None:
        for changes in (({"amount": 2_103_587, "overkill": 100}, {}),
                        ({"amount": 2_103_688}, {"amount": 2_103_686})):
            events = self.events()
            events[0].update(changes[0])
            events[1].update(changes[1])
            accumulator = m8s.MechanicAccumulator(self.actors)
            accumulator.add(events)
            self.assertEqual(m8s.summary_status(accumulator.summary()), "suspected")

    def test_summary_validation_rejects_stale_or_corrupt_evidence(self) -> None:
        for value in (None, {"version": "old"}, {"version": m8s.MODEL, "targets": []}):
            self.assertIsNone(m8s.normalize_summary(value))
        summary = make_mechanic_summary()
        summary["targets"][0]["effective_damage"] += 1
        self.assertEqual(m8s.summary_status(summary), "suspected")

    def test_config_rejects_dynamic_model_with_static_total_or_wrong_encounter(self) -> None:
        config_path = Path(__file__).resolve().parent.parent / "config/fight_integrity_known_enemy_hp.json"
        original = json.loads(config_path.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as directory:
            for mutation in ("static_total", "wrong_encounter", "wrong_hp", "unknown_model"):
                data = copy.deepcopy(original)
                rule = data["encounters"]["savage_m8s"]
                if mutation == "static_total":
                    rule.update(required_enemy_damage_min=148_739_091, required_enemy_damage_max=148_759_091)
                elif mutation == "wrong_encounter":
                    data["encounters"]["savage_m7s"] = rule
                elif mutation == "wrong_hp":
                    rule["target_damage_profile"]["targets"][1]["max_hp"] += 1
                else:
                    rule["target_damage_profile"]["mechanic_damage_model"] = "unknown"
                path = Path(directory) / "invalid.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(mutation=mutation), self.assertRaises(RuntimeError):
                    known_capacity.load_known_enemy_capacity_policy(path)

    def test_all_event_pages_are_consumed_once(self) -> None:
        events = self.events()
        with patch.object(fflogs, "執行_graphql", side_effect=[
            self.response(events[:2], 300_000), self.response(events[2:]),
        ]) as query:
            result = fflogs.查詢M8S狼機制承傷(None, None, "fixture", self.fight)
        self.assertEqual(m8s.summary_status(result), "valid")
        self.assertEqual(query.call_count, 2)
        self.assertEqual(query.call_args_list[0].args[3]["startTime"], 2_000)
        self.assertEqual(query.call_args_list[1].args[3]["startTime"], 300_000)
        self.assertEqual(query.call_args_list[1].args[3]["endTime"], 820_000)
        self.assertIn("dataType: All", query.call_args.args[2])

    def test_missing_report_and_broken_pages_fail_without_partial_summary(self) -> None:
        for response, error in (({"reportData": {"report": None}}, fflogs.FFLogs報告存取錯誤),
                                (self.response(self.events(), 2_000), RuntimeError),
                                (self.response(self.events(), float("nan")), RuntimeError),
                                (self.response(self.events(), "broken"), RuntimeError)):
            with self.subTest(response=response), patch.object(fflogs, "執行_graphql", return_value=response):
                with self.assertRaises(error):
                    fflogs.查詢M8S狼機制承傷(None, None, "fixture", self.fight)
        with patch.object(fflogs, "執行_graphql", side_effect=[self.response(self.events(), 300_000),
                                                              {"reportData": {"report": {"events": {}}}}]):
            with self.assertRaises(RuntimeError):
                fflogs.查詢M8S狼機制承傷(None, None, "fixture", self.fight)

    def test_wrong_fight_and_pagination_limit_are_rejected(self) -> None:
        response = self.response(self.events())
        response["reportData"]["report"]["fights"][0]["encounterID"] = 99
        with patch.object(fflogs, "執行_graphql", return_value=response):
            with self.assertRaises(RuntimeError):
                fflogs.查詢M8S狼機制承傷(None, None, "fixture", self.fight)
        with patch.object(fflogs, "執行_graphql", side_effect=lambda *args: self.response(
            [], args[3]["startTime"] + 1,
        )) as query:
            with self.assertRaisesRegex(RuntimeError, "100"):
                fflogs.查詢M8S狼機制承傷(None, None, "fixture", self.fight)
        self.assertEqual(query.call_count, 100)

    def test_new_fetch_reuses_targets_and_stores_only_summary(self) -> None:
        policy = known_capacity.load_known_enemy_capacity_policy(
            Path(__file__).resolve().parent.parent / "config/fight_integrity_known_enemy_hp.json"
        )
        config = fflogs.戰鬥完整性檢核設定(
            enabled=True, cutoff_ms=0, cutoff_iso="2026-07-28T18:00:00+08:00",
            hp_ratio_threshold=1.15, suspected_hp_ratio_threshold=1.14,
            excluded_encounter_keys=set(), known_enemy_capacity=policy,
        )
        report = {"start_time": 1_800_000_000_000, "end_time": 1_800_001_000_000, "revision": 1}
        targets = [{"guid": g, "damage": d, "max_hp": hp, "instance_count": 1}
                   for g, d, hp in ((18215, 67_582_728, 67_582_753),
                                    (18219, 4_207_377, 10_518_438),
                                    (18222, 72_751_579, 72_751_588),
                                    (18225, 4_459_553, 10_518_438))]
        with tempfile.TemporaryDirectory() as directory:
            cache = fflogs.integrity_cache.FightIntegrityMeasurementCache(Path(directory) / "cache.json")
            cache.put("fixture", report, self.fight, measurement={
                "enemy_damage": 149_001_237, "enemy_hp_capacity": 161_371_217,
                "target_count": 4, "targets": targets,
            }, cached_at_iso="2026-09-09T00:00:00Z")
            with (patch.object(fflogs, "查詢M8S狼機制承傷", return_value=make_mechanic_summary(252_176)) as query,
                  patch.object(fflogs, "查詢戰鬥完整性目標傷害") as target_query):
                results = [fflogs.檢核戰鬥完整性(
                    None, None, 副本鍵值="savage_m8s", 報告代碼="fixture", 報告脈絡=report,
                    戰鬥=self.fight, 設定=config, 測量快取=cache,
                ) for _ in range(2)]
            self.assertTrue(all(r["status"] == "valid" for r in results))
            query.assert_called_once()
            target_query.assert_not_called()
            saved = json.loads(cache.path.read_text(encoding="utf-8"))
            self.assertNotIn("sourceID", json.dumps(saved))
            self.assertNotIn("timestamp", json.dumps(saved))
            self.assertEqual(results[0]["metrics"]["target_damage_profile"]["expected_enemy_damage"], 149_001_271)

            # 新收錄若機制 API 中斷，已抓好的目標承傷仍須保存；下次只補機制。
            cache = fflogs.integrity_cache.FightIntegrityMeasurementCache(Path(directory) / "new.json")
            with (patch.object(fflogs, "查詢M8S狼機制承傷", side_effect=RuntimeError("暫時中斷")),
                  patch.object(fflogs, "查詢戰鬥完整性目標傷害", return_value=[
                      {**t, "id": t["guid"]} for t in targets]),
                  patch.object(fflogs, "查詢戰鬥完整性目標生命值",
                               return_value={t["guid"]: t["max_hp"] for t in targets})):
                with self.assertRaises(RuntimeError):
                    fflogs.檢核戰鬥完整性(
                        None, None, 副本鍵值="savage_m8s", 報告代碼="fixture", 報告脈絡=report,
                        戰鬥=self.fight, 設定=config, 測量快取=cache,
                    )
            stored = cache.get("fixture", report, self.fight)["measurement"]
            self.assertEqual(stored["targets"], targets)
            self.assertNotIn("wolf_mechanic_damage", stored)


if __name__ == "__main__":
    unittest.main()
