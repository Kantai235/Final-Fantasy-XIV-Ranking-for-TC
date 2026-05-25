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


戰鬥清單查詢 = """
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
      fights(encounterID: $encounterID, difficulty: $difficulty, killType: Kills) {
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


玩家成績查詢 = """
query FightPlayerStats($code: String!, $fightIDs: [Int], $encounterID: Int!, $difficulty: Int!) {
  reportData {
    report(code: $code) {
      playerDetails(
        fightIDs: $fightIDs,
        encounterID: $encounterID,
        difficulty: $difficulty,
        killType: Kills,
        translate: true,
        includeCombatantInfo: false
      )
      damageDone: table(
        dataType: DamageDone,
        fightIDs: $fightIDs,
        encounterID: $encounterID,
        difficulty: $difficulty,
        killType: Kills,
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
