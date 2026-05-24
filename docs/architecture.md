# 系統架構

本專案是靜態化分離架構：Python 負責抓取 FFLogs，Node.js 負責把來源資料建置成網站可讀的統計 JSON，Vue 只負責呈現 `public/data/`。

```mermaid
flowchart LR
  FFLogs["FFLogs GraphQL API"] --> Fetch["scripts/fetch_fflogs.py"]
  Fetch --> Source["data/rankings/ 與 data/state.json"]
  Source --> Builder["scripts/build_user_data.mjs"]
  Builder --> Public["public/data/ 靜態 JSON"]
  Public --> Vue["src/ Vue 3 / Vite 前端"]
```

## 三層責任邊界

### Data Fetching Layer

`scripts/fetch_fflogs.py` 是唯一可直接呼叫 FFLogs GraphQL API 的資料管線入口，負責：

- OAuth 憑證讀取與多憑證輪替。
- FFLogs 限流、重試、暫時性 500/502/503/504 與逾時處理。
- 淺層 reports 掃描、延遲掃描、歷史補查與既有 report 狀態巡檢。
- 以 `masterData.actors(type: "Player")` 與 `playerDetails` 確認繁中服玩家。
- 寫入 `data/rankings/`、`public/data/rankings/` 與 `data/state.json`。

這一層只保存可重建排行榜所需的 report/fight/player 脈絡，不應輸出 UI 專用格式。

### Data Building Layer

`scripts/build_user_data.mjs` 負責把來源資料整理成前端可直接讀取的靜態 JSON：

- `public/data/users/*.json`
- `public/data/users/index.json`
- `public/data/global_stats.json`
- `public/data/activity.json`
- `public/data/team_rankings.json`
- `public/data/server_compare.json`
- `public/data/all/` 完整資料鏡像

複雜排序、分位數、隊友統計、職業分布與版本切片應在這一層完成。若新增前端畫面需要新的統計欄位，請先擴充這一層，再讓 Vue 讀取結果。
同名角色若有公開轉服紀錄，公開衍生資料也在這一層統一收斂到最新公開紀錄所在伺服器，並保留 alias 與原始伺服器欄位供搜尋與追溯。

全域公告是例外的營運靜態內容：`public/data/announcements.json` 直接隨 commit 維護，不從 FFLogs 或使用者統計建置而來；`build_user_data.mjs` 只負責把它同步到 `public/data/all/announcements.json`。這讓公告可快速發佈，同時不碰 append-only 排行榜歷史資料。

### UI Presentation Layer

`src/` 是 Vue 3 / Vite 前端，只能讀取 `public/data/` 靜態 JSON：

- `src/pages/` 放主要頁面。
- `src/components/` 放跨頁共用元件。
- `src/composables/` 放前端狀態、篩選、排序與資料讀取邏輯。
- `src/utils/` 放格式化、分享網址狀態、靜態資料 URL 與 fetch 工具。
- `src/domain/` 放 FFXIV 職業與職能等領域設定。

前端元件不得直接呼叫 FFLogs API，也不要在 Vue 內重做全服統計或資料聚合。
公告元件只能讀取 `public/data/announcements.json`，並用瀏覽器 `localStorage` 保存使用者已關閉公告 id；這個狀態不會寫回公開資料。

## 專案結構

```text
.
├── src/
│   ├── App.vue
│   ├── components/
│   ├── composables/
│   ├── domain/
│   ├── pages/
│   ├── styles/
│   ├── utils/
│   └── main.js
├── scripts/
│   ├── fetch_fflogs.py
│   ├── gcd_coverage_core.py
│   ├── backfill_gcd_coverage.py
│   ├── backfill_gcd_coverage_xivanalysis.py
│   ├── build_user_data.mjs
│   ├── validate_data.mjs
│   ├── compact_ranking_data.py
│   ├── compact_state.py
│   └── build_spa_fallback.mjs
├── config/
│   ├── encounters.json
│   ├── fflogs.json
│   └── site.json
├── data/
│   ├── rankings/
│   ├── state.json
│   └── update_status.json
├── public/
│   ├── data/
│   ├── favicon.svg
│   ├── site.webmanifest
│   └── icons/jobs/
├── docs/
└── .github/workflows/update_rankings.yml
```

## 前端頁面範圍

- 排行榜：依副本、伺服器、職業類型、職業、關鍵字與版本篩選成績。
- 全服統計：伺服器分布、職業分布、零式進度概覽與資料狀態。
- 個人成績單：各副本最佳紀錄、歷史紀錄、同職分位、常同場隊友與分享用代表職業。
- 玩家比較：依職能或職業並排比較兩名玩家。
- 隊伍榜：同場 8 人公開紀錄的最速通關、隊伍 rDPS 與成員組成。
- 伺服器對比：收錄玩家、副本通關、職能比例、熱門職業與副本落點。
- 職業分析：各職能與職業的 rDPS 分位、副本分布、伺服器分布與代表紀錄。
- 近期動態：最新公開成績、刷新個人最佳、新收錄玩家、伺服器活躍與副本活躍。

## 功能旗標

臨時隱藏或恢復作者相關 UI 標示、社群連結或 GCD 覆蓋率時，只調整 `src/utils/siteFeatures.js`：

- `顯示作者相關標示`
- `顯示社群連結`
- `顯示Gcd覆蓋率`

目前 `顯示Gcd覆蓋率=true`，網站會顯示 GCD 欄位。這些旗標只影響前端呈現，不改動公開資料或排行榜歷史資料結構。
