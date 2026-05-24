# 資料契約與歷史資料保護

本文件記錄資料檔的判讀方式與不可破壞的歷史契約。更細的排行榜分片格式請看 [../data/rankings/README.md](../data/rankings/README.md)。

## Append-Only 保護原則

以下資料是不可逆的重要歷史資產：

- `config/encounters.json` 的 encounter key。
- `data/state.json` 的 report 狀態與掃描游標。
- `data/rankings/*.json` 與 `data/rankings/*.reports/*.json` 的 report/fight/player 來源脈絡。

禁止用硬刪、覆寫或改名的方式整理這些資料。若需要同步本機與 GitHub Actions 產物，先執行：

```bash
npm run sync:data -- --dry-run
```

看到 `REMOVAL` 或 `CONFLICT` 時不可自動套用。

## 副本清單

`config/encounters.json` 的欄位：

- `key`：內部識別碼，也會對應資料檔名與網址狀態。建立後不得任意改名。
- `name`：網站顯示名稱。
- `category`：副本分類，例如 `零式`、`極`、`幻`、`絕`。
- `zone_id`、`encounter_id`、`difficulty`：FFLogs 查詢用設定。
- `enabled`：是否啟用下一輪 Python 爬蟲掃描。
- `scan_start_date`：首次掃描起始日期。
- `version_cutoff`：版本切點，代表該副本有效版本紀錄的結束時間。

`enabled` 只控制下一輪 Python 爬蟲是否掃描該副本，不代表前端是否顯示。前端選單來源是 `public/data/encounters.json`；只要副本已有 `data/rankings/` 或 `public/data/rankings/` 歷史資料，即使 `enabled=false`，仍應保留在公開清單中，避免既有排行榜與個人成績單消失。

## 排行榜來源資料

`data/rankings/*.json` 主檔保留：

- `schema_version`
- `encounter`
- `ranking_entries`
- `updated_at_iso`
- `report_shards`

完整 report/fight/player 脈絡保存在同名 `*.reports/*.json` 分片中。當分片存在時，`ranking_entries` 只視為衍生索引；重建排行榜必須以 `reports -> fights -> players` 為權威來源，避免重抓單一 report 後舊扁平索引把錯誤高分帶回來。

新寫入的 report 不保存 `fflogs_raw`、`master_data` 與 `matched_players`。這些大型 raw 欄位可依 report code 重查，停止落地是為避免 Git repo 容量快速膨脹。

## 去重與排名規則

同一角色、同一伺服器、同一職業的最佳成績排序規則：

1. rDPS 較高者優先。
2. rDPS 平手時，通關時間較短者優先。
3. 仍平手時，aDPS 較高者優先。
4. 最後才用紀錄時間或名稱做穩定排序。

`fight_hash` 用於辨識不同 report 上傳的同一場戰鬥；`source_reports` 與 `duplicate_count` 必須保留，不能因去重而刪掉來源線索。

個人成績單會用 `fight_hash + 角色 + 伺服器 + 職業` 合併同一場戰鬥的多份上傳。合併列保留代表成績，並輸出 `report_variants` 與 `source_reports`，讓前端報告彈窗可分頁切換不同 report 來源。

個人成績單未套用職業篩選時，副本代表列與分享用代表職業優先選同職 `job_rank` 最前面的有效紀錄；`summary.best_rdps` 仍保留最高 rDPS，避免把「代表職業」與「最高輸出」混成同一件事。

若同名角色有跨伺服器的公開紀錄，公開排行榜、`public/data/users/*.json`、`public/data/users/index.json`、近期動態、隊伍榜與伺服器對比等公開衍生資料，都會以該角色最新公開紀錄所在伺服器作為 `canonical_server`。這些資料的 `servers` 只保留 canonical 伺服器，舊伺服器改寫到 `server_aliases`；若某筆歷史紀錄原本來自舊伺服器，條目會另外保留 `original_server` 供追溯。這樣可避免轉服前後被誤判成兩位玩家，同時保留舊連結與人工查核所需的線索。

## FFLogs 欄位解析

淺層 reports 查詢目前不能直接用伺服器過濾；`report_region_scope` 只控制候選 report 的地區範圍。專案與 GitHub Actions 預設使用 `all` 掃全部地區，以涵蓋繁中服玩家上傳到其他地區的紀錄。無論候選來自哪個地區，都必須再查 `masterData.actors(type: "Player")` 確認是否包含繁中服伺服器。

玩家身分以 `playerDetails` 為主，因為它能排除 Boss、LimitBreak、Pet，並提供角色、伺服器與職業；`damageDone.entries` 只作為輸出數值來源。

`id` / `guid` 優先於角色名稱；只有在同一 report 的名稱唯一時才用名稱 fallback，避免跨伺服器同名角色被合併。

`damage_time_ms` 優先來自 FFLogs damageDone table 的 `combatTime - damageDowntime`。沒有該表格時才退回 fight combatTime，避免 rDPS/aDPS 分母被誤判。

單場 `playerDetails` 與 `damageDone` GraphQL 查詢必須同時帶 `fightIDs` 以及該 fight 的相對 `startTime` / `endTime`。少數 FFLogs 舊報告的 `report.endTime` 可能停在 fight 中途；只用 `fightIDs` 會拿到 partial table，導致 rDPS/aDPS 異常放大。

`active_percent` 對齊 FFLogs Damage Done CSV 的 Active%，優先使用 `fflogs_total_time_ms` 作為分母；DPS/rDPS/aDPS 仍使用 `damage_time_ms` 作為分母。

## Hidden Report 與完整鏡像

資料管線可在 report 上標記：

- `report_hidden: true`
- `hidden_reason`
- `hidden_detected_at_iso`
- `hidden_source`

一般公開資料會排除 hidden report，讓前端不需要在 Vue 元件內重做資料狀態判斷。`public/data/all/` 會同步輸出完整資料鏡像，供額外檢視流程使用。

額外檢視流程若需要完整資料，應只把 `/data/...` 改寫到 `/data/all/...`；若部署端尚未產生鏡像，應退回一般公開資料，避免網站載入失敗。

若玩家的公開成績沒有可列出的 entry，一般 `public/data/users/index.json` 仍會保留空白成績單入口與伺服器資訊，讓 `/user/{玩家}` 頁面可以開啟；預設成績單不會輸出副本成績、分數、隊友或紀錄時間。

## 版本切點與過版紀錄

`config/encounters.json` 的 `version_cutoff` 用來描述副本版本有效期限。目前 `極 佐拉加` 與 `極 豔翼蛇鳥` 的過版切點是台灣時間 2026-04-21 18:00，對應 `2026-04-21T10:00:00.000Z`。

`scripts/fetch_fflogs.py --rebuild-public` 會依 `start_time` 標記公開排行榜條目的：

- `is_obsolete_record`
- `version_status`
- `version_cutoff_iso`
- `version_ranking_entries.all|valid|obsolete`

`scripts/build_user_data.mjs` 會在全服統計、個人成績單與隊伍榜輸出 `version_slices.all|valid|obsolete`。同職分位、個人最佳紀錄與職業最佳紀錄只能使用 `valid` 紀錄，過版紀錄只作為歷史資料呈現與追溯。

前端版本篩選一律使用 `version=all|valid|obsolete` 的網址狀態；若副本沒有 `version_cutoff`，必須自動回到 `all`，避免非過版副本出現無效篩選。

## 外部工具連結

排行榜報告欄以「報告」按鈕開啟可關閉的彈跳視窗，集中呈現該筆成績數值與 FFLogs、xivanalysis、ffreplay 外部工具連結。

精準 xivanalysis 玩家頁使用公開 JSON 的 `report_code`、`fight_id` 與 `fflogs_source_id` 組成 `/fflogs/{report}/{fight}/{sourceID}`。`fflogs_source_id` 來自 FFLogs `playerDetails` 的 sourceID，只用於外部工具深連結，不作為排行榜角色身分主鍵。ffreplay 連結則使用含 `fight` query 的 FFLogs URL 進行 URL encode。
