import { onMounted, onUnmounted, unref, watch } from "vue";

export const 站台名稱 = "FFXIV 繁中服排行榜";
export const 預設分享標題 = 站台名稱;
export const 預設分享描述 =
  "整理 FFLogs 公開報告中的 FFXIV 繁中服零式、極、幻與絕本成績，提供排行榜、全服統計、個人成績單、玩家比較與近期動態。";

const 預設站台網址 = "https://ranking.init.engineer/";
const 預設分享圖片檔名 = "og-image.png";
export const 分享網址變更事件 = "ffxivtc:urlchange";

function 讀取Document() {
  return typeof document === "undefined" ? null : document;
}

function 壓縮空白(文字) {
  return String(文字 || "")
    .replace(/\s+/g, " ")
    .trim();
}

export function 正規化分享描述(文字, 最大長度 = 155) {
  const 描述 = 壓縮空白(文字) || 預設分享描述;
  const 字元 = Array.from(描述);
  if (字元.length <= 最大長度) {
    return 描述;
  }
  return `${字元.slice(0, Math.max(0, 最大長度 - 3)).join("")}...`;
}

function 建立絕對網址(路徑或網址, 基底網址 = 預設站台網址) {
  try {
    return new URL(路徑或網址 || ".", 基底網址).href;
  } catch {
    return 預設站台網址;
  }
}

export function 建立目前分享網址() {
  if (typeof window === "undefined") {
    return 預設站台網址;
  }

  const 網址 = new URL(window.location.href);
  網址.hash = "";
  return 網址.href;
}

function 讀取分享圖片網址() {
  if (typeof window === "undefined") {
    return 建立絕對網址(預設分享圖片檔名);
  }

  return 建立絕對網址(`${import.meta.env.BASE_URL}${預設分享圖片檔名}`, window.location.href);
}

function 設定Meta(屬性名稱, 屬性值, 內容) {
  const 文件 = 讀取Document();
  if (!文件) {
    return;
  }

  let 節點 = Array.from(文件.head.querySelectorAll("meta")).find(
    (meta) => meta.getAttribute(屬性名稱) === 屬性值,
  );

  if (!壓縮空白(內容)) {
    節點?.remove();
    return;
  }

  if (!節點) {
    節點 = 文件.createElement("meta");
    節點.setAttribute(屬性名稱, 屬性值);
    文件.head.appendChild(節點);
  }

  節點.setAttribute("content", 壓縮空白(內容));
}

function 設定Canonical(網址) {
  const 文件 = 讀取Document();
  if (!文件) {
    return;
  }

  let 節點 = 文件.head.querySelector('link[rel="canonical"]');
  if (!節點) {
    節點 = 文件.createElement("link");
    節點.setAttribute("rel", "canonical");
    文件.head.appendChild(節點);
  }
  節點.setAttribute("href", 網址);
}

function 設定結構化資料(分享資訊) {
  const 文件 = 讀取Document();
  if (!文件) {
    return;
  }

  let 節點 = 文件.getElementById("site-structured-data");
  if (!節點) {
    節點 = 文件.createElement("script");
    節點.id = "site-structured-data";
    節點.type = "application/ld+json";
    文件.head.appendChild(節點);
  }

  節點.textContent = JSON.stringify({
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: 站台名稱,
    alternateName: ["FFXIV TC Rankings", "FF14 繁中服排行榜"],
    url: 建立絕對網址(".", 預設站台網址),
    inLanguage: "zh-Hant-TW",
    description: 預設分享描述,
    potentialAction: {
      "@type": "SearchAction",
      target: `${建立絕對網址(".", 預設站台網址)}?q={search_term_string}`,
      "query-input": "required name=search_term_string",
    },
    mainEntity: {
      "@type": "WebPage",
      name: 分享資訊.title,
      url: 分享資訊.url,
      description: 分享資訊.description,
      inLanguage: "zh-Hant-TW",
      isPartOf: {
        "@type": "WebSite",
        name: 站台名稱,
        url: 建立絕對網址(".", 預設站台網址),
      },
    },
  });
}

export function 套用分享Meta(原始分享資訊 = {}) {
  const 文件 = 讀取Document();
  if (!文件) {
    return;
  }

  const 標題 = 壓縮空白(原始分享資訊.title) || 預設分享標題;
  const 描述 = 正規化分享描述(原始分享資訊.description);
  const 網址 = 原始分享資訊.url || 建立目前分享網址();
  const 圖片網址 = 原始分享資訊.image || 讀取分享圖片網址();

  文件.title = 標題;
  設定Meta("name", "description", 描述);
  設定Meta("name", "robots", "index, follow");
  設定Meta("name", "theme-color", "#101214");
  設定Canonical(網址);

  設定Meta("property", "og:site_name", 站台名稱);
  設定Meta("property", "og:type", 原始分享資訊.type || "website");
  設定Meta("property", "og:locale", "zh_TW");
  設定Meta("property", "og:title", 標題);
  設定Meta("property", "og:description", 描述);
  設定Meta("property", "og:url", 網址);
  設定Meta("property", "og:image", 圖片網址);
  設定Meta("property", "og:image:secure_url", 圖片網址);
  設定Meta("property", "og:image:type", "image/png");
  設定Meta("property", "og:image:width", "1200");
  設定Meta("property", "og:image:height", "630");
  設定Meta("property", "og:image:alt", `${站台名稱} 社群分享預覽圖`);
  設定Meta("property", "og:updated_time", 原始分享資訊.updatedAt);

  設定Meta("name", "twitter:card", "summary_large_image");
  設定Meta("name", "twitter:title", 標題);
  設定Meta("name", "twitter:description", 描述);
  設定Meta("name", "twitter:image", 圖片網址);
  設定Meta("name", "twitter:image:alt", `${站台名稱} 社群分享預覽圖`);

  設定結構化資料({
    title: 標題,
    description: 描述,
    url: 網址,
  });
}

export function useShareMeta(分享資訊來源) {
  const 套用目前分享資訊 = () => {
    const 分享資訊 = unref(分享資訊來源) || {};
    // SPA 內部切換頁面不會重新載入 index.html，因此需要在 Vue 狀態更新後同步 head meta。
    // 不執行 JavaScript 的社群爬蟲則會讀取 postbuild 產生的 route 專屬 HTML。
    套用分享Meta({
      ...分享資訊,
      url: 建立目前分享網址(),
    });
  };

  watch(() => unref(分享資訊來源), 套用目前分享資訊, {
    deep: true,
    flush: "post",
    immediate: true,
  });

  onMounted(() => {
    套用目前分享資訊();
    if (typeof window !== "undefined") {
      window.addEventListener("popstate", 套用目前分享資訊);
      window.addEventListener(分享網址變更事件, 套用目前分享資訊);
    }
  });

  onUnmounted(() => {
    if (typeof window !== "undefined") {
      window.removeEventListener("popstate", 套用目前分享資訊);
      window.removeEventListener(分享網址變更事件, 套用目前分享資訊);
    }
  });
}
