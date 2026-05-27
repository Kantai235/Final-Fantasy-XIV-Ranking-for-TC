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

- `report_page_limit`、`report_max_pages`、`report_region_scope`、`scan_window_hours`、`min_scan_window_seconds`、`initial_lookback_hours` 與 `incremental_lookback_hours` 控制近期 reports 掃描範圍；專案預設 `report_region_scope=all`，保留全部地區候選，後續仍會用繁中服伺服器名稱做深層過濾。`scan_window_hours=24` 代表 API 查詢會以 24 小時為一段切開；若單一區間報告超過 FFLogs 分頁上限，`fetch_fflogs.py` 會切半查詢到不小於 `min_scan_window_seconds`。第一次沒有 state 時會從 `initial_lookback_hours` 往回掃；之後則用 `incremental_lookback_hours=24` 讓最近一天的 report 保持可重查。若短期維護需要降低掃描量，可暫時改成 `china` 只把中國區域 report 放入候選。
- `no_clear_retry_hours` 控制 `skipped_no_clear` 與尚未完整匯出 report 的近期重試窗。這個值預設 24 小時，讓剛上傳但稍後才匯出 kill 的 report 不會被舊快取永久擋住。
- `delayed_scan_enabled`、`delayed_scan_recent_gap_hours`、`delayed_scan_lookback_hours` 與 `delayed_max_deep_reports_per_run` 控制延遲淺層掃描。GitHub Actions 預設開啟 24-72 小時前的固定區段，只把 state 與排行榜都沒見過的新 report 選入深層處理，不重查既有 report。
- `history_scan_enabled`、`history_scan_full_run`、`history_scan_window_hours`、`history_scan_windows_per_run`、`history_scan_recent_gap_hours` 與 `history_max_deep_reports_per_run` 控制歷史補查。專案預設在 `config/fflogs.json` 關閉，GitHub Actions 會用同名大寫 `FFLOGS_` 環境變數暫時開啟低量巡檢，避免本機一般執行時額外掃描舊時間窗。`history_scan_full_run=true` 只適合人工維護時使用，會讓歷史補查忽略每輪視窗數上限。
- `existing_report_status_check_enabled` 與 `existing_report_status_check_limit` 控制既有排行榜 report 狀態巡檢。專案預設關閉，GitHub Actions 預設每輪由舊到新檢查 200 筆副本/report 紀錄，游標保存在 `data/state.json`，跑完後會回到最舊紀錄繼續輪巡。
- `fetch_gcd_coverage_enabled` 與 `fetch_gcd_coverage_max_fights_per_run` 控制新 report 落地時是否即時計算 GCD 覆蓋率，以及每輪最多查幾場 fight 的 Casts graph。專案預設關閉，GitHub Actions 會用 `FFLOGS_FETCH_GCD_COVERAGE_ENABLED=true` 與 `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN=500` 開啟。
- `request_timeout` 是整體請求逾時；`request_connect_timeout` 與 `request_read_timeout` 可分別覆寫連線與讀取逾時。值為 `null` 時會沿用 `fetch_fflogs.py` 的保守預設，避免單次 FFLogs 連線卡住整輪掃描。`request_retries` 控制暫時性 500/502/503/504、429 與連線逾時的重試次數。
- `rate_limit_requests`、`rate_limit_window_seconds`、`rate_limit_padding_seconds` 與 `rate_limited_cooldown_seconds` 控制 FFLogs API 限流、多憑證輪替與 429 後冷卻。
- `ranking_flush_reports` 控制有效 report 累積幾份後批次寫入排行榜；`state_checkpoint_flush_reports` 控制略過/待重試 checkpoint 與深層掃描 `active_scan.current_report_*` 累積幾筆後批次寫入 `data/state.json`，目前預設 `2000`。首輪全地區回補大量無關 report 時，後者可避免每份 report 都重寫大型 state 檔；人工中斷後則可從最近已落地且已確認安全的 report 切點接續。深層掃描會先整段快轉已處理前綴，避免大量已知 report 逐筆輸出或觸發進度寫入。
- `shallow_scan_cache_enabled` 控制淺層 reports 查詢快取。保留開啟可避免同一輪近期、延遲與歷史補查重複查相同時間窗；若需要診斷 FFLogs 查詢結果，可用環境變數暫時關閉。
- `report_status_cache_limit` 控制 `data/state.json` 內每個副本保留多少筆 `checked_reports` 狀態快取，避免 state 無限制膨脹；它不會刪除 `data/rankings/` 的歷史 report。
- `json_write_retries` 與 `json_write_retry_seconds` 控制 JSON 寫入遇到本機檔案鎖定時的重試策略；`ranking_flush_reports` 控制抓取流程累積幾份有效 report 後先批次落地，降低長時間掃描中斷時的資料遺失風險。
- `player_stats_batch_size` 控制同一份 report、同一副本內一次 GraphQL request 會合併查詢幾場通關戰鬥的 playerDetails / damageDone；每場 fight 仍用獨立 alias 查詢，避免多場戰鬥的輸出數值被 FFLogs 聚合。
- `retry_report_codes` 會在一般掃描中強制重抓指定 report code。
- `only_report_codes` 只處理指定 report code，且不推進掃描點，適合手動補抓或除錯。
- 手動補抓完成後應清空 `retry_report_codes` 與 `only_report_codes`，避免排程重複處理同一批 report。
- 所有 `fflogs.json` 非敏感執行設定都可用 `FFLOGS_{設定名稱大寫}` 環境變數暫時覆寫，例如 `FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN=2`。環境變數只影響當次執行，不會改寫設定檔。
