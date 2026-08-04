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
CALCULATION_VERSION = 9
RULESET = "post_2026_07_28_basic_attack_v9_low_party_damage_target_fallback"
# v9 是為了重判 v8 的失敗案例而新增；v8 已明確通過的結果不應因規則升版而整批下架。
# 更舊版本未具備相同的 7.2 檢核語意，仍維持 fail-closed 並等待現行規則重判。
LEGACY_PUBLIC_COMPATIBLE_VERSIONS = frozenset({8})
PUBLIC_STATUSES = frozenset({"valid", "not_applicable"})
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


def is_legacy_public_compatible_result(result: Any) -> bool:
    """判斷既有版本結果是否可沿用，避免規則升版時把已驗證正常資料整批下架。"""

    if not isinstance(result, dict):
        return False
    return (
        to_int(result.get("calculation_version")) in LEGACY_PUBLIC_COMPATIBLE_VERSIONS
        and result.get("status") in PUBLIC_STATUSES
        and not bool(result.get("hidden_from_public"))
    )


def is_public_compatible_result(result: Any) -> bool:
    """只接受現行結論，或明確列入相容清單的舊版正常結論。"""

    if not isinstance(result, dict):
        return False
    version = to_int(result.get("calculation_version"))
    version_is_supported = (
        version == CALCULATION_VERSION
        or version in LEGACY_PUBLIC_COMPATIBLE_VERSIONS
    )
    return (
        version_is_supported
        and result.get("status") in PUBLIC_STATUSES
        and not bool(result.get("hidden_from_public"))
    )


def attach_historical_damage_screen(
    result: dict[str, Any],
    historical_screen: Any | None,
) -> dict[str, Any]:
    """把不含玩家資訊的本地預篩證據附在既有結果，不改變生命池判定優先順序。"""

    if historical_screen is None:
        return result
    to_metrics = getattr(historical_screen, "to_metrics", None)
    if not callable(to_metrics):
        return result
    metrics = result.get("metrics")
    normalized_metrics = dict(metrics) if isinstance(metrics, dict) else {}
    normalized_metrics["historical_team_damage"] = to_metrics()
    result["metrics"] = normalized_metrics
    return result


def attach_known_capacity_screen(
    result: dict[str, Any],
    known_capacity_screen: Any | None,
) -> dict[str, Any]:
    """附上固定生命池的完整隊伍傷害下限，不把下限誤當成正常證據。"""

    if known_capacity_screen is None:
        return result
    to_metrics = getattr(known_capacity_screen, "to_metrics", None)
    if not callable(to_metrics):
        return result
    metrics = result.get("metrics")
    normalized_metrics = dict(metrics) if isinstance(metrics, dict) else {}
    normalized_metrics["known_full_party_damage"] = to_metrics()
    result["metrics"] = normalized_metrics
    return result


def needs_check(fight: dict[str, Any]) -> bool:
    result = current_result(fight)
    if result is None:
        return True
    if to_int(result.get("calculation_version")) == CALCULATION_VERSION:
        return False
    # v8 正常結論繼續公開且不占用日常回補額度；v8 失敗結果才逐批用 v9 重判。
    return not is_legacy_public_compatible_result(result)


def is_hidden_from_public(fight: Any) -> bool:
    if not isinstance(fight, dict):
        return False
    result = current_result(fight)
    if result is not None:
        # v8 已證實正常的資料維持公開；v8 失敗、其他舊版或無法驗證的結果仍保守隱藏。
        # 這讓 v9 能專注修正 v8 誤判案例，而不會在漫長回補期間撤下正常 7.2 成績。
        return not is_public_compatible_result(result)
    cutoff_ms = parse_iso_to_epoch_ms(DEFAULT_CUTOFF_ISO)
    # 回補尚未寫入標記的既有 fight 同樣採 fail-closed，直到離線批次處理完畢。
    return cutoff_ms is not None and is_in_scope({}, fight, cutoff_ms)


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
    historical_screen: Any | None = None,
    known_capacity_screen: Any | None = None,
) -> dict[str, Any]:
    # 有 Attack 標記時，即使 FFLogs 已 Private 或 HP 資源缺漏，也不能把它重新視為正常。
    baseline_exceeded = bool(getattr(historical_screen, "exceeds_threshold", False))
    known_capacity_exceeded = bool(getattr(known_capacity_screen, "exceeds_suspected_threshold", False))
    known_total_damage_exceeded = bool(
        getattr(known_capacity_screen, "exceeds_maximum_full_party_damage", False)
    )
    status = (
        "suspected"
        if attack_marker
        or baseline_exceeded
        or known_capacity_exceeded
        or known_total_damage_exceeded
        else "unverifiable"
    )
    reasons = [reason]
    if baseline_exceeded:
        reasons.append("historical_team_damage_exceeds_screen_threshold")
    if known_capacity_exceeded:
        reasons.append("full_party_damage_exceeds_known_hp_suspected_ratio_threshold")
    if known_total_damage_exceeded:
        reasons.append("full_party_damage_exceeds_confirmed_total_damage_upper_limit")
    if attack_marker:
        reasons.append("fflogs_basic_attack_exploit_marker")
    result = {
        "calculation_version": CALCULATION_VERSION,
        "ruleset": RULESET,
        "checked_at_iso": checked_at_iso,
        "status": status,
        # 無法驗證不是正常。這是避免新資料在 API 例外與回補尚未完成期間污染公開榜的
        # fail-closed 防線；原始 report/fight 仍完整保存，不會被刪除。
        "hidden_from_public": True,
        "reasons": reasons,
    }
    return attach_known_capacity_screen(
        attach_historical_damage_screen(result, historical_screen),
        known_capacity_screen,
    )


def make_known_capacity_result(
    *,
    checked_at_iso: str,
    known_capacity_screen: Any,
    hp_ratio_threshold: float,
    attack_marker: bool,
) -> dict[str, Any]:
    """套用固定生命池下限或固定完整隊伍總傷害範圍的離線結果。

    一般副本的 ``players[].total_damage`` 可能缺少 Limit Break 等未歸屬玩家來源，
    故只能作為超標異常的下限。只有經過樣本驗證、明確設定總傷害上下限的副本，
    才可在範圍內直接寫入 ``valid``；Attack 標記仍優先維持疑似異常。
    """

    raw_ratio = getattr(known_capacity_screen, "damage_to_known_hp_ratio", None)
    ratio = raw_ratio if isinstance(raw_ratio, (int, float)) else None
    damage_source = str(getattr(known_capacity_screen, "damage_source", ""))
    has_required_full_party_range = damage_source != "enemy_damage" and bool(
        getattr(known_capacity_screen, "has_required_full_party_damage_range", False)
    )
    matches_required_full_party_range = bool(
        getattr(known_capacity_screen, "matches_required_full_party_damage_range", False)
    )
    has_required_enemy_damage_range = damage_source == "enemy_damage" and bool(
        getattr(known_capacity_screen, "has_required_enemy_damage_range", False)
    )
    matches_required_enemy_damage_range = bool(
        getattr(known_capacity_screen, "matches_required_enemy_damage_range", False)
    )
    has_required_range = has_required_full_party_range or has_required_enemy_damage_range
    matches_required_range = (
        matches_required_enemy_damage_range
        if has_required_enemy_damage_range
        else matches_required_full_party_range
    )
    exceeds_maximum_full_party_damage = bool(
        getattr(known_capacity_screen, "exceeds_maximum_full_party_damage", False)
    )
    exceeds_maximum_enemy_damage = bool(
        getattr(known_capacity_screen, "exceeds_maximum_enemy_damage", False)
    )
    if has_required_range:
        if not matches_required_range:
            status = "excluded" if ratio is not None and ratio > hp_ratio_threshold else "suspected"
            reason = (
                "enemy_damage_outside_required_confirmed_total_range"
                if has_required_enemy_damage_range
                else "full_party_damage_outside_required_known_total_range"
            )
            reasons = [reason]
            if attack_marker:
                reasons.append("fflogs_basic_attack_exploit_marker")
            return attach_known_capacity_screen({
                "calculation_version": CALCULATION_VERSION,
                "ruleset": RULESET,
                "checked_at_iso": checked_at_iso,
                "status": status,
                "hidden_from_public": True,
                "reasons": reasons,
            }, known_capacity_screen)
        if attack_marker:
            return attach_known_capacity_screen({
                "calculation_version": CALCULATION_VERSION,
                "ruleset": RULESET,
                "checked_at_iso": checked_at_iso,
                "status": "suspected",
                "hidden_from_public": True,
                "reasons": ["fflogs_basic_attack_exploit_marker"],
            }, known_capacity_screen)
        return attach_known_capacity_screen({
            "calculation_version": CALCULATION_VERSION,
            "ruleset": RULESET,
            "checked_at_iso": checked_at_iso,
            "status": "valid",
            "hidden_from_public": False,
            "reasons": [
                "enemy_damage_matches_required_confirmed_total_range"
                if has_required_enemy_damage_range
                else "full_party_damage_matches_required_known_total_range"
            ],
        }, known_capacity_screen)

    if exceeds_maximum_full_party_damage or exceeds_maximum_enemy_damage:
        reasons = [
            "enemy_damage_exceeds_confirmed_total_damage_upper_limit"
            if exceeds_maximum_enemy_damage
            else "full_party_damage_exceeds_confirmed_total_damage_upper_limit"
        ]
        if attack_marker:
            reasons.append("fflogs_basic_attack_exploit_marker")
        return attach_known_capacity_screen({
            "calculation_version": CALCULATION_VERSION,
            "ruleset": RULESET,
            "checked_at_iso": checked_at_iso,
            "status": "suspected",
            "hidden_from_public": True,
            "reasons": reasons,
        }, known_capacity_screen)

    if ratio is not None and ratio > hp_ratio_threshold:
        result = {
            "calculation_version": CALCULATION_VERSION,
            "ruleset": RULESET,
            "checked_at_iso": checked_at_iso,
            "status": "excluded",
            "hidden_from_public": True,
            "reasons": ["full_party_damage_exceeds_known_hp_ratio_threshold"],
        }
        return attach_known_capacity_screen(result, known_capacity_screen)
    return make_unverifiable_result(
        checked_at_iso=checked_at_iso,
        reason="missing_enemy_hp_measurement",
        attack_marker=False,
        known_capacity_screen=known_capacity_screen,
    )


def make_historical_screen_valid_result(
    *,
    checked_at_iso: str,
    historical_screen: Any,
) -> dict[str, Any]:
    """歷史高端篩檢未命中時，避免為一般舊副本正常場次再查一次 API。"""

    return attach_historical_damage_screen({
        "calculation_version": CALCULATION_VERSION,
        "ruleset": RULESET,
        "checked_at_iso": checked_at_iso,
        "status": "valid",
        "hidden_from_public": False,
        "reasons": [],
    }, historical_screen)


def evaluate(
    *,
    checked_at_iso: str,
    enemy_damage: float,
    enemy_hp_capacity: float,
    target_count: int,
    attack_marker: bool,
    hp_ratio_threshold: float,
    suspected_hp_ratio_threshold: float,
    historical_screen: Any | None = None,
    known_capacity_screen: Any | None = None,
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
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        )

    ratio = enemy_damage / enemy_hp_capacity
    reasons: list[str] = []
    if ratio > hp_ratio_threshold:
        reasons.append("enemy_damage_exceeds_hp_ratio_threshold")
    elif ratio >= suspected_hp_ratio_threshold:
        reasons.append("enemy_damage_reaches_suspected_hp_ratio_threshold")
    raw_known_capacity_ratio = getattr(known_capacity_screen, "damage_to_known_hp_ratio", None)
    known_capacity_ratio = (
        raw_known_capacity_ratio
        if isinstance(raw_known_capacity_ratio, (int, float))
        else None
    )
    known_capacity_suspected = bool(getattr(known_capacity_screen, "exceeds_suspected_threshold", False))
    known_capacity_damage_source = str(getattr(known_capacity_screen, "damage_source", ""))
    known_capacity_has_required_full_party_range = (
        known_capacity_damage_source != "enemy_damage"
        and bool(getattr(known_capacity_screen, "has_required_full_party_damage_range", False))
    )
    known_capacity_matches_required_full_party_range = bool(
        getattr(known_capacity_screen, "matches_required_full_party_damage_range", False)
    )
    known_capacity_has_required_enemy_damage_range = (
        known_capacity_damage_source == "enemy_damage"
        and bool(getattr(known_capacity_screen, "has_required_enemy_damage_range", False))
    )
    known_capacity_matches_required_enemy_damage_range = bool(
        getattr(known_capacity_screen, "matches_required_enemy_damage_range", False)
    )
    known_capacity_has_required_range = (
        known_capacity_has_required_full_party_range
        or known_capacity_has_required_enemy_damage_range
    )
    known_capacity_matches_required_range = (
        known_capacity_matches_required_enemy_damage_range
        if known_capacity_has_required_enemy_damage_range
        else known_capacity_matches_required_full_party_range
    )
    known_capacity_exceeds_maximum_total_damage = bool(
        getattr(known_capacity_screen, "exceeds_maximum_full_party_damage", False)
    )
    known_capacity_exceeds_maximum_enemy_damage = bool(
        getattr(known_capacity_screen, "exceeds_maximum_enemy_damage", False)
    )
    if known_capacity_ratio is not None and known_capacity_ratio > hp_ratio_threshold:
        reasons.append("full_party_damage_exceeds_known_hp_ratio_threshold")
    elif known_capacity_suspected:
        reasons.append("full_party_damage_exceeds_known_hp_suspected_ratio_threshold")
    if known_capacity_has_required_range and not known_capacity_matches_required_range:
        reasons.append(
            "enemy_damage_outside_required_confirmed_total_range"
            if known_capacity_has_required_enemy_damage_range
            else "full_party_damage_outside_required_known_total_range"
        )
    if known_capacity_exceeds_maximum_total_damage:
        reasons.append("full_party_damage_exceeds_confirmed_total_damage_upper_limit")
    if known_capacity_exceeds_maximum_enemy_damage:
        reasons.append("enemy_damage_exceeds_confirmed_total_damage_upper_limit")
    if attack_marker:
        reasons.append("fflogs_basic_attack_exploit_marker")

    if (
        ratio > hp_ratio_threshold
        or (known_capacity_ratio is not None and known_capacity_ratio > hp_ratio_threshold)
    ):
        status = "excluded"
    elif (
        ratio >= suspected_hp_ratio_threshold
        or known_capacity_suspected
        or (known_capacity_has_required_range and not known_capacity_matches_required_range)
        or known_capacity_exceeds_maximum_total_damage
        or known_capacity_exceeds_maximum_enemy_damage
        or attack_marker
    ):
        status = "suspected"
    else:
        status = "valid"

    result = {
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
    return attach_known_capacity_screen(
        attach_historical_damage_screen(result, historical_screen),
        known_capacity_screen,
    )
