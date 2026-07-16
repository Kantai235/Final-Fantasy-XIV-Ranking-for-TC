import { 計算PR值 } from "./formatters.js";

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
  savage_m1s: "輕量級 1",
  savage_m2s: "輕量級 2",
  savage_m3s: "輕量級 3",
  savage_m4s: "輕量級 4",
  ultimate_bahamut: "巴哈姆特",
  ultimate_ultima_weapon: "究極神兵",
  ultimate_alexander: "亞歷山大",
  ultimate_dragonsong: "幻想龍詩",
  ultimate_omega: "歐米茄",
  ultimate_futures_rewritten: "伊甸",
  extreme_queen_eternal: "永恆女王",
  unreal_byakko: "白虎",
  chaotic_cloud_of_darkness: "黑暗之雲",
};

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

export function 建立個人成績簡表群組(副本清單, 副本成績) {
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

  for (const 副本 of Array.isArray(副本清單) ? 副本清單 : []) {
    if (!是個人成績簡表目標副本(副本)) {
      continue;
    }

    const 群組 = 群組索引.get(取得簡表群組鍵值(副本));
    if (!群組) {
      continue;
    }

    群組.encounters.push({
      key: 副本.key,
      name: 簡表副本顯示名稱[副本.key] || 副本.name,
      ...建立副本簡表狀態(成績索引.get(副本.key)),
    });
  }

  return 個人成績簡表群組順序
    .map((群組鍵值) => 群組索引.get(群組鍵值))
    .filter((群組) => 群組?.encounters.length > 0);
}
