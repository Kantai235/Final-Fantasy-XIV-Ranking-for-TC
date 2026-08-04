import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  buildHeaderRepairRanges,
  buildHiddenReportSet,
  buildIndexedReportSet,
  buildMalformedMessageRepairRanges,
  buildReportStatusesByCode,
  buildUpdateRanges,
  canonicalizeQueueHeaders,
} from "./complete_fflogs_refresh_queue.mjs";

const TEMP_PREFIX = "fflogs-refresh-queue-";
const SHEET_NAME = "pending";
const NOW_ISO = "2026-07-16T10:00:00.000Z";

async function writeJson(filePath, value) {
  await mkdir(path.dirname(filePath), { recursive: true });
  await writeFile(filePath, `${JSON.stringify(value)}\n`, "utf8");
}

function updateValue(updates, cell) {
  const update = updates.find((item) => item.range === `'${SHEET_NAME}'!${cell}`);
  return update?.values?.[0]?.[0];
}

async function main() {
  const repositoryRoot = await mkdtemp(path.join(os.tmpdir(), TEMP_PREFIX));
  try {
    const rankingsDir = path.join(repositoryRoot, "data", "rankings");
    await writeJson(path.join(rankingsDir, "fixture.json"), {
      ranking_entries: [],
      report_shards: ["data/rankings/fixture.reports/000.json"],
    });
    await writeJson(path.join(rankingsDir, "fixture.reports", "000.json"), {
      ShardOnly123: {
        report_code: "ShardOnly123",
        fights: [{
          data_integrity: {
            calculation_version: 9,
            status: "valid",
            hidden_from_public: false,
          },
        }],
      },
      IntegrityBlocked123: {
        report_code: "IntegrityBlocked123",
        fights: [{
          data_integrity: {
            calculation_version: 9,
            status: "suspected",
            hidden_from_public: true,
          },
        }],
      },
      MissingIntegrity123: {
        report_code: "MissingIntegrity123",
        report_end_time_iso: "2026-07-29T00:00:00.000Z",
        fights: [{}],
      },
      LegacyNoIntegrity123: {
        report_code: "LegacyNoIntegrity123",
        report_end_time_iso: "2026-07-27T00:00:00.000Z",
        fights: [{}],
      },
      HiddenOnly123: {
        report_code: "HiddenOnly123",
        report_hidden: true,
        fights: [],
      },
    });

    const integrityBlockedReportCodes = new Set();
    const indexedReportCodes = await buildIndexedReportSet({
      statusIndexPath: path.join(repositoryRoot, "public", "data", "report_status_index.json"),
      hiddenStatusIndexPath: path.join(repositoryRoot, "public", "data", "all", "report_status_index.json"),
      sourceRankingsDir: rankingsDir,
      includeHidden: false,
      repositoryRoot,
      integrityBlockedReportCodes,
    });
    assert(indexedReportCodes.has("ShardOnly123"), "公開 report 分片必須能完成待收錄列");
    assert(!indexedReportCodes.has("HiddenOnly123"), "未啟用 hidden delta 時不得把隱藏 report 視為公開收錄");
    assert(!indexedReportCodes.has("IntegrityBlocked123"), "完整性隱藏 report 不得回覆為公開收錄");
    assert(integrityBlockedReportCodes.has("IntegrityBlocked123"), "完整性隱藏 report 必須進入站務複核集合");
    assert(!indexedReportCodes.has("MissingIntegrity123"), "新制切點後缺少完整性結果的 report 不得回覆為公開收錄");
    assert(integrityBlockedReportCodes.has("MissingIntegrity123"), "新制切點後缺少完整性結果的 report 必須進入站務複核集合");
    assert(indexedReportCodes.has("LegacyNoIntegrity123"), "新制切點前缺少完整性結果的 report 應維持向後相容");

    const hiddenStatusIndexPath = path.join(repositoryRoot, "public", "data", "all", "report_status_index.json");
    await writeJson(hiddenStatusIndexPath, {
      reports: [{ report_code: "HiddenOnly123" }],
    });
    const hiddenReportCodes = await buildHiddenReportSet({ hiddenStatusIndexPath });
    assert(hiddenReportCodes.has("HiddenOnly123"), "hidden delta 索引必須能結束公開狀態重新排查列");

    const statusesByCode = buildReportStatusesByCode({
      encounters: {
        savage_m1s: {
          checked_reports: {
            NoClear123: { status: "skipped_no_clear" },
            NoTcOnly123: { status: "skipped_no_traditional_chinese_players" },
          },
          processed_reports: {
            NoTcOnly123: { status: "skipped_no_clear" },
          },
        },
      },
    }, ["ShardOnly123", "IntegrityBlocked123", "NoClear123", "NoTcOnly123", "Waiting123"]);

    const updates = buildUpdateRanges({
      headers: ["report_code", "request_type", "status", "updated_at_iso", "last_message"],
      rows: [
        { _row_number: 2, report_code: "ShardOnly123", request_type: "retry_existing" },
        { _row_number: 3, report_code: "IntegrityBlocked123", request_type: "retry_existing" },
        { _row_number: 4, report_code: "NoClear123", request_type: "new" },
        { _row_number: 5, report_code: "NoTcOnly123", request_type: "new" },
        { _row_number: 6, report_code: "Waiting123", request_type: "new" },
      ],
      sheetName: SHEET_NAME,
      nowIso: NOW_ISO,
      maxRows: 500,
      indexedReportCodes,
      statusesByCode,
      integrityBlockedReportCodes,
    });

    assert.equal(updateValue(updates, "C2"), "done");
    assert.match(updateValue(updates, "E2"), /公開資料已收錄/);
    assert.equal(updateValue(updates, "C3"), "review_required_data_integrity");
    assert.match(updateValue(updates, "E3"), /資料完整性規則暫時隱藏/);
    assert.equal(updateValue(updates, "C4"), "not_eligible_no_clear");
    assert.match(updateValue(updates, "E4"), /未找到本站支援副本的通關戰鬥/);
    assert.equal(updateValue(updates, "C5"), "not_eligible_no_traditional_chinese_players");
    assert.match(updateValue(updates, "E5"), /未發現繁中服玩家/);
    assert.equal(updateValue(updates, "C6"), undefined, "尚無終局結果的列必須保留 queued/pending/retry");
    assert.equal(updates.length, 12, "四筆終局結果各應更新 status、時間與訊息");

    const visibilityReviewUpdates = buildUpdateRanges({
      headers: ["report_code", "requested_action", "status", "updated_at_iso", "last_message"],
      rows: [
        { _row_number: 6, report_code: "HiddenOnly123", requested_action: "review_existing_visibility" },
        { _row_number: 7, report_code: "HiddenOnly123", requested_action: "queue_missing" },
      ],
      sheetName: SHEET_NAME,
      nowIso: NOW_ISO,
      maxRows: 500,
      indexedReportCodes,
      statusesByCode,
      hiddenReportCodes,
    });
    assert.equal(updateValue(visibilityReviewUpdates, "C6"), "hidden");
    assert.match(updateValue(visibilityReviewUpdates, "E6"), /標記為 hidden/);
    assert.equal(updateValue(visibilityReviewUpdates, "C7"), undefined, "只有公開狀態重新排查可因 hidden delta 結束列");

    const malformedHeaders = [
      "submitted_at_iso",
      "updated_at_iso",
      "report_code",
      "report_url",
      "requested_action",
      "site_status",
      "fight_text",
      "fflogs_access",
      "visibility",
      "archive_accessible",
      "status",
      "request_count",
      "request_count",
      "source",
    ];
    const repairedHeaders = canonicalizeQueueHeaders(malformedHeaders);
    const headerUpdates = buildHeaderRepairRanges({ headers: malformedHeaders, sheetName: SHEET_NAME });
    assert.equal(repairedHeaders[12], "last_message", "重複 request_count 必須回復為 last_message");
    assert.equal(updateValue(headerUpdates, "M1"), "last_message", "workflow 必須修復錯置的訊息欄標題");
    assert.equal(headerUpdates.length, 1, "正確 schema 僅應修復錯置欄位");

    const messageUpdates = buildMalformedMessageRepairRanges({
      headers: repairedHeaders,
      rows: [
        {
          _row_number: 6,
          report_code: "ShardOnly123",
          requested_action: "queue_missing",
          status: "done",
          request_count: "1",
          last_message: "1",
        },
        {
          _row_number: 7,
          report_code: "ShardOnly123",
          requested_action: "retry_existing",
          status: "done",
          request_count: "1",
          last_message: "1",
        },
        {
          _row_number: 8,
          report_code: "ShardOnly123",
          requested_action: "queue_missing",
          status: "done",
          request_count: "1",
          last_message: "站務保留訊息",
        },
      ],
      sheetName: SHEET_NAME,
      indexedReportCodes,
      statusesByCode,
      hiddenReportCodes,
    });
    assert.equal(updateValue(messageUpdates, "M6"), "workflow 已確認公開資料收錄 report。");
    assert.equal(updateValue(messageUpdates, "M7"), "workflow 已送出整份 report 重掃，公開資料已收錄此 report。");
    assert.equal(updateValue(messageUpdates, "M8"), undefined, "非數字的既有訊息不得被覆寫");

    console.log("FFLogs 待收錄名單收尾測試通過。");
  } finally {
    await rm(repositoryRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
