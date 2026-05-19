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
GCD_ACTION_CATEGORY_IDS = {2, 3}  # 2=Spell, 3=Weaponskill
GCD_CALCULATION_VERSION = 5
GCD_SOURCE = "fflogs_casts_graph"
RECAST_TIGHT_DELTA_MIN_RATIO = 0.8
RECAST_TIGHT_DELTA_MAX_RATIO = 1.05
RECAST_INTERVAL_BATCH_MS = 45
RECAST_INTERVAL_MODE_RADIUS = 2

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
    34620: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=False),
    34623: GcdActionOverride(gcd_recast_ms=3000, speed_adjusted=False),
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

    if metadata.cast_ms > 0 and cast_duration > 0:
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


def build_gcd_coverage_status(*, checked_at_iso: str, state: str = "ok", reason: str | None = None) -> dict[str, Any]:
    status = {
        "state": state,
        "calculation_version": GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
    }
    if reason:
        status["reason"] = reason
    return status
