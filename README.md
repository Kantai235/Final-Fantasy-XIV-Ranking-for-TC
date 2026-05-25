# FFXIV 繁中服排行榜

Final Fantasy XIV 繁中服排行榜是一個以 FFLogs 公開資料為來源的 Vue 3 / Vite 靜態網站，用來整理繁中服玩家在零式、極、幻與絕本中的公開通關成績。

專案由兩個主要部分組成：

- 前端網站：瀏覽排行榜、全服統計、個人成績單、玩家比較、隊伍榜、伺服器對比、職業分析與近期動態。
- 資料管線：透過 FFLogs GraphQL API 抓取報告，篩選繁中服玩家，建置排行榜與前端需要的靜態 JSON。

> 這是非官方社群工具，資料來自 FFLogs 公開報告；顯示結果不代表遊戲內完整人口或所有通關紀錄。

## 快速開始

需求環境：

- Node.js 20+
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
- 顯示 DPS、rDPS、aDPS、Active、GCD 覆蓋率參考值、通關時間與紀錄時間。
- 個人成績單可查看各副本最佳紀錄、歷史紀錄、同職分位與常同場隊友。
- 玩家比較、隊伍榜、伺服器對比、職業分析與近期動態皆由靜態資料產生。
- 支援深色 / 亮色主題，並依目前頁面的職業或職能篩選切換主色調。
- 支援全域公告通知，公告內容由 `public/data/announcements.json` 隨 commit 更新，使用者關閉後不再主動顯示。
- GitHub Actions 可定時抓取 FFLogs、建置資料並部署 GitHub Pages。

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
| [config/README.md](config/README.md) | `config/` 設定檔欄位判讀。 |
| [data/rankings/README.md](data/rankings/README.md) | 排行榜完整資料格式與分片說明。 |

## 核心架構

本專案最重要的邊界是「抓取、建置、呈現」三層分離：

1. `scripts/fetch_fflogs.py` 是 Data Fetching Layer。它是唯一可直接呼叫 FFLogs GraphQL API 的入口，負責 OAuth、限流、重試、繁中服玩家初篩、report 狀態判定，以及 `data/rankings/` 與 `data/state.json` 的可追溯寫入。
2. `scripts/build_user_data.mjs` 是 Data Building Layer。它讀取排行榜來源資料，產生個人成績單、全服統計、近期動態、隊伍榜與伺服器對比等 `public/data/` 靜態 JSON。
3. `src/` 是 UI Presentation Layer。Vue 只讀取 `public/data/` 靜態 JSON 進行呈現、篩選與狀態管理，不能直接呼叫 FFLogs API。

## 常用指令

| 指令 | 用途 |
| --- | --- |
| `npm run build:public-rankings` | 只重建公開排行榜與副本清單，不呼叫 FFLogs API。 |
| `npm run build:ranking-tables` | 由公開排行榜產生前端薄索引與按需載入報告細節檔。 |
| `npm run build:user-data` | 建置個人成績單、全服統計、近期動態、隊伍榜、伺服器對比與排行榜薄索引。 |
| `npm run validate:data` | 驗證公開資料、分片、全服統計與使用者索引完整性。 |
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
- 若 GitHub Actions 與本機同時產生資料，先跑 `npm run sync:data -- --dry-run`；看到 `REMOVAL` 或 `CONFLICT` 時不可自動套用。
- 文件或註解變更仍需至少執行 `npm run check` 與 `npm run build:user-data`，確認資料聚合流程可完成。
