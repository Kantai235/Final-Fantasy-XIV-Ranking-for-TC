"""已知固定敵方生命池的完整隊伍傷害下限檢核。

這個暫時模組只處理已能由副本機制確定敵方總生命池的 encounter。它和歷史 P99
預篩不同：完整繁中隊伍的 ``players[].total_damage`` 可能漏掉 Limit Break，因此只
能當作敵方承傷的下限，絕不能單獨證明戰鬥正常；但當這個下限本身已超過固定生命池
的保守容許值時，該 fight 必然不能視為正常，足以先從公開資料隱藏而不耗用 API。

規則與設定檔刻意獨立，待 Log 工具修正後可整組移除，已寫入的
``fights[].data_integrity`` 則繼續保留作為歷史追溯證據。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
METRIC_NAME = "full_traditional_chinese_party_damage_lower_bound_vs_known_enemy_hp"


def _to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _to_positive_int(value: Any) -> int | None:
    number = _to_number(value)
    if number is None or number <= 0 or not number.is_integer():
        return None
    return int(number)


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


@dataclass(frozen=True)
class KnownEnemyCapacityRule:
    """單一副本已確認的敵方總生命池與保守疑似門檻。"""

    enemy_hp_capacity: int
    suspected_team_damage_ratio_threshold: float


@dataclass(frozen=True)
class KnownEnemyCapacityScreen:
    """完整隊伍傷害下限相對於已知敵方生命池的可追溯證據。"""

    encounter_key: str
    team_total_damage: int
    enemy_hp_capacity: int
    suspected_team_damage_ratio_threshold: float

    @property
    def damage_to_known_hp_ratio(self) -> float:
        return self.team_total_damage / self.enemy_hp_capacity

    @property
    def exceeds_suspected_threshold(self) -> bool:
        return self.damage_to_known_hp_ratio > self.suspected_team_damage_ratio_threshold

    def to_metrics(self) -> dict[str, Any]:
        return {
            "metric": METRIC_NAME,
            "encounter_key": self.encounter_key,
            "team_total_damage_lower_bound": self.team_total_damage,
            "enemy_hp_capacity": self.enemy_hp_capacity,
            "damage_to_known_hp_ratio": round(self.damage_to_known_hp_ratio, 6),
            "suspected_team_damage_ratio_threshold": self.suspected_team_damage_ratio_threshold,
            "exceeds_suspected_threshold": self.exceeds_suspected_threshold,
        }


@dataclass(frozen=True)
class KnownEnemyCapacityPolicy:
    """可獨立拔除的固定生命池規則集合。"""

    enabled: bool
    rules: dict[str, KnownEnemyCapacityRule]

    @classmethod
    def disabled(cls) -> "KnownEnemyCapacityPolicy":
        return cls(enabled=False, rules={})

    def screen(self, encounter_key: str, fight: dict[str, Any]) -> KnownEnemyCapacityScreen | None:
        """只在完整繁中隊伍的玩家傷害齊全時提供傷害下限證據。"""

        if not self.enabled:
            return None
        rule = self.rules.get(encounter_key)
        if rule is None:
            return None

        party_size = _to_positive_int(fight.get("size"))
        players = fight.get("players")
        if party_size is None or not isinstance(players, list) or len(players) != party_size:
            return None

        damages: list[float] = []
        for player in players:
            if not isinstance(player, dict):
                return None
            damage = _to_number(player.get("total_damage"))
            if damage is None or damage < 0:
                return None
            damages.append(damage)

        team_total_damage = round(sum(damages))
        if team_total_damage <= 0:
            return None
        return KnownEnemyCapacityScreen(
            encounter_key=encounter_key,
            team_total_damage=team_total_damage,
            enemy_hp_capacity=rule.enemy_hp_capacity,
            suspected_team_damage_ratio_threshold=rule.suspected_team_damage_ratio_threshold,
        )


def load_known_enemy_capacity_policy(path: Path) -> KnownEnemyCapacityPolicy:
    """讀取固定生命池規則；不存在代表已安全停用這個暫時防護。"""

    if not path.exists():
        return KnownEnemyCapacityPolicy.disabled()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"無法讀取固定敵方生命池規則設定：{path}") from error
    if not isinstance(raw, dict):
        raise RuntimeError("固定敵方生命池規則設定必須是 JSON 物件。")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"固定敵方生命池規則 schema_version 必須是 {SCHEMA_VERSION}。")
    if not _to_bool(raw.get("enabled"), True):
        return KnownEnemyCapacityPolicy.disabled()
    if raw.get("metric") != METRIC_NAME:
        raise RuntimeError(f"固定敵方生命池規則 metric 必須是 {METRIC_NAME}。")

    raw_rules = raw.get("encounters")
    if not isinstance(raw_rules, dict):
        raise RuntimeError("固定敵方生命池規則 encounters 必須是物件。")
    rules: dict[str, KnownEnemyCapacityRule] = {}
    for encounter_key, entry in raw_rules.items():
        if not isinstance(encounter_key, str) or not encounter_key or not isinstance(entry, dict):
            raise RuntimeError("固定敵方生命池規則 encounters 含有無效項目。")
        capacity = _to_positive_int(entry.get("enemy_hp_capacity"))
        suspected_threshold = _to_number(entry.get("suspected_team_damage_ratio_threshold"))
        if capacity is None or suspected_threshold is None or suspected_threshold <= 1:
            raise RuntimeError(f"固定敵方生命池規則 {encounter_key} 缺少有效生命池或疑似門檻。")
        rules[encounter_key] = KnownEnemyCapacityRule(
            enemy_hp_capacity=capacity,
            suspected_team_damage_ratio_threshold=suspected_threshold,
        )

    return KnownEnemyCapacityPolicy(enabled=True, rules=rules)
