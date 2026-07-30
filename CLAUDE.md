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
* **測試範圍按變更風險選擇**：每次任務執行完畢前，必須進行與變更範圍直接相關的測試或檢查，以確保功能正常且無回歸錯誤（Regression）。純公告、文案、文件或不影響資料產物的靜態設定變更，可只做 JSON / Markdown / 語法檢查與 `git diff` 檢視，不需要執行使用者資料相關驗證。
* **使用者資料驗證限制**：除非任務明確涉及使用者資料、個人成績單、隊伍榜、全服統計、前端資料契約、`scripts/build_user_data.mjs`、`public/data/users/`、`public/data/user-entry-details/` 或相關資料產物，否則不要主動執行 `npm run build:user-data`、`npm run validate:data`、`npm run test:frontend-data`、`npm run test:data-conservation` 等使用者資料或全量資料驗證。
* **測試優先級**：當任務實際涉及 **「FFLogs API 限流與重試機制（Rate Limit & Backoff）」**、**「無效或隱藏報告的例外捕捉」** 或 **「`npm run build:user-data` 資料聚合正確性」** 時，必須確保對應腳本能順利執行到底，保證前端依賴的靜態 JSON 檔案完整且準確。

## 6. 文件一致性與可追溯性 (Documentation Consistency)
* **全面同步**：每次執行完畢前，必須完整檢視 `CLAUDE.md`、`AGENTS.md` 與 `README.md`。
* **逐一檢核**：確認文件內的所有紀錄（如：GitHub Actions 排程時間、環境變數需求、手動補抓指令、相依套件）與目前的專案狀態完全相符。

## 7. 架構邊界嚴守 (Architecture Boundaries)
本專案為靜態化分離架構，職責必須嚴格分離：
* **Data Fetching Layer (資料管線層 - Python)**：負責處理最純粹的資料獲取（GraphQL 查詢、限流控制、繁中服玩家初步過濾）。嚴禁在此層直接寫入與 UI 呈現相關的格式。
* **Data Building Layer (資料建置層 - Node.js)**：負責將原始的分散資料，聚合為使用者易讀的「全服統計」與「個人成績單」。複雜的陣列排序與統計運算必須在此層完成（如 `build_user_data.mjs`）。
* **UI Presentation (表現層 - Vue 3)**：僅負責讀取靜態 JSON 檔案進行渲染、篩選與狀態管理；主站共用資料與個人成績單索引部署為 Pages artifact 的 `/data/`，個別玩家成績單 JSON 則由 users 專用 repo 提供。**嚴禁在前端元件內直接發送 Request 至 FFLogs API**。

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
3. `src/` 前端只能讀取靜態 JSON。主站共用資料與個人成績單索引來自 `public/data/` 建置後部署到 Pages artifact 的 `/data/`；個別玩家成績單 JSON 由 `Final-Fantasy-XIV-Ranking-for-TC-Users` 專用 repo 提供。任何新增畫面若需要新統計欄位，應先擴充 Node.js 建置層，再讓前端讀取結果。
4. `scripts/fflogs_pipeline/graphql_queries.py` 只集中存放 FFLogs GraphQL 查詢字串；OAuth、限流、重試、掃描游標、繁中服玩家判定、GCD 衍生計算與資料寫入仍必須留在 `scripts/fetch_fflogs.py`。
5. `src/composables/useRankingApp.js` 是前端排行榜 app 的狀態協調入口；`src/composables/rankingApp/context.js`、`defaults.js` 與 `useRankingData.js` 分別管理注入 context、預設值/選項與排行榜列正規化/排序/細節載入，不得在頁面元件中重複這些資料讀取規則。
6. `src/styles/app.css` 只作為樣式入口清單；設計 token、版面骨架、控制項、頁面樣式、表格彈窗與響應式規則應放在 `src/styles/` 對應拆分檔，避免再次累積成單一巨型 CSS 檔。

### B. 副本清單的雙層語意
1. `config/encounters.json` 的 `enabled` 只控制下一輪 Python 爬蟲是否掃描該副本。
2. `public/data/encounters.json` 是前端選單來源。只要副本已有 `data/rankings/` 或 `public/data/rankings/` 歷史資料，即使 `enabled=false`，仍應保留在公開清單中，避免歷史排行榜與個人成績單消失。
3. `key` 是 `data/rankings/{key}.json`、`data/rankings/{key}.reports/`、`state.encounters[key]` 與前端網址狀態的共同主鍵，建立後不得任意改名。
4. `chaotic_cloud_of_darkness` 對應繁中服 2026-06-23 18:00 維護後開放的 7.15「滅 黑暗之雲」；FFLogs 為 Alliance Raids (Chaotic) `zone_id=66`、Cloud of Darkness `encounter_id=2061`、`difficulty=100`，`scan_start_date` 使用 `2026-06-23T18:00:00+08:00` 對齊開放時間。
5. `current_high_end: true` 是個人成績單簡表模式的領域標記；所有 `category="絕"` 與 `category="極"` 副本固定列入，其他副本只有標記為 true 才列入。簡表按零式、絕、極、幻、滅橫列分組；多職業玩家可用與一般成績單共用的職能／職業條件縮小範圍，初始顯示全部職業。有效版本紀錄顯示目前職業範圍最高 PR 與對應職業，只有過版紀錄時只顯示灰色勾勾。「尚未收錄公開通關」只表示本站尚無該角色在目前職業範圍內的公開 FFLogs 成績，不能視為未通關。`fetch_fflogs.py` 寫入公開副本清單時必須轉出此欄位，且不得用公開清單固定為 true 的 `enabled` 推測目前內容。
6. 7.2 確定於繁中服 2026-07-28 13:00 開放；`extreme_zelenia` 使用 Trials II (Extreme) `zone_id=67`、Zelenia `encounter_id=1080`、`difficulty=100`，並以 `scan_start_date="2026-07-28T13:00:00+08:00"` 排程。`savage_m5s` 至 `savage_m8s` 使用 AAC Cruiserweight `zone_id=68`、`encounter_id=97` 至 `100`、`difficulty=101`；次重量級因資料收錄排程調整，四層的 `scan_start_date` 統一延至 `2026-08-04T13:00:00+08:00`。此延後只控制 FFLogs 掃描，不影響 7.2 遊戲版本切點或個人成績簡表量級。未到各自掃描開放時間的啟用副本不得查詢 FFLogs，也不得在公開清單出現；公開清單只可列入已有排行榜檔案的副本，以避免前端讀取空路徑。同一時間 `savage_m1s` 至 `savage_m4s`、`extreme_queen_eternal` 與 `chaotic_cloud_of_darkness` 以 `version_cutoff` 標記過版；`unreal_byakko` 用 `scan_end_date` 停止新增掃描、用 `profile_summary_available_until="7.15"` 僅保留於歷史簡表，而 `unreal_suzaku` 使用 Trials (Unreal) `zone_id=64`、`encounter_id=3010`、`difficulty=100` 自 7.2 起掃。

### C. 排行榜與去重規則
1. `data/rankings/*.json` 主檔保留 `ranking_entries`、副本摘要、更新時間與 `report_shards`；report/fight/player 脈絡保存在同名 `*.reports/*.json` 分片。
2. `ranking_entries` 是扁平索引，供前端快速顯示與 Node.js 聚合；完整追溯仍以 `reports -> fights -> players` 為準。
3. 同一角色、同一伺服器、同一職業的最佳成績排序規則為 rDPS 優先，平手看通關時間，再看 aDPS，最後才用紀錄時間或名稱穩定排序。
4. `fight_hash` 用於辨識不同 report 上傳的同一場戰鬥；`source_reports` 與 `duplicate_count` 必須保留，不能因去重而刪掉來源線索。
5. 新寫入的 report 不保存 `fflogs_raw`、`master_data` 與 `matched_players`；這些大型 raw 欄位可依 report code 重查，停止落地是為避免 Git repo 容量快速膨脹。
6. 當 `reports` 分片存在時，`ranking_entries` 只視為衍生索引；重建排行榜必須以 `reports -> fights -> players` 為權威來源，避免重抓單一 report 後舊扁平索引把錯誤高分帶回來。
7. `report_hidden: true` 的 report 預設不進入一般公開資料；`public/data/all/` 只保存 hidden delta 與額外檢視必要索引，供前端與公開底稿合併後使用。
8. 個人成績單未套用職業篩選時，前 N% 顯示模式的副本代表列與分享用代表職業優先選同職 `job_rank` 最前面的有效紀錄；PR 顯示模式則優先使用 `performance.score_percentile`，缺值時才由 `rank` / `sample_count` 回推 PR。`summary.best_rdps` 仍保留最高 rDPS，避免跨職業 raw rDPS 讓坦補主職被偶爾遊玩的輸出職業蓋掉。
9. 個人成績單以 `fight_hash + 角色 + 伺服器 + 職業` 合併同一場戰鬥的多份上傳；主檔保留代表成績、`duplicate_count`、`report_detail_path` 與 `report_detail_id`，`report_variants` / `source_reports` 需寫入 `public/data/user-entry-details/` 或 `public/data/all/user-entry-details/`，供報告彈窗按需載入並分頁切換不同 report 來源。`report_variants` 可只保存必要或與主檔代表成績不同的欄位，前端需以主檔成績作為分頁 fallback。
10. 公開排行榜與所有公開衍生資料遇到同名角色跨伺服器的公開紀錄時，必須以「角色名稱 + 伺服器」拆成不同玩家；不得再用最新公開紀錄所在伺服器自動合併。`canonical_server` 僅保留為既有前端相容欄位，值應等於該份個人成績單自己的伺服器；`server_aliases` 預設為空陣列，不得把另一個同名角色所在伺服器列為 alias。

### D. FFLogs 欄位解析脈絡
1. 淺層 reports 查詢目前不能直接用伺服器過濾；`report_region_scope` 只控制候選 report 的地區範圍。專案與 GitHub Actions 預設使用 `all` 掃全部地區，以涵蓋繁中服玩家上傳到其他地區的紀錄；若短期維護需要降低掃描量，可暫時改用 `china`。無論候選來自哪個地區，都必須再查 `masterData.actors(type: "Player")` 確認是否包含繁中服伺服器。
2. 玩家身分以 `playerDetails` 為主，因為它能排除 Boss、LimitBreak、Pet，並提供角色、伺服器與職業；`damageDone.entries` 只作為輸出數值來源。
3. `id` / `guid` 優先於角色名稱；只有在同一 report 的名稱唯一時才用名稱 fallback，避免跨伺服器同名角色被合併。
4. `damage_time_ms` 優先來自 FFLogs damageDone table 的 `combatTime - damageDowntime`。沒有該表格時才退回 fight combatTime，避免 rDPS/aDPS 分母被誤判。
5. `backfill_missing_fflogs_data.py` 只應補齊影響建置的欄位，例如 `fights[].players`、`clear_time_ms` 與 `damage_time_ms`；不得因缺少 raw 欄位而把大型原始資料補回 repo。
6. 單場 `playerDetails` 與 `damageDone` GraphQL 查詢必須同時帶 `fightIDs` 以及該 fight 的相對 `startTime` / `endTime`。少數 FFLogs 舊報告的 `report.endTime` 可能停在 fight 中途；只用 `fightIDs` 會拿到 partial table，導致 rDPS/aDPS 異常放大。
7. `active_percent` 對齊 FFLogs Damage Done CSV 的 Active%，優先使用 `fflogs_total_time_ms` 作為分母；DPS/rDPS/aDPS 仍使用 `damage_time_ms` 作為分母。
8. `gcd_coverage` 只保存衍生結果，不保存 FFLogs Casts graph 或 raw events。key 不存在代表尚未嘗試補齊；值為 `null` 代表已嘗試但 report 已轉為 Private、刪除或無權限。
9. `scripts/backfill_gcd_coverage.py` 會以 FFLogs `Casts` graph 本地補算 GCD 覆蓋率；GraphQL 查詢必須帶 `fightIDs` 與該 fight 的相對 `startTime` / `endTime`，同一個 report/fight 優先查整場 graph 後再依玩家 `sourceID` 於本地切分，避免每位玩家各打一個 request。`unreal_byakko`、`extreme_queen_eternal`、`extreme_valigarmanda`、`extreme_zoraal_ja` 與 `savage_m1s` 至 `savage_m4s` 預設改用 FFLogs `All` raw events，因為這些副本需要 raw targetability、玩家 UnableToAct 狀態或 raw packet 時序才能對齊 xivanalysis。
10. GCD 技能分類與基礎 cast/recast 以 XIVAPI datamining `Action.csv` 為底；腳本只於執行時讀入記憶體，不落地完整遊戲資料。`Action.csv` 無法表達的 xivanalysis-like 例外，例如忍者 mudra/ninjutsu 屬於 GCD 流程、Limit Break、機工士 Hypercharge、`Flamethrower` 只給 2.5 秒 GCD lock、長冷卻 GCD、舞者步舞與 Finish 類技能、賢者 Eukrasia、武士 `Tendo Kaeshi Setsugekka` 3.2 秒 GCD、毒蛇劍士部分技能有獨立 `gcdRecast`，需集中在 `scripts/xivanalysis_gcd_rules.py` 補上，並記錄對應的 xivanalysis 來源 commit。若 raw `combatantinfo` 沒有技速/詠速，必須依 xivanalysis `SpeedStatsAdapterStep`：用 GCD 起點間隔、45ms timestamp 分桶、職業/狀態速度修正與 2.50 秒 tooltip GCD 反推副屬性，再回算各技能 recast；即使反推值低於遊戲實際副屬性下限 420，也要保留站端 actorUpdate 語意，不可擅自 clamp；也不可只用同 base recast 的 tight interval 粗估。Always Be Casting 分母會扣除 downtime；分子只在 GCD 覆蓋結束點落入 downtime 時裁到 downtime 起點，不額外扣除中間橫跨的短 downtime。PCT `Inspiration` 只套用在 `HYPERPHANTASIA_SPELLS`，`Rainbow Bright` 會讓 `Rainbow Drip` 以速度調整後 6 秒 recast 再套 -3500ms；毒蛇 `Dreadwinder/Vicepit` 不吃副屬性但會吃 `Swiftscaled` 狀態加速；武士居合類技能不可用 FFLogs 偏短的 cast packet 比例縮短 GCD lock；毒蛇與武僧 raw packet 的下一個 GCD 裁切需依副本/職業例外決定，幻白虎預設裁切，極瓦利加爾曼達、極佐拉加與 AAC 零式的 MNK/VPR 不裁切；忍者 mudra/ninjutsu 不可套此裁切，因為 xivanalysis 會以各自固定 lock 累加。
11. `scripts/backfill_gcd_coverage_xivanalysis.py` 只保留為人工抽樣診斷工具，會以 Playwright 開啟 xivanalysis report/fight/player 頁面並解析 Checklist 的 `Always be casting` 百分比；GitHub Actions 預設不得使用此入口，避免觸發 xivanalysis 的 `Slow down / Too many requests` 限流。xivanalysis 沒有正式結果 JSON API；此腳本不得保存頁面或 FFLogs raw events。
12. 排行榜報告欄以「報告」按鈕開啟可關閉的彈跳視窗，集中呈現該筆成績數值與外部工具連結。前端外部報告工具連結依 `report_code`、`fight_id` 與 `fflogs_source_id` 組成；`fflogs_source_id` 來自 FFLogs `playerDetails` 的 sourceID，只用於 xivanalysis `/fflogs/{report}/{fight}/{sourceID}` 深連結，不得取代角色名稱、伺服器與職業組成的排行榜身分判定；ffreplay 連結則使用含 `fight` query 的 FFLogs URL 進行 URL encode。
13. 少數副本的 FFLogs `Casts` graph 不會回傳 downtime，但 Boss 轉場仍應從 GCD 覆蓋率分母扣除；raw-events 副本會以 raw `targetabilityupdate` 推出所有敵人都不可選取的窗口，並以 XIVAPI `Status.csv` 的 `LockActions/LockControl` 狀態補上玩家 UnableToAct。推導 targetability 時只使用實際出現 targetability 事件的敵方 actor，避免把雜項 actor 誤當成仍可攻擊敵人。PCT 在幻白虎少數 Starry Muse 窗會於 Boss 不可選取時施放自我 GCD，若 raw targetability 比 Casts graph encounter gap 晚且只造成約一個顯示百分點差異，會標記 `downtime_selection=casts_graph_encounter_gap` 並使用 graph encounter gap 對齊 xivanalysis；更大的差距仍以 raw targetability 為準。黑魔在幻白虎若 raw events 因 Ley Lines / packet 邊界低估 Always Be Casting 且與 Casts graph 差距達 8 個百分點以上，才可標記 `fallback_selection=black_mage_casts_graph_large_raw_gap` 並回退到 Casts graph；若 raw action lock 反而比 Casts graph GCD 嘗試加 raw downtime 高約一到兩個百分點，會標記 `fallback_selection=black_mage_casts_graph_raw_downtime_moderate_raw_overcount`，避免 source combatantinfo / packet 邊界把覆蓋率小幅推高；若 FFLogs raw `combatantinfo` 提供 logging actor 詠速且玩家死亡事件落在 downtime 內，ABC raw lock 需標記 `speed_stat_source=combatantinfo_unadjusted_xivanalysis_raw_lock` 並用未套副屬性的 lock 長度，對齊 xivanalysis legacy raw-events 頁面值。極永恆女王會使用 raw events；武僧不可沿用幻白虎的下一個 GCD 裁切，黑魔、舞者、騎士、繪靈法師與學者使用 targetability-only 分母，Gunbreaker 同時使用 targetability-only 分母與下一個 GCD 裁切；龍騎不做整職業裁切，但 `Dragonsong Dive` 若落在連段循環邊界、下一個 GCD 是 `Raiden Thrust` 等連段起手，需排除該次 LB uptime 以貼近 xivanalysis；RedMage 預設由 selector 保守回到 Casts graph，因為 Queen raw events 對 Dualcast/instant GCD 視窗可能高估 ABC，但低覆蓋率且 raw 只比 graph 高約一到兩個百分點時會標記 `fallback_selection=queen_red_mage_raw_events_low_graph_uptime` 並使用 raw events；Scholar 在 Queen 低覆蓋且 Casts graph 比 raw 高約一到三個百分點時，會標記 `fallback_selection=queen_scholar_casts_graph_intermission_gap` 回退 graph；Bard 在 Queen 近滿覆蓋場次會用 Casts graph 對齊 xivanalysis，避免 raw packet 邊界讓 100% 顯示被壓低。極瓦利加爾曼達的 Casts graph 會漏掉多段短暫 targetability / 玩家 UnableToAct downtime；大多數職業在 raw events 分母下對齊 xivanalysis，但 AST 保留 Casts graph，MNK/VPR 不裁到下一個 GCD，低覆蓋率 RDM 或 WHM 若 raw events 比 Casts graph 高約一到兩個百分點則回退 graph；Bard 則在小幅 graph gap 時回退 graph，低覆蓋率 Army's Paeon 視窗會用固定百分點修正。極佐拉加與 AAC 零式的 Casts graph 會讓部分 SAM/PCT/VPR 的 instant 或長鎖 GCD 累加過寬；固定 seed 稽核差異在 All raw events 路徑會回到 xivanalysis 顯示值，因此也預設使用 raw events，且 MNK/VPR 不裁到下一個 GCD；Bard 在極佐拉加與 AAC 零式採用 raw / Casts graph 小比例混合，補足 xivanalysis 對歌曲或連續施放視窗的呈現差距。這些例外都是為了避免 FFLogs graph downtime 或 raw packet 語意讓 ABC 偏離 xivanalysis。此規則應限縮在已驗證的副本 key，避免多目標或換目標副本被錯誤套用。
14. UCoB（絕巴哈姆特，encounterID 1073）不能只依賴 FFLogs 原生 `kill=true`；資料管線查 fight list 時需取回所有同副本 fight，保留原生 `kill=true`，並補判 `fightPercentage == 80`、名稱已進入 Bahamut Prime 後段、`endTime - startTime >= 780000` 的場次。UCoB 的 `playerDetails` / `damageDone` 查詢也不得套 `killType: Kills`，否則補判通關的 fight 會抓不到玩家與傷害表。其他絕本仍使用 FFLogs 原生 kill 旗標；TOP（絕歐，encounterID 1077）目前只需注意 P3/P4 enemy preload 會影響未來 Phase 判斷，不應因此移除通關查詢的 `killType: Kills`。
15. 混合上傳 report 的 top-level zone 可能只指向其中一種內容；例如 report 主 zone 是幻白虎，但內部同時含零式通關 fight。資料管線不能只依賴 `reports(zoneID)` 的主 zone 分類。當任一 zone 掃到候選 report 並確認含繁中服玩家後，`fetch_fflogs.py` 需查完整 fight list，依 fight 層 `encounterID`、`difficulty` 與通關語意分派到所有啟用副本；同 zone / 同 difficulty 副本仍保留既有 no-clear checkpoint 行為，跨 zone 只處理完整 fight list 實際命中的副本，避免把無關副本寫入 `skipped_no_clear`。

### E. 驗證與同步
1. 文件、註解、公告、文案或不影響資料產物的靜態設定變更，不需要執行 `npm run build:user-data` 或使用者資料相關驗證；只需執行與檔案型態相符的最小檢查（例如 JSON / Markdown / 語法檢查）並檢視 `git diff`。只有當變更會影響資料結構、使用者資料、前端資料契約或 workflow 輸出時，才需要執行對應的資料建置或驗證。
2. `python scripts/fetch_fflogs.py --rebuild-public` 只重建公開排行榜與副本清單，不會呼叫 FFLogs API；適合在沒有憑證或不想推進掃描點時驗證公開產物。
3. 若本機與 GitHub Actions 都產生資料，必須先執行 `npm run sync:data -- --dry-run`；看到 `REMOVAL` 或 `CONFLICT` 不可自動套用。
4. 清理既有 ranking raw 欄位時，先跑 `npm run compact:rankings -- --dry-run` 確認只移除 `fflogs_raw`、`master_data`、`matched_players` 與 fight 層 raw payload，再執行正式清理。
5. `npm run validate:data` 會檢查公開副本是否都有 ranking 檔、來源分片是否存在、raw 欄位是否回流、全服統計、近期動態、隊伍榜、伺服器對比、Honey B. Lovely 粉絲榜與使用者索引是否完整；只應在需要驗證上述資料產物時執行，純公告、文案或文件變更不需要主動執行。`npm run build` 會在 Vite 建置前自動執行這個驗證。
6. `npm run compact:state` 只可移除已由 `checked_reports` 完整保留的 `processed_reports` 重複 checkpoint，以及可由 `processed_at` 毫秒時間重建的 checkpoint `processed_at_iso` 鏡像欄位；跨輪 `checked_reports` 依副本存於 `data/state/checked_reports/{encounter key}.json`，主 state 仍為 `data/state.json`。壓縮器必須載入兩者、保留所有 report code 與 status，並檢查主檔及每個分片都低於 GitHub 100 MiB 單檔限制；不得以刪除歷史快取換取體積。執行正式壓縮前必須先跑 `npm run compact:state -- --dry-run`。
7. `build_user_data.mjs` 預設以最新 `rankings_updated_at_iso` 作為 `generated_at_iso`，讓同一批排行榜重建時輸出穩定；可用 `FFXIV_TC_GENERATED_AT_ISO` 覆寫，`npm test` 會用 fixture 驗證這個規則。
8. `npm run test:frontend-data` 會檢查前端資料讀取邊界、`useRankingApp()` 匯出的 shorthand 是否都有定義，以及公開 JSON 是否具備頁面會讀取的必要欄位。
9. SEO/OG 分享網址的乾淨路徑需同時維持舊版 query 相容性；`npm run test:frontend-data` 會覆蓋 `/user/{玩家}`、`/stats/{副本 key}`、`/jobs/{職業}`、`/servers/{左}/vs/{右}`、舊版 query 與子路徑部署情境。
10. `scripts/build_spa_fallback.mjs` 會為 route、個人成績單、副本統計、職業分析與伺服器對比產生各自的 1200x630 PNG OG 圖；內部可用 SVG 模板繪製，但公開 `og:image` / `twitter:image` 必須指向 crawler-safe PNG。OG PNG 應使用有限 palette 壓縮，避免玩家分享圖隨角色數成長時撐大 GitHub Pages artifact。
11. `dist/robots.txt` 必須明確允許 `facebookexternalhit` 與 `Facebot`，避免 Facebook 分享偵錯工具把 robots 設定判定為可能阻擋 OG 抓取。
12. `scripts/apply_cloudflare_rules.mjs` 必須維護 Meta/Facebook 分享爬蟲例外規則；`AS32934`、`AS63293` 與 Cloudflare verified Facebook bot 的 GET/HEAD 請求需跳過會造成 OG 抓取 403 的 Security Level、BIC、UA Blocking、Rate Limiting 與後續自訂規則。
13. GCD 覆蓋率目前已在前端開啟：`src/utils/siteFeatures.js` 的 `顯示Gcd覆蓋率=true`。GitHub Actions 會在新 report 落地時由 `fetch_fflogs.py` 即時計算 GCD 衍生結果；既有玩家先由 `backfill_gcd_coverage.py --report-limit 25` 不套 stateful cutoff 補最新候選空洞，再由 `backfill_gcd_coverage.py --stateful-report-backfill --report-limit 50` 從固定切點往舊 report 逐輪回補。近期補洞由 `FFLOGS_RECENT_GCD_BACKFILL_REPORT_LIMIT` 控制，設為 `0` 可暫停；歷史 stateful 回補由 `FFLOGS_GCD_BACKFILL_REPORT_LIMIT` 控制。`gcd_report_backfill.cutoff_sort_time` 會保存在 `data/state.json`；若未設定 `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`，第一次正式執行會用當下時間當切點。每輪完成後，`cursor_sort_time` / `cursor_report_code` 會更新成本輪最舊 report，下一輪從該位置繼續往更舊 report 推進；`gcd_report_backfill.calculation_version` 會記錄該輪使用的 GCD 演算法版本，若 state 缺少版本或版本落後目前 `GCD_CALCULATION_VERSION`，必須保留 cutoff 但重設 cursor，讓新版演算法能重新由新往舊追平既有 report。暫時失敗的 report 會保存在 `retry_report_codes`，避免被游標永久略過。`npm run backfill:gcd -- --dry-run` 可手動列出待以本地演算法更新的 GCD 覆蓋率筆數與本輪候選；若要本機全量重算所有非 null 玩家 GCD，使用 `npm run backfill:gcd:all`。
14. `scripts/fetch_fflogs.py` 遇到 FFLogs 暫時性 500/502/503/504 或連線逾時時，只延後受影響副本並保留該副本原掃描點；`active_scan.last_error_*` 會記錄錯誤摘要，已完成副本仍可推進掃描點，避免單一 API 波動中斷整輪資料更新。正式 GitHub Actions 會設定 `FFLOGS_MAX_RUNTIME_SECONDS=6000` 與 `FFLOGS_RUNTIME_GRACE_SECONDS=900`（可由 repo variables 覆寫），讓 FFLogs 憑證長冷卻或掃描接近 runner 風險時，腳本標記 `last_run_stats.time_budget_exhausted=true`、保留 `active_scan` 續跑位置並正常結束，保留後續資料建置與 commit 的時間。
15. GitHub Actions 會用 `FFLOGS_INCREMENTAL_LOOKBACK_HOURS=24` 與 `FFLOGS_NO_CLEAR_RETRY_HOURS=24` 讓最近 24 小時內的 no-clear / incomplete report 重新深查；另用 `FFLOGS_DELAYED_SCAN_*` 開啟 24-72 小時固定延遲掃描。延遲掃描一般只選入 state 與排行榜都沒見過的新 report；例外包含 UCoB 通關規則重判，以及尚未寫入目前 `mixed_report_dispatch_revision` 的既有 report。這兩類 report 都需穿透 `checked_reports` 快取重新深查；完成後寫回版本欄位，避免每輪無限重刷。
16. 額外檢視流程若需要 hidden report，應載入 `public/data/all/` 的 delta 產物，再由前端依 `base_path` / `file_path` 合併一般公開資料；不可再假設 `/data/all/` 內有所有公開 JSON 的完整複本。
17. GitHub Actions 會用 `FFLOGS_EXISTING_REPORT_STATUS_CHECK_*` 開啟既有 report 狀態巡檢；巡檢以 report code 去重，尚未巡檢時優先檢查較新的 report，之後依來源分片的 `report_status_checked_at` 選取最久未巡檢者。這避免固定小額度被大量舊資料卡住，且不需在接近大小上限的 `data/state.json` 保存每筆巡檢狀態。FFLogs 回傳 `visibility=Private`、report 不存在或 `archiveStatus.isAccessible=false` 時，必須標記來源 report hidden，正常公開資料不得再列出。
18. `scripts/check_missing_gcd_report_status.py` 是一次性維護工具，只針對缺少 `gcd_coverage` key 或 `gcd_coverage: null` 的既有 report code 做輕量狀態查詢；不可存取時標記 report hidden，不補算 GCD，也不取代 `backfill_gcd_coverage.py`。
19. `skipped_no_clear` 只在近期重試窗外才視為永久已檢查；workflow 預設 `FFLOGS_NO_CLEAR_RETRY_HOURS=24`，讓剛上傳但尚未匯出通關 fight 的 report 在一天內會被重新深查，避免後續出現 kill 時被舊快取擋掉。
20. 單次 `fetch_fflogs.py` 執行內，report code 是深層檢查去重單位；`masterData.actors` 的繁中服玩家判斷會寫入本輪記憶體快取，後續同 report code 來自其他副本、recent、delayed 或 history 來源時直接重用結果或錯誤，不重複打 FFLogs API。
21. GitHub Actions 會用 `FFLOGS_HISTORY_SCAN_*` 環境變數暫時開啟歷史補查，workflow 預設每輪掃 1 個 168 小時視窗、最多選入 600 份深層候選，且同一 zone/difficulty 群組最多選入 150 份，並用 `FFLOGS_FETCH_GCD_COVERAGE_*` 在新 report 落地時即時計算 GCD（預設上限 150 場）；`config/fflogs.json` 仍預設關閉延遲掃描、歷史補查、即時 GCD 與執行時間預算，避免本機一般執行時額外掃描舊時間窗或查 Casts graph。正式 workflow 會另外設定可續跑的抓取時間預算，讓每 30 分鐘排程遇到長冷卻時能保留後續資料建置與 commit 時間。歷史補查依各副本 `history_scan_cursor_at` 輪巡，專門補抓後來才公開或延後匯出的更舊 report，也會在絕本通關規則版本或混合上傳分派版本更新時，將尚未寫入目前 `clear_rule_revision` 或 `mixed_report_dispatch_revision` 的既有 report 重新選入深查；目前絕本通關版本只影響 UCoB，已確認沒有繁中服玩家的 report 不會因通關規則更新而重刷。近期、延遲與歷史來源只要遇到需要重判的 UCoB report，或需要補跑混合上傳分派的既有 report，都必須讓對應副本穿透 `checked_reports` 已處理快取；重判完成後版本寫入 `checked_reports` / `processed_reports`，避免每輪無限重刷。不取代最新增量掃描與 24-72 小時延遲掃描；若本輪深查上限打滿且仍有 deferred report，游標必須停在最後一筆已選候選的 `startTime`，若該副本本輪未分到深查額度則停回本輪時間窗起點，避免尚未更新的 report 被推到下一輪歷史全區間輪巡後才重試。
22. `scripts/audit_xivanalysis_gcd_sample.py` 是人工稽核工具，預設用固定 seed 對零式、極、幻的每個副本各隨機抽樣 10 場並輸出 `docs/gcd_xivanalysis_audit_latest.json`；`--sample-size` 代表每個副本的基本抽樣戰鬥數，不是分類加總。若 10 場沒有涵蓋全職業，腳本會從同副本補抽能覆蓋缺漏職業的戰鬥；若資料內完全找不到某職業，會在 `job_coverage_by_encounter[].unavailable_jobs` 記錄。預設 `--local-mode recompute` 會即時重算本地結果再比對 xivanalysis，若要檢查已寫入資料可改用 `--local-mode stored`。此工具會對 `Modules not found` 等 xivanalysis 前端暫時狀態重建 browser context，並在主巡檢後集中重試 error 玩家；遇到 `Slow down / Too many requests` 時必須保留或拉長 `--delay-ms`。`--workers` 可平行讀取頁面但不應過高，`--abort-on-fetch-error` 可在 private/deleted 等永久錯誤時中止，`--exclude-report-codes` 可排除已無法由 xivanalysis 存取的 report 並由抽樣器補足同副本樣本。`backfill_gcd_coverage.py --raw-events` 可讀 FFLogs `All` raw events、`combatantinfo` 技速/詠速、狀態視窗與 targetability 來追查差異；目前 `unreal_byakko`、`extreme_queen_eternal`、`extreme_valigarmanda`、`extreme_zoraal_ja` 與 `savage_m1s` 至 `savage_m4s` 已正式預設 raw events，其它副本正式啟用前仍需抽樣驗證。加上 `--apply` 時只會把抽樣中超過容許差異的玩家改寫為 `source=xivanalysis_page`；若要把所有已檢查玩家都改成外站頁面值，必須明確加 `--apply-all-checked`。使用後必須重建公開排行榜與使用者資料，且不得放入 GitHub Actions 預設流程，以免對 xivanalysis 造成過量請求。最新 100 場 stored no-apply 稽核輸出至 `docs/gcd_xivanalysis_audit_100_latest.json`，涵蓋極本 3 個、零式 4 個、幻本 1 個副本，共 800 場、6416 位玩家，結果為 `matched=6416`、`mismatched=0`、`errors=0`；零式抽樣排除了已無法由 xivanalysis 存取的 `3Pw7nFAjh1Q2caKW` 與 `z4daK1LTRFjJA67G`。
23. `fetch_fflogs.py` 深層 report 檢查會先以 `checked_reports`、`processed_reports` 與排行榜分片建立已處理集合，整段快轉所有同區同難度副本都已完成的候選前綴；中斷恢復時則以 `active_scan.current_report_*` 作為輔助切點，但仍會逐筆確認被快轉的 report 已在 state/ranking 留下紀錄。跨輪 `checked_reports` 會依副本寫入 `data/state/checked_reports/`，讀取時再還原既有 state 結構；已處理候選只輸出摘要，不得為逐筆略過重寫整份 state 儲存體。`state_checkpoint_flush_reports` 預設維持 `2000`，避免舊副本歷史回補被大量已知 report 拖慢。時間預算收尾時不得把目前副本加入 completed encounters，也不得推進該副本掃描點，必須依 `active_scan` 與既有 checkpoint 讓下一輪續跑。
24. `npm run test:data-conservation` 是公開資料瘦身前的資料守恆測試，會解析 hidden delta 並檢查排行榜薄索引、報告細節檔、使用者檔、個人成績報告細節檔與多來源 report 線索，避免後續拆檔或延遲載入時讓既有成績或來源追溯消失。
25. GitHub Actions 會在同步 users 專用 repo、執行 Vite/postbuild 後，先跑 `npm run prune:pages-user-data` 保留 `dist/data/users/index.json`，並移除 `dist/data/users` 內的個別玩家檔、`dist/data/user-entry-details`、hidden 使用者差量 JSON、逐玩家靜態分享頁與 `dist/og/users`，再於上傳 Pages artifact 前執行 `npm run audit:pages-payload:strict -- --write-history data/pages_payload_history.jsonl`。正式 workflow 以 `FFXIV_TC_BUILD_USER_SHARE_PAGES=false` 關閉逐玩家靜態分享頁與玩家 OG 圖，只保留 `/user` route 層級入口與共用搜尋索引；`dist/data/users/` 的 target 仍保留給本機完整 build、緊急排查或流程異動時監控。這讓 FFLogs 抓取成果先保存進 Git，payload 超標時只停止部署。稽核通過後若 `data/pages_payload_history.jsonl` 有變更，workflow 會另行 commit/push，記錄 artifact 體積、檔案數、建置秒數與上一筆差異；`npm run audit:pages-payload` 只保留作為本機 baseline 觀察用途。
26. GitHub Actions 會在 payload 稽核與 history commit 後把 `npm run cloudflare:estimate` 與 `npm run cloudflare:purge -- --dry-run --summary` 輸出到 Step Summary，用來檢查 Cloudflare HIT ratio 承載估算與 scoped purge 範圍；正式部署後仍只執行 scoped purge，不做 purge everything。
27. GitHub Actions 會在 `fetch_fflogs.py` 後執行 `npm run audit:mixed-report-dispatch`，把 mixed report 分派版本覆蓋率、待重查副本-report 組合、ranking-only 待補項目、歷史補查游標與 deferred 數量輸出到 Step Summary。此報表只作觀測用途，pending 大於 0 不應阻擋資料 commit 或部署；若要判斷歷史混合上傳重掃是否追平，應看「待重查」是否歸零，並搭配各副本歷史游標是否完成全區間輪巡。
28. `.github/workflows/update_rankings.yml` 與 `.github/workflows/emergency_deploy.yml` checkout 時只抓目前分支的淺層 partial clone，後續同步與 push retry 也只 fetch 有限深度。資料 repo 的完整歷史 pack 已累積到數 GiB；正式 workflow 不需要完整歷史，若改回 `fetch-depth: 0`，GitHub-hosted runner 可能在 checkout 階段耗盡磁碟。
29. `.github/workflows/update_rankings.yml` 與 `.github/workflows/emergency_deploy.yml` 固定使用 Node.js 24，並採用支援 Node 24 runtime 的官方 actions major 版本。GitHub Pages 部署若在 `syncing_files` 階段遇到暫時性失敗，workflow 會等待 60 秒後以同一個 Pages artifact 重試一次；只有部署成功後才會執行 Cloudflare purge。

### F. 版本切點與過版紀錄
1. `config/encounters.json` 的 `version_cutoff` 用來描述副本版本有效期限；`極 佐拉加` 與 `極 豔翼蛇鳥` 的過版切點是台灣時間 2026-04-21 18:00（`2026-04-21T10:00:00.000Z`），輕量級零式 M1S～M4S、`極 永恆女王` 與 `滅 黑暗之雲` 的過版切點是台灣時間 2026-07-28 13:00（`2026-07-28T05:00:00.000Z`）。
2. `scripts/fetch_fflogs.py --rebuild-public` 會依 `start_time` 標記公開排行榜條目的 `is_obsolete_record`、`version_status` 與 `version_cutoff_iso`。排行榜可依使用者偏好用 `game_version` 做繁中服版本累積篩選，或只用既有過版標記做時效篩選；無論哪種模式都不得再輸出重複的 `version_ranking_entries.all|valid|obsolete`。
3. `scripts/build_user_data.mjs` 會在全服統計、個人成績單與隊伍榜輸出 `version_slices.all|valid|obsolete`。同職分位、個人最佳紀錄與職業最佳紀錄只能使用 `valid` 紀錄，過版紀錄只作為歷史資料呈現與追溯。
4. 全服統計、玩家比較與隊伍榜的版本時效篩選仍使用 `version=all|valid|obsolete`；排行榜的共用「版本紀錄」偏好開啟時使用 `gameVersion`，直接顯示目前已開放的實際遊戲版本作為預設，並顯示每筆版本。偏好關閉時，排行榜若有 `version_cutoff` 則改使用 `version=all|valid|obsolete` 的紀錄時效篩選；網址只能寫入目前模式的條件。
5. 個人成績簡表另有繁中服遊戲版本快照，和 `version_cutoff` 的 valid／obsolete 語意分離。`profile_summary_available_from` 決定副本首次可見版本，選填的 `profile_summary_available_until` 可讓輪替內容只保留至最後一個歷史版本；版本選項以「下一版本開放時間」排除後續 `recorded_at_iso`。已公告的未來版本需保存明確開放時間，並在時間到達前標示待開放、到達後自動可選。未公告開放時間時不得用目前時間或猜測日期切分歷史戰鬥。
6. 個人成績簡表的零式會列出所選遊戲版本中全部已開放量級，預設選取最新量級，但可切換查看較早量級。`profile_summary_savage_tier` 必須保存量級 key、名稱、遞增順序與量級內 1～4 層；某量級四層皆有該版本有效通關時，量級按鈕顯示彩色勾勾，量級內樓層仍顯示職業與 PR。新增次重量級、重量級時提高 order 即可讓簡表加入新量級，舊量級的排行榜與個人成績仍維持歷史追溯。
7. `config/game_versions.json` 是個人成績單與排行榜 `game_version` 的唯一繁中服競技版本切點來源。`build_user_data.mjs` 與 `build_ranking_table_data.mjs` 必須以戰鬥 `recorded_at_iso` 在建置層寫入版本標籤；此欄位只用於玩家辨識當時的技能／裝備環境，不得改變 `version_cutoff` 的 valid／obsolete、排名或 PR 語意。前端以共用 localStorage「版本紀錄」偏好控制顯示，預設關閉；開啟時個人分位亮點的 PR 在左、版本在右，成績列摘要與歷史表皆在 aDPS 後顯示版本，並在一般成績單依目前伺服器的已收錄版本提供篩選。版本條件需與職業篩選交集，並以「截至選定版本」的累積快照套用：選擇 7.1 時包含 7.0、7.05 與 7.1，最新版本即完整成績單，不另設「全部版本」。關閉版本顯示時需清除版本條件。個別玩家 JSON 來自專用資料來源，若舊資料尚未帶入 `game_version`，前端僅可依同一組繁中服切點從 `recorded_at_iso` 回推顯示與篩選版本；明確欄位永遠優先，無法判讀時間時不可臆測。

8. 開啟「版本紀錄」時，個人成績趨勢圖只能在每筆 `recorded_at_iso` 可解析時改用時間橫軸，並依繁中服更新切點插入垂直版本線。若有紀錄缺少時間，必須保留等距樣本軸且不畫切點，不得猜測錯位。預設只標示最高／最低數值；滑鼠懸停、鍵盤聚焦或觸控點擊資料點時，只顯示該點數值，離開圖表、按 Escape 或點擊圖表空白處後恢復預設標記。

9. 說明提示按鈕以 localStorage 偏好控制，預設顯示；使用者關閉時，前端必須在根節點設定狀態，讓一般頁面與 Teleport 到 body 的報告彈窗同步隱藏提示。成績列摘要的說明標籤需預留提示按鈕空間，新增欄位時不可讓標籤、按鈕與數值互相擠壓。
10. 個人成績歷史表格的排序只可對目前已篩選的 `public_entries` 建立前端檢視，不得改寫資料、排名或最佳成績。排序設定以副本 key 隔離；切換玩家、伺服器、職業或遊戲版本快照時必須重設。缺失值固定排在最後；同職分位須依可見的 PR／前 N% 語意決定預設方向，避免數字方向與畫面內容相反。

### G. Honey B. Lovely 粉絲榜趣味資料
1. `scripts/fetch_honey_b_fans.py` 是獨立於正式排行榜的趣味資料管線，固定使用 `savage_m2s` 的 `zone_id`、`encounter_id` 與 `difficulty`，不依賴 `enabled` 是否為 `true`。
2. 來源資料保存在 `data/fun/honey_b_fans.json`，公開資料保存在 `public/data/fun/honey_b_fans.json`；不得寫入 `data/rankings/` 或 `data/state.json`，避免趣味榜影響正式排行榜與個人成績單。
3. 粉絲榜只保存通關與 wipe 場次中 `心醉魂迷：奴役`（ability id `1003926`）的 `applydebuff` 衍生紀錄、已檢查戰鬥狀態、已檢查 report 快取與掃描游標，不保存 FFLogs raw events、`masterData` 大表或其他可重查 payload。
4. 每輪正式抓取先掃描近三天公開 M2S 紀錄，補上尚未檢查的通關與 wipe 戰鬥；再從 `scan_start_date` 的歷史游標往後掃描，每輪最多檢查 200 場未記錄戰鬥。已完成目前 `fight_scan_mode` 的 `checked_reports` 快取的 report 必須在 detail query 前略過，避免重複消耗 FFLogs API 配額；舊版只掃通關場次的快取不得阻擋 wipe 補掃。
5. `.github/workflows/update_rankings.yml` 會在正式排行榜抓取後執行 `npm run fetch:honey-fans`，預設 `--recent-days 3 --history-limit 200`，並可用 `HONEY_FANS_RECENT_DAYS`、`HONEY_FANS_HISTORY_LIMIT`、`HONEY_FANS_RECENT_WINDOW_HOURS`、`HONEY_FANS_HISTORY_WINDOW_HOURS` 調整排程掃描範圍。
6. `npm run build:honey-fans` 只由既有來源檔重建公開 JSON，不呼叫 FFLogs API；正式 workflow 會在資料建置階段執行它，並把 `public/data/fun/*.json` 納入資料 commit 路徑。`npm run validate:data` 與 `npm run test:frontend-data` 會檢查公開粉絲榜資料契約。
7. 公開粉絲榜 `top_fans`、粉絲列 `records`、`latest_records`、公開 `records` 與本期摘要只納入以 `source.updated_at_iso` 為基準的近 7 天紀錄；`latest_records` 最多輸出 5 筆，`latest_fans` 最多輸出 16 筆。來源檔仍保留歷史紀錄，建置層會用同樣 7 天切片回推 `current_streak_weeks`，並以 `summary.historical_*` 與粉絲列 `historical_*` 保留歷史統計，供前端顯示「連續 N 週入榜」。
8. 公開 `team_rankings` 使用來源檔中自台灣時間 2026-05-30 00:00:00 起的通關場次，依單場全隊 `心醉魂迷：奴役` 總次數排序，並沿用戰鬥時間軸去重合併同一場的多份 FFLogs 上傳；來源檔仍保留全歷史紀錄與 `summary.historical_*` 追溯欄位。前端 Honey 頁面的「超高難度」開關開啟時，顯示此活動團隊榜而非近 7 天粉絲榜。

### H. 常見問題與 Logs 檢查
1. `src/pages/ReportStatusPage.vue` 是常見問題頁，正式路徑為 `/faq`，舊 `/logs` 只作為相容入口。頁面中的站內收錄判定只能讀取 `public/data/report_status_index.json`、`public/data/all/report_status_index.json` 與 `public/data/update_status.json` 這三類靜態資料；FFLogs 即時公開狀態與待處理申請只能透過 `apps-script/fflogs-report-status/` 的受保護 Web App，不得在前端直接呼叫 FFLogs API，也不得把 OAuth 憑證或 `data/state.json` 掃描 checkpoint 暴露到瀏覽器。
2. `scripts/build_report_status_index.mjs` 由 `public/data/ranking-details/*.json` 產生 report code / fight / 副本摘要索引，使用欄位陣列格式控制 payload 體積。這份索引是衍生快取，不是判定 report 是否應入庫的權威來源；權威來源仍是 `data/rankings/*.json` 與分片。
3. `scripts/build_public_status_data.mjs` 只把 `data/update_status.json` 與 `public/data/global_stats.json` 中可公開的更新摘要輸出到 `public/data/update_status.json`，供前端推估每 30 分鐘排程、24 小時近期重查、24-72 小時延遲掃描與歷史補查等待時間。
4. 若使用者貼上的 report 完全不在公開或 hidden delta 索引中，前端只能回報「尚未在公開索引找到」並列出排程與常見原因；不能宣稱已即時確認 private、deleted、沒有繁中服玩家或沒有通關，這類精確判斷仍只能由資料管線下一輪掃描或站務端受保護診斷工具完成。
5. 待處理名單只以 report code 為單位；即使使用者貼上的 FFLogs 網址帶有 `fight` 參數，也不得把 queue 語意改成指定 fight 補抓。Public 且可讀的 report 可使用一般待收錄或重查；只有本站公開索引已命中且 Apps Script 明確確認 FFLogs 非 Public 或不可讀時，才可使用 `review_existing_visibility` 重新確認公開狀態。workflow 仍須完整重掃整份 report；只有重建後的 hidden delta 真的命中時，收尾才可把該列標為 `hidden`，避免暫時性錯誤或前端參數直接隱藏資料。

### I. 2026-07-28 後普攻資料完整性暫時防護
1. `scripts/fight_integrity.py` 是唯一集中定義此暫時規則的模組；`scripts/backfill_fight_integrity.py` 只針對台灣時間 `2026-07-28T18:00:00+08:00` 後的 fight 查詢「依目標傷害」與 `targetResources.maxHitPoints`，不保存 raw events。全隊敵方承傷／敵方最大生命池總和嚴格大於 `1.15` 時標記為 `excluded`；`damage_done_summary.exploitDetails` 出現 `guid=7` 或 `Attack` 時標記為 `suspected`。不可使用泛用 `exploit:6`，因為它在正常紀錄也會大量出現。
2. 檢核結果必須寫在 `fights[].data_integrity`，其中 `hidden_from_public=true` 只會使該 fight 從 `ranking_entries`、公開排行榜、個人成績、隊伍榜與近期動態消失；report、fight、players 與其檢核證據均保留。不得把此情況轉為 `report_hidden`，也不得整份 report 刪除。
3. `ultimate_bahamut` 的多階段敵方生命池語意不能套用此倍率檢核，必須寫入 `not_applicable`，避免把正常歷史戰鬥誤判。其他無法取得最大 HP 的 fight 只能寫 `unverifiable`，除非同時有 `Attack` 標記才可隱藏為 `suspected`。
4. 這是可撤除的資料品質防護。GitHub Actions 用 `FFLOGS_FIGHT_INTEGRITY_REPORT_LIMIT` 小批量逐輪補查，`FFLOGS_FIGHT_INTEGRITY_ENABLED=false` 停止新增檢核；日後 Log 工具修正後可停止 workflow 步驟與回補腳本，但已標記的歷史 fight 必須繼續保留並隱藏，不能回填為正常或硬刪。
