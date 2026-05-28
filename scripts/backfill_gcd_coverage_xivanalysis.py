from __future__ import annotations

import argparse
import queue
import re
import sys
import threading
import time
from dataclasses import dataclass
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
# 再於瀏覽器內跑 AlwaysBeCasting 模組產生畫面上的百分比。這支腳本刻意只讀取畫面上的
# 衍生結果，不保存 xivanalysis 或 FFLogs raw events，避免把第三方大量資料落地到 repo。
XIVANALYSIS_BASE_URL = "https://xivanalysis.com"
XIVANALYSIS_GCD_SOURCE = "xivanalysis_page"
DEFAULT_LIMIT = 200
DEFAULT_PAGE_TIMEOUT_MS = 90_000
DEFAULT_DELAY_MS = 2_500
DEFAULT_FLUSH_EVERY = 1_000
DEFAULT_WORKERS = 1
DEFAULT_RATE_LIMIT_COOLDOWN_SECONDS = 600
DEFAULT_MAX_RATE_LIMIT_PAUSES = 12


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
    ) -> None:
        self.base_url = base_url
        self.timeout_ms = timeout_ms
        self.retries = max(1, retries)
        self.headful = headful
        self.locale = locale
        self.worker_id = worker_id
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

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

    def fetch_gcd_percent(self, candidate: local_gcd.GcdCandidate) -> tuple[float, str]:
        url = build_xivanalysis_url(candidate, self.base_url)
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 1):
            try:
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

        raise XivanalysisLookupError(f"xivanalysis 頁面讀取失敗：{last_error}") from last_error

    def _fetch_gcd_percent_once(self, url: str) -> tuple[float, str]:
        if self._page is None:
            raise XivanalysisLookupError("Playwright page 尚未初始化。")

        response = self._page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
        if response is not None and response.status == 429:
            raise XivanalysisRateLimitError("xivanalysis 觸發站端限流（HTTP 429）。")

        deadline = time.monotonic() + self.timeout_ms / 1000
        latest_text = ""
        while time.monotonic() < deadline:
            latest_text = self._page.locator("body").inner_text(timeout=5_000)
            percent = parse_xivanalysis_gcd_percent(latest_text)
            if percent is not None:
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
    def __init__(self) -> None:
        self.session: Any = None
        self.auth_pool: Any = None
        self.metadata_store: local_gcd.ActionMetadataStore | None = None
        self.status_store: local_gcd.StatusMetadataStore | None = None
        self.unable_to_act_status_ids: set[int] = set()
        self.fight_graph_cache: dict[tuple[str, int, float, float], dict[str, Any]] = {}
        self.fight_raw_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]] = {}
        self.damage_event_cache: dict[tuple[str, int, float, float], list[dict[str, Any]]] = {}

    def calculate(self, candidate: local_gcd.GcdCandidate) -> dict[str, Any] | None:
        if self.session is None:
            self.session = local_gcd.fflogs.requests.Session()
            self.auth_pool = local_gcd.auth_pool_class(self.session, local_gcd.read_credentials())
            self.metadata_store = local_gcd.ActionMetadataStore()
            self.metadata_store.preload()

        fight_id = local_gcd.to_int(candidate.fight.get("fight_id"))
        start_time = local_gcd.first_number(candidate.fight.get("start_time"), candidate.fight.get("startTime"))
        end_time = local_gcd.first_number(candidate.fight.get("end_time"), candidate.fight.get("endTime"))
        if fight_id is None or start_time is None or end_time is None:
            raise RuntimeError("缺少 fight_id 或 fight 時間窗，無法以本地 Casts graph 回退計算。")

        cache_key = (candidate.report_code, fight_id, start_time, end_time)
        base_graph = self.fight_graph_cache.get(cache_key)
        if base_graph is None:
            base_graph = local_gcd.query_fight_casts_graph(self.session, self.auth_pool, candidate)
            self.fight_graph_cache[cache_key] = base_graph
        graph = local_gcd.add_encounter_specific_downtime(
            base_graph,
            session=self.session,
            auth_pool=self.auth_pool,
            candidate=candidate,
            damage_event_cache=self.damage_event_cache,
        )
        assert self.metadata_store is not None
        job = str(candidate.player.get("job") or "")
        if local_gcd.gcd_core.should_use_raw_events_for_gcd(candidate.encounter_key, job):
            if self.status_store is None:
                self.status_store = local_gcd.StatusMetadataStore()
                self.status_store.preload()
                self.unable_to_act_status_ids = self.status_store.unable_to_act_status_ids()
            raw_events = self.fight_raw_event_cache.get(cache_key)
            if raw_events is None:
                raw_events = local_gcd.query_fight_raw_events(self.session, self.auth_pool, candidate)
                self.fight_raw_event_cache[cache_key] = raw_events
            friendly_ids = {
                player_id
                for player_id in (
                    local_gcd.to_int(player.get("fflogs_id"))
                    for player in candidate.fight.get("players") or []
                    if isinstance(player, dict)
                )
                if player_id is not None
            }
            if candidate.encounter_key in local_gcd.RAW_EVENT_GCD_ENCOUNTERS:
                downtime_source = local_gcd.gcd_core.raw_event_downtime_source(
                    base_graph,
                    raw_events,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    friendly_ids=friendly_ids,
                    fight_start_time=start_time,
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
                fight_end_time=end_time,
                fallback_denominator_ms=local_gcd.first_number(
                    candidate.fight.get("clear_time_ms"),
                    end_time - start_time,
                    candidate.fight.get("damage_time_ms"),
                ),
                downtime_source=downtime_source,
                cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
            )
            if coverage and candidate.encounter_key == "unreal_byakko" and job in local_gcd.gcd_core.TANK_JOBS:
                main_gap_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                    downtime_source=local_gcd.gcd_core.raw_event_downtime_source(
                        graph,
                        raw_events,
                        source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                        friendly_ids=friendly_ids,
                        fight_start_time=start_time,
                        fight_end_time=end_time,
                        unable_to_act_status_ids=set(),
                        metadata_store=self.metadata_store,
                        job=job,
                    ),
                    cap_next_gcd_jobs=local_gcd.gcd_core.raw_next_gcd_capped_jobs_for_encounter(candidate.encounter_key),
                )
                coverage = local_gcd.gcd_core.select_tank_byakko_coverage(coverage, main_gap_coverage)
            if coverage and candidate.encounter_key == "unreal_byakko" and job == "Pictomancer":
                graph_downtime_coverage = local_gcd.calculate_gcd_coverage_from_raw_events(
                    raw_events,
                    self.metadata_store,
                    encounter_key=candidate.encounter_key,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
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
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
                raw_downtime_graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    downtime_source,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
                coverage = local_gcd.gcd_core.select_blm_byakko_coverage(
                    coverage,
                    graph_coverage,
                    raw_downtime_graph_coverage,
                )
            if coverage and candidate.encounter_key == "extreme_queen_eternal" and job == "RedMage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
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
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
                coverage = local_gcd.gcd_core.select_queen_scholar_coverage(
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
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_red_mage_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and candidate.encounter_key == "extreme_valigarmanda" and job == "WhiteMage":
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
                coverage = local_gcd.gcd_core.select_valigarmanda_white_mage_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage and job == "Bard" and candidate.encounter_key in local_gcd.gcd_core.BARD_GRAPH_FALLBACK_ENCOUNTERS:
                graph_coverage = local_gcd.calculate_gcd_coverage_from_graph(
                    graph,
                    self.metadata_store,
                    source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
                    job=candidate.player.get("job"),
                    fight_end_time=end_time,
                    fallback_denominator_ms=local_gcd.first_number(
                        candidate.fight.get("clear_time_ms"),
                        end_time - start_time,
                        candidate.fight.get("damage_time_ms"),
                    ),
                )
                coverage = local_gcd.gcd_core.select_bard_raw_event_coverage(
                    coverage,
                    graph_coverage,
                    encounter_key=candidate.encounter_key,
                )
            if coverage:
                return coverage

        return local_gcd.calculate_gcd_coverage_from_graph(
            graph,
            self.metadata_store,
            source_id=local_gcd.to_int(candidate.player.get("fflogs_id")),
            job=candidate.player.get("job"),
            fight_end_time=end_time,
            fallback_denominator_ms=local_gcd.first_number(
                candidate.fight.get("clear_time_ms"),
                end_time - start_time,
                candidate.fight.get("damage_time_ms"),
            ),
        )


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
) -> Iterator[XivanalysisFetchResult]:
    total = len(selected)
    with XivanalysisPageClient(
        base_url=base_url,
        timeout_ms=timeout_ms,
        retries=retries,
        headful=headful,
        locale=locale,
        worker_id=1,
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
    fallback = LocalGcdFallback()
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
