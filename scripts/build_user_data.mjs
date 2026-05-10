import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, readFile, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const sourceRankingsDir = path.join(rootDir, "data", "rankings");
const publicRankingsDir = path.join(rootDir, "public", "data", "rankings");
const publicEncountersPath = path.join(rootDir, "public", "data", "encounters.json");
const configEncountersPath = path.join(rootDir, "config", "encounters.json");
const publicDataDir = path.join(rootDir, "public", "data");
const outputDir = path.join(rootDir, "public", "data", "users");
const globalStatsPath = path.join(publicDataDir, "global_stats.json");
const savageDamageComparisonEncounterKeys = ["savage_m1s", "savage_m2s", "savage_m3s", "savage_m4s"];
const savageDamageComparisonEncounterKeySet = new Set(savageDamageComparisonEncounterKeys);
const minimumDamageActivePercent = 50;

const jobRoleGroups = [
  {
    role: "role:tank",
    role_name: "防護職業",
    jobs: ["Paladin", "Warrior", "DarkKnight", "Gunbreaker"],
  },
  {
    role: "role:healer",
    role_name: "治療職業",
    jobs: ["WhiteMage", "Scholar", "Astrologian", "Sage"],
  },
  {
    role: "role:melee",
    role_name: "近戰職業",
    jobs: ["Monk", "Dragoon", "Ninja", "Samurai", "Reaper", "Viper"],
  },
  {
    role: "role:physical_ranged",
    role_name: "遠程物理職業",
    jobs: ["Bard", "Machinist", "Dancer"],
  },
  {
    role: "role:magical_ranged",
    role_name: "遠程魔法職業",
    jobs: ["BlackMage", "Summoner", "RedMage", "Pictomancer"],
  },
];

const jobRoleByJob = new Map(
  jobRoleGroups.flatMap((group) =>
    group.jobs.map((job) => [
      job,
      {
        role: group.role,
        role_name: group.role_name,
      },
    ]),
  ),
);

function assertInside(parent, target) {
  const relative = path.relative(parent, target);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error(`Refusing to write outside ${parent}: ${target}`);
  }
}

async function readJson(filePath, fallback = null) {
  try {
    return JSON.parse(await readFile(filePath, "utf8"));
  } catch (error) {
    if (error?.code === "ENOENT") {
      return fallback;
    }
    throw error;
  }
}

function writeJson(filePath, data) {
  return writeFile(filePath, `${JSON.stringify(data)}\n`, "utf8");
}

function toNumber(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function calculateActivePercent(activeTimeMs, clearTimeMs, clearTimeSeconds) {
  const activeTime = toNumber(activeTimeMs);
  const clearMs = toNumber(clearTimeMs) ?? (toNumber(clearTimeSeconds) ?? 0) * 1000;
  if (activeTime === null || clearMs <= 0) {
    return null;
  }
  return Number(((activeTime / clearMs) * 100).toFixed(2));
}

function stableJson(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableJson).join(",")}]`;
  }
  if (value && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${stableJson(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function createId(value) {
  return createHash("sha256").update(stableJson(value)).digest("hex");
}

function isBetterEntry(candidate, currentBest) {
  if (!currentBest) {
    return true;
  }

  const candidateRdps = candidate.rdps ?? candidate.dps ?? 0;
  const currentRdps = currentBest.rdps ?? currentBest.dps ?? 0;
  if (candidateRdps !== currentRdps) {
    return candidateRdps > currentRdps;
  }

  const candidateClearTime = candidate.clear_time_seconds ?? Infinity;
  const currentClearTime = currentBest.clear_time_seconds ?? Infinity;
  if (candidateClearTime !== currentClearTime) {
    return candidateClearTime < currentClearTime;
  }

  const candidateAdps = candidate.adps ?? candidate.dps ?? 0;
  const currentAdps = currentBest.adps ?? currentBest.dps ?? 0;
  if (candidateAdps !== currentAdps) {
    return candidateAdps > currentAdps;
  }

  const candidateTime = new Date(candidate.recorded_at_iso || 0).getTime();
  const currentTime = new Date(currentBest.recorded_at_iso || 0).getTime();
  return (Number.isNaN(candidateTime) ? 0 : candidateTime) > (Number.isNaN(currentTime) ? 0 : currentTime);
}

function compareEntriesByTimeThenScore(left, right) {
  const leftTime = new Date(left.recorded_at_iso || 0).getTime();
  const rightTime = new Date(right.recorded_at_iso || 0).getTime();
  const normalizedLeftTime = Number.isNaN(leftTime) ? 0 : leftTime;
  const normalizedRightTime = Number.isNaN(rightTime) ? 0 : rightTime;

  if (normalizedLeftTime !== normalizedRightTime) {
    return normalizedRightTime - normalizedLeftTime;
  }

  return (right.rdps ?? right.dps ?? 0) - (left.rdps ?? left.dps ?? 0);
}

function compareEntriesByBestScore(left, right) {
  if (isBetterEntry(left, right)) {
    return -1;
  }
  if (isBetterEntry(right, left)) {
    return 1;
  }

  const characterCompare = compareByLocale(left.character_name || "", right.character_name || "");
  if (characterCompare) {
    return characterCompare;
  }
  return compareByLocale(left.server || "", right.server || "");
}

function compareByLocale(left, right) {
  return String(left).localeCompare(String(right), "zh-Hant-TW");
}

function characterJobKey(entry) {
  return `${entry.character_name}@${entry.server}:${entry.job}`;
}

function characterServerKey(characterName, server) {
  return `${characterName}@${server}`;
}

function toPercent(count, total) {
  return total > 0 ? Number(((count / total) * 100).toFixed(2)) : 0;
}

function roundDamageStat(value) {
  return value === null ? null : Number(value.toFixed(2));
}

function percentile(sortedValues, percentileValue) {
  if (sortedValues.length === 0) {
    return null;
  }
  if (sortedValues.length === 1) {
    return sortedValues[0];
  }

  const index = (sortedValues.length - 1) * percentileValue;
  const lowerIndex = Math.floor(index);
  const upperIndex = Math.ceil(index);
  if (lowerIndex === upperIndex) {
    return sortedValues[lowerIndex];
  }

  const weight = index - lowerIndex;
  return sortedValues[lowerIndex] * (1 - weight) + sortedValues[upperIndex] * weight;
}

function buildDamageMetricStats(values) {
  const sortedValues = values
    .map(toNumber)
    .filter((value) => value !== null && value > 0)
    .sort((left, right) => left - right);

  if (sortedValues.length === 0) {
    return null;
  }

  const total = sortedValues.reduce((sum, value) => sum + value, 0);
  return {
    count: sortedValues.length,
    min: roundDamageStat(sortedValues[0]),
    q1: roundDamageStat(percentile(sortedValues, 0.25)),
    median: roundDamageStat(percentile(sortedValues, 0.5)),
    q3: roundDamageStat(percentile(sortedValues, 0.75)),
    max: roundDamageStat(sortedValues.at(-1)),
    average: roundDamageStat(total / sortedValues.length),
  };
}

function getDamageActivePercent(entry) {
  const activePercent = toNumber(entry?.active_percent);
  if (activePercent !== null) {
    return activePercent;
  }
  return calculateActivePercent(entry?.active_time_ms, entry?.clear_time_ms, entry?.clear_time_seconds);
}

function isDamageComparisonEntry(entry) {
  return getDamageActivePercent(entry) >= minimumDamageActivePercent;
}

function buildJobDamageStats(entries) {
  const groupedByJob = new Map();

  for (const entry of entries || []) {
    if (!entry?.job || !isDamageComparisonEntry(entry)) {
      continue;
    }

    if (!groupedByJob.has(entry.job)) {
      groupedByJob.set(entry.job, {
        dps: [],
        rdps: [],
        adps: [],
        entry_count: 0,
      });
    }

    const bucket = groupedByJob.get(entry.job);
    bucket.entry_count += 1;
    bucket.dps.push(entry.dps);
    bucket.rdps.push(entry.rdps ?? entry.dps);
    bucket.adps.push(entry.adps);
  }

  return Array.from(groupedByJob.entries())
    .map(([job, bucket]) => ({
      job,
      ...getJobRole(job),
      entry_count: bucket.entry_count,
      metrics: {
        dps: buildDamageMetricStats(bucket.dps),
        rdps: buildDamageMetricStats(bucket.rdps),
        adps: buildDamageMetricStats(bucket.adps),
      },
    }))
    .filter((item) => item.metrics.dps || item.metrics.rdps || item.metrics.adps)
    .sort((left, right) => {
      const leftScore = left.metrics.rdps?.median ?? left.metrics.dps?.median ?? 0;
      const rightScore = right.metrics.rdps?.median ?? right.metrics.dps?.median ?? 0;
      return rightScore - leftScore || compareByLocale(left.job, right.job);
    });
}

function buildServerDamageStats(entries) {
  const groupedByServer = new Map();

  for (const entry of entries || []) {
    const server = entry?.server;
    if (!server || !isDamageComparisonEntry(entry)) {
      continue;
    }

    if (!groupedByServer.has(server)) {
      groupedByServer.set(server, []);
    }
    groupedByServer.get(server).push(entry);
  }

  return Array.from(groupedByServer.entries())
    .map(([server, serverEntries]) => ({
      server,
      entry_count: serverEntries.length,
      damage_stats: buildJobDamageStats(serverEntries),
    }))
    .sort((left, right) => compareByLocale(left.server, right.server));
}

function attachDamageStatsToServers(serverStats, entries) {
  const damageStatsByServer = new Map(buildServerDamageStats(entries).map((item) => [item.server, item]));
  return (serverStats || []).map((serverStatsItem) => {
    const damageStats = damageStatsByServer.get(serverStatsItem.server);
    return {
      ...serverStatsItem,
      damage_stats: damageStats?.damage_stats || [],
    };
  });
}

function getJobRole(job) {
  return (
    jobRoleByJob.get(job) || {
      role: "role:unknown",
      role_name: "其他職業",
    }
  );
}

function addDistributionRecord(distribution, key, recordKey) {
  const normalizedKey = key || "未知";
  let bucket = distribution.get(normalizedKey);
  if (!bucket) {
    bucket = {
      recordKeys: new Set(),
      entry_count: 0,
    };
    distribution.set(normalizedKey, bucket);
  }

  bucket.recordKeys.add(recordKey);
  bucket.entry_count += 1;
  return bucket;
}

function buildDistributionList(distribution, totalRecords, keyName) {
  return Array.from(distribution.entries())
    .map(([key, bucket]) => ({
      [keyName]: key,
      clear_count: bucket.recordKeys.size,
      entry_count: bucket.entry_count,
      percentage: toPercent(bucket.recordKeys.size, totalRecords),
      ...(keyName === "job" ? getJobRole(key) : {}),
    }))
    .sort((left, right) => {
      if (left.clear_count !== right.clear_count) {
        return right.clear_count - left.clear_count;
      }
      if (left.entry_count !== right.entry_count) {
        return right.entry_count - left.entry_count;
      }
      return compareByLocale(left[keyName], right[keyName]);
    });
}

function buildRoleDistributionList(distribution, totalRecords) {
  return Array.from(distribution.entries())
    .map(([role, bucket]) => ({
      role,
      role_name: jobRoleGroups.find((group) => group.role === role)?.role_name || "其他職業",
      clear_count: bucket.recordKeys.size,
      entry_count: bucket.entry_count,
      percentage: toPercent(bucket.recordKeys.size, totalRecords),
    }))
    .sort((left, right) => {
      if (left.clear_count !== right.clear_count) {
        return right.clear_count - left.clear_count;
      }
      if (left.entry_count !== right.entry_count) {
        return right.entry_count - left.entry_count;
      }
      return compareByLocale(left.role_name, right.role_name);
    });
}

function buildServerDistributionList(distribution, totalRecords) {
  return Array.from(distribution.entries())
    .map(([server, bucket]) => {
      const roleRecordTotal = bucket.roleRecordKeys?.size || 0;
      const jobRecordTotal = bucket.jobRecordKeys?.size || 0;
      return {
        server,
        clear_count: bucket.recordKeys.size,
        role_record_count: roleRecordTotal,
        job_record_count: jobRecordTotal,
        entry_count: bucket.entry_count,
        percentage: toPercent(bucket.recordKeys.size, totalRecords),
        role_stats: buildRoleDistributionList(bucket.roleDistribution || new Map(), roleRecordTotal),
        job_stats: buildDistributionList(bucket.jobDistribution || new Map(), jobRecordTotal, "job"),
      };
    })
    .sort((left, right) => {
      if (left.clear_count !== right.clear_count) {
        return right.clear_count - left.clear_count;
      }
      if (left.entry_count !== right.entry_count) {
        return right.entry_count - left.entry_count;
      }
      return compareByLocale(left.server, right.server);
    });
}

function collectScopeDistribution(entries, scopeKeyForEntry) {
  const characterKeys = new Set();
  const roleRecordKeys = new Set();
  const jobRecordKeys = new Set();
  const serverDistribution = new Map();
  const roleDistribution = new Map();
  const jobDistribution = new Map();

  for (const entry of entries) {
    const scopeKey =
      typeof scopeKeyForEntry === "function" ? scopeKeyForEntry(entry) : scopeKeyForEntry || entry.encounter_key || "unknown";
    const characterKey = `${scopeKey}:${characterServerKey(entry.character_name, entry.server)}`;
    const role = getJobRole(entry.job).role;
    const roleRecordKey = `${characterKey}:${role}`;
    const jobRecordKey = `${characterKey}:${entry.job}`;

    characterKeys.add(characterKey);
    roleRecordKeys.add(roleRecordKey);
    jobRecordKeys.add(jobRecordKey);
    const serverBucket = addDistributionRecord(serverDistribution, entry.server, characterKey);
    serverBucket.roleRecordKeys ||= new Set();
    serverBucket.jobRecordKeys ||= new Set();
    serverBucket.roleDistribution ||= new Map();
    serverBucket.jobDistribution ||= new Map();
    serverBucket.roleRecordKeys.add(roleRecordKey);
    serverBucket.jobRecordKeys.add(jobRecordKey);
    addDistributionRecord(serverBucket.roleDistribution, role, roleRecordKey);
    addDistributionRecord(serverBucket.jobDistribution, entry.job, jobRecordKey);
    addDistributionRecord(roleDistribution, role, roleRecordKey);
    addDistributionRecord(jobDistribution, entry.job, jobRecordKey);
  }

  return {
    character_count: characterKeys.size,
    role_record_count: roleRecordKeys.size,
    job_record_count: jobRecordKeys.size,
    entry_count: entries.length,
    server_stats: buildServerDistributionList(serverDistribution, characterKeys.size),
    role_stats: buildRoleDistributionList(roleDistribution, roleRecordKeys.size),
    job_stats: buildDistributionList(jobDistribution, jobRecordKeys.size, "job"),
  };
}

function collectEncounterStats(encounter, entries, updatedAtIso) {
  const distribution = collectScopeDistribution(entries, encounter.key);

  return {
    encounter_key: encounter.key,
    encounter_name: encounter.name,
    encounter_category: encounter.category || null,
    updated_at_iso: updatedAtIso || null,
    ...distribution,
    server_stats: attachDamageStatsToServers(distribution.server_stats, entries),
    damage_stats: buildJobDamageStats(entries),
    clear_share_percent: 0,
    top_server: distribution.server_stats[0] || null,
    top_job: distribution.job_stats[0] || null,
  };
}

function buildJobRankIndex(rankingEntries) {
  const groupedByJob = new Map();
  const rankIndex = new Map();

  for (const entry of rankingEntries || []) {
    if (!entry?.character_name || !entry?.server || !entry?.job) {
      continue;
    }

    if (!groupedByJob.has(entry.job)) {
      groupedByJob.set(entry.job, []);
    }
    groupedByJob.get(entry.job).push({
      ...entry,
      dps: toNumber(entry.dps),
      rdps: toNumber(entry.rdps ?? entry.dps),
      adps: toNumber(entry.adps),
      clear_time_seconds: toNumber(entry.clear_time_seconds),
    });
  }

  for (const entries of groupedByJob.values()) {
    entries.sort(compareEntriesByBestScore);
    entries.forEach((entry, index) => {
      rankIndex.set(characterJobKey(entry), {
        job_rank: index + 1,
        overall_rank: entry.rank ?? null,
      });
    });
  }

  return rankIndex;
}

function normalizeFileBaseName(characterName, usedNames) {
  const trimmed = String(characterName || "unknown").normalize("NFC").trim();
  const safeBaseName = trimmed
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "_")
    .replace(/\.+$/g, "")
    .trim() || "unknown";
  const reservedName = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(safeBaseName)
    ? `${safeBaseName}_`
    : safeBaseName;

  let candidate = reservedName;
  let suffix = 2;
  while (usedNames.has(candidate.toLocaleLowerCase("en-US"))) {
    candidate = `${reservedName}-${suffix}`;
    suffix += 1;
  }
  usedNames.add(candidate.toLocaleLowerCase("en-US"));
  return candidate;
}

function makePublicEntry({ encounter, report, reportCode, fight, player, fightPlayers }) {
  const characterName = player.name || player.character_name;
  const server = player.server;
  const job = player.job;
  if (!characterName || !server || !job || toNumber(player.dps) === null) {
    return null;
  }

  const clearTimeMs = toNumber(fight.clear_time_ms);
  const clearTimeSeconds = toNumber(fight.clear_time_seconds) ?? (clearTimeMs === null ? null : clearTimeMs / 1000);
  const activePercent =
    toNumber(player.active_percent) ?? calculateActivePercent(player.active_time_ms, clearTimeMs, clearTimeSeconds);
  const signature = {
    encounter_key: encounter.key,
    fight_hash: fight.fight_hash || null,
    report_code: reportCode,
    fight_id: fight.fight_id,
    character_name: characterName,
    server,
    job,
    active_time_ms: toNumber(player.active_time_ms),
    rdps: toNumber(player.rdps),
    adps: toNumber(player.adps),
    dps: toNumber(player.dps),
    total_damage: toNumber(player.total_damage),
  };

  return {
    id: createId(signature),
    encounter_key: encounter.key,
    encounter_name: encounter.name,
    encounter_category: encounter.category || null,
    character_name: characterName,
    server,
    job,
    dps: toNumber(player.dps),
    rdps: toNumber(player.rdps ?? player.dps),
    adps: toNumber(player.adps),
    ndps: toNumber(player.ndps),
    total_damage: toNumber(player.total_damage),
    active_time_ms: toNumber(player.active_time_ms),
    active_percent: activePercent,
    clear_time_ms: clearTimeMs,
    clear_time_seconds: clearTimeSeconds,
    recorded_at: toNumber(fight.recorded_at),
    recorded_at_iso: fight.recorded_at_iso || report.report_start_time_iso || null,
    report_code: reportCode,
    report_url: report.url || (reportCode ? `https://www.fflogs.com/reports/${reportCode}` : null),
    report_title: report.title || null,
    fight_id: fight.fight_id ?? null,
    rank: null,
    job_rank: null,
    overall_rank: null,
    duplicate_count: 1,
    teammates: fightPlayers
      .filter((teammate) => {
        const teammateName = teammate?.name || teammate?.character_name;
        return teammateName && teammate?.server && teammate?.job && !(teammateName === characterName && teammate.server === server);
      })
      .map((teammate) => ({
        character_name: teammate.name || teammate.character_name,
        server: teammate.server,
        job: teammate.job,
      })),
  };
}

function collectEntriesFromReports({ ranking, encounter }) {
  const entriesByExactKey = new Map();
  const rankIndex = buildJobRankIndex(ranking.ranking_entries || []);

  for (const [fallbackReportCode, report] of Object.entries(ranking.reports || {})) {
    if (!report || typeof report !== "object") {
      continue;
    }

    const reportCode = report.report_code || fallbackReportCode;
    for (const fight of report.fights || []) {
      if (!fight || typeof fight !== "object") {
        continue;
      }

      const fightPlayers = Array.isArray(fight.players) ? fight.players : [];
      for (const player of fightPlayers) {
        const entry = makePublicEntry({ encounter, report, reportCode, fight, player, fightPlayers });
        if (!entry) {
          continue;
        }

        const exactKey = createId({
          encounter_key: entry.encounter_key,
          fight_hash: fight.fight_hash || null,
          character_name: entry.character_name,
          server: entry.server,
          job: entry.job,
          active_time_ms: entry.active_time_ms,
          rdps: entry.rdps,
          adps: entry.adps,
          dps: entry.dps,
          total_damage: entry.total_damage,
        });
        const existing = entriesByExactKey.get(exactKey);
        if (existing) {
          existing.duplicate_count += 1;
          continue;
        }

        entriesByExactKey.set(exactKey, entry);
      }
    }
  }

  const entries = Array.from(entriesByExactKey.values());
  const bestByCharacterJob = new Map();

  for (const entry of entries) {
    const key = characterJobKey(entry);
    if (isBetterEntry(entry, bestByCharacterJob.get(key))) {
      bestByCharacterJob.set(key, entry);
    }
  }

  for (const [key, entry] of bestByCharacterJob.entries()) {
    const ranks = rankIndex.get(key);
    if (ranks) {
      entry.rank = ranks.job_rank;
      entry.job_rank = ranks.job_rank;
      entry.overall_rank = ranks.overall_rank;
    }
  }

  return entries;
}

function collectEntriesFromRankingEntries({ ranking, encounter }) {
  const rankIndex = buildJobRankIndex(ranking.ranking_entries || []);

  return (ranking.ranking_entries || [])
    .map((entry) => {
      const ranks = rankIndex.get(characterJobKey(entry)) || {};
      return {
        id: entry.id || createId({ encounter_key: encounter.key, entry }),
        encounter_key: encounter.key,
        encounter_name: encounter.name,
        encounter_category: encounter.category || null,
        character_name: entry.character_name,
        server: entry.server,
        job: entry.job,
        dps: toNumber(entry.dps),
        rdps: toNumber(entry.rdps ?? entry.dps),
        adps: toNumber(entry.adps),
        ndps: toNumber(entry.ndps),
        total_damage: toNumber(entry.total_damage),
        active_time_ms: toNumber(entry.active_time_ms),
        active_percent: toNumber(entry.active_percent),
        clear_time_ms: toNumber(entry.clear_time_ms),
        clear_time_seconds: toNumber(entry.clear_time_seconds),
        recorded_at: toNumber(entry.recorded_at),
        recorded_at_iso: entry.recorded_at_iso || entry.report_start_time_iso || null,
        report_code: entry.report_code,
        report_url: entry.report_url,
        report_title: entry.report_title || null,
        fight_id: entry.fight_id ?? null,
        rank: ranks.job_rank ?? null,
        job_rank: ranks.job_rank ?? null,
        overall_rank: ranks.overall_rank ?? entry.rank ?? null,
        duplicate_count: toNumber(entry.duplicate_count) || 1,
      };
    })
    .filter((entry) => entry.character_name && entry.server && entry.job && entry.dps !== null);
}

async function loadEncounters() {
  const encounters = await readJson(publicEncountersPath, null) ?? await readJson(configEncountersPath, []);
  if (!Array.isArray(encounters)) {
    throw new Error("Encounter config must be a JSON array.");
  }
  return encounters.filter((encounter) => encounter?.key && encounter?.name && encounter.enabled !== false);
}

async function loadRankingForEncounter(encounter) {
  const sourcePath = path.join(sourceRankingsDir, `${encounter.key}.json`);
  const publicPath = path.join(publicRankingsDir, `${encounter.key}.json`);
  const ranking = await readJson(existsSync(sourcePath) ? sourcePath : publicPath, null);
  return ranking && typeof ranking === "object" ? ranking : null;
}

function getOrCreateUser(usersByName, characterName) {
  let user = usersByName.get(characterName);
  if (!user) {
    user = {
      character_name: characterName,
      servers: new Set(),
      entriesByEncounter: new Map(),
      total_entries: 0,
      last_recorded_at_iso: null,
      best_entry: null,
      teammates: new Map(),
    };
    usersByName.set(characterName, user);
  }
  return user;
}

function addEntry(usersByName, entry) {
  const user = getOrCreateUser(usersByName, entry.character_name);
  user.servers.add(entry.server);
  user.total_entries += 1;

  const recordedAt = new Date(entry.recorded_at_iso || 0).getTime();
  const lastRecordedAt = new Date(user.last_recorded_at_iso || 0).getTime();
  if ((Number.isNaN(lastRecordedAt) ? 0 : lastRecordedAt) < (Number.isNaN(recordedAt) ? 0 : recordedAt)) {
    user.last_recorded_at_iso = entry.recorded_at_iso;
  }
  if (isBetterEntry(entry, user.best_entry)) {
    user.best_entry = entry;
  }

  for (const teammate of entry.teammates || []) {
    const key = characterServerKey(teammate.character_name, teammate.server);
    let teammateStats = user.teammates.get(key);
    if (!teammateStats) {
      teammateStats = {
        character_name: teammate.character_name,
        server: teammate.server,
        jobs: new Set(),
        encounters: new Map(),
        user_servers: new Map(),
        co_clear_count: 0,
        last_recorded_at_iso: null,
      };
      user.teammates.set(key, teammateStats);
    }

    teammateStats.co_clear_count += 1;
    teammateStats.jobs.add(teammate.job);
    teammateStats.user_servers.set(entry.server, (teammateStats.user_servers.get(entry.server) || 0) + 1);

    const encounterStats = teammateStats.encounters.get(entry.encounter_key) || {
      encounter_key: entry.encounter_key,
      encounter_name: entry.encounter_name,
      co_clear_count: 0,
    };
    encounterStats.co_clear_count += 1;
    teammateStats.encounters.set(entry.encounter_key, encounterStats);

    const entryRecordedAt = new Date(entry.recorded_at_iso || 0).getTime();
    const teammateLastRecordedAt = new Date(teammateStats.last_recorded_at_iso || 0).getTime();
    if ((Number.isNaN(teammateLastRecordedAt) ? 0 : teammateLastRecordedAt) < (Number.isNaN(entryRecordedAt) ? 0 : entryRecordedAt)) {
      teammateStats.last_recorded_at_iso = entry.recorded_at_iso;
    }
  }

  let encounterEntries = user.entriesByEncounter.get(entry.encounter_key);
  if (!encounterEntries) {
    encounterEntries = [];
    user.entriesByEncounter.set(entry.encounter_key, encounterEntries);
  }
  encounterEntries.push(entry);
}

function buildFrequentTeammates(user) {
  return Array.from(user.teammates.values())
    .map((teammate) => ({
      character_name: teammate.character_name,
      server: teammate.server,
      jobs: Array.from(teammate.jobs).sort(compareByLocale),
      co_clear_count: teammate.co_clear_count,
      last_recorded_at_iso: teammate.last_recorded_at_iso,
      user_servers: Array.from(teammate.user_servers.entries())
        .map(([server, coClearCount]) => ({
          server,
          co_clear_count: coClearCount,
        }))
        .sort((left, right) => right.co_clear_count - left.co_clear_count || compareByLocale(left.server, right.server)),
      encounters: Array.from(teammate.encounters.values())
        .sort((left, right) => right.co_clear_count - left.co_clear_count || compareByLocale(left.encounter_name, right.encounter_name))
        .slice(0, 4),
    }))
    .sort((left, right) => {
      if (left.co_clear_count !== right.co_clear_count) {
        return right.co_clear_count - left.co_clear_count;
      }

      const leftTime = new Date(left.last_recorded_at_iso || 0).getTime();
      const rightTime = new Date(right.last_recorded_at_iso || 0).getTime();
      if ((Number.isNaN(leftTime) ? 0 : leftTime) !== (Number.isNaN(rightTime) ? 0 : rightTime)) {
        return (Number.isNaN(rightTime) ? 0 : rightTime) - (Number.isNaN(leftTime) ? 0 : leftTime);
      }

      return compareByLocale(left.character_name, right.character_name);
    })
    .slice(0, 20);
}

function buildEntryPayload(entry) {
  const { teammates, ...payload } = entry;
  return payload;
}

function buildUserPayload(user, generatedAtIso, updatedAtIsoByEncounter) {
  const frequentTeammates = buildFrequentTeammates(user);
  const encounters = Array.from(user.entriesByEncounter.entries())
    .map(([encounterKey, entries]) => {
      entries.sort(compareEntriesByTimeThenScore);
      const bestByJob = new Map();
      let bestEntry = null;

      for (const entry of entries) {
        if (isBetterEntry(entry, bestEntry)) {
          bestEntry = entry;
        }
        if (isBetterEntry(entry, bestByJob.get(entry.job))) {
          bestByJob.set(entry.job, entry);
        }
      }

      return {
        encounter_key: encounterKey,
        encounter_name: bestEntry?.encounter_name || encounterKey,
        encounter_category: bestEntry?.encounter_category || null,
        updated_at_iso: updatedAtIsoByEncounter.get(encounterKey) || null,
        best_entry: bestEntry ? buildEntryPayload(bestEntry) : null,
        best_by_job: Array.from(bestByJob.values())
          .sort((left, right) => compareByLocale(left.job, right.job))
          .map(buildEntryPayload),
        public_entries: entries.map(buildEntryPayload),
      };
    })
    .sort((left, right) => {
      const categoryCompare = compareByLocale(left.encounter_category || "", right.encounter_category || "");
      return categoryCompare || compareByLocale(left.encounter_name, right.encounter_name);
    });

  return {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    character_name: user.character_name,
    servers: Array.from(user.servers).sort(compareByLocale),
    summary: {
      encounter_count: encounters.length,
      public_entry_count: user.total_entries,
      teammate_count: user.teammates.size,
      best_rdps: user.best_entry?.rdps ?? null,
      best_encounter_key: user.best_entry?.encounter_key ?? null,
      last_recorded_at_iso: user.last_recorded_at_iso,
    },
    frequent_teammates: frequentTeammates,
    encounters,
  };
}

async function main() {
  assertInside(path.join(rootDir, "public", "data"), outputDir);
  assertInside(publicDataDir, globalStatsPath);

  const encounters = await loadEncounters();
  const usersByName = new Map();
  const updatedAtIsoByEncounter = new Map();
  const overallCharacterKeys = new Set();
  const encounterStats = [];
  const allEntries = [];

  for (const encounter of encounters) {
    const ranking = await loadRankingForEncounter(encounter);
    if (!ranking) {
      continue;
    }

    if (ranking.updated_at_iso) {
      updatedAtIsoByEncounter.set(encounter.key, ranking.updated_at_iso);
    }

    const entries = ranking.reports
      ? collectEntriesFromReports({ ranking, encounter })
      : collectEntriesFromRankingEntries({ ranking, encounter });

    encounterStats.push(collectEncounterStats(encounter, entries, ranking.updated_at_iso));
    allEntries.push(...entries);

    for (const entry of entries) {
      overallCharacterKeys.add(characterServerKey(entry.character_name, entry.server));
      addEntry(usersByName, entry);
    }
  }

  await rm(outputDir, { recursive: true, force: true });
  await mkdir(outputDir, { recursive: true });

  const generatedAtIso = new Date().toISOString();
  const usedFileBaseNames = new Set();
  const indexUsers = [];

  for (const user of Array.from(usersByName.values()).sort((left, right) =>
    compareByLocale(left.character_name, right.character_name),
  )) {
    const fileBaseName = normalizeFileBaseName(user.character_name, usedFileBaseNames);
    const fileName = `${fileBaseName}.json`;
    const filePath = path.join(outputDir, fileName);
    const payload = buildUserPayload(user, generatedAtIso, updatedAtIsoByEncounter);
    await writeJson(filePath, payload);

    indexUsers.push({
      character_name: user.character_name,
      servers: payload.servers,
      file_path: `data/users/${fileName}`,
      encounter_count: payload.summary.encounter_count,
      public_entry_count: payload.summary.public_entry_count,
      best_rdps: payload.summary.best_rdps,
      last_recorded_at_iso: payload.summary.last_recorded_at_iso,
    });
  }

  const latestRankingUpdatedAt = Array.from(updatedAtIsoByEncounter.values()).sort().at(-1) || null;
  const globalDistribution = collectScopeDistribution(allEntries, (entry) => entry.encounter_key);
  const savageDamageComparisonEntries = allEntries.filter((entry) => savageDamageComparisonEncounterKeySet.has(entry.encounter_key));
  const totalEncounterClearCount = globalDistribution.character_count;
  const totalJobClearCount = globalDistribution.job_record_count;
  const normalizedEncounterStats = encounterStats.map((encounter) => ({
    ...encounter,
    clear_share_percent: toPercent(encounter.character_count, overallCharacterKeys.size),
  }));

  await writeJson(path.join(outputDir, "index.json"), {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    rankings_updated_at_iso: latestRankingUpdatedAt,
    total_users: indexUsers.length,
    users: indexUsers,
  });

  await writeJson(globalStatsPath, {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    rankings_updated_at_iso: latestRankingUpdatedAt,
    total_character_count: overallCharacterKeys.size,
    total_encounter_clear_count: totalEncounterClearCount,
    total_role_clear_count: globalDistribution.role_record_count,
    total_job_clear_count: totalJobClearCount,
    total_entry_count: globalDistribution.entry_count,
    encounter_count: normalizedEncounterStats.length,
    server_stats: attachDamageStatsToServers(globalDistribution.server_stats, allEntries),
    role_stats: globalDistribution.role_stats,
    job_stats: globalDistribution.job_stats,
    damage_stats: buildJobDamageStats(allEntries),
    savage_damage_comparison_encounter_keys: savageDamageComparisonEncounterKeys,
    savage_damage_stats: buildJobDamageStats(savageDamageComparisonEntries),
    savage_server_damage_stats: buildServerDamageStats(savageDamageComparisonEntries),
    encounters: normalizedEncounterStats,
  });

  console.log(`Built ${indexUsers.length} user data files in ${path.relative(rootDir, outputDir)}.`);
  console.log(`Built global stats in ${path.relative(rootDir, globalStatsPath)}.`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
