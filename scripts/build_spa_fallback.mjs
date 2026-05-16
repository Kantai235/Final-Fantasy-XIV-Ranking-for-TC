import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { dirname, join } from "node:path";
import sharp from "sharp";

const distDir = "dist";
const indexPath = join(distDir, "index.html");
const fallbackPath = join(distDir, "404.html");
const userIndexPath = join("public", "data", "users", "index.json");
const globalStatsPath = join("public", "data", "global_stats.json");
const serverComparePath = join("public", "data", "server_compare.json");

const siteConfig = readJson("config/site.json", {});
const siteUrl = String(siteConfig.site_url || "https://ranking.init.engineer/").replace(/\/?$/, "/");
const siteBasePath = new URL(siteUrl).pathname || "/";
const siteName = "FFXIV 繁中服排行榜";
const defaultDescription =
  "整理 FFLogs 公開報告中的 FFXIV 繁中服零式、極、幻與絕本成績，提供排行榜、全服統計、個人成績單、玩家比較與近期動態。";
const genericOgImageUrl = new URL("og-image.png", siteUrl).href;

// postbuild 只讀取 public/data 的靜態聚合結果，輸出 dist/ 內的 HTML、PNG OG 圖、sitemap 與 robots。
// 這一層不得回寫 data/ 或 public/data/，避免 SEO 分享頁生成影響排行榜歷史資料或前端資料契約。
const jobNames = {
  Paladin: "騎士",
  Warrior: "戰士",
  DarkKnight: "暗黑騎士",
  Gunbreaker: "絕槍戰士",
  WhiteMage: "白魔法師",
  Scholar: "學者",
  Astrologian: "占星術士",
  Sage: "賢者",
  Monk: "武僧",
  Dragoon: "龍騎士",
  Ninja: "忍者",
  Samurai: "武士",
  Reaper: "鐮刀師",
  Viper: "蝰蛇劍士",
  Bard: "吟遊詩人",
  Machinist: "機工士",
  Dancer: "舞者",
  BlackMage: "黑魔法師",
  Summoner: "召喚師",
  RedMage: "赤魔法師",
  Pictomancer: "繪靈法師",
  BlueMage: "青魔法師",
};

const roleAccents = {
  "role:tank": "#68a8ff",
  "role:healer": "#55d98c",
  "role:melee": "#ff766f",
  "role:physical_ranged": "#d6a354",
  "role:magical_ranged": "#b58cff",
};

const routePages = [
  {
    path: "",
    title: siteName,
    description: defaultDescription,
    imageTitle: "FFXIV 繁中服排行榜",
    imageSubtitle: "零式・極・幻・絕本公開成績",
    imageHighlights: ["排行榜與全服統計", "玩家比較與隊伍榜", "FFLogs 公開報告整理"],
  },
  {
    path: "stats",
    title: `全服統計 | ${siteName}`,
    description: "查看 FFXIV 繁中服公開紀錄中的伺服器分布、職業分布、零式進度概覽、傷害分位數與資料狀態。",
    imageTitle: "全服統計",
    imageSubtitle: "伺服器・職業・進度概覽",
    imageHighlights: ["伺服器分布", "職業分布", "傷害分位數"],
  },
  {
    path: "user",
    title: `個人成績單 | ${siteName}`,
    description: "搜尋 FFXIV 繁中服玩家個人成績單，查看各副本最佳 rDPS、aDPS、分位表現、歷史紀錄與常同場隊友。",
    imageTitle: "個人成績單",
    imageSubtitle: "玩家最佳紀錄與分位表現",
    imageHighlights: ["最佳 rDPS / aDPS", "副本歷史紀錄", "常同場隊友"],
  },
  {
    path: "compare",
    title: `玩家比較 | ${siteName}`,
    description: "並排比較兩名 FFXIV 繁中服玩家在指定職能的公開成績，查看各副本最佳紀錄、rDPS 與通關表現。",
    imageTitle: "玩家比較",
    imageSubtitle: "兩名玩家並排查看公開成績",
    imageHighlights: ["指定職能比較", "各副本最佳紀錄", "rDPS 與通關表現"],
  },
  {
    path: "teams",
    title: `隊伍榜 | ${siteName}`,
    description: "查看 FFXIV 繁中服同場 8 人公開紀錄的副本最速通關、隊伍 rDPS 與成員組成。",
    imageTitle: "隊伍榜",
    imageSubtitle: "同場 8 人公開紀錄",
    imageHighlights: ["副本最速通關", "隊伍 rDPS", "成員組成"],
  },
  {
    path: "servers",
    title: `伺服器對比 | ${siteName}`,
    description: "比較兩個 FFXIV 繁中服伺服器的收錄玩家、副本通關、職能比例、熱門職業與副本落點。",
    imageTitle: "伺服器對比",
    imageSubtitle: "兩個伺服器並排分析",
    imageHighlights: ["收錄玩家", "職能比例", "副本落點"],
  },
  {
    path: "jobs",
    title: `職業分析 | ${siteName}`,
    description: "查看 FFXIV 繁中服各職業在副本、伺服器、rDPS 分布與代表紀錄中的公開成績落點。",
    imageTitle: "職業分析",
    imageSubtitle: "職業公開成績分布",
    imageHighlights: ["副本分布", "伺服器落點", "代表紀錄"],
  },
  {
    path: "activity",
    title: `近期動態 | ${siteName}`,
    description: "追蹤 FFXIV 繁中服最新公開成績、刷新個人最佳、新收錄玩家、伺服器活躍與副本活躍。",
    imageTitle: "近期動態",
    imageSubtitle: "最新公開成績與刷新紀錄",
    imageHighlights: ["最新成績", "個人最佳刷新", "伺服器活躍"],
  },
  {
    path: "honey-fans",
    title: `Honey B. Lovely 粉絲榜 | ${siteName}`,
    description: "趣味統計 M2S 通關紀錄中吃到第 4 顆愛心並進入心醉魂迷：奴役的 Honey B. Lovely 粉絲榜。",
    imageTitle: "Honey B. Lovely 粉絲榜",
    imageSubtitle: "吃到第 4 顆愛心的趣味統計",
    imageHighlights: ["頭號粉絲", "最新收錄紀錄", "最新加入粉絲"],
  },
];

if (!existsSync(indexPath)) {
  throw new Error("找不到 dist/index.html，請先完成 Vite build。");
}

function readJson(path, fallback) {
  if (!existsSync(path)) {
    return fallback;
  }

  return JSON.parse(readFileSync(path, "utf8"));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function escapeJsonForHtml(value) {
  return JSON.stringify(value, null, 8).replaceAll("</", "<\\/");
}

function escapeXml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&apos;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}

function clampText(value, maxLength) {
  const chars = Array.from(String(value ?? "").trim());
  if (chars.length <= maxLength) {
    return chars.join("");
  }

  return `${chars.slice(0, Math.max(0, maxLength - 1)).join("")}…`;
}

function formatNumber(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "";
  }

  return number.toLocaleString("zh-TW", {
    maximumFractionDigits: digits,
  });
}

function formatSignedNumber(value, digits = 0) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "";
  }

  const prefix = number > 0 ? "+" : "";
  return `${prefix}${formatNumber(number, digits)}`;
}

function encodePathSegment(value) {
  return encodeURIComponent(String(value || "").trim());
}

function routeUrl(routePath) {
  return new URL(routePath || ".", siteUrl).href;
}

function pageOutputPath(routePath) {
  return join(distDir, ...String(routePath || "").split("/").filter(Boolean), "index.html");
}

function userPath(characterName) {
  return `user/${encodePathSegment(characterName)}`;
}

function hashFileName(value) {
  const hash = createHash("sha1").update(String(value || ""), "utf8").digest("hex").slice(0, 16);
  return `${hash}.png`;
}

function ogImageUrlForPath(imagePath) {
  return new URL(imagePath, siteUrl).href;
}

function displayJobName(job) {
  return jobNames[job] || job || "未知職業";
}

function displayJobLabel(job) {
  const localName = jobNames[job];
  return localName ? `${localName}（${job}）` : job || "未知職業";
}

function upsertHeadTag(html, pattern, tag) {
  if (pattern.test(html)) {
    return html.replace(pattern, tag);
  }

  return html.replace(/<\/head>/i, `    ${tag}\n  </head>`);
}

function upsertMeta(html, selector, tag) {
  const pattern = selector.startsWith("name=")
    ? new RegExp(`<meta\\s+name="${selector.slice(5)}"[^>]*>`, "i")
    : new RegExp(`<meta\\s+property="${selector.slice(9)}"[^>]*>`, "i");

  return upsertHeadTag(html, pattern, tag);
}

function buildJsonLd(page, canonicalUrl) {
  if (!page.path) {
    return {
      "@context": "https://schema.org",
      "@type": "WebSite",
      name: siteName,
      alternateName: ["FFXIV TC Rankings", "FF14 繁中服排行榜"],
      url: siteUrl,
      inLanguage: "zh-Hant-TW",
      description: page.description,
      potentialAction: {
        "@type": "SearchAction",
        target: `${siteUrl}?q={search_term_string}`,
        "query-input": "required name=search_term_string",
      },
    };
  }

  return {
    "@context": "https://schema.org",
    "@type": page.schemaType || "WebPage",
    name: page.title,
    url: canonicalUrl,
    inLanguage: "zh-Hant-TW",
    description: page.description,
    ...(page.about ? { about: page.about } : {}),
    isPartOf: {
      "@type": "WebSite",
      name: siteName,
      url: siteUrl,
    },
  };
}

function replaceHeadMetadata(html, page) {
  const canonicalUrl = routeUrl(page.path);
  // 社群爬蟲對 SVG 的 OG 圖支援不一致，因此所有靜態分享頁都輸出實體 PNG。
  // page.imageUrl 仍由各頁資料決定，避免玩家頁、職業頁或伺服器比較退回首頁預覽圖。
  const imageUrl = page.imageUrl || genericOgImageUrl;
  const imageType = page.imageType || (imageUrl.endsWith(".png") ? "image/png" : "image/svg+xml");
  const imageAlt = page.imageAlt || `${page.title} 社群分享預覽圖`;
  const jsonLd = buildJsonLd(page, canonicalUrl);

  let nextHtml = html
    .replace(/<title>[\s\S]*?<\/title>/i, `<title>${escapeHtml(page.title)}</title>`)
    .replace(
      /<script\s+id="site-structured-data"\s+type="application\/ld\+json">[\s\S]*?<\/script>/i,
      `<script id="site-structured-data" type="application/ld+json">\n      ${escapeJsonForHtml(jsonLd)}\n    </script>`,
    );

  nextHtml = upsertHeadTag(
    nextHtml,
    /<link\s+rel="canonical"[^>]*>/i,
    `<link rel="canonical" href="${escapeHtml(canonicalUrl)}" />`,
  );
  nextHtml = upsertMeta(
    nextHtml,
    "name=description",
    `<meta name="description" content="${escapeHtml(page.description)}" />`,
  );
  nextHtml = upsertMeta(nextHtml, "property=og:type", `<meta property="og:type" content="website" />`);
  nextHtml = upsertMeta(nextHtml, "property=og:title", `<meta property="og:title" content="${escapeHtml(page.title)}" />`);
  nextHtml = upsertMeta(
    nextHtml,
    "property=og:description",
    `<meta property="og:description" content="${escapeHtml(page.description)}" />`,
  );
  nextHtml = upsertMeta(nextHtml, "property=og:url", `<meta property="og:url" content="${escapeHtml(canonicalUrl)}" />`);
  nextHtml = upsertMeta(nextHtml, "property=og:image", `<meta property="og:image" content="${escapeHtml(imageUrl)}" />`);
  nextHtml = upsertMeta(
    nextHtml,
    "property=og:image:secure_url",
    `<meta property="og:image:secure_url" content="${escapeHtml(imageUrl)}" />`,
  );
  nextHtml = upsertMeta(nextHtml, "property=og:image:type", `<meta property="og:image:type" content="${escapeHtml(imageType)}" />`);
  nextHtml = upsertMeta(nextHtml, "property=og:image:width", `<meta property="og:image:width" content="1200" />`);
  nextHtml = upsertMeta(nextHtml, "property=og:image:height", `<meta property="og:image:height" content="630" />`);
  nextHtml = upsertMeta(nextHtml, "property=og:image:alt", `<meta property="og:image:alt" content="${escapeHtml(imageAlt)}" />`);
  nextHtml = upsertMeta(nextHtml, "name=twitter:card", `<meta name="twitter:card" content="summary_large_image" />`);
  nextHtml = upsertMeta(nextHtml, "name=twitter:title", `<meta name="twitter:title" content="${escapeHtml(page.title)}" />`);
  nextHtml = upsertMeta(
    nextHtml,
    "name=twitter:description",
    `<meta name="twitter:description" content="${escapeHtml(page.description)}" />`,
  );
  nextHtml = upsertMeta(nextHtml, "name=twitter:image", `<meta name="twitter:image" content="${escapeHtml(imageUrl)}" />`);
  nextHtml = upsertMeta(nextHtml, "name=twitter:image:alt", `<meta name="twitter:image:alt" content="${escapeHtml(imageAlt)}" />`);

  return nextHtml;
}

function addRouteBaseHref(html) {
  if (/<base\s+/i.test(html)) {
    return html;
  }

  return html.replace(/<meta name="viewport"[^>]*>\s*/i, (match) => `${match}    <base href="${escapeHtml(siteBasePath)}" />\n`);
}

function buildOgSvg({ title, subtitle, highlights = [], footer = "ranking.init.engineer", accent = "#d6a354" }) {
  const safeHighlights = highlights.filter(Boolean).slice(0, 3);
  const highlightMarkup = safeHighlights
    .map((highlight, index) => {
      const y = 402 + index * 48;
      const colors = ["#68a8ff", "#55d98c", "#ff766f"];
      return `<circle cx="132" cy="${y + 8}" r="9" fill="${colors[index] || accent}" />
  <text x="160" y="${y + 18}" fill="#f4f1ea" font-size="26" font-weight="700">${escapeXml(clampText(highlight, 34))}</text>`;
    })
    .join("\n  ");

  return `<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <rect width="1200" height="630" fill="#101214"/>
  <rect x="58" y="58" width="1084" height="514" fill="#171b1f" stroke="#303842" stroke-width="2"/>
  <rect x="58" y="58" width="10" height="514" fill="${escapeXml(accent)}"/>
  <text x="126" y="184" fill="#f4f1ea" font-family="Microsoft JhengHei, Noto Sans TC, sans-serif" font-size="58" font-weight="800">${escapeXml(clampText(title, 22))}</text>
  <text x="126" y="252" fill="#b7b1a8" font-family="Microsoft JhengHei, Noto Sans TC, sans-serif" font-size="30">${escapeXml(clampText(subtitle, 32))}</text>
  <text x="126" y="300" fill="${escapeXml(accent)}" font-family="Microsoft JhengHei, Noto Sans TC, sans-serif" font-size="30">FFXIV 繁中服公開成績</text>
  <line x1="120" y1="350" x2="620" y2="350" stroke="${escapeXml(accent)}" stroke-width="5"/>
  <g font-family="Microsoft JhengHei, Noto Sans TC, sans-serif">
  ${highlightMarkup}
  </g>
  <text x="822" y="480" fill="${escapeXml(accent)}" font-family="Microsoft JhengHei, Noto Sans TC, sans-serif" font-size="25" font-weight="800">TC Rankings</text>
  <text x="822" y="522" fill="#b7b1a8" font-family="Microsoft JhengHei, Noto Sans TC, sans-serif" font-size="22">${escapeXml(clampText(footer, 28))}</text>
</svg>
`;
}

function writeTextFile(path, content) {
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, content, "utf8");
}

const queuedOgPngImages = [];

function queueOgPng(path, svgContent) {
  queuedOgPngImages.push({ path, svgContent });
}

async function writeOgPng(path, svgContent) {
  mkdirSync(dirname(path), { recursive: true });
  await sharp(Buffer.from(svgContent))
    .resize(1200, 630, { fit: "fill" })
    .png({ compressionLevel: 9, effort: 8, palette: true })
    .toFile(path);
}

async function writeQueuedOgPngImages(concurrency = 6) {
  let nextIndex = 0;
  const workerCount = Math.min(concurrency, queuedOgPngImages.length);

  await Promise.all(
    Array.from({ length: workerCount }, async () => {
      while (nextIndex < queuedOgPngImages.length) {
        const item = queuedOgPngImages[nextIndex];
        nextIndex += 1;
        await writeOgPng(item.path, item.svgContent);
      }
    }),
  );
}

function writeGeneratedPage(page, rootHtml) {
  writeTextFile(pageOutputPath(page.path), addRouteBaseHref(replaceHeadMetadata(rootHtml, page)));
  return routeUrl(page.path);
}

function readUserIndex() {
  const userIndex = readJson(userIndexPath, { users: [] });
  return Array.isArray(userIndex.users) ? userIndex.users : [];
}

function buildUserDescription(user) {
  const servers = Array.isArray(user.servers) ? user.servers.filter(Boolean) : [];
  const serverText = servers.length > 0 ? `（${servers.slice(0, 3).join(" / ")}${servers.length > 3 ? " 等" : ""}）` : "";
  const encounterCount = formatNumber(user.encounter_count);
  const entryCount = formatNumber(user.public_entry_count);
  const rdps = formatNumber(user.best_rdps, 2);
  const parts = [];
  if (encounterCount) {
    parts.push(`${encounterCount} 個副本`);
  }
  if (entryCount) {
    parts.push(`${entryCount} 筆公開成績`);
  }
  if (rdps) {
    parts.push(`最佳 rDPS ${rdps}`);
  }

  return `${user.character_name}${serverText}的 FFXIV 繁中服個人成績單，${parts.length > 0 ? `收錄 ${parts.join("、")}，` : ""}可查看最佳紀錄、分位表現、歷史紀錄與常同場隊友。`;
}

function buildUserPage(user, rootHtml) {
  const imagePath = `og/users/${hashFileName(user.character_name)}`;
  const servers = Array.isArray(user.servers) ? user.servers.filter(Boolean) : [];
  const page = {
    path: userPath(user.character_name),
    title: `${user.character_name} 個人成績單 | ${siteName}`,
    description: buildUserDescription(user),
    imageUrl: ogImageUrlForPath(imagePath),
    imageType: "image/png",
    schemaType: "ProfilePage",
    about: {
      "@type": "Thing",
      name: `${user.character_name} FFXIV 角色`,
      ...(servers.length > 0 ? { gameServer: servers.join(" / ") } : {}),
    },
  };

  const highlights = [
    servers.length > 0 ? servers.slice(0, 2).join(" / ") : "繁中服玩家",
    user.encounter_count ? `${formatNumber(user.encounter_count)} 個副本` : "",
    user.best_rdps ? `最佳 rDPS ${formatNumber(user.best_rdps, 2)}` : `${formatNumber(user.public_entry_count)} 筆公開成績`,
  ];

  queueOgPng(
    join(distDir, imagePath),
    buildOgSvg({
      title: user.character_name,
      subtitle: servers.length > 0 ? servers.join(" / ") : "個人成績單",
      highlights,
      footer: "個人成績單",
      accent: "#d6a354",
    }),
  );

  return {
    path: pageOutputPath(page.path),
    html: addRouteBaseHref(replaceHeadMetadata(rootHtml, page)),
    url: routeUrl(page.path),
  };
}

function buildEncounterDescription(encounter) {
  const parts = [
    encounter.character_count ? `${formatNumber(encounter.character_count)} 名角色` : "",
    encounter.entry_count ? `${formatNumber(encounter.entry_count)} 筆公開紀錄` : "",
  ].filter(Boolean);
  const topServer = encounter.server_stats?.[0]?.server;
  const topJob = displayJobName(encounter.job_stats?.[0]?.job);
  const tail = [
    topServer ? `最多紀錄伺服器為 ${topServer}` : "",
    topJob ? `熱門職業包含 ${topJob}` : "",
  ].filter(Boolean);

  return `${encounter.encounter_name} 的 FFXIV 繁中服全服統計，${parts.length > 0 ? `整理 ${parts.join("、")}，` : ""}包含伺服器分布、職業分布與 rDPS / aDPS 分位${tail.length > 0 ? `；${tail.join("，")}。` : "。"}`;
}

function buildStatsEncounterPages(globalStats) {
  // 只為副本層級產生靜態頁。伺服器、職業範圍、分群與指標等細部條件仍由前端動態 meta 處理，
  // 避免把所有 query 組合都展開成靜態 HTML，導致建置產物暴增且難以追蹤。
  const encounters = Array.isArray(globalStats.encounters) ? globalStats.encounters : [];
  return encounters
    .filter((encounter) => encounter?.encounter_key && encounter?.encounter_name)
    .map((encounter) => {
      const imagePath = `og/stats/${encodePathSegment(encounter.encounter_key)}.png`;
      const topServer = encounter.server_stats?.[0]?.server;
      const topJob = displayJobName(encounter.job_stats?.[0]?.job);

      queueOgPng(
        join(distDir, imagePath),
        buildOgSvg({
          title: encounter.encounter_name,
          subtitle: "全服統計",
          highlights: [
            encounter.character_count ? `${formatNumber(encounter.character_count)} 名角色` : "",
            encounter.entry_count ? `${formatNumber(encounter.entry_count)} 筆公開紀錄` : "",
            topServer ? `最多紀錄：${topServer}` : topJob ? `熱門職業：${topJob}` : "",
          ],
          footer: "副本全服統計",
          accent: "#55d98c",
        }),
      );

      return {
        path: `stats/${encodePathSegment(encounter.encounter_key)}`,
        title: `${encounter.encounter_name} 全服統計 | ${siteName}`,
        description: buildEncounterDescription(encounter),
        imageUrl: ogImageUrlForPath(imagePath),
        imageType: "image/png",
        schemaType: "Dataset",
        about: {
          "@type": "Thing",
          name: `${encounter.encounter_name} 公開成績統計`,
        },
      };
    });
}

function buildJobDescription(profile) {
  const jobLabel = displayJobLabel(profile.job);
  const parts = [
    profile.unique_player_count ? `${formatNumber(profile.unique_player_count)} 名玩家` : "",
    profile.entry_count ? `${formatNumber(profile.entry_count)} 筆公開紀錄` : "",
    profile.encounter_count ? `${formatNumber(profile.encounter_count)} 個副本` : "",
  ].filter(Boolean);
  const rdpsMedian = profile.damage_profile?.rdps?.median ?? profile.savage_damage_profile?.rdps?.median;

  return `${jobLabel}在 FFXIV 繁中服高難度副本的職業分析，${parts.length > 0 ? `整理 ${parts.join("、")}，` : ""}包含伺服器分布、傷害分位與代表成績${rdpsMedian ? `，rDPS 中位數 ${formatNumber(rdpsMedian, 2)}。` : "。"}`;
}

function buildJobPages(globalStats) {
  // 職業分析以 job_profiles 為唯一來源；這些資料已由 build_user_data.mjs 聚合完成，
  // 因此這裡只做分享文案與 OG 圖，不重新計算職業統計。
  const profiles = Array.isArray(globalStats.job_profiles) ? globalStats.job_profiles : [];
  return profiles
    .filter((profile) => profile?.job)
    .map((profile) => {
      const imagePath = `og/jobs/${encodePathSegment(profile.job)}.png`;
      const rdpsMedian = profile.damage_profile?.rdps?.median ?? profile.savage_damage_profile?.rdps?.median;
      const jobName = displayJobName(profile.job);

      queueOgPng(
        join(distDir, imagePath),
        buildOgSvg({
          title: `${jobName} 職業分析`,
          subtitle: profile.role_name || "職業公開成績分布",
          highlights: [
            profile.unique_player_count ? `${formatNumber(profile.unique_player_count)} 名玩家` : "",
            profile.entry_count ? `${formatNumber(profile.entry_count)} 筆公開紀錄` : "",
            rdpsMedian ? `rDPS 中位 ${formatNumber(rdpsMedian, 2)}` : "",
          ],
          footer: "職業分析",
          accent: roleAccents[profile.role] || "#d6a354",
        }),
      );

      return {
        path: `jobs/${encodePathSegment(profile.job)}`,
        title: `${jobName} 職業分析 | ${siteName}`,
        description: buildJobDescription(profile),
        imageUrl: ogImageUrlForPath(imagePath),
        imageType: "image/png",
        about: {
          "@type": "Thing",
          name: `${displayJobLabel(profile.job)} FFXIV 職業`,
        },
      };
    });
}

function buildServerPairDescription(left, right) {
  const leftPlayers = formatNumber(left.unique_player_count);
  const rightPlayers = formatNumber(right.unique_player_count);
  const leftEntries = formatNumber(left.entry_count);
  const rightEntries = formatNumber(right.entry_count);
  const details = [
    leftPlayers && rightPlayers ? `${left.server} ${leftPlayers} 名角色、${right.server} ${rightPlayers} 名角色` : "",
    leftEntries && rightEntries ? `${left.server} ${leftEntries} 筆紀錄、${right.server} ${rightEntries} 筆紀錄` : "",
  ].filter(Boolean);

  return `比較 ${left.server} 與 ${right.server} 在 FFXIV 繁中服高難度副本的收錄玩家、通關紀錄、rDPS 中位數、職業分布與副本落點${details.length > 0 ? `；${details.join("，")}。` : "。"}`;
}

function buildServerComparePages(serverCompare) {
  // 左右伺服器在 UI 上代表比較方向，因此產生有序配對：A/vs/B 與 B/vs/A 都保留各自網址。
  const servers = Array.isArray(serverCompare.servers) ? serverCompare.servers : [];
  const pages = [];

  for (const left of servers) {
    for (const right of servers) {
      if (!left?.server || !right?.server || left.server === right.server) {
        continue;
      }

      const pairKey = `${left.server}-vs-${right.server}`;
      const imagePath = `og/servers/${hashFileName(pairKey)}`;
      const medianDiff = Number(left.rdps_stats?.median) - Number(right.rdps_stats?.median);

      queueOgPng(
        join(distDir, imagePath),
        buildOgSvg({
          title: `${left.server} vs ${right.server}`,
          subtitle: "伺服器對比",
          highlights: [
            left.unique_player_count ? `${left.server}：${formatNumber(left.unique_player_count)} 名角色` : "",
            right.unique_player_count ? `${right.server}：${formatNumber(right.unique_player_count)} 名角色` : "",
            Number.isFinite(medianDiff) ? `rDPS 中位差 ${formatSignedNumber(medianDiff, 2)}` : "",
          ],
          footer: "伺服器對比",
          accent: "#68a8ff",
        }),
      );

      pages.push({
        path: `servers/${encodePathSegment(left.server)}/vs/${encodePathSegment(right.server)}`,
        title: `${left.server} vs ${right.server} 伺服器對比 | ${siteName}`,
        description: buildServerPairDescription(left, right),
        imageUrl: ogImageUrlForPath(imagePath),
        imageType: "image/png",
        about: {
          "@type": "Thing",
          name: `${left.server} 與 ${right.server} 伺服器公開成績比較`,
        },
      });
    }
  }

  return pages;
}

function buildSitemap(urls) {
  const uniqueUrls = Array.from(new Set(urls));
  return `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${uniqueUrls.map((url) => `  <url><loc>${escapeXml(url)}</loc></url>`).join("\n")}
</urlset>
`;
}

function buildRobotsTxt() {
  const sitemapUrl = new URL("sitemap.xml", siteUrl).href;
  // Facebook 分享偵錯工具會把 robots.txt 內沒有明確 allowlist 視為可能阻擋爬取。
  // 這裡保留全站允許，同時明列 Facebook 的兩個常見社群預覽 crawler。
  return `User-agent: facebookexternalhit
Allow: /

User-agent: Facebot
Allow: /

User-agent: *
Allow: /

Sitemap: ${sitemapUrl}
`;
}

const indexHtml = readFileSync(indexPath, "utf8");
const sitemapUrls = [];

for (const page of routePages) {
  const imageFileName = page.path || "home";
  const imagePath = `og/pages/${imageFileName}.png`;
  queueOgPng(
    join(distDir, imagePath),
    buildOgSvg({
      title: page.imageTitle || page.title,
      subtitle: page.imageSubtitle || page.description,
      highlights: page.imageHighlights || [],
    }),
  );
  page.imageUrl = page.path ? ogImageUrlForPath(imagePath) : genericOgImageUrl;
  page.imageType = "image/png";
}

const rootHtml = replaceHeadMetadata(indexHtml, routePages[0]);
writeFileSync(indexPath, rootHtml, "utf8");
sitemapUrls.push(routeUrl(routePages[0].path));

// GitHub Pages 對未知 History API 路徑沒有伺服器端 rewrite。
// 404.html 保留根頁預設分享資訊，讓沒有 route 專屬 HTML 的舊連結仍可交回 Vue SPA 接手解析。
writeFileSync(fallbackPath, addRouteBaseHref(rootHtml), "utf8");

for (const page of routePages.filter((routePage) => routePage.path)) {
  sitemapUrls.push(writeGeneratedPage(page, rootHtml));
}

const globalStats = readJson(globalStatsPath, {});
const statsEncounterPages = buildStatsEncounterPages(globalStats);
for (const page of statsEncounterPages) {
  sitemapUrls.push(writeGeneratedPage(page, rootHtml));
}

const jobPages = buildJobPages(globalStats);
for (const page of jobPages) {
  sitemapUrls.push(writeGeneratedPage(page, rootHtml));
}

const serverCompare = readJson(serverComparePath, {});
const serverComparePages = buildServerComparePages(serverCompare);
for (const page of serverComparePages) {
  sitemapUrls.push(writeGeneratedPage(page, rootHtml));
}

const users = readUserIndex();
let userPageCount = 0;
for (const user of users) {
  if (!user?.character_name) {
    continue;
  }

  const userPage = buildUserPage(user, rootHtml);
  writeTextFile(userPage.path, userPage.html);
  sitemapUrls.push(userPage.url);
  userPageCount += 1;
}

await writeQueuedOgPngImages();

writeTextFile(join(distDir, "sitemap.xml"), buildSitemap(sitemapUrls));
writeTextFile(join(distDir, "robots.txt"), buildRobotsTxt());

console.log(
  `Built SPA fallback at dist/404.html, ${routePages.length - 1} route meta pages, ${statsEncounterPages.length} stats pages, ${jobPages.length} job pages, ${serverComparePages.length} server compare pages, ${userPageCount} user share pages and ${queuedOgPngImages.length} PNG OG images.`,
);
