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

    def test_parse_args_supports_report_limit_env_and_cli_override(self) -> None:
        with (
            patch.dict(gcd.os.environ, {"FFLOGS_GCD_BACKFILL_REPORT_LIMIT": "200"}),
            patch.object(gcd.sys, "argv", ["backfill_gcd_coverage.py", "--report-limit", "50"]),
        ):
            args = gcd.parse_args()

        self.assertEqual(args.report_limit, 50)

    def test_select_candidates_can_limit_by_report_code(self) -> None:
        def make_candidate(report_code: str, sort_time: int, player_name: str) -> gcd.GcdCandidate:
            return gcd.GcdCandidate(
                encounter_key="fixture",
                encounter={},
                ranking={},
                report_code=report_code,
                report={},
                fight={"fight_id": sort_time},
                player={"name": player_name},
                sort_time=sort_time,
            )

        candidates = [
            make_candidate("NEW", 300, "新報告第一位"),
            make_candidate("MID", 200, "中間報告"),
            make_candidate("OLD", 100, "舊報告"),
            make_candidate("NEW", 90, "新報告第二位"),
        ]

        selected = gcd.select_candidates(candidates, player_limit=1, report_limit=1)

        self.assertEqual([candidate.player["name"] for candidate in selected], ["新報告第一位", "新報告第二位"])
        self.assertEqual(gcd.selected_report_count(selected), 1)

    def test_select_candidates_keeps_player_limit_when_report_limit_is_disabled(self) -> None:
        candidates = [
            gcd.GcdCandidate("fixture", {}, {}, "A", {}, {}, {"name": "一"}, 30),
            gcd.GcdCandidate("fixture", {}, {}, "B", {}, {}, {"name": "二"}, 20),
            gcd.GcdCandidate("fixture", {}, {}, "C", {}, {}, {"name": "三"}, 10),
        ]

        selected = gcd.select_candidates(candidates, player_limit=2, report_limit=0)

        self.assertEqual([candidate.report_code for candidate in selected], ["A", "B"])

    def test_stateful_report_window_uses_existing_cursor_before_now(self) -> None:
        state = {
            gcd.GCD_REPORT_BACKFILL_STATE_KEY: {
                "cutoff_sort_time": 5000,
                "cursor_sort_time": 2000,
                "cursor_report_code": "CURSOR",
            }
        }

        cutoff, cursor, report_code, initialized = gcd.resolve_stateful_report_window(
            state,
            explicit_cutoff=None,
            now_ms=8000,
        )

        self.assertEqual(cutoff, 5000)
        self.assertEqual(cursor, 2000)
        self.assertEqual(report_code, "CURSOR")
        self.assertFalse(initialized)

    def test_stateful_report_window_initializes_from_now(self) -> None:
        cutoff, cursor, report_code, initialized = gcd.resolve_stateful_report_window(
            {},
            explicit_cutoff=None,
            now_ms=3000,
        )

        self.assertEqual(cutoff, 3000)
        self.assertEqual(cursor, 3000)
        self.assertIsNone(report_code)
        self.assertTrue(initialized)

    def test_stateful_report_window_allows_explicit_override(self) -> None:
        state = {
            gcd.GCD_REPORT_BACKFILL_STATE_KEY: {
                "cutoff_sort_time": 1000,
                "cursor_sort_time": 900,
                "cursor_report_code": "OLD",
            }
        }

        cutoff, cursor, report_code, initialized = gcd.resolve_stateful_report_window(
            state,
            explicit_cutoff="1970-01-01T00:00:02Z",
            now_ms=3000,
        )

        self.assertEqual(cutoff, 2000)
        self.assertEqual(cursor, 2000)
        self.assertIsNone(report_code)
        self.assertTrue(initialized)

    def test_filter_candidates_before_cursor_excludes_newer_reports(self) -> None:
        candidates = [
            gcd.GcdCandidate("fixture", {}, {}, "NEW", {}, {}, {"name": "new"}, 3000),
            gcd.GcdCandidate("fixture", {}, {}, "OLD", {}, {}, {"name": "old"}, 1000),
        ]

        filtered = gcd.filter_candidates_before_cursor(candidates, 2000)

        self.assertEqual([candidate.report_code for candidate in filtered], ["OLD"])

    def test_filter_candidates_before_cursor_uses_report_code_tie_breaker(self) -> None:
        candidates = [
            gcd.GcdCandidate("fixture", {}, {}, "Z", {}, {}, {"name": "cursor"}, 3000),
            gcd.GcdCandidate("fixture", {}, {}, "A", {}, {}, {"name": "same-time-older"}, 3000),
            gcd.GcdCandidate("fixture", {}, {}, "OLD", {}, {}, {"name": "old"}, 1000),
        ]

        filtered = gcd.filter_candidates_before_cursor(candidates, 3000, "Z")

        self.assertEqual([candidate.report_code for candidate in filtered], ["A", "OLD"])

    def test_filter_candidates_before_cursor_keeps_retry_reports(self) -> None:
        candidates = [
            gcd.GcdCandidate("fixture", {}, {}, "RETRY", {}, {}, {"name": "retry"}, 4000),
            gcd.GcdCandidate("fixture", {}, {}, "OLD", {}, {}, {"name": "old"}, 1000),
        ]

        filtered = gcd.filter_candidates_before_cursor(
            candidates,
            2000,
            retry_report_codes={"RETRY"},
        )

        self.assertEqual([candidate.report_code for candidate in filtered], ["RETRY", "OLD"])

    def test_update_stateful_report_backfill_state_moves_cursor_to_oldest_selected_report(self) -> None:
        state = {}
        selected = [
            gcd.GcdCandidate("fixture", {}, {}, "NEW", {}, {}, {"name": "new"}, 3000),
            gcd.GcdCandidate("fixture", {}, {}, "OLD", {}, {}, {"name": "old"}, 1000),
        ]

        gcd.update_stateful_report_backfill_state(
            state,
            cutoff_ms=5000,
            initialized=True,
            candidate_count=2,
            selected=selected,
            updated=1,
            marked_null=0,
            failed=1,
            checked_at_iso="1970-01-01T00:00:05.000Z",
            failed_report_codes={"OLD"},
            completed_report_codes={"NEW"},
        )

        node = state[gcd.GCD_REPORT_BACKFILL_STATE_KEY]
        self.assertEqual(node["cutoff_sort_time"], 5000)
        self.assertEqual(node["cursor_sort_time"], 1000)
        self.assertEqual(node["cursor_report_code"], "OLD")
        self.assertEqual(node["retry_report_codes"], ["OLD"])

    def test_update_stateful_report_backfill_state_resets_stale_cursor_when_reinitialized(self) -> None:
        state = {
            gcd.GCD_REPORT_BACKFILL_STATE_KEY: {
                "cutoff_sort_time": 1000,
                "cursor_sort_time": 500,
                "cursor_report_code": "STALE",
            }
        }

        gcd.update_stateful_report_backfill_state(
            state,
            cutoff_ms=3000,
            initialized=True,
            candidate_count=0,
            selected=[],
            updated=0,
            marked_null=0,
            failed=0,
            checked_at_iso="1970-01-01T00:00:03.000Z",
        )

        node = state[gcd.GCD_REPORT_BACKFILL_STATE_KEY]
        self.assertEqual(node["cutoff_sort_time"], 3000)
        self.assertEqual(node["cursor_sort_time"], 3000)
        self.assertNotIn("cursor_report_code", node)

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

    def test_samurai_cast_packet_does_not_shorten_gcd_recast(self) -> None:
        metadata = gcd.ActionMetadata(
            action_id=7487,
            name="Midare Setsugekka",
            action_category_id=3,
            cast_ms=1800,
            recast_ms=2500,
        )
        attempt = {
            "timestamp": 0,
            "cast_duration_ms": 1300,
            "metadata": metadata,
        }
        timing = gcd.gcd_core.RecastTimingEstimate(
            multiplier_by_base={2500: 0.86},
            dominant_speed_modifier_by_base={2500: 1.0},
        )

        recast = gcd.gcd_core.adjusted_recast_ms(
            attempt,
            0.86,
            timing,
            job="Samurai",
            speed_windows=[],
        )

        # 武士居合的 FFLogs cast duration 會比遊戲內 GCD lock 短；若用 1300/1800
        # 比例縮短 recast，Always Be Casting 會系統性低估武士覆蓋率。
        self.assertEqual(recast, 2150)

    def test_xivanalysis_like_action_overrides_cover_job_specific_gcd_locks(self) -> None:
        overrides = gcd.gcd_core.GCD_ACTION_OVERRIDES

        self.assertEqual(overrides[24290].gcd_recast_ms, 1000)
        self.assertFalse(overrides[24290].speed_adjusted)
        self.assertEqual(overrides[36978].gcd_recast_ms, 1500)
        self.assertFalse(overrides[36978].speed_adjusted)
        self.assertEqual(overrides[36984].gcd_recast_ms, 2500)
        self.assertTrue(overrides[36984].speed_adjusted)
        self.assertEqual(overrides[15999].gcd_recast_ms, 1000)
        self.assertFalse(overrides[15999].speed_adjusted)
        self.assertEqual(overrides[16196].gcd_recast_ms, 1500)
        self.assertFalse(overrides[16196].speed_adjusted)
        self.assertEqual(overrides[34620].gcd_recast_ms, 3000)
        self.assertTrue(overrides[34620].speed_adjusted)
        self.assertIn(34620, gcd.gcd_core.RECAST_SUBSTAT_EXCLUDED_ACTION_IDS)
        self.assertEqual(overrides[4242].gcd_recast_ms, 8200)
        self.assertFalse(overrides[4242].speed_adjusted)
        self.assertEqual(overrides[36968].gcd_recast_ms, 3200)
        self.assertTrue(overrides[36968].speed_adjusted)

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

    def test_denominator_only_downtime_does_not_remove_player_activity(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="測試用 GCD",
                    action_category_id=2,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        graph = {
            "combatTime": 10000,
            "denominator_downtime": [{"startTime": 4000, "endTime": 5000}],
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
        self.assertEqual(result["covered_time_ms"], 8500)
        self.assertEqual(result["downtime_ms"], 1000)
        self.assertEqual(result["coverage_downtime_ms"], 0)
        self.assertEqual(result["denominator_downtime_ms"], 1000)
        self.assertEqual(result["percent"], 94.44)

    def test_infers_main_target_downtime_from_damage_gaps(self) -> None:
        events = [
            {"timestamp": 0, "targetID": 11},
            {"timestamp": 1000, "targetID": 11},
            {"timestamp": 2000, "targetID": 11},
            {"timestamp": 3000, "targetID": 17},
            {"timestamp": 4000, "targetID": 17},
            {"timestamp": 20000, "targetID": 11},
            {"timestamp": 21000, "targetID": 11},
        ]

        windows = gcd.gcd_core.infer_main_target_damage_downtime_windows(
            events,
            min_gap_ms=10_000,
            min_event_share=0.50,
        )

        self.assertEqual(
            windows,
            [{"startTime": 2000, "endTime": 20000, "targetID": 11, "source": "main_target_damage_gap"}],
        )

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

    def test_raw_events_use_combatantinfo_speed_and_status_windows(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Raw Fixture GCD",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {
                "type": "combatantinfo",
                "timestamp": 0,
                "sourceID": 10,
                "skillSpeed": 582,
                "spellSpeed": 420,
                "auras": [],
            },
            {"type": "applybuff", "timestamp": 1000, "sourceID": 10, "targetID": 10, "abilityGameID": 1001299, "duration": 4000},
            {"type": "cast", "timestamp": 1000, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 4000, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 7000, "sourceID": 10, "abilityGameID": 100},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="Samurai",
            fight_end_time=10000,
            fallback_denominator_ms=10000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["source"], gcd.gcd_core.GCD_SOURCE_RAW_EVENTS)
        self.assertEqual(result["speed_stat_source"], "combatantinfo")
        self.assertEqual(result["gcd_cast_count"], 3)
        self.assertEqual(result["covered_time_ms"], 7110)
        self.assertEqual(result["percent"], 71.1)

    def test_raw_events_infer_unable_to_act_status_windows(self) -> None:
        raw_events = [
            {"type": "applydebuff", "timestamp": 1000, "targetID": 10, "abilityGameID": 1000783},
            {"type": "refreshdebuff", "timestamp": 1500, "targetID": 10, "abilityGameID": 1000783},
            {"type": "removedebuff", "timestamp": 3000, "targetID": 10, "abilityGameID": 1000783},
            {"type": "applybuff", "timestamp": 3500, "targetID": 11, "abilityGameID": 1001513},
            {"type": "applydebuff", "timestamp": 4000, "targetID": 10, "abilityGameID": 1001513},
        ]

        windows = gcd.gcd_core.infer_unable_to_act_windows(
            raw_events,
            source_id=10,
            unable_to_act_status_ids={783, 1513},
            fight_end_time=5000,
        )

        self.assertEqual(
            windows,
            [
                {"startTime": 1000, "endTime": 3000, "statusID": 783, "source": "unable_to_act_status"},
                {"startTime": 4000, "endTime": 5000, "statusID": 1513, "source": "unable_to_act_status"},
            ],
        )

    def test_raw_events_infer_all_foes_untargetable_after_midfight_add_leaves(self) -> None:
        raw_events = [
            {"type": "damage", "timestamp": 250, "sourceID": 10, "targetID": 99, "abilityGameID": 100},
            {"type": "targetabilityupdate", "timestamp": 500, "sourceID": 17, "targetable": 1},
            {"type": "targetabilityupdate", "timestamp": 1000, "sourceID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 1500, "sourceID": 17, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 3000, "sourceID": 11, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(windows, [{"startTime": 1500, "endTime": 3000, "source": "all_foes_untargetable"}])

    def test_raw_events_use_xivanalysis_tendo_kaeshi_recast_override(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                36968: gcd.ActionMetadata(
                    action_id=36968,
                    name="Tendo Kaeshi Setsugekka",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                    gcd_recast_ms=3200,
                )
            }
        )
        raw_events = [
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 36968},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="Samurai",
            fight_end_time=4000,
            fallback_denominator_ms=4000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 3200)
        self.assertEqual(result["percent"], 80.0)

    def test_raw_events_infer_recast_when_combatantinfo_has_no_speed_stats(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Raw Fixture GCD",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "combatantinfo", "timestamp": 0, "sourceID": 10, "auras": []},
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 2400, "sourceID": 10, "abilityGameID": 100},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            fight_end_time=10000,
            fallback_denominator_ms=10000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 4820)
        self.assertEqual(result["percent"], 48.2)

    def test_raw_events_cap_viper_overlap_at_next_gcd(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Viper Fixture GCD",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                    recast_speed_adjusted=False,
                )
            }
        )
        raw_events = [
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 2000, "sourceID": 10, "abilityGameID": 100},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="Viper",
            fight_end_time=5000,
            fallback_denominator_ms=5000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 4500)
        self.assertEqual(result["percent"], 90.0)

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
