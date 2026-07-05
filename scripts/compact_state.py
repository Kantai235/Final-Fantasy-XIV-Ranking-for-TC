from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "data" / "state.json"
GITHUB_SINGLE_BLOB_LIMIT_BYTES = 100 * 1024 * 1024


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def compact_json_bytes(content: Any) -> bytes:
    return (json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temp_path.write_bytes(compact_json_bytes(content))
    os.replace(temp_path, path)


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
        help="壓縮後若仍超過此 byte 數就失敗；0 代表使用 GitHub 100 MiB 單檔限制。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = read_json(STATE_PATH, {})
    if not isinstance(state, dict):
        raise RuntimeError("data/state.json 必須是 JSON 物件。")

    before_bytes = STATE_PATH.stat().st_size if STATE_PATH.exists() else 0
    timestamp_summary = compact_report_checkpoint_timestamps(state)
    summary = compact_processed_reports(state)
    compacted_bytes = len(compact_json_bytes(state))

    if not args.dry_run and STATE_PATH.exists() and compacted_bytes != before_bytes:
        write_json(STATE_PATH, state)

    after_bytes = STATE_PATH.stat().st_size if STATE_PATH.exists() else 0
    mode = "dry-run" if args.dry_run else "written"
    if args.dry_run:
        after_bytes = compacted_bytes

    print(
        f"State compact {mode}: "
        f"{summary['encounters_changed']} encounters changed, "
        f"{summary['removed_duplicate_processed_reports']} duplicate processed reports removed, "
        f"{timestamp_summary['removed_redundant_processed_at_iso']} redundant processed_at_iso fields removed."
    )
    print(
        f"processed_reports: {summary['processed_before']:,} -> {summary['processed_after']:,}; "
        f"bytes: {before_bytes:,} -> {after_bytes:,}."
    )
    limit = args.max_bytes or GITHUB_SINGLE_BLOB_LIMIT_BYTES
    if after_bytes > limit:
        print(
            f"ERROR: data/state.json is {after_bytes:,} bytes after compaction; "
            f"limit is {limit:,} bytes.",
            file=sys.stderr,
        )
        return 1
    if after_bytes > GITHUB_SINGLE_BLOB_LIMIT_BYTES:
        print(
            f"WARNING: data/state.json is above GitHub's 100 MiB single-file limit "
            f"({after_bytes:,} > {GITHUB_SINGLE_BLOB_LIMIT_BYTES:,}).",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
