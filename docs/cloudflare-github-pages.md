# Cloudflare CDN 與 GitHub Pages 流量保護

本專案部署在 GitHub Pages，站台本身是純靜態 Vue/Vite 產物。Cloudflare 的角色是放在 GitHub Pages 前方做快取、壓縮、部署後清除快取與節流，目標是讓大量重複瀏覽命中 Cloudflare 邊緣節點，降低 GitHub Pages origin 流量，同時讓半小時一次的資料更新能在部署後快速生效。

查證日期：2026-05-13。

## 官方限制脈絡

- GitHub Pages 官方文件列出每月 100 GB 軟性頻寬上限；若超出，GitHub 可能無法服務站台或建議在前方放第三方 CDN。
- Cloudflare 預設會依副檔名快取靜態資源，但不會預設快取 HTML 或 JSON。本專案最大的流量壓力正是 `public/data/**/*.json`，所以必須用 Cache Rules 明確設定。
- Cloudflare Free 方案可設定 Edge Cache TTL，但最短 Edge TTL 是 2 小時；本專案每半小時更新資料，因此不能只靠 TTL 自然過期，必須在 GitHub Pages 部署成功後透過 Purge API 主動清除會變動的路徑。
- Cloudflare Rate Limiting Rules 可在邊緣節點對超量請求回應 429；Free 方案目前只有 1 條規則、10 秒計數週期，因此本專案採用保守的單條全站節流規則。
- Facebook 分享偵錯工具若回 403，通常不是 GitHub Pages 靜態檔本身，而是 Cloudflare 的 Security Level、Under Attack mode、國家/ASN 自訂規則或節流擋到 Meta 爬蟲；Meta 常用 ASN 為 `AS32934` 與 `AS63293`。

參考文件：

- [GitHub Pages limits](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits)
- [Cloudflare default cache behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/)
- [Cloudflare Cache Rules settings](https://developers.cloudflare.com/cache/how-to/cache-rules/settings/)
- [Cloudflare Rate Limiting Rules](https://developers.cloudflare.com/waf/rate-limiting-rules/)
- [GitHub Pages custom domain DNS records](https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site/managing-a-custom-domain-for-your-github-pages-site)

## DNS 設定

目前 `config/site.json` 的正式站台是 `https://ranking.init.engineer/`。Cloudflare DNS 應維持橘雲代理，讓請求先進 Cloudflare 再到 GitHub Pages。

若使用 apex 網域，GitHub Pages 官方建議設定四筆 A 與四筆 AAAA；若只用 `ranking.init.engineer` 這類子網域，設定 CNAME 到 GitHub Pages 預設網域即可。不要使用 wildcard DNS，避免 GitHub Pages custom domain takeover 風險。

GitHub Pages 自訂網域仍需在 repository Settings → Pages 設定。因本專案用 GitHub Actions 部署 Pages artifact，不需要把 `CNAME` 檔提交到 repo。

## 建議快取策略

`scripts/apply_cloudflare_rules.mjs` 會建立或更新 `http_request_cache_settings` phase 的 Cache Rules：

| 路徑 | Edge TTL | Browser TTL | 原因 |
| --- | ---: | ---: | --- |
| `/assets/*` | 365 天 | 365 天 | Vite 產物檔名含 hash，可長效快取。 |
| `/icons/*`、favicon、`site.webmanifest`、`/og/*`、`/og-image.png` | 6 小時 | 1 小時 | 網站圖示、職業圖示與 OG 圖可快取，但 OG 圖會隨資料建置更新。 |
| `/data/*` | 2 小時 | 5 分鐘 | 排行榜 JSON 每半小時排程更新；Edge TTL 撐高 HIT ratio，部署成功後由 workflow purge 變動路徑。 |
| SPA HTML、route fallback、`robots.txt`、`sitemap.xml` | 2 小時 | 5 分鐘 | HTML 是靜態產物；部署後 purge 讓 SEO/OG fallback 快速更新。 |

4xx 與 5xx 不做長時間快取，避免 GitHub Pages 暫時錯誤被放大。

## 部署後 Purge 策略

`.github/workflows/update_rankings.yml` 在 `actions/deploy-pages` 成功後會執行：

```bash
npm run cloudflare:purge
```

這支腳本會用兩個 Cloudflare Purge API 請求處理會隨半小時資料更新變動的內容：

- Prefix purge：`/data`、`/stats`、`/user`、`/compare`、`/teams`、`/servers`、`/jobs`、`/activity`、`/og`
- File purge：首頁、`index.html`、`404.html`、`sitemap.xml`、`robots.txt`、`og-image.png`、favicon、Apple touch icon 與 `site.webmanifest`

這比每半小時 purge everything 更適合本專案，因為 Vite hashed assets 和職業圖示可以繼續長效命中 Cloudflare，不必每次資料更新都讓所有靜態資源重新冷啟動。

## 建議節流策略

`scripts/apply_cloudflare_rules.mjs` 會先在 `http_request_firewall_custom` phase 建立 Facebook 分享爬蟲例外規則。這條規則只套用於本 hostname 的 GET/HEAD 請求，條件是來源 ASN 為 `32934` / `63293`，或 Cloudflare 已驗證的 Facebook bot，並跳過後續自訂規則、Rate Limiting、Super Bot Fight Mode、WAF Managed Rules、Security Level、User Agent Blocking 與 Browser Integrity Check。這是為了避免 Facebook 分享偵錯工具讀不到靜態 HTML 與 OG 圖而回報 403；一般使用者與未驗證的仿冒 User-Agent 不會因這條規則直接放行。

`scripts/apply_cloudflare_rules.mjs` 預設也會建立 `http_ratelimit` phase 的單條規則：

- 條件：非 verified bot，且路徑不是 `/robots.txt`。
- 計數：每個 IP 10 秒 240 次請求。
- 動作：超量時回應 429，10 秒後解除。

這個門檻遠高於一般使用者首屏載入量，主要攔截短時間掃全站 JSON、OG 圖或 sitemap 的異常爬取。若 Cloudflare 方案已有更細緻的 Rate Limiting Rules，可用 `--skip-rate-limit` 只套用快取規則。

## 套用方式

先用 dry-run 檢查即將套用的規則：

```bash
npm run cloudflare:apply -- --dry-run
```

正式套用前，在本機 `.env` 或 shell 環境設定：

```env
CLOUDFLARE_ZONE_ID=你的 zone id
CLOUDFLARE_RULES_API_TOKEN=你的規則管理 API token
CLOUDFLARE_HOSTNAME=ranking.init.engineer
# 可選：調整 Rulesets API 暫時性錯誤的重試次數與基礎等待毫秒數。
CLOUDFLARE_RULES_API_MAX_ATTEMPTS=3
CLOUDFLARE_RULES_API_RETRY_BASE_MS=750
# 可選：調整資料、HTML、媒體與 hashed 靜態資源的 Edge/Browser TTL。
CLOUDFLARE_DATA_EDGE_TTL_SECONDS=7200
CLOUDFLARE_DATA_BROWSER_TTL_SECONDS=300
CLOUDFLARE_HTML_EDGE_TTL_SECONDS=7200
CLOUDFLARE_HTML_BROWSER_TTL_SECONDS=300
CLOUDFLARE_MEDIA_EDGE_TTL_SECONDS=21600
CLOUDFLARE_MEDIA_BROWSER_TTL_SECONDS=3600
CLOUDFLARE_STATIC_EDGE_TTL_SECONDS=31536000
CLOUDFLARE_STATIC_BROWSER_TTL_SECONDS=31536000
```

規則管理 token 最小權限：

- `Zone > Cache Rules > Edit`（新版介面可能顯示為 `Cache Settings Write`）
- Facebook 分享爬蟲例外與 Rate Limiting 若要由腳本套用，另需 `Zone WAF Edit`（新版介面可能顯示為 `Zone WAF Write`）
- 若只想讓 workflow 管理 Cache Rules 與 Facebook 分享爬蟲例外、不要管理 Rate Limiting，可在 GitHub Variables 設定 `CLOUDFLARE_MANAGE_RATE_LIMIT=false`；此時 token 仍需要 WAF 權限，因為 Facebook 例外屬於 WAF Custom Rules。
- GitHub Actions 部署後清除快取另需一組較低權限的 `CLOUDFLARE_PURGE_API_TOKEN`，權限只要 `Cache Purge`。

正式套用：

```bash
npm run cloudflare:apply
```

只套用快取、不碰節流：

```bash
npm run cloudflare:apply -- --skip-rate-limit
```

若希望 GitHub Actions 自動維護 Cloudflare 規則，請在 repository secrets 設定：

```text
CLOUDFLARE_ZONE_ID
CLOUDFLARE_RULES_API_TOKEN
CLOUDFLARE_PURGE_API_TOKEN
```

workflow 會在安裝依賴後先執行 `npm run cloudflare:apply -- --allow-transient-failure`，確保 `/data/*`、HTML route、OG 圖、assets、Facebook 分享爬蟲例外與 Rate Limiting 規則存在。Cloudflare Rulesets API 回傳 5xx、429 或網路暫時錯誤時，腳本會先重試；若最後仍失敗，workflow 會把本次規則同步標成 warning 並繼續更新排行榜。這是為了避免 Cloudflare 外部 API 短暫異常阻斷 FFLogs 抓取；若是 4xx 權限不足、token 錯誤或 payload 不合法，仍會讓 workflow 失敗。部署成功後再執行 `npm run cloudflare:purge`。如果不想讓 workflow 管理 Rate Limiting Rules，可在 repository variables 設定：

```text
CLOUDFLARE_MANAGE_RATE_LIMIT=false
```

手動檢查部署後 purge 會送出的內容：

```bash
npm run cloudflare:purge -- --dry-run
```

## 驗證方式

部署完成後檢查回應標頭：

```bash
curl -I https://ranking.init.engineer/data/rankings/savage_m4s.json
curl -I https://ranking.init.engineer/assets/index-q40GMfNq.js
```

第一次通常會看到 `CF-Cache-Status: MISS` 或 `EXPIRED`，第二次應該轉為 `HIT`。若 JSON 維持 `DYNAMIC`，代表 `/data/*` Cache Rule 沒有命中。

估算目前建置產物的承載量：

```bash
npm run build
npm run cloudflare:estimate
```

`cloudflare:estimate` 會用目前 `dist/` 的 gzip / brotli 大小估算在不同 Cloudflare HIT ratio 下，GitHub Pages 100 GB/月 origin 流量約能承受多少次頁面載入。

## 流量估算公式

簡化公式：

```text
GitHub origin 流量 ~= 使用者流量 * (1 - Cloudflare HIT ratio)
可承載頁面載入次數 ~= 100 GB / (單次載入大小 * (1 - Cloudflare HIT ratio))
```

舉例：若排行榜首屏 gzip 後約 623 KB，Cloudflare HIT 95%，則 GitHub origin 只需要承擔約 5% 請求，約可支撐 `100 GB / (623 KB * 0.05)`，也就是三百萬次以上排行榜首屏載入。實際數字請以 `npm run cloudflare:estimate` 的本機輸出與 Cloudflare Analytics 為準。

## 注意事項

- Cloudflare 快取降低的是 GitHub Pages origin 流量；使用者到 Cloudflare 的邊緣流量仍會存在，需遵守 Cloudflare 方案的服務條款與合理使用。
- 不要把 `CLOUDFLARE_API_TOKEN` 寫入文件、Log 或 commit。
- 若排程剛完成但使用者仍看到舊資料，先確認 `/data/*` 的 Edge TTL 是否仍在 30 分鐘內；緊急時可在 Cloudflare Dashboard 對 hostname 或 `/data/` prefix purge cache。
- 本設定不改變資料管線。FFLogs API 抓取仍只允許由 `scripts/fetch_fflogs.py` 執行，前端仍只讀 `public/data/` 靜態 JSON。
