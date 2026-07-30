import { 計算PR值 } from "./formatters.js";

// 簡表版本是「當時可看到什麼」的歷史快照，不等同排行榜的 valid/obsolete 分類。
// cutoff 採下一個版本開放的瞬間，避免剛改版後上傳的戰鬥被錯放回舊版。已知開放時間的
// 未來版本會保留在選單中，但瀏覽器時間到達前仍不可選取，讓部署可提早完成而不污染歷史快照。
export const 個人成績簡表版本選項 = Object.freeze([
  { value: "7.0", label: "7.0", record_cutoff_iso: "2026-03-10T10:00:00.000Z" },
  { value: "7.05", label: "7.05", record_cutoff_iso: "2026-04-21T10:00:00.000Z" },
  { value: "7.1", label: "7.1", record_cutoff_iso: "2026-06-23T10:00:00.000Z" },
  { value: "7.15", label: "7.15", record_cutoff_iso: "2026-07-28T05:00:00.000Z" },
  { value: "7.2", label: "7.2", record_cutoff_iso: null, available_from_iso: "2026-07-28T05:00:00.000Z" },
]);

// 個別玩家成績由專用資料來源提供，部署新版欄位與舊有 JSON 的更新時間不一定同步。
// 因此明確寫入的 game_version 優先；缺欄位的既有紀錄則固定依繁中服改版切點回推，
// 讓版本欄位與篩選選單在資料逐步重建前仍能維持可用，且不影響建置層的資料權威性。
export function 取得個人成績紀錄版本(成績) {
  const 明確版本 = String(成績?.game_version || "").trim();
  if (明確版本) {
    return 明確版本;
  }

  const 紀錄時間 = new Date(成績?.recorded_at_iso || "").getTime();
  if (!Number.isFinite(紀錄時間)) {
    return "";
  }

  const 對應版本 = 個人成績簡表版本選項.find((版本) => {
    const 截止時間 = new Date(版本.record_cutoff_iso || "").getTime();
    return Number.isFinite(截止時間) && 紀錄時間 < 截止時間;
  });

  return 對應版本?.value || 個人成績簡表版本選項.at(-1)?.value || "";
}

// 趨勢圖的橫軸只有在每筆紀錄都能解析出時間時，才能精準對齊繁中服改版切點。
// 切點標籤使用「切點之後」開始的版本：例如 7.05 的線就是 7.0 截止、
// 7.05 開始的瞬間。這樣不需要另存趨勢標記，仍能與既有版本回推規則保持一致。
export function 建立個人成績趨勢版本切點(起始時間戳記, 結束時間戳記) {
  if (
    !Number.isFinite(起始時間戳記)
    || !Number.isFinite(結束時間戳記)
    || 結束時間戳記 <= 起始時間戳記
  ) {
    return [];
  }

  const 時間範圍 = 結束時間戳記 - 起始時間戳記;
  return 個人成績簡表版本選項
    .map((版本, index) => {
      if (index === 0) {
        return null;
      }

      const 前一版本 = 個人成績簡表版本選項[index - 1];
      const 切點時間戳記 = new Date(版本.available_from_iso || 前一版本?.record_cutoff_iso || "").getTime();
      // 切點在圖形邊緣時不另外畫線，以免標籤被裁切；它也無法幫助辨識圖中的歷史分段。
      if (!Number.isFinite(切點時間戳記) || 切點時間戳記 <= 起始時間戳記 || 切點時間戳記 >= 結束時間戳記) {
        return null;
      }

      const x = Number((((切點時間戳記 - 起始時間戳記) / 時間範圍) * 100).toFixed(2));
      return {
        key: `game-version-${版本.value}`,
        label: 版本.label,
        starts_at_iso: new Date(切點時間戳記).toISOString(),
        x,
      };
    })
    .filter(Boolean);
}

export const 預設個人成績簡表版本 = "7.2";

const 個人成績簡表版本索引 = new Map(個人成績簡表版本選項.map((版本, index) => [版本.value, { ...版本, index }]));

function 取得個人成績簡表版本設定(版本) {
  if (typeof 版本 === "string") {
    return 個人成績簡表版本索引.get(版本) || null;
  }
  return 版本 && typeof 版本 === "object" ? 版本 : null;
}

export function 個人成績簡表版本已開放(版本, 目前時間戳記 = Date.now()) {
  const 選項 = 取得個人成績簡表版本設定(版本);
  if (!選項 || 選項.available === false) {
    return false;
  }

  const 開放時間戳記 = new Date(選項.available_from_iso || "").getTime();
  return !Number.isFinite(開放時間戳記) || 開放時間戳記 <= 目前時間戳記;
}

export function 建立個人成績簡表可選版本(目前時間戳記 = Date.now()) {
  return 個人成績簡表版本選項.map((選項) => ({
    ...選項,
    available: 個人成績簡表版本已開放(選項, 目前時間戳記),
  }));
}

export function 正規化個人成績簡表版本(版本) {
  const 選項 = 個人成績簡表版本索引.get(版本);
  return 個人成績簡表版本已開放(選項) ? 選項.value : 預設個人成績簡表版本;
}

export function 取得個人成績簡表版本選項(版本) {
  return 個人成績簡表版本索引.get(正規化個人成績簡表版本(版本)) || 個人成績簡表版本索引.get(預設個人成績簡表版本);
}

export function 副本符合個人成績簡表版本(副本, 版本) {
  const 目標版本 = 取得個人成績簡表版本選項(版本);
  const 首次可見版本 = 個人成績簡表版本索引.get(副本?.profile_summary_available_from);
  const 最後可見版本 = 副本?.profile_summary_available_until
    ? 個人成績簡表版本索引.get(副本.profile_summary_available_until)
    : null;

  // 未帶欄位的舊快取或未知的新版本必須先隱藏，不能錯把後續副本放進早期版本快照。
  // 輪替內容可設定最後可見版本；此欄位只縮小歷史快照的呈現範圍，不會刪除排行榜資料。
  return Boolean(
    目標版本
      && 首次可見版本
      && 首次可見版本.index <= 目標版本.index
      && (!副本?.profile_summary_available_until || (最後可見版本 && 目標版本.index <= 最後可見版本.index)),
  );
}

export function 成績符合個人成績簡表版本(成績, 版本) {
  const 目標版本 = 取得個人成績簡表版本選項(版本);
  const 截止時間 = 目標版本?.record_cutoff_iso ? new Date(目標版本.record_cutoff_iso).getTime() : null;
  if (!Number.isFinite(截止時間)) {
    return true;
  }

  const 紀錄時間 = new Date(成績?.recorded_at_iso || "").getTime();
  // 歷史快照缺少可靠時間時不能假設它屬於舊版，否則新紀錄可能污染既有版本的成績單。
  return Number.isFinite(紀錄時間) && 紀錄時間 < 截止時間;
}

// 個人成績簡表只回答「本站是否已收錄此角色的公開通關」，不應把缺少公開 FFLogs
// 紀錄解讀為玩家尚未通關。副本目標由公開副本清單的領域標記決定，避免前端以
// enabled 推測現行內容；enabled 為保留歷史排行榜而刻意維持 true。
export const 個人成績簡表群組順序 = ["savage", "ultimate", "extreme", "unreal", "chaotic", "current"];

const 個人成績簡表群組資料 = {
  savage: "零式",
  ultimate: "絕本",
  extreme: "極本",
  unreal: "幻本",
  chaotic: "滅本",
  // 保留未來新增的高難分類，避免設定已標記 current_high_end 的副本被前端靜默忽略。
  current: "現行高難",
};

const 目前高難分類群組 = {
  零式: "savage",
  極: "extreme",
  幻: "unreal",
  滅: "chaotic",
};

const 簡表副本顯示名稱 = {
  ultimate_bahamut: "巴哈姆特",
  ultimate_ultima_weapon: "究極神兵",
  ultimate_alexander: "亞歷山大",
  ultimate_dragonsong: "幻想龍詩",
  ultimate_omega: "歐米茄",
  ultimate_futures_rewritten: "伊甸",
  extreme_queen_eternal: "永恆女王",
  unreal_byakko: "白虎",
  unreal_suzaku: "朱雀",
  chaotic_cloud_of_darkness: "黑暗之雲",
};

function 取得個人成績簡表零式量級(副本) {
  const 量級 = 副本?.profile_summary_savage_tier;
  if (
    !量級
    || typeof 量級.key !== "string"
    || typeof 量級.label !== "string"
    || !Number.isInteger(量級.order)
    || 量級.order < 1
    || !Number.isInteger(量級.floor)
    || 量級.floor < 1
    || 量級.floor > 4
  ) {
    return null;
  }

  return 量級;
}

function 取得個人成績簡表副本名稱(副本) {
  if (副本?.category === "零式") {
    const 量級 = 取得個人成績簡表零式量級(副本);
    if (量級) {
      // 量級已由上方大項目標示，樓層改用副本原有的 MxS／首領名稱，
      // 讓「輕量級」與「M1S / 黑貓」分別承擔量級和戰鬥的語意。
      const 零式副本名稱 = String(副本?.name || "").replace(/^零式\s*/, "").trim();
      if (零式副本名稱) {
        return 零式副本名稱;
      }

      return `${量級.label} ${量級.floor}`;
    }
  }

  return 簡表副本顯示名稱[副本?.key] || 副本?.name || "未知副本";
}

export function 是個人成績簡表目標副本(副本) {
  // 絕本與極本需要保留完整歷史通關輪廓；極本即使只剩過版成績，也會以灰色勾勾呈現。
  // 其餘分類才由 current_high_end 限縮為目前高難，避免過版零式、幻本與滅本堆滿簡表。
  return 副本?.category === "絕" || 副本?.category === "極" || 副本?.current_high_end === true;
}

function 取得簡表群組鍵值(副本) {
  if (副本?.category === "絕") {
    return "ultimate";
  }

  return 目前高難分類群組[副本?.category] || "current";
}

function 取得最高有效PR成績(成績列表) {
  let 最高PR成績 = null;

  for (const 成績 of 成績列表) {
    const PR值 = 計算PR值(成績?.performance);
    if (PR值 !== null && (最高PR成績 === null || PR值 > 最高PR成績.pr_value)) {
      最高PR成績 = {
        job: 成績?.job || "",
        pr_value: PR值,
      };
    }
  }

  return 最高PR成績;
}

function 建立副本簡表狀態(副本成績) {
  const 公開成績 = Array.isArray(副本成績?.public_entries) ? 副本成績.public_entries : [];
  if (公開成績.length === 0) {
    return {
      已收錄通關: false,
      狀態: "unrecorded",
      job: "",
      pr_value: null,
    };
  }

  // 過版紀錄的分位數會受裝備品級與可跳過機制影響，不能與當期 PR 並列；
  // 因此只在有有效版本紀錄時顯示該角色跨職業的最高 PR 與對應職業。
  const 有效成績 = 公開成績.filter((成績) => !成績?.is_obsolete_record);
  if (有效成績.length > 0) {
    const PR代表成績 = 取得最高有效PR成績(有效成績);
    return {
      已收錄通關: true,
      狀態: PR代表成績 === null ? "valid-clear" : "pr",
      job: PR代表成績?.job || "",
      pr_value: PR代表成績?.pr_value ?? null,
    };
  }

  return {
    已收錄通關: true,
    狀態: "obsolete-clear",
    job: "",
    pr_value: null,
  };
}

function 是當版本通關狀態(狀態) {
  return 狀態 === "pr" || 狀態 === "valid-clear";
}

function 建立零式量級資料(副本清單, 成績索引, 版本) {
  const 量級索引 = new Map();

  for (const 副本 of Array.isArray(副本清單) ? 副本清單 : []) {
    if (副本?.category !== "零式" || !是個人成績簡表目標副本(副本) || !副本符合個人成績簡表版本(副本, 版本)) {
      continue;
    }

    const 量級 = 取得個人成績簡表零式量級(副本);
    if (!量級) {
      continue;
    }

    let 量級資料 = 量級索引.get(量級.key);
    if (!量級資料) {
      量級資料 = {
        key: 量級.key,
        label: 量級.label,
        order: 量級.order,
        encounters: [],
      };
      量級索引.set(量級.key, 量級資料);
    }

    量級資料.encounters.push({
      key: 副本.key,
      name: 取得個人成績簡表副本名稱(副本),
      sort_order: 量級.floor,
      ...建立副本簡表狀態(成績索引.get(副本.key)),
    });
  }

  return [...量級索引.values()]
    .sort((左, 右) => 左.order - 右.order)
    .map((量級) => {
      const encounters = 量級.encounters.sort((左, 右) => 左.sort_order - 右.sort_order);
      const floors = new Set(encounters.map((副本) => 副本.sort_order));
      return {
        ...量級,
        encounters,
        // 量級進度只認該版本內的有效通關；舊版灰色勾勾不能把量級誤亮成全通。
        is_current_version_complete: floors.size === 4
          && [1, 2, 3, 4].every((樓層) => floors.has(樓層))
          && encounters.every((副本) => 是當版本通關狀態(副本.狀態)),
      };
    });
}

function 取得已選擇零式量級(量級列表, 選擇量級鍵值) {
  if (!Array.isArray(量級列表) || 量級列表.length === 0) {
    return null;
  }

  // 使用者尚未手動選擇、或切換遊戲版本後該量級尚未開放時，預設停在最新量級。
  return 量級列表.find((量級) => 量級.key === 選擇量級鍵值) || 量級列表.at(-1);
}

export function 建立個人成績簡表群組(
  副本清單,
  副本成績,
  版本 = 預設個人成績簡表版本,
  選擇零式量級鍵值 = "",
) {
  const 成績索引 = new Map(
    (Array.isArray(副本成績) ? 副本成績 : [])
      .filter((副本) => 副本?.encounter_key)
      .map((副本) => [副本.encounter_key, 副本]),
  );
  const 群組索引 = new Map(
    個人成績簡表群組順序.map((群組鍵值) => [群組鍵值, {
      key: 群組鍵值,
      name: 個人成績簡表群組資料[群組鍵值],
      encounters: [],
    }]),
  );
  const 零式量級列表 = 建立零式量級資料(副本清單, 成績索引, 版本);
  const 已選擇零式量級 = 取得已選擇零式量級(零式量級列表, 選擇零式量級鍵值);
  const 零式群組 = 群組索引.get("savage");
  if (零式群組 && 已選擇零式量級) {
    零式群組.selected_tier_key = 已選擇零式量級.key;
    零式群組.tiers = 零式量級列表.map(({ encounters, ...量級 }) => 量級);
    零式群組.encounters.push(...已選擇零式量級.encounters);
  }

  for (const 副本 of Array.isArray(副本清單) ? 副本清單 : []) {
    if (
      副本?.category === "零式"
      || !是個人成績簡表目標副本(副本)
      || !副本符合個人成績簡表版本(副本, 版本)
    ) {
      continue;
    }

    const 群組 = 群組索引.get(取得簡表群組鍵值(副本));
    if (!群組) {
      continue;
    }

    群組.encounters.push({
      key: 副本.key,
      name: 取得個人成績簡表副本名稱(副本),
      sort_order: 0,
      ...建立副本簡表狀態(成績索引.get(副本.key)),
    });
  }

  return 個人成績簡表群組順序
    .map((群組鍵值) => {
      const 群組 = 群組索引.get(群組鍵值);
      if (!群組) {
        return null;
      }

      return {
        ...群組,
        encounters: 群組.encounters
          .sort((左, 右) => 左.sort_order - 右.sort_order)
          .map(({ sort_order, ...副本 }) => 副本),
      };
    })
    .filter((群組) => 群組?.encounters.length > 0);
}
