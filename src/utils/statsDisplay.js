import { 職業群組設定 } from "../domain/jobs.js";
import { 轉為數字 } from "./formatters.js";

export function 職業範圍類型(範圍) {
  if (!範圍 || 範圍 === "all") {
    return "all";
  }
  return String(範圍).startsWith("role:") ? "role" : "job";
}

function 計算顯示比例(數量, 分母) {
  return 分母 > 0 ? Number(((數量 / 分母) * 100).toFixed(2)) : 0;
}

function 正規化統計數量(數量) {
  return 轉為數字(數量) || 0;
}

export function 取得統計範圍計數(統計項目, 職業範圍 = "all") {
  if (!統計項目) {
    return 0;
  }

  const 範圍類型 = 職業範圍類型(職業範圍);
  if (範圍類型 === "role") {
    return 正規化統計數量((統計項目.role_stats || []).find((項目) => 項目.role === 職業範圍)?.clear_count);
  }
  if (範圍類型 === "job") {
    return 正規化統計數量((統計項目.job_stats || []).find((項目) => 項目.job === 職業範圍)?.clear_count);
  }

  // global_stats 根層沒有 character_count / clear_count；全服副本通關概覽的全範圍佔比
  // 要對齊「公開玩家覆蓋率」，所以分母是唯一玩家 total_character_count，而不是跨副本加總的人次。
  return 正規化統計數量(統計項目.character_count ?? 統計項目.clear_count ?? 統計項目.total_character_count);
}

export function 建立職業佔比分組(來源, 職業範圍 = "all") {
  const 範圍類型 = 職業範圍類型(職業範圍);
  const 原始職業列表 = Array.isArray(來源?.job_stats) ? 來源.job_stats : [];
  const 職業列表 = 原始職業列表
    .filter((項目) => {
      if (範圍類型 === "role") {
        return 項目.role === 職業範圍;
      }
      if (範圍類型 === "job") {
        return 項目.job === 職業範圍;
      }
      return true;
    })
    .map((項目) => ({
      ...項目,
      clear_count: 正規化統計數量(項目.clear_count),
      entry_count: 正規化統計數量(項目.entry_count),
      percentage: 正規化統計數量(項目.percentage),
    }));
  const 篩選後職業紀錄總數 = 職業列表.reduce((總數, 項目) => 總數 + 項目.clear_count, 0);

  return 職業群組設定
    .map((群組) => {
      const jobs = 職業列表.filter((項目) => 項目.role === 群組.代碼);
      if (jobs.length === 0) {
        return null;
      }

      const roleStats = (來源?.role_stats || []).find((項目) => 項目.role === 群組.代碼);
      const roleClearCount = 正規化統計數量(roleStats?.clear_count);
      const jobsClearCount = jobs.reduce((總數, 項目) => 總數 + 項目.clear_count, 0);
      const shouldRebasePercentage = 範圍類型 !== "all";
      const rebasedJobs = shouldRebasePercentage
        ? jobs.map((項目) => ({
            ...項目,
            percentage: 計算顯示比例(項目.clear_count, 篩選後職業紀錄總數),
          }))
        : jobs;

      // all 範圍沿用 Data Building Layer 預先算好的 role/job 分母；
      // 使用者套用職能或單一職業後，畫面只把既有 clear_count 依目前篩選範圍重定比例，避免顯示仍停在全職業分母。
      return {
        role: 群組.代碼,
        role_name: 群組.名稱,
        色彩: 群組.色彩,
        clear_count: shouldRebasePercentage
          ? 範圍類型 === "job"
            ? jobsClearCount
            : roleClearCount || jobsClearCount
          : roleClearCount || jobsClearCount,
        percentage: shouldRebasePercentage
          ? 計算顯示比例(jobsClearCount, 篩選後職業紀錄總數)
          : 正規化統計數量(roleStats?.percentage),
        jobs: rebasedJobs,
      };
    })
    .filter(Boolean);
}
