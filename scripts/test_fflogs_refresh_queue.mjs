import assert from "node:assert/strict";
import { mkdtemp, mkdir, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  buildIndexedReportSet,
  buildReportStatusesByCode,
  buildUpdateRanges,
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
        fights: [],
      },
      HiddenOnly123: {
        report_code: "HiddenOnly123",
        report_hidden: true,
        fights: [],
      },
    });

    const indexedReportCodes = await buildIndexedReportSet({
      statusIndexPath: path.join(repositoryRoot, "public", "data", "report_status_index.json"),
      hiddenStatusIndexPath: path.join(repositoryRoot, "public", "data", "all", "report_status_index.json"),
      sourceRankingsDir: rankingsDir,
      includeHidden: false,
      repositoryRoot,
    });
    assert(indexedReportCodes.has("ShardOnly123"), "公開 report 分片必須能完成待收錄列");
    assert(!indexedReportCodes.has("HiddenOnly123"), "未啟用 hidden delta 時不得把隱藏 report 視為公開收錄");

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
    }, ["ShardOnly123", "NoClear123", "NoTcOnly123", "Waiting123"]);

    const updates = buildUpdateRanges({
      headers: ["report_code", "request_type", "status", "updated_at_iso", "last_message"],
      rows: [
        { _row_number: 2, report_code: "ShardOnly123", request_type: "retry_existing" },
        { _row_number: 3, report_code: "NoClear123", request_type: "new" },
        { _row_number: 4, report_code: "NoTcOnly123", request_type: "new" },
        { _row_number: 5, report_code: "Waiting123", request_type: "new" },
      ],
      sheetName: SHEET_NAME,
      nowIso: NOW_ISO,
      maxRows: 500,
      indexedReportCodes,
      statusesByCode,
    });

    assert.equal(updateValue(updates, "C2"), "done");
    assert.match(updateValue(updates, "E2"), /公開資料已收錄/);
    assert.equal(updateValue(updates, "C3"), "not_eligible_no_clear");
    assert.match(updateValue(updates, "E3"), /未找到本站支援副本的通關戰鬥/);
    assert.equal(updateValue(updates, "C4"), "not_eligible_no_traditional_chinese_players");
    assert.match(updateValue(updates, "E4"), /未發現繁中服玩家/);
    assert.equal(updateValue(updates, "C5"), undefined, "尚無終局結果的列必須保留 queued/pending/retry");
    assert.equal(updates.length, 9, "三筆終局結果各應更新 status、時間與訊息");

    console.log("FFLogs 待收錄名單收尾測試通過。");
  } finally {
    await rm(repositoryRoot, { recursive: true, force: true });
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.stack || error.message : error);
  process.exitCode = 1;
});
