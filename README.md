# FFXIV 繁中服排行榜

Final Fantasy XIV 繁中服排行榜是一個以 FFLogs 公開資料為來源的 Vue 3 / Vite 網站，用來整理繁中服玩家在零式、極、幻與絕本中的公開通關成績。

專案包含兩個主要部分：

- 前端網站：瀏覽排行榜、全服統計、個人成績單、玩家比較、職業分析與近期動態。
- 資料管線：透過 FFLogs API 抓取報告，篩選繁中服玩家，產生排行榜、個人成績單與全服統計資料。

> 這是非官方社群工具，資料來自 FFLogs 公開報告；顯示結果不代表遊戲內完整人口或所有通關紀錄。

## 功能

- 依副本查看排行榜，支援伺服器、職業類型、職業、關鍵字與排序篩選。
- 顯示 DPS、rDPS、aDPS、Active、通關時間與紀錄時間。
- 個人成績單可查看角色各副本最佳紀錄、歷史紀錄與常同場隊友，並依職能或職業篩選成績與趨勢。
- 玩家比較可選擇防護、治療、近戰、遠程物理或遠程魔法職業，並排比較兩名玩家的公開成績。
- 全服統計可查看伺服器分布、職業分布、零式進度概覽與資料狀態。
- 職業分析可查看特定職業在副本與伺服器中的分布。
- 支援深色 / 亮色主題。
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
│   ├── App.vue                # 主要前端介面
│   └── main.js                # Vue 入口
├── scripts/
│   ├── fetch_fflogs.py        # 抓取並整理 FFLogs 排行榜資料
│   └── build_user_data.mjs    # 產生個人成績單與全服統計資料
├── config/
│   ├── encounters.json        # 副本、FFLogs ID 與掃描起始日期
│   ├── fflogs.json            # 抓取範圍、限流、重試與手動補抓設定
│   └── site.json              # Vite base path 與允許 host
├── data/
│   ├── rankings/              # 原始排行榜資料
│   └── state.json             # 掃描進度與處理狀態
├── public/
│   ├── data/                  # 網站讀取的公開資料
│   └── icons/jobs/            # 職業圖示
└── .github/workflows/
    └── update_rankings.yml    # 定時更新排行榜資料
```

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

## 常用指令

啟動開發伺服器：

```bash
npm run dev
```

產生個人成績單與全服統計資料：

```bash
npm run build:user-data
```

建置靜態網站：

```bash
npm run build
```

## 同步 GitHub Actions 與本機資料

如果 GitHub Actions 和本機爬蟲同時產生新資料，先用 dry-run 檢查：

```bash
npm run sync:data -- --dry-run
```

確認沒有 `REMOVAL` 或 `CONFLICT` 後，再同步遠端並自動合併來源資料：

```bash
npm run sync:data
```

這個工具會保護 append-only 資料：`data/state.json` 的 report 狀態、`data/rankings/*.json` 的 reports，以及 `config/encounters.json` 的 encounter key。如果任一邊刪除了既有資料，工具會停止並列出需要人工確認的項目。合併成功後會重建 `public/data` 產物；若只想合併來源資料，可以加上 `--no-rebuild`。

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
   - 透過 FFLogs API 掃描中國區域公開報告。
   - 篩選繁中服伺服器玩家。
   - 更新 `data/rankings/*.json`、`public/data/rankings/*.json` 與 `data/state.json`。

2. `npm run build:user-data`
   - 讀取排行榜資料。
   - 產生 `public/data/users/*.json`。
   - 產生 `public/data/users/index.json`。
   - 產生 `public/data/global_stats.json`。

3. `npm run build`
   - 先自動執行 `build:user-data`。
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

## 自動更新

`.github/workflows/update_rankings.yml` 會每小時執行一次，也支援手動觸發。

工作流程會：

1. 安裝 Python 與 Node.js。
2. 安裝 Python 依賴。
3. 使用 GitHub Secrets 中的 FFLogs 憑證執行抓取腳本。
4. 產生個人成績單與全服統計資料。
5. 若 `data` 或 `public/data` 有變更，提交並推送更新。

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

若部署到子路徑，請調整 `config/site.json` 的 `base_path`。本機開發或預覽需要額外允許 host 時，也可在同一個檔案調整 `allowed_hosts`。

## 注意事項

- `data/state.json` 是抓取進度狀態，手動修改前請先確認目前掃描狀態。
- `public/data/users/` 是由 `scripts/build_user_data.mjs` 重新產生的資料。
- FFLogs API 有限流，`config/fflogs.json` 可調整請求限制、重試與冷卻時間。
- 排行榜只統計公開報告中可解析且符合繁中服條件的資料。
