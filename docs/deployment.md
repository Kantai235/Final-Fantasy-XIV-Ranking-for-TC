# 部署與自動更新

網站是靜態 Vite 專案，建置後輸出在 `dist/`，由 GitHub Actions 部署到 GitHub Pages。

## 本機建置

```bash
npm run build
```

`npm run build` 會先執行：

1. `npm run build:public-rankings`
2. `npm run build:user-data`
3. `npm run validate:data`

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

1. Checkout 並同步最新分支狀態。
2. 設定 Python 3.11 與 Node.js 20。
3. 安裝 Python 與 Node.js 依賴。
4. 若有 Cloudflare secrets，先同步 Cloudflare Cache Rules、Facebook 分享爬蟲例外與 Rate Limiting Rules。
5. 使用 GitHub Secrets 中的 FFLogs 憑證執行 `python scripts/fetch_fflogs.py`，掃描全部地區候選 report，近期 24 小時完整重查、24-72 小時只選未知 report，並以低量歷史補查檢查更舊時間窗是否有新的公開 logs 可抓取，同時對新落地 fight 即時計算 GCD 覆蓋率。
6. 執行 `python scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 200`，從固定切點往更舊 report 逐輪追平既有 GCD。
7. 執行 `python scripts/fetch_fflogs.py --split-rankings`，將完整排行榜資料拆分成適合 Git 追蹤的檔案。
8. 執行 `node scripts/build_user_data.mjs`，產生個人成績單、全服統計、近期動態、隊伍榜、伺服器對比與 `data/update_status.json`。
9. 執行 `npm run build`，在提交前完成公開資料驗證與 Vite 建置。
10. 若 `data` 或 `public/data` 有變更，提交並推送更新。
11. 上傳 `dist/` 並部署到 GitHub Pages。
12. 若有 Cloudflare purge token，部署成功後清除會變動的 CDN 快取。

## GitHub Secrets 與 Variables

必要 Secrets：

- `FFLOGS_CLIENT_ID`
- `FFLOGS_CLIENT_SECRET`

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
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_ENABLED`
- `FFLOGS_EXISTING_REPORT_STATUS_CHECK_LIMIT`
- `FFLOGS_FETCH_GCD_COVERAGE_ENABLED`
- `FFLOGS_FETCH_GCD_COVERAGE_MAX_FIGHTS_PER_RUN`
- `FFLOGS_GCD_BACKFILL_REPORT_LIMIT`
- `FFLOGS_GCD_BACKFILL_CUTOFF_ISO`
- `CLOUDFLARE_HOSTNAME`
- `CLOUDFLARE_MANAGE_RATE_LIMIT`
- `VITE_GA_MEASUREMENT_ID`

workflow 預設掃全部地區候選 report，近期 24 小時完整重查，24-72 小時只選未知 report，並以低量歷史補查檢查更舊時間窗是否有新的公開 logs 可抓取，同時對新落地 fight 即時計算 GCD 覆蓋率。

## 暫停的維護步驟

`scripts/backfill_missing_fflogs_data.py --limit 250` 的自動步驟目前已在 workflow 內以註解保留，不會隨每輪排程執行。若需要修補既有 report 缺漏欄位，可手動執行：

```bash
npm run backfill:fflogs
npm run build:user-data
npm run validate:data
```

## 既有 report GCD 逐輪回補

`scripts/backfill_gcd_coverage.py --stateful-report-backfill --report-limit 200` 已在 workflow 內啟用，用來從上線切點往舊 report 回補既有 GCD。新 report 的 GCD 仍由 `fetch_fflogs.py` 即時計算；若需要人工追平或重算舊資料，可手動執行：

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
