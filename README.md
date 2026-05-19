# FFXIV 繁中服排行榜

Final Fantasy XIV 繁中服排行榜是一個以 FFLogs 公開資料為來源的 Vue 3 / Vite 網站，用來整理繁中服玩家在零式、極、幻與絕本中的公開通關成績。

專案包含兩個主要部分：

- 前端網站：瀏覽排行榜、全服統計、個人成績單、玩家比較、隊伍榜、伺服器對比、職業分析與近期動態。
- 資料管線：透過 FFLogs API 抓取報告，篩選繁中服玩家，產生排行榜、個人成績單、全服統計、近期動態、隊伍榜與伺服器對比資料。

> 這是非官方社群工具，資料來自 FFLogs 公開報告；顯示結果不代表遊戲內完整人口或所有通關紀錄。

## 功能

- 依副本查看排行榜，支援伺服器、職業類型、職業、關鍵字與排序篩選。
- 顯示 DPS、rDPS、aDPS、Active、通關時間與紀錄時間。
- 個人成績單可查看玩家各副本最佳紀錄、歷史紀錄與常同場隊友，並依職能或職業篩選成績與趨勢。
- 個人成績單會顯示同副本同職業 rDPS 分位、樣本排名、中位數差距與個人分位亮點。
- 玩家比較可選擇防護、治療、近戰、遠程物理或遠程魔法職業，並排比較兩名玩家的公開成績。
- 隊伍榜可查看同場 8 人公開紀錄的副本最速通關、隊伍 rDPS 與成員組成。
- 伺服器對比可並排查看兩個伺服器的收錄玩家、副本通關、職能比例、熱門職業與副本落點。
- 全服統計可查看伺服器分布、職業分布、零式進度概覽與資料狀態，職業範圍選擇沿用排行榜的職業選單。
- 職業分析可查看特定職業在副本、伺服器、副本別 rDPS 與代表紀錄中的分布。
- 近期動態可查看最新公開成績、刷新個人最佳、新收錄玩家、伺服器活躍與副本活躍。
- 支援深色 / 亮色主題，並依目前頁面的職業或職能篩選切換主色調。
- GitHub Actions 可定時抓取 FFLogs 並提交更新後的資料。

## 技術棧

- Node.js 20+
- Vue 3
- Vite
- Python 3.11+
- FFLogs GraphQL API

## 專案結構

```text
.
├── src/
│   ├── App.vue                # 前端殼層，負責組裝頁首、頁籤與各頁元件
│   ├── components/            # 跨頁共用元件
│   ├── composables/           # 前端狀態、篩選、排序與資料讀取邏輯
│   ├── domain/                # FFXIV 職業、職能等領域設定
│   ├── pages/                 # 依頁面切分的主要呈現元件
│   ├── styles/                # 全站樣式
│   ├── utils/                 # 格式化、分享網址狀態、靜態資料 URL 與 fetch 工具
│   └── main.js                # Vue 入口
├── scripts/
│   ├── fetch_fflogs.py        # 抓取並整理 FFLogs 排行榜資料
│   ├── gcd_coverage_core.py   # fetch/backfill 共用的本地 GCD 覆蓋率計算核心
│   ├── backfill_gcd_coverage.py # 以 xivanalysis 規則參照的本地 GCD 覆蓋率計算
│   ├── backfill_gcd_coverage_xivanalysis.py # 診斷用：解析 xivanalysis 頁面結果，不作為 workflow 預設
│   ├── build_user_data.mjs    # 產生個人成績單、全服統計、近期動態、隊伍榜與伺服器對比資料
│   ├── validate_data.mjs      # 驗證公開資料、分片與使用者索引完整性
│   ├── test_build_user_data.mjs # 使用 fixture 驗證資料建置規則
│   ├── test_frontend_data_contract.mjs # 驗證前端資料讀取契約與 useRankingApp 匯出
│   ├── compact_state.py       # 壓縮 state.json 中重複 checkpoint
│   └── build_spa_fallback.mjs # 為 GitHub Pages 產生 History API fallback、靜態 SEO/OG 頁與 sitemap
├── config/
│   ├── encounters.json        # 副本、FFLogs ID 與掃描起始日期
│   ├── fflogs.json            # 抓取範圍、限流、重試與手動補抓設定
│   └── site.json              # 站台網址、Vite base path 與允許 host
├── data/
│   ├── rankings/              # 原始排行榜資料
│   └── state.json             # 掃描進度與處理狀態
├── public/
│   ├── data/                  # 網站讀取的公開資料
│   ├── favicon.svg            # 網站 icon 的向量來源
│   ├── site.webmanifest       # 瀏覽器安裝與 app icon 設定
│   └── icons/jobs/            # 職業圖示
└── .github/workflows/
    └── update_rankings.yml    # 定時更新排行榜資料
```

## 給 Codex / 協作者的專案脈絡

這個專案最重要的邊界是「抓取、建置、呈現」三層分離：

1. `scripts/fetch_fflogs.py` 是 Data Fetching Layer。它查 FFLogs GraphQL、處理限流與重試、用 `masterData.actors` 判斷是否有繁中服玩家，並把可重建排行榜的 report/fight/player 脈絡寫入 `data/rankings/`。
2. `scripts/build_user_data.mjs` 是 Data Building Layer。它讀取 `data/rankings/` 與 `public/data/rankings/`，產生 `public/data/users/`、`public/data/users/index.json`、`public/data/global_stats.json`、`public/data/activity.json`、`public/data/team_rankings.json` 與 `public/data/server_compare.json`。
3. `src/` 是 UI Presentation Layer。Vue 只讀 `public/data/` 靜態 JSON，不能直接呼叫 FFLogs API，也不能在元件內重做全服統計或資料聚合。

容易誤判的資料契約：

- `config/encounters.json` 的 `enabled` 只代表下一輪 Python 爬蟲是否掃描該副本。
- `public/data/encounters.json` 才是前端選單來源。已經有歷史排行榜資料的副本即使暫停掃描，仍會保留在公開清單，避免既有排行榜與個人成績單消失。
- `data/rankings/*.json` 主檔通常只保留 `ranking_entries` 與 `report_shards`；完整 report 會在同名的 `*.reports/*.json` 分片中。
- `ranking_entries` 是去重後的扁平索引；完整追溯請讀 `reports -> fights -> players`。
- `gcd_coverage` 會逐批補在 `reports -> fights -> players`。key 不存在代表尚未嘗試；`gcd_coverage: null` 代表已嘗試但 report 已轉為 Private、刪除或無權限，避免 workflow 反覆重抓同一筆不可用資料。
- `report_hidden: true` 的 report 預設不進入一般 `public/data/` 產物；`public/data/all/` 會同步輸出完整資料鏡像，供額外檢視流程使用。
- 新資料不再保存 `fflogs_raw`、`master_data` 與 `matched_players`，避免可重查的 FFLogs raw table 讓 repo 容量快速膨脹；若需要重新推導 raw 層欄位，應以 report code 重新查 FFLogs API。
- 同一玩家同一副本同一職業的最佳成績排序規則為 rDPS 優先，平手看通關時間，再看 aDPS。
- `build_user_data.mjs` 預設以最新 `rankings_updated_at_iso` 作為 `generated_at_iso`，避免同一批資料重建時讓 `global_stats.json` 產生無意義 diff；需要指定產物時間時可設定 `FFXIV_TC_GENERATED_AT_ISO`。
- `data/state.json` 的 `checked_reports` 是跨輪快取，`processed_reports` 是單輪 checkpoint；兩者和 `data/rankings/` 都不能用硬刪或覆蓋方式整理。

開發代理注意事項：

- 修改前先檢查 `git status`。本專案常有資料管線產物處於未提交狀態，不要回復或清掉非本次任務造成的資料差異。
- 不要擅自啟動 `npm run dev` 或 Vite 開發伺服器；需要瀏覽器驗證時先取得使用者同意。
- 臨時隱藏或恢復作者相關 UI 標示、社群連結或 GCD 覆蓋率時，只調整 `src/utils/siteFeatures.js` 的 `顯示作者相關標示`、`顯示社群連結` 與 `顯示Gcd覆蓋率`。目前 `顯示Gcd覆蓋率=true`，網站會顯示 GCD 欄位；這些旗標只影響前端呈現，不改動公開資料或排行榜歷史資料結構。
- 驗證資料聚合優先跑 `npm run build:user-data`。若只是重建公開排行榜 JSON，可跑 `python scripts/fetch_fflogs.py --rebuild-public`，這個模式不會呼叫 FFLogs API。
- 驗證公開資料完整性可跑 `npm run validate:data`；它會檢查公開副本是否都有 ranking 檔案、來源分片是否存在、raw 欄位是否回流，以及全服統計、近期動態、隊伍榜、伺服器對比與使用者索引是否可讀。
- 需要同步本機與 GitHub Actions 產生的資料時，先跑 `npm run sync:data -- --dry-run`，確認沒有 `REMOVAL` 或 `CONFLICT` 再真正同步。

## 快速開始

安裝前端依賴：

```bash
npm install
```

安裝 Python 依賴：

```bash
python -m pip install -r requirements.txt
```

啟動本機開發伺服器：

```bash
npm run dev
```

預設會由 Vite 啟動本機站台，終端機會顯示可開啟的網址。

## 環境變數

複製 `.env.example` 為 `.env`，並填入 FFLogs OAuth Client Credentials：

```bash
cp .env.example .env
```

PowerShell 可改用：

```powershell
Copy-Item .env.example .env
```

必要設定：

```env
FFLOGS_CLIENT_ID=your_client_id
FFLOGS_CLIENT_SECRET=your_client_secret
```

也可以設定多組憑證以分散限流：

```env
FFLOGS_CLIENT_IDS=client_id_1,client_id_2
FFLOGS_CLIENT_SECRETS=client_secret_1,client_secret_2
```

或使用 JSON 格式：

```env
FFLOGS_CLIENT_CREDENTIALS_JSON=[{"client_id":"client_id_1","client_secret":"client_secret_1"}]
```

`.env` 內含敏感資訊，不應提交到版本控制。

可選的前端分析設定：

```env
VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX
VITE_GA_ENABLE_IN_DEV=false
```

`VITE_GA_ENABLE_IN_DEV` 只有在刻意要於 `npm run dev` 送出 GA 事件時才設為 `true`。

## 常用指令

啟動開發伺服器：

```bash
npm run dev
```

產生個人成績單、全服統計、近期動態、隊伍榜與伺服器對比資料：

```bash
npm run build:user-data
```

由 `public/favicon.svg` 重建 favicon、Apple touch icon 與 manifest icon：

```bash
npm run build:icons
```

驗證公開資料完整性：

```bash
npm run validate:data
```

執行語法檢查：

```bash
npm run check
```

執行資料管線、資料建置與前端資料契約測試：

```bash
npm test
```

其中 `npm run test:fetch-fflogs` 會確認單一 report 內多場通關戰鬥會以 GraphQL alias 批次查詢玩家成績，避免每場 fight 各自增加一個 API request。`npm run test:frontend-data` 會檢查前端資料讀取邊界、`useRankingApp()` 回傳物件的 shorthand 變數，以及分享網址狀態的相容性。它會覆蓋舊版 query 連結、`/user/{玩家}`、`/stats/{副本 key}`、`/jobs/{職業}`、`/servers/{左}/vs/{右}` 與子路徑部署情境，避免 SEO/OG 路徑調整時讓既有分享連結失效。

逐批補齊 GCD 覆蓋率時，先預覽再正式執行：

```bash
npm run backfill:gcd -- --dry-run
npm run backfill:gcd
```

`fetch_fflogs.py` 抓到新 report 時，workflow 會在每場 fight 的玩家成績整理完成後，順手查同一場 FFLogs `Casts` graph，並用 `scripts/gcd_coverage_core.py` 的本地 xivanalysis-like 演算法計算 GCD 覆蓋率；只保存 `gcd_coverage` 與 `gcd_coverage_status` 衍生結果，不保存 Casts raw events。這讓最新增量掃描與歷史巡檢補回來的新公開 logs 都能當場補 GCD。

`backfill_gcd_coverage.py` 則保留為修補既有歷史資料的手動工具。它會依通關時間由新到舊挑選缺少 `gcd_coverage` key，或仍停在舊版 `calculation_version` 的玩家，預設每輪 2000 筆。執行時會先輸出待補筆數、需重算筆數、已為 null 的筆數與本輪選取筆數，更新過程也會逐筆顯示 `[目前/本輪總數]` 進度。同一個 report/fight 會優先只查一次整場 FFLogs `Casts` graph，再於本地依玩家 `sourceID` 切分，避免每位玩家各打一個 FFLogs request。若 FFLogs report 已無法存取，該玩家會寫入 `gcd_coverage: null` 與 `gcd_coverage_status.reason = "private_or_deleted"`，並同步標記來源 report，讓一般公開資料排除整份 report；暫時性錯誤會保留缺 key 或舊版狀態，留待下次重試。

本地計算會參照 xivanalysis `Always be casting` 的核心規則：以 GCD cast/recast 取最大覆蓋時間、扣除 downtime，並用 FFLogs 約 45ms 批次的 timestamp 分桶推估實際 recast。對於忍者 mudra/ninjutsu、毒蛇劍士獨立 `gcdRecast`，以及毒蛇劍士、武士、白魔法師等加速狀態，腳本會用小型規則表補上 `Action.csv` 無法表達的例外。xivanalysis 頁面本身容易被站端限流，因此 workflow 預設不再讀取該網站頁面。

若要在本機把既有玩家 GCD 都以目前本地演算法重新計算，執行：

```bash
npm run backfill:gcd:all
npm run build:user-data
npm run validate:data
```

`backfill:gcd:all` 會帶 `--all --limit 999999`，連已是目前 `calculation_version` 的玩家也會重新計算；已標為 `gcd_coverage: null` 的不可用 report 仍會略過，避免反覆查詢 Private、刪除或無權限的報告。若只想重算單場，可使用 `npm run backfill:gcd -- --report-code A4cf9kg7Xbmt6vDh --fight-id 3`。

`scripts/backfill_gcd_coverage_xivanalysis.py` 保留為人工診斷工具，用來抽樣比對 xivanalysis 頁面顯示值；它不是 GitHub Actions 的預設流程。若臨時需要使用，請先安裝 Playwright Chromium，並把 worker 與速率調低，避免再次觸發 xivanalysis 的 `Slow down / Too many requests` 限流。

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

建置靜態網站：

```bash
npm run build
```

## 分享網址

前端維持靜態網站架構，不使用後端路由；頁面以 History API 路徑表示，只有偏離預設值的篩選條件才會寫入 query string，讓分享連結盡量短。

- 排行榜：`./`
- 全服統計：`./stats`、`./stats/savage_m1s`
- 個人成績單：`./user/玩家名稱?server=伺服器`
- 玩家比較：`./compare?left=玩家A%20@%20伺服器&right=玩家B%20@%20伺服器`
- 隊伍榜：`./teams`、`./teams?encounter=savage_m1s`
- 伺服器對比：`./servers/陸行鳥/vs/莫古力`
- 職業分析：`./jobs/Paladin`
- 近期動態：`./activity`

例如排行榜預設副本與隊伍榜預設副本目前都是 `savage_m4s`（零式 M4S / 狡雷），全服統計的「全部副本」、玩家比較的預設防護職能，也都不會寫入 URL。全服統計的副本、職業分析的職業、伺服器對比的左右伺服器會寫入乾淨路徑，讓社群爬蟲可以讀到對應的靜態 SEO/OG；額外的指標、分群、伺服器篩選等細部條件仍保留為 query，由前端載入後同步動態 meta。舊版 `?page=user&user=玩家名稱`、`?user=玩家名稱&server=伺服器`、`./user?name=玩家名稱`、`./jobs?job=Paladin` 或 `./servers?left=陸行鳥&right=莫古力` 連結仍會自動套用到對應頁面，避免既有分享連結失效；但需要社群爬蟲讀到專屬 OG 時，應使用 `./user/玩家名稱`、`./stats/{副本 key}`、`./jobs/{職業}` 或 `./servers/{左}/vs/{右}` 這類乾淨路徑。

排行榜與全服統計切換副本時會保留已選的伺服器與職業條件，讓使用者可以沿用同一組 query 在多個副本間比較；只有副本本身不支援版本切點時，版本篩選會自動回到 `all`。

`index.html` 提供站台層級 SEO、Open Graph、Twitter Card、JSON-LD 結構化資料，以及 favicon / Apple touch icon / web app manifest 引用。網站 icon 的設計來源是 `public/favicon.svg`，實際 PNG 與 ICO 由 `npm run build:icons` 產生；社群預覽圖位於 `public/og-image.png`。`npm run build` 後會由 `scripts/build_spa_fallback.mjs` 產生 `/stats/`、`/user/`、`/compare/`、`/teams/`、`/servers/`、`/jobs/` 與 `/activity/` 的 route 專屬 HTML，讓不執行 JavaScript 的社群爬蟲也能讀到各頁預設標題、描述、canonical 與 OG/Twitter meta。

同一個 postbuild 也會依 `public/data/global_stats.json`、`public/data/server_compare.json` 與 `public/data/users/index.json` 產生每個副本統計的 `dist/stats/{副本 key}/index.html`、每個職業的 `dist/jobs/{職業}/index.html`、每組有序伺服器配對的 `dist/servers/{左}/vs/{右}/index.html`、每位玩家的 `dist/user/{玩家名稱}/index.html`，以及對應的 `dist/og/stats/*.png`、`dist/og/jobs/*.png`、`dist/og/servers/*.png`、`dist/og/users/*.png`、`dist/sitemap.xml` 與 `dist/robots.txt`。因 LINE、Facebook 與多數 OG 檢查器對 SVG 支援不一致，postbuild 會用 `sharp` 將內部 SVG 模板轉成 1200x630 PNG，讓各頁 `og:image` 與 `twitter:image` 都指向自己的實體預覽圖；`robots.txt` 會明確允許 `facebookexternalhit` 與 `Facebot` 抓取分享預覽，首頁仍使用 `public/og-image.png` 作為站台層級預覽圖。建置產物只存在於 `dist/`，不會寫回 `data/` 或 `public/data/`，也不會改變 `config/encounters.json`、`data/rankings/` 或個人成績單 JSON schema。

前端載入後會由 `src/utils/shareMeta.js` 依目前頁面狀態同步 `document.title`、description、canonical、OG 與 Twitter meta；頁首的「分享」按鈕會優先使用瀏覽器 Web Share API，無法使用時改為複製目前分享連結。因為部署目標是靜態 SPA，沒有伺服器端依每一組 query 產生 HTML；不執行 JavaScript 的社群爬蟲會讀到 route 或玩家預設分享資訊，執行 JavaScript 的搜尋或瀏覽器環境則會看到目前篩選、玩家或比較條件的動態標題與描述。

`npm run build` 會在 Vite 建置完成後複製 `dist/index.html` 為 `dist/404.html`，讓 GitHub Pages 重新整理 `./stats`、`./user`、`./servers` 等路徑時仍可交回 Vue SPA 解析。

## 同步 GitHub Actions 與本機資料

如果 GitHub Actions 和本機爬蟲同時產生新資料，先用 dry-run 檢查：

```bash
npm run sync:data -- --dry-run
```

確認沒有 `REMOVAL` 或 `CONFLICT` 後，再同步遠端並自動合併來源資料：

```bash
npm run sync:data
```

這個工具會保護 append-only 資料：`data/state.json` 的 report 狀態、`data/rankings/*.json` 的 reports，以及 `config/encounters.json` 的 encounter key。如果任一邊刪除了既有資料，工具會停止並列出需要人工確認的條目。合併成功後會重建 `public/data` 產物；若只想合併來源資料，可以加上 `--no-rebuild`。

預覽建置結果：

```bash
npm run preview
```

抓取 FFLogs 並更新排行榜資料：

```bash
python scripts/fetch_fflogs.py
```

## 資料更新流程

一般更新流程如下：

1. `python scripts/fetch_fflogs.py`
   - 讀取 `config/encounters.json` 的啟用副本。
   - 透過 FFLogs API 掃描公開報告；預設掃全部地區。
   - 若 workflow 以 `FFLOGS_HISTORY_SCAN_ENABLED=true` 開啟歷史補查，會沿著各副本的 `history_scan_cursor_at` 輪巡較舊時間窗，檢查是否有後來才公開或延後匯出的 logs 可以補抓。
   - 篩選繁中服伺服器玩家。
   - 更新 `data/rankings/*.json`、`public/data/rankings/*.json` 與 `data/state.json`。
   - 若 FFLogs 暫時回傳 500/502/503/504 或連線逾時，該副本會保留原掃描點並在 `active_scan.last_error_*` 記錄錯誤摘要；已完成副本仍會更新掃描點，下一輪排程會自動補掃延後副本。

2. `npm run build:user-data`
   - 讀取排行榜資料。
   - 產生 `public/data/users/*.json`。
   - 產生 `public/data/users/index.json`。
   - 產生 `public/data/global_stats.json`。
   - 產生 `public/data/activity.json`。
   - 產生 `public/data/team_rankings.json`。
   - 產生 `public/data/server_compare.json`。

3. `npm run build`
   - 先自動執行 `build:public-rankings`，確保 `public/data/rankings/*.json` 與目前原始排行榜資料同步。
   - 接著自動執行 `build:user-data`。
   - 執行 `validate:data`，確認公開副本、排行榜分片、全服統計、近期動態、隊伍榜、伺服器對比與使用者索引完整。
   - 再由 Vite 建置靜態網站到 `dist/`。

## 設定副本

副本設定位於 `config/encounters.json`。每個副本包含：

- `key`：內部識別碼，也會對應資料檔名。
- `name`：網站顯示名稱。
- `category`：副本分類，例如 `零式`、`極`、`幻`、`絕`。
- `zone_id`：FFLogs zone ID。
- `encounter_id`：FFLogs encounter ID。
- `difficulty`：FFLogs difficulty。
- `enabled`：是否啟用掃描。
- `scan_start_date`：首次掃描起始日期。

新增或停用副本後，重新執行資料更新流程即可。

## 手動補抓報告

可以透過 `config/fflogs.json` 的欄位控制手動補抓：

- `retry_report_codes`：在一般掃描中強制重抓指定 report code。
- `only_report_codes`：只處理指定 report code，不推進掃描進度。

修改後執行：

```bash
python scripts/fetch_fflogs.py
npm run build:user-data
```

處理完成後，建議清空手動補抓欄位，避免下次排程重複處理。

手動補抓既有 report 時，資料管線會以 `data/rankings/{key}.reports/` 的 report/fight/player 明細重新建立 `ranking_entries`。因此重抓可以修正舊扁平索引中的錯誤數值，不需要手動編輯公開 JSON。

## 隱藏 Report 與資料鏡像

資料管線可在 report 上標記 `report_hidden: true`、`hidden_reason`、`hidden_detected_at_iso` 與 `hidden_source`。一般公開資料會排除這類 report，讓前端不需要在 Vue 元件內重做資料狀態判斷。

`python scripts/fetch_fflogs.py --rebuild-public` 會輸出兩套排行榜 JSON：一般 `public/data/rankings/*.json` 與完整 `public/data/all/rankings/*.json`。`npm run build:user-data` 也會同步輸出一般 `public/data/` 聚合產物與 `public/data/all/` 完整鏡像。

若玩家的公開成績沒有可列出的 entry，一般 `public/data/users/index.json` 仍會保留空白成績單入口與伺服器資訊，讓 `/user/{玩家}` 頁面可以開啟；預設成績單不會輸出副本成績、分數、隊友或紀錄時間。

額外檢視流程若需要完整資料，應只把 `/data/...` 改寫到 `/data/all/...`；若部署端尚未產生鏡像，應退回一般公開資料，避免網站載入失敗。

## 歷史補查

`config/fflogs.json` 預設關閉歷史補查，避免本機一般執行時額外掃描舊時間窗。GitHub Actions 會在 workflow 內用環境變數暫時開啟：

- `FFLOGS_REPORT_REGION_SCOPE`：淺層 reports 候選地區，`china` 只看中國區域，`all` 會掃全部地區；專案與 workflow 預設 `all`。
- `FFLOGS_HISTORY_SCAN_ENABLED`：是否啟用歷史補查，workflow 預設 `true`。
- `FFLOGS_HISTORY_SCAN_WINDOW_HOURS`：每個歷史時間窗長度，workflow 預設 `168`（一週）。
- `FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN`：每輪每個副本最多巡幾個歷史時間窗，workflow 預設 `1`。
- `FFLOGS_HISTORY_SCAN_RECENT_GAP_HOURS`：歷史補查避開最新掃描點前幾小時，workflow 預設 `6`。
- `FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN`：每輪最多挑幾份未知 report 進深層檢查，workflow 預設 `25`。
- `FFLOGS_HISTORY_SCAN_FULL_RUN`：是否一次跑完整歷史區間；預設 `false`，只建議人工短期維護時開啟。
- `FFLOGS_FETCH_GCD_COVERAGE_ENABLED`：新 report 落地時是否即時計算 GCD 覆蓋率，workflow 預設 `true`。
- `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN`：每輪最多查幾場 fight 的 Casts graph，workflow 預設 `500`；`0` 代表不設上限。

歷史補查會從副本的 `history_scan_start_date`、`scan_start_date` 或 `initial_scan_start_date` 開始，依 `data/state.json` 內各副本的 `history_scan_cursor_at` 往後輪巡。它只會把尚未在 state 或排行榜中的 report 選入候選，適合抓回「當時未公開、後來改成公開」或「FFLogs 延後完成匯出」的歷史 logs；一般最新資料仍由增量掃描負責。

## 自動更新

`.github/workflows/update_rankings.yml` 會在每小時第 17 分與第 47 分左右執行一次，也支援手動觸發。這兩個時間點各自使用一條獨立 cron 排程，讓 GitHub Actions 比較明確地註冊半小時更新。排程會以 GitHub 預設分支上的最新版 workflow 與設定檔執行；本機尚未 commit / push 的 `config/encounters.json` 變更不會被自動更新流程使用。

工作流程會：

1. 安裝 Python 與 Node.js。
2. 安裝 Python 與 Node.js 依賴。
3. 同步 Cloudflare CDN 規則；若 Cloudflare Rulesets API 只有 5xx、429 或網路暫時錯誤，會記錄 warning 並繼續抓取 FFLogs，4xx 設定或權限錯誤仍會中止。
4. 使用 GitHub Secrets 中的 FFLogs 憑證執行抓取腳本，掃描全部地區候選 report，以低量歷史補查檢查舊時間窗是否有新的公開 logs 可抓取，並對新落地 fight 即時計算 GCD 覆蓋率。
5. 執行 `python scripts/fetch_fflogs.py --split-rankings`，將完整排行榜資料拆分成適合 Git 追蹤的檔案。
6. 產生個人成績單、全服統計、近期動態、隊伍榜、伺服器對比資料與 `data/update_status.json`。
7. 執行 `npm run build`，在提交前完成公開資料驗證與 Vite 建置。
8. 若 `data` 或 `public/data` 有變更，提交並推送更新。
9. 上傳 `dist/` 並部署到 GitHub Pages。

`scripts/backfill_missing_fflogs_data.py --limit 250` 的自動步驟目前已在 workflow 內以註解保留，不會隨每輪排程執行。若需要修補既有 report 缺漏欄位，可手動執行 `npm run backfill:fflogs` 或原 Python 指令，再接續建置與驗證資料。

`scripts/backfill_gcd_coverage.py --limit 2000` 的自動步驟目前也已在 workflow 內以註解保留，不會隨每輪排程重掃既有玩家。新 report 的 GCD 會由 `fetch_fflogs.py` 即時計算；若需要追平舊資料，可手動執行 `npm run backfill:gcd -- --dry-run` 預覽，再正式執行 `npm run backfill:gcd`。Repository Variable `FFLOGS_GCD_BACKFILL_LIMIT` 只在重新啟用 workflow 註解步驟時生效。

需要在 GitHub Repository Secrets 設定至少一組：

- `FFLOGS_CLIENT_ID`
- `FFLOGS_CLIENT_SECRET`

可選擇再設定：

- `FFLOGS_CLIENT_IDS`
- `FFLOGS_CLIENT_SECRETS`
- `FFLOGS_CLIENT_CREDENTIALS_JSON`

## 部署

網站是靜態 Vite 專案，建置後輸出在 `dist/`：

```bash
npm run build
```

若部署到子路徑，請調整 `config/site.json` 的 `site_url` 與 `base_path`。`site_url` 會用於 canonical、OG URL 與建置後 route 專屬 HTML 的 `<base href>`；本機開發或預覽需要額外允許 host 時，也可在同一個檔案調整 `allowed_hosts`。

### Cloudflare CDN 與節流

為降低 GitHub Pages origin 流量，正式網域建議放在 Cloudflare 橘雲代理後方，並套用本專案的 Cache Rules、部署後 purge、Rate Limiting Rules 與 Facebook 分享爬蟲例外規則。Cloudflare 預設不快取 JSON，因此 `/data/*` 必須明確設定快取；否則排行榜與個人成績單資料仍會直接打到 GitHub Pages。

檢查將套用的規則：

```bash
npm run cloudflare:apply -- --dry-run
```

正式套用前需在本機環境設定 `CLOUDFLARE_ZONE_ID`、`CLOUDFLARE_RULES_API_TOKEN` 與 `CLOUDFLARE_HOSTNAME`，再執行：

```bash
npm run cloudflare:apply
```

GitHub Actions 每次執行時會先嘗試用 `CLOUDFLARE_RULES_API_TOKEN` 同步 Cloudflare Cache Rules、Facebook 分享爬蟲例外與 Rate Limiting Rules；若這個 secret 沒設定，會自動略過。Cloudflare Rulesets API 回傳 5xx、429 或網路暫時錯誤時，workflow 會先重試，最後仍失敗才略過本次規則同步，避免外部 API 波動阻斷 FFLogs 排行榜更新；權限或設定錯誤等 4xx 仍會讓 workflow 失敗。部署成功後會再用 `CLOUDFLARE_PURGE_API_TOKEN` 或相容的 `CLOUDFLARE_API_TOKEN` 執行 `npm run cloudflare:purge` 清除會變動的快取。

估算目前 `dist/` 在不同 Cloudflare HIT ratio 下，大約能承載多少頁面載入：

```bash
npm run cloudflare:estimate
```

完整 DNS、權限、TTL 與驗證方式請看 `docs/cloudflare-github-pages.md`。

## 注意事項

- `data/state.json` 是抓取進度狀態，手動修改前請先確認目前掃描狀態。
- `public/data/users/` 是由 `scripts/build_user_data.mjs` 重新產生的資料。
- `public/data/rankings/` 是由 `fetch_fflogs.py --rebuild-public` 或 `--split-rankings` 重新產生的公開排行榜資料；若副本列在 `public/data/encounters.json`，就必須有對應公開 ranking 檔案。
- FFLogs API 有限流，`config/fflogs.json` 可調整請求限制、重試、冷卻時間與單一 report 多 fight 的玩家成績批次大小。
- 排行榜只統計公開報告中可解析且符合繁中服條件的資料；地區只決定淺層候選池，真正的玩家身分仍以 FFLogs `masterData.actors` / `playerDetails` 的伺服器欄位判斷。
- 單場 FFLogs `playerDetails` / `damageDone` 查詢會同時帶 `fightIDs` 與 fight 的相對 `startTime` / `endTime`，避免少數舊報告只用 `fightIDs` 時拿到 partial damage table，造成 rDPS/aDPS 異常放大。
- `active_percent` 對齊 FFLogs Damage Done CSV 的 Active%，使用 `fflogs_total_time_ms` 作為優先分母；DPS/rDPS/aDPS 仍使用 `damage_time_ms`。
- GCD 覆蓋率目前前端已開啟：`顯示Gcd覆蓋率=true`。GitHub Actions 會在新 report 落地時即時計算 GCD 衍生結果；既有玩家的全量 backfill 仍維持手動。`fetch_fflogs.py` 與 `backfill_gcd_coverage.py` 都共用 `gcd_coverage_core.py`，以 FFLogs `Casts` graph 本地計算，`backfill_gcd_coverage_xivanalysis.py` 只保留為抽樣診斷工具；需要追平舊資料時，先以 `npm run backfill:gcd -- --dry-run` 預覽。本地計算會使用 graph 內的 downtime 視窗同時扣除分母與分子；同一個 report/fight 優先查整場 graph，再於本地依玩家 `sourceID` 切分，降低 FFLogs request 數。技能的 GCD 分類與基礎 cast/recast 以 XIVAPI datamining 的 `Action.csv` 為底，並用小型 allow-list 補上 xivanalysis 也會視為 GCD 的例外，例如忍者 mudra/ninjutsu，以及毒蛇劍士同時具有技能冷卻與獨立 GCD recast 的技能。完整 Casts raw events 只在記憶體中計算，不會保存到 repo。

## 版本切點與過版紀錄

- `極 佐拉加` 與 `極 豔翼蛇鳥` 目前有版本切點設定；台灣時間 2026-04-21 18:00 後的紀錄會被標記為過版紀錄。
- 公開排行榜會輸出 `is_obsolete_record`、`version_status`、`version_cutoff_iso` 與 `version_ranking_entries`，讓前端可以切換全部版本、有效版本紀錄、過時版本紀錄。
- `scripts/build_user_data.mjs` 會讓全服統計、個人成績單與隊伍榜輸出版本切片；個人最佳紀錄與同職分位只採計有效版本紀錄，過版紀錄保留在歷史紀錄中供追溯。
- 若要驗證這些切片，請執行 `npm run build:public-rankings`、`npm run build:user-data`、`npm run validate:data`，正式發佈前仍以 `npm run build` 做完整檢查。
