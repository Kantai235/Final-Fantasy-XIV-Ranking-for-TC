# FFLogs Report 狀態查詢 Apps Script

這個 Apps Script Web App 是排行榜前端以外的受保護小後端：

- 使用 FFLogs OAuth Client Credentials 向 FFLogs GraphQL API 查詢單一 report。
- 回答「目前 FFLogs API 是否可讀取這份 report」。
- 當 report 已 Public 且可讀時，可把 report code 寫入 Google Sheet 待收錄名單。
- 不判斷是否應收錄排行榜，因為收錄仍必須由 `scripts/fetch_fflogs.py` 檢查繁中服玩家、支援副本、通關 fight 與 FFLogs 匯出完整度。

## 建立 Apps Script 專案

1. 開啟 [Google Apps Script](https://script.google.com/)。
2. 建立新專案，命名為 `FFXIV TC FFLogs Report Status`。
3. 將本目錄的 `Code.gs` 貼到 Apps Script 編輯器中的 `Code.gs`。
4. 在左側「專案設定」勾選「在編輯器中顯示 appsscript.json 資訊清單檔」。
5. 將本目錄的 `appsscript.json` 貼到 Apps Script 的 `appsscript.json`。

## 設定 FFLogs 憑證

在 Apps Script 編輯器中新增一個一次性設定函式，填入 FFLogs OAuth client id 與 secret 後執行一次：

```javascript
function setupSecretsOnce() {
  PropertiesService.getScriptProperties().setProperties({
    FFLOGS_CLIENT_ID: "填入 FFLogs client id",
    FFLOGS_CLIENT_SECRET: "填入 FFLogs client secret",
    FFLOGS_QUEUE_SPREADSHEET_ID: "填入 Google Sheet ID",
    FFLOGS_QUEUE_SHEET_NAME: "pending",
  });
}
```

執行完成後，立刻刪除 `setupSecretsOnce()` 函式，避免憑證留在程式碼中。這些值會存在 Apps Script 的 Script Properties，不會被 Web App 回傳給使用者。

`FFLOGS_QUEUE_SPREADSHEET_ID` 是 Google Sheet 網址中 `/d/` 和 `/edit` 之間的 ID。`FFLOGS_QUEUE_SHEET_NAME` 可省略，預設是 `pending`。

## 建立待收錄 Google Sheet

建立一份 Google Sheet，並把 Apps Script 執行者帳號設為可編輯。Apps Script 第一次寫入時會建立 `pending` 工作表欄位；之後每次寫入都會校正 A:N 的標題順序，但不改寫歷史資料列，避免手動誤改標題後把 `request_count` 寫入 `last_message`：

| 欄位 | 用途 |
| --- | --- |
| `submitted_at_iso` | 第一次送出的時間。 |
| `updated_at_iso` | 最近一次送出或要求重查的時間。 |
| `report_code` | FFLogs report code，workflow 會讀這欄。 |
| `report_url` | FFLogs report URL。 |
| `requested_action` | `queue_missing` 或 `retry_existing`。 |
| `site_status` | 前端當下判斷的站內狀態，例如 `missing`、`found`、`fight_missing`。 |
| `fight_text` | 使用者網址指定的 fight。 |
| `fflogs_access` / `visibility` / `archive_accessible` | Apps Script 送出時重新確認的 FFLogs 狀態。 |
| `status` | workflow 會讀取 `queued`、`pending` 或 `retry`；收尾後依結果標記為 `done`、`not_eligible_no_clear` 或 `not_eligible_no_traditional_chinese_players`。 |
| `request_count` | 同一 report 重複送出的次數。 |
| `last_message` | 給站務看的最近處理摘要。 |
| `source` | 來源，目前主站使用 `faq`。 |

若不想讓某筆繼續被 workflow 讀取，可手動把 `status` 改成 `done`、`ignored` 或其它非 `queued/pending/retry` 的值。正式 workflow 也會在收尾時把已收錄、無通關或無繁中服玩家的列改為對應終止狀態，不會刪除列。

## 部署 Web App

1. 點選「部署」>「新增部署作業」。
2. 類型選「網頁應用程式」。
3. `執行身分` 選「我」。
4. `誰可以存取` 選「所有人」。
5. 部署後複製 `/exec` 結尾的 Web App URL。

`/dev` URL 只適合站務測試，正式前端應使用 `/exec` URL。

## 手動測試

瀏覽器直接開啟：

```text
https://script.google.com/macros/s/你的部署ID/exec?report=FFLOGS_REPORT_CODE
```

若要用命令列測試，Apps Script Content Service 會轉址到 `script.googleusercontent.com`，所以 `curl` 需要加 `-L`：

```bash
curl -L "https://script.google.com/macros/s/你的部署ID/exec?report=FFLOGS_REPORT_CODE"
```

成功時會回傳類似：

```json
{
  "ok": true,
  "script_version": "fflogs-report-status-v1",
  "report_code": "FFLOGS_REPORT_CODE",
  "fflogs_access": "accessible",
  "visibility": "public",
  "archive_accessible": true,
  "message": "FFLogs API 目前可讀取這份 report。是否收錄仍需等待排行榜資料管線確認繁中服玩家、支援副本與通關 fight。"
}
```

## 前端 JSONP 測試

如果要先從靜態前端測試跨網域讀取，可用 JSONP：

```html
<script>
  window.handleFflogsStatus = (payload) => {
    console.log(payload);
  };
</script>
<script src="https://script.google.com/macros/s/你的部署ID/exec?report=FFLOGS_REPORT_CODE&callback=handleFflogsStatus"></script>
```

JSONP 會用於公開狀態查詢，以及在 report 已 Public 且可讀時送出待收錄需求；回傳內容不能包含 FFLogs OAuth token、client secret、Apps Script 設定值或站務用內部狀態。

## 串接主站常見問題頁

主站常見問題頁的 FFLogs 檢查工具會讀取 `VITE_FFLOGS_REPORT_STATUS_WEB_APP_URL`，用 JSONP 呼叫這個 `/exec` URL。若沒有另外設定，前端會使用目前版控內的預設 Apps Script URL。

```env
VITE_FFLOGS_REPORT_STATUS_WEB_APP_URL=https://script.google.com/macros/s/你的部署ID/exec
```

這個 URL 是公開唯讀 endpoint，不是 FFLogs OAuth secret。若之後在 Apps Script 重新建立部署、換了部署 ID，更新此環境變數後重新建置前端即可。

## 回傳狀態

| 欄位 | 說明 |
| --- | --- |
| `fflogs_access=accessible` | FFLogs API 目前可讀取 report。 |
| `fflogs_access=private_or_deleted` | FFLogs API 無法讀取 report；常見原因是 Private、已刪除、不存在或沒有權限。 |
| `fflogs_access=archived_inaccessible` | FFLogs 找到 report，但封存狀態不可存取。 |
| `error_code=rate_limited` | FFLogs OAuth 或 GraphQL API 回傳 429。 |
| `error_code=temporary_error` | FFLogs 或 Apps Script 暫時性錯誤。 |
| `error_code=server_config_error` | Apps Script 憑證未設定或 FFLogs OAuth 設定錯誤。 |
| `error_code=queue_write_error` | FFLogs 已確認可讀，但 Google Sheet 寫入失敗；檢查 `FFLOGS_QUEUE_SPREADSHEET_ID`、Apps Script 是否已重新授權 Sheets 權限，以及 Web App 是否以 `Execute as: Me` 部署。 |
| `error_code=invalid_report_code` | 使用者輸入的 report code 或網址格式不合法。 |

`accessible` 只代表 FFLogs API 可讀，不代表已收錄排行榜。排行榜資料仍會等 GitHub Actions 執行 `fetch_fflogs.py` 時處理。

## Workflow 讀取待收錄名單

GitHub Actions 使用 `scripts/read_fflogs_refresh_queue.mjs` 透過 Google Sheets API 讀取 `pending` 工作表，將符合條件的 report code 寫入 `FFLOGS_RETRY_REPORT_CODES`。workflow 收尾時會掃描公開狀態索引、排行榜 `source_reports` 與公開 report 分片：已收錄會標記為 `done`；已確認沒有支援副本通關會標記為 `not_eligible_no_clear`；未發現繁中服玩家會標記為 `not_eligible_no_traditional_chinese_players`。後兩者會保留原因文字且不會再次送入強制重掃；資料管線既有的近期 no-clear 重試規則不受影響。需要設定：

- Repository Variable `FFLOGS_REFRESH_QUEUE_SPREADSHEET_ID`
- Repository Variable `FFLOGS_REFRESH_QUEUE_SHEET_NAME`，預設 `pending`
- Repository Variable `FFLOGS_REFRESH_QUEUE_MAX_CODES`，預設 `50`
- Repository Variable `FFLOGS_REFRESH_QUEUE_COMPLETE_MAX_ROWS`，預設 `500`
- Repository Variable `FFLOGS_REFRESH_QUEUE_COMPLETE_INCLUDE_HIDDEN`，預設 `false`
- Repository Secret `GOOGLE_SHEETS_SERVICE_ACCOUNT_JSON`，或 `GOOGLE_SHEETS_CLIENT_EMAIL` + `GOOGLE_SHEETS_PRIVATE_KEY`

Service account 必須被分享為該 Google Sheet 的編輯者，因為 workflow 需要回寫已收錄或不符合收錄條件的終止狀態。前端不會接觸 service account 或 Sheet API 憑證。
