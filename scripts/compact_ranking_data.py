from __future__ import annotations

import argparse
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RANKINGS_DIR = PROJECT_ROOT / "data" / "rankings"
SHARD_TARGET_BYTES = 45 * 1024 * 1024
REPORT_TOP_LEVEL_DROP_KEYS = {"fflogs_raw", "master_data", "matched_players"}
FIGHT_DROP_KEYS = {"fflogs_raw"}


def assert_inside(parent: Path, child: Path) -> None:
    parent_resolved = parent.resolve()
    child_resolved = child.resolve()
    if parent_resolved != child_resolved and parent_resolved not in child_resolved.parents:
        raise RuntimeError(f"路徑超出允許範圍：{child}")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(content, file, ensure_ascii=False, separators=(",", ":"))
        file.write("\n")
    os.replace(temp_path, path)


def compact_report(report: Any) -> tuple[Any, int]:
    if not isinstance(report, dict):
        return report, 0

    removed_fields = 0
    for key in REPORT_TOP_LEVEL_DROP_KEYS:
        if key in report:
            report.pop(key, None)
            removed_fields += 1

    fights = report.get("fights")
    if isinstance(fights, list):
        for fight in fights:
            if not isinstance(fight, dict):
                continue
            for key in FIGHT_DROP_KEYS:
                if key in fight:
                    fight.pop(key, None)
                    removed_fields += 1

    return report, removed_fields


def shard_relative_path(shard_path: Path) -> str:
    return shard_path.relative_to(PROJECT_ROOT).as_posix()


def serialized_json_size(content: Any) -> int:
    return len(json.dumps(content, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1


def load_reports(main_path: Path, ranking: dict[str, Any]) -> dict[str, Any]:
    reports: dict[str, Any] = {}
    inline_reports = ranking.get("reports")
    if isinstance(inline_reports, dict):
        reports.update(inline_reports)

    for shard_text in ranking.get("report_shards") or []:
        if not isinstance(shard_text, str) or not shard_text:
            continue
        shard_path = PROJECT_ROOT / shard_text
        assert_inside(RANKINGS_DIR, shard_path)
        shard_content = read_json(shard_path, {})
        if isinstance(shard_content, dict):
            reports.update(shard_content)

    return reports


def build_report_shard_plan(reports: dict[str, Any]) -> list[dict[str, Any]]:
    shards: list[dict[str, Any]] = []
    current_shard: dict[str, Any] = {}
    current_size = 2

    def flush_current_shard() -> None:
        nonlocal current_shard, current_size
        if not current_shard:
            return
        shards.append(current_shard)
        current_shard = {}
        current_size = 2

    for report_code, report in sorted(reports.items(), key=lambda item: str(item[0])):
        report_code_text = str(report_code)
        report_text = json.dumps(report, ensure_ascii=False, separators=(",", ":"))
        entry_size = (
            len(json.dumps(report_code_text, ensure_ascii=False).encode("utf-8"))
            + 1
            + len(report_text.encode("utf-8"))
            + 1
        )
        if current_shard and current_size + entry_size > SHARD_TARGET_BYTES:
            flush_current_shard()
        current_shard[report_code_text] = report
        current_size += entry_size

    flush_current_shard()
    return shards


def write_report_shards(main_path: Path, reports: dict[str, Any]) -> list[str]:
    shard_dir = main_path.with_suffix(".reports")
    assert_inside(RANKINGS_DIR, shard_dir)
    temp_dir = shard_dir.with_name(f".{shard_dir.name}.{os.getpid()}.{time.time_ns()}.tmp")
    assert_inside(RANKINGS_DIR, temp_dir)

    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True, exist_ok=True)

    shard_paths: list[str] = []
    planned_shards = build_report_shard_plan(reports)

    for shard_index, shard_content in enumerate(planned_shards):
        shard_path = temp_dir / f"{shard_index:03d}.json"
        write_json(shard_path, shard_content)
        shard_paths.append(shard_relative_path(shard_dir / shard_path.name))

    if shard_dir.exists():
        shutil.rmtree(shard_dir)
    if shard_paths:
        temp_dir.rename(shard_dir)
    else:
        shutil.rmtree(temp_dir)

    return shard_paths


def compact_main_file(main_path: Path, *, dry_run: bool) -> dict[str, Any]:
    ranking = read_json(main_path, {})
    if not isinstance(ranking, dict):
        return {
            "path": str(main_path),
            "reports": 0,
            "removed_fields": 0,
            "before_bytes": main_path.stat().st_size,
            "after_bytes": main_path.stat().st_size,
            "before_shards": 0,
            "after_shards": 0,
            "changed": False,
        }

    before_bytes = main_path.stat().st_size
    before_shards = len(ranking.get("report_shards") or [])
    for shard_text in ranking.get("report_shards") or []:
        if isinstance(shard_text, str) and shard_text:
            shard_path = PROJECT_ROOT / shard_text
            if shard_path.exists():
                before_bytes += shard_path.stat().st_size

    reports = load_reports(main_path, ranking)
    removed_fields = 0
    for report_code, report in list(reports.items()):
        reports[report_code], report_removed_fields = compact_report(report)
        removed_fields += report_removed_fields

    updated_ranking = dict(ranking)
    updated_ranking.pop("reports", None)
    planned_shards = build_report_shard_plan(reports)
    planned_shard_paths = [
        shard_relative_path(main_path.with_suffix(".reports") / f"{index:03d}.json")
        for index, _ in enumerate(planned_shards)
    ]
    if planned_shard_paths:
        updated_ranking["report_shards"] = planned_shard_paths
    else:
        updated_ranking.pop("report_shards", None)
        updated_ranking["reports"] = {}
    after_shards = len(planned_shards)
    after_bytes = serialized_json_size(updated_ranking) + sum(serialized_json_size(shard) for shard in planned_shards)

    if not dry_run:
        write_report_shards(main_path, reports)
        write_json(main_path, updated_ranking)

        after_bytes = main_path.stat().st_size
        for shard_text in updated_ranking.get("report_shards") or []:
            shard_path = PROJECT_ROOT / shard_text
            if shard_path.exists():
                after_bytes += shard_path.stat().st_size

    return {
        "path": str(main_path.relative_to(PROJECT_ROOT)),
        "reports": len(reports),
        "removed_fields": removed_fields,
        "before_bytes": before_bytes,
        "after_bytes": after_bytes,
        "before_shards": before_shards,
        "after_shards": after_shards,
        "changed": removed_fields > 0 or after_shards != before_shards,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="移除 data/rankings 內可重查的大型 FFLogs raw 欄位並重新分片。")
    parser.add_argument("--dry-run", action="store_true", help="只列出預估異動，不寫入檔案。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    main_files = sorted(path for path in RANKINGS_DIR.glob("*.json") if path.is_file())
    summaries = [compact_main_file(path, dry_run=args.dry_run) for path in main_files]

    changed = [summary for summary in summaries if summary["changed"]]
    total_before = sum(int(summary["before_bytes"]) for summary in summaries)
    total_after = sum(int(summary["after_bytes"]) for summary in summaries)
    total_removed_fields = sum(int(summary["removed_fields"]) for summary in summaries)
    total_reports = sum(int(summary["reports"]) for summary in summaries)

    mode = "dry-run" if args.dry_run else "written"
    print(
        f"Ranking compact {mode}: {len(changed)} files changed, "
        f"{total_reports} reports scanned, {total_removed_fields} raw fields removed."
    )
    print(
        f"Bytes: {total_before:,} -> {total_after:,} "
        f"({total_before - total_after:,} saved)."
    )
    for summary in changed:
        print(
            f"- {summary['path']}: reports={summary['reports']}, "
            f"removed_fields={summary['removed_fields']}, "
            f"shards={summary['before_shards']}->{summary['after_shards']}, "
            f"bytes={int(summary['before_bytes']):,}->{int(summary['after_bytes']):,}"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
