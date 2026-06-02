from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import backfill_gcd_coverage as gcd
import audit_xivanalysis_gcd_sample as audit_gcd


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

    def test_audit_apply_all_checked_updates_stale_stored_value_after_recompute_match(self) -> None:
        class FakeClient:
            def fetch_gcd_percent(self, candidate: gcd.GcdCandidate) -> tuple[float, str]:
                return 95.0, "ok"

        class FakeFallback:
            def calculate(self, candidate: gcd.GcdCandidate) -> dict[str, Any]:
                return {"percent": 95.02, "source": "fixture_recompute"}

        player = {
            "name": "測試玩家",
            "server": "測試伺服器",
            "job": "Samurai",
            "fflogs_id": 7,
            "dps": 1,
            "gcd_coverage": {
                "percent": 96.2,
                "calculation_version": gcd.GCD_CALCULATION_VERSION,
                "source": gcd.GCD_SOURCE,
            },
        }
        candidate = gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="REPORT",
            report={},
            fight={"fight_id": 1},
            player=player,
            sort_time=0,
        )

        result = audit_gcd.compare_candidate(
            FakeClient(),  # type: ignore[arg-type]
            candidate,
            checked_at_iso="1970-01-01T00:00:00Z",
            tolerance=0,
            apply=True,
            apply_all_checked=True,
            local_mode=audit_gcd.LOCAL_MODE_RECOMPUTE,
            local_fallback=FakeFallback(),  # type: ignore[arg-type]
        )

        self.assertEqual(result["state"], "matched")
        self.assertTrue(result["applied"])
        self.assertEqual(result["applied_reason"], "all_checked")
        self.assertEqual(result["stored_display_percent"], 96.2)
        self.assertEqual(result["stored_difference"], 1.2)
        self.assertEqual(player["gcd_coverage"]["percent"], 95.0)
        self.assertEqual(player["gcd_coverage"]["source"], audit_gcd.xiv_gcd.XIVANALYSIS_GCD_SOURCE)

    def test_zoraal_ja_sage_uses_casts_graph_for_xivanalysis_alignment(self) -> None:
        # 極佐拉加大多數職業需要 raw events 才能對齊 xivanalysis 的 packet 語意；
        # Sage 例外，固定 seed 稽核顯示 raw events 會多算 Eukrasia 系短 GCD lock。
        self.assertFalse(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_zoraal_ja", "Sage"))
        self.assertTrue(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_zoraal_ja", "Samurai"))

    def test_m1s_black_mage_prefers_raw_actions_with_graph_downtime(self) -> None:
        raw_coverage = {
            "percent": 95.2,
            "denominator_ms": 500000,
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }
        graph_downtime_coverage = {
            "percent": 94.7,
            "denominator_ms": 505000,
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }

        selected = gcd.gcd_core.select_savage_m1s_black_mage_coverage(
            raw_coverage,
            graph_downtime_coverage,
            encounter_key="savage_m1s",
            job="BlackMage",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.7)
        self.assertEqual(selected["fallback_selection"], "m1s_black_mage_raw_events_graph_downtime")
        self.assertEqual(selected["raw_events_percent"], 95.2)

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

    def test_calculation_matches_xivanalysis_downtime_endpoint_semantics(self) -> None:
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
        # xivanalysis 只在 GCD 覆蓋結束點落入 downtime 時裁切 covered time；
        # 3000ms 這個 GCD 橫跨 4000-5000ms downtime、但結束點已在 downtime 後，
        # 因此站端百分比只扣分母，不再把中間重疊段從分子扣一次。
        self.assertEqual(result["covered_time_ms"], 8500)
        self.assertEqual(result["gcd_cast_count"], 4)
        self.assertEqual(result["percent"], 94.44)

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
        self.assertFalse(overrides[34620].speed_adjusted)
        self.assertTrue(overrides[34620].status_speed_adjusted)
        self.assertIn(34620, gcd.gcd_core.RECAST_SUBSTAT_EXCLUDED_ACTION_IDS)
        self.assertEqual(overrides[16497].gcd_recast_ms, 2500)
        self.assertFalse(overrides[16497].speed_adjusted)
        self.assertEqual(overrides[7418].gcd_recast_ms, 2500)
        self.assertFalse(overrides[7418].speed_adjusted)
        self.assertEqual(overrides[34688].gcd_recast_ms, 6000)
        self.assertTrue(overrides[34688].speed_adjusted)
        self.assertEqual(overrides[34689].gcd_recast_ms, 4000)
        self.assertFalse(overrides[34689].speed_adjusted)
        self.assertEqual(overrides[36966].gcd_recast_ms, 2500)
        self.assertTrue(overrides[36966].speed_adjusted)
        self.assertEqual(overrides[4242].gcd_recast_ms, 8200)
        self.assertFalse(overrides[4242].speed_adjusted)
        self.assertEqual(overrides[36968].gcd_recast_ms, 3200)
        self.assertTrue(overrides[36968].speed_adjusted)

    def test_bard_army_windows_follow_xivanalysis_source_only_events(self) -> None:
        windows = gcd.gcd_core.raw_status_windows(
            [
                {"timestamp": 1000, "type": "applybuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 2},
                {"timestamp": 2000, "type": "refreshbuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 8},
                {"timestamp": 2300, "type": "removebuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 8},
                {"timestamp": 2600, "type": "refreshbuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 2},
                {"timestamp": 4000, "type": "removebuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 2},
            ],
            source_id=2,
            status_ids=gcd.gcd_core.BARD_ARMY_STATUS_IDS,
            fight_end_time=5000,
        )

        # xivanalysis 的 BRD AlwaysBeCasting hook 只篩 source 與 status，不篩 target。
        # 因此隊友身上的第一個 remove 會關掉 currentArmy，後續 refresh 再重新開窗。
        self.assertEqual(windows, [(1000, 2300), (2600, 4000)])

    def test_bard_army_windows_close_before_same_timestamp_reapply(self) -> None:
        windows = gcd.gcd_core.raw_status_windows(
            [
                {"timestamp": 1000, "type": "applybuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 8},
                {"timestamp": 4000, "type": "applybuff", "abilityGameID": 1001932, "sourceID": 2, "targetID": 2},
                {"timestamp": 4000, "type": "removebuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 8},
                {"timestamp": 7000, "type": "removebuff", "abilityGameID": 1001932, "sourceID": 2, "targetID": 2},
            ],
            source_id=2,
            status_ids=gcd.gcd_core.BARD_ARMY_STATUS_IDS,
            fight_end_time=8000,
        )

        # FFLogs raw events 有時把同一 timestamp 的 Muse apply 放在 Paeon remove 前。
        # xivanalysis 顯示結果等同先關舊 Army 視窗，再立刻開下一段 Army 視窗。
        self.assertEqual(windows, [(1000, 7000)])

    def test_bard_army_windows_require_matching_combatantinfo_aura_source(self) -> None:
        windows = gcd.gcd_core.raw_status_windows(
            [
                {
                    "timestamp": 500,
                    "type": "combatantinfo",
                    "sourceID": 8,
                    "auras": [
                        {"ability": 1002218, "source": 2},
                    ],
                },
                {
                    "timestamp": 1000,
                    "type": "combatantinfo",
                    "sourceID": 2,
                    "auras": [
                        {"ability": 1002218, "source": 99},
                        {"ability": 1001932, "source": 2},
                    ],
                },
                {"timestamp": 4000, "type": "removebuff", "abilityGameID": 1001932, "sourceID": 2, "targetID": 2},
            ],
            source_id=2,
            status_ids=gcd.gcd_core.BARD_ARMY_STATUS_IDS,
            fight_end_time=5000,
        )

        # xivanalysis 會把 combatantinfo aura 轉成 statusApply，但 source 取自 aura.source。
        # 因此隊友 combatantinfo 上由該 Bard 給出的 Army/Muse 也會開啟 ABC 排除窗。
        self.assertEqual(windows, [(500, 4000)])

    def test_fixed_recast_actions_do_not_use_passive_job_speed(self) -> None:
        metadata = gcd.ActionMetadata(
            action_id=36942,
            name="Forbidden Meditation",
            action_category_id=4,
            cast_ms=0,
            recast_ms=1000,
            gcd_recast_ms=1000,
            is_gcd_override=True,
            recast_speed_adjusted=False,
            recast_status_adjusted=True,
        )
        attempt = {"timestamp": 1000, "metadata": metadata}

        self.assertEqual(
            gcd.gcd_core.raw_recast_ms(
                attempt,
                speed_stats={"skill_speed": 786},
                job="Monk",
                speed_windows=[],
            ),
            1000,
        )
        self.assertEqual(
            gcd.gcd_core.raw_recast_ms(
                attempt,
                speed_stats={"skill_speed": 786},
                job="Samurai",
                speed_windows=[gcd.gcd_core.SpeedModifierWindow(0, 2000, 0.87, "Fuka")],
            ),
            870,
        )

    def test_pictomancer_rainbow_drip_uses_bright_or_prepull_proc_only(self) -> None:
        metadata = gcd.ActionMetadata(
            action_id=34688,
            name="Rainbow Drip",
            action_category_id=2,
            cast_ms=4000,
            recast_ms=6000,
            gcd_recast_ms=6000,
            is_gcd_override=True,
            recast_speed_adjusted=True,
            recast_status_adjusted=True,
        )

        def recast(timestamp: int, *, bright: bool = False, first: int | None = None) -> float:
            return gcd.gcd_core.raw_recast_ms(
                {"timestamp": timestamp, "cast_duration_ms": 0, "metadata": metadata},
                speed_stats={},
                job="Pictomancer",
                speed_windows=[],
                status_windows_by_status_id={3679: [(900, 1100)] if bright else []},
                first_gcd_timestamp=first,
            )

        self.assertEqual(recast(1000, bright=True), 2500)
        self.assertEqual(recast(1000, first=1000), 2500)
        self.assertEqual(recast(1000), 6000)

    def test_raw_event_downtime_source_preserves_player_unable_to_act_windows(self) -> None:
        raw_events = [
            {"timestamp": 1000, "type": "applydebuff", "targetID": 1, "abilityGameID": 783},
            {"timestamp": 8000, "type": "removedebuff", "targetID": 1, "abilityGameID": 783},
            {"timestamp": 20000, "type": "applydebuff", "targetID": 1, "abilityGameID": 783},
            {"timestamp": 28000, "type": "removedebuff", "targetID": 1, "abilityGameID": 783},
        ]

        source = gcd.gcd_core.raw_event_downtime_source(
            {"combatTime": 50_000, "downtime": []},
            raw_events,
            source_id=1,
            friendly_ids={1},
            fight_start_time=0,
            fight_end_time=50_000,
            unable_to_act_status_ids={783},
            job="Pictomancer",
        )

        self.assertEqual(
            source["downtime"],
            [
                {"startTime": 1000, "endTime": 8000, "statusID": 783, "source": "unable_to_act_status"},
                {"startTime": 20000, "endTime": 28000, "statusID": 783, "source": "unable_to_act_status"},
            ],
        )

    def test_raw_event_downtime_source_can_ignore_graph_downtime_for_targetability_only_jobs(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 5000, "sourceID": 99, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 9000, "sourceID": 99, "targetable": 1},
            {"timestamp": 12000, "type": "applydebuff", "targetID": 1, "abilityGameID": 783},
            {"timestamp": 15000, "type": "removedebuff", "targetID": 1, "abilityGameID": 783},
        ]

        source = gcd.gcd_core.raw_event_downtime_source(
            {"combatTime": 20_000, "downtime": [{"startTime": 1000, "endTime": 4000}]},
            raw_events,
            source_id=1,
            friendly_ids={1},
            fight_start_time=0,
            fight_end_time=20_000,
            unable_to_act_status_ids={783},
            job="BlackMage",
            include_graph_downtime=False,
        )

        self.assertEqual(
            source["downtime"],
            [{"startTime": 12000, "endTime": 15000, "statusID": 783, "source": "unable_to_act_status"}],
        )
        self.assertEqual(
            source["encounter_downtime"],
            [{"startTime": 5000, "endTime": 9000, "source": "all_foes_untargetable"}],
        )

    def test_raw_event_downtime_source_preserves_existing_encounter_gap_for_tanks(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 6000, "sourceID": 99, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 9000, "sourceID": 99, "targetable": 1},
        ]

        source = gcd.gcd_core.raw_event_downtime_source(
            {
                "combatTime": 20_000,
                "encounter_downtime": [{"startTime": 3000, "endTime": 9000, "source": "main_target_damage_gap"}],
            },
            raw_events,
            source_id=1,
            friendly_ids={1},
            fight_start_time=0,
            fight_end_time=20_000,
            unable_to_act_status_ids=set(),
            job="Warrior",
        )

        self.assertEqual(
            source["encounter_downtime"],
            [
                {"startTime": 3000, "endTime": 9000, "source": "main_target_damage_gap"},
                {"startTime": 6000, "endTime": 9000, "source": "all_foes_untargetable"},
            ],
        )

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
        # Casts graph 路徑對齊 xivanalysis，不用下一個 GCD timestamp 裁掉理論 recast；
        # 因此高覆蓋率樣本可以在分子略高於分母後由 percent 上限壓回 100%。
        self.assertEqual(result["covered_time_ms"], 13280)
        self.assertEqual(result["percent"], 100.0)

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
        self.assertEqual(result["percent"], 94.44)

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

    def test_raw_speed_status_windows_close_on_remove_before_refresh_duration(self) -> None:
        raw_events = [
            {"type": "applybuff", "timestamp": 1000, "sourceID": 10, "targetID": 10, "abilityGameID": 1000738, "duration": 5000},
            {"type": "refreshbuff", "timestamp": 3000, "sourceID": 10, "targetID": 10, "abilityGameID": 1000738, "duration": 5000},
            {"type": "removebuff", "timestamp": 4200, "sourceID": 10, "targetID": 10, "abilityGameID": 1000738},
        ]

        windows = gcd.gcd_core.raw_speed_modifier_windows(
            raw_events,
            source_id=10,
            fight_end_time=10_000,
        )

        self.assertEqual(
            windows,
            [
                gcd.gcd_core.SpeedModifierWindow(
                    start_ms=1000,
                    end_ms=4200,
                    modifier=0.85,
                    label="status 738",
                )
            ],
        )

    def test_raw_speed_initial_status_closes_on_remove(self) -> None:
        raw_events = [
            {
                "type": "combatantinfo",
                "timestamp": 0,
                "sourceID": 10,
                "auras": [{"ability": 1000738}],
            },
            {"type": "removebuff", "timestamp": 6000, "sourceID": 10, "targetID": 10, "abilityGameID": 1000738},
        ]

        windows = gcd.gcd_core.raw_speed_modifier_windows(
            raw_events,
            source_id=10,
            fight_end_time=60_000,
        )

        self.assertEqual(
            windows,
            [
                gcd.gcd_core.SpeedModifierWindow(
                    start_ms=0,
                    end_ms=6000,
                    modifier=0.85,
                    label="initial status 738",
                )
            ],
        )

    def test_raw_events_match_xivanalysis_black_mage_source_speed_lock(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                3577: gcd.ActionMetadata(
                    action_id=3577,
                    name="Fire IV",
                    action_category_id=2,
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
                "skillSpeed": 420,
                "spellSpeed": 756,
                "auras": [],
            },
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 3577},
            {"type": "cast", "timestamp": 2500, "sourceID": 10, "abilityGameID": 3577},
            {"type": "death", "timestamp": 1000, "targetID": 10},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="BlackMage",
            fight_end_time=5000,
            fallback_denominator_ms=5000,
            downtime_source={"combatTime": 5000, "downtime": [{"startTime": 900, "endTime": 1100}]},
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["speed_stat_source"], "combatantinfo_unadjusted_xivanalysis_raw_lock")
        self.assertEqual(result["covered_time_ms"], 5000)
        self.assertEqual(result["percent"], 100.0)

    def test_raw_events_black_mage_without_death_keeps_combatantinfo_speed(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                3577: gcd.ActionMetadata(
                    action_id=3577,
                    name="Fire IV",
                    action_category_id=2,
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
                "skillSpeed": 420,
                "spellSpeed": 756,
                "auras": [],
            },
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 3577},
            {"type": "cast", "timestamp": 2500, "sourceID": 10, "abilityGameID": 3577},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="BlackMage",
            fight_end_time=5000,
            fallback_denominator_ms=5000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["speed_stat_source"], "combatantinfo")
        self.assertEqual(result["covered_time_ms"], 4920)
        self.assertEqual(result["percent"], 98.4)

    def test_raw_events_black_mage_death_outside_downtime_keeps_combatantinfo_speed(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                3577: gcd.ActionMetadata(
                    action_id=3577,
                    name="Fire IV",
                    action_category_id=2,
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
                "skillSpeed": 420,
                "spellSpeed": 756,
                "auras": [],
            },
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 3577},
            {"type": "cast", "timestamp": 2500, "sourceID": 10, "abilityGameID": 3577},
            {"type": "death", "timestamp": 4000, "targetID": 10},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="BlackMage",
            fight_end_time=5000,
            fallback_denominator_ms=5000,
            downtime_source={"combatTime": 5000, "downtime": [{"startTime": 900, "endTime": 1100}]},
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["speed_stat_source"], "combatantinfo")
        self.assertEqual(result["covered_time_ms"], 4920)
        self.assertEqual(result["percent"], 100.0)

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

    def test_raw_events_preserve_xivanalysis_unclamped_estimated_speed(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Delayed Fixture Spell",
                    action_category_id=2,
                    cast_ms=1500,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "begincast", "timestamp": 0, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 1500, "sourceID": 10, "abilityGameID": 100},
            {"type": "begincast", "timestamp": 3000, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 4500, "sourceID": 10, "abilityGameID": 100},
        ]
        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(raw_events, metadata_store, source_id=10)  # type: ignore[arg-type]

        estimated = gcd.gcd_core.estimate_speed_stats_from_attempts(
            attempts,
            job="Scholar",
            speed_windows=[],
        )

        # xivanalysis 會把缺 combatantinfo 時反推出的副屬性原樣寫進 actorUpdate；
        # 若少量魔法 GCD 因戰鬥空窗被估到 2.50s 以上，站端也會留下低於遊戲下限的值。
        self.assertLess(estimated["spell_speed"], gcd.gcd_core.SUB_ATTRIBUTE_MINIMUM)

    def test_raw_events_speed_estimation_keeps_interrupted_cast_boundaries(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Interrupted Fixture Spell",
                    action_category_id=2,
                    cast_ms=1500,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "begincast", "timestamp": 0, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 1500, "sourceID": 10, "abilityGameID": 100},
            {"type": "begincast", "timestamp": 2500, "sourceID": 10, "abilityGameID": 100},
            {"type": "begincast", "timestamp": 5000, "sourceID": 10, "abilityGameID": 100},
            {"type": "cast", "timestamp": 6500, "sourceID": 10, "abilityGameID": 100},
        ]
        attempts = gcd.gcd_core.extract_gcd_speed_estimation_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        estimated = gcd.gcd_core.estimate_speed_stats_from_attempts(
            attempts,
            job="Scholar",
            speed_windows=[],
        )

        self.assertEqual(sum(1 for attempt in attempts if attempt.get("interrupted")), 1)
        self.assertEqual(estimated["spell_speed"], gcd.gcd_core.SUB_ATTRIBUTE_MINIMUM)

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

    def test_raw_events_can_cap_encounter_specific_jobs_at_next_gcd(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Gunbreaker Fixture GCD",
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
            job="Gunbreaker",
            fight_end_time=5000,
            fallback_denominator_ms=5000,
            cap_next_gcd_jobs=gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 4500)
        self.assertEqual(result["percent"], 90.0)

    def test_queen_dragoon_limit_break_combo_boundary_is_not_counted(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                36952: gcd.ActionMetadata(
                    action_id=36952,
                    name="Drakesbane",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                    recast_speed_adjusted=False,
                ),
                4242: gcd.ActionMetadata(
                    action_id=4242,
                    name="Dragonsong Dive",
                    action_category_id=3,
                    cast_ms=4500,
                    recast_ms=8200,
                    recast_speed_adjusted=False,
                ),
                16479: gcd.ActionMetadata(
                    action_id=16479,
                    name="Raiden Thrust",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                    recast_speed_adjusted=False,
                ),
            }
        )
        raw_events = [
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 36952},
            {"type": "begincast", "timestamp": 4000, "sourceID": 10, "abilityGameID": 4242, "duration": 4500},
            {"type": "cast", "timestamp": 8000, "sourceID": 10, "abilityGameID": 4242},
            {"type": "cast", "timestamp": 12000, "sourceID": 10, "abilityGameID": 16479},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            encounter_key="extreme_queen_eternal",
            source_id=10,
            job="Dragoon",
            fight_end_time=20000,
            fallback_denominator_ms=20000,
            cap_next_gcd_jobs=gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 5000)
        self.assertEqual(result["percent"], 25.0)

    def test_queen_dragoon_limit_break_before_drakesbane_still_counts_full_lock(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                3554: gcd.ActionMetadata(
                    action_id=3554,
                    name="Fang and Claw",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                    recast_speed_adjusted=False,
                ),
                4242: gcd.ActionMetadata(
                    action_id=4242,
                    name="Dragonsong Dive",
                    action_category_id=3,
                    cast_ms=4500,
                    recast_ms=8200,
                    recast_speed_adjusted=False,
                ),
                36952: gcd.ActionMetadata(
                    action_id=36952,
                    name="Drakesbane",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                    recast_speed_adjusted=False,
                ),
            }
        )
        raw_events = [
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 3554},
            {"type": "begincast", "timestamp": 4000, "sourceID": 10, "abilityGameID": 4242, "duration": 4500},
            {"type": "cast", "timestamp": 8000, "sourceID": 10, "abilityGameID": 4242},
            {"type": "cast", "timestamp": 12000, "sourceID": 10, "abilityGameID": 36952},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            encounter_key="extreme_queen_eternal",
            source_id=10,
            job="Dragoon",
            fight_end_time=20000,
            fallback_denominator_ms=20000,
            cap_next_gcd_jobs=gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 13200)
        self.assertEqual(result["percent"], 66.0)

    def test_raw_events_do_not_cap_queen_monk_at_next_gcd(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Monk Fixture GCD",
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
            job="Monk",
            fight_end_time=5000,
            fallback_denominator_ms=5000,
            cap_next_gcd_jobs=gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 5000)
        self.assertEqual(result["percent"], 100.0)

    def test_queen_uses_targetability_only_downtime_for_verified_jobs(self) -> None:
        for job in ("BlackMage", "Dancer", "Gunbreaker", "Monk", "Pictomancer", "Samurai", "Scholar"):
            self.assertTrue(
                gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                    "extreme_queen_eternal",
                    job,
                ),
                msg=f"{job} 應使用 Queen 專屬 targetability-only downtime。",
            )
        self.assertFalse(
            gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                "extreme_queen_eternal",
                "Paladin",
            )
        )

    def test_queen_gunbreaker_uses_targetability_downtime_and_next_gcd_cap(self) -> None:
        self.assertTrue(
            gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                "extreme_queen_eternal",
                "Gunbreaker",
            )
        )
        self.assertIn(
            "Gunbreaker",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )
        self.assertIn(
            "Machinist",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )
        self.assertNotIn(
            "Paladin",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )
        self.assertNotIn(
            "Dragoon",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )

    def test_valigarmanda_uses_raw_events_for_verified_downtime_gaps(self) -> None:
        # 極瓦利加爾曼達的 Casts graph 會漏掉短暫 targetability / UnableToAct downtime。
        # 100 場外站頁面稽核顯示 AST 也應回到 raw events；舊 graph 例外會低估
        # 低覆蓋率樣本的可用分母。
        for job in (
            "BlackMage",
            "Dancer",
            "WhiteMage",
            "Reaper",
            "Samurai",
            "Viper",
            "Dragoon",
            "Sage",
            "DarkKnight",
            "Monk",
            "Astrologian",
        ):
            self.assertTrue(
                gcd.gcd_core.should_use_raw_events_for_gcd(
                    "extreme_valigarmanda",
                    job,
                ),
                msg=f"{job} 應在 Valigarmanda 使用 raw events GCD 計算。",
            )

    def test_valigarmanda_keeps_verified_graph_jobs_and_uncapped_monk_viper_raw_events(self) -> None:
        # MNK/VPR raw lock 不應裁到下一個 GCD；xivanalysis legacy 事件流會累加這些
        # 高速轉化窗口，裁切反而會低估 ABC。
        self.assertNotIn(
            "Viper",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_valigarmanda"),
        )
        self.assertNotIn(
            "Monk",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_valigarmanda"),
        )

    def test_zoraal_ja_and_savage_use_raw_events_for_verified_gcd_lock_gaps(self) -> None:
        # 極佐拉加與 AAC 零式的 Casts graph 會高估部分 SAM/PCT/VPR 的 GCD lock；
        # xivanalysis 頁面使用 raw FFLogs 事件語意，抽樣差異在 raw events 路徑會回到容許值內。
        for encounter_key in ("extreme_zoraal_ja", "savage_m1s", "savage_m2s", "savage_m3s", "savage_m4s"):
            for job in ("Samurai", "Pictomancer", "Viper"):
                self.assertTrue(
                    gcd.gcd_core.should_use_raw_events_for_gcd(
                        encounter_key,
                        job,
                    ),
                    msg=f"{encounter_key} 的 {job} 應使用 raw events GCD 計算。",
                )
            self.assertNotIn(
                "Monk",
                gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(encounter_key),
                msg=f"{encounter_key} 的 Monk raw events 不應裁到下一個 GCD。",
            )
            self.assertNotIn(
                "Viper",
                gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(encounter_key),
                msg=f"{encounter_key} 的 Viper raw events 不應裁到下一個 GCD。",
            )

    def test_queen_red_mage_uses_raw_events_with_selector(self) -> None:
        # Queen 的 RedMage 需要先計算 raw events 才能判斷是否為低覆蓋率 graph undercount；
        # selector 預設仍會保守回 graph，避免 Dualcast / instant GCD 被 raw events 吃過滿。
        self.assertTrue(
            gcd.gcd_core.should_use_raw_events_for_gcd(
                "extreme_queen_eternal",
                "RedMage",
            )
        )
        self.assertTrue(
            gcd.gcd_core.should_use_raw_events_for_gcd("unreal_byakko", "RedMage")
        )

    def test_savage_black_mage_graph_exceptions_and_m2s_white_mage_raw_events(self) -> None:
        for encounter_key in ("savage_m2s", "savage_m3s", "savage_m4s"):
            self.assertFalse(
                gcd.gcd_core.should_use_raw_events_for_gcd(
                    encounter_key,
                    "BlackMage",
                ),
                msg=f"{encounter_key} 的 BlackMage 應回到 Casts graph 對齊頁面值。",
            )
        self.assertTrue(
            gcd.gcd_core.should_use_raw_events_for_gcd(
                "savage_m2s",
                "WhiteMage",
            )
        )

    def test_raw_events_do_not_cap_ninja_mudra_overlap_at_next_gcd(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                2259: gcd.ActionMetadata(
                    action_id=2259,
                    name="Ten",
                    action_category_id=None,
                    cast_ms=0,
                    recast_ms=0,
                    gcd_recast_ms=500,
                    is_gcd_override=True,
                    recast_speed_adjusted=False,
                )
            }
        )
        raw_events = [
            {"type": "cast", "timestamp": 0, "sourceID": 10, "abilityGameID": 2259},
            {"type": "cast", "timestamp": 300, "sourceID": 10, "abilityGameID": 2259},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="Ninja",
            fight_end_time=2000,
            fallback_denominator_ms=2000,
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 1000)
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

    def test_pct_byakko_selector_uses_graph_gap_only_for_small_positive_delta(self) -> None:
        raw = {"percent": 70.35, "denominator_ms": 529727}
        graph_gap = {"percent": 71.26, "denominator_ms": 504002}

        selected = gcd.gcd_core.select_pct_byakko_downtime_coverage(raw, graph_gap)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 71.26)
        self.assertEqual(selected["downtime_selection"], "casts_graph_encounter_gap")
        self.assertEqual(selected["raw_targetability_percent"], 70.35)

    def test_pct_byakko_selector_keeps_raw_when_graph_gap_is_too_wide(self) -> None:
        raw = {"percent": 79.42, "denominator_ms": 574270}
        graph_gap = {"percent": 81.93, "denominator_ms": 547566}

        selected = gcd.gcd_core.select_pct_byakko_downtime_coverage(raw, graph_gap)

        self.assertIs(selected, raw)

    def test_pct_byakko_selector_keeps_raw_for_mid_uptime_graph_gap(self) -> None:
        raw = {"percent": 74.97, "denominator_ms": 552109}
        graph_gap = {"percent": 75.82, "denominator_ms": 525511}

        selected = gcd.gcd_core.select_pct_byakko_downtime_coverage(raw, graph_gap)

        self.assertIs(selected, raw)

    def test_blm_byakko_selector_uses_graph_when_raw_events_underestimate_badly(self) -> None:
        raw = {"percent": 81.40, "denominator_ms": 475085}
        graph = {"percent": 94.96, "denominator_ms": 456381}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.96)
        self.assertEqual(selected["fallback_selection"], "black_mage_casts_graph_large_raw_gap")
        self.assertEqual(selected["raw_events_percent"], 81.40)

    def test_blm_byakko_selector_prefers_graph_with_raw_downtime_when_available(self) -> None:
        raw = {"percent": 80.42, "denominator_ms": 494255}
        graph = {"percent": 90.92, "denominator_ms": 475964}
        raw_downtime_graph = {"percent": 92.17, "denominator_ms": 494255}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph, raw_downtime_graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.17)
        self.assertEqual(selected["fallback_selection"], "black_mage_casts_graph_raw_downtime_large_raw_gap")
        self.assertEqual(selected["raw_events_percent"], 80.42)
        self.assertEqual(selected["casts_graph_percent"], 90.92)

    def test_blm_byakko_selector_uses_graph_raw_downtime_for_moderate_raw_overcount(self) -> None:
        raw = {"percent": 88.77, "denominator_ms": 542071}
        graph = {"percent": 86.12, "denominator_ms": 523386}
        raw_downtime_graph = {"percent": 87.46, "denominator_ms": 542071}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph, raw_downtime_graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.46)
        self.assertEqual(
            selected["fallback_selection"],
            "black_mage_casts_graph_raw_downtime_moderate_raw_overcount",
        )
        self.assertEqual(selected["raw_events_percent"], 88.77)

    def test_blm_byakko_selector_keeps_raw_for_normal_small_gaps(self) -> None:
        raw = {"percent": 84.35, "denominator_ms": 555346}
        graph = {"percent": 83.99, "denominator_ms": 537158}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

        self.assertIs(selected, raw)

    def test_tank_byakko_selector_uses_main_target_gap_only_for_large_positive_delta(self) -> None:
        raw = {"percent": 95.04, "denominator_ms": 482477}
        main_gap = {"percent": 96.74, "denominator_ms": 478940}

        selected = gcd.gcd_core.select_tank_byakko_coverage(raw, main_gap)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.74)
        self.assertEqual(selected["fallback_selection"], "tank_main_target_damage_gap")
        self.assertEqual(selected["raw_targetability_percent"], 95.04)

    def test_tank_byakko_selector_keeps_raw_for_small_gap(self) -> None:
        raw = {"percent": 91.83, "denominator_ms": 500000}
        main_gap = {"percent": 92.57, "denominator_ms": 496000}

        selected = gcd.gcd_core.select_tank_byakko_coverage(raw, main_gap)

        self.assertIs(selected, raw)

    def test_tank_byakko_selector_keeps_raw_for_mid_uptime_large_gap(self) -> None:
        raw = {"percent": 80.91, "denominator_ms": 478123}
        main_gap = {"percent": 82.24, "denominator_ms": 480960}

        selected = gcd.gcd_core.select_tank_byakko_coverage(raw, main_gap)

        self.assertIs(selected, raw)

    def test_tank_byakko_selector_keeps_high_raw_with_unclamped_estimated_speed(self) -> None:
        raw = {"percent": 96.55, "denominator_ms": 482477, "estimated_speed_below_minimum": True}
        main_gap = {"percent": 98.29, "denominator_ms": 478940}

        selected = gcd.gcd_core.select_tank_byakko_coverage(raw, main_gap)

        self.assertIs(selected, raw)

    def test_tank_byakko_selector_uses_paladin_graph_for_estimated_speed_gap(self) -> None:
        raw = {"percent": 96.3, "denominator_ms": 534595, "estimated_speed_below_minimum": True}
        main_gap = {"percent": 96.1, "denominator_ms": 534595}
        graph = {"percent": 95.3, "denominator_ms": 534595}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.3)
        self.assertEqual(selected["fallback_selection"], "paladin_byakko_casts_graph_estimated_speed_gap")
        self.assertEqual(selected["raw_targetability_percent"], 96.3)

    def test_tank_byakko_selector_keeps_non_paladin_high_raw_with_graph_gap(self) -> None:
        raw = {"percent": 95.64, "denominator_ms": 534595, "estimated_speed_below_minimum": True}
        main_gap = {"percent": 95.2, "denominator_ms": 534595}
        graph = {"percent": 94.55, "denominator_ms": 534595}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="DarkKnight",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_red_mage_selector_uses_graph_for_low_uptime_raw_gap(self) -> None:
        raw = {"percent": 69.28, "denominator_ms": 518612}
        graph = {"percent": 67.62, "denominator_ms": 520577}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 67.62)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_red_mage_casts_graph_low_uptime")
        self.assertEqual(selected["raw_events_percent"], 69.28)

    def test_valigarmanda_red_mage_selector_keeps_raw_for_high_uptime(self) -> None:
        raw = {"percent": 80.26, "denominator_ms": 517575}
        graph = {"percent": 78.13, "denominator_ms": 529348}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_white_mage_selector_uses_graph_for_low_uptime_raw_overcount(self) -> None:
        raw = {"percent": 56.85, "denominator_ms": 544100}
        graph = {"percent": 55.12, "denominator_ms": 551031}

        selected = gcd.gcd_core.select_valigarmanda_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 55.12)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_white_mage_casts_graph_low_uptime")
        self.assertEqual(selected["raw_events_percent"], 56.85)

    def test_valigarmanda_white_mage_selector_keeps_raw_for_small_gap(self) -> None:
        raw = {"percent": 57.44, "denominator_ms": 544100}
        graph = {"percent": 57.19, "denominator_ms": 551031}

        selected = gcd.gcd_core.select_valigarmanda_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_queen_red_mage_selector_uses_raw_for_low_graph_uptime(self) -> None:
        raw = {"percent": 86.04, "denominator_ms": 539728}
        graph = {"percent": 84.22, "denominator_ms": 551749}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.04)
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_raw_events_low_graph_uptime")
        self.assertEqual(selected["casts_graph_percent"], 84.22)

    def test_queen_red_mage_selector_uses_raw_for_mid_graph_uptime(self) -> None:
        raw = {"percent": 90.92, "denominator_ms": 518194}
        graph = {"percent": 88.85, "denominator_ms": 530225}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.92)
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_raw_events_low_graph_uptime")
        self.assertEqual(selected["casts_graph_percent"], 88.85)

    def test_queen_red_mage_selector_keeps_graph_when_raw_gap_is_not_verified(self) -> None:
        raw = {"percent": 93.5, "denominator_ms": 539728}
        graph = {"percent": 90.2, "denominator_ms": 551749}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, graph)

    def test_queen_scholar_selector_uses_graph_for_intermission_gap(self) -> None:
        raw = {"percent": 88.01, "denominator_ms": 551059}
        graph = {"percent": 90.48, "denominator_ms": 530225}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.48)
        self.assertEqual(selected["fallback_selection"], "queen_scholar_casts_graph_intermission_gap")
        self.assertEqual(selected["raw_events_percent"], 88.01)

    def test_queen_scholar_selector_keeps_raw_for_small_graph_gap(self) -> None:
        raw = {"percent": 90.24, "denominator_ms": 551059}
        graph = {"percent": 90.81, "denominator_ms": 530225}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_uses_graph_for_high_uptime_low_estimated_speed(self) -> None:
        raw = {"percent": 98.04, "denominator_ms": 422129, "estimated_speed_below_minimum": True}
        graph = {"percent": 100.0, "denominator_ms": 630742}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m3s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 100.0)
        self.assertEqual(selected["fallback_selection"], "bard_casts_graph_high_uptime_estimated_speed")

    def test_bard_selector_blends_without_low_estimated_speed_instead_of_graph_jump(self) -> None:
        raw = {"percent": 98.49, "denominator_ms": 282847}
        graph = {"percent": 100.0, "denominator_ms": 414286}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.82)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_with_casts_graph_lock_blend")

    def test_bard_selector_keeps_low_estimated_speed_raw_when_not_high_uptime(self) -> None:
        raw = {"percent": 87.97, "denominator_ms": 479527, "estimated_speed_below_minimum": True}
        graph = {"percent": 92.59, "denominator_ms": 656736}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m4s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.97)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_low_estimated_speed_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 92.59)

    def test_bard_selector_blends_raw_and_graph_lock_for_aac_samples(self) -> None:
        raw = {"percent": 93.26, "denominator_ms": 412170, "covered_time_ms": 384400}
        graph = {"percent": 99.35, "denominator_ms": 603476}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m2s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.6)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_with_casts_graph_lock_blend")

    def test_bard_selector_keeps_low_uptime_raw_instead_of_blending_graph(self) -> None:
        raw = {"percent": 63.74, "denominator_ms": 484199, "covered_time_ms": 308600}
        graph = {"percent": 69.54, "denominator_ms": 656950}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_uses_m1s_specific_blend_ratio(self) -> None:
        raw = {"percent": 91.86, "denominator_ms": 389838, "covered_time_ms": 358088}
        graph = {"percent": 96.94, "denominator_ms": 549888}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m1s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.38)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_with_casts_graph_lock_blend")

    def test_bard_selector_uses_valigarmanda_graph_for_small_gap(self) -> None:
        raw = {"percent": 86.28, "denominator_ms": 290269}
        graph = {"percent": 86.79, "denominator_ms": 460713}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.79)
        self.assertEqual(selected["fallback_selection"], "bard_casts_graph_valigarmanda_small_raw_gap")
        self.assertEqual(selected["raw_events_percent"], 86.28)

    def test_bard_selector_uses_byakko_graph_for_combatantinfo_high_uptime(self) -> None:
        raw = {
            "percent": 99.02,
            "denominator_ms": 362902,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 100.0, "denominator_ms": 362902}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 100.0)
        self.assertEqual(selected["fallback_selection"], "bard_casts_graph_byakko_high_uptime")
        self.assertEqual(selected["raw_events_percent"], 99.02)

    def test_bard_selector_keeps_byakko_mid_uptime_raw(self) -> None:
        raw = {
            "percent": 95.92,
            "denominator_ms": 404716,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 98.21, "denominator_ms": 404716}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIs(selected, raw)

    def test_byakko_red_mage_selector_uses_graph_for_raw_overcount(self) -> None:
        raw = {"percent": 71.66, "denominator_ms": 562808}
        graph = {"percent": 70.61, "denominator_ms": 544269}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 70.61)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_casts_graph_raw_overcount")
        self.assertEqual(selected["raw_targetability_percent"], 71.66)

    def test_byakko_red_mage_selector_keeps_high_uptime_raw(self) -> None:
        raw = {"percent": 84.54, "denominator_ms": 562808}
        graph = {"percent": 83.54, "denominator_ms": 544269}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.54)
        self.assertNotIn("fallback_selection", selected)

    def test_byakko_red_mage_selector_blends_estimated_speed_mid_gap(self) -> None:
        raw = {
            "percent": 82.02,
            "denominator_ms": 573831,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 80.43, "denominator_ms": 544269}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.22)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_raw_graph_estimated_speed_blend")
        self.assertEqual(selected["raw_targetability_percent"], 82.02)
        self.assertEqual(selected["casts_graph_percent"], 80.43)

    def test_valigarmanda_summoner_selector_uses_graph_for_estimated_speed_gap(self) -> None:
        raw = {
            "percent": 91.16,
            "denominator_ms": 589950,
            "covered_time_ms": 537825,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 89.98, "denominator_ms": 591607}

        selected = gcd.gcd_core.select_valigarmanda_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.98)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_summoner_casts_graph_estimated_speed_gap",
        )
        self.assertEqual(selected["raw_events_percent"], 91.16)

    def test_valigarmanda_black_mage_selector_uses_graph_for_small_raw_overcount(self) -> None:
        raw = {"percent": 92.99, "denominator_ms": 445248}
        graph = {"percent": 92.41, "denominator_ms": 446532}

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.41)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_black_mage_casts_graph_raw_overcount",
        )
        self.assertEqual(selected["raw_events_percent"], 92.99)

    def test_bard_selector_uses_queen_graph_for_high_uptime(self) -> None:
        raw = {"percent": 98.48, "denominator_ms": 383646}
        graph = {"percent": 100.0, "denominator_ms": 555084}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 100.0)
        self.assertEqual(selected["fallback_selection"], "bard_casts_graph_queen_high_uptime")
        self.assertEqual(selected["raw_events_percent"], 98.48)

    def test_bard_selector_keeps_queen_raw_when_not_high_uptime(self) -> None:
        raw = {"percent": 91.24, "denominator_ms": 383646}
        graph = {"percent": 100.0, "denominator_ms": 555084}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_adjusts_valigarmanda_low_uptime_small_gap(self) -> None:
        raw = {"percent": 81.92, "denominator_ms": 299059, "covered_time_ms": 245000}
        graph = {"percent": 82.19, "denominator_ms": 466566}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.17)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_low_uptime_army_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 82.19)

    def test_bard_selector_keeps_valigarmanda_raw_for_large_graph_jump(self) -> None:
        raw = {"percent": 78.25, "denominator_ms": 290269}
        graph = {"percent": 85.88, "denominator_ms": 460713}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_tank_byakko_selector_keeps_mid_high_raw_with_unclamped_estimated_speed(self) -> None:
        # 3T8bytG1vCwkpajf fight=7 的 DarkKnight 樣本：xivanalysis 保留 raw
        # targetability + UTA 的 95.2% 顯示值；若切到 main-target damage gap 會高估到 96.6%。
        raw = {"percent": 95.28, "denominator_ms": 493173, "estimated_speed_below_minimum": True}
        main_gap = {"percent": 96.57, "denominator_ms": 496117}

        selected = gcd.gcd_core.select_tank_byakko_coverage(raw, main_gap)

        self.assertIs(selected, raw)


if __name__ == "__main__":
    unittest.main()
