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

- `report_page_limit`、`report_max_pages` 與 `scan_window_hours` 控制淺層 reports 掃描範圍；報告太多時 `fetch_fflogs.py` 會自動切半查詢。
- `rate_limit_requests`、`rate_limit_window_seconds`、`rate_limit_padding_seconds` 與 `rate_limited_cooldown_seconds` 控制 FFLogs API 限流與多憑證輪替。
- `player_stats_batch_size` 控制同一份 report、同一副本內一次 GraphQL request 會合併查詢幾場通關戰鬥的 playerDetails / damageDone；每場 fight 仍用獨立 alias 查詢，避免多場戰鬥的輸出數值被 FFLogs 聚合。
- `retry_report_codes` 會在一般掃描中強制重抓指定 report code。
- `only_report_codes` 只處理指定 report code，且不推進掃描點，適合手動補抓或除錯。
- 手動補抓完成後應清空 `retry_report_codes` 與 `only_report_codes`，避免排程重複處理同一批 report。
