from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import fight_integrity_baselines as baselines


class HistoricalDamageBaselinePolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = baselines.HistoricalDamageBaselinePolicy(
            enabled=True,
            reference_cutoff_iso="2026-07-28T18:00:00+08:00",
            screening_multiplier=1.05,
            baselines={
                "fixture": baselines.HistoricalDamageBaseline(
                    upper_reference_damage=1_000,
                    sample_count=500,
                    unique_fight_count=300,
                )
            },
        )

    def test_complete_party_below_upper_screen_is_local_valid_candidate(self) -> None:
        fight = {"size": 8, "players": [{"total_damage": 125} for _ in range(8)]}

        screen = self.policy.screen("fixture", fight)

        self.assertIsNotNone(screen)
        self.assertEqual(screen.team_total_damage, 1_000)
        self.assertEqual(screen.screening_threshold, 1_050)
        self.assertFalse(screen.exceeds_threshold)
        self.assertEqual(screen.to_metrics()["metric"], baselines.METRIC_NAME)

    def test_partial_party_is_never_used_as_historical_reference(self) -> None:
        fight = {"size": 8, "players": [{"total_damage": 125} for _ in range(7)]}

        self.assertIsNone(self.policy.screen("fixture", fight))

    def test_loader_rejects_baseline_below_minimum_unique_sample_count(self) -> None:
        payload = {
            "schema_version": 1,
            "enabled": True,
            "metric": baselines.METRIC_NAME,
            "reference_cutoff_iso": "2026-07-28T18:00:00+08:00",
            "minimum_sample_count": 100,
            "screening_multiplier": 1.05,
            "encounters": {
                "fixture": {
                    "upper_reference_damage": 1_000,
                    "sample_count": 100,
                    "unique_fight_count": 99,
                }
            },
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "baselines.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "fixture"):
                baselines.load_historical_damage_baseline_policy(path)


if __name__ == "__main__":
    unittest.main()
