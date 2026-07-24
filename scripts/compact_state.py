from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from fflogs_pipeline import state_store


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "data" / "state.json"
GITHUB_SINGLE_BLOB_LIMIT_BYTES = 100 * 1024 * 1024


def compact_json_bytes(content: Any) -> bytes:
    return state_store.compact_json_bytes(content)


def on_disk_state_storage_sizes(state_path: Path) -> dict[Path, int]:
    paths = [state_path]
    shard_directory = state_store.checked_reports_directory(state_path)
    if shard_directory.exists():
        paths.extend(sorted(shard_directory.glob("*.json")))
    return {path: path.stat().st_size for path in paths if path.exists()}


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def compact_report_checkpoint_timestamps(state: dict[str, Any]) -> dict[str, Any]:
    # checked_reports / processed_reports 是跨輪去重與續跑的核心資產；壓縮時不能移除
    # report code 或 status。processed_at_iso 只是 processed_at 的可重建顯示鏡像，
    # 在數十萬筆 checkpoint 上會讓 state.json 很快撞到 GitHub 100 MiB 單檔限制。
    summary = {
        "records_changed": 0,
        "removed_redundant_processed_at_iso": 0,
    }
    encounters = state.get("encounters")
    if not isinstance(encounters, dict):
        return summary

    for encounter_state in encounters.values():
        if not isinstance(encounter_state, dict):
            continue

        for field_name in ("checked_reports", "processed_reports"):
            reports = encounter_state.get(field_name)
            if not isinstance(reports, dict):
                continue

            for record in reports.values():
                if not isinstance(record, dict):
                    continue
                if "processed_at" not in record or "processed_at_iso" not in record:
                    continue
                record.pop("processed_at_iso", None)
                summary["records_changed"] += 1
                summary["removed_redundant_processed_at_iso"] += 1

    return summary


def compact_processed_reports(state: dict[str, Any]) -> dict[str, Any]:
    # processed_reports 是單輪 checkpoint；同一筆若已完整保存在 checked_reports，
    # 移除 checkpoint 不會失去 report 狀態，卻能避免中斷或手動補抓後 state.json 永久膨脹。
    summary = {
        "encounters_changed": 0,
        "processed_before": 0,
        "processed_after": 0,
        "removed_duplicate_processed_reports": 0,
    }
    encounters = state.get("encounters")
    if not isinstance(encounters, dict):
        return summary

    for encounter_state in encounters.values():
        if not isinstance(encounter_state, dict):
            continue

        processed_reports = encounter_state.get("processed_reports")
        checked_reports = encounter_state.get("checked_reports")
        if not isinstance(processed_reports, dict):
            continue
        if not isinstance(checked_reports, dict):
            checked_reports = {}

        summary["processed_before"] += len(processed_reports)
        kept_reports: dict[str, Any] = {}
        removed = 0

        for report_code, processed_record in processed_reports.items():
            checked_record = checked_reports.get(report_code)
            if checked_record is not None and stable_json(checked_record) == stable_json(processed_record):
                removed += 1
                continue
            kept_reports[report_code] = processed_record

        if removed:
            encounter_state["processed_reports"] = kept_reports
            summary["encounters_changed"] += 1
            summary["removed_duplicate_processed_reports"] += removed

        summary["processed_after"] += len(encounter_state.get("processed_reports") or {})

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="壓縮 data/state.json 的重複 checkpoint 與 JSON 空白。")
    parser.add_argument("--dry-run", action="store_true", help="只列出預估異動，不寫入檔案。")
    parser.add_argument(
        "--max-bytes",
        type=int,
        default=0,
        help="任一 state 主檔或 checked_reports 分片超過此 byte 數就失敗；0 代表 GitHub 100 MiB 單檔限制。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = state_store.load_state(STATE_PATH)

    before_sizes = on_disk_state_storage_sizes(STATE_PATH)
    timestamp_summary = compact_report_checkpoint_timestamps(state)
    summary = compact_processed_reports(state)
    compacted_sizes = state_store.state_storage_sizes(STATE_PATH, state)

    if not args.dry_run:
        state_store.write_state(STATE_PATH, state)

    after_sizes = compacted_sizes if args.dry_run else on_disk_state_storage_sizes(STATE_PATH)
    mode = "dry-run" if args.dry_run else "written"
    before_total = sum(before_sizes.values())
    after_total = sum(after_sizes.values())
    largest_path, largest_size = max(after_sizes.items(), key=lambda item: item[1], default=(STATE_PATH, 0))

    print(
        f"State compact {mode}: "
        f"{summary['encounters_changed']} encounters changed, "
        f"{summary['removed_duplicate_processed_reports']} duplicate processed reports removed, "
        f"{timestamp_summary['removed_redundant_processed_at_iso']} redundant processed_at_iso fields removed."
    )
    print(
        f"processed_reports: {summary['processed_before']:,} -> {summary['processed_after']:,}; "
        f"state storage bytes: {before_total:,} -> {after_total:,} across {len(after_sizes)} files."
    )
    limit = args.max_bytes or GITHUB_SINGLE_BLOB_LIMIT_BYTES
    oversized = [(path, size) for path, size in after_sizes.items() if size > limit]
    if oversized:
        for path, size in oversized:
            print(
                f"ERROR: {path.relative_to(PROJECT_ROOT)} is {size:,} bytes after compaction; "
                f"limit is {limit:,} bytes.",
                file=sys.stderr,
            )
        return 1
    if largest_size > GITHUB_SINGLE_BLOB_LIMIT_BYTES:
        print(
            f"WARNING: {largest_path.relative_to(PROJECT_ROOT)} is above GitHub's 100 MiB single-file limit "
            f"({largest_size:,} > {GITHUB_SINGLE_BLOB_LIMIT_BYTES:,}).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
