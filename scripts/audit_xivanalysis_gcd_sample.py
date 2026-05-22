from __future__ import annotations

import argparse
import json
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import backfill_gcd_coverage as local_gcd  # noqa: E402
import backfill_gcd_coverage_xivanalysis as xiv_gcd  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


DEFAULT_CATEGORIES = ("零式", "極", "幻")
DEFAULT_REPORT_PATH = PROJECT_ROOT / "docs" / "gcd_xivanalysis_audit_latest.json"
LOCAL_MODE_STORED = "stored"
LOCAL_MODE_RECOMPUTE = "recompute"


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


def sample_fights(fights: list[FightGroup], *, sample_size: int, seed: str) -> list[FightGroup]:
    if sample_size >= len(fights):
        return list(fights)
    rng = random.Random(seed)
    return sorted(rng.sample(fights, sample_size), key=lambda group: (group.encounter_key, group.report_code, group.fight_id))


def compare_candidate(
    client: xiv_gcd.XivanalysisPageClient,
    candidate: local_gcd.GcdCandidate,
    *,
    checked_at_iso: str,
    tolerance: float,
    apply: bool,
    local_mode: str,
    local_fallback: xiv_gcd.LocalGcdFallback | None,
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
    url = xiv_gcd.build_xivanalysis_url(candidate)
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
            )
            if key in local_coverage
        }
    try:
        xiv_percent, _ = client.fetch_gcd_percent(candidate)
    except Exception as error:  # noqa: BLE001
        result["state"] = "error"
        result["error"] = f"{type(error).__name__}: {error}"
        return result

    difference = None if before is None else round(before - xiv_percent, 2)
    mismatch = before is None or abs(difference or 0) > tolerance
    result.update(
        {
            "state": "mismatch" if mismatch else "matched",
            "xivanalysis_percent": round(xiv_percent, 2),
            "difference": difference,
        }
    )
    if mismatch and apply:
        xiv_gcd.apply_xivanalysis_coverage(
            candidate,
            percent=xiv_percent,
            url=url,
            checked_at_iso=checked_at_iso,
        )
        result["applied"] = True
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
    parser.add_argument("--sample-size", type=int, default=100, help="抽樣戰鬥組數。")
    parser.add_argument("--seed", default="2026-05-22", help="抽樣 seed，固定後可重現同一批戰鬥。")
    parser.add_argument("--categories", nargs="+", default=list(DEFAULT_CATEGORIES), help="要抽樣的副本分類。")
    parser.add_argument("--tolerance", type=float, default=1.0, help="允許差異百分點，超過才視為不相符。")
    parser.add_argument("--apply", action="store_true", help="將不相符玩家改寫為 xivanalysis 頁面值。")
    parser.add_argument(
        "--local-mode",
        choices=[LOCAL_MODE_STORED, LOCAL_MODE_RECOMPUTE],
        default=LOCAL_MODE_RECOMPUTE,
        help="stored 使用已保存的 GCD；recompute 重新查 FFLogs Casts graph 並用本地演算法計算。",
    )
    parser.add_argument("--delay-ms", type=int, default=2500, help="每位玩家查詢後的延遲，避免 xivanalysis 限流。")
    parser.add_argument("--page-timeout-ms", type=int, default=90_000, help="xivanalysis 單頁逾時。")
    parser.add_argument("--retries", type=int, default=1, help="xivanalysis 單頁重試次數。")
    parser.add_argument("--report-path", default=str(DEFAULT_REPORT_PATH), help="輸出的 JSON 稽核報告路徑。")
    parser.add_argument("--headful", action="store_true", help="以有畫面模式開啟 Chromium，僅供人工除錯。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    categories = {str(category) for category in args.categories}
    encounters = local_gcd.load_all_encounters()
    fights, rankings_by_key = collect_fight_groups(encounters, categories=categories)
    selected = sample_fights(fights, sample_size=max(0, args.sample_size), seed=str(args.seed))
    total_players = sum(len(group.candidates) for group in selected)
    checked_at_iso = local_gcd.milliseconds_to_iso(time.time() * 1000)

    print(f"可抽樣戰鬥組數：{len(fights)}")
    print(f"本輪抽樣戰鬥組數：{len(selected)}")
    print(f"本輪需比對玩家數：{total_players}")
    print(f"分類：{', '.join(sorted(categories))}")
    print(f"seed：{args.seed}")
    print(f"差異容忍值：±{args.tolerance:.2f} 個百分點")
    print(f"本地值來源：{args.local_mode}")
    print(f"寫回修正：{'是' if args.apply else '否'}")

    report: dict[str, Any] = {
        "schema_version": 1,
        "seed": args.seed,
        "categories": sorted(categories),
        "sample_size": len(selected),
        "player_count": total_players,
        "tolerance": args.tolerance,
        "local_mode": args.local_mode,
        "apply": bool(args.apply),
        "checked_at_iso": checked_at_iso,
        "fights": [],
        "summary": {},
    }

    changed_encounter_keys: set[str] = set()
    matched = 0
    mismatched = 0
    errors = 0
    processed_players = 0
    local_fallback = xiv_gcd.LocalGcdFallback() if args.local_mode == LOCAL_MODE_RECOMPUTE else None

    with xiv_gcd.XivanalysisPageClient(
        base_url=xiv_gcd.XIVANALYSIS_BASE_URL,
        timeout_ms=max(5_000, args.page_timeout_ms),
        retries=max(1, args.retries),
        headful=args.headful,
        locale="en-US",
    ) as client:
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
                player_result = compare_candidate(
                    client,
                    candidate,
                    checked_at_iso=checked_at_iso,
                    tolerance=max(0.0, args.tolerance),
                    apply=bool(args.apply),
                    local_mode=args.local_mode,
                    local_fallback=local_fallback,
                )
                fight_result["players"].append(player_result)
                if player_result["state"] == "matched":
                    matched += 1
                elif player_result["state"] == "mismatch":
                    mismatched += 1
                    if player_result.get("applied"):
                        changed_encounter_keys.add(group.encounter_key)
                else:
                    errors += 1
                print(
                    f"  [{processed_players}/{total_players}] "
                    f"{player_result.get('player')}:{player_result.get('job')} "
                    f"{player_result['state']} "
                    f"local={player_result.get('current_percent')} "
                    f"xiv={player_result.get('xivanalysis_percent')} "
                    f"diff={player_result.get('difference')}"
                )
                if args.delay_ms > 0 and processed_players < total_players:
                    time.sleep(args.delay_ms / 1000)
            report["fights"].append(fight_result)

    if args.apply:
        write_changed_rankings(changed_encounter_keys, rankings_by_key=rankings_by_key, encounters=encounters)

    report["summary"] = {
        "matched": matched,
        "mismatched": mismatched,
        "errors": errors,
        "applied": bool(args.apply),
        "changed_encounter_keys": sorted(changed_encounter_keys),
    }
    report_path = Path(args.report_path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已輸出稽核報告：{report_path}")
    print(f"比對完成：相符 {matched}，不相符 {mismatched}，錯誤 {errors}。")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
