from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import backfill_gcd_coverage as gcd


class FakeMetadataStore:
    def __init__(self, metadata_by_id: dict[int, gcd.ActionMetadata]) -> None:
        self.metadata_by_id = metadata_by_id

    def get(self, action_id: int) -> gcd.ActionMetadata | None:
        return self.metadata_by_id.get(action_id)


def make_cast_group(timestamp: int, action_id: int, source_id: int | None = None) -> list[dict[str, Any]]:
    event: dict[str, Any] = {
        "timestamp": timestamp,
        "type": "cast",
        "ability": {"guid": action_id},
    }
    if source_id is not None:
        event["sourceID"] = source_id
    return [event]


class GcdCoverageBackfillTest(unittest.TestCase):
    def test_parse_args_treats_empty_env_limit_as_default(self) -> None:
        with (
            patch.dict(gcd.os.environ, {"FFLOGS_GCD_BACKFILL_LIMIT": ""}),
            patch.object(gcd.sys, "argv", ["backfill_gcd_coverage.py"]),
        ):
            args = gcd.parse_args()

        self.assertEqual(args.limit, gcd.DEFAULT_GCD_BACKFILL_LIMIT)

    def test_parse_args_allows_cli_limit_when_env_limit_is_empty(self) -> None:
        with (
            patch.dict(gcd.os.environ, {"FFLOGS_GCD_BACKFILL_LIMIT": ""}),
            patch.object(gcd.sys, "argv", ["backfill_gcd_coverage.py", "--limit", "37"]),
        ):
            args = gcd.parse_args()

        self.assertEqual(args.limit, 37)

    def test_calculation_subtracts_downtime_from_denominator_and_covered_time(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="測試 GCD",
                    action_category_id=2,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        graph = {
            "combatTime": 10000,
            "downtime": [{"startTime": 4000, "endTime": 5000}],
            "series": [
                {
                    "guid": 100,
                    "events": [
                        make_cast_group(0, 100),
                        make_cast_group(3000, 100),
                        make_cast_group(6000, 100),
                        make_cast_group(9000, 100),
                    ],
                }
            ],
        }

        result = gcd.calculate_gcd_coverage_from_graph(
            graph,
            metadata_store,  # type: ignore[arg-type]
            fight_end_time=10000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["denominator_ms"], 9000)
        self.assertEqual(result["downtime_ms"], 1000)
        self.assertEqual(result["covered_time_ms"], 7500)
        self.assertEqual(result["gcd_cast_count"], 4)
        self.assertEqual(result["percent"], 83.33)

    def test_recast_estimate_uses_xivanalysis_style_interval_batches(self) -> None:
        metadata = gcd.ActionMetadata(
            action_id=100,
            name="測試 GCD",
            action_category_id=2,
            cast_ms=0,
            recast_ms=2500,
        )
        timestamp = 0
        attempts: list[dict[str, Any]] = []
        for delta in [2400, 2404, 2410, 2420, 2450, 2450, 2450, 2450, 3000]:
            attempts.append({"timestamp": timestamp, "metadata": metadata})
            timestamp += delta
        attempts.append({"timestamp": timestamp, "metadata": metadata})

        multipliers = gcd.infer_recast_multiplier_by_base(attempts)

        # xivanalysis 會把 FFLogs 約 45ms 的 timestamp 批次分桶，再取眾數附近的加權平均。
        # 這比直接取分位數更接近它在 Always Be Casting 使用的 GCD recast 估算。
        self.assertEqual(multipliers[2500], 0.972)

    def test_speed_status_does_not_leak_to_pre_buff_gcds(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                34607: gcd.ActionMetadata(
                    action_id=34607,
                    name="Reaving Fangs",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                ),
                34609: gcd.ActionMetadata(
                    action_id=34609,
                    name="Swiftskin's Sting",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                ),
            }
        )
        graph = {
            "combatTime": 12950,
            "series": [
                {
                    "guid": 34607,
                    "events": [
                        make_cast_group(0, 34607),
                        make_cast_group(4590, 34607),
                        make_cast_group(6680, 34607),
                        make_cast_group(8770, 34607),
                        make_cast_group(10860, 34607),
                    ],
                },
                {"guid": 34609, "events": [make_cast_group(2500, 34609)]},
            ],
        }

        result = gcd.calculate_gcd_coverage_from_graph(
            graph,
            metadata_store,  # type: ignore[arg-type]
            job="Viper",
            fight_end_time=12950,
        )

        self.assertIsNotNone(result)
        assert result is not None
        # 後續樣本的主流 recast 是 2.09s，但開場尚未有 Swiftscaled，第一個 GCD 應還原成約 2.46s。
        self.assertEqual(result["covered_time_ms"], 12910)
        self.assertEqual(result["percent"], 99.69)

    def test_fallback_denominator_also_subtracts_downtime(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="測試 GCD",
                    action_category_id=2,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        graph = {
            "downtime": [{"startTime": 4000, "endTime": 5000}],
            "series": [
                {
                    "guid": 100,
                    "events": [
                        make_cast_group(0, 100),
                        make_cast_group(3000, 100),
                        make_cast_group(6000, 100),
                        make_cast_group(9000, 100),
                    ],
                }
            ],
        }

        result = gcd.calculate_gcd_coverage_from_graph(
            graph,
            metadata_store,  # type: ignore[arg-type]
            fight_end_time=10000,
            fallback_denominator_ms=10000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["denominator_ms"], 9000)
        self.assertEqual(result["downtime_ms"], 1000)
        self.assertEqual(result["percent"], 83.33)

    def test_ninja_ability_overrides_count_as_gcd_locks(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                2259: gcd.ActionMetadata(
                    action_id=2259,
                    name="Ten",
                    action_category_id=4,
                    cast_ms=0,
                    recast_ms=20000,
                    gcd_recast_ms=500,
                    is_gcd_override=True,
                    recast_speed_adjusted=False,
                ),
                2267: gcd.ActionMetadata(
                    action_id=2267,
                    name="Raiton",
                    action_category_id=4,
                    cast_ms=0,
                    recast_ms=1500,
                    gcd_recast_ms=1500,
                    is_gcd_override=True,
                    recast_speed_adjusted=False,
                ),
            }
        )
        graph = {
            "combatTime": 3000,
            "series": [
                {"guid": 2259, "events": [make_cast_group(0, 2259)]},
                {"guid": 2267, "events": [make_cast_group(500, 2267)]},
            ],
        }

        result = gcd.calculate_gcd_coverage_from_graph(
            graph,
            metadata_store,  # type: ignore[arg-type]
            fight_end_time=3000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["gcd_cast_count"], 2)
        self.assertEqual(result["covered_time_ms"], 2000)
        self.assertEqual(result["percent"], 66.67)

    def test_gcd_recast_override_prevents_long_cooldown_overcount(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                34620: gcd.ActionMetadata(
                    action_id=34620,
                    name="Vicewinder",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=40000,
                    gcd_recast_ms=3000,
                    is_gcd_override=True,
                    recast_speed_adjusted=False,
                )
            }
        )
        graph = {
            "combatTime": 10000,
            "series": [
                {
                    "guid": 34620,
                    "events": [
                        make_cast_group(0, 34620),
                        make_cast_group(6000, 34620),
                    ],
                }
            ],
        }

        result = gcd.calculate_gcd_coverage_from_graph(
            graph,
            metadata_store,  # type: ignore[arg-type]
            fight_end_time=10000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["gcd_cast_count"], 2)
        self.assertEqual(result["covered_time_ms"], 6000)
        self.assertEqual(result["percent"], 60.0)

    def test_whole_fight_casts_graph_filters_attempts_by_source_id(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Fixture GCD",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        graph = {
            "combatTime": 10000,
            "series": [
                {
                    "guid": 10,
                    "events": [
                        make_cast_group(0, 100, source_id=10),
                        make_cast_group(5000, 100, source_id=10),
                    ],
                },
                {
                    "guid": 11,
                    "events": [
                        make_cast_group(2500, 100, source_id=11),
                        make_cast_group(7500, 100, source_id=11),
                    ],
                },
            ],
        }

        result = gcd.calculate_gcd_coverage_from_graph(
            graph,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            fight_end_time=10000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["gcd_cast_count"], 2)
        self.assertEqual(result["covered_time_ms"], 5000)
        self.assertEqual(result["percent"], 50.0)

    def test_scan_candidates_counts_missing_and_null_gcd_keys(self) -> None:
        encounter = {"key": "fixture", "name": "測試副本", "zone_id": 1, "encounter_id": 2, "difficulty": 100}
        ranking = {
            "reports": {
                "ABC": {
                    "report_code": "ABC",
                    "report_start_time": 100000,
                    "fights": [
                        {
                            "fight_id": 1,
                            "start_time": 0,
                            "end_time": 10000,
                            "players": [
                                {
                                    "name": "待補角色",
                                    "server": "巴哈姆特",
                                    "job": "Paladin",
                                    "dps": 100,
                                    "fflogs_id": 10,
                                },
                                {
                                    "name": "無法存取角色",
                                    "server": "鳳凰",
                                    "job": "WhiteMage",
                                    "dps": 90,
                                    "fflogs_id": 11,
                                    "gcd_coverage": None,
                                },
                                {
                                    "name": "舊版角色",
                                    "server": "利維坦",
                                    "job": "Samurai",
                                    "dps": 80,
                                    "fflogs_id": 12,
                                    "gcd_coverage": {"percent": 99.0, "calculation_version": 1},
                                },
                                {
                                    "name": "新版角色",
                                    "server": "莫古力",
                                    "job": "BlackMage",
                                    "dps": 70,
                                    "fflogs_id": 13,
                                    "gcd_coverage": {
                                        "percent": 98.0,
                                        "calculation_version": gcd.GCD_CALCULATION_VERSION,
                                    },
                                },
                            ],
                        }
                    ],
                }
            }
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "fixture.json"
            marker.write_text("{}", encoding="utf-8")
            with (
                patch.object(gcd, "ranking_path", return_value=marker),
                patch.object(gcd, "load_ranking_file", return_value=ranking),
            ):
                candidates, missing_count, stale_count, null_count, rankings_by_key = gcd.scan_candidates(
                    {"fixture": encounter}
                )
                all_candidates, *_ = gcd.scan_candidates({"fixture": encounter}, include_current=True)

        self.assertEqual(missing_count, 1)
        self.assertEqual(stale_count, 1)
        self.assertEqual(null_count, 1)
        self.assertEqual(len(candidates), 2)
        self.assertEqual(len(all_candidates), 3)
        self.assertEqual({candidate.player["name"] for candidate in candidates}, {"待補角色", "舊版角色"})
        self.assertIs(rankings_by_key["fixture"], ranking)

    def test_mark_unavailable_writes_null_key_and_status(self) -> None:
        player: dict[str, Any] = {"name": "測試角色"}
        candidate = gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="ABC",
            report={},
            fight={},
            player=player,
            sort_time=0,
        )

        gcd.mark_candidate_unavailable(candidate, "private_or_deleted", "2026-01-01T00:00:00+00:00")

        self.assertIn("gcd_coverage", player)
        self.assertIsNone(player["gcd_coverage"])
        self.assertEqual(player["gcd_coverage_status"]["state"], "unavailable")
        self.assertEqual(player["gcd_coverage_status"]["reason"], "private_or_deleted")


if __name__ == "__main__":
    unittest.main()
