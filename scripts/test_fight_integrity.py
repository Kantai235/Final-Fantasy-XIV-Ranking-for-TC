from __future__ import annotations

import unittest

import fight_integrity as integrity


class FightIntegrityTest(unittest.TestCase):
    def test_hp_ratio_over_threshold_is_excluded(self) -> None:
        result = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=115_001,
            enemy_hp_capacity=100_000,
            target_count=2,
            attack_marker=False,
            hp_ratio_threshold=1.15,
        )

        self.assertEqual(result["status"], "excluded")
        self.assertTrue(result["hidden_from_public"])
        self.assertAlmostEqual(result["metrics"]["damage_to_hp_ratio"], 1.15001)
        self.assertEqual(result["reasons"], ["enemy_damage_exceeds_hp_ratio_threshold"])

    def test_attack_marker_under_threshold_remains_hidden_as_suspected(self) -> None:
        result = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=105_000,
            enemy_hp_capacity=100_000,
            target_count=1,
            attack_marker=True,
            hp_ratio_threshold=1.15,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("fflogs_basic_attack_exploit_marker", result["reasons"])
        self.assertNotIn("enemy_damage_exceeds_hp_ratio_threshold", result["reasons"])

    def test_generic_exploit_six_is_not_basic_attack_marker(self) -> None:
        fight = {
            "damage_done_summary": {
                "exploitDetails": [
                    {"exploit": 6, "abilities": []},
                ]
            }
        }
        self.assertFalse(integrity.has_basic_attack_exploit_marker(fight))

    def test_attack_guid_is_marker_without_relying_on_localized_name(self) -> None:
        fight = {
            "damage_done_summary": {
                "exploitDetails": [
                    {"exploit": 7, "abilities": [{"guid": 7, "name": "任意翻譯"}]},
                ]
            }
        }
        self.assertTrue(integrity.has_basic_attack_exploit_marker(fight))

    def test_cutoff_uses_timezone_aware_taipei_time(self) -> None:
        cutoff = integrity.parse_iso_to_epoch_ms("2026-07-28T18:00:00+08:00")
        self.assertIsNotNone(cutoff)
        report = {}
        before = {"recorded_at": cutoff - 1}
        at_cutoff = {"recorded_at": cutoff}
        self.assertFalse(integrity.is_in_scope(report, before, cutoff))
        self.assertTrue(integrity.is_in_scope(report, at_cutoff, cutoff))

    def test_unverifiable_attack_marker_stays_hidden(self) -> None:
        result = integrity.make_unverifiable_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            reason="missing_enemy_max_hp",
            attack_marker=True,
        )
        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])


if __name__ == "__main__":
    unittest.main()
