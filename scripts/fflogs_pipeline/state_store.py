from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable


# checked_reports 會隨掃描年資成長，但每個副本的快取彼此沒有讀寫相依。
# 因此把它依 encounter key 分開保存，既能完整保留跨輪略過依據，又不會讓單一
# data/state.json 撞上 GitHub 100 MiB blob 限制。主檔仍保存掃描游標與其他狀態，
# 讀取端則在記憶體中還原為既有的 state.encounters.*.checked_reports 結構。
CHECKED_REPORTS_STORAGE_FIELD = "checked_reports_storage"
CHECKED_REPORTS_STORAGE_FORMAT = "encounter_shards_v1"
CHECKED_REPORTS_DIRECTORY = "state/checked_reports"
_SAFE_ENCOUNTER_KEY = re.compile(r"^[A-Za-z0-9_-]+$")

JsonWriter = Callable[[Path, Any], None]


def compact_json_bytes(content: Any) -> bytes:
    return (json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"無法解析 JSON 檔案：{path}") from error


def checked_reports_directory(state_path: Path) -> Path:
    return state_path.parent / CHECKED_REPORTS_DIRECTORY


def checked_reports_shard_path(state_path: Path, encounter_key: str) -> Path:
    if not _SAFE_ENCOUNTER_KEY.fullmatch(encounter_key):
        raise RuntimeError(f"副本 key 不可用於 checked_reports 分片路徑：{encounter_key!r}")
    return checked_reports_directory(state_path) / f"{encounter_key}.json"


def is_checked_reports_shard_path(state_path: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(checked_reports_directory(state_path).resolve())
    except ValueError:
        return False
    return path.suffix == ".json"


def _record_time(record: Any) -> float:
    if not isinstance(record, dict):
        return float("-inf")
    value = record.get("processed_at", record.get("updated_at", float("-inf")))
    if isinstance(value, bool):
        return float("-inf")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("-inf")


def _merge_record(inline_record: Any, shard_record: Any) -> Any:
    # 中斷可能發生在「先寫分片、後寫主檔」之間。遇到相同 report code 時，以較新的
    # processed_at 為主，並保留另一側缺少的輔助欄位，避免舊版 inline state 覆蓋新分片。
    if not isinstance(inline_record, dict):
        return shard_record
    if not isinstance(shard_record, dict):
        return inline_record

    preferred, secondary = (
        (shard_record, inline_record)
        if _record_time(shard_record) >= _record_time(inline_record)
        else (inline_record, shard_record)
    )
    return {**secondary, **preferred}


def merge_checked_reports(inline_reports: Any, shard_reports: Any) -> dict[str, Any]:
    inline_map = inline_reports if isinstance(inline_reports, dict) else {}
    shard_map = shard_reports if isinstance(shard_reports, dict) else {}
    merged: dict[str, Any] = {}
    for report_code in sorted({*inline_map.keys(), *shard_map.keys()}, key=str):
        inline_record = inline_map.get(report_code)
        shard_record = shard_map.get(report_code)
        if report_code not in inline_map:
            merged[str(report_code)] = shard_record
        elif report_code not in shard_map:
            merged[str(report_code)] = inline_record
        else:
            merged[str(report_code)] = _merge_record(inline_record, shard_record)
    return merged


def load_state(state_path: Path) -> dict[str, Any]:
    state = read_json(state_path, {})
    if not isinstance(state, dict):
        raise RuntimeError(f"狀態檔必須是 JSON 物件：{state_path}")

    encounters = state.get("encounters")
    if not isinstance(encounters, dict):
        return state

    for encounter_key, encounter_state in encounters.items():
        if not isinstance(encounter_key, str) or not isinstance(encounter_state, dict):
            continue
        shard_path = checked_reports_shard_path(state_path, encounter_key)
        if not shard_path.exists():
            continue
        shard_reports = read_json(shard_path, {})
        if not isinstance(shard_reports, dict):
            raise RuntimeError(f"checked_reports 分片必須是 JSON 物件：{shard_path}")
        encounter_state["checked_reports"] = merge_checked_reports(
            encounter_state.get("checked_reports"),
            shard_reports,
        )
    return state


def build_state_storage(state_path: Path, state: dict[str, Any]) -> dict[Path, Any]:
    """將記憶體 state 拆成主檔與 checked_reports 分片，不修改呼叫端持有的 state。"""
    main_state = dict(state)
    encounters = state.get("encounters")
    shard_payloads: dict[Path, Any] = {}

    if isinstance(encounters, dict):
        main_encounters: dict[str, Any] = {}
        for encounter_key, encounter_state in encounters.items():
            if not isinstance(encounter_key, str) or not isinstance(encounter_state, dict):
                main_encounters[str(encounter_key)] = encounter_state
                continue
            main_encounter_state = dict(encounter_state)
            checked_reports = main_encounter_state.pop("checked_reports", None)
            if isinstance(checked_reports, dict):
                shard_payloads[checked_reports_shard_path(state_path, encounter_key)] = checked_reports
            main_encounters[encounter_key] = main_encounter_state
        main_state["encounters"] = main_encounters
        main_state[CHECKED_REPORTS_STORAGE_FIELD] = {
            "format": CHECKED_REPORTS_STORAGE_FORMAT,
            "path": CHECKED_REPORTS_DIRECTORY,
        }

    # 先寫分片，最後才改寫主檔；任何中斷都可由 load_state 合併舊 inline 快取與新分片，
    # 不會因遷移過程而遺失已檢查 report。
    return {**dict(sorted(shard_payloads.items(), key=lambda item: str(item[0]))), state_path: main_state}


def _write_compact_json(path: Path, content: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    temporary_path.write_bytes(compact_json_bytes(content))
    os.replace(temporary_path, path)


def write_state(state_path: Path, state: dict[str, Any], *, write_json: JsonWriter | None = None) -> dict[Path, int]:
    if not isinstance(state, dict):
        raise RuntimeError("狀態資料必須是 JSON 物件。")
    writer = write_json or _write_compact_json
    payloads = build_state_storage(state_path, state)
    sizes: dict[Path, int] = {}
    for path, content in payloads.items():
        writer(path, content)
        sizes[path] = len(compact_json_bytes(content))
    return sizes


def state_storage_sizes(state_path: Path, state: dict[str, Any]) -> dict[Path, int]:
    return {
        path: len(compact_json_bytes(content))
        for path, content in build_state_storage(state_path, state).items()
    }
