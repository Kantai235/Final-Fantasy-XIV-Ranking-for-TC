# 開發與驗證入門

本文件說明新 clone 的安裝、權威資料載入、環境變數與如何依變更風險選擇驗證。全部 npm scripts 與寫入範圍見 [commands.md](commands.md)；資料維護前另讀 [data-contracts.md](data-contracts.md) 與 [data-pipeline.md](data-pipeline.md)。

## 需求環境

- Node.js 20+。
- npm 10+；`package.json` 固定 `packageManager=npm@10.9.2`。
- Python 3.11+；`.python-version` 為 `3.11`。
- Git。
- 只有要呼叫 FFLogs 時才需要 OAuth Client Credentials。

GitHub Actions 與官方 actions 固定使用 Node.js 24，Python 固定使用 3.11。本機可使用符合 engines 的較新 Node 版本，但遇到建置差異時應優先用 Actions 相同 major 重現。

## 安裝相依套件

```bash
npm install
npm run python:venv
npm run python:install
```

CI 使用鎖定檔執行 `npm ci`；本機第一次安裝或更新相依套件使用 `npm install`。

所有 Python npm scripts 都透過 `scripts/run_python.mjs` 選擇直譯器，順序為：

1. `FFXIV_TC_PYTHON`。
2. Windows 的 `.venv/Scripts/python.exe` 或 Unix 的 `.venv/bin/python`。
3. `python3.11`、`python3`、`python`。

候選版本低於 3.11 時會拒絕執行。確認實際選到的版本：

```bash
npm run python -- --version
```

## 載入權威資料

主 repo 的 `.gitignore` 排除 `data/` 與 `public/data/`，因此新 clone 不能直接完整建置。權威資料位於 Data repo 的單一 root snapshot。

先執行 dry-run：

```bash
npm run sync:data -- --dry-run
```

dry-run 會下載 snapshot、展開 Git 工作目錄、驗證 manifest 的大小與 SHA-256，再比對本機受管理資料；它不覆寫檔案。即使只是 dry-run，也必須取得完整 snapshot，因為沒有全部位元組就無法安全判斷差異。

確認本機沒有未發布資料後再 hydrate：

```bash
npm run sync:data
```

hydrate 會還原 Data repo 管理的來源與共用公開資料。若本機內容不同，它會停止而不覆寫；此時先暫停 workflow、保存或發布本機成果，再決定下一步。一般工作不得用 `--force` 掩蓋未知差異。

`.data-repo/` 是不進 Git 的本機快取。舊版 `blob:none` partial clone 會在下載階段補齊缺少物件；暫時性 HTTP/2 中斷最多重試三次。

## 基本檢查與建置

不需要 FFLogs 憑證即可從已 hydrate 的資料重建網站：

```bash
npm run check
npm run build
```

`npm run build` 的 lifecycle 為：

1. `build:public-rankings`：由既有來源重建公開排行榜，不查 FFLogs。
2. `build:user-data`：建置使用者、統計、薄索引與狀態資料。
3. `build:honey-fans`：由既有 Honey 來源重建公開 JSON，不查 FFLogs。
4. `validate:data`：驗證資料契約。
5. `vite build`：產生 `dist/`。
6. `postbuild`：產生 route fallback、SEO／OG、sitemap、robots 與 `404.html`。

如果只修改前端且不需要完整資料重建，可依變更範圍使用 `npm run check` 與 `npm run test:frontend-data`；不要為純文件變更啟動全量使用者資料建置。

## 本機服務

```bash
npm run dev
npm run preview
```

- `dev` 在 `127.0.0.1` 啟動 Vite 開發伺服器。
- `preview` 預覽既有 `dist/`。
- `config/site.json.allowed_hosts` 控制額外允許的 host。

代理協作者除非使用者明確要求，不得自行啟動 Vite 或 preview。若互動式驗證確實需要服務，應先說明原因並取得同意。

## 環境變數

複製範本：

```bash
cp .env.example .env
```

PowerShell：

```powershell
Copy-Item .env.example .env
```

`.env` 被 Git 排除。任何真實的 OAuth secret、service-account private key、GitHub PAT 或 Cloudflare token 都不得出現在文件、commit 或 Log；文件只能使用無效的佔位值。

### FFLogs OAuth

單組憑證：

```env
FFLOGS_CLIENT_ID=your_client_id
FFLOGS_CLIENT_SECRET=your_client_secret
```

逗號分隔多組：

```env
FFLOGS_CLIENT_IDS=client_id_1,client_id_2
FFLOGS_CLIENT_SECRETS=client_secret_1,client_secret_2
```

編號多組：

```env
FFLOGS_CLIENT_ID_1=client_id_1
FFLOGS_CLIENT_SECRET_1=client_secret_1
FFLOGS_CLIENT_ID_2=client_id_2
FFLOGS_CLIENT_SECRET_2=client_secret_2
```

JSON 陣列適合 GitHub Secret：

```env
FFLOGS_CLIENT_CREDENTIALS_JSON=[{"client_id":"client_id_1","client_secret":"client_secret_1"}]
```

`config/fflogs.json` 的頂層純量與清單設定可用同名大寫 `FFLOGS_*` 暫時覆寫；巢狀的 `fight_integrity_check` 不接受整個物件覆寫，目前只有 `enabled` 另支援 `FFLOGS_FIGHT_INTEGRITY_ENABLED`。完整欄位與 workflow 預設見 [data-pipeline.md](data-pipeline.md) 及 [deployment.md](deployment.md)。

### 前端

```env
VITE_GA_MEASUREMENT_ID=
VITE_GA_ENABLE_IN_DEV=false
VITE_FFLOGS_REPORT_STATUS_WEB_APP_URL=https://script.google.com/macros/s/.../exec
VITE_USER_DATA_BASE_URL=
VITE_USER_DATA_FALLBACK_BASE_URLS=
VITE_USER_INDEX_BASE_URL=
```

- GA Measurement ID 留空即停用分析；本機只有 `VITE_GA_ENABLE_IN_DEV=true` 才送事件。
- Apps Script URL 是公開 JSONP endpoint，不是 OAuth secret。
- `VITE_USER_DATA_BASE_URL` 覆寫個別玩家主檔與報告細節來源。
- `VITE_USER_DATA_FALLBACK_BASE_URLS` 可用逗號或換行加入備援來源；未自訂主來源時預設包含 jsDelivr。
- 使用者索引預設保留在主站 `/data/users/index.json`；只有需要搬到獨立 CDN 時才設定 `VITE_USER_INDEX_BASE_URL`。

### Google Sheet、Data／Users repo 與 Cloudflare

本機測試待收錄佇列可設定：

```env
FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID=
FFLOGS_REFRESH_QUEUE_SHEET_NAME=pending
FFLOGS_REFRESH_QUEUE_MAX_CODES=50
FFLOGS_REFRESH_QUEUE_COMPLETE_MAX_ROWS=500
FFLOGS_REFRESH_QUEUE_COMPLETE_INCLUDE_HIDDEN=false
GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON={"client_email":"...","private_key":"-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"}
```

發布 Data／Users repo 需要具有對應 push 權限的 `GIT_PAT`。Cloudflare token、TTL 與權限見 [cloudflare-github-pages.md](cloudflare-github-pages.md)。正式 GitHub Secrets／Variables 的完整列表見 [deployment.md](deployment.md)。

## 一般資料更新

開始前先 dry-run 同步，並確定 FFLogs 憑證已設定：

```bash
npm run sync:data -- --dry-run
npm run python -- scripts/fetch_fflogs.py
npm run build:user-data
npm run build:honey-fans
npm run validate:data
```

這會修改來源與公開資料，但不會自動發布 Data repo。正式發布前依序執行相關測試、資料守恆、state 壓縮與：

```bash
npm run data:publish
```

`data:publish` 會驗證舊 snapshot manifest、report／fight／player／checkpoint append-only 守恆，再建立沒有 parent 的 root commit，以 `force-with-lease` 更新 Data repo。完整正式流程由 GitHub Actions 負責，不建議在未理解 [deployment.md](deployment.md) 前手動發布。

若 manifest 明確因 Git 的 CRLF／LF 正規化不一致而損壞，只能在暫停 workflow 且確認原始位元組後使用：

```bash
npm run data:repair-eol
```

此指令仍要求每個檔案完全命中既有大小與 SHA-256，不能繞過資料守恆。

## 驗證選擇

| 變更範圍 | 最小驗證 |
| --- | --- |
| 純 Markdown、公告、文案 | Markdown／本機連結檢查、敏感資訊掃描、`git diff`。 |
| JSON 靜態設定且不影響資料產物 | JSON parse、對應規則檢查、`git diff`。 |
| Vue／工具函式／樣式 | `npm run check`，再依資料讀取範圍選 `test:frontend-data`。 |
| 使用者資料、隊伍榜、全服統計、排行榜薄索引 | 對應建置測試、`validate:data`、必要時 `test:data-conservation`。 |
| FFLogs 限流、重試、hidden report | `test:fetch-fflogs` 與明確的小範圍流程。 |
| GCD、支援統計或戰鬥完整性 | 對應 Python 測試；只有需要外站證據時才執行稽核／回補。 |
| workflow、Data／Users repo、Cloudflare | 對應單元測試或 dry-run，並逐項比對 [deployment.md](deployment.md)。 |

不相關的資料建置不會增加文件變更的可信度，反而可能在本機產生大量無關差異。完整測試指令對照見 [commands.md](commands.md)。
