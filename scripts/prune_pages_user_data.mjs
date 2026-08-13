import { existsSync, mkdirSync, readdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
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
// postbuild 也可能需要它產生玩家分享頁與 OG 圖；提前刪 public/data 會讓本機 SEO 抽查產物缺漏。
// users/index.json 是所有訪客共用的搜尋入口，部署時刻意留在主站 /data/users/index.json，
// 讓 Cloudflare/GitHub Pages 快取承接高頻請求；個別玩家 JSON 仍由 users 專用 repo 提供。
const userDataPaths = [
  "data/user-entry-details",
  "data/all/users",
  "data/all/user-entry-details",
  "og/users",
];

let removedCount = 0;
const usersDir = path.join(distDir, "data", "users");
if (existsSync(usersDir)) {
  const entries = readdirSync(usersDir, { withFileTypes: true });
  const removedUserFileCount = entries.filter((entry) => entry.name !== "index.json").length;

  if (removedUserFileCount > 0) {
    // 逐檔 rmSync 在 Windows 本機完整 build 的上萬個玩家檔上極慢，且曾觸發 Node/libuv
    // 非正常結束。先把唯一要保留的共用索引讀入記憶體，再以單一受限目錄操作重建，
    // Linux workflow 與本機維護都可維持相同的 artifact 契約。
    const indexPath = path.join(usersDir, "index.json");
    const indexPayload = existsSync(indexPath) ? readFileSync(indexPath) : null;
    if (!isInsidePath(distDir, usersDir)) {
      throw new Error(`拒絕清理 artifact 目錄外的路徑：${usersDir}`);
    }
    rmSync(usersDir, { recursive: true, force: true });
    if (indexPayload) {
      mkdirSync(usersDir, { recursive: true });
      writeFileSync(indexPath, indexPayload);
    }
    removedCount += removedUserFileCount;
    console.log(`已從 Pages artifact 移除 ${removedUserFileCount} 個個別玩家成績單檔，保留 data/users/index.json。`);
  }
}

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

const userRouteDir = path.join(distDir, "user");
if (existsSync(userRouteDir)) {
  for (const entry of readdirSync(userRouteDir, { withFileTypes: true })) {
    if (entry.name === "index.html") {
      continue;
    }

    const targetPath = path.join(userRouteDir, entry.name);
    if (!isInsidePath(userRouteDir, targetPath)) {
      throw new Error(`拒絕清理 user route 目錄外的路徑：${targetPath}`);
    }

    rmSync(targetPath, { recursive: true, force: true });
    removedCount += 1;
  }

  console.log("已從 Pages artifact 移除逐玩家靜態分享頁，保留 /user route 入口。");
}

const sitemapPath = path.join(distDir, "sitemap.xml");
if (existsSync(sitemapPath)) {
  const sitemap = readFileSync(sitemapPath, "utf8");
  const prunedSitemap = sitemap.replace(
    /\s*<url><loc>https?:\/\/[^<]+\/user\/[^<]+<\/loc><\/url>/g,
    "",
  );
  if (prunedSitemap !== sitemap) {
    writeFileSync(sitemapPath, prunedSitemap, "utf8");
    console.log("已從 sitemap.xml 移除逐玩家靜態分享 URL。");
  }
}

if (removedCount === 0) {
  console.log("Pages artifact 沒有個人成績單部署資料需要移除。");
} else {
  console.log(
    "個別玩家成績單 JSON、逐玩家分享頁與玩家 OG 圖由專用資料來源或前端 SPA 補回；主站 artifact 只保留 route 層級入口、共用使用者索引與非使用者資料。",
  );
}
