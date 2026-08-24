# 程式碼責任索引

本文件是程式碼與文件之間的追溯索引。它記錄每個列管程式碼、設定、workflow 與測試檔案的主要責任；演算法細節仍應留在程式碼註解與對應主題文件，不在此複製第二套規則。

新增、移除或重新命名列管檔案時，必須同步更新本文件。變更資料契約、指令、部署或使用者功能時，還要更新表格「主要文件」指向的主題頁。

## 根目錄與進入點

| 檔案 | 責任 | 主要文件 |
| --- | --- | --- |
| `package.json` | Node 版本、相依套件、完整 npm scripts 與 lifecycle。 | [commands.md](commands.md) |
| `package-lock.json` | npm 10 鎖定的可重現相依版本。 | [getting-started.md](getting-started.md) |
| `requirements.txt` | FFLogs／環境讀取與 Playwright 診斷所需 Python 套件。 | [getting-started.md](getting-started.md) |
| `.python-version` | 本機工具預設 Python 3.11。 | [getting-started.md](getting-started.md) |
| `.env.example` | 本機與 CI 可用環境變數範本，不含真實秘密。 | [getting-started.md](getting-started.md)、[deployment.md](deployment.md) |
| `.gitignore` | 排除憑證、Data／Users 產物、快取、虛擬環境、建置輸出與本機稽核檔。 | [data-contracts.md](data-contracts.md) |
| `.gitattributes` | 統一程式碼換行；Data snapshot 會另產生禁止換行轉換的屬性檔以保護 manifest 位元組。 | [deployment.md](deployment.md) |
| `index.html` | Vite HTML 入口、站台層 SEO／OG、favicon、manifest 與 JSON-LD。 | [routing-and-seo.md](routing-and-seo.md) |
| `vite.config.js` | Vue plugin、`base_path` 與 dev／preview allowed hosts。 | [getting-started.md](getting-started.md)、[routing-and-seo.md](routing-and-seo.md) |
| `README.md` | 專案入口與文件導覽，不承載完整演算法規則。 | [docs/README.md](README.md) |
| `AGENTS.md`、`CLAUDE.md` | 鎖定的協作準則與已確立技術決策。 | 本身 |

## 前端應用

### 應用殼層與頁面

| 檔案 | 責任 |
| --- | --- |
| `src/main.js` | 初始化分析並掛載 Vue app。 |
| `src/analytics.js` | 依 `VITE_GA_*` 選填載入 GA4 與送出事件。 |
| `src/App.vue` | 建立 app context、非同步載入頁面、共用 Header／Footer／搜尋歷程與 Honey 裝飾。 |
| `src/pages/RankingPage.vue` | 排行榜桌機／手機表格、篩選、排序、分頁與職能欄位。 |
| `src/pages/GlobalStatsPage.vue` | 全服概要、職業／伺服器分布、進度與資料狀態。 |
| `src/pages/UserProfilePage.vue` | 個人成績、簡表、趨勢、歷史、支援統計、徽章與成就手冊入口。 |
| `src/pages/ComparePage.vue` | 兩名玩家的職能／副本比較。 |
| `src/pages/TeamRankingsPage.vue` | 八人隊伍榜、版本切片與成員組成。 |
| `src/pages/ServerComparePage.vue` | 兩個伺服器的收錄、職能、職業與副本比較。 |
| `src/pages/JobAnalysisPage.vue` | 職能／職業分位、分布、代表紀錄與分析。 |
| `src/pages/ActivityPage.vue` | 最新紀錄、活躍度、每日 Logs／通關趨勢與版本事件。 |
| `src/pages/ReportStatusPage.vue` | 常見問題、report 靜態索引比對、Apps Script 即時查詢與送單。 |
| `src/pages/HoneyFansPage.vue` | Honey B. Lovely 近 7 天粉絲榜、歷史統計與活動隊伍榜。 |

頁面功能以 [features.md](features.md) 為主，網址與靜態 fallback 以 [routing-and-seo.md](routing-and-seo.md) 為主。

### 共用元件

| 檔案 | 責任 |
| --- | --- |
| `src/components/AppHeader.vue` | 主導覽、搜尋、設定、公告入口與 Telegram 連結。 |
| `src/components/AppFooter.vue` | 站台說明、資料來源、作者／社群連結。 |
| `src/components/PageNavigation.vue` | 桌機與手機頁面導覽。 |
| `src/components/EncounterMenu.vue` | 依分類與零式量級分組的副本選單。 |
| `src/components/JobIcon.vue` | 職業／職能 icon 與失敗 fallback。 |
| `src/components/RankingCompactValue.vue` | K／M 縮寫、完整值提示與鍵盤／觸控互動。 |
| `src/components/ReportDetailDialog.vue` | 排行榜與個人成績共用的報告彈窗及來源分頁。 |
| `src/components/ReportExternalLinks.vue` | FFLogs、xivanalysis、ffreplay 連結呈現。 |
| `src/components/PlayerSearchHistoryPanel.vue` | 搜尋欄近期玩家歷程。 |
| `src/components/PlayerSearchHistoryDialog.vue` | 搜尋歷程管理、刪除與清除。 |
| `src/components/AchievementHandbook.vue` | 固定分類、進度與全站持有率的成就彈窗。 |
| `src/components/AnnouncementCenter.vue` | 公告通知、列表、關閉狀態與焦點管理。 |
| `src/components/AnnouncementMarkdown.vue` | 將允許的公告 Markdown token 呈現為安全元件。 |
| `src/components/HoneyFansFloatingButton.vue` | Honey 頁面浮動入口。 |

### 狀態、領域與工具

| 檔案 | 責任 |
| --- | --- |
| `src/composables/useRankingApp.js` | 全站狀態協調、各靜態資料載入、篩選與跨頁 computed；不應再放可獨立純函式。 |
| `src/composables/useTheme.js` | 深／亮主題與瀏覽器儲存。 |
| `src/composables/rankingApp/context.js` | Vue provide／inject key 與安全注入。 |
| `src/composables/rankingApp/defaults.js` | 預設副本、排序、職能、版本、作者資訊與選項。 |
| `src/composables/rankingApp/useRankingData.js` | 排行榜列正規化、排序值與報告細節按需載入。 |
| `src/domain/jobs.js` | 職業／職能名稱、分組、色彩、icon 路徑與預熱。 |
| `src/domain/encounters.js` | 副本分類順序與選單分組。 |
| `src/utils/fetchJson.js` | 主站 JSON 的一致錯誤處理。 |
| `src/utils/publicData.js` | 主站、Users repo、fallback CDN 與索引資料基底 URL。 |
| `src/utils/userData.js` | 玩家搜尋輸入、歷程、索引命中、Users repo fallback 與 hidden delta 載入。 |
| `src/utils/urlState.js` | History API 乾淨路徑、query 白名單、舊網址解析與分享狀態。 |
| `src/utils/shareMeta.js` | 動態 title、canonical、description、OG／Twitter meta 與分享網址事件。 |
| `src/utils/reportLinks.js` | FFLogs、xivanalysis、ffreplay URL 組合。 |
| `src/utils/reportStatus.js` | report URL 解析、索引解碼、排程提示、JSONP 查詢與送單。 |
| `src/utils/formatters.js` | 傷害、百分比、分位、日期、通關時間與總量格式。 |
| `src/utils/statsDisplay.js` | 全服統計職業範圍計數與職能分組。 |
| `src/utils/userProfileSorting.js` | 個人成績代表列與 PR／前 N% 排序。 |
| `src/utils/userProfileClearSummary.js` | 簡表版本、可見副本、零式量級與代表成績。 |
| `src/utils/userProfileBadges.js` | 固定成就 ID、條件、優先順序、目錄分類與進度群組。 |
| `src/utils/userProfileTrend.js` | 個人成績趨勢條件、時間範圍、資料點與版本線。 |
| `src/utils/activityTimelineAnnotations.js` | 近期動態與個人成績趨勢共用的台／國際服版本事件。 |
| `src/utils/announcements.js` | 公告 schema 正規化、狀態、localStorage 與受限 Markdown 解析。 |
| `src/utils/siteFeatures.js` | 作者、社群、Telegram、GCD 與 Honey UI 暫時性旗標。 |
| `src/utils/viewHelpers.js` | 排名色彩、比例條、熱力格、趨勢點與圖片 fallback。 |

### 樣式

`src/styles/app.css` 只作為下列表格所列拆分樣式的匯入入口，不應重新累積畫面規則：

| 檔案 | 責任 |
| --- | --- |
| `src/styles/tokens.css` | 色彩、字級、間距與主題 token。 |
| `src/styles/layout-shell.css` | App shell、Header、Footer、導覽、公告與共用版面。 |
| `src/styles/controls.css` | 按鈕、輸入、選單、篩選與設定控制項。 |
| `src/styles/tables-dialogs.css` | 排行表格、緊湊值、報告與共用彈窗。 |
| `src/styles/pages-analytics.css` | 全服統計、比較、隊伍、伺服器、職業與近期動態。 |
| `src/styles/pages-profile.css` | 個人成績、簡表、趨勢、徽章與成就手冊。 |
| `src/styles/pages-report-status.css` | 常見問題與 FFLogs 檢查工具。 |
| `src/styles/pages-honey-fans.css` | Honey 頁面、背景、動畫與活動榜。 |
| `src/styles/responsive.css` | 跨頁手機／窄螢幕覆寫。 |

## 正式資料抓取層

| 檔案 | 責任 | 主要文件 |
| --- | --- | --- |
| `scripts/fetch_fflogs.py` | 正式排行榜 OAuth、限流／重試、淺層與深層掃描、mixed report 分派、繁中服玩家判定、來源寫入、公開重建與 report 狀態巡檢。 | [data-pipeline.md](data-pipeline.md) |
| `scripts/fflogs_pipeline/graphql_queries.py` | 集中 GraphQL 查詢字串與 alias builder；不管理掃描狀態。 | [data-pipeline.md](data-pipeline.md) |
| `scripts/fflogs_pipeline/state_store.py` | Python 的 state／checked-report 分片讀寫與合併。 | [data-contracts.md](data-contracts.md) |
| `scripts/fflogs_pipeline/support_metrics.py` | Healing table、坦克承傷／防護與有效減傷時窗純計算。 | [data-pipeline.md](data-pipeline.md) |
| `scripts/fflogs_pipeline/__init__.py` | Python 子套件標記。 | 本文件 |
| `scripts/fetch_honey_b_fans.py` | 獨立掃描 M2S Honey 趣味紀錄並建置近 7 天公開資料。 | [data-pipeline.md](data-pipeline.md) |

`fetch_honey_b_fans.py` 與 Apps Script 會使用 FFLogs，但不屬於正式排行榜來源入口；回補／診斷腳本則重用 `fetch_fflogs.py` 的認證與查詢能力。Vue 前端仍禁止直接呼叫 FFLogs。

## 資料建置與契約

| 檔案 | 責任 |
| --- | --- |
| `scripts/build_user_data.mjs` | 由來源分片聚合使用者、成就統計、全服統計、近期動態、隊伍榜與伺服器對比。 |
| `scripts/build_ranking_table_data.mjs` | 建立排行榜薄索引、完整報告細節、支援統計欄位、搭檔與 hidden delta。 |
| `scripts/build_report_status_index.mjs` | 將報告細節壓縮成 FAQ 使用的 report／fight 查詢索引。 |
| `scripts/build_public_status_data.mjs` | 由內部更新戳記輸出可公開的更新與排程摘要。 |
| `schemas/public_data_contracts.mjs` | 可執行公開 schema、typedef 與共用契約驗證。 |
| `scripts/validate_data.mjs` | 套用契約並驗證來源／衍生資料、分片、索引、raw 禁止欄位與統計一致性。 |
| `scripts/write_file_with_retry.mjs` | 對 Windows 暫時性檔案鎖定做有上限的通用檔案寫入重試；目前供公開 JSON 建置器使用。 |

欄位新增順序固定為：資料來源／建置器 → `schemas/public_data_contracts.mjs` → 前端讀取端 → 對應測試 → [data-contracts.md](data-contracts.md)。

## GCD 覆蓋率

| 檔案 | 責任 |
| --- | --- |
| `scripts/gcd_coverage_core.py` | XIVAPI datamining 載入、Casts graph／raw events 解析、速度反推、downtime 與 xivanalysis-like ABC 計算。 |
| `scripts/xivanalysis_gcd_rules.py` | Action.csv 無法表達的技能 lock／recast 例外與 xivanalysis 來源 commit。 |
| `scripts/backfill_gcd_coverage.py` | 掃描既有玩家／report 候選、查 FFLogs 並寫回本地 GCD 衍生結果。 |
| `scripts/backfill_gcd_coverage_xivanalysis.py` | 以 Playwright 讀 xivanalysis 頁面值的人工診斷與 fallback。 |
| `scripts/audit_xivanalysis_gcd_sample.py` | 固定 seed 抽樣、職業覆蓋補抽、外站比對與稽核報告。 |
| `scripts/recompute_xivanalysis_gcd_audit.py` | 依既有目標與快取重算稽核結果。 |
| `scripts/run_gcd_audit.py` | 提供固定、可記錄 log 的稽核 wrapper。 |
| `scripts/seed_xivanalysis_gcd_cache.py` | 由既有證據或查詢預填外站稽核快取。 |
| `scripts/build_gcd_recompute_manifest.mjs` | 彙整 top-ranking 重算證據完成度。 |
| `scripts/build_gcd_player_sample_manifest.mjs` | 彙整逐職業玩家樣本證據完成度。 |
| `scripts/check_missing_gcd_report_status.py` | 只查缺少 GCD report 的可見度，永久不可讀時標記 hidden。 |

演算法、raw-events 副本與人工稽核限制見 [data-pipeline.md](data-pipeline.md) 的 GCD 章節。

## 戰鬥完整性

| 檔案 | 責任 |
| --- | --- |
| `scripts/fight_integrity.py` | fight 層完整性結果、版本與純判定；不讀寫檔案、不直接呼叫 API。 |
| `scripts/fight_integrity_baselines.py` | 切點前完整繁中隊伍 P99 的本地預篩；不能單獨排除 fight。 |
| `scripts/fight_integrity_known_capacity.py` | 固定敵方承傷範圍、逐 NPC profile 與單向上限規則。 |
| `scripts/fight_integrity_cache.py` | 不進 Git 的匿名化最小量測快取與來源指紋。 |
| `scripts/backfill_fight_integrity.py` | 選取既有候選、查 FFLogs Target Damage／HP／Attack 證據並寫回。 |

設定來源為 `config/fflogs.json`、`config/fight_integrity_baselines.json` 與 `config/fight_integrity_known_enemy_hp.json`；業務規則見 [data-pipeline.md](data-pipeline.md) 與 [data-contracts.md](data-contracts.md)。

## 維護、同步與部署工具

| 檔案 | 責任 |
| --- | --- |
| `scripts/backfill_missing_fflogs_data.py` | 補齊既有 fight/player 必要欄位與支援統計；重用正式解析規則。 |
| `scripts/compact_ranking_data.py` | 移除可重查 raw 欄位並依 report 重新分片。 |
| `scripts/compact_state.py` | 壓縮 state／checked-report 分片並檢查 Git 單檔上限。 |
| `scripts/state_store.mjs` | Node.js 讀取主 state 與 checked-report 分片。 |
| `scripts/data_repository.mjs` | Data repo hydrate、verify、publish、manifest、append-only 守恆與 EOL 修復。 |
| `scripts/sync_user_leaderboard_repo.mjs` | 將使用者主檔與細節同步為 Users repo 單一 root snapshot。 |
| `scripts/read_fflogs_refresh_queue.mjs` | 讀 Google Sheet 待處理 report code 並輸出給 workflow。 |
| `scripts/complete_fflogs_refresh_queue.mjs` | 依公開／hidden／來源／state 與 fight 完整性相容證據回寫 Google Sheet 終止狀態。 |
| `scripts/google_sheets_service_account.mjs` | Google service-account JWT、token 與 Sheets 讀寫共用函式。 |
| `scripts/build_spa_fallback.mjs` | route fallback、SEO／OG PNG、sitemap、robots 與選填玩家頁。 |
| `scripts/prune_pages_user_data.mjs` | 從 Pages artifact 移除高基數玩家 JSON／頁面／OG。 |
| `scripts/generate_site_icons.mjs` | 由 SVG 唯一來源產生 favicon 與 PWA icon。 |
| `scripts/setup_og_fonts.sh` | 在 Actions 下載／抽取／註冊 OG 所需 Noto CJK 字型。 |
| `scripts/audit_pages_payload.mjs` | 量測 Pages artifact 區段、執行 target／hard limit 與寫入趨勢。 |
| `scripts/audit_mixed_report_dispatch.mjs` | 稽核 mixed report revision 套用率與歷史掃描進度。 |
| `scripts/apply_cloudflare_rules.mjs` | 建立或更新 Cache Rules、Facebook bot 例外與選填 Rate Limiting。 |
| `scripts/purge_cloudflare_cache.mjs` | 部署後 scoped／everything purge 與 Step Summary。 |
| `scripts/estimate_cloudflare_capacity.mjs` | 依 gzip／brotli 體積與 HIT ratio 估算 Pages origin 流量。 |
| `scripts/run_python.mjs` | 跨平台尋找並驗證 Python 3.11+ 後轉交參數。 |

## 設定、靜態資產與外部輔助程式

| 檔案／目錄 | 責任 |
| --- | --- |
| `config/encounters.json` | 副本穩定 key、FFLogs ID、掃描時窗、版本切點與簡表領域設定。 |
| `config/game_versions.json` | 繁中服競技版本順序與開放時間。 |
| `config/fflogs.json` | 非敏感的掃描、限流、回補、排除與完整性設定。 |
| `config/fight_integrity_baselines.json` | 歷史完整隊伍 P99 預篩設定。 |
| `config/fight_integrity_known_enemy_hp.json` | 已知承傷範圍、硬上限與逐目標 profile。 |
| `config/site.json` | 正式站台 URL、Vite base path 與 allowed hosts。 |
| `public/favicon.svg` | 全部站台 icon 的設計來源。 |
| `public/favicon-*.png`、`public/favicon.ico`、`public/apple-touch-icon.png`、`public/icons/site/` | 由 icon 腳本產生並由 HTML／manifest 引用的站台 icon。 |
| `public/site.webmanifest` | PWA icon 與站台資訊。 |
| `public/icons/jobs/` | 職業／職能 icon 靜態資產。 |
| `public/og-image.png` | 站台層級社群預覽圖。 |
| `public/author.png`、`public/telegram.png` | 作者與 Telegram UI 靜態圖片。 |
| `docs/gcd_xivanalysis_audit*.json` | 人工抽樣對齊 xivanalysis 的已提交稽核證據；不是網站公開資料契約。 |
| `apps-script/fflogs-report-status/Code.gs` | 站務端 FFLogs 可讀狀態查詢、JSONP 與 Google Sheet 送單。 |
| `apps-script/fflogs-report-status/appsscript.json` | Apps Script runtime、時區與 OAuth scope。 |

設定欄位見 [config/README.md](../config/README.md)，Apps Script 部署見 [專用 README](../apps-script/fflogs-report-status/README.md)。

## GitHub Actions

| 檔案 | 責任 |
| --- | --- |
| `.github/workflows/update_rankings.yml` | push、每小時 17／47 分與手動觸發；hydrate、抓取、回補、建置、驗證、Data／Users repo 發布、Pages 部署與 Cloudflare purge。 |
| `.github/workflows/emergency_deploy.yml` | 手動以既有 Data snapshot 重建並部署，不抓 FFLogs、不發布新資料。 |

完整步驟、Secrets、Variables 與重試行為見 [deployment.md](deployment.md)。

## 測試檔案

測試檔依被保護的責任分組；完整 npm 對應見 [commands.md](commands.md)。

| 檔案 | 保護範圍 |
| --- | --- |
| `scripts/test_fetch_fflogs_batch.py` | 正式掃描設定、批次 alias、mixed report、重試、checkpoint 與欄位解析。 |
| `scripts/test_support_metrics.py` | Healing、護盾、減傷封包、Status namespace 與事件聯集。 |
| `scripts/test_backfill_support_metrics.py` | 支援統計候選、版本與 stateful 游標。 |
| `scripts/test_gcd_coverage_backfill.py` | GCD 候選、graph／raw 計算、速度與副本／職業例外。 |
| `scripts/test_xivanalysis_gcd_backfill.py` | xivanalysis 頁面解析、限流、快取與 fallback。 |
| `scripts/test_missing_gcd_report_status.py` | 缺 GCD report 可見度與 hidden 標記。 |
| `scripts/test_fight_integrity.py` | 完整性狀態、門檻、版本與 fight-hash 傳播。 |
| `scripts/test_fight_integrity_baselines.py` | 歷史預篩載入與判定。 |
| `scripts/test_fight_integrity_known_capacity.py` | 固定承傷範圍、硬上限與逐目標 profile。 |
| `scripts/test_fight_integrity_cache.py` | 最小快取 schema、指紋、原子寫入與隱私邊界。 |
| `scripts/test_fight_integrity_backfill.py` | 完整性候選、FFLogs 查詢、離線重判與 hidden。 |
| `scripts/test_honey_b_fans.py` | Honey 掃描、去重、7 天窗、歷史與活動榜。 |
| `scripts/test_compact_state.py` | state 壓縮、checkpoint 守恆與大小限制。 |
| `scripts/test_state_store.py` | Python state 分片讀寫與合併。 |
| `scripts/test_build_user_data.mjs` | 使用者身分、去重、分位、版本、成就、活動與統計。 |
| `scripts/test_build_ranking_table_data.mjs` | 薄索引、報告細節、遊戲版本、支援欄位與搭檔。 |
| `scripts/test_frontend_data_contract.mjs` | 前端資料邊界、URL、元件引用、公開 schema 與 no-direct-FFLogs 規則。 |
| `scripts/test_data_conservation.mjs` | 來源、公開底稿、hidden delta、使用者與報告來源守恆。 |
| `scripts/test_data_repository.mjs` | Data repo 單一 snapshot、manifest、hydrate 與 append-only 阻擋。 |
| `scripts/test_sync_user_leaderboard_repo.mjs` | Users repo 空白初始化、root snapshot、收斂與 lease。 |
| `scripts/test_fflogs_refresh_queue.mjs` | 待處理 Sheet 欄位、report code、終止狀態、fight 完整性版本相容與錯置修復。 |

## 變更時應同步哪份文件

| 變更 | 必須同步檢查 |
| --- | --- |
| 新增頁面、篩選、偏好或使用者可見規則 | `features.md`、`routing-and-seo.md`、本文件 |
| 新增／修改 npm script | `commands.md`、`package.json`、必要時 `getting-started.md` |
| 新增公開 JSON 或欄位 | `data-contracts.md`、schema、建置器、前端讀取、測試、本文件 |
| 修改 FFLogs 查詢或掃描 | `data-pipeline.md`、`config/README.md`、測試、本文件 |
| 修改副本 key／版本／開放時間 | `config/README.md`、`data-contracts.md`，並先檢查歷史相容性 |
| 修改 Actions、Secrets、Variables 或排程 | `deployment.md`、`.env.example`（若適合本機）、本文件 |
| 修改 Cloudflare 規則 | `cloudflare-github-pages.md`、`deployment.md`、本文件 |
| 新增／刪除程式碼或測試檔 | 本文件；若責任改變再更新對應主題文件 |
