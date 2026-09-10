"""M8S 狼機制承傷的最小證據；純計算，不呼叫 API 或保存 raw events。

三次 Surge 名義上各扣 20% HP，最後一次若過量擊殺，玩家實際承傷會高於
固定 40%。只接受已驗證的技能／敵方來源，不能用任意敵方傷害調低基準。
查核來源見 docs/m8s-tolerance-audit-2026-09-09.md。
"""

from __future__ import annotations

import math
from typing import Any, Iterable

MODEL = "m8s_wolf_surges_v1"
MAX_HP = 10_518_438
NOMINAL_HIT = 2_103_687
# NPC GUID 可跨 report 對應；report 內 actor ID 只在讀取事件時使用。
WOLVES = {18219: (18262, frozenset({41966, 43138, 43520})),
          18225: (18261, frozenset({41965, 43137}))}
MECHANIC_ABILITIES = frozenset().union(*(rule[1] for rule in WOLVES.values()))


def nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not math.isfinite(value) or value < 0 or int(value) != value:
        return None
    return int(value)


class MechanicAccumulator:
    """逐頁收斂為每隻狼的計數／總量／極值，記憶體不累積原始事件。"""

    def __init__(self, actor_guids: dict[int, int]) -> None:
        self.actor_guids = actor_guids
        self.targets: dict[int, dict[str, Any]] = {
            guid: {"guid": guid, "hit_count": 0, "effective_damage": 0,
                   "overkill": 0, "overkill_hit_count": 0, "nominal_min": 0, "nominal_max": 0,
                   "invalid_hit_count": 0, "source_npc_guids": [], "ability_ids": []}
            for guid in WOLVES
        }

    def add(self, events: Iterable[dict[str, Any]]) -> None:
        for event in events:
            if not isinstance(event, dict) or event.get("type") != "damage":
                continue  # calculateddamage 與 damage 不能重複累加。
            guid = self.actor_guids.get(event.get("targetID"))
            if guid not in WOLVES:
                continue
            source = self.actor_guids.get(event.get("sourceID"))
            ability = nonnegative_int(event.get("abilityGameID"))
            expected_source, allowed_abilities = WOLVES[guid]
            if source is None and ability not in MECHANIC_ABILITIES:
                continue  # 玩家／寵物的傷害已由 Target Damage 提供，不是機制。
            target = self.targets[guid]
            if target["overkill_hit_count"]:
                target["invalid_hit_count"] += 1  # 已被機制擊殺後不可再有另一次 Surge。
            amount = nonnegative_int(event.get("amount"))
            # FFLogs 的 -1 表示沒有過量擊殺；缺值亦依未過量處理。
            raw_overkill = event.get("overkill", 0)
            overkill = 0 if raw_overkill == -1 else nonnegative_int(raw_overkill)
            target["hit_count"] += 1
            if source is not None and source not in target["source_npc_guids"]:
                target["source_npc_guids"].append(source)
            if ability is not None and ability not in target["ability_ids"]:
                target["ability_ids"].append(ability)
            if amount is None or overkill is None:
                target["invalid_hit_count"] += 1
                continue
            nominal = amount + overkill
            target["effective_damage"] += amount
            target["overkill"] += overkill
            target["overkill_hit_count"] += int(overkill > 0)
            target["nominal_min"] = min(target["nominal_min"] or nominal, nominal)
            target["nominal_max"] = max(target["nominal_max"], nominal)
            if source != expected_source or ability not in allowed_abilities or nominal != NOMINAL_HIT:
                target["invalid_hit_count"] += 1

    def summary(self) -> dict[str, Any]:
        return {"version": MODEL, "targets": [
            {**target, "source_npc_guids": sorted(target["source_npc_guids"]),
             "ability_ids": sorted(target["ability_ids"])}
            for _, target in sorted(self.targets.items())
        ]}


def normalize_summary(raw: Any) -> dict[str, Any] | None:
    """以欄位白名單重建摘要，舊版／損毀證據不能在快取中冒充已驗證資料。"""
    if not isinstance(raw, dict) or raw.get("version") != MODEL:
        return None
    rows = raw.get("targets")
    if not isinstance(rows, list) or len(rows) != len(WOLVES):
        return None
    targets: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        guid = nonnegative_int(row.get("guid"))
        if guid not in WOLVES or guid in targets:
            return None
        target: dict[str, Any] = {"guid": guid}
        for key in ("hit_count", "effective_damage", "overkill", "overkill_hit_count", "nominal_min",
                    "nominal_max", "invalid_hit_count"):
            number = nonnegative_int(row.get(key))
            if number is None:
                return None
            target[key] = number
        for key in ("source_npc_guids", "ability_ids"):
            values = row.get(key)
            if not isinstance(values, list) or any(
                nonnegative_int(v) is None or v <= 0 for v in values
            ):
                return None
            target[key] = sorted(set(values))
        targets[guid] = target
    return {"version": MODEL, "targets": [targets[g] for g in sorted(targets)]}


def summary_status(raw: Any) -> str:
    summary = normalize_summary(raw)
    if summary is None:
        return "unverifiable"
    for target in summary["targets"]:
        source, abilities = WOLVES[target["guid"]]
        count = target["hit_count"]
        if (target["invalid_hit_count"] or count > 3
                or target["overkill_hit_count"] != int(target["overkill"] > 0)
                or (count and (target["nominal_min"] != NOMINAL_HIT
                               or target["nominal_max"] != NOMINAL_HIT))
                or (count and target["source_npc_guids"] != [source])
                or not set(target["ability_ids"]).issubset(abilities)
                or target["effective_damage"] + target["overkill"] != count * NOMINAL_HIT):
            return "suspected"
    if any(t["hit_count"] != 3 or not t["ability_ids"]
           or t["effective_damage"] <= 0 for t in summary["targets"]):
        return "unverifiable"
    return "valid"


def expected_wolf_damage(raw: Any) -> dict[int, int]:
    if summary_status(raw) != "valid":
        return {}
    summary = normalize_summary(raw)
    assert summary is not None
    return {t["guid"]: MAX_HP - t["effective_damage"] for t in summary["targets"]}
