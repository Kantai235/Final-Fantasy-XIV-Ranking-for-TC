from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402


read_json = getattr(fflogs, "\u8b80\u53d6_json")
ranking_path = getattr(fflogs, "\u6392\u884c\u699c\u6a94\u6848\u8def\u5f91")
load_ranking_file = getattr(fflogs, "\u8b80\u53d6\u6392\u884c\u699c\u6a94\u6848")
write_ranking_file = getattr(fflogs, "\u5beb\u5165\u6392\u884c\u699c\u6a94\u6848")
report_is_hidden = getattr(fflogs, "\u5831\u544a\u5df2\u6a19\u8a18\u96b1\u85cf")
mark_ranking_report_hidden = getattr(fflogs, "\u6a19\u8a18\u6392\u884c\u699c\u5831\u544a\u96b1\u85cf")
query_report_status = getattr(fflogs, "\u67e5\u8a62\u5831\u544a\u76ee\u524d\u72c0\u614b")
read_credentials = getattr(fflogs, "\u8b80\u53d6\u8a8d\u8b49\u8a2d\u5b9a")
auth_pool_class = getattr(fflogs, "FFLogs\u8a8d\u8b49\u6c60")
report_access_error_class = getattr(fflogs, "FFLogs\u5831\u544a\u5b58\u53d6\u932f\u8aa4")
report_status_unavailable_class = getattr(fflogs, "FFLogs\u5831\u544a\u72c0\u614b\u4e0d\u53ef\u5b58\u53d6\u932f\u8aa4")
hidden_reason_inaccessible = getattr(fflogs, "\u5831\u544a\u7121\u6cd5\u5b58\u53d6\u96b1\u85cf\u539f\u56e0")


@dataclass
class MissingGcdReportCandidate:
    report_code: str
    sort_time: float = 0
    encounter_keys: set[str] = field(default_factory=set)
    missing_player_count: int = 0
    fight_count: int = 0

    @property
    def label(self) -> str:
        encounters = ",".join(sorted(self.encounter_keys))
        return (
            f"{self.report_code} encounters={encounters} "
            f"missing_players={self.missing_player_count} fights={self.fight_count}"
        )


def to_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def first_number(*values: Any) -> float | None:
    for value in values:
        number = to_number(value)
        if number is not None:
            return number
    return None


def load_all_encounters() -> dict[str, dict[str, Any]]:
    raw = read_json(PROJECT_ROOT / "config" / "encounters.json", [])
    if not isinstance(raw, list):
        raise RuntimeError("config/encounters.json 必須是陣列。")

    encounters: dict[str, dict[str, Any]] = {}
    for item in raw:
        if not isinstance(item, dict):
            continue

        key = item.get("key")
        if not key or not item.get("name"):
            continue
        if item.get("zone_id") is None or item.get("encounter_id") is None or item.get("difficulty") is None:
            continue

        encounter = dict(item)
        encounter["zone_id"] = int(encounter["zone_id"])
        encounter["encounter_id"] = int(encounter["encounter_id"])
        encounter["difficulty"] = int(encounter["difficulty"])
        encounters[str(key)] = encounter

    return encounters


def report_sort_time(report: dict[str, Any]) -> float:
    # 這個腳本只做 report 可讀性巡檢，不需要 fight 級排序精度；report 時間不足時才退回 fight 紀錄時間。
    values = [
        first_number(report.get("report_start_time"), report.get("startTime")),
        first_number(report.get("report_end_time"), report.get("endTime")),
        first_number(report.get("fetched_at")),
    ]
    for fight in report.get("fights") or []:
        if not isinstance(fight, dict):
            continue
        values.append(first_number(fight.get("recorded_at"), fight.get("recordedAt")))
    return max((value for value in values if value is not None), default=0)


def player_needs_gcd_status_check(player: dict[str, Any]) -> bool:
    # 這個一次性排查關心「玩家沒有可用 GCD 資料」：
    # key 不存在代表從未補算；值為 null 則代表曾被補算流程判定不可用，但 report 本身尚未 hidden。
    return "gcd_coverage" not in player or player.get("gcd_coverage") is None


def report_missing_gcd_summary(report: dict[str, Any]) -> tuple[int, int]:
    missing_players = 0
    fight_ids: set[str] = set()
    for fight in report.get("fights") or []:
        if not isinstance(fight, dict):
            continue
        fight_missing_players = 0
        for player in fight.get("players") or []:
            if isinstance(player, dict) and player_needs_gcd_status_check(player):
                fight_missing_players += 1
        if fight_missing_players:
            missing_players += fight_missing_players
            fight_ids.add(str(fight.get("fight_id") or fight.get("id") or len(fight_ids) + 1))
    return missing_players, len(fight_ids)


def scan_missing_gcd_report_candidates(
    encounters: dict[str, dict[str, Any]],
) -> tuple[list[MissingGcdReportCandidate], int, dict[str, dict[str, Any]]]:
    # 候選以 report_code 合併，避免同一份 report 橫跨多個副本時重複呼叫 FFLogs。
    candidates: dict[str, MissingGcdReportCandidate] = {}
    rankings_by_key: dict[str, dict[str, Any]] = {}
    total_missing_players = 0

    for key, encounter in sorted(encounters.items()):
        if not ranking_path(encounter).exists():
            continue

        ranking = load_ranking_file(encounter)
        rankings_by_key[key] = ranking
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for fallback_report_code, report in reports.items():
            if not isinstance(report, dict) or report_is_hidden(report):
                continue

            missing_players, fight_count = report_missing_gcd_summary(report)
            if missing_players <= 0:
                continue

            report_code = str(report.get("report_code") or fallback_report_code)
            candidate = candidates.setdefault(report_code, MissingGcdReportCandidate(report_code=report_code))
            candidate.encounter_keys.add(key)
            candidate.missing_player_count += missing_players
            candidate.fight_count += fight_count
            candidate.sort_time = max(candidate.sort_time, report_sort_time(report))
            total_missing_players += missing_players

    selected = sorted(candidates.values(), key=lambda item: (item.sort_time, item.report_code), reverse=True)
    return selected, total_missing_players, rankings_by_key


def candidate_matches_filters(candidate: MissingGcdReportCandidate, args: argparse.Namespace) -> bool:
    if args.report_code and candidate.report_code != args.report_code:
        return False
    if args.encounter_key and args.encounter_key not in candidate.encounter_keys:
        return False
    return True


def mark_report_hidden_across_rankings(
    report_code: str,
    rankings_by_key: dict[str, dict[str, Any]],
    error: Exception,
) -> set[str]:
    changed_keys: set[str] = set()
    for key, ranking in rankings_by_key.items():
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict) or report_code not in reports:
            continue

        if mark_ranking_report_hidden(
            ranking,
            report_code,
            原因=hidden_reason_inaccessible,
            來源="check_missing_gcd_report_status",
            詳細原因=str(error),
        ):
            changed_keys.add(key)

    return changed_keys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="只檢查沒有可用 gcd_coverage 的既有 report 是否仍可存取，無法存取時標記 hidden。"
    )
    parser.add_argument("--limit", type=int, default=0, help="最多檢查幾個 report code；0 代表全部。")
    parser.add_argument("--dry-run", action="store_true", help="只列出候選與統計，不呼叫 FFLogs 也不寫檔。")
    parser.add_argument("--report-code", help="只檢查指定 report code。")
    parser.add_argument("--encounter-key", help="只檢查包含指定副本 key 的候選。")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    encounters = load_all_encounters()
    candidates, total_missing_players, rankings_by_key = scan_missing_gcd_report_candidates(encounters)
    candidates = [candidate for candidate in candidates if candidate_matches_filters(candidate, args)]
    selected = candidates if args.limit <= 0 else candidates[: args.limit]

    print(f"缺少 gcd_coverage key 或值為 null 的玩家筆數：{total_missing_players}")
    print(f"需要檢查狀態的 report code 數：{len(candidates)}")
    print(f"本輪選取 report code 數：{len(selected)}")
    for index, candidate in enumerate(selected[:20], start=1):
        print(f"{index:>2}. {candidate.label} sort_time={int(candidate.sort_time)}")
    if len(selected) > 20:
        print(f"... 另有 {len(selected) - 20} 個 report code。")

    if args.dry_run or not selected:
        return 0

    session = fflogs.requests.Session()
    auth_pool = auth_pool_class(session, read_credentials())
    changed_keys: set[str] = set()
    accessible_count = 0
    hidden_report_codes: set[str] = set()
    failed_count = 0

    for index, candidate in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] 檢查 report 狀態：{candidate.report_code}")
        try:
            query_report_status(session, auth_pool, candidate.report_code)
        except (report_access_error_class, report_status_unavailable_class) as error:
            changed = mark_report_hidden_across_rankings(candidate.report_code, rankings_by_key, error)
            changed_keys.update(changed)
            hidden_report_codes.add(candidate.report_code)
            print(
                f"[{index}/{len(selected)}] → 無法存取，已標記 {len(changed)} 個副本中的 report："
                f"{candidate.report_code}"
            )
        except Exception as error:  # noqa: BLE001
            failed_count += 1
            print(f"[{index}/{len(selected)}] → 檢查失敗，暫不標記 hidden：{error}", file=sys.stderr)
        else:
            accessible_count += 1
            print(f"[{index}/{len(selected)}] → report 仍可讀取。")

    for key in sorted(changed_keys):
        encounter = encounters.get(key)
        ranking = rankings_by_key.get(key)
        if not encounter or not ranking:
            continue
        write_ranking_file(encounter, ranking)
        print(f"已寫入 hidden report 更新：{key}")

    print(
        "缺 GCD report 狀態排查完成："
        f"可讀 {accessible_count} 個，"
        f"標記 hidden {len(hidden_report_codes)} 個，"
        f"檢查失敗 {failed_count} 個。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
