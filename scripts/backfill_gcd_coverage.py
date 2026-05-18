from __future__ import annotations

import argparse
import csv
import io
import os
import statistics
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import fetch_fflogs as fflogs  # noqa: E402


# GCD 覆蓋率只保存衍生結果，不能把 Casts raw events 寫入 repo。
# 技能分類來自 XIVAPI 維護的 FFXIV datamining Action.csv；腳本只在記憶體中解析 action id、
# cast、recast 與分類，避免整份遊戲資料落地造成 repo 膨脹。
# 注意：Action.csv 的 Recast100ms 對部分技能代表「技能冷卻」而不是實際 GCD 鎖定時間。
# 例如毒蛇劍士 Vicewinder 有 40 秒技能冷卻，但按下後實際讓 GCD 滾動約 3 秒；忍者 mudra /
# ninjutsu 則在 Action.csv 內屬於 Ability，仍會被 xivanalysis 視為 GCD 覆蓋率的一部分。
# 因此下方以小型 allow-list 保存這類業務例外，避免為了少數技能把整份遊戲資料或第三方網站輸出落地。
ACTION_CSV_URL = "https://raw.githubusercontent.com/xivapi/ffxiv-datamining/master/csv/en/Action.csv"
GCD_ACTION_CATEGORY_IDS = {2, 3}  # 2=Spell, 3=Weaponskill
GCD_CALCULATION_VERSION = 5
GCD_SOURCE = "fflogs_casts_graph"
MIN_REASONABLE_EPOCH_MS = 946684800000
DEFAULT_GCD_BACKFILL_LIMIT = 2000
BASE_GCD_MS = 2500
RECAST_TIGHT_DELTA_MIN_RATIO = 0.8
RECAST_TIGHT_DELTA_MAX_RATIO = 1.05
RECAST_INTERVAL_BATCH_MS = 45
RECAST_INTERVAL_MODE_RADIUS = 2

# xivanalysis 的 FFLogs legacy adapter 會把部分「常駐或自給自足的加速」從 raw GCD 間隔中拆開：
# - 忍者與武僧的職業加速視為整場常駐倍率。
# - 毒蛇劍士、武士等由技能維持的加速 buff，只影響 buff 生效後的 GCD。
# 本專案仍只讀 FFLogs Casts graph，因此 status 視窗以「會套用該 status 的技能」推回來；這讓開場第一輪、
# buff 斷掉後的第一個 GCD 不會錯用已加速的 recast 估計。
JOB_SPEED_MODIFIERS = {
    "Monk": 0.80,
    "Ninja": 0.85,
}


@dataclass(frozen=True)
class SpeedStatusRule:
    action_ids: frozenset[int]
    duration_ms: int
    modifier: float
    label: str


SPEED_STATUS_RULES = [
    SpeedStatusRule(
        action_ids=frozenset({34609, 34617, 34622, 34625}),
        duration_ms=40000,
        modifier=0.85,
        label="Viper Swiftscaled",
    ),
    SpeedStatusRule(
        action_ids=frozenset({7479, 7485}),
        duration_ms=40000,
        modifier=0.87,
        label="Samurai Fuka",
    ),
    SpeedStatusRule(
        action_ids=frozenset({136}),
        duration_ms=15000,
        modifier=0.80,
        label="White Mage Presence of Mind",
    ),
]


@dataclass(frozen=True)
class GcdActionOverride:
    gcd_recast_ms: int
    speed_adjusted: bool


@dataclass(frozen=True)
class SpeedModifierWindow:
    start_ms: float
    end_ms: float
    modifier: float
    label: str


@dataclass(frozen=True)
class RecastTimingEstimate:
    multiplier_by_base: dict[int, float]
    dominant_speed_modifier_by_base: dict[int, float]


# 這些 action id 來自 xivanalysis 的 Dawntrail action 定義與 FFLogs Casts graph 實測。
# key 只在 Action.csv 不能直接表達「on GCD」或「GCD recast」時出現：
# - 忍者 mudra / ninjutsu：Action.csv 類別是 Ability，但它們會佔用 GCD 流程，漏掉會讓 NIN
#   覆蓋率低估約二十個百分點。
# - 毒蛇劍士特殊 GCD：部分技能同時有技能冷卻與 GCD 鎖定時間，必須使用 gcd_recast_ms 而非
#   Action.csv 的 Recast100ms，否則延遲空窗會被 40 秒冷卻誤判成仍在滾 GCD。
GCD_ACTION_OVERRIDES: dict[int, GcdActionOverride] = {
    # Ninja mudras.
    2259: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),  # Ten
    2261: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),  # Chi
    2263: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),  # Jin
    18805: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),  # Ten (Kassatsu)
    18806: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),  # Chi (Kassatsu)
    18807: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),  # Jin (Kassatsu)
    # Ninja ninjutsu and Ten Chi Jin variants.
    2260: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Ninjutsu
    2265: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Fuma Shuriken
    2266: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Katon
    2267: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Raiton
    2268: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Hyoton
    2269: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Huton
    2270: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Doton
    2271: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Suiton
    2272: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Rabbit Medium
    16491: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Goka Mekkyaku
    16492: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Hyosho Ranryu
    18873: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),  # Fuma Shuriken (TCJ)
    18874: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),  # Fuma Shuriken (TCJ)
    18875: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),  # Fuma Shuriken (TCJ)
    18876: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),  # Katon (TCJ)
    18877: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),  # Raiton (TCJ)
    18878: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),  # Hyoton (TCJ)
    18879: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Huton (TCJ)
    18880: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Doton (TCJ)
    18881: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),  # Suiton (TCJ)
    # Viper GCDs whose Action.csv recast is a cooldown or whose GCD lock differs from the default 2.5s.
    34620: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=False),  # Vicewinder
    34623: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=False),  # Vicepit
    34621: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),  # Hunter's Coil
    34622: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),  # Swiftskin's Coil
    34624: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),  # Hunter's Den
    34625: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),  # Swiftskin's Den
    34633: GcdActionOverride(gcd_recast_ms=3500, speed_adjusted=True),  # Uncoiled Fury
    34626: GcdActionOverride(gcd_recast_ms=2200, speed_adjusted=True),  # Reawaken
    34627: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),  # First Generation
    34628: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),  # Second Generation
    34629: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),  # Third Generation
    34630: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),  # Fourth Generation
    34631: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),  # Ouroboros
}

read_json = getattr(fflogs, "\u8b80\u53d6_json")
ranking_path = getattr(fflogs, "\u6392\u884c\u699c\u6a94\u6848\u8def\u5f91")
load_ranking_file = getattr(fflogs, "\u8b80\u53d6\u6392\u884c\u699c\u6a94\u6848")
write_ranking_file = getattr(fflogs, "\u5beb\u5165\u6392\u884c\u699c\u6a94\u6848")
read_credentials = getattr(fflogs, "\u8b80\u53d6\u8a8d\u8b49\u8a2d\u5b9a")
auth_pool_class = getattr(fflogs, "FFLogs\u8a8d\u8b49\u6c60")
execute_graphql = getattr(fflogs, "\u57f7\u884c_graphql")
report_access_error_class = getattr(fflogs, "FFLogs\u5831\u544a\u5b58\u53d6\u932f\u8aa4")
milliseconds_to_iso = getattr(fflogs, "\u6beb\u79d2\u8f49_iso")


@dataclass(frozen=True)
class ActionMetadata:
    action_id: int
    name: str | None
    action_category_id: int | None
    cast_ms: int
    recast_ms: int
    gcd_recast_ms: int | None = None
    is_gcd_override: bool | None = None
    recast_speed_adjusted: bool = True

    @property
    def is_gcd(self) -> bool:
        if self.is_gcd_override is not None:
            return self.is_gcd_override
        return self.action_category_id in GCD_ACTION_CATEGORY_IDS and self.recast_ms >= 1500

    @property
    def effective_recast_ms(self) -> int:
        return self.gcd_recast_ms if self.gcd_recast_ms is not None else self.recast_ms


@dataclass
class GcdCandidate:
    encounter_key: str
    encounter: dict[str, Any]
    ranking: dict[str, Any]
    report_code: str
    report: dict[str, Any]
    fight: dict[str, Any]
    player: dict[str, Any]
    sort_time: float

    @property
    def label(self) -> str:
        name = self.player.get("name") or self.player.get("character_name") or "未知角色"
        server = self.player.get("server") or "未知伺服器"
        job = self.player.get("job") or "未知職業"
        return f"{self.encounter_key} {self.report_code} fight={self.fight.get('fight_id')} {name}@{server}:{job}"


class ActionMetadataStore:
    def __init__(self, source_url: str = ACTION_CSV_URL) -> None:
        self.source_url = source_url
        self._metadata_by_id: dict[int, ActionMetadata] | None = None

    def get(self, action_id: int) -> ActionMetadata | None:
        if self._metadata_by_id is None:
            self._metadata_by_id = self._load_action_csv()
        return self._metadata_by_id.get(action_id)

    def preload(self) -> None:
        if self._metadata_by_id is None:
            self._metadata_by_id = self._load_action_csv()

    def _load_action_csv(self) -> dict[int, ActionMetadata]:
        try:
            request = urllib.request.Request(
                self.source_url,
                headers={"User-Agent": "ffxiv-tc-ranking-gcd-backfill/1.0"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_csv = response.read().decode("utf-8-sig")
        except (OSError, urllib.error.URLError) as error:
            raise RuntimeError(f"無法下載 GCD 技能資料：{self.source_url}") from error

        metadata_by_id: dict[int, ActionMetadata] = {}
        reader = csv.DictReader(io.StringIO(raw_csv))
        for row in reader:
            action_id = to_int(row.get("#"))
            if action_id is None:
                continue

            override = GCD_ACTION_OVERRIDES.get(action_id)
            metadata_by_id[action_id] = ActionMetadata(
                action_id=action_id,
                name=row.get("Name") or None,
                action_category_id=to_int(row.get("ActionCategory")),
                cast_ms=(to_int(row.get("Cast100ms")) or 0) * 100,
                recast_ms=(to_int(row.get("Recast100ms")) or 0) * 100,
                gcd_recast_ms=override.gcd_recast_ms if override else None,
                is_gcd_override=True if override else None,
                recast_speed_adjusted=override.speed_adjusted if override else True,
            )

        if not metadata_by_id:
            raise RuntimeError("GCD 技能資料為空，無法計算覆蓋率。")
        return metadata_by_id


def to_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", ""))
        except ValueError:
            return None
    return None


def to_int(value: Any) -> int | None:
    number = to_number(value)
    if number is None:
        return None
    return int(number)


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


def fight_absolute_time(report_start_time: float | None, value: Any) -> float | None:
    number = to_number(value)
    if number is None:
        return None
    if number >= MIN_REASONABLE_EPOCH_MS:
        return number
    if report_start_time is not None:
        return report_start_time + number
    return None


def candidate_sort_time(report: dict[str, Any], fight: dict[str, Any]) -> float:
    report_start_time = first_number(report.get("report_start_time"), report.get("startTime"))
    values = [
        fight_absolute_time(report_start_time, first_number(fight.get("end_time"), fight.get("endTime"))),
        first_number(fight.get("recorded_at"), fight.get("recordedAt")),
        first_number(report.get("report_end_time"), report.get("endTime")),
        first_number(report.get("report_start_time"), report.get("startTime")),
    ]
    return max((value for value in values if value is not None), default=0)


def player_is_rankable(player: dict[str, Any]) -> bool:
    return bool(
        (player.get("name") or player.get("character_name"))
        and player.get("server")
        and player.get("job")
        and player.get("dps") is not None
    )


def player_has_query_context(fight: dict[str, Any], player: dict[str, Any]) -> bool:
    return (
        to_int(fight.get("fight_id")) is not None
        and first_number(fight.get("start_time"), fight.get("startTime")) is not None
        and first_number(fight.get("end_time"), fight.get("endTime")) is not None
        and to_int(player.get("fflogs_id")) is not None
    )


def gcd_coverage_version(player: dict[str, Any]) -> int | None:
    coverage = player.get("gcd_coverage")
    if not isinstance(coverage, dict):
        return None
    return to_int(coverage.get("calculation_version"))


def scan_candidates(
    encounters: dict[str, dict[str, Any]],
    *,
    include_current: bool = False,
) -> tuple[list[GcdCandidate], int, int, int, dict[str, dict[str, Any]]]:
    candidates: list[GcdCandidate] = []
    missing_key_count = 0
    stale_key_count = 0
    null_key_count = 0
    rankings_by_key: dict[str, dict[str, Any]] = {}

    for key, encounter in sorted(encounters.items()):
        if not ranking_path(encounter).exists():
            continue

        ranking = load_ranking_file(encounter)
        rankings_by_key[key] = ranking
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for fallback_report_code, report in reports.items():
            if not isinstance(report, dict):
                continue

            report_code = str(report.get("report_code") or fallback_report_code)
            for fight in report.get("fights") or []:
                if not isinstance(fight, dict):
                    continue

                for player in fight.get("players") or []:
                    if not isinstance(player, dict) or not player_is_rankable(player):
                        continue

                    if "gcd_coverage" not in player:
                        if not player_has_query_context(fight, player):
                            continue
                        missing_key_count += 1
                        candidates.append(
                            GcdCandidate(
                                encounter_key=key,
                                encounter=encounter,
                                ranking=ranking,
                                report_code=report_code,
                                report=report,
                                fight=fight,
                                player=player,
                                sort_time=candidate_sort_time(report, fight),
                            )
                        )
                    elif player.get("gcd_coverage") is None:
                        null_key_count += 1
                    elif gcd_coverage_version(player) != GCD_CALCULATION_VERSION:
                        if not player_has_query_context(fight, player):
                            continue
                        stale_key_count += 1
                        candidates.append(
                            GcdCandidate(
                                encounter_key=key,
                                encounter=encounter,
                                ranking=ranking,
                                report_code=report_code,
                                report=report,
                                fight=fight,
                                player=player,
                                sort_time=candidate_sort_time(report, fight),
                            )
                        )
                    elif include_current:
                        if not player_has_query_context(fight, player):
                            continue
                        candidates.append(
                            GcdCandidate(
                                encounter_key=key,
                                encounter=encounter,
                                ranking=ranking,
                                report_code=report_code,
                                report=report,
                                fight=fight,
                                player=player,
                                sort_time=candidate_sort_time(report, fight),
                            )
                        )

    candidates.sort(key=lambda candidate: (candidate.sort_time, candidate.report_code), reverse=True)
    return candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key


def query_casts_graph(session: Any, auth_pool: Any, candidate: GcdCandidate) -> dict[str, Any]:
    fight_id = to_int(candidate.fight.get("fight_id"))
    source_id = to_int(candidate.player.get("fflogs_id"))
    start_time = first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
    end_time = first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
    if fight_id is None or source_id is None or start_time is None or end_time is None:
        raise RuntimeError("缺少 fight_id、sourceID 或 fight 時間窗，無法查詢 Casts graph。")

    query = f"""
    query($code: String!, $sourceID: Int!) {{
      reportData {{
        report(code: $code) {{
          graph(
            dataType: Casts,
            fightIDs: [{fight_id}],
            startTime: {start_time},
            endTime: {end_time},
            sourceID: $sourceID
          )
        }}
      }}
    }}
    """
    data = execute_graphql(session, auth_pool, query, {"code": candidate.report_code, "sourceID": source_id})
    graph = (((data.get("reportData") or {}).get("report") or {}).get("graph") or {}).get("data")
    if not isinstance(graph, dict):
        raise RuntimeError("FFLogs Casts graph 回傳格式不正確。")
    return graph


def query_fight_casts_graph(session: Any, auth_pool: Any, candidate: GcdCandidate) -> dict[str, Any]:
    fight_id = to_int(candidate.fight.get("fight_id"))
    start_time = first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
    end_time = first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法查詢整場 Casts graph。")

    query = f"""
    query($code: String!) {{
      reportData {{
        report(code: $code) {{
          graph(
            dataType: Casts,
            fightIDs: [{fight_id}],
            startTime: {start_time},
            endTime: {end_time}
          )
        }}
      }}
    }}
    """
    data = execute_graphql(session, auth_pool, query, {"code": candidate.report_code})
    graph = (((data.get("reportData") or {}).get("report") or {}).get("graph") or {}).get("data")
    if not isinstance(graph, dict):
        raise RuntimeError("FFLogs 整場 Casts graph 回傳格式不正確。")
    return graph


def event_source_id(event: dict[str, Any]) -> int | None:
    return to_int(event.get("sourceID"))


def event_action_id(event: dict[str, Any], fallback_action_id: int | None) -> int | None:
    ability = event.get("ability")
    if isinstance(ability, dict):
        action_id = to_int(ability.get("guid"))
        if action_id is not None:
            return action_id
    action_id = to_int(event.get("abilityGameID"))
    if action_id is not None:
        return action_id
    return fallback_action_id


def extract_attempt_from_event_group(
    events: list[dict[str, Any]],
    *,
    fallback_action_id: int | None,
    source_id: int | None,
) -> dict[str, Any] | None:
    if source_id is not None and not any(event_source_id(event) == source_id for event in events):
        return None

    matching_events = [
        event
        for event in events
        if source_id is None or event_source_id(event) == source_id
    ]
    begin_event = next((event for event in matching_events if event.get("type") == "begincast"), None)
    cast_event = next((event for event in matching_events if event.get("type") == "cast"), None)
    if begin_event:
        timestamp = to_number(begin_event.get("timestamp"))
        duration = to_number(begin_event.get("duration")) or 0
        action_id = event_action_id(begin_event, fallback_action_id)
    elif cast_event:
        timestamp = to_number(cast_event.get("timestamp"))
        duration = 0
        action_id = event_action_id(cast_event, fallback_action_id)
    else:
        return None

    if timestamp is None or action_id is None:
        return None

    return {
        "action_id": action_id,
        "timestamp": timestamp,
        "cast_duration_ms": duration,
        "source_id": source_id if source_id is not None else event_source_id(begin_event or cast_event or {}),
    }


def extract_attempts_from_series(series: dict[str, Any], *, source_id: int | None = None) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    events_groups = series.get("events")
    if not isinstance(events_groups, list):
        return attempts

    fallback_action_id = to_int(series.get("guid"))

    for group in events_groups:
        if not isinstance(group, list):
            continue

        events = [event for event in group if isinstance(event, dict)]
        if not events:
            continue

        attempt = extract_attempt_from_event_group(
            events,
            fallback_action_id=fallback_action_id,
            source_id=source_id,
        )
        if attempt is not None:
            attempts.append(attempt)

    return attempts


def extract_all_attempts(graph: dict[str, Any], *, source_id: int | None = None) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for series in graph.get("series") or []:
        if not isinstance(series, dict):
            continue
        attempts.extend(extract_attempts_from_series(series, source_id=source_id))

    attempts.sort(key=lambda attempt: (attempt["timestamp"], attempt["action_id"]))
    return attempts


def extract_gcd_attempts(
    graph: dict[str, Any],
    metadata_store: ActionMetadataStore,
    *,
    source_id: int | None = None,
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for attempt in extract_all_attempts(graph, source_id=source_id):
        action_id = to_int(attempt.get("action_id"))
        if action_id is None:
            continue
        metadata = metadata_store.get(action_id)
        if not metadata or not metadata.is_gcd:
            continue
        attempt["metadata"] = metadata
        attempts.append(attempt)

    attempts.sort(key=lambda attempt: (attempt["timestamp"], attempt["action_id"]))
    return attempts


def merge_speed_modifier_windows(windows: list[SpeedModifierWindow]) -> list[SpeedModifierWindow]:
    merged: list[SpeedModifierWindow] = []
    for window in sorted(windows, key=lambda item: (item.modifier, item.start_ms, item.end_ms, item.label)):
        if (
            not merged
            or merged[-1].modifier != window.modifier
            or merged[-1].label != window.label
            or window.start_ms > merged[-1].end_ms
        ):
            merged.append(window)
            continue

        merged[-1] = SpeedModifierWindow(
            start_ms=merged[-1].start_ms,
            end_ms=max(merged[-1].end_ms, window.end_ms),
            modifier=merged[-1].modifier,
            label=merged[-1].label,
        )
    return sorted(merged, key=lambda item: (item.start_ms, item.end_ms, item.label))


def infer_speed_modifier_windows(
    action_attempts: list[dict[str, Any]],
    *,
    fight_end_time: float | None = None,
) -> list[SpeedModifierWindow]:
    windows: list[SpeedModifierWindow] = []
    for attempt in action_attempts:
        action_id = to_int(attempt.get("action_id"))
        timestamp = to_number(attempt.get("timestamp"))
        if action_id is None or timestamp is None:
            continue

        for rule in SPEED_STATUS_RULES:
            if action_id not in rule.action_ids:
                continue

            end_ms = timestamp + rule.duration_ms
            if fight_end_time is not None:
                end_ms = min(end_ms, fight_end_time)
            if end_ms > timestamp:
                windows.append(
                    SpeedModifierWindow(
                        start_ms=timestamp,
                        end_ms=end_ms,
                        modifier=rule.modifier,
                        label=rule.label,
                    )
                )
    return merge_speed_modifier_windows(windows)


def speed_modifier_at_timestamp(
    timestamp: float,
    *,
    job: str | None,
    speed_windows: list[SpeedModifierWindow],
) -> float:
    modifier = JOB_SPEED_MODIFIERS.get(str(job), 1.0)
    for window in speed_windows:
        # xivanalysis 的 speedStat adapter 用 start < timestamp <= end，避免把「套用加速的那一招」
        # 也反向當成已吃到加速。這對毒蛇劍士與武士開場 GCD 特別重要。
        if window.start_ms < timestamp <= window.end_ms:
            modifier *= window.modifier
    return modifier


def downtime_windows(graph: dict[str, Any]) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for item in graph.get("downtime") or []:
        if not isinstance(item, dict):
            continue
        start = to_number(item.get("startTime"))
        end = to_number(item.get("endTime"))
        if start is None or end is None or end <= start:
            continue
        windows.append((start, end))
    return windows


def overlap_ms(start: float, end: float, windows: list[tuple[float, float]]) -> float:
    total = 0.0
    for window_start, window_end in windows:
        total += max(0.0, min(end, window_end) - max(start, window_start))
    return total


def median_default_speed_multiplier(attempts: list[dict[str, Any]]) -> float:
    ratios: list[float] = []
    for attempt in attempts:
        metadata = attempt.get("metadata")
        if (
            not isinstance(metadata, ActionMetadata)
            or not metadata.recast_speed_adjusted
            or metadata.cast_ms <= 0
        ):
            continue

        cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
        if cast_duration <= 0:
            continue

        ratio = cast_duration / metadata.cast_ms
        if 0.9 <= ratio <= 1.05:
            ratios.append(ratio)

    if not ratios:
        return 1.0
    return statistics.median(ratios)


def round_to_nearest_10_ms(value: float) -> float:
    return int((value / 10) + 0.5) * 10


def floor_to_10_ms(value: float) -> float:
    return int(value // 10) * 10


def estimate_recast_from_xivanalysis_batches(observed_intervals: list[float]) -> float:
    if not observed_intervals:
        return 0.0

    # xivanalysis 的 FFLogs adapter 註解指出 FFLogs timestamps 會以約 45ms 批次落點；
    # 因此它不是直接取最短/最常見的單一 interval，而是先分桶，取眾數桶附近一小段範圍
    # 的加權平均，再四捨五入到遊戲 tooltip 會呈現的 10ms。這比舊版分位數更不容易被
    # 單次低延遲封包或長間隔重開污染，是目前本地計算對齊 xivanalysis ABC 的核心。
    batch_counts: dict[int, int] = {}
    for interval in observed_intervals:
        batch = int(interval // RECAST_INTERVAL_BATCH_MS)
        batch_counts[batch] = batch_counts.get(batch, 0) + 1

    mode_batch = max(batch_counts.items(), key=lambda item: item[1])[0]
    weighted_sum = 0.0
    count_sum = 0
    for batch in range(mode_batch - RECAST_INTERVAL_MODE_RADIUS, mode_batch + RECAST_INTERVAL_MODE_RADIUS + 1):
        count = batch_counts.get(batch, 0)
        smallest_interval = batch * RECAST_INTERVAL_BATCH_MS
        largest_interval = ((batch + 1) * RECAST_INTERVAL_BATCH_MS) - 1
        average_interval = (smallest_interval + largest_interval) / 2
        weighted_sum += average_interval * count
        count_sum += count

    if count_sum <= 0:
        return 0.0
    raw_estimate = weighted_sum / count_sum
    return round_to_nearest_10_ms(raw_estimate)


def infer_recast_timing_by_base(
    attempts: list[dict[str, Any]],
    *,
    job: str | None = None,
    speed_windows: list[SpeedModifierWindow] | None = None,
) -> RecastTimingEstimate:
    # Cast duration 和 recast 會經過不同的遊戲端取整流程；只用 hardcast duration 推 recast
    # 會讓 GCD 覆蓋時間偏高。這裡參照 xivanalysis 的 speedStat adapter：先保留緊貼施放的
    # 相鄰 GCD interval，再以 45ms 批次眾數附近的加權平均估算同一種 base recast。
    # 後續仍會用下一個 GCD timestamp 夾住覆蓋區間，因此短窗加速或即刻詠唱不會被估計值灌水。
    # 忍者 mudra/ninjutsu 這類固定 0.5s/1.0s/1.5s 的 GCD-like Ability 不吃速度估算；否則
    # FFLogs 封包間隔的微小抖動會被誤當成可縮放的 GCD 長度。
    speed_windows = speed_windows or []
    intervals_by_recast: dict[int, list[float]] = {}
    speed_modifier_counts_by_recast: dict[int, dict[float, int]] = {}
    for index, attempt in enumerate(attempts[:-1]):
        metadata = attempt.get("metadata")
        if (
            not isinstance(metadata, ActionMetadata)
            or not metadata.recast_speed_adjusted
            or metadata.effective_recast_ms <= 0
        ):
            continue

        timestamp = to_number(attempt.get("timestamp"))
        next_timestamp = to_number(attempts[index + 1].get("timestamp"))
        if timestamp is None or next_timestamp is None:
            continue

        delta = next_timestamp - timestamp
        ratio = delta / metadata.effective_recast_ms
        if RECAST_TIGHT_DELTA_MIN_RATIO <= ratio <= RECAST_TIGHT_DELTA_MAX_RATIO:
            intervals_by_recast.setdefault(metadata.effective_recast_ms, []).append(delta)
            speed_modifier = speed_modifier_at_timestamp(
                timestamp,
                job=job,
                speed_windows=speed_windows,
            )
            modifier_key = round(speed_modifier, 5)
            counts = speed_modifier_counts_by_recast.setdefault(metadata.effective_recast_ms, {})
            counts[modifier_key] = counts.get(modifier_key, 0) + 1

    multipliers: dict[int, float] = {}
    for recast_ms, intervals in intervals_by_recast.items():
        estimate = estimate_recast_from_xivanalysis_batches(intervals)
        if estimate > 0:
            multipliers[recast_ms] = estimate / recast_ms

    dominant_speed_modifier_by_base: dict[int, float] = {}
    for recast_ms, counts in speed_modifier_counts_by_recast.items():
        if counts:
            dominant_speed_modifier_by_base[recast_ms] = max(counts.items(), key=lambda item: item[1])[0]

    return RecastTimingEstimate(
        multiplier_by_base=multipliers,
        dominant_speed_modifier_by_base=dominant_speed_modifier_by_base,
    )


def infer_recast_multiplier_by_base(attempts: list[dict[str, Any]]) -> dict[int, float]:
    return infer_recast_timing_by_base(attempts).multiplier_by_base


def adjusted_recast_ms(
    attempt: dict[str, Any],
    default_speed_multiplier: float,
    recast_timing: RecastTimingEstimate,
    *,
    job: str | None = None,
    speed_windows: list[SpeedModifierWindow] | None = None,
) -> float:
    metadata = attempt["metadata"]
    cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
    timestamp = to_number(attempt.get("timestamp"))
    base_recast = metadata.effective_recast_ms
    recast_multiplier = (
        recast_timing.multiplier_by_base.get(base_recast, default_speed_multiplier)
        if metadata.recast_speed_adjusted
        else 1.0
    )
    recast = float(base_recast) * recast_multiplier
    speed_windows = speed_windows or []

    if metadata.recast_speed_adjusted and timestamp is not None:
        actual_speed_modifier = speed_modifier_at_timestamp(
            timestamp,
            job=job,
            speed_windows=speed_windows,
        )
        dominant_speed_modifier = recast_timing.dominant_speed_modifier_by_base.get(base_recast, actual_speed_modifier)
        if dominant_speed_modifier > 0 and abs(actual_speed_modifier - dominant_speed_modifier) > 0.00001:
            # recast_timing 是從「最常見的速度狀態」下的相鄰 GCD 間隔估出來的。若這一招發生在
            # buff 尚未生效或短暫斷掉的時間點，先還原成未套用該速度狀態的 tooltip GCD，
            # 再依當下實際速度倍率往下取整，貼近 xivanalysis CastTime 的處理方式。
            unmodified_recast = round_to_nearest_10_ms(recast / dominant_speed_modifier)
            recast = floor_to_10_ms(unmodified_recast * actual_speed_modifier)

    if metadata.cast_ms > 0 and cast_duration > 0:
        cast_ratio = cast_duration / metadata.cast_ms
        if 0.5 <= cast_ratio < 0.9:
            # 例如 Pictomancer 的 Inspiration 會同時縮短 cast 與 recast；這類短窗 buff
            # 不一定有足夠相鄰樣本可推低分位，因此保留 hardcast duration 作為補充線索。
            recast = float(base_recast) * cast_ratio

    return max(0.0, recast)


def calculate_gcd_coverage_from_graph(
    graph: dict[str, Any],
    metadata_store: ActionMetadataStore,
    *,
    source_id: int | None = None,
    job: str | None = None,
    fight_end_time: float | None = None,
    fallback_denominator_ms: float | None = None,
) -> dict[str, Any] | None:
    attempts = extract_gcd_attempts(graph, metadata_store, source_id=source_id)
    if not attempts:
        return None

    windows = downtime_windows(graph)
    downtime_ms = sum(end - start for start, end in windows)
    combat_time_ms = to_number(graph.get("combatTime"))
    raw_denominator_ms = combat_time_ms if combat_time_ms is not None else fallback_denominator_ms
    denominator_ms = raw_denominator_ms - downtime_ms if raw_denominator_ms is not None else None
    if denominator_ms is None or denominator_ms <= 0:
        return None

    default_speed_multiplier = median_default_speed_multiplier(attempts)
    covered_ms = 0.0
    end_time = fight_end_time if fight_end_time is not None else to_number(graph.get("endTime"))
    action_attempts = extract_all_attempts(graph, source_id=source_id)
    speed_windows = infer_speed_modifier_windows(action_attempts, fight_end_time=end_time)
    recast_timing = infer_recast_timing_by_base(
        attempts,
        job=job,
        speed_windows=speed_windows,
    )

    for index, attempt in enumerate(attempts):
        timestamp = to_number(attempt.get("timestamp"))
        if timestamp is None:
            continue

        next_attempt = attempts[index + 1] if index + 1 < len(attempts) else None
        cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
        recast = adjusted_recast_ms(
            attempt,
            default_speed_multiplier,
            recast_timing,
            job=job,
            speed_windows=speed_windows,
        )
        uptime = max(cast_duration, recast)
        if cast_duration > 0 and cast_duration >= recast:
            uptime += 100

        if next_attempt:
            next_timestamp = to_number(next_attempt.get("timestamp"))
            if next_timestamp is not None:
                uptime = min(uptime, max(0.0, next_timestamp - timestamp))

        if end_time is not None:
            uptime = min(uptime, max(0.0, end_time - timestamp))

        covered_ms += max(0.0, uptime - overlap_ms(timestamp, timestamp + uptime, windows))

    covered_ms = max(0, round(covered_ms))
    denominator_ms = max(1, round(denominator_ms))
    return {
        "percent": round(min(100.0, covered_ms / denominator_ms * 100), 2),
        "covered_time_ms": covered_ms,
        "denominator_ms": denominator_ms,
        "downtime_ms": round(downtime_ms),
        "gcd_cast_count": len(attempts),
        "calculation_version": GCD_CALCULATION_VERSION,
        "source": GCD_SOURCE,
    }


def mark_candidate_unavailable(candidate: GcdCandidate, reason: str, checked_at_iso: str) -> None:
    candidate.player["gcd_coverage"] = None
    candidate.player["gcd_coverage_status"] = {
        "state": "unavailable",
        "reason": reason,
        "calculation_version": GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
    }


def apply_coverage(candidate: GcdCandidate, coverage: dict[str, Any], checked_at_iso: str) -> None:
    candidate.player["gcd_coverage"] = coverage
    candidate.player["gcd_coverage_status"] = {
        "state": "ok",
        "calculation_version": GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
    }


def parse_int_env_default(name: str, fallback: int) -> int:
    raw_value = os.environ.get(name)
    if raw_value is None or raw_value.strip() == "":
        return fallback
    try:
        return int(raw_value)
    except ValueError:
        print(f"環境變數 {name} 不是整數，已改用預設值 {fallback}。", file=sys.stderr)
        return fallback


def parse_args() -> argparse.Namespace:
    # GitHub Actions 未設定 Repository Variable 時，若 workflow 明確把它傳入 env，
    # Python 會看到空字串而不是缺少 key。這裡先把空值視為預設值，避免還沒讀到
    # 命令列 --limit 覆寫前就因 int("") 中止整輪資料更新。
    default_limit = parse_int_env_default("FFLOGS_GCD_BACKFILL_LIMIT", DEFAULT_GCD_BACKFILL_LIMIT)
    parser = argparse.ArgumentParser(description="Backfill missing FFLogs GCD coverage fields.")
    parser.add_argument("--limit", type=int, default=default_limit, help="本輪最多更新的玩家筆數。")
    parser.add_argument("--all", action="store_true", help="連已是目前 GCD 計算版本的玩家也重新計算；仍會略過已標為 null 的不可用報告。")
    parser.add_argument("--dry-run", action="store_true", help="只列出待補統計與本輪候選，不寫入也不呼叫 FFLogs。")
    parser.add_argument("--report-code", help="只處理指定 report code，方便驗證單場戰鬥。")
    parser.add_argument("--fight-id", type=int, help="只處理指定 fight id。")
    parser.add_argument("--player-name", help="只處理指定角色名稱。")
    return parser.parse_args()


def candidate_matches_filters(candidate: GcdCandidate, args: argparse.Namespace) -> bool:
    if args.report_code and candidate.report_code != args.report_code:
        return False
    if args.fight_id is not None and to_int(candidate.fight.get("fight_id")) != args.fight_id:
        return False
    if args.player_name:
        name = candidate.player.get("name") or candidate.player.get("character_name")
        if name != args.player_name:
            return False
    return True


def main() -> int:
    args = parse_args()
    encounters = load_all_encounters()
    candidates, missing_key_count, stale_key_count, null_key_count, rankings_by_key = scan_candidates(
        encounters,
        include_current=args.all,
    )
    candidates = [candidate for candidate in candidates if candidate_matches_filters(candidate, args)]
    selected = candidates[: max(args.limit, 0)]

    print(f"需要更新 GCD 覆蓋率的玩家筆數：{missing_key_count}")
    print(f"需要以 v{GCD_CALCULATION_VERSION} 重算 GCD 覆蓋率的玩家筆數：{stale_key_count}")
    print(f"已建立 gcd_coverage key 但值為 null 的玩家筆數：{null_key_count}")
    print(f"本輪選取更新筆數：{len(selected)}")
    if args.all:
        print("已啟用 --all：本輪候選包含目前版本已完成的 GCD 覆蓋率。")
    if args.report_code or args.fight_id is not None or args.player_name:
        print(f"套用篩選後剩餘待補筆數：{len(candidates)}")

    for index, candidate in enumerate(selected[:20], start=1):
        print(f"{index:>2}. {candidate.label} clear_time_sort={int(candidate.sort_time)}")
    if len(selected) > 20:
        print(f"... 另有 {len(selected) - 20} 筆本輪候選。")

    if args.dry_run or not selected:
        return 0

    session = fflogs.requests.Session()
    auth_pool = auth_pool_class(session, read_credentials())
    metadata_store = ActionMetadataStore()
    try:
        metadata_store.preload()
    except RuntimeError as error:
        print(f"無法載入 GCD 技能資料，本輪保留缺 key 狀態，下次 workflow 會重試：{error}", file=sys.stderr)
        return 0

    changed_encounter_keys: set[str] = set()
    inaccessible_reports: dict[str, str] = {}
    fight_graph_cache: dict[tuple[str, int, float, float], dict[str, Any]] = {}
    updated = 0
    marked_null = 0
    failed = 0
    checked_at_iso = milliseconds_to_iso(time.time() * 1000)

    for index, candidate in enumerate(selected, start=1):
        print(f"[{index}/{len(selected)}] 更新 GCD 覆蓋率：{candidate.label}")
        if candidate.report_code in inaccessible_reports:
            mark_candidate_unavailable(candidate, inaccessible_reports[candidate.report_code], checked_at_iso)
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            print(f"[{index}/{len(selected)}] → report 已標記無法存取，寫入 null。")
            continue

        try:
            fight_id = to_int(candidate.fight.get("fight_id"))
            start_time = first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
            end_time = first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
            if fight_id is None or start_time is None or end_time is None:
                raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法查詢整場 Casts graph。")

            graph_cache_key = (candidate.report_code, fight_id, start_time, end_time)
            graph = fight_graph_cache.get(graph_cache_key)
            if graph is None:
                graph = query_fight_casts_graph(session, auth_pool, candidate)
                fight_graph_cache[graph_cache_key] = graph

            coverage = calculate_gcd_coverage_from_graph(
                graph,
                metadata_store,
                source_id=to_int(candidate.player.get("fflogs_id")),
                job=candidate.player.get("job"),
                fight_end_time=first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
                fallback_denominator_ms=first_number(
                    candidate.fight.get("clear_time_ms"),
                    end_time - start_time,
                    candidate.fight.get("damage_time_ms"),
                ),
            )
        except report_access_error_class:
            reason = "private_or_deleted"
            inaccessible_reports[candidate.report_code] = reason
            mark_candidate_unavailable(candidate, reason, checked_at_iso)
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            print(f"[{index}/{len(selected)}] → report 已轉為 Private、刪除或無權限，寫入 null。")
            continue
        except Exception as error:  # noqa: BLE001
            failed += 1
            print(f"[{index}/{len(selected)}] → 暫時失敗，下次 workflow 會重試：{error}", file=sys.stderr)
            continue

        if not coverage:
            failed += 1
            print(f"[{index}/{len(selected)}] → 無法從 Casts graph 計算 GCD 覆蓋率，保留缺 key 狀態。", file=sys.stderr)
            continue

        apply_coverage(candidate, coverage, checked_at_iso)
        changed_encounter_keys.add(candidate.encounter_key)
        updated += 1
        print(
            f"[{index}/{len(selected)}] → {coverage['percent']:.2f}% "
            f"({coverage['covered_time_ms']}/{coverage['denominator_ms']} ms, "
            f"{coverage['gcd_cast_count']} GCD)"
        )

    for key in sorted(changed_encounter_keys):
        ranking = rankings_by_key.get(key)
        encounter = encounters.get(key)
        if not ranking or not encounter:
            continue
        write_ranking_file(encounter, ranking)
        print(f"已寫入 {key} 的 GCD 覆蓋率更新。")

    print(
        "GCD 覆蓋率補齊完成："
        f"成功 {updated} 筆，"
        f"寫入 null {marked_null} 筆，"
        f"暫時失敗 {failed} 筆。"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
