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
    maximum_enemy_damage: int | None = None
    target_damage_profile: "KnownTargetDamageProfile | None" = None


@dataclass(frozen=True)
class KnownTargetDamageRule:
    """單一敵方 NPC 在標準通關中的固定生命值與有效承傷語意。

    ``expected_damage_instances`` 不等同 FFLogs ``enemyNPCs.instanceCount``。M6S、
    M7S 的 fight metadata 會列出未實際擊殺或只在場景中生成的同 GUID actor；若直接
    乘上 instanceCount，會把未承傷的生命池誤算進上限。此欄位只描述經多份正常
    report 交叉確認、實際需要打掉的等效實例數，再由 ``expected_damage_ratio`` 表達
    M8S 狼打至剩餘 60% 血量便轉場（因此有效承傷為 40%）之類的固定比例。
    """

    guid: int
    name: str
    max_hp: int
    expected_damage_instances: int
    expected_damage_ratio: float
    damage_tolerance: int

    @property
    def expected_damage(self) -> int:
        return round(
            self.max_hp
            * self.expected_damage_instances
            * self.expected_damage_ratio
        )


@dataclass(frozen=True)
class KnownTargetDamageProfile:
    """副本專用逐目標生命值／轉場比例規則。"""

    version: str
    targets: dict[int, KnownTargetDamageRule]


@dataclass(frozen=True)
class KnownTargetDamageProfileScreen:
    """逐目標量測相對於副本固定 profile 的可追溯判定。"""

    encounter_key: str
    profile_version: str
    status: str
    reason: str | None
    metrics: dict[str, Any]

    @property
    def is_abnormal(self) -> bool:
        return self.status in {"excluded", "suspected", "unverifiable"}

    def to_metrics(self) -> dict[str, Any]:
        return {
            "profile_version": self.profile_version,
            "status": self.status,
            **self.metrics,
        }


@dataclass(frozen=True)
class KnownEnemyCapacityScreen:
    """完整隊伍傷害或已量測敵方承傷相對於已知規則的可追溯證據。"""

    encounter_key: str
    team_total_damage: int
    enemy_hp_capacity: int | None = None
    suspected_team_damage_ratio_threshold: float | None = None
    required_full_party_damage_min: int | None = None
    required_full_party_damage_max: int | None = None
    required_enemy_damage_min: int | None = None
    required_enemy_damage_max: int | None = None
    maximum_full_party_damage: int | None = None
    maximum_enemy_damage: int | None = None
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
    def is_below_required_full_party_damage_range(self) -> bool:
        """玩家傷害下限是否低於固定範圍，因而需要更完整的傷害來源佐證。"""

        return (
            self.has_required_full_party_damage_range
            and self.team_total_damage < self.required_full_party_damage_min
        )

    @property
    def is_above_required_full_party_damage_range(self) -> bool:
        """玩家傷害下限是否已高於固定範圍，可直接視為異常證據。"""

        return (
            self.has_required_full_party_damage_range
            and self.team_total_damage > self.required_full_party_damage_max
        )

    @property
    def needs_enemy_damage_for_low_full_party_total(self) -> bool:
        """是否不能只靠偏低的玩家傷害下限判定異常。

        ``players[].total_damage`` 不包含 Limit Break 等未歸屬角色的來源。只有當
        玩家合計已高於上限時，這個下限才足以直接證明異常；低於下限時若另有
        FFLogs Target Damage 固定範圍，必須改用完整敵方承傷確認。
        """

        return (
            self.damage_source == "full_party_player_damage"
            and self.is_below_required_full_party_damage_range
            and self.has_required_enemy_damage_range
        )

    @property
    def has_maximum_enemy_damage(self) -> bool:
        """是否有只能由 FFLogs Target Damage 驗證的敵方承傷上限。"""

        return self.maximum_enemy_damage is not None

    @property
    def exceeds_maximum_enemy_damage(self) -> bool:
        return (
            self.maximum_enemy_damage is not None
            and self.team_total_damage > self.maximum_enemy_damage
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
                "is_below_required_full_party_damage_range": self.is_below_required_full_party_damage_range,
                "is_above_required_full_party_damage_range": self.is_above_required_full_party_damage_range,
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
        if self.has_maximum_enemy_damage:
            metrics.update({
                "maximum_enemy_damage": self.maximum_enemy_damage,
                "exceeds_maximum_enemy_damage": self.exceeds_maximum_enemy_damage,
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

    def target_damage_profile(
        self,
        encounter_key: str,
    ) -> KnownTargetDamageProfile | None:
        if not self.enabled:
            return None
        rule = self.rules.get(encounter_key)
        return rule.target_damage_profile if rule is not None else None

    def requires_target_damage_profile_measurement(self, encounter_key: str) -> bool:
        """是否必須保存逐目標最小量測，不能只沿用舊版彙總生命池快取。"""

        return self.target_damage_profile(encounter_key) is not None

    def screen_target_damage_profile(
        self,
        encounter_key: str,
        measurement: dict[str, Any],
    ) -> KnownTargetDamageProfileScreen | None:
        """比對逐目標生命值、有效承傷與固定轉場比例。

        這裡只接受 FFLogs Target Damage 與少量 resource events 壓縮後的最小量測；
        actor id 是 report 區域值，不能跨上傳比對，因此規則與結果都以 NPC GUID
        作為穩定主鍵。若舊快取只有敵方總傷害，必須回報 unverifiable，讓呼叫端
        重新查詢，而不是用缺少逐目標證據的彙總值誤判為有效。
        """

        profile = self.target_damage_profile(encounter_key)
        if profile is None:
            return None

        raw_targets = measurement.get("targets") if isinstance(measurement, dict) else None
        if not isinstance(raw_targets, list) or not raw_targets:
            return KnownTargetDamageProfileScreen(
                encounter_key=encounter_key,
                profile_version=profile.version,
                status="unverifiable",
                reason="missing_target_damage_profile_measurement",
                metrics={
                    "expected_target_guids": sorted(profile.targets),
                    "target_results": [],
                },
            )

        observed_by_guid: dict[int, dict[str, int]] = {}
        invalid_measurement = False
        for raw_target in raw_targets:
            if not isinstance(raw_target, dict):
                invalid_measurement = True
                continue
            guid = _to_positive_int(raw_target.get("guid"))
            damage_value = _to_number(raw_target.get("damage"))
            max_hp = _to_positive_int(raw_target.get("max_hp"))
            instance_count = _to_positive_int(raw_target.get("instance_count"))
            if guid is None or damage_value is None or damage_value <= 0 or max_hp is None:
                invalid_measurement = True
                continue
            damage = round(damage_value)
            existing = observed_by_guid.get(guid)
            if existing is None:
                observed_by_guid[guid] = {
                    "damage": damage,
                    "max_hp": max_hp,
                    "instance_count": instance_count or 1,
                }
                continue
            # 同一 GUID 若在 Target table 被拆成多個 actor id，可安全合併承傷與
            # instanceCount；但 max HP 不一致代表 resource 語意不完整，不能猜測。
            if existing["max_hp"] != max_hp:
                invalid_measurement = True
                continue
            existing["damage"] += damage
            existing["instance_count"] += instance_count or 1

        if invalid_measurement:
            return KnownTargetDamageProfileScreen(
                encounter_key=encounter_key,
                profile_version=profile.version,
                status="unverifiable",
                reason="invalid_target_damage_profile_measurement",
                metrics={
                    "expected_target_guids": sorted(profile.targets),
                    "observed_target_guids": sorted(observed_by_guid),
                    "target_results": [],
                },
            )

        missing_guids = sorted(set(profile.targets) - set(observed_by_guid))
        unexpected_guids = sorted(set(observed_by_guid) - set(profile.targets))
        target_results: list[dict[str, Any]] = []
        mismatched_guids: list[int] = []
        for guid, target_rule in sorted(profile.targets.items()):
            observed = observed_by_guid.get(guid)
            expected_damage = target_rule.expected_damage
            damage_min = expected_damage - target_rule.damage_tolerance
            damage_max = expected_damage + target_rule.damage_tolerance
            if observed is None:
                target_results.append({
                    "guid": guid,
                    "name": target_rule.name,
                    "expected_max_hp": target_rule.max_hp,
                    "expected_damage_instances": target_rule.expected_damage_instances,
                    "expected_damage_ratio": target_rule.expected_damage_ratio,
                    "expected_damage": expected_damage,
                    "damage_min": damage_min,
                    "damage_max": damage_max,
                    "matches": False,
                })
                mismatched_guids.append(guid)
                continue

            max_hp_matches = observed["max_hp"] == target_rule.max_hp
            damage_matches = damage_min <= observed["damage"] <= damage_max
            matches = max_hp_matches and damage_matches
            if not matches:
                mismatched_guids.append(guid)
            target_results.append({
                "guid": guid,
                "name": target_rule.name,
                "observed_damage": observed["damage"],
                "observed_max_hp": observed["max_hp"],
                "observed_instance_count": observed["instance_count"],
                "observed_damage_ratio": round(
                    observed["damage"]
                    / (target_rule.max_hp * target_rule.expected_damage_instances),
                    6,
                ),
                "expected_max_hp": target_rule.max_hp,
                "expected_damage_instances": target_rule.expected_damage_instances,
                "expected_damage_ratio": target_rule.expected_damage_ratio,
                "expected_damage": expected_damage,
                "damage_min": damage_min,
                "damage_max": damage_max,
                "max_hp_matches": max_hp_matches,
                "damage_matches": damage_matches,
                "matches": matches,
            })

        expected_enemy_damage = sum(
            target_rule.expected_damage for target_rule in profile.targets.values()
        )
        observed_enemy_damage = sum(target["damage"] for target in observed_by_guid.values())
        has_mismatch = bool(missing_guids or unexpected_guids or mismatched_guids)
        return KnownTargetDamageProfileScreen(
            encounter_key=encounter_key,
            profile_version=profile.version,
            status="suspected" if has_mismatch else "valid",
            reason="target_damage_profile_mismatch" if has_mismatch else None,
            metrics={
                "expected_enemy_damage": expected_enemy_damage,
                "observed_enemy_damage": observed_enemy_damage,
                "missing_target_guids": missing_guids,
                "unexpected_target_guids": unexpected_guids,
                "mismatched_target_guids": sorted(set(mismatched_guids)),
                "target_results": target_results,
            },
        )

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

    def requires_enemy_damage_measurement(self, encounter_key: str) -> bool:
        """是否必須量測 FFLogs Target Damage 才能套用副本專用規則。"""

        if not self.enabled:
            return False
        rule = self.rules.get(encounter_key)
        return bool(
            rule is not None
            and (
                (
                    rule.required_enemy_damage_min is not None
                    and rule.required_enemy_damage_max is not None
                )
                or rule.maximum_enemy_damage is not None
                or rule.target_damage_profile is not None
            )
        )

    def screen_enemy_damage(
        self,
        encounter_key: str,
        enemy_damage: float | int,
    ) -> KnownEnemyCapacityScreen | None:
        """以已量測的敵方承傷套用固定總傷害規則。

        部分 report 的繁中服玩家列可能不完整，不能以 ``players[].total_damage``
        判定固定總傷害；此時只有已保存或剛查得的 FFLogs 敵方承傷可作為完整隊伍
        總量。此入口刻意只啟用設定了敵方承傷範圍或敵方承傷上限的副本，避免把
        多目標副本的敵方承傷誤當成角色傷害總和。
        """

        if not self.enabled:
            return None
        rule = self.rules.get(encounter_key)
        if rule is None or not self.requires_enemy_damage_measurement(encounter_key):
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
            maximum_enemy_damage=rule.maximum_enemy_damage,
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
        maximum_enemy_damage = _to_positive_int(entry.get("maximum_enemy_damage"))
        if "maximum_enemy_damage" in entry and maximum_enemy_damage is None:
            raise RuntimeError(
                f"固定敵方生命池規則 {encounter_key} 的敵方承傷上限無效。"
            )
        target_damage_profile: KnownTargetDamageProfile | None = None
        raw_target_profile = entry.get("target_damage_profile")
        if raw_target_profile is not None:
            if not isinstance(raw_target_profile, dict):
                raise RuntimeError(f"逐目標生命值規則必須是物件：{encounter_key}")
            profile_version = raw_target_profile.get("version")
            raw_target_rules = raw_target_profile.get("targets")
            default_tolerance = _to_positive_int(
                raw_target_profile.get("damage_tolerance")
            )
            if (
                not isinstance(profile_version, str)
                or not profile_version.strip()
                or not isinstance(raw_target_rules, list)
                or not raw_target_rules
                or default_tolerance is None
            ):
                raise RuntimeError(
                    f"逐目標生命值規則缺少版本、容許值或目標清單：{encounter_key}"
                )

            parsed_targets: dict[int, KnownTargetDamageRule] = {}
            for raw_target_rule in raw_target_rules:
                if not isinstance(raw_target_rule, dict):
                    raise RuntimeError(f"逐目標生命值規則含有無效目標：{encounter_key}")
                guid = _to_positive_int(raw_target_rule.get("guid"))
                name = raw_target_rule.get("name")
                max_hp = _to_positive_int(raw_target_rule.get("max_hp"))
                expected_instances = _to_positive_int(
                    raw_target_rule.get("expected_damage_instances")
                )
                expected_ratio = _to_number(
                    raw_target_rule.get("expected_damage_ratio")
                )
                tolerance = _to_positive_int(
                    raw_target_rule.get("damage_tolerance")
                ) or default_tolerance
                if (
                    guid is None
                    or guid in parsed_targets
                    or not isinstance(name, str)
                    or not name.strip()
                    or max_hp is None
                    or expected_instances is None
                    or expected_ratio is None
                    or expected_ratio <= 0
                    or expected_ratio > 1
                    or tolerance is None
                ):
                    raise RuntimeError(
                        f"逐目標生命值規則欄位無效或 GUID 重複：{encounter_key}"
                    )
                parsed_targets[guid] = KnownTargetDamageRule(
                    guid=guid,
                    name=name.strip(),
                    max_hp=max_hp,
                    expected_damage_instances=expected_instances,
                    expected_damage_ratio=expected_ratio,
                    damage_tolerance=tolerance,
                )
            target_damage_profile = KnownTargetDamageProfile(
                version=profile_version.strip(),
                targets=parsed_targets,
            )
        if (
            not has_capacity
            and not has_required_min
            and not has_required_enemy_min
            and maximum_full_party_damage is None
            and maximum_enemy_damage is None
            and target_damage_profile is None
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
            maximum_enemy_damage=maximum_enemy_damage,
            target_damage_profile=target_damage_profile,
        )

    return KnownEnemyCapacityPolicy(enabled=True, rules=rules)
