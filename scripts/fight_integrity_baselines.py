"""可撤除的歷史全隊傷害預篩規則。

這個模組刻意不把 ``players[].total_damage`` 當成 Boss 生命池。排行榜來源只保存
繁中服角色的 Damage Done Source 列，Limit Break、Pet 或多目標傷害可能使其偏離敵方
實際承傷。因此它只能在 2026-07-28 後先篩出「明顯高於乾淨歷史上緣」的候選；最終的
``excluded`` 判定仍必須交由目標生命池量測完成。

歷史基準是小型、可追溯的設定檔，不包含 report、玩家或 FFLogs 回應。等 Log 工具修正
後，可以移除此模組與設定檔；已寫入 fight 的 ``data_integrity`` 狀態不受影響。
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
METRIC_NAME = "full_traditional_chinese_party_player_total_damage"


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
class HistoricalDamageBaseline:
    """單一副本在問題切點前的乾淨、高端全隊角色傷害參考值。"""

    upper_reference_damage: int
    sample_count: int
    unique_fight_count: int


@dataclass(frozen=True)
class HistoricalDamageScreen:
    """不含玩家資料、可安全寫入 fight ``data_integrity.metrics`` 的預篩結果。"""

    encounter_key: str
    team_total_damage: int
    upper_reference_damage: int
    screening_threshold: int
    screening_multiplier: float
    sample_count: int
    unique_fight_count: int
    reference_cutoff_iso: str

    @property
    def exceeds_threshold(self) -> bool:
        return self.team_total_damage > self.screening_threshold

    def to_metrics(self) -> dict[str, Any]:
        return {
            "metric": METRIC_NAME,
            "encounter_key": self.encounter_key,
            "team_total_damage": self.team_total_damage,
            "upper_reference_damage": self.upper_reference_damage,
            "screening_threshold": self.screening_threshold,
            "screening_multiplier": self.screening_multiplier,
            "sample_count": self.sample_count,
            "unique_fight_count": self.unique_fight_count,
            "reference_cutoff_iso": self.reference_cutoff_iso,
            "exceeds_threshold": self.exceeds_threshold,
        }


@dataclass(frozen=True)
class HistoricalDamageBaselinePolicy:
    """讀取後的歷史預篩設定；停用時 ``baselines`` 保持空集合。"""

    enabled: bool
    reference_cutoff_iso: str
    screening_multiplier: float
    baselines: dict[str, HistoricalDamageBaseline]

    @classmethod
    def disabled(cls) -> "HistoricalDamageBaselinePolicy":
        return cls(
            enabled=False,
            reference_cutoff_iso="",
            screening_multiplier=1.05,
            baselines={},
        )

    def screen(self, encounter_key: str, fight: dict[str, Any]) -> HistoricalDamageScreen | None:
        """只接受完整繁中隊伍，避免部分收錄的角色傷害被錯當成正常低值。"""

        if not self.enabled:
            return None
        baseline = self.baselines.get(encounter_key)
        if baseline is None:
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
        screening_threshold = round(baseline.upper_reference_damage * self.screening_multiplier)
        return HistoricalDamageScreen(
            encounter_key=encounter_key,
            team_total_damage=team_total_damage,
            upper_reference_damage=baseline.upper_reference_damage,
            screening_threshold=screening_threshold,
            screening_multiplier=self.screening_multiplier,
            sample_count=baseline.sample_count,
            unique_fight_count=baseline.unique_fight_count,
            reference_cutoff_iso=self.reference_cutoff_iso,
        )


def load_historical_damage_baseline_policy(path: Path) -> HistoricalDamageBaselinePolicy:
    """載入版本化的小型設定；缺檔或明確停用時不啟用預篩。"""

    if not path.exists():
        return HistoricalDamageBaselinePolicy.disabled()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"無法讀取歷史傷害基準設定：{path}") from error
    if not isinstance(raw, dict):
        raise RuntimeError("歷史傷害基準設定必須是 JSON 物件。")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise RuntimeError(f"歷史傷害基準設定 schema_version 必須是 {SCHEMA_VERSION}。")
    if not _to_bool(raw.get("enabled"), True):
        return HistoricalDamageBaselinePolicy.disabled()
    if raw.get("metric") != METRIC_NAME:
        raise RuntimeError(f"歷史傷害基準 metric 必須是 {METRIC_NAME}。")

    reference_cutoff_iso = raw.get("reference_cutoff_iso")
    if not isinstance(reference_cutoff_iso, str) or not reference_cutoff_iso:
        raise RuntimeError("歷史傷害基準必須記錄 reference_cutoff_iso。")
    multiplier = _to_number(raw.get("screening_multiplier"))
    if multiplier is None or multiplier <= 1:
        raise RuntimeError("歷史傷害基準 screening_multiplier 必須大於 1。")
    minimum_sample_count = _to_positive_int(raw.get("minimum_sample_count"))
    if minimum_sample_count is None:
        raise RuntimeError("歷史傷害基準 minimum_sample_count 必須是正整數。")

    raw_baselines = raw.get("encounters")
    if not isinstance(raw_baselines, dict):
        raise RuntimeError("歷史傷害基準 encounters 必須是物件。")
    baselines: dict[str, HistoricalDamageBaseline] = {}
    for encounter_key, entry in raw_baselines.items():
        if not isinstance(encounter_key, str) or not encounter_key or not isinstance(entry, dict):
            raise RuntimeError("歷史傷害基準 encounters 含有無效項目。")
        upper_reference_damage = _to_positive_int(entry.get("upper_reference_damage"))
        sample_count = _to_positive_int(entry.get("sample_count"))
        unique_fight_count = _to_positive_int(entry.get("unique_fight_count"))
        if (
            upper_reference_damage is None
            or sample_count is None
            or unique_fight_count is None
            or unique_fight_count < minimum_sample_count
        ):
            raise RuntimeError(f"歷史傷害基準 {encounter_key} 的樣本或上緣值無效。")
        baselines[encounter_key] = HistoricalDamageBaseline(
            upper_reference_damage=upper_reference_damage,
            sample_count=sample_count,
            unique_fight_count=unique_fight_count,
        )

    return HistoricalDamageBaselinePolicy(
        enabled=True,
        reference_cutoff_iso=reference_cutoff_iso,
        screening_multiplier=multiplier,
        baselines=baselines,
    )
