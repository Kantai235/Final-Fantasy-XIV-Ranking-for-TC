// 前端仍維持靜態 JSON 邊界：主站資料由 Pages artifact 的 /data 提供，
// 個人成績單資料則由專用 users repo 提供，避免大型使用者 JSON 撐大主站 artifact。
// 這裡集中處理兩種資料 URL，避免頁面或 composable 各自拼接路徑時漏掉 base path 或外部 repo 基底。
const Vite公開基底路徑 = import.meta.env?.BASE_URL ?? "/";

const 乾淨路由片段 = new Set(["stats", "user", "compare", "jobs", "activity", "teams", "servers", "honey-fans"]);

const DEFAULT_USER_DATA_BASE_URL =
  "https://raw.githubusercontent.com/Kantai235/Final-Fantasy-XIV-Ranking-for-TC-Users/refs/heads/main/";

function 取得使用者資料基底() {
  const 自訂網址 = String(import.meta.env?.VITE_USER_DATA_BASE_URL || "").trim();
  return 補結尾斜線(自訂網址 || DEFAULT_USER_DATA_BASE_URL);
}

function 補結尾斜線(路徑) {
  const 文字 = String(路徑 || "/").trim();
  return 文字.endsWith("/") ? 文字 : `${文字}/`;
}

function 安全解碼路徑片段(片段) {
  try {
    return decodeURIComponent(片段);
  } catch {
    return 片段;
  }
}

function 編碼路徑片段(片段) {
  return encodeURIComponent(String(片段 || "").trim());
}

function 解析路徑片段(pathname) {
  return String(pathname || "")
    .split("/")
    .map((片段) => 安全解碼路徑片段(片段))
    .filter(Boolean);
}

function 推導目前路由基底(pathname) {
  const 片段列表 = 解析路徑片段(pathname);
  const 路由索引 = 片段列表.findIndex((片段) => 乾淨路由片段.has(片段));

  if (路由索引 >= 0) {
    // Vite base_path 使用 "./" 時，直接開啟 /user/ 這類乾淨路由會讓相對 URL 指到 /user/data。
    // 因此公開資料要以 route 片段以前的部署根目錄為準；子路徑部署則保留 /repo/ 這段。
    const 基底片段 = 片段列表.slice(0, 路由索引).map((片段) => 編碼路徑片段(片段));
    return 基底片段.length > 0 ? `/${基底片段.join("/")}/` : "/";
  }

  const 路徑 = String(pathname || "/");
  if (路徑.endsWith("/")) {
    return 路徑;
  }

  const 最後斜線 = 路徑.lastIndexOf("/");
  return 最後斜線 >= 0 ? 路徑.slice(0, 最後斜線 + 1) : "/";
}

function 取得公開資料基底路徑() {
  const 設定值 = String(Vite公開基底路徑 || "/").trim();
  if (!設定值 || 設定值 === "." || 設定值 === "./") {
    return typeof window === "undefined" ? "/" : 推導目前路由基底(window.location?.pathname || "/");
  }

  if (/^[a-z][a-z\d+.-]*:\/\//i.test(設定值)) {
    return 補結尾斜線(new URL(設定值).pathname || "/");
  }

  if (設定值.startsWith("/")) {
    return 補結尾斜線(設定值);
  }

  return 補結尾斜線(設定值);
}

const 公開資料基底路徑 = 取得公開資料基底路徑();
const 使用者資料基底路徑 = 取得使用者資料基底();

export const 副本清單網址 = `${公開資料基底路徑}data/encounters.json`;
export const 使用者索引網址 = `${使用者資料基底路徑}data/users/index.json`;
export const 全服統計網址 = `${公開資料基底路徑}data/global_stats.json`;
export const 近期動態網址 = `${公開資料基底路徑}data/activity.json`;
export const 隊伍榜網址 = `${公開資料基底路徑}data/team_rankings.json`;
export const 伺服器對比網址 = `${公開資料基底路徑}data/server_compare.json`;
export const 蜂蜜粉絲榜網址 = `${公開資料基底路徑}data/fun/honey_b_fans.json`;
export const 蜂蜂粉絲榜網址 = 蜂蜜粉絲榜網址;
export const 公告資料網址 = `${公開資料基底路徑}data/announcements.json`;

export function 建立公開資料網址(相對路徑) {
  return `${公開資料基底路徑}${String(相對路徑)
    .split("/")
    .map((片段) => encodeURIComponent(片段))
    .join("/")}`;
}

export function 建立使用者資料網址(相對路徑) {
  return `${使用者資料基底路徑}${String(相對路徑)
    .split("/")
    .map((片段) => encodeURIComponent(片段))
    .join("/")}`;
}

export function 建立使用者預設資料網址(角色名稱) {
  return 建立使用者資料網址(`data/users/${角色名稱}.json`);
}

export function 建立排行榜表格資料網址(副本鍵值) {
  return 建立公開資料網址(`data/ranking-tables/${副本鍵值}.json`);
}
