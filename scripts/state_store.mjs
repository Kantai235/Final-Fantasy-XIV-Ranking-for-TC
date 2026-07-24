import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

export const CHECKED_REPORTS_DIRECTORY = path.join("state", "checked_reports");
const SAFE_ENCOUNTER_KEY = /^[A-Za-z0-9_-]+$/;

function recordTime(record) {
  const value = record?.processed_at ?? record?.updated_at;
  return Number.isFinite(Number(value)) ? Number(value) : Number.NEGATIVE_INFINITY;
}

function mergeRecord(inlineRecord, shardRecord) {
  if (!inlineRecord || typeof inlineRecord !== "object" || Array.isArray(inlineRecord)) {
    return shardRecord;
  }
  if (!shardRecord || typeof shardRecord !== "object" || Array.isArray(shardRecord)) {
    return inlineRecord;
  }
  const [preferred, secondary] = recordTime(shardRecord) >= recordTime(inlineRecord)
    ? [shardRecord, inlineRecord]
    : [inlineRecord, shardRecord];
  return { ...secondary, ...preferred };
}

export function checkedReportsShardPath(statePath, encounterKey) {
  if (!SAFE_ENCOUNTER_KEY.test(encounterKey)) {
    throw new Error(`副本 key 不可用於 checked_reports 分片路徑：${String(encounterKey)}`);
  }
  return path.join(path.dirname(statePath), CHECKED_REPORTS_DIRECTORY, `${encounterKey}.json`);
}

export function mergeCheckedReports(inlineReports, shardReports) {
  const inlineMap = inlineReports && typeof inlineReports === "object" && !Array.isArray(inlineReports)
    ? inlineReports
    : {};
  const shardMap = shardReports && typeof shardReports === "object" && !Array.isArray(shardReports)
    ? shardReports
    : {};
  const merged = {};
  for (const reportCode of [...new Set([...Object.keys(inlineMap), ...Object.keys(shardMap)])].sort()) {
    if (!(reportCode in inlineMap)) {
      merged[reportCode] = shardMap[reportCode];
    } else if (!(reportCode in shardMap)) {
      merged[reportCode] = inlineMap[reportCode];
    } else {
      merged[reportCode] = mergeRecord(inlineMap[reportCode], shardMap[reportCode]);
    }
  }
  return merged;
}

export function readStateWithCheckedReportShards(statePath, fallback = {}) {
  if (!existsSync(statePath)) {
    return fallback;
  }
  const state = JSON.parse(readFileSync(statePath, "utf8"));
  if (!state || typeof state !== "object" || Array.isArray(state)) {
    throw new Error(`狀態檔必須是 JSON 物件：${statePath}`);
  }
  const encounters = state.encounters;
  if (!encounters || typeof encounters !== "object" || Array.isArray(encounters)) {
    return state;
  }
  for (const [encounterKey, encounterState] of Object.entries(encounters)) {
    if (!encounterState || typeof encounterState !== "object" || Array.isArray(encounterState)) {
      continue;
    }
    const shardPath = checkedReportsShardPath(statePath, encounterKey);
    if (!existsSync(shardPath)) {
      continue;
    }
    const shardReports = JSON.parse(readFileSync(shardPath, "utf8"));
    if (!shardReports || typeof shardReports !== "object" || Array.isArray(shardReports)) {
      throw new Error(`checked_reports 分片必須是 JSON 物件：${shardPath}`);
    }
    encounterState.checked_reports = mergeCheckedReports(encounterState.checked_reports, shardReports);
  }
  return state;
}
