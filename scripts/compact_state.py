from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
STATE_PATH = PROJECT_ROOT / "data" / "state.json"


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    with temp_path.open("w", encoding="utf-8", newline="\n") as file:
        json.dump(content, file, ensure_ascii=False, indent=2, sort_keys=True)
        file.write("\n")
    os.replace(temp_path, path)


def stable_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


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
    parser = argparse.ArgumentParser(description="壓縮 data/state.json 中可由 checked_reports 保留的重複 checkpoint。")
    parser.add_argument("--dry-run", action="store_true", help="只列出預估異動，不寫入檔案。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = read_json(STATE_PATH, {})
    if not isinstance(state, dict):
        raise RuntimeError("data/state.json 必須是 JSON 物件。")

    before_bytes = STATE_PATH.stat().st_size if STATE_PATH.exists() else 0
    summary = compact_processed_reports(state)

    if not args.dry_run and summary["removed_duplicate_processed_reports"] > 0:
        write_json(STATE_PATH, state)

    after_bytes = STATE_PATH.stat().st_size if STATE_PATH.exists() else 0
    mode = "dry-run" if args.dry_run else "written"
    if args.dry_run:
        after_bytes = before_bytes

    print(
        f"State compact {mode}: "
        f"{summary['encounters_changed']} encounters changed, "
        f"{summary['removed_duplicate_processed_reports']} duplicate processed reports removed."
    )
    print(
        f"processed_reports: {summary['processed_before']:,} -> {summary['processed_after']:,}; "
        f"bytes: {before_bytes:,} -> {after_bytes:,}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
