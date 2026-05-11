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


read_json = getattr(fflogs, "\u8b80\u53d6_json")
ranking_path = getattr(fflogs, "\u6392\u884c\u699c\u6a94\u6848\u8def\u5f91")
normalize_ranking = getattr(fflogs, "\u6b63\u898f\u5316\u6392\u884c\u699c")
load_ranking_file = getattr(fflogs, "\u8b80\u53d6\u6392\u884c\u699c\u6a94\u6848")
build_report_score = getattr(fflogs, "\u5efa\u7acb\u5831\u544a\u6210\u7e3e")
apply_scores_to_ranking = getattr(fflogs, "\u5957\u7528\u6210\u7e3e\u5230\u6392\u884c\u699c")
write_ranking_file = getattr(fflogs, "\u5beb\u5165\u6392\u884c\u699c\u6a94\u6848")
read_credentials = getattr(fflogs, "\u8b80\u53d6\u8a8d\u8b49\u8a2d\u5b9a")
auth_pool_class = getattr(fflogs, "FFLogs\u8a8d\u8b49\u6c60")
report_has_tc_players = getattr(fflogs, "\u5831\u544a\u662f\u5426\u5305\u542b\u7e41\u4e2d\u670d\u73a9\u5bb6")


MIN_REASONABLE_EPOCH_MS = 946684800000


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
    raw = fight.get("fflogs_raw") if isinstance(fight.get("fflogs_raw"), dict) else {}
    raw_damage_done = raw.get("damage_done") if isinstance(raw, dict) else None
    return (
        fight.get("damage_downtime_ms") is None
        or fight.get("damage_time_ms") is None
        or not isinstance(raw_damage_done, dict)
    )


def report_needs_backfill(report: dict[str, Any]) -> tuple[bool, int]:
    raw = report.get("fflogs_raw") if isinstance(report.get("fflogs_raw"), dict) else {}
    raw_report = raw.get("report") if isinstance(raw, dict) else None
    needs_report_metadata = not isinstance(raw_report, dict) or not isinstance(report.get("master_data"), dict)

    need_fights = 0
    for fight in report.get("fights") or []:
        if isinstance(fight, dict) and fight_needs_backfill(fight):
            need_fights += 1

    return needs_report_metadata or need_fights > 0, need_fights


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


def scan_candidates(encounters: dict[str, dict[str, Any]], now_ms: float) -> dict[str, BackfillCandidate]:
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
    parser = argparse.ArgumentParser(description="Backfill existing FFLogs reports that miss newly stored raw fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="Maximum unique report codes to update.")
    parser.add_argument("--dry-run", action="store_true", help="Only print the selected reports.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    encounters = load_all_encounters()
    now_ms = time.time() * 1000
    candidates = scan_candidates(encounters, now_ms)
    selected = sorted(candidates.values(), key=lambda item: (item.sort_time, item.report_code), reverse=True)[
        : max(args.limit, 0)
    ]

    print(f"Found {len(candidates)} report codes needing FFLogs backfill.")
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
    updated_reports = 0

    for index, candidate in enumerate(selected, start=1):
        existing_report = get_existing_report(candidate)
        shallow_report = make_shallow_report(candidate.report_code, existing_report)
        matched_players = get_existing_matched_players(candidate)

        if not matched_players:
            try:
                _, matched_players = report_has_tc_players(session, auth_pool, candidate.report_code)
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
        f"{failed} failures."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
