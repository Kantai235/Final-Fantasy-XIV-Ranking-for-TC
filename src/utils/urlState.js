import { 分享網址變更事件 } from "./shareMeta";

export const 可分享頁面模式 = new Set(["ranking", "stats", "user", "compare", "jobs", "activity", "teams", "servers", "honey-fans"]);

const 頁面路徑片段 = {
  ranking: "",
  stats: "stats",
  user: "user",
  compare: "compare",
  jobs: "jobs",
  activity: "activity",
  teams: "teams",
  servers: "servers",
  "honey-fans": "honey-fans",
};

const 路徑片段頁面 = new Map(
  Object.entries(頁面路徑片段)
    .filter(([, 片段]) => 片段)
    .map(([頁面, 片段]) => [片段, 頁面]),
);

// 這份清單是分享網址的「可寫入狀態」白名單。寫入新網址前會先清掉這些舊參數，
// 再依頁面重新寫入需要的欄位，避免使用者從排行榜切到職業分析時殘留無關 query。
const 可分享參數 = [
  "page",
  "encounter",
  "server",
  "jobType",
  "job",
  "q",
  "sort",
  "order",
  "pageNo",
  "name",
  "user",
  "left",
  "right",
  "role",
  "jobScope",
  "split",
  "metric",
  "version",
];

function 讀取瀏覽器網址() {
  if (typeof window === "undefined") {
    return null;
  }

  return new URL(window.location.href);
}

function 讀取參數文字(參數, 名稱) {
  return String(參數.get(名稱) || "").trim();
}

function 最後路徑片段(pathname) {
  return 解析路徑片段(pathname).at(-1) || "";
}

function 安全解碼路徑片段(片段) {
  try {
    return decodeURIComponent(片段);
  } catch {
    return 片段;
  }
}

function 解析路徑片段(pathname) {
  return String(pathname || "")
    .split("/")
    .map((片段) => 安全解碼路徑片段(片段))
    .filter(Boolean);
}

function 尋找路徑頁面索引(pathname) {
  const 片段列表 = 解析路徑片段(pathname);
  const 頁面索引 = 片段列表.findIndex((片段) => 路徑片段頁面.has(片段));

  return {
    片段列表,
    頁面索引,
  };
}

function 取得目前路由基底(pathname) {
  const 路徑 = String(pathname || "/");
  const { 片段列表, 頁面索引 } = 尋找路徑頁面索引(路徑);
  if (頁面索引 >= 0) {
    // GitHub Pages 可能部署在子路徑，例如 /repo/stats/savage_m1s。
    // 這裡保留 route 片段以前的路徑，後續寫入 /jobs/Paladin 時才不會跳回根目錄。
    const 基底片段 = 片段列表.slice(0, 頁面索引).map((片段) => encodeURIComponent(片段));
    return 基底片段.length > 0 ? `/${基底片段.join("/")}/` : "/";
  }

  if (路徑.endsWith("/")) {
    return 路徑;
  }

  const 末段 = 最後路徑片段(路徑);
  // 若使用者直接開 index.html，後續切頁仍應回到同一個資料夾底下。
  if (末段.toLocaleLowerCase("en-US") === "index.html") {
    return 路徑.slice(0, 路徑.lastIndexOf("/") + 1) || "/";
  }

  return 路徑.slice(0, 路徑.lastIndexOf("/") + 1) || "/";
}

function 讀取路徑頁面(網址) {
  const { 片段列表, 頁面索引 } = 尋找路徑頁面索引(網址?.pathname || "");
  if (頁面索引 >= 0) {
    return 路徑片段頁面.get(片段列表[頁面索引]) || "";
  }

  return "";
}

function 讀取路徑使用者(網址) {
  const { 片段列表, 頁面索引 } = 尋找路徑頁面索引(網址?.pathname || "");
  if (頁面索引 < 0 || 路徑片段頁面.get(片段列表[頁面索引]) !== "user") {
    return "";
  }

  return String(片段列表[頁面索引 + 1] || "").trim();
}

function 讀取路徑單一選項(網址, 頁面模式) {
  const { 片段列表, 頁面索引 } = 尋找路徑頁面索引(網址?.pathname || "");
  if (頁面索引 < 0 || 路徑片段頁面.get(片段列表[頁面索引]) !== 頁面模式) {
    return "";
  }

  return String(片段列表[頁面索引 + 1] || "").trim();
}

function 讀取路徑伺服器對比(網址) {
  const { 片段列表, 頁面索引 } = 尋找路徑頁面索引(網址?.pathname || "");
  if (頁面索引 < 0 || 路徑片段頁面.get(片段列表[頁面索引]) !== "servers") {
    return { left: "", right: "" };
  }

  const left = String(片段列表[頁面索引 + 1] || "").trim();
  const vs = String(片段列表[頁面索引 + 2] || "").trim().toLocaleLowerCase("en-US");
  const right = String(片段列表[頁面索引 + 3] || "").trim();
  if (vs !== "vs") {
    return { left: "", right: "" };
  }

  return { left, right };
}

function 正規化頁面模式(頁面模式, 參數 = null) {
  const 模式 = String(頁面模式 || "").trim();
  if (可分享頁面模式.has(模式)) {
    return 模式;
  }

  // 相容舊版 query 分享：?page=user 或只有 ?user= 的連結仍可直接打開。
  const 舊版頁面 = String(參數?.get("page") || "").trim();
  if (可分享頁面模式.has(舊版頁面)) {
    return 舊版頁面;
  }
  if (參數?.get("user") || 參數?.get("name")) {
    return "user";
  }

  return "ranking";
}

export function 讀取目前網址狀態() {
  const 網址 = 讀取瀏覽器網址();
  const 參數 = 網址?.searchParams || new URLSearchParams();
  const 頁面 = 正規化頁面模式(讀取路徑頁面(網址), 參數);
  const 路徑使用者 = 讀取路徑使用者(網址);
  const 路徑副本 = 讀取路徑單一選項(網址, "stats");
  const 路徑職業 = 讀取路徑單一選項(網址, "jobs");
  const 路徑伺服器對比 = 讀取路徑伺服器對比(網址);

  return {
    page: 頁面,
    encounter: 路徑副本 || 讀取參數文字(參數, "encounter"),
    server: 讀取參數文字(參數, "server"),
    jobType: 讀取參數文字(參數, "jobType"),
    job: 路徑職業 || 讀取參數文字(參數, "job"),
    q: 讀取參數文字(參數, "q"),
    sort: 讀取參數文字(參數, "sort"),
    order: 讀取參數文字(參數, "order"),
    pageNo: 讀取參數文字(參數, "pageNo"),
    user: 路徑使用者 || 讀取參數文字(參數, "name") || 讀取參數文字(參數, "user"),
    left: 路徑伺服器對比.left || 讀取參數文字(參數, "left"),
    right: 路徑伺服器對比.right || 讀取參數文字(參數, "right"),
    role: 讀取參數文字(參數, "role"),
    jobScope: 讀取參數文字(參數, "jobScope"),
    split: 讀取參數文字(參數, "split"),
    metric: 讀取參數文字(參數, "metric"),
    version: 讀取參數文字(參數, "version"),
  };
}

function 寫入參數(參數, 名稱, 值) {
  const 文字 = String(值 ?? "").trim();
  if (文字) {
    參數.set(名稱, 文字);
  }
}

function 寫入頁面專屬參數(參數, 狀態) {
  if (狀態.page === "ranking") {
    寫入參數(參數, "encounter", 狀態.encounter);
    寫入參數(參數, "server", 狀態.server);
    寫入參數(參數, "jobType", 狀態.jobType);
    寫入參數(參數, "job", 狀態.job);
    寫入參數(參數, "q", 狀態.q);
    寫入參數(參數, "sort", 狀態.sort);
    寫入參數(參數, "order", 狀態.order);
    寫入參數(參數, "pageNo", 狀態.pageNo);
    寫入參數(參數, "version", 狀態.version);
    return;
  }

  if (狀態.page === "stats") {
    // encounter 會寫入 /stats/{encounterKey}，query 只保留伺服器、分群與指標等細部篩選。
    寫入參數(參數, "server", 狀態.server);
    寫入參數(參數, "jobScope", 狀態.jobScope);
    寫入參數(參數, "split", 狀態.split);
    寫入參數(參數, "metric", 狀態.metric);
    寫入參數(參數, "version", 狀態.version);
    return;
  }

  if (狀態.page === "user") {
    // 玩家名稱放在 /user/{characterName}，server 保留 query 是為了處理同名或跨伺服器角色。
    寫入參數(參數, "server", 狀態.server);
    return;
  }

  if (狀態.page === "compare") {
    寫入參數(參數, "left", 狀態.left);
    寫入參數(參數, "right", 狀態.right);
    寫入參數(參數, "role", 狀態.role);
    寫入參數(參數, "encounter", 狀態.encounter);
    寫入參數(參數, "version", 狀態.version);
    return;
  }

  if (狀態.page === "jobs") {
    // 單一職業使用 /jobs/{job}；職能範圍則寫入 jobScope，
    // 避免把 role:* 放進路徑後和既有 /jobs/{job} 語意混在一起。
    寫入參數(參數, "jobScope", 狀態.jobScope);
    return;
  }

  if (狀態.page === "teams") {
    寫入參數(參數, "encounter", 狀態.encounter);
    寫入參數(參數, "version", 狀態.version);
    return;
  }

  if (狀態.page === "servers") {
    // 伺服器左右欄位放在 /servers/{left}/vs/{right}，讓社群爬蟲能讀到配對專屬 HTML。
    return;
  }
}

function 編碼路徑值(值) {
  return encodeURIComponent(String(值 || "").trim());
}

function 建立頁面路徑(目前路徑, 狀態) {
  const 基底 = 取得目前路由基底(目前路徑);
  const 片段 = 頁面路徑片段[狀態.page] || "";
  if (!片段) {
    return 基底;
  }

  if (狀態.page === "user" && String(狀態.user || "").trim()) {
    return `${基底}${片段}/${編碼路徑值(狀態.user)}`;
  }

  if (狀態.page === "stats" && String(狀態.encounter || "").trim()) {
    return `${基底}${片段}/${編碼路徑值(狀態.encounter)}`;
  }

  if (狀態.page === "jobs" && String(狀態.job || "").trim()) {
    return `${基底}${片段}/${編碼路徑值(狀態.job)}`;
  }

  if (狀態.page === "servers" && String(狀態.left || "").trim() && String(狀態.right || "").trim()) {
    return `${基底}${片段}/${編碼路徑值(狀態.left)}/vs/${編碼路徑值(狀態.right)}`;
  }

  return `${基底}${片段}`;
}

export function 寫入網址狀態(下一個狀態, 選項 = {}) {
  const 網址 = 讀取瀏覽器網址();
  if (!網址 || !window.history) {
    return;
  }

  const 狀態 = {
    ...下一個狀態,
    page: 正規化頁面模式(下一個狀態?.page),
  };

  for (const 名稱 of 可分享參數) {
    網址.searchParams.delete(名稱);
  }

  網址.pathname = 建立頁面路徑(網址.pathname, 狀態);
  寫入頁面專屬參數(網址.searchParams, 狀態);

  const 目前網址 = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const 目標網址 = `${網址.pathname}${網址.search}${網址.hash}`;
  if (目標網址 === 目前網址) {
    return;
  }

  const 方法 = 選項.replace ? "replaceState" : "pushState";
  window.history[方法](null, "", 網址);
  // History API 不會自動送出 popstate；自訂事件讓 SEO/OG meta 與分享按鈕能同步到最新網址。
  window.dispatchEvent(new CustomEvent(分享網址變更事件));
}
