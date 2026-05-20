from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import check_missing_gcd_report_status as checker


class MissingGcdReportStatusTest(unittest.TestCase):
    def test_scan_candidates_selects_reports_with_missing_or_null_gcd(self) -> None:
        encounters = {
            "fixture_a": {"key": "fixture_a", "name": "測試副本 A", "zone_id": 1, "encounter_id": 2, "difficulty": 100},
            "fixture_b": {"key": "fixture_b", "name": "測試副本 B", "zone_id": 1, "encounter_id": 3, "difficulty": 100},
        }
        rankings: dict[str, dict[str, Any]] = {
            "fixture_a": {
                "reports": {
                    "ABC": {
                        "report_code": "ABC",
                        "report_start_time": 3000,
                        "fights": [
                            {
                                "fight_id": 1,
                                "players": [
                                    {"name": "缺資料角色"},
                                    {"name": "已有 null 角色", "gcd_coverage": None},
                                ],
                            }
                        ],
                    },
                    "HIDDEN": {
                        "report_hidden": True,
                        "fights": [{"fight_id": 1, "players": [{"name": "已隱藏角色"}]}],
                    },
                }
            },
            "fixture_b": {
                "reports": {
                    "ABC": {
                        "report_code": "ABC",
                        "report_start_time": 4000,
                        "fights": [{"fight_id": 2, "players": [{"name": "另一副本缺資料"}]}],
                    },
                    "OK": {
                        "report_code": "OK",
                        "fights": [{"fight_id": 1, "players": [{"name": "已完成角色", "gcd_coverage": {"percent": 99}}]}],
                    },
                }
            },
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            marker = Path(temp_dir) / "fixture.json"
            marker.write_text("{}", encoding="utf-8")

            def fake_load_ranking(encounter: dict[str, Any]) -> dict[str, Any]:
                return rankings[encounter["key"]]

            with (
                patch.object(checker, "ranking_path", return_value=marker),
                patch.object(checker, "load_ranking_file", fake_load_ranking),
            ):
                candidates, missing_players, rankings_by_key = checker.scan_missing_gcd_report_candidates(encounters)

        self.assertEqual(missing_players, 3)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].report_code, "ABC")
        self.assertEqual(candidates[0].encounter_keys, {"fixture_a", "fixture_b"})
        self.assertEqual(candidates[0].missing_player_count, 3)
        self.assertIs(rankings_by_key["fixture_a"], rankings["fixture_a"])

    def test_mark_report_hidden_across_rankings_updates_every_matching_report(self) -> None:
        rankings = {
            "fixture_a": {"reports": {"ABC": {"report_code": "ABC"}}},
            "fixture_b": {"reports": {"ABC": {"report_code": "ABC"}, "OTHER": {"report_code": "OTHER"}}},
        }

        changed = checker.mark_report_hidden_across_rankings(
            "ABC",
            rankings,
            RuntimeError("permission to view this report"),
        )

        self.assertEqual(changed, {"fixture_a", "fixture_b"})
        self.assertTrue(rankings["fixture_a"]["reports"]["ABC"]["report_hidden"])
        self.assertTrue(rankings["fixture_b"]["reports"]["ABC"]["report_hidden"])
        self.assertNotIn("report_hidden", rankings["fixture_b"]["reports"]["OTHER"])


if __name__ == "__main__":
    unittest.main()
