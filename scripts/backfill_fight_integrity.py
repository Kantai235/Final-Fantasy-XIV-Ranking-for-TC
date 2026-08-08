"""分批回補 2026-07-28 後 FFLogs 戰鬥的普攻資料完整性檢核。"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402
import fight_integrity as integrity  # noqa: E402
import fight_integrity_baselines as historical_baselines  # noqa: E402
import fight_integrity_cache as integrity_cache  # noqa: E402
import fight_integrity_known_capacity as known_capacity  # noqa: E402
from fflogs_pipeline.graphql_queries import (  # noqa: E402
    建立戰鬥完整性目標生命值查詢,
    戰鬥完整性目標傷害查詢,
)


read_json = getattr(fflogs, "讀取_json")
ranking_path = getattr(fflogs, "排行榜檔案路徑")
load_ranking_file = getattr(fflogs, "讀取排行榜檔案")
write_ranking_file = getattr(fflogs, "寫入排行榜檔案")
read_credentials = getattr(fflogs, "讀取認證設定")
auth_pool_class = getattr(fflogs, "FFLogs認證池")
execute_graphql = getattr(fflogs, "執行_graphql")
milliseconds_to_iso = getattr(fflogs, "毫秒轉_iso")
report_is_hidden = getattr(fflogs, "報告已標記隱藏")
mark_ranking_report_hidden = getattr(fflogs, "標記排行榜報告隱藏")
report_access_error_class = getattr(fflogs, "FFLogs報告存取錯誤")
graphql_error_class = getattr(fflogs, "FFLogsGraphQL錯誤")
hidden_reason_inaccessible = getattr(fflogs, "報告無法存取隱藏原因")
query_basic_attack_events = getattr(fflogs, "查詢戰鬥完整性普攻事件")

DEFAULT_CACHE_PATH = PROJECT_ROOT / "data" / "local-cache" / "fight-integrity" / "measurements.json"


@dataclass
class IntegrityConfig:
    enabled: bool
    cutoff_ms: int
    cutoff_iso: str
    hp_ratio_threshold: float
    suspected_hp_ratio_threshold: float
    excluded_encounter_keys: set[str]
    default_report_limit: int
    historical_damage_baselines: historical_baselines.HistoricalDamageBaselinePolicy = field(
        default_factory=historical_baselines.HistoricalDamageBaselinePolicy.disabled
    )
    known_enemy_capacity: known_capacity.KnownEnemyCapacityPolicy = field(
        default_factory=known_capacity.KnownEnemyCapacityPolicy.disabled
    )
    basic_attack_distribution: integrity.BasicAttackDistributionPolicy = field(
        default_factory=integrity.BasicAttackDistributionPolicy.disabled
    )


@dataclass
class Candidate:
    encounter_key: str
    encounter: dict[str, Any]
    ranking: dict[str, Any]
    report_code: str
    report: dict[str, Any]
    fight: dict[str, Any]
    sort_time: int

    @property
    def label(self) -> str:
        return f"{self.encounter_key} {self.report_code} fight={self.fight.get('fight_id')}"


def parse_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return default


def load_config() -> IntegrityConfig:
    raw = read_json(PROJECT_ROOT / "config" / "fflogs.json", {})
    raw_config = raw.get("fight_integrity_check") if isinstance(raw, dict) else {}
    config = raw_config if isinstance(raw_config, dict) else {}

    cutoff_iso = str(config.get("cutoff_iso") or integrity.DEFAULT_CUTOFF_ISO)
    cutoff_ms = integrity.parse_iso_to_epoch_ms(cutoff_iso)
    if cutoff_ms is None:
        raise RuntimeError("fight_integrity_check.cutoff_iso 必須是含時區的有效 ISO 時間。")

    threshold = integrity.to_number(config.get("hp_ratio_threshold"))
    if threshold is None or threshold <= 1:
        raise RuntimeError("fight_integrity_check.hp_ratio_threshold 必須大於 1。")
    suspected_threshold = integrity.to_number(config.get("suspected_hp_ratio_threshold"))
    if suspected_threshold is None:
        suspected_threshold = integrity.DEFAULT_SUSPECTED_HP_RATIO_THRESHOLD
    if suspected_threshold <= 1 or suspected_threshold >= threshold:
        raise RuntimeError(
            "fight_integrity_check.suspected_hp_ratio_threshold 必須大於 1 且小於 hp_ratio_threshold。"
        )

    excluded = config.get("excluded_encounter_keys")
    excluded_keys = {
        str(value)
        for value in (excluded if isinstance(excluded, list) else integrity.DEFAULT_EXCLUDED_ENCOUNTER_KEYS)
        if isinstance(value, str) and value
    }
    report_limit = integrity.to_int(config.get("report_limit"))
    baseline_file = config.get("historical_baseline_file")
    if not isinstance(baseline_file, str) or not baseline_file:
        raise RuntimeError("fight_integrity_check.historical_baseline_file 必須是設定檔路徑。")
    baseline_path = Path(baseline_file)
    if not baseline_path.is_absolute():
        baseline_path = PROJECT_ROOT / baseline_path
    historical_damage_baselines = historical_baselines.load_historical_damage_baseline_policy(baseline_path)
    known_capacity_file = config.get("known_enemy_capacity_file")
    if not isinstance(known_capacity_file, str) or not known_capacity_file:
        raise RuntimeError("fight_integrity_check.known_enemy_capacity_file 必須是設定檔路徑。")
    known_capacity_path = Path(known_capacity_file)
    if not known_capacity_path.is_absolute():
        known_capacity_path = PROJECT_ROOT / known_capacity_path
    known_enemy_capacity = known_capacity.load_known_enemy_capacity_policy(known_capacity_path)
    basic_attack_distribution = integrity.BasicAttackDistributionPolicy.from_mapping(
        config.get("basic_attack_distribution")
    )

    enabled = parse_bool(config.get("enabled"), True)
    enabled = parse_bool(os.getenv("FFLOGS_FIGHT_INTEGRITY_ENABLED"), enabled)
    return IntegrityConfig(
        enabled=enabled,
        cutoff_ms=cutoff_ms,
        cutoff_iso=cutoff_iso,
        hp_ratio_threshold=threshold,
        suspected_hp_ratio_threshold=suspected_threshold,
        excluded_encounter_keys=excluded_keys,
        default_report_limit=max(1, report_limit or 25),
        historical_damage_baselines=historical_damage_baselines,
        known_enemy_capacity=known_enemy_capacity,
        basic_attack_distribution=basic_attack_distribution,
    )


def load_encounters() -> dict[str, dict[str, Any]]:
    raw = read_json(PROJECT_ROOT / "config" / "encounters.json", [])
    if not isinstance(raw, list):
        raise RuntimeError("config/encounters.json 必須是陣列。")

    encounters: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not isinstance(key, str) or not key:
            continue
        encounters[key] = dict(item)
    return encounters


def sort_time(report: dict[str, Any], fight: dict[str, Any]) -> int:
    return integrity.fight_recorded_at_ms(report, fight) or 0


def has_query_context(fight: dict[str, Any]) -> bool:
    return all(
        integrity.to_number(fight.get(field)) is not None
        for field in ("fight_id", "start_time", "end_time", "encounter_id", "difficulty")
    ) and (integrity.to_number(fight.get("end_time")) or 0) > (integrity.to_number(fight.get("start_time")) or 0)


def needs_known_capacity_recheck(candidate: Candidate, config: IntegrityConfig) -> bool:
    """判斷既有 fight 是否缺少現行固定生命池或固定總傷害的證據。"""

    screen = config.known_enemy_capacity.screen(candidate.encounter_key, candidate.fight)
    if screen is None:
        return False
    result = integrity.current_result(candidate.fight)
    # 已有敵方生命池 1.15 倍高信心結論時不可被僅有「玩家傷害上限」的離線證據
    # 降級成 suspected。它本來已隱藏，且不需要額外重查或消耗 API 配額。
    if isinstance(result, dict) and result.get("status") == "excluded":
        return False
    metrics = result.get("metrics") if isinstance(result, dict) else None
    known_metrics = metrics.get("known_full_party_damage") if isinstance(metrics, dict) else None
    if screen.has_required_full_party_damage_range:
        if screen.needs_enemy_damage_for_low_full_party_total:
            return not (
                isinstance(known_metrics, dict)
                and known_metrics.get("damage_source") == "enemy_damage"
                and known_metrics.get("required_enemy_damage_min")
                == screen.required_enemy_damage_min
                and known_metrics.get("required_enemy_damage_max")
                == screen.required_enemy_damage_max
            )
        return not (
            isinstance(known_metrics, dict)
            and known_metrics.get("required_full_party_damage_min")
            == screen.required_full_party_damage_min
            and known_metrics.get("required_full_party_damage_max")
            == screen.required_full_party_damage_max
        )
    if screen.exceeds_maximum_full_party_damage:
        return not (
            isinstance(known_metrics, dict)
            and known_metrics.get("maximum_full_party_damage")
            == screen.maximum_full_party_damage
            and known_metrics.get("exceeds_maximum_full_party_damage") is True
        )
    return screen.exceeds_suspected_threshold and not isinstance(known_metrics, dict)


def candidate_needs_check(candidate: Candidate, config: IntegrityConfig) -> bool:
    """只重判現行規則需要的新證據；其他已通過舊版結果繼續公開。"""

    result = integrity.current_result(candidate.fight)
    target_profile = config.known_enemy_capacity.target_damage_profile(
        candidate.encounter_key
    )
    if target_profile is not None:
        metrics = result.get("metrics") if isinstance(result, dict) else None
        target_metrics = (
            metrics.get("target_damage_profile") if isinstance(metrics, dict) else None
        )
        if (
            integrity.to_int((result or {}).get("calculation_version"))
            != integrity.CALCULATION_VERSION
            or not isinstance(target_metrics, dict)
            or target_metrics.get("profile_version") != target_profile.version
        ):
            # v11 的逐目標證據只適用設定了固定 profile 的副本。這個明示分支讓
            # M5S～M8S 的 v10 正常與異常結果全部重判，同時讓其他 v8～v10 已驗證
            # 結果維持公開，不會因全域版號升級整批下架。
            return True
    if (
        config.basic_attack_distribution.applies(candidate.encounter_key, candidate.fight)
        and integrity.to_int((result or {}).get("calculation_version"))
        != integrity.CALCULATION_VERSION
    ):
        # 事件分布只適用 M5S～M8S；逐目標 profile 未啟用時仍以此分支補齊新版證據。
        return True
    if integrity.is_legacy_public_compatible_result(result):
        return False
    return integrity.needs_check(candidate.fight) or needs_known_capacity_recheck(candidate, config)


def find_candidates(
    encounters: dict[str, dict[str, Any]],
    config: IntegrityConfig,
    *,
    force: bool,
    encounter_keys: set[str] | None = None,
    recorded_at_or_after_ms: int | None = None,
) -> tuple[list[Candidate], dict[str, dict[str, Any]], int]:
    candidates: list[Candidate] = []
    rankings: dict[str, dict[str, Any]] = {}
    scoped_fights = 0

    for encounter_key, encounter in sorted(encounters.items()):
        if encounter_keys and encounter_key not in encounter_keys:
            continue
        if not ranking_path(encounter).exists():
            continue
        ranking = load_ranking_file(encounter)
        rankings[encounter_key] = ranking
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for fallback_code, report in reports.items():
            if not isinstance(report, dict):
                continue
            # 一般定期回補不必再次讀取已隱藏 report，避免對已不可讀來源浪費 API
            # 額度；但 --force 代表人工全量稽核，仍允許明確要求重判所有切點後資料。
            if report_is_hidden(report) and not force:
                continue
            report_code = str(report.get("report_code") or fallback_code)
            for fight in report.get("fights") or []:
                if not isinstance(fight, dict) or not integrity.is_in_scope(report, fight, config.cutoff_ms):
                    continue
                # 人工全量稽核通常只針對特定版本或副本開放後的紀錄。使用 fight 的
                # recorded_at（缺值時由 fight_integrity 依 report 時間回退）篩選，
                # 避免把同一 report 內較早的戰鬥或其他版本資料一起重判。
                recorded_at_ms = integrity.fight_recorded_at_ms(report, fight)
                if (
                    recorded_at_or_after_ms is not None
                    and (recorded_at_ms is None or recorded_at_ms < recorded_at_or_after_ms)
                ):
                    continue
                scoped_fights += 1
                candidate = Candidate(
                    encounter_key=encounter_key,
                    encounter=encounter,
                    ranking=ranking,
                    report_code=report_code,
                    report=report,
                    fight=fight,
                    sort_time=sort_time(report, fight),
                )
                if not force and not candidate_needs_check(candidate, config):
                    continue
                candidates.append(candidate)

    candidates.sort(key=lambda item: (item.sort_time, item.report_code), reverse=True)
    return candidates, rankings, scoped_fights


def select_candidates(candidates: list[Candidate], report_limit: int) -> list[Candidate]:
    selected_codes: set[str] = set()
    for candidate in candidates:
        selected_codes.add(candidate.report_code)
        if len(selected_codes) >= report_limit:
            break
    return [candidate for candidate in candidates if candidate.report_code in selected_codes]


def seed_measurement_cache_from_results(
    candidates: list[Candidate],
    measurement_cache: integrity_cache.FightIntegrityMeasurementCache,
) -> int:
    """將既有檢核結果中的彙總測量值補入新快取，不重新讀取 FFLogs。"""

    seeded = 0
    for candidate in candidates:
        # 舊版結果的敵方承傷／生命池仍是可重用的最小量測資料。先植入快取再以
        # 現行規則離線重判，避免規則升版使全量回補重新耗用 FFLogs API。
        result = integrity.current_result(candidate.fight)
        if result is None:
            continue
        if measurement_cache.get(candidate.report_code, candidate.report, candidate.fight) is not None:
            continue
        metrics = result.get("metrics") if isinstance(result, dict) else None
        checked_at_iso = str(result.get("checked_at_iso") or "") if isinstance(result, dict) else ""
        try:
            if isinstance(metrics, dict) and all(
                key in metrics for key in ("enemy_damage", "enemy_hp_capacity", "target_count")
            ):
                measurement = {
                    "enemy_damage": metrics["enemy_damage"],
                    "enemy_hp_capacity": metrics["enemy_hp_capacity"],
                    "target_count": metrics["target_count"],
                }
                target_metrics = metrics.get("target_damage_profile")
                target_results = (
                    target_metrics.get("target_results")
                    if isinstance(target_metrics, dict)
                    else None
                )
                if isinstance(target_results, list):
                    target_measurements = [
                        {
                            "guid": target.get("guid"),
                            "damage": target.get("observed_damage"),
                            "max_hp": target.get("observed_max_hp"),
                            "instance_count": target.get("observed_instance_count"),
                        }
                        for target in target_results
                        if isinstance(target, dict)
                        and target.get("observed_damage") is not None
                        and target.get("observed_max_hp") is not None
                    ]
                    if len(target_measurements) == integrity.to_int(metrics.get("target_count")):
                        measurement["targets"] = target_measurements
                measurement_cache.put(
                    candidate.report_code,
                    candidate.report,
                    candidate.fight,
                    measurement=measurement,
                    cached_at_iso=checked_at_iso,
                    persist=False,
                )
            else:
                status = result.get("status") if isinstance(result, dict) else None
                if status not in {"unverifiable", "suspected"}:
                    continue
                reasons = result.get("reasons") if isinstance(result, dict) else None
                reason = reasons[0] if isinstance(reasons, list) and reasons and isinstance(reasons[0], str) else ""
                # suspected 可能只是固定範圍或歷史預篩的規則結論，不代表 FFLogs
                # 真的無法量測。只有底層查詢可重現的失敗原因能進快取，避免舊規則
                # 的 false positive 永久擋住新版 Target Damage 重查。
                if reason not in integrity_cache.CACHEABLE_UNVERIFIABLE_REASONS:
                    continue
                measurement_cache.put_unverifiable(
                    candidate.report_code,
                    candidate.report,
                    candidate.fight,
                    reason=reason,
                    cached_at_iso=checked_at_iso,
                    persist=False,
                )
        except ValueError:
            continue
        seeded += 1

    if seeded:
        measurement_cache.save()
    return seeded


def query_target_damage(
    session: Any,
    auth_pool: Any,
    candidate: Candidate,
) -> tuple[list[dict[str, Any]], dict[int, int]]:
    fight = candidate.fight
    variables = {
        "code": candidate.report_code,
        "fightID": integrity.to_int(fight.get("fight_id")),
        "startTime": integrity.to_number(fight.get("start_time")),
        "endTime": integrity.to_number(fight.get("end_time")),
        "encounterID": integrity.to_int(fight.get("encounter_id")),
        "difficulty": integrity.to_int(fight.get("difficulty")),
    }
    payload = execute_graphql(session, auth_pool, 戰鬥完整性目標傷害查詢, variables)
    report = ((payload.get("reportData") or {}).get("report")) or {}
    table = report.get("targetDamage") if isinstance(report, dict) else {}
    table_data = table.get("data") if isinstance(table, dict) else {}
    entries = table_data.get("entries") if isinstance(table_data, dict) else []

    fights = report.get("fights") if isinstance(report, dict) else []
    enemy_npcs = fights[0].get("enemyNPCs") if isinstance(fights, list) and fights else []
    instance_counts: dict[int, int] = {}
    for npc in enemy_npcs if isinstance(enemy_npcs, list) else []:
        if not isinstance(npc, dict):
            continue
        actor_id = integrity.to_int(npc.get("id"))
        if actor_id is None:
            continue
        count = integrity.to_int(npc.get("instanceCount")) or 1
        instance_counts[actor_id] = max(1, count)

    targets: list[dict[str, Any]] = []
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue
        actor_id = integrity.to_int(entry.get("id"))
        total = integrity.to_number(entry.get("total"))
        if actor_id is None or total is None or total <= 0:
            continue
        targets.append(
            {
                "id": actor_id,
                "guid": integrity.to_int(entry.get("guid")),
                "damage": total,
                "instance_count": instance_counts.get(actor_id, 1),
            }
        )
    return targets, instance_counts


def query_target_max_hp(session: Any, auth_pool: Any, candidate: Candidate, target_ids: list[int]) -> dict[int, float]:
    if not target_ids:
        return {}
    fight = candidate.fight
    payload = execute_graphql(
        session,
        auth_pool,
        建立戰鬥完整性目標生命值查詢(target_ids),
        {
            "code": candidate.report_code,
            "fightID": integrity.to_int(fight.get("fight_id")),
            "startTime": integrity.to_number(fight.get("start_time")),
            "endTime": integrity.to_number(fight.get("end_time")),
        },
    )
    report = ((payload.get("reportData") or {}).get("report")) or {}
    max_hp_by_target: dict[int, float] = {}
    for index, target_id in enumerate(target_ids):
        events = report.get(f"target_{index}") if isinstance(report, dict) else {}
        event_data = events.get("data") if isinstance(events, dict) else []
        max_hp = max(
            (
                integrity.to_number((event.get("targetResources") or {}).get("maxHitPoints")) or 0
                for event in event_data if isinstance(event, dict)
            ),
            default=0,
        )
        if max_hp > 0:
            max_hp_by_target[target_id] = max_hp
    return max_hp_by_target


def evaluate_measurement(
    candidate: Candidate,
    config: IntegrityConfig,
    checked_at_iso: str,
    *,
    measurement: dict[str, Any],
    historical_screen: historical_baselines.HistoricalDamageScreen | None,
    known_capacity_screen: known_capacity.KnownEnemyCapacityScreen | None,
    basic_attack_screen: integrity.BasicAttackDistributionScreen | None = None,
) -> dict[str, Any]:
    """以已快取或剛查得的最小測量資料重新套用完整性規則。"""

    attack_marker = integrity.has_basic_attack_exploit_marker(candidate.fight)
    # 部分 report 的繁中服玩家來源列少於實際隊伍人數時，玩家傷害總和不是全隊
    # 總量，不能套用固定範圍。若副本明確設定敵方承傷範圍，改用已保存／查得的
    # FFLogs 敵方承傷作為權威值；它能攔下極澤蓮尼亞 93.63m 類漏網資料。
    enemy_damage_screen = config.known_enemy_capacity.screen_enemy_damage(
        candidate.encounter_key,
        measurement["enemy_damage"],
    )
    effective_known_capacity_screen = enemy_damage_screen or known_capacity_screen
    target_damage_profile_screen = (
        config.known_enemy_capacity.screen_target_damage_profile(
            candidate.encounter_key,
            measurement,
        )
    )
    return integrity.evaluate(
        checked_at_iso=checked_at_iso,
        enemy_damage=measurement["enemy_damage"],
        enemy_hp_capacity=measurement["enemy_hp_capacity"],
        target_count=measurement["target_count"],
        attack_marker=attack_marker,
        hp_ratio_threshold=config.hp_ratio_threshold,
        suspected_hp_ratio_threshold=config.suspected_hp_ratio_threshold,
        historical_screen=historical_screen,
        known_capacity_screen=effective_known_capacity_screen,
        basic_attack_screen=basic_attack_screen,
        target_damage_profile_screen=target_damage_profile_screen,
    )


def evaluate_candidate(
    session: Any,
    auth_pool: Any,
    candidate: Candidate,
    config: IntegrityConfig,
    checked_at_iso: str,
    measurement_cache: integrity_cache.FightIntegrityMeasurementCache,
    *,
    refresh_cache: bool,
    offline_only: bool = False,
) -> tuple[dict[str, Any], bool, bool]:
    """優先以本機測量快取判定；只有未命中或要求刷新時才呼叫 FFLogs。"""

    attack_marker = integrity.has_basic_attack_exploit_marker(candidate.fight)
    historical_screen = config.historical_damage_baselines.screen(
        candidate.encounter_key,
        candidate.fight,
    )
    known_capacity_screen = config.known_enemy_capacity.screen(
        candidate.encounter_key,
        candidate.fight,
    )
    requires_enemy_damage_measurement = config.known_enemy_capacity.requires_enemy_damage_measurement(
        candidate.encounter_key,
    )
    requires_target_details = (
        config.known_enemy_capacity.requires_target_damage_profile_measurement(
            candidate.encounter_key
        )
    )
    basic_attack_screen: integrity.BasicAttackDistributionScreen | None = None
    basic_cache_hit = False
    basic_api_queried = False

    if config.basic_attack_distribution.applies(candidate.encounter_key, candidate.fight):
        basic_measurement = None if refresh_cache else measurement_cache.get_basic_attack(
            candidate.report_code,
            candidate.report,
            candidate.fight,
        )
        basic_cache_hit = basic_measurement is not None
        if basic_measurement is None:
            if offline_only:
                return integrity.make_unverifiable_result(
                    checked_at_iso=checked_at_iso,
                    reason="offline_basic_attack_measurement_not_available",
                    attack_marker=attack_marker,
                    historical_screen=historical_screen,
                    known_capacity_screen=known_capacity_screen,
                ), False, False
            if not has_query_context(candidate.fight):
                return integrity.make_unverifiable_result(
                    checked_at_iso=checked_at_iso,
                    reason="missing_basic_attack_query_context",
                    attack_marker=attack_marker,
                    historical_screen=historical_screen,
                    known_capacity_screen=known_capacity_screen,
                ), False, False
            events = query_basic_attack_events(
                session,
                auth_pool,
                candidate.report_code,
                candidate.fight,
            )
            basic_api_queried = True
            basic_measurement = integrity.summarize_basic_attack_events(
                events,
                candidate.fight.get("players")
                if isinstance(candidate.fight.get("players"), list)
                else [],
            )
            measurement_cache.put_basic_attack(
                candidate.report_code,
                candidate.report,
                candidate.fight,
                measurement=basic_measurement,
                cached_at_iso=checked_at_iso,
            )
        basic_attack_screen = config.basic_attack_distribution.screen(basic_measurement)
        if basic_attack_screen.is_abnormal and not requires_target_details:
            return integrity.make_basic_attack_distribution_result(
                checked_at_iso=checked_at_iso,
                screen=basic_attack_screen,
            ), basic_cache_hit, basic_api_queried

    def finish(
        result: dict[str, Any],
        *,
        cache_hit: bool = False,
        api_queried: bool = False,
    ) -> tuple[dict[str, Any], bool, bool]:
        return (
            integrity.apply_basic_attack_distribution_screen(result, basic_attack_screen),
            basic_cache_hit or cache_hit,
            basic_api_queried or api_queried,
        )

    # 固定完整隊伍傷害落在範圍內或已高於上限時，優先於任何舊快取離線判定。
    # 低於下限時玩家合計仍可能只是漏掉 Limit Break；若有 Target Damage 固定範圍，
    # 必須繼續讀取快取或 FFLogs 精準量測，不能用傷害下限直接隱藏正常紀錄。
    if (
        known_capacity_screen is not None
        and (
            (
                known_capacity_screen.has_required_full_party_damage_range
                and not known_capacity_screen.needs_enemy_damage_for_low_full_party_total
            )
            or known_capacity_screen.exceeds_maximum_full_party_damage
        )
    ):
        return finish(integrity.make_known_capacity_result(
            checked_at_iso=checked_at_iso,
            known_capacity_screen=known_capacity_screen,
            hp_ratio_threshold=config.hp_ratio_threshold,
            attack_marker=attack_marker,
        ))

    # 絕巴哈姆特等多階段副本不能以查得的單一目標生命池判定正常；不過在完整隊伍
    # 傷害已越過獨立確認的歷史硬上限時，該上限仍是足以直接隱藏的異常證據。
    if candidate.encounter_key in config.excluded_encounter_keys:
        return finish(integrity.make_not_applicable_result(
            checked_at_iso=checked_at_iso,
            reason="encounter_hp_pool_semantics_not_supported",
        ))

    cached = None if refresh_cache else measurement_cache.get(
        candidate.report_code,
        candidate.report,
        candidate.fight,
        require_target_details=requires_target_details,
    )
    if cached is not None:
        if cached["outcome"] == "unverifiable":
            return finish(integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason=cached["reason"],
                attack_marker=attack_marker,
                historical_screen=historical_screen,
                known_capacity_screen=known_capacity_screen,
            ), cache_hit=True)
        return finish(evaluate_measurement(
            candidate,
            config,
            checked_at_iso,
            measurement=cached["measurement"],
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
            basic_attack_screen=basic_attack_screen,
        ), cache_hit=True)

    # 已知固定生命池只會用完整隊伍傷害下限認定異常，不能反過來判定正常。這讓極澤蓮尼亞
    # 的誇張 log 可離線先隱藏，同時避免 Limit Break 未歸屬玩家時造成 false valid。
    if known_capacity_screen is not None and known_capacity_screen.exceeds_suspected_threshold:
        return finish(integrity.make_known_capacity_result(
            checked_at_iso=checked_at_iso,
            known_capacity_screen=known_capacity_screen,
            hp_ratio_threshold=config.hp_ratio_threshold,
            attack_marker=attack_marker,
        ))

    # 歷史基準也只會把完整隊伍的極端高傷害標為疑似並隱藏，永不直接寫成 excluded。
    # 這可在一次性離線回補時先阻斷明顯污染，而有量測快取時仍以目標生命池為最終判定。
    if offline_only and historical_screen is not None and historical_screen.exceeds_threshold:
        return finish(integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="historical_team_damage_requires_enemy_hp_measurement",
            attack_marker=attack_marker,
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        ))

    # 完整繁中隊伍且仍在歷史高端範圍內、又沒有敵方承傷專用規則的舊副本，不必
    # 為正常新紀錄重複查敵方 HP。已設定敵方承傷上限者仍必須量測，否則玩家列未
    # 歸屬的 Limit Break 等來源會使角色總傷害看似正常卻漏過真正的總傷害異常。
    if (
        historical_screen is not None
        and not historical_screen.exceeds_threshold
        and not attack_marker
        and not requires_enemy_damage_measurement
    ):
        return finish(integrity.make_historical_screen_valid_result(
            checked_at_iso=checked_at_iso,
            historical_screen=historical_screen,
        ))

    if offline_only:
        return finish(integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="offline_measurement_not_available",
            attack_marker=attack_marker,
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        ))

    if not has_query_context(candidate.fight):
        return finish(integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="missing_fight_query_context",
            attack_marker=attack_marker,
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        ))

    targets, _ = query_target_damage(session, auth_pool, candidate)
    target_ids = [target["id"] for target in targets]
    target_hp = query_target_max_hp(session, auth_pool, candidate, target_ids)
    if not targets or len(target_hp) != len(target_ids):
        measurement_cache.put_unverifiable(
            candidate.report_code,
            candidate.report,
            candidate.fight,
            reason="missing_enemy_max_hp",
            cached_at_iso=checked_at_iso,
        )
        return finish(integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="missing_enemy_max_hp",
            attack_marker=attack_marker,
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        ), api_queried=True)

    if requires_target_details and any(target.get("guid") is None for target in targets):
        measurement_cache.put_unverifiable(
            candidate.report_code,
            candidate.report,
            candidate.fight,
            reason="missing_enemy_target_guid",
            cached_at_iso=checked_at_iso,
        )
        return finish(integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="missing_enemy_target_guid",
            attack_marker=attack_marker,
            historical_screen=historical_screen,
            known_capacity_screen=known_capacity_screen,
        ), api_queried=True)

    measurement = {
        "enemy_damage": sum(target["damage"] for target in targets),
        "enemy_hp_capacity": sum(target_hp[target["id"]] * target["instance_count"] for target in targets),
        "target_count": len(targets),
    }
    if all(target.get("guid") is not None for target in targets):
        measurement["targets"] = [
            {
                "guid": target["guid"],
                "damage": target["damage"],
                "max_hp": target_hp[target["id"]],
                "instance_count": target["instance_count"],
            }
            for target in targets
        ]
    # 落地的是彙總值與逐目標 NPC GUID／承傷／生命值／實例數，不保存 report 內
    # actor ID、完整 Target table 或 raw events；FFLogs 修正 report 時來源指紋會失效。
    measurement_cache.put(
        candidate.report_code,
        candidate.report,
        candidate.fight,
        measurement=measurement,
        cached_at_iso=checked_at_iso,
    )
    return finish(evaluate_measurement(
        candidate,
        config,
        checked_at_iso,
        measurement=measurement,
        historical_screen=historical_screen,
        known_capacity_screen=known_capacity_screen,
        basic_attack_screen=basic_attack_screen,
    ), api_queried=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="分批回補 FFLogs 戰鬥完整性檢核。")
    parser.add_argument("--report-limit", type=int, default=None, help="本輪最多處理的 report 數。")
    parser.add_argument("--dry-run", action="store_true", help="只列出候選，不呼叫 API、不寫入資料。")
    parser.add_argument(
        "--force",
        action="store_true",
        help="重新判定已有目前版本結果的 fight；仍優先使用有效測量快取。",
    )
    parser.add_argument(
        "--cache-path",
        type=Path,
        default=DEFAULT_CACHE_PATH,
        help="不進 Git 的完整性測量快取路徑。",
    )
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="忽略有效快取並重新向 FFLogs 讀取本輪測量資料。",
    )
    parser.add_argument(
        "--offline-only",
        action="store_true",
        help="只使用已保存結果、本機快取與本地預篩；缺少量測時保守隱藏，完全不呼叫 FFLogs。",
    )
    parser.add_argument(
        "--report-code",
        action="append",
        default=[],
        help="只處理指定 report code；可重複提供，且不受 report-limit 截斷。",
    )
    parser.add_argument(
        "--encounter-key",
        action="append",
        default=[],
        help="只處理指定副本 key；可重複提供。",
    )
    parser.add_argument(
        "--recorded-at-or-after",
        default=None,
        help="只處理此 ISO 時間（含）之後記錄的 fight；時間必須包含時區。",
    )
    args = parser.parse_args()

    config = load_config()
    if not config.enabled:
        print("fight_integrity_check.enabled=false，保留既有標記並略過本輪新增檢核。")
        return 0

    report_limit = max(0, args.report_limit if args.report_limit is not None else config.default_report_limit)
    if report_limit == 0:
        print("report limit 為 0，略過本輪戰鬥完整性檢核。")
        return 0

    encounters = load_encounters()
    requested_encounter_keys = {
        str(value).strip() for value in args.encounter_key if str(value).strip()
    }
    unknown_encounter_keys = requested_encounter_keys - set(encounters)
    if unknown_encounter_keys:
        parser.error("找不到副本 key：" + "、".join(sorted(unknown_encounter_keys)))

    recorded_at_or_after_ms: int | None = None
    if args.recorded_at_or_after:
        recorded_at_or_after_ms = integrity.parse_iso_to_epoch_ms(str(args.recorded_at_or_after))
        if recorded_at_or_after_ms is None:
            parser.error("--recorded-at-or-after 必須是含時區的有效 ISO 時間。")

    scoped_candidates, _, scoped_fights = find_candidates(
        encounters,
        config,
        force=args.force,
        encounter_keys=requested_encounter_keys or None,
        recorded_at_or_after_ms=recorded_at_or_after_ms,
    )
    candidates = scoped_candidates if args.force else [
        candidate for candidate in scoped_candidates if candidate_needs_check(candidate, config)
    ]
    requested_report_codes = {
        str(value).strip() for value in args.report_code if str(value).strip()
    }
    if requested_report_codes:
        selected = [
            candidate
            for candidate in candidates
            if candidate.report_code in requested_report_codes
        ]
    else:
        selected = select_candidates(candidates, report_limit)
    selection_label = "指定 report" if requested_report_codes else f"report 上限={report_limit}"
    print(
        "戰鬥完整性檢核候選："
        f"切點={config.cutoff_iso}、範圍內 fight={scoped_fights}、"
        f"待檢查={len(candidates)}、本輪={len(selected)}、{selection_label}"
    )
    for candidate in selected[:20]:
        print(f"- {candidate.label}")
    if len(selected) > 20:
        print(f"... 另有 {len(selected) - 20} 場本輪候選。")
    if args.dry_run:
        return 0

    measurement_cache = integrity_cache.FightIntegrityMeasurementCache.load(args.cache_path)
    seeded_count = seed_measurement_cache_from_results(scoped_candidates, measurement_cache)
    cache_mode = "強制刷新" if args.refresh_cache else "優先讀取"
    seeded_label = f"、由既有結果補入 {seeded_count} 筆" if seeded_count else ""
    print(f"完整性測量快取：{args.cache_path}（目前 {len(measurement_cache)} 筆，{cache_mode}{seeded_label}）")
    if not selected:
        return 0

    session: Any | None = None
    auth_pool: Any | None = None
    if args.offline_only:
        print("已啟用離線完整性回補：不建立 OAuth、不呼叫 FFLogs，未量測 fight 將保守隱藏。")
    else:
        session = fflogs.requests.Session()
        auth_pool = auth_pool_class(session, read_credentials())
    changed_encounters: set[str] = set()
    counters = {"excluded": 0, "suspected": 0, "valid": 0, "unverifiable": 0, "not_applicable": 0, "failed": 0}
    cache_hits = 0
    api_measurements = 0
    checked_at_iso = milliseconds_to_iso(time.time() * 1000) or ""

    for index, candidate in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] 檢核 {candidate.label}")
        historical_screen = config.historical_damage_baselines.screen(
            candidate.encounter_key,
            candidate.fight,
        )
        known_capacity_screen = config.known_enemy_capacity.screen(
            candidate.encounter_key,
            candidate.fight,
        )
        try:
            result, cache_hit, api_queried = evaluate_candidate(
                session,
                auth_pool,
                candidate,
                config,
                checked_at_iso,
                measurement_cache,
                refresh_cache=args.refresh_cache,
                offline_only=args.offline_only,
            )
            if cache_hit:
                cache_hits += 1
            if api_queried:
                api_measurements += 1
        except report_access_error_class:
            mark_ranking_report_hidden(
                candidate.ranking,
                candidate.report_code,
                原因=hidden_reason_inaccessible,
                來源="backfill_fight_integrity",
                詳細原因="戰鬥完整性檢核時 FFLogs 回報 report 無法存取",
            )
            result = integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason="report_not_accessible",
                attack_marker=integrity.has_basic_attack_exploit_marker(candidate.fight),
                historical_screen=historical_screen,
                known_capacity_screen=known_capacity_screen,
            )
        except graphql_error_class as error:
            print(f"  → FFLogs 查詢失敗，保留不可驗證狀態：{error}", file=sys.stderr)
            result = integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason="fflogs_graphql_query_failed",
                attack_marker=integrity.has_basic_attack_exploit_marker(candidate.fight),
                historical_screen=historical_screen,
                known_capacity_screen=known_capacity_screen,
            )
            counters["failed"] += 1
        except (RuntimeError, ValueError, TypeError) as error:
            print(f"  → 檢核失敗，保留不可驗證狀態：{error}", file=sys.stderr)
            result = integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason="integrity_measurement_failed",
                attack_marker=integrity.has_basic_attack_exploit_marker(candidate.fight),
                historical_screen=historical_screen,
                known_capacity_screen=known_capacity_screen,
            )
            counters["failed"] += 1

        candidate.fight[integrity.DATA_INTEGRITY_KEY] = result
        status = str(result.get("status") or "unverifiable")
        counters[status] = counters.get(status, 0) + 1
        changed_encounters.add(candidate.encounter_key)
        ratio = ((result.get("metrics") or {}).get("damage_to_hp_ratio"))
        print(f"  → {status}，倍率={ratio if ratio is not None else '無法取得'}")

    for encounter_key in sorted(changed_encounters):
        candidate = next(item for item in selected if item.encounter_key == encounter_key)
        write_ranking_file(candidate.encounter, candidate.ranking)

    print(
        "戰鬥完整性檢核完成："
        + "、".join(f"{key}={value}" for key, value in counters.items())
        + f"、快取命中={cache_hits}、FFLogs 測量={api_measurements}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
