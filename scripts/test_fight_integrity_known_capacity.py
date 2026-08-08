from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fight_integrity_known_capacity as known_capacity


class KnownEnemyCapacityPolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "fixture": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                )
            },
        )

    @staticmethod
    def make_target_profile_policy() -> known_capacity.KnownEnemyCapacityPolicy:
        return known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "fixture": known_capacity.KnownEnemyCapacityRule(
                    required_enemy_damage_min=199_900,
                    required_enemy_damage_max=200_100,
                    target_damage_profile=known_capacity.KnownTargetDamageProfile(
                        version="fixture-v1",
                        targets={
                            101: known_capacity.KnownTargetDamageRule(
                                guid=101,
                                name="第一目標",
                                max_hp=100_000,
                                expected_damage_instances=1,
                                expected_damage_ratio=1.0,
                                damage_tolerance=100,
                            ),
                            102: known_capacity.KnownTargetDamageRule(
                                guid=102,
                                name="轉場目標",
                                max_hp=250_000,
                                expected_damage_instances=1,
                                expected_damage_ratio=0.4,
                                damage_tolerance=100,
                            ),
                        },
                    ),
                )
            },
        )

    def test_complete_party_over_known_capacity_threshold_is_evidence(self) -> None:
        fight = {"size": 8, "players": [{"total_damage": 13_425} for _ in range(8)]}

        screen = self.policy.screen("fixture", fight)

        self.assertIsNotNone(screen)
        self.assertAlmostEqual(screen.damage_to_known_hp_ratio, 1.074)
        self.assertTrue(screen.exceeds_suspected_threshold)

    def test_partial_party_does_not_produce_known_capacity_evidence(self) -> None:
        fight = {"size": 8, "players": [{"total_damage": 13_425} for _ in range(7)]}

        self.assertIsNone(self.policy.screen("fixture", fight))

    def test_confirmed_total_damage_upper_limit_does_not_require_enemy_hp(self) -> None:
        policy = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "fixture": known_capacity.KnownEnemyCapacityRule(
                    maximum_full_party_damage=100_000,
                )
            },
        )

        screen = policy.screen(
            "fixture",
            {"size": 8, "players": [{"total_damage": 12_625} for _ in range(8)]},
        )

        self.assertIsNotNone(screen)
        self.assertIsNone(screen.damage_to_known_hp_ratio)
        self.assertTrue(screen.exceeds_maximum_full_party_damage)
        self.assertEqual(screen.to_metrics()["maximum_full_party_damage"], 100_000)

    def test_required_full_party_damage_range_distinguishes_low_and_high_anomalies(self) -> None:
        policy = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "fixture": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                    required_full_party_damage_min=99_900,
                    required_full_party_damage_max=100_100,
                )
            },
        )

        matching = policy.screen(
            "fixture",
            {"size": 8, "players": [{"total_damage": 12_500} for _ in range(8)]},
        )
        low = policy.screen(
            "fixture",
            {"size": 8, "players": [{"total_damage": 12_400} for _ in range(8)]},
        )
        high = policy.screen(
            "fixture",
            {"size": 8, "players": [{"total_damage": 12_600} for _ in range(8)]},
        )

        self.assertIsNotNone(matching)
        self.assertTrue(matching.has_required_full_party_damage_range)
        self.assertTrue(matching.matches_required_full_party_damage_range)
        self.assertFalse(matching.is_below_required_full_party_damage_range)
        self.assertFalse(matching.is_above_required_full_party_damage_range)
        self.assertFalse(low.matches_required_full_party_damage_range)
        self.assertTrue(low.is_below_required_full_party_damage_range)
        self.assertFalse(high.matches_required_full_party_damage_range)
        self.assertTrue(high.is_above_required_full_party_damage_range)

    def test_low_player_damage_with_enemy_range_requires_target_measurement(self) -> None:
        policy = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "unreal_suzaku": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=127_613_543,
                    suspected_team_damage_ratio_threshold=1.005,
                    required_full_party_damage_min=71_280_000,
                    required_full_party_damage_max=72_720_000,
                    required_enemy_damage_min=71_280_000,
                    required_enemy_damage_max=72_720_000,
                )
            },
        )

        screen = policy.screen(
            "unreal_suzaku",
            {
                "size": 8,
                "players": [
                    {"total_damage": 8_856_012} for _ in range(5)
                ] + [
                    {"total_damage": 8_856_011} for _ in range(3)
                ],
            },
        )

        self.assertIsNotNone(screen)
        self.assertEqual(screen.team_total_damage, 70_848_093)
        self.assertTrue(screen.needs_enemy_damage_for_low_full_party_total)
        self.assertTrue(screen.to_metrics()["is_below_required_full_party_damage_range"])

    def test_enemy_damage_range_handles_partial_party_source(self) -> None:
        policy = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "fixture": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                    required_enemy_damage_min=99_900,
                    required_enemy_damage_max=100_100,
                )
            },
        )

        screen = policy.screen_enemy_damage("fixture", 101_500)

        self.assertIsNotNone(screen)
        self.assertEqual(screen.damage_source, "enemy_damage")
        self.assertTrue(screen.has_required_enemy_damage_range)
        self.assertFalse(screen.matches_required_enemy_damage_range)
        self.assertEqual(screen.to_metrics()["enemy_damage"], 101_500)

    def test_enemy_damage_upper_limit_requires_target_damage_measurement(self) -> None:
        policy = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "fixture": known_capacity.KnownEnemyCapacityRule(
                    maximum_enemy_damage=100_100,
                )
            },
        )

        # 玩家列傷害不能代替敵方承傷，因此一般 screen 不可攜帶這項上限。
        self.assertIsNone(
            policy.screen(
                "fixture",
                {"size": 8, "players": [{"total_damage": 12_700} for _ in range(8)]},
            ).maximum_enemy_damage
        )
        screen = policy.screen_enemy_damage("fixture", 101_500)

        self.assertIsNotNone(screen)
        self.assertEqual(screen.damage_source, "enemy_damage")
        self.assertTrue(screen.exceeds_maximum_enemy_damage)
        self.assertEqual(screen.to_metrics()["maximum_enemy_damage"], 100_100)

    def test_target_profile_accepts_fixed_hp_and_transition_ratio(self) -> None:
        screen = self.make_target_profile_policy().screen_target_damage_profile(
            "fixture",
            {
                "targets": [
                    {"guid": 101, "damage": 99_950, "max_hp": 100_000, "instance_count": 1},
                    {"guid": 102, "damage": 100_050, "max_hp": 250_000, "instance_count": 1},
                ]
            },
        )

        self.assertIsNotNone(screen)
        self.assertEqual(screen.status, "valid")
        self.assertFalse(screen.is_abnormal)
        self.assertEqual(screen.metrics["expected_enemy_damage"], 200_000)
        transition = next(
            target for target in screen.metrics["target_results"] if target["guid"] == 102
        )
        self.assertEqual(transition["expected_damage_ratio"], 0.4)
        self.assertEqual(transition["observed_damage_ratio"], 0.4002)

    def test_target_profile_rejects_shifted_damage_even_when_total_matches(self) -> None:
        screen = self.make_target_profile_policy().screen_target_damage_profile(
            "fixture",
            {
                "targets": [
                    {"guid": 101, "damage": 110_000, "max_hp": 100_000, "instance_count": 1},
                    {"guid": 102, "damage": 90_000, "max_hp": 250_000, "instance_count": 1},
                ]
            },
        )

        self.assertIsNotNone(screen)
        self.assertEqual(screen.metrics["observed_enemy_damage"], 200_000)
        self.assertEqual(screen.status, "suspected")
        self.assertEqual(screen.reason, "target_damage_profile_mismatch")
        self.assertEqual(screen.metrics["mismatched_target_guids"], [101, 102])

    def test_target_profile_without_per_target_measurement_is_unverifiable(self) -> None:
        screen = self.make_target_profile_policy().screen_target_damage_profile(
            "fixture",
            {"enemy_damage": 200_000, "enemy_hp_capacity": 350_000, "target_count": 2},
        )

        self.assertIsNotNone(screen)
        self.assertEqual(screen.status, "unverifiable")
        self.assertEqual(screen.reason, "missing_target_damage_profile_measurement")

    def test_loader_rejects_non_positive_tolerance(self) -> None:
        payload = {
            "schema_version": 1,
            "enabled": True,
            "metric": known_capacity.METRIC_NAME,
            "encounters": {
                "fixture": {
                    "enemy_hp_capacity": 100_000,
                    "suspected_team_damage_ratio_threshold": 1,
                }
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "known_capacity.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                known_capacity.load_known_enemy_capacity_policy(path)

    def test_repository_policy_contains_confirmed_capacity_and_total_damage_rules(self) -> None:
        """正式設定只能收錄已有重複量測證據的固定生命池。"""

        config_path = Path(__file__).resolve().parent.parent / "config" / "fight_integrity_known_enemy_hp.json"

        policy = known_capacity.load_known_enemy_capacity_policy(config_path)

        self.assertEqual(policy.rules["extreme_zelenia"].enemy_hp_capacity, 92_086_232)
        self.assertEqual(policy.rules["extreme_zelenia"].required_full_party_damage_min, 92_086_132)
        self.assertEqual(policy.rules["extreme_zelenia"].required_full_party_damage_max, 92_086_332)
        self.assertEqual(policy.rules["extreme_zelenia"].required_enemy_damage_min, 92_086_132)
        self.assertEqual(policy.rules["extreme_zelenia"].required_enemy_damage_max, 92_086_332)
        self.assertEqual(policy.rules["unreal_suzaku"].enemy_hp_capacity, 127_613_543)
        self.assertEqual(
            policy.rules["unreal_suzaku"].suspected_team_damage_ratio_threshold,
            1.005,
        )
        self.assertEqual(
            policy.rules["unreal_suzaku"].required_full_party_damage_min,
            71_280_000,
        )
        self.assertEqual(
            policy.rules["unreal_suzaku"].required_full_party_damage_max,
            72_720_000,
        )
        self.assertEqual(
            policy.rules["unreal_suzaku"].required_enemy_damage_min,
            71_280_000,
        )
        self.assertEqual(
            policy.rules["unreal_suzaku"].required_enemy_damage_max,
            72_720_000,
        )
        suzaku_enemy_damage_screen = policy.screen_enemy_damage(
            "unreal_suzaku",
            80_962_111,
        )
        self.assertIsNotNone(suzaku_enemy_damage_screen)
        self.assertFalse(suzaku_enemy_damage_screen.matches_required_enemy_damage_range)
        self.assertEqual(
            policy.rules["ultimate_futures_rewritten"].maximum_full_party_damage,
            151_500_000,
        )
        self.assertEqual(
            policy.rules["ultimate_futures_rewritten"].maximum_enemy_damage,
            151_500_000,
        )
        self.assertEqual(
            policy.rules["ultimate_bahamut"].maximum_full_party_damage,
            13_230_230,
        )
        self.assertEqual(policy.rules["savage_m1s"].maximum_full_party_damage, 75_870_000)
        self.assertEqual(policy.rules["savage_m3s"].maximum_full_party_damage, 96_523_000)
        self.assertEqual(policy.rules["savage_m4s"].maximum_full_party_damage, 114_526_000)
        self.assertEqual(policy.rules["savage_m5s"].required_enemy_damage_min, 105_549_582)
        self.assertEqual(policy.rules["savage_m6s"].required_enemy_damage_max, 130_232_146)
        self.assertEqual(policy.rules["savage_m7s"].required_enemy_damage_min, 121_558_848)
        self.assertEqual(policy.rules["savage_m8s"].required_enemy_damage_max, 148_749_191)
        expected_totals = {
            "savage_m5s": 105_549_682,
            "savage_m6s": 130_232_046,
            "savage_m7s": 121_558_948,
            "savage_m8s": 148_749_091,
        }
        for encounter_key, expected_total in expected_totals.items():
            with self.subTest(encounter_key=encounter_key):
                rule = policy.rules[encounter_key]
                profile = policy.target_damage_profile(encounter_key)
                self.assertIsNotNone(profile)
                self.assertEqual(
                    sum(target.expected_damage for target in profile.targets.values()),
                    expected_total,
                )
                self.assertEqual(rule.required_enemy_damage_min, expected_total - 100)
                self.assertEqual(rule.required_enemy_damage_max, expected_total + 100)
        m8_profile = policy.target_damage_profile("savage_m8s")
        self.assertIsNotNone(m8_profile)
        self.assertEqual(m8_profile.targets[18215].max_hp, 67_582_753)
        self.assertEqual(m8_profile.targets[18222].max_hp, 72_751_588)
        self.assertEqual(m8_profile.targets[18219].expected_damage_ratio, 0.4)
        self.assertEqual(m8_profile.targets[18225].expected_damage_ratio, 0.4)


if __name__ == "__main__":
    unittest.main()
