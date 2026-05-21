from __future__ import annotations

import hashlib
import builtins
import json
import os
import sys
import time
from collections import deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

import requests
from dotenv import load_dotenv

import gcd_coverage_core as gcd_core


# 本檔是資料管線的 Data Fetching Layer。
# 它只負責和 FFLogs GraphQL API 溝通、判斷報告是否含繁中服玩家、保存可追溯的原始戰鬥資料。
# 前端顯示用的統計、個人成績單與職業分布，必須留給 scripts/build_user_data.mjs 聚合。
API_URL = "https://www.fflogs.com/api/v2/client"
TOKEN_URL = "https://www.fflogs.com/oauth/token"

專案根目錄 = Path(__file__).resolve().parents[1]
load_dotenv(專案根目錄 / ".env")

狀態檔案路徑 = 專案根目錄 / "data" / "state.json"
副本設定檔路徑 = 專案根目錄 / "config" / "encounters.json"
FFLogs執行設定檔路徑 = 專案根目錄 / "config" / "fflogs.json"
公開副本清單路徑 = 專案根目錄 / "public" / "data" / "encounters.json"
含隱藏公開副本清單路徑 = 專案根目錄 / "public" / "data" / "all" / "encounters.json"
淺層掃描快取目錄 = 專案根目錄 / "data" / "shallow_scan_cache"

FFLogs執行設定預設值: dict[str, Any] = {
    "report_page_limit": 100,
    "report_max_pages": 25,
    "report_region_scope": "all",
    "scan_window_hours": 24,
    "min_scan_window_seconds": 60,
    "initial_lookback_hours": 24,
    "incremental_lookback_hours": 24,
    "no_clear_retry_hours": 24,
    "delayed_scan_enabled": False,
    "delayed_scan_recent_gap_hours": 24,
    "delayed_scan_lookback_hours": 72,
    "delayed_max_deep_reports_per_run": 0,
    "history_scan_enabled": True,
    "history_scan_full_run": False,
    "history_scan_window_hours": 24,
    "history_scan_windows_per_run": 1,
    "history_scan_recent_gap_hours": 6,
    "history_max_deep_reports_per_run": 25,
    "existing_report_status_check_enabled": False,
    "existing_report_status_check_limit": 0,
    "fetch_gcd_coverage_enabled": False,
    "fetch_gcd_coverage_max_fights_per_run": 0,
    "report_status_cache_limit": 50000,
    "request_timeout": 30,
    "request_connect_timeout": None,
    "request_read_timeout": None,
    "request_retries": 3,
    "rate_limit_requests": 240,
    "rate_limit_window_seconds": 120,
    "rate_limit_padding_seconds": 1.0,
    "rate_limited_cooldown_seconds": 3600,
    "shallow_scan_cache_enabled": True,
    "json_write_retries": 10,
    "json_write_retry_seconds": 0.5,
    "ranking_flush_reports": 25,
    "player_stats_batch_size": 10,
    "retry_report_codes": [],
    "only_report_codes": [],
}

浮點環境設定名稱 = {
    "request_timeout",
    "request_connect_timeout",
    "request_read_timeout",
    "rate_limit_padding_seconds",
    "json_write_retry_seconds",
}


def 分割環境設定清單(值: str) -> list[str]:
    return [項.strip() for 項 in 值.split(",") if 項.strip()]


def 解析環境設定覆寫值(名稱: str, 原始值: str, 參考值: Any) -> Any:
    文字值 = 原始值.strip()
    if 文字值 == "":
        return 參考值

    # workflow 會用環境變數臨時開啟歷史補查；用既有設定值的型別解析，避免把數字或布林
    # 以字串混入後續限流與掃描區間計算。這只處理非敏感執行參數，不讀取 OAuth 憑證。
    if isinstance(參考值, bool):
        標準值 = 文字值.lower()
        if 標準值 in {"1", "true", "yes", "on"}:
            return True
        if 標準值 in {"0", "false", "no", "off"}:
            return False
        raise RuntimeError(f"環境變數 FFLOGS_{名稱.upper()} 必須是布林值。")

    if 名稱 in 浮點環境設定名稱 or isinstance(參考值, float):
        try:
            return float(文字值)
        except ValueError as 錯誤:
            raise RuntimeError(f"環境變數 FFLOGS_{名稱.upper()} 必須是數字。") from 錯誤

    if isinstance(參考值, int) and not isinstance(參考值, bool):
        try:
            return int(文字值)
        except ValueError as 錯誤:
            raise RuntimeError(f"環境變數 FFLOGS_{名稱.upper()} 必須是整數。") from 錯誤

    if isinstance(參考值, list):
        return 分割環境設定清單(文字值)

    return 文字值


def 套用環境變數覆寫設定(設定: dict[str, Any]) -> dict[str, Any]:
    覆寫後設定 = dict(設定)
    for 名稱, 目前值 in list(覆寫後設定.items()):
        環境變數名稱 = f"FFLOGS_{名稱.upper()}"
        if 環境變數名稱 not in os.environ:
            continue

        原始值 = os.environ[環境變數名稱]
        if 原始值.strip() == "":
            continue

        參考值 = FFLogs執行設定預設值.get(名稱, 目前值)
        覆寫後設定[名稱] = 解析環境設定覆寫值(名稱, 原始值, 參考值)

    return 覆寫後設定


def 讀取FFLogs執行設定() -> dict[str, Any]:
    if not FFLogs執行設定檔路徑.exists():
        return 套用環境變數覆寫設定(dict(FFLogs執行設定預設值))

    try:
        with FFLogs執行設定檔路徑.open("r", encoding="utf-8") as 設定檔:
            原始設定 = json.load(設定檔)
    except json.JSONDecodeError as 錯誤:
        raise RuntimeError(f"FFLogs 執行設定不是有效 JSON：{FFLogs執行設定檔路徑}") from 錯誤

    if not isinstance(原始設定, dict):
        raise RuntimeError(f"FFLogs 執行設定必須是物件：{FFLogs執行設定檔路徑}")

    設定 = dict(FFLogs執行設定預設值)
    設定.update(原始設定)
    return 套用環境變數覆寫設定(設定)


FFLogs執行設定 = 讀取FFLogs執行設定()


def 整數設定(名稱: str) -> int:
    try:
        return int(FFLogs執行設定[名稱])
    except (TypeError, ValueError) as 錯誤:
        raise RuntimeError(f"FFLogs 執行設定 {名稱} 必須是整數。") from 錯誤


def 浮點設定(名稱: str) -> float:
    try:
        return float(FFLogs執行設定[名稱])
    except (TypeError, ValueError) as 錯誤:
        raise RuntimeError(f"FFLogs 執行設定 {名稱} 必須是數字。") from 錯誤


def 可選浮點設定(名稱: str, 預設值: float) -> float:
    值 = FFLogs執行設定.get(名稱)
    if 值 is None or 值 == "":
        return 預設值
    try:
        return float(值)
    except (TypeError, ValueError) as 錯誤:
        raise RuntimeError(f"FFLogs 執行設定 {名稱} 必須是數字。") from 錯誤


def 布林設定(名稱: str) -> bool:
    值 = FFLogs執行設定[名稱]
    if isinstance(值, bool):
        return 值
    if isinstance(值, str):
        標準值 = 值.strip().lower()
        if 標準值 in {"1", "true", "yes", "on"}:
            return True
        if 標準值 in {"0", "false", "no", "off"}:
            return False
    raise RuntimeError(f"FFLogs 執行設定 {名稱} 必須是布林值。")


def 正規化報告地區範圍(值: Any) -> str:
    範圍 = str(值 or "all").strip().lower()
    if 範圍 in 報告地區範圍選項:
        return 範圍
    raise RuntimeError("FFLogs 執行設定 report_region_scope 必須是 china 或 all。")


中國區域_ID = 4
報告地區範圍選項 = {"china", "all"}
# FFLogs reports 查詢目前不能直接以伺服器過濾。過去只先看 region=China，但玩家可能把繁中服角色
# 的 report 上傳到其他地區；因此 workflow 會用 all 掃全部地區候選，再用 masterData.actors 的 server
# 欄位篩出真正的繁中服玩家。若短期維護需要降低掃描量，可暫時改用 china。
繁中服伺服器名稱 = {"伊弗利特", "迦樓羅", "利維坦", "鳳凰", "奧汀", "巴哈姆特", "泰坦"}
有效職業名稱 = {
    "Paladin",
    "Warrior",
    "DarkKnight",
    "Gunbreaker",
    "WhiteMage",
    "Scholar",
    "Astrologian",
    "Sage",
    "Monk",
    "Dragoon",
    "Ninja",
    "Samurai",
    "Reaper",
    "Viper",
    "Bard",
    "Machinist",
    "Dancer",
    "BlackMage",
    "Summoner",
    "RedMage",
    "Pictomancer",
    "BlueMage",
}
無效來源類型 = {"Boss", "LimitBreak", "Pet"}
# public/data/rankings/*.json 只輸出這些欄位，避免把 FFLogs 原始資料、上傳者、公會等資訊帶到前端。
# data/rankings/*.reports/*.json 保留已計算完成的 report/fight/player 脈絡；大型 GraphQL raw table
# 不再落地，避免 masterData、damageDone 等可重查資料讓 Git repo 持續膨脹。
公開排行榜條目欄位 = (
    "id",
    "character_name",
    "server",
    "job",
    "dps",
    "rdps",
    "adps",
    "ndps",
    "total_damage",
    "active_time_ms",
    "active_percent",
    "gcd_coverage",
    "gcd_coverage_status",
    "clear_time_ms",
    "clear_time_seconds",
    "damage_downtime_ms",
    "damage_downtime_seconds",
    "damage_time_ms",
    "damage_time_seconds",
    "recorded_at_iso",
    "report_start_time_iso",
    "report_code",
    "report_url",
    "fight_id",
    "fflogs_source_id",
    "duplicate_count",
    "report_hidden",
    "hidden_reason",
    "hidden_detected_at_iso",
    "hidden_source",
    "rank",
    "is_obsolete_record",
    "version_status",
    "version_cutoff_iso",
)

版本紀錄範圍清單 = ("all", "valid", "obsolete")
報告尚未完整匯出狀態 = "deferred_incomplete_export"
無通關報告狀態 = "skipped_no_clear"
報告無法存取隱藏原因 = "private_or_deleted"
可重試報告處理狀態 = {報告尚未完整匯出狀態}
暫時性HTTP狀態碼 = {500, 502, 503, 504}

每頁報告數量 = 整數設定("report_page_limit")
報告查詢最大頁數 = 整數設定("report_max_pages")
報告地區範圍 = 正規化報告地區範圍(FFLogs執行設定.get("report_region_scope"))
掃描全部地區報告 = 報告地區範圍 == "all"
淺層掃描區間小時 = 整數設定("scan_window_hours")
最小切分區間毫秒 = 整數設定("min_scan_window_seconds") * 1000
初次掃描回溯小時 = 整數設定("initial_lookback_hours")
增量掃描回溯小時 = max(0, 整數設定("incremental_lookback_hours"))
無通關報告重試小時 = max(0, 整數設定("no_clear_retry_hours"))
無通關報告重試毫秒 = 無通關報告重試小時 * 60 * 60 * 1000
延遲掃描已啟用 = 布林設定("delayed_scan_enabled")
延遲掃描最近避讓小時 = max(0, 整數設定("delayed_scan_recent_gap_hours"))
延遲掃描回溯小時 = max(
    延遲掃描最近避讓小時,
    整數設定("delayed_scan_lookback_hours"),
)
延遲掃描深層報告上限 = max(0, 整數設定("delayed_max_deep_reports_per_run"))
歷史補查已啟用 = 布林設定("history_scan_enabled")
歷史補查完整執行 = 布林設定("history_scan_full_run")
歷史補查區間小時 = max(1, 整數設定("history_scan_window_hours"))
歷史補查每輪區間數 = max(0, 整數設定("history_scan_windows_per_run"))
歷史補查最近避讓小時 = max(
    0,
    整數設定("history_scan_recent_gap_hours"),
)
歷史補查深層報告上限 = 整數設定("history_max_deep_reports_per_run")
既有報告狀態巡檢已啟用 = 布林設定("existing_report_status_check_enabled")
既有報告狀態巡檢上限 = max(0, 整數設定("existing_report_status_check_limit"))
即時GCD覆蓋率已啟用 = 布林設定("fetch_gcd_coverage_enabled")
即時GCD覆蓋率戰鬥上限 = max(0, 整數設定("fetch_gcd_coverage_max_fights_per_run"))
報告檢查快取上限 = max(0, 整數設定("report_status_cache_limit"))
請求逾時秒數 = max(1.0, 浮點設定("request_timeout"))
請求連線逾時秒數 = max(1.0, 可選浮點設定("request_connect_timeout", min(10.0, 請求逾時秒數)))
請求讀取逾時秒數 = max(1.0, 可選浮點設定("request_read_timeout", 請求逾時秒數))
請求逾時設定 = (請求連線逾時秒數, 請求讀取逾時秒數)
重試次數 = 整數設定("request_retries")
速率限制請求數 = 整數設定("rate_limit_requests")
速率限制視窗秒數 = 整數設定("rate_limit_window_seconds")
速率限制緩衝秒數 = 浮點設定("rate_limit_padding_seconds")
限流冷卻秒數 = 整數設定("rate_limited_cooldown_seconds")
淺層掃描快取已啟用 = 布林設定("shallow_scan_cache_enabled")
json寫入重試次數 = max(1, 整數設定("json_write_retries"))
json寫入重試等待秒數 = max(0.1, 浮點設定("json_write_retry_seconds"))
排行榜批次寫入報告數 = max(1, 整數設定("ranking_flush_reports"))
玩家成績批次查詢戰鬥數 = max(1, 整數設定("player_stats_batch_size"))
台灣時區 = timezone(timedelta(hours=8))


def 台灣時間戳記文字() -> str:
    return datetime.now(台灣時區).strftime("%Y-%m-%d %H:%M:%S %z")


def print(*內容: Any, **選項: Any) -> None:
    分隔字元 = str(選項.get("sep", " "))
    訊息 = 分隔字元.join(str(片段) for 片段 in 內容)
    選項.setdefault("flush", True)
    builtins.print(f"[{台灣時間戳記文字()}] {訊息}", **選項)


class 滑動視窗速率限制器:
    def __init__(self, 最大請求數: int, 視窗秒數: int, 緩衝秒數: float) -> None:
        self.最大請求數 = 最大請求數
        self.視窗秒數 = 視窗秒數
        self.緩衝秒數 = 緩衝秒數
        self.請求時間: deque[float] = deque()

    def 清除過期紀錄(self, 現在: float) -> None:
        while self.請求時間 and 現在 - self.請求時間[0] >= self.視窗秒數:
            self.請求時間.popleft()

    def 等待可送出(self) -> None:
        if self.最大請求數 <= 0 or self.視窗秒數 <= 0:
            return

        while True:
            現在 = time.monotonic()
            self.清除過期紀錄(現在)

            if len(self.請求時間) < self.最大請求數:
                self.請求時間.append(time.monotonic())
                return

            等待秒數 = self.請求時間[0] + self.視窗秒數 + self.緩衝秒數 - 現在
            等待秒數 = max(等待秒數, self.緩衝秒數)
            print(
                f"已達 FFLogs 速率限制 {self.最大請求數} 次 / {self.視窗秒數} 秒，"
                f"等待 {等待秒數:.1f} 秒後繼續。",
                file=sys.stderr,
            )
            time.sleep(等待秒數)


FFLOGS速率限制器 = 滑動視窗速率限制器(速率限制請求數, 速率限制視窗秒數, 速率限制緩衝秒數)


class 區間報告過多錯誤(RuntimeError):
    def __init__(self, 起始時間戳記: int, 結束時間戳記: int) -> None:
        super().__init__(
            f"FFLogs 報告查詢區間過大：{毫秒轉_iso(起始時間戳記)} ~ {毫秒轉_iso(結束時間戳記)}"
        )
        self.起始時間戳記 = 起始時間戳記
        self.結束時間戳記 = 結束時間戳記


def 截短文字(內容: Any, 最大長度: int = 500) -> str:
    文字 = str(內容)
    if len(文字) <= 最大長度:
        return 文字
    return f"{文字[:最大長度]}...（已截短）"


class FFLogs暫時性API錯誤(RuntimeError):
    def __init__(
        self,
        訊息: str,
        *,
        status_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.response_text = response_text

        訊息片段 = 訊息
        if status_code is not None:
            訊息片段 += f"：HTTP {status_code}"
        if response_text:
            訊息片段 += f" {截短文字(response_text)}"
        super().__init__(訊息片段)


class FFLogs限流錯誤(RuntimeError):
    def __init__(self, 回應: requests.Response) -> None:
        super().__init__(f"FFLogs 回傳 HTTP 429：{回應.text}")
        self.回應 = 回應


class FFLogsGraphQL錯誤(RuntimeError):
    def __init__(self, 錯誤列表: list[Any]) -> None:
        self.錯誤列表 = 錯誤列表
        super().__init__(f"FFLogs GraphQL 回傳錯誤：{json.dumps(錯誤列表, ensure_ascii=False)}")


class FFLogs報告存取錯誤(FFLogsGraphQL錯誤):
    pass


class FFLogs報告狀態不可存取錯誤(RuntimeError):
    pass


class FFLogs報告尚未完整匯出錯誤(RuntimeError):
    def __init__(
        self,
        報告代碼: str,
        戰鬥_id: int,
        報告結束時間戳記: int,
        戰鬥結束時間戳記: int,
    ) -> None:
        self.報告代碼 = 報告代碼
        self.戰鬥_id = 戰鬥_id
        self.報告結束時間戳記 = 報告結束時間戳記
        self.戰鬥結束時間戳記 = 戰鬥結束時間戳記
        super().__init__(
            f"FFLogs 報告尚未完整匯出：{報告代碼} fight {戰鬥_id}，"
            f"report end={毫秒轉_iso(報告結束時間戳記)}，"
            f"fight end={毫秒轉_iso(戰鬥結束時間戳記)}"
        )


def GraphQL錯誤是否為報告存取錯誤(錯誤列表: list[Any]) -> bool:
    for 錯誤 in 錯誤列表:
        if not isinstance(錯誤, dict):
            continue

        訊息 = str(錯誤.get("message") or "").lower()
        路徑 = 錯誤.get("path")
        是報告路徑 = isinstance(路徑, list) and "report" in 路徑
        if 是報告路徑 and (
            "permission to view this report" in 訊息
            or "permission to view the report" in 訊息
            or "report does not exist" in 訊息
            or "not found" in 訊息
            or "private" in 訊息
            or "deleted" in 訊息
        ):
            return True

    return False


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


def 現在毫秒() -> int:
    return int(time.time() * 1000)


def 毫秒轉_iso(時間戳記: int | float | None) -> str | None:
    if 時間戳記 is None:
        return None
    return datetime.fromtimestamp(float(時間戳記) / 1000, tz=timezone.utc).isoformat()


def 相對戰鬥時間轉實際時間(報告起始時間戳記: Any, 戰鬥時間戳記: Any) -> int | None:
    報告起點 = 轉_float(報告起始時間戳記)
    戰鬥時間 = 轉_float(戰鬥時間戳記)
    if 報告起點 is None or 戰鬥時間 is None:
        return None
    return int(報告起點 + 戰鬥時間)


def 解析日期時間為毫秒(日期文字: str | None) -> int | None:
    if not 日期文字:
        return None

    文字 = 日期文字.strip().replace("/", "-")
    if not 文字:
        return None

    try:
        if len(文字) == 10:
            日期時間 = datetime.strptime(文字, "%Y-%m-%d").replace(tzinfo=台灣時區)
        else:
            日期時間 = datetime.fromisoformat(文字.replace("Z", "+00:00"))
            if 日期時間.tzinfo is None:
                日期時間 = 日期時間.replace(tzinfo=台灣時區)
    except ValueError as 錯誤:
        raise RuntimeError(f"日期格式無法解析：{日期文字}，請使用 YYYY-MM-DD 或 ISO 8601 格式。") from 錯誤

    return int(日期時間.astimezone(timezone.utc).timestamp() * 1000)


def 讀取_json(路徑: Path, 預設值: Any) -> Any:
    if not 路徑.exists():
        return 預設值

    try:
        with 路徑.open("r", encoding="utf-8") as 檔案:
            return json.load(檔案)
    except json.JSONDecodeError as 錯誤:
        raise RuntimeError(f"無法解析 JSON 檔案：{路徑}") from 錯誤


def 是_windows檔案鎖定錯誤(錯誤: OSError) -> bool:
    return isinstance(錯誤, PermissionError) or getattr(錯誤, "winerror", None) in {5, 32}


def 就地覆寫檔案(來源路徑: Path, 目標路徑: Path) -> None:
    with 來源路徑.open("rb") as 來源檔案:
        with 目標路徑.open("r+b") as 目標檔案:
            目標檔案.seek(0)
            while True:
                區塊 = 來源檔案.read(1024 * 1024)
                if not 區塊:
                    break
                目標檔案.write(區塊)
            目標檔案.truncate()
            目標檔案.flush()
            os.fsync(目標檔案.fileno())


def 寫入_json(路徑: Path, 內容: Any, *, 緊湊格式: bool = False) -> None:
    路徑.parent.mkdir(parents=True, exist_ok=True)
    暫存路徑 = 路徑.with_name(f".{路徑.name}.{os.getpid()}.{time.time_ns()}.tmp")

    try:
        with 暫存路徑.open("w", encoding="utf-8", newline="\n") as 檔案:
            if 緊湊格式:
                json.dump(內容, 檔案, ensure_ascii=False, separators=(",", ":"))
            else:
                json.dump(內容, 檔案, ensure_ascii=False, indent=2, sort_keys=True)
            檔案.write("\n")

        最後錯誤: OSError | None = None
        for 第幾次 in range(1, json寫入重試次數 + 1):
            try:
                os.replace(暫存路徑, 路徑)
                return
            except OSError as 錯誤:
                if not 是_windows檔案鎖定錯誤(錯誤):
                    raise
                最後錯誤 = 錯誤

            等待秒數 = json寫入重試等待秒數 * 第幾次
            print(f"JSON 檔案暫時被鎖定，{等待秒數:.1f} 秒後重試寫入：{路徑}", file=sys.stderr)
            time.sleep(等待秒數)

        if os.name == "nt" and 路徑.exists() and 最後錯誤 is not None:
            try:
                就地覆寫檔案(暫存路徑, 路徑)
                print(f"JSON 檔案無法原子替換，已改用就地覆寫：{路徑}", file=sys.stderr)
                return
            except OSError as 錯誤:
                最後錯誤 = 錯誤

        raise RuntimeError(f"無法寫入 JSON 檔案：{路徑}，請確認檔案未被其他程式鎖定。") from 最後錯誤
    finally:
        if 暫存路徑.exists():
            try:
                暫存路徑.unlink()
            except OSError:
                pass


階段切換清除欄位 = {
    "current_window_start_at",
    "current_window_start_at_iso",
    "current_window_end_at",
    "current_window_end_at_iso",
    "last_completed_window_end_at",
    "last_completed_window_end_at_iso",
    "shallow_reports_found_so_far",
    "current_report_index",
    "total_reports",
    "current_report_code",
    "current_report_start_at",
    "current_report_start_at_iso",
    "processed_reports_in_checkpoint",
    "scan_failed",
    "failure_stage",
    "last_error_type",
    "last_error_message",
    "last_error_at",
    "last_error_at_iso",
}


def 更新副本掃描進度(狀態: dict[str, Any], 副本設定: dict[str, Any], **進度: Any) -> None:
    副本狀態索引 = 狀態.setdefault("encounters", {})
    副本狀態 = 副本狀態索引.setdefault(副本設定["key"], {})
    即時進度 = 副本狀態.setdefault("active_scan", {})
    更新時間戳記 = 現在毫秒()

    新階段 = 進度.get("stage")
    if 新階段 and 新階段 != 即時進度.get("stage"):
        for 欄位名稱 in 階段切換清除欄位:
            if 欄位名稱 not in 進度:
                即時進度.pop(欄位名稱, None)

    即時進度.update(進度)
    即時進度["updated_at"] = 更新時間戳記
    即時進度["updated_at_iso"] = 毫秒轉_iso(更新時間戳記)
    寫入_json(狀態檔案路徑, 狀態)


def 清除副本掃描進度(狀態: dict[str, Any], 副本設定: dict[str, Any]) -> None:
    副本狀態 = (狀態.get("encounters") or {}).get(副本設定["key"]) or {}
    副本狀態.pop("active_scan", None)


def 記錄暫時性掃描失敗(
    狀態: dict[str, Any],
    副本設定: dict[str, Any],
    錯誤: FFLogs暫時性API錯誤,
) -> None:
    現在時間戳記 = 現在毫秒()
    副本狀態 = ((狀態.get("encounters") or {}).get(副本設定["key"]) or {})
    即時進度 = 副本狀態.get("active_scan") if isinstance(副本狀態, dict) else {}
    目前階段 = 即時進度.get("stage") if isinstance(即時進度, dict) else None
    # 不切換 stage，讓 active_scan 保留最後一個淺層掃描區間；
    # 下一輪可直接看到是哪個時間窗遇到 FFLogs 暫時性錯誤。
    更新副本掃描進度(
        狀態,
        副本設定,
        scan_failed=True,
        failure_stage=目前階段,
        last_error_type=錯誤.__class__.__name__,
        last_error_message=截短文字(str(錯誤)),
        last_error_at=現在時間戳記,
        last_error_at_iso=毫秒轉_iso(現在時間戳記),
    )


def 顯示前次未完成掃描(狀態: dict[str, Any], 副本設定: dict[str, Any]) -> None:
    即時進度 = ((狀態.get("encounters") or {}).get(副本設定["key"]) or {}).get("active_scan")
    if not isinstance(即時進度, dict) or not 即時進度:
        return

    階段 = 即時進度.get("stage") or "未知階段"
    最後更新 = 即時進度.get("updated_at_iso") or "未知時間"
    區間起點 = 即時進度.get("current_window_start_at_iso")
    區間終點 = 即時進度.get("current_window_end_at_iso")
    報告代碼 = 即時進度.get("current_report_code")
    補充 = ""
    if 區間起點 and 區間終點:
        補充 = f"，最後區間 {區間起點} ~ {區間終點}"
    if 報告代碼:
        補充 += f"，最後報告 {報告代碼}"
    錯誤訊息 = 即時進度.get("last_error_message")
    if 錯誤訊息:
        補充 += f"，最後錯誤 {截短文字(錯誤訊息, 160)}"

    print(f"偵測到前次未完成掃描：{副本設定['name']} / {階段}，最後更新 {最後更新}{補充}")


def 轉_int_or_none(值: Any) -> int | None:
    if 值 is None or 值 == "":
        return None
    try:
        return int(值)
    except (TypeError, ValueError):
        return None


def 是否中國區域報告(報告: dict[str, Any]) -> bool:
    區域 = 報告.get("region") or {}
    return 轉_int_or_none(區域.get("id")) == 中國區域_ID


def 報告符合淺層地區範圍(報告: dict[str, Any]) -> bool:
    if 掃描全部地區報告:
        return True
    return 是否中國區域報告(報告)


def 淺層地區範圍說明() -> str:
    return "全部地區" if 掃描全部地區報告 else "中國區域"


淺層掃描快取版本 = 2


def 建立淺層掃描快取路徑(副本設定: dict[str, Any], 起始時間戳記: int, 掃描區間小時: int) -> Path:
    zone_id = int(副本設定["zone_id"])
    快取識別 = {
        "version": 淺層掃描快取版本,
        "zone_id": zone_id,
        "start_at": int(起始時間戳記),
        "scan_window_hours": int(掃描區間小時),
        "report_region_scope": 報告地區範圍,
    }
    雜湊 = hashlib.sha256(json.dumps(快取識別, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return 淺層掃描快取目錄 / f"zone_{zone_id}_{起始時間戳記}_{掃描區間小時}_{雜湊}.json"


def 讀取淺層掃描快取(
    副本設定: dict[str, Any],
    起始時間戳記: int,
    掃描區間小時: int,
) -> tuple[Path | None, int | None, list[dict[str, Any]]]:
    if not 淺層掃描快取已啟用:
        return None, None, []

    快取路徑 = 建立淺層掃描快取路徑(副本設定, 起始時間戳記, 掃描區間小時)
    if not 快取路徑.exists():
        return 快取路徑, None, []

    try:
        快取內容 = 讀取_json(快取路徑, {})
    except Exception as 錯誤:
        print(f"淺層掃描快取讀取失敗，將重新掃描：{快取路徑}（{錯誤}）", file=sys.stderr)
        return 快取路徑, None, []

    if not isinstance(快取內容, dict):
        return 快取路徑, None, []
    if 快取內容.get("version") != 淺層掃描快取版本:
        return 快取路徑, None, []
    if int(快取內容.get("zone_id") or -1) != int(副本設定["zone_id"]):
        return 快取路徑, None, []
    if 轉_int_or_none(快取內容.get("start_at")) != int(起始時間戳記):
        return 快取路徑, None, []
    if 轉_int_or_none(快取內容.get("scan_window_hours")) != int(掃描區間小時):
        return 快取路徑, None, []
    if str(快取內容.get("report_region_scope") or "all") != 報告地區範圍:
        return 快取路徑, None, []

    完成至 = 轉_int_or_none(快取內容.get("completed_until"))
    報告列表 = [
        報告
        for 報告 in 快取內容.get("reports") or []
        if isinstance(報告, dict) and 報告.get("code")
    ]
    return 快取路徑, 完成至, 報告列表


def 寫入淺層掃描快取(
    快取路徑: Path | None,
    副本設定: dict[str, Any],
    起始時間戳記: int,
    結束時間戳記: int,
    掃描區間小時: int,
    完成至: int,
    報告列表: list[dict[str, Any]],
) -> None:
    if not 淺層掃描快取已啟用:
        return

    路徑 = 快取路徑 or 建立淺層掃描快取路徑(副本設定, 起始時間戳記, 掃描區間小時)
    更新時間戳記 = 現在毫秒()
    快取內容 = {
        "version": 淺層掃描快取版本,
        "zone_id": int(副本設定["zone_id"]),
        "start_at": int(起始時間戳記),
        "start_at_iso": 毫秒轉_iso(起始時間戳記),
        "target_end_at": int(結束時間戳記),
        "target_end_at_iso": 毫秒轉_iso(結束時間戳記),
        "scan_window_hours": int(掃描區間小時),
        "report_region_scope": 報告地區範圍,
        "completed_until": int(完成至),
        "completed_until_iso": 毫秒轉_iso(完成至),
        "updated_at": 更新時間戳記,
        "updated_at_iso": 毫秒轉_iso(更新時間戳記),
        "reports": 報告列表,
    }
    try:
        寫入_json(路徑, 快取內容, 緊湊格式=True)
    except Exception as 錯誤:
        print(f"淺層掃描快取寫入失敗，掃描仍會繼續：{路徑}（{錯誤}）", file=sys.stderr)


def 可重用淺層快取完成時間(結束時間戳記: int, 快取完成至: int | None) -> int | None:
    if 快取完成至 is None:
        return None

    安全回溯毫秒 = max(0, 增量掃描回溯小時) * 60 * 60 * 1000
    安全可用至 = min(結束時間戳記, 現在毫秒() - 安全回溯毫秒)
    return min(快取完成至, 安全可用至, 結束時間戳記)


def 排行榜檔案路徑(
    副本設定: dict[str, Any],
    public: bool = False,
    *,
    包含隱藏公開資料: bool = False,
) -> Path:
    if public and 包含隱藏公開資料:
        return 專案根目錄 / "public" / "data" / "all" / "rankings" / f"{副本設定['key']}.json"
    根目錄 = 專案根目錄 / "public" if public else 專案根目錄
    return 根目錄 / "data" / "rankings" / f"{副本設定['key']}.json"


def 排行榜報告分片目錄路徑(副本設定: dict[str, Any]) -> Path:
    return 專案根目錄 / "data" / "rankings" / f"{副本設定['key']}.reports"


def 確認路徑在目錄內(根目錄: Path, 目標路徑: Path) -> None:
    已解析根目錄 = 根目錄.resolve()
    已解析目標路徑 = 目標路徑.resolve()
    if 已解析目標路徑 != 已解析根目錄 and 已解析根目錄 not in 已解析目標路徑.parents:
        raise RuntimeError(f"拒絕存取目錄外路徑：{目標路徑}")


def 專案相對路徑(路徑: Path) -> str:
    return 路徑.relative_to(專案根目錄).as_posix()


def 讀取副本設定清單() -> list[dict[str, Any]]:
    # 這份清單只代表「本輪要掃描的副本」。
    # enabled=false 不代表前端要隱藏既有歷史資料，因為排行榜是 append-only 歷史資產。
    設定清單 = 讀取_json(副本設定檔路徑, [])
    if not isinstance(設定清單, list):
        raise RuntimeError(f"副本設定檔格式錯誤：{副本設定檔路徑}")

    啟用清單: list[dict[str, Any]] = []
    for 原始副本 in 設定清單:
        if not isinstance(原始副本, dict):
            continue

        副本 = dict(原始副本)
        if not 副本.get("enabled"):
            continue

        if not 副本.get("key") or not 副本.get("name"):
            raise RuntimeError(f"副本設定缺少 key 或 name：{副本}")
        if 副本.get("zone_id") is None or 副本.get("encounter_id") is None or 副本.get("difficulty") is None:
            raise RuntimeError(f"啟用的副本設定缺少 FFLogs ID：{副本}")
        if not 副本.get("scan_start_date"):
            raise RuntimeError(f"啟用的副本設定缺少 scan_start_date：{副本}")

        副本["zone_id"] = int(副本["zone_id"])
        副本["encounter_id"] = int(副本["encounter_id"])
        副本["difficulty"] = int(副本["difficulty"])
        啟用清單.append(副本)

    if not 啟用清單:
        raise RuntimeError("沒有任何已啟用且設定完整的副本。")

    return 啟用清單


def 讀取全部有效副本設定清單() -> list[dict[str, Any]]:
    設定清單 = 讀取_json(副本設定檔路徑, [])
    if not isinstance(設定清單, list):
        raise RuntimeError(f"副本設定檔格式錯誤：{副本設定檔路徑}")

    副本清單: list[dict[str, Any]] = []
    for 原始副本 in 設定清單:
        if not isinstance(原始副本, dict):
            continue

        if not 原始副本.get("key") or not 原始副本.get("name"):
            continue
        if 原始副本.get("zone_id") is None or 原始副本.get("encounter_id") is None or 原始副本.get("difficulty") is None:
            continue

        副本 = dict(原始副本)
        副本["zone_id"] = int(副本["zone_id"])
        副本["encounter_id"] = int(副本["encounter_id"])
        副本["difficulty"] = int(副本["difficulty"])
        副本清單.append(副本)

    return 副本清單


def 寫入公開副本清單(副本清單: list[dict[str, Any]]) -> None:
    # public/data/encounters.json 是前端選單，不等同於掃描清單。
    # 已停用掃描但仍有 data/rankings 或 public/data/rankings 的副本，必須保留在前端，
    # 否則歷史排行榜與個人成績單會因為設定暫停掃描而從網站消失。
    啟用鍵值 = {副本["key"] for 副本 in 副本清單}
    設定清單 = 讀取_json(副本設定檔路徑, [])
    公開清單: list[dict[str, Any]] = []
    已加入鍵值: set[str] = set()

    for 原始副本 in 設定清單 if isinstance(設定清單, list) else []:
        if not isinstance(原始副本, dict):
            continue

        副本鍵值 = 原始副本.get("key")
        if not 副本鍵值 or not 原始副本.get("name"):
            continue

        副本 = dict(原始副本)
        已有排行榜檔案 = 排行榜檔案路徑(副本).exists() or 排行榜檔案路徑(副本, public=True).exists()
        if 副本鍵值 not in 啟用鍵值 and not 已有排行榜檔案:
            continue

        公開副本 = {
            "key": 副本鍵值,
            "name": 副本["name"],
            "category": 副本.get("category"),
            "enabled": True,
            "data_path": f"data/rankings/{副本鍵值}.json",
        }
        if isinstance(副本.get("version_cutoff"), dict):
            公開副本["version_cutoff"] = 副本["version_cutoff"]
        公開清單.append(公開副本)
        已加入鍵值.add(副本鍵值)

    for 副本 in 副本清單:
        if 副本["key"] in 已加入鍵值:
            continue
        公開副本 = {
            "key": 副本["key"],
            "name": 副本["name"],
            "category": 副本.get("category"),
            "enabled": True,
            "data_path": f"data/rankings/{副本['key']}.json",
        }
        if isinstance(副本.get("version_cutoff"), dict):
            公開副本["version_cutoff"] = 副本["version_cutoff"]
        公開清單.append(公開副本)

    寫入_json(公開副本清單路徑, 公開清單)
    # 副本清單本身不分資料視圖；鏡像檔必須存在，才能讓所有靜態 JSON 使用相同路徑結構。
    寫入_json(含隱藏公開副本清單路徑, 公開清單)


def 取得副本掃描起始時間戳記(副本設定: dict[str, Any], *欄位名稱列表: str) -> int | None:
    for 欄位名稱 in 欄位名稱列表:
        值 = 副本設定.get(欄位名稱)
        if isinstance(值, str) and 值.strip():
            return 解析日期時間為毫秒(值)
    return None


def 取得狀態時間戳記(狀態: dict[str, Any], 副本設定: dict[str, Any]) -> int:
    副本鍵值 = 副本設定["key"]
    if 副本鍵值:
        副本狀態 = (狀態.get("encounters") or {}).get(副本鍵值) or {}
        for 欄位名稱 in ("last_scanned_at", "last_scan_timestamp", "last_scanned_timestamp", "last_timestamp"):
            值 = 副本狀態.get(欄位名稱)
            if isinstance(值, (int, float)) and 值 > 0:
                return int(值)
            if isinstance(值, str) and 值.strip().isdigit():
                return int(值)

    # 相容幾種常見欄位名稱，避免未來手動調整 state.json 後腳本直接失效。
    if 副本鍵值 == "savage_m1s":
        for 欄位名稱 in ("last_scanned_at", "last_scan_timestamp", "last_scanned_timestamp", "last_timestamp"):
            值 = 狀態.get(欄位名稱)
            if isinstance(值, (int, float)) and 值 > 0:
                return int(值)
            if isinstance(值, str) and 值.strip().isdigit():
                return int(值)

    初次掃描起始時間戳記 = 取得副本掃描起始時間戳記(副本設定, "scan_start_date", "initial_scan_start_date")
    if 初次掃描起始時間戳記 is not None:
        return 初次掃描起始時間戳記

    return 現在毫秒() - 初次掃描回溯小時 * 60 * 60 * 1000


def 取得增量掃描起點(狀態時間戳記: int, 副本設定: dict[str, Any]) -> int:
    回溯毫秒 = 增量掃描回溯小時 * 60 * 60 * 1000
    起點 = max(0, 狀態時間戳記 - 回溯毫秒)
    初次掃描起始時間戳記 = 取得副本掃描起始時間戳記(副本設定, "scan_start_date", "initial_scan_start_date")
    if 初次掃描起始時間戳記 is not None:
        起點 = max(起點, 初次掃描起始時間戳記)
    return 起點


def 取得歷史補查起始時間戳記(副本設定: dict[str, Any]) -> int:
    歷史起始時間戳記 = 取得副本掃描起始時間戳記(
        副本設定,
        "history_scan_start_date",
        "scan_start_date",
        "initial_scan_start_date",
    )
    if 歷史起始時間戳記 is not None:
        return 歷史起始時間戳記
    return 現在毫秒() - 初次掃描回溯小時 * 60 * 60 * 1000


def 讀取副本狀態整數欄位(狀態: dict[str, Any], 副本鍵值: str, 欄位名稱: str) -> int | None:
    副本狀態 = (狀態.get("encounters") or {}).get(副本鍵值) or {}
    值 = 副本狀態.get(欄位名稱)
    if isinstance(值, (int, float)) and 值 > 0:
        return int(值)
    if isinstance(值, str) and 值.strip().isdigit():
        return int(值)
    return None


def 建立延遲掃描區間(
    副本設定: dict[str, Any],
    掃描結束時間戳記: int,
) -> tuple[dict[str, int] | None, dict[str, Any] | None]:
    if not 延遲掃描已啟用:
        return None, None

    避讓毫秒 = 延遲掃描最近避讓小時 * 60 * 60 * 1000
    回溯毫秒 = 延遲掃描回溯小時 * 60 * 60 * 1000
    區間起點 = max(0, 掃描結束時間戳記 - 回溯毫秒)
    區間終點 = max(0, 掃描結束時間戳記 - 避讓毫秒 - 1)
    初次掃描起始時間戳記 = 取得副本掃描起始時間戳記(副本設定, "scan_start_date", "initial_scan_start_date")
    if 初次掃描起始時間戳記 is not None:
        區間起點 = max(區間起點, 初次掃描起始時間戳記)

    狀態 = {
        "enabled": True,
        "recent_gap_hours": 延遲掃描最近避讓小時,
        "lookback_hours": 延遲掃描回溯小時,
        "range_start_at": 區間起點,
        "range_start_at_iso": 毫秒轉_iso(區間起點),
        "range_end_at": 區間終點,
        "range_end_at_iso": 毫秒轉_iso(區間終點),
        "reports_found": 0,
        "reports_selected": 0,
        "reports_skipped_known": 0,
        "reports_deferred": 0,
    }
    if 區間終點 <= 區間起點:
        狀態["window"] = None
        return None, 狀態

    區間 = {"start_at": 區間起點, "end_at": 區間終點}
    狀態["window"] = {
        "start_at": 區間起點,
        "start_at_iso": 毫秒轉_iso(區間起點),
        "end_at": 區間終點,
        "end_at_iso": 毫秒轉_iso(區間終點),
    }
    return 區間, 狀態


def 建立歷史補查區間(
    狀態: dict[str, Any],
    副本設定: dict[str, Any],
    歷史終點基準時間戳記: int,
) -> tuple[list[dict[str, int]], dict[str, Any] | None]:
    if not 歷史補查已啟用 or (not 歷史補查完整執行 and 歷史補查每輪區間數 <= 0):
        return [], None

    歷史起點 = 取得歷史補查起始時間戳記(副本設定)
    最近避讓毫秒 = 歷史補查最近避讓小時 * 60 * 60 * 1000
    歷史終點 = 歷史終點基準時間戳記 - 最近避讓毫秒
    if 歷史終點 < 歷史起點:
        return [], {
            "enabled": True,
            "range_start_at": 歷史起點,
            "range_start_at_iso": 毫秒轉_iso(歷史起點),
            "range_end_at": 歷史終點,
            "range_end_at_iso": 毫秒轉_iso(歷史終點),
            "windows": [],
            "next_cursor_at": 歷史起點,
            "next_cursor_at_iso": 毫秒轉_iso(歷史起點),
        }

    游標 = 讀取副本狀態整數欄位(狀態, 副本設定["key"], "history_scan_cursor_at")
    if 游標 is None or 游標 < 歷史起點 or 游標 > 歷史終點:
        游標 = 歷史起點

    區間毫秒 = 歷史補查區間小時 * 60 * 60 * 1000
    區間列表: list[dict[str, int]] = []
    下一游標 = 游標
    最大區間數 = sys.maxsize if 歷史補查完整執行 else 歷史補查每輪區間數

    while len(區間列表) < 最大區間數:
        if 下一游標 > 歷史終點:
            下一游標 = 歷史起點
            break

        區間起點 = 下一游標
        區間終點 = min(區間起點 + 區間毫秒 - 1, 歷史終點)
        區間列表.append({"start_at": 區間起點, "end_at": 區間終點})
        下一游標 = 區間終點 + 1

        if 下一游標 > 歷史終點:
            下一游標 = 歷史起點
            break

    歷史補查狀態 = {
        "enabled": True,
        "range_start_at": 歷史起點,
        "range_start_at_iso": 毫秒轉_iso(歷史起點),
        "range_end_at": 歷史終點,
        "range_end_at_iso": 毫秒轉_iso(歷史終點),
        "current_cursor_at": 游標,
        "current_cursor_at_iso": 毫秒轉_iso(游標),
        "next_cursor_at": 下一游標,
        "next_cursor_at_iso": 毫秒轉_iso(下一游標),
        "windows": [
            {
                "start_at": 區間["start_at"],
                "start_at_iso": 毫秒轉_iso(區間["start_at"]),
                "end_at": 區間["end_at"],
                "end_at_iso": 毫秒轉_iso(區間["end_at"]),
            }
            for 區間 in 區間列表
        ],
    }
    return 區間列表, 歷史補查狀態


def 套用歷史補查深查上限游標(
    歷史補查狀態: dict[str, Any] | None,
    候選列表: list[dict[str, Any]],
    候選統計: dict[str, int],
) -> None:
    if not isinstance(歷史補查狀態, dict) or 候選統計.get("deferred", 0) <= 0:
        return

    視窗列表 = 歷史補查狀態.get("windows") if isinstance(歷史補查狀態.get("windows"), list) else []
    第一視窗 = 視窗列表[0] if 視窗列表 and isinstance(視窗列表[0], dict) else {}
    目前游標 = 轉_int_or_none(歷史補查狀態.get("current_cursor_at"))
    接續游標 = 轉_int_or_none(第一視窗.get("start_at")) or 目前游標
    接續來源 = "current_window_start"
    接續報告代碼: str | None = None

    for 報告 in reversed(候選列表):
        報告時間戳記 = 轉_int_or_none(報告.get("startTime"))
        if 報告時間戳記 is None:
            continue
        接續游標 = max(報告時間戳記, 目前游標 or 報告時間戳記)
        接續來源 = "last_selected_report_start_time"
        接續報告代碼 = str(報告.get("code") or "") or None
        break

    if 接續游標 is None:
        return

    # 歷史補查的 deep report 上限打滿時，代表本輪時間窗還有未知 report 沒有深查。
    # 此時不可把 history_scan_cursor_at 推到下一週，否則 deferred report 要等整個歷史區間繞回才會再被看到。
    # 游標刻意停在最後一筆 selected report 的 startTime，而不是 +1ms，避免同毫秒的其他 report 被跳過；
    # 下一輪會先略過已保存/已檢查的同一筆，接著處理同一時間窗後續尚未更新的候選。
    歷史補查狀態["next_cursor_at"] = 接續游標
    歷史補查狀態["next_cursor_at_iso"] = 毫秒轉_iso(接續游標)
    歷史補查狀態["cursor_limited_by_deep_report_limit"] = True
    歷史補查狀態["cursor_resume_source"] = 接續來源
    歷史補查狀態["cursor_resume_report_code"] = 接續報告代碼


def 分割環境清單(值: str | None) -> list[str]:
    if not 值:
        return []
    return 分割環境設定清單(值)


def 清單設定(名稱: str) -> list[str]:
    值 = FFLogs執行設定.get(名稱, [])
    if 值 is None:
        return []
    if isinstance(值, str):
        return 分割環境清單(值)
    if isinstance(值, list):
        return [str(項).strip() for 項 in 值 if str(項).strip()]
    raise RuntimeError(f"FFLogs 執行設定 {名稱} 必須是陣列或逗號分隔字串。")


def 讀取指定報告代碼() -> tuple[set[str], set[str]]:
    重抓報告代碼 = set(清單設定("retry_report_codes"))
    只處理報告代碼 = set(清單設定("only_report_codes"))
    return 重抓報告代碼, 只處理報告代碼


def 建立手動報告資料(報告代碼: str, 起始時間戳記: int, 結束時間戳記: int) -> dict[str, Any]:
    return {
        "code": 報告代碼,
        "title": "手動指定報告",
        "startTime": 起始時間戳記,
        "endTime": 結束時間戳記,
        "region": {"id": 中國區域_ID, "name": "China"},
    }


def 補入指定報告(
    報告列表: list[dict[str, Any]],
    指定報告代碼: set[str],
    起始時間戳記: int,
    結束時間戳記: int,
) -> list[dict[str, Any]]:
    if not 指定報告代碼:
        return 報告列表

    已存在代碼 = {str(報告.get("code")) for 報告 in 報告列表 if 報告.get("code")}
    補齊後列表 = list(報告列表)
    for 報告代碼 in sorted(指定報告代碼):
        if 報告代碼 not in 已存在代碼:
            補齊後列表.append(建立手動報告資料(報告代碼, 起始時間戳記, 結束時間戳記))

    return 補齊後列表


def 加入掃描來源(報告列表: list[dict[str, Any]], 掃描來源: str) -> list[dict[str, Any]]:
    已標記列表: list[dict[str, Any]] = []
    for 報告 in 報告列表:
        已標記報告 = dict(報告)
        已標記報告["_scan_source"] = 掃描來源
        已標記列表.append(已標記報告)
    return 已標記列表


def 合併淺層報告列表(
    主要報告列表: list[dict[str, Any]],
    補充報告列表: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    合併後列表: list[dict[str, Any]] = []
    已加入代碼: set[str] = set()
    for 報告 in [*主要報告列表, *補充報告列表]:
        代碼 = str(報告.get("code") or "")
        if not 代碼 or 代碼 in 已加入代碼:
            continue
        已加入代碼.add(代碼)
        合併後列表.append(報告)
    return 合併後列表


def 讀取認證設定() -> list[dict[str, Any]]:
    認證清單: list[dict[str, Any]] = []

    json_文字 = os.environ.get("FFLOGS_CLIENT_CREDENTIALS_JSON")
    if json_文字:
        try:
            原始清單 = json.loads(json_文字)
        except json.JSONDecodeError as 錯誤:
            raise RuntimeError("FFLOGS_CLIENT_CREDENTIALS_JSON 不是有效 JSON。") from 錯誤

        if not isinstance(原始清單, list):
            raise RuntimeError("FFLOGS_CLIENT_CREDENTIALS_JSON 必須是陣列。")

        for index, 原始認證 in enumerate(原始清單, start=1):
            if not isinstance(原始認證, dict):
                continue
            client_id = 原始認證.get("client_id") or 原始認證.get("id")
            client_secret = 原始認證.get("client_secret") or 原始認證.get("secret")
            if client_id and client_secret:
                認證清單.append({"name": f"json-{index}", "client_id": str(client_id), "client_secret": str(client_secret)})

    client_ids = 分割環境清單(os.environ.get("FFLOGS_CLIENT_IDS"))
    client_secrets = 分割環境清單(os.environ.get("FFLOGS_CLIENT_SECRETS"))
    if client_ids or client_secrets:
        if len(client_ids) != len(client_secrets):
            raise RuntimeError("FFLOGS_CLIENT_IDS 與 FFLOGS_CLIENT_SECRETS 數量必須相同。")
        for index, (client_id, client_secret) in enumerate(zip(client_ids, client_secrets), start=1):
            認證清單.append({"name": f"list-{index}", "client_id": client_id, "client_secret": client_secret})

    for index in range(1, 21):
        client_id = os.environ.get(f"FFLOGS_CLIENT_ID_{index}")
        client_secret = os.environ.get(f"FFLOGS_CLIENT_SECRET_{index}")
        if client_id and client_secret:
            認證清單.append({"name": f"slot-{index}", "client_id": client_id, "client_secret": client_secret})

    client_id = os.environ.get("FFLOGS_CLIENT_ID")
    client_secret = os.environ.get("FFLOGS_CLIENT_SECRET")
    if client_id and client_secret:
        認證清單.append({"name": "default", "client_id": client_id, "client_secret": client_secret})

    去重後清單: list[dict[str, Any]] = []
    已看過: set[str] = set()
    for 認證 in 認證清單:
        if 認證["client_id"] in 已看過:
            continue
        已看過.add(認證["client_id"])
        認證["token"] = None
        認證["token_expires_at"] = 0.0
        認證["limited_until"] = 0.0
        認證["limiter"] = 滑動視窗速率限制器(速率限制請求數, 速率限制視窗秒數, 速率限制緩衝秒數)
        去重後清單.append(認證)

    if not 去重後清單:
        raise RuntimeError("請先設定至少一組 FFLOGS Client ID 與 Client Secret。")

    return 去重後清單


def post_並重試(
    session: requests.Session,
    url: str,
    *,
    速率限制器: 滑動視窗速率限制器 | None = None,
    限流時直接回傳: bool = False,
    **kwargs: Any,
) -> requests.Response:
    最後錯誤: Exception | None = None
    最後回應: requests.Response | None = None
    使用速率限制器 = 速率限制器 or FFLOGS速率限制器
    實際重試次數 = max(1, 重試次數)
    kwargs.setdefault("timeout", 請求逾時設定)

    for 第幾次 in range(1, 實際重試次數 + 1):
        try:
            使用速率限制器.等待可送出()
            回應 = session.post(url, **kwargs)
            最後回應 = 回應
            最後錯誤 = None
            if 回應.status_code not in {429, *暫時性HTTP狀態碼}:
                return 回應
            if 回應.status_code == 429 and 限流時直接回傳:
                return 回應

            retry_after = 回應.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                等待秒數 = int(retry_after)
            elif 回應.status_code == 429:
                等待秒數 = 速率限制視窗秒數 + int(速率限制緩衝秒數)
            else:
                等待秒數 = min(2 ** 第幾次, 30)
            if 第幾次 >= 實際重試次數:
                break
            print(
                f"FFLogs API 暫時無法回應（第 {第幾次}/{實際重試次數} 次），"
                f"{等待秒數} 秒後重試。HTTP {回應.status_code}",
                file=sys.stderr,
            )
            time.sleep(等待秒數)
        except requests.RequestException as 錯誤:
            最後錯誤 = 錯誤
            等待秒數 = min(2 ** 第幾次, 30)
            錯誤類型 = "請求逾時" if isinstance(錯誤, requests.Timeout) else "連線失敗"
            if 第幾次 >= 實際重試次數:
                break
            print(
                f"{錯誤類型}（第 {第幾次}/{實際重試次數} 次，"
                f"connect/read timeout={請求連線逾時秒數:g}/{請求讀取逾時秒數:g}s），"
                f"{等待秒數} 秒後重試：{錯誤}",
                file=sys.stderr,
            )
            time.sleep(等待秒數)

    if 最後錯誤:
        raise FFLogs暫時性API錯誤(
            "FFLogs API 請求重試後仍失敗",
            response_text=str(最後錯誤),
        ) from 最後錯誤

    if 最後回應 is None:
        raise FFLogs暫時性API錯誤("FFLogs API 請求未取得任何回應")
    return 最後回應


def 取得_bearer_token(
    session: requests.Session,
    client_id: str,
    client_secret: str,
    速率限制器: 滑動視窗速率限制器 | None = None,
) -> tuple[str, int | None]:
    # FFLogs Client Credentials 流程使用 HTTP Basic Auth 傳送 client_id 與 client_secret。
    回應 = post_並重試(
        session,
        TOKEN_URL,
        速率限制器=速率限制器,
        限流時直接回傳=True,
        data={"grant_type": "client_credentials"},
        auth=(client_id, client_secret),
    )

    if 回應.status_code == 429:
        raise FFLogs限流錯誤(回應)

    if not 回應.ok:
        if 回應.status_code in 暫時性HTTP狀態碼:
            raise FFLogs暫時性API錯誤(
                "取得 FFLogs Bearer Token 重試後仍失敗",
                status_code=回應.status_code,
                response_text=回應.text,
            )
        raise RuntimeError(f"取得 FFLogs Bearer Token 失敗：HTTP {回應.status_code} {回應.text}")

    內容 = 回應.json()
    token = 內容.get("access_token")
    if not token:
        raise RuntimeError(f"FFLogs Token 回應缺少 access_token：{內容}")

    expires_in = 轉_int_or_none(內容.get("expires_in"))
    return token, expires_in


class FFLogs認證池:
    def __init__(self, session: requests.Session, 認證清單: list[dict[str, Any]]) -> None:
        self.session = session
        self.認證清單 = 認證清單
        self.目前索引 = 0

    def 可用認證索引(self) -> list[int]:
        現在 = time.monotonic()
        return [index for index, 認證 in enumerate(self.認證清單) if 認證.get("limited_until", 0) <= 現在]

    def 等待可用認證(self) -> None:
        最早時間 = min(認證.get("limited_until", 0) for 認證 in self.認證清單)
        等待秒數 = max(最早時間 - time.monotonic() + 速率限制緩衝秒數, 1)
        print(f"所有 FFLogs 憑證都在冷卻中，等待 {等待秒數:.1f} 秒後繼續。", file=sys.stderr)
        time.sleep(等待秒數)

    def 取得目前認證(self) -> dict[str, Any]:
        while True:
            可用索引 = self.可用認證索引()
            if not 可用索引:
                self.等待可用認證()
                continue

            if self.目前索引 not in 可用索引:
                self.目前索引 = 可用索引[0]
            return self.認證清單[self.目前索引]

    def 切換下一組(self) -> None:
        if len(self.認證清單) <= 1:
            return

        可用索引 = self.可用認證索引()
        if not 可用索引:
            return

        for offset in range(1, len(self.認證清單) + 1):
            下一個索引 = (self.目前索引 + offset) % len(self.認證清單)
            if 下一個索引 in 可用索引:
                self.目前索引 = 下一個索引
                return

    def 標記限流(self, 認證: dict[str, Any], 回應: requests.Response) -> None:
        retry_after = 回應.headers.get("Retry-After")
        if retry_after and retry_after.isdigit():
            冷卻秒數 = int(retry_after)
        else:
            冷卻秒數 = 限流冷卻秒數

        認證["limited_until"] = time.monotonic() + 冷卻秒數
        認證["token"] = None
        認證["token_expires_at"] = 0.0
        print(f"FFLogs 憑證 {認證['name']} 被限流，冷卻 {冷卻秒數} 秒後再使用。", file=sys.stderr)
        self.切換下一組()

    def 取得_token(self, 認證: dict[str, Any] | None = None) -> tuple[dict[str, Any], str]:
        while True:
            使用認證 = 認證 or self.取得目前認證()
            現在 = time.monotonic()
            if 使用認證.get("token") and 使用認證.get("token_expires_at", 0) > 現在 + 60:
                return 使用認證, 使用認證["token"]

            try:
                token, expires_in = 取得_bearer_token(
                    self.session,
                    使用認證["client_id"],
                    使用認證["client_secret"],
                    使用認證.get("limiter"),
                )
            except FFLogs限流錯誤 as 錯誤:
                self.標記限流(使用認證, 錯誤.回應)
                認證 = None
                continue

            使用認證["token"] = token
            使用認證["token_expires_at"] = 現在 + (expires_in or 3600)
            return 使用認證, token


def 執行_graphql(
    session: requests.Session,
    認證池: FFLogs認證池,
    查詢: str,
    變數: dict[str, Any] | None = None,
) -> dict[str, Any]:
    while True:
        認證 = 認證池.取得目前認證()
        認證, token = 認證池.取得_token(認證)
        回應 = post_並重試(
            session,
            API_URL,
            速率限制器=認證.get("limiter"),
            限流時直接回傳=True,
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"query": 查詢, "variables": 變數 or {}},
        )

        if 回應.status_code == 429:
            認證池.標記限流(認證, 回應)
            continue

        認證池.切換下一組()
        break

    if not 回應.ok:
        if 回應.status_code in 暫時性HTTP狀態碼:
            raise FFLogs暫時性API錯誤(
                "FFLogs GraphQL 請求重試後仍失敗",
                status_code=回應.status_code,
                response_text=回應.text,
            )
        raise RuntimeError(
            f"FFLogs GraphQL 請求失敗：HTTP {回應.status_code} {截短文字(回應.text)}"
        )

    內容 = 回應.json()
    錯誤列表 = 內容.get("errors")
    if 錯誤列表:
        if GraphQL錯誤是否為報告存取錯誤(錯誤列表):
            raise FFLogs報告存取錯誤(錯誤列表)
        raise FFLogsGraphQL錯誤(錯誤列表)

    return 內容.get("data") or {}


def 擷取時間區間報告(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    起始時間戳記: int,
    結束時間戳記: int,
) -> list[dict[str, Any]]:
    報告列表: list[dict[str, Any]] = []
    已看過代碼: set[str] = set()
    頁碼 = 1

    while 頁碼 <= 報告查詢最大頁數:
        變數 = {
            "startTime": float(起始時間戳記),
            "endTime": float(結束時間戳記),
            "page": 頁碼,
            "limit": 每頁報告數量,
            "zoneID": 副本設定["zone_id"],
        }
        try:
            資料 = 執行_graphql(session, 認證池, 淺層掃描查詢, 變數)
        except RuntimeError as 錯誤:
            if "maximum allowed page" in str(錯誤):
                raise 區間報告過多錯誤(起始時間戳記, 結束時間戳記) from 錯誤
            raise
        分頁 = (((資料.get("reportData") or {}).get("reports")) or {})

        for 報告 in 分頁.get("data") or []:
            代碼 = 報告.get("code")
            if not 代碼 or 代碼 in 已看過代碼:
                continue

            # reports 查詢無法用繁中服伺服器過濾；地區只決定候選池大小，真正身分仍看 masterData server。
            if not 報告符合淺層地區範圍(報告):
                continue

            已看過代碼.add(代碼)
            報告列表.append(報告)

        if not 分頁.get("has_more_pages"):
            break

        if 頁碼 >= 報告查詢最大頁數:
            raise 區間報告過多錯誤(起始時間戳記, 結束時間戳記)

        頁碼 += 1

    return 報告列表


def 擷取可容納區間報告(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    起始時間戳記: int,
    結束時間戳記: int,
) -> list[dict[str, Any]]:
    try:
        return 擷取時間區間報告(session, 認證池, 副本設定, 起始時間戳記, 結束時間戳記)
    except 區間報告過多錯誤:
        if 結束時間戳記 - 起始時間戳記 <= 最小切分區間毫秒:
            raise

        中間時間戳記 = 起始時間戳記 + (結束時間戳記 - 起始時間戳記) // 2
        print(
            f"掃描區間仍超過 FFLogs 分頁上限，改切半查詢："
            f"{毫秒轉_iso(起始時間戳記)} ~ {毫秒轉_iso(結束時間戳記)}",
            file=sys.stderr,
        )

        前半段 = 擷取可容納區間報告(session, 認證池, 副本設定, 起始時間戳記, 中間時間戳記)
        後半段 = 擷取可容納區間報告(session, 認證池, 副本設定, 中間時間戳記 + 1, 結束時間戳記)
        return 前半段 + 後半段


def 擷取最新報告(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    起始時間戳記: int,
    結束時間戳記: int,
    進度回呼: Callable[[dict[str, Any]], None] | None = None,
    *,
    掃描區間小時: int | None = None,
    階段名稱: str = "淺層掃描",
) -> list[dict[str, Any]]:
    報告索引: dict[str, dict[str, Any]] = {}
    實際掃描區間小時 = max(掃描區間小時 or 淺層掃描區間小時, 1)
    區間毫秒 = 實際掃描區間小時 * 60 * 60 * 1000
    目前起點 = 起始時間戳記
    快取路徑, 快取完成至, 快取報告列表 = 讀取淺層掃描快取(副本設定, 起始時間戳記, 實際掃描區間小時)
    可重用完成至 = 可重用淺層快取完成時間(結束時間戳記, 快取完成至)

    if 可重用完成至 is not None and 可重用完成至 >= 起始時間戳記:
        for 報告 in 快取報告列表:
            報告開始時間 = 轉_float(報告.get("startTime"))
            if 報告開始時間 is not None and int(報告開始時間) > 可重用完成至:
                continue
            代碼 = 報告.get("code")
            if 代碼:
                報告索引[代碼] = 報告
        目前起點 = min(可重用完成至 + 1, 結束時間戳記)
        print(
            f"{階段名稱}重用快取至 {毫秒轉_iso(可重用完成至)}，"
            f"已載入 {len(報告索引)} 份報告。"
        )

    while 目前起點 < 結束時間戳記:
        目前終點 = min(目前起點 + 區間毫秒 - 1, 結束時間戳記)
        print(f"{階段名稱}區間：{毫秒轉_iso(目前起點)} ~ {毫秒轉_iso(目前終點)}")
        if 進度回呼:
            進度回呼(
                {
                    "stage": 階段名稱,
                    "current_window_start_at": 目前起點,
                    "current_window_start_at_iso": 毫秒轉_iso(目前起點),
                    "current_window_end_at": 目前終點,
                    "current_window_end_at_iso": 毫秒轉_iso(目前終點),
                    "shallow_reports_found_so_far": len(報告索引),
                }
            )

        for 報告 in 擷取可容納區間報告(session, 認證池, 副本設定, 目前起點, 目前終點):
            代碼 = 報告.get("code")
            if 代碼:
                報告索引[代碼] = 報告

        if 進度回呼:
            進度回呼(
                {
                    "stage": 階段名稱,
                    "last_completed_window_end_at": 目前終點,
                    "last_completed_window_end_at_iso": 毫秒轉_iso(目前終點),
                    "shallow_reports_found_so_far": len(報告索引),
                }
            )

        寫入淺層掃描快取(
            快取路徑,
            副本設定,
            起始時間戳記,
            結束時間戳記,
            實際掃描區間小時,
            目前終點,
            sorted(報告索引.values(), key=lambda 報告: 報告.get("startTime") or 0),
        )
        目前起點 = 目前終點 + 1

    return sorted(報告索引.values(), key=lambda 報告: 報告.get("startTime") or 0)


def 報告是否包含繁中服玩家(
    session: requests.Session,
    認證池: FFLogs認證池,
    報告代碼: str,
) -> tuple[bool, list[dict[str, Any]]]:
    資料 = 執行_graphql(session, 認證池, 深層過濾查詢, {"code": 報告代碼})
    報告 = ((資料.get("reportData") or {}).get("report")) or {}
    master_data = 報告.get("masterData") or {}
    玩家列表 = master_data.get("actors") or []

    有效玩家 = [
        玩家
        for 玩家 in 玩家列表
        if isinstance(玩家, dict) and 玩家.get("server") in 繁中服伺服器名稱
    ]

    return bool(有效玩家), 有效玩家


def 取得本輪報告繁中服檢查結果(
    本輪快取: dict[str, dict[str, Any]],
    session: requests.Session,
    認證池: FFLogs認證池,
    報告代碼: str,
) -> tuple[bool, list[dict[str, Any]]]:
    if 報告代碼 not in 本輪快取:
        try:
            # masterData.actors 是 report 層級資料，與 M1S/M2S 這類 encounter 無關；
            # 同一輪 workflow 只需要查一次，後續同 code 來自其他副本或歷史補查來源時重用結果。
            有繁中服玩家, 繁中服玩家 = 報告是否包含繁中服玩家(session, 認證池, 報告代碼)
            本輪快取[報告代碼] = {
                "ok": True,
                "has_traditional_chinese_players": 有繁中服玩家,
                "traditional_chinese_players": 繁中服玩家,
            }
        except Exception as 錯誤:
            本輪快取[報告代碼] = {"ok": False, "error": 錯誤}

    記錄 = 本輪快取[報告代碼]
    if 記錄.get("ok"):
        return bool(記錄.get("has_traditional_chinese_players")), list(記錄.get("traditional_chinese_players") or [])

    錯誤 = 記錄.get("error")
    if isinstance(錯誤, Exception):
        raise 錯誤
    raise RuntimeError(f"本輪 report 檢查快取缺少錯誤內容：{報告代碼}")


def 查詢報告目前狀態(
    session: requests.Session,
    認證池: FFLogs認證池,
    報告代碼: str,
) -> dict[str, Any]:
    # 既有 report 狀態巡檢只需要確認 report 是否還可讀，不重查戰鬥與玩家表格。
    # 這讓 workflow 能用固定 request 預算輪巡舊紀錄，並在 report 轉為不可存取時套用同一套 hidden 標記。
    資料 = 執行_graphql(session, 認證池, 報告狀態查詢, {"code": 報告代碼})
    報告 = ((資料.get("reportData") or {}).get("report")) or None
    if not isinstance(報告, dict):
        raise FFLogs報告狀態不可存取錯誤(f"FFLogs report 無法讀取或不存在：{報告代碼}")

    封存狀態 = 報告.get("archiveStatus")
    if isinstance(封存狀態, dict) and 封存狀態.get("isAccessible") is False:
        raise FFLogs報告狀態不可存取錯誤(
            f"FFLogs report archiveStatus.isAccessible=false：{報告代碼}"
        )

    return 報告


def 查詢通關戰鬥(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    報告代碼: str,
) -> dict[str, Any] | None:
    資料 = 執行_graphql(
        session,
        認證池,
        戰鬥清單查詢,
        {"code": 報告代碼, "encounterID": 副本設定["encounter_id"], "difficulty": 副本設定["difficulty"]},
    )
    return ((資料.get("reportData") or {}).get("report")) or None


def 查詢玩家成績(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    報告代碼: str,
    戰鬥_id: int,
) -> dict[str, Any]:
    資料 = 執行_graphql(
        session,
        認證池,
        玩家成績查詢,
        {
            "code": 報告代碼,
            "fightIDs": [戰鬥_id],
            "encounterID": 副本設定["encounter_id"],
            "difficulty": 副本設定["difficulty"],
        },
    )
    報告 = ((資料.get("reportData") or {}).get("report")) or {}
    return {
        "player_details": 報告.get("playerDetails"),
        "damage_done": 報告.get("damageDone"),
        "rankings": 報告.get("rankings"),
    }


def 建立玩家成績批次查詢(
    戰鬥_id清單: list[int],
    戰鬥時間範圍索引: dict[int, dict[str, int | float]] | None = None,
) -> str:
    # playerDetails 與 damageDone 必須維持「單一 fight」語意，否則多場通關會被 FFLogs 聚合成同一張表，
    # rDPS/aDPS 分母、停手時間與玩家列表都會失去逐場可追溯性。這裡用 GraphQL alias 把多個單 fight
    # 查詢包進同一個 HTTP request，降低 workflow 遇到多場戰鬥 report 時的 API request 數量。
    欄位片段: list[str] = []
    for 索引, 戰鬥_id in enumerate(戰鬥_id清單):
        時間範圍 = (戰鬥時間範圍索引 or {}).get(戰鬥_id) or {}
        起始時間 = 轉_float(時間範圍.get("start_time"))
        結束時間 = 轉_float(時間範圍.get("end_time"))
        時間範圍參數 = ""
        if 起始時間 is not None and 結束時間 is not None and 結束時間 > 起始時間:
            # fightIDs 在少數舊報告上會跟 report.endTime 的舊匯出邊界一起截斷 damageDone table。
            # 同時提供 fight 的相對 start/end time，可讓 FFLogs 回傳與網頁 CSV 匯出一致的完整時間窗。
            時間範圍參數 = f"""
        startTime: {起始時間},
        endTime: {結束時間},"""
        欄位片段.append(
            f"""
      playerDetails_{索引}: playerDetails(
        fightIDs: [{戰鬥_id}],
{時間範圍參數}
        encounterID: $encounterID,
        difficulty: $difficulty,
        killType: Kills,
        translate: true,
        includeCombatantInfo: false
      )
      damageDone_{索引}: table(
        dataType: DamageDone,
        fightIDs: [{戰鬥_id}],
{時間範圍參數}
        encounterID: $encounterID,
        difficulty: $difficulty,
        killType: Kills,
        hostilityType: Friendlies,
        viewBy: Source,
        translate: true
      )
      rankings_{索引}: rankings(
        fightIDs: [{戰鬥_id}],
        encounterID: $encounterID,
        difficulty: $difficulty,
        playerMetric: dps,
        timeframe: Historical
      )
"""
        )

    return f"""
query FightPlayerStatsBatch($code: String!, $encounterID: Int!, $difficulty: Int!) {{
  reportData {{
    report(code: $code) {{
{''.join(欄位片段)}
    }}
  }}
}}
"""


def 查詢多場玩家成績(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    報告代碼: str,
    戰鬥_id清單: list[int],
    戰鬥時間範圍索引: dict[int, dict[str, int | float]] | None = None,
) -> dict[int, dict[str, Any]]:
    def 查詢批次(批次戰鬥_id清單: list[int]) -> dict[int, dict[str, Any]]:
        資料 = 執行_graphql(
            session,
            認證池,
            建立玩家成績批次查詢(批次戰鬥_id清單, 戰鬥時間範圍索引),
            {
                "code": 報告代碼,
                "encounterID": 副本設定["encounter_id"],
                "difficulty": 副本設定["difficulty"],
            },
        )
        報告 = ((資料.get("reportData") or {}).get("report")) or {}
        批次成績索引: dict[int, dict[str, Any]] = {}
        for 索引, 戰鬥_id in enumerate(批次戰鬥_id清單):
            批次成績索引[戰鬥_id] = {
                "player_details": 報告.get(f"playerDetails_{索引}"),
                "damage_done": 報告.get(f"damageDone_{索引}"),
                "rankings": 報告.get(f"rankings_{索引}"),
            }
        return 批次成績索引

    def 安全查詢批次(批次戰鬥_id清單: list[int]) -> dict[int, dict[str, Any]]:
        try:
            return 查詢批次(批次戰鬥_id清單)
        except FFLogs報告存取錯誤:
            raise
        except FFLogsGraphQL錯誤 as 錯誤:
            if len(批次戰鬥_id清單) <= 1:
                raise

            # 若 FFLogs 拒絕較大的 alias 查詢，改切半重試；這保留「能省 request 就省」，
            # 也避免一次大型批次失敗時整份 report 無法整理。
            中間 = len(批次戰鬥_id清單) // 2
            print(
                f"{報告代碼} 玩家成績批次查詢失敗，改切半重試："
                f"{批次戰鬥_id清單}（{錯誤}）",
                file=sys.stderr,
            )
            前半段 = 安全查詢批次(批次戰鬥_id清單[:中間])
            後半段 = 安全查詢批次(批次戰鬥_id清單[中間:])
            return {**前半段, **後半段}

    有效戰鬥_id清單: list[int] = []
    已加入戰鬥_id: set[int] = set()
    for 戰鬥_id in 戰鬥_id清單:
        if type(戰鬥_id) is not int or 戰鬥_id in 已加入戰鬥_id:
            continue
        已加入戰鬥_id.add(戰鬥_id)
        有效戰鬥_id清單.append(戰鬥_id)

    成績索引: dict[int, dict[str, Any]] = {}
    for 起點 in range(0, len(有效戰鬥_id清單), 玩家成績批次查詢戰鬥數):
        批次戰鬥_id清單 = 有效戰鬥_id清單[起點 : 起點 + 玩家成績批次查詢戰鬥數]
        成績索引.update(安全查詢批次(批次戰鬥_id清單))

    return 成績索引


def 遞迴尋找字典(內容: Any) -> list[dict[str, Any]]:
    if isinstance(內容, dict):
        結果 = [內容]
        for 值 in 內容.values():
            結果.extend(遞迴尋找字典(值))
        return 結果

    if isinstance(內容, list):
        結果: list[dict[str, Any]] = []
        for 值 in 內容:
            結果.extend(遞迴尋找字典(值))
        return 結果

    return []


def 轉_float(值: Any) -> float | None:
    if isinstance(值, (int, float)):
        return float(值)
    if isinstance(值, str):
        try:
            return float(值.replace(",", ""))
        except ValueError:
            return None
    return None


def 第一個數值(資料: dict[str, Any], 欄位列表: tuple[str, ...]) -> float | None:
    for 欄位 in 欄位列表:
        值 = 轉_float(資料.get(欄位))
        if 值 is not None:
            return 值
    return None


def 正規化職業名稱(候選: dict[str, Any]) -> str | None:
    for 欄位名稱 in ("type", "subType", "icon"):
        職業 = 候選.get(欄位名稱)
        if not isinstance(職業, str):
            continue
        if 職業 in 無效來源類型 or 職業.isdigit():
            return None
        if 職業 in 有效職業名稱:
            return 職業
    return None


def 加入來源(玩家: dict[str, Any], 來源名稱: str) -> None:
    來源列表 = 玩家.setdefault("sources", [])
    if 來源名稱 not in 來源列表:
        來源列表.append(來源名稱)


def 取得玩家明細資料(原始成績: dict[str, Any]) -> dict[str, Any]:
    player_details = 原始成績.get("player_details")
    if not isinstance(player_details, dict):
        return {}

    資料 = player_details.get("data")
    if not isinstance(資料, dict):
        return {}

    明細資料 = 資料.get("playerDetails")
    return 明細資料 if isinstance(明細資料, dict) else {}


def 取得傷害統計資料(原始成績: dict[str, Any]) -> dict[str, Any]:
    damage_done = 原始成績.get("damage_done")
    if not isinstance(damage_done, dict):
        return {}

    資料 = damage_done.get("data")
    if not isinstance(資料, dict):
        return {}

    return 資料


def 取得傷害統計列(原始成績: dict[str, Any]) -> list[dict[str, Any]]:
    資料 = 取得傷害統計資料(原始成績)

    entries = 資料.get("entries")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def 整理毫秒數值(數值: float | None) -> int | float | None:
    if 數值 is None:
        return None
    return int(數值) if float(數值).is_integer() else round(數值, 3)


def 毫秒轉秒數(數值: float | int | None) -> float | None:
    if 數值 is None:
        return None
    return round(float(數值) / 1000, 3)


def 建立傷害表格摘要(原始成績: dict[str, Any]) -> dict[str, Any]:
    資料 = 取得傷害統計資料(原始成績)
    return {鍵: 值 for 鍵, 值 in 資料.items() if 鍵 != "entries"}


def 計算傷害時間資訊(原始成績: dict[str, Any], 戰鬥時間毫秒: float | None) -> dict[str, int | float | None]:
    # FFLogs damageDone table 的 totalTime/combatTime/damageDowntime 比 fight.combatTime 更接近輸出統計分母。
    # rDPS/aDPS 會受停手時間影響；若沒有表格資料才退回戰鬥時間，避免把缺漏資料誤算成 0 秒。
    傷害資料 = 取得傷害統計資料(原始成績)
    表格總時間毫秒 = 轉_float(傷害資料.get("totalTime"))
    表格戰鬥時間毫秒 = 轉_float(傷害資料.get("combatTime"))
    停手時間毫秒 = 轉_float(傷害資料.get("damageDowntime"))
    if 停手時間毫秒 is None and 傷害資料:
        停手時間毫秒 = 0
    分母基準毫秒 = 表格戰鬥時間毫秒 if 表格戰鬥時間毫秒 is not None else 戰鬥時間毫秒

    傷害計算時間毫秒 = None
    if 分母基準毫秒 is not None:
        傷害計算時間毫秒 = 分母基準毫秒 - (停手時間毫秒 or 0)
        if 傷害計算時間毫秒 <= 0:
            傷害計算時間毫秒 = 分母基準毫秒

    return {
        "fflogs_total_time_ms": 整理毫秒數值(表格總時間毫秒),
        "fflogs_combat_time_ms": 整理毫秒數值(表格戰鬥時間毫秒),
        "damage_downtime_ms": 整理毫秒數值(停手時間毫秒),
        "damage_time_ms": 整理毫秒數值(傷害計算時間毫秒),
    }


def 建立玩家索引(
    原始成績: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, str], dict[str, str], dict[str, str]]:
    玩家索引: dict[str, dict[str, Any]] = {}
    id_索引: dict[str, str] = {}
    guid_索引: dict[str, str] = {}
    名稱暫存: dict[str, list[str]] = {}

    # playerDetails 是可信的玩家名單來源；它包含角色、伺服器與職業，不包含技能、王、寵物或 LB。
    for 群組列表 in 取得玩家明細資料(原始成績).values():
        if not isinstance(群組列表, list):
            continue

        for 候選 in 群組列表:
            if not isinstance(候選, dict):
                continue

            名稱 = 候選.get("name")
            伺服器 = 候選.get("server")
            職業 = 正規化職業名稱(候選)
            if not isinstance(名稱, str) or not 名稱 or 伺服器 not in 繁中服伺服器名稱 or not 職業:
                continue

            主鍵 = f"id:{候選.get('id')}" if 候選.get("id") is not None else f"{名稱}@{伺服器}"
            玩家索引[主鍵] = {
                "name": 名稱,
                "server": 伺服器,
                "job": 職業,
                "dps": None,
                "rdps": None,
                "adps": None,
                "ndps": None,
                "total_damage": None,
                "fflogs_id": 候選.get("id"),
                "fflogs_guid": 候選.get("guid"),
                "sources": ["player_details"],
            }

            if 候選.get("id") is not None:
                id_索引[str(候選.get("id"))] = 主鍵
            if 候選.get("guid") is not None:
                guid_索引[str(候選.get("guid"))] = 主鍵
            名稱暫存.setdefault(名稱, []).append(主鍵)

    名稱索引 = {名稱: keys[0] for 名稱, keys in 名稱暫存.items() if len(set(keys)) == 1}
    return 玩家索引, id_索引, guid_索引, 名稱索引


def 找出玩家主鍵(
    傷害列: dict[str, Any],
    id_索引: dict[str, str],
    guid_索引: dict[str, str],
    名稱索引: dict[str, str],
) -> str | None:
    # 傷害表格有時只帶 id/guid/name 的其中一種；跨伺服器同名角色不能只靠 name 合併。
    # 名稱索引只在 playerDetails 中同名候選唯一時使用，避免把不同伺服器或分身誤判成同一人。
    if 傷害列.get("id") is not None and str(傷害列.get("id")) in id_索引:
        return id_索引[str(傷害列.get("id"))]
    if 傷害列.get("guid") is not None and str(傷害列.get("guid")) in guid_索引:
        return guid_索引[str(傷害列.get("guid"))]

    名稱 = 傷害列.get("name")
    if isinstance(名稱, str):
        return 名稱索引.get(名稱)

    return None


def 每秒數值(總量: float | None, 戰鬥時間毫秒: float | None) -> float | None:
    if 總量 is None or not 戰鬥時間毫秒 or 戰鬥時間毫秒 <= 0:
        return None
    return round(總量 / (戰鬥時間毫秒 / 1000), 2)


def 計算_active_percent(active_time_ms: Any, clear_time_ms: Any) -> float | None:
    active_time = 轉_float(active_time_ms)
    clear_time = 轉_float(clear_time_ms)
    if active_time is None or clear_time is None or clear_time <= 0:
        return None
    return round(active_time / clear_time * 100, 2)


class 即時GCD覆蓋率計算器:
    def __init__(self) -> None:
        self.啟用 = 即時GCD覆蓋率已啟用
        self.戰鬥上限 = 即時GCD覆蓋率戰鬥上限
        self.已查詢戰鬥數 = 0
        self.已更新玩家數 = 0
        self.失敗戰鬥數 = 0
        self._已提示達到上限 = False
        self._已提示停用原因: str | None = None
        self._metadata_store = gcd_core.ActionMetadataStore()
        self._metadata_已載入 = False
        self._graph_cache: dict[tuple[str, int, float, float], dict[str, Any]] = {}
        self.checked_at_iso = 毫秒轉_iso(現在毫秒()) or ""

    def 可查詢下一場(self) -> bool:
        if not self.啟用 or self._已提示停用原因:
            return False
        if self.戰鬥上限 > 0 and self.已查詢戰鬥數 >= self.戰鬥上限:
            if not self._已提示達到上限:
                print(f"即時 GCD 覆蓋率已達本輪上限：{self.戰鬥上限} 場戰鬥。")
                self._已提示達到上限 = True
            return False
        return True

    def 載入技能資料(self) -> bool:
        if self._metadata_已載入:
            return True
        try:
            self._metadata_store.preload()
        except RuntimeError as 錯誤:
            self._已提示停用原因 = str(錯誤)
            print(
                f"無法載入 GCD 技能資料，本輪即時 GCD 覆蓋率暫停，資料仍可由手動 backfill 補齊：{錯誤}",
                file=sys.stderr,
            )
            return False
        self._metadata_已載入 = True
        return True

    def 補齊戰鬥玩家GCD覆蓋率(
        self,
        session: requests.Session,
        認證池: FFLogs認證池,
        報告代碼: str,
        戰鬥: dict[str, Any],
        玩家列表: list[dict[str, Any]],
    ) -> None:
        if not 玩家列表 or not self.可查詢下一場():
            return

        fight_id = gcd_core.to_int(戰鬥.get("fight_id"))
        start_time = gcd_core.first_number(戰鬥.get("start_time"), 戰鬥.get("startTime"))
        end_time = gcd_core.first_number(戰鬥.get("end_time"), 戰鬥.get("endTime"))
        if fight_id is None or start_time is None or end_time is None:
            return
        if not any(gcd_core.to_int(玩家.get("fflogs_id")) is not None for 玩家 in 玩家列表):
            return
        if not self.載入技能資料():
            return

        self.已查詢戰鬥數 += 1
        graph_cache_key = (報告代碼, fight_id, start_time, end_time)
        try:
            graph = self._graph_cache.get(graph_cache_key)
            if graph is None:
                graph = gcd_core.query_fight_casts_graph(執行_graphql, session, 認證池, 報告代碼, 戰鬥)
                self._graph_cache[graph_cache_key] = graph
        except Exception as 錯誤:  # noqa: BLE001
            # GCD 是衍生欄位；Casts graph 暫時失敗不能阻擋排行榜主資料落地。
            self.失敗戰鬥數 += 1
            print(f"{報告代碼} fight={fight_id} 即時 GCD 覆蓋率計算失敗，保留缺 key 狀態：{錯誤}", file=sys.stderr)
            return

        本場更新數 = 0
        for 玩家 in 玩家列表:
            source_id = gcd_core.to_int(玩家.get("fflogs_id"))
            if source_id is None:
                continue

            coverage = gcd_core.calculate_gcd_coverage_from_graph(
                graph,
                self._metadata_store,
                source_id=source_id,
                job=玩家.get("job"),
                fight_end_time=end_time,
                fallback_denominator_ms=gcd_core.first_number(
                    戰鬥.get("clear_time_ms"),
                    end_time - start_time,
                    戰鬥.get("damage_time_ms"),
                ),
            )
            if not coverage:
                continue

            玩家["gcd_coverage"] = coverage
            玩家["gcd_coverage_status"] = gcd_core.build_gcd_coverage_status(checked_at_iso=self.checked_at_iso)
            本場更新數 += 1

        self.已更新玩家數 += 本場更新數
        if 本場更新數:
            print(f"{報告代碼} fight={fight_id} 已即時計算 GCD 覆蓋率：{本場更新數} 位玩家。")

    def 建立統計(self) -> dict[str, Any]:
        return {
            "enabled": self.啟用,
            "max_fights_per_run": self.戰鬥上限,
            "fights_queried": self.已查詢戰鬥數,
            "players_updated": self.已更新玩家數,
            "fights_failed": self.失敗戰鬥數,
            "disabled_reason": self._已提示停用原因,
        }


def 從原始成績整理玩家_dps(原始成績: dict[str, Any], 戰鬥時間毫秒: float | None) -> list[dict[str, Any]]:
    # playerDetails 提供身分，damageDone 提供輸出數值；兩者必須合併才有可信的「繁中服角色 + 職業 + DPS」。
    # 這裡不做全服統計或 UI 排序，只產出每場戰鬥可回溯的玩家列。
    玩家索引, id_索引, guid_索引, 名稱索引 = 建立玩家索引(原始成績)

    for 傷害列 in 取得傷害統計列(原始成績):
        if not 正規化職業名稱(傷害列):
            continue

        主鍵 = 找出玩家主鍵(傷害列, id_索引, guid_索引, 名稱索引)
        if not 主鍵:
            continue

        玩家 = 玩家索引[主鍵]
        總傷害 = 第一個數值(傷害列, ("total", "amount", "damage", "totalDamage"))
        if 總傷害 is not None:
            玩家["total_damage"] = int(總傷害)
            玩家["dps"] = 每秒數值(總傷害, 戰鬥時間毫秒)

        rdps_總量 = 第一個數值(傷害列, ("totalRDPS", "rdps", "rDPS"))
        adps_總量 = 第一個數值(傷害列, ("totalADPS", "adps", "aDPS"))
        ndps_總量 = 第一個數值(傷害列, ("totalNDPS", "ndps", "nDPS"))
        玩家["rdps"] = 每秒數值(rdps_總量, 戰鬥時間毫秒)
        玩家["adps"] = 每秒數值(adps_總量, 戰鬥時間毫秒)
        玩家["ndps"] = 每秒數值(ndps_總量, 戰鬥時間毫秒)
        玩家["active_time_ms"] = int(傷害列["activeTime"]) if isinstance(傷害列.get("activeTime"), int) else None
        加入來源(玩家, "damage_done")

    整理後玩家 = [
        玩家
        for 玩家 in 玩家索引.values()
        if 玩家.get("server") in 繁中服伺服器名稱
        and 玩家.get("job") in 有效職業名稱
        and 玩家.get("dps") is not None
    ]
    整理後玩家.sort(key=lambda 玩家: 玩家.get("dps") or 0, reverse=True)
    return 整理後玩家


def 建立_sha256(內容: Any) -> str:
    原文 = json.dumps(內容, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(原文.encode("utf-8")).hexdigest()


def 建立戰鬥簽章(戰鬥: dict[str, Any]) -> str:
    # 同一場戰鬥可能由不同隊員上傳成多份 report；用通關時間與全隊成績建立簽章來辨識同場戰鬥。
    玩家簽章 = [
        {
            "name": 玩家.get("name"),
            "server": 玩家.get("server"),
            "job": 玩家.get("job"),
            "dps": 玩家.get("dps"),
            "total_damage": 玩家.get("total_damage"),
        }
        for 玩家 in 戰鬥.get("players", [])
        if isinstance(玩家, dict)
    ]
    玩家簽章.sort(
        key=lambda 玩家: (
            玩家.get("name") or "",
            玩家.get("server") or "",
            玩家.get("job") or "",
            玩家.get("dps") or 0,
            玩家.get("total_damage") or 0,
        )
    )
    return 建立_sha256(
        {
            "encounter_id": 戰鬥.get("encounter_id"),
            "difficulty": 戰鬥.get("difficulty"),
            "clear_time_ms": 戰鬥.get("clear_time_ms"),
            "damage_downtime_ms": 戰鬥.get("damage_downtime_ms"),
            "damage_time_ms": 戰鬥.get("damage_time_ms"),
            "players": 玩家簽章,
        }
    )


def 成績是否優先(候選: dict[str, Any], 目前最佳: dict[str, Any] | None) -> bool:
    # 同一角色同一職業只保留最佳成績：rDPS 優先，平手才看通關時間與 aDPS。
    # 前端與 build_user_data.mjs 也沿用同樣排序，避免不同頁面顯示不同「最佳」。
    if 目前最佳 is None:
        return True

    候選_rdps = 候選.get("rdps") or 候選.get("dps") or 0
    目前_rdps = 目前最佳.get("rdps") or 目前最佳.get("dps") or 0
    if 候選_rdps != 目前_rdps:
        return 候選_rdps > 目前_rdps

    候選通關時間 = 候選.get("clear_time_seconds") or float("inf")
    目前通關時間 = 目前最佳.get("clear_time_seconds") or float("inf")
    if 候選通關時間 != 目前通關時間:
        return 候選通關時間 < 目前通關時間

    return (候選.get("adps") or 候選.get("dps") or 0) > (目前最佳.get("adps") or 目前最佳.get("dps") or 0)


def 解析_iso_時間毫秒(時間文字: Any) -> int | None:
    if not isinstance(時間文字, str) or not 時間文字.strip():
        return None

    try:
        時間 = datetime.fromisoformat(時間文字.strip().replace("Z", "+00:00"))
    except ValueError:
        return None

    if 時間.tzinfo is None:
        時間 = 時間.replace(tzinfo=timezone.utc)
    return int(時間.timestamp() * 1000)


def 取得副本版本截止設定(副本資料: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(副本資料, dict):
        return None

    設定 = 副本資料.get("version_cutoff")
    if not isinstance(設定, dict):
        return None

    截止時間 = 設定.get("obsolete_after_iso")
    截止毫秒 = 解析_iso_時間毫秒(截止時間)
    if 截止毫秒 is None:
        return None

    # 版本 cutoff 是公開資料 schema 的一部分；保留原本標籤可以讓前端直接顯示 7.1 與台灣時間，
    # 但實際判定一律使用 UTC ISO，避免本機時區不同導致同一筆 FFLogs 紀錄被分到不同版本。
    return {
        **設定,
        "obsolete_after_iso": datetime.fromtimestamp(截止毫秒 / 1000, tz=timezone.utc).isoformat().replace("+00:00", "Z"),
    }


def 標記成績版本狀態(成績: dict[str, Any], 版本設定: dict[str, Any] | None) -> dict[str, Any]:
    if not 版本設定:
        return 成績

    紀錄毫秒 = 解析_iso_時間毫秒(成績.get("recorded_at_iso") or 成績.get("report_start_time_iso"))
    截止毫秒 = 解析_iso_時間毫秒(版本設定.get("obsolete_after_iso"))
    是否過版 = 紀錄毫秒 is not None and 截止毫秒 is not None and 紀錄毫秒 >= 截止毫秒
    成績["is_obsolete_record"] = 是否過版
    成績["version_status"] = "obsolete" if 是否過版 else "valid"
    成績["version_cutoff_iso"] = 版本設定["obsolete_after_iso"]
    return 成績


def 成績符合版本範圍(成績: dict[str, Any], 版本範圍: str, 版本設定: dict[str, Any] | None) -> bool:
    if not 版本設定 or 版本範圍 == "all":
        return True

    是否過版 = bool(成績.get("is_obsolete_record"))
    if 版本範圍 == "obsolete":
        return 是否過版
    if 版本範圍 == "valid":
        return not 是否過版
    return True


def 標準化排行榜條目(條目: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(條目, dict):
        return None

    成績 = dict(條目)
    名稱 = 成績.get("character_name")
    伺服器 = 成績.get("server")
    職業 = 成績.get("job")
    dps = 成績.get("dps")
    if not 名稱 or 伺服器 not in 繁中服伺服器名稱 or 職業 not in 有效職業名稱 or dps is None:
        return None

    角色鍵值 = 成績.get("character_key") or f"{名稱}@{伺服器}:{職業}"
    成績["character_key"] = 角色鍵值

    if not 成績.get("id"):
        成績["id"] = 建立_sha256(
            {
                "character": 角色鍵值,
                "active_time_ms": 成績.get("active_time_ms"),
                "rdps": 成績.get("rdps"),
                "adps": 成績.get("adps"),
                "dps": dps,
                "total_damage": 成績.get("total_damage"),
                "damage_time_ms": 成績.get("damage_time_ms"),
                "report_code": 成績.get("report_code"),
                "fight_id": 成績.get("fight_id"),
            }
        )

    來源報告 = 成績.get("source_reports")
    if isinstance(來源報告, list):
        成績["source_reports"] = list(dict.fromkeys(str(報告代碼) for 報告代碼 in 來源報告 if 報告代碼))
    elif 成績.get("report_code"):
        成績["source_reports"] = [str(成績["report_code"])]
    else:
        成績["source_reports"] = []

    重複數量 = 轉_int_or_none(成績.get("duplicate_count"))
    成績["duplicate_count"] = max(重複數量 or 1, len(成績["source_reports"]) or 1)
    return 成績


def 登記排行榜條目(
    成績: dict[str, Any],
    精確成績索引: dict[str, dict[str, Any]],
) -> None:
    標準成績 = 標準化排行榜條目(成績)
    if not 標準成績:
        return

    精確成績鍵值 = 標準成績["id"]
    既有成績 = 精確成績索引.get(精確成績鍵值)
    if 既有成績:
        既有來源報告 = 既有成績.setdefault("source_reports", [])
        for 報告代碼 in 標準成績.get("source_reports") or []:
            if 報告代碼 not in 既有來源報告:
                既有來源報告.append(報告代碼)
        既有成績["duplicate_count"] = max(
            轉_int_or_none(既有成績.get("duplicate_count")) or 1,
            len(既有來源報告) or 1,
        )
        標準成績 = 既有成績
    else:
        精確成績索引[精確成績鍵值] = 標準成績


def 報告已標記隱藏(報告: Any) -> bool:
    return isinstance(報告, dict) and bool(報告.get("report_hidden") or 報告.get("hidden_report"))


def 標記排行榜報告隱藏(
    排行榜: dict[str, Any],
    報告代碼: str,
    *,
    原因: str = 報告無法存取隱藏原因,
    來源: str = "fetch_fflogs",
    詳細原因: str | None = None,
) -> bool:
    # 將 report 狀態集中標在來源節點，公開建置層即可用同一套規則排除一般公開資料。
    報告索引 = 排行榜.get("reports") if isinstance(排行榜.get("reports"), dict) else {}
    報告 = 報告索引.get(str(報告代碼))
    if not isinstance(報告, dict):
        return False

    現在時間戳記 = 現在毫秒()
    欄位更新 = {
        "report_hidden": True,
        "hidden_reason": 原因,
        "hidden_source": 來源,
        "hidden_detected_at": 現在時間戳記,
        "hidden_detected_at_iso": 毫秒轉_iso(現在時間戳記),
    }
    if 詳細原因:
        欄位更新["hidden_detail"] = 詳細原因

    已變更 = any(報告.get(欄位) != 值 for 欄位, 值 in 欄位更新.items())
    if 已變更:
        報告.update(欄位更新)
    return 已變更


既有報告狀態巡檢狀態鍵 = "existing_report_status_check"


def 取得既有報告排序時間(報告: dict[str, Any]) -> int:
    # 巡檢順序以 report 本身的時間為主；舊資料若缺 report_start_time，才退回 fight 的實際紀錄時間。
    # fight.start_time 是 report 內相對時間，不能直接拿來跨 report 排序。
    候選時間: list[int] = []
    for 欄位 in ("report_start_time", "startTime", "fetched_at"):
        時間 = 轉_float(報告.get(欄位))
        if 時間 is not None and 時間 >= 0:
            候選時間.append(int(時間))

    for 欄位 in ("report_start_time_iso", "startTimeISO", "fetched_at_iso"):
        時間 = 解析_iso_時間毫秒(報告.get(欄位))
        if 時間 is not None and 時間 >= 0:
            候選時間.append(時間)

    for 戰鬥 in 報告.get("fights") or []:
        if not isinstance(戰鬥, dict):
            continue
        for 欄位 in ("recorded_at", "recordedAt"):
            時間 = 轉_float(戰鬥.get(欄位))
            if 時間 is not None and 時間 >= 0:
                候選時間.append(int(時間))
        for 欄位 in ("recorded_at_iso", "recordedAtISO"):
            時間 = 解析_iso_時間毫秒(戰鬥.get(欄位))
            if 時間 is not None and 時間 >= 0:
                候選時間.append(時間)

    return min(候選時間, default=0)


def 建立既有報告狀態巡檢候選(
    副本清單: list[dict[str, Any]],
    排行榜索引: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    候選列表: list[dict[str, Any]] = []
    for 副本設定 in 副本清單:
        副本鍵值 = 副本設定["key"]
        排行榜 = 排行榜索引.get(副本鍵值) or {}
        報告索引 = 排行榜.get("reports") if isinstance(排行榜.get("reports"), dict) else {}
        for 原始報告代碼, 報告 in 報告索引.items():
            if not isinstance(報告, dict) or 報告已標記隱藏(報告):
                continue

            報告代碼 = str(原始報告代碼)
            排序時間 = 取得既有報告排序時間(報告)
            候選列表.append(
                {
                    "encounter_key": 副本鍵值,
                    "encounter_name": 副本設定.get("name") or 副本鍵值,
                    "report_code": 報告代碼,
                    "report_start_at": 排序時間,
                    "report_start_at_iso": 毫秒轉_iso(排序時間),
                    "sort_key": [排序時間, 副本鍵值, 報告代碼],
                }
            )

    return sorted(候選列表, key=lambda 候選: tuple(候選["sort_key"]))


def 讀取既有報告狀態巡檢游標(狀態: dict[str, Any]) -> tuple[int, str, str] | None:
    巡檢狀態 = 狀態.get(既有報告狀態巡檢狀態鍵)
    if not isinstance(巡檢狀態, dict):
        return None

    原始游標 = 巡檢狀態.get("last_sort_key")
    if not isinstance(原始游標, list) or len(原始游標) != 3:
        return None

    時間 = 轉_float(原始游標[0])
    副本鍵值 = 原始游標[1]
    報告代碼 = 原始游標[2]
    if 時間 is None or not isinstance(副本鍵值, str) or not isinstance(報告代碼, str):
        return None
    return (int(時間), 副本鍵值, 報告代碼)


def 選取既有報告狀態巡檢批次(
    候選列表: list[dict[str, Any]],
    狀態: dict[str, Any],
    上限: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if 上限 <= 0 or not 候選列表:
        return [], {"candidate_reports": len(候選列表), "wrapped": False}

    游標 = 讀取既有報告狀態巡檢游標(狀態)
    起始索引 = 0
    if 游標 is not None:
        for 索引, 候選 in enumerate(候選列表):
            if tuple(候選["sort_key"]) > 游標:
                起始索引 = 索引
                break
        else:
            起始索引 = 0

    最大選取數 = min(上限, len(候選列表))
    選取列表: list[dict[str, Any]] = []
    for 偏移 in range(最大選取數):
        選取列表.append(候選列表[(起始索引 + 偏移) % len(候選列表)])

    最後索引 = (起始索引 + len(選取列表) - 1) % len(候選列表) if 選取列表 else None
    已繞回 = bool(選取列表) and 起始索引 + len(選取列表) > len(候選列表)
    return 選取列表, {
        "candidate_reports": len(候選列表),
        "start_index": 起始索引,
        "last_index": 最後索引,
        "wrapped": 已繞回,
        "previous_cursor": list(游標) if 游標 is not None else None,
    }


def 更新既有報告狀態巡檢狀態(
    狀態: dict[str, Any],
    統計: dict[str, Any],
    最後排序鍵: list[Any] | None,
) -> None:
    巡檢狀態 = 狀態.setdefault(既有報告狀態巡檢狀態鍵, {})
    if not isinstance(巡檢狀態, dict):
        巡檢狀態 = {}
        狀態[既有報告狀態巡檢狀態鍵] = 巡檢狀態

    現在時間戳記 = 現在毫秒()
    巡檢狀態.update(
        {
            "enabled": 統計.get("enabled"),
            "limit": 統計.get("limit"),
            "candidate_reports": 統計.get("candidate_reports"),
            "last_checked_at": 現在時間戳記,
            "last_checked_at_iso": 毫秒轉_iso(現在時間戳記),
            "last_selected_reports": 統計.get("selected_reports", 0),
            "last_checked_reports": 統計.get("checked_reports", 0),
            "last_unique_codes_checked": 統計.get("unique_codes_checked", 0),
            "last_inaccessible_reports": 統計.get("inaccessible_reports", 0),
            "last_unique_inaccessible_codes": 統計.get("unique_inaccessible_codes", 0),
            "last_hidden_reports_changed": 統計.get("hidden_reports_changed", 0),
            "last_failed_reports": 統計.get("failed_reports", 0),
            "last_wrapped": 統計.get("wrapped", False),
            "last_deferred": 統計.get("deferred", False),
            "last_error": 統計.get("error"),
        }
    )
    if 最後排序鍵 is not None:
        巡檢狀態["last_sort_key"] = 最後排序鍵
        巡檢狀態["last_sort_key_report_start_at"] = 最後排序鍵[0]
        巡檢狀態["last_sort_key_report_start_at_iso"] = 毫秒轉_iso(最後排序鍵[0])
        巡檢狀態["last_sort_key_encounter_key"] = 最後排序鍵[1]
        巡檢狀態["last_sort_key_report_code"] = 最後排序鍵[2]


def 建立排行榜條目(
    排行榜: dict[str, Any],
    版本範圍: str = "all",
    *,
    包含隱藏報告: bool = False,
) -> list[dict[str, Any]]:
    # ranking_entries 是給前端快速讀取的扁平索引；reports/fights/players 才是可追溯歷史。
    # 重建時會同時讀兩種來源，確保舊資料、分片資料與新資料都能用同一套去重規則整理。
    精確成績索引: dict[str, dict[str, Any]] = {}
    最佳成績索引: dict[str, dict[str, Any]] = {}
    版本設定 = 取得副本版本截止設定(排行榜.get("encounter"))

    報告索引 = 排行榜.get("reports") if isinstance(排行榜.get("reports"), dict) else {}
    if not 報告索引:
        for 條目 in 排行榜.get("ranking_entries") or []:
            if not 包含隱藏報告 and isinstance(條目, dict) and 條目.get("report_hidden"):
                continue
            if isinstance(條目, dict):
                登記排行榜條目(條目, 精確成績索引)

    for 報告代碼, 報告 in 報告索引.items():
        if not isinstance(報告, dict):
            continue
        if 報告已標記隱藏(報告) and not 包含隱藏報告:
            continue

        報告隱藏 = 報告已標記隱藏(報告)

        for 戰鬥 in 報告.get("fights") or []:
            if not isinstance(戰鬥, dict):
                continue

            戰鬥簽章 = 建立戰鬥簽章(戰鬥)
            戰鬥["fight_hash"] = 戰鬥簽章

            for 玩家 in 戰鬥.get("players") or []:
                if not isinstance(玩家, dict):
                    continue

                名稱 = 玩家.get("name")
                伺服器 = 玩家.get("server")
                職業 = 玩家.get("job")
                dps = 玩家.get("dps")
                if not 名稱 or 伺服器 not in 繁中服伺服器名稱 or 職業 not in 有效職業名稱 or dps is None:
                    continue

                角色鍵值 = f"{名稱}@{伺服器}:{職業}"
                精確成績鍵值 = 建立_sha256(
                    {
                        "fight_hash": 戰鬥簽章,
                        "character": 角色鍵值,
                        "active_time_ms": 玩家.get("active_time_ms"),
                        "rdps": 玩家.get("rdps"),
                        "adps": 玩家.get("adps"),
                        "dps": dps,
                        "total_damage": 玩家.get("total_damage"),
                        "damage_time_ms": 戰鬥.get("damage_time_ms"),
                    }
                )
                成績 = {
                    "id": 精確成績鍵值,
                    "character_key": 角色鍵值,
                    "character_name": 名稱,
                    "server": 伺服器,
                    "job": 職業,
                    "dps": dps,
                    "rdps": 玩家.get("rdps"),
                    "adps": 玩家.get("adps"),
                    "ndps": 玩家.get("ndps"),
                    "total_damage": 玩家.get("total_damage"),
                    "active_time_ms": 玩家.get("active_time_ms"),
                    # FFLogs Damage Done 表格的 Active% 以 totalTime 為分母，包含 pull 起訖的完整時間窗；
                    # clear_time_ms/combatTime 會扣掉 FFLogs 認定的非戰鬥邊界，拿來算 DPS 分母是對的，
                    # 但拿來算 Active% 會和 FFLogs CSV 顯示略有落差。
                    "active_percent": 計算_active_percent(
                        玩家.get("active_time_ms"),
                        戰鬥.get("fflogs_total_time_ms") or 戰鬥.get("clear_time_ms"),
                    ),
                    "clear_time_ms": 戰鬥.get("clear_time_ms"),
                    "clear_time_seconds": 戰鬥.get("clear_time_seconds"),
                    "damage_downtime_ms": 戰鬥.get("damage_downtime_ms"),
                    "damage_downtime_seconds": 戰鬥.get("damage_downtime_seconds"),
                    "damage_time_ms": 戰鬥.get("damage_time_ms"),
                    "damage_time_seconds": 戰鬥.get("damage_time_seconds"),
                    "recorded_at": 戰鬥.get("recorded_at"),
                    "recorded_at_iso": 戰鬥.get("recorded_at_iso"),
                    "report_code": 報告代碼,
                    "report_url": 報告.get("url"),
                    "report_title": 報告.get("title"),
                    "fight_id": 戰鬥.get("fight_id"),
                    # xivanalysis 的精準玩家頁需要 FFLogs 在該 report/fight 內的 sourceID。
                    # 這個 ID 只用來組外部工具深連結，仍以角色名稱、伺服器與職業作為排行榜身分主鍵。
                    "fflogs_source_id": 玩家.get("fflogs_id"),
                    "fight_hash": 戰鬥簽章,
                    "source_reports": [報告代碼],
                    "duplicate_count": 1,
                }
                if 報告隱藏:
                    成績["report_hidden"] = True
                    成績["hidden_reason"] = 報告.get("hidden_reason")
                    成績["hidden_detected_at_iso"] = 報告.get("hidden_detected_at_iso")
                    成績["hidden_source"] = 報告.get("hidden_source")
                if "gcd_coverage" in 玩家:
                    # GCD 覆蓋率由 backfill_gcd_coverage.py 依 Casts graph 後補。
                    # key 不存在代表尚未嘗試；值為 null 代表已嘗試但 report 無法存取。
                    成績["gcd_coverage"] = 玩家.get("gcd_coverage")
                if "gcd_coverage_status" in 玩家:
                    成績["gcd_coverage_status"] = 玩家.get("gcd_coverage_status")
                登記排行榜條目(成績, 精確成績索引)

    for 成績 in 精確成績索引.values():
        標記成績版本狀態(成績, 版本設定)
        if not 成績符合版本範圍(成績, 版本範圍, 版本設定):
            continue

        角色鍵值 = 成績["character_key"]
        if 成績是否優先(成績, 最佳成績索引.get(角色鍵值)):
            最佳成績索引[角色鍵值] = 成績

    排行榜條目 = sorted(
        最佳成績索引.values(),
        key=lambda 成績: (成績.get("rdps") or 成績.get("dps") or 0, 成績.get("adps") or 0),
        reverse=True,
    )
    for 排名, 成績 in enumerate(排行榜條目, start=1):
        成績["rank"] = 排名
    return 排行榜條目


def 建立公開排行榜條目(條目: dict[str, Any]) -> dict[str, Any]:
    return {欄位: 條目.get(欄位) for 欄位 in 公開排行榜條目欄位 if 欄位 in 條目}


def 建立版本排行榜條目(
    排行榜: dict[str, Any],
    *,
    包含隱藏報告: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    版本設定 = 取得副本版本截止設定(排行榜.get("encounter"))
    if not 版本設定:
        return {}

    return {
        版本範圍: [
            建立公開排行榜條目(條目)
            for 條目 in 建立排行榜條目(排行榜, 版本範圍, 包含隱藏報告=包含隱藏報告)
            if isinstance(條目, dict)
        ]
        for 版本範圍 in 版本紀錄範圍清單
    }


def 建立公開排行榜(排行榜: dict[str, Any], *, 包含隱藏報告: bool = False) -> dict[str, Any]:
    排行榜條目 = 建立排行榜條目(排行榜, 包含隱藏報告=包含隱藏報告)
    版本設定 = 取得副本版本截止設定(排行榜.get("encounter"))
    公開排行榜 = {
        "schema_version": 排行榜.get("schema_version", 1),
        "encounter": 排行榜.get("encounter"),
        "updated_at": 排行榜.get("updated_at"),
        "updated_at_iso": 排行榜.get("updated_at_iso"),
        "hidden_reports_included": 包含隱藏報告,
        "ranking_entries": [
            建立公開排行榜條目(條目)
            for 條目 in 排行榜條目
            if isinstance(條目, dict)
        ],
    }

    if 版本設定:
        公開排行榜["version_cutoff"] = 版本設定
        公開排行榜["version_ranking_entries"] = 建立版本排行榜條目(
            排行榜,
            包含隱藏報告=包含隱藏報告,
        )

    return 公開排行榜


排行榜報告分片目標大小 = 45 * 1024 * 1024


def 建立排行榜基礎儲存內容(副本設定: dict[str, Any], 排行榜: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 排行榜.get("schema_version", 1),
        "encounter": 排行榜.get("encounter") or 建立副本摘要(副本設定),
        "updated_at": 排行榜.get("updated_at"),
        "updated_at_iso": 排行榜.get("updated_at_iso"),
        "ranking_entries": 建立排行榜條目(排行榜),
    }


def 讀取排行榜報告分片(排行榜: dict[str, Any]) -> dict[str, Any]:
    報告索引: dict[str, Any] = {}
    分片清單 = 排行榜.get("report_shards")
    if not isinstance(分片清單, list):
        return 報告索引

    for 分片路徑文字 in 分片清單:
        if not isinstance(分片路徑文字, str) or not 分片路徑文字:
            continue

        分片路徑 = 專案根目錄 / 分片路徑文字
        確認路徑在目錄內(專案根目錄 / "data" / "rankings", 分片路徑)
        分片內容 = 讀取_json(分片路徑, {})
        if isinstance(分片內容, dict):
            報告索引.update(分片內容)

    return 報告索引


def 讀取排行榜檔案(副本設定: dict[str, Any]) -> dict[str, Any]:
    排行榜 = 正規化排行榜(讀取_json(排行榜檔案路徑(副本設定), {}), 副本設定)
    if isinstance(排行榜.get("reports"), dict):
        return 排行榜

    分片報告索引 = 讀取排行榜報告分片(排行榜)
    if 分片報告索引:
        排行榜["reports"] = 分片報告索引
    return 排行榜


def 清除舊排行榜報告分片(副本設定: dict[str, Any]) -> None:
    分片目錄 = 排行榜報告分片目錄路徑(副本設定)
    確認路徑在目錄內(專案根目錄 / "data" / "rankings", 分片目錄)
    if not 分片目錄.exists():
        return

    for 舊分片 in 分片目錄.glob("*.json"):
        確認路徑在目錄內(分片目錄, 舊分片)
        舊分片.unlink()

    try:
        分片目錄.rmdir()
    except OSError:
        pass


def 寫入排行榜報告分片(副本設定: dict[str, Any], 報告索引: dict[str, Any]) -> list[str]:
    # 完整 report 內容可能很大，分片目標壓在 GitHub 100 MB 檔案限制以下。
    # 主檔保留 ranking_entries 與 report_shards，讀取時再透過 讀取排行榜檔案() 合併。
    清除舊排行榜報告分片(副本設定)
    if not 報告索引:
        return []

    分片目錄 = 排行榜報告分片目錄路徑(副本設定)
    確認路徑在目錄內(專案根目錄 / "data" / "rankings", 分片目錄)
    分片目錄.mkdir(parents=True, exist_ok=True)

    分片路徑清單: list[str] = []
    目前分片: dict[str, Any] = {}
    目前大小 = 2
    分片序號 = 0

    def 寫出目前分片() -> None:
        nonlocal 分片序號, 目前分片, 目前大小
        if not 目前分片:
            return

        分片路徑 = 分片目錄 / f"{分片序號:03d}.json"
        寫入_json(分片路徑, 目前分片, 緊湊格式=True)
        分片路徑清單.append(專案相對路徑(分片路徑))
        分片序號 += 1
        目前分片 = {}
        目前大小 = 2

    for 原始報告代碼, 報告 in sorted(報告索引.items(), key=lambda 項目: str(項目[0])):
        報告代碼 = str(原始報告代碼)
        if not isinstance(報告, dict):
            continue

        報告文字 = json.dumps(報告, ensure_ascii=False, separators=(",", ":"))
        項目大小 = (
            len(json.dumps(報告代碼, ensure_ascii=False).encode("utf-8"))
            + 1
            + len(報告文字.encode("utf-8"))
            + 1
        )
        if 目前分片 and 目前大小 + 項目大小 > 排行榜報告分片目標大小:
            寫出目前分片()

        目前分片[報告代碼] = 報告
        目前大小 += 項目大小

    寫出目前分片()
    return 分片路徑清單


def 建立戰鬥時間範圍索引(戰鬥列表: list[dict[str, Any]]) -> dict[int, dict[str, int | float]]:
    時間範圍索引: dict[int, dict[str, int | float]] = {}
    for 戰鬥 in 戰鬥列表:
        if not isinstance(戰鬥, dict):
            continue

        戰鬥_id = 戰鬥.get("id")
        戰鬥開始時間 = 轉_float(戰鬥.get("startTime"))
        戰鬥結束時間 = 轉_float(戰鬥.get("endTime"))
        if type(戰鬥_id) is int and 戰鬥開始時間 is not None and 戰鬥結束時間 is not None:
            時間範圍索引[戰鬥_id] = {
                "start_time": 戰鬥開始時間,
                "end_time": 戰鬥結束時間,
            }

    return 時間範圍索引


def 傷害表格疑似未完整匯出(
    戰鬥時間毫秒: float | None,
    傷害時間資訊: dict[str, Any],
    玩家列表: list[dict[str, Any]],
) -> bool:
    if 戰鬥時間毫秒 is None or 戰鬥時間毫秒 <= 0:
        return False

    傷害時間毫秒 = 轉_float(傷害時間資訊.get("damage_time_ms"))
    if 傷害時間毫秒 is None or 傷害時間毫秒 <= 0:
        return False

    傷害時間比例 = 傷害時間毫秒 / 戰鬥時間毫秒
    玩家活躍比例 = [
        活躍時間 / 戰鬥時間毫秒
        for 玩家 in 玩家列表
        if (活躍時間 := 轉_float(玩家.get("active_time_ms"))) is not None
    ]
    最高活躍比例 = max(玩家活躍比例, default=1)
    return 傷害時間比例 < 0.25 and 最高活躍比例 < 0.5


def 建立尚未完整匯出錯誤(報告代碼: str, 報告: dict[str, Any], 戰鬥: dict[str, Any]) -> FFLogs報告尚未完整匯出錯誤:
    報告起始時間戳記 = 轉_float(報告.get("startTime"))
    報告結束時間戳記 = 轉_float(報告.get("endTime"))
    戰鬥結束時間 = 轉_float(戰鬥.get("endTime"))
    戰鬥_id = 戰鬥.get("id")
    if (
        報告起始時間戳記 is None
        or 報告結束時間戳記 is None
        or 戰鬥結束時間 is None
        or type(戰鬥_id) is not int
    ):
        return FFLogs報告尚未完整匯出錯誤(報告代碼, int(戰鬥_id or 0), 0, 0)

    戰鬥結束時間戳記 = int(報告起始時間戳記 + 戰鬥結束時間)
    return FFLogs報告尚未完整匯出錯誤(
        報告代碼,
        戰鬥_id,
        int(報告結束時間戳記),
        戰鬥結束時間戳記,
    )


def 建立報告成績(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    淺層報告: dict[str, Any],
    繁中服玩家: list[dict[str, Any]],
    gcd計算器: 即時GCD覆蓋率計算器 | None = None,
) -> dict[str, Any] | None:
    # 一份 report 可能含同 zone 多個 encounter；這裡保存完成排名建置所需的 report/fight/player 脈絡。
    # GraphQL 原始表格可從 FFLogs 依 report code 重查，若全部落地會讓 repo 以 GB 級成長。
    # 因此只保留已計算出的玩家列、傷害時間分母與追溯用 report code，不保存 fflogs_raw/masterData。
    報告代碼 = 淺層報告["code"]
    報告 = 查詢通關戰鬥(session, 認證池, 副本設定, 報告代碼)
    if not 報告:
        return None

    戰鬥列表 = 報告.get("fights") or []
    if not 戰鬥列表:
        return None

    整理後戰鬥列表: list[dict[str, Any]] = []
    報告起始時間戳記 = 報告.get("startTime") or 淺層報告.get("startTime")
    戰鬥_id清單 = [戰鬥.get("id") for 戰鬥 in 戰鬥列表 if type(戰鬥.get("id")) is int]
    戰鬥時間範圍索引 = 建立戰鬥時間範圍索引(戰鬥列表)
    玩家成績索引 = 查詢多場玩家成績(session, 認證池, 副本設定, 報告代碼, 戰鬥_id清單, 戰鬥時間範圍索引)
    for 戰鬥 in 戰鬥列表:
        戰鬥_id = 戰鬥.get("id")
        if type(戰鬥_id) is not int:
            continue

        戰鬥時間毫秒 = 轉_float(戰鬥.get("combatTime"))
        if 戰鬥時間毫秒 is None:
            戰鬥開始 = 轉_float(戰鬥.get("startTime"))
            戰鬥結束 = 轉_float(戰鬥.get("endTime"))
            if 戰鬥開始 is not None and 戰鬥結束 is not None:
                戰鬥時間毫秒 = 戰鬥結束 - 戰鬥開始

        原始成績 = 玩家成績索引.get(
            戰鬥_id,
            {"player_details": None, "damage_done": None, "rankings": None},
        )
        傷害時間資訊 = 計算傷害時間資訊(原始成績, 戰鬥時間毫秒)
        傷害計算時間毫秒 = 轉_float(傷害時間資訊.get("damage_time_ms")) or 戰鬥時間毫秒
        紀錄時間戳記 = 相對戰鬥時間轉實際時間(報告起始時間戳記, 戰鬥.get("startTime"))
        玩家列表 = 從原始成績整理玩家_dps(原始成績, 傷害計算時間毫秒)
        if 傷害表格疑似未完整匯出(戰鬥時間毫秒, 傷害時間資訊, 玩家列表):
            raise 建立尚未完整匯出錯誤(報告代碼, 報告, 戰鬥)

        整理後戰鬥 = {
            "fight_id": 戰鬥_id,
            "encounter_id": 戰鬥.get("encounterID"),
            "original_encounter_id": 戰鬥.get("originalEncounterID"),
            "name": 戰鬥.get("name"),
            "difficulty": 戰鬥.get("difficulty"),
            "kill": 戰鬥.get("kill"),
            "complete_raid": 戰鬥.get("completeRaid"),
            "in_progress": 戰鬥.get("inProgress"),
            "has_echo": 戰鬥.get("hasEcho"),
            "last_phase": 戰鬥.get("lastPhase"),
            "last_phase_as_absolute_index": 戰鬥.get("lastPhaseAsAbsoluteIndex"),
            "last_phase_is_intermission": 戰鬥.get("lastPhaseIsIntermission"),
            "size": 戰鬥.get("size"),
            "standard_composition": 戰鬥.get("standardComposition"),
            "wipe_called_time": 戰鬥.get("wipeCalledTime"),
            "friendly_players": 戰鬥.get("friendlyPlayers"),
            "enemy_players": 戰鬥.get("enemyPlayers"),
            "start_time": 戰鬥.get("startTime"),
            "start_time_iso": 毫秒轉_iso(戰鬥.get("startTime")),
            "end_time": 戰鬥.get("endTime"),
            "end_time_iso": 毫秒轉_iso(戰鬥.get("endTime")),
            "recorded_at": 紀錄時間戳記,
            "recorded_at_iso": 毫秒轉_iso(紀錄時間戳記),
            "clear_time_ms": int(戰鬥時間毫秒) if 戰鬥時間毫秒 is not None else None,
            "clear_time_seconds": round(戰鬥時間毫秒 / 1000, 3) if 戰鬥時間毫秒 is not None else None,
            "fflogs_total_time_ms": 傷害時間資訊.get("fflogs_total_time_ms"),
            "fflogs_total_time_seconds": 毫秒轉秒數(傷害時間資訊.get("fflogs_total_time_ms")),
            "fflogs_combat_time_ms": 傷害時間資訊.get("fflogs_combat_time_ms"),
            "fflogs_combat_time_seconds": 毫秒轉秒數(傷害時間資訊.get("fflogs_combat_time_ms")),
            "damage_downtime_ms": 傷害時間資訊.get("damage_downtime_ms"),
            "damage_downtime_seconds": 毫秒轉秒數(傷害時間資訊.get("damage_downtime_ms")),
            "damage_time_ms": 傷害時間資訊.get("damage_time_ms"),
            "damage_time_seconds": 毫秒轉秒數(傷害時間資訊.get("damage_time_ms")),
            "fight_percentage": 戰鬥.get("fightPercentage"),
            "average_item_level": 戰鬥.get("averageItemLevel"),
            "boss_percentage": 戰鬥.get("bossPercentage"),
            "damage_done_summary": 建立傷害表格摘要(原始成績),
            "players": 玩家列表,
        }
        if gcd計算器 is not None:
            gcd計算器.補齊戰鬥玩家GCD覆蓋率(session, 認證池, 報告代碼, 整理後戰鬥, 玩家列表)

        整理後戰鬥列表.append(整理後戰鬥)

    if not 整理後戰鬥列表:
        return None

    區域 = 報告.get("region") or 淺層報告.get("region") or {}
    return {
        "report_code": 報告代碼,
        "title": 報告.get("title") or 淺層報告.get("title"),
        "url": f"https://www.fflogs.com/reports/{報告代碼}",
        "revision": 報告.get("revision"),
        "segments": 報告.get("segments"),
        "exported_segments": 報告.get("exportedSegments"),
        "visibility": 報告.get("visibility"),
        "archive_status": 報告.get("archiveStatus"),
        "region": {
            "id": 區域.get("id"),
            "name": 區域.get("name"),
            "compact_name": 區域.get("compactName"),
            "slug": 區域.get("slug"),
        },
        "zone": 報告.get("zone"),
        "guild": 報告.get("guild"),
        "guild_tag": 報告.get("guildTag"),
        "owner": 報告.get("owner"),
        "ranked_characters": 報告.get("rankedCharacters"),
        "phases": 報告.get("phases"),
        "report_start_time": 報告起始時間戳記,
        "report_start_time_iso": 毫秒轉_iso(報告起始時間戳記),
        "report_end_time": 報告.get("endTime") or 淺層報告.get("endTime"),
        "report_end_time_iso": 毫秒轉_iso(報告.get("endTime") or 淺層報告.get("endTime")),
        "matched_traditional_chinese_servers": sorted(
            {玩家.get("server") for 玩家 in 繁中服玩家 if 玩家.get("server")}
        ),
        "fights": 整理後戰鬥列表,
        "fetched_at": 現在毫秒(),
        "fetched_at_iso": 毫秒轉_iso(現在毫秒()),
    }


def 建立副本摘要(副本設定: dict[str, Any]) -> dict[str, Any]:
    副本摘要 = {
        "key": 副本設定["key"],
        "name": 副本設定["name"],
        "category": 副本設定.get("category"),
        "zone_id": 副本設定["zone_id"],
        "encounter_id": 副本設定["encounter_id"],
        "difficulty": 副本設定["difficulty"],
    }
    if isinstance(副本設定.get("version_cutoff"), dict):
        副本摘要["version_cutoff"] = 副本設定["version_cutoff"]
    return 副本摘要


def 正規化排行榜(原始內容: Any, 副本設定: dict[str, Any]) -> dict[str, Any]:
    if isinstance(原始內容, dict):
        if isinstance(原始內容.get("reports"), dict) or isinstance(原始內容.get("ranking_entries"), list):
            排行榜 = dict(原始內容)
            排行榜.setdefault("schema_version", 1)
            既有副本摘要 = 排行榜.get("encounter") if isinstance(排行榜.get("encounter"), dict) else {}
            排行榜["encounter"] = {**既有副本摘要, **建立副本摘要(副本設定)}
            return 排行榜

    報告索引: dict[str, Any] = {}
    if isinstance(原始內容, list):
        for 報告 in 原始內容:
            if isinstance(報告, dict):
                代碼 = 報告.get("report_code") or 報告.get("code")
                if 代碼:
                    報告索引[str(代碼)] = 報告

    return {
        "schema_version": 1,
        "encounter": 建立副本摘要(副本設定),
        "reports": 報告索引,
        "updated_at": None,
        "updated_at_iso": None,
    }


def 套用成績到排行榜(排行榜: dict[str, Any], 新成績列表: list[dict[str, Any]]) -> int:
    報告索引 = 排行榜.setdefault("reports", {})

    新增或更新數量 = 0
    for 成績 in 新成績列表:
        報告代碼 = 成績.get("report_code")
        if not 報告代碼:
            continue
        if 報告索引.get(報告代碼) != 成績:
            新增或更新數量 += 1
        報告索引[報告代碼] = 成績

    return 新增或更新數量


def 寫入排行榜檔案(副本設定: dict[str, Any], 排行榜: dict[str, Any]) -> None:
    排行榜["schema_version"] = 1
    排行榜["encounter"] = 建立副本摘要(副本設定)
    排行榜["updated_at"] = 現在毫秒()
    排行榜["updated_at_iso"] = 毫秒轉_iso(排行榜["updated_at"])
    儲存內容 = 建立排行榜基礎儲存內容(副本設定, 排行榜)
    報告索引 = 排行榜.get("reports") if isinstance(排行榜.get("reports"), dict) else {}
    分片路徑清單 = 寫入排行榜報告分片(副本設定, 報告索引)
    if 分片路徑清單:
        儲存內容["report_shards"] = 分片路徑清單
    else:
        儲存內容["reports"] = {}

    寫入_json(排行榜檔案路徑(副本設定), 儲存內容, 緊湊格式=True)
    寫入_json(排行榜檔案路徑(副本設定, public=True), 建立公開排行榜(排行榜), 緊湊格式=True)
    寫入_json(
        排行榜檔案路徑(副本設定, public=True, 包含隱藏公開資料=True),
        建立公開排行榜(排行榜, 包含隱藏報告=True),
        緊湊格式=True,
    )


def 重建公開排行榜檔案() -> None:
    # rebuild-public 不呼叫 FFLogs API，只把 data/rankings 的既有歷史資料轉成前端可讀的 public/data。
    # 因此這裡不能只看 enabled=true：停掃的副本若仍有歷史排行榜，也必須同步重建公開檔案，
    # 否則 public/data/encounters.json 會列出副本，但前端讀不到對應 data/rankings/{key}.json。
    全部副本清單 = 讀取全部有效副本設定清單()
    啟用副本清單 = [副本 for 副本 in 全部副本清單 if 副本.get("enabled")]
    啟用鍵值 = {副本["key"] for 副本 in 啟用副本清單}
    寫入公開副本清單(啟用副本清單)

    for 副本設定 in 全部副本清單:
        已有排行榜檔案 = 排行榜檔案路徑(副本設定).exists() or 排行榜檔案路徑(副本設定, public=True).exists()
        if 副本設定["key"] not in 啟用鍵值 and not 已有排行榜檔案:
            continue

        排行榜 = 讀取排行榜檔案(副本設定)
        排行榜.setdefault("schema_version", 1)
        排行榜.setdefault("encounter", 建立副本摘要(副本設定))
        寫入_json(排行榜檔案路徑(副本設定, public=True), 建立公開排行榜(排行榜), 緊湊格式=True)
        寫入_json(
            排行榜檔案路徑(副本設定, public=True, 包含隱藏公開資料=True),
            建立公開排行榜(排行榜, 包含隱藏報告=True),
            緊湊格式=True,
        )
        print(f"已重建公開排行榜：{副本設定['key']}")


def 分割排行榜儲存檔案() -> None:
    啟用副本清單 = 讀取副本設定清單()
    寫入公開副本清單(啟用副本清單)

    for 副本設定 in 讀取全部有效副本設定清單():
        路徑 = 排行榜檔案路徑(副本設定)
        if not 路徑.exists():
            continue

        排行榜 = 讀取排行榜檔案(副本設定)
        排行榜.setdefault("schema_version", 1)
        排行榜.setdefault("encounter", 建立副本摘要(副本設定))
        儲存內容 = 建立排行榜基礎儲存內容(副本設定, 排行榜)
        報告索引 = 排行榜.get("reports") if isinstance(排行榜.get("reports"), dict) else {}
        分片路徑清單 = 寫入排行榜報告分片(副本設定, 報告索引)
        if 分片路徑清單:
            儲存內容["report_shards"] = 分片路徑清單
        else:
            儲存內容["reports"] = {}
        寫入_json(路徑, 儲存內容, 緊湊格式=True)
        寫入_json(排行榜檔案路徑(副本設定, public=True), 建立公開排行榜(排行榜), 緊湊格式=True)
        寫入_json(
            排行榜檔案路徑(副本設定, public=True, 包含隱藏公開資料=True),
            建立公開排行榜(排行榜, 包含隱藏報告=True),
            緊湊格式=True,
        )
        print(f"已分割完整排行榜儲存檔案：{副本設定['key']}")


def 合併寫入排行榜(副本設定: dict[str, Any], 新成績列表: list[dict[str, Any]]) -> int:
    排行榜 = 讀取排行榜檔案(副本設定)
    新增或更新數量 = 套用成績到排行榜(排行榜, 新成績列表)
    寫入排行榜檔案(副本設定, 排行榜)
    return 新增或更新數量


def 報告處理記錄可重試(記錄: Any) -> bool:
    if not isinstance(記錄, dict):
        return False

    處理狀態 = 記錄.get("status")
    if 處理狀態 in 可重試報告處理狀態:
        return True

    if 處理狀態 != 無通關報告狀態 or 無通關報告重試毫秒 <= 0:
        return False

    處理時間戳記 = 轉_int_or_none(記錄.get("processed_at"))
    if 處理時間戳記 is None:
        return False

    # FFLogs report 可能在上傳過程中先出現在 reports 清單，實際通關 fight 則稍後才匯出完成。
    # `skipped_no_clear` 因此不能立刻成為永久快取；只在近期重試窗內放行深層查詢，
    # 讓 workflow 能補抓 HtgYr71cqz3K2LwC 這類「先被掃到、後來才有 kill」的紀錄。
    return 處理時間戳記 + 無通關報告重試毫秒 >= 現在毫秒()


def 讀取已處理報告代碼(
    狀態: dict[str, Any],
    副本設定: dict[str, Any],
    *,
    可重試報告視為未處理: bool = True,
) -> set[str]:
    副本鍵值 = 副本設定["key"]
    已處理 = set()

    副本狀態 = (狀態.get("encounters") or {}).get(副本鍵值) or {}
    已處理報告 = 副本狀態.get("processed_reports") or {}
    if isinstance(已處理報告, dict):
        已處理.update(
            str(代碼)
            for 代碼, 記錄 in 已處理報告.items()
            if not (可重試報告視為未處理 and 報告處理記錄可重試(記錄))
        )

    已檢查報告 = 副本狀態.get("checked_reports") or {}
    if isinstance(已檢查報告, dict):
        已處理.update(
            str(代碼)
            for 代碼, 記錄 in 已檢查報告.items()
            if not (可重試報告視為未處理 and 報告處理記錄可重試(記錄))
        )

    排行榜 = 讀取排行榜檔案(副本設定)
    報告索引 = 排行榜.get("reports") if isinstance(排行榜, dict) else {}
    if isinstance(報告索引, dict):
        已處理.update(str(代碼) for 代碼 in 報告索引.keys())

    return 已處理


def 清理報告檢查快取(副本狀態: dict[str, Any]) -> None:
    if 報告檢查快取上限 <= 0:
        return

    已檢查報告 = 副本狀態.get("checked_reports")
    if not isinstance(已檢查報告, dict) or len(已檢查報告) <= 報告檢查快取上限:
        return

    排序後項目 = sorted(
        已檢查報告.items(),
        key=lambda 項目: (項目[1] or {}).get("processed_at", 0) if isinstance(項目[1], dict) else 0,
        reverse=True,
    )
    副本狀態["checked_reports"] = dict(排序後項目[:報告檢查快取上限])


def 套用延遲掃描執行狀態(
    狀態: dict[str, Any],
    副本設定: dict[str, Any],
    處理狀態: dict[str, Any],
) -> None:
    延遲掃描狀態 = 處理狀態.get("delayed_scan")
    if not isinstance(延遲掃描狀態, dict):
        return

    副本狀態索引 = 狀態.setdefault("encounters", {})
    副本狀態 = 副本狀態索引.setdefault(副本設定["key"], {})
    現在時間戳記 = 現在毫秒()
    視窗 = 延遲掃描狀態.get("window") if isinstance(延遲掃描狀態.get("window"), dict) else {}

    副本狀態["delayed_scan_enabled"] = bool(延遲掃描狀態.get("enabled"))
    副本狀態["delayed_scan_recent_gap_hours"] = 延遲掃描狀態.get("recent_gap_hours")
    副本狀態["delayed_scan_lookback_hours"] = 延遲掃描狀態.get("lookback_hours")
    副本狀態["delayed_scan_range_start_at"] = 延遲掃描狀態.get("range_start_at")
    副本狀態["delayed_scan_range_start_at_iso"] = 延遲掃描狀態.get("range_start_at_iso")
    副本狀態["delayed_scan_range_end_at"] = 延遲掃描狀態.get("range_end_at")
    副本狀態["delayed_scan_range_end_at_iso"] = 延遲掃描狀態.get("range_end_at_iso")
    副本狀態["delayed_last_checked_at"] = 現在時間戳記
    副本狀態["delayed_last_checked_at_iso"] = 毫秒轉_iso(現在時間戳記)
    副本狀態["delayed_last_window_start_at"] = 視窗.get("start_at")
    副本狀態["delayed_last_window_start_at_iso"] = 視窗.get("start_at_iso")
    副本狀態["delayed_last_window_end_at"] = 視窗.get("end_at")
    副本狀態["delayed_last_window_end_at_iso"] = 視窗.get("end_at_iso")
    副本狀態["delayed_last_reports_found"] = 延遲掃描狀態.get("reports_found", 0)
    副本狀態["delayed_last_reports_selected"] = 延遲掃描狀態.get("reports_selected", 0)
    副本狀態["delayed_last_reports_skipped_known"] = 延遲掃描狀態.get("reports_skipped_known", 0)
    副本狀態["delayed_last_reports_deferred"] = 延遲掃描狀態.get("reports_deferred", 0)


def 套用歷史補查執行狀態(
    狀態: dict[str, Any],
    副本設定: dict[str, Any],
    處理狀態: dict[str, Any],
) -> None:
    歷史補查狀態 = 處理狀態.get("history_scan")
    if not isinstance(歷史補查狀態, dict):
        return

    副本狀態索引 = 狀態.setdefault("encounters", {})
    副本狀態 = 副本狀態索引.setdefault(副本設定["key"], {})
    現在時間戳記 = 現在毫秒()
    視窗列表 = 歷史補查狀態.get("windows") if isinstance(歷史補查狀態.get("windows"), list) else []
    最後視窗 = 視窗列表[-1] if 視窗列表 and isinstance(視窗列表[-1], dict) else {}

    副本狀態["history_scan_enabled"] = bool(歷史補查狀態.get("enabled"))
    副本狀態["history_scan_range_start_at"] = 歷史補查狀態.get("range_start_at")
    副本狀態["history_scan_range_start_at_iso"] = 歷史補查狀態.get("range_start_at_iso")
    副本狀態["history_scan_range_end_at"] = 歷史補查狀態.get("range_end_at")
    副本狀態["history_scan_range_end_at_iso"] = 歷史補查狀態.get("range_end_at_iso")
    副本狀態["history_scan_cursor_at"] = 歷史補查狀態.get("next_cursor_at")
    副本狀態["history_scan_cursor_at_iso"] = 歷史補查狀態.get("next_cursor_at_iso")
    副本狀態["history_last_checked_at"] = 現在時間戳記
    副本狀態["history_last_checked_at_iso"] = 毫秒轉_iso(現在時間戳記)
    副本狀態["history_last_window_start_at"] = 最後視窗.get("start_at")
    副本狀態["history_last_window_start_at_iso"] = 最後視窗.get("start_at_iso")
    副本狀態["history_last_window_end_at"] = 最後視窗.get("end_at")
    副本狀態["history_last_window_end_at_iso"] = 最後視窗.get("end_at_iso")
    副本狀態["history_last_reports_found"] = 歷史補查狀態.get("reports_found", 0)
    副本狀態["history_last_reports_selected"] = 歷史補查狀態.get("reports_selected", 0)
    副本狀態["history_last_reports_skipped_known"] = 歷史補查狀態.get("reports_skipped_known", 0)
    副本狀態["history_last_reports_deferred"] = 歷史補查狀態.get("reports_deferred", 0)


def 標記報告處理狀態(
    狀態: dict[str, Any],
    副本設定: dict[str, Any],
    報告代碼: str,
    處理狀態: str,
    額外內容: dict[str, Any] | None = None,
    *,
    立即寫入: bool = True,
) -> None:
    副本狀態索引 = 狀態.setdefault("encounters", {})
    副本狀態 = 副本狀態索引.setdefault(副本設定["key"], {})
    已處理報告 = 副本狀態.setdefault("processed_reports", {})
    已檢查報告 = 副本狀態.setdefault("checked_reports", {})
    現在時間戳記 = 現在毫秒()

    記錄 = {
        "status": 處理狀態,
        "processed_at": 現在時間戳記,
        "processed_at_iso": 毫秒轉_iso(現在時間戳記),
    }
    if 額外內容:
        記錄.update(額外內容)

    已處理報告[報告代碼] = 記錄
    已檢查報告[報告代碼] = dict(記錄)
    副本狀態["checkpoint_updated_at"] = 現在時間戳記
    副本狀態["checkpoint_updated_at_iso"] = 毫秒轉_iso(現在時間戳記)
    if 立即寫入:
        寫入_json(狀態檔案路徑, 狀態)


def 更新狀態(
    原始狀態: dict[str, Any],
    新時間戳記: int,
    統計: dict[str, Any],
    已處理副本清單: list[dict[str, Any]],
    *,
    完整成功: bool = True,
) -> None:
    # processed_reports 是單輪 checkpoint，成功跑完整輪後會清空，避免永久膨脹。
    # checked_reports 才是跨輪的略過/已檢查快取；清理時只裁切最舊快取，不會刪 data/rankings 的歷史報告。
    # 當 FFLogs 暫時性 5xx/逾時只影響部分副本時，只推進已完成副本的掃描點；
    # 失敗副本保留原掃描點與 active_scan，避免下次排程漏掃該時間窗。
    狀態 = dict(原始狀態)
    執行結束時間戳記 = 現在毫秒()
    狀態["last_attempted_run_at"] = 執行結束時間戳記
    狀態["last_attempted_run_at_iso"] = 毫秒轉_iso(執行結束時間戳記)
    狀態["last_run_completed"] = 完整成功
    if 完整成功:
        狀態["last_scanned_at"] = 新時間戳記
        狀態["last_scanned_at_iso"] = 毫秒轉_iso(新時間戳記)
        狀態["last_successful_run_at"] = 執行結束時間戳記
        狀態["last_successful_run_at_iso"] = 毫秒轉_iso(執行結束時間戳記)
    狀態["last_run_stats"] = 統計
    副本狀態索引 = dict(狀態.get("encounters") or {})
    for 副本 in 已處理副本清單:
        副本狀態 = dict(副本狀態索引.get(副本["key"]) or {})
        副本狀態["last_scanned_at"] = 新時間戳記
        副本狀態["last_scanned_at_iso"] = 毫秒轉_iso(新時間戳記)
        副本狀態["processed_reports"] = {}
        清理報告檢查快取(副本狀態)
        副本狀態.pop("active_scan", None)
        副本狀態索引[副本["key"]] = 副本狀態
    狀態["encounters"] = 副本狀態索引
    寫入_json(狀態檔案路徑, 狀態)


def main() -> int:
    session = requests.Session()
    認證池 = FFLogs認證池(session, 讀取認證設定())
    副本清單 = 讀取副本設定清單()
    重抓報告代碼, 只處理報告代碼 = 讀取指定報告代碼()
    只處理指定報告模式 = bool(只處理報告代碼)
    寫入公開副本清單(副本清單)

    狀態 = 讀取_json(狀態檔案路徑, {})
    掃描結束時間戳記 = 現在毫秒()
    gcd計算器 = 即時GCD覆蓋率計算器()

    print(f"啟用副本：{', '.join(副本['name'] for 副本 in 副本清單)}")
    print(f"可用 FFLogs 憑證組數：{len(認證池.認證清單)}")
    if gcd計算器.啟用:
        上限文字 = str(gcd計算器.戰鬥上限) if gcd計算器.戰鬥上限 > 0 else "無上限"
        print(f"已啟用新 report 即時 GCD 覆蓋率計算，本輪 Casts graph 戰鬥上限：{上限文字}。")
    if 重抓報告代碼:
        print(f"指定重抓報告：{', '.join(sorted(重抓報告代碼))}")
    if 只處理報告代碼:
        print(f"只處理指定報告，掃描點不會往後推進：{', '.join(sorted(只處理報告代碼))}")

    副本處理狀態: dict[str, dict[str, Any]] = {}
    for 副本設定 in 副本清單:
        副本處理狀態[副本設定["key"]] = {
            "副本設定": 副本設定,
            "已處理報告代碼": 讀取已處理報告代碼(狀態, 副本設定),
            # 24-72 小時的延遲掃描只找「真正沒見過」的新 report。
            # 因此這裡保留一份不放行 retryable 狀態的嚴格集合，避免該區段重查既有 no-clear 紀錄。
            "已知報告代碼": 讀取已處理報告代碼(狀態, 副本設定, 可重試報告視為未處理=False),
            "本輪已嘗試報告代碼": set(),
            "排行榜": 讀取排行榜檔案(副本設定),
            "待寫入成績清單": [],
            "待標記已儲存報告": [],
            "scan_start_at": None,
            "scan_end_at": 掃描結束時間戳記,
            "candidate_reports": 0,
            "china_region_reports": 0,
            "recent_reports": 0,
            "delayed_reports_found": 0,
            "delayed_reports_selected": 0,
            "delayed_reports_skipped_known": 0,
            "delayed_reports_deferred": 0,
            "delayed_scan": None,
            "history_reports_found": 0,
            "history_reports_selected": 0,
            "history_reports_skipped_known": 0,
            "history_reports_deferred": 0,
            "history_scan": None,
            "scan_failed": False,
            "scan_error": None,
            "skipped_already_processed_reports": 0,
            "traditional_chinese_reports": 0,
            "reports_saved": 0,
            "reports_failed": 0,
            "rankings_inserted_or_updated": 0,
        }

    淺層掃描快取: dict[tuple[int, int, int, int | None], list[dict[str, Any]]] = {}
    本輪報告繁中服檢查快取: dict[str, dict[str, Any]] = {}
    延遲掃描候選報告代碼: set[str] = set()
    歷史補查候選報告代碼: set[str] = set()
    已完成副本清單: list[dict[str, Any]] = []
    暫時失敗副本清單: list[dict[str, Any]] = []

    def 取得同區同難度副本清單(基準副本: dict[str, Any]) -> list[dict[str, Any]]:
        # 同一份 FFLogs report 常同時包含同區同難度的多個副本。
        # 掃到任一副本時順手檢查同區副本，可減少重複淺層掃描與 API 請求。
        同區副本 = [
            副本
            for 副本 in 副本清單
            if 副本["key"] != 基準副本["key"]
            and 副本.get("zone_id") == 基準副本.get("zone_id")
            and 副本.get("difficulty") == 基準副本.get("difficulty")
        ]
        return [基準副本, *同區副本]

    def 擷取並快取淺層報告(
        副本設定: dict[str, Any],
        起始時間戳記: int,
        結束時間戳記: int,
        進度回呼: Callable[[dict[str, Any]], None] | None,
        *,
        掃描區間小時: int | None = None,
        階段名稱: str = "淺層掃描",
    ) -> list[dict[str, Any]]:
        快取鍵 = (副本設定["zone_id"], 起始時間戳記, 結束時間戳記, 掃描區間小時)
        if 快取鍵 not in 淺層掃描快取:
            淺層掃描快取[快取鍵] = 擷取最新報告(
                session,
                認證池,
                副本設定,
                起始時間戳記,
                結束時間戳記,
                進度回呼,
                掃描區間小時=掃描區間小時,
                階段名稱=階段名稱,
            )
        else:
            print(
                f"{副本設定['name']} 重用同 zone 淺層掃描結果："
                f"{毫秒轉_iso(起始時間戳記)} ~ {毫秒轉_iso(結束時間戳記)}"
            )
        return [dict(報告) for 報告 in 淺層掃描快取[快取鍵]]

    def 是否需要深層處理任何同區副本(
        目前副本設定: dict[str, Any],
        報告代碼: str,
        強制重抓: bool = False,
    ) -> bool:
        for 目標副本設定 in 取得同區同難度副本清單(目前副本設定):
            目標處理狀態 = 副本處理狀態[目標副本設定["key"]]
            if 報告代碼 in 目標處理狀態["本輪已嘗試報告代碼"]:
                continue
            if 強制重抓 or 報告代碼 not in 目標處理狀態["已處理報告代碼"]:
                return True
        return False

    def 歷史補查仍可加入候選(報告代碼: str) -> bool:
        if 報告代碼 in 歷史補查候選報告代碼:
            return True
        return 歷史補查深層報告上限 <= 0 or len(歷史補查候選報告代碼) < 歷史補查深層報告上限

    def 延遲掃描仍可加入候選(報告代碼: str) -> bool:
        if 報告代碼 in 延遲掃描候選報告代碼:
            return True
        return 延遲掃描深層報告上限 <= 0 or len(延遲掃描候選報告代碼) < 延遲掃描深層報告上限

    def 是否為任何同區副本的未知報告(目前副本設定: dict[str, Any], 報告代碼: str) -> bool:
        for 目標副本設定 in 取得同區同難度副本清單(目前副本設定):
            目標處理狀態 = 副本處理狀態[目標副本設定["key"]]
            if 報告代碼 in 目標處理狀態["本輪已嘗試報告代碼"]:
                continue
            if 報告代碼 not in 目標處理狀態["已知報告代碼"]:
                return True
        return False

    def 篩選延遲掃描候選(
        副本設定: dict[str, Any],
        報告列表: list[dict[str, Any]],
        最新報告代碼: set[str],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        候選列表: list[dict[str, Any]] = []
        統計 = {"selected": 0, "skipped_known": 0, "deferred": 0}

        for 報告 in 報告列表:
            報告代碼 = str(報告.get("code") or "")
            if not 報告代碼:
                continue
            if 報告代碼 in 最新報告代碼:
                統計["skipped_known"] += 1
                continue
            if not 是否為任何同區副本的未知報告(副本設定, 報告代碼):
                統計["skipped_known"] += 1
                continue
            if not 延遲掃描仍可加入候選(報告代碼):
                統計["deferred"] += 1
                continue

            延遲掃描候選報告代碼.add(報告代碼)
            候選列表.append(報告)
            統計["selected"] += 1

        return 候選列表, 統計

    def 篩選歷史補查候選(
        副本設定: dict[str, Any],
        報告列表: list[dict[str, Any]],
        最新報告代碼: set[str],
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        候選列表: list[dict[str, Any]] = []
        統計 = {"selected": 0, "skipped_known": 0, "deferred": 0}

        for 報告 in 報告列表:
            報告代碼 = str(報告.get("code") or "")
            if not 報告代碼:
                continue
            if 報告代碼 in 最新報告代碼:
                統計["skipped_known"] += 1
                continue
            if not 是否需要深層處理任何同區副本(副本設定, 報告代碼):
                統計["skipped_known"] += 1
                continue
            if not 歷史補查仍可加入候選(報告代碼):
                統計["deferred"] += 1
                continue

            歷史補查候選報告代碼.add(報告代碼)
            候選列表.append(報告)
            統計["selected"] += 1

        return 候選列表, 統計

    def 批次寫入排行榜(處理狀態: dict[str, Any], 原因: str) -> None:
        副本設定 = 處理狀態["副本設定"]
        待寫入成績清單 = 處理狀態["待寫入成績清單"]
        待標記已儲存報告 = 處理狀態["待標記已儲存報告"]
        if not 待寫入成績清單:
            return

        批次報告數量 = len(待寫入成績清單)
        批次新增或更新數量 = 套用成績到排行榜(處理狀態["排行榜"], 待寫入成績清單)
        寫入排行榜檔案(副本設定, 處理狀態["排行榜"])

        for 已儲存報告代碼 in 待標記已儲存報告:
            標記報告處理狀態(
                狀態,
                副本設定,
                已儲存報告代碼,
                "saved",
                {"has_clear": True},
                立即寫入=False,
            )
            處理狀態["已處理報告代碼"].add(已儲存報告代碼)
            處理狀態["已知報告代碼"].add(已儲存報告代碼)
        寫入_json(狀態檔案路徑, 狀態)

        處理狀態["rankings_inserted_or_updated"] += 批次新增或更新數量
        處理狀態["reports_saved"] += 批次報告數量
        print(
            f"{副本設定['name']} 已批次寫入 {批次報告數量} 份有效報告"
            f"（{原因}，新增或更新 {批次新增或更新數量} 筆）。"
        )
        待寫入成績清單.clear()
        待標記已儲存報告.clear()

    def 篩選待處理副本(
        目前副本設定: dict[str, Any],
        報告代碼: str,
        強制重抓: bool,
    ) -> tuple[list[dict[str, Any]], bool]:
        # 強制重抓模式只重新處理指定 report，不推進掃描點；一般模式則跳過已在 state 或排行榜中的報告。
        # 這讓手動補抓能修正單份報告，同時保護既有 append-only 資料不被整批重算覆蓋。
        待處理副本: list[dict[str, Any]] = []
        目前副本已處理 = False

        for 目標副本設定 in 取得同區同難度副本清單(目前副本設定):
            目標處理狀態 = 副本處理狀態[目標副本設定["key"]]
            if 報告代碼 in 目標處理狀態["本輪已嘗試報告代碼"]:
                continue

            if 報告代碼 in 目標處理狀態["已處理報告代碼"] and not 強制重抓:
                if 目標副本設定["key"] == 目前副本設定["key"]:
                    目前副本已處理 = True
                    目標處理狀態["skipped_already_processed_reports"] += 1
                continue

            待處理副本.append(目標副本設定)

        return 待處理副本, 目前副本已處理

    def 標記報告略過(
        處理狀態: dict[str, Any],
        報告代碼: str,
        處理狀態文字: str,
        額外內容: dict[str, Any] | None = None,
        *,
        立即寫入: bool = True,
    ) -> None:
        副本設定 = 處理狀態["副本設定"]
        標記報告處理狀態(狀態, 副本設定, 報告代碼, 處理狀態文字, 額外內容, 立即寫入=立即寫入)
        處理狀態["已處理報告代碼"].add(報告代碼)
        處理狀態["已知報告代碼"].add(報告代碼)
        處理狀態["本輪已嘗試報告代碼"].add(報告代碼)

    def 標記不可存取報告隱藏(目標副本設定: dict[str, Any], 報告代碼: str, 錯誤: Exception) -> None:
        目標處理狀態 = 副本處理狀態[目標副本設定["key"]]
        已變更 = 標記排行榜報告隱藏(
            目標處理狀態["排行榜"],
            報告代碼,
            原因=報告無法存取隱藏原因,
            來源="fetch_fflogs",
            詳細原因=str(錯誤),
        )
        if not 已變更:
            return

        寫入排行榜檔案(目標副本設定, 目標處理狀態["排行榜"])
        print(f"{目標副本設定['name']} 已將無法存取的既有 report 標記為隱藏：{報告代碼}")

    def 標記所有排行榜不可存取報告隱藏(
        報告代碼: str,
        錯誤: Exception,
        處理狀態索引: dict[str, dict[str, Any]] | None = None,
    ) -> int:
        變更數量 = 0
        for 目標處理狀態 in (處理狀態索引 or 副本處理狀態).values():
            目標副本設定 = 目標處理狀態["副本設定"]
            排行榜 = 目標處理狀態["排行榜"]
            報告索引 = 排行榜.get("reports") if isinstance(排行榜.get("reports"), dict) else {}
            報告 = 報告索引.get(報告代碼)
            if not isinstance(報告, dict) or 報告已標記隱藏(報告):
                continue

            if 標記排行榜報告隱藏(
                排行榜,
                報告代碼,
                原因=報告無法存取隱藏原因,
                來源="existing_report_status_check",
                詳細原因=str(錯誤),
            ):
                寫入排行榜檔案(目標副本設定, 排行榜)
                變更數量 += 1
                print(f"{目標副本設定['name']} 巡檢發現 report 無法存取，已標記為隱藏：{報告代碼}")

        return 變更數量

    def 執行既有報告狀態巡檢() -> dict[str, Any]:
        統計 = {
            "enabled": 既有報告狀態巡檢已啟用,
            "limit": 既有報告狀態巡檢上限,
            "candidate_reports": 0,
            "selected_reports": 0,
            "checked_reports": 0,
            "unique_codes_checked": 0,
            "inaccessible_reports": 0,
            "unique_inaccessible_codes": 0,
            "hidden_reports_changed": 0,
            "failed_reports": 0,
            "wrapped": False,
            "deferred": False,
            "error": None,
        }
        if not 既有報告狀態巡檢已啟用 or 既有報告狀態巡檢上限 <= 0:
            return 統計
        if 只處理指定報告模式:
            統計["enabled"] = False
            統計["skipped_reason"] = "manual_report_mode"
            return 統計

        巡檢副本清單 = 讀取全部有效副本設定清單()
        巡檢處理狀態索引 = {
            副本鍵值: 處理狀態
            for 副本鍵值, 處理狀態 in 副本處理狀態.items()
        }
        for 巡檢副本設定 in 巡檢副本清單:
            巡檢副本鍵值 = 巡檢副本設定["key"]
            if 巡檢副本鍵值 in 巡檢處理狀態索引:
                continue
            巡檢處理狀態索引[巡檢副本鍵值] = {
                "副本設定": 巡檢副本設定,
                "排行榜": 讀取排行榜檔案(巡檢副本設定),
            }

        排行榜索引 = {
            副本鍵值: 處理狀態["排行榜"]
            for 副本鍵值, 處理狀態 in 巡檢處理狀態索引.items()
        }
        候選列表 = 建立既有報告狀態巡檢候選(巡檢副本清單, 排行榜索引)
        選取列表, 選取狀態 = 選取既有報告狀態巡檢批次(候選列表, 狀態, 既有報告狀態巡檢上限)
        統計.update(選取狀態)
        統計["selected_reports"] = len(選取列表)
        統計["wrapped"] = 選取狀態.get("wrapped", False)
        if not 選取列表:
            更新既有報告狀態巡檢狀態(狀態, 統計, None)
            return 統計

        print(
            f"既有 report 狀態巡檢：本輪選入 {len(選取列表)}/{len(候選列表)} 筆，"
            f"由舊到新檢查，游標繞回={統計['wrapped']}。"
        )

        查詢結果快取: dict[str, Exception | None] = {}
        已查詢代碼: set[str] = set()
        不可存取代碼: set[str] = set()
        最後排序鍵: list[Any] | None = None

        for 候選 in 選取列表:
            報告代碼 = 候選["report_code"]
            if 報告代碼 not in 查詢結果快取:
                try:
                    查詢報告目前狀態(session, 認證池, 報告代碼)
                    查詢結果快取[報告代碼] = None
                except (FFLogs報告存取錯誤, FFLogs報告狀態不可存取錯誤) as 錯誤:
                    查詢結果快取[報告代碼] = 錯誤
                except FFLogs暫時性API錯誤 as 錯誤:
                    統計["deferred"] = True
                    統計["error"] = str(錯誤)
                    print(f"既有 report 狀態巡檢因 FFLogs 暫時性錯誤暫停：{錯誤}", file=sys.stderr)
                    break
                except Exception as 錯誤:
                    查詢結果快取[報告代碼] = None
                    統計["failed_reports"] += 1
                    print(f"既有 report 狀態巡檢檢查 {報告代碼} 時失敗：{錯誤}", file=sys.stderr)
                已查詢代碼.add(報告代碼)

            錯誤 = 查詢結果快取[報告代碼]
            if 錯誤 is not None:
                統計["inaccessible_reports"] += 1
                不可存取代碼.add(報告代碼)
                統計["hidden_reports_changed"] += 標記所有排行榜不可存取報告隱藏(
                    報告代碼,
                    錯誤,
                    巡檢處理狀態索引,
                )

            統計["checked_reports"] += 1
            最後排序鍵 = list(候選["sort_key"])

        統計["unique_codes_checked"] = len(已查詢代碼)
        統計["unique_inaccessible_codes"] = len(不可存取代碼)
        更新既有報告狀態巡檢狀態(狀態, 統計, 最後排序鍵)
        print(
            f"既有 report 狀態巡檢完成：檢查 {統計['checked_reports']} 筆、"
            f"{統計['unique_codes_checked']} 個 report code，"
            f"不可存取 {統計['unique_inaccessible_codes']} 個，"
            f"更新 hidden 標記 {統計['hidden_reports_changed']} 筆。"
        )
        return 統計

    def 延後副本掃描(
        副本設定: dict[str, Any],
        處理狀態: dict[str, Any],
        錯誤: FFLogs暫時性API錯誤,
    ) -> None:
        if not 處理狀態["scan_failed"]:
            暫時失敗副本清單.append(副本設定)
        處理狀態["scan_failed"] = True
        處理狀態["scan_error"] = str(錯誤)
        記錄暫時性掃描失敗(狀態, 副本設定, 錯誤)
        print(
            f"{副本設定['name']} 因 FFLogs 暫時性錯誤延後本輪掃描，"
            f"該副本掃描點維持在原位置：{錯誤}",
            file=sys.stderr,
        )

    for 副本設定 in 副本清單:
        目前處理狀態 = 副本處理狀態[副本設定["key"]]
        顯示前次未完成掃描(狀態, 副本設定)
        狀態時間戳記 = 取得狀態時間戳記(狀態, 副本設定)
        起始時間戳記 = 取得增量掃描起點(狀態時間戳記, 副本設定)
        目前處理狀態["scan_start_at"] = 起始時間戳記
        目前處理狀態["scan_end_at"] = 掃描結束時間戳記
        print(
            f"開始掃描 {副本設定['name']}："
            f"{毫秒轉_iso(起始時間戳記)} ~ {毫秒轉_iso(掃描結束時間戳記)}"
        )
        if 起始時間戳記 < 狀態時間戳記:
            print(
                f"{副本設定['name']} 增量掃描回溯 {增量掃描回溯小時} 小時，"
                f"原掃描點為 {毫秒轉_iso(狀態時間戳記)}。"
            )
        更新副本掃描進度(
            狀態,
            副本設定,
            stage="準備掃描",
            scan_start_at=起始時間戳記,
            scan_start_at_iso=毫秒轉_iso(起始時間戳記),
            scan_end_at=掃描結束時間戳記,
            scan_end_at_iso=毫秒轉_iso(掃描結束時間戳記),
        )

        if 只處理指定報告模式:
            淺層報告列表 = 補入指定報告([], 只處理報告代碼, 起始時間戳記, 掃描結束時間戳記)
            淺層報告列表 = 加入掃描來源(淺層報告列表, "manual")
            更新副本掃描進度(
                狀態,
                副本設定,
                stage="指定報告處理",
                total_reports=len(淺層報告列表),
            )
            print(f"{副本設定['name']} 指定處理 {len(淺層報告列表)} 份報告，略過淺層掃描。")
        else:
            def 記錄淺層掃描進度(進度: dict[str, Any]) -> None:
                更新副本掃描進度(
                    狀態,
                    副本設定,
                    scan_start_at=起始時間戳記,
                    scan_start_at_iso=毫秒轉_iso(起始時間戳記),
                    scan_end_at=掃描結束時間戳記,
                    scan_end_at_iso=毫秒轉_iso(掃描結束時間戳記),
                    **進度,
                )

            try:
                最新報告列表 = 擷取並快取淺層報告(
                    副本設定,
                    起始時間戳記,
                    掃描結束時間戳記,
                    記錄淺層掃描進度,
                )
            except FFLogs暫時性API錯誤 as 錯誤:
                延後副本掃描(副本設定, 目前處理狀態, 錯誤)
                continue
            最新報告列表 = 補入指定報告(最新報告列表, 重抓報告代碼, 起始時間戳記, 掃描結束時間戳記)
            最新報告列表 = 加入掃描來源(最新報告列表, "recent")
            最新報告代碼 = {str(報告.get("code")) for 報告 in 最新報告列表 if 報告.get("code")}

            延遲報告列表: list[dict[str, Any]] = []
            延遲掃描區間, 延遲掃描狀態 = 建立延遲掃描區間(副本設定, 掃描結束時間戳記)
            目前處理狀態["delayed_scan"] = 延遲掃描狀態
            延遲掃描暫停 = False

            if 延遲掃描區間:
                def 記錄延遲掃描進度(進度: dict[str, Any]) -> None:
                    更新副本掃描進度(
                        狀態,
                        副本設定,
                        scan_start_at=起始時間戳記,
                        scan_start_at_iso=毫秒轉_iso(起始時間戳記),
                        scan_end_at=掃描結束時間戳記,
                        scan_end_at_iso=毫秒轉_iso(掃描結束時間戳記),
                        **進度,
                    )

                try:
                    延遲報告列表 = 擷取並快取淺層報告(
                        副本設定,
                        延遲掃描區間["start_at"],
                        延遲掃描區間["end_at"],
                        記錄延遲掃描進度,
                        階段名稱="延遲淺層掃描",
                    )
                except FFLogs暫時性API錯誤 as 錯誤:
                    延後副本掃描(副本設定, 目前處理狀態, 錯誤)
                    延遲掃描暫停 = True

            if 延遲掃描暫停:
                continue

            延遲報告列表 = 加入掃描來源(延遲報告列表, "delayed")
            延遲報告候選列表, 延遲候選統計 = 篩選延遲掃描候選(副本設定, 延遲報告列表, 最新報告代碼)
            延遲報告代碼 = {str(報告.get("code")) for 報告 in 延遲報告列表 if 報告.get("code")}
            目前處理狀態["delayed_reports_found"] = len(延遲報告代碼)
            目前處理狀態["delayed_reports_selected"] = 延遲候選統計["selected"]
            目前處理狀態["delayed_reports_skipped_known"] = 延遲候選統計["skipped_known"]
            目前處理狀態["delayed_reports_deferred"] = 延遲候選統計["deferred"]
            if 延遲掃描狀態 is not None:
                延遲掃描狀態["reports_found"] = len(延遲報告代碼)
                延遲掃描狀態["reports_selected"] = 延遲候選統計["selected"]
                延遲掃描狀態["reports_skipped_known"] = 延遲候選統計["skipped_known"]
                延遲掃描狀態["reports_deferred"] = 延遲候選統計["deferred"]

            歷史報告列表: list[dict[str, Any]] = []
            歷史區間列表, 歷史補查狀態 = 建立歷史補查區間(狀態, 副本設定, 狀態時間戳記)
            目前處理狀態["history_scan"] = 歷史補查狀態
            歷史補查暫停 = False

            if 歷史區間列表:
                def 記錄歷史補查進度(進度: dict[str, Any]) -> None:
                    更新副本掃描進度(
                        狀態,
                        副本設定,
                        scan_start_at=起始時間戳記,
                        scan_start_at_iso=毫秒轉_iso(起始時間戳記),
                        scan_end_at=掃描結束時間戳記,
                        scan_end_at_iso=毫秒轉_iso(掃描結束時間戳記),
                        **進度,
                    )

                for 歷史區間 in 歷史區間列表:
                    try:
                        歷史報告列表.extend(
                            擷取並快取淺層報告(
                                副本設定,
                                歷史區間["start_at"],
                                歷史區間["end_at"],
                                記錄歷史補查進度,
                                掃描區間小時=歷史補查區間小時,
                                階段名稱="歷史補查淺層掃描",
                            )
                        )
                    except FFLogs暫時性API錯誤 as 錯誤:
                        延後副本掃描(副本設定, 目前處理狀態, 錯誤)
                        歷史補查暫停 = True
                        break

            if 歷史補查暫停:
                continue

            歷史報告列表 = 加入掃描來源(歷史報告列表, "history")
            近期已涵蓋報告代碼 = 最新報告代碼 | 延遲報告代碼
            歷史報告候選列表, 歷史候選統計 = 篩選歷史補查候選(副本設定, 歷史報告列表, 近期已涵蓋報告代碼)
            歷史報告代碼 = {str(報告.get("code")) for 報告 in 歷史報告列表 if 報告.get("code")}
            目前處理狀態["history_reports_found"] = len(歷史報告代碼)
            目前處理狀態["history_reports_selected"] = 歷史候選統計["selected"]
            目前處理狀態["history_reports_skipped_known"] = 歷史候選統計["skipped_known"]
            目前處理狀態["history_reports_deferred"] = 歷史候選統計["deferred"]
            if 歷史補查狀態 is not None:
                歷史補查狀態["reports_found"] = len(歷史報告代碼)
                歷史補查狀態["reports_selected"] = 歷史候選統計["selected"]
                歷史補查狀態["reports_skipped_known"] = 歷史候選統計["skipped_known"]
                歷史補查狀態["reports_deferred"] = 歷史候選統計["deferred"]
                套用歷史補查深查上限游標(歷史補查狀態, 歷史報告候選列表, 歷史候選統計)

            淺層報告列表 = 合併淺層報告列表(最新報告列表, 延遲報告候選列表 + 歷史報告候選列表)
            目前處理狀態["recent_reports"] = len(最新報告列表)
            最新中國區域候選數 = sum(1 for 報告 in 最新報告列表 if 是否中國區域報告(報告))
            中國區域說明 = (
                f"（其中中國區域 {最新中國區域候選數} 份）"
                if 掃描全部地區報告
                else ""
            )
            print(
                f"{副本設定['name']} 淺層掃描取得 "
                f"{len(最新報告列表)} 份{淺層地區範圍說明()}候選報告{中國區域說明}；"
                f"延遲掃描找到 {len(延遲報告代碼)} 份，選入 {延遲候選統計['selected']} 份"
                f"（已知略過 {延遲候選統計['skipped_known']}，延後 {延遲候選統計['deferred']}）；"
                f"歷史補查找到 {len(歷史報告代碼)} 份，選入 {歷史候選統計['selected']} 份"
                f"（已知略過 {歷史候選統計['skipped_known']}，延後 {歷史候選統計['deferred']}）。"
            )

        目前處理狀態["candidate_reports"] = len(淺層報告列表)
        目前處理狀態["china_region_reports"] = sum(
            1 for 報告 in 淺層報告列表 if 是否中國區域報告(報告)
        )
        總報告數量 = len(淺層報告列表)

        for 報告序號, 報告 in enumerate(淺層報告列表, start=1):
            報告代碼 = 報告["code"]
            進度文字 = f"({報告序號}/{總報告數量})"
            強制重抓 = 報告代碼 in 重抓報告代碼 or 報告代碼 in 只處理報告代碼
            if (
                報告序號 == 1
                or 報告序號 % 100 == 0
                or 報告代碼 not in 目前處理狀態["已處理報告代碼"]
                or 強制重抓
            ):
                更新副本掃描進度(
                    狀態,
                    副本設定,
                    stage="深層過濾與成績整理",
                    current_report_index=報告序號,
                    total_reports=總報告數量,
                    current_report_code=報告代碼,
                    current_report_start_at=報告.get("startTime"),
                    current_report_start_at_iso=毫秒轉_iso(報告.get("startTime")),
                    processed_reports_in_checkpoint=len(目前處理狀態["已處理報告代碼"]),
                )

            待處理副本, 目前副本已處理 = 篩選待處理副本(副本設定, 報告代碼, 強制重抓)
            if not 待處理副本:
                if 目前副本已處理:
                    print(f"{副本設定['name']} {進度文字} 略過已處理報告：{報告代碼}")
                continue

            if 目前副本已處理:
                print(f"{副本設定['name']} {進度文字} 略過已處理報告：{報告代碼}")
                print(f"{副本設定['name']} {進度文字} 檢查同區其他副本：{報告代碼}")
            else:
                其他副本名稱 = [
                    目標副本["name"]
                    for 目標副本 in 待處理副本
                    if 目標副本["key"] != 副本設定["key"]
                ]
                同步說明 = f"（同時檢查：{', '.join(其他副本名稱)}）" if 其他副本名稱 else ""
                print(f"{副本設定['name']} {進度文字} 處理報告：{報告代碼}{同步說明}")

            try:
                有繁中服玩家, 繁中服玩家 = 取得本輪報告繁中服檢查結果(
                    本輪報告繁中服檢查快取,
                    session,
                    認證池,
                    報告代碼,
                )
            except FFLogs報告存取錯誤 as 錯誤:
                for 目標副本 in 待處理副本:
                    標記不可存取報告隱藏(目標副本, 報告代碼, 錯誤)
                    標記報告略過(
                        副本處理狀態[目標副本["key"]],
                        報告代碼,
                        "skipped_inaccessible",
                        {"reason": str(錯誤)},
                        立即寫入=False,
                    )
                寫入_json(狀態檔案路徑, 狀態)
                print(f"{副本設定['name']} {進度文字} FFLogs 報告無法存取，已略過 {len(待處理副本)} 個副本：{報告代碼}")
                continue
            except Exception as 錯誤:
                for 目標副本 in 待處理副本:
                    目標處理狀態 = 副本處理狀態[目標副本["key"]]
                    目標處理狀態["reports_failed"] += 1
                    目標處理狀態["本輪已嘗試報告代碼"].add(報告代碼)
                print(f"{副本設定['name']} {進度文字} 檢查報告 {報告代碼} 時失敗：{錯誤}", file=sys.stderr)
                continue

            if not 有繁中服玩家:
                for 目標副本 in 待處理副本:
                    標記報告略過(
                        副本處理狀態[目標副本["key"]],
                        報告代碼,
                        "skipped_no_traditional_chinese_players",
                        立即寫入=False,
                    )
                寫入_json(狀態檔案路徑, 狀態)
                print(f"{副本設定['name']} {進度文字} 沒有繁中服玩家，已略過 {len(待處理副本)} 個副本：{報告代碼}")
                continue

            for 目標副本 in 待處理副本:
                目標處理狀態 = 副本處理狀態[目標副本["key"]]
                目標處理狀態["traditional_chinese_reports"] += 1
                目標處理狀態["本輪已嘗試報告代碼"].add(報告代碼)

                try:
                    成績 = 建立報告成績(session, 認證池, 目標副本, 報告, 繁中服玩家, gcd計算器)
                except FFLogs報告尚未完整匯出錯誤 as 錯誤:
                    標記報告略過(
                        目標處理狀態,
                        報告代碼,
                        報告尚未完整匯出狀態,
                        {
                            "reason": str(錯誤),
                            "retryable": True,
                            "report_end_at": 錯誤.報告結束時間戳記,
                            "report_end_at_iso": 毫秒轉_iso(錯誤.報告結束時間戳記),
                            "required_fight_end_at": 錯誤.戰鬥結束時間戳記,
                            "required_fight_end_at_iso": 毫秒轉_iso(錯誤.戰鬥結束時間戳記),
                            "fight_id": 錯誤.戰鬥_id,
                        },
                    )
                    掃描來源 = str(報告.get("_scan_source") or "")
                    if 掃描來源 == "delayed":
                        目標處理狀態["delayed_reports_deferred"] += 1
                    elif 掃描來源 == "history":
                        目標處理狀態["history_reports_deferred"] += 1
                    print(f"{目標副本['name']} {進度文字} FFLogs 尚未完整匯出，延後重抓：{報告代碼}")
                    continue
                except FFLogs報告存取錯誤 as 錯誤:
                    標記不可存取報告隱藏(目標副本, 報告代碼, 錯誤)
                    標記報告略過(
                        目標處理狀態,
                        報告代碼,
                        "skipped_inaccessible",
                        {"reason": str(錯誤)},
                    )
                    print(f"{目標副本['name']} {進度文字} FFLogs 報告無法存取，已略過：{報告代碼}")
                    continue
                except Exception as 錯誤:
                    # 單份報告失敗時不中斷整批排程，避免一份異常報告卡住 GitHub Actions。
                    目標處理狀態["reports_failed"] += 1
                    print(f"{目標副本['name']} {進度文字} 處理報告 {報告代碼} 時失敗：{錯誤}", file=sys.stderr)
                    continue

                if 成績:
                    目標處理狀態["待寫入成績清單"].append(成績)
                    目標處理狀態["待標記已儲存報告"].append(報告代碼)
                    目標處理狀態["已處理報告代碼"].add(報告代碼)
                    目標處理狀態["已知報告代碼"].add(報告代碼)
                    print(
                        f"{目標副本['name']} {進度文字} 已整理有效報告：{報告代碼}"
                        f"（待寫入 {len(目標處理狀態['待寫入成績清單'])}/{排行榜批次寫入報告數}）"
                    )
                    if len(目標處理狀態["待寫入成績清單"]) >= 排行榜批次寫入報告數:
                        批次寫入排行榜(目標處理狀態, "達到批次門檻")
                else:
                    標記報告略過(目標處理狀態, 報告代碼, 無通關報告狀態)
                    print(f"{目標副本['name']} {進度文字} 未找到通關戰鬥，已略過：{報告代碼}")

        for 處理狀態 in 副本處理狀態.values():
            原因 = (
                "副本掃描結尾"
                if 處理狀態["副本設定"]["key"] == 副本設定["key"]
                else f"{副本設定['name']} 跨副本掃描結尾"
            )
            批次寫入排行榜(處理狀態, 原因)
        已完成副本清單.append(副本設定)

    既有報告狀態巡檢統計 = 執行既有報告狀態巡檢()

    副本統計: dict[str, Any] = {}
    for 副本設定 in 副本清單:
        處理狀態 = 副本處理狀態[副本設定["key"]]
        掃描起始時間戳記 = 處理狀態.get("scan_start_at")
        掃描結束時間戳記_副本 = 處理狀態.get("scan_end_at") or 掃描結束時間戳記
        副本統計[副本設定["key"]] = {
            "name": 副本設定["name"],
            "scan_start_at": 掃描起始時間戳記,
            "scan_start_at_iso": 毫秒轉_iso(掃描起始時間戳記),
            "scan_end_at": 掃描結束時間戳記_副本,
            "scan_end_at_iso": 毫秒轉_iso(掃描結束時間戳記_副本),
            "report_region_scope": 報告地區範圍,
            "candidate_reports": 處理狀態["candidate_reports"],
            "china_region_reports": 處理狀態["china_region_reports"],
            "recent_reports": 處理狀態["recent_reports"],
            "delayed_reports_found": 處理狀態["delayed_reports_found"],
            "delayed_reports_selected": 處理狀態["delayed_reports_selected"],
            "delayed_reports_skipped_known": 處理狀態["delayed_reports_skipped_known"],
            "delayed_reports_deferred": 處理狀態["delayed_reports_deferred"],
            "delayed_scan": 處理狀態.get("delayed_scan"),
            "history_reports_found": 處理狀態["history_reports_found"],
            "history_reports_selected": 處理狀態["history_reports_selected"],
            "history_reports_skipped_known": 處理狀態["history_reports_skipped_known"],
            "history_reports_deferred": 處理狀態["history_reports_deferred"],
            "history_scan": 處理狀態.get("history_scan"),
            "scan_failed": 處理狀態["scan_failed"],
            "scan_error": 處理狀態["scan_error"],
            "skipped_already_processed_reports": 處理狀態["skipped_already_processed_reports"],
            "traditional_chinese_reports": 處理狀態["traditional_chinese_reports"],
            "reports_saved": 處理狀態["reports_saved"],
            "reports_failed": 處理狀態["reports_failed"],
            "rankings_inserted_or_updated": 處理狀態["rankings_inserted_or_updated"],
        }

    總新增或更新數量 = sum(處理狀態["rankings_inserted_or_updated"] for 處理狀態 in 副本處理狀態.values())
    總失敗報告數量 = sum(處理狀態["reports_failed"] for 處理狀態 in 副本處理狀態.values())
    暫時失敗副本鍵值 = [副本["key"] for 副本 in 暫時失敗副本清單]
    即時GCD統計 = gcd計算器.建立統計()

    統計 = {
        "scan_end_at": 掃描結束時間戳記,
        "scan_end_at_iso": 毫秒轉_iso(掃描結束時間戳記),
        "report_region_scope": 報告地區範圍,
        "enabled_encounters": [副本["key"] for 副本 in 副本清單],
        "completed_encounters": [副本["key"] for 副本 in 已完成副本清單],
        "deferred_encounters": 暫時失敗副本鍵值,
        "manual_report_codes": sorted(只處理報告代碼 or 重抓報告代碼),
        "encounters": 副本統計,
        "rankings_inserted_or_updated": 總新增或更新數量,
        "reports_failed": 總失敗報告數量,
        "scan_deferred_encounters": len(暫時失敗副本鍵值),
        "fetch_gcd_coverage": 即時GCD統計,
        "existing_report_status_check": 既有報告狀態巡檢統計,
    }
    if 只處理指定報告模式:
        if 總失敗報告數量 == 0:
            for 副本設定 in 副本清單:
                清除副本掃描進度(狀態, 副本設定)
        狀態["last_manual_run_at"] = 掃描結束時間戳記
        狀態["last_manual_run_at_iso"] = 毫秒轉_iso(掃描結束時間戳記)
        狀態["last_run_stats"] = 統計
        寫入_json(狀態檔案路徑, 狀態)
    else:
        for 副本設定 in 已完成副本清單:
            套用延遲掃描執行狀態(狀態, 副本設定, 副本處理狀態[副本設定["key"]])
            套用歷史補查執行狀態(狀態, 副本設定, 副本處理狀態[副本設定["key"]])
        更新狀態(
            狀態,
            掃描結束時間戳記,
            統計,
            已完成副本清單,
            完整成功=not 暫時失敗副本鍵值,
        )

    if gcd計算器.啟用:
        print(
            "即時 GCD 覆蓋率計算："
            f"查詢 {即時GCD統計['fights_queried']} 場戰鬥，"
            f"更新 {即時GCD統計['players_updated']} 位玩家，"
            f"失敗 {即時GCD統計['fights_failed']} 場。"
        )

    if 只處理指定報告模式 and 總失敗報告數量 > 0:
        print(
            f"處理結束：寫入或更新 {總新增或更新數量} 筆排行榜成績，"
            f"{總失敗報告數量} 份報告失敗，掃描點維持不變。"
        )
        print(f"指定報告有 {總失敗報告數量} 份處理失敗，請稍後或改到其他網路環境續跑。", file=sys.stderr)
        return 1
    if 只處理指定報告模式:
        print(f"完成：寫入或更新 {總新增或更新數量} 筆排行榜成績，掃描點維持不變。")
    elif 暫時失敗副本鍵值:
        print(
            f"完成：寫入或更新 {總新增或更新數量} 筆排行榜成績；"
            f"{len(暫時失敗副本鍵值)} 個副本因 FFLogs 暫時性錯誤延後，"
            "已完成副本的掃描點已更新。"
        )
    else:
        print(f"完成：寫入或更新 {總新增或更新數量} 筆排行榜成績，state.json 已更新。")
    return 0


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--rebuild-public"]:
            重建公開排行榜檔案()
            raise SystemExit(0)
        if sys.argv[1:] == ["--split-rankings"]:
            分割排行榜儲存檔案()
            raise SystemExit(0)
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("收到中斷訊號，已保留目前掃描進度；稍後可重新執行續跑。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as 錯誤:
        print(f"執行失敗：{錯誤}", file=sys.stderr)
        raise SystemExit(1)
