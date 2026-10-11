// 傷害驗證已停用，但不能把「未做驗證」與「歷史驗證未通過」混為一談。
// 固定沿用退役時可公開的版本，避免過舊 valid 或缺少 hidden 旗標的失準結論回流。
const publicVersions = new Set([8, 9, 10, 11, 12, 13]);
const publicStatuses = new Set(["valid", "not_applicable"]);

export function isHistoricalIntegrityHidden(fight) {
  if (!Object.hasOwn(fight || {}, "data_integrity")) return false;
  const result = fight.data_integrity;
  return !result || typeof result !== "object" || Array.isArray(result)
    || Boolean(result.hidden_from_public)
    || !publicVersions.has(Number(result.calculation_version))
    || !publicStatuses.has(result.status);
}

export function isHistoricalIntegrityAnomaly(fight) {
  // status 已是歷史判定證據，不要求舊資料一定另有 hidden_from_public 鏡像旗標。
  return ["excluded", "suspected"].includes(fight?.data_integrity?.status);
}
