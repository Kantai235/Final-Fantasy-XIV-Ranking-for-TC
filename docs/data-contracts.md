# 資料契約與歷史資料保護

本文件記錄資料檔的判讀方式與不可破壞的歷史契約。更細的排行榜分片格式請看 [../data/rankings/README.md](../data/rankings/README.md)。

## Append-Only 保護原則

以下資料是不可逆的重要歷史資產：

- `config/encounters.json` 的 encounter key。
- `data/state.json` 的 report 狀態與掃描游標。
- `data/rankings/*.json` 與 `data/rankings/*.reports/*.json` 的 report/fight/player 來源脈絡。

禁止用硬刪、覆寫或改名的方式整理這些資料。若需要同步本機與 GitHub Actions 產物，先執行：

```bash
npm run sync:data -- --dry-run
```

看到 `REMOVAL` 或 `CONFLICT` 時不可自動套用。

## 副本清單

`config/encounters.json` 的欄位：

- `key`：內部識別碼，也會對應資料檔名與網址狀態。建立後不得任意改名。
- `name`：網站顯示名稱。
- `category`：副本分類，例如 `零式`、`極`、`幻`、`滅`、`絕`。
- `zone_id`、`encounter_id`、`difficulty`：FFLogs 查詢用設定。
- `enabled`：是否啟用下一輪 Python 爬蟲掃描。
- `scan_start_date`：首次掃描起始日期。
- `scan_end_date`：選填；輪替下架副本停止新增掃描的時間，既有歷史資料仍會保留。
- `version_cutoff`：版本切點，代表該副本有效版本紀錄的結束時間。
- `profile_summary_available_from`：副本首次出現在個人成績簡表的繁中服遊戲版本；公開副本清單必須保留此欄位，供版本快照隱藏尚未開放的副本。
- `profile_summary_available_until`：選填；輪替內容最後出現在個人成績簡表的遊戲版本。公開副本清單必須保留此欄位，供新版快照移除已關閉的內容而不刪除歷史資料。
- `profile_summary_savage_tier`：僅限 `category="零式"`，包含穩定的量級 `key`、顯示用 `label`、遞增的 `order` 與量級內 1～4 的 `floor`。公開副本清單必須完整保留它，供簡表列出已開放量級、切換量級並排序第 1～4 層。

`enabled` 只控制下一輪 Python 爬蟲是否掃描該副本，不代表前端是否顯示。前端選單來源是 `public/data/encounters.json`；只要副本已有 `data/rankings/` 或 `public/data/rankings/` 歷史資料，即使 `enabled=false`，仍應保留在公開清單中，避免既有排行榜與個人成績單消失。

個人成績簡表的版本選擇採「版本快照」：先用 `profile_summary_available_from` 與選填的 `profile_summary_available_until` 界定副本的可見版本，再以每個版本的下一個繁中服版本開放時間排除之後的 `recorded_at_iso`。因此選擇 7.0 時，極豔翼蛇鳥／極佐拉加會保留至 7.05 開放前，而 7.05 之後的同副本戰鬥不會混入。幻白虎最後可見於 7.15，7.2 改由幻朱雀呈現。7.15 的截止時間是 2026-07-28 12:00（`2026-07-28T04:00:00.000Z`）；7.2 在此時間到達前維持待開放，到達後自動可選。這與 `version_cutoff` 的 valid／obsolete 語意分離：前者是歷史畫面的時間範圍，後者是副本難度是否已過版。

零式在版本快照中會列出全部已開放量級；簡表預設選取 `profile_summary_savage_tier.order` 最大的一組，但可切換至較早量級。因此 7.05 與 7.15 只提供輕量級 1～4；7.2 會同時提供輕量級與次重量級，預設顯示次重量級 1～4（M5S／熱舞綠光、M6S／狂熱糖潮、M7S／野蠻恨心、M8S／劍嚎）。某量級四層皆有該版本有效通關時，該量級按鈕會亮起彩色勾勾；量級內的第 1～4 層仍依一般簡表規則顯示職業與 PR。這只影響簡表呈現，不會刪除舊量級的個人成績或排行歷史。

## 排行榜來源資料

`data/rankings/*.json` 主檔保留：

- `schema_version`
- `encounter`
- `ranking_entries`
- `updated_at_iso`
- `report_shards`

完整 report/fight/player 脈絡保存在同名 `*.reports/*.json` 分片中。當分片存在時，`ranking_entries` 只視為衍生索引；重建排行榜必須以 `reports -> fights -> players` 為權威來源，避免重抓單一 report 後舊扁平索引把錯誤高分帶回來。

新寫入的 report 不保存 `fflogs_raw`、`master_data` 與 `matched_players`。這些大型 raw 欄位可依 report code 重查，停止落地是為避免 Git repo 容量快速膨脹。

## 可執行資料契約

`schemas/public_data_contracts.mjs` 是公開資料的可執行契約來源，裡面同時保留 JSDoc typedef 與驗證用 schema。`npm run validate:data` 會套用這份契約檢查：

- `public/data/rankings/*.json` 的 `ranking_entries`。
- `public/data/ranking-details/*.json` 的按需載入報告細節。
- `public/data/users/index.json` 與每一份 `public/data/users/*.json` 個人成績單。
- `public/data/user-entry-details/*.json` 的個人成績報告分頁細節。
- `public/data/activity.json` 的近期動態、活躍分布與 Logs 趨勢。
- `public/data/team_rankings.json` 的副本、隊伍紀錄與 8 人隊員列。
- `public/data/server_compare.json` 的伺服器列、副本列、職業/職能統計與傷害分位。
- `public/data/report_status_index.json` 的 report code、fight、副本與收錄狀態摘要。
- `public/data/update_status.json` 的最近資料更新與排程摘要。
- `public/data/fun/honey_b_fans.json` 的 Honey B. Lovely 粉絲榜摘要、頭號粉絲、近期紀錄與完整趣味紀錄。

`public/data/all/` 目前是 hidden delta 產物，不再複製所有公開 JSON；delta 檔也有自己的資料契約，驗證時會先與公開底稿合併再檢查完整資料形狀。新增或移除公開 JSON 欄位時，必須同步更新 `schemas/public_data_contracts.mjs`、資料建置腳本與前端讀取端，讓欄位漂移在 `npm test` 或 `npm run validate:data` 階段被抓到。

正式部署時，`public/data/users`、`public/data/user-entry-details`、`public/data/all/users` 與 `public/data/all/user-entry-details` 會先同步到 `Final-Fantasy-XIV-Ranking-for-TC-Users`。Vite/postbuild 仍會讀本 repo 的 `public/data/users/index.json` 供本機抽查或 `FFXIV_TC_BUILD_USER_SHARE_PAGES=true` 時產生玩家分享頁與 OG 圖；正式 workflow 預設關閉逐玩家靜態分享頁，建置完成後再由 `npm run prune:pages-user-data` 移除 `dist/` 內除了 `data/users/index.json` 之外的大型使用者 JSON 與任何被產生的逐玩家分享產物。也就是說，`public/data/users` 仍是 repo 內可驗證的資料契約來源；正式主站 artifact 只把 `data/users/index.json` 當作前端個人成績單搜尋索引，個別玩家主檔與報告細節仍由 users 專用 repo 提供。

`public/data/activity.json` 的 `log_activity` 由 `scripts/build_user_data.mjs` 讀取 `reports -> fights -> players` 產生，不由 Vue 元件即時計算。`unique_report_count` 以 `report_code` 去重，代表 FFLogs 日誌數；`unique_fight_count` 以 `encounter_key + fight_hash` 去重，代表同場多份上傳合併後的通關場次。每日 bucket 使用台灣日期切分，前端只負責依副本、日期範圍與每日座標顯示這些靜態統計；日期範圍的 UI 初始值依響應式模式決定，桌面預設近 90 天，手機預設近 30 天。`log_activity.category_series` 會以零式、極、幻、滅、絕等副本分類預先彙整同樣的每日數量，供近期動態頁在全部副本曲線下方顯示分類堆疊占比。圖表上的台服與國際服改版標註是前端維護的靜態時間軸脈絡，不屬於 `activity.json` 資料契約，也不影響 Logs 或通關場次統計。

`gcd_coverage` 是公開資料中可顯示的衍生結果；除了 `percent`、分母與計算版本，也允許保留小型診斷欄位，例如 `estimated_speed_below_minimum`、`fallback_selection`、`downtime_selection`，以及 raw events、Casts graph、raw targetability fallback 的比較百分比與分母。這些欄位只說明本地演算法為什麼選用某個覆蓋率結果，不保存 FFLogs raw events 或 Casts graph payload，因此符合公開 JSON 的瘦身邊界。

Honey B. Lovely 粉絲榜來源在 `data/fun/honey_b_fans.json`，公開檔在 `public/data/fun/honey_b_fans.json`。它是與正式排行榜分離的趣味資料，只記錄 M2S `心醉魂迷：奴役` 衍生結果與掃描快取，不參與個人成績單、全服統計或 `data/rankings/` 去重規則。公開檔的 `top_fans`、粉絲列 `records`、`latest_records`、公開 `records` 與本期摘要只納入近 7 天；`latest_records` 最多 5 筆，`latest_fans` 最多 16 筆。歷史紀錄留在來源檔，公開檔以 `summary.historical_*` 與粉絲列的 `historical_*` / `current_streak_weeks` 保留歷史追溯與連續入榜語意；`team_rankings` 則使用自台灣時間 2026-05-30 00:00:00 起的通關場次，依同一場戰鬥全隊 `心醉魂迷：奴役` 總次數排序，並沿用戰鬥時間軸去重以合併多份上傳。

## 資料守恆與 payload 預算

`scripts/test_data_conservation.mjs` 是資料瘦身前的守門測試，會檢查：

- `users/index.json` 的 `total_users`、`encounter_count` 與 `public_entry_count` 是否和實際使用者檔一致。
- `ranking-tables` 列數是否等於公開 `ranking_entries`。
- 標記 `has_report_detail` 的排行榜薄索引列是否都能在 `ranking-details` 找到完整 entry。
- `duplicate_count > 1` 的個人成績是否仍保留 `report_variants` / `source_reports`，或能透過 `report_detail_path` / `report_detail_id` 在個人成績報告細節檔找回來源。
- `public/data/all` 的 hidden delta 是否能與一般公開資料合併，避免額外檢視流程缺漏公開資料或 hidden 來源。

`scripts/audit_pages_payload.mjs` 則量測 `dist/`、`dist/data/`、`dist/data/all/`、`dist/data/users/`、`dist/user/` 與 `dist/og/`。正式 GitHub Actions 會先用 `npm run prune:pages-user-data` 清掉 `dist/data/users` 內除了 `index.json` 之外的大型使用者 JSON、逐玩家靜態分享頁與 `dist/og/users`，再執行 `npm run audit:pages-payload:strict -- --write-history data/pages_payload_history.jsonl`；若本機完整 build 或緊急流程未清掉 users 資料，`dist/data/users/` 與 `dist/user/` 預算仍會提供體積警訊。任一項超過 target 會在上傳 Pages artifact 前失敗；正式 workflow 會先提交並推送本輪 `data` / `public/data` 更新，再執行 payload 稽核，避免體積超標時丟失 FFLogs 抓取成果。稽核通過後若歷史 JSONL 有變更，會用另一筆 commit 追蹤 artifact 體積、檔案數、建置秒數與上一筆差異。本機若只想做 baseline 觀察，可手動執行 `npm run audit:pages-payload`；需要比較趨勢時再加 `-- --write-history /tmp/pages_payload_history.jsonl`。

目前 strict target 將 hidden delta 從 120 MiB 收斂為 90 MiB；`dist/data/users` target 保留為 530 MiB，主要用來保護本機完整 build、緊急排查或未來流程異動時的體積上限。正式主站 artifact 的這一列通常只應剩下 `data/users/index.json`，因為個別玩家成績單 JSON 已移到 users 專用 repo；逐玩家靜態分享頁與玩家 OG 圖也不應保留在正式 artifact，避免 GitHub Pages 同步大量小檔失敗。

## 排行榜前端薄索引

`public/data/rankings/*.json` 仍保留完整公開 `ranking_entries`，作為相容資料契約與外部檢視入口。前端排行榜預設改讀 `public/data/ranking-tables/{key}.json`：

- `format="ranking_table_index_v1"`：代表檔案是欄位陣列加列陣列的薄索引。
- `table_columns`：列陣列的欄位順序。
- `table_rows`：前端表格、篩選與排序所需的最小欄位。
- `version_table_rows`：若副本有版本切點，保留 `all|valid|obsolete` 各自排序後的薄索引列，避免前端重新計算版本排名。
- `detail_path`：指向 `public/data/ranking-details/{key}.json`，使用者點擊「報告」按鈕時才載入。

`public/data/ranking-details/{key}.json` 保存以 entry `id` 為 key 的完整公開排行榜條目，用來組成 FFLogs、xivanalysis 與 ffreplay 外部連結，以及報告彈窗內的追溯欄位。這組檔案是公開 `ranking_entries` 的衍生快取，不是權威來源；重建時仍以 `data/rankings/*.json` 與分片為準。

## Logs 檢查索引

`public/data/report_status_index.json` 是常見問題頁中 FFLogs 檢查工具的輕量查詢索引，由 `scripts/build_report_status_index.mjs` 讀取 `public/data/ranking-details/*.json` 產生。它使用 `report_columns`、`encounter_columns` 與 `fight_columns` 欄位陣列格式壓縮體積，內容只保留：

- report code 與首次/最新紀錄時間。
- report 命中的副本、fight id、排行列數與玩家數。
- hidden entry 計數，用來區分一般公開資料與 hidden delta 摘要。

這份索引不保存玩家完整成績、FFLogs raw payload、`masterData` 或掃描 checkpoint，也不是判定 report 是否應入庫的權威來源；權威來源仍是 `data/rankings/*.json` 與分片。`public/data/all/report_status_index.json` 則是 hidden delta，只保存額外檢視必要的 hidden report 摘要並以 `base_path="data/report_status_index.json"` 指回公開底稿。

`public/data/update_status.json` 由 `scripts/build_public_status_data.mjs` 從 `data/update_status.json` 與 `public/data/global_stats.json` 產生，公開最近資料更新時間、Actions run URL、總角色/成績數，以及 workflow 的每 30 分鐘排程、近期 24 小時重查、24-72 小時延遲掃描與 168 小時歷史補查視窗摘要。前端只能用這份靜態 JSON 推估等待時間；若使用者需要確認 FFLogs 目前是否公開可讀，常見問題頁會透過 Apps Script Web App 查詢單一 report，但即時可讀不代表已符合排行榜收錄條件。

`public/data/all/ranking-tables/` 與 `public/data/all/ranking-details/` 輸出 hidden delta：

- `format="ranking_table_hidden_delta_v1"`：只保存 hidden 排行列、完整排序 ID 與 `base_path`，前端讀到後會載入公開 `ranking-tables` 底稿合併。
- `format="ranking_detail_hidden_delta_v1"`：只保存 hidden 報告細節 entry，前端會與公開 `ranking-details` 合併。
- `public/data/all/rankings/*.json` 也改為 `format="ranking_hidden_delta_v1"`，保留 hidden `ranking_entries` 與排序 ID，供相容 fallback 或額外檢視使用。

## 個人成績單報告細節

`public/data/users/*.json` 是個人成績單主檔，保留頁面列表、最佳紀錄、同職分位與常同場隊友。多份 report 上傳同一場戰鬥時，主檔只保留代表成績、`duplicate_count`、`report_detail_path` 與 `report_detail_id`；完整 `report_variants` 與 `source_reports` 會寫入 `public/data/user-entry-details/{玩家檔名}.json`。

個人成績單會保留前端顯示所需的 `gcd_coverage`，但不輸出 `gcd_coverage_status`。後者是 GCD 回補與抓取流程的診斷狀態，會隨每筆歷史成績大量重複；需要追查演算法來源或失敗原因時，應回到排行榜來源資料或 `data/rankings/` 的 report 分片查證。

前端讀取個人成績單時，`data/users/index.json` 預設由主站 `/data/users/index.json` 提供，讓所有訪客共用的搜尋索引套用主站 CDN 快取；個別玩家成績單主檔與 `user-entry-details` 則透過 `src/utils/publicData.js` 的 users 專用 repo 基底讀取。`VITE_USER_DATA_BASE_URL` 可在部署環境覆寫個別玩家資料基底；`VITE_USER_INDEX_BASE_URL` 可在需要獨立索引 CDN 時覆寫索引基底。檔案內的 `file_path` / `base_path` 仍維持 `data/...` 相對路徑，讓主站與專用 repo 可以共用同一份資料契約。

`public/data/user-entry-details/{玩家檔名}.json` 使用 `format="user_entry_details_v1"`，`entries` 以成績 `id` 為 key。使用者點擊個人成績單的「報告」按鈕時，前端才依 `report_detail_path` 載入這份細節檔並補回報告彈窗分頁。這讓 `public/data/users/` 能維持較薄的列表資料，同時保留每個來源 report code、fight、FFLogs 連結與外部工具深連結所需欄位。細節檔內的 `report_variants` 只保存每個來源必要或與主檔代表成績不同的欄位；前端會先套用主檔成績，再覆蓋來源分頁欄位。

`public/data/all/user-entry-details/` 只會為 hidden delta 成績單中實際引用的多來源條目輸出細節；沒有 hidden 成績的使用者仍直接共用一般公開 `user-entry-details`。

## 去重與排名規則

同一角色、同一伺服器、同一職業的最佳成績排序規則：

1. rDPS 較高者優先。
2. rDPS 平手時，通關時間較短者優先。
3. 仍平手時，aDPS 較高者優先。
4. 最後才用紀錄時間或名稱做穩定排序。

`fight_hash` 用於辨識不同 report 上傳的同一場戰鬥；`source_reports` 與 `duplicate_count` 必須保留，不能因去重而刪掉來源線索。

個人成績單會用 `fight_hash + 角色 + 伺服器 + 職業` 合併同一場戰鬥的多份上傳。合併列保留代表成績與細節指標，完整 `report_variants` 與 `source_reports` 由 `user-entry-details` 按需載入，讓前端報告彈窗可分頁切換不同 report 來源。

個人成績單未套用職業篩選時，副本代表列與分享用代表職業優先選同職 `job_rank` 最前面的有效紀錄；`summary.best_rdps` 仍保留最高 rDPS，避免把「代表職業」與「最高輸出」混成同一件事。

若同名角色有跨伺服器的公開紀錄，公開排行榜、`public/data/users/*.json`、`public/data/users/index.json`、近期動態、隊伍榜與伺服器對比等公開衍生資料，都必須以「角色名稱 + 伺服器」拆成不同玩家。遊戲允許不同伺服器使用相同角色名稱，因此目前不再自動處理轉服合併；`canonical_server` 僅保留為前端相容欄位，值等於該份個人成績單自己的伺服器，`server_aliases` 預設為空陣列，公開條目也不再輸出 `original_server`。

## FFLogs 欄位解析

淺層 reports 查詢目前不能直接用伺服器過濾；`report_region_scope` 只控制候選 report 的地區範圍。專案與 GitHub Actions 預設使用 `all` 掃全部地區，以涵蓋繁中服玩家上傳到其他地區的紀錄。無論候選來自哪個地區，都必須再查 `masterData.actors(type: "Player")` 確認是否包含繁中服伺服器。

玩家身分以 `playerDetails` 為主，因為它能排除 Boss、LimitBreak、Pet，並提供角色、伺服器與職業；`damageDone.entries` 只作為輸出數值來源。

`id` / `guid` 優先於角色名稱；只有在同一 report 的名稱唯一時才用名稱 fallback，避免跨伺服器同名角色被合併。

`damage_time_ms` 優先來自 FFLogs damageDone table 的 `combatTime - damageDowntime`。沒有該表格時才退回 fight combatTime，避免 rDPS/aDPS 分母被誤判。

單場 `playerDetails` 與 `damageDone` GraphQL 查詢必須同時帶 `fightIDs` 以及該 fight 的相對 `startTime` / `endTime`。少數 FFLogs 舊報告的 `report.endTime` 可能停在 fight 中途；只用 `fightIDs` 會拿到 partial table，導致 rDPS/aDPS 異常放大。

UCoB（絕巴哈姆特，encounterID 1073）通關判斷需由資料管線補判：先取回所有同副本 fight，保留原生 `kill=true`，再接受 `fightPercentage == 80`、名稱已進入 Bahamut Prime 後段、`endTime - startTime >= 780000` 的 fight。UCoB 的 `playerDetails` / `damageDone` 查詢也不能套 `killType: Kills`，避免 FFLogs 未標記 kill 的通關場抓不到玩家與傷害表；其他絕本仍使用原生 kill 旗標。TOP（絕歐，encounterID 1077）P3/P4 也有 enemy preload 造成 Phase 判斷困難的情境，但這是 Phase 分類風險，不是目前通關收錄需要移除 `killType: Kills` 的理由。

絕本 report 的 `checked_reports` / `processed_reports` 會記錄 `clear_rule_revision`。當通關判斷規則更新時，只要調整程式內版本與受影響副本清單，近期、延遲或歷史來源遇到尚未套用新版本的既有受影響絕本 report 時，就會讓該副本穿透 checked_reports 已處理快取重新深查；目前版本只影響 UCoB。已確認沒有繁中服玩家的 report 不會因通關規則更新而重刷，因為通關判斷不會改變 `masterData` 的玩家伺服器；重判完成後再寫入版本，避免同一份 report 在後續輪巡中重複消耗深查預算。

未來若要輸出團滅 Phase 或相位統計，UCoB 與 TOP 需要各自的副本特例，不能只靠 `enemyNPCs[].gameID` 或 enemy 是否出現判斷；應優先確認 FFLogs 的 `lastPhase` / `phaseTransitions` 是否可靠，再用 report/fight 實例交叉校正。

`active_percent` 對齊 FFLogs Damage Done CSV 的 Active%，優先使用 `fflogs_total_time_ms` 作為分母；DPS/rDPS/aDPS 仍使用 `damage_time_ms` 作為分母。

## Hidden Report 與 Hidden Delta

資料管線可在 report 上標記：

- `report_hidden: true`
- `hidden_reason`
- `hidden_detected_at_iso`
- `hidden_source`

一般公開資料會排除 hidden report，讓前端不需要在 Vue 元件內重做資料狀態判斷。`public/data/all/` 只輸出 hidden delta，供額外檢視流程與公開資料合併：

- `users/index.json` 仍列出所有角色；沒有 hidden 成績的角色 `file_path` 直接指回 `data/users/*.json`，有 hidden 成績的角色才指向 `data/all/users/*.json`。
- `data/all/users/*.json` 使用 `format="user_profile_hidden_delta_v1"`，保存 hidden 副本列、完整排序 ID、完整 summary 與常同場隊友；前端會依 `base_path` 載入公開個人成績單後合併。
- `data/all/user-entry-details/*.json` 保存 hidden delta 成績單實際引用的多來源報告分頁細節。
- 額外檢視流程若把部分 `/data/...` 載入改到 `/data/all/...`，必須允許前端依 `base_path` / `file_path` 讀回公開底稿；不可再假設 `/data/all/` 有所有公開檔案的完整複本。

若玩家的公開成績沒有可列出的 entry，一般 `public/data/users/index.json` 仍會保留空白成績單入口與伺服器資訊，讓 `/user/{玩家}` 頁面可以開啟；預設成績單不會輸出副本成績、分數、隊友或紀錄時間。

## 全域公告資料

全域公告由 `public/data/announcements.json` 提供，`npm run build:user-data` 會同步產生 `public/data/all/announcements.json`，避免額外檢視流程讀取 hidden delta 根目錄資料時公告缺檔。公告是 commit 維護的營運靜態內容，不屬於 FFLogs 抓取或使用者統計建置產物。

公告檔格式：

- `schema_version`：目前固定為 `1`。
- `updated_at_iso`：公告檔最後維護時間。
- `announcements[]`：公告列表。

每則公告欄位：

- `id`：穩定識別碼。前端會用它保存使用者關閉狀態；若希望已關閉的使用者重新看到同一主題，請新增新 id。
- `title`：公告標題。
- `summary`：右上角通知顯示的純文字摘要。
- `details_markdown`：公告視窗內顯示的 Markdown 詳細內容。
- `starts_at_iso`：選填；未設定時視為即刻生效。
- `expires_at_iso`：選填；未設定時不會自動過期。
- `severity`：選填，可用 `info`、`update` 或 `warning` 控制視覺語氣。
- `links[]`：選填，格式為 `{ "label": "...", "url": "..." }`，前端會以按鈕樣式顯示。只允許 `http:`、`https:` 與 `mailto:` 連結。

前端主動通知只顯示「目前已開始、尚未過期、使用者尚未關閉」的公告；「所有公告」視窗則會列出公告檔內所有公告，並標示進行中、尚未開始或已過期。

## 版本切點與過版紀錄

`config/encounters.json` 的 `version_cutoff` 用來描述副本版本有效期限。`極 佐拉加` 與 `極 豔翼蛇鳥` 的過版切點是台灣時間 2026-04-21 18:00（`2026-04-21T10:00:00.000Z`）；輕量級零式 M1S～M4S 與 `極 永恆女王` 的過版切點是台灣時間 2026-07-28 12:00（`2026-07-28T04:00:00.000Z`）。

`scripts/fetch_fflogs.py --rebuild-public` 會依 `start_time` 標記公開排行榜條目的：

- `is_obsolete_record`
- `version_status`
- `version_cutoff_iso`
- `version_ranking_entries.all|valid|obsolete`

`scripts/build_user_data.mjs` 會在全服統計、個人成績單與隊伍榜輸出 `version_slices.all|valid|obsolete`。同職分位、個人最佳紀錄與職業最佳紀錄只能使用 `valid` 紀錄，過版紀錄只作為歷史資料呈現與追溯。

前端版本篩選一律使用 `version=all|valid|obsolete` 的網址狀態；若副本沒有 `version_cutoff`，必須自動回到 `all`，避免非過版副本出現無效篩選。

## 外部工具連結

排行榜報告欄以「報告」按鈕開啟可關閉的彈跳視窗，集中呈現該筆成績數值與 FFLogs、xivanalysis、ffreplay 外部工具連結。

精準 xivanalysis 玩家頁使用公開 JSON 的 `report_code`、`fight_id` 與 `fflogs_source_id` 組成 `/fflogs/{report}/{fight}/{sourceID}`。`fflogs_source_id` 來自 FFLogs `playerDetails` 的 sourceID，只用於外部工具深連結，不作為排行榜角色身分主鍵。ffreplay 連結則使用含 `fight` query 的 FFLogs URL 進行 URL encode。
