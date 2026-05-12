import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const srcDir = path.join(rootDir, "src");
const publicDataDir = path.join(rootDir, "public", "data");

const issues = [];

function reportIssue(message) {
  issues.push(message);
}

async function readText(filePath) {
  return readFile(filePath, "utf8");
}

async function readJson(filePath, label) {
  try {
    return JSON.parse(await readText(filePath));
  } catch (error) {
    reportIssue(`${label} 不是可讀取的 JSON：${error.message}`);
    return null;
  }
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

function assert(condition, message) {
  if (!condition) {
    reportIssue(message);
  }
}

function addImportedBindings(source, bindings) {
  const namedImportPattern = /import\s*\{([\s\S]*?)\}\s*from\s*["'][^"']+["']/g;
  for (const match of source.matchAll(namedImportPattern)) {
    for (const rawPart of match[1].split(",")) {
      const part = rawPart.trim();
      if (!part) {
        continue;
      }
      const aliasMatch = part.match(/\s+as\s+(.+)$/);
      bindings.add((aliasMatch?.[1] || part).trim());
    }
  }

  const defaultImportPattern = /import\s+([^\s{},*][^\s{},]*)\s+from\s*["'][^"']+["']/g;
  for (const match of source.matchAll(defaultImportPattern)) {
    bindings.add(match[1].trim());
  }

  const namespaceImportPattern = /import\s+\*\s+as\s+([^\s]+)\s+from\s*["'][^"']+["']/g;
  for (const match of source.matchAll(namespaceImportPattern)) {
    bindings.add(match[1].trim());
  }
}

function addDeclaredBindings(source, bindings) {
  const declarationPattern = /^\s*(?:(?:async\s+)?function|const|let|var|class)\s+([^\s=({]+)/gmu;
  for (const match of source.matchAll(declarationPattern)) {
    bindings.add(match[1].trim());
  }

  const objectDestructurePattern = /^\s*(?:const|let|var)\s*\{([\s\S]*?)\}\s*=/gmu;
  for (const match of source.matchAll(objectDestructurePattern)) {
    for (const rawPart of match[1].split(",")) {
      const part = rawPart.trim();
      if (!part || part.startsWith("...")) {
        continue;
      }
      const withoutDefault = part.split("=")[0].trim();
      const alias = withoutDefault.includes(":") ? withoutDefault.split(":").at(-1).trim() : withoutDefault;
      if (alias) {
        bindings.add(alias);
      }
    }
  }
}

function findMatchingBrace(source, openIndex) {
  let depth = 0;
  let inString = "";
  let escaped = false;

  for (let index = openIndex; index < source.length; index += 1) {
    const char = source[index];
    const previous = source[index - 1];

    if (inString) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === inString && !(inString === "`" && previous === "$")) {
        inString = "";
      }
      continue;
    }

    if (char === "\"" || char === "'" || char === "`") {
      inString = char;
      continue;
    }

    if (char === "{") {
      depth += 1;
    } else if (char === "}") {
      depth -= 1;
      if (depth === 0) {
        return index;
      }
    }
  }

  return -1;
}

function extractUseRankingAppReturnBlock(source) {
  const returnIndex = source.lastIndexOf("\n  return {");
  if (returnIndex === -1) {
    reportIssue("useRankingApp.js 找不到 useRankingApp() 的 return 物件");
    return "";
  }

  const openIndex = source.indexOf("{", returnIndex);
  const closeIndex = findMatchingBrace(source, openIndex);
  if (closeIndex === -1) {
    reportIssue("useRankingApp.js 的 return 物件大括號不完整");
    return "";
  }

  return source.slice(openIndex + 1, closeIndex);
}

async function validateUseRankingAppReturnBindings() {
  const filePath = path.join(srcDir, "composables", "useRankingApp.js");
  const source = await readText(filePath);
  const bindings = new Set();
  addImportedBindings(source, bindings);
  addDeclaredBindings(source, bindings);

  const returnBlock = extractUseRankingAppReturnBlock(source);
  const shorthandNames = [];
  for (const line of returnBlock.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.includes(":") || trimmed.startsWith("//")) {
      continue;
    }
    const match = trimmed.match(/^([\p{L}\p{N}_$\u200c\u200d]+),?$/u);
    if (match) {
      shorthandNames.push(match[1]);
    }
  }

  for (const name of shorthandNames) {
    if (!bindings.has(name)) {
      reportIssue(`useRankingApp() return 了未定義的資料或函式：${name}`);
    }
  }
}

async function validateFrontendFetchBoundary() {
  const allowedFetchFiles = new Set([
    normalizePath(path.join(srcDir, "utils", "fetchJson.js")),
    normalizePath(path.join(srcDir, "utils", "userData.js")),
  ]);
  const files = [
    "analytics.js",
    "main.js",
    "composables/useRankingApp.js",
    "domain/jobs.js",
    "utils/fetchJson.js",
    "utils/publicData.js",
    "utils/urlState.js",
    "utils/userData.js",
    "utils/viewHelpers.js",
  ];

  for (const relativePath of files) {
    const filePath = path.join(srcDir, relativePath);
    const source = await readText(filePath);
    if (source.includes("fetch(") && !allowedFetchFiles.has(normalizePath(filePath))) {
      reportIssue(`${relativePath} 直接呼叫 fetch，前端資料讀取應集中在 utils/fetchJson.js 或 utils/userData.js`);
    }
    if (/fflogs\.com\/api|api\/v2|graphql/i.test(source)) {
      reportIssue(`${relativePath} 看起來直接碰到 FFLogs API，前端不得繞過資料管線`);
    }
  }
}

async function validatePublicDataForFrontend() {
  const encounters = await readJson(path.join(publicDataDir, "encounters.json"), "public/data/encounters.json");
  const globalStats = await readJson(path.join(publicDataDir, "global_stats.json"), "public/data/global_stats.json");
  const userIndex = await readJson(path.join(publicDataDir, "users", "index.json"), "public/data/users/index.json");

  assert(Array.isArray(encounters) && encounters.length > 0, "public/data/encounters.json 必須提供前端副本清單");
  assert(globalStats?.schema_version === 1, "public/data/global_stats.json schema_version 必須是 1");
  assert(Array.isArray(globalStats?.server_stats), "public/data/global_stats.json 必須包含 server_stats");
  assert(Array.isArray(globalStats?.role_stats), "public/data/global_stats.json 必須包含 role_stats");
  assert(Array.isArray(globalStats?.job_stats), "public/data/global_stats.json 必須包含 job_stats");
  assert(Array.isArray(globalStats?.damage_stats), "public/data/global_stats.json 必須包含 damage_stats");
  assert(Array.isArray(globalStats?.encounters), "public/data/global_stats.json 必須包含 encounters");
  assert(Array.isArray(userIndex?.users) && userIndex.users.length > 0, "public/data/users/index.json 必須包含 users");
  assert(userIndex?.total_users === userIndex?.users?.length, "public/data/users/index.json total_users 必須等於 users 長度");

  for (const encounter of encounters || []) {
    const key = encounter?.key;
    const dataPath = encounter?.data_path || `data/rankings/${key}.json`;
    const publicRankingPath = path.join(publicDataDir, dataPath.replace(/^data\//, ""));
    assert(Boolean(key), "public/data/encounters.json 的每筆副本都必須有 key");
    assert(existsSync(publicRankingPath), `${key} 的公開排行榜檔案不存在：${dataPath}`);
    const ranking = await readJson(publicRankingPath, `${key} 公開排行榜`);
    assert(ranking?.schema_version === 1, `${key} 公開排行榜 schema_version 必須是 1`);
    assert(Array.isArray(ranking?.ranking_entries), `${key} 公開排行榜必須包含 ranking_entries`);
    assert(!ranking?.reports && !ranking?.report_shards, `${key} 公開排行榜不可包含 reports 或 report_shards`);
  }

  for (const user of (userIndex?.users || []).slice(0, 20)) {
    const userPath = path.join(rootDir, "public", user.file_path || "");
    assert(existsSync(userPath), `使用者索引指向不存在的檔案：${user.file_path}`);
    const userData = await readJson(userPath, `使用者檔案 ${user.file_path}`);
    assert(userData?.schema_version === 1, `${user.file_path} schema_version 必須是 1`);
    assert(Array.isArray(userData?.servers), `${user.file_path} 必須包含 servers`);
    assert(Array.isArray(userData?.encounters), `${user.file_path} 必須包含 encounters`);
    assert(Array.isArray(userData?.frequent_teammates), `${user.file_path} 必須包含 frequent_teammates`);
    assert(userData?.summary && typeof userData.summary === "object", `${user.file_path} 必須包含 summary`);
  }
}

async function main() {
  await validateUseRankingAppReturnBindings();
  await validateFrontendFetchBoundary();
  await validatePublicDataForFrontend();

  if (issues.length > 0) {
    console.error(`前端資料契約測試失敗：${issues.length} 個問題`);
    for (const issue of issues) {
      console.error(`- ${issue}`);
    }
    process.exit(1);
  }

  console.log("frontend data contract test passed.");
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
