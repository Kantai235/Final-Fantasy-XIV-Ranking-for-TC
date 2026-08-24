# 部署與自動更新

網站是靜態 Vite 專案，建置後輸出在 `dist/`，由 GitHub Actions 部署到 GitHub Pages。

## 本機建置

```bash
npm run build
```

`npm run build` 會先執行：

1. `npm run build:public-rankings`
2. `npm run build:user-data`
3. `npm run build:honey-fans`
4. `npm run validate:data`

接著由 Vite 建置靜態網站，最後用 `scripts/build_spa_fallback.mjs` 產生 route fallback、SEO/OG 靜態頁、OG PNG、`sitemap.xml`、`robots.txt` 與 `404.html`。

若部署到子路徑，請調整 `config/site.json`：

- `site_url`：正式站台網址，用於 canonical、OG URL 與建置後 route 專屬 HTML 的 `<base href>`。
- `base_path`：Vite base path。
- `allowed_hosts`：本機開發或預覽需要額外允許的 host。

目前正式站台設定為 `https://ranking.init.engineer/`。

## GitHub Actions 排程

`.github/workflows/update_rankings.yml` 會每 30 分鐘執行一次，約在每小時第 17 與 47 分觸發，也支援 `workflow_dispatch` 手動觸發。排程避開整點執行，降低 GitHub Actions 高峰時段延遲機率。

排程會以 GitHub 預設分支上的最新版 workflow 與設定檔執行；本機尚未 commit / push 的 `config/encounters.json` 變更不會被自動更新流程使用。

工作流程摘要：

1. 以 `fetch-depth: 1` 的 partial clone checkout 主 repo 目前程式碼；不下載遷移前的資料歷史。
2. 設定 Python 3.11、Node.js 24 並安裝依賴。
3. 執行 `npm run data:hydrate`，從 `Final-Fantasy-XIV-Ranking-for-TC-Data` 驗證 manifest 與檔案 SHA-256 後，還原 `data/` 及主站共用 `public/data/`。
4. 若有 Cloudflare secrets，先同步 Cache Rules、Facebook 分享爬蟲例外與 Rate Limiting Rules。
5. 讀取 Google Sheet 待收錄名單，再用 FFLogs 憑證執行近期、延遲與歷史掃描；新落地 fight 同時計算 GCD，並小批量回補坦補支援統計、既有 GCD 與戰鬥完整性。
6. 抓取 Honey B. Lovely 趣味榜資料，並執行 `python scripts/fetch_fflogs.py --split-rankings` 整理排行榜來源分片。
7. 執行 `npm run build:user-data`、`npm run build:honey-fans` 與 `npm run validate:data`，產生並驗證個人成績、全服統計、排行榜薄索引、Logs 狀態索引及公開資料。
8. 寫入 `data/update_status.json` 並重建 `public/data/update_status.json`。
9. 執行 `npm run compact:state -- --max-bytes 104857600`，只壓縮可重建欄位與 JSON 空白，保留完整 checkpoint。
10. 重新讀取主 repo 遠端 HEAD；若本輪期間已有新程式碼 commit，立即停止，避免舊 runner 發布資料。
11. 執行 `npm run data:publish`。工具先驗證上一版 Data snapshot，再確認 report、`fight_id`、玩家與 checkpoint 沒有遺失，最後建立沒有 parent 的 root commit，並以 `force-with-lease` 更新 Data repo `main`。Git blob 以來源檔案的原始位元組寫入，且 snapshot 內的 `.gitattributes` 禁止換行轉換，確保 manifest 在 Windows 與 Linux runner 上有相同的大小與 SHA-256。這一步在 Pages 建置前完成，後續失敗也不會遺失 FFLogs 成果。
12. 執行 `scripts/sync_user_leaderboard_repo.mjs`，將個別玩家成績、報告明細與 hidden 使用者差量以單一 root snapshot 更新到 Users repo。
13. 從 Actions cache 還原 `$HOME/.local/share/fonts/ffxiv-og` 的 Noto Sans CJK TC Regular／Bold；cache miss 時才由 `scripts/setup_og_fonts.sh` 限時重試下載 Ubuntu `fonts-noto-cjk`，抽出必要字型並立即保存快取。接著執行 Vite/postbuild，產生主站、route fallback、低基數 SEO/OG 頁、`sitemap.xml`、`robots.txt` 與 `404.html`；`FFXIV_TC_BUILD_USER_SHARE_PAGES` 預設為 `false`，因此正式流程預設不產生逐玩家分享頁與玩家 OG 圖。
14. 執行 `npm run prune:pages-user-data`，讓 Pages artifact 在使用者資料中只保留 `data/users/index.json`；即使人工開啟逐玩家分享頁建置，這一步仍會移除玩家頁與玩家 OG 圖，個別玩家 JSON 由 Users repo 提供。
15. 更新 Google Sheet 待收錄名單結果。
16. 執行 Pages payload strict 稽核並寫入 `data/pages_payload_history.jsonl`，再執行第二次 `data:publish`，把趨勢納入新的 Data root snapshot。
17. 執行 Cloudflare 容量估算與 purge dry-run 摘要。
18. 上傳 `dist/` 並部署到 GitHub Pages；`syncing_files` 暫時失敗時等待 60 秒後重試一次。只有 Pages artifact 已成功上傳才匯總兩次部署結果；若 hydrate、Data publish 或建置先失敗，workflow 會保留原始錯誤，不會再以誤導的 Pages 失敗取代根因。
19. Pages 部署成功後清除會變動的 Cloudflare CDN 快取。

## 緊急部署

`.github/workflows/emergency_deploy.yml` 是手動觸發的緊急部署通道，用於前端 hotfix、空白頁修復、SEO/OG 產物修正或 Cloudflare 快取異常。這條流程 checkout 主 repo 後先由 Data repo hydrate 最新權威快照，再執行 `npm run build`、上傳 `dist/` 並部署 GitHub Pages；它不會執行正式 FFLogs 抓取、不會推進掃描點，也不會發布新資料。

緊急部署同樣只做淺層 partial clone，因為主 repo 只需要目前程式碼，資料則來自 Data repo 的單一 root snapshot。

緊急部署與正式排程共用 `og-fonts-{OS}-{architecture}-{setup script hash}` Actions cache。快取只包含 OG SVG 使用的 Noto Sans CJK TC Regular／Bold，不保存整個 `/usr/share/fonts`；runner 每輪仍會執行 `fc-cache`，並確認 `fontconfig` 可辨識 Regular／Bold family，避免快取存在但實際轉圖時退回錯誤字型。

手動執行方式：

1. 到 GitHub Actions 選擇「緊急部署靜態網站」。
2. 選擇要部署的 branch，通常是 `main`。
3. 選擇 `cloudflare_purge_mode`：
   - `everything`：預設值。適合首頁、`404.html` 或 hashed bundle 仍被 Cloudflare 邊緣節點回舊版本時使用。
   - `scoped`：只清除本專案既有 prefix 與核心檔案，適合一般靜態頁或資料路徑更新。
4. 執行後確認 workflow 的 `記錄 GitHub Pages 部署網址` 與 `清除 Cloudflare CDN 快取` 步驟完成。

緊急部署仍會跑 `npm run build`，因此會從 Data snapshot 重建公開排行榜、個人成績單、排行榜薄索引、Logs 狀態索引、Honey B. Lovely 粉絲榜公開 JSON、低基數 SEO/OG 靜態頁、`sitemap.xml`、`robots.txt` 與 `404.html`，並執行 `validate:data`。建置完成後同樣會執行 `npm run prune:pages-user-data`，讓主站 artifact 在使用者資料中只保留 `data/users/index.json`，不重新帶回大型個別玩家成績單 JSON、逐玩家靜態分享頁或玩家 OG 圖。它不向 FFLogs 取得新資料，也不會同步 Users 或發布 Data repo。

## GitHub Secrets 與 Variables

正式更新必要 Secrets：

- 至少一種完整 FFLogs OAuth 憑證格式：單組 `FFLOGS_CLIENT_ID` + `FFLOGS_CLIENT_SECRET`、成對的 `FFLOGS_CLIENT_IDS` + `FFLOGS_CLIENT_SECRETS`，或 `FFLOGS_CLIENT_CREDENTIALS_JSON`。
- `GIT_PAT`，需可推送 `Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Data` 與 `Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users`，用來發布權威資料快照及同步個人成績單快照。

可選 Secrets：

- `FFLOGS_CLIENT_IDS`
- `FFLOGS_CLIENT_SECRETS`
- `FFLOGS_CLIENT_CREDENTIALS_JSON`
- `CLOUDFLARE_ZONE_ID`
- `CLOUDFLARE_RULES_API_TOKEN`
- `CLOUDFLARE_PURGE_API_TOKEN`
- `CLOUDFLARE_API_TOKEN`，只作為 purge token 相容 fallback
- `VITE_GA_MEASUREMENT_ID`
- `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`，FFLogs 待收錄 Sheet 的 service account JSON
- `GOOGLE_SHEETS_CLIENT_EMAIL` 與 `GOOGLE_SHEETS_PRIVATE_KEY`，前一項的拆分格式
- `FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID`，只作為同名 repository variable 的相容 fallback

常用 Variables：

- `FFLOGS_REPORT_REGION_SCOPE`
- `FFLOGS_INCREMENTAL_LOOKBACK_HOURS`
- `FFLOGS_NO_CLEAR_RETRY_HOURS`
- `FFLOGS_DELAYED_SCAN_ENABLED`
- `FFLOGS_DELAYED_SCAN_RECENT_GAP_HOURS`
- `FFLOGS_DELAYED_SCAN_LOOKBACK_HOURS`
- `FFLOGS_DELAYED_MAX_DEEP_REPORTS_PER_RUN`
- `FFLOGS_HISTORY_SCAN_ENABLED`
- `FFLOGS_HISTORY_SCAN_FULL_RUN`
- `FFLOGS_HISTORY_SCAN_WINDOW_HOURS`
- `FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN`
- `FFLOGS_HISTORY_SCAN_RECENT_GAP_HOURS`
- `FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_RUN`
- `FFLOGS_HISTORY_MAX_DEEP_REPORTS_PER_GROUP_PER_RUN`
- `FFLOGS_MAX_RUNTIME_SECONDS`
- `FFLOGS_RUNTIME_GRACE_SECONDS`
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_ENABLED`
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_LIMIT`
- `FFLOGS_FETCH_GCD_COVERAGE_ENABLED`
- `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN`
- `FFLOGS_RECENT_GCD_BACKFILL_REPORT_LIMIT`
- `FFLOGS_GCD_BACKFILL_REPORT_LIMIT`
- `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`
- `FFLOGS_SUPPORT_METRICS_BACKFILL_REPORT_LIMIT`
- `FFLOGS_SUPPORT_METRICS_BACKFILL_CUTOFF_ISO`
- `FFLOGS_FIGHT_INTEGRITY_ENABLED`
- `FFLOGS_FIGHT_INTEGRITY_REPORT_LIMIT`
- `FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID`
- `FFLOGS_REFRESH_QUEUE_SHEET_NAME`
- `FFLOGS_REFRESH_QUEUE_MAX_CODES`
- `FFLOGS_REFRESH_QUEUE_COMPLETE_MAX_ROWS`
- `FFLOGS_REFRESH_QUEUE_COMPLETE_INCLUDE_HIDDEN`
- `FFLOGS_RETRY_REPORT_CODES`
- `HONEY_FANS_RECENT_DAYS`
- `HONEY_FANS_HISTORY_LIMIT`
- `HONEY_FANS_RECENT_WINDOW_HOURS`
- `HONEY_FANS_HISTORY_WINDOW_HOURS`
- `CLOUDFLARE_HOSTNAME`
- `CLOUDFLARE_MANAGE_RATE_LIMIT`
- `FFXIV_TC_BUILD_USER_SHARE_PAGES`
- `PAGES_PAYLOAD_HISTORY_LIMIT`
- `VITE_GA_MEASUREMENT_ID`
- `VITE_FFLOGS_REPORT_STATUS_WEB_APP_URL`
- `VITE_USER_DATA_BASE_URL`
- `VITE_USER_DATA_FALLBACK_BASE_URLS`
- `VITE_USER_INDEX_BASE_URL`

`VITE_USER_DATA_FALLBACK_BASE_URLS` 已由前端支援，但目前兩條 workflow 尚未傳入此變數；若部署需要自訂備援來源，必須同步在正式更新與緊急部署的 Vite build `env` 加入它，不能只在 repository variables 建立同名值。`VITE_FFLOGS_REPORT_STATUS_WEB_APP_URL` 目前也使用版控內預設 URL，workflow 沒有傳入時不影響建置；只有更換 Apps Script deployment ID 時才需要同步 build env。

workflow 預設掃全部地區候選 report，近期 24 小時完整重查，24-72 小時一般只選未知 report；UCoB 通關規則重判是例外，尚未寫入目前 `clear_rule_revision` 的既有 report 仍會重新深查。歷史補查則以每輪 1 個 168 小時視窗、最多 600 份深層候選且同一 zone/difficulty 群組最多 150 份的設定檢查更舊時間窗是否有新的公開 logs 可抓取，同時對新落地 fight 即時計算 GCD 覆蓋率。主排行榜更新的時間目標是落在 GitHub-hosted runner 6 小時硬上限內；正式排程預設 `FFLOGS_MAX_RUNTIME_SECONDS=6000` 與 `FFLOGS_RUNTIME_GRACE_SECONDS=900`，遇到長冷卻時會保留 `active_scan` 續跑位置，讓後續資料建置與 Data snapshot 發布仍能在同一輪完成。Honey B. Lovely 粉絲榜另以 `HONEY_FANS_*` variables 控制近期掃描天數、每輪歷史檢查上限與查詢切窗，預設為近 3 天、每輪 200 場、24 小時切窗。

坦補支援統計的 stateful 歷史回補預設每輪 25 份，固定切點為 `2026-07-28T05:00:00Z`；設 `FFLOGS_SUPPORT_METRICS_BACKFILL_REPORT_LIMIT=0` 可暫停。戰鬥完整性歷史回補同樣預設每輪 25 份；`FFLOGS_FIGHT_INTEGRITY_ENABLED=false` 停止新增檢核，`FFLOGS_FIGHT_INTEGRITY_REPORT_LIMIT=0` 略過該輪歷史批次，但既有 `hidden_from_public` 結果仍持續生效。

FFLogs 待收錄名單需要額外設定 Google Sheet 與 service account。Apps Script 會寫入 `FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID` 指定的 Sheet；workflow 會用 `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON` secret，或 `GOOGLE_SHEETS_CLIENT_EMAIL` + `GOOGLE_SHEETS_PRIVATE_KEY` secrets，透過 Google Sheets API 讀取 `status=queued|pending|retry` 的 report code。Data snapshot 發布成功後，workflow 會再依公開／hidden 狀態索引、`data/rankings/*.json` 的 `source_reports`、公開 report 分片、fight 完整性結果與 state checkpoint，回寫 `done`、`hidden`、`review_required_data_integrity`、無通關或無繁中服玩家的終止狀態，因此 service account 必須被分享為該 Sheet 的編輯者；Apps Script 執行者帳號也需要可編輯該 Sheet。

## 暫停的維護步驟

`scripts/backfill_missing_fflogs_data.py --limit 250` 的自動步驟目前已在 workflow 內以註解保留，不會隨每輪排程執行。若需要修補既有 report 缺漏欄位，可手動執行：

```bash
npm run backfill:fflogs
npm run build:user-data
npm run validate:data
```

## 既有 report GCD 逐輪回補

workflow 會先執行 `scripts/backfill_gcd_coverage.py --report-limit 25` 補最新候選的 GCD 空洞；這段不使用 `data/state.json` 的 `gcd_report_backfill.cutoff_sort_time`，因此能處理 cutoff 之後才新增、或因 GCD 演算法版本更新而需要重算的既有 report。Repository Variable `FFLOGS_RECENT_GCD_BACKFILL_REPORT_LIMIT` 可調整每輪近期 report 數，設為 `0` 可暫停這段補洞。

`scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 50` 也在 workflow 內啟用，用來從固定切點往舊 report 回補既有 GCD。新 report 的 GCD 仍由 `fetch_fflogs.py` 即時計算；若需要人工追平或重算舊資料，可手動執行：

```bash
npm run backfill:gcd -- --dry-run
npm run backfill:gcd
```

Repository Variable `FFLOGS_GCD_BACKFILL_REPORT_LIMIT` 可調整每輪 report 數；若要固定回補切點，可設定 `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`。未設定切點時，第一次正式執行會把當下時間寫入 `data/state.json` 的 `gcd_report_backfill.cutoff_sort_time`，後續用 `cursor_sort_time` / `cursor_report_code` 接續上一輪最舊 report。

## Cloudflare CDN 摘要

為降低 GitHub Pages origin 流量，正式網域建議放在 Cloudflare 橘雲代理後方，並套用本專案的 Cache Rules、部署後 purge、Rate Limiting Rules 與 Facebook 分享爬蟲例外規則。

檢查將套用的規則：

```bash
npm run cloudflare:apply -- --dry-run
```

正式套用前需設定：

```env
CLOUDFLARE_ZONE_ID=your_zone_id
CLOUDFLARE_RULES_API_TOKEN=your_rules_token
CLOUDFLARE_HOSTNAME=ranking.init.engineer
```

正式套用：

```bash
npm run cloudflare:apply
```

估算目前 `dist/` 在不同 Cloudflare HIT ratio 下的承載量：

```bash
npm run cloudflare:estimate
```

完整 DNS、權限、TTL、Rate Limiting、Facebook 分享爬蟲例外與驗證方式請看 [cloudflare-github-pages.md](cloudflare-github-pages.md)。
