"""分批回補 2026-07-28 後 FFLogs 戰鬥的普攻資料完整性檢核。"""

from __future__ import annotations

import argparse
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402
import fight_integrity as integrity  # noqa: E402
import fight_integrity_cache as integrity_cache  # noqa: E402
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


def find_candidates(
    encounters: dict[str, dict[str, Any]],
    config: IntegrityConfig,
    *,
    force: bool,
) -> tuple[list[Candidate], dict[str, dict[str, Any]], int]:
    candidates: list[Candidate] = []
    rankings: dict[str, dict[str, Any]] = {}
    scoped_fights = 0

    for encounter_key, encounter in sorted(encounters.items()):
        if not ranking_path(encounter).exists():
            continue
        ranking = load_ranking_file(encounter)
        rankings[encounter_key] = ranking
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for fallback_code, report in reports.items():
            if not isinstance(report, dict) or report_is_hidden(report):
                continue
            report_code = str(report.get("report_code") or fallback_code)
            for fight in report.get("fights") or []:
                if not isinstance(fight, dict) or not integrity.is_in_scope(report, fight, config.cutoff_ms):
                    continue
                scoped_fights += 1
                if not force and not integrity.needs_check(fight):
                    continue
                candidates.append(
                    Candidate(
                        encounter_key=encounter_key,
                        encounter=encounter,
                        ranking=ranking,
                        report_code=report_code,
                        report=report,
                        fight=fight,
                        sort_time=sort_time(report, fight),
                    )
                )

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
        if integrity.needs_check(candidate.fight):
            continue
        if measurement_cache.get(candidate.report_code, candidate.report, candidate.fight) is not None:
            continue
        result = integrity.current_result(candidate.fight)
        metrics = result.get("metrics") if isinstance(result, dict) else None
        checked_at_iso = str(result.get("checked_at_iso") or "") if isinstance(result, dict) else ""
        try:
            if isinstance(metrics, dict):
                measurement_cache.put(
                    candidate.report_code,
                    candidate.report,
                    candidate.fight,
                    measurement=metrics,
                    cached_at_iso=checked_at_iso,
                    persist=False,
                )
            else:
                status = result.get("status") if isinstance(result, dict) else None
                if status not in {"unverifiable", "suspected"}:
                    continue
                reasons = result.get("reasons") if isinstance(result, dict) else None
                reason = reasons[0] if isinstance(reasons, list) and reasons and isinstance(reasons[0], str) else ""
                if not reason:
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
    measurement: dict[str, float | int],
) -> dict[str, Any]:
    """以已快取或剛查得的最小測量資料重新套用完整性規則。"""

    attack_marker = integrity.has_basic_attack_exploit_marker(candidate.fight)
    return integrity.evaluate(
        checked_at_iso=checked_at_iso,
        enemy_damage=measurement["enemy_damage"],
        enemy_hp_capacity=measurement["enemy_hp_capacity"],
        target_count=measurement["target_count"],
        attack_marker=attack_marker,
        hp_ratio_threshold=config.hp_ratio_threshold,
        suspected_hp_ratio_threshold=config.suspected_hp_ratio_threshold,
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
) -> tuple[dict[str, Any], bool]:
    """優先以本機測量快取判定；只有未命中或要求刷新時才呼叫 FFLogs。"""

    attack_marker = integrity.has_basic_attack_exploit_marker(candidate.fight)
    if candidate.encounter_key in config.excluded_encounter_keys:
        return integrity.make_not_applicable_result(
            checked_at_iso=checked_at_iso,
            reason="encounter_hp_pool_semantics_not_supported",
        ), False
    if not has_query_context(candidate.fight):
        return integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="missing_fight_query_context",
            attack_marker=attack_marker,
        ), False

    cached = None if refresh_cache else measurement_cache.get(
        candidate.report_code,
        candidate.report,
        candidate.fight,
    )
    if cached is not None:
        if cached["outcome"] == "unverifiable":
            return integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason=cached["reason"],
                attack_marker=attack_marker,
            ), True
        return evaluate_measurement(
            candidate,
            config,
            checked_at_iso,
            measurement=cached["measurement"],
        ), True

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
        return integrity.make_unverifiable_result(
            checked_at_iso=checked_at_iso,
            reason="missing_enemy_max_hp",
            attack_marker=attack_marker,
        ), False

    measurement = {
        "enemy_damage": sum(target["damage"] for target in targets),
        "enemy_hp_capacity": sum(target_hp[target["id"]] * target["instance_count"] for target in targets),
        "target_count": len(targets),
    }
    # 落地的是最小彙總值，不保存依目標表格或 raw events；若 FFLogs 之後修正
    # 同一 report，來源指紋變更時快取自然會失效。
    measurement_cache.put(
        candidate.report_code,
        candidate.report,
        candidate.fight,
        measurement=measurement,
        cached_at_iso=checked_at_iso,
    )
    return evaluate_measurement(
        candidate,
        config,
        checked_at_iso,
        measurement=measurement,
    ), False


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
    args = parser.parse_args()

    config = load_config()
    if not config.enabled:
        print("fight_integrity_check.enabled=false，保留既有標記並略過本輪新增檢核。")
        return 0

    report_limit = max(0, args.report_limit if args.report_limit is not None else config.default_report_limit)
    if report_limit == 0:
        print("report limit 為 0，略過本輪戰鬥完整性檢核。")
        return 0

    scoped_candidates, _, scoped_fights = find_candidates(load_encounters(), config, force=True)
    candidates = scoped_candidates if args.force else [
        candidate for candidate in scoped_candidates if integrity.needs_check(candidate.fight)
    ]
    selected = select_candidates(candidates, report_limit)
    print(
        "戰鬥完整性檢核候選："
        f"切點={config.cutoff_iso}、範圍內 fight={scoped_fights}、"
        f"待檢查={len(candidates)}、本輪={len(selected)}、report 上限={report_limit}"
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

    session = fflogs.requests.Session()
    auth_pool = auth_pool_class(session, read_credentials())
    changed_encounters: set[str] = set()
    counters = {"excluded": 0, "suspected": 0, "valid": 0, "unverifiable": 0, "not_applicable": 0, "failed": 0}
    cache_hits = 0
    api_measurements = 0
    checked_at_iso = milliseconds_to_iso(time.time() * 1000) or ""

    for index, candidate in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] 檢核 {candidate.label}")
        try:
            result, cache_hit = evaluate_candidate(
                session,
                auth_pool,
                candidate,
                config,
                checked_at_iso,
                measurement_cache,
                refresh_cache=args.refresh_cache,
            )
            if cache_hit:
                cache_hits += 1
            elif candidate.encounter_key not in config.excluded_encounter_keys and has_query_context(candidate.fight):
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
            )
        except graphql_error_class as error:
            print(f"  → FFLogs 查詢失敗，保留不可驗證狀態：{error}", file=sys.stderr)
            result = integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason="fflogs_graphql_query_failed",
                attack_marker=integrity.has_basic_attack_exploit_marker(candidate.fight),
            )
            counters["failed"] += 1
        except (RuntimeError, ValueError, TypeError) as error:
            print(f"  → 檢核失敗，保留不可驗證狀態：{error}", file=sys.stderr)
            result = integrity.make_unverifiable_result(
                checked_at_iso=checked_at_iso,
                reason="integrity_measurement_failed",
                attack_marker=integrity.has_basic_attack_exploit_marker(candidate.fight),
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
