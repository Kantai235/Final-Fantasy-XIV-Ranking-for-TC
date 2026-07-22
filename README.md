# FFXIV 繁中服排行榜

Final Fantasy XIV 繁中服排行榜是一個以 FFLogs 公開資料為來源的 Vue 3 / Vite 靜態網站，用來整理繁中服玩家在零式、極、幻、滅與絕本中的公開通關成績。

專案由兩個主要部分組成：

- 前端網站：瀏覽排行榜、全服統計、個人成績單、玩家比較、隊伍榜、伺服器對比、職業分析、近期動態、常見問題與 Honey B. Lovely 粉絲榜趣味頁。
- 資料管線：透過 FFLogs GraphQL API 抓取報告，篩選繁中服玩家，建置排行榜與前端需要的靜態 JSON。

> 這是非官方社群工具，資料來自 FFLogs 公開報告；顯示結果不代表遊戲內完整人口或所有通關紀錄。

## 快速開始

需求環境：

- Node.js 20+（GitHub Actions 固定使用 Node.js 24）
- Python 3.11+
- FFLogs OAuth Client Credentials

安裝依賴：

```bash
npm install
npm run python:venv
npm run python:install
```

`npm run python:install` 與所有 Python 相關 npm scripts 會優先使用 `.venv/bin/python`，也可用 `FFXIV_TC_PYTHON=/path/to/python3.11` 指定直譯器；專案需求為 `.python-version` 宣告的 Python 3.11+。

設定本機環境變數：

```bash
cp .env.example .env
```

在 `.env` 填入至少一組 FFLogs OAuth 憑證：

```env
FFLOGS_CLIENT_ID=your_client_id
FFLOGS_CLIENT_SECRET=your_client_secret
```

常用驗證指令：

```bash
npm run build:user-data
npm run validate:data
npm run check
```

本機開發伺服器可用：

```bash
npm run dev
```

代理協作者請注意：除非使用者明確要求，請不要自行啟動 Vite 開發伺服器。

## 功能摘要

- 依副本查看排行榜，支援伺服器、職業類型、職業、關鍵字與排序篩選。
- 玩家搜尋欄支援本機搜尋歷程，下拉顯示最近 8 筆，編輯視窗最多保存 100 筆。
- 同名角色若分屬不同伺服器，會以「角色名稱 + 伺服器」拆成不同個人成績單；目前不再自動處理轉服合併。
- 顯示 DPS、rDPS、aDPS、Active、GCD 覆蓋率、通關時間與紀錄時間。
- 個人成績單可查看各副本最佳紀錄、歷史紀錄、同職分位與常同場隊友；也可在查詢列右側開啟「簡表模式」，以零式、絕、極、幻、滅橫列顯示所有絕本、所有極本與目前高難副本。簡表可切換繁中服遊戲版本，僅顯示該版本已開放且尚未輪替關閉的副本，以及下一版本開放前完成的戰鬥；已公告的未來版本會在開放時間前維持待開放、時間到達後自動可選。零式會列出該版本已開放量級，預設選取最新量級，並可切換查看各量級第 1～4 層。某量級四層皆有該版本有效通關時，該量級按鈕會亮起彩色勾勾；量級內各樓層仍顯示有效紀錄的職業與跨職業最高 PR，只有過版紀錄則顯示灰色勾勾。「尚未收錄」不代表玩家未通關。同職分位預設顯示整數 PR 值，也可由使用者端偏好切換為「前 N%」，PR 模式會讓代表列、分位亮點與歷史列優先依 PR 值排序。
- 玩家比較、隊伍榜、伺服器對比、職業分析與近期動態皆由靜態資料產生；近期動態也提供每日 Logs 曲線、零式、極、幻、滅、絕分類占比，以及台服與國際服改版時間標註，桌面預設近 90 天、手機預設近 30 天，可切換副本、日期範圍與 Logs、通關場次等統計口徑。
- 常見問題頁整理 Telegram 群組常見回報，包含更新時間、過版紀錄、GCD 覆蓋率、同名角色與公開狀態；其中的 FFLogs 檢查工具可貼上 report 網址或 report code，比對 `public/data/report_status_index.json` 與 `public/data/update_status.json`，判斷目前公開資料是否已收錄、指定 fight 是否命中，以及剛上傳或歷史補查紀錄大約會落在哪個排程窗；「查詢公開狀態」按鈕會透過 Apps Script Web App 確認 FFLogs API 目前是否可讀。Public 且可讀的 report 可寫入 Google Sheet 待收錄名單；若本站已收錄、但 FFLogs 明確不可公開讀取，則可要求重新確認公開狀態，下一輪 workflow 會重新排查，確認仍不可讀時把既有紀錄標記 hidden。待處理名單只保存 report code，不保留指定 fight。
- Honey B. Lovely 粉絲榜以獨立趣味資料呈現 M2S `心醉魂迷：奴役` 衍生紀錄；本期榜單、吃心心數、戰鬥次數與報告只計近 7 天，最新收錄紀錄顯示 5 筆、最新加入粉絲顯示 16 筆。頁面可用「超高難度」開關切換為自台灣時間 2026-05-30 00:00:00 起算的通關團隊榜，依單場全隊奴役總次數排序，來源歷史紀錄仍保留用於連續入榜與追溯統計，不混入正式排行榜。
- 支援深色 / 亮色主題，並依目前頁面的職業或職能篩選切換主色調。
- 設定視窗可依個人偏好顯示或隱藏各頁的說明提示按鈕，預設為顯示。
- 支援全域公告通知，公告內容由 `public/data/announcements.json` 隨 commit 更新，使用者關閉後不再主動顯示。
- GitHub Actions 可定時抓取 FFLogs 與 Honey B. Lovely 粉絲榜、建置資料並部署 GitHub Pages，也提供不抓 FFLogs 的手動緊急部署通道。

## 文件地圖

README 只保留入口與最小操作脈絡，完整說明請依主題閱讀：

| 文件 | 內容 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文件索引與閱讀順序。 |
| [docs/getting-started.md](docs/getting-started.md) | 安裝、環境變數、常用指令與本機驗證。 |
| [docs/architecture.md](docs/architecture.md) | 專案結構、三層責任邊界與前端頁面脈絡。 |
| [docs/data-pipeline.md](docs/data-pipeline.md) | FFLogs 抓取、資料建置、GCD 覆蓋率、手動補抓與維護流程。 |
| [docs/data-contracts.md](docs/data-contracts.md) | JSON 資料契約、去重規則、hidden report、版本切點與 append-only 原則。 |
| [docs/routing-and-seo.md](docs/routing-and-seo.md) | 分享網址、乾淨路徑、SEO/OG 靜態頁與社群預覽圖。 |
| [docs/deployment.md](docs/deployment.md) | GitHub Actions、GitHub Pages、部署需求與 Cloudflare 串接摘要。 |
| [docs/cloudflare-github-pages.md](docs/cloudflare-github-pages.md) | Cloudflare CDN、Cache Rules、Rate Limiting 與 purge 細節。 |
| [apps-script/fflogs-report-status/README.md](apps-script/fflogs-report-status/README.md) | FFLogs report 即時可讀狀態查詢用 Apps Script Web App 範本。 |
| [config/README.md](config/README.md) | `config/` 設定檔欄位判讀。 |
| [data/rankings/README.md](data/rankings/README.md) | 排行榜完整資料格式與分片說明。 |

## 核心架構

本專案最重要的邊界是「抓取、建置、呈現」三層分離：

1. `scripts/fetch_fflogs.py` 是 Data Fetching Layer。它是唯一可直接呼叫 FFLogs GraphQL API 的入口，負責 OAuth、限流、重試、繁中服玩家初篩、report 狀態判定，以及 `data/rankings/` 與 `data/state.json` 的可追溯寫入；GraphQL 查詢字串集中在 `scripts/fflogs_pipeline/graphql_queries.py`，避免掃描策略與查詢文本互相纏在同一個巨型檔。
2. `scripts/build_user_data.mjs` 是 Data Building Layer。它讀取排行榜來源資料，產生個人成績單、個人成績報告細節、全服統計、近期動態、隊伍榜與伺服器對比等 `public/data/` 靜態 JSON；`build:user-data` 也會接續產生排行榜薄索引、Logs 狀態索引與公開更新狀態。正式部署時，個別玩家成績單 JSON 會先同步到專用 users repo，再從主站 Pages artifact 移除；高頻共用的 `data/users/index.json` 會保留在主站 `/data/`，讓 Cloudflare/GitHub Pages 快取承接玩家搜尋索引請求。
3. `src/` 是 UI Presentation Layer。Vue 只讀取靜態 JSON 進行呈現、篩選與狀態管理：主站共用資料與個人成績單索引來自 Pages artifact 的 `/data/`，個別玩家成績單資料來自專用 users repo，不能直接呼叫 FFLogs API；`src/composables/rankingApp/` 承接排行榜預設值、注入 context 與排行列正規化，`src/styles/app.css` 則只作為樣式拆檔入口。

## 常用指令

| 指令 | 用途 |
| --- | --- |
| `npm run build:public-rankings` | 只重建公開排行榜與副本清單，不呼叫 FFLogs API。 |
| `npm run check:report-status -- <report code>` | 只查既有 report 目前是否仍可公開讀取；Private、刪除或無權限時將來源標記為 hidden，不推進掃描點。 |
| `npm run fetch:honey-fans` | 抓取 Honey B. Lovely 粉絲榜趣味資料，會呼叫 FFLogs API。 |
| `npm run build:honey-fans` | 由 `data/fun/honey_b_fans.json` 重建公開趣味榜 JSON，不呼叫 FFLogs API。 |
| `npm run build:ranking-tables` | 由公開排行榜產生前端薄索引與按需載入報告細節檔。 |
| `npm run build:report-status` | 由排行榜報告細節檔產生 `public/data/report_status_index.json` 與 hidden delta report 索引，供常見問題頁中的 FFLogs 檢查工具快速比對。 |
| `npm run build:public-status` | 由 `data/update_status.json` 與 `public/data/global_stats.json` 產生 `public/data/update_status.json`，公開最近資料更新與排程摘要。 |
| `npm run build:user-data` | 建置個人成績單、個人成績報告細節、全服統計、近期動態、隊伍榜、伺服器對比、排行榜薄索引、Logs 狀態索引與公開更新狀態。 |
| `npm run read:fflogs-refresh-queue` | 讀取 Google Sheet 待收錄名單，輸出本輪會送入 `FFLOGS_RETRY_REPORT_CODES` 的 report code。 |
| `npm run complete:fflogs-refresh-queue` | 依公開與 hidden 狀態索引、排行榜來源與 report 分片更新 Google Sheet 待處理列：已收錄為 `done`，已確認隱藏為 `hidden`，無通關或無繁中服玩家則寫入終止狀態與原因；也會校正待處理欄位標題與純數字的錯置訊息。 |
| `npm run validate:data` | 驗證公開資料、schema 契約、分片、全服統計、使用者索引與 Honey B. Lovely 粉絲榜完整性。 |
| `npm run compact:state` | 壓縮 `data/state.json` 的重複 checkpoint、可重建時間鏡像與 JSON 空白，保留 `checked_reports` 狀態並降低 Git blob 體積。 |
| `npm run audit:gcd:xivanalysis` | 以固定 seed 對零式、極、幻的每個副本各抽樣 10 場，若 10 場未涵蓋全職業會自動補抽缺漏職業所在戰鬥，並將本地 GCD 覆蓋率與 xivanalysis 畫面值比對；100 場外站頁面稽核使用 `--sample-size 100 --local-mode stored --tolerance 0`，必要時可搭配 `--workers`、`--exclude-report-codes` 與 `--apply-all-checked`。 |
| `npm run test:data-conservation` | 檢查排行榜薄索引、細節檔、使用者檔與 hidden delta 的資料守恆。 |
| `npm run audit:pages-payload` | 以 baseline 模式稽核 `dist/` 與 GitHub Pages payload 體積，只在超過硬上限時失敗，可用 `-- --write-history <path>` 記錄趨勢。 |
| `npm run audit:pages-payload:strict` | 以與 GitHub Actions 相同的 strict 模式稽核 payload，任一項超過 target 就失敗；workflow 會寫入 `data/pages_payload_history.jsonl`。 |
| `npm run audit:mixed-report-dispatch` | 統計 mixed report 分派版本在已知歷史 report 的覆蓋率與歷史補查游標進度；GitHub Actions 會輸出到 Step Summary。 |
| `npm run prune:pages-user-data` | 從 `dist/` 移除個別玩家成績單 JSON、逐玩家靜態分享頁與玩家 OG 圖，保留 `data/users/index.json` 以模擬正式 Pages artifact。 |
| `npm run check` | 執行 Python 與 Node.js 語法檢查。 |
| `npm test` | 執行資料管線、GCD、資料建置與前端資料契約測試。 |
| `npm run build` | 完整建置靜態網站到 `dist/`。 |
| `npm run sync:data -- --dry-run` | 同步 GitHub Actions 與本機資料前的安全預覽。 |
| `npm run python -- --version` | 顯示 npm scripts 解析到的 Python 直譯器版本。 |
| `npm run python:venv` | 使用可用的 Python 3.11+ 建立 `.venv`。 |
| `npm run python:install` | 用專案 Python 直譯器安裝 `requirements.txt`。 |

更多指令情境請看 [docs/getting-started.md](docs/getting-started.md) 與 [docs/data-pipeline.md](docs/data-pipeline.md)。

## 維護原則

- `config/encounters.json` 的 `key`、`data/state.json` 的 report 狀態與 `data/rankings/` 歷史資料都是 append-only 資產，不可任意改名、硬刪或覆寫。
- `.env` 內的 FFLogs 與 Cloudflare 憑證是敏感資訊，不應提交到版本控制，也不要印到 Log。
- 若新增前端畫面需要新的統計欄位，請先擴充資料建置層，再讓 Vue 讀取新的靜態 JSON。
- Honey B. Lovely 粉絲榜來源在 `data/fun/honey_b_fans.json`，公開輸出在 `public/data/fun/honey_b_fans.json`；它是獨立趣味資料，不屬於正式 `data/rankings/` schema。公開榜單、粉絲報告與本期 `records` 只計近 7 天，歷史紀錄仍留在來源檔並輸出 `historical_*`、連續入榜週數與自台灣時間 2026-05-30 00:00:00 起算的活動 `team_rankings`；正式 workflow 會執行 `npm run fetch:honey-fans` 抓新資料，再用 `npm run build:honey-fans` 整理公開 JSON。
- `data/state.json` 會以緊湊 JSON 保存大量 `checked_reports`，避免為了通過 GitHub 100 MiB 單檔限制而刪除跨輪略過依據；正式 workflow 會在資料 commit 前執行 `npm run compact:state -- --max-bytes 104857600`。`processed_at_iso` 不再作為 report checkpoint 必要欄位，因為它可由 `processed_at` 毫秒時間重建。
- 既有 report 的公開狀態巡檢以 report code 為單位：尚未巡檢時優先選較新的 report，之後依來源分片保存的 `report_status_checked_at` 輪替。FFLogs 回傳 `visibility=Private`、report 不存在或封存不可讀時，來源 report 會標記 hidden，正常公開產物不再列出該紀錄；完整追溯則保留於 hidden delta。
- GitHub Actions 的 FFLogs 排行榜抓取步驟預設設定 `FFLOGS_MAX_RUNTIME_SECONDS=6000` 與 `FFLOGS_RUNTIME_GRACE_SECONDS=900`，可由 repo variables 覆寫。這讓 FFLogs 憑證全數進入長冷卻時，`fetch_fflogs.py` 能先保留 `active_scan` 續跑位置並正常進入後續資料建置與 commit，避免 GitHub-hosted runner 直接取消整個 job。
- GitHub Actions 會先用 `FFLOGS_RECENT_GCD_BACKFILL_REPORT_LIMIT` 控制的非 stateful GCD 補洞追最新候選，再用 `FFLOGS_GCD_BACKFILL_REPORT_LIMIT` 控制的 stateful 回補從固定 cutoff 往舊追；前者處理 cutoff 後空洞，後者處理歷史追平。
- GitHub Actions checkout 只抓目前分支的淺層 partial clone；這個資料 repo 的完整歷史 pack 已非常大，正式更新與緊急部署都不應改回 `fetch-depth: 0`，避免 runner 在 checkout 階段耗盡磁碟。
- GitHub Actions 以 Node.js 24 執行前端與資料建置，官方 actions 也需使用支援 Node 24 的 major 版本；Pages 部署若遇到 `syncing_files` 後的暫時性失敗，workflow 會等待 60 秒後重試一次。
- 正式 Pages artifact 只保留 `dist/data/users/index.json`，不保留個別玩家成績單 JSON、`dist/data/user-entry-details`、hidden 使用者差量 JSON、逐玩家靜態分享頁與 `dist/og/users` 玩家 OG 圖；前端仍由 `/user` route 與 users 專用 repo 讀取個別玩家成績單。這是為了讓高頻搜尋索引吃到主站 CDN 快取，同時避免 GitHub Pages 在 `syncing_files` 階段同步上萬個小檔時失敗。
- 若 GitHub Actions 與本機同時產生資料，先跑 `npm run sync:data -- --dry-run`；看到 `REMOVAL` 或 `CONFLICT` 時不可自動套用。
- 文件或註解變更仍需至少執行 `npm run check` 與 `npm run build:user-data`，若碰到 Honey B. Lovely 粉絲榜流程也要執行 `npm run build:honey-fans`。
