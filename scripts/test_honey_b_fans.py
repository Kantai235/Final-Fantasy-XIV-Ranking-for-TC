from __future__ import annotations

import unittest

import fetch_honey_b_fans as honey


class HoneyBFansPublicDataTest(unittest.TestCase):
    def test_public_payload_groups_top_fans_and_latest_records(self) -> None:
        source = honey.建立空來源(
            {
                "name": "零式 M2S / 蜂蜂小甜心",
                "zone_id": 62,
                "encounter_id": 94,
                "difficulty": 101,
                "scan_start_date": "2026-02-01",
            },
        )
        source["updated_at_iso"] = "2026-05-01T00:00:00+00:00"
        source["records"] = [
            {
                "id": "R1:2:7:1000",
                "fight_key": "R1:2",
                "report_code": "R1",
                "report_title": "AAC Light-heavyweight",
                "report_url": "https://www.fflogs.com/reports/R1",
                "fight_id": 2,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": "2026-04-30T12:00:00+00:00",
                "clear_time_seconds": 520.5,
                "event_at_iso": "2026-04-30T11:58:00+00:00",
                "seconds_from_pull": 164.358,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
                "collected_at_iso": "2026-05-01T00:00:00+00:00",
            },
            {
                "id": "R2:1:8:2000",
                "fight_key": "R2:1",
                "report_code": "R2",
                "report_title": "AAC Light-heavyweight",
                "report_url": "https://www.fflogs.com/reports/R2",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": "2026-05-01T12:00:00+00:00",
                "clear_time_seconds": 510.5,
                "event_at_iso": "2026-05-01T11:58:00+00:00",
                "seconds_from_pull": 302.043,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
                "collected_at_iso": "2026-05-01T00:01:00+00:00",
            },
            {
                "id": "R3:1:9:3000",
                "fight_key": "R3:1",
                "report_code": "R3",
                "report_title": "AAC Light-heavyweight",
                "report_url": "https://www.fflogs.com/reports/R3",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": "2026-04-29T12:00:00+00:00",
                "clear_time_seconds": 530.5,
                "event_at_iso": "2026-04-29T11:58:00+00:00",
                "seconds_from_pull": 180.0,
                "character_name": "里區欠",
                "server": "鳳凰",
                "job": "Gunbreaker",
                "collected_at_iso": "2026-05-01T00:02:00+00:00",
            },
        ]

        payload = honey.建立公開資料(source)

        self.assertEqual(payload["summary"]["total_event_count"], 3)
        self.assertEqual(payload["summary"]["kill_event_count"], 3)
        self.assertEqual(payload["summary"]["wipe_event_count"], 0)
        self.assertEqual(payload["summary"]["fan_count"], 2)
        self.assertEqual(payload["top_fans"][0]["character_name"], "岳白")
        self.assertEqual(payload["top_fans"][0]["total_event_count"], 2)
        self.assertEqual(payload["top_fans"][0]["fight_count"], 2)
        self.assertEqual([record["id"] for record in payload["top_fans"][0]["records"]], ["R2:1", "R1:2"])
        self.assertEqual(payload["top_fans"][0]["records"][0]["report_url"], "https://www.fflogs.com/reports/R2")
        self.assertEqual(payload["top_fans"][0]["records"][0]["event_count"], 1)
        self.assertEqual(payload["latest_records"][0]["id"], "R2:1")
        self.assertEqual(payload["latest_fans"][0]["character_name"], "里區欠")

    def test_public_payload_limits_leaderboard_to_recent_week_and_marks_streak(self) -> None:
        source = honey.建立空來源()
        source["updated_at_iso"] = "2026-05-15T00:00:00+00:00"
        source["records"] = [
            {
                "id": "R1:1:7:1000",
                "fight_key": "R1:1",
                "report_code": "R1",
                "report_title": "本期上傳",
                "report_url": "https://www.fflogs.com/reports/R1",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": "2026-05-14T12:00:00+00:00",
                "event_at_iso": "2026-05-14T11:58:00+00:00",
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
                "collected_at_iso": "2026-05-14T12:10:00+00:00",
            },
            {
                "id": "R2:1:7:1000",
                "fight_key": "R2:1",
                "report_code": "R2",
                "report_title": "前一週上傳",
                "report_url": "https://www.fflogs.com/reports/R2",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": "2026-05-07T12:00:00+00:00",
                "event_at_iso": "2026-05-07T11:58:00+00:00",
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
                "collected_at_iso": "2026-05-07T12:10:00+00:00",
            },
            {
                "id": "R3:1:9:1000",
                "fight_key": "R3:1",
                "report_code": "R3",
                "report_title": "本期另一位粉絲",
                "report_url": "https://www.fflogs.com/reports/R3",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": "2026-05-13T12:00:00+00:00",
                "event_at_iso": "2026-05-13T11:58:00+00:00",
                "character_name": "里區欠",
                "server": "鳳凰",
                "job": "Gunbreaker",
                "collected_at_iso": "2026-05-13T12:10:00+00:00",
            },
        ]

        payload = honey.建立公開資料(source)

        self.assertEqual(payload["leaderboard_window"]["days"], 7)
        self.assertEqual(payload["summary"]["total_event_count"], 2)
        self.assertEqual(payload["summary"]["historical_total_event_count"], 3)
        self.assertEqual([fan["character_name"] for fan in payload["top_fans"]], ["岳白", "里區欠"])
        self.assertEqual(payload["top_fans"][0]["total_event_count"], 1)
        self.assertEqual(payload["top_fans"][0]["historical_total_event_count"], 2)
        self.assertEqual(payload["top_fans"][0]["historical_record_count"], 2)
        self.assertEqual(payload["top_fans"][0]["current_streak_weeks"], 2)
        self.assertEqual([record["id"] for record in payload["top_fans"][0]["records"]], ["R1:1"])
        self.assertEqual([record["id"] for record in payload["latest_records"]], ["R1:1", "R3:1"])
        self.assertEqual(len(payload["records"]), 2)

    def test_public_payload_limits_latest_sections(self) -> None:
        source = honey.建立空來源()
        source["updated_at_iso"] = "2026-05-20T00:00:00+00:00"
        source["records"] = [
            {
                "id": f"R{index}:1:{index}:1000",
                "fight_key": f"R{index}:1",
                "report_code": f"R{index}",
                "report_title": "本期上傳",
                "report_url": f"https://www.fflogs.com/reports/R{index}",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_completed_at_iso": f"2026-05-19T{index % 24:02d}:00:00+00:00",
                "event_at_iso": f"2026-05-19T{index % 24:02d}:01:00+00:00",
                "character_name": f"粉絲{index:02d}",
                "server": "鳳凰",
                "job": "Sage",
                "collected_at_iso": f"2026-05-19T{index % 24:02d}:02:00+00:00",
            }
            for index in range(20)
        ]

        payload = honey.建立公開資料(source)

        self.assertEqual(len(payload["latest_records"]), 5)
        self.assertEqual(len(payload["latest_fans"]), 16)

    def test_empty_public_payload_keeps_stable_generated_time(self) -> None:
        payload = honey.建立公開資料(honey.建立空來源())

        self.assertEqual(payload["generated_at_iso"], "1970-01-01T00:00:00+00:00")
        self.assertEqual(payload["summary"]["total_event_count"], 0)
        self.assertEqual(payload["top_fans"], [])

    def test_latest_records_merge_duplicate_uploaded_reports(self) -> None:
        records = [
            {
                "id": "R1:7:1:1000",
                "fight_key": "R1:7",
                "report_code": "R1",
                "report_title": "第一份上傳",
                "report_url": "https://www.fflogs.com/reports/R1",
                "fight_id": 7,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-01T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-01T12:00:00+00:00",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-01T11:55:02+00:00",
                "seconds_from_pull": 302.0,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
            },
            {
                "id": "R2:3:1:1000",
                "fight_key": "R2:3",
                "report_code": "R2",
                "report_title": "第二份上傳",
                "report_url": "https://www.fflogs.com/reports/R2",
                "fight_id": 3,
                "fight_name": "蜂蜂小甜心",
                "fight_start_at_iso": "2026-05-01T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-01T12:00:00+00:00",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-01T11:55:02+00:00",
                "seconds_from_pull": 302.0,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
            },
        ]

        latest_records = honey.建立戰鬥公開紀錄(records)

        self.assertEqual(len(latest_records), 1)
        self.assertEqual(latest_records[0]["fan_event_count"], 1)
        self.assertEqual(latest_records[0]["duplicate_report_count"], 1)
        self.assertEqual(
            [report["report_code"] for report in latest_records[0]["source_reports"]],
            ["R1", "R2"],
        )

    def test_public_payload_uses_merged_latest_records(self) -> None:
        source = honey.建立空來源()
        source["records"] = [
            {
                "id": "R1:7:1:1000",
                "fight_key": "R1:7",
                "report_code": "R1",
                "report_title": "第一份上傳",
                "report_url": "https://www.fflogs.com/reports/R1",
                "fight_id": 7,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-01T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-01T12:00:00+00:00",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-01T11:55:02+00:00",
                "seconds_from_pull": 302.0,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
            },
            {
                "id": "R2:3:1:1000",
                "fight_key": "R2:3",
                "report_code": "R2",
                "report_title": "第二份上傳",
                "report_url": "https://www.fflogs.com/reports/R2",
                "fight_id": 3,
                "fight_name": "蜂蜂小甜心",
                "fight_start_at_iso": "2026-05-01T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-01T12:00:00+00:00",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-01T11:55:02+00:00",
                "seconds_from_pull": 302.0,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
            },
        ]

        payload = honey.建立公開資料(source)

        self.assertEqual(len(payload["latest_records"]), 1)
        self.assertEqual(payload["summary"]["fight_count"], 1)
        self.assertEqual(payload["latest_records"][0]["duplicate_report_count"], 1)
        self.assertEqual(
            [report["report_code"] for report in payload["latest_records"][0]["source_reports"]],
            ["R1", "R2"],
        )

    def test_public_payload_builds_activity_kill_team_rankings_from_cutoff(self) -> None:
        source = honey.建立空來源()
        source["updated_at_iso"] = "2026-06-01T00:00:00+00:00"
        source["records"] = [
            {
                "id": "R_BEFORE:1:1:1000",
                "fight_key": "R_BEFORE:1",
                "report_code": "R_BEFORE",
                "report_title": "活動切點前通關",
                "report_url": "https://www.fflogs.com/reports/R_BEFORE",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-29T15:49:59+00:00",
                "fight_completed_at_iso": "2026-05-29T15:59:59+00:00",
                "is_kill": True,
                "fight_status": "kill",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-29T15:55:00+00:00",
                "seconds_from_pull": 300.0,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
            },
            {
                "id": "R_BEFORE:1:2:1100",
                "fight_key": "R_BEFORE:1",
                "report_code": "R_BEFORE",
                "report_title": "活動切點前通關",
                "report_url": "https://www.fflogs.com/reports/R_BEFORE",
                "fight_id": 1,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-29T15:49:59+00:00",
                "fight_completed_at_iso": "2026-05-29T15:59:59+00:00",
                "is_kill": True,
                "fight_status": "kill",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-29T15:56:00+00:00",
                "seconds_from_pull": 360.0,
                "character_name": "里區欠",
                "server": "鳳凰",
                "job": "Gunbreaker",
            },
            {
                "id": "R_START:2:3:1000",
                "fight_key": "R_START:2",
                "report_code": "R_START",
                "report_title": "活動切點通關",
                "report_url": "https://www.fflogs.com/reports/R_START",
                "fight_id": 2,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-29T15:50:00+00:00",
                "fight_completed_at_iso": "2026-05-29T16:00:00+00:00",
                "is_kill": True,
                "fight_status": "kill",
                "clear_time_seconds": 600.0,
                "event_at_iso": "2026-05-29T15:55:00+00:00",
                "seconds_from_pull": 300.0,
                "character_name": "切點粉絲",
                "server": "鳳凰",
                "job": "Sage",
            },
            {
                "id": "R_AFTER:3:4:1000",
                "fight_key": "R_AFTER:3",
                "report_code": "R_AFTER",
                "report_title": "活動通關",
                "report_url": "https://www.fflogs.com/reports/R_AFTER",
                "fight_id": 3,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-30T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-30T12:00:00+00:00",
                "is_kill": True,
                "fight_status": "kill",
                "clear_time_seconds": 590.0,
                "event_at_iso": "2026-05-30T11:55:00+00:00",
                "seconds_from_pull": 300.0,
                "character_name": "最近粉絲",
                "server": "鳳凰",
                "job": "Dancer",
            },
            {
                "id": "R_AFTER:3:5:1100",
                "fight_key": "R_AFTER:3",
                "report_code": "R_AFTER",
                "report_title": "活動通關",
                "report_url": "https://www.fflogs.com/reports/R_AFTER",
                "fight_id": 3,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-30T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-30T12:00:00+00:00",
                "is_kill": True,
                "fight_status": "kill",
                "clear_time_seconds": 590.0,
                "event_at_iso": "2026-05-30T11:56:00+00:00",
                "seconds_from_pull": 360.0,
                "character_name": "另一位粉絲",
                "server": "鳳凰",
                "job": "Warrior",
            },
            {
                "id": "R_DUP:4:4:1000",
                "fight_key": "R_DUP:4",
                "report_code": "R_DUP",
                "report_title": "同場另一份上傳",
                "report_url": "https://www.fflogs.com/reports/R_DUP",
                "fight_id": 4,
                "fight_name": "蜂蜂小甜心",
                "fight_start_at_iso": "2026-05-30T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-30T12:00:00+00:00",
                "is_kill": True,
                "fight_status": "kill",
                "clear_time_seconds": 590.0,
                "event_at_iso": "2026-05-30T11:55:00+00:00",
                "seconds_from_pull": 300.0,
                "character_name": "最近粉絲",
                "server": "鳳凰",
                "job": "Dancer",
            },
            {
                "id": "R_WIPE:4:4:1000",
                "fight_key": "R_WIPE:4",
                "report_code": "R_WIPE",
                "report_title": "滅團場",
                "report_url": "https://www.fflogs.com/reports/R_WIPE",
                "fight_id": 4,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-30T12:20:00+00:00",
                "fight_completed_at_iso": "2026-05-30T12:24:00+00:00",
                "is_kill": False,
                "fight_status": "wipe",
                "clear_time_seconds": None,
                "fight_duration_seconds": 240.0,
                "event_at_iso": "2026-05-30T12:23:00+00:00",
                "seconds_from_pull": 180.0,
                "character_name": "滅團粉絲",
                "server": "鳳凰",
                "job": "BlackMage",
            },
        ]

        payload = honey.建立公開資料(source)

        self.assertEqual(payload["team_ranking_window"]["start_at_iso"], "2026-05-29T16:00:00+00:00")
        self.assertEqual(payload["summary"]["historical_team_record_count"], 3)
        self.assertEqual(payload["summary"]["team_ranking_record_count"], 2)
        self.assertEqual(payload["summary"]["team_ranking_event_count"], 3)
        self.assertEqual(payload["summary"]["top_team_event_count"], 2)
        self.assertEqual(payload["team_rankings"][0]["id"], "R_AFTER:3")
        self.assertEqual(payload["team_rankings"][0]["total_event_count"], 2)
        self.assertEqual(payload["team_rankings"][0]["unique_fan_count"], 2)
        self.assertEqual(payload["team_rankings"][0]["duplicate_report_count"], 1)
        self.assertEqual([member["event_count"] for member in payload["team_rankings"][0]["members"]], [1, 1])
        self.assertNotIn("R_BEFORE:1", [record["id"] for record in payload["team_rankings"]])
        self.assertEqual([record["id"] for record in payload["latest_records"][:2]], ["R_WIPE:4", "R_AFTER:3"])

    def test_report_detail_query_includes_wipe_fights(self) -> None:
        self.assertIn("fights(encounterID: $encounterID, difficulty: $difficulty)", honey.REPORT_DETAIL_QUERY)
        self.assertNotIn("killType: Kills", honey.REPORT_DETAIL_QUERY)

    def test_wipe_fight_record_keeps_duration_separate_from_clear_time(self) -> None:
        record = honey.建立粉絲紀錄(
            report={"code": "R_WIPE", "title": "含 wipe 的 report", "startTime": 100000},
            fight={
                "id": 4,
                "name": "Honey B. Lovely",
                "kill": False,
                "startTime": 2000,
                "endTime": 125456,
                "combatTime": 123456,
            },
            actor={"id": 7, "name": "岳白", "server": "鳳凰", "subType": "Sage", "type": "Player"},
            event={"type": "applydebuff", "targetID": 7, "timestamp": 62000},
            collected_at_iso="2026-05-01T00:00:00+00:00",
        )

        self.assertIsNotNone(record)
        assert record is not None
        self.assertFalse(record["is_kill"])
        self.assertEqual(record["fight_status"], "wipe")
        self.assertEqual(record["fight_status_label"], "滅團")
        self.assertEqual(record["fight_duration_seconds"], 123.456)
        self.assertIsNone(record["clear_time_seconds"])
        self.assertEqual(record["fight_scan_mode"], honey.FIGHT_SCAN_MODE)

    def test_public_payload_counts_wipe_records(self) -> None:
        source = honey.建立空來源()
        source["records"] = [
            {
                "id": "R1:7:1:1000",
                "fight_key": "R1:7",
                "report_code": "R1",
                "report_title": "滅團上傳",
                "report_url": "https://www.fflogs.com/reports/R1",
                "fight_id": 7,
                "fight_name": "Honey B. Lovely",
                "fight_start_at_iso": "2026-05-01T11:50:00+00:00",
                "fight_completed_at_iso": "2026-05-01T11:54:00+00:00",
                "is_kill": False,
                "fight_status": "wipe",
                "fight_status_label": "滅團",
                "fight_duration_seconds": 240.0,
                "clear_time_seconds": None,
                "event_at_iso": "2026-05-01T11:53:02+00:00",
                "seconds_from_pull": 182.0,
                "character_name": "岳白",
                "server": "鳳凰",
                "job": "Sage",
            },
        ]

        payload = honey.建立公開資料(source)

        self.assertEqual(payload["summary"]["kill_event_count"], 0)
        self.assertEqual(payload["summary"]["wipe_event_count"], 1)
        self.assertEqual(payload["summary"]["wipe_fight_count"], 1)
        self.assertEqual(payload["latest_records"][0]["fight_status"], "wipe")
        self.assertEqual(payload["latest_records"][0]["fight_duration_seconds"], 240.0)
        self.assertIsNone(payload["latest_records"][0]["clear_time_seconds"])

    def test_recorded_report_skips_detail_query(self) -> None:
        source = honey.建立空來源()
        source["records"] = [
            {
                "id": "R1:7:1:1000",
                "fight_key": "R1:7",
                "report_code": "R1",
                "fight_scan_mode": honey.FIGHT_SCAN_MODE,
            },
        ]

        original = honey.查詢報告詳情

        def fail_if_called(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("已有紀錄的 report 不應再次呼叫 detail query")

        honey.查詢報告詳情 = fail_if_called
        try:
            summary = honey.處理報告列表(
                None,
                None,
                source,
                [{"code": "R1", "title": "已收錄 report"}],
                {"encounter_id": 94, "difficulty": 101},
            )
        finally:
            honey.查詢報告詳情 = original

        self.assertEqual(summary["reports_seen"], 1)
        self.assertEqual(summary["reports_skipped_already_recorded"], 1)
        self.assertEqual(summary["fights_checked"], 0)

    def test_checked_report_cache_skips_detail_query(self) -> None:
        source = honey.建立空來源()
        source["state"]["checked_reports"] = {
            "R1": {
                "status": "checked",
                "report_code": "R1",
                "fight_scan_mode": honey.FIGHT_SCAN_MODE,
            },
        }

        original = honey.查詢報告詳情

        def fail_if_called(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("已完成快取的 report 不應再次呼叫 detail query")

        honey.查詢報告詳情 = fail_if_called
        try:
            summary = honey.處理報告列表(
                None,
                None,
                source,
                [{"code": "R1", "title": "已完成 report"}],
                {"encounter_id": 94, "difficulty": 101},
            )
        finally:
            honey.查詢報告詳情 = original

        self.assertEqual(summary["reports_skipped_already_recorded"], 1)
        self.assertEqual(summary["fights_checked"], 0)

    def test_legacy_checked_report_cache_does_not_skip_wipe_scan(self) -> None:
        source = honey.建立空來源()
        source["state"]["checked_reports"] = {
            "R_LEGACY": {
                "status": "checked",
                "report_code": "R_LEGACY",
            },
        }
        calls: list[str] = []
        original = honey.查詢報告詳情

        def fake_detail(
            _session: object,
            _auth_pool: object,
            _副本設定: dict[str, object],
            report_code: str,
        ) -> dict[str, object]:
            calls.append(report_code)
            return {
                "code": report_code,
                "title": "舊快取 report",
                "startTime": 1000,
                "endTime": 2000,
                "fights": [],
            }

        honey.查詢報告詳情 = fake_detail
        try:
            summary = honey.處理報告列表(
                None,
                None,
                source,
                [{"code": "R_LEGACY", "title": "舊快取 report"}],
                {"encounter_id": 94, "difficulty": 101},
            )
        finally:
            honey.查詢報告詳情 = original

        self.assertEqual(calls, ["R_LEGACY"])
        self.assertEqual(summary["reports_skipped_already_recorded"], 0)
        self.assertEqual(source["state"]["checked_reports"]["R_LEGACY"]["fight_scan_mode"], honey.FIGHT_SCAN_MODE)

    def test_report_without_m2s_fights_is_cached_after_detail_query(self) -> None:
        source = honey.建立空來源()
        calls: list[str] = []
        original = honey.查詢報告詳情

        def fake_detail(
            _session: object,
            _auth_pool: object,
            _副本設定: dict[str, object],
            report_code: str,
        ) -> dict[str, object]:
            calls.append(report_code)
            return {
                "code": report_code,
                "title": "沒有 M2S 戰鬥的 report",
                "startTime": 1000,
                "endTime": 2000,
                "fights": [],
            }

        honey.查詢報告詳情 = fake_detail
        try:
            first_summary = honey.處理報告列表(
                None,
                None,
                source,
                [{"code": "R_EMPTY", "title": "沒有 M2S 戰鬥的 report"}],
                {"encounter_id": 94, "difficulty": 101},
            )
        finally:
            honey.查詢報告詳情 = original

        self.assertEqual(calls, ["R_EMPTY"])
        self.assertEqual(first_summary["reports_skipped_already_recorded"], 0)
        self.assertEqual(
            source["state"]["checked_reports"]["R_EMPTY"]["status"],
            "skipped_no_m2s_fights",
        )

        def fail_if_called(*_args: object, **_kwargs: object) -> dict[str, object]:
            raise AssertionError("checked_reports 已完成時不應再次呼叫 detail query")

        honey.查詢報告詳情 = fail_if_called
        try:
            second_summary = honey.處理報告列表(
                None,
                None,
                source,
                [{"code": "R_EMPTY", "title": "沒有 M2S 戰鬥的 report"}],
                {"encounter_id": 94, "difficulty": 101},
            )
        finally:
            honey.查詢報告詳情 = original

        self.assertEqual(second_summary["reports_skipped_already_recorded"], 1)


if __name__ == "__main__":
    unittest.main()
