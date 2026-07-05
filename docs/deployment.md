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

`.github/workflows/update_rankings.yml` 會在每小時第 17 分左右執行一次，也支援 `workflow_dispatch` 手動觸發。排程避開整點執行，降低 GitHub Actions 高峰時段延遲機率。

排程會以 GitHub 預設分支上的最新版 workflow 與設定檔執行；本機尚未 commit / push 的 `config/encounters.json` 變更不會被自動更新流程使用。

工作流程摘要：

1. 以淺層 partial clone checkout 並同步最新分支狀態；workflow 不抓完整 Git 歷史，避免大型資料 repo 的歷史 pack 耗盡 GitHub-hosted runner 磁碟。
2. 設定 Python 3.11 與 Node.js 24。
3. 安裝 Python 與 Node.js 依賴。
4. 若有 Cloudflare secrets，先同步 Cloudflare Cache Rules、Facebook 分享爬蟲例外與 Rate Limiting Rules。
5. 使用 GitHub Secrets 中的 FFLogs 憑證執行 `python scripts/fetch_fflogs.py`，掃描全部地區候選 report，近期 24 小時完整重查、24-72 小時只選未知 report，並以每輪 1 個 168 小時視窗、最多 600 份深層候選且同一 zone/difficulty 群組最多 150 份的歷史補查檢查更舊時間窗是否有新的公開 logs 可抓取，同時對新落地 fight 即時計算 GCD 覆蓋率。正式排程設定可續跑的抓取時間預算，避免 FFLogs 憑證長冷卻時整個 job 被 runner 取消。
6. 執行 `npm run fetch:honey-fans`，以同一組 FFLogs 憑證抓取 Honey B. Lovely 粉絲榜趣味資料；workflow 預設掃近 3 天，並從歷史游標最多檢查 200 場未記錄戰鬥。
7. 執行 `python scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 50`，從固定切點往更舊 report 逐輪追平既有 GCD。
8. 執行 `python scripts/fetch_fflogs.py --split-rankings`，將完整排行榜資料拆分成適合 Git 追蹤的檔案。
9. 執行 `npm run build:user-data`，產生個人成績單、個人成績報告細節、全服統計、近期動態、隊伍榜、伺服器對比、排行榜薄索引、Logs 狀態索引與公開更新狀態。
10. 執行 `npm run build:honey-fans`，由 `data/fun/honey_b_fans.json` 重建 `public/data/fun/honey_b_fans.json`。
11. 執行 `npm run validate:data`，在個人成績單還保留於 `public/data/` 時驗證公開資料契約、來源分片、使用者索引、報告細節、隊伍榜、伺服器對比與 Honey B. Lovely 粉絲榜。
12. 執行 `node scripts/sync_user_leaderboard_repo.mjs`，把 `public/data/users`、`public/data/user-entry-details` 與 hidden delta 的個人成績單同步到 `Final-Fantasy-XIV-Ranking-for-TC-Users`。這一步只抓專用 users repo 的最新 commit/tree 與上一版 `data/sync-manifest.json`，再用 Git index 直接重建下一個 commit，避免完整 clone 舊資料歷史造成 GitHub runner 磁碟不足。
13. 由 workflow 寫入 `data/update_status.json`，記錄本輪 GitHub Actions run、資料更新時間與總量摘要，並執行 `npm run build:public-status` 同步刷新 `public/data/update_status.json`。
14. 執行 `npx vite build` 與 `npm run postbuild`，完成 Vite 建置、route fallback、SEO/OG 靜態頁、OG PNG、`sitemap.xml`、`robots.txt` 與 `404.html`，並把建置秒數寫入後續 payload 稽核。`postbuild` 會讀取 `public/data/users/index.json` 產生玩家分享頁與 OG 圖，因此不可在這一步之前刪除 repo 內的使用者資料。
15. 執行 `npm run prune:pages-user-data`，只移除 `dist/data/users`、`dist/data/user-entry-details`、`dist/data/all/users` 與 `dist/data/all/user-entry-details`；前端正式讀取個人成績單時會改向 users 專用 repo 取得 JSON。
16. 壓縮 `data/state.json`，並檢查 Git 單檔大小是否仍低於 100 MiB。
17. 若 `data`、`public/data/*.json` 或 `public/data/fun/*.json` 有變更，先提交並推送更新，避免後續 artifact 體積超標時白白丟失本輪 FFLogs 抓取成果。
18. 執行 `npm run audit:pages-payload:strict -- --write-history data/pages_payload_history.jsonl`，讓 artifact 體積超過 target 時在上傳 Pages artifact 前失敗，並在 GitHub Step Summary 顯示本輪與上一筆歷史差異。
19. 若 `data/pages_payload_history.jsonl` 有變更，另行提交並推送 payload 稽核歷史。
20. 執行 `npm run cloudflare:estimate` 與 `npm run cloudflare:purge -- --dry-run --summary`，在 Step Summary 顯示 HIT ratio 承載估算與 scoped purge 範圍。
21. 上傳 `dist/` 並部署到 GitHub Pages；若 Pages 服務端在 `syncing_files` 階段回報暫時性失敗，workflow 會等待 60 秒後重試一次。
22. 若有 Cloudflare purge token，部署成功後清除會變動的 CDN 快取。

## 緊急部署

`.github/workflows/emergency_deploy.yml` 是手動觸發的緊急部署通道，用於前端 hotfix、空白頁修復、SEO/OG 產物修正或 Cloudflare 快取異常。這條流程只使用目前分支已提交的 `data/` 與 `public/data/`，執行 `npm run build` 後上傳 `dist/` 並部署 GitHub Pages；它不會執行 `python scripts/fetch_fflogs.py` 的正式抓取流程、不會呼叫 FFLogs API、不會推進 `data/state.json` 掃描點，也不會 commit 新資料。

緊急部署同樣只做淺層 partial clone，因為它只需要目前分支的靜態產物，不需要完整 Git 歷史。

手動執行方式：

1. 到 GitHub Actions 選擇「緊急部署靜態網站」。
2. 選擇要部署的 branch，通常是 `main`。
3. 選擇 `cloudflare_purge_mode`：
   - `everything`：預設值。適合首頁、`404.html` 或 hashed bundle 仍被 Cloudflare 邊緣節點回舊版本時使用。
   - `scoped`：只清除本專案既有 prefix 與核心檔案，適合一般靜態頁或資料路徑更新。
4. 執行後確認 workflow 的 `記錄 GitHub Pages 部署網址` 與 `清除 Cloudflare CDN 快取` 步驟完成。

緊急部署仍會跑 `npm run build`，因此會重建公開排行榜、個人成績單、排行榜薄索引、Logs 狀態索引、Honey B. Lovely 粉絲榜公開 JSON、SEO/OG 靜態頁、`sitemap.xml`、`robots.txt` 與 `404.html`，並執行 `validate:data`。建置完成後同樣會執行 `npm run prune:pages-user-data`，讓主站 artifact 不重新帶回大型個人成績單 JSON。這是為了確保部署出去的靜態產物與 repo 內資料契約一致；差別在於它只重建已提交資料，不向 FFLogs 取得新資料，也不會同步 users 專用 repo。

## GitHub Secrets 與 Variables

必要 Secrets：

- `FFLOGS_CLIENT_ID`
- `FFLOGS_CLIENT_SECRET`
- `GIT_PAT`，需可推送 `Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users`，用來同步個人成績單專用 users repo。

可選 Secrets：

- `FFLOGS_CLIENT_IDS`
- `FFLOGS_CLIENT_SECRETS`
- `FFLOGS_CLIENT_CREDENTIALS_JSON`
- `CLOUDFLARE_ZONE_ID`
- `CLOUDFLARE_RULES_API_TOKEN`
- `CLOUDFLARE_PURGE_API_TOKEN`
- `CLOUDFLARE_API_TOKEN`，只作為 purge token 相容 fallback
- `VITE_GA_MEASUREMENT_ID`

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
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_ENABLED`
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_LIMIT`
- `FFLOGS_FETCH_GCD_COVERAGE_ENABLED`
- `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN`
- `FFLOGS_GCD_BACKFILL_REPORT_LIMIT`
- `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`
- `HONEY_FANS_RECENT_DAYS`
- `HONEY_FANS_HISTORY_LIMIT`
- `HONEY_FANS_RECENT_WINDOW_HOURS`
- `HONEY_FANS_HISTORY_WINDOW_HOURS`
- `CLOUDFLARE_HOSTNAME`
- `CLOUDFLARE_MANAGE_RATE_LIMIT`
- `VITE_GA_MEASUREMENT_ID`

workflow 預設掃全部地區候選 report，近期 24 小時完整重查，24-72 小時一般只選未知 report；UCoB 通關規則重判是例外，尚未寫入目前 `clear_rule_revision` 的既有 report 仍會重新深查。歷史補查則以每輪 1 個 168 小時視窗、最多 600 份深層候選且同一 zone/difficulty 群組最多 150 份的設定檢查更舊時間窗是否有新的公開 logs 可抓取，同時對新落地 fight 即時計算 GCD 覆蓋率。主排行榜更新的時間目標是落在 GitHub-hosted runner 6 小時硬上限內；正式排程預設 `FFLOGS_MAX_RUNTIME_SECONDS=6000` 與 `FFLOGS_RUNTIME_GRACE_SECONDS=900`，遇到長冷卻時會保留 `active_scan` 續跑位置並把後續資料建置與 commit 留在同一輪完成。Honey B. Lovely 粉絲榜另以 `HONEY_FANS_*` variables 控制近期掃描天數、每輪歷史檢查上限與查詢切窗，預設為近 3 天、每輪 200 場、24 小時切窗。

## 暫停的維護步驟

`scripts/backfill_missing_fflogs_data.py --limit 250` 的自動步驟目前已在 workflow 內以註解保留，不會隨每輪排程執行。若需要修補既有 report 缺漏欄位，可手動執行：

```bash
npm run backfill:fflogs
npm run build:user-data
npm run validate:data
```

## 既有 report GCD 逐輪回補

`scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 50` 已在 workflow 內啟用，用來從上線切點往舊 report 回補既有 GCD。新 report 的 GCD 仍由 `fetch_fflogs.py` 即時計算；若需要人工追平或重算舊資料，可手動執行：

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
