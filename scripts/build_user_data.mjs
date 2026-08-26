import { createHash } from "node:crypto";
import { existsSync } from "node:fs";
import { mkdir, open, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import path from "node:path";
import { setTimeout as sleep } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { 建立個人成績徽章, 取得個人成績成就目錄 } from "../src/utils/userProfileBadges.js";
import { resolvePhysicalFightHash } from "./fight_identity.mjs";

// 本檔是資料管線的 Data Building Layer。
// 它讀取 data/rankings 的可追溯原始資料與 ranking_entries，聚合成前端可直接讀取的靜態 JSON。
// 請勿在 Vue 元件中重做這裡的排序、去重、分位數或隊友統計，否則各頁會出現不一致的結果。
const defaultRootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const rootDir = path.resolve(process.env.FFXIV_TC_ROOT_DIR || defaultRootDir);
const sourceRankingsDir = path.join(rootDir, "data", "rankings");
const basePublicDataDir = path.join(rootDir, "public", "data");
const publicRankingsDir = path.join(basePublicDataDir, "rankings");
const publicEncountersPath = path.join(basePublicDataDir, "encounters.json");
const publicAnnouncementsPath = path.join(basePublicDataDir, "announcements.json");
const configEncountersPath = path.join(rootDir, "config", "encounters.json");
const configGameVersionsPath = path.join(rootDir, "config", "game_versions.json");
const userEntryDetailsDirName = "user-entry-details";
// 目前箱型圖只比較現行零式系列；其他副本仍會進入全服統計與個人成績單。
// minimumDamageActivePercent 用來排除明顯中途死亡或缺乏輸出時間的樣本，避免分位數被極端異常值拉歪。
const savageDamageComparisonEncounterKeys = ["savage_m1s", "savage_m2s", "savage_m3s", "savage_m4s"];
const savageDamageComparisonEncounterKeySet = new Set(savageDamageComparisonEncounterKeys);
const minimumDamageActivePercent = 50;
const activityWindowDays = 7;
const activityLogDefaultWindowDays = 30;
const activityLogCategoryOrder = ["零式", "極", "幻", "滅", "絕"];
const recentActivityLimit = 40;
const teamRecordsPerEncounterLimit = 50;
const versionRecordModes = ["all", "valid", "obsolete"];
const jsonWriteRetryCount = 10;
const jsonWriteRetryDelayMs = 500;
const jsonWriteChunkBytes = 1024 * 1024;
const transientWriteErrorCodes = new Set(["EBUSY", "EPERM", "UNKNOWN"]);
const transientRemoveErrorCodes = new Set(["EBUSY", "EMFILE", "ENFILE", "ENOTEMPTY", "EPERM", "UNKNOWN"]);
const publicGcdCoverageFields = new Set([
  "percent",
  "covered_time_ms",
  "denominator_ms",
  "downtime_ms",
  "gcd_cast_count",
  "calculation_version",
  "source",
  "xivanalysis_url",
  "speed_stat_source",
  "estimated_skill_speed",
  "estimated_spell_speed",
  "coverage_downtime_ms",
  "denominator_downtime_ms",
  "estimated_speed_below_minimum",
  "fallback_selection",
  "previous_fallback_selection",
  "downtime_selection",
  "raw_events_percent",
  "raw_events_denominator_ms",
  "casts_graph_percent",
  "casts_graph_denominator_ms",
  "raw_targetability_percent",
  "raw_targetability_denominator_ms",
  "raw_next_gcd_capped_percent",
  "raw_next_gcd_capped_denominator_ms",
]);

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
const healerJobs = new Set(jobRoleGroups.find((group) => group.role === "role:healer")?.jobs || []);
const tankJobs = new Set(jobRoleGroups.find((group) => group.role === "role:tank")?.jobs || []);

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

function isTransientTempWriteError(error) {
  return error?.code === "ENOENT" || isTransientWriteError(error);
}

function formatWritePath(filePath) {
  const relativePath = path.relative(rootDir, filePath);
  return relativePath && !relativePath.startsWith("..") && !path.isAbsolute(relativePath)
    ? relativePath
    : filePath;
}

async function writeTempJsonFile(tempPath, payload) {
  for (let attempt = 1; attempt <= jsonWriteRetryCount; attempt += 1) {
    try {
      await mkdir(path.dirname(tempPath), { recursive: true });
      await writeFile(tempPath, payload, "utf8");
      return;
    } catch (error) {
      if (!isTransientTempWriteError(error)) {
        throw error;
      }

      if (attempt === jsonWriteRetryCount) {
        throw new Error(
          `無法建立 JSON 暫存檔：${formatWritePath(tempPath)}，請確認輸出目錄未被編輯器、同步軟體或防護軟體鎖定。`,
          { cause: error },
        );
      }

      const waitMs = jsonWriteRetryDelayMs * attempt;
      console.warn(
        `JSON 暫存檔暫時無法建立，${(waitMs / 1000).toFixed(1)} 秒後重試：${formatWritePath(tempPath)}`,
      );
      await sleep(waitMs);
    }
  }
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
    await writeTempJsonFile(tempPath, payload);

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

async function syncAnnouncementMirror(outputDataDir) {
  if (path.resolve(outputDataDir) === path.resolve(basePublicDataDir)) {
    return;
  }

  const announcements = await readJson(publicAnnouncementsPath, null);
  if (!announcements) {
    return;
  }

  // 公告是 commit 維護的營運靜態資料，不屬於排行榜聚合產物；
  // 但額外檢視流程可能把 /data/... 改寫到 /data/all/...，
  // 因此完整鏡像仍要跟一般公開公告保持同步。
  await writeJson(path.join(outputDataDir, "announcements.json"), announcements);
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

function compactHealingStats(value) {
  if (!value || typeof value !== "object") {
    return null;
  }

  return {
    hps: toNumber(value.hps),
    pure_healing: toNumber(value.pure_healing),
    protection: toNumber(value.protection),
    overheal_percent: toNumber(value.overheal_percent),
  };
}

function compactTankStats(value) {
  if (!value || typeof value !== "object") {
    return null;
  }

  return {
    damage_taken: toNumber(value.damage_taken),
    self_healing: toNumber(value.self_healing),
    personal_protection: toNumber(value.personal_protection),
    team_protection: toNumber(value.team_protection),
    // 個人成績與排行榜必須沿用同一口徑：這是「有實際傷害落在狀態時窗內」的
    // 有效 activation 比例，不是 buff 持續時間占比，也不是單招實際減免量。
    mitigation_coverage_percent: toNumber(value.mitigation_coverage?.effective_activation_percent),
  };
}

function compactCoHealer(value) {
  if (!value || typeof value !== "object") {
    return null;
  }

  const characterName = String(value.character_name || value.name || "").trim();
  const server = String(value.server || "").trim();
  const job = String(value.job || "").trim();
  return characterName && server && healerJobs.has(job)
    ? { character_name: characterName, server, job }
    : null;
}

function sanitizeGcdCoverageForPublic(coverage) {
  if (coverage === undefined) {
    return undefined;
  }
  if (coverage === null) {
    return null;
  }
  if (!coverage || typeof coverage !== "object" || Array.isArray(coverage)) {
    return coverage;
  }

  // data/rankings 會保留 raw-events selector 的診斷值，方便後續追 GCD 與 xivanalysis 差異。
  // 個人成績單、團隊榜與公開摘要只需要公開契約欄位，避免診斷欄位讓前端 payload 和 schema 漂移。
  return Object.fromEntries(Object.entries(coverage).filter(([key]) => publicGcdCoverageFields.has(key)));
}

function isHiddenReport(report) {
  return Boolean(report?.report_hidden || report?.hidden_report);
}

function isHiddenEntry(entry) {
  return Boolean(entry?.report_hidden || entry?.hidden_report);
}

const fightIntegrityCutoffMs = Date.parse("2026-07-28T18:00:00+08:00");
// 必須與 scripts/fight_integrity.py 同步。v13 只強制幻朱雀補齊全職業 ability 7／8
// 普攻證據；其他副本已確認正常的 v8～v12 fight 繼續公開，避免全域版號升級時把個人成績、
// 隊伍榜與統計整批撤下。副本專用重驗候選由 Python 資料管線負責，建置層只消費
// 已寫入來源分片的最終狀態，不能自行推測哪些舊版 fight 需要重判。
const currentFightIntegrityCalculationVersion = 13;
const legacyPublicCompatibleFightIntegrityVersions = new Set([8, 9, 10, 11, 12]);
const publicFightIntegrityStatuses = new Set(["valid", "not_applicable"]);
const confirmedFightIntegrityAnomalyStatuses = new Set(["excluded", "suspected"]);

function isPublicCompatibleIntegrityResult(integrity) {
  const version = Number(integrity?.calculation_version);
  const versionIsSupported = version === currentFightIntegrityCalculationVersion
    || legacyPublicCompatibleFightIntegrityVersions.has(version);
  return versionIsSupported
    && publicFightIntegrityStatuses.has(String(integrity?.status || ""))
    && !Boolean(integrity?.hidden_from_public);
}

function isIntegrityHiddenFight(fight, report = {}) {
  // 普攻異常檢核是 fight 層而不是 report 層：保留 report 原始資料以供日後追溯，
  // 但無論是否建置 hidden report delta，都不能讓異常或尚未驗證的 pull 回流到公開衍生資料。
  const integrity = fight?.data_integrity;
  if (integrity && typeof integrity === "object") {
    return !isPublicCompatibleIntegrityResult(integrity);
  }
  // 回補尚未完成或 API 暫時失敗時，切點後沒有完整性結果的 fight 必須 fail-closed。
  // 來源層仍保存 report/fight，待離線回補後只有明確 valid 的資料才會公開。
  const recordedAt = fightRecordedAtMs(fight, report);
  return Number.isFinite(recordedAt) && recordedAt >= fightIntegrityCutoffMs;
}

function isConfirmedFightIntegrityAnomaly(fight) {
  const integrity = fight?.data_integrity;
  return Boolean(integrity?.hidden_from_public)
    && confirmedFightIntegrityAnomalyStatuses.has(String(integrity?.status || ""));
}

function buildFightIdentityEncounter(ranking, encounter) {
  // public/data/encounters.json 為了前端精簡化，舊快照可能沒有 encounter_id／difficulty；
  // reports 所在的 ranking 主檔仍保留這些 FFLogs 身分欄位。建置 v2 指紋時必須合併
  // 兩邊契約，否則歷史資料會因公開清單缺欄而退回不穩定的 v1 hash。
  return {
    ...(ranking?.encounter || {}),
    ...(encounter || {}),
    encounter_id: encounter?.encounter_id ?? ranking?.encounter?.encounter_id,
    difficulty: encounter?.difficulty ?? ranking?.encounter?.difficulty,
  };
}

function collectConfirmedAnomalousFightHashes(ranking, encounter) {
  const fightHashes = new Set();
  for (const report of Object.values(ranking?.reports || {})) {
    for (const fight of report?.fights || []) {
      // 同一場戰鬥可能被多位隊員分別上傳。只要任一來源已取得明確異常證據，
      // 就必須排除相同 v2 fight_hash 的所有變體。歷史分片仍是 v1 時也在記憶體
      // 依穩定欄位重算，避免同一場因通關或 damage table 的 1 ms／小數漂移而回流。
      const fightHash = resolvePhysicalFightHash(fight, encounter);
      if (fightHash && isConfirmedFightIntegrityAnomaly(fight)) {
        fightHashes.add(fightHash);
      }
    }
  }
  return fightHashes;
}

function isIntegrityHiddenFightOrDuplicate(fight, report, encounter, confirmedAnomalousFightHashes) {
  const fightHash = resolvePhysicalFightHash(fight, encounter);
  return isIntegrityHiddenFight(fight, report)
    || Boolean(fightHash && confirmedAnomalousFightHashes.has(fightHash));
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

function playersMatch(left, right) {
  const leftSourceId = toFflogsSourceId(left?.fflogs_source_id ?? left?.fflogs_id ?? left?.source_id);
  const rightSourceId = toFflogsSourceId(right?.fflogs_source_id ?? right?.fflogs_id ?? right?.source_id);
  if (leftSourceId !== null && rightSourceId !== null) {
    return leftSourceId === rightSourceId;
  }

  return (left?.name || left?.character_name) === (right?.name || right?.character_name)
    && left?.server === right?.server
    && left?.job === right?.job;
}

function buildCoHealer(player, fightPlayers) {
  if (!healerJobs.has(player?.job)) {
    return null;
  }

  const healers = (fightPlayers || []).filter((candidate) => healerJobs.has(candidate?.job));
  // 標準八人副本能以雙補唯一互相配對；聯盟副本缺少小隊編號，同場超過兩名
  // 治療職業時不得依來源陣列順序猜測「另一補」。
  if (healers.length !== 2) {
    return null;
  }

  const playerIndex = healers.findIndex((candidate) => playersMatch(candidate, player));
  if (playerIndex < 0) {
    return null;
  }

  const companion = healers[playerIndex === 0 ? 1 : 0];
  const characterName = companion?.name || companion?.character_name || "";
  if (!characterName || !companion?.server || !companion?.job) {
    return null;
  }

  return compactCoHealer({
    character_name: characterName,
    server: companion.server,
    job: companion.job,
  });
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

function fightRecordedAtMs(fight, report) {
  const recordedAt = toNumber(fight?.recorded_at);
  if (recordedAt !== null && recordedAt > 0) {
    return recordedAt;
  }

  const recordedAtIso = new Date(fight?.recorded_at_iso || report?.report_start_time_iso || 0).getTime();
  if (Number.isFinite(recordedAtIso) && recordedAtIso > 0) {
    return recordedAtIso;
  }

  const reportStartTime = toNumber(report?.report_start_time);
  return reportStartTime !== null && reportStartTime > 0 ? reportStartTime : 0;
}

function taiwanDateKeyFromMs(timeMs) {
  if (!Number.isFinite(timeMs) || timeMs <= 0) {
    return null;
  }

  // 近期動態面向繁中服使用者，日誌曲線以台灣日期切日；
  // 台灣沒有日光節約時間，固定 +08:00 可避免 Intl 在 GitHub runner 上輸出格式差異。
  return new Date(timeMs + 8 * 60 * 60 * 1000).toISOString().slice(0, 10);
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

function normalizeGameVersions(config) {
  const versions = Array.isArray(config?.versions) ? config.versions : null;
  if (!versions || versions.length === 0) {
    throw new Error("config/game_versions.json 必須提供至少一個繁中服版本區間。");
  }

  const normalized = versions.map((version, index) => {
    const patch = String(version?.patch || "").trim();
    const label = String(version?.label || patch).trim();
    const startsAtIso = version?.starts_at_iso ?? null;
    const startsAtMs = startsAtIso === null ? null : new Date(startsAtIso).getTime();

    if (!patch || !label) {
      throw new Error(`config/game_versions.json 的 versions[${index}] 缺少 patch 或 label。`);
    }
    if (startsAtIso !== null && !Number.isFinite(startsAtMs)) {
      throw new Error(`config/game_versions.json 的 ${patch} starts_at_iso 不是有效時間。`);
    }

    return {
      patch,
      label,
      starts_at_iso: startsAtIso === null ? null : new Date(startsAtMs).toISOString(),
      starts_at_ms: startsAtMs,
    };
  });

  if (normalized[0].starts_at_ms !== null) {
    throw new Error("config/game_versions.json 的第一個版本必須以 starts_at_iso: null 表示最早的已收錄版本。");
  }

  const patches = new Set();
  let previousStartsAtMs = 0;
  for (const version of normalized) {
    if (patches.has(version.patch)) {
      throw new Error(`config/game_versions.json 的 patch 不可重複：${version.patch}`);
    }
    patches.add(version.patch);

    if (version.starts_at_ms !== null) {
      if (version.starts_at_ms <= previousStartsAtMs) {
        throw new Error("config/game_versions.json 的版本開放時間必須依序遞增。");
      }
      previousStartsAtMs = version.starts_at_ms;
    }
  }

  return normalized;
}

async function loadGameVersions() {
  // 此設定描述「繁中服的競技資料區間」，不是 FFLogs 的 valid/obsolete 狀態。
  // 兩者必須分開：同一筆舊副本的過版紀錄仍可能屬於 7.15，供玩家辨識當時的
  // 技能與裝備環境；valid/obsolete 則只回答該副本在該時間是否仍是現行難度。
  return normalizeGameVersions(await readJson(configGameVersionsPath, null));
}

function attachGameVersion(entry, gameVersions) {
  const recordedAtMs = entryRecordedAtMs(entry);
  if (!Number.isFinite(recordedAtMs) || recordedAtMs <= 0) {
    entry.game_version = null;
    return entry;
  }

  let matchedVersion = gameVersions[0];
  for (const version of gameVersions) {
    if (version.starts_at_ms === null || version.starts_at_ms <= recordedAtMs) {
      matchedVersion = version;
      continue;
    }
    break;
  }

  entry.game_version = matchedVersion.label;
  for (const variant of entry._reportVariants || []) {
    variant.game_version = matchedVersion.label;
  }
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
  // 這份摘要會被近期動態、職業分析與伺服器對比等全站共用資料重複引用。
  // 坦補詳細統計只屬於排行榜與個人成績契約；若在此沿用完整成績欄位，
  // 不只會讓高頻共用 payload 膨脹，也會讓嚴格的 entrySummary 契約隨資料職業而漂移。
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
    gcd_coverage: sanitizeGcdCoverageForPublic(entry.gcd_coverage),
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

function buildReportVariant(entry) {
  const healingStats = compactHealingStats(entry.healing_stats);
  const tankStats = compactTankStats(entry.tank_stats);
  const coHealer = compactCoHealer(entry.co_healer);
  const variant = {
    report_code: entry.report_code || null,
    report_url: entry.report_url || null,
    report_title: entry.report_title || null,
    fight_id: entry.fight_id ?? null,
    recorded_at: toNumber(entry.recorded_at),
    recorded_at_iso: entry.recorded_at_iso || null,
    dps: toNumber(entry.dps),
    rdps: toNumber(entry.rdps ?? entry.dps),
    adps: toNumber(entry.adps),
    ndps: toNumber(entry.ndps),
    total_damage: toNumber(entry.total_damage),
    active_time_ms: toNumber(entry.active_time_ms),
    active_percent: toNumber(entry.active_percent),
    ...(healingStats ? { healing_stats: healingStats } : {}),
    ...(tankStats ? { tank_stats: tankStats } : {}),
    ...(coHealer ? { co_healer: coHealer } : {}),
    clear_time_ms: toNumber(entry.clear_time_ms),
    clear_time_seconds: toNumber(entry.clear_time_seconds),
    damage_downtime_ms: toNumber(entry.damage_downtime_ms),
    damage_downtime_seconds: toNumber(entry.damage_downtime_seconds),
    damage_time_ms: toNumber(entry.damage_time_ms),
    damage_time_seconds: toNumber(entry.damage_time_seconds),
    game_version: entry.game_version || null,
    ...hiddenReportFields(entry),
  };

  if (entry.fflogs_source_id !== null && entry.fflogs_source_id !== undefined) {
    variant.fflogs_source_id = entry.fflogs_source_id;
  }
  if (Object.hasOwn(entry, "gcd_coverage")) {
    variant.gcd_coverage = sanitizeGcdCoverageForPublic(entry.gcd_coverage);
  }
  if (Object.hasOwn(entry, "gcd_coverage_status")) {
    variant.gcd_coverage_status = entry.gcd_coverage_status;
  }

  variant.key = reportVariantKey(variant);
  return variant;
}

function reportVariantKey(variant) {
  if (variant?.key) {
    return variant.key;
  }
  return createId({
    report_code: variant?.report_code || null,
    report_url: variant?.report_url || null,
    fight_id: variant?.fight_id ?? null,
    fflogs_source_id: variant?.fflogs_source_id ?? null,
    recorded_at_iso: variant?.recorded_at_iso || null,
  });
}

function mergeReportVariants(...variantGroups) {
  const variantsByKey = new Map();

  for (const variantGroup of variantGroups) {
    for (const variant of variantGroup || []) {
      if (!variant || (!variant.report_code && !variant.report_url)) {
        continue;
      }
      const key = reportVariantKey(variant);
      variantsByKey.set(key, {
        ...variant,
        key,
      });
    }
  }

  return Array.from(variantsByKey.values());
}

function getEntryReportVariants(entry) {
  return Array.isArray(entry?._reportVariants) && entry._reportVariants.length > 0
    ? entry._reportVariants
    : [buildReportVariant(entry)];
}

function orderReportVariantsForEntry(variants, entry) {
  const primaryKey = reportVariantKey(buildReportVariant(entry));
  return variants.slice().sort((left, right) => {
    const leftIsPrimary = reportVariantKey(left) === primaryKey;
    const rightIsPrimary = reportVariantKey(right) === primaryKey;
    if (leftIsPrimary !== rightIsPrimary) {
      return leftIsPrimary ? -1 : 1;
    }

    const leftTime = new Date(left.recorded_at_iso || 0).getTime();
    const rightTime = new Date(right.recorded_at_iso || 0).getTime();
    const normalizedLeftTime = Number.isNaN(leftTime) ? 0 : leftTime;
    const normalizedRightTime = Number.isNaN(rightTime) ? 0 : rightTime;
    return (
      normalizedRightTime - normalizedLeftTime ||
      compareByLocale(left.report_code || left.report_url || "", right.report_code || right.report_url || "")
    );
  });
}

function mergeDuplicateEntry(existing, candidate) {
  const mergedVariants = mergeReportVariants(getEntryReportVariants(existing), getEntryReportVariants(candidate));
  const representative = isBetterEntry(candidate, existing) ? candidate : existing;

  if (representative === candidate) {
    Object.assign(existing, candidate);
  }

  // 同一場 fight 可能由多名隊員各自上傳；個人成績列只保留一筆代表成績，
  // 但每個 report code 都必須留在 report_variants，讓彈窗可以切換來源並追溯外部工具連結。
  existing._reportVariants = orderReportVariantsForEntry(mergedVariants, existing);
  existing.duplicate_count = existing._reportVariants.length;
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

function buildAchievementStatistics(users, baselineAtMs) {
  const catalog = 取得個人成績成就目錄();
  const holderCountById = new Map(catalog.map((achievement) => [achievement.id, 0]));
  const totalUsers = users.length;

  for (const user of users) {
    const publicEntries = Array.from(user.entriesByEncounter.values()).flat();
    const earnedAchievementIds = new Set(
      建立個人成績徽章({
        角色名稱: user.character_name,
        公開成績: publicEntries,
        公開同場玩家數: user.teammates.size,
        最後紀錄時間: user.last_recorded_at_iso,
        近期動態基準時間: baselineAtMs,
        取得職能代碼: (job) => getJobRole(job).role,
      })
        .filter((achievement) => achievement.是成就 !== false && holderCountById.has(achievement.id))
        .map((achievement) => achievement.id),
    );

    // 一位玩家對同一成就最多計一次。零式首週／次週／一般雖由產品規則保證
    // 互斥，這層去重仍可防止未來新增條件時把同一角色重複灌入全站人數。
    for (const achievementId of earnedAchievementIds) {
      holderCountById.set(achievementId, (holderCountById.get(achievementId) || 0) + 1);
    }
  }

  return catalog.map((achievement) => {
    const holderCount = holderCountById.get(achievement.id) || 0;
    return {
      id: achievement.id,
      name: achievement.名稱,
      description: achievement.說明,
      category: achievement.分類,
      holder_count: holderCount,
      holder_percentage: toPercent(holderCount, totalUsers),
    };
  });
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

function makePublicEntry({ encounter, report, reportCode, fight, fightHash, player, fightPlayers }) {
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
  const healingStats = healerJobs.has(job) ? compactHealingStats(player.healing_stats) : null;
  const tankStats = tankJobs.has(job) ? compactTankStats(player.tank_stats) : null;
  const coHealer = buildCoHealer(player, fightPlayers);
  const signature = fightHash
    ? {
        encounter_key: encounter.key,
        fight_hash: fightHash,
        character_name: characterName,
        server,
        job,
      }
    : {
        // 極舊資料若缺少副本／時間／完整隊伍，寧可保留來源層級的獨立 ID，
        // 也不能再用近似輸出值跨 report 猜測同場。
        encounter_key: encounter.key,
        report_code: reportCode,
        fight_id: fight.fight_id,
        character_name: characterName,
        server,
        job,
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
    ...(healingStats ? { healing_stats: healingStats } : {}),
    ...(tankStats ? { tank_stats: tankStats } : {}),
    ...(coHealer ? { co_healer: coHealer } : {}),
    ...(Object.hasOwn(player, "gcd_coverage") ? { gcd_coverage: sanitizeGcdCoverageForPublic(player.gcd_coverage) } : {}),
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
  entry._reportVariants = [buildReportVariant(entry)];
  return attachVersionState(entry, encounter);
}

function collectEntriesFromReports({ ranking, encounter, includeHiddenReports = false }) {
  // 完整 reports 是最可信來源：它能辨識同場玩家、重複上傳與物理戰鬥。
  // 歷史 v1 fight_hash 會在記憶體重算為 v2；v2 不含輸出／通關時間，因此不同
  // 上傳者的 table 毫秒或小數漂移不會再把同一場拆成多筆個人成績。
  const entriesByExactKey = new Map();
  const rankIndex = buildJobRankIndex(ranking.ranking_entries || []);
  const fightIdentityEncounter = buildFightIdentityEncounter(ranking, encounter);
  const confirmedAnomalousFightHashes = collectConfirmedAnomalousFightHashes(ranking, fightIdentityEncounter);

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
      if (isIntegrityHiddenFightOrDuplicate(fight, report, fightIdentityEncounter, confirmedAnomalousFightHashes)) {
        continue;
      }

      const fightPlayers = Array.isArray(fight.players) ? fight.players : [];
      const fightHash = resolvePhysicalFightHash(fight, fightIdentityEncounter);
      for (const player of fightPlayers) {
        const entry = makePublicEntry({ encounter, report, reportCode, fight, fightHash, player, fightPlayers });
        if (!entry) {
          continue;
        }

        const exactKey = fightHash
          ? createId({
              encounter_key: entry.encounter_key,
              fight_hash: fightHash,
              character_name: entry.character_name,
              server: entry.server,
              job: entry.job,
            })
          : createId({
              encounter_key: entry.encounter_key,
              fight_hash: null,
              report_code: entry.report_code,
              fight_id: entry.fight_id,
              character_name: entry.character_name,
              server: entry.server,
              job: entry.job,
            });
        const existing = entriesByExactKey.get(exactKey);
        if (existing) {
          mergeDuplicateEntry(existing, entry);
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
      const healingStats = compactHealingStats(entry.healing_stats);
      const tankStats = compactTankStats(entry.tank_stats);
      const coHealer = compactCoHealer(entry.co_healer);
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
        ...(healingStats ? { healing_stats: healingStats } : {}),
        ...(tankStats ? { tank_stats: tankStats } : {}),
        ...(coHealer ? { co_healer: coHealer } : {}),
        ...(Object.hasOwn(entry, "gcd_coverage") ? { gcd_coverage: sanitizeGcdCoverageForPublic(entry.gcd_coverage) } : {}),
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
        ...(Object.hasOwn(player, "gcd_coverage") ? { gcd_coverage: sanitizeGcdCoverageForPublic(player.gcd_coverage) } : {}),
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

function buildTeamRecord({ encounter, report, reportCode, fight, fightHash }) {
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
    ...(fightHash
      ? { fight_hash: fightHash }
      : {
          report_code: reportCode,
          fight_id: fight.fight_id ?? null,
        }),
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
  // v2 fight_hash 是最佳識別來源；欄位不足時才退回 report/fight 身分，避免用相近輸出誤合併不同 pull。
  const recordsByFight = new Map();
  const fightIdentityEncounter = buildFightIdentityEncounter(ranking, encounter);
  const confirmedAnomalousFightHashes = collectConfirmedAnomalousFightHashes(ranking, fightIdentityEncounter);

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
      if (isIntegrityHiddenFightOrDuplicate(fight, report, fightIdentityEncounter, confirmedAnomalousFightHashes)) {
        continue;
      }

      const fightHash = resolvePhysicalFightHash(fight, fightIdentityEncounter);
      const record = buildTeamRecord({ encounter, report, reportCode, fight, fightHash });
      if (!record) {
        continue;
      }

      const dedupeKey = fightHash ? `${encounter.key}:${fightHash}` : record.id;
      const existing = recordsByFight.get(dedupeKey);
      if (existing) {
        const duplicateCount = existing.duplicate_count + 1;
        const representative = compareTeamRecords(record, existing) < 0 ? record : existing;
        representative.duplicate_count = duplicateCount;
        recordsByFight.set(dedupeKey, representative);
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

function getOrCreateUser(usersByIdentity, characterName, server) {
  const identityKey = characterServerKey(characterName, server);
  let user = usersByIdentity.get(identityKey);
  if (!user) {
    user = {
      character_name: characterName,
      servers: new Set([server]),
      entriesByEncounter: new Map(),
      total_entries: 0,
      last_recorded_at_iso: null,
      best_entry: null,
      teammates: new Map(),
    };
    usersByIdentity.set(identityKey, user);
  }
  return user;
}

function addEntry(usersByIdentity, entry) {
  const user = getOrCreateUser(usersByIdentity, entry.character_name, entry.server);
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

function addHiddenUserStub(usersByIdentity, stub) {
  const characterName = stub?.character_name;
  const server = stub?.server;
  if (!characterName || !server) {
    return;
  }

  // 一般公開成績單只保留可開啟的入口與伺服器辨識，不帶入非公開 entry 的成績或隊友資料。
  getOrCreateUser(usersByIdentity, characterName, server);
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

function buildEntryPayload(entry, detailContext = null) {
  const { teammates, _reportVariants, ...payload } = entry;
  // 個人成績單主檔會被每位玩家首屏載入；UI 只需要 gcd_coverage 的顯示值，
  // gcd_coverage_status 屬於管線診斷欄位，保留在來源排行榜資料即可，避免每筆歷史成績重複膨脹。
  delete payload.gcd_coverage_status;
  if (Object.hasOwn(payload, "gcd_coverage")) {
    payload.gcd_coverage = sanitizeGcdCoverageForPublic(payload.gcd_coverage);
  }
  const reportVariants = orderReportVariantsForEntry(mergeReportVariants(_reportVariants), entry);
  if (reportVariants.length > 1) {
    const sourceReports = reportVariants.map((variant) => variant.report_code).filter(Boolean);
    payload.duplicate_count = reportVariants.length;
    if (detailContext?.detailPath && detailContext?.entries) {
      // report_variants 是個人成績單最大的重複 payload；玩家頁只有打開報告彈窗時才需要。
      // 主檔保留穩定 id 與 detail path，讓前端可按需補回所有來源 report，而不影響列表載入。
      payload.report_detail_path = detailContext.detailPath;
      payload.report_detail_id = payload.id;
      if (!detailContext.entries.has(payload.id)) {
        detailContext.entries.set(payload.id, {
          duplicate_count: reportVariants.length,
          source_reports: sourceReports,
          report_variants: reportVariants.map((variant) => compactReportVariantForEntry(variant, payload)),
        });
      }
    } else {
      payload.report_variants = reportVariants;
      payload.source_reports = sourceReports;
    }
  }
  return payload;
}

const inheritedReportVariantFields = new Set([
  // 個人成績報告細節會在前端與主檔代表成績合併後才開彈窗；
  // 因此來源分頁只需要保存不同值，避免同一場多份 report 把成績欄位重複寫進 payload。
  "report_url",
  "report_title",
  "fight_id",
  "recorded_at",
  "recorded_at_iso",
  "dps",
  "rdps",
  "adps",
  "ndps",
  "total_damage",
  "active_time_ms",
  "active_percent",
  "healing_stats",
  "tank_stats",
  "co_healer",
  "clear_time_ms",
  "clear_time_seconds",
  "damage_downtime_ms",
  "damage_downtime_seconds",
  "damage_time_ms",
  "damage_time_seconds",
  "game_version",
  "fflogs_source_id",
  "gcd_coverage",
  "gcd_coverage_status",
  "report_hidden",
  "hidden_reason",
  "hidden_detected_at_iso",
  "hidden_source",
]);

function equivalentJsonValue(left, right) {
  return JSON.stringify(left ?? null) === JSON.stringify(right ?? null);
}

function compactReportVariantForEntry(variant, baseEntry) {
  const compactVariant = {};

  for (const [key, value] of Object.entries(variant)) {
    if (key === "gcd_coverage_status") {
      continue;
    }
    const publicValue = key === "gcd_coverage" ? sanitizeGcdCoverageForPublic(value) : value;
    if (key === "report_url" && variant.report_code) {
      continue;
    }
    if (inheritedReportVariantFields.has(key) && equivalentJsonValue(baseEntry?.[key], publicValue)) {
      continue;
    }
    compactVariant[key] = publicValue;
  }

  return compactVariant;
}

function buildUserEntryDetailsPayload(payload, detailContext, hiddenReportsIncluded = false) {
  if (!detailContext?.entries?.size) {
    return null;
  }

  return {
    schema_version: 1,
    format: "user_entry_details_v1",
    generated_at_iso: payload.generated_at_iso,
    character_name: payload.character_name,
    canonical_server: payload.canonical_server,
    hidden_reports_included: hiddenReportsIncluded,
    entry_count: detailContext.entries.size,
    entries: Object.fromEntries(detailContext.entries),
  };
}

function collectUserEntryDetailIds(profile) {
  const ids = new Set();
  for (const encounter of profile?.encounters || []) {
    const entries = [
      encounter?.best_entry,
      ...(encounter?.best_by_job || []),
      ...(encounter?.public_entries || []),
    ];
    for (const entry of entries) {
      if (entry?.report_detail_path && entry?.report_detail_id) {
        ids.add(entry.report_detail_id);
      }
    }
  }
  return ids;
}

function filterUserEntryDetailsPayload(detailsPayload, ids) {
  if (!detailsPayload || !ids?.size) {
    return null;
  }

  const entries = Object.fromEntries(
    Array.from(ids)
      .map((id) => [id, detailsPayload.entries?.[id]])
      .filter(([, detail]) => detail),
  );
  const entryCount = Object.keys(entries).length;
  if (entryCount === 0) {
    return null;
  }

  return {
    ...detailsPayload,
    entry_count: entryCount,
    entries,
  };
}

function pickProfileEntry(entries) {
  return (entries || []).reduce((best, entry) => (isBetterProfileEntry(entry, best) ? entry : best), null);
}

function buildUserPayload(user, generatedAtIso, updatedAtIsoByEncounter, { reportDetailPath = null, hiddenReportsIncluded = false } = {}) {
  const canonicalServer = user.canonical_server || Array.from(user.servers).sort(compareByLocale)[0] || "";
  const serverAliases = Array.from(user.server_aliases || [])
    .filter((server) => server && server !== canonicalServer)
    .sort(compareByLocale);
  const detailContext = reportDetailPath ? { detailPath: reportDetailPath, entries: new Map() } : null;
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
        best_entry: bestEntry ? buildEntryPayload(bestEntry, detailContext) : null,
        best_by_job: Array.from(bestByJob.values())
          .sort((left, right) => compareByLocale(left.job, right.job))
          .map((entry) => buildEntryPayload(entry, detailContext)),
        public_entries: entries.map((entry) => buildEntryPayload(entry, detailContext)),
      };
    })
    .sort((left, right) => {
      const categoryCompare = compareByLocale(left.encounter_category || "", right.encounter_category || "");
      return categoryCompare || compareByLocale(left.encounter_name, right.encounter_name);
    });

  const payload = {
    schema_version: 1,
    generated_at_iso: generatedAtIso,
    character_name: user.character_name,
    canonical_server: canonicalServer || null,
    servers: canonicalServer ? [canonicalServer] : [],
    server_aliases: serverAliases,
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

  return {
    payload,
    reportDetails: buildUserEntryDetailsPayload(payload, detailContext, hiddenReportsIncluded),
  };
}

function hasHiddenReportMarker(value) {
  return Boolean(value?.report_hidden || value?.hidden_report);
}

function buildUserHiddenDeltaPayload(payload, basePath, basePayload = null) {
  // hidden delta 不能只看 report_hidden。戰鬥完整性檢核也會讓一場戰鬥不進公開底稿，
  // 但它不會把整份 FFLogs report 標為 private。若只依 report_hidden 篩選，完整鏡像
  // 的 summary 會包含該筆成績，實際合併後的 encounters 卻遺失它，造成管理檢視與
  // 公開資料的資料守恆失敗。因此以公開底稿已實際輸出的 entry id 為準：底稿沒有的
  // entry 必須由 delta 補上；已公開但來源 report 已隱藏的代表 entry 則仍由 delta
  // 覆寫，保留隱藏來源的正確變體與報告狀態。
  const baseEntryIdsByEncounter = new Map(
    (basePayload?.encounters || []).map((encounter) => [
      encounter?.encounter_key,
      new Set((encounter?.public_entries || []).map((entry) => entry?.id).filter(Boolean)),
    ]),
  );
  const deltaEncounters = (payload.encounters || [])
    .map((encounter) => {
      const baseEntryIds = baseEntryIdsByEncounter.get(encounter.encounter_key) || new Set();
      const hiddenEntries = (encounter.public_entries || []).filter(
        (entry) => hasHiddenReportMarker(entry) || !baseEntryIds.has(entry?.id),
      );
      const hasHiddenBestEntry = hasHiddenReportMarker(encounter.best_entry);
      const hasHiddenBestByJob = (encounter.best_by_job || []).some(hasHiddenReportMarker);
      if (hiddenEntries.length === 0 && !hasHiddenBestEntry && !hasHiddenBestByJob) {
        return null;
      }

      return {
        encounter_key: encounter.encounter_key,
        encounter_name: encounter.encounter_name,
        encounter_category: encounter.encounter_category,
        updated_at_iso: encounter.updated_at_iso,
        // best_entry / best_by_job 使用完整鏡像的結果，避免 hidden report 其實是該副本代表成績時，
        // 前端只附加 hidden 歷史列卻仍顯示公開資料的代表列。
        best_entry: encounter.best_entry,
        best_by_job: encounter.best_by_job || [],
        public_entry_order: (encounter.public_entries || []).map((entry) => entry?.id).filter(Boolean),
        public_entries: hiddenEntries,
      };
    })
    .filter(Boolean);

  if (deltaEncounters.length === 0) {
    return null;
  }

  return {
    schema_version: 1,
    format: "user_profile_hidden_delta_v1",
    base_path: basePath,
    generated_at_iso: payload.generated_at_iso,
    character_name: payload.character_name,
    canonical_server: payload.canonical_server,
    servers: payload.servers,
    server_aliases: payload.server_aliases,
    summary: payload.summary,
    frequent_teammates: payload.frequent_teammates,
    encounter_order: (payload.encounters || []).map((encounter) => encounter.encounter_key).filter(Boolean),
    encounters: deltaEncounters,
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

function createActivityLogAccumulator() {
  return {
    buckets: new Map(),
    series: new Map(),
    earliestDate: null,
    latestDate: null,
    latestRecordedAtMs: 0,
  };
}

function createActivityLogSeriesMeta(encounter) {
  return {
    encounter_key: encounter.encounter_key,
    encounter_name: encounter.encounter_name,
    encounter_category: encounter.encounter_category,
    uniqueReportKeys: new Set(),
    uniqueFightKeys: new Set(),
    latestRecordedAtMs: 0,
  };
}

function getActivityLogSeriesMeta(accumulator, encounter) {
  const key = encounter.encounter_key;
  let meta = accumulator.series.get(key);
  if (!meta) {
    meta = createActivityLogSeriesMeta(encounter);
    accumulator.series.set(key, meta);
  }
  return meta;
}

function getActivityLogBucket(accumulator, encounter, dateKey) {
  const key = `${encounter.encounter_key}:${dateKey}`;
  let bucket = accumulator.buckets.get(key);
  if (!bucket) {
    bucket = {
      date: dateKey,
      encounter_key: encounter.encounter_key,
      encounter_name: encounter.encounter_name,
      encounter_category: encounter.encounter_category,
      uniqueReportKeys: new Set(),
      uniqueFightKeys: new Set(),
      latestRecordedAtMs: 0,
    };
    accumulator.buckets.set(key, bucket);
  }
  return bucket;
}

function updateActivityLogDateRange(accumulator, dateKey, recordedAtMs) {
  if (!accumulator.earliestDate || dateKey < accumulator.earliestDate) {
    accumulator.earliestDate = dateKey;
  }
  if (!accumulator.latestDate || dateKey > accumulator.latestDate) {
    accumulator.latestDate = dateKey;
  }
  if (recordedAtMs > accumulator.latestRecordedAtMs) {
    accumulator.latestRecordedAtMs = recordedAtMs;
  }
}

function addActivityLogCounts(accumulator, encounter, dateKey, recordedAtMs, counts) {
  const bucket = getActivityLogBucket(accumulator, encounter, dateKey);
  const meta = getActivityLogSeriesMeta(accumulator, encounter);

  if (counts.reportKey) {
    bucket.uniqueReportKeys.add(counts.reportKey);
    meta.uniqueReportKeys.add(counts.reportKey);
  }
  if (counts.fightKey) {
    bucket.uniqueFightKeys.add(counts.fightKey);
    meta.uniqueFightKeys.add(counts.fightKey);
  }

  bucket.latestRecordedAtMs = Math.max(bucket.latestRecordedAtMs, recordedAtMs);
  meta.latestRecordedAtMs = Math.max(meta.latestRecordedAtMs, recordedAtMs);
  updateActivityLogDateRange(accumulator, dateKey, recordedAtMs);
}

function addActivityLogObservation(accumulator, encounter, dateKey, recordedAtMs, counts) {
  const allEncounter = {
    encounter_key: "all",
    encounter_name: "全部副本",
    encounter_category: null,
  };
  addActivityLogCounts(accumulator, allEncounter, dateKey, recordedAtMs, counts);
  addActivityLogCounts(accumulator, {
    encounter_key: encounter.key,
    encounter_name: encounter.name,
    encounter_category: encounter.category || null,
  }, dateKey, recordedAtMs, counts);
}

function addActivityLogsFromReports(
  accumulator,
  { ranking, encounter, includeHiddenReports = false },
) {
  // 近期動態的 Logs 曲線以 reports/fights/players 權威來源建立：
  // report_code 回答「有多少份 FFLogs 日誌」，v2 fight_hash 回答「去重後有多少場通關」。
  // 這兩個口徑若在 Vue 端用 ranking_entries 反推，會把同場多份上傳或同一 report 內多場戰鬥混在一起。
  const fightIdentityEncounter = buildFightIdentityEncounter(ranking, encounter);
  const confirmedAnomalousFightHashes = collectConfirmedAnomalousFightHashes(ranking, fightIdentityEncounter);
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
      if (isIntegrityHiddenFightOrDuplicate(fight, report, fightIdentityEncounter, confirmedAnomalousFightHashes)) {
        continue;
      }

      const recordedAtMs = fightRecordedAtMs(fight, report);
      const dateKey = taiwanDateKeyFromMs(recordedAtMs);
      const fightPlayers = Array.isArray(fight.players) ? fight.players : [];
      if (!dateKey || fightPlayers.length === 0) {
        continue;
      }

      const fightHash = resolvePhysicalFightHash(fight, fightIdentityEncounter);
      const fightKey = fightHash
        ? `${encounter.key}:${fightHash}`
        : `${encounter.key}:${reportCode}:${fight.fight_id ?? ""}:${recordedAtMs}`;
      addActivityLogObservation(accumulator, encounter, dateKey, recordedAtMs, {
        reportKey: reportCode || null,
        fightKey,
      });
    }
  }
}

function addActivityLogsFromEntries(accumulator, { entries, encounter }) {
  // 舊資料若沒有 reports 分片，至少用 ranking_entries 建出相容的 Logs 與通關場次粗估。
  // 這條路徑沒有 report/fight 完整隊友，因此只作為舊格式保底，不應成為新統計的主要來源。
  for (const entry of entries || []) {
    const recordedAtMs = entryRecordedAtMs(entry);
    const dateKey = taiwanDateKeyFromMs(recordedAtMs);
    if (!dateKey) {
      continue;
    }

    const reportKey = entry.report_code || entry.report_url || null;
    const fightHash = resolvePhysicalFightHash(entry, encounter);
    const fightKey = fightHash
      ? `${encounter.key}:${fightHash}`
      : `${encounter.key}:${reportKey || entry.id}:${entry.fight_id ?? ""}:${recordedAtMs}`;

    addActivityLogObservation(accumulator, encounter, dateKey, recordedAtMs, {
      reportKey,
      fightKey,
    });
  }
}

function serializeActivityLogPoint(bucket) {
  return {
    date: bucket.date,
    unique_report_count: bucket.uniqueReportKeys.size,
    unique_fight_count: bucket.uniqueFightKeys.size,
    latest_recorded_at_iso: bucket.latestRecordedAtMs > 0 ? new Date(bucket.latestRecordedAtMs).toISOString() : null,
  };
}

function serializeActivityLogSeries(accumulator, meta) {
  const points = Array.from(accumulator.buckets.values())
    .filter((bucket) => bucket.encounter_key === meta.encounter_key)
    .sort((left, right) => compareByLocale(left.date, right.date))
    .map(serializeActivityLogPoint);

  return {
    encounter_key: meta.encounter_key,
    encounter_name: meta.encounter_name,
    encounter_category: meta.encounter_category,
    total_unique_report_count: meta.uniqueReportKeys.size,
    total_unique_fight_count: meta.uniqueFightKeys.size,
    latest_recorded_at_iso: meta.latestRecordedAtMs > 0 ? new Date(meta.latestRecordedAtMs).toISOString() : null,
    points,
  };
}

function createActivityLogCategoryBucket(category, date) {
  return {
    date,
    category,
    uniqueReportKeys: new Set(),
    uniqueFightKeys: new Set(),
    latestRecordedAtMs: 0,
  };
}

function buildActivityLogCategorySeries(accumulator) {
  const categoryIndex = new Map();

  for (const bucket of accumulator.buckets.values()) {
    if (bucket.encounter_key === "all" || !bucket.encounter_category) {
      continue;
    }

    let categoryEntry = categoryIndex.get(bucket.encounter_category);
    if (!categoryEntry) {
      categoryEntry = {
        category: bucket.encounter_category,
        uniqueReportKeys: new Set(),
        uniqueFightKeys: new Set(),
        latestRecordedAtMs: 0,
        buckets: new Map(),
      };
      categoryIndex.set(bucket.encounter_category, categoryEntry);
    }

    let categoryBucket = categoryEntry.buckets.get(bucket.date);
    if (!categoryBucket) {
      categoryBucket = createActivityLogCategoryBucket(bucket.encounter_category, bucket.date);
      categoryEntry.buckets.set(bucket.date, categoryBucket);
    }

    for (const reportKey of bucket.uniqueReportKeys) {
      categoryBucket.uniqueReportKeys.add(reportKey);
      categoryEntry.uniqueReportKeys.add(reportKey);
    }
    for (const fightKey of bucket.uniqueFightKeys) {
      categoryBucket.uniqueFightKeys.add(fightKey);
      categoryEntry.uniqueFightKeys.add(fightKey);
    }
    categoryBucket.latestRecordedAtMs = Math.max(categoryBucket.latestRecordedAtMs, bucket.latestRecordedAtMs);
    categoryEntry.latestRecordedAtMs = Math.max(categoryEntry.latestRecordedAtMs, bucket.latestRecordedAtMs);
  }

  const categoryOrder = new Map(activityLogCategoryOrder.map((category, index) => [category, index]));
  return Array.from(categoryIndex.values())
    .sort((left, right) => {
      const leftOrder = categoryOrder.get(left.category) ?? activityLogCategoryOrder.length;
      const rightOrder = categoryOrder.get(right.category) ?? activityLogCategoryOrder.length;
      return leftOrder - rightOrder || compareByLocale(left.category, right.category);
    })
    .map((categoryEntry) => ({
      category: categoryEntry.category,
      label: categoryEntry.category,
      total_unique_report_count: categoryEntry.uniqueReportKeys.size,
      total_unique_fight_count: categoryEntry.uniqueFightKeys.size,
      latest_recorded_at_iso: categoryEntry.latestRecordedAtMs > 0 ? new Date(categoryEntry.latestRecordedAtMs).toISOString() : null,
      points: Array.from(categoryEntry.buckets.values())
        .sort((left, right) => compareByLocale(left.date, right.date))
        .map(serializeActivityLogPoint),
    }));
}

function buildActivityLogPayload(accumulator) {
  const allMeta = accumulator.series.get("all") || createActivityLogSeriesMeta({
    encounter_key: "all",
    encounter_name: "全部副本",
    encounter_category: null,
  });
  const encounterSeries = Array.from(accumulator.series.values())
    .filter((meta) => meta.encounter_key !== "all")
    .sort((left, right) => right.uniqueFightKeys.size - left.uniqueFightKeys.size || compareByLocale(left.encounter_name, right.encounter_name));

  return {
    schema_version: 1,
    default_window_days: activityLogDefaultWindowDays,
    available_start_date: accumulator.earliestDate,
    available_end_date: accumulator.latestDate,
    baseline_at_iso: accumulator.latestRecordedAtMs > 0 ? new Date(accumulator.latestRecordedAtMs).toISOString() : null,
    metrics: [
      { key: "unique_report_count", label: "Logs" },
      { key: "unique_fight_count", label: "通關場次" },
    ],
    summary: {
      total_unique_report_count: allMeta.uniqueReportKeys.size,
      total_unique_fight_count: allMeta.uniqueFightKeys.size,
    },
    series: [
      serializeActivityLogSeries(accumulator, allMeta),
      ...encounterSeries.map((meta) => serializeActivityLogSeries(accumulator, meta)),
    ],
    category_series: buildActivityLogCategorySeries(accumulator),
  };
}

function buildActivityPayload(entries, generatedAtIso, latestRankingUpdatedAt, activityLogAccumulator = createActivityLogAccumulator()) {
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
    log_activity: buildActivityLogPayload(activityLogAccumulator),
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
  userProfileMode = "full",
}) {
  const outputDir = path.join(outputDataDir, "users");
  const userEntryDetailsDir = path.join(outputDataDir, userEntryDetailsDirName);
  const globalStatsPath = path.join(outputDataDir, "global_stats.json");
  const activityPath = path.join(outputDataDir, "activity.json");
  const teamRankingsPath = path.join(outputDataDir, "team_rankings.json");
  const serverComparePath = path.join(outputDataDir, "server_compare.json");

  assertInside(basePublicDataDir, outputDataDir);
  assertInside(basePublicDataDir, outputDir);
  assertInside(basePublicDataDir, userEntryDetailsDir);
  assertInside(basePublicDataDir, globalStatsPath);
  assertInside(basePublicDataDir, activityPath);
  assertInside(basePublicDataDir, teamRankingsPath);
  assertInside(basePublicDataDir, serverComparePath);

  const [encounters, gameVersions] = await Promise.all([loadEncounters(), loadGameVersions()]);
  const usersByIdentity = new Map();
  const updatedAtIsoByEncounter = new Map();
  const overallCharacterKeys = new Set();
  const encounterStats = [];
  const allEntries = [];
  const activityLogAccumulator = createActivityLogAccumulator();
  const teamRecordsByEncounter = new Map();
  const pendingEncounterData = [];
  const hiddenUserStubs = [];

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
    const teamRecords = ranking.reports
      ? collectTeamRecordsFromReports({ ranking, encounter, includeHiddenReports })
      : [];
    if (ranking.reports) {
      addActivityLogsFromReports(activityLogAccumulator, {
        ranking,
        encounter,
        includeHiddenReports,
      });
    } else {
      addActivityLogsFromEntries(activityLogAccumulator, { entries, encounter });
    }

    pendingEncounterData.push({
      encounter,
      updated_at_iso: ranking.updated_at_iso,
      entries,
      teamRecords,
    });

    // 公開與完整鏡像都必須保留同一批「只有非公開來源」的使用者入口。完整鏡像雖然
    // 可讀取 private report，但戰鬥完整性仍可能排除其中所有 fight；此時若不建立
    // stub，public/data/all 的索引就會比公開索引少人，且前端無法回退至公開底稿。
    hiddenUserStubs.push(...collectHiddenUserStubs(ranking));
  }

  for (const item of pendingEncounterData) {
    const entries = item.entries || [];
    for (const entry of entries) {
      attachGameVersion(entry, gameVersions);
    }
    assignValidVersionJobRanks(entries);
    encounterStats.push(collectEncounterStats(item.encounter, entries, item.updated_at_iso));
    allEntries.push(...entries);

    if (item.teamRecords.length > 0) {
      teamRecordsByEncounter.set(item.encounter.key, item.teamRecords);
    }

    for (const entry of entries) {
      overallCharacterKeys.add(characterServerKey(entry.character_name, entry.server));
      addEntry(usersByIdentity, entry);
    }
  }

  for (const stub of hiddenUserStubs) {
    addHiddenUserStub(usersByIdentity, stub);
  }

  attachRdpsPerformance(allEntries);

  // public/data/users 是完整衍生產物，可以整包重建；append-only 保護的是 data/state 與 data/rankings。
  // 使用者檔名以角色名稱正規化，index.json 的 file_path 才是前端實際讀取入口。
  await removeGeneratedDirectory(outputDir);
  await removeGeneratedDirectory(userEntryDetailsDir);
  await mkdir(outputDir, { recursive: true });
  await mkdir(userEntryDetailsDir, { recursive: true });

  const latestRankingUpdatedAt = Array.from(updatedAtIsoByEncounter.values()).sort().at(-1) || null;
  const generatedAtIso = resolveGeneratedAtIso(latestRankingUpdatedAt);
  const usedFileBaseNames = new Set();
  const indexUsers = [];
  let writtenUserFileCount = 0;
  let writtenUserDetailFileCount = 0;
  const sortedUsers = Array.from(usersByIdentity.values()).sort((left, right) => {
    const nameCompare = compareByLocale(left.character_name, right.character_name);
    if (nameCompare) {
      return nameCompare;
    }
    const leftServer = Array.from(left.servers).sort(compareByLocale)[0] || "";
    const rightServer = Array.from(right.servers).sort(compareByLocale)[0] || "";
    return compareByLocale(leftServer, rightServer);
  });
  const achievementBaselineAtMs = allEntries.reduce(
    (latest, entry) => Math.max(latest, entryRecordedAtMs(entry)),
    0,
  );

  for (const user of sortedUsers) {
    user.canonical_server = Array.from(user.servers).sort(compareByLocale)[0] || "";
    user.server_aliases = new Set();
    const fileBaseName = normalizeFileBaseName(user.character_name, usedFileBaseNames);
    const fileName = `${fileBaseName}.json`;
    const filePath = path.join(outputDir, fileName);
    const publicDetailPathText = `data/${userEntryDetailsDirName}/${fileName}`;
    const publicFilePathText = `data/users/${fileName}`;
    const detailPathText = userProfileMode === "hidden-delta"
      ? `data/all/${userEntryDetailsDirName}/${fileName}`
      : publicDetailPathText;
    const { payload, reportDetails } = buildUserPayload(user, generatedAtIso, updatedAtIsoByEncounter, {
      reportDetailPath: detailPathText,
      hiddenReportsIncluded: includeHiddenReports,
    });
    let indexFilePathText = publicFilePathText;

    if (userProfileMode === "hidden-delta") {
      const basePayload = await readJson(path.join(basePublicDataDir, "users", fileName), null);
      const deltaPayload = buildUserHiddenDeltaPayload(payload, publicFilePathText, basePayload);
      if (deltaPayload) {
        // public/data/all/users 只保存 hidden report 差量；沒有 hidden 成績的使用者直接指回公開成績單。
        // 這能避免完整鏡像把數千份公開個人成績單再複製一份，同時保留額外檢視需要的 hidden 來源。
        await writeJson(filePath, deltaPayload);
        writtenUserFileCount += 1;
        indexFilePathText = `data/all/users/${fileName}`;
        const deltaDetailIds = collectUserEntryDetailIds(deltaPayload);
        const deltaReportDetails = filterUserEntryDetailsPayload(reportDetails, deltaDetailIds);
        if (deltaReportDetails) {
          await writeJson(path.join(userEntryDetailsDir, fileName), deltaReportDetails);
          writtenUserDetailFileCount += 1;
        }
      }
    } else {
      await writeJson(filePath, payload);
      writtenUserFileCount += 1;
      if (reportDetails) {
        await writeJson(path.join(userEntryDetailsDir, fileName), reportDetails);
        writtenUserDetailFileCount += 1;
      }
    }

    indexUsers.push({
      character_name: user.character_name,
      canonical_server: payload.canonical_server,
      servers: payload.servers,
      server_aliases: payload.server_aliases,
      file_path: indexFilePathText,
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
    achievements: buildAchievementStatistics(sortedUsers, achievementBaselineAtMs),
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

  await writeJson(activityPath, buildActivityPayload(allEntries, generatedAtIso, latestRankingUpdatedAt, activityLogAccumulator));
  await writeJson(teamRankingsPath, buildTeamRankingsPayload(teamRecordsByEncounter, generatedAtIso, latestRankingUpdatedAt));
  await writeJson(serverComparePath, buildServerComparePayload(allEntries, normalizedEncounterStats, generatedAtIso, latestRankingUpdatedAt));
  await syncAnnouncementMirror(outputDataDir);
  await waitForUserOutputReady(outputDir, writtenUserFileCount, label);

  console.log(`Built ${label} ${writtenUserFileCount} user data files in ${path.relative(rootDir, outputDir)}.`);
  console.log(`Built ${label} ${writtenUserDetailFileCount} user entry detail files in ${path.relative(rootDir, userEntryDetailsDir)}.`);
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

  // public/data/all 是 hidden delta 產物：公開資料維持在 public/data，all 只補 hidden report 差異。
  await buildDataset({
    outputDataDir: path.join(basePublicDataDir, "all"),
    includeHiddenReports: true,
    label: "Hidden delta",
    userProfileMode: "hidden-delta",
  });
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
