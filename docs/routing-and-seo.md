# 分享網址、SEO 與 OG

前端維持靜態網站架構，不使用後端路由。頁面以 History API 路徑表示，只有偏離預設值的篩選條件才寫入 query string，讓分享連結盡量短。

## 主要路徑

| 頁面 | 路徑範例 |
| --- | --- |
| 排行榜 | `./` |
| 全服統計 | `./stats`、`./stats/savage_m1s` |
| 個人成績單 | `./user/玩家名稱?server=伺服器` |
| 玩家比較 | `./compare?left=玩家A%20@%20伺服器&right=玩家B%20@%20伺服器` |
| 隊伍榜 | `./teams`、`./teams?encounter=savage_m1s` |
| 伺服器對比 | `./servers/陸行鳥/vs/莫古力` |
| 職業分析 | `./jobs?jobScope=role:tank`、`./jobs/Paladin` |
| 近期動態 | `./activity` |
| Honey B. Lovely 粉絲榜 | `./honey-fans` |

排行榜預設副本與隊伍榜預設副本目前都是 `savage_m4s`（零式 M4S / 狡雷），全服統計的「全部副本」與玩家比較的預設防護職能不會寫入 URL。

全服統計的副本、職業分析的單一職業、伺服器對比的左右伺服器會寫入乾淨路徑，讓社群爬蟲可以讀到對應的靜態 SEO/OG。職業分析的職能範圍使用 `jobScope=role:*` query；其他指標、分群、伺服器篩選等細部條件也保留為 query，由前端載入後同步動態 meta。

## 舊連結相容

舊版連結仍會自動套用到對應頁面，例如：

- `?page=user&user=玩家名稱`
- `?user=玩家名稱&server=伺服器`
- `./user?name=玩家名稱`
- `./jobs?job=Paladin`
- `./servers?left=陸行鳥&right=莫古力`

個人成績單路徑中的 `server` 會用來區分同名跨服角色；目前不再把舊伺服器解析成轉服 alias。若使用者只提供玩家名稱，前端會依使用者索引命中第一筆同名資料，但建議分享與搜尋都使用 `玩家 @ 伺服器` 格式。

需要社群爬蟲讀到專屬 OG 時，請使用乾淨路徑，例如 `./user/玩家名稱`、`./stats/{副本 key}`、`./jobs/{職業}` 或 `./servers/{左}/vs/{右}`。

排行榜與全服統計切換副本時會保留已選的伺服器與職業條件，讓使用者可以沿用同一組 query 在多個副本間比較；只有副本本身不支援版本切點時，版本篩選會自動回到 `all`。

## 靜態 SEO/OG 產物

`index.html` 提供站台層級 SEO、Open Graph、Twitter Card、JSON-LD 結構化資料，以及 favicon / Apple touch icon / web app manifest 引用。網站 icon 的設計來源是 `public/favicon.svg`，實際 PNG 與 ICO 由 `npm run build:icons` 產生；站台層級社群預覽圖位於 `public/og-image.png`。

`npm run build` 後會由 `scripts/build_spa_fallback.mjs` 產生：

- `/stats/`
- `/user/`
- `/compare/`
- `/teams/`
- `/servers/`
- `/jobs/`
- `/activity/`
- `/honey-fans/`

這些 route 專屬 HTML 可讓不執行 JavaScript 的社群爬蟲讀到各頁預設標題、描述、canonical 與 OG/Twitter meta。

同一個 postbuild 也會依 `public/data/global_stats.json`、`public/data/server_compare.json` 與 `public/data/users/index.json` 產生：

- `dist/stats/{副本 key}/index.html`
- `dist/jobs/{職業}/index.html`
- `dist/servers/{左}/vs/{右}/index.html`
- `dist/user/{玩家名稱}/index.html`
- `dist/og/stats/*.png`
- `dist/og/jobs/*.png`
- `dist/og/servers/*.png`
- `dist/og/users/*.png`
- `dist/sitemap.xml`
- `dist/robots.txt`

因 LINE、Facebook 與多數 OG 檢查器對 SVG 支援不一致，postbuild 會用 `sharp` 將內部 SVG 模板轉成 1200x630 PNG，讓各頁 `og:image` 與 `twitter:image` 都指向自己的實體預覽圖。玩家頁數會跟收錄角色數同步成長，因此 OG PNG 會使用有限 palette 壓縮，保留 crawler-safe PNG 格式與文字可讀性，同時避免 GitHub Pages artifact 被分享圖撐大。

`dist/robots.txt` 會明確允許 `facebookexternalhit` 與 `Facebot` 抓取分享預覽，首頁仍使用 `public/og-image.png` 作為站台層級預覽圖。

## 前端動態 meta

前端載入後會由 `src/utils/shareMeta.js` 依目前頁面狀態同步：

- `document.title`
- description
- canonical
- OG meta
- Twitter meta

頁首的「分享」按鈕會優先使用瀏覽器 Web Share API，無法使用時改為複製目前分享連結。

因部署目標是靜態 SPA，沒有伺服器端依每一組 query 產生 HTML；不執行 JavaScript 的社群爬蟲會讀到 route 或玩家預設分享資訊，執行 JavaScript 的搜尋或瀏覽器環境則會看到目前篩選、玩家或比較條件的動態標題與描述。

## GitHub Pages fallback

`npm run build` 會在 Vite 建置完成後複製 `dist/index.html` 為 `dist/404.html`，讓 GitHub Pages 重新整理 `./stats`、`./user`、`./servers` 等路徑時仍可交回 Vue SPA 解析。

建置產物只存在於 `dist/`，不會寫回 `data/` 或 `public/data/`，也不會改變 `config/encounters.json`、`data/rankings/` 或個人成績單 JSON schema。
