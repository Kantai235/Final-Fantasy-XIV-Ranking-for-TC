# 設定檔說明

`.env` 只放敏感資訊，例如 FFLogs OAuth client ID / secret，並且不要提交實際值。

非敏感設定集中在這個目錄：

- `encounters.json`：副本名稱、FFLogs ID、啟用狀態、目前高難標記、個人成績簡表版本與起掃日期。
- `game_versions.json`：繁中服競技版本的更新切點；資料建置層依通關紀錄時間寫入個人成績單的 `game_version`，供使用者選擇顯示或隱藏。
- `fflogs.json`：FFLogs 爬蟲的掃描、限流、重試與手動補抓參數。
- `site.json`：正式站台網址、Vite base path 與本機開發/預覽允許的 host。Cloudflare 規則腳本也會以 `site_url` 推導預設 hostname。

## `encounters.json` 的判讀重點

- `key` 是歷史資料檔名與狀態索引，已存在後不可任意改名或刪除。
- `enabled` 只控制下一輪 Python 爬蟲是否掃描該副本，不代表前端是否顯示該副本。
- 前端實際讀取的是 `public/data/encounters.json`。只要某副本已有 `data/rankings/` 或 `public/data/rankings/` 歷史資料，即使 `enabled=false`，公開清單仍會保留它，避免既有排行榜與個人成績單消失。
- `current_high_end=true` 是個人成績單「簡表模式」的目前高難標記；所有 `category="絕"` 與 `category="極"` 副本固定列入，其他副本僅在此欄位為 `true` 時列入。它和 `enabled` 的掃描語意無關，公開清單會保留此欄位供前端判定。
- `profile_summary_available_from` 是副本首次出現在個人成績簡表的繁中服遊戲版本；`profile_summary_available_until` 為選填，表示輪替內容最後可見的版本。兩者只控制簡表版本快照的可見範圍，不能取代 `scan_start_date` 或影響 Python 掃描。版本交界的戰鬥時間上限由前端簡表版本規則集中管理；已公告開放時間的未來版本會在時間到達前維持待開放，時間到達後自動可選，避免把後續戰鬥誤列入舊版。
- 零式必須額外設定 `profile_summary_savage_tier` 的 `key`、`label`、`order` 與 `floor`（1～4）。簡表會列出所選版本中已開放的所有量級，預設選取 `order` 最新者，並可切換查看各量級的第 1～4 層；某量級四層皆為該版本有效通關時，量級按鈕會亮起彩色勾勾。量級按鈕只表示四層完成狀態，量級內各樓層仍保留職業與 PR 顯示。個人成績一般模式的量級踏破徽章不從這個欄位自動衍生，而是固定規則：輕量級為 M1S～M4S、次重量級為 M5S～M8S，且四層皆須有有效版本公開成績；新增未來量級成就時，必須另行在前端成就規則中明確定義。新增次重量級、重量級時只要填入新量級與較大的 `order`，舊量級的歷史排行榜與玩家成績不會被刪除。
- 個人成績「&lt;傳奇&gt;&lt;究極&gt;&lt;完美&gt;&lt;蒼天&gt;&lt;元始&gt;&lt;創世&gt;」稱號同樣使用固定的六絕副本鍵值：巴哈姆特、究極神兵、亞歷山大、幻想龍詩、歐米茄與伊甸。這是歷史全通成就，與零式量級踏破不同，不套用有效版本限制；未來新增絕本也不得自動擴張既有稱號條件。
- 新增副本時先確認 `zone_id`、`encounter_id`、`difficulty` 與 `scan_start_date`，再執行資料更新流程。若 `scan_start_date` 是未來時間，爬蟲會在開放前略過它，公開清單也會等首份排行榜檔案建立後才列出，避免提早顯示空選項或造成讀取 404。輪替下架副本可設定選填的 `scan_end_date`；關閉時間到達後停止新增掃描，但既有排行榜與公開歷史資料仍會保留。
- `ultimate_futures_rewritten` 對應繁中服 2026-05-26 開放的 7.11「絕 伊甸」；FFLogs v2 `worldData.zones` 顯示 Futures Rewritten 的 `zone_id=65`、`encounter_id=1079`、`difficulty=100`。
- `chaotic_cloud_of_darkness` 對應繁中服 2026-06-23 18:00 維護後開放的 7.15「滅 黑暗之雲」；FFLogs 排行榜頁顯示 Alliance Raids (Chaotic) 的 `zone_id=66`、Cloud of Darkness 的 `encounter_id=2061`，本專案沿用非零式高難度的 `difficulty=100`。`scan_start_date` 使用 `2026-06-23T18:00:00+08:00`，避免維護前候選 report 進入新分類掃描窗。
- 7.2 確定於繁中服 2026-07-28 13:00 開放。`extreme_zelenia` 對應 FFLogs Trials II (Extreme) 的 `zone_id=67`、Zelenia `encounter_id=1080`、`difficulty=100`，其 `scan_start_date` 使用 `2026-07-28T13:00:00+08:00`；`savage_m5s` 至 `savage_m8s` 對應 AAC Cruiserweight 的 `zone_id=68`、`encounter_id=97` 至 `100`、`difficulty=101`，並以 `profile_summary_savage_tier.key="cruiserweight"`、`label="次重量級"`、`order=2`、`floor=1` 至 `4` 表示。次重量級因資料收錄排程調整，四層的 `scan_start_date` 統一延至 `2026-08-04T13:00:00+08:00`；這不影響 7.2 的遊戲版本切點或個人成績簡表的量級定義。同一時間 `savage_m1s` 至 `savage_m4s`、`extreme_queen_eternal` 與 `chaotic_cloud_of_darkness` 套用 `version_cutoff` 成為過版資料；`unreal_byakko` 以 `scan_end_date` 停止掃描並以 `profile_summary_available_until="7.15"` 留在歷史快照，新增的 `unreal_suzaku` 則使用 Trials (Unreal) `zone_id=64`、`encounter_id=3010`、`difficulty=100` 與 7.2 起掃時間。

## `game_versions.json` 的判讀重點

- `versions` 必須依 `starts_at_iso` 由舊到新排序；第一筆以 `null` 表示最早已收錄的版本，讓更早的公開戰鬥仍有可追溯標籤。
- `patch` 是穩定的繁中服競技版本鍵值，`label` 是寫入公開個人成績資料的顯示文字。新增版本時必須同時提供已確認的繁中服開放時間；不可依國際服日期或瀏覽器目前時間猜測切點。
- `game_version` 與副本的 `version_cutoff` 完全分離：前者標示紀錄時的技能／裝備環境，後者判定該副本是否已過版。變更此檔後必須重跑 `npm run build:user-data`，讓既有個人成績單重新取得版本欄位。前端開啟版本資料時，個人成績單會依目前選取伺服器的 `game_version` 產生版本選單，並與職業篩選交集；每個選項都是截至該版本的累積快照，最新版本即完整資料，不另設「全部版本」。個別玩家 JSON 由專用資料來源提供；若舊資料尚未同步此欄位，前端只可用相同更新切點與 `recorded_at_iso` 回推版本，並以明確欄位優先。

## `fflogs.json` 的判讀重點

- `report_page_limit`、`report_max_pages`、`report_region_scope`、`scan_window_hours`、`min_scan_window_seconds`、`initial_lookback_hours` 與 `incremental_lookback_hours` 控制近期 reports 掃描範圍；專案預設 `report_region_scope=all`，保留全部地區候選，後續仍會用繁中服伺服器名稱做深層過濾。伺服器白名單位於 `fetch_fflogs.py`，必須完整包含伊弗利特、迦樓羅、利維坦、拉姆、鳳凰、奧汀、巴哈姆特與泰坦；少任何一服都會讓只含該服玩家的公開 report 被誤判為無繁中服玩家。`scan_window_hours=24` 代表 API 查詢會以 24 小時為一段切開；若單一區間報告超過 FFLogs 分頁上限，`fetch_fflogs.py` 會切半查詢到不小於 `min_scan_window_seconds`。第一次沒有 state 時會從 `initial_lookback_hours` 往回掃；之後則用 `incremental_lookback_hours=24` 讓最近一天的 report 保持可重查。若短期維護需要降低掃描量，可暫時改成 `china` 只把中國區域 report 放入候選。
- `no_clear_retry_hours` 控制 `skipped_no_clear` 與尚未完整匯出 report 的近期重試窗。這個值預設 24 小時，讓剛上傳但稍後才匯出 kill 的 report 不會被舊快取永久擋住。
- `delayed_scan_enabled`、`delayed_scan_recent_gap_hours`、`delayed_scan_lookback_hours` 與 `delayed_max_deep_reports_per_run` 控制延遲淺層掃描。GitHub Actions 預設開啟 24-72 小時前的固定區段，一般只把 state 與排行榜都沒見過的新 report 選入深層處理；UCoB 通關規則重判是例外，尚未寫入目前 `clear_rule_revision` 的既有 report 仍需重查。
- `history_scan_enabled`、`history_scan_full_run`、`history_scan_window_hours`、`history_scan_windows_per_run`、`history_scan_recent_gap_hours`、`history_max_deep_reports_per_run` 與 `history_max_deep_reports_per_group_per_run` 控制歷史補查。專案預設在 `config/fflogs.json` 關閉，避免本機一般執行時額外掃描舊時間窗；GitHub Actions 會用同名大寫 `FFLOGS_` 環境變數暫時開啟輪巡，目前 workflow 預設每輪掃 1 個 168 小時視窗，最多選入 600 份深層候選，且同一個 zone/difficulty 群組最多選入 150 份，避免舊絕本同區候選長時間吃滿整輪深查預算。`history_scan_full_run=true` 只適合人工維護時使用，會讓歷史補查忽略每輪視窗數上限。
- `existing_report_status_check_enabled` 與 `existing_report_status_check_limit` 控制既有排行榜 report 狀態巡檢。專案預設關閉，GitHub Actions 預設每輪由舊到新檢查 25 筆副本/report 紀錄，游標保存在 `data/state.json`，跑完後會回到最舊紀錄繼續輪巡。
- `fetch_gcd_coverage_enabled` 與 `fetch_gcd_coverage_max_fights_per_run` 控制新 report 落地時是否即時計算 GCD 覆蓋率，以及每輪最多查幾場 fight 的 Casts graph。專案預設關閉，GitHub Actions 會用 `FFLOGS_FETCH_GCD_COVERAGE_ENABLED=true` 與 `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN=150` 開啟。
- `fight_integrity_check` 是可撤除的暫時性資料品質防護，專門檢查台灣時間 2026-07-28 18:00 後受普攻解析問題影響的 fight。`cutoff_iso` 是時區明確的啟用切點；`hp_ratio_threshold=1.15` 代表全隊對敵方目標造成的傷害嚴格超過其最大生命池總和 15% 時，以 `data_integrity.status="excluded"` 隱藏。`suspected_hp_ratio_threshold=1.14` 代表 1.14 至 1.15 倍的邊界群組會以 `status="suspected"` 隱藏，但不列為高信心排除：極澤蓮尼亞實測此區間 11 場中有 8 場已有 `Attack` 標記，另 3 場漏報標記，且正常未標記的下一個倍率僅 1.120350。`damage_done_summary.exploitDetails` 出現 `guid=7`／`Attack` 時，即使倍率未達 1.14 也會以 `status="suspected"` 隱藏。泛用 `exploit:6` 不參與判定。`excluded_encounter_keys` 用於生命池語意不適用的多階段副本（目前為 `ultimate_bahamut`），避免誤判。`scripts/backfill_fight_integrity.py` 會將彙總敵方承傷、生命池與目標數存在 `.gitignore` 排除的 `data/local-cache/fight-integrity/measurements.json`，讓規則重跑可離線復查；既有 `data_integrity.metrics` 會直接植入快取，來源指紋改變或指定 `--refresh-cache` 才會重新讀取 FFLogs。workflow 以 GitHub Actions cache 接續這份本機快取。停用 `enabled` 或 workflow 的 `FFLOGS_FIGHT_INTEGRITY_ENABLED=false` 只停止新增檢核，既有標記仍會持續從公開產物隱藏。
- `max_runtime_seconds` 與 `runtime_grace_seconds` 控制 `fetch_fflogs.py` 的可選執行時間預算。專案預設 `max_runtime_seconds=0` 代表本機不限制；正式 GitHub Actions 預設使用 `FFLOGS_MAX_RUNTIME_SECONDS=6000` 與 `FFLOGS_RUNTIME_GRACE_SECONDS=900`，並可由 repo variables 覆寫。時間不足或 FFLogs 憑證長時間冷卻時，腳本會保留 `active_scan` 與已落地批次，不會推進未完成副本掃描點，讓後續資料建置與 commit 還有時間完成。
- `request_timeout` 是整體請求逾時；`request_connect_timeout` 與 `request_read_timeout` 可分別覆寫連線與讀取逾時。值為 `null` 時會沿用 `fetch_fflogs.py` 的保守預設，避免單次 FFLogs 連線卡住整輪掃描。`request_retries` 控制暫時性 500/502/503/504、429 與連線逾時的重試次數。
- `rate_limit_requests`、`rate_limit_window_seconds`、`rate_limit_padding_seconds` 與 `rate_limited_cooldown_seconds` 控制 FFLogs API 限流、多憑證輪替與 429 後冷卻。
- `ranking_flush_reports` 控制有效 report 累積幾份後批次寫入排行榜；`state_checkpoint_flush_reports` 控制略過/待重試 checkpoint 與深層掃描 `active_scan.current_report_*` 累積幾筆後批次寫入 `data/state.json`，目前預設 `2000`。首輪全地區回補大量無關 report 時，後者可避免每份 report 都重寫大型 state 檔；人工中斷後則可從最近已落地且已確認安全的 report 切點接續。深層掃描會先整段快轉已處理前綴，避免大量已知 report 逐筆輸出或觸發進度寫入。
- `shallow_scan_cache_enabled` 控制淺層 reports 查詢快取。保留開啟可避免同一輪近期、延遲與歷史補查重複查相同時間窗；若需要診斷 FFLogs 查詢結果，可用環境變數暫時關閉。
- `report_status_cache_limit` 控制 `data/state.json` 內每個副本保留多少筆 `checked_reports` 狀態快取，避免 state 無限制膨脹；它不會刪除 `data/rankings/` 的歷史 report。`data/state.json` 會以緊湊 JSON 寫入；report checkpoint 只需要保留 `processed_at` 毫秒時間，`processed_at_iso` 可由壓縮工具移除後按需重建，避免重複時間字串把 Git blob 撐過 100 MiB。
- `json_write_retries` 與 `json_write_retry_seconds` 控制 JSON 寫入遇到本機檔案鎖定時的重試策略；`ranking_flush_reports` 控制抓取流程累積幾份有效 report 後先批次落地，降低長時間掃描中斷時的資料遺失風險。
- `player_stats_batch_size` 控制同一份 report、同一副本內一次 GraphQL request 會合併查詢幾場通關戰鬥的 playerDetails / damageDone；每場 fight 仍用獨立 alias 查詢，避免多場戰鬥的輸出數值被 FFLogs 聚合。
- `excluded_report_codes` 是站務判定排除的 report code 清單。這些 report 會從近期、延遲、歷史、手動補抓、公開排行榜重建與既有 report 狀態巡檢排除，避免疑似灌水或其他不應採計的成績被排程重新寫回。
- `retry_report_codes` 會在一般掃描中強制重抓指定 report code；若同時出現在 `excluded_report_codes`，排除清單優先。
- `only_report_codes` 只處理指定 report code，且不推進掃描點，適合手動補抓或除錯；若同時出現在 `excluded_report_codes`，排除清單優先。
- 手動補抓完成後應清空 `retry_report_codes` 與 `only_report_codes`，避免排程重複處理同一批 report。`excluded_report_codes` 則只有在站務確認可重新採計時才移除。
- 所有 `fflogs.json` 非敏感執行設定都可用 `FFLOGS_{設定名稱大寫}` 環境變數暫時覆寫，例如 `FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN=2`。環境變數只影響當次執行，不會改寫設定檔。
