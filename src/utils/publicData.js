// 前端只讀取 Vite 打包後位於 public/data 的靜態 JSON。
// 這裡集中處理公開資料 URL，避免頁面或 composable 各自拼接路徑時漏掉 base path。
const 公開資料基底路徑 = import.meta.env?.BASE_URL ?? "/";

export const 副本清單網址 = `${公開資料基底路徑}data/encounters.json`;
export const 使用者索引網址 = `${公開資料基底路徑}data/users/index.json`;
export const 全服統計網址 = `${公開資料基底路徑}data/global_stats.json`;
export const 近期動態網址 = `${公開資料基底路徑}data/activity.json`;
export const 隊伍榜網址 = `${公開資料基底路徑}data/team_rankings.json`;
export const 伺服器對比網址 = `${公開資料基底路徑}data/server_compare.json`;
export const 公告資料網址 = `${公開資料基底路徑}data/announcements.json`;

export function 建立公開資料網址(相對路徑) {
  return `${公開資料基底路徑}${String(相對路徑)
    .split("/")
    .map((片段) => encodeURIComponent(片段))
    .join("/")}`;
}

export function 建立使用者預設資料網址(角色名稱) {
  return 建立公開資料網址(`data/users/${角色名稱}.json`);
}

export function 建立排行榜表格資料網址(副本鍵值) {
  return 建立公開資料網址(`data/ranking-tables/${副本鍵值}.json`);
}
