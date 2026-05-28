# 資料管線與維護流程

資料管線分成 FFLogs 抓取、公開排行榜重建、使用者資料建置與資料驗證。資料契約細節請先讀 [data-contracts.md](data-contracts.md)。

## 一般更新流程

1. 執行 FFLogs 抓取：

   ```bash
   python scripts/fetch_fflogs.py
   ```

   這一步會讀取 `config/encounters.json` 的啟用副本、掃描 FFLogs reports、篩選繁中服玩家、更新 `data/rankings/*.json`、`data/rankings/*.reports/*.json`、`public/data/rankings/*.json` 與 `data/state.json`。

2. 建置前端統計資料：

   ```bash
   npm run build:user-data
   ```

   這一步會產生 `public/data/users/`、`public/data/user-entry-details/`、`public/data/users/index.json`、`public/data/global_stats.json`、`public/data/activity.json`、`public/data/team_rankings.json` 與 `public/data/server_compare.json`。
   同時會在 `public/data/all/` 產生 hidden delta：有 hidden 成績的個人成績單才輸出差量檔，沒有 hidden 成績的索引項目會直接指回公開成績單。
   指令結束前也會執行 `npm run build:ranking-tables`，由公開排行榜產生 `public/data/ranking-tables/` 薄索引與 `public/data/ranking-details/` 按需載入細節檔，並把 `public/data/all/rankings|ranking-tables|ranking-details` 轉成 hidden delta。

   全域公告內容直接維護在 `public/data/announcements.json`；這一步會把它同步到 `public/data/all/announcements.json`，供 hidden delta 檢視流程使用。

3. 驗證資料完整性：

   ```bash
   npm run validate:data
   ```

   這一步會套用 `schemas/public_data_contracts.mjs` 檢查公開 JSON 契約，包含排行榜條目、個人成績單、個人成績報告細節、隊伍榜與伺服器對比資料。

4. 完整建置網站：

   ```bash
   npm run build
   ```

   `npm run build` 會先自動執行 `build:public-rankings`、`build:user-data` 與 `validate:data`，再由 Vite 建置靜態網站到 `dist/`。
   GitHub Actions 會在資料 commit/push 後、上傳 Pages artifact 前執行 `npm run audit:pages-payload:strict -- --write-history data/pages_payload_history.jsonl`，讓 `dist/`、`dist/data/`、`dist/data/all/`、`dist/data/users/` 與 `dist/og/` 超過 target 時停止部署；稽核通過時會另行提交 payload 趨勢紀錄。

## FFLogs 掃描策略

`config/fflogs.json` 預設保守，適合本機一般執行；GitHub Actions 會用同名大寫 `FFLOGS_` 環境變數暫時開啟較完整的排程策略。
`scripts/fflogs_pipeline/graphql_queries.py` 只集中管理 FFLogs GraphQL 查詢字串，實際 OAuth、限流、重試、掃描游標、繁中服玩家判定與寫入流程仍全部由 `scripts/fetch_fflogs.py` 控制。調整查詢欄位時必須確認 `fetch_fflogs.py` 的解析邏輯與 `schemas/public_data_contracts.mjs` 的公開輸出契約仍相容。

| 策略 | 預設脈絡 |
| --- | --- |
| 近期掃描 | `incremental_lookback_hours=24`，讓最近一天的 no-clear / incomplete report 重新深查。 |
| 延遲掃描 | workflow 預設掃 24-72 小時前的 reports，只選 state 與排行榜都沒見過的新 report。 |
| 歷史補查 | workflow 預設低量輪巡較舊時間窗，抓回後來才公開或延後匯出的 logs。 |
| 既有 report 狀態巡檢 | workflow 預設每輪由舊到新檢查固定數量，將不可存取 report 標記 hidden。 |
| 新 report GCD 即時計算 | workflow 預設查同一場 FFLogs `Casts` graph，只保存 GCD 衍生結果。 |

重要環境變數：

- `FFLOGS_REPORT_REGION_SCOPE`：淺層 reports 候選地區，專案與 workflow 預設 `all`。
- `FFLOGS_INCREMENTAL_LOOKBACK_HOURS`：近期完整重查回溯時數，workflow 預設 `24`。
- `FFLOGS_NO_CLEAR_RETRY_HOURS`：`skipped_no_clear` 的近期重試時數，workflow 預設 `24`。
- `FFLOGS_DELAYED_SCAN_ENABLED`、`FFLOGS_DELAYED_SCAN_RECENT_GAP_HOURS`、`FFLOGS_DELAYED_SCAN_LOOKBACK_HOURS`、`FFLOGS_DELAYED_MAX_DEEP_REPORTS_PER_RUN`：控制 24-72 小時延遲掃描與本輪深查上限。
- `FFLOGS_HISTORY_SCAN_ENABLED`、`FFLOGS_HISTORY_SCAN_FULL_RUN`、`FFLOGS_HISTORY_SCAN_WINDOW_HOURS`、`FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN`、`FFLOGS_HISTORY_SCAN_RECENT_GAP_HOURS`、`FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN`：控制歷史補查輪巡。
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_ENABLED`、`FFLOGS_EXISTING_REPORT_STATUS_CHECK_LIMIT`：控制既有 report 狀態巡檢。
- `FFLOGS_FETCH_GCD_COVERAGE_ENABLED`、`FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN`：控制新 report 落地時的 GCD 即時計算。

單次 `fetch_fflogs.py` 執行內，report code 是深層檢查去重單位；`masterData.actors` 的繁中服玩家判斷會寫入本輪記憶體快取，避免同一 report code 來自不同掃描來源時重複打 FFLogs API。

近期掃描負責最近 24 小時完整重查。`skipped_no_clear` 與 `deferred_incomplete_export` 會在重試窗內被視為未完成，重新進入深層檢查，避免剛上傳但尚未匯出通關 fight 的 report 被舊快取永久擋住。

延遲掃描固定檢查 24-72 小時前的 reports，但使用嚴格已知 report 集合：凡是已在 state 或排行榜出現過的 report 都會略過。這段只補抓後來才出現在 reports 查詢中的新 report，不重查既有 no-clear 紀錄。

歷史補查會從副本的 `history_scan_start_date`、`scan_start_date` 或 `initial_scan_start_date` 開始，依 `data/state.json` 內各副本的 `history_scan_cursor_at` 往後輪巡。一般副本只會把尚未在 state 或排行榜中的 report 選入候選，適合抓回當時未公開、後來改成公開，或 FFLogs 延後完成匯出的更舊 logs。絕本額外支援通關規則重判：當程式內的 `clear_rule_revision` 更新時，歷史補查會把尚未寫入目前版本的既有絕本 report 重新選入深查，重判完成後在 `checked_reports` / `processed_reports` 記錄版本，避免同一份 report 每輪都被重刷。若 `FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN` 使本輪候選出現 deferred，`fetch_fflogs.py` 會把 `history_scan_cursor_at` 停在最後一筆已選候選 report 的 `startTime`；若該副本本輪未分到深查額度，游標會停回本輪時間窗起點，避免尚未處理的 report 被推到下一輪全區間輪巡後才重試。

## GCD 覆蓋率

新 report 抓取時，workflow 會在每場 fight 的玩家成績整理完成後，查同一場 FFLogs `Casts` graph，並用 `scripts/gcd_coverage_core.py` 的本地 xivanalysis-like 演算法計算 GCD 覆蓋率。幻白虎 `unreal_byakko` 會改查同場 FFLogs `All` raw events，因為 xivanalysis 的 Always Be Casting 需要玩家無法行動狀態與 Boss/add targetability 才能精準扣 downtime。

設計重點：

- 只保存 `gcd_coverage` 與 `gcd_coverage_status` 衍生結果，不保存 Casts graph 或 raw events。
- 同一個 report/fight 優先只查一次整場 `Casts` graph 或 raw events，再於本地依玩家 `sourceID` 切分。
- GraphQL 查詢必須帶 `fightIDs` 與該 fight 的相對 `startTime` / `endTime`。
- 計算會使用 graph downtime 視窗同時扣除分母與分子。
- 少數副本的 FFLogs `Casts` graph 不會回傳 downtime 視窗；`unreal_byakko` 會從 raw `targetabilityupdate` 推出所有敵人都不可選取的窗口，並用 `Status.csv` 的 `LockActions/LockControl` 狀態補上玩家 UnableToAct。
- 技能的 GCD 分類與基礎 cast/recast 以 XIVAPI datamining `Action.csv` 為底，腳本只在執行時讀入記憶體，並用小型 allow-list 補上 xivanalysis 也視為 GCD 的例外技能。

逐批補齊既有歷史資料：

```bash
npm run backfill:gcd -- --dry-run
npm run backfill:gcd
npm run backfill:gcd:reports -- --dry-run
```

`backfill_gcd_coverage.py` 預設依玩家筆數逐批補齊，適合人工追平或抽樣重算。若帶 `--report-limit 200`，則改以 FFLogs report code 為單位，將同一份 report 內所有待更新玩家一起補齊，避免留下半套 GCD 結果。

GitHub Actions 會執行 `python scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 200`，從固定切點往更舊 report 逐輪追平既有 GCD。第一次正式執行時若未設定 `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`，腳本會把當下時間寫入 `data/state.json` 的 `gcd_report_backfill.cutoff_sort_time`；每輪完成後再把本輪最舊 report 的排序時間與 report code 寫入 `cursor_sort_time` / `cursor_report_code`，下一輪從該位置繼續往舊推進。

若要在本機把既有玩家 GCD 都以目前本地演算法重新計算：

```bash
npm run backfill:gcd:all
npm run build:user-data
npm run validate:data
```

若只想重算單場：

```bash
npm run backfill:gcd -- --report-code A4cf9kg7Xbmt6vDh --fight-id 3
```

若要針對單場差異追查 raw events 與 Casts graph 的差別，可在單場指令後加上 `--raw-events`。這會即時讀取 FFLogs `All` events、使用 `combatantinfo` 的技速/詠速、狀態視窗與 raw targetability 重算；raw events 仍只在記憶體中使用，不會寫入 repo。

`scripts/backfill_gcd_coverage_xivanalysis.py` 只保留為人工抽樣診斷工具，用來比對 xivanalysis 頁面顯示值；它不是 GitHub Actions 預設流程。

## 手動補抓 report

可以透過 `config/fflogs.json` 控制手動補抓：

- `retry_report_codes`：在一般掃描中強制重抓指定 report code。
- `only_report_codes`：只處理指定 report code，不推進掃描進度。

修改後執行：

```bash
python scripts/fetch_fflogs.py
npm run build:user-data
npm run validate:data
```

處理完成後，建議清空手動補抓欄位，避免下次排程重複處理。重抓既有 report 時，資料管線會以 `data/rankings/{key}.reports/` 的 report/fight/player 明細重新建立 `ranking_entries`，所以可以修正舊扁平索引中的錯誤數值。

## 隱藏 report 狀態檢查

若要一次性排查「仍缺少 `gcd_coverage` key 或 `gcd_coverage: null` 的 report 是否已無法讀取」，先預覽：

```bash
npm run check:gcd-missing-report-status -- --dry-run
```

確認候選後正式執行：

```bash
npm run check:gcd-missing-report-status
```

這個腳本只對沒有可用 GCD 資料的既有 report code 做輕量 report 狀態查詢。若 FFLogs 回報無權限、report 不存在或找不到，會將同一 report code 在所有排行榜來源中標記為 hidden；它不會查 Casts graph，也不會補算 GCD 覆蓋率。

## 壓縮與清理

清理既有 `data/rankings/*.reports/*.json` 裡可重查的大型 FFLogs raw 欄位時，先預覽再正式執行：

```bash
npm run compact:rankings -- --dry-run
npm run compact:rankings
```

這個指令只移除 `fflogs_raw`、`master_data`、`matched_players` 與 fight 層 raw payload，並重新分片；不會刪除 report、fight 或 player 紀錄。

壓縮 `data/state.json` 中已由 `checked_reports` 保留的重複 checkpoint 時，先預覽再正式執行：

```bash
npm run compact:state -- --dry-run
npm run compact:state
```

這個指令只移除和 `checked_reports` 完全相同的 `processed_reports` 重複紀錄；`checked_reports` 仍保留 report 狀態，避免破壞掃描略過依據。
