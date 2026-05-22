from __future__ import annotations

import csv
import io
import statistics
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


# GCD 覆蓋率只保存衍生結果，不能把 FFLogs Casts raw events 寫入 repo。
# 這個模組不 import fetch_fflogs.py，讓 fetch 與 backfill 都能共用同一套本地 xivanalysis-like 計算。
ACTION_CSV_URL = "https://raw.githubusercontent.com/xivapi/ffxiv-datamining/master/csv/en/Action.csv"
STATUS_CSV_URL = "https://raw.githubusercontent.com/xivapi/ffxiv-datamining/master/csv/en/Status.csv"
GCD_ACTION_CATEGORY_IDS = {2, 3}  # 2=Spell, 3=Weaponskill
GCD_CALCULATION_VERSION = 10
GCD_SOURCE_CASTS_GRAPH = "fflogs_casts_graph"
GCD_SOURCE_RAW_EVENTS = "fflogs_raw_events"
GCD_SOURCE = GCD_SOURCE_CASTS_GRAPH
FFLOGS_STATUS_ID_OFFSET = 1_000_000
SUB_ATTRIBUTE_MINIMUM = 420
STAT_DIVISOR = 2780
MIN_RECAST_TIME_MS = 1500
RECAST_TIGHT_DELTA_MIN_RATIO = 0.8
RECAST_TIGHT_DELTA_MAX_RATIO = 1.05
RECAST_INTERVAL_BATCH_MS = 45
RECAST_INTERVAL_MODE_RADIUS = 2
MAIN_TARGET_DAMAGE_DOWNTIME_MIN_GAP_MS = 10_000
MAIN_TARGET_DAMAGE_DOWNTIME_MIN_EVENT_SHARE = 0.50
# 武士的居合／返技在 FFLogs 會回傳偏短的 cast duration packet；xivanalysis 仍用
# 技速後的完整 GCD lock 判斷 Always Be Casting，因此不可用 cast_ms 比例回推 recast。
CAST_RATIO_RECAST_EXCLUDED_JOBS = {"Samurai"}
RAW_NEXT_GCD_CAPPED_JOBS = {"Viper"}
TANK_JOBS = {"DarkKnight", "Gunbreaker", "Paladin", "Warrior"}

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

RAW_SPEED_STATUS_MODIFIERS_BY_STATUS_ID = {
    1299: 0.87,  # Samurai Fuka
    3669: 0.85,  # Viper Swiftscaled
    157: 0.80,   # White Mage Presence of Mind
    3689: 0.75,  # Pictomancer Inspiration
}

RAW_STATUS_APPLY_EVENT_TYPES = {"applybuff", "refreshbuff", "applydebuff", "refreshdebuff"}
RAW_STATUS_REMOVE_EVENT_TYPES = {"removebuff", "removedebuff"}
RAW_PLAYER_ACTION_EVENT_TYPES = {"begincast", "cast", "damage", "calculateddamage"}
# datamining 若暫時無法下載 Status.csv，仍保留幻白虎已確認會影響 ABC 的狀態。
FALLBACK_UNABLE_TO_ACT_STATUS_IDS = {
    783,   # Down for the Count
    1479,  # Falling
    1513,  # Stun
}
RECAST_SUBSTAT_EXCLUDED_ACTION_IDS = {
    34620,  # Viper Dreadwinder
    34623,  # Viper Vicepit
}


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
# key 只在 Action.csv 不能直接表達「on GCD」或「GCD recast」時出現。
GCD_ACTION_OVERRIDES: dict[int, GcdActionOverride] = {
    2259: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),
    2261: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),
    2263: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),
    18805: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),
    18806: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),
    18807: GcdActionOverride(gcd_recast_ms=500, speed_adjusted=False),
    2260: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2265: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2266: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2267: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2268: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2269: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2270: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2271: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    2272: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    16491: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    16492: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    18873: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),
    18874: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),
    18875: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),
    18876: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),
    18877: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),
    18878: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False),
    18879: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    18880: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    18881: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    197: GcdActionOverride(gcd_recast_ms=1930, speed_adjusted=False),
    198: GcdActionOverride(gcd_recast_ms=3860, speed_adjusted=False),
    199: GcdActionOverride(gcd_recast_ms=3860, speed_adjusted=False),
    200: GcdActionOverride(gcd_recast_ms=5860, speed_adjusted=False),
    201: GcdActionOverride(gcd_recast_ms=6860, speed_adjusted=False),
    202: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    203: GcdActionOverride(gcd_recast_ms=5100, speed_adjusted=False),
    204: GcdActionOverride(gcd_recast_ms=8100, speed_adjusted=False),
    205: GcdActionOverride(gcd_recast_ms=12600, speed_adjusted=False),
    206: GcdActionOverride(gcd_recast_ms=4100, speed_adjusted=False),
    207: GcdActionOverride(gcd_recast_ms=7130, speed_adjusted=False),
    208: GcdActionOverride(gcd_recast_ms=10100, speed_adjusted=False),
    4238: GcdActionOverride(gcd_recast_ms=5100, speed_adjusted=False),
    4239: GcdActionOverride(gcd_recast_ms=6100, speed_adjusted=False),
    4240: GcdActionOverride(gcd_recast_ms=3860, speed_adjusted=False),
    4241: GcdActionOverride(gcd_recast_ms=3860, speed_adjusted=False),
    4242: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    4243: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    4244: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    4245: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    4246: GcdActionOverride(gcd_recast_ms=12600, speed_adjusted=False),
    4247: GcdActionOverride(gcd_recast_ms=10100, speed_adjusted=False),
    4248: GcdActionOverride(gcd_recast_ms=10100, speed_adjusted=False),
    7861: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    7862: GcdActionOverride(gcd_recast_ms=12600, speed_adjusted=False),
    17105: GcdActionOverride(gcd_recast_ms=3860, speed_adjusted=False),
    17106: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    24858: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    24859: GcdActionOverride(gcd_recast_ms=10100, speed_adjusted=False),
    34866: GcdActionOverride(gcd_recast_ms=8200, speed_adjusted=False),
    34867: GcdActionOverride(gcd_recast_ms=12600, speed_adjusted=False),
    7410: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    16497: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    16498: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),
    16499: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),
    16500: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),
    25788: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),
    36978: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False),
    36981: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),
    36982: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),
    34620: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    34623: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    34621: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    34622: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    34624: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    34625: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    34633: GcdActionOverride(gcd_recast_ms=3500, speed_adjusted=True),
    34626: GcdActionOverride(gcd_recast_ms=2200, speed_adjusted=True),
    34627: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),
    34628: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),
    34629: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),
    34630: GcdActionOverride(gcd_recast_ms=2000, speed_adjusted=True),
    34631: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=True),
    # 下列技能在 Action.csv 會同時帶有「技能本身冷卻」與 Spell/Weaponskill 類別。
    # FFLogs Casts graph 只提供 action id，若直接使用 Action.csv 的 Recast100ms，會把這些 GCD
    # 誤當成 30/60/120/180 秒的 GCD 鎖，造成覆蓋時間被高估。這裡只覆寫實際 GCD 鎖時間，
    # 技能冷卻本身仍由職業循環分析處理，不屬於本專案的 GCD 覆蓋率分母。
    7427: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),   # Summon Bahamut
    25831: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),  # Summon Phoenix
    36992: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),  # Summon Solar Bahamut
    24290: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False), # Eukrasia
    15997: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Standard Step
    15998: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Technical Step
    15999: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False), # Emboite
    16000: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False), # Entrechat
    16001: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False), # Jete
    16002: GcdActionOverride(gcd_recast_ms=1000, speed_adjusted=False), # Pirouette
    16003: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Standard Finish
    16191: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Single Standard Finish
    16192: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Double Standard Finish
    16004: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Technical Finish
    16193: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Single Technical Finish
    16194: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Double Technical Finish
    16195: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Triple Technical Finish
    16196: GcdActionOverride(gcd_recast_ms=1500, speed_adjusted=False), # Quadruple Technical Finish
    36984: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),  # Finishing Move
    16146: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),  # Gnashing Fang
    25760: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),  # Double Down
    25874: GcdActionOverride(gcd_recast_ms=2500, speed_adjusted=True),  # Macrocosmos
    # xivanalysis 將 Tendo Kaeshi Setsugekka 視為 3.2s GCD；XIVAPI Action.csv 目前會落到
    # 2.5s 的一般武士 GCD，會讓 7.1 武士 ABC delay 多出約 0.6 秒。
    36968: GcdActionOverride(gcd_recast_ms=3200, speed_adjusted=True),  # Tendo Kaeshi Setsugekka
}


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
                headers={"User-Agent": "ffxiv-tc-ranking-gcd-coverage/1.0"},
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


class StatusMetadataStore:
    def __init__(self, source_url: str = STATUS_CSV_URL) -> None:
        self.source_url = source_url
        self._unable_to_act_status_ids: set[int] | None = None

    def unable_to_act_status_ids(self) -> set[int]:
        if self._unable_to_act_status_ids is None:
            self._unable_to_act_status_ids = self._load_unable_to_act_status_ids()
        return set(self._unable_to_act_status_ids)

    def preload(self) -> None:
        self.unable_to_act_status_ids()

    def _load_unable_to_act_status_ids(self) -> set[int]:
        try:
            request = urllib.request.Request(
                self.source_url,
                headers={"User-Agent": "ffxiv-tc-ranking-gcd-coverage/1.0"},
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                raw_csv = response.read().decode("utf-8-sig")
        except (OSError, urllib.error.URLError):
            return set(FALLBACK_UNABLE_TO_ACT_STATUS_IDS)

        status_ids: set[int] = set()
        reader = csv.DictReader(io.StringIO(raw_csv))
        for row in reader:
            status_id = to_int(row.get("#"))
            if status_id is None:
                continue
            if parse_bool(row.get("LockActions")) or parse_bool(row.get("LockControl")):
                status_ids.add(status_id)

        return status_ids or set(FALLBACK_UNABLE_TO_ACT_STATUS_IDS)


def parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes"}
    return bool(value)


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


def query_fight_casts_graph(
    execute_graphql: Callable[[Any, Any, str, dict[str, Any]], dict[str, Any]],
    session: Any,
    auth_pool: Any,
    report_code: str,
    fight: dict[str, Any],
) -> dict[str, Any]:
    fight_id = to_int(fight.get("fight_id"))
    start_time = first_number(fight.get("start_time"), fight.get("startTime"))
    end_time = first_number(fight.get("end_time"), fight.get("endTime"))
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
    data = execute_graphql(session, auth_pool, query, {"code": report_code})
    graph = (((data.get("reportData") or {}).get("report") or {}).get("graph") or {}).get("data")
    if not isinstance(graph, dict):
        raise RuntimeError("FFLogs 整場 Casts graph 回傳格式不正確。")
    return graph


def query_fight_damage_done_events(
    execute_graphql: Callable[[Any, Any, str, dict[str, Any]], dict[str, Any]],
    session: Any,
    auth_pool: Any,
    report_code: str,
    fight: dict[str, Any],
    *,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    fight_id = to_int(fight.get("fight_id"))
    start_time = first_number(fight.get("start_time"), fight.get("startTime"))
    end_time = first_number(fight.get("end_time"), fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法查詢整場 DamageDone events。")

    query = """
    query($code: String!, $startTime: Float!, $endTime: Float!, $limit: Int!) {
      reportData {
        report(code: $code) {
          events(
            dataType: DamageDone,
            fightIDs: [%d],
            startTime: $startTime,
            endTime: $endTime,
            hostilityType: Friendlies,
            limit: $limit
          ) {
            data
            nextPageTimestamp
          }
        }
      }
    }
    """ % fight_id

    events: list[dict[str, Any]] = []
    cursor = start_time
    while cursor is not None and cursor < end_time:
        data = execute_graphql(
            session,
            auth_pool,
            query,
            {
                "code": report_code,
                "startTime": cursor,
                "endTime": end_time,
                "limit": limit,
            },
        )
        page = (((data.get("reportData") or {}).get("report") or {}).get("events") or {})
        page_events = page.get("data")
        if isinstance(page_events, list):
            events.extend(event for event in page_events if isinstance(event, dict))

        next_cursor = to_number(page.get("nextPageTimestamp"))
        if next_cursor is None or next_cursor <= cursor:
            break
        cursor = next_cursor

    return events


def query_fight_raw_events(
    execute_graphql: Callable[[Any, Any, str, dict[str, Any]], dict[str, Any]],
    session: Any,
    auth_pool: Any,
    report_code: str,
    fight: dict[str, Any],
    *,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    fight_id = to_int(fight.get("fight_id"))
    start_time = first_number(fight.get("start_time"), fight.get("startTime"))
    end_time = first_number(fight.get("end_time"), fight.get("endTime"))
    if fight_id is None or start_time is None or end_time is None:
        raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法查詢 raw events。")

    query = """
    query($code: String!, $startTime: Float!, $endTime: Float!, $limit: Int!) {
      reportData {
        report(code: $code) {
          events(
            dataType: All,
            fightIDs: [%d],
            startTime: $startTime,
            endTime: $endTime,
            hostilityType: Friendlies,
            limit: $limit
          ) {
            data
            nextPageTimestamp
          }
        }
      }
    }
    """ % fight_id

    events: list[dict[str, Any]] = []
    cursor = start_time
    while cursor is not None and cursor < end_time:
        data = execute_graphql(
            session,
            auth_pool,
            query,
            {
                "code": report_code,
                "startTime": cursor,
                "endTime": end_time,
                "limit": limit,
            },
        )
        page = (((data.get("reportData") or {}).get("report") or {}).get("events") or {})
        page_events = page.get("data")
        if isinstance(page_events, list):
            events.extend(event for event in page_events if isinstance(event, dict))

        next_cursor = to_number(page.get("nextPageTimestamp"))
        if next_cursor is None or next_cursor <= cursor:
            break
        cursor = next_cursor

    events.sort(key=lambda event: (to_number(event.get("timestamp")) or 0, to_int(event.get("packetID")) or 0, str(event.get("type") or "")))
    return events


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


def event_status_id(event: dict[str, Any]) -> int | None:
    status_id = to_int(event.get("abilityGameID"))
    if status_id is None:
        return None
    if status_id >= FFLOGS_STATUS_ID_OFFSET:
        return status_id - FFLOGS_STATUS_ID_OFFSET
    return status_id


def speed_stat_adjusted_duration_ms(speed_stat: int | float | None, base_duration_ms: int | float) -> float:
    if speed_stat is None:
        return float(base_duration_ms)
    attribute_multiplier = 1000 - int(130 * (float(speed_stat) - SUB_ATTRIBUTE_MINIMUM) // STAT_DIVISOR)
    adjusted_duration = int(attribute_multiplier * float(base_duration_ms) // 1000)
    final_duration = int((adjusted_duration * 100 // 1000) * 100 // 100)
    return float(final_duration * 10)


def combatant_speed_stats(raw_events: list[dict[str, Any]], *, source_id: int | None) -> dict[str, int]:
    for event in raw_events:
        if event.get("type") != "combatantinfo":
            continue
        if source_id is not None and event_source_id(event) != source_id:
            continue
        stats: dict[str, int] = {}
        skill_speed = to_int(event.get("skillSpeed"))
        spell_speed = to_int(event.get("spellSpeed"))
        if skill_speed is not None:
            stats["skill_speed"] = skill_speed
        if spell_speed is not None:
            stats["spell_speed"] = spell_speed
        return stats
    return {}


def raw_speed_modifier_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    fight_end_time: float | None,
) -> list[SpeedModifierWindow]:
    if source_id is None:
        return []

    windows: list[SpeedModifierWindow] = []
    for event in raw_events:
        timestamp = to_number(event.get("timestamp"))
        if timestamp is None:
            continue

        if event.get("type") == "combatantinfo" and event_source_id(event) == source_id:
            for aura in event.get("auras") or []:
                if not isinstance(aura, dict):
                    continue
                raw_status_id = to_int(aura.get("ability"))
                if raw_status_id is None:
                    continue
                status_id = raw_status_id - FFLOGS_STATUS_ID_OFFSET if raw_status_id >= FFLOGS_STATUS_ID_OFFSET else raw_status_id
                modifier = RAW_SPEED_STATUS_MODIFIERS_BY_STATUS_ID.get(status_id)
                if modifier is None:
                    continue
                duration = to_number(aura.get("duration"))
                end_ms = timestamp + duration if duration else fight_end_time
                if end_ms is None:
                    continue
                windows.append(
                    SpeedModifierWindow(
                        start_ms=timestamp,
                        end_ms=min(end_ms, fight_end_time) if fight_end_time is not None else end_ms,
                        modifier=modifier,
                        label=f"initial status {status_id}",
                    )
                )
            continue

        if event.get("type") not in {"applybuff", "refreshbuff"}:
            continue
        if to_int(event.get("targetID")) != source_id:
            continue
        status_id = event_status_id(event)
        if status_id is None:
            continue
        modifier = RAW_SPEED_STATUS_MODIFIERS_BY_STATUS_ID.get(status_id)
        if modifier is None:
            continue
        duration = to_number(event.get("duration"))
        end_ms = timestamp + duration if duration else fight_end_time
        if end_ms is None:
            continue
        windows.append(
            SpeedModifierWindow(
                start_ms=timestamp,
                end_ms=min(end_ms, fight_end_time) if fight_end_time is not None else end_ms,
                modifier=modifier,
                label=f"status {status_id}",
            )
        )

    return merge_speed_modifier_windows([window for window in windows if window.end_ms > window.start_ms])


def extract_gcd_attempts_from_raw_events(
    raw_events: list[dict[str, Any]],
    metadata_store: ActionMetadataStore,
    *,
    source_id: int | None = None,
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    pending_begin_by_source: dict[int, dict[str, Any]] = {}

    for event in sorted(raw_events, key=lambda item: (to_number(item.get("timestamp")) or 0, to_int(item.get("packetID")) or 0, str(item.get("type") or ""))):
        event_type = event.get("type")
        if event_type not in {"begincast", "cast"}:
            continue

        event_source = event_source_id(event)
        if source_id is not None and event_source != source_id:
            continue

        action_id = event_action_id(event, None)
        if action_id is None:
            continue
        metadata = metadata_store.get(action_id)
        if not metadata or not metadata.is_gcd:
            continue

        if event_type == "begincast":
            if event_source is not None:
                pending_begin_by_source[event_source] = event
            continue

        timestamp = to_number(event.get("timestamp"))
        if timestamp is None:
            continue

        begin_event = pending_begin_by_source.pop(event_source, None) if event_source is not None else None
        if begin_event is not None and event_action_id(begin_event, None) != action_id:
            begin_event = None

        cast_start = to_number(begin_event.get("timestamp")) if begin_event else timestamp
        cast_duration = to_number(begin_event.get("duration")) if begin_event else 0
        attempts.append(
            {
                "action_id": action_id,
                "timestamp": timestamp,
                "cast_start_timestamp": cast_start if cast_start is not None else timestamp,
                "cast_duration_ms": cast_duration or 0,
                "source_id": event_source,
                "metadata": metadata,
            }
        )

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
        if window.start_ms < timestamp <= window.end_ms:
            modifier *= window.modifier
    return modifier


def raw_recast_ms(
    attempt: dict[str, Any],
    *,
    speed_stats: dict[str, int],
    job: str | None,
    speed_windows: list[SpeedModifierWindow],
) -> float:
    metadata = attempt["metadata"]
    base_recast = metadata.effective_recast_ms
    if not metadata.recast_speed_adjusted:
        return float(base_recast)

    if metadata.action_id in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS:
        recast = float(base_recast)
    else:
        attribute_key = "spell_speed" if metadata.action_category_id == 2 else "skill_speed"
        recast = speed_stat_adjusted_duration_ms(speed_stats.get(attribute_key), base_recast)
    timestamp = to_number(attempt.get("timestamp"))
    if timestamp is not None:
        recast *= speed_modifier_at_timestamp(timestamp, job=job, speed_windows=speed_windows)
    if base_recast > MIN_RECAST_TIME_MS:
        recast = max(float(MIN_RECAST_TIME_MS), recast)
    return floor_to_10_ms(recast)


def raw_speed_stats_cover_attempt(attempt: dict[str, Any], speed_stats: dict[str, int]) -> bool:
    metadata = attempt["metadata"]
    if not metadata.recast_speed_adjusted:
        return True
    if metadata.action_id in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS:
        return True
    attribute_key = "spell_speed" if metadata.action_category_id == 2 else "skill_speed"
    return speed_stats.get(attribute_key) is not None


def timestamp_in_windows(timestamp: float, windows: list[tuple[float, float]]) -> bool:
    return any(start <= timestamp <= end for start, end in windows)


def first_window_containing(timestamp: float, windows: list[tuple[float, float]]) -> tuple[float, float] | None:
    for start, end in windows:
        if start <= timestamp <= end:
            return start, end
    return None


def windows_from_graph_items(items: Any) -> list[tuple[float, float]]:
    windows: list[tuple[float, float]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        start = to_number(item.get("startTime"))
        end = to_number(item.get("endTime"))
        if start is None or end is None or end <= start:
            continue
        windows.append((start, end))
    return windows


def merge_time_windows(windows: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(windows):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def total_window_ms(windows: list[tuple[float, float]]) -> float:
    return sum(end - start for start, end in merge_time_windows(windows))


def downtime_windows(graph: dict[str, Any]) -> list[tuple[float, float]]:
    return windows_from_graph_items(graph.get("downtime"))


def encounter_downtime_windows(graph: dict[str, Any]) -> list[tuple[float, float]]:
    return windows_from_graph_items(graph.get("encounter_downtime"))


def denominator_only_downtime_windows(graph: dict[str, Any]) -> list[tuple[float, float]]:
    # `denominator_downtime` 代表「這段時間不應算進可要求 GCD 持續運轉的分母」。
    # 它不一定要從 covered_time 扣除：例如幻白虎主目標離場時玩家可能仍在打白帝，
    # xivanalysis 的 Always Be Casting 會把這些操作視為玩家仍有在做事，但不把主目標離場
    # 的整段時間放進分母懲罰。
    return windows_from_graph_items(graph.get("denominator_downtime"))


def infer_main_target_damage_downtime_windows(
    events: list[dict[str, Any]],
    *,
    min_gap_ms: float = MAIN_TARGET_DAMAGE_DOWNTIME_MIN_GAP_MS,
    min_event_share: float = MAIN_TARGET_DAMAGE_DOWNTIME_MIN_EVENT_SHARE,
) -> list[dict[str, Any]]:
    timestamps_by_target: dict[int, list[float]] = {}
    for event in events:
        target_id = to_int(event.get("targetID"))
        timestamp = to_number(event.get("timestamp"))
        if target_id is None or timestamp is None:
            continue
        timestamps_by_target.setdefault(target_id, []).append(timestamp)

    total_events = sum(len(timestamps) for timestamps in timestamps_by_target.values())
    if total_events <= 0:
        return []

    main_target_id, timestamps = max(timestamps_by_target.items(), key=lambda item: len(item[1]))
    if len(timestamps) / total_events < min_event_share:
        return []

    windows: list[dict[str, int]] = []
    unique_timestamps = sorted(set(timestamps))
    for previous_timestamp, next_timestamp in zip(unique_timestamps, unique_timestamps[1:]):
        gap = next_timestamp - previous_timestamp
        if gap < min_gap_ms:
            continue
        windows.append(
            {
                "startTime": round(previous_timestamp),
                "endTime": round(next_timestamp),
                "targetID": main_target_id,
                "source": "main_target_damage_gap",
            }
        )
    return windows


def infer_unable_to_act_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    unable_to_act_status_ids: set[int],
    fight_end_time: float | None,
) -> list[dict[str, Any]]:
    if source_id is None or not unable_to_act_status_ids:
        return []

    active_by_status_id: dict[int, float] = {}
    windows: list[dict[str, Any]] = []
    for event in raw_events:
        event_type = str(event.get("type") or "")
        if event_type not in RAW_STATUS_APPLY_EVENT_TYPES and event_type not in RAW_STATUS_REMOVE_EVENT_TYPES:
            continue
        if to_int(event.get("targetID")) != source_id:
            continue

        status_id = event_status_id(event)
        timestamp = to_number(event.get("timestamp"))
        if status_id is None or timestamp is None or status_id not in unable_to_act_status_ids:
            continue

        if event_type in RAW_STATUS_APPLY_EVENT_TYPES:
            # xivanalysis 的 UnableToAct 由 statusApply/statusRemove 組窗；FFLogs raw events 對
            # buff 與 debuff 分別有 apply/refresh，refresh 只保留第一個起點避免重疊窗膨脹。
            active_by_status_id.setdefault(status_id, timestamp)
            continue

        start = active_by_status_id.pop(status_id, None)
        if start is None or timestamp <= start:
            continue
        windows.append(
            {
                "startTime": round(start),
                "endTime": round(timestamp),
                "statusID": status_id,
                "source": "unable_to_act_status",
            }
        )

    if fight_end_time is not None:
        for status_id, start in active_by_status_id.items():
            if fight_end_time > start:
                windows.append(
                    {
                        "startTime": round(start),
                        "endTime": round(fight_end_time),
                        "statusID": status_id,
                        "source": "unable_to_act_status",
                    }
                )

    return windows


def infer_all_foes_untargetable_windows(
    raw_events: list[dict[str, Any]],
    *,
    friendly_ids: set[int],
    fight_start_time: float | None,
    fight_end_time: float | None,
) -> list[dict[str, Any]]:
    if fight_start_time is None or fight_end_time is None or fight_end_time <= fight_start_time:
        return []

    foe_ids: set[int] = set()
    first_targetability_event: dict[int, tuple[float, bool]] = {}
    first_friendly_interaction: dict[int, float] = {}
    targetability_changes: list[tuple[float, int, bool]] = []

    for event in raw_events:
        timestamp = to_number(event.get("timestamp"))
        if timestamp is None:
            continue

        event_type = str(event.get("type") or "")
        source_id = event_source_id(event)
        target_id = to_int(event.get("targetID"))

        if event_type == "targetabilityupdate":
            actor_id = source_id if source_id is not None else target_id
            if actor_id is None or actor_id in friendly_ids:
                continue
            targetable = bool(to_int(event.get("targetable")))
            foe_ids.add(actor_id)
            first_targetability_event.setdefault(actor_id, (timestamp, targetable))
            targetability_changes.append((timestamp, actor_id, targetable))
            continue

        if event_type in RAW_PLAYER_ACTION_EVENT_TYPES:
            if source_id in friendly_ids and target_id is not None and target_id not in friendly_ids:
                first_friendly_interaction.setdefault(target_id, timestamp)
            if target_id in friendly_ids and source_id is not None and source_id not in friendly_ids:
                first_friendly_interaction.setdefault(source_id, timestamp)

    if not foe_ids or not targetability_changes:
        return []

    availability: dict[int, bool] = {}
    for foe_id in foe_ids:
        first_update = first_targetability_event.get(foe_id)
        first_seen = first_friendly_interaction.get(foe_id)
        # 若敵人的第一筆 targetability 是變成可選取，而且在此之前沒有玩家互動，
        # 代表這是中途進場的 add；進場前不應讓「全敵人不可選取」的 downtime 提早結束。
        availability[foe_id] = not (
            first_update is not None
            and first_update[1]
            and (first_seen is None or first_seen >= first_update[0])
        )

    changes_by_timestamp: dict[float, list[tuple[int, bool]]] = {}
    for timestamp, actor_id, targetable in targetability_changes:
        changes_by_timestamp.setdefault(timestamp, []).append((actor_id, targetable))

    windows: list[dict[str, Any]] = []
    cursor = fight_start_time
    for timestamp in sorted(changes_by_timestamp):
        bounded_timestamp = min(max(timestamp, fight_start_time), fight_end_time)
        if bounded_timestamp > cursor and availability and not any(availability.values()):
            windows.append(
                {
                    "startTime": round(cursor),
                    "endTime": round(bounded_timestamp),
                    "source": "all_foes_untargetable",
                }
            )
        for actor_id, targetable in changes_by_timestamp[timestamp]:
            availability[actor_id] = targetable
        cursor = bounded_timestamp
        if cursor >= fight_end_time:
            break

    if cursor < fight_end_time and availability and not any(availability.values()):
        windows.append(
            {
                "startTime": round(cursor),
                "endTime": round(fight_end_time),
                "source": "all_foes_untargetable",
            }
        )

    return [window for window in windows if to_number(window.get("endTime")) > to_number(window.get("startTime"))]


def raw_event_downtime_source(
    graph: dict[str, Any],
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    friendly_ids: set[int],
    fight_start_time: float | None,
    fight_end_time: float | None,
    unable_to_act_status_ids: set[int],
) -> dict[str, Any]:
    downtime_source = dict(graph)
    encounter_windows = infer_all_foes_untargetable_windows(
        raw_events,
        friendly_ids=friendly_ids,
        fight_start_time=fight_start_time,
        fight_end_time=fight_end_time,
    )
    if encounter_windows:
        downtime_source["encounter_downtime"] = encounter_windows

    player_windows = infer_unable_to_act_windows(
        raw_events,
        source_id=source_id,
        unable_to_act_status_ids=unable_to_act_status_ids,
        fight_end_time=fight_end_time,
    )
    if player_windows:
        downtime_source["downtime"] = list(downtime_source.get("downtime") or []) + player_windows

    return downtime_source


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
            unmodified_recast = round_to_nearest_10_ms(recast / dominant_speed_modifier)
            recast = floor_to_10_ms(unmodified_recast * actual_speed_modifier)

    if str(job) not in CAST_RATIO_RECAST_EXCLUDED_JOBS and metadata.cast_ms > 0 and cast_duration > 0:
        cast_ratio = cast_duration / metadata.cast_ms
        if 0.5 <= cast_ratio < 0.9:
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

    base_downtime_windows = downtime_windows(graph)
    inferred_encounter_windows = encounter_downtime_windows(graph)
    if str(job) in TANK_JOBS:
        coverage_windows = base_downtime_windows
        denominator_windows = merge_time_windows(
            base_downtime_windows + inferred_encounter_windows + denominator_only_downtime_windows(graph)
        )
    else:
        coverage_windows = merge_time_windows(base_downtime_windows + inferred_encounter_windows)
        denominator_windows = merge_time_windows(coverage_windows + denominator_only_downtime_windows(graph))
    coverage_downtime_ms = total_window_ms(coverage_windows)
    denominator_downtime_ms = total_window_ms(denominator_windows)
    combat_time_ms = to_number(graph.get("combatTime"))
    raw_denominator_ms = combat_time_ms if combat_time_ms is not None else fallback_denominator_ms
    denominator_ms = raw_denominator_ms - denominator_downtime_ms if raw_denominator_ms is not None else None
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

        next_attempt = attempts[index + 1] if index + 1 < len(attempts) else None
        if next_attempt:
            next_timestamp = to_number(next_attempt.get("timestamp"))
            if next_timestamp is not None:
                uptime = min(uptime, max(0.0, next_timestamp - timestamp))

        # FFLogs Casts graph 是聚合後的事件來源；用下一個 GCD timestamp 夾住覆蓋區間，
        # 避免高密度或讀條職業在同一段時間被重複加分。
        if end_time is not None:
            uptime = min(uptime, max(0.0, end_time - timestamp))

        covered_ms += max(0.0, uptime - overlap_ms(timestamp, timestamp + uptime, coverage_windows))

    covered_ms = max(0, round(covered_ms))
    denominator_ms = max(1, round(denominator_ms))
    coverage = {
        "percent": round(min(100.0, covered_ms / denominator_ms * 100), 2),
        "covered_time_ms": covered_ms,
        "denominator_ms": denominator_ms,
        "downtime_ms": round(denominator_downtime_ms),
        "gcd_cast_count": len(attempts),
        "calculation_version": GCD_CALCULATION_VERSION,
        "source": GCD_SOURCE_CASTS_GRAPH,
    }
    if round(coverage_downtime_ms) != round(denominator_downtime_ms):
        coverage["coverage_downtime_ms"] = round(coverage_downtime_ms)
        coverage["denominator_downtime_ms"] = round(denominator_downtime_ms)
    return coverage


def calculate_gcd_coverage_from_raw_events(
    raw_events: list[dict[str, Any]],
    metadata_store: ActionMetadataStore,
    *,
    source_id: int | None = None,
    job: str | None = None,
    fight_end_time: float | None = None,
    fallback_denominator_ms: float | None = None,
    downtime_source: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    attempts = extract_gcd_attempts_from_raw_events(raw_events, metadata_store, source_id=source_id)
    if not attempts:
        return None

    downtime_source = downtime_source or {}
    base_downtime_windows = downtime_windows(downtime_source)
    inferred_encounter_windows = encounter_downtime_windows(downtime_source)
    if str(job) in TANK_JOBS:
        coverage_windows = base_downtime_windows
        denominator_windows = merge_time_windows(
            base_downtime_windows + inferred_encounter_windows + denominator_only_downtime_windows(downtime_source)
        )
    else:
        coverage_windows = merge_time_windows(base_downtime_windows + inferred_encounter_windows)
        denominator_windows = merge_time_windows(coverage_windows + denominator_only_downtime_windows(downtime_source))

    coverage_downtime_ms = total_window_ms(coverage_windows)
    denominator_downtime_ms = total_window_ms(denominator_windows)
    combat_time_ms = to_number(downtime_source.get("combatTime"))
    raw_denominator_ms = combat_time_ms if combat_time_ms is not None else fallback_denominator_ms
    denominator_ms = raw_denominator_ms - denominator_downtime_ms if raw_denominator_ms is not None else None
    if denominator_ms is None or denominator_ms <= 0:
        return None

    speed_stats = combatant_speed_stats(raw_events, source_id=source_id)
    speed_windows = raw_speed_modifier_windows(raw_events, source_id=source_id, fight_end_time=fight_end_time)
    default_speed_multiplier = median_default_speed_multiplier(attempts)
    recast_timing = infer_recast_timing_by_base(
        attempts,
        job=job,
        speed_windows=speed_windows,
    )
    covered_ms = 0.0

    for index, attempt in enumerate(attempts):
        timestamp = to_number(attempt.get("timestamp"))
        if timestamp is None:
            continue

        cast_start = to_number(attempt.get("cast_start_timestamp"))
        if cast_start is not None and timestamp_in_windows(cast_start, coverage_windows):
            continue

        cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
        if raw_speed_stats_cover_attempt(attempt, speed_stats):
            recast = raw_recast_ms(
                attempt,
                speed_stats=speed_stats,
                job=job,
                speed_windows=speed_windows,
            )
        else:
            # FFLogs combatantinfo 有時不提供副屬性；此時改以同場 GCD timestamp 分桶推估
            # 實際 recast，避免缺少 skillSpeed/spellSpeed 時把所有技能退回未加速基礎值。
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
        if fight_end_time is not None:
            uptime = min(uptime, max(0.0, fight_end_time - timestamp))
        if str(job) in RAW_NEXT_GCD_CAPPED_JOBS:
            next_attempt = attempts[index + 1] if index + 1 < len(attempts) else None
            if next_attempt:
                next_timestamp = to_number(next_attempt.get("timestamp"))
                if next_timestamp is not None:
                    uptime = min(uptime, max(0.0, next_timestamp - timestamp))
        if uptime <= 0:
            continue

        end_time = timestamp + uptime
        ending_window = first_window_containing(end_time, coverage_windows)
        if ending_window is not None:
            uptime = max(0.0, ending_window[0] - timestamp)

        covered_ms += max(0.0, uptime)

    covered_ms = max(0, round(covered_ms))
    denominator_ms = max(1, round(denominator_ms))
    coverage = {
        "percent": round(min(100.0, covered_ms / denominator_ms * 100), 2),
        "covered_time_ms": covered_ms,
        "denominator_ms": denominator_ms,
        "downtime_ms": round(denominator_downtime_ms),
        "gcd_cast_count": len(attempts),
        "calculation_version": GCD_CALCULATION_VERSION,
        "source": GCD_SOURCE_RAW_EVENTS,
    }
    if round(coverage_downtime_ms) != round(denominator_downtime_ms):
        coverage["coverage_downtime_ms"] = round(coverage_downtime_ms)
        coverage["denominator_downtime_ms"] = round(denominator_downtime_ms)
    if speed_stats:
        coverage["speed_stat_source"] = "combatantinfo"
    return coverage


def build_gcd_coverage_status(*, checked_at_iso: str, state: str = "ok", reason: str | None = None) -> dict[str, Any]:
    status = {
        "state": state,
        "calculation_version": GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
    }
    if reason:
        status["reason"] = reason
    return status
