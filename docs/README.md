# 文件索引

這個目錄收納 README 拆分後的主題文件。閱讀順序可以依角色挑選：

- 第一次接手專案：先讀 [getting-started.md](getting-started.md)，再讀 [architecture.md](architecture.md)。
- 要調整資料管線：先讀 [data-contracts.md](data-contracts.md)，再讀 [data-pipeline.md](data-pipeline.md)。
- 要處理分享連結、OG 或部署：讀 [routing-and-seo.md](routing-and-seo.md)、[deployment.md](deployment.md) 與 [cloudflare-github-pages.md](cloudflare-github-pages.md)。
- 要改設定檔：搭配 [../config/README.md](../config/README.md)。
- 要追查排行榜來源資料：搭配 [../data/rankings/README.md](../data/rankings/README.md)。

## 文件分類

| 文件 | 主要讀者 | 說明 |
| --- | --- | --- |
| [getting-started.md](getting-started.md) | 所有協作者 | 安裝、環境變數、常用 npm/Python 指令與本機驗證流程。 |
| [architecture.md](architecture.md) | 前端與資料管線開發者 | 專案結構、三層責任邊界、資料流與前端頁面對應。 |
| [data-pipeline.md](data-pipeline.md) | 資料維護者 | FFLogs 抓取、掃描策略、資料建置、Honey B. Lovely 趣味榜、GCD 覆蓋率、手動補抓與壓縮流程。 |
| [data-contracts.md](data-contracts.md) | 所有會碰資料的人 | 副本 key、排行榜分片、去重、hidden report、版本切點與 append-only 保護。 |
| [routing-and-seo.md](routing-and-seo.md) | 前端與部署維護者 | 乾淨路徑、舊 query 相容、SEO/OG fallback、社群預覽圖與 sitemap。 |
| [deployment.md](deployment.md) | 維運者 | GitHub Actions 排程、GitHub Pages 部署、必要 Secrets 與 Cloudflare 串接摘要。 |
| [cloudflare-github-pages.md](cloudflare-github-pages.md) | 維運者 | Cloudflare CDN、Cache Rules、Facebook 分享爬蟲例外、Rate Limiting 與 purge 細節。 |

## 文件維護規則

- README 保持短入口；新增長篇說明時，優先放到本目錄的主題文件。
- 文件內的指令、環境變數、GitHub Actions 排程與資料契約變更時，需同步檢查 [../AGENTS.md](../AGENTS.md)、[../CLAUDE.md](../CLAUDE.md) 與 [../README.md](../README.md) 是否仍一致。
- 文件或註解變更仍需執行 `npm run check`、`npm run build:user-data`，若碰到趣味榜流程也要執行 `npm run build:honey-fans`。
