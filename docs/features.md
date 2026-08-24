# 功能與頁面

本文件描述使用者看得到的功能，以及這些功能由哪一層資料與程式碼支援。JSON 欄位與去重細節請看 [data-contracts.md](data-contracts.md)，網址狀態請看 [routing-and-seo.md](routing-and-seo.md)，逐檔責任請看 [codebase-map.md](codebase-map.md)。

## 頁面總覽

| 頁面 | 路徑 | 主要資料 | 前端入口 |
| --- | --- | --- | --- |
| 排行榜 | `/` | `data/encounters.json`、`data/ranking-tables/*.json`、`data/ranking-details/*.json` | `src/pages/RankingPage.vue` |
| 全服統計 | `/stats` | `data/global_stats.json` | `src/pages/GlobalStatsPage.vue` |
| 個人成績單 | `/user/{玩家}` | `data/users/index.json`、Users repo 的玩家主檔與報告細節 | `src/pages/UserProfilePage.vue` |
| 玩家比較 | `/compare` | 兩份個人成績單 | `src/pages/ComparePage.vue` |
| 隊伍榜 | `/teams` | `data/team_rankings.json` | `src/pages/TeamRankingsPage.vue` |
| 伺服器對比 | `/servers/{左}/vs/{右}` | `data/server_compare.json` | `src/pages/ServerComparePage.vue` |
| 職業分析 | `/jobs`、`/jobs/{職業}` | `data/global_stats.json` | `src/pages/JobAnalysisPage.vue` |
| 近期動態 | `/activity` | `data/activity.json` | `src/pages/ActivityPage.vue` |
| 常見問題／Logs 檢查 | `/faq`；舊 `/logs` 相容 | report 狀態索引、更新狀態、選填 Apps Script | `src/pages/ReportStatusPage.vue` |
| Honey B. Lovely 粉絲榜 | `/honey-fans` | `data/fun/honey_b_fans.json` | `src/pages/HoneyFansPage.vue` |

`src/App.vue` 依 `src/utils/urlState.js` 解析出的頁面模式切換非同步頁面元件；專案沒有額外的 Vue Router 依賴。所有頁面共用 `src/composables/useRankingApp.js` 的狀態與載入流程，排行榜列的正規化、排序與報告細節按需載入則拆在 `src/composables/rankingApp/useRankingData.js`。

## 排行榜

首頁與隊伍榜預設副本均為 `savage_m8s`（零式 M8S／呼嘯之劍），預設以 rDPS 由高到低排序。排行榜支援：

- 副本、伺服器、職能、職業與關鍵字篩選。
- DPS、rDPS、aDPS、Active、GCD、通關時間、紀錄時間與職能專屬欄位排序。
- 每頁 100 筆的分頁。
- 以報告按鈕按需載入完整條目，再顯示 FFLogs、xivanalysis 與 ffreplay 連結。
- 在資料能唯一辨識同場恰有兩名坦克或兩名補師時，展開另一名同職能玩家；聯盟副本等無法唯一配對的情況不猜測搭檔。

欄位會依職能改變：

- 輸出職業：DPS、rDPS、aDPS。
- 坦克：承傷、自補、個人防護、團隊防護、減傷覆蓋。
- 治療職業：HPS、純治療、防護量、OH%。

三類都保留 Active、GCD、rDPS、通關時間、版本／時效與紀錄時間。手機版把坦克與治療的主要統計收斂成緊湊數值列；總量一萬以上以一位小數的 K／M 縮寫，仍可透過提示查看完整整數。

### 版本紀錄與紀錄時效

設定視窗的「版本紀錄」是排行榜與個人成績單共用的瀏覽器偏好，預設關閉：

- 開啟時，排行榜顯示每筆 `game_version` 並提供累積版本選單。選擇 7.1 會包含 7.0、7.05 與 7.1；未指定時使用目前已開放的最新實際版本，目前為 7.2。
- 若選擇的版本早於副本 `profile_summary_available_from`，畫面會提示副本的繁中服開放版本，而不是顯示泛用空狀態。
- 關閉時，排行榜隱藏遊戲版本欄；只有設定 `version_cutoff` 的副本提供全部／有效／過版紀錄時效篩選。
- 兩種模式只使用薄索引現有的 `game_version` 與 `is_obsolete_record`，不輸出或重建重複的版本排行榜切片。

建置產物 `game_version` 的版本順序與切點只讀取 `config/game_versions.json`。建置層會依 `recorded_at_iso` 寫入欄位；遊戲版本標籤不改變 PR、排名或有效／過版判定。個人成績簡表另有 `src/utils/userProfileClearSummary.js` 的歷史畫面快照範圍，兩者不能混成同一種規則。

## 個人成績單

個人成績單以「角色名稱 + 伺服器」作為公開身分範圍。同名角色出現在不同伺服器時會分成不同成績單，不再自動合併為轉服 alias。

頁面提供：

- 各副本最佳紀錄、完整公開歷史、同職分位與常同場隊友。
- 職能／職業、累積遊戲版本與歷史表格欄位排序。
- PR／前 N% 顯示偏好；PR 模式會讓代表列與歷史列優先依 `performance.score_percentile` 排序，缺值才由排名與樣本數回推。
- 單一時間軸整合所有可解析時間的紀錄，可篩選副本、職能／職業、PR／rDPS 與 7／14／30／90 天、全部或自訂日期。
- 與近期動態共用的繁中服版本事件標記。跨副本或跨職業 rDPS 趨勢只供時間檢視，不代表同一比較母體。
- 同一戰鬥多份上傳的報告分頁；主檔保留代表成績，完整來源變體由 `user-entry-details` 按需載入。

坦克與治療的摘要、歷史表與報告彈窗會切換為對應支援統計。舊資料沒有選填欄位時顯示 `-`，前端不得自行掃描其他排行榜列補算。

### 簡表模式

簡表以繁中服遊戲版本快照顯示零式、絕、極、幻與滅：

- 預設版本為 7.2；未到已公告開放時間的版本會維持待開放。
- 所有絕本與極本固定納入；其他分類依 `current_high_end` 與簡表版本範圍判定。
- 零式列出該版本已開放的量級，預設選最新量級，也能切換舊量級第 1～4 層。
- 每層顯示目前職業範圍最高 PR 與對應職業；只有過版紀錄時顯示灰色勾勾。
- 量級四層都有該版本有效公開通關時，量級按鈕顯示彩色勾勾。
- 7.2 幻本固定同時顯示白虎與朱雀；沒有白虎公開紀錄時仍顯示「尚未收錄」。

「尚未收錄公開通關」只表示本站沒有該角色在目前版本與職業範圍內的公開 FFLogs 成績，不能解讀為玩家未通關。

### 成就徽章與成就手冊

固定成就 ID、判定、分類、排序與進度群組集中在 `src/utils/userProfileBadges.js`；Vue 元件只呈現結果。網站作者是身分標示，不納入成就目錄。

徽章順序固定為：

1. 網站作者識別。
2. 六絕全通。
3. 次重量級。
4. 輕量級。
5. 其他一般成就。

同一零式量級先顯示互斥的四階進度，再顯示可獨立取得的炒股仔。四階依「首週踏破 → 次週踏破 → 踏破 → 通關」只發放命中的最高階：

| 量級 | 首週 | 次週 | 踏破 | 通關 |
| --- | --- | --- | --- | --- |
| 輕量級 | M4S 於 2026-03-17 16:00 前完成 | M4S 於 2026-03-24 16:00 前完成 | M4S 於 2026-06-23 13:00 前完成 | M1S～M4S 皆有有效版本公開成績 |
| 次重量級 | M8S 於 2026-08-11 16:00 前完成 | M8S 於 2026-08-18 16:00 前完成 | 現行依序攻略限制下，M8S 有有效公開通關 | M5S～M8S 皆有有效版本公開成績，且未命中更高階 |

門檻當下列入。實際完成時間以戰鬥紀錄時間加通關時間計算；缺少可解析時間時不猜測限時階級，但四層完整仍可取得通關。次重量級日後解除依序攻略限制時，只能以明確公告切點更新固定規則，不可由副本掃描日期自動推導。

每個量級另有獨立的炒股仔成就：四層各自至少有一筆非過版、`performance.qualified=true` 且本站四捨五入顯示 PR 95 以上的紀錄，各層可以使用不同職業。輕量級使用固定有效版本成績；次重量級會隨現行分位重建。

成就手冊分為絕本、零式、其他三頁，完整目錄有 16 列。進度計算把每個量級的四階視為一項，兩個炒股仔各自獨立，因此總進度共有 10 項。全站獲得人數與百分比由 `scripts/build_user_data.mjs` 以完整角色公開成績建置到 `users/index.json`；分母固定為同一索引的 `total_users`，前端不得掃描所有玩家檔重算。

## 全服統計、比較與分析

### 全服統計

全服統計提供伺服器與職業分布、零式進度、資料狀態、rDPS 分布與副本概覽。副本、伺服器、職業範圍、拆分方式、傷害指標與有效／過版條件都只篩選已建置的靜態切片。

### 玩家比較

玩家比較會載入兩份個人成績單，依指定職能／職業、副本與紀錄時效並排比較。同職分位與代表紀錄沿用個人成績單的排序規則，不重新計算跨職業 PR。

### 隊伍榜

隊伍榜使用同場八名公開玩家資料，顯示最速通關、隊伍 rDPS 與成員組成。同一物理戰鬥依 `fight_hash` 合併多份上傳；版本切片在 Node.js 建置層完成。

### 伺服器對比與職業分析

伺服器對比呈現收錄玩家、副本通關、職能比例、熱門職業與副本落點；職業分析呈現各職能／職業的 rDPS 分位、副本分布、伺服器分布與代表紀錄。兩頁只讀 `server_compare.json` 與 `global_stats.json`。

## 近期動態

近期動態包含最新公開成績、個人最佳刷新、新收錄玩家、伺服器與副本活躍度，以及每日 Logs／通關場次曲線：

- `unique_report_count` 以 report code 去重。
- `unique_fight_count` 以副本 key 與 `fight_hash` 去重，合併同場多份上傳。
- 每日 bucket 使用台灣日期，並預先建置零式、極、幻、滅、絕分類序列。
- 桌面預設近 90 天，手機預設近 30 天，可切換副本、指標與自訂日期。
- 台服與國際服版本事件由 `src/utils/activityTimelineAnnotations.js` 維護，只作圖表脈絡，不參與統計。

## 常見問題與 FFLogs 檢查

常見問題頁會解析 FFLogs report 網址或 code，先比對：

- `public/data/report_status_index.json`
- `public/data/all/report_status_index.json`
- `public/data/update_status.json`

靜態索引只能回答本站是否已收錄、指定 fight 是否命中，以及大致排程時間。完全找不到 report 時，前端不能宣稱 report 是 Private、已刪除、沒有繁中服玩家或沒有通關。

選填的 Apps Script Web App 會以站務端 OAuth 即時查詢單一 report 是否公開可讀。Public 且可讀的 report 可寫入 Google Sheet 待收錄名單；已收錄但明確不可公開讀取的 report 可要求重新檢查可見度。Apps Script 不直接修改排行榜，workflow 仍須完整重掃並由 `fetch_fflogs.py` 決定收錄或 hidden 狀態。

## Honey B. Lovely 粉絲榜

Honey B. Lovely 是與正式排行榜分離的趣味資料：

- 來源固定為 M2S 的 `心醉魂迷：奴役` 衍生紀錄。
- 本期榜單、吃心心數、戰鬥次數、報告與粉絲列紀錄只計近 7 天。
- 最新收錄紀錄最多 5 筆，最新加入粉絲最多 16 筆。
- 歷史資料保留於來源檔，用於歷史統計與連續入榜週數。
- 「超高難度」模式使用自台灣時間 2026-05-30 00:00 起的通關場次，依單場全隊奴役總次數排序。

資料由 `scripts/fetch_honey_b_fans.py` 獨立抓取與建置，不得寫入正式 `data/rankings/` 或個人成績聚合。

## 共用介面與偏好

- 主題：深色／亮色，並依目前職能或職業切換主色。
- 分位顯示：PR 或前 N%，預設 PR。
- 版本紀錄：排行榜與個人成績單共用，預設關閉。
- 說明提示：可顯示或隱藏，預設顯示。
- 玩家搜尋歷程：下拉顯示最近 8 筆，最多保存 100 筆，可個別刪除或全部清除。
- 全域公告：讀取 `data/announcements.json`，關閉狀態以公告穩定 ID 保存在 `localStorage`。
- 分析：只有設定 `VITE_GA_MEASUREMENT_ID` 時載入 GA4；本機開發預設不送事件。

暫時性 UI 開關集中在 `src/utils/siteFeatures.js`。目前作者標示、Telegram、GCD 與 Honey 粉絲榜開啟，一般社群連結關閉；這些旗標只影響呈現，不改變公開資料契約或歷史資料。
