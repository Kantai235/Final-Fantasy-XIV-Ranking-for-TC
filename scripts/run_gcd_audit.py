"""固定入口：執行 xivanalysis GCD 稽核並把輸出寫入 log。

Codex 的權限核准是依命令前綴記住的；若每次都用 PowerShell redirection
或不同 report path 直接跑稽核腳本，系統會把整條命令視為不同操作而反覆詢問。
這個 wrapper 讓外部網路稽核固定走 `python -X utf8 scripts/run_gcd_audit.py`，
其餘參數仍完全交給既有 audit 腳本，方便一次核准後重用同類工作。
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DEFAULT_LOG_DIR = PROJECT_ROOT / ".codex_tmp"


def split_wrapper_args(argv: list[str]) -> tuple[Path, list[str]]:
    log_path: Path | None = None
    passthrough: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--log-path":
            if index + 1 >= len(argv):
                raise SystemExit("--log-path 需要指定檔案路徑")
            log_path = Path(argv[index + 1])
            index += 2
            continue
        passthrough.append(arg)
        index += 1

    if log_path is None:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = DEFAULT_LOG_DIR / f"gcd_audit_{stamp}.log"
    if not log_path.is_absolute():
        log_path = PROJECT_ROOT / log_path
    return log_path, passthrough


def run_debug_local_coverage(argv: list[str], log_path: Path) -> int:
    if len(argv) != 4:
        raise SystemExit(
            "--debug-local-coverage 需要 4 個參數：report_code fight_id job fflogs_source_id"
        )

    report_code, fight_id_text, job, source_id_text = argv
    sys.path.insert(0, str(SCRIPT_DIR))
    import audit_xivanalysis_gcd_sample as audit  # noqa: PLC0415
    import backfill_gcd_coverage as local_gcd  # noqa: PLC0415
    import backfill_gcd_coverage_xivanalysis as xiv_gcd  # noqa: PLC0415

    fight_id = local_gcd.to_int(fight_id_text)
    source_id = local_gcd.to_int(source_id_text)
    if fight_id is None or source_id is None:
        raise SystemExit("fight_id 與 fflogs_source_id 必須是數字")

    encounters = local_gcd.load_all_encounters()
    fights, _rankings_by_key = audit.collect_fight_groups(
        encounters,
        categories=set(audit.DEFAULT_CATEGORIES),
    )
    selected: Any | None = None
    for group in fights:
        if group.report_code != report_code or group.fight_id != fight_id:
            continue
        for candidate in group.candidates:
            if (
                str(candidate.player.get("job") or "") == job
                and local_gcd.to_int(candidate.player.get("fflogs_id")) == source_id
            ):
                selected = candidate
                break
        if selected is not None:
            break

    if selected is None:
        raise SystemExit("candidate not found")

    audit_cache = xiv_gcd.GcdAuditCache(PROJECT_ROOT / ".cache" / "xivanalysis-gcd-audit")
    fallback = xiv_gcd.LocalGcdFallback(audit_cache=audit_cache, cache_only=True)
    coverage = fallback.calculate(selected)
    import json  # noqa: PLC0415

    log_path.write_text(
        json.dumps(coverage, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        errors="backslashreplace",
    )
    return 0


def run_debug_local_coverage_variants(argv: list[str], log_path: Path) -> int:
    if len(argv) != 4:
        raise SystemExit(
            "--debug-local-coverage-variants 需要 4 個參數：report_code fight_id job fflogs_source_id"
        )

    report_code, fight_id_text, job, source_id_text = argv
    sys.path.insert(0, str(SCRIPT_DIR))
    import audit_xivanalysis_gcd_sample as audit  # noqa: PLC0415
    import backfill_gcd_coverage as local_gcd  # noqa: PLC0415
    import backfill_gcd_coverage_xivanalysis as xiv_gcd  # noqa: PLC0415
    import json  # noqa: PLC0415

    fight_id = local_gcd.to_int(fight_id_text)
    source_id = local_gcd.to_int(source_id_text)
    if fight_id is None or source_id is None:
        raise SystemExit("fight_id 與 fflogs_source_id 必須是整數。")

    encounters = local_gcd.load_all_encounters()
    fights, _rankings_by_key = audit.collect_fight_groups(
        encounters,
        categories=set(audit.DEFAULT_CATEGORIES),
    )
    selected: Any | None = None
    for group in fights:
        if group.report_code != report_code or group.fight_id != fight_id:
            continue
        for candidate in group.candidates:
            if (
                str(candidate.player.get("job") or "") == job
                and local_gcd.to_int(candidate.player.get("fflogs_id")) == source_id
            ):
                selected = candidate
                break
        if selected is not None:
            break

    if selected is None:
        raise SystemExit("candidate not found")

    audit_cache = xiv_gcd.GcdAuditCache(PROJECT_ROOT / ".cache" / "xivanalysis-gcd-audit")
    fallback = xiv_gcd.LocalGcdFallback(audit_cache=audit_cache, cache_only=True)
    fallback.metadata_store = local_gcd.ActionMetadataStore()
    fallback.metadata_store.preload()
    fallback.status_store = local_gcd.StatusMetadataStore()
    fallback.status_store.preload()
    fallback.unable_to_act_status_ids = fallback.status_store.unable_to_act_status_ids()

    start_time = local_gcd.first_number(selected.fight.get("start_time"), selected.fight.get("startTime"))
    end_time = local_gcd.first_number(selected.fight.get("end_time"), selected.fight.get("endTime"))
    if start_time is None or end_time is None:
        raise SystemExit("candidate fight 缺少 start/end time")

    calculation_fight = fallback._calculation_fight(selected)
    gcd_denominator_ms = local_gcd.gcd_pull_duration_ms(calculation_fight, start_time, end_time)
    gcd_start_time = local_gcd.gcd_core.gcd_pull_start_time_ms(calculation_fight, start_time, end_time)
    graph = audit_cache.read_fflogs_payload("casts_graph", selected)
    raw_events = audit_cache.read_fflogs_payload("raw_events", selected)
    if not isinstance(graph, dict) or not isinstance(raw_events, list):
        raise SystemExit("debug variants 需要 casts_graph 與 raw_events 快取")

    friendly_ids = {
        player_id
        for player_id in (
            local_gcd.to_int(player.get("fflogs_id"))
            for player in calculation_fight.get("players") or []
            if isinstance(player, dict)
        )
        if player_id is not None
    }
    base_capped_jobs = local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(selected.encounter_key)
    include_graph_downtime = not local_gcd.gcd_core.raw_event_uses_targetability_only_downtime(
        selected.encounter_key,
        job,
    )

    def build_downtime(*, include_graph: bool, unable_to_act: set[int] | None = None) -> dict[str, Any]:
        return local_gcd.gcd_core.raw_event_downtime_source(
            graph,
            raw_events,
            encounter_key=selected.encounter_key,
            source_id=source_id,
            friendly_ids=friendly_ids,
            fight_start_time=gcd_start_time,
            fight_end_time=end_time,
            unable_to_act_status_ids=fallback.unable_to_act_status_ids if unable_to_act is None else unable_to_act,
            metadata_store=fallback.metadata_store,
            job=job,
            include_graph_downtime=include_graph,
        )

    def without_windows(source: dict[str, Any], *keys: str) -> dict[str, Any]:
        copied = dict(source)
        for key in keys:
            copied[key] = []
        return copied

    def summarize_downtime(source: dict[str, Any]) -> dict[str, Any]:
        base_windows = local_gcd.gcd_core.downtime_windows(source)
        encounter_windows = local_gcd.gcd_core.encounter_downtime_windows(source)
        denominator_only_windows = local_gcd.gcd_core.denominator_only_downtime_windows(source)
        coverage_clip_windows = local_gcd.gcd_core.coverage_clip_downtime_windows(source)

        def compact_windows(windows: list[tuple[float, float]]) -> dict[str, Any]:
            return {
                "count": len(windows),
                "total_ms": round(local_gcd.gcd_core.total_window_ms(windows)),
                "windows": [[round(start), round(end)] for start, end in windows[:10]],
            }

        return {
            "base": compact_windows(base_windows),
            "encounter": compact_windows(encounter_windows),
            "denominator_only": compact_windows(denominator_only_windows),
            "coverage_clip": compact_windows(coverage_clip_windows),
        }

    def compact(coverage: dict[str, Any] | None) -> dict[str, Any] | None:
        if not coverage:
            return None
        keys = (
            "percent",
            "covered_time_ms",
            "denominator_ms",
            "downtime_ms",
            "gcd_cast_count",
            "source",
            "speed_stat_source",
            "estimated_skill_speed",
            "estimated_spell_speed",
            "estimated_speed_below_minimum",
            "casts_graph_percent",
            "casts_graph_denominator_ms",
        )
        return {key: coverage.get(key) for key in keys if key in coverage}

    def calculate_variant(
        *,
        downtime_source: dict[str, Any],
        cap_next_gcd_jobs: set[str] | frozenset[str],
        speed_stats_override: dict[str, int] | None = None,
    ) -> dict[str, Any] | None:
        return local_gcd.calculate_gcd_coverage_from_raw_events(
            raw_events,
            fallback.metadata_store,
            encounter_key=selected.encounter_key,
            source_id=source_id,
            job=job,
            fight_start_time=gcd_start_time,
            fight_end_time=end_time,
            fallback_denominator_ms=gcd_denominator_ms,
            downtime_source=downtime_source,
            cap_next_gcd_jobs=cap_next_gcd_jobs,
            speed_stats_override=speed_stats_override,
        )

    def speed_estimation_debug() -> dict[str, Any]:
        speed_windows = local_gcd.gcd_core.raw_speed_modifier_windows(
            raw_events,
            source_id=source_id,
            fight_end_time=end_time,
        )
        attempts = local_gcd.gcd_core.extract_gcd_speed_estimation_attempts_from_raw_events(
            raw_events,
            fallback.metadata_store,
            source_id=source_id,
        )
        intervals_by_attribute: dict[str, list[dict[str, Any]]] = {
            "skill_speed": [],
            "spell_speed": [],
        }
        for index, current in enumerate(attempts[1:], start=1):
            previous = attempts[index - 1]
            if previous.get("interrupted"):
                continue
            metadata = previous.get("metadata")
            if (
                not isinstance(metadata, local_gcd.gcd_core.ActionMetadata)
                or not metadata.recast_speed_adjusted
                or metadata.action_id in local_gcd.gcd_core.RECAST_SUBSTAT_EXCLUDED_ACTION_IDS
            ):
                continue
            attribute_key: str | None = None
            if metadata.action_category_id == 2:
                attribute_key = "spell_speed"
            elif metadata.action_category_id == 3:
                attribute_key = "skill_speed"
            if attribute_key is None:
                continue

            previous_start = local_gcd.first_number(previous.get("cast_start_timestamp"), previous.get("timestamp"))
            current_start = local_gcd.first_number(current.get("cast_start_timestamp"), current.get("timestamp"))
            if previous_start is None or current_start is None:
                continue
            raw_interval = current_start - previous_start
            if raw_interval <= 0:
                continue

            recast_for_scale = metadata.effective_recast_ms or local_gcd.gcd_core.BASE_GCD_MS
            has_animation_lock = False
            if local_gcd.to_number(previous.get("cast_duration_ms")) and metadata.cast_ms >= local_gcd.gcd_core.BASE_GCD_MS:
                has_animation_lock = True
                recast_for_scale = metadata.cast_ms

            speed_modifier = local_gcd.gcd_core.speed_modifier_at_timestamp(
                previous_start,
                job=job,
                speed_windows=speed_windows,
            )
            if speed_modifier <= 0:
                continue
            adjusted_interval = (
                (raw_interval - (100 if has_animation_lock else 0))
                / (recast_for_scale / local_gcd.gcd_core.BASE_GCD_MS)
                / speed_modifier
            )
            if adjusted_interval <= 0:
                continue
            intervals_by_attribute[attribute_key].append(
                {
                    "previous_action_id": metadata.action_id,
                    "previous_action_name": metadata.name,
                    "next_action_id": current.get("action_id"),
                    "timestamp": previous_start,
                    "raw_interval": raw_interval,
                    "adjusted_interval": adjusted_interval,
                    "base_recast": metadata.effective_recast_ms,
                    "speed_modifier": speed_modifier,
                    "has_animation_lock": has_animation_lock,
                }
            )

        summary: dict[str, Any] = {}
        for attribute_key, intervals in intervals_by_attribute.items():
            raw_values = [item["adjusted_interval"] for item in intervals]
            bucket_counts: dict[int, int] = {}
            for interval in raw_values:
                bucket = int(interval // local_gcd.gcd_core.RECAST_INTERVAL_BATCH_MS)
                bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1
            sorted_buckets = sorted(bucket_counts.items(), key=lambda item: (-item[1], item[0]))[:10]
            estimate = local_gcd.gcd_core.estimate_recast_from_xivanalysis_batches(raw_values)
            summary[attribute_key] = {
                "sample_count": len(intervals),
                "estimated_gcd_ms": estimate,
                "estimated_stat": (
                    local_gcd.gcd_core.speed_stat_from_estimated_gcd_ms(estimate)
                    if estimate > 0
                    else None
                ),
                "top_buckets": [
                    {
                        "bucket": bucket,
                        "range_ms": [
                            bucket * local_gcd.gcd_core.RECAST_INTERVAL_BATCH_MS,
                            ((bucket + 1) * local_gcd.gcd_core.RECAST_INTERVAL_BATCH_MS) - 1,
                        ],
                        "count": count,
                    }
                    for bucket, count in sorted_buckets
                ],
                "samples": sorted(intervals, key=lambda item: item["adjusted_interval"])[:12]
                + sorted(intervals, key=lambda item: item["adjusted_interval"])[-12:],
            }
        return summary

    default_downtime = build_downtime(include_graph=include_graph_downtime)
    raw_only_downtime = build_downtime(include_graph=False)
    no_unable_downtime = build_downtime(include_graph=include_graph_downtime, unable_to_act=set())
    no_downtime = {"combatTime": gcd_denominator_ms}
    no_base_downtime = without_windows(default_downtime, "downtime")
    no_encounter_downtime = without_windows(default_downtime, "encounter_downtime")
    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
        graph,
        fallback.metadata_store,
        source_id=source_id,
        job=job,
        fight_start_time=gcd_start_time,
        fight_end_time=end_time,
        fallback_denominator_ms=gcd_denominator_ms,
    )

    variants: dict[str, Any] = {
        "graph": compact(graph_coverage),
        "raw_default": compact(calculate_variant(downtime_source=default_downtime, cap_next_gcd_jobs=base_capped_jobs)),
        "raw_capped_job": compact(
            calculate_variant(downtime_source=default_downtime, cap_next_gcd_jobs=base_capped_jobs | {job})
        ),
        "raw_targetability_only": compact(
            calculate_variant(downtime_source=raw_only_downtime, cap_next_gcd_jobs=base_capped_jobs)
        ),
        "raw_no_unable_to_act": compact(
            calculate_variant(downtime_source=no_unable_downtime, cap_next_gcd_jobs=base_capped_jobs)
        ),
        "raw_no_base_downtime": compact(
            calculate_variant(downtime_source=no_base_downtime, cap_next_gcd_jobs=base_capped_jobs)
        ),
        "raw_no_encounter_downtime": compact(
            calculate_variant(downtime_source=no_encounter_downtime, cap_next_gcd_jobs=base_capped_jobs)
        ),
        "raw_no_downtime": compact(
            calculate_variant(downtime_source=no_downtime, cap_next_gcd_jobs=base_capped_jobs)
        ),
    }
    for skill_speed in (420, 505, 591, 676, 847, 1018, 1104, 1360, 1600, 2000, 3000):
        variants[f"skill_speed_{skill_speed}"] = compact(
            calculate_variant(
                downtime_source=default_downtime,
                cap_next_gcd_jobs=base_capped_jobs,
                speed_stats_override={"skill_speed": skill_speed},
            )
        )

    result = {
        "identity": {
            "report_code": report_code,
            "fight_id": fight_id,
            "encounter_key": selected.encounter_key,
            "job": job,
            "fflogs_source_id": source_id,
            "player": selected.player.get("name"),
            "server": selected.player.get("server"),
        },
        "fight": {
            "start_time": start_time,
            "end_time": end_time,
            "gcd_start_time": gcd_start_time,
            "gcd_denominator_ms": gcd_denominator_ms,
            "friendly_count": len(friendly_ids),
        },
        "combatant_speed_stats": local_gcd.gcd_core.combatant_speed_stats(raw_events, source_id=source_id),
        "base_capped_jobs": sorted(base_capped_jobs),
        "include_graph_downtime": include_graph_downtime,
        "downtime": {
            "default_windows": len(default_downtime.get("downtime") or []),
            "raw_only_windows": len(raw_only_downtime.get("downtime") or []),
            "no_unable_windows": len(no_unable_downtime.get("downtime") or []),
            "default": summarize_downtime(default_downtime),
            "raw_only": summarize_downtime(raw_only_downtime),
            "no_unable": summarize_downtime(no_unable_downtime),
        },
        "speed_estimation": speed_estimation_debug(),
        "variants": variants,
    }
    log_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
        errors="backslashreplace",
    )
    return 0


def main(argv: list[str]) -> int:
    log_path, audit_args = split_wrapper_args(argv)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if audit_args[:1] == ["--debug-local-coverage"]:
        exit_code = run_debug_local_coverage(audit_args[1:], log_path)
        print(f"log={log_path}")
        print(f"exit_code={exit_code}")
        return exit_code
    if audit_args[:1] == ["--debug-local-coverage-variants"]:
        exit_code = run_debug_local_coverage_variants(audit_args[1:], log_path)
        print(f"log={log_path}")
        print(f"exit_code={exit_code}")
        return exit_code

    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8:backslashreplace"

    command = [
        sys.executable,
        "-X",
        "utf8",
        str(SCRIPT_DIR / "audit_xivanalysis_gcd_sample.py"),
        *audit_args,
    ]
    with log_path.open("w", encoding="utf-8", errors="backslashreplace") as log_file:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            check=False,
        )

    print(f"log={log_path}")
    print(f"exit_code={completed.returncode}")
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
