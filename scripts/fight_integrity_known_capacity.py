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
    """單一副本已確認的敵方總生命池與保守疑似門檻。

    ``maximum_full_party_damage`` 是和敵方生命池分離的歷史傷害上限。它只在
    完整繁中隊伍的玩家傷害合計超過明確上限時提供異常證據，不能把未超過上限
    的戰鬥視為正常；這避免 Limit Break 未歸屬玩家列時產生 false valid，也能
    安全用於多階段生命池副本。
    """

    enemy_hp_capacity: int | None = None
    suspected_team_damage_ratio_threshold: float | None = None
    required_full_party_damage_min: int | None = None
    required_full_party_damage_max: int | None = None
    required_enemy_damage_min: int | None = None
    required_enemy_damage_max: int | None = None
    maximum_full_party_damage: int | None = None


@dataclass(frozen=True)
class KnownEnemyCapacityScreen:
    """完整隊伍傷害下限相對於已知敵方生命池的可追溯證據。"""

    encounter_key: str
    team_total_damage: int
    enemy_hp_capacity: int | None = None
    suspected_team_damage_ratio_threshold: float | None = None
    required_full_party_damage_min: int | None = None
    required_full_party_damage_max: int | None = None
    required_enemy_damage_min: int | None = None
    required_enemy_damage_max: int | None = None
    maximum_full_party_damage: int | None = None
    damage_source: str = "full_party_player_damage"

    @property
    def has_known_enemy_hp_capacity(self) -> bool:
        return self.enemy_hp_capacity is not None

    @property
    def damage_to_known_hp_ratio(self) -> float | None:
        if self.enemy_hp_capacity is None:
            return None
        return self.team_total_damage / self.enemy_hp_capacity

    @property
    def exceeds_suspected_threshold(self) -> bool:
        ratio = self.damage_to_known_hp_ratio
        return (
            ratio is not None
            and self.suspected_team_damage_ratio_threshold is not None
            and ratio > self.suspected_team_damage_ratio_threshold
        )

    @property
    def has_maximum_full_party_damage(self) -> bool:
        return self.maximum_full_party_damage is not None

    @property
    def exceeds_maximum_full_party_damage(self) -> bool:
        return (
            self.maximum_full_party_damage is not None
            and self.team_total_damage > self.maximum_full_party_damage
        )

    @property
    def has_required_full_party_damage_range(self) -> bool:
        """是否有可由完整隊伍總傷害直接判定正常與否的副本專用規則。"""

        return (
            self.required_full_party_damage_min is not None
            and self.required_full_party_damage_max is not None
        )

    @property
    def matches_required_full_party_damage_range(self) -> bool:
        """完整隊伍總傷害是否落在副本確認過的正常範圍內。"""

        if not self.has_required_full_party_damage_range:
            return False
        return (
            self.required_full_party_damage_min <= self.team_total_damage
            <= self.required_full_party_damage_max
        )

    @property
    def has_required_enemy_damage_range(self) -> bool:
        """確認已設定可直接比對 FFLogs 敵方承傷的固定總傷害範圍。"""

        return (
            self.required_enemy_damage_min is not None
            and self.required_enemy_damage_max is not None
        )

    @property
    def matches_required_enemy_damage_range(self) -> bool:
        if not self.has_required_enemy_damage_range:
            return False
        return (
            self.required_enemy_damage_min <= self.team_total_damage
            <= self.required_enemy_damage_max
        )

    def to_metrics(self) -> dict[str, Any]:
        metrics: dict[str, Any] = {
            "metric": METRIC_NAME,
            "encounter_key": self.encounter_key,
            "damage_source": self.damage_source,
        }
        if self.damage_source == "enemy_damage":
            metrics["enemy_damage"] = self.team_total_damage
        else:
            metrics.update({
                "full_party_total_damage": self.team_total_damage,
                "team_total_damage_lower_bound": self.team_total_damage,
            })
        if self.has_known_enemy_hp_capacity:
            metrics.update({
                "enemy_hp_capacity": self.enemy_hp_capacity,
                "damage_to_known_hp_ratio": round(self.damage_to_known_hp_ratio or 0, 6),
                "suspected_team_damage_ratio_threshold": self.suspected_team_damage_ratio_threshold,
                "exceeds_suspected_threshold": self.exceeds_suspected_threshold,
            })
        if self.has_required_full_party_damage_range:
            metrics.update({
                "required_full_party_damage_min": self.required_full_party_damage_min,
                "required_full_party_damage_max": self.required_full_party_damage_max,
                "matches_required_full_party_damage_range": self.matches_required_full_party_damage_range,
            })
        if self.has_required_enemy_damage_range:
            metrics.update({
                "required_enemy_damage_min": self.required_enemy_damage_min,
                "required_enemy_damage_max": self.required_enemy_damage_max,
                "matches_required_enemy_damage_range": self.matches_required_enemy_damage_range,
            })
        if self.has_maximum_full_party_damage:
            metrics.update({
                "maximum_full_party_damage": self.maximum_full_party_damage,
                "exceeds_maximum_full_party_damage": self.exceeds_maximum_full_party_damage,
            })
        return metrics


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
            required_full_party_damage_min=rule.required_full_party_damage_min,
            required_full_party_damage_max=rule.required_full_party_damage_max,
            required_enemy_damage_min=rule.required_enemy_damage_min,
            required_enemy_damage_max=rule.required_enemy_damage_max,
            maximum_full_party_damage=rule.maximum_full_party_damage,
        )

    def screen_enemy_damage(
        self,
        encounter_key: str,
        enemy_damage: float | int,
    ) -> KnownEnemyCapacityScreen | None:
        """以已量測的敵方承傷套用固定總傷害規則。

        部分 report 的繁中服玩家列可能不完整，不能以 ``players[].total_damage``
        判定固定總傷害；此時只有已保存或剛查得的 FFLogs 敵方承傷可作為完整隊伍
        總量。此入口刻意只啟用設定了敵方承傷範圍的副本，避免把多目標副本的
        敵方承傷誤當成角色傷害總和。
        """

        if not self.enabled:
            return None
        rule = self.rules.get(encounter_key)
        if (
            rule is None
            or rule.required_enemy_damage_min is None
            or rule.required_enemy_damage_max is None
        ):
            return None
        measured_damage = _to_number(enemy_damage)
        if measured_damage is None or measured_damage <= 0:
            return None
        return KnownEnemyCapacityScreen(
            encounter_key=encounter_key,
            team_total_damage=round(measured_damage),
            enemy_hp_capacity=rule.enemy_hp_capacity,
            suspected_team_damage_ratio_threshold=rule.suspected_team_damage_ratio_threshold,
            required_enemy_damage_min=rule.required_enemy_damage_min,
            required_enemy_damage_max=rule.required_enemy_damage_max,
            damage_source="enemy_damage",
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
        has_capacity = "enemy_hp_capacity" in entry
        has_suspected_threshold = "suspected_team_damage_ratio_threshold" in entry
        if has_capacity != has_suspected_threshold:
            raise RuntimeError(
                f"固定敵方生命池規則 {encounter_key} 的生命池與疑似門檻必須成對設定。"
            )
        if has_capacity and (
            capacity is None or suspected_threshold is None or suspected_threshold <= 1
        ):
            raise RuntimeError(f"固定敵方生命池規則 {encounter_key} 缺少有效生命池或疑似門檻。")
        required_min = _to_positive_int(entry.get("required_full_party_damage_min"))
        required_max = _to_positive_int(entry.get("required_full_party_damage_max"))
        has_required_min = "required_full_party_damage_min" in entry
        has_required_max = "required_full_party_damage_max" in entry
        if has_required_min != has_required_max:
            raise RuntimeError(
                f"固定敵方生命池規則 {encounter_key} 的完整隊伍總傷害範圍必須同時設定上下限。"
            )
        if has_required_min and (
            required_min is None
            or required_max is None
            or required_min > required_max
        ):
            raise RuntimeError(
                f"固定敵方生命池規則 {encounter_key} 的完整隊伍總傷害範圍無效。"
            )
        required_enemy_min = _to_positive_int(entry.get("required_enemy_damage_min"))
        required_enemy_max = _to_positive_int(entry.get("required_enemy_damage_max"))
        has_required_enemy_min = "required_enemy_damage_min" in entry
        has_required_enemy_max = "required_enemy_damage_max" in entry
        if has_required_enemy_min != has_required_enemy_max:
            raise RuntimeError(
                f"固定敵方承傷範圍必須同時提供最小值與最大值：{encounter_key}"
            )
        if has_required_enemy_min and (
            required_enemy_min is None
            or required_enemy_max is None
            or required_enemy_min > required_enemy_max
        ):
            raise RuntimeError(
                f"固定敵方承傷範圍必須是正整數且最小值不得超過最大值：{encounter_key}"
            )
        maximum_full_party_damage = _to_positive_int(entry.get("maximum_full_party_damage"))
        if "maximum_full_party_damage" in entry and maximum_full_party_damage is None:
            raise RuntimeError(
                f"固定敵方生命池規則 {encounter_key} 的完整隊伍總傷害上限無效。"
            )
        if (
            not has_capacity
            and not has_required_min
            and not has_required_enemy_min
            and maximum_full_party_damage is None
        ):
            raise RuntimeError(
                f"固定敵方生命池規則 {encounter_key} 至少要設定生命池、固定傷害範圍或傷害上限。"
            )
        rules[encounter_key] = KnownEnemyCapacityRule(
            enemy_hp_capacity=capacity,
            suspected_team_damage_ratio_threshold=suspected_threshold,
            required_full_party_damage_min=required_min,
            required_full_party_damage_max=required_max,
            required_enemy_damage_min=required_enemy_min,
            required_enemy_damage_max=required_enemy_max,
            maximum_full_party_damage=maximum_full_party_damage,
        )

    return KnownEnemyCapacityPolicy(enabled=True, rules=rules)
