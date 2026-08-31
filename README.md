# FFXIV 繁中服排行榜

FFXIV 繁中服排行榜是以 FFLogs 公開報告為來源的社群專案，整理繁中服玩家在零式、極、幻、滅與絕本中的公開通關成績。網站以 Vue 3／Vite 建置，資料由 Python 抓取、Node.js 聚合，再以靜態 JSON 提供排行榜、全服統計、個人成績單與分析頁面。

正式站台：[ranking.init.engineer](https://ranking.init.engineer/)

> 本站不是 Square Enix 或 FFLogs 的官方服務。公開榜單只反映本站已收錄、且尚未被資料管線標記為不可公開的 FFLogs 紀錄；報告在兩次巡檢之間仍可能改變可見度，因此不代表 FFLogs 當下的完整狀態、遊戲內完整人口或所有通關紀錄。

## 專案重點

- 排行榜支援副本、伺服器、職能、職業、關鍵字、版本與紀錄時效篩選。
- 個人成績單提供最佳紀錄、歷史紀錄、同職分位、趨勢、常同場隊友、可選的同場坦／補對照、簡表與成就手冊。
- 全服統計、玩家比較、隊伍榜、伺服器對比、職業分析與近期動態皆由靜態資料產生。
- 坦克與治療職業另整理承傷、治療、防護、過量治療與有效減傷覆蓋等支援統計。
- FFLogs 報告狀態、hidden delta、同場多份上傳與戰鬥完整性結果都保留可追溯脈絡。
- GitHub Actions 每小時第 17、47 分執行資料更新，並以 GitHub Pages 與 Cloudflare 提供靜態內容。

完整功能與規則請見 [功能與頁面](docs/features.md)，網址行為請見 [分享網址、SEO 與 OG](docs/routing-and-seo.md)。

## 架構邊界

```text
FFLogs GraphQL API
        │
        ▼
Python 抓取層 ──► Data repo：data/rankings、state、共用 public/data 快照
        │
        ▼
Node.js 建置層 ─► 主站共用 JSON ＋ Users repo 個別玩家 JSON
        │
        ▼
Vue 3 呈現層 ──► GitHub Pages／Cloudflare
```

三層責任必須維持分離：

1. `scripts/fetch_fflogs.py` 負責正式排行榜掃描、FFLogs 欄位解析、限流／重試、繁中服玩家初篩與來源資料寫入。
2. `scripts/build_user_data.mjs` 與其他 Node.js 建置腳本負責去重、排序、分位、全服統計及前端靜態資料。
3. `src/` 只讀靜態 JSON 並呈現畫面，不得直接呼叫 FFLogs API，也不得重做建置層聚合。

權威來源資料位於 `Final-Fantasy-XIV-Ranking-for-TC-Data`；個別玩家成績單部署快照位於 `Final-Fantasy-XIV-Ranking-for-TC-Users`。主 repo 只追蹤程式碼、設定、文件與靜態資產，不追蹤 `data/` 或 `public/data/` 產物。完整責任與逐檔索引請見 [系統架構](docs/architecture.md) 與 [程式碼責任索引](docs/codebase-map.md)。

## 快速開始

需求環境：

- Node.js 20+、npm 10+；GitHub Actions 固定使用 Node.js 24。
- Python 3.11+；專案版本記錄於 `.python-version`。
- 若要抓取 FFLogs，另需 FFLogs OAuth Client Credentials。

安裝依賴並建立 Python 虛擬環境：

```bash
npm install
npm run python:venv
npm run python:install
```

新 clone 不包含資料產物。第一次建置前先確認本機沒有未發布資料，再載入 Data repo 的權威快照：

```bash
npm run sync:data -- --dry-run
npm run sync:data
```

執行基本檢查與靜態建置：

```bash
npm run check
npm run build
```

`npm run build` 會從已 hydrate 的來源重建公開資料、驗證資料契約、建置 Vite 網站並產生 SPA／SEO fallback；它不會呼叫 FFLogs API。`npm run dev` 與 `npm run preview` 會啟動本機服務，代理協作者除非取得使用者明確同意，否則不得自行執行。

安裝、PowerShell 指令、資料同步與本機工作流程請見 [開發與驗證入門](docs/getting-started.md)。

## 更新 FFLogs 資料

先複製環境變數範本並填入至少一組 OAuth 憑證：

```bash
cp .env.example .env
```

```env
FFLOGS_CLIENT_ID=your_client_id
FFLOGS_CLIENT_SECRET=your_client_secret
```

開始任何會產生資料的工作前，仍須先執行 `npm run sync:data -- --dry-run`。一般更新流程為：

```bash
npm run python -- scripts/fetch_fflogs.py
npm run build:user-data
npm run build:honey-fans
npm run validate:data
```

這些步驟會修改不由主 repo 追蹤的來源與公開資料；發布前還必須執行 state 壓縮、資料守恆檢查與 Data repo 發布流程。請勿只依本節操作正式資料，完整流程與回補指令請見 [資料管線與維護流程](docs/data-pipeline.md) 及 [資料契約與歷史資料保護](docs/data-contracts.md)。

## 常用指令

| 指令 | 用途 |
| --- | --- |
| `npm run sync:data -- --dry-run` | 比對本機受管理資料與 Data repo，不寫入檔案。 |
| `npm run build:public-rankings` | 由既有來源重建公開排行榜與副本清單，不呼叫 FFLogs API。 |
| `npm run build:user-data` | 建置個人成績、統計、排行榜薄索引與公開狀態資料。 |
| `npm run validate:data` | 驗證公開 JSON、分片、索引與 schema 契約。 |
| `npm run check` | 執行 Python 與 Node.js 語法檢查。 |
| `npm test` | 執行完整測試套件，涵蓋資料管線邏輯、建置器與前端資料契約。 |
| `npm run build` | 完整建置靜態網站到 `dist/`。 |

全部 npm scripts、外部存取與資料寫入範圍請查閱 [指令參考](docs/commands.md)，不要只憑指令名稱推測是否安全。

## 文件導覽

| 文件 | 適用情境 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文件索引、閱讀順序與權威來源分工。 |
| [docs/getting-started.md](docs/getting-started.md) | 初次安裝、環境變數、Data repo hydrate 與驗證策略。 |
| [docs/features.md](docs/features.md) | 頁面功能、共用偏好、版本紀錄、支援統計與成就規則。 |
| [docs/architecture.md](docs/architecture.md) | 三層架構、資料流、repo 分工與前端邊界。 |
| [docs/codebase-map.md](docs/codebase-map.md) | 每個程式碼、設定、workflow 與測試檔案的責任索引。 |
| [docs/commands.md](docs/commands.md) | `package.json` 全部指令、是否寫入資料及外部依賴。 |
| [docs/data-pipeline.md](docs/data-pipeline.md) | FFLogs 掃描、支援統計、GCD、完整性檢核與回補流程。 |
| [docs/data-contracts.md](docs/data-contracts.md) | JSON 契約、去重、hidden delta、版本切點與 append-only 保護。 |
| [docs/routing-and-seo.md](docs/routing-and-seo.md) | 乾淨路徑、舊網址相容、OG／SEO 與 SPA fallback。 |
| [docs/deployment.md](docs/deployment.md) | GitHub Actions、Data／Users repo 發布與 GitHub Pages 部署。 |
| [docs/cloudflare-github-pages.md](docs/cloudflare-github-pages.md) | Cloudflare 快取、節流、purge 與維運。 |
| [config/README.md](config/README.md) | 副本、版本、FFLogs 與站台設定欄位。 |
| [apps-script/fflogs-report-status/README.md](apps-script/fflogs-report-status/README.md) | FFLogs report 即時可讀狀態與 Google Sheet 待收錄名單。 |

## 不可破壞的維護原則

- `config/encounters.json` 的 `key`、`data/state.json` 的 report 狀態與 `data/rankings/` 的 report／fight／player 歷史都是 append-only 資產，不可任意改名、覆寫或硬刪。
- 本機資料與遠端 snapshot 不同時，hydrate 必須停止；不得用 `--force` 掩蓋未知差異。
- `.env`、FFLogs、Google Sheets、GitHub 與 Cloudflare 憑證不得提交，也不得輸出到 Log。
- 新前端統計欄位應先擴充 Node.js 建置層與 schema，再由 Vue 讀取；前端不得直接查 FFLogs。
- 純文件或文案變更只做相符的 Markdown／連結檢查與 `git diff`；只有實際影響資料產物或契約時才執行使用者資料建置與全量驗證。
- 所有協作、註解、文件與 commit message 使用繁體中文（台灣用語）。

協作者在修改前還必須完整閱讀 [AGENTS.md](AGENTS.md) 或對應代理準則；README 是入口文件，不取代專案運作準則。
