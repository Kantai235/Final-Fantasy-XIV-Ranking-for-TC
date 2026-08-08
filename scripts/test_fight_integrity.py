from __future__ import annotations

import unittest

import fight_integrity as integrity
import fight_integrity_baselines as baselines
import fight_integrity_known_capacity as known_capacity


class FightIntegrityTest(unittest.TestCase):
    def make_basic_attack_policy(self) -> integrity.BasicAttackDistributionPolicy:
        return integrity.BasicAttackDistributionPolicy.from_mapping({
            "enabled": True,
            "reference_version": "fixture",
            "encounter_keys": ["savage_m6s"],
            "reference_hit_median": 4_805.7,
            "reference_attack_share": 0.0861,
        })

    @staticmethod
    def basic_attack_player(
        source_id: int,
        job: str,
        hit_median: float,
        attack_share: float,
        *,
        attack_count: int = 180,
        pure_count: int = 80,
    ) -> dict[str, object]:
        return {
            "source_id": source_id,
            "job": job,
            "attack_event_count": attack_count,
            "pure_normal_count": pure_count,
            "pure_normal_median": hit_median,
            "attack_damage": 4_000_000,
            "attack_share": attack_share,
        }

    def test_basic_attack_summary_uses_only_actual_non_crit_non_direct_hits(self) -> None:
        players = [{"fflogs_id": 10, "job": "Reaper", "total_damage": 1_000}]
        events = [
            {
                "timestamp": 1,
                "packetID": 1,
                "type": "calculateddamage",
                "sourceID": 10,
                "targetID": 20,
                "abilityGameID": 7,
                "hitType": 1,
                "amount": 200,
                "multiplier": 2,
            },
            {
                "timestamp": 2,
                "packetID": 1,
                "type": "damage",
                "sourceID": 10,
                "targetID": 20,
                "abilityGameID": 7,
                "hitType": 1,
                "amount": 200,
                "multiplier": 2,
            },
            {
                "timestamp": 3,
                "packetID": 2,
                "type": "damage",
                "sourceID": 10,
                "targetID": 20,
                "abilityGameID": 7,
                "hitType": 1,
                "directHit": True,
                "amount": 250,
                "multiplier": 1,
            },
            {
                "timestamp": 4,
                "packetID": 3,
                "type": "damage",
                "sourceID": 10,
                "targetID": 20,
                "abilityGameID": 7,
                "hitType": 2,
                "amount": 300,
                "multiplier": 1,
            },
        ]

        measurement = integrity.summarize_basic_attack_events(events, players)

        self.assertEqual(measurement["actual_event_count"], 3)
        self.assertEqual(measurement["mapped_event_count"], 3)
        player = measurement["players"][0]
        self.assertEqual(player["attack_event_count"], 3)
        self.assertEqual(player["pure_normal_count"], 1)
        self.assertEqual(player["pure_normal_median"], 100)
        self.assertEqual(player["attack_damage"], 750)
        self.assertEqual(player["attack_share"], 0.75)

    def test_basic_attack_normal_team_is_valid(self) -> None:
        policy = self.make_basic_attack_policy()
        measurement = {
            "actual_event_count": 900,
            "mapped_event_count": 900,
            "players": [
                self.basic_attack_player(index, job, 5_000, 0.09)
                for index, job in enumerate(
                    ("Warrior", "Paladin", "Samurai", "Viper", "Dancer"),
                    start=1,
                )
            ],
        }

        screen = policy.screen(measurement)

        self.assertEqual(screen.status, "valid")
        self.assertEqual(screen.metrics["eligible_player_count"], 5)
        self.assertEqual(screen.metrics["flagged_player_count"], 0)

    def test_basic_attack_four_of_five_abnormal_players_are_excluded(self) -> None:
        policy = self.make_basic_attack_policy()
        measurement = {
            "actual_event_count": 900,
            "mapped_event_count": 900,
            "players": [
                self.basic_attack_player(1, "Warrior", 17_000, 0.23),
                self.basic_attack_player(2, "Paladin", 23_000, 0.28),
                self.basic_attack_player(3, "Samurai", 17_100, 0.24),
                self.basic_attack_player(4, "Reaper", 19_800, 0.18),
                self.basic_attack_player(5, "Dancer", 5_700, 0.10),
            ],
        }

        screen = policy.screen(measurement)

        self.assertEqual(screen.status, "excluded")
        self.assertEqual(screen.reason, "team_basic_attack_damage_distribution_abnormal")
        self.assertEqual(screen.metrics["flagged_player_count"], 4)
        self.assertGreaterEqual(screen.metrics["group_hit_median"], 15_000)
        self.assertGreaterEqual(screen.metrics["group_attack_share"], 0.20)

    def test_basic_attack_three_of_five_abnormal_players_are_suspected(self) -> None:
        policy = self.make_basic_attack_policy()
        measurement = {
            "actual_event_count": 900,
            "mapped_event_count": 900,
            "players": [
                self.basic_attack_player(1, "Warrior", 16_000, 0.18),
                self.basic_attack_player(2, "Samurai", 16_500, 0.19),
                self.basic_attack_player(3, "Viper", 17_000, 0.20),
                self.basic_attack_player(4, "Paladin", 3_300, 0.09),
                self.basic_attack_player(5, "Dancer", 5_700, 0.10),
            ],
        }

        screen = policy.screen(measurement)

        self.assertEqual(screen.status, "suspected")
        self.assertEqual(screen.reason, "multiple_players_basic_attack_metrics_abnormal")
        self.assertEqual(screen.metrics["flagged_player_ratio"], 0.6)

    def test_basic_attack_requires_both_hit_and_share_thresholds(self) -> None:
        policy = self.make_basic_attack_policy()
        measurement = {
            "actual_event_count": 700,
            "mapped_event_count": 700,
            "players": [
                self.basic_attack_player(1, "Warrior", 16_000, 0.10),
                self.basic_attack_player(2, "Samurai", 5_000, 0.20),
                self.basic_attack_player(3, "Viper", 5_000, 0.09),
                self.basic_attack_player(4, "Paladin", 3_300, 0.09),
            ],
        }

        screen = policy.screen(measurement)

        self.assertEqual(screen.status, "valid")
        self.assertEqual(screen.metrics["flagged_player_count"], 0)

    def test_basic_attack_screen_never_downgrades_existing_excluded_result(self) -> None:
        screen = self.make_basic_attack_policy().screen({
            "actual_event_count": 700,
            "mapped_event_count": 700,
            "players": [
                self.basic_attack_player(index, job, 5_000, 0.09)
                for index, job in enumerate(("Warrior", "Paladin", "Samurai"), start=1)
            ],
        })
        result = {
            "status": "excluded",
            "hidden_from_public": True,
            "reasons": ["enemy_damage_exceeds_hp_ratio_threshold"],
        }

        merged = integrity.apply_basic_attack_distribution_screen(result, screen)

        self.assertEqual(merged["status"], "excluded")
        self.assertTrue(merged["hidden_from_public"])
        self.assertIn("basic_attack_distribution", merged["metrics"])

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

    def test_existing_v10_valid_result_remains_generically_public(self) -> None:
        fight = {
            "data_integrity": {
                "calculation_version": 10,
                "status": "valid",
                "hidden_from_public": False,
            }
        }

        self.assertFalse(integrity.needs_check(fight))
        self.assertFalse(integrity.is_hidden_from_public(fight))

    def test_existing_v8_failed_result_stays_hidden_and_enters_current_recheck(self) -> None:
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

    def test_current_transient_measurement_failure_is_retried(self) -> None:
        fight = {
            "data_integrity": {
                "calculation_version": integrity.CALCULATION_VERSION,
                "status": "unverifiable",
                "hidden_from_public": True,
                "reasons": ["integrity_measurement_failed"],
            }
        }

        self.assertTrue(integrity.needs_check(fight))

    def test_current_reproducible_unverifiable_result_is_not_retried_each_run(self) -> None:
        fight = {
            "data_integrity": {
                "calculation_version": integrity.CALCULATION_VERSION,
                "status": "unverifiable",
                "hidden_from_public": True,
                "reasons": ["missing_enemy_max_hp"],
            }
        }

        self.assertFalse(integrity.needs_check(fight))

    def test_unverifiable_attack_marker_stays_hidden(self) -> None:
        result = integrity.make_unverifiable_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            reason="missing_enemy_max_hp",
            attack_marker=True,
        )
        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])

    def test_target_profile_mismatch_is_independent_hidden_evidence(self) -> None:
        screen = known_capacity.KnownTargetDamageProfileScreen(
            encounter_key="savage_m8s",
            profile_version="fixture-v1",
            status="suspected",
            reason="target_damage_profile_mismatch",
            metrics={"mismatched_target_guids": [18219]},
        )

        result = integrity.evaluate(
            checked_at_iso="2026-08-09T00:00:00Z",
            enemy_damage=100_000,
            enemy_hp_capacity=100_000,
            target_count=1,
            attack_marker=False,
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
            target_damage_profile_screen=screen,
        )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("target_damage_profile_mismatch", result["reasons"])
        self.assertEqual(
            result["metrics"]["target_damage_profile"]["profile_version"],
            "fixture-v1",
        )

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
