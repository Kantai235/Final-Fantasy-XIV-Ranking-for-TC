"""整理補師治療與坦克防護／減傷的精簡衍生資料。

這個模組只處理單場 fight 已取得的 FFLogs Healing table 與事件。原始 table／events
不會寫入 ``data/rankings``；呼叫端只保存本模組回傳的小型摘要。如此可讓未來 Node.js
建置層依同一場 fight 關聯兩名補師，也能避免 Git 歷史因 raw events 持續膨脹。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


支援統計計算版本 = 1
坦克減傷規則版本 = "ffxiv_7_2_2026_08_11_v3"
FFLOGS狀態ID偏移 = 1_000_000
團隊減傷封包合併容許毫秒 = 2_000

坦克職業 = {"Paladin", "Warrior", "DarkKnight", "Gunbreaker"}
補師職業 = {"WhiteMage", "Scholar", "Astrologian", "Sage"}


@dataclass(frozen=True)
class 減傷規則:
    """描述跨副本通用的玩家減傷狀態，不包含任何副本機制 ID。

    ``audience`` 是計算分母與呈現分類用的語意：

    - ``personal``：狀態只保護施放坦克。
    - ``target``：狀態可保護自己或單一隊友，依實際 targetID 分類。
    - ``team``：團隊減傷／護盾，覆蓋率以全隊承傷為分母。
    - ``enemy``：施加在敵人的降傷 Debuff，以該敵人造成的全隊傷害判斷有效性。

    FFLogs Buffs／Debuffs events 的 ``abilityGameID`` 是狀態 ID，不是 Action ID；
    因此規則明確保存 Status.csv ID，避免把名稱翻譯或副本技能誤當成玩家減傷。
    """

    key: str
    name: str
    jobs: frozenset[str]
    status_ids: frozenset[int]
    audience: Literal["personal", "target", "team", "enemy"]


全部坦克 = frozenset(坦克職業)

# 規則只描述玩家職業技能，且一律要求事件 sourceID 等於該坦克。即使副本 NPC 使用同名
# 狀態，也不會被算入玩家減傷。舊版／等級同步仍可能出現較早的狀態 ID，因此保留已知變體。
坦克減傷規則: tuple[減傷規則, ...] = (
    減傷規則("rampart", "Rampart", 全部坦克, frozenset({71, 1191, 1978, 4168}), "personal"),
    減傷規則("reprisal", "Reprisal", 全部坦克, frozenset({753, 1193, 2101}), "enemy"),
    減傷規則("sentinel", "Sentinel", frozenset({"Paladin"}), frozenset({74}), "personal"),
    減傷規則("guardian", "Guardian", frozenset({"Paladin"}), frozenset({3829, 3830}), "personal"),
    減傷規則("bulwark", "Bulwark", frozenset({"Paladin"}), frozenset({77}), "personal"),
    減傷規則("sheltron", "Sheltron", frozenset({"Paladin"}), frozenset({728, 1856}), "personal"),
    減傷規則("holy_sheltron", "Holy Sheltron", frozenset({"Paladin"}), frozenset({2674, 3026}), "personal"),
    減傷規則("intervention", "Intervention", frozenset({"Paladin"}), frozenset({1174, 2020}), "target"),
    減傷規則("passage_of_arms", "Passage of Arms", frozenset({"Paladin"}), frozenset({1175, 1176}), "team"),
    減傷規則("divine_veil", "Divine Veil", frozenset({"Paladin"}), frozenset({727, 1362, 2168, 2169}), "team"),
    減傷規則("hallowed_ground", "Hallowed Ground", frozenset({"Paladin"}), frozenset({82, 1302}), "personal"),
    減傷規則("vengeance", "Vengeance", frozenset({"Warrior"}), frozenset({89}), "personal"),
    減傷規則("damnation", "Damnation", frozenset({"Warrior"}), frozenset({3832}), "personal"),
    減傷規則("raw_intuition", "Raw Intuition", frozenset({"Warrior"}), frozenset({735}), "personal"),
    減傷規則("bloodwhetting", "Bloodwhetting", frozenset({"Warrior"}), frozenset({2678}), "personal"),
    減傷規則("nascent_glint", "Nascent Flash", frozenset({"Warrior"}), frozenset({1858, 2062}), "target"),
    減傷規則("shake_it_off", "Shake It Off", frozenset({"Warrior"}), frozenset({1457, 1993}), "team"),
    減傷規則("holmgang", "Holmgang", frozenset({"Warrior"}), frozenset({409, 1304}), "personal"),
    減傷規則("dark_mind", "Dark Mind", frozenset({"DarkKnight"}), frozenset({746}), "personal"),
    減傷規則("shadow_wall", "Shadow Wall", frozenset({"DarkKnight"}), frozenset({747}), "personal"),
    減傷規則("shadowed_vigil", "Shadowed Vigil", frozenset({"DarkKnight"}), frozenset({3835}), "personal"),
    減傷規則("the_blackest_night", "The Blackest Night", frozenset({"DarkKnight"}), frozenset({1178, 1308}), "target"),
    減傷規則("oblation", "Oblation", frozenset({"DarkKnight"}), frozenset({2682}), "target"),
    減傷規則("dark_missionary", "Dark Missionary", frozenset({"DarkKnight"}), frozenset({1894, 2171}), "team"),
    減傷規則("living_dead", "Living Dead", frozenset({"DarkKnight"}), frozenset({810, 811, 3255}), "personal"),
    減傷規則("camouflage", "Camouflage", frozenset({"Gunbreaker"}), frozenset({1832}), "personal"),
    減傷規則("nebula", "Nebula", frozenset({"Gunbreaker"}), frozenset({1834}), "personal"),
    減傷規則("great_nebula", "Great Nebula", frozenset({"Gunbreaker"}), frozenset({3838}), "personal"),
    減傷規則("heart_of_stone", "Heart of Stone", frozenset({"Gunbreaker"}), frozenset({1840}), "target"),
    減傷規則("heart_of_corundum", "Heart of Corundum", frozenset({"Gunbreaker"}), frozenset({2683, 4295}), "target"),
    減傷規則("heart_of_light", "Heart of Light", frozenset({"Gunbreaker"}), frozenset({1839, 2000}), "team"),
    減傷規則("superbolide", "Superbolide", frozenset({"Gunbreaker"}), frozenset({1836}), "personal"),
)


def 轉數值(值: Any) -> float | None:
    if isinstance(值, bool):
        return None
    if isinstance(值, (int, float)):
        return float(值)
    return None


def 轉整數(值: Any) -> int | None:
    數值 = 轉數值(值)
    return int(數值) if 數值 is not None else None


def 正規化FFLogs狀態ID(值: Any) -> int | None:
    """將 Buffs／Debuffs events 的 FFLogs namespace ID 還原為 Status.csv ID。

    FFLogs events 實際回傳 ``1_000_000 + Status ID``（例如 Reprisal 是
    ``1001193``），但規則表刻意保存可由 XIVAPI Status.csv 追溯的 ``1193``。
    測試 fixture 與部分舊 payload 可能已是未加 namespace 的值，因此兩種格式都接受。
    """

    狀態id = 轉整數(值)
    if 狀態id is not None and FFLOGS狀態ID偏移 <= 狀態id < FFLOGS狀態ID偏移 * 2:
        return 狀態id - FFLOGS狀態ID偏移
    return 狀態id


def 整理總量(值: float) -> int | float:
    return int(值) if float(值).is_integer() else round(值, 3)


def 每秒(總量: float, 時間毫秒: float | None) -> float | None:
    if 時間毫秒 is None or 時間毫秒 <= 0:
        return None
    return round(總量 / (時間毫秒 / 1000), 2)


def 百分比(分子: float, 分母: float) -> float:
    if 分母 <= 0:
        return 0.0
    return round(分子 / 分母 * 100, 2)


def _取得表格資料(表格: Any) -> dict[str, Any]:
    if not isinstance(表格, dict):
        return {}
    資料 = 表格.get("data")
    return 資料 if isinstance(資料, dict) else {}


def _取得表格列(表格: Any) -> list[dict[str, Any]]:
    列 = _取得表格資料(表格).get("entries")
    if not isinstance(列, list):
        return []
    return [項目 for 項目 in 列 if isinstance(項目, dict)]


def _建立治療列索引(表格: Any) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    id索引: dict[str, dict[str, Any]] = {}
    guid索引: dict[str, dict[str, Any]] = {}
    名稱暫存: dict[str, list[dict[str, Any]]] = {}
    for 列 in _取得表格列(表格):
        if 列.get("id") is not None:
            id索引[str(列.get("id"))] = 列
        if 列.get("guid") is not None:
            guid索引[str(列.get("guid"))] = 列
        名稱 = 列.get("name")
        if isinstance(名稱, str) and 名稱:
            名稱暫存.setdefault(名稱, []).append(列)
    名稱索引 = {名稱: 候選[0] for 名稱, 候選 in 名稱暫存.items() if len(候選) == 1}
    return id索引, guid索引, 名稱索引


def _找出治療列(
    玩家: dict[str, Any],
    id索引: dict[str, dict[str, Any]],
    guid索引: dict[str, dict[str, Any]],
    名稱索引: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    玩家id = 玩家.get("fflogs_id")
    if 玩家id is not None and str(玩家id) in id索引:
        return id索引[str(玩家id)]
    guid = 玩家.get("fflogs_guid")
    if guid is not None and str(guid) in guid索引:
        return guid索引[str(guid)]
    名稱 = 玩家.get("name")
    return 名稱索引.get(名稱) if isinstance(名稱, str) else None


def _拆解治療列(治療列: dict[str, Any] | None) -> dict[str, float]:
    if not isinstance(治療列, dict):
        return {"healing_and_protection": 0.0, "pure_healing": 0.0, "protection": 0.0, "overheal": 0.0}

    合計 = max(轉數值(治療列.get("total")) or 0.0, 0.0)
    純治療原值 = 轉數值(治療列.get("totalReduced"))
    純治療 = max(純治療原值 if 純治療原值 is not None else 合計, 0.0)
    防護 = max(合計 - 純治療, 0.0)
    過量治療 = max(轉數值(治療列.get("overheal")) or 0.0, 0.0)
    return {
        "healing_and_protection": 合計,
        "pure_healing": 純治療,
        "protection": 防護,
        "overheal": 過量治療,
    }


def _建立補師治療摘要(治療列: dict[str, Any] | None, 治療時間毫秒: float | None) -> dict[str, Any]:
    總量 = _拆解治療列(治療列)
    純治療 = 總量["pure_healing"]
    過量治療 = 總量["overheal"]
    return {
        "calculation_version": 支援統計計算版本,
        "source": "fflogs_healing_table",
        "combat_time_ms": 整理總量(治療時間毫秒) if 治療時間毫秒 is not None else None,
        "hps": 每秒(總量["healing_and_protection"], 治療時間毫秒),
        "healing_and_protection": 整理總量(總量["healing_and_protection"]),
        "pure_healing": 整理總量(純治療),
        "protection": 整理總量(總量["protection"]),
        "overheal": 整理總量(過量治療),
        # 護盾不會產生 overheal；OH% 因此只用「純治療 + 過量治療」作分母，
        # 避免盾補因防護量高而被人工壓低 OH%。
        "overheal_percent": 百分比(過量治療, 純治療 + 過量治療),
    }


def _拆解坦克自身治療與防護(
    玩家: dict[str, Any],
    治療列: dict[str, Any] | None,
    同名玩家數: dict[str, int],
) -> dict[str, Any]:
    總量 = _拆解治療列(治療列)
    if not isinstance(治療列, dict):
        return {
            "self_healing": 0,
            "personal_protection": 0,
            "team_protection": 0,
            "target_breakdown_complete": True,
        }

    目標列 = 治療列.get("targets")
    if not isinstance(目標列, list):
        return {
            "self_healing": None,
            "personal_protection": None,
            "team_protection": None,
            "target_breakdown_complete": False,
        }
    if not 目標列 and (總量["pure_healing"] > 0 or 總量["protection"] > 0):
        return {
            "self_healing": None,
            "personal_protection": None,
            "team_protection": None,
            "target_breakdown_complete": False,
        }

    玩家id = 玩家.get("fflogs_id")
    玩家名稱 = 玩家.get("name")
    自身目標: dict[str, Any] | None = None
    有模糊同名目標 = False
    for 候選 in 目標列:
        if not isinstance(候選, dict):
            continue
        if 玩家id is not None and 候選.get("id") is not None and str(候選.get("id")) == str(玩家id):
            自身目標 = 候選
            break
        if (
            isinstance(玩家名稱, str)
            and 候選.get("name") == 玩家名稱
        ):
            if 同名玩家數.get(玩家名稱, 0) == 1:
                自身目標 = 候選
                break
            有模糊同名目標 = True

    if 自身目標 is None and 有模糊同名目標:
        return {
            "self_healing": None,
            "personal_protection": None,
            "team_protection": None,
            "target_breakdown_complete": False,
        }

    自身總量 = _拆解治療列(自身目標)
    個人防護 = 自身總量["protection"]
    團隊防護 = max(總量["protection"] - 個人防護, 0.0)
    return {
        "self_healing": 整理總量(自身總量["pure_healing"]),
        "personal_protection": 整理總量(個人防護),
        "team_protection": 整理總量(團隊防護),
        "target_breakdown_complete": True,
    }


def _正規化傷害事件(事件列表: Any, 隊伍玩家id: set[int]) -> list[dict[str, Any]]:
    if not isinstance(事件列表, list):
        return []
    結果: list[dict[str, Any]] = []
    for 原始事件 in 事件列表:
        if not isinstance(原始事件, dict) or str(原始事件.get("type") or "").lower() != "damage":
            # DamageTaken events 同時含 calculateddamage；兩者描述同一次命中，不能重複加總。
            continue
        目標id = 轉整數(原始事件.get("targetID"))
        時間戳記 = 轉數值(原始事件.get("timestamp"))
        if 目標id not in 隊伍玩家id or 時間戳記 is None:
            continue
        承傷 = max(轉數值(原始事件.get("amount")) or 0.0, 0.0)
        吸收 = max(轉數值(原始事件.get("absorbed")) or 0.0, 0.0)
        未減免 = max(轉數值(原始事件.get("unmitigatedAmount")) or 0.0, 承傷 + 吸收)
        if 承傷 <= 0 and 吸收 <= 0 and 未減免 <= 0:
            continue
        結果.append(
            {
                "timestamp": 時間戳記,
                "source_id": 轉整數(原始事件.get("sourceID")),
                "target_id": 目標id,
                "amount": 承傷,
                "absorbed": 吸收,
                "unmitigated": 未減免,
            }
        )
    結果.sort(key=lambda 事件: 事件["timestamp"])
    return 結果


def _建立狀態時窗(
    規則: 減傷規則,
    坦克id: int,
    事件列表: Any,
    戰鬥結束時間: float,
) -> list[dict[str, Any]]:
    if not isinstance(事件列表, list):
        return []

    套用類型 = {"applybuff", "applydebuff"}
    更新類型 = {"refreshbuff", "refreshdebuff"}
    移除類型 = {"removebuff", "removedebuff"}
    開啟時窗: dict[tuple[int, int], dict[str, Any]] = {}
    完成時窗: list[dict[str, Any]] = []

    def 關閉時窗(鍵值: tuple[int, int], 結束時間: float) -> None:
        時窗 = 開啟時窗.pop(鍵值, None)
        if 時窗 is None or 結束時間 < 時窗["start"]:
            return
        完成時窗.append({**時窗, "end": 結束時間})

    排序事件 = sorted(
        (事件 for 事件 in 事件列表 if isinstance(事件, dict)),
        key=lambda 事件: (轉數值(事件.get("timestamp")) or 0.0, 轉整數(事件.get("packetID")) or 0),
    )
    for 事件 in 排序事件:
        if 轉整數(事件.get("sourceID")) != 坦克id:
            continue
        狀態id = 正規化FFLogs狀態ID(事件.get("abilityGameID"))
        目標id = 轉整數(事件.get("targetID"))
        時間戳記 = 轉數值(事件.get("timestamp"))
        類型 = str(事件.get("type") or "").lower()
        if 狀態id not in 規則.status_ids or 目標id is None or 時間戳記 is None:
            continue
        鍵值 = (狀態id, 目標id)

        if 類型 in 套用類型:
            # 同一狀態尚未移除又重新套用時，先結束舊窗；refresh 則維持同一 activation，
            # 讓延長持續時間不會被誤算成再次施放。
            關閉時窗(鍵值, 時間戳記)
            packet_id = 轉整數(事件.get("packetID"))
            啟用鍵值 = f"packet:{packet_id}" if packet_id is not None else f"time:{round(時間戳記 / 100) * 100}"
            開啟時窗[鍵值] = {
                "start": 時間戳記,
                "target_id": 目標id,
                "activation_key": 啟用鍵值,
            }
        elif 類型 in 更新類型:
            if 鍵值 not in 開啟時窗:
                packet_id = 轉整數(事件.get("packetID"))
                啟用鍵值 = f"packet:{packet_id}" if packet_id is not None else f"time:{round(時間戳記 / 100) * 100}"
                開啟時窗[鍵值] = {
                    "start": 時間戳記,
                    "target_id": 目標id,
                    "activation_key": 啟用鍵值,
                }
        elif 類型 in 移除類型:
            關閉時窗(鍵值, 時間戳記)

    for 鍵值 in list(開啟時窗):
        關閉時窗(鍵值, 戰鬥結束時間)
    return 完成時窗


def _事件落在時窗(傷害: dict[str, Any], 時窗: dict[str, Any], audience: str) -> bool:
    時間戳記 = 傷害["timestamp"]
    if 時間戳記 < 時窗["start"] or 時間戳記 > 時窗["end"]:
        return False
    if audience == "enemy":
        return 傷害["source_id"] == 時窗["target_id"]
    return 傷害["target_id"] == 時窗["target_id"]


def _啟用分類(規則: 減傷規則, 坦克id: int, 時窗列表: list[dict[str, Any]]) -> str:
    if 規則.audience == "personal":
        return "personal"
    if 規則.audience in {"team", "enemy"}:
        return "team"
    return "personal" if all(時窗["target_id"] == 坦克id for 時窗 in 時窗列表) else "team"


def _建立啟用時窗索引(
    規則: 減傷規則,
    時窗列表: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """把 FFLogs 的狀態時窗收斂成玩家實際按下技能的次數。

    FFLogs 會把 Dark Missionary、Heart of Light 等團隊狀態拆成每名隊員各自的
    apply/remove 封包，而且各 target 的 packetID 不相同；直接按 packetID 計數會把
    一次施放誤算成至多八次。團隊減傷因此依「彼此重疊，或僅有短封包間隔」的時窗
    合併。同一技能的正常冷卻遠長於兩秒，不會因此把兩次合法施放接在一起。

    非團隊規則仍保留 FFLogs packetID，避免 Oblation 等可連續消耗充能的單體技能
    因為狀態時窗重疊而被錯誤合併。
    """

    if 規則.audience != "team":
        結果: dict[str, list[dict[str, Any]]] = {}
        for 時窗 in 時窗列表:
            結果.setdefault(str(時窗["activation_key"]), []).append(時窗)
        return 結果

    排序時窗 = sorted(
        時窗列表,
        key=lambda 時窗: (時窗["start"], 時窗["end"], 時窗["target_id"]),
    )
    合併群組: list[list[dict[str, Any]]] = []
    群組結束時間: float | None = None
    for 時窗 in 排序時窗:
        if (
            not 合併群組
            or 群組結束時間 is None
            or 時窗["start"] > 群組結束時間 + 團隊減傷封包合併容許毫秒
        ):
            合併群組.append([時窗])
            群組結束時間 = 時窗["end"]
            continue
        合併群組[-1].append(時窗)
        群組結束時間 = max(群組結束時間, 時窗["end"])

    return {
        f"window:{索引}:{round(群組[0]['start'])}": 群組
        for 索引, 群組 in enumerate(合併群組)
    }


def _建立減傷覆蓋摘要(
    玩家: dict[str, Any],
    傷害事件: list[dict[str, Any]],
    友方狀態事件: Any,
    敵方減益事件: Any,
    戰鬥結束時間: float,
) -> dict[str, Any]:
    坦克id = 轉整數(玩家.get("fflogs_id"))
    職業 = str(玩家.get("job") or "")
    if 坦克id is None:
        return {
            "calculation_version": 支援統計計算版本,
            "rules_version": 坦克減傷規則版本,
            "total_activations": 0,
            "effective_activations": 0,
            "effective_activation_percent": 0.0,
            "personal": _建立覆蓋分類摘要(set(), set(), set(), 傷害事件, 坦克id, 個人=True),
            "team": _建立覆蓋分類摘要(set(), set(), set(), 傷害事件, 坦克id, 個人=False),
            "skills": [],
        }

    個人涵蓋事件: set[int] = set()
    團隊涵蓋事件: set[int] = set()
    個人啟用: set[str] = set()
    團隊啟用: set[str] = set()
    個人有效啟用: set[str] = set()
    團隊有效啟用: set[str] = set()
    技能摘要: list[dict[str, Any]] = []

    for 規則 in 坦克減傷規則:
        if 職業 not in 規則.jobs:
            continue
        狀態事件 = 敵方減益事件 if 規則.audience == "enemy" else 友方狀態事件
        時窗 = _建立狀態時窗(規則, 坦克id, 狀態事件, 戰鬥結束時間)
        if not 時窗:
            continue

        啟用時窗索引 = _建立啟用時窗索引(規則, 時窗)

        有效啟用數 = 0
        技能涵蓋事件: set[int] = set()
        個人技能涵蓋: set[int] = set()
        團隊技能涵蓋: set[int] = set()
        for 啟用鍵值, 啟用時窗 in 啟用時窗索引.items():
            分類 = _啟用分類(規則, 坦克id, 啟用時窗)
            完整啟用鍵值 = f"{規則.key}:{啟用鍵值}"
            if 分類 == "personal":
                個人啟用.add(完整啟用鍵值)
            else:
                團隊啟用.add(完整啟用鍵值)

            命中事件 = {
                索引
                for 索引, 傷害 in enumerate(傷害事件)
                if any(_事件落在時窗(傷害, 單一時窗, 規則.audience) for 單一時窗 in 啟用時窗)
            }
            if 命中事件:
                有效啟用數 += 1
                技能涵蓋事件.update(命中事件)
                if 分類 == "personal":
                    個人涵蓋事件.update(命中事件)
                    個人技能涵蓋.update(命中事件)
                    個人有效啟用.add(完整啟用鍵值)
                else:
                    團隊涵蓋事件.update(命中事件)
                    團隊技能涵蓋.update(命中事件)
                    團隊有效啟用.add(完整啟用鍵值)

        技能摘要.append(
            {
                "key": 規則.key,
                "name": 規則.name,
                "audience": 規則.audience,
                "activation_count": len(啟用時窗索引),
                "effective_activation_count": 有效啟用數,
                "effective_activation_percent": 百分比(有效啟用數, len(啟用時窗索引)),
                "covered_unmitigated_damage": 整理總量(
                    sum(傷害事件[索引]["unmitigated"] for 索引 in 技能涵蓋事件)
                ),
                "personal_covered_unmitigated_damage": 整理總量(
                    sum(傷害事件[索引]["unmitigated"] for 索引 in 個人技能涵蓋)
                ),
                "team_covered_unmitigated_damage": 整理總量(
                    sum(傷害事件[索引]["unmitigated"] for 索引 in 團隊技能涵蓋)
                ),
            }
        )

    全部啟用數 = len(個人啟用 | 團隊啟用)
    全部有效啟用 = 個人有效啟用 | 團隊有效啟用

    return {
        "calculation_version": 支援統計計算版本,
        "rules_version": 坦克減傷規則版本,
        "definition": "damage_during_active_mitigation_window",
        "total_activations": 全部啟用數,
        "effective_activations": len(全部有效啟用),
        "effective_activation_percent": 百分比(len(全部有效啟用), 全部啟用數),
        "personal": _建立覆蓋分類摘要(
            個人涵蓋事件,
            個人啟用,
            個人有效啟用,
            傷害事件,
            坦克id,
            個人=True,
        ),
        "team": _建立覆蓋分類摘要(
            團隊涵蓋事件,
            團隊啟用,
            團隊有效啟用,
            傷害事件,
            坦克id,
            個人=False,
        ),
        "skills": 技能摘要,
    }


def _建立覆蓋分類摘要(
    涵蓋事件: set[int],
    啟用鍵值: set[str],
    有效啟用鍵值: set[str],
    傷害事件: list[dict[str, Any]],
    坦克id: int | None,
    *,
    個人: bool,
) -> dict[str, Any]:
    分母事件 = (
        [事件 for 事件 in 傷害事件 if 事件["target_id"] == 坦克id]
        if 個人
        else 傷害事件
    )
    分母 = sum(事件["unmitigated"] for 事件 in 分母事件)
    涵蓋量 = sum(傷害事件[索引]["unmitigated"] for 索引 in 涵蓋事件)
    return {
        "activation_count": len(啟用鍵值),
        "effective_activation_count": len(有效啟用鍵值),
        "effective_activation_percent": 百分比(len(有效啟用鍵值), len(啟用鍵值)),
        "covered_unmitigated_damage": 整理總量(涵蓋量),
        "total_unmitigated_damage": 整理總量(分母),
        "damage_coverage_percent": 百分比(涵蓋量, 分母),
    }


def 套用支援統計(
    玩家列表: list[dict[str, Any]],
    治療表格: Any,
    支援事件: dict[str, Any] | None,
    *,
    預設戰鬥時間毫秒: float | None,
    戰鬥結束時間: float,
) -> dict[str, Any] | None:
    """把小型摘要直接加到單場玩家列，並回傳 fight 層計算脈絡。"""

    角色玩家 = [玩家 for 玩家 in 玩家列表 if isinstance(玩家, dict)]
    目標玩家 = [玩家 for 玩家 in 角色玩家 if 玩家.get("job") in 坦克職業 | 補師職業]
    if not 目標玩家:
        return None

    治療資料 = _取得表格資料(治療表格)
    if not 治療資料 or not isinstance(治療資料.get("entries"), list):
        # 新資料若把 Healing table 缺漏當成全員 0，後續排行榜會產生無法回補的假資料；
        # 直接讓 report 本輪失敗並由既有 retry/backoff 流程重試，才符合「新 fight 必須收錄」契約。
        raise RuntimeError("FFLogs Healing table 回應不完整，無法建立坦補支援統計。")
    治療時間毫秒 = 轉數值(治療資料.get("combatTime")) or 預設戰鬥時間毫秒
    id索引, guid索引, 名稱索引 = _建立治療列索引(治療表格)
    同名玩家數: dict[str, int] = {}
    for 玩家 in 角色玩家:
        名稱 = 玩家.get("name")
        if isinstance(名稱, str):
            同名玩家數[名稱] = 同名玩家數.get(名稱, 0) + 1

    隊伍玩家id = {
        玩家id
        for 玩家 in 角色玩家
        if (玩家id := 轉整數(玩家.get("fflogs_id"))) is not None
    }
    事件 = 支援事件 or {}
    傷害事件 = _正規化傷害事件(事件.get("damage_taken"), 隊伍玩家id)

    for 玩家 in 目標玩家:
        職業 = 玩家.get("job")
        治療列 = _找出治療列(玩家, id索引, guid索引, 名稱索引)
        if 職業 in 補師職業:
            玩家["healing_stats"] = _建立補師治療摘要(治療列, 治療時間毫秒)
        if 職業 not in 坦克職業:
            continue

        坦克id = 轉整數(玩家.get("fflogs_id"))
        坦克承傷事件 = [傷害 for 傷害 in 傷害事件 if 傷害["target_id"] == 坦克id]
        治療防護 = _拆解坦克自身治療與防護(玩家, 治療列, 同名玩家數)
        self_healing = 治療防護["self_healing"]
        玩家["tank_stats"] = {
            "calculation_version": 支援統計計算版本,
            "source": "fflogs_healing_table_and_events",
            "damage_taken": 整理總量(sum(傷害["amount"] for 傷害 in 坦克承傷事件)),
            "absorbed_damage": 整理總量(sum(傷害["absorbed"] for 傷害 in 坦克承傷事件)),
            "unmitigated_damage": 整理總量(sum(傷害["unmitigated"] for 傷害 in 坦克承傷事件)),
            "self_healing": self_healing,
            "self_healing_hps": 每秒(float(self_healing), 治療時間毫秒) if isinstance(self_healing, (int, float)) else None,
            "personal_protection": 治療防護["personal_protection"],
            "team_protection": 治療防護["team_protection"],
            "target_breakdown_complete": 治療防護["target_breakdown_complete"],
            "mitigation_coverage": _建立減傷覆蓋摘要(
                玩家,
                傷害事件,
                事件.get("friendly_buffs"),
                事件.get("enemy_debuffs"),
                戰鬥結束時間,
            ),
        }

    return {
        "calculation_version": 支援統計計算版本,
        "mitigation_rules_version": 坦克減傷規則版本,
        "raw_events_persisted": False,
        "healer_count": sum(1 for 玩家 in 目標玩家 if 玩家.get("job") in 補師職業),
        "tank_count": sum(1 for 玩家 in 目標玩家 if 玩家.get("job") in 坦克職業),
        "event_counts": {
            "damage_taken": len(事件.get("damage_taken") or []),
            "friendly_buffs": len(事件.get("friendly_buffs") or []),
            "enemy_debuffs": len(事件.get("enemy_debuffs") or []),
        },
    }
