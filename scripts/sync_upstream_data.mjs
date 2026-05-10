import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const maxBuffer = 1024 * 1024 * 512;
const missing = Symbol("missing");

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

function isSourceDataPath(filePath) {
  const normalized = normalizePath(filePath);
  return (
    normalized === "config/encounters.json" ||
    normalized === "data/state.json" ||
    (normalized.startsWith("data/rankings/") && normalized.endsWith(".json"))
  );
}

function isGeneratedDataPath(filePath) {
  const normalized = normalizePath(filePath);
  return (
    normalized === "public/data/encounters.json" ||
    normalized === "public/data/global_stats.json" ||
    (normalized.startsWith("public/data/rankings/") && normalized.endsWith(".json")) ||
    (normalized.startsWith("public/data/users/") && normalized.endsWith(".json"))
  );
}

function isManagedPath(filePath) {
  return isSourceDataPath(filePath) || isGeneratedDataPath(filePath);
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
  return parsePorcelainZ(gitText(["status", "--porcelain=v1", "-z"]));
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

  if (relPath === "data/state.json") {
    checkRemovedKeys(issues, `${relPath}:encounters`, base.encounters, side.encounters, sideName);
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
      checkRemovedKeys(
        issues,
        `${relPath}:encounters.${encounterKey}.processed_reports`,
        baseEncounter?.processed_reports,
        sideEncounter?.processed_reports,
        sideName,
      );
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

function resolveScalar(base, local, remote, pathParts, issues) {
  const key = pathParts.at(-1) || "";
  if (typeof local === "number" && typeof remote === "number") {
    if (isTimestampKey(pathParts) || key.endsWith("_count") || key === "duplicate_count" || key === "rank") {
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

function chooseStatusRecord(base, local, remote) {
  const signature = (record) =>
    record === missing
      ? "<missing>"
      : [
          record?.status ?? "",
          record?.processed_at ?? "",
          record?.processed_at_iso ?? "",
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
  const output = {};
  const baseMap = asObject(base);
  const localMap = asObject(local);
  const remoteMap = asObject(remote);

  for (const key of orderedUnion(Object.keys(baseMap), Object.keys(localMap), Object.keys(remoteMap))) {
    const baseValue = key in baseMap ? baseMap[key] : missing;
    const localValue = key in localMap ? localMap[key] : missing;
    const remoteValue = key in remoteMap ? remoteMap[key] : missing;

    if (localValue === missing && remoteValue === missing) {
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
  if (sameJson(local, remote)) {
    return cloneJson(local);
  }
  if (sameJson(base, local)) {
    return cloneJson(remote);
  }
  if (sameJson(base, remote)) {
    return cloneJson(local);
  }
  return mergeJsonValue(base, local, remote, pathParts, issues);
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

function mergeIdentifiedArray(base, local, remote, pathParts, issues) {
  const keyFor = (item) => itemKeyForArray(pathParts, item);
  const baseMap = new Map((Array.isArray(base) ? base : []).map((item) => [keyFor(item), item]).filter(([key]) => key));
  const localMap = new Map((Array.isArray(local) ? local : []).map((item) => [keyFor(item), item]).filter(([key]) => key));
  const remoteMap = new Map((Array.isArray(remote) ? remote : []).map((item) => [keyFor(item), item]).filter(([key]) => key));
  const output = [];

  for (const key of orderedUnion([...baseMap.keys()], [...localMap.keys()], [...remoteMap.keys()])) {
    const merged = mergeJsonValue(
      baseMap.get(key) ?? missing,
      localMap.get(key) ?? missing,
      remoteMap.get(key) ?? missing,
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
  await writeFile(fullPath, formatJson(relPath, value), "utf8");
}

function assertNoIssues(issues) {
  if (issues.removals.length || issues.conflicts.length) {
    const details = [
      ...issues.removals.map((issue) => `REMOVAL ${issue.path}: ${issue.message}`),
      ...issues.conflicts.map((issue) => `CONFLICT ${issue.path}: ${issue.message}`),
    ];
    throw new ToolError("Automatic data merge stopped because protected data was removed or a real conflict was found.", details);
  }
}

function summarizeIssues(label, issues) {
  console.log(`${label}: ${issues.additions} protected additions, ${issues.removals.length} removals, ${issues.conflicts.length} conflicts.`);
}

async function buildCommittedMergePlan(mergeBase, localHead, upstreamRef, upstreamHead) {
  const sourcePaths = orderedUnion(
    getChangedFiles(mergeBase, localHead).filter(isSourceDataPath),
    getChangedFiles(mergeBase, upstreamRef).filter(isSourceDataPath),
  );
  console.log(`Preflighting committed source files (${sourcePaths.length})...`);
  const mergedByPath = new Map();
  const issues = createIssues();

  for (const relPath of sourcePaths) {
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

  return { sourcePaths, mergedByPath, issues };
}

async function buildDirtyReapplyPlan(dirtySourcePaths, localHead, committedMergedByPath) {
  console.log(`Preflighting dirty source files (${dirtySourcePaths.length})...`);
  const mergedByPath = new Map();
  const issues = createIssues();

  for (const relPath of dirtySourcePaths) {
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

  return { mergedByPath, issues };
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

async function resolveMergeConflicts(options) {
  const unmerged = getDirtyEntries().filter((entry) => hasUnmergedStatus(entry.xy));
  const unmanaged = unmerged.filter((entry) => !isManagedPath(entry.path));
  if (unmanaged.length) {
    throw new ToolError("Git merge produced conflicts outside managed data files.", unmanaged.map((entry) => `${entry.xy} ${entry.path}`));
  }

  const issues = createIssues();
  for (const entry of unmerged) {
    const relPath = entry.path;
    if (isSourceDataPath(relPath)) {
      const merged = mergeDataPath(relPath, readIndexJson(1, relPath), readIndexJson(2, relPath), readIndexJson(3, relPath), issues);
      if (merged !== missing) {
        await writeJsonFile(relPath, merged);
        git(["add", "--", relPath]);
      }
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
  assertNoIssues(issues);
  summarizeIssues("Merge conflict resolution", issues);

  if (existsSync(path.join(rootDir, gitText(["rev-parse", "--git-dir"]).trim(), "MERGE_HEAD"))) {
    git(["commit", "--no-edit"]);
  }
}

async function reapplyDirtySourceChanges(dirtyPlan) {
  for (const [relPath, merged] of dirtyPlan.mergedByPath.entries()) {
    await writeJsonFile(relPath, merged);
  }
}

function runNpmScript(scriptName) {
  console.log(`Running npm run ${scriptName}...`);
  run(process.platform === "win32" ? "npm.cmd" : "npm", ["run", scriptName]);
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
    const upstreamDirtyOverlap = getChangedFiles(localHead, upstreamRef).filter((filePath) => dirtyOutsidePaths.has(filePath));
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
  assertNoIssues(committedPlan.issues);
  assertNoIssues(dirtyPlan.issues);

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
    const merge = git(["merge", "--no-edit", upstreamRef], { allowFailure: true });
    if (merge.status !== 0) {
      console.log("Git merge needs structured data conflict resolution.");
      await resolveMergeConflicts(options);
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
