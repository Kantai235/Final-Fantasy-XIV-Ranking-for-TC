from __future__ import annotations

import unittest

import fight_integrity as integrity
import fight_integrity_baselines as baselines
import fight_integrity_known_capacity as known_capacity


class FightIntegrityTest(unittest.TestCase):
    def test_hp_ratio_over_threshold_is_excluded(self) -> None:
        result = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=115_001,
            enemy_hp_capacity=100_000,
            target_count=2,
            attack_marker=False,
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
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
            suspected_hp_ratio_threshold=1.14,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("fflogs_basic_attack_exploit_marker", result["reasons"])
        self.assertNotIn("enemy_damage_exceeds_hp_ratio_threshold", result["reasons"])

    def test_near_hp_ratio_threshold_is_suspected_without_attack_marker(self) -> None:
        result = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=114_274.4,
            enemy_hp_capacity=100_000,
            target_count=2,
            attack_marker=False,
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertEqual(result["reasons"], ["enemy_damage_reaches_suspected_hp_ratio_threshold"])

    def test_ratio_below_near_hp_threshold_is_valid_without_attack_marker(self) -> None:
        result = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=113_999.9,
            enemy_hp_capacity=100_000,
            target_count=2,
            attack_marker=False,
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
        )

        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["hidden_from_public"])

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

    def test_existing_v2_hp_measurement_requires_current_rule_recheck(self) -> None:
        fight = {"data_integrity": {"calculation_version": 2, "status": "valid"}}

        self.assertTrue(integrity.needs_check(fight))
        self.assertTrue(integrity.is_hidden_from_public(fight))

    def test_existing_v8_valid_result_remains_public_without_recheck(self) -> None:
        fight = {
            "data_integrity": {
                "calculation_version": 8,
                "status": "valid",
                "hidden_from_public": False,
            }
        }

        self.assertFalse(integrity.needs_check(fight))
        self.assertFalse(integrity.is_hidden_from_public(fight))

    def test_existing_v8_not_applicable_result_remains_public_without_recheck(self) -> None:
        fight = {
            "data_integrity": {
                "calculation_version": 8,
                "status": "not_applicable",
                "hidden_from_public": False,
            }
        }

        self.assertFalse(integrity.needs_check(fight))
        self.assertFalse(integrity.is_hidden_from_public(fight))

    def test_existing_v8_failed_result_stays_hidden_and_enters_v9_recheck(self) -> None:
        for status in ("excluded", "suspected", "unverifiable"):
            with self.subTest(status=status):
                fight = {
                    "data_integrity": {
                        "calculation_version": 8,
                        "status": status,
                        "hidden_from_public": True,
                    }
                }

                self.assertTrue(integrity.needs_check(fight))
                self.assertTrue(integrity.is_hidden_from_public(fight))

    def test_unverifiable_attack_marker_stays_hidden(self) -> None:
        result = integrity.make_unverifiable_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            reason="missing_enemy_max_hp",
            attack_marker=True,
        )
        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])

    def test_unverifiable_historical_high_damage_stays_hidden_as_suspected(self) -> None:
        screen = baselines.HistoricalDamageScreen(
            encounter_key="fixture",
            team_total_damage=1_100,
            upper_reference_damage=1_000,
            screening_threshold=1_050,
            screening_multiplier=1.05,
            sample_count=500,
            unique_fight_count=300,
            reference_cutoff_iso="2026-07-28T18:00:00+08:00",
        )

        result = integrity.make_unverifiable_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            reason="missing_enemy_max_hp",
            attack_marker=False,
            historical_screen=screen,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("historical_team_damage_exceeds_screen_threshold", result["reasons"])

    def test_known_capacity_lower_bound_hides_zelenia_style_anomaly_before_hp_query(self) -> None:
        screen = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="extreme_zelenia",
            team_total_damage=107_393,
            enemy_hp_capacity=100_000,
            suspected_team_damage_ratio_threshold=1.005,
        )

        result = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=107_393,
            enemy_hp_capacity=100_000,
            target_count=2,
            attack_marker=False,
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
            known_capacity_screen=screen,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("full_party_damage_exceeds_known_hp_suspected_ratio_threshold", result["reasons"])

    def test_required_full_party_damage_range_hides_both_low_and_high_results(self) -> None:
        matching = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="extreme_zelenia",
            team_total_damage=100_000,
            enemy_hp_capacity=100_000,
            suspected_team_damage_ratio_threshold=1.005,
            required_full_party_damage_min=99_900,
            required_full_party_damage_max=100_100,
        )
        low = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="extreme_zelenia",
            team_total_damage=99_899,
            enemy_hp_capacity=100_000,
            suspected_team_damage_ratio_threshold=1.005,
            required_full_party_damage_min=99_900,
            required_full_party_damage_max=100_100,
        )
        high = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="extreme_zelenia",
            team_total_damage=115_001,
            enemy_hp_capacity=100_000,
            suspected_team_damage_ratio_threshold=1.005,
            required_full_party_damage_min=99_900,
            required_full_party_damage_max=100_100,
        )

        matching_result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=matching,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )
        low_result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=low,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )
        high_result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=high,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )
        attack_result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=matching,
            hp_ratio_threshold=1.15,
            attack_marker=True,
        )

        self.assertEqual(matching_result["status"], "valid")
        self.assertFalse(matching_result["hidden_from_public"])
        self.assertEqual(low_result["status"], "suspected")
        self.assertTrue(low_result["hidden_from_public"])
        self.assertEqual(high_result["status"], "excluded")
        self.assertTrue(high_result["hidden_from_public"])
        self.assertIn("full_party_damage_outside_required_known_total_range", low_result["reasons"])
        self.assertEqual(attack_result["status"], "suspected")
        self.assertTrue(attack_result["hidden_from_public"])

    def test_required_enemy_damage_range_hides_partial_party_anomaly(self) -> None:
        screen = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="extreme_zelenia",
            team_total_damage=101_500,
            enemy_hp_capacity=100_000,
            suspected_team_damage_ratio_threshold=1.005,
            required_enemy_damage_min=99_900,
            required_enemy_damage_max=100_100,
            damage_source="enemy_damage",
        )

        result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=screen,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("enemy_damage_outside_required_confirmed_total_range", result["reasons"])

    def test_required_enemy_damage_range_uses_enemy_source_when_both_ranges_exist(self) -> None:
        screen = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="unreal_suzaku",
            team_total_damage=71_943_449,
            enemy_hp_capacity=127_613_543,
            suspected_team_damage_ratio_threshold=1.005,
            required_full_party_damage_min=71_280_000,
            required_full_party_damage_max=72_720_000,
            required_enemy_damage_min=71_280_000,
            required_enemy_damage_max=72_720_000,
            damage_source="enemy_damage",
        )

        result = integrity.make_known_capacity_result(
            checked_at_iso="2026-08-04T00:00:00Z",
            known_capacity_screen=screen,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )

        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["hidden_from_public"])
        self.assertEqual(
            result["reasons"],
            ["enemy_damage_matches_required_confirmed_total_range"],
        )

    def test_confirmed_total_damage_upper_limit_hides_without_hp_ratio(self) -> None:
        screen = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="ultimate_bahamut",
            team_total_damage=243_355_653,
            maximum_full_party_damage=13_230_230,
        )

        result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=screen,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn(
            "full_party_damage_exceeds_confirmed_total_damage_upper_limit",
            result["reasons"],
        )
        self.assertIsNone(
            result["metrics"]["known_full_party_damage"].get("enemy_hp_capacity"),
        )

    def test_confirmed_enemy_damage_upper_limit_hides_without_hp_ratio(self) -> None:
        screen = known_capacity.KnownEnemyCapacityScreen(
            encounter_key="ultimate_futures_rewritten",
            team_total_damage=152_651_798,
            maximum_enemy_damage=151_500_000,
            damage_source="enemy_damage",
        )

        result = integrity.make_known_capacity_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            known_capacity_screen=screen,
            hp_ratio_threshold=1.15,
            attack_marker=False,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn(
            "enemy_damage_exceeds_confirmed_total_damage_upper_limit",
            result["reasons"],
        )
        known_metrics = result["metrics"]["known_full_party_damage"]
        self.assertEqual(known_metrics["damage_source"], "enemy_damage")
        self.assertEqual(known_metrics["maximum_enemy_damage"], 151_500_000)

    def test_unverifiable_fight_is_fail_closed(self) -> None:
        result = integrity.make_unverifiable_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            reason="offline_measurement_not_available",
            attack_marker=False,
        )

        self.assertEqual(result["status"], "unverifiable")
        self.assertTrue(result["hidden_from_public"])

    def test_unmarked_post_cutoff_fight_is_not_public(self) -> None:
        cutoff = integrity.parse_iso_to_epoch_ms(integrity.DEFAULT_CUTOFF_ISO)
        self.assertIsNotNone(cutoff)

        self.assertTrue(integrity.is_hidden_from_public({"recorded_at": cutoff}))


if __name__ == "__main__":
    unittest.main()
