import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { 建立職業佔比分組 } from "../src/utils/statsDisplay.js";

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
    "utils/shareMeta.js",
    "utils/siteFeatures.js",
    "utils/statsDisplay.js",
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

function extractSourceSection(source, startText, endText, label) {
  const startIndex = source.indexOf(startText);
  const endIndex = source.indexOf(endText, startIndex + startText.length);
  if (startIndex === -1 || endIndex === -1) {
    reportIssue(`${label} 區段定位失敗，無法驗證副本切換篩選狀態`);
    return "";
  }

  return source.slice(startIndex, endIndex);
}

async function validateEncounterSwitchFilterPersistence() {
  const filePath = path.join(srcDir, "composables", "useRankingApp.js");
  const source = await readText(filePath);
  const rankingWatcher = extractSourceSection(source, "watch(副本鍵值", "watch(排行榜版本範圍", "排行榜副本切換 watcher");
  const statsWatcher = extractSourceSection(
    source,
    "watch([統計副本鍵值, 全服統計資料]",
    "watch([統計副本鍵值, 統計版本範圍",
    "全服統計副本切換 watcher",
  );

  for (const resetExpression of ['伺服器篩選.value = ""', '職業類型篩選.value = ""', '職業篩選.value = ""']) {
    assert(!rankingWatcher.includes(resetExpression), `排行榜切換副本時不可清空既有篩選：${resetExpression}`);
  }

  assert(
    statsWatcher.includes("統計伺服器可識別"),
    "全服統計切換副本時應以全域伺服器清單判斷有效性，避免只因目前副本沒有資料就清空伺服器篩選",
  );
  assert(
    statsWatcher.includes("統計職業範圍可識別"),
    "全服統計切換副本時應以職業定義判斷有效性，避免只因目前副本沒有資料就清空職業篩選",
  );
}

async function validatePublicDataForFrontend() {
  const encounters = await readJson(path.join(publicDataDir, "encounters.json"), "public/data/encounters.json");
  const globalStats = await readJson(path.join(publicDataDir, "global_stats.json"), "public/data/global_stats.json");
  const serverCompare = await readJson(path.join(publicDataDir, "server_compare.json"), "public/data/server_compare.json");
  const honeyFans = await readJson(path.join(publicDataDir, "fun", "honey_b_fans.json"), "public/data/fun/honey_b_fans.json");
  const userIndex = await readJson(path.join(publicDataDir, "users", "index.json"), "public/data/users/index.json");
  const versionedEncounterKeys = new Set((encounters || []).filter((encounter) => encounter?.version_cutoff).map((encounter) => encounter.key));

  assert(Array.isArray(encounters) && encounters.length > 0, "public/data/encounters.json 必須提供前端副本清單");
  assert(globalStats?.schema_version === 1, "public/data/global_stats.json schema_version 必須是 1");
  assert(Array.isArray(globalStats?.server_stats), "public/data/global_stats.json 必須包含 server_stats");
  assert(Array.isArray(globalStats?.role_stats), "public/data/global_stats.json 必須包含 role_stats");
  assert(Array.isArray(globalStats?.job_stats), "public/data/global_stats.json 必須包含 job_stats");
  assert(Array.isArray(globalStats?.damage_stats), "public/data/global_stats.json 必須包含 damage_stats");
  assert(Array.isArray(globalStats?.job_profiles), "public/data/global_stats.json 必須包含 job_profiles");
  assert(Array.isArray(globalStats?.encounters), "public/data/global_stats.json 必須包含 encounters");
  assert(serverCompare?.schema_version === 1, "public/data/server_compare.json schema_version 必須是 1");
  assert(Array.isArray(serverCompare?.servers), "public/data/server_compare.json 必須包含 servers");
  assert(honeyFans?.schema_version === 1, "public/data/fun/honey_b_fans.json schema_version 必須是 1");
  assert(honeyFans?.feature === "honey_b_lovely_fans", "public/data/fun/honey_b_fans.json feature 必須是 honey_b_lovely_fans");
  assert(Array.isArray(honeyFans?.top_fans), "public/data/fun/honey_b_fans.json 必須包含 top_fans");
  assert(Array.isArray(honeyFans?.latest_records), "public/data/fun/honey_b_fans.json 必須包含 latest_records");
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
    if (encounter?.version_cutoff) {
      assert(ranking?.version_cutoff?.obsolete_after_iso, `${key} 公開排行榜必須保留 version_cutoff.obsolete_after_iso`);
      for (const versionMode of ["all", "valid", "obsolete"]) {
        assert(
          Array.isArray(ranking?.version_ranking_entries?.[versionMode]),
          `${key} 公開排行榜必須包含 version_ranking_entries.${versionMode}`,
        );
      }
      assert(
        ranking.ranking_entries.some((entry) => typeof entry.is_obsolete_record === "boolean"),
        `${key} 公開排行榜條目必須標記 is_obsolete_record`,
      );
    }
  }

  for (const encounter of globalStats?.encounters || []) {
    if (!encounter?.version_cutoff) {
      continue;
    }
    for (const versionMode of ["all", "valid", "obsolete"]) {
      assert(
        encounter.version_slices?.[versionMode]?.version_mode === versionMode,
        `${encounter.encounter_key} 全服統計必須包含 version_slices.${versionMode}`,
      );
    }
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

  for (const user of userIndex?.users || []) {
    const userPath = path.join(rootDir, "public", user.file_path || "");
    if (!existsSync(userPath)) {
      continue;
    }

    const userData = await readJson(userPath, `使用者檔案 ${user.file_path}`);
    for (const encounter of userData?.encounters || []) {
      if (!versionedEncounterKeys.has(encounter?.encounter_key)) {
        continue;
      }

      const entries = Array.isArray(encounter.public_entries) ? encounter.public_entries : [];
      const validEntries = entries.filter((entry) => !entry.is_obsolete_record);
      const obsoleteEntries = entries.filter((entry) => entry.is_obsolete_record);
      if (obsoleteEntries.length === 0) {
        continue;
      }

      for (const entry of obsoleteEntries) {
        assert(entry.rank === null && entry.job_rank === null, `${user.file_path} 的過版紀錄不可保留職業 Rank`);
        assert(entry.performance?.reason === "obsolete_record", `${user.file_path} 的過版紀錄同職分位必須標記 obsolete_record`);
      }

      if (validEntries.length > 0) {
        assert(encounter.best_entry && !encounter.best_entry.is_obsolete_record, `${user.file_path} 混合有效與過版紀錄時，最佳紀錄必須取有效版本`);
        assert(Number(encounter.best_entry?.job_rank) > 0, `${user.file_path} 的有效最佳紀錄必須有正數職業 Rank`);
      } else {
        assert(encounter.best_entry === null, `${user.file_path} 只有過版紀錄時不可標示最佳紀錄`);
      }
    }
  }
}

function validateScopedJobShareRecalculation() {
  const source = {
    role_stats: [
      { role: "role:tank", role_name: "防護職業", clear_count: 3, percentage: 25 },
      { role: "role:healer", role_name: "治療職業", clear_count: 9, percentage: 75 },
    ],
    job_stats: [
      { job: "Paladin", role: "role:tank", role_name: "防護職業", clear_count: 3, percentage: 20 },
      { job: "Warrior", role: "role:tank", role_name: "防護職業", clear_count: 1, percentage: 6.67 },
      { job: "WhiteMage", role: "role:healer", role_name: "治療職業", clear_count: 8, percentage: 53.33 },
      { job: "Sage", role: "role:healer", role_name: "治療職業", clear_count: 1, percentage: 6.67 },
    ],
  };

  const allGroups = 建立職業佔比分組(source, "all");
  const allTankGroup = allGroups.find((group) => group.role === "role:tank");
  assert(allTankGroup?.percentage === 25, "全部職業範圍應沿用資料建置層已算好的職能佔比。");
  assert(
    allTankGroup?.jobs.find((job) => job.job === "Paladin")?.percentage === 20,
    "全部職業範圍應沿用資料建置層已算好的職業佔比。",
  );

  const tankGroups = 建立職業佔比分組(source, "role:tank");
  const tankGroup = tankGroups[0];
  assert(tankGroups.length === 1 && tankGroup?.role === "role:tank", "職能範圍應只顯示該職能的職業佔比群組。");
  assert(tankGroup?.percentage === 100, "職能範圍的群組佔比應以目前職能作為 100% 分母。");
  assert(
    tankGroup?.jobs.find((job) => job.job === "Paladin")?.percentage === 75,
    "職能範圍內的職業佔比應依該職能的職業紀錄總數重算。",
  );
  assert(
    tankGroup?.jobs.find((job) => job.job === "Warrior")?.percentage === 25,
    "職能範圍內的第二個職業也應依該職能分母重算。",
  );

  const paladinGroup = 建立職業佔比分組(source, "Paladin")[0];
  assert(paladinGroup?.percentage === 100, "單一職業範圍的群組佔比應以目前職業作為 100% 分母。");
  assert(paladinGroup?.jobs[0]?.percentage === 100, "單一職業範圍的職業佔比應顯示為 100%。");
}

async function loadUrlStateTestModule() {
  const filePath = path.join(srcDir, "utils", "urlState.js");
  let source = await readText(filePath);
  const importMatch = source.match(/import\s*\{\s*([^}]+?)\s*\}\s*from\s*["']\.\/shareMeta(?:\.js)?["'];\r?\n/);
  const exportedFunctions = [...source.matchAll(/export function\s+([^\s(]+)\s*\(/g)].map((match) => match[1]);

  assert(Boolean(importMatch), "urlState.js 必須明確匯入分享網址變更事件，讓網址寫入後可同步 SEO/OG meta");
  assert(exportedFunctions.length >= 2, "urlState.js 必須匯出讀取與寫入網址狀態函式");
  if (!importMatch || exportedFunctions.length < 2) {
    return null;
  }

  const importedEventName = importMatch[1].trim();
  source = source.replace(importMatch[0], 'const shareUrlChangeEvent = "ffxivtc:urlchange";\n');
  source = source.split(importedEventName).join("shareUrlChangeEvent");
  source = source.replace(/export const /g, "const ");
  source = source.replace(/export function /g, "function ");
  source += `\nexport { ${exportedFunctions[0]} as readState, ${exportedFunctions[1]} as writeState };\n`;

  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;
  return import(moduleUrl);
}

async function loadUserDataTestModule() {
  const filePath = path.join(srcDir, "utils", "userData.js");
  let source = await readText(filePath);
  source = source.replace(
    /import\s*\{[\s\S]*?\}\s*from\s*["']\.\/publicData(?:\.js)?["'];/,
    `
const 建立公開資料網址 = (相對路徑) => \`/mock/\${String(相對路徑)}\`;
const 建立使用者預設資料網址 = (角色名稱) => \`/mock/data/users/\${String(角色名稱)}.json\`;
`,
  );

  const moduleUrl = `data:text/javascript;base64,${Buffer.from(source, "utf8").toString("base64")}`;
  return import(moduleUrl);
}

async function validateUserSearchResolution() {
  const module = await loadUserDataTestModule();
  const users = [
    {
      character_name: "Shibe柴",
      servers: ["利維坦"],
      file_path: "data/users/Shibe柴.json",
    },
  ];

  const pureNameTarget = module.解析使用者搜尋目標("Shibe柴", users);
  assert(pureNameTarget.角色名稱 === "Shibe柴", "純玩家名稱搜尋應解析到索引中的正式玩家名稱");
  assert(pureNameTarget.伺服器 === "利維坦", "純玩家名稱搜尋應由使用者索引補上主要伺服器");
  assert(
    module.格式化使用者搜尋文字(pureNameTarget.角色名稱, pureNameTarget.伺服器) === "Shibe柴 @ 利維坦",
    "純玩家名稱搜尋成功後應能正規化為「玩家 @ 伺服器」格式",
  );

  const formattedTarget = module.解析使用者搜尋目標("Shibe柴 @ 利維坦", users);
  assert(formattedTarget.角色名稱 === "Shibe柴" && formattedTarget.伺服器 === "利維坦", "已含伺服器的搜尋文字仍應解析成功");
  const compactTarget = module.解析使用者搜尋目標("Shibe柴@利維坦", users);
  assert(compactTarget.角色名稱 === "Shibe柴" && compactTarget.伺服器 === "利維坦", "沒有空白的玩家伺服器格式仍應解析成功");

  const indexEntry = module.尋找使用者索引條目(users, "shibe柴");
  assert(indexEntry?.file_path === "data/users/Shibe柴.json", "使用者索引查找應支援純玩家名稱大小寫差異");
}

function installUrlStateWindow(href, events) {
  globalThis.CustomEvent = class CustomEvent {
    constructor(type) {
      this.type = type;
    }
  };
  globalThis.window = {
    location: new URL(href),
    history: {
      replaceState(_state, _title, nextUrl) {
        globalThis.window.location = new URL(nextUrl, globalThis.window.location.href);
      },
      pushState(_state, _title, nextUrl) {
        globalThis.window.location = new URL(nextUrl, globalThis.window.location.href);
      },
    },
    dispatchEvent(event) {
      events.push(event.type);
    },
  };
}

async function validateShareUrlStateCompatibility() {
  const module = await loadUrlStateTestModule();
  if (!module) {
    return;
  }

  const cases = [
    {
      label: "舊版個人成績單 query",
      href: "https://ranking.init.engineer/?user=Aa&server=%E5%A5%A7%E6%B1%80",
      expected: { page: "user", user: "Aa", server: "奧汀" },
    },
    {
      label: "個人成績單乾淨路徑",
      href: "https://ranking.init.engineer/user/Aa?server=%E5%A5%A7%E6%B1%80",
      expected: { page: "user", user: "Aa", server: "奧汀" },
    },
    {
      label: "副本全服統計乾淨路徑",
      href: "https://ranking.init.engineer/stats/savage_m1s?server=%E9%B3%B3%E5%87%B0&metric=rdps&version=valid",
      expected: { page: "stats", encounter: "savage_m1s", server: "鳳凰", metric: "rdps", version: "valid" },
    },
    {
      label: "玩家比較版本 query",
      href: "https://ranking.init.engineer/compare?left=Aa&right=Bb&encounter=extreme_zoraal_ja&version=obsolete",
      expected: { page: "compare", left: "Aa", right: "Bb", encounter: "extreme_zoraal_ja", version: "obsolete" },
    },
    {
      label: "隊伍榜版本 query",
      href: "https://ranking.init.engineer/teams?encounter=extreme_valigarmanda&version=valid",
      expected: { page: "teams", encounter: "extreme_valigarmanda", version: "valid" },
    },
    {
      label: "職業分析乾淨路徑",
      href: "https://ranking.init.engineer/jobs/Paladin",
      expected: { page: "jobs", job: "Paladin" },
    },
    {
      label: "伺服器對比乾淨路徑",
      href: "https://ranking.init.engineer/servers/%E9%B3%B3%E5%87%B0/vs/%E4%BC%8A%E5%BC%97%E5%88%A9%E7%89%B9",
      expected: { page: "servers", left: "鳳凰", right: "伊弗利特" },
    },
    {
      label: "舊版伺服器對比 query",
      href: "https://ranking.init.engineer/servers?left=%E9%B3%B3%E5%87%B0&right=%E4%BC%8A%E5%BC%97%E5%88%A9%E7%89%B9",
      expected: { page: "servers", left: "鳳凰", right: "伊弗利特" },
    },
    {
      label: "Honey B. Lovely 粉絲榜乾淨路徑",
      href: "https://ranking.init.engineer/honey-fans",
      expected: { page: "honey-fans" },
    },
  ];

  const events = [];
  for (const testCase of cases) {
    installUrlStateWindow(testCase.href, events);
    const state = module.readState();
    for (const [key, value] of Object.entries(testCase.expected)) {
      assert(state[key] === value, `${testCase.label} 解析失敗：${key} 應為 ${value}，實際為 ${state[key]}`);
    }
  }

  installUrlStateWindow("https://example.test/repo/stats/savage_m1s?server=x", events);
  module.writeState({ page: "jobs", job: "Paladin" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://example.test/repo/jobs/Paladin",
    "子路徑部署下從 /stats/{副本} 寫入 /jobs/{職業} 時，必須保留部署基底路徑",
  );
  assert(events.includes("ffxivtc:urlchange"), "寫入分享網址後必須送出自訂事件，讓 SEO/OG meta 同步更新");

  installUrlStateWindow("https://ranking.init.engineer/?encounter=savage_m1s&version=valid", events);
  module.writeState({ page: "ranking", encounter: "extreme_zoraal_ja", version: "obsolete" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/?encounter=extreme_zoraal_ja&version=obsolete",
    "排行榜分享網址必須保留版本篩選 query",
  );

  installUrlStateWindow("https://ranking.init.engineer/?encounter=savage_m1s&server=%E9%B3%B3%E5%87%B0&jobType=role%3Ahealer&job=WhiteMage", events);
  module.writeState(
    { page: "ranking", encounter: "savage_m2s", server: "鳳凰", jobType: "role:healer", job: "WhiteMage" },
    { replace: true },
  );
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/?encounter=savage_m2s&server=%E9%B3%B3%E5%87%B0&jobType=role%3Ahealer&job=WhiteMage",
    "排行榜切換副本後的分享網址必須保留伺服器與職業篩選 query",
  );

  installUrlStateWindow("https://ranking.init.engineer/stats/savage_m1s?server=%E9%B3%B3%E5%87%B0&jobScope=WhiteMage", events);
  module.writeState({ page: "stats", encounter: "savage_m2s", server: "鳳凰", jobScope: "WhiteMage" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/stats/savage_m2s?server=%E9%B3%B3%E5%87%B0&jobScope=WhiteMage",
    "全服統計切換副本後的分享網址必須保留伺服器與職業範圍 query",
  );

  installUrlStateWindow("https://ranking.init.engineer/servers?left=a&right=b", events);
  module.writeState({ page: "servers", left: "鳳凰", right: "伊弗利特" }, { replace: true });
  assert(
    globalThis.window.location.href ===
      "https://ranking.init.engineer/servers/%E9%B3%B3%E5%87%B0/vs/%E4%BC%8A%E5%BC%97%E5%88%A9%E7%89%B9",
    "伺服器對比分享網址必須寫成 /servers/{left}/vs/{right}",
  );

  installUrlStateWindow("https://ranking.init.engineer/activity", events);
  module.writeState({ page: "honey-fans" }, { replace: true });
  assert(
    globalThis.window.location.href === "https://ranking.init.engineer/honey-fans",
    "Honey B. Lovely 粉絲榜分享網址必須寫成 /honey-fans",
  );

  delete globalThis.window;
  delete globalThis.CustomEvent;
}

async function main() {
  await validateUseRankingAppReturnBindings();
  await validateFrontendFetchBoundary();
  await validateEncounterSwitchFilterPersistence();
  await validatePublicDataForFrontend();
  validateScopedJobShareRecalculation();
  await validateUserSearchResolution();
  await validateShareUrlStateCompatibility();

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
