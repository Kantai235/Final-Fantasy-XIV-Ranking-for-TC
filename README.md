# FFXIV 繁中服排行榜

Final Fantasy XIV 繁中服排行榜是一個以 FFLogs 公開資料為來源的 Vue 3 / Vite 靜態網站，用來整理繁中服玩家在零式、極、幻、滅與絕本中的公開通關成績。

專案由兩個主要部分組成：

- 前端網站：瀏覽排行榜、全服統計、個人成績單、玩家比較、隊伍榜、伺服器對比、職業分析、近期動態、常見問題與 Honey B. Lovely 粉絲榜趣味頁。
- 資料管線：透過 FFLogs GraphQL API 抓取報告，篩選繁中服玩家，建置排行榜與前端需要的靜態 JSON。

> 這是非官方社群工具，資料來自 FFLogs 公開報告；顯示結果不代表遊戲內完整人口或所有通關紀錄。

## 快速開始

需求環境：

- Node.js 20+（GitHub Actions 固定使用 Node.js 24）
- Python 3.11+
- FFLogs OAuth Client Credentials

安裝依賴：

```bash
npm install
npm run python:venv
npm run python:install
```

`npm run python:install` 與所有 Python 相關 npm scripts 會優先使用 `.venv/bin/python`，也可用 `FFXIV_TC_PYTHON=/path/to/python3.11` 指定直譯器；專案需求為 `.python-version` 宣告的 Python 3.11+。

設定本機環境變數：

```bash
cp .env.example .env
```

在 `.env` 填入至少一組 FFLogs OAuth 憑證：

```env
FFLOGS_CLIENT_ID=your_client_id
FFLOGS_CLIENT_SECRET=your_client_secret
```

常用驗證指令：

```bash
npm run build:user-data
npm run validate:data
npm run check
```

本機開發伺服器可用：

```bash
npm run dev
```

代理協作者請注意：除非使用者明確要求，請不要自行啟動 Vite 開發伺服器。

## 功能摘要

- 依副本查看排行榜，首頁預設顯示「零式 M7S / 野蠻憎惡」，並支援伺服器、職業類型、職業、關鍵字與排序篩選。設定視窗的「版本紀錄」是個人成績單與排行榜共用的偏好：開啟時排行榜提供繁中服累積版本選單，選擇 7.1 只納入 7.0、7.05 與 7.1 的戰鬥，列表也會顯示每筆紀錄的版本；每筆資料依 `config/game_versions.json` 的繁中服開放時間與 `recorded_at_iso` 歸類。選單預設顯示目前已開放的實際版本（7.2 於 2026-07-28 13:00 開放後自動成為預設）；若所選版本早於副本的 `profile_summary_available_from`，會提示該副本的繁中服開放版本與最低可選版本。關閉時排行榜隱藏版本欄與累積版本選單，若副本有 `version_cutoff` 則改顯示「紀錄時效」的全部／有效／過版篩選。
- 玩家搜尋欄支援本機搜尋歷程，下拉顯示最近 8 筆，編輯視窗最多保存 100 筆。
- 同名角色若分屬不同伺服器，會以「角色名稱 + 伺服器」拆成不同個人成績單；目前不再自動處理轉服合併。
- 排行榜依職能切換欄位：輸出職業顯示 DPS／rDPS／aDPS，坦克顯示承傷、自補、個人／團隊防護與減傷覆蓋，治療職業顯示 HPS、純治療、防護量與 OH%；三者皆保留 Active、GCD、rDPS、通關時間與紀錄時間。百分比以原字級顯示整數與百分號，小數位則略微縮小。治療的純治療／防護量，以及坦克的承傷／自補／個人防護／團隊防護，在一萬以上會以一位小數的 K／M 縮寫，滑鼠移入、鍵盤聚焦或點擊可查看完整整數。一般排行榜分開顯示「玩家名稱」與「伺服器」；只有坦克與治療排行榜合併為「玩家」欄，以「玩家名稱 @ 伺服器」呈現，其中伺服器文字略小。坦克與治療桌機榜維持 16px 正文與頁面內彈性欄寬，不需要橫向捲動；排名徽章限制在排名欄內，玩家名稱不會以省略號截短，極端長名稱則在欄內換行完整顯示。職能榜的排序箭頭固定在作用中按鈕右側，且不占用文字欄寬，因此個人防護、團隊防護、減傷覆蓋與通關時間等表頭在切換排序後仍維持單行。職能／職業篩選另可展開同場另一名同職能玩家，只有資料能唯一辨識雙坦或雙補時才會顯示。同場列不另加職能標記，也不重複顯示相同 fight 的通關時間與紀錄時間。
- 手機版坦克與治療排行榜會把主要統計濃縮在單一數值列；Active、GCD、通關時間、版本、紀錄時間與報告則沿用輸出職業的緊湊資訊列，避免每個狀態都呈現成大型重點卡片。
- 個人成績單可查看各副本最佳紀錄、歷史紀錄、同職分位、常同場隊友與角色累積成就徽章；選定坦克職能／職業時，摘要列、歷史表格與報告彈窗會改顯示 rDPS、承傷、自補、個人防護、團隊防護與減傷覆蓋；選定治療職能／職業時則顯示 rDPS、HPS、純治療、防護量、OH% 與可唯一辨識的同場另一補。支援總量沿用排行榜的一位小數 K／M 縮寫與完整數值提示，舊個人成績資料尚無欄位時顯示 `-`。徽章一律以未套用頁面伺服器／職業篩選的完整公開成績判定。零式量級成就是固定規則，會依量級的末層與樓層攻略限制解除時間判定踏破，再以四層有效版本成績判定通關，詳細條件見下一點；後續量級成就須另行明確定義。六個絕本皆有公開通關紀錄時，會取得具虹彩循環邊框的「&lt;傳奇&gt;&lt;究極&gt;&lt;完美&gt;&lt;蒼天&gt;&lt;元始&gt;&lt;創世&gt;」稱號；此為歷史全通成就，不套用零式量級的有效版本限制。也可在查詢列右側開啟「簡表模式」，以零式、絕、極、幻、滅橫列顯示所有絕本、所有極本與目前高難副本。簡表預設選擇 7.2，也可切換其他繁中服遊戲版本；畫面依各副本設定的簡表版本範圍顯示，並只納入下一版本開放前完成的戰鬥。7.2 的幻本固定同時列出白虎與朱雀，即使玩家沒有白虎公開成績，白虎仍會顯示為「尚未收錄」。已公告的未來版本會在開放時間前維持待開放、時間到達後自動可選。玩家在目前伺服器有多個已收錄職業時，簡表會顯示職能／職業選單，預設為全部職業，並與一般成績單共用目前的職業範圍。零式會列出該版本已開放量級，預設選取最新量級，並可切換查看各量級第 1～4 層。某量級四層皆有該版本與職業範圍內的有效通關時，該量級按鈕會亮起彩色勾勾；量級內各樓層仍顯示有效紀錄的職業與目前職業範圍最高 PR，只有過版紀錄則顯示灰色勾勾。「尚未收錄」不代表玩家未通關。同職分位預設顯示整數 PR 值，也可由使用者端偏好切換為「前 N%」，PR 模式會讓代表列、分位亮點與歷史列優先依 PR 值排序。設定視窗的共用「版本紀錄」偏好預設關閉；開啟後會在分位亮點與歷史紀錄標示通關當時的版本。歷史表格可直接點擊紀錄時間、同職分位、Active、GCD、目前職能對應的輸出／支援統計、版本或通關時間欄位排序；再點一次會反轉方向，手機則提供對應的排序選單與方向按鈕。
- 零式量級成就依「首週踏破 → 次週踏破 → 踏破 → 通關」判定，同量級只顯示命中的最高階一枚。輕量級只看 M4S 判定前三階：繁中服時間 2026-03-17 16:00（含門檻當下）前完成為金色「輕量級【首週】踏破」，2026-03-24 16:00 前完成為銀色「輕量級【次週】踏破」，2026-06-23 13:00 前完成為銅色「輕量級踏破」；前三階皆未命中、但 M1S～M4S 四層皆有有效版本公開成績時，取得無特效的「輕量級通關」。次重量級同樣只看 M8S 判定首週與次週：2026-08-11 16:00 前完成為金色「次重量級【首週】踏破」，2026-08-18 16:00 前完成為銀色「次重量級【次週】踏破」；目前尚未解除依序攻略樓層的限制，因此只要有 M8S 有效公開通關即可取得銅色「次重量級踏破」，M5S～M8S 四層完整的無特效「次重量級通關」只會在較高階踏破未命中時發放。所有時間門檻均以 FFLogs 戰鬥開始時間加上通關時間計算；缺少必要時間時不會猜測首週、次週或輕量級踏破，但四層完整仍可取得通關。次重量級已預留解除時間設定，未來填入公告切點後，切點後的 M8S 不再取得踏破，四層完整者則取得通關。顯示順序固定為網站作者識別、六絕全通稱號、次重量級、輕量級，再接續其他一般成就；非作者角色則從六絕全通開始。
- 個人成績單載入角色後，右下角會顯示書本造型的「成就手冊」入口；手冊以「絕本」、「零式」、「其他」三個分頁顯示全站獲得人數與占收錄玩家比例，彈窗外框維持固定高度，僅成就內容區捲動。零式分頁會依輕量級、次重量級完整列出「首週踏破 → 次週踏破 → 踏破 → 通關」四階統計；四階仍互斥，玩家只會取得最高階一枚，其他列標示為「其他階段」。四階皆未取得時，依繁中服目前時間把仍可取得的最高階標為「目前目標」，截止當下仍列入。完整目錄共有十四列，但總進度將每個零式量級視為一項，因此仍是八項可取得成就；「網站作者」屬於身分標示，不納入成就總數或獲得率。
- 開啟版本紀錄後，一般成績單查詢列會新增「版本」選單；選項依目前伺服器已收錄的版本產生，並與職業篩選交集。選擇版本時會顯示截至該版本的累積歷史資料，例如選擇 7.1 會包含 7.0、7.05 與 7.1；最新版本即代表完整成績單，因此不另設「全部版本」。
- 個人成績趨勢以一張時間軸整合所有公開紀錄，並沿用排行榜的雙欄分組選單篩選副本、職能與職業；另可切換 PR 值／rDPS，以及近 7／14／30／90 天、全部資料或自訂日期，預設為全部副本、全部職業、近 30 天與 PR 值。滑鼠懸停、鍵盤聚焦或點擊標點時會顯示該筆副本、職業、PR、rDPS 與紀錄時間。圖表固定沿用近期動態 Logs 趨勢的版本事件，只標示繁中服更新，並以「7.11 絕伊甸」等省略地區前綴的文字顯示版本與開放內容。
- 玩家比較、隊伍榜、伺服器對比、職業分析與近期動態皆由靜態資料產生；隊伍榜預設顯示「零式 M7S / 野蠻憎惡」。近期動態也提供每日 Logs 曲線、零式、極、幻、滅、絕分類占比，以及台服與國際服改版時間標註，桌面預設近 90 天、手機預設近 30 天，可切換副本、日期範圍與 Logs、通關場次等統計口徑。
- 常見問題頁整理 Telegram 群組常見回報，包含更新時間、職業 Rank／同職分位、跨職業比較、過版紀錄、GCD 覆蓋率、同名角色與公開狀態；其中的 FFLogs 檢查工具可貼上 report 網址或 report code，比對 `public/data/report_status_index.json` 與 `public/data/update_status.json`，判斷目前公開資料是否已收錄、指定 fight 是否命中，以及剛上傳或歷史補查紀錄大約會落在哪個排程窗；「查詢公開狀態」按鈕會透過 Apps Script Web App 確認 FFLogs API 目前是否可讀。Public 且可讀的 report 可寫入 Google Sheet 待收錄名單；若本站已收錄、但 FFLogs 明確不可公開讀取，則可要求重新確認公開狀態，下一輪 workflow 會重新排查，確認仍不可讀時把既有紀錄標記 hidden。待處理名單只保存 report code，不保留指定 fight。
- Honey B. Lovely 粉絲榜以獨立趣味資料呈現 M2S `心醉魂迷：奴役` 衍生紀錄；本期榜單、吃心心數、戰鬥次數與報告只計近 7 天，最新收錄紀錄顯示 5 筆、最新加入粉絲顯示 16 筆。頁面可用「超高難度」開關切換為自台灣時間 2026-05-30 00:00:00 起算的通關團隊榜，依單場全隊奴役總次數排序，來源歷史紀錄仍保留用於連續入榜與追溯統計，不混入正式排行榜。
- 支援深色 / 亮色主題，並依目前頁面的職業或職能篩選切換主色調。
- 設定視窗可依個人偏好顯示或隱藏各頁的說明提示按鈕，預設為顯示。
- 支援全域公告通知，公告內容由 `public/data/announcements.json` 隨 commit 更新，使用者關閉後不再主動顯示。
- GitHub Actions 可定時抓取 FFLogs 與 Honey B. Lovely 粉絲榜、建置資料並部署 GitHub Pages，也提供不抓 FFLogs 的手動緊急部署通道。

## 文件地圖

README 只保留入口與最小操作脈絡，完整說明請依主題閱讀：

| 文件 | 內容 |
| --- | --- |
| [docs/README.md](docs/README.md) | 文件索引與閱讀順序。 |
| [docs/getting-started.md](docs/getting-started.md) | 安裝、環境變數、常用指令與本機驗證。 |
| [docs/architecture.md](docs/architecture.md) | 專案結構、三層責任邊界與前端頁面脈絡。 |
| [docs/data-pipeline.md](docs/data-pipeline.md) | FFLogs 抓取、資料建置、GCD 覆蓋率、手動補抓與維護流程。 |
| [docs/data-contracts.md](docs/data-contracts.md) | JSON 資料契約、去重規則、hidden report、版本切點與 append-only 原則。 |
| [docs/routing-and-seo.md](docs/routing-and-seo.md) | 分享網址、乾淨路徑、SEO/OG 靜態頁與社群預覽圖。 |
| [docs/deployment.md](docs/deployment.md) | GitHub Actions、GitHub Pages、部署需求與 Cloudflare 串接摘要。 |
| [docs/cloudflare-github-pages.md](docs/cloudflare-github-pages.md) | Cloudflare CDN、Cache Rules、Rate Limiting 與 purge 細節。 |
| [apps-script/fflogs-report-status/README.md](apps-script/fflogs-report-status/README.md) | FFLogs report 即時可讀狀態查詢用 Apps Script Web App 範本。 |
| [config/README.md](config/README.md) | `config/` 設定檔欄位判讀。 |
| [Data repo 的 data/rankings/README.md](https://github.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Data/blob/main/data/rankings/README.md) | 排行榜完整資料格式與分片說明。 |

## 核心架構

本專案最重要的邊界是「抓取、建置、呈現」三層分離：

1. `scripts/fetch_fflogs.py` 是 Data Fetching Layer。它是唯一可直接呼叫 FFLogs GraphQL API 的入口，負責 OAuth、限流、重試、繁中服玩家初篩、report 狀態判定，以及 `data/rankings/` 與 `data/state.json` 的可追溯寫入；GraphQL 查詢字串集中在 `scripts/fflogs_pipeline/graphql_queries.py`，避免掃描策略與查詢文本互相纏在同一個巨型檔。新收錄 fight 會保存補師 Healing table 摘要，以及坦克承傷、實際護盾吸收與有效減傷時窗摘要；DamageTaken／Buffs／Debuffs raw events 完整分頁後立即丟棄，不會寫入 Git。7/28 後新收錄的 fight 也會在 `fetch_fflogs.py` 建立排行來源前即時完成普攻資料完整性檢核；既有副本先以切點前的全隊角色傷害 P99 本地預篩，只有超出高端、Attack 標記或新副本才讀取敵方生命池。`scripts/backfill_fight_integrity.py` 則只負責既有歷史資料的分批回補。兩者共用不進 Git 的最小測量快取，只在 fight 層寫入 `data_integrity` 標記，不會刪除原始 report。
2. `scripts/build_user_data.mjs` 是 Data Building Layer。它讀取排行榜來源資料，產生個人成績單、個人成績報告細節、全服統計、近期動態、隊伍榜與伺服器對比等 `public/data/` 靜態 JSON；`build:user-data` 也會接續產生排行榜薄索引、Logs 狀態索引與公開更新狀態。正式部署時，個別玩家成績單 JSON 會先同步到專用 users repo，再從主站 Pages artifact 移除；高頻共用的 `data/users/index.json` 會保留在主站 `/data/`，讓 Cloudflare/GitHub Pages 快取承接玩家搜尋索引請求。
3. `src/` 是 UI Presentation Layer。Vue 只讀取靜態 JSON 進行呈現、篩選與狀態管理：主站共用資料與個人成績單索引來自 Pages artifact 的 `/data/`，個別玩家成績單資料來自專用 users repo，不能直接呼叫 FFLogs API；`src/composables/rankingApp/` 承接排行榜預設值、注入 context 與排行列正規化，`src/styles/app.css` 則只作為樣式拆檔入口。

權威來源資料存放於 `Final-Fantasy-XIV-Ranking-for-TC-Data`。主 repo 只追蹤程式碼與設定；本機或 workflow 必須先執行 `npm run data:hydrate` 還原經 manifest 驗證的最新資料，再進行抓取、建置或部署。Data repo 每次更新都以沒有 parent 的 root commit 取代 `main`，避免高頻 JSON 版本持續累積歷史容量；append-only report、fight、player 與 checkpoint 則由發布工具逐輪守恆檢查。同步期間會顯示下載、展開、檔案驗證與本機比對進度，長步驟也會定期回報已等待時間；舊版 `blob:none` 快取會在下載階段自動補齊，不再等到展開時才隱性抓取缺少物件。

## 常用指令

| 指令 | 用途 |
| --- | --- |
| `npm run build:public-rankings` | 只重建公開排行榜與副本清單，不呼叫 FFLogs API。 |
| `npm run backfill:support` | 由本機完整回補 2026-07-28 13:00 至執行開始時間缺少的補師治療與坦克承傷／防護／有效減傷摘要；可安全重跑並分批寫入。 |
| `npm run backfill:support:history` | 模擬 workflow 從 2026-07-28 13:00 往舊回補 25 份 report，游標保存於 `data/state.json`。 |
| `npm run check:report-status -- <report code>` | 只查既有 report 目前是否仍可公開讀取；Private、刪除或無權限時將來源標記為 hidden，不推進掃描點。 |
| `npm run backfill:fight-integrity` | 分批檢核台灣時間 2026-07-28 18:00 後的 fight：全隊敵方承傷／敵方最大生命池嚴格超過 1.15 倍時標記 `excluded`；介於 1.14 至 1.15 倍、或 FFLogs `Attack` 異常標記時標記 `suspected`。極澤蓮尼亞與幻朱雀分別要求完整隊伍角色傷害或 FFLogs Target Damage 落在 `92,086,132–92,086,332`、`71,280,000–72,720,000`；玩家合計高於上限可直接隱藏，低於下限時因可能漏掉 Limit Break，必須改查 Target Damage 後才能決定。絕伊甸、絕巴哈姆特與 M1／M3／M4 則採用只攔截超高傷害的硬上限。所有措施都只從公開衍生資料隱藏，原始 report/fight 保留。敵方承傷與生命池會保存於不進 Git 的最小快取，重跑時不會重複耗用 API；`--offline-only` 完全不會呼叫 FFLogs，無法離線確認者會保守隱藏。 |
| `npm run fetch:honey-fans` | 抓取 Honey B. Lovely 粉絲榜趣味資料，會呼叫 FFLogs API。 |
| `npm run build:honey-fans` | 由 `data/fun/honey_b_fans.json` 重建公開趣味榜 JSON，不呼叫 FFLogs API。 |
| `npm run build:ranking-tables` | 由公開排行榜產生前端薄索引與按需載入報告細節檔；會依 `config/game_versions.json` 在薄索引列寫入 `game_version`，並加入坦克／治療職業的支援統計摘要。只有同場恰好兩名同職能玩家時才會建立雙坦／雙補搭檔，避免聯盟副本缺少小隊資訊時誤配。 |
| `npm run build:report-status` | 由排行榜報告細節檔產生 `public/data/report_status_index.json` 與 hidden delta report 索引，供常見問題頁中的 FFLogs 檢查工具快速比對。 |
| `npm run build:public-status` | 由 `data/update_status.json` 與 `public/data/global_stats.json` 產生 `public/data/update_status.json`，公開最近資料更新與排程摘要。 |
| `npm run build:user-data` | 建置個人成績單、個人成績報告細節、全服統計、近期動態、隊伍榜、伺服器對比、排行榜薄索引、Logs 狀態索引與公開更新狀態。 |
| `npm run read:fflogs-refresh-queue` | 讀取 Google Sheet 待收錄名單，輸出本輪會送入 `FFLOGS_RETRY_REPORT_CODES` 的 report code。 |
| `npm run complete:fflogs-refresh-queue` | 依公開與 hidden 狀態索引、排行榜來源與 report 分片更新 Google Sheet 待處理列：已收錄為 `done`，已確認隱藏為 `hidden`，來源已保存但所有 fight 都被完整性規則隱藏時為 `review_required_data_integrity`，無通關或無繁中服玩家則寫入終止狀態與原因；也會校正待處理欄位標題與純數字的錯置訊息。 |
| `npm run validate:data` | 驗證公開資料、schema 契約、分片、全服統計、使用者索引與 Honey B. Lovely 粉絲榜完整性。 |
| `npm run compact:state` | 壓縮 state 主檔與各副本 `checked_reports` 分片中的重複 checkpoint、可重建時間鏡像與 JSON 空白；保留完整快取並檢查每個 Git blob 體積。 |
| `npm run audit:gcd:xivanalysis` | 以固定 seed 對零式、極、幻的每個副本各抽樣 10 場，若 10 場未涵蓋全職業會自動補抽缺漏職業所在戰鬥，並將本地 GCD 覆蓋率與 xivanalysis 畫面值比對；100 場外站頁面稽核使用 `--sample-size 100 --local-mode stored --tolerance 0`，必要時可搭配 `--workers`、`--exclude-report-codes` 與 `--apply-all-checked`。 |
| `npm run test:data-conservation` | 檢查排行榜薄索引、細節檔、使用者檔與 hidden delta 的資料守恆。 |
| `npm run test:sync-user-repo` | 以本機 bare repo 驗證 users 專用 repo 的空白初始化、單一快照更新、歷史收斂與無變更略過。 |
| `npm run data:hydrate` | 從 Data repo 驗證並還原權威 `data/` 與主站共用 `public/data/` 快照。 |
| `npm run data:publish` | 驗證 append-only 歷史、建立單一 root snapshot，並以 `force-with-lease` 發布到 Data repo。 |
| `npm run data:verify` | 驗證 Data repo 的單一 root commit、manifest、檔案大小與 SHA-256。 |
| `npm run data:repair-eol` | 人工修復 Git 將 CRLF 錯誤正規化為 LF 造成的 Data snapshot；只有本機原始檔或換行還原結果的大小與 SHA-256 完全符合 manifest 才會推送。 |
| `npm run test:data-repository` | 以本機 bare repo 驗證 Data repo 空白初始化、單一快照、排除規則、hydrate 與守恆阻擋。 |
| `npm run audit:pages-payload` | 以 baseline 模式稽核 `dist/` 與 GitHub Pages payload 體積，只在超過硬上限時失敗，可用 `-- --write-history <path>` 記錄趨勢。 |
| `npm run audit:pages-payload:strict` | 以與 GitHub Actions 相同的 strict 模式稽核 payload，任一項超過 target 就失敗；workflow 會寫入 `data/pages_payload_history.jsonl`。 |
| `npm run audit:mixed-report-dispatch` | 統計 mixed report 分派版本在已知歷史 report 的覆蓋率與歷史補查游標進度；GitHub Actions 會輸出到 Step Summary。 |
| `npm run prune:pages-user-data` | 從 `dist/` 移除個別玩家成績單 JSON、逐玩家靜態分享頁與玩家 OG 圖，保留 `data/users/index.json` 以模擬正式 Pages artifact。 |
| `npm run check` | 執行 Python 與 Node.js 語法檢查。 |
| `npm test` | 執行資料管線、GCD、資料建置與前端資料契約測試。 |
| `npm run build` | 完整建置靜態網站到 `dist/`。 |
| `npm run sync:data -- --dry-run` | 比對本機受管理資料與 Data repo 快照，不寫入檔案；本機有未發布差異時會停止。 |
| `npm run python -- --version` | 顯示 npm scripts 解析到的 Python 直譯器版本。 |
| `npm run python:venv` | 使用可用的 Python 3.11+ 建立 `.venv`。 |
| `npm run python:install` | 用專案 Python 直譯器安裝 `requirements.txt`。 |

更多指令情境請看 [docs/getting-started.md](docs/getting-started.md) 與 [docs/data-pipeline.md](docs/data-pipeline.md)。

## 維護原則

- `config/encounters.json` 的 `key`、`data/state.json` 的 report 狀態與 `data/rankings/` 歷史資料都是 append-only 資產，不可任意改名、硬刪或覆寫。
- `.env` 內的 FFLogs 與 Cloudflare 憑證是敏感資訊，不應提交到版本控制，也不要印到 Log。
- 若新增前端畫面需要新的統計欄位，請先擴充資料建置層，再讓 Vue 讀取新的靜態 JSON。
- 成就規則與固定 ID 集中於 `src/utils/userProfileBadges.js`；`scripts/build_user_data.mjs` 依完整角色成績與建置中的完整同場玩家集合聚合獲得人數，將成就目錄及 `holder_count`／`holder_percentage` 寫入 `public/data/users/index.json`。占比分母固定使用同一索引的 `total_users`，前端不得重新掃描所有玩家檔案計算。
- Honey B. Lovely 粉絲榜來源在 `data/fun/honey_b_fans.json`，公開輸出在 `public/data/fun/honey_b_fans.json`；它是獨立趣味資料，不屬於正式 `data/rankings/` schema。公開榜單、粉絲報告與本期 `records` 只計近 7 天，歷史紀錄仍留在來源檔並輸出 `historical_*`、連續入榜週數與自台灣時間 2026-05-30 00:00:00 起算的活動 `team_rankings`；正式 workflow 會執行 `npm run fetch:honey-fans` 抓新資料，再用 `npm run build:honey-fans` 整理公開 JSON。
- `data/state.json` 保存掃描游標與執行狀態；跨輪 `checked_reports` 依副本緊湊保存於 `data/state/checked_reports/{encounter key}.json`。讀取資料管線時會自動還原既有 state 結構，避免為了通過 GitHub 100 MiB 單檔限制而刪除略過依據；正式 workflow 會在 Data snapshot 發布前執行 `npm run compact:state -- --max-bytes 104857600`，確認主檔與每個分片都符合限制。`processed_at_iso` 不再作為 report checkpoint 必要欄位，因為它可由 `processed_at` 毫秒時間重建。
- 既有 report 的公開狀態巡檢以 report code 為單位：尚未巡檢時優先選較新的 report，之後依來源分片保存的 `report_status_checked_at` 輪替。FFLogs 回傳 `visibility=Private`、report 不存在或封存不可讀時，來源 report 會標記 hidden，正常公開產物不再列出該紀錄；完整追溯則保留於 hidden delta。
- GitHub Actions 的 FFLogs 排行榜抓取步驟預設設定 `FFLOGS_MAX_RUNTIME_SECONDS=6000` 與 `FFLOGS_RUNTIME_GRACE_SECONDS=900`，可由 repo variables 覆寫。這讓 FFLogs 憑證全數進入長冷卻時，`fetch_fflogs.py` 能先保留 `active_scan` 續跑位置並正常進入後續資料建置與 commit，避免 GitHub-hosted runner 直接取消整個 job。
- GitHub Actions 會先用 `FFLOGS_RECENT_GCD_BACKFILL_REPORT_LIMIT` 控制的非 stateful GCD 補洞追最新候選，再用 `FFLOGS_GCD_BACKFILL_REPORT_LIMIT` 控制的 stateful 回補從固定 cutoff 往舊追；前者處理 cutoff 後空洞，後者處理歷史追平。
- GitHub Actions 的 `fetch_fflogs.py` 會在每筆新收錄的 7/28 後 fight 寫入排行來源前立即執行戰鬥完整性檢核；`config/fight_integrity_baselines.json` 以切點前、完整繁中隊伍且依 `fight_hash` 去重的 P99 傷害建立舊副本本地預篩，避免正常場次反覆查 API。預篩超標不是排除證據，仍須以生命池量測確認；僅在高端候選無法量測時保守隱藏為疑似。`FFLOGS_FIGHT_INTEGRITY_REPORT_LIMIT`（預設 25）只限制既有歷史資料的回補批次。可用 `FFLOGS_FIGHT_INTEGRITY_ENABLED=false` 停止新增檢核。兩個流程共用 Actions cache 接續 `data/local-cache/fight-integrity/measurements.json` 的最小測量資料；該資料只含彙總敵方承傷、生命池、目標數、需要固定 profile 時的 NPC GUID／逐目標承傷／最大生命值／實例數，以及匿名化玩家普攻彙總，不會進 Git。既有 `data_integrity.metrics` 也會直接植入快取，不會為了補快取重讀 API。規則重跑優先離線復查，僅在 report／fight 來源指紋變動或明確使用 `--refresh-cache` 時重新讀取 FFLogs。這是可撤除的暫時性防護：停用後既有 `data_integrity.hidden_from_public=true` 仍會從排行榜、個人成績、隊伍榜與近期動態隱藏，原始 report/fight 不會被移除。
- 完整性 v10 對 M5S～M8S 的標準 8 人、無超越力通關查詢 ability 7 的完整事件頁。只採 `type=damage`，一般普攻限定 `hitType=1` 且非直擊，並以 `amount / multiplier` 還原團輔前每擊基準。物理職業至少要有 60 筆普攻、30 筆純一般普攻才列入樣本；單人必須同時達到每擊中位數 `max(10,000, 參考值×2)` 與普攻傷害占比 `max(15%, 參考值×1.5)` 才算異常。至少 3 人且占合格樣本 60%，或 2 名物理職業加上異常非物理職業，標為 `suspected`；至少 4 人、占 75%，且異常組每擊中位數至少 15,000、占比中位數至少 20%，標為 `excluded`。判定需同時符合「每擊傷害」與「傷害占比」，不能用單一尖峰或單一玩家排除整場。
- 完整性 v11 對 M5S～M8S 再加入副本固定敵方有效承傷範圍與逐 NPC GUID profile。每個目標都必須同時符合已確認的最大生命值、等效承傷實例數與轉場比例，不能只用 FFLogs `enemyNPCs.instanceCount` 或所有敵人的最大生命值總和推估。M5S、M6S、M7S、M8S 的固定總承傷範圍依序為 `105,549,582–105,549,782`、`130,231,946–130,232,146`、`121,558,848–121,559,048`、`148,748,991–148,749,191`；M8S 兩隻狼各以最大生命值的 40% 作為轉場有效承傷。總量落在範圍內但逐目標傷害被轉移的紀錄仍會標為 `suspected` 並隱藏。
- 完整性 v13 將幻朱雀的副本／職業普攻基準擴充至全部 21 個戰鬥職業：多數職業查 ability 7（Attack），吟遊詩人與機工士另以 ability 8（Shot）補齊遠程自動攻擊。每個職業都有人工抽樣的正常每擊中位數、普攻占比與普攻每秒傷害基準；同一名玩家必須同時跨過三項門檻才標為 `suspected`。物理職業預設採參考值的 `2×／1.5×／1.5×`，法系／治療職則另設至少每擊 `1,000`、占比 `2%`、每秒傷害 `100` 的絕對下限，避免 FFLogs 正常的 1 點 Attack packet 被雜訊放大。這能攔截只影響紅魔、白魔或少數近戰、但全隊傷害仍落在幻朱雀 72m 範圍內的變體；也避免把單次普攻偏高、但每秒貢獻仍在職業正常範圍內的舞者等紀錄誤判。玩家證據只保存 ability ID、source ID、職業與匿名化彙總，不保存 raw events，也不依角色名稱硬編碼。
- 完整性結論屬於實際戰鬥而非單一 report。同一場若有多份上傳，只要任一來源已明確標為 `excluded`／`suspected`，相同 `fight_hash` 的所有變體都必須從排行榜、個人成績、隊伍榜與近期動態排除；`unverifiable` 不可跨 report 傳播，以免暫時性查詢失敗壓過另一份已驗證正常的來源。
- `config/fight_integrity_baselines.json` 為具足夠歷史樣本的副本保存完整繁中隊伍傷害上緣。低於保守上緣的完整隊伍可離線通過初篩；超出上緣、出現 Attack 標記或缺少完整隊伍時，仍以敵方生命池檢核。若超出上緣但無法取得生命池，該 fight 會標為 `suspected` 並從公開資料隱藏。
- `config/fight_integrity_known_enemy_hp.json` 是更嚴格、可獨立撤除的固定規則。極澤蓮尼亞要求完整隊伍 `players[].total_damage` 加總落於 `92,086,132–92,086,332`；幻朱雀依站務暫時性收錄決定，要求落於 `71,280,000–72,720,000`（72m ±1%）。玩家合計落在範圍內且沒有 `Attack` 標記可離線判為有效；高於上限時因玩家合計是傷害下限，可直接標為異常。低於下限或玩家列未完整涵蓋隊伍時，兩者必須改以已快取或新查得的 FFLogs Target Damage 比較同一範圍，避免未歸屬玩家的 Limit Break 造成正常紀錄被誤判。幻朱雀仍保留固定生命池 `127,613,543` 作為可追溯量測資訊，但固定範圍優先於下限倍率判定。絕伊甸、絕巴哈姆特、M1、M3、M4 的完整隊伍總傷害若分別超過 `151,500,000`、`13,230,230`、`75,870,000`、`96,523,000`、`114,526,000`，則直接標示為 `suspected` 並隱藏；它們都是只攔截高傷害的獨立上限，不能把未超過上限的紀錄判為正常。這也確保絕巴哈姆特不會因多階段生命池的 `not_applicable` 例外而放行 243m 類異常。切點後沒有完整性結果、`unverifiable` 或其他非 `valid`／`not_applicable` 的 fight 一律不進公開衍生資料，避免尚未檢核的異常成績混入榜單。
- 截至 2026-08-06，20 個副本自 `2026-07-28T18:00:00+08:00` 起的 11,142 場既有 fight 已全數完成 v10 重驗。v11 只強制 M5S～M8S 缺少逐目標 profile 的場次補查；v13 則依幻朱雀的跨職業 reference version 與 ability 7／8 清單，挑出缺少現行證據的場次。其他副本已公開的 v8～v12 `valid`／`not_applicable` 結果維持相容，不會因全域版號升級整批下架。後續若同步進缺少對應子規則證據的舊場次，仍會逐批補查。舊版失敗結果、缺少結果、早於 v8 或未知版本仍採 fail-closed。現行版本若因執行期例外寫成 `integrity_measurement_failed`，後續批次會自動重試；可重現的缺少生命池或 NPC GUID 則不會每輪重查。人工使用 `--force` 時仍可全量稽核，`--report-code` 可重複指定報告進行定向複查；`--encounter-key` 與 `--recorded-at-or-after` 可將範圍限定為指定副本與含時區的 fight 紀錄時間。FFLogs 若回傳空的 report 節點會視為來源已無法讀取並標記 hidden，但暫時性 HTTP／連線錯誤不會誤判為永久隱藏。workflow 推送前也會比對起始規則指紋，若執行期間規則已更新就拒絕將舊 runner 的結果回寫。
- 極澤蓮尼亞與幻朱雀除了完整繁中隊伍的角色傷害固定範圍外，若玩家來源列不完整或玩家合計低於下限，會分別改以已保存或查得的 FFLogs 敵方承傷檢查 `92,086,132–92,086,332` 與 `71,280,000–72,720,000`；前者避免 93.63m 或 80.96m 類資料因缺少一名玩家列而略過規則，後者避免 Limit Break 未歸屬玩家列時誤殺正常通關。
- 絕伊甸的 `151,500,000` 單向上限同時檢查完整隊伍角色傷害與已量測的 FFLogs 敵方承傷。後者補足 Limit Break 等未歸屬玩家列來源，能隱藏「角色合計未超標、但實際敵方承傷超標」的 rDPS 異常戰鬥；未超過上限不能據此視為正常。
- GitHub Actions checkout 只抓主 repo 目前程式碼 commit，再由 Data repo 單一快照還原權威資料；正式更新與緊急部署都不應改回 `fetch-depth: 0`，避免重新下載遷移前的巨型資料歷史。
- GitHub Actions 以 Node.js 24 執行前端與資料建置，官方 actions 也需使用支援 Node 24 的 major 版本；Pages 部署若遇到 `syncing_files` 後的暫時性失敗，workflow 會等待 60 秒後重試一次。
- 正式 Pages artifact 只保留 `dist/data/users/index.json`，不保留個別玩家成績單 JSON、`dist/data/user-entry-details`、hidden 使用者差量 JSON、逐玩家靜態分享頁與 `dist/og/users` 玩家 OG 圖；前端仍由 `/user` route 與 users 專用 repo 讀取個別玩家成績單。這是為了讓高頻搜尋索引吃到主站 CDN 快取，同時避免 GitHub Pages 在 `syncing_files` 階段同步上萬個小檔時失敗。
- users 專用 repo 只保存可由主 repo 重新建置的最新部署快照，不保存每輪 JSON 版本歷史。`scripts/sync_user_leaderboard_repo.mjs` 每次有內容變更時建立無 parent 的 root commit，再以 `force-with-lease` 確認遠端仍是本輪抓到的 SHA 後更新 `main`；既有累積式歷史即使資料未變也會收斂一次。若 GitHub 已回報 `Repository is above its size quota`，須先請 GitHub Support 協助解除配額鎖定並在快照 force push 後清除舊物件，或在確認資料可重建後重新建立同名空白 repo，再重跑 workflow；同步腳本支援空白 repo 初始化。
- Data repo 只保存 `data/`、`public/data/` 根層共用 JSON 與 `public/data/fun/`；可重建的排行榜薄索引、hidden delta、個別玩家檔與報告明細不重複保存。每次發布先驗證舊快照 manifest，再確認既有 report、`fight_id`、玩家身分與 checked-report checkpoint 沒有遺失，最後以明確舊 SHA 的 `force-with-lease` 更新單一 root commit。
- workflow 在抓取前必須先 `data:hydrate`，完成資料建置與 state 壓縮後先 `data:publish` 保存 FFLogs 成果；Pages payload 稽核寫入趨勢後再發布一次同一類快照。主 repo 在該輪出現新 commit 時，舊 runner 必須停止，不得發布用舊程式碼產生的資料。
- 本機工作開始前先跑 `npm run sync:data -- --dry-run`。若本機已有不同資料，hydrate 會停止而不覆寫；請先暫停 workflow、備份或發布本機成果，再從最新 Data snapshot 開始下一輪，不能用 `--force` 掩蓋未知差異。
- 文件、公告、文案或不影響資料產物的靜態設定變更，只需做相符的語法／格式檢查與 `git diff` 檢視；只有影響使用者資料、前端資料契約或資料建置輸出時，才執行對應的資料建置與驗證。
