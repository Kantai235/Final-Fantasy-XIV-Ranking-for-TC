from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402
from fflogs_pipeline import support_metrics  # noqa: E402


# 這支腳本只補齊既有 data/rankings 中缺少的新欄位或 FFLogs raw 片段。
# 為了避免主爬蟲與補抓腳本出現兩套解析規則，所有 FFLogs 查詢、排行榜寫入與狀態標記都沿用 fetch_fflogs.py。
# getattr 使用 unicode 名稱是為了讓本檔保持英文檔名與工具友善，同時仍可呼叫主腳本的繁中函式。
read_json = getattr(fflogs, "\u8b80\u53d6_json")
ranking_path = getattr(fflogs, "\u6392\u884c\u699c\u6a94\u6848\u8def\u5f91")
normalize_ranking = getattr(fflogs, "\u6b63\u898f\u5316\u6392\u884c\u699c")
load_ranking_file = getattr(fflogs, "\u8b80\u53d6\u6392\u884c\u699c\u6a94\u6848")
build_report_score = getattr(fflogs, "\u5efa\u7acb\u5831\u544a\u6210\u7e3e")
apply_scores_to_ranking = getattr(fflogs, "\u5957\u7528\u6210\u7e3e\u5230\u6392\u884c\u699c")
write_ranking_file = getattr(fflogs, "\u5beb\u5165\u6392\u884c\u699c\u6a94\u6848")
mark_ranking_report_hidden = getattr(fflogs, "\u6a19\u8a18\u6392\u884c\u699c\u5831\u544a\u96b1\u85cf")
read_credentials = getattr(fflogs, "\u8b80\u53d6\u8a8d\u8b49\u8a2d\u5b9a")
auth_pool_class = getattr(fflogs, "FFLogs\u8a8d\u8b49\u6c60")
report_has_tc_players = getattr(fflogs, "\u5831\u544a\u662f\u5426\u5305\u542b\u7e41\u4e2d\u670d\u73a9\u5bb6")
calculate_damage_time_info = getattr(fflogs, "\u8a08\u7b97\u50b7\u5bb3\u6642\u9593\u8cc7\u8a0a")
milliseconds_to_seconds = getattr(fflogs, "\u6beb\u79d2\u8f49\u79d2\u6578")
load_state_file = getattr(fflogs, "\u8b80\u53d6\u72c0\u614b\u6a94\u6848")
write_state_file = getattr(fflogs, "\u5beb\u5165\u72c0\u614b\u6a94\u6848")
mark_report_status = getattr(fflogs, "\u6a19\u8a18\u5831\u544a\u8655\u7406\u72c0\u614b")
report_access_error_class = getattr(fflogs, "FFLogs\u5831\u544a\u5b58\u53d6\u932f\u8aa4")
hidden_reason_inaccessible = getattr(fflogs, "\u5831\u544a\u7121\u6cd5\u5b58\u53d6\u96b1\u85cf\u539f\u56e0")


MIN_REASONABLE_EPOCH_MS = 946684800000
SKIPPED_INACCESSIBLE_STATUS = "skipped_inaccessible"
SUPPORT_METRICS_REPORT_BACKFILL_STATE_KEY = "support_metrics_report_backfill"
DEFAULT_SUPPORT_METRICS_CUTOFF_ISO = "2026-07-28T05:00:00Z"


@dataclass
class BackfillCandidate:
    report_code: str
    sort_time: float = 0
    encounter_keys: set[str] = field(default_factory=set)
    reports_by_key: dict[str, dict[str, Any]] = field(default_factory=dict)
    need_fight_count: int = 0


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def first_number(*values: Any) -> float | None:
    for value in values:
        number = to_number(value)
        if number is not None:
            return number
    return None


def fight_absolute_time(report_start_time: float | None, value: Any) -> float | None:
    number = to_number(value)
    if number is None:
        return None
    if number >= MIN_REASONABLE_EPOCH_MS:
        return number
    if report_start_time is not None:
        return report_start_time + number
    return None


def fight_time_values(report: dict[str, Any], fight: dict[str, Any]) -> list[float]:
    report_start_time = first_number(report.get("report_start_time"), report.get("startTime"))
    values = [
        first_number(fight.get("recorded_at"), fight.get("recordedAt")),
        fight_absolute_time(report_start_time, first_number(fight.get("end_time"), fight.get("endTime"))),
        fight_absolute_time(report_start_time, first_number(fight.get("start_time"), fight.get("startTime"))),
    ]
    return [value for value in values if value is not None]


def load_all_encounters() -> dict[str, dict[str, Any]]:
    raw = read_json(PROJECT_ROOT / "config" / "encounters.json", [])
    if not isinstance(raw, list):
        raise RuntimeError("config/encounters.json must be a list.")

    encounters: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue

        key = item.get("key")
        if not key or not item.get("name"):
            continue
        if item.get("zone_id") is None or item.get("encounter_id") is None or item.get("difficulty") is None:
            continue

        encounter = dict(item)
        encounter["zone_id"] = int(encounter["zone_id"])
        encounter["encounter_id"] = int(encounter["encounter_id"])
        encounter["difficulty"] = int(encounter["difficulty"])
        encounters[str(key)] = encounter

    return encounters


def fight_recorded_time(report: dict[str, Any], fight: dict[str, Any]) -> float | None:
    """取得 fight 的絕對開始時間，供歷史回補切點判斷使用。

    舊分片可能只有 report-relative ``start_time``，新分片則通常已有絕對
    ``recorded_at``。兩種格式都必須支援，否則 7.2 開放前後的既有資料會被漏掉。
    """

    recorded_at = first_number(fight.get("recorded_at"), fight.get("recordedAt"))
    if recorded_at is not None and recorded_at >= MIN_REASONABLE_EPOCH_MS:
        return recorded_at

    report_start_time = first_number(report.get("report_start_time"), report.get("startTime"))
    return fight_absolute_time(
        report_start_time,
        first_number(fight.get("start_time"), fight.get("startTime")),
    )


def parse_iso_timestamp(value: str) -> float:
    """將命令列 ISO 8601 時間轉成毫秒；未帶時區時採 UTC，避免依電腦時區漂移。"""

    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"無法解析 ISO 8601 時間：{value}") from error
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp() * 1000


def support_metrics_are_current(fight: dict[str, Any]) -> bool:
    """確認 fight 與其中坦補玩家皆已使用目前的支援統計／減傷規則版本。"""

    summary = fight.get("support_metrics_summary")
    if not isinstance(summary, dict):
        return False
    if summary.get("calculation_version") != support_metrics.支援統計計算版本:
        return False
    if summary.get("mitigation_rules_version") != support_metrics.坦克減傷規則版本:
        return False

    players = fight.get("players")
    if not isinstance(players, list):
        return False

    for player in players:
        if not isinstance(player, dict):
            continue
        job = player.get("job")
        if job in support_metrics.補師職業:
            healing_stats = player.get("healing_stats")
            if not isinstance(healing_stats, dict):
                return False
            if healing_stats.get("calculation_version") != support_metrics.支援統計計算版本:
                return False
        elif job in support_metrics.坦克職業:
            tank_stats = player.get("tank_stats")
            if not isinstance(tank_stats, dict):
                return False
            if tank_stats.get("calculation_version") != support_metrics.支援統計計算版本:
                return False
            coverage = tank_stats.get("mitigation_coverage")
            if not isinstance(coverage, dict):
                return False
            if coverage.get("rules_version") != support_metrics.坦克減傷規則版本:
                return False
    return True


def fight_needs_support_metrics(
    report: dict[str, Any],
    fight: dict[str, Any],
    since_ms: float,
    until_ms: float,
) -> bool:
    recorded_at = fight_recorded_time(report, fight)
    if recorded_at is None or recorded_at < since_ms or recorded_at > until_ms:
        return False
    return not support_metrics_are_current(fight)


def report_support_metrics_sort_time(
    report: dict[str, Any],
    since_ms: float,
    until_ms: float,
) -> float:
    """以實際待補 fight 排序，避免跨切點 report 被其它時間的 fight 推錯游標。"""

    return max(
        (
            fight_recorded_time(report, fight) or 0
            for fight in report.get("fights") or []
            if isinstance(fight, dict) and fight_needs_support_metrics(report, fight, since_ms, until_ms)
        ),
        default=0,
    )


def fight_needs_backfill(fight: dict[str, Any]) -> bool:
    # compact report 不再保存 fflogs_raw.damage_done，因此補抓條件只能看建置層真正需要的欄位。
    # players 是個人成績單、隊友統計與排行榜去重的來源；damage_time_ms 則是 rDPS/aDPS 分母脈絡。
    players = fight.get("players")
    has_rankable_players = isinstance(players, list) and any(
        isinstance(player, dict)
        and player.get("server")
        and player.get("job")
        and player.get("dps") is not None
        for player in players
    )
    return (
        fight.get("clear_time_ms") is None
        or fight.get("damage_time_ms") is None
        or not has_rankable_players
    )


def report_needs_backfill(
    report: dict[str, Any],
    *,
    support_metrics_since_ms: float | None = None,
    support_metrics_until_ms: float | None = None,
) -> tuple[bool, int]:
    # raw metadata 已不再是資料契約的一部分；只要 report/fight/player 足以重建 public/data，
    # 就不應把它送回 FFLogs 補抓，否則 backfill 會把大型 raw 欄位重新寫進 repo。
    fights = report.get("fights")
    if support_metrics_since_ms is not None:
        until_ms = support_metrics_until_ms if support_metrics_until_ms is not None else time.time() * 1000
        if not isinstance(fights, list) or not fights:
            return False, 0
        need_fights = sum(
            1
            for fight in fights
            if isinstance(fight, dict)
            and fight_needs_support_metrics(report, fight, support_metrics_since_ms, until_ms)
        )
        return need_fights > 0, need_fights

    needs_report_metadata = report.get("report_start_time") is None or report.get("report_end_time") is None
    if not isinstance(fights, list) or not fights:
        return True, 0

    need_fights = 0
    for fight in fights:
        if isinstance(fight, dict) and fight_needs_backfill(fight):
            need_fights += 1

    return needs_report_metadata or need_fights > 0, need_fights


def locally_fill_damage_time_fields(report: dict[str, Any]) -> int:
    # 舊資料若仍保有 raw damageDone，可先在本機補衍生欄位，不浪費 FFLogs API 配額。
    # compact report 不再保存 raw；沒有 raw 且缺必要欄位時，後續才會進入 API backfill。
    changed = 0
    for fight in report.get("fights") or []:
        if not isinstance(fight, dict):
            continue

        raw = fight.get("fflogs_raw") if isinstance(fight.get("fflogs_raw"), dict) else {}
        raw_damage_done = raw.get("damage_done") if isinstance(raw, dict) else None
        if not isinstance(raw_damage_done, dict):
            continue

        time_info = calculate_damage_time_info({"damage_done": raw_damage_done}, to_number(fight.get("clear_time_ms")))
        for field_name in (
            "fflogs_total_time_ms",
            "fflogs_combat_time_ms",
            "damage_downtime_ms",
            "damage_time_ms",
        ):
            value = time_info.get(field_name)
            if fight.get(field_name) is None and value is not None:
                fight[field_name] = value
                changed += 1

        for ms_field, seconds_field in (
            ("fflogs_total_time_ms", "fflogs_total_time_seconds"),
            ("fflogs_combat_time_ms", "fflogs_combat_time_seconds"),
            ("damage_downtime_ms", "damage_downtime_seconds"),
            ("damage_time_ms", "damage_time_seconds"),
        ):
            if fight.get(seconds_field) is None and fight.get(ms_field) is not None:
                fight[seconds_field] = milliseconds_to_seconds(fight.get(ms_field))
                changed += 1

    return changed


def locally_fill_existing_damage_time_fields(encounters: dict[str, dict[str, Any]]) -> tuple[int, int]:
    changed_fields = 0
    changed_encounters = 0

    for key, encounter in sorted(encounters.items()):
        path = ranking_path(encounter)
        if not path.exists():
            continue

        ranking = load_ranking_file(encounter)
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        encounter_changed_fields = 0
        for report in reports.values():
            if isinstance(report, dict):
                encounter_changed_fields += locally_fill_damage_time_fields(report)

        if encounter_changed_fields:
            write_ranking_file(encounter, ranking)
            changed_fields += encounter_changed_fields
            changed_encounters += 1
            print(f"Locally filled {encounter_changed_fields} derived damage time fields for {key}.")

    return changed_fields, changed_encounters


def report_sort_time(report: dict[str, Any], now_ms: float | None = None) -> float:
    report_values = [
        first_number(report.get("report_end_time"), report.get("endTime")),
        first_number(report.get("report_start_time"), report.get("startTime")),
    ]
    missing_fight_values = []
    all_fight_values = []
    for fight in report.get("fights") or []:
        if not isinstance(fight, dict):
            continue
        values = fight_time_values(report, fight)
        all_fight_values.extend(values)
        if fight_needs_backfill(fight):
            missing_fight_values.extend(values)

    for values in (missing_fight_values, all_fight_values, report_values):
        usable_values = [
            value for value in values if value is not None and (now_ms is None or value <= now_ms)
        ]
        if usable_values:
            return max(usable_values)

    return 0


def make_shallow_report(report_code: str, report: dict[str, Any]) -> dict[str, Any]:
    region = report.get("region") if isinstance(report.get("region"), dict) else {}
    return {
        "code": report_code,
        "title": report.get("title") or "backfill",
        "startTime": report.get("report_start_time") or report.get("startTime"),
        "endTime": report.get("report_end_time") or report.get("endTime"),
        "region": region,
    }


def load_state() -> dict[str, Any]:
    return load_state_file()


def skipped_inaccessible_report_codes(state: dict[str, Any]) -> set[str]:
    # 隱藏、刪除或沒有權限的 report 會被 state 快取，避免排程每次都對同一批不可存取報告重試。
    skipped: set[str] = set()
    encounters = state.get("encounters")
    if not isinstance(encounters, dict):
        return skipped

    for encounter_state in encounters.values():
        if not isinstance(encounter_state, dict):
            continue
        for bucket_name in ("checked_reports", "processed_reports"):
            reports = encounter_state.get(bucket_name)
            if not isinstance(reports, dict):
                continue
            for report_code, record in reports.items():
                if isinstance(record, dict) and record.get("status") == SKIPPED_INACCESSIBLE_STATUS:
                    skipped.add(str(report_code))

    return skipped


def mark_candidate_inaccessible(
    state: dict[str, Any],
    encounters: dict[str, dict[str, Any]],
    candidate: BackfillCandidate,
    error: Exception,
) -> None:
    extra = {"reason": str(error), "source": "backfill_missing_fflogs_data"}
    for key in sorted(candidate.encounter_keys):
        encounter = encounters.get(key)
        if not encounter:
            continue
        ranking = load_ranking_file(encounter)
        if mark_ranking_report_hidden(
            ranking,
            candidate.report_code,
            原因=hidden_reason_inaccessible,
            來源="backfill_missing_fflogs_data",
            詳細原因=str(error),
        ):
            # 補欄位腳本常是第一個碰到 Private/刪除 report 的 workflow。
            # 回寫來源 ranking 的隱藏旗標後，公開排行榜與所有 Node.js 聚合都會同步排除該 report。
            write_ranking_file(encounter, ranking)
        mark_report_status(
            state,
            encounter,
            candidate.report_code,
            SKIPPED_INACCESSIBLE_STATUS,
            extra,
            立即寫入=False,
        )
    write_state_file(state)


def scan_candidates(
    encounters: dict[str, dict[str, Any]],
    now_ms: float,
    skipped_report_codes: set[str],
    *,
    support_metrics_since_ms: float | None = None,
    support_metrics_until_ms: float | None = None,
) -> dict[str, BackfillCandidate]:
    # 同一 report 可能出現在多個 encounter；候選以 report_code 合併，真正寫回時再拆回各副本排行榜。
    candidates: dict[str, BackfillCandidate] = {}

    for key, encounter in sorted(encounters.items()):
        path = ranking_path(encounter)
        if not path.exists():
            continue

        ranking = load_ranking_file(encounter)
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for report_code, report in reports.items():
            if not report_code or not isinstance(report, dict):
                continue

            needs_backfill, need_fights = report_needs_backfill(
                report,
                support_metrics_since_ms=support_metrics_since_ms,
                support_metrics_until_ms=support_metrics_until_ms,
            )
            if not needs_backfill:
                continue

            code = str(report_code)
            if code in skipped_report_codes:
                continue

            candidate = candidates.setdefault(code, BackfillCandidate(report_code=code))
            candidate.encounter_keys.add(key)
            candidate.reports_by_key[key] = report
            candidate.need_fight_count += need_fights
            if support_metrics_since_ms is not None:
                until_ms = support_metrics_until_ms if support_metrics_until_ms is not None else now_ms
                candidate.sort_time = max(
                    candidate.sort_time,
                    report_support_metrics_sort_time(report, support_metrics_since_ms, until_ms),
                )
            else:
                candidate.sort_time = max(candidate.sort_time, report_sort_time(report, now_ms))

    return candidates


def get_existing_report(candidate: BackfillCandidate) -> dict[str, Any]:
    return max(candidate.reports_by_key.values(), key=report_sort_time)


def get_existing_matched_players(candidate: BackfillCandidate) -> list[dict[str, Any]]:
    for report in sorted(candidate.reports_by_key.values(), key=report_sort_time, reverse=True):
        players = report.get("matched_players")
        if isinstance(players, list):
            return [player for player in players if isinstance(player, dict)]

    # compact 後的 report 不再保存 masterData／matched_players，但既有 fight.players 已是
    # 繁中服篩選完成的結果。支援統計回補只需要伺服器摘要，直接由現有玩家列重建可省下一次
    # masterData GraphQL request；若舊資料連玩家列都沒有，呼叫端仍會退回正式深層查詢。
    rebuilt: dict[tuple[str, str], dict[str, Any]] = {}
    for report in sorted(candidate.reports_by_key.values(), key=report_sort_time, reverse=True):
        for fight in report.get("fights") or []:
            if not isinstance(fight, dict):
                continue
            for player in fight.get("players") or []:
                if not isinstance(player, dict):
                    continue
                name = player.get("name")
                server = player.get("server")
                if not isinstance(name, str) or not name or not isinstance(server, str) or not server:
                    continue
                rebuilt.setdefault(
                    (name, server),
                    {
                        "id": player.get("fflogs_id"),
                        "gameID": player.get("fflogs_guid"),
                        "name": name,
                        "server": server,
                        "subType": player.get("job"),
                    },
                )
        if rebuilt:
            return list(rebuilt.values())
    return []


def parse_args() -> argparse.Namespace:
    default_limit = int(os.environ.get("FFLOGS_BACKFILL_LIMIT", "500"))
    parser = argparse.ArgumentParser(description="Backfill existing FFLogs reports that miss build-critical fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum unique report codes to update.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the selected reports.")
    parser.add_argument(
        "--support-metrics-since",
        help="只回補此 ISO 8601 時間（含）之後缺少目前版本坦補摘要的 fight。",
    )
    parser.add_argument(
        "--support-metrics-until",
        help="支援統計回補終點（含）；省略時固定使用本次執行開始時間。",
    )
    parser.add_argument(
        "--stateful-support-metrics-backfill",
        action="store_true",
        help="從固定切點由新往舊回補，並以 data/state.json 保存跨 workflow 游標。",
    )
    parser.add_argument(
        "--support-metrics-cutoff-iso",
        default=os.environ.get("FFLOGS_SUPPORT_METRICS_BACKFILL_CUTOFF_ISO", DEFAULT_SUPPORT_METRICS_CUTOFF_ISO),
        help="stateful 支援統計回補的固定切點，預設為繁中服 7.2 開放時間。",
    )
    parser.add_argument(
        "--oldest-first",
        action="store_true",
        help="由最舊候選開始，適合和處理最新 report 的 workflow 同時執行。",
    )
    parser.add_argument(
        "--checkpoint-every",
        type=int,
        default=int(os.environ.get("FFLOGS_BACKFILL_CHECKPOINT_EVERY", "0")),
        help="每處理幾份 report 寫回一次；0 代表結束時一次寫回。",
    )
    return parser.parse_args()


def flush_updates(
    encounters: dict[str, dict[str, Any]],
    updates_by_encounter: dict[str, list[dict[str, Any]]],
) -> tuple[int, set[str]]:
    """批次寫回已完成的 report，讓長時間回補可安全中斷並從剩餘空洞續跑。"""

    updated_entries = 0
    changed_encounters: set[str] = set()
    for key, scores in sorted(updates_by_encounter.items()):
        if not scores:
            continue

        encounter = encounters[key]
        ranking = load_ranking_file(encounter)
        changed = apply_scores_to_ranking(ranking, scores)
        write_ranking_file(encounter, ranking)
        scores.clear()
        updated_entries += changed
        changed_encounters.add(key)
        print(f"寫入 {key}：取得 {changed} 份有變更的 report。")
    return updated_entries, changed_encounters


def resolve_support_metrics_backfill_state(
    state: dict[str, Any],
    cutoff_ms: int,
) -> tuple[int, str | None, bool, set[str]]:
    """讀取 workflow 由新往舊游標；規則版本更新時自動從固定切點重跑。"""

    node = state.get(SUPPORT_METRICS_REPORT_BACKFILL_STATE_KEY)
    if not isinstance(node, dict):
        node = {}
    version_changed = (
        node.get("calculation_version") != support_metrics.支援統計計算版本
        or node.get("mitigation_rules_version") != support_metrics.坦克減傷規則版本
    )
    cutoff_changed = int(node.get("cutoff_sort_time") or 0) != cutoff_ms
    initialized = version_changed or cutoff_changed
    if initialized:
        return cutoff_ms, None, True, set()

    cursor_ms = int(node.get("cursor_sort_time") or cutoff_ms)
    cursor_report_code = str(node.get("cursor_report_code")) if node.get("cursor_report_code") else None
    retry_report_codes = {
        str(report_code)
        for report_code in (node.get("retry_report_codes") or [])
        if report_code
    }
    return cursor_ms, cursor_report_code, False, retry_report_codes


def filter_support_candidates_before_cursor(
    candidates: list[BackfillCandidate],
    cursor_ms: int,
    cursor_report_code: str | None,
    retry_report_codes: set[str],
) -> list[BackfillCandidate]:
    cursor_key = (float(cursor_ms), cursor_report_code or "")
    return [
        candidate
        for candidate in candidates
        if candidate.report_code in retry_report_codes
        or (
            (candidate.sort_time, candidate.report_code) < cursor_key
            if cursor_report_code
            else candidate.sort_time < cursor_ms
        )
    ]


def update_support_metrics_backfill_state(
    state: dict[str, Any],
    *,
    cutoff_ms: int,
    initialized: bool,
    candidate_count: int,
    selected: list[BackfillCandidate],
    updated_reports: int,
    skipped_inaccessible: int,
    failed_report_codes: set[str],
    completed_report_codes: set[str],
) -> None:
    node = state.setdefault(SUPPORT_METRICS_REPORT_BACKFILL_STATE_KEY, {})
    if not isinstance(node, dict):
        node = {}
        state[SUPPORT_METRICS_REPORT_BACKFILL_STATE_KEY] = node

    now_iso = datetime.now(timezone.utc).isoformat()
    node["schema_version"] = 1
    node["mode"] = "new_to_old_report_backfill"
    node["calculation_version"] = support_metrics.支援統計計算版本
    node["mitigation_rules_version"] = support_metrics.坦克減傷規則版本
    if initialized or "cutoff_sort_time" not in node:
        node["cutoff_sort_time"] = cutoff_ms
        node["cutoff_sort_time_iso"] = datetime.fromtimestamp(cutoff_ms / 1000, tz=timezone.utc).isoformat()
        node["initialized_at_iso"] = now_iso
        node["cursor_sort_time"] = cutoff_ms
        node["cursor_sort_time_iso"] = node["cutoff_sort_time_iso"]
        node.pop("cursor_report_code", None)

    existing_retries = {
        str(report_code)
        for report_code in (node.get("retry_report_codes") or [])
        if report_code
    }
    retries = (existing_retries - completed_report_codes) | failed_report_codes
    if retries:
        node["retry_report_codes"] = sorted(retries)
    else:
        node.pop("retry_report_codes", None)

    if selected:
        oldest = min(selected, key=lambda candidate: (candidate.sort_time, candidate.report_code))
        node["cursor_sort_time"] = int(oldest.sort_time)
        node["cursor_sort_time_iso"] = datetime.fromtimestamp(oldest.sort_time / 1000, tz=timezone.utc).isoformat()
        node["cursor_report_code"] = oldest.report_code
        node["last_oldest_selected_report_code"] = oldest.report_code
    node["last_run_at_iso"] = now_iso
    node["last_candidate_reports_before_cursor"] = candidate_count
    node["last_selected_reports"] = len(selected)
    node["last_updated_reports"] = updated_reports
    node["last_skipped_inaccessible_reports"] = skipped_inaccessible
    node["last_failed_reports"] = len(failed_report_codes)
    node["completed"] = candidate_count == 0


def main() -> int:
    args = parse_args()
    if args.support_metrics_until and not args.support_metrics_since:
        raise SystemExit("--support-metrics-until 必須和 --support-metrics-since 一起使用。")
    if args.stateful_support_metrics_backfill and args.support_metrics_since:
        raise SystemExit("stateful 歷史回補不可同時使用 --support-metrics-since。")
    if args.checkpoint_every < 0:
        raise SystemExit("--checkpoint-every 不可小於 0。")

    encounters = load_all_encounters()
    support_metrics_mode = bool(args.support_metrics_since or args.stateful_support_metrics_backfill)
    if not args.dry_run and not support_metrics_mode:
        local_fields, local_encounters = locally_fill_existing_damage_time_fields(encounters)
        if local_fields:
            print(
                f"Local derived damage time fill complete: "
                f"{local_fields} fields changed across {local_encounters} encounters."
            )

    now_ms = time.time() * 1000
    state = load_state()
    support_metrics_cutoff_ms: int | None = None
    support_metrics_cursor_ms: int | None = None
    support_metrics_cursor_report_code: str | None = None
    support_metrics_state_initialized = False
    retry_report_codes: set[str] = set()
    try:
        if args.stateful_support_metrics_backfill:
            support_metrics_cutoff_ms = int(parse_iso_timestamp(args.support_metrics_cutoff_iso))
            support_metrics_since_ms = 0.0
            support_metrics_until_ms = float(support_metrics_cutoff_ms)
            (
                support_metrics_cursor_ms,
                support_metrics_cursor_report_code,
                support_metrics_state_initialized,
                retry_report_codes,
            ) = resolve_support_metrics_backfill_state(state, support_metrics_cutoff_ms)
        else:
            support_metrics_since_ms = (
                parse_iso_timestamp(args.support_metrics_since) if args.support_metrics_since else None
            )
            support_metrics_until_ms = (
                parse_iso_timestamp(args.support_metrics_until) if args.support_metrics_until else now_ms
            )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    if support_metrics_since_ms is not None and support_metrics_until_ms < support_metrics_since_ms:
        raise SystemExit("支援統計回補終點不可早於起點。")

    skipped_report_codes = skipped_inaccessible_report_codes(state)
    candidate_index = scan_candidates(
        encounters,
        now_ms,
        skipped_report_codes,
        support_metrics_since_ms=support_metrics_since_ms,
        support_metrics_until_ms=support_metrics_until_ms,
    )
    candidates = list(candidate_index.values())
    if args.stateful_support_metrics_backfill:
        candidates = filter_support_candidates_before_cursor(
            candidates,
            support_metrics_cursor_ms or support_metrics_cutoff_ms or int(now_ms),
            support_metrics_cursor_report_code,
            retry_report_codes,
        )
    selected = sorted(
        candidates,
        key=lambda item: (item.sort_time, item.report_code),
        reverse=args.stateful_support_metrics_backfill or not args.oldest_first,
    )[
        : max(args.limit, 0)
    ]

    if support_metrics_since_ms is not None:
        print(
            "支援統計回補範圍："
            f"{datetime.fromtimestamp(support_metrics_since_ms / 1000, tz=timezone.utc).isoformat()} 至 "
            f"{datetime.fromtimestamp(support_metrics_until_ms / 1000, tz=timezone.utc).isoformat()}。"
        )
    if args.stateful_support_metrics_backfill:
        cursor_iso = datetime.fromtimestamp(
            (support_metrics_cursor_ms or support_metrics_cutoff_ms or int(now_ms)) / 1000,
            tz=timezone.utc,
        ).isoformat()
        print(f"Workflow 歷史游標：{cursor_iso}，由新往舊回補 7/28 以前資料。")
    print(f"找到 {len(candidates)} 份需要 FFLogs 回補的 report。")
    if skipped_report_codes:
        print(f"Skipped {len(skipped_report_codes)} inaccessible report codes already cached in state.")
    排序名稱 = "最新" if args.stateful_support_metrics_backfill else ("最舊" if args.oldest_first else "最新")
    print(f"本輪依戰鬥時間選取 {len(selected)} 份{排序名稱} report。")
    if not selected:
        if args.stateful_support_metrics_backfill and not args.dry_run and support_metrics_cutoff_ms is not None:
            update_support_metrics_backfill_state(
                state,
                cutoff_ms=support_metrics_cutoff_ms,
                initialized=support_metrics_state_initialized,
                candidate_count=0,
                selected=[],
                updated_reports=0,
                skipped_inaccessible=0,
                failed_report_codes=set(),
                completed_report_codes=set(),
            )
            write_state_file(state)
            print("已更新 data/state.json：支援統計歷史回補目前沒有剩餘候選。")
        return 0

    for index, candidate in enumerate(selected[:20], start=1):
        print(
            f"{index:>2}. {candidate.report_code} "
            f"encounters={','.join(sorted(candidate.encounter_keys))} "
            f"missing_fights={candidate.need_fight_count} "
            f"encounter_time={int(candidate.sort_time) if candidate.sort_time else 0}"
        )
    if len(selected) > 20:
        print(f"... and {len(selected) - 20} more.")

    if args.dry_run:
        return 0

    session = fflogs.requests.Session()
    auth_pool = auth_pool_class(session, read_credentials())
    updates_by_encounter: dict[str, list[dict[str, Any]]] = {key: [] for key in encounters}
    failed = 0
    skipped_inaccessible = 0
    updated_reports = 0
    updated_entries = 0
    changed_encounter_keys: set[str] = set()
    failed_report_codes: set[str] = set()
    completed_report_codes: set[str] = set()

    for index, candidate in enumerate(selected, start=1):
        existing_report = get_existing_report(candidate)
        shallow_report = make_shallow_report(candidate.report_code, existing_report)
        matched_players = get_existing_matched_players(candidate)

        if not matched_players:
            try:
                _, matched_players = report_has_tc_players(session, auth_pool, candidate.report_code)
            except report_access_error_class as error:
                skipped_inaccessible += 1
                completed_report_codes.add(candidate.report_code)
                mark_candidate_inaccessible(state, encounters, candidate, error)
                print(
                    f"[{index}/{len(selected)}] Skipped inaccessible report {candidate.report_code} "
                    f"for {len(candidate.encounter_keys)} encounters."
                )
                continue
            except Exception as error:  # noqa: BLE001
                failed += 1
                failed_report_codes.add(candidate.report_code)
                print(f"[{index}/{len(selected)}] Failed to check players for {candidate.report_code}: {error}", file=sys.stderr)
                continue

        report_updated = False
        for key in sorted(candidate.encounter_keys):
            encounter = encounters.get(key)
            if not encounter:
                continue

            try:
                score = build_report_score(session, auth_pool, encounter, shallow_report, matched_players)
            except report_access_error_class as error:
                skipped_inaccessible += 1
                completed_report_codes.add(candidate.report_code)
                mark_candidate_inaccessible(state, encounters, candidate, error)
                print(
                    f"[{index}/{len(selected)}] Skipped inaccessible report {candidate.report_code} "
                    f"for {len(candidate.encounter_keys)} encounters."
                )
                break
            except Exception as error:  # noqa: BLE001
                failed += 1
                failed_report_codes.add(candidate.report_code)
                print(f"[{index}/{len(selected)}] Failed to backfill {candidate.report_code} for {key}: {error}", file=sys.stderr)
                continue

            if not score:
                failed_report_codes.add(candidate.report_code)
                print(f"[{index}/{len(selected)}] No matching clear found for {candidate.report_code} in {key}.")
                continue

            updates_by_encounter[key].append(score)
            report_updated = True
            print(f"[{index}/{len(selected)}] Backfilled {candidate.report_code} for {key}.")

        if report_updated:
            updated_reports += 1
            if candidate.report_code not in failed_report_codes:
                completed_report_codes.add(candidate.report_code)

        if args.checkpoint_every and index % args.checkpoint_every == 0:
            checkpoint_entries, checkpoint_encounters = flush_updates(encounters, updates_by_encounter)
            updated_entries += checkpoint_entries
            changed_encounter_keys.update(checkpoint_encounters)
            print(f"已完成 {index}/{len(selected)} 份 report 的回補檢查點。")

    final_entries, final_encounters = flush_updates(encounters, updates_by_encounter)
    updated_entries += final_entries
    changed_encounter_keys.update(final_encounters)

    if args.stateful_support_metrics_backfill and support_metrics_cutoff_ms is not None:
        update_support_metrics_backfill_state(
            state,
            cutoff_ms=support_metrics_cutoff_ms,
            initialized=support_metrics_state_initialized,
            candidate_count=len(candidates),
            selected=selected,
            updated_reports=updated_reports,
            skipped_inaccessible=skipped_inaccessible,
            failed_report_codes=failed_report_codes,
            completed_report_codes=completed_report_codes,
        )
        write_state_file(state)
        print("已更新 data/state.json 的 support_metrics_report_backfill 歷史游標。")

    print(
        "回補完成："
        f"取得 {updated_reports} 份 report，"
        f"更新 {updated_entries} 份副本 report 來源（{len(changed_encounter_keys)} 個副本），"
        f"略過 {skipped_inaccessible} 份不可存取 report，"
        f"失敗 {failed} 份。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
