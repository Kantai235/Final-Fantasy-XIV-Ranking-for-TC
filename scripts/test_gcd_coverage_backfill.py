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


def make_cast_group(timestamp: int, action_id: int) -> list[dict[str, Any]]:
    return [
        {
            "timestamp": timestamp,
            "type": "cast",
            "ability": {"guid": action_id},
        }
    ]


class GcdCoverageBackfillTest(unittest.TestCase):
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
                                    "name": "已完成角色",
                                    "server": "利維坦",
                                    "job": "Samurai",
                                    "dps": 80,
                                    "fflogs_id": 12,
                                    "gcd_coverage": {"percent": 99.0},
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
                candidates, missing_count, null_count, rankings_by_key = gcd.scan_candidates({"fixture": encounter})

        self.assertEqual(missing_count, 1)
        self.assertEqual(null_count, 1)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].player["name"], "待補角色")
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
