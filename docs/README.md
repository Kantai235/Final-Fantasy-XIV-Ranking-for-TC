# 文件索引

這個目錄保存 README 拆分後的主題文件。每項規則只應有一份主要說明，其它文件以連結補充脈絡，避免同一個排程、欄位或演算法散落多份副本後逐漸不一致。

## 建議閱讀順序

- 第一次接手：先讀 [getting-started.md](getting-started.md)，再讀 [architecture.md](architecture.md) 與 [codebase-map.md](codebase-map.md)。
- 要理解網站：讀 [features.md](features.md) 與 [routing-and-seo.md](routing-and-seo.md)。
- 要修改資料：先讀 [data-contracts.md](data-contracts.md)，再讀 [data-pipeline.md](data-pipeline.md) 與 [commands.md](commands.md)。
- 要維運部署：讀 [deployment.md](deployment.md) 與 [cloudflare-github-pages.md](cloudflare-github-pages.md)。
- 要改副本或 FFLogs 設定：讀 [../config/README.md](../config/README.md)。
- 要設定 report 即時查詢：讀 [../apps-script/fflogs-report-status/README.md](../apps-script/fflogs-report-status/README.md)。

## 文件分類與權威範圍

| 文件 | 主要讀者 | 主要權威範圍 |
| --- | --- | --- |
| [../README.md](../README.md) | 所有人 | 專案定位、最短啟動流程、安全原則與文件入口。 |
| [getting-started.md](getting-started.md) | 新協作者 | 安裝、環境變數、Data repo hydrate 與驗證選擇。 |
| [commands.md](commands.md) | 開發者／維運者 | `package.json` 全部指令、外部存取與寫入風險。 |
| [features.md](features.md) | 產品、前端與資料開發者 | 使用者可見頁面、偏好、版本、支援統計與成就行為。 |
| [architecture.md](architecture.md) | 全體開發者 | 三層責任邊界、repo 分工、資料流與前端讀取邊界。 |
| [codebase-map.md](codebase-map.md) | 接手與審查者 | 每個程式碼、設定、workflow 與測試檔案的責任。 |
| [data-pipeline.md](data-pipeline.md) | 資料維護者 | FFLogs 掃描、支援統計、GCD、完整性檢核與回補。 |
| [data-contracts.md](data-contracts.md) | 所有會碰資料的人 | 副本 key、來源／公開 JSON、去重、hidden delta、版本與 append-only。 |
| [routing-and-seo.md](routing-and-seo.md) | 前端／部署維護者 | History API 路徑、舊網址相容、SEO／OG 與 fallback。 |
| [deployment.md](deployment.md) | 維運者 | GitHub Actions、Secrets／Variables、Data／Users repo 與 Pages 部署。 |
| [cloudflare-github-pages.md](cloudflare-github-pages.md) | 維運者 | Cloudflare DNS、快取、節流、purge 與事故處理。 |
| [../config/README.md](../config/README.md) | 資料維護者 | 設定欄位與不能自動推導的業務語意。 |
| [../apps-script/fflogs-report-status/README.md](../apps-script/fflogs-report-status/README.md) | 維運者 | Apps Script、Google Sheet 待處理名單與 report 即時可讀狀態。 |
| [Data repo 的 data/rankings/README.md](https://github.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Data/blob/main/data/rankings/README.md) | 資料維護者 | 權威排行榜來源主檔與 report 分片實體格式。 |

`docs/gcd_xivanalysis_audit_*.json` 是固定抽樣稽核證據，不是人工維護的規格文件；產生方式與判讀規則以 [data-pipeline.md](data-pipeline.md) 為準。

## 文件維護規則

- README 保持入口層級；長篇功能、指令、資料或部署規則放入對應主題文件。
- 新增、刪除或重新命名程式碼／測試檔時，更新 [codebase-map.md](codebase-map.md)。
- 新增或修改 npm script 時，更新 [commands.md](commands.md)。
- 指令、環境變數、排程、資料契約或技術決策改變時，逐一檢查 [../AGENTS.md](../AGENTS.md)、[../CLAUDE.md](../CLAUDE.md) 與 [../README.md](../README.md)。
- 純文件、公告或文案變更不執行使用者資料建置；只做 Markdown／連結／檔案型態檢查與 `git diff`。只有實際影響資料產物、前端資料契約或 workflow 輸出時，才執行對應建置與驗證。
- 文件中的範例不得包含真實 OAuth、service account、GitHub PAT 或 Cloudflare token。
