from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402
import gcd_coverage_core as gcd_core  # noqa: E402


DEFAULT_GCD_BACKFILL_LIMIT = 2000
MIN_REASONABLE_EPOCH_MS = 946684800000
MAIN_TARGET_DAMAGE_DOWNTIME_ENCOUNTERS = {"unreal_byakko"}
RAW_EVENT_GCD_ENCOUNTERS = {"unreal_byakko"}

read_json = getattr(fflogs, "\u8b80\u53d6_json")
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
    # 命令列 --limit 覆寫前就因 int("") 中止整輪資料更新。
    default_limit = parse_int_env_default("FFLOGS_GCD_BACKFILL_LIMIT", DEFAULT_GCD_BACKFILL_LIMIT)
    parser = argparse.ArgumentParser(description="Backfill missing FFLogs GCD coverage fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="本輪最多更新的玩家筆數。")
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
    encounters = load_all_encounters()
    candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key = scan_candidates(
        encounters,
        include_current=args.all,
    )
    candidates = [candidate for candidate in candidates if candidate_matches_filters(candidate, args)]
    selected = candidates[: max(args.limit, 0)]

    print(f"需要更新 GCD 覆蓋率的玩家筆數：{missing_key_count}")
    print(f"需要以 v{GCD_CALCULATION_VERSION} 重算 GCD 覆蓋率的玩家筆數：{stale_key_count}")
    print(f"已建立 gcd_coverage key 但值為 null 的玩家筆數：{null_key_count}")
    print(f"本輪選取更新筆數：{len(selected)}")
    if args.all:
        print("已啟用 --all：本輪候選包含目前版本已完成的 GCD 覆蓋率。")
    if args.report_code or args.fight_id is not None or args.player_name:
        print(f"套用篩選後剩餘待補筆數：{len(candidates)}")

    for index, candidate in enumerate(selected[:20], start=1):
        print(f"{index:>2}. {candidate.label} clear_time_sort={int(candidate.sort_time)}")
    if len(selected) > 20:
        print(f"... 另有 {len(selected) - 20} 筆本輪候選。")

    if args.dry_run or not selected:
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
            use_raw_events = args.raw_events or candidate.encounter_key in RAW_EVENT_GCD_ENCOUNTERS
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
                downtime_source = gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    source_id=to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=unable_to_act_status_ids,
                )
                coverage = calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    metadata_store,
                    source_id=to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                    fallback_denominator_ms=first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                    downtime_source=downtime_source,
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
            print(f"[{index}/{len(selected)}] → report 已轉為 Private、刪除或無權限，寫入 null。")
            continue
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"[{index}/{len(selected)}] → 暫時失敗，下次 workflow 會重試：{error}", file=sys.stderr)
            continue

        if not coverage:
            failed += 1
            print(f"[{index}/{len(selected)}] → 無法從 Casts graph 計算 GCD 覆蓋率，保留缺 key 狀態。", file=sys.stderr)
            continue

        apply_coverage(candidate, coverage, checked_at_iso)
        changed_encounter_keys.add(candidate.encounter_key)
        updated += 1
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
