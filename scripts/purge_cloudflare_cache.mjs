import { appendFileSync, existsSync, readFileSync } from "node:fs";

const CloudflareApiBase = "https://api.cloudflare.com/client/v4";
const Args = new Set(process.argv.slice(2));
const DryRun = Args.has("--dry-run");
const PurgeEverything = Args.has("--everything");
const Summary = Args.has("--summary") || process.env.CLOUDFLARE_PURGE_SUMMARY === "true";
const GithubStepSummaryPath = process.env.GITHUB_STEP_SUMMARY || "";

loadLocalEnv();

const SiteConfig = JSON.parse(readFileSync(new URL("../config/site.json", import.meta.url), "utf8"));
const SiteUrl = new URL(SiteConfig.site_url || "https://ranking.init.engineer/");
const SiteHostname = normalizeHostname(process.env.CLOUDFLARE_HOSTNAME || SiteUrl.hostname);
const SiteOrigin = `${SiteUrl.protocol}//${SiteHostname}`;
const ZoneId = process.env.CLOUDFLARE_ZONE_ID || "";
const ApiToken =
  process.env.CLOUDFLARE_PURGE_API_TOKEN || process.env.CLOUDFLARE_API_TOKEN || process.env.CLOUDFLARE_RULES_API_TOKEN || "";

const PrefixesToPurge = [
  `${SiteHostname}/data`,
  `${SiteHostname}/stats`,
  `${SiteHostname}/user`,
  `${SiteHostname}/compare`,
  `${SiteHostname}/teams`,
  `${SiteHostname}/servers`,
  `${SiteHostname}/jobs`,
  `${SiteHostname}/activity`,
  `${SiteHostname}/honey-fans`,
  `${SiteHostname}/og`,
];

const FilesToPurge = [
  `${SiteOrigin}/`,
  `${SiteOrigin}/index.html`,
  `${SiteOrigin}/404.html`,
  `${SiteOrigin}/sitemap.xml`,
  `${SiteOrigin}/robots.txt`,
  `${SiteOrigin}/og-image.png`,
  `${SiteOrigin}/favicon.svg`,
  `${SiteOrigin}/favicon.ico`,
  `${SiteOrigin}/favicon-16x16.png`,
  `${SiteOrigin}/favicon-32x32.png`,
  `${SiteOrigin}/apple-touch-icon.png`,
  `${SiteOrigin}/site.webmanifest`,
];

function loadLocalEnv() {
  const envPath = new URL("../.env", import.meta.url);
  if (!existsSync(envPath)) {
    return;
  }

  const lines = readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const separatorIndex = trimmed.indexOf("=");
    if (separatorIndex <= 0) {
      continue;
    }

    const key = trimmed.slice(0, separatorIndex).trim();
    const rawValue = trimmed.slice(separatorIndex + 1).trim();
    if (!key || Object.hasOwn(process.env, key)) {
      continue;
    }

    process.env[key] = rawValue.replace(/^(['"])(.*)\1$/, "$2");
  }
}

function normalizeHostname(hostname) {
  const value = String(hostname || "").trim().toLowerCase();
  if (!/^[a-z0-9.-]+$/.test(value)) {
    throw new Error(`CLOUDFLARE_HOSTNAME 只能是一般網域名稱，目前取得：${hostname}`);
  }
  return value;
}

async function cloudflarePurge(payload) {
  const response = await fetch(`${CloudflareApiBase}/zones/${ZoneId}/purge_cache`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${ApiToken}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const bodyText = await response.text();
  const body = bodyText ? JSON.parse(bodyText) : null;

  if (!response.ok || body?.success === false) {
    const errors = Array.isArray(body?.errors) ? body.errors.map((error) => error.message).join("; ") : bodyText;
    throw new Error(`Cloudflare purge 失敗：HTTP ${response.status} ${errors || ""}`.trim());
  }
}

function formatPurgeSummary() {
  const lines = [
    "## Cloudflare Purge 範圍",
    "",
    `- Hostname：${SiteHostname}`,
    `- 模式：${PurgeEverything ? "purge everything" : "scoped prefix + file purge"}`,
    "",
    "類型 | 數量 | 內容",
    "--- | ---: | ---",
  ];

  if (PurgeEverything) {
    lines.push("全站 | 1 | `purge_everything=true`");
    return `${lines.join("\n")}\n`;
  }

  lines.push(`Prefix | ${PrefixesToPurge.length} | ${PrefixesToPurge.map((prefix) => `\`${prefix}\``).join("<br>")}`);
  lines.push(`File | ${FilesToPurge.length} | ${FilesToPurge.map((file) => `\`${file}\``).join("<br>")}`);
  return `${lines.join("\n")}\n`;
}

function printPurgeSummary() {
  if (!Summary) {
    return;
  }

  const summary = formatPurgeSummary();
  console.log(summary.trimEnd());
  if (GithubStepSummaryPath) {
    appendFileSync(GithubStepSummaryPath, summary, "utf8");
  }
}

async function main() {
  if (PurgeEverything) {
    const payload = { purge_everything: true };
    printPurgeSummary();
    if (DryRun) {
      console.log(JSON.stringify(payload, null, 2));
      return;
    }
    await cloudflarePurge(payload);
    console.log("已清除 Cloudflare 全站快取。");
    return;
  }

  const payloads = [
    { prefixes: PrefixesToPurge },
    { files: FilesToPurge },
  ];

  printPurgeSummary();

  if (DryRun) {
    console.log(JSON.stringify({ hostname: SiteHostname, purge_requests: payloads }, null, 2));
    return;
  }

  if (!ZoneId || !ApiToken) {
    console.log("未設定 CLOUDFLARE_ZONE_ID 或 CLOUDFLARE_API_TOKEN，略過 Cloudflare 快取清除。");
    return;
  }

  for (const payload of payloads) {
    await cloudflarePurge(payload);
  }
  console.log(`已清除 ${SiteHostname} 的 Cloudflare prefix 與核心檔案快取。`);
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
