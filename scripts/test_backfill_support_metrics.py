from __future__ import annotations

import unittest

import backfill_missing_fflogs_data as backfill
from fflogs_pipeline import support_metrics


def 建立已完成支援統計的戰鬥() -> dict:
    return {
        "fight_id": 1,
        "start_time": 1_000,
        "support_metrics_summary": {
            "calculation_version": support_metrics.支援統計計算版本,
            "mitigation_rules_version": support_metrics.坦克減傷規則版本,
        },
        "players": [
            {
                "name": "補師",
                "server": "巴哈姆特",
                "job": "WhiteMage",
                "fflogs_id": 1,
                "healing_stats": {"calculation_version": support_metrics.支援統計計算版本},
            },
            {
                "name": "坦克",
                "server": "巴哈姆特",
                "job": "Paladin",
                "fflogs_id": 2,
                "tank_stats": {
                    "calculation_version": support_metrics.支援統計計算版本,
                    "mitigation_coverage": {
                        "rules_version": support_metrics.坦克減傷規則版本,
                    },
                },
            },
        ],
    }


class SupportMetricsBackfillTests(unittest.TestCase):
    def test_parse_iso_timestamp_uses_explicit_utc(self) -> None:
        self.assertEqual(
            backfill.parse_iso_timestamp("2026-07-28T05:00:00Z"),
            backfill.parse_iso_timestamp("2026-07-28T05:00:00+00:00"),
        )

    def test_current_support_metrics_require_fight_and_player_versions(self) -> None:
        fight = 建立已完成支援統計的戰鬥()
        self.assertTrue(backfill.support_metrics_are_current(fight))

        fight["players"][0].pop("healing_stats")
        self.assertFalse(backfill.support_metrics_are_current(fight))

    def test_support_backfill_window_accepts_report_relative_start_time(self) -> None:
        cutoff = backfill.parse_iso_timestamp("2026-07-28T05:00:00Z")
        report = {"report_start_time": cutoff, "fights": []}
        fight = 建立已完成支援統計的戰鬥()
        fight.pop("support_metrics_summary")

        self.assertTrue(backfill.fight_needs_support_metrics(report, fight, cutoff, cutoff + 2_000))
        self.assertFalse(backfill.fight_needs_support_metrics(report, fight, cutoff + 2_000, cutoff + 3_000))

    def test_report_support_mode_only_counts_fights_in_window(self) -> None:
        cutoff = backfill.parse_iso_timestamp("2026-07-28T05:00:00Z")
        missing = 建立已完成支援統計的戰鬥()
        missing.pop("support_metrics_summary")
        current = 建立已完成支援統計的戰鬥()
        current["fight_id"] = 2
        current["start_time"] = 2_000
        old = 建立已完成支援統計的戰鬥()
        old["fight_id"] = 3
        old["recorded_at"] = cutoff - 1
        report = {"report_start_time": cutoff, "fights": [missing, current, old]}

        needs_backfill, count = backfill.report_needs_backfill(
            report,
            support_metrics_since_ms=cutoff,
            support_metrics_until_ms=cutoff + 3_000,
        )

        self.assertTrue(needs_backfill)
        self.assertEqual(count, 1)

    def test_existing_fight_players_rebuild_tc_actor_summary(self) -> None:
        report = {
            "fights": [
                {
                    "players": [
                        {
                            "name": "測試角色",
                            "server": "巴哈姆特",
                            "job": "Paladin",
                            "fflogs_id": 17,
                            "fflogs_guid": 99,
                        }
                    ]
                }
            ]
        }
        candidate = backfill.BackfillCandidate(
            report_code="ABC",
            reports_by_key={"fixture": report},
        )

        players = backfill.get_existing_matched_players(candidate)

        self.assertEqual(players[0]["name"], "測試角色")
        self.assertEqual(players[0]["server"], "巴哈姆特")
        self.assertEqual(players[0]["subType"], "Paladin")

    def test_stateful_cursor_starts_at_fixed_cutoff_and_moves_backward(self) -> None:
        cutoff = int(backfill.parse_iso_timestamp("2026-07-28T05:00:00Z"))
        cursor, report_code, initialized, retries = backfill.resolve_support_metrics_backfill_state({}, cutoff)

        self.assertEqual(cursor, cutoff)
        self.assertIsNone(report_code)
        self.assertTrue(initialized)
        self.assertEqual(retries, set())

        older = backfill.BackfillCandidate(report_code="OLDER", sort_time=cutoff - 2_000)
        boundary = backfill.BackfillCandidate(report_code="BOUNDARY", sort_time=cutoff)
        filtered = backfill.filter_support_candidates_before_cursor(
            [boundary, older],
            cutoff,
            None,
            set(),
        )

        self.assertEqual([candidate.report_code for candidate in filtered], ["OLDER"])

    def test_stateful_status_records_versions_cursor_and_retries(self) -> None:
        cutoff = int(backfill.parse_iso_timestamp("2026-07-28T05:00:00Z"))
        selected = [
            backfill.BackfillCandidate(report_code="NEWER", sort_time=cutoff - 1_000),
            backfill.BackfillCandidate(report_code="OLDER", sort_time=cutoff - 2_000),
        ]
        state: dict = {}

        backfill.update_support_metrics_backfill_state(
            state,
            cutoff_ms=cutoff,
            initialized=True,
            candidate_count=2,
            selected=selected,
            updated_reports=1,
            skipped_inaccessible=0,
            failed_report_codes={"NEWER"},
            completed_report_codes={"OLDER"},
        )

        node = state[backfill.SUPPORT_METRICS_REPORT_BACKFILL_STATE_KEY]
        self.assertEqual(node["cursor_report_code"], "OLDER")
        self.assertEqual(node["cursor_sort_time"], cutoff - 2_000)
        self.assertEqual(node["retry_report_codes"], ["NEWER"])
        self.assertEqual(node["calculation_version"], support_metrics.支援統計計算版本)
        self.assertEqual(node["mitigation_rules_version"], support_metrics.坦克減傷規則版本)


if __name__ == "__main__":
    unittest.main()
