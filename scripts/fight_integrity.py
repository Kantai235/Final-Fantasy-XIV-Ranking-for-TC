"""暫時性的 FFLogs 戰鬥完整性檢核共用邏輯。

2026-07-28 後，部分 FFLogs 日誌的普攻解析會讓 rDPS 與全隊傷害偏高。本模組
只定義可追溯的 fight 層資料契約與純計算，不讀寫檔案，也不直接呼叫 API：

* ``backfill_fight_integrity.py`` 以小批次查詢敵方承傷與最大 HP，逐步寫入結果；
* ``fetch_fflogs.py`` 與 ``build_user_data.mjs`` 只根據 ``hidden_from_public`` 隱藏
  已標記 fight，原始 report / fight / 玩家列始終保留。

日後 Log 工具修正後，可停止執行回補腳本；既有標記仍留在歷史資料，且本模組是唯一
需要移除的檢核規則集合，不會把暫時規則散落進 DPS 計算或 Vue 呈現層。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


DATA_INTEGRITY_KEY = "data_integrity"
CALCULATION_VERSION = 2
RULESET = "post_2026_07_28_basic_attack_v2"
DEFAULT_CUTOFF_ISO = "2026-07-28T18:00:00+08:00"
DEFAULT_HP_RATIO_THRESHOLD = 1.15
DEFAULT_SUSPECTED_HP_RATIO_THRESHOLD = 1.14
DEFAULT_EXCLUDED_ENCOUNTER_KEYS = ("ultimate_bahamut",)


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def to_int(value: Any) -> int | None:
    number = to_number(value)
    return int(number) if number is not None and number.is_integer() else None


def parse_iso_to_epoch_ms(value: Any) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp() * 1000)


def fight_recorded_at_ms(report: dict[str, Any], fight: dict[str, Any]) -> int | None:
    for value in (
        fight.get("recorded_at"),
        fight.get("recordedAt"),
        report.get("report_end_time"),
        report.get("endTime"),
    ):
        number = to_number(value)
        if number is not None and number >= 946684800000:
            return int(number)
    for value in (
        fight.get("recorded_at_iso"),
        report.get("report_end_time_iso"),
    ):
        parsed = parse_iso_to_epoch_ms(value)
        if parsed is not None:
            return parsed
    return None


def is_in_scope(report: dict[str, Any], fight: dict[str, Any], cutoff_ms: int) -> bool:
    recorded_at_ms = fight_recorded_at_ms(report, fight)
    return recorded_at_ms is not None and recorded_at_ms >= cutoff_ms


def has_basic_attack_exploit_marker(fight: dict[str, Any]) -> bool:
    """只識別 guid=7 / Attack，不採用大量正常紀錄也會出現的泛用 exploit:6。"""
    summary = fight.get("damage_done_summary")
    if not isinstance(summary, dict):
        return False
    details = summary.get("exploitDetails")
    if not isinstance(details, list):
        return False
    for detail in details:
        if not isinstance(detail, dict):
            continue
        abilities = detail.get("abilities")
        if not isinstance(abilities, list):
            continue
        for ability in abilities:
            if not isinstance(ability, dict):
                continue
            if ability.get("guid") == 7 or ability.get("name") == "Attack":
                return True
    return False


def current_result(fight: dict[str, Any]) -> dict[str, Any] | None:
    value = fight.get(DATA_INTEGRITY_KEY)
    return value if isinstance(value, dict) else None


def needs_check(fight: dict[str, Any]) -> bool:
    result = current_result(fight)
    return not result or result.get("calculation_version") != CALCULATION_VERSION


def is_hidden_from_public(fight: Any) -> bool:
    if not isinstance(fight, dict):
        return False
    result = current_result(fight)
    return bool(result and result.get("hidden_from_public"))


def make_not_applicable_result(
    *,
    checked_at_iso: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "calculation_version": CALCULATION_VERSION,
        "ruleset": RULESET,
        "checked_at_iso": checked_at_iso,
        "status": "not_applicable",
        "hidden_from_public": False,
        "reasons": [reason],
    }


def make_unverifiable_result(
    *,
    checked_at_iso: str,
    reason: str,
    attack_marker: bool,
) -> dict[str, Any]:
    # 有 Attack 標記時，即使 FFLogs 已 Private 或 HP 資源缺漏，也不能把它重新視為正常。
    status = "suspected" if attack_marker else "unverifiable"
    reasons = [reason]
    if attack_marker:
        reasons.append("fflogs_basic_attack_exploit_marker")
    return {
        "calculation_version": CALCULATION_VERSION,
        "ruleset": RULESET,
        "checked_at_iso": checked_at_iso,
        "status": status,
        "hidden_from_public": attack_marker,
        "reasons": reasons,
    }


def evaluate(
    *,
    checked_at_iso: str,
    enemy_damage: float,
    enemy_hp_capacity: float,
    target_count: int,
    attack_marker: bool,
    hp_ratio_threshold: float,
    suspected_hp_ratio_threshold: float,
) -> dict[str, Any]:
    """建立唯一的判定結果；倍率是全隊傷害 / 目標最大 HP 總和。

    1.15 以上（嚴格大於）是高信心排除；1.14 至 1.15 的邊界群組只標為疑似。
    後者來自極澤蓮尼亞實測：同一群組大多已有 Attack 標記，但少數 report
    漏報標記，因此不能再依賴泛用 exploit:6 補判。
    """
    if enemy_damage < 0 or enemy_hp_capacity <= 0 or target_count <= 0:
        return make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="invalid_enemy_hp_measurement",
            attack_marker=attack_marker,
        )

    ratio = enemy_damage / enemy_hp_capacity
    reasons: list[str] = []
    if ratio > hp_ratio_threshold:
        reasons.append("enemy_damage_exceeds_hp_ratio_threshold")
    elif ratio >= suspected_hp_ratio_threshold:
        reasons.append("enemy_damage_reaches_suspected_hp_ratio_threshold")
    if attack_marker:
        reasons.append("fflogs_basic_attack_exploit_marker")

    if ratio > hp_ratio_threshold:
        status = "excluded"
    elif ratio >= suspected_hp_ratio_threshold or attack_marker:
        status = "suspected"
    else:
        status = "valid"

    return {
        "calculation_version": CALCULATION_VERSION,
        "ruleset": RULESET,
        "checked_at_iso": checked_at_iso,
        "status": status,
        # 兩種異常訊號都從一般公開榜單排除；unverifiable 只保留檢查紀錄，不得誤殺。
        "hidden_from_public": status in {"excluded", "suspected"},
        "reasons": reasons,
        "metrics": {
            "enemy_damage": round(enemy_damage, 3),
            "enemy_hp_capacity": round(enemy_hp_capacity, 3),
            "damage_to_hp_ratio": round(ratio, 6),
            "hp_ratio_threshold": hp_ratio_threshold,
            "suspected_hp_ratio_threshold": suspected_hp_ratio_threshold,
            "target_count": target_count,
        },
    }
