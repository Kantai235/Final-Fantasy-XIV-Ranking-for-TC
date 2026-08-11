from __future__ import annotations

import contextlib
import copy
import io
import unittest
from typing import Any
from unittest.mock import patch

import fetch_fflogs as fflogs
from fflogs_pipeline import support_metrics


class SupportMetricsTest(unittest.TestCase):
    def test_source_ranking_keeps_support_summary_but_public_allowlist_does_not_yet_expose_it(self) -> None:
        healing_stats = {
            "calculation_version": 1,
            "hps": 12_345.67,
            "pure_healing": 1_000_000,
            "protection": 200_000,
            "overheal_percent": 15.5,
        }
        排行榜 = {
            "encounter": {"key": "fixture", "name": "測試副本", "category": "零式"},
            "reports": {
                "SUPPORT": {
                    "report_code": "SUPPORT",
                    "url": "https://www.fflogs.com/reports/SUPPORT",
                    "fights": [
                        {
                            "fight_id": 1,
                            "encounter_id": 99,
                            "difficulty": 101,
                            "clear_time_ms": 100_000,
                            "clear_time_seconds": 100,
                            "damage_time_ms": 100_000,
                            "damage_time_seconds": 100,
                            "recorded_at_iso": "2026-01-01T00:00:00Z",
                            "players": [
                                {
                                    "name": "測試補師",
                                    "server": "巴哈姆特",
                                    "job": "Scholar",
                                    "dps": 10_000,
                                    "rdps": 9_500,
                                    "adps": 9_700,
                                    "total_damage": 1_000_000,
                                    "active_time_ms": 95_000,
                                    "fflogs_id": 2,
                                    "healing_stats": healing_stats,
                                }
                            ],
                        }
                    ],
                }
            },
        }
        支援報告 = 排行榜["reports"]["SUPPORT"]
        舊報告 = copy.deepcopy(支援報告)
        舊報告["report_code"] = "OLD"
        舊報告["url"] = "https://www.fflogs.com/reports/OLD"
        舊報告["fights"][0]["players"][0].pop("healing_stats")
        排行榜["reports"] = {"OLD": 舊報告, "SUPPORT": 支援報告}

        來源條目 = fflogs.建立排行榜條目(排行榜)[0]
        公開條目 = fflogs.建立公開排行榜(排行榜)["ranking_entries"][0]

        self.assertEqual(來源條目["healing_stats"], healing_stats)
        self.assertEqual(來源條目["duplicate_count"], 2)
        self.assertNotIn("healing_stats", 公開條目)

    def test_healer_and_tank_metrics_are_derived_without_persisting_raw_events(self) -> None:
        玩家列表 = [
            {
                "name": "測試騎士",
                "server": "巴哈姆特",
                "job": "Paladin",
                "fflogs_id": 1,
                "fflogs_guid": 1001,
            },
            {
                "name": "測試白魔",
                "server": "巴哈姆特",
                "job": "WhiteMage",
                "fflogs_id": 2,
                "fflogs_guid": 1002,
            },
        ]
        治療表格 = {
            "data": {
                "combatTime": 10_000,
                "entries": [
                    {
                        "id": 1,
                        "guid": 1001,
                        "name": "測試騎士",
                        "total": 500,
                        "totalReduced": 300,
                        "overheal": 100,
                        "targets": [
                            {"id": 1, "name": "測試騎士", "total": 200, "totalReduced": 150},
                            {"id": 2, "name": "測試白魔", "total": 300, "totalReduced": 150},
                        ],
                    },
                    {
                        "id": 2,
                        "guid": 1002,
                        "name": "測試白魔",
                        "total": 1_200,
                        "totalReduced": 900,
                        "overheal": 300,
                        "targets": [],
                    },
                ],
            }
        }
        支援事件 = {
            "damage_taken": [
                # calculateddamage 與 damage 是同一次命中；只能計入後者。
                {"timestamp": 100, "type": "calculateddamage", "targetID": 1, "amount": 100},
                {
                    "timestamp": 100,
                    "type": "damage",
                    "sourceID": 90,
                    "targetID": 1,
                    "amount": 100,
                    "absorbed": 20,
                    "unmitigatedAmount": 200,
                },
                {
                    "timestamp": 300,
                    "type": "damage",
                    "sourceID": 99,
                    "targetID": 2,
                    "amount": 80,
                    "absorbed": 0,
                    "unmitigatedAmount": 120,
                },
                {
                    "timestamp": 500,
                    "type": "damage",
                    "sourceID": 90,
                    "targetID": 1,
                    "amount": 50,
                    "absorbed": 0,
                    "unmitigatedAmount": 100,
                },
            ],
            "friendly_buffs": [
                {
                    "timestamp": 50,
                    "type": "applybuff",
                    "sourceID": 1,
                    "targetID": 1,
                    "abilityGameID": 1191,
                    "packetID": 10,
                },
                {
                    "timestamp": 200,
                    "type": "removebuff",
                    "sourceID": 1,
                    "targetID": 1,
                    "abilityGameID": 1191,
                    "packetID": 11,
                },
                # 這次 Rampart 沒有任何傷害落在時窗內，必須算成無效 activation。
                {
                    "timestamp": 600,
                    "type": "applybuff",
                    "sourceID": 1,
                    "targetID": 1,
                    "abilityGameID": 1191,
                    "packetID": 12,
                },
                {
                    "timestamp": 800,
                    "type": "removebuff",
                    "sourceID": 1,
                    "targetID": 1,
                    "abilityGameID": 1191,
                    "packetID": 13,
                },
            ],
            "enemy_debuffs": [
                {
                    "timestamp": 250,
                    "type": "applydebuff",
                    "sourceID": 1,
                    "targetID": 99,
                    "abilityGameID": 1193,
                    "packetID": 20,
                },
                {
                    "timestamp": 400,
                    "type": "removedebuff",
                    "sourceID": 1,
                    "targetID": 99,
                    "abilityGameID": 1193,
                    "packetID": 21,
                },
            ],
        }

        摘要 = support_metrics.套用支援統計(
            玩家列表,
            治療表格,
            支援事件,
            預設戰鬥時間毫秒=10_000,
            戰鬥結束時間=1_000,
        )

        self.assertIsNotNone(摘要)
        self.assertFalse(摘要["raw_events_persisted"])
        self.assertEqual(摘要["healer_count"], 1)
        self.assertEqual(摘要["tank_count"], 1)

        補師摘要 = 玩家列表[1]["healing_stats"]
        self.assertEqual(補師摘要["hps"], 120.0)
        self.assertEqual(補師摘要["pure_healing"], 900)
        self.assertEqual(補師摘要["protection"], 300)
        self.assertEqual(補師摘要["overheal_percent"], 25.0)

        坦克摘要 = 玩家列表[0]["tank_stats"]
        self.assertEqual(坦克摘要["damage_taken"], 150)
        self.assertEqual(坦克摘要["absorbed_damage"], 20)
        self.assertEqual(坦克摘要["unmitigated_damage"], 300)
        self.assertEqual(坦克摘要["self_healing"], 150)
        self.assertEqual(坦克摘要["personal_protection"], 50)
        self.assertEqual(坦克摘要["team_protection"], 150)

        覆蓋 = 坦克摘要["mitigation_coverage"]
        self.assertEqual(覆蓋["total_activations"], 3)
        self.assertEqual(覆蓋["effective_activations"], 2)
        self.assertEqual(覆蓋["effective_activation_percent"], 66.67)
        self.assertEqual(覆蓋["personal"]["damage_coverage_percent"], 66.67)
        self.assertEqual(覆蓋["team"]["damage_coverage_percent"], 28.57)

    def test_same_name_players_do_not_guess_tank_target_breakdown(self) -> None:
        玩家列表 = [
            {"name": "同名角色", "server": "巴哈姆特", "job": "Paladin", "fflogs_id": 1},
            {"name": "同名角色", "server": "泰坦", "job": "WhiteMage", "fflogs_id": 2},
        ]
        治療表格 = {
            "data": {
                "combatTime": 10_000,
                "entries": [
                    {
                        "id": 1,
                        "name": "同名角色",
                        "total": 500,
                        "totalReduced": 300,
                        "targets": [{"name": "同名角色", "total": 500, "totalReduced": 300}],
                    }
                ],
            }
        }

        support_metrics.套用支援統計(
            玩家列表,
            治療表格,
            {"damage_taken": [], "friendly_buffs": [], "enemy_debuffs": []},
            預設戰鬥時間毫秒=10_000,
            戰鬥結束時間=10_000,
        )

        坦克摘要 = 玩家列表[0]["tank_stats"]
        self.assertFalse(坦克摘要["target_breakdown_complete"])
        self.assertIsNone(坦克摘要["self_healing"])
        self.assertIsNone(坦克摘要["personal_protection"])
        self.assertIsNone(坦克摘要["team_protection"])

    def test_missing_healing_table_fails_closed_for_support_roles(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "Healing table"):
            support_metrics.套用支援統計(
                [{"name": "測試學者", "server": "巴哈姆特", "job": "Scholar", "fflogs_id": 1}],
                None,
                {},
                預設戰鬥時間毫秒=10_000,
                戰鬥結束時間=10_000,
            )

    def test_support_event_query_follows_each_alias_cursor(self) -> None:
        回應 = [
            {
                "reportData": {
                    "report": {
                        "damageTaken": {
                            "data": [{"timestamp": 100, "type": "damage"}],
                            "nextPageTimestamp": 500,
                        },
                        "friendlyBuffs": {
                            "data": [{"timestamp": 120, "type": "applybuff"}],
                            "nextPageTimestamp": None,
                        },
                        "enemyDebuffs": {
                            "data": [{"timestamp": 130, "type": "applydebuff"}],
                            "nextPageTimestamp": 700,
                        },
                    }
                }
            },
            {
                "reportData": {
                    "report": {
                        "events": {
                            "data": [{"timestamp": 600, "type": "damage"}],
                            "nextPageTimestamp": None,
                        }
                    }
                }
            },
            {
                "reportData": {
                    "report": {
                        "events": {
                            "data": [{"timestamp": 800, "type": "removedebuff"}],
                            "nextPageTimestamp": None,
                        }
                    }
                }
            },
        ]
        with patch.object(fflogs, "執行_graphql", side_effect=回應) as 執行查詢:
            事件 = fflogs.查詢戰鬥支援事件(
                object(),
                object(),
                "PAGINATED",
                {"id": 4, "startTime": 0, "endTime": 1_000},
            )

        self.assertEqual([事件項["timestamp"] for 事件項 in 事件["damage_taken"]], [100, 600])
        self.assertEqual([事件項["timestamp"] for 事件項 in 事件["friendly_buffs"]], [120])
        self.assertEqual([事件項["timestamp"] for 事件項 in 事件["enemy_debuffs"]], [130, 800])
        self.assertEqual(執行查詢.call_count, 3)
        self.assertEqual(執行查詢.call_args_list[1].args[3]["startTime"], 500)
        self.assertEqual(執行查詢.call_args_list[2].args[3]["startTime"], 700)

    def test_support_event_combined_query_falls_back_to_single_type_pages(self) -> None:
        單欄位回應 = {
            "reportData": {
                "report": {"events": {"data": [], "nextPageTimestamp": None}}
            }
        }

        def 假查詢(
            session: Any,
            auth_pool: Any,
            query: str,
            variables: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            if "damageTaken: events" in query:
                raise fflogs.FFLogsGraphQL錯誤([{"message": "query is too complex"}])
            return 單欄位回應

        with (
            patch.object(fflogs, "執行_graphql", side_effect=假查詢) as 執行查詢,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            事件 = fflogs.查詢戰鬥支援事件(
                object(),
                object(),
                "FALLBACK",
                {"fight_id": 7, "start_time": 0, "end_time": 1_000},
            )

        self.assertEqual(事件, {"damage_taken": [], "friendly_buffs": [], "enemy_debuffs": []})
        self.assertEqual(執行查詢.call_count, 4)


if __name__ == "__main__":
    unittest.main()
