import { existsSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const args = new Set(process.argv.slice(2));
const enforceTargets = args.has("--enforce-targets") || process.env.PAGES_PAYLOAD_ENFORCE_TARGETS === "true";
const distDir = path.resolve(rootDir, process.env.PAGES_PAYLOAD_DIST || "dist");

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
    targetMiB: 120,
    hardMiB: Number(process.env.PAGES_PAYLOAD_ALL_HARD_MIB || 950),
    reason: "public/data/all 應維持 hidden delta，不可重新膨脹成完整公開資料複本。",
  },
  {
    label: "個人成績單資料",
    relativePath: "data/users",
    targetMiB: 500,
    hardMiB: Number(process.env.PAGES_PAYLOAD_USERS_HARD_MIB || 800),
    reason: "個人成績單是使用者資料最大來源，report_variants 延遲載入後應明顯下降。",
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

function formatMiB(bytes) {
  return `${(bytes / MiB).toFixed(1)} MiB`;
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

function printRows(rows) {
  console.log("GitHub Pages payload 稽核");
  console.log("");
  console.log(`目錄：${normalizePath(path.relative(rootDir, distDir) || ".")}`);
  console.log(`模式：${enforceTargets ? "strict，超過 target 會失敗" : "baseline，超過 hard limit 才失敗"}`);
  console.log("");
  console.log("項目 | 檔案數 | 目前大小 | target | hard limit | 狀態");
  console.log("--- | ---: | ---: | ---: | ---: | ---");
  for (const row of rows) {
    console.log(
      `${row.label} | ${row.fileCount.toLocaleString("zh-TW")} | ${formatMiB(row.bytes)} | ${row.targetMiB} MiB | ${row.hardMiB} MiB | ${row.status}`,
    );
  }
}

if (!existsSync(distDir)) {
  console.error("找不到 dist/。請先執行 npm run build，再執行 payload 稽核。");
  process.exit(1);
}

const issues = [];
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

printRows(rows);

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
