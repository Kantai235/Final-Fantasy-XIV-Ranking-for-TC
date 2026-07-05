from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_xivanalysis_gcd_sample as audit_gcd  # noqa: E402
import backfill_gcd_coverage as local_gcd  # noqa: E402
import backfill_gcd_coverage_xivanalysis as xiv_gcd  # noqa: E402


for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", line_buffering=True)


DEFAULT_TOLERANCE = 0.0
XIVANALYSIS_PAGE_SOURCE = "xivanalysis_page"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "用已落地的 FFLogs payload 與 xivanalysis GCD 答案快取，"
            "重新計算既有稽核 JSON。"
        )
    )
    parser.add_argument("audit_report", type=Path, help="既有 docs/gcd_xivanalysis_audit_*.json。")
    parser.add_argument(
        "--output-path",
        type=Path,
        default=None,
        help="重算結果輸出路徑；預設寫到同目錄的 *.cache_recompute.json。",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=xiv_gcd.DEFAULT_AUDIT_CACHE_DIR,
        help="xivanalysis GCD 稽核快取目錄。",
    )
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE, help="顯示百分點容許差異。")
    parser.add_argument("--encounter-key", action="append", default=[], help="只重算指定副本 key，可重複指定。")
    parser.add_argument("--required-jobs", nargs="*", default=None, help="只重算指定職業。")
    parser.add_argument(
        "--exclude-report-codes",
        nargs="*",
        default=None,
        help="排除已無法由 FFLogs / xivanalysis proxy 重算的 report code。",
    )
    parser.add_argument(
        "--audit-fight-start",
        type=int,
        default=None,
        help="只重算稽核報告中第 N 個 fight group 之後的資料，1-based 且包含 N。",
    )
    parser.add_argument(
        "--audit-fight-end",
        type=int,
        default=None,
        help="只重算稽核報告中第 N 個 fight group 之前的資料，1-based 且包含 N。",
    )
    parser.add_argument("--limit", type=int, default=None, help="最多重算幾位玩家，供快速診斷。")
    parser.add_argument("--progress-every", type=int, default=100, help="每 N 位玩家輸出進度；0 表示不輸出。")
    parser.add_argument(
        "--checkpoint-every-players",
        type=int,
        default=0,
        help="每 N 位已重算玩家將目前 partial JSON 寫入 output-path；0 表示只在完成時寫出。",
    )
    parser.add_argument(
        "--fetch-missing-fflogs-cache",
        action="store_true",
        help=(
            "缺少 FFLogs Casts graph / raw events / damage events 快取時，"
            "使用本機 FFLogs 憑證補抓並寫入 cache；預設為純離線模式。"
        ),
    )
    parser.add_argument(
        "--skip-candidate-index",
        action="store_true",
        help=(
            "不要預先掃描 data/rankings/ 建立 candidate index；"
            "適合 report_fights 快取已補齊的離線重算，可大幅縮短啟動時間。"
        ),
    )
    parser.add_argument(
        "--raw-event-source",
        choices=("graphql", "xivanalysis-proxy", "auto"),
        default="graphql",
        help=(
            "raw-events 副本離線重算的事件來源。graphql 使用正式資料管線快取；"
            "xivanalysis-proxy 使用 seed_xivanalysis_gcd_cache.py 補種的外站 proxy events；"
            "auto 優先使用 proxy，缺少時回退 graphql。"
        ),
    )
    return parser.parse_args()


def number(value: Any) -> float | None:
    return local_gcd.to_number(value)


def int_value(value: Any) -> int | None:
    return local_gcd.to_int(value)


def should_preserve_xivanalysis_page_zero(player_row: dict[str, Any], xivanalysis_percent: float) -> bool:
    """Preserve explicit xivanalysis page zeroes that were applied to stored data.

    A few legacy xivanalysis pages render the ABC answer as 0.0 even when FFLogs
    raw events can be recomputed locally.  The audit JSON records those rows as
    `xivanalysis_page` values; same-source recompute must keep that external page
    answer so the verification target stays identical to the original page audit.
    """

    if abs(float(xivanalysis_percent)) > 0.0001:
        return False

    sources = {
        str(player_row.get("current_source") or ""),
        str(player_row.get("stored_source") or ""),
    }
    if XIVANALYSIS_PAGE_SOURCE not in sources:
        return False

    current_percent = number(player_row.get("current_percent"))
    stored_percent = number(player_row.get("stored_percent"))
    known_page_zero = any(
        value is not None and abs(float(value)) <= 0.0001
        for value in (current_percent, stored_percent)
    )
    return known_page_zero


def xivanalysis_page_zero_coverage(player_row: dict[str, Any]) -> dict[str, Any]:
    """Build displayable coverage for legacy xivanalysis page zeroes."""

    return {
        "covered_time_ms": 0.0,
        "denominator_ms": 1.0,
        "percent": 0.0,
        "calculation_version": local_gcd.GCD_CALCULATION_VERSION,
        "source": XIVANALYSIS_PAGE_SOURCE,
        "xivanalysis_url": player_row.get("xivanalysis_url"),
        "recompute_override": "preserve_xivanalysis_page_zero",
    }


def audit_output_path(input_path: Path) -> Path:
    return input_path.with_name(f"{input_path.stem}.cache_recompute.json")


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f"{path.name}.tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_path.replace(path)


def build_recompute_result(
    *,
    audit_report_path: Path,
    cache_dir: Path,
    tolerance: float,
    raw_event_source: str,
    encounter_filter: set[str],
    job_filter: set[str],
    excluded_report_codes: set[str],
    audit_fight_start: int | None,
    audit_fight_end: int | None,
    limit: int | None,
    fetch_missing_fflogs_cache: bool,
    skip_candidate_index: bool,
    summary: dict[str, int],
    results_by_fight: dict[tuple[str, str, int], dict[str, Any]],
) -> dict[str, Any]:
    return {
        "source_report": str(audit_report_path),
        "cache_dir": str(cache_dir),
        "tolerance": tolerance,
        "raw_event_source": raw_event_source,
        "filters": {
            "encounter_key": sorted(encounter_filter),
            "required_jobs": sorted(job_filter),
            "excluded_report_codes": sorted(excluded_report_codes),
            "audit_fight_start": audit_fight_start,
            "audit_fight_end": audit_fight_end,
            "limit": limit,
            "fetch_missing_fflogs_cache": bool(fetch_missing_fflogs_cache),
            "skip_candidate_index": bool(skip_candidate_index),
        },
        "summary": summary,
        "fights": sorted(
            results_by_fight.values(),
            key=lambda fight: (
                str(fight.get("encounter_key") or ""),
                str(fight.get("report_code") or ""),
                int_value(fight.get("fight_id")) or 0,
            ),
        ),
    }


def iter_audit_rows(report: dict[str, Any]) -> Iterator[tuple[int, dict[str, Any], dict[str, Any]]]:
    fights = report.get("fights")
    if not isinstance(fights, list):
        return

    for fight_index, fight in enumerate(fights, start=1):
        if not isinstance(fight, dict):
            continue

        players = fight.get("players")
        if not isinstance(players, list):
            continue

        for player in players:
            if isinstance(player, dict):
                yield fight_index, fight, player


def row_field(fight: dict[str, Any], player: dict[str, Any], key: str) -> Any:
    return player.get(key) if player.get(key) is not None else fight.get(key)


def build_candidate_index(
    encounters: dict[str, dict[str, Any]],
    encounter_filter: set[str],
) -> dict[tuple[str, str, int, int], local_gcd.GcdCandidate]:
    selected_encounters = (
        {key: encounter for key, encounter in encounters.items() if key in encounter_filter}
        if encounter_filter
        else encounters
    )
    categories = {str(encounter.get("category") or "") for encounter in selected_encounters.values()}
    fight_groups, _ = audit_gcd.collect_fight_groups(selected_encounters, categories=categories)
    index: dict[tuple[str, str, int, int], local_gcd.GcdCandidate] = {}
    for fight_group in fight_groups:
        for candidate in fight_group.candidates:
            source_id = int_value(candidate.player.get("fflogs_id"))
            if source_id is None:
                continue
            index.setdefault(
                (fight_group.encounter_key, fight_group.report_code, fight_group.fight_id, source_id),
                candidate,
            )
    return index


def make_candidate(
    *,
    fight_row: dict[str, Any],
    player_row: dict[str, Any],
    encounters: dict[str, dict[str, Any]],
    cache: xiv_gcd.GcdAuditCache,
    candidate_index: dict[tuple[str, str, int, int], local_gcd.GcdCandidate],
) -> local_gcd.GcdCandidate:
    encounter_key = str(row_field(fight_row, player_row, "encounter_key") or "")
    report_code = str(row_field(fight_row, player_row, "report_code") or "")
    fight_id = int_value(row_field(fight_row, player_row, "fight_id"))
    fflogs_id = int_value(player_row.get("fflogs_id"))

    if not encounter_key:
        raise RuntimeError("audit row 缺少 encounter_key。")
    if not report_code:
        raise RuntimeError("audit row 缺少 report_code。")
    if fight_id is None:
        raise RuntimeError("audit row 缺少 fight_id。")
    if fflogs_id is None:
        raise RuntimeError("audit row 缺少 fflogs_id，無法對應 xivanalysis player sourceID。")

    indexed_candidate = candidate_index.get((encounter_key, report_code, fight_id, fflogs_id))
    cached_fight = cache.find_report_fight_by_id(report_code, fight_id)
    if cached_fight and indexed_candidate is not None:
        # 早期快取只保存 FFLogs fight list，沒有排行榜分片裡的 players/sourceID 脈絡；
        # raw targetability 推導需要 friendly id 集合，所以離線重算時順手把舊快取補厚。
        cache.write_report_fight_metadata(indexed_candidate, indexed_candidate.fight)
        cached_fight = cache.find_report_fight_by_id(report_code, fight_id) or cached_fight
    if not cached_fight:
        if indexed_candidate is None:
            raise RuntimeError(f"缺少 FFLogs report_fights 快取：{report_code} fight={fight_id}")
        # 舊版長跑稽核只會留下 raw/casts payload 與 xivanalysis 答案；如果本機分片仍找得到
        # 同一筆候選，順手補上 fight metadata，之後再重算就能完全走 cache-only。
        cache.write_report_fight_metadata(indexed_candidate, indexed_candidate.fight)
        return indexed_candidate
    if (
        indexed_candidate is None
        and not xiv_gcd.GcdAuditCache._fight_has_players(cached_fight)
        and local_gcd.gcd_core.should_use_raw_events_for_gcd(encounter_key, str(player_row.get("job") or ""))
    ):
        raise RuntimeError(
            "raw-events 離線重算需要 fight players/sourceID；"
            f"{report_code} fight={fight_id} 的 report_fights cache 太薄，"
            "請移除 --skip-candidate-index 或先補種完整 metadata。"
        )

    encounter = encounters.get(encounter_key, {"key": encounter_key, "name": encounter_key})
    player = {
        "name": player_row.get("player") or player_row.get("name"),
        "server": player_row.get("server"),
        "job": player_row.get("job"),
        "fflogs_id": fflogs_id,
        # GCD 離線重算只需要玩家身分與 sourceID；dps 補值是為了沿用既有 candidate 型別。
        "dps": number(player_row.get("current_percent")) or 1,
    }

    return local_gcd.GcdCandidate(
        encounter_key=encounter_key,
        encounter=encounter,
        ranking={},
        report_code=report_code,
        report={"report_code": report_code},
        fight=cached_fight,
        player=player,
        sort_time=0,
    )


def recompute(args: argparse.Namespace) -> dict[str, Any]:
    audit_report_path = args.audit_report
    output_path = args.output_path or audit_output_path(audit_report_path)
    report = json.loads(audit_report_path.read_text(encoding="utf-8"))
    encounters = local_gcd.load_all_encounters()
    encounter_filter = {str(key) for key in args.encounter_key if str(key)}
    job_filter = {str(job) for job in args.required_jobs or [] if str(job)}
    excluded_report_codes = {str(code) for code in args.exclude_report_codes or [] if str(code)}
    report_encounter_keys = {
        str(row_field(fight_row, player_row, "encounter_key") or "")
        for _, fight_row, player_row in iter_audit_rows(report)
    }
    report_encounter_keys.discard("")
    candidate_encounter_filter = encounter_filter or report_encounter_keys
    cache = xiv_gcd.GcdAuditCache(args.cache_dir)
    calculator = xiv_gcd.LocalGcdFallback(
        audit_cache=cache,
        cache_only=not args.fetch_missing_fflogs_cache,
        raw_event_source=args.raw_event_source,
    )
    candidate_index = {} if args.skip_candidate_index else build_candidate_index(encounters, candidate_encounter_filter)

    results_by_fight: dict[tuple[str, str, int], dict[str, Any]] = {}
    summary = {
        "checked": 0,
        "matched": 0,
        "mismatched": 0,
        "errors": 0,
        "skipped_no_xivanalysis_answer": 0,
        "skipped_by_filter": 0,
        "gt_0_5": 0,
        "gt_1_0": 0,
    }
    previous_fight_key: tuple[str, str, int] | None = None

    audit_fight_start = max(1, args.audit_fight_start) if args.audit_fight_start is not None else None
    audit_fight_end = max(1, args.audit_fight_end) if args.audit_fight_end is not None else None

    for audit_fight_index, fight_row, player_row in iter_audit_rows(report):
        encounter_key = str(row_field(fight_row, player_row, "encounter_key") or "")
        report_code_for_filter = str(row_field(fight_row, player_row, "report_code") or "")
        job = str(player_row.get("job") or "")
        if audit_fight_start is not None and audit_fight_index < audit_fight_start:
            summary["skipped_by_filter"] += 1
            continue
        if audit_fight_end is not None and audit_fight_index > audit_fight_end:
            summary["skipped_by_filter"] += 1
            continue
        if report_code_for_filter in excluded_report_codes:
            summary["skipped_by_filter"] += 1
            continue
        if encounter_filter and encounter_key not in encounter_filter:
            summary["skipped_by_filter"] += 1
            continue
        if job_filter and job not in job_filter:
            summary["skipped_by_filter"] += 1
            continue

        xivanalysis_percent = number(player_row.get("xivanalysis_percent"))
        if xivanalysis_percent is None:
            summary["skipped_no_xivanalysis_answer"] += 1
            continue

        if args.limit is not None and summary["checked"] >= args.limit:
            break

        report_code = str(row_field(fight_row, player_row, "report_code") or "")
        fight_id = int_value(row_field(fight_row, player_row, "fight_id")) or 0
        fight_key = (encounter_key, report_code, fight_id)
        if previous_fight_key is not None and fight_key != previous_fight_key:
            # raw events payload 可能很大；離線重算只需要同一 fight 內共用快取，跨 fight 應釋放記憶體。
            calculator.clear_cached_fight_data()
        previous_fight_key = fight_key

        output_fight = results_by_fight.setdefault(
            fight_key,
            {
                "encounter_key": encounter_key,
                "report_code": report_code,
                "fight_id": fight_id,
                "players": [],
            },
        )

        result = {
            "player": player_row.get("player") or player_row.get("name"),
            "server": player_row.get("server"),
            "job": job,
            "fflogs_id": int_value(player_row.get("fflogs_id")),
            "xivanalysis_percent": xivanalysis_percent,
            "state": "error",
        }

        try:
            if should_preserve_xivanalysis_page_zero(player_row, xivanalysis_percent):
                coverage = xivanalysis_page_zero_coverage(player_row)
            else:
                candidate = make_candidate(
                    fight_row=fight_row,
                    player_row=player_row,
                    encounters=encounters,
                    cache=cache,
                    candidate_index=candidate_index,
                )
                coverage = calculator.calculate(candidate)
                if coverage and encounter_key == "unreal_byakko":
                    coverage = local_gcd.gcd_core.select_byakko_display_edge_coverage(
                        coverage,
                        job=job,
                    )
            local_percent = audit_gcd.display_percent_from_coverage(coverage, None)
            if local_percent is None:
                raise RuntimeError("本地 GCD 計算未回傳可顯示百分比。")

            difference = round(local_percent - xivanalysis_percent, 3)
            matched = abs(difference) <= args.tolerance
            result.update(
                {
                    "state": "matched" if matched else "mismatched",
                    "local_percent": local_percent,
                    "difference": difference,
                    "local_coverage": coverage,
                }
            )
            if matched:
                summary["matched"] += 1
            else:
                summary["mismatched"] += 1
            if abs(difference) > 0.5:
                summary["gt_0_5"] += 1
            if abs(difference) > 1.0:
                summary["gt_1_0"] += 1
        except Exception as error:
            summary["errors"] += 1
            result["error"] = f"{type(error).__name__}: {str(error)[:500]}"

        output_fight["players"].append(result)
        summary["checked"] += 1
        if args.progress_every and summary["checked"] % args.progress_every == 0:
            print(
                "已離線重算 "
                f"{summary['checked']} players；"
                f"mismatched={summary['mismatched']} errors={summary['errors']} gt1={summary['gt_1_0']}"
                f" gt0.5={summary['gt_0_5']}"
            )
        if args.checkpoint_every_players and summary["checked"] % args.checkpoint_every_players == 0:
            write_json_atomic(
                output_path,
                build_recompute_result(
                    audit_report_path=audit_report_path,
                    cache_dir=args.cache_dir,
                    tolerance=args.tolerance,
                    raw_event_source=args.raw_event_source,
                    encounter_filter=encounter_filter,
                    job_filter=job_filter,
                    excluded_report_codes=excluded_report_codes,
                    audit_fight_start=audit_fight_start,
                    audit_fight_end=audit_fight_end,
                    limit=args.limit,
                    fetch_missing_fflogs_cache=bool(args.fetch_missing_fflogs_cache),
                    skip_candidate_index=bool(args.skip_candidate_index),
                    summary=summary,
                    results_by_fight=results_by_fight,
                ),
            )

    return build_recompute_result(
        audit_report_path=audit_report_path,
        cache_dir=args.cache_dir,
        tolerance=args.tolerance,
        raw_event_source=args.raw_event_source,
        encounter_filter=encounter_filter,
        job_filter=job_filter,
        excluded_report_codes=excluded_report_codes,
        audit_fight_start=audit_fight_start,
        audit_fight_end=audit_fight_end,
        limit=args.limit,
        fetch_missing_fflogs_cache=bool(args.fetch_missing_fflogs_cache),
        skip_candidate_index=bool(args.skip_candidate_index),
        summary=summary,
        results_by_fight=results_by_fight,
    )


def main() -> int:
    args = parse_args()
    output_path = args.output_path or audit_output_path(args.audit_report)
    result = recompute(args)
    write_json_atomic(output_path, result)
    print(f"已寫出離線重算結果：{output_path}")
    print(json.dumps(result["summary"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
