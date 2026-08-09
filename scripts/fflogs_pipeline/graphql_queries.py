"""FFLogs GraphQL 查詢字串。

這些查詢只描述 Data Fetching Layer 需要向 FFLogs 取得的欄位；
欄位語意、排行榜去重與公開資料輸出規則仍留在 scripts/fetch_fflogs.py，
避免拆檔時改變資料權威來源。
"""

淺層掃描查詢 = """
query RecentReports($startTime: Float!, $endTime: Float!, $page: Int!, $limit: Int!, $zoneID: Int!) {
  reportData {
    reports(startTime: $startTime, endTime: $endTime, page: $page, limit: $limit, zoneID: $zoneID) {
      data {
        code
        title
        startTime
        endTime
        region {
          id
          name
        }
      }
      current_page
      has_more_pages
    }
  }
}
"""


# 查詢分成三階段是為了節省 API 配額：
# 1. 淺層 reports 查詢只列出時間區間內的公開報告。
# 2. masterData actors 先確認報告是否含繁中服玩家，避免對無關報告查完整戰鬥。
# 3. 確認命中後才查 fight list 與 damage/playerDetails，整理可追溯的排行榜資料。
深層過濾查詢 = """
query ReportMasterData($code: String!) {
  reportData {
    report(code: $code) {
      code
      masterData {
        actors(type: "Player") {
          gameID
          icon
          id
          name
          petOwner
          server
          subType
          type
        }
      }
    }
  }
}
"""


報告狀態查詢 = """
query ReportStatus($code: String!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      visibility
      archiveStatus {
        isArchived
        isAccessible
        archiveDate
      }
    }
  }
}
"""


戰鬥清單查詢模板 = """
query ReportFightList($code: String!, $encounterID: Int!, $difficulty: Int!) {
  reportData {
    report(code: $code) {
      code
      title
      startTime
      endTime
      exportedSegments
      revision
      segments
      visibility
      archiveStatus {
        isArchived
        isAccessible
        archiveDate
      }
      region {
        id
        name
        compactName
        slug
      }
      zone {
        id
        name
        frozen
      }
      guild {
        id
        name
        type
        competitionMode
        stealthMode
        server {
          ...ServerFields
        }
      }
      guildTag {
        id
        name
      }
      owner {
        id
        name
      }
      rankedCharacters {
        id
        canonicalID
        lodestoneID
        name
        hidden
        server {
          ...ServerFields
        }
      }
      phases {
        encounterID
        separatesWipes
        phases {
          id
          name
          isIntermission
        }
      }
      fights(encounterID: $encounterID, difficulty: $difficulty__KILL_TYPE_FILTER__) {
        id
        encounterID
        name
        startTime
        endTime
        combatTime
        originalEncounterID
        fightPercentage
        difficulty
        kill
        completeRaid
        inProgress
        hasEcho
        lastPhase
        lastPhaseAsAbsoluteIndex
        lastPhaseIsIntermission
        size
        standardComposition
        wipeCalledTime
        friendlyPlayers
        enemyPlayers
        boundingBox {
          minX
          maxX
          minY
          maxY
        }
        dungeonPulls {
          id
          encounterID
          name
          startTime
          endTime
          kill
          x
          y
          boundingBox {
            minX
            maxX
            minY
            maxY
          }
          maps {
            id
          }
          enemyNPCs {
            id
            gameID
            minimumInstanceID
            maximumInstanceID
            minimumInstanceGroupID
            maximumInstanceGroupID
          }
        }
        enemyNPCs {
          gameID
          id
          instanceCount
          groupCount
          petOwner
        }
        enemyPets {
          gameID
          id
          instanceCount
          groupCount
          petOwner
        }
        friendlyNPCs {
          gameID
          id
          instanceCount
          groupCount
          petOwner
        }
        friendlyPets {
          gameID
          id
          instanceCount
          groupCount
          petOwner
        }
        gameZone {
          id
          name
        }
        maps {
          id
        }
        phaseTransitions {
          id
          startTime
        }
        averageItemLevel
        bossPercentage
      }
    }
  }
}

fragment ServerFields on Server {
  id
  name
  normalizedName
  slug
  region {
    id
    name
    compactName
    slug
  }
  subregion {
    id
    name
  }
}
"""


def 建立戰鬥清單查詢(套用通關篩選: bool = True) -> str:
    # UCoB 的 FFLogs 原生 kill 旗標不穩定；用同一份欄位模板只切換 killType，
    # 避免兩份 GraphQL 查詢欄位日後不同步而讓資料追溯欄位缺漏。
    通關篩選參數 = ", killType: Kills" if 套用通關篩選 else ""
    return 戰鬥清單查詢模板.replace("__KILL_TYPE_FILTER__", 通關篩選參數)


戰鬥清單查詢 = 建立戰鬥清單查詢()
戰鬥清單全部查詢 = 建立戰鬥清單查詢(套用通關篩選=False)
# 混合上傳 report 的 top-level zone 只會指向其中一種內容，例如 report 主 zone 是幻白虎，
# 但內部同時含零式 fight。這個查詢一次取回完整 fight list，讓 fetch_fflogs.py 可以在本地
# 依 encounterID/difficulty 分派到所有啟用副本，而不是被 reports(zoneID) 的主 zone 篩選卡住。
報告完整戰鬥清單查詢 = (
    戰鬥清單查詢模板
    .replace(
        "query ReportFightList($code: String!, $encounterID: Int!, $difficulty: Int!)",
        "query ReportFullFightList($code: String!)",
    )
    .replace(
        "      fights(encounterID: $encounterID, difficulty: $difficulty__KILL_TYPE_FILTER__) {",
        "      fights {",
    )
)


# 戰鬥完整性檢核是暫時性防護：2026-07-28 之後部分日誌的普攻資料會讓團隊總傷害
# 明顯超過敵方生命池。查詢刻意只取「依目標彙總的傷害」與目標 actor 的 instanceCount，
# 不把完整事件序列落地；下一段查詢再以少量事件的 targetResources 取得 maxHitPoints。
#
# 不直接重用玩家 Damage Done 表，是因為排行榜玩家列採 viewBy: Source，而生命池比較
# 必須採 viewBy: Target，才能同時涵蓋王與實際被擊殺的附加目標。
戰鬥完整性目標傷害查詢 = """
query FightIntegrityTargets(
  $code: String!
  $fightID: Int!
  $startTime: Float!
  $endTime: Float!
  $encounterID: Int!
  $difficulty: Int!
) {
  reportData {
    report(code: $code) {
      fights(fightIDs: [$fightID]) {
        enemyNPCs {
          id
          instanceCount
        }
      }
      targetDamage: table(
        dataType: DamageDone
        fightIDs: [$fightID]
        startTime: $startTime
        endTime: $endTime
        encounterID: $encounterID
        difficulty: $difficulty
        hostilityType: Friendlies
        viewBy: Target
        translate: true
      )
    }
  }
}
"""


# M5S～M8S 的異常變體不一定會讓敵方承傷／生命池超過既有門檻，也不一定帶有
# exploitDetails Attack 標記。因此只針對設定中的副本逐一查詢指定 ability；ability 7
# 是多數職業的 Attack，ability 8 則涵蓋吟遊詩人／機工士的 Shot。呼叫端會完整
# 分頁後立刻壓成玩家層命中數、中位數、占比與每秒傷害，不會保存這段 raw events。
戰鬥完整性普攻事件查詢 = """
query FightIntegrityBasicAttackEvents(
  $code: String!
  $fightID: Int!
  $startTime: Float!
  $endTime: Float!
  $abilityID: Float!
) {
  reportData {
    report(code: $code) {
      basicAttacks: events(
        dataType: DamageDone
        fightIDs: [$fightID]
        startTime: $startTime
        endTime: $endTime
        abilityID: $abilityID
        hostilityType: Friendlies
        limit: 10000
        translate: true
      ) {
        data
        nextPageTimestamp
      }
    }
  }
}
"""


def 建立戰鬥完整性目標生命值查詢(目標_id清單: list[int]) -> str:
    # GraphQL 的 targetID 只能逐目標指定；用 alias 合併成一個 request，避免每個王／小怪
    # 都各打一次 API。targetResources.maxHitPoints 只需前幾筆傷害事件即可取得，無須保存 raw events。
    查詢片段 = "\n".join(
        f"""
      target_{索引}: events(
        dataType: DamageDone
        fightIDs: [$fightID]
        startTime: $startTime
        endTime: $endTime
        targetID: {目標_id}
        includeResources: true
        limit: 5
        translate: true
      ) {{
        data
      }}
"""
        for 索引, 目標_id in enumerate(目標_id清單)
    )
    return f"""
query FightIntegrityTargetHealth(
  $code: String!
  $fightID: Int!
  $startTime: Float!
  $endTime: Float!
) {{
  reportData {{
    report(code: $code) {{
{查詢片段}
    }}
  }}
}}
"""


玩家成績查詢模板 = """
query FightPlayerStats($code: String!, $fightIDs: [Int], $encounterID: Int!, $difficulty: Int!) {
  reportData {
    report(code: $code) {
      playerDetails(
        fightIDs: $fightIDs,
        encounterID: $encounterID,
        difficulty: $difficulty,
__KILL_TYPE_FILTER__
        translate: true,
        includeCombatantInfo: false
      )
      damageDone: table(
        dataType: DamageDone,
        fightIDs: $fightIDs,
        encounterID: $encounterID,
        difficulty: $difficulty,
__KILL_TYPE_FILTER__
        hostilityType: Friendlies,
        viewBy: Source,
        translate: true
      )
      rankings(
        fightIDs: $fightIDs,
        encounterID: $encounterID,
        difficulty: $difficulty,
        playerMetric: dps,
        timeframe: Historical
      )
    }
  }
}
"""


def 建立玩家成績查詢(套用通關篩選: bool = True) -> str:
    通關篩選列 = "        killType: Kills,\n" if 套用通關篩選 else ""
    return 玩家成績查詢模板.replace("__KILL_TYPE_FILTER__\n", 通關篩選列)


玩家成績查詢 = 建立玩家成績查詢()
玩家成績全部查詢 = 建立玩家成績查詢(套用通關篩選=False)
