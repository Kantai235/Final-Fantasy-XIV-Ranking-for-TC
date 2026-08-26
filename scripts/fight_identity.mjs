import { createHash } from "node:crypto";

// fight_hash v2 只描述「這是哪一場物理戰鬥」，不能混入 rDPS、通關時間或
// 其他會因 FFLogs 上傳來源／後續回補而漂移的衍生值。Python 資料取得層會
// 使用同一份欄位契約落地；Node.js 建置層則用這個 helper 相容尚未遷移的歷史資料。
export const physicalFightHashVersion = 2;

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

function toInteger(value) {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  const number = Number(value);
  return Number.isFinite(number) ? Math.trunc(number) : null;
}

function recordedAtMs(fight) {
  const explicitValue = toInteger(fight?.recorded_at);
  if (explicitValue !== null && explicitValue > 0) {
    return explicitValue;
  }

  const parsedValue = new Date(fight?.recorded_at_iso || "").getTime();
  return Number.isFinite(parsedValue) && parsedValue > 0 ? Math.trunc(parsedValue) : null;
}

function normalizedRoster(players) {
  const sourcePlayers = Array.isArray(players) ? players : [];
  const roster = sourcePlayers
    .map((player) => ({
      name: String(player?.name || player?.character_name || "").trim(),
      server: String(player?.server || "").trim(),
      job: String(player?.job || "").trim(),
    }))
    .filter((player) => player.name && player.server && player.job);

  // v2 契約要求完整名單。任一玩家缺少身分欄位時必須保守退回，
  // 不可用「剩下玩家」的子集指紋去猜測，以免誤合併真正名單不同的戰鬥。
  if (sourcePlayers.length === 0 || roster.length !== sourcePlayers.length) {
    return [];
  }

  roster.sort((left, right) => {
    for (const field of ["name", "server", "job"]) {
      if (left[field] !== right[field]) {
        return left[field] < right[field] ? -1 : 1;
      }
    }
    return 0;
  });
  return roster;
}

export function calculatePhysicalFightHash(fight, encounter = null) {
  const encounterId = toInteger(fight?.encounter_id ?? encounter?.encounter_id);
  const difficulty = toInteger(fight?.difficulty ?? encounter?.difficulty);
  const fightRecordedAtMs = recordedAtMs(fight);
  const roster = normalizedRoster(fight?.players);

  // 缺少任一必要欄位時不能用近似數值猜測同場，否則可能把不同 pull 誤合併。
  // 呼叫端會保守退回舊 fight_hash 或 report_code + fight_id 的來源身分。
  if (encounterId === null || difficulty === null || fightRecordedAtMs === null || roster.length === 0) {
    return null;
  }

  const payload = {
    difficulty,
    encounter_id: encounterId,
    fight_hash_version: physicalFightHashVersion,
    players: roster,
    recorded_at_ms: fightRecordedAtMs,
  };
  return createHash("sha256").update(stableJson(payload)).digest("hex");
}

export function resolvePhysicalFightHash(fight, encounter = null) {
  const storedHash = typeof fight?.fight_hash === "string" ? fight.fight_hash.trim() : "";
  if (storedHash && Number(fight?.fight_hash_version) === physicalFightHashVersion) {
    return storedHash;
  }

  return calculatePhysicalFightHash(fight, encounter) || storedHash || null;
}
