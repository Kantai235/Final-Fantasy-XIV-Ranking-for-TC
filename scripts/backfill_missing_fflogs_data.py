from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402


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
write_json = getattr(fflogs, "\u5beb\u5165_json")
state_path = getattr(fflogs, "\u72c0\u614b\u6a94\u6848\u8def\u5f91")
mark_report_status = getattr(fflogs, "\u6a19\u8a18\u5831\u544a\u8655\u7406\u72c0\u614b")
report_access_error_class = getattr(fflogs, "FFLogs\u5831\u544a\u5b58\u53d6\u932f\u8aa4")
hidden_reason_inaccessible = getattr(fflogs, "\u5831\u544a\u7121\u6cd5\u5b58\u53d6\u96b1\u85cf\u539f\u56e0")


MIN_REASONABLE_EPOCH_MS = 946684800000
SKIPPED_INACCESSIBLE_STATUS = "skipped_inaccessible"


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


def report_needs_backfill(report: dict[str, Any]) -> tuple[bool, int]:
    # raw metadata 已不再是資料契約的一部分；只要 report/fight/player 足以重建 public/data，
    # 就不應把它送回 FFLogs 補抓，否則 backfill 會把大型 raw 欄位重新寫進 repo。
    fights = report.get("fights")
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
    state = read_json(state_path, {})
    return state if isinstance(state, dict) else {}


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
    write_json(state_path, state)


def scan_candidates(
    encounters: dict[str, dict[str, Any]],
    now_ms: float,
    skipped_report_codes: set[str],
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

            needs_backfill, need_fights = report_needs_backfill(report)
            if not needs_backfill:
                continue

            code = str(report_code)
            if code in skipped_report_codes:
                continue

            candidate = candidates.setdefault(code, BackfillCandidate(report_code=code))
            candidate.encounter_keys.add(key)
            candidate.reports_by_key[key] = report
            candidate.need_fight_count += need_fights
            candidate.sort_time = max(candidate.sort_time, report_sort_time(report, now_ms))

    return candidates


def get_existing_report(candidate: BackfillCandidate) -> dict[str, Any]:
    return max(candidate.reports_by_key.values(), key=report_sort_time)


def get_existing_matched_players(candidate: BackfillCandidate) -> list[dict[str, Any]]:
    for report in sorted(candidate.reports_by_key.values(), key=report_sort_time, reverse=True):
        players = report.get("matched_players")
        if isinstance(players, list):
            return [player for player in players if isinstance(player, dict)]
    return []


def parse_args() -> argparse.Namespace:
    default_limit = int(os.environ.get("FFLOGS_BACKFILL_LIMIT", "500"))
    parser = argparse.ArgumentParser(description="Backfill existing FFLogs reports that miss build-critical fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum unique report codes to update.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the selected reports.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    encounters = load_all_encounters()
    if not args.dry_run:
        local_fields, local_encounters = locally_fill_existing_damage_time_fields(encounters)
        if local_fields:
            print(
                f"Local derived damage time fill complete: "
                f"{local_fields} fields changed across {local_encounters} encounters."
            )

    now_ms = time.time() * 1000
    state = load_state()
    skipped_report_codes = skipped_inaccessible_report_codes(state)
    candidates = scan_candidates(encounters, now_ms, skipped_report_codes)
    selected = sorted(candidates.values(), key=lambda item: (item.sort_time, item.report_code), reverse=True)[
        : max(args.limit, 0)
    ]

    print(f"Found {len(candidates)} report codes needing FFLogs backfill.")
    if skipped_report_codes:
        print(f"Skipped {len(skipped_report_codes)} inaccessible report codes already cached in state.")
    print(f"Selected {len(selected)} newest report codes by encounter time for this run.")
    if not selected:
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

    for index, candidate in enumerate(selected, start=1):
        existing_report = get_existing_report(candidate)
        shallow_report = make_shallow_report(candidate.report_code, existing_report)
        matched_players = get_existing_matched_players(candidate)

        if not matched_players:
            try:
                _, matched_players = report_has_tc_players(session, auth_pool, candidate.report_code)
            except report_access_error_class as error:
                skipped_inaccessible += 1
                mark_candidate_inaccessible(state, encounters, candidate, error)
                print(
                    f"[{index}/{len(selected)}] Skipped inaccessible report {candidate.report_code} "
                    f"for {len(candidate.encounter_keys)} encounters."
                )
                continue
            except Exception as error:  # noqa: BLE001
                failed += 1
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
                mark_candidate_inaccessible(state, encounters, candidate, error)
                print(
                    f"[{index}/{len(selected)}] Skipped inaccessible report {candidate.report_code} "
                    f"for {len(candidate.encounter_keys)} encounters."
                )
                break
            except Exception as error:  # noqa: BLE001
                failed += 1
                print(f"[{index}/{len(selected)}] Failed to backfill {candidate.report_code} for {key}: {error}", file=sys.stderr)
                continue

            if not score:
                print(f"[{index}/{len(selected)}] No matching clear found for {candidate.report_code} in {key}.")
                continue

            updates_by_encounter[key].append(score)
            report_updated = True
            print(f"[{index}/{len(selected)}] Backfilled {candidate.report_code} for {key}.")

        if report_updated:
            updated_reports += 1

    updated_entries = 0
    changed_encounters = 0
    for key, scores in sorted(updates_by_encounter.items()):
        if not scores:
            continue

        encounter = encounters[key]
        ranking = load_ranking_file(encounter)
        changed = apply_scores_to_ranking(ranking, scores)
        write_ranking_file(encounter, ranking)
        updated_entries += changed
        changed_encounters += 1
        print(f"Wrote {key}: {len(scores)} fetched reports, {changed} changed report entries.")

    print(
        "Backfill complete: "
        f"{updated_reports} report codes fetched, "
        f"{updated_entries} report entries changed across {changed_encounters} encounters, "
        f"{skipped_inaccessible} inaccessible report codes skipped, "
        f"{failed} failures."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
