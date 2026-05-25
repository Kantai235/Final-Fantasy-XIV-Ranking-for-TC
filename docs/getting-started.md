# 開發與驗證入門

本文件整理本機安裝、環境變數與常用指令。資料契約與掃描策略請看 [data-contracts.md](data-contracts.md) 與 [data-pipeline.md](data-pipeline.md)。

## 需求環境

- Node.js 20+
- Python 3.11+
- FFLogs OAuth Client Credentials

安裝依賴：

```bash
npm install
npm run python:venv
npm run python:install
```

Python 版本由 `.python-version` 宣告為 3.11。所有 Python 相關 npm scripts 會透過 `scripts/run_python.mjs` 解析直譯器，順序是 `FFXIV_TC_PYTHON`、`.venv/bin/python`、`python3.11`、`python3`、`python`，且會拒絕低於 3.11 的版本。若要確認目前解析到的版本：

```bash
npm run python -- --version
```

## 環境變數

複製範本：

```bash
cp .env.example .env
```

PowerShell 可改用：

```powershell
Copy-Item .env.example .env
```

`.env` 至少需要一組 FFLogs OAuth 憑證：

```env
FFLOGS_CLIENT_ID=your_client_id
FFLOGS_CLIENT_SECRET=your_client_secret
```

也可以設定多組憑證以分散限流：

```env
FFLOGS_CLIENT_IDS=client_id_1,client_id_2
FFLOGS_CLIENT_SECRETS=client_secret_1,client_secret_2
```

或使用編號欄位：

```env
FFLOGS_CLIENT_ID_1=client_id_1
FFLOGS_CLIENT_SECRET_1=client_secret_1
FFLOGS_CLIENT_ID_2=client_id_2
FFLOGS_CLIENT_SECRET_2=client_secret_2
```

也支援 JSON 格式，適合放在 GitHub Secret：

```env
FFLOGS_CLIENT_CREDENTIALS_JSON=[{"client_id":"client_id_1","client_secret":"client_secret_1"}]
```

可選的前端分析設定：

```env
VITE_GA_MEASUREMENT_ID=G-XXXXXXXXXX
VITE_GA_ENABLE_IN_DEV=false
```

`VITE_GA_ENABLE_IN_DEV` 只有在刻意要於 `npm run dev` 送出 GA 事件時才設為 `true`。

`.env` 內含敏感資訊，不應提交到版本控制，也不要印到 Log。

## 常用指令

| 指令 | 用途 |
| --- | --- |
| `npm run dev` | 啟動 Vite 本機開發伺服器。代理協作者需先取得使用者同意。 |
| `npm run python:venv` | 使用可用的 Python 3.11+ 建立 `.venv`。 |
| `npm run python:install` | 使用專案 Python 3.11+ 直譯器安裝 `requirements.txt`。 |
| `npm run build:public-rankings` | 執行 `fetch_fflogs.py --rebuild-public`，只重建公開排行榜與副本清單，不呼叫 FFLogs API。 |
| `npm run build:ranking-tables` | 由公開排行榜產生 `ranking-tables` 薄索引與 `ranking-details` 報告細節檔。 |
| `npm run build:user-data` | 產生個人成績單、個人成績報告細節、全服統計、近期動態、隊伍榜、伺服器對比與排行榜薄索引資料。 |
| `npm run validate:data` | 驗證公開副本、公開資料 schema、排行榜分片、raw 欄位、全服統計與使用者索引。 |
| `npm run test:data-conservation` | 檢查公開資料與 hidden delta 的資料守恆，避免瘦身時漏掉成績或報告來源。 |
| `npm run audit:pages-payload` | 以 baseline 模式稽核 `dist/`、`dist/data/`、`dist/data/all/`、`dist/data/users/` 與 `dist/og/` 體積，可加 `-- --write-history <path>` 記錄趨勢。 |
| `npm run audit:pages-payload:strict` | 以與 GitHub Actions 相同的 strict 模式稽核 payload，超過 target 會失敗。Actions 會寫入 `data/pages_payload_history.jsonl`。 |
| `npm run check` | 執行 Python 與 Node.js 語法檢查。 |
| `npm test` | 執行資料管線、GCD、資料建置與前端資料契約測試。 |
| `npm run build` | 先重建公開資料並驗證，再由 Vite 建置靜態網站到 `dist/`。 |
| `npm run preview` | 預覽 `dist/` 靜態網站。代理協作者需先取得使用者同意。 |
| `npm run build:icons` | 由 `public/favicon.svg` 重建 favicon、Apple touch icon 與 manifest icon。 |

文件或註解變更仍需至少執行：

```bash
npm run check
npm run build:user-data
```

## 本機資料更新

完整抓取 FFLogs 並重建資料：

```bash
npm run python -- scripts/fetch_fflogs.py
npm run build:user-data
npm run validate:data
```

建置網站：

```bash
npm run build
```

`npm run build` 會先執行 `build:public-rankings`、`build:user-data` 與 `validate:data`，再輸出 Vite 產物。`build:public-rankings` 不會呼叫 FFLogs API，適合在沒有憑證或不想推進掃描點時重建公開資料。

## 同步本機與 GitHub Actions 資料

如果 GitHub Actions 和本機爬蟲同時產生新資料，先用 dry-run 檢查：

```bash
npm run sync:data -- --dry-run
```

確認沒有 `REMOVAL` 或 `CONFLICT` 後，再同步遠端並自動合併來源資料：

```bash
npm run sync:data
```

這個工具會保護 append-only 資料：`data/state.json` 的 report 狀態、`data/rankings/*.json` 的 reports，以及 `config/encounters.json` 的 encounter key。合併成功後會重建 `public/data` 產物；若只想合併來源資料，可以加上 `--no-rebuild`。
