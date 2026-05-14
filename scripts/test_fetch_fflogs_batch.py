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

        with (
            patch.object(fflogs, "查詢通關戰鬥", 假通關戰鬥),
            patch.object(fflogs, "查詢多場玩家成績", 假多場玩家成績),
            patch.object(fflogs, "查詢玩家成績", 不應呼叫單場玩家成績),
        ):
            成績 = fflogs.建立報告成績(None, None, 副本設定, 淺層報告, [{"server": "巴哈姆特"}])

        self.assertEqual(批次呼叫, [[1, 2]])
        self.assertIsNotNone(成績)
        self.assertEqual(len(成績["fights"]), 2)
        self.assertEqual(成績["fights"][0]["players"][0]["dps"], 1000)
        self.assertEqual(成績["fights"][1]["players"][0]["dps"], 2000)

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


if __name__ == "__main__":
    unittest.main()
