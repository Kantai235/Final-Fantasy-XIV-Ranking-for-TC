from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backfill_fight_integrity as backfill
import fight_integrity as integrity
import fight_integrity_baselines as baselines
import fight_integrity_cache as cache_module
import fight_integrity_known_capacity as known_capacity


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
            first_result, first_cache_hit, first_api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
            )
            second_result, second_cache_hit, second_api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:01:00Z",
                self.cache,
                refresh_cache=False,
            )
            _, refreshed_cache_hit, refreshed_api_queried = backfill.evaluate_candidate(
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
        self.assertTrue(first_api_queried)
        self.assertFalse(second_api_queried)
        self.assertTrue(refreshed_api_queried)
        self.assertEqual(query_damage.call_count, 2)
        self.assertEqual(query_max_hp.call_count, 2)

    def test_historical_baseline_normal_fight_skips_hp_query(self) -> None:
        self.candidate.encounter_key = "savage_m1s"
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 125} for _ in range(8)]
        self.config.historical_damage_baselines = baselines.HistoricalDamageBaselinePolicy(
            enabled=True,
            reference_cutoff_iso="2026-07-28T18:00:00+08:00",
            screening_multiplier=1.05,
            baselines={
                "savage_m1s": baselines.HistoricalDamageBaseline(
                    upper_reference_damage=1_000,
                    sample_count=500,
                    unique_fight_count=300,
                )
            },
        )

        with (
            patch.object(backfill, "query_target_damage") as query_damage,
            patch.object(backfill, "query_target_max_hp") as query_max_hp,
        ):
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
            )

        self.assertEqual(result["status"], "valid")
        self.assertFalse(cache_hit)
        self.assertFalse(api_queried)
        self.assertFalse(result["metrics"]["historical_team_damage"]["exceeds_threshold"])
        query_damage.assert_not_called()
        query_max_hp.assert_not_called()

    def test_offline_historical_high_damage_is_hidden_without_api_measurement(self) -> None:
        self.candidate.encounter_key = "savage_m1s"
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 138} for _ in range(8)]
        self.config.historical_damage_baselines = baselines.HistoricalDamageBaselinePolicy(
            enabled=True,
            reference_cutoff_iso="2026-07-28T18:00:00+08:00",
            screening_multiplier=1.05,
            baselines={
                "savage_m1s": baselines.HistoricalDamageBaseline(
                    upper_reference_damage=1_000,
                    sample_count=500,
                    unique_fight_count=300,
                )
            },
        )

        with (
            patch.object(
                backfill,
                "query_target_damage",
                return_value=([{"id": 10, "damage": 100_000, "instance_count": 1}], {10: 1}),
            ) as query_damage,
            patch.object(backfill, "query_target_max_hp", return_value={10: 100_000}) as query_max_hp,
        ):
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
                offline_only=True,
            )

        self.assertEqual(result["status"], "suspected")
        self.assertFalse(cache_hit)
        self.assertFalse(api_queried)
        self.assertTrue(result["metrics"]["historical_team_damage"]["exceeds_threshold"])
        query_damage.assert_not_called()
        query_max_hp.assert_not_called()

    def test_known_capacity_high_damage_is_hidden_without_api_measurement(self) -> None:
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 13_425} for _ in range(8)]
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "extreme_zelenia": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                )
            },
        )

        with (
            patch.object(backfill, "query_target_damage") as query_damage,
            patch.object(backfill, "query_target_max_hp") as query_max_hp,
        ):
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
                offline_only=True,
            )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertFalse(cache_hit)
        self.assertFalse(api_queried)
        query_damage.assert_not_called()
        query_max_hp.assert_not_called()

    def test_multiphase_encounter_total_damage_upper_limit_overrides_not_applicable(self) -> None:
        self.candidate.encounter_key = "ultimate_bahamut"
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 30_000_000} for _ in range(8)]
        self.config.excluded_encounter_keys = {"ultimate_bahamut"}
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "ultimate_bahamut": known_capacity.KnownEnemyCapacityRule(
                    maximum_full_party_damage=13_230_230,
                )
            },
        )

        with patch.object(backfill, "query_target_damage") as query_damage:
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
                offline_only=True,
            )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertFalse(cache_hit)
        self.assertFalse(api_queried)
        query_damage.assert_not_called()

    def test_required_total_damage_range_replaces_old_cached_result_without_api(self) -> None:
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 12_400} for _ in range(8)]
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "extreme_zelenia": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                    required_full_party_damage_min=99_900,
                    required_full_party_damage_max=100_100,
                )
            },
        )
        self.cache.put(
            self.candidate.report_code,
            self.candidate.report,
            self.candidate.fight,
            measurement={"enemy_damage": 100_000, "enemy_hp_capacity": 100_000, "target_count": 1},
            cached_at_iso="2026-07-30T00:00:00Z",
        )

        with patch.object(backfill, "query_target_damage") as query_damage:
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
                offline_only=True,
            )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertFalse(cache_hit)
        self.assertFalse(api_queried)
        self.assertIn("full_party_damage_outside_required_known_total_range", result["reasons"])
        query_damage.assert_not_called()

    def test_enemy_damage_range_replaces_partial_party_valid_result_without_api(self) -> None:
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 12_500} for _ in range(7)]
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "extreme_zelenia": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                    required_enemy_damage_min=99_900,
                    required_enemy_damage_max=100_100,
                )
            },
        )
        self.cache.put(
            self.candidate.report_code,
            self.candidate.report,
            self.candidate.fight,
            measurement={"enemy_damage": 101_500, "enemy_hp_capacity": 100_000, "target_count": 1},
            cached_at_iso="2026-07-30T00:00:00Z",
        )

        with patch.object(backfill, "query_target_damage") as query_damage:
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
                offline_only=True,
            )

        self.assertEqual(result["status"], "suspected")
        self.assertTrue(result["hidden_from_public"])
        self.assertIn("enemy_damage_outside_required_confirmed_total_range", result["reasons"])
        self.assertTrue(cache_hit)
        self.assertFalse(api_queried)
        query_damage.assert_not_called()

    def test_suzaku_low_player_total_uses_target_damage_and_becomes_valid(self) -> None:
        self.candidate.encounter_key = "unreal_suzaku"
        self.candidate.fight.update({
            "size": 8,
            "players": [
                {"total_damage": 8_856_012} for _ in range(5)
            ] + [
                {"total_damage": 8_856_011} for _ in range(3)
            ],
        })
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
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

        with (
            patch.object(
                backfill,
                "query_target_damage",
                return_value=([{"id": 10, "damage": 71_943_449, "instance_count": 1}], {10: 1}),
            ) as query_damage,
            patch.object(
                backfill,
                "query_target_max_hp",
                return_value={10: 127_613_543},
            ) as query_max_hp,
        ):
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-08-04T00:00:00Z",
                self.cache,
                refresh_cache=False,
            )

        self.assertEqual(result["status"], "valid")
        self.assertFalse(result["hidden_from_public"])
        self.assertFalse(cache_hit)
        self.assertTrue(api_queried)
        self.assertEqual(
            result["metrics"]["known_full_party_damage"]["damage_source"],
            "enemy_damage",
        )
        query_damage.assert_called_once()
        query_max_hp.assert_called_once()

    def test_enemy_damage_upper_limit_prevents_historical_valid_shortcut(self) -> None:
        self.candidate.encounter_key = "ultimate_futures_rewritten"
        self.candidate.fight["size"] = 8
        self.candidate.fight["players"] = [{"total_damage": 12_500} for _ in range(8)]
        self.config.historical_damage_baselines = baselines.HistoricalDamageBaselinePolicy(
            enabled=True,
            reference_cutoff_iso="2026-07-28T18:00:00+08:00",
            screening_multiplier=1.05,
            baselines={
                "ultimate_futures_rewritten": baselines.HistoricalDamageBaseline(
                    upper_reference_damage=100_100,
                    sample_count=500,
                    unique_fight_count=300,
                )
            },
        )
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "ultimate_futures_rewritten": known_capacity.KnownEnemyCapacityRule(
                    maximum_enemy_damage=100_100,
                )
            },
        )

        with patch.object(backfill, "query_target_damage") as query_damage:
            result, cache_hit, api_queried = backfill.evaluate_candidate(
                None,
                None,
                self.candidate,
                self.config,
                "2026-07-30T00:00:00Z",
                self.cache,
                refresh_cache=False,
                offline_only=True,
            )

        self.assertEqual(result["status"], "unverifiable")
        self.assertTrue(result["hidden_from_public"])
        self.assertFalse(cache_hit)
        self.assertFalse(api_queried)
        query_damage.assert_not_called()

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
        # 規則升版後仍應把既有最小量測值植入快取，讓全量回補不必重查 API。
        self.candidate.fight["data_integrity"]["calculation_version"] = 4

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

    def test_rule_classification_does_not_seed_unverifiable_cache(self) -> None:
        self.candidate.fight["data_integrity"] = {
            "calculation_version": 8,
            "status": "suspected",
            "hidden_from_public": True,
            "reasons": ["enemy_damage_outside_required_confirmed_total_range"],
        }

        seeded = backfill.seed_measurement_cache_from_results([self.candidate], self.cache)

        self.assertEqual(seeded, 0)
        self.assertIsNone(
            self.cache.get(self.candidate.report_code, self.candidate.report, self.candidate.fight)
        )

    def test_v8_valid_result_does_not_enter_v9_backfill_for_new_diagnostics(self) -> None:
        self.candidate.fight.update({
            "size": 8,
            "players": [{"total_damage": 12_500} for _ in range(8)],
            "data_integrity": {
                "calculation_version": 8,
                "status": "valid",
                "hidden_from_public": False,
            },
        })
        self.config.known_enemy_capacity = known_capacity.KnownEnemyCapacityPolicy(
            enabled=True,
            rules={
                "extreme_zelenia": known_capacity.KnownEnemyCapacityRule(
                    enemy_hp_capacity=100_000,
                    suspected_team_damage_ratio_threshold=1.005,
                    required_full_party_damage_min=99_900,
                    required_full_party_damage_max=100_100,
                )
            },
        )

        self.assertTrue(backfill.needs_known_capacity_recheck(self.candidate, self.config))
        self.assertFalse(backfill.candidate_needs_check(self.candidate, self.config))

    def test_v8_failed_result_enters_v9_backfill(self) -> None:
        self.candidate.fight["data_integrity"] = {
            "calculation_version": 8,
            "status": "suspected",
            "hidden_from_public": True,
        }

        self.assertTrue(backfill.candidate_needs_check(self.candidate, self.config))


if __name__ == "__main__":
    unittest.main()
