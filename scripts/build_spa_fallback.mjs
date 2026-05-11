import { copyFileSync, existsSync } from "node:fs";
import { join } from "node:path";

const distDir = "dist";
const indexPath = join(distDir, "index.html");
const fallbackPath = join(distDir, "404.html");

if (!existsSync(indexPath)) {
  throw new Error("找不到 dist/index.html，請先完成 Vite build。");
}

// GitHub Pages 對 /stats、/user 這類 History API 路徑沒有伺服器端 rewrite。
// 複製一份 404.html 可讓靜態主機把未知路徑交回同一個 Vue SPA 接手解析。
copyFileSync(indexPath, fallbackPath);
console.log("Built SPA fallback at dist/404.html.");
