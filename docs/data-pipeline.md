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
   正式部署會把使用者主檔與個人成績報告細節同步到 users 專用 repo；`public/data/users` 仍是資料建置與驗證的來源產物，不能在 postbuild 前刪除，否則玩家分享頁與 OG 圖會失去本輪最新索引。

   全域公告內容直接維護在 `public/data/announcements.json`；這一步會把它同步到 `public/data/all/announcements.json`，供 hidden delta 檢視流程使用。

3. 驗證資料完整性：

   Honey B. Lovely 粉絲榜是獨立趣味資料；若來源檔已有更新或需要完整建置前同步公開 JSON，先執行：

   ```bash
   npm run build:honey-fans
   ```

   這一步只讀取 `data/fun/honey_b_fans.json` 並輸出 `public/data/fun/honey_b_fans.json`，不呼叫 FFLogs API，也不影響正式排行榜來源資料。

   ```bash
   npm run validate:data
   ```

   這一步會套用 `schemas/public_data_contracts.mjs` 檢查公開 JSON 契約，包含排行榜條目、個人成績單、個人成績報告細節、隊伍榜、伺服器對比與 Honey B. Lovely 粉絲榜資料。

4. 完整建置網站：

   ```bash
   npm run build
   ```

   `npm run build` 會先自動執行 `build:public-rankings`、`build:user-data`、`build:honey-fans` 與 `validate:data`，再由 Vite 建置靜態網站到 `dist/`。
   GitHub Actions 會在 Vite 與 postbuild 完成後執行 `npm run prune:pages-user-data`，只移除 `dist/data/users`、`dist/data/user-entry-details` 與 hidden 使用者差量 JSON，保留玩家分享頁與 OG 圖。資料 commit/push 後、上傳 Pages artifact 前會再執行 `npm run audit:pages-payload:strict -- --write-history data/pages_payload_history.jsonl`，讓 `dist/`、`dist/data/`、`dist/data/all/`、必要時存在的 `dist/data/users/` 與 `dist/og/` 超過 target 時停止部署；稽核通過時會另行提交 payload 趨勢紀錄。

## Honey B. Lovely 粉絲榜

`scripts/fetch_honey_b_fans.py` 與正式排行榜分離，固定使用 `savage_m2s` 的 zone / encounter / difficulty 設定掃描 Honey B. Lovely 粉絲紀錄。它只保存通關與 wipe 場次中進入 `心醉魂迷：奴役` 的衍生資料、已檢查戰鬥狀態與 report 快取，來源檔是 `data/fun/honey_b_fans.json`，公開檔是 `public/data/fun/honey_b_fans.json`。公開 `top_fans`、粉絲列 `records`、`latest_records`、公開 `records` 與本期摘要只計入以來源更新時間為基準的近 7 天紀錄；`latest_records` 最多輸出 5 筆，`latest_fans` 最多輸出 16 筆。歷史紀錄仍留在來源檔，並由建置層計算 `summary.historical_*`、粉絲列 `historical_*` 與 `current_streak_weeks`，供前端顯示歷史統計與連續入榜標示。公開 `team_rankings` 會使用自台灣時間 2026-05-30 00:00:00 起的通關場次，依單場全隊奴役總次數排序，作為 Honey 頁面「超高難度」模式的活動團隊榜資料來源。

抓取新資料：

```bash
npm run fetch:honey-fans
```

這個指令會呼叫 FFLogs API。若只要從既有來源檔重建公開 JSON，使用 `npm run build:honey-fans`，它不會推進正式排行榜掃描點，也不會改動 `data/rankings/` 或 `data/state.json`。

正式 `.github/workflows/update_rankings.yml` 會在 `fetch_fflogs.py` 後執行 `npm run fetch:honey-fans`，預設參數為 `--recent-days 3 --history-limit 200 --recent-window-hours 24 --history-window-hours 24`；對應的 GitHub Variables 是 `HONEY_FANS_RECENT_DAYS`、`HONEY_FANS_HISTORY_LIMIT`、`HONEY_FANS_RECENT_WINDOW_HOURS` 與 `HONEY_FANS_HISTORY_WINDOW_HOURS`。資料建置階段會再執行 `npm run build:honey-fans`，並把 `data/fun/honey_b_fans.json` 與 `public/data/fun/honey_b_fans.json` 一起納入自動資料提交。

## FFLogs 掃描策略

`config/fflogs.json` 預設保守，適合本機一般執行；GitHub Actions 會用同名大寫 `FFLOGS_` 環境變數暫時開啟較完整的排程策略。
`scripts/fflogs_pipeline/graphql_queries.py` 只集中管理 FFLogs GraphQL 查詢字串，實際 OAuth、限流、重試、掃描游標、繁中服玩家判定與寫入流程仍全部由 `scripts/fetch_fflogs.py` 控制。調整查詢欄位時必須確認 `fetch_fflogs.py` 的解析邏輯與 `schemas/public_data_contracts.mjs` 的公開輸出契約仍相容。

| 策略 | 預設脈絡 |
| --- | --- |
| 近期掃描 | `incremental_lookback_hours=24`，讓最近一天的 no-clear / incomplete report 重新深查。 |
| 延遲掃描 | workflow 預設掃 24-72 小時前的 reports，一般只選 state 與排行榜都沒見過的新 report；UCoB 通關規則重判例外會重查需要更新 `clear_rule_revision` 的既有 report。 |
| 歷史補查 | workflow 預設每輪掃 1 個 168 小時視窗，最多選入 600 份深層候選，且同一 zone/difficulty 群組最多 150 份，抓回後來才公開或延後匯出的 logs。 |
| 既有 report 狀態巡檢 | workflow 預設每輪由舊到新檢查固定數量，將不可存取 report 標記 hidden。 |
| 新 report GCD 即時計算 | workflow 預設查同一場 FFLogs `Casts` graph，只保存 GCD 衍生結果。 |
| 站務 report 排除 | `excluded_report_codes` 會讓指定 report 從近期、延遲、歷史、手動補抓、公開重建與既有狀態巡檢排除，避免疑似灌水或其他不採計紀錄重新進入排行榜。 |

重要環境變數：

- `FFLOGS_REPORT_REGION_SCOPE`：淺層 reports 候選地區，專案與 workflow 預設 `all`。
- `FFLOGS_EXCLUDED_REPORT_CODES`：站務排除的 report code 逗號分隔清單；設定檔中的 `excluded_report_codes` 適合保存長期排除，環境變數適合當次維護覆寫。
- `FFLOGS_INCREMENTAL_LOOKBACK_HOURS`：近期完整重查回溯時數，workflow 預設 `24`。
- `FFLOGS_NO_CLEAR_RETRY_HOURS`：`skipped_no_clear` 的近期重試時數，workflow 預設 `24`。
- `FFLOGS_DELAYED_SCAN_ENABLED`、`FFLOGS_DELAYED_SCAN_RECENT_GAP_HOURS`、`FFLOGS_DELAYED_SCAN_LOOKBACK_HOURS`、`FFLOGS_DELAYED_MAX_DEEP_REPORTS_PER_RUN`：控制 24-72 小時延遲掃描與本輪深查上限。
- `FFLOGS_HISTORY_SCAN_ENABLED`、`FFLOGS_HISTORY_SCAN_FULL_RUN`、`FFLOGS_HISTORY_SCAN_WINDOW_HOURS`、`FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN`、`FFLOGS_HISTORY_SCAN_RECENT_GAP_HOURS`、`FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN`、`FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_GROUP_PER_RUN`：控制歷史補查輪巡；workflow 預設 `FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN=1`、`FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN=600`、`FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_GROUP_PER_RUN=150`。
- `FFLOGS_MAX_RUNTIME_SECONDS`、`FFLOGS_RUNTIME_GRACE_SECONDS`：控制 `fetch_fflogs.py` 的可選時間預算；正式 workflow 不設定這組變數，讓所有副本依序推進。人工短時維護若臨時啟用，腳本會在剩餘時間不足時保留 `active_scan` 位置並正常收尾。
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_ENABLED`、`FFLOGS_EXISTING_REPORT_STATUS_CHECK_LIMIT`：控制既有 report 狀態巡檢。
- `FFLOGS_FETCH_GCD_COVERAGE_ENABLED`、`FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN`：控制新 report 落地時的 GCD 即時計算。

單次 `fetch_fflogs.py` 執行內，report code 是深層檢查去重單位；`masterData.actors` 的繁中服玩家判斷會寫入本輪記憶體快取，避免同一 report code 來自不同掃描來源時重複打 FFLogs API。

近期掃描負責最近 24 小時完整重查。`skipped_no_clear` 與 `deferred_incomplete_export` 會在重試窗內被視為未完成，重新進入深層檢查，避免剛上傳但尚未匯出通關 fight 的 report 被舊快取永久擋住。

延遲掃描固定檢查 24-72 小時前的 reports，但使用嚴格已知 report 集合：凡是已在 state 或排行榜出現過的 report 原則上都會略過。這段主要補抓後來才出現在 reports 查詢中的新 report，不重查既有 no-clear 紀錄；唯一例外是 UCoB 通關規則重判，因舊版可能把 `fightPercentage=80` 的通關寫成 `skipped_no_clear`，所以尚未寫入目前 `clear_rule_revision` 的已知 UCoB report 仍會穿透快取重新深查。

歷史補查會從副本的 `history_scan_start_date`、`scan_start_date` 或 `initial_scan_start_date` 開始，依 `data/state.json` 內各副本的 `history_scan_cursor_at` 往後輪巡。一般副本只會把尚未在 state 或排行榜中的 report 選入候選，適合抓回當時未公開、後來改成公開，或 FFLogs 延後完成匯出的更舊 logs。候選先受整輪 `FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN` 限制，再受 `FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_GROUP_PER_RUN` 的 zone/difficulty 分組限制，避免舊絕本同區大量候選讓其它副本長時間沒有深查預算。絕本額外支援通關規則重判：當程式內的 `clear_rule_revision` 更新時，近期、延遲與歷史來源只要看到本次規則版本明確影響的既有絕本 report，都要讓該副本穿透 checked_reports 已處理快取重新深查；目前受影響的是 UCoB。已確認沒有繁中服玩家的 report 不會因通關規則版本重刷，因為通關判斷不會改變 `masterData` 的玩家伺服器。重判完成後會在 `checked_reports` / `processed_reports` 記錄版本，避免同一份 report 每輪都被重刷。若深查上限使本輪候選出現 deferred，`fetch_fflogs.py` 會把 `history_scan_cursor_at` 停在最後一筆已選候選 report 的 `startTime`；若該副本本輪未分到深查額度，游標會停回本輪時間窗起點，避免尚未處理的 report 被推到下一輪全區間輪巡後才重試。

## GCD 覆蓋率

新 report 抓取時，workflow 會在每場 fight 的玩家成績整理完成後，查同一場 FFLogs `Casts` graph，並用 `scripts/gcd_coverage_core.py` 的本地 xivanalysis-like 演算法計算 GCD 覆蓋率。幻白虎 `unreal_byakko`、極永恆女王 `extreme_queen_eternal`、極瓦利加爾曼達 `extreme_valigarmanda`、極佐拉加 `extreme_zoraal_ja` 與 AAC 零式 `savage_m1s` 至 `savage_m4s` 會改查同場 FFLogs `All` raw events，因為 xivanalysis 的 Always Be Casting 需要玩家無法行動狀態、Boss/add targetability 或 raw packet 時序才能精準扣 downtime 與計算 GCD lock。

公式對照 xivanalysis `dawntrail` 分支 `aaa13d4b380f69bf01968c79b78904d9477aa9db`：

- 每次 on-GCD action 的分子貢獻是 `max(有效 castTime, 有效 recastTime)`；若有效 castTime 大於等於當下全域 GCD 基準，會先加 100ms animation lock 再取最大值。戰鬥開場前預唱與戰鬥結束後溢出的 GCD 只計入落在戰鬥時間內的部分。
- 有效 recast 先取 xivanalysis action 定義的 `gcdRecast`，沒有才取 `cooldown`；on-GCD action 若未明列時間，xivanalysis 預設 `castTime=0`、`cooldown=2500`。有 `speedAttribute` 的 action 先套技速/詠速公式，再套 CastTime 模組的 flat 與百分比調整，最後向下取 10ms。
- 技速/詠速公式為 `attribute_multiplier = 1000 - floor(130 * (speed_stat - 420) / 2780)`，`adjusted_duration = floor(attribute_multiplier * base_duration / 1000)`，最後換算成毫秒；FFLogs raw events 缺 `combatantinfo` 時，依 xivanalysis `SpeedStatsAdapterStep` 用 GCD 起點間隔、45ms 分桶與最眾批次附近加權平均反推 tooltip GCD，再轉回副屬性。
- 最終 `percent = gcd_uptime / (fight_duration - downtime) * 100`，前端與稽核都以一位小數顯示值比對。downtime 由玩家 UnableToAct 與敵方 untargetable 視窗合併；分子只在 GCD 結束點落入 downtime 時裁到該 downtime 起點，不扣中途橫跨的短 downtime。

設計重點：

- 只保存 `gcd_coverage` 與 `gcd_coverage_status` 衍生結果，不保存 Casts graph 或 raw events。
- `source=xivanalysis_page` 代表人工稽核工具直接寫回 xivanalysis 頁面顯示值；這類紀錄只保證一位小數百分比與外站一致，會保存 `percent`、`source`、`calculation_version` 與 `xivanalysis_url`，不會偽造本地演算法才有的分母、downtime 或 GCD 次數。
- 同一個 report/fight 優先只查一次整場 `Casts` graph 或 raw events，再於本地依玩家 `sourceID` 切分。
- GraphQL 查詢必須帶 `fightIDs` 與該 fight 的相對 `startTime` / `endTime`。
- 計算會使用 graph downtime 視窗扣除分母；分子則對齊 xivanalysis 的 Always Be Casting 語意，只在 GCD 覆蓋結束點落入 downtime 時裁到 downtime 起點。
- 少數副本的 FFLogs `Casts` graph 不會回傳 downtime 視窗；raw-events 副本會從 raw `targetabilityupdate` 推出所有敵人都不可選取的窗口，並用 `Status.csv` 的 `LockActions/LockControl` 狀態補上玩家 UnableToAct。
- 技能的 GCD 分類與基礎 cast/recast 以 XIVAPI datamining `Action.csv` 為底，腳本只在執行時讀入記憶體，並用 `scripts/xivanalysis_gcd_rules.py` 補上 xivanalysis 也視為 GCD、或 Action.csv 容易把長冷卻誤判成 GCD lock 的例外技能；例如機工士 `Flamethrower` 在 ABC 只給一次 2.5 秒 GCD lock，不能使用 60 秒技能冷卻。
- raw `combatantinfo` 缺少技速/詠速時，會依 xivanalysis `SpeedStatsAdapterStep` 用 GCD 起點間隔、45ms timestamp 分桶、職業/狀態速度修正與 2.50 秒 tooltip GCD 反推副屬性；反推結果即使低於遊戲實際副屬性下限 420，也保留 xivanalysis actorUpdate 的原樣數值。PCT `Inspiration` 與 `Rainbow Bright` 依 xivanalysis PCT 模組套用在指定技能，不當成全域詠速。
- raw events 路徑的下一個 GCD timestamp 裁切預設只套用在武僧與毒蛇；忍者 mudra/ninjutsu 需依 xivanalysis 以固定 lock 累加，不能用下一個 timestamp 裁掉密集結印窗口。副本專屬例外會覆寫這個預設：極永恆女王武僧不裁切、Gunbreaker 需要裁切；極瓦利加爾曼達、極佐拉加與 AAC 零式 MNK/VPR 不裁切。龍騎不做整職業裁切，但 `Dragonsong Dive` 若落在連段循環邊界、下一個 GCD 是 `Raiden Thrust` 等連段起手，會排除該次 LB uptime，以對齊 xivanalysis legacy FFLogs 頁面值。
- `unreal_byakko` 的 PCT 少數低覆蓋率 Starry Muse 窗若 raw targetability 比 Casts graph encounter gap 晚且只影響約一個顯示百分點，會標記 `downtime_selection=casts_graph_encounter_gap` 並使用 graph encounter gap，避免自我 GCD 讓 Boss 不可選取時間被晚扣；中覆蓋率樣本保留 raw targetability，避免 graph gap 過度扣短分母。
- `unreal_byakko` 的 RedMage 低覆蓋率樣本若 raw targetability 比 Casts graph 高約一個百分點，會標記 `fallback_selection=byakko_red_mage_casts_graph_raw_overcount` 回退 graph；若低速反推且 raw/graph 差距約 1.5 個百分點，會標記 `fallback_selection=byakko_red_mage_raw_graph_estimated_speed_blend` 混合兩者。Paladin 低速反推且 raw 比 Casts graph 高約一個百分點時，會標記 `fallback_selection=paladin_byakko_casts_graph_estimated_speed_gap` 回退 graph。黑魔若 raw events 因 Ley Lines / packet 邊界低估 Always Be Casting，且與 Casts graph 差距達 8 個百分點以上，會標記 `fallback_selection=black_mage_casts_graph_large_raw_gap` 並回退到 Casts graph；若 raw action lock 比 Casts graph GCD 嘗試加 raw downtime 高約一到兩個百分點，會標記 `fallback_selection=black_mage_casts_graph_raw_downtime_moderate_raw_overcount`，避免 source combatantinfo / packet 邊界小幅高估；若 raw `combatantinfo` 提供 logging actor 詠速且玩家死亡事件落在 downtime 內，ABC raw lock 會標記 `speed_stat_source=combatantinfo_unadjusted_xivanalysis_raw_lock` 並改用未套副屬性的 lock 長度，對齊 xivanalysis legacy raw-events 頁面值。這些規則只處理已驗證的幻白虎 raw-events 邊界差，不替代一般 raw targetability 規則。
- `unreal_byakko` 的 Bard 若 combatantinfo 可用、raw 已接近滿覆蓋且 Casts graph 為 100%，會標記 `fallback_selection=bard_casts_graph_byakko_high_uptime` 回退 graph；中低覆蓋率仍保留 raw events，避免 Casts graph 高估 Army 排除窗。
- `extreme_queen_eternal` 的 Casts graph downtime 會讓黑魔、舞者、繪靈法師、學者、武僧、武士與少數 Gunbreaker 樣本的分母比 xivanalysis raw-events 路徑更短；這些職業使用 targetability-only 分母。Paladin 在 100 場外站頁面稽核中改回 raw action events 搭配 graph downtime 更接近站端顯示值，因此不列入 targetability-only。Gunbreaker 另因 raw combo packet 會在 downtime-adjacent 間隔重疊加分，Machinist 則會在少數 Hypercharge/短 GCD raw packet 重疊樣本高估，兩者需把 GCD lock 裁到下一個 GCD timestamp。RedMage 會先計算 raw events 再由 selector 保守回 graph；只有低覆蓋率且 raw 只比 graph 高約一到兩個百分點時，才標記 `fallback_selection=queen_red_mage_raw_events_low_graph_uptime` 並使用 raw events，避免 Queen raw events 在其他 Dualcast/instant GCD 視窗高估 ABC。
- `extreme_valigarmanda` 的 Casts graph 會漏掉多段短暫 targetability / 玩家 UnableToAct downtime；固定 seed 稽核的大多數職業在 raw events 分母下對齊 xivanalysis。100 場外站頁面稽核顯示 AST 也應回到 raw events；MNK/VPR 走 raw events 但不裁到下一個 GCD，避免少算 Perfect Balance 與轉化後 GCD lock；低覆蓋率 RDM 若 raw events 比 Casts graph 高約一到兩個百分點，會標記 `fallback_selection=valigarmanda_red_mage_casts_graph_low_uptime` 回退 graph；BlackMage 若 raw events 只比 Casts graph 高約半到一個百分點，會標記 `fallback_selection=valigarmanda_black_mage_casts_graph_raw_overcount` 回退 graph；Summoner 缺 combatantinfo 且中低覆蓋率 raw 只比 graph 高約一個百分點時，會標記 `fallback_selection=valigarmanda_summoner_casts_graph_estimated_speed_gap` 回退 graph。
- `extreme_zoraal_ja` 與 `savage_m1s` 至 `savage_m4s` 的 Casts graph 會讓部分 SAM/PCT/VPR 的 instant 或長鎖 GCD 累加過寬；固定 seed 稽核的差異樣本改用 All raw events 後會回到 xivanalysis 顯示值，因此這些副本預設使用 raw events。這些副本的 MNK/VPR raw events 不裁到下一個 GCD，保留 Perfect Balance 與毒蛇轉化窗口的站端累加語意。例外需限縮在已驗證職業：`extreme_zoraal_ja` 的 Sage 保留 Casts graph；AAC M2S-M4S 的 BlackMage 也回到 Casts graph，避免 Ley Lines / instant packet 邊界讓 raw 分子偏高；AAC M3S-M4S 的 Scholar 同樣保留 Casts graph；AAC M1S 的 BlackMage 使用 raw action events 搭配 graph downtime，標記 `fallback_selection=m1s_black_mage_raw_events_graph_downtime`；Bard 的小比例 graph blend 只套中高覆蓋率樣本，低覆蓋率保留 raw events；若缺 `combatantinfo` 且反推副屬性低於 420，只有接近滿覆蓋時才回退 graph，其餘保留 raw events，避免 graph blend 高估 Army 窗口後的 ABC。

逐批補齊既有歷史資料：

```bash
npm run backfill:gcd -- --dry-run
npm run backfill:gcd
npm run backfill:gcd:reports -- --dry-run
```

`backfill_gcd_coverage.py` 預設依玩家筆數逐批補齊，適合人工追平或抽樣重算。若帶 `--report-limit 50`，則改以 FFLogs report code 為單位，將同一份 report 內所有待更新玩家一起補齊，避免留下半套 GCD 結果。

GitHub Actions 會執行 `python scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 50`，從固定切點往更舊 report 逐輪追平既有 GCD。第一次正式執行時若未設定 `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`，腳本會把當下時間寫入 `data/state.json` 的 `gcd_report_backfill.cutoff_sort_time`；每輪完成後再把本輪最舊 report 的排序時間與 report code 寫入 `cursor_sort_time` / `cursor_report_code`，下一輪從該位置繼續往舊推進。`gcd_report_backfill.calculation_version` 會記錄本輪使用的 GCD 演算法版本；若 state 缺少版本或版本落後目前 `GCD_CALCULATION_VERSION`，腳本會保留固定切點但將 cursor 重設回 cutoff，避免新版重算被上一版已走到底的舊游標略過。

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

若要抽樣驗證本地計算與 xivanalysis 畫面值，可執行：

```bash
npm run audit:gcd:xivanalysis
```

`audit:gcd:xivanalysis` 預設會以固定 seed 對零式、極、幻的每個副本各抽樣 10 場戰鬥，並檢查戰鬥內所有玩家的 Always be casting 百分比。若某個副本的 10 場樣本沒有涵蓋全職業，腳本會再從同副本補抽能覆蓋缺漏職業的戰鬥；若資料內完全找不到某職業，則在 JSON 報告的 `job_coverage_by_encounter[].unavailable_jobs` 留下交接線索。這個流程會開啟 Playwright 並存取 xivanalysis 與 FFLogs，遇到 `Modules not found` 會重建 browser context 並於主巡檢後集中重試 error 玩家；遇到站端 `Slow down / Too many requests` 限流時應降低抽樣數或拉長 `--delay-ms`，且不得放入 GitHub Actions 預設流程。

100 場外站頁面稽核建議使用 `--sample-size 100 --local-mode stored --tolerance 0` 檢查已寫入資料是否與 xivanalysis 顯示值完全相同；若要先用頁面值校準抽樣資料，可加 `--apply --apply-all-checked`，完成後必須重跑 `python scripts/fetch_fflogs.py --rebuild-public`、`npm run build:user-data` 與 no-apply 驗證。`--workers` 可平行讀取頁面，但過高容易觸發站端限流；`--abort-on-fetch-error` 只會在 private/deleted 等永久錯誤時中止，`--exclude-report-codes` 可排除目前已無法由 xivanalysis 存取的 report 並自動補抽同副本其他戰鬥。最新 100 場 stored no-apply 稽核已輸出至 `docs/gcd_xivanalysis_audit_100_latest.json`，涵蓋極本 3 個、零式 4 個、幻本 1 個副本，共 800 場、6416 位玩家，結果為 `matched=6416`、`mismatched=0`、`errors=0`；零式抽樣排除了已無法由 xivanalysis 存取的 `3Pw7nFAjh1Q2caKW` 與 `z4daK1LTRFjJA67G`，並由抽樣器補足每個零式副本 100 場。

## 手動補抓 report

可以透過 `config/fflogs.json` 控制手動補抓：

- `retry_report_codes`：在一般掃描中強制重抓指定 report code。
- `only_report_codes`：只處理指定 report code，不推進掃描進度。
- `excluded_report_codes`：站務判定不採計的 report code；排除清單優先於重抓與手動指定，只有確認可重新採計時才移除。

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

壓縮 `data/state.json` 中已由 `checked_reports` 保留的重複 checkpoint 與 JSON 空白時，先預覽再正式執行：

```bash
npm run compact:state -- --dry-run
npm run compact:state
```

這個指令只移除和 `checked_reports` 完全相同的 `processed_reports` 重複紀錄，並把狀態檔改寫為無縮排 JSON；`checked_reports` 仍保留 report 狀態，避免破壞掃描略過依據。GitHub Actions 會在資料 commit 前執行 `npm run compact:state -- --max-bytes 104857600`，若壓縮後仍超過 GitHub 100 MiB 單檔限制，就會在 commit/push 前提早失敗並提示需要調整 state 保留策略。
