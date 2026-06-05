import { appendFileSync, existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const configPath = path.join(rootDir, "config", "encounters.json");
const statePath = path.join(rootDir, "data", "state.json");
const rankingsDir = path.join(rootDir, "data", "rankings");
const fetchScriptPath = path.join(rootDir, "scripts", "fetch_fflogs.py");
const githubStepSummaryPath = process.env.GITHUB_STEP_SUMMARY || "";

const rawArgs = process.argv.slice(2);
const includeDisabled = rawArgs.includes("--include-disabled");
const maxPendingExamples = Math.max(0, Number(readOption("--max-pending-examples") || 8) || 8);
const historyWindowHours = Math.max(1, Number(process.env.FFLOGS_HISTORY_SCAN_WINDOW_HOURS || readOption("--history-window-hours") || 168) || 168);
const historyWindowsPerRun = Math.max(1, Number(process.env.FFLOGS_HISTORY_SCAN_WINDOWS_PER_RUN || readOption("--history-windows-per-run") || 1) || 1);

const noNeedStatuses = new Set(["skipped_no_traditional_chinese_players", "skipped_inaccessible"]);

function readOption(name) {
  const inlinePrefix = `${name}=`;
  for (let index = 0; index < rawArgs.length; index += 1) {
    const arg = rawArgs[index];
    if (arg === name) {
      return rawArgs[index + 1] || "";
    }
    if (arg.startsWith(inlinePrefix)) {
      return arg.slice(inlinePrefix.length);
    }
  }
  return "";
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

function readJson(filePath, fallback = null) {
  if (!existsSync(filePath)) {
    return fallback;
  }
  return JSON.parse(readFileSync(filePath, "utf8"));
}

function assertInside(parent, target, label) {
  const relative = path.relative(parent, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`${label} 指向允許目錄外：${normalizePath(path.relative(rootDir, target))}`);
  }
}

function readMixedDispatchRevision() {
  const source = readFileSync(fetchScriptPath, "utf8");
  const match = source.match(/混合Report分派版本\s*=\s*"([^"]+)"/u);
  if (!match) {
    throw new Error("無法從 scripts/fetch_fflogs.py 讀取混合 Report 分派版本。");
  }
  return match[1];
}

function enabledEncounterList(encounters) {
  return encounters.filter((encounter) => {
    if (!encounter || typeof encounter !== "object") {
      return false;
    }
    if (!includeDisabled && !encounter.enabled) {
      return false;
    }
    return Boolean(encounter.key && encounter.name);
  });
}

function readRankingReportCodes(encounterKey) {
  const rankingPath = path.join(rankingsDir, `${encounterKey}.json`);
  const ranking = readJson(rankingPath, {});
  const codes = new Set();
  const inlineReports = ranking?.reports;
  if (inlineReports && typeof inlineReports === "object" && !Array.isArray(inlineReports)) {
    for (const code of Object.keys(inlineReports)) {
      codes.add(String(code));
    }
  }

  const shardPaths = Array.isArray(ranking?.report_shards) ? ranking.report_shards : [];
  for (const shardPathText of shardPaths) {
    if (typeof shardPathText !== "string" || !shardPathText) {
      continue;
    }
    const shardPath = path.resolve(rootDir, shardPathText);
    assertInside(rankingsDir, shardPath, "ranking report shard");
    const shard = readJson(shardPath, {});
    if (!shard || typeof shard !== "object" || Array.isArray(shard)) {
      continue;
    }
    for (const code of Object.keys(shard)) {
      codes.add(String(code));
    }
  }

  return codes;
}

function stateRecordPairs(encounterState, reportCode) {
  const records = [];
  for (const field of ["processed_reports", "checked_reports"]) {
    const recordMap = encounterState?.[field];
    if (!recordMap || typeof recordMap !== "object" || Array.isArray(recordMap)) {
      continue;
    }
    const record = recordMap[reportCode];
    if (record && typeof record === "object" && !Array.isArray(record)) {
      records.push({ field, record });
    }
  }
  return records;
}

function reportHasRevision(records, revision) {
  return records.some(({ record }) => record.mixed_report_dispatch_revision === revision);
}

function reportDoesNotNeedRecheck(records) {
  return records.some(({ record }) => noNeedStatuses.has(record.status));
}

function reportStatusLabel(records) {
  const labels = records
    .map(({ field, record }) => `${field}:${record.status || "unknown"}`)
    .filter(Boolean);
  return labels.length > 0 ? labels.join(", ") : "ranking_only";
}

function formatInteger(value) {
  return Number(value || 0).toLocaleString("zh-TW");
}

function formatPercent(numerator, denominator) {
  if (!denominator) {
    return "100.0%";
  }
  return `${((numerator / denominator) * 100).toFixed(1)}%`;
}

function formatIso(value) {
  return typeof value === "string" && value ? value : "-";
}

function historyProgress(encounterState) {
  const start = Number(encounterState?.history_scan_range_start_at);
  const end = Number(encounterState?.history_scan_range_end_at);
  const cursor = Number(encounterState?.history_scan_cursor_at);
  const lastWindowEnd = Number(encounterState?.history_last_window_end_at);
  const enabled = Boolean(encounterState?.history_scan_enabled);
  const deferred = Number(encounterState?.history_last_reports_deferred || 0);
  const mixedDispatchRecheckSelected = (
    Number(encounterState?.delayed_last_reports_mixed_dispatch_recheck_selected || 0)
    + Number(encounterState?.history_last_reports_mixed_dispatch_recheck_selected || 0)
  );
  const selected = Number(encounterState?.history_last_reports_selected || 0);
  const found = Number(encounterState?.history_last_reports_found || 0);

  if (!enabled || !Number.isFinite(start) || !Number.isFinite(end) || end <= start || !Number.isFinite(cursor)) {
    return {
      enabled,
      percent: null,
      remainingWindows: null,
      remainingRuns: null,
      cycleCompletedThisRun: false,
      deferred,
      mixedDispatchRecheckSelected,
      selected,
      found,
      label: enabled ? "缺少游標" : "未啟用",
    };
  }

  const clampedCursor = Math.min(Math.max(cursor, start), end + 1);
  const percent = ((clampedCursor - start) / (end - start + 1)) * 100;
  const windowMs = historyWindowHours * 60 * 60 * 1000;
  const remainingMs = Math.max(0, end - clampedCursor + 1);
  const remainingWindows = Math.ceil(remainingMs / windowMs);
  const remainingRuns = Math.ceil(remainingWindows / historyWindowsPerRun);
  const cycleCompletedThisRun = cursor === start && Number.isFinite(lastWindowEnd) && lastWindowEnd >= end;

  return {
    enabled,
    percent,
    remainingWindows,
    remainingRuns,
    cycleCompletedThisRun,
    deferred,
    mixedDispatchRecheckSelected,
    selected,
    found,
    label: cycleCompletedThisRun
      ? "最近完成一圈"
      : `${percent.toFixed(1)}%，估 ${formatInteger(remainingRuns)} 輪`,
  };
}

function buildEncounterAudit(encounter, state, revision) {
  const encounterState = state?.encounters?.[encounter.key] || {};
  const processedReports = encounterState.processed_reports && typeof encounterState.processed_reports === "object"
    ? encounterState.processed_reports
    : {};
  const checkedReports = encounterState.checked_reports && typeof encounterState.checked_reports === "object"
    ? encounterState.checked_reports
    : {};
  const rankingReportCodes = readRankingReportCodes(encounter.key);
  const knownCodes = new Set([
    ...Object.keys(processedReports).map(String),
    ...Object.keys(checkedReports).map(String),
    ...rankingReportCodes,
  ]);

  const pendingExamples = [];
  let currentRevision = 0;
  let noNeed = 0;
  let pending = 0;
  let rankingOnlyPending = 0;

  for (const code of knownCodes) {
    const records = stateRecordPairs(encounterState, code);
    if (reportHasRevision(records, revision)) {
      currentRevision += 1;
      continue;
    }
    if (reportDoesNotNeedRecheck(records)) {
      noNeed += 1;
      continue;
    }

    pending += 1;
    if (records.length === 0 && rankingReportCodes.has(code)) {
      rankingOnlyPending += 1;
    }
    if (pendingExamples.length < maxPendingExamples) {
      pendingExamples.push({
        code,
        status: reportStatusLabel(records),
        source: records.length === 0 && rankingReportCodes.has(code) ? "ranking_only" : "state",
      });
    }
  }

  const required = knownCodes.size - noNeed;
  const completedRequired = currentRevision;
  const history = historyProgress(encounterState);
  return {
    key: encounter.key,
    name: encounter.name,
    category: encounter.category || "",
    enabled: Boolean(encounter.enabled),
    known: knownCodes.size,
    rankingReports: rankingReportCodes.size,
    stateReports: new Set([...Object.keys(processedReports), ...Object.keys(checkedReports)]).size,
    currentRevision,
    noNeed,
    required,
    completedRequired,
    pending,
    rankingOnlyPending,
    pendingExamples,
    history,
    historyCursorIso: formatIso(encounterState.history_scan_cursor_at_iso),
    historyRangeEndIso: formatIso(encounterState.history_scan_range_end_at_iso),
    historyLastWindowIso: [
      formatIso(encounterState.history_last_window_start_at_iso),
      formatIso(encounterState.history_last_window_end_at_iso),
    ].join(" ~ "),
  };
}

function summarize(rows) {
  return rows.reduce(
    (summary, row) => {
      summary.known += row.known;
      summary.required += row.required;
      summary.currentRevision += row.currentRevision;
      summary.noNeed += row.noNeed;
      summary.pending += row.pending;
      summary.rankingOnlyPending += row.rankingOnlyPending;
      summary.historyEnabled += row.history.enabled ? 1 : 0;
      summary.historyCycleCompletedThisRun += row.history.cycleCompletedThisRun ? 1 : 0;
      summary.historyDeferred += row.history.deferred;
      summary.mixedDispatchRecheckSelected += row.history.mixedDispatchRecheckSelected;
      return summary;
    },
    {
      known: 0,
      required: 0,
      currentRevision: 0,
      noNeed: 0,
      pending: 0,
      rankingOnlyPending: 0,
      historyEnabled: 0,
      historyCycleCompletedThisRun: 0,
      historyDeferred: 0,
      mixedDispatchRecheckSelected: 0,
    },
  );
}

function markdownTable(rows) {
  const lines = [
    "副本 | 已知 | 已寫版本 | 不需重查 | 待重查 | 完成度 | 歷史游標 | mixed 重查 | deferred",
    "--- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---:",
  ];
  for (const row of rows) {
    lines.push(
      [
        row.name,
        formatInteger(row.known),
        formatInteger(row.currentRevision),
        formatInteger(row.noNeed),
        formatInteger(row.pending),
        formatPercent(row.completedRequired, row.required),
        row.history.label,
        formatInteger(row.history.mixedDispatchRecheckSelected),
        formatInteger(row.history.deferred),
      ].join(" | "),
    );
  }
  return lines;
}

function pendingMarkdown(rows) {
  const rowsWithPending = rows
    .filter((row) => row.pending > 0)
    .sort((a, b) => b.pending - a.pending || a.key.localeCompare(b.key));
  if (rowsWithPending.length === 0) {
    return ["目前沒有已知 report 需要補跑 mixed report 分派。"];
  }

  const lines = [
    "副本 | 待重查 | ranking-only | 範例",
    "--- | ---: | ---: | ---",
  ];
  for (const row of rowsWithPending.slice(0, 10)) {
    const examples = row.pendingExamples
      .map((item) => `${item.code} (${item.status})`)
      .join("<br>");
    lines.push(`${row.name} | ${formatInteger(row.pending)} | ${formatInteger(row.rankingOnlyPending)} | ${examples || "-"}`);
  }
  return lines;
}

function buildMarkdownReport(rows, summary, revision) {
  const statusLine = summary.pending === 0
    ? "已知 report 的 mixed report 分派版本已補齊。"
    : `仍有 ${formatInteger(summary.pending)} 筆已知副本-report 組合待補跑 mixed report 分派。`;

  return [
    "## 混合上傳 Report 分派完成度",
    "",
    `- 分派版本：\`${revision}\``,
    `- 稽核範圍：${includeDisabled ? "全部 config/encounters.json 副本" : "enabled=true 副本"}`,
    `- 已知副本-report 組合：${formatInteger(summary.known)}`,
    `- 需寫版本完成度：${formatPercent(summary.currentRevision, summary.required)}（${formatInteger(summary.currentRevision)} / ${formatInteger(summary.required)}，不含已確認無繁中服玩家或不可存取）`,
    `- 不需重查：${formatInteger(summary.noNeed)}`,
    `- 待重查：${formatInteger(summary.pending)}，其中 ranking-only ${formatInteger(summary.rankingOnlyPending)}`,
    `- 歷史補查：${formatInteger(summary.historyEnabled)} 個副本啟用；最近一次完成一圈 ${formatInteger(summary.historyCycleCompletedThisRun)} 個；mixed 重查選入 ${formatInteger(summary.mixedDispatchRecheckSelected)} 筆；deferred ${formatInteger(summary.historyDeferred)} 筆`,
    "",
    `> ${statusLine} 歷史游標代表 FFLogs 時間窗輪巡進度；若 deferred 大於 0，代表深查上限仍在限制追趕速度。`,
    "",
    ...markdownTable(rows),
    "",
    "### 待重查範例",
    "",
    ...pendingMarkdown(rows),
    "",
  ];
}

function printConsoleReport(lines) {
  console.log(lines.join("\n"));
}

function appendStepSummary(lines) {
  if (!githubStepSummaryPath) {
    return;
  }
  appendFileSync(githubStepSummaryPath, `${lines.join("\n")}\n`, "utf8");
}

const revision = readMixedDispatchRevision();
const encounters = enabledEncounterList(readJson(configPath, []));
const state = readJson(statePath, {});
const rows = encounters.map((encounter) => buildEncounterAudit(encounter, state, revision));
const summary = summarize(rows);
const lines = buildMarkdownReport(rows, summary, revision);

printConsoleReport(lines);
appendStepSummary(lines);
