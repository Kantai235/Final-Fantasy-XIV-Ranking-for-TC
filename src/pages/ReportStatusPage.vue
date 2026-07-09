<script setup>
import { computed, onMounted, ref, watch } from "vue";
import { 讀取Json } from "../utils/fetchJson";
import { 格式化整數, 格式化紀錄時間 } from "../utils/formatters";
import { 建立公開資料網址, 報告狀態索引網址, 更新狀態網址 } from "../utils/publicData";
import { 顯示Telegram連結 } from "../utils/siteFeatures";
import {
  建立Fflogs即時狀態顯示,
  建立Report檢查結果,
  建立報告索引Map,
  建立未收錄提示,
  查詢Fflogs即時狀態,
  送出Fflogs待收錄,
  解析Fflogs網址,
} from "../utils/reportStatus";

const 輸入文字 = ref("");
const 報告索引 = ref(null);
const hidden報告索引 = ref(null);
const 更新狀態 = ref(null);
const 讀取中 = ref(false);
const 錯誤訊息 = ref("");
const 即時狀態讀取中 = ref(false);
const 即時狀態Payload = ref(null);
const 即時狀態錯誤 = ref("");
const 即時狀態ReportCode = ref("");
const 待收錄送出中 = ref(false);
const 待收錄Payload = ref(null);
const 待收錄錯誤 = ref("");

const Telegram連結 = "https://t.me/ffxiv_tc";
const hidden報告狀態索引網址 = 建立公開資料網址("data/all/report_status_index.json");
const 快速處理清單 = Object.freeze([
  {
    title: "先貼 FFLogs",
    text: "如果問題和收錄有關，先用下方工具確認 report code、fight、站內索引命中與 FFLogs 目前公開狀態。",
  },
  {
    title: "再看時間窗",
    text: "三天內的新紀錄通常較快補上；三天前的歷史戰鬥會進入較慢的輪巡補查。",
  },
  {
    title: "最後附脈絡",
    text: "回報時附上角色、伺服器、副本、職業、report code 與 fight，會比只貼截圖更容易追查。",
  },
]);
const 常見問題分類 = Object.freeze([
  {
    id: "fflogs",
    label: "FFLogs",
    title: "收錄與更新",
    summary: "大多數「沒抓到」都和公開狀態、戰鬥時間、fight 匯出、支援副本或歷史補查進度有關。",
    items: [
      {
        question: "我剛上傳 FFLogs，通常多久會出現在排行榜？",
        answer: [
          "要看戰鬥發生的時間，不只看上傳時間。三天內的新紀錄大約 2 到 3 小時會被檢查一次；三天前的歷史戰鬥會進入較慢的歷史補查，常見等待時間約 2 到 3 週。",
          "如果 FFLogs 還沒匯出通關 fight、report 還是 Private、或 FFLogs API 暫時不完整，即使到了排程也可能要等下一輪。",
        ],
      },
      {
        question: "為什麼 FFLogs 網址貼上去，排行榜還是找不到？",
        answer: [
          "常見原因包含 report 沒公開、已刪除或轉 Private、沒有繁中服玩家、不是目前支援的副本、指定 fight 沒有通關、FFLogs 尚未匯出該 fight，或歷史補查還沒輪到。",
          "下方工具會先比對目前公開靜態索引，也可以透過站務 Apps Script 即時確認 FFLogs API 目前是否公開可讀。若 FFLogs 可讀但尚未入庫，仍需要等待資料管線下一輪確認繁中服玩家、支援副本與通關 fight。",
        ],
      },
      {
        question: "一份 report 包了整天或多種副本，會不會抓不到？",
        answer: [
          "目前資料管線已支援混合上傳 report，會查完整 fight list 並依 fight 層的副本資訊分派到啟用副本。",
          "仍建議依內容或時間分開上傳，因為分開的 report 比較容易追查，也比較能避免超大型 report 在 FFLogs 匯出、掃描與診斷時拖慢整個流程。",
        ],
      },
    ],
  },
  {
    id: "ranking",
    label: "排行榜",
    title: "公開、移除與同名角色",
    summary: "排行榜以 FFLogs 公開資料與繁中服角色身分為基礎，會尊重 report 後續變成不可存取的狀態。",
    items: [
      {
        question: "可以只鎖個人排行榜，讓某位玩家不要出現嗎？",
        answer: [
          "目前沒有單獨鎖某位玩家公開排行榜的功能。資料來源是公開 FFLogs report；如果 report 或戰鬥資料被移除、轉成 Private，後續狀態巡檢與重建公開資料時，排行榜也會移除對應紀錄。",
          "站方不提供單一玩家或單筆紀錄的站內遮蔽協助。若隊友對紀錄公開有疑慮，請回到 FFLogs report 本身調整公開狀態或移除對應戰鬥資料。",
        ],
      },
      {
        question: "同名角色在不同伺服器，為什麼會被拆開？轉服怎麼辦？",
        answer: [
          "公開排行榜與個人成績單現在以「角色名稱 + 伺服器」作為玩家身分。同名但不同伺服器會視為不同角色，避免把兩個不同玩家合併在一起。",
          "真正的轉服紀錄沒有穩定公開 ID 可以完整追溯，因此不會自動把不同伺服器的同名紀錄合併成同一人。若遇到看起來被舊資料合併的狀況，回報時請附兩邊伺服器與代表 report。",
        ],
      },
    ],
  },
  {
    id: "version",
    label: "版本",
    title: "過版紀錄與分位",
    summary: "部分副本會用版本切點區分有效版本與全部版本，避免裝備提升後的紀錄混入同職分位。",
    items: [
      {
        question: "紀錄出現了，為什麼標示為過版或過時？",
        answer: [
          "部分副本會設定版本切點。例如「極 豔翼蛇鳥」與「極 佐拉加」在 7.1 改版後，因裝備品級提升與可能跳過機制，較難反映原本版本的副本實力，因此 2026-04-21 18:00 後的紀錄會標示為過版紀錄。",
          "過版紀錄仍可在全部版本資料中查看，但不參與有效版本的同職分位。這是為了讓分位比較盡量落在同一個裝備與副本環境。",
        ],
      },
      {
        question: "一定要在通關當天上傳才算有效版本嗎？",
        answer: [
          "不用。版本判斷看的是戰鬥發生時間，不是上傳時間。上傳時間只會影響掃描優先順序與等待時間。",
        ],
      },
    ],
  },
  {
    id: "gcd",
    label: "GCD",
    title: "GCD 覆蓋率與 Active",
    summary: "GCD 覆蓋率不是 FFLogs Active%，它是站內用 FFLogs 資料推算、盡量對齊 xivanalysis 的 Always Be Casting 類指標。",
    items: [
      {
        question: "Active% 和 GCD 覆蓋率為什麼不一樣？",
        answer: [
          "Active% 主要對齊 FFLogs Damage Done 的活躍時間；GCD 覆蓋率則是在估算玩家可行動時間中，有多少時間被 GCD 行動覆蓋。兩者定義不同，所以數值不同是正常的。",
          "站內 GCD 會盡量接近 xivanalysis 的 Always Be Casting 顯示值，並依副本處理 Boss 不可選取、玩家 UnableToAct、部分職業技能例外與 raw events 差異。",
        ],
      },
      {
        question: "為什麼舊紀錄沒有 GCD%，或和 xivanalysis 有差？",
        answer: [
          "新紀錄會在落地時嘗試即時計算 GCD；舊紀錄需要後台逐輪回補，常見等待時間約 2 到 3 週。",
          "如果 report 變成 Private、刪除或無權限，GCD 可能無法補算。若新紀錄和 xivanalysis 差距明顯，回報時請附 report、fight、角色、伺服器與職業，方便比對技能例外或 downtime 判斷。",
        ],
      },
    ],
  },
]);

const 常見問題總數 = computed(() =>
  常見問題分類.reduce((總數, 分類) => 總數 + 分類.items.length, 0),
);

const 常見問題導覽 = computed(() =>
  常見問題分類.map((分類) => ({
    ...分類,
    count: 分類.items.length,
    href: `#faq-${分類.id}`,
  })),
);

const 解析結果 = computed(() => 解析Fflogs網址(輸入文字.value));
const 公開索引Map = computed(() => 建立報告索引Map(報告索引.value));
const hidden索引Map = computed(() => 建立報告索引Map(hidden報告索引.value));
const 檢查結果 = computed(() =>
  建立Report檢查結果({
    解析結果: 解析結果.value,
    公開索引Map: 公開索引Map.value,
    hidden索引Map: hidden索引Map.value,
  }),
);
const 未收錄提示 = computed(() => 建立未收錄提示(更新狀態.value));

const 結果狀態 = computed(() => 檢查結果.value.status);
const 命中Report = computed(() => 檢查結果.value.report);
const 命中Fight = computed(() => 檢查結果.value.fight);

const 結果標題 = computed(() => {
  if (結果狀態.value === "empty") {
    return "等待 FFLogs 網址";
  }
  if (結果狀態.value === "invalid") {
    return "無法解析網址";
  }
  if (結果狀態.value === "found") {
    return 命中Fight.value ? "指定 fight 已收錄" : "Report 已收錄";
  }
  if (結果狀態.value === "fight_missing") {
    return "Report 已收錄，但指定 fight 未收錄";
  }
  if (結果狀態.value === "hidden") {
    return "曾收錄，但目前不在一般公開資料";
  }
  return "尚未在公開索引找到";
});

const 結果說明 = computed(() => {
  if (結果狀態.value === "empty") {
    return "貼上 FFLogs report 網址後，這裡會比對目前公開資料索引；按下查詢公開狀態可確認 FFLogs 目前是否公開可讀。";
  }
  if (結果狀態.value === "invalid") {
    return 解析結果.value.error || "請確認網址是否為 FFLogs report 頁面。";
  }
  if (結果狀態.value === "found") {
    return "這份紀錄已存在於目前公開資料；如果使用者看不到，通常是職業、伺服器、副本或版本篩選條件不同。";
  }
  if (結果狀態.value === "fight_missing") {
    return "同一份 report 有其它 fight 被收錄，但網址指定的 fight 沒有公開排行列；常見原因是該 fight 不是支援副本、沒有通關、沒有繁中服玩家，或尚未完成資料匯出。";
  }
  if (結果狀態.value === "hidden") {
    return "這份 report 曾進入額外狀態資料，但目前被標記為 private、deleted 或不可存取，因此不會出現在一般公開排行榜。";
  }
  return "公開靜態索引沒有找到這個 report code；如果 report 剛上傳或是歷史戰鬥，請參考下方排程判斷。";
});

const 查詢摘要 = computed(() => [
  {
    label: "Report code",
    value: 解析結果.value.report_code || "-",
  },
  {
    label: "指定 fight",
    value: 解析結果.value.fight_text || "未指定",
  },
  {
    label: "資料更新",
    value: 格式化紀錄時間(更新狀態.value?.rankings_updated_at_iso || 報告索引.value?.generated_at_iso),
  },
  {
    label: "下一輪排程",
    value: 格式化紀錄時間(未收錄提示.value.next_run_at_iso),
    secondary_value: 未收錄提示.value.next_run_wait_text,
  },
]);

const 顯示Fight列表 = computed(() => {
  if (命中Fight.value) {
    return [命中Fight.value];
  }
  return (命中Report.value?.fights || []).slice(0, 6);
});

const 顯示副本列表 = computed(() => 命中Report.value?.encounters || []);

const 狀態徽章文字 = computed(() => {
  if (結果狀態.value === "found") {
    return "已收錄";
  }
  if (結果狀態.value === "fight_missing") {
    return "部分命中";
  }
  if (結果狀態.value === "hidden") {
    return "不公開";
  }
  if (結果狀態.value === "missing") {
    return "未入庫";
  }
  if (結果狀態.value === "invalid") {
    return "格式錯誤";
  }
  return "待查詢";
});

const 可查詢即時狀態 = computed(() =>
  解析結果.value.valid
  && Boolean(解析結果.value.report_code)
  && !即時狀態讀取中.value,
);

const 即時狀態顯示 = computed(() => {
  if (即時狀態讀取中.value) {
    return {
      status: "loading",
      badge: "查詢中",
      title: "正在確認 FFLogs 公開狀態",
      description: "正在透過站務 Apps Script 查詢 FFLogs API，通常幾秒內會完成。",
    };
  }

  if (即時狀態錯誤.value) {
    return {
      status: "error",
      badge: "查詢失敗",
      title: "暫時無法確認 FFLogs 公開狀態",
      description: 即時狀態錯誤.value,
    };
  }

  return 建立Fflogs即時狀態顯示(即時狀態Payload.value);
});

const 即時狀態細節 = computed(() => {
  const payload = 即時狀態Payload.value;
  if (!payload || typeof payload !== "object") {
    return [];
  }

  return [
    {
      label: "FFLogs 判定",
      value: payload.fflogs_access || payload.error_code || "-",
    },
    {
      label: "Visibility",
      value: payload.visibility || "-",
    },
    {
      label: "封存可讀",
      value: payload.archive_accessible === true ? "是" : payload.archive_accessible === false ? "否" : "-",
    },
    {
      label: "查詢時間",
      value: 格式化紀錄時間(payload.checked_at_iso),
    },
  ];
});

const Fflogs已公開可讀 = computed(() =>
  即時狀態Payload.value?.ok === true
  && 即時狀態Payload.value?.fflogs_access === "accessible"
  && String(即時狀態Payload.value?.visibility || "").toLocaleLowerCase("en-US") === "public",
);

const 待收錄請求類型 = computed(() =>
  結果狀態.value === "found" || 結果狀態.value === "fight_missing"
    ? "retry_existing"
    : "queue_missing",
);

const 待收錄按鈕文字 = computed(() =>
  待收錄請求類型.value === "retry_existing" ? "要求重新排查" : "加入待收錄名單",
);

const 可送出待收錄 = computed(() =>
  解析結果.value.valid
  && Boolean(解析結果.value.report_code)
  && Fflogs已公開可讀.value
  && !即時狀態讀取中.value
  && !待收錄送出中.value,
);

const 待收錄狀態顯示 = computed(() => {
  if (待收錄送出中.value) {
    return {
      status: "loading",
      badge: "送出中",
      title: "正在送出待收錄需求",
      description: "正在透過 Apps Script 寫入 Google Sheet 待收錄名單。",
    };
  }

  if (待收錄錯誤.value) {
    return {
      status: "error",
      badge: "送出失敗",
      title: "無法送出待收錄需求",
      description: 待收錄錯誤.value,
    };
  }

  const payload = 待收錄Payload.value;
  if (!payload) {
    return null;
  }

  const success = payload.queue_status === "queued" || payload.queue_status === "updated";
  return {
    status: success ? "public" : "error",
    badge: success ? "已排入" : "未排入",
    title: success ? "已加入待收錄名單" : "未加入待收錄名單",
    description: payload.message || (success ? "後續 workflow 執行時會完整重查整份 report。" : "請確認 report 是否已設為公開。"),
  };
});

function 重設即時狀態() {
  即時狀態讀取中.value = false;
  即時狀態Payload.value = null;
  即時狀態錯誤.value = "";
  即時狀態ReportCode.value = "";
  待收錄送出中.value = false;
  待收錄Payload.value = null;
  待收錄錯誤.value = "";
}

function 清除輸入() {
  輸入文字.value = "";
  重設即時狀態();
}

async function 查詢即時公開狀態() {
  const reportCode = 解析結果.value.report_code;
  if (!可查詢即時狀態.value || !reportCode) {
    return;
  }

  即時狀態讀取中.value = true;
  即時狀態Payload.value = null;
  即時狀態錯誤.value = "";
  即時狀態ReportCode.value = reportCode;
  待收錄Payload.value = null;
  待收錄錯誤.value = "";

  try {
    const payload = await 查詢Fflogs即時狀態(reportCode);
    if (即時狀態ReportCode.value === reportCode) {
      即時狀態Payload.value = payload;
    }
  } catch (error) {
    if (即時狀態ReportCode.value === reportCode) {
      即時狀態錯誤.value = error instanceof Error ? error.message : "FFLogs 即時狀態查詢失敗。";
    }
  } finally {
    if (即時狀態ReportCode.value === reportCode) {
      即時狀態讀取中.value = false;
    }
  }
}

async function 送出待收錄需求() {
  const reportCode = 解析結果.value.report_code;
  if (!可送出待收錄.value || !reportCode) {
    return;
  }

  待收錄送出中.value = true;
  待收錄Payload.value = null;
  待收錄錯誤.value = "";

  try {
    待收錄Payload.value = await 送出Fflogs待收錄({
      reportCode,
      requestType: 待收錄請求類型.value,
      siteStatus: 結果狀態.value,
    });
  } catch (error) {
    待收錄錯誤.value = error instanceof Error ? error.message : "待收錄需求送出失敗。";
  } finally {
    待收錄送出中.value = false;
  }
}

async function 載入Logs檢查資料() {
  讀取中.value = true;
  錯誤訊息.value = "";

  const [公開結果, 更新結果, hidden結果] = await Promise.allSettled([
    讀取Json(報告狀態索引網址, "讀取 Logs 狀態索引失敗"),
    讀取Json(更新狀態網址, "讀取更新狀態失敗"),
    讀取Json(hidden報告狀態索引網址, "讀取 hidden Logs 狀態索引失敗"),
  ]);

  if (公開結果.status === "fulfilled") {
    報告索引.value = 公開結果.value;
  } else {
    錯誤訊息.value = 公開結果.reason instanceof Error ? 公開結果.reason.message : "無法讀取 Logs 狀態索引";
  }

  if (更新結果.status === "fulfilled") {
    更新狀態.value = 更新結果.value;
  }

  if (hidden結果.status === "fulfilled") {
    hidden報告索引.value = hidden結果.value;
  }

  讀取中.value = false;
}

onMounted(() => {
  if (typeof window !== "undefined") {
    const 參數 = new URLSearchParams(window.location.search);
    輸入文字.value = String(參數.get("report") || "").trim();
  }
  載入Logs檢查資料();
});

watch(
  () => 解析結果.value.report_code,
  (下一個ReportCode, 前一個ReportCode) => {
    if (下一個ReportCode !== 前一個ReportCode) {
      重設即時狀態();
    }
  },
);
</script>

<template>
  <section class="常見問題頁" aria-live="polite">
    <section class="常見問題前言" aria-label="常見問題摘要">
      <div class="常見問題前言主文">
        <span class="常見問題眉標">站務支援中心</span>
        <h2>常見問題</h2>
        <p>把排行榜最常被問到的收錄、更新、過版、GCD 與角色身分問題整理在同一頁；FFLogs 相關疑問可以先用檢查工具比對目前公開索引。</p>
      </div>
      <nav class="常見問題分類導覽" aria-label="常見問題分類">
        <a v-for="分類 in 常見問題導覽" :key="分類.id" :href="分類.href">
          <small>{{ 分類.label }}</small>
          <strong>{{ 分類.title }}</strong>
          <span>{{ 分類.count }} 題</span>
        </a>
      </nav>
    </section>

    <section class="常見問題內容格" aria-label="常見問題內容">
      <aside class="常見問題側欄" aria-label="回報前檢查">
        <section class="常見問題側欄面板">
          <span class="常見問題眉標">回報前確認</span>
          <ol class="常見問題流程清單">
            <li v-for="項目 in 快速處理清單" :key="項目.title">
              <strong>{{ 項目.title }}</strong>
              <p>{{ 項目.text }}</p>
            </li>
          </ol>
        </section>
        <section class="常見問題側欄面板 常見問題統計卡">
          <small>已整理</small>
          <strong>{{ 常見問題總數 }} 題</strong>
          <span>{{ 常見問題分類.length }} 個分類</span>
        </section>
        <section v-if="顯示Telegram連結" class="常見問題側欄面板 常見問題Telegram卡" aria-label="Telegram 回報引導">
          <small>仍然找不到原因？</small>
          <strong>到 Telegram 交流群回報</strong>
          <p>請附上角色、伺服器、副本、職業、report code 與 fight，會更容易追查。</p>
          <a :href="Telegram連結" target="_blank" rel="noopener noreferrer">開啟 Telegram 交流群</a>
        </section>
      </aside>

      <div class="常見問題主欄">
        <section class="常見問題工具區" aria-label="FFLogs 網址檢查工具">
          <header class="常見問題區塊標題">
            <span>FFLogs 檢查工具</span>
            <h2>貼上 report 網址，先確認目前收錄狀態</h2>
            <p>這裡會比對站內已建好的靜態索引，判斷 report 是否已收錄、是否只命中部分 fight，以及下一輪資料更新等待時間；也可按下查詢公開狀態，確認 FFLogs 目前是否公開可讀。</p>
          </header>

          <section class="Logs檢查工具卡" aria-label="FFLogs 網址檢查">
            <div class="Logs檢查輸入區">
              <label class="Logs檢查輸入欄">
                <span>FFLogs 網址或 report code</span>
                <textarea
                  v-model="輸入文字"
                  rows="3"
                  spellcheck="false"
                  placeholder="https://www.fflogs.com/reports/xxxxxxxxxxxxxxxx?fight=3"
                ></textarea>
              </label>
              <div class="Logs檢查操作列">
                <a
                  v-if="解析結果.valid"
                  class="主要連結按鈕"
                  :href="解析結果.normalized_url"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  開啟 FFLogs
                </a>
                <button type="button" :disabled="!可查詢即時狀態" @click="查詢即時公開狀態">查詢公開狀態</button>
                <button type="button" :disabled="!可送出待收錄" @click="送出待收錄需求">{{ 待收錄按鈕文字 }}</button>
                <button type="button" :disabled="!輸入文字" @click="清除輸入">清除</button>
              </div>
            </div>

            <div v-if="讀取中" class="狀態列">讀取 Logs 狀態索引中</div>
            <div v-else-if="錯誤訊息" class="狀態列 錯誤">{{ 錯誤訊息 }}</div>

            <template v-else>
              <section class="Logs檢查結果" :data-status="結果狀態" aria-label="Logs 檢查結果">
                <header class="Logs檢查結果標頭">
                  <span class="Logs檢查狀態徽章">{{ 狀態徽章文字 }}</span>
                  <div>
                    <h2>{{ 結果標題 }}</h2>
                    <p>{{ 結果說明 }}</p>
                  </div>
                </header>
                <div class="Logs檢查摘要列" aria-label="查詢摘要">
                  <span v-for="項目 in 查詢摘要" :key="項目.label">
                    <small>{{ 項目.label }}</small>
                    <strong :class="{ Logs檢查摘要分行值: 項目.secondary_value }">
                      <template v-if="項目.secondary_value">
                        <span>{{ 項目.value }}</span>
                        <span class="Logs檢查摘要次值">{{ 項目.secondary_value }}</span>
                      </template>
                      <template v-else>{{ 項目.value }}</template>
                    </strong>
                  </span>
                </div>
              </section>

              <section
                v-if="解析結果.valid"
                class="Logs檢查即時狀態"
                :data-status="即時狀態顯示.status"
                aria-label="FFLogs 公開狀態"
              >
                <header class="Logs檢查即時狀態標頭">
                  <span class="Logs檢查即時狀態徽章">{{ 即時狀態顯示.badge }}</span>
                  <div>
                    <h2>{{ 即時狀態顯示.title }}</h2>
                    <p>{{ 即時狀態顯示.description }}</p>
                  </div>
                </header>
                <div v-if="即時狀態細節.length" class="Logs檢查即時狀態細節" aria-label="FFLogs 即時查詢細節">
                  <span v-for="項目 in 即時狀態細節" :key="項目.label">
                    <small>{{ 項目.label }}</small>
                    <strong>{{ 項目.value }}</strong>
                  </span>
                </div>
              </section>

              <section
                v-if="待收錄狀態顯示"
                class="Logs檢查即時狀態 Logs檢查待收錄狀態"
                :data-status="待收錄狀態顯示.status"
                aria-label="待收錄名單送出狀態"
              >
                <header class="Logs檢查即時狀態標頭">
                  <span class="Logs檢查即時狀態徽章">{{ 待收錄狀態顯示.badge }}</span>
                  <div>
                    <h2>{{ 待收錄狀態顯示.title }}</h2>
                    <p>{{ 待收錄狀態顯示.description }}</p>
                  </div>
                </header>
              </section>

              <div class="Logs檢查資訊格">
                <section v-if="命中Report" class="Logs檢查面板" aria-label="已收錄紀錄摘要">
                  <header class="統計面板標題">
                    <h2>命中紀錄</h2>
                    <span>{{ 格式化整數(命中Report.entry_count) }} 筆排行列・{{ 格式化整數(命中Report.character_count) }} 名玩家</span>
                  </header>
                  <div class="Logs檢查副本列表">
                    <article v-for="副本 in 顯示副本列表" :key="副本.encounter_key" class="Logs檢查副本卡">
                      <small>{{ 副本.encounter_category }}</small>
                      <strong>{{ 副本.encounter_name }}</strong>
                      <span>{{ 格式化整數(副本.entry_count) }} 筆・fight {{ 副本.fight_ids.join(", ") || "-" }}</span>
                    </article>
                  </div>
                  <div v-if="顯示Fight列表.length" class="Logs檢查Fight列表">
                    <article v-for="fight in 顯示Fight列表" :key="fight.fight_id || 'unknown'" class="Logs檢查Fight卡">
                      <div class="Logs檢查Fight標題">
                        <strong>Fight {{ fight.fight_id || "-" }}</strong>
                        <span>{{ 格式化整數(fight.entry_count) }} 筆排行列</span>
                      </div>
                      <div class="Logs檢查Fight指標列">
                        <span>
                          <small>玩家數</small>
                          <strong>{{ 格式化整數(fight.character_count) }}</strong>
                        </span>
                        <span>
                          <small>副本</small>
                          <strong>{{ fight.encounter_keys.join(", ") || "-" }}</strong>
                        </span>
                        <span>
                          <small>紀錄時間</small>
                          <strong>{{ 格式化紀錄時間(fight.latest_recorded_at_iso) }}</strong>
                        </span>
                      </div>
                    </article>
                  </div>
                </section>

                <section class="Logs檢查面板" aria-label="更新排程判斷">
                  <header class="統計面板標題">
                    <h2>更新判斷</h2>
                  </header>
                  <ul class="Logs檢查提示列表">
                    <li v-for="提示 in 未收錄提示.notes" :key="提示">{{ 提示 }}</li>
                  </ul>
                </section>
              </div>
            </template>
          </section>
        </section>

        <section class="常見問題列表區" aria-label="常見問題列表">
          <article v-for="分類 in 常見問題分類" :id="`faq-${分類.id}`" :key="分類.id" class="常見問題分類">
            <header class="常見問題分類標題">
              <span>{{ 分類.label }}</span>
              <h2>{{ 分類.title }}</h2>
              <p>{{ 分類.summary }}</p>
            </header>
            <div class="常見問題清單">
              <details v-for="項目 in 分類.items" :key="項目.question" class="常見問題項目">
                <summary>{{ 項目.question }}</summary>
                <div class="常見問題回答">
                  <p v-for="段落 in 項目.answer" :key="段落">{{ 段落 }}</p>
                </div>
              </details>
            </div>
          </article>
        </section>
      </div>
    </section>
  </section>
</template>
