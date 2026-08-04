"""戰鬥完整性檢核的本機測量快取。

快取只保存已彙整的敵方承傷、敵方最大生命池與目標數，或可重現的無法量測
原因，讓倍率規則或 Attack 標記規則調整時可離線重新判定，不必重複讀取
FFLogs。這不是排行榜資料的一部分：預設路徑由 .gitignore 排除，GitHub
Actions 只透過 Actions cache 在執行輪次之間接續使用。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


CACHE_SCHEMA_VERSION = 3
CACHEABLE_UNVERIFIABLE_REASONS = frozenset({"missing_enemy_max_hp"})


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _source_fingerprint(report: dict[str, Any], fight: dict[str, Any]) -> str:
    """建立會在 FFLogs 重算同一 report 時失效的來源指紋。"""

    source = {
        "report_end_time": report.get("end_time"),
        "report_end_time_iso": report.get("end_time_iso"),
        "report_start_time": report.get("start_time"),
        "report_start_time_iso": report.get("start_time_iso"),
        "report_revision": report.get("revision"),
        "fight_id": fight.get("fight_id"),
        "start_time": fight.get("start_time"),
        "end_time": fight.get("end_time"),
        "encounter_id": fight.get("encounter_id"),
        "difficulty": fight.get("difficulty"),
        "recorded_at": fight.get("recorded_at"),
    }
    encoded = json.dumps(source, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _cache_key(report_code: str, fight: dict[str, Any]) -> str | None:
    fight_id = _to_int(fight.get("fight_id"))
    if not report_code or fight_id is None:
        return None
    return f"{report_code}:{fight_id}"


def _normalize_measurement(raw: Any) -> dict[str, float | int] | None:
    if not isinstance(raw, dict):
        return None
    enemy_damage = _to_number(raw.get("enemy_damage"))
    enemy_hp_capacity = _to_number(raw.get("enemy_hp_capacity"))
    target_count = _to_int(raw.get("target_count"))
    if enemy_damage is None or enemy_hp_capacity is None or target_count is None or target_count <= 0:
        return None
    return {
        "enemy_damage": enemy_damage,
        "enemy_hp_capacity": enemy_hp_capacity,
        "target_count": target_count,
    }


class FightIntegrityMeasurementCache:
    """以原子寫入保存每一場已成功取得的最小測量資料。"""

    def __init__(self, path: Path, entries: dict[str, dict[str, Any]] | None = None) -> None:
        self.path = path
        self.entries = entries or {}

    @classmethod
    def load(cls, path: Path) -> "FightIntegrityMeasurementCache":
        if not path.exists():
            return cls(path)

        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # 快取損毀只會造成下一輪重新查詢，不能讓完整性檢核整輪中斷。
            return cls(path)

        if not isinstance(raw, dict) or raw.get("schema_version") != CACHE_SCHEMA_VERSION:
            return cls(path)
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            return cls(path)
        return cls(path, {key: value for key, value in entries.items() if isinstance(value, dict)})

    def __len__(self) -> int:
        return len(self.entries)

    def get(self, report_code: str, report: dict[str, Any], fight: dict[str, Any]) -> dict[str, Any] | None:
        key = _cache_key(report_code, fight)
        if key is None:
            return None
        entry = self.entries.get(key)
        if not isinstance(entry, dict):
            return None
        if entry.get("source_fingerprint") != _source_fingerprint(report, fight):
            return None
        outcome = entry.get("outcome")
        if outcome == "measured":
            measurement = _normalize_measurement(entry.get("measurement"))
            return {"outcome": outcome, "measurement": measurement} if measurement is not None else None
        if outcome == "unverifiable" and entry.get("reason") in CACHEABLE_UNVERIFIABLE_REASONS:
            return {"outcome": outcome, "reason": entry["reason"]}
        return None

    def put(
        self,
        report_code: str,
        report: dict[str, Any],
        fight: dict[str, Any],
        *,
        measurement: dict[str, Any],
        cached_at_iso: str,
        persist: bool = True,
    ) -> None:
        key = _cache_key(report_code, fight)
        normalized_measurement = _normalize_measurement(measurement)
        if key is None or normalized_measurement is None:
            raise ValueError("無法快取缺少 fight 識別或格式不正確的完整性測量資料")

        self.entries[key] = {
            "source_fingerprint": _source_fingerprint(report, fight),
            "cached_at_iso": cached_at_iso,
            "outcome": "measured",
            "measurement": normalized_measurement,
        }
        if persist:
            self.save()

    def put_unverifiable(
        self,
        report_code: str,
        report: dict[str, Any],
        fight: dict[str, Any],
        *,
        reason: str,
        cached_at_iso: str,
        persist: bool = True,
    ) -> None:
        """快取可重現的無法量測結果，避免每輪重讀同一份缺漏資料。"""

        key = _cache_key(report_code, fight)
        if key is None or reason not in CACHEABLE_UNVERIFIABLE_REASONS:
            raise ValueError("無法快取缺少 fight 識別或不可重現的完整性量測失敗")
        self.entries[key] = {
            "source_fingerprint": _source_fingerprint(report, fight),
            "cached_at_iso": cached_at_iso,
            "outcome": "unverifiable",
            "reason": reason,
        }
        if persist:
            self.save()

    def save(self) -> None:
        """每筆 API 測量完成後立即原子落地，避免程序中斷浪費已使用額度。"""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": CACHE_SCHEMA_VERSION,
            "entries": self.entries,
        }
        temporary_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temporary_path.write_text(
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n",
            encoding="utf-8",
        )
        os.replace(temporary_path, self.path)
