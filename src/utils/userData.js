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

export function 尋找使用者索引條目(使用者索引列表, 角色名稱) {
  const 正規化名稱 = String(角色名稱 || "").trim().toLocaleLowerCase("zh-TW");
  if (!正規化名稱) {
    return null;
  }

  return (
    使用者索引列表.find((使用者) => 使用者.character_name?.toLocaleLowerCase("zh-TW") === 正規化名稱) ||
    null
  );
}

export async function 讀取使用者資料檔(角色名稱, 使用者索引列表) {
  const 查詢名稱 = String(角色名稱 || "").trim();
  const 索引條目 = 尋找使用者索引條目(使用者索引列表, 查詢名稱);
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
