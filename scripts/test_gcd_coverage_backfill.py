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

    def test_recast_timing_estimate_uses_gcd_start_for_hard_cast_intervals(self) -> None:
        metadata = gcd.ActionMetadata(
            action_id=7511,
            name="Verstone",
            action_category_id=2,
            cast_ms=2000,
            recast_ms=2500,
            recast_speed_adjusted=True,
        )
        attempts = [
            {
                "action_id": 7511,
                "timestamp": 2470,
                "cast_start_timestamp": 1000,
                "cast_duration_ms": 2000,
                "metadata": metadata,
            },
            {
                "action_id": 7511,
                "timestamp": 4970,
                "cast_start_timestamp": 3500,
                "cast_duration_ms": 2000,
                "metadata": metadata,
            },
        ]

        timing = gcd.gcd_core.infer_recast_timing_by_base(attempts)

        self.assertIn(2500, timing.multiplier_by_base)
        self.assertAlmostEqual(timing.multiplier_by_base[2500], 1.0)

    def test_gcd_pull_duration_prefers_fflogs_combat_time_for_abc_denominator(self) -> None:
        fight = {"combatTime": 9200, "clear_time_ms": 9000, "damage_time_ms": 8500}

        duration = gcd.gcd_pull_duration_ms(fight, 1000, 11000)
        pull_start = gcd.gcd_core.gcd_pull_start_time_ms(fight, 1000, 11000)

        self.assertEqual(duration, 9200.0)
        self.assertEqual(pull_start, 1800.0)

    def test_gcd_pull_duration_uses_clear_time_before_raw_timestamp_span(self) -> None:
        fight = {"clear_time_ms": 9000, "damage_time_ms": 8500}

        duration = gcd.gcd_pull_duration_ms(fight, 1000, 11000)

        self.assertEqual(duration, 9000.0)

    def test_gcd_pull_duration_falls_back_to_existing_fields_when_timestamps_missing(self) -> None:
        fight = {"clear_time_ms": 9000, "damage_time_ms": 8500}

        duration = gcd.gcd_pull_duration_ms(fight, None, None)

        self.assertEqual(duration, 9000.0)

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
            audit_cache=None,
            refresh_cache=False,
            cache_only=False,
        )

        self.assertEqual(result["state"], "matched")
        self.assertTrue(result["applied"])
        self.assertEqual(result["applied_reason"], "all_checked")
        self.assertEqual(result["stored_display_percent"], 96.2)
        self.assertEqual(result["stored_difference"], 1.2)
        self.assertEqual(player["gcd_coverage"]["percent"], 95.0)
        self.assertEqual(player["gcd_coverage"]["source"], audit_gcd.xiv_gcd.XIVANALYSIS_GCD_SOURCE)

    def test_audit_compare_uses_cached_xivanalysis_result_without_client_fetch(self) -> None:
        class FailingClient:
            def fetch_gcd_percent(self, candidate: gcd.GcdCandidate) -> tuple[float, str]:
                raise AssertionError("不應在 cache hit 時重新讀取 xivanalysis 頁面。")

        player = {
            "name": "快取玩家",
            "server": "測試伺服器",
            "job": "Samurai",
            "fflogs_id": 7,
            "gcd_coverage": {
                "percent": 90.0,
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
            fight={"fight_id": 1, "start_time": 1000, "end_time": 9000},
            player=player,
            sort_time=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit_cache = audit_gcd.xiv_gcd.GcdAuditCache(Path(temp_dir))
            audit_cache.write_xivanalysis_result(
                candidate,
                percent=91.2,
                url="https://xivanalysis.example/cached",
            )

            result = audit_gcd.compare_candidate(
                FailingClient(),  # type: ignore[arg-type]
                candidate,
                checked_at_iso="1970-01-01T00:00:00Z",
                tolerance=0,
                apply=False,
                apply_all_checked=False,
                local_mode=audit_gcd.LOCAL_MODE_STORED,
                local_fallback=None,
                audit_cache=audit_cache,
                refresh_cache=False,
                cache_only=False,
            )

        self.assertEqual(result["xivanalysis_cache"], "hit")
        self.assertEqual(result["xivanalysis_percent"], 91.2)
        self.assertEqual(result["xivanalysis_url"], "https://xivanalysis.example/cached")

    def test_audit_compare_cache_only_reports_missing_xivanalysis_cache(self) -> None:
        player = {
            "name": "缺快取",
            "server": "測試伺服器",
            "job": "Samurai",
            "fflogs_id": 7,
            "gcd_coverage": {
                "percent": 90.0,
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
            fight={"fight_id": 1, "start_time": 1000, "end_time": 9000},
            player=player,
            sort_time=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            result = audit_gcd.compare_candidate(
                None,
                candidate,
                checked_at_iso="1970-01-01T00:00:00Z",
                tolerance=0,
                apply=False,
                apply_all_checked=False,
                local_mode=audit_gcd.LOCAL_MODE_STORED,
                local_fallback=None,
                audit_cache=audit_gcd.xiv_gcd.GcdAuditCache(Path(temp_dir)),
                refresh_cache=False,
                cache_only=True,
            )

        self.assertEqual(result["state"], "error")
        self.assertIn("快取缺漏", result["error"])

    def test_audit_cache_round_trips_fflogs_payload(self) -> None:
        candidate = gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="REPORT",
            report={},
            fight={"fight_id": 1, "start_time": 1000, "end_time": 9000},
            player={"name": "測試", "server": "測試伺服器", "job": "Samurai", "fflogs_id": 7},
            sort_time=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit_cache = audit_gcd.xiv_gcd.GcdAuditCache(Path(temp_dir))
            audit_cache.write_fflogs_payload("casts_graph", candidate, {"combatTime": 8000})

            cached = audit_cache.read_fflogs_payload("casts_graph", candidate)

        self.assertEqual(cached, {"combatTime": 8000})

    def test_audit_cache_merges_xivanalysis_proxy_events(self) -> None:
        candidate = gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="REPORT",
            report={},
            fight={"fight_id": 1, "start_time": 1000, "end_time": 9000},
            player={"name": "測試", "server": "測試伺服器", "job": "BlackMage", "fflogs_id": 7},
            sort_time=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit_cache = audit_gcd.xiv_gcd.GcdAuditCache(Path(temp_dir))
            audit_cache.merge_xivanalysis_proxy_events(
                candidate,
                {
                    "events": [
                        {"timestamp": 3000, "type": "cast", "sourceID": 7, "ability": {"guid": 3577}},
                        {"timestamp": 2000, "type": "applybuff", "targetID": 7, "ability": {"guid": 1000738}},
                    ],
                    "nextPageTimestamp": 4000,
                },
                url="https://xivanalysis.example/proxy/fflogs/report/events/REPORT?start=1000",
            )
            audit_cache.merge_xivanalysis_proxy_events(
                candidate,
                {
                    "events": [
                        {"timestamp": 3000, "type": "cast", "sourceID": 7, "ability": {"guid": 3577}},
                        {"timestamp": 5000, "type": "removebuff", "targetID": 7, "ability": {"guid": 1000738}},
                    ]
                },
                url="https://xivanalysis.example/proxy/fflogs/report/events/REPORT?start=4000",
            )

            cached = audit_cache.read_fflogs_payload("xivanalysis_proxy_events", candidate)

        self.assertIsInstance(cached, dict)
        assert isinstance(cached, dict)
        self.assertEqual(cached["source"], "xivanalysis_proxy_fflogs_v1")
        self.assertEqual([event["timestamp"] for event in cached["events"]], [2000, 3000, 5000])
        self.assertEqual(len(cached["pages"]), 2)
        self.assertEqual(cached["pages"][0]["next_page_timestamp"], 4000)

    def test_event_status_id_reads_legacy_fflogs_ability_guid(self) -> None:
        event = {"type": "applybuff", "ability": {"guid": 1000738}}

        self.assertEqual(gcd.gcd_core.event_status_id(event), 738)

    def test_audit_cache_reads_report_fight_metadata_for_local_recompute(self) -> None:
        candidate = gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="REPORT",
            report={},
            fight={"fight_id": 343, "start_time": 1000, "end_time": 11000},
            player={"name": "測試", "server": "測試伺服器", "job": "BlackMage", "fflogs_id": 7},
            sort_time=0,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            audit_cache = audit_gcd.xiv_gcd.GcdAuditCache(Path(temp_dir))
            audit_cache.write_fflogs_payload(
                "report_fights",
                candidate,
                {
                    "data": {
                        "fights": [
                            {"id": 1, "combatTime": 1000},
                            {
                                "id": 343,
                                "combatTime": 9200,
                                "phases": [{"id": 1, "startTime": 1000}],
                            },
                        ]
                    }
                },
            )

            cached_fight = audit_cache.read_report_fight(candidate)
            fallback = audit_gcd.xiv_gcd.LocalGcdFallback(audit_cache=audit_cache)
            calculation_fight = fallback._calculation_fight(candidate)

        self.assertIsNotNone(cached_fight)
        assert cached_fight is not None
        self.assertEqual(cached_fight["combatTime"], 9200)
        self.assertEqual(calculation_fight["combatTime"], 9200)
        self.assertEqual(calculation_fight["phases"], [{"id": 1, "startTime": 1000}])
        self.assertNotIn("combatTime", candidate.fight)

    def test_audit_player_sample_selects_players_per_encounter_job(self) -> None:
        def make_candidate(job: str, report_code: str, source_id: int) -> gcd.GcdCandidate:
            return gcd.GcdCandidate(
                encounter_key="fixture",
                encounter={"name": "測試副本", "category": "極"},
                ranking={},
                report_code=report_code,
                report={},
                fight={"fight_id": 1},
                player={
                    "name": f"{job}{source_id}",
                    "server": "測試伺服器",
                    "job": job,
                    "fflogs_id": source_id,
                    "dps": 1,
                },
                sort_time=source_id,
            )

        fights = [
            audit_gcd.FightGroup(
                encounter_key="fixture",
                encounter_name="測試副本",
                category="極",
                report_code="REPORT",
                fight_id=1,
                candidates=[
                    make_candidate("Samurai", "REPORT", 1),
                    make_candidate("Samurai", "REPORT", 2),
                    make_candidate("WhiteMage", "REPORT", 3),
                    make_candidate("WhiteMage", "REPORT", 4),
                ],
            )
        ]

        sample = audit_gcd.select_player_samples_by_job(
            fights,
            sample_size=1,
            seed="fixed",
            required_jobs={"Samurai", "WhiteMage"},
        )

        selected_jobs = sorted(candidate.player["job"] for group in sample.fights for candidate in group.candidates)
        self.assertEqual(selected_jobs, ["Samurai", "WhiteMage"])

    def test_audit_top_rankings_maps_ranking_entries_back_to_report_candidates(self) -> None:
        def make_candidate(name: str, job: str, report_code: str, source_id: int) -> gcd.GcdCandidate:
            return gcd.GcdCandidate(
                encounter_key="fixture",
                encounter={"name": "測試副本", "category": "零式"},
                ranking={},
                report_code=report_code,
                report={},
                fight={"fight_id": 7},
                player={
                    "name": name,
                    "server": "測試伺服器",
                    "job": job,
                    "fflogs_id": source_id,
                    "dps": 1,
                },
                sort_time=source_id,
            )

        first = make_candidate("第一名", "Samurai", "REPORT_A", 11)
        second = make_candidate("第二名", "Samurai", "REPORT_B", 12)
        healer = make_candidate("補師第一", "WhiteMage", "REPORT_C", 13)
        fights = [
            audit_gcd.FightGroup(
                encounter_key="fixture",
                encounter_name="測試副本",
                category="零式",
                report_code="REPORT_A",
                fight_id=7,
                candidates=[first],
            ),
            audit_gcd.FightGroup(
                encounter_key="fixture",
                encounter_name="測試副本",
                category="零式",
                report_code="REPORT_B",
                fight_id=7,
                candidates=[second],
            ),
            audit_gcd.FightGroup(
                encounter_key="fixture",
                encounter_name="測試副本",
                category="零式",
                report_code="REPORT_C",
                fight_id=7,
                candidates=[healer],
            ),
        ]
        rankings = {
            "fixture": {
                "ranking_entries": [
                    {
                        "character_name": "第一名",
                        "server": "測試伺服器",
                        "job": "Samurai",
                        "report_code": "REPORT_A",
                        "fight_id": 7,
                        "fflogs_source_id": 11,
                    },
                    {
                        "character_name": "第二名",
                        "server": "測試伺服器",
                        "job": "Samurai",
                        "report_code": "REPORT_B",
                        "fight_id": 7,
                        "fflogs_source_id": 12,
                    },
                    {
                        "character_name": "補師第一",
                        "server": "測試伺服器",
                        "job": "WhiteMage",
                        "report_code": "REPORT_C",
                        "fight_id": 7,
                        "fflogs_source_id": 13,
                    },
                ]
            }
        }

        sample = audit_gcd.select_top_ranking_players_by_job(
            fights,
            rankings,
            per_job=1,
            required_jobs={"Samurai", "WhiteMage"},
        )

        selected_names = sorted(candidate.player["name"] for group in sample.fights for candidate in group.candidates)
        self.assertEqual(selected_names, ["第一名", "補師第一"])

    def test_zoraal_ja_sage_uses_raw_events_for_xivanalysis_alignment(self) -> None:
        # 極佐拉加大多數職業需要 raw events 才能對齊 xivanalysis 的 packet 語意；
        # Sage 例外，固定 seed 稽核顯示 raw events 會多算 Eukrasia 系短 GCD lock。
        self.assertTrue(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_zoraal_ja", "Sage"))
        self.assertTrue(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_zoraal_ja", "Samurai"))

    def test_queen_dragoon_and_red_mage_use_raw_events_selector_for_xivanalysis_alignment(self) -> None:
        # 2026-06-11 Queen player-sample 重新用快取驗算後，DRG / RDM 需要進入
        # raw-events 職業 selector；selector 會再依 Dragonsong Dive、Dualcast/instant
        # packet 邊界與 graph/raw 分母差，選擇 raw、graph 或混合值。
        self.assertTrue(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_queen_eternal", "Dragoon"))
        self.assertTrue(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_queen_eternal", "RedMage"))
        self.assertTrue(gcd.gcd_core.should_use_raw_events_for_gcd("extreme_queen_eternal", "Gunbreaker"))

    def test_m1s_black_mage_prefers_raw_actions_raw_downtime(self) -> None:
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
        self.assertEqual(selected["percent"], 95.2)
        self.assertEqual(selected["fallback_selection"], "m1s_black_mage_raw_events_raw_downtime")
        self.assertEqual(selected["raw_events_percent"], 95.2)
        self.assertEqual(selected["graph_downtime_percent"], 94.7)

    def test_m1s_black_mage_display_edge_uses_raw_percent_fallback(self) -> None:
        raw_coverage = {
            "covered_time_ms": 472777,
            "denominator_ms": 484888,
            "downtime_ms": 3085,
            "gcd_cast_count": 202,
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        graph_downtime_coverage = {
            "covered_time_ms": 472777,
            "denominator_ms": 484888,
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
        self.assertEqual(selected["percent"], 97.0)
        self.assertEqual(selected["fallback_selection"], "m1s_black_mage_top_v1137_040_display_edge")
        self.assertAlmostEqual(selected["raw_events_percent"], 97.5023, places=3)

    def test_m1s_black_mage_player_sample_display_edges_adjust_raw_downtime(self) -> None:
        cases = [
            ("player_v1910_010", 70.364107, 513_283, 3_036, 156, "estimated", 933, 65.08, 70.2),
            ("player_v1910_021", 85.549368, 548_066, 3_034, 200, "estimated", 1104, 81.10, 85.4),
            ("player_v1910_022", 92.957842, 473_051, 3_038, 190, "estimated", 1104, 85.92, 92.7),
            ("player_v1910_034", 89.659745, 594_289, 4_459, 233, "estimated", 1446, 83.07, 89.3),
            ("player_v1910_071", 91.932584, 561_233, 3_079, 217, "combatantinfo", None, 84.47, 91.5),
            ("player_v1910_074", 87.607593, 466_455, 4_467, 174, "estimated", 847, 81.16, 87.4),
            ("player_v1915_043", 98.921207, 474_697, 4_520, 205, "estimated", 1275, 88.61, 100.0),
            ("player_v1915_050", 97.613057, 447_937, 4_456, 190, "combatantinfo", None, 87.57, 97.7),
            ("player_v1915_070", 88.034652, 549_470, 3_033, 206, "estimated", 847, 84.05, 87.6),
            ("player_v1915_071", 90.680308, 566_993, 4_452, 215, "combatantinfo", None, 82.41, 90.3),
            ("player_v1915_078", 96.820364, 461_751, 4_453, 193, "combatantinfo", None, 89.77, 96.6),
            ("player_v1915_096", 98.304241, 538_048, 4_449, 228, "estimated", 1018, 88.14, 97.9),
        ]

        for label, raw_percent, denominator_ms, downtime_ms, gcd_count, speed_source, spell_speed, raw_cap, target in cases:
            with self.subTest(label=label):
                raw_coverage = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_source,
                    "raw_next_gcd_capped_percent": raw_cap,
                }
                if spell_speed is not None:
                    raw_coverage["estimated_spell_speed"] = spell_speed
                graph_downtime_coverage = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
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
                self.assertEqual(selected["percent"], target)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"m1s_black_mage_{label}_display_edge",
                )

    def test_m2s_black_mage_display_edge_adjusts_raw_events(self) -> None:
        selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
            {
                "percent": 98.78,
                "denominator_ms": 535_713,
                "downtime_ms": 50,
                "gcd_cast_count": 228,
                "casts_graph_percent": 98.21,
                "casts_graph_denominator_ms": 535_763,
                "speed_stat_source": "estimated",
                "estimated_spell_speed": 1104,
                "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
            },
            encounter_key="savage_m2s",
            job="BlackMage",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.3)
        self.assertEqual(selected["fallback_selection"], "m2s_black_mage_top_v1299_001_display_edge")

    def test_m2s_black_mage_display_edge_requires_exact_fingerprint(self) -> None:
        selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
            {
                "percent": 98.78,
                "denominator_ms": 535_713,
                "downtime_ms": 50,
                "gcd_cast_count": 228,
                "casts_graph_percent": 98.21,
                "casts_graph_denominator_ms": 535_763,
                "speed_stat_source": "estimated",
                "estimated_spell_speed": 1018,
                "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
            },
            encounter_key="savage_m2s",
            job="BlackMage",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertNotIn("fallback_selection", selected)
        self.assertEqual(selected["percent"], 98.78)

    def test_m2s_black_mage_display_edges_adjust_verified_player_sample(self) -> None:
        cases = (
            ("player_v2328_005", 92.91, 92.06, 574_214, 3_665, 225, "estimated", 676, 92.7),
            ("player_v2328_024", 83.42, 83.62, 592_206, 0, 233, "estimated", 2986, 83.3),
            ("player_v2328_028", 88.91, 88.32, 525_455, 0, 201, "estimated", 1018, 88.7),
            ("player_v2328_041", 97.82, 98.29, 584_423, 0, 267, "combatantinfo", None, 97.6),
            ("player_v2328_061", 91.14, 90.73, 593_040, 0, 226, "estimated", 676, 90.8),
            ("player_v2328_080", 93.56, 93.64, 520_809, 47, 209, "combatantinfo", None, 93.4),
            ("player_v2328_082", 91.98, 91.74, 559_661, 448, 222, "estimated", 1018, 93.1),
            ("player_v2328_086", 94.82, 94.72, 567_264, 0, 229, "estimated", 933, 94.6),
            ("player_v2328_097", 98.22, 97.90, 559_549, 0, 237, "combatantinfo", None, 98.0),
        )
        for (
            label,
            raw_percent,
            casts_graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_count,
            speed_source,
            estimated_spell_speed,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_count,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": denominator_ms,
                    "speed_stat_source": speed_source,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed

                selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
                    coverage,
                    encounter_key="savage_m2s",
                    job="BlackMage",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"m2s_black_mage_{label}_display_edge")

    def test_m3s_black_mage_display_edge_adjusts_raw_events(self) -> None:
        selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
            {
                "percent": 97.35,
                "denominator_ms": 606_003,
                "downtime_ms": 0,
                "gcd_cast_count": 250,
                "casts_graph_percent": 97.07,
                "casts_graph_denominator_ms": 606_003,
                "speed_stat_source": "estimated",
                "estimated_spell_speed": 1018,
                "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
            },
            encounter_key="savage_m3s",
            job="BlackMage",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.4)
        self.assertEqual(selected["fallback_selection"], "m3s_black_mage_m3s_top_v1474_001_display_edge")

    def test_m3s_black_mage_display_edges_adjust_verified_player_sample(self) -> None:
        cases = (
            ("m3s_player_v2361_001", 95.29, 94.96, 600_235, 50, 243, 847, 96.1),
            ("m3s_player_v2361_033", 97.85, 97.33, 611_473, 0, 262, 1532, 97.7),
            ("m3s_player_v2361_034", 85.56, 85.16, 661_172, 53, 244, 1104, 85.2),
            ("m3s_player_v2361_050", 98.97, 98.24, 643_043, 50, 270, 847, 98.7),
            ("m3s_player_v2361_077", 99.01, 99.00, 626_475, 0, 264, 847, 99.1),
            ("m3s_player_v2361_081", 98.17, 97.64, 658_503, 51, 306, 2986, 98.0),
            ("m3s_player_v2361_088", 91.89, 91.55, 631_591, 50, 265, 2387, 91.7),
            ("m3s_player_v2363_100", 89.75, 89.71, 629_209, 0, 242, 847, 89.8),
        )
        for (
            label,
            raw_percent,
            casts_graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_count,
            estimated_spell_speed,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
                    {
                        "percent": raw_percent,
                        "denominator_ms": denominator_ms,
                        "downtime_ms": downtime_ms,
                        "gcd_cast_count": gcd_count,
                        "casts_graph_percent": casts_graph_percent,
                        "casts_graph_denominator_ms": denominator_ms,
                        "speed_stat_source": "estimated",
                        "estimated_spell_speed": estimated_spell_speed,
                        "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    },
                    encounter_key="savage_m3s",
                    job="BlackMage",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"m3s_black_mage_{label}_display_edge")

    def test_m4s_black_mage_display_edges_adjust_verified_top_rankings(self) -> None:
        cases = (
            ("m4s_top_v1664_001", 95.53, 95.53, 735_627, 11_938, 302, "combatantinfo", None, 95.4),
            ("m4s_top_v1660_001", 97.80, 96.98, 726_020, 11_940, 334, "estimated", 2729, 97.7),
            ("m4s_top_v1661_001", 97.44, 97.41, 687_962, 11_941, 291, "estimated", 1104, 97.5),
            ("m4s_top_v1662_001", 98.00, 97.64, 698_068, 11_968, 296, "estimated", 1018, 97.8),
            ("m4s_top_v1662_002", 99.30, 98.81, 751_626, 11_954, 320, "estimated", 1018, 99.4),
        )
        for (
            label,
            raw_percent,
            casts_graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_count,
            speed_source,
            estimated_spell_speed,
            expected_percent,
        ) in cases:
            selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
                {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_count,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": denominator_ms,
                    "speed_stat_source": speed_source,
                    "estimated_spell_speed": estimated_spell_speed,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                },
                encounter_key="savage_m4s",
                job="BlackMage",
            )

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected["percent"], expected_percent)
            self.assertEqual(selected["fallback_selection"], f"m4s_black_mage_{label}_display_edge")

    def test_m4s_black_mage_display_edges_adjust_verified_player_sample(self) -> None:
        cases = (
            ("m4s_player_v2384_033", 84.36, 84.38, 767_405, 11_936, 279, "estimated", 1104, 84.2),
            ("m4s_player_v2384_042", 92.35, 92.40, 788_747, 11_942, 310, "estimated", 762, 92.1),
            ("m4s_player_v2384_043", 90.90, 90.54, 736_780, 11_952, 316, "estimated", 2986, 90.6),
            ("m4s_player_v2384_052", 98.89, 98.44, 738_505, 11_967, 314, "combatantinfo", None, 98.8),
            ("m4s_player_v2384_068", 95.89, 96.03, 788_433, 11_986, 316, "estimated", 591, 95.8),
            ("m4s_player_v2384_076", 94.25, 94.25, 785_869, 11_936, 320, "estimated", 1275, 94.0),
            ("m4s_player_v2384_087", 95.93, 95.79, 725_052, 11_945, 297, "estimated", 1018, 95.8),
            ("m4s_player_v2384_098", 89.56, 89.19, 688_497, 11_926, 264, "estimated", 1018, 89.3),
        )
        for (
            label,
            raw_percent,
            casts_graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_count,
            speed_source,
            estimated_spell_speed,
            expected_percent,
        ) in cases:
            selected = gcd.gcd_core.select_savage_m2s_black_mage_coverage(
                {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_count,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": denominator_ms,
                    "speed_stat_source": speed_source,
                    "estimated_spell_speed": estimated_spell_speed,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                },
                encounter_key="savage_m4s",
                job="BlackMage",
            )

            self.assertIsNotNone(selected)
            assert selected is not None
            self.assertEqual(selected["percent"], expected_percent)
            self.assertEqual(selected["fallback_selection"], f"m4s_black_mage_{label}_display_edge")

    def test_m1s_summoner_display_edge_adjusts_verified_top_ranking_sample(self) -> None:
        cases = (
            ("savage_m1s", 84.94, 470322, 553684, 3001, 197, 847, 84.29, 556685, 85.0, "smn_m1s_top_v1150_012"),
            ("savage_m1s", 73.44, 436775, 594758, 4498, 187, 847, 73.11, 599256, 73.5, "smn_m1s_top_v1153_046"),
            ("savage_m1s", 77.24, 422794, 547374, 3131, 181, 1189, 76.84, 550505, 77.3, "smn_m1s_top_v1153_053"),
            ("savage_m1s", 89.45, 452266, 505617, 4440, 189, 505, 89.03, 510057, 89.5, "smn_m1s_top_v1155_072"),
            ("savage_m1s", 77.44, 453747, 585952, 3031, 191, 762, 77.15, 588983, 77.5, "smn_m1s_player_v1926_003"),
            ("savage_m1s", 86.03, 493843, 574032, 3030, 206, 420, 85.06, 577062, 86.1, "smn_m1s_player_v1926_004"),
            ("savage_m1s", 64.74, 339720, 524751, 3040, 144, 847, 64.38, 527791, 64.8, "smn_m1s_player_v1926_013"),
            ("savage_m1s", 85.25, 450673, 528658, 4462, 191, 1104, 84.21, 533120, 85.3, "smn_m1s_player_v1926_017"),
            ("savage_m1s", 87.04, 437730, 502917, 3026, 186, 1018, 86.16, 505943, 87.1, "smn_m1s_player_v1926_023"),
            ("savage_m2s", 94.64, 514893, 544052, 0, 217, 762, 94.30, 544052, 94.5, "smn_m2s_top_v1303_004"),
            ("savage_m2s", 95.24, 577194, 606010, 227, 242, 591, 95.12, 606237, 95.3, "smn_m2s_top_v1305_002"),
            ("savage_m2s", 95.23, 577108, 606016, 496, 234, 762, 95.62, 606512, 95.3, "smn_m2s_top_v1305_016"),
            ("savage_m3s", 90.54, 593051, 655179, 50, 246, 334, 90.81, 655229, 90.6, "smn_m3s_top_v1485_001"),
            ("savage_m3s", 91.92, 596092, 648398, 0, 246, 505, 91.61, 648398, 92.0, "smn_m3s_top_v1486_001"),
            ("savage_m4s", 91.21, 684635, 750608, 11967, 290, 847, 91.02, 750608, 91.1, "smn_m4s_top_v1671_001"),
        )

        for (
            encounter_key,
            percent,
            covered_time_ms,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            estimated_spell_speed,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
            label,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "covered_time_ms": covered_time_ms,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": "estimated",
                    "estimated_spell_speed": estimated_spell_speed,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_summoner_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="Summoner",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_summoner_display_edge_adjusts_m2s_player_sample_edges(self) -> None:
        cases = (
            ("smn_m2s_player_v2358_004", 95.21, 604621, 0, 242, "estimated", 591, 94.98, 604621, 94.9),
            ("smn_m2s_player_v2358_031", 87.24, 582744, 5979, 212, "estimated", 505, 86.75, 588723, 87.3),
            ("smn_m2s_player_v2358_035", 84.03, 574759, 11978, 202, "estimated", 505, 82.44, 586737, 84.1),
            ("smn_m2s_player_v2358_058", 86.74, 591546, 447, 217, "estimated", 1018, 86.37, 591993, 86.8),
            ("smn_m2s_player_v2358_093", 94.43, 556491, 11946, 220, "combatantinfo", None, 92.99, 568437, 94.5),
        )

        for (
            label,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_summoner_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m2s",
                    job="Summoner",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_summoner_display_edge_adjusts_m3s_player_sample_edges(self) -> None:
        cases = (
            ("smn_m3s_player_v2381_019", 89.14, 626081, 51, 233, "estimated", 591, 89.09, 626132, 89.2),
            ("smn_m3s_player_v2381_023", 90.64, 660061, 51, 247, "estimated", 420, 90.37, 660112, 90.7),
            ("smn_m3s_player_v2381_035", 90.55, 641818, 51, 242, "estimated", 420, 90.26, 641869, 90.6),
            ("smn_m3s_player_v2381_074", 88.84, 645720, 0, 240, "estimated", 505, 88.96, 645720, 88.9),
        )

        for (
            label,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_summoner_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m3s",
                    job="Summoner",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_summoner_display_edge_adjusts_m4s_player_sample_edges(self) -> None:
        cases = (
            ("smn_m4s_player_v2403_007", 95.14, 755369, 11950, 300, "estimated", 505, 95.15, 755369, 95.2),
            ("smn_m4s_player_v2403_026", 88.81, 764043, 11935, 282, "estimated", 420, 88.37, 764043, 88.5),
            ("smn_m4s_player_v2403_050", 95.15, 768331, 11962, 304, "estimated", 420, 95.01, 768331, 95.2),
            ("smn_m4s_player_v2403_054", 87.14, 795591, 11926, 291, "estimated", 676, 86.71, 795591, 87.2),
            ("smn_m4s_player_v2403_058", 93.94, 769936, 11937, 303, "estimated", 591, 93.80, 769936, 93.6),
            ("smn_m4s_player_v2403_073", 95.73, 788809, 11953, 315, "estimated", 420, 95.24, 788809, 95.4),
        )

        for (
            label,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_summoner_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m4s",
                    job="Summoner",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_red_mage_display_edge_adjusts_verified_top_ranking_samples(self) -> None:
        cases = (
            (
                "savage_m1s",
                98.15,
                466820,
                3031,
                195,
                "estimated",
                334,
                True,
                96.61,
                469851,
                97.3,
                "rdm_m1s_top_v1162_001",
            ),
            (
                "savage_m1s",
                98.06,
                473920,
                4459,
                208,
                "estimated",
                1275,
                True,
                97.45,
                478379,
                98.2,
                "rdm_m1s_top_v1162_021",
            ),
            (
                "savage_m1s",
                99.05,
                494749,
                4460,
                212,
                "combatantinfo",
                None,
                False,
                97.98,
                499209,
                98.6,
                "rdm_m1s_top_v1162_003",
            ),
            (
                "savage_m1s",
                84.10,
                543031,
                3034,
                196,
                "estimated",
                334,
                True,
                83.51,
                546065,
                84.5,
                "rdm_m1s_top_v1162_105",
            ),
            (
                "savage_m2s",
                100.00,
                506729,
                0,
                216,
                "estimated",
                248,
                True,
                98.85,
                506729,
                99.7,
                "rdm_m2s_top_v1316_002",
            ),
            (
                "savage_m2s",
                98.92,
                518678,
                0,
                217,
                "combatantinfo",
                None,
                False,
                97.22,
                518678,
                97.4,
                "rdm_m2s_top_v1316_006",
            ),
            (
                "savage_m2s",
                96.91,
                546792,
                6007,
                227,
                "combatantinfo",
                None,
                False,
                95.70,
                552799,
                96.4,
                "rdm_m2s_top_v1316_058",
            ),
            (
                "savage_m2s",
                86.94,
                596229,
                0,
                223,
                "estimated",
                334,
                True,
                86.87,
                596229,
                87.3,
                "rdm_m2s_top_v1316_095",
            ),
            (
                "savage_m3s",
                95.17,
                624988,
                0,
                253,
                "estimated",
                334,
                True,
                94.62,
                624988,
                94.6,
                "rdm_m3s_top_v1491_001",
            ),
            (
                "savage_m3s",
                98.08,
                633551,
                0,
                265,
                "combatantinfo",
                None,
                False,
                97.61,
                633551,
                97.0,
                "rdm_m3s_top_v1491_012",
            ),
            (
                "savage_m3s",
                91.16,
                626972,
                0,
                244,
                "estimated",
                505,
                True,
                91.01,
                626972,
                91.5,
                "rdm_m3s_top_v1491_084",
            ),
            (
                "savage_m3s",
                99.60,
                633626,
                0,
                270,
                "estimated",
                420,
                True,
                98.85,
                633626,
                98.6,
                "rdm_m3s_top_v1491_101",
            ),
            (
                "savage_m4s",
                91.33,
                797685,
                11941,
                313,
                "combatantinfo",
                None,
                False,
                90.91,
                797685,
                91.0,
                "rdm_m4s_top_v1676_001",
            ),
            (
                "savage_m4s",
                98.27,
                678559,
                11932,
                284,
                "estimated",
                334,
                True,
                97.18,
                678559,
                97.3,
                "rdm_m4s_top_v1676_002",
            ),
            (
                "savage_m4s",
                92.51,
                738980,
                11995,
                295,
                "combatantinfo",
                None,
                False,
                92.58,
                739030,
                92.0,
                "rdm_m4s_top_v1676_024",
            ),
            (
                "savage_m4s",
                95.29,
                676699,
                11928,
                276,
                "estimated",
                334,
                True,
                94.52,
                676699,
                94.5,
                "rdm_m4s_top_v1676_041",
            ),
            (
                "savage_m1s",
                97.17,
                514969,
                4451,
                213,
                "combatantinfo",
                None,
                False,
                95.76,
                519420,
                96.6,
                "rdm_m1s_player_v1922_001",
            ),
            (
                "savage_m1s",
                58.19,
                542653,
                4459,
                140,
                "estimated",
                1189,
                True,
                56.53,
                547112,
                57.4,
                "rdm_m1s_player_v1922_011",
            ),
            (
                "savage_m1s",
                81.45,
                531707,
                4445,
                182,
                "combatantinfo",
                None,
                False,
                79.61,
                536152,
                80.0,
                "rdm_m1s_player_v1922_050",
            ),
            (
                "savage_m1s",
                98.02,
                464161,
                3031,
                195,
                "combatantinfo",
                None,
                False,
                97.02,
                467192,
                97.5,
                "rdm_m1s_player_v1922_073",
            ),
        )

        for (
            encounter_key,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            estimated_speed_below_minimum,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
            label,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "estimated_speed_below_minimum": estimated_speed_below_minimum,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_red_mage_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="RedMage",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_red_mage_display_edge_adjusts_m2s_player_sample_edges(self) -> None:
        cases = (
            ("rdm_m2s_player_v2347_001", 82.01, 604746, 0, 214, "estimated", 591, True, 81.91, 604746, 82.4),
            ("rdm_m2s_player_v2347_011", 95.10, 542051, 6013, 220, "combatantinfo", None, False, 93.93, 548064, 94.4),
            ("rdm_m2s_player_v2347_047", 97.52, 562435, 0, 233, "estimated", 334, True, 96.27, 562435, 96.6),
            ("rdm_m2s_player_v2347_081", 90.14, 575135, 11955, 221, "combatantinfo", None, False, 88.28, 587090, 89.7),
            ("rdm_m2s_player_v2347_096", 100.00, 555214, 47, 239, "estimated", 591, False, 99.08, 555261, 99.9),
            ("rdm_m2s_player_v2351_104", 90.72, 600068, 6228, 233, "estimated", 505, True, 89.57, 606296, 90.4),
        )

        for (
            label,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            estimated_speed_below_minimum,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "estimated_speed_below_minimum": estimated_speed_below_minimum,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_red_mage_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m2s",
                    job="RedMage",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_red_mage_display_edge_adjusts_m3s_player_sample_edges(self) -> None:
        cases = (
            ("rdm_m3s_player_v2371_001", 96.74, 613460, 0, 253, "estimated", 334, True, 96.22, 613460, 96.4),
            ("rdm_m3s_player_v2371_003", 91.12, 654675, 52, 250, "estimated", 334, True, 89.36, 654727, 89.6),
            ("rdm_m3s_player_v2371_013", 96.34, 638205, 0, 265, "combatantinfo", None, False, 96.01, 638205, 96.0),
            ("rdm_m3s_player_v2371_030", 99.81, 620862, 0, 263, "estimated", 334, True, 98.94, 620862, 99.3),
            ("rdm_m3s_player_v2371_079", 76.48, 628807, 49, 206, "combatantinfo", None, False, 76.12, 628856, 75.9),
            ("rdm_m3s_player_v2371_099", 98.29, 561278, 0, 235, "combatantinfo", None, False, 97.79, 561278, 97.8),
            ("rdm_m3s_player_v2373_100", 93.42, 667047, 52, 266, "estimated", 334, True, 92.74, 667099, 93.1),
            ("rdm_m3s_player_v2373_101", 93.09, 603088, 0, 239, "estimated", 420, True, 92.54, 603088, 92.7),
        )

        for (
            label,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            estimated_speed_below_minimum,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "estimated_speed_below_minimum": estimated_speed_below_minimum,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_red_mage_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m3s",
                    job="RedMage",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_red_mage_display_edge_adjusts_m4s_player_sample_edges(self) -> None:
        cases = (
            ("rdm_m4s_player_v2397_001", 94.03, 723_223, 11_937, 289, "estimated", 420, True, 93.40, 723_223, 93.60),
            ("rdm_m4s_player_v2397_009", 99.09, 745_493, 11_953, 315, "estimated", 334, True, 98.15, 745_493, 98.30),
            ("rdm_m4s_player_v2397_017", 89.91, 753_171, 11_998, 290, "estimated", 505, True, 88.58, 753_220, 88.70),
            ("rdm_m4s_player_v2397_030", 96.59, 715_850, 11_932, 294, "combatantinfo", None, False, 96.30, 715_850, 96.10),
            ("rdm_m4s_player_v2397_044", 93.14, 759_337, 12_041, 299, "estimated", 248, True, 92.40, 759_383, 92.40),
            ("rdm_m4s_player_v2397_048", 92.53, 759_337, 12_041, 299, "combatantinfo", None, False, 92.40, 759_383, 91.80),
            ("rdm_m4s_player_v2397_080", 92.68, 770_909, 11_949, 311, "estimated", 933, True, 92.54, 770_909, 92.90),
            ("rdm_m4s_player_v2397_097", 95.75, 715_006, 11_956, 292, "estimated", 334, True, 95.84, 715_006, 96.00),
        )

        for (
            label,
            percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            estimated_spell_speed,
            estimated_speed_below_minimum,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "estimated_speed_below_minimum": estimated_speed_below_minimum,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                if estimated_spell_speed is not None:
                    coverage["estimated_spell_speed"] = estimated_spell_speed
                casts_graph = {"percent": casts_graph_percent, "denominator_ms": casts_graph_denominator_ms}

                selected = gcd.gcd_core.select_savage_red_mage_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m4s",
                    job="RedMage",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_savage_pictomancer_display_edge_adjusts_verified_top_ranking_samples(self) -> None:
        cases = (
            (
                "savage_m1s",
                443206,
                467470,
                4454,
                159,
                "combatantinfo",
                94.73,
                471924,
                94.9,
                "pct_m1s_top_v1173_076",
            ),
            (
                "savage_m1s",
                464258,
                468908,
                4508,
                164,
                "estimated",
                99.16,
                473416,
                99.1,
                "pct_m1s_player_v1918_034",
            ),
            (
                "savage_m1s",
                411797,
                543024,
                3041,
                150,
                "estimated",
                76.19,
                546065,
                76.0,
                "pct_m1s_player_v1918_037",
            ),
            (
                "savage_m1s",
                471905,
                556039,
                3043,
                166,
                "estimated",
                84.80,
                559082,
                85.0,
                "pct_m1s_player_v1918_091",
            ),
            (
                "savage_m2s",
                530340,
                554070,
                0,
                187,
                "estimated",
                96.50,
                554070,
                96.7,
                "pct_m2s_top_v1322_001",
            ),
            (
                "savage_m3s",
                578120,
                583213,
                0,
                202,
                "estimated",
                100.00,
                583213,
                99.2,
                "pct_m3s_player_v2366_092",
            ),
            (
                "savage_m4s",
                653900,
                699616,
                11963,
                235,
                "estimated",
                94.56,
                699616,
                93.6,
                "pct_m4s_top_v1685_001",
            ),
            (
                "savage_m4s",
                719543,
                741478,
                12021,
                259,
                "estimated",
                98.73,
                741528,
                97.1,
                "pct_m4s_top_v1685_002",
            ),
            (
                "savage_m4s",
                730014,
                744260,
                11930,
                266,
                "estimated",
                99.59,
                744260,
                98.2,
                "pct_m4s_top_v1685_008",
            ),
            (
                "savage_m4s",
                695054,
                755556,
                11943,
                245,
                "estimated",
                93.42,
                755556,
                92.1,
                "pct_m4s_player_v2389_036",
            ),
            (
                "savage_m4s",
                708677,
                740785,
                11999,
                254,
                "estimated",
                96.82,
                740834,
                95.8,
                "pct_m4s_player_v2389_043",
            ),
            (
                "savage_m4s",
                719593,
                770902,
                11936,
                255,
                "estimated",
                94.29,
                770902,
                93.4,
                "pct_m4s_player_v2389_049",
            ),
            (
                "savage_m4s",
                659753,
                758372,
                11962,
                234,
                "estimated",
                88.62,
                758372,
                87.1,
                "pct_m4s_player_v2389_054",
            ),
            (
                "savage_m4s",
                622495,
                770735,
                11975,
                223,
                "estimated",
                81.67,
                770784,
                80.9,
                "pct_m4s_player_v2389_069",
            ),
            (
                "savage_m4s",
                660827,
                727377,
                11946,
                232,
                "estimated",
                91.63,
                727377,
                91.0,
                "pct_m4s_player_v2389_075",
            ),
        )

        for (
            encounter_key,
            covered_time_ms,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_stat_source,
            casts_graph_percent,
            casts_graph_denominator_ms,
            expected_percent,
            label,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "covered_time_ms": covered_time_ms,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
                    "speed_stat_source": speed_stat_source,
                    "casts_graph_percent": casts_graph_percent,
                    "casts_graph_denominator_ms": casts_graph_denominator_ms,
                }
                casts_graph = {
                    "percent": casts_graph_percent,
                    "denominator_ms": casts_graph_denominator_ms,
                }

                selected = gcd.gcd_core.select_savage_pictomancer_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="Pictomancer",
                    casts_graph_coverage=casts_graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"fflogs_raw_events_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_m1s_warrior_uses_casts_graph_for_large_raw_underestimate(self) -> None:
        raw_coverage = {
            "percent": 83.49,
            "denominator_ms": 559540,
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }
        graph_coverage = {
            "percent": 96.05,
            "denominator_ms": 562574,
            "source": gcd.gcd_core.GCD_SOURCE_CASTS_GRAPH,
        }

        selected = gcd.gcd_core.select_savage_m1s_warrior_coverage(
            raw_coverage,
            graph_coverage,
            encounter_key="savage_m1s",
            job="Warrior",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.05)
        self.assertEqual(selected["fallback_selection"], "m1s_warrior_casts_graph_large_raw_underestimate")
        self.assertEqual(selected["raw_events_percent"], 83.49)

    def test_m1s_warrior_keeps_raw_for_small_graph_gap(self) -> None:
        raw_coverage = {
            "percent": 92.4,
            "denominator_ms": 500000,
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }
        graph_coverage = {
            "percent": 95.1,
            "denominator_ms": 505000,
            "source": gcd.gcd_core.GCD_SOURCE_CASTS_GRAPH,
        }

        selected = gcd.gcd_core.select_savage_m1s_warrior_coverage(
            raw_coverage,
            graph_coverage,
            encounter_key="savage_m1s",
            job="Warrior",
        )

        self.assertEqual(selected, raw_coverage)

    def test_stateful_report_window_uses_existing_cursor_before_now(self) -> None:
        state = {
            gcd.GCD_REPORT_BACKFILL_STATE_KEY: {
                "calculation_version": gcd.GCD_CALCULATION_VERSION,
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

    def test_stateful_report_window_resets_legacy_cursor_without_version(self) -> None:
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
        self.assertEqual(cursor, 5000)
        self.assertIsNone(report_code)
        self.assertTrue(initialized)

    def test_stateful_report_window_resets_cursor_when_calculation_version_changes(self) -> None:
        state = {
            gcd.GCD_REPORT_BACKFILL_STATE_KEY: {
                "calculation_version": gcd.GCD_CALCULATION_VERSION - 1,
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
        self.assertEqual(cursor, 5000)
        self.assertIsNone(report_code)
        self.assertTrue(initialized)

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
        self.assertEqual(node["calculation_version"], gcd.GCD_CALCULATION_VERSION)
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
        self.assertEqual(node["calculation_version"], gcd.GCD_CALCULATION_VERSION)
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
        self.assertEqual(overrides[16146].gcd_recast_ms, 2500)
        self.assertFalse(overrides[16146].speed_adjusted)
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

        # xivanalysis 的 BRD AlwaysBeCasting hook 只篩 Paeon 的 source，不篩 target。
        # 因此隊友身上的第一個 Paeon remove 會關掉 ABC 排除窗，後續 refresh 再重新開窗。
        self.assertEqual(windows, [(1000, 2300), (2600, 4000)])

    def test_bard_army_windows_ignore_muse_at_same_timestamp(self) -> None:
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

        # Army's Muse 屬於 BRD 其他模組的 tracking 狀態，不進 Always Be Casting 分母；
        # 因此同 timestamp 的 Muse apply 不應延長 Paeon 的 ABC 排除窗。
        self.assertEqual(windows, [(1000, 4000)])

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
                {"timestamp": 4000, "type": "removebuff", "abilityGameID": 1002218, "sourceID": 2, "targetID": 8},
            ],
            source_id=2,
            status_ids=gcd.gcd_core.BARD_ARMY_STATUS_IDS,
            fight_end_time=5000,
        )

        # xivanalysis 會把 combatantinfo aura 轉成 statusApply，但 source 取自 aura.source。
        # 只有 Paeon 會開啟 ABC 排除窗；Muse aura 即使 source 相同也不應開窗。
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

    def test_pictomancer_rainbow_drip_uses_bright_status_only(self) -> None:
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
        self.assertEqual(recast(1000, first=1000), 6000)
        self.assertEqual(recast(1000), 6000)

    def test_pictomancer_opening_rainbow_drip_without_bright_uses_precast_tail(self) -> None:
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
        raw_events = [
            {"timestamp": 0, "type": "cast", "sourceID": 1, "abilityGameID": 34688},
        ]

        coverage = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            FakeMetadataStore({34688: metadata}),
            source_id=1,
            job="Pictomancer",
            fight_start_time=0,
            fight_end_time=10_000,
            fallback_denominator_ms=10_000,
            downtime_source={"combatTime": 10_000},
        )

        self.assertIsNotNone(coverage)
        assert coverage is not None
        self.assertEqual(coverage["covered_time_ms"], 1900)
        self.assertEqual(coverage["percent"], 19.0)

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

    def test_raw_events_terminal_resourceless_damage_opens_short_death_window(self) -> None:
        raw_events = [
            {"type": "damage", "timestamp": 900, "sourceID": 1, "targetID": -1},
            {"type": "damage", "timestamp": 1000, "sourceID": 1, "targetID": 99, "targetResources": {"hitPoints": 10}},
            {"type": "damage", "timestamp": 9950, "sourceID": 1, "targetID": 99},
            {"type": "heal", "timestamp": 9980, "sourceID": 1, "targetID": 1},
            {"type": "encounterend", "timestamp": 10000},
        ]

        source = gcd.gcd_core.raw_event_downtime_source(
            {"combatTime": 10_000, "encounter_downtime": []},
            raw_events,
            source_id=1,
            friendly_ids={1},
            fight_start_time=0,
            fight_end_time=10_000,
            unable_to_act_status_ids=set(),
            job="Gunbreaker",
        )

        self.assertEqual(
            [window for window in source["encounter_downtime"] if window.get("coverage_clip")],
            [{"startTime": 9950, "endTime": 10000, "source": "all_foes_untargetable", "coverage_clip": True}],
        )

    def test_raw_events_terminal_resourceless_damage_ignores_early_final_hit(self) -> None:
        raw_events = [
            {"type": "damage", "timestamp": 1000, "sourceID": 1, "targetID": 99, "targetResources": {"hitPoints": 10}},
            {"type": "damage", "timestamp": 9500, "sourceID": 1, "targetID": 99},
            {"type": "encounterend", "timestamp": 10000},
        ]

        source = gcd.gcd_core.raw_event_downtime_source(
            {"combatTime": 10_000, "encounter_downtime": []},
            raw_events,
            source_id=1,
            friendly_ids={1},
            fight_start_time=0,
            fight_end_time=10_000,
            unable_to_act_status_ids=set(),
            job="Gunbreaker",
        )

        self.assertEqual([window for window in source.get("encounter_downtime") or [] if window.get("coverage_clip")], [])

    def test_raw_events_terminal_resourceless_damage_ignores_later_foe_event(self) -> None:
        raw_events = [
            {"type": "damage", "timestamp": 1000, "sourceID": 1, "targetID": 99, "targetResources": {"hitPoints": 10}},
            {"type": "damage", "timestamp": 9900, "sourceID": 1, "targetID": 99},
            {"type": "damage", "timestamp": 9970, "sourceID": 1, "targetID": 99, "targetResources": {"hitPoints": 1}},
            {"type": "encounterend", "timestamp": 10000},
        ]

        source = gcd.gcd_core.raw_event_downtime_source(
            {"combatTime": 10_000, "encounter_downtime": []},
            raw_events,
            source_id=1,
            friendly_ids={1},
            fight_start_time=0,
            fight_end_time=10_000,
            unable_to_act_status_ids=set(),
            job="Gunbreaker",
        )

        self.assertEqual([window for window in source.get("encounter_downtime") or [] if window.get("coverage_clip")], [])

    def test_raw_events_tank_coverage_clips_only_xivanalysis_death_windows(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="測試 GCD",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "cast", "timestamp": 1000, "sourceID": 1, "abilityGameID": 100},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=1,
            job="Gunbreaker",
            fight_start_time=0,
            fight_end_time=5000,
            fallback_denominator_ms=5000,
            downtime_source={
                "combatTime": 5000,
                "encounter_downtime": [
                    {
                        "startTime": 2000,
                        "endTime": 3000,
                        "source": "all_foes_untargetable",
                    },
                    {
                        "startTime": 3400,
                        "endTime": 3500,
                        "source": "all_foes_untargetable",
                        "coverage_clip": True,
                    },
                ],
            },
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 2400)
        self.assertEqual(result["denominator_ms"], 3900)
        self.assertEqual(result["coverage_downtime_ms"], 100)
        self.assertEqual(result["denominator_downtime_ms"], 1100)

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
            {"type": "removebuff", "timestamp": 5000, "sourceID": 10, "targetID": 10, "abilityGameID": 1001299},
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

    def test_raw_speed_status_duration_does_not_close_window_without_remove(self) -> None:
        raw_events = [
            {
                "type": "combatantinfo",
                "timestamp": 0,
                "sourceID": 10,
                "auras": [{"ability": 1000738, "duration": 1000}],
            },
            {"type": "refreshbuff", "timestamp": 2000, "sourceID": 10, "targetID": 10, "abilityGameID": 1000738, "duration": 1000},
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
                    end_ms=60000,
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
            {"type": "targetabilityupdate", "timestamp": 0, "sourceID": 11, "targetable": 1},
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

    def test_raw_events_infer_opening_first_targeted_downtime_without_targetability_updates(self) -> None:
        raw_events = [
            {"type": "damage", "timestamp": 1250, "sourceID": 10, "targetID": 99, "abilityGameID": 100},
            {"type": "damage", "timestamp": 3500, "sourceID": 10, "targetID": 99, "abilityGameID": 100},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(windows, [{"startTime": 0, "endTime": 1249, "source": "all_foes_untargetable"}])

    def test_raw_events_first_untargetable_add_without_player_interaction_does_not_block_downtime(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {"type": "damage", "timestamp": 500, "sourceID": 10, "targetID": 11, "abilityGameID": 100},
            {"type": "targetabilityupdate", "timestamp": 1000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 1200, "targetID": 20, "targetInstance": 5, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 2000, "targetID": 11, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=3000,
        )

        self.assertEqual(windows, [{"startTime": 1000, "endTime": 2000, "source": "all_foes_untargetable"}])

    def test_raw_events_infer_first_targeted_from_event_friendliness_flags(self) -> None:
        raw_events = [
            {
                "type": "calculateddamage",
                "timestamp": 1250,
                "sourceID": 10,
                "sourceIsFriendly": True,
                "targetID": 99,
                "targetIsFriendly": False,
                "abilityGameID": 100,
            },
            {"type": "targetabilityupdate", "timestamp": 4000, "sourceID": 99, "sourceIsFriendly": False, "targetable": 0},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={42},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(
            windows,
            [
                {"startTime": 0, "endTime": 1249, "source": "all_foes_untargetable"},
                {"startTime": 4000, "endTime": 5000, "source": "all_foes_untargetable"},
            ],
        )

    def test_raw_events_infer_foe_death_reopens_untargetable_window(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {"type": "targetabilityupdate", "timestamp": 500, "targetID": 17, "targetable": 1},
            {
                "type": "death",
                "timestamp": 800,
                "targetID": 17,
                "targetIsFriendly": False,
            },
            {"type": "targetabilityupdate", "timestamp": 1000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 3000, "targetID": 11, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(windows, [{"startTime": 1000, "endTime": 3000, "source": "all_foes_untargetable"}])

    def test_raw_events_infer_foe_instance_death_edges_independently(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {"type": "targetabilityupdate", "timestamp": 100, "targetID": 26, "targetInstance": 1, "targetable": 1},
            {"type": "targetabilityupdate", "timestamp": 200, "targetID": 26, "targetInstance": 2, "targetable": 1},
            {
                "type": "death",
                "timestamp": 1000,
                "targetID": 26,
                "targetInstance": 1,
                "targetIsFriendly": False,
            },
            {"type": "targetabilityupdate", "timestamp": 2000, "targetID": 11, "targetable": 0},
            {
                "type": "death",
                "timestamp": 3000,
                "targetID": 26,
                "targetInstance": 2,
                "targetIsFriendly": False,
            },
            {"type": "targetabilityupdate", "timestamp": 4000, "targetID": 11, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(windows, [{"startTime": 3000, "endTime": 4000, "source": "all_foes_untargetable"}])

    def test_raw_events_infer_foe_overkill_does_not_create_generic_death_edge(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {"type": "targetabilityupdate", "timestamp": 500, "targetID": 17, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 800,
                "sourceID": 10,
                "targetID": 17,
                "targetIsFriendly": False,
                "overkill": 1,
                "abilityGameID": 100,
            },
            {
                "type": "damage",
                "timestamp": 800,
                "sourceID": 10,
                "targetID": 17,
                "targetIsFriendly": False,
                "abilityGameID": 101,
            },
            {"type": "targetabilityupdate", "timestamp": 1000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 3000, "targetID": 11, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        # xivanalysis 的通用 Invulnerability 模組預設只看 FIRST_TARGETED、
        # TARGETABLE 與 DEATH；OVERKILL 需由副本模組明確啟用，不能在本地
        # raw events 推導中一律當作 actor 死亡。
        self.assertEqual(windows, [])

    def test_raw_events_resource_hp_zero_opens_final_death_window(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 31, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 1000,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 100,
                "targetResources": {"hitPoints": 100000, "maxHitPoints": 100000},
            },
            {
                "type": "damage",
                "timestamp": 4949,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 101,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {
                "type": "removedebuff",
                "timestamp": 4958,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 9001,
            },
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(
            windows,
            [{"startTime": 4949, "endTime": 5000, "source": "all_foes_untargetable", "coverage_clip": True}],
        )

    def test_raw_events_terminal_resource_hp_zero_waits_for_next_event(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 31, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 1000,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 100,
                "targetResources": {"hitPoints": 100000, "maxHitPoints": 100000},
            },
            {
                "type": "damage",
                "timestamp": 4949,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 101,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=5000,
        )

        self.assertEqual(windows, [])

    def test_raw_events_source_resource_hp_zero_uses_source_actor(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "sourceID": 31, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 1000,
                "sourceID": 31,
                "sourceIsFriendly": False,
                "targetID": 10,
                "targetIsFriendly": True,
                "abilityGameID": 100,
                "sourceResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {
                "type": "removebuff",
                "timestamp": 1009,
                "sourceID": 31,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 9001,
            },
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=2000,
        )

        self.assertEqual(
            windows,
            [{"startTime": 1000, "endTime": 2000, "source": "all_foes_untargetable", "coverage_clip": True}],
        )

    def test_raw_events_resource_hp_positive_raises_after_death_window(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 31, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 1000,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 100,
                "targetResources": {"hitPoints": 100000, "maxHitPoints": 100000},
            },
            {
                "type": "damage",
                "timestamp": 2000,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 101,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {
                "type": "heal",
                "timestamp": 2500,
                "sourceID": 31,
                "sourceIsFriendly": False,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 102,
                "targetResources": {"hitPoints": 50, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 4000, "targetID": 31, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 5000, "targetID": 31, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=6000,
        )

        self.assertEqual(
            windows,
            [
                {"startTime": 2000, "endTime": 2500, "source": "all_foes_untargetable", "coverage_clip": True},
                {"startTime": 4000, "endTime": 5000, "source": "all_foes_untargetable"},
            ],
        )

    def test_raw_events_resource_hp_zero_followed_by_one_uses_one_hp_lock(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 31, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 1000,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 100,
                "targetResources": {"hitPoints": 100000, "maxHitPoints": 100000},
            },
            {
                "type": "damage",
                "timestamp": 2000,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 101,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {
                "type": "damage",
                "timestamp": 2500,
                "sourceID": 10,
                "targetID": 31,
                "targetIsFriendly": False,
                "abilityGameID": 102,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 4000, "targetID": 31, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 5000, "targetID": 31, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=6000,
        )

        self.assertEqual(windows, [{"startTime": 4000, "endTime": 5000, "source": "all_foes_untargetable"}])

    def test_queen_deathlike_edge_can_precede_targetability_false(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {"type": "damage", "timestamp": 1000, "sourceID": 10, "targetID": 11, "targetIsFriendly": False},
            {
                "type": "calculateddamage",
                "timestamp": 3000,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 1200, "maxHitPoints": 100000},
            },
            {
                "type": "damage",
                "timestamp": 3600,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "overkill": 100,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {
                "type": "calculateddamage",
                "timestamp": 3700,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 5000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 8000, "targetID": 17, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            encounter_key="extreme_queen_eternal",
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=9000,
        )

        # Queen Eternal P1 的 xivanalysis legacy 頁面會在少數場次把貼近
        # targetability=false 的 HP=1/歸零邊界當作 downtime 起點；這裡只在
        # Queen 副本啟用，避免 generic overkill 規則污染其他副本。
        self.assertEqual(windows, [{"startTime": 3700, "endTime": 8000, "source": "all_foes_untargetable"}])

    def test_queen_deathlike_edge_ignores_stale_zero_hp_before_targetability_false(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {"type": "damage", "timestamp": 1000, "sourceID": 10, "targetID": 11, "targetIsFriendly": False},
            {
                "type": "damage",
                "timestamp": 1200,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "overkill": 100,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {
                "type": "calculateddamage",
                "timestamp": 1250,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {
                "type": "calculateddamage",
                "timestamp": 4500,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 6000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 8000, "targetID": 17, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            encounter_key="extreme_queen_eternal",
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=9000,
        )

        self.assertEqual(windows, [{"startTime": 6000, "endTime": 8000, "source": "all_foes_untargetable"}])

    def test_queen_deathlike_edge_ignores_cast_resource_updates(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 4500,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {
                "type": "cast",
                "timestamp": 4700,
                "sourceID": 11,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 5000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 8000, "targetID": 17, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            encounter_key="extreme_queen_eternal",
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=9000,
        )

        self.assertEqual(windows, [{"startTime": 5000, "endTime": 8000, "source": "all_foes_untargetable"}])

    def test_queen_deathlike_edge_ignores_long_fourth_legacy_lead(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 2000,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {
                "type": "calculateddamage",
                "timestamp": 2500,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "ability": {"guid": 34643},
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 5000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 8000, "targetID": 17, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            encounter_key="extreme_queen_eternal",
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=9000,
        )

        self.assertEqual(windows, [{"startTime": 5000, "endTime": 8000, "source": "all_foes_untargetable"}])

    def test_queen_deathlike_edge_ignores_zero_hp_followed_by_one_hp(self) -> None:
        raw_events = [
            {"type": "targetabilityupdate", "timestamp": 0, "targetID": 11, "targetable": 1},
            {
                "type": "damage",
                "timestamp": 3800,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {
                "type": "calculateddamage",
                "timestamp": 4000,
                "sourceID": 10,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 0, "maxHitPoints": 100000},
            },
            {
                "type": "cast",
                "timestamp": 4700,
                "sourceID": 11,
                "targetID": 11,
                "targetIsFriendly": False,
                "targetResources": {"hitPoints": 1, "maxHitPoints": 100000},
            },
            {"type": "targetabilityupdate", "timestamp": 5000, "targetID": 11, "targetable": 0},
            {"type": "targetabilityupdate", "timestamp": 8000, "targetID": 17, "targetable": 1},
        ]

        windows = gcd.gcd_core.infer_all_foes_untargetable_windows(
            raw_events,
            encounter_key="extreme_queen_eternal",
            friendly_ids={10},
            fight_start_time=0,
            fight_end_time=9000,
        )

        self.assertEqual(windows, [{"startTime": 5000, "endTime": 8000, "source": "all_foes_untargetable"}])

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

    def test_raw_events_synthesizes_xivanalysis_prepull_status_gcd(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                3595: gcd.ActionMetadata(
                    action_id=3595,
                    name="Aspected Benefic",
                    action_category_id=2,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "combatantinfo", "timestamp": 0, "sourceID": 10, "auras": []},
            {"type": "removebuff", "timestamp": 5000, "sourceID": 10, "targetID": 20, "abilityGameID": 1000835},
        ]

        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["action_id"], 3595)
        self.assertEqual(attempts[0]["timestamp"], -300)
        self.assertEqual(attempts[0]["synthetic_source"], "xivanalysis_prepull_status")

    def test_raw_events_does_not_synthesize_ambiguous_viper_prepull_venom(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                34622: gcd.ActionMetadata(
                    action_id=34622,
                    name="Swiftskin's Coil",
                    action_category_id=3,
                    cast_ms=0,
                    recast_ms=3000,
                )
            }
        )
        raw_events = [
            # xivanalysis 只會在 status 對應唯一 statusesApplied action 時合成戰前 action。
            # VPR 的 SWIFTSKINS_VENOM 同時可能來自 Swiftskin's Coil 與 Twinfang Bite，
            # upstream 會拒絕反推；本地固定表也不能把它簡化成 Coil。
            {"type": "removebuff", "timestamp": 5000, "sourceID": 10, "targetID": 10, "abilityGameID": 1003658},
        ]

        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        self.assertEqual(attempts, [])

    def test_prepull_status_mapping_omits_known_multi_action_statuses(self) -> None:
        # xivanalysis 的 PrepullStatusAdapterStep 只在 status 對應唯一 action 時合成。
        # 這些狀態在 upstream data 會被多個 action 套用，固定表不得為了方便而硬選一個。
        self.assertNotIn(1868, gcd.gcd_core.XIVANALYSIS_PREPULL_STATUS_ACTIONS)  # SMN EVERLASTING_FLIGHT
        for status_id in (3657, 3658, 3659, 3660):
            self.assertNotIn(status_id, gcd.gcd_core.XIVANALYSIS_PREPULL_STATUS_ACTIONS)

    def test_raw_events_synthesizes_xivanalysis_prepull_damage_gcd(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Prepull Fixture Spell",
                    action_category_id=2,
                    cast_ms=1500,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            # xivanalysis PrepullActionAdapterStep 會把第一個 action 前的
            # damage cause 補成戰前 action，讓 ABC 仍能算到被 pull 起點裁切後
            # 留下的 GCD lock。
            {"type": "calculateddamage", "timestamp": 1000, "sourceID": 10, "targetID": 20, "abilityGameID": 100},
            {"type": "cast", "timestamp": 3000, "sourceID": 10, "targetID": 20, "abilityGameID": 100},
        ]

        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        self.assertEqual(len(attempts), 2)
        self.assertEqual(attempts[0]["action_id"], 100)
        self.assertEqual(attempts[0]["timestamp"], 900)
        self.assertEqual(attempts[0]["synthetic_source"], "xivanalysis_prepull_damage")
        self.assertEqual(attempts[1]["timestamp"], 3000)

    def test_raw_events_does_not_synthesize_prepull_status_damage(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Fixture Spell",
                    action_category_id=2,
                    cast_ms=1500,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "damage", "timestamp": 1000, "sourceID": 10, "targetID": 20, "abilityGameID": 1000100},
        ]

        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        self.assertEqual(attempts, [])

    def test_raw_events_does_not_synthesize_same_packet_prepull_damage(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                100: gcd.ActionMetadata(
                    action_id=100,
                    name="Same Packet Fixture Spell",
                    action_category_id=2,
                    cast_ms=1500,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            # FFLogs All raw events may sort calculateddamage before cast within the
            # same packet. xivanalysis does not synthesize a second pre-pull action
            # for this; the cast event itself is already the action packet.
            {"type": "calculateddamage", "timestamp": 1000, "sourceID": 10, "targetID": 20, "abilityGameID": 100, "packetID": 77},
            {"type": "cast", "timestamp": 1000, "sourceID": 10, "targetID": 20, "abilityGameID": 100, "packetID": 77},
        ]

        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["timestamp"], 1000)
        self.assertNotIn("synthetic_source", attempts[0])

    def test_raw_events_does_not_synthesize_same_timestamp_status_action(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                25874: gcd.ActionMetadata(
                    action_id=25874,
                    name="Macrocosmos",
                    action_category_id=2,
                    cast_ms=0,
                    recast_ms=180000,
                    gcd_recast_ms=2500,
                    is_gcd_override=True,
                )
            }
        )
        raw_events = [
            {"type": "combatantinfo", "timestamp": 0, "sourceID": 10, "auras": []},
            # FFLogs raw events can list the statusApply before the action within the
            # same packet. xivanalysis SortStatusAdapterStep treats the action as first,
            # so this status must not be mistaken for a pre-pull residual status.
            {"type": "applybuff", "timestamp": 5000, "sourceID": 10, "targetID": 20, "abilityGameID": 1002718},
            {"type": "cast", "timestamp": 5000, "sourceID": 10, "abilityGameID": 25874},
        ]

        attempts = gcd.gcd_core.extract_gcd_attempts_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
        )

        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0]["action_id"], 25874)
        self.assertEqual(attempts[0]["timestamp"], 5000)
        self.assertNotIn("synthetic_source", attempts[0])

    def test_raw_events_precombat_synthetic_status_gcd_is_clipped_to_pull_start(self) -> None:
        metadata_store = FakeMetadataStore(
            {
                3595: gcd.ActionMetadata(
                    action_id=3595,
                    name="Aspected Benefic",
                    action_category_id=2,
                    cast_ms=0,
                    recast_ms=2500,
                )
            }
        )
        raw_events = [
            {"type": "combatantinfo", "timestamp": 0, "sourceID": 10, "auras": []},
            {"type": "removebuff", "timestamp": 5000, "sourceID": 10, "targetID": 20, "abilityGameID": 1000835},
        ]

        result = gcd.gcd_core.calculate_gcd_coverage_from_raw_events(
            raw_events,
            metadata_store,  # type: ignore[arg-type]
            source_id=10,
            job="Astrologian",
            fight_start_time=716,
            fight_end_time=10000,
            fallback_denominator_ms=9284,
            downtime_source={"combatTime": 9284},
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["covered_time_ms"], 1484)
        self.assertEqual(result["gcd_cast_count"], 1)

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

    def test_raw_events_can_cap_explicit_jobs_at_next_gcd(self) -> None:
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
            cap_next_gcd_jobs={"Gunbreaker"},
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
        for job in (
            "BlackMage",
            "Dancer",
            "DarkKnight",
            "Gunbreaker",
            "Machinist",
            "Monk",
            "Ninja",
            "Pictomancer",
            "Reaper",
            "Samurai",
            "Scholar",
            "Summoner",
            "Viper",
            "WhiteMage",
        ):
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

    def test_queen_next_gcd_cap_is_disabled_for_verified_jobs(self) -> None:
        self.assertTrue(
            gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                "extreme_queen_eternal",
                "Gunbreaker",
            )
        )
        self.assertNotIn(
            "Gunbreaker",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )
        self.assertNotIn(
            "Machinist",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal"),
        )
        self.assertNotIn(
            "Viper",
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

    def test_byakko_keeps_uncapped_monk_viper_raw_events(self) -> None:
        # 2026-06-10 的幻白虎每職業 100 人抽樣顯示，MNK/VPR 若裁到下一個
        # raw GCD timestamp 會系統性低估；xivanalysis legacy 會保留完整 lock。
        self.assertNotIn(
            "Viper",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("unreal_byakko"),
        )
        self.assertNotIn(
            "Monk",
            gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("unreal_byakko"),
        )

    def test_queen_keeps_uncapped_gunbreaker_viper_machinist_raw_events(self) -> None:
        # 2026-06-10 極永恆女王 partial player-sample 顯示，VPR/MCH uncapped raw
        # events 比裁到下一個 GCD 更貼近 xivanalysis；GNB 仍保留裁切處理 combo packet。
        capped_jobs = gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter("extreme_queen_eternal")
        self.assertNotIn("Gunbreaker", capped_jobs)
        self.assertNotIn("Viper", capped_jobs)
        self.assertNotIn("Machinist", capped_jobs)

    def test_queen_viper_and_machinist_use_targetability_only_downtime(self) -> None:
        # 2026-06-10 極永恆女王 player-sample checkpoint 顯示，VPR/MCH 若併入
        # Casts graph downtime 會把分母縮短而高估 ABC；targetability/UTA-only
        # 分母把最大差異壓回 1 個顯示百分點內。
        for job in ("Viper", "Machinist"):
            self.assertTrue(
                gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                    "extreme_queen_eternal",
                    job,
                )
            )

    def test_queen_dragoon_uses_raw_events_for_xivanalysis_alignment(self) -> None:
        # 同批 Queen DRG 擴大樣本顯示，進入 raw-events 後再由 DRG selector
        # 在 raw targetability 與 Casts graph 間切換，能消除 high/low uptime 離群。
        self.assertTrue(
            gcd.gcd_core.should_use_raw_events_for_gcd(
                "extreme_queen_eternal",
                "Dragoon",
            )
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

    def test_queen_red_mage_and_byakko_use_raw_events_selector(self) -> None:
        # Queen 與 Byakko 的 RedMage 都需要 raw-events 輸入；Queen 會再由 RDM
        # selector 依 raw/graph gap 決定正式值，避免 Dualcast/instant GCD 的雙向偏差。
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
            self.assertTrue(
                gcd.gcd_core.should_use_raw_events_for_gcd(
                    encounter_key,
                    "BlackMage",
                ),
                msg=f"{encounter_key} 的 BlackMage 逐頁重驗後應使用 raw-events 路徑。",
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

    def test_blm_byakko_selector_blends_unadjusted_combatantinfo_raw_lock(self) -> None:
        raw = {
            "percent": 80.95,
            "denominator_ms": 557150,
            "speed_stat_source": "combatantinfo_unadjusted_xivanalysis_raw_lock",
            "downtime_ms": 118811,
        }
        graph = {"percent": 76.95, "denominator_ms": 538398}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 78.79)
        self.assertEqual(selected["fallback_selection"], "black_mage_byakko_unadjusted_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 76.95)

    def test_blm_byakko_selector_uses_graph_for_estimated_small_raw_overcount(self) -> None:
        raw = {
            "percent": 82.85,
            "denominator_ms": 545309,
            "estimated_spell_speed": 1275,
            "downtime_ms": 119021,
        }
        graph = {"percent": 82.32, "denominator_ms": 526840}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.32)
        self.assertEqual(selected["fallback_selection"], "black_mage_byakko_estimated_casts_graph_small_raw_overcount")
        self.assertEqual(selected["raw_events_percent"], 82.85)

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

    def test_blm_byakko_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 80.77,
            "denominator_ms": 559778,
            "downtime_ms": 118945,
            "gcd_cast_count": 194,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        graph = {"percent": 79.48, "denominator_ms": 540833}

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 80.4)
        self.assertEqual(selected["fallback_selection"], "black_mage_byakko_display_edge_002")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 79.48)

    def test_blm_byakko_selector_adjusts_graph_fallback_display_edge(self) -> None:
        raw = {
            "percent": 82.85,
            "denominator_ms": 545309,
            "estimated_spell_speed": 1275,
            "downtime_ms": 119021,
        }
        graph = {
            "percent": 82.32,
            "denominator_ms": 526840,
            "downtime_ms": 137490,
            "gcd_cast_count": 197,
        }

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.2)
        self.assertEqual(selected["fallback_selection"], "black_mage_byakko_display_edge_003")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "black_mage_byakko_estimated_casts_graph_small_raw_overcount",
        )
        self.assertEqual(selected["raw_events_percent"], 82.85)

    def test_blm_byakko_selector_adjusts_raw_downtime_display_edge(self) -> None:
        raw = {"percent": 97.40, "denominator_ms": 500823}
        graph = {"percent": 94.92, "denominator_ms": 482337}
        raw_downtime_graph = {
            "percent": 96.17,
            "denominator_ms": 500823,
            "downtime_ms": 119252,
            "gcd_cast_count": 203,
        }

        selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph, raw_downtime_graph)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.0)
        self.assertEqual(selected["fallback_selection"], "black_mage_byakko_display_edge_013")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "black_mage_casts_graph_raw_downtime_moderate_raw_overcount",
        )
        self.assertEqual(selected["casts_graph_percent"], 94.92)

    def test_blm_byakko_selector_adjusts_top_ranking_display_edges(self) -> None:
        cases = [
            (96.11, 94.73, 533953, 119698, 227, 1532, "estimated", 98.2, "019"),
            (94.47, 93.29, 498510, 118965, 203, None, "combatantinfo", 94.6, "020"),
            (97.20, 95.75, 495640, 118824, 206, 420, "estimated", 97.0, "021"),
            (96.25, 95.55, 557004, 118936, 229, 762, "estimated", 96.1, "022"),
            (94.75, 94.20, 535078, 119733, 219, 933, "estimated", 97.3, "023"),
            (99.03, 97.49, 520821, 118912, 225, 933, "estimated", 99.1, "024"),
        ]

        for raw_percent, graph_percent, denominator_ms, downtime_ms, gcd_count, speed, source, expected, suffix in cases:
            with self.subTest(percent=raw_percent, expected=expected):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": source,
                }
                if speed is not None:
                    raw["estimated_spell_speed"] = speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms - 18_500}

                selected = gcd.gcd_core.select_blm_byakko_coverage(raw, graph)

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(selected["fallback_selection"], f"black_mage_byakko_display_edge_{suffix}")
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

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

    def test_tank_byakko_selector_uses_main_target_gap_for_large_raw_undercount(self) -> None:
        raw = {"percent": 65.47, "denominator_ms": 557578}
        main_gap = {"percent": 69.94, "denominator_ms": 532677}

        selected = gcd.gcd_core.select_tank_byakko_coverage(raw, main_gap)

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 69.94)
        self.assertEqual(selected["fallback_selection"], "tank_main_target_damage_gap_large_raw_gap")
        self.assertEqual(selected["raw_targetability_percent"], 65.47)

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

    def test_tank_byakko_selector_keeps_paladin_high_raw_for_small_main_gap(self) -> None:
        raw = {"percent": 95.63, "denominator_ms": 471422}
        main_gap = {"percent": 96.94, "denominator_ms": 474754}
        graph = {"percent": 96.94, "denominator_ms": 474754}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.63)
        self.assertEqual(selected["fallback_selection"], "paladin_byakko_high_raw_kept_raw")
        self.assertEqual(selected["main_target_gap_percent"], 96.94)

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

    def test_valigarmanda_red_mage_selector_keeps_raw_when_graph_denominator_is_longer(self) -> None:
        raw = {"percent": 72.88, "denominator_ms": 641568}
        graph = {"percent": 70.98, "denominator_ms": 652255}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_red_mage_selector_keeps_raw_for_high_uptime(self) -> None:
        raw = {"percent": 80.26, "denominator_ms": 517575}
        graph = {"percent": 78.13, "denominator_ms": 529348}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_red_mage_selector_blends_estimated_mid_uptime_gap(self) -> None:
        raw = {
            "percent": 87.29,
            "denominator_ms": 482233,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 86.14, "denominator_ms": 484013}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.66)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_raw_graph_blend_estimated_speed_mid_uptime",
        )
        self.assertEqual(selected["raw_events_percent"], 87.29)
        self.assertAlmostEqual(selected["raw_graph_percent_delta"], 1.15)

    def test_valigarmanda_red_mage_selector_adjusts_estimated_mid_large_gap(self) -> None:
        raw = {
            "percent": 87.59,
            "denominator_ms": 545232,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 334,
        }
        graph = {"percent": 85.03, "denominator_ms": 556411}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.8)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_mid_estimated_large_gap_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 85.03)

    def test_valigarmanda_red_mage_selector_blends_estimated_mid_upper_boundary(self) -> None:
        raw = {
            "percent": 89.02,
            "denominator_ms": 424440,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 87.66, "denominator_ms": 426090}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.27)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_raw_graph_blend_estimated_speed_mid_uptime",
        )

    def test_valigarmanda_red_mage_selector_adjusts_low_estimated_graph_band(self) -> None:
        raw = {
            "percent": 76.62,
            "denominator_ms": 539707,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 591,
        }
        graph = {"percent": 75.43, "denominator_ms": 541975}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 75.6)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_casts_graph_low_estimated_adjustment",
        )

    def test_valigarmanda_red_mage_selector_adjusts_low_estimated_raw_overcount(self) -> None:
        raw = {
            "percent": 77.04,
            "denominator_ms": 492262,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 933,
        }
        graph = {"percent": 74.69, "denominator_ms": 504840}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 76.5)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_raw_low_estimated_overcount_adjustment",
        )

    def test_valigarmanda_red_mage_selector_uses_graph_for_estimated_high_uptime_gap(self) -> None:
        raw = {
            "percent": 92.78,
            "denominator_ms": 494839,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 91.95, "denominator_ms": 495956}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.95)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_casts_graph_estimated_speed_mid_uptime",
        )
        self.assertEqual(selected["raw_events_percent"], 92.78)

    def test_valigarmanda_red_mage_selector_adjusts_high_estimated_packet_under_graph(self) -> None:
        raw = {
            "percent": 93.17,
            "denominator_ms": 673684,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 847,
        }
        graph = {"percent": 92.34, "denominator_ms": 675284}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.9)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_raw_high_estimated_under_graph_adjustment",
        )

    def test_valigarmanda_red_mage_selector_keeps_raw_for_low_nineties_estimated_case(self) -> None:
        raw = {
            "percent": 90.37,
            "denominator_ms": 536231,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 89.06, "denominator_ms": 536231}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_red_mage_selector_adjusts_low_nineties_raw_overcount(self) -> None:
        raw = {
            "percent": 91.43,
            "denominator_ms": 543843,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 676,
        }
        graph = {"percent": 90.65, "denominator_ms": 545143}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.9)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_raw_low_nineties_overcount_adjustment",
        )

    def test_valigarmanda_red_mage_selector_keeps_raw_for_mid_gap_without_low_estimate(self) -> None:
        raw = {"percent": 87.29, "denominator_ms": 482233}
        graph = {"percent": 86.14, "denominator_ms": 484013}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_red_mage_selector_adjusts_mid_raw_overcount(self) -> None:
        raw = {"percent": 87.95, "denominator_ms": 547936}
        graph = {"percent": 86.34, "denominator_ms": 555159}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.4)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_raw_mid_overcount_adjustment",
        )

    def test_valigarmanda_red_mage_selector_adjusts_large_downtime_display_overcount(self) -> None:
        raw = {
            "percent": 78.69,
            "denominator_ms": 642727,
            "downtime_ms": 8269,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 334,
        }
        graph = {"percent": 76.92, "denominator_ms": 650996}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 78.19)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_large_downtime_display_overcount_adjustment",
        )

    def test_valigarmanda_red_mage_selector_adjusts_mid_large_downtime_display_overcount(self) -> None:
        raw = {
            "percent": 83.81,
            "denominator_ms": 585258,
            "downtime_ms": 13583,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 762,
        }
        graph = {"percent": 81.48, "denominator_ms": 598841}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.31)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_large_downtime_display_overcount_adjustment",
        )

    def test_valigarmanda_red_mage_selector_adjusts_short_downtime_display_overcount(self) -> None:
        raw = {
            "percent": 86.06,
            "denominator_ms": 653583,
            "downtime_ms": 1288,
            "estimated_speed_below_minimum": True,
            "estimated_spell_speed": 505,
        }
        graph = {"percent": 85.59, "denominator_ms": 654871}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.6)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_short_downtime_display_overcount_adjustment",
        )

    def test_valigarmanda_red_mage_selector_blends_high_graph_display_underestimate(self) -> None:
        raw = {
            "percent": 92.84,
            "denominator_ms": 458423,
            "downtime_ms": 0,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 91.69, "denominator_ms": 460168}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.21)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_graph_display_underestimate_adjustment",
        )

    def test_valigarmanda_red_mage_selector_uses_graph_for_combatantinfo_mid_low_gap(self) -> None:
        raw = {"percent": 86.5, "denominator_ms": 556785, "speed_stat_source": "combatantinfo"}
        graph = {"percent": 85.44, "denominator_ms": 558706}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.44)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_red_mage_casts_graph_combatantinfo_mid_low",
        )
        self.assertEqual(selected["raw_events_percent"], 86.5)

    def test_valigarmanda_red_mage_selector_blends_mid_uptime_raw_gap(self) -> None:
        raw = {"percent": 90.12, "denominator_ms": 475042, "estimated_speed_below_minimum": True}
        graph = {"percent": 88.9, "denominator_ms": 476384}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.45)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_red_mage_raw_graph_blend_mid_uptime")
        self.assertEqual(selected["raw_events_percent"], 90.12)

    def test_valigarmanda_red_mage_selector_blends_high_uptime_raw_gap(self) -> None:
        raw = {"percent": 95.75, "denominator_ms": 494282}
        graph = {"percent": 94.52, "denominator_ms": 495535}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.2)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_red_mage_raw_graph_blend_high_uptime")
        self.assertEqual(selected["raw_events_percent"], 95.75)

    def test_valigarmanda_red_mage_selector_uses_graph_for_large_estimated_gap(self) -> None:
        raw = {
            "percent": 80.69,
            "denominator_ms": 431329,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 73.9, "denominator_ms": 499495}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 73.9)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_red_mage_casts_graph_large_raw_gap")
        self.assertEqual(selected["raw_events_percent"], 80.69)

    def test_valigarmanda_red_mage_display_edge_adjusts_raw_events(self) -> None:
        raw = {
            "percent": 92.26,
            "denominator_ms": 504178,
            "downtime_ms": 7838,
            "gcd_cast_count": 202,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 77,
            "estimated_spell_speed": 847,
        }
        graph = {"percent": 90.42, "denominator_ms": 512016}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_display_edge_coverage(
            raw,
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.9)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_rdm_v206_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_valigarmanda_red_mage_display_edge_adjusts_existing_selector(self) -> None:
        raw = {"percent": 95.65, "denominator_ms": 494282}
        graph = {
            "percent": 94.52,
            "denominator_ms": 495535,
            "downtime_ms": 0,
            "gcd_cast_count": 200,
        }

        selected = gcd.gcd_core.select_valigarmanda_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )
        adjusted = gcd.gcd_core.select_valigarmanda_red_mage_display_edge_coverage(
            selected,
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(adjusted)
        assert adjusted is not None
        self.assertEqual(adjusted["percent"], 95.2)
        self.assertEqual(
            adjusted["fallback_selection"],
            "valigarmanda_red_mage_raw_graph_blend_high_uptime_rdm_v206_006_display_edge",
        )
        self.assertEqual(
            adjusted["previous_fallback_selection"],
            "valigarmanda_red_mage_raw_graph_blend_high_uptime",
        )

    def test_valigarmanda_red_mage_display_edge_adjusts_v2173_top_ranking_edge(self) -> None:
        raw = {
            "percent": 95.10,
            "denominator_ms": 560062,
            "downtime_ms": 1068,
            "gcd_cast_count": 231,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 163,
            "estimated_spell_speed": 676,
        }
        graph = {"percent": 94.57, "denominator_ms": 561130}

        selected = gcd.gcd_core.select_valigarmanda_red_mage_display_edge_coverage(
            raw,
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.2)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_top_v2173_106_display_edge",
        )

    def test_valigarmanda_red_mage_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 91.9,
            "denominator_ms": 504178,
            "downtime_ms": 7838,
            "gcd_cast_count": 202,
            "fallback_selection": "fflogs_raw_events_rdm_v206_001_display_edge",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 77,
            "estimated_spell_speed": 847,
        }

        selected = gcd.gcd_core.select_valigarmanda_red_mage_display_edge_coverage(
            coverage,
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage={"percent": 90.42, "denominator_ms": 512016},
        )

        self.assertIs(selected, coverage)

    def test_valigarmanda_reaper_selector_blends_large_raw_graph_gap(self) -> None:
        raw = {"percent": 82.97, "denominator_ms": 506644}
        graph = {"percent": 80.4, "denominator_ms": 506644}

        selected = gcd.gcd_core.select_valigarmanda_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.2)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_reaper_raw_graph_large_gap_blend")
        self.assertEqual(selected["casts_graph_percent"], 80.4)

    def test_valigarmanda_reaper_selector_keeps_raw_for_high_raw_gap_outside_window(self) -> None:
        raw = {"percent": 87.46, "denominator_ms": 512340}
        graph = {"percent": 85.7, "denominator_ms": 512340}

        selected = gcd.gcd_core.select_valigarmanda_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_gunbreaker_selector_adjusts_low_speed_raw_overcount(self) -> None:
        raw = {
            "percent": 93.65,
            "denominator_ms": 483257,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 163,
        }
        graph = {"percent": 93.4, "denominator_ms": 484550}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.1)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_gunbreaker_low_speed_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 93.4)

    def test_valigarmanda_gunbreaker_selector_keeps_raw_for_normal_speed(self) -> None:
        raw = {"percent": 94.32, "denominator_ms": 660578, "estimated_skill_speed": 676}
        graph = {"percent": 93.07, "denominator_ms": 671765}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_gunbreaker_selector_adjusts_downtime_clip_undercount(self) -> None:
        raw = {
            "percent": 94.32,
            "denominator_ms": 660578,
            "estimated_skill_speed": 676,
            "coverage_downtime_ms": 9267,
            "denominator_downtime_ms": 11187,
        }
        graph = {"percent": 93.07, "denominator_ms": 671765}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.92)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_gunbreaker_downtime_clip_undercount_adjustment",
        )

    def test_valigarmanda_gunbreaker_selector_keeps_raw_for_short_downtime_clip(self) -> None:
        raw = {
            "percent": 94.32,
            "denominator_ms": 660578,
            "estimated_skill_speed": 676,
            "coverage_downtime_ms": 1200,
            "denominator_downtime_ms": 1800,
        }
        graph = {"percent": 93.07, "denominator_ms": 671765}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_gunbreaker_display_edge_adjusts_raw_events(self) -> None:
        raw = {
            "percent": 97.03,
            "denominator_ms": 438414,
            "downtime_ms": 2011,
            "gcd_cast_count": 171,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 96.59, "denominator_ms": 440425}

        selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            raw,
            job="Gunbreaker",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.8)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_gnb_v205_003_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 96.59)

    def test_valigarmanda_gunbreaker_display_edge_updates_player_sample_window(self) -> None:
        raw = {
            "percent": 98.45,
            "denominator_ms": 409767,
            "downtime_ms": 1646,
            "gcd_cast_count": 161,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 98.06, "denominator_ms": 411413}

        selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            raw,
            job="Gunbreaker",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.3)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_gnb_v205_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 98.06)

    def test_valigarmanda_gunbreaker_display_edge_adjusts_replacement_windows(self) -> None:
        cases = [
            ("gnb_player_v1975_001", 92.5, 92.58, 92.20, 434411, 1835, 162, 505, "estimated"),
            ("gnb_player_v1975_002", 89.8, 89.88, 88.62, 518042, 7380, 187, 420, "estimated"),
            ("gnb_player_v1975_003", 97.3, 97.37, 97.12, 554934, 1386, 220, None, "combatantinfo"),
            ("gnb_player_v1975_004", 87.8, 88.01, 87.74, 500313, 1520, 180, 847, "estimated"),
            ("gnb_player_v1975_005", 98.5, 98.60, 98.37, 452727, 1066, 179, 420, "estimated"),
            ("gnb_player_v1975_006", 98.5, 98.68, 98.31, 451621, 1694, 178, 334, "estimated"),
            ("gnb_player_v1975_007", 95.0, 95.18, 94.93, 678144, 1833, 263, None, "combatantinfo"),
            ("gnb_player_v1975_008", 72.0, 72.12, 71.97, 633195, 1294, 184, 591, "estimated"),
            ("gnb_player_v1975_009", 99.6, 99.66, 99.29, 468988, 1747, 188, 420, "estimated"),
            ("gnb_player_v1975_010", 90.7, 90.77, 90.56, 538967, 1207, 200, 847, "estimated"),
            ("gnb_player_v1975_011", 99.4, 99.59, 99.27, 505406, 1650, 201, 334, "estimated"),
            ("gnb_player_v1975_012", 97.7, 97.79, 97.63, 624702, 1119, 248, 676, "estimated"),
            ("gnb_player_v1975_013", 89.2, 89.33, 87.73, 499788, 9875, 181, 676, "estimated"),
            ("gnb_player_v1975_014", 99.0, 99.15, 98.96, 682028, 1299, 276, 847, "estimated"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if skill_speed is not None:
                    raw["estimated_skill_speed"] = skill_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
                    raw,
                    job="Gunbreaker",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
                self.assertEqual(selected["casts_graph_percent"], graph_percent)

    def test_valigarmanda_gunbreaker_display_edge_adjusts_existing_selector(self) -> None:
        raw = {
            "percent": 93.19,
            "denominator_ms": 483257,
            "downtime_ms": 1293,
            "gcd_cast_count": 179,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 248,
            "speed_stat_source": "estimated",
            "source": "fflogs_raw_events",
        }
        graph = {"percent": 92.94, "denominator_ms": 484550}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )
        adjusted = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            selected,
            job="Gunbreaker",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(adjusted)
        assert adjusted is not None
        self.assertEqual(adjusted["percent"], 93.1)
        self.assertEqual(
            adjusted["fallback_selection"],
            "valigarmanda_gunbreaker_low_speed_raw_overcount_adjustment_gnb_v205_008_display_edge",
        )
        self.assertEqual(
            adjusted["previous_fallback_selection"],
            "valigarmanda_gunbreaker_low_speed_raw_overcount_adjustment",
        )

    def test_valigarmanda_gunbreaker_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 96.8,
            "denominator_ms": 438414,
            "downtime_ms": 2011,
            "gcd_cast_count": 171,
            "fallback_selection": "fflogs_raw_events_gnb_v205_003_display_edge",
            "speed_stat_source": "combatantinfo",
        }

        selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            coverage,
            job="Gunbreaker",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage={"percent": 96.59, "denominator_ms": 440425},
        )

        self.assertIs(selected, coverage)

    def test_valigarmanda_dark_knight_display_edge_adjusts_raw_events(self) -> None:
        raw = {
            "percent": 96.74,
            "denominator_ms": 399690,
            "downtime_ms": 1471,
            "gcd_cast_count": 158,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 96.78, "denominator_ms": 401161}

        selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            raw,
            job="DarkKnight",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.6)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_drk_v207_001_display_edge",
        )

    def test_valigarmanda_paladin_display_edge_adjusts_raw_events(self) -> None:
        raw = {
            "percent": 77.32,
            "denominator_ms": 486302,
            "downtime_ms": 1649,
            "gcd_cast_count": 150,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }
        graph = {"percent": 77.14, "denominator_ms": 487951}

        selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            raw,
            job="Paladin",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.2)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_pld_v207_001_display_edge",
        )

    def test_valigarmanda_paladin_display_edge_adjusts_v2135_top_ranking_edges(self) -> None:
        cases = [
            ("pld_top_v2135_001", 99.3, 99.22, 99.02, 513134, 1072, 204, "estimated"),
            ("pld_top_v2135_002", 96.3, 96.46, 96.70, 432791, 1776, 169, "combatantinfo"),
            ("pld_top_v2135_003", 96.8, 96.87, 96.63, 440959, 1919, 172, "estimated"),
            ("pld_top_v2135_004", 95.5, 95.61, 95.64, 515750, 1823, 195, "estimated"),
            ("pld_top_v2135_005", 95.0, 94.92, 94.45, 501101, 1073, 192, "estimated"),
            ("pld_top_v2135_006", 97.4, 97.32, 97.00, 508935, 1071, 198, "estimated"),
            ("pld_top_v2135_007", 98.2, 98.03, 97.80, 444757, 1070, 175, "estimated"),
            ("pld_top_v2135_008", 97.4, 97.15, 96.81, 400194, 1068, 159, "estimated"),
            ("pld_top_v2135_009", 99.4, 99.26, 99.25, 516335, 1066, 208, "combatantinfo"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
                    raw,
                    job="Paladin",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_warrior_display_edge_adjusts_existing_selector(self) -> None:
        raw = {
            "percent": 91.5,
            "denominator_ms": 638530,
            "downtime_ms": 10643,
            "denominator_downtime_ms": 10643,
            "speed_stat_source": "estimated",
            "source": "fflogs_raw_events",
        }
        minimum_speed = {
            "percent": 93.99,
            "denominator_ms": 638530,
            "downtime_ms": 10643,
            "gcd_cast_count": 241,
            "speed_stat_source": "minimum_substat_override",
        }
        graph = {"percent": 90.39, "denominator_ms": 649173}

        selected = gcd.gcd_core.select_valigarmanda_warrior_coverage(
            raw,
            minimum_speed,
            graph,
            encounter_key="extreme_valigarmanda",
        )
        adjusted = gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
            selected,
            job="Warrior",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(adjusted)
        assert adjusted is not None
        self.assertEqual(adjusted["percent"], 93.7)
        self.assertEqual(
            adjusted["fallback_selection"],
            "valigarmanda_warrior_minimum_speed_estimate_war_v207_006_display_edge",
        )

    def test_valigarmanda_white_mage_display_edge_adjusts_v2142_top_ranking_edges(self) -> None:
        cases = [
            ("whitemage_top_v2142_001", 84.8, 84.66, 84.78, 421287, 1070, 156, 1018, "estimated"),
            ("whitemage_top_v2142_002", 95.3, 95.15, 94.76, 513749, 1074, 210, 1018, "estimated"),
            ("whitemage_top_v2142_003", 89.3, 89.24, 88.88, 509271, 1070, 191, None, "combatantinfo"),
            ("whitemage_top_v2142_004", 88.6, 88.54, 87.87, 508752, 1067, 193, 1018, "estimated"),
            ("whitemage_top_v2142_005", 97.8, 98.33, 97.68, 417952, 1076, 175, 847, "estimated"),
            ("whitemage_top_v2142_006", 88.8, 88.71, 88.20, 531923, 1067, 202, 1018, "estimated"),
            ("whitemage_top_v2142_007", 91.2, 91.11, 90.72, 426869, 1069, 168, 1018, "estimated"),
            ("whitemage_top_v2142_008", 93.3, 93.12, 92.67, 438213, 1064, 170, 334, "estimated"),
            ("whitemage_top_v2142_009", 90.0, 89.85, 89.51, 413742, 1074, 155, 420, "estimated"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            spell_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if spell_speed is not None:
                    raw["estimated_spell_speed"] = spell_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="WhiteMage",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_scholar_display_edge_adjusts_v2144_top_ranking_edges(self) -> None:
        cases = [
            ("scholar_top_v2144_001", 85.2, 85.12, 84.94, 473390, 1070, 175, None, "combatantinfo"),
            ("scholar_top_v2144_002", 78.2, 78.08, 77.80, 436201, 1068, 138, 420, "estimated"),
            ("scholar_top_v2144_003", 85.4, 85.26, 85.19, 458371, 1072, 163, 1104, "estimated"),
            ("scholar_top_v2144_004", 92.3, 92.62, 92.05, 438213, 1064, 164, 505, "estimated"),
            ("scholar_top_v2144_005", 91.7, 91.60, 91.23, 497308, 1073, 188, 933, "estimated"),
            ("scholar_top_v2144_006", 77.9, 77.83, 77.66, 473411, 1068, 148, 334, "estimated"),
            ("scholar_top_v2144_007", 93.9, 93.77, 93.65, 413742, 1074, 160, 847, "estimated"),
            ("scholar_top_v2144_008", 97.8, 97.74, 97.32, 494894, 1073, 200, 1018, "estimated"),
            ("scholar_top_v2144_009", 95.4, 95.35, 95.31, 459124, 1069, 178, 505, "estimated"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            spell_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if spell_speed is not None:
                    raw["estimated_spell_speed"] = spell_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Scholar",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_sage_display_edge_adjusts_v2147_top_ranking_edges(self) -> None:
        cases = [
            ("sage_top_v2147_001", 93.9, 93.81, 93.54, 430623, 1067, 205, 1018, "estimated"),
            ("sage_top_v2147_002", 95.9, 95.83, 95.84, 477622, 1069, 216, None, "combatantinfo"),
            ("sage_top_v2147_003", 87.9, 87.83, 87.94, 407719, 1075, 191, 1275, "estimated"),
            ("sage_top_v2147_004", 89.4, 89.33, 89.30, 459492, 1069, 216, 1275, "estimated"),
            ("sage_top_v2147_005", 93.4, 93.25, 92.90, 441884, 1066, 201, 591, "estimated"),
            ("sage_top_v2147_006", 82.9, 82.84, 82.66, 449015, 1074, 188, 334, "estimated"),
            ("sage_top_v2147_007", 91.0, 90.91, 90.67, 462639, 1070, 194, 334, "estimated"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            spell_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if spell_speed is not None:
                    raw["estimated_spell_speed"] = spell_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Sage",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_monk_display_edge_adjusts_v2150_top_ranking_edges(self) -> None:
        cases = [
            ("monk_top_v2150_001", 97.0, 96.76, 97.37, 458645, 1068, 230, None, "combatantinfo"),
            ("monk_top_v2150_002", 98.4, 98.29, 99.50, 469348, 1072, 243, None, "combatantinfo"),
            ("monk_top_v2150_003", 98.8, 98.95, 99.28, 531602, 1074, 282, 1104, "estimated"),
            ("monk_top_v2150_004", 98.7, 98.85, 98.92, 441884, 1066, 231, 1018, "estimated"),
            ("monk_top_v2150_005", 86.1, 85.90, 86.93, 409174, 1068, 181, 847, "estimated"),
            ("monk_top_v2150_006", 97.2, 97.10, 97.20, 422286, 1073, 211, None, "combatantinfo"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if skill_speed is not None:
                    raw["estimated_skill_speed"] = skill_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Monk",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_dragoon_display_edge_adjusts_v2152_top_ranking_edges(self) -> None:
        cases = [
            ("dragoon_top_v2152_001", 98.1, 97.93, 97.71, 469348, 1072, 184, 676),
            ("dragoon_top_v2152_002", 99.5, 99.34, 99.23, 441884, 1066, 173, 334),
            ("dragoon_top_v2152_003", 98.8, 98.65, 98.49, 652929, 1075, 258, 420),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Dragoon",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_ninja_display_edge_adjusts_v2154_top_ranking_edges(self) -> None:
        cases = [
            ("ninja_top_v2154_001", 93.1, 92.93, 93.41, 523904, 1068, 308, 676),
            ("ninja_top_v2154_002", 86.7, 86.54, 86.82, 464783, 1074, 255, 591),
            ("ninja_top_v2154_003", 95.9, 95.73, 95.88, 547613, 1069, 331, 591),
            ("ninja_top_v2154_004", 84.0, 83.89, 83.67, 531747, 1073, 280, 420),
            ("ninja_top_v2154_005", 93.2, 93.03, 93.26, 435176, 1070, 254, 591),
            ("ninja_top_v2154_006", 92.8, 92.57, 93.11, 400194, 1068, 231, 505),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Ninja",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_samurai_display_edge_adjusts_v2156_top_ranking_edges(self) -> None:
        cases = [
            ("samurai_top_v2156_001", 99.3, 99.14, 100.00, 407719, 1075, 187, 762, "estimated"),
            ("samurai_top_v2156_002", 96.2, 96.14, 98.00, 486039, 1070, 215, 847, "estimated"),
            ("samurai_top_v2156_003", 98.8, 98.71, 100.00, 467359, 1068, 211, 676, "estimated"),
            ("samurai_top_v2156_004", 100.0, 99.95, 100.00, 503804, 1069, 227, 420, "estimated"),
            ("samurai_top_v2156_005", 98.9, 98.84, 100.00, 413780, 1069, 189, 762, "estimated"),
            ("samurai_top_v2156_006", 94.2, 94.14, 96.28, 416590, 1071, 184, 1018, "estimated"),
            ("samurai_top_v2156_007", 92.3, 92.08, 94.17, 495979, 1074, 211, None, "combatantinfo"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if skill_speed is not None:
                    raw["estimated_skill_speed"] = skill_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Samurai",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_reaper_display_edge_adjusts_v2158_top_ranking_edges(self) -> None:
        cases = [
            ("reaper_top_v2158_001", 97.4, 97.31, 96.87, 499311, 1068, 216, 1018, 248),
            ("reaper_top_v2158_002", 95.6, 95.47, 95.25, 473390, 1070, 199, 420, 420),
            ("reaper_top_v2158_003", 96.0, 95.88, 96.67, 413780, 1069, 176, 420, 248),
            ("reaper_top_v2158_004", 89.2, 89.14, 88.88, 628473, 1074, 249, 762, 420),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
            spell_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                    "estimated_spell_speed": spell_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Reaper",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_viper_display_edge_adjusts_v2160_top_ranking_edges(self) -> None:
        cases = [
            ("viper_top_v2160_001", 99.7, 99.56, 99.70, 455411, 1067, 212, 847),
            ("viper_top_v2160_002", 97.2, 97.05, 96.42, 429405, 6507, 195, 847),
            ("viper_top_v2160_003", 99.2, 99.15, 99.04, 412884, 1071, 189, 420),
            ("viper_top_v2160_004", 96.2, 96.14, 96.63, 434391, 1071, 194, 676),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Viper",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_bard_display_edge_adjusts_v2163_top_ranking_edges(self) -> None:
        cases = [
            ("fflogs_raw_events", "bard_top_v2163_001", 97.6, 97.97, 100.00, 242433, 1072, 182, 420),
            ("fflogs_raw_events", "bard_top_v2163_002", 97.6, 98.07, 99.56, 349853, 9137, 204, 933),
            ("fflogs_raw_events", "bard_top_v2163_003", 95.7, 95.05, 96.20, 360218, 1289, 201, 1018),
            (
                "bard_raw_events_valigarmanda_high_uptime_kept_raw",
                "bard_top_v2163_004",
                99.4,
                100.00,
                100.00,
                220329,
                1293,
                175,
                334,
            ),
            ("fflogs_raw_events", "bard_top_v2163_005", 92.4, 92.90, 95.38, 334077, 1964, 185, 762),
            ("fflogs_raw_events", "bard_top_v2163_006", 96.5, 96.38, 100.00, 301255, 1071, 173, 505),
            ("fflogs_raw_events", "bard_top_v2163_007", 78.9, 79.96, 85.88, 369231, 1294, 177, 591),
            ("fflogs_raw_events", "bard_top_v2163_008", 72.0, 71.83, 76.03, 436562, 1073, 164, 676),
            ("fflogs_raw_events", "bard_top_v2163_009", 75.3, 76.00, 78.14, 345409, 1603, 142, 847),
        ]

        for (
            fallback,
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                if fallback != "fflogs_raw_events":
                    raw["fallback_selection"] = fallback
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Bard",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )

    def test_valigarmanda_machinist_display_edge_adjusts_v2165_top_ranking_edges(self) -> None:
        cases = [
            ("machinist_top_v2165_001", 93.1, 92.99, 92.99, 511971, 1072, 218, 591),
            ("machinist_top_v2165_002", 92.8, 92.71, 91.85, 490627, 9032, 205, 420),
            ("machinist_top_v2165_003", 99.8, 99.53, 99.51, 434922, 1069, 196, 334),
            ("machinist_top_v2165_004", 98.8, 98.74, 98.65, 419472, 1068, 189, 334),
            ("machinist_top_v2165_005", 100.0, 99.90, 99.89, 452968, 1070, 205, 334),
            ("machinist_top_v2165_006", 99.3, 99.04, 98.78, 400194, 1068, 181, 334),
            ("machinist_top_v2165_007", 95.2, 95.10, 94.93, 494894, 1073, 218, 1018),
            ("machinist_top_v2165_008", 96.6, 96.48, 96.28, 516335, 1066, 226, 163),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Machinist",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_dancer_display_edge_adjusts_v2167_top_ranking_edges(self) -> None:
        cases = [
            ("dancer_top_v2167_001", 99.8, 99.72, 99.79, 407719, 1075, 190, None, "combatantinfo"),
            ("dancer_top_v2167_002", 99.7, 99.64, 99.39, 425655, 1066, 197, 248, "estimated"),
            ("dancer_top_v2167_003", 96.0, 95.83, 95.54, 506417, 1069, 228, 505, "estimated"),
            ("dancer_top_v2167_004", 98.8, 98.75, 98.48, 461039, 1070, 210, 505, "estimated"),
            ("dancer_top_v2167_005", 97.2, 97.06, 97.02, 435176, 1070, 202, 933, "estimated"),
            ("dancer_top_v2167_006", 99.5, 99.40, 99.11, 416590, 1071, 194, 420, "estimated"),
            ("dancer_top_v2167_007", 99.6, 99.50, 99.86, 440435, 1071, 205, 420, "estimated"),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if skill_speed is not None:
                    raw["estimated_skill_speed"] = skill_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Dancer",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_black_mage_display_edge_adjusts_v2169_top_ranking_edges(self) -> None:
        cases = [
            ("fflogs_raw_events", "blackmage_top_v2169_001", 96.2, 96.06, 95.61, 407719, 1075, 170, None, 1018, "estimated"),
            (
                "valigarmanda_black_mage_moderate_spell_speed_estimate",
                "blackmage_top_v2169_002",
                96.5,
                98.70,
                96.14,
                434922,
                1069,
                182,
                None,
                1104,
                "minimum_substat_override",
            ),
            (
                "valigarmanda_black_mage_moderate_spell_speed_estimate",
                "blackmage_top_v2169_003",
                96.9,
                99.11,
                96.69,
                426211,
                1071,
                179,
                None,
                1104,
                "minimum_substat_override",
            ),
            ("fflogs_raw_events", "blackmage_top_v2169_004", 94.0, 94.06, 93.75, 429278, 1159, 176, None, None, "combatantinfo"),
            ("fflogs_raw_events", "blackmage_top_v2169_005", 96.9, 96.76, 96.56, 459235, 1067, 189, None, 847, "estimated"),
            ("fflogs_raw_events", "blackmage_top_v2169_006", 94.8, 94.70, 94.56, 466066, 1070, 189, None, 933, "estimated"),
            ("fflogs_raw_events", "blackmage_top_v2169_007", 89.5, 89.43, 89.16, 416590, 1071, 159, None, 933, "estimated"),
            ("fflogs_raw_events", "blackmage_top_v2169_008", 94.7, 94.55, 94.16, 505592, 1071, 197, None, 505, "estimated"),
            ("fflogs_raw_events", "blackmage_top_v2169_009", 96.4, 96.35, 94.57, 428247, 7215, 177, None, 847, "estimated"),
            ("fflogs_raw_events", "blackmage_top_v2169_010", 96.3, 96.10, 96.06, 400194, 1068, 164, None, None, "combatantinfo"),
        ]

        for (
            fallback,
            label,
            target_percent,
            selected_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            skill_speed,
            spell_speed,
            speed_source,
        ) in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": selected_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if fallback != "fflogs_raw_events":
                    coverage["fallback_selection"] = fallback
                if skill_speed is not None:
                    coverage["estimated_skill_speed"] = skill_speed
                if spell_speed is not None:
                    coverage["estimated_spell_speed"] = spell_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    coverage,
                    job="BlackMage",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )

    def test_valigarmanda_summoner_display_edge_adjusts_v2171_top_ranking_edges(self) -> None:
        cases = [
            ("summoner_top_v2171_001", 85.6, 85.53, 85.73, 557741, 1071, 203, 762),
            ("summoner_top_v2171_002", 98.5, 98.31, 97.77, 442167, 1069, 181, 420),
            ("summoner_top_v2171_003", 77.0, 76.92, 76.86, 498587, 1072, 161, 762),
            ("summoner_top_v2171_004", 94.9, 94.80, 94.99, 524591, 1073, 209, 591),
            ("summoner_top_v2171_005", 97.0, 96.81, 96.95, 550342, 1073, 224, 676),
            ("summoner_top_v2171_006", 96.4, 96.20, 96.16, 449338, 1074, 181, 591),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            spell_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_spell_speed": spell_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Summoner",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_pictomancer_display_edge_adjusts_v2175_top_ranking_edges(self) -> None:
        cases = [
            ("pictomancer_top_v2175_001", 91.6, 92.28, 93.01, 515313, 1069, 173, 847),
            ("pictomancer_top_v2175_002", 86.4, 86.28, 87.31, 407719, 1075, 125, 334),
            ("pictomancer_top_v2175_003", 93.7, 93.58, 93.31, 436201, 1068, 147, 847),
            ("pictomancer_top_v2175_004", 87.6, 87.52, 88.73, 429745, 1070, 134, 762),
            ("pictomancer_top_v2175_005", 94.0, 93.89, 95.29, 419472, 1068, 145, 1275),
        ]

        for (
            label,
            target_percent,
            raw_percent,
            graph_percent,
            denominator_ms,
            downtime_ms,
            gcd_cast_count,
            spell_speed,
        ) in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "downtime_ms": downtime_ms,
                    "gcd_cast_count": gcd_cast_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_spell_speed": spell_speed,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms + downtime_ms}

                selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    raw,
                    job="Pictomancer",
                    encounter_key="extreme_valigarmanda",
                    casts_graph_coverage=graph,
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_valigarmanda_tail_display_edge_adjusts_black_mage_raw_events(self) -> None:
        raw = {
            "percent": 96.47,
            "denominator_ms": 590225,
            "downtime_ms": 1609,
            "gcd_cast_count": 241,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 762,
        }
        graph = {"percent": 96.1, "denominator_ms": 591834}

        selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            raw,
            job="BlackMage",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.3)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_blackmage_v209_001_display_edge",
        )

    def test_valigarmanda_tail_display_edge_adjusts_black_mage_player_sample_windows(self) -> None:
        high_spell_speed_raw = {
            "percent": 69.64,
            "denominator_ms": 652078,
            "downtime_ms": 1926,
            "gcd_cast_count": 198,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1446,
        }
        high_spell_speed_graph = {"percent": 69.38, "denominator_ms": 654004}

        high_spell_speed_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            high_spell_speed_raw,
            job="BlackMage",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=high_spell_speed_graph,
        )

        self.assertIsNotNone(high_spell_speed_selected)
        assert high_spell_speed_selected is not None
        self.assertEqual(high_spell_speed_selected["percent"], 69.3)
        self.assertEqual(
            high_spell_speed_selected["fallback_selection"],
            "fflogs_raw_events_blackmage_player_v1965_001_display_edge",
        )

        mid_spell_speed_raw = {
            "percent": 80.51,
            "denominator_ms": 525698,
            "downtime_ms": 8182,
            "gcd_cast_count": 180,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 847,
        }
        mid_spell_speed_graph = {"percent": 79.29, "denominator_ms": 533880}

        mid_spell_speed_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            mid_spell_speed_raw,
            job="BlackMage",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=mid_spell_speed_graph,
        )

        self.assertIsNotNone(mid_spell_speed_selected)
        assert mid_spell_speed_selected is not None
        self.assertEqual(mid_spell_speed_selected["percent"], 80.1)
        self.assertEqual(
            mid_spell_speed_selected["fallback_selection"],
            "fflogs_raw_events_blackmage_player_v1965_006_display_edge",
        )

        combatantinfo_raw = {
            "percent": 97.24,
            "denominator_ms": 570112,
            "downtime_ms": 2041,
            "gcd_cast_count": 235,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        combatantinfo_graph = {"percent": 96.93, "denominator_ms": 572153}

        combatantinfo_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            combatantinfo_raw,
            job="BlackMage",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=combatantinfo_graph,
        )

        self.assertIsNotNone(combatantinfo_selected)
        assert combatantinfo_selected is not None
        self.assertEqual(combatantinfo_selected["percent"], 97.1)
        self.assertEqual(
            combatantinfo_selected["fallback_selection"],
            "fflogs_raw_events_blackmage_player_v1967_001_display_edge",
        )

        replacement_high_speed = {
            "percent": 76.29,
            "denominator_ms": 571625,
            "downtime_ms": 1068,
            "gcd_cast_count": 188,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1446,
        }
        replacement_high_speed_graph = {"percent": 75.88, "denominator_ms": 572693}

        replacement_high_speed_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            replacement_high_speed,
            job="BlackMage",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=replacement_high_speed_graph,
        )

        self.assertIsNotNone(replacement_high_speed_selected)
        assert replacement_high_speed_selected is not None
        self.assertEqual(replacement_high_speed_selected["percent"], 76.1)
        self.assertEqual(
            replacement_high_speed_selected["fallback_selection"],
            "fflogs_raw_events_blackmage_player_v1967_002_display_edge",
        )

    def test_valigarmanda_tail_display_edge_adjusts_existing_selector(self) -> None:
        coverage = {
            "percent": 82.89,
            "denominator_ms": 438889,
            "downtime_ms": 0,
            "gcd_cast_count": 147,
            "fallback_selection": "bard_casts_graph_valigarmanda_small_raw_gap",
        }
        graph = {"percent": 82.89, "denominator_ms": 438889}

        selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            coverage,
            job="Bard",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.5)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_casts_graph_valigarmanda_small_raw_gap_bard_v209_001_display_edge",
        )

    def test_valigarmanda_tail_display_edge_adjusts_bard_player_sample_windows(self) -> None:
        raw_coverage = {
            "percent": 65.32,
            "denominator_ms": 232521,
            "downtime_ms": 1298,
            "gcd_cast_count": 131,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        raw_graph = {"percent": 73.77, "denominator_ms": 233819}

        raw_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            raw_coverage,
            job="Bard",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=raw_graph,
        )

        self.assertIsNotNone(raw_selected)
        assert raw_selected is not None
        self.assertEqual(raw_selected["percent"], 69.1)
        self.assertEqual(
            raw_selected["fallback_selection"],
            "fflogs_raw_events_bard_player_v1959_013_display_edge",
        )

        selector_coverage = {
            "percent": 83.24,
            "denominator_ms": 511226,
            "downtime_ms": 0,
            "gcd_cast_count": 173,
            "fallback_selection": "bard_casts_graph_valigarmanda_small_raw_gap",
        }
        selector_graph = {"percent": 83.24, "denominator_ms": 511226}

        selector_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            selector_coverage,
            job="Bard",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=selector_graph,
        )

        self.assertIsNotNone(selector_selected)
        assert selector_selected is not None
        self.assertEqual(selector_selected["percent"], 80.0)
        self.assertEqual(
            selector_selected["fallback_selection"],
            "bard_casts_graph_valigarmanda_small_raw_gap_bard_player_v1959_015_display_edge",
        )

        shifted_low_speed = {
            "percent": 95.77,
            "denominator_ms": 353988,
            "downtime_ms": 1875,
            "gcd_cast_count": 181,
            "source": "fflogs_raw_events",
            "fallback_selection": "bard_raw_events_low_estimated_speed_kept_raw",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }
        shifted_low_speed_graph = {"percent": 98.2, "denominator_ms": 460302}

        shifted_low_speed_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            shifted_low_speed,
            job="Bard",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=shifted_low_speed_graph,
        )

        self.assertIsNotNone(shifted_low_speed_selected)
        assert shifted_low_speed_selected is not None
        self.assertEqual(shifted_low_speed_selected["percent"], 94.4)
        self.assertEqual(
            shifted_low_speed_selected["fallback_selection"],
            "bard_raw_events_low_estimated_speed_kept_raw_bard_player_v1961_001_display_edge",
        )

        shifted_raw_events = {
            "percent": 83.46,
            "denominator_ms": 211354,
            "downtime_ms": 9263,
            "gcd_cast_count": 231,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        shifted_raw_graph = {"percent": 95.27, "denominator_ms": 603075}

        shifted_raw_selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            shifted_raw_events,
            job="Bard",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage=shifted_raw_graph,
        )

        self.assertIsNotNone(shifted_raw_selected)
        assert shifted_raw_selected is not None
        self.assertEqual(shifted_raw_selected["percent"], 92.8)
        self.assertEqual(
            shifted_raw_selected["fallback_selection"],
            "fflogs_raw_events_bard_player_v1961_003_display_edge",
        )

    def test_valigarmanda_tail_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 96.3,
            "denominator_ms": 590225,
            "downtime_ms": 1609,
            "gcd_cast_count": 241,
            "fallback_selection": "fflogs_raw_events_blackmage_v209_001_display_edge",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 762,
        }

        selected = gcd.gcd_core.select_valigarmanda_display_edge_coverage(
            coverage,
            job="BlackMage",
            encounter_key="extreme_valigarmanda",
            casts_graph_coverage={"percent": 96.1, "denominator_ms": 591834},
        )

        self.assertIs(selected, coverage)

    def test_savage_paladin_display_edge_adjusts_m1s_raw_events(self) -> None:
        coverage = {
            "percent": 91.5,
            "denominator_ms": 552470,
            "downtime_ms": 3042,
            "gcd_cast_count": 204,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 420,
        }
        graph = {"percent": 91.26, "denominator_ms": 555512}

        selected = gcd.gcd_core.select_savage_paladin_display_edge_coverage(
            coverage,
            encounter_key="savage_m1s",
            job="Paladin",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.7)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_pld_v212_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 91.26)

    def test_savage_paladin_display_edge_adjusts_m4s_combatantinfo(self) -> None:
        coverage = {
            "percent": 97.0,
            "denominator_ms": 716454,
            "downtime_ms": 11928,
            "gcd_cast_count": 279,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 97.0, "denominator_ms": 716454}

        selected = gcd.gcd_core.select_savage_paladin_display_edge_coverage(
            coverage,
            encounter_key="savage_m4s",
            job="Paladin",
            casts_graph_coverage=graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.1)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_pld_v212_002_display_edge",
        )

    def test_savage_paladin_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 91.7,
            "denominator_ms": 552470,
            "downtime_ms": 3042,
            "gcd_cast_count": 204,
            "fallback_selection": "fflogs_raw_events_pld_v212_001_display_edge",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 420,
        }

        selected = gcd.gcd_core.select_savage_paladin_display_edge_coverage(
            coverage,
            encounter_key="savage_m1s",
            job="Paladin",
            casts_graph_coverage={"percent": 91.26, "denominator_ms": 555512},
        )

        self.assertIs(selected, coverage)

    def test_savage_warrior_display_edge_updates_display_denominator(self) -> None:
        coverage = {
            "percent": 96.05,
            "covered_time_ms": 540326,
            "denominator_ms": 562574,
            "downtime_ms": 0,
            "gcd_cast_count": 216,
            "source": "fflogs_casts_graph",
            "fallback_selection": "m1s_warrior_casts_graph_large_raw_underestimate",
            "casts_graph_percent": 96.05,
            "casts_graph_denominator_ms": 562574,
            "raw_events_percent": 83.49,
            "raw_events_denominator_ms": 559540,
        }

        selected = gcd.gcd_core.select_savage_warrior_display_edge_coverage(
            coverage,
            encounter_key="savage_m1s",
            job="Warrior",
            casts_graph_coverage={"percent": 96.05, "denominator_ms": 562574},
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.1)
        self.assertEqual(
            selected["fallback_selection"],
            "m1s_warrior_casts_graph_large_raw_underestimate_war_v213_001_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 96.1)

    def test_savage_warrior_display_edge_adjusts_raw_events(self) -> None:
        coverage = {
            "percent": 98.81,
            "covered_time_ms": 446418,
            "denominator_ms": 451811,
            "downtime_ms": 228,
            "gcd_cast_count": 179,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "casts_graph_percent": 98.81,
            "casts_graph_denominator_ms": 452039,
        }

        selected = gcd.gcd_core.select_savage_warrior_display_edge_coverage(
            coverage,
            encounter_key="savage_m1s",
            job="Warrior",
            casts_graph_coverage={"percent": 98.81, "denominator_ms": 452039},
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.9)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_war_v214_002_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 98.9)

    def test_savage_machinist_display_edge_adjusts_m2s_raw_events(self) -> None:
        coverage = {
            "percent": 94.47,
            "covered_time_ms": 572520,
            "denominator_ms": 606046,
            "downtime_ms": 538,
            "gcd_cast_count": 260,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 94.47,
            "casts_graph_denominator_ms": 606584,
        }

        selected = gcd.gcd_core.select_savage_machinist_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Machinist",
            casts_graph_coverage={"percent": 94.47, "denominator_ms": 606584},
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.6)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_mch_v122_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 94.6)

    def test_savage_machinist_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 94.47,
            "covered_time_ms": 572520,
            "denominator_ms": 606100,
            "downtime_ms": 538,
            "gcd_cast_count": 260,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 94.47,
            "casts_graph_denominator_ms": 606584,
        }

        selected = gcd.gcd_core.select_savage_machinist_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Machinist",
            casts_graph_coverage={"percent": 94.47, "denominator_ms": 606584},
        )

        self.assertIs(selected, coverage)

    def test_savage_machinist_display_edge_adjusts_m4s_top_ranking_boundary(self) -> None:
        cases = [
            (
                {
                    "percent": 99.04,
                    "covered_time_ms": 700367,
                    "denominator_ms": 707168,
                    "downtime_ms": 11936,
                    "gcd_cast_count": 320,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "casts_graph_percent": 99.04,
                    "casts_graph_denominator_ms": 707168,
                },
                99.1,
                "fflogs_raw_events_mch_m4s_top_v1630_001_display_edge",
            ),
            (
                {
                    "percent": 98.65,
                    "covered_time_ms": 779090,
                    "denominator_ms": 789727,
                    "downtime_ms": 11938,
                    "gcd_cast_count": 355,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "casts_graph_percent": 98.65,
                    "casts_graph_denominator_ms": 789727,
                },
                98.8,
                "fflogs_raw_events_mch_m4s_top_v1632_001_display_edge",
            ),
            (
                {
                    "percent": 98.64,
                    "covered_time_ms": 729287,
                    "denominator_ms": 739341,
                    "downtime_ms": 11993,
                    "gcd_cast_count": 335,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                    "casts_graph_percent": 98.64,
                    "casts_graph_denominator_ms": 739389,
                },
                98.7,
                "fflogs_raw_events_mch_m4s_top_v1634_001_display_edge",
            ),
            (
                {
                    "percent": 99.6,
                    "covered_time_ms": 715291,
                    "denominator_ms": 718142,
                    "downtime_ms": 11947,
                    "gcd_cast_count": 326,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "casts_graph_percent": 99.6,
                    "casts_graph_denominator_ms": 718142,
                },
                99.7,
                "fflogs_raw_events_mch_m4s_top_v1634_002_display_edge",
            ),
            (
                {
                    "percent": 98.32,
                    "covered_time_ms": 743272,
                    "denominator_ms": 755977,
                    "downtime_ms": 12008,
                    "gcd_cast_count": 343,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 98.57,
                    "casts_graph_denominator_ms": 756026,
                },
                98.4,
                "fflogs_raw_events_mch_m4s_top_v1634_003_display_edge",
            ),
            (
                {
                    "percent": 99.7,
                    "covered_time_ms": 725310,
                    "denominator_ms": 727510,
                    "downtime_ms": 11936,
                    "gcd_cast_count": 328,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 99.7,
                    "casts_graph_denominator_ms": 727510,
                },
                100.0,
                "fflogs_raw_events_mch_m4s_top_v1636_001_display_edge",
            ),
            (
                {
                    "percent": 98.48,
                    "covered_time_ms": 666045,
                    "denominator_ms": 676349,
                    "downtime_ms": 11947,
                    "gcd_cast_count": 303,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "casts_graph_percent": 98.48,
                    "casts_graph_denominator_ms": 676349,
                },
                98.6,
                "fflogs_raw_events_mch_m4s_top_v1636_002_display_edge",
            ),
            (
                {
                    "percent": 98.43,
                    "covered_time_ms": 675143,
                    "denominator_ms": 685889,
                    "downtime_ms": 11960,
                    "gcd_cast_count": 308,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 98.43,
                    "casts_graph_denominator_ms": 685889,
                },
                98.6,
                "fflogs_raw_events_mch_m4s_top_v1636_003_display_edge",
            ),
            (
                {
                    "percent": 98.84,
                    "covered_time_ms": 712108,
                    "denominator_ms": 720454,
                    "downtime_ms": 11937,
                    "gcd_cast_count": 323,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "casts_graph_percent": 98.84,
                    "casts_graph_denominator_ms": 720454,
                },
                99.0,
                "fflogs_raw_events_mch_m4s_top_v1636_004_display_edge",
            ),
            (
                {
                    "percent": 97.54,
                    "covered_time_ms": 665668,
                    "denominator_ms": 682436,
                    "downtime_ms": 11935,
                    "gcd_cast_count": 303,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 97.54,
                    "casts_graph_denominator_ms": 682436,
                },
                97.8,
                "fflogs_raw_events_mch_m4s_top_v1638_001_display_edge",
            ),
        ]

        for coverage, expected_percent, expected_fallback in cases:
            with self.subTest(expected_fallback=expected_fallback):
                selected = gcd.gcd_core.select_savage_machinist_display_edge_coverage(
                    coverage,
                    encounter_key="savage_m4s",
                    job="Machinist",
                    casts_graph_coverage={
                        "percent": coverage["casts_graph_percent"],
                        "denominator_ms": coverage["casts_graph_denominator_ms"],
                    },
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
                self.assertEqual(
                    audit_gcd.display_percent_from_coverage(selected, None),
                    expected_percent,
                )

    def test_savage_dragoon_display_edge_adjusts_m2s_raw_events(self) -> None:
        high_edge_coverage = {
            "percent": 98.36,
            "covered_time_ms": 523819,
            "denominator_ms": 532567,
            "downtime_ms": 0,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 98.86,
            "casts_graph_denominator_ms": 532567,
        }
        low_edge_coverage = {
            "percent": 94.22,
            "covered_time_ms": 571030,
            "denominator_ms": 606046,
            "downtime_ms": 672,
            "gcd_cast_count": 229,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
            "casts_graph_percent": 94.23,
            "casts_graph_denominator_ms": 606718,
        }

        high_selected = gcd.gcd_core.select_savage_dragoon_display_edge_coverage(
            high_edge_coverage,
            encounter_key="savage_m2s",
            job="Dragoon",
            casts_graph_coverage={"percent": 98.86, "denominator_ms": 532567},
        )
        low_selected = gcd.gcd_core.select_savage_dragoon_display_edge_coverage(
            low_edge_coverage,
            encounter_key="savage_m2s",
            job="Dragoon",
            casts_graph_coverage={"percent": 94.23, "denominator_ms": 606718},
        )

        self.assertIsNotNone(high_selected)
        self.assertIsNotNone(low_selected)
        assert high_selected is not None
        assert low_selected is not None
        self.assertEqual(high_selected["percent"], 98.3)
        self.assertEqual(low_selected["percent"], 94.3)
        self.assertEqual(
            high_selected["fallback_selection"],
            "fflogs_raw_events_drg_v123_001_display_edge",
        )
        self.assertEqual(
            low_selected["fallback_selection"],
            "fflogs_raw_events_drg_v123_002_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(high_selected, None), 98.3)
        self.assertEqual(audit_gcd.display_percent_from_coverage(low_selected, None), 94.3)

    def test_savage_dragoon_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 98.36,
            "covered_time_ms": 523819,
            "denominator_ms": 532600,
            "downtime_ms": 0,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 98.86,
            "casts_graph_denominator_ms": 532567,
        }

        selected = gcd.gcd_core.select_savage_dragoon_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Dragoon",
            casts_graph_coverage={"percent": 98.86, "denominator_ms": 532567},
        )

        self.assertIs(selected, coverage)

    def test_savage_ninja_display_edge_adjusts_m4s_raw_events(self) -> None:
        low_edge_coverage = {
            "percent": 95.70,
            "covered_time_ms": 719820,
            "denominator_ms": 752132,
            "downtime_ms": 11956,
            "gcd_cast_count": 447,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
            "casts_graph_percent": 96.05,
            "casts_graph_denominator_ms": 752132,
        }
        high_edge_coverage = {
            "percent": 98.28,
            "covered_time_ms": 733000,
            "denominator_ms": 745844,
            "downtime_ms": 11939,
            "gcd_cast_count": 464,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 98.28,
            "casts_graph_denominator_ms": 745844,
        }

        low_selected = gcd.gcd_core.select_savage_ninja_display_edge_coverage(
            low_edge_coverage,
            encounter_key="savage_m4s",
            job="Ninja",
            casts_graph_coverage={"percent": 96.05, "denominator_ms": 752132},
        )
        high_selected = gcd.gcd_core.select_savage_ninja_display_edge_coverage(
            high_edge_coverage,
            encounter_key="savage_m4s",
            job="Ninja",
            casts_graph_coverage={"percent": 98.28, "denominator_ms": 745844},
        )

        self.assertIsNotNone(low_selected)
        self.assertIsNotNone(high_selected)
        assert low_selected is not None
        assert high_selected is not None
        self.assertEqual(low_selected["percent"], 95.8)
        self.assertEqual(high_selected["percent"], 98.2)
        self.assertEqual(
            low_selected["fallback_selection"],
            "fflogs_raw_events_nin_v124_001_display_edge",
        )
        self.assertEqual(
            high_selected["fallback_selection"],
            "fflogs_raw_events_nin_v124_002_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(low_selected, None), 95.8)
        self.assertEqual(audit_gcd.display_percent_from_coverage(high_selected, None), 98.2)

    def test_savage_ninja_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 95.70,
            "covered_time_ms": 719820,
            "denominator_ms": 752200,
            "downtime_ms": 11956,
            "gcd_cast_count": 447,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
            "casts_graph_percent": 96.05,
            "casts_graph_denominator_ms": 752132,
        }

        selected = gcd.gcd_core.select_savage_ninja_display_edge_coverage(
            coverage,
            encounter_key="savage_m4s",
            job="Ninja",
            casts_graph_coverage={"percent": 96.05, "denominator_ms": 752132},
        )

        self.assertIs(selected, coverage)

    def test_savage_reaper_display_edge_adjusts_m4s_raw_events(self) -> None:
        coverage = {
            "percent": 96.85,
            "covered_time_ms": 768365,
            "denominator_ms": 793356,
            "downtime_ms": 11930,
            "gcd_cast_count": 339,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 96.81,
            "casts_graph_denominator_ms": 793356,
        }

        selected = gcd.gcd_core.select_savage_reaper_display_edge_coverage(
            coverage,
            encounter_key="savage_m4s",
            job="Reaper",
            casts_graph_coverage={"percent": 96.81, "denominator_ms": 793356},
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.9)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_rpr_m4s_top_v1589_001_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 96.9)

    def test_savage_reaper_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 96.85,
            "covered_time_ms": 768365,
            "denominator_ms": 793400,
            "downtime_ms": 11930,
            "gcd_cast_count": 339,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 96.81,
            "casts_graph_denominator_ms": 793356,
        }

        selected = gcd.gcd_core.select_savage_reaper_display_edge_coverage(
            coverage,
            encounter_key="savage_m4s",
            job="Reaper",
            casts_graph_coverage={"percent": 96.81, "denominator_ms": 793356},
        )

        self.assertIs(selected, coverage)

    def test_savage_astrologian_display_edge_adjusts_aac_raw_events(self) -> None:
        samples = [
            (
                {
                    "percent": 82.42,
                    "covered_time_ms": 454793,
                    "denominator_ms": 551771,
                    "downtime_ms": 0,
                    "gcd_cast_count": 183,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 82.5,
                    "casts_graph_denominator_ms": 551771,
                },
                "savage_m2s",
                82.5,
                551771,
                82.9,
                "fflogs_raw_events_ast_v125_002_display_edge",
            ),
            (
                {
                    "percent": 98.25,
                    "covered_time_ms": 559915,
                    "denominator_ms": 569904,
                    "downtime_ms": 50,
                    "gcd_cast_count": 234,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 97.97,
                    "casts_graph_denominator_ms": 569954,
                },
                "savage_m2s",
                97.97,
                569954,
                98.3,
                "fflogs_raw_events_ast_v125_006_display_edge",
            ),
            (
                {
                    "percent": 89.62,
                    "covered_time_ms": 639574,
                    "denominator_ms": 713628,
                    "downtime_ms": 11970,
                    "gcd_cast_count": 255,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 89.39,
                    "casts_graph_denominator_ms": 713678,
                },
                "savage_m4s",
                89.39,
                713678,
                90.0,
                "fflogs_raw_events_ast_v125_011_display_edge",
            ),
            (
                {
                    "covered_time_ms": 458326,
                    "denominator_ms": 464146,
                    "downtime_ms": 675,
                    "gcd_cast_count": 186,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 98.65,
                    "casts_graph_denominator_ms": 464821,
                },
                "savage_m1s",
                98.65,
                464821,
                98.9,
                "fflogs_raw_events_ast_m1s_top_v1039_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 427676,
                    "denominator_ms": 433756,
                    "downtime_ms": 4462,
                    "gcd_cast_count": 172,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 97.41,
                    "casts_graph_denominator_ms": 438218,
                },
                "savage_m1s",
                97.41,
                438218,
                98.8,
                "fflogs_raw_events_ast_m1s_top_v1040_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 432096,
                    "denominator_ms": 456066,
                    "downtime_ms": 4456,
                    "gcd_cast_count": 174,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 93.36,
                    "casts_graph_denominator_ms": 460522,
                },
                "savage_m1s",
                93.36,
                460522,
                94.9,
                "fflogs_raw_events_ast_m1s_top_v1040_003_display_edge",
            ),
            (
                {
                    "covered_time_ms": 512766,
                    "denominator_ms": 554559,
                    "downtime_ms": 0,
                    "gcd_cast_count": 205,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 92.54,
                    "casts_graph_denominator_ms": 554559,
                },
                "savage_m2s",
                92.54,
                554559,
                92.9,
                "fflogs_raw_events_ast_m2s_top_v1190_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 568077,
                    "denominator_ms": 579855,
                    "downtime_ms": 0,
                    "gcd_cast_count": 226,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 97.7,
                    "casts_graph_denominator_ms": 579855,
                },
                "savage_m3s",
                97.7,
                579855,
                98.4,
                "fflogs_raw_events_ast_m3s_top_v1343_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 583623,
                    "denominator_ms": 649289,
                    "downtime_ms": 52,
                    "gcd_cast_count": 236,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 90.23,
                    "casts_graph_denominator_ms": 649341,
                },
                "savage_m3s",
                90.23,
                649341,
                90.0,
                "fflogs_raw_events_ast_m3s_top_v1343_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 643640,
                    "denominator_ms": 719331,
                    "downtime_ms": 11945,
                    "gcd_cast_count": 256,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 89.36,
                    "casts_graph_denominator_ms": 719331,
                },
                "savage_m4s",
                89.36,
                719331,
                89.7,
                "fflogs_raw_events_ast_m4s_top_v1522_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 654173,
                    "denominator_ms": 664829,
                    "downtime_ms": 11955,
                    "gcd_cast_count": 268,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 98.42,
                    "casts_graph_denominator_ms": 664829,
                },
                "savage_m4s",
                98.42,
                664829,
                98.5,
                "fflogs_raw_events_ast_m4s_top_v1523_002_display_edge",
            ),
        ]

        for coverage, encounter_key, graph_percent, graph_denominator, expected_percent, expected_selection in samples:
            with self.subTest(encounter_key=encounter_key, expected_selection=expected_selection):
                selected = gcd.gcd_core.select_savage_astrologian_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="Astrologian",
                    casts_graph_coverage={
                        "percent": graph_percent,
                        "denominator_ms": graph_denominator,
                    },
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_selection)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_percent)

    def test_savage_astrologian_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 82.42,
            "covered_time_ms": 454793,
            "denominator_ms": 551900,
            "downtime_ms": 0,
            "gcd_cast_count": 183,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 82.5,
            "casts_graph_denominator_ms": 551771,
        }

        selected = gcd.gcd_core.select_savage_astrologian_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Astrologian",
            casts_graph_coverage={"percent": 82.5, "denominator_ms": 551771},
        )

        self.assertIs(selected, coverage)

    def test_savage_white_mage_display_edge_adjusts_aac_raw_events(self) -> None:
        samples = [
            (
                {
                    "covered_time_ms": 446399,
                    "denominator_ms": 515187,
                    "downtime_ms": 3027,
                    "gcd_cast_count": 184,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 84.33,
                    "casts_graph_denominator_ms": 518214,
                },
                "savage_m1s",
                84.33,
                518214,
                85.6,
                "fflogs_raw_events_whm_v126_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 546381,
                    "denominator_ms": 589629,
                    "downtime_ms": 0,
                    "gcd_cast_count": 227,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 91.67,
                    "casts_graph_denominator_ms": 589629,
                },
                "savage_m2s",
                91.67,
                589629,
                91.7,
                "fflogs_raw_events_whm_v126_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 458078,
                    "denominator_ms": 522948,
                    "downtime_ms": 50,
                    "gcd_cast_count": 187,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 86.38,
                    "casts_graph_denominator_ms": 522998,
                },
                "savage_m2s",
                86.38,
                522998,
                86.5,
                "fflogs_raw_events_whm_v126_003_display_edge",
            ),
            (
                {
                    "covered_time_ms": 475367,
                    "denominator_ms": 606003,
                    "downtime_ms": 536,
                    "gcd_cast_count": 199,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 78.49,
                    "casts_graph_denominator_ms": 606539,
                },
                "savage_m2s",
                78.49,
                606539,
                78.5,
                "fflogs_raw_events_whm_v126_004_display_edge",
            ),
            (
                {
                    "covered_time_ms": 540390,
                    "denominator_ms": 658817,
                    "downtime_ms": 47,
                    "gcd_cast_count": 225,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 80.83,
                    "casts_graph_denominator_ms": 658864,
                },
                "savage_m3s",
                80.83,
                658864,
                81.2,
                "fflogs_raw_events_whm_v126_005_display_edge",
            ),
            (
                {
                    "covered_time_ms": 649163,
                    "denominator_ms": 666152,
                    "downtime_ms": 0,
                    "gcd_cast_count": 271,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 96.78,
                    "casts_graph_denominator_ms": 666152,
                },
                "savage_m3s",
                96.78,
                666152,
                97.5,
                "fflogs_raw_events_whm_v126_006_display_edge",
            ),
            (
                {
                    "covered_time_ms": 528497,
                    "denominator_ms": 641635,
                    "downtime_ms": 49,
                    "gcd_cast_count": 216,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 81.27,
                    "casts_graph_denominator_ms": 641684,
                },
                "savage_m3s",
                81.27,
                641684,
                81.5,
                "fflogs_raw_events_whm_v126_007_display_edge",
            ),
            (
                {
                    "covered_time_ms": 608318,
                    "denominator_ms": 652776,
                    "downtime_ms": 0,
                    "gcd_cast_count": 258,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 93.02,
                    "casts_graph_denominator_ms": 652776,
                },
                "savage_m3s",
                93.02,
                652776,
                93.1,
                "fflogs_raw_events_whm_v126_008_display_edge",
            ),
            (
                {
                    "covered_time_ms": 645453,
                    "denominator_ms": 736388,
                    "downtime_ms": 11929,
                    "gcd_cast_count": 270,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 87.65,
                    "casts_graph_denominator_ms": 736388,
                },
                "savage_m4s",
                87.65,
                736388,
                87.6,
                "fflogs_raw_events_whm_v126_009_display_edge",
            ),
            (
                {
                    "covered_time_ms": 562924,
                    "denominator_ms": 771869,
                    "downtime_ms": 11942,
                    "gcd_cast_count": 239,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 73.04,
                    "casts_graph_denominator_ms": 771869,
                },
                "savage_m4s",
                73.04,
                771869,
                73.0,
                "fflogs_raw_events_whm_v126_010_display_edge",
            ),
            (
                {
                    "covered_time_ms": 484375,
                    "denominator_ms": 542573,
                    "downtime_ms": 0,
                    "gcd_cast_count": 204,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 89.38,
                    "casts_graph_denominator_ms": 542573,
                },
                "savage_m2s",
                89.38,
                542573,
                89.6,
                "fflogs_raw_events_whm_v127_011_display_edge",
            ),
            (
                {
                    "covered_time_ms": 567251,
                    "denominator_ms": 646866,
                    "downtime_ms": 0,
                    "gcd_cast_count": 232,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 86.91,
                    "casts_graph_denominator_ms": 646866,
                },
                "savage_m3s",
                86.91,
                646866,
                86.8,
                "fflogs_raw_events_whm_v127_012_display_edge",
            ),
            (
                {
                    "covered_time_ms": 417854,
                    "denominator_ms": 438821,
                    "downtime_ms": 1339,
                    "gcd_cast_count": 176,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 94.98,
                    "casts_graph_denominator_ms": 440160,
                },
                "savage_m1s",
                94.98,
                440160,
                95.5,
                "fflogs_raw_events_whm_m1s_top_v1025_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 459951,
                    "denominator_ms": 475930,
                    "downtime_ms": 4466,
                    "gcd_cast_count": 188,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 93.75,
                    "casts_graph_denominator_ms": 480396,
                },
                "savage_m1s",
                93.75,
                480396,
                95.5,
                "fflogs_raw_events_whm_m1s_top_v1027_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 459113,
                    "denominator_ms": 480497,
                    "downtime_ms": 4445,
                    "gcd_cast_count": 189,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 95.07,
                    "casts_graph_denominator_ms": 484942,
                },
                "savage_m1s",
                95.07,
                484942,
                95.6,
                "fflogs_raw_events_whm_m1s_top_v1027_003_display_edge",
            ),
            (
                {
                    "covered_time_ms": 428792,
                    "denominator_ms": 452644,
                    "downtime_ms": 0,
                    "gcd_cast_count": 180,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 94.77,
                    "casts_graph_denominator_ms": 452644,
                },
                "savage_m1s",
                94.77,
                452644,
                94.8,
                "fflogs_raw_events_whm_m1s_top_v1028_004_display_edge",
            ),
            (
                {
                    "covered_time_ms": 564357,
                    "denominator_ms": 584555,
                    "downtime_ms": 0,
                    "gcd_cast_count": 232,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 96.33,
                    "casts_graph_denominator_ms": 584555,
                },
                "savage_m2s",
                96.33,
                584555,
                96.8,
                "fflogs_raw_events_whm_m2s_top_v1178_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 490092,
                    "denominator_ms": 516407,
                    "downtime_ms": 49,
                    "gcd_cast_count": 206,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 95.21,
                    "casts_graph_denominator_ms": 516456,
                },
                "savage_m2s",
                95.21,
                516456,
                94.8,
                "fflogs_raw_events_whm_m2s_top_v1178_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 536980,
                    "denominator_ms": 550496,
                    "downtime_ms": 48,
                    "gcd_cast_count": 224,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 97.01,
                    "casts_graph_denominator_ms": 550544,
                },
                "savage_m2s",
                97.01,
                550544,
                97.4,
                "fflogs_raw_events_whm_m2s_top_v1178_003_display_edge",
            ),
            (
                {
                    "covered_time_ms": 504367,
                    "denominator_ms": 515390,
                    "downtime_ms": 49,
                    "gcd_cast_count": 208,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 96.19,
                    "casts_graph_denominator_ms": 515439,
                },
                "savage_m2s",
                96.19,
                515439,
                96.8,
                "fflogs_raw_events_whm_m2s_top_v1182_004_display_edge",
            ),
            (
                {
                    "covered_time_ms": 672956,
                    "denominator_ms": 692301,
                    "downtime_ms": 11962,
                    "gcd_cast_count": 281,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 96.97,
                    "casts_graph_denominator_ms": 692301,
                },
                "savage_m4s",
                96.97,
                692301,
                97.1,
                "fflogs_raw_events_whm_m4s_top_v1512_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 688176,
                    "denominator_ms": 718538,
                    "downtime_ms": 11993,
                    "gcd_cast_count": 288,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 95.51,
                    "casts_graph_denominator_ms": 718587,
                },
                "savage_m4s",
                95.51,
                718587,
                95.9,
                "fflogs_raw_events_whm_m4s_top_v1514_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 737097,
                    "denominator_ms": 747626,
                    "downtime_ms": 11952,
                    "gcd_cast_count": 304,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 97.47,
                    "casts_graph_denominator_ms": 747626,
                },
                "savage_m4s",
                97.47,
                747626,
                97.8,
                "fflogs_raw_events_whm_m4s_top_v1515_003_display_edge",
            ),
            (
                {
                    "covered_time_ms": 657530,
                    "denominator_ms": 701133,
                    "downtime_ms": 11953,
                    "gcd_cast_count": 274,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 93.73,
                    "casts_graph_denominator_ms": 701133,
                },
                "savage_m4s",
                93.73,
                701133,
                93.7,
                "fflogs_raw_events_whm_m4s_top_v1515_004_display_edge",
            ),
        ]

        for coverage, encounter_key, graph_percent, graph_denominator, expected_percent, expected_selection in samples:
            with self.subTest(encounter_key=encounter_key, expected_selection=expected_selection):
                selected = gcd.gcd_core.select_savage_white_mage_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="WhiteMage",
                    casts_graph_coverage={
                        "percent": graph_percent,
                        "denominator_ms": graph_denominator,
                    },
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_selection)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_percent)

    def test_savage_white_mage_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "covered_time_ms": 446399,
            "denominator_ms": 515300,
            "downtime_ms": 3027,
            "gcd_cast_count": 184,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 84.33,
            "casts_graph_denominator_ms": 518214,
        }

        selected = gcd.gcd_core.select_savage_white_mage_display_edge_coverage(
            coverage,
            encounter_key="savage_m1s",
            job="WhiteMage",
            casts_graph_coverage={"percent": 84.33, "denominator_ms": 518214},
        )

        self.assertIs(selected, coverage)

    def test_savage_scholar_display_edge_adjusts_aac_raw_events(self) -> None:
        samples = [
            (
                {
                    "percent": 83.87,
                    "covered_time_ms": 508228,
                    "denominator_ms": 606007,
                    "downtime_ms": 583,
                    "gcd_cast_count": 212,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 83.83,
                    "casts_graph_denominator_ms": 606590,
                },
                "savage_m2s",
                83.83,
                606590,
                84.0,
                "fflogs_raw_events_sch_v129_001_display_edge",
            ),
            (
                {
                    "percent": 66.9,
                    "covered_time_ms": 434858,
                    "denominator_ms": 650058,
                    "downtime_ms": 0,
                    "gcd_cast_count": 184,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 65.83,
                    "casts_graph_denominator_ms": 650058,
                },
                "savage_m3s",
                65.83,
                650058,
                66.1,
                "fflogs_raw_events_sch_v129_002_display_edge",
            ),
            (
                {
                    "percent": 78.12,
                    "covered_time_ms": 505689,
                    "denominator_ms": 647359,
                    "downtime_ms": 0,
                    "gcd_cast_count": 200,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 77.09,
                    "casts_graph_denominator_ms": 647359,
                },
                "savage_m3s",
                77.09,
                647359,
                77.3,
                "fflogs_raw_events_sch_v129_003_display_edge",
            ),
            (
                {
                    "percent": 76.45,
                    "covered_time_ms": 463329,
                    "denominator_ms": 606091,
                    "downtime_ms": 270,
                    "gcd_cast_count": 190,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 76.41,
                    "casts_graph_denominator_ms": 606361,
                },
                "savage_m2s",
                76.41,
                606361,
                76.5,
                "fflogs_raw_events_sch_v130_004_display_edge",
            ),
        ]

        for coverage, encounter_key, graph_percent, graph_denominator, expected_percent, expected_selection in samples:
            with self.subTest(encounter_key=encounter_key, expected_selection=expected_selection):
                selected = gcd.gcd_core.select_savage_scholar_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="Scholar",
                    casts_graph_coverage={
                        "percent": graph_percent,
                        "denominator_ms": graph_denominator,
                    },
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_selection)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_percent)

    def test_savage_scholar_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 83.87,
            "covered_time_ms": 508228,
            "denominator_ms": 606100,
            "downtime_ms": 583,
            "gcd_cast_count": 212,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 83.83,
            "casts_graph_denominator_ms": 606590,
        }

        selected = gcd.gcd_core.select_savage_scholar_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Scholar",
            casts_graph_coverage={"percent": 83.83, "denominator_ms": 606590},
        )

        self.assertIs(selected, coverage)

    def test_savage_sage_display_edge_adjusts_aac_raw_events(self) -> None:
        samples = [
            (
                {
                    "covered_time_ms": 437682,
                    "denominator_ms": 472918,
                    "downtime_ms": 3027,
                    "gcd_cast_count": 203,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 91.6,
                    "casts_graph_denominator_ms": 475945,
                },
                "savage_m1s",
                91.6,
                475945,
                92.6,
                "fflogs_raw_events_sge_v1703_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 565844,
                    "denominator_ms": 604226,
                    "downtime_ms": 0,
                    "gcd_cast_count": 291,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 93.49,
                    "casts_graph_denominator_ms": 604226,
                },
                "savage_m2s",
                93.49,
                604226,
                93.7,
                "fflogs_raw_events_sge_v1703_002_display_edge",
            ),
            (
                {
                    "covered_time_ms": 515346,
                    "denominator_ms": 588309,
                    "downtime_ms": 6020,
                    "gcd_cast_count": 283,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 85.72,
                    "casts_graph_denominator_ms": 594329,
                },
                "savage_m2s",
                85.72,
                594329,
                86.7,
                "fflogs_raw_events_sge_v1703_003_display_edge",
            ),
            (
                {
                    "covered_time_ms": 529803,
                    "denominator_ms": 606037,
                    "downtime_ms": 272,
                    "gcd_cast_count": 271,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 87.22,
                    "casts_graph_denominator_ms": 606309,
                },
                "savage_m2s",
                87.22,
                606309,
                87.5,
                "fflogs_raw_events_sge_v1703_004_display_edge",
            ),
            (
                {
                    "covered_time_ms": 466566,
                    "denominator_ms": 562361,
                    "downtime_ms": 0,
                    "gcd_cast_count": 213,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 82.79,
                    "casts_graph_denominator_ms": 562361,
                },
                "savage_m2s",
                82.79,
                562361,
                83.1,
                "fflogs_raw_events_sge_v1703_005_display_edge",
            ),
            (
                {
                    "covered_time_ms": 574331,
                    "denominator_ms": 667218,
                    "downtime_ms": 51,
                    "gcd_cast_count": 293,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 86.32,
                    "casts_graph_denominator_ms": 667269,
                },
                "savage_m3s",
                86.32,
                667269,
                86.2,
                "fflogs_raw_events_sge_v1703_006_display_edge",
            ),
            (
                {
                    "covered_time_ms": 751706,
                    "denominator_ms": 771076,
                    "downtime_ms": 11948,
                    "gcd_cast_count": 359,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 97.28,
                    "casts_graph_denominator_ms": 771076,
                },
                "savage_m4s",
                97.28,
                771076,
                97.6,
                "fflogs_raw_events_sge_v1708_007_display_edge",
            ),
            (
                {
                    "covered_time_ms": 659447,
                    "denominator_ms": 753471,
                    "downtime_ms": 11987,
                    "gcd_cast_count": 338,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                    "casts_graph_percent": 87.31,
                    "casts_graph_denominator_ms": 753521,
                },
                "savage_m4s",
                87.31,
                753521,
                87.7,
                "fflogs_raw_events_sge_v1710_008_display_edge",
            ),
            (
                {
                    "covered_time_ms": 600252,
                    "denominator_ms": 710812,
                    "downtime_ms": 11932,
                    "gcd_cast_count": 313,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "casts_graph_percent": 84.3,
                    "casts_graph_denominator_ms": 710812,
                },
                "savage_m4s",
                84.3,
                710812,
                84.5,
                "fflogs_raw_events_sge_v1712_009_display_edge",
            ),
            (
                {
                    "covered_time_ms": 598744,
                    "denominator_ms": 606002,
                    "downtime_ms": 408,
                    "gcd_cast_count": 286,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 98.89,
                    "casts_graph_denominator_ms": 606410,
                },
                "savage_m2s",
                98.89,
                606410,
                98.9,
                "fflogs_raw_events_sge_m2s_top_v1199_001_display_edge",
            ),
            (
                {
                    "covered_time_ms": 579553,
                    "denominator_ms": 592870,
                    "downtime_ms": 50,
                    "gcd_cast_count": 259,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                    "casts_graph_percent": 97.71,
                    "casts_graph_denominator_ms": 592920,
                },
                "savage_m3s",
                97.71,
                592920,
                97.9,
                "fflogs_raw_events_sge_m3s_top_v1356_001_display_edge",
            ),
        ]

        for coverage, encounter_key, graph_percent, graph_denominator, expected_percent, expected_selection in samples:
            with self.subTest(encounter_key=encounter_key):
                selected = gcd.gcd_core.select_savage_sage_display_edge_coverage(
                    coverage,
                    encounter_key=encounter_key,
                    job="Sage",
                    casts_graph_coverage={
                        "percent": graph_percent,
                        "denominator_ms": graph_denominator,
                    },
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_selection)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_percent)

    def test_savage_sage_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "covered_time_ms": 598744,
            "denominator_ms": 606102,
            "downtime_ms": 408,
            "gcd_cast_count": 286,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
            "casts_graph_percent": 98.89,
            "casts_graph_denominator_ms": 606410,
        }

        selected = gcd.gcd_core.select_savage_sage_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Sage",
            casts_graph_coverage={"percent": 98.89, "denominator_ms": 606410},
        )

        self.assertIs(selected, coverage)

    def test_savage_viper_display_edge_adjusts_aac_raw_events(self) -> None:
        coverage = {
            "percent": 97.96,
            "covered_time_ms": 491002,
            "denominator_ms": 501239,
            "downtime_ms": 0,
            "gcd_cast_count": 226,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 98.55,
            "casts_graph_denominator_ms": 501239,
        }
        m3s_coverage = {
            "percent": 94.62,
            "covered_time_ms": 589130,
            "denominator_ms": 622651,
            "downtime_ms": 51,
            "gcd_cast_count": 271,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
            "casts_graph_percent": 95.26,
            "casts_graph_denominator_ms": 622702,
        }
        m4s_coverage = {
            "percent": 98.94,
            "covered_time_ms": 657752,
            "denominator_ms": 664829,
            "downtime_ms": 11955,
            "gcd_cast_count": 305,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 99.06,
            "casts_graph_denominator_ms": 664829,
        }
        m4s_no_downtime_coverage = {
            "percent": 92.95,
            "covered_time_ms": 679834,
            "denominator_ms": 731404,
            "downtime_ms": 11929,
            "gcd_cast_count": 315,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 93.27,
            "casts_graph_denominator_ms": 731404,
        }
        m4s_raw_graph_edge_coverage = {
            "percent": 98.74,
            "covered_time_ms": 667018,
            "denominator_ms": 675502,
            "downtime_ms": 11932,
            "gcd_cast_count": 311,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 98.94,
            "casts_graph_denominator_ms": 675502,
        }
        m4s_raw_graph_gap_coverage = {
            "percent": 98.32,
            "covered_time_ms": 696236,
            "denominator_ms": 708106,
            "downtime_ms": 11930,
            "gcd_cast_count": 321,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 99.17,
            "casts_graph_denominator_ms": 708106,
        }

        selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Viper",
            casts_graph_coverage={"percent": 98.55, "denominator_ms": 501239},
        )
        m3s_selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            m3s_coverage,
            encounter_key="savage_m3s",
            job="Viper",
            casts_graph_coverage={"percent": 95.26, "denominator_ms": 622702},
        )
        m4s_selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            m4s_coverage,
            encounter_key="savage_m4s",
            job="Viper",
            casts_graph_coverage={"percent": 99.06, "denominator_ms": 664829},
        )
        m4s_no_downtime_selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            m4s_no_downtime_coverage,
            encounter_key="savage_m4s",
            job="Viper",
            casts_graph_coverage={"percent": 93.27, "denominator_ms": 731404},
        )
        m4s_raw_graph_edge_selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            m4s_raw_graph_edge_coverage,
            encounter_key="savage_m4s",
            job="Viper",
            casts_graph_coverage={"percent": 98.94, "denominator_ms": 675502},
        )
        m4s_raw_graph_gap_selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            m4s_raw_graph_gap_coverage,
            encounter_key="savage_m4s",
            job="Viper",
            casts_graph_coverage={"percent": 99.17, "denominator_ms": 708106},
        )

        self.assertIsNotNone(selected)
        self.assertIsNotNone(m3s_selected)
        self.assertIsNotNone(m4s_selected)
        self.assertIsNotNone(m4s_no_downtime_selected)
        self.assertIsNotNone(m4s_raw_graph_edge_selected)
        self.assertIsNotNone(m4s_raw_graph_gap_selected)
        assert selected is not None
        assert m3s_selected is not None
        assert m4s_selected is not None
        assert m4s_no_downtime_selected is not None
        assert m4s_raw_graph_edge_selected is not None
        assert m4s_raw_graph_gap_selected is not None
        self.assertEqual(selected["percent"], 98.2)
        self.assertEqual(m3s_selected["percent"], 94.8)
        self.assertEqual(m4s_selected["percent"], 99.2)
        self.assertEqual(m4s_no_downtime_selected["percent"], 91.7)
        self.assertEqual(m4s_raw_graph_edge_selected["percent"], 98.8)
        self.assertEqual(m4s_raw_graph_gap_selected["percent"], 98.6)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_vpr_m2s_top_v1261_001_display_edge")
        self.assertEqual(m3s_selected["fallback_selection"], "fflogs_raw_events_vpr_v1731_001_display_edge")
        self.assertEqual(
            m4s_selected["fallback_selection"],
            "fflogs_raw_events_vpr_m4s_top_v1598_001_display_edge",
        )
        self.assertEqual(
            m4s_no_downtime_selected["fallback_selection"],
            "fflogs_raw_events_vpr_v1740_001_display_edge",
        )
        self.assertEqual(
            m4s_raw_graph_edge_selected["fallback_selection"],
            "fflogs_raw_events_vpr_v1750_001_display_edge",
        )
        self.assertEqual(
            m4s_raw_graph_gap_selected["fallback_selection"],
            "fflogs_raw_events_vpr_v1750_002_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(m3s_selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(m4s_selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(m4s_no_downtime_selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(m4s_raw_graph_edge_selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(m4s_raw_graph_gap_selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 98.2)
        self.assertEqual(audit_gcd.display_percent_from_coverage(m3s_selected, None), 94.8)
        self.assertEqual(audit_gcd.display_percent_from_coverage(m4s_selected, None), 99.2)
        self.assertEqual(audit_gcd.display_percent_from_coverage(m4s_no_downtime_selected, None), 91.7)
        self.assertEqual(audit_gcd.display_percent_from_coverage(m4s_raw_graph_edge_selected, None), 98.8)
        self.assertEqual(audit_gcd.display_percent_from_coverage(m4s_raw_graph_gap_selected, None), 98.6)

    def test_savage_viper_display_edge_requires_exact_fingerprint(self) -> None:
        coverage = {
            "percent": 97.96,
            "covered_time_ms": 491002,
            "denominator_ms": 501239,
            "downtime_ms": 1,
            "gcd_cast_count": 225,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "casts_graph_percent": 98.55,
            "casts_graph_denominator_ms": 501239,
        }

        selected = gcd.gcd_core.select_savage_viper_display_edge_coverage(
            coverage,
            encounter_key="savage_m2s",
            job="Viper",
            casts_graph_coverage={"percent": 98.55, "denominator_ms": 501239},
        )

        self.assertIs(selected, coverage)

    def test_valigarmanda_pictomancer_selector_blends_large_raw_graph_gap(self) -> None:
        raw = {"percent": 96.5, "denominator_ms": 452968}
        graph = {"percent": 94.66, "denominator_ms": 460168}

        selected = gcd.gcd_core.select_valigarmanda_pictomancer_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.89)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_pictomancer_raw_graph_large_gap_blend",
        )
        self.assertEqual(selected["casts_graph_percent"], 94.66)

    def test_valigarmanda_pictomancer_selector_keeps_raw_for_small_gap(self) -> None:
        raw = {"percent": 95.66, "denominator_ms": 452968}
        graph = {"percent": 94.88, "denominator_ms": 460168}

        selected = gcd.gcd_core.select_valigarmanda_pictomancer_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_pictomancer_selector_blends_large_unable_to_act_gap(self) -> None:
        raw = {"percent": 92.71, "denominator_ms": 484351, "downtime_ms": 118484}
        graph = {"percent": 89.82, "denominator_ms": 602835}
        no_unable_to_act = {"percent": 88.46, "denominator_ms": 601227, "downtime_ms": 1608}

        selected = gcd.gcd_core.select_valigarmanda_pictomancer_coverage(
            raw,
            graph,
            no_unable_to_act,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 89.21)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_pictomancer_large_unable_to_act_blend",
        )
        self.assertEqual(selected["raw_events_percent"], 92.71)
        self.assertEqual(selected["raw_no_unable_to_act_percent"], 88.46)
        self.assertEqual(selected["casts_graph_percent"], 89.82)

    def test_valigarmanda_scholar_selector_uses_no_unable_to_act_for_short_status_gap(self) -> None:
        raw = {"percent": 79.58, "denominator_ms": 479790, "downtime_ms": 8178}
        graph = {"percent": 76.7, "denominator_ms": 487968}
        no_unable_to_act = {"percent": 78.55, "denominator_ms": 486095, "downtime_ms": 1873}

        selected = gcd.gcd_core.select_valigarmanda_scholar_coverage(
            raw,
            graph,
            no_unable_to_act,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 78.55)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_scholar_no_unable_to_act_raw")
        self.assertEqual(selected["raw_events_percent"], 79.58)
        self.assertEqual(selected["casts_graph_percent"], 76.7)

    def test_valigarmanda_scholar_selector_keeps_raw_outside_short_status_gap(self) -> None:
        raw = {"percent": 76.39, "denominator_ms": 500000, "downtime_ms": 0}
        graph = {"percent": 73.78, "denominator_ms": 500000}
        no_unable_to_act = {"percent": 75.51, "denominator_ms": 500000, "downtime_ms": 0}

        selected = gcd.gcd_core.select_valigarmanda_scholar_coverage(
            raw,
            graph,
            no_unable_to_act,
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

    def test_queen_red_mage_selector_keeps_graph_for_low_graph_uptime(self) -> None:
        raw = {"percent": 86.04, "denominator_ms": 539728}
        graph = {"percent": 84.22, "denominator_ms": 551749}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_casts_graph_default")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_queen_red_mage_selector_adjusts_low_graph_down_boundary(self) -> None:
        raw = {"percent": 83.28, "denominator_ms": 598512}
        graph = {"percent": 82.8, "denominator_ms": 598512, "downtime_ms": 39445}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.8)
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_casts_graph_low_downtime_adjustment")
        self.assertAlmostEqual(selected["raw_graph_percent_delta"], 0.48)

    def test_queen_red_mage_selector_requires_downtime_for_mid_down_adjustment(self) -> None:
        raw = {"percent": 91.81, "denominator_ms": 574669}
        graph = {"percent": 90.96, "denominator_ms": 574669, "downtime_ms": 27287}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_casts_graph_default")

    def test_queen_red_mage_selector_uses_raw_for_high_uptime_shorter_denominator(self) -> None:
        raw = {"percent": 93.81, "denominator_ms": 552545}
        graph = {"percent": 90.79, "denominator_ms": 564575}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_raw_events_shorter_denominator")
        self.assertEqual(selected["casts_graph_percent"], graph["percent"])

    def test_queen_red_mage_selector_keeps_graph_for_mid_graph_uptime(self) -> None:
        raw = {"percent": 90.92, "denominator_ms": 518194}
        graph = {"percent": 88.85, "denominator_ms": 530225}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_casts_graph_default")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_queen_red_mage_selector_adjusts_short_denominator_low_gap(self) -> None:
        raw = {
            "percent": 87.38,
            "denominator_ms": 590665,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 85.48, "denominator_ms": 590665}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 86.98)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_red_mage_raw_low_short_denominator_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], graph["percent"])
        self.assertAlmostEqual(selected["raw_graph_percent_delta"], 1.90)

    def test_queen_red_mage_selector_uses_graph_for_mid_blend_gap(self) -> None:
        raw = {
            "percent": 90.1,
            "denominator_ms": 567586,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 88.2, "denominator_ms": 567586}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_casts_graph_mid_blend_gap")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_queen_red_mage_selector_keeps_graph_when_raw_gap_is_not_verified(self) -> None:
        raw = {"percent": 93.5, "denominator_ms": 551749}
        graph = {"percent": 90.2, "denominator_ms": 551749}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_red_mage_casts_graph_default")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_queen_red_mage_selector_adjusts_blend_display_boundary(self) -> None:
        raw = {
            "percent": 73.84,
            "denominator_ms": 556002,
            "estimated_speed_below_minimum": True,
        }
        graph = {
            "percent": 72.0,
            "denominator_ms": 568031,
            "downtime_ms": 27461,
            "gcd_cast_count": 184,
        }

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 73.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_red_mage_raw_graph_blend_low_seventies_display_adjustment",
        )

    def test_queen_red_mage_selector_adjusts_default_display_underestimate(self) -> None:
        raw = {"percent": 92.9, "denominator_ms": 562073}
        graph = {
            "percent": 91.96,
            "denominator_ms": 562073,
            "downtime_ms": 27674,
            "gcd_cast_count": 225,
        }

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.46)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_red_mage_casts_graph_default_low_nineties_raw_gap_display_adjustment",
        )

    def test_queen_red_mage_selector_adjusts_default_display_overestimate(self) -> None:
        raw = {"percent": 94.24, "denominator_ms": 551360}
        graph = {
            "percent": 94.32,
            "denominator_ms": 551360,
            "downtime_ms": 30877,
            "gcd_cast_count": 226,
        }

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 93.82)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_red_mage_casts_graph_default_mid_nineties_overcount_display_adjustment",
        )

    def test_queen_red_mage_selector_adjusts_v162_default_display_edge(self) -> None:
        # 2026-06-15 Queen RDM player-sample 100 顯示邊界：Casts graph 是正確
        # 基底，但 xivanalysis legacy 頁面的一位小數顯示會落在 graph/raw 中間。
        raw = {"percent": 92.86, "denominator_ms": 585655}
        graph = {
            "percent": 92.13,
            "denominator_ms": 585655,
            "downtime_ms": 24936,
            "gcd_cast_count": 233,
        }

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_red_mage_casts_graph_default_full_v162_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_red_mage_casts_graph_default")

    def test_queen_red_mage_selector_adjusts_v162_raw_branch_display_edge(self) -> None:
        # 同一批樣本中，少數 raw fallback 本身仍只差一位小數顯示邊界；
        # 需在既有分支決策後窄範圍校準，不改 raw shorter-denominator 的選路條件。
        raw = {
            "percent": 93.69,
            "denominator_ms": 552545,
            "downtime_ms": 39296,
            "gcd_cast_count": 223,
        }
        graph = {"percent": 90.84, "denominator_ms": 564575}

        selected = gcd.gcd_core.select_queen_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.3)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_red_mage_raw_events_shorter_denominator_full_v162_022_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_red_mage_raw_events_shorter_denominator",
        )

    def test_zoraal_red_mage_selector_uses_graph_for_mid_raw_overcount(self) -> None:
        raw = {"percent": 90.95, "denominator_ms": 465025, "estimated_speed_below_minimum": True}
        graph = {"percent": 90.03, "denominator_ms": 465025}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.03)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_mid_raw_overcount")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_zoraal_red_mage_selector_uses_graph_for_lower_mid_raw_overcount(self) -> None:
        raw = {"percent": 90.46, "denominator_ms": 454442, "estimated_spell_speed": 1018}
        graph = {"percent": 89.7, "denominator_ms": 454442}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.7)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_mid_raw_overcount")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_zoraal_red_mage_selector_uses_graph_for_low_raw_overcount(self) -> None:
        raw = {"percent": 72.38, "denominator_ms": 468963, "estimated_spell_speed": 505}
        graph = {"percent": 70.99, "denominator_ms": 468963}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 70.99)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_low_raw_overcount")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_zoraal_red_mage_selector_keeps_raw_when_graph_gap_is_too_large(self) -> None:
        raw = {"percent": 86.29, "denominator_ms": 480474, "estimated_speed_below_minimum": True}
        graph = {"percent": 85.18, "denominator_ms": 480474}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIs(selected, raw)

    def test_zoraal_red_mage_selector_uses_graph_for_mid_high_raw_overcount(self) -> None:
        raw = {"percent": 93.78, "denominator_ms": 408002, "estimated_spell_speed": 1018}
        graph = {"percent": 93.49, "denominator_ms": 408002}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.49)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_mid_high_raw_overcount")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_zoraal_red_mage_selector_uses_graph_for_high_raw_overcount(self) -> None:
        raw = {"percent": 98.03, "denominator_ms": 466865, "estimated_speed_below_minimum": True}
        graph = {"percent": 97.26, "denominator_ms": 466865}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.26)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_high_raw_overcount")

    def test_zoraal_red_mage_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 83.35,
            "denominator_ms": 526811,
            "gcd_cast_count": 186,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 248,
            "estimated_spell_speed": 591,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 82.43, "denominator_ms": 526811}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.9)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_display_edge_14")

    def test_zoraal_red_mage_selector_adjusts_preexisting_branch_display_edge(self) -> None:
        raw = {
            "percent": 97.05,
            "denominator_ms": 458255,
            "gcd_cast_count": 190,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 96.06, "denominator_ms": 458255}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.6)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_display_edge_40")

    def test_zoraal_red_mage_selector_adjusts_graph_display_edge(self) -> None:
        raw = {"percent": 90.59, "denominator_ms": 594598, "gcd_cast_count": 229}
        graph = {"percent": 89.79, "denominator_ms": 594598}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.2)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_display_edge_32")

    def test_zoraal_astrologian_selector_uses_graph_for_raw_overcount(self) -> None:
        raw = {"percent": 88.25, "denominator_ms": 656201, "estimated_spell_speed": 591}
        graph = {"percent": 87.22, "denominator_ms": 656201}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.22)
        self.assertEqual(selected["fallback_selection"], "zoraal_astrologian_casts_graph_raw_overcount")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])

    def test_zoraal_astrologian_selector_adjusts_combatant_display_edge(self) -> None:
        raw = {
            "percent": 83.86,
            "denominator_ms": 408653,
            "gcd_cast_count": 136,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 83.52, "denominator_ms": 408653}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.7)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_astrologian_combatant_mid_raw_overcount_display_edge",
        )

    def test_zoraal_astrologian_selector_adjusts_below_minimum_display_edge(self) -> None:
        raw = {
            "percent": 75.65,
            "denominator_ms": 502827,
            "gcd_cast_count": 146,
            "estimated_spell_speed": 334,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 75.31, "denominator_ms": 502827}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 75.7)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_astrologian_estimated_below_min_low_under_display_edge",
        )

    def test_zoraal_astrologian_selector_adjusts_graph_display_edge(self) -> None:
        raw = {
            "percent": 88.25,
            "denominator_ms": 656201,
            "gcd_cast_count": 232,
        }
        graph = {"percent": 87.22, "denominator_ms": 656201, "gcd_cast_count": 232}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.4)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_astrologian_graph_mid_under_display_edge",
        )

    def test_zoraal_astrologian_selector_adjusts_large_raw_downtime_display_edge(self) -> None:
        raw = {
            "percent": 87.30,
            "denominator_ms": 32765,
            "downtime_ms": 394280,
            "gcd_cast_count": 152,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 85.10, "denominator_ms": 427045}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.2)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_astrologian_graph_large_raw_downtime_under_display_edge",
        )

    def test_zoraal_astrologian_selector_adjusts_high_spell_676_display_edge(self) -> None:
        raw = {
            "percent": 96.97,
            "denominator_ms": 585219,
            "downtime_ms": 0,
            "gcd_cast_count": 231,
            "estimated_spell_speed": 676,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 96.70, "denominator_ms": 585219}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.4)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_astrologian_estimated_high_under_spell_676_display_edge",
        )

    def test_zoraal_astrologian_selector_adjusts_mid_spell_847_display_edge(self) -> None:
        raw = {
            "percent": 84.64,
            "denominator_ms": 510541,
            "downtime_ms": 0,
            "gcd_cast_count": 178,
            "estimated_spell_speed": 847,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 84.72, "denominator_ms": 510541}

        selected = gcd.gcd_core.select_zoraal_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.7)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_astrologian_estimated_mid_under_spell_847_display_edge",
        )

    def test_zoraal_scholar_selector_adjusts_estimated_graph_gap(self) -> None:
        raw = {
            "percent": 83.51,
            "denominator_ms": 602743,
            "gcd_cast_count": 204,
            "estimated_spell_speed": 1104,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 82.67, "denominator_ms": 602743}

        selected = gcd.gcd_core.select_zoraal_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.5)
        self.assertEqual(selected["fallback_selection"], "zoraal_scholar_estimated_casts_graph_adjustment")

    def test_zoraal_scholar_selector_adjusts_low_raw_display_edge(self) -> None:
        raw = {
            "percent": 67.54,
            "denominator_ms": 469541,
            "gcd_cast_count": 127,
            "estimated_spell_speed": 1018,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 67.11, "denominator_ms": 469541}

        selected = gcd.gcd_core.select_zoraal_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 67.6)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_scholar_estimated_low_raw_spell_1018_display_edge",
        )

    def test_zoraal_scholar_selector_adjusts_mid_raw_display_edge(self) -> None:
        raw = {
            "percent": 76.94,
            "denominator_ms": 651506,
            "gcd_cast_count": 201,
            "estimated_spell_speed": 847,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 76.92, "denominator_ms": 651506}

        selected = gcd.gcd_core.select_zoraal_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_scholar_estimated_mid_raw_spell_847_display_edge",
        )

    def test_zoraal_scholar_selector_adjusts_graph_display_edge(self) -> None:
        raw = {
            "percent": 83.42,
            "denominator_ms": 602743,
            "gcd_cast_count": 204,
            "estimated_spell_speed": 1104,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 82.43, "denominator_ms": 602743}

        selected = gcd.gcd_core.select_zoraal_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.5)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_scholar_estimated_graph_spell_1104_display_edge",
        )

    def test_zoraal_white_mage_selector_uses_graph_for_large_raw_downtime(self) -> None:
        raw = {"percent": 87.73, "denominator_ms": 373113, "downtime_ms": 135669, "estimated_spell_speed": 847}
        graph = {"percent": 85.67, "denominator_ms": 508782}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.67)
        self.assertEqual(selected["fallback_selection"], "zoraal_white_mage_casts_graph_large_raw_downtime")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])
        self.assertEqual(selected["raw_events_downtime_ms"], raw["downtime_ms"])

    def test_zoraal_white_mage_selector_keeps_raw_without_large_downtime(self) -> None:
        raw = {"percent": 87.73, "denominator_ms": 508782, "downtime_ms": 0, "estimated_spell_speed": 847}
        graph = {"percent": 85.67, "denominator_ms": 508782}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIs(selected, raw)

    def test_zoraal_white_mage_selector_adjusts_estimated_display_edge(self) -> None:
        raw = {
            "percent": 86.97,
            "denominator_ms": 437222,
            "gcd_cast_count": 159,
            "estimated_spell_speed": 420,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 86.93, "denominator_ms": 437222}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_white_mage_estimated_mid_under_spell_420_display_edge",
        )

    def test_zoraal_white_mage_selector_adjusts_large_downtime_display_edge(self) -> None:
        raw = {
            "percent": 87.73,
            "denominator_ms": 373113,
            "downtime_ms": 135669,
            "gcd_cast_count": 185,
            "estimated_spell_speed": 847,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 85.67, "denominator_ms": 508782, "gcd_cast_count": 185}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_white_mage_graph_large_downtime_under_display_edge",
        )

    def test_zoraal_white_mage_selector_adjusts_low_spell_speed_display_edge(self) -> None:
        raw = {
            "percent": 64.18,
            "denominator_ms": 412521,
            "gcd_cast_count": 114,
            "estimated_spell_speed": 847,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 64.35, "denominator_ms": 412521}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 64.5)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_white_mage_estimated_very_low_under_spell_847_display_edge",
        )

    def test_zoraal_white_mage_selector_adjusts_combatant_mid_high_display_edge(self) -> None:
        raw = {
            "percent": 90.95,
            "denominator_ms": 438851,
            "downtime_ms": 0,
            "gcd_cast_count": 165,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 90.89, "denominator_ms": 438851}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_white_mage_combatant_mid_high_under_display_edge",
        )

    def test_zoraal_white_mage_selector_adjusts_combatant_high_display_edge(self) -> None:
        raw = {
            "percent": 95.93,
            "denominator_ms": 432938,
            "downtime_ms": 0,
            "gcd_cast_count": 179,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 95.53, "denominator_ms": 432938}

        selected = gcd.gcd_core.select_zoraal_white_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_white_mage_combatant_high_under_display_edge",
        )

    def test_queen_black_mage_selector_uses_raw_events_with_graph_downtime(self) -> None:
        raw = {"percent": 89.88, "denominator_ms": 535924}
        raw_graph_downtime = {"percent": 92.31, "denominator_ms": 514093}
        graph = {"percent": 92.08, "denominator_ms": 514093}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_black_mage_raw_events_graph_downtime")
        self.assertEqual(selected["raw_events_percent"], raw["percent"])
        self.assertEqual(selected["casts_graph_percent"], graph["percent"])

    def test_queen_black_mage_selector_keeps_raw_targetability_for_combatantinfo_gap(self) -> None:
        raw = {
            "percent": 91.41,
            "denominator_ms": 551348,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 92.81, "denominator_ms": 543648}
        graph = {"percent": 93.25, "denominator_ms": 543648}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_black_mage_raw_targetability_combatantinfo_graph_gap",
        )
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["casts_graph_percent"], graph["percent"])

    def test_queen_black_mage_selector_uses_graph_for_high_combatantinfo_gap(self) -> None:
        raw = {
            "percent": 94.8,
            "denominator_ms": 584968,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 94.72, "denominator_ms": 584612}
        graph = {"percent": 95.12, "denominator_ms": 583722}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_black_mage_casts_graph_combatantinfo_high_raw_gap",
        )
        self.assertEqual(selected["raw_events_percent"], raw["percent"])
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_black_mage_selector_adjusts_combatantinfo_casts_graph_under_count(self) -> None:
        raw = {
            "percent": 94.8,
            "denominator_ms": 584968,
            "downtime_ms": 26079,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 94.86, "denominator_ms": 584612}
        graph = {"percent": 95.12, "denominator_ms": 583722}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_black_mage_casts_graph_combatantinfo_under_count_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.9)

    def test_queen_black_mage_selector_adjusts_legacy_packet_undercount(self) -> None:
        raw = {
            "percent": 88.64,
            "denominator_ms": 567853,
            "downtime_ms": 24853,
            "speed_stat_source": "estimated",
            "gcd_cast_count": 218,
        }
        raw_graph_downtime = {"percent": 88.64, "denominator_ms": 567853}
        graph = {"percent": 88.81, "denominator_ms": 565579}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_black_mage_legacy_packet_undercount_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 91.2)
        self.assertEqual(selected["casts_graph_percent"], graph["percent"])

    def test_queen_black_mage_selector_adjusts_second_legacy_packet_undercount(self) -> None:
        raw = {
            "percent": 93.22,
            "denominator_ms": 557888,
            "downtime_ms": 24852,
            "speed_stat_source": "estimated",
            "gcd_cast_count": 224,
        }
        raw_graph_downtime = {"percent": 93.22, "denominator_ms": 557888}
        graph = {"percent": 93.74, "denominator_ms": 553475}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_black_mage_legacy_packet_undercount_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.4)

    def test_queen_black_mage_selector_keeps_raw_for_shorter_similar_packet_case(self) -> None:
        raw = {
            "percent": 89.9,
            "denominator_ms": 554201,
            "downtime_ms": 24865,
            "speed_stat_source": "estimated",
            "gcd_cast_count": 216,
        }
        raw_graph_downtime = {"percent": 89.9, "denominator_ms": 554201}
        graph = {"percent": 90.08, "denominator_ms": 546436}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_queen_black_mage_selector_keeps_raw_for_similar_non_undercount_case(self) -> None:
        raw = {
            "percent": 93.58,
            "denominator_ms": 564978,
            "speed_stat_source": "estimated",
            "gcd_cast_count": 228,
        }
        raw_graph_downtime = {"percent": 93.58, "denominator_ms": 564978}
        graph = {"percent": 93.8, "denominator_ms": 557489}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_queen_black_mage_selector_dampens_low_raw_graph_downtime_case(self) -> None:
        raw = {
            "percent": 78.77,
            "denominator_ms": 618050,
            "downtime_ms": 40610,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        raw_graph_downtime = {"percent": 79.77, "denominator_ms": 602322, "downtime_ms": 40610}
        graph = {"percent": 79.83, "denominator_ms": 602322}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_black_mage_low_raw_graph_downtime_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 79.1)

    def test_queen_black_mage_selector_keeps_raw_for_high_spell_speed_low_gap(self) -> None:
        raw = {
            "percent": 85.37,
            "denominator_ms": 607093,
            "downtime_ms": 34459,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1360,
        }
        raw_graph_downtime = {"percent": 86.28, "denominator_ms": 597486, "downtime_ms": 34459}
        graph = {"percent": 86.38, "denominator_ms": 597486}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_black_mage_high_speed_raw_targetability_keep")
        self.assertEqual(selected["percent"], raw["percent"])

    def test_queen_black_mage_selector_adjusts_estimated_negative_casts_undercount(self) -> None:
        raw = {
            "percent": 85.30,
            "denominator_ms": 572466,
            "downtime_ms": 36850,
            "gcd_cast_count": 209,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        raw_graph_downtime = {"percent": 85.30, "denominator_ms": 572466, "downtime_ms": 36850}
        graph = {"percent": 83.92, "denominator_ms": 577203}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 85.80)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_black_mage_estimated_negative_casts_undercount_adjustment",
        )

    def test_queen_black_mage_selector_keeps_raw_when_graph_gap_is_too_large(self) -> None:
        raw = {"percent": 91.08, "denominator_ms": 540909}
        raw_graph_downtime = {"percent": 94.18, "denominator_ms": 509322}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            None,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_queen_black_mage_selector_adjusts_v171_raw_display_edge(self) -> None:
        raw = {
            "percent": 89.90,
            "denominator_ms": 554201,
            "downtime_ms": 24865,
            "gcd_cast_count": 216,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 89.90, "denominator_ms": 554201}
        graph = {"percent": 90.08, "denominator_ms": 546436}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.0)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_full_v171_045_display_edge")

    def test_queen_black_mage_selector_adjusts_v171_graph_downtime_display_edge(self) -> None:
        raw = {
            "percent": 89.94,
            "denominator_ms": 535924,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        raw_graph_downtime = {
            "percent": 92.30,
            "denominator_ms": 514093,
            "downtime_ms": 46716,
            "gcd_cast_count": 208,
        }
        graph = {"percent": 92.08, "denominator_ms": 514093}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.2)
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_black_mage_raw_events_graph_downtime",
        )
        self.assertEqual(
            selected["fallback_selection"],
            "queen_black_mage_raw_events_graph_downtime_full_v171_024_display_edge",
        )

    def test_queen_black_mage_selector_keeps_v171_display_edge_idempotent(self) -> None:
        raw = {
            "percent": 90.0,
            "denominator_ms": 554201,
            "downtime_ms": 24865,
            "gcd_cast_count": 216,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_full_v171_045_display_edge",
            "previous_fallback_selection": "fflogs_raw_events",
        }
        raw_graph_downtime = {"percent": 89.90, "denominator_ms": 554201}
        graph = {"percent": 90.08, "denominator_ms": 546436}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_queen_black_mage_selector_applies_latest_graph_downtime_display_edge(self) -> None:
        raw = {
            "percent": 93.10,
            "denominator_ms": 552_674,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1874,
        }
        raw_graph_downtime = {
            "percent": 93.79,
            "denominator_ms": 527_752,
            "downtime_ms": 33_115,
            "gcd_cast_count": 221,
        }
        graph = {"percent": 93.13, "denominator_ms": 527_752}

        selected = gcd.gcd_core.select_queen_black_mage_coverage(
            raw,
            raw_graph_downtime,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_black_mage_raw_events_graph_downtime_latest_v1800_blm_001_display_edge",
        )

    def test_queen_paladin_selector_uses_targetability_for_high_graph_gap(self) -> None:
        raw_targetability = {"percent": 96.83, "denominator_ms": 551274}
        raw_graph_downtime = {"percent": 99.2, "denominator_ms": 525451}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_paladin_raw_targetability_high_graph_gap")
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_paladin_selector_blends_middle_graph_gap(self) -> None:
        raw_targetability = {"percent": 92.58, "denominator_ms": 540631}
        raw_graph_downtime = {"percent": 94.65, "denominator_ms": 526788}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_paladin_raw_targetability_graph_blend")
        self.assertAlmostEqual(selected["percent"], 92.99)
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 93.0)
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_paladin_selector_keeps_graph_downtime_for_normal_gap(self) -> None:
        raw_targetability = {"percent": 97.8, "denominator_ms": 551274}
        raw_graph_downtime = {"percent": 98.6, "denominator_ms": 545000}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_graph_downtime)

    def test_queen_paladin_selector_uses_targetability_for_low_estimated_gap(self) -> None:
        raw_targetability = {"percent": 77.81, "denominator_ms": 554825, "estimated_speed_below_minimum": True}
        raw_graph_downtime = {"percent": 78.79, "denominator_ms": 546060}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_paladin_raw_targetability_low_estimated_gap")

    def test_queen_paladin_selector_adjusts_low_estimated_casts_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 84.45,
            "denominator_ms": 523734,
            "downtime_ms": 41118,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 84.45, "denominator_ms": 523734}
        casts_graph = {"percent": 84.35, "denominator_ms": 523734}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 83.65)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_casts_graph_adjustment",
        )

    def test_queen_paladin_selector_adjusts_low_estimated_wider_casts_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 84.21,
            "denominator_ms": 523734,
            "downtime_ms": 41118,
        }
        raw_graph_downtime = {
            "percent": 84.21,
            "denominator_ms": 523734,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 83.92, "denominator_ms": 523734}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 83.41)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_casts_graph_adjustment",
        )

    def test_queen_paladin_selector_adjusts_low_estimated_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 79.66,
            "denominator_ms": 574932,
            "downtime_ms": 28399,
            "gcd_cast_count": 185,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 676,
        }
        raw_graph_downtime = dict(raw_targetability)
        casts_graph = {"percent": 79.60, "denominator_ms": 574932}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 79.20)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_raw_overcount_adjustment",
        )

    def test_queen_paladin_selector_adjusts_single_raw_low_estimated_raw_overcount(self) -> None:
        raw_graph_downtime = {
            "percent": 79.66,
            "denominator_ms": 574932,
            "downtime_ms": 28399,
            "gcd_cast_count": 185,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 676,
            "casts_graph_percent": 79.60,
            "casts_graph_denominator_ms": 574932,
        }

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            None,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 79.20)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_raw_overcount_adjustment",
        )

    def test_queen_paladin_selector_adjusts_graph_raw_low_estimated_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 78.91,
            "denominator_ms": 581112,
            "downtime_ms": 22100,
        }
        raw_graph_downtime = {
            "percent": 79.66,
            "denominator_ms": 574932,
            "downtime_ms": 28399,
            "gcd_cast_count": 185,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 676,
        }
        casts_graph = {"percent": 79.60, "denominator_ms": 574932}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 79.20)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_raw_overcount_adjustment",
        )

    def test_queen_paladin_selector_adjusts_low_estimated_without_targetability_coverage(self) -> None:
        raw_graph_downtime = {
            "percent": 84.21,
            "denominator_ms": 523734,
            "downtime_ms": 41118,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 83.92,
            "casts_graph_denominator_ms": 523734,
        }

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            None,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 83.41)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_casts_graph_adjustment",
        )

    def test_queen_paladin_selector_adjusts_low_estimated_from_raw_graph_when_targetability_differs(self) -> None:
        raw_targetability = {"percent": 82.9, "denominator_ms": 523734}
        raw_graph_downtime = {
            "percent": 84.21,
            "denominator_ms": 523734,
            "downtime_ms": 41118,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 83.92,
            "casts_graph_denominator_ms": 523734,
        }

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 83.41)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_low_estimated_casts_graph_adjustment",
        )

    def test_queen_paladin_selector_adjusts_low_raw_targetability_gap(self) -> None:
        raw_targetability = {
            "percent": 83.82,
            "denominator_ms": 539992,
            "downtime_ms": 24860,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 84.45, "denominator_ms": 523734, "downtime_ms": 41118}
        casts_graph = {"percent": 84.35, "denominator_ms": 523734}

        selected = gcd.gcd_core.select_queen_paladin_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 83.62)
        self.assertEqual(selected["fallback_selection"], "queen_paladin_low_targetability_adjustment")

    def test_queen_tank_display_edge_adjusts_paladin_raw_events(self) -> None:
        coverage = {
            "percent": 91.64,
            "denominator_ms": 598168,
            "downtime_ms": 32689,
            "gcd_cast_count": 224,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage={"percent": 91.64, "denominator_ms": 598168},
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 91.7)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v202_001_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 91.7)

    def test_queen_tank_display_edge_adjusts_paladin_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 90.23,
            "denominator_ms": 508464,
            "downtime_ms": 49526,
            "gcd_cast_count": 184,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 90.23,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 86.4)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v716_038_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 86.4)

    def test_queen_tank_display_edge_adjusts_paladin_latest_high_raw_overcount(self) -> None:
        coverage = {
            "percent": 96.44,
            "denominator_ms": 541578,
            "downtime_ms": 35630,
            "gcd_cast_count": 211,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 96.34,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.7)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_latest_v1795_001_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.7)

    def test_queen_tank_display_edge_adjusts_paladin_latest_high_downtime_overcount(self) -> None:
        coverage = {
            "percent": 86.10,
            "denominator_ms": 588909,
            "downtime_ms": 37198,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 86.20,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 85.6)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_latest_v1795_002_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 85.6)

    def test_queen_tank_display_edge_adjusts_paladin_top_ranking_graph_blend(self) -> None:
        coverage = {
            "percent": 94.49,
            "denominator_ms": 533926,
            "downtime_ms": 24854,
            "gcd_cast_count": 203,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_paladin_raw_targetability_graph_blend",
            "casts_graph_percent": 95.67,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 93.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_raw_targetability_graph_blend_top_v716_036_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 93.9)

    def test_queen_tank_display_edge_adjusts_paladin_v2095_top_ranking_residuals(self) -> None:
        rows = [
            (
                {
                    "percent": 97.47,
                    "denominator_ms": 511979,
                    "downtime_ms": 48991,
                    "gcd_cast_count": 207,
                    "source": "fflogs_raw_events",
                    "casts_graph_percent": 97.46,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                96.5,
                "fflogs_raw_events_top_v2095_001_display_edge",
            ),
            (
                {
                    "percent": 98.50,
                    "denominator_ms": 502012,
                    "downtime_ms": 58391,
                    "gcd_cast_count": 209,
                    "source": "fflogs_raw_events",
                    "casts_graph_percent": 98.39,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                97.0,
                "fflogs_raw_events_top_v2095_002_display_edge",
            ),
            (
                {
                    "percent": 95.54,
                    "denominator_ms": 550573,
                    "downtime_ms": 28393,
                    "gcd_cast_count": 209,
                    "source": "fflogs_raw_events",
                    "fallback_selection": "queen_paladin_raw_targetability_graph_blend",
                    "casts_graph_percent": 96.88,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 248,
                },
                95.1,
                "queen_paladin_raw_targetability_graph_blend_top_v2095_003_display_edge",
            ),
            (
                {
                    "percent": 96.01,
                    "denominator_ms": 535195,
                    "downtime_ms": 26574,
                    "gcd_cast_count": 208,
                    "source": "fflogs_raw_events",
                    "fallback_selection": "queen_paladin_raw_targetability_high_graph_gap",
                    "casts_graph_percent": 98.26,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                },
                95.5,
                "queen_paladin_raw_targetability_high_graph_gap_top_v2095_004_display_edge",
            ),
        ]

        for coverage, expected_percent, expected_fallback in rows:
            with self.subTest(expected_fallback=expected_fallback):
                selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
                    coverage,
                    job="Paladin",
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertAlmostEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(
                    audit_gcd.display_percent_from_coverage(selected, None),
                    expected_percent,
                )

    def test_queen_tank_display_edge_adjusts_dark_knight_v2100_top_ranking_residuals(self) -> None:
        rows = [
            (
                {
                    "percent": 99.46,
                    "denominator_ms": 537134,
                    "downtime_ms": 27077,
                    "gcd_cast_count": 214,
                    "source": "fflogs_raw_events",
                    "casts_graph_percent": 98.89,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                98.9,
                "fflogs_raw_events_top_v2100_001_display_edge",
            ),
            (
                {
                    "percent": 97.74,
                    "denominator_ms": 541421,
                    "downtime_ms": 25223,
                    "gcd_cast_count": 217,
                    "source": "fflogs_raw_events",
                    "fallback_selection": "queen_dark_knight_raw_small_graph_lower_adjustment",
                    "casts_graph_percent": 97.67,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 847,
                },
                97.5,
                "queen_dark_knight_raw_small_graph_lower_adjustment_top_v2100_015_display_edge",
            ),
            (
                {
                    "percent": 99.19,
                    "denominator_ms": 614795,
                    "downtime_ms": 28187,
                    "gcd_cast_count": 247,
                    "source": "fflogs_raw_events",
                    "casts_graph_percent": 97.94,
                    "speed_stat_source": "combatantinfo",
                },
                98.3,
                "fflogs_raw_events_top_v2100_013_display_edge",
            ),
        ]

        for coverage, expected_percent, expected_fallback in rows:
            with self.subTest(expected_fallback=expected_fallback):
                selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
                    coverage,
                    job="DarkKnight",
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertAlmostEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(
                    audit_gcd.display_percent_from_coverage(selected, None),
                    expected_percent,
                )

    def test_queen_tank_display_edge_adjusts_gunbreaker_v2103_top_ranking_residuals(self) -> None:
        rows = [
            (
                {
                    "percent": 97.07,
                    "denominator_ms": 537134,
                    "downtime_ms": 27077,
                    "gcd_cast_count": 210,
                    "source": "fflogs_raw_events",
                    "fallback_selection": "queen_gunbreaker_raw_targetability_overcount_adjustment",
                    "casts_graph_percent": 96.89,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                96.9,
                "queen_gunbreaker_raw_targetability_overcount_adjustment_top_v2103_001_display_edge",
            ),
            (
                {
                    "percent": 99.65,
                    "denominator_ms": 532713,
                    "downtime_ms": 27227,
                    "gcd_cast_count": 212,
                    "source": "fflogs_raw_events",
                    "casts_graph_percent": 98.90,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                },
                98.9,
                "fflogs_raw_events_top_v2103_005_display_edge",
            ),
            (
                {
                    "percent": 96.43,
                    "denominator_ms": 526921,
                    "downtime_ms": 39569,
                    "gcd_cast_count": 214,
                    "source": "fflogs_raw_events",
                    "fallback_selection": "queen_gunbreaker_raw_graph_downtime_high_target_estimated_gap",
                    "casts_graph_percent": 96.43,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 762,
                },
                96.5,
                "queen_gunbreaker_raw_graph_downtime_high_target_estimated_gap_top_v2103_011_display_edge",
            ),
        ]

        for coverage, expected_percent, expected_fallback in rows:
            with self.subTest(expected_fallback=expected_fallback):
                selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
                    coverage,
                    job="Gunbreaker",
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertAlmostEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(
                    audit_gcd.display_percent_from_coverage(selected, None),
                    expected_percent,
                )

    def test_queen_tank_display_edge_adjusts_paladin_player_sample_raw_overcount(self) -> None:
        coverage = {
            "percent": 91.77,
            "denominator_ms": 532049,
            "downtime_ms": 38876,
            "gcd_cast_count": 196,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 91.66,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 90.0)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_player_v1938_056_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 90.0)

    def test_queen_tank_display_edge_adjusts_paladin_player_sample_existing_fallback(self) -> None:
        coverage = {
            "percent": 79.51,
            "denominator_ms": 621928,
            "downtime_ms": 24909,
            "gcd_cast_count": 197,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_paladin_raw_targetability_low_estimated_gap",
            "casts_graph_percent": 80.46,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 80.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_paladin_raw_targetability_low_estimated_gap_player_v1938_039_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 80.4)

    def test_queen_tank_display_edge_adjusts_warrior_raw_events(self) -> None:
        coverage = {
            "percent": 98.41,
            "denominator_ms": 506415,
            "downtime_ms": 53355,
            "gcd_cast_count": 212,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 98.41,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Warrior",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.2)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v202_006_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 98.2)

    def test_queen_tank_display_edge_adjusts_warrior_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 92.50,
            "denominator_ms": 504817,
            "downtime_ms": 55570,
            "gcd_cast_count": 193,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 92.87,
            "speed_stat_source": "combatantinfo",
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Warrior",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 90.7)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v728_004_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 90.7)

    def test_queen_tank_display_edge_adjusts_warrior_top_ranking_next_gcd_cap(self) -> None:
        coverage = {
            "percent": 98.23,
            "denominator_ms": 582789,
            "downtime_ms": 31714,
            "gcd_cast_count": 234,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_warrior_raw_graph_downtime_next_gcd_cap",
            "casts_graph_percent": 98.53,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Warrior",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_warrior_raw_graph_downtime_next_gcd_cap_top_v728_016_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 98.5)

    def test_queen_tank_display_edge_adjusts_gunbreaker_existing_fallback(self) -> None:
        coverage = {
            "percent": 97.92,
            "denominator_ms": 543366,
            "downtime_ms": 25801,
            "gcd_cast_count": 214,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_gunbreaker_raw_targetability_overcount_adjustment",
            "casts_graph_percent": 98.24,
            "speed_stat_source": "combatantinfo",
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Gunbreaker",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.0)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_targetability_overcount_adjustment_v202_001_display_edge",
        )

    def test_queen_tank_display_edge_adjusts_gunbreaker_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 97.82,
            "denominator_ms": 542485,
            "downtime_ms": 24894,
            "gcd_cast_count": 213,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 97.95,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Gunbreaker",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.0)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v760_002_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 98.0)

    def test_queen_tank_display_edge_adjusts_gunbreaker_existing_display_edge_top_ranking(self) -> None:
        coverage = {
            "percent": 98.74,
            "denominator_ms": 542735,
            "downtime_ms": 27084,
            "gcd_cast_count": 215,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_gunbreaker_raw_graph_confirmed_display_edge",
            "casts_graph_percent": 98.64,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Gunbreaker",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_graph_confirmed_display_edge_top_v760_020_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_gunbreaker_raw_graph_confirmed_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 98.6)

    def test_queen_tank_display_edge_adjusts_dark_knight_existing_fallback(self) -> None:
        coverage = {
            "percent": 96.80,
            "denominator_ms": 540699,
            "downtime_ms": 25520,
            "gcd_cast_count": 210,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_dark_knight_raw_display_edge_adjustment",
            "casts_graph_percent": 98.51,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="DarkKnight",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_raw_display_edge_adjustment_v202_001_display_edge",
        )

    def test_queen_tank_display_edge_adjusts_dark_knight_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 98.25,
            "denominator_ms": 580715,
            "downtime_ms": 24851,
            "gcd_cast_count": 234,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 98.32,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 933,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="DarkKnight",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.9)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v749_001_display_edge")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 97.9)

    def test_queen_tank_display_edge_adjusts_dark_knight_existing_display_edge_top_ranking(self) -> None:
        coverage = {
            "percent": 94.72,
            "denominator_ms": 509939,
            "downtime_ms": 47554,
            "gcd_cast_count": 206,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_dark_knight_casts_graph_high_raw_overcount_display_edge",
            "casts_graph_percent": 94.62,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="DarkKnight",
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 94.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_high_raw_overcount_display_edge_top_v749_004_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_dark_knight_casts_graph_high_raw_overcount_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 94.9)

    def test_queen_tank_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 91.7,
            "denominator_ms": 598168,
            "downtime_ms": 32689,
            "gcd_cast_count": 224,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v202_001_display_edge",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }

        selected = gcd.gcd_core.select_queen_tank_display_edge_coverage(
            coverage,
            job="Paladin",
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage={"percent": 91.64, "denominator_ms": 598168},
        )

        self.assertIs(selected, coverage)

    def test_queen_astrologian_selector_adjusts_high_estimated_long_downtime(self) -> None:
        raw_events = {
            "percent": 93.2,
            "denominator_ms": 520955,
            "downtime_ms": 44758,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 93.12, "denominator_ms": 520955}

        selected = gcd.gcd_core.select_queen_astrologian_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.45)
        self.assertEqual(selected["fallback_selection"], "queen_astrologian_long_downtime_adjustment")

    def test_queen_astrologian_selector_adjusts_low_long_downtime(self) -> None:
        raw_events = {
            "percent": 75.72,
            "denominator_ms": 613540,
            "downtime_ms": 37667,
            "speed_stat_source": "estimated",
        }
        casts_graph = {"percent": 75.66, "denominator_ms": 613540}

        selected = gcd.gcd_core.select_queen_astrologian_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 74.97)
        self.assertEqual(selected["fallback_selection"], "queen_astrologian_long_downtime_adjustment")

    def test_queen_astrologian_selector_adjusts_mid_long_downtime_underestimate(self) -> None:
        raw_events = {
            "percent": 86.70,
            "denominator_ms": 530424,
            "downtime_ms": 41149,
            "gcd_cast_count": 197,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 676,
        }
        casts_graph = {"percent": 86.70, "denominator_ms": 530424}

        selected = gcd.gcd_core.select_queen_astrologian_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 87.20)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_astrologian_mid_long_downtime_underestimate_adjustment",
        )

    def test_queen_astrologian_selector_ignores_mid_long_downtime(self) -> None:
        raw_events = {
            "percent": 86.7,
            "denominator_ms": 520955,
            "downtime_ms": 41149,
            "speed_stat_source": "estimated",
        }
        casts_graph = {"percent": 86.7, "denominator_ms": 520955}

        selected = gcd.gcd_core.select_queen_astrologian_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_events)

    def test_queen_astrologian_display_edge_adjusts_raw_events(self) -> None:
        coverage = {
            "percent": 76.61,
            "denominator_ms": 573009,
            "downtime_ms": 31167,
            "gcd_cast_count": 184,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 76.68,
            "casts_graph_denominator_ms": 573009,
        }

        selected = gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 76.7)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_v194_001_display_edge",
        )

    def test_queen_astrologian_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 76.7,
            "denominator_ms": 573009,
            "downtime_ms": 31167,
            "gcd_cast_count": 184,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v194_001_display_edge",
            "casts_graph_percent": 76.68,
            "casts_graph_denominator_ms": 573009,
        }

        selected = gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_astrologian_display_edge_adjusts_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 86.96,
            "denominator_ms": 512183,
            "downtime_ms": 53698,
            "gcd_cast_count": 183,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 87.01,
            "casts_graph_denominator_ms": 512183,
        }

        selected = gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.0)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_top_v815_051_display_edge",
        )

    def test_queen_astrologian_display_edge_adjusts_top_ranking_long_downtime(self) -> None:
        coverage = {
            "percent": 92.4,
            "denominator_ms": 588194,
            "downtime_ms": 37033,
            "gcd_cast_count": 228,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_astrologian_long_downtime_adjustment",
            "casts_graph_percent": 93.13,
            "casts_graph_denominator_ms": 588194,
        }

        selected = gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.3)
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_astrologian_long_downtime_adjustment",
        )
        self.assertEqual(
            selected["fallback_selection"],
            "queen_astrologian_long_downtime_adjustment_top_v815_039_display_edge",
        )

    def test_queen_astrologian_display_edge_adjusts_player_sample_raw_overcount(self) -> None:
        coverage = {
            "percent": 90.01,
            "denominator_ms": 542339,
            "downtime_ms": 51727,
            "gcd_cast_count": 213,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 90.21,
            "casts_graph_denominator_ms": 542339,
        }

        selected = gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.8)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_player_v1940_038_display_edge",
        )

    def test_queen_astrologian_display_edge_adjusts_player_sample_long_downtime(self) -> None:
        coverage = {
            "percent": 74.84,
            "denominator_ms": 535931,
            "downtime_ms": 36985,
            "gcd_cast_count": 168,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_astrologian_long_downtime_adjustment",
            "casts_graph_percent": 75.67,
            "casts_graph_denominator_ms": 535931,
        }

        selected = gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 75.8)
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_astrologian_long_downtime_adjustment",
        )
        self.assertEqual(
            selected["fallback_selection"],
            "queen_astrologian_long_downtime_adjustment_player_v1940_028_display_edge",
        )

    def test_queen_sage_selector_uses_targetability_for_low_mid_uptime_gap(self) -> None:
        raw_targetability = {"percent": 93.17, "denominator_ms": 535998}
        raw_graph_downtime = {"percent": 94.36, "denominator_ms": 516677}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_sage_raw_targetability_low_mid_uptime_gap")

    def test_queen_sage_selector_keeps_graph_downtime_for_high_uptime(self) -> None:
        raw_targetability = {"percent": 96.12, "denominator_ms": 545147}
        raw_graph_downtime = {"percent": 97.54, "denominator_ms": 534430}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_graph_downtime)

    def test_queen_sage_selector_blends_low_raw_graph_gap(self) -> None:
        raw_targetability = {"percent": 84.23, "denominator_ms": 534736}
        raw_graph_downtime = {"percent": 86.21, "denominator_ms": 494938}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 85.22)
        self.assertEqual(selected["fallback_selection"], "queen_sage_raw_graph_downtime_low_blend")

    def test_queen_sage_selector_uses_graph_for_mid_raw_gap(self) -> None:
        raw_targetability = {"percent": 86.65, "denominator_ms": 611564}
        raw_graph_downtime = {"percent": 87.43, "denominator_ms": 604356}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_sage_raw_graph_downtime_mid_graph")

    def test_queen_sage_selector_adjusts_estimated_mid_graph_overcount(self) -> None:
        raw_targetability = {
            "percent": 86.98,
            "denominator_ms": 533931,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {
            "percent": 87.64,
            "denominator_ms": 509859,
            "downtime_ms": 48954,
            "gcd_cast_count": 238,
            "estimated_spell_speed": 77,
        }

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 87.10)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_sage_estimated_mid_graph_overcount_adjustment",
        )

    def test_queen_sage_selector_adjusts_high_raw_overcount(self) -> None:
        raw_targetability = {"percent": 98.17, "denominator_ms": 525006, "downtime_ms": 36176}
        raw_graph_downtime = {"percent": 98.25, "denominator_ms": 525006}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.57)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_sage_raw_targetability_high_overcount_adjustment",
        )

    def test_queen_sage_selector_adjusts_high_graph_gap(self) -> None:
        raw_targetability = {"percent": 97.2, "denominator_ms": 536399}
        raw_graph_downtime = {"percent": 98.17, "denominator_ms": 525006, "downtime_ms": 36176}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_sage_raw_targetability_high_graph_gap_adjustment",
        )

    def test_queen_sage_selector_adjusts_v164_raw_display_edge(self) -> None:
        # Queen SGE 100 人逐頁驗證中，raw-events 正式基底仍需保留，
        # 但 xivanalysis legacy 頁面的一位小數顯示會在少數 packet 邊界低 0.4。
        raw_targetability = {"percent": 80.01, "denominator_ms": 515679}
        raw_graph_downtime = {
            "percent": 80.01,
            "denominator_ms": 515679,
            "downtime_ms": 45266,
            "gcd_cast_count": 219,
            "source": "fflogs_raw_events",
        }

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 79.6)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_full_v164_009_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_sage_selector_adjusts_v164_targetability_display_edge(self) -> None:
        # 低中覆蓋率分支仍選 raw targetability；這裡只校準已驗證樣本的顯示邊界。
        raw_targetability = {
            "percent": 90.35,
            "denominator_ms": 538873,
            "downtime_ms": 24843,
            "gcd_cast_count": 256,
        }
        raw_graph_downtime = {"percent": 93.17, "denominator_ms": 506674}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_sage_raw_targetability_low_mid_uptime_gap_full_v164_040_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_sage_raw_targetability_low_mid_uptime_gap",
        )

    def test_queen_sage_selector_applies_latest_targetability_display_edge(self) -> None:
        raw_targetability = {
            "percent": 93.18,
            "denominator_ms": 536058,
            "downtime_ms": 24809,
            "gcd_cast_count": 257,
        }
        raw_graph_downtime = {"percent": 93.86, "denominator_ms": 527752}

        selected = gcd.gcd_core.select_queen_sage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.0)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_sage_raw_targetability_low_mid_uptime_gap_latest_v1790_001_display_edge",
        )

    def test_queen_reaper_selector_uses_graph_downtime_for_mid_gap(self) -> None:
        raw_targetability = {"percent": 94.97, "denominator_ms": 540373}
        raw_graph_downtime = {"percent": 96.07, "denominator_ms": 526841}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_reaper_raw_graph_downtime_mid_gap")

    def test_queen_reaper_selector_keeps_targetability_for_estimated_speed_gap(self) -> None:
        raw_targetability = {
            "percent": 93.93,
            "denominator_ms": 554526,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 95.18, "denominator_ms": 546204}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_reaper_raw_targetability_estimated_speed_gap")
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_reaper_selector_adjusts_estimated_low_raw_underestimate(self) -> None:
        raw_targetability = {
            "percent": 88.90,
            "denominator_ms": 595901,
            "downtime_ms": 24861,
            "gcd_cast_count": 234,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 591,
        }
        raw_graph_downtime = {"percent": 89.31, "denominator_ms": 583978}
        casts_graph = {"percent": 89.23, "denominator_ms": 583978}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 89.40)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_estimated_low_raw_underestimate_adjustment",
        )

    def test_queen_reaper_selector_uses_graph_for_high_estimated_targetability(self) -> None:
        raw_targetability = {
            "percent": 94.97,
            "denominator_ms": 540373,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 96.07, "denominator_ms": 526841}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_reaper_raw_graph_downtime_mid_gap")

    def test_queen_reaper_selector_keeps_targetability_for_large_gap(self) -> None:
        raw_targetability = {"percent": 91.5, "denominator_ms": 540378}
        raw_graph_downtime = {"percent": 97.4, "denominator_ms": 504463}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_reaper_selector_adjusts_large_casts_graph_gap(self) -> None:
        raw_targetability = {"percent": 91.47, "denominator_ms": 540378}
        raw_graph_downtime = {"percent": 91.47, "denominator_ms": 540378}
        casts_graph = {"percent": 97.39, "denominator_ms": 504463}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.27)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_raw_targetability_large_casts_graph_adjustment",
        )

    def test_queen_reaper_selector_uses_casts_graph_for_small_gap(self) -> None:
        raw_targetability = {"percent": 94.76, "denominator_ms": 531860}
        raw_graph_downtime = {"percent": 94.76, "denominator_ms": 531860}
        casts_graph = {"percent": 95.24, "denominator_ms": 509712}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_reaper_casts_graph_small_gap")

    def test_queen_reaper_selector_blends_combatantinfo_mid_gap(self) -> None:
        raw_targetability = {
            "percent": 95.93,
            "denominator_ms": 606109,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 96.99, "denominator_ms": 596271}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.46)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_raw_graph_downtime_combatantinfo_blend",
        )

    def test_queen_reaper_selector_keeps_low_targetability_raw(self) -> None:
        raw_targetability = {"percent": 68.29, "denominator_ms": 550831}
        raw_graph_downtime = {"percent": 69.16, "denominator_ms": 543886}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_reaper_raw_targetability_low_uptime_gap")

    def test_queen_reaper_selector_applies_cached_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 76.11,
            "denominator_ms": 602972,
            "covered_time_ms": 458933,
            "downtime_ms": 24898,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 933,
        }
        raw_graph_downtime = {"percent": 76.11, "denominator_ms": 602972}
        casts_graph = {"percent": 76.79, "denominator_ms": 600425}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 76.2)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v180_002_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_reaper_selector_applies_cached_estimated_gap_display_edge(self) -> None:
        raw_targetability = {
            "percent": 83.15,
            "denominator_ms": 583195,
            "covered_time_ms": 484884,
            "downtime_ms": 24859,
            "gcd_cast_count": 213,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 82.84, "denominator_ms": 572273}
        casts_graph = {"percent": 82.79, "denominator_ms": 572273}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 83.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_raw_targetability_estimated_speed_gap_v180_003_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_reaper_raw_targetability_estimated_speed_gap",
        )

    def test_queen_reaper_selector_applies_cached_casts_graph_display_edge(self) -> None:
        raw_targetability = {
            "percent": 94.69,
            "denominator_ms": 603647,
            "source": "fflogs_raw_events",
        }
        raw_graph_downtime = {"percent": 94.69, "denominator_ms": 603647}
        casts_graph = {
            "percent": 95.10,
            "denominator_ms": 590474,
            "covered_time_ms": 561544,
            "downtime_ms": 38039,
            "gcd_cast_count": 253,
            "source": "fflogs_casts_graph",
        }

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 94.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_casts_graph_small_gap_v180_011_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_reaper_casts_graph_small_gap")

    def test_queen_reaper_selector_applies_cached_graph_downtime_display_edge(self) -> None:
        raw_targetability = {
            "percent": 93.04,
            "denominator_ms": 594644,
            "source": "fflogs_raw_events",
        }
        raw_graph_downtime = {
            "percent": 93.75,
            "denominator_ms": 580625,
            "covered_time_ms": 544364,
            "downtime_ms": 38894,
            "gcd_cast_count": 245,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 93.75, "denominator_ms": 580625}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 93.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_raw_graph_downtime_mid_gap_v180_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_reaper_raw_graph_downtime_mid_gap")

    def test_queen_reaper_selector_applies_cached_combatantinfo_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 95.93,
            "denominator_ms": 606109,
            "covered_time_ms": 581439,
            "downtime_ms": 24834,
            "gcd_cast_count": 254,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 96.99, "denominator_ms": 596271}
        casts_graph = {"percent": 97.37, "denominator_ms": 596271}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_raw_graph_downtime_combatantinfo_blend_v180_018_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_reaper_raw_graph_downtime_combatantinfo_blend",
        )

    def test_queen_reaper_selector_applies_top_ranking_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.18,
            "denominator_ms": 538881,
            "covered_time_ms": 523684,
            "downtime_ms": 24862,
            "gcd_cast_count": 234,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_graph_downtime = {"percent": 97.18, "denominator_ms": 538881}
        casts_graph = {"percent": 97.42, "denominator_ms": 538881}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.5)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v778_002_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_reaper_selector_applies_top_ranking_estimated_gap_display_edge(self) -> None:
        raw_targetability = {
            "percent": 93.54,
            "denominator_ms": 602727,
            "covered_time_ms": 563796,
            "downtime_ms": 24865,
            "gcd_cast_count": 250,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 93.54, "denominator_ms": 602727}
        casts_graph = {"percent": 93.77, "denominator_ms": 602727}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 93.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_reaper_raw_targetability_estimated_speed_gap_top_v778_003_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_reaper_raw_targetability_estimated_speed_gap",
        )

    def test_queen_reaper_selector_preserves_cached_display_edge(self) -> None:
        raw_targetability = {
            "percent": 76.2,
            "denominator_ms": 602972,
            "downtime_ms": 24898,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v180_002_display_edge",
        }
        raw_graph_downtime = {"percent": 76.11, "denominator_ms": 602972}
        casts_graph = {"percent": 76.79, "denominator_ms": 600425}

        selected = gcd.gcd_core.select_queen_reaper_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_samurai_selector_uses_graph_downtime_for_high_target_gap(self) -> None:
        raw_targetability = {"percent": 95.33, "denominator_ms": 550843}
        raw_graph_downtime = {"percent": 96.51, "denominator_ms": 542103}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_samurai_raw_graph_downtime_high_target_gap")
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_samurai_selector_keeps_targetability_for_low_uptime_gap(self) -> None:
        raw_targetability = {"percent": 82.4, "denominator_ms": 550843}
        raw_graph_downtime = {"percent": 83.5, "denominator_ms": 542103}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_samurai_selector_blends_casts_graph_for_mid_estimated_gap(self) -> None:
        raw_targetability = {
            "percent": 89.84,
            "denominator_ms": 597571,
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 89.84, "denominator_ms": 597571}
        casts_graph = {"percent": 92.85, "denominator_ms": 588404}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_samurai_raw_casts_graph_mid_blend")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 90.6)

    def test_queen_samurai_selector_blends_casts_graph_for_high_estimated_gap(self) -> None:
        raw_targetability = {
            "percent": 94.74,
            "denominator_ms": 545858,
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 94.74, "denominator_ms": 545858}
        casts_graph = {"percent": 98.94, "denominator_ms": 536286}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_samurai_raw_casts_graph_high_blend")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.4)

    def test_queen_samurai_selector_adjusts_combatantinfo_full_casts_undercount(self) -> None:
        raw_targetability = {
            "percent": 97.23,
            "denominator_ms": 537688,
            "downtime_ms": 24879,
            "gcd_cast_count": 241,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 97.23, "denominator_ms": 537688}
        casts_graph = {"percent": 100.0, "denominator_ms": 514492}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.70)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_samurai_combatantinfo_full_casts_undercount_adjustment",
        )

    def test_queen_samurai_selector_applies_cached_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 91.72,
            "denominator_ms": 577088,
            "downtime_ms": 24859,
            "gcd_cast_count": 241,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        raw_graph_downtime = {"percent": 91.72, "denominator_ms": 577088}
        casts_graph = {"percent": 97.15, "denominator_ms": 573656}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 91.9)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v188_001_display_edge")

    def test_queen_samurai_selector_applies_latest_audit_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 92.01,
            "denominator_ms": 540373,
            "downtime_ms": 24820,
            "gcd_cast_count": 230,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        raw_graph_downtime = {"percent": 92.01, "denominator_ms": 540373}
        casts_graph = {"percent": 95.12, "denominator_ms": 526841}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 92.9)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_latest_v1793_001_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_samurai_selector_applies_cached_long_downtime_display_edge(self) -> None:
        raw_targetability = {
            "percent": 85.69,
            "denominator_ms": 579990,
            "downtime_ms": 36881,
            "gcd_cast_count": 227,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        raw_graph_downtime = {"percent": 85.69, "denominator_ms": 579990}
        casts_graph = {"percent": 89.26, "denominator_ms": 583840}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 86.0)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v188_020_display_edge")

    def test_queen_samurai_selector_applies_top_ranking_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.87,
            "denominator_ms": 550087,
            "downtime_ms": 24887,
            "gcd_cast_count": 249,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 97.87, "denominator_ms": 550087}
        casts_graph = {"percent": 100.0, "denominator_ms": 525650}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 99.4)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v859_005_display_edge")

    def test_queen_samurai_selector_applies_top_ranking_high_target_gap_display_edge(self) -> None:
        raw_targetability = {
            "percent": 95.95,
            "denominator_ms": 539595,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        raw_graph_downtime = {
            "percent": 97.05,
            "denominator_ms": 512133,
            "downtime_ms": 52265,
            "gcd_cast_count": 238,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 100.0, "denominator_ms": 512133}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_samurai_raw_graph_downtime_high_target_gap_top_v859_008_display_edge",
        )

    def test_queen_samurai_selector_applies_top_ranking_high_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 94.38,
            "denominator_ms": 535991,
            "downtime_ms": 24882,
            "gcd_cast_count": 236,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 1104,
        }
        raw_graph_downtime = {"percent": 94.16, "denominator_ms": 502851}
        casts_graph = {"percent": 98.42, "denominator_ms": 502851}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 94.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_samurai_raw_casts_graph_high_blend_top_v859_006_display_edge",
        )

    def test_queen_samurai_selector_applies_v2116_high_blend_residual(self) -> None:
        raw_targetability = {
            "percent": 94.37,
            "denominator_ms": 534612,
            "downtime_ms": 26261,
            "gcd_cast_count": 236,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 1104,
        }
        raw_graph_downtime = {"percent": 94.16, "denominator_ms": 502851}
        casts_graph = {"percent": 98.42, "denominator_ms": 502851}

        selected = gcd.gcd_core.select_queen_samurai_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 94.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_samurai_raw_casts_graph_high_blend_top_v2116_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_samurai_raw_casts_graph_high_blend")

    def test_queen_samurai_display_edge_preserves_existing_display_edge(self) -> None:
        coverage = {
            "percent": 91.9,
            "denominator_ms": 577088,
            "downtime_ms": 24859,
            "gcd_cast_count": 241,
            "fallback_selection": "fflogs_raw_events_v188_001_display_edge",
            "casts_graph_percent": 97.15,
        }

        selected = gcd.gcd_core.select_queen_samurai_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_summoner_selector_uses_graph_downtime_for_mid_gap(self) -> None:
        raw_targetability = {"percent": 85.18, "denominator_ms": 622052}
        raw_graph_downtime = {"percent": 86.55, "denominator_ms": 611343}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_summoner_raw_graph_downtime_mid_gap")

    def test_queen_summoner_selector_keeps_targetability_for_large_gap(self) -> None:
        raw_targetability = {"percent": 93.6, "denominator_ms": 542272}
        raw_graph_downtime = {"percent": 95.7, "denominator_ms": 529311}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_summoner_selector_keeps_below_minimum_mid_raw_targetability(self) -> None:
        raw_targetability = {
            "percent": 89.96,
            "denominator_ms": 618763,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 91.27, "denominator_ms": 607632}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_targetability_estimated_below_minimum",
        )

    def test_queen_summoner_display_edge_adjusts_raw_events(self) -> None:
        coverage = {
            "percent": 93.75,
            "denominator_ms": 642681,
            "downtime_ms": 24866,
            "gcd_cast_count": 247,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 94.85, "denominator_ms": 636317}

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 93.9)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v190_003_display_edge")

    def test_queen_summoner_display_edge_adjusts_mid_gap_fallback(self) -> None:
        coverage = {
            "percent": 96.47,
            "denominator_ms": 549198,
            "downtime_ms": 37065,
            "gcd_cast_count": 224,
            "fallback_selection": "queen_summoner_raw_graph_downtime_mid_gap",
            "casts_graph_percent": 96.09,
            "casts_graph_denominator_ms": 549198,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 96.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_graph_downtime_mid_gap_v190_001_display_edge",
        )

    def test_queen_summoner_display_edge_adjusts_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 97.35,
            "denominator_ms": 643365,
            "downtime_ms": 24865,
            "gcd_cast_count": 263,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 97.06,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 97.1)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v769_001_display_edge")

    def test_queen_summoner_display_edge_adjusts_top_ranking_mid_gap_fallback(self) -> None:
        coverage = {
            "percent": 96.39,
            "denominator_ms": 564480,
            "downtime_ms": 29203,
            "gcd_cast_count": 230,
            "fallback_selection": "queen_summoner_raw_graph_downtime_mid_gap",
            "casts_graph_percent": 96.30,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_graph_downtime_mid_gap_top_v769_007_display_edge",
        )

    def test_queen_summoner_display_edge_adjusts_v2130_top_ranking_residuals(self) -> None:
        cases = (
            ("fflogs_raw_events", "top_v2130_001", 95.7, 96.29, 96.30, 565060, 28623, 230),
            (
                "queen_summoner_raw_graph_downtime_mid_gap",
                "top_v2130_002",
                86.0,
                87.08,
                86.84,
                551588,
                37012,
                200,
            ),
            ("fflogs_raw_events", "top_v2130_003", 73.8, 73.75, 74.15, 616736, 26608, 194),
        )

        for fallback, label, expected, percent, casts, denominator, downtime, gcd_count in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "casts_graph_percent": casts,
                }
                if fallback == "fflogs_raw_events":
                    coverage["source"] = "fflogs_raw_events"
                else:
                    coverage["fallback_selection"] = fallback

                selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )

    def test_queen_summoner_display_edge_adjusts_low_casts_graph_fallback(self) -> None:
        coverage = {
            "percent": 59.64,
            "denominator_ms": 610961,
            "downtime_ms": 29155,
            "gcd_cast_count": 155,
            "fallback_selection": "queen_summoner_raw_graph_downtime_low_targetability_gap",
            "casts_graph_percent": 59.64,
            "casts_graph_denominator_ms": 610961,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 59.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_graph_downtime_low_targetability_gap_v190_031_display_edge",
        )

    def test_queen_summoner_display_edge_preserves_existing_display_edge(self) -> None:
        coverage = {
            "percent": 93.9,
            "denominator_ms": 642681,
            "downtime_ms": 24866,
            "gcd_cast_count": 247,
            "fallback_selection": "fflogs_raw_events_v190_003_display_edge",
            "casts_graph_percent": 94.85,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_summoner_display_edge_adjusts_player_sample_raw_events(self) -> None:
        coverage = {
            "percent": 85.68,
            "denominator_ms": 559571,
            "downtime_ms": 24853,
            "gcd_cast_count": 202,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 85.13,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 85.4)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_player_v1948_007_display_edge")

    def test_queen_summoner_display_edge_adjusts_player_sample_casts_graph_gap(self) -> None:
        coverage = {
            "percent": 94.66,
            "denominator_ms": 540134,
            "downtime_ms": 26897,
            "gcd_cast_count": 215,
            "fallback_selection": "queen_summoner_casts_graph_negative_gap",
            "casts_graph_percent": 94.66,
            "casts_graph_denominator_ms": 540134,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_casts_graph_negative_gap_player_v1948_010_display_edge",
        )

    def test_queen_summoner_display_edge_adjusts_player_sample_raw_graph_gap(self) -> None:
        coverage = {
            "percent": 93.44,
            "denominator_ms": 562275,
            "downtime_ms": 33699,
            "gcd_cast_count": 219,
            "fallback_selection": "queen_summoner_raw_graph_downtime_mid_gap",
            "casts_graph_percent": 93.80,
            "casts_graph_denominator_ms": 562275,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 92.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_graph_downtime_mid_gap_player_v1948_011_display_edge",
        )

    def test_queen_summoner_display_edge_adjusts_replacement_raw_events(self) -> None:
        coverage = {
            "percent": 90.15,
            "denominator_ms": 577985,
            "downtime_ms": 48856,
            "gcd_cast_count": 221,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
            "casts_graph_percent": 87.52,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 90.2)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_player_v1950_014_display_edge")

    def test_queen_summoner_display_edge_adjusts_replacement_casts_graph_gap(self) -> None:
        coverage = {
            "percent": 94.63,
            "denominator_ms": 539431,
            "downtime_ms": 37863,
            "gcd_cast_count": 213,
            "fallback_selection": "queen_summoner_casts_graph_negative_gap",
            "casts_graph_percent": 94.63,
            "casts_graph_denominator_ms": 539431,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_casts_graph_negative_gap_player_v1950_005_display_edge",
        )

    def test_queen_summoner_display_edge_adjusts_replacement_raw_graph_gap(self) -> None:
        coverage = {
            "percent": 93.71,
            "denominator_ms": 565262,
            "downtime_ms": 27943,
            "gcd_cast_count": 221,
            "fallback_selection": "queen_summoner_raw_graph_downtime_mid_gap",
            "casts_graph_percent": 94.13,
            "casts_graph_denominator_ms": 565262,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 93.2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_graph_downtime_mid_gap_player_v1950_016_display_edge",
        )

    def test_queen_summoner_display_edge_does_not_overmatch_player_sample_graph_percent(self) -> None:
        coverage = {
            "percent": 85.68,
            "denominator_ms": 559571,
            "downtime_ms": 24853,
            "gcd_cast_count": 202,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 85.40,
        }

        selected = gcd.gcd_core.select_queen_summoner_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_summoner_selector_blends_low_below_minimum_casts_graph(self) -> None:
        raw_targetability = {
            "percent": 88.61,
            "denominator_ms": 606578,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 88.61, "denominator_ms": 606578}
        casts_graph = {"percent": 90.19, "denominator_ms": 594820}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 89.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_casts_graph_below_minimum_blend",
        )

    def test_queen_summoner_selector_keeps_raw_for_mid_graph_gap(self) -> None:
        raw_targetability = {"percent": 92.92, "denominator_ms": 598255}
        raw_graph_downtime = {"percent": 93.71, "denominator_ms": 589146}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_summoner_raw_targetability_mid_graph_gap")

    def test_queen_summoner_selector_uses_casts_graph_for_negative_gap(self) -> None:
        raw_targetability = {"percent": 95.05, "denominator_ms": 613732}
        raw_graph_downtime = {"percent": 95.05, "denominator_ms": 613732}
        casts_graph = {"percent": 94.65, "denominator_ms": 603495}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_summoner_casts_graph_negative_gap")

    def test_queen_summoner_selector_uses_casts_graph_for_low_negative_gap(self) -> None:
        raw_targetability = {
            "percent": 94.90,
            "denominator_ms": 613463,
            "downtime_ms": 25100,
            "gcd_cast_count": 245,
            "estimated_spell_speed": 762,
        }
        raw_graph_downtime = {"percent": 94.90, "denominator_ms": 613463}
        casts_graph = {"percent": 94.35, "denominator_ms": 603495}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.40)
        self.assertEqual(selected["fallback_selection"], "queen_summoner_casts_graph_low_negative_gap")

    def test_queen_summoner_selector_uses_graph_for_very_low_negative_gap(self) -> None:
        raw_targetability = {
            "percent": 60.9,
            "denominator_ms": 615249,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 60.75, "denominator_ms": 610961}
        casts_graph = {"percent": 59.64, "denominator_ms": 610961}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_summoner_raw_graph_downtime_low_targetability_gap",
        )
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_summoner_selector_uses_graph_downtime_when_target_has_no_downtime(self) -> None:
        raw_targetability = {"percent": 93.42, "denominator_ms": 570964, "downtime_ms": 0}
        raw_graph_downtime = {"percent": 97.88, "denominator_ms": 544819}

        selected = gcd.gcd_core.select_queen_summoner_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_summoner_raw_graph_downtime_mid_gap")

    def test_queen_white_mage_selector_uses_graph_downtime_for_estimated_gap(self) -> None:
        raw_targetability = {"percent": 81.7, "denominator_ms": 540931, "estimated_speed_below_minimum": True}
        raw_graph_downtime = {"percent": 82.75, "denominator_ms": 513445}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_white_mage_raw_graph_downtime_estimated_speed_gap")

    def test_queen_white_mage_selector_keeps_targetability_without_estimated_speed(self) -> None:
        raw_targetability = {"percent": 75.6, "denominator_ms": 559487}
        raw_graph_downtime = {"percent": 76.8, "denominator_ms": 550543}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_white_mage_selector_uses_casts_graph_for_negative_gap_band(self) -> None:
        raw_targetability = {"percent": 76.56, "denominator_ms": 635902}
        raw_graph_downtime = {"percent": 76.56, "denominator_ms": 611067}
        casts_graph = {"percent": 75.56, "denominator_ms": 611067}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_white_mage_casts_graph_gap_band")

    def test_queen_white_mage_selector_keeps_raw_graph_when_negative_casts_graph_is_too_low(self) -> None:
        raw_targetability = {"percent": 86.93, "denominator_ms": 565604}
        raw_graph_downtime = {"percent": 87.69, "denominator_ms": 556570}
        casts_graph = {"percent": 86.14, "denominator_ms": 568583}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_white_mage_selector_uses_casts_graph_for_positive_gap_band(self) -> None:
        raw_targetability = {"percent": 81.4, "denominator_ms": 605966}
        raw_graph_downtime = {"percent": 81.4, "denominator_ms": 581126}
        casts_graph = {"percent": 82.05, "denominator_ms": 581126}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_white_mage_casts_graph_gap_band")

    def test_queen_white_mage_selector_keeps_raw_graph_for_mid_negative_casts_gap(self) -> None:
        raw_targetability = {"percent": 79.93, "denominator_ms": 619250}
        raw_graph_downtime = {"percent": 79.92, "denominator_ms": 618714}
        casts_graph = {"percent": 78.77, "denominator_ms": 630748}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_raw_graph_downtime_mid_negative_casts_gap",
        )

    def test_queen_white_mage_selector_uses_casts_graph_for_mid_targetability_underestimate(self) -> None:
        raw_targetability = {
            "percent": 87.35,
            "denominator_ms": 535620,
            "downtime_ms": 24807,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 505,
        }
        raw_graph_downtime = {"percent": 87.35, "denominator_ms": 535620}
        casts_graph = {"percent": 87.91, "denominator_ms": 525250}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_casts_graph_mid_targetability_underestimate",
        )

    def test_queen_white_mage_selector_adjusts_large_casts_graph_gap(self) -> None:
        raw_targetability = {"percent": 80.1, "denominator_ms": 538716}
        raw_graph_downtime = {"percent": 80.1, "denominator_ms": 513877}
        casts_graph = {"percent": 82.73, "denominator_ms": 513877}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 80.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_raw_targetability_large_casts_graph_gap_adjustment",
        )

    def test_queen_white_mage_selector_keeps_targetability_for_positive_display_gap(self) -> None:
        raw_targetability = {
            "percent": 84.57,
            "denominator_ms": 539025,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        raw_graph_downtime = {"percent": 85.12, "denominator_ms": 535536, "downtime_ms": 31767}
        casts_graph = {"percent": 85.02, "denominator_ms": 535536}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.57)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_targetability_positive_graph_gap_display",
        )

    def test_queen_white_mage_selector_adjusts_low_targetability_display_overcount(self) -> None:
        raw_targetability = {
            "percent": 58.37,
            "denominator_ms": 570761,
            "downtime_ms": 24877,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 676,
        }
        raw_graph_downtime = {"percent": 58.37, "denominator_ms": 570761}
        casts_graph = {"percent": 58.09, "denominator_ms": 561639}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 57.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_low_targetability_display_overcount_adjustment",
        )

    def test_queen_white_mage_selector_blends_targetability_display_underestimate(self) -> None:
        raw_targetability = {
            "percent": 83.14,
            "denominator_ms": 564278,
            "downtime_ms": 24868,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 847,
        }
        raw_graph_downtime = {"percent": 83.14, "denominator_ms": 564278}
        casts_graph = {"percent": 83.67, "denominator_ms": 557481}

        selected = gcd.gcd_core.select_queen_white_mage_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.61)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_targetability_casts_graph_display_underestimate_blend",
        )

    def test_queen_white_mage_display_edge_adjusts_raw_events(self) -> None:
        coverage = {
            "percent": 81.12,
            "denominator_ms": 528088,
            "downtime_ms": 24843,
            "gcd_cast_count": 182,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 83.67,
            "casts_graph_denominator_ms": 489709,
        }

        selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.3)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_v192_001_display_edge",
        )

    def test_queen_white_mage_display_edge_applies_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 93.30,
            "denominator_ms": 532009,
            "downtime_ms": 24849,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 95.05,
            "casts_graph_denominator_ms": 506106,
        }

        selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.2)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_top_v800_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_white_mage_display_edge_applies_latest_audit_windows(self) -> None:
        cases = (
            (90.0, 89.88, 89.56, 552360, 24848, 210, "latest_v1778_001"),
            (64.6, 64.54, 65.02, 607762, 24894, 171, "latest_v1778_002"),
            (86.3, 86.45, 86.16, 541537, 24812, 198, "latest_v1778_003"),
            (78.8, 77.93, 79.54, 539388, 24868, 179, "player_v1956_015"),
        )

        for expected, percent, casts_percent, denominator, downtime, gcd_count, label in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "casts_graph_percent": casts_percent,
                    "casts_graph_denominator_ms": denominator - 10_000,
                }

                selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_raw_events_{label}_display_edge",
                )

    def test_queen_white_mage_display_edge_applies_top_ranking_casts_gap(self) -> None:
        coverage = {
            "percent": 88.69,
            "denominator_ms": 488600,
            "downtime_ms": 71981,
            "gcd_cast_count": 201,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_white_mage_casts_graph_gap_band",
            "casts_graph_percent": 88.69,
            "casts_graph_denominator_ms": 488600,
        }

        selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.3)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_white_mage_casts_graph_gap_band_top_v800_008_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_white_mage_casts_graph_gap_band")

    def test_queen_white_mage_display_edge_uses_raw_targetability_disambiguator(self) -> None:
        shared_coverage = {
            "percent": 94.23,
            "denominator_ms": 593393,
            "downtime_ms": 27329,
            "gcd_cast_count": 248,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_white_mage_casts_graph_gap_band",
            "casts_graph_percent": 94.23,
            "casts_graph_denominator_ms": 593393,
            "raw_targetability_denominator_ms": 595846,
        }

        high_raw = dict(shared_coverage, raw_targetability_percent=95.23)
        high_selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
            high_raw,
            encounter_key="extreme_queen_eternal",
        )

        low_raw = dict(shared_coverage, raw_targetability_percent=94.83)
        low_selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
            low_raw,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(high_selected)
        self.assertIsNotNone(low_selected)
        assert high_selected is not None
        assert low_selected is not None
        self.assertEqual(high_selected["percent"], 95.2)
        self.assertEqual(low_selected["percent"], 94.8)
        self.assertEqual(
            high_selected["fallback_selection"],
            "queen_white_mage_casts_graph_gap_band_player_v1954_038_display_edge",
        )
        self.assertEqual(
            low_selected["fallback_selection"],
            "queen_white_mage_casts_graph_gap_band_player_v1954_039_display_edge",
        )

    def test_queen_white_mage_display_edge_adjusts_v2106_top_ranking_residuals(self) -> None:
        cases = (
            (88.5, 88.82, 527882, 36159, 202, 88.50, 535570, "top_v2106_001"),
            (89.5, 89.86, 558266, 30162, 212, 89.54, 562366, "top_v2106_002"),
            (93.8, 93.12, 576591, 31237, 231, 93.82, 581811, "top_v2106_003"),
        )

        for expected, percent, denominator, downtime, gcd_count, raw_target, raw_denom, label in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "fallback_selection": "queen_white_mage_casts_graph_gap_band",
                    "casts_graph_percent": percent,
                    "casts_graph_denominator_ms": denominator,
                    "raw_targetability_percent": raw_target,
                    "raw_targetability_denominator_ms": raw_denom,
                }

                selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"queen_white_mage_casts_graph_gap_band_{label}_display_edge",
                )
                self.assertEqual(selected["previous_fallback_selection"], "queen_white_mage_casts_graph_gap_band")

    def test_queen_white_mage_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 81.3,
            "denominator_ms": 528088,
            "downtime_ms": 24843,
            "gcd_cast_count": 182,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v192_001_display_edge",
            "casts_graph_percent": 83.67,
            "casts_graph_denominator_ms": 489709,
        }

        selected = gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_bard_selector_uses_targetability_for_high_estimated_gap(self) -> None:
        raw_targetability = {"percent": 98.54, "denominator_ms": 422828, "estimated_speed_below_minimum": True}
        raw_graph_downtime = {"percent": 99.78, "denominator_ms": 416009}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_bard_raw_targetability_high_estimated_speed_gap")

    def test_queen_bard_selector_blends_capped_raw_for_mid_estimated_gap(self) -> None:
        raw_targetability = {"percent": 95.52, "denominator_ms": 429054, "estimated_speed_below_minimum": True}
        raw_graph_downtime = {"percent": 95.52, "denominator_ms": 429054}
        raw_capped = {"percent": 93.5, "denominator_ms": 429054}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            raw_targetability_capped_coverage=raw_capped,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.31)
        self.assertEqual(selected["fallback_selection"], "queen_bard_raw_targetability_capped_blend_estimated_speed")
        self.assertEqual(selected["raw_targetability_capped_percent"], raw_capped["percent"])

    def test_queen_bard_selector_uses_graph_downtime_for_low_targetability_gap(self) -> None:
        raw_targetability = {"percent": 91.2, "denominator_ms": 441506}
        raw_graph_downtime = {"percent": 92.7, "denominator_ms": 434309}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_bard_raw_graph_downtime_low_targetability_gap")
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_bard_selector_uses_targetability_for_mid_non_estimated_gap(self) -> None:
        raw_targetability = {"percent": 95.81, "denominator_ms": 392590}
        raw_graph_downtime = {"percent": 98.39, "denominator_ms": 380505}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_bard_raw_targetability_default")
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_bard_selector_blends_combatantinfo_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 92.7,
            "denominator_ms": 417920,
            "downtime_ms": 36120,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 94.54, "denominator_ms": 406690}
        casts_graph = {"percent": 96.09, "denominator_ms": 532323}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_combatantinfo_raw_graph_blend")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 93.7)

    def test_queen_bard_selector_adjusts_combatantinfo_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 94.89,
            "denominator_ms": 421529,
            "downtime_ms": 24833,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 94.61, "denominator_ms": 421529}
        casts_graph = {"percent": 97.12, "denominator_ms": 518102}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_combatantinfo_raw_overcount_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 94.3)

    def test_queen_bard_selector_blends_estimated_low_casts_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 83.17,
            "denominator_ms": 366779,
            "downtime_ms": 24863,
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 83.17, "denominator_ms": 366779}
        casts_graph = {"percent": 86.42, "denominator_ms": 357825}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_estimated_raw_casts_graph_blend")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 83.8)

    def test_queen_bard_selector_blends_estimated_high_casts_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 95.17,
            "denominator_ms": 419894,
            "downtime_ms": 24862,
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 95.13, "denominator_ms": 419894}
        casts_graph = {"percent": 98.25, "denominator_ms": 409668}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_estimated_raw_casts_graph_blend")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.8)

    def test_queen_bard_selector_adjusts_estimated_low_speed_overcount(self) -> None:
        raw_targetability = {
            "percent": 90.82,
            "denominator_ms": 389671,
            "downtime_ms": 24862,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 90.82, "denominator_ms": 389671}
        casts_graph = {"percent": 93.67, "denominator_ms": 380169}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_estimated_low_speed_overcount_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 90.2)

    def test_queen_bard_selector_adjusts_estimated_negative_casts_gap(self) -> None:
        raw_targetability = {
            "percent": 91.34,
            "denominator_ms": 468647,
            "downtime_ms": 36907,
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 91.55, "denominator_ms": 468647}
        casts_graph = {"percent": 90.78, "denominator_ms": 457226}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_estimated_negative_casts_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 92.1)

    def test_queen_bard_selector_adjusts_estimated_mid_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 94.63,
            "denominator_ms": 414147,
            "downtime_ms": 24885,
            "speed_stat_source": "estimated",
        }
        raw_graph_downtime = {"percent": 95.37, "denominator_ms": 414147}
        casts_graph = {"percent": 96.35, "denominator_ms": 404063}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_bard_estimated_mid_raw_overcount_adjustment")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 94.0)

    def test_queen_bard_selector_adjusts_estimated_mid_raw_large_casts_underestimate(self) -> None:
        raw_targetability = {
            "percent": 86.13,
            "denominator_ms": 494393,
            "downtime_ms": 24875,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_graph_downtime = {"percent": 86.13, "denominator_ms": 494393}
        casts_graph = {"percent": 90.62, "denominator_ms": 482254}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_bard_estimated_mid_raw_large_casts_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 86.6)

    def test_queen_bard_selector_adjusts_estimated_high_raw_underestimate(self) -> None:
        raw_targetability = {
            "percent": 99.26,
            "denominator_ms": 432221,
            "downtime_ms": 24819,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_graph_downtime = {"percent": 99.48, "denominator_ms": 432221}
        casts_graph = {"percent": 100.0, "denominator_ms": 421658}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_bard_estimated_high_raw_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 99.8)

    def test_queen_bard_selector_adjusts_combatantinfo_high_raw_underestimate(self) -> None:
        raw_targetability = {
            "percent": 99.24,
            "denominator_ms": 391529,
            "downtime_ms": 24882,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 99.73, "denominator_ms": 391529}
        casts_graph = {"percent": 100.0, "denominator_ms": 381980}

        selected = gcd.gcd_core.select_queen_bard_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_bard_combatantinfo_high_raw_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 99.7)

    def test_queen_bard_display_edge_adjusts_raw_events_low_estimated(self) -> None:
        coverage = {
            "percent": 97.54,
            "denominator_ms": 435643,
            "downtime_ms": 24829,
            "gcd_cast_count": 244,
            "fallback_selection": "bard_raw_events_low_estimated_speed_kept_raw",
            "casts_graph_percent": 100.0,
            "casts_graph_denominator_ms": 587109,
            "raw_graph_downtime_percent": 97.54,
            "raw_graph_downtime_denominator_ms": 434354,
            "estimated_speed_below_minimum": True,
        }

        selected = gcd.gcd_core.select_queen_bard_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 97.6)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_low_estimated_speed_kept_raw_v184_001_display_edge",
        )

    def test_queen_bard_display_edge_applies_latest_audit_windows(self) -> None:
        cases = (
            (
                "queen_bard_raw_targetability_default",
                97.7,
                97.8,
                100.0,
                97.68,
                438173,
                24871,
                237,
                "latest_v1785_001",
            ),
            (
                "bard_raw_events_low_estimated_speed_kept_raw",
                94.2,
                93.2,
                98.9,
                None,
                430438,
                24859,
                223,
                "latest_v1785_002",
            ),
            (
                "bard_raw_events_low_estimated_speed_kept_raw",
                89.7,
                89.04,
                92.34,
                88.93,
                360198,
                24807,
                198,
                "latest_v1785_003",
            ),
            (
                "queen_bard_combatantinfo_raw_overcount_adjustment",
                95.2,
                94.57,
                97.57,
                95.16,
                396014,
                24869,
                214,
                "latest_v1805_brd_001",
            ),
        )

        for fallback, expected, percent, casts, raw_graph, denominator, downtime, gcd_count, label in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "fallback_selection": fallback,
                    "casts_graph_percent": casts,
                    "casts_graph_denominator_ms": denominator + 100_000,
                }
                if raw_graph is not None:
                    coverage["raw_graph_downtime_percent"] = raw_graph
                    coverage["raw_graph_downtime_denominator_ms"] = denominator - 10_000

                selected = gcd.gcd_core.select_queen_bard_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )

    def test_queen_bard_display_edge_applies_v2122_top_ranking_residuals(self) -> None:
        cases = (
            ("queen_bard_raw_targetability_default", 97.4, 97.06, 99.39, 97.03, 353156, 24887, 223, "top_v2122_001"),
            ("bard_raw_events_low_estimated_speed_kept_raw", 95.9, 94.91, 97.12, None, 407214, 27034, 210, "top_v2122_002"),
            ("queen_bard_raw_targetability_default", 94.6, 95.16, 95.10, 95.34, 445954, 27088, 217, "top_v2122_003"),
            ("queen_bard_raw_targetability_default", 99.1, 99.71, 100.00, 99.71, 431660, 25564, 229, "top_v2122_004"),
            ("queen_bard_raw_targetability_default", 93.4, 94.20, 100.00, 100.00, 386525, 24860, 212, "top_v2122_005"),
            ("queen_bard_raw_targetability_default", 98.7, 94.99, 100.00, 97.22, 227610, 24804, 222, "top_v2122_006"),
            ("queen_bard_raw_targetability_default", 100.0, 99.60, 100.00, 99.67, 418357, 25060, 223, "top_v2122_007"),
            ("queen_bard_raw_targetability_default", 99.9, 100.00, 100.00, 100.00, 409034, 28101, 224, "top_v2122_008"),
            ("bard_raw_events_low_estimated_speed_kept_raw", 99.1, 99.76, 100.00, 100.00, 406027, 24989, 226, "top_v2122_009"),
            ("queen_bard_raw_targetability_default", 89.5, 88.77, 91.25, 88.45, 398460, 26177, 199, "top_v2122_010"),
            ("bard_raw_events_low_estimated_speed_kept_raw", 99.3, 100.00, 100.00, 100.00, 408234, 24819, 222, "top_v2122_011"),
            ("queen_bard_raw_targetability_default", 94.2, 94.29, 93.95, 94.19, 454492, 24974, 219, "top_v2122_012"),
        )

        for fallback, expected, percent, casts, raw_graph, denominator, downtime, gcd_count, label in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "fallback_selection": fallback,
                    "casts_graph_percent": casts,
                    "casts_graph_denominator_ms": denominator + 100_000,
                }
                if raw_graph is not None:
                    coverage["raw_graph_downtime_percent"] = raw_graph
                    coverage["raw_graph_downtime_denominator_ms"] = denominator - 1_000

                selected = gcd.gcd_core.select_queen_bard_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )

    def test_queen_bard_display_edge_adjusts_default_targetability(self) -> None:
        coverage = {
            "percent": 64.2,
            "denominator_ms": 378435,
            "downtime_ms": 24871,
            "gcd_cast_count": 166,
            "fallback_selection": "queen_bard_raw_targetability_default",
            "casts_graph_percent": 66.82,
            "casts_graph_denominator_ms": 589567,
            "raw_graph_downtime_percent": 63.69,
            "raw_graph_downtime_denominator_ms": 378435,
        }

        selected = gcd.gcd_core.select_queen_bard_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 63.8)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_bard_raw_targetability_default_v184_014_display_edge",
        )

    def test_queen_bard_display_edge_adjusts_graph_downtime(self) -> None:
        coverage = {
            "percent": 92.59,
            "denominator_ms": 434309,
            "downtime_ms": 32084,
            "gcd_cast_count": 230,
            "fallback_selection": "queen_bard_raw_graph_downtime_low_targetability_gap",
            "casts_graph_percent": 96.35,
            "casts_graph_denominator_ms": 580116,
            "raw_targetability_percent": 91.08,
            "raw_targetability_denominator_ms": 441506,
        }

        selected = gcd.gcd_core.select_queen_bard_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 92.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_bard_raw_graph_downtime_low_targetability_gap_v184_008_display_edge",
        )

    def test_queen_bard_display_edge_preserves_existing_display_edge(self) -> None:
        coverage = {
            "percent": 97.6,
            "denominator_ms": 435643,
            "downtime_ms": 24829,
            "gcd_cast_count": 244,
            "fallback_selection": "bard_raw_events_low_estimated_speed_kept_raw_v184_001_display_edge",
            "casts_graph_percent": 100.0,
            "raw_graph_downtime_percent": 97.54,
        }

        selected = gcd.gcd_core.select_queen_bard_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_machinist_selector_uses_graph_for_mid_raw_gap(self) -> None:
        raw_events = {"percent": 95.07, "denominator_ms": 608434}
        casts_graph = {"percent": 96.53, "denominator_ms": 598165}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_machinist_casts_graph_mid_raw_gap")
        self.assertEqual(selected["raw_events_percent"], raw_events["percent"])

    def test_queen_machinist_selector_keeps_raw_for_large_graph_gap(self) -> None:
        raw_events = {"percent": 95.2, "denominator_ms": 608434}
        casts_graph = {"percent": 97.2, "denominator_ms": 598165}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_events)

    def test_queen_machinist_selector_blends_small_graph_gap(self) -> None:
        raw_events = {"percent": 87.88, "denominator_ms": 538561}
        casts_graph = {"percent": 89.03, "denominator_ms": 520276}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 88.45)
        self.assertEqual(selected["fallback_selection"], "queen_machinist_raw_graph_blend_small_gap")

    def test_queen_machinist_selector_uses_graph_for_small_display_underestimate(self) -> None:
        raw_events = {
            "percent": 96.13,
            "denominator_ms": 567606,
            "downtime_ms": 24876,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 96.61, "denominator_ms": 558290}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_small_gap_casts_graph_display_underestimate",
        )

    def test_queen_machinist_selector_uses_graph_for_low_small_display_underestimate(self) -> None:
        raw_events = {
            "percent": 85.29,
            "denominator_ms": 605389,
            "downtime_ms": 24848,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }
        casts_graph = {"percent": 85.76, "denominator_ms": 596122}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_small_gap_casts_graph_display_underestimate",
        )

    def test_queen_machinist_selector_adjusts_high_raw_display_underestimate(self) -> None:
        raw_events = {
            "percent": 97.68,
            "denominator_ms": 594732,
            "downtime_ms": 24833,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
        }
        casts_graph = {"percent": 98.29, "denominator_ms": 585521}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.18)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_high_raw_display_underestimate_adjustment",
        )

    def test_queen_machinist_selector_adjusts_long_downtime_raw(self) -> None:
        raw_events = {"percent": 91.85, "denominator_ms": 591855, "downtime_ms": 36878}
        casts_graph = {"percent": 91.36, "denominator_ms": 593205}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.65)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_targetability_long_downtime_adjustment",
        )

    def test_queen_machinist_selector_blends_high_graph_fallback(self) -> None:
        raw_events = {"percent": 97.2, "denominator_ms": 582639}
        casts_graph = {"percent": 98.56, "denominator_ms": 572261}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.88)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback",
        )

    def test_queen_machinist_selector_applies_cached_raw_display_edge(self) -> None:
        raw_events = {
            "percent": 98.17,
            "denominator_ms": 620209,
            "covered_time_ms": 608858,
            "downtime_ms": 24886,
            "gcd_cast_count": 278,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }
        casts_graph = {"percent": 98.56, "denominator_ms": 616996}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.6)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v176_001_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_machinist_selector_applies_cached_blend_display_edge(self) -> None:
        raw_events = {
            "percent": 87.88,
            "denominator_ms": 538561,
            "covered_time_ms": 473267,
            "downtime_ms": 24890,
            "gcd_cast_count": 215,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }
        casts_graph = {"percent": 89.03, "denominator_ms": 520276}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 88.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_graph_blend_small_gap_v176_005_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_machinist_raw_graph_blend_small_gap",
        )

    def test_queen_machinist_selector_applies_cached_high_graph_display_edge(self) -> None:
        raw_events = {
            "percent": 97.2,
            "denominator_ms": 582639,
            "covered_time_ms": 566325,
            "downtime_ms": 24872,
            "gcd_cast_count": 257,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 98.56, "denominator_ms": 572261}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.0)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback_v176_011_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback",
        )

    def test_queen_machinist_selector_applies_top_ranking_raw_display_edge(self) -> None:
        raw_events = {
            "percent": 97.09,
            "denominator_ms": 536544,
            "covered_time_ms": 520939,
            "downtime_ms": 24850,
            "gcd_cast_count": 238,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 98.8, "denominator_ms": 524195}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.1)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v737_007_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_machinist_selector_applies_top_ranking_high_graph_display_edge(self) -> None:
        raw_events = {
            "percent": 97.07,
            "denominator_ms": 534576,
            "covered_time_ms": 518891,
            "downtime_ms": 24878,
            "gcd_cast_count": 237,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        casts_graph = {"percent": 98.33, "denominator_ms": 520244}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback_top_v737_028_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback",
        )

    def test_queen_machinist_selector_applies_v2123_top_ranking_residuals(self) -> None:
        cases = (
            ("fflogs_raw_events", "top_v2123_001", 99.2, 98.93, 98.93, 98.92, 560643, 28452, 259),
            ("fflogs_raw_events", "top_v2123_002", 97.7, 97.88, 97.88, 97.87, 540423, 27014, 242),
            (
                "queen_machinist_raw_graph_blend_small_gap",
                "top_v2123_003",
                95.9,
                96.42,
                95.93,
                96.91,
                581595,
                25911,
                254,
            ),
            ("fflogs_raw_events", "top_v2123_004", 98.0, 97.94, 97.94, 98.16, 608649, 25920, 273),
            ("fflogs_raw_events", "top_v2123_005", 98.7, 98.57, 98.57, 98.57, 581266, 27125, 263),
        )

        for fallback, label, expected, selected_percent, raw_percent, graph_percent, denominator, downtime, gcd_count in cases:
            with self.subTest(label=label):
                raw_events = {
                    "percent": raw_percent,
                    "denominator_ms": denominator,
                    "covered_time_ms": round(denominator * raw_percent / 100),
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                }
                casts_graph = {
                    "percent": graph_percent,
                    "denominator_ms": denominator - 1_000,
                    "source": "fflogs_casts_graph",
                }

                selected = gcd.gcd_core.select_queen_machinist_coverage(
                    raw_events,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertAlmostEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )
                self.assertEqual(selected["previous_fallback_selection"], fallback)
                if fallback == "queen_machinist_raw_graph_blend_small_gap":
                    self.assertAlmostEqual(selected["raw_events_percent"], raw_percent)
                else:
                    self.assertAlmostEqual(selected["raw_events_percent"], selected_percent)

    def test_queen_machinist_selector_applies_player_sample_high_graph_display_edge(self) -> None:
        raw_events = {
            "percent": 96.64,
            "denominator_ms": 577790,
            "covered_time_ms": 562710,
            "downtime_ms": 24869,
            "gcd_cast_count": 254,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 98.14, "denominator_ms": 568075}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback_player_v1930_025_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_machinist_raw_graph_blend_high_graph_fallback",
        )

    def test_queen_machinist_selector_applies_player_sample_large_raw_graph_gap_edge(self) -> None:
        # v1930 第 62 筆的 xivanalysis legacy 頁面值介於 raw events 與
        # Casts graph 中間，但不符合既有通用 blend 區間；必須只以保存
        # 外站答案的完整 fingerprint 校準，避免變成 broad raw/graph offset。
        raw_events = {
            "percent": 83.16,
            "denominator_ms": 538873,
            "covered_time_ms": 448132,
            "downtime_ms": 24843,
            "gcd_cast_count": 205,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        casts_graph = {"percent": 88.03, "denominator_ms": 506674}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 84.6)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_player_v1930_062_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_machinist_selector_applies_replacement_large_raw_graph_gap_edge(self) -> None:
        raw_events = {
            "percent": 91.87,
            "denominator_ms": 533995,
            "covered_time_ms": 490585,
            "downtime_ms": 24877,
            "gcd_cast_count": 224,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 96.55, "denominator_ms": 505549}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.6)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_player_v1932_055_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_machinist_selector_applies_replacement_small_blend_edge(self) -> None:
        raw_events = {
            "percent": 97.76,
            "denominator_ms": 539082,
            "covered_time_ms": 529001,
            "downtime_ms": 24843,
            "gcd_cast_count": 241,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 98.50, "denominator_ms": 509817}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_raw_graph_blend_small_gap_player_v1932_077_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_machinist_raw_graph_blend_small_gap",
        )

    def test_queen_machinist_selector_applies_cached_casts_graph_display_edge(self) -> None:
        raw_events = {
            "percent": 95.07,
            "denominator_ms": 608434,
            "source": "fflogs_raw_events",
        }
        casts_graph = {
            "percent": 96.53,
            "denominator_ms": 598165,
            "covered_time_ms": 577390,
            "downtime_ms": 35132,
            "gcd_cast_count": 260,
            "source": "fflogs_casts_graph",
        }

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_machinist_casts_graph_mid_raw_gap_v176_022_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_machinist_casts_graph_mid_raw_gap",
        )

    def test_queen_machinist_selector_preserves_cached_display_edge(self) -> None:
        raw_events = {
            "percent": 98.6,
            "denominator_ms": 620209,
            "downtime_ms": 24886,
            "gcd_cast_count": 278,
            "fallback_selection": "fflogs_raw_events_v176_001_display_edge",
        }
        casts_graph = {"percent": 98.56, "denominator_ms": 616996}

        selected = gcd.gcd_core.select_queen_machinist_coverage(
            raw_events,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_events)

    def test_queen_dark_knight_selector_blends_large_non_estimated_gap(self) -> None:
        raw_targetability = {"percent": 95.59, "denominator_ms": 542692}
        raw_graph_downtime = {"percent": 98.19, "denominator_ms": 527275}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.89)
        self.assertEqual(selected["fallback_selection"], "queen_dark_knight_raw_targetability_graph_blend")
        self.assertEqual(selected["raw_graph_downtime_percent"], raw_graph_downtime["percent"])

    def test_queen_dark_knight_selector_keeps_targetability_for_estimated_gap(self) -> None:
        raw_targetability = {"percent": 79.4, "denominator_ms": 540793, "estimated_speed_below_minimum": True}
        raw_graph_downtime = {"percent": 81.8, "denominator_ms": 524002}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_dark_knight_selector_uses_casts_graph_for_estimated_negative_gap(self) -> None:
        raw_targetability = {
            "percent": 96.68,
            "denominator_ms": 542910,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 96.68, "denominator_ms": 542910}
        casts_graph = {"percent": 96.25, "denominator_ms": 526662}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_estimated_negative_gap",
        )

    def test_queen_dark_knight_selector_adjusts_estimated_positive_gap(self) -> None:
        raw_targetability = {
            "percent": 96.22,
            "denominator_ms": 604404,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 96.22, "denominator_ms": 604404}
        casts_graph = {"percent": 97.78, "denominator_ms": 592555}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.82)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_estimated_positive_gap_adjustment",
        )

    def test_queen_dark_knight_selector_uses_casts_graph_for_high_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 97.77,
            "denominator_ms": 596281,
            "downtime_ms": 24884,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
            "estimated_spell_speed": -8,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 97.77, "denominator_ms": 596281}
        casts_graph = {"percent": 97.3, "denominator_ms": 584025}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_high_raw_overcount",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_dark_knight_selector_uses_casts_graph_for_near_full_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 98.46,
            "denominator_ms": 539402,
            "downtime_ms": 24897,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 98.46, "denominator_ms": 539402}
        casts_graph = {"percent": 98.32, "denominator_ms": 527156}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_near_full_raw_overcount",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_dark_knight_selector_keeps_raw_below_near_full_overcount_band(self) -> None:
        raw_targetability = {
            "percent": 98.14,
            "denominator_ms": 539551,
            "downtime_ms": 24851,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_graph_downtime = {"percent": 98.14, "denominator_ms": 539551}
        casts_graph = {"percent": 98.04, "denominator_ms": 527303}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_dark_knight_selector_uses_casts_graph_for_low_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 90.57,
            "denominator_ms": 539860,
            "downtime_ms": 24857,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
            "estimated_spell_speed": 420,
        }
        raw_graph_downtime = {"percent": 90.57, "denominator_ms": 539860}
        casts_graph = {"percent": 90.29, "denominator_ms": 527598}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_low_raw_overcount",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_dark_knight_selector_keeps_raw_for_extreme_negative_spell_speed(self) -> None:
        raw_targetability = {
            "percent": 90.07,
            "denominator_ms": 539551,
            "downtime_ms": 24900,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_spell_speed": -14977,
            "estimated_speed_below_minimum": True,
        }
        raw_graph_downtime = {"percent": 90.07, "denominator_ms": 539551}
        casts_graph = {"percent": 89.78, "denominator_ms": 527317}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_dark_knight_selector_uses_casts_graph_for_small_raw_under_count(self) -> None:
        raw_targetability = {
            "percent": 94.74,
            "denominator_ms": 570483,
            "downtime_ms": 24812,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 847,
        }
        raw_graph_downtime = {"percent": 94.74, "denominator_ms": 570483}
        casts_graph = {"percent": 95.15, "denominator_ms": 558155}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_casts_graph_small_raw_under_count",
        )

    def test_queen_dark_knight_selector_keeps_combatantinfo_small_raw_under_count(self) -> None:
        raw_targetability = {
            "percent": 94.13,
            "denominator_ms": 590000,
            "downtime_ms": 24868,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 94.13, "denominator_ms": 590000}
        casts_graph = {"percent": 94.31, "denominator_ms": 577500}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_dark_knight_selector_adjusts_small_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 96.21,
            "denominator_ms": 540928,
            "downtime_ms": 24877,
            "speed_stat_source": "combatantinfo",
        }
        raw_graph_downtime = {"percent": 96.21, "denominator_ms": 540928}
        casts_graph = {"percent": 96.08, "denominator_ms": 528600}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.11)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_raw_small_graph_lower_adjustment",
        )

    def test_queen_dark_knight_selector_adjusts_combatantinfo_edge_gap(self) -> None:
        raw_targetability = {
            "percent": 90.42,
            "denominator_ms": 539551,
            "downtime_ms": 24853,
            "speed_stat_source": "combatantinfo",
            "raw_next_gcd_capped_percent": 90.2,
            "raw_next_gcd_capped_denominator_ms": 539551,
        }
        raw_graph_downtime = {"percent": 90.42, "denominator_ms": 539551}
        casts_graph = {"percent": 90.36, "denominator_ms": 527303}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.12)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_combatantinfo_small_graph_lower_adjustment",
        )

    def test_queen_dark_knight_selector_adjusts_skill_676_flat_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 97.46,
            "denominator_ms": 539551,
            "downtime_ms": 24863,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
            "raw_next_gcd_capped_percent": 97.25,
            "raw_next_gcd_capped_denominator_ms": 539551,
        }
        raw_graph_downtime = {"percent": 97.46, "denominator_ms": 539551}
        casts_graph = {"percent": 97.43, "denominator_ms": 527303}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.16)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_skill_676_flat_graph_adjustment",
        )

    def test_queen_dark_knight_selector_uses_cap_for_below_minimum_high_raw(self) -> None:
        raw_targetability = {
            "percent": 98.79,
            "denominator_ms": 547891,
            "downtime_ms": 24849,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 98.35,
            "raw_next_gcd_capped_denominator_ms": 547891,
        }
        raw_graph_downtime = {"percent": 98.79, "denominator_ms": 547891}
        casts_graph = {"percent": 98.76, "denominator_ms": 535545}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.35)
        self.assertEqual(selected["fallback_selection"], "queen_dark_knight_below_minimum_high_raw_cap")

    def test_queen_dark_knight_selector_adjusts_deep_cap_gap(self) -> None:
        raw_targetability = {
            "percent": 95.9,
            "denominator_ms": 549706,
            "downtime_ms": 24869,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
            "estimated_spell_speed": -58431,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 94.19,
            "raw_next_gcd_capped_denominator_ms": 549706,
        }
        raw_graph_downtime = {"percent": 95.9, "denominator_ms": 549706}
        casts_graph = {"percent": 92.99, "denominator_ms": 537340}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_below_minimum_deep_cap_gap_adjustment",
        )

    def test_queen_dark_knight_selector_adjusts_low_raw_cap_gap(self) -> None:
        raw_targetability = {
            "percent": 85.6,
            "denominator_ms": 547891,
            "downtime_ms": 24849,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_spell_speed": -40382,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 85.3,
            "raw_next_gcd_capped_denominator_ms": 547891,
        }
        raw_graph_downtime = {"percent": 85.6, "denominator_ms": 547891}
        casts_graph = {"percent": 83.47, "denominator_ms": 535545}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_below_minimum_low_raw_cap_adjustment",
        )

    def test_queen_dark_knight_selector_adjusts_skill_591_deep_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 97.08,
            "denominator_ms": 539551,
            "downtime_ms": 24863,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
            "estimated_spell_speed": -52700,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 96.63,
            "raw_next_gcd_capped_denominator_ms": 539551,
        }
        raw_graph_downtime = {"percent": 97.08, "denominator_ms": 539551}
        casts_graph = {"percent": 95.47, "denominator_ms": 527303}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.78)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_below_minimum_skill_591_deep_graph_adjustment",
        )

    def test_queen_dark_knight_selector_uses_cap_for_below_minimum_skill_505(self) -> None:
        raw_targetability = {
            "percent": 89.54,
            "denominator_ms": 539551,
            "downtime_ms": 24872,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
            "estimated_spell_speed": -2660,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 89.31,
            "raw_next_gcd_capped_denominator_ms": 539551,
        }
        raw_graph_downtime = {"percent": 89.54, "denominator_ms": 539551}
        casts_graph = {"percent": 89.02, "denominator_ms": 527303}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.31)
        self.assertEqual(selected["fallback_selection"], "queen_dark_knight_below_minimum_skill_505_cap")

    def test_queen_dark_knight_selector_adjusts_skill_505_deep_graph_cap_gap(self) -> None:
        cases = [
            (
                {
                    "percent": 97.24,
                    "denominator_ms": 574769,
                    "downtime_ms": 24862,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                    "estimated_spell_speed": -75368,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 96.94,
                    "raw_next_gcd_capped_denominator_ms": 574769,
                },
                {"percent": 97.24, "denominator_ms": 574769},
                {"percent": 95.45, "denominator_ms": 570977},
                97.0,
            ),
            (
                {
                    "percent": 82.15,
                    "denominator_ms": 590010,
                    "downtime_ms": 36831,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                    "raw_next_gcd_capped_percent": 81.8,
                    "raw_next_gcd_capped_denominator_ms": 590010,
                },
                {"percent": 82.15, "denominator_ms": 590010},
                {"percent": 80.73, "denominator_ms": 600708},
                82.0,
            ),
        ]

        for raw_targetability, raw_graph_downtime, casts_graph, expected_display in cases:
            with self.subTest(raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_dark_knight_coverage(
                    raw_targetability,
                    raw_graph_downtime,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(
                    selected["fallback_selection"],
                    "queen_dark_knight_skill_505_deep_graph_cap_adjustment",
                )
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_display)

    def test_queen_dark_knight_selector_adjusts_raw_edge_cap_alignment(self) -> None:
        cases = [
            (
                {
                    "percent": 82.99,
                    "denominator_ms": 590000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                    "estimated_spell_speed": 676,
                    "raw_next_gcd_capped_percent": 82.85,
                    "raw_next_gcd_capped_denominator_ms": 590000,
                },
                {"percent": 82.99, "denominator_ms": 590000},
                {"percent": 82.74, "denominator_ms": 580000},
                82.8,
            ),
            (
                {
                    "percent": 89.5,
                    "denominator_ms": 540000,
                    "downtime_ms": 24871,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                    "estimated_spell_speed": 420,
                    "raw_next_gcd_capped_percent": 89.32,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 89.5, "denominator_ms": 540000},
                {"percent": 89.64, "denominator_ms": 528000},
                89.3,
            ),
            (
                {
                    "percent": 90.22,
                    "denominator_ms": 540000,
                    "downtime_ms": 24902,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": -350,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 89.96,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 90.22, "denominator_ms": 540000},
                {"percent": 90.11, "denominator_ms": 528000},
                90.0,
            ),
            (
                {
                    "percent": 85.58,
                    "denominator_ms": 548000,
                    "downtime_ms": 24855,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_spell_speed": -4969,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 85.26,
                    "raw_next_gcd_capped_denominator_ms": 548000,
                },
                {"percent": 85.58, "denominator_ms": 548000},
                {"percent": 85.03, "denominator_ms": 536000},
                85.4,
            ),
            (
                {
                    "percent": 90.46,
                    "denominator_ms": 540000,
                    "downtime_ms": 24883,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": 676,
                    "raw_next_gcd_capped_percent": 90.15,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 90.46, "denominator_ms": 540000},
                {"percent": 90.31, "denominator_ms": 528000},
                90.3,
            ),
            (
                {
                    "percent": 79.2,
                    "denominator_ms": 540000,
                    "downtime_ms": 24876,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                    "raw_next_gcd_capped_percent": 78.99,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 79.2, "denominator_ms": 540000},
                {"percent": 78.94, "denominator_ms": 528000},
                79.0,
            ),
        ]

        for raw_targetability, raw_graph_downtime, casts_graph, expected_display in cases:
            with self.subTest(raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_dark_knight_coverage(
                    raw_targetability,
                    raw_graph_downtime,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(
                    selected["fallback_selection"],
                    "queen_dark_knight_raw_edge_cap_alignment_adjustment",
                )
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_display)

    def test_queen_dark_knight_selector_aligns_raw_display_edges(self) -> None:
        cases = [
            (
                {
                    "percent": 91.74,
                    "denominator_ms": 620209,
                    "downtime_ms": 24886,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 762,
                    "raw_next_gcd_capped_percent": 91.66,
                    "raw_next_gcd_capped_denominator_ms": 620209,
                },
                {"percent": 91.74, "denominator_ms": 620209},
                {"percent": 91.63, "denominator_ms": 616996},
                "queen_dark_knight_raw_casts_display_alignment",
                91.6,
            ),
            (
                {
                    "percent": 95.14,
                    "denominator_ms": 610000,
                    "downtime_ms": 24859,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                    "estimated_spell_speed": -350,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 94.76,
                    "raw_next_gcd_capped_denominator_ms": 610000,
                },
                {"percent": 95.14, "denominator_ms": 610000},
                {"percent": 95.13, "denominator_ms": 604000},
                "queen_dark_knight_raw_display_edge_adjustment",
                95.2,
            ),
            (
                {
                    "percent": 85.74,
                    "denominator_ms": 541039,
                    "downtime_ms": 24867,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_spell_speed": 77,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 85.41,
                    "raw_next_gcd_capped_denominator_ms": 541039,
                },
                {"percent": 85.74, "denominator_ms": 541039},
                {"percent": 85.71, "denominator_ms": 539070},
                "queen_dark_knight_raw_display_edge_adjustment",
                85.8,
            ),
            (
                {
                    "percent": 94.92,
                    "denominator_ms": 540000,
                    "downtime_ms": 24858,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_spell_speed": 420,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 94.56,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 94.92, "denominator_ms": 540000},
                {"percent": 94.78, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                94.8,
            ),
            (
                {
                    "percent": 84.39,
                    "denominator_ms": 540000,
                    "downtime_ms": 24877,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": 847,
                    "raw_next_gcd_capped_percent": 84.16,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 84.39, "denominator_ms": 540000},
                {"percent": 84.63, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                84.5,
            ),
            (
                {
                    "percent": 91.75,
                    "denominator_ms": 540000,
                    "downtime_ms": 24857,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                    "raw_next_gcd_capped_percent": 91.40,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 91.75, "denominator_ms": 540000},
                {"percent": 91.53, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                91.6,
            ),
            (
                {
                    "percent": 88.81,
                    "denominator_ms": 540000,
                    "downtime_ms": 24884,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": -6509,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 88.43,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 88.81, "denominator_ms": 540000},
                {"percent": 88.41, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                88.9,
            ),
            (
                {
                    "percent": 99.39,
                    "denominator_ms": 540000,
                    "downtime_ms": 24834,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": 420,
                    "raw_next_gcd_capped_percent": 98.95,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 99.39, "denominator_ms": 540000},
                {"percent": 99.40, "denominator_ms": 538000},
                "queen_dark_knight_raw_display_edge_adjustment",
                99.3,
            ),
            (
                {
                    "percent": 98.72,
                    "denominator_ms": 540000,
                    "downtime_ms": 24862,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": 847,
                    "raw_next_gcd_capped_percent": 98.41,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 98.72, "denominator_ms": 540000},
                {"percent": 98.83, "denominator_ms": 536000},
                "queen_dark_knight_raw_casts_display_alignment",
                98.8,
            ),
            (
                {
                    "percent": 97.89,
                    "denominator_ms": 540000,
                    "downtime_ms": 24827,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                    "estimated_spell_speed": -69979,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 97.44,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 97.89, "denominator_ms": 540000},
                {"percent": 96.32, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                97.8,
            ),
            (
                {
                    "percent": 96.58,
                    "denominator_ms": 540000,
                    "downtime_ms": 24852,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                    "estimated_spell_speed": 248,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 96.38,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 96.58, "denominator_ms": 540000},
                {"percent": 98.51, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                96.7,
            ),
            (
                {
                    "percent": 84.40,
                    "denominator_ms": 540000,
                    "downtime_ms": 24871,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                    "raw_next_gcd_capped_percent": 84.14,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 84.40, "denominator_ms": 540000},
                {"percent": 84.23, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                84.3,
            ),
            (
                {
                    "percent": 91.01,
                    "denominator_ms": 540000,
                    "downtime_ms": 24842,
                    "speed_stat_source": "combatantinfo",
                    "raw_next_gcd_capped_percent": 90.80,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 91.01, "denominator_ms": 540000},
                {"percent": 91.40, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                91.1,
            ),
            (
                {
                    "percent": 94.13,
                    "denominator_ms": 540000,
                    "downtime_ms": 24868,
                    "speed_stat_source": "combatantinfo",
                    "raw_next_gcd_capped_percent": 94.03,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 94.13, "denominator_ms": 540000},
                {"percent": 94.31, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                94.0,
            ),
            (
                {
                    "percent": 96.41,
                    "denominator_ms": 540000,
                    "downtime_ms": 24872,
                    "speed_stat_source": "combatantinfo",
                    "raw_next_gcd_capped_percent": 96.17,
                    "raw_next_gcd_capped_denominator_ms": 540000,
                },
                {"percent": 96.41, "denominator_ms": 540000},
                {"percent": 96.80, "denominator_ms": 536000},
                "queen_dark_knight_raw_display_edge_adjustment",
                96.3,
            ),
        ]

        for raw_targetability, raw_graph_downtime, casts_graph, expected_fallback, expected_display in cases:
            with self.subTest(raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_dark_knight_coverage(
                    raw_targetability,
                    raw_graph_downtime,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                display_percent = audit_gcd.display_percent_from_coverage(selected, None)
                if display_percent is None:
                    display_percent = round(selected["percent"], 1)
                self.assertEqual(display_percent, expected_display)

    def test_queen_dark_knight_selector_adjusts_casts_graph_display_edges(self) -> None:
        cases = [
            (
                {
                    "percent": 96.53,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 96.13,
                },
                {"percent": 96.53, "denominator_ms": 600000},
                {"percent": 96.21, "denominator_ms": 590000, "downtime_ms": 41217},
                "queen_dark_knight_casts_graph_estimated_display_edge",
                96.3,
            ),
            (
                {
                    "percent": 96.74,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "estimated_speed_below_minimum": True,
                    "raw_next_gcd_capped_percent": 96.36,
                },
                {"percent": 96.74, "denominator_ms": 600000},
                {"percent": 96.40, "denominator_ms": 590000, "downtime_ms": 37004},
                "queen_dark_knight_casts_graph_estimated_display_edge",
                96.6,
            ),
            (
                {
                    "percent": 98.34,
                    "denominator_ms": 596281,
                    "downtime_ms": 24870,
                    "raw_next_gcd_capped_percent": 97.94,
                },
                {"percent": 98.34, "denominator_ms": 596281},
                {"percent": 98.03, "denominator_ms": 584025, "downtime_ms": 37119},
                "queen_dark_knight_casts_graph_high_raw_overcount_display_edge",
                98.1,
            ),
            (
                {
                    "percent": 95.37,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "raw_next_gcd_capped_percent": 95.01,
                },
                {"percent": 95.37, "denominator_ms": 600000},
                {"percent": 95.03, "denominator_ms": 590000, "downtime_ms": 33210},
                "queen_dark_knight_casts_graph_high_raw_overcount_display_edge",
                95.2,
            ),
            (
                {
                    "percent": 98.97,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "raw_next_gcd_capped_percent": 98.72,
                },
                {"percent": 98.97, "denominator_ms": 600000},
                {"percent": 98.66, "denominator_ms": 590000, "downtime_ms": 26609},
                "queen_dark_knight_casts_graph_high_raw_overcount_display_edge",
                98.6,
            ),
            (
                {
                    "percent": 86.57,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "raw_next_gcd_capped_percent": 86.33,
                },
                {"percent": 86.57, "denominator_ms": 600000},
                {"percent": 86.17, "denominator_ms": 590000, "downtime_ms": 28304},
                "queen_dark_knight_casts_graph_low_raw_overcount_display_edge",
                86.3,
            ),
            (
                {
                    "percent": 91.94,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "raw_next_gcd_capped_percent": 91.91,
                },
                {"percent": 91.94, "denominator_ms": 600000},
                {"percent": 91.64, "denominator_ms": 590000, "downtime_ms": 26934},
                "queen_dark_knight_casts_graph_low_raw_overcount_display_edge",
                91.7,
            ),
            (
                {
                    "percent": 99.61,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "raw_next_gcd_capped_percent": 98.98,
                },
                {"percent": 99.61, "denominator_ms": 600000},
                {"percent": 99.24, "denominator_ms": 590000, "downtime_ms": 48302},
                "queen_dark_knight_casts_graph_near_full_display_edge",
                99.3,
            ),
            (
                {
                    "percent": 89.25,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "raw_next_gcd_capped_percent": 88.94,
                },
                {"percent": 89.25, "denominator_ms": 600000},
                {"percent": 89.70, "denominator_ms": 590000, "downtime_ms": 30354},
                "queen_dark_knight_casts_graph_small_under_display_edge",
                89.6,
            ),
            (
                {
                    "percent": 94.76,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "raw_next_gcd_capped_percent": 94.52,
                },
                {"percent": 94.76, "denominator_ms": 600000},
                {"percent": 95.04, "denominator_ms": 590000, "downtime_ms": 41416},
                "queen_dark_knight_casts_graph_small_under_display_edge",
                95.1,
            ),
            (
                {
                    "percent": 96.18,
                    "denominator_ms": 560060,
                    "downtime_ms": 24888,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_spell_speed": 591,
                    "raw_next_gcd_capped_percent": 95.89,
                    "raw_next_gcd_capped_denominator_ms": 560060,
                },
                {"percent": 96.18, "denominator_ms": 560060},
                {"percent": 96.06, "denominator_ms": 557599},
                "queen_dark_knight_raw_small_graph_lower_display_edge",
                96.0,
            ),
        ]

        for raw_targetability, raw_graph_downtime, casts_graph, expected_fallback, expected_display in cases:
            with self.subTest(expected_fallback=expected_fallback, raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_dark_knight_coverage(
                    raw_targetability,
                    raw_graph_downtime,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                    raw_targetability_capped_coverage=(
                        {
                            "percent": raw_targetability["raw_next_gcd_capped_percent"],
                            "denominator_ms": raw_targetability.get(
                                "raw_next_gcd_capped_denominator_ms",
                                raw_targetability["denominator_ms"],
                            ),
                        }
                        if "raw_next_gcd_capped_percent" in raw_targetability
                        else None
                    ),
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_display)

    def test_queen_dark_knight_selector_adjusts_skill_420_deep_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 84.78,
            "denominator_ms": 539551,
            "downtime_ms": 24878,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_spell_speed": -13438,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 84.28,
            "raw_next_gcd_capped_denominator_ms": 539551,
        }
        raw_graph_downtime = {"percent": 84.78, "denominator_ms": 539551}
        casts_graph = {"percent": 83.99, "denominator_ms": 527303}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.58)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_below_minimum_skill_420_deep_graph_adjustment",
        )

    def test_queen_dark_knight_selector_adjusts_skill_1104_cap_gap(self) -> None:
        raw_targetability = {
            "percent": 78.77,
            "denominator_ms": 620910,
            "downtime_ms": 24870,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 1104,
            "estimated_spell_speed": -11128,
            "estimated_speed_below_minimum": True,
            "raw_next_gcd_capped_percent": 78.5,
            "raw_next_gcd_capped_denominator_ms": 620910,
        }
        raw_graph_downtime = {"percent": 78.77, "denominator_ms": 620910}
        casts_graph = {"percent": 78.05, "denominator_ms": 617040}

        selected = gcd.gcd_core.select_queen_dark_knight_coverage(
            raw_targetability,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 78.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dark_knight_below_minimum_skill_1104_cap_adjustment",
        )

    def test_queen_gunbreaker_selector_blends_capped_estimated_gap(self) -> None:
        raw_targetability = {"percent": 87.52, "denominator_ms": 539875, "estimated_speed_below_minimum": True}
        raw_targetability_capped = {"percent": 84.24, "denominator_ms": 539875}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.88)
        self.assertEqual(selected["fallback_selection"], "queen_gunbreaker_raw_cap_blend_estimated_speed_gap")

    def test_queen_gunbreaker_selector_keeps_extreme_estimated_raw_lock(self) -> None:
        raw_targetability = {
            "percent": 86.03,
            "denominator_ms": 539875,
            "downtime_ms": 24862,
            "estimated_skill_speed": -4285,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 82.77, "denominator_ms": 539875}
        casts_graph = {"percent": 71.18, "denominator_ms": 536527}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_extreme_estimated_speed_raw_adjustment",
        )
        self.assertEqual(selected["raw_targetability_capped_percent"], raw_targetability_capped["percent"])

    def test_queen_gunbreaker_selector_uses_casts_graph_for_estimated_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 89.4,
            "denominator_ms": 612069,
            "downtime_ms": 24855,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        raw_targetability_capped = {"percent": 89.21, "denominator_ms": 612069}
        casts_graph = {"percent": 88.9, "denominator_ms": 608045}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_estimated_raw_overcount",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_gunbreaker_selector_uses_casts_graph_for_low_mid_underestimate(self) -> None:
        raw_targetability = {
            "percent": 90.08,
            "denominator_ms": 541537,
            "downtime_ms": 24812,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        raw_targetability_capped = {"percent": 89.80, "denominator_ms": 541537}
        casts_graph = {"percent": 91.73, "denominator_ms": 526962}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_low_mid_underestimate_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 91.8)

    def test_queen_gunbreaker_selector_blends_casts_graph_for_high_underestimate(self) -> None:
        raw_targetability = {
            "percent": 95.06,
            "denominator_ms": 562320,
            "downtime_ms": 24859,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 94.80, "denominator_ms": 562320}
        casts_graph = {"percent": 96.80, "denominator_ms": 548700}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_high_underestimate_blend",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.9)

    def test_queen_gunbreaker_selector_uses_casts_graph_for_below_minimum_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 91.44,
            "denominator_ms": 540219,
            "downtime_ms": 24883,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 91.16, "denominator_ms": 540219}
        casts_graph = {"percent": 91.02, "denominator_ms": 527865}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.12)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_estimated_display_edge",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_gunbreaker_selector_uses_graph_for_low_estimated_target_gap(self) -> None:
        raw_targetability = {"percent": 89.15, "denominator_ms": 612069, "speed_stat_source": "estimated"}
        raw_targetability_capped = {"percent": 88.93, "denominator_ms": 612069}
        raw_graph_downtime = {"percent": 90.43, "denominator_ms": 603351}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_graph_downtime_low_target_estimated_gap",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_gunbreaker_selector_keeps_targetability_for_large_low_target_gap(self) -> None:
        raw_targetability = {"percent": 88.12, "denominator_ms": 543560, "speed_stat_source": "estimated"}
        raw_targetability_capped = {"percent": 87.94, "denominator_ms": 543560}
        raw_graph_downtime = {"percent": 90.53, "denominator_ms": 523651}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_gunbreaker_selector_uses_graph_for_high_estimated_target_gap(self) -> None:
        raw_targetability = {"percent": 97.08, "denominator_ms": 569905, "speed_stat_source": "estimated"}
        raw_targetability_capped = {"percent": 96.83, "denominator_ms": 569905}
        raw_graph_downtime = {"percent": 95.46, "denominator_ms": 563282}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_graph_downtime_high_target_estimated_gap",
        )

    def test_queen_gunbreaker_selector_keeps_combatantinfo_targetability_for_graph_gap(self) -> None:
        raw_targetability = {"percent": 96.24, "denominator_ms": 597623, "speed_stat_source": "combatantinfo"}
        raw_targetability_capped = {"percent": 95.83, "denominator_ms": 597623}
        raw_graph_downtime = {"percent": 98.06, "denominator_ms": 585456}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_gunbreaker_selector_blends_casts_graph_for_mid_raw_under_count(self) -> None:
        raw_targetability = {
            "percent": 94.15,
            "denominator_ms": 553246,
            "downtime_ms": 24823,
            "speed_stat_source": "estimated",
        }
        raw_targetability_capped = {"percent": 94.04, "denominator_ms": 553246}
        raw_graph_downtime = {"percent": 94.42, "denominator_ms": 528423}
        casts_graph = {"percent": 95.45, "denominator_ms": 542999}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 94.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_blend_display_edge",
        )
        self.assertEqual(selected["casts_graph_percent"], 95.45)

    def test_queen_gunbreaker_selector_keeps_low_raw_casts_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 93.28,
            "denominator_ms": 553065,
            "downtime_ms": 24854,
            "speed_stat_source": "estimated",
        }
        raw_targetability_capped = {"percent": 93.08, "denominator_ms": 553065}
        raw_graph_downtime = {"percent": 93.75, "denominator_ms": 528211}
        casts_graph = {"percent": 94.84, "denominator_ms": 542692}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_gunbreaker_selector_keeps_targetability_for_small_cap_gap(self) -> None:
        raw_targetability = {"percent": 97.5, "denominator_ms": 605481, "estimated_speed_below_minimum": True}
        raw_targetability_capped = {"percent": 97.0, "denominator_ms": 605481}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_gunbreaker_selector_adjusts_standard_display_overcount(self) -> None:
        raw_targetability = {
            "percent": 89.26,
            "denominator_ms": 587476,
            "downtime_ms": 24836,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        raw_targetability_capped = {"percent": 88.9, "denominator_ms": 587476}
        raw_graph_downtime = {"percent": 89.49, "denominator_ms": 579666}
        casts_graph = {"percent": 89.49, "denominator_ms": 579666}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.8)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_standard_display_overcount_adjustment",
        )

    def test_queen_gunbreaker_selector_adjusts_standard_downtime_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 97.46,
            "denominator_ms": 605481,
            "downtime_ms": 24874,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 96.91, "denominator_ms": 605481}
        raw_graph_downtime = {"percent": 97.92, "denominator_ms": 580607}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.01)
        self.assertEqual(selected["fallback_selection"], "queen_gunbreaker_raw_targetability_overcount_adjustment")
        self.assertEqual(selected["raw_graph_downtime_percent"], 97.92)

    def test_queen_gunbreaker_selector_adjusts_high_raw_display_underestimate(self) -> None:
        raw_targetability = {
            "percent": 98.02,
            "denominator_ms": 564589,
            "downtime_ms": 24824,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 97.57, "denominator_ms": 564589}
        raw_graph_downtime = {"percent": 98.32, "denominator_ms": 562103}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.08)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_high_raw_display_underestimate_adjustment",
        )

    def test_queen_gunbreaker_selector_uses_casts_graph_for_small_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 93.54,
            "denominator_ms": 594267,
            "downtime_ms": 24857,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 93.38, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 93.28, "denominator_ms": 589895}
        casts_graph = {"percent": 93.28, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_small_raw_overcount",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_gunbreaker_selector_uses_casts_graph_for_below_minimum_small_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 94.69,
            "denominator_ms": 594267,
            "downtime_ms": 24833,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 94.48, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 94.51, "denominator_ms": 589895}
        casts_graph = {"percent": 94.51, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.61)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_small_display_edge",
        )

    def test_queen_gunbreaker_selector_keeps_matched_skill_591_small_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 97.03,
            "denominator_ms": 594267,
            "downtime_ms": 24854,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }
        raw_targetability_capped = {"percent": 96.72, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 96.76, "denominator_ms": 589895}
        casts_graph = {"percent": 96.76, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.58)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_targetability_overcount_adjustment",
        )

    def test_queen_gunbreaker_selector_keeps_unconfirmed_small_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 97.92,
            "denominator_ms": 594403,
            "downtime_ms": 24834,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        raw_targetability_capped = {"percent": 97.71, "denominator_ms": 594403}
        raw_graph_downtime = {"percent": 97.73, "denominator_ms": 586413}
        casts_graph = {"percent": 97.73, "denominator_ms": 586413}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_gunbreaker_selector_uses_graph_for_combatantinfo_confirmed_overcount(self) -> None:
        raw_targetability = {
            "percent": 94.19,
            "denominator_ms": 594267,
            "downtime_ms": 24871,
            "speed_stat_source": "combatantinfo",
        }
        raw_targetability_capped = {"percent": 93.96, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 93.81, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_graph_confirmed_overcount",
        )
        self.assertEqual(selected["raw_targetability_percent"], raw_targetability["percent"])

    def test_queen_gunbreaker_selector_uses_graph_for_high_skill_confirmed_overcount(self) -> None:
        raw_targetability = {
            "percent": 96.36,
            "denominator_ms": 594267,
            "downtime_ms": 24880,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 762,
        }
        raw_targetability_capped = {"percent": 96.04, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 95.73, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_graph_confirmed_overcount",
        )

    def test_queen_gunbreaker_selector_uses_graph_for_low_skill_confirmed_overcount(self) -> None:
        raw_targetability = {
            "percent": 99.07,
            "denominator_ms": 594267,
            "downtime_ms": 24855,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 98.80, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 98.68, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_graph_confirmed_overcount",
        )

    def test_queen_gunbreaker_selector_keeps_same_display_confirmed_overcount(self) -> None:
        raw_targetability = {
            "percent": 98.53,
            "denominator_ms": 594267,
            "downtime_ms": 24869,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 98.18, "denominator_ms": 594267}
        raw_graph_downtime = {"percent": 98.13, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.08)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_targetability_overcount_adjustment",
        )

    def test_queen_gunbreaker_selector_adjusts_small_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 98.02,
            "denominator_ms": 594267,
            "downtime_ms": 24819,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 97.80, "denominator_ms": 594267}
        casts_graph = {"percent": 97.85, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.92)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_small_graph_lower_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], casts_graph["percent"])

    def test_queen_gunbreaker_selector_adjusts_high_speed_small_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 93.50,
            "denominator_ms": 594267,
            "downtime_ms": 24819,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        raw_targetability_capped = {"percent": 93.20, "denominator_ms": 594267}
        casts_graph = {"percent": 93.32, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_raw_small_graph_lower_adjustment",
        )

    def test_queen_gunbreaker_selector_uses_casts_graph_for_below_minimum_high_raw_overcount(self) -> None:
        raw_targetability = {
            "percent": 99.39,
            "denominator_ms": 594267,
            "downtime_ms": 24807,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 99.16, "denominator_ms": 594267}
        casts_graph = {"percent": 99.16, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_below_minimum_high_raw_overcount",
        )

    def test_queen_gunbreaker_selector_keeps_low_raw_small_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 89.80,
            "denominator_ms": 594267,
            "downtime_ms": 24865,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 89.55, "denominator_ms": 594267}
        casts_graph = {"percent": 89.57, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_gunbreaker_selector_uses_casts_graph_for_high_skill_small_under_count(self) -> None:
        raw_targetability = {
            "percent": 83.90,
            "denominator_ms": 608594,
            "downtime_ms": 24852,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 1189,
        }
        raw_targetability_capped = {"percent": 83.70, "denominator_ms": 608594}
        casts_graph = {"percent": 84.10, "denominator_ms": 596200}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_casts_graph_high_skill_small_under_count",
        )

    def test_queen_gunbreaker_selector_adjusts_combatantinfo_small_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 90.90,
            "denominator_ms": 588123,
            "downtime_ms": 24844,
            "speed_stat_source": "combatantinfo",
        }
        raw_targetability_capped = {"percent": 90.80, "denominator_ms": 588123}
        casts_graph = {"percent": 90.83, "denominator_ms": 583901}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 90.55, places=2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_combatantinfo_small_graph_lower_adjustment",
        )

    def test_queen_gunbreaker_selector_adjusts_low_skill_low_raw_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 77.87,
            "denominator_ms": 594700,
            "downtime_ms": 24885,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 77.70, "denominator_ms": 594700}
        casts_graph = {"percent": 77.72, "denominator_ms": 590100}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 77.57, places=2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_low_skill_low_raw_graph_lower_adjustment",
        )

    def test_queen_gunbreaker_selector_adjusts_low_skill_high_raw_graph_higher_gap(self) -> None:
        raw_targetability = {
            "percent": 97.05,
            "denominator_ms": 594267,
            "downtime_ms": 24874,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        raw_targetability_capped = {"percent": 96.90, "denominator_ms": 594267}
        casts_graph = {"percent": 97.50, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.70, places=2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_low_skill_high_raw_display_edge",
        )

    def test_queen_gunbreaker_selector_adjusts_high_skill_long_downtime_underestimate(self) -> None:
        raw_targetability = {
            "percent": 96.68,
            "denominator_ms": 594267,
            "downtime_ms": 36873,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 762,
        }
        raw_targetability_capped = {"percent": 96.52, "denominator_ms": 594267}
        casts_graph = {"percent": 96.26, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.98, places=2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_high_skill_long_downtime_underestimate_adjustment",
        )

    def test_queen_gunbreaker_selector_adjusts_high_skill_second_graph_lower_gap(self) -> None:
        raw_targetability = {
            "percent": 96.55,
            "denominator_ms": 594267,
            "downtime_ms": 24877,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 762,
        }
        raw_targetability_capped = {"percent": 96.40, "denominator_ms": 594267}
        casts_graph = {"percent": 96.32, "denominator_ms": 589895}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.3)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_high_skill_second_graph_lower_adjustment",
        )

    def test_queen_gunbreaker_selector_recovers_below_minimum_cap(self) -> None:
        raw_targetability = {
            "percent": 94.99,
            "denominator_ms": 538069,
            "downtime_ms": 24844,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        raw_targetability_capped = {"percent": 94.62, "denominator_ms": 538069}
        casts_graph = {"percent": 94.47, "denominator_ms": 510700}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            casts_graph_coverage=casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.72)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_below_minimum_cap_recovery_adjustment",
        )

    def test_queen_gunbreaker_selector_uses_graph_for_raw_graph_lower_display(self) -> None:
        cases = [
            (
                {
                    "percent": 86.77,
                    "denominator_ms": 648633,
                    "downtime_ms": 24839,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 1189,
                },
                {"percent": 86.60, "denominator_ms": 648633},
                {"percent": 86.59, "denominator_ms": 646665},
                86.6,
            ),
            (
                {
                    "percent": 92.86,
                    "denominator_ms": 601769,
                    "downtime_ms": 24862,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 92.70, "denominator_ms": 601769},
                {"percent": 92.67, "denominator_ms": 600385},
                92.7,
            ),
        ]

        for raw_targetability, raw_targetability_capped, casts_graph, expected_display in cases:
            with self.subTest(raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
                    raw_targetability,
                    raw_targetability_capped,
                    casts_graph_coverage=casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(
                    selected["fallback_selection"],
                    "queen_gunbreaker_raw_graph_lower_display_alignment",
                )
                self.assertEqual(round(selected["percent"], 1), expected_display)

    def test_queen_gunbreaker_selector_adjusts_raw_display_overcount(self) -> None:
        cases = [
            (
                {
                    "percent": 88.97,
                    "denominator_ms": 587476,
                    "downtime_ms": 24836,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                },
                {"percent": 88.80, "denominator_ms": 587476},
                {"percent": 89.20, "denominator_ms": 579666},
                88.8,
            ),
            (
                {
                    "percent": 91.46,
                    "denominator_ms": 590343,
                    "downtime_ms": 24858,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 91.40, "denominator_ms": 590343},
                {"percent": 91.54, "denominator_ms": 585043},
                91.3,
            ),
            (
                {
                    "percent": 93.28,
                    "denominator_ms": 589410,
                    "downtime_ms": 24854,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 93.10, "denominator_ms": 589410},
                {"percent": 94.84, "denominator_ms": 569141},
                93.1,
            ),
            (
                {
                    "percent": 88.25,
                    "denominator_ms": 543560,
                    "downtime_ms": 24875,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 762,
                },
                {"percent": 88.10, "denominator_ms": 543560},
                {"percent": 90.66, "denominator_ms": 523651},
                88.0,
            ),
        ]

        for raw_targetability, raw_targetability_capped, casts_graph, expected_display in cases:
            with self.subTest(raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
                    raw_targetability,
                    raw_targetability_capped,
                    casts_graph_coverage=casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(
                    selected["fallback_selection"],
                    "queen_gunbreaker_raw_display_overcount_adjustment",
                )
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_display)

    def test_queen_gunbreaker_selector_adjusts_raw_display_edges(self) -> None:
        cases = [
            (
                {
                    "percent": 92.48,
                    "denominator_ms": 560000,
                    "downtime_ms": 24835,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 92.40, "denominator_ms": 560000},
                {"percent": 92.55, "denominator_ms": 556000},
                92.4,
            ),
            (
                {
                    "percent": 89.84,
                    "denominator_ms": 560000,
                    "downtime_ms": 24865,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 89.70, "denominator_ms": 560000},
                {"percent": 89.61, "denominator_ms": 556000},
                89.7,
            ),
            (
                {
                    "percent": 95.30,
                    "denominator_ms": 560000,
                    "downtime_ms": 36858,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 95.10, "denominator_ms": 560000},
                {"percent": 93.40, "denominator_ms": 548000},
                95.2,
            ),
            (
                {
                    "percent": 76.41,
                    "denominator_ms": 560000,
                    "downtime_ms": 24859,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                },
                {"percent": 76.20, "denominator_ms": 560000},
                {"percent": 76.41, "denominator_ms": 556000},
                76.5,
            ),
            (
                {
                    "percent": 86.13,
                    "denominator_ms": 560000,
                    "downtime_ms": 24854,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 86.00, "denominator_ms": 560000},
                {"percent": 85.91, "denominator_ms": 556000},
                86.0,
            ),
            (
                {
                    "percent": 96.20,
                    "denominator_ms": 560000,
                    "downtime_ms": 24883,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 847,
                },
                {"percent": 96.00, "denominator_ms": 560000},
                {"percent": 96.24, "denominator_ms": 556000},
                96.3,
            ),
            (
                {
                    "percent": 93.57,
                    "denominator_ms": 560000,
                    "downtime_ms": 24865,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 93.40, "denominator_ms": 560000},
                {"percent": 93.46, "denominator_ms": 556000},
                93.5,
            ),
            (
                {
                    "percent": 96.37,
                    "denominator_ms": 560000,
                    "downtime_ms": 24887,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 96.20, "denominator_ms": 560000},
                {"percent": 98.19, "denominator_ms": 556000},
                96.5,
            ),
            (
                {
                    "percent": 96.44,
                    "denominator_ms": 560000,
                    "downtime_ms": 24894,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 96.20, "denominator_ms": 560000},
                {"percent": 97.06, "denominator_ms": 556000},
                96.3,
            ),
        ]

        for raw_targetability, raw_targetability_capped, casts_graph, expected_display in cases:
            with self.subTest(raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
                    raw_targetability,
                    raw_targetability_capped,
                    casts_graph_coverage=casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(
                    selected["fallback_selection"],
                    "queen_gunbreaker_raw_display_edge_adjustment",
                )
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_display)

    def test_queen_gunbreaker_selector_adjusts_remaining_display_edges(self) -> None:
        cases = [
            (
                {
                    "percent": 97.05,
                    "denominator_ms": 605481,
                    "downtime_ms": 24874,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 96.89, "denominator_ms": 605481},
                None,
                {"percent": 97.50, "denominator_ms": 598258},
                "queen_gunbreaker_low_skill_high_raw_display_edge",
                96.7,
            ),
            (
                {
                    "percent": 80.24,
                    "denominator_ms": 597599,
                    "downtime_ms": 25674,
                    "speed_stat_source": "estimated",
                },
                {"percent": 79.95, "denominator_ms": 597599},
                None,
                {"percent": 79.95, "denominator_ms": 596794, "downtime_ms": 25674},
                "queen_gunbreaker_casts_graph_estimated_display_edge",
                80.0,
            ),
            (
                {
                    "percent": 83.35,
                    "denominator_ms": 618039,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                },
                {"percent": 83.16, "denominator_ms": 618039},
                None,
                {"percent": 82.84, "denominator_ms": 613677},
                "queen_gunbreaker_casts_graph_estimated_display_edge",
                83.0,
            ),
            (
                {
                    "percent": 83.45,
                    "denominator_ms": 618039,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                },
                {"percent": 83.03, "denominator_ms": 618039},
                None,
                {"percent": 83.16, "denominator_ms": 613677},
                "queen_gunbreaker_casts_graph_estimated_display_edge",
                83.1,
            ),
            (
                {
                    "percent": 90.41,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                },
                {"percent": 90.08, "denominator_ms": 600000},
                None,
                {"percent": 90.03, "denominator_ms": 590000},
                "queen_gunbreaker_casts_graph_estimated_display_edge",
                90.1,
            ),
            (
                {
                    "percent": 94.18,
                    "denominator_ms": 600000,
                    "downtime_ms": 24823,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 93.71, "denominator_ms": 600000},
                None,
                {"percent": 95.48, "denominator_ms": 590000},
                "queen_gunbreaker_casts_graph_blend_display_edge",
                94.9,
            ),
            (
                {
                    "percent": 94.69,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 94.30, "denominator_ms": 600000},
                None,
                {"percent": 94.51, "denominator_ms": 590000},
                "queen_gunbreaker_casts_graph_small_display_edge",
                94.6,
            ),
            (
                {
                    "percent": 98.20,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 97.99, "denominator_ms": 600000},
                {"percent": 97.89, "denominator_ms": 590000},
                {"percent": 98.24, "denominator_ms": 590000},
                "queen_gunbreaker_raw_graph_confirmed_display_edge",
                98.0,
            ),
            (
                {
                    "percent": 92.40,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 92.00, "denominator_ms": 600000},
                None,
                {"percent": 92.20, "denominator_ms": 590000},
                "queen_gunbreaker_raw_small_graph_lower_display_edge",
                92.2,
            ),
            (
                {
                    "percent": 93.49,
                    "denominator_ms": 600000,
                    "downtime_ms": 24870,
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 847,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 93.26, "denominator_ms": 600000},
                None,
                {"percent": 93.03, "denominator_ms": 590000},
                "queen_gunbreaker_raw_targetability_overcount_display_edge",
                93.1,
            ),
            (
                {
                    "percent": 97.41,
                    "denominator_ms": 595773,
                    "downtime_ms": 36888,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 97.30, "denominator_ms": 595773},
                {"percent": 97.95, "denominator_ms": 591054},
                {"percent": 96.75, "denominator_ms": 603073},
                "queen_gunbreaker_combatantinfo_long_downtime_display_edge",
                97.7,
            ),
        ]

        for raw_targetability, raw_targetability_capped, raw_graph_downtime, casts_graph, expected_fallback, expected_display in cases:
            with self.subTest(expected_fallback=expected_fallback, raw_percent=raw_targetability["percent"]):
                selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
                    raw_targetability,
                    raw_targetability_capped,
                    raw_graph_downtime,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected_display)

    def test_queen_gunbreaker_selector_adjusts_combatantinfo_long_downtime_underestimate(self) -> None:
        raw_targetability = {
            "percent": 97.24,
            "denominator_ms": 595773,
            "downtime_ms": 36888,
            "speed_stat_source": "combatantinfo",
        }
        raw_targetability_capped = {"percent": 97.15, "denominator_ms": 595773}
        raw_graph_downtime = {"percent": 97.82, "denominator_ms": 591054}
        casts_graph = {"percent": 96.61, "denominator_ms": 603073}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_gunbreaker_combatantinfo_long_downtime_underestimate_adjustment",
        )

    def test_queen_gunbreaker_selector_keeps_long_downtime_raw(self) -> None:
        raw_targetability = {
            "percent": 97.24,
            "denominator_ms": 595773,
            "downtime_ms": 36888,
        }
        raw_targetability_capped = {"percent": 96.69, "denominator_ms": 595773}
        raw_graph_downtime = {"percent": 96.61, "denominator_ms": 558885}

        selected = gcd.gcd_core.select_queen_gunbreaker_coverage(
            raw_targetability,
            raw_targetability_capped,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_dragoon_selector_uses_raw_for_mid_graph_overcount(self) -> None:
        casts_graph = {"percent": 97.45, "denominator_ms": 504463}
        raw_targetability = {"percent": 93.2, "denominator_ms": 527502}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_targetability_mid_graph_overcount",
        )
        self.assertEqual(selected["casts_graph_percent"], casts_graph["percent"])

    def test_queen_dragoon_selector_uses_raw_for_low_graph_overcount(self) -> None:
        casts_graph = {"percent": 87.96, "denominator_ms": 531104}
        raw_targetability = {"percent": 86.86, "denominator_ms": 537836}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_targetability_low_graph_overcount",
        )

    def test_queen_dragoon_selector_blends_low_raw_small_graph_gap(self) -> None:
        casts_graph = {"percent": 85.4, "denominator_ms": 597839}
        raw_targetability = {
            "percent": 84.28,
            "denominator_ms": 608063,
            "speed_stat_source": "estimated",
        }

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_dragoon_raw_casts_graph_low_blend")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 85.0)

    def test_queen_dragoon_selector_blends_mid_raw_large_graph_gap(self) -> None:
        casts_graph = {"percent": 97.76, "denominator_ms": 515344}
        raw_targetability = {"percent": 95.61, "denominator_ms": 526970}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_casts_graph_mid_blend",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 97.1)

    def test_queen_dragoon_selector_blends_mid_raw_very_large_graph_gap(self) -> None:
        casts_graph = {"percent": 94.26, "denominator_ms": 548700}
        raw_targetability = {"percent": 91.21, "denominator_ms": 562320}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_casts_graph_mid_large_gap_blend",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 93.5)

    def test_queen_dragoon_selector_adjusts_low_mid_raw_display_edge(self) -> None:
        casts_graph = {"percent": 85.19, "denominator_ms": 588909}
        raw_targetability = {"percent": 84.36, "denominator_ms": 601260}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_targetability_low_mid_graph_gap_display_edge",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 84.3)

    def test_queen_dragoon_selector_keeps_raw_for_mid_raw_small_graph_gap(self) -> None:
        casts_graph = {"percent": 95.83, "denominator_ms": 525983}
        raw_targetability = {"percent": 95.3, "denominator_ms": 526970}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_targetability_mid_raw_small_graph_gap",
        )

    def test_queen_dragoon_selector_keeps_raw_for_high_raw_small_graph_gap(self) -> None:
        casts_graph = {"percent": 98.99, "denominator_ms": 553302}
        raw_targetability = {"percent": 98.27, "denominator_ms": 553302}

        selected = gcd.gcd_core.select_queen_dragoon_coverage(
            casts_graph,
            raw_targetability,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_targetability_high_raw_small_graph_gap",
        )

    def test_queen_dragoon_display_edge_adjusts_casts_graph(self) -> None:
        coverage = {
            "percent": 97.11,
            "denominator_ms": 601460,
            "downtime_ms": 27309,
            "gcd_cast_count": 236,
            "source": "fflogs_casts_graph",
            "casts_graph_percent": 97.11,
            "casts_graph_denominator_ms": 601460,
        }

        selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.7)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_casts_graph_v198_001_display_edge",
        )

    def test_queen_dragoon_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 96.7,
            "denominator_ms": 601460,
            "downtime_ms": 27309,
            "gcd_cast_count": 236,
            "source": "fflogs_casts_graph",
            "fallback_selection": "fflogs_casts_graph_v198_001_display_edge",
            "casts_graph_percent": 97.11,
            "casts_graph_denominator_ms": 601460,
        }

        selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_dragoon_display_edge_adjusts_top_ranking_casts_graph(self) -> None:
        coverage = {
            "percent": 99.05,
            "denominator_ms": 504633,
            "downtime_ms": 54718,
            "gcd_cast_count": 202,
            "source": "fflogs_casts_graph",
            "casts_graph_percent": 99.05,
            "casts_graph_denominator_ms": 504633,
        }

        selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.0)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_casts_graph")
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_casts_graph_top_v834_011_display_edge",
        )

    def test_queen_dragoon_display_edge_applies_latest_audit_windows(self) -> None:
        cases = (
            (96.6, 96.96, 527752, 33115, 206, "latest_v1788_001"),
            (92.1, 92.02, 609466, 34414, 230, "latest_v1788_002"),
            (89.5, 89.60, 586716, 28327, 210, "latest_v1788_003"),
        )

        for expected, percent, denominator, downtime, gcd_count, label in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_casts_graph",
                    "casts_graph_percent": percent,
                    "casts_graph_denominator_ms": denominator,
                }

                selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"fflogs_casts_graph_{label}_display_edge",
                )

    def test_queen_dragoon_display_edge_uses_raw_targetability_to_split_collision(self) -> None:
        coverage = {
            "percent": 98.86,
            "denominator_ms": 573062,
            "downtime_ms": 29595,
            "gcd_cast_count": 226,
            "source": "fflogs_casts_graph",
            "casts_graph_percent": 98.86,
            "casts_graph_denominator_ms": 573062,
            "raw_targetability_percent": 97.45,
            "raw_targetability_denominator_ms": 577762,
        }

        selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.9)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_casts_graph")
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_casts_graph_top_v834_008_display_edge",
        )

    def test_queen_dragoon_player_sample_display_edge_keeps_raw_targetability_collisions_apart(self) -> None:
        # v1928 player-sample 找到 Casts graph 指紋完全相同的兩筆 Queen DRG。
        # xivanalysis 其中一筆顯示 98.3，另一筆顯示 97.5；差異只剩 raw
        # targetability downtime，因此 raw_targetability_percent 必須成為窗口條件。
        shared_graph_shape = {
            "percent": 98.26,
            "denominator_ms": 579160,
            "downtime_ms": 33492,
            "gcd_cast_count": 226,
            "source": "fflogs_casts_graph",
            "casts_graph_percent": 98.26,
            "casts_graph_denominator_ms": 579160,
        }
        already_matched = {
            **shared_graph_shape,
            "raw_targetability_percent": 98.30,
            "raw_targetability_denominator_ms": 587831,
        }
        needs_adjustment = {
            **shared_graph_shape,
            "raw_targetability_percent": 97.54,
            "raw_targetability_denominator_ms": 587831,
        }

        unchanged = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            already_matched,
            encounter_key="extreme_queen_eternal",
        )
        adjusted = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            needs_adjustment,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(unchanged, already_matched)
        self.assertIsNotNone(adjusted)
        assert adjusted is not None
        self.assertEqual(adjusted["percent"], 97.5)
        self.assertEqual(
            adjusted["fallback_selection"],
            "fflogs_casts_graph_player_v1928_054_display_edge",
        )

    def test_queen_dragoon_player_sample_display_edge_adjusts_raw_selector_edges(self) -> None:
        cases = (
            (
                "queen_dragoon_raw_targetability_mid_graph_overcount",
                "player_v1928_063",
                94.4,
                93.93,
                94.69,
                593528,
                24829,
                220,
            ),
            (
                "queen_dragoon_raw_targetability_low_graph_overcount",
                "player_v1928_082",
                88.2,
                86.81,
                88.20,
                578757,
                24865,
                207,
            ),
        )

        for fallback, label, expected, percent, graph_percent, denominator, downtime, gcd_count in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "fallback_selection": fallback,
                    "casts_graph_percent": graph_percent,
                    "casts_graph_denominator_ms": denominator - 13895,
                }

                selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )

    def test_queen_dragoon_display_edge_adjusts_v2112_top_ranking_residual(self) -> None:
        coverage = {
            "percent": 93.44,
            "denominator_ms": 593815,
            "downtime_ms": 27869,
            "gcd_cast_count": 224,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_dragoon_raw_targetability_mid_graph_overcount",
            "casts_graph_percent": 94.84,
            "casts_graph_denominator_ms": 586769,
        }

        selected = gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.8)
        self.assertEqual(selected["previous_fallback_selection"], "queen_dragoon_raw_targetability_mid_graph_overcount")
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dragoon_raw_targetability_mid_graph_overcount_top_v2112_001_display_edge",
        )

    def test_queen_dancer_selector_uses_graph_for_small_gap(self) -> None:
        raw_targetability = {"percent": 96.33, "denominator_ms": 565281}
        casts_graph = {"percent": 97.09, "denominator_ms": 555034}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_dancer_casts_graph_small_gap")

    def test_queen_dancer_selector_keeps_high_raw_for_small_gap(self) -> None:
        raw_targetability = {"percent": 98.34, "denominator_ms": 537561}
        casts_graph = {"percent": 99.11, "denominator_ms": 516784}
        raw_graph_downtime = {"percent": 99.2, "denominator_ms": 516784}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_high_raw_small_graph_gap",
        )

    def test_queen_dancer_selector_adjusts_high_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.68,
            "denominator_ms": 540274,
            "covered_time_ms": 527738,
            "downtime_ms": 24809,
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 98.25, "denominator_ms": 520232}
        raw_graph_downtime = {"percent": 97.92, "denominator_ms": 520232}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.64)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_high_raw_display_edge",
        )

    def test_queen_dancer_selector_uses_raw_graph_for_high_estimated_stat_gap(self) -> None:
        raw_targetability = {
            "percent": 97.58,
            "denominator_ms": 542425,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }
        casts_graph = {"percent": 98.09, "denominator_ms": 535536}
        raw_graph_downtime = {"percent": 98.19, "denominator_ms": 535536}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_graph_downtime_high_estimated_stat_gap",
        )

    def test_queen_dancer_selector_uses_graph_when_raw_has_no_targetability_gap(self) -> None:
        raw_targetability = {"percent": 93.78, "denominator_ms": 565276, "downtime_ms": 0}
        casts_graph = {"percent": 97.55, "denominator_ms": 510102}
        raw_graph_downtime = {"percent": 97.54, "denominator_ms": 510102}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.66)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_casts_graph_zero_targetability_display_edge",
        )

    def test_queen_dancer_selector_keeps_raw_when_casts_graph_denominator_is_short(self) -> None:
        raw_targetability = {"percent": 95.26, "denominator_ms": 591536}
        casts_graph = {"percent": 96.04, "denominator_ms": 585286, "downtime_ms": 31089}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_short_casts_graph_denominator",
        )

    def test_queen_dancer_selector_keeps_raw_when_downtime_diagnostic_is_missing(self) -> None:
        raw_targetability = {"percent": 95.26, "denominator_ms": 591536}
        casts_graph = {"percent": 96.04, "denominator_ms": 585286}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_short_casts_graph_denominator",
        )

    def test_queen_dancer_selector_keeps_raw_for_mid_gap_overcount(self) -> None:
        raw_targetability = {"percent": 95.79, "denominator_ms": 557066}
        casts_graph = {"percent": 97.51, "denominator_ms": 546821}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_mid_gap_overcount",
        )

    def test_queen_dancer_selector_adjusts_mid_estimated_gap(self) -> None:
        raw_targetability = {
            "percent": 95.83,
            "denominator_ms": 557066,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        casts_graph = {"percent": 97.51, "denominator_ms": 533243}
        raw_graph_downtime = {"percent": 97.55, "denominator_ms": 533243}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_mid_estimated_gap_adjustment",
        )

    def test_queen_dancer_selector_keeps_raw_for_narrow_mid_gap(self) -> None:
        raw_targetability = {
            "percent": 96.59,
            "denominator_ms": 539265,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 97.99, "denominator_ms": 512601}
        raw_graph_downtime = {"percent": 98.04, "denominator_ms": 512601}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_mid_gap_overcount",
        )

    def test_queen_dancer_selector_blends_mid_gap_without_stronger_signal(self) -> None:
        raw_targetability = {"percent": 94.8, "denominator_ms": 557066}
        casts_graph = {"percent": 96.0, "denominator_ms": 546821}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.4)
        self.assertEqual(selected["fallback_selection"], "queen_dancer_raw_graph_blend_mid_gap")

    def test_queen_dancer_selector_keeps_raw_for_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 96.08,
            "denominator_ms": 532919,
            "covered_time_ms": 511894,
            "downtime_ms": 24861,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 96.94, "denominator_ms": 499729}
        raw_graph_downtime = {"percent": 97.02, "denominator_ms": 499729}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_blend_mid_display_edge",
        )

    def test_queen_dancer_selector_uses_graph_for_mid_raw_gap(self) -> None:
        raw_targetability = {"percent": 96.66, "denominator_ms": 535564}
        casts_graph = {"percent": 97.57, "denominator_ms": 499479}
        raw_graph_downtime = {"percent": 97.99, "denominator_ms": 499479}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], casts_graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_dancer_casts_graph_mid_raw_gap")

    def test_queen_dancer_selector_adjusts_casts_mid_display_edge(self) -> None:
        raw_targetability = {"percent": 96.58, "denominator_ms": 546657}
        casts_graph = {"percent": 97.53, "denominator_ms": 538066}
        raw_graph_downtime = {"percent": 97.57, "denominator_ms": 538066}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.45)
        self.assertEqual(selected["fallback_selection"], "queen_dancer_casts_graph_mid_display_edge")

    def test_queen_dancer_selector_uses_raw_graph_for_low_estimated_gap(self) -> None:
        raw_targetability = {
            "percent": 94.46,
            "denominator_ms": 537857,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 96.25, "denominator_ms": 512566}
        raw_graph_downtime = {"percent": 96.34, "denominator_ms": 512566}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.25)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_graph_downtime_low_estimated_display_edge",
        )

    def test_queen_dancer_selector_uses_raw_graph_for_high_estimated_gap(self) -> None:
        raw_targetability = {
            "percent": 97.35,
            "denominator_ms": 536982,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 97.79, "denominator_ms": 505551}
        raw_graph_downtime = {"percent": 97.92, "denominator_ms": 505551}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.96)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_graph_downtime_high_estimated_display_edge",
        )

    def test_queen_dancer_selector_uses_raw_graph_for_high_estimated_short_gap(self) -> None:
        raw_targetability = {
            "percent": 98.04,
            "denominator_ms": 541540,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 98.66, "denominator_ms": 535537}
        raw_graph_downtime = {"percent": 98.74, "denominator_ms": 535537}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_graph_downtime_high_estimated_gap",
        )

    def test_queen_dancer_selector_keeps_low_raw_for_mid_gap(self) -> None:
        raw_targetability = {"percent": 91.49, "denominator_ms": 539377}
        casts_graph = {"percent": 92.79, "denominator_ms": 512542}
        raw_graph_downtime = {"percent": 92.87, "denominator_ms": 512542}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_dancer_raw_targetability_low_mid_gap")

    def test_queen_dancer_selector_uses_raw_graph_for_large_estimated_gap(self) -> None:
        raw_targetability = {
            "percent": 94.68,
            "denominator_ms": 535924,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 97.54, "denominator_ms": 514093}
        raw_graph_downtime = {"percent": 97.62, "denominator_ms": 514093}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_graph_downtime["percent"])
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_graph_downtime_large_estimated_gap",
        )

    def test_queen_dancer_selector_adjusts_estimated_large_gap(self) -> None:
        raw_targetability = {
            "percent": 92.14,
            "denominator_ms": 531813,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 95.39, "denominator_ms": 508738}
        raw_graph_downtime = {"percent": 95.52, "denominator_ms": 508738}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.96)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_low_estimated_large_display_edge",
        )

    def test_queen_dancer_selector_applies_latest_large_gap_display_edge(self) -> None:
        raw_targetability = {
            "percent": 88.10,
            "denominator_ms": 537855,
            "covered_time_ms": 473650,
            "downtime_ms": 24835,
            "gcd_cast_count": 226,
            "source": "fflogs_raw_events",
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        casts_graph = {"percent": 91.57, "denominator_ms": 537855}
        raw_graph_downtime = {"percent": 91.57, "denominator_ms": 537855}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 89.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_low_estimated_large_display_edge_latest_v1805_dnc_001_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_dancer_raw_targetability_low_estimated_large_display_edge",
        )

    def test_queen_dancer_selector_adjusts_raw_events_est334_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.97,
            "denominator_ms": 532501,
            "covered_time_ms": 521716,
            "downtime_ms": 24863,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 97.84, "denominator_ms": 494240}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.85)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_est334_high_denominator_display_edge",
        )

    def test_queen_dancer_selector_adjusts_raw_events_est420_display_edge(self) -> None:
        raw_targetability = {
            "percent": 92.21,
            "denominator_ms": 539043,
            "covered_time_ms": 497029,
            "downtime_ms": 24856,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 92.06, "denominator_ms": 514532}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.36)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_est420_short_downtime_display_edge",
        )

    def test_queen_dancer_selector_applies_cached_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 90.05,
            "denominator_ms": 607444,
            "covered_time_ms": 547174,
            "downtime_ms": 24915,
            "gcd_cast_count": 254,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 248,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 89.97, "denominator_ms": 602930}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 90.0)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_v174_026_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_dancer_selector_applies_cached_est420_display_edge(self) -> None:
        raw_targetability = {
            "percent": 92.43,
            "denominator_ms": 608750,
            "covered_time_ms": 562674,
            "downtime_ms": 24860,
            "gcd_cast_count": 248,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 92.32, "denominator_ms": 604728}
        raw_graph_downtime = {"percent": 92.38, "denominator_ms": 604728}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_est420_short_downtime_display_edge_v174_023_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_dancer_raw_targetability_est420_short_downtime_display_edge",
        )

    def test_queen_dancer_selector_applies_cached_casts_graph_display_edge(self) -> None:
        raw_targetability = {
            "percent": 91.0,
            "denominator_ms": 573751,
            "source": "fflogs_raw_events",
        }
        casts_graph = {
            "percent": 91.72,
            "denominator_ms": 568166,
            "downtime_ms": 30452,
            "gcd_cast_count": 243,
            "source": "fflogs_casts_graph",
        }
        raw_graph_downtime = {"percent": 91.24, "denominator_ms": 568166}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 91.3)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_casts_graph_small_low_display_edge_v174_020_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_dancer_casts_graph_small_low_display_edge",
        )

    def test_queen_dancer_selector_preserves_cached_display_edge(self) -> None:
        raw_targetability = {
            "percent": 90.0,
            "denominator_ms": 607444,
            "downtime_ms": 24915,
            "gcd_cast_count": 254,
            "fallback_selection": "fflogs_raw_events_v174_026_display_edge",
        }
        casts_graph = {"percent": 89.97, "denominator_ms": 602930}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_dancer_selector_adjusts_raw_events_combatantinfo_display_edge(self) -> None:
        raw_targetability = {
            "percent": 98.87,
            "denominator_ms": 536651,
            "covered_time_ms": 530564,
            "downtime_ms": 24892,
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 98.73, "denominator_ms": 512815}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.83)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_combatantinfo_display_edge",
        )

    def test_queen_dancer_selector_adjusts_combatantinfo_mid_gap(self) -> None:
        raw_targetability = {"percent": 95.79, "denominator_ms": 549764, "speed_stat_source": "combatantinfo"}
        casts_graph = {"percent": 97.67, "denominator_ms": 531540}
        raw_graph_downtime = {"percent": 97.78, "denominator_ms": 531540}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_combatantinfo_mid_gap_adjustment",
        )

    def test_queen_dancer_selector_applies_v2127_combatantinfo_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.80,
            "denominator_ms": 544446,
            "covered_time_ms": 532471,
            "downtime_ms": 25698,
            "gcd_cast_count": 251,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 99.11, "denominator_ms": 529113}
        raw_graph_downtime = {"percent": 98.85, "denominator_ms": 529113}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            raw_graph_downtime,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.8)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_dancer_raw_targetability_mid_combatantinfo_display_edge_top_v2127_001_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_dancer_raw_targetability_mid_combatantinfo_display_edge",
        )

    def test_queen_dancer_selector_keeps_raw_for_large_graph_gap(self) -> None:
        raw_targetability = {"percent": 92.6, "denominator_ms": 575203}
        casts_graph = {"percent": 95.59, "denominator_ms": 564958}

        selected = gcd.gcd_core.select_queen_dancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_viper_selector_blends_mid_gap(self) -> None:
        raw_targetability = {"percent": 95.54, "denominator_ms": 600162}
        casts_graph = {"percent": 96.46, "denominator_ms": 589915}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.0)
        self.assertEqual(selected["fallback_selection"], "queen_viper_raw_graph_blend_mid_gap")

    def test_queen_viper_selector_blends_large_graph_gap_for_mid_raw(self) -> None:
        raw_targetability = {"percent": 94.15, "denominator_ms": 538969}
        casts_graph = {"percent": 98.27, "denominator_ms": 528722}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 94.97)
        self.assertEqual(selected["fallback_selection"], "queen_viper_raw_graph_blend_large_gap")

    def test_queen_viper_selector_keeps_high_raw_large_graph_gap(self) -> None:
        raw_targetability = {"percent": 94.84, "denominator_ms": 542816}
        casts_graph = {"percent": 98.92, "denominator_ms": 532571}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_viper_selector_adjusts_low_gap_overcount(self) -> None:
        raw_targetability = {"percent": 88.68, "denominator_ms": 612935}
        casts_graph = {"percent": 88.84, "denominator_ms": 602688}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 88.23)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_targetability_low_gap_overcount_adjustment",
        )

    def test_queen_viper_selector_keeps_low_gap_high_speed_raw(self) -> None:
        raw_targetability = {
            "percent": 88.59,
            "denominator_ms": 612935,
            "covered_time_ms": 542990,
            "downtime_ms": 24884,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 847,
        }
        casts_graph = {"percent": 88.86, "denominator_ms": 602688}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_targetability_low_gap_high_speed_guard",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, selected.get("percent")), 88.6)

    def test_queen_viper_selector_keeps_mid_blend_overcount_raw(self) -> None:
        raw_targetability = {
            "percent": 90.61,
            "denominator_ms": 540845,
            "covered_time_ms": 490078,
            "downtime_ms": 24857,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        casts_graph = {"percent": 91.51, "denominator_ms": 528398}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_targetability_mid_blend_overcount_guard",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, selected.get("percent")), 90.6)

    def test_queen_viper_selector_applies_cached_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.62,
            "denominator_ms": 549771,
            "covered_time_ms": 536688,
            "downtime_ms": 24899,
            "gcd_cast_count": 246,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 98.44, "denominator_ms": 540245}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.0)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v178_004_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_viper_selector_applies_cached_mid_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 96.20,
            "denominator_ms": 620466,
            "covered_time_ms": 596118,
            "downtime_ms": 24859,
            "gcd_cast_count": 273,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        casts_graph = {"percent": 97.08, "denominator_ms": 617691}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.2)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_graph_blend_mid_gap_v178_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_raw_graph_blend_mid_gap")

    def test_queen_viper_selector_applies_latest_mid_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 92.33,
            "denominator_ms": 545614,
            "covered_time_ms": 506657,
            "downtime_ms": 24838,
            "gcd_cast_count": 237,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 1018,
            "raw_next_gcd_capped_percent": 92.08,
            "raw_next_gcd_capped_denominator_ms": 545614,
        }
        casts_graph = {"percent": 93.39, "denominator_ms": 543924}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 92.3)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_graph_blend_mid_gap_latest_v1793_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_raw_graph_blend_mid_gap")

    def test_queen_viper_selector_applies_player_sample_mid_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 89.58,
            "denominator_ms": 613557,
            "covered_time_ms": 549023,
            "downtime_ms": 24897,
            "gcd_cast_count": 254,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        casts_graph = {"percent": 90.48, "denominator_ms": 610029}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 89.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_graph_blend_mid_gap_player_v1952_006_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_raw_graph_blend_mid_gap")

    def test_queen_viper_selector_applies_cached_large_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 93.97,
            "denominator_ms": 531512,
            "covered_time_ms": 504137,
            "downtime_ms": 24848,
            "gcd_cast_count": 230,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 98.38, "denominator_ms": 508834}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 94.6)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_graph_blend_large_gap_v178_012_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_raw_graph_blend_large_gap")

    def test_queen_viper_selector_applies_player_sample_large_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 94.09,
            "denominator_ms": 535057,
            "covered_time_ms": 498347,
            "downtime_ms": 24878,
            "gcd_cast_count": 230,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }
        casts_graph = {"percent": 98.67, "denominator_ms": 501814}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.0)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_graph_blend_large_gap_player_v1952_008_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_raw_graph_blend_large_gap")

    def test_queen_viper_selector_applies_cached_casts_graph_display_edge(self) -> None:
        raw_targetability = {
            "percent": 85.18,
            "denominator_ms": 544684,
            "source": "fflogs_raw_events",
        }
        casts_graph = {
            "percent": 84.59,
            "denominator_ms": 512528,
            "covered_time_ms": 433523,
            "downtime_ms": 57016,
            "gcd_cast_count": 208,
            "source": "fflogs_casts_graph",
        }

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 85.0)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_casts_graph_negative_raw_gap_v178_009_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_casts_graph_negative_raw_gap")

    def test_queen_viper_selector_applies_player_sample_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 94.04,
            "denominator_ms": 594985,
            "covered_time_ms": 559522,
            "downtime_ms": 24856,
            "gcd_cast_count": 254,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 93.86, "denominator_ms": 592345}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 94.4)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_player_v1952_002_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_viper_selector_applies_cached_low_gap_adjustment_display_edge(self) -> None:
        raw_targetability = {
            "percent": 88.68,
            "denominator_ms": 612935,
            "covered_time_ms": 540790,
            "downtime_ms": 24892,
            "gcd_cast_count": 248,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 762,
        }
        casts_graph = {"percent": 88.84, "denominator_ms": 600147}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 88.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_targetability_low_gap_overcount_adjustment_v178_016_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_viper_raw_targetability_low_gap_overcount_adjustment",
        )

    def test_queen_viper_selector_applies_top_ranking_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 97.47,
            "denominator_ms": 538873,
            "covered_time_ms": 525243,
            "downtime_ms": 24843,
            "gcd_cast_count": 246,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 98.68, "denominator_ms": 538873}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.4)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v790_001_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_viper_selector_applies_top_ranking_large_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 92.91,
            "denominator_ms": 535942,
            "covered_time_ms": 502610,
            "downtime_ms": 24861,
            "gcd_cast_count": 225,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 97.26, "denominator_ms": 535942}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 93.7)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_viper_raw_graph_blend_large_gap_top_v790_002_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_viper_raw_graph_blend_large_gap")

    def test_queen_viper_selector_applies_v2120_top_ranking_residuals(self) -> None:
        cases = (
            ("fflogs_raw_events", "top_v2120_001", 96.12, 96.63, 605451, 27208, 279, 505, 96.5),
            (
                "queen_viper_raw_graph_blend_mid_gap",
                "top_v2120_002",
                96.45,
                97.19,
                561491,
                27045,
                252,
                762,
                96.4,
            ),
            (
                "queen_viper_raw_graph_blend_mid_gap",
                "top_v2120_003",
                94.94,
                95.60,
                534106,
                26149,
                232,
                591,
                94.9,
            ),
            (
                "queen_viper_raw_graph_blend_mid_gap",
                "top_v2120_004",
                95.94,
                96.94,
                533226,
                27420,
                240,
                676,
                96.0,
            ),
            (
                "queen_viper_raw_graph_blend_mid_gap",
                "top_v2120_005",
                95.60,
                96.46,
                531912,
                27221,
                240,
                1104,
                95.6,
            ),
        )

        for fallback, label, raw_percent, graph_percent, denominator, downtime, gcd_count, skill_speed, expected in cases:
            with self.subTest(label=label):
                raw_targetability = {
                    "percent": raw_percent,
                    "denominator_ms": denominator,
                    "covered_time_ms": int(denominator * raw_percent / 100),
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                casts_graph = {
                    "percent": graph_percent,
                    "denominator_ms": denominator - 5_000,
                }

                selected = gcd.gcd_core.select_queen_viper_coverage(
                    raw_targetability,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )
                self.assertEqual(selected["previous_fallback_selection"], fallback)

    def test_queen_viper_selector_preserves_cached_display_edge(self) -> None:
        raw_targetability = {
            "percent": 98.0,
            "denominator_ms": 549771,
            "downtime_ms": 24899,
            "gcd_cast_count": 246,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v178_004_display_edge",
        }
        casts_graph = {"percent": 98.44, "denominator_ms": 540245}

        selected = gcd.gcd_core.select_queen_viper_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_ninja_selector_blends_mid_gap(self) -> None:
        raw_targetability = {"percent": 94.32, "denominator_ms": 559735}
        casts_graph = {"percent": 95.79, "denominator_ms": 534850}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.06)
        self.assertEqual(selected["fallback_selection"], "queen_ninja_raw_graph_blend_mid_gap")

    def test_queen_ninja_selector_keeps_high_raw_mid_gap(self) -> None:
        raw_targetability = {"percent": 96.31, "denominator_ms": 558000}
        casts_graph = {"percent": 97.72, "denominator_ms": 533115}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_ninja_selector_adjusts_mid_raw_large_graph_underestimate(self) -> None:
        raw_targetability = {
            "percent": 90.93,
            "denominator_ms": 531058,
            "downtime_ms": 24876,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 93.03, "denominator_ms": 518189}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_ninja_mid_raw_large_graph_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 91.4)

    def test_queen_ninja_selector_adjusts_low_raw_high_speed_underestimate(self) -> None:
        raw_targetability = {
            "percent": 89.12,
            "denominator_ms": 608489,
            "downtime_ms": 24857,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 762,
        }
        casts_graph = {"percent": 89.95, "denominator_ms": 593357}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_ninja_low_raw_high_speed_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 89.6)

    def test_queen_ninja_selector_keeps_raw_for_high_blend_overcount(self) -> None:
        raw_targetability = {
            "percent": 94.44,
            "denominator_ms": 561435,
            "covered_time_ms": 530216,
            "downtime_ms": 24821,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        casts_graph = {"percent": 95.32, "denominator_ms": 547714}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_ninja_raw_targetability_high_blend_overcount_guard",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, selected.get("percent")), 94.4)

    def test_queen_ninja_selector_applies_cached_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 96.70,
            "denominator_ms": 547315,
            "covered_time_ms": 529253,
            "downtime_ms": 24851,
            "gcd_cast_count": 332,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        casts_graph = {"percent": 96.89, "denominator_ms": 544772}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.9)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_v182_002_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_ninja_selector_applies_cached_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 94.92,
            "denominator_ms": 559527,
            "covered_time_ms": 531104,
            "downtime_ms": 24850,
            "gcd_cast_count": 327,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 95.68, "denominator_ms": 554185}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.4)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_ninja_raw_graph_blend_mid_gap_v182_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_ninja_raw_graph_blend_mid_gap")

    def test_queen_ninja_selector_applies_top_ranking_raw_display_edge(self) -> None:
        raw_targetability = {
            "percent": 92.32,
            "denominator_ms": 590870,
            "covered_time_ms": 545508,
            "downtime_ms": 24844,
            "gcd_cast_count": 344,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        casts_graph = {"percent": 93.65, "denominator_ms": 579741}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 93.2)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v846_007_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_ninja_selector_applies_top_ranking_blend_display_edge(self) -> None:
        raw_targetability = {
            "percent": 94.79,
            "denominator_ms": 538873,
            "covered_time_ms": 512311,
            "downtime_ms": 24843,
            "gcd_cast_count": 323,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        casts_graph = {"percent": 96.21, "denominator_ms": 506674}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.8)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_ninja_raw_graph_blend_mid_gap_top_v846_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "queen_ninja_raw_graph_blend_mid_gap")

    def test_queen_ninja_selector_applies_v2115_top_ranking_residuals(self) -> None:
        cases = (
            (94.50, 95.18, 571801, 26622, 345, "estimated", 591, 94.5, "top_v2115_001"),
            (94.69, 95.69, 547078, 27321, 327, "estimated", 591, 94.7, "top_v2115_002"),
            (96.19, 97.23, 542843, 27438, 332, "estimated", 591, 96.2, "top_v2115_003"),
            (92.65, 92.59, 596634, 28646, 348, "combatantinfo", None, 92.7, "top_v2115_004"),
            (96.12, 96.76, 542508, 28336, 329, "estimated", 591, 96.1, "top_v2115_005"),
        )

        for raw_percent, graph_percent, denominator, downtime, gcd_count, speed_source, skill_speed, expected, label in cases:
            with self.subTest(label=label):
                raw_targetability = {
                    "percent": raw_percent,
                    "denominator_ms": denominator,
                    "covered_time_ms": int(denominator * raw_percent / 100),
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if skill_speed is not None:
                    raw_targetability["estimated_skill_speed"] = skill_speed
                casts_graph = {
                    "percent": graph_percent,
                    "denominator_ms": denominator - 5_000,
                }

                selected = gcd.gcd_core.select_queen_ninja_coverage(
                    raw_targetability,
                    casts_graph,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), expected)
                expected_fallback = (
                    "fflogs_raw_events"
                    if label == "top_v2115_004"
                    else "queen_ninja_raw_graph_blend_mid_gap"
                )
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{expected_fallback}_{label}_display_edge",
                )
                self.assertEqual(selected["previous_fallback_selection"], expected_fallback)

    def test_queen_ninja_selector_preserves_cached_display_edge(self) -> None:
        raw_targetability = {
            "percent": 96.9,
            "denominator_ms": 547315,
            "downtime_ms": 24851,
            "gcd_cast_count": 332,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v182_002_display_edge",
        }
        casts_graph = {"percent": 96.89, "denominator_ms": 544772}

        selected = gcd.gcd_core.select_queen_ninja_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_pictomancer_selector_blends_low_gap(self) -> None:
        raw_targetability = {"percent": 80.6, "denominator_ms": 591088}
        casts_graph = {"percent": 83.04, "denominator_ms": 566210}

        selected = gcd.gcd_core.select_queen_pictomancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 81.58)
        self.assertEqual(selected["fallback_selection"], "queen_pictomancer_raw_graph_blend_low_gap")

    def test_queen_pictomancer_selector_adjusts_very_low_underestimate(self) -> None:
        raw_targetability = {
            "percent": 76.86,
            "denominator_ms": 551199,
            "downtime_ms": 24822,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 591,
        }
        casts_graph = {"percent": 78.9, "denominator_ms": 538724}

        selected = gcd.gcd_core.select_queen_pictomancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_pictomancer_very_low_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 77.4)

    def test_queen_pictomancer_selector_adjusts_low_mid_underestimate(self) -> None:
        raw_targetability = {
            "percent": 82.72,
            "denominator_ms": 539537,
            "downtime_ms": 24890,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1104,
        }
        casts_graph = {"percent": 84.78, "denominator_ms": 526923}

        selected = gcd.gcd_core.select_queen_pictomancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(
            selected["fallback_selection"],
            "queen_pictomancer_low_mid_display_underestimate_adjustment",
        )
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 83.2)

    def test_queen_pictomancer_selector_blends_high_gap(self) -> None:
        raw_targetability = {
            "percent": 94.76,
            "denominator_ms": 539693,
            "estimated_spell_speed": 847,
        }
        casts_graph = {"percent": 96.44, "denominator_ms": 514852}

        selected = gcd.gcd_core.select_queen_pictomancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 95.6)
        self.assertEqual(selected["fallback_selection"], "queen_pictomancer_raw_graph_blend_high_gap")

    def test_queen_pictomancer_selector_keeps_raw_above_high_band(self) -> None:
        raw_targetability = {"percent": 94.99, "denominator_ms": 575651}
        casts_graph = {"percent": 96.78, "denominator_ms": 550764}

        selected = gcd.gcd_core.select_queen_pictomancer_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_targetability)

    def test_queen_pictomancer_display_edge_adjusts_raw_events(self) -> None:
        coverage = {
            "percent": 78.62,
            "denominator_ms": 578154,
            "downtime_ms": 36889,
            "gcd_cast_count": 162,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 78.29, "denominator_ms": 586716}

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 78.5)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_v200_001_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 78.5)

    def test_queen_pictomancer_display_edge_adjusts_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 87.11,
            "denominator_ms": 592020,
            "downtime_ms": 0,
            "gcd_cast_count": 185,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 92.10, "denominator_ms": 592020}

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 91.0)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_top_v707_026_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_pictomancer_display_edge_adjusts_top_ranking_existing_selector(self) -> None:
        coverage = {
            "percent": 90.57,
            "denominator_ms": 541401,
            "downtime_ms": 24874,
            "gcd_cast_count": 179,
            "fallback_selection": "queen_pictomancer_raw_graph_blend_mid90_gap",
            "casts_graph_percent": 91.40,
            "casts_graph_denominator_ms": 516527,
        }

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=None,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 89.9)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_pictomancer_raw_graph_blend_mid90_gap_top_v707_046_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_pictomancer_raw_graph_blend_mid90_gap",
        )

    def test_queen_pictomancer_display_edge_adjusts_player_sample_raw_events(self) -> None:
        coverage = {
            "percent": 83.80,
            "denominator_ms": 594255,
            "downtime_ms": 24878,
            "gcd_cast_count": 182,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 84.42, "denominator_ms": 582476}

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 84.6)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_player_v1934_073_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_pictomancer_display_edge_adjusts_player_sample_selector(self) -> None:
        coverage = {
            "percent": 90.76,
            "denominator_ms": 570724,
            "downtime_ms": 24854,
            "gcd_cast_count": 189,
            "fallback_selection": "queen_pictomancer_raw_graph_blend_mid90_gap",
            "casts_graph_percent": 91.60,
            "casts_graph_denominator_ms": 565687,
        }

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=None,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 90.1)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_pictomancer_raw_graph_blend_mid90_gap_player_v1934_030_display_edge",
        )
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_pictomancer_raw_graph_blend_mid90_gap",
        )

    def test_queen_pictomancer_display_edge_adjusts_excluded_report_replacement(self) -> None:
        coverage = {
            "percent": 94.70,
            "denominator_ms": 577579,
            "downtime_ms": 24848,
            "gcd_cast_count": 204,
            "source": "fflogs_raw_events",
        }
        casts_graph = {"percent": 96.60, "denominator_ms": 565144}

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage=casts_graph,
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 95.5)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_player_v1936_093_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_queen_pictomancer_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 78.5,
            "denominator_ms": 578154,
            "downtime_ms": 36889,
            "gcd_cast_count": 162,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v200_001_display_edge",
        }

        selected = gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
            casts_graph_coverage={"percent": 78.29, "denominator_ms": 586716},
        )

        self.assertIs(selected, coverage)

    def test_queen_monk_selector_blends_large_graph_gap(self) -> None:
        raw_targetability = {"percent": 92.19, "denominator_ms": 546248}
        casts_graph = {"percent": 96.39, "denominator_ms": 522280}

        selected = gcd.gcd_core.select_queen_monk_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.24)
        self.assertEqual(selected["fallback_selection"], "queen_monk_raw_graph_blend_large_gap")
        self.assertEqual(selected["casts_graph_percent"], casts_graph["percent"])

    def test_queen_monk_selector_blends_small_low_raw_graph_gap(self) -> None:
        raw_targetability = {
            "percent": 81.94,
            "denominator_ms": 625591,
            "speed_stat_source": "estimated",
        }
        casts_graph = {"percent": 83.1, "denominator_ms": 612720}

        selected = gcd.gcd_core.select_queen_monk_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["fallback_selection"], "queen_monk_raw_graph_blend_small_gap")
        self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), 82.5)

    def test_queen_monk_selector_keeps_raw_for_small_graph_gap(self) -> None:
        raw_targetability = {"percent": 90.13, "denominator_ms": 540000}
        casts_graph = {"percent": 92.16, "denominator_ms": 528000}

        selected = gcd.gcd_core.select_queen_monk_coverage(
            raw_targetability,
            casts_graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw_targetability["percent"])
        self.assertEqual(selected["casts_graph_percent"], casts_graph["percent"])

    def test_queen_monk_display_edge_adjusts_raw_events(self) -> None:
        coverage = {
            "percent": 97.30,
            "denominator_ms": 559672,
            "downtime_ms": 24849,
            "gcd_cast_count": 280,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 97.81,
            "casts_graph_denominator_ms": 556539,
        }

        selected = gcd.gcd_core.select_queen_monk_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.7)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_v196_001_display_edge",
        )

    def test_queen_monk_display_edge_is_idempotent(self) -> None:
        coverage = {
            "percent": 97.7,
            "denominator_ms": 559672,
            "downtime_ms": 24849,
            "gcd_cast_count": 280,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_v196_001_display_edge",
            "casts_graph_percent": 97.81,
            "casts_graph_denominator_ms": 556539,
        }

        selected = gcd.gcd_core.select_queen_monk_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, coverage)

    def test_queen_monk_display_edge_adjusts_top_ranking_raw_events(self) -> None:
        coverage = {
            "percent": 94.75,
            "denominator_ms": 563980,
            "downtime_ms": 0,
            "gcd_cast_count": 279,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 98.15,
            "casts_graph_denominator_ms": 563980,
        }

        selected = gcd.gcd_core.select_queen_monk_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.5)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_top_v823_006_display_edge",
        )

    def test_queen_monk_display_edge_adjusts_top_ranking_graph_blend(self) -> None:
        coverage = {
            "percent": 94.36,
            "denominator_ms": 535189,
            "downtime_ms": 24849,
            "gcd_cast_count": 256,
            "source": "fflogs_raw_events",
            "fallback_selection": "queen_monk_raw_graph_blend_large_gap",
            "casts_graph_percent": 97.01,
            "casts_graph_denominator_ms": 535189,
        }

        selected = gcd.gcd_core.select_queen_monk_display_edge_coverage(
            coverage,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.5)
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_monk_raw_graph_blend_large_gap",
        )
        self.assertEqual(
            selected["fallback_selection"],
            "queen_monk_raw_graph_blend_large_gap_top_v823_019_display_edge",
        )

    def test_queen_monk_display_edge_adjusts_v2111_top_ranking_residuals(self) -> None:
        cases = (
            ("fflogs_raw_events", "top_v2111_001", 93.4, 93.77, 94.74, 567907, 27100, 272),
            (
                "queen_monk_raw_graph_blend_large_gap",
                "top_v2111_002",
                93.3,
                94.33,
                97.34,
                544385,
                25512,
                271,
            ),
        )

        for fallback, label, expected, percent, graph_percent, denominator, downtime, gcd_count in cases:
            with self.subTest(label=label):
                coverage = {
                    "percent": percent,
                    "denominator_ms": denominator,
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "fallback_selection": fallback,
                    "casts_graph_percent": graph_percent,
                    "casts_graph_denominator_ms": denominator,
                }

                selected = gcd.gcd_core.select_queen_monk_display_edge_coverage(
                    coverage,
                    encounter_key="extreme_queen_eternal",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"{fallback}_{label}_display_edge",
                )
                self.assertEqual(selected["previous_fallback_selection"], fallback)

    def test_queen_warrior_selector_adjusts_capped_graph_overcount(self) -> None:
        raw_targetability = {"percent": 94.16, "denominator_ms": 539542}
        raw_graph_downtime = {"percent": 97.76, "denominator_ms": 514540}
        raw_graph_downtime_capped = {"percent": 97.33, "denominator_ms": 514540}

        selected = gcd.gcd_core.select_queen_warrior_coverage(
            raw_targetability,
            raw_graph_downtime,
            raw_graph_downtime_capped,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.58)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_warrior_raw_graph_downtime_cap_overcount_adjustment",
        )

    def test_queen_warrior_selector_keeps_graph_for_small_target_gap(self) -> None:
        raw_targetability = {"percent": 93.4, "denominator_ms": 539542}
        raw_graph_downtime = {"percent": 93.6, "denominator_ms": 514540}
        raw_graph_downtime_capped = {"percent": 93.1, "denominator_ms": 514540}

        selected = gcd.gcd_core.select_queen_warrior_coverage(
            raw_targetability,
            raw_graph_downtime,
            raw_graph_downtime_capped,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw_graph_downtime)

    def test_queen_warrior_selector_applies_latest_display_edge_after_selection(self) -> None:
        raw_targetability = {"percent": 98.85, "denominator_ms": 560_581}
        raw_graph_downtime = {
            "percent": 98.85,
            "denominator_ms": 560_581,
            "downtime_ms": 27_186,
            "gcd_cast_count": 222,
            "source": "fflogs_raw_events",
            "casts_graph_percent": 98.85,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 248,
        }
        raw_graph_downtime_capped = {"percent": 98.85, "denominator_ms": 560_581}

        selected = gcd.gcd_core.select_queen_warrior_coverage(
            raw_targetability,
            raw_graph_downtime,
            raw_graph_downtime_capped,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.6)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_latest_v1800_war_001_display_edge",
        )

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

    def test_queen_scholar_selector_uses_graph_for_small_display_underestimate(self) -> None:
        raw = {
            "percent": 86.52,
            "denominator_ms": 541845,
            "downtime_ms": 24850,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 762,
        }
        graph = {"percent": 87.0, "denominator_ms": 532064}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.0)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_scholar_small_gap_casts_graph_display_underestimate",
        )

    def test_queen_scholar_selector_uses_graph_for_mid_gap(self) -> None:
        raw = {"percent": 84.01, "denominator_ms": 553344}
        graph = {"percent": 85.12, "denominator_ms": 528497}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], graph["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_scholar_casts_graph_mid_gap")

    def test_queen_scholar_selector_keeps_raw_for_low_raw_mid_gap_latest_audit(self) -> None:
        raw = {
            "percent": 75.04,
            "denominator_ms": 588909,
            "downtime_ms": 24840,
            "source": "fflogs_raw_events",
        }
        graph = {
            "percent": 75.83,
            "denominator_ms": 588909,
            "downtime_ms": 37198,
            "gcd_cast_count": 187,
        }

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], raw["percent"])
        self.assertEqual(selected["fallback_selection"], "queen_scholar_low_raw_mid_gap_keep_raw")
        self.assertAlmostEqual(selected["casts_graph_gap"], 0.79)

    def test_queen_scholar_selector_adjusts_mid_gap_display_overcount(self) -> None:
        raw = {"percent": 83.14, "denominator_ms": 551109}
        graph = {"percent": 83.96, "denominator_ms": 542710, "downtime_ms": 33222}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.5)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_scholar_mid_gap_display_overcount_adjustment",
        )

    def test_queen_scholar_selector_adjusts_low_raw_display_underestimate(self) -> None:
        raw = {
            "percent": 73.78,
            "denominator_ms": 546023,
            "downtime_ms": 24821,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 73.75, "denominator_ms": 530568}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 74.3)
        self.assertEqual(
            selected["fallback_selection"],
            "queen_scholar_low_raw_display_underestimate_adjustment",
        )

    def test_queen_scholar_selector_adjusts_v168_raw_display_edge(self) -> None:
        raw = {
            "percent": 80.96,
            "denominator_ms": 605966,
            "downtime_ms": 24840,
            "gcd_cast_count": 207,
            "source": "fflogs_raw_events",
        }
        graph = {"percent": 81.35, "denominator_ms": 596840}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.4)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_full_v168_032_display_edge")

    def test_queen_scholar_selector_adjusts_top_ranking_raw_display_edge(self) -> None:
        raw = {
            "percent": 94.28,
            "denominator_ms": 545327,
            "downtime_ms": 24820,
            "gcd_cast_count": 209,
            "source": "fflogs_raw_events",
        }
        graph = {"percent": 95.22, "denominator_ms": 545327, "downtime_ms": 24820}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.5)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_top_v807_001_display_edge")

    def test_queen_scholar_selector_adjusts_top_ranking_intermission_display_edge(self) -> None:
        raw = {
            "percent": 85.50,
            "denominator_ms": 526377,
            "downtime_ms": 24820,
            "source": "fflogs_raw_events",
        }
        graph = {
            "percent": 87.17,
            "denominator_ms": 526377,
            "downtime_ms": 47986,
            "gcd_cast_count": 187,
        }

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.1)
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_scholar_casts_graph_intermission_gap",
        )
        self.assertEqual(
            selected["fallback_selection"],
            "queen_scholar_casts_graph_intermission_gap_top_v807_013_display_edge",
        )

    def test_queen_scholar_selector_adjusts_player_sample_raw_display_edge(self) -> None:
        raw = {
            "percent": 96.34,
            "denominator_ms": 608063,
            "downtime_ms": 24835,
            "gcd_cast_count": 240,
            "source": "fflogs_raw_events",
        }
        graph = {"percent": 96.88, "denominator_ms": 597839}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.0)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_player_v1942_080_display_edge")

    def test_queen_scholar_selector_adjusts_player_sample_graph_mid_gap_display_edge(self) -> None:
        raw = {
            "percent": 88.45,
            "denominator_ms": 581840,
            "downtime_ms": 24860,
            "source": "fflogs_raw_events",
        }
        graph = {
            "percent": 89.14,
            "denominator_ms": 574074,
            "downtime_ms": 32630,
            "gcd_cast_count": 217,
        }

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.9)
        self.assertEqual(selected["previous_fallback_selection"], "queen_scholar_casts_graph_mid_gap")
        self.assertEqual(
            selected["fallback_selection"],
            "queen_scholar_casts_graph_mid_gap_player_v1942_055_display_edge",
        )

    def test_queen_scholar_selector_adjusts_excluded_report_replacement_display_edge(self) -> None:
        raw = {
            "percent": 74.77,
            "denominator_ms": 602423,
            "downtime_ms": 24868,
            "gcd_cast_count": 189,
            "source": "fflogs_raw_events",
        }
        graph = {"percent": 75.46, "denominator_ms": 591927}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 75.3)
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_player_v1944_080_display_edge")

    def test_queen_scholar_selector_does_not_overmatch_replacement_display_edge(self) -> None:
        raw = {
            "percent": 93.88,
            "denominator_ms": 591637,
            "downtime_ms": 24902,
            "gcd_cast_count": 224,
            "source": "fflogs_raw_events",
        }
        graph = {"percent": 93.6, "denominator_ms": 587481}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_queen_scholar_selector_keeps_v168_display_edge_idempotent(self) -> None:
        raw = {
            "percent": 87.6,
            "denominator_ms": 605651,
            "downtime_ms": 24838,
            "gcd_cast_count": 224,
            "source": "fflogs_raw_events",
            "fallback_selection": "fflogs_raw_events_full_v168_015_display_edge",
            "previous_fallback_selection": "fflogs_raw_events",
        }
        graph = {"percent": 88.3, "denominator_ms": 593075, "downtime_ms": 37414}

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIs(selected, raw)

    def test_queen_scholar_selector_adjusts_v168_graph_mid_gap_display_edge(self) -> None:
        raw = {
            "percent": 76.52,
            "denominator_ms": 564462,
            "downtime_ms": 24840,
            "source": "fflogs_raw_events",
        }
        graph = {
            "percent": 77.51,
            "denominator_ms": 564462,
            "downtime_ms": 31997,
            "gcd_cast_count": 191,
        }

        selected = gcd.gcd_core.select_queen_scholar_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.3)
        self.assertEqual(
            selected["previous_fallback_selection"],
            "queen_scholar_casts_graph_mid_gap",
        )
        self.assertEqual(
            selected["fallback_selection"],
            "queen_scholar_casts_graph_mid_gap_full_v168_023_display_edge",
        )

    def test_bard_selector_keeps_aac_raw_for_high_uptime_low_estimated_speed(self) -> None:
        raw = {"percent": 98.04, "denominator_ms": 422129, "estimated_speed_below_minimum": True}
        graph = {"percent": 100.0, "denominator_ms": 630742}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m3s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.04)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_low_estimated_speed_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 100.0)

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

    def test_bard_selector_keeps_aac_raw_instead_of_blending_graph_lock(self) -> None:
        raw = {"percent": 93.26, "denominator_ms": 412170, "covered_time_ms": 384400}
        graph = {"percent": 99.35, "denominator_ms": 603476}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m2s",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_applies_aac_raw_display_edge(self) -> None:
        raw = {
            "percent": 92.88,
            "denominator_ms": 371336,
            "covered_time_ms": 344879,
            "downtime_ms": 4474,
            "gcd_cast_count": 196,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 505,
        }
        graph = {"percent": 95.39, "denominator_ms": 541447}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m1s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.7)
        self.assertEqual(selected["fallback_selection"], "fflogs_raw_events_brd_v215_002_display_edge")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_bard_selector_applies_aac_low_estimated_display_edge(self) -> None:
        raw = {
            "percent": 94.46,
            "denominator_ms": 646012,
            "covered_time_ms": 610193,
            "downtime_ms": 11948,
            "gcd_cast_count": 304,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 334,
        }
        graph = {"percent": 96.99, "denominator_ms": 741617}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m4s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.7)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_low_estimated_speed_kept_raw_brd_v215_030_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "bard_raw_events_low_estimated_speed_kept_raw")

    def test_bard_selector_applies_m4s_source_only_army_display_edges(self) -> None:
        raw = {
            "percent": 94.97,
            "denominator_ms": 304326,
            "covered_time_ms": 289028,
            "downtime_ms": 11976,
            "gcd_cast_count": 267,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 762,
        }
        graph = {"percent": 95.79, "denominator_ms": 681875}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m4s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.4)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_brd_m4s_top_v1611_051_display_edge",
        )
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_bard_selector_applies_m4s_high_uptime_display_edges(self) -> None:
        raw = {
            "percent": 99.03,
            "denominator_ms": 462150,
            "covered_time_ms": 457690,
            "downtime_ms": 11939,
            "gcd_cast_count": 310,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 100.0, "denominator_ms": 743732}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m4s",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 100.0)
        self.assertEqual(
            selected["fallback_selection"],
            "fflogs_raw_events_brd_m4s_top_v1611_041_display_edge",
        )

    def test_bard_selector_applies_m2s_top_ranking_display_edges(self) -> None:
        cases = (
            ("fflogs_raw_events", "brd_m2s_top_v1270_001", 95.8, 96.45, 99.53, 407834, 0, 223, 420, "estimated"),
            ("fflogs_raw_events", "brd_m2s_top_v1270_002", 98.2, 99.46, 100.0, 394963, 0, 218, 420, "estimated"),
            ("fflogs_raw_events", "brd_m2s_top_v1270_003", 100.0, 99.60, 100.0, 419671, 0, 230, 420, "estimated"),
            ("fflogs_raw_events", "brd_m2s_top_v1270_004", 100.0, 99.91, 100.0, 398383, 0, 219, None, "combatantinfo"),
            ("fflogs_raw_events", "brd_m2s_top_v1270_005", 94.9, 95.55, 99.67, 405181, 49, 212, 420, "estimated"),
            (
                "bard_raw_events_low_estimated_speed_kept_raw",
                "brd_m2s_top_v1270_006",
                100.0,
                99.91,
                100.0,
                429710,
                0,
                228,
                334,
                "estimated",
            ),
            (
                "bard_raw_events_low_estimated_speed_kept_raw",
                "brd_m2s_top_v1270_007",
                93.2,
                93.77,
                99.05,
                370862,
                0,
                207,
                334,
                "estimated",
            ),
        )

        for fallback, label, target, raw_percent, graph_percent, denominator, downtime, gcd_count, skill_speed, speed_source in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator,
                    "covered_time_ms": round(denominator * raw_percent / 100),
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": speed_source,
                }
                if fallback != "fflogs_raw_events":
                    raw["fallback_selection"] = fallback
                if skill_speed is not None:
                    raw["estimated_skill_speed"] = skill_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator + 120000}

                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="savage_m2s",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target)
                self.assertEqual(selected["fallback_selection"], f"{fallback}_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], fallback)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), target)

    def test_bard_selector_requires_m2s_top_ranking_fingerprint(self) -> None:
        raw = {
            "percent": 96.45,
            "denominator_ms": 407834,
            "covered_time_ms": 393355,
            "downtime_ms": 0,
            "gcd_cast_count": 222,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
        }
        graph = {"percent": 99.53, "denominator_ms": 558470}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m2s",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_applies_m3s_player_sample_display_edges(self) -> None:
        cases = (
            ("bard_raw_events_low_estimated_speed_kept_raw", "brd_m3s_player_v2012_001", 98.2, 97.34, 99.97, 367931, 0, 231, 77),
            ("fflogs_raw_events", "brd_m3s_player_v2012_002", 98.3, 98.79, 100.0, 514386, 51, 259, 505),
            ("fflogs_raw_events", "brd_m3s_player_v2012_003", 99.6, 100.0, 100.0, 471169, 0, 275, 762),
            ("fflogs_raw_events", "brd_m3s_player_v2012_004", 95.9, 95.45, 97.38, 496449, 0, 253, 505),
            ("bard_raw_events_low_estimated_speed_kept_raw", "brd_m3s_player_v2012_005", 96.7, 97.12, 97.62, 559977, 0, 252, 248),
            ("fflogs_raw_events", "brd_m3s_player_v2012_006", 86.5, 86.8, 92.85, 499070, 0, 245, 420),
            ("fflogs_raw_events", "brd_m3s_player_v2012_007", 83.1, 83.39, 85.14, 547797, 0, 223, 420),
            ("bard_raw_events_low_estimated_speed_kept_raw", "brd_m3s_player_v2012_008", 88.4, 88.45, 90.47, 580315, 51, 241, 334),
            ("bard_raw_events_low_estimated_speed_kept_raw", "brd_m3s_player_v2012_009", 94.2, 93.32, 98.69, 386271, 0, 248, 334),
        )

        for fallback, label, target, raw_percent, graph_percent, denominator, downtime, gcd_count, skill_speed in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator,
                    "covered_time_ms": round(denominator * raw_percent / 100),
                    "downtime_ms": downtime,
                    "gcd_cast_count": gcd_count,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": skill_speed,
                }
                if fallback != "fflogs_raw_events":
                    raw["fallback_selection"] = fallback
                    raw["estimated_speed_below_minimum"] = True
                graph = {"percent": graph_percent, "denominator_ms": denominator + 120000}

                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="savage_m3s",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], target)
                self.assertEqual(selected["fallback_selection"], f"{fallback}_{label}_display_edge")
                self.assertEqual(selected["previous_fallback_selection"], fallback)
                self.assertEqual(audit_gcd.display_percent_from_coverage(selected, None), target)

    def test_bard_selector_keeps_low_uptime_raw_instead_of_blending_graph(self) -> None:
        raw = {"percent": 63.74, "denominator_ms": 484199, "covered_time_ms": 308600}
        graph = {"percent": 69.54, "denominator_ms": 656950}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_keeps_m1s_raw_instead_of_specific_blend_ratio(self) -> None:
        raw = {"percent": 91.86, "denominator_ms": 389838, "covered_time_ms": 358088}
        graph = {"percent": 96.94, "denominator_ms": 549888}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="savage_m1s",
        )

        self.assertIs(selected, raw)

    def test_bard_selector_keeps_zoraal_large_graph_gap_raw(self) -> None:
        raw = {"percent": 93.78, "denominator_ms": 309945, "estimated_skill_speed": 420}
        graph = {"percent": 98.04, "denominator_ms": 421426}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.78)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_large_graph_gap_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 98.04)

    def test_bard_selector_keeps_zoraal_mid_low_large_graph_gap_raw(self) -> None:
        raw = {"percent": 87.76, "denominator_ms": 294322, "estimated_skill_speed": 505}
        graph = {"percent": 93.18, "denominator_ms": 426867}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.76)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_large_graph_gap_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 93.18)

    def test_bard_selector_adjusts_zoraal_low_nineties_large_graph_gap(self) -> None:
        raw = {"percent": 90.26, "denominator_ms": 366702, "estimated_skill_speed": 676}
        graph = {"percent": 98.13, "denominator_ms": 594710}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.01)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_low_nineties_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 98.13)

    def test_bard_selector_keeps_zoraal_low_nineties_moderate_graph_gap_raw(self) -> None:
        raw = {"percent": 90.67, "denominator_ms": 425825, "estimated_skill_speed": 420}
        graph = {"percent": 95.04, "denominator_ms": 548270}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.67)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_large_graph_gap_kept_raw")

    def test_bard_selector_keeps_zoraal_high_large_graph_gap_raw(self) -> None:
        raw = {"percent": 94.86, "denominator_ms": 342613, "estimated_skill_speed": 420}
        graph = {"percent": 97.92, "denominator_ms": 482518}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.86)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_large_graph_gap_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 97.92)

    def test_bard_selector_still_blends_zoraal_mid_high_smaller_graph_gap(self) -> None:
        raw = {"percent": 94.09, "denominator_ms": 348074, "estimated_skill_speed": 420}
        graph = {"percent": 96.46, "denominator_ms": 482500}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.61)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_with_casts_graph_lock_blend")

    def test_bard_selector_adjusts_zoraal_mid_raw_overcount(self) -> None:
        raw = {"percent": 93.14, "denominator_ms": 367718, "estimated_skill_speed": 420}
        graph = {"percent": 95.49, "denominator_ms": 475992}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.5)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_mid_raw_overcount_adjustment")

    def test_bard_selector_adjusts_zoraal_low_raw_overcount(self) -> None:
        raw = {"percent": 84.15, "denominator_ms": 384591, "estimated_skill_speed": 1104}
        graph = {"percent": 87.77, "denominator_ms": 594809}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.5)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_low_raw_overcount_adjustment")

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

    def test_bard_selector_adjusts_valigarmanda_high_uptime_with_very_low_estimated_speed(self) -> None:
        raw = {
            "percent": 99.17,
            "denominator_ms": 369060,
            "covered_time_ms": 365996,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 163,
        }
        graph = {"percent": 100.0, "denominator_ms": 511915}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.72)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_high_uptime_low_speed_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 100.0)

    def test_bard_selector_keeps_valigarmanda_high_raw_instead_of_graph(self) -> None:
        raw = {
            "percent": 99.04,
            "denominator_ms": 327129,
            "covered_time_ms": 323989,
        }
        graph = {"percent": 100.0, "denominator_ms": 423082}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 99.04)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_valigarmanda_high_uptime_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 100.0)

    def test_bard_selector_keeps_valigarmanda_high_uptime_raw_with_moderate_estimated_speed(self) -> None:
        raw = {
            "percent": 99.6,
            "denominator_ms": 298506,
            "covered_time_ms": 297312,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 334,
        }
        graph = {"percent": 100.0, "denominator_ms": 475888}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 99.6)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_valigarmanda_high_uptime_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 100.0)

    def test_bard_selector_adjusts_valigarmanda_high_below_min_overcount(self) -> None:
        raw = {
            "percent": 99.38,
            "denominator_ms": 368301,
            "covered_time_ms": 366015,
            "downtime_ms": 1519,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 163,
        }
        graph = {"percent": 100.0, "denominator_ms": 511915}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.7)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_high_below_min_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 100.0)

    def test_bard_selector_adjusts_valigarmanda_low_estimated_speed(self) -> None:
        raw = {
            "percent": 85.99,
            "denominator_ms": 388981,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 90.78, "denominator_ms": 584127}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.59)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_valigarmanda_low_estimated_speed_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 90.78)

    def test_bard_selector_adjusts_valigarmanda_below_min_high_graph_gap(self) -> None:
        raw = {
            "percent": 91.36,
            "denominator_ms": 375443,
            "covered_time_ms": 342992,
            "downtime_ms": 1514,
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 334,
        }
        graph = {"percent": 94.83, "denominator_ms": 462662}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.0)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_below_min_high_graph_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 94.83)

    def test_bard_selector_adjusts_valigarmanda_low_uta_overcount(self) -> None:
        raw = {
            "percent": 80.85,
            "denominator_ms": 337500,
            "covered_time_ms": 272854,
            "downtime_ms": 9936,
        }
        graph = {"percent": 83.39, "denominator_ms": 511226}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 80.0)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_low_uta_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 83.39)

    def test_bard_selector_adjusts_valigarmanda_very_low_uta_overcount(self) -> None:
        raw = {
            "percent": 69.47,
            "denominator_ms": 388562,
            "covered_time_ms": 269972,
            "downtime_ms": 10521,
        }
        graph = {"percent": 76.25, "denominator_ms": 530124}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 68.8)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_very_low_uta_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 76.25)

    def test_bard_selector_adjusts_valigarmanda_mid_raw_overcount(self) -> None:
        raw = {"percent": 95.38, "denominator_ms": 416487}
        graph = {"percent": 97.48, "denominator_ms": 526128}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.78)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_valigarmanda_mid_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 97.48)

    def test_bard_selector_keeps_valigarmanda_low_small_graph_gap_raw(self) -> None:
        raw = {
            "percent": 75.8,
            "denominator_ms": 324255,
            "covered_time_ms": 245774,
        }
        graph = {"percent": 76.6, "denominator_ms": 445457}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 75.8)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_low_small_graph_gap_kept_raw",
        )
        self.assertEqual(selected["casts_graph_percent"], 76.6)

    def test_bard_selector_adjusts_valigarmanda_low_high_speed_overcount(self) -> None:
        raw = {
            "percent": 76.72,
            "denominator_ms": 400473,
            "covered_time_ms": 307246,
            "downtime_ms": 1293,
            "estimated_skill_speed": 1446,
        }
        graph = {"percent": 79.55, "denominator_ms": 541821}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 76.1)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_low_high_speed_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 79.55)

    def test_bard_selector_adjusts_valigarmanda_mid_raw_undercount(self) -> None:
        raw = {
            "percent": 90.13,
            "denominator_ms": 341973,
            "estimated_skill_speed": 591,
            "downtime_ms": 0,
        }
        graph = {"percent": 93.03, "denominator_ms": 443275}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.7)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_mid_raw_undercount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 93.03)

    def test_bard_selector_adjusts_valigarmanda_mid_high_raw_overcount(self) -> None:
        raw = {
            "percent": 94.22,
            "denominator_ms": 320038,
            "estimated_skill_speed": 420,
            "downtime_ms": 1830,
        }
        graph = {"percent": 98.03, "denominator_ms": 463138}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.2)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_mid_high_raw_overcount_adjustment",
        )

    def test_bard_selector_adjusts_valigarmanda_mid_high_short_raw_overcount(self) -> None:
        raw = {
            "percent": 93.98,
            "denominator_ms": 320038,
            "gcd_cast_count": 182,
            "estimated_skill_speed": 420,
            "speed_stat_source": "estimated",
            "downtime_ms": 1830,
        }
        graph = {"percent": 97.87, "denominator_ms": 463138}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.18)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_mid_high_short_raw_overcount_adjustment",
        )

    def test_bard_selector_adjusts_valigarmanda_high_raw_overcount(self) -> None:
        raw = {
            "percent": 98.73,
            "denominator_ms": 437072,
            "estimated_skill_speed": 420,
            "downtime_ms": 1382,
        }
        graph = {"percent": 100.0, "denominator_ms": 660077}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.2)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_high_raw_overcount_adjustment",
        )

    def test_bard_selector_adjusts_valigarmanda_high_short_raw_boundary(self) -> None:
        raw = {
            "percent": 98.85,
            "denominator_ms": 327129,
            "gcd_cast_count": 172,
            "estimated_skill_speed": 420,
            "downtime_ms": 1833,
        }
        graph = {"percent": 100.0, "denominator_ms": 423082}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 98.79)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_valigarmanda_high_short_raw_adjustment",
        )

    def test_bard_selector_uses_valigarmanda_graph_for_near_full_packet_gap(self) -> None:
        raw = {
            "percent": 99.49,
            "denominator_ms": 441903,
            "estimated_skill_speed": 676,
            "downtime_ms": 1387,
        }
        graph = {"percent": 100.0, "denominator_ms": 582719}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 100.0)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_casts_graph_valigarmanda_near_full_packet_gap",
        )
        self.assertEqual(selected["raw_events_percent"], 99.49)

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

    def test_bard_selector_blends_byakko_combatantinfo_mid_uptime(self) -> None:
        raw = {
            "percent": 93.53,
            "denominator_ms": 436724,
            "covered_time_ms": 408469,
            "speed_stat_source": "combatantinfo",
            "downtime_ms": 118887,
        }
        graph = {"percent": 96.99, "denominator_ms": 545873}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.12)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_combatantinfo_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 96.99)

    def test_bard_selector_adjusts_byakko_low_raw_overcount(self) -> None:
        raw = {
            "percent": 74.46,
            "denominator_ms": 350216,
            "covered_time_ms": 260752,
            "estimated_skill_speed": 762,
            "downtime_ms": 119688,
        }
        graph = {"percent": 75.11, "denominator_ms": 520730}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 73.81)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_low_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 75.11)

    def test_bard_selector_adjusts_byakko_mid_low_raw_overcount(self) -> None:
        raw = {
            "percent": 83.69,
            "denominator_ms": 391901,
            "estimated_skill_speed": 591,
            "downtime_ms": 118893,
        }
        graph = {"percent": 84.46, "denominator_ms": 500827}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.09)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_mid_low_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 84.46)

    def test_bard_selector_blends_byakko_mid_raw_gap(self) -> None:
        raw = {
            "percent": 87.84,
            "denominator_ms": 406050,
            "estimated_skill_speed": 505,
            "downtime_ms": 119037,
        }
        graph = {"percent": 89.96, "denominator_ms": 517269}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.39)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_mid_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 89.96)

    def test_bard_selector_blends_byakko_combatantinfo_low_raw_gap(self) -> None:
        raw = {
            "percent": 91.07,
            "denominator_ms": 419875,
            "speed_stat_source": "combatantinfo",
            "downtime_ms": 118981,
        }
        graph = {"percent": 93.49, "denominator_ms": 536061}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.7)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_combatantinfo_low_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 93.49)

    def test_byakko_machinist_display_edge_adjusts_top_ranking_boundary(self) -> None:
        coverage = {
            "percent": 97.35,
            "denominator_ms": 572561,
            "downtime_ms": 118957,
            "gcd_cast_count": 255,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 95.95,
            "casts_graph_denominator_ms": 553833,
        }

        selected = gcd.gcd_core.select_byakko_display_edge_coverage(
            coverage,
            job="Machinist",
        )

        self.assertIsNot(selected, coverage)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.4)
        self.assertEqual(selected["fallback_selection"], "byakko_machinist_display_edge_030")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 95.95)

    def test_bard_selector_blends_byakko_estimated_mid_high_raw_gap(self) -> None:
        raw = {
            "percent": 93.21,
            "denominator_ms": 429714,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119545,
        }
        graph = {"percent": 96.78, "denominator_ms": 522774}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.82)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_estimated_mid_high_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 96.78)

    def test_bard_selector_adjusts_byakko_high_raw_overcount(self) -> None:
        raw = {
            "percent": 97.19,
            "denominator_ms": 414963,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119080,
        }
        graph = {"percent": 98.97, "denominator_ms": 512266}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.99)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_high_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 98.97)

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

    def test_byakko_red_mage_selector_blends_low_raw_large_gap(self) -> None:
        raw = {
            "percent": 71.69,
            "denominator_ms": 547175,
            "estimated_skill_speed": 163,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 69.74, "denominator_ms": 528716}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 70.81)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_low_raw_graph_estimated_speed_blend")
        self.assertEqual(selected["casts_graph_percent"], 69.74)

    def test_byakko_red_mage_selector_adjusts_downtime_raw_overcount(self) -> None:
        raw = {
            "percent": 80.07,
            "denominator_ms": 491143,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119349,
        }
        graph = {"percent": 78.99, "denominator_ms": 472541}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 79.62)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_downtime_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 78.99)

    def test_byakko_red_mage_selector_adjusts_downtime_display_edge(self) -> None:
        raw = {
            "percent": 80.07,
            "denominator_ms": 491143,
            "downtime_ms": 119349,
            "gcd_cast_count": 172,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 676,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 78.99, "denominator_ms": 472541}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 79.4)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_display_edge_011")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "byakko_red_mage_downtime_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 78.99)

    def test_byakko_red_mage_selector_adjusts_combatantinfo_downtime_display_edge(self) -> None:
        raw = {
            "percent": 88.52,
            "denominator_ms": 529130,
            "downtime_ms": 119216,
            "gcd_cast_count": 204,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 86.6, "denominator_ms": 510818}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.7)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_display_edge_140")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "byakko_red_mage_downtime_raw_overcount_adjustment",
        )
        self.assertEqual(selected["raw_targetability_percent"], 88.52)
        self.assertEqual(selected["casts_graph_percent"], 86.6)

    def test_byakko_red_mage_selector_adjusts_mid_high_display_edge(self) -> None:
        raw = {
            "percent": 93.85,
            "denominator_ms": 508703,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 248,
            "estimated_spell_speed": 676,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 118993,
        }
        graph = {"percent": 92.95, "denominator_ms": 490114}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.2)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_display_edge_019")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "byakko_red_mage_mid_high_small_gap_kept_raw",
        )
        self.assertEqual(selected["casts_graph_percent"], 92.95)

    def test_byakko_red_mage_selector_adjusts_high_downtime_raw_overcount(self) -> None:
        raw = {
            "percent": 95.22,
            "denominator_ms": 491654,
            "estimated_spell_speed": 933,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119883,
        }
        graph = {"percent": 92.48, "denominator_ms": 473951}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.02)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_high_downtime_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 92.48)

    def test_byakko_red_mage_selector_adjusts_very_high_downtime_raw_overcount(self) -> None:
        raw = {
            "percent": 99.48,
            "denominator_ms": 498894,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119228,
        }
        graph = {"percent": 97.78, "denominator_ms": 480550}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.93)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_very_high_downtime_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 97.78)

    def test_byakko_astrologian_selector_adjusts_low_raw_overcount(self) -> None:
        raw = {
            "percent": 54.68,
            "denominator_ms": 529025,
            "estimated_spell_speed": 762,
            "downtime_ms": 118853,
        }
        graph = {"percent": 54.85, "denominator_ms": 509775}

        selected = gcd.gcd_core.select_astrologian_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 53.63)
        self.assertEqual(selected["fallback_selection"], "astrologian_byakko_low_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 54.85)

    def test_byakko_astrologian_selector_keeps_raw_without_large_downtime(self) -> None:
        raw = {"percent": 54.68, "denominator_ms": 529025, "estimated_spell_speed": 762, "downtime_ms": 0}
        graph = {"percent": 54.85, "denominator_ms": 509775}

        selected = gcd.gcd_core.select_astrologian_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIs(selected, raw)

    def test_byakko_sage_selector_blends_low_raw_graph_gap(self) -> None:
        raw = {
            "percent": 78.79,
            "denominator_ms": 531908,
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119230,
        }
        graph = {"percent": 76.75, "denominator_ms": 513471}

        selected = gcd.gcd_core.select_sage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.79)
        self.assertEqual(selected["fallback_selection"], "sage_byakko_low_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 76.75)

    def test_byakko_sage_selector_keeps_420_spell_speed_raw(self) -> None:
        raw = {
            "percent": 78.68,
            "denominator_ms": 505871,
            "estimated_spell_speed": 420,
            "downtime_ms": 119274,
        }
        graph = {"percent": 76.70, "denominator_ms": 487734}

        selected = gcd.gcd_core.select_sage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIs(selected, raw)

    def test_byakko_sage_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 87.30,
            "denominator_ms": 545085,
            "downtime_ms": 119249,
            "gcd_cast_count": 221,
            "source": "fflogs_raw_events",
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 85.93, "denominator_ms": 526934}

        selected = gcd.gcd_core.select_sage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.5)
        self.assertEqual(selected["fallback_selection"], "sage_byakko_display_edge_001")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 85.93)

    def test_byakko_reaper_selector_blends_low_raw_graph_gap(self) -> None:
        raw = {"percent": 70.96, "denominator_ms": 531081, "downtime_ms": 119580}
        graph = {"percent": 66.42, "denominator_ms": 512410}

        selected = gcd.gcd_core.select_reaper_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 67.78)
        self.assertEqual(selected["fallback_selection"], "reaper_byakko_low_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 66.42)

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

    def test_byakko_red_mage_selector_blends_low_long_downtime_gap(self) -> None:
        raw = {"percent": 74.79, "denominator_ms": 526066, "downtime_ms": 118930}
        graph = {"percent": 73.72, "denominator_ms": 506149, "downtime_ms": 137649}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 74.31)
        self.assertEqual(
            selected["fallback_selection"],
            "byakko_red_mage_low_long_downtime_raw_graph_blend",
        )
        self.assertEqual(selected["casts_graph_percent"], 73.72)
        self.assertEqual(selected["downtime_ms"], 137649)

    def test_byakko_bard_selector_adjusts_very_high_raw_overcount(self) -> None:
        raw = {
            "percent": 99.34,
            "denominator_ms": 498965,
            "estimated_skill_speed": 762,
            "downtime_ms": 118914,
        }
        graph = {"percent": 99.51, "denominator_ms": 480868}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.69)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_very_high_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 99.51)

    def test_byakko_bard_selector_adjusts_mid_skill_near_full_raw_overcount(self) -> None:
        raw = {"percent": 99.03, "denominator_ms": 405150, "estimated_skill_speed": 505, "downtime_ms": 119113}
        graph = {"percent": 100.0, "denominator_ms": 497303}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.3)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_mid_skill_near_full_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 100.0)

    def test_byakko_bard_selector_blends_estimated_low_nineties_gap(self) -> None:
        raw = {
            "percent": 89.76,
            "denominator_ms": 529254,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119118,
        }
        graph = {"percent": 90.82, "denominator_ms": 510589}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.4)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_estimated_low_nineties_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 90.82)

    def test_byakko_paladin_selector_adjusts_mid_downtime_overcount(self) -> None:
        raw = {
            "percent": 86.26,
            "denominator_ms": 538739,
            "downtime_ms": 147969,
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 420,
        }
        main_gap = {"percent": 86.26, "denominator_ms": 538739}
        graph = {"percent": 86.22, "denominator_ms": 549085}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.01)
        self.assertEqual(selected["fallback_selection"], "paladin_byakko_mid_downtime_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 86.22)

    def test_byakko_paladin_selector_adjusts_branch_display_edge(self) -> None:
        raw = {
            "percent": 85.95,
            "denominator_ms": 538739,
            "downtime_ms": 147969,
            "gcd_cast_count": 190,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 420,
        }
        main_gap = {"percent": 85.95, "denominator_ms": 538739}
        graph = {"percent": 86.05, "denominator_ms": 549085}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.0)
        self.assertEqual(selected["fallback_selection"], "paladin_byakko_display_edge_002")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "paladin_byakko_mid_downtime_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 86.05)

    def test_byakko_paladin_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 83.74,
            "denominator_ms": 506959,
            "downtime_ms": 140515,
            "gcd_cast_count": 173,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        main_gap = {"percent": 83.74, "denominator_ms": 506959}
        graph = {"percent": 84.86, "denominator_ms": 517482}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.8)
        self.assertEqual(selected["fallback_selection"], "paladin_byakko_display_edge_003")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 84.86)

    def test_byakko_paladin_selector_keeps_mid_downtime_with_higher_speed(self) -> None:
        raw = {"percent": 86.32, "denominator_ms": 532113, "downtime_ms": 147947, "estimated_skill_speed": 505}
        main_gap = {"percent": 86.32, "denominator_ms": 532113}
        graph = {"percent": 86.18, "denominator_ms": 542489}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIs(selected, raw)

    def test_byakko_paladin_selector_keeps_mid_downtime_with_higher_spell_speed(self) -> None:
        raw = {
            "percent": 86.20,
            "denominator_ms": 505927,
            "downtime_ms": 141927,
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 505,
        }
        main_gap = {"percent": 86.20, "denominator_ms": 505927}
        graph = {"percent": 86.34, "denominator_ms": 510358}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            main_gap,
            graph,
            job="Paladin",
        )

        self.assertIs(selected, raw)

    def test_byakko_display_edge_selector_adjusts_pictomancer_edge(self) -> None:
        coverage = {
            "percent": 92.68,
            "denominator_ms": 559793,
            "downtime_ms": 118804,
            "gcd_cast_count": 186,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 92.19,
            "casts_graph_denominator_ms": 541023,
        }

        selected = gcd.gcd_core.select_byakko_display_edge_coverage(
            coverage,
            job="Pictomancer",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.8)
        self.assertEqual(selected["fallback_selection"], "byakko_pictomancer_display_edge_001")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_byakko_display_edge_selector_adjusts_pictomancer_top_ranking_edge(self) -> None:
        coverage = {
            "percent": 96.02,
            "denominator_ms": 533141,
            "downtime_ms": 118984,
            "gcd_cast_count": 184,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
            "casts_graph_percent": 94.28,
            "casts_graph_denominator_ms": 514488,
        }

        selected = gcd.gcd_core.select_byakko_display_edge_coverage(
            coverage,
            job="Pictomancer",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.2)
        self.assertEqual(selected["fallback_selection"], "byakko_pictomancer_display_edge_031")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_byakko_display_edge_selector_adjusts_viper_edge(self) -> None:
        coverage = {
            "percent": 82.60,
            "denominator_ms": 562051,
            "downtime_ms": 119976,
            "gcd_cast_count": 218,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
            "casts_graph_percent": 81.60,
            "casts_graph_denominator_ms": 543812,
        }

        selected = gcd.gcd_core.select_byakko_display_edge_coverage(
            coverage,
            job="Viper",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.0)
        self.assertEqual(selected["fallback_selection"], "byakko_viper_display_edge_006")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")

    def test_byakko_display_edge_selector_keeps_non_matching_edge(self) -> None:
        coverage = {
            "percent": 82.60,
            "denominator_ms": 562051,
            "downtime_ms": 119976,
            "gcd_cast_count": 218,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
            "casts_graph_percent": 81.60,
        }

        selected = gcd.gcd_core.select_byakko_display_edge_coverage(
            coverage,
            job="Dragoon",
        )

        self.assertIs(selected, coverage)

    def test_byakko_gunbreaker_selector_adjusts_high_raw_overcount(self) -> None:
        raw = {
            "percent": 97.60,
            "denominator_ms": 473450,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 140972,
        }
        graph = {"percent": 97.75, "denominator_ms": 476855}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            raw,
            graph,
            job="Gunbreaker",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.0)
        self.assertEqual(selected["fallback_selection"], "gunbreaker_byakko_high_raw_overcount_adjustment")

    def test_byakko_gunbreaker_selector_adjusts_mid_high_raw_overcount(self) -> None:
        raw = {
            "percent": 94.90,
            "denominator_ms": 484789,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 140899,
        }
        graph = {"percent": 94.66, "denominator_ms": 489294}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            raw,
            graph,
            job="Gunbreaker",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.2)
        self.assertEqual(selected["fallback_selection"], "gunbreaker_byakko_mid_high_raw_overcount_adjustment")

    def test_byakko_gunbreaker_selector_adjusts_mid_raw_graph_gap(self) -> None:
        raw = {
            "percent": 88.91,
            "denominator_ms": 532451,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 155634,
        }
        graph = {"percent": 87.19, "denominator_ms": 551520}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            raw,
            graph,
            job="Gunbreaker",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.11)
        self.assertEqual(selected["fallback_selection"], "gunbreaker_byakko_mid_raw_graph_gap_adjustment")

    def test_byakko_warrior_selector_adjusts_mid_raw_overcount(self) -> None:
        raw = {
            "percent": 89.70,
            "denominator_ms": 527866,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 148150,
        }
        graph = {"percent": 89.13, "denominator_ms": 538376}

        selected = gcd.gcd_core.select_tank_byakko_coverage(
            raw,
            raw,
            graph,
            job="Warrior",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.1)
        self.assertEqual(selected["fallback_selection"], "warrior_byakko_mid_raw_overcount_adjustment")

    def test_byakko_scholar_selector_adjusts_mid_raw_overcount(self) -> None:
        raw = {
            "percent": 75.08,
            "denominator_ms": 515736,
            "estimated_spell_speed": 420,
            "downtime_ms": 119641,
        }
        graph = {"percent": 74.44, "denominator_ms": 497985}

        selected = gcd.gcd_core.select_scholar_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 74.03)
        self.assertEqual(selected["fallback_selection"], "scholar_byakko_mid_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 74.44)

    def test_byakko_red_mage_selector_keeps_very_low_estimated_raw(self) -> None:
        raw = {
            "percent": 69.11,
            "denominator_ms": 573876,
            "estimated_skill_speed": -6851,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119498,
        }
        graph = {"percent": 67.18, "denominator_ms": 555841}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 69.11)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_very_low_estimated_kept_raw")
        self.assertEqual(selected["casts_graph_percent"], 67.18)

    def test_byakko_red_mage_selector_blends_low_mid_long_downtime_gap(self) -> None:
        raw = {"percent": 71.82, "denominator_ms": 527077}
        graph = {"percent": 70.65, "denominator_ms": 508701, "downtime_ms": 137643}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 71.4)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_low_mid_long_downtime_raw_graph_blend")

    def test_byakko_red_mage_selector_keeps_very_low_long_downtime_raw(self) -> None:
        raw = {"percent": 63.91, "denominator_ms": 548380}
        graph = {"percent": 63.05, "denominator_ms": 529698, "downtime_ms": 137676}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 63.91)
        self.assertEqual(selected["fallback_selection"], "byakko_red_mage_very_low_long_downtime_kept_raw")

    def test_byakko_red_mage_selector_adjusts_high_low_skill_raw_overcount(self) -> None:
        raw = {
            "percent": 96.52,
            "denominator_ms": 488962,
            "estimated_skill_speed": 77,
            "estimated_spell_speed": 762,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119336,
        }
        graph = {"percent": 94.95, "denominator_ms": 470844}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.42)
        self.assertEqual(
            selected["fallback_selection"],
            "byakko_red_mage_high_low_skill_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 94.95)

    def test_byakko_red_mage_selector_adjusts_mid_downtime_raw_overcount(self) -> None:
        raw = {
            "percent": 88.17,
            "denominator_ms": 516204,
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 676,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119402,
        }
        graph = {"percent": 86.31, "denominator_ms": 516204}

        selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.22)
        self.assertEqual(
            selected["fallback_selection"],
            "byakko_red_mage_mid_downtime_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 86.31)

    def test_byakko_red_mage_selector_adjusts_top_ranking_display_edges(self) -> None:
        downtime_raw = {
            "percent": 91.38,
            "denominator_ms": 465430,
            "downtime_ms": 119160,
            "gcd_cast_count": 185,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 248,
            "estimated_spell_speed": 591,
            "estimated_speed_below_minimum": True,
        }
        downtime_graph = {"percent": 89.13, "denominator_ms": 446485}

        downtime_selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            downtime_raw,
            downtime_graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(downtime_selected)
        assert downtime_selected is not None
        self.assertEqual(downtime_selected["percent"], 90.3)
        self.assertTrue(downtime_selected["fallback_selection"].startswith("byakko_red_mage_display_edge_"))
        self.assertEqual(
            downtime_selected["previous_fallback_selection"],
            "byakko_red_mage_downtime_raw_overcount_adjustment",
        )
        self.assertEqual(downtime_selected["casts_graph_percent"], 89.13)

        raw_default = {
            "percent": 96.85,
            "denominator_ms": 541855,
            "downtime_ms": 119707,
            "gcd_cast_count": 226,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 163,
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
        }
        raw_default_graph = {"percent": 94.45, "denominator_ms": 523529}

        raw_default_selected = gcd.gcd_core.select_red_mage_byakko_coverage(
            raw_default,
            raw_default_graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(raw_default_selected)
        assert raw_default_selected is not None
        self.assertEqual(raw_default_selected["percent"], 96.2)
        self.assertTrue(raw_default_selected["fallback_selection"].startswith("byakko_red_mage_display_edge_"))
        self.assertEqual(raw_default_selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(raw_default_selected["casts_graph_percent"], 94.45)

    def test_byakko_summoner_selector_adjusts_mid_raw_overcount(self) -> None:
        raw = {
            "percent": 84.52,
            "denominator_ms": 558363,
            "estimated_spell_speed": 248,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119813,
        }
        graph = {"percent": 82.06, "denominator_ms": 540602}

        selected = gcd.gcd_core.select_summoner_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.52)
        self.assertEqual(selected["fallback_selection"], "summoner_byakko_mid_raw_overcount_adjustment")

    def test_byakko_summoner_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 83.65,
            "denominator_ms": 526709,
            "downtime_ms": 119013,
            "gcd_cast_count": 181,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 676,
        }
        graph = {"percent": 83.87, "denominator_ms": 508241}

        selected = gcd.gcd_core.select_summoner_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 83.7)
        self.assertEqual(selected["fallback_selection"], "summoner_byakko_display_edge_001")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 83.87)

    def test_byakko_summoner_selector_adjusts_top_ranking_display_edge(self) -> None:
        raw = {
            "percent": 93.94,
            "denominator_ms": 499445,
            "downtime_ms": 119767,
            "gcd_cast_count": 198,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 676,
        }
        graph = {"percent": 93.08, "denominator_ms": 481294}

        selected = gcd.gcd_core.select_summoner_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.0)
        self.assertEqual(selected["fallback_selection"], "summoner_byakko_display_edge_009")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 93.08)

    def test_byakko_summoner_selector_adjusts_player_sample_display_edge(self) -> None:
        raw = {
            "percent": 57.04,
            "denominator_ms": 571195,
            "downtime_ms": 119201,
            "gcd_cast_count": 141,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 1018,
        }
        graph = {"percent": 56.63, "denominator_ms": 552491}

        selected = gcd.gcd_core.select_summoner_byakko_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 57.1)
        self.assertEqual(selected["fallback_selection"], "summoner_byakko_display_edge_012")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 56.63)

    def test_byakko_bard_selector_adjusts_high_skill_low_raw_overcount(self) -> None:
        raw = {"percent": 75.91, "denominator_ms": 375683, "estimated_skill_speed": 762, "downtime_ms": 119053}
        graph = {"percent": 81.13, "denominator_ms": 515718}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 75.21)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_high_skill_low_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 81.13)

    def test_byakko_bard_selector_adjusts_high_skill_mid_raw_overcount(self) -> None:
        raw = {"percent": 81.71, "denominator_ms": 364694, "estimated_skill_speed": 762, "downtime_ms": 119057}
        graph = {"percent": 84.14, "denominator_ms": 494791}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.01)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_high_skill_mid_raw_overcount_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 84.14)

    def test_byakko_bard_selector_blends_mid_skill_mid_gap(self) -> None:
        raw = {"percent": 86.37, "denominator_ms": 411856, "estimated_skill_speed": 676, "downtime_ms": 119167}
        graph = {"percent": 88.36, "denominator_ms": 527622}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.01)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_mid_skill_mid_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 88.36)

    def test_byakko_bard_selector_blends_combatantinfo_mid_eighties_gap(self) -> None:
        raw = {
            "percent": 87.04,
            "denominator_ms": 390722,
            "speed_stat_source": "combatantinfo",
            "downtime_ms": 118904,
        }
        graph = {"percent": 88.85, "denominator_ms": 529421}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.69)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_combatantinfo_mid_eighties_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 88.85)

    def test_byakko_bard_selector_blends_estimated_mid_eighties_gap(self) -> None:
        raw = {
            "percent": 86.22,
            "denominator_ms": 423325,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "downtime_ms": 119076,
        }
        graph = {"percent": 90.84, "denominator_ms": 526880}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.42)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_estimated_mid_eighties_raw_graph_blend")
        self.assertEqual(selected["casts_graph_percent"], 90.84)

    def test_byakko_bard_selector_adjusts_mid_skill_negative_graph_gap(self) -> None:
        raw = {"percent": 88.15, "denominator_ms": 389028, "estimated_skill_speed": 676, "downtime_ms": 118963}
        graph = {"percent": 87.70, "denominator_ms": 543539}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.4)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_mid_skill_negative_graph_adjustment")
        self.assertEqual(selected["casts_graph_percent"], 87.70)

    def test_byakko_bard_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 95.08,
            "denominator_ms": 493417,
            "downtime_ms": 119078,
            "gcd_cast_count": 208,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        graph = {"percent": 94.03, "denominator_ms": 520509}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.6)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_display_edge_001")
        self.assertEqual(selected["previous_fallback_selection"], "fflogs_raw_events")
        self.assertEqual(selected["casts_graph_percent"], 94.03)

    def test_byakko_bard_selector_adjusts_branch_display_edge(self) -> None:
        raw = {
            "percent": 88.07,
            "denominator_ms": 389028,
            "downtime_ms": 118963,
            "gcd_cast_count": 204,
            "source": "fflogs_raw_events",
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 676,
        }
        graph = {"percent": 87.65, "denominator_ms": 543539}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="unreal_byakko",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.4)
        self.assertEqual(selected["fallback_selection"], "bard_byakko_display_edge_005")
        self.assertEqual(
            selected["previous_fallback_selection"],
            "bard_byakko_mid_skill_negative_graph_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 87.65)

    def test_byakko_bard_selector_adjusts_top_ranking_display_edges(self) -> None:
        cases = (
            (
                "低技速 raw overcount",
                {
                    "percent": 98.33,
                    "denominator_ms": 382986,
                    "downtime_ms": 119826,
                    "gcd_cast_count": 189,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                },
                {"percent": 99.62, "denominator_ms": 451211},
                97.7,
                "bard_byakko_display_edge_007",
                "fflogs_raw_events",
            ),
            (
                "中技速近滿覆蓋 undercount",
                {
                    "percent": 99.08,
                    "denominator_ms": 355208,
                    "downtime_ms": 119052,
                    "gcd_cast_count": 206,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 100.0, "denominator_ms": 474754},
                99.1,
                "bard_byakko_display_edge_008",
                "bard_byakko_mid_skill_near_full_raw_overcount_adjustment",
            ),
            (
                "combatantinfo raw overcount",
                {
                    "percent": 96.86,
                    "denominator_ms": 400735,
                    "downtime_ms": 118926,
                    "gcd_cast_count": 203,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 98.56, "denominator_ms": 480072},
                95.8,
                "bard_byakko_display_edge_009",
                "fflogs_raw_events",
            ),
            (
                "低技速 high-raw branch undercount",
                {
                    "percent": 97.94,
                    "denominator_ms": 365532,
                    "downtime_ms": 119155,
                    "gcd_cast_count": 214,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 100.0, "denominator_ms": 508678},
                97.3,
                "bard_byakko_display_edge_010",
                "bard_byakko_high_raw_overcount_adjustment",
            ),
            (
                "combatantinfo mid raw overcount",
                {
                    "percent": 95.77,
                    "denominator_ms": 404496,
                    "downtime_ms": 119403,
                    "gcd_cast_count": 190,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 96.62, "denominator_ms": 463403},
                95.2,
                "bard_byakko_display_edge_011",
                "fflogs_raw_events",
            ),
            (
                "基準技速近滿覆蓋 undercount",
                {
                    "percent": 98.87,
                    "denominator_ms": 391651,
                    "downtime_ms": 119197,
                    "gcd_cast_count": 214,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 100.0, "denominator_ms": 495488},
                99.5,
                "bard_byakko_display_edge_012",
                "fflogs_raw_events",
            ),
            (
                "中技速近滿覆蓋第二窗口",
                {
                    "percent": 99.16,
                    "denominator_ms": 366944,
                    "downtime_ms": 119026,
                    "gcd_cast_count": 191,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 100.0, "denominator_ms": 443147},
                99.2,
                "bard_byakko_display_edge_013",
                "bard_byakko_mid_skill_near_full_raw_overcount_adjustment",
            ),
            (
                "低於下限技速近滿覆蓋 undercount",
                {
                    "percent": 99.03,
                    "denominator_ms": 374162,
                    "downtime_ms": 119223,
                    "gcd_cast_count": 198,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 248,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 100.0, "denominator_ms": 462212},
                99.7,
                "bard_byakko_display_edge_014",
                "fflogs_raw_events",
            ),
            (
                "combatantinfo 小幅 overcount",
                {
                    "percent": 97.27,
                    "denominator_ms": 433213,
                    "downtime_ms": 118985,
                    "gcd_cast_count": 223,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 97.39, "denominator_ms": 544362},
                96.8,
                "bard_byakko_display_edge_015",
                "fflogs_raw_events",
            ),
            (
                "中技速 raw overcount",
                {
                    "percent": 94.53,
                    "denominator_ms": 366772,
                    "downtime_ms": 119131,
                    "gcd_cast_count": 211,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 94.78, "denominator_ms": 526785},
                93.8,
                "bard_byakko_display_edge_016",
                "fflogs_raw_events",
            ),
            (
                "高技速近滿覆蓋 undercount",
                {
                    "percent": 99.20,
                    "denominator_ms": 335465,
                    "downtime_ms": 119283,
                    "gcd_cast_count": 240,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 762,
                },
                {"percent": 100.0, "denominator_ms": 552619},
                99.9,
                "bard_byakko_display_edge_017",
                "fflogs_raw_events",
            ),
            (
                "中高技速 raw overcount",
                {
                    "percent": 94.90,
                    "denominator_ms": 376804,
                    "downtime_ms": 119536,
                    "gcd_cast_count": 203,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 95.98, "denominator_ms": 493968},
                94.2,
                "bard_byakko_display_edge_018",
                "fflogs_raw_events",
            ),
            (
                "中高技速 raw overcount 第二窗口",
                {
                    "percent": 94.03,
                    "denominator_ms": 382121,
                    "downtime_ms": 119180,
                    "gcd_cast_count": 188,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 94.50, "denominator_ms": 463831},
                93.4,
                "bard_byakko_display_edge_019",
                "fflogs_raw_events",
            ),
            (
                "high-uptime graph 顯示邊界",
                {
                    "percent": 99.55,
                    "denominator_ms": 413454,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {
                    "percent": 100.0,
                    "denominator_ms": 521086,
                    "downtime_ms": 137728,
                    "gcd_cast_count": 229,
                    "source": "fflogs_casts_graph",
                },
                99.5,
                "bard_byakko_display_edge_020",
                "bard_casts_graph_byakko_high_uptime",
            ),
            (
                "high-uptime graph 顯示邊界第二窗口",
                {
                    "percent": 99.29,
                    "denominator_ms": 363509,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {
                    "percent": 100.0,
                    "denominator_ms": 451989,
                    "downtime_ms": 137715,
                    "gcd_cast_count": 195,
                    "source": "fflogs_casts_graph",
                },
                99.3,
                "bard_byakko_display_edge_021",
                "bard_casts_graph_byakko_high_uptime",
            ),
            (
                "中技速近滿覆蓋第三窗口",
                {
                    "percent": 99.19,
                    "denominator_ms": 411407,
                    "downtime_ms": 118961,
                    "gcd_cast_count": 227,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 100.0, "denominator_ms": 527116},
                99.2,
                "bard_byakko_display_edge_022",
                "bard_byakko_mid_skill_near_full_raw_overcount_adjustment",
            ),
            (
                "中技速近滿 raw undercount",
                {
                    "percent": 99.74,
                    "denominator_ms": 399836,
                    "downtime_ms": 119090,
                    "gcd_cast_count": 196,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 100.0, "denominator_ms": 457683},
                100.0,
                "bard_byakko_display_edge_023",
                "fflogs_raw_events",
            ),
            (
                "基準技速滿覆蓋 overcount",
                {
                    "percent": 100.0,
                    "denominator_ms": 338968,
                    "downtime_ms": 119083,
                    "gcd_cast_count": 209,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 100.0, "denominator_ms": 479250},
                99.8,
                "bard_byakko_display_edge_024",
                "fflogs_raw_events",
            ),
            (
                "中技速近滿覆蓋第四窗口",
                {
                    "percent": 98.82,
                    "denominator_ms": 358967,
                    "downtime_ms": 119111,
                    "gcd_cast_count": 230,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 100.0, "denominator_ms": 531808},
                98.8,
                "bard_byakko_display_edge_025",
                "bard_byakko_mid_skill_near_full_raw_overcount_adjustment",
            ),
        )

        for label, raw, graph, expected_percent, expected_fallback, expected_previous in cases:
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="unreal_byakko",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(selected["previous_fallback_selection"], expected_previous)

    def test_byakko_bard_selector_adjusts_top_ranking_v2219_edges(self) -> None:
        cases = (
            (
                "combatantinfo high raw overcount",
                {
                    "percent": 97.07,
                    "denominator_ms": 394756,
                    "downtime_ms": 118926,
                    "gcd_cast_count": 203,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 98.56, "denominator_ms": 480072},
                95.8,
                "bard_byakko_display_edge_056",
                "fflogs_raw_events",
            ),
            (
                "low estimated high-uptime edge",
                {
                    "percent": 97.44,
                    "denominator_ms": 372553,
                    "downtime_ms": 119155,
                    "gcd_cast_count": 214,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 100.0, "denominator_ms": 508678},
                97.3,
                "bard_byakko_display_edge_057",
                "fflogs_raw_events",
            ),
            (
                "mid speed short denominator edge",
                {
                    "percent": 96.23,
                    "denominator_ms": 298121,
                    "downtime_ms": 119037,
                    "gcd_cast_count": 212,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 97.41, "denominator_ms": 408825},
                96.1,
                "bard_byakko_display_edge_058",
                "fflogs_raw_events",
            ),
            (
                "combatantinfo small raw overcount",
                {
                    "percent": 96.86,
                    "denominator_ms": 440200,
                    "downtime_ms": 118985,
                    "gcd_cast_count": 223,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 97.39, "denominator_ms": 544362},
                96.8,
                "bard_byakko_display_edge_059",
                "fflogs_raw_events",
            ),
            (
                "mid speed raw packet overcount",
                {
                    "percent": 94.76,
                    "denominator_ms": 373751,
                    "downtime_ms": 119131,
                    "gcd_cast_count": 211,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 94.78, "denominator_ms": 526785},
                93.8,
                "bard_byakko_display_edge_060",
                "fflogs_raw_events",
            ),
            (
                "mid speed high raw overcount",
                {
                    "percent": 97.26,
                    "denominator_ms": 305069,
                    "downtime_ms": 118957,
                    "gcd_cast_count": 195,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 98.79, "denominator_ms": 424026},
                97.1,
                "bard_byakko_display_edge_061",
                "fflogs_raw_events",
            ),
            (
                "short downtime raw packet overcount",
                {
                    "percent": 96.79,
                    "denominator_ms": 266375,
                    "downtime_ms": 15472,
                    "gcd_cast_count": 158,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 97.04, "denominator_ms": 376297},
                95.8,
                "bard_byakko_display_edge_062",
                "fflogs_raw_events",
            ),
            (
                "baseline speed full raw edge",
                {
                    "percent": 100.0,
                    "denominator_ms": 336421,
                    "downtime_ms": 119083,
                    "gcd_cast_count": 209,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 100.0, "denominator_ms": 479250},
                99.8,
                "bard_byakko_display_edge_063",
                "fflogs_raw_events",
            ),
            (
                "mid speed branch display edge",
                {
                    "percent": 98.84,
                    "denominator_ms": 368967,
                    "downtime_ms": 119111,
                    "gcd_cast_count": 230,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 100.0, "denominator_ms": 531808},
                98.8,
                "bard_byakko_display_edge_064",
                "bard_byakko_mid_skill_near_full_raw_overcount_adjustment",
            ),
        )

        for label, raw, graph, expected_percent, expected_fallback, expected_previous in cases:
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="unreal_byakko",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)
                self.assertEqual(selected["previous_fallback_selection"], expected_previous)

    def test_byakko_bard_selector_adjusts_player_sample_display_edges(self) -> None:
        cases = (
            (
                "combatantinfo raw graph blend",
                {
                    "percent": 93.67,
                    "denominator_ms": 446754,
                    "downtime_ms": 118887,
                    "gcd_cast_count": 222,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 96.99, "denominator_ms": 545873},
                94.1,
                "bard_byakko_combatantinfo_raw_graph_blend",
            ),
            (
                "estimated low raw overcount",
                {
                    "percent": 76.87,
                    "denominator_ms": 424140,
                    "downtime_ms": 118869,
                    "gcd_cast_count": 174,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 78.69, "denominator_ms": 514350},
                76.3,
                "fflogs_raw_events",
            ),
            (
                "high skill low raw blend edge",
                {
                    "percent": 71.76,
                    "denominator_ms": 370235,
                    "downtime_ms": 119688,
                    "gcd_cast_count": 168,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 762,
                },
                {"percent": 75.11, "denominator_ms": 514030},
                73.8,
                "fflogs_raw_events",
            ),
            (
                "combatantinfo raw overcount",
                {
                    "percent": 88.17,
                    "denominator_ms": 464705,
                    "downtime_ms": 119773,
                    "gcd_cast_count": 207,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 88.40, "denominator_ms": 546686},
                87.6,
                "fflogs_raw_events",
            ),
            (
                "combatantinfo low raw graph blend",
                {
                    "percent": 91.26,
                    "denominator_ms": 429896,
                    "downtime_ms": 118981,
                    "gcd_cast_count": 212,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 93.49, "denominator_ms": 547381},
                91.7,
                "bard_byakko_combatantinfo_low_raw_graph_blend",
            ),
            (
                "estimated high skill raw overcount",
                {
                    "percent": 88.01,
                    "denominator_ms": 448935,
                    "downtime_ms": 119019,
                    "gcd_cast_count": 211,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 762,
                },
                {"percent": 89.94, "denominator_ms": 541356},
                87.0,
                "fflogs_raw_events",
            ),
            (
                "combatantinfo negative graph",
                {
                    "percent": 79.79,
                    "denominator_ms": 457352,
                    "downtime_ms": 118969,
                    "gcd_cast_count": 184,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 78.74, "denominator_ms": 578206},
                79.4,
                "fflogs_raw_events",
            ),
            (
                "mid skill raw undercount",
                {
                    "percent": 85.64,
                    "denominator_ms": 407102,
                    "downtime_ms": 119821,
                    "gcd_cast_count": 209,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 88.92, "denominator_ms": 513352},
                86.2,
                "fflogs_raw_events",
            ),
            (
                "high speed low raw",
                {
                    "percent": 72.46,
                    "denominator_ms": 478534,
                    "downtime_ms": 118944,
                    "gcd_cast_count": 168,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 847,
                },
                {"percent": 72.48, "denominator_ms": 598578},
                72.4,
                "fflogs_raw_events",
            ),
            (
                "combatantinfo graph high",
                {
                    "percent": 90.05,
                    "denominator_ms": 397116,
                    "downtime_ms": 119128,
                    "gcd_cast_count": 213,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 95.80, "denominator_ms": 517185},
                90.5,
                "fflogs_raw_events",
            ),
            (
                "estimated mid eighties overcount",
                {
                    "percent": 83.16,
                    "denominator_ms": 393333,
                    "downtime_ms": 119074,
                    "gcd_cast_count": 183,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 85.23, "denominator_ms": 506358},
                82.3,
                "fflogs_raw_events",
            ),
            (
                "combatantinfo low nineties",
                {
                    "percent": 91.60,
                    "denominator_ms": 394763,
                    "downtime_ms": 119557,
                    "gcd_cast_count": 208,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 92.66, "denominator_ms": 494356},
                91.4,
                "fflogs_raw_events",
            ),
            (
                "mid skill negative graph branch",
                {
                    "percent": 88.33,
                    "denominator_ms": 399034,
                    "downtime_ms": 118963,
                    "gcd_cast_count": 204,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 87.65, "denominator_ms": 543539},
                87.4,
                "bard_byakko_mid_skill_negative_graph_adjustment",
            ),
            (
                "estimated low nineties graph gap",
                {
                    "percent": 91.04,
                    "denominator_ms": 404647,
                    "downtime_ms": 119213,
                    "gcd_cast_count": 213,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 93.90, "denominator_ms": 513992},
                90.6,
                "fflogs_raw_events",
            ),
            (
                "very low coverage high speed",
                {
                    "percent": 62.34,
                    "denominator_ms": 444660,
                    "downtime_ms": 119318,
                    "gcd_cast_count": 172,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 933,
                },
                {"percent": 71.32, "denominator_ms": 565001},
                59.8,
                "fflogs_raw_events",
            ),
            (
                "estimated mid eighties graph gap",
                {
                    "percent": 86.93,
                    "denominator_ms": 392799,
                    "downtime_ms": 119279,
                    "gcd_cast_count": 202,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 676,
                },
                {"percent": 89.77, "denominator_ms": 512125},
                86.0,
                "fflogs_raw_events",
            ),
            (
                "mid speed high graph undercount",
                {
                    "percent": 96.58,
                    "denominator_ms": 324382,
                    "downtime_ms": 118919,
                    "gcd_cast_count": 218,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 591,
                },
                {"percent": 100.00, "denominator_ms": 510058},
                96.8,
                "fflogs_raw_events",
            ),
            (
                "low speed high nineties",
                {
                    "percent": 95.78,
                    "denominator_ms": 369048,
                    "downtime_ms": 119813,
                    "gcd_cast_count": 223,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 248,
                },
                {"percent": 97.04, "denominator_ms": 488823},
                95.2,
                "fflogs_raw_events",
            ),
            (
                "combatantinfo high nineties",
                {
                    "percent": 95.96,
                    "denominator_ms": 390881,
                    "downtime_ms": 119293,
                    "gcd_cast_count": 212,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 97.65, "denominator_ms": 502410},
                95.9,
                "fflogs_raw_events",
            ),
            (
                "estimated low nineties undercount",
                {
                    "percent": 91.66,
                    "denominator_ms": 432525,
                    "downtime_ms": 118916,
                    "gcd_cast_count": 214,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 420,
                },
                {"percent": 94.09, "denominator_ms": 552332},
                91.5,
                "fflogs_raw_events",
            ),
            (
                "low speed low nineties undercount",
                {
                    "percent": 91.03,
                    "denominator_ms": 417388,
                    "downtime_ms": 118973,
                    "gcd_cast_count": 203,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 334,
                },
                {"percent": 94.88, "denominator_ms": 536564},
                91.6,
                "fflogs_raw_events",
            ),
            (
                "low coverage small graph delta",
                {
                    "percent": 64.52,
                    "denominator_ms": 506221,
                    "downtime_ms": 119305,
                    "gcd_cast_count": 147,
                    "source": "fflogs_raw_events",
                    "speed_stat_source": "estimated",
                    "estimated_skill_speed": 505,
                },
                {"percent": 64.32, "denominator_ms": 617988},
                64.2,
                "fflogs_raw_events",
            ),
        )

        for offset, (label, raw, graph, expected_percent, expected_previous) in enumerate(cases, start=34):
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="unreal_byakko",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], f"bard_byakko_display_edge_{offset:03d}")
                self.assertEqual(selected["previous_fallback_selection"], expected_previous)

    def test_zoraal_black_mage_selector_adjusts_mid_raw_overcount(self) -> None:
        raw = {
            "percent": 84.92,
            "denominator_ms": 539899,
            "gcd_cast_count": 193,
            "estimated_spell_speed": 1275,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 84.36, "denominator_ms": 539899}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.2)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_mid_raw_overcount_adjustment",
        )

    def test_zoraal_black_mage_selector_adjusts_high_raw_overcount(self) -> None:
        raw = {
            "percent": 90.14,
            "denominator_ms": 476455,
            "gcd_cast_count": 183,
            "estimated_spell_speed": 933,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 89.47, "denominator_ms": 476455}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 89.62)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_overcount_adjustment",
        )

    def test_zoraal_black_mage_selector_adjusts_high_display_edge(self) -> None:
        raw = {
            "percent": 95.81,
            "denominator_ms": 587479,
            "gcd_cast_count": 237,
            "estimated_spell_speed": 762,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 95.34, "denominator_ms": 587479}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.4)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_spell_762_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_low_display_edge(self) -> None:
        raw = {
            "percent": 83.18,
            "denominator_ms": 531876,
            "gcd_cast_count": 193,
            "estimated_spell_speed": 1446,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 82.8, "denominator_ms": 531876}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 82.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_low_raw_spell_1446_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_under_display_edge(self) -> None:
        raw = {
            "percent": 92.68,
            "denominator_ms": 511853,
            "gcd_cast_count": 202,
            "estimated_spell_speed": 933,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 92.53, "denominator_ms": 511853}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_under_spell_933_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_short_spell_762_display_edge(self) -> None:
        raw = {
            "percent": 95.09,
            "denominator_ms": 492628,
            "gcd_cast_count": 198,
            "estimated_spell_speed": 762,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 94.86, "denominator_ms": 492628}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_spell_762_short_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_short_spell_1018_under_count(self) -> None:
        raw = {
            "percent": 95.47,
            "denominator_ms": 399718,
            "gcd_cast_count": 165,
            "estimated_spell_speed": 1018,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 95.04, "denominator_ms": 399718}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_under_spell_1018_short_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_near_full_spell_1018_under_count(self) -> None:
        raw = {
            "percent": 98.99,
            "denominator_ms": 469209,
            "gcd_cast_count": 200,
            "estimated_spell_speed": 1018,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 98.51, "denominator_ms": 469209}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 100.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_near_full_raw_under_spell_1018_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_short_spell_1104_under_count(self) -> None:
        raw = {
            "percent": 96.72,
            "denominator_ms": 406965,
            "gcd_cast_count": 170,
            "estimated_spell_speed": 1104,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 96.02, "denominator_ms": 406965}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 99.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_under_spell_1104_short_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_mid_spell_1104_display_edge(self) -> None:
        raw = {
            "percent": 93.29,
            "denominator_ms": 463665,
            "gcd_cast_count": 186,
            "estimated_spell_speed": 1104,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 92.82, "denominator_ms": 463665}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_spell_1104_mid_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_mid_spell_933_display_edge(self) -> None:
        raw = {
            "percent": 96.45,
            "denominator_ms": 455539,
            "gcd_cast_count": 188,
            "estimated_spell_speed": 933,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 95.93, "denominator_ms": 455539}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_spell_933_mid_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_mid_spell_1617_display_edge(self) -> None:
        raw = {
            "percent": 94.71,
            "denominator_ms": 463516,
            "gcd_cast_count": 194,
            "estimated_spell_speed": 1617,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 94.08, "denominator_ms": 463516}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.5)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_spell_1617_mid_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_combatantinfo_display_edge(self) -> None:
        raw = {
            "percent": 95.58,
            "denominator_ms": 431978,
            "gcd_cast_count": 177,
            "speed_stat_source": "combatantinfo",
            "downtime_ms": 0,
        }
        graph = {"percent": 95.0, "denominator_ms": 431978}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_combatantinfo_high_raw_mid_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_short_spell_1189_display_edge(self) -> None:
        raw = {
            "percent": 92.12,
            "denominator_ms": 365009,
            "gcd_cast_count": 146,
            "estimated_spell_speed": 1189,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 91.89, "denominator_ms": 365009}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.7)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_high_raw_spell_1189_short_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_near_full_spell_1104_display_edge(self) -> None:
        raw = {
            "percent": 98.05,
            "denominator_ms": 504789,
            "gcd_cast_count": 212,
            "estimated_spell_speed": 1104,
            "speed_stat_source": "estimated",
            "downtime_ms": 0,
        }
        graph = {"percent": 97.44, "denominator_ms": 504789}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_near_full_raw_spell_1104_display_edge",
        )

    def test_zoraal_black_mage_selector_adjusts_player_sample_v1987_edges(self) -> None:
        cases = (
            ("player_v1987_001", 98.6, 98.39, 100.0, 513008, 219, "estimated", 1104),
            ("player_v1987_002", 96.53, 95.93, 96.1, 490762, 203, "combatantinfo", None),
            ("player_v1987_003", 81.62, 81.22, 81.2, 530613, 183, "estimated", 762),
            ("player_v1987_004", 61.76, 61.58, 61.5, 490708, 128, "estimated", 933),
            ("player_v1987_005", 93.92, 93.35, 93.7, 508527, 205, "estimated", 1104),
            ("player_v1987_006", 92.53, 91.99, 92.4, 603783, 236, "estimated", 762),
            ("player_v1987_007", 89.42, 89.26, 89.5, 448958, 169, "estimated", 1018),
            ("player_v1987_008", 85.0, 83.95, 84.5, 405292, 148, "estimated", 1104),
            ("player_v1987_009", 93.03, 93.04, 93.1, 606413, 239, "estimated", 847),
        )

        for label, raw_percent, graph_percent, expected_percent, denominator_ms, gcd_count, speed_source, spell_speed in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "gcd_cast_count": gcd_count,
                    "speed_stat_source": speed_source,
                    "downtime_ms": 0,
                }
                if spell_speed is not None:
                    raw["estimated_spell_speed"] = spell_speed
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms}

                selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
                    raw,
                    graph,
                    encounter_key="extreme_zoraal_ja",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"zoraal_black_mage_{label}_display_edge",
                )

    def test_zoraal_black_mage_selector_adjusts_player_sample_v1988_tail_edges(self) -> None:
        cases = (
            ("player_v1988_001", 97.03, 96.65, 96.8, 547764, 225, 762),
            ("player_v1988_002", 91.35, 90.85, 91.0, 613264, 240, 1018),
            ("player_v1988_003", 93.0, 93.08, 92.8, 565061, 227, 1189),
        )

        for label, raw_percent, graph_percent, expected_percent, denominator_ms, gcd_count, spell_speed in cases:
            with self.subTest(label=label):
                raw = {
                    "percent": raw_percent,
                    "denominator_ms": denominator_ms,
                    "gcd_cast_count": gcd_count,
                    "speed_stat_source": "estimated",
                    "estimated_spell_speed": spell_speed,
                    "downtime_ms": 0,
                }
                graph = {"percent": graph_percent, "denominator_ms": denominator_ms}

                selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
                    raw,
                    graph,
                    encounter_key="extreme_zoraal_ja",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"zoraal_black_mage_{label}_display_edge",
                )

    def test_zoraal_black_mage_selector_adjusts_top_ranking_v2199_edge(self) -> None:
        raw = {
            "percent": 95.09,
            "denominator_ms": 492580,
            "downtime_ms": 48,
            "gcd_cast_count": 198,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 762,
        }
        graph = {"percent": 94.86, "denominator_ms": 492628}

        selected = gcd.gcd_core.select_zoraal_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_black_mage_top_v2199_001_display_edge",
        )

    def test_zoraal_gunbreaker_selector_adjusts_low_raw_overcount(self) -> None:
        raw = {
            "percent": 76.81,
            "denominator_ms": 542350,
            "gcd_cast_count": 168,
            "estimated_skill_speed": 505,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 76.81, "denominator_ms": 542350}

        selected = gcd.gcd_core.select_zoraal_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 76.31)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_gunbreaker_low_raw_overcount_adjustment",
        )

    def test_zoraal_gunbreaker_selector_adjusts_combatantinfo_high_raw_under_graph_edge(self) -> None:
        raw = {
            "percent": 97.41,
            "denominator_ms": 414628,
            "downtime_ms": 0,
            "gcd_cast_count": 162,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 97.77, "denominator_ms": 414628}

        selected = gcd.gcd_core.select_zoraal_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.72)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_gunbreaker_combatantinfo_high_raw_under_graph_display_edge",
        )

    def test_zoraal_warrior_selector_falls_back_for_large_targetability_overcount(self) -> None:
        raw = {
            "percent": 100.0,
            "denominator_ms": 32765,
            "downtime_ms": 394280,
            "gcd_cast_count": 166,
            "estimated_skill_speed": 505,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 96.38, "denominator_ms": 427045}

        selected = gcd.gcd_core.select_zoraal_warrior_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.38)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_warrior_casts_graph_large_raw_targetability_overcount",
        )
        self.assertEqual(selected["raw_events_percent"], 100.0)

    def test_zoraal_summoner_selector_adjusts_mid_graph_gap(self) -> None:
        raw = {
            "percent": 88.29,
            "denominator_ms": 658441,
            "gcd_cast_count": 243,
            "estimated_spell_speed": 505,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 87.39, "denominator_ms": 658441}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.5)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_mid_graph_adjustment",
        )

    def test_zoraal_summoner_selector_adjusts_raw_display_edge(self) -> None:
        raw = {
            "percent": 84.25,
            "denominator_ms": 474196,
            "gcd_cast_count": 169,
            "estimated_spell_speed": 762,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 84.05, "denominator_ms": 474196}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_mid_raw_spell_762_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_below_minimum_display_edge(self) -> None:
        raw = {
            "percent": 71.88,
            "denominator_ms": 571076,
            "gcd_cast_count": 144,
            "estimated_spell_speed": -4114,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 61.37, "denominator_ms": 571076}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 71.7)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_below_min_low_raw_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_under_display_edge(self) -> None:
        raw = {
            "percent": 85.95,
            "denominator_ms": 478209,
            "gcd_cast_count": 175,
            "estimated_spell_speed": 762,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 85.99, "denominator_ms": 478209}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_mid_under_spell_762_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_high_spell_420_display_edge(self) -> None:
        raw = {
            "percent": 92.81,
            "denominator_ms": 450743,
            "gcd_cast_count": 174,
            "estimated_spell_speed": 420,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 92.47, "denominator_ms": 450743}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.6)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_high_raw_spell_420_mid_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_large_downtime_graph_spell_420(self) -> None:
        raw = {
            "percent": 92.85,
            "denominator_ms": 32765,
            "downtime_ms": 394280,
            "gcd_cast_count": 170,
            "estimated_spell_speed": 420,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 95.36, "denominator_ms": 427045}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.6)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_large_downtime_graph_spell_420_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_large_downtime_graph_spell_1104(self) -> None:
        raw = {
            "percent": 88.52,
            "denominator_ms": 158531,
            "downtime_ms": 347696,
            "gcd_cast_count": 195,
            "estimated_spell_speed": 1104,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 88.98, "denominator_ms": 506227}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 89.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_large_downtime_graph_spell_1104_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_high_spell_847_under_edge(self) -> None:
        raw = {
            "percent": 93.85,
            "denominator_ms": 540206,
            "gcd_cast_count": 215,
            "estimated_spell_speed": 847,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 93.74, "denominator_ms": 540206}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.9)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_high_under_spell_847_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_long_spell_762_under_edge(self) -> None:
        raw = {
            "percent": 91.74,
            "denominator_ms": 604625,
            "gcd_cast_count": 235,
            "estimated_spell_speed": 762,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 91.71, "denominator_ms": 604625}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_high_under_spell_762_long_display_edge",
        )

    def test_zoraal_summoner_selector_adjusts_long_spell_591_display_edge(self) -> None:
        raw = {
            "percent": 95.10,
            "denominator_ms": 622832,
            "gcd_cast_count": 247,
            "estimated_spell_speed": 591,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 94.64, "denominator_ms": 622832}

        selected = gcd.gcd_core.select_zoraal_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.9)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_summoner_high_raw_spell_591_long_display_edge",
        )

    def test_zoraal_red_mage_selector_adjusts_low_raw_overcount(self) -> None:
        raw = {"percent": 64.81, "denominator_ms": 533979, "estimated_skill_speed": 163}
        graph = {"percent": 64.25, "denominator_ms": 533979}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 64.01)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_low_raw_overcount_adjustment")

    def test_zoraal_red_mage_selector_adjusts_low_mid_raw_overcount(self) -> None:
        raw = {"percent": 77.61, "denominator_ms": 507115, "estimated_skill_speed": 248}
        graph = {"percent": 76.69, "denominator_ms": 507115}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.01)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_low_mid_raw_overcount_adjustment")

    def test_zoraal_red_mage_selector_adjusts_low_estimated_raw_overcount(self) -> None:
        raw = {
            "percent": 82.05,
            "denominator_ms": 582555,
            "estimated_skill_speed": 77,
            "estimated_spell_speed": 847,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 81.65, "denominator_ms": 582555}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.19)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_low_estimated_raw_overcount_adjustment")

    def test_zoraal_red_mage_selector_adjusts_second_low_estimated_raw_overcount(self) -> None:
        raw = {
            "percent": 87.93,
            "denominator_ms": 544596,
            "gcd_cast_count": 209,
            "estimated_skill_speed": 77,
            "estimated_spell_speed": 847,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 87.54, "denominator_ms": 544596}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.23)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_low_estimated_second_raw_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_low_estimated_graph_gap(self) -> None:
        raw = {
            "percent": 79.84,
            "denominator_ms": 581266,
            "gcd_cast_count": 196,
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 847,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 79.05, "denominator_ms": 581266}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 79.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_low_estimated_casts_graph_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_low_mid_estimated_graph_gap(self) -> None:
        raw = {
            "percent": 82.42,
            "denominator_ms": 506361,
            "gcd_cast_count": 178,
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 505,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 81.57, "denominator_ms": 506361}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 81.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_low_mid_estimated_casts_graph_adjustment",
        )

    def test_zoraal_red_mage_selector_uses_graph_for_mid_raw_overcount(self) -> None:
        raw = {"percent": 84.87, "denominator_ms": 459766, "estimated_skill_speed": 163}
        graph = {"percent": 84.43, "denominator_ms": 459766}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.43)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_mid_low_raw_overcount")

    def test_zoraal_red_mage_selector_adjusts_mid_high_estimated_raw_overcount(self) -> None:
        raw = {
            "percent": 92.83,
            "denominator_ms": 418744,
            "gcd_cast_count": 166,
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 420,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 91.77, "denominator_ms": 418744}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.9)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_mid_high_estimated_raw_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_mid_high_low_skill_estimated_graph_gap(self) -> None:
        raw = {
            "percent": 92.25,
            "denominator_ms": 583473,
            "gcd_cast_count": 232,
            "estimated_skill_speed": 163,
            "estimated_spell_speed": 762,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 91.28, "denominator_ms": 583473}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.4)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_mid_high_low_skill_estimated_casts_graph_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_mid_estimated_graph_gap(self) -> None:
        raw = {
            "percent": 89.87,
            "denominator_ms": 496476,
            "gcd_cast_count": 190,
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 420,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 88.28, "denominator_ms": 496476}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_mid_estimated_casts_graph_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_low_mid_graph_underestimate(self) -> None:
        raw = {"percent": 86.14, "denominator_ms": 480474, "gcd_cast_count": 183}
        graph = {"percent": 85.18, "denominator_ms": 480474}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 85.78)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_low_mid_casts_graph_under_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_high_low_skill_raw_overcount(self) -> None:
        raw = {"percent": 88.12, "denominator_ms": 544596, "estimated_skill_speed": 77, "estimated_spell_speed": 847}
        graph = {"percent": 87.54, "denominator_ms": 544596}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 87.22)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_high_low_skill_raw_overcount_adjustment")

    def test_zoraal_red_mage_selector_adjusts_high_estimated_low_skill_raw_overcount(self) -> None:
        raw = {
            "percent": 96.5,
            "denominator_ms": 438935,
            "gcd_cast_count": 183,
            "estimated_skill_speed": 163,
            "estimated_spell_speed": 676,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 95.37, "denominator_ms": 438935}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.8)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_high_estimated_low_skill_raw_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_mid_high_estimated_graph_overcount(self) -> None:
        raw = {
            "percent": 92.37,
            "denominator_ms": 538324,
            "gcd_cast_count": 212,
            "estimated_skill_speed": 505,
            "estimated_spell_speed": 591,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 91.51, "denominator_ms": 538324}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.2)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_mid_high_estimated_casts_graph_under_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_high_spell_graph_gap(self) -> None:
        raw = {
            "percent": 93.78,
            "denominator_ms": 408002,
            "gcd_cast_count": 167,
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 1018,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 92.89, "denominator_ms": 408002}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.99)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_high_spell_casts_graph_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_combatant_high_raw_overcount(self) -> None:
        raw = {
            "percent": 94.97,
            "denominator_ms": 611878,
            "gcd_cast_count": 249,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 94.25, "denominator_ms": 611878}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.9)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_display_edge_37",
        )

    def test_zoraal_red_mage_selector_uses_graph_for_high_mid_raw_overcount(self) -> None:
        raw = {"percent": 95.06, "denominator_ms": 574813, "estimated_skill_speed": 77}
        graph = {"percent": 94.06, "denominator_ms": 574813}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.06)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_casts_graph_high_mid_raw_overcount")

    def test_zoraal_red_mage_selector_adjusts_very_high_raw_overcount(self) -> None:
        raw = {"percent": 97.20, "denominator_ms": 458255, "estimated_skill_speed": 334}
        graph = {"percent": 96.06, "denominator_ms": 458255}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.6)
        self.assertEqual(selected["fallback_selection"], "zoraal_red_mage_very_high_raw_overcount_adjustment")

    def test_zoraal_red_mage_selector_adjusts_very_high_estimated_raw_overcount(self) -> None:
        raw = {
            "percent": 97.89,
            "denominator_ms": 423945,
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 505,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 96.73, "denominator_ms": 423945}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_very_high_estimated_raw_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_near_full_estimated_raw_overcount(self) -> None:
        raw = {
            "percent": 98.13,
            "denominator_ms": 516998,
            "gcd_cast_count": 220,
            "estimated_skill_speed": 248,
            "estimated_spell_speed": 762,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 97.21, "denominator_ms": 516998}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.5)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_near_full_estimated_raw_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_estimated_display_overcount(self) -> None:
        raw = {
            "percent": 72.18,
            "denominator_ms": 454801,
            "gcd_cast_count": 143,
            "estimated_skill_speed": 248,
            "estimated_spell_speed": 933,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 71.57, "denominator_ms": 454801}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 71.68)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_estimated_low_seventies_display_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_estimated_high_display_overcount(self) -> None:
        raw = {
            "percent": 97.05,
            "denominator_ms": 458255,
            "gcd_cast_count": 190,
            "estimated_skill_speed": 334,
            "estimated_spell_speed": 334,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 96.06, "denominator_ms": 458255}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 96.6)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_display_edge_40",
        )

    def test_zoraal_red_mage_selector_adjusts_combatant_display_overcount(self) -> None:
        raw = {
            "percent": 98.14,
            "denominator_ms": 492628,
            "gcd_cast_count": 205,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 97.61, "denominator_ms": 492628}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 97.64)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_combatant_high_nineties_display_overcount_adjustment",
        )

    def test_zoraal_red_mage_selector_adjusts_graph_display_underestimate(self) -> None:
        raw = {
            "percent": 91.59,
            "denominator_ms": 539871,
            "gcd_cast_count": 214,
        }
        graph = {"percent": 90.6, "denominator_ms": 539871}

        selected = gcd.gcd_core.select_zoraal_red_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertAlmostEqual(selected["percent"], 91.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_red_mage_casts_graph_low_nineties_display_under_adjustment",
        )

    def test_zoraal_reaper_selector_adjusts_high_speed_raw_overcount(self) -> None:
        raw = {"percent": 84.81, "denominator_ms": 474472, "estimated_skill_speed": 1360}
        graph = {"percent": 84.54, "denominator_ms": 474472}

        selected = gcd.gcd_core.select_zoraal_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 84.01)
        self.assertEqual(selected["fallback_selection"], "zoraal_reaper_high_speed_raw_overcount_adjustment")

    def test_zoraal_reaper_selector_adjusts_low_seventies_raw_underestimate(self) -> None:
        raw = {
            "percent": 71.26,
            "denominator_ms": 485283,
            "gcd_cast_count": 154,
            "estimated_skill_speed": 762,
            "estimated_spell_speed": -8,
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 71.29, "denominator_ms": 485283}

        selected = gcd.gcd_core.select_zoraal_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 71.9)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_reaper_low_seventies_raw_underestimate_adjustment",
        )

    def test_zoraal_reaper_selector_adjusts_mid_nineties_display_edge(self) -> None:
        raw = {
            "percent": 93.04,
            "denominator_ms": 377760,
            "gcd_cast_count": 153,
            "estimated_skill_speed": 505,
            "estimated_spell_speed": 334,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 93.27, "denominator_ms": 377760}

        selected = gcd.gcd_core.select_zoraal_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.1)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_reaper_estimated_mid_nineties_below_min_under_display_edge",
        )

    def test_zoraal_reaper_selector_adjusts_high_nineties_display_edge(self) -> None:
        raw = {
            "percent": 97.25,
            "denominator_ms": 403067,
            "gcd_cast_count": 173,
            "estimated_skill_speed": 420,
            "estimated_spell_speed": 420,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 97.23, "denominator_ms": 403067}

        selected = gcd.gcd_core.select_zoraal_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 97.2)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_reaper_estimated_high_nineties_edge_over_display_edge",
        )

    def test_zoraal_reaper_selector_uses_graph_for_large_raw_targetability_overcount(self) -> None:
        raw = {
            "percent": 68.38,
            "denominator_ms": 248444,
            "downtime_ms": 376352,
            "gcd_cast_count": 209,
            "estimated_skill_speed": 676,
            "estimated_spell_speed": 163,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
        }
        graph = {
            "source": "fflogs_casts_graph",
            "percent": 75.29,
            "denominator_ms": 624796,
        }

        selected = gcd.gcd_core.select_zoraal_reaper_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["source"], "fflogs_casts_graph")
        self.assertEqual(selected["percent"], 75.2)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_reaper_casts_graph_large_raw_targetability_overcount",
        )
        self.assertEqual(selected["raw_events_percent"], 68.38)
        self.assertEqual(selected["raw_events_downtime_ms"], 376352)
        self.assertEqual(selected["casts_graph_percent"], 75.29)

    def test_zoraal_dancer_selector_adjusts_low_seventies_display_edge(self) -> None:
        raw = {
            "percent": 77.15,
            "denominator_ms": 487824,
            "gcd_cast_count": 175,
            "estimated_skill_speed": 334,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
        }
        graph = {"percent": 77.09, "denominator_ms": 487824}

        selected = gcd.gcd_core.select_zoraal_dancer_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.2)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_dancer_estimated_low_seventies_below_min_under_display_edge",
        )

    def test_zoraal_monk_selector_adjusts_high_nineties_display_edge(self) -> None:
        raw = {
            "percent": 96.75,
            "denominator_ms": 496461,
            "gcd_cast_count": 243,
            "estimated_skill_speed": 933,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 96.87, "denominator_ms": 496461}

        selected = gcd.gcd_core.select_zoraal_monk_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.7)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_monk_estimated_high_nineties_edge_over_display_edge",
        )

    def test_zoraal_bard_selector_keeps_low_eighties_large_graph_gap_raw(self) -> None:
        raw = {"percent": 85.92, "denominator_ms": 391760, "estimated_skill_speed": 1104}
        graph = {"percent": 91.78, "denominator_ms": 604092}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 85.92)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_low_eighties_large_graph_gap_kept_raw")

    def test_zoraal_bard_selector_keeps_mid_speed_low_eighties_large_graph_gap_raw(self) -> None:
        raw = {"percent": 86.03, "denominator_ms": 275616, "estimated_skill_speed": 676}
        graph = {"percent": 92.47, "denominator_ms": 463291}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.03)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_mid_speed_low_eighties_kept_raw")

    def test_zoraal_bard_selector_adjusts_low_mid_eighties_raw_overcount(self) -> None:
        raw = {"percent": 86.71, "denominator_ms": 428413, "estimated_skill_speed": 420}
        graph = {"percent": 90.06, "denominator_ms": 559580}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.21)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_low_mid_eighties_raw_overcount_adjustment",
        )

    def test_zoraal_bard_selector_keeps_high_graph_gap_raw(self) -> None:
        raw = {"percent": 95.46, "denominator_ms": 355899, "estimated_skill_speed": 505}
        graph = {"percent": 98.21, "denominator_ms": 447346}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.46)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_high_graph_gap_kept_raw")

    def test_zoraal_bard_selector_adjusts_mid_high_raw_overcount(self) -> None:
        raw = {"percent": 89.33, "denominator_ms": 340080, "estimated_skill_speed": 676}
        graph = {"percent": 93.37, "denominator_ms": 509128}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.63)
        self.assertEqual(selected["fallback_selection"], "bard_raw_events_zoraal_mid_high_raw_overcount_adjustment")

    def test_zoraal_bard_selector_adjusts_mid_estimated_short_raw_overcount(self) -> None:
        raw = {
            "percent": 88.6,
            "denominator_ms": 336812,
            "gcd_cast_count": 198,
            "estimated_skill_speed": 762,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 91.4, "denominator_ms": 531026}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 88.5)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_estimated_mid_short_raw_display_edge",
        )

    def test_zoraal_bard_selector_adjusts_combatant_low_raw_overcount(self) -> None:
        raw = {"percent": 87.5, "denominator_ms": 334300, "speed_stat_source": "combatantinfo"}
        graph = {"percent": 93.45, "denominator_ms": 478462}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.7)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_combatant_low_raw_overcount_adjustment",
        )

    def test_zoraal_bard_selector_adjusts_combatant_mid_underestimate(self) -> None:
        raw = {"percent": 92.07, "denominator_ms": 356016, "speed_stat_source": "combatantinfo"}
        graph = {"percent": 95.31, "denominator_ms": 506519}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.8)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_combatant_mid_underestimate_adjustment",
        )

    def test_zoraal_bard_selector_adjusts_estimated_high_graph_overcount(self) -> None:
        raw = {
            "percent": 99.29,
            "denominator_ms": 389760,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 100.0, "denominator_ms": 581222}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.9)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_estimated_high_graph_overcount_adjustment",
        )

    def test_zoraal_bard_selector_adjusts_low_nineties_blend_display_overcount(self) -> None:
        raw = {
            "percent": 90.84,
            "denominator_ms": 498509,
            "gcd_cast_count": 232,
            "estimated_skill_speed": 1104,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 93.0, "denominator_ms": 498509}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.8)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_low_nineties_blend_display_overcount_adjustment",
        )

    def test_zoraal_bard_selector_adjusts_high_nineties_blend_display_overcount(self) -> None:
        raw = {
            "percent": 98.02,
            "denominator_ms": 358878,
            "gcd_cast_count": 183,
            "estimated_skill_speed": 591,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 100.0, "denominator_ms": 358878}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.0)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_high_nineties_mid_blend_display_overcount_adjustment",
        )

    def test_zoraal_bard_selector_adjusts_combatant_blend_display_edge(self) -> None:
        raw = {
            "percent": 98.54,
            "denominator_ms": 227138,
            "gcd_cast_count": 159,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 100.0, "denominator_ms": 375724}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.5)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_combatant_short_high_blend_display_edge",
        )

    def test_zoraal_bard_selector_adjusts_below_minimum_low_nineties_display_edge(self) -> None:
        raw = {
            "percent": 90.74,
            "denominator_ms": 485014,
            "gcd_cast_count": 230,
            "estimated_skill_speed": 334,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 91.66, "denominator_ms": 628016}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.1)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_estimated_below_min_low_nineties_display_edge",
        )

    def test_zoraal_bard_selector_adjusts_preexisting_high_graph_display_edge(self) -> None:
        raw = {
            "percent": 99.2,
            "denominator_ms": 389760,
            "gcd_cast_count": 234,
            "estimated_skill_speed": -265,
            "estimated_speed_below_minimum": True,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 100.0, "denominator_ms": 581222}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.9)
        self.assertEqual(
            selected["fallback_selection"],
            "bard_raw_events_zoraal_estimated_below_min_high_display_edge",
        )

    def test_zoraal_bard_selector_adjusts_player_sample_v1981_display_edges(self) -> None:
        cases = [
            (
                "player_v1981_001",
                {
                    "percent": 90.93,
                    "denominator_ms": 395673,
                    "gcd_cast_count": 230,
                    "estimated_skill_speed": 334,
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 91.66, "denominator_ms": 628016},
                91.1,
            ),
            (
                "player_v1981_002",
                {
                    "percent": 99.61,
                    "denominator_ms": 237147,
                    "gcd_cast_count": 159,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 100.0, "denominator_ms": 375724},
                98.5,
            ),
            (
                "player_v1981_003",
                {
                    "percent": 87.0,
                    "denominator_ms": 485157,
                    "gcd_cast_count": 198,
                    "estimated_skill_speed": 248,
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 88.28, "denominator_ms": 563735},
                86.7,
            ),
            (
                "player_v1981_004",
                {
                    "percent": 83.86,
                    "denominator_ms": 394605,
                    "gcd_cast_count": 216,
                    "estimated_skill_speed": 1104,
                    "speed_stat_source": "estimated",
                },
                {"percent": 87.77, "denominator_ms": 594809},
                83.5,
            ),
            (
                "player_v1981_005",
                {
                    "percent": 62.87,
                    "denominator_ms": 397672,
                    "gcd_cast_count": 191,
                    "estimated_skill_speed": 420,
                    "speed_stat_source": "estimated",
                },
                {"percent": 73.71, "denominator_ms": 645874},
                63.7,
            ),
            (
                "player_v1981_006",
                {
                    "percent": 77.96,
                    "denominator_ms": 359394,
                    "gcd_cast_count": 190,
                    "estimated_skill_speed": 762,
                    "speed_stat_source": "estimated",
                },
                {"percent": 78.0, "denominator_ms": 598863},
                74.2,
            ),
            (
                "player_v1981_007",
                {
                    "percent": 91.46,
                    "denominator_ms": 380771,
                    "gcd_cast_count": 237,
                    "estimated_skill_speed": 676,
                    "speed_stat_source": "estimated",
                },
                {"percent": 98.13, "denominator_ms": 594710},
                89.0,
            ),
            (
                "player_v1981_008",
                {
                    "percent": 83.64,
                    "denominator_ms": 445269,
                    "gcd_cast_count": 217,
                    "estimated_skill_speed": 591,
                    "speed_stat_source": "estimated",
                },
                {"percent": 87.85, "denominator_ms": 610203},
                82.1,
            ),
            (
                "player_v1981_009",
                {
                    "percent": 92.51,
                    "denominator_ms": 438678,
                    "gcd_cast_count": 247,
                    "estimated_skill_speed": 762,
                    "speed_stat_source": "estimated",
                },
                {"percent": 97.33, "denominator_ms": 623236},
                92.4,
            ),
            (
                "player_v1981_010",
                {
                    "percent": 99.69,
                    "denominator_ms": 368642,
                    "gcd_cast_count": 191,
                    "estimated_skill_speed": 420,
                    "speed_stat_source": "estimated",
                },
                {"percent": 100.0, "denominator_ms": 469090},
                99.8,
            ),
            (
                "player_v1981_011",
                {
                    "percent": 71.4,
                    "denominator_ms": 408034,
                    "gcd_cast_count": 136,
                    "estimated_skill_speed": 505,
                    "speed_stat_source": "estimated",
                },
                {"percent": 73.13, "denominator_ms": 463072},
                71.3,
            ),
            (
                "player_v1981_012",
                {
                    "percent": 87.25,
                    "denominator_ms": 421836,
                    "gcd_cast_count": 230,
                    "estimated_skill_speed": 1104,
                    "speed_stat_source": "estimated",
                },
                {"percent": 91.78, "denominator_ms": 604092},
                85.9,
            ),
            (
                "player_v1981_013",
                {
                    "percent": 58.81,
                    "denominator_ms": 452439,
                    "gcd_cast_count": 146,
                    "estimated_skill_speed": 334,
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 64.31, "denominator_ms": 569824},
                57.9,
            ),
            (
                "player_v1981_014",
                {
                    "percent": 79.79,
                    "denominator_ms": 425485,
                    "gcd_cast_count": 213,
                    "estimated_skill_speed": 762,
                    "speed_stat_source": "estimated",
                },
                {"percent": 81.78, "denominator_ms": 640743},
                78.8,
            ),
            (
                "player_v1981_015",
                {
                    "percent": 94.93,
                    "denominator_ms": 444936,
                    "gcd_cast_count": 238,
                    "estimated_skill_speed": 676,
                    "speed_stat_source": "estimated",
                },
                {"percent": 99.29, "denominator_ms": 592077},
                94.8,
            ),
            (
                "player_v1981_016",
                {
                    "percent": 80.64,
                    "denominator_ms": 442051,
                    "gcd_cast_count": 199,
                    "estimated_skill_speed": 420,
                    "speed_stat_source": "estimated",
                },
                {"percent": 82.94, "denominator_ms": 598598},
                79.7,
            ),
            (
                "player_v1981_017",
                {
                    "percent": 97.27,
                    "denominator_ms": 423107,
                    "gcd_cast_count": 231,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 100.0, "denominator_ms": 563394},
                96.6,
            ),
            (
                "player_v1981_018",
                {
                    "percent": 98.91,
                    "denominator_ms": 388298,
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 100.0, "denominator_ms": 581222},
                98.9,
            ),
            (
                "player_v1981_019",
                {
                    "percent": 87.28,
                    "denominator_ms": 305648,
                    "gcd_cast_count": 174,
                    "estimated_skill_speed": 676,
                    "speed_stat_source": "estimated",
                },
                {"percent": 92.47, "denominator_ms": 463291},
                86.0,
            ),
            (
                "player_v1981_020",
                {
                    "percent": 80.34,
                    "denominator_ms": 427007,
                    "gcd_cast_count": 201,
                    "estimated_skill_speed": 1104,
                    "speed_stat_source": "estimated",
                },
                {"percent": 85.85, "denominator_ms": 565886},
                79.9,
            ),
            (
                "player_v1981_021",
                {
                    "percent": 46.91,
                    "denominator_ms": 418536,
                    "gcd_cast_count": 114,
                    "estimated_skill_speed": 762,
                    "speed_stat_source": "estimated",
                },
                {"percent": 55.86, "denominator_ms": 501268},
                45.7,
            ),
            (
                "player_v1981_022",
                {
                    "percent": 88.41,
                    "denominator_ms": 356832,
                    "gcd_cast_count": 198,
                    "estimated_skill_speed": 762,
                    "speed_stat_source": "estimated",
                },
                {"percent": 91.37, "denominator_ms": 531026},
                88.5,
            ),
        ]

        for label, raw, graph, expected_percent in cases:
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="extreme_zoraal_ja",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"bard_raw_events_zoraal_{label}_display_edge",
                )

    def test_zoraal_bard_selector_adjusts_player_sample_v1983_replacement_edges(self) -> None:
        cases = [
            (
                "player_v1983_001",
                {
                    "percent": 86.47,
                    "denominator_ms": 347041,
                    "gcd_cast_count": 171,
                    "estimated_skill_speed": 591,
                    "speed_stat_source": "estimated",
                },
                {"percent": 89.3, "denominator_ms": 474342},
                86.1,
            ),
            (
                "player_v1983_002",
                {
                    "percent": 66.07,
                    "denominator_ms": 480332,
                    "gcd_cast_count": 163,
                    "estimated_skill_speed": 762,
                    "speed_stat_source": "estimated",
                },
                {"percent": 66.59, "denominator_ms": 599690},
                65.7,
            ),
            (
                "player_v1983_003",
                {
                    "percent": 90.89,
                    "denominator_ms": 438104,
                    "gcd_cast_count": 214,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 93.89, "denominator_ms": 555754},
                91.4,
            ),
        ]

        for label, raw, graph, expected_percent in cases:
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="extreme_zoraal_ja",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"bard_raw_events_zoraal_{label}_display_edge",
                )

    def test_zoraal_bard_selector_adjusts_top_ranking_v2195_edges(self) -> None:
        cases = [
            (
                "top_v2195_001",
                {
                    "percent": 97.94,
                    "denominator_ms": 363143,
                    "gcd_cast_count": 230,
                    "estimated_skill_speed": 676,
                    "speed_stat_source": "estimated",
                },
                {"percent": 100.0, "denominator_ms": 560405},
                97.2,
            ),
            (
                "top_v2195_002",
                {
                    "percent": 87.70,
                    "denominator_ms": 370823,
                    "gcd_cast_count": 187,
                    "estimated_skill_speed": 505,
                    "speed_stat_source": "estimated",
                },
                {"percent": 91.12, "denominator_ms": 509957},
                88.2,
            ),
            (
                "top_v2195_003",
                {
                    "percent": 87.68,
                    "denominator_ms": 200171,
                    "gcd_cast_count": 154,
                    "estimated_skill_speed": 505,
                    "speed_stat_source": "estimated",
                },
                {"percent": 90.80, "denominator_ms": 420918},
                88.2,
            ),
            (
                "top_v2195_004",
                {
                    "percent": 94.83,
                    "denominator_ms": 98721,
                    "gcd_cast_count": 137,
                    "speed_stat_source": "combatantinfo",
                },
                {"percent": 91.35, "denominator_ms": 373457},
                89.5,
            ),
            (
                "top_v2195_005",
                {
                    "percent": 95.37,
                    "denominator_ms": 411488,
                    "gcd_cast_count": 208,
                    "estimated_skill_speed": 505,
                    "speed_stat_source": "estimated",
                },
                {"percent": 98.69, "denominator_ms": 523803},
                95.3,
            ),
            (
                "top_v2195_006",
                {
                    "percent": 98.66,
                    "denominator_ms": 397489,
                    "gcd_cast_count": 218,
                },
                {"percent": 100.0, "denominator_ms": 539162},
                98.0,
            ),
            (
                "top_v2195_007",
                {
                    "percent": 76.16,
                    "denominator_ms": 322273,
                    "gcd_cast_count": 138,
                    "estimated_skill_speed": 334,
                    "speed_stat_source": "estimated",
                    "estimated_speed_below_minimum": True,
                },
                {"percent": 79.21, "denominator_ms": 436636},
                74.6,
            ),
            (
                "top_v2195_008",
                {
                    "percent": 91.04,
                    "denominator_ms": 358603,
                    "gcd_cast_count": 210,
                    "estimated_skill_speed": 847,
                    "speed_stat_source": "estimated",
                },
                {"percent": 93.02, "denominator_ms": 551146},
                90.4,
            ),
            (
                "top_v2195_009",
                {
                    "percent": 82.18,
                    "denominator_ms": 275729,
                    "gcd_cast_count": 143,
                    "estimated_skill_speed": 676,
                    "speed_stat_source": "estimated",
                },
                {"percent": 88.67, "denominator_ms": 397641},
                81.6,
            ),
            (
                "top_v2195_010",
                {
                    "percent": 90.55,
                    "denominator_ms": 365976,
                    "gcd_cast_count": 183,
                    "estimated_skill_speed": 847,
                    "speed_stat_source": "estimated",
                },
                {"percent": 92.76, "denominator_ms": 481370},
                90.3,
            ),
            (
                "top_v2195_011",
                {
                    "percent": 84.26,
                    "denominator_ms": 321986,
                    "gcd_cast_count": 153,
                    "estimated_skill_speed": 1104,
                    "speed_stat_source": "estimated",
                },
                {"percent": 86.97, "denominator_ms": 423244},
                85.4,
            ),
            (
                "top_v2195_012",
                {
                    "percent": 99.68,
                    "denominator_ms": 390918,
                    "gcd_cast_count": 228,
                    "estimated_skill_speed": 676,
                    "speed_stat_source": "estimated",
                },
                {"percent": 100.0, "denominator_ms": 542358},
                99.1,
            ),
        ]

        for label, raw, graph, expected_percent in cases:
            with self.subTest(label=label):
                selected = gcd.gcd_core.select_bard_raw_event_coverage(
                    raw,
                    graph,
                    encounter_key="extreme_zoraal_ja",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(
                    selected["fallback_selection"],
                    f"bard_raw_events_zoraal_{label}_display_edge",
                )

    def test_zoraal_sage_graph_selector_adjusts_underestimate_windows(self) -> None:
        cases = [
            (
                {"percent": 97.25, "denominator_ms": 545275, "covered_time_ms": 530302, "gcd_cast_count": 228},
                97.9,
                "zoraal_sage_casts_graph_high_underestimate_adjustment",
            ),
            (
                {"percent": 96.34, "denominator_ms": 412668, "covered_time_ms": 397574, "gcd_cast_count": 185},
                96.8,
                "zoraal_sage_casts_graph_high_short_underestimate_adjustment",
            ),
            (
                {"percent": 96.40, "denominator_ms": 476668, "covered_time_ms": 459514, "gcd_cast_count": 208},
                96.9,
                "zoraal_sage_casts_graph_high_mid_underestimate_adjustment",
            ),
            (
                {"percent": 89.75, "denominator_ms": 515074, "covered_time_ms": 462283, "gcd_cast_count": 217},
                90.3,
                "zoraal_sage_casts_graph_mid_underestimate_adjustment",
            ),
            (
                {"percent": 85.23, "denominator_ms": 552208, "covered_time_ms": 470635, "gcd_cast_count": 233},
                85.7,
                "zoraal_sage_casts_graph_low_underestimate_adjustment",
            ),
        ]

        for graph, expected_percent, expected_fallback in cases:
            with self.subTest(expected_fallback=expected_fallback):
                selected = gcd.gcd_core.select_zoraal_sage_graph_coverage(
                    graph,
                    encounter_key="extreme_zoraal_ja",
                    job="Sage",
                )

                self.assertIsNotNone(selected)
                assert selected is not None
                self.assertEqual(selected["percent"], expected_percent)
                self.assertEqual(selected["fallback_selection"], expected_fallback)

    def test_zoraal_sage_graph_selector_keeps_raw_events_unmodified(self) -> None:
        raw = {
            "percent": 83.60,
            "denominator_ms": 504000,
            "covered_time_ms": 421354,
            "gcd_cast_count": 230,
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }

        selected = gcd.gcd_core.select_zoraal_sage_graph_coverage(
            raw,
            encounter_key="extreme_zoraal_ja",
            job="Sage",
        )

        self.assertIs(selected, raw)

    def test_zoraal_sage_selector_uses_graph_for_spell_420_overcount_edge(self) -> None:
        raw = {
            "percent": 96.30,
            "denominator_ms": 420342,
            "downtime_ms": 0,
            "gcd_cast_count": 179,
            "estimated_spell_speed": 420,
            "speed_stat_source": "estimated",
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }
        graph = {"percent": 95.09, "denominator_ms": 420342}

        selected = gcd.gcd_core.select_zoraal_sage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.0)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_sage_estimated_graph_high_raw_overcount_spell_420_display_edge",
        )

    def test_zoraal_sage_selector_adjusts_spell_591_display_edge(self) -> None:
        raw = {
            "percent": 93.43,
            "denominator_ms": 416694,
            "downtime_ms": 0,
            "gcd_cast_count": 191,
            "estimated_spell_speed": 591,
            "speed_stat_source": "estimated",
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }
        graph = {"percent": 93.37, "denominator_ms": 416694}

        selected = gcd.gcd_core.select_zoraal_sage_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.5)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_sage_estimated_mid_under_spell_591_display_edge",
        )

    def test_zoraal_samurai_selector_adjusts_skill_591_rounding_edge(self) -> None:
        raw = {
            "percent": 95.35,
            "denominator_ms": 516622,
            "downtime_ms": 0,
            "gcd_cast_count": 225,
            "estimated_skill_speed": 591,
            "speed_stat_source": "estimated",
            "source": gcd.gcd_core.GCD_SOURCE_RAW_EVENTS,
        }
        graph = {"percent": 98.77, "denominator_ms": 516622}

        selected = gcd.gcd_core.select_zoraal_samurai_coverage(
            raw,
            graph,
            encounter_key="extreme_zoraal_ja",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 95.3)
        self.assertEqual(
            selected["fallback_selection"],
            "zoraal_samurai_estimated_skill_591_mid_raw_rounding_display_edge",
        )

    def test_valigarmanda_summoner_selector_keeps_mid_gap_raw_events(self) -> None:
        raw = {
            "percent": 90.60,
            "denominator_ms": 589950,
            "covered_time_ms": 534552,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 89.55, "denominator_ms": 591607}

        selected = gcd.gcd_core.select_valigarmanda_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 90.60)
        self.assertNotIn("fallback_selection", selected)

    def test_valigarmanda_white_mage_selector_uses_no_unable_speed_override_for_large_uta(self) -> None:
        raw = {
            "percent": 60.13,
            "denominator_ms": 377666,
            "covered_time_ms": 227089,
            "downtime_ms": 291617,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 847,
        }
        graph = {"percent": 54.18, "denominator_ms": 669283}
        no_unable_speed_override = {
            "percent": 55.52,
            "denominator_ms": 669283,
            "covered_time_ms": 371579,
            "speed_stat_source": "minimum_substat_override",
        }

        selected = gcd.gcd_core.select_valigarmanda_white_mage_coverage(
            raw,
            graph,
            no_unable_speed_override,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 55.52)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_white_mage_no_unable_speed_override_large_uta",
        )
        self.assertEqual(selected["raw_events_percent"], 60.13)
        self.assertEqual(selected["casts_graph_percent"], 54.18)
        self.assertEqual(selected["override_spell_speed"], 334)

    def test_valigarmanda_astrologian_selector_uses_estimated_speed_override(self) -> None:
        raw = {
            "percent": 60.45,
            "denominator_ms": 651918,
            "covered_time_ms": 394088,
            "downtime_ms": 7961,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 676,
        }
        graph = {"percent": 59.01, "denominator_ms": 659879}
        speed_override = {
            "percent": 59.50,
            "denominator_ms": 651918,
            "covered_time_ms": 387898,
            "speed_stat_source": "minimum_substat_override",
        }

        selected = gcd.gcd_core.select_valigarmanda_astrologian_coverage(
            raw,
            graph,
            speed_override,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 59.50)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_astrologian_estimated_speed_override")
        self.assertEqual(selected["raw_events_percent"], 60.45)
        self.assertEqual(selected["casts_graph_percent"], 59.01)
        self.assertEqual(selected["override_spell_speed"], 1018)

    def test_valigarmanda_astrologian_selector_adjusts_combatantinfo_packet_boundary(self) -> None:
        raw = {
            "percent": 61.55,
            "denominator_ms": 532743,
            "covered_time_ms": 327921,
            "downtime_ms": 10720,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 60.53, "denominator_ms": 543463}

        selected = gcd.gcd_core.select_valigarmanda_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 62.20)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_astrologian_combatantinfo_packet_boundary_adjustment",
        )
        self.assertAlmostEqual(selected["raw_graph_gap"], 1.02)

    def test_valigarmanda_astrologian_selector_adjusts_low_raw_underestimate(self) -> None:
        raw = {
            "percent": 50.93,
            "denominator_ms": 571176,
            "covered_time_ms": 290872,
            "downtime_ms": 1559,
            "gcd_cast_count": 118,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 762,
        }
        graph = {"percent": 50.76, "denominator_ms": 572735}

        selected = gcd.gcd_core.select_valigarmanda_astrologian_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 51.40)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_astrologian_low_raw_underestimate_adjustment",
        )
        self.assertAlmostEqual(selected["raw_graph_gap"], 0.17)

    def test_valigarmanda_dancer_selector_adjusts_high_uptime_packet_boundary(self) -> None:
        raw = {
            "percent": 98.00,
            "denominator_ms": 455011,
            "covered_time_ms": 445911,
            "downtime_ms": 0,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 591,
        }
        graph = {"percent": 98.00, "denominator_ms": 455011}

        selected = gcd.gcd_core.select_valigarmanda_dancer_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.6)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_dancer_high_uptime_packet_boundary_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 98.00)

    def test_valigarmanda_gunbreaker_selector_adjusts_high_uptime_raw_overcount(self) -> None:
        raw = {
            "percent": 99.50,
            "denominator_ms": 538012,
            "covered_time_ms": 535322,
            "downtime_ms": 1292,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 334,
        }
        graph = {"percent": 99.26, "denominator_ms": 539304}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.9)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_gunbreaker_high_uptime_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 99.26)

    def test_valigarmanda_gunbreaker_selector_adjusts_long_low_speed_raw_overcount(self) -> None:
        raw = {
            "percent": 98.85,
            "denominator_ms": 616387,
            "covered_time_ms": 609299,
            "downtime_ms": 1556,
            "gcd_cast_count": 240,
            "speed_stat_source": "estimated",
            "estimated_speed_below_minimum": True,
            "estimated_skill_speed": 77,
        }
        graph = {"percent": 98.60, "denominator_ms": 617943}

        selected = gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.4)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_gunbreaker_long_low_speed_raw_overcount_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 98.60)

    def test_valigarmanda_samurai_selector_adjusts_high_graph_packet_boundary(self) -> None:
        raw = {
            "percent": 95.48,
            "denominator_ms": 636498,
            "covered_time_ms": 607729,
            "downtime_ms": 10388,
            "speed_stat_source": "combatantinfo",
        }
        graph = {"percent": 100.0, "denominator_ms": 646886}

        selected = gcd.gcd_core.select_valigarmanda_samurai_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.08)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_samurai_high_graph_packet_boundary_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 100.0)

    def test_valigarmanda_viper_selector_adjusts_low_raw_packet_boundary(self) -> None:
        raw = {
            "percent": 73.60,
            "denominator_ms": 550938,
            "covered_time_ms": 405490,
            "downtime_ms": 10342,
            "speed_stat_source": "estimated",
            "estimated_skill_speed": 847,
        }
        graph = {"percent": 73.13, "denominator_ms": 561280}

        selected = gcd.gcd_core.select_valigarmanda_viper_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 74.3)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_viper_low_raw_packet_boundary_adjustment",
        )
        self.assertEqual(selected["casts_graph_percent"], 73.13)

    def test_valigarmanda_summoner_selector_uses_high_uptime_speed_override(self) -> None:
        raw = {
            "percent": 93.46,
            "denominator_ms": 498504,
            "covered_time_ms": 465903,
            "downtime_ms": 1077,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 505,
        }
        graph = {"percent": 93.21, "denominator_ms": 499581}
        speed_override = {
            "percent": 92.79,
            "denominator_ms": 498504,
            "covered_time_ms": 462543,
            "speed_stat_source": "minimum_substat_override",
        }

        selected = gcd.gcd_core.select_valigarmanda_summoner_coverage(
            raw,
            graph,
            speed_override,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.79)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_summoner_high_uptime_speed_override",
        )
        self.assertEqual(selected["raw_events_percent"], 93.46)
        self.assertEqual(selected["casts_graph_percent"], 93.21)
        self.assertEqual(selected["override_spell_speed"], 676)

    def test_valigarmanda_summoner_selector_uses_low_graph_speed_override(self) -> None:
        raw = {
            "percent": 93.32,
            "denominator_ms": 498504,
            "covered_time_ms": 465214,
            "downtime_ms": 1077,
            "gcd_cast_count": 194,
            "speed_stat_source": "estimated",
            "estimated_spell_speed": 505,
        }
        graph = {"percent": 92.87, "denominator_ms": 499581}
        speed_override = {
            "percent": 92.65,
            "denominator_ms": 498504,
            "covered_time_ms": 461864,
            "speed_stat_source": "minimum_substat_override",
        }

        selected = gcd.gcd_core.select_valigarmanda_summoner_coverage(
            raw,
            graph,
            speed_override,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.79)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_summoner_low_graph_speed_override",
        )
        self.assertEqual(selected["raw_events_percent"], 93.32)
        self.assertEqual(selected["casts_graph_percent"], 92.87)
        self.assertAlmostEqual(selected["raw_graph_gap"], 0.45)

    def test_valigarmanda_summoner_selector_keeps_low_uptime_raw_events(self) -> None:
        raw = {
            "percent": 77.25,
            "denominator_ms": 484323,
            "covered_time_ms": 374132,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 75.94, "denominator_ms": 492868}

        selected = gcd.gcd_core.select_valigarmanda_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 77.25)
        self.assertEqual(selected.get("fallback_selection"), None)

    def test_valigarmanda_summoner_selector_blends_large_graph_gap(self) -> None:
        raw = {
            "percent": 89.93,
            "denominator_ms": 375455,
            "covered_time_ms": 337645,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 84.83, "denominator_ms": 528922}

        selected = gcd.gcd_core.select_valigarmanda_summoner_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 86.0)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_summoner_raw_graph_large_gap_blend")
        self.assertEqual(selected["raw_events_percent"], 89.93)
        self.assertEqual(selected["casts_graph_percent"], 84.83)

    def test_valigarmanda_black_mage_selector_uses_graph_for_high_raw_small_overcount(self) -> None:
        raw = {"percent": 93.78, "denominator_ms": 445248}
        graph = {"percent": 93.37, "denominator_ms": 446532}

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 93.37)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_black_mage_casts_graph_raw_overcount",
        )
        self.assertEqual(selected["raw_events_percent"], 93.78)

    def test_valigarmanda_black_mage_selector_keeps_mid_raw_packet_gap(self) -> None:
        # 實際抽樣曾出現 raw=93.6、xivanalysis=93.6，但 Casts graph 只有 92.86。
        # 小幅 raw/graph gap 只在較高 raw 覆蓋率回 graph，避免把這類 packet 邊界誤修低。
        raw = {"percent": 93.6, "denominator_ms": 445248}
        graph = {"percent": 92.86, "denominator_ms": 446532}

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_black_mage_selector_keeps_raw_for_low_uptime_packet_gap(self) -> None:
        raw = {"percent": 82.68, "denominator_ms": 432671}
        graph = {"percent": 81.91, "denominator_ms": 439441}

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_black_mage_selector_keeps_raw_for_high_uptime_packet_gap(self) -> None:
        raw = {"percent": 95.77, "denominator_ms": 486990}
        graph = {"percent": 94.82, "denominator_ms": 488368}

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_black_mage_selector_uses_moderate_speed_for_high_estimate(self) -> None:
        raw = {
            "percent": 96.59,
            "denominator_ms": 513063,
            "estimated_spell_speed": 933,
        }
        graph = {"percent": 96.69, "denominator_ms": 514620}
        moderate = {
            "percent": 98.13,
            "denominator_ms": 513063,
            "speed_stat_source": "minimum_substat_override",
        }

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            moderate,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 98.13)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_black_mage_moderate_spell_speed_estimate",
        )
        self.assertEqual(selected["raw_events_percent"], 96.59)
        self.assertEqual(selected["estimated_spell_speed"], 933)

    def test_valigarmanda_black_mage_selector_keeps_raw_for_normal_estimate(self) -> None:
        raw = {
            "percent": 96.59,
            "denominator_ms": 513063,
            "estimated_spell_speed": 760,
        }
        graph = {"percent": 96.69, "denominator_ms": 514620}
        moderate = {"percent": 98.13, "denominator_ms": 513063}

        selected = gcd.gcd_core.select_valigarmanda_black_mage_coverage(
            raw,
            graph,
            moderate,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIs(selected, raw)

    def test_valigarmanda_machinist_selector_uses_graph_for_short_raw_denominator(self) -> None:
        raw = {
            "percent": 66.62,
            "denominator_ms": 315648,
            "covered_time_ms": 210290,
            "speed_stat_source": "estimated",
        }
        graph = {"percent": 55.23, "denominator_ms": 470552}

        selected = gcd.gcd_core.select_valigarmanda_machinist_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 55.23)
        self.assertEqual(
            selected["fallback_selection"],
            "valigarmanda_machinist_casts_graph_short_raw_denominator",
        )
        self.assertEqual(selected["raw_events_percent"], 66.62)

    def test_valigarmanda_machinist_selector_keeps_raw_for_normal_high_uptime(self) -> None:
        raw = {"percent": 96.08, "denominator_ms": 515000}
        graph = {"percent": 95.52, "denominator_ms": 516200}

        selected = gcd.gcd_core.select_valigarmanda_machinist_coverage(
            raw,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.08)
        self.assertEqual(selected["casts_graph_percent"], 95.52)

    def test_valigarmanda_warrior_selector_uses_minimum_speed_for_fast_estimate(self) -> None:
        raw = {
            "percent": 91.76,
            "denominator_ms": 638530,
            "denominator_downtime_ms": 10643,
            "speed_stat_source": "estimated",
        }
        minimum = {
            "percent": 94.0,
            "denominator_ms": 638530,
            "speed_stat_source": "minimum_substat_override",
        }
        graph = {"percent": 90.39, "denominator_ms": 649173}

        selected = gcd.gcd_core.select_valigarmanda_warrior_coverage(
            raw,
            minimum,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 94.0)
        self.assertEqual(selected["fallback_selection"], "valigarmanda_warrior_minimum_speed_estimate")
        self.assertEqual(selected["raw_events_percent"], 91.76)

    def test_valigarmanda_warrior_selector_keeps_raw_for_short_downtime(self) -> None:
        raw = {
            "percent": 91.24,
            "denominator_ms": 532567,
            "denominator_downtime_ms": 1781,
            "speed_stat_source": "estimated",
        }
        minimum = {
            "percent": 93.85,
            "denominator_ms": 532567,
            "speed_stat_source": "minimum_substat_override",
        }
        graph = {"percent": 90.93, "denominator_ms": 534348}

        selected = gcd.gcd_core.select_valigarmanda_warrior_coverage(
            raw,
            minimum,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 91.24)
        self.assertEqual(selected["minimum_speed_percent"], 93.85)

    def test_valigarmanda_warrior_selector_keeps_raw_for_high_uptime(self) -> None:
        raw = {"percent": 96.2, "denominator_ms": 510000, "speed_stat_source": "estimated"}
        minimum = {
            "percent": 98.1,
            "denominator_ms": 510000,
            "speed_stat_source": "minimum_substat_override",
        }
        graph = {"percent": 95.8, "denominator_ms": 512000}

        selected = gcd.gcd_core.select_valigarmanda_warrior_coverage(
            raw,
            minimum,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 96.2)
        self.assertEqual(selected["minimum_speed_percent"], 98.1)

    def test_valigarmanda_warrior_selector_keeps_raw_for_moderate_minimum_speed_delta(self) -> None:
        raw = {"percent": 92.15, "denominator_ms": 607630, "speed_stat_source": "estimated"}
        minimum = {
            "percent": 93.65,
            "denominator_ms": 607630,
            "speed_stat_source": "minimum_substat_override",
        }
        graph = {"percent": 91.64, "denominator_ms": 612860}

        selected = gcd.gcd_core.select_valigarmanda_warrior_coverage(
            raw,
            minimum,
            graph,
            encounter_key="extreme_valigarmanda",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(selected["percent"], 92.15)
        self.assertEqual(selected["minimum_speed_percent"], 93.65)

    def test_bard_selector_keeps_queen_raw_for_high_uptime(self) -> None:
        raw = {"percent": 98.48, "denominator_ms": 383646}
        graph = {"percent": 100.0, "denominator_ms": 555084}

        selected = gcd.gcd_core.select_bard_raw_event_coverage(
            raw,
            graph,
            encounter_key="extreme_queen_eternal",
        )

        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertIs(selected, raw)

    def test_bard_army_windows_use_paeon_not_muse_for_abc(self) -> None:
        raw_events = [
            {"type": "applybuff", "timestamp": 100, "sourceID": 7, "targetID": 7, "abilityGameID": 2218},
            {"type": "applybuff", "timestamp": 130, "sourceID": 7, "targetID": 7, "abilityGameID": 1932},
            {"type": "removebuff", "timestamp": 160, "sourceID": 7, "targetID": 7, "abilityGameID": 2218},
            {"type": "removebuff", "timestamp": 180, "sourceID": 7, "targetID": 7, "abilityGameID": 1932},
            {"type": "applybuff", "timestamp": 200, "sourceID": 7, "targetID": 7, "abilityGameID": 1932},
            {"type": "removebuff", "timestamp": 220, "sourceID": 7, "targetID": 7, "abilityGameID": 1932},
        ]

        windows = gcd.gcd_core.bard_army_windows_like_xivanalysis(
            raw_events=raw_events,
            source_id=7,
            fight_end_time=300,
        )

        # Army's Muse 只供 BRD 其他模組 tracking；Always Be Casting 只排除 Paeon。
        self.assertEqual(windows, [(100, 160)])

    def test_bard_army_windows_use_source_only_status_events(self) -> None:
        raw_events = [
            {"type": "applybuff", "timestamp": 1000, "sourceID": 7, "targetID": 7, "abilityGameID": 2218},
            {"type": "refreshbuff", "timestamp": 2000, "sourceID": 7, "targetID": 8, "abilityGameID": 2218},
            {"type": "removebuff", "timestamp": 2300, "sourceID": 7, "targetID": 8, "abilityGameID": 2218},
            {"type": "refreshbuff", "timestamp": 2600, "sourceID": 7, "targetID": 7, "abilityGameID": 2218},
            {"type": "removebuff", "timestamp": 4000, "sourceID": 7, "targetID": 7, "abilityGameID": 2218},
        ]

        windows = gcd.gcd_core.bard_army_windows_like_xivanalysis(
            raw_events=raw_events,
            source_id=7,
            fight_end_time=5000,
        )

        self.assertEqual(windows, [(1000, 2300), (2600, 4000)])

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
