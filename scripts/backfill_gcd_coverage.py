from __future__ import annotations

import argparse
import csv
import io
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402


# GCD 覆蓋率只保存衍生結果，不能把 Casts raw events 寫入 repo。
# 技能分類來自 XIVAPI 維護的 FFXIV datamining Action.csv；腳本只在記憶體中解析 action id、
# cast、recast 與分類，避免整份遊戲資料落地造成 repo 膨脹。
ACTION_CSV_URL = "https://raw.githubusercontent.com/xivapi/ffxiv-datamining/master/csv/en/Action.csv"
GCD_ACTION_CATEGORY_IDS = {2, 3}  # 2=Spell, 3=Weaponskill
GCD_CALCULATION_VERSION = 2
GCD_SOURCE = "fflogs_casts_graph"
MIN_REASONABLE_EPOCH_MS = 946684800000
RECAST_TIGHT_DELTA_MIN_RATIO = 0.9
RECAST_TIGHT_DELTA_MAX_RATIO = 1.05
RECAST_TIGHT_DELTA_PERCENTILE = 0.7

read_json = getattr(fflogs, "\u8b80\u53d6_json")
ranking_path = getattr(fflogs, "\u6392\u884c\u699c\u6a94\u6848\u8def\u5f91")
load_ranking_file = getattr(fflogs, "\u8b80\u53d6\u6392\u884c\u699c\u6a94\u6848")
write_ranking_file = getattr(fflogs, "\u5beb\u5165\u6392\u884c\u699c\u6a94\u6848")
read_credentials = getattr(fflogs, "\u8b80\u53d6\u8a8d\u8b49\u8a2d\u5b9a")
auth_pool_class = getattr(fflogs, "FFLogs\u8a8d\u8b49\u6c60")
execute_graphql = getattr(fflogs, "\u57f7\u884c_graphql")
report_access_error_class = getattr(fflogs, "FFLogs\u5831\u544a\u5b58\u53d6\u932f\u8aa4")
milliseconds_to_iso = getattr(fflogs, "\u6beb\u79d2\u8f49_iso")


@dataclass(frozen=True)
class ActionMetadata:
    action_id: int
    name: str | None
    action_category_id: int | None
    cast_ms: int
    recast_ms: int

    @property
    def is_gcd(self) -> bool:
        return self.action_category_id in GCD_ACTION_CATEGORY_IDS and self.recast_ms >= 1500


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


class ActionMetadataStore:
    def __init__(self, source_url: str = ACTION_CSV_URL) -> None:
        self.source_url = source_url
        self._metadata_by_id: dict[int, ActionMetadata] | None = None

    def get(self, action_id: int) -> ActionMetadata | None:
        if self._metadata_by_id is None:
            self._metadata_by_id = self._load_action_csv()
        return self._metadata_by_id.get(action_id)

    def preload(self) -> None:
        if self._metadata_by_id is None:
            self._metadata_by_id = self._load_action_csv()

    def _load_action_csv(self) -> dict[int, ActionMetadata]:
        try:
            request = urllib.request.Request(
                self.source_url,
                headers={"User-Agent": "ffxiv-tc-ranking-gcd-backfill/1.0"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_csv = response.read().decode("utf-8-sig")
        except (OSError, urllib.error.URLError) as error:
            raise RuntimeError(f"無法下載 GCD 技能資料：{self.source_url}") from error

        metadata_by_id: dict[int, ActionMetadata] = {}
        reader = csv.DictReader(io.StringIO(raw_csv))
        for row in reader:
            action_id = to_int(row.get("#"))
            if action_id is None:
                continue

            metadata_by_id[action_id] = ActionMetadata(
                action_id=action_id,
                name=row.get("Name") or None,
                action_category_id=to_int(row.get("ActionCategory")),
                cast_ms=(to_int(row.get("Cast100ms")) or 0) * 100,
                recast_ms=(to_int(row.get("Recast100ms")) or 0) * 100,
            )

        if not metadata_by_id:
            raise RuntimeError("GCD 技能資料為空，無法計算覆蓋率。")
        return metadata_by_id


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


def to_int(value: Any) -> int | None:
    number = to_number(value)
    if number is None:
        return None
    return int(number)


def first_number(*values: Any) -> float | None:
    for value in values:
        number = to_number(value)
        if number is not None:
            return number
    return None


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

    candidates.sort(key=lambda candidate: (candidate.sort_time, candidate.report_code), reverse=True)
    return candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key


def query_casts_graph(session: Any, auth_pool: Any, candidate: GcdCandidate) -> dict[str, Any]:
    fight_id = to_int(candidate.fight.get("fight_id"))
    source_id = to_int(candidate.player.get("fflogs_id"))
    start_time = first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
    end_time = first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
    if fight_id is None or source_id is None or start_time is None or end_time is None:
        raise RuntimeError("缺少 fight_id、sourceID 或 fight 時間窗，無法查詢 Casts graph。")

    query = f"""
    query($code: String!, $sourceID: Int!) {{
      reportData {{
        report(code: $code) {{
          graph(
            dataType: Casts,
            fightIDs: [{fight_id}],
            startTime: {start_time},
            endTime: {end_time},
            sourceID: $sourceID
          )
        }}
      }}
    }}
    """
    data = execute_graphql(session, auth_pool, query, {"code": candidate.report_code, "sourceID": source_id})
    graph = (((data.get("reportData") or {}).get("report") or {}).get("graph") or {}).get("data")
    if not isinstance(graph, dict):
        raise RuntimeError("FFLogs Casts graph 回傳格式不正確。")
    return graph


def extract_attempts_from_series(series: dict[str, Any]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    events_groups = series.get("events")
    if not isinstance(events_groups, list):
        return attempts

    action_id = to_int(series.get("guid"))
    if action_id is None:
        return attempts

    for group in events_groups:
        if not isinstance(group, list):
            continue

        events = [event for event in group if isinstance(event, dict)]
        if not events:
            continue

        begin_event = next((event for event in events if event.get("type") == "begincast"), None)
        cast_event = next((event for event in events if event.get("type") == "cast"), None)
        if begin_event:
            timestamp = to_number(begin_event.get("timestamp"))
            duration = to_number(begin_event.get("duration")) or 0
        elif cast_event:
            timestamp = to_number(cast_event.get("timestamp"))
            duration = 0
        else:
            continue

        if timestamp is None:
            continue

        attempts.append({"action_id": action_id, "timestamp": timestamp, "cast_duration_ms": duration})

    return attempts


def extract_gcd_attempts(graph: dict[str, Any], metadata_store: ActionMetadataStore) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for series in graph.get("series") or []:
        if not isinstance(series, dict):
            continue

        action_id = to_int(series.get("guid"))
        if action_id is None:
            continue

        metadata = metadata_store.get(action_id)
        if not metadata or not metadata.is_gcd:
            continue

        for attempt in extract_attempts_from_series(series):
            attempt["metadata"] = metadata
            attempts.append(attempt)

    attempts.sort(key=lambda attempt: (attempt["timestamp"], attempt["action_id"]))
    return attempts


def downtime_windows(graph: dict[str, Any]) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for item in graph.get("downtime") or []:
        if not isinstance(item, dict):
            continue
        start = to_number(item.get("startTime"))
        end = to_number(item.get("endTime"))
        if start is None or end is None or end <= start:
            continue
        windows.append((start, end))
    return windows


def overlap_ms(start: float, end: float, windows: list[tuple[float, float]]) -> float:
    total = 0.0
    for window_start, window_end in windows:
        total += max(0.0, min(end, window_end) - max(start, window_start))
    return total


def median_default_speed_multiplier(attempts: list[dict[str, Any]]) -> float:
    ratios: list[float] = []
    for attempt in attempts:
        metadata = attempt.get("metadata")
        if not isinstance(metadata, ActionMetadata) or metadata.cast_ms <= 0:
            continue

        cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
        if cast_duration <= 0:
            continue

        ratio = cast_duration / metadata.cast_ms
        if 0.9 <= ratio <= 1.05:
            ratios.append(ratio)

    if not ratios:
        return 1.0
    return statistics.median(ratios)


def percentile_value(values: list[float], percentile: float) -> float:
    if not values:
        return 1.0
    sorted_values = sorted(values)
    index = int((len(sorted_values) - 1) * percentile)
    index = max(0, min(len(sorted_values) - 1, index))
    return sorted_values[index]


def infer_recast_multiplier_by_base(attempts: list[dict[str, Any]]) -> dict[int, float]:
    # Cast duration 和 recast 會經過不同的遊戲端取整流程；只用 hardcast duration 推 recast
    # 會讓 GCD 覆蓋時間偏高。不過 FFLogs 的 cast packet timestamp 也可能略早於真正可重按的時間，
    # 若取低分位會把偏短間隔套到整場，導致像黑魔這類高施放密度職業被低估。這裡先只保留
    # 緊貼施放區間，再取偏高分位作為同一種 base recast 的估計；後續仍會用下一個 GCD timestamp
    # 夾住覆蓋區間，因此短窗加速或即刻詠唱不會被這個偏高估計直接灌水。
    ratios_by_recast: dict[int, list[float]] = {}
    for index, attempt in enumerate(attempts[:-1]):
        metadata = attempt.get("metadata")
        if not isinstance(metadata, ActionMetadata) or metadata.recast_ms <= 0:
            continue

        timestamp = to_number(attempt.get("timestamp"))
        next_timestamp = to_number(attempts[index + 1].get("timestamp"))
        if timestamp is None or next_timestamp is None:
            continue

        delta = next_timestamp - timestamp
        ratio = delta / metadata.recast_ms
        if RECAST_TIGHT_DELTA_MIN_RATIO <= ratio <= RECAST_TIGHT_DELTA_MAX_RATIO:
            ratios_by_recast.setdefault(metadata.recast_ms, []).append(ratio)

    return {
        recast_ms: percentile_value(ratios, RECAST_TIGHT_DELTA_PERCENTILE)
        for recast_ms, ratios in ratios_by_recast.items()
        if ratios
    }


def adjusted_recast_ms(
    attempt: dict[str, Any],
    default_speed_multiplier: float,
    recast_multiplier_by_base: dict[int, float],
) -> float:
    metadata = attempt["metadata"]
    cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
    recast_multiplier = recast_multiplier_by_base.get(metadata.recast_ms, default_speed_multiplier)
    recast = float(metadata.recast_ms) * recast_multiplier

    if metadata.cast_ms > 0 and cast_duration > 0:
        cast_ratio = cast_duration / metadata.cast_ms
        if 0.5 <= cast_ratio < 0.9:
            # 例如 Pictomancer 的 Inspiration 會同時縮短 cast 與 recast；這類短窗 buff
            # 不一定有足夠相鄰樣本可推低分位，因此保留 hardcast duration 作為補充線索。
            recast = float(metadata.recast_ms) * cast_ratio

    return max(0.0, recast)


def calculate_gcd_coverage_from_graph(
    graph: dict[str, Any],
    metadata_store: ActionMetadataStore,
    *,
    fight_end_time: float | None = None,
    fallback_denominator_ms: float | None = None,
) -> dict[str, Any] | None:
    attempts = extract_gcd_attempts(graph, metadata_store)
    if not attempts:
        return None

    windows = downtime_windows(graph)
    downtime_ms = sum(end - start for start, end in windows)
    combat_time_ms = to_number(graph.get("combatTime"))
    denominator_ms = (
        combat_time_ms - downtime_ms
        if combat_time_ms is not None and combat_time_ms > downtime_ms
        else fallback_denominator_ms
    )
    if denominator_ms is None or denominator_ms <= 0:
        return None

    default_speed_multiplier = median_default_speed_multiplier(attempts)
    recast_multiplier_by_base = infer_recast_multiplier_by_base(attempts)
    covered_ms = 0.0
    end_time = fight_end_time if fight_end_time is not None else to_number(graph.get("endTime"))

    for index, attempt in enumerate(attempts):
        timestamp = to_number(attempt.get("timestamp"))
        if timestamp is None:
            continue

        next_attempt = attempts[index + 1] if index + 1 < len(attempts) else None
        cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
        recast = adjusted_recast_ms(attempt, default_speed_multiplier, recast_multiplier_by_base)
        uptime = max(cast_duration, recast)
        if cast_duration > 0 and cast_duration >= recast:
            uptime += 100

        if next_attempt:
            next_timestamp = to_number(next_attempt.get("timestamp"))
            if next_timestamp is not None:
                uptime = min(uptime, max(0.0, next_timestamp - timestamp))

        if end_time is not None:
            uptime = min(uptime, max(0.0, end_time - timestamp))

        covered_ms += max(0.0, uptime - overlap_ms(timestamp, timestamp + uptime, windows))

    covered_ms = max(0, round(covered_ms))
    denominator_ms = max(1, round(denominator_ms))
    return {
        "percent": round(min(100.0, covered_ms / denominator_ms * 100), 2),
        "covered_time_ms": covered_ms,
        "denominator_ms": denominator_ms,
        "downtime_ms": round(downtime_ms),
        "gcd_cast_count": len(attempts),
        "calculation_version": GCD_CALCULATION_VERSION,
        "source": GCD_SOURCE,
    }


def mark_candidate_unavailable(candidate: GcdCandidate, reason: str, checked_at_iso: str) -> None:
    candidate.player["gcd_coverage"] = None
    candidate.player["gcd_coverage_status"] = {
        "state": "unavailable",
        "reason": reason,
        "calculation_version": GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
    }


def apply_coverage(candidate: GcdCandidate, coverage: dict[str, Any], checked_at_iso: str) -> None:
    candidate.player["gcd_coverage"] = coverage
    candidate.player["gcd_coverage_status"] = {
        "state": "ok",
        "calculation_version": GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
    }


def parse_args() -> argparse.Namespace:
    default_limit = int(os.environ.get("FFLOGS_GCD_BACKFILL_LIMIT", "2000"))
    parser = argparse.ArgumentParser(description="Backfill missing FFLogs GCD coverage fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="本輪最多更新的玩家筆數。")
    parser.add_argument("--dry-run", action="store_true", help="只列出待補統計與本輪候選，不寫入也不呼叫 FFLogs。")
    parser.add_argument("--report-code", help="只處理指定 report code，方便驗證單場戰鬥。")
    parser.add_argument("--fight-id", type=int, help="只處理指定 fight id。")
    parser.add_argument("--player-name", help="只處理指定角色名稱。")
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
    return True


def main() -> int:
    args = parse_args()
    encounters = load_all_encounters()
    candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key = scan_candidates(encounters)
    candidates = [candidate for candidate in candidates if candidate_matches_filters(candidate, args)]
    selected = candidates[: max(args.limit, 0)]

    print(f"需要更新 GCD 覆蓋率的玩家筆數：{missing_key_count}")
    print(f"需要以 v{GCD_CALCULATION_VERSION} 重算 GCD 覆蓋率的玩家筆數：{stale_key_count}")
    print(f"已建立 gcd_coverage key 但值為 null 的玩家筆數：{null_key_count}")
    print(f"本輪選取更新筆數：{len(selected)}")
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

    changed_encounter_keys: set[str] = set()
    inaccessible_reports: dict[str, str] = {}
    updated = 0
    marked_null = 0
    failed = 0
    checked_at_iso = milliseconds_to_iso(time.time() * 1000)

    for index, candidate in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] 更新 GCD 覆蓋率：{candidate.label}")
        if candidate.report_code in inaccessible_reports:
            mark_candidate_unavailable(candidate, inaccessible_reports[candidate.report_code], checked_at_iso)
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            print(f"[{index}/{len(selected)}] → report 已標記無法存取，寫入 null。")
            continue

        try:
            graph = query_casts_graph(session, auth_pool, candidate)
            coverage = calculate_gcd_coverage_from_graph(
                graph,
                metadata_store,
                fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                fallback_denominator_ms=first_number(candidate.fight.get("damage_time_ms"), candidate.fight.get("clear_time_ms")),
            )
        except report_access_error_class:
            reason = "private_or_deleted"
            inaccessible_reports[candidate.report_code] = reason
            mark_candidate_unavailable(candidate, reason, checked_at_iso)
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
