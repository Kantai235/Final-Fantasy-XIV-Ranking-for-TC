from __future__ import annotations

from dataclasses import dataclass


# 本檔只保存「xivanalysis 明確覆寫、且 XIVAPI Action.csv 無法安全推回」的 GCD 規則。
# 來源為 xivanalysis/xivanalysis dawntrail 分支 aaa13d4b380f69bf01968c79b78904d9477aa9db：
# - src/data/ACTIONS/index.ts 會替 onGcd action 補上預設 castTime=0、cooldown=2500。
# - src/data/ACTIONS/root/*.ts 與 layers/patch*.ts 的 gcdRecast/cooldown/speedAttribute
#   決定 Always Be Casting 的 recast；例如 7.01 layer 會把 Tendo Setsugekka 調回 2.5 秒。
# 這裡不保存完整 xivanalysis action 表，避免把無關職業循環資料複製進本專案；只有當
# Action.csv 可能把技能本身冷卻誤當 GCD、或 xivanalysis 將該 action 標成非副屬性加速時才列入。
XIVANALYSIS_SOURCE_REPOSITORY = "https://github.com/xivanalysis/xivanalysis"
XIVANALYSIS_SOURCE_COMMIT = "aaa13d4b380f69bf01968c79b78904d9477aa9db"


@dataclass(frozen=True)
class XivanalysisGcdActionRule:
    gcd_recast_ms: int
    substat_adjusted: bool
    status_speed_adjusted: bool = True


def rule(recast_ms: int, *, substat: bool, status_speed: bool = True) -> XivanalysisGcdActionRule:
    return XivanalysisGcdActionRule(
        gcd_recast_ms=recast_ms,
        substat_adjusted=substat,
        status_speed_adjusted=status_speed,
    )


XIVANALYSIS_GCD_ACTION_RULES: dict[int, XivanalysisGcdActionRule] = {
    # 占星術士。
    25874: rule(2500, substat=True),   # Macrocosmos

    # 舞者舞步與 Finish 在 xivanalysis 以固定 GCD lock 計算。
    15997: rule(1500, substat=False),  # Standard Step
    15998: rule(1500, substat=False),  # Technical Step
    15999: rule(1000, substat=False),  # Emboite
    16000: rule(1000, substat=False),  # Entrechat
    16001: rule(1000, substat=False),  # Jete
    16002: rule(1000, substat=False),  # Pirouette
    16003: rule(1500, substat=False),  # Standard Finish
    16004: rule(1500, substat=False),  # Technical Finish
    16191: rule(1500, substat=False),  # Single Standard Finish
    16192: rule(1500, substat=False),  # Double Standard Finish
    16193: rule(1500, substat=False),  # Single Technical Finish
    16194: rule(1500, substat=False),  # Double Technical Finish
    16195: rule(1500, substat=False),  # Triple Technical Finish
    16196: rule(1500, substat=False),  # Quadruple Technical Finish
    36984: rule(2500, substat=True),   # Finishing Move

    # 絕槍戰士彈藥與長冷卻 GCD。部分技能在 XIVAPI 具有較長的技能冷卻，
    # 但 xivanalysis 的 ABC 只計入實際 GCD lock。
    16146: rule(2500, substat=True),   # Gnashing Fang
    16153: rule(2500, substat=True),   # Sonic Break
    25760: rule(2500, substat=True),   # Double Down
    36937: rule(2500, substat=True),   # Reign of Beasts
    36938: rule(2500, substat=True),   # Noble Blood
    36939: rule(2500, substat=True),   # Lion Heart

    # Limit Break 在 xivanalysis 屬於 on-GCD，但不受玩家副屬性調整。
    197: rule(1930, substat=False),
    198: rule(3860, substat=False),
    199: rule(3860, substat=False),
    200: rule(5860, substat=False),
    201: rule(6860, substat=False),
    202: rule(8200, substat=False),
    203: rule(5100, substat=False),
    204: rule(8100, substat=False),
    205: rule(12600, substat=False),
    206: rule(4100, substat=False),
    207: rule(7130, substat=False),
    208: rule(10100, substat=False),
    4238: rule(5100, substat=False),
    4239: rule(6100, substat=False),
    4240: rule(3860, substat=False),
    4241: rule(3860, substat=False),
    4242: rule(8200, substat=False),
    4243: rule(8200, substat=False),
    4244: rule(8200, substat=False),
    4245: rule(8200, substat=False),
    4246: rule(12600, substat=False),
    4247: rule(10100, substat=False),
    4248: rule(10100, substat=False),
    7861: rule(8200, substat=False),
    7862: rule(12600, substat=False),
    17105: rule(3860, substat=False),
    17106: rule(8200, substat=False),
    24858: rule(8200, substat=False),
    24859: rule(10100, substat=False),
    34866: rule(8200, substat=False),
    34867: rule(12600, substat=False),

    # 機工士特殊 GCD。Flamethrower 是 channel action，但 xivanalysis 的 ABC
    # 仍只給一次 2.5 秒 GCD lock；不能把 Action.csv 的 60 秒技能冷卻當成覆蓋時間。
    2872: rule(2500, substat=True),    # Hot Shot
    7410: rule(1500, substat=False),   # Heat Blast
    7418: rule(2500, substat=False),   # Flamethrower
    16497: rule(2500, substat=False),  # Auto Crossbow
    16498: rule(2500, substat=False),  # Drill
    16499: rule(2500, substat=False),  # Bioblaster
    16500: rule(2500, substat=True),   # Air Anchor
    16504: rule(2500, substat=False),  # Arm Punch
    25788: rule(2500, substat=True),   # Chain Saw
    36978: rule(1500, substat=False),  # Blazing Shot
    36981: rule(2500, substat=True),   # Excavator
    36982: rule(2500, substat=False),  # Full Metal Field

    # 武僧冥想類 action 在 xivanalysis 是時間軸上的 on-GCD action，但使用固定 lock。
    16476: rule(5000, substat=True),   # Six-sided Star
    36940: rule(1000, substat=False),  # Steeled Meditation
    36942: rule(1000, substat=False),  # Forbidden Meditation
    36943: rule(1000, substat=False),  # Enlightened Meditation

    # 忍者印與忍術的類 GCD lock。
    2259: rule(500, substat=False),
    2261: rule(500, substat=False),
    2263: rule(500, substat=False),
    18805: rule(500, substat=False),
    18806: rule(500, substat=False),
    18807: rule(500, substat=False),
    2260: rule(1500, substat=False),
    2265: rule(1500, substat=False),
    2266: rule(1500, substat=False),
    2267: rule(1500, substat=False),
    2268: rule(1500, substat=False),
    2269: rule(1500, substat=False),
    2270: rule(1500, substat=False),
    2271: rule(1500, substat=False),
    2272: rule(1500, substat=False),
    16491: rule(1500, substat=False),
    16492: rule(1500, substat=False),
    18873: rule(1000, substat=False),
    18874: rule(1000, substat=False),
    18875: rule(1000, substat=False),
    18876: rule(1000, substat=False),
    18877: rule(1000, substat=False),
    18878: rule(1000, substat=False),
    18879: rule(1500, substat=False),
    18880: rule(1500, substat=False),
    18881: rule(1500, substat=False),

    # 繪靈法師有多個 3.3 / 4 / 6 秒 GCD lock，不能全部安全地從 Action.csv 冷卻推回。
    # Motif 類技能在 xivanalysis 不受副屬性調整。
    34653: rule(3300, substat=True),   # Blizzard in Cyan
    34654: rule(3300, substat=True),   # Stone in Yellow
    34655: rule(3300, substat=True),   # Thunder in Magenta
    34659: rule(3300, substat=True),   # Blizzard II in Cyan
    34660: rule(3300, substat=True),   # Stone II in Yellow
    34661: rule(3300, substat=True),   # Thunder II in Magenta
    34663: rule(3300, substat=True),   # Comet in Black
    34664: rule(4000, substat=False),  # Pom Motif
    34665: rule(4000, substat=False),  # Wing Motif
    34666: rule(4000, substat=False),  # Claw Motif
    34667: rule(4000, substat=False),  # Maw Motif
    34668: rule(4000, substat=False),  # Hammer Motif
    34669: rule(4000, substat=False),  # Starry Sky Motif
    34688: rule(6000, substat=True),   # Rainbow Drip
    34689: rule(4000, substat=False),  # Creature Motif
    34690: rule(4000, substat=False),  # Weapon Motif
    34691: rule(4000, substat=False),  # Landscape Motif

    # 赤魔法師近戰連段有固定或短 GCD lock；Grand Impact 在 xivanalysis 也是固定值。
    7527: rule(1500, substat=False),
    7528: rule(1500, substat=False),
    7529: rule(2200, substat=True),
    7530: rule(1500, substat=False),
    37006: rule(2500, substat=False),
    45960: rule(1500, substat=False),
    45961: rule(1500, substat=False),
    45962: rule(2200, substat=True),

    # 職能 action。
    7568: rule(2500, substat=False),   # Esuna

    # 鐮刀師 Enshroud 與長冷卻 GCD。
    24380: rule(2500, substat=False),
    24381: rule(2500, substat=False),
    24395: rule(1500, substat=False),
    24396: rule(1500, substat=False),
    24397: rule(1500, substat=False),

    # 武士返、天道 recast 與時間軸上的冥想 action。
    16485: rule(2500, substat=True),
    16486: rule(2500, substat=True),
    36966: rule(2500, substat=True),
    36967: rule(2500, substat=True),
    36968: rule(3200, substat=True),
    7497: rule(2500, substat=True),

    # 賢者 Eukrasia 相關 action 是固定短 GCD lock；Phlegma/Pneuma 則是受詠速影響的
    # GCD，但本身有長技能冷卻，不能被算成 40 / 120 秒 ABC 覆蓋時間。
    24289: rule(2500, substat=True),
    24290: rule(1000, substat=False),
    24291: rule(1500, substat=False),
    24292: rule(1500, substat=False),
    24293: rule(1500, substat=False),
    24307: rule(2500, substat=True),
    24308: rule(1500, substat=False),
    24313: rule(2500, substat=True),
    24314: rule(1500, substat=False),
    24318: rule(2500, substat=True),
    37034: rule(1500, substat=False),

    # 召喚士 Demi 與元素召喚階段的 GCD lock。
    7427: rule(2500, substat=True),
    25814: rule(3000, substat=True),
    25816: rule(1500, substat=False),
    25817: rule(3000, substat=True),
    25819: rule(1500, substat=True),
    25823: rule(3000, substat=True),
    25825: rule(1500, substat=False),
    25831: rule(2500, substat=True),
    25832: rule(3000, substat=True),
    25834: rule(1500, substat=False),
    25837: rule(3500, substat=True),
    36992: rule(2500, substat=True),

    # 毒蛇劍士長 GCD 與轉化後 GCD lock。Dreadwinder 與 Vicepit 在 xivanalysis 會受
    # Swiftscaled 百分比加速影響，但不受技速副屬性影響。
    34620: rule(3000, substat=False),
    34621: rule(3000, substat=True),
    34622: rule(3000, substat=True),
    34623: rule(3000, substat=False),
    34624: rule(3000, substat=True),
    34625: rule(3000, substat=True),
    34626: rule(2200, substat=True),
    34627: rule(2000, substat=True),
    34628: rule(2000, substat=True),
    34629: rule(2000, substat=True),
    34630: rule(2000, substat=True),
    34631: rule(3000, substat=True),
    34633: rule(3500, substat=True),

    # 白魔法師 Repose 雖然有詠唱時間，但在 xivanalysis 沒有 speedAttribute。
    128: rule(2500, substat=False),
}
