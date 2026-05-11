# 專案運作準則 (Operating Principles)

本專案為「FFXIV 繁中服專屬高難度副本排行榜」系統。專案架構包含基於 Vue 3 / Vite 的前端網站，以及基於 Python 與 FFLogs GraphQL API 的資料管線（Data Pipeline）。所有開發、重構、文件撰寫與註解都必須嚴格遵守以下準則。

## 1. 嚴格遵守準則 (Strict Adherence)
* **最高優先級**：本運作準則必須被嚴格執行。在每一個開發與重構的步驟中，請反覆確認是否符合此處列出的所有規範。

## 2. 全盤檢視與交接導向 (Context & Handover)
* **完整檢視**：每次修改前，必須完整檢視專案所有相關程式碼（包含 Python 爬蟲腳本、Node.js 聚合腳本、JSON 資料結構與 Vue 前端狀態管理），確保理解整體脈絡。
* **交接思維**：撰寫程式碼與註解時，必須假設「這份專案即將移交給完全未接觸過的新人」。盡可能添加詳細的上下文（Context）註解。尤其是涉及 **FFLogs 欄位解析與 GraphQL 查詢優化**、**rDPS / aDPS 等輸出數據計算邏輯**，以及 **跨伺服器玩家身分判定與去重機制**時，必須解釋「為什麼這樣做（業務邏輯）」而非僅是「做了什麼」，確保資料整理邏輯清晰可追溯。

## 3. 規劃優先 (Planning First)
* 在實際撰寫程式碼前，必須先規劃要執行的項目與影響範圍，並列出簡要的 Step-by-step 計畫。
* **資料結構優先**：任何涉及 `config/encounters.json` (副本設定) 或輸出 JSON Schema 的變更規劃，必須優先確認是否會破壞現有已抓取的 `data/rankings/` 歷史紀錄，或影響前端讀取資料的向後相容性。

## 4. 變更檢核與自我修正 (Verification & Review)
* **Git Diff 檢查**：每次執行完畢前，必須執行 `git diff` 重新檢視即將提交的變更。
* **意義確認**：確認所有更新皆有具體意義、無多餘程式碼（Clean Code），且每一處複雜邏輯變更都附帶了充分的註解說明。

## 5. 強制測試與驗證 (Mandatory Testing & Validation)
* **執行測試**：每次任務執行完畢前，必須進行測試以確保功能正常且無回歸錯誤（Regression）。
* **測試優先級**：針對 **「FFLogs API 限流與重試機制（Rate Limit & Backoff）」**、**「無效或隱藏報告的例外捕捉」** 與 **「`npm run build:user-data` 資料聚合正確性」**，必須確保腳本能順利執行到底，保證前端依賴的靜態 JSON 檔案完整且準確。

## 6. 文件一致性與可追溯性 (Documentation Consistency)
* **全面同步**：每次執行完畢前，必須完整檢視 `CLAUDE.md`、`AGENTS.md` 與 `README.md`。
* **逐一檢核**：確認文件內的所有紀錄（如：GitHub Actions 排程時間、環境變數需求、手動補抓指令、相依套件）與目前的專案狀態完全相符。

## 7. 架構邊界嚴守 (Architecture Boundaries)
本專案為靜態化分離架構，職責必須嚴格分離：
* **Data Fetching Layer (資料管線層 - Python)**：負責處理最純粹的資料獲取（GraphQL 查詢、限流控制、繁中服玩家初步過濾）。嚴禁在此層直接寫入與 UI 呈現相關的格式。
* **Data Building Layer (資料建置層 - Node.js)**：負責將原始的分散資料，聚合為使用者易讀的「全服統計」與「個人成績單」。複雜的陣列排序與統計運算必須在此層完成（如 `build_user_data.mjs`）。
* **UI Presentation (表現層 - Vue 3)**：僅負責讀取 `public/data/` 內的靜態 JSON 檔案進行渲染、篩選與狀態管理。**嚴禁在前端元件內直接發送 Request 至 FFLogs API**。

## 8. 語言規範與在地化 (Language & Localization Standards)
* 所有對話、Git Commit Message、文件、註解皆需使用**繁體中文 (台灣用語)**。
* **Git Commit Message 格式必須遵循常規慣例**：一律採用 `type(scope): 中文描述`，例如 `feat(parser): 實作極樓神通關紀錄的解析邏輯`。`type` 應依變更性質選用 `feat`, `fix`, `docs`, `refactor`, `test`, `chore` 等；`scope` 必須對應實際影響模組。
* **每一筆 Commit 都必須補完整 Description（commit body）**：Description 必須使用繁體中文（台灣用語），清楚記錄 Why、主要變更、測試/驗證結果。
* **嚴禁使用中國用語**：例如將「接口、項目、回調、模塊、內存、數據庫、服務器、異步」必須嚴格替換為「**API/介面、專案、回呼、模組、記憶體、資料庫、伺服器、非同步**」。

## 9. 資料狀態與例外處理 (Data State & Exception Handling)
* **Append-Only 保護原則**：`data/state.json` 的 report 狀態、`data/rankings/*.json` 的 reports，以及 `config/encounters.json` 的 encounter key 皆為不可逆的重要歷史資產。
* **禁止覆寫或硬刪除**：嚴禁寫出會隨意覆蓋或刪除歷史紀錄的程式碼。如果需要同步資料，必須使用 `npm run sync:data`，並事先透過 `--dry-run` 檢查是否有 `REMOVAL` 或 `CONFLICT` 發生。
* **API 例外處理**：FFLogs API 可能會發生逾時或回傳不完整資料，Python 爬蟲必須實作穩健的 Exception 捕捉機制，記錄錯誤 report code，確保掃描進度不會中斷崩潰。

## 10. 開發伺服器與環境限制 (Dev Server & Environment Limits)
* **禁止擅自啟動服務 (Agent Instructions)**：除非使用者明確要求，否則嚴禁擅自啟動 Vite 開發伺服器（例如執行 `npm run dev`、`vite` 或同等指令）。
* **核准機制 (Agent Instructions)**：若前端驗證或功能測試通常需要依賴開發伺服器，請先向使用者說明需要啟動伺服器的原因，並在取得使用者明確同意後方可啟動。
* **環境變數安全**：`.env` 內的 `FFLOGS_CLIENT_ID` 等憑證為敏感資訊，嚴禁在任何除錯輸出、Log 或 Commit 中印出明文。

## 11. 程式碼風格 (Code Style)
* 前端專案需符合 Vue 3 組合式 API (Composition API) 最佳實踐及 ESLint 規範。
* 後端管線需符合 Python 3.11+ 的 PEP 8 規範。
* 全面實施**強型別**開發思維：Python 腳本應加上 Type Hints（型別提示）；前端與 Node.js 資料處理應明確知道 JSON 的結構邊界。

## 12. 準則鎖定 (Principle Locking)
* 本「運作準則」不允許被 AI 自行修改，僅能由使用者發起變更。
* 文件末端可新增「附錄：已確立的技術決策」，由 AI 於開發過程中隨實作累積補充技術細節（如 FFLogs GraphQL 查詢 Schema、資料檔結構對應），作為未來協作的背景知識。

## 附錄：已確立的技術決策
