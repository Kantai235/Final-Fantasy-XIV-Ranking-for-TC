import { brotliCompressSync, constants as zlibConstants, gzipSync } from "node:zlib";
import { existsSync, readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";
import { fileURLToPath } from "node:url";

const ProjectRoot = fileURLToPath(new URL("../", import.meta.url));
const DistPath = join(ProjectRoot, "dist");
const GithubPagesSoftLimitBytes = 100 * 1024 ** 3;
const CacheHitRatios = [0, 0.9, 0.95, 0.98, 0.99];
const FullCompression = process.argv.includes("--full-compression");
const CompressionSizeCache = new Map();

function listFiles(directory) {
  const entries = [];
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    const fullPath = join(directory, entry.name);
    if (entry.isDirectory()) {
      entries.push(...listFiles(fullPath));
    } else if (entry.isFile()) {
      entries.push(fullPath);
    }
  }
  return entries;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) {
    return "-";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unitIndex = 0;
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024;
    unitIndex += 1;
  }
  return `${value.toFixed(value >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatInteger(value) {
  return Math.floor(value).toLocaleString("zh-TW");
}

function readDistFile(relativePath) {
  const fullPath = join(DistPath, relativePath);
  if (!existsSync(fullPath)) {
    return null;
  }
  return readFileSync(fullPath);
}

function fileBytes(relativePath) {
  return readDistFile(relativePath)?.byteLength || 0;
}

function brotliEstimate(content) {
  return brotliCompressSync(content, {
    params: {
      [zlibConstants.BROTLI_PARAM_QUALITY]: 5,
    },
  });
}

function compressedBytes(relativePath, algorithm, compressor) {
  const cacheKey = `${algorithm}:${relativePath}`;
  if (CompressionSizeCache.has(cacheKey)) {
    return CompressionSizeCache.get(cacheKey);
  }

  const content = readDistFile(relativePath);
  const size = content ? compressor(content).byteLength : 0;
  CompressionSizeCache.set(cacheKey, size);
  return size;
}

function filesTotal(files, sizeReader) {
  return files.reduce((sum, file) => sum + sizeReader(file), 0);
}

function allRelativeFilesUnder(relativeDirectory) {
  const directory = join(DistPath, relativeDirectory);
  if (!existsSync(directory)) {
    return [];
  }
  return listFiles(directory).map((file) => relative(DistPath, file).split(sep).join("/"));
}

function percentileFile(files, ratio) {
  if (files.length === 0) {
    return null;
  }
  const sorted = [...files].sort((a, b) => fileBytes(a) - fileBytes(b));
  const index = Math.min(sorted.length - 1, Math.max(0, Math.ceil(sorted.length * ratio) - 1));
  return sorted[index];
}

function scenarioCapacity(bytes, cacheHitRatio) {
  const originMissRatio = Math.max(1 - cacheHitRatio, 0.000001);
  return GithubPagesSoftLimitBytes / (bytes * originMissRatio);
}

function printScenarioTable(scenarios) {
  console.log("Cloudflare / GitHub Pages 流量估算");
  console.log("");
  console.log(`資料來源：${DistPath}`);
  console.log(`GitHub Pages 軟性流量上限估算：${formatBytes(GithubPagesSoftLimitBytes)} / 月`);
  if (!FullCompression) {
    console.log("提示：完整 dist 預設只列未壓縮大小；需要壓縮完整輸出時可加上 --full-compression。");
  }
  console.log("");
  console.log("情境 | 未壓縮 | gzip | brotli");
  console.log("--- | ---: | ---: | ---:");
  for (const scenario of scenarios) {
    console.log(`${scenario.name} | ${formatBytes(scenario.rawBytes)} | ${formatBytes(scenario.gzipBytes)} | ${formatBytes(scenario.brotliBytes)}`);
  }
  console.log("");

  for (const scenario of scenarios.filter((item) => item.includeCapacity !== false)) {
    console.log(`${scenario.name} 可承載量（以 gzip 大小估算 GitHub origin 流量）：`);
    for (const hitRatio of CacheHitRatios) {
      const label = hitRatio === 0 ? "沒有 CDN HIT" : `Cloudflare HIT ${(hitRatio * 100).toFixed(0)}%`;
      console.log(`- ${label}：約 ${formatInteger(scenarioCapacity(scenario.gzipBytes, hitRatio))} 次 / 月`);
    }
    console.log("");
  }
}

if (!existsSync(DistPath)) {
  console.error("找不到 dist/。請先執行 npm run build，再重新估算 Cloudflare 承載量。");
  process.exit(1);
}

const allFiles = listFiles(DistPath);
const allRelativeFiles = allFiles.map((file) => relative(DistPath, file).split(sep).join("/"));
const assetFiles = allRelativeFilesUnder("assets");
const iconFiles = allRelativeFilesUnder("icons/jobs");
const siteIconFiles = [
  "favicon.svg",
  "favicon.ico",
  "favicon-16x16.png",
  "favicon-32x32.png",
  "apple-touch-icon.png",
  "site.webmanifest",
  ...allRelativeFilesUnder("icons/site"),
];
const appShellFiles = ["index.html", ...assetFiles, ...iconFiles, ...siteIconFiles];
const userFiles = allRelativeFilesUnder("data/users").filter((file) => file !== "data/users/index.json");
const userIndexFile = existsSync(join(DistPath, "data/users/index.json")) ? "data/users/index.json" : null;
const medianUserFile = percentileFile(userFiles, 0.5);
const p95UserFile = percentileFile(userFiles, 0.95);

function buildScenario(name, files) {
  return {
    name,
    rawBytes: filesTotal(files, fileBytes),
    gzipBytes: filesTotal(files, (file) => compressedBytes(file, "gzip", gzipSync)),
    brotliBytes: filesTotal(files, (file) => compressedBytes(file, "brotli", brotliEstimate)),
  };
}

const scenarios = [
  buildScenario("排行榜首屏", [...appShellFiles, "data/encounters.json", "data/rankings/savage_m4s.json"]),
  buildScenario("全服統計首屏", [...appShellFiles, "data/encounters.json", "data/global_stats.json"]),
  ...(userIndexFile && userFiles.length > 0
    ? [
        buildScenario("個人成績單首屏（artifact 內含中位數使用者檔）", [
          ...appShellFiles,
          "data/encounters.json",
          userIndexFile,
          medianUserFile,
        ].filter(Boolean)),
        buildScenario("個人成績單首屏（artifact 內含前 5% 大使用者檔）", [
          ...appShellFiles,
          "data/encounters.json",
          userIndexFile,
          p95UserFile,
        ].filter(Boolean)),
      ]
    : [
        buildScenario("個人成績單首屏（主站殼層與搜尋索引；users repo 外部載入）", [
          ...appShellFiles,
          "data/encounters.json",
          userIndexFile,
        ].filter(Boolean)),
      ]),
  {
    name: "完整 dist 冷爬一次",
    rawBytes: allFiles.reduce((sum, file) => sum + statSync(file).size, 0),
    gzipBytes: FullCompression ? filesTotal(allRelativeFiles, (file) => compressedBytes(file, "gzip", gzipSync)) : Number.NaN,
    brotliBytes: FullCompression ? filesTotal(allRelativeFiles, (file) => compressedBytes(file, "brotli", brotliEstimate)) : Number.NaN,
    includeCapacity: false,
  },
];

printScenarioTable(scenarios);
