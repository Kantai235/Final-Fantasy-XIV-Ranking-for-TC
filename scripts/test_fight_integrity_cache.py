from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import fight_integrity_cache as cache_module


class FightIntegrityMeasurementCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.cache_path = Path(self.temporary_directory.name) / "measurements.json"
        self.report = {
            "start_time": 1_000,
            "end_time": 10_000,
            "revision": 3,
        }
        self.fight = {
            "fight_id": 7,
            "start_time": 2_000,
            "end_time": 9_000,
            "encounter_id": 1080,
            "difficulty": 100,
            "recorded_at": 9_000,
        }

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_persists_minimal_measurement_and_reloads_it(self) -> None:
        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)
        cache.put(
            "ABC123",
            self.report,
            self.fight,
            measurement={"enemy_damage": 150_000, "enemy_hp_capacity": 100_000, "target_count": 1},
            cached_at_iso="2026-07-30T00:00:00Z",
        )

        reloaded = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)
        measurement = reloaded.get("ABC123", self.report, self.fight)

        self.assertIsNotNone(measurement)
        self.assertEqual(
            measurement,
            {
                "outcome": "measured",
                "measurement": {"enemy_damage": 150_000.0, "enemy_hp_capacity": 100_000.0, "target_count": 1},
            },
        )
        content = self.cache_path.read_text(encoding="utf-8")
        self.assertNotIn("raw_events", content)
        self.assertNotIn("playerDetails", content)
        self.assertNotIn("instance_count", content)

    def test_source_revision_change_invalidates_cached_measurement(self) -> None:
        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)
        cache.put(
            "ABC123",
            self.report,
            self.fight,
            measurement={"enemy_damage": 100_000, "enemy_hp_capacity": 100_000, "target_count": 1},
            cached_at_iso="2026-07-30T00:00:00Z",
        )

        changed_report = {**self.report, "revision": 4}
        self.assertIsNone(cache.get("ABC123", changed_report, self.fight))

    def test_invalid_measurement_is_not_cacheable(self) -> None:
        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)
        with self.assertRaises(ValueError):
            cache.put(
                "ABC123",
                self.report,
                self.fight,
                measurement={"enemy_damage": 0, "enemy_hp_capacity": 0, "target_count": 0},
                cached_at_iso="2026-07-30T00:00:00Z",
            )

    def test_unverifiable_result_is_cacheable_without_measurement_payload(self) -> None:
        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)
        cache.put_unverifiable(
            "ABC123",
            self.report,
            self.fight,
            reason="missing_enemy_max_hp",
            cached_at_iso="2026-07-30T00:00:00Z",
        )

        self.assertEqual(
            cache.get("ABC123", self.report, self.fight),
            {"outcome": "unverifiable", "reason": "missing_enemy_max_hp"},
        )


if __name__ == "__main__":
    unittest.main()
