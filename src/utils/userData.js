import { 建立公開資料網址, 建立使用者預設資料網址 } from "./publicData";

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

function 取得使用者伺服器列表(使用者) {
  return Array.isArray(使用者?.servers) ? 使用者.servers : [];
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
  const 索引伺服器 = 尋找索引內伺服器(伺服器列表, 查詢伺服器);

  // 玩家名稱在目前公開索引中視為唯一值；純名稱查詢先落到 users/index.json，
  // 再補上 canonical 伺服器，避免表單沒有選 datalist 時走到不穩定的檔名 fallback。
  return {
    角色名稱: 索引條目?.character_name || 查詢.角色名稱,
    伺服器: 索引伺服器 || 伺服器列表[0] || 查詢伺服器 || "",
    索引條目,
  };
}

export async function 讀取使用者資料檔(角色名稱, 使用者索引列表) {
  const 搜尋目標 = 解析使用者搜尋目標(角色名稱, 使用者索引列表);
  const 查詢名稱 = String(搜尋目標.角色名稱 || "").trim();
  const 索引條目 = 搜尋目標.索引條目;
  const 資料網址 = 索引條目?.file_path ? 建立公開資料網址(索引條目.file_path) : 建立使用者預設資料網址(查詢名稱);
  const 回應 = await fetch(資料網址, {
    headers: {
      Accept: "application/json",
    },
  });

  if (!回應.ok) {
    throw new Error(`找不到「${查詢名稱}」的個人成績單`);
  }

  return 回應.json();
}
