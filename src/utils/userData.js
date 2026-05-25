import { 建立公開資料網址, 建立使用者預設資料網址 } from "./publicData";

export const 玩家搜尋歷史儲存鍵 = "ffxiv-tc-rankings-player-search-history";
export const 玩家搜尋歷史顯示上限 = 8;
export const 玩家搜尋歷史保存上限 = 100;

export function 格式化使用者搜尋文字(角色名稱, 伺服器 = "") {
  const 名稱 = String(角色名稱 || "").trim();
  const 伺服器名稱 = String(伺服器 || "").trim();
  return 伺服器名稱 ? `${名稱} @ ${伺服器名稱}` : 名稱;
}

export function 解析使用者搜尋輸入(輸入文字) {
  const 文字 = String(輸入文字 || "").trim();
  const 分隔結果 = 文字.match(/^(.*?)\s*[@＠]\s*(.+)$/);
  if (!分隔結果) {
    return {
      角色名稱: 文字,
      伺服器: "",
    };
  }

  return {
    角色名稱: 分隔結果[1].trim(),
    伺服器: 分隔結果[2].trim(),
  };
}

function 正規化使用者查詢文字(文字) {
  return String(文字 || "").trim().toLocaleLowerCase("zh-TW");
}

function 使用者搜尋歷史鍵(紀錄) {
  if (!紀錄?.character_name) {
    return "";
  }

  return `${正規化使用者查詢文字(紀錄?.character_name)}@${正規化使用者查詢文字(紀錄?.server)}`;
}

function 正規化搜尋時間Iso(時間) {
  const 日期 = 時間 instanceof Date ? 時間 : new Date(時間 || "");
  return Number.isNaN(日期.getTime()) ? "" : 日期.toISOString();
}

function 取得瀏覽器儲存(storage = null) {
  if (storage) {
    return storage;
  }

  if (typeof window === "undefined") {
    return null;
  }

  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function 正規化玩家搜尋歷史紀錄(紀錄) {
  if (typeof 紀錄 === "string") {
    const 查詢 = 解析使用者搜尋輸入(紀錄);
    if (!查詢.角色名稱) {
      return null;
    }

    return {
      character_name: 查詢.角色名稱,
      server: 查詢.伺服器,
      value: 格式化使用者搜尋文字(查詢.角色名稱, 查詢.伺服器),
      searched_at_iso: "",
    };
  }

  const 角色名稱 = String(紀錄?.character_name || 紀錄?.角色名稱 || 紀錄?.name || "").trim();
  const 伺服器 = String(紀錄?.server || 紀錄?.伺服器 || "").trim();
  if (!角色名稱) {
    return null;
  }

  return {
    character_name: 角色名稱,
    server: 伺服器,
    value: 格式化使用者搜尋文字(角色名稱, 伺服器),
    searched_at_iso: 正規化搜尋時間Iso(紀錄?.searched_at_iso || 紀錄?.searched_at || 紀錄?.searchedAt || 紀錄?.搜尋時間),
  };
}

export function 正規化玩家搜尋歷史列表(列表) {
  const 已收錄 = new Set();
  const 正規化列表 = [];

  for (const 原始紀錄 of Array.isArray(列表) ? 列表 : []) {
    const 紀錄 = 正規化玩家搜尋歷史紀錄(原始紀錄);
    const 鍵值 = 使用者搜尋歷史鍵(紀錄);
    if (!紀錄 || !鍵值 || 已收錄.has(鍵值)) {
      continue;
    }

    已收錄.add(鍵值);
    正規化列表.push(紀錄);
    if (正規化列表.length >= 玩家搜尋歷史保存上限) {
      break;
    }
  }

  return 正規化列表;
}

export function 讀取玩家搜尋歷史(storage = null) {
  const 儲存 = 取得瀏覽器儲存(storage);
  if (!儲存) {
    return [];
  }

  try {
    const 原始資料 = 儲存.getItem(玩家搜尋歷史儲存鍵);
    if (!原始資料) {
      return [];
    }

    return 正規化玩家搜尋歷史列表(JSON.parse(原始資料));
  } catch {
    return [];
  }
}

export function 寫入玩家搜尋歷史(列表, storage = null) {
  const 正規化列表 = 正規化玩家搜尋歷史列表(列表);
  const 儲存 = 取得瀏覽器儲存(storage);
  if (!儲存) {
    return 正規化列表;
  }

  try {
    儲存.setItem(玩家搜尋歷史儲存鍵, JSON.stringify(正規化列表));
  } catch {
    // localStorage 可能因瀏覽器隱私設定或容量限制不可寫；此功能只是 UI 便利性，不應影響搜尋主流程。
  }

  return 正規化列表;
}

export function 新增玩家搜尋歷史(紀錄, storage = null, 搜尋時間 = new Date()) {
  const 正規化紀錄 = 正規化玩家搜尋歷史紀錄(紀錄);
  if (!正規化紀錄) {
    return 讀取玩家搜尋歷史(storage);
  }

  return 寫入玩家搜尋歷史(
    [
      {
        ...正規化紀錄,
        searched_at_iso: 正規化搜尋時間Iso(搜尋時間) || new Date().toISOString(),
      },
      ...讀取玩家搜尋歷史(storage),
    ],
    storage,
  );
}

export function 刪除玩家搜尋歷史(紀錄, storage = null) {
  const 正規化紀錄 = 正規化玩家搜尋歷史紀錄(紀錄);
  const 刪除鍵值 = 使用者搜尋歷史鍵(正規化紀錄);
  if (!刪除鍵值) {
    return 讀取玩家搜尋歷史(storage);
  }

  return 寫入玩家搜尋歷史(
    讀取玩家搜尋歷史(storage).filter((現有紀錄) => 使用者搜尋歷史鍵(現有紀錄) !== 刪除鍵值),
    storage,
  );
}

export function 清除玩家搜尋歷史(storage = null) {
  const 儲存 = 取得瀏覽器儲存(storage);
  if (儲存) {
    try {
      if (typeof 儲存.removeItem === "function") {
        儲存.removeItem(玩家搜尋歷史儲存鍵);
      } else {
        儲存.setItem(玩家搜尋歷史儲存鍵, "[]");
      }
    } catch {
      // 清除失敗時維持畫面狀態同步為空，避免管理彈窗看起來沒有回應。
    }
  }

  return [];
}

function 合併唯一伺服器列表(...伺服器列表群組) {
  const 已收錄 = new Set();
  const 結果 = [];

  for (const 伺服器列表 of 伺服器列表群組) {
    for (const 原始伺服器 of Array.isArray(伺服器列表) ? 伺服器列表 : []) {
      const 伺服器 = String(原始伺服器 || "").trim();
      const 鍵值 = 正規化使用者查詢文字(伺服器);
      if (!鍵值 || 已收錄.has(鍵值)) {
        continue;
      }
      已收錄.add(鍵值);
      結果.push(伺服器);
    }
  }

  return 結果;
}

export function 取得使用者主要伺服器(使用者) {
  const canonicalServer = String(使用者?.canonical_server || "").trim();
  if (canonicalServer) {
    return canonicalServer;
  }

  return 合併唯一伺服器列表(使用者?.servers)[0] || "";
}

export function 取得使用者伺服器列表(使用者) {
  return 合併唯一伺服器列表(
    [取得使用者主要伺服器(使用者)],
    使用者?.servers,
    使用者?.server_aliases,
  );
}

function 尋找索引內伺服器(伺服器列表, 查詢伺服器) {
  const 正規化伺服器 = 正規化使用者查詢文字(查詢伺服器);
  if (!正規化伺服器) {
    return "";
  }

  return 伺服器列表.find((伺服器) => 正規化使用者查詢文字(伺服器) === 正規化伺服器) || "";
}

export function 尋找使用者索引條目(使用者索引列表, 角色名稱, 伺服器 = "") {
  const 查詢 = 解析使用者搜尋輸入(角色名稱);
  const 正規化名稱 = 正規化使用者查詢文字(查詢.角色名稱);
  const 正規化伺服器 = 正規化使用者查詢文字(伺服器 || 查詢.伺服器);
  const 索引列表 = Array.isArray(使用者索引列表) ? 使用者索引列表 : [];
  if (!正規化名稱) {
    return null;
  }

  return (
    索引列表.find((使用者) => {
      if (正規化使用者查詢文字(使用者.character_name) !== 正規化名稱) {
        return false;
      }

      if (!正規化伺服器) {
        return true;
      }

      return 取得使用者伺服器列表(使用者).some((索引伺服器) => 正規化使用者查詢文字(索引伺服器) === 正規化伺服器);
    }) ||
    null
  );
}

export function 解析使用者搜尋目標(輸入文字, 使用者索引列表, 預設伺服器 = "") {
  const 查詢 = 解析使用者搜尋輸入(輸入文字);
  const 查詢伺服器 = 預設伺服器 || 查詢.伺服器;
  const 索引條目 = 尋找使用者索引條目(使用者索引列表, 查詢.角色名稱, 查詢伺服器);
  const 伺服器列表 = 取得使用者伺服器列表(索引條目);
  const 主要伺服器 = 取得使用者主要伺服器(索引條目);
  const 索引伺服器 = 尋找索引內伺服器(伺服器列表, 查詢伺服器);

  // 遊戲允許不同伺服器存在同名角色；若查詢有指定伺服器，必須優先保留該身分，
  // 避免「同名但不同人」被導到純名稱搜尋時命中的第一筆索引。
  return {
    角色名稱: 索引條目?.character_name || 查詢.角色名稱,
    伺服器: 索引伺服器 || 主要伺服器 || 伺服器列表[0] || 查詢伺服器 || "",
    索引條目,
  };
}

async function 讀取使用者Json(資料網址, 錯誤訊息) {
  const 回應 = await fetch(資料網址, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!回應.ok) {
    throw new Error(錯誤訊息);
  }

  return 回應.json();
}

function 複製資料(資料) {
  return JSON.parse(JSON.stringify(資料 || {}));
}

function 合併使用者副本差量(公開副本, 差量副本) {
  const 合併後 = {
    ...公開副本,
    encounter_key: 差量副本.encounter_key || 公開副本.encounter_key,
    encounter_name: 差量副本.encounter_name || 公開副本.encounter_name,
    encounter_category: 差量副本.encounter_category ?? 公開副本.encounter_category ?? null,
    updated_at_iso: 差量副本.updated_at_iso ?? 公開副本.updated_at_iso ?? null,
    best_entry: 差量副本.best_entry ?? 公開副本.best_entry ?? null,
    best_by_job: Array.isArray(差量副本.best_by_job) ? 差量副本.best_by_job : 公開副本.best_by_job || [],
  };
  const 成績索引 = new Map();
  for (const 成績 of 公開副本.public_entries || []) {
    if (成績?.id) {
      成績索引.set(成績.id, 成績);
    }
  }
  for (const 成績 of 差量副本.public_entries || []) {
    if (成績?.id) {
      成績索引.set(成績.id, 成績);
    }
  }

  const 排序後 = [];
  const 已使用 = new Set();
  for (const id of 差量副本.public_entry_order || []) {
    const 成績 = 成績索引.get(id);
    if (成績) {
      排序後.push(成績);
      已使用.add(id);
    }
  }
  if (Array.isArray(差量副本.public_entry_order) && 差量副本.public_entry_order.length > 0) {
    合併後.public_entries = 排序後;
    return 合併後;
  }
  for (const 成績 of [...(公開副本.public_entries || []), ...(差量副本.public_entries || [])]) {
    if (成績?.id && !已使用.has(成績.id)) {
      排序後.push(成績);
      已使用.add(成績.id);
    }
  }
  合併後.public_entries = 排序後;
  return 合併後;
}

async function 解析使用者隱藏差量(差量資料) {
  if (差量資料?.format !== "user_profile_hidden_delta_v1") {
    return 差量資料;
  }

  const 公開底稿 = 差量資料.base_path
    ? await 讀取使用者Json(建立公開資料網址(差量資料.base_path), "找不到公開個人成績單底稿").catch(() => null)
    : null;
  const 合併後 = {
    ...複製資料(公開底稿),
    schema_version: 1,
    generated_at_iso: 差量資料.generated_at_iso,
    character_name: 差量資料.character_name || 公開底稿?.character_name || "",
    canonical_server: 差量資料.canonical_server ?? 公開底稿?.canonical_server ?? null,
    servers: Array.isArray(差量資料.servers) ? 差量資料.servers : 公開底稿?.servers || [],
    server_aliases: Array.isArray(差量資料.server_aliases) ? 差量資料.server_aliases : 公開底稿?.server_aliases || [],
    summary: 差量資料.summary || 公開底稿?.summary || {},
    frequent_teammates: Array.isArray(差量資料.frequent_teammates)
      ? 差量資料.frequent_teammates
      : 公開底稿?.frequent_teammates || [],
  };

  const 副本索引 = new Map((公開底稿?.encounters || []).map((副本) => [副本.encounter_key, 複製資料(副本)]));
  for (const 差量副本 of 差量資料.encounters || []) {
    if (!差量副本?.encounter_key) {
      continue;
    }
    const 公開副本 = 副本索引.get(差量副本.encounter_key) || {
      encounter_key: 差量副本.encounter_key,
      encounter_name: 差量副本.encounter_name || 差量副本.encounter_key,
      encounter_category: 差量副本.encounter_category ?? null,
      updated_at_iso: 差量副本.updated_at_iso ?? null,
      best_entry: null,
      best_by_job: [],
      public_entries: [],
    };
    副本索引.set(差量副本.encounter_key, 合併使用者副本差量(公開副本, 差量副本));
  }

  const 排序後副本 = [];
  const 已加入副本 = new Set();
  for (const 副本鍵值 of 差量資料.encounter_order || []) {
    const 副本 = 副本索引.get(副本鍵值);
    if (副本) {
      排序後副本.push(副本);
      已加入副本.add(副本鍵值);
    }
  }
  for (const 副本 of 副本索引.values()) {
    if (!已加入副本.has(副本.encounter_key)) {
      排序後副本.push(副本);
    }
  }
  合併後.encounters = 排序後副本;
  return 合併後;
}

export async function 讀取使用者資料檔(角色名稱, 使用者索引列表, 伺服器 = "") {
  const 搜尋目標 = 解析使用者搜尋目標(角色名稱, 使用者索引列表, 伺服器);
  const 查詢名稱 = String(搜尋目標.角色名稱 || "").trim();
  const 查詢顯示名稱 = 格式化使用者搜尋文字(查詢名稱, 搜尋目標.伺服器);
  const 索引條目 = 搜尋目標.索引條目;
  if (!索引條目 && 搜尋目標.伺服器) {
    throw new Error(`找不到「${查詢顯示名稱}」的個人成績單`);
  }

  const 資料網址 = 索引條目?.file_path ? 建立公開資料網址(索引條目.file_path) : 建立使用者預設資料網址(查詢名稱);
  const 資料 = await 讀取使用者Json(資料網址, `找不到「${查詢顯示名稱 || 查詢名稱}」的個人成績單`);
  return 解析使用者隱藏差量(資料);
}
