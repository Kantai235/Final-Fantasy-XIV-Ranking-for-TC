# 設定檔說明

`.env` 只放敏感資訊，例如 FFLogs OAuth client ID / secret，並且不要提交實際值。

非敏感設定集中在這個目錄：

- `encounters.json`：副本名稱、FFLogs ID、啟用狀態與起掃日期。
- `fflogs.json`：FFLogs 爬蟲的掃描、限流、重試與手動補抓參數。
- `site.json`：正式站台網址、Vite base path 與本機開發/預覽允許的 host。Cloudflare 規則腳本也會以 `site_url` 推導預設 hostname。

## `encounters.json` 的判讀重點

- `key` 是歷史資料檔名與狀態索引，已存在後不可任意改名或刪除。
- `enabled` 只控制下一輪 Python 爬蟲是否掃描該副本，不代表前端是否顯示該副本。
- 前端實際讀取的是 `public/data/encounters.json`。只要某副本已有 `data/rankings/` 或 `public/data/rankings/` 歷史資料，即使 `enabled=false`，公開清單仍會保留它，避免既有排行榜與個人成績單消失。
- 新增副本時先確認 `zone_id`、`encounter_id`、`difficulty` 與 `scan_start_date`，再執行資料更新流程。

## `fflogs.json` 的判讀重點

- `report_page_limit`、`report_max_pages`、`report_region_scope` 與 `scan_window_hours` 控制淺層 reports 掃描範圍；專案預設 `report_region_scope=all`，保留全部地區候選，後續仍會用繁中服伺服器名稱做深層過濾。若短期維護需要降低掃描量，可暫時改成 `china` 只把中國區域 report 放入候選。報告太多時 `fetch_fflogs.py` 會自動切半查詢。
- `history_scan_enabled`、`history_scan_window_hours`、`history_scan_windows_per_run`、`history_scan_recent_gap_hours` 與 `history_max_deep_reports_per_run` 控制歷史補查。專案預設在 `config/fflogs.json` 關閉，GitHub Actions 會用同名大寫 `FFLOGS_` 環境變數暫時開啟低量巡檢，避免本機一般執行時額外掃描舊時間窗。
- `fetch_gcd_coverage_enabled` 與 `fetch_gcd_coverage_max_fights_per_run` 控制新 report 落地時是否即時計算 GCD 覆蓋率，以及每輪最多查幾場 fight 的 Casts graph。專案預設關閉，GitHub Actions 會用 `FFLOGS_FETCH_GCD_COVERAGE_ENABLED=true` 與 `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN=500` 開啟。
- `rate_limit_requests`、`rate_limit_window_seconds`、`rate_limit_padding_seconds` 與 `rate_limited_cooldown_seconds` 控制 FFLogs API 限流與多憑證輪替。
- `player_stats_batch_size` 控制同一份 report、同一副本內一次 GraphQL request 會合併查詢幾場通關戰鬥的 playerDetails / damageDone；每場 fight 仍用獨立 alias 查詢，避免多場戰鬥的輸出數值被 FFLogs 聚合。
- `retry_report_codes` 會在一般掃描中強制重抓指定 report code。
- `only_report_codes` 只處理指定 report code，且不推進掃描點，適合手動補抓或除錯。
- 手動補抓完成後應清空 `retry_report_codes` 與 `only_report_codes`，避免排程重複處理同一批 report。
- 所有 `fflogs.json` 非敏感執行設定都可用 `FFLOGS_{設定名稱大寫}` 環境變數暫時覆寫，例如 `FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN=2`。環境變數只影響當次執行，不會改寫設定檔。
