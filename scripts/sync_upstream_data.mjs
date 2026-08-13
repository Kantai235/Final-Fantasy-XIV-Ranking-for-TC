import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

// 這支工具處理「本機爬蟲」與「GitHub Actions 排程」同時產生資料時的合併。
// 它只管理 append-only 資料與衍生 public/data 產物；一般程式碼衝突仍應交給 Git 人工處理。
const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const maxBuffer = 1024 * 1024 * 512;
const missing = Symbol("missing");
const rankingReportShardTargetBytes = 45 * 1024 * 1024;

class ToolError extends Error {
  constructor(message, details = []) {
    super(message);
    this.details = details;
  }
}

function printUsage() {
  console.log(`Usage: npm run sync:data -- [options]

Fetch and merge upstream ranking data with local scraper output.

Options:
  --remote-ref <ref>  Upstream ref to merge. Defaults to the current branch upstream, or origin/main.
  --no-fetch         Skip git fetch before merging.
  --no-rebuild       Do not rebuild public/data after merging source data.
  --allow-dirty-other
                     Ignore dirty non-data files unless upstream also touches them.
  --accept-protected-removals <count>
                     Continue only when a manual audit found exactly this many protected removals.
                     The merged output still restores the append-only union; conflicts remain blocked.
  --repair-merge-ref <ref>
                     Rebuild source data from an existing two-parent merge after improving merge rules.
  --dry-run          Check what would be merged without changing files.
  --help             Show this help.
`);
}

function parseArgs(argv) {
  const options = {
    dryRun: false,
    fetch: true,
    rebuild: true,
    allowDirtyOther: false,
    acceptedProtectedRemovals: null,
    repairMergeRef: null,
    remoteRef: null,
  };

  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--dry-run") {
      options.dryRun = true;
    } else if (arg === "--no-fetch") {
      options.fetch = false;
    } else if (arg === "--no-rebuild") {
      options.rebuild = false;
    } else if (arg === "--allow-dirty-other") {
      options.allowDirtyOther = true;
    } else if (arg === "--accept-protected-removals") {
      const rawCount = argv[index + 1];
      index += 1;
      const count = Number(rawCount);
      if (!Number.isSafeInteger(count) || count <= 0) {
        throw new ToolError("--accept-protected-removals needs a positive integer from the completed dry-run audit.");
      }
      options.acceptedProtectedRemovals = count;
    } else if (arg === "--repair-merge-ref") {
      options.repairMergeRef = argv[index + 1];
      index += 1;
      if (!options.repairMergeRef) {
        throw new ToolError("--repair-merge-ref needs a merge commit ref.");
      }
    } else if (arg === "--remote-ref" || arg === "-r") {
      options.remoteRef = argv[index + 1];
      index += 1;
      if (!options.remoteRef) {
        throw new ToolError("--remote-ref needs a ref name.");
      }
    } else if (arg === "--help" || arg === "-h") {
      printUsage();
      process.exit(0);
    } else {
      throw new ToolError(`Unknown option: ${arg}`);
    }
  }

  return options;
}

function normalizePath(filePath) {
  return filePath.replace(/\\/g, "/");
}

function isCheckedReportsShardPath(filePath) {
  const normalized = normalizePath(filePath);
  return normalized.startsWith("data/state/checked_reports/") && normalized.endsWith(".json");
}

function isRankingReportShardPath(filePath) {
  const normalized = normalizePath(filePath);
  return /^data\/rankings\/[^/]+\.reports\/[^/]+\.json$/.test(normalized);
}

function rankingKeyFromPath(filePath) {
  const normalized = normalizePath(filePath);
  const mainMatch = normalized.match(/^data\/rankings\/([^/]+)\.json$/);
  if (mainMatch) {
    return mainMatch[1];
  }
  const shardMatch = normalized.match(/^data\/rankings\/([^/]+)\.reports\/[^/]+\.json$/);
  return shardMatch?.[1] || null;
}

function usesShardedCheckedReports(state) {
  return state?.checked_reports_storage?.format === "encounter_shards_v1";
}

function isSourceDataPath(filePath) {
  // 來源資料是不可逆歷史資產：encounter key、state report 狀態（含分片）與完整排行榜
  // 報告都不能被靜默刪除。checked_reports 雖然已離開單一 state.json，仍維持 append-only
  // 同步保護，避免本機與 workflow 同時寫入時遺失跨輪略過依據。
  const normalized = normalizePath(filePath);
  return (
    normalized === "config/encounters.json" ||
    normalized === "data/state.json" ||
    isCheckedReportsShardPath(normalized) ||
    (normalized.startsWith("data/rankings/") && normalized.endsWith(".json"))
  );
}

function isGeneratedDataPath(filePath) {
  // 衍生資料可由來源資料重建；合併衝突時通常採用上游或重建結果，而不是手工拼接。
  const normalized = normalizePath(filePath);
  return (
    normalized.startsWith("public/data/") &&
    (normalized.endsWith(".json") || normalized.endsWith(".jsonl"))
  );
}

function isLatestSnapshotDataPath(filePath) {
  const normalized = normalizePath(filePath);
  return (
    normalized === "data/fun/honey_b_fans.json" ||
    normalized === "data/pages_payload_history.jsonl" ||
    normalized === "data/update_status.json"
  );
}

function isManagedPath(filePath) {
  return isSourceDataPath(filePath) || isLatestSnapshotDataPath(filePath) || isGeneratedDataPath(filePath);
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, {
    cwd: rootDir,
    encoding: "utf8",
    maxBuffer,
    windowsHide: true,
    ...options.spawnOptions,
  });

  if (result.error) {
    throw result.error;
  }
  if (result.status !== 0 && !options.allowFailure) {
    const rendered = [command, ...args].join(" ");
    throw new ToolError(`${rendered} failed.`, [result.stderr || result.stdout || ""]);
  }
  return result;
}

function git(args, options = {}) {
  return run("git", args, options);
}

function gitText(args, options = {}) {
  return git(args, options).stdout;
}

function ensureGitReady() {
  git(["rev-parse", "--show-toplevel"]);
  const gitDir = gitText(["rev-parse", "--git-dir"]).trim();
  const mergeHeadPath = path.resolve(rootDir, gitDir, "MERGE_HEAD");
  const rebaseMergePath = path.resolve(rootDir, gitDir, "rebase-merge");
  const rebaseApplyPath = path.resolve(rootDir, gitDir, "rebase-apply");
  if (existsSync(mergeHeadPath) || existsSync(rebaseMergePath) || existsSync(rebaseApplyPath)) {
    throw new ToolError("A merge or rebase is already in progress. Finish or abort it before running this tool.");
  }
}

function parsePorcelainZ(output) {
  const records = output.split("\0").filter(Boolean);
  const entries = [];

  for (let index = 0; index < records.length; index += 1) {
    const record = records[index];
    const xy = record.slice(0, 2);
    const filePath = normalizePath(record.slice(3));
    const entry = { xy, path: filePath };
    entries.push(entry);
    if (xy[0] === "R" || xy[0] === "C") {
      index += 1;
      entry.originalPath = normalizePath(records[index] || "");
    }
  }

  return entries;
}

function getDirtyEntries() {
  const entries = parsePorcelainZ(gitText(["status", "--porcelain=v1", "-z"]));
  const expandedEntries = [];
  for (const entry of entries) {
    // Git 會把全新的 data/state/ 顯示成單一未追蹤目錄，導致內部 JSON 分片未參與
    // append-only 預檢。展開檔案後才能讓每個 checked_reports 分片接受相同保護。
    if (entry.xy !== "??" || !entry.path.endsWith("/")) {
      expandedEntries.push(entry);
      continue;
    }
    const directoryPath = path.join(rootDir, entry.path);
    if (!existsSync(directoryPath)) {
      expandedEntries.push(entry);
      continue;
    }
    const pendingDirectories = [directoryPath];
    while (pendingDirectories.length) {
      const currentDirectory = pendingDirectories.pop();
      for (const child of readdirSync(currentDirectory, { withFileTypes: true })) {
        const childPath = path.join(currentDirectory, child.name);
        if (child.isDirectory()) {
          pendingDirectories.push(childPath);
        } else if (child.isFile()) {
          expandedEntries.push({
            ...entry,
            path: normalizePath(path.relative(rootDir, childPath)),
          });
        }
      }
    }
  }
  return expandedEntries;
}

function hasUnmergedStatus(xy) {
  return xy.includes("U") || xy === "AA" || xy === "DD";
}

function getChangedFiles(leftRef, rightRef) {
  if (leftRef === rightRef) {
    return [];
  }
  return gitText(["diff", "--name-only", "-z", leftRef, rightRef])
    .split("\0")
    .filter(Boolean)
    .map(normalizePath);
}

function resolveUpstreamRef(explicitRef) {
  if (explicitRef) {
    return explicitRef;
  }
  const upstream = git(["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], { allowFailure: true });
  const ref = upstream.status === 0 ? upstream.stdout.trim() : "";
  return ref || "origin/main";
}

function fetchUpstream(upstreamRef) {
  const remoteName = upstreamRef.includes("/") ? upstreamRef.split("/")[0] : null;
  if (remoteName) {
    console.log(`Fetching ${remoteName}...`);
    git(["fetch", "--prune", remoteName]);
  } else {
    console.log("Fetching all remotes...");
    git(["fetch", "--all", "--prune"]);
  }
}

function readGitJson(ref, relPath) {
  const objectRef = `${ref}:${relPath}`;
  const exists = git(["cat-file", "-e", objectRef], { allowFailure: true });
  if (exists.status !== 0) {
    return missing;
  }
  const text = gitText(["show", objectRef]);
  return JSON.parse(text);
}

async function readWorkingJson(relPath) {
  try {
    return JSON.parse(await readFile(path.join(rootDir, relPath), "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      return missing;
    }
    throw error;
  }
}

function readIndexJson(stage, relPath) {
  const result = git(["show", `:${stage}:${relPath}`], { allowFailure: true });
  if (result.status !== 0) {
    return missing;
  }
  return JSON.parse(result.stdout);
}

function readIndexText(stage, relPath) {
  const result = git(["show", `:${stage}:${relPath}`], { allowFailure: true });
  return result.status === 0 ? result.stdout : missing;
}

function readGitRankingGroup(ref, rankingKey) {
  const mainPath = `data/rankings/${rankingKey}.json`;
  const main = readGitJson(ref, mainPath);
  if (main === missing) {
    return { value: missing, paths: new Set() };
  }

  const reports = { ...asObject(main.reports) };
  const paths = new Set([mainPath]);
  for (const shardPath of Array.isArray(main.report_shards) ? main.report_shards : []) {
    if (typeof shardPath !== "string" || !isRankingReportShardPath(shardPath)) {
      throw new ToolError(`Invalid ranking report shard path in ${ref}:${mainPath}.`, [String(shardPath)]);
    }
    paths.add(shardPath);
    const shard = readGitJson(ref, shardPath);
    if (shard === missing || !isPlainObject(shard)) {
      throw new ToolError(`Ranking report shard is missing or invalid in ${ref}.`, [shardPath]);
    }
    for (const [reportCode, report] of Object.entries(shard)) {
      if (reportCode in reports && !sameJson(reports[reportCode], report)) {
        throw new ToolError(`Ranking report code appears with conflicting payloads in ${ref}.`, [
          `${rankingKey}:${reportCode}`,
        ]);
      }
      reports[reportCode] = report;
    }
  }

  const value = cloneJson(main);
  delete value.report_shards;
  value.reports = reports;
  return { value, paths };
}

async function readWorkingRankingGroup(rankingKey) {
  const mainPath = `data/rankings/${rankingKey}.json`;
  const main = await readWorkingJson(mainPath);
  if (main === missing) {
    return { value: missing, paths: new Set() };
  }
  const reports = { ...asObject(main.reports) };
  const paths = new Set([mainPath]);
  for (const shardPath of Array.isArray(main.report_shards) ? main.report_shards : []) {
    if (typeof shardPath !== "string" || !isRankingReportShardPath(shardPath)) {
      throw new ToolError(`Invalid working ranking report shard path in ${mainPath}.`, [String(shardPath)]);
    }
    paths.add(shardPath);
    const shard = await readWorkingJson(shardPath);
    if (shard === missing || !isPlainObject(shard)) {
      throw new ToolError("Working ranking report shard is missing or invalid.", [shardPath]);
    }
    for (const [reportCode, report] of Object.entries(shard)) {
      if (reportCode in reports && !sameJson(reports[reportCode], report)) {
        throw new ToolError("Working ranking report code appears with conflicting payloads.", [
          `${rankingKey}:${reportCode}`,
        ]);
      }
      reports[reportCode] = report;
    }
  }
  const value = cloneJson(main);
  delete value.report_shards;
  value.reports = reports;
  return { value, paths };
}

function readPlannedRankingGroup(mergedByPath, rankingKey) {
  const mainPath = `data/rankings/${rankingKey}.json`;
  const main = mergedByPath.get(mainPath);
  if (!main) {
    return null;
  }
  const reports = { ...asObject(main.reports) };
  const paths = new Set([mainPath]);
  for (const shardPath of Array.isArray(main.report_shards) ? main.report_shards : []) {
    const shard = mergedByPath.get(shardPath);
    if (!isPlainObject(shard)) {
      throw new ToolError("Committed merge plan is missing a ranking report shard.", [shardPath]);
    }
    paths.add(shardPath);
    Object.assign(reports, shard);
  }
  const value = cloneJson(main);
  delete value.report_shards;
  value.reports = reports;
  return { value, paths };
}

function buildRankingGroupFiles(rankingKey, ranking) {
  const mainPath = `data/rankings/${rankingKey}.json`;
  const main = cloneJson(ranking);
  const reports = asObject(main.reports);
  delete main.reports;
  delete main.report_shards;

  const files = new Map();
  const shardPaths = [];
  let currentShard = {};
  let currentSize = 2;

  const flushShard = () => {
    if (!Object.keys(currentShard).length) {
      return;
    }
    const shardPath = `data/rankings/${rankingKey}.reports/${String(shardPaths.length).padStart(3, "0")}.json`;
    shardPaths.push(shardPath);
    files.set(shardPath, currentShard);
    currentShard = {};
    currentSize = 2;
  };

  for (const reportCode of Object.keys(reports).sort()) {
    const report = reports[reportCode];
    if (!isPlainObject(report)) {
      continue;
    }
    const reportText = JSON.stringify(report);
    const itemSize = Buffer.byteLength(JSON.stringify(reportCode), "utf8") + 1 + Buffer.byteLength(reportText, "utf8") + 1;
    if (Object.keys(currentShard).length && currentSize + itemSize > rankingReportShardTargetBytes) {
      flushShard();
    }
    currentShard[reportCode] = report;
    currentSize += itemSize;
  }
  flushShard();

  if (shardPaths.length) {
    main.report_shards = shardPaths;
  } else {
    main.reports = {};
  }
  files.set(mainPath, main);
  return files;
}

function cloneJson(value) {
  if (value === missing) {
    return missing;
  }
  return JSON.parse(JSON.stringify(value));
}

const fingerprintCache = new WeakMap();

function stableStringify(value) {
  if (value === missing) {
    return "<missing>";
  }
  if (value === null || typeof value !== "object") {
    return JSON.stringify(value);
  }
  const cached = fingerprintCache.get(value);
  if (cached) {
    return cached;
  }
  let rendered;
  if (Array.isArray(value)) {
    rendered = `[${value.map(stableStringify).join(",")}]`;
  } else {
    rendered = `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
      .join(",")}}`;
  }
  fingerprintCache.set(value, rendered);
  return rendered;
}

function sameJson(left, right) {
  if (left === right) {
    return true;
  }
  return stableStringify(left) === stableStringify(right);
}

function orderedUnion(...lists) {
  const seen = new Set();
  const output = [];
  for (const list of lists) {
    for (const value of list || []) {
      if (!seen.has(value)) {
        seen.add(value);
        output.push(value);
      }
    }
  }
  return output;
}

function reportIssue(issues, type, pathParts, message) {
  issues[type].push({
    path: pathParts.join("."),
    message,
  });
}

function asObject(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function keySet(value) {
  return new Set(Object.keys(asObject(value)));
}

function checkRemovedKeys(issues, label, baseMap, sideMap, sideName) {
  if (!baseMap || typeof baseMap !== "object") {
    return;
  }
  if (!sideMap || typeof sideMap !== "object") {
    for (const key of Object.keys(baseMap)) {
      reportIssue(issues, "removals", [label, key], `${sideName} removed protected data.`);
    }
    return;
  }
  for (const key of Object.keys(baseMap)) {
    if (!(key in sideMap)) {
      reportIssue(issues, "removals", [label, key], `${sideName} removed protected data.`);
    }
  }
}

function itemKeyForArray(pathParts, item) {
  const name = pathParts.at(-1);
  if (!item || typeof item !== "object" || Array.isArray(item)) {
    return null;
  }
  if (name === "ranking_entries") {
    return rankingEntryKey(item);
  }
  if (name === "fights") {
    return item.fight_hash || (item.fight_id == null ? null : String(item.fight_id));
  }
  if (name === "players" || name === "matched_players") {
    return playerKey(item);
  }
  if (item.key != null) {
    return String(item.key);
  }
  if (item.id != null) {
    return String(item.id);
  }
  if (item.report_code != null) {
    return String(item.report_code);
  }
  return null;
}

function checkRemovedArrayItems(issues, label, baseArray, sideArray, sideName, keyFunction) {
  if (!Array.isArray(baseArray)) {
    return;
  }
  if (!Array.isArray(sideArray)) {
    for (const item of baseArray) {
      const key = keyFunction(item);
      if (key) {
        reportIssue(issues, "removals", [label, key], `${sideName} removed protected data.`);
      }
    }
    return;
  }

  const sideKeys = new Set(sideArray.map(keyFunction).filter(Boolean));
  for (const item of baseArray) {
    const key = keyFunction(item);
    if (key && !sideKeys.has(key)) {
      reportIssue(issues, "removals", [label, key], `${sideName} removed protected data.`);
    }
  }
}

function checkProtectedRemovals(relPath, base, side, sideName, issues) {
  // 任何一邊刪掉受保護鍵值都視為 REMOVAL，而不是自動接受。
  // 這能避免歷史 report、checked_reports 或 encounter key 在同步時被不小心洗掉。
  if (base === missing) {
    return;
  }
  if (side === missing) {
    reportIssue(issues, "removals", [relPath], `${sideName} removed the source data file.`);
    return;
  }

  if (relPath === "config/encounters.json") {
    checkRemovedArrayItems(issues, `${relPath}:encounters`, base, side, sideName, (item) => item?.key);
    return;
  }

  if (isCheckedReportsShardPath(relPath)) {
    checkRemovedKeys(issues, relPath, base, side, sideName);
    return;
  }

  if (isRankingReportShardPath(relPath)) {
    checkRemovedKeys(issues, `${relPath}:reports`, base, side, sideName);
    for (const reportCode of Object.keys(asObject(base))) {
      const baseReport = base?.[reportCode];
      const sideReport = side?.[reportCode];
      checkRemovedArrayItems(
        issues,
        `${relPath}:reports.${reportCode}.fights`,
        baseReport?.fights,
        sideReport?.fights,
        sideName,
        (fight) => fight?.fight_hash || (fight?.fight_id == null ? null : String(fight.fight_id)),
      );
    }
    return;
  }

  if (relPath === "data/state.json") {
    checkRemovedKeys(issues, `${relPath}:encounters`, base.encounters, side.encounters, sideName);
    if (usesShardedCheckedReports(side)) {
      // 分片遷移把 checkpoint 從主檔移到受保護的 data/state/checked_reports/*.json。
      // 此時主檔少了 checked_reports 是儲存位置改變，不是刪除；各分片會在本輪
      // sync 預檢中逐一驗證 report code 沒有遺失。
      return;
    }
    for (const encounterKey of Object.keys(base.encounters || {})) {
      const baseEncounter = base.encounters?.[encounterKey];
      const sideEncounter = side.encounters?.[encounterKey];
      checkRemovedKeys(
        issues,
        `${relPath}:encounters.${encounterKey}.checked_reports`,
        baseEncounter?.checked_reports,
        sideEncounter?.checked_reports,
        sideName,
      );
      // processed_reports 是單輪 checkpoint，fetch_fflogs.py 成功完成一輪後會清空；
      // checked_reports 才是跨輪保留的已檢查快取，因此這裡只把 checked_reports 視為同步保護資料。
    }
    return;
  }

  if (relPath.startsWith("data/rankings/")) {
    checkRemovedKeys(issues, `${relPath}:reports`, base.reports, side.reports, sideName);
    for (const reportCode of Object.keys(base.reports || {})) {
      const baseReport = base.reports?.[reportCode];
      const sideReport = side.reports?.[reportCode];
      checkRemovedArrayItems(
        issues,
        `${relPath}:reports.${reportCode}.fights`,
        baseReport?.fights,
        sideReport?.fights,
        sideName,
        (fight) => fight?.fight_hash || (fight?.fight_id == null ? null : String(fight.fight_id)),
      );
    }
  }
}

function countProtectedAdditions(relPath, base, side) {
  if (base === missing || side === missing) {
    return 0;
  }
  let count = 0;
  if (isCheckedReportsShardPath(relPath)) {
    // checked_reports 分片可能累積數十萬筆 report。基準 Set 必須只建立一次；
    // 若在 filter 回呼內重建，會讓單純的新增計數退化成平方級運算，造成同步預檢長時間無進度。
    const baseKeys = keySet(base);
    return [...keySet(side)].filter((key) => !baseKeys.has(key)).length;
  }
  if (isRankingReportShardPath(relPath)) {
    const baseKeys = keySet(base);
    return [...keySet(side)].filter((key) => !baseKeys.has(key)).length;
  }
  if (relPath === "data/state.json") {
    for (const [encounterKey, encounter] of Object.entries(side.encounters || {})) {
      const baseEncounter = base.encounters?.[encounterKey] || {};
      const baseCheckedReports = keySet(baseEncounter.checked_reports);
      const baseProcessedReports = keySet(baseEncounter.processed_reports);
      count += [...keySet(encounter.checked_reports)].filter((key) => !baseCheckedReports.has(key)).length;
      count += [...keySet(encounter.processed_reports)].filter((key) => !baseProcessedReports.has(key)).length;
    }
  } else if (relPath.startsWith("data/rankings/")) {
    const baseReports = keySet(base.reports);
    count += [...keySet(side.reports)].filter((key) => !baseReports.has(key)).length;
  } else if (relPath === "config/encounters.json" && Array.isArray(side)) {
    const baseKeys = new Set(Array.isArray(base) ? base.map((item) => item?.key).filter(Boolean) : []);
    count += side.filter((item) => item?.key && !baseKeys.has(item.key)).length;
  }
  return count;
}

function isPlainObject(value) {
  return value && typeof value === "object" && !Array.isArray(value);
}

function isScalar(value) {
  return value === missing || value === null || typeof value !== "object";
}

function isTimestampKey(pathParts) {
  const key = pathParts.at(-1) || "";
  return key.endsWith("_at") || key === "updated_at" || key === "recorded_at" || key === "fetched_at";
}

function isIsoTimestampKey(pathParts) {
  const key = pathParts.at(-1) || "";
  return key.endsWith("_at_iso") || key.endsWith("_time_iso");
}

function latestIso(left, right) {
  const leftTime = Date.parse(left);
  const rightTime = Date.parse(right);
  if (Number.isFinite(leftTime) && Number.isFinite(rightTime)) {
    return rightTime >= leftTime ? right : left;
  }
  return String(right) >= String(left) ? right : left;
}

function statusScore(status) {
  const scores = {
    saved: 4,
    skipped_no_clear: 3,
    skipped_no_traditional_chinese_players: 2,
    failed: 1,
  };
  return scores[status] || 0;
}

function isCounterKey(key) {
  return (
    key.endsWith("_count") ||
    key.endsWith("_reports") ||
    key === "reports_found" ||
    key === "reports_selected" ||
    key === "reports_skipped_known" ||
    key === "reports_deferred" ||
    key === "reports_saved" ||
    key === "rankings_inserted_or_updated" ||
    key.endsWith("_reports_found") ||
    key.endsWith("_reports_selected") ||
    key.endsWith("_reports_skipped_known") ||
    key.endsWith("_reports_deferred") ||
    key === "duplicate_count" ||
    key === "rank"
  );
}

function resolveScalar(base, local, remote, pathParts, issues) {
  const key = pathParts.at(-1) || "";
  if (typeof local === "number" && typeof remote === "number") {
    if (key === "calculation_version" && pathParts.includes("data_integrity")) {
      // 同一場戰鬥可能被本機與 workflow 以不同版本的完整性規則重算；版本號較大者
      // 代表較新的站務判定，必須與下方 ruleset 一起採新版本，不能視為任意數值衝突。
      return Math.max(local, remote);
    }
    if (isTimestampKey(pathParts) || isCounterKey(key)) {
      return Math.max(local, remote);
    }
  }
  if (typeof local === "string" && typeof remote === "string") {
    if (isIsoTimestampKey(pathParts)) {
      return latestIso(local, remote);
    }
    if (key === "status") {
      return statusScore(remote) > statusScore(local) ? remote : local;
    }
    if (key === "ruleset" && pathParts.includes("data_integrity")) {
      const localVersion = Number(local.match(/(?:^|_)v(\d+)(?:_|$)/)?.[1]);
      const remoteVersion = Number(remote.match(/(?:^|_)v(\d+)(?:_|$)/)?.[1]);
      if (Number.isSafeInteger(localVersion) && Number.isSafeInteger(remoteVersion) && localVersion !== remoteVersion) {
        return remoteVersion > localVersion ? remote : local;
      }
    }
  }
  reportIssue(
    issues,
    "conflicts",
    pathParts,
    `Both sides changed a scalar value differently from ${JSON.stringify(base)} to ${JSON.stringify(local)} and ${JSON.stringify(remote)}.`,
  );
  return cloneJson(local);
}

function playerKey(player) {
  if (!player || typeof player !== "object") {
    return null;
  }
  if (player.fflogs_guid != null) {
    return `guid:${player.fflogs_guid}`;
  }
  if (player.fflogs_id != null) {
    return `id:${player.fflogs_id}`;
  }
  const name = player.name || player.character_name;
  if (name && player.server && player.job) {
    return `${name}@${player.server}:${player.job}`;
  }
  return null;
}

function rankingEntryKey(entry) {
  if (!entry || typeof entry !== "object") {
    return null;
  }
  if (entry.character_key && entry.job) {
    return `${entry.character_key}:${entry.job}`;
  }
  if (entry.character_name && entry.server && entry.job) {
    return `${entry.character_name}@${entry.server}:${entry.job}`;
  }
  return entry.id || null;
}

function toNumber(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function entryScore(entry) {
  return toNumber(entry?.rdps ?? entry?.dps) || 0;
}

function isBetterEntry(candidate, currentBest) {
  if (!currentBest) {
    return true;
  }
  const candidateScore = entryScore(candidate);
  const currentScore = entryScore(currentBest);
  if (candidateScore !== currentScore) {
    return candidateScore > currentScore;
  }
  const candidateClear = toNumber(candidate?.clear_time_seconds) ?? Number.POSITIVE_INFINITY;
  const currentClear = toNumber(currentBest?.clear_time_seconds) ?? Number.POSITIVE_INFINITY;
  if (candidateClear !== currentClear) {
    return candidateClear < currentClear;
  }
  const candidateAdps = toNumber(candidate?.adps ?? candidate?.dps) || 0;
  const currentAdps = toNumber(currentBest?.adps ?? currentBest?.dps) || 0;
  if (candidateAdps !== currentAdps) {
    return candidateAdps > currentAdps;
  }
  const candidateTime = Date.parse(candidate?.recorded_at_iso || 0) || 0;
  const currentTime = Date.parse(currentBest?.recorded_at_iso || 0) || 0;
  return candidateTime > currentTime;
}

function compareRankingEntries(left, right) {
  if (isBetterEntry(left, right)) {
    return -1;
  }
  if (isBetterEntry(right, left)) {
    return 1;
  }
  return String(left.character_key || left.id || "").localeCompare(String(right.character_key || right.id || ""));
}

function mergePrimitiveArray(base, local, remote) {
  const values = [];
  const seen = new Set();
  for (const item of [...(Array.isArray(base) ? base : []), ...(Array.isArray(local) ? local : []), ...(Array.isArray(remote) ? remote : [])]) {
    const key = stableStringify(item);
    if (!seen.has(key)) {
      seen.add(key);
      values.push(cloneJson(item));
    }
  }
  return values;
}

function mergeRankingEntries(base, local, remote, pathParts, issues) {
  // ranking_entries 是完整 reports 的扁平索引；同一角色同一職業以最佳成績合併並重新排名。
  // 若雙方是同一筆 id，source_reports 與 duplicate_count 會保留雙方來源，方便追查重複上傳。
  const baseMap = new Map((Array.isArray(base) ? base : []).map((item) => [rankingEntryKey(item), item]).filter(([key]) => key));
  const localMap = new Map((Array.isArray(local) ? local : []).map((item) => [rankingEntryKey(item), item]).filter(([key]) => key));
  const remoteMap = new Map((Array.isArray(remote) ? remote : []).map((item) => [rankingEntryKey(item), item]).filter(([key]) => key));
  const merged = [];

  for (const key of orderedUnion([...baseMap.keys()], [...localMap.keys()], [...remoteMap.keys()])) {
    const baseItem = baseMap.get(key) ?? missing;
    const localItem = localMap.get(key) ?? missing;
    const remoteItem = remoteMap.get(key) ?? missing;

    if (localItem === missing && remoteItem === missing) {
      continue;
    }
    if (localItem === missing) {
      merged.push(cloneJson(remoteItem));
      continue;
    }
    if (remoteItem === missing) {
      merged.push(cloneJson(localItem));
      continue;
    }
    if (sameJson(localItem, remoteItem)) {
      merged.push(cloneJson(localItem));
      continue;
    }
    if (sameJson(baseItem, localItem)) {
      merged.push(cloneJson(remoteItem));
      continue;
    }
    if (sameJson(baseItem, remoteItem)) {
      merged.push(cloneJson(localItem));
      continue;
    }

    const chosen = isBetterEntry(localItem, remoteItem) ? localItem : remoteItem;
    const output = cloneJson(chosen);
    if (localItem.id === remoteItem.id) {
      output.source_reports = mergePrimitiveArray([], localItem.source_reports || [], remoteItem.source_reports || []);
      output.duplicate_count = Math.max(
        toNumber(localItem.duplicate_count) || 1,
        toNumber(remoteItem.duplicate_count) || 1,
        output.source_reports.length || 1,
      );
    }
    merged.push(output);
  }

  merged.sort(compareRankingEntries);
  merged.forEach((entry, index) => {
    entry.rank = index + 1;
  });
  return merged;
}

function recordTime(record) {
  if (!record || typeof record !== "object") {
    return 0;
  }
  const numericTime = toNumber(record.processed_at) ?? toNumber(record.updated_at) ?? toNumber(record.fetched_at);
  if (numericTime !== null) {
    return numericTime;
  }
  return Date.parse(record.processed_at_iso || record.updated_at_iso || record.fetched_at_iso || 0) || 0;
}

function checkpointSignatureTime(record) {
  const time = recordTime(record);
  return time > 0 ? time : "";
}

function chooseStatusRecord(base, local, remote) {
  const signature = (record) =>
    record === missing
      ? "<missing>"
      : [
          record?.status ?? "",
          checkpointSignatureTime(record),
          record?.updated_at ?? "",
          record?.updated_at_iso ?? "",
          record?.has_clear ?? "",
        ].join("|");
  const baseSignature = signature(base);
  const localSignature = signature(local);
  const remoteSignature = signature(remote);

  if (localSignature === remoteSignature) {
    return cloneJson(local);
  }
  if (baseSignature === localSignature) {
    return cloneJson(remote);
  }
  if (baseSignature === remoteSignature) {
    return cloneJson(local);
  }
  const localStatus = statusScore(local?.status);
  const remoteStatus = statusScore(remote?.status);
  if (localStatus !== remoteStatus) {
    return cloneJson(remoteStatus > localStatus ? remote : local);
  }
  return cloneJson(recordTime(remote) >= recordTime(local) ? remote : local);
}

function mergeAppendOnlyMap(base, local, remote, pathParts, issues, valueMerger = chooseStatusRecord) {
  // state.checked_reports、state.processed_reports 與 ranking reports 都是 append-only map。
  // 合併時只新增或選擇較新的狀態，不會因某一邊缺少鍵值就刪除另一邊已有的歷史資料。
  const output = {};
  const baseMap = asObject(base);
  const localMap = asObject(local);
  const remoteMap = asObject(remote);

  for (const key of orderedUnion(Object.keys(baseMap), Object.keys(localMap), Object.keys(remoteMap))) {
    const baseValue = key in baseMap ? baseMap[key] : missing;
    const localValue = key in localMap ? localMap[key] : missing;
    const remoteValue = key in remoteMap ? remoteMap[key] : missing;

    if (localValue === missing && remoteValue === missing) {
      // append-only map 的共同基準可能被兩個分支各自的舊版裁切邏輯移除。預檢仍會
      // 回報 REMOVAL 並要求人工稽核，但實際合併結果永遠保留基準值，避免使用者
      // 接受已稽核的移除數量後反而真的刪掉歷史 checkpoint 或 report。
      if (baseValue !== missing) {
        output[key] = cloneJson(baseValue);
      }
      continue;
    }
    if (localValue === missing) {
      output[key] = cloneJson(remoteValue);
      continue;
    }
    if (remoteValue === missing) {
      output[key] = cloneJson(localValue);
      continue;
    }
    output[key] = valueMerger(baseValue, localValue, remoteValue, [...pathParts, key], issues);
  }

  return output;
}

function mergeReportRecord(base, local, remote, pathParts, issues) {
  const normalizedLocal = cloneJson(local);
  const normalizedRemote = cloneJson(remote);
  if (isPlainObject(normalizedLocal) && isPlainObject(normalizedRemote)) {
    // FFLogs report 可在上傳後繼續增加 segment；revision、report_end_time 與
    // segment 數只會單調增加。本機歷史回補與 workflow 若在不同時點
    // 重抓同一 report，應保留較完整的後續版本，不能把這些視為
    // 任意數值衝突。fight 與 player 內容仍由下方的結構化聯集合併。
    for (const key of ["revision", "report_end_time", "segments", "exported_segments"]) {
      if (typeof normalizedLocal[key] === "number" && typeof normalizedRemote[key] === "number") {
        const latestValue = Math.max(normalizedLocal[key], normalizedRemote[key]);
        normalizedLocal[key] = latestValue;
        normalizedRemote[key] = latestValue;
      }
    }

    const localFetchedAt =
      (toNumber(normalizedLocal.fetched_at) ?? Date.parse(normalizedLocal.fetched_at_iso || 0)) || 0;
    const remoteFetchedAt =
      (toNumber(normalizedRemote.fetched_at) ?? Date.parse(normalizedRemote.fetched_at_iso || 0)) || 0;
    if (
      normalizedLocal.visibility !== normalizedRemote.visibility &&
      normalizedLocal.visibility != null &&
      normalizedRemote.visibility != null &&
      localFetchedAt !== remoteFetchedAt
    ) {
      // visibility 可由 public 改為 unlisted，不能以字串優先序猜測。
      // 只採實際重抓 report 時間較新的快照；同時間仍保留為衝突。
      const visibility = remoteFetchedAt > localFetchedAt ? normalizedRemote.visibility : normalizedLocal.visibility;
      normalizedLocal.visibility = visibility;
      normalizedRemote.visibility = visibility;
    }

    const localHiddenAt =
      (toNumber(normalizedLocal.hidden_detected_at) ??
        Date.parse(normalizedLocal.hidden_detected_at_iso || 0)) ||
      0;
    const remoteHiddenAt =
      (toNumber(normalizedRemote.hidden_detected_at) ??
        Date.parse(normalizedRemote.hidden_detected_at_iso || 0)) ||
      0;
    if (
      normalizedLocal.hidden_source !== normalizedRemote.hidden_source &&
      normalizedLocal.hidden_source != null &&
      normalizedRemote.hidden_source != null &&
      localHiddenAt !== remoteHiddenAt
    ) {
      // hidden_source 是偵測來源的診斷欄位；與較新 hidden_detected_at 同步，
      // 避免合併出來源與偵測時間互相矛盾的虛構記錄。
      const hiddenSource = remoteHiddenAt > localHiddenAt ? normalizedRemote.hidden_source : normalizedLocal.hidden_source;
      normalizedLocal.hidden_source = hiddenSource;
      normalizedRemote.hidden_source = hiddenSource;
    }
  }
  return mergeRecordObject(base, normalizedLocal, normalizedRemote, pathParts, issues, {
    fights: mergeFightRecord,
  });
}

function mergeFightRecord(base, local, remote, pathParts, issues) {
  return mergeRecordObject(base, local, remote, pathParts, issues, {
    players: mergePlayerRecord,
  });
}

function mergePlayerRecord(base, local, remote, pathParts, issues) {
  return mergeRecordObject(base, local, remote, pathParts, issues);
}

function mergeRecordObject(base, local, remote, pathParts, issues, identifiedArrayMergers = {}) {
  if (!isPlainObject(local) || !isPlainObject(remote)) {
    return mergeJsonValue(base, local, remote, pathParts, issues);
  }
  const baseObject = asObject(base);
  const output = {};
  for (const key of orderedUnion(Object.keys(baseObject), Object.keys(local), Object.keys(remote))) {
    const baseValue = key in baseObject ? baseObject[key] : missing;
    const localValue = key in local ? local[key] : missing;
    const remoteValue = key in remote ? remote[key] : missing;
    let merged;
    if (key in identifiedArrayMergers) {
      merged = mergeIdentifiedArray(
        Array.isArray(baseValue) ? baseValue : [],
        Array.isArray(localValue) ? localValue : [],
        Array.isArray(remoteValue) ? remoteValue : [],
        [...pathParts, key],
        issues,
        identifiedArrayMergers[key],
      );
    } else {
      merged = mergeJsonValue(baseValue, localValue, remoteValue, [...pathParts, key], issues);
    }
    if (merged !== missing) {
      output[key] = merged;
    }
  }
  return output;
}

function mergeStateEncounter(base, local, remote, pathParts, issues) {
  const output = {};
  const baseObject = asObject(base);
  const localObject = asObject(local);
  const remoteObject = asObject(remote);
  const keys = orderedUnion(Object.keys(baseObject), Object.keys(localObject), Object.keys(remoteObject));

  for (const key of keys) {
    const baseValue = key in baseObject ? baseObject[key] : missing;
    const localValue = key in localObject ? localObject[key] : missing;
    const remoteValue = key in remoteObject ? remoteObject[key] : missing;
    if (key === "checked_reports" || key === "processed_reports") {
      output[key] = mergeAppendOnlyMap(baseValue, localValue, remoteValue, [...pathParts, key], issues);
      continue;
    }
    const merged = mergeJsonValue(baseValue, localValue, remoteValue, [...pathParts, key], issues);
    if (merged !== missing) {
      output[key] = merged;
    }
  }

  return output;
}

function mergeStateFile(base, local, remote, pathParts, issues) {
  const output = {};
  const baseObject = asObject(base);
  const localObject = asObject(local);
  const remoteObject = asObject(remote);
  const keys = orderedUnion(Object.keys(baseObject), Object.keys(localObject), Object.keys(remoteObject));

  for (const key of keys) {
    const baseValue = key in baseObject ? baseObject[key] : missing;
    const localValue = key in localObject ? localObject[key] : missing;
    const remoteValue = key in remoteObject ? remoteObject[key] : missing;
    if (key === "encounters") {
      output.encounters = mergeAppendOnlyMap(
        baseValue,
        localValue,
        remoteValue,
        [...pathParts, key],
        issues,
        mergeStateEncounter,
      );
      continue;
    }
    if (key === "last_run_stats") {
      // last_run_stats 是單次 workflow 的診斷快照，不是可逐欄累加的 checkpoint。
      // 混合兩輪摘要會產生不存在的執行狀態，因此整份採 scan_end_at 較新的版本。
      output[key] = chooseSnapshotByTime(baseValue, localValue, remoteValue, (value) =>
        (toNumber(value?.scan_end_at) ?? Date.parse(value?.scan_end_at_iso || 0)) || 0,
      );
      continue;
    }
    if (key === "support_metrics_report_backfill") {
      // 坦補 workflow 由新往舊移動 cursor；同一版本中較小的 cursor_sort_time 代表
      // 已掃得更早。completed 優先，其次才比較 cursor，避免較晚提交的舊進度倒退游標。
      output[key] = chooseSupportBackfillSnapshot(baseValue, localValue, remoteValue);
      continue;
    }
    const merged = mergeJsonValue(baseValue, localValue, remoteValue, [...pathParts, key], issues);
    if (merged !== missing) {
      output[key] = merged;
    }
  }

  return output;
}

function mergeRankingFile(base, local, remote, pathParts, issues) {
  const output = {};
  const baseObject = asObject(base);
  const localObject = asObject(local);
  const remoteObject = asObject(remote);
  const keys = orderedUnion(Object.keys(baseObject), Object.keys(localObject), Object.keys(remoteObject));

  for (const key of keys) {
    const baseValue = key in baseObject ? baseObject[key] : missing;
    const localValue = key in localObject ? localObject[key] : missing;
    const remoteValue = key in remoteObject ? remoteObject[key] : missing;
    if (key === "reports") {
      output.reports = mergeAppendOnlyMap(baseValue, localValue, remoteValue, [...pathParts, key], issues, mergeReportRecord);
      continue;
    }
    if (key === "ranking_entries") {
      output.ranking_entries = mergeRankingEntries(
        Array.isArray(baseValue) ? baseValue : [],
        Array.isArray(localValue) ? localValue : [],
        Array.isArray(remoteValue) ? remoteValue : [],
        [...pathParts, key],
        issues,
      );
      continue;
    }
    const merged = mergeJsonValue(baseValue, localValue, remoteValue, [...pathParts, key], issues);
    if (merged !== missing) {
      output[key] = merged;
    }
  }

  return output;
}

function mergeIdentifiedArray(base, local, remote, pathParts, issues, valueMerger = mergeJsonValue) {
  const keyFor = (item) => itemKeyForArray(pathParts, item);
  const baseMap = new Map((Array.isArray(base) ? base : []).map((item) => [keyFor(item), item]).filter(([key]) => key));
  const localMap = new Map((Array.isArray(local) ? local : []).map((item) => [keyFor(item), item]).filter(([key]) => key));
  const remoteMap = new Map((Array.isArray(remote) ? remote : []).map((item) => [keyFor(item), item]).filter(([key]) => key));
  const output = [];

  for (const key of orderedUnion([...baseMap.keys()], [...localMap.keys()], [...remoteMap.keys()])) {
    const baseItem = baseMap.get(key) ?? missing;
    const localItem = localMap.get(key) ?? missing;
    const remoteItem = remoteMap.get(key) ?? missing;
    if (
      (pathParts.at(-1) === "fights" || pathParts.at(-1) === "players") &&
      baseItem !== missing &&
      localItem === missing &&
      remoteItem === missing
    ) {
      // FFLogs report 持續上傳後可能在新 revision 不再回傳舊 fight；站內已收錄
      // fight 仍是 append-only 追溯資產。即使兩個分支都漏掉它，也要從
      // 共同基準復原，不可因 report revision 刷新而刪除。
      output.push(cloneJson(baseItem));
      continue;
    }
    const merged = valueMerger(
      baseItem,
      localItem,
      remoteItem,
      [...pathParts, String(key)],
      issues,
    );
    if (merged !== missing) {
      output.push(merged);
    }
  }

  return output;
}

function mergeArray(base, local, remote, pathParts, issues) {
  if (pathParts.at(-1) === "ranking_entries") {
    return mergeRankingEntries(base, local, remote, pathParts, issues);
  }

  const allItems = [...(Array.isArray(base) ? base : []), ...(Array.isArray(local) ? local : []), ...(Array.isArray(remote) ? remote : [])];
  const hasObject = allItems.some((item) => item && typeof item === "object");
  if (!hasObject) {
    return mergePrimitiveArray(base, local, remote);
  }

  const identifiable = allItems.every((item) => !item || typeof item !== "object" || itemKeyForArray(pathParts, item));
  if (identifiable) {
    return mergeIdentifiedArray(base, local, remote, pathParts, issues);
  }

  return mergePrimitiveArray(base, local, remote);
}

function mergeObject(base, local, remote, pathParts, issues) {
  const output = {};
  const keys = orderedUnion(
    Object.keys(isPlainObject(base) ? base : {}),
    Object.keys(isPlainObject(local) ? local : {}),
    Object.keys(isPlainObject(remote) ? remote : {}),
  );

  for (const key of keys) {
    const merged = mergeJsonValue(
      isPlainObject(base) && key in base ? base[key] : missing,
      isPlainObject(local) && key in local ? local[key] : missing,
      isPlainObject(remote) && key in remote ? remote[key] : missing,
      [...pathParts, key],
      issues,
    );
    if (merged !== missing) {
      output[key] = merged;
    }
  }

  return output;
}

function mergeJsonValue(base, local, remote, pathParts, issues) {
  if (local === missing && remote === missing) {
    return missing;
  }
  if (local === missing) {
    return cloneJson(remote);
  }
  if (remote === missing) {
    return cloneJson(local);
  }
  if (sameJson(local, remote)) {
    return cloneJson(local);
  }
  if (sameJson(base, local)) {
    return cloneJson(remote);
  }
  if (sameJson(base, remote)) {
    return cloneJson(local);
  }
  if (isScalar(base) && isScalar(local) && isScalar(remote)) {
    if (sameJson(local, remote)) {
      return cloneJson(local);
    }
    if (sameJson(base, local)) {
      return cloneJson(remote);
    }
    if (sameJson(base, remote)) {
      return cloneJson(local);
    }
    return resolveScalar(base, local, remote, pathParts, issues);
  }
  if (Array.isArray(local) && Array.isArray(remote)) {
    return mergeArray(Array.isArray(base) ? base : [], local, remote, pathParts, issues);
  }
  if (isPlainObject(local) && isPlainObject(remote)) {
    return mergeObject(isPlainObject(base) ? base : {}, local, remote, pathParts, issues);
  }
  return resolveScalar(base, local, remote, pathParts, issues);
}

function createIssues() {
  return {
    removals: [],
    conflicts: [],
    additions: 0,
  };
}

function mergeDataPath(relPath, base, local, remote, issues) {
  checkProtectedRemovals(relPath, base, local, "local", issues);
  checkProtectedRemovals(relPath, base, remote, "upstream", issues);
  issues.additions += countProtectedAdditions(relPath, base, local);
  issues.additions += countProtectedAdditions(relPath, base, remote);
  if (relPath === "data/state.json") {
    return mergeStateFile(base, local, remote, [relPath], issues);
  }
  if (isCheckedReportsShardPath(relPath)) {
    return mergeAppendOnlyMap(base, local, remote, [relPath], issues);
  }
  if (isRankingReportShardPath(relPath)) {
    // report 分片的根層本身就是 report_code -> report 的 append-only map，
    // 不是含 reports 欄位的排行榜主檔。分開辨識才能同時保護
    // report code，並讓同一 report 的 fight/player 結構化合併規則生效。
    return mergeAppendOnlyMap(base, local, remote, [relPath], issues, mergeReportRecord);
  }
  if (relPath.startsWith("data/rankings/")) {
    return mergeRankingFile(base, local, remote, [relPath], issues);
  }
  return mergeJsonValue(base, local, remote, [relPath], issues);
}

function sortKeysDeep(value) {
  if (Array.isArray(value)) {
    return value.map(sortKeysDeep);
  }
  if (!isPlainObject(value)) {
    return value;
  }
  const output = {};
  for (const key of Object.keys(value).sort()) {
    output[key] = sortKeysDeep(value[key]);
  }
  return output;
}

function formatJson(relPath, value) {
  if (relPath === "data/state.json") {
    return `${JSON.stringify(sortKeysDeep(value), null, 2)}\n`;
  }
  if (relPath === "config/encounters.json") {
    return `${JSON.stringify(value, null, 2)}\n`;
  }
  return `${JSON.stringify(value)}\n`;
}

async function writeJsonFile(relPath, value) {
  const fullPath = path.join(rootDir, relPath);
  await mkdir(path.dirname(fullPath), { recursive: true });
  const content = formatJson(relPath, value);
  const transientWindowsErrorCodes = new Set(["UNKNOWN", "EBUSY", "EPERM", "EACCES"]);
  const maxAttempts = process.platform === "win32" ? 5 : 1;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    try {
      await writeFile(fullPath, content, "utf8");
      return;
    } catch (error) {
      const canRetry = transientWindowsErrorCodes.has(error?.code) && attempt < maxAttempts;
      if (!canRetry) {
        throw error;
      }
      // Windows Defender、搜尋索引或 Git 可能在大型 JSON 切換版本時短暫持有檔案；
      // 有上限的遞增等待可處理瞬間鎖定，同時避免真正的權限問題被無限隱藏。
      const delayMs = attempt * 250;
      console.warn(`寫入 ${relPath} 時發生 ${error.code}；${delayMs} 毫秒後重試（${attempt}/${maxAttempts}）。`);
      await new Promise((resolve) => setTimeout(resolve, delayMs));
    }
  }
}

function chooseSnapshotByTime(base, local, remote, timeGetter) {
  if (local === missing) {
    return cloneJson(remote);
  }
  if (remote === missing) {
    return cloneJson(local);
  }
  if (sameJson(local, remote)) {
    return cloneJson(local);
  }
  if (sameJson(base, local)) {
    return cloneJson(remote);
  }
  if (sameJson(base, remote)) {
    return cloneJson(local);
  }
  return cloneJson(timeGetter(remote) >= timeGetter(local) ? remote : local);
}

function chooseSupportBackfillSnapshot(base, local, remote) {
  if (local === missing || remote === missing || sameJson(local, remote) || sameJson(base, local) || sameJson(base, remote)) {
    return chooseSnapshotByTime(base, local, remote, (value) => Date.parse(value?.last_run_at_iso || 0) || 0);
  }

  const versionKey = (value) => `${value?.calculation_version ?? ""}|${value?.mitigation_rules_version ?? ""}`;
  if (versionKey(local) !== versionKey(remote)) {
    return chooseSnapshotByTime(base, local, remote, (value) => Date.parse(value?.initialized_at_iso || value?.last_run_at_iso || 0) || 0);
  }
  if (Boolean(local?.completed) !== Boolean(remote?.completed)) {
    return cloneJson(remote?.completed ? remote : local);
  }
  if (local?.mode === "new_to_old_report_backfill" && remote?.mode === "new_to_old_report_backfill") {
    const localCursor = toNumber(local?.cursor_sort_time);
    const remoteCursor = toNumber(remote?.cursor_sort_time);
    if (localCursor !== null && remoteCursor !== null && localCursor !== remoteCursor) {
      return cloneJson(remoteCursor < localCursor ? remote : local);
    }
  }
  return chooseSnapshotByTime(base, local, remote, (value) => Date.parse(value?.last_run_at_iso || 0) || 0);
}

function assertNoIssues(issues, acceptedProtectedRemovals = null) {
  const removalsAccepted =
    acceptedProtectedRemovals !== null && issues.removals.length === acceptedProtectedRemovals;
  if ((!removalsAccepted && issues.removals.length) || issues.conflicts.length) {
    const details = [
      ...issues.removals.map((issue) => `REMOVAL ${issue.path}: ${issue.message}`),
      ...issues.conflicts.map((issue) => `CONFLICT ${issue.path}: ${issue.message}`),
    ];
    if (acceptedProtectedRemovals !== null && issues.removals.length !== acceptedProtectedRemovals) {
      details.unshift(
        `Audited removal count mismatch: expected ${acceptedProtectedRemovals}, found ${issues.removals.length}.`,
      );
    }
    throw new ToolError("Automatic data merge stopped because protected data was removed or a real conflict was found.", details);
  }
  if (removalsAccepted) {
    console.warn(
      `Continuing after manual audit accepted exactly ${acceptedProtectedRemovals} protected removals; append-only maps will restore their union.`,
    );
  }
}

function summarizeIssues(label, issues) {
  console.log(`${label}: ${issues.additions} protected additions, ${issues.removals.length} removals, ${issues.conflicts.length} conflicts.`);
}

async function buildCommittedMergePlan(mergeBase, localHead, upstreamRef, upstreamHead) {
  const changedSourcePaths = orderedUnion(
    getChangedFiles(mergeBase, localHead).filter(isSourceDataPath),
    getChangedFiles(mergeBase, upstreamRef).filter(isSourceDataPath),
  );
  console.log(`Preflighting committed source files (${changedSourcePaths.length})...`);
  const mergedByPath = new Map();
  const removedPaths = new Set();
  const issues = createIssues();
  const rankingKeys = new Set(changedSourcePaths.map(rankingKeyFromPath).filter(Boolean));

  for (const relPath of changedSourcePaths.filter((candidate) => !rankingKeyFromPath(candidate))) {
    console.log(`  committed: ${relPath}`);
    const base = readGitJson(mergeBase, relPath);
    let merged;
    if (localHead === mergeBase) {
      const remote = readGitJson(upstreamRef, relPath);
      checkProtectedRemovals(relPath, base, remote, "upstream", issues);
      issues.additions += countProtectedAdditions(relPath, base, remote);
      merged = remote;
    } else if (upstreamHead === mergeBase) {
      const local = readGitJson(localHead, relPath);
      checkProtectedRemovals(relPath, base, local, "local", issues);
      issues.additions += countProtectedAdditions(relPath, base, local);
      merged = local;
    } else {
      merged = mergeDataPath(relPath, base, readGitJson(localHead, relPath), readGitJson(upstreamRef, relPath), issues);
    }
    if (merged !== missing) {
      mergedByPath.set(relPath, merged);
    }
  }

  for (const rankingKey of [...rankingKeys].sort()) {
    console.log(`  committed ranking group: ${rankingKey}`);
    const baseGroup = readGitRankingGroup(mergeBase, rankingKey);
    const localGroup = readGitRankingGroup(localHead, rankingKey);
    const remoteGroup = readGitRankingGroup(upstreamRef, rankingKey);
    const mainPath = `data/rankings/${rankingKey}.json`;
    const merged = mergeDataPath(mainPath, baseGroup.value, localGroup.value, remoteGroup.value, issues);
    if (merged === missing) {
      continue;
    }

    const groupFiles = buildRankingGroupFiles(rankingKey, merged);
    for (const [relPath, value] of groupFiles) {
      mergedByPath.set(relPath, value);
    }
    const existingPaths = new Set([...baseGroup.paths, ...localGroup.paths, ...remoteGroup.paths]);
    for (const relPath of existingPaths) {
      if (!groupFiles.has(relPath)) {
        removedPaths.add(relPath);
      }
    }
  }

  const sourcePaths = orderedUnion(changedSourcePaths, [...mergedByPath.keys()], [...removedPaths]);
  return { sourcePaths, mergedByPath, removedPaths, issues };
}

async function buildDirtyReapplyPlan(dirtySourcePaths, localHead, committedMergedByPath) {
  console.log(`Preflighting dirty source files (${dirtySourcePaths.length})...`);
  const mergedByPath = new Map();
  const removedPaths = new Set();
  const issues = createIssues();
  const rankingKeys = new Set(dirtySourcePaths.map(rankingKeyFromPath).filter(Boolean));

  for (const relPath of dirtySourcePaths.filter((candidate) => !rankingKeyFromPath(candidate))) {
    console.log(`  dirty: ${relPath}`);
    const local = await readWorkingJson(relPath);
    const base = readGitJson(localHead, relPath);
    let merged;
    if (committedMergedByPath.has(relPath)) {
      const postMerge = committedMergedByPath.get(relPath);
      merged = mergeDataPath(relPath, base, local, postMerge, issues);
    } else {
      checkProtectedRemovals(relPath, base, local, "local", issues);
      issues.additions += countProtectedAdditions(relPath, base, local);
      merged = local;
    }
    if (merged !== missing) {
      mergedByPath.set(relPath, merged);
    }
  }

  for (const rankingKey of [...rankingKeys].sort()) {
    console.log(`  dirty ranking group: ${rankingKey}`);
    const baseGroup = readGitRankingGroup(localHead, rankingKey);
    const localGroup = await readWorkingRankingGroup(rankingKey);
    const plannedGroup = readPlannedRankingGroup(committedMergedByPath, rankingKey) || baseGroup;
    const mainPath = `data/rankings/${rankingKey}.json`;
    const merged = mergeDataPath(mainPath, baseGroup.value, localGroup.value, plannedGroup.value, issues);
    if (merged === missing) {
      continue;
    }
    const groupFiles = buildRankingGroupFiles(rankingKey, merged);
    for (const [relPath, value] of groupFiles) {
      mergedByPath.set(relPath, value);
    }
    for (const relPath of new Set([...localGroup.paths, ...plannedGroup.paths])) {
      if (!groupFiles.has(relPath)) {
        removedPaths.add(relPath);
      }
    }
  }

  return { mergedByPath, removedPaths, issues };
}

function writePathspecFile(paths) {
  const tempDir = mkdtempSync(path.join(os.tmpdir(), "ffxiv-sync-data-"));
  const filePath = path.join(tempDir, "pathspecs");
  writeFileSync(filePath, `${paths.join("\0")}\0`, "utf8");
  return { tempDir, filePath };
}

function stashDirtyPaths(paths) {
  if (!paths.length) {
    return null;
  }

  const { tempDir, filePath } = writePathspecFile(paths);
  try {
    const message = `sync-upstream-data ${new Date().toISOString()}`;
    const result = git([
      "stash",
      "push",
      "--include-untracked",
      "--message",
      message,
      "--pathspec-from-file",
      filePath,
      "--pathspec-file-nul",
    ]);
    if (/No local changes/i.test(result.stdout)) {
      return null;
    }
    const ref = "stash@{0}";
    const top = gitText(["stash", "list", "-1"]);
    if (!top.includes(message)) {
      throw new ToolError("Created a stash, but could not verify it is on top of the stash stack.");
    }
    console.log(`Saved local managed changes in ${ref}.`);
    return ref;
  } finally {
    rmSync(tempDir, { recursive: true, force: true });
  }
}

function dropStash(stashRef) {
  if (!stashRef) {
    return;
  }
  git(["stash", "drop", stashRef]);
  console.log(`Dropped temporary ${stashRef}.`);
}

async function applyCommittedSourcePlan(committedPlan) {
  for (const relPath of committedPlan.removedPaths) {
    git(["rm", "--ignore-unmatch", "--", relPath], { allowFailure: true });
  }
  for (const [relPath, merged] of committedPlan.mergedByPath) {
    await writeJsonFile(relPath, merged);
    git(["add", "--", relPath]);
  }
}

async function resolveLatestSnapshotConflict(relPath) {
  if (relPath === "data/pages_payload_history.jsonl") {
    const local = readIndexText(2, relPath);
    const remote = readIndexText(3, relPath);
    if (local === missing || remote === missing) {
      throw new ToolError("Payload history snapshot is missing from one side of the merge.", [relPath]);
    }
    const latestTime = (textValue) => {
      const lines = textValue.split(/\r?\n/).filter(Boolean);
      if (!lines.length) {
        return 0;
      }
      try {
        return Date.parse(JSON.parse(lines.at(-1)).recorded_at_iso || 0) || 0;
      } catch {
        throw new ToolError("Payload history contains an invalid JSONL record.", [relPath]);
      }
    };
    const chosen = latestTime(remote) >= latestTime(local) ? remote : local;
    await writeFile(path.join(rootDir, relPath), chosen.endsWith("\n") ? chosen : `${chosen}\n`, "utf8");
    git(["add", "--", relPath]);
    return;
  }

  const local = readIndexJson(2, relPath);
  const remote = readIndexJson(3, relPath);
  if (local === missing || remote === missing) {
    throw new ToolError("Latest snapshot data is missing from one side of the merge.", [relPath]);
  }

  if (relPath === "data/fun/honey_b_fans.json") {
    const immutablePayload = (value) => {
      const copy = cloneJson(value);
      delete copy.state;
      delete copy.updated_at_iso;
      return copy;
    };
    if (!sameJson(immutablePayload(local), immutablePayload(remote))) {
      throw new ToolError("Honey B. source records differ between branches; refusing to choose a snapshot.", [relPath]);
    }
  }

  const localTime = Date.parse(local?.updated_at_iso || 0) || 0;
  const remoteTime = Date.parse(remote?.updated_at_iso || 0) || 0;
  await writeJsonFile(relPath, remoteTime >= localTime ? remote : local);
  git(["add", "--", relPath]);
}

async function resolveMergeConflicts(committedPlan) {
  const unmerged = getDirtyEntries().filter((entry) => hasUnmergedStatus(entry.xy));
  const unmanaged = unmerged.filter((entry) => !isManagedPath(entry.path));
  if (unmanaged.length) {
    throw new ToolError("Git merge produced conflicts outside managed data files.", unmanaged.map((entry) => `${entry.xy} ${entry.path}`));
  }

  for (const entry of unmerged) {
    const relPath = entry.path;
    if (isLatestSnapshotDataPath(relPath)) {
      await resolveLatestSnapshotConflict(relPath);
    } else if (isGeneratedDataPath(relPath)) {
      const upstream = readIndexJson(3, relPath);
      if (upstream !== missing) {
        await writeJsonFile(relPath, upstream);
        git(["add", "--", relPath]);
      } else {
        git(["rm", "--", relPath], { allowFailure: true });
      }
    }
  }
  // 不以 Git 的單檔衝突片段合併 ranking report 分片。預檢已經以
  // 副本為單位載入全部分片並驗證三方聯集；這裡直接套用同一份
  // plan，確保預覽與實際寫入完全一致，也不會把跨分片搬移當成刪除。
  await applyCommittedSourcePlan(committedPlan);

  const remaining = getDirtyEntries().filter((entry) => hasUnmergedStatus(entry.xy));
  if (remaining.length) {
    throw new ToolError("Structured data plan did not resolve every Git conflict.", remaining.map((entry) => `${entry.xy} ${entry.path}`));
  }
}

async function reapplyDirtySourceChanges(dirtyPlan) {
  for (const relPath of dirtyPlan.removedPaths) {
    rmSync(path.join(rootDir, relPath), { force: true });
  }
  for (const [relPath, merged] of dirtyPlan.mergedByPath.entries()) {
    await writeJsonFile(relPath, merged);
  }
}

async function repairExistingMerge(options) {
  const mergeRef = options.repairMergeRef;
  const parents = gitText(["rev-list", "--parents", "-n", "1", mergeRef]).trim().split(/\s+/).slice(1);
  if (parents.length !== 2) {
    throw new ToolError("--repair-merge-ref must reference a two-parent merge commit.", [mergeRef]);
  }
  const [localParent, remoteParent] = parents;
  const mergeBase = gitText(["merge-base", localParent, remoteParent]).trim();
  console.log(`Repair merge: ${mergeRef}`);
  console.log(`Local parent: ${localParent.slice(0, 12)}`);
  console.log(`Remote parent: ${remoteParent.slice(0, 12)}`);
  console.log(`Merge base: ${mergeBase.slice(0, 12)}`);

  const plan = await buildCommittedMergePlan(mergeBase, localParent, remoteParent, remoteParent);
  summarizeIssues("Existing merge repair preflight", plan.issues);
  assertNoIssues(plan.issues, options.acceptedProtectedRemovals);
  if (options.dryRun) {
    console.log("Repair dry run complete. No files were changed.");
    return;
  }

  await applyCommittedSourcePlan(plan);
  if (options.rebuild) {
    runNpmScript("build:public-rankings");
    runNpmScript("build:user-data");
  }
  printStatusSummary();
}

function runNpmScript(scriptName) {
  console.log(`Running npm run ${scriptName}...`);
  if (process.platform === "win32") {
    run("cmd.exe", ["/d", "/s", "/c", "npm", "run", scriptName]);
    return;
  }
  run("npm", ["run", scriptName]);
}

function printStatusSummary() {
  const status = gitText(["status", "--short", "--branch"]);
  console.log(status.trimEnd());
}

async function main() {
  const options = parseArgs(process.argv.slice(2));
  ensureGitReady();

  const dirtyEntries = getDirtyEntries();
  const unmergedEntries = dirtyEntries.filter((entry) => hasUnmergedStatus(entry.xy));
  if (unmergedEntries.length) {
    throw new ToolError("The working tree already has unmerged files.", unmergedEntries.map((entry) => `${entry.xy} ${entry.path}`));
  }

  if (options.repairMergeRef) {
    await repairExistingMerge(options);
    return;
  }

  const upstreamRef = resolveUpstreamRef(options.remoteRef);
  if (options.fetch) {
    fetchUpstream(upstreamRef);
  }

  git(["rev-parse", "--verify", upstreamRef]);
  const localHead = gitText(["rev-parse", "HEAD"]).trim();
  const upstreamHead = gitText(["rev-parse", upstreamRef]).trim();
  const mergeBase = gitText(["merge-base", localHead, upstreamHead]).trim();
  const dirtyOutsideManaged = dirtyEntries.filter((entry) => !isManagedPath(entry.path));
  if (dirtyOutsideManaged.length && !options.allowDirtyOther) {
    throw new ToolError(
      "Refusing to sync while non-data files have local changes.",
      dirtyOutsideManaged.map((entry) => `${entry.xy} ${entry.path}`),
    );
  }
  if (dirtyOutsideManaged.length) {
    const dirtyOutsidePaths = new Set(dirtyOutsideManaged.map((entry) => entry.path));
    const upstreamDirtyOverlap = getChangedFiles(mergeBase, upstreamRef).filter((filePath) => dirtyOutsidePaths.has(filePath));
    if (upstreamDirtyOverlap.length) {
      throw new ToolError(
        "Dirty non-data files overlap with upstream changes.",
        upstreamDirtyOverlap.map((filePath) => `${filePath} is dirty locally and changed in ${upstreamRef}`),
      );
    }
    console.log(`Ignoring ${dirtyOutsideManaged.length} dirty non-data file(s) because --allow-dirty-other was passed.`);
  }
  const dirtySourcePaths = dirtyEntries.map((entry) => entry.path).filter(isSourceDataPath);
  const dirtyGeneratedPaths = dirtyEntries.map((entry) => entry.path).filter(isGeneratedDataPath);

  console.log(`Local HEAD: ${localHead.slice(0, 12)}`);
  console.log(`Upstream ${upstreamRef}: ${upstreamHead.slice(0, 12)}`);
  console.log(`Merge base: ${mergeBase.slice(0, 12)}`);

  const committedPlan = await buildCommittedMergePlan(mergeBase, localHead, upstreamRef, upstreamHead);
  const dirtyPlan = await buildDirtyReapplyPlan(dirtySourcePaths, localHead, committedPlan.mergedByPath);
  summarizeIssues("Committed upstream merge preflight", committedPlan.issues);
  summarizeIssues("Local dirty data preflight", dirtyPlan.issues);
  const combinedIssues = {
    additions: committedPlan.issues.additions + dirtyPlan.issues.additions,
    removals: [...committedPlan.issues.removals, ...dirtyPlan.issues.removals],
    conflicts: [...committedPlan.issues.conflicts, ...dirtyPlan.issues.conflicts],
  };
  assertNoIssues(combinedIssues, options.acceptedProtectedRemovals);

  console.log(`Source files touched by upstream/local commits: ${committedPlan.sourcePaths.length || 0}`);
  console.log(`Dirty source files to reapply: ${dirtySourcePaths.length || 0}`);
  console.log(`Dirty generated files to rebuild: ${dirtyGeneratedPaths.length || 0}`);

  if (options.dryRun) {
    console.log("Dry run complete. No files were changed.");
    return;
  }

  const dirtyManagedPaths = dirtyEntries.map((entry) => entry.path).filter(isManagedPath);
  const stashRef = stashDirtyPaths(dirtyManagedPaths);
  let completed = false;
  try {
    const mergeMessage = [
      "chore(data): 合併遠端自動化資料",
      "",
      "Why:",
      "- 本機 FFLogs 回補與 GitHub Actions 同時產生 append-only 資料，需要保留三方完整聯集。",
      "",
      "主要變更：",
      "- 以副本為單位合併排行榜 report 分片，保留 report、fight 與 player 追溯資料。",
      "- 合併本機歷史坦補支援統計與遠端最新掃描結果。",
      "",
      "測試與驗證：",
      `- npm run sync:data -- --dry-run（${combinedIssues.additions.toLocaleString("en-US")} 筆受保護新增、${options.acceptedProtectedRemovals ?? 0} 筆已稽核分支移除、0 衝突）`,
    ].join("\n");
    const merge = git(["merge", "--no-commit", "--no-ff", "-m", mergeMessage, upstreamRef], {
      allowFailure: true,
    });
    if (merge.status !== 0) {
      console.log("Git merge needs structured data conflict resolution.");
      await resolveMergeConflicts(committedPlan);
    } else {
      // 即使 Git 對某些單行 JSON 巧合自動合併，仍要套用已通過預檢的
      // 結構化 plan，避免預覽與實際結果因 Git 文字策略而分歧。
      await applyCommittedSourcePlan(committedPlan);
    }

    if (existsSync(path.join(rootDir, gitText(["rev-parse", "--git-dir"]).trim(), "MERGE_HEAD"))) {
      git(["commit", "--no-edit"]);
    }

    await reapplyDirtySourceChanges(dirtyPlan);

    if (options.rebuild) {
      runNpmScript("build:public-rankings");
      runNpmScript("build:user-data");
    } else {
      console.log("Skipped public/data rebuild because --no-rebuild was passed.");
    }

    completed = true;
  } finally {
    if (completed) {
      dropStash(stashRef);
    } else if (stashRef) {
      console.error(`Temporary local changes are still saved in ${stashRef}. Inspect with git stash show -p ${stashRef}.`);
    }
  }

  printStatusSummary();
}

main().catch((error) => {
  console.error(error.message);
  for (const detail of error.details || []) {
    console.error(`- ${detail}`);
  }
  process.exitCode = 1;
});
