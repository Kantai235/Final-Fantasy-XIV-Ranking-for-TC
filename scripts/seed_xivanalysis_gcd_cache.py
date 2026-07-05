from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import audit_xivanalysis_gcd_sample as audit_gcd  # noqa: E402
import backfill_gcd_coverage as local_gcd  # noqa: E402
import backfill_gcd_coverage_xivanalysis as xiv_gcd  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", line_buffering=True)


def read_json(path: Path) -> dict[str, Any]:
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise RuntimeError(f"{path} 不是稽核 JSON 物件。")
    return content


def all_encounter_categories(encounters: dict[str, dict[str, Any]]) -> set[str]:
    return {str(encounter.get("category") or "") for encounter in encounters.values()}


def build_candidate_index() -> dict[tuple[str, str, int, int], local_gcd.GcdCandidate]:
    encounters = local_gcd.load_all_encounters()
    categories = all_encounter_categories(encounters)
    fights, _ = audit_gcd.collect_fight_groups(encounters, categories=categories)

    index: dict[tuple[str, str, int, int], local_gcd.GcdCandidate] = {}
    for fight in fights:
        for candidate in fight.candidates:
            source_id = local_gcd.to_int(candidate.player.get("fflogs_id"))
            if source_id is None:
                continue
            index[(fight.encounter_key, fight.report_code, fight.fight_id, source_id)] = candidate
    return index


def candidate_fight_key(candidate: local_gcd.GcdCandidate) -> tuple[str, int, float, float]:
    fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
    start_time = local_gcd.first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
    end_time = local_gcd.first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        raise RuntimeError(f"候選缺少 fight_id 或時間窗，無法補種 FFLogs proxy 快取：{candidate.label}")
    return (candidate.report_code, fight_id, start_time, end_time)


def fetch_xivanalysis_proxy_json(
    session: Any,
    path: str,
    *,
    params: dict[str, Any],
    timeout_seconds: int,
) -> dict[str, Any]:
    """讀取 xivanalysis proxy 的 FFLogs v1 JSON。

    這裡刻意走 xivanalysis 部署正在使用的 `/proxy/fflogs/`，而不是 FFLogs
    GraphQL。人工外站稽核的目標是對齊「頁面實際顯示值」，因此保存頁面同源
    proxy payload 能讓後續演算法修正時重放同一份 fight/event 輸入，不需要再
    逐頁打開 xivanalysis。
    """

    url = f"{xiv_gcd.XIVANALYSIS_BASE_URL.rstrip('/')}/proxy/fflogs/{path.lstrip('/')}"
    response = session.get(
        url,
        params=params,
        timeout=timeout_seconds,
        headers={"User-Agent": "ffxiv-tc-ranking-xivanalysis-gcd-cache/1.0"},
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError(f"xivanalysis proxy 回傳非 JSON 物件：{url}")
    return payload


def proxy_query_number(value: float | int) -> int | float:
    """讓 xivanalysis proxy timestamp 保持頁面實際使用的整數格式。

    `requests` 會把 Python float 直接序列化成 `269784604.0`；FFLogs v1 proxy
    對這種 timestamp 會回傳 200 但 events 為空，導致快取看似成功卻無法離線
    重放外站頁面資料。因此只要數值本身是整數時間戳，就明確轉回 int。
    """
    numeric = local_gcd.to_number(value)
    if numeric is None:
        return value
    if float(numeric).is_integer():
        return int(numeric)
    return numeric


def fetch_xivanalysis_proxy_report_fights(
    session: Any,
    report_code: str,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    return fetch_xivanalysis_proxy_json(
        session,
        f"report/fights/{report_code}",
        params={"translate": "true"},
        timeout_seconds=timeout_seconds,
    )


def fetch_xivanalysis_proxy_events(
    session: Any,
    candidate: local_gcd.GcdCandidate,
    *,
    timeout_seconds: int,
) -> dict[str, Any]:
    fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
    start_time = local_gcd.first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
    end_time = local_gcd.first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        raise RuntimeError(f"候選缺少 fight_id 或時間窗，無法補種 FFLogs proxy events：{candidate.label}")

    events: list[dict[str, Any]] = []
    pages: list[dict[str, Any]] = []
    cursor = start_time
    while cursor is not None and cursor < end_time:
        payload = fetch_xivanalysis_proxy_json(
            session,
            f"report/events/{candidate.report_code}",
            params={
                "start": proxy_query_number(cursor),
                "end": proxy_query_number(end_time),
                "translate": "true",
            },
            timeout_seconds=timeout_seconds,
        )
        page_events = payload.get("events")
        if isinstance(page_events, list):
            events.extend(event for event in page_events if isinstance(event, dict))
        pages.append(
            {
                "start": cursor,
                "end": end_time,
                "event_count": len(page_events) if isinstance(page_events, list) else 0,
                "next_page_timestamp": payload.get("nextPageTimestamp"),
            }
        )

        next_cursor = local_gcd.to_number(payload.get("nextPageTimestamp"))
        if next_cursor is None or next_cursor <= cursor:
            break
        cursor = next_cursor

    return {
        "events": events,
        "pages": pages,
    }


def is_proxy_report_fights_payload(payload: Any) -> bool:
    if not isinstance(payload, dict):
        return False
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    return (
        isinstance(data, dict)
        and isinstance(data.get("fights"), list)
        and isinstance(data.get("friendlies"), list)
        and isinstance(data.get("enemies"), list)
    )


def is_proxy_events_payload(payload: Any) -> bool:
    return (
        isinstance(payload, dict)
        and payload.get("source") == "xivanalysis_proxy_fflogs_v1"
        and isinstance(payload.get("events"), list)
        and len(payload.get("events") or []) > 0
    )


def seed_proxy_fflogs_cache(
    candidate: local_gcd.GcdCandidate,
    *,
    cache: xiv_gcd.GcdAuditCache,
    session: Any,
    refresh_cache: bool,
    timeout_seconds: int,
) -> tuple[bool, bool]:
    seeded_fights = False
    seeded_events = False

    cached_fights = cache.read_fflogs_payload("report_fights", candidate)
    if refresh_cache or not is_proxy_report_fights_payload(cached_fights):
        report_fights = fetch_xivanalysis_proxy_report_fights(
            session,
            candidate.report_code,
            timeout_seconds=timeout_seconds,
        )
        cache.write_fflogs_payload("report_fights", candidate, report_fights)
        seeded_fights = True

    cached_events = cache.read_fflogs_payload("xivanalysis_proxy_events", candidate)
    if refresh_cache or not is_proxy_events_payload(cached_events):
        events_payload = fetch_xivanalysis_proxy_events(
            session,
            candidate,
            timeout_seconds=timeout_seconds,
        )
        cache.merge_xivanalysis_proxy_events(
            candidate,
            {"events": events_payload["events"]},
            url=(
                f"{xiv_gcd.XIVANALYSIS_BASE_URL.rstrip('/')}/proxy/fflogs/"
                f"report/events/{candidate.report_code}"
            ),
        )
        seeded_events = True

    return seeded_fights, seeded_events


def seed_report(
    path: Path,
    *,
    cache: xiv_gcd.GcdAuditCache,
    candidate_index: dict[tuple[str, str, int, int], local_gcd.GcdCandidate],
    dry_run: bool,
    fetch_fflogs_proxy: bool,
    refresh_fflogs_proxy: bool,
    audit_fight_start: int | None,
    audit_fight_end: int | None,
    delay_ms: int,
    timeout_seconds: int,
) -> dict[str, int]:
    data = read_json(path)
    stats = {
        "checked": 0,
        "seeded": 0,
        "fflogs_proxy_fights_seeded": 0,
        "fflogs_proxy_events_seeded": 0,
        "fflogs_proxy_errors": 0,
        "missing_candidate": 0,
        "skipped_without_percent": 0,
        "skipped_without_source_id": 0,
    }
    seen_fights: set[tuple[str, int, float, float]] = set()
    session = local_gcd.fflogs.requests.Session() if fetch_fflogs_proxy and not dry_run else None

    for fight_index, fight in enumerate(data.get("fights") or [], start=1):
        if not isinstance(fight, dict):
            continue
        if audit_fight_start is not None and fight_index < audit_fight_start:
            continue
        if audit_fight_end is not None and fight_index > audit_fight_end:
            continue
        encounter_key = str(fight.get("encounter_key") or "")
        report_code = str(fight.get("report_code") or "")
        fight_id = local_gcd.to_int(fight.get("fight_id"))
        if fight_id is None:
            continue

        for player in fight.get("players") or []:
            if not isinstance(player, dict):
                continue
            stats["checked"] += 1
            percent = local_gcd.to_number(player.get("xivanalysis_percent"))
            if percent is None:
                stats["skipped_without_percent"] += 1
                continue
            source_id = local_gcd.to_int(player.get("fflogs_id"))
            if source_id is None:
                stats["skipped_without_source_id"] += 1
                continue

            candidate = candidate_index.get((encounter_key, report_code, fight_id, source_id))
            if candidate is None:
                stats["missing_candidate"] += 1
                continue

            if not dry_run:
                url = str(player.get("xivanalysis_url") or xiv_gcd.build_xivanalysis_url(candidate))
                cache.write_xivanalysis_result(candidate, percent=percent, url=url)
            stats["seeded"] += 1

            if not fetch_fflogs_proxy:
                continue

            fight_key = candidate_fight_key(candidate)
            if fight_key in seen_fights:
                continue
            seen_fights.add(fight_key)

            if dry_run:
                cached_fights = cache.read_fflogs_payload("report_fights", candidate)
                cached_events = cache.read_fflogs_payload("xivanalysis_proxy_events", candidate)
                if refresh_fflogs_proxy or not is_proxy_report_fights_payload(cached_fights):
                    stats["fflogs_proxy_fights_seeded"] += 1
                if refresh_fflogs_proxy or not is_proxy_events_payload(cached_events):
                    stats["fflogs_proxy_events_seeded"] += 1
                continue

            try:
                assert session is not None
                seeded_fights, seeded_events = seed_proxy_fflogs_cache(
                    candidate,
                    cache=cache,
                    session=session,
                    refresh_cache=refresh_fflogs_proxy,
                    timeout_seconds=timeout_seconds,
                )
                if seeded_fights:
                    stats["fflogs_proxy_fights_seeded"] += 1
                if seeded_events:
                    stats["fflogs_proxy_events_seeded"] += 1
                if delay_ms > 0 and (seeded_fights or seeded_events):
                    time.sleep(delay_ms / 1000)
            except Exception as error:  # noqa: BLE001
                stats["fflogs_proxy_errors"] += 1
                print(
                    f"FFLogs proxy 快取補種失敗：{candidate.report_code} "
                    f"fight={candidate.fight.get('fight_id')} {type(error).__name__}: {error}",
                    file=sys.stderr,
                )

    return stats


def merge_stats(total: dict[str, int], current: dict[str, int]) -> None:
    for key, value in current.items():
        total[key] = total.get(key, 0) + value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "將既有 xivanalysis GCD 稽核報告中的外站答案導入本機快取。"
            "此工具不會修改 data/、public/data/ 或排行榜正式資料。"
        )
    )
    parser.add_argument(
        "reports",
        nargs="+",
        type=Path,
        help="要導入的 docs/gcd_xivanalysis_audit_*.json 檔案。",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=xiv_gcd.DEFAULT_AUDIT_CACHE_DIR,
        help="xivanalysis GCD 稽核快取目錄。",
    )
    parser.add_argument("--dry-run", action="store_true", help="只統計可導入筆數，不寫入快取。")
    parser.add_argument(
        "--fetch-fflogs-proxy",
        action="store_true",
        help=(
            "同時透過 xivanalysis /proxy/fflogs/ 補種 report/fights 與 report/events 快取，"
            "供之後離線重放外站實際輸入資料。"
        ),
    )
    parser.add_argument(
        "--refresh-fflogs-proxy",
        action="store_true",
        help="重新抓取並覆寫既有 xivanalysis proxy FFLogs 快取。",
    )
    parser.add_argument(
        "--audit-fight-start",
        type=int,
        default=None,
        help="只處理稽核輸出中的第 N 個 fight group（1-based）起點。",
    )
    parser.add_argument(
        "--audit-fight-end",
        type=int,
        default=None,
        help="只處理稽核輸出中的第 N 個 fight group（1-based）終點。",
    )
    parser.add_argument("--delay-ms", type=int, default=0, help="補種每場 FFLogs proxy 快取後等待毫秒數。")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="xivanalysis proxy 單次請求逾時秒數。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report_paths = [path if path.is_absolute() else PROJECT_ROOT / path for path in args.reports]
    missing = [path for path in report_paths if not path.exists()]
    if missing:
        for path in missing:
            print(f"找不到稽核報告：{path}", file=sys.stderr)
        return 1

    print("建立本地 report/fight/player 索引...")
    candidate_index = build_candidate_index()
    print(f"索引候選玩家：{len(candidate_index)}")

    cache_dir = args.cache_dir if args.cache_dir.is_absolute() else PROJECT_ROOT / args.cache_dir
    cache = xiv_gcd.GcdAuditCache(cache_dir)
    total: dict[str, int] = {}
    for path in report_paths:
        stats = seed_report(
            path,
            cache=cache,
            candidate_index=candidate_index,
            dry_run=args.dry_run,
            fetch_fflogs_proxy=bool(args.fetch_fflogs_proxy),
            refresh_fflogs_proxy=bool(args.refresh_fflogs_proxy),
            audit_fight_start=max(1, args.audit_fight_start) if args.audit_fight_start is not None else None,
            audit_fight_end=max(1, args.audit_fight_end) if args.audit_fight_end is not None else None,
            delay_ms=max(0, args.delay_ms),
            timeout_seconds=max(1, args.timeout_seconds),
        )
        merge_stats(total, stats)
        print(
            f"{path.name}: checked={stats['checked']} seeded={stats['seeded']} "
            f"fflogs_proxy_fights_seeded={stats['fflogs_proxy_fights_seeded']} "
            f"fflogs_proxy_events_seeded={stats['fflogs_proxy_events_seeded']} "
            f"fflogs_proxy_errors={stats['fflogs_proxy_errors']} "
            f"missing_candidate={stats['missing_candidate']} "
            f"skipped_without_percent={stats['skipped_without_percent']} "
            f"skipped_without_source_id={stats['skipped_without_source_id']}"
        )

    print(
        f"總計：checked={total.get('checked', 0)} seeded={total.get('seeded', 0)} "
        f"fflogs_proxy_fights_seeded={total.get('fflogs_proxy_fights_seeded', 0)} "
        f"fflogs_proxy_events_seeded={total.get('fflogs_proxy_events_seeded', 0)} "
        f"fflogs_proxy_errors={total.get('fflogs_proxy_errors', 0)} "
        f"missing_candidate={total.get('missing_candidate', 0)} "
        f"skipped_without_percent={total.get('skipped_without_percent', 0)} "
        f"skipped_without_source_id={total.get('skipped_without_source_id', 0)} "
        f"cache_dir={cache_dir}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
