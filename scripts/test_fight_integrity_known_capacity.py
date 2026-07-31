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
        self.assertFalse(low.matches_required_full_party_damage_range)
        self.assertFalse(high.matches_required_full_party_damage_range)

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


if __name__ == "__main__":
    unittest.main()
