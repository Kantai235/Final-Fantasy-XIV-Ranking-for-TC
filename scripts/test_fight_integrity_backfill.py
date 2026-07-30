from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backfill_fight_integrity as backfill
import fight_integrity as integrity
import fight_integrity_cache as cache_module


class FightIntegrityBackfillCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.cache = cache_module.FightIntegrityMeasurementCache.load(
            Path(temporary_directory.name) / "measurements.json"
        )
        self.candidate = backfill.Candidate(
            encounter_key="extreme_zelenia",
            encounter={},
            ranking={},
            report_code="ABC123",
            report={"start_time": 1_000, "end_time": 10_000, "revision": 1},
            fight={
                "fight_id": 7,
                "start_time": 2_000,
                "end_time": 9_000,
                "encounter_id": 1080,
                "difficulty": 100,
                "recorded_at": 9_000,
            },
            sort_time=9_000,
        )
        self.config = backfill.IntegrityConfig(
            enabled=True,
            cutoff_ms=0,
            cutoff_iso="2026-07-28T18:00:00+08:00",
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
            excluded_encounter_keys=set(),
            default_report_limit=25,
        )

    def test_recheck_uses_cached_measurement_unless_refresh_requested(self) -> None:
        with (
            patch.object(
                backfill,
                "query_target_damage",
                return_value=([{"id": 10, "damage": 120_000, "instance_count": 1}], {10: 1}),
            ) as query_damage,
            patch.object(backfill, "query_target_max_hp", return_value={10: 100_000}) as query_max_hp,
        ):
            first_result, first_cache_hit = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
            )
            second_result, second_cache_hit = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:01:00Z",
                self.cache,
                refresh_cache=False,
            )
            _, refreshed_cache_hit = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:02:00Z",
                self.cache,
                refresh_cache=True,
            )

        self.assertEqual(first_result["status"], "excluded")
        self.assertEqual(second_result["status"], "excluded")
        self.assertFalse(first_cache_hit)
        self.assertTrue(second_cache_hit)
        self.assertFalse(refreshed_cache_hit)
        self.assertEqual(query_damage.call_count, 2)
        self.assertEqual(query_max_hp.call_count, 2)

    def test_existing_result_seeds_cache_without_an_api_query(self) -> None:
        self.candidate.fight["data_integrity"] = integrity.evaluate(
            checked_at_iso="2026-07-30T00:00:00Z",
            enemy_damage=120_000,
            enemy_hp_capacity=100_000,
            target_count=1,
            attack_marker=False,
            hp_ratio_threshold=1.15,
            suspected_hp_ratio_threshold=1.14,
        )

        seeded = backfill.seed_measurement_cache_from_results([self.candidate], self.cache)

        self.assertEqual(seeded, 1)
        self.assertEqual(
            self.cache.get(self.candidate.report_code, self.candidate.report, self.candidate.fight),
            {
                "outcome": "measured",
                "measurement": {"enemy_damage": 120_000.0, "enemy_hp_capacity": 100_000.0, "target_count": 1},
            },
        )

    def test_existing_unverifiable_result_seeds_without_requery(self) -> None:
        self.candidate.fight["data_integrity"] = integrity.make_unverifiable_result(
            checked_at_iso="2026-07-30T00:00:00Z",
            reason="missing_enemy_max_hp",
            attack_marker=True,
        )

        seeded = backfill.seed_measurement_cache_from_results([self.candidate], self.cache)

        self.assertEqual(seeded, 1)
        self.assertEqual(
            self.cache.get(self.candidate.report_code, self.candidate.report, self.candidate.fight),
            {"outcome": "unverifiable", "reason": "missing_enemy_max_hp"},
        )


if __name__ == "__main__":
    unittest.main()
