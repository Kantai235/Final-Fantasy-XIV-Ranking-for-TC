import { existsSync, readFileSync } from "node:fs";

const CloudflareApiBase = "https://api.cloudflare.com/client/v4";
const CacheRulesPhase = "http_request_cache_settings";
const FirewallCustomPhase = "http_request_firewall_custom";
const RateLimitPhase = "http_ratelimit";
const ManagedRuleRefPrefix = "ffxiv_tc_";
const ManagedRuleDescriptionPrefix = "FFXIV TC - ";

const Args = new Set(process.argv.slice(2));
const DryRun = Args.has("--dry-run");
const SkipRateLimit = Args.has("--skip-rate-limit");
const AllowTransientFailure = Args.has("--allow-transient-failure");

loadLocalEnv();

const SiteConfig = JSON.parse(readFileSync(new URL("../config/site.json", import.meta.url), "utf8"));
const SiteHostname = normalizeHostname(
  readOptionalEnv("CLOUDFLARE_HOSTNAME") || new URL(SiteConfig.site_url || "https://ranking.init.engineer/").hostname,
);
const ZoneId = process.env.CLOUDFLARE_ZONE_ID || "";
const ApiToken = process.env.CLOUDFLARE_RULES_API_TOKEN || process.env.CLOUDFLARE_API_TOKEN || "";
const CloudflareMaxAttempts = readPositiveIntegerEnv("CLOUDFLARE_RULES_API_MAX_ATTEMPTS", 3);
const CloudflareRetryBaseDelayMs = readPositiveIntegerEnv("CLOUDFLARE_RULES_API_RETRY_BASE_MS", 750);

const DataEdgeTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_DATA_EDGE_TTL_SECONDS", 7200);
const DataBrowserTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_DATA_BROWSER_TTL_SECONDS", 300);
const HtmlEdgeTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_HTML_EDGE_TTL_SECONDS", 7200);
const HtmlBrowserTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_HTML_BROWSER_TTL_SECONDS", 300);
const MediaEdgeTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_MEDIA_EDGE_TTL_SECONDS", 21600);
const MediaBrowserTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_MEDIA_BROWSER_TTL_SECONDS", 3600);
const StaticEdgeTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_STATIC_EDGE_TTL_SECONDS", 31536000);
const StaticBrowserTtlSeconds = readPositiveIntegerEnv("CLOUDFLARE_STATIC_BROWSER_TTL_SECONDS", 31536000);
const RateLimitRequestsPer10Seconds = readPositiveIntegerEnv("CLOUDFLARE_RATE_LIMIT_REQUESTS_PER_10S", 240);

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

function readOptionalEnv(name) {
  const value = String(process.env[name] || "").trim();
  return value || "";
}

function normalizeHostname(hostname) {
  const value = String(hostname || "").trim().toLowerCase();
  if (!/^[a-z0-9.-]+$/.test(value)) {
    throw new Error(`CLOUDFLARE_HOSTNAME 只能是一般網域名稱，目前取得：${hostname}`);
  }
  return value;
}

function readPositiveIntegerEnv(name, fallback) {
  const rawValue = process.env[name];
  if (!rawValue) {
    return fallback;
  }

  const value = Number(rawValue);
  if (!Number.isInteger(value) || value <= 0) {
    throw new Error(`${name} 必須是正整數，目前取得：${rawValue}`);
  }
  return value;
}

function hostAndMethodExpression(pathExpression) {
  return [
    `(http.host eq "${SiteHostname}")`,
    `(http.request.method in {"GET" "HEAD"})`,
    `(${pathExpression})`,
  ].join(" and ");
}

function ttlActionParameters(edgeTtlSeconds, browserTtlSeconds) {
  return {
    cache: true,
    edge_ttl: {
      mode: "override_origin",
      default: edgeTtlSeconds,
      status_code_ttl: [
        {
          status_code_range: { from: 200, to: 299 },
          value: edgeTtlSeconds,
        },
        {
          status_code_range: { from: 300, to: 399 },
          value: Math.min(edgeTtlSeconds, 300),
        },
        {
          status_code_range: { from: 400, to: 499 },
          value: 0,
        },
        {
          status_code_range: { from: 500 },
          value: -1,
        },
      ],
    },
    browser_ttl: {
      mode: "override_origin",
      default: browserTtlSeconds,
    },
  };
}

function cacheRule(ref, description, pathExpression, edgeTtlSeconds, browserTtlSeconds) {
  return {
    ref,
    description: `${ManagedRuleDescriptionPrefix}${description}`,
    expression: hostAndMethodExpression(pathExpression),
    action: "set_cache_settings",
    action_parameters: ttlActionParameters(edgeTtlSeconds, browserTtlSeconds),
    enabled: true,
  };
}

function buildCacheRules() {
  return [
    cacheRule(
      "ffxiv_tc_vite_assets_cache",
      "Vite 指紋化 assets 長效快取",
      `starts_with(http.request.uri.path, "/assets/")`,
      StaticEdgeTtlSeconds,
      StaticBrowserTtlSeconds,
    ),
    cacheRule(
      "ffxiv_tc_media_cache",
      "網站圖示、職業圖示與 OG 圖快取",
      [
        `starts_with(http.request.uri.path, "/icons/")`,
        `starts_with(http.request.uri.path, "/og/")`,
        `http.request.uri.path eq "/og-image.png"`,
        `http.request.uri.path eq "/favicon.svg"`,
        `http.request.uri.path eq "/favicon.ico"`,
        `http.request.uri.path eq "/favicon-16x16.png"`,
        `http.request.uri.path eq "/favicon-32x32.png"`,
        `http.request.uri.path eq "/apple-touch-icon.png"`,
        `http.request.uri.path eq "/site.webmanifest"`,
      ].join(" or "),
      MediaEdgeTtlSeconds,
      MediaBrowserTtlSeconds,
    ),
    cacheRule(
      "ffxiv_tc_public_data_cache",
      "公開 JSON 資料快取",
      `starts_with(http.request.uri.path, "/data/")`,
      DataEdgeTtlSeconds,
      DataBrowserTtlSeconds,
    ),
    cacheRule(
      "ffxiv_tc_html_routes_cache",
      "SPA HTML 與 SEO fallback 快取",
      [
        `http.request.uri.path eq "/"`,
        `ends_with(http.request.uri.path, ".html")`,
        `http.request.uri.path eq "/robots.txt"`,
        `http.request.uri.path eq "/sitemap.xml"`,
        `starts_with(http.request.uri.path, "/stats")`,
        `starts_with(http.request.uri.path, "/user")`,
        `starts_with(http.request.uri.path, "/compare")`,
        `starts_with(http.request.uri.path, "/teams")`,
        `starts_with(http.request.uri.path, "/servers")`,
        `starts_with(http.request.uri.path, "/jobs")`,
        `starts_with(http.request.uri.path, "/activity")`,
        `starts_with(http.request.uri.path, "/honey-fans")`,
      ].join(" or "),
      HtmlEdgeTtlSeconds,
      HtmlBrowserTtlSeconds,
    ),
  ];
}

function buildRateLimitRule() {
  return {
    ref: "ffxiv_tc_static_site_rate_limit",
    description: `${ManagedRuleDescriptionPrefix}靜態網站每 IP 請求節流`,
    // Free 方案的 Rate Limiting 可用欄位較少，這條規則刻意只依 Path 與 Verified Bot 判斷。
    expression: `(not cf.client.bot and http.request.uri.path ne "/robots.txt")`,
    action: "block",
    action_parameters: {
      response: {
        status_code: 429,
        content_type: "text/plain",
        content: "Too many requests. Please retry later.",
      },
    },
    ratelimit: {
      characteristics: ["ip.src", "cf.colo.id"],
      period: 10,
      requests_per_period: RateLimitRequestsPer10Seconds,
      mitigation_timeout: 10,
    },
    enabled: true,
  };
}

function buildFacebookCrawlerSkipRule() {
  const metaCrawlerExpression = [
    `ip.geoip.asnum in {32934 63293}`,
    `(cf.client.bot and lower(http.user_agent) contains "facebook")`,
  ].join(" or ");

  return {
    ref: "ffxiv_tc_facebook_crawler_skip",
    description: `${ManagedRuleDescriptionPrefix}Facebook 分享預覽爬蟲例外`,
    // Facebook 分享偵錯工具會由 Meta ASN 抓取頁面；Cloudflare 官方建議對 AS32934 / AS63293 建立 skip rule。
    // 這條規則只放行本靜態站的 GET/HEAD 預覽請求，避免社群爬蟲被 Security Level、BIC 或後續自訂規則擋成 403。
    expression: [
      `(http.host eq "${SiteHostname}")`,
      `(http.request.method in {"GET" "HEAD"})`,
      `(${metaCrawlerExpression})`,
    ].join(" and "),
    action: "skip",
    action_parameters: {
      ruleset: "current",
      phases: ["http_ratelimit", "http_request_sbfm", "http_request_firewall_managed"],
      products: ["securityLevel", "uaBlock", "bic"],
    },
    logging: {
      enabled: true,
    },
    enabled: true,
  };
}

function isManagedRule(rule) {
  const ref = String(rule?.ref || "");
  const description = String(rule?.description || "");
  return ref.startsWith(ManagedRuleRefPrefix) || description.startsWith(ManagedRuleDescriptionPrefix);
}

function mergeRules(existingRules, managedRules, { managedFirst = false } = {}) {
  const unmanagedRules = Array.isArray(existingRules) ? existingRules.filter((rule) => !isManagedRule(rule)) : [];
  return managedFirst ? [...managedRules, ...unmanagedRules] : [...unmanagedRules, ...managedRules];
}

class CloudflareApiError extends Error {
  constructor(message, { status = 0, method = "GET", path = "" } = {}) {
    super(message);
    this.name = "CloudflareApiError";
    this.status = status;
    this.method = method;
    this.path = path;
  }

  get isTransient() {
    return this.status === 0 || this.status === 429 || (this.status >= 500 && this.status <= 599);
  }
}

function parseCloudflareResponseBody(bodyText) {
  if (!bodyText) {
    return null;
  }

  try {
    return JSON.parse(bodyText);
  } catch {
    return null;
  }
}

function describeCloudflareResponse(body, bodyText) {
  const messages = [];
  const responseItems = [
    ...(Array.isArray(body?.errors) ? body.errors : []),
    ...(Array.isArray(body?.messages) ? body.messages : []),
  ];
  for (const item of responseItems) {
    const code = item?.code ? `#${item.code} ` : "";
    const message = item?.message || JSON.stringify(item);
    if (message) {
      messages.push(`${code}${message}`.trim());
    }
  }

  if (messages.length > 0) {
    return messages.join("; ");
  }

  return bodyText ? bodyText.slice(0, 500) : "";
}

function cloudflareRetryDelayMs(attempt) {
  return CloudflareRetryBaseDelayMs * 2 ** (attempt - 1);
}

function sleep(ms) {
  return new Promise((resolve) => {
    setTimeout(resolve, ms);
  });
}

async function retryCloudflareRequest(error, attempt) {
  if (!(error instanceof CloudflareApiError) || !error.isTransient || attempt >= CloudflareMaxAttempts) {
    return false;
  }

  const delayMs = cloudflareRetryDelayMs(attempt);
  const statusLabel = error.status === 0 ? "network" : `HTTP ${error.status}`;
  console.warn(
    `Cloudflare API 暫時性錯誤：${error.method} ${error.path} ${statusLabel}，第 ${attempt}/${CloudflareMaxAttempts} 次失敗，${delayMs}ms 後重試。`,
  );
  await sleep(delayMs);
  return true;
}

async function cloudflareRequest(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();

  for (let attempt = 1; attempt <= CloudflareMaxAttempts; attempt += 1) {
    let response = null;
    try {
      response = await fetch(`${CloudflareApiBase}${path}`, {
        ...options,
        method,
        headers: {
          Authorization: `Bearer ${ApiToken}`,
          "Content-Type": "application/json",
          ...(options.headers || {}),
        },
      });
    } catch (cause) {
      const reason = cause instanceof Error ? cause.message : String(cause);
      const error = new CloudflareApiError(`Cloudflare API 呼叫失敗：${method} ${path} 網路錯誤 ${reason}`, {
        method,
        path,
      });
      if (await retryCloudflareRequest(error, attempt)) {
        continue;
      }
      throw error;
    }

    const bodyText = await response.text();
    const body = parseCloudflareResponseBody(bodyText);

    if (response.status === 404) {
      return null;
    }

    if (response.ok && body?.success !== false) {
      return body?.result || null;
    }

    const details = describeCloudflareResponse(body, bodyText);
    const error = new CloudflareApiError(
      `Cloudflare API 呼叫失敗：${method} ${path} HTTP ${response.status} ${details || ""}`.trim(),
      {
        status: response.status,
        method,
        path,
      },
    );
    if (await retryCloudflareRequest(error, attempt)) {
      continue;
    }
    throw error;
  }

  return null;
}

async function getEntrypointRuleset(phase) {
  return cloudflareRequest(`/zones/${ZoneId}/rulesets/phases/${phase}/entrypoint`);
}

async function upsertEntrypointRuleset(phase, name, managedRules, options = {}) {
  const existingRuleset = await getEntrypointRuleset(phase);
  const rules = mergeRules(existingRuleset?.rules || [], managedRules, options);
  const payload = {
    name: existingRuleset?.name || name,
    description: "由 scripts/apply_cloudflare_rules.mjs 管理的 FFXIV TC 靜態站台規則",
    kind: "zone",
    phase,
    rules,
  };

  if (!existingRuleset) {
    await cloudflareRequest(`/zones/${ZoneId}/rulesets`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    console.log(`已建立 ${phase} entry point ruleset，包含 ${managedRules.length} 條本專案規則。`);
    return;
  }

  await cloudflareRequest(`/zones/${ZoneId}/rulesets/${existingRuleset.id}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
  console.log(`已更新 ${phase} entry point ruleset，保留 ${rules.length - managedRules.length} 條既有規則並套用 ${managedRules.length} 條本專案規則。`);
}

async function main() {
  const cacheRules = buildCacheRules();
  const facebookCrawlerSkipRule = buildFacebookCrawlerSkipRule();
  const rateLimitRule = buildRateLimitRule();
  const preview = {
    hostname: SiteHostname,
    facebook_crawler_skip_rule: facebookCrawlerSkipRule,
    cache_rules: cacheRules,
    rate_limit_rule: SkipRateLimit ? null : rateLimitRule,
  };

  if (DryRun) {
    console.log(JSON.stringify(preview, null, 2));
    return;
  }

  if (!ZoneId || !ApiToken) {
    throw new Error("請先設定 CLOUDFLARE_ZONE_ID 與 CLOUDFLARE_API_TOKEN，或加上 --dry-run 檢視將套用的規則。");
  }

  await upsertEntrypointRuleset(FirewallCustomPhase, "FFXIV TC WAF Custom Rules", [facebookCrawlerSkipRule], {
    managedFirst: true,
  });
  await upsertEntrypointRuleset(CacheRulesPhase, "FFXIV TC Cache Rules", cacheRules);
  if (!SkipRateLimit) {
    await upsertEntrypointRuleset(RateLimitPhase, "FFXIV TC Rate Limiting Rules", [rateLimitRule]);
  }
}

main().catch((error) => {
  if (AllowTransientFailure && error instanceof CloudflareApiError && error.isTransient) {
    console.warn(`::warning::Cloudflare 規則同步遇到暫時性錯誤，已略過本次同步：${error.message}`);
    return;
  }

  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
});
