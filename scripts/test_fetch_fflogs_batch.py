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


if __name__ == "__main__":
    unittest.main()
