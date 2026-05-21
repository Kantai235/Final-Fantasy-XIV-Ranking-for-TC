import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, open, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { fileURLToPath } from "node:url";

// 本檔是資料管線的 Data Building Layer。
// 它讀取 data/rankings 的可追溯原始資料與 ranking_entries，聚合成前端可直接讀取的靜態 JSON。
// 請勿在 Vue 元件中重做這裡的排序、去重、分位數或隊友統計，否則各頁會出現不一致的結果。
const defaultRootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const rootDir = path.resolve(process.env.FFXIV_TC_ROOT_DIR || defaultRootDir);
const sourceRankingsDir = path.join(rootDir, "data", "rankings");
const basePublicDataDir = path.join(rootDir, "public", "data");
const publicRankingsDir = path.join(basePublicDataDir, "rankings");
const publicEncountersPath = path.join(basePublicDataDir, "encounters.json");
const configEncountersPath = path.join(rootDir, "config", "encounters.json");
// 目前箱型圖只比較現行零式系列；其他副本仍會進入全服統計與個人成績單。
// minimumDamageActivePercent 用來排除明顯中途死亡或缺乏輸出時間的樣本，避免分位數被極端異常值拉歪。
const savageDamageComparisonEncounterKeys = ["savage_m1s", "savage_m2s", "savage_m3s", "savage_m4s"];
const savageDamageComparisonEncounterKeySet = new Set(savageDamageComparisonEncounterKeys);
const minimumDamageActivePercent = 50;
const activityWindowDays = 7;
const recentActivityLimit = 40;
const teamRecordsPerEncounterLimit = 50;
const versionRecordModes = ["all", "valid", "obsolete"];
const jsonWriteRetryCount = 10;
const jsonWriteRetryDelayMs = 500;
const jsonWriteChunkBytes = 1024 * 1024;
const transientWriteErrorCodes = new Set(["EBUSY", "EPERM", "UNKNOWN"]);
const transientRemoveErrorCodes = new Set(["EBUSY", "EMFILE", "ENFILE", "ENOTEMPTY", "EPERM", "UNKNOWN"]);

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
const jobRoleOrder = new Map(jobRoleGroups.map((group, index) => [group.role, index]));

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

function isTransientWriteError(error) {
  return transientWriteErrorCodes.has(error?.code);
}

function formatWritePath(filePath) {
  const relativePath = path.relative(rootDir, filePath);
  return relativePath && !relativePath.startsWith("..") && !path.isAbsolute(relativePath)
    ? relativePath
    : filePath;
}

async function overwriteFileInPlace(filePath, payload) {
  const buffer = Buffer.from(payload, "utf8");
  const file = await open(filePath, "r+");

  try {
    let offset = 0;
    while (offset < buffer.length) {
      const length = Math.min(jsonWriteChunkBytes, buffer.length - offset);
      const { bytesWritten } = await file.write(buffer, offset, length, offset);
      if (bytesWritten === 0) {
        throw new Error(`無法繼續寫入 JSON 檔案：${formatWritePath(filePath)}`);
      }
      offset += bytesWritten;
    }

    await file.truncate(buffer.length);
    await file.sync();
  } finally {
    await file.close();
  }
}

async function writeJson(filePath, data) {
  const payload = `${JSON.stringify(data)}\n`;
  const tempPath = path.join(
    path.dirname(filePath),
    `.${path.basename(filePath)}.${process.pid}.${Date.now()}.tmp`,
  );

  await mkdir(path.dirname(filePath), { recursive: true });

  let lastTransientError = null;
  try {
    await writeFile(tempPath, payload, "utf8");

    for (let attempt = 1; attempt <= jsonWriteRetryCount; attempt += 1) {
      try {
        await rename(tempPath, filePath);
        return;
      } catch (error) {
        if (!isTransientWriteError(error)) {
          throw error;
        }

        lastTransientError = error;
        if (attempt === jsonWriteRetryCount) {
          break;
        }

        const waitMs = jsonWriteRetryDelayMs * attempt;
        console.warn(
          `JSON 檔案暫時被鎖定，${(waitMs / 1000).toFixed(1)} 秒後重試寫入：${formatWritePath(filePath)}`,
        );
        await sleep(waitMs);
      }
    }

    if (process.platform === "win32" && existsSync(filePath) && lastTransientError) {
      // Windows 上有些讀取端允許讀取但不允許替換或刪除共享權限，導致 rename 連續失敗。
      // 這裡保留「先寫暫存檔」的驗證流程，只在替換語意被鎖住時才退回就地覆寫既有檔案。
      try {
        await overwriteFileInPlace(filePath, payload);
        console.warn(`JSON 檔案無法原子替換，已改用就地覆寫：${formatWritePath(filePath)}`);
        return;
      } catch (error) {
        lastTransientError = error;
      }
    }

    throw new Error(
      `無法寫入 JSON 檔案：${formatWritePath(filePath)}，請確認檔案未被編輯器、同步軟體、本機伺服器或防護軟體鎖定。`,
      { cause: lastTransientError },
    );
  } finally {
    await rm(tempPath, { force: true }).catch(() => {});
  }
}

async function removeGeneratedDirectory(dirPath) {
  for (let attempt = 1; attempt <= jsonWriteRetryCount; attempt += 1) {
    try {
      await rm(dirPath, {
        recursive: true,
        force: true,
        maxRetries: 2,
        retryDelay: 100,
      });
      return;
    } catch (error) {
      if (!transientRemoveErrorCodes.has(error?.code)) {
        throw error;
      }

      if (attempt === jsonWriteRetryCount) {
        throw new Error(
          `無法清理衍生資料目錄：${formatWritePath(dirPath)}，`
            + "請確認目錄內檔案未被編輯器、同步軟體、本機伺服器或防護軟體鎖定。",
          { cause: error },
        );
      }

      const waitMs = jsonWriteRetryDelayMs * attempt;
      console.warn(
        `衍生資料目錄暫時無法清理，${(waitMs / 1000).toFixed(1)} 秒後重試：${formatWritePath(dirPath)}`,
      );
      await sleep(waitMs);
    }
  }
}

async function waitForUserOutputReady(outputDir, expectedUserCount, label) {
  const expectedEntryCount = expectedUserCount + 1; // 每位玩家一檔，加上 users/index.json。

  for (let attempt = 0; attempt < 20; attempt += 1) {
    let entries = [];
    try {
      entries = await readdir(outputDir);
    } catch (error) {
      if (error?.code !== "ENOENT") {
        throw error;
      }
    }

    if (entries.includes("index.json") && entries.length >= expectedEntryCount) {
      return;
    }

    // Windows 在大量重建 users JSON 後，下一個 Vite copy 有時會先看到半更新的目錄狀態。
    // 這裡等到 index 與檔案數都可穩定列舉，避免 production build 偶發 ENOENT。
    await sleep(250);
  }

  const entries = await readdir(outputDir).catch(() => []);
  throw new Error(
    `${label} 使用者資料輸出尚未穩定：${path.relative(rootDir, outputDir)} 目前 ${entries.length} 筆，預期至少 ${expectedEntryCount} 筆。`,
  );
}

function resolveGeneratedAtIso(latestRankingUpdatedAt) {
  const override = String(process.env.FFXIV_TC_GENERATED_AT_ISO || "").trim();
  if (override) {
    const overrideTime = new Date(override).getTime();
    if (!Number.isNaN(overrideTime)) {
      return new Date(overrideTime).toISOString();
    }
    throw new Error("FFXIV_TC_GENERATED_AT_ISO must be a valid ISO timestamp.");
  }

  // public/data/global_stats.json 是會被 Git 追蹤的衍生資料。
  // 若同一批 ranking 重建時總是寫入目前時間，排程會產生沒有資料意義的 diff；
  // 因此預設以來源 ranking 的最新更新時間作為產物時間戳，只有沒有來源時間時才退回現在時間。
  const latestRankingTime = new Date(latestRankingUpdatedAt || 0).getTime();
  return Number.isNaN(latestRankingTime) || latestRankingTime <= 0
    ? new Date().toISOString()
    : new Date(latestRankingTime).toISOString();
}

function toNumber(value) {
  const numberValue = Number(value);
  return Number.isFinite(numberValue) ? numberValue : null;
}

function isHiddenReport(report) {
  return Boolean(report?.report_hidden || report?.hidden_report);
}

function isHiddenEntry(entry) {
  return Boolean(entry?.report_hidden || entry?.hidden_report);
}

function hiddenReportFields(report) {
  if (!isHiddenReport(report)) {
    return {};
  }

  return {
    report_hidden: true,
    hidden_reason: report.hidden_reason || null,
    hidden_detected_at_iso: report.hidden_detected_at_iso || null,
    hidden_source: report.hidden_source || null,
  };
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
  // 與 fetch_fflogs.py 的「最佳成績」規則保持一致：
  // rDPS 優先，平手看通關時間，再看 aDPS，最後以較新的紀錄補齊決定性。
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

function toPositiveRank(value) {
  const rank = toNumber(value);
  return rank !== null && rank > 0 ? rank : null;
}

function toFflogsSourceId(value) {
  const sourceId = toNumber(value);
  return sourceId !== null && sourceId > 0 ? Math.trunc(sourceId) : null;
}

function entryJobRank(entry) {
  return toPositiveRank(entry?.job_rank ?? entry?.rank);
}

function entryTopPercent(entry) {
  const topPercent = toNumber(entry?.performance?.top_percent);
  return topPercent !== null && topPercent >= 0 ? topPercent : null;
}

function isBetterProfileEntry(candidate, currentBest) {
  // 個人成績單的代表職業不能直接跨職業比 raw rDPS，否則坦補玩家只要有一筆輸出職業紀錄，
  // 預設履歷就容易被 DPS 數值蓋過。這裡優先用同副本同職業的 rank，才回退到 rDPS 最佳規則。
  if (!candidate) {
    return false;
  }
  if (!currentBest) {
    return true;
  }

  const candidateRank = entryJobRank(candidate);
  const currentRank = entryJobRank(currentBest);
  if (candidateRank !== null || currentRank !== null) {
    if (candidateRank === null) {
      return false;
    }
    if (currentRank === null) {
      return true;
    }
    if (candidateRank !== currentRank) {
      return candidateRank < currentRank;
    }
  }

  const candidateTopPercent = entryTopPercent(candidate);
  const currentTopPercent = entryTopPercent(currentBest);
  if (candidateTopPercent !== null || currentTopPercent !== null) {
    if (candidateTopPercent === null) {
      return false;
    }
    if (currentTopPercent === null) {
      return true;
    }
    if (candidateTopPercent !== currentTopPercent) {
      return candidateTopPercent < currentTopPercent;
    }
  }

  return isBetterEntry(candidate, currentBest);
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

function roundPercent(value) {
  return value === null ? null : Number(value.toFixed(2));
}

function entryRecordedAtMs(entry) {
  const time = new Date(entry?.recorded_at_iso || 0).getTime();
  return Number.isNaN(time) ? 0 : time;
}

function getEncounterVersionCutoff(encounter) {
  const rule = encounter?.version_cutoff;
  if (!rule || typeof rule !== "object" || !rule.obsolete_after_iso) {
    return null;
  }

  const cutoffTime = new Date(rule.obsolete_after_iso).getTime();
  if (Number.isNaN(cutoffTime)) {
    return null;
  }

  return {
    ...rule,
    obsolete_after_iso: new Date(cutoffTime).toISOString(),
  };
}

function isObsoleteRecord(entry, encounter) {
  const cutoff = getEncounterVersionCutoff(encounter);
  if (!cutoff) {
    return false;
  }

  const recordedAt = entryRecordedAtMs(entry);
  const cutoffAt = new Date(cutoff.obsolete_after_iso).getTime();
  return recordedAt > 0 && !Number.isNaN(cutoffAt) && recordedAt >= cutoffAt;
}

function attachVersionState(entry, encounter) {
  const cutoff = getEncounterVersionCutoff(encounter);
  if (!cutoff) {
    return entry;
  }

  const isObsolete = isObsoleteRecord(entry, encounter);
  entry.is_obsolete_record = isObsolete;
  entry.version_status = isObsolete ? "obsolete" : "valid";
  entry.version_cutoff_iso = cutoff.obsolete_after_iso;
  return entry;
}

function filterEntriesByVersionMode(entries, versionMode) {
  if (versionMode === "obsolete") {
    return entries.filter((entry) => entry.is_obsolete_record);
  }
  if (versionMode === "valid") {
    return entries.filter((entry) => !entry.is_obsolete_record);
  }
  return entries;
}

function buildEntrySummary(entry) {
  return {
    id: entry.id,
    encounter_key: entry.encounter_key,
    encounter_name: entry.encounter_name,
    encounter_category: entry.encounter_category,
    character_name: entry.character_name,
    server: entry.server,
    job: entry.job,
    dps: entry.dps,
    rdps: entry.rdps,
    adps: entry.adps,
    active_percent: entry.active_percent,
    gcd_coverage: entry.gcd_coverage,
    gcd_coverage_status: entry.gcd_coverage_status,
    clear_time_seconds: entry.clear_time_seconds,
    recorded_at_iso: entry.recorded_at_iso,
    report_code: entry.report_code,
    report_url: entry.report_url,
    ...(entry.fflogs_source_id !== null && entry.fflogs_source_id !== undefined
      ? { fflogs_source_id: entry.fflogs_source_id }
      : {}),
    rank: entry.rank,
    job_rank: entry.job_rank,
    performance: entry.performance || null,
    is_obsolete_record: Boolean(entry.is_obsolete_record),
    version_status: entry.version_status || null,
    version_cutoff_iso: entry.version_cutoff_iso || null,
  };
}

function attachRdpsPerformance(entries) {
  // 個人成績分位必須在 Data Building Layer 先算好，避免 Vue 針對每位角色重新掃描全站成績。
  // 分位母體限定「同副本、同職業、Active 達標」的公開紀錄，和職業輸出箱型圖使用同一套樣本門檻。
  const buckets = new Map();

  for (const entry of entries) {
    entry.performance = {
      qualified: false,
      active_threshold: minimumDamageActivePercent,
      sample_count: 0,
      reason: entry.is_obsolete_record ? "obsolete_record" : "active_low_or_missing",
    };

    if (entry.is_obsolete_record) {
      continue;
    }

    if (!entry?.encounter_key || !entry?.job || toNumber(entry.rdps) === null || !isDamageComparisonEntry(entry)) {
      continue;
    }

    const key = `${entry.encounter_key}:${entry.job}`;
    if (!buckets.has(key)) {
      buckets.set(key, []);
    }
    buckets.get(key).push(entry);
  }

  for (const bucketEntries of buckets.values()) {
    bucketEntries.sort((left, right) => (right.rdps ?? 0) - (left.rdps ?? 0) || entryRecordedAtMs(right) - entryRecordedAtMs(left));
    const valuesAsc = bucketEntries
      .map((entry) => toNumber(entry.rdps))
      .filter((value) => value !== null && value > 0)
      .sort((left, right) => left - right);
    const sampleCount = bucketEntries.length;
    const median = roundDamageStat(percentile(valuesAsc, 0.5));
    const q3 = roundDamageStat(percentile(valuesAsc, 0.75));
    const top10Index = Math.min(sampleCount - 1, Math.max(0, Math.ceil(sampleCount * 0.1) - 1));
    const top10Threshold = roundDamageStat(bucketEntries[top10Index]?.rdps ?? null);
    let previousValue = null;
    let previousRank = 0;

    bucketEntries.forEach((entry, index) => {
      const rdps = toNumber(entry.rdps) || 0;
      const rank = rdps === previousValue ? previousRank : index + 1;
      previousValue = rdps;
      previousRank = rank;

      entry.performance = {
        qualified: true,
        active_threshold: minimumDamageActivePercent,
        sample_count: sampleCount,
        rank,
        top_percent: roundPercent((rank / sampleCount) * 100),
        score_percentile: roundPercent(((sampleCount - rank + 1) / sampleCount) * 100),
        median_rdps: median,
        q3_rdps: q3,
        top10_rdps: top10Threshold,
        delta_to_median: median === null ? null : roundDamageStat(rdps - median),
        delta_to_q3: q3 === null ? null : roundDamageStat(rdps - q3),
        gap_to_top10: top10Threshold === null ? null : roundDamageStat(Math.max(0, top10Threshold - rdps)),
      };
    });
  }
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
  // clear_count 以「角色@伺服器」去重；role/job record 則保留同角色不同職能或職業的紀錄。
  // 這是為了讓伺服器人口分布與職業分布各自回答不同問題，不把多職玩家誤算成多個角色。
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

function collectEncounterStatsCore(encounter, entries, updatedAtIso) {
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

function collectEncounterStats(encounter, entries, updatedAtIso) {
  const stats = collectEncounterStatsCore(encounter, entries, updatedAtIso);
  const versionCutoff = getEncounterVersionCutoff(encounter);
  if (!versionCutoff) {
    return stats;
  }

  // 過版切片在 Data Building Layer 預先算好，讓 Vue 只切換已完成的統計結果。
  // 這能避免前端為了「有效版本」重做去重、職業分布、伺服器分布與傷害統計，降低頁面間規則分歧。
  stats.version_cutoff = versionCutoff;
  stats.version_slices = Object.fromEntries(
    versionRecordModes.map((versionMode) => [
      versionMode,
      {
        ...collectEncounterStatsCore(encounter, filterEntriesByVersionMode(entries, versionMode), updatedAtIso),
        version_cutoff: versionCutoff,
        version_mode: versionMode,
      },
    ]),
  );
  return stats;
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

function clearRankMetadata(entry) {
  entry.rank = null;
  entry.job_rank = null;
  entry.overall_rank = null;
}

function assignValidVersionJobRanks(entries) {
  // 個人成績單的職業 Rank 代表「副本仍屬當版本難度時」的排名。
  // 過版後的裝備品級與可跳過機制會改變成績意義，因此過版紀錄不參與排名，也不保留舊 rank。
  const bestValidByCharacterJob = new Map();

  for (const entry of entries || []) {
    clearRankMetadata(entry);
    if (entry.is_obsolete_record) {
      continue;
    }

    const key = characterJobKey(entry);
    if (isBetterEntry(entry, bestValidByCharacterJob.get(key))) {
      bestValidByCharacterJob.set(key, entry);
    }
  }

  const bestValidEntries = Array.from(bestValidByCharacterJob.values());
  for (const jobEntries of groupEntriesBy(bestValidEntries, (entry) => entry.job).values()) {
    jobEntries.sort(compareEntriesByBestScore);
    jobEntries.forEach((entry, index) => {
      const rank = index + 1;
      entry.rank = rank;
      entry.job_rank = rank;
    });
  }
}

function indexToRank(index) {
  return index >= 0 ? index + 1 : null;
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
  // 個人成績單需要同場隊友、職業排名與完整時間欄位，因此這裡會從 report/fight/player 重組公開 entry。
  // 若來源只有 ranking_entries，collectEntriesFromRankingEntries 會走相容路徑，但就不會有隊友資訊。
  const characterName = player.name || player.character_name;
  const server = player.server;
  const job = player.job;
  if (!characterName || !server || !job || toNumber(player.dps) === null) {
    return null;
  }

  const clearTimeMs = toNumber(fight.clear_time_ms);
  const clearTimeSeconds = toNumber(fight.clear_time_seconds) ?? (clearTimeMs === null ? null : clearTimeMs / 1000);
  const fflogsTotalTimeMs = toNumber(fight.fflogs_total_time_ms);
  const fflogsTotalTimeSeconds = fflogsTotalTimeMs === null ? null : fflogsTotalTimeMs / 1000;
  const damageDowntimeMs = toNumber(fight.damage_downtime_ms);
  const damageTimeMs = toNumber(fight.damage_time_ms);
  const damageDowntimeSeconds =
    toNumber(fight.damage_downtime_seconds) ?? (damageDowntimeMs === null ? null : damageDowntimeMs / 1000);
  const damageTimeSeconds = toNumber(fight.damage_time_seconds) ?? (damageTimeMs === null ? null : damageTimeMs / 1000);
  const fflogsSourceId = toFflogsSourceId(player.fflogs_source_id ?? player.fflogs_id ?? player.source_id);
  // FFLogs Damage Done CSV 的 Active% 使用 totalTime，而 DPS/rDPS 使用 combatTime - downtime。
  // 這兩個分母不同；這裡優先用 fflogs_total_time_ms，避免個人成績單與排行榜重建時偏離 FFLogs 顯示值。
  const activePercentDurationMs = fflogsTotalTimeMs ?? clearTimeMs;
  const activePercentDurationSeconds = fflogsTotalTimeSeconds ?? clearTimeSeconds;
  const activePercent =
    toNumber(player.active_percent) ??
    calculateActivePercent(player.active_time_ms, activePercentDurationMs, activePercentDurationSeconds);
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
    damage_time_ms: damageTimeMs,
  };

  const entry = {
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
    ...(Object.hasOwn(player, "gcd_coverage") ? { gcd_coverage: player.gcd_coverage } : {}),
    ...(Object.hasOwn(player, "gcd_coverage_status") ? { gcd_coverage_status: player.gcd_coverage_status } : {}),
    clear_time_ms: clearTimeMs,
    clear_time_seconds: clearTimeSeconds,
    damage_downtime_ms: damageDowntimeMs,
    damage_downtime_seconds: damageDowntimeSeconds,
    damage_time_ms: damageTimeMs,
    damage_time_seconds: damageTimeSeconds,
    recorded_at: toNumber(fight.recorded_at),
    recorded_at_iso: fight.recorded_at_iso || report.report_start_time_iso || null,
    report_code: reportCode,
    report_url: report.url || (reportCode ? `https://www.fflogs.com/reports/${reportCode}` : null),
    ...(fflogsSourceId !== null ? { fflogs_source_id: fflogsSourceId } : {}),
    report_title: report.title || null,
    fight_id: fight.fight_id ?? null,
    rank: null,
    job_rank: null,
    overall_rank: null,
    duplicate_count: 1,
    ...hiddenReportFields(report),
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
  return attachVersionState(entry, encounter);
}

function collectEntriesFromReports({ ranking, encounter, includeHiddenReports = false }) {
  // 完整 reports 是最可信來源：它能辨識同場玩家、重複上傳與 fight_hash。
  // exactKey 不含 report_code，讓同一場戰鬥被多名隊員上傳時只算一次，duplicate_count 保留來源數。
  const entriesByExactKey = new Map();
  const rankIndex = buildJobRankIndex(ranking.ranking_entries || []);

  for (const [fallbackReportCode, report] of Object.entries(ranking.reports || {})) {
    if (!report || typeof report !== "object") {
      continue;
    }
    if (isHiddenReport(report) && !includeHiddenReports) {
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
          damage_time_ms: entry.damage_time_ms,
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

function collectEntriesFromRankingEntries({ ranking, encounter, includeHiddenReports = false }) {
  const rankIndex = buildJobRankIndex(ranking.ranking_entries || []);

  return (ranking.ranking_entries || [])
    .filter((entry) => includeHiddenReports || !isHiddenEntry(entry))
    .map((entry) => {
      const ranks = rankIndex.get(characterJobKey(entry)) || {};
      const fflogsSourceId = toFflogsSourceId(entry.fflogs_source_id ?? entry.fflogs_id ?? entry.source_id);
      const normalizedEntry = {
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
        ...(Object.hasOwn(entry, "gcd_coverage") ? { gcd_coverage: entry.gcd_coverage } : {}),
        ...(Object.hasOwn(entry, "gcd_coverage_status") ? { gcd_coverage_status: entry.gcd_coverage_status } : {}),
        clear_time_ms: toNumber(entry.clear_time_ms),
        clear_time_seconds: toNumber(entry.clear_time_seconds),
        damage_downtime_ms: toNumber(entry.damage_downtime_ms),
        damage_downtime_seconds: toNumber(entry.damage_downtime_seconds),
        damage_time_ms: toNumber(entry.damage_time_ms),
        damage_time_seconds: toNumber(entry.damage_time_seconds),
        recorded_at: toNumber(entry.recorded_at),
        recorded_at_iso: entry.recorded_at_iso || entry.report_start_time_iso || null,
        report_code: entry.report_code,
        report_url: entry.report_url,
        ...(fflogsSourceId !== null ? { fflogs_source_id: fflogsSourceId } : {}),
        report_title: entry.report_title || null,
        fight_id: entry.fight_id ?? null,
        rank: ranks.job_rank ?? null,
        job_rank: ranks.job_rank ?? null,
        overall_rank: ranks.overall_rank ?? entry.rank ?? null,
        duplicate_count: toNumber(entry.duplicate_count) || 1,
        ...(isHiddenEntry(entry)
          ? {
              report_hidden: true,
              hidden_reason: entry.hidden_reason || null,
              hidden_detected_at_iso: entry.hidden_detected_at_iso || null,
              hidden_source: entry.hidden_source || null,
            }
          : {}),
      };
      return attachVersionState(normalizedEntry, encounter);
    })
    .filter((entry) => entry.character_name && entry.server && entry.job && entry.dps !== null);
}

function collectHiddenUserStubsFromReports(ranking) {
  const stubsByCharacterServer = new Map();

  for (const report of Object.values(ranking.reports || {})) {
    if (!report || typeof report !== "object" || !isHiddenReport(report)) {
      continue;
    }

    for (const fight of report.fights || []) {
      if (!fight || typeof fight !== "object") {
        continue;
      }

      for (const player of Array.isArray(fight.players) ? fight.players : []) {
        const characterName = player?.name || player?.character_name;
        const server = player?.server;
        if (!characterName || !server) {
          continue;
        }

        stubsByCharacterServer.set(characterServerKey(characterName, server), {
          character_name: characterName,
          server,
        });
      }
    }
  }

  return Array.from(stubsByCharacterServer.values());
}

function collectHiddenUserStubsFromRankingEntries(ranking) {
  const stubsByCharacterServer = new Map();

  for (const entry of ranking.ranking_entries || []) {
    if (!isHiddenEntry(entry)) {
      continue;
    }

    const characterName = entry?.character_name;
    const server = entry?.server;
    if (!characterName || !server) {
      continue;
    }

    stubsByCharacterServer.set(characterServerKey(characterName, server), {
      character_name: characterName,
      server,
    });
  }

  return Array.from(stubsByCharacterServer.values());
}

function collectHiddenUserStubs(ranking) {
  const stubsByCharacterServer = new Map();
  for (const stub of [
    ...collectHiddenUserStubsFromReports(ranking),
    ...collectHiddenUserStubsFromRankingEntries(ranking),
  ]) {
    stubsByCharacterServer.set(characterServerKey(stub.character_name, stub.server), stub);
  }
  return Array.from(stubsByCharacterServer.values());
}

function compareTeamPlayers(left, right) {
  const leftRoleOrder = jobRoleOrder.get(getJobRole(left.job).role) ?? Number.MAX_SAFE_INTEGER;
  const rightRoleOrder = jobRoleOrder.get(getJobRole(right.job).role) ?? Number.MAX_SAFE_INTEGER;
  return (
    leftRoleOrder - rightRoleOrder ||
    compareByLocale(left.job || "", right.job || "") ||
    compareByLocale(left.server || "", right.server || "") ||
    compareByLocale(left.character_name || "", right.character_name || "")
  );
}

function summarizeTeamPlayers(players) {
  return players
    .filter((player) => {
      const characterName = player?.name || player?.character_name;
      return characterName && player?.server && player?.job && toNumber(player?.dps) !== null;
    })
    .map((player) => {
      const fflogsSourceId = toFflogsSourceId(player.fflogs_source_id ?? player.fflogs_id ?? player.source_id);
      return {
        character_name: player.name || player.character_name,
        server: player.server,
        job: player.job,
        role: getJobRole(player.job).role,
        role_name: getJobRole(player.job).role_name,
        dps: toNumber(player.dps),
        rdps: toNumber(player.rdps ?? player.dps),
        adps: toNumber(player.adps),
        active_percent: toNumber(player.active_percent),
        ...(fflogsSourceId !== null ? { fflogs_source_id: fflogsSourceId } : {}),
        ...(Object.hasOwn(player, "gcd_coverage") ? { gcd_coverage: player.gcd_coverage } : {}),
        ...(Object.hasOwn(player, "gcd_coverage_status") ? { gcd_coverage_status: player.gcd_coverage_status } : {}),
      };
    })
    .sort(compareTeamPlayers);
}

function compareTeamRecords(left, right) {
  const clearTimeDiff = (left.clear_time_seconds ?? Infinity) - (right.clear_time_seconds ?? Infinity);
  if (clearTimeDiff !== 0) {
    return clearTimeDiff;
  }

  const damageDiff = (right.total_rdps ?? 0) - (left.total_rdps ?? 0);
  if (damageDiff !== 0) {
    return damageDiff;
  }

  return entryRecordedAtMs(right) - entryRecordedAtMs(left);
}

function buildTeamRecord({ encounter, report, reportCode, fight }) {
  const players = summarizeTeamPlayers(Array.isArray(fight?.players) ? fight.players : []);
  if (players.length !== 8) {
    return null;
  }

  const clearTimeMs = toNumber(fight.clear_time_ms);
  const clearTimeSeconds = toNumber(fight.clear_time_seconds) ?? (clearTimeMs === null ? null : clearTimeMs / 1000);
  if (clearTimeSeconds === null || clearTimeSeconds <= 0) {
    return null;
  }

  const totalRdps = players.reduce((sum, player) => sum + (toNumber(player.rdps) || 0), 0);
  const totalAdps = players.reduce((sum, player) => sum + (toNumber(player.adps) || 0), 0);
  const totalDps = players.reduce((sum, player) => sum + (toNumber(player.dps) || 0), 0);
  const identity = {
    encounter_key: encounter.key,
    fight_hash: fight.fight_hash || null,
    report_code: reportCode,
    fight_id: fight.fight_id ?? null,
    clear_time_seconds: clearTimeSeconds,
    players: players.map((player) => `${player.character_name}@${player.server}:${player.job}`),
  };

  const record = {
    id: createId(identity),
    encounter_key: encounter.key,
    encounter_name: encounter.name,
    encounter_category: encounter.category || null,
    clear_time_seconds: clearTimeSeconds,
    clear_time_ms: clearTimeMs,
    recorded_at_iso: fight.recorded_at_iso || report.report_start_time_iso || null,
    report_code: reportCode,
    report_url: report.url || (reportCode ? `https://www.fflogs.com/reports/${reportCode}` : null),
    fight_id: fight.fight_id ?? null,
    duplicate_count: 1,
    ...hiddenReportFields(report),
    total_rdps: roundDamageStat(totalRdps),
    total_adps: roundDamageStat(totalAdps),
    total_dps: roundDamageStat(totalDps),
    players,
  };
  return attachVersionState(record, encounter);
}

function collectTeamRecordsFromReports({ ranking, encounter, includeHiddenReports = false }) {
  // 隊伍榜以 fight 為單位，和個人榜不同：同一場戰鬥若被不同隊員上傳，只保留一筆並累計 duplicate_count。
  // fight_hash 是最佳識別來源；缺少時才退回 report/fight/player 簽章，避免誤合併不同隊伍的相近時間紀錄。
  const recordsByFight = new Map();

  for (const [fallbackReportCode, report] of Object.entries(ranking.reports || {})) {
    if (!report || typeof report !== "object") {
      continue;
    }
    if (isHiddenReport(report) && !includeHiddenReports) {
      continue;
    }

    const reportCode = report.report_code || fallbackReportCode;
    for (const fight of report.fights || []) {
      if (!fight || typeof fight !== "object") {
        continue;
      }

      const record = buildTeamRecord({ encounter, report, reportCode, fight });
      if (!record) {
        continue;
      }

      const dedupeKey = fight.fight_hash ? `${encounter.key}:${fight.fight_hash}` : record.id;
      const existing = recordsByFight.get(dedupeKey);
      if (existing) {
        existing.duplicate_count += 1;
        continue;
      }

      recordsByFight.set(dedupeKey, record);
    }
  }

  return Array.from(recordsByFight.values()).sort(compareTeamRecords);
}

async function loadEncounters() {
  // 優先讀 public/data/encounters.json，因為它代表「前端可見副本」；
  // config/encounters.json 的 enabled 只控制下一輪掃描，不應讓既有歷史資料在網站上消失。
  const encounters = await readJson(publicEncountersPath, null) ?? await readJson(configEncountersPath, []);
  if (!Array.isArray(encounters)) {
    throw new Error("Encounter config must be a JSON array.");
  }
  return encounters.filter((encounter) => encounter?.key && encounter?.name && encounter.enabled !== false);
}

async function loadRankingForEncounter(encounter) {
  const sourcePath = path.join(sourceRankingsDir, `${encounter.key}.json`);
  const publicPath = path.join(publicRankingsDir, `${encounter.key}.json`);
  const rankingPath = existsSync(sourcePath) ? sourcePath : publicPath;
  const ranking = await readJson(rankingPath, null);
  if (!ranking || typeof ranking !== "object") {
    return null;
  }

  const shardReports = await loadRankingReportShards(ranking);
  if (Object.keys(shardReports).length > 0) {
    ranking.reports = {
      ...(ranking.reports && typeof ranking.reports === "object" ? ranking.reports : {}),
      ...shardReports,
    };
  }

  return ranking;
}

async function loadRankingReportShards(ranking) {
  // ranking 主檔為了 Git 檔案大小只列 report_shards；實際報告資料在 data/rankings/*.reports/*.json。
  // assertInside 會阻止惡意或錯誤的分片路徑跳出 data/rankings。
  const shardPaths = Array.isArray(ranking.report_shards) ? ranking.report_shards : [];
  const reports = {};

  for (const shardPath of shardPaths) {
    if (typeof shardPath !== "string" || !shardPath) {
      continue;
    }

    const resolvedShardPath = path.resolve(rootDir, shardPath);
    assertInside(sourceRankingsDir, resolvedShardPath);
    const shardReports = await readJson(resolvedShardPath, {});
    if (shardReports && typeof shardReports === "object" && !Array.isArray(shardReports)) {
      Object.assign(reports, shardReports);
    }
  }

  return reports;
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
  // 個人成績單的最佳紀錄代表玩家在副本仍屬當版本難度時的表現；
  // 過版後裝備品級與可跳過機制會改變分數意義，因此只用有效版本紀錄更新 best_entry。
  if (!entry.is_obsolete_record && isBetterEntry(entry, user.best_entry)) {
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

function addHiddenUserStub(usersByName, stub) {
  const characterName = stub?.character_name;
  const server = stub?.server;
  if (!characterName || !server) {
    return;
  }

  // 一般公開成績單只保留可開啟的入口與伺服器辨識，不帶入非公開 entry 的成績或隊友資料。
  const user = getOrCreateUser(usersByName, characterName);
  user.servers.add(server);
}

function buildTeammateRows(user) {
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
    });
}

function buildFrequentTeammates(user) {
  return buildTeammateRows(user).slice(0, 20);
}

function buildEntryPayload(entry) {
  const { teammates, ...payload } = entry;
  return payload;
}

function pickProfileEntry(entries) {
  return (entries || []).reduce((best, entry) => (isBetterProfileEntry(entry, best) ? entry : best), null);
}

function buildUserPayload(user, generatedAtIso, updatedAtIsoByEncounter) {
  const frequentTeammates = buildFrequentTeammates(user);
  const allValidEntries = Array.from(user.entriesByEncounter.values())
    .flat()
    .filter((entry) => !entry.is_obsolete_record);
  const bestDamageEntry = pickBestEntry(allValidEntries);
  const profileEntry = pickProfileEntry(allValidEntries);
  const encounters = Array.from(user.entriesByEncounter.entries())
    .map(([encounterKey, entries]) => {
      entries.sort(compareEntriesByTimeThenScore);
      const bestByJob = new Map();
      let bestEntry = null;
      const validEntries = entries.filter((entry) => !entry.is_obsolete_record);

      for (const entry of validEntries) {
        if (isBetterProfileEntry(entry, bestEntry)) {
          bestEntry = entry;
        }
        if (isBetterEntry(entry, bestByJob.get(entry.job))) {
          bestByJob.set(entry.job, entry);
        }
      }

      return {
        encounter_key: encounterKey,
        encounter_name: bestEntry?.encounter_name || entries[0]?.encounter_name || encounterKey,
        encounter_category: bestEntry?.encounter_category || entries[0]?.encounter_category || null,
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
      best_rdps: bestDamageEntry?.rdps ?? null,
      best_encounter_key: bestDamageEntry?.encounter_key ?? null,
      profile_job: profileEntry?.job ?? null,
      profile_encounter_key: profileEntry?.encounter_key ?? null,
      profile_job_rank: profileEntry ? entryJobRank(profileEntry) : null,
      last_recorded_at_iso: user.last_recorded_at_iso,
    },
    frequent_teammates: frequentTeammates,
    encounters,
  };
}

function buildRecentEntries(entries, sinceMs) {
  return entries
    .filter((entry) => entryRecordedAtMs(entry) >= sinceMs)
    .sort(compareEntriesByTimeThenScore)
    .slice(0, recentActivityLimit)
    .map(buildEntrySummary);
}

function buildPersonalBestActivity(entries, sinceMs) {
  const groupedEntries = new Map();

  for (const entry of entries) {
    const key = `${characterServerKey(entry.character_name, entry.server)}:${entry.encounter_key}:${entry.job}`;
    if (!groupedEntries.has(key)) {
      groupedEntries.set(key, []);
    }
    groupedEntries.get(key).push(entry);
  }

  const improvements = [];
  for (const entryList of groupedEntries.values()) {
    entryList.sort((left, right) => entryRecordedAtMs(left) - entryRecordedAtMs(right));
    let bestEntry = null;

    for (const entry of entryList) {
      if (!isBetterEntry(entry, bestEntry)) {
        continue;
      }

      const previousBest = bestEntry;
      bestEntry = entry;
      if (!previousBest || entryRecordedAtMs(entry) < sinceMs) {
        continue;
      }

      improvements.push({
        ...buildEntrySummary(entry),
        previous_rdps: previousBest.rdps ?? null,
        previous_recorded_at_iso: previousBest.recorded_at_iso || null,
        rdps_gain: roundDamageStat((entry.rdps ?? 0) - (previousBest.rdps ?? 0)),
        clear_time_gain_seconds:
          previousBest.clear_time_seconds === null || entry.clear_time_seconds === null
            ? null
            : Number((previousBest.clear_time_seconds - entry.clear_time_seconds).toFixed(3)),
      });
    }
  }

  return improvements
    .sort((left, right) => {
      const gainDiff = (right.rdps_gain ?? 0) - (left.rdps_gain ?? 0);
      return gainDiff || entryRecordedAtMs(right) - entryRecordedAtMs(left);
    });
}

function buildNewCharacterActivity(entries, sinceMs) {
  const groupedByCharacter = new Map();

  for (const entry of entries) {
    const key = characterServerKey(entry.character_name, entry.server);
    let bucket = groupedByCharacter.get(key);
    if (!bucket) {
      bucket = {
        character_name: entry.character_name,
        server: entry.server,
        first_entry: entry,
        last_entry: entry,
        best_entry: entry,
        encounters: new Set(),
        jobs: new Set(),
        entry_count: 0,
      };
      groupedByCharacter.set(key, bucket);
    }

    bucket.entry_count += 1;
    bucket.encounters.add(entry.encounter_key);
    bucket.jobs.add(entry.job);
    if (entryRecordedAtMs(entry) < entryRecordedAtMs(bucket.first_entry)) {
      bucket.first_entry = entry;
    }
    if (entryRecordedAtMs(entry) > entryRecordedAtMs(bucket.last_entry)) {
      bucket.last_entry = entry;
    }
    if (isBetterEntry(entry, bucket.best_entry)) {
      bucket.best_entry = entry;
    }
  }

  return Array.from(groupedByCharacter.values())
    .filter((bucket) => entryRecordedAtMs(bucket.first_entry) >= sinceMs)
    .map((bucket) => ({
      character_name: bucket.character_name,
      server: bucket.server,
      first_recorded_at_iso: bucket.first_entry.recorded_at_iso,
      last_recorded_at_iso: bucket.last_entry.recorded_at_iso,
      encounter_count: bucket.encounters.size,
      job_count: bucket.jobs.size,
      public_entry_count: bucket.entry_count,
      best_entry: buildEntrySummary(bucket.best_entry),
    }))
    .sort((left, right) => entryRecordedAtMs(right.best_entry) - entryRecordedAtMs(left.best_entry));
}

function buildScopeActivity(entries, personalBests, scopeName) {
  const buckets = new Map();

  for (const entry of entries) {
    const key = entry?.[scopeName];
    if (!key) {
      continue;
    }

    let bucket = buckets.get(key);
    if (!bucket) {
      bucket = {
        [scopeName]: key,
        entry_count: 0,
        characters: new Set(),
        encounters: new Set(),
        jobs: new Set(),
        latest_recorded_at_iso: null,
        personal_best_count: 0,
      };
      buckets.set(key, bucket);
    }

    bucket.entry_count += 1;
    bucket.characters.add(characterServerKey(entry.character_name, entry.server));
    bucket.encounters.add(entry.encounter_key);
    bucket.jobs.add(entry.job);
    if (entryRecordedAtMs(entry) > new Date(bucket.latest_recorded_at_iso || 0).getTime()) {
      bucket.latest_recorded_at_iso = entry.recorded_at_iso;
    }
  }

  for (const best of personalBests) {
    const key = best?.[scopeName];
    if (key && buckets.has(key)) {
      buckets.get(key).personal_best_count += 1;
    }
  }

  return Array.from(buckets.values())
    .map((bucket) => ({
      [scopeName]: bucket[scopeName],
      entry_count: bucket.entry_count,
      character_count: bucket.characters.size,
      encounter_count: bucket.encounters.size,
      job_count: bucket.jobs.size,
      personal_best_count: bucket.personal_best_count,
      latest_recorded_at_iso: bucket.latest_recorded_at_iso,
    }))
    .sort((left, right) => right.entry_count - left.entry_count || compareByLocale(left[scopeName], right[scopeName]));
}

function buildActivityPayload(entries, generatedAtIso, latestRankingUpdatedAt) {
  const latestEntryTime = entries
    .map(entryRecordedAtMs)
    .filter((time) => time > 0)
    .sort((left, right) => right - left)[0] || Date.now();
  const sinceMs = latestEntryTime - activityWindowDays * 24 * 60 * 60 * 1000;
  const recentEntries = entries.filter((entry) => entryRecordedAtMs(entry) >= sinceMs);
  const personalBests = buildPersonalBestActivity(entries, sinceMs);
  const newCharacters = buildNewCharacterActivity(entries, sinceMs);
  const serverActivity = buildScopeActivity(recentEntries, personalBests, "server");
  const encounterActivity = buildScopeActivity(recentEntries, personalBests, "encounter_key").map((item) => {
    const source = recentEntries.find((entry) => entry.encounter_key === item.encounter_key);
    return {
      ...item,
      encounter_name: source?.encounter_name || item.encounter_key,
      encounter_category: source?.encounter_category || null,
    };
  });

  return {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    rankings_updated_at_iso: latestRankingUpdatedAt,
    window_days: activityWindowDays,
    baseline_at_iso: new Date(latestEntryTime).toISOString(),
    summary: {
      recent_entry_count: recentEntries.length,
      personal_best_count: personalBests.length,
      new_character_count: newCharacters.length,
      active_server_count: serverActivity.length,
      active_encounter_count: encounterActivity.length,
      top_server: serverActivity[0] || null,
      top_encounter: encounterActivity[0] || null,
    },
    recent_entries: buildRecentEntries(entries, sinceMs),
    personal_bests: personalBests.slice(0, recentActivityLimit),
    new_characters: newCharacters.slice(0, recentActivityLimit),
    server_activity: serverActivity,
    encounter_activity: encounterActivity,
  };
}

function buildTeamEncounterPayload(encounterKey, records, versionMode = "all") {
  const filteredRecords = filterEntriesByVersionMode(records, versionMode);
  const sortedRecords = filteredRecords.slice().sort(compareTeamRecords);
  const firstRecord = sortedRecords[0] || null;
  const fallbackRecord = records[0] || null;
  return {
    encounter_key: encounterKey,
    encounter_name: firstRecord?.encounter_name || fallbackRecord?.encounter_name || encounterKey,
    encounter_category: firstRecord?.encounter_category || fallbackRecord?.encounter_category || null,
    record_count: sortedRecords.length,
    fastest_clear_seconds: firstRecord?.clear_time_seconds ?? null,
    fastest_record: firstRecord,
    records: sortedRecords.slice(0, teamRecordsPerEncounterLimit).map((record, index) => ({
      ...record,
      rank: index + 1,
    })),
  };
}

function buildTeamRankingsPayload(teamRecordsByEncounter, generatedAtIso, latestRankingUpdatedAt) {
  const encounters = Array.from(teamRecordsByEncounter.entries())
    .map(([encounterKey, records]) => {
      const payload = buildTeamEncounterPayload(encounterKey, records);
      const versionCutoff = records.find((record) => record.version_cutoff_iso)?.version_cutoff_iso;
      if (versionCutoff) {
        payload.version_cutoff = records.find((record) => record.version_cutoff_iso)
          ? {
              obsolete_after_iso: versionCutoff,
            }
          : null;
        payload.version_slices = Object.fromEntries(
          versionRecordModes.map((versionMode) => [
            versionMode,
            {
              ...buildTeamEncounterPayload(encounterKey, records, versionMode),
              version_mode: versionMode,
            },
          ]),
        );
      }
      return payload;
    })
    .sort((left, right) => compareByLocale(left.encounter_category || "", right.encounter_category || "") || compareByLocale(left.encounter_name, right.encounter_name));
  const allRecords = encounters.flatMap((encounter) => encounter.records.map((record) => ({ ...record, encounter_name: encounter.encounter_name })));

  return {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    rankings_updated_at_iso: latestRankingUpdatedAt,
    total_team_record_count: encounters.reduce((sum, encounter) => sum + encounter.record_count, 0),
    encounter_count: encounters.length,
    overall_fastest: allRecords.slice().sort(compareTeamRecords).slice(0, recentActivityLimit),
    encounters,
  };
}

function groupEntriesBy(entries, keyForEntry) {
  const groups = new Map();

  for (const entry of entries || []) {
    const key = keyForEntry(entry);
    if (!key) {
      continue;
    }
    if (!groups.has(key)) {
      groups.set(key, []);
    }
    groups.get(key).push(entry);
  }

  return groups;
}

function pickBestEntry(entries) {
  return (entries || []).reduce((best, entry) => (isBetterEntry(entry, best) ? entry : best), null);
}

function pickFastestEntry(entries) {
  return (entries || [])
    .filter((entry) => toNumber(entry.clear_time_seconds) !== null && toNumber(entry.clear_time_seconds) > 0)
    .sort((left, right) => {
      const clearTimeDiff = (left.clear_time_seconds ?? Infinity) - (right.clear_time_seconds ?? Infinity);
      return clearTimeDiff || (right.rdps ?? 0) - (left.rdps ?? 0) || entryRecordedAtMs(right) - entryRecordedAtMs(left);
    })[0] || null;
}

function buildDamageProfile(entries) {
  const qualifiedEntries = (entries || []).filter(isDamageComparisonEntry);
  return {
    dps: buildDamageMetricStats(qualifiedEntries.map((entry) => entry.dps)),
    rdps: buildDamageMetricStats(qualifiedEntries.map((entry) => entry.rdps ?? entry.dps)),
    adps: buildDamageMetricStats(qualifiedEntries.map((entry) => entry.adps)),
  };
}

function buildJobProfiles(entries, encounterStats) {
  const entriesByJob = groupEntriesBy(entries, (entry) => entry.job);
  const globalJobStats = collectScopeDistribution(entries, (entry) => entry.encounter_key).job_stats;
  const globalDamageStats = buildJobDamageStats(entries);
  const encounterStatsByKey = new Map((encounterStats || []).map((encounter) => [encounter.encounter_key, encounter]));
  const encounterOrder = new Map((encounterStats || []).map((encounter, index) => [encounter.encounter_key, index]));

  return Array.from(entriesByJob.entries())
    .map(([job, jobEntries]) => {
      const role = getJobRole(job);
      const distribution = collectScopeDistribution(jobEntries, (entry) => entry.encounter_key);
      const entriesByServer = groupEntriesBy(jobEntries, (entry) => entry.server);
      const entriesByEncounter = groupEntriesBy(jobEntries, (entry) => entry.encounter_key);
      const rolePeers = globalJobStats
        .filter((item) => item.role === role.role)
        .sort((left, right) => right.clear_count - left.clear_count || compareByLocale(left.job, right.job));
      const damagePeers = globalDamageStats
        .filter((item) => item.role === role.role && toNumber(item.metrics?.rdps?.median) !== null)
        .sort((left, right) => (right.metrics.rdps?.median || 0) - (left.metrics.rdps?.median || 0));
      const damageStats = globalDamageStats.find((item) => item.job === job);

      const servers = Array.from(entriesByServer.entries())
        .map(([server, serverEntries]) => {
          const serverDistribution = collectScopeDistribution(serverEntries, (entry) => entry.encounter_key);
          const bestEntry = pickBestEntry(serverEntries);
          return {
            server,
            clear_count: serverDistribution.character_count,
            entry_count: serverDistribution.entry_count,
            job_share_percent: toPercent(serverDistribution.character_count, distribution.character_count),
            best_entry: bestEntry ? buildEntrySummary(bestEntry) : null,
          };
        })
        .sort((left, right) => right.clear_count - left.clear_count || compareByLocale(left.server, right.server));

      const encounters = Array.from(entriesByEncounter.entries())
        .map(([encounterKey, encounterEntries]) => {
          const encounterDistribution = collectScopeDistribution(encounterEntries, encounterKey);
          const encounter = encounterStatsByKey.get(encounterKey);
          const bestEntry = pickBestEntry(encounterEntries);
          const fastestEntry = pickFastestEntry(encounterEntries);
          return {
            encounter_key: encounterKey,
            encounter_name: encounterEntries[0]?.encounter_name || encounter?.encounter_name || encounterKey,
            encounter_category: encounterEntries[0]?.encounter_category || encounter?.encounter_category || null,
            clear_count: encounterDistribution.character_count,
            entry_count: encounterDistribution.entry_count,
            encounter_share_percent: toPercent(encounterDistribution.character_count, encounter?.character_count || 0),
            job_share_percent: toPercent(encounterDistribution.character_count, distribution.character_count),
            damage_profile: buildDamageProfile(encounterEntries),
            best_entry: bestEntry ? buildEntrySummary(bestEntry) : null,
            fastest_entry: fastestEntry ? buildEntrySummary(fastestEntry) : null,
          };
        })
        .sort((left, right) => {
          const orderDiff = (encounterOrder.get(left.encounter_key) ?? Number.MAX_SAFE_INTEGER) -
            (encounterOrder.get(right.encounter_key) ?? Number.MAX_SAFE_INTEGER);
          return orderDiff || compareByLocale(left.encounter_name, right.encounter_name);
        });
      const bestEntry = pickBestEntry(jobEntries);
      const fastestEntry = pickFastestEntry(jobEntries);

      return {
        job,
        ...role,
        unique_player_count: new Set(jobEntries.map((entry) => characterServerKey(entry.character_name, entry.server))).size,
        encounter_clear_count: distribution.character_count,
        role_record_count: distribution.role_record_count,
        job_record_count: distribution.job_record_count,
        entry_count: distribution.entry_count,
        encounter_count: encounters.length,
        role_peer_rank: indexToRank(rolePeers.findIndex((item) => item.job === job)),
        role_peer_count: rolePeers.length,
        rdps_peer_rank: indexToRank(damagePeers.findIndex((item) => item.job === job)),
        rdps_peer_count: damagePeers.length,
        damage_profile: buildDamageProfile(jobEntries),
        savage_damage_profile: buildDamageProfile(jobEntries.filter((entry) => savageDamageComparisonEncounterKeySet.has(entry.encounter_key))),
        damage_stats: damageStats || null,
        best_entry: bestEntry ? buildEntrySummary(bestEntry) : null,
        fastest_entry: fastestEntry ? buildEntrySummary(fastestEntry) : null,
        servers,
        encounters,
      };
    })
    .sort((left, right) => {
      if (left.encounter_clear_count !== right.encounter_clear_count) {
        return right.encounter_clear_count - left.encounter_clear_count;
      }
      return compareByLocale(left.job, right.job);
    });
}

function buildServerEncounterCompareRows(serverEntries, encounterStatsByKey) {
  return Array.from(groupEntriesBy(serverEntries, (entry) => entry.encounter_key).entries())
    .map(([encounterKey, encounterEntries]) => {
      const distribution = collectScopeDistribution(encounterEntries, encounterKey);
      const encounter = encounterStatsByKey.get(encounterKey);
      const bestEntry = pickBestEntry(encounterEntries);
      const fastestEntry = pickFastestEntry(encounterEntries);

      return {
        encounter_key: encounterKey,
        encounter_name: encounterEntries[0]?.encounter_name || encounter?.encounter_name || encounterKey,
        encounter_category: encounterEntries[0]?.encounter_category || encounter?.encounter_category || null,
        character_count: distribution.character_count,
        job_record_count: distribution.job_record_count,
        entry_count: distribution.entry_count,
        clear_share_percent: toPercent(distribution.character_count, encounter?.character_count || 0),
        damage_profile: buildDamageProfile(encounterEntries),
        best_entry: bestEntry ? buildEntrySummary(bestEntry) : null,
        fastest_entry: fastestEntry ? buildEntrySummary(fastestEntry) : null,
      };
    })
    .sort((left, right) => {
      const leftOrder = Array.from(encounterStatsByKey.keys()).indexOf(left.encounter_key);
      const rightOrder = Array.from(encounterStatsByKey.keys()).indexOf(right.encounter_key);
      return leftOrder - rightOrder || compareByLocale(left.encounter_name, right.encounter_name);
    });
}

function buildServerComparePayload(entries, encounterStats, generatedAtIso, latestRankingUpdatedAt) {
  const encounterStatsByKey = new Map((encounterStats || []).map((encounter) => [encounter.encounter_key, encounter]));
  const servers = Array.from(groupEntriesBy(entries, (entry) => entry.server).entries())
    .map(([server, serverEntries]) => {
      const distribution = collectScopeDistribution(serverEntries, (entry) => entry.encounter_key);
      const uniquePlayerCount = new Set(serverEntries.map((entry) => characterServerKey(entry.character_name, entry.server))).size;
      const bestEntry = pickBestEntry(serverEntries);
      const fastestEntry = pickFastestEntry(serverEntries);
      const rdpsStats = buildDamageMetricStats(
        serverEntries.filter(isDamageComparisonEntry).map((entry) => entry.rdps ?? entry.dps),
      );

      return {
        server,
        unique_player_count: uniquePlayerCount,
        encounter_clear_count: distribution.character_count,
        role_record_count: distribution.role_record_count,
        job_record_count: distribution.job_record_count,
        entry_count: distribution.entry_count,
        encounter_count: new Set(serverEntries.map((entry) => entry.encounter_key).filter(Boolean)).size,
        role_stats: distribution.role_stats,
        job_stats: distribution.job_stats,
        damage_stats: buildJobDamageStats(serverEntries),
        rdps_stats: rdpsStats,
        best_entry: bestEntry ? buildEntrySummary(bestEntry) : null,
        fastest_entry: fastestEntry ? buildEntrySummary(fastestEntry) : null,
        encounters: buildServerEncounterCompareRows(serverEntries, encounterStatsByKey),
      };
    })
    .sort((left, right) => {
      if (left.encounter_clear_count !== right.encounter_clear_count) {
        return right.encounter_clear_count - left.encounter_clear_count;
      }
      return compareByLocale(left.server, right.server);
    });

  const topRdpsServer = servers
    .filter((server) => server.rdps_stats?.median !== null)
    .sort((left, right) => (right.rdps_stats?.median || 0) - (left.rdps_stats?.median || 0))[0] || null;
  const fastestServer = servers
    .filter((server) => server.fastest_entry?.clear_time_seconds)
    .sort((left, right) => (left.fastest_entry?.clear_time_seconds || Infinity) - (right.fastest_entry?.clear_time_seconds || Infinity))[0] || null;

  return {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    rankings_updated_at_iso: latestRankingUpdatedAt,
    summary: {
      server_count: servers.length,
      top_clear_server: servers[0] || null,
      top_rdps_server: topRdpsServer,
      fastest_server: fastestServer,
    },
    servers,
  };
}

function normalizeEncounterShare(encounterStatsItem, totalCharacterCount) {
  const normalized = {
    ...encounterStatsItem,
    clear_share_percent: toPercent(encounterStatsItem.character_count, totalCharacterCount),
  };

  if (encounterStatsItem.version_slices && typeof encounterStatsItem.version_slices === "object") {
    normalized.version_slices = Object.fromEntries(
      Object.entries(encounterStatsItem.version_slices).map(([versionMode, versionStats]) => [
        versionMode,
        {
          ...versionStats,
          clear_share_percent: toPercent(versionStats.character_count, totalCharacterCount),
        },
      ]),
    );
  }

  return normalized;
}

async function buildDataset({
  outputDataDir,
  includeHiddenReports = false,
  label = "公開",
}) {
  const outputDir = path.join(outputDataDir, "users");
  const globalStatsPath = path.join(outputDataDir, "global_stats.json");
  const activityPath = path.join(outputDataDir, "activity.json");
  const teamRankingsPath = path.join(outputDataDir, "team_rankings.json");
  const serverComparePath = path.join(outputDataDir, "server_compare.json");

  assertInside(basePublicDataDir, outputDataDir);
  assertInside(basePublicDataDir, outputDir);
  assertInside(basePublicDataDir, globalStatsPath);
  assertInside(basePublicDataDir, activityPath);
  assertInside(basePublicDataDir, teamRankingsPath);
  assertInside(basePublicDataDir, serverComparePath);

  const encounters = await loadEncounters();
  const usersByName = new Map();
  const updatedAtIsoByEncounter = new Map();
  const overallCharacterKeys = new Set();
  const encounterStats = [];
  const allEntries = [];
  const teamRecordsByEncounter = new Map();

  for (const encounter of encounters) {
    const ranking = await loadRankingForEncounter(encounter);
    if (!ranking) {
      continue;
    }

    if (ranking.updated_at_iso) {
      updatedAtIsoByEncounter.set(encounter.key, ranking.updated_at_iso);
    }

    const entries = ranking.reports
      ? collectEntriesFromReports({ ranking, encounter, includeHiddenReports })
      : collectEntriesFromRankingEntries({ ranking, encounter, includeHiddenReports });
    assignValidVersionJobRanks(entries);
    const teamRecords = ranking.reports
      ? collectTeamRecordsFromReports({ ranking, encounter, includeHiddenReports })
      : [];

    encounterStats.push(collectEncounterStats(encounter, entries, ranking.updated_at_iso));
    allEntries.push(...entries);
    if (teamRecords.length > 0) {
      teamRecordsByEncounter.set(encounter.key, teamRecords);
    }

    for (const entry of entries) {
      overallCharacterKeys.add(characterServerKey(entry.character_name, entry.server));
      addEntry(usersByName, entry);
    }

    if (!includeHiddenReports) {
      for (const stub of collectHiddenUserStubs(ranking)) {
        addHiddenUserStub(usersByName, stub);
      }
    }
  }

  attachRdpsPerformance(allEntries);

  // public/data/users 是完整衍生產物，可以整包重建；append-only 保護的是 data/state 與 data/rankings。
  // 使用者檔名以角色名稱正規化，index.json 的 file_path 才是前端實際讀取入口。
  await removeGeneratedDirectory(outputDir);
  await mkdir(outputDir, { recursive: true });

  const latestRankingUpdatedAt = Array.from(updatedAtIsoByEncounter.values()).sort().at(-1) || null;
  const generatedAtIso = resolveGeneratedAtIso(latestRankingUpdatedAt);
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
      profile_job: payload.summary.profile_job,
      profile_job_rank: payload.summary.profile_job_rank,
      last_recorded_at_iso: payload.summary.last_recorded_at_iso,
    });
  }

  const globalDistribution = collectScopeDistribution(allEntries, (entry) => entry.encounter_key);
  const savageDamageComparisonEntries = allEntries.filter((entry) => savageDamageComparisonEncounterKeySet.has(entry.encounter_key));
  const totalEncounterClearCount = globalDistribution.character_count;
  const totalJobClearCount = globalDistribution.job_record_count;
  const normalizedEncounterStats = encounterStats.map((encounter) =>
    normalizeEncounterShare(encounter, overallCharacterKeys.size),
  );

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
    job_profiles: buildJobProfiles(allEntries, normalizedEncounterStats),
    encounters: normalizedEncounterStats,
  });

  await writeJson(activityPath, buildActivityPayload(allEntries, generatedAtIso, latestRankingUpdatedAt));
  await writeJson(teamRankingsPath, buildTeamRankingsPayload(teamRecordsByEncounter, generatedAtIso, latestRankingUpdatedAt));
  await writeJson(serverComparePath, buildServerComparePayload(allEntries, normalizedEncounterStats, generatedAtIso, latestRankingUpdatedAt));
  await waitForUserOutputReady(outputDir, indexUsers.length, label);

  console.log(`Built ${label} ${indexUsers.length} user data files in ${path.relative(rootDir, outputDir)}.`);
  console.log(`Built ${label} global stats in ${path.relative(rootDir, globalStatsPath)}.`);
  console.log(`Built ${label} activity feed in ${path.relative(rootDir, activityPath)}.`);
  console.log(`Built ${label} team rankings in ${path.relative(rootDir, teamRankingsPath)}.`);
  console.log(`Built ${label} server compare data in ${path.relative(rootDir, serverComparePath)}.`);
}

async function main() {
  await buildDataset({
    outputDataDir: basePublicDataDir,
    includeHiddenReports: false,
    label: "預設公開",
  });

  // public/data/all 是完整資料鏡像，讓額外檢視流程能和一般公開資料使用相同 JSON 結構。
  await buildDataset({
    outputDataDir: path.join(basePublicDataDir, "all"),
    includeHiddenReports: true,
    label: "完整鏡像",
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
