from __future__ import annotations

from dataclasses import dataclass


# 本檔只保存「xivanalysis 明確覆寫、且 XIVAPI Action.csv 無法安全推回」的 GCD 規則。
# 來源為 xivanalysis/xivanalysis dawntrail 分支 b7c000ae57ae1eb11e6a810dadc3bf46dc45f53f：
# - src/data/ACTIONS/index.ts 會替 onGcd action 補上預設 castTime=0、cooldown=2500。
# - src/data/ACTIONS/root/*.ts 與 layers/patch*.ts 的 gcdRecast/cooldown/speedAttribute
#   決定 Always Be Casting 的 recast；例如 7.01 layer 會把 Tendo Setsugekka 調回 2.5 秒。
# 這裡不保存完整 xivanalysis action 表，避免把無關職業循環資料複製進本專案；只有當
# Action.csv 可能把技能本身冷卻誤當 GCD、或 xivanalysis 將該 action 標成非副屬性加速時才列入。
XIVANALYSIS_SOURCE_REPOSITORY = "https://github.com/xivanalysis/xivanalysis"
XIVANALYSIS_SOURCE_COMMIT = "b7c000ae57ae1eb11e6a810dadc3bf46dc45f53f"


@dataclass(frozen=True)
class XivanalysisGcdActionRule:
    gcd_recast_ms: int
    substat_adjusted: bool
    status_speed_adjusted: bool = True
    cast_ms: int | None = None


def rule(
    recast_ms: int,
    *,
    substat: bool,
    status_speed: bool = True,
    cast_ms: int | None = None,
) -> XivanalysisGcdActionRule:
    return XivanalysisGcdActionRule(
        gcd_recast_ms=recast_ms,
        substat_adjusted=substat,
        status_speed_adjusted=status_speed,
        cast_ms=cast_ms,
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
    16146: rule(2500, substat=False),  # Gnashing Fang (xivanalysis patch 7.4: speedAttribute removed)
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


# xivanalysis 的 legacy FFLogs adapter 會在第一個 raw event 前補合成 action：
# 若它先看到某個 status 的 apply/remove，但尚未看過唯一會套用該 status 的 action，
# 就會把該 action 放在 `firstEvent - 300ms`。這份對照只保存「唯一 status -> GCD
# action」的必要子集，來源同上方 commit 的 `src/data/ACTIONS/root/*.ts` 與
# `src/data/STATUSES/root/*.ts`。多個 GCD action 都會套用的 status 不能安全反推，
# 需維持 xivanalysis `actions.length !== 1` 時不合成的語意。
XIVANALYSIS_PREPULL_STATUS_ACTIONS: dict[int, int] = {
    118: 88,      # Chaos Thrust -> CHAOS_THRUST
    150: 133,     # Medica II -> MEDICA_II
    158: 137,     # Regen -> REGEN
    163: 153,     # Thunder III -> THUNDER_III
    189: 17865,   # Bio II -> BIO_II
    815: 3594,    # Benefic -> ENHANCED_BENEFIC_II
    835: 3595,    # Aspected Benefic -> ASPECTED_BENEFIC
    836: 3601,    # Aspected Helios -> ASPECTED_HELIOS
    838: 3599,    # Combust -> COMBUST
    843: 3608,    # Combust II -> COMBUST_II
    1200: 7406,   # Caustic Bite -> CAUSTIC_BITE
    1201: 7407,   # Stormbite -> STORMBITE
    1205: 7418,   # Flamethrower -> FLAMETHROWER
    1210: 7420,   # Thunder IV -> THUNDER_IV
    1228: 7489,   # Higanbana -> HIGANBANA
    1231: 7497,   # Meditate -> MEDITATE
    1818: 15997,  # Standard Step -> STANDARD_STEP
    1819: 15998,  # Technical Step -> TECHNICAL_STEP
    1821: 16192,  # Double Standard Finish -> STANDARD_FINISH
    1822: 16196,  # Quadruple Technical Finish -> TECHNICAL_FINISH
    1837: 16153,  # Sonic Break -> SONIC_BREAK
    1847: 16192,  # Double Standard Finish -> ESPRIT
    1848: 16196,  # Quadruple Technical Finish -> ESPRIT_TECHNICAL
    1865: 7497,   # Meditate -> MEDITATION
    1866: 16499,  # Bioblaster -> BIOBLASTER
    # SMN EVERLASTING_FLIGHT 同時可由 Summon Phoenix 與 Phoenix 相關動作套用；
    # xivanalysis 會因多個 statusesApplied action 而拒絕 prepull status 反推。
    1871: 16532,  # Dia -> DIA
    1881: 16554,  # Combust III -> COMBUST_III
    1895: 16540,  # Biolysis -> BIOLYSIS
    1898: 16139,  # Brutal Shell -> BRUTAL_SHELL
    1902: 3539,   # Royal Authority -> ATONEMENT_READY
    2105: 16192,  # Double Standard Finish -> STANDARD_FINISH_PARTNER
    2514: 16476,  # Six-sided Star -> SIX_SIDED_STAR
    2590: 24396,  # Cross Reaping -> ENHANCED_VOID_REAPING
    2591: 24395,  # Void Reaping -> ENHANCED_CROSS_REAPING
    2594: 24387,  # Soulsow -> SOULSOW
    2606: 24290,  # Eukrasia -> EUKRASIA
    2607: 24291,  # Eukrasian Diagnosis -> EUKRASIAN_DIAGNOSIS
    2608: 24291,  # Eukrasian Diagnosis -> DIFFERENTIAL_DIAGNOSIS
    2614: 24293,  # Eukrasian Dosis -> EUKRASIAN_DOSIS
    2615: 24308,  # Eukrasian Dosis II -> EUKRASIAN_DOSIS_II
    2616: 24314,  # Eukrasian Dosis III -> EUKRASIAN_DOSIS_III
    2623: 24318,  # Pneuma -> PNEUMA
    2690: 2267,   # Raiton -> RAIJU_READY
    2698: 16196,  # Quadruple Technical Finish -> FLOURISHING_FINISH
    2706: 25837,  # Slipstream -> SLIPSTREAM
    2718: 25874,  # Macrocosmos -> MACROCOSMOS
    2719: 25772,  # Chaotic Spring -> CHAOTIC_SPRING
    3645: 34613,  # Hindsbane Fang -> FLANKSTUNG_VENOM
    3646: 34612,  # Hindsting Strike -> FLANKSBANE_VENOM
    3647: 34610,  # Flanksting Strike -> HINDSTUNG_VENOM
    3648: 34611,  # Flanksbane Fang -> HINDSBANE_VENOM
    # VPR 3657-3660 venom 狀態看起來可由 Dreadwinder/Pit 系 GCD 反推，
    # 但在 xivanalysis 的 ACTIONS/root/VPR.ts 中，同一狀態也會由 Twinfang /
    # Twinblood 變化技套用。PrepullStatusAdapterStep 遇到多個 statusesApplied
    # action 時會走 `actions.length !== 1` 並拒絕合成，所以這裡必須刻意不列入。
    3665: 34633,  # Uncoiled Fury -> POISED_FOR_TWINFANG
    3670: 34626,  # Reawaken -> REAWAKENED
    3827: 16460,  # Atonement -> SUPPLICATION_READY
    3828: 36918,  # Supplication -> SEPULCHRE_READY
    3831: 25750,  # Blade of Valor -> BLADE_OF_HONOR_READY
    3833: 3549,   # Fell Cleave -> BURGEONING_FURY
    3834: 25753,  # Primal Rend -> PRIMAL_RUINATION_READY
    3859: 24385,  # Plentiful Harvest -> PERFECTIO_OCCULTA
    3860: 24398,  # Communio -> PERFECTIO_PARATA
    3865: 25788,  # Chain Saw -> EXCAVATOR_READY
    3867: 16192,  # Double Standard Finish -> LAST_DANCE_READY
    3869: 16196,  # Quadruple Technical Finish -> DANCE_OF_THE_DAWN_READY
    3871: 36986,  # High Thunder -> HIGH_THUNDER
    3872: 36987,  # High Thunder II -> HIGH_THUNDER_II
    3880: 37010,  # Medica III -> MEDICA_III
    3894: 37030,  # Helios Conjunction -> HELIOS_CONJUNCTION
    3897: 37032,  # Eukrasian Dyskrasia -> EUKRASIAN_DYSKRASIA
    3901: 3549,   # Fell Cleave -> WRATHFUL
    3905: 24385,  # Plentiful Harvest -> IDEAL_HOST
}
