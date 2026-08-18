export const 預設副本鍵值 = "savage_m7s";
export const 預設排序欄位 = "rdps";
export const 預設排序方向 = "desc";
export const 預設比較職能 = "role:tank";
export const 預設比較副本鍵值 = "all";
export const 預設版本紀錄範圍 = "all";
export const 預設統計副本鍵值 = "all";
export const 預設統計職業範圍 = "all";
export const 預設伺服器拆分模式 = "none";
export const 預設統計傷害指標 = "rdps";
export const 預設隊伍榜副本鍵值 = "savage_m7s";
export const 預設職業分析範圍 = "role:tank";

export const 作者角色名稱 = "乾太";
export const 作者說明文字 = "這個網站的作者，可愛的乾太。";

export const 傷害比較指標選項 = [
  { value: "dps", label: "DPS" },
  { value: "rdps", label: "rDPS" },
  { value: "adps", label: "aDPS" },
];

export const 版本紀錄範圍選項 = [
  { value: "all", label: "全部版本" },
  { value: "obsolete", label: "過時版本紀錄" },
  { value: "valid", label: "有效版本紀錄" },
];

export { 副本分類順序 } from "../../domain/encounters.js";

export const 排序欄位標籤 = {
  rank: "排名",
  active: "Active",
  gcdCoverage: "GCD 覆蓋率",
  dps: "DPS",
  rdps: "rDPS",
  adps: "aDPS",
  healingHps: "HPS",
  pureHealing: "純治療",
  healingProtection: "防護量",
  overhealPercent: "OH%",
  damageTaken: "承傷",
  selfHealing: "自補",
  personalProtection: "個人防護",
  teamProtection: "團隊防護",
  mitigationCoverage: "減傷覆蓋",
  clearTime: "通關時間",
  recordedAt: "紀錄時間",
};

export const 排序預設方向 = {
  rank: "asc",
  active: "desc",
  gcdCoverage: "desc",
  dps: "desc",
  rdps: "desc",
  adps: "desc",
  healingHps: "desc",
  pureHealing: "desc",
  healingProtection: "desc",
  overhealPercent: "asc",
  damageTaken: "asc",
  selfHealing: "desc",
  personalProtection: "desc",
  teamProtection: "desc",
  mitigationCoverage: "desc",
  clearTime: "asc",
  recordedAt: "desc",
};
