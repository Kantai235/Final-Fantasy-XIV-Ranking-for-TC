import {
  職業所屬類型,
  職業群組設定,
  職業類型排序值,
  顯示職業名稱,
} from "../domain/jobs.js";
import { 建立繁中服版本更新切點 } from "./activityTimelineAnnotations.js";
import { 轉為數字 } from "./formatters.js";
import { 取得成績PR值 } from "./userProfileSorting.js";

export const 個人成績趨勢預設副本範圍 = "all";
export const 個人成績趨勢預設職業範圍 = "all";
export const 個人成績趨勢預設時間範圍 = "30";
export const 個人成績趨勢預設指標 = "pr";

export const 個人成績趨勢時間範圍選項 = Object.freeze([
  { value: "7", label: "近 7 天" },
  { value: "14", label: "近 14 天" },
  { value: "30", label: "近 30 天" },
  { value: "90", label: "近 90 天" },
  { value: "all", label: "全部資料" },
  { value: "custom", label: "自訂日期" },
]);

export const 個人成績趨勢指標選項 = Object.freeze([
  { value: "pr", label: "PR 值" },
  { value: "rdps", label: "rDPS" },
]);

const 圖形最左 = 2;
const 圖形最右 = 98;
const 圖形最上 = 5;
const 圖形最下 = 46;
const 台灣時區偏移毫秒 = 8 * 60 * 60 * 1000;

function 限制範圍(數值, 最小, 最大) {
  return Math.min(Math.max(數值, 最小), 最大);
}

function 成績符合職業範圍(成績, 職業範圍) {
  if (!職業範圍 || 職業範圍 === 個人成績趨勢預設職業範圍) {
    return true;
  }

  if (職業範圍.startsWith("role:")) {
    return 職業所屬類型(成績?.job)?.代碼 === 職業範圍;
  }

  return 成績?.job === 職業範圍;
}

function 時間戳記轉台灣日期(時間戳記) {
  return Number.isFinite(時間戳記)
    ? new Date(時間戳記 + 台灣時區偏移毫秒).toISOString().slice(0, 10)
    : "";
}

function 台灣日期轉時間戳記(日期字串, 日末 = false) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(日期字串 || "")) {
    return null;
  }

  const 時間戳記 = Date.parse(`${日期字串}T${日末 ? "23:59:59.999" : "00:00:00.000"}+08:00`);
  return Number.isFinite(時間戳記) && 時間戳記轉台灣日期(時間戳記) === 日期字串
    ? 時間戳記
    : null;
}

function 台灣日期加天數(日期字串, 天數) {
  const 時間戳記 = 台灣日期轉時間戳記(日期字串);
  return 時間戳記 === null ? "" : 時間戳記轉台灣日期(時間戳記 + 天數 * 24 * 60 * 60 * 1000);
}

function 建立趨勢日期範圍(時間戳記列表, 時間範圍, 自訂開始日期, 自訂結束日期) {
  const 有效時間範圍 = 個人成績趨勢時間範圍選項.some((選項) => 選項.value === 時間範圍)
    ? 時間範圍
    : 個人成績趨勢預設時間範圍;
  if (時間戳記列表.length === 0) {
    return {
      value: 有效時間範圍,
      start: "",
      end: "",
      start_timestamp: null,
      end_timestamp: null,
    };
  }

  const 最早日期 = 時間戳記轉台灣日期(Math.min(...時間戳記列表));
  const 最晚日期 = 時間戳記轉台灣日期(Math.max(...時間戳記列表));
  let 開始日期 = 最早日期;
  let 結束日期 = 最晚日期;

  if (有效時間範圍 === "custom") {
    const 可用自訂開始 = 台灣日期轉時間戳記(自訂開始日期) === null ? 最早日期 : 自訂開始日期;
    const 可用自訂結束 = 台灣日期轉時間戳記(自訂結束日期) === null ? 最晚日期 : 自訂結束日期;
    [開始日期, 結束日期] = 可用自訂開始 <= 可用自訂結束
      ? [可用自訂開始, 可用自訂結束]
      : [可用自訂結束, 可用自訂開始];
  } else if (有效時間範圍 !== "all") {
    const 天數 = Math.max(1, 轉為數字(有效時間範圍) ?? 轉為數字(個人成績趨勢預設時間範圍) ?? 30);
    開始日期 = 台灣日期加天數(最晚日期, -(天數 - 1));
  }

  return {
    value: 有效時間範圍,
    start: 開始日期,
    end: 結束日期,
    start_timestamp: 台灣日期轉時間戳記(開始日期),
    end_timestamp: 台灣日期轉時間戳記(結束日期, true),
  };
}

function 取得漂亮刻度間距(範圍, 目標區間數 = 4) {
  const 粗略間距 = Math.max(範圍 / 目標區間數, Number.EPSILON);
  const 數量級 = 10 ** Math.floor(Math.log10(粗略間距));
  const 比例 = 粗略間距 / 數量級;
  const 倍數 = 比例 <= 1 ? 1 : 比例 <= 2 ? 2 : 比例 <= 5 ? 5 : 10;
  return 倍數 * 數量級;
}

function 建立數值軸(數值列表, 指標) {
  if (指標 === "pr") {
    return {
      最小值: 0,
      最大值: 100,
      刻度列表: [100, 75, 50, 25, 0],
    };
  }

  const 最低值 = Math.min(...數值列表);
  const 最高值 = Math.max(...數值列表);
  const 原始範圍 = Math.max(最高值 - 最低值, Math.abs(最高值) * 0.1, 1);
  const 刻度間距 = 取得漂亮刻度間距(原始範圍);
  const 最小值 = Math.max(0, Math.floor(最低值 / 刻度間距) * 刻度間距);
  let 最大值 = Math.ceil(最高值 / 刻度間距) * 刻度間距;
  if (最大值 <= 最小值) {
    最大值 = 最小值 + 刻度間距;
  }

  const 刻度列表 = [];
  for (let 數值 = 最大值; 數值 >= 最小值 && 刻度列表.length < 8; 數值 -= 刻度間距) {
    刻度列表.push(Number(數值.toFixed(6)));
  }

  if (刻度列表.at(-1) !== 最小值) {
    刻度列表.push(最小值);
  }

  return { 最小值, 最大值, 刻度列表 };
}

function 數值轉Y座標(數值, 數值軸) {
  const 範圍 = 數值軸.最大值 - 數值軸.最小值;
  const 比例 = 範圍 > 0 ? (數值 - 數值軸.最小值) / 範圍 : 0.5;
  return Number((圖形最下 - 限制範圍(比例, 0, 1) * (圖形最下 - 圖形最上)).toFixed(2));
}

function 建立時間刻度列表(起始時間戳記, 結束時間戳記) {
  if (!Number.isFinite(起始時間戳記) || !Number.isFinite(結束時間戳記)) {
    return [];
  }

  if (結束時間戳記 <= 起始時間戳記) {
    return [{ key: "time-0", x: 50, recorded_at_iso: new Date(起始時間戳記).toISOString(), 邊緣: "中央" }];
  }

  const 相差天數 = (結束時間戳記 - 起始時間戳記) / (24 * 60 * 60 * 1000);
  // 時間範圍很短時若仍硬塞五個「日期」標籤，會出現多個完全相同的日期。
  // 依跨度縮減刻度，保留起迄關係且不讓軸標籤製造不存在的資訊差異。
  const 刻度比例 = 相差天數 < 2
    ? [0, 1]
    : 相差天數 < 7
      ? [0, 0.5, 1]
      : [0, 0.25, 0.5, 0.75, 1];

  return 刻度比例.map((比例, index) => ({
    key: `time-${index}`,
    x: Number((圖形最左 + 比例 * (圖形最右 - 圖形最左)).toFixed(2)),
    recorded_at_iso: new Date(起始時間戳記 + (結束時間戳記 - 起始時間戳記) * 比例).toISOString(),
    邊緣: index === 0 ? "左" : index === 刻度比例.length - 1 ? "右" : "中央",
  }));
}

/**
 * 建立成績趨勢專用篩選選項。
 *
 * 趨勢圖刻意使用未套用頁面職業條件的副本成績：頁面本身的職業篩選服務
 * 詳細成績表，而這張圖有自己的「全部／職能／職業」範圍。如果沿用頁面
 * 篩選後的資料，「全部職業」可能只剩一個職業，畫面文字會與實際資料矛盾。
 */
export function 建立個人成績趨勢篩選選項(副本成績列表) {
  const 副本選項 = [];
  const 職業集合 = new Set();

  for (const 副本 of Array.isArray(副本成績列表) ? 副本成績列表 : []) {
    const 公開成績 = Array.isArray(副本?.public_entries) ? 副本.public_entries : [];
    if (公開成績.length === 0 || !副本?.encounter_key) {
      continue;
    }

    副本選項.push({
      value: 副本.encounter_key,
      label: 副本.encounter_name || 副本.encounter_key,
      category: 副本.encounter_category || "副本",
    });
    for (const 成績 of 公開成績) {
      if (成績?.job) {
        職業集合.add(成績.job);
      }
    }
  }

  const 職業選項 = [...職業集合]
    .sort((前一個, 後一個) => {
      const 類型差 = 職業類型排序值(職業所屬類型(前一個)?.代碼)
        - 職業類型排序值(職業所屬類型(後一個)?.代碼);
      return 類型差 || 顯示職業名稱(前一個).localeCompare(顯示職業名稱(後一個), "zh-Hant-TW");
    })
    .map((職業) => {
      const 職能 = 職業所屬類型(職業);
      return {
        value: 職業,
        label: 顯示職業名稱(職業),
        role: 職能?.代碼 || "",
        color: 職能?.色彩 || "",
      };
    });

  const 職能選項 = 職業群組設定
    .filter((職能) => 職能.職業.some((職業) => 職業集合.has(職業)))
    .map((職能) => ({ value: 職能.代碼, label: 職能.名稱, color: 職能.色彩 }));

  return { 副本選項, 職能選項, 職業選項 };
}

/**
 * 將所有符合範圍的公開成績整理成單一時間軸。
 *
 * PR 可以直接跨副本、跨職業比較；rDPS 則依使用者要求保留為另一個檢視。
 * rDPS 在不同副本與職業間不代表相同強度，因此資訊卡仍同時顯示副本與職業，
 * 避免使用者把跨條件的絕對數值誤認為同一母體的排名。
 */
export function 建立個人成績統一趨勢(
  副本成績列表,
  {
    副本範圍 = 個人成績趨勢預設副本範圍,
    職業範圍 = 個人成績趨勢預設職業範圍,
    時間範圍 = 個人成績趨勢預設時間範圍,
    自訂開始日期 = "",
    自訂結束日期 = "",
    指標 = 個人成績趨勢預設指標,
  } = {},
) {
  const 有效指標 = 個人成績趨勢指標選項.some((選項) => 選項.value === 指標)
    ? 指標
    : 個人成績趨勢預設指標;
  const 候選點列表 = [];
  let 略過無時間紀錄數 = 0;

  for (const [副本索引, 副本] of (Array.isArray(副本成績列表) ? 副本成績列表 : []).entries()) {
    if (副本範圍 !== 個人成績趨勢預設副本範圍 && 副本?.encounter_key !== 副本範圍) {
      continue;
    }

    for (const [成績索引, 成績] of (Array.isArray(副本?.public_entries) ? 副本.public_entries : []).entries()) {
      if (!成績符合職業範圍(成績, 職業範圍)) {
        continue;
      }

      const 時間戳記 = new Date(成績?.recorded_at_iso || "").getTime();
      if (!Number.isFinite(時間戳記)) {
        // 單一時間軸不能替缺少時間的舊資料猜測位置；保留略過數量供 UI 說明，
        // 也避免等距 fallback 讓版本切點與真實紀錄日期錯位。
        略過無時間紀錄數 += 1;
        continue;
      }

      候選點列表.push({
        id: `${副本?.encounter_key || "encounter"}-${成績?.id || `${時間戳記}-${成績索引}`}`,
        encounter_key: 副本?.encounter_key || 成績?.encounter_key || "",
        encounter_name: 副本?.encounter_name || 成績?.encounter_name || "未知副本",
        encounter_category: 副本?.encounter_category || 成績?.encounter_category || "副本",
        encounter_order: 副本索引,
        job: 成績?.job || "",
        job_name: 顯示職業名稱(成績?.job),
        job_role: 職業所屬類型(成績?.job),
        pr_value: 取得成績PR值(成績),
        rdps: 轉為數字(成績?.rdps),
        recorded_at_iso: new Date(時間戳記).toISOString(),
        timestamp: 時間戳記,
        過版紀錄: Boolean(成績?.is_obsolete_record),
      });
    }
  }

  // 「近 N 天」與近期動態一致，以目前副本／職業範圍中最新可用日期為終點，
  // 而不是以今天倒推。否則較久未上傳紀錄的角色會得到一張空圖，也無法查看
  // 自己最後一段成長歷程。日期邊界固定採繁中服時區（UTC+8）。
  const 日期範圍 = 建立趨勢日期範圍(
    候選點列表.map((點) => 點.timestamp),
    時間範圍,
    自訂開始日期,
    自訂結束日期,
  );
  const 原始點列表 = 候選點列表
    .filter((點) => (
      日期範圍.start_timestamp === null
      || 日期範圍.end_timestamp === null
      || (點.timestamp >= 日期範圍.start_timestamp && 點.timestamp <= 日期範圍.end_timestamp)
    ))
    .map((點) => ({ ...點, metric_value: 有效指標 === "rdps" ? 點.rdps : 點.pr_value }))
    .filter((點) => 點.metric_value !== null);

  原始點列表.sort((前一個, 後一個) => (
    前一個.timestamp - 後一個.timestamp
    || 前一個.encounter_order - 後一個.encounter_order
    || 前一個.job_name.localeCompare(後一個.job_name, "zh-Hant-TW")
    || 前一個.id.localeCompare(後一個.id)
  ));

  if (原始點列表.length === 0) {
    return {
      指標: 有效指標,
      指標名稱: 有效指標 === "rdps" ? "rDPS" : "PR 值",
      點列表: [],
      線段列表: [],
      Y軸刻度列表: [],
      時間刻度列表: [],
      版本切點列表: [],
      日期範圍,
      略過無時間紀錄數,
    };
  }

  const 起始時間戳記 = 原始點列表[0].timestamp;
  const 結束時間戳記 = 原始點列表.at(-1).timestamp;
  const 使用線性時間軸 = 原始點列表.length > 1 && 結束時間戳記 > 起始時間戳記;
  const 數值軸 = 建立數值軸(原始點列表.map((點) => 點.metric_value), 有效指標);
  const 點列表 = 原始點列表.map((點, index) => {
    const x = 使用線性時間軸
      ? 圖形最左 + ((點.timestamp - 起始時間戳記) / (結束時間戳記 - 起始時間戳記)) * (圖形最右 - 圖形最左)
      : (原始點列表.length === 1 ? 50 : 圖形最左 + (index / (原始點列表.length - 1)) * (圖形最右 - 圖形最左));
    return {
      ...點,
      x: Number(x.toFixed(2)),
      y: 數值轉Y座標(點.metric_value, 數值軸),
    };
  });
  const 線段列表 = 點列表.slice(1).map((點, index) => {
    const 前一點 = 點列表[index];
    return {
      key: `${前一點.id}-${點.id}`,
      path: `M ${前一點.x} ${前一點.y} L ${點.x} ${點.y}`,
      過版紀錄: 前一點.過版紀錄 || 點.過版紀錄,
    };
  });
  const Y軸刻度列表 = 數值軸.刻度列表.map((數值) => ({
    key: `value-${數值}`,
    value: 數值,
    y: 數值轉Y座標(數值, 數值軸),
  }));
  const 版本切點列表 = 使用線性時間軸
    ? 建立繁中服版本更新切點(起始時間戳記, 結束時間戳記).map((切點) => ({
        ...切點,
        x: Number((圖形最左 + (切點.x / 100) * (圖形最右 - 圖形最左)).toFixed(2)),
      }))
    : [];

  return {
    指標: 有效指標,
    指標名稱: 有效指標 === "rdps" ? "rDPS" : "PR 值",
    點列表,
    線段列表,
    Y軸刻度列表,
    時間刻度列表: 建立時間刻度列表(起始時間戳記, 結束時間戳記),
    版本切點列表,
    日期範圍,
    略過無時間紀錄數,
  };
}
