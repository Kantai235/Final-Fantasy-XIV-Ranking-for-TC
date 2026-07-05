from __future__ import annotations

import argparse
import hashlib
import json
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

import backfill_gcd_coverage as local_gcd  # noqa: E402

for stream in (sys.stdout, sys.stderr):
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8")


# xivanalysis 沒有提供正式的「GCD 覆蓋率 JSON API」。它的網站會載入 FFLogs v1 fights/events，
# 再於瀏覽器內跑 AlwaysBeCasting 模組產生畫面上的百分比。正式資料仍只保存衍生結果；
# 人工稽核可額外使用 .cache/ 本機快取保存外部答案與 FFLogs fight payload，讓演算法修正
# 能離線重算，避免每次都重新打 FFLogs / xivanalysis。
XIVANALYSIS_BASE_URL = "https://xivanalysis.com"
XIVANALYSIS_GCD_SOURCE = "xivanalysis_page"
DEFAULT_AUDIT_CACHE_DIR = PROJECT_ROOT / ".cache" / "xivanalysis-gcd-audit"
DEFAULT_LIMIT = 200
DEFAULT_PAGE_TIMEOUT_MS = 90_000
DEFAULT_DELAY_MS = 2_500
DEFAULT_FLUSH_EVERY = 1_000
DEFAULT_WORKERS = 1
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 600
DEFAULT_MAX_RATE_LIMIT_PAUSES = 12
GCD_PERCENT_STABLE_POLLS = 4
GCD_PERCENT_SETTLE_SECONDS = 3.0
GCD_PERCENT_NETWORK_IDLE_TIMEOUT_MS = 0


class XivanalysisLookupError(RuntimeError):
    pass


class XivanalysisPermanentError(XivanalysisLookupError):
    pass


class XivanalysisRateLimitError(XivanalysisLookupError):
    pass


@dataclass(frozen=True)
class CandidateScanSummary:
    total_rankable: int
    queryable: int
    missing_key: int
    null_value: int
    current_xivanalysis: int
    needs_refresh: int
    no_query_context: int


@dataclass(frozen=True)
class XivanalysisFetchResult:
    index: int
    total: int
    candidate: local_gcd.GcdCandidate
    percent: float | None = None
    url: str | None = None
    error: Exception | None = None


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def stable_json_hash(value: dict[str, Any]) -> str:
    encoded = json_dumps_compact(value).encode("utf-8")
    return hashlib.sha1(encoded).hexdigest()


def json_dumps_compact(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(f".{path.name}.{time.time_ns()}.tmp")
    temp_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_path.replace(path)


def read_json_if_exists(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        content = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return content if isinstance(content, dict) else None


def fight_cache_identity(candidate: local_gcd.GcdCandidate) -> dict[str, Any]:
    return {
        "report_code": candidate.report_code,
        "fight_id": local_gcd.to_int(candidate.fight.get("fight_id")),
        "start_time": local_gcd.first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime")),
        "end_time": local_gcd.first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime")),
    }


def player_cache_identity(candidate: local_gcd.GcdCandidate) -> dict[str, Any]:
    player = candidate.player
    identity = fight_cache_identity(candidate)
    identity.update(
        {
            "encounter_key": candidate.encounter_key,
            "fflogs_id": local_gcd.to_int(player.get("fflogs_id")),
            "player": player.get("name") or player.get("character_name"),
            "server": player.get("server"),
            "job": player.get("job"),
        }
    )
    return identity


class GcdAuditCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _report_dir(self, namespace: str, report_code: str) -> Path:
        safe_report = re.sub(r"[^A-Za-z0-9_-]+", "_", report_code or "unknown")
        return self.root / namespace / "v1" / safe_report

    def _fflogs_path(self, kind: str, candidate: local_gcd.GcdCandidate) -> Path:
        identity = fight_cache_identity(candidate)
        key = stable_json_hash(identity)
        return self._report_dir("fflogs", candidate.report_code) / f"{key}.{kind}.json"

    def _xivanalysis_path(self, candidate: local_gcd.GcdCandidate) -> Path:
        identity = player_cache_identity(candidate)
        key = stable_json_hash(identity)
        return self._report_dir("xivanalysis", candidate.report_code) / f"{key}.json"

    def read_fflogs_payload(self, kind: str, candidate: local_gcd.GcdCandidate) -> Any | None:
        cached = read_json_if_exists(self._fflogs_path(kind, candidate))
        if not cached or cached.get("schema_version") != 1 or cached.get("kind") != kind:
            return None
        return cached.get("payload")

    @staticmethod
    def _cached_fight_id(fight: dict[str, Any]) -> int | None:
        for value in (fight.get("id"), fight.get("fightID"), fight.get("fight_id")):
            fight_id = local_gcd.to_int(value)
            if fight_id is not None:
                return fight_id
        return None

    @staticmethod
    def _fight_has_players(fight: dict[str, Any]) -> bool:
        players = fight.get("players")
        return isinstance(players, list) and len(players) > 0

    @classmethod
    def _merge_fight_metadata(cls, primary: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
        merged = dict(primary)
        for key, value in fallback.items():
            if value is None:
                continue
            if key == "players":
                if isinstance(value, list) and value and not cls._fight_has_players(merged):
                    merged["players"] = value
                continue
            if key not in merged or merged.get(key) is None:
                merged[key] = value
        return merged

    def _preserve_rich_report_fight_metadata(
        self,
        candidate: local_gcd.GcdCandidate,
        payload: Any,
    ) -> Any:
        if not isinstance(payload, dict):
            return payload

        fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
        existing_fight = self.find_report_fight_by_id(candidate.report_code, fight_id)
        if fight_id is None or not existing_fight:
            return payload

        payload_parent = payload
        payload_fights = payload.get("fights")
        if isinstance(payload.get("data"), dict):
            payload_parent = payload["data"]
            payload_fights = payload_parent.get("fights")
        if not isinstance(payload_fights, list):
            return payload

        merged_fights: list[Any] = []
        changed = False
        for fight in payload_fights:
            if not isinstance(fight, dict) or self._cached_fight_id(fight) != fight_id:
                merged_fights.append(fight)
                continue

            # xivanalysis proxy 的 report/fights 很適合保存 combatTime，但不會帶本專案
            # 從 playerDetails 建好的 players/sourceID。raw-events 的 targetability 推導
            # 需要這些 friendly sourceID 排除玩家事件，因此寫入 proxy cache 時要保留
            # 既有較完整的 FFLogs fight metadata。
            merged = self._merge_fight_metadata(fight, existing_fight)
            merged.setdefault("id", fight_id)
            merged.setdefault("fight_id", fight_id)
            changed = changed or merged != fight
            merged_fights.append(merged)

        if not changed:
            return payload

        merged_payload = dict(payload)
        if payload_parent is not payload:
            merged_data = dict(payload_parent)
            merged_data["fights"] = merged_fights
            merged_payload["data"] = merged_data
        else:
            merged_payload["fights"] = merged_fights
        return merged_payload

    def write_fflogs_payload(self, kind: str, candidate: local_gcd.GcdCandidate, payload: Any) -> None:
        if kind == "report_fights":
            payload = self._preserve_rich_report_fight_metadata(candidate, payload)
        write_json_atomic(
            self._fflogs_path(kind, candidate),
            {
                "schema_version": 1,
                "kind": kind,
                "identity": fight_cache_identity(candidate),
                "cached_at_iso": utc_now_iso(),
                "payload": payload,
            },
        )

    def find_report_fight_by_id(self, report_code: str, fight_id: int | None) -> dict[str, Any] | None:
        """從已落地的 report_fights 快取找 fight metadata，供離線重算工具重建 GCD candidate。"""
        if fight_id is None:
            return None

        report_dir = self._report_dir("fflogs", report_code)
        if not report_dir.exists():
            return None

        best_fight: dict[str, Any] | None = None
        best_score = -1
        for path in report_dir.glob("*.report_fights.json"):
            payload = read_json_if_exists(path)
            if not payload or payload.get("schema_version") != 1 or payload.get("kind") != "report_fights":
                continue

            cached_payload = payload.get("payload")
            if isinstance(cached_payload, dict) and isinstance(cached_payload.get("data"), dict):
                cached_payload = cached_payload["data"]
            fights = cached_payload.get("fights") if isinstance(cached_payload, dict) else None
            if not isinstance(fights, list):
                continue

            for fight in fights:
                if not isinstance(fight, dict):
                    continue

                if self._cached_fight_id(fight) != fight_id:
                    continue

                normalized = dict(fight)
                normalized.setdefault("id", fight_id)
                normalized.setdefault("fight_id", fight_id)
                players = normalized.get("players")
                player_count = len(players) if isinstance(players, list) else 0
                # 同一場 fight 可能同時存在 FFLogs 輕量 fight list、專案分片補上的
                # 完整 playerDetails，以及 xivanalysis proxy 補種的 metadata。raw-events
                # 的 targetability 推斷需要友方 sourceID，否則會把玩家事件誤當成敵方
                # actor，讓幻白虎等副本少扣 downtime。掃完整個 report cache，優先採用
                # 帶有 players 的版本，避免 glob 順序拿到較薄的舊快取。
                score = 10 if player_count > 0 else 0
                if normalized.get("combatTime") is not None or normalized.get("clear_time_ms") is not None:
                    score += 1
                if score > best_score:
                    best_fight = normalized
                    best_score = score

        return best_fight

    def write_report_fight_metadata(self, candidate: local_gcd.GcdCandidate, fight: dict[str, Any]) -> None:
        """保存可離線重算 GCD 的單場 fight metadata。

        xivanalysis 頁面不一定會在每次載入時請求完整 FFLogs fight list；但本地重算
        Always Be Casting 需要 `combatTime` 來對齊 legacy FFLogs adapter 的 pull 起點。
        因此在抽樣稽核已經取得候選 fight 或 Casts graph 時，至少把單場必要 metadata
        快取起來。若快取中已有完整 fight list，保留完整 payload，但仍補齊本地候選
        fight 內的 players/sourceID 脈絡，讓未來離線重算 raw targetability 不必回頭讀
        排行榜分片或重新打 FFLogs。
        """
        if not isinstance(fight, dict):
            return

        existing_payload = self.read_fflogs_payload("report_fights", candidate)
        existing_fight = self.read_report_fight(candidate) if isinstance(existing_payload, dict) else None
        fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
        if fight_id is None:
            fight_id = local_gcd.to_int(fight.get("id")) or local_gcd.to_int(fight.get("fight_id"))

        if isinstance(existing_payload, dict):
            payload_fights = existing_payload.get("fights")
            payload_parent: dict[str, Any] = existing_payload
            if isinstance(existing_payload.get("data"), dict):
                payload_parent = existing_payload["data"]
                payload_fights = payload_parent.get("fights")
            if isinstance(payload_fights, list) and len(payload_fights) > 1:
                merged_fights: list[Any] = []
                changed = False
                for cached_fight in payload_fights:
                    if not isinstance(cached_fight, dict):
                        merged_fights.append(cached_fight)
                        continue

                    if self._cached_fight_id(cached_fight) != fight_id:
                        merged_fights.append(cached_fight)
                        continue

                    merged = self._merge_fight_metadata(cached_fight, fight)
                    if fight_id is not None:
                        merged.setdefault("id", fight_id)
                        merged.setdefault("fight_id", fight_id)
                    changed = changed or merged != cached_fight
                    merged_fights.append(merged)

                if changed:
                    merged_payload = dict(existing_payload)
                    if payload_parent is not existing_payload:
                        merged_data = dict(payload_parent)
                        merged_data["fights"] = merged_fights
                        merged_payload["data"] = merged_data
                    else:
                        merged_payload["fights"] = merged_fights
                    self.write_fflogs_payload("report_fights", candidate, merged_payload)
                return

        merged = self._merge_fight_metadata(existing_fight or {}, fight)
        if fight_id is not None:
            merged.setdefault("id", fight_id)
            merged.setdefault("fight_id", fight_id)

        self.write_fflogs_payload("report_fights", candidate, {"fights": [merged]})

    def merge_xivanalysis_proxy_events(
        self,
        candidate: local_gcd.GcdCandidate,
        payload: dict[str, Any],
        *,
        url: str,
    ) -> None:
        events = payload.get("events")
        if not isinstance(events, list):
            return

        cached_payload = self.read_fflogs_payload("xivanalysis_proxy_events", candidate)
        cached_events: list[dict[str, Any]] = []
        cached_pages: list[dict[str, Any]] = []
        if isinstance(cached_payload, dict):
            cached_events = [event for event in cached_payload.get("events") or [] if isinstance(event, dict)]
            cached_pages = [page for page in cached_payload.get("pages") or [] if isinstance(page, dict)]

        merged_by_hash = {
            stable_json_hash(event): event
            for event in [*cached_events, *[event for event in events if isinstance(event, dict)]]
        }
        pages_by_url = {
            str(page.get("url")): page
            for page in cached_pages
            if page.get("url")
        }
        pages_by_url[url] = {
            "url": url,
            "cached_at_iso": utc_now_iso(),
            "event_count": len(events),
            "next_page_timestamp": payload.get("nextPageTimestamp"),
        }

        merged_events = sorted(
            merged_by_hash.values(),
            key=lambda event: (
                local_gcd.to_number(event.get("timestamp")) or 0,
                local_gcd.to_int(event.get("packetID")) or 0,
                str(event.get("type") or ""),
            ),
        )
        self.write_fflogs_payload(
            "xivanalysis_proxy_events",
            candidate,
            {
                "source": "xivanalysis_proxy_fflogs_v1",
                "events": merged_events,
                "pages": sorted(pages_by_url.values(), key=lambda page: str(page.get("url") or "")),
            },
        )

    def read_report_fight(self, candidate: local_gcd.GcdCandidate) -> dict[str, Any] | None:
        """從頁面載入時攔截到的 FFLogs v1 fight list 找回單場 fight。

        排行榜分片只保存前端與資料建置必要欄位；xivanalysis 的 legacy
        FFLogs adapter 會使用 `combatTime` 決定 ABC pull 起點與分母。把這份
        metadata 快取起來後，修正演算法時就能重用同一批外站資料離線重算。
        """
        payload = self.read_fflogs_payload("report_fights", candidate)
        if not isinstance(payload, dict):
            return None

        data = payload.get("data")
        if isinstance(data, dict):
            payload = data

        fights = payload.get("fights")
        if not isinstance(fights, list):
            return None

        fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
        if fight_id is None:
            return None

        exact_fight: dict[str, Any] | None = None
        for fight in fights:
            if not isinstance(fight, dict):
                continue
            if self._cached_fight_id(fight) == fight_id:
                exact_fight = fight
                break

        best_fight = self.find_report_fight_by_id(candidate.report_code, fight_id)
        if best_fight and (
            exact_fight is None
            or (self._fight_has_players(best_fight) and not self._fight_has_players(exact_fight))
        ):
            return best_fight
        return exact_fight

    def read_xivanalysis_result(self, candidate: local_gcd.GcdCandidate) -> dict[str, Any] | None:
        cached = read_json_if_exists(self._xivanalysis_path(candidate))
        if not cached or cached.get("schema_version") != 1:
            return None
        percent = local_gcd.to_number(cached.get("percent"))
        if percent is None:
            return None
        cached["percent"] = percent
        return cached

    def write_xivanalysis_result(self, candidate: local_gcd.GcdCandidate, *, percent: float, url: str) -> None:
        write_json_atomic(
            self._xivanalysis_path(candidate),
            {
                "schema_version": 1,
                "kind": "xivanalysis_gcd_percent",
                "identity": player_cache_identity(candidate),
                "cached_at_iso": utc_now_iso(),
                "percent": round(percent, 2),
                "url": url,
                "source": XIVANALYSIS_GCD_SOURCE,
            },
        )


def normalize_page_text(text: str) -> str:
    return re.sub(r"[ \t\r\f\v\u00a0]+", " ", text).strip()


def parse_xivanalysis_gcd_percent(text: str) -> float | None:
    normalized = normalize_page_text(text)
    patterns = [
        # 英文畫面：Checklist -> Always be casting -> 98.3%
        r"\bAlways\s+be\s+casting\b\s*[:：]?\s*(?:\n|\s)+(?P<percent>\d{1,3}(?:\.\d+)?)\s*%",
        # 中文或其他語系曾出現的 GCD 覆蓋率文字。
        r"\bGCD\s*(?:Uptime|Coverage|覆蓋率|覆盖率)\b\s*[:：]?\s*(?P<percent>\d{1,3}(?:\.\d+)?)\s*%",
        r"\bGCD\s*(?:Uptime|Coverage|覆蓋率|覆盖率)\b\s*[:：]?\s*(?:\n|\s)+(?P<percent>\d{1,3}(?:\.\d+)?)\s*%",
    ]
    for pattern in patterns:
        match = re.search(pattern, normalized, flags=re.IGNORECASE)
        if not match:
            continue

        percent = float(match.group("percent"))
        if 0 <= percent <= 100:
            return percent
    return None


def is_terminal_xivanalysis_error(text: str) -> bool:
    lowered = text.lower()
    permanent_markers = [
        "this report does not exist or is private",
        "report not found",
        "unsupported patch",
        "unsupported job",
        "no parser available",
    ]
    return any(marker in lowered for marker in permanent_markers)


def is_retryable_xivanalysis_page(text: str) -> bool:
    lowered = text.lower()
    retryable_markers = [
        "modules not found",
        "a new version has probably been deployed",
    ]
    return any(marker in lowered for marker in retryable_markers)


def is_rate_limited_xivanalysis_page(text: str) -> bool:
    lowered = text.lower()
    rate_limit_markers = [
        "slow down",
        "too many requests",
        "please wait a little while",
    ]
    return any(marker in lowered for marker in rate_limit_markers)


def build_xivanalysis_url(candidate: local_gcd.GcdCandidate, base_url: str = XIVANALYSIS_BASE_URL) -> str:
    fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
    source_id = local_gcd.to_int(candidate.player.get("fflogs_id"))
    if fight_id is None or source_id is None:
        raise XivanalysisPermanentError("缺少 fight_id 或玩家 sourceID，無法建立 xivanalysis URL。")
    return f"{base_url.rstrip('/')}/fflogs/{candidate.report_code}/{fight_id}/{source_id}"


def gcd_source_is_current_xivanalysis(player: dict[str, Any]) -> bool:
    coverage = player.get("gcd_coverage")
    if not isinstance(coverage, dict):
        return False
    return (
        coverage.get("source") == XIVANALYSIS_GCD_SOURCE
        and local_gcd.to_int(coverage.get("calculation_version")) == local_gcd.GCD_CALCULATION_VERSION
    )


def collect_candidates(
    encounters: dict[str, dict[str, Any]],
    *,
    force: bool,
) -> tuple[list[local_gcd.GcdCandidate], CandidateScanSummary, dict[str, dict[str, Any]]]:
    candidates: list[local_gcd.GcdCandidate] = []
    rankings_by_key: dict[str, dict[str, Any]] = {}
    total_rankable = 0
    queryable = 0
    missing_key = 0
    null_value = 0
    current_xivanalysis = 0
    no_query_context = 0

    for key, encounter in sorted(encounters.items()):
        if not local_gcd.ranking_path(encounter).exists():
            continue

        ranking = local_gcd.load_ranking_file(encounter)
        rankings_by_key[key] = ranking
        reports = ranking.get("reports") if isinstance(ranking, dict) else {}
        if not isinstance(reports, dict):
            continue

        for fallback_report_code, report in reports.items():
            if not isinstance(report, dict):
                continue

            report_code = str(report.get("report_code") or fallback_report_code)
            for fight in report.get("fights") or []:
                if not isinstance(fight, dict):
                    continue

                for player in fight.get("players") or []:
                    if not isinstance(player, dict) or not local_gcd.player_is_rankable(player):
                        continue

                    total_rankable += 1
                    if not local_gcd.player_has_query_context(fight, player):
                        no_query_context += 1
                        continue

                    queryable += 1
                    if "gcd_coverage" not in player:
                        missing_key += 1
                    elif player.get("gcd_coverage") is None:
                        null_value += 1
                    elif gcd_source_is_current_xivanalysis(player):
                        current_xivanalysis += 1

                    if not force and gcd_source_is_current_xivanalysis(player):
                        continue

                    candidates.append(
                        local_gcd.GcdCandidate(
                            encounter_key=key,
                            encounter=encounter,
                            ranking=ranking,
                            report_code=report_code,
                            report=report,
                            fight=fight,
                            player=player,
                            sort_time=local_gcd.candidate_sort_time(report, fight),
                        )
                    )

    candidates.sort(key=lambda candidate: (candidate.sort_time, candidate.report_code), reverse=True)
    summary = CandidateScanSummary(
        total_rankable=total_rankable,
        queryable=queryable,
        missing_key=missing_key,
        null_value=null_value,
        current_xivanalysis=current_xivanalysis,
        needs_refresh=len(candidates),
        no_query_context=no_query_context,
    )
    return candidates, summary, rankings_by_key


class XivanalysisRateLimitCoordinator:
    """讓多個瀏覽器 worker 共用同一個站端限流冷卻時間。

    xivanalysis 會在站端壓力過高時直接回傳「Slow down」頁面。這不是單一玩家資料失敗，
    而是整個來源暫時拒絕更多請求；如果每個 worker 繼續各自重試，只會延長封鎖時間。
    因此偵測到限流後，所有 worker 都先睡到同一個 resume 時間，再重試原本那一筆候選玩家。
    """

    def __init__(self, *, cooldown_seconds: int, max_pauses: int) -> None:
        self.cooldown_seconds = max(1, cooldown_seconds)
        self.max_pauses = max(0, max_pauses)
        self._condition = threading.Condition()
        self._resume_at = 0.0
        self._pause_count = 0

    @property
    def pause_count(self) -> int:
        with self._condition:
            return self._pause_count

    def wait_if_needed(self) -> None:
        while True:
            with self._condition:
                remaining = self._resume_at - time.monotonic()
                if remaining <= 0:
                    return
            time.sleep(min(remaining, 5.0))

    def record_rate_limit(self) -> bool:
        with self._condition:
            if self.max_pauses and self._pause_count >= self.max_pauses:
                return False

            self._pause_count += 1
            self._resume_at = max(self._resume_at, time.monotonic() + self.cooldown_seconds)
            self._condition.notify_all()
            return True


class XivanalysisPageClient:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_ms: int,
        retries: int,
        headful: bool,
        locale: str,
        worker_id: int | None = None,
        audit_cache: GcdAuditCache | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout_ms = timeout_ms
        self.retries = max(1, retries)
        self.headful = headful
        self.locale = locale
        self.worker_id = worker_id
        self.audit_cache = audit_cache
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._active_candidate: local_gcd.GcdCandidate | None = None

    def __enter__(self) -> "XivanalysisPageClient":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as error:
            raise RuntimeError(
                "缺少 Playwright。請先安裝 Python 套件並執行：python -m playwright install chromium"
            ) from error

        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(headless=not self.headful)
        self._open_context()
        return self

    def _open_context(self) -> None:
        if self._browser is None:
            raise XivanalysisLookupError("Playwright browser 尚未初始化。")
        self._context = self._browser.new_context(
            locale=self.locale,
            user_agent=f"ffxiv-tc-ranking-xivanalysis-gcd/1.0 worker/{self.worker_id or 1}",
        )
        self._context.route("**/*", self._route_request)
        self._page = self._context.new_page()
        self._page.on("response", self._handle_response)

    def _close_context(self) -> None:
        if self._page is not None:
            self._page.close()
            self._page = None
        if self._context is not None:
            self._context.close()
            self._context = None

    def _reset_context(self) -> None:
        # xivanalysis 部署新前端 chunk 時，單一 browser context 可能卡在
        # "Modules not found" 或 React 錯誤狀態；重建 context 能清掉該頁快取與執行狀態。
        self._close_context()
        self._open_context()

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self._close_context()
        if self._browser is not None:
            self._browser.close()
        if self._playwright is not None:
            self._playwright.stop()

    def _route_request(self, route: Any) -> None:
        request = route.request
        url = request.url.lower()
        if (
            request.resource_type in {"image", "font", "media"}
            or "cloudflareinsights" in url
            or "cdn-cgi/rum" in url
            or "sentry.io" in url
        ):
            route.abort()
            return
        route.continue_()

    def _handle_response(self, response: Any) -> None:
        candidate = self._active_candidate
        if candidate is None or self.audit_cache is None:
            return
        url = str(getattr(response, "url", "") or "").lower()
        captures_report_fights = f"report/fights/{candidate.report_code}".lower() in url
        captures_report_events = f"report/events/{candidate.report_code}".lower() in url
        if not captures_report_fights and not captures_report_events:
            return
        try:
            if getattr(response, "status", None) != 200:
                return
            payload = response.json()
            if not isinstance(payload, dict):
                return
            if captures_report_fights:
                self.audit_cache.write_fflogs_payload("report_fights", candidate, payload)
            if captures_report_events:
                self.audit_cache.merge_xivanalysis_proxy_events(
                    candidate,
                    payload,
                    url=str(getattr(response, "url", "") or ""),
                )
        except Exception:
            # 這份 metadata 只是稽核快取；頁面百分比仍是主要目標，快取失敗不應中斷外站驗證。
            return

    def fetch_gcd_percent(self, candidate: local_gcd.GcdCandidate) -> tuple[float, str]:
        url = build_xivanalysis_url(candidate, self.base_url)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
                self._active_candidate = candidate
                return self._fetch_gcd_percent_once(url)
            except XivanalysisPermanentError:
                raise
            except XivanalysisRateLimitError as error:
                last_error = error
                if attempt < self.retries:
                    self._reset_context()
                    time.sleep(60 * attempt)
            except Exception as error:  # noqa: BLE001
                last_error = error
                if attempt < self.retries:
                    self._reset_context()
                    time.sleep(1.5 * attempt)

        if isinstance(last_error, XivanalysisRateLimitError):
            raise last_error
        raise XivanalysisLookupError(f"xivanalysis 頁面讀取失敗：{last_error}") from last_error

    def _fetch_gcd_percent_once(self, url: str) -> tuple[float, str]:
        if self._page is None:
            raise XivanalysisLookupError("Playwright page 尚未初始化。")

        response = self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        if response is not None and response.status == 429:
            raise XivanalysisRateLimitError("xivanalysis 觸發站端限流（HTTP 429）。")

        if GCD_PERCENT_NETWORK_IDLE_TIMEOUT_MS > 0:
            try:
                self._page.wait_for_load_state("networkidle", timeout=GCD_PERCENT_NETWORK_IDLE_TIMEOUT_MS)
            except Exception:
                # xivanalysis 有時會因長輪詢或第三方請求無法進入嚴格 networkidle；這只代表我們
                # 不能用網路閒置當完成訊號，後面的文字穩定檢查仍會負責確認百分比沒有繼續刷新。
                pass

        deadline = time.monotonic() + self.timeout_ms / 1000
        latest_text = ""
        stable_percent: float | None = None
        stable_count = 0
        stable_since_at: float | None = None
        while time.monotonic() < deadline:
            latest_text = self._page.locator("body").inner_text(timeout=5_000)
            percent = parse_xivanalysis_gcd_percent(latest_text)
            if percent is not None:
                now = time.monotonic()
                if stable_percent == percent:
                    stable_count += 1
                else:
                    stable_percent = percent
                    stable_count = 1
                    stable_since_at = now

                # xivanalysis 的報告頁會先載入 FFLogs v1 資料，再由前端模組逐步完成分析。
                # Always Be Casting 的 checklist 有時會在同一頁生命週期內刷新一次；第一個可解析
                # 百分比不一定是最終顯示值。稽核工具需要對齊使用者實際看到的結果，因此同一
                # 百分比必須連續穩定數次，且從該百分比開始穩定後已有一小段 settle 時間，才視
                # 為可採用。若只用「首次看到任意百分比」作為起點，頁面晚到刷新時可能把中間值
                # 誤判成最終值，導致同一 URL 在不同稽核輪次出現 0.1 個百分點的往返差異。
                if (
                    stable_count >= GCD_PERCENT_STABLE_POLLS
                    and stable_since_at is not None
                    and now - stable_since_at >= GCD_PERCENT_SETTLE_SECONDS
                ):
                    return percent, url

            if is_rate_limited_xivanalysis_page(latest_text):
                raise XivanalysisRateLimitError(f"xivanalysis 觸發站端限流：{normalize_page_text(latest_text)[:500]}")

            if is_retryable_xivanalysis_page(latest_text):
                raise XivanalysisLookupError(f"xivanalysis 暫時載入失敗：{normalize_page_text(latest_text)[:500]}")

            if is_terminal_xivanalysis_error(latest_text):
                raise XivanalysisPermanentError(normalize_page_text(latest_text)[:500])

            self._page.wait_for_timeout(500)

        raise XivanalysisLookupError(f"等候 xivanalysis GCD 結果逾時：{normalize_page_text(latest_text)[:500]}")


class LocalGcdFallback:
    def __init__(
        self,
        *,
        audit_cache: GcdAuditCache | None = None,
        refresh_cache: bool = False,
        cache_only: bool = False,
        raw_event_source: str = "graphql",
    ) -> None:
        self.session: Any = None
        self.auth_pool: Any = None
        self.audit_cache = audit_cache
        self.refresh_cache = refresh_cache
        self.cache_only = cache_only
        if raw_event_source not in {"graphql", "xivanalysis-proxy", "auto"}:
            raise ValueError("raw_event_source 必須是 graphql、xivanalysis-proxy 或 auto。")
        self.raw_event_source = raw_event_source
        self.metadata_store: local_gcd.ActionMetadataStore | None = None
        self.status_store: local_gcd.StatusMetadataStore | None = None
        self.unable_to_act_status_ids: set[int] = set()
        self.fight_graph_cache: dict[tuple[str, int, float, float], dict[str, Any]] = {}
        self.fight_raw_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]] = {}
        self.damage_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]] = {}

    def clear_cached_fight_data(self) -> None:
        # 全量 xivanalysis 稽核會逐場重算上千個 report/fight。Action/Status metadata
        # 可以跨場保留，但 FFLogs graph/raw events 只供同一個 fight group 內多位玩家重用；
        # 若跨 group 累積，人工稽核會在跑完全量前耗盡記憶體。
        self.fight_graph_cache.clear()
        self.fight_raw_event_cache.clear()
        self.damage_event_cache.clear()

    @staticmethod
    def _usable_raw_event_payload(payload: Any) -> list[dict[str, Any]] | None:
        if not isinstance(payload, list) or not payload:
            return None
        events = [event for event in payload if isinstance(event, dict)]
        return events or None

    @classmethod
    def _usable_proxy_event_payload(cls, payload: Any) -> list[dict[str, Any]] | None:
        proxy_events = payload.get("events") if isinstance(payload, dict) else None
        return cls._usable_raw_event_payload(proxy_events)

    def _calculation_fight(self, candidate: local_gcd.GcdCandidate) -> dict[str, Any]:
        """回傳只供本次 GCD 計算使用的 fight metadata，不改動排行榜原始物件。"""
        fight = candidate.fight
        if self.audit_cache is None or self.refresh_cache:
            return fight

        cached_fight = self.audit_cache.read_report_fight(candidate)
        if not cached_fight:
            return fight

        merged = dict(fight)
        if "combatTime" in cached_fight and "combatTime" not in merged:
            merged["combatTime"] = cached_fight["combatTime"]
        if "phases" in cached_fight and "phases" not in merged:
            merged["phases"] = cached_fight["phases"]
        if "start_time" not in merged:
            merged["start_time"] = cached_fight.get("start_time")
        if "end_time" not in merged:
            merged["end_time"] = cached_fight.get("end_time")
        if GcdAuditCache._fight_has_players(cached_fight) and not GcdAuditCache._fight_has_players(merged):
            merged["players"] = cached_fight["players"]
        return merged

    def calculate(self, candidate: local_gcd.GcdCandidate) -> dict[str, Any] | None:
        if self.session is None:
            self.session = local_gcd.fflogs.requests.Session()
            self.auth_pool = None if self.cache_only else local_gcd.auth_pool_class(self.session, local_gcd.read_credentials())
            self.metadata_store = local_gcd.ActionMetadataStore()
            self.metadata_store.preload()

        fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
        start_time = local_gcd.first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
        end_time = local_gcd.first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
        if fight_id is None or start_time is None or end_time is None:
            raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法以本地 Casts graph 回退計算。")

        calculation_fight = self._calculation_fight(candidate)
        if self.audit_cache is not None and not self.refresh_cache:
            self.audit_cache.write_report_fight_metadata(candidate, calculation_fight)
        gcd_denominator_ms = local_gcd.gcd_pull_duration_ms(calculation_fight, start_time, end_time)
        gcd_start_time = local_gcd.gcd_core.gcd_pull_start_time_ms(calculation_fight, start_time, end_time)
        cache_key = (candidate.report_code, fight_id, start_time, end_time)
        base_graph = self.fight_graph_cache.get(cache_key)
        if base_graph is None:
            cached_graph = None if self.refresh_cache or self.audit_cache is None else self.audit_cache.read_fflogs_payload(
                "casts_graph",
                candidate,
            )
            if isinstance(cached_graph, dict):
                base_graph = cached_graph
            elif self.cache_only:
                raise RuntimeError(f"FFLogs Casts graph 快取缺漏：{candidate.label}")
            else:
                base_graph = local_gcd.query_fight_casts_graph(self.session, self.auth_pool, candidate)
                if self.audit_cache is not None:
                    self.audit_cache.write_fflogs_payload("casts_graph", candidate, base_graph)
            self.fight_graph_cache[cache_key] = base_graph
        if self.audit_cache is not None and not self.refresh_cache and isinstance(base_graph, dict):
            graph_fight = dict(calculation_fight)
            for source_key, target_key in (
                ("combatTime", "combatTime"),
                ("startTime", "start_time"),
                ("endTime", "end_time"),
                ("phases", "phases"),
            ):
                if base_graph.get(source_key) is not None and graph_fight.get(target_key) is None:
                    graph_fight[target_key] = base_graph.get(source_key)
            self.audit_cache.write_report_fight_metadata(candidate, graph_fight)
        if candidate.encounter_key in local_gcd.MAIN_TARGET_DAMAGE_DOWNTIME_ENCOUNTERS and cache_key not in self.damage_event_cache:
            cached_damage_events = (
                None
                if self.refresh_cache or self.audit_cache is None
                else self.audit_cache.read_fflogs_payload("damage_events", candidate)
            )
            if isinstance(cached_damage_events, list):
                self.damage_event_cache[cache_key] = cached_damage_events
            elif self.cache_only:
                raise RuntimeError(f"FFLogs damage events 快取缺漏：{candidate.label}")
        graph = local_gcd.add_encounter_specific_downtime(
            base_graph,
            session=self.session,
            auth_pool=self.auth_pool,
            candidate=candidate,
            damage_event_cache=self.damage_event_cache,
        )
        if (
            self.audit_cache is not None
            and candidate.encounter_key in local_gcd.MAIN_TARGET_DAMAGE_DOWNTIME_ENCOUNTERS
            and isinstance(self.damage_event_cache.get(cache_key), list)
            and (
                self.refresh_cache
                or not isinstance(
                    self.audit_cache.read_fflogs_payload("damage_events", candidate),
                    list,
                )
            )
        ):
            self.audit_cache.write_fflogs_payload("damage_events", candidate, self.damage_event_cache[cache_key])
        assert self.metadata_store is not None
        job = str(candidate.player.get("job") or "")
        if local_gcd.gcd_core.should_use_raw_events_for_gcd(candidate.encounter_key, job):
            if self.status_store is None:
                self.status_store = local_gcd.StatusMetadataStore()
                self.status_store.preload()
                self.unable_to_act_status_ids = self.status_store.unable_to_act_status_ids()
            raw_events = self.fight_raw_event_cache.get(cache_key)
            if raw_events is None:
                cached_proxy_payload = None
                if (
                    self.raw_event_source in {"xivanalysis-proxy", "auto"}
                    and not self.refresh_cache
                    and self.audit_cache is not None
                ):
                    cached_proxy_payload = self.audit_cache.read_fflogs_payload(
                        "xivanalysis_proxy_events",
                        candidate,
                    )
                    raw_events = self._usable_proxy_event_payload(cached_proxy_payload)

                cached_raw_events = None if self.refresh_cache or self.audit_cache is None else self.audit_cache.read_fflogs_payload(
                    "raw_events",
                    candidate,
                )
                cached_raw_events_payload = self._usable_raw_event_payload(cached_raw_events)
                cached_raw_events_empty = isinstance(cached_raw_events, list) and cached_raw_events_payload is None
                if cached_raw_events_payload is not None and self.raw_event_source in {"graphql", "auto"}:
                    if self.raw_event_source == "graphql" or raw_events is None:
                        raw_events = cached_raw_events_payload
                if (
                    raw_events is None
                    and cached_raw_events_empty
                    and self.audit_cache is not None
                    and not self.refresh_cache
                ):
                    # FFLogs GraphQL 偶爾會把 raw events 查詢結果落成空陣列。這不是
                    # 合法的「本場沒有事件」，而是人工稽核快取缺口；若同場已保存
                    # xivanalysis proxy events，優先沿用該 payload，避免 recompute
                    # 靜默退回 Casts graph 而產生假性算法差異。
                    cached_proxy_payload = self.audit_cache.read_fflogs_payload(
                        "xivanalysis_proxy_events",
                        candidate,
                    )
                    raw_events = self._usable_proxy_event_payload(cached_proxy_payload)
                if raw_events is None and self.raw_event_source == "xivanalysis-proxy":
                    raise RuntimeError(f"xivanalysis proxy raw events 快取缺漏：{candidate.label}")
                if raw_events is not None:
                    pass
                elif self.cache_only:
                    if cached_raw_events_empty:
                        raise RuntimeError(f"FFLogs raw events 快取為空：{candidate.label}")
                    raise RuntimeError(f"FFLogs raw events 快取缺漏：{candidate.label}")
                else:
                    raw_events = local_gcd.query_fight_raw_events(self.session, self.auth_pool, candidate)
                    if self.audit_cache is not None:
                        self.audit_cache.write_fflogs_payload("raw_events", candidate, raw_events)
                self.fight_raw_event_cache[cache_key] = raw_events
            friendly_ids = {
                player_id
                for player_id in (
                    local_gcd.to_int(player.get("fflogs_id"))
                    for player in calculation_fight.get("players") or []
                    if isinstance(player, dict)
                )
                if player_id is not None
            }
            if candidate.encounter_key in local_gcd.RAW_EVENT_GCD_ENCOUNTERS:
                downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=self.unable_to_act_status_ids,
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=not local_gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                        candidate.encounter_key,
                        job,
                    ),
                )
            else:
                downtime_source = graph
            coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                raw_events,
                self.metadata_store,
                encounter_key=candidate.encounter_key,
                source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                job=candidate.player.get("job"),
                fight_start_time=gcd_start_time,
                fight_end_time=end_time,
                fallback_denominator_ms=gcd_denominator_ms,
                downtime_source=downtime_source,
                cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
            )
            if coverage and candidate.encounter_key == "unreal_byakko" and job in local_gcd.gcd_core.TANK_JOBS:
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                main_gap_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=local_gcd.gcd_core.raw_event_downtime_source(
                        graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=set(),
                        metadata_store=self.metadata_store,
                        job=job,
                    ),
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_tank_byakko_coverage(
                    coverage,
                    main_gap_coverage,
                    casts_graph_coverage,
                    job=job,
                )
            if coverage and candidate.encounter_key == "savage_m1s" and job == "Warrior":
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_m1s_warrior_coverage(
                    coverage,
                    casts_graph_coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                )
                coverage = local_gcd.gcd_core.select_savage_warrior_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Paladin"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_PALADIN_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_paladin_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Machinist"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_MACHINIST_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_machinist_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Summoner"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_SUMMONER_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_summoner_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "RedMage"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_REDMAGE_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_red_mage_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Pictomancer"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_PICTOMANCER_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_pictomancer_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Dragoon"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_DRAGOON_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_dragoon_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Ninja"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_NINJA_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_ninja_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Reaper"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_REAPER_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_reaper_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Astrologian"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_ASTROLOGIAN_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_astrologian_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "WhiteMage"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_WHITE_MAGE_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_white_mage_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Scholar"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_SCHOLAR_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_scholar_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Sage"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_SAGE_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_sage_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Monk"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_MONK_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_monk_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Gunbreaker"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_GUNBREAKER_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_gunbreaker_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if (
                coverage
                and job == "Viper"
                and candidate.encounter_key in local_gcd.gcd_core.SAVAGE_VIPER_DISPLAY_EDGE_ENCOUNTERS
            ):
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_viper_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Pictomancer":
                graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=graph,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_pct_byakko_downtime_coverage(
                    coverage,
                    graph_downtime_coverage,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "BlackMage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                raw_downtime_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    downtime_source,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_blm_byakko_coverage(
                    coverage,
                    graph_coverage,
                    raw_downtime_graph_coverage,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "RedMage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_red_mage_byakko_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Astrologian":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_astrologian_byakko_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Sage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_sage_byakko_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Scholar":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_scholar_byakko_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Summoner":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_summoner_byakko_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Reaper":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_reaper_byakko_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "unreal_byakko":
                coverage = local_gcd.gcd_core.select_byakko_display_edge_coverage(
                    coverage,
                    job=job,
                )
            if (
                coverage
                and candidate.encounter_key == "extreme_zoraal_ja"
                and job in {
                    "BlackMage",
                    "Gunbreaker",
                    "Machinist",
                    "Summoner",
                    "RedMage",
                    "Astrologian",
                    "WhiteMage",
                    "Scholar",
                    "Sage",
                    "Samurai",
                    "Reaper",
                    "Dancer",
                    "Monk",
                    "Warrior",
                }
            ):
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                if job == "BlackMage":
                    coverage = local_gcd.gcd_core.select_zoraal_black_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Gunbreaker":
                    coverage = local_gcd.gcd_core.select_zoraal_gunbreaker_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Warrior":
                    coverage = local_gcd.gcd_core.select_zoraal_warrior_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Machinist":
                    coverage = local_gcd.gcd_core.select_zoraal_machinist_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Summoner":
                    coverage = local_gcd.gcd_core.select_zoraal_summoner_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "RedMage":
                    coverage = local_gcd.gcd_core.select_zoraal_red_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Astrologian":
                    coverage = local_gcd.gcd_core.select_zoraal_astrologian_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "WhiteMage":
                    coverage = local_gcd.gcd_core.select_zoraal_white_mage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Scholar":
                    coverage = local_gcd.gcd_core.select_zoraal_scholar_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Sage":
                    coverage = local_gcd.gcd_core.select_zoraal_sage_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Samurai":
                    coverage = local_gcd.gcd_core.select_zoraal_samurai_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Reaper":
                    coverage = local_gcd.gcd_core.select_zoraal_reaper_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Dancer":
                    coverage = local_gcd.gcd_core.select_zoraal_dancer_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                else:
                    coverage = local_gcd.gcd_core.select_zoraal_monk_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
            if coverage and candidate.encounter_key == "savage_m1s" and job == "BlackMage":
                graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=graph,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_savage_m1s_black_mage_coverage(
                    coverage,
                    graph_downtime_coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                )
            if coverage and candidate.encounter_key in {"savage_m2s", "savage_m3s", "savage_m4s"} and job == "BlackMage":
                casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_savage_m2s_black_mage_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    job=job,
                    casts_graph_coverage=casts_graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "BlackMage":
                combined_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=self.unable_to_act_status_ids,
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=True,
                )
                graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=combined_downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_black_mage_coverage(
                    coverage,
                    graph_downtime_coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Paladin":
                raw_targetability_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=self.unable_to_act_status_ids,
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=False,
                )
                raw_targetability_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=raw_targetability_downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_paladin_coverage(
                    raw_targetability_coverage,
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_queen_tank_display_edge_coverage(
                    coverage,
                    job=job,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job in {
                "Bard",
                "Reaper",
                "Sage",
                "Samurai",
                "Summoner",
                "WhiteMage",
            }:
                use_graph_downtime = job in {"Reaper", "Samurai", "Summoner", "WhiteMage"}
                queen_alternate_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=self.unable_to_act_status_ids,
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=use_graph_downtime,
                )
                queen_alternate_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=queen_alternate_downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                if job == "Bard":
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    queen_capped_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=queen_alternate_downtime_source,
                        cap_next_gcd_jobs={job},
                    )
                    coverage = local_gcd.gcd_core.select_queen_bard_coverage(
                        queen_alternate_coverage,
                        coverage,
                        encounter_key=candidate.encounter_key,
                        raw_targetability_capped_coverage=queen_capped_coverage,
                        casts_graph_coverage=graph_coverage,
                    )
                    coverage = local_gcd.gcd_core.select_queen_bard_display_edge_coverage(
                        coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                elif job == "Reaper":
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    coverage = local_gcd.gcd_core.select_queen_reaper_coverage(
                        coverage,
                        queen_alternate_coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                elif job == "Sage":
                    coverage = local_gcd.gcd_core.select_queen_sage_coverage(
                        queen_alternate_coverage,
                        coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Samurai":
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    coverage = local_gcd.gcd_core.select_queen_samurai_coverage(
                        coverage,
                        queen_alternate_coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                elif job == "Summoner":
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    coverage = local_gcd.gcd_core.select_queen_summoner_coverage(
                        coverage,
                        queen_alternate_coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                    coverage = local_gcd.gcd_core.select_queen_summoner_display_edge_coverage(
                        coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                elif job == "WhiteMage":
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    coverage = local_gcd.gcd_core.select_queen_white_mage_coverage(
                        coverage,
                        queen_alternate_coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                    coverage = local_gcd.gcd_core.select_queen_white_mage_display_edge_coverage(
                        coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job in {
                "DarkKnight",
                "Gunbreaker",
                "Warrior",
            }:
                if job == "DarkKnight":
                    raw_targetability_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=self.unable_to_act_status_ids,
                        metadata_store=self.metadata_store,
                        job=job,
                        include_graph_downtime=False,
                    )
                    raw_graph_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=self.unable_to_act_status_ids,
                        metadata_store=self.metadata_store,
                        job=job,
                        include_graph_downtime=True,
                    )
                    raw_graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=raw_graph_downtime_source,
                        cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    raw_targetability_capped_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=raw_targetability_downtime_source,
                        cap_next_gcd_jobs={job},
                    )
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    coverage = local_gcd.gcd_core.select_queen_dark_knight_coverage(
                        coverage,
                        raw_graph_downtime_coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                        raw_targetability_capped_coverage=raw_targetability_capped_coverage,
                    )
                    coverage = local_gcd.gcd_core.select_queen_tank_display_edge_coverage(
                        coverage,
                        job=job,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                elif job == "Gunbreaker":
                    raw_targetability_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=self.unable_to_act_status_ids,
                        metadata_store=self.metadata_store,
                        job=job,
                        include_graph_downtime=False,
                    )
                    raw_graph_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=self.unable_to_act_status_ids,
                        metadata_store=self.metadata_store,
                        job=job,
                        include_graph_downtime=True,
                    )
                    raw_graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=raw_graph_downtime_source,
                        cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    raw_targetability_capped_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=raw_targetability_downtime_source,
                        cap_next_gcd_jobs={job},
                    )
                    casts_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    coverage = local_gcd.gcd_core.select_queen_gunbreaker_coverage(
                        coverage,
                        raw_targetability_capped_coverage,
                        raw_graph_downtime_coverage,
                        casts_graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                    coverage = local_gcd.gcd_core.select_queen_tank_display_edge_coverage(
                        coverage,
                        job=job,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=casts_graph_coverage,
                    )
                elif job == "Warrior":
                    raw_targetability_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=self.unable_to_act_status_ids,
                        metadata_store=self.metadata_store,
                        job=job,
                        include_graph_downtime=False,
                    )
                    raw_targetability_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=raw_targetability_downtime_source,
                        cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    raw_graph_downtime_capped_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=downtime_source,
                        cap_next_gcd_jobs={job},
                    )
                    coverage = local_gcd.gcd_core.select_queen_warrior_coverage(
                        raw_targetability_coverage,
                        coverage,
                        raw_graph_downtime_capped_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                    coverage = local_gcd.gcd_core.select_queen_tank_display_edge_coverage(
                        coverage,
                        job=job,
                        encounter_key=candidate.encounter_key,
                    )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Astrologian":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_astrologian_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_queen_astrologian_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "RedMage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_red_mage_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Scholar":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_scholar_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Monk":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_monk_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_queen_monk_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Dragoon":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                raw_targetability_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=self.unable_to_act_status_ids,
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=False,
                )
                raw_targetability_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=raw_targetability_downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_queen_dragoon_coverage(
                    graph_coverage,
                    raw_targetability_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_queen_dragoon_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "Machinist":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_queen_machinist_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "RedMage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_red_mage_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_red_mage_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "WhiteMage":
                no_unable_to_act_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=set(),
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=not local_gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                        candidate.encounter_key,
                        job,
                    ),
                )
                no_unable_speed_override_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=no_unable_to_act_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    speed_stats_override={
                        "spell_speed": local_gcd.gcd_core.VALIGARMANDA_WHM_LARGE_UNABLE_SPEED_OVERRIDE_SPELL_SPEED,
                    },
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_white_mage_coverage(
                    coverage,
                    graph_coverage,
                    no_unable_speed_override_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Astrologian":
                speed_override_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    speed_stats_override={
                        "spell_speed": local_gcd.gcd_core.VALIGARMANDA_AST_ESTIMATED_SPEED_OVERRIDE_SPELL_SPEED,
                    },
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_astrologian_coverage(
                    coverage,
                    graph_coverage,
                    speed_override_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Dancer":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_dancer_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Samurai":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_samurai_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Viper":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_viper_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Summoner":
                speed_override_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    speed_stats_override={
                        "spell_speed": local_gcd.gcd_core.VALIGARMANDA_SMN_HIGH_UPTIME_SPEED_OVERRIDE_SPELL_SPEED,
                    },
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_summoner_coverage(
                    coverage,
                    graph_coverage,
                    speed_override_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Reaper":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_reaper_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Gunbreaker":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_gunbreaker_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
                    coverage,
                    job=job,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job in {
                "DarkKnight",
                "Paladin",
            }:
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
                    coverage,
                    job=job,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Pictomancer":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                no_unable_to_act_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=set(),
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=not local_gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                        candidate.encounter_key,
                        job,
                    ),
                )
                no_unable_to_act_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=no_unable_to_act_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_pictomancer_coverage(
                    coverage,
                    graph_coverage,
                    no_unable_to_act_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Scholar":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                no_unable_to_act_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    unable_to_act_status_ids=set(),
                    metadata_store=self.metadata_store,
                    job=job,
                    include_graph_downtime=not local_gcd.gcd_core.raw_event_uses_targetability_only_downtime(
                        candidate.encounter_key,
                        job,
                    ),
                )
                no_unable_to_act_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=no_unable_to_act_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_scholar_coverage(
                    coverage,
                    graph_coverage,
                    no_unable_to_act_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "BlackMage":
                moderate_speed_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    speed_stats_override={
                        "spell_speed": local_gcd.gcd_core.VALIGARMANDA_BLM_MODERATE_SPEED_OVERRIDE_SPELL_SPEED,
                    },
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_black_mage_coverage(
                    coverage,
                    graph_coverage,
                    moderate_speed_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Machinist":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_machinist_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "Warrior":
                minimum_speed_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                    downtime_source=downtime_source,
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    speed_stats_override={"skill_speed": local_gcd.gcd_core.SUB_ATTRIBUTE_MINIMUM},
                )
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_warrior_coverage(
                    coverage,
                    minimum_speed_coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_tank_display_edge_coverage(
                    coverage,
                    job=job,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job in {
                "Dancer",
                "Ninja",
                "Pictomancer",
                "Scholar",
                "Viper",
            }:
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                if job == "Dancer":
                    raw_graph_downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                        base_graph,
                        raw_events,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=self.unable_to_act_status_ids,
                        metadata_store=self.metadata_store,
                        job=job,
                        include_graph_downtime=True,
                    )
                    raw_graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=raw_graph_downtime_source,
                        cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                    )
                    coverage = local_gcd.gcd_core.select_queen_dancer_coverage(
                        coverage,
                        graph_coverage,
                        raw_graph_downtime_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Ninja":
                    coverage = local_gcd.gcd_core.select_queen_ninja_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Pictomancer":
                    coverage = local_gcd.gcd_core.select_queen_pictomancer_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                    coverage = local_gcd.gcd_core.select_queen_pictomancer_display_edge_coverage(
                        coverage,
                        encounter_key=candidate.encounter_key,
                        casts_graph_coverage=graph_coverage,
                    )
                elif job == "Scholar":
                    coverage = local_gcd.gcd_core.select_queen_scholar_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
                elif job == "Viper":
                    coverage = local_gcd.gcd_core.select_queen_viper_coverage(
                        coverage,
                        graph_coverage,
                        encounter_key=candidate.encounter_key,
                    )
            if coverage and job == "Bard":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_bard_raw_event_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
                coverage = local_gcd.gcd_core.select_queen_bard_display_edge_coverage(
                    coverage,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if (
                coverage
                and candidate.encounter_key == "extreme_valigarmanda"
                and job in local_gcd.gcd_core.VALIGARMANDA_DISPLAY_EDGE_JOBS
            ):
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_start_time=gcd_start_time,
                    fight_end_time=end_time,
                    fallback_denominator_ms=gcd_denominator_ms,
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_display_edge_coverage(
                    coverage,
                    job=job,
                    encounter_key=candidate.encounter_key,
                    casts_graph_coverage=graph_coverage,
                )
            if coverage:
                base_capped_jobs = local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key)
                if job not in base_capped_jobs and job in {"RedMage", "Summoner", "Machinist", "DarkKnight", "BlackMage", "Viper"}:
                    capped_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=downtime_source,
                        cap_next_gcd_jobs=base_capped_jobs | {job},
                    )
                    if capped_coverage:
                        coverage = dict(coverage)
                        coverage["raw_next_gcd_capped_percent"] = capped_coverage.get("percent")
                        coverage["raw_next_gcd_capped_denominator_ms"] = capped_coverage.get("denominator_ms")
                        # 診斷用：確認少數 instant-heavy 職業的 raw action lock 是否因封包
                        # timestamp 重疊而高估。正式採用仍需由 selector 明確決定。
                if job in base_capped_jobs and job in {"Gunbreaker", "Machinist", "Monk", "Viper"}:
                    uncapped_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                        raw_events,
                        self.metadata_store,
                        encounter_key=candidate.encounter_key,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                        downtime_source=downtime_source,
                        cap_next_gcd_jobs=base_capped_jobs - {job},
                    )
                    if uncapped_coverage:
                        coverage = dict(coverage)
                        coverage["raw_next_gcd_uncapped_percent"] = uncapped_coverage.get("percent")
                        coverage["raw_next_gcd_uncapped_denominator_ms"] = uncapped_coverage.get("denominator_ms")
                        # 反向診斷用：Queen/Valigarmanda/AAC 的 MNK/VPR/MCH/GNB
                        # 有些差異來自是否裁到下一個 GCD。保留 uncapped 派生值，
                        # 後續調 selector 時可直接用快取重算，不需再次讀外站頁面。
                if "casts_graph_percent" not in coverage:
                    graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                        graph,
                        self.metadata_store,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        job=candidate.player.get("job"),
                        fight_start_time=gcd_start_time,
                        fight_end_time=end_time,
                        fallback_denominator_ms=gcd_denominator_ms,
                    )
                    if graph_coverage:
                        coverage = dict(coverage)
                        coverage["casts_graph_percent"] = graph_coverage.get("percent")
                        coverage["casts_graph_denominator_ms"] = graph_coverage.get("denominator_ms")
                        # 人工稽核只保存衍生診斷值；這能快速判斷 mismatch 是 raw-events
                        # downtime / packet 邊界，還是 Casts graph lock 更接近 xivanalysis。
                if coverage and candidate.encounter_key == "unreal_byakko":
                    coverage = local_gcd.gcd_core.select_byakko_display_edge_coverage(
                        coverage,
                        job=job,
                    )
                return coverage

        coverage = local_gcd.calculate_gcd_coverage_from_graph(
            graph,
            self.metadata_store,
            source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
            job=candidate.player.get("job"),
            fight_start_time=gcd_start_time,
            fight_end_time=end_time,
            fallback_denominator_ms=gcd_denominator_ms,
        )
        if coverage:
            coverage = local_gcd.gcd_core.select_zoraal_sage_graph_coverage(
                coverage,
                encounter_key=candidate.encounter_key,
                job=job,
            )
        return coverage


def apply_xivanalysis_coverage(
    candidate: local_gcd.GcdCandidate,
    *,
    percent: float,
    url: str,
    checked_at_iso: str,
) -> None:
    candidate.player["gcd_coverage"] = {
        "percent": round(percent, 2),
        "calculation_version": local_gcd.GCD_CALCULATION_VERSION,
        "source": XIVANALYSIS_GCD_SOURCE,
        "xivanalysis_url": url,
    }
    candidate.player["gcd_coverage_status"] = {
        "state": "ok",
        "calculation_version": local_gcd.GCD_CALCULATION_VERSION,
        "checked_at_iso": checked_at_iso,
        "source": XIVANALYSIS_GCD_SOURCE,
    }


def apply_fallback_coverage(
    candidate: local_gcd.GcdCandidate,
    coverage: dict[str, Any],
    *,
    checked_at_iso: str,
) -> None:
    local_gcd.apply_coverage(candidate, coverage, checked_at_iso)
    candidate.player["gcd_coverage_status"]["source"] = coverage.get("source")
    candidate.player["gcd_coverage_status"]["fallback_from"] = XIVANALYSIS_GCD_SOURCE


def fetch_xivanalysis_results_sequential(
    selected: list[local_gcd.GcdCandidate],
    *,
    base_url: str,
    timeout_ms: int,
    retries: int,
    headful: bool,
    locale: str,
    delay_ms: int,
    rate_limit_coordinator: XivanalysisRateLimitCoordinator,
    audit_cache: GcdAuditCache | None = None,
) -> Iterator[XivanalysisFetchResult]:
    total = len(selected)
    with XivanalysisPageClient(
        base_url=base_url,
        timeout_ms=timeout_ms,
        retries=retries,
        headful=headful,
        locale=locale,
        worker_id=1,
        audit_cache=audit_cache,
    ) as xivanalysis_client:
        for index, candidate in enumerate(selected, start=1):
            while True:
                rate_limit_coordinator.wait_if_needed()
                try:
                    percent, url = xivanalysis_client.fetch_gcd_percent(candidate)
                    yield XivanalysisFetchResult(
                        index=index,
                        total=total,
                        candidate=candidate,
                        percent=percent,
                        url=url,
                    )
                    break
                except XivanalysisRateLimitError as error:
                    if rate_limit_coordinator.record_rate_limit():
                        print(
                            f"[{index}/{total}] → xivanalysis 站端限流，"
                            f"等待 {rate_limit_coordinator.cooldown_seconds} 秒後重試同一筆：{error}",
                            file=sys.stderr,
                        )
                        continue
                    yield XivanalysisFetchResult(index=index, total=total, candidate=candidate, error=error)
                    break
                except Exception as error:  # noqa: BLE001
                    yield XivanalysisFetchResult(index=index, total=total, candidate=candidate, error=error)
                    break

            if delay_ms > 0:
                time.sleep(delay_ms / 1000)


def fetch_xivanalysis_results_parallel(
    selected: list[local_gcd.GcdCandidate],
    *,
    workers: int,
    base_url: str,
    timeout_ms: int,
    retries: int,
    headful: bool,
    locale: str,
    delay_ms: int,
    rate_limit_coordinator: XivanalysisRateLimitCoordinator,
    audit_cache: GcdAuditCache | None = None,
) -> Iterator[XivanalysisFetchResult]:
    worker_count = max(1, min(workers, len(selected)))
    if worker_count == 1:
        yield from fetch_xivanalysis_results_sequential(
            selected,
            base_url=base_url,
            timeout_ms=timeout_ms,
            retries=retries,
            headful=headful,
            locale=locale,
            delay_ms=delay_ms,
            rate_limit_coordinator=rate_limit_coordinator,
            audit_cache=audit_cache,
        )
        return

    task_queue: queue.Queue[tuple[int, local_gcd.GcdCandidate] | None] = queue.Queue()
    result_queue: queue.Queue[XivanalysisFetchResult | Exception | None] = queue.Queue()
    total = len(selected)
    for index, candidate in enumerate(selected, start=1):
        task_queue.put((index, candidate))
    for _ in range(worker_count):
        task_queue.put(None)

    def worker_loop(worker_id: int) -> None:
        try:
            with XivanalysisPageClient(
                base_url=base_url,
                timeout_ms=timeout_ms,
                retries=retries,
                headful=headful,
                locale=locale,
                worker_id=worker_id,
                audit_cache=audit_cache,
            ) as xivanalysis_client:
                while True:
                    task = task_queue.get()
                    if task is None:
                        result_queue.put(None)
                        return

                    index, candidate = task
                    while True:
                        rate_limit_coordinator.wait_if_needed()
                        try:
                            percent, url = xivanalysis_client.fetch_gcd_percent(candidate)
                            result_queue.put(
                                XivanalysisFetchResult(
                                    index=index,
                                    total=total,
                                    candidate=candidate,
                                    percent=percent,
                                    url=url,
                                )
                            )
                            break
                        except XivanalysisRateLimitError as error:
                            if rate_limit_coordinator.record_rate_limit():
                                print(
                                    f"[{index}/{total}] → xivanalysis 站端限流，"
                                    f"等待 {rate_limit_coordinator.cooldown_seconds} 秒後重試同一筆：{error}",
                                    file=sys.stderr,
                                )
                                continue
                            result_queue.put(
                                XivanalysisFetchResult(index=index, total=total, candidate=candidate, error=error)
                            )
                            break
                        except Exception as error:  # noqa: BLE001
                            result_queue.put(
                                XivanalysisFetchResult(index=index, total=total, candidate=candidate, error=error)
                            )
                            break

                    if delay_ms > 0:
                        time.sleep(delay_ms / 1000)
        except Exception as error:  # noqa: BLE001
            result_queue.put(error)

    threads = [
        threading.Thread(target=worker_loop, args=(worker_id,), daemon=True)
        for worker_id in range(1, worker_count + 1)
    ]
    for thread in threads:
        thread.start()

    results_received = 0
    finished_workers = 0
    try:
        while results_received < total:
            result = result_queue.get()
            if result is None:
                finished_workers += 1
                if finished_workers == worker_count and results_received < total:
                    raise RuntimeError("xivanalysis workers 提前結束，仍有候選玩家尚未處理。")
                continue
            if isinstance(result, Exception):
                raise RuntimeError(f"xivanalysis worker 啟動失敗：{result}") from result

            results_received += 1
            yield result
    finally:
        for thread in threads:
            thread.join(timeout=1)


def flush_changed_rankings(
    changed_encounter_keys: set[str],
    *,
    rankings_by_key: dict[str, dict[str, Any]],
    encounters: dict[str, dict[str, Any]],
) -> None:
    if not changed_encounter_keys:
        return

    for key in sorted(changed_encounter_keys):
        ranking = rankings_by_key.get(key)
        encounter = encounters.get(key)
        if not ranking or not encounter:
            continue
        local_gcd.write_ranking_file(encounter, ranking)
        print(f"已寫入 {key} 的 GCD 覆蓋率更新。")
    changed_encounter_keys.clear()


def parse_args() -> argparse.Namespace:
    default_limit = int(local_gcd.os.environ.get("XIVANALYSIS_GCD_BACKFILL_LIMIT", str(DEFAULT_LIMIT)))
    default_workers = int(local_gcd.os.environ.get("XIVANALYSIS_GCD_WORKERS", str(DEFAULT_WORKERS)))
    parser = argparse.ArgumentParser(description="以 xivanalysis 頁面結果優先重抓 GCD 覆蓋率。")
    parser.add_argument("--limit", type=int, default=default_limit, help="本輪最多更新的玩家筆數。")
    parser.add_argument("--all", action="store_true", help="不套用 limit，會嘗試更新所有候選玩家。")
    parser.add_argument("--force", action="store_true", help="即使已是最新版 xivanalysis GCD 結果也重新抓取。")
    parser.add_argument("--dry-run", action="store_true", help="只列出待更新統計與本輪候選，不開瀏覽器、不寫入。")
    parser.add_argument("--no-fallback", action="store_true", help="xivanalysis 失敗時不回退本地 Casts graph 計算。")
    parser.add_argument("--base-url", default=XIVANALYSIS_BASE_URL, help="xivanalysis base URL。")
    parser.add_argument("--page-timeout-ms", type=int, default=DEFAULT_PAGE_TIMEOUT_MS, help="單頁等待毫秒數。")
    parser.add_argument("--retries", type=int, default=1, help="單筆 xivanalysis 頁面重試次數。")
    parser.add_argument("--delay-ms", type=int, default=DEFAULT_DELAY_MS, help="每筆完成後等待毫秒數，避免壓力過大。")
    parser.add_argument(
        "--rate-limit-cooldown-seconds",
        type=int,
        default=DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS,
        help="遇到 xivanalysis Slow down / Too many requests 後，所有 worker 共同等待的秒數。",
    )
    parser.add_argument(
        "--max-rate-limit-pauses",
        type=int,
        default=DEFAULT_MAX_RATE_LIMIT_PAUSES,
        help="本輪最多接受幾次站端限流冷卻；設為 0 代表不設上限。",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=default_workers,
        help="同時開啟幾個 xivanalysis 瀏覽器 worker；全量重抓建議從 1 開始，過高容易被站端限流。",
    )
    parser.add_argument(
        "--flush-every",
        type=int,
        default=DEFAULT_FLUSH_EVERY,
        help="每成功更新多少位玩家後寫回一次排行榜；設為 0 代表只在結尾寫回。",
    )
    parser.add_argument("--headful", action="store_true", help="以可視 Chromium 執行，方便除錯。")
    parser.add_argument("--locale", default="en-US", help="瀏覽器語系，預設 en-US 以穩定解析 Always be casting。")
    parser.add_argument("--report-code", help="只處理指定 report code，方便驗證單場戰鬥。")
    parser.add_argument("--fight-id", type=int, help="只處理指定 fight id。")
    parser.add_argument("--player-name", help="只處理指定角色名稱。")
    return parser.parse_args()


def candidate_matches_filters(candidate: local_gcd.GcdCandidate, args: argparse.Namespace) -> bool:
    if args.report_code and candidate.report_code != args.report_code:
        return False
    if args.fight_id is not None and local_gcd.to_int(candidate.fight.get("fight_id")) != args.fight_id:
        return False
    if args.player_name:
        name = candidate.player.get("name") or candidate.player.get("character_name")
        if name != args.player_name:
            return False
    return True


def print_candidate_preview(candidates: list[local_gcd.GcdCandidate]) -> None:
    for index, candidate in enumerate(candidates[:20], start=1):
        current = candidate.player.get("gcd_coverage")
        current_percent = current.get("percent") if isinstance(current, dict) else current
        current_source = current.get("source") if isinstance(current, dict) else None
        print(
            f"{index:>2}. {candidate.label} "
            f"current={current_percent if current_percent is not None else '-'} "
            f"source={current_source or '-'}"
        )
    if len(candidates) > 20:
        print(f"... 另有 {len(candidates) - 20} 筆本輪候選。")


def main() -> int:
    args = parse_args()
    encounters = local_gcd.load_all_encounters()
    candidates, summary, rankings_by_key = collect_candidates(encounters, force=args.force)
    candidates = [candidate for candidate in candidates if candidate_matches_filters(candidate, args)]
    selected = candidates if args.all else candidates[: max(args.limit, 0)]

    print(f"可排名玩家筆數：{summary.total_rankable}")
    print(f"可查詢 GCD 的玩家筆數：{summary.queryable}")
    print(f"缺少 gcd_coverage key：{summary.missing_key}")
    print(f"gcd_coverage 已為 null：{summary.null_value}")
    print(f"已是 xivanalysis 來源且版本相符：{summary.current_xivanalysis}")
    print(f"缺少查詢脈絡而略過：{summary.no_query_context}")
    print(f"待以 xivanalysis 更新筆數：{len(candidates)}")
    print(f"本輪選取更新筆數：{len(selected)}")
    print(f"xivanalysis worker 數：{max(1, args.workers)}")
    print(f"xivanalysis 每筆延遲：{max(0, args.delay_ms)} ms")
    print(f"xivanalysis 限流冷卻：{max(1, args.rate_limit_cooldown_seconds)} 秒")
    if args.report_code or args.fight_id is not None or args.player_name:
        print(f"套用篩選後剩餘待更新筆數：{len(candidates)}")
    print_candidate_preview(selected)

    if args.dry_run or not selected:
        return 0

    checked_at_iso = local_gcd.milliseconds_to_iso(time.time() * 1000)
    changed_encounter_keys: set[str] = set()
    inaccessible_reports: dict[str, str] = {}
    audit_cache = GcdAuditCache(DEFAULT_AUDIT_CACHE_DIR)
    fallback = LocalGcdFallback(audit_cache=audit_cache)
    updated_from_xivanalysis = 0
    updated_from_fallback = 0
    marked_null = 0
    failed = 0
    changed_since_flush = 0

    def maybe_flush_changed_rankings() -> None:
        nonlocal changed_since_flush
        if args.flush_every <= 0 or changed_since_flush < args.flush_every:
            return
        flush_changed_rankings(
            changed_encounter_keys,
            rankings_by_key=rankings_by_key,
            encounters=encounters,
        )
        changed_since_flush = 0

    rate_limit_coordinator = XivanalysisRateLimitCoordinator(
        cooldown_seconds=args.rate_limit_cooldown_seconds,
        max_pauses=args.max_rate_limit_pauses,
    )
    xivanalysis_results = fetch_xivanalysis_results_parallel(
        selected,
        workers=max(1, args.workers),
        base_url=args.base_url,
        timeout_ms=max(5_000, args.page_timeout_ms),
        retries=args.retries,
        headful=args.headful,
        locale=args.locale,
        delay_ms=args.delay_ms,
        rate_limit_coordinator=rate_limit_coordinator,
        audit_cache=audit_cache,
    )

    for result in xivanalysis_results:
        candidate = result.candidate
        index = result.index
        total = result.total
        print(f"[{index}/{total}] 更新 GCD 覆蓋率：{candidate.label}")

        if result.error is None:
            assert result.percent is not None and result.url is not None
            apply_xivanalysis_coverage(
                candidate,
                percent=result.percent,
                url=result.url,
                checked_at_iso=checked_at_iso,
            )
            changed_encounter_keys.add(candidate.encounter_key)
            updated_from_xivanalysis += 1
            changed_since_flush += 1
            print(f"[{index}/{total}] → xivanalysis {result.percent:.2f}%")
            maybe_flush_changed_rankings()
            continue

        if candidate.report_code in inaccessible_reports:
            local_gcd.mark_candidate_unavailable(candidate, inaccessible_reports[candidate.report_code], checked_at_iso)
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            changed_since_flush += 1
            print(f"[{index}/{total}] → report 已標記無法存取，寫入 null。")
            maybe_flush_changed_rankings()
            continue

        if isinstance(result.error, XivanalysisPermanentError):
            print(f"[{index}/{total}] → xivanalysis 無法提供結果，嘗試回退本地計算：{result.error}")
        else:
            print(f"[{index}/{total}] → xivanalysis 暫時失敗：{result.error}", file=sys.stderr)

        if args.no_fallback:
            failed += 1
            continue

        try:
            coverage = fallback.calculate(candidate)
        except local_gcd.report_access_error_class:
            reason = "private_or_deleted"
            inaccessible_reports[candidate.report_code] = reason
            local_gcd.mark_candidate_unavailable(candidate, reason, checked_at_iso)
            changed_encounter_keys.add(candidate.encounter_key)
            marked_null += 1
            changed_since_flush += 1
            print(f"[{index}/{total}] → report 已轉為 Private、刪除或無權限，寫入 null。")
            maybe_flush_changed_rankings()
            continue
        except Exception as fallback_error:  # noqa: BLE001
            failed += 1
            print(f"[{index}/{total}] → 本地回退也失敗，保留既有值：{fallback_error}", file=sys.stderr)
            continue

        if not coverage:
            failed += 1
            print(f"[{index}/{total}] → 本地回退無法計算，保留既有值。", file=sys.stderr)
            continue

        apply_fallback_coverage(candidate, coverage, checked_at_iso=checked_at_iso)
        changed_encounter_keys.add(candidate.encounter_key)
        updated_from_fallback += 1
        changed_since_flush += 1
        print(f"[{index}/{total}] → 本地回退 {coverage['percent']:.2f}%")
        maybe_flush_changed_rankings()

    flush_changed_rankings(changed_encounter_keys, rankings_by_key=rankings_by_key, encounters=encounters)

    print(
        "xivanalysis GCD 覆蓋率更新完成："
        f"xivanalysis 成功 {updated_from_xivanalysis} 筆，"
        f"本地回退 {updated_from_fallback} 筆，"
        f"寫入 null {marked_null} 筆，"
        f"暫時失敗 {failed} 筆，"
        f"xivanalysis 限流冷卻 {rate_limit_coordinator.pause_count} 次。"
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
