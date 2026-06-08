import { existsSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const rawArgs = process.argv.slice(2);

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

const distDir = path.resolve(rootDir, readOption("--dist") || process.env.PAGES_PAYLOAD_DIST || "dist");

function canonicalPath(targetPath) {
  const resolved = path.resolve(targetPath).replace(/[\\/]+$/, "");
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

function isSamePath(left, right) {
  return canonicalPath(left) === canonicalPath(right);
}

function isInsidePath(parentPath, childPath) {
  const relativePath = path.relative(parentPath, childPath);
  return relativePath === "" || (!relativePath.startsWith("..") && !path.isAbsolute(relativePath));
}

const protectedSourceDirs = [
  rootDir,
  path.join(rootDir, "data"),
  path.join(rootDir, "public"),
  path.join(rootDir, "public", "data"),
];

if (protectedSourceDirs.some((protectedPath) => isSamePath(distDir, protectedPath))) {
  throw new Error(
    `拒絕清理來源資料目錄：${path.relative(rootDir, distDir) || "."}。請只對 dist/ 或部署 artifact 目錄執行。`,
  );
}

// 只能清理 dist/ 內的部署 artifact。public/data/users 仍是本 repo 的資料契約來源，
// postbuild 也需要它產生玩家分享頁與 OG 圖；提前刪 public/data 會讓 SEO 產物缺漏。
const userDataPaths = [
  "data/users",
  "data/user-entry-details",
  "data/all/users",
  "data/all/user-entry-details",
];

let removedCount = 0;
for (const relativePath of userDataPaths) {
  const targetPath = path.join(distDir, relativePath);
  if (!isInsidePath(distDir, targetPath)) {
    throw new Error(`拒絕清理 artifact 目錄外的路徑：${targetPath}`);
  }

  if (!existsSync(targetPath)) {
    continue;
  }

  rmSync(targetPath, { recursive: true, force: true });
  removedCount += 1;
  console.log(`已從 Pages artifact 移除個人成績單資料：${path.relative(rootDir, targetPath)}`);
}

if (removedCount === 0) {
  console.log("Pages artifact 沒有個人成績單資料需要移除。");
} else {
  console.log("個人成績單 JSON 由專用 users repo 提供；主站 artifact 只保留分享頁、OG 圖與非使用者資料。");
}
