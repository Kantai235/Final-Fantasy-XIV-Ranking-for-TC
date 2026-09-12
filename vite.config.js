import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { readFileSync } from "node:fs";
import { 版本進度資料插件 } from "./scripts/build_version_progress.mjs";

const siteConfig = JSON.parse(readFileSync(new URL("./config/site.json", import.meta.url), "utf8"));
const allowedHosts = Array.isArray(siteConfig.allowed_hosts) ? siteConfig.allowed_hosts : [];

export default defineConfig({
  base: siteConfig.base_path || "./",
  plugins: [vue(), 版本進度資料插件()],
  server: {
    allowedHosts,
  },
  preview: {
    allowedHosts,
  },
});
