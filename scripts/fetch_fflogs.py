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


API_URL = "https://www.fflogs.com/api/v2/client"
TOKEN_URL = "https://www.fflogs.com/oauth/token"

專案根目錄 = Path(__file__).resolve().parents[1]
load_dotenv(專案根目錄 / ".env")

狀態檔案路徑 = 專案根目錄 / "data" / "state.json"
副本設定檔路徑 = 專案根目錄 / "config" / "encounters.json"
FFLogs執行設定檔路徑 = 專案根目錄 / "config" / "fflogs.json"
公開副本清單路徑 = 專案根目錄 / "public" / "data" / "encounters.json"

FFLogs執行設定預設值: dict[str, Any] = {
    "report_page_limit": 100,
    "report_max_pages": 25,
    "scan_window_hours": 24,
    "min_scan_window_seconds": 60,
    "initial_lookback_hours": 24,
    "incremental_lookback_hours": 6,
    "history_scan_enabled": True,
    "history_scan_full_run": False,
    "history_scan_window_hours": 24,
    "history_scan_windows_per_run": 1,
    "history_scan_recent_gap_hours": 6,
    "history_max_deep_reports_per_run": 25,
    "report_status_cache_limit": 50000,
    "request_timeout": 30,
    "request_retries": 3,
    "rate_limit_requests": 240,
    "rate_limit_window_seconds": 120,
    "rate_limit_padding_seconds": 1.0,
    "rate_limited_cooldown_seconds": 3600,
    "json_write_retries": 10,
    "json_write_retry_seconds": 0.5,
    "ranking_flush_reports": 25,
    "retry_report_codes": [],
    "only_report_codes": [],
}


def 讀取FFLogs執行設定() -> dict[str, Any]:
    if not FFLogs執行設定檔路徑.exists():
        return dict(FFLogs執行設定預設值)

    try:
        with FFLogs執行設定檔路徑.open("r", encoding="utf-8") as 設定檔:
            原始設定 = json.load(設定檔)
    except json.JSONDecodeError as 錯誤:
        raise RuntimeError(f"FFLogs 執行設定不是有效 JSON：{FFLogs執行設定檔路徑}") from 錯誤

    if not isinstance(原始設定, dict):
        raise RuntimeError(f"FFLogs 執行設定必須是物件：{FFLogs執行設定檔路徑}")

    設定 = dict(FFLogs執行設定預設值)
    設定.update(原始設定)
    return 設定


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

中國區域_ID = 4
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
公開排行榜條目欄位 = (
    "id",
    "character_name",
    "server",
    "job",
    "dps",
    "rdps",
    "adps",
    "active_time_ms",
    "active_percent",
    "clear_time_seconds",
    "recorded_at_iso",
    "report_start_time_iso",
    "report_code",
    "report_url",
    "fight_id",
    "duplicate_count",
    "rank",
)

每頁報告數量 = 整數設定("report_page_limit")
報告查詢最大頁數 = 整數設定("report_max_pages")
淺層掃描區間小時 = 整數設定("scan_window_hours")
最小切分區間毫秒 = 整數設定("min_scan_window_seconds") * 1000
初次掃描回溯小時 = 整數設定("initial_lookback_hours")
增量掃描回溯小時 = max(0, 整數設定("incremental_lookback_hours"))
歷史補查已啟用 = 布林設定("history_scan_enabled")
歷史補查完整執行 = 布林設定("history_scan_full_run")
歷史補查區間小時 = max(1, 整數設定("history_scan_window_hours"))
歷史補查每輪區間數 = max(0, 整數設定("history_scan_windows_per_run"))
歷史補查最近避讓小時 = max(
    0,
    整數設定("history_scan_recent_gap_hours"),
)
歷史補查深層報告上限 = 整數設定("history_max_deep_reports_per_run")
報告檢查快取上限 = max(0, 整數設定("report_status_cache_limit"))
請求逾時秒數 = 整數設定("request_timeout")
重試次數 = 整數設定("request_retries")
速率限制請求數 = 整數設定("rate_limit_requests")
速率限制視窗秒數 = 整數設定("rate_limit_window_seconds")
速率限制緩衝秒數 = 浮點設定("rate_limit_padding_seconds")
限流冷卻秒數 = 整數設定("rate_limited_cooldown_seconds")
json寫入重試次數 = max(1, 整數設定("json_write_retries"))
json寫入重試等待秒數 = max(0.1, 浮點設定("json_write_retry_seconds"))
排行榜批次寫入報告數 = max(1, 整數設定("ranking_flush_reports"))
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


class FFLogs限流錯誤(RuntimeError):
    def __init__(self, 回應: requests.Response) -> None:
        super().__init__(f"FFLogs 回傳 HTTP 429：{回應.text}")
        self.回應 = 回應


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


深層過濾查詢 = """
query ReportMasterData($code: String!) {
  reportData {
    report(code: $code) {
      code
      masterData {
        actors(type: "Player") {
          id
          name
          server
          subType
        }
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
      region {
        id
        name
      }
      fights(encounterID: $encounterID, difficulty: $difficulty, killType: Kills) {
        id
        encounterID
        name
        startTime
        endTime
        combatTime
        difficulty
        averageItemLevel
        bossPercentage
      }
    }
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


def 更新副本掃描進度(狀態: dict[str, Any], 副本設定: dict[str, Any], **進度: Any) -> None:
    副本狀態索引 = 狀態.setdefault("encounters", {})
    副本狀態 = 副本狀態索引.setdefault(副本設定["key"], {})
    即時進度 = 副本狀態.setdefault("active_scan", {})
    更新時間戳記 = 現在毫秒()

    即時進度.update(進度)
    即時進度["updated_at"] = 更新時間戳記
    即時進度["updated_at_iso"] = 毫秒轉_iso(更新時間戳記)
    寫入_json(狀態檔案路徑, 狀態)


def 清除副本掃描進度(狀態: dict[str, Any], 副本設定: dict[str, Any]) -> None:
    副本狀態 = (狀態.get("encounters") or {}).get(副本設定["key"]) or {}
    副本狀態.pop("active_scan", None)


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

    print(f"偵測到前次未完成掃描：{副本設定['name']} / {階段}，最後更新 {最後更新}{補充}")


def 轉_int_or_none(值: Any) -> int | None:
    if 值 is None or 值 == "":
        return None
    try:
        return int(值)
    except (TypeError, ValueError):
        return None


def 排行榜檔案路徑(副本設定: dict[str, Any], public: bool = False) -> Path:
    根目錄 = 專案根目錄 / "public" if public else 專案根目錄
    return 根目錄 / "data" / "rankings" / f"{副本設定['key']}.json"


def 讀取副本設定清單() -> list[dict[str, Any]]:
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


def 寫入公開副本清單(副本清單: list[dict[str, Any]]) -> None:
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

        公開清單.append(
            {
                "key": 副本鍵值,
                "name": 副本["name"],
                "category": 副本.get("category"),
                "enabled": True,
                "data_path": f"data/rankings/{副本鍵值}.json",
            }
        )
        已加入鍵值.add(副本鍵值)

    for 副本 in 副本清單:
        if 副本["key"] in 已加入鍵值:
            continue
        公開清單.append(
            {
                "key": 副本["key"],
                "name": 副本["name"],
                "category": 副本.get("category"),
                "enabled": True,
                "data_path": f"data/rankings/{副本['key']}.json",
            }
        )

    寫入_json(公開副本清單路徑, 公開清單)


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


def 分割環境清單(值: str | None) -> list[str]:
    if not 值:
        return []
    return [項.strip() for 項 in 值.split(",") if 項.strip()]


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
    使用速率限制器 = 速率限制器 or FFLOGS速率限制器

    for 第幾次 in range(1, 重試次數 + 1):
        try:
            使用速率限制器.等待可送出()
            回應 = session.post(url, timeout=請求逾時秒數, **kwargs)
            if 回應.status_code not in {429, 500, 502, 503, 504}:
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
            print(f"FFLogs API 暫時無法回應，{等待秒數} 秒後重試。HTTP {回應.status_code}", file=sys.stderr)
            time.sleep(等待秒數)
        except requests.RequestException as 錯誤:
            最後錯誤 = 錯誤
            等待秒數 = min(2 ** 第幾次, 30)
            print(f"連線失敗，{等待秒數} 秒後重試：{錯誤}", file=sys.stderr)
            time.sleep(等待秒數)

    if 最後錯誤:
        raise RuntimeError("FFLogs API 請求重試後仍失敗。") from 最後錯誤

    return 回應


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
        raise RuntimeError(f"FFLogs GraphQL 請求失敗：HTTP {回應.status_code} {回應.text}")

    內容 = 回應.json()
    if 內容.get("errors"):
        raise RuntimeError(f"FFLogs GraphQL 回傳錯誤：{json.dumps(內容['errors'], ensure_ascii=False)}")

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
            區域 = 報告.get("region") or {}
            if not 代碼 or 代碼 in 已看過代碼:
                continue

            # FFLogs 目前 reports 查詢沒有 regionID 參數，因此先抓指定時間與 zone，再以 report.region.id 過濾。
            if int(區域.get("id") or -1) != 中國區域_ID:
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
    區間毫秒 = max(掃描區間小時 or 淺層掃描區間小時, 1) * 60 * 60 * 1000
    目前起點 = 起始時間戳記

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


def 取得傷害統計列(原始成績: dict[str, Any]) -> list[dict[str, Any]]:
    damage_done = 原始成績.get("damage_done")
    if not isinstance(damage_done, dict):
        return []

    資料 = damage_done.get("data")
    if not isinstance(資料, dict):
        return []

    entries = 資料.get("entries")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


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


def 從原始成績整理玩家_dps(原始成績: dict[str, Any], 戰鬥時間毫秒: float | None) -> list[dict[str, Any]]:
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
            "players": 玩家簽章,
        }
    )


def 成績是否優先(候選: dict[str, Any], 目前最佳: dict[str, Any] | None) -> bool:
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


def 建立排行榜條目(排行榜: dict[str, Any]) -> list[dict[str, Any]]:
    精確成績索引: dict[str, dict[str, Any]] = {}
    最佳成績索引: dict[str, dict[str, Any]] = {}

    for 報告代碼, 報告 in (排行榜.get("reports") or {}).items():
        if not isinstance(報告, dict):
            continue

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
                    }
                )
                既有成績 = 精確成績索引.get(精確成績鍵值)
                if 既有成績:
                    if 報告代碼 not in 既有成績["source_reports"]:
                        既有成績["source_reports"].append(報告代碼)
                        既有成績["duplicate_count"] = len(既有成績["source_reports"])
                    continue

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
                    "active_percent": 計算_active_percent(玩家.get("active_time_ms"), 戰鬥.get("clear_time_ms")),
                    "clear_time_ms": 戰鬥.get("clear_time_ms"),
                    "clear_time_seconds": 戰鬥.get("clear_time_seconds"),
                    "recorded_at": 戰鬥.get("recorded_at"),
                    "recorded_at_iso": 戰鬥.get("recorded_at_iso"),
                    "report_code": 報告代碼,
                    "report_url": 報告.get("url"),
                    "report_title": 報告.get("title"),
                    "fight_id": 戰鬥.get("fight_id"),
                    "fight_hash": 戰鬥簽章,
                    "source_reports": [報告代碼],
                    "duplicate_count": 1,
                }
                精確成績索引[精確成績鍵值] = 成績

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


def 建立公開排行榜(排行榜: dict[str, Any]) -> dict[str, Any]:
    排行榜條目 = 排行榜.get("ranking_entries")
    if not isinstance(排行榜條目, list):
        排行榜條目 = 建立排行榜條目(排行榜)

    return {
        "schema_version": 排行榜.get("schema_version", 1),
        "encounter": 排行榜.get("encounter"),
        "updated_at": 排行榜.get("updated_at"),
        "updated_at_iso": 排行榜.get("updated_at_iso"),
        "ranking_entries": [
            建立公開排行榜條目(條目)
            for 條目 in 排行榜條目
            if isinstance(條目, dict)
        ],
    }


def 建立報告成績(
    session: requests.Session,
    認證池: FFLogs認證池,
    副本設定: dict[str, Any],
    淺層報告: dict[str, Any],
    繁中服玩家: list[dict[str, Any]],
) -> dict[str, Any] | None:
    報告代碼 = 淺層報告["code"]
    報告 = 查詢通關戰鬥(session, 認證池, 副本設定, 報告代碼)
    if not 報告:
        return None

    戰鬥列表 = 報告.get("fights") or []
    if not 戰鬥列表:
        return None

    整理後戰鬥列表: list[dict[str, Any]] = []
    報告起始時間戳記 = 報告.get("startTime") or 淺層報告.get("startTime")
    for 戰鬥 in 戰鬥列表:
        戰鬥_id = 戰鬥.get("id")
        if not isinstance(戰鬥_id, int):
            continue

        戰鬥時間毫秒 = 轉_float(戰鬥.get("combatTime"))
        if 戰鬥時間毫秒 is None:
            戰鬥開始 = 轉_float(戰鬥.get("startTime"))
            戰鬥結束 = 轉_float(戰鬥.get("endTime"))
            if 戰鬥開始 is not None and 戰鬥結束 is not None:
                戰鬥時間毫秒 = 戰鬥結束 - 戰鬥開始

        原始成績 = 查詢玩家成績(session, 認證池, 副本設定, 報告代碼, 戰鬥_id)
        紀錄時間戳記 = 相對戰鬥時間轉實際時間(報告起始時間戳記, 戰鬥.get("startTime"))
        整理後戰鬥列表.append(
            {
                "fight_id": 戰鬥_id,
                "encounter_id": 戰鬥.get("encounterID"),
                "name": 戰鬥.get("name"),
                "difficulty": 戰鬥.get("difficulty"),
                "start_time": 戰鬥.get("startTime"),
                "start_time_iso": 毫秒轉_iso(戰鬥.get("startTime")),
                "end_time": 戰鬥.get("endTime"),
                "end_time_iso": 毫秒轉_iso(戰鬥.get("endTime")),
                "recorded_at": 紀錄時間戳記,
                "recorded_at_iso": 毫秒轉_iso(紀錄時間戳記),
                "clear_time_ms": int(戰鬥時間毫秒) if 戰鬥時間毫秒 is not None else None,
                "clear_time_seconds": round(戰鬥時間毫秒 / 1000, 3) if 戰鬥時間毫秒 is not None else None,
                "average_item_level": 戰鬥.get("averageItemLevel"),
                "boss_percentage": 戰鬥.get("bossPercentage"),
                "players": 從原始成績整理玩家_dps(原始成績, 戰鬥時間毫秒),
            }
        )

    if not 整理後戰鬥列表:
        return None

    區域 = 報告.get("region") or 淺層報告.get("region") or {}
    return {
        "report_code": 報告代碼,
        "title": 報告.get("title") or 淺層報告.get("title"),
        "url": f"https://www.fflogs.com/reports/{報告代碼}",
        "region": {
            "id": 區域.get("id"),
            "name": 區域.get("name"),
        },
        "report_start_time": 報告起始時間戳記,
        "report_start_time_iso": 毫秒轉_iso(報告起始時間戳記),
        "report_end_time": 報告.get("endTime") or 淺層報告.get("endTime"),
        "report_end_time_iso": 毫秒轉_iso(報告.get("endTime") or 淺層報告.get("endTime")),
        "matched_traditional_chinese_servers": sorted(
            {玩家.get("server") for 玩家 in 繁中服玩家 if 玩家.get("server")}
        ),
        "matched_players": 繁中服玩家,
        "fights": 整理後戰鬥列表,
        "fetched_at": 現在毫秒(),
        "fetched_at_iso": 毫秒轉_iso(現在毫秒()),
    }


def 建立副本摘要(副本設定: dict[str, Any]) -> dict[str, Any]:
    return {
        "key": 副本設定["key"],
        "name": 副本設定["name"],
        "category": 副本設定.get("category"),
        "zone_id": 副本設定["zone_id"],
        "encounter_id": 副本設定["encounter_id"],
        "difficulty": 副本設定["difficulty"],
    }


def 正規化排行榜(原始內容: Any, 副本設定: dict[str, Any]) -> dict[str, Any]:
    if isinstance(原始內容, dict) and isinstance(原始內容.get("reports"), dict):
        return 原始內容

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
    排行榜["ranking_entries"] = 建立排行榜條目(排行榜)
    排行榜["updated_at"] = 現在毫秒()
    排行榜["updated_at_iso"] = 毫秒轉_iso(排行榜["updated_at"])

    寫入_json(排行榜檔案路徑(副本設定), 排行榜, 緊湊格式=True)
    寫入_json(排行榜檔案路徑(副本設定, public=True), 建立公開排行榜(排行榜), 緊湊格式=True)


def 重建公開排行榜檔案() -> None:
    副本清單 = 讀取副本設定清單()
    寫入公開副本清單(副本清單)

    for 副本設定 in 副本清單:
        排行榜 = 正規化排行榜(讀取_json(排行榜檔案路徑(副本設定), {}), 副本設定)
        if not isinstance(排行榜.get("ranking_entries"), list):
            排行榜["ranking_entries"] = 建立排行榜條目(排行榜)
        排行榜.setdefault("schema_version", 1)
        排行榜.setdefault("encounter", 建立副本摘要(副本設定))
        寫入_json(排行榜檔案路徑(副本設定, public=True), 建立公開排行榜(排行榜), 緊湊格式=True)
        print(f"已重建公開排行榜：{副本設定['key']}")


def 合併寫入排行榜(副本設定: dict[str, Any], 新成績列表: list[dict[str, Any]]) -> int:
    排行榜 = 正規化排行榜(讀取_json(排行榜檔案路徑(副本設定), {}), 副本設定)
    新增或更新數量 = 套用成績到排行榜(排行榜, 新成績列表)
    寫入排行榜檔案(副本設定, 排行榜)
    return 新增或更新數量


def 讀取已處理報告代碼(狀態: dict[str, Any], 副本設定: dict[str, Any]) -> set[str]:
    副本鍵值 = 副本設定["key"]
    已處理 = set()

    副本狀態 = (狀態.get("encounters") or {}).get(副本鍵值) or {}
    已處理報告 = 副本狀態.get("processed_reports") or {}
    if isinstance(已處理報告, dict):
        已處理.update(str(代碼) for 代碼 in 已處理報告.keys())

    已檢查報告 = 副本狀態.get("checked_reports") or {}
    if isinstance(已檢查報告, dict):
        已處理.update(str(代碼) for 代碼 in 已檢查報告.keys())

    排行榜 = 讀取_json(排行榜檔案路徑(副本設定), {})
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
) -> None:
    狀態 = dict(原始狀態)
    狀態["last_scanned_at"] = 新時間戳記
    狀態["last_scanned_at_iso"] = 毫秒轉_iso(新時間戳記)
    狀態["last_successful_run_at"] = 現在毫秒()
    狀態["last_successful_run_at_iso"] = 毫秒轉_iso(狀態["last_successful_run_at"])
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

    print(f"啟用副本：{', '.join(副本['name'] for 副本 in 副本清單)}")
    print(f"可用 FFLogs 憑證組數：{len(認證池.認證清單)}")
    if 重抓報告代碼:
        print(f"指定重抓報告：{', '.join(sorted(重抓報告代碼))}")
    if 只處理報告代碼:
        print(f"只處理指定報告，掃描點不會往後推進：{', '.join(sorted(只處理報告代碼))}")

    副本處理狀態: dict[str, dict[str, Any]] = {}
    for 副本設定 in 副本清單:
        副本處理狀態[副本設定["key"]] = {
            "副本設定": 副本設定,
            "已處理報告代碼": 讀取已處理報告代碼(狀態, 副本設定),
            "本輪已嘗試報告代碼": set(),
            "排行榜": 正規化排行榜(讀取_json(排行榜檔案路徑(副本設定), {}), 副本設定),
            "待寫入成績清單": [],
            "待標記已儲存報告": [],
            "scan_start_at": None,
            "scan_end_at": 掃描結束時間戳記,
            "china_region_reports": 0,
            "recent_reports": 0,
            "history_reports_found": 0,
            "history_reports_selected": 0,
            "history_reports_skipped_known": 0,
            "history_reports_deferred": 0,
            "history_scan": None,
            "skipped_already_processed_reports": 0,
            "traditional_chinese_reports": 0,
            "reports_saved": 0,
            "reports_failed": 0,
            "rankings_inserted_or_updated": 0,
        }

    淺層掃描快取: dict[tuple[int, int, int, int | None], list[dict[str, Any]]] = {}
    歷史補查候選報告代碼: set[str] = set()

    def 取得同區同難度副本清單(基準副本: dict[str, Any]) -> list[dict[str, Any]]:
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
        *,
        立即寫入: bool = True,
    ) -> None:
        副本設定 = 處理狀態["副本設定"]
        標記報告處理狀態(狀態, 副本設定, 報告代碼, 處理狀態文字, 立即寫入=立即寫入)
        處理狀態["已處理報告代碼"].add(報告代碼)
        處理狀態["本輪已嘗試報告代碼"].add(報告代碼)

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

            最新報告列表 = 擷取並快取淺層報告(
                副本設定,
                起始時間戳記,
                掃描結束時間戳記,
                記錄淺層掃描進度,
            )
            最新報告列表 = 補入指定報告(最新報告列表, 重抓報告代碼, 起始時間戳記, 掃描結束時間戳記)
            最新報告列表 = 加入掃描來源(最新報告列表, "recent")
            最新報告代碼 = {str(報告.get("code")) for 報告 in 最新報告列表 if 報告.get("code")}

            歷史報告列表: list[dict[str, Any]] = []
            歷史區間列表, 歷史補查狀態 = 建立歷史補查區間(狀態, 副本設定, 狀態時間戳記)
            目前處理狀態["history_scan"] = 歷史補查狀態

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

            歷史報告列表 = 加入掃描來源(歷史報告列表, "history")
            歷史報告候選列表, 歷史候選統計 = 篩選歷史補查候選(副本設定, 歷史報告列表, 最新報告代碼)
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

            淺層報告列表 = 合併淺層報告列表(最新報告列表, 歷史報告候選列表)
            目前處理狀態["recent_reports"] = len(最新報告列表)
            print(
                f"{副本設定['name']} 淺層掃描取得 {len(最新報告列表)} 份中國區域報告；"
                f"歷史補查找到 {len(歷史報告代碼)} 份，選入 {歷史候選統計['selected']} 份"
                f"（已知略過 {歷史候選統計['skipped_known']}，延後 {歷史候選統計['deferred']}）。"
            )

        目前處理狀態["china_region_reports"] = len(淺層報告列表)
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
                有繁中服玩家, 繁中服玩家 = 報告是否包含繁中服玩家(session, 認證池, 報告代碼)
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
                    成績 = 建立報告成績(session, 認證池, 目標副本, 報告, 繁中服玩家)
                except Exception as 錯誤:
                    # 單份報告失敗時不中斷整批排程，避免一份異常報告卡住 GitHub Actions。
                    目標處理狀態["reports_failed"] += 1
                    print(f"{目標副本['name']} {進度文字} 處理報告 {報告代碼} 時失敗：{錯誤}", file=sys.stderr)
                    continue

                if 成績:
                    目標處理狀態["待寫入成績清單"].append(成績)
                    目標處理狀態["待標記已儲存報告"].append(報告代碼)
                    目標處理狀態["已處理報告代碼"].add(報告代碼)
                    print(
                        f"{目標副本['name']} {進度文字} 已整理有效報告：{報告代碼}"
                        f"（待寫入 {len(目標處理狀態['待寫入成績清單'])}/{排行榜批次寫入報告數}）"
                    )
                    if len(目標處理狀態["待寫入成績清單"]) >= 排行榜批次寫入報告數:
                        批次寫入排行榜(目標處理狀態, "達到批次門檻")
                else:
                    標記報告略過(目標處理狀態, 報告代碼, "skipped_no_clear")
                    print(f"{目標副本['name']} {進度文字} 未找到通關戰鬥，已略過：{報告代碼}")

        for 處理狀態 in 副本處理狀態.values():
            原因 = "副本掃描結尾" if 處理狀態["副本設定"]["key"] == 副本設定["key"] else f"{副本設定['name']} 跨副本掃描結尾"
            批次寫入排行榜(處理狀態, 原因)

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
            "china_region_reports": 處理狀態["china_region_reports"],
            "recent_reports": 處理狀態["recent_reports"],
            "history_reports_found": 處理狀態["history_reports_found"],
            "history_reports_selected": 處理狀態["history_reports_selected"],
            "history_reports_skipped_known": 處理狀態["history_reports_skipped_known"],
            "history_reports_deferred": 處理狀態["history_reports_deferred"],
            "history_scan": 處理狀態.get("history_scan"),
            "skipped_already_processed_reports": 處理狀態["skipped_already_processed_reports"],
            "traditional_chinese_reports": 處理狀態["traditional_chinese_reports"],
            "reports_saved": 處理狀態["reports_saved"],
            "reports_failed": 處理狀態["reports_failed"],
            "rankings_inserted_or_updated": 處理狀態["rankings_inserted_or_updated"],
        }

    總新增或更新數量 = sum(處理狀態["rankings_inserted_or_updated"] for 處理狀態 in 副本處理狀態.values())
    總失敗報告數量 = sum(處理狀態["reports_failed"] for 處理狀態 in 副本處理狀態.values())

    統計 = {
        "scan_end_at": 掃描結束時間戳記,
        "scan_end_at_iso": 毫秒轉_iso(掃描結束時間戳記),
        "enabled_encounters": [副本["key"] for 副本 in 副本清單],
        "manual_report_codes": sorted(只處理報告代碼 or 重抓報告代碼),
        "encounters": 副本統計,
        "rankings_inserted_or_updated": 總新增或更新數量,
        "reports_failed": 總失敗報告數量,
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
        for 副本設定 in 副本清單:
            套用歷史補查執行狀態(狀態, 副本設定, 副本處理狀態[副本設定["key"]])
        更新狀態(狀態, 掃描結束時間戳記, 統計, 副本清單)

    if 只處理指定報告模式 and 總失敗報告數量 > 0:
        print(
            f"處理結束：寫入或更新 {總新增或更新數量} 筆排行榜成績，"
            f"{總失敗報告數量} 份報告失敗，掃描點維持不變。"
        )
        print(f"指定報告有 {總失敗報告數量} 份處理失敗，請稍後或改到其他網路環境續跑。", file=sys.stderr)
        return 1
    if 只處理指定報告模式:
        print(f"完成：寫入或更新 {總新增或更新數量} 筆排行榜成績，掃描點維持不變。")
    else:
        print(f"完成：寫入或更新 {總新增或更新數量} 筆排行榜成績，state.json 已更新。")
    return 0


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--rebuild-public"]:
            重建公開排行榜檔案()
            raise SystemExit(0)
        raise SystemExit(main())
    except Exception as 錯誤:
        print(f"執行失敗：{錯誤}", file=sys.stderr)
        raise SystemExit(1)
