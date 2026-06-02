from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402
import gcd_coverage_core as gcd_core  # noqa: E402


DEFAULT_GCD_BACKFILL_LIMIT = 2000
DEFAULT_GCD_BACKFILL_REPORT_LIMIT = 0
GCD_REPORT_BACKFILL_STATE_KEY = "gcd_report_backfill"
MIN_REASONABLE_EPOCH_MS = 946684800000
MAIN_TARGET_DAMAGE_DOWNTIME_ENCOUNTERS = {"unreal_byakko"}
RAW_EVENT_GCD_ENCOUNTERS = gcd_core.RAW_EVENT_GCD_ENCOUNTERS

read_json = getattr(fflogs, "\u8b80\u53d6_json")
write_json = getattr(fflogs, "\u5beb\u5165_json")
state_path = getattr(fflogs, "\u72c0\u614b\u6a94\u6848\u8def\u5f91")
ranking_path = getattr(fflogs, "\u6392\u884c\u699c\u6a94\u6848\u8def\u5f91")
load_ranking_file = getattr(fflogs, "\u8b80\u53d6\u6392\u884c\u699c\u6a94\u6848")
write_ranking_file = getattr(fflogs, "\u5beb\u5165\u6392\u884c\u699c\u6a94\u6848")
report_is_hidden = getattr(fflogs, "\u5831\u544a\u5df2\u6a19\u8a18\u96b1\u85cf")
mark_ranking_report_hidden = getattr(fflogs, "\u6a19\u8a18\u6392\u884c\u699c\u5831\u544a\u96b1\u85cf")
read_credentials = getattr(fflogs, "\u8b80\u53d6\u8a8d\u8b49\u8a2d\u5b9a")
auth_pool_class = getattr(fflogs, "FFLogs\u8a8d\u8b49\u6c60")
execute_graphql = getattr(fflogs, "\u57f7\u884c_graphql")
report_access_error_class = getattr(fflogs, "FFLogs\u5831\u544a\u5b58\u53d6\u932f\u8aa4")
milliseconds_to_iso = getattr(fflogs, "\u6beb\u79d2\u8f49_iso")
hidden_reason_inaccessible = getattr(fflogs, "\u5831\u544a\u7121\u6cd5\u5b58\u53d6\u96b1\u85cf\u539f\u56e0")


@dataclass
class GcdCandidate:
    encounter_key: str
    encounter: dict[str, Any]
    ranking: dict[str, Any]
    report_code: str
    report: dict[str, Any]
    fight: dict[str, Any]
    player: dict[str, Any]
    sort_time: float

    @property
    def label(self) -> str:
        name = self.player.get("name") or self.player.get("character_name") or "未知角色"
        server = self.player.get("server") or "未知伺服器"
        job = self.player.get("job") or "未知職業"
        return f"{self.encounter_key} {self.report_code} fight={self.fight.get('fight_id')} {name}@{server}:{job}"


def load_all_encounters() -> dict[str, dict[str, Any]]:
    raw = read_json(PROJECT_ROOT / "config" / "encounters.json", [])
    if not isinstance(raw, list):
        raise RuntimeError("config/encounters.json 必須是陣列。")

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


def fight_absolute_time(report_start_time: float | None, value: Any) -> float | None:
    number = to_number(value)
    if number is None:
        return None
    if number >= MIN_REASONABLE_EPOCH_MS:
        return number
    if report_start_time is not None:
        return report_start_time + number
    return None


def candidate_sort_time(report: dict[str, Any], fight: dict[str, Any]) -> float:
    report_start_time = first_number(report.get("report_start_time"), report.get("startTime"))
    values = [
        fight_absolute_time(report_start_time, first_number(fight.get("end_time"), fight.get("endTime"))),
        first_number(fight.get("recorded_at"), fight.get("recordedAt")),
        first_number(report.get("report_end_time"), report.get("endTime")),
        first_number(report.get("report_start_time"), report.get("startTime")),
    ]
    return max((value for value in values if value is not None), default=0)


def player_is_rankable(player: dict[str, Any]) -> bool:
    return bool(
        (player.get("name") or player.get("character_name"))
        and player.get("server")
        and player.get("job")
        and player.get("dps") is not None
    )


def player_has_query_context(fight: dict[str, Any], player: dict[str, Any]) -> bool:
    return (
        to_int(fight.get("fight_id")) is not None
        and first_number(fight.get("start_time"), fight.get("startTime")) is not None
        and first_number(fight.get("end_time"), fight.get("endTime")) is not None
        and to_int(player.get("fflogs_id")) is not None
    )


def gcd_coverage_version(player: dict[str, Any]) -> int | None:
    coverage = player.get("gcd_coverage")
    if not isinstance(coverage, dict):
        return None
    return to_int(coverage.get("calculation_version"))


def scan_candidates(
    encounters: dict[str, dict[str, Any]],
    *,
    include_current: bool = False,
) -> tuple[list[GcdCandidate], int, int, int, dict[str, dict[str, Any]]]:
    candidates: list[GcdCandidate] = []
    missing_key_count = 0
    stale_key_count = 0
    null_key_count = 0
    rankings_by_key: dict[str, dict[str, Any]] = {}

    for key, encounter in sorted(encounters.items()):
        if not ranking_path(encounter).exists():
            continue

        ranking = load_ranking_file(encounter)
        rankings_by_key[key] = ranking
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for fallback_report_code, report in reports.items():
            if not isinstance(report, dict):
                continue
            if report_is_hidden(report):
                # 已確認無法存取的 report 不再補 GCD，避免 workflow 反覆打同一份 Private/刪除資料。
                continue

            report_code = str(report.get("report_code") or fallback_report_code)
            for fight in report.get("fights") or []:
                if not isinstance(fight, dict):
                    continue

                for player in fight.get("players") or []:
                    if not isinstance(player, dict) or not player_is_rankable(player):
                        continue

                    if "gcd_coverage" not in player:
                        if not player_has_query_context(fight, player):
                            continue
                        missing_key_count += 1
                        candidates.append(
                            GcdCandidate(
                                encounter_key=key,
                                encounter=encounter,
                                ranking=ranking,
                                report_code=report_code,
                                report=report,
                                fight=fight,
                                player=player,
                                sort_time=candidate_sort_time(report, fight),
                            )
                        )
                    elif player.get("gcd_coverage") is None:
                        null_key_count += 1
                    elif gcd_coverage_version(player) != GCD_CALCULATION_VERSION:
                        if not player_has_query_context(fight, player):
                            continue
                        stale_key_count += 1
                        candidates.append(
                            GcdCandidate(
                                encounter_key=key,
                                encounter=encounter,
                                ranking=ranking,
                                report_code=report_code,
                                report=report,
                                fight=fight,
                                player=player,
                                sort_time=candidate_sort_time(report, fight),
                            )
                        )
                    elif include_current:
                        if not player_has_query_context(fight, player):
                            continue
                        candidates.append(
                            GcdCandidate(
                                encounter_key=key,
                                encounter=encounter,
                                ranking=ranking,
                                report_code=report_code,
                                report=report,
                                fight=fight,
                                player=player,
                                sort_time=candidate_sort_time(report, fight),
                            )
                        )

    candidates.sort(key=lambda candidate: (candidate.sort_time, candidate.report_code), reverse=True)
    return candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key


def candidate_report_key(candidate: GcdCandidate) -> str:
    return candidate.report_code


def select_candidates(
    candidates: list[GcdCandidate],
    *,
    player_limit: int,
    report_limit: int = 0,
) -> list[GcdCandidate]:
    if report_limit <= 0:
        return candidates[: max(player_limit, 0)]

    selected_report_codes: set[str] = set()
    for candidate in candidates:
        selected_report_codes.add(candidate_report_key(candidate))
        if len(selected_report_codes) >= report_limit:
            break

    if not selected_report_codes:
        return []

    # Workflow 需要以 report 為單位從新往舊追 GCD。選出最新 N 份 report code 後，
    # 同一份 report 在不同副本分片或不同 fight 裡的待補玩家必須一起處理，避免
    # 同一個 FFLogs report 被切成多輪，浪費 Casts/raw events request 與留下半套結果。
    return [candidate for candidate in candidates if candidate_report_key(candidate) in selected_report_codes]


def selected_report_count(candidates: list[GcdCandidate]) -> int:
    return len({candidate_report_key(candidate) for candidate in candidates})


def parse_report_cutoff_ms(raw_value: str | None) -> int | None:
    if raw_value is None:
        return None

    text = raw_value.strip()
    if not text:
        return None

    try:
        return int(text)
    except ValueError:
        pass

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as error:
        raise RuntimeError(
            f"FFLOGS_GCD_BACKFILL_CUTOFF_ISO 無法解析：{raw_value}，請使用 ISO 8601 或 epoch 毫秒。"
        ) from error

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def cutoff_iso(cutoff_ms: int | None) -> str | None:
    if cutoff_ms is None:
        return None
    return milliseconds_to_iso(cutoff_ms)


def load_state() -> dict[str, Any]:
    state = read_json(state_path, {})
    return state if isinstance(state, dict) else {}


def resolve_stateful_report_window(
    state: dict[str, Any],
    *,
    explicit_cutoff: str | None,
    now_ms: int,
) -> tuple[int, int, str | None, bool]:
    node = state.get(GCD_REPORT_BACKFILL_STATE_KEY)
    if not isinstance(node, dict):
        node = {}

    parsed_explicit = parse_report_cutoff_ms(explicit_cutoff)
    if parsed_explicit is not None:
        initialized = to_int(node.get("cutoff_sort_time")) != parsed_explicit
        cursor_report_code = str(node.get("cursor_report_code")) if node.get("cursor_report_code") else None
        cursor_ms = to_int(node.get("cursor_sort_time")) if not initialized else None
        return parsed_explicit, cursor_ms or parsed_explicit, cursor_report_code if not initialized else None, initialized

    existing_cutoff = to_int(node.get("cutoff_sort_time"))
    if existing_cutoff is not None:
        cursor_ms = to_int(node.get("cursor_sort_time")) or existing_cutoff
        cursor_report_code = str(node.get("cursor_report_code")) if node.get("cursor_report_code") else None
        return existing_cutoff, cursor_ms, cursor_report_code, False

    return now_ms, now_ms, None, True


def report_cursor_key(candidate: GcdCandidate) -> tuple[float, str]:
    return candidate.sort_time, candidate_report_key(candidate)


def filter_candidates_before_cursor(
    candidates: list[GcdCandidate],
    cursor_ms: int | None,
    cursor_report_code: str | None = None,
    *,
    retry_report_codes: set[str] | None = None,
) -> list[GcdCandidate]:
    retry_report_codes = retry_report_codes or set()
    if cursor_ms is None:
        return candidates

    cursor_key = (float(cursor_ms), cursor_report_code or "")
    filtered: list[GcdCandidate] = []
    for candidate in candidates:
        report_code = candidate_report_key(candidate)
        if report_code in retry_report_codes:
            filtered.append(candidate)
            continue
        if cursor_report_code:
            if report_cursor_key(candidate) < cursor_key:
                filtered.append(candidate)
        elif candidate.sort_time < cursor_ms:
            filtered.append(candidate)
    return filtered


def distinct_report_cursor_order(candidates: list[GcdCandidate]) -> list[tuple[float, str]]:
    seen_report_codes: set[str] = set()
    order: list[tuple[float, str]] = []
    for candidate in candidates:
        report_code = candidate_report_key(candidate)
        if report_code in seen_report_codes:
            continue
        seen_report_codes.add(report_code)
        order.append(report_cursor_key(candidate))
    return order


def update_stateful_report_backfill_state(
    state: dict[str, Any],
    *,
    cutoff_ms: int,
    initialized: bool,
    candidate_count: int,
    selected: list[GcdCandidate],
    updated: int,
    marked_null: int,
    failed: int,
    checked_at_iso: str,
    failed_report_codes: set[str] | None = None,
    completed_report_codes: set[str] | None = None,
) -> None:
    node = state.setdefault(GCD_REPORT_BACKFILL_STATE_KEY, {})
    if not isinstance(node, dict):
        node = {}
        state[GCD_REPORT_BACKFILL_STATE_KEY] = node

    node["schema_version"] = 1
    node["mode"] = "new_to_old_report_backfill"
    if initialized or "cutoff_sort_time" not in node:
        node["cutoff_sort_time"] = cutoff_ms
        node["cutoff_sort_time_iso"] = cutoff_iso(cutoff_ms)
        node["initialized_at_iso"] = checked_at_iso
        node["cursor_sort_time"] = cutoff_ms
        node["cursor_sort_time_iso"] = cutoff_iso(cutoff_ms)
        node.pop("cursor_report_code", None)

    existing_retry_report_codes = {
        str(report_code)
        for report_code in (node.get("retry_report_codes") or [])
        if report_code
    }
    retry_report_codes = (existing_retry_report_codes - (completed_report_codes or set())) | (failed_report_codes or set())
    if retry_report_codes:
        node["retry_report_codes"] = sorted(retry_report_codes)
    else:
        node.pop("retry_report_codes", None)

    selected_reports = selected_report_count(selected)
    selected_report_order = distinct_report_cursor_order(selected)
    oldest_selected = selected_report_order[-1] if selected_report_order else None
    if selected_report_order:
        node["cursor_sort_time"] = int(oldest_selected[0])
        node["cursor_sort_time_iso"] = cutoff_iso(int(oldest_selected[0]))
        node["cursor_report_code"] = oldest_selected[1]
    node["last_run_at_iso"] = checked_at_iso
    node["last_candidate_players_before_cutoff"] = candidate_count
    node["last_candidate_players_before_cursor"] = candidate_count
    node["last_selected_players"] = len(selected)
    node["last_selected_reports"] = selected_reports
    node["last_updated_players"] = updated
    node["last_marked_null_players"] = marked_null
    node["last_failed_players"] = failed
    node["last_oldest_selected_sort_time"] = int(oldest_selected[0]) if oldest_selected else None
    node["last_oldest_selected_sort_time_iso"] = cutoff_iso(int(oldest_selected[0])) if oldest_selected else None
    node["last_oldest_selected_report_code"] = oldest_selected[1] if oldest_selected else None
    node["completed"] = candidate_count == 0


def parse_int_env_default(name: str, fallback: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return fallback
    try:
        return int(raw_value)
    except ValueError:
        print(f"環境變數 {name} 不是整數，已改用預設值 {fallback}。", file=sys.stderr)
        return fallback


# backfill 與 fetch 共用核心 GCD 計算器，避免即時補算與手動補算走出不同規則。
ActionMetadata = gcd_core.ActionMetadata
ActionMetadataStore = gcd_core.ActionMetadataStore
StatusMetadataStore = gcd_core.StatusMetadataStore
GCD_CALCULATION_VERSION = gcd_core.GCD_CALCULATION_VERSION
GCD_SOURCE = gcd_core.GCD_SOURCE
to_number = gcd_core.to_number
to_int = gcd_core.to_int
first_number = gcd_core.first_number
infer_recast_multiplier_by_base = gcd_core.infer_recast_multiplier_by_base
calculate_gcd_coverage_from_graph = gcd_core.calculate_gcd_coverage_from_graph
calculate_gcd_coverage_from_raw_events = gcd_core.calculate_gcd_coverage_from_raw_events

def query_fight_casts_graph(session: Any, auth_pool: Any, candidate: GcdCandidate) -> dict[str, Any]:
    return gcd_core.query_fight_casts_graph(
        execute_graphql,
        session,
        auth_pool,
        candidate.report_code,
        candidate.fight,
    )


def query_fight_damage_done_events(session: Any, auth_pool: Any, candidate: GcdCandidate) -> list[dict[str, Any]]:
    return gcd_core.query_fight_damage_done_events(
        execute_graphql,
        session,
        auth_pool,
        candidate.report_code,
        candidate.fight,
    )


def query_fight_raw_events(session: Any, auth_pool: Any, candidate: GcdCandidate) -> list[dict[str, Any]]:
    return gcd_core.query_fight_raw_events(
        execute_graphql,
        session,
        auth_pool,
        candidate.report_code,
        candidate.fight,
    )


def add_encounter_specific_downtime(
    graph: dict[str, Any],
    *,
    session: Any,
    auth_pool: Any,
    candidate: GcdCandidate,
    damage_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]],
) -> dict[str, Any]:
    if candidate.encounter_key not in MAIN_TARGET_DAMAGE_DOWNTIME_ENCOUNTERS:
        return graph

    fight_id = to_int(candidate.fight.get("fight_id"))
    start_time = first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
    end_time = first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        return graph

    cache_key = (candidate.report_code, fight_id, start_time, end_time)
    events = damage_event_cache.get(cache_key)
    if events is None:
        events = query_fight_damage_done_events(session, auth_pool, candidate)
        damage_event_cache[cache_key] = events

    windows = gcd_core.infer_main_target_damage_downtime_windows(events)
    if not windows:
        return graph

    # 幻白虎的 Casts graph 沒有把主目標離場回報成 downtime；核心計算會依職能
    # 決定 encounter_downtime 應只扣分母，或同時扣分母與覆蓋時間。
    graph_with_downtime = dict(graph)
    graph_with_downtime["encounter_downtime"] = windows
    return graph_with_downtime


def mark_candidate_unavailable(candidate: GcdCandidate, reason: str, checked_at_iso: str) -> None:
    candidate.player["gcd_coverage"] = None
    candidate.player["gcd_coverage_status"] = gcd_core.build_gcd_coverage_status(
        checked_at_iso=checked_at_iso,
        state="unavailable",
        reason=reason,
    )


def apply_coverage(candidate: GcdCandidate, coverage: dict[str, Any], checked_at_iso: str) -> None:
    candidate.player["gcd_coverage"] = coverage
    candidate.player["gcd_coverage_status"] = gcd_core.build_gcd_coverage_status(checked_at_iso=checked_at_iso)


def parse_args() -> argparse.Namespace:
    # GitHub Actions 未設定 Repository Variable 時，若 workflow 明確把它傳入 env，
    # Python 會看到空字串而不是缺少 key。這裡先把空值視為預設值，避免還沒讀到
    # 命令列 --limit / --report-limit 覆寫前就因 int("") 中止整輪資料更新。
    default_limit = parse_int_env_default("FFLOGS_GCD_BACKFILL_LIMIT", DEFAULT_GCD_BACKFILL_LIMIT)
    default_report_limit = parse_int_env_default(
        "FFLOGS_GCD_BACKFILL_REPORT_LIMIT",
        DEFAULT_GCD_BACKFILL_REPORT_LIMIT,
    )
    parser = argparse.ArgumentParser(description="Backfill missing FFLogs GCD coverage fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="本輪最多更新的玩家筆數。")
    parser.add_argument(
        "--report-limit",
        type=int,
        default=default_report_limit,
        help="本輪最多處理幾份 FFLogs report code；大於 0 時會取代 --limit 的玩家筆數限制。",
    )
    parser.add_argument(
        "--stateful-report-backfill",
        action="store_true",
        help="使用 data/state.json 的 gcd_report_backfill 切點，只處理切點以前的既有 report。",
    )
    parser.add_argument(
        "--report-cutoff-iso",
        default=os.environ.get("FFLOGS_GCD_BACKFILL_CUTOFF_ISO"),
        help="歷史 GCD 回補的固定時間切點；未指定時，stateful 模式第一次正式執行會使用當下時間。",
    )
    parser.add_argument("--all", action="store_true", help="連已是目前 GCD 計算版本的玩家也重新計算；仍會略過已標為 null 的不可用報告。")
    parser.add_argument("--dry-run", action="store_true", help="只列出待補統計與本輪候選，不寫入也不呼叫 FFLogs。")
    parser.add_argument("--report-code", help="只處理指定 report code，方便驗證單場戰鬥。")
    parser.add_argument("--fight-id", type=int, help="只處理指定 fight id。")
    parser.add_argument("--player-name", help="只處理指定角色名稱。")
    parser.add_argument("--encounter-key", help="只處理指定副本 key，例如 unreal_byakko。")
    parser.add_argument("--raw-events", action="store_true", help="診斷用：優先以 FFLogs raw events 計算；預設仍使用較穩定的 Casts graph。")
    return parser.parse_args()


def candidate_matches_filters(candidate: GcdCandidate, args: argparse.Namespace) -> bool:
    if args.report_code and candidate.report_code != args.report_code:
        return False
    if args.fight_id is not None and to_int(candidate.fight.get("fight_id")) != args.fight_id:
        return False
    if args.player_name:
        name = candidate.player.get("name") or candidate.player.get("character_name")
        if name != args.player_name:
            return False
    if args.encounter_key and candidate.encounter_key != args.encounter_key:
        return False
    return True


def main() -> int:
    args = parse_args()
    state: dict[str, Any] | None = None
    stateful_cutoff_ms: int | None = None
    stateful_cursor_ms: int | None = None
    stateful_cursor_report_code: str | None = None
    stateful_cutoff_initialized = False
    retry_report_codes: set[str] = set()
    encounters = load_all_encounters()
    candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key = scan_candidates(
        encounters,
        include_current=args.all,
    )
    candidates = [candidate for candidate in candidates if candidate_matches_filters(candidate, args)]
    unfiltered_candidate_count = len(candidates)
    if args.stateful_report_backfill:
        state = load_state()
        state_node = state.get(GCD_REPORT_BACKFILL_STATE_KEY)
        if isinstance(state_node, dict):
            retry_report_codes = {
                str(report_code)
                for report_code in (state_node.get("retry_report_codes") or [])
                if report_code
            }
        (
            stateful_cutoff_ms,
            stateful_cursor_ms,
            stateful_cursor_report_code,
            stateful_cutoff_initialized,
        ) = resolve_stateful_report_window(
            state,
            explicit_cutoff=args.report_cutoff_iso,
            now_ms=int(time.time() * 1000),
        )
        if stateful_cutoff_initialized:
            retry_report_codes = set()
        candidates = filter_candidates_before_cursor(
            candidates,
            stateful_cursor_ms,
            stateful_cursor_report_code,
            retry_report_codes=retry_report_codes,
        )
    selected = select_candidates(
        candidates,
        player_limit=args.limit,
        report_limit=max(args.report_limit, 0),
    )

    print(f"需要更新 GCD 覆蓋率的玩家筆數：{missing_key_count}")
    print(f"需要以 v{GCD_CALCULATION_VERSION} 重算 GCD 覆蓋率的玩家筆數：{stale_key_count}")
    print(f"已建立 gcd_coverage key 但值為 null 的玩家筆數：{null_key_count}")
    if args.stateful_report_backfill:
        cursor_text = cutoff_iso(stateful_cursor_ms)
        if stateful_cursor_report_code:
            cursor_text = f"{cursor_text} report={stateful_cursor_report_code}"
        print(
            "已啟用 stateful report 回補："
            f"cutoff={cutoff_iso(stateful_cutoff_ms)}，"
            f"cursor={cursor_text}，"
            f"切點前待補玩家 {len(candidates)} / 全部篩選後 {unfiltered_candidate_count}"
        )
    print(f"本輪選取更新筆數：{len(selected)}")
    if args.report_limit > 0:
        print(f"本輪選取 report 數：{selected_report_count(selected)} / {args.report_limit}")
    if args.all:
        print("已啟用 --all：本輪候選包含目前版本已完成的 GCD 覆蓋率。")
    if args.report_code or args.fight_id is not None or args.player_name:
        print(f"套用篩選後剩餘待補筆數：{len(candidates)}")

    for index, candidate in enumerate(selected[:20], start=1):
        print(f"{index:>2}. {candidate.label} clear_time_sort={int(candidate.sort_time)}")
    if len(selected) > 20:
        print(f"... 另有 {len(selected) - 20} 筆本輪候選。")

    if args.dry_run:
        return 0

    if not selected:
        if args.stateful_report_backfill and state is not None and stateful_cutoff_ms is not None:
            checked_at_iso = milliseconds_to_iso(time.time() * 1000) or ""
            update_stateful_report_backfill_state(
                state,
                cutoff_ms=stateful_cutoff_ms,
                initialized=stateful_cutoff_initialized,
                candidate_count=len(candidates),
                selected=selected,
                updated=0,
                marked_null=0,
                failed=0,
                checked_at_iso=checked_at_iso,
            )
            write_json(state_path, state)
        return 0

    session = fflogs.requests.Session()
    auth_pool = auth_pool_class(session, read_credentials())
    metadata_store = ActionMetadataStore()
    try:
        metadata_store.preload()
    except RuntimeError as error:
        print(f"無法載入 GCD 技能資料，本輪保留缺 key 狀態，下次 workflow 會重試：{error}", file=sys.stderr)
        return 0

    unable_to_act_status_ids: set[int] = set()
    if args.raw_events or any(candidate.encounter_key in RAW_EVENT_GCD_ENCOUNTERS for candidate in selected):
        status_store = StatusMetadataStore()
        status_store.preload()
        unable_to_act_status_ids = status_store.unable_to_act_status_ids()

    changed_encounter_keys: set[str] = set()
    inaccessible_reports: dict[str, str] = {}
    fight_graph_cache: dict[tuple[str, int, float, float], dict[str, Any]] = {}
    fight_raw_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]] = {}
    damage_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]] = {}
    updated = 0
    marked_null = 0
    failed = 0
    completed_report_codes: set[str] = set()
    failed_report_codes: set[str] = set()
    checked_at_iso = milliseconds_to_iso(time.time() * 1000)

    for index, candidate in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] 更新 GCD 覆蓋率：{candidate.label}")
        if candidate.report_code in inaccessible_reports:
            mark_candidate_unavailable(candidate, inaccessible_reports[candidate.report_code], checked_at_iso)
            mark_ranking_report_hidden(
                candidate.ranking,
                candidate.report_code,
                原因=hidden_reason_inaccessible,
                來源="backfill_gcd_coverage",
                詳細原因="同一 report 稍早已確認無法存取",
            )
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            completed_report_codes.add(candidate.report_code)
            print(f"[{index}/{len(selected)}] → report 已標記無法存取，寫入 null。")
            continue

        try:
            fight_id = to_int(candidate.fight.get("fight_id"))
            start_time = first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
            end_time = first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
            if fight_id is None or start_time is None or end_time is None:
                raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法查詢整場 Casts graph。")

            graph_cache_key = (candidate.report_code, fight_id, start_time, end_time)
            base_graph = fight_graph_cache.get(graph_cache_key)
            if base_graph is None:
                base_graph = query_fight_casts_graph(session, auth_pool, candidate)
                fight_graph_cache[graph_cache_key] = base_graph
            graph = add_encounter_specific_downtime(
                base_graph,
                session=session,
                auth_pool=auth_pool,
                candidate=candidate,
                damage_event_cache=damage_event_cache,
            )

            coverage = None
            job = str(candidate.player.get("job") or "")
            use_raw_events = gcd_core.should_use_raw_events_for_gcd(
                candidate.encounter_key,
                job,
                force_raw_events=args.raw_events,
            )
            if use_raw_events:
                raw_events = fight_raw_event_cache.get(graph_cache_key)
                if raw_events is None:
                    raw_events = query_fight_raw_events(session, auth_pool, candidate)
                    fight_raw_event_cache[graph_cache_key] = raw_events
                friendly_ids = {
                    player_id
                    for player_id in (
                        to_int(player.get("fflogs_id"))
                        for player in candidate.fight.get("players") or []
                        if isinstance(player, dict)
                    )
                    if player_id is not None
                }
                if candidate.encounter_key in RAW_EVENT_GCD_ENCOUNTERS:
                    downtime_source = gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=unable_to_act_status_ids,
                        metadata_store=metadata_store,
                        job=job,
                        include_graph_downtime=not gcd_core.raw_event_uses_targetability_only_downtime(
                            candidate.encounter_key,
                            job,
                        ),
                    )
                else:
                    downtime_source = graph
                coverage = calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                    fallback_denominator_ms=first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                    downtime_source=downtime_source,
                    cap_next_gcd_jobs=gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                if coverage and candidate.encounter_key == "unreal_byakko" and job in gcd_core.TANK_JOBS:
                    casts_graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    main_gap_coverage = calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                        downtime_source=gcd_core.raw_event_downtime_source(
                            graph,
                            raw_events,
                            source_id=to_int(candidate.player.get("fflogs_id")),
                            friendly_ids=friendly_ids,
                            fight_start_time=start_time,
                            fight_end_time=end_time,
                            unable_to_act_status_ids=set(),
                            metadata_store=metadata_store,
                            job=job,
                        ),
                        cap_next_gcd_jobs=gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    coverage = gcd_core.select_tank_byakko_coverage(
                        coverage,
                        main_gap_coverage,
                        casts_graph_coverage,
                        job=job,
                    )
                if coverage and candidate.encounter_key == "unreal_byakko" and job == "Pictomancer":
                    graph_downtime_coverage = calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                        downtime_source=graph,
                        cap_next_gcd_jobs=gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    coverage = gcd_core.select_pct_byakko_downtime_coverage(coverage, graph_downtime_coverage)
                if coverage and candidate.encounter_key == "unreal_byakko" and job == "BlackMage":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    raw_downtime_graph_coverage = calculate_gcd_coverage_from_graph(
                        downtime_source,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_blm_byakko_coverage(
                        coverage,
                        graph_coverage,
                        raw_downtime_graph_coverage,
                    )
                if coverage and candidate.encounter_key == "unreal_byakko" and job == "RedMage":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_red_mage_byakko_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and candidate.encounter_key == "savage_m1s" and job == "BlackMage":
                    graph_downtime_coverage = calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                        downtime_source=graph,
                        cap_next_gcd_jobs=gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    coverage = gcd_core.select_savage_m1s_black_mage_coverage(
                        coverage,
                        graph_downtime_coverage,
                        encounter_key=candidate.encounter_key,
                        job=job,
                    )
                if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "RedMage":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_queen_red_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Scholar":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_queen_scholar_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "RedMage":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_valigarmanda_red_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "WhiteMage":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_valigarmanda_white_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Summoner":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_valigarmanda_summoner_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "BlackMage":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_valigarmanda_black_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                if coverage and job == "Bard":
                    graph_coverage = calculate_gcd_coverage_from_graph(
                        graph,
                        metadata_store,
                        source_id=to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                        fallback_denominator_ms=first_number(
                            candidate.fight.get("clear_time_ms"),
                            end_time - start_time,
                            candidate.fight.get("damage_time_ms"),
                        ),
                    )
                    coverage = gcd_core.select_bard_raw_event_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
            if not coverage:
                coverage = calculate_gcd_coverage_from_graph(
                    graph,
                    metadata_store,
                    source_id=to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                    fallback_denominator_ms=first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
        except report_access_error_class:
            reason = "private_or_deleted"
            inaccessible_reports[candidate.report_code] = reason
            mark_candidate_unavailable(candidate, reason, checked_at_iso)
            mark_ranking_report_hidden(
                candidate.ranking,
                candidate.report_code,
                原因=hidden_reason_inaccessible,
                來源="backfill_gcd_coverage",
                詳細原因="FFLogs Casts graph 無法存取",
            )
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            completed_report_codes.add(candidate.report_code)
            print(f"[{index}/{len(selected)}] → report 已轉為 Private、刪除或無權限，寫入 null。")
            continue
        except Exception as error:  # noqa: BLE001
            failed += 1
            failed_report_codes.add(candidate.report_code)
            print(f"[{index}/{len(selected)}] → 暫時失敗，下次 workflow 會重試：{error}", file=sys.stderr)
            continue

        if not coverage:
            failed += 1
            failed_report_codes.add(candidate.report_code)
            print(f"[{index}/{len(selected)}] → 無法從 Casts graph 計算 GCD 覆蓋率，保留缺 key 狀態。", file=sys.stderr)
            continue

        apply_coverage(candidate, coverage, checked_at_iso)
        changed_encounter_keys.add(candidate.encounter_key)
        updated += 1
        completed_report_codes.add(candidate.report_code)
        print(
            f"[{index}/{len(selected)}] → {coverage['percent']:.2f}% "
            f"({coverage['covered_time_ms']}/{coverage['denominator_ms']} ms, "
            f"{coverage['gcd_cast_count']} GCD)"
        )

    for key in sorted(changed_encounter_keys):
        ranking = rankings_by_key.get(key)
        encounter = encounters.get(key)
        if not ranking or not encounter:
            continue
        write_ranking_file(encounter, ranking)
        print(f"已寫入 {key} 的 GCD 覆蓋率更新。")

    print(
        "GCD 覆蓋率補齊完成："
        f"成功 {updated} 筆，"
        f"寫入 null {marked_null} 筆，"
        f"暫時失敗 {failed} 筆。"
    )
    if args.stateful_report_backfill and state is not None and stateful_cutoff_ms is not None:
        update_stateful_report_backfill_state(
            state,
            cutoff_ms=stateful_cutoff_ms,
            initialized=stateful_cutoff_initialized,
            candidate_count=len(candidates),
            selected=selected,
            updated=updated,
            marked_null=marked_null,
            failed=failed,
            checked_at_iso=checked_at_iso or "",
            failed_report_codes=failed_report_codes,
            completed_report_codes=completed_report_codes,
        )
        write_json(state_path, state)
        print("已更新 data/state.json 的 gcd_report_backfill 回補狀態。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
