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

    def test_repository_policy_contains_confirmed_zelenia_and_suzaku_capacities(self) -> None:
        """正式設定只能收錄已有重複量測證據的固定生命池。"""

        config_path = Path(__file__).resolve().parent.parent / "config" / "fight_integrity_known_enemy_hp.json"

        policy = known_capacity.load_known_enemy_capacity_policy(config_path)

        self.assertEqual(policy.rules["extreme_zelenia"].enemy_hp_capacity, 92_086_232)
        self.assertEqual(policy.rules["unreal_suzaku"].enemy_hp_capacity, 127_613_543)
        self.assertEqual(
            policy.rules["unreal_suzaku"].suspected_team_damage_ratio_threshold,
            1.005,
        )


if __name__ == "__main__":
    unittest.main()
