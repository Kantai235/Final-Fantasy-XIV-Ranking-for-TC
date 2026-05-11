export const 可分享頁面模式 = new Set(["ranking", "stats", "user", "compare", "jobs", "activity"]);

const 頁面路徑片段 = {
  ranking: "",
  stats: "stats",
  user: "user",
  compare: "compare",
  jobs: "jobs",
  activity: "activity",
};

const 路徑片段頁面 = new Map(
  Object.entries(頁面路徑片段)
    .filter(([, 片段]) => 片段)
    .map(([頁面, 片段]) => [片段, 頁面]),
);

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
  const 片段列表 = String(pathname || "")
    .split("/")
    .map((片段) => decodeURIComponent(片段))
    .filter(Boolean);
  return 片段列表.at(-1) || "";
}

function 取得目前路由基底(pathname) {
  const 路徑 = String(pathname || "/");
  const 末段 = 最後路徑片段(路徑);
  if (路徑片段頁面.has(末段)) {
    const 去除尾端斜線 = 路徑.replace(/\/+$/, "");
    return 去除尾端斜線.slice(0, 去除尾端斜線.lastIndexOf("/") + 1) || "/";
  }

  if (路徑.endsWith("/")) {
    return 路徑;
  }

  // 若使用者直接開 index.html，後續切頁仍應回到同一個資料夾底下。
  if (末段.toLocaleLowerCase("en-US") === "index.html") {
    return 路徑.slice(0, 路徑.lastIndexOf("/") + 1) || "/";
  }

  return 路徑.slice(0, 路徑.lastIndexOf("/") + 1) || "/";
}

function 讀取路徑頁面(網址) {
  const 末段 = 最後路徑片段(網址?.pathname || "");
  return 路徑片段頁面.get(末段) || "";
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

  return {
    page: 頁面,
    encounter: 讀取參數文字(參數, "encounter"),
    server: 讀取參數文字(參數, "server"),
    jobType: 讀取參數文字(參數, "jobType"),
    job: 讀取參數文字(參數, "job"),
    q: 讀取參數文字(參數, "q"),
    sort: 讀取參數文字(參數, "sort"),
    order: 讀取參數文字(參數, "order"),
    pageNo: 讀取參數文字(參數, "pageNo"),
    user: 讀取參數文字(參數, "name") || 讀取參數文字(參數, "user"),
    left: 讀取參數文字(參數, "left"),
    right: 讀取參數文字(參數, "right"),
    role: 讀取參數文字(參數, "role"),
    jobScope: 讀取參數文字(參數, "jobScope"),
    split: 讀取參數文字(參數, "split"),
    metric: 讀取參數文字(參數, "metric"),
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
    return;
  }

  if (狀態.page === "stats") {
    寫入參數(參數, "encounter", 狀態.encounter);
    寫入參數(參數, "server", 狀態.server);
    寫入參數(參數, "jobScope", 狀態.jobScope);
    寫入參數(參數, "split", 狀態.split);
    寫入參數(參數, "metric", 狀態.metric);
    return;
  }

  if (狀態.page === "user") {
    寫入參數(參數, "name", 狀態.user);
    寫入參數(參數, "server", 狀態.server);
    return;
  }

  if (狀態.page === "compare") {
    寫入參數(參數, "left", 狀態.left);
    寫入參數(參數, "right", 狀態.right);
    寫入參數(參數, "role", 狀態.role);
    return;
  }

  if (狀態.page === "jobs") {
    // 職業分析只有「職業」是可分享的選擇；職能可由職業反推，
    // 不寫入 jobType 可避免 /jobs 連結出現重複語意的 query。
    寫入參數(參數, "job", 狀態.job);
  }
}

function 建立頁面路徑(目前路徑, 頁面) {
  const 基底 = 取得目前路由基底(目前路徑);
  const 片段 = 頁面路徑片段[頁面] || "";
  return 片段 ? `${基底}${片段}` : 基底;
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

  網址.pathname = 建立頁面路徑(網址.pathname, 狀態.page);
  寫入頁面專屬參數(網址.searchParams, 狀態);

  const 目前網址 = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  const 目標網址 = `${網址.pathname}${網址.search}${網址.hash}`;
  if (目標網址 === 目前網址) {
    return;
  }

  const 方法 = 選項.replace ? "replaceState" : "pushState";
  window.history[方法](null, "", 網址);
}
