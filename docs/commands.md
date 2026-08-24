# 指令參考

本文件逐一對應 `package.json` 的 npm scripts。執行前請先確認指令是否會呼叫外部服務、寫入 append-only 來源資料，或變更遠端 repo／Cloudflare。資料工作開始前一律先執行：

```bash
npm run sync:data -- --dry-run
```

若本機資料與 Data repo snapshot 不同，先停止並保存成果，不得直接用 `--force` 覆蓋。

表格中的「寫入」分為：

- 無：只讀或語法／測試檢查；測試可能在系統暫存目錄建立隔離檔案。
- 產物：重建可由來源資料再生的 `public/data/`、`dist/`、圖示或稽核報告。
- 來源：可能更新 `data/rankings/`、`data/state.json` 或其它 append-only 來源資料。
- 外部：可能推送 repo、更新 Google Sheet、Cloudflare 規則或快取。

## Python 執行環境

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run python -- <args>` | 依傳入腳本 | 依傳入腳本 | 以 `scripts/run_python.mjs` 選出 Python 3.11+ 後執行參數。 |
| `npm run python -- --version` | 否 | 無 | 顯示目前會使用的 Python 版本。 |
| `npm run python:venv` | 否 | 產物 | 建立 `.venv`。 |
| `npm run python:install` | PyPI | 產物 | 將 `requirements.txt` 安裝到專案 Python 環境。 |

解析順序為 `FFXIV_TC_PYTHON`、平台對應的 `.venv`、`python3.11`、`python3`、`python`；低於 3.11 會停止。

## 資料抓取、回補與清理

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run build:public-rankings` | 否 | 產物 | 執行 `fetch_fflogs.py --rebuild-public`，由來源分片重建公開排行榜與副本清單。 |
| `npm run check:report-status -- <report code>` | FFLogs | 來源 | 查單一既有 report 的可讀狀態；不可讀時在來源分片標記 hidden，不推進掃描點。 |
| `npm run compact:rankings -- --dry-run` | 否 | 無 | 預覽排行榜 raw 欄位清理與重新分片。 |
| `npm run compact:rankings` | 否 | 來源 | 移除可重查的大型 raw 欄位並重新分片；不得刪除 report／fight／player。 |
| `npm run compact:state -- --dry-run` | 否 | 無 | 預覽 state 可重建欄位與 JSON 空白壓縮。 |
| `npm run compact:state` | 否 | 來源 | 壓縮 state 主檔與 checked-report 分片，保留完整 checkpoint。 |
| `npm run backfill:fflogs` | FFLogs | 來源 | 最多 500 份 report，補齊影響建置的既有欄位。 |
| `npm run backfill:support -- --dry-run` | 否 | 無 | 預覽 7.2 開放後缺少目前支援統計版本的 report。 |
| `npm run backfill:support` | FFLogs | 來源 | 由最舊開始完整回補 7.2 開放後的坦補支援統計，每 25 份 checkpoint。 |
| `npm run backfill:support:history -- --dry-run` | 否 | 無 | 預覽 workflow 式支援統計歷史批次。 |
| `npm run backfill:support:history` | FFLogs | 來源 | 依 state 游標由 7.2 切點往舊處理 25 份 report。 |
| `npm run backfill:gcd -- --dry-run` | 否 | 無 | 預覽缺少或需要新版計算的 GCD 玩家候選。 |
| `npm run backfill:gcd` | FFLogs、XIVAPI datamining | 來源 | 依玩家候選補齊 GCD 覆蓋率，預設最多 2,000 筆。 |
| `npm run backfill:gcd:reports -- --dry-run` | 否 | 無 | 預覽以 report 為單位的 stateful GCD 回補。 |
| `npm run backfill:gcd:reports` | FFLogs、XIVAPI datamining | 來源 | 由固定 cutoff 往舊，以 report 為單位補齊 GCD。 |
| `npm run backfill:gcd:all` | FFLogs、XIVAPI datamining | 來源 | 以目前演算法重算所有可處理的 GCD；屬高成本維護指令。 |
| `npm run backfill:fight-integrity -- --dry-run` | 否 | 無 | 預覽需要戰鬥完整性檢核的 report。 |
| `npm run backfill:fight-integrity` | FFLogs | 來源 | 以 25 份 report 為預設批次回補 fight 層完整性證據。 |
| `npm run check:gcd-missing-report-status -- --dry-run` | 否 | 無 | 預覽缺少 GCD 且需要確認 report 可見度的候選。 |
| `npm run check:gcd-missing-report-status` | FFLogs | 來源 | 查候選 report 狀態；永久不可讀時標記 hidden，不補算 GCD。 |
| `npm run fetch:honey-fans` | FFLogs | 來源、產物 | 抓取並重建 Honey B. Lovely 趣味資料；不寫正式排行榜。 |
| `npm run build:honey-fans` | 否 | 產物 | 由既有 `data/fun/honey_b_fans.json` 重建公開趣味榜。 |

直接執行正式排行榜掃描使用：

```bash
npm run python -- scripts/fetch_fflogs.py
```

這會呼叫 FFLogs 並修改來源資料；操作細節、憑證與掃描策略見 [data-pipeline.md](data-pipeline.md)。

## GCD 診斷與稽核

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run backfill:gcd:xivanalysis` | xivanalysis、FFLogs | 來源／快取 | 人工診斷工具，優先讀 xivanalysis 畫面值；不屬於 Actions 預設流程。 |
| `npm run audit:gcd:xivanalysis` | xivanalysis、FFLogs | 稽核報告／快取 | 以固定 seed 抽樣比對本地計算與 Always Be Casting 顯示值。 |
| `npm run recompute:gcd:xivanalysis-cache` | 依參數與快取狀態 | 稽核報告／快取 | 由既有稽核目標與快取重新計算比較結果。 |
| `npm run build:gcd-recompute-manifest` | 否 | 稽核報告 | 彙整 GCD top-ranking 重算完成狀態。 |
| `npm run build:gcd-player-sample-manifest` | 否 | 稽核報告 | 彙整逐職業玩家樣本完成狀態。 |
| `npm run seed:gcd:xivanalysis-cache` | FFLogs／xivanalysis，依參數 | 快取 | 以既有稽核證據或外部查詢預填診斷快取。 |

上述工具可能觸發外站限流。xivanalysis 沒有正式結果 JSON API；不得把這些指令加入 GitHub Actions 預設更新流程。

## 靜態資料建置

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run build:ranking-tables` | 否 | 產物 | 產生排行榜薄索引、按需報告細節與 hidden delta。 |
| `npm run build:report-status` | 否 | 產物 | 由排行榜細節產生公開與 hidden report 狀態索引。 |
| `npm run build:public-status` | 否 | 產物 | 由內部更新戳記與全服統計產生可公開的排程摘要。 |
| `npm run build:user-data` | 否 | 產物 | 建置使用者、成就統計、全服統計、近期動態、隊伍榜、伺服器對比，並接續執行前三項。 |
| `npm run validate:data` | 否 | 無 | 驗證公開 schema、來源／衍生資料一致性與禁止 raw 欄位。 |
| `npm run build:icons` | 否 | 產物 | 由 `public/favicon.svg` 產生 PNG、ICO 與 PWA icon。 |
| `npm run prebuild` | 否 | 產物 | npm lifecycle：依序重建公開排行榜、使用者資料、Honey 公開資料並驗證。 |
| `npm run build` | 否 | 產物 | 自動執行 `prebuild`，再由 Vite 建置 `dist/`，最後自動執行 `postbuild`。 |
| `npm run postbuild` | 否 | 產物 | 產生 route fallback、低基數 SEO／OG 頁、sitemap、robots 與 `404.html`。 |
| `npm run prune:pages-user-data` | 否 | 產物 | 從 `dist/` 移除個別玩家 JSON、逐玩家分享頁與 OG 圖，保留使用者索引。 |

`npm run build` 雖不呼叫 FFLogs，仍會重建大量本機產物；新 clone 必須先 hydrate Data repo。

## FFLogs 待收錄佇列

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run read:fflogs-refresh-queue` | Google Sheets | CI 環境輸出 | 讀取 queued／pending／retry report code，合併到本輪 `FFLOGS_RETRY_REPORT_CODES`。 |
| `npm run complete:fflogs-refresh-queue` | Google Sheets | 外部 | 依來源分片、公開／hidden 索引與 state checkpoint 回寫終止狀態。 |
| `npm run test:fflogs-refresh-queue` | 否 | 無 | 測試佇列解析、狀態判定與欄位校正。 |

Google Sheet 的欄位、權限與狀態生命週期見 [Apps Script 文件](../apps-script/fflogs-report-status/README.md)。

## Data repo 與 Users repo

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run data:hydrate`／`npm run sync:data` | Data repo | 本機來源與產物 | 驗證 manifest 後還原權威 snapshot；本機不同時預設停止。 |
| `npm run sync:data -- --dry-run` | Data repo | 無 | 完整下載、驗證並比對 snapshot，不覆寫本機。 |
| `npm run data:publish` | Data repo | 外部 | 驗證 append-only 守恆，建立單一 root snapshot 並以 `force-with-lease` 發布。 |
| `npm run data:verify` | Data repo／本機快取 | 無 | 驗證單一 root commit、manifest、大小與 SHA-256。 |
| `npm run data:repair-eol` | Data repo | 外部 | 只在位元組可完全命中 manifest 時修復 CRLF／LF 正規化損壞。 |
| `npm run test:data-repository` | 本機 bare repo | 無 | 驗證 hydrate、publish、manifest、快照與守恆阻擋。 |
| `npm run test:sync-user-repo` | 本機 bare repo | 無 | 驗證 Users repo 空白初始化、單一快照、收斂與無變更略過。 |

Users repo 正式同步沒有獨立 npm script，由 workflow 直接執行 `node scripts/sync_user_leaderboard_repo.mjs`。

## 測試與檢查

| 指令 | 範圍 |
| --- | --- |
| `npm run test:fetch-fflogs` | FFLogs 批次解析、Healing／坦補支援統計與支援回補。 |
| `npm run test:compact-state` | state 壓縮與 blob 大小保護。 |
| `npm run test:state-store` | Python checked-report 分片讀寫。 |
| `npm run test:gcd-coverage` | 本地 GCD 回補、缺漏 report 狀態與 xivanalysis 診斷流程。 |
| `npm run test:fight-integrity` | 完整性純計算、歷史基準、固定容量、快取與回補。 |
| `npm run test:honey-fans` | Honey B. Lovely 抓取、時間窗與公開建置。 |
| `npm run test:build-user-data` | 使用者資料、去重、版本、成就與統計聚合。 |
| `npm run test:ranking-tables` | 排行榜薄索引、報告細節、支援統計與 hidden delta。 |
| `npm run test:sync-user-repo` | Users repo 單一快照同步。 |
| `npm run test:data-repository` | Data repo snapshot 與守恆。 |
| `npm run test:fflogs-refresh-queue` | Google Sheet 待處理佇列邏輯。 |
| `npm run test:frontend-data` | Vue 靜態資料邊界、網址、元件契約與公開資料讀取。 |
| `npm run test:data-conservation` | 來源、薄索引、細節檔、使用者檔與 hidden delta 守恆。 |
| `npm run test:data-contracts` | `validate:data` 的別名。 |
| `npm run check` | 專案列管的 Python 編譯與 Node.js 語法檢查。 |
| `npm test` | 依序執行上述完整測試與資料契約檢查。 |

驗證需依變更風險選擇：

- 純文件、公告或不影響資料產物的靜態設定：Markdown／JSON／連結檢查與 `git diff` 即可。
- 前端邏輯：至少 `npm run check`，再依資料讀取範圍選 `test:frontend-data`。
- 使用者資料、排行榜薄索引或 schema：執行對應建置測試、`validate:data` 與守恆測試。
- 限流、重試、hidden report、支援統計、GCD 或完整性規則：執行對應 Python 測試，必要時再做明確的小範圍資料驗證。

## 稽核、建置容量與 Cloudflare

| 指令 | 外部存取 | 寫入 | 用途 |
| --- | --- | --- | --- |
| `npm run audit:pages-payload` | 否 | 選填歷史檔 | 以 baseline 模式量測 `dist/` 各區體積，只在硬上限失敗。 |
| `npm run audit:pages-payload:strict` | 否 | 選填歷史檔 | 使用 Actions 的 strict target；任一 target 超標即失敗。 |
| `npm run audit:mixed-report-dispatch` | 否 | Step Summary | 稽核 mixed report 分派 revision 與歷史游標完成度。 |
| `npm run cloudflare:apply -- --dry-run` | 否 | 無 | 顯示預計套用的 Cache、WAF 例外與節流規則。 |
| `npm run cloudflare:apply` | Cloudflare | 外部 | 建立或更新本專案管理的 Cloudflare 規則。 |
| `npm run cloudflare:purge -- --dry-run` | 否 | 無 | 顯示 scoped purge 範圍。 |
| `npm run cloudflare:purge` | Cloudflare | 外部 | 清除會隨部署變動的 prefix 與核心檔案快取。 |
| `npm run cloudflare:estimate` | 否 | 無 | 依 `dist/` 壓縮體積估算 GitHub Pages origin 承載量。 |

Cloudflare 權限、TTL 與事故處理見 [cloudflare-github-pages.md](cloudflare-github-pages.md)。

## 本機服務

| 指令 | 作用 |
| --- | --- |
| `npm run dev` | 在 `127.0.0.1` 啟動 Vite 開發伺服器。 |
| `npm run preview` | 在 `127.0.0.1` 預覽既有 `dist/`。 |

代理協作者不得擅自啟動本機服務；若驗證確實需要互動式伺服器，必須先說明原因並取得使用者明確同意。
