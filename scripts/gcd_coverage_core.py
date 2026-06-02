from __future__ import annotations

import csv
import io
import math
import statistics
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable

from xivanalysis_gcd_rules import XIVANALYSIS_GCD_ACTION_RULES


# GCD 覆蓋率只保存衍生結果，不能把 FFLogs Casts raw events 寫入 repo。
# 這個模組不 import fetch_fflogs.py，讓 fetch 與 backfill 都能共用同一套本地 xivanalysis-like 計算。
ACTION_CSV_URL = "https://raw.githubusercontent.com/xivapi/ffxiv-datamining/master/csv/en/Action.csv"
STATUS_CSV_URL = "https://raw.githubusercontent.com/xivapi/ffxiv-datamining/master/csv/en/Status.csv"
GCD_ACTION_CATEGORY_IDS = {2, 3}  # 2=Spell, 3=Weaponskill
GCD_CALCULATION_VERSION = 20
GCD_SOURCE_CASTS_GRAPH = "fflogs_casts_graph"
GCD_SOURCE_RAW_EVENTS = "fflogs_raw_events"
GCD_SOURCE = GCD_SOURCE_CASTS_GRAPH
FFLOGS_STATUS_ID_OFFSET = 1_000_000
SUB_ATTRIBUTE_MINIMUM = 420
STAT_DIVISOR = 2780
BASE_GCD_MS = 2500
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
# raw events 能提供精準 targetability / unable-to-act，但不同職業的 timestamp 語意仍有差異。
# 這些 job 用下一個 GCD 夾住 raw 覆蓋區間，避免轉化或加速 GCD 被重疊加分。
# 忍者的 mudra/ninjutsu 在 xivanalysis 會以各自固定 lock 累加；若用下一個 timestamp 裁切，
# 會系統性低估高密度結印窗口的 Always Be Casting。
RAW_NEXT_GCD_CAPPED_JOBS = {"Monk", "Viper"}
RAW_EVENT_GCD_ENCOUNTERS = {
    "unreal_byakko",
    "extreme_queen_eternal",
    # 極瓦利加爾曼達的 Casts graph 不穩定回傳短暫 targetability /
    # UnableToAct downtime；固定 seed 抽樣中，DNC/WHM/RPR/SAM/VPR/DRG/SGE/Tank
    # 的差異都會在 raw events 分母下回到 xivanalysis 顯示值。
    "extreme_valigarmanda",
    # 極佐拉加與 AAC 零式的 Casts graph 會把部分 instant/長鎖 GCD 累加得比
    # xivanalysis legacy FFLogs 事件路徑更寬，特別容易讓 SAM/PCT/VPR 高估。
    # 抽樣案例改用 All raw events 後，分子與站端顯示值對齊。
    "extreme_zoraal_ja",
    "savage_m1s",
    "savage_m2s",
    "savage_m3s",
    "savage_m4s",
}
RAW_TARGETABILITY_ONLY_DOWNTIME_JOBS_BY_ENCOUNTER = {
    # 極永恆女王的 FFLogs Casts graph 會把部分短暫 boss downtime 放進
    # damageDowntime；xivanalysis raw-events 路徑對黑魔、舞者、繪靈法師、學者、
    # Monk、Samurai 與少數 Gunbreaker 樣本更接近只看 targetability / 玩家 UnableToAct 的分母。
    # 舞者若吃 graph downtime，部分 Technical / Standard 流程會因分母過短而高估
    # ABC；PCT/SCH 則先走 targetability-only，再由 SCH selector 處理少數 graph
    # lock 較貼近 xivanalysis 的 intermission-adjacent 樣本。PLD 在 100 場頁面稽核中
    # 改回 raw+graph downtime 更貼近站端，因此不放在 targetability-only 清單。
    "extreme_queen_eternal": {
        "BlackMage",
        "Dancer",
        "Gunbreaker",
        "Monk",
        "Pictomancer",
        "Samurai",
        "Scholar",
    },
}
RAW_NEXT_GCD_CAPPED_JOBS_BY_ENCOUNTER = {
    # 極瓦利加爾曼達的 Monk/Viper raw packet 已與 xivanalysis 的 lock 語意一致；
    # 若沿用幻白虎的下一個 GCD 裁切會少算 Perfect Balance 或 Viper 轉化後的覆蓋。
    "extreme_valigarmanda": set(),
    # 極佐拉加與 AAC 零式的 Monk/Viper raw events 需要保留站端累加語意；
    # 裁到下一個 timestamp 會讓 Perfect Balance 或 Viper 轉化窗口低估約一個 GCD。
    "extreme_zoraal_ja": set(),
    "savage_m1s": set(),
    "savage_m2s": set(),
    "savage_m3s": set(),
    "savage_m4s": set(),
    # 極永恆女王的 raw event timestamp 對武僧較接近 xivanalysis 的
    # CastTime lock 累加語意；若沿用幻白虎的 Monk 下一個 GCD 裁切，會把
    # 高速連段窗口少算約一個半 GCD。Gunbreaker 的 raw combo packet 會在
    # downtime-adjacent 間隔重疊加分；Machinist 的 Hypercharge/短 GCD raw packet
    # 在 Queen 少數樣本也會重疊高估，因此兩者需裁到下一個 GCD 才貼近 xivanalysis。
    "extreme_queen_eternal": (RAW_NEXT_GCD_CAPPED_JOBS - {"Monk"}) | {"Gunbreaker", "Machinist"},
}
# 幻白虎需要 raw events 推 downtime；少數 job 的 raw packet 語意仍已知會高估 ABC，
# 因此保留在 Casts graph 路徑。
RAW_EVENT_GCD_EXCLUDED_JOBS: set[str] = set()
RAW_EVENT_GCD_EXCLUDED_JOBS_BY_ENCOUNTER = {
    # 極佐拉加固定 seed 稽核中，Sage 的 Eukrasia / Eukrasian Prognosis II
    # raw events 會比 xivanalysis legacy 頁面多吃約兩到三個短 GCD lock；
    # 同批所有 SGE 樣本改用 Casts graph 仍與站端顯示值吻合，因此在這個副本
    # 讓賢者保留 graph 路徑，避免 raw packet 語意小幅高估 ABC。
    "extreme_zoraal_ja": {"Sage"},
    # AAC 零式 BLM raw event 會多吃部分 Ley Lines / instant packet 邊界；M2S-M4S
    # 在 100 場外站頁面稽核中改用 Casts graph 可明顯降低顯示百分比偏高。
    "savage_m2s": {"BlackMage"},
    "savage_m3s": {"BlackMage", "Scholar"},
    "savage_m4s": {"BlackMage", "Scholar"},
}
RAW_EVENT_GCD_REQUIRED_JOBS = {"Bard"}
# xivanalysis 的 legacy FFLogs raw-events 路徑在黑魔死亡事件落在 downtime 內的案例中，
# GCD uptime 會落在未套 source combatantinfo 詠速的 lock 長度；死亡不在 downtime 內的
# logging actor 仍會正常使用 combatantinfo。這個例外只影響幻白虎 raw-events 診斷/補算路徑。
RAW_EVENT_UNADJUSTED_SOURCE_SPEED_JOBS = {"BlackMage"}
TANK_JOBS = {"DarkKnight", "Gunbreaker", "Paladin", "Warrior"}
PCT_BYAKKO_GRAPH_DOWNTIME_DELTA_MIN = 0.75
PCT_BYAKKO_GRAPH_DOWNTIME_DELTA_MAX = 1.25
PCT_BYAKKO_GRAPH_DOWNTIME_RAW_PERCENT_MAX = 72.5
BLM_BYAKKO_GRAPH_FALLBACK_DELTA_MIN = 8.0
BLM_BYAKKO_RAW_DOWNTIME_GRAPH_OVERCOUNT_MIN = 1.0
BLM_BYAKKO_RAW_DOWNTIME_GRAPH_OVERCOUNT_MAX = 2.0
TANK_BYAKKO_MAIN_GAP_FALLBACK_DELTA_MIN = 1.25
TANK_BYAKKO_MAIN_GAP_RAW_PERCENT_MIN = 90.0
TANK_BYAKKO_UNCLAMPED_HIGH_UPTIME_RAW_MIN = 95.0
PALADIN_BYAKKO_GRAPH_FALLBACK_RAW_PERCENT_MIN = 90.0
PALADIN_BYAKKO_GRAPH_FALLBACK_DELTA_MIN = 0.95
PALADIN_BYAKKO_GRAPH_FALLBACK_DELTA_MAX = 1.05
BARD_ARMY_STATUS_IDS = {1932, 2218}  # Army's Muse / Army's Paeon
BARD_GRAPH_FALLBACK_ENCOUNTERS = {
    "extreme_queen_eternal",
    "extreme_valigarmanda",
    "extreme_zoraal_ja",
    "savage_m1s",
    "savage_m2s",
    "savage_m3s",
    "savage_m4s",
}
BARD_RAW_GRAPH_BLEND_RATIO = 0.22
BARD_RAW_GRAPH_BLEND_RATIO_BY_ENCOUNTER = {
    "savage_m1s": 0.30,
}
BARD_RAW_GRAPH_BLEND_RAW_PERCENT_MIN = 85.0
BARD_QUEEN_GRAPH_FALLBACK_RAW_PERCENT_MIN = 98.0
BARD_QUEEN_GRAPH_FALLBACK_GRAPH_PERCENT_MIN = 99.95
BARD_VALIGARMANDA_LOW_RAW_ADJUSTMENT_PERCENT_MIN = 80.0
BARD_VALIGARMANDA_LOW_RAW_ADJUSTMENT_PERCENT_MAX = 83.0
BARD_VALIGARMANDA_LOW_RAW_ADJUSTMENT = 0.75
BARD_VALIGARMANDA_GRAPH_FALLBACK_DELTA_MAX = 1.0
BARD_BYAKKO_HIGH_UPTIME_RAW_PERCENT_MIN = 98.5
BARD_BYAKKO_HIGH_UPTIME_GRAPH_PERCENT_MIN = 99.95
BARD_GRAPH_FALLBACK_RAW_PERCENT_MIN = 98.0
BARD_GRAPH_FALLBACK_GRAPH_PERCENT_MIN = 99.95
VALIGARMANDA_RDM_GRAPH_FALLBACK_RAW_PERCENT_MAX = 75.0
VALIGARMANDA_RDM_GRAPH_FALLBACK_DELTA_MIN = 1.0
VALIGARMANDA_RDM_GRAPH_FALLBACK_DELTA_MAX = 2.0
VALIGARMANDA_WHM_GRAPH_FALLBACK_RAW_PERCENT_MAX = 60.0
VALIGARMANDA_WHM_GRAPH_FALLBACK_DELTA_MIN = 1.0
VALIGARMANDA_WHM_GRAPH_FALLBACK_DELTA_MAX = 2.0
VALIGARMANDA_SMN_GRAPH_FALLBACK_RAW_PERCENT_MAX = 92.0
VALIGARMANDA_SMN_GRAPH_FALLBACK_DELTA_MIN = 0.8
VALIGARMANDA_SMN_GRAPH_FALLBACK_DELTA_MAX = 1.5
VALIGARMANDA_BLM_GRAPH_FALLBACK_DELTA_MIN = 0.4
VALIGARMANDA_BLM_GRAPH_FALLBACK_DELTA_MAX = 1.0
BYAKKO_RDM_GRAPH_FALLBACK_DELTA_MIN = 0.8
BYAKKO_RDM_GRAPH_FALLBACK_DELTA_MAX = 1.4
BYAKKO_RDM_GRAPH_FALLBACK_RAW_PERCENT_MAX = 75.0
BYAKKO_RDM_GRAPH_BLEND_RAW_PERCENT_MIN = 78.0
BYAKKO_RDM_GRAPH_BLEND_RAW_PERCENT_MAX = 84.0
BYAKKO_RDM_GRAPH_BLEND_DELTA_MIN = 1.4
BYAKKO_RDM_GRAPH_BLEND_DELTA_MAX = 1.8
BYAKKO_RDM_GRAPH_BLEND_RATIO = 0.5
QUEEN_RDM_RAW_FALLBACK_GRAPH_PERCENT_MAX = 89.0
QUEEN_RDM_RAW_FALLBACK_DELTA_MIN = 1.0
QUEEN_RDM_RAW_FALLBACK_DELTA_MAX = 2.5
QUEEN_SCH_GRAPH_FALLBACK_RAW_PERCENT_MAX = 90.0
QUEEN_SCH_GRAPH_FALLBACK_DELTA_MIN = 1.5
QUEEN_SCH_GRAPH_FALLBACK_DELTA_MAX = 3.0
PCT_INSPIRATION_STATUS_ID = 3689
PCT_RAINBOW_BRIGHT_STATUS_ID = 3679
PCT_RAINBOW_DRIP_ACTION_ID = 34688
PCT_HYPERPHANTASIA_ACTION_IDS = {
    34650,  # Fire in Red
    34651,  # Aero in Green
    34652,  # Water in Blue
    34653,  # Blizzard in Cyan
    34654,  # Stone in Yellow
    34655,  # Thunder in Magenta
    34656,  # Fire II in Red
    34657,  # Aero II in Green
    34658,  # Water II in Blue
    34659,  # Blizzard II in Cyan
    34660,  # Stone II in Yellow
    34661,  # Thunder II in Magenta
    34662,  # Holy in White
    34663,  # Comet in Black
    34681,  # Star Prism
}
DRAGOON_DRAGONSONG_DIVE_ACTION_ID = 4242
DRAGOON_COMBO_STARTER_ACTION_IDS = {
    75,     # True Thrust
    16479,  # Raiden Thrust
    86,     # Doom Spike
    25770,  # Draconian Fury
}

JOB_SPEED_MODIFIERS = {
    "Monk": 0.80,
    "Ninja": 0.85,
}


def raw_event_uses_targetability_only_downtime(encounter_key: str | None, job: str | None) -> bool:
    jobs = RAW_TARGETABILITY_ONLY_DOWNTIME_JOBS_BY_ENCOUNTER.get(str(encounter_key or ""))
    return bool(jobs and str(job or "") in jobs)


def raw_next_gcd_capped_jobs_for_encounter(encounter_key: str | None) -> set[str]:
    return set(RAW_NEXT_GCD_CAPPED_JOBS_BY_ENCOUNTER.get(str(encounter_key or ""), RAW_NEXT_GCD_CAPPED_JOBS))


def raw_event_excludes_job(encounter_key: str | None, job: str | None) -> bool:
    job_name = str(job or "")
    if job_name in RAW_EVENT_GCD_EXCLUDED_JOBS:
        return True
    encounter_jobs = RAW_EVENT_GCD_EXCLUDED_JOBS_BY_ENCOUNTER.get(str(encounter_key or ""))
    return bool(encounter_jobs and job_name in encounter_jobs)


def should_use_raw_events_for_gcd(encounter_key: str | None, job: str | None, *, force_raw_events: bool = False) -> bool:
    if force_raw_events:
        return True
    job_name = str(job or "")
    return job_name in RAW_EVENT_GCD_REQUIRED_JOBS or (
        str(encounter_key or "") in RAW_EVENT_GCD_ENCOUNTERS
        and not raw_event_excludes_job(encounter_key, job_name)
    )


def should_skip_raw_gcd_uptime(
    encounter_key: str | None,
    job: str | None,
    attempt: dict[str, Any],
    next_attempt: dict[str, Any] | None,
) -> bool:
    metadata = attempt.get("metadata")
    next_metadata = next_attempt.get("metadata") if next_attempt else None
    if not isinstance(metadata, ActionMetadata) or not isinstance(next_metadata, ActionMetadata):
        return False

    if (
        str(encounter_key or "") == "extreme_queen_eternal"
        and str(job or "") == "Dragoon"
        and metadata.action_id == DRAGOON_DRAGONSONG_DIVE_ACTION_ID
        and next_metadata.action_id in DRAGOON_COMBO_STARTER_ACTION_IDS
    ):
        # 極永恆女王的 CN7.5 龍騎樣本顯示，xivanalysis legacy FFLogs 轉接層在
        # `Drakesbane -> Dragonsong Dive -> Raiden/True Thrust` 這類連段循環邊界，
        # 等同沒有把 LB 這次長 recast 納入 ABC 分子；但 `Fang/Wheeling -> LB -> Drakesbane`
        # 的連段內 LB 仍會完整計入。這裡只把已驗證的邊界型態排除，避免回頭破壞
        # Queen 7.4 樣本中已對齊的龍騎 LB 覆蓋率。
        return True
    return False


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
    738: 0.85,   # Black Mage Circle of Power
    1299: 0.87,  # Samurai Fuka
    3669: 0.85,  # Viper Swiftscaled
    157: 0.80,   # White Mage Presence of Mind
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
    status_speed_adjusted: bool = True


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

GCD_ACTION_OVERRIDES.update(
    {
        action_id: GcdActionOverride(
            gcd_recast_ms=rule.gcd_recast_ms,
            speed_adjusted=rule.substat_adjusted,
            status_speed_adjusted=rule.status_speed_adjusted,
        )
        for action_id, rule in XIVANALYSIS_GCD_ACTION_RULES.items()
    }
)


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
    recast_status_adjusted: bool = True

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
                recast_status_adjusted=override.status_speed_adjusted if override else True,
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
        cast_start = timestamp
    elif cast_event:
        timestamp = to_number(cast_event.get("timestamp"))
        duration = 0
        action_id = event_action_id(cast_event, fallback_action_id)
        cast_start = timestamp
    else:
        return None

    if timestamp is None or action_id is None:
        return None

    return {
        "action_id": action_id,
        "timestamp": timestamp,
        "cast_start_timestamp": cast_start if cast_start is not None else timestamp,
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


def source_death_in_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    windows: list[tuple[float, float]],
) -> bool:
    if source_id is None:
        return False
    return any(
        str(event.get("type") or "") == "death"
        and to_int(event.get("targetID")) == source_id
        and timestamp_in_windows(to_number(event.get("timestamp")), windows)
        for event in raw_events
    )


def speed_stat_from_estimated_gcd_ms(estimated_gcd_ms: float) -> int:
    return math.floor(
        (STAT_DIVISOR * (1000 - (1000 * estimated_gcd_ms) / BASE_GCD_MS) / 130)
        + SUB_ATTRIBUTE_MINIMUM
    )


def select_pct_byakko_downtime_coverage(
    raw_targetability_coverage: dict[str, Any] | None,
    graph_downtime_coverage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not raw_targetability_coverage or not graph_downtime_coverage:
        return raw_targetability_coverage or graph_downtime_coverage

    raw_percent = to_number(raw_targetability_coverage.get("percent"))
    graph_percent = to_number(graph_downtime_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_targetability_coverage

    delta = graph_percent - raw_percent
    if (
        raw_percent <= PCT_BYAKKO_GRAPH_DOWNTIME_RAW_PERCENT_MAX
        and PCT_BYAKKO_GRAPH_DOWNTIME_DELTA_MIN <= delta <= PCT_BYAKKO_GRAPH_DOWNTIME_DELTA_MAX
    ):
        selected = dict(graph_downtime_coverage)
        selected["downtime_selection"] = "casts_graph_encounter_gap"
        selected["raw_targetability_percent"] = raw_targetability_coverage.get("percent")
        selected["raw_targetability_denominator_ms"] = raw_targetability_coverage.get("denominator_ms")
        # 幻白虎的 raw targetability 偶爾會比 xivanalysis 判定晚約 28 秒，
        # 主要出現在 PCT 可於 Boss 不可選取時持續使用自我 GCD 的 Starry Muse 窗。
        # 若改用 Casts graph 的 encounter gap 只移動約一個顯示百分點，實測會更貼近
        # xivanalysis；更大的差距通常代表 graph gap 過寬，仍以 raw targetability 為準。
        return selected

    return raw_targetability_coverage


def select_blm_byakko_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    raw_downtime_casts_graph_coverage: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or raw_downtime_casts_graph_coverage or casts_graph_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    raw_downtime_graph_percent = (
        to_number(raw_downtime_casts_graph_coverage.get("percent"))
        if raw_downtime_casts_graph_coverage
        else None
    )
    if (
        raw_downtime_casts_graph_coverage
        and raw_downtime_graph_percent is not None
        and BLM_BYAKKO_RAW_DOWNTIME_GRAPH_OVERCOUNT_MIN
        <= raw_percent - raw_downtime_graph_percent
        <= BLM_BYAKKO_RAW_DOWNTIME_GRAPH_OVERCOUNT_MAX
    ):
        selected = dict(raw_downtime_casts_graph_coverage)
        selected["fallback_selection"] = "black_mage_casts_graph_raw_downtime_moderate_raw_overcount"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
        selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
        # 幻白虎少數黑魔 log 會因 source combatantinfo / raw packet 邊界讓 raw action
        # lock 比 xivanalysis 顯示值高約一到兩個百分點。此時 Casts graph 的 GCD 嘗試
        # 搭配 raw targetability / UTA downtime 會更接近站端，同時避開前面已驗證的
        # 大幅低估 fallback 條件。
        return selected

    if (
        raw_downtime_casts_graph_coverage
        and raw_downtime_graph_percent is not None
        and raw_downtime_graph_percent - raw_percent >= BLM_BYAKKO_GRAPH_FALLBACK_DELTA_MIN
    ):
        selected = dict(raw_downtime_casts_graph_coverage)
        selected["fallback_selection"] = "black_mage_casts_graph_raw_downtime_large_raw_gap"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
        selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
        # 幻白虎黑魔 raw action packet 可能低估 GCD lock，但 xivanalysis 仍會把
        # raw targetability 與玩家 UnableToAct 視為分母修正來源。這種案例用 Casts
        # graph 的 GCD 嘗試搭配 raw downtime，會比單純 main-target damage gap 更貼近站端。
        return selected

    if graph_percent - raw_percent >= BLM_BYAKKO_GRAPH_FALLBACK_DELTA_MIN:
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "black_mage_casts_graph_large_raw_gap"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # 幻白虎的 raw action events 對 BLM Ley Lines / Circle of Power 期間的 GCD
        # 會偶發把 recast 壓得遠低於 xivanalysis 的 ABC 判定，導致高 uptime 玩家被
        # 低估十幾個百分點。只有當 Casts graph 與 raw events 的差距大到足以判定
        # raw packet 語意失真時才回退，避免影響前面已驗證正常的 BLM 樣本。
        return selected

    return raw_events_coverage


def select_red_mage_byakko_coverage(
    raw_targetability_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_targetability_coverage or not casts_graph_coverage:
        return raw_targetability_coverage or casts_graph_coverage
    if str(encounter_key or "") != "unreal_byakko":
        return raw_targetability_coverage

    raw_percent = to_number(raw_targetability_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_targetability_coverage

    delta = raw_percent - graph_percent
    if (
        raw_targetability_coverage.get("estimated_speed_below_minimum")
        and BYAKKO_RDM_GRAPH_BLEND_RAW_PERCENT_MIN <= raw_percent <= BYAKKO_RDM_GRAPH_BLEND_RAW_PERCENT_MAX
        and BYAKKO_RDM_GRAPH_BLEND_DELTA_MIN <= delta <= BYAKKO_RDM_GRAPH_BLEND_DELTA_MAX
    ):
        selected = dict(raw_targetability_coverage)
        adjusted_percent = raw_percent + (graph_percent - raw_percent) * BYAKKO_RDM_GRAPH_BLEND_RATIO
        selected["percent"] = round(adjusted_percent, 2)
        denominator_ms = to_number(raw_targetability_coverage.get("denominator_ms"))
        if denominator_ms is not None:
            selected["covered_time_ms"] = round(denominator_ms * selected["percent"] / 100)
        selected["fallback_selection"] = "byakko_red_mage_raw_graph_estimated_speed_blend"
        selected["raw_targetability_percent"] = raw_targetability_coverage.get("percent")
        selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
        selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
        # 幻白虎 RDM 低速反推樣本中，raw targetability 仍保留 Dualcast/instant
        # packet 語意，但少數 raw 與 Casts graph 相差約 1.5 個百分點時，
        # xivanalysis 顯示值會落在兩者中間，而非完全回退 graph。
        return selected

    if (
        raw_percent <= BYAKKO_RDM_GRAPH_FALLBACK_RAW_PERCENT_MAX
        and BYAKKO_RDM_GRAPH_FALLBACK_DELTA_MIN <= delta <= BYAKKO_RDM_GRAPH_FALLBACK_DELTA_MAX
    ):
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "byakko_red_mage_casts_graph_raw_overcount"
        selected["raw_targetability_percent"] = raw_targetability_coverage.get("percent")
        selected["raw_targetability_denominator_ms"] = raw_targetability_coverage.get("denominator_ms")
        # 幻白虎 RDM 的 Dualcast/instant raw packet 在少數低覆蓋率樣本會比
        # xivanalysis legacy 頁面多吃約一個百分點；當 Casts graph 只比 raw 低
        # 約 0.8-1.4 個百分點時，站端顯示更貼近 graph。
        return selected

    return raw_targetability_coverage


def select_tank_byakko_coverage(
    raw_targetability_coverage: dict[str, Any] | None,
    main_target_gap_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None = None,
    *,
    job: str | None = None,
) -> dict[str, Any] | None:
    if not raw_targetability_coverage or not main_target_gap_coverage:
        return raw_targetability_coverage or main_target_gap_coverage

    raw_percent = to_number(raw_targetability_coverage.get("percent"))
    main_gap_percent = to_number(main_target_gap_coverage.get("percent"))
    if raw_percent is None or main_gap_percent is None:
        return raw_targetability_coverage

    graph_percent = to_number(casts_graph_coverage.get("percent")) if casts_graph_coverage else None
    if (
        str(job or "") == "Paladin"
        and graph_percent is not None
        and raw_targetability_coverage.get("estimated_speed_below_minimum")
        and raw_percent >= PALADIN_BYAKKO_GRAPH_FALLBACK_RAW_PERCENT_MIN
    ):
        graph_delta = raw_percent - graph_percent
        if PALADIN_BYAKKO_GRAPH_FALLBACK_DELTA_MIN <= graph_delta <= PALADIN_BYAKKO_GRAPH_FALLBACK_DELTA_MAX:
            selected = dict(casts_graph_coverage)
            selected["fallback_selection"] = "paladin_byakko_casts_graph_estimated_speed_gap"
            selected["raw_targetability_percent"] = raw_targetability_coverage.get("percent")
            selected["raw_targetability_denominator_ms"] = raw_targetability_coverage.get("denominator_ms")
            # 幻白虎 PLD 若缺 combatantinfo 且 raw 比 Casts graph 高約 1%，
            # xivanalysis 在這批外站稽核中更接近 graph 的 lock/分母組合。
            # 條件刻意限縮在高覆蓋率與約 1% gap，避免一般坦克樣本被 graph 低估。
            return selected

    if (
        raw_targetability_coverage.get("estimated_speed_below_minimum")
        and raw_percent >= TANK_BYAKKO_UNCLAMPED_HIGH_UPTIME_RAW_MIN
    ):
        # xivanalysis 會保留低於 420 的反推副屬性；這會自然拉長 GCD lock。高覆蓋率坦克
        # 若再套 main-target damage gap，等於同時放大分子與縮小分母，會比站端高估。
        return raw_targetability_coverage

    if (
        raw_percent >= TANK_BYAKKO_MAIN_GAP_RAW_PERCENT_MIN
        and main_gap_percent - raw_percent >= TANK_BYAKKO_MAIN_GAP_FALLBACK_DELTA_MIN
    ):
        selected = dict(main_target_gap_coverage)
        selected["fallback_selection"] = "tank_main_target_damage_gap"
        selected["raw_targetability_percent"] = raw_targetability_coverage.get("percent")
        selected["raw_targetability_denominator_ms"] = raw_targetability_coverage.get("denominator_ms")
        # 幻白虎少數坦克 log 的 raw targetability 會晚於 xivanalysis 的主目標不可攻擊窗；
        # 只在高覆蓋率且主目標傷害空窗版本明顯較高時回退，避免低/中覆蓋率坦克被
        # Casts graph 的 encounter gap 誤判成更接近站端。
        return selected

    return raw_targetability_coverage


def select_bard_raw_event_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or casts_graph_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    if str(encounter_key or "") == "unreal_byakko":
        if (
            raw_events_coverage.get("speed_stat_source") == "combatantinfo"
            and raw_percent >= BARD_BYAKKO_HIGH_UPTIME_RAW_PERCENT_MIN
            and graph_percent >= BARD_BYAKKO_HIGH_UPTIME_GRAPH_PERCENT_MIN
        ):
            selected = dict(casts_graph_coverage)
            selected["fallback_selection"] = "bard_casts_graph_byakko_high_uptime"
            selected["raw_events_percent"] = raw_events_coverage.get("percent")
            selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
            # 幻白虎 Bard 在 combatantinfo 可用且 raw 已接近滿覆蓋時，xivanalysis
            # checklist 會把最後一小段 Army/encounter gap 邊界顯示為 100%。低於此門檻
            # 的樣本仍保留 raw events，避免 graph 高估 Army 排除窗。
            return selected
        return raw_events_coverage

    if str(encounter_key or "") not in BARD_GRAPH_FALLBACK_ENCOUNTERS:
        return raw_events_coverage

    if (
        raw_events_coverage.get("estimated_speed_below_minimum")
        and raw_percent >= BARD_GRAPH_FALLBACK_RAW_PERCENT_MIN
        and graph_percent >= BARD_GRAPH_FALLBACK_GRAPH_PERCENT_MIN
    ):
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "bard_casts_graph_high_uptime_estimated_speed"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # 少數 AAC / Zoraal Bard 缺 combatantinfo 時，raw interval 會反推到低於遊戲
        # 實際下限的副屬性；xivanalysis 頁面在接近滿覆蓋的樣本更接近 Casts graph 的
        # 100% 顯示值。只對 estimated_speed_below_minimum 且 graph 幾乎滿覆蓋時回退。
        return selected

    if raw_events_coverage.get("estimated_speed_below_minimum"):
        selected = dict(raw_events_coverage)
        selected["fallback_selection"] = "bard_raw_events_low_estimated_speed_kept_raw"
        selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
        selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
        # xivanalysis 會保留低於 420 的反推副屬性；非接近滿覆蓋的 Bard 樣本若再混入
        # Casts graph lock，會把 Army 窗口後的 raw-events 分母語意高估。只有上方高覆蓋率
        # 分支可回退 graph，其餘低速反推樣本保留 raw-events。
        return selected

    if str(encounter_key or "") == "extreme_queen_eternal":
        if (
            raw_percent >= BARD_QUEEN_GRAPH_FALLBACK_RAW_PERCENT_MIN
            and graph_percent >= BARD_QUEEN_GRAPH_FALLBACK_GRAPH_PERCENT_MIN
        ):
            selected = dict(casts_graph_coverage)
            selected["fallback_selection"] = "bard_casts_graph_queen_high_uptime"
            selected["raw_events_percent"] = raw_events_coverage.get("percent")
            selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
            # Queen 高覆蓋率 Bard 樣本中，xivanalysis legacy 頁面與 Casts graph /
            # no-Army raw path 同樣顯示 100%。只有 raw 已接近滿覆蓋且 graph 幾乎滿
            # 時才回退，避免一般 Army 排除窗樣本被 graph 高估。
            return selected
        return raw_events_coverage

    if str(encounter_key or "") == "extreme_valigarmanda":
        graph_delta = graph_percent - raw_percent
        if 0 < graph_delta <= BARD_VALIGARMANDA_GRAPH_FALLBACK_DELTA_MAX:
            if (
                BARD_VALIGARMANDA_LOW_RAW_ADJUSTMENT_PERCENT_MIN
                <= raw_percent
                <= BARD_VALIGARMANDA_LOW_RAW_ADJUSTMENT_PERCENT_MAX
            ):
                selected = dict(raw_events_coverage)
                adjusted_percent = max(0.0, raw_percent - BARD_VALIGARMANDA_LOW_RAW_ADJUSTMENT)
                selected["percent"] = round(adjusted_percent, 2)
                denominator_ms = to_number(raw_events_coverage.get("denominator_ms"))
                if denominator_ms is not None:
                    selected["covered_time_ms"] = round(denominator_ms * selected["percent"] / 100)
                selected["fallback_selection"] = "bard_raw_events_valigarmanda_low_uptime_army_adjustment"
                selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
                selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
                # 低覆蓋率 Valigarmanda Bard 的 Army 窗口結束點在 raw events 與
                # xivanalysis 顯示間會有約一個顯示百分點的差距。只在 raw 約 80-83%
                # 且 graph 只略高於 raw 時修正，避免高覆蓋率樣本被低估。
                return selected
            selected = dict(casts_graph_coverage)
            selected["fallback_selection"] = "bard_casts_graph_valigarmanda_small_raw_gap"
            selected["raw_events_percent"] = raw_events_coverage.get("percent")
            selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
            # 極瓦利加爾曼達 Bard 有兩種型態：Army 排除窗造成 graph 比 raw 高很多時，
            # xivanalysis 仍貼近 raw；但若 graph 只高約半個百分點，站端顯示會更接近
            # Casts graph 的 GCD lock。此分支只處理小差距，避免破壞低覆蓋率詩人樣本。
            return selected
        return raw_events_coverage

    if graph_percent > raw_percent and raw_percent >= BARD_RAW_GRAPH_BLEND_RAW_PERCENT_MIN:
        selected = dict(raw_events_coverage)
        blend_ratio = BARD_RAW_GRAPH_BLEND_RATIO_BY_ENCOUNTER.get(
            str(encounter_key or ""),
            BARD_RAW_GRAPH_BLEND_RATIO,
        )
        adjusted_percent = min(100.0, raw_percent + (graph_percent - raw_percent) * blend_ratio)
        selected["percent"] = round(adjusted_percent, 2)
        denominator_ms = to_number(raw_events_coverage.get("denominator_ms"))
        if denominator_ms is not None:
            selected["covered_time_ms"] = round(denominator_ms * selected["percent"] / 100)
        selected["fallback_selection"] = "bard_raw_events_with_casts_graph_lock_blend"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
        selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
        # AAC / Zoraal 的 Bard 在中高覆蓋率 Army 排除窗內仍會受 FFLogs raw packet 與
        # Casts graph lock 語意差異影響。xivanalysis 顯示值落在兩者之間；固定 seed 樣本
        # 顯示以 raw 分母為主、只混入少量 graph lock，可同時對齊 89%、94% 與接近
        # 100% 的 Bard。低覆蓋率樣本則仍貼近 raw events，不套這個混合修正。
        return selected

    return raw_events_coverage


def select_valigarmanda_white_mage_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or casts_graph_coverage
    if str(encounter_key or "") != "extreme_valigarmanda":
        return raw_events_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    delta = raw_percent - graph_percent
    if (
        raw_percent <= VALIGARMANDA_WHM_GRAPH_FALLBACK_RAW_PERCENT_MAX
        and VALIGARMANDA_WHM_GRAPH_FALLBACK_DELTA_MIN <= delta <= VALIGARMANDA_WHM_GRAPH_FALLBACK_DELTA_MAX
    ):
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "valigarmanda_white_mage_casts_graph_low_uptime"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # 極瓦利加爾曼達 WHM 多數樣本需要 raw downtime；但低 ABC 且 raw 只比 graph
        # 高約一到兩個百分點時，raw targetability/UTA 會把 Presence of Mind 附近
        # 的 lock 吃得略滿。此時回 Casts graph 會更貼近 xivanalysis 顯示值。
        return selected

    return raw_events_coverage


def select_valigarmanda_summoner_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or casts_graph_coverage
    if str(encounter_key or "") != "extreme_valigarmanda":
        return raw_events_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    delta = raw_percent - graph_percent
    if (
        raw_events_coverage.get("speed_stat_source") == "estimated"
        and raw_percent <= VALIGARMANDA_SMN_GRAPH_FALLBACK_RAW_PERCENT_MAX
        and VALIGARMANDA_SMN_GRAPH_FALLBACK_DELTA_MIN <= delta <= VALIGARMANDA_SMN_GRAPH_FALLBACK_DELTA_MAX
    ):
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "valigarmanda_summoner_casts_graph_estimated_speed_gap"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # 極瓦利加爾曼達 Summoner 大多數樣本 raw events 已貼近 xivanalysis；但缺
        # combatantinfo、且 raw 只比 Casts graph 高約一個百分點的中低覆蓋率樣本，
        # 站端顯示更接近 graph lock。限縮在 estimated speed 與 92% 以下避免破壞
        # 原本已對齊的高覆蓋率召喚樣本。
        return selected

    return raw_events_coverage


def select_valigarmanda_black_mage_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or casts_graph_coverage
    if str(encounter_key or "") != "extreme_valigarmanda":
        return raw_events_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    delta = raw_percent - graph_percent
    if VALIGARMANDA_BLM_GRAPH_FALLBACK_DELTA_MIN <= delta <= VALIGARMANDA_BLM_GRAPH_FALLBACK_DELTA_MAX:
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "valigarmanda_black_mage_casts_graph_raw_overcount"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # 極瓦利加爾曼達 BLM 的 raw events 多數仍需 raw downtime；但當 graph
        # 只比 raw 低約半到一個百分點時，xivanalysis 頁面更貼近 Casts graph 的
        # Ley Lines / instant packet 邊界。
        return selected

    return raw_events_coverage


def select_valigarmanda_red_mage_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or casts_graph_coverage
    if str(encounter_key or "") != "extreme_valigarmanda":
        return raw_events_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    delta = raw_percent - graph_percent
    if (
        raw_percent <= VALIGARMANDA_RDM_GRAPH_FALLBACK_RAW_PERCENT_MAX
        and VALIGARMANDA_RDM_GRAPH_FALLBACK_DELTA_MIN <= delta <= VALIGARMANDA_RDM_GRAPH_FALLBACK_DELTA_MAX
    ):
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "valigarmanda_red_mage_casts_graph_low_uptime"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # 極瓦利加爾曼達赤魔在低 ABC 樣本中，raw events 會把 Dualcast/instant GCD
        # 視窗吃得比 xivanalysis 頁面更滿；但高覆蓋率樣本仍需保留 raw lock。
        # 因此只在 raw 與 graph 相差約一個半百分點、且 raw 本身低於 75% 時回退。
        return selected

    return raw_events_coverage


def select_queen_scholar_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return raw_events_coverage or casts_graph_coverage
    if str(encounter_key or "") != "extreme_queen_eternal":
        return raw_events_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return raw_events_coverage

    delta = graph_percent - raw_percent
    if (
        raw_percent <= QUEEN_SCH_GRAPH_FALLBACK_RAW_PERCENT_MAX
        and QUEEN_SCH_GRAPH_FALLBACK_DELTA_MIN <= delta <= QUEEN_SCH_GRAPH_FALLBACK_DELTA_MAX
    ):
        selected = dict(casts_graph_coverage)
        selected["fallback_selection"] = "queen_scholar_casts_graph_intermission_gap"
        selected["raw_events_percent"] = raw_events_coverage.get("percent")
        selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
        # Queen SCH 預設仍走 targetability-only raw downtime，避免短 intermission
        # 讓分母過度縮短；但固定 seed 新樣本顯示，若 raw 比 Casts graph 低約兩個
        # 百分點，xivanalysis legacy 頁面會貼近 graph 的 GCD lock 與 downtime 組合。
        return selected

    return raw_events_coverage


def select_queen_red_mage_coverage(
    raw_events_coverage: dict[str, Any] | None,
    casts_graph_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not casts_graph_coverage:
        return casts_graph_coverage or raw_events_coverage
    if str(encounter_key or "") != "extreme_queen_eternal":
        return raw_events_coverage

    raw_percent = to_number(raw_events_coverage.get("percent"))
    graph_percent = to_number(casts_graph_coverage.get("percent"))
    if raw_percent is None or graph_percent is None:
        return casts_graph_coverage

    delta = raw_percent - graph_percent
    if (
        graph_percent <= QUEEN_RDM_RAW_FALLBACK_GRAPH_PERCENT_MAX
        and QUEEN_RDM_RAW_FALLBACK_DELTA_MIN <= delta <= QUEEN_RDM_RAW_FALLBACK_DELTA_MAX
    ):
        selected = dict(raw_events_coverage)
        selected["fallback_selection"] = "queen_red_mage_raw_events_low_graph_uptime"
        selected["casts_graph_percent"] = casts_graph_coverage.get("percent")
        selected["casts_graph_denominator_ms"] = casts_graph_coverage.get("denominator_ms")
        # Queen RDM 預設仍保守採 Casts graph，避免 Dualcast / instant GCD 在 raw events
        # 中被吃得過滿；但固定 seed 新樣本顯示，低覆蓋率且 raw 只比 graph 高約一到
        # 兩個百分點時，xivanalysis legacy 頁面會貼近 raw targetability/UTA 分母。
        return selected

    return casts_graph_coverage


def select_savage_m1s_black_mage_coverage(
    raw_events_coverage: dict[str, Any] | None,
    graph_downtime_coverage: dict[str, Any] | None,
    *,
    encounter_key: str | None,
    job: str | None,
) -> dict[str, Any] | None:
    if not raw_events_coverage or not graph_downtime_coverage:
        return raw_events_coverage or graph_downtime_coverage
    if str(encounter_key or "") != "savage_m1s" or str(job or "") != "BlackMage":
        return raw_events_coverage

    selected = dict(graph_downtime_coverage)
    selected["fallback_selection"] = "m1s_black_mage_raw_events_graph_downtime"
    selected["raw_events_percent"] = raw_events_coverage.get("percent")
    selected["raw_events_denominator_ms"] = raw_events_coverage.get("denominator_ms")
    # M1S 的 BLM raw targetability/UTA downtime 在 Ley Lines 與轉場 packet 邊界會讓
    # ABC 分母略短、分子略滿；同一批 100 場外站頁面稽核中，raw action events 搭配
    # Casts graph downtime 才貼近 xivanalysis legacy FFLogs adapter 的顯示百分比。
    return selected


def estimate_speed_stats_from_attempts(
    attempts: list[dict[str, Any]],
    *,
    job: str | None,
    speed_windows: list[SpeedModifierWindow],
) -> dict[str, int]:
    # xivanalysis 在 FFLogs 沒有 combatantinfo 副屬性時，會由 GCD 事件間隔反推
    # tooltip GCD，再轉回技速/詠速。這段對齊該流程，而不是直接把 3.3s / 6s
    # 長 GCD 的 raw interval 當成該 base recast 的實際倍率，避免 PCT 等職業被估歪。
    intervals_by_attribute: dict[str, list[float]] = {
        "skill_speed": [],
        "spell_speed": [],
    }
    for index, current in enumerate(attempts[1:], start=1):
        previous = attempts[index - 1]
        if previous.get("interrupted"):
            continue
        metadata = previous.get("metadata")
        if (
            not isinstance(metadata, ActionMetadata)
            or not metadata.recast_speed_adjusted
            or metadata.action_id in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS
        ):
            continue

        attribute_key: str | None = None
        if metadata.action_category_id == 2:
            attribute_key = "spell_speed"
        elif metadata.action_category_id == 3:
            attribute_key = "skill_speed"
        if attribute_key is None:
            continue

        previous_start = first_number(previous.get("cast_start_timestamp"), previous.get("timestamp"))
        current_start = first_number(current.get("cast_start_timestamp"), current.get("timestamp"))
        if previous_start is None or current_start is None:
            continue

        raw_interval = current_start - previous_start
        if raw_interval <= 0:
            continue

        recast_for_scale = metadata.effective_recast_ms or BASE_GCD_MS
        has_animation_lock = False
        if to_number(previous.get("cast_duration_ms")) and metadata.cast_ms >= BASE_GCD_MS:
            has_animation_lock = True
            recast_for_scale = metadata.cast_ms

        speed_modifier = speed_modifier_at_timestamp(previous_start, job=job, speed_windows=speed_windows)
        if speed_modifier <= 0:
            continue

        adjusted_interval = (
            (raw_interval - (100 if has_animation_lock else 0))
            / (recast_for_scale / BASE_GCD_MS)
            / speed_modifier
        )
        if adjusted_interval > 0:
            intervals_by_attribute[attribute_key].append(adjusted_interval)

    estimated_stats: dict[str, int] = {}
    for attribute_key, intervals in intervals_by_attribute.items():
        if not intervals:
            continue
        estimated_gcd = estimate_recast_from_xivanalysis_batches(intervals)
        if estimated_gcd > 0:
            # xivanalysis 的 SpeedStatsAdapterStep 會把反推副屬性原樣寫入 actorUpdate；
            # 即使 FFLogs 間隔讓結果低於遊戲實際下限 420，後續 CastTime 仍會使用該值。
            # 本地必須保留這個站端語意，否則少量遠距魔法 GCD 會被壓回 2.50s 而低估 ABC。
            estimated_stats[attribute_key] = speed_stat_from_estimated_gcd_ms(estimated_gcd)
    return estimated_stats


def raw_speed_modifier_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    fight_end_time: float | None,
    extra_status_modifiers_by_status_id: dict[int, float] | None = None,
) -> list[SpeedModifierWindow]:
    if source_id is None:
        return []

    status_modifiers_by_status_id = {
        **RAW_SPEED_STATUS_MODIFIERS_BY_STATUS_ID,
        **(extra_status_modifiers_by_status_id or {}),
    }
    windows: list[SpeedModifierWindow] = []
    active_status_windows: dict[int, tuple[float, float | None, float, str]] = {}
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
                modifier = status_modifiers_by_status_id.get(status_id)
                if modifier is None:
                    continue
                duration = to_number(aura.get("duration"))
                fallback_end = timestamp + duration if duration else fight_end_time
                active_status_windows.setdefault(
                    status_id,
                    (
                        timestamp,
                        fallback_end,
                        modifier,
                        f"initial status {status_id}",
                    ),
                )
            continue

        event_type = str(event.get("type") or "")
        if event_type not in RAW_STATUS_APPLY_EVENT_TYPES and event_type not in RAW_STATUS_REMOVE_EVENT_TYPES:
            continue
        if to_int(event.get("targetID")) != source_id:
            continue
        status_id = event_status_id(event)
        if status_id is None:
            continue
        modifier = status_modifiers_by_status_id.get(status_id)
        if modifier is None:
            continue

        if event_type in RAW_STATUS_APPLY_EVENT_TYPES:
            duration = to_number(event.get("duration"))
            fallback_end = timestamp + duration if duration else fight_end_time
            if status_id in active_status_windows:
                start, existing_fallback_end, active_modifier, label = active_status_windows[status_id]
                # xivanalysis 的 CastTime 調整由 apply/remove 驅動；refresh 只在缺少
                # remove 時當成 fallback，避免 Circle of Power 這類地板 buff 在離開後
                # 仍因 FFLogs refresh duration 被誤延長。
                if fallback_end is not None:
                    fallback_end = max(existing_fallback_end or fallback_end, fallback_end)
                else:
                    fallback_end = existing_fallback_end
                active_status_windows[status_id] = (start, fallback_end, active_modifier, label)
            else:
                active_status_windows[status_id] = (
                    timestamp,
                    fallback_end,
                    modifier,
                    f"status {status_id}",
                )
            continue

        active_window = active_status_windows.pop(status_id, None)
        if active_window is None:
            continue
        start, _fallback_end, active_modifier, label = active_window
        if timestamp > start:
            windows.append(
                SpeedModifierWindow(
                    start_ms=start,
                    end_ms=min(timestamp, fight_end_time) if fight_end_time is not None else timestamp,
                    modifier=active_modifier,
                    label=label,
                )
            )

    for start, fallback_end, modifier, label in active_status_windows.values():
        end_ms = fallback_end if fallback_end is not None else fight_end_time
        if end_ms is None:
            continue
        windows.append(
            SpeedModifierWindow(
                start_ms=start,
                end_ms=min(end_ms, fight_end_time) if fight_end_time is not None else end_ms,
                modifier=modifier,
                label=label,
            )
        )

    return merge_speed_modifier_windows([window for window in windows if window.end_ms > window.start_ms])


def raw_status_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    status_ids: set[int],
    fight_end_time: float | None,
) -> list[tuple[float, float]]:
    if source_id is None or not status_ids:
        return []

    windows: list[tuple[float, float]] = []
    active_start: float | None = None

    def event_order_key(event: dict[str, Any]) -> tuple[float, int]:
        timestamp = to_number(event.get("timestamp"))
        event_type = str(event.get("type") or "")
        priority = 1
        if event_type in RAW_STATUS_REMOVE_EVENT_TYPES:
            priority = 0
        # FFLogs All raw events can place Army's Muse apply before Army's Paeon remove at
        # the exact same timestamp. xivanalysis' final ABC result behaves as if the old
        # Army window closes before the next one opens, so normalize same-timestamp status
        # transitions here while keeping original order for all other ties.
        return (timestamp if timestamp is not None else 0, priority)

    for event in sorted(raw_events, key=event_order_key):
        timestamp = to_number(event.get("timestamp"))
        if timestamp is None:
            continue

        if event.get("type") == "combatantinfo":
            for aura in event.get("auras") or []:
                if not isinstance(aura, dict):
                    continue
                raw_status_id = to_int(aura.get("ability"))
                if raw_status_id is None:
                    continue
                status_id = raw_status_id - FFLOGS_STATUS_ID_OFFSET if raw_status_id >= FFLOGS_STATUS_ID_OFFSET else raw_status_id
                if status_id not in status_ids:
                    continue
                # xivanalysis legacy adapter maps combatantinfo aura source from aura.source,
                # not from the actor receiving combatantinfo. Bard Army windows filter by
                # source only, so a party member's combatantinfo can open the Bard's
                # exclusion window when that aura came from this Bard.
                if to_int(aura.get("source")) != source_id:
                    continue
                if active_start is None:
                    active_start = timestamp
            continue

        event_type = str(event.get("type") or "")
        if event_type not in RAW_STATUS_APPLY_EVENT_TYPES and event_type not in RAW_STATUS_REMOVE_EVENT_TYPES:
            continue
        if event_source_id(event) != source_id:
            continue
        status_id = event_status_id(event)
        if status_id is None or status_id not in status_ids:
            continue

        if event_type in RAW_STATUS_APPLY_EVENT_TYPES:
            # xivanalysis 的 BRD Army 排除是 source-only filter，沒有綁 target。
            # 因此隊友身上的 refresh/apply 會在目前沒有開窗時重新開窗，任一 remove
            # 也會先關掉 currentArmy。這看起來反直覺，但正是站端模組的事件語意。
            if active_start is None:
                active_start = timestamp
            continue

        if active_start is not None and timestamp > active_start:
            windows.append((active_start, timestamp))
        active_start = None

    if active_start is not None and fight_end_time is not None and fight_end_time > active_start:
        windows.append((active_start, fight_end_time))

    return merge_time_windows(windows)


def raw_target_status_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    status_ids: set[int],
    fight_end_time: float | None,
) -> dict[int, list[tuple[float, float]]]:
    if source_id is None or not status_ids:
        return {}

    windows_by_status: dict[int, list[tuple[float, float]]] = {status_id: [] for status_id in status_ids}
    active_by_status: dict[int, float] = {}
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
                if status_id not in status_ids or status_id in active_by_status:
                    continue
                active_by_status[status_id] = timestamp
            continue

        event_type = str(event.get("type") or "")
        if event_type not in RAW_STATUS_APPLY_EVENT_TYPES and event_type not in RAW_STATUS_REMOVE_EVENT_TYPES:
            continue
        if to_int(event.get("targetID")) != source_id:
            continue
        status_id = event_status_id(event)
        if status_id is None or status_id not in status_ids:
            continue

        if event_type in RAW_STATUS_APPLY_EVENT_TYPES:
            if status_id not in active_by_status:
                active_by_status[status_id] = timestamp
            continue

        start = active_by_status.pop(status_id, None)
        if start is not None and timestamp >= start:
            windows_by_status[status_id].append((start, timestamp))

    if fight_end_time is not None:
        for status_id, start in active_by_status.items():
            if fight_end_time >= start:
                windows_by_status[status_id].append((start, fight_end_time))

    return {
        status_id: merge_time_windows(windows)
        for status_id, windows in windows_by_status.items()
        if windows
    }


def job_gcd_exclusion_windows(
    raw_events: list[dict[str, Any]],
    *,
    source_id: int | None,
    job: str | None,
    fight_end_time: float | None,
) -> list[tuple[float, float]]:
    if str(job) == "Bard":
        # xivanalysis 的 BRD AlwaysBeCasting 會排除 Army's Paeon / Army's Muse：
        # 這兩個狀態的 GCD 加速層數無法可靠合成，因此 buff 期間的 GCD 不進分子，
        # buff 時間也會從 ABC 分母扣除。
        return raw_status_windows(
            raw_events,
            source_id=source_id,
            status_ids=BARD_ARMY_STATUS_IDS,
            fight_end_time=fight_end_time,
        )
    return []


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


def extract_gcd_speed_estimation_attempts_from_raw_events(
    raw_events: list[dict[str, Any]],
    metadata_store: ActionMetadataStore,
    *,
    source_id: int | None = None,
) -> list[dict[str, Any]]:
    # xivanalysis 的 SpeedStatsAdapterStep 會把 interrupted prepare 留在 GCD 序列中；
    # 速度反推時只跳過「前一個 GCD 被中斷」的區間。若本地只看完成的 cast，會把
    # 中斷讀條前後兩段間隔合併成一段過長 GCD，進而反推出低於實際值的技速/詠速。
    attempts: list[dict[str, Any]] = []
    pending_index_by_source: dict[int, int] = {}

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

        timestamp = to_number(event.get("timestamp"))
        if timestamp is None:
            continue

        if event_type == "begincast":
            attempts.append(
                {
                    "action_id": action_id,
                    "timestamp": timestamp,
                    "cast_start_timestamp": timestamp,
                    "cast_duration_ms": to_number(event.get("duration")) or 0,
                    "source_id": event_source,
                    "metadata": metadata,
                    "interrupted": True,
                }
            )
            if event_source is not None:
                pending_index_by_source[event_source] = len(attempts) - 1
            continue

        pending_index = pending_index_by_source.pop(event_source, None) if event_source is not None else None
        if pending_index is not None and attempts[pending_index].get("action_id") == action_id:
            attempts[pending_index]["timestamp"] = timestamp
            attempts[pending_index]["interrupted"] = False
            continue

        attempts.append(
            {
                "action_id": action_id,
                "timestamp": timestamp,
                "cast_start_timestamp": timestamp,
                "cast_duration_ms": 0,
                "source_id": event_source,
                "metadata": metadata,
                "interrupted": False,
            }
        )

    attempts.sort(
        key=lambda attempt: (
            first_number(attempt.get("cast_start_timestamp"), attempt.get("timestamp")) or 0,
            attempt["action_id"],
        )
    )
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


def status_speed_modifier_at_timestamp(
    timestamp: float,
    *,
    speed_windows: list[SpeedModifierWindow],
) -> float:
    modifier = 1.0
    for window in speed_windows:
        if window.start_ms <= timestamp <= window.end_ms:
            modifier *= window.modifier
    return modifier


def raw_recast_ms(
    attempt: dict[str, Any],
    *,
    speed_stats: dict[str, int],
    job: str | None,
    speed_windows: list[SpeedModifierWindow],
    status_windows_by_status_id: dict[int, list[tuple[float, float]]] | None = None,
    first_gcd_timestamp: float | None = None,
) -> float:
    metadata = attempt["metadata"]
    base_recast = metadata.effective_recast_ms
    timestamp = to_number(attempt.get("timestamp"))
    cast_duration = to_number(attempt.get("cast_duration_ms")) or 0
    recast_flat_adjustment = 0.0
    if (
        str(job) == "Pictomancer"
        and metadata.action_id == PCT_RAINBOW_DRIP_ACTION_ID
        and timestamp is not None
        and (
            timestamp_in_windows_inclusive(
                timestamp,
                (status_windows_by_status_id or {}).get(PCT_RAINBOW_BRIGHT_STATUS_ID, []),
            )
            or (cast_duration <= 0 and first_gcd_timestamp is not None and timestamp == first_gcd_timestamp)
        )
    ):
        # xivanalysis 的 PCT Procs 模組在 Rainbow Bright 被 Rainbow Drip 消耗的當下，
        # 先讓 6 秒 recast 吃詠速，再套 -3500ms flat adjustment；不是直接改成
        # 2500ms。Casts graph 會把 proc 後的 Rainbow Drip 呈現為 0ms cast，因此
        # raw events 診斷路徑也用 cast_duration 作為 status 事件缺漏時的 fallback。
        recast_flat_adjustment = -3500.0
    if not metadata.recast_speed_adjusted or metadata.action_id in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS:
        recast = float(base_recast)
    else:
        attribute_key = "spell_speed" if metadata.action_category_id == 2 else "skill_speed"
        recast = speed_stat_adjusted_duration_ms(speed_stats.get(attribute_key), base_recast)
    if recast_flat_adjustment:
        recast = max(float(MIN_RECAST_TIME_MS), recast + recast_flat_adjustment)
    if timestamp is not None and metadata.recast_status_adjusted:
        if metadata.recast_speed_adjusted and metadata.action_id not in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS:
            recast *= speed_modifier_at_timestamp(timestamp, job=job, speed_windows=speed_windows)
        else:
            # xivanalysis 的 Monk/Ninja 被動加速在 SpeedAdjustments 層，只會套到有
            # speedAttribute 的 action。固定 recast action 仍可吃 Fuka、Swiftscaled
            # 這類 CastTime percentage status，但不吃職業被動速度。
            recast *= status_speed_modifier_at_timestamp(timestamp, speed_windows=speed_windows)
        if (
            str(job) == "Pictomancer"
            and metadata.action_id in PCT_HYPERPHANTASIA_ACTION_IDS
            and timestamp_in_windows_inclusive(
                timestamp,
                (status_windows_by_status_id or {}).get(PCT_INSPIRATION_STATUS_ID, []),
            )
        ):
            # Inspiration 並不是全域施法加速；xivanalysis 只把它掛到
            # HYPERPHANTASIA_SPELLS，避免 Motif / Hammer 等其他 GCD 被誤縮短。
            recast *= 0.75
    if base_recast > MIN_RECAST_TIME_MS:
        recast = max(float(MIN_RECAST_TIME_MS), recast)
    return floor_to_10_ms(recast)


def adjusted_cast_ms_for_uptime(
    attempt: dict[str, Any],
    *,
    job: str | None,
    speed_windows: list[SpeedModifierWindow],
    speed_stats: dict[str, int] | None = None,
    default_speed_multiplier: float | None = None,
    recast_timing: RecastTimingEstimate | None = None,
    status_windows_by_status_id: dict[int, list[tuple[float, float]]] | None = None,
    first_gcd_timestamp: float | None = None,
) -> float:
    metadata = attempt["metadata"]
    observed_cast_ms = to_number(attempt.get("cast_duration_ms")) or 0
    if observed_cast_ms <= 0 or metadata.cast_ms <= 0:
        return max(0.0, observed_cast_ms)

    timestamp = to_number(attempt.get("timestamp"))
    adjusted_cast = float(metadata.cast_ms)
    if metadata.recast_speed_adjusted:
        attribute_key = "spell_speed" if metadata.action_category_id == 2 else "skill_speed"
        if speed_stats and speed_stats.get(attribute_key) is not None:
            adjusted_cast = speed_stat_adjusted_duration_ms(speed_stats.get(attribute_key), metadata.cast_ms)
        elif recast_timing is not None and default_speed_multiplier is not None:
            multiplier = recast_timing.multiplier_by_base.get(BASE_GCD_MS, default_speed_multiplier)
            adjusted_cast = float(metadata.cast_ms) * multiplier

    if metadata.recast_status_adjusted and timestamp is not None:
        adjusted_cast *= speed_modifier_at_timestamp(timestamp, job=job, speed_windows=speed_windows)
        if (
            str(job) == "Pictomancer"
            and metadata.action_id in PCT_HYPERPHANTASIA_ACTION_IDS
            and timestamp_in_windows_inclusive(
                timestamp,
                (status_windows_by_status_id or {}).get(PCT_INSPIRATION_STATUS_ID, []),
            )
        ):
            adjusted_cast *= 0.75

    if (
        str(job) == "Pictomancer"
        and metadata.action_id == PCT_RAINBOW_DRIP_ACTION_ID
        and timestamp is not None
        and (
            timestamp_in_windows_inclusive(
                timestamp,
                (status_windows_by_status_id or {}).get(PCT_RAINBOW_BRIGHT_STATUS_ID, []),
            )
            or (first_gcd_timestamp is not None and timestamp == first_gcd_timestamp)
        )
    ):
        # Rainbow Bright 會把 Rainbow Drip 變成即時施放；FFLogs raw/graph 有時仍保留
        # begincast duration。本地分子必須跟 xivanalysis 的 CastTime instant adjustment
        # 一樣歸零，否則 PCT 在 proc 當下會被多算一段讀條時間。
        adjusted_cast = 0.0

    # xivanalysis 的 AlwaysBeCasting 使用 CastTime 模組的技能表 cast time，而不是
    # FFLogs 封包實際讀條耗時。封包耗時仍可辨識 Swiftcast/Dualcast 等即時施放
    # （observed=0），但不應把延遲或 packet duration 放大成額外 GCD uptime。
    return max(0.0, min(observed_cast_ms, floor_to_10_ms(adjusted_cast)))


def raw_speed_stats_cover_attempt(attempt: dict[str, Any], speed_stats: dict[str, int]) -> bool:
    metadata = attempt["metadata"]
    if not metadata.recast_speed_adjusted:
        return True
    if metadata.action_id in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS:
        return True
    attribute_key = "spell_speed" if metadata.action_category_id == 2 else "skill_speed"
    return speed_stats.get(attribute_key) is not None


def timestamp_in_windows(timestamp: float, windows: list[tuple[float, float]]) -> bool:
    return any(start <= timestamp < end for start, end in windows)


def first_window_containing(timestamp: float, windows: list[tuple[float, float]]) -> tuple[float, float] | None:
    for start, end in windows:
        if start <= timestamp < end:
            return start, end
    return None


def timestamp_in_windows_inclusive(timestamp: float, windows: list[tuple[float, float]]) -> bool:
    return any(start <= timestamp <= end for start, end in windows)


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
    metadata_store: ActionMetadataStore | None = None,
    job: str | None = None,
    include_graph_downtime: bool = True,
) -> dict[str, Any]:
    downtime_source = dict(graph)
    if not include_graph_downtime:
        downtime_source["downtime"] = []
    encounter_windows = infer_all_foes_untargetable_windows(
        raw_events,
        friendly_ids=friendly_ids,
        fight_start_time=fight_start_time,
        fight_end_time=fight_end_time,
    )
    if encounter_windows:
        existing_encounter_windows = downtime_source.get("encounter_downtime") or []
        if str(job) in TANK_JOBS and isinstance(existing_encounter_windows, list):
            downtime_source["encounter_downtime"] = list(existing_encounter_windows) + encounter_windows
        else:
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
    status_windows_by_status_id: dict[int, list[tuple[float, float]]] | None = None,
) -> RecastTimingEstimate:
    speed_windows = speed_windows or []
    status_windows_by_status_id = status_windows_by_status_id or {}
    intervals_by_recast: dict[int, list[float]] = {}
    speed_modifier_counts_by_recast: dict[int, dict[float, int]] = {}
    for index, attempt in enumerate(attempts[:-1]):
        metadata = attempt.get("metadata")
        if (
            not isinstance(metadata, ActionMetadata)
            or not (metadata.recast_speed_adjusted or (metadata.recast_status_adjusted and speed_windows))
            or metadata.effective_recast_ms <= 0
        ):
            continue

        timestamp = to_number(attempt.get("timestamp"))
        next_timestamp = to_number(attempts[index + 1].get("timestamp"))
        if timestamp is None or next_timestamp is None:
            continue

        if (
            str(job) == "Pictomancer"
            and metadata.action_id in PCT_HYPERPHANTASIA_ACTION_IDS
            and timestamp_in_windows_inclusive(
                timestamp,
                status_windows_by_status_id.get(PCT_INSPIRATION_STATUS_ID, []),
            )
        ):
            # xivanalysis 的 PCT Inspiration 是 Hyperphantasia 法術專屬調整，
            # 不應被當成整場基礎詠速推估樣本；否則會把 3.3 秒系 GCD 全場誤縮短。
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
    status_windows_by_status_id: dict[int, list[tuple[float, float]]] | None = None,
    first_gcd_timestamp: float | None = None,
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
    pct_rainbow_bright = (
        timestamp is not None
        and timestamp_in_windows_inclusive(
            timestamp,
            (status_windows_by_status_id or {}).get(PCT_RAINBOW_BRIGHT_STATUS_ID, []),
        )
    )
    pct_prepull_rainbow = (
        timestamp is not None
        and first_gcd_timestamp is not None
        and timestamp == first_gcd_timestamp
    )
    pct_rainbow_adjusted = (
        cast_duration <= 0
        and (
            pct_rainbow_bright
            or pct_prepull_rainbow
            or status_windows_by_status_id is None
        )
    )
    if str(job) == "Pictomancer" and metadata.action_id == PCT_RAINBOW_DRIP_ACTION_ID and pct_rainbow_adjusted:
        # xivanalysis 的 Rainbow Bright 特例是 CastTime 的 flat recast adjustment：
        # speed-adjusted 6 秒 recast 先算完，再於消耗 Rainbow Drip 的同一 timestamp
        # 扣 3500ms，這會比「直接改成 2500ms 再吃詠速」略短。
        recast = max(float(MIN_RECAST_TIME_MS), recast - 3500.0)

    if metadata.recast_status_adjusted and timestamp is not None:
        actual_speed_modifier = speed_modifier_at_timestamp(
            timestamp,
            job=job,
            speed_windows=speed_windows,
        )
        if metadata.recast_speed_adjusted and metadata.action_id not in RECAST_SUBSTAT_EXCLUDED_ACTION_IDS:
            dominant_speed_modifier = recast_timing.dominant_speed_modifier_by_base.get(base_recast)
            if dominant_speed_modifier is None:
                recast = floor_to_10_ms(recast * actual_speed_modifier)
            elif dominant_speed_modifier > 0 and abs(actual_speed_modifier - dominant_speed_modifier) > 0.00001:
                unmodified_recast = round_to_nearest_10_ms(recast / dominant_speed_modifier)
                recast = floor_to_10_ms(unmodified_recast * actual_speed_modifier)
        elif speed_windows:
            recast = floor_to_10_ms(recast * status_speed_modifier_at_timestamp(timestamp, speed_windows=speed_windows))

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

        cast_start = to_number(attempt.get("cast_start_timestamp"))
        if cast_start is not None and timestamp_in_windows(cast_start, coverage_windows):
            continue

        cast_duration = adjusted_cast_ms_for_uptime(
            attempt,
            job=job,
            speed_windows=speed_windows,
            default_speed_multiplier=default_speed_multiplier,
            recast_timing=recast_timing,
        )
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

        cap_at_next_gcd = cast_duration > 0 or str(job) in {"BlackMage", "Monk"}
        if cap_at_next_gcd:
            next_attempt = attempts[index + 1] if index + 1 < len(attempts) else None
            if next_attempt:
                next_timestamp = to_number(next_attempt.get("timestamp"))
                if next_timestamp is not None:
                    uptime = min(uptime, max(0.0, next_timestamp - timestamp))

        # xivanalysis 的事件流會把每個 instant GCD action 的覆蓋時間獨立相加，最後才把
        # percent 壓在 100。Casts graph 沒有完整 action event 語意；讀條與已知會高估的
        # job 在上方先用下一個 GCD 裁切，其餘短鎖/instant 技能保留站端較寬鬆的累加語意。
        if end_time is not None:
            uptime = min(uptime, max(0.0, end_time - timestamp))
        if uptime <= 0:
            continue

        # xivanalysis 的 Always Be Casting 只在「GCD 覆蓋結束點落在 downtime 內」
        # 時裁到 downtime 起點；若一個 GCD 橫跨短 downtime 但結束後已回到可行動時間，
        # 站端百分比不會再把中間重疊段扣一次。這裡刻意對齊該語意，避免本地值偏低。
        ending_window = first_window_containing(timestamp + uptime, coverage_windows)
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
    encounter_key: str | None = None,
    source_id: int | None = None,
    job: str | None = None,
    fight_end_time: float | None = None,
    fallback_denominator_ms: float | None = None,
    downtime_source: dict[str, Any] | None = None,
    cap_next_gcd_jobs: set[str] | frozenset[str] | None = None,
) -> dict[str, Any] | None:
    attempts = extract_gcd_attempts_from_raw_events(raw_events, metadata_store, source_id=source_id)
    if not attempts:
        return None

    capped_jobs = RAW_NEXT_GCD_CAPPED_JOBS if cap_next_gcd_jobs is None else cap_next_gcd_jobs
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

    source_provided_speed_stats = combatant_speed_stats(raw_events, source_id=source_id)
    use_unadjusted_source_speed = (
        bool(source_provided_speed_stats)
        and str(job) in RAW_EVENT_UNADJUSTED_SOURCE_SPEED_JOBS
        and source_death_in_windows(raw_events, source_id=source_id, windows=coverage_windows)
    )
    if use_unadjusted_source_speed:
        speed_stats = {
            "skill_speed": SUB_ATTRIBUTE_MINIMUM,
            "spell_speed": SUB_ATTRIBUTE_MINIMUM,
        }
    else:
        speed_stats = dict(source_provided_speed_stats)
    speed_windows = raw_speed_modifier_windows(raw_events, source_id=source_id, fight_end_time=fight_end_time)
    status_windows_by_status_id = raw_target_status_windows(
        raw_events,
        source_id=source_id,
        status_ids={PCT_INSPIRATION_STATUS_ID, PCT_RAINBOW_BRIGHT_STATUS_ID} if str(job) == "Pictomancer" else set(),
        fight_end_time=fight_end_time,
    )
    estimated_speed_stats: dict[str, int] = {}
    if not speed_stats:
        speed_estimation_attempts = extract_gcd_speed_estimation_attempts_from_raw_events(
            raw_events,
            metadata_store,
            source_id=source_id,
        )
        speed_stat_estimation_windows = raw_speed_modifier_windows(
            raw_events,
            source_id=source_id,
            fight_end_time=fight_end_time,
            extra_status_modifiers_by_status_id=(
                {PCT_INSPIRATION_STATUS_ID: 0.75} if str(job) == "Pictomancer" else None
            ),
        )
        estimated_speed_stats = estimate_speed_stats_from_attempts(
            speed_estimation_attempts or attempts,
            job=job,
            speed_windows=speed_stat_estimation_windows,
        )
        speed_stats.update(estimated_speed_stats)
    gcd_exclusion_windows = job_gcd_exclusion_windows(
        raw_events,
        source_id=source_id,
        job=job,
        fight_end_time=fight_end_time,
    )
    if gcd_exclusion_windows:
        denominator_ms -= sum(
            max(0.0, end - start - overlap_ms(start, end, denominator_windows))
            for start, end in gcd_exclusion_windows
        )
        if denominator_ms <= 0:
            return None

    default_speed_multiplier = median_default_speed_multiplier(attempts)
    recast_timing = infer_recast_timing_by_base(
        attempts,
        job=job,
        speed_windows=speed_windows,
        status_windows_by_status_id=status_windows_by_status_id,
    )
    first_gcd_timestamp = to_number(attempts[0].get("timestamp")) if attempts else None
    covered_ms = 0.0

    for index, attempt in enumerate(attempts):
        timestamp = to_number(attempt.get("timestamp"))
        if timestamp is None:
            continue

        cast_start = to_number(attempt.get("cast_start_timestamp"))
        if cast_start is not None and timestamp_in_windows(cast_start, coverage_windows):
            continue
        if cast_start is not None and timestamp_in_windows(cast_start, gcd_exclusion_windows):
            continue

        next_attempt = attempts[index + 1] if index + 1 < len(attempts) else None
        if should_skip_raw_gcd_uptime(encounter_key, job, attempt, next_attempt):
            continue

        cast_duration = adjusted_cast_ms_for_uptime(
            attempt,
            job=job,
            speed_windows=speed_windows,
            speed_stats=speed_stats,
            default_speed_multiplier=default_speed_multiplier,
            recast_timing=recast_timing,
            status_windows_by_status_id=status_windows_by_status_id,
            first_gcd_timestamp=first_gcd_timestamp,
        )
        if raw_speed_stats_cover_attempt(attempt, speed_stats):
            recast = raw_recast_ms(
                attempt,
                speed_stats=speed_stats,
                job=job,
                speed_windows=speed_windows,
                status_windows_by_status_id=status_windows_by_status_id,
                first_gcd_timestamp=first_gcd_timestamp,
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
                status_windows_by_status_id=status_windows_by_status_id,
                first_gcd_timestamp=first_gcd_timestamp,
            )
        uptime = max(cast_duration, recast)
        if cast_duration > 0 and cast_duration >= recast:
            uptime += 100
        if fight_end_time is not None:
            uptime = min(uptime, max(0.0, fight_end_time - timestamp))
        if str(job) in capped_jobs:
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
    if use_unadjusted_source_speed:
        coverage["speed_stat_source"] = "combatantinfo_unadjusted_xivanalysis_raw_lock"
    elif source_provided_speed_stats and estimated_speed_stats:
        coverage["speed_stat_source"] = "combatantinfo+estimated"
    elif source_provided_speed_stats:
        coverage["speed_stat_source"] = "combatantinfo"
    elif estimated_speed_stats:
        coverage["speed_stat_source"] = "estimated"
        if any(value < SUB_ATTRIBUTE_MINIMUM for value in estimated_speed_stats.values()):
            coverage["estimated_speed_below_minimum"] = True
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
