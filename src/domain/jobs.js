import { 建立公開資料網址 } from "../utils/publicData.js";

// FFLogs 回傳職業代碼為英文 job slug；前端所有頁面都透過這張表轉成繁中顯示。
// 新增職業時，需同步補上：繁中名稱、職業群組、職業圖示檔名與比較圖色彩。
export const 職業繁中名稱 = {
  Paladin: "騎士",
  Warrior: "戰士",
  DarkKnight: "暗黑騎士",
  Gunbreaker: "絕槍戰士",
  WhiteMage: "白魔道士",
  Scholar: "學者",
  Astrologian: "占星術師",
  Sage: "賢者",
  Monk: "武僧",
  Dragoon: "龍騎士",
  Ninja: "忍者",
  Samurai: "武士",
  Reaper: "奪魂者",
  Viper: "毒蛇劍士",
  Bard: "吟遊詩人",
  Machinist: "機工士",
  Dancer: "舞者",
  BlackMage: "黑魔道士",
  Summoner: "召喚士",
  RedMage: "赤魔道士",
  Pictomancer: "繪靈法師",
  BlueMage: "青魔法師",
};

// 這裡的群組同時服務三種 UI：排行榜篩選、職業分析分組、玩家比較職能。
// 請維持代碼穩定，因為多個 computed 會用 role:* 代碼串接資料與狀態。
export const 職業群組設定 = [
  {
    代碼: "role:tank",
    名稱: "防護職業",
    色彩: "tank",
    職業: ["Paladin", "Warrior", "DarkKnight", "Gunbreaker"],
  },
  {
    代碼: "role:healer",
    名稱: "治療職業",
    色彩: "healer",
    職業: ["WhiteMage", "Scholar", "Astrologian", "Sage"],
  },
  {
    代碼: "role:melee",
    名稱: "近戰職業",
    色彩: "dps",
    職業: ["Monk", "Dragoon", "Ninja", "Samurai", "Reaper", "Viper"],
  },
  {
    代碼: "role:physical_ranged",
    名稱: "遠程物理職業",
    色彩: "dps",
    職業: ["Bard", "Machinist", "Dancer"],
  },
  {
    代碼: "role:magical_ranged",
    名稱: "遠程魔法職業",
    色彩: "dps",
    職業: ["BlackMage", "Summoner", "RedMage", "Pictomancer"],
  },
];

export const 職業群組索引 = 職業群組設定.reduce((索引, 群組) => {
  索引[群組.代碼] = new Set(群組.職業);
  return 索引;
}, {});

const 職業Icon檔名 = {
  Paladin: "Paladin.png",
  Warrior: "Warrior.png",
  DarkKnight: "DarkKnight.png",
  Gunbreaker: "Gunbreaker.png",
  WhiteMage: "WhiteMage.png",
  Scholar: "Scholar.png",
  Astrologian: "Astrologian.png",
  Sage: "Sage.png",
  Monk: "Monk.png",
  Dragoon: "Dragoon.png",
  Ninja: "Ninja.png",
  Samurai: "Samurai.png",
  Reaper: "Reaper.png",
  Viper: "Viper.png",
  Bard: "Bard.png",
  Machinist: "Machinist.png",
  Dancer: "Dancer.png",
  BlackMage: "BlackMage.png",
  Summoner: "Summoner.png",
  RedMage: "RedMage.png",
  Pictomancer: "Pictomancer.png",
  BlueMage: "BlueMage.png",
};

const 職業比較色彩 = {
  Paladin: "#6aa8ff",
  Warrior: "#b46bff",
  DarkKnight: "#8d75ff",
  Gunbreaker: "#4fc1a6",
  WhiteMage: "#72d56f",
  Scholar: "#5f9dff",
  Astrologian: "#d49bff",
  Sage: "#66d5dc",
  Monk: "#d49a32",
  Dragoon: "#6686ff",
  Ninja: "#c73d8f",
  Samurai: "#d96d22",
  Reaper: "#9b5a93",
  Viper: "#35a545",
  Bard: "#9abf66",
  Machinist: "#57c8be",
  Dancer: "#e5a2a5",
  BlackMage: "#a477d8",
  Summoner: "#3ba88d",
  RedMage: "#e67070",
  Pictomancer: "#eb80c9",
};

const 職業類型Icon檔名 = {
  "role:tank": "RoleTank.png",
  "role:healer": "RoleHealer.png",
  "role:melee": "RoleMelee.png",
  "role:physical_ranged": "RolePhysicalRanged.png",
  "role:magical_ranged": "RoleMagicalRanged.png",
};

export const 比較職能設定 = 職業群組設定.map((群組) => ({ ...群組, 圖示代碼: 群組.代碼 }));
export const 比較職能索引 = new Map(比較職能設定.map((職能) => [職能.代碼, 職能]));

export function 顯示職業名稱(職業代碼) {
  return 職業繁中名稱[職業代碼] || 職業代碼 || "-";
}

export function 職業Icon路徑(職業代碼) {
  const 檔名 = 職業Icon檔名[職業代碼];
  return 檔名 ? 建立公開資料網址(`icons/jobs/${檔名}`) : "";
}

export function 職業類型Icon路徑(類型代碼) {
  const 檔名 = 職業類型Icon檔名[類型代碼];
  return 檔名 ? 建立公開資料網址(`icons/jobs/${檔名}`) : "";
}

export function 職業色彩類別(色彩) {
  return {
    防護色: 色彩 === "tank",
    治療色: 色彩 === "healer",
    輸出色: 色彩 === "dps",
  };
}

export function 職業代碼色彩(職業代碼) {
  return 職業群組設定.find((群組) => 群組.職業.includes(職業代碼))?.色彩 || "";
}

export function 職業比較圖色彩(職業代碼) {
  return 職業比較色彩[職業代碼] || "var(--重點色)";
}

export function 職業類型色彩(類型代碼) {
  return 職業群組設定.find((群組) => 群組.代碼 === 類型代碼)?.色彩 || "";
}

export function 職業類型排序值(類型代碼) {
  const 索引 = 職業群組設定.findIndex((群組) => 群組.代碼 === 類型代碼);
  return 索引 >= 0 ? 索引 : Number.MAX_SAFE_INTEGER;
}

export function 職業所屬類型(職業代碼) {
  return 職業群組設定.find((群組) => 群組.職業.includes(職業代碼)) || null;
}

export function 取得比較職能(職業代碼) {
  const 詳細類型 = 職業所屬類型(職業代碼);
  if (!詳細類型) {
    return null;
  }

  return 比較職能索引.get(詳細類型.代碼) || null;
}
