# 專案運作準則 (Operating Principles)

本專案為「FFXIV 繁中服專屬高難度副本排行榜」系統。專案架構包含基於 Vue 3 / Vite 的前端網站，以及基於 Python 與 FFLogs GraphQL API 的資料管線（Data Pipeline）。所有開發、重構、文件撰寫與註解都必須嚴格遵守以下準則。

## 1. 嚴格遵守準則 (Strict Adherence)
* **最高優先級**：本運作準則必須被嚴格執行。在每一個開發與重構的步驟中，請反覆確認是否符合此處列出的所有規範。

## 2. 全盤檢視與交接導向 (Context & Handover)
* **完整檢視**：每次修改前，必須完整檢視專案所有相關程式碼（包含 Python 爬蟲腳本、Node.js 聚合腳本、JSON 資料結構與 Vue 前端狀態管理），確保理解整體脈絡。
* **交接思維**：撰寫程式碼與註解時，必須假設「這份專案即將移交給完全未接觸過的新人」。盡可能添加詳細的上下文（Context）註解。尤其是涉及 **FFLogs 欄位解析與 GraphQL 查詢優化**、**rDPS / aDPS 等輸出數據計算邏輯**，以及 **跨伺服器玩家身分判定與去重機制**時，必須解釋「為什麼這樣做（業務邏輯）」而非僅是「做了什麼」，確保資料整理邏輯清晰可追溯。

## 3. 規劃優先 (Planning First)
* 在實際撰寫程式碼前，必須先規劃要執行的項目與影響範圍，並列出簡要的 Step-by-step 計畫。
* **資料結構優先**：任何涉及 `config/encounters.json` (副本設定) 或輸出 JSON Schema 的變更規劃，必須優先確認是否會破壞現有已抓取的 `data/rankings/` 歷史紀錄，或影響前端讀取資料的向後相容性。

## 4. 變更檢核與自我修正 (Verification & Review)
* **Git Diff 檢查**：每次執行完畢前，必須執行 `git diff` 重新檢視即將提交的變更。
* **意義確認**：確認所有更新皆有具體意義、無多餘程式碼（Clean Code），且每一處複雜邏輯變更都附帶了充分的註解說明。

## 5. 強制測試與驗證 (Mandatory Testing & Validation)
* **執行測試**：每次任務執行完畢前，必須進行測試以確保功能正常且無回歸錯誤（Regression）。
* **測試優先級**：針對 **「FFLogs API 限流與重試機制（Rate Limit & Backoff）」**、**「無效或隱藏報告的例外捕捉」** 與 **「`npm run build:user-data` 資料聚合正確性」**，必須確保腳本能順利執行到底，保證前端依賴的靜態 JSON 檔案完整且準確。

## 6. 文件一致性與可追溯性 (Documentation Consistency)
* **全面同步**：每次執行完畢前，必須完整檢視 `CLAUDE.md`、`AGENTS.md` 與 `README.md`。
* **逐一檢核**：確認文件內的所有紀錄（如：GitHub Actions 排程時間、環境變數需求、手動補抓指令、相依套件）與目前的專案狀態完全相符。

## 7. 架構邊界嚴守 (Architecture Boundaries)
本專案為靜態化分離架構，職責必須嚴格分離：
* **Data Fetching Layer (資料管線層 - Python)**：負責處理最純粹的資料獲取（GraphQL 查詢、限流控制、繁中服玩家初步過濾）。嚴禁在此層直接寫入與 UI 呈現相關的格式。
* **Data Building Layer (資料建置層 - Node.js)**：負責將原始的分散資料，聚合為使用者易讀的「全服統計」與「個人成績單」。複雜的陣列排序與統計運算必須在此層完成（如 `build_user_data.mjs`）。
* **UI Presentation (表現層 - Vue 3)**：僅負責讀取 `public/data/` 內的靜態 JSON 檔案進行渲染、篩選與狀態管理。**嚴禁在前端元件內直接發送 Request 至 FFLogs API**。

## 8. 語言規範與在地化 (Language & Localization Standards)
* 所有對話、Git Commit Message、文件、註解皆需使用**繁體中文 (台灣用語)**。
* **Git Commit Message 格式必須遵循常規慣例**：一律採用 `type(scope): 中文描述`，例如 `feat(parser): 實作極樓神通關紀錄的解析邏輯`。`type` 應依變更性質選用 `feat`, `fix`, `docs`, `refactor`, `test`, `chore` 等；`scope` 必須對應實際影響模組。
* **每一筆 Commit 都必須補完整 Description（commit body）**：Description 必須使用繁體中文（台灣用語），清楚記錄 Why、主要變更、測試/驗證結果。
* **嚴禁使用中國用語**：例如將「接口、項目、回調、模塊、內存、數據庫、服務器、異步」必須嚴格替換為「**API/介面、專案、回呼、模組、記憶體、資料庫、伺服器、非同步**」。

## 9. 資料狀態與例外處理 (Data State & Exception Handling)
* **Append-Only 保護原則**：`data/state.json` 的 report 狀態、`data/rankings/*.json` 的 reports，以及 `config/encounters.json` 的 encounter key 皆為不可逆的重要歷史資產。
* **禁止覆寫或硬刪除**：嚴禁寫出會隨意覆蓋或刪除歷史紀錄的程式碼。如果需要同步資料，必須使用 `npm run sync:data`，並事先透過 `--dry-run` 檢查是否有 `REMOVAL` 或 `CONFLICT` 發生。
* **API 例外處理**：FFLogs API 可能會發生逾時或回傳不完整資料，Python 爬蟲必須實作穩健的 Exception 捕捉機制，記錄錯誤 report code，確保掃描進度不會中斷崩潰。

## 10. 開發伺服器與環境限制 (Dev Server & Environment Limits)
* **禁止擅自啟動服務 (Agent Instructions)**：除非使用者明確要求，否則嚴禁擅自啟動 Vite 開發伺服器（例如執行 `npm run dev`、`vite` 或同等指令）。
* **核准機制 (Agent Instructions)**：若前端驗證或功能測試通常需要依賴開發伺服器，請先向使用者說明需要啟動伺服器的原因，並在取得使用者明確同意後方可啟動。
* **環境變數安全**：`.env` 內的 `FFLOGS_CLIENT_ID` 等憑證為敏感資訊，嚴禁在任何除錯輸出、Log 或 Commit 中印出明文。

## 11. 程式碼風格 (Code Style)
* 前端專案需符合 Vue 3 組合式 API (Composition API) 最佳實踐及 ESLint 規範。
* 後端管線需符合 Python 3.11+ 的 PEP 8 規範。
* 全面實施**強型別**開發思維：Python 腳本應加上 Type Hints（型別提示）；前端與 Node.js 資料處理應明確知道 JSON 的結構邊界。

## 12. 準則鎖定 (Principle Locking)
* 本「運作準則」不允許被 AI 自行修改，僅能由使用者發起變更。
* 文件末端可新增「附錄：已確立的技術決策」，由 AI 於開發過程中隨實作累積補充技術細節（如 FFLogs GraphQL 查詢 Schema、資料檔結構對應），作為未來協作的背景知識。

## 附錄：已確立的技術決策

### A. 資料流與責任邊界
1. `scripts/fetch_fflogs.py` 是唯一可直接呼叫 FFLogs GraphQL API 的資料管線入口，負責 OAuth、限流、重試、報告存取例外、繁中服玩家初篩，以及 `data/rankings/` 與 `data/state.json` 的可追溯資料寫入。
2. `scripts/build_user_data.mjs` 是唯一負責全服統計、個人成績單、隊友統計、職業分布與傷害分位數的資料建置腳本。Vue 元件不得重做這些聚合。
3. `src/` 前端只能讀取 `public/data/` 靜態 JSON。任何新增畫面若需要新統計欄位，應先擴充 Node.js 建置層，再讓前端讀取結果。

### B. 副本清單的雙層語意
1. `config/encounters.json` 的 `enabled` 只控制下一輪 Python 爬蟲是否掃描該副本。
2. `public/data/encounters.json` 是前端選單來源。只要副本已有 `data/rankings/` 或 `public/data/rankings/` 歷史資料，即使 `enabled=false`，仍應保留在公開清單中，避免歷史排行榜與個人成績單消失。
3. `key` 是 `data/rankings/{key}.json`、`data/rankings/{key}.reports/`、`state.encounters[key]` 與前端網址狀態的共同主鍵，建立後不得任意改名。

### C. 排行榜與去重規則
1. `data/rankings/*.json` 主檔保留 `ranking_entries`、副本摘要、更新時間與 `report_shards`；report/fight/player 脈絡保存在同名 `*.reports/*.json` 分片。
2. `ranking_entries` 是扁平索引，供前端快速顯示與 Node.js 聚合；完整追溯仍以 `reports -> fights -> players` 為準。
3. 同一角色、同一伺服器、同一職業的最佳成績排序規則為 rDPS 優先，平手看通關時間，再看 aDPS，最後才用紀錄時間或名稱穩定排序。
4. `fight_hash` 用於辨識不同 report 上傳的同一場戰鬥；`source_reports` 與 `duplicate_count` 必須保留，不能因去重而刪掉來源線索。
5. 新寫入的 report 不保存 `fflogs_raw`、`master_data` 與 `matched_players`；這些大型 raw 欄位可依 report code 重查，停止落地是為避免 Git repo 容量快速膨脹。
6. 當 `reports` 分片存在時，`ranking_entries` 只視為衍生索引；重建排行榜必須以 `reports -> fights -> players` 為權威來源，避免重抓單一 report 後舊扁平索引把錯誤高分帶回來。
7. `report_hidden: true` 的 report 預設不進入一般公開資料；`public/data/all/` 則提供完整資料鏡像，供額外檢視流程使用。
8. 個人成績單未套用職業篩選時，副本代表列與分享用代表職業優先選同職 `job_rank` 最前面的有效紀錄；`summary.best_rdps` 仍保留最高 rDPS，避免跨職業 raw rDPS 讓坦補主職被偶爾遊玩的輸出職業蓋掉。

### D. FFLogs 欄位解析脈絡
1. 淺層 reports 查詢目前不能直接用伺服器過濾；`report_region_scope` 只控制候選 report 的地區範圍。專案與 GitHub Actions 預設使用 `all` 掃全部地區，以涵蓋繁中服玩家上傳到其他地區的紀錄；若短期維護需要降低掃描量，可暫時改用 `china`。無論候選來自哪個地區，都必須再查 `masterData.actors(type: "Player")` 確認是否包含繁中服伺服器。
2. 玩家身分以 `playerDetails` 為主，因為它能排除 Boss、LimitBreak、Pet，並提供角色、伺服器與職業；`damageDone.entries` 只作為輸出數值來源。
3. `id` / `guid` 優先於角色名稱；只有在同一 report 的名稱唯一時才用名稱 fallback，避免跨伺服器同名角色被合併。
4. `damage_time_ms` 優先來自 FFLogs damageDone table 的 `combatTime - damageDowntime`。沒有該表格時才退回 fight combatTime，避免 rDPS/aDPS 分母被誤判。
5. `backfill_missing_fflogs_data.py` 只應補齊影響建置的欄位，例如 `fights[].players`、`clear_time_ms` 與 `damage_time_ms`；不得因缺少 raw 欄位而把大型原始資料補回 repo。
6. 單場 `playerDetails` 與 `damageDone` GraphQL 查詢必須同時帶 `fightIDs` 以及該 fight 的相對 `startTime` / `endTime`。少數 FFLogs 舊報告的 `report.endTime` 可能停在 fight 中途；只用 `fightIDs` 會拿到 partial table，導致 rDPS/aDPS 異常放大。
7. `active_percent` 對齊 FFLogs Damage Done CSV 的 Active%，優先使用 `fflogs_total_time_ms` 作為分母；DPS/rDPS/aDPS 仍使用 `damage_time_ms` 作為分母。
8. `gcd_coverage` 只保存衍生結果，不保存 FFLogs Casts raw events。key 不存在代表尚未嘗試補齊；值為 `null` 代表已嘗試但 report 已轉為 Private、刪除或無權限。
9. `scripts/backfill_gcd_coverage.py` 會以 FFLogs `Casts` graph 本地補算 GCD 覆蓋率；GraphQL 查詢必須帶 `fightIDs` 與該 fight 的相對 `startTime` / `endTime`，同一個 report/fight 優先查整場 graph 後再依玩家 `sourceID` 於本地切分，避免每位玩家各打一個 request。計算仍使用 graph downtime 視窗同時扣除分母與分子。
10. GCD 技能分類與基礎 cast/recast 以 XIVAPI datamining `Action.csv` 為底；腳本只於執行時讀入記憶體，不落地完整遊戲資料。`Action.csv` 無法表達的 xivanalysis-like 例外，例如忍者 mudra/ninjutsu 屬於 GCD 流程、毒蛇劍士部分技能有獨立 `gcdRecast`，需在腳本 allow-list 補上。實際 recast 參照 xivanalysis 的 45ms timestamp 分桶估計，並拆分忍者/武僧職業加速與毒蛇劍士、武士、白魔法師等加速狀態，避免把有 buff 的短 GCD 誤套到開場或 buff 斷掉的 GCD；最後仍以下一個 GCD timestamp 夾住覆蓋區間，避免 FFLogs 偏短 cast packet 間隔讓高施放密度職業被高估。
11. `scripts/backfill_gcd_coverage_xivanalysis.py` 只保留為人工抽樣診斷工具，會以 Playwright 開啟 xivanalysis report/fight/player 頁面並解析 Checklist 的 `Always be casting` 百分比；GitHub Actions 預設不得使用此入口，避免觸發 xivanalysis 的 `Slow down / Too many requests` 限流。xivanalysis 沒有正式結果 JSON API；此腳本不得保存頁面或 FFLogs raw events。
12. 排行榜報告欄以「報告」按鈕開啟可關閉的彈跳視窗，集中呈現該筆成績數值與外部工具連結。前端外部報告工具連結依 `report_code`、`fight_id` 與 `fflogs_source_id` 組成；`fflogs_source_id` 來自 FFLogs `playerDetails` 的 sourceID，只用於 xivanalysis `/fflogs/{report}/{fight}/{sourceID}` 深連結，不得取代角色名稱、伺服器與職業組成的排行榜身分判定；ffreplay 連結則使用含 `fight` query 的 FFLogs URL 進行 URL encode。

### E. 驗證與同步
1. 文件或註解變更仍需至少執行語法檢查與 `npm run build:user-data`，確認資料聚合可完成。
2. `python scripts/fetch_fflogs.py --rebuild-public` 只重建公開排行榜與副本清單，不會呼叫 FFLogs API；適合在沒有憑證或不想推進掃描點時驗證公開產物。
3. 若本機與 GitHub Actions 都產生資料，必須先執行 `npm run sync:data -- --dry-run`；看到 `REMOVAL` 或 `CONFLICT` 不可自動套用。
4. 清理既有 ranking raw 欄位時，先跑 `npm run compact:rankings -- --dry-run` 確認只移除 `fflogs_raw`、`master_data`、`matched_players` 與 fight 層 raw payload，再執行正式清理。
5. `npm run validate:data` 會檢查公開副本是否都有 ranking 檔、來源分片是否存在、raw 欄位是否回流、全服統計與使用者索引是否完整；`npm run build` 會在 Vite 建置前自動執行這個驗證。
6. `npm run compact:state` 只可移除已由 `checked_reports` 完整保留的 `processed_reports` 重複 checkpoint；執行正式壓縮前必須先跑 `npm run compact:state -- --dry-run`。
7. `build_user_data.mjs` 預設以最新 `rankings_updated_at_iso` 作為 `generated_at_iso`，讓同一批排行榜重建時輸出穩定；可用 `FFXIV_TC_GENERATED_AT_ISO` 覆寫，`npm test` 會用 fixture 驗證這個規則。
8. `npm run test:frontend-data` 會檢查前端資料讀取邊界、`useRankingApp()` 匯出的 shorthand 是否都有定義，以及公開 JSON 是否具備頁面會讀取的必要欄位。
9. SEO/OG 分享網址的乾淨路徑需同時維持舊版 query 相容性；`npm run test:frontend-data` 會覆蓋 `/user/{玩家}`、`/stats/{副本 key}`、`/jobs/{職業}`、`/servers/{左}/vs/{右}`、舊版 query 與子路徑部署情境。
10. `scripts/build_spa_fallback.mjs` 會為 route、個人成績單、副本統計、職業分析與伺服器對比產生各自的 1200x630 PNG OG 圖；內部可用 SVG 模板繪製，但公開 `og:image` / `twitter:image` 必須指向 crawler-safe PNG。
11. `dist/robots.txt` 必須明確允許 `facebookexternalhit` 與 `Facebot`，避免 Facebook 分享偵錯工具把 robots 設定判定為可能阻擋 OG 抓取。
12. `scripts/apply_cloudflare_rules.mjs` 必須維護 Meta/Facebook 分享爬蟲例外規則；`AS32934`、`AS63293` 與 Cloudflare verified Facebook bot 的 GET/HEAD 請求需跳過會造成 OG 抓取 403 的 Security Level、BIC、UA Blocking、Rate Limiting 與後續自訂規則。
13. GCD 覆蓋率目前已在前端開啟：`src/utils/siteFeatures.js` 的 `顯示Gcd覆蓋率=true`。GitHub Actions 會在新 report 落地時由 `fetch_fflogs.py` 即時計算 GCD 衍生結果；既有玩家的全量補算仍維持手動。`npm run backfill:gcd -- --dry-run` 可手動列出待以本地演算法更新的 GCD 覆蓋率筆數與本輪候選；若需要追平舊資料，再正式執行 `npm run backfill:gcd`。若要本機全量重算所有非 null 玩家 GCD，使用 `npm run backfill:gcd:all`。
14. `scripts/fetch_fflogs.py` 遇到 FFLogs 暫時性 500/502/503/504 或連線逾時時，只延後受影響副本並保留該副本原掃描點；`active_scan.last_error_*` 會記錄錯誤摘要，已完成副本仍可推進掃描點，避免單一 API 波動中斷整輪資料更新。
15. GitHub Actions 會用 `FFLOGS_HISTORY_SCAN_*` 環境變數暫時開啟低量歷史補查，並用 `FFLOGS_FETCH_GCD_COVERAGE_*` 在新 report 落地時即時計算 GCD；`config/fflogs.json` 仍預設關閉，避免本機一般執行時額外掃描舊時間窗或查 Casts graph。歷史補查依各副本 `history_scan_cursor_at` 輪巡，專門補抓後來才公開或延後匯出的 report，不取代最新增量掃描。
16. 額外檢視流程若需要完整資料，應只把 `/data/...` 改寫到 `/data/all/...`，不應改動前端邏輯；因此 `build:public-rankings` 與 `build:user-data` 必須維持一般公開資料與完整鏡像同步。
17. GitHub Actions 會用 `FFLOGS_EXISTING_REPORT_STATUS_CHECK_*` 開啟既有 report 狀態巡檢；每輪依 report 時間由舊到新檢查固定數量，游標保存在 `data/state.json` 的 `existing_report_status_check`，跑完後會回到最舊紀錄繼續輪巡。
18. `scripts/check_missing_gcd_report_status.py` 是一次性維護工具，只針對缺少 `gcd_coverage` key 或 `gcd_coverage: null` 的既有 report code 做輕量狀態查詢；不可存取時標記 report hidden，不補算 GCD，也不取代 `backfill_gcd_coverage.py`。

### F. 版本切點與過版紀錄
1. `config/encounters.json` 的 `version_cutoff` 用來描述副本版本有效期限；目前 `極 佐拉加` 與 `極 豔翼蛇鳥` 的過版切點是台灣時間 2026-04-21 18:00，對應 `2026-04-21T10:00:00.000Z`。
2. `scripts/fetch_fflogs.py --rebuild-public` 會依 `start_time` 標記公開排行榜條目的 `is_obsolete_record`、`version_status` 與 `version_cutoff_iso`，並為支援切點的副本輸出 `version_ranking_entries.all|valid|obsolete`；這是避免前端重新實作排行榜去重與排序規則。
3. `scripts/build_user_data.mjs` 會在全服統計、個人成績單與隊伍榜輸出 `version_slices.all|valid|obsolete`。同職分位、個人最佳紀錄與職業最佳紀錄只能使用 `valid` 紀錄，過版紀錄只作為歷史資料呈現與追溯。
4. 前端版本篩選一律使用 `version=all|valid|obsolete` 的網址狀態；若副本沒有 `version_cutoff`，必須自動回到 `all`，避免非過版副本出現無效篩選。
