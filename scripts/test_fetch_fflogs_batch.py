from __future__ import annotations

import contextlib
import io
import unittest
from typing import Any
from unittest.mock import patch

import fetch_fflogs as fflogs


def 建立測試原始成績(總傷害: int) -> dict[str, Any]:
    return {
        "player_details": {
            "data": {
                "playerDetails": {
                    "DPS": [
                        {
                            "id": 1,
                            "guid": 1001,
                            "name": "測試角色",
                            "server": "巴哈姆特",
                            "type": "BlackMage",
                        }
                    ]
                }
            }
        },
        "damage_done": {
            "data": {
                "combatTime": 10000,
                "damageDowntime": 0,
                "totalTime": 10000,
                "entries": [
                    {
                        "id": 1,
                        "guid": 1001,
                        "name": "測試角色",
                        "type": "BlackMage",
                        "total": 總傷害,
                        "totalRDPS": 總傷害,
                        "totalADPS": 總傷害,
                        "totalNDPS": 總傷害,
                        "activeTime": 9500,
                    }
                ],
            }
        },
        "rankings": {"data": []},
    }


class FetchFFLogsBatchTest(unittest.TestCase):
    def test_public_ranking_keeps_same_name_cross_server_players_separate(self) -> None:
        排行榜 = {
            "encounter": {
                "key": "fixture_encounter",
                "name": "測試副本",
                "category": "零式",
            },
            "reports": {
                "OLD": {
                    "report_code": "OLD",
                    "report_start_time_iso": "2026-01-01T01:50:00.000Z",
                    "url": "https://www.fflogs.com/reports/OLD",
                    "fights": [
                        {
                            "fight_id": 1,
                            "fight_hash": "old-fight",
                            "clear_time_seconds": 600,
                            "recorded_at_iso": "2026-01-01T02:00:00.000Z",
                            "players": [
                                {
                                    "name": "同名角色",
                                    "server": "巴哈姆特",
                                    "job": "Paladin",
                                    "dps": 210,
                                    "rdps": 200,
                                    "adps": 205,
                                    "total_damage": 1000,
                                    "active_time_ms": 500000,
                                }
                            ],
                        }
                    ],
                },
                "NEW": {
                    "report_code": "NEW",
                    "report_start_time_iso": "2026-01-04T03:50:00.000Z",
                    "url": "https://www.fflogs.com/reports/NEW",
                    "fights": [
                        {
                            "fight_id": 2,
                            "fight_hash": "new-fight",
                            "clear_time_seconds": 610,
                            "recorded_at_iso": "2026-01-04T04:00:00.000Z",
                            "players": [
                                {
                                    "name": "同名角色",
                                    "server": "泰坦",
                                    "job": "Paladin",
                                    "dps": 190,
                                    "rdps": 180,
                                    "adps": 185,
                                    "total_damage": 900,
                                    "active_time_ms": 490000,
                                }
                            ],
                        }
                    ],
                },
            },
        }

        公開排行榜 = fflogs.建立公開排行榜(排行榜)

        self.assertEqual(len(公開排行榜["ranking_entries"]), 2)
        self.assertEqual(
            {f"{條目['character_name']}@{條目['server']}:{條目['job']}" for 條目 in 公開排行榜["ranking_entries"]},
            {"同名角色@巴哈姆特:Paladin", "同名角色@泰坦:Paladin"},
        )
        self.assertEqual(
            {條目["server"] for 條目 in 公開排行榜["ranking_entries"]},
            {"巴哈姆特", "泰坦"},
        )
        self.assertTrue(all("original_server" not in 條目 for 條目 in 公開排行榜["ranking_entries"]))

    def test_public_ranking_keeps_legacy_flat_character_key_server(self) -> None:
        排行榜 = {
            "encounter": {
                "key": "fixture_encounter",
                "name": "測試副本",
                "category": "零式",
            },
            "ranking_entries": [
                {
                    "id": "old-entry",
                    "character_key": "同名角色@巴哈姆特:Paladin",
                    "character_name": "同名角色",
                    "server": "巴哈姆特",
                    "job": "Paladin",
                    "dps": 210,
                    "rdps": 200,
                    "adps": 205,
                    "clear_time_seconds": 600,
                    "recorded_at_iso": "2026-01-01T02:00:00.000Z",
                },
                {
                    "id": "new-entry",
                    "character_key": "同名角色@泰坦:Paladin",
                    "character_name": "同名角色",
                    "server": "泰坦",
                    "job": "Paladin",
                    "dps": 190,
                    "rdps": 180,
                    "adps": 185,
                    "clear_time_seconds": 610,
                    "recorded_at_iso": "2026-01-04T04:00:00.000Z",
                },
            ],
        }

        排行榜條目 = fflogs.建立排行榜條目(排行榜)
        公開排行榜 = fflogs.建立公開排行榜(排行榜)

        self.assertEqual(len(排行榜條目), 2)
        self.assertEqual(
            {條目["character_key"] for 條目 in 排行榜條目},
            {"同名角色@巴哈姆特:Paladin", "同名角色@泰坦:Paladin"},
        )
        self.assertEqual(len(公開排行榜["ranking_entries"]), 2)
        self.assertEqual(
            {條目["server"] for 條目 in 公開排行榜["ranking_entries"]},
            {"巴哈姆特", "泰坦"},
        )
        self.assertTrue(all("original_server" not in 條目 for 條目 in 公開排行榜["ranking_entries"]))

    def test_history_scan_deep_report_code_default_keeps_local_runs_conservative(self) -> None:
        self.assertEqual(fflogs.FFLogs執行設定預設值["history_max_deep_reports_per_run"], 200)
        self.assertEqual(fflogs.FFLogs執行設定預設值["history_max_deep_reports_per_group_per_run"], 0)

    def test_state_checkpoint_default_avoids_frequent_large_state_writes(self) -> None:
        self.assertEqual(fflogs.FFLogs執行設定預設值["state_checkpoint_flush_reports"], 2000)

    def test_fflogs_runtime_settings_can_be_overridden_by_environment(self) -> None:
        原始設定 = {
            "history_scan_enabled": False,
            "history_scan_windows_per_run": 0,
            "history_scan_window_hours": 24,
            "history_max_deep_reports_per_run": 0,
            "history_max_deep_reports_per_group_per_run": 0,
            "existing_report_status_check_enabled": False,
            "existing_report_status_check_limit": 0,
            "report_region_scope": "china",
            "fetch_gcd_coverage_enabled": False,
            "fetch_gcd_coverage_max_fights_per_run": 0,
            "request_timeout": 30,
            "incremental_lookback_hours": 24,
            "no_clear_retry_hours": 24,
            "delayed_scan_enabled": False,
            "delayed_scan_recent_gap_hours": 24,
            "delayed_scan_lookback_hours": 72,
            "delayed_max_deep_reports_per_run": 0,
            "state_checkpoint_flush_reports": 10,
            "retry_report_codes": [],
        }

        with patch.dict(
            fflogs.os.environ,
            {
                "FFLOGS_HISTORY_SCAN_ENABLED": "true",
                "FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN": "2",
                "FFLOGS_HISTORY_SCAN_WINDOW_HOURS": "12",
                "FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN": "10",
                "FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_GROUP_PER_RUN": "4",
                "FFLOGS_EXISTING_REPORT_STATUS_CHECK_ENABLED": "true",
                "FFLOGS_EXISTING_REPORT_STATUS_CHECK_LIMIT": "200",
                "FFLOGS_REPORT_REGION_SCOPE": "all",
                "FFLOGS_FETCH_GCD_COVERAGE_ENABLED": "true",
                "FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN": "500",
                "FFLOGS_REQUEST_TIMEOUT": "12.5",
                "FFLOGS_INCREMENTAL_LOOKBACK_HOURS": "24",
                "FFLOGS_NO_CLEAR_RETRY_HOURS": "48",
                "FFLOGS_DELAYED_SCAN_ENABLED": "true",
                "FFLOGS_DELAYED_SCAN_RECENT_GAP_HOURS": "24",
                "FFLOGS_DELAYED_SCAN_LOOKBACK_HOURS": "72",
                "FFLOGS_DELAYED_MAX_DEEP_REPORTS_PER_RUN": "30",
                "FFLOGS_STATE_CHECKPOINT_FLUSH_REPORTS": "75",
                "FFLOGS_RETRY_REPORT_CODES": "abc123, def456",
            },
        ):
            覆寫後設定 = fflogs.套用環境變數覆寫設定(原始設定)

        self.assertTrue(覆寫後設定["history_scan_enabled"])
        self.assertEqual(覆寫後設定["history_scan_windows_per_run"], 2)
        self.assertEqual(覆寫後設定["history_scan_window_hours"], 12)
        self.assertEqual(覆寫後設定["history_max_deep_reports_per_run"], 10)
        self.assertEqual(覆寫後設定["history_max_deep_reports_per_group_per_run"], 4)
        self.assertTrue(覆寫後設定["existing_report_status_check_enabled"])
        self.assertEqual(覆寫後設定["existing_report_status_check_limit"], 200)
        self.assertEqual(覆寫後設定["report_region_scope"], "all")
        self.assertTrue(覆寫後設定["fetch_gcd_coverage_enabled"])
        self.assertEqual(覆寫後設定["fetch_gcd_coverage_max_fights_per_run"], 500)
        self.assertEqual(覆寫後設定["request_timeout"], 12.5)
        self.assertEqual(覆寫後設定["incremental_lookback_hours"], 24)
        self.assertEqual(覆寫後設定["no_clear_retry_hours"], 48)
        self.assertTrue(覆寫後設定["delayed_scan_enabled"])
        self.assertEqual(覆寫後設定["delayed_scan_recent_gap_hours"], 24)
        self.assertEqual(覆寫後設定["delayed_scan_lookback_hours"], 72)
        self.assertEqual(覆寫後設定["delayed_max_deep_reports_per_run"], 30)
        self.assertEqual(覆寫後設定["state_checkpoint_flush_reports"], 75)
        self.assertEqual(覆寫後設定["retry_report_codes"], ["abc123", "def456"])

    def test_report_fight_list_query_does_not_request_ranked_character_claimed(self) -> None:
        # claimed 是 FFLogs 帳號認領狀態，部分 report 會因這個欄位回傳權限錯誤；
        # 目前資料管線不使用它，避免查詢非必要欄位造成整份 report 整理失敗。
        self.assertIn("rankedCharacters", fflogs.戰鬥清單查詢)
        self.assertNotIn("claimed", fflogs.戰鬥清單查詢)

    def test_ucob_fight_list_does_not_depend_on_fflogs_kill_flag(self) -> None:
        副本設定 = {"encounter_id": 1073, "difficulty": 100}
        呼叫查詢: list[str] = []

        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            呼叫查詢.append(查詢)
            return {
                "reportData": {
                    "report": {
                        "code": "ucob123",
                        "fights": [
                            {
                                "id": 21,
                                "encounterID": 1073,
                                "name": "Nael Deus Darnus / Bahamut Prime / Twintania",
                                "kill": False,
                                "startTime": 0,
                                "endTime": 619000,
                                "fightPercentage": 80,
                            },
                            {
                                "id": 22,
                                "encounterID": 1073,
                                "name": "Nael Deus Darnus / Bahamut Prime / Twintania",
                                "kill": False,
                                "startTime": 0,
                                "endTime": 957000,
                                "fightPercentage": 80,
                            },
                            {
                                "id": 23,
                                "encounterID": 1073,
                                "name": "Twintania",
                                "kill": False,
                                "startTime": 0,
                                "endTime": 900000,
                                "fightPercentage": 80,
                            },
                            {
                                "id": 24,
                                "encounterID": 1073,
                                "name": "Nael Deus Darnus / Bahamut Prime / Twintania",
                                "kill": True,
                                "startTime": 0,
                                "endTime": 1000,
                                "fightPercentage": 0,
                            },
                        ],
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql):
            報告 = fflogs.查詢通關戰鬥(None, None, 副本設定, "ucob123")

        self.assertEqual(呼叫查詢, [fflogs.戰鬥清單全部查詢])
        self.assertNotIn("killType: Kills", 呼叫查詢[0])
        self.assertIsNotNone(報告)
        self.assertEqual([戰鬥["id"] for 戰鬥 in 報告["fights"]], [22, 24])

    def test_top_fight_list_still_uses_native_kill_filter(self) -> None:
        # TOP（絕歐）P3/P4 的 enemy preload 會影響未來 Phase 判斷，但 FFLogs kill 旗標目前可用。
        # 這個測試鎖住 UCoB workaround 的範圍，避免把所有絕本都改成全 fight 查詢而增加誤收風險。
        副本設定 = {"encounter_id": 1077, "difficulty": 100}
        呼叫查詢: list[str] = []

        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            呼叫查詢.append(查詢)
            return {
                "reportData": {
                    "report": {
                        "code": "top123",
                        "fights": [
                            {
                                "id": 88,
                                "encounterID": 1077,
                                "name": "The Omega Protocol",
                                "kill": True,
                                "startTime": 0,
                                "endTime": 1120000,
                            }
                        ],
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql):
            報告 = fflogs.查詢通關戰鬥(None, None, 副本設定, "top123")

        self.assertEqual(呼叫查詢, [fflogs.戰鬥清單查詢])
        self.assertIn("killType: Kills", 呼叫查詢[0])
        self.assertIsNotNone(報告)
        self.assertEqual([戰鬥["id"] for 戰鬥 in 報告["fights"]], [88])

    def test_delayed_scan_window_targets_24_to_72_hours_before_scan_end(self) -> None:
        一小時 = 60 * 60 * 1000
        掃描結束 = 100 * 一小時

        with (
            patch.object(fflogs, "延遲掃描已啟用", True),
            patch.object(fflogs, "延遲掃描最近避讓小時", 24),
            patch.object(fflogs, "延遲掃描回溯小時", 72),
        ):
            區間, 狀態 = fflogs.建立延遲掃描區間({"key": "savage_m1s"}, 掃描結束)

        self.assertEqual(區間, {"start_at": 28 * 一小時, "end_at": 76 * 一小時 - 1})
        self.assertIsNotNone(狀態)
        self.assertEqual(狀態["recent_gap_hours"], 24)
        self.assertEqual(狀態["lookback_hours"], 72)

    def test_history_scan_cursor_stays_at_last_selected_report_when_limit_is_full(self) -> None:
        歷史補查狀態 = {
            "current_cursor_at": 1000,
            "current_cursor_at_iso": fflogs.毫秒轉_iso(1000),
            "next_cursor_at": 8000,
            "next_cursor_at_iso": fflogs.毫秒轉_iso(8000),
            "windows": [
                {
                    "start_at": 1000,
                    "start_at_iso": fflogs.毫秒轉_iso(1000),
                    "end_at": 7999,
                    "end_at_iso": fflogs.毫秒轉_iso(7999),
                }
            ],
        }
        候選列表 = [
            {"code": "first", "startTime": 2000},
            {"code": "last-selected", "startTime": 5000},
        ]

        fflogs.套用歷史補查深查上限游標(
            歷史補查狀態,
            候選列表,
            {"selected": 2, "skipped_known": 0, "deferred": 3},
        )

        self.assertEqual(歷史補查狀態["next_cursor_at"], 5000)
        self.assertEqual(歷史補查狀態["cursor_resume_source"], "last_selected_report_start_time")
        self.assertEqual(歷史補查狀態["cursor_resume_report_code"], "last-selected")
        self.assertTrue(歷史補查狀態["cursor_limited_by_deep_report_limit"])

    def test_history_scan_cursor_stays_at_window_start_when_limit_was_used_by_previous_encounter(self) -> None:
        歷史補查狀態 = {
            "current_cursor_at": 1000,
            "next_cursor_at": 8000,
            "windows": [
                {
                    "start_at": 1000,
                    "end_at": 7999,
                }
            ],
        }

        fflogs.套用歷史補查深查上限游標(
            歷史補查狀態,
            [],
            {"selected": 0, "skipped_known": 5, "deferred": 20},
        )

        self.assertEqual(歷史補查狀態["next_cursor_at"], 1000)
        self.assertEqual(歷史補查狀態["cursor_resume_source"], "current_window_start")
        self.assertIsNone(歷史補查狀態["cursor_resume_report_code"])

    def test_history_deep_candidate_budget_limits_each_zone_group(self) -> None:
        額度 = fflogs.歷史補查深層候選額度(總上限=10, 群組上限=2)
        舊絕本 = {"zone_id": 59, "difficulty": 100}
        伊甸絕 = {"zone_id": 65, "difficulty": 100}

        self.assertTrue(額度.可加入(舊絕本, "old-1"))
        額度.加入(舊絕本, "old-1")
        self.assertTrue(額度.可加入(舊絕本, "old-2"))
        額度.加入(舊絕本, "old-2")

        self.assertFalse(額度.可加入(舊絕本, "old-3"))
        self.assertTrue(額度.可加入(舊絕本, "old-1"))
        self.assertTrue(額度.可加入(伊甸絕, "fru-1"))

    def test_history_deep_candidate_budget_still_honors_global_limit(self) -> None:
        額度 = fflogs.歷史補查深層候選額度(總上限=2, 群組上限=0)
        第一組 = {"zone_id": 59, "difficulty": 100}
        第二組 = {"zone_id": 65, "difficulty": 100}

        額度.加入(第一組, "first")
        額度.加入(第二組, "second")

        self.assertFalse(額度.可加入(第二組, "third"))
        self.assertTrue(額度.可加入(第一組, "first"))

    def test_graphql_private_report_error_is_report_access_error(self) -> None:
        self.assertTrue(
            fflogs.GraphQL錯誤是否為報告存取錯誤(
                [
                    {
                        "message": "This report is private.",
                        "path": ["reportData", "report"],
                    }
                ]
            )
        )
        self.assertFalse(
            fflogs.GraphQL錯誤是否為報告存取錯誤(
                [
                    {
                        "message": "You do not have permission to view the claimed characters for this user.",
                        "path": ["reportData", "report", "rankedCharacters", 0, "claimed"],
                    }
                ]
            )
        )

    def test_report_tc_player_check_is_cached_per_run(self) -> None:
        呼叫報告代碼: list[str] = []

        def 假繁中服檢查(session: Any, 認證池: Any, 報告代碼: str) -> tuple[bool, list[dict[str, Any]]]:
            呼叫報告代碼.append(報告代碼)
            return True, [{"name": "測試角色", "server": "巴哈姆特"}]

        快取: dict[str, dict[str, Any]] = {}

        with patch.object(fflogs, "報告是否包含繁中服玩家", 假繁中服檢查):
            第一次 = fflogs.取得本輪報告繁中服檢查結果(快取, None, None, "same-report")
            第二次 = fflogs.取得本輪報告繁中服檢查結果(快取, None, None, "same-report")

        self.assertEqual(呼叫報告代碼, ["same-report"])
        self.assertEqual(第一次, 第二次)
        self.assertTrue(第二次[0])

    def test_report_tc_player_check_cached_error_is_reused(self) -> None:
        呼叫次數 = 0

        def 假繁中服檢查(session: Any, 認證池: Any, 報告代碼: str) -> tuple[bool, list[dict[str, Any]]]:
            nonlocal 呼叫次數
            呼叫次數 += 1
            raise fflogs.FFLogs報告存取錯誤("private")

        快取: dict[str, dict[str, Any]] = {}

        with patch.object(fflogs, "報告是否包含繁中服玩家", 假繁中服檢查):
            with self.assertRaises(fflogs.FFLogs報告存取錯誤):
                fflogs.取得本輪報告繁中服檢查結果(快取, None, None, "same-report")
            with self.assertRaises(fflogs.FFLogs報告存取錯誤):
                fflogs.取得本輪報告繁中服檢查結果(快取, None, None, "same-report")

        self.assertEqual(呼叫次數, 1)

    def test_existing_report_status_check_candidates_are_oldest_first(self) -> None:
        副本清單 = [
            {"key": "encounter_a", "name": "副本 A"},
            {"key": "encounter_b", "name": "副本 B"},
        ]
        排行榜索引 = {
            "encounter_a": {
                "reports": {
                    "new": {"report_start_time": 3000, "fights": []},
                    "hidden": {
                        "report_start_time": 1000,
                        "report_hidden": True,
                        "fights": [],
                    },
                }
            },
            "encounter_b": {
                "reports": {
                    "old": {"report_start_time": 1000, "fights": []},
                    "middle": {
                        "fights": [
                            {
                                "recorded_at": 2000,
                            }
                        ]
                    },
                }
            },
        }

        候選列表 = fflogs.建立既有報告狀態巡檢候選(副本清單, 排行榜索引)

        self.assertEqual([候選["report_code"] for 候選 in 候選列表], ["old", "middle", "new"])
        self.assertNotIn("hidden", [候選["report_code"] for 候選 in 候選列表])

    def test_existing_report_status_check_batch_wraps_after_newest(self) -> None:
        候選列表 = [
            {"report_code": "old", "sort_key": [1000, "a", "old"]},
            {"report_code": "middle", "sort_key": [2000, "a", "middle"]},
            {"report_code": "new", "sort_key": [3000, "a", "new"]},
        ]
        狀態 = {
            "existing_report_status_check": {
                "last_sort_key": [2000, "a", "middle"],
            }
        }

        選取列表, 選取狀態 = fflogs.選取既有報告狀態巡檢批次(候選列表, 狀態, 2)

        self.assertEqual([候選["report_code"] for 候選 in 選取列表], ["new", "old"])
        self.assertTrue(選取狀態["wrapped"])

    def test_report_status_query_marks_inaccessible_archive_status(self) -> None:
        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "reportData": {
                    "report": {
                        "code": 變數["code"] if 變數 else "unknown",
                        "archiveStatus": {"isAccessible": False},
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql):
            with self.assertRaises(fflogs.FFLogs報告狀態不可存取錯誤):
                fflogs.查詢報告目前狀態(None, None, "hidden-code")

    def test_shallow_report_scan_filters_to_china_scope_when_configured(self) -> None:
        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "reportData": {
                    "reports": {
                        "data": [
                            {"code": "china", "region": {"id": fflogs.中國區域_ID, "name": "China"}},
                            {"code": "global", "region": {"id": 1, "name": "North America"}},
                        ],
                        "has_more_pages": False,
                    }
                }
            }

        with (
            patch.object(fflogs, "執行_graphql", 假_graphql),
            patch.object(fflogs, "掃描全部地區報告", False),
            patch.object(fflogs, "報告地區範圍", "china"),
        ):
            報告列表 = fflogs.擷取時間區間報告(None, None, {"zone_id": 62}, 1, 2)

        self.assertEqual([報告["code"] for 報告 in 報告列表], ["china"])

    def test_shallow_report_scan_can_keep_all_regions_for_workflow(self) -> None:
        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            return {
                "reportData": {
                    "reports": {
                        "data": [
                            {"code": "china", "region": {"id": fflogs.中國區域_ID, "name": "China"}},
                            {"code": "global", "region": {"id": 1, "name": "North America"}},
                        ],
                        "has_more_pages": False,
                    }
                }
            }

        with (
            patch.object(fflogs, "執行_graphql", 假_graphql),
            patch.object(fflogs, "掃描全部地區報告", True),
            patch.object(fflogs, "報告地區範圍", "all"),
        ):
            報告列表 = fflogs.擷取時間區間報告(None, None, {"zone_id": 62}, 1, 2)

        self.assertEqual([報告["code"] for 報告 in 報告列表], ["china", "global"])

    def test_graphql_503_is_treated_as_transient_api_error(self) -> None:
        class 假回應:
            status_code = 503
            ok = False
            text = "Service Unavailable" * 80

            def json(self) -> dict[str, Any]:
                return {}

        class 假認證池:
            認證 = {"limiter": None}

            def 取得目前認證(self) -> dict[str, Any]:
                return self.認證

            def 取得_token(self, 認證: dict[str, Any]) -> tuple[dict[str, Any], str]:
                return 認證, "token"

            def 切換下一組(self) -> None:
                return None

        with patch.object(fflogs, "post_並重試", return_value=假回應()):
            with self.assertRaises(fflogs.FFLogs暫時性API錯誤) as 錯誤內容:
                fflogs.執行_graphql(
                    None,
                    假認證池(),
                    "query Test { reportData { reports { data { code } } } }",
                )

        self.assertEqual(錯誤內容.exception.status_code, 503)
        self.assertIn("已截短", str(錯誤內容.exception))

    def test_partial_state_update_keeps_failed_encounter_scan_cursor(self) -> None:
        原始狀態 = {
            "last_scanned_at": 1000,
            "last_scanned_at_iso": "1970-01-01T00:00:01+00:00",
            "encounters": {
                "done": {
                    "last_scanned_at": 1000,
                    "active_scan": {"stage": "深層過濾與成績整理"},
                    "processed_reports": {"old": {"status": "saved"}},
                },
                "deferred": {
                    "last_scanned_at": 1000,
                    "active_scan": {"stage": "淺層掃描", "current_window_start_at": 900},
                    "processed_reports": {"keep": {"status": "saved"}},
                },
            },
        }
        寫入結果: list[dict[str, Any]] = []

        def 假寫入_json(path: Any, content: dict[str, Any], **kwargs: Any) -> None:
            寫入結果.append(content)

        with (
            patch.object(fflogs, "寫入_json", 假寫入_json),
            patch.object(fflogs, "現在毫秒", return_value=3000),
        ):
            fflogs.更新狀態(
                原始狀態,
                2000,
                {"deferred_encounters": ["deferred"]},
                [{"key": "done"}],
                完整成功=False,
            )

        self.assertEqual(len(寫入結果), 1)
        新狀態 = 寫入結果[0]
        self.assertEqual(新狀態["last_scanned_at"], 1000)
        self.assertFalse(新狀態["last_run_completed"])
        self.assertEqual(新狀態["encounters"]["done"]["last_scanned_at"], 2000)
        self.assertEqual(新狀態["encounters"]["done"]["processed_reports"], {})
        self.assertNotIn("active_scan", 新狀態["encounters"]["done"])
        self.assertEqual(新狀態["encounters"]["deferred"]["last_scanned_at"], 1000)
        self.assertEqual(
            新狀態["encounters"]["deferred"]["processed_reports"],
            {"keep": {"status": "saved"}},
        )
        self.assertEqual(新狀態["encounters"]["deferred"]["active_scan"]["stage"], "淺層掃描")

    def test_deep_scan_resume_skips_checked_prefix(self) -> None:
        狀態 = {
            "encounters": {
                "ultimate": {
                    "active_scan": {
                        "stage": fflogs.深層掃描階段名稱,
                        "scan_start_at": 1000,
                        "current_report_index": 3,
                        "current_report_code": "r3",
                    }
                }
            }
        }
        報告列表 = [
            {"code": "r1"},
            {"code": "r2"},
            {"code": "r3"},
            {"code": "r4"},
        ]

        起始索引, 說明 = fflogs.取得深層掃描恢復起始索引(
            狀態,
            {"key": "ultimate"},
            報告列表,
            [{"key": "ultimate"}],
            {"ultimate": {"r1", "r2", "r3"}},
            1000,
        )

        self.assertEqual(起始索引, 3)
        self.assertIsNotNone(說明)
        self.assertIn("r4", 說明 or "")

    def test_deep_scan_resume_starts_at_first_unchecked_prefix_report(self) -> None:
        狀態 = {
            "encounters": {
                "ultimate": {
                    "active_scan": {
                        "stage": fflogs.深層掃描階段名稱,
                        "scan_start_at": 1000,
                        "current_report_code": "r4",
                    }
                }
            }
        }
        報告列表 = [
            {"code": "r1"},
            {"code": "r2"},
            {"code": "r3"},
            {"code": "r4"},
        ]

        起始索引, 說明 = fflogs.取得深層掃描恢復起始索引(
            狀態,
            {"key": "ultimate"},
            報告列表,
            [{"key": "ultimate"}],
            {"ultimate": {"r1", "r3", "r4"}},
            1000,
        )

        self.assertEqual(起始索引, 1)
        self.assertIsNotNone(說明)
        self.assertIn("r2", 說明 or "")

    def test_deep_scan_resume_does_not_skip_forced_report(self) -> None:
        狀態 = {
            "encounters": {
                "ultimate": {
                    "active_scan": {
                        "stage": fflogs.深層掃描階段名稱,
                        "scan_start_at": 1000,
                        "current_report_code": "r3",
                    }
                }
            }
        }
        報告列表 = [{"code": "r1"}, {"code": "r2"}, {"code": "r3"}]

        起始索引, 說明 = fflogs.取得深層掃描恢復起始索引(
            狀態,
            {"key": "ultimate"},
            報告列表,
            [{"key": "ultimate"}],
            {"ultimate": {"r1", "r2", "r3"}},
            1000,
            強制處理報告代碼={"r2"},
        )

        self.assertEqual(起始索引, 1)
        self.assertIsNotNone(說明)
        self.assertIn("r2", 說明 or "")

    def test_deep_scan_resume_can_use_previous_progress_snapshot(self) -> None:
        狀態 = {
            "encounters": {
                "ultimate": {
                    "active_scan": {
                        "stage": "準備掃描",
                        "scan_start_at": 1000,
                    }
                }
            }
        }
        前次即時進度 = {
            "stage": fflogs.深層掃描階段名稱,
            "scan_start_at": 1000,
            "current_report_code": "r2",
        }

        起始索引, 說明 = fflogs.取得深層掃描恢復起始索引(
            狀態,
            {"key": "ultimate"},
            [{"code": "r1"}, {"code": "r2"}, {"code": "r3"}],
            [{"key": "ultimate"}],
            {"ultimate": {"r1", "r2"}},
            1000,
            前次即時進度=前次即時進度,
        )

        self.assertEqual(起始索引, 2)
        self.assertIsNotNone(說明)
        self.assertIn("r3", 說明 or "")

    def test_processed_prefix_fast_forward_stops_at_first_unprocessed_report(self) -> None:
        起始索引 = fflogs.取得已處理報告前綴快轉索引(
            [{"code": "r1"}, {"code": "r2"}, {"code": "r3"}],
            [{"key": "ultimate"}],
            {"ultimate": {"r1"}},
        )

        self.assertEqual(起始索引, 1)

    def test_processed_prefix_fast_forward_does_not_skip_forced_report(self) -> None:
        起始索引 = fflogs.取得已處理報告前綴快轉索引(
            [{"code": "r1"}, {"code": "r2"}, {"code": "r3"}],
            [{"key": "ultimate"}],
            {"ultimate": {"r1", "r2", "r3"}},
            強制處理報告代碼={"r2"},
        )

        self.assertEqual(起始索引, 1)

    def test_processed_prefix_fast_forward_requires_all_same_zone_encounters_checked(self) -> None:
        起始索引 = fflogs.取得已處理報告前綴快轉索引(
            [{"code": "r1"}, {"code": "r2"}],
            [{"key": "ultimate_a"}, {"key": "ultimate_b"}],
            {
                "ultimate_a": {"r1", "r2"},
                "ultimate_b": {"r2"},
            },
        )

        self.assertEqual(起始索引, 0)

    def test_batch_query_keeps_each_fight_as_separate_alias(self) -> None:
        副本設定 = {"encounter_id": 93, "difficulty": 101}
        呼叫紀錄: list[tuple[str, dict[str, Any]]] = []

        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            呼叫紀錄.append((查詢, 變數 or {}))
            self.assertIn("fightIDs: [11]", 查詢)
            self.assertIn("fightIDs: [22]", 查詢)
            self.assertIn("killType: Kills", 查詢)
            return {
                "reportData": {
                    "report": {
                        "playerDetails_0": {"fight": 11},
                        "damageDone_0": {"fight": 11},
                        "rankings_0": {"fight": 11},
                        "playerDetails_1": {"fight": 22},
                        "damageDone_1": {"fight": 22},
                        "rankings_1": {"fight": 22},
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql), contextlib.redirect_stderr(io.StringIO()):
            結果 = fflogs.查詢多場玩家成績(None, None, 副本設定, "abc123", [11, 22])

        self.assertEqual(len(呼叫紀錄), 1)
        self.assertEqual(呼叫紀錄[0][1], {"code": "abc123", "encounterID": 93, "difficulty": 101})
        self.assertEqual(結果[11]["player_details"], {"fight": 11})
        self.assertEqual(結果[22]["damage_done"], {"fight": 22})

    def test_ucob_batch_player_stats_omits_native_kill_filter(self) -> None:
        副本設定 = {"encounter_id": 1073, "difficulty": 100}
        呼叫查詢: list[str] = []

        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            呼叫查詢.append(查詢)
            return {
                "reportData": {
                    "report": {
                        "playerDetails_0": {"fight": 42},
                        "damageDone_0": {"fight": 42},
                        "rankings_0": {"fight": 42},
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql), contextlib.redirect_stderr(io.StringIO()):
            結果 = fflogs.查詢多場玩家成績(None, None, 副本設定, "ucob123", [42])

        self.assertEqual(len(呼叫查詢), 1)
        self.assertIn("fightIDs: [42]", 呼叫查詢[0])
        self.assertNotIn("killType: Kills", 呼叫查詢[0])
        self.assertEqual(結果[42]["damage_done"], {"fight": 42})

    def test_batch_query_can_pin_each_fight_to_explicit_time_window(self) -> None:
        副本設定 = {"encounter_id": 94, "difficulty": 101}

        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            self.assertIn("fightIDs: [31]", 查詢)
            self.assertIn("startTime: 12012597.0", 查詢)
            self.assertIn("endTime: 12604496.0", 查詢)
            return {
                "reportData": {
                    "report": {
                        "playerDetails_0": {"fight": 31},
                        "damageDone_0": {"fight": 31},
                        "rankings_0": {"fight": 31},
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql), contextlib.redirect_stderr(io.StringIO()):
            結果 = fflogs.查詢多場玩家成績(
                None,
                None,
                副本設定,
                "abc123",
                [31],
                {31: {"start_time": 12012597, "end_time": 12604496}},
            )

        self.assertEqual(結果[31]["damage_done"], {"fight": 31})

    def test_batch_query_splits_when_fflogs_rejects_alias_size(self) -> None:
        副本設定 = {"encounter_id": 93, "difficulty": 101}
        呼叫戰鬥_id: list[list[int]] = []

        def 假_graphql(
            session: Any,
            認證池: Any,
            查詢: str,
            變數: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            本次戰鬥_id = []
            if "fightIDs: [11]" in 查詢:
                本次戰鬥_id.append(11)
            if "fightIDs: [22]" in 查詢:
                本次戰鬥_id.append(22)
            呼叫戰鬥_id.append(本次戰鬥_id)
            if len(本次戰鬥_id) > 1:
                raise fflogs.FFLogsGraphQL錯誤([{"message": "query is too complex"}])

            戰鬥_id = 本次戰鬥_id[0]
            return {
                "reportData": {
                    "report": {
                        "playerDetails_0": {"fight": 戰鬥_id},
                        "damageDone_0": {"fight": 戰鬥_id},
                        "rankings_0": {"fight": 戰鬥_id},
                    }
                }
            }

        with patch.object(fflogs, "執行_graphql", 假_graphql), contextlib.redirect_stderr(io.StringIO()):
            結果 = fflogs.查詢多場玩家成績(None, None, 副本設定, "abc123", [11, 22])

        self.assertEqual(呼叫戰鬥_id, [[11, 22], [11], [22]])
        self.assertEqual(結果[11]["rankings"], {"fight": 11})
        self.assertEqual(結果[22]["player_details"], {"fight": 22})

    def test_report_score_uses_one_stats_batch_for_multiple_fights(self) -> None:
        副本設定 = {
            "key": "savage_m1s",
            "name": "零式 M1S / 黑貓",
            "category": "零式",
            "zone_id": 62,
            "encounter_id": 93,
            "difficulty": 101,
        }
        淺層報告 = {"code": "abc123", "title": "測試報告", "startTime": 100000, "endTime": 130000}
        批次呼叫: list[list[int]] = []

        def 假通關戰鬥(
            session: Any,
            認證池: Any,
            目標副本: dict[str, Any],
            報告代碼: str,
        ) -> dict[str, Any]:
            return {
                "code": 報告代碼,
                "title": "測試報告",
                "startTime": 100000,
                "endTime": 130000,
                "fights": [
                    {
                        "id": 1,
                        "encounterID": 93,
                        "difficulty": 101,
                        "kill": True,
                        "startTime": 0,
                        "endTime": 10000,
                        "combatTime": 10000,
                    },
                    {
                        "id": 2,
                        "encounterID": 93,
                        "difficulty": 101,
                        "kill": True,
                        "startTime": 20000,
                        "endTime": 30000,
                        "combatTime": 10000,
                    },
                ],
            }

        def 假多場玩家成績(
            session: Any,
            認證池: Any,
            目標副本: dict[str, Any],
            報告代碼: str,
            戰鬥_id清單: list[int],
            戰鬥時間範圍索引: dict[int, dict[str, int | float]] | None = None,
        ) -> dict[int, dict[str, Any]]:
            批次呼叫.append(list(戰鬥_id清單))
            return {戰鬥_id: 建立測試原始成績(戰鬥_id * 10000) for 戰鬥_id in 戰鬥_id清單}

        def 不應呼叫單場玩家成績(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise AssertionError("建立報告成績應使用批次玩家成績查詢，避免每場 fight 各打一個 API request。")

        gcd呼叫: list[tuple[str, int, int]] = []

        class 假即時Gcd計算器:
            def 補齊戰鬥玩家GCD覆蓋率(
                self,
                session: Any,
                認證池: Any,
                報告代碼: str,
                副本設定: dict[str, Any],
                戰鬥: dict[str, Any],
                玩家列表: list[dict[str, Any]],
            ) -> None:
                gcd呼叫.append((報告代碼, 戰鬥["fight_id"], len(玩家列表)))
                for 玩家 in 玩家列表:
                    玩家["gcd_coverage"] = {"percent": 97.5, "calculation_version": 5}
                    玩家["gcd_coverage_status"] = {"state": "ok"}

        with (
            patch.object(fflogs, "查詢通關戰鬥", 假通關戰鬥),
            patch.object(fflogs, "查詢多場玩家成績", 假多場玩家成績),
            patch.object(fflogs, "查詢玩家成績", 不應呼叫單場玩家成績),
        ):
            成績 = fflogs.建立報告成績(
                None,
                None,
                副本設定,
                淺層報告,
                [{"server": "巴哈姆特"}],
                假即時Gcd計算器(),
            )

        self.assertEqual(批次呼叫, [[1, 2]])
        self.assertEqual(gcd呼叫, [("abc123", 1, 1), ("abc123", 2, 1)])
        self.assertIsNotNone(成績)
        self.assertEqual(len(成績["fights"]), 2)
        self.assertEqual(成績["fights"][0]["players"][0]["dps"], 1000)
        self.assertEqual(成績["fights"][1]["players"][0]["dps"], 2000)
        self.assertEqual(成績["fights"][0]["players"][0]["gcd_coverage"]["percent"], 97.5)

    def test_report_score_defers_when_damage_table_is_still_partial(self) -> None:
        副本設定 = {
            "key": "savage_m2s",
            "name": "零式 M2S / 蜂蜂",
            "category": "零式",
            "zone_id": 62,
            "encounter_id": 94,
            "difficulty": 101,
        }
        淺層報告 = {"code": "partial123", "title": "測試報告", "startTime": 100000, "endTime": 105000}

        def 假通關戰鬥(
            session: Any,
            認證池: Any,
            目標副本: dict[str, Any],
            報告代碼: str,
        ) -> dict[str, Any]:
            return {
                "code": 報告代碼,
                "title": "測試報告",
                "startTime": 100000,
                # report.endTime 只到 fight 開始後 5 秒，但 fight.endTime 是 10 秒。
                # 這代表 FFLogs 尚未完整匯出 damageDone table，不能落地成排行榜資料。
                "endTime": 105000,
                "fights": [
                    {
                        "id": 31,
                        "encounterID": 94,
                        "difficulty": 101,
                        "kill": True,
                        "startTime": 0,
                        "endTime": 10000,
                        "combatTime": 10000,
                    }
                ],
            }

        def 假多場玩家成績(
            session: Any,
            認證池: Any,
            目標副本: dict[str, Any],
            報告代碼: str,
            戰鬥_id清單: list[int],
            戰鬥時間範圍索引: dict[int, dict[str, int | float]] | None = None,
        ) -> dict[int, dict[str, Any]]:
            原始成績 = 建立測試原始成績(10000)
            原始成績["damage_done"]["data"]["totalTime"] = 1000
            原始成績["damage_done"]["data"]["combatTime"] = 1000
            原始成績["damage_done"]["data"]["entries"][0]["activeTime"] = 900
            return {31: 原始成績}

        with (
            patch.object(fflogs, "查詢通關戰鬥", 假通關戰鬥),
            patch.object(fflogs, "查詢多場玩家成績", 假多場玩家成績),
        ):
            with self.assertRaises(fflogs.FFLogs報告尚未完整匯出錯誤) as 錯誤內容:
                fflogs.建立報告成績(None, None, 副本設定, 淺層報告, [{"server": "巴哈姆特"}])

        self.assertEqual(錯誤內容.exception.報告代碼, "partial123")
        self.assertEqual(錯誤內容.exception.戰鬥_id, 31)
        self.assertEqual(錯誤內容.exception.報告結束時間戳記, 105000)
        self.assertEqual(錯誤內容.exception.戰鬥結束時間戳記, 110000)

    def test_retryable_incomplete_export_status_is_not_treated_as_processed(self) -> None:
        副本設定 = {"key": "savage_m2s"}
        狀態 = {
            "encounters": {
                "savage_m2s": {
                    "processed_reports": {
                        "retry-me": {"status": fflogs.報告尚未完整匯出狀態},
                    },
                    "checked_reports": {
                        "retry-me-too": {"status": fflogs.報告尚未完整匯出狀態},
                        "done": {"status": "saved"},
                    },
                }
            }
        }

        with patch.object(fflogs, "讀取排行榜檔案", return_value={"reports": {}}):
            已處理 = fflogs.讀取已處理報告代碼(狀態, 副本設定)

        self.assertNotIn("retry-me", 已處理)
        self.assertNotIn("retry-me-too", 已處理)
        self.assertIn("done", 已處理)

    def test_recent_no_clear_status_is_retried_only_inside_retry_window(self) -> None:
        副本設定 = {"key": "savage_m3s"}
        現在 = 1_000_000_000
        一小時 = 60 * 60 * 1000
        狀態 = {
            "encounters": {
                "savage_m3s": {
                    "processed_reports": {
                        "recent-no-clear": {
                            "status": fflogs.無通關報告狀態,
                            "processed_at": 現在 - 一小時,
                        },
                    },
                    "checked_reports": {
                        "old-no-clear": {
                            "status": fflogs.無通關報告狀態,
                            "processed_at": 現在 - 25 * 一小時,
                        },
                        "done": {"status": "saved"},
                    },
                }
            }
        }

        with (
            patch.object(fflogs, "讀取排行榜檔案", return_value={"reports": {}}),
            patch.object(fflogs, "現在毫秒", return_value=現在),
            patch.object(fflogs, "無通關報告重試毫秒", 24 * 一小時),
        ):
            已處理 = fflogs.讀取已處理報告代碼(狀態, 副本設定)
            嚴格已知 = fflogs.讀取已處理報告代碼(
                狀態,
                副本設定,
                可重試報告視為未處理=False,
            )

        self.assertNotIn("recent-no-clear", 已處理)
        self.assertIn("old-no-clear", 已處理)
        self.assertIn("done", 已處理)
        self.assertIn("recent-no-clear", 嚴格已知)
        self.assertIn("old-no-clear", 嚴格已知)
        self.assertIn("done", 嚴格已知)

    def test_ultimate_known_report_without_clear_rule_revision_needs_history_recheck(self) -> None:
        副本設定 = {"key": "ultimate_bahamut", "category": "絕", "encounter_id": 1073}
        副本狀態 = {
            "checked_reports": {
                "old-no-clear": {"status": fflogs.無通關報告狀態},
                "old-no-tc": {"status": fflogs.無繁中服玩家報告狀態},
                "already-rechecked": {
                    "status": fflogs.無通關報告狀態,
                    "clear_rule_revision": fflogs.絕本通關規則版本,
                },
            }
        }

        self.assertTrue(
            fflogs.報告需要絕本通關規則重判(
                副本設定,
                "old-no-clear",
                副本狀態,
                {"old-no-clear", "old-no-tc", "already-rechecked"},
            )
        )
        self.assertFalse(
            fflogs.報告需要絕本通關規則重判(
                副本設定,
                "old-no-tc",
                副本狀態,
                {"old-no-clear", "old-no-tc", "already-rechecked"},
            )
        )
        self.assertFalse(
            fflogs.報告需要絕本通關規則重判(
                副本設定,
                "already-rechecked",
                副本狀態,
                {"old-no-clear", "old-no-tc", "already-rechecked"},
            )
        )
        self.assertFalse(
            fflogs.報告需要絕本通關規則重判(
                副本設定,
                "unknown",
                副本狀態,
                {"old-no-clear", "old-no-tc", "already-rechecked"},
            )
        )

    def test_unaffected_ultimate_report_never_needs_clear_rule_recheck(self) -> None:
        副本設定 = {"key": "ultimate_omega", "category": "絕", "encounter_id": 1077}
        副本狀態 = {"checked_reports": {"known": {"status": fflogs.無通關報告狀態}}}

        self.assertFalse(
            fflogs.報告需要絕本通關規則重判(
                副本設定,
                "known",
                副本狀態,
                {"known"},
            )
        )

    def test_non_ultimate_report_never_needs_ultimate_clear_rule_recheck(self) -> None:
        副本設定 = {"key": "savage_m3s", "category": "零式"}
        副本狀態 = {"checked_reports": {"known": {"status": fflogs.無通關報告狀態}}}

        self.assertFalse(
            fflogs.報告需要絕本通關規則重判(
                副本設定,
                "known",
                副本狀態,
                {"known"},
            )
        )
        self.assertEqual(
            fflogs.建立報告處理額外內容({"key": "ultimate_omega", "category": "絕"}, {"has_clear": True}),
            {"has_clear": True, "clear_rule_revision": fflogs.絕本通關規則版本},
        )
        self.assertEqual(
            fflogs.建立報告處理額外內容(副本設定, {"has_clear": True}),
            {"has_clear": True},
        )

    def test_ranking_rebuild_prefers_reports_over_stale_flat_entries(self) -> None:
        排行榜 = {
            "encounter": {"key": "savage_m2s", "name": "零式 M2S / 蜂蜂"},
            "ranking_entries": [
                {
                    "character_name": "測試角色",
                    "server": "巴哈姆特",
                    "job": "Dancer",
                    "dps": 99999,
                    "rdps": 99999,
                    "adps": 99999,
                    "report_code": "abc123",
                    "fight_id": 1,
                }
            ],
            "reports": {
                "abc123": {
                    "title": "測試報告",
                    "url": "https://www.fflogs.com/reports/abc123",
                    "fights": [
                        {
                            "fight_id": 1,
                            "clear_time_ms": 10000,
                            "clear_time_seconds": 10,
                            "fflogs_total_time_ms": 10000,
                            "damage_time_ms": 10000,
                            "damage_time_seconds": 10,
                            "recorded_at": 100000,
                            "recorded_at_iso": "1970-01-01T00:01:40+00:00",
                            "players": [
                                {
                                    "name": "測試角色",
                                    "server": "巴哈姆特",
                                    "job": "Dancer",
                                    "dps": 20000,
                                    "rdps": 21000,
                                    "adps": 20000,
                                    "total_damage": 200000,
                                    "active_time_ms": 9900,
                                    "gcd_coverage": {"percent": 98.76},
                                    "gcd_coverage_status": {"state": "ok"},
                                }
                            ],
                        }
                    ],
                }
            },
        }

        條目 = fflogs.建立排行榜條目(排行榜)

        self.assertEqual(len(條目), 1)
        self.assertEqual(條目[0]["rdps"], 21000)
        self.assertEqual(條目[0]["dps"], 20000)
        self.assertEqual(條目[0]["gcd_coverage"]["percent"], 98.76)
        self.assertEqual(條目[0]["gcd_coverage_status"]["state"], "ok")

    def test_hidden_reports_are_excluded_from_default_public_rankings(self) -> None:
        排行榜 = {
            "encounter": {"key": "savage_m1s", "name": "零式 M1S / 黑貓"},
            "reports": {
                "visible": {
                    "title": "公開報告",
                    "url": "https://www.fflogs.com/reports/visible",
                    "fights": [
                        {
                            "fight_id": 1,
                            "clear_time_seconds": 600,
                            "damage_time_ms": 600000,
                            "recorded_at_iso": "2026-01-01T00:00:00+00:00",
                            "players": [
                                {
                                    "name": "公開角色",
                                    "server": "巴哈姆特",
                                    "job": "Paladin",
                                    "dps": 100,
                                    "rdps": 100,
                                    "adps": 100,
                                }
                            ],
                        }
                    ],
                },
                "hidden": {
                    "report_hidden": True,
                    "hidden_reason": fflogs.報告無法存取隱藏原因,
                    "hidden_detected_at_iso": "2026-05-19T00:00:00+00:00",
                    "hidden_source": "test",
                    "title": "隱藏報告",
                    "url": "https://www.fflogs.com/reports/hidden",
                    "fights": [
                        {
                            "fight_id": 2,
                            "clear_time_seconds": 500,
                            "damage_time_ms": 500000,
                            "recorded_at_iso": "2026-01-02T00:00:00+00:00",
                            "players": [
                                {
                                    "name": "隱藏角色",
                                    "server": "巴哈姆特",
                                    "job": "Paladin",
                                    "dps": 999,
                                    "rdps": 999,
                                    "adps": 999,
                                }
                            ],
                        }
                    ],
                },
            },
        }

        預設公開 = fflogs.建立公開排行榜(排行榜)
        含隱藏公開 = fflogs.建立公開排行榜(排行榜, 包含隱藏報告=True)

        self.assertEqual([條目["character_name"] for 條目 in 預設公開["ranking_entries"]], ["公開角色"])
        self.assertFalse(預設公開["hidden_reports_included"])
        self.assertEqual(
            sorted(條目["character_name"] for 條目 in 含隱藏公開["ranking_entries"]),
            ["公開角色", "隱藏角色"],
        )
        隱藏條目 = next(條目 for 條目 in 含隱藏公開["ranking_entries"] if 條目["character_name"] == "隱藏角色")
        self.assertTrue(隱藏條目["report_hidden"])
        self.assertEqual(隱藏條目["hidden_reason"], fflogs.報告無法存取隱藏原因)

    def test_mark_ranking_report_hidden_preserves_report_context(self) -> None:
        排行榜 = {
            "reports": {
                "abc123": {
                    "report_code": "abc123",
                    "title": "既有報告",
                    "fights": [],
                }
            }
        }

        with patch.object(fflogs, "現在毫秒", return_value=1779123456789):
            已變更 = fflogs.標記排行榜報告隱藏(
                排行榜,
                "abc123",
                來源="test",
                詳細原因="permission to view this report",
            )

        self.assertTrue(已變更)
        報告 = 排行榜["reports"]["abc123"]
        self.assertTrue(報告["report_hidden"])
        self.assertEqual(報告["hidden_reason"], fflogs.報告無法存取隱藏原因)
        self.assertEqual(報告["hidden_source"], "test")
        self.assertEqual(報告["hidden_detected_at"], 1779123456789)
        self.assertIn("permission to view this report", 報告["hidden_detail"])


if __name__ == "__main__":
    unittest.main()
