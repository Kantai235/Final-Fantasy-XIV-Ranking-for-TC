from __future__ import annotations

import json
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

    def test_rule_classification_is_not_cacheable_as_measurement_failure(self) -> None:
        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)

        with self.assertRaises(ValueError):
            cache.put_unverifiable(
                "ABC123",
                self.report,
                self.fight,
                reason="enemy_damage_outside_required_confirmed_total_range",
                cached_at_iso="2026-08-04T00:00:00Z",
            )

    def test_basic_attack_aggregate_coexists_with_enemy_hp_measurement(self) -> None:
        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)
        cache.put(
            "ABC123",
            self.report,
            self.fight,
            measurement={"enemy_damage": 100_000, "enemy_hp_capacity": 100_000, "target_count": 1},
            cached_at_iso="2026-08-06T00:00:00Z",
        )
        cache.put_basic_attack(
            "ABC123",
            self.report,
            self.fight,
            measurement={
                "actual_event_count": 180,
                "mapped_event_count": 180,
                "players": [
                    {
                        "source_id": 10,
                        "job": "Reaper",
                        "attack_event_count": 180,
                        "pure_normal_count": 80,
                        "pure_normal_median": 19_842,
                        "attack_damage": 4_574_613,
                        "attack_share": 0.1757,
                    },
                    {
                        "source_id": 11,
                        "job": "Paladin",
                        "attack_event_count": 1,
                        "pure_normal_count": 0,
                        "pure_normal_median": None,
                        "attack_damage": 0,
                        "attack_share": 0,
                    },
                ],
            },
            cached_at_iso="2026-08-06T00:00:00Z",
        )

        reloaded = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)

        self.assertIsNotNone(reloaded.get("ABC123", self.report, self.fight))
        basic = reloaded.get_basic_attack("ABC123", self.report, self.fight)
        self.assertIsNotNone(basic)
        self.assertEqual(basic["players"][0]["pure_normal_median"], 19_842)
        self.assertEqual(basic["players"][1]["attack_damage"], 0)
        self.assertEqual(basic["players"][1]["attack_share"], 0)
        content = self.cache_path.read_text(encoding="utf-8")
        self.assertNotIn("raw_events", content)
        self.assertNotIn("player_name", content)

    def test_schema_three_enemy_hp_cache_remains_readable(self) -> None:
        source_fingerprint = cache_module._source_fingerprint(self.report, self.fight)
        self.cache_path.write_text(
            json.dumps({
                "schema_version": 3,
                "entries": {
                    "ABC123:7": {
                        "source_fingerprint": source_fingerprint,
                        "outcome": "measured",
                        "measurement": {
                            "enemy_damage": 100_000,
                            "enemy_hp_capacity": 100_000,
                            "target_count": 1,
                        },
                    }
                },
            }),
            encoding="utf-8",
        )

        cache = cache_module.FightIntegrityMeasurementCache.load(self.cache_path)

        self.assertIsNotNone(cache.get("ABC123", self.report, self.fight))
        self.assertIsNone(cache.get_basic_attack("ABC123", self.report, self.fight))


if __name__ == "__main__":
    unittest.main()
