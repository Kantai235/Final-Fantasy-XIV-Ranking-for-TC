import { appendFileSync, existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const rawArgs = process.argv.slice(2);
const args = new Set(rawArgs);
const enforceTargets = args.has("--enforce-targets") || process.env.PAGES_PAYLOAD_ENFORCE_TARGETS === "true";
const distDir = path.resolve(rootDir, process.env.PAGES_PAYLOAD_DIST || "dist");
const historyPathArg = readOption("--write-history") || process.env.PAGES_PAYLOAD_HISTORY_PATH || "";
const historyLimit = Math.max(1, Number(readOption("--history-limit") || process.env.PAGES_PAYLOAD_HISTORY_LIMIT || 200) || 200);
const githubStepSummaryPath = process.env.GITHUB_STEP_SUMMARY || "";
const buildSeconds = parseOptionalNumber(process.env.PAGES_BUILD_SECONDS);

const MiB = 1024 * 1024;

const payloadBudgets = [
  {
    label: "完整 dist",
    relativePath: "",
    targetMiB: 950,
    hardMiB: Number(process.env.PAGES_PAYLOAD_DIST_HARD_MIB || 2048),
    reason: "GitHub Pages 官方建議發布站台不超過 1GB；目前先以硬上限防止體積繼續膨脹。",
  },
  {
    label: "公開資料總量",
    relativePath: "data",
    targetMiB: 800,
    hardMiB: Number(process.env.PAGES_PAYLOAD_DATA_HARD_MIB || 1800),
    reason: "public/data 是 Pages artifact 最大來源，後續瘦身應優先讓它降到 800MiB 以下。",
  },
  {
    label: "Hidden delta 資料",
    relativePath: "data/all",
    targetMiB: 90,
    hardMiB: Number(process.env.PAGES_PAYLOAD_ALL_HARD_MIB || 950),
    reason: "public/data/all 應維持 hidden delta，不可重新膨脹成完整公開資料複本。",
  },
  {
    label: "個人成績單資料（若保留於 artifact）",
    relativePath: "data/users",
    targetMiB: 530,
    hardMiB: Number(process.env.PAGES_PAYLOAD_USERS_HARD_MIB || 800),
    reason: "正式 Pages artifact 應在 postbuild 後移除這批 JSON，改由專用 users repo 提供；本機完整 build 或緊急流程若保留時仍需監控體積。",
  },
  {
    label: "逐玩家靜態分享頁",
    relativePath: "user",
    targetMiB: 2,
    hardMiB: Number(process.env.PAGES_PAYLOAD_USER_PAGES_HARD_MIB || 60),
    reason: "正式 Pages artifact 只保留 /user route 入口；逐玩家 HTML 會造成上萬個小檔同步到 GitHub Pages。",
  },
  {
    label: "OG 圖與分享頁媒體",
    relativePath: "og",
    targetMiB: 150,
    hardMiB: Number(process.env.PAGES_PAYLOAD_OG_HARD_MIB || 190),
    reason: "OG PNG 數量與使用者頁數同步成長，需要避免靜態分享資源無上限膨脹。",
  },
];

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

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

function parseOptionalNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : null;
}

function formatMiB(bytes) {
  return `${(bytes / MiB).toFixed(1)} MiB`;
}

function formatSignedMiB(bytes) {
  const sign = bytes > 0 ? "+" : "";
  return `${sign}${formatMiB(bytes)}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) {
    return "-";
  }
  if (seconds < 60) {
    return `${seconds.toFixed(0)} 秒`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes} 分 ${remainingSeconds} 秒`;
}

function listFiles(directory) {
  if (!existsSync(directory)) {
    return [];
  }

  const files = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const fullPath = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      files.push(...listFiles(fullPath));
    } else if (entry.isFile()) {
      files.push(fullPath);
    }
  }
  return files;
}

function measureDirectory(directory) {
  const files = listFiles(directory);
  return {
    fileCount: files.length,
    bytes: files.reduce((sum, file) => sum + statSync(file).size, 0),
  };
}

function resolveHistoryPath(filePath) {
  if (!filePath) {
    return "";
  }
  return path.isAbsolute(filePath) ? filePath : path.resolve(rootDir, filePath);
}

function readHistoryRecords(historyPath) {
  if (!historyPath || !existsSync(historyPath)) {
    return [];
  }

  return readFileSync(historyPath, "utf8")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      try {
        return JSON.parse(line);
      } catch {
        return null;
      }
    })
    .filter(Boolean);
}

function buildHistoryRecord(rows) {
  const runId = process.env.GITHUB_RUN_ID || null;
  const repository = process.env.GITHUB_REPOSITORY || null;
  return {
    schema_version: 1,
    recorded_at_iso: new Date().toISOString(),
    mode: enforceTargets ? "strict" : "baseline",
    event: process.env.GITHUB_EVENT_NAME || null,
    branch: process.env.GITHUB_REF_NAME || null,
    head_sha: process.env.GITHUB_SHA || null,
    run_id: runId,
    run_attempt: Number(process.env.GITHUB_RUN_ATTEMPT || 0) || null,
    run_url: repository && runId ? `https://github.com/${repository}/actions/runs/${runId}` : null,
    build_seconds: buildSeconds,
    dist_path: normalizePath(path.relative(rootDir, distDir) || "."),
    rows: rows.map((row) => ({
      label: row.label,
      relative_path: row.relativePath,
      file_count: row.fileCount,
      bytes: row.bytes,
      target_mib: row.targetMiB,
      hard_mib: row.hardMiB,
      status: row.status,
    })),
  };
}

function writeHistoryRecord(historyPath, record, previousRecords) {
  if (!historyPath) {
    return;
  }

  mkdirSync(path.dirname(historyPath), { recursive: true });
  const nextRecords = [...previousRecords, record].slice(-historyLimit);
  writeFileSync(historyPath, `${nextRecords.map((item) => JSON.stringify(item)).join("\n")}\n`, "utf8");
}

function buildTrendRows(rows, previousRecord) {
  if (!previousRecord?.rows) {
    return [];
  }

  const previousByLabel = new Map(previousRecord.rows.map((row) => [row.label, row]));
  return rows
    .map((row) => {
      const previous = previousByLabel.get(row.label);
      if (!previous) {
        return null;
      }
      return {
        label: row.label,
        previousBytes: previous.bytes,
        currentBytes: row.bytes,
        deltaBytes: row.bytes - previous.bytes,
      };
    })
    .filter(Boolean);
}

function markdownRows(rows, trendRows = []) {
  const trendByLabel = new Map(trendRows.map((row) => [row.label, row.deltaBytes]));
  const lines = [
    "項目 | 檔案數 | 目前大小 | target | hard limit | 趨勢 | 狀態",
    "--- | ---: | ---: | ---: | ---: | ---: | ---",
  ];
  for (const row of rows) {
    const delta = trendByLabel.has(row.label) ? formatSignedMiB(trendByLabel.get(row.label)) : "-";
    lines.push(
      `${row.label} | ${row.fileCount.toLocaleString("zh-TW")} | ${formatMiB(row.bytes)} | ${row.targetMiB} MiB | ${row.hardMiB} MiB | ${delta} | ${row.status}`,
    );
  }
  return lines;
}

function printRows(rows, trendRows, previousRecord, historyPath) {
  console.log("GitHub Pages payload 稽核");
  console.log("");
  console.log(`目錄：${normalizePath(path.relative(rootDir, distDir) || ".")}`);
  console.log(`模式：${enforceTargets ? "strict，超過 target 會失敗" : "baseline，超過 hard limit 才失敗"}`);
  if (buildSeconds !== null) {
    console.log(`建置時間：${formatDuration(buildSeconds)}`);
  }
  if (historyPath) {
    console.log(`歷史紀錄：${normalizePath(path.relative(rootDir, historyPath) || ".")}，保留最近 ${historyLimit} 筆`);
  }
  console.log("");
  for (const line of markdownRows(rows, trendRows)) {
    console.log(line);
  }
  if (previousRecord) {
    console.log("");
    console.log(`上一筆歷史紀錄：${previousRecord.recorded_at_iso || "未知時間"}`);
  }
}

function appendStepSummary(rows, trendRows, previousRecord, historyPath) {
  if (!githubStepSummaryPath) {
    return;
  }

  const lines = [
    "## GitHub Pages Payload",
    "",
    `- 模式：${enforceTargets ? "strict" : "baseline"}`,
    `- 目錄：${normalizePath(path.relative(rootDir, distDir) || ".")}`,
  ];
  if (buildSeconds !== null) {
    lines.push(`- 建置時間：${formatDuration(buildSeconds)}`);
  }
  if (historyPath) {
    lines.push(`- 歷史紀錄：${normalizePath(path.relative(rootDir, historyPath) || ".")}，保留最近 ${historyLimit} 筆`);
  }
  if (previousRecord?.recorded_at_iso) {
    lines.push(`- 趨勢比較：上一筆 ${previousRecord.recorded_at_iso}`);
  }
  lines.push("", ...markdownRows(rows, trendRows), "");
  appendFileSync(githubStepSummaryPath, `${lines.join("\n")}\n`, "utf8");
}

if (!existsSync(distDir)) {
  console.error("找不到 dist/。請先執行 npm run build，再執行 payload 稽核。");
  process.exit(1);
}

const issues = [];
const historyPath = resolveHistoryPath(historyPathArg);
const previousRecords = readHistoryRecords(historyPath);
const previousRecord = previousRecords.at(-1) || null;
const rows = payloadBudgets.map((budget) => {
  const directory = path.join(distDir, budget.relativePath);
  const measurement = measureDirectory(directory);
  const targetBytes = budget.targetMiB * MiB;
  const hardBytes = budget.hardMiB * MiB;
  const overTarget = measurement.bytes > targetBytes;
  const overHard = measurement.bytes > hardBytes;
  const status = overHard
    ? "超過 hard limit"
    : overTarget
      ? "超過 target"
      : "通過";

  if (overHard || (enforceTargets && overTarget)) {
    issues.push(`${budget.label} ${formatMiB(measurement.bytes)} 超過 ${overHard ? "hard limit" : "target"}：${budget.reason}`);
  }

  return {
    ...budget,
    ...measurement,
    status,
  };
});
const trendRows = buildTrendRows(rows, previousRecord);
const historyRecord = buildHistoryRecord(rows);

printRows(rows, trendRows, previousRecord, historyPath);
appendStepSummary(rows, trendRows, previousRecord, historyPath);
writeHistoryRecord(historyPath, historyRecord, previousRecords);

const warnings = rows.filter((row) => row.bytes > row.targetMiB * MiB && row.bytes <= row.hardMiB * MiB);
if (warnings.length > 0) {
  console.log("");
  console.log("瘦身提醒：");
  for (const warning of warnings) {
    console.log(`- ${warning.label} 仍高於 target：${warning.reason}`);
  }
}

if (issues.length > 0) {
  console.error("");
  console.error(`Pages payload 稽核失敗：${issues.length} 個問題`);
  for (const issue of issues) {
    console.error(`- ${issue}`);
  }
  process.exit(1);
}

console.log("");
console.log("Pages payload 稽核完成。");
