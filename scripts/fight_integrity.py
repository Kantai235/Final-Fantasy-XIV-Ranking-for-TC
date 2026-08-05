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

from dataclasses import dataclass, field
from datetime import datetime, timezone
from statistics import median
from typing import Any


DATA_INTEGRITY_KEY = "data_integrity"
CALCULATION_VERSION = 10
RULESET = "post_2026_07_28_basic_attack_v10_team_distribution"
# v10 新增 M5S～M8S 的 Attack 事件分布檢核。v8、v9 已明確通過的其他副本不能因
# 規則升版整批下架；回補器會另外挑出這四層缺少新分布證據的 v9 場次逐批重判。
LEGACY_PUBLIC_COMPATIBLE_VERSIONS = frozenset({8, 9})
PUBLIC_STATUSES = frozenset({"valid", "not_applicable"})
DEFAULT_CUTOFF_ISO = "2026-07-28T18:00:00+08:00"
DEFAULT_HP_RATIO_THRESHOLD = 1.15
DEFAULT_SUSPECTED_HP_RATIO_THRESHOLD = 1.14
DEFAULT_EXCLUDED_ENCOUNTER_KEYS = ("ultimate_bahamut",)

PHYSICAL_AUTO_ATTACK_JOBS = frozenset({
    "Paladin",
    "Warrior",
    "DarkKnight",
    "Gunbreaker",
    "Monk",
    "Dragoon",
    "Ninja",
    "Samurai",
    "Reaper",
    "Viper",
    "Bard",
    "Machinist",
    "Dancer",
})


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def to_int(value: Any) -> int | None:
    number = to_number(value)
    return int(number) if number is not None and number.is_integer() else None


@dataclass(frozen=True)
class BasicAttackDistributionScreen:
    """保存 Attack 事件分布的純計算結果，不攜帶或落地 raw events。"""

    status: str
    reason: str | None
    metrics: dict[str, Any]

    @property
    def is_abnormal(self) -> bool:
        return self.status in {"excluded", "suspected"}


@dataclass(frozen=True)
class BasicAttackDistributionPolicy:
    """M5S～M8S 同場多人普攻異常的版本化門檻。

    玩家必須同時跨過「純一般普攻每擊中位數」與「普攻占個人總傷比例」兩道門檻；
    戰鬥層再要求多名物理職業同時命中。這樣不會因單一玩家死亡、低 GCD 覆蓋率、
    少數暴擊或直擊尖峰，就把正常戰鬥誤判為整場資料異常。
    """

    enabled: bool = False
    encounter_keys: frozenset[str] = field(default_factory=frozenset)
    reference_version: str = ""
    reference_hit_median: float = 4_805.7
    reference_attack_share: float = 0.0861
    job_hit_references: dict[str, float] = field(default_factory=dict)
    job_share_references: dict[str, float] = field(default_factory=dict)
    minimum_attack_event_count: int = 60
    minimum_pure_normal_count: int = 30
    minimum_player_hit_median: float = 10_000.0
    hit_reference_multiplier: float = 2.0
    minimum_player_attack_share: float = 0.15
    share_reference_multiplier: float = 1.5
    suspected_minimum_eligible_players: int = 3
    suspected_minimum_flagged_players: int = 3
    suspected_minimum_flagged_ratio: float = 0.60
    excluded_minimum_eligible_players: int = 4
    excluded_minimum_flagged_players: int = 4
    excluded_minimum_flagged_ratio: float = 0.75
    excluded_minimum_group_hit_median: float = 15_000.0
    excluded_minimum_group_attack_share: float = 0.20
    support_minimum_pure_normal_count: int = 3
    support_minimum_hit_median: float = 10_000.0

    @classmethod
    def disabled(cls) -> "BasicAttackDistributionPolicy":
        return cls()

    @classmethod
    def from_mapping(cls, raw: Any) -> "BasicAttackDistributionPolicy":
        if not isinstance(raw, dict) or raw.get("enabled") is False:
            return cls.disabled()

        encounter_keys = raw.get("encounter_keys")
        if not isinstance(encounter_keys, list) or not encounter_keys:
            raise RuntimeError("basic_attack_distribution.encounter_keys 必須是非空陣列。")

        def positive_number(name: str, default: float) -> float:
            value = to_number(raw.get(name))
            normalized = default if value is None else value
            if normalized <= 0:
                raise RuntimeError(f"basic_attack_distribution.{name} 必須大於 0。")
            return normalized

        def positive_int(name: str, default: int) -> int:
            value = to_int(raw.get(name))
            normalized = default if value is None else value
            if normalized <= 0:
                raise RuntimeError(f"basic_attack_distribution.{name} 必須是正整數。")
            return normalized

        def ratio(name: str, default: float) -> float:
            value = positive_number(name, default)
            if value > 1:
                raise RuntimeError(f"basic_attack_distribution.{name} 必須介於 0 與 1。")
            return value

        job_references = raw.get("job_references")
        job_hit_references: dict[str, float] = {}
        job_share_references: dict[str, float] = {}
        if isinstance(job_references, dict):
            for job, reference in job_references.items():
                if not isinstance(job, str) or not isinstance(reference, dict):
                    continue
                hit = to_number(reference.get("hit_median"))
                share = to_number(reference.get("attack_share"))
                if hit is not None and hit > 0:
                    job_hit_references[job] = hit
                if share is not None and 0 < share <= 1:
                    job_share_references[job] = share

        return cls(
            enabled=True,
            encounter_keys=frozenset(str(value) for value in encounter_keys if isinstance(value, str) and value),
            reference_version=str(raw.get("reference_version") or ""),
            reference_hit_median=positive_number("reference_hit_median", 4_805.7),
            reference_attack_share=ratio("reference_attack_share", 0.0861),
            job_hit_references=job_hit_references,
            job_share_references=job_share_references,
            minimum_attack_event_count=positive_int("minimum_attack_event_count", 60),
            minimum_pure_normal_count=positive_int("minimum_pure_normal_count", 30),
            minimum_player_hit_median=positive_number("minimum_player_hit_median", 10_000),
            hit_reference_multiplier=positive_number("hit_reference_multiplier", 2.0),
            minimum_player_attack_share=ratio("minimum_player_attack_share", 0.15),
            share_reference_multiplier=positive_number("share_reference_multiplier", 1.5),
            suspected_minimum_eligible_players=positive_int("suspected_minimum_eligible_players", 3),
            suspected_minimum_flagged_players=positive_int("suspected_minimum_flagged_players", 3),
            suspected_minimum_flagged_ratio=ratio("suspected_minimum_flagged_ratio", 0.60),
            excluded_minimum_eligible_players=positive_int("excluded_minimum_eligible_players", 4),
            excluded_minimum_flagged_players=positive_int("excluded_minimum_flagged_players", 4),
            excluded_minimum_flagged_ratio=ratio("excluded_minimum_flagged_ratio", 0.75),
            excluded_minimum_group_hit_median=positive_number(
                "excluded_minimum_group_hit_median", 15_000
            ),
            excluded_minimum_group_attack_share=ratio(
                "excluded_minimum_group_attack_share", 0.20
            ),
            support_minimum_pure_normal_count=positive_int(
                "support_minimum_pure_normal_count", 3
            ),
            support_minimum_hit_median=positive_number("support_minimum_hit_median", 10_000),
        )

    def applies(self, encounter_key: str, fight: dict[str, Any]) -> bool:
        return (
            self.enabled
            and encounter_key in self.encounter_keys
            and fight.get("kill") is True
            and fight.get("has_echo") is not True
            and to_int(fight.get("size")) == 8
            and fight.get("standard_composition") is not False
        )

    def screen(self, measurement: dict[str, Any]) -> BasicAttackDistributionScreen:
        raw_players = measurement.get("players") if isinstance(measurement, dict) else None
        players = raw_players if isinstance(raw_players, list) else []
        eligible: list[dict[str, Any]] = []
        flagged: list[dict[str, Any]] = []
        supporting_nonphysical: list[dict[str, Any]] = []

        for raw_player in players:
            if not isinstance(raw_player, dict):
                continue
            job = str(raw_player.get("job") or "")
            attack_count = to_int(raw_player.get("attack_event_count")) or 0
            pure_count = to_int(raw_player.get("pure_normal_count")) or 0
            hit_median = to_number(raw_player.get("pure_normal_median"))
            attack_share = to_number(raw_player.get("attack_share"))
            if hit_median is None or attack_share is None:
                continue

            if job not in PHYSICAL_AUTO_ATTACK_JOBS:
                if (
                    pure_count >= self.support_minimum_pure_normal_count
                    and hit_median >= self.support_minimum_hit_median
                ):
                    supporting_nonphysical.append(raw_player)
                continue
            if (
                attack_count < self.minimum_attack_event_count
                or pure_count < self.minimum_pure_normal_count
            ):
                continue

            eligible.append(raw_player)
            hit_reference = self.job_hit_references.get(job, self.reference_hit_median)
            share_reference = self.job_share_references.get(job, self.reference_attack_share)
            hit_threshold = max(
                self.minimum_player_hit_median,
                hit_reference * self.hit_reference_multiplier,
            )
            share_threshold = max(
                self.minimum_player_attack_share,
                share_reference * self.share_reference_multiplier,
            )
            if hit_median < hit_threshold or attack_share < share_threshold:
                continue
            flagged.append({
                "source_id": to_int(raw_player.get("source_id")),
                "job": job,
                "attack_event_count": attack_count,
                "pure_normal_count": pure_count,
                "pure_normal_median": round(hit_median, 3),
                "attack_share": round(attack_share, 6),
                "hit_reference_ratio": round(hit_median / hit_reference, 6),
                "share_reference_ratio": round(attack_share / share_reference, 6),
            })

        eligible_count = len(eligible)
        flagged_count = len(flagged)
        flagged_ratio = flagged_count / eligible_count if eligible_count else 0.0
        group_hit_median = (
            median(float(player["pure_normal_median"]) for player in flagged)
            if flagged
            else None
        )
        group_attack_share = (
            median(float(player["attack_share"]) for player in flagged)
            if flagged
            else None
        )

        excluded = (
            eligible_count >= self.excluded_minimum_eligible_players
            and flagged_count >= self.excluded_minimum_flagged_players
            and flagged_ratio >= self.excluded_minimum_flagged_ratio
            and group_hit_median is not None
            and group_hit_median >= self.excluded_minimum_group_hit_median
            and group_attack_share is not None
            and group_attack_share >= self.excluded_minimum_group_attack_share
        )
        suspected = (
            (
                eligible_count >= self.suspected_minimum_eligible_players
                and flagged_count >= self.suspected_minimum_flagged_players
                and flagged_ratio >= self.suspected_minimum_flagged_ratio
            )
            or (flagged_count >= 2 and bool(supporting_nonphysical))
        )
        if excluded:
            status = "excluded"
            reason = "team_basic_attack_damage_distribution_abnormal"
        elif suspected:
            status = "suspected"
            reason = "multiple_players_basic_attack_metrics_abnormal"
        elif eligible_count >= self.suspected_minimum_eligible_players:
            status = "valid"
            reason = None
        else:
            status = "insufficient_sample"
            reason = None

        metrics: dict[str, Any] = {
            "reference_version": self.reference_version,
            "actual_event_count": to_int(measurement.get("actual_event_count")) or 0,
            "mapped_event_count": to_int(measurement.get("mapped_event_count")) or 0,
            "eligible_player_count": eligible_count,
            "flagged_player_count": flagged_count,
            "flagged_player_ratio": round(flagged_ratio, 6),
            "supporting_nonphysical_count": len(supporting_nonphysical),
            "minimum_player_hit_median": self.minimum_player_hit_median,
            "minimum_player_attack_share": self.minimum_player_attack_share,
            "group_hit_median": round(group_hit_median, 3) if group_hit_median is not None else None,
            "group_attack_share": (
                round(group_attack_share, 6) if group_attack_share is not None else None
            ),
        }
        if flagged:
            metrics["flagged_players"] = flagged
        return BasicAttackDistributionScreen(status=status, reason=reason, metrics=metrics)


def summarize_basic_attack_events(
    events: list[Any],
    players: list[Any],
) -> dict[str, Any]:
    """把 ability 7 raw events 壓成可重判的最小玩家彙總。

    FFLogs 同一個命中通常同時回傳 ``calculateddamage`` 與 ``damage``；只能採後者，
    否則命中數與普攻總傷會重複兩次。純一般普攻另排除暴擊與直擊，再除以 FFLogs
    ``multiplier``，避免團輔、目標減傷或易傷直接污染每擊基準。
    """

    player_by_source: dict[int, dict[str, Any]] = {}
    for raw_player in players:
        if not isinstance(raw_player, dict):
            continue
        source_id = to_int(raw_player.get("fflogs_id"))
        if source_id is not None:
            player_by_source[source_id] = raw_player

    grouped: dict[int, list[dict[str, Any]]] = {}
    seen: set[tuple[Any, ...]] = set()
    actual_event_count = 0
    for raw_event in events:
        if not isinstance(raw_event, dict) or raw_event.get("type") != "damage":
            continue
        ability_id = to_int(raw_event.get("abilityGameID"))
        if ability_id is not None and ability_id != 7:
            continue
        source_id = to_int(raw_event.get("sourceID"))
        amount = to_number(raw_event.get("amount"))
        if source_id is None or amount is None or amount <= 0:
            continue
        identity = (
            raw_event.get("timestamp"),
            raw_event.get("packetID"),
            source_id,
            raw_event.get("targetID"),
            amount,
            raw_event.get("hitType"),
            bool(raw_event.get("directHit")),
        )
        if identity in seen:
            continue
        seen.add(identity)
        actual_event_count += 1
        grouped.setdefault(source_id, []).append(raw_event)

    summaries: list[dict[str, Any]] = []
    mapped_event_count = 0
    for source_id, source_events in sorted(grouped.items()):
        player = player_by_source.get(source_id)
        total_damage = to_number(player.get("total_damage")) if player is not None else None
        if player is None or total_damage is None or total_damage <= 0:
            continue
        mapped_event_count += len(source_events)
        attack_damage = sum(to_number(event.get("amount")) or 0 for event in source_events)
        pure_normal: list[float] = []
        for event in source_events:
            if to_int(event.get("hitType")) != 1 or bool(event.get("directHit")):
                continue
            amount = to_number(event.get("amount"))
            if amount is None or amount <= 0:
                continue
            multiplier = to_number(event.get("multiplier")) or 1.0
            pure_normal.append(amount / multiplier)
        summaries.append({
            "source_id": source_id,
            "job": str(player.get("job") or ""),
            "attack_event_count": len(source_events),
            "pure_normal_count": len(pure_normal),
            "pure_normal_median": round(median(pure_normal), 3) if pure_normal else None,
            "attack_damage": round(attack_damage, 3),
            "attack_share": round(attack_damage / total_damage, 6),
        })

    return {
        "actual_event_count": actual_event_count,
        "mapped_event_count": mapped_event_count,
        "players": summaries,
    }


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


def apply_basic_attack_distribution_screen(
    result: dict[str, Any],
    screen: BasicAttackDistributionScreen | None,
) -> dict[str, Any]:
    """把事件分布作為獨立 OR 分支合併，不讓正常事件結果覆蓋其他異常證據。"""

    if screen is None:
        return result
    metrics = result.get("metrics")
    normalized_metrics = dict(metrics) if isinstance(metrics, dict) else {}
    normalized_metrics["basic_attack_distribution"] = dict(screen.metrics)
    result["metrics"] = normalized_metrics
    if not screen.is_abnormal:
        return result

    reasons = result.get("reasons")
    normalized_reasons = list(reasons) if isinstance(reasons, list) else []
    if screen.reason and screen.reason not in normalized_reasons:
        normalized_reasons.append(screen.reason)
    result["reasons"] = normalized_reasons
    if screen.status == "excluded" or result.get("status") != "excluded":
        result["status"] = screen.status
    result["hidden_from_public"] = True
    return result


def make_basic_attack_distribution_result(
    *,
    checked_at_iso: str,
    screen: BasicAttackDistributionScreen,
) -> dict[str, Any]:
    """事件分布已足以判定異常時，不再為同一場額外消耗敵方生命池 API。"""

    return apply_basic_attack_distribution_screen({
        "calculation_version": CALCULATION_VERSION,
        "ruleset": RULESET,
        "checked_at_iso": checked_at_iso,
        "status": "valid",
        "hidden_from_public": False,
        "reasons": [],
    }, screen)


def needs_check(fight: dict[str, Any]) -> bool:
    result = current_result(fight)
    if result is None:
        return True
    if to_int(result.get("calculation_version")) == CALCULATION_VERSION:
        # 可重現的 missing_enemy_max_hp 等結果不應每輪重查；但執行期例外只是一時失敗，
        # 必須重新排入後續批次，避免程式修正後仍永久停在 unverifiable。
        reasons = result.get("reasons")
        return (
            result.get("status") == "unverifiable"
            and isinstance(reasons, list)
            and "integrity_measurement_failed" in reasons
        )
    # v8/v9 正常結論繼續公開且不占用日常回補額度；失敗結果才逐批用現行規則重判。
    return not is_legacy_public_compatible_result(result)


def is_hidden_from_public(fight: Any) -> bool:
    if not isinstance(fight, dict):
        return False
    result = current_result(fight)
    if result is not None:
        # v8/v9 已證實正常的資料維持公開；舊版失敗、未知版本或無法驗證的結果仍保守隱藏。
        # 這讓 v10 能優先補 M5S～M8S 的普攻分布，而不會在漫長回補期間撤下其他正常成績。
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
    basic_attack_screen: BasicAttackDistributionScreen | None = None,
) -> dict[str, Any]:
    """建立唯一的判定結果；倍率是全隊傷害 / 目標最大 HP 總和。

    1.15 以上（嚴格大於）是高信心排除；1.14 至 1.15 的邊界群組只標為疑似。
    後者來自極澤蓮尼亞實測：同一群組大多已有 Attack 標記，但少數 report
    漏報標記，因此不能再依賴泛用 exploit:6 補判。
    """
    if enemy_damage < 0 or enemy_hp_capacity <= 0 or target_count <= 0:
        return apply_basic_attack_distribution_screen(make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="invalid_enemy_hp_measurement",
            attack_marker=attack_marker,
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        ), basic_attack_screen)

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
    result = attach_known_capacity_screen(
        attach_historical_damage_screen(result, historical_screen),
        known_capacity_screen,
    )
    return apply_basic_attack_distribution_screen(result, basic_attack_screen)
