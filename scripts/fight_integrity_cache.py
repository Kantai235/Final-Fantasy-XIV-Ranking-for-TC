"""戰鬥完整性檢核的本機測量快取。

快取只保存已彙整的敵方承傷、敵方最大生命池、目標數、逐目標 NPC GUID／生命值／
有效承傷／實例數，以及玩家層普攻技能 ID、命中數、中位數、占比與每秒傷害，或
可重現的無法量測原因。它不保存 raw events、玩家名稱、report 內 actor ID 或完整
FFLogs payload，讓門檻調整時仍能離線重新判定。這不是排行榜資料的一部分：
預設路徑由 .gitignore 排除，GitHub Actions 只透過 Actions cache 在執行輪次之間
接續使用。
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


CACHE_SCHEMA_VERSION = 6
SUPPORTED_CACHE_SCHEMA_VERSIONS = frozenset({3, 4, 5, CACHE_SCHEMA_VERSION})
CACHEABLE_UNVERIFIABLE_REASONS = frozenset({
    "missing_enemy_max_hp",
    "missing_enemy_target_guid",
})


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


def _to_nonnegative_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


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


def _normalize_target_measurements(raw: Any) -> list[dict[str, float | int]] | None:
    if not isinstance(raw, list) or not raw:
        return None
    targets: list[dict[str, float | int]] = []
    for raw_target in raw:
        if not isinstance(raw_target, dict):
            return None
        guid = _to_int(raw_target.get("guid"))
        damage = _to_number(raw_target.get("damage"))
        max_hp = _to_number(raw_target.get("max_hp"))
        instance_count = _to_int(raw_target.get("instance_count"))
        if (
            guid is None
            or guid <= 0
            or damage is None
            or max_hp is None
            or instance_count is None
            or instance_count <= 0
        ):
            return None
        targets.append({
            "guid": guid,
            "damage": damage,
            "max_hp": max_hp,
            "instance_count": instance_count,
        })
    targets.sort(key=lambda target: int(target["guid"]))
    return targets


def _normalize_measurement(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    enemy_damage = _to_number(raw.get("enemy_damage"))
    enemy_hp_capacity = _to_number(raw.get("enemy_hp_capacity"))
    target_count = _to_int(raw.get("target_count"))
    if enemy_damage is None or enemy_hp_capacity is None or target_count is None or target_count <= 0:
        return None
    measurement: dict[str, Any] = {
        "enemy_damage": enemy_damage,
        "enemy_hp_capacity": enemy_hp_capacity,
        "target_count": target_count,
    }
    if "targets" in raw:
        targets = _normalize_target_measurements(raw.get("targets"))
        if targets is None or len(targets) != target_count:
            return None
        measurement["targets"] = targets
    return measurement


def _normalize_basic_attack_measurement(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    actual_event_count = _to_int(raw.get("actual_event_count"))
    mapped_event_count = _to_int(raw.get("mapped_event_count"))
    raw_players = raw.get("players")
    if (
        actual_event_count is None
        or actual_event_count < 0
        or mapped_event_count is None
        or mapped_event_count < 0
        or not isinstance(raw_players, list)
    ):
        return None

    ability_ids: list[int] | None = None
    raw_ability_ids = raw.get("ability_ids")
    if raw_ability_ids is not None:
        if not isinstance(raw_ability_ids, list) or not raw_ability_ids:
            return None
        ability_ids = []
        for raw_ability_id in raw_ability_ids:
            ability_id = _to_int(raw_ability_id)
            if ability_id not in {7, 8} or ability_id in ability_ids:
                return None
            ability_ids.append(ability_id)

    players: list[dict[str, Any]] = []
    for raw_player in raw_players:
        if not isinstance(raw_player, dict):
            return None
        source_id = _to_int(raw_player.get("source_id"))
        attack_event_count = _to_int(raw_player.get("attack_event_count"))
        pure_normal_count = _to_int(raw_player.get("pure_normal_count"))
        # Attack 事件可能包含免疫／零傷害事件；零值仍是合法的完整彙總，不能因為
        # 本機快取驗證拒絕它，就把原本可判定的戰鬥降級成 unverifiable。
        attack_damage = _to_nonnegative_number(raw_player.get("attack_damage"))
        attack_share = _to_nonnegative_number(raw_player.get("attack_share"))
        raw_attack_dps = raw_player.get("attack_dps")
        attack_dps = (
            None
            if raw_attack_dps is None
            else _to_nonnegative_number(raw_attack_dps)
        )
        pure_normal_median = raw_player.get("pure_normal_median")
        normalized_median = (
            None if pure_normal_median is None else _to_number(pure_normal_median)
        )
        if (
            source_id is None
            or attack_event_count is None
            or attack_event_count < 0
            or pure_normal_count is None
            or pure_normal_count < 0
            or attack_damage is None
            or attack_share is None
            or (raw_attack_dps is not None and attack_dps is None)
            or (pure_normal_median is not None and normalized_median is None)
        ):
            return None
        player = {
            "source_id": source_id,
            "job": str(raw_player.get("job") or ""),
            "attack_event_count": attack_event_count,
            "pure_normal_count": pure_normal_count,
            "pure_normal_median": normalized_median,
            "attack_damage": attack_damage,
            "attack_share": attack_share,
        }
        if attack_dps is not None:
            player["attack_dps"] = attack_dps
        players.append(player)
    measurement = {
        "actual_event_count": actual_event_count,
        "mapped_event_count": mapped_event_count,
        "players": players,
    }
    if ability_ids is not None:
        measurement["ability_ids"] = ability_ids
    return measurement


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

        if (
            not isinstance(raw, dict)
            or raw.get("schema_version") not in SUPPORTED_CACHE_SCHEMA_VERSIONS
        ):
            return cls(path)
        entries = raw.get("entries")
        if not isinstance(entries, dict):
            return cls(path)
        return cls(path, {key: value for key, value in entries.items() if isinstance(value, dict)})

    def __len__(self) -> int:
        return len(self.entries)

    def get(
        self,
        report_code: str,
        report: dict[str, Any],
        fight: dict[str, Any],
        *,
        require_target_details: bool = False,
    ) -> dict[str, Any] | None:
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
            if (
                measurement is not None
                and require_target_details
                and "targets" not in measurement
            ):
                return None
            return {"outcome": outcome, "measurement": measurement} if measurement is not None else None
        if outcome == "unverifiable" and entry.get("reason") in CACHEABLE_UNVERIFIABLE_REASONS:
            return {"outcome": outcome, "reason": entry["reason"]}
        return None

    def get_basic_attack(
        self,
        report_code: str,
        report: dict[str, Any],
        fight: dict[str, Any],
    ) -> dict[str, Any] | None:
        key = _cache_key(report_code, fight)
        if key is None:
            return None
        entry = self.entries.get(key)
        if not isinstance(entry, dict):
            return None
        if entry.get("source_fingerprint") != _source_fingerprint(report, fight):
            return None
        return _normalize_basic_attack_measurement(entry.get("basic_attack_measurement"))

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

        existing = self.entries.get(key)
        preserved = (
            dict(existing)
            if isinstance(existing, dict)
            and existing.get("source_fingerprint") == _source_fingerprint(report, fight)
            else {}
        )
        self.entries[key] = {
            **preserved,
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
        existing = self.entries.get(key)
        preserved = (
            dict(existing)
            if isinstance(existing, dict)
            and existing.get("source_fingerprint") == _source_fingerprint(report, fight)
            else {}
        )
        self.entries[key] = {
            **preserved,
            "source_fingerprint": _source_fingerprint(report, fight),
            "cached_at_iso": cached_at_iso,
            "outcome": "unverifiable",
            "reason": reason,
        }
        if persist:
            self.save()

    def put_basic_attack(
        self,
        report_code: str,
        report: dict[str, Any],
        fight: dict[str, Any],
        *,
        measurement: dict[str, Any],
        cached_at_iso: str,
        persist: bool = True,
    ) -> None:
        """保存可重判的玩家層彙總，不保存事件、名稱或 FFLogs 完整回應。"""

        key = _cache_key(report_code, fight)
        normalized = _normalize_basic_attack_measurement(measurement)
        if key is None or normalized is None:
            raise ValueError("無法快取缺少 fight 識別或格式不正確的普攻分布測量資料")
        existing = self.entries.get(key)
        preserved = (
            dict(existing)
            if isinstance(existing, dict)
            and existing.get("source_fingerprint") == _source_fingerprint(report, fight)
            else {}
        )
        self.entries[key] = {
            **preserved,
            "source_fingerprint": _source_fingerprint(report, fight),
            "cached_at_iso": cached_at_iso,
            "basic_attack_measurement": normalized,
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
