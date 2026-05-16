from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import fetch_fflogs as fflogs  # noqa: E402


# Honey B. Lovely 粉絲榜是趣味資料，不參與正式排行榜、個人成績單或全服統計。
# 來源檔保留「已檢查戰鬥」與 debuff 衍生紀錄；公開檔只輸出前端需要的聚合結果。
SOURCE_PATH = PROJECT_ROOT / "data" / "fun" / "honey_b_fans.json"
PUBLIC_PATH = PROJECT_ROOT / "public" / "data" / "fun" / "honey_b_fans.json"
ENCOUNTERS_PATH = PROJECT_ROOT / "config" / "encounters.json"
FEATURE_KEY = "honey_b_lovely_fans"
ENCOUNTER_KEY = "savage_m2s"
ENCOUNTER_NAME = "零式 M2S / Honey B. Lovely"
DEBUFF_ABILITY_ID = 1003926
DEBUFF_NAME = "心醉魂迷：奴役"
FIGHT_SCAN_MODE = "kills_and_wipes"
DEFAULT_RECENT_DAYS = 3
DEFAULT_HISTORY_LIMIT = 200000
DEFAULT_SCAN_WINDOW_HOURS = 24
CHINA_REGION_ID = 4
COMPLETED_FIGHT_STATUSES = {"checked", "skipped_no_tc_players"}
COMPLETED_REPORT_STATUSES = {"checked", "skipped_no_m2s_fights", "skipped_no_m2s_kills"}

RECENT_REPORTS_QUERY = """
query HoneyRecentReports($startTime: Float!, $endTime: Float!, $page: Int!, $limit: Int!, $zoneID: Int!) {
  reportData {
    reports(startTime: $startTime, endTime: $endTime, page: $page, limit: $limit, zoneID: $zoneID) {
      data {
        code
        title
        startTime
        endTime
        region {
          id
          name
        }
      }
      current_page
      has_more_pages
    }
  }
}
"""

REPORT_DETAIL_QUERY = """
query HoneyReportDetail($code: String!, $encounterID: Int!, $difficulty: Int!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      visibility
      region {
        id
        name
      }
      fights(encounterID: $encounterID, difficulty: $difficulty) {
        id
        encounterID
        name
        difficulty
        kill
        startTime
        endTime
        combatTime
        friendlyPlayers
      }
      masterData(translate: false) {
        actors(type: "Player") {
          id
          name
          server
          subType
          type
        }
        abilities {
          gameID
          name
          type
        }
      }
    }
  }
}
"""


def 讀取副本設定() -> dict[str, Any]:
    encounters = fflogs.讀取_json(ENCOUNTERS_PATH, [])
    if not isinstance(encounters, list):
        raise RuntimeError("config/encounters.json 必須是陣列。")

    for encounter in encounters:
        if isinstance(encounter, dict) and encounter.get("key") == ENCOUNTER_KEY:
            return encounter

    raise RuntimeError(f"找不到 {ENCOUNTER_KEY} 副本設定。")


def 建立空來源(副本設定: dict[str, Any] | None = None) -> dict[str, Any]:
    scan_start_date = (副本設定 or {}).get("scan_start_date") or "2026-02-01"
    return {
        "schema_version": 1,
        "feature": FEATURE_KEY,
        "description": "Honey B. Lovely 粉絲榜趣味資料，與正式排行榜資料分開保存。",
        "source_encounter": {
            "key": ENCOUNTER_KEY,
            "name": (副本設定 or {}).get("name") or ENCOUNTER_NAME,
            "zone_id": (副本設定 or {}).get("zone_id"),
            "encounter_id": (副本設定 or {}).get("encounter_id"),
            "difficulty": (副本設定 or {}).get("difficulty"),
            "scan_start_date": scan_start_date,
        },
        "target_debuff": {
            "ability_id": DEBUFF_ABILITY_ID,
            "name": DEBUFF_NAME,
            "count_rule": "以 FFLogs Debuffs events 的 applydebuff 判定通關與 wipe 場次中吃到第 4 顆並進入奴役。",
        },
        "state": {
            "recent_lookback_days": DEFAULT_RECENT_DAYS,
            "history_cursor_at": None,
            "history_cursor_at_iso": None,
            "history_max_unrecorded_fights_per_run": DEFAULT_HISTORY_LIMIT,
            "fight_scan_mode": FIGHT_SCAN_MODE,
            "checked_fights": {},
            "checked_reports": {},
            "failed_reports": {},
            "last_run": None,
        },
        "records": [],
        "created_at_iso": None,
        "updated_at_iso": None,
    }


def 讀取來源(副本設定: dict[str, Any] | None = None) -> dict[str, Any]:
    source = fflogs.讀取_json(SOURCE_PATH, 建立空來源(副本設定))
    if not isinstance(source, dict):
        source = 建立空來源(副本設定)

    source.setdefault("schema_version", 1)
    source.setdefault("feature", FEATURE_KEY)
    source.setdefault("source_encounter", 建立空來源(副本設定)["source_encounter"])
    source.setdefault("target_debuff", 建立空來源(副本設定)["target_debuff"])
    source.setdefault("records", [])
    source.setdefault("state", {})
    state = source["state"]
    if not isinstance(state, dict):
        source["state"] = {}
        state = source["state"]
    state["fight_scan_mode"] = FIGHT_SCAN_MODE
    if 轉_int(state.get("history_max_unrecorded_fights_per_run")) in {None, 200000}:
        state["history_max_unrecorded_fights_per_run"] = DEFAULT_HISTORY_LIMIT
    state.setdefault("checked_fights", {})
    state.setdefault("checked_reports", {})
    state.setdefault("failed_reports", {})
    return source


def 寫入來源與公開檔(source: dict[str, Any], *, dry_run: bool = False) -> None:
    public_payload = 建立公開資料(source)
    if dry_run:
        print(json.dumps({"source": source, "public": public_payload}, ensure_ascii=False, indent=2))
        return

    fflogs.寫入_json(SOURCE_PATH, source)
    fflogs.寫入_json(PUBLIC_PATH, public_payload)


def 轉_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def 轉_float(value: Any) -> float | None:
    return fflogs.轉_float(value)


def 時間加總_iso(report_start_time: Any, relative_time: Any) -> tuple[int | None, str | None]:
    timestamp = fflogs.相對戰鬥時間轉實際時間(report_start_time, relative_time)
    return timestamp, fflogs.毫秒轉_iso(timestamp)


def 戰鬥鍵(report_code: str, fight_id: int) -> str:
    return f"{report_code}:{fight_id}"


def 紀錄鍵(report_code: str, fight_id: int, target_id: int, timestamp: int) -> str:
    return f"{report_code}:{fight_id}:{target_id}:{timestamp}"


def 角色鍵(record: dict[str, Any]) -> str:
    return f"{record.get('character_name', '')}@{record.get('server', '')}"


def 是通關戰鬥(fight: dict[str, Any]) -> bool:
    kill = fight.get("kill")
    if isinstance(kill, bool):
        return kill
    if isinstance(kill, (int, float)):
        return kill != 0
    if isinstance(kill, str):
        return kill.strip().lower() in {"1", "true", "kill", "killed"}
    return False


def 紀錄戰鬥狀態(record: dict[str, Any]) -> str:
    status = record.get("fight_status")
    if status in {"kill", "wipe"}:
        return str(status)
    if record.get("is_kill") is False:
        return "wipe"
    return "kill"


def 紀錄戰鬥狀態標籤(record: dict[str, Any]) -> str:
    return "通關" if 紀錄戰鬥狀態(record) == "kill" else "滅團"


def 公開戰鬥去重鍵(record: dict[str, Any]) -> str:
    # 同一場 M2S 戰鬥可能被不同隊友以不同語系上傳，FFLogs fight_name 會在
    # "Honey B. Lovely" 與「蜂蜂小甜心」之間變動。Honey 粉絲榜已固定只掃 M2S，
    # 因此公開列表以實際戰鬥時間軸去重，避免語系名稱讓同一場被拆成多筆。
    return "|".join(
        str(part or "")
        for part in (
            record.get("fight_start_at_iso"),
            record.get("fight_completed_at_iso"),
            record.get("fight_duration_seconds") or record.get("clear_time_seconds"),
        )
    )


def 建立角色索引(actors: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    actor_index: dict[int, dict[str, Any]] = {}
    for actor in actors:
        actor_id = 轉_int(actor.get("id"))
        if actor_id is None:
            continue
        actor_index[actor_id] = actor
    return actor_index


def 是繁中服玩家(actor: dict[str, Any] | None) -> bool:
    return bool(actor and actor.get("server") in fflogs.繁中服伺服器名稱 and actor.get("type") == "Player")


def 報告已失敗(source: dict[str, Any], report_code: str, error: Exception) -> None:
    state = source.setdefault("state", {})
    failed_reports = state.setdefault("failed_reports", {})
    failed_reports[report_code] = {
        "status": "error",
        "error": str(error)[:500],
        "checked_at_iso": fflogs.毫秒轉_iso(fflogs.現在毫秒()),
    }


def 建立已收錄報告集合(source: dict[str, Any]) -> set[str]:
    report_codes: set[str] = set()
    for record in source.get("records") or []:
        if not isinstance(record, dict):
            continue
        if record.get("fight_scan_mode") != FIGHT_SCAN_MODE:
            continue
        report_code = str(record.get("report_code") or "")
        if report_code:
            report_codes.add(report_code)
    return report_codes


def report_should_skip(
    source: dict[str, Any],
    report_code: str,
    recorded_report_codes: set[str],
    *,
    force: bool = False,
) -> bool:
    if force:
        return False

    checked_reports = source.get("state", {}).get("checked_reports", {})
    checked_report = checked_reports.get(report_code, {}) if isinstance(checked_reports, dict) else {}
    checked_status = checked_report.get("status") if isinstance(checked_report, dict) else None
    if checked_status in COMPLETED_REPORT_STATUSES and checked_report.get("fight_scan_mode") == FIGHT_SCAN_MODE:
        return True

    # 舊資料只掃通關場次，沒有 fight_scan_mode 時不能直接略過；否則新增 wipe 掃描後，
    # 既有 report 內的 wipe 場次會被快取誤擋。新模式完整掃完後才會再次略過。
    return report_code in recorded_report_codes


def fight_should_skip(source: dict[str, Any], fight_key: str, *, force: bool = False) -> bool:
    if force:
        return False

    checked = source.get("state", {}).get("checked_fights", {})
    checked_status = checked.get(fight_key, {}).get("status") if isinstance(checked, dict) else None
    if checked_status in COMPLETED_FIGHT_STATUSES:
        return True

    return any(record.get("fight_key") == fight_key for record in source.get("records") or [])


def 移除既有戰鬥紀錄(source: dict[str, Any], fight_key: str) -> None:
    source["records"] = [record for record in source.get("records") or [] if record.get("fight_key") != fight_key]


def 標記戰鬥已檢查(
    source: dict[str, Any],
    fight_key: str,
    *,
    status: str,
    report_code: str,
    fight: dict[str, Any],
    fan_event_count: int,
    error: str | None = None,
) -> None:
    state = source.setdefault("state", {})
    checked_fights = state.setdefault("checked_fights", {})
    is_kill = 是通關戰鬥(fight)
    checked_fights[fight_key] = {
        "status": status,
        "fight_scan_mode": FIGHT_SCAN_MODE,
        "report_code": report_code,
        "fight_id": fight.get("id"),
        "is_kill": is_kill,
        "fight_status": "kill" if is_kill else "wipe",
        "fan_event_count": fan_event_count,
        "fight_completed_at_iso": fflogs.毫秒轉_iso(
            fflogs.相對戰鬥時間轉實際時間(fight.get("_report_start_time"), fight.get("endTime")),
        ),
        "checked_at_iso": fflogs.毫秒轉_iso(fflogs.現在毫秒()),
        **({"error": error[:500]} if error else {}),
    }


def 標記報告已檢查(
    source: dict[str, Any],
    report: dict[str, Any],
    *,
    status: str,
    fights_seen: int,
    fights_checked: int,
) -> None:
    report_code = str(report.get("code") or "")
    if not report_code:
        return

    # report 層級快取是 FFLogs 配額保護：只要一份 report 的 M2S fight 清單已經掃完，
    # 下次從近期或歷史視窗再次遇到同一 code 時，就能在 detail query 前直接略過。
    state = source.setdefault("state", {})
    checked_reports = state.setdefault("checked_reports", {})
    fan_event_count = sum(
        1
        for record in source.get("records") or []
        if isinstance(record, dict) and record.get("report_code") == report_code
    )
    checked_reports[report_code] = {
        "status": status,
        "fight_scan_mode": FIGHT_SCAN_MODE,
        "report_code": report_code,
        "report_title": report.get("title"),
        "report_start_at": 轉_int(report.get("startTime")),
        "report_start_at_iso": fflogs.毫秒轉_iso(轉_int(report.get("startTime"))),
        "report_end_at": 轉_int(report.get("endTime")),
        "report_end_at_iso": fflogs.毫秒轉_iso(轉_int(report.get("endTime"))),
        "fights_seen": fights_seen,
        "fights_checked": fights_checked,
        "fan_event_count": fan_event_count,
        "checked_at_iso": fflogs.毫秒轉_iso(fflogs.現在毫秒()),
    }


def 查詢報告分頁(
    session: Any,
    auth_pool: Any,
    副本設定: dict[str, Any],
    start_time: int,
    end_time: int,
    *,
    page_limit: int,
    max_pages: int,
) -> tuple[list[dict[str, Any]], bool]:
    reports: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    page = 1
    has_more = False

    while page <= max_pages:
        data = fflogs.執行_graphql(
            session,
            auth_pool,
            RECENT_REPORTS_QUERY,
            {
                "startTime": float(start_time),
                "endTime": float(end_time),
                "page": page,
                "limit": page_limit,
                "zoneID": int(副本設定["zone_id"]),
            },
        )
        response = (((data.get("reportData") or {}).get("reports")) or {})
        for report in response.get("data") or []:
            code = report.get("code")
            region = report.get("region") or {}
            if not code or code in seen_codes:
                continue
            # 繁中服報告目前只能先用 China region 粗篩，再於 deep query 以 actor server 精篩。
            if int(region.get("id") or -1) != CHINA_REGION_ID:
                continue
            seen_codes.add(code)
            reports.append(report)

        has_more = bool(response.get("has_more_pages"))
        if not has_more:
            break
        page += 1

    return reports, has_more


def 查詢報告區間(
    session: Any,
    auth_pool: Any,
    副本設定: dict[str, Any],
    start_time: int,
    end_time: int,
    *,
    page_limit: int,
    max_pages: int,
    min_window_ms: int,
) -> list[dict[str, Any]]:
    reports, has_more = 查詢報告分頁(
        session,
        auth_pool,
        副本設定,
        start_time,
        end_time,
        page_limit=page_limit,
        max_pages=max_pages,
    )
    if not has_more:
        return sorted(reports, key=lambda report: report.get("startTime") or 0)

    if end_time - start_time <= min_window_ms:
        print(
            f"Honey B. Lovely 粉絲榜警告：{fflogs.毫秒轉_iso(start_time)} ~ {fflogs.毫秒轉_iso(end_time)} "
            "仍超過 FFLogs 分頁上限，先處理已取得報告。",
            file=sys.stderr,
        )
        return sorted(reports, key=lambda report: report.get("startTime") or 0)

    middle = start_time + (end_time - start_time) // 2
    left = 查詢報告區間(
        session,
        auth_pool,
        副本設定,
        start_time,
        middle,
        page_limit=page_limit,
        max_pages=max_pages,
        min_window_ms=min_window_ms,
    )
    right = 查詢報告區間(
        session,
        auth_pool,
        副本設定,
        middle + 1,
        end_time,
        page_limit=page_limit,
        max_pages=max_pages,
        min_window_ms=min_window_ms,
    )
    by_code = {report.get("code"): report for report in [*left, *right] if report.get("code")}
    return sorted(by_code.values(), key=lambda report: report.get("startTime") or 0)


def 查詢報告詳情(session: Any, auth_pool: Any, 副本設定: dict[str, Any], report_code: str) -> dict[str, Any] | None:
    data = fflogs.執行_graphql(
        session,
        auth_pool,
        REPORT_DETAIL_QUERY,
        {
            "code": report_code,
            "encounterID": int(副本設定["encounter_id"]),
            "difficulty": int(副本設定["difficulty"]),
        },
    )
    return ((data.get("reportData") or {}).get("report")) or None


def 建立_debuff_events_query(fight_id: int, start_time: float, end_time: float) -> str:
    return f"""
query HoneyDebuffEvents($code: String!) {{
  reportData {{
    report(code: $code) {{
      events(
        dataType: Debuffs,
        fightIDs: [{fight_id}],
        startTime: {start_time},
        endTime: {end_time},
        abilityID: {DEBUFF_ABILITY_ID},
        limit: 10000,
        translate: false
      ) {{
        data
        nextPageTimestamp
      }}
    }}
  }}
}}
"""


def 查詢奴役_events(session: Any, auth_pool: Any, report_code: str, fight: dict[str, Any]) -> list[dict[str, Any]]:
    fight_id = 轉_int(fight.get("id"))
    start_time = 轉_float(fight.get("startTime"))
    end_time = 轉_float(fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        return []

    all_events: list[dict[str, Any]] = []
    next_start = start_time
    while next_start < end_time:
        data = fflogs.執行_graphql(
            session,
            auth_pool,
            建立_debuff_events_query(fight_id, next_start, end_time),
            {"code": report_code},
        )
        events_response = (((data.get("reportData") or {}).get("report") or {}).get("events") or {})
        events = [event for event in events_response.get("data") or [] if isinstance(event, dict)]
        all_events.extend(events)
        next_page = 轉_float(events_response.get("nextPageTimestamp"))
        if next_page is None or next_page <= next_start:
            break
        next_start = next_page

    return all_events


def 建立粉絲紀錄(
    *,
    report: dict[str, Any],
    fight: dict[str, Any],
    actor: dict[str, Any],
    event: dict[str, Any],
    collected_at_iso: str,
) -> dict[str, Any] | None:
    report_code = str(report.get("code") or "")
    fight_id = 轉_int(fight.get("id"))
    target_id = 轉_int(event.get("targetID"))
    event_timestamp = 轉_int(event.get("timestamp"))
    if not report_code or fight_id is None or target_id is None or event_timestamp is None:
        return None

    fight_start_at, fight_start_at_iso = 時間加總_iso(report.get("startTime"), fight.get("startTime"))
    fight_completed_at, fight_completed_at_iso = 時間加總_iso(report.get("startTime"), fight.get("endTime"))
    event_at, event_at_iso = 時間加總_iso(report.get("startTime"), event_timestamp)
    fight_duration_ms = 轉_float(fight.get("combatTime"))
    is_kill = 是通關戰鬥(fight)
    fight_start_relative = 轉_float(fight.get("startTime"))
    seconds_from_pull = None
    if fight_start_relative is not None:
        seconds_from_pull = round((float(event_timestamp) - fight_start_relative) / 1000, 3)

    return {
        "id": 紀錄鍵(report_code, fight_id, target_id, event_timestamp),
        "fight_key": 戰鬥鍵(report_code, fight_id),
        "report_code": report_code,
        "report_title": report.get("title"),
        "report_url": f"https://www.fflogs.com/reports/{report_code}",
        "fight_id": fight_id,
        "fight_name": fight.get("name") or "Honey B. Lovely",
        "fight_start_at": fight_start_at,
        "fight_start_at_iso": fight_start_at_iso,
        "fight_completed_at": fight_completed_at,
        "fight_completed_at_iso": fight_completed_at_iso,
        "is_kill": is_kill,
        "fight_status": "kill" if is_kill else "wipe",
        "fight_status_label": "通關" if is_kill else "滅團",
        "fight_duration_ms": int(fight_duration_ms) if fight_duration_ms is not None else None,
        "fight_duration_seconds": round(fight_duration_ms / 1000, 3) if fight_duration_ms is not None else None,
        "clear_time_ms": int(fight_duration_ms) if is_kill and fight_duration_ms is not None else None,
        "clear_time_seconds": round(fight_duration_ms / 1000, 3) if is_kill and fight_duration_ms is not None else None,
        "event_at": event_at,
        "event_at_iso": event_at_iso,
        "seconds_from_pull": seconds_from_pull,
        "fflogs_actor_id": target_id,
        "character_name": actor.get("name"),
        "server": actor.get("server"),
        "job": actor.get("subType"),
        "debuff_ability_id": DEBUFF_ABILITY_ID,
        "debuff_name": DEBUFF_NAME,
        "fight_scan_mode": FIGHT_SCAN_MODE,
        "collected_at_iso": collected_at_iso,
    }


def 處理戰鬥(
    session: Any,
    auth_pool: Any,
    source: dict[str, Any],
    report: dict[str, Any],
    fight: dict[str, Any],
    actors: dict[int, dict[str, Any]],
    *,
    force: bool = False,
) -> int:
    report_code = str(report.get("code") or "")
    fight_id = 轉_int(fight.get("id"))
    if not report_code or fight_id is None:
        return 0

    fight_key = 戰鬥鍵(report_code, fight_id)
    if fight_should_skip(source, fight_key, force=force):
        return 0

    if force:
        移除既有戰鬥紀錄(source, fight_key)

    fight["_report_start_time"] = report.get("startTime")
    friendly_ids = {轉_int(actor_id) for actor_id in fight.get("friendlyPlayers") or []}
    tc_friendly_ids = {actor_id for actor_id in friendly_ids if actor_id is not None and 是繁中服玩家(actors.get(actor_id))}
    if not tc_friendly_ids:
        標記戰鬥已檢查(
            source,
            fight_key,
            status="skipped_no_tc_players",
            report_code=report_code,
            fight=fight,
            fan_event_count=0,
        )
        return 1

    try:
        events = 查詢奴役_events(session, auth_pool, report_code, fight)
    except Exception as error:  # noqa: BLE001
        標記戰鬥已檢查(
            source,
            fight_key,
            status="error",
            report_code=report_code,
            fight=fight,
            fan_event_count=0,
            error=str(error),
        )
        raise

    collected_at_iso = fflogs.毫秒轉_iso(fflogs.現在毫秒()) or ""
    existing_ids = {record.get("id") for record in source.get("records") or []}
    added_count = 0
    for event in events:
        if event.get("type") != "applydebuff":
            continue
        target_id = 轉_int(event.get("targetID"))
        actor = actors.get(target_id) if target_id is not None else None
        if not 是繁中服玩家(actor):
            continue
        record = 建立粉絲紀錄(report=report, fight=fight, actor=actor, event=event, collected_at_iso=collected_at_iso)
        if not record or record["id"] in existing_ids:
            continue
        source.setdefault("records", []).append(record)
        existing_ids.add(record["id"])
        added_count += 1

    標記戰鬥已檢查(
        source,
        fight_key,
        status="checked",
        report_code=report_code,
        fight=fight,
        fan_event_count=added_count,
    )
    return 1


def 處理報告列表(
    session: Any,
    auth_pool: Any,
    source: dict[str, Any],
    reports: list[dict[str, Any]],
    副本設定: dict[str, Any],
    *,
    unrecorded_limit: int | None = None,
    force: bool = False,
) -> dict[str, int]:
    summary = {
        "reports_seen": len(reports),
        "reports_skipped_already_recorded": 0,
        "reports_with_m2s_fights": 0,
        "fights_checked": 0,
        "fan_records_before": len(source.get("records") or []),
        "fan_records_after": 0,
    }
    recorded_report_codes = 建立已收錄報告集合(source)

    for shallow_report in reports:
        if unrecorded_limit is not None and summary["fights_checked"] >= unrecorded_limit:
            break

        report_code = str(shallow_report.get("code") or "")
        if not report_code:
            continue
        if report_should_skip(source, report_code, recorded_report_codes, force=force):
            summary["reports_skipped_already_recorded"] += 1
            continue

        try:
            report = 查詢報告詳情(session, auth_pool, 副本設定, report_code)
        except Exception as error:  # noqa: BLE001
            報告已失敗(source, report_code, error)
            print(f"{report_code} 報告詳情查詢失敗：{error}", file=sys.stderr)
            continue

        if not report:
            continue

        report.setdefault("code", report_code)
        report.setdefault("title", shallow_report.get("title"))
        report.setdefault("startTime", shallow_report.get("startTime"))
        report.setdefault("endTime", shallow_report.get("endTime"))

        fights = [fight for fight in report.get("fights") or [] if isinstance(fight, dict)]
        if not fights:
            標記報告已檢查(
                source,
                report,
                status="skipped_no_m2s_fights",
                fights_seen=0,
                fights_checked=0,
            )
            continue
        summary["reports_with_m2s_fights"] += 1

        master_data = report.get("masterData") or {}
        actors = 建立角色索引([actor for actor in master_data.get("actors") or [] if isinstance(actor, dict)])

        report_completed = True
        report_fights_checked = 0
        for fight in fights:
            if unrecorded_limit is not None and summary["fights_checked"] >= unrecorded_limit:
                report_completed = False
                break
            before = summary["fights_checked"]
            try:
                checked_delta = 處理戰鬥(session, auth_pool, source, report, fight, actors, force=force)
            except Exception as error:  # noqa: BLE001
                print(f"{report_code}:{fight.get('id')} 戰鬥查詢失敗，保留待下次重試：{error}", file=sys.stderr)
                checked_delta = 0
                report_completed = False
            summary["fights_checked"] += checked_delta
            report_fights_checked += checked_delta
            if checked_delta and summary["fights_checked"] != before:
                print(
                    f"Honey B. Lovely 粉絲榜已檢查 {report_code}:{fight.get('id')}，"
                    f"目前本段新增檢查 {summary['fights_checked']} 場。",
                )

        if report_completed:
            標記報告已檢查(
                source,
                report,
                status="checked",
                fights_seen=len(fights),
                fights_checked=report_fights_checked,
            )
            recorded_report_codes.add(report_code)

    summary["fan_records_after"] = len(source.get("records") or [])
    return summary


def 掃描區間報告(
    session: Any,
    auth_pool: Any,
    副本設定: dict[str, Any],
    start_time: int,
    end_time: int,
    *,
    window_hours: int,
) -> list[dict[str, Any]]:
    config = fflogs.讀取FFLogs執行設定()
    page_limit = max(int(config.get("report_page_limit") or 100), 1)
    max_pages = max(int(config.get("report_max_pages") or 25), 1)
    min_window_ms = max(int(config.get("min_scan_window_seconds") or 60), 1) * 1000
    window_ms = max(window_hours, 1) * 60 * 60 * 1000
    report_index: dict[str, dict[str, Any]] = {}
    cursor = start_time

    while cursor < end_time:
        window_end = min(cursor + window_ms - 1, end_time)
        print(f"Honey B. Lovely 粉絲榜掃描區間：{fflogs.毫秒轉_iso(cursor)} ~ {fflogs.毫秒轉_iso(window_end)}")
        reports = 查詢報告區間(
            session,
            auth_pool,
            副本設定,
            cursor,
            window_end,
            page_limit=page_limit,
            max_pages=max_pages,
            min_window_ms=min_window_ms,
        )
        for report in reports:
            code = report.get("code")
            if code:
                report_index[code] = report
        cursor = window_end + 1

    return sorted(report_index.values(), key=lambda report: report.get("startTime") or 0)


def 執行近期掃描(
    session: Any,
    auth_pool: Any,
    source: dict[str, Any],
    副本設定: dict[str, Any],
    *,
    recent_days: int,
    window_hours: int,
    force: bool,
) -> dict[str, int]:
    end_time = fflogs.現在毫秒()
    start_time = end_time - max(recent_days, 1) * 24 * 60 * 60 * 1000
    reports = 掃描區間報告(session, auth_pool, 副本設定, start_time, end_time, window_hours=window_hours)
    summary = 處理報告列表(session, auth_pool, source, reports, 副本設定, force=force)
    source.setdefault("state", {})["recent_last_scanned_at"] = end_time
    source.setdefault("state", {})["recent_last_scanned_at_iso"] = fflogs.毫秒轉_iso(end_time)
    return summary


def 讀取歷史游標(source: dict[str, Any], 副本設定: dict[str, Any]) -> int:
    state = source.setdefault("state", {})
    cursor = 轉_int(state.get("history_cursor_at"))
    if cursor is not None:
        return cursor

    scan_start_date = str(副本設定.get("scan_start_date") or "2026-02-01")
    start_at = fflogs.解析日期時間為毫秒(scan_start_date)
    if start_at is None:
        raise RuntimeError(f"{ENCOUNTER_KEY} scan_start_date 無法解析：{scan_start_date}")
    state["history_cursor_at"] = start_at
    state["history_cursor_at_iso"] = fflogs.毫秒轉_iso(start_at)
    return start_at


def 執行歷史掃描(
    session: Any,
    auth_pool: Any,
    source: dict[str, Any],
    副本設定: dict[str, Any],
    *,
    history_limit: int,
    window_hours: int,
    force: bool,
) -> dict[str, int]:
    state = source.setdefault("state", {})
    end_time = fflogs.現在毫秒()
    cursor = 讀取歷史游標(source, 副本設定)
    window_ms = max(window_hours, 1) * 60 * 60 * 1000
    total_summary = {
        "reports_seen": 0,
        "reports_skipped_already_recorded": 0,
        "reports_with_m2s_fights": 0,
        "fights_checked": 0,
        "fan_records_before": len(source.get("records") or []),
        "fan_records_after": 0,
    }

    while cursor < end_time and total_summary["fights_checked"] < history_limit:
        window_end = min(cursor + window_ms - 1, end_time)
        reports = 掃描區間報告(session, auth_pool, 副本設定, cursor, window_end, window_hours=window_hours)
        remaining = history_limit - total_summary["fights_checked"]
        summary = 處理報告列表(
            session,
            auth_pool,
            source,
            reports,
            副本設定,
            unrecorded_limit=remaining,
            force=force,
        )
        for key in (
            "reports_seen",
            "reports_skipped_already_recorded",
            "reports_with_m2s_fights",
            "fights_checked",
        ):
            total_summary[key] += summary[key]

        if summary["fights_checked"] >= remaining:
            # 若本段撞到上限，游標停在同一區間開頭；下次會重掃這段並跳過已完成戰鬥，
            # 避免同一時間窗內尚未處理的報告被跳過。
            break

        cursor = window_end + 1
        state["history_cursor_at"] = cursor
        state["history_cursor_at_iso"] = fflogs.毫秒轉_iso(cursor)

    total_summary["fan_records_after"] = len(source.get("records") or [])
    state["history_last_scanned_at"] = end_time
    state["history_last_scanned_at_iso"] = fflogs.毫秒轉_iso(end_time)
    return total_summary


def 建立戰鬥公開紀錄(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fight_index: dict[str, dict[str, Any]] = {}
    for record in records:
        fight_key = record.get("fight_key")
        if not fight_key:
            continue
        # 同一場戰鬥可能被多位隊友上傳成不同 FFLogs report。這些 report 的 fight_id
        # 與 fight_name 可能不同；最新收錄紀錄應呈現「實際戰鬥」而不是「report
        # 上傳份數」，因此用戰鬥時間軸做公開列表去重。
        public_fight_key = 公開戰鬥去重鍵(record)
        fight = fight_index.setdefault(
            public_fight_key,
            {
                "id": fight_key,
                "report_code": record.get("report_code"),
                "report_title": record.get("report_title"),
                "report_url": record.get("report_url"),
                "fight_id": record.get("fight_id"),
                "fight_name": record.get("fight_name"),
                "fight_completed_at_iso": record.get("fight_completed_at_iso"),
                "is_kill": 紀錄戰鬥狀態(record) == "kill",
                "fight_status": 紀錄戰鬥狀態(record),
                "fight_status_label": 紀錄戰鬥狀態標籤(record),
                "fight_duration_seconds": record.get("fight_duration_seconds") or record.get("clear_time_seconds"),
                "clear_time_seconds": record.get("clear_time_seconds"),
                "fan_event_count": 0,
                "fans": [],
                "source_reports": [],
                "_fan_keys": set(),
                "_source_report_codes": set(),
            },
        )
        report_code = record.get("report_code")
        if report_code and report_code not in fight["_source_report_codes"]:
            fight["_source_report_codes"].add(report_code)
            fight["source_reports"].append(
                {
                    "report_code": report_code,
                    "report_title": record.get("report_title"),
                    "report_url": record.get("report_url"),
                    "fight_id": record.get("fight_id"),
                    "is_kill": 紀錄戰鬥狀態(record) == "kill",
                    "fight_status": 紀錄戰鬥狀態(record),
                },
            )

        fan_key = (
            record.get("character_name"),
            record.get("server"),
            record.get("job"),
            record.get("event_at_iso"),
            record.get("seconds_from_pull"),
        )
        if fan_key in fight["_fan_keys"]:
            continue

        fight["_fan_keys"].add(fan_key)
        fight["fan_event_count"] += 1
        fight["fans"].append(
            {
                "character_name": record.get("character_name"),
                "server": record.get("server"),
                "job": record.get("job"),
                "event_at_iso": record.get("event_at_iso"),
                "seconds_from_pull": record.get("seconds_from_pull"),
            },
        )

    for fight in fight_index.values():
        fight["fans"].sort(key=lambda fan: (fan.get("seconds_from_pull") is None, fan.get("seconds_from_pull") or 0))
        fight["source_reports"].sort(key=lambda report: report.get("report_code") or "")
        fight["duplicate_report_count"] = max(0, len(fight["source_reports"]) - 1)
        del fight["_fan_keys"]
        del fight["_source_report_codes"]

    return sorted(
        fight_index.values(),
        key=lambda fight: fight.get("fight_completed_at_iso") or "",
        reverse=True,
    )


def 建立粉絲公開排行(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fan_index: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record.get("character_name") or not record.get("server"):
            continue
        key = 角色鍵(record)
        if record.get("fight_key"):
            fight_key = record["fight_key"]
        elif record.get("report_code") and record.get("fight_id") is not None:
            fight_key = f"{record.get('report_code')}:{record.get('fight_id')}"
        else:
            fight_key = record.get("id")
        fan = fan_index.setdefault(
            key,
            {
                "id": key,
                "character_name": record.get("character_name"),
                "server": record.get("server"),
                "total_event_count": 0,
                "fight_count": 0,
                "jobs": Counter(),
                "first_recorded_at_iso": record.get("fight_completed_at_iso"),
                "latest_recorded_at_iso": record.get("fight_completed_at_iso"),
                "first_collected_at_iso": record.get("collected_at_iso"),
                "latest_collected_at_iso": record.get("collected_at_iso"),
                "latest_report_url": record.get("report_url"),
                "latest_fight_name": record.get("fight_name"),
                "_fight_keys": set(),
                "_records_by_fight": {},
            },
        )
        fan["total_event_count"] += 1
        fan["_fight_keys"].add(fight_key)
        fan["jobs"][record.get("job") or "Unknown"] += 1
        # 同一位粉絲可能在不同 FFLogs 戰鬥內多次吃到第 4 顆愛心；公開資料保留
        # fight 粒度的歷史列表，讓前端彈窗能追溯來源報告，而不用重新掃描扁平 records。
        fan_record = fan["_records_by_fight"].setdefault(
            fight_key,
            {
                "id": fight_key,
                "report_code": record.get("report_code"),
                "report_title": record.get("report_title"),
                "report_url": record.get("report_url"),
                "fight_id": record.get("fight_id"),
                "fight_name": record.get("fight_name"),
                "fight_completed_at_iso": record.get("fight_completed_at_iso"),
                "is_kill": 紀錄戰鬥狀態(record) == "kill",
                "fight_status": 紀錄戰鬥狀態(record),
                "fight_status_label": 紀錄戰鬥狀態標籤(record),
                "fight_duration_seconds": record.get("fight_duration_seconds") or record.get("clear_time_seconds"),
                "clear_time_seconds": record.get("clear_time_seconds"),
                "job": record.get("job"),
                "event_count": 0,
                "first_event_at_iso": record.get("event_at_iso"),
                "latest_event_at_iso": record.get("event_at_iso"),
                "seconds_from_pull": record.get("seconds_from_pull"),
                "collected_at_iso": record.get("collected_at_iso"),
            },
        )
        fan_record["event_count"] += 1
        if (record.get("event_at_iso") or "") < (fan_record.get("first_event_at_iso") or "9999"):
            fan_record["first_event_at_iso"] = record.get("event_at_iso")
        if (record.get("event_at_iso") or "") > (fan_record.get("latest_event_at_iso") or ""):
            fan_record["latest_event_at_iso"] = record.get("event_at_iso")
            fan_record["seconds_from_pull"] = record.get("seconds_from_pull")
            fan_record["job"] = record.get("job")
        if (record.get("collected_at_iso") or "") > (fan_record.get("collected_at_iso") or ""):
            fan_record["collected_at_iso"] = record.get("collected_at_iso")
        if (record.get("fight_completed_at_iso") or "") < (fan.get("first_recorded_at_iso") or "9999"):
            fan["first_recorded_at_iso"] = record.get("fight_completed_at_iso")
        if (record.get("fight_completed_at_iso") or "") > (fan.get("latest_recorded_at_iso") or ""):
            fan["latest_recorded_at_iso"] = record.get("fight_completed_at_iso")
            fan["latest_report_url"] = record.get("report_url")
            fan["latest_fight_name"] = record.get("fight_name")
        if (record.get("collected_at_iso") or "") < (fan.get("first_collected_at_iso") or "9999"):
            fan["first_collected_at_iso"] = record.get("collected_at_iso")
        if (record.get("collected_at_iso") or "") > (fan.get("latest_collected_at_iso") or ""):
            fan["latest_collected_at_iso"] = record.get("collected_at_iso")

    fans: list[dict[str, Any]] = []
    for fan in fan_index.values():
        job_counts = [{"job": job, "count": count} for job, count in fan["jobs"].most_common()]
        fan_records = sorted(
            fan["_records_by_fight"].values(),
            key=lambda item: (
                item.get("fight_completed_at_iso") or "",
                item.get("latest_event_at_iso") or "",
                item.get("id") or "",
            ),
            reverse=True,
        )
        fans.append(
            {
                "id": fan["id"],
                "character_name": fan["character_name"],
                "server": fan["server"],
                "total_event_count": fan["total_event_count"],
                "fight_count": len(fan["_fight_keys"]),
                "jobs": job_counts,
                "main_job": job_counts[0]["job"] if job_counts else None,
                "first_recorded_at_iso": fan["first_recorded_at_iso"],
                "latest_recorded_at_iso": fan["latest_recorded_at_iso"],
                "first_collected_at_iso": fan["first_collected_at_iso"],
                "latest_collected_at_iso": fan["latest_collected_at_iso"],
                "latest_report_url": fan["latest_report_url"],
                "latest_fight_name": fan["latest_fight_name"],
                "records": fan_records,
            },
        )

    return sorted(
        fans,
        key=lambda fan: (
            fan.get("total_event_count") or 0,
            fan.get("latest_recorded_at_iso") or "",
            fan.get("character_name") or "",
            fan.get("server") or "",
        ),
        reverse=True,
    )


def 建立公開資料(source: dict[str, Any]) -> dict[str, Any]:
    seen_ids: set[str] = set()
    records: list[dict[str, Any]] = []
    for record in source.get("records") or []:
        if not isinstance(record, dict) or not record.get("id") or record["id"] in seen_ids:
            continue
        seen_ids.add(record["id"])
        records.append(record)

    records.sort(key=lambda record: (record.get("fight_completed_at_iso") or "", record.get("event_at_iso") or ""), reverse=True)
    top_fans = 建立粉絲公開排行(records)
    latest_records = 建立戰鬥公開紀錄(records)
    kill_event_count = sum(1 for record in records if 紀錄戰鬥狀態(record) == "kill")
    wipe_event_count = len(records) - kill_event_count
    kill_fight_count = sum(1 for record in latest_records if record.get("fight_status") == "kill")
    wipe_fight_count = len(latest_records) - kill_fight_count
    latest_fans = sorted(
        top_fans,
        key=lambda fan: (
            fan.get("first_collected_at_iso") or "",
            fan.get("latest_recorded_at_iso") or "",
        ),
        reverse=True,
    )
    generated_at_iso = source.get("updated_at_iso") or source.get("created_at_iso") or "1970-01-01T00:00:00+00:00"

    return {
        "schema_version": 1,
        "feature": FEATURE_KEY,
        "generated_at_iso": generated_at_iso,
        "source_updated_at_iso": source.get("updated_at_iso"),
        "source_encounter": source.get("source_encounter") or {},
        "target_debuff": source.get("target_debuff") or {},
        "summary": {
            "total_event_count": len(records),
            "kill_event_count": kill_event_count,
            "wipe_event_count": wipe_event_count,
            "fan_count": len(top_fans),
            "fight_count": len(latest_records),
            "kill_fight_count": kill_fight_count,
            "wipe_fight_count": wipe_fight_count,
            "top_fan_name": top_fans[0]["character_name"] if top_fans else None,
            "top_fan_server": top_fans[0]["server"] if top_fans else None,
            "top_fan_event_count": top_fans[0]["total_event_count"] if top_fans else 0,
            "latest_recorded_at_iso": records[0].get("fight_completed_at_iso") if records else None,
            "latest_collected_at_iso": max((record.get("collected_at_iso") or "" for record in records), default=None),
        },
        "top_fans": top_fans[:100],
        "latest_records": latest_records[:100],
        "latest_fans": latest_fans[:100],
        "records": records[:500],
    }


def 建立_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="抓取 Honey B. Lovely 粉絲榜趣味資料。")
    parser.add_argument("--rebuild-public", action="store_true", help="只由 data/fun 來源檔重建 public/data/fun，不呼叫 FFLogs API。")
    parser.add_argument("--dry-run", action="store_true", help="執行查詢與聚合但不寫入檔案。")
    parser.add_argument("--skip-recent", action="store_true", help="略過近三天掃描。")
    parser.add_argument("--skip-history", action="store_true", help="略過歷史游標掃描。")
    parser.add_argument("--force", action="store_true", help="重新檢查已完成狀態的戰鬥，會覆蓋該戰鬥既有粉絲紀錄。")
    parser.add_argument("--recent-days", type=int, default=DEFAULT_RECENT_DAYS, help="近期掃描回看天數，預設 3。")
    parser.add_argument("--history-limit", type=int, default=DEFAULT_HISTORY_LIMIT, help="每輪歷史掃描最多檢查的未記錄戰鬥數，預設 200。")
    parser.add_argument("--recent-window-hours", type=int, default=DEFAULT_SCAN_WINDOW_HOURS, help="近期掃描的 FFLogs 查詢切窗小時數。")
    parser.add_argument("--history-window-hours", type=int, default=DEFAULT_SCAN_WINDOW_HOURS, help="歷史掃描的 FFLogs 查詢切窗小時數。")
    return parser


def main() -> None:
    args = 建立_arg_parser().parse_args()
    副本設定 = 讀取副本設定()
    source = 讀取來源(副本設定)

    if args.rebuild_public:
        寫入來源與公開檔(source, dry_run=args.dry_run)
        print(f"已重建 Honey B. Lovely 粉絲榜公開資料：{PUBLIC_PATH.relative_to(PROJECT_ROOT)}")
        return

    session = fflogs.requests.Session()
    auth_pool = fflogs.FFLogs認證池(session, fflogs.讀取認證設定())
    now_iso = fflogs.毫秒轉_iso(fflogs.現在毫秒())
    source["created_at_iso"] = source.get("created_at_iso") or now_iso

    run_summary: dict[str, Any] = {
        "started_at_iso": now_iso,
        "recent": None,
        "history": None,
    }

    if not args.skip_recent:
        run_summary["recent"] = 執行近期掃描(
            session,
            auth_pool,
            source,
            副本設定,
            recent_days=args.recent_days,
            window_hours=args.recent_window_hours,
            force=args.force,
        )

    if not args.skip_history and args.history_limit > 0:
        source.setdefault("state", {})["history_max_unrecorded_fights_per_run"] = args.history_limit
        run_summary["history"] = 執行歷史掃描(
            session,
            auth_pool,
            source,
            副本設定,
            history_limit=args.history_limit,
            window_hours=args.history_window_hours,
            force=args.force,
        )

    finished_at = fflogs.現在毫秒()
    source["updated_at_iso"] = fflogs.毫秒轉_iso(finished_at)
    run_summary["finished_at_iso"] = source["updated_at_iso"]
    run_summary["total_records"] = len(source.get("records") or [])
    source.setdefault("state", {})["last_run"] = run_summary

    寫入來源與公開檔(source, dry_run=args.dry_run)
    print(
        "Honey B. Lovely 粉絲榜完成："
        f"目前收錄 {len(source.get('records') or [])} 筆奴役紀錄，"
        f"公開資料輸出至 {PUBLIC_PATH.relative_to(PROJECT_ROOT)}。"
    )


if __name__ == "__main__":
    main()
