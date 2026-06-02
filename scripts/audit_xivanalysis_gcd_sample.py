from __future__ import annotations

import argparse
import json
import random
import sys
import time
from contextlib import nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import backfill_gcd_coverage as local_gcd  # noqa: E402
import backfill_gcd_coverage_xivanalysis as xiv_gcd  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", line_buffering=True)


DEFAULT_CATEGORIES = ("零式", "極", "幻")
DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs" / "gcd_xivanalysis_audit_latest.json"
LOCAL_MODE_STORED = "stored"
LOCAL_MODE_RECOMPUTE = "recompute"
DEFAULT_REQUIRED_JOBS = (
    "Paladin",
    "Warrior",
    "DarkKnight",
    "Gunbreaker",
    "WhiteMage",
    "Scholar",
    "Astrologian",
    "Sage",
    "Monk",
    "Dragoon",
    "Ninja",
    "Samurai",
    "Reaper",
    "Viper",
    "Bard",
    "Machinist",
    "Dancer",
    "BlackMage",
    "Summoner",
    "RedMage",
    "Pictomancer",
)


@dataclass(frozen=True)
class FightGroup:
    encounter_key: str
    encounter_name: str
    category: str
    report_code: str
    fight_id: int
    candidates: list[local_gcd.GcdCandidate]

    @property
    def label(self) -> str:
        return f"{self.encounter_key} {self.report_code} fight={self.fight_id}"

    @property
    def identity(self) -> tuple[str, str, int]:
        return (self.encounter_key, self.report_code, self.fight_id)


@dataclass(frozen=True)
class EncounterSampleSummary:
    encounter_key: str
    encounter_name: str
    category: str
    available_fights: int
    selected_fights: int
    base_selected_fights: int
    supplemental_fights: int
    available_jobs: list[str]
    target_jobs: list[str]
    covered_jobs: list[str]
    missing_jobs: list[str]
    unavailable_jobs: list[str]


@dataclass(frozen=True)
class SampleResult:
    fights: list[FightGroup]
    summaries: dict[str, EncounterSampleSummary]


@dataclass(frozen=True)
class AccessibleSampleResult:
    fights: list[FightGroup]
    skipped_fights: list[dict[str, Any]]


def current_percent(player: dict[str, Any]) -> float | None:
    coverage = player.get("gcd_coverage")
    if not isinstance(coverage, dict):
        return None
    return local_gcd.to_number(coverage.get("percent"))


def current_source(player: dict[str, Any]) -> str | None:
    coverage = player.get("gcd_coverage")
    if not isinstance(coverage, dict):
        return None
    source = coverage.get("source")
    return str(source) if source else None


def display_percent(value: float | None) -> float | None:
    return None if value is None else round(value, 1)


def collect_fight_groups(
    encounters: dict[str, dict[str, Any]],
    *,
    categories: set[str],
) -> tuple[list[FightGroup], dict[str, dict[str, Any]]]:
    candidates, _, _, _, rankings_by_key = local_gcd.scan_candidates(encounters, include_current=True)
    groups: dict[tuple[str, str, int], list[local_gcd.GcdCandidate]] = {}
    for candidate in candidates:
        category = str(candidate.encounter.get("category") or "")
        if category not in categories:
            continue
        fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
        if fight_id is None:
            continue
        if not local_gcd.player_has_query_context(candidate.fight, candidate.player):
            continue
        key = (candidate.encounter_key, candidate.report_code, fight_id)
        groups.setdefault(key, []).append(candidate)

    fight_groups: list[FightGroup] = []
    for (encounter_key, report_code, fight_id), group_candidates in groups.items():
        encounter = group_candidates[0].encounter
        fight_groups.append(
            FightGroup(
                encounter_key=encounter_key,
                encounter_name=str(encounter.get("name") or encounter_key),
                category=str(encounter.get("category") or ""),
                report_code=report_code,
                fight_id=fight_id,
                candidates=sorted(
                    group_candidates,
                    key=lambda candidate: (
                        local_gcd.to_int(candidate.player.get("fflogs_id")) or 0,
                        str(candidate.player.get("name") or ""),
                    ),
                ),
            )
        )

    fight_groups.sort(key=lambda group: (group.encounter_key, group.report_code, group.fight_id))
    return fight_groups, rankings_by_key


def apply_candidate_filters(fights: list[FightGroup], args: argparse.Namespace) -> list[FightGroup]:
    excluded_report_codes = {str(code) for code in (args.exclude_report_codes or []) if str(code)}
    if not args.report_code and args.fight_id is None and not args.player_name and not excluded_report_codes:
        return fights

    filtered: list[FightGroup] = []
    for group in fights:
        if group.report_code in excluded_report_codes:
            continue
        if args.report_code and group.report_code != args.report_code:
            continue
        if args.fight_id is not None and group.fight_id != args.fight_id:
            continue

        candidates = group.candidates
        if args.player_name:
            candidates = [
                candidate
                for candidate in candidates
                if (candidate.player.get("name") or candidate.player.get("character_name")) == args.player_name
            ]
        if not candidates:
            continue

        filtered.append(
            FightGroup(
                encounter_key=group.encounter_key,
                encounter_name=group.encounter_name,
                category=group.category,
                report_code=group.report_code,
                fight_id=group.fight_id,
                candidates=candidates,
            )
        )

    return filtered


def jobs_in_fight(group: FightGroup) -> set[str]:
    jobs: set[str] = set()
    for candidate in group.candidates:
        job = str(candidate.player.get("job") or "")
        if job:
            jobs.add(job)
    return jobs


def sorted_jobs(jobs: set[str]) -> list[str]:
    known_order = {job: index for index, job in enumerate(DEFAULT_REQUIRED_JOBS)}
    return sorted(jobs, key=lambda job: (known_order.get(job, len(known_order)), job))


def sample_fights(
    fights: list[FightGroup],
    *,
    sample_size: int,
    seed: str,
    required_jobs: set[str] | None = None,
) -> SampleResult:
    # 稽核單位是「副本」，不是「分類」。每個副本先抽基本場數，再用最少額外 fight
    # 補齊缺漏職業，避免 10 場剛好都沒有某個職業時留下公式盲點。
    groups_by_encounter: dict[str, list[FightGroup]] = {}
    for fight in fights:
        groups_by_encounter.setdefault(fight.encounter_key, []).append(fight)

    selected: list[FightGroup] = []
    summaries: dict[str, EncounterSampleSummary] = {}
    target_jobs = set(DEFAULT_REQUIRED_JOBS if required_jobs is None else required_jobs)
    for encounter_key, encounter_fights in sorted(groups_by_encounter.items()):
        encounter_fights = sorted(
            encounter_fights,
            key=lambda group: (group.category, group.report_code, group.fight_id),
        )
        available_jobs: set[str] = set()
        for group in encounter_fights:
            available_jobs.update(jobs_in_fight(group))

        base_count = min(max(0, sample_size), len(encounter_fights))
        rng = random.Random(f"{seed}:{encounter_key}:base")
        if base_count >= len(encounter_fights):
            encounter_selected = list(encounter_fights)
        else:
            encounter_selected = rng.sample(encounter_fights, base_count)

        selected_keys = {group.identity for group in encounter_selected}
        covered_jobs: set[str] = set()
        for group in encounter_selected:
            covered_jobs.update(jobs_in_fight(group))

        available_target_jobs = target_jobs & available_jobs
        missing_available_jobs = available_target_jobs - covered_jobs
        supplemental_count = 0
        supplement_rng = random.Random(f"{seed}:{encounter_key}:job-coverage")
        tie_breakers = {group.identity: supplement_rng.random() for group in encounter_fights}
        while missing_available_jobs:
            remaining = [group for group in encounter_fights if group.identity not in selected_keys]
            if not remaining:
                break
            best = max(
                remaining,
                key=lambda group: (
                    len(jobs_in_fight(group) & missing_available_jobs),
                    len(jobs_in_fight(group) & available_target_jobs),
                    tie_breakers[group.identity],
                ),
            )
            if not (jobs_in_fight(best) & missing_available_jobs):
                break
            encounter_selected.append(best)
            selected_keys.add(best.identity)
            covered_jobs.update(jobs_in_fight(best))
            missing_available_jobs = available_target_jobs - covered_jobs
            supplemental_count += 1

        encounter_selected = sorted(
            encounter_selected,
            key=lambda group: (group.category, group.encounter_key, group.report_code, group.fight_id),
        )
        selected.extend(encounter_selected)
        first = encounter_fights[0]
        summaries[encounter_key] = EncounterSampleSummary(
            encounter_key=encounter_key,
            encounter_name=first.encounter_name,
            category=first.category,
            available_fights=len(encounter_fights),
            selected_fights=len(encounter_selected),
            base_selected_fights=base_count,
            supplemental_fights=supplemental_count,
            available_jobs=sorted_jobs(available_jobs),
            target_jobs=sorted_jobs(target_jobs),
            covered_jobs=sorted_jobs(covered_jobs & target_jobs),
            missing_jobs=sorted_jobs(target_jobs - covered_jobs),
            unavailable_jobs=sorted_jobs(target_jobs - available_jobs),
        )

    return SampleResult(
        fights=sorted(selected, key=lambda group: (group.category, group.encounter_key, group.report_code, group.fight_id)),
        summaries=summaries,
    )


def summarize_sample(
    fights: list[FightGroup],
    selected: list[FightGroup],
    *,
    sample_size: int,
    required_jobs: set[str],
) -> dict[str, EncounterSampleSummary]:
    groups_by_encounter: dict[str, list[FightGroup]] = {}
    selected_by_encounter: dict[str, list[FightGroup]] = {}
    for group in fights:
        groups_by_encounter.setdefault(group.encounter_key, []).append(group)
    for group in selected:
        selected_by_encounter.setdefault(group.encounter_key, []).append(group)

    summaries: dict[str, EncounterSampleSummary] = {}
    target_jobs = set(required_jobs)
    for encounter_key, encounter_fights in sorted(groups_by_encounter.items()):
        selected_fights = selected_by_encounter.get(encounter_key, [])
        available_jobs: set[str] = set()
        covered_jobs: set[str] = set()
        for group in encounter_fights:
            available_jobs.update(jobs_in_fight(group))
        for group in selected_fights:
            covered_jobs.update(jobs_in_fight(group))

        available_target_jobs = target_jobs & available_jobs
        missing_jobs = available_target_jobs - covered_jobs
        unavailable_jobs = target_jobs - available_jobs
        base_count = min(max(0, sample_size), len(selected_fights))
        exemplar = encounter_fights[0]
        summaries[encounter_key] = EncounterSampleSummary(
            encounter_key=encounter_key,
            encounter_name=exemplar.encounter_name,
            category=exemplar.category,
            available_fights=len(encounter_fights),
            selected_fights=len(selected_fights),
            base_selected_fights=base_count,
            supplemental_fights=max(0, len(selected_fights) - base_count),
            available_jobs=sorted_jobs(available_jobs),
            target_jobs=sorted_jobs(target_jobs),
            covered_jobs=sorted_jobs(covered_jobs & available_target_jobs),
            missing_jobs=sorted_jobs(missing_jobs),
            unavailable_jobs=sorted_jobs(unavailable_jobs),
        )
    return summaries


def ensure_xivanalysis_accessible_sample(
    *,
    fights: list[FightGroup],
    selected: list[FightGroup],
    sample_size: int,
    seed: str,
    required_jobs: set[str],
    page_timeout_ms: int,
    retries: int,
    workers: int,
    delay_ms: int,
    headful: bool,
) -> AccessibleSampleResult:
    """補抽目前仍能由 xivanalysis 頁面讀取的戰鬥。

    排行榜資料可能保存了當時公開、後來轉 private 或被刪除的 FFLogs report。這些紀錄仍是
    專案歷史資料，但外站頁面稽核無法讀取，自然不能用來證明「本地 GCD 與 xivanalysis 顯示
    相同」。preflight 只檢查每場第一位玩家的頁面；同一 report/fight 若第一位玩家已是 Report
    not found，整場八人都會失敗，因此直接換抽同副本其他戰鬥，讓每個副本仍維持 100 場可稽核樣本。
    """

    groups_by_encounter: dict[str, list[FightGroup]] = {}
    selected_by_encounter: dict[str, list[FightGroup]] = {}
    for group in fights:
        groups_by_encounter.setdefault(group.encounter_key, []).append(group)
    for group in selected:
        selected_by_encounter.setdefault(group.encounter_key, []).append(group)

    selected_ids = {group.identity for group in selected}
    skipped_ids: set[tuple[str, str, int]] = set()
    skipped_fights: list[dict[str, Any]] = []

    def skip_group(group: FightGroup, error: Exception) -> None:
        skipped_ids.add(group.identity)
        skipped_fights.append(
            {
                "encounter_key": group.encounter_key,
                "encounter_name": group.encounter_name,
                "category": group.category,
                "report_code": group.report_code,
                "fight_id": group.fight_id,
                "error": f"{type(error).__name__}: {error}",
            }
        )
        print(f"  preflight skip {group.label}: {type(error).__name__}: {error}")

    def selected_jobs(encounter_key: str) -> set[str]:
        jobs: set[str] = set()
        for group in selected_by_encounter.get(encounter_key, []):
            jobs.update(jobs_in_fight(group))
        return jobs

    def available_jobs(encounter_key: str) -> set[str]:
        jobs: set[str] = set()
        for group in groups_by_encounter.get(encounter_key, []):
            jobs.update(jobs_in_fight(group))
        return jobs

    def ordered_remaining(encounter_key: str) -> list[FightGroup]:
        rng = random.Random(f"{seed}:{encounter_key}:xivanalysis-accessible-replacement")
        tie_breakers = {group.identity: rng.random() for group in groups_by_encounter.get(encounter_key, [])}
        missing_jobs = (required_jobs & available_jobs(encounter_key)) - selected_jobs(encounter_key)
        return sorted(
            (
                group
                for group in groups_by_encounter.get(encounter_key, [])
                if group.identity not in selected_ids and group.identity not in skipped_ids
            ),
            key=lambda group: (
                -len(jobs_in_fight(group) & missing_jobs),
                -len(jobs_in_fight(group) & required_jobs),
                tie_breakers[group.identity],
            ),
        )

    print("xivanalysis 可讀性 preflight：檢查抽樣戰鬥是否仍可由外站頁面讀取。")
    preflight_candidates = [group.candidates[0] for group in selected]
    group_by_candidate_id = {id(group.candidates[0]): group for group in selected}
    accessible_initial_ids: set[tuple[str, str, int]] = set()
    rate_limit_coordinator = xiv_gcd.XivanalysisRateLimitCoordinator(
        cooldown_seconds=xiv_gcd.DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
        max_pauses=xiv_gcd.DEFAULT_MAX_RATE_LIMIT_PAUSES,
    )
    for fetch_result in xiv_gcd.fetch_xivanalysis_results_parallel(
        preflight_candidates,
        workers=max(1, workers),
        base_url=xiv_gcd.XIVANALYSIS_BASE_URL,
        timeout_ms=max(5_000, page_timeout_ms),
        retries=max(1, retries),
        headful=headful,
        locale="en-US",
        delay_ms=max(0, delay_ms),
        rate_limit_coordinator=rate_limit_coordinator,
    ):
        group = group_by_candidate_id[id(fetch_result.candidate)]
        if fetch_result.error is None:
            accessible_initial_ids.add(group.identity)
            if fetch_result.index % 25 == 0 or fetch_result.index == fetch_result.total:
                print(f"  preflight [{fetch_result.index}/{fetch_result.total}] ok")
        else:
            selected_ids.discard(group.identity)
            skip_group(group, fetch_result.error)

    for encounter_key, encounter_selected in list(selected_by_encounter.items()):
        selected_by_encounter[encounter_key] = [
            group for group in encounter_selected if group.identity in accessible_initial_ids
        ]

    with xiv_gcd.XivanalysisPageClient(
        base_url=xiv_gcd.XIVANALYSIS_BASE_URL,
        timeout_ms=max(5_000, page_timeout_ms),
        retries=max(1, retries),
        headful=headful,
        locale="en-US",
    ) as client:
        for encounter_key, encounter_fights in sorted(groups_by_encounter.items()):
            target_count = min(max(0, sample_size), len(encounter_fights))
            while len(selected_by_encounter.get(encounter_key, [])) < target_count:
                replacement = None
                for candidate_group in ordered_remaining(encounter_key):
                    try:
                        client.fetch_gcd_percent(candidate_group.candidates[0])
                    except Exception as error:  # noqa: BLE001
                        skipped_ids.add(candidate_group.identity)
                        skip_group(candidate_group, error)
                        continue
                    replacement = candidate_group
                    break

                if replacement is None:
                    raise RuntimeError(
                        f"{encounter_key} 找不到足夠可由 xivanalysis 讀取的替代戰鬥，"
                        f"目前只有 {len(selected_by_encounter.get(encounter_key, []))} / {target_count} 場。"
                    )
                selected_by_encounter.setdefault(encounter_key, []).append(replacement)
                selected_ids.add(replacement.identity)
                print(f"  preflight add {replacement.label}")

            while True:
                missing_jobs = (required_jobs & available_jobs(encounter_key)) - selected_jobs(encounter_key)
                if not missing_jobs:
                    break

                replacement = None
                for candidate_group in ordered_remaining(encounter_key):
                    if not (jobs_in_fight(candidate_group) & missing_jobs):
                        continue
                    try:
                        client.fetch_gcd_percent(candidate_group.candidates[0])
                    except Exception as error:  # noqa: BLE001
                        skipped_ids.add(candidate_group.identity)
                        skip_group(candidate_group, error)
                        continue
                    replacement = candidate_group
                    break

                if replacement is None:
                    print(f"  preflight warning {encounter_key}: 無法補齊職業 {', '.join(sorted_jobs(missing_jobs))}")
                    break
                selected_by_encounter.setdefault(encounter_key, []).append(replacement)
                selected_ids.add(replacement.identity)
                print(f"  preflight add {replacement.label} for job coverage")

    accessible_selected = [
        group
        for encounter_key in sorted(selected_by_encounter)
        for group in selected_by_encounter[encounter_key]
    ]
    return AccessibleSampleResult(
        fights=sorted(accessible_selected, key=lambda group: (group.category, group.encounter_key, group.report_code, group.fight_id)),
        skipped_fights=skipped_fights,
    )


def compare_candidate(
    client: xiv_gcd.XivanalysisPageClient | None,
    candidate: local_gcd.GcdCandidate,
    *,
    checked_at_iso: str,
    tolerance: float,
    apply: bool,
    apply_all_checked: bool,
    local_mode: str,
    local_fallback: xiv_gcd.LocalGcdFallback | None,
    fetched_percent: float | None = None,
    fetched_url: str | None = None,
    fetched_error: Exception | None = None,
) -> dict[str, Any]:
    player = candidate.player
    stored_percent = current_percent(player)
    stored_source = current_source(player)
    before = stored_percent
    before_source = stored_source
    local_coverage: dict[str, Any] | None = None
    if local_mode == LOCAL_MODE_RECOMPUTE:
        if local_fallback is None:
            raise RuntimeError("local_mode=recompute 需要本地 GCD 計算器。")
        try:
            local_coverage = local_fallback.calculate(candidate)
        except Exception as error:  # noqa: BLE001
            return {
                "encounter_key": candidate.encounter_key,
                "report_code": candidate.report_code,
                "fight_id": local_gcd.to_int(candidate.fight.get("fight_id")),
                "player": player.get("name") or player.get("character_name"),
                "server": player.get("server"),
                "job": player.get("job"),
                "fflogs_id": player.get("fflogs_id"),
                "current_percent": None,
                "current_source": LOCAL_MODE_RECOMPUTE,
                "stored_percent": stored_percent,
                "stored_source": stored_source,
                "state": "error",
                "error": f"LocalGcdError: {type(error).__name__}: {error}",
            }
        before = local_gcd.to_number((local_coverage or {}).get("percent"))
        before_source = str((local_coverage or {}).get("source") or LOCAL_MODE_RECOMPUTE)
    url = fetched_url or xiv_gcd.build_xivanalysis_url(candidate)
    result: dict[str, Any] = {
        "encounter_key": candidate.encounter_key,
        "report_code": candidate.report_code,
        "fight_id": local_gcd.to_int(candidate.fight.get("fight_id")),
        "player": player.get("name") or player.get("character_name"),
        "server": player.get("server"),
        "job": player.get("job"),
        "fflogs_id": player.get("fflogs_id"),
        "current_percent": before,
        "current_source": before_source,
        "stored_percent": stored_percent,
        "stored_source": stored_source,
        "local_mode": local_mode,
        "xivanalysis_url": url,
    }
    if local_coverage is not None:
        result["local_coverage"] = {
            key: local_coverage.get(key)
            for key in (
                "covered_time_ms",
                "denominator_ms",
                "downtime_ms",
                "coverage_downtime_ms",
                "denominator_downtime_ms",
                "gcd_cast_count",
                "calculation_version",
                "source",
                "fallback_selection",
                "downtime_selection",
                "speed_stat_source",
                "estimated_speed_below_minimum",
                "raw_events_percent",
                "raw_events_denominator_ms",
                "casts_graph_percent",
                "casts_graph_denominator_ms",
                "raw_targetability_percent",
                "raw_targetability_denominator_ms",
                "raw_next_gcd_capped_percent",
                "raw_next_gcd_capped_denominator_ms",
            )
            if key in local_coverage
        }
    try:
        if fetched_error is not None:
            raise fetched_error
        if fetched_percent is None:
            if client is None:
                raise xiv_gcd.XivanalysisLookupError("缺少 xivanalysis client 或預抓結果，無法讀取頁面百分比。")
            xiv_percent, url = client.fetch_gcd_percent(candidate)
        else:
            xiv_percent = fetched_percent
    except Exception as error:  # noqa: BLE001
        result["state"] = "error"
        result["error"] = f"{type(error).__name__}: {error}"
        return result

    # xivanalysis checklist 頁面只顯示一位小數；audit 應以同樣的顯示精度判斷
    # 是否超出容忍值，避免 73.71 vs 72.7 這類其實顯示為 73.7 的邊界值被誤判。
    before_display = display_percent(before)
    stored_display = display_percent(stored_percent)
    difference = None if before_display is None else round(before_display - xiv_percent, 2)
    stored_difference = None if stored_display is None else round(stored_display - xiv_percent, 2)
    mismatch = before is None or abs(difference or 0) > tolerance
    result.update(
        {
            "state": "mismatch" if mismatch else "matched",
            "xivanalysis_percent": round(xiv_percent, 2),
            "current_display_percent": before_display,
            "difference": difference,
            "stored_display_percent": stored_display,
            "stored_difference": stored_difference,
        }
    )
    should_apply = apply and (mismatch or apply_all_checked)
    if should_apply:
        xiv_gcd.apply_xivanalysis_coverage(
            candidate,
            percent=xiv_percent,
            url=url,
            checked_at_iso=checked_at_iso,
        )
        result["applied"] = True
        result["applied_reason"] = "mismatch" if mismatch else "all_checked"
    return result


def write_changed_rankings(
    changed_encounter_keys: set[str],
    *,
    rankings_by_key: dict[str, dict[str, Any]],
    encounters: dict[str, dict[str, Any]],
) -> None:
    for key in sorted(changed_encounter_keys):
        ranking = rankings_by_key.get(key)
        encounter = encounters.get(key)
        if not ranking or not encounter:
            continue
        local_gcd.write_ranking_file(encounter, ranking)
        print(f"已寫入 {key} 的 xivanalysis GCD 稽核修正。")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="隨機抽樣比對本地 GCD 與 xivanalysis Always Be Casting。")
    parser.add_argument("--sample-size", type=int, default=10, help="每個副本基本抽樣的戰鬥組數；職業覆蓋不足時會自動補抽。")
    parser.add_argument("--seed", default="2026-05-22", help="抽樣 seed，固定後可重現同一批戰鬥。")
    parser.add_argument("--categories", nargs="+", default=list(DEFAULT_CATEGORIES), help="要抽樣的副本分類。")
    parser.add_argument(
        "--required-jobs",
        nargs="+",
        default=list(DEFAULT_REQUIRED_JOBS),
        help="每個副本至少要覆蓋一次的職業代碼。若資料內完全沒有該職業，會記錄為 unavailable。",
    )
    parser.add_argument("--tolerance", type=float, default=1.0, help="允許差異百分點，超過才視為不相符。")
    parser.add_argument("--apply", action="store_true", help="將不相符玩家改寫為 xivanalysis 頁面值。")
    parser.add_argument(
        "--apply-all-checked",
        action="store_true",
        help=(
            "搭配 --apply 使用；所有成功讀到 xivanalysis 頁面的玩家都寫回頁面值。"
            "這可用於 exact stored 稽核，避免本地重算已相符但舊 stored 值仍不同。"
        ),
    )
    parser.add_argument(
        "--local-mode",
        choices=[LOCAL_MODE_STORED, LOCAL_MODE_RECOMPUTE],
        default=LOCAL_MODE_RECOMPUTE,
        help="stored 使用已保存的 GCD；recompute 重新查 FFLogs Casts graph 並用本地演算法計算。",
    )
    parser.add_argument("--delay-ms", type=int, default=2500, help="每位玩家查詢後的延遲，避免 xivanalysis 限流。")
    parser.add_argument("--page-timeout-ms", type=int, default=120_000, help="xivanalysis 單頁逾時。")
    parser.add_argument("--retries", type=int, default=4, help="xivanalysis 單頁重試次數。")
    parser.add_argument("--workers", type=int, default=1, help="同時開啟幾個 xivanalysis 瀏覽器 worker；預設 1，過高容易被站端限流。")
    parser.add_argument(
        "--abort-on-fetch-error",
        action="store_true",
        help="抓取 xivanalysis 頁面時若遇到永久錯誤就立刻中止，方便快速找出需排除的 private/deleted report。",
    )
    parser.add_argument(
        "--require-xivanalysis-accessible",
        action="store_true",
        help="正式抽樣前先排除目前已無法由 xivanalysis 頁面讀取的 report/fight，並從同副本補抽可讀戰鬥。",
    )
    parser.add_argument("--error-retry-passes", type=int, default=3, help="主巡檢後，針對讀取錯誤玩家額外重試幾輪。")
    parser.add_argument("--error-retry-delay-ms", type=int, default=1500, help="錯誤重試時每位玩家查詢後的延遲。")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH), help="輸出的 JSON 稽核報告路徑。")
    parser.add_argument("--headful", action="store_true", help="以有畫面模式開啟 Chromium，僅供人工除錯。")
    parser.add_argument("--report-code", help="只稽核指定 report code，方便複驗單場差異。")
    parser.add_argument(
        "--exclude-report-codes",
        nargs="+",
        default=[],
        help="從抽樣池排除目前已無法由 xivanalysis 檢核的 report code；抽樣器會自動補抽同副本其他戰鬥。",
    )
    parser.add_argument("--fight-id", type=int, help="只稽核指定 fight id。")
    parser.add_argument("--player-name", help="只稽核指定角色名稱。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    categories = {str(category) for category in args.categories}
    required_jobs = {str(job) for job in args.required_jobs if str(job)}
    encounters = local_gcd.load_all_encounters()
    fights, rankings_by_key = collect_fight_groups(encounters, categories=categories)
    fights = apply_candidate_filters(fights, args)
    sample = sample_fights(
        fights,
        sample_size=max(0, args.sample_size),
        seed=str(args.seed),
        required_jobs=required_jobs,
    )
    selected = sample.fights
    skipped_inaccessible_fights: list[dict[str, Any]] = []
    if args.require_xivanalysis_accessible:
        accessible_sample = ensure_xivanalysis_accessible_sample(
            fights=fights,
            selected=selected,
            sample_size=max(0, args.sample_size),
            seed=str(args.seed),
            required_jobs=required_jobs,
            page_timeout_ms=max(5_000, args.page_timeout_ms),
            retries=max(1, args.retries),
            workers=max(1, args.workers),
            delay_ms=max(0, args.delay_ms),
            headful=bool(args.headful),
        )
        selected = accessible_sample.fights
        skipped_inaccessible_fights = accessible_sample.skipped_fights
        sample.summaries = summarize_sample(
            fights,
            selected,
            sample_size=max(0, args.sample_size),
            required_jobs=required_jobs,
        )
    total_players = sum(len(group.candidates) for group in selected)
    selected_by_category: dict[str, int] = {}
    available_by_category: dict[str, int] = {}
    selected_by_encounter: dict[str, int] = {}
    available_by_encounter: dict[str, int] = {}
    for group in fights:
        available_by_category[group.category] = available_by_category.get(group.category, 0) + 1
        available_by_encounter[group.encounter_key] = available_by_encounter.get(group.encounter_key, 0) + 1
    for group in selected:
        selected_by_category[group.category] = selected_by_category.get(group.category, 0) + 1
        selected_by_encounter[group.encounter_key] = selected_by_encounter.get(group.encounter_key, 0) + 1
    checked_at_iso = local_gcd.milliseconds_to_iso(time.time() * 1000)

    print(f"可抽樣戰鬥組數：{len(fights)}")
    print(f"本輪抽樣戰鬥組數：{len(selected)}")
    for category in sorted(categories):
        print(
            f"  {category}：抽樣 {selected_by_category.get(category, 0)} / "
            f"可用 {available_by_category.get(category, 0)} 場"
        )
    print("副本抽樣與職業覆蓋：")
    for encounter_key, summary in sorted(sample.summaries.items(), key=lambda item: (item[1].category, item[0])):
        print(
            f"  {summary.category} / {summary.encounter_name} ({encounter_key})："
            f"抽樣 {summary.selected_fights} / 可用 {summary.available_fights} 場，"
            f"基本 {summary.base_selected_fights}，補職業 {summary.supplemental_fights}，"
            f"職業覆蓋 {len(summary.covered_jobs)} / {len(summary.target_jobs)}"
        )
        if summary.missing_jobs:
            print(f"    尚未覆蓋職業：{', '.join(summary.missing_jobs)}")
        if summary.unavailable_jobs:
            print(f"    資料內不可用職業：{', '.join(summary.unavailable_jobs)}")
    print(f"本輪需比對玩家數：{total_players}")
    print(f"分類：{', '.join(sorted(categories))}")
    print(f"seed：{args.seed}")
    print(f"每副本基本抽樣：{max(0, args.sample_size)} 場")
    print(f"職業覆蓋目標：{', '.join(sorted_jobs(required_jobs))}")
    print(f"差異容忍值：±{args.tolerance:.2f} 個百分點")
    print(f"本地值來源：{args.local_mode}")
    print(f"寫回修正：{'是' if args.apply else '否'}")
    print(f"寫回全部成功讀取玩家：{'是' if args.apply and args.apply_all_checked else '否'}")
    print(f"xivanalysis worker 數：{max(1, args.workers)}")
    print(f"排除不可讀 xivanalysis 頁面：{'是' if args.require_xivanalysis_accessible else '否'}")
    print(f"排除 report code：{', '.join(args.exclude_report_codes) if args.exclude_report_codes else '無'}")

    report: dict[str, Any] = {
        "schema_version": 2,
        "seed": args.seed,
        "categories": sorted(categories),
        "sample_size_per_encounter": max(0, args.sample_size),
        "required_jobs": sorted_jobs(required_jobs),
        "selected_fight_count": len(selected),
        "available_fights_by_category": available_by_category,
        "selected_fights_by_category": selected_by_category,
        "available_fights_by_encounter": available_by_encounter,
        "selected_fights_by_encounter": selected_by_encounter,
        "job_coverage_by_encounter": {
            encounter_key: asdict(summary)
            for encounter_key, summary in sorted(sample.summaries.items())
        },
        "player_count": total_players,
        "tolerance": args.tolerance,
        "local_mode": args.local_mode,
        "apply": bool(args.apply),
        "apply_all_checked": bool(args.apply and args.apply_all_checked),
        "require_xivanalysis_accessible": bool(args.require_xivanalysis_accessible),
        "excluded_report_codes": list(args.exclude_report_codes or []),
        "skipped_inaccessible_fights": skipped_inaccessible_fights,
        "checked_at_iso": checked_at_iso,
        "fights": [],
        "summary": {},
    }

    changed_encounter_keys: set[str] = set()
    matched = 0
    mismatched = 0
    errors = 0
    processed_players = 0
    error_entries: list[dict[str, Any]] = []
    local_fallback = xiv_gcd.LocalGcdFallback() if args.local_mode == LOCAL_MODE_RECOMPUTE else None

    if total_players <= 0:
        print("沒有需要比對的玩家，略過 xivanalysis 瀏覽器查詢。")
    else:
        worker_count = max(1, args.workers)
        prefetched_results: dict[int, xiv_gcd.XivanalysisFetchResult] = {}
        if worker_count > 1:
            # 外站稽核的權威仍是 xivanalysis 實際頁面文字。多 worker 只並行讀頁面百分比，
            # 後續仍照抽樣 fight/player 原順序比對與寫回，讓輸出 JSON 可穩定重現。
            selected_candidates = [candidate for group in selected for candidate in group.candidates]
            rate_limit_coordinator = xiv_gcd.XivanalysisRateLimitCoordinator(
                cooldown_seconds=xiv_gcd.DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
                max_pauses=xiv_gcd.DEFAULT_MAX_RATE_LIMIT_PAUSES,
            )
            for fetch_result in xiv_gcd.fetch_xivanalysis_results_parallel(
                selected_candidates,
                workers=worker_count,
                base_url=xiv_gcd.XIVANALYSIS_BASE_URL,
                timeout_ms=max(5_000, args.page_timeout_ms),
                retries=max(1, args.retries),
                headful=args.headful,
                locale="en-US",
                delay_ms=max(0, args.delay_ms),
                rate_limit_coordinator=rate_limit_coordinator,
            ):
                prefetched_results[id(fetch_result.candidate)] = fetch_result
                player = fetch_result.candidate.player
                player_label = player.get("name") or player.get("character_name")
                if fetch_result.error is None:
                    print(
                        f"  [fetch {fetch_result.index}/{fetch_result.total}] "
                        f"{player_label}:{player.get('job')} xiv={fetch_result.percent}"
                    )
                else:
                    if args.abort_on_fetch_error and isinstance(fetch_result.error, xiv_gcd.XivanalysisPermanentError):
                        fight_id = local_gcd.to_int(fetch_result.candidate.fight.get("fight_id"))
                        raise RuntimeError(
                            "xivanalysis fetch error: "
                            f"index={fetch_result.index}/{fetch_result.total} "
                            f"encounter={fetch_result.candidate.encounter_key} "
                            f"report={fetch_result.candidate.report_code} "
                            f"fight={fight_id} "
                            f"player={player_label} "
                            f"job={player.get('job')} "
                            f"error={type(fetch_result.error).__name__}: {fetch_result.error}"
                        ) from fetch_result.error
                    print(
                        f"  [fetch {fetch_result.index}/{fetch_result.total}] "
                        f"{player_label}:{player.get('job')} error={type(fetch_result.error).__name__}: {fetch_result.error}"
                    )

        client_context = (
            nullcontext(None)
            if worker_count > 1
            else xiv_gcd.XivanalysisPageClient(
                base_url=xiv_gcd.XIVANALYSIS_BASE_URL,
                timeout_ms=max(5_000, args.page_timeout_ms),
                retries=max(1, args.retries),
                headful=args.headful,
                locale="en-US",
            )
        )
        with client_context as client:
            for fight_index, group in enumerate(selected, start=1):
                print(f"[{fight_index}/{len(selected)}] 比對 {group.label}，玩家 {len(group.candidates)} 位。")
                fight_result = {
                    "encounter_key": group.encounter_key,
                    "encounter_name": group.encounter_name,
                    "category": group.category,
                    "report_code": group.report_code,
                    "fight_id": group.fight_id,
                    "players": [],
                }
                for candidate in group.candidates:
                    processed_players += 1
                    fetch_result = prefetched_results.get(id(candidate))
                    player_result = compare_candidate(
                        client,
                        candidate,
                        checked_at_iso=checked_at_iso,
                        tolerance=max(0.0, args.tolerance),
                        apply=bool(args.apply),
                        apply_all_checked=bool(args.apply and args.apply_all_checked),
                        local_mode=args.local_mode,
                        local_fallback=local_fallback,
                        fetched_percent=None if fetch_result is None else fetch_result.percent,
                        fetched_url=None if fetch_result is None else fetch_result.url,
                        fetched_error=None if fetch_result is None else fetch_result.error,
                    )
                    player_result_index = len(fight_result["players"])
                    fight_result["players"].append(player_result)
                    if player_result["state"] == "matched":
                        matched += 1
                    elif player_result["state"] == "mismatch":
                        mismatched += 1
                        if player_result.get("applied"):
                            changed_encounter_keys.add(group.encounter_key)
                    else:
                        errors += 1
                        error_entries.append(
                            {
                                "fight_result": fight_result,
                                "player_index": player_result_index,
                                "candidate": candidate,
                            }
                        )
                    if player_result.get("applied"):
                        changed_encounter_keys.add(group.encounter_key)
                    print(
                        f"  [{processed_players}/{total_players}] "
                        f"{player_result.get('player')}:{player_result.get('job')} "
                        f"{player_result['state']} "
                        f"local={player_result.get('current_percent')} "
                        f"xiv={player_result.get('xivanalysis_percent')} "
                        f"diff={player_result.get('difference')}"
                    )
                    if worker_count <= 1 and args.delay_ms > 0 and processed_players < total_players:
                        time.sleep(args.delay_ms / 1000)
                report["fights"].append(fight_result)

    for retry_pass in range(1, max(0, args.error_retry_passes) + 1):
        if not error_entries:
            break

        pending_entries = error_entries
        error_entries = []
        print(f"錯誤重試第 {retry_pass} 輪：待重試 {len(pending_entries)} 位玩家。")
        with xiv_gcd.XivanalysisPageClient(
            base_url=xiv_gcd.XIVANALYSIS_BASE_URL,
            timeout_ms=max(5_000, args.page_timeout_ms),
            retries=max(1, args.retries),
            headful=args.headful,
            locale="en-US",
        ) as client:
            for retry_index, entry in enumerate(pending_entries, start=1):
                candidate = entry["candidate"]
                retry_result = compare_candidate(
                    client,
                    candidate,
                    checked_at_iso=checked_at_iso,
                    tolerance=max(0.0, args.tolerance),
                    apply=bool(args.apply),
                    apply_all_checked=bool(args.apply and args.apply_all_checked),
                    local_mode=args.local_mode,
                    local_fallback=local_fallback,
                )
                entry["fight_result"]["players"][entry["player_index"]] = retry_result
                if retry_result["state"] == "matched":
                    matched += 1
                    errors -= 1
                elif retry_result["state"] == "mismatch":
                    mismatched += 1
                    errors -= 1
                    if retry_result.get("applied"):
                        changed_encounter_keys.add(candidate.encounter_key)
                else:
                    error_entries.append(entry)
                if retry_result.get("applied"):
                    changed_encounter_keys.add(candidate.encounter_key)
                print(
                    f"  [retry {retry_pass}:{retry_index}/{len(pending_entries)}] "
                    f"{retry_result.get('player')}:{retry_result.get('job')} "
                    f"{retry_result['state']} "
                    f"local={retry_result.get('current_percent')} "
                    f"xiv={retry_result.get('xivanalysis_percent')} "
                    f"diff={retry_result.get('difference')}"
                )
                if args.error_retry_delay_ms > 0 and retry_index < len(pending_entries):
                    time.sleep(args.error_retry_delay_ms / 1000)

    if args.apply:
        write_changed_rankings(changed_encounter_keys, rankings_by_key=rankings_by_key, encounters=encounters)

    report["summary"] = {
        "matched": matched,
        "mismatched": mismatched,
        "errors": errors,
        "applied": bool(args.apply),
        "apply_all_checked": bool(args.apply and args.apply_all_checked),
        "changed_encounter_keys": sorted(changed_encounter_keys),
    }
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已輸出稽核報告：{report_path}")
    print(f"比對完成：相符 {matched}，不相符 {mismatched}，錯誤 {errors}。")
    return 0 if errors == 0 and mismatched == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
