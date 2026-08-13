import { 顯示職業名稱 } from "../../domain/jobs";
import { 讀取Json } from "../../utils/fetchJson";
import { 計算Active百分比, 轉為數字 } from "../../utils/formatters";
import { 建立公開資料網址 } from "../../utils/publicData";
import { 排序欄位標籤, 排序預設方向 } from "./defaults";

export function useRankingData({
  排序欄位,
  排序方向,
  目前副本,
  取得紀錄版本狀態,
}) {
  function 排序欄位預設方向(欄位) {
    return 排序預設方向[欄位] || "desc";
  }

  function 排序方向文字(欄位, 方向 = 排序方向.value) {
    if (欄位 === "clearTime") {
      return 方向 === "asc" ? "短到長" : "長到短";
    }
    if (欄位 === "recordedAt") {
      return 方向 === "asc" ? "舊到新" : "新到舊";
    }
    return 方向 === "asc" ? "低到高" : "高到低";
  }

  function 下一個排序方向(欄位) {
    if (排序欄位.value !== 欄位) {
      return 排序欄位預設方向(欄位);
    }
    return 排序方向.value === "asc" ? "desc" : "asc";
  }

  function 切換排序(欄位) {
    if (排序欄位.value === 欄位) {
      排序方向.value = 下一個排序方向(欄位);
      return;
    }

    排序欄位.value = 欄位;
    排序方向.value = 排序欄位預設方向(欄位);
  }

  function 是否目前排序(欄位) {
    return 排序欄位.value === 欄位;
  }

  function 排序方向圖示(欄位) {
    if (!是否目前排序(欄位)) {
      return "";
    }
    return 排序方向.value === "asc" ? "▲" : "▼";
  }

  function 排序ARIA(欄位) {
    if (!是否目前排序(欄位)) {
      return "none";
    }
    return 排序方向.value === "asc" ? "ascending" : "descending";
  }

  function 排序按鈕標籤(欄位) {
    const 標籤 = 排序欄位標籤[欄位] || 欄位;
    const 下一方向 = 下一個排序方向(欄位);
    return `以${標籤}${排序方向文字(欄位, 下一方向)}排序`;
  }

  function 排序數值(列, 欄位) {
    if (欄位 === "rank") {
      return 列.原始排名 ?? 列.職業排名 ?? null;
    }
    if (欄位 === "active") {
      return 列.active ?? null;
    }
    if (欄位 === "gcdCoverage") {
      return typeof 列.gcd_coverage === "number" ? 轉為數字(列.gcd_coverage) : 轉為數字(列.gcd_coverage?.percent);
    }
    if (欄位 === "dps") {
      return 列.dps ?? null;
    }
    if (欄位 === "rdps") {
      return 列.rdps ?? 列.dps ?? null;
    }
    if (欄位 === "adps") {
      return 列.adps ?? null;
    }
    if (欄位 === "healingHps") {
      return 列.healingStats?.hps ?? null;
    }
    if (欄位 === "pureHealing") {
      return 列.healingStats?.pureHealing ?? null;
    }
    if (欄位 === "healingProtection") {
      return 列.healingStats?.protection ?? null;
    }
    if (欄位 === "overhealPercent") {
      return 列.healingStats?.overhealPercent ?? null;
    }
    if (欄位 === "damageTaken") {
      return 列.tankStats?.damageTaken ?? null;
    }
    if (欄位 === "selfHealing") {
      return 列.tankStats?.selfHealing ?? null;
    }
    if (欄位 === "personalProtection") {
      return 列.tankStats?.personalProtection ?? null;
    }
    if (欄位 === "teamProtection") {
      return 列.tankStats?.teamProtection ?? null;
    }
    if (欄位 === "mitigationCoverage") {
      return 列.tankStats?.mitigationCoveragePercent ?? null;
    }
    if (欄位 === "clearTime") {
      return 列.通關秒數 ?? null;
    }
    if (欄位 === "recordedAt") {
      const 時間 = new Date(列.紀錄時間).getTime();
      return Number.isNaN(時間) ? null : 時間;
    }

    return 列.rdps ?? 列.dps ?? null;
  }

  function 比較排行列(前一筆, 後一筆) {
    const 欄位 = 排序欄位.value;
    const 前值 = 排序數值(前一筆, 欄位);
    const 後值 = 排序數值(後一筆, 欄位);
    const 前值缺失 = 前值 === null || Number.isNaN(前值);
    const 後值缺失 = 後值 === null || Number.isNaN(後值);

    if (前值缺失 || 後值缺失) {
      if (前值缺失 !== 後值缺失) {
        return 前值缺失 ? 1 : -1;
      }
    } else if (前值 !== 後值) {
      const 排序係數 = 排序方向.value === "asc" ? 1 : -1;
      return (前值 - 後值) * 排序係數;
    }

    const 前rDPS = 前一筆.rdps ?? 前一筆.dps ?? 0;
    const 後rDPS = 後一筆.rdps ?? 後一筆.dps ?? 0;
    if (前rDPS !== 後rDPS) {
      return 後rDPS - 前rDPS;
    }

    return 前一筆.角色名稱.localeCompare(後一筆.角色名稱, "zh-Hant-TW");
  }

  // public/data/rankings 目前有兩種相容格式：
  // 1. ranking_entries：Node 建置後供前端直接使用的扁平列。
  // 2. reports/fights/players：較舊或原始的 report 結構。
  // 這個正規化步驟讓 UI 後續只面對同一個欄位集合，避免每個頁面都理解資料來源差異。
  function 轉為可選數字(值) {
    if (值 === null || 值 === undefined || 值 === "") {
      return null;
    }
    return 轉為數字(值);
  }

  function 建立治療統計(來源) {
    if (!來源 || typeof 來源 !== "object") {
      return null;
    }
    return {
      hps: 轉為可選數字(來源.hps),
      pureHealing: 轉為可選數字(來源.pure_healing),
      protection: 轉為可選數字(來源.protection),
      overhealPercent: 轉為可選數字(來源.overheal_percent),
    };
  }

  function 建立坦克統計(來源) {
    if (!來源 || typeof 來源 !== "object") {
      return null;
    }
    return {
      damageTaken: 轉為可選數字(來源.damage_taken),
      selfHealing: 轉為可選數字(來源.self_healing),
      personalProtection: 轉為可選數字(來源.personal_protection),
      teamProtection: 轉為可選數字(來源.team_protection),
      mitigationCoveragePercent: 轉為可選數字(來源.mitigation_coverage_percent),
    };
  }

  function 建立同場支援職業(來源) {
    if (!來源 || typeof 來源 !== "object") {
      return null;
    }
    const 職業代碼 = 來源.job || "-";
    return {
      角色名稱: 來源.character_name || 來源.name || "未知玩家",
      伺服器: 來源.server || "未知伺服器",
      職業代碼,
      職業: 顯示職業名稱(職業代碼),
      rdps: 轉為可選數字(來源.rdps),
      active: 轉為可選數字(來源.active_percent),
      gcd_coverage: 來源.gcd_coverage ?? null,
      healingStats: 建立治療統計(來源.healing_stats),
      tankStats: 建立坦克統計(來源.tank_stats),
    };
  }

  function 建立排行列(條目, 副本 = 目前副本.value) {
    const 職業代碼 = 條目.job || "-";
    const 通關秒數 = 轉為數字(條目.clear_time_seconds);
    const active = 轉為數字(條目.active_percent) ?? 計算Active百分比(條目.active_time_ms, 通關秒數);
    const 版本狀態 = 取得紀錄版本狀態(條目, 副本);

    return {
      id: 條目.id || `${條目.report_code}-${條目.fight_id}-${條目.character_name}-${條目.server}`,
      detailId: 條目.detail_id || 條目.id || "",
      hasReportDetail: Boolean(條目.has_report_detail || 條目.report_code || 條目.report_url || 條目.fight_id),
      reportCode: 條目.report_code,
      reportUrl: 條目.report_url,
      fightId: 條目.fight_id ?? null,
      fflogsSourceId: 條目.fflogs_source_id ?? 條目.fflogs_id ?? 條目.source_id ?? null,
      角色名稱: 條目.character_name || 條目.name || "未知玩家",
      伺服器: 條目.server || "未知伺服器",
      職業代碼,
      職業: 顯示職業名稱(職業代碼),
      rdps: 轉為數字(條目.rdps ?? 條目.dps),
      adps: 轉為數字(條目.adps),
      dps: 轉為數字(條目.dps),
      active,
      gcd_coverage: 條目.gcd_coverage ?? null,
      gcd_coverage_status: 條目.gcd_coverage_status ?? null,
      healingStats: 建立治療統計(條目.healing_stats),
      tankStats: 建立坦克統計(條目.tank_stats),
      同場治療: 建立同場支援職業(條目.co_healer),
      同場坦克: 建立同場支援職業(條目.co_tank),
      activeTimeMs: 轉為數字(條目.active_time_ms),
      通關秒數,
      紀錄時間: 條目.recorded_at_iso || 條目.report_start_time_iso,
      gameVersion: 條目.game_version || null,
      重複來源數: 轉為數字(條目.duplicate_count) || 1,
      原始排名: 轉為數字(條目.rank),
      職業排名: 轉為數字(條目.job_rank ?? 條目.rank),
      過版紀錄: 版本狀態.is_obsolete_record,
      versionStatus: 版本狀態.version_status,
      versionCutoffIso: 版本狀態.version_cutoff_iso,
    };
  }

  function 還原排行榜薄索引列(列, 欄位列表) {
    if (!Array.isArray(列)) {
      return 列 && typeof 列 === "object" ? 列 : null;
    }

    return Object.fromEntries((欄位列表 || []).map((欄位, index) => [欄位, 列[index]]));
  }

  function 取得排行榜薄索引條目(原始資料) {
    if (!原始資料 || 原始資料.format !== "ranking_table_index_v1") {
      return null;
    }

    const 欄位列表 = Array.isArray(原始資料.table_columns) ? 原始資料.table_columns : [];
    const 來源列 = 原始資料.table_rows;
    if (!Array.isArray(來源列)) {
      return [];
    }

    return 來源列
      .map((列) => 還原排行榜薄索引列(列, 欄位列表))
      .filter(Boolean);
  }

  function 取得列Id(列, 欄位列表) {
    if (Array.isArray(列)) {
      const id索引 = 欄位列表.indexOf("id");
      return id索引 >= 0 ? 列[id索引] : null;
    }
    return 列?.id || null;
  }

  function 依順序合併列(公開列 = [], 差量列 = [], 順序 = [], 欄位列表 = []) {
    const 列索引 = new Map();
    for (const 列 of [...公開列, ...差量列]) {
      const id = 取得列Id(列, 欄位列表);
      if (id) {
        列索引.set(id, 列);
      }
    }

    const 合併後 = [];
    const 已使用 = new Set();
    for (const id of Array.isArray(順序) ? 順序 : []) {
      const 列 = 列索引.get(id);
      if (列) {
        合併後.push(列);
        已使用.add(id);
      }
    }
    if (Array.isArray(順序) && 順序.length > 0) {
      return 合併後;
    }
    for (const 列 of [...公開列, ...差量列]) {
      const id = 取得列Id(列, 欄位列表);
      if (id && !已使用.has(id)) {
        合併後.push(列);
        已使用.add(id);
      }
    }
    return 合併後;
  }

  function 依順序合併條目(公開條目 = [], 差量條目 = [], 順序 = []) {
    const 條目索引 = new Map();
    for (const 條目 of [...公開條目, ...差量條目]) {
      if (條目?.id) {
        條目索引.set(條目.id, 條目);
      }
    }

    const 合併後 = [];
    const 已使用 = new Set();
    for (const id of Array.isArray(順序) ? 順序 : []) {
      const 條目 = 條目索引.get(id);
      if (條目) {
        合併後.push(條目);
        已使用.add(id);
      }
    }
    if (Array.isArray(順序) && 順序.length > 0) {
      return 合併後;
    }
    for (const 條目 of [...公開條目, ...差量條目]) {
      if (條目?.id && !已使用.has(條目.id)) {
        合併後.push(條目);
        已使用.add(條目.id);
      }
    }
    return 合併後;
  }

  async function 解析排行榜資料格式(資料) {
    if (資料?.format === "ranking_table_hidden_delta_v1") {
      const 公開資料 = await 讀取Json(建立公開資料網址(資料.base_path), "讀取排行榜公開底稿失敗");
      const 欄位列表 = Array.isArray(資料.table_columns) ? 資料.table_columns : 公開資料.table_columns || [];
      const 合併後 = {
        ...公開資料,
        ...資料,
        format: "ranking_table_index_v1",
        hidden_reports_included: true,
        table_columns: 欄位列表,
        table_rows: 依順序合併列(公開資料.table_rows, 資料.table_rows, 資料.table_row_order, 欄位列表),
        // hidden delta 與公開底稿的快取更新可能短暫不同步；優先採用 delta 的中繼資料，
        // 但 delta 尚未更新時仍保留公開底稿的版本清單，避免版本紀錄控制項消失。
        game_versions: Array.isArray(資料.game_versions) && 資料.game_versions.length > 0
          ? 資料.game_versions
          : 公開資料.game_versions,
      };
      return 合併後;
    }

    if (資料?.format === "ranking_hidden_delta_v1") {
      const 公開資料 = await 讀取Json(建立公開資料網址(資料.base_path), "讀取排行榜公開底稿失敗");
      const 合併後 = {
        ...公開資料,
        ...資料,
        hidden_reports_included: true,
        ranking_entries: 依順序合併條目(公開資料.ranking_entries, 資料.ranking_entries, 資料.ranking_entry_order),
      };
      delete 合併後.format;
      return 合併後;
    }

    return 資料;
  }

  async function 解析排行榜詳細資料格式(資料) {
    if (資料?.format !== "ranking_detail_hidden_delta_v1") {
      return 資料;
    }

    const 公開資料 = await 讀取Json(建立公開資料網址(資料.base_path), "讀取排行榜報告公開底稿失敗");
    return {
      ...公開資料,
      ...資料,
      format: "ranking_detail_entries_v1",
      hidden_reports_included: true,
      entries: {
        ...(公開資料.entries || {}),
        ...(資料.entries || {}),
      },
    };
  }

  function 成績是否較佳(候選, 目前最佳) {
    if (!目前最佳) {
      return true;
    }

    if ((候選.rdps ?? 0) !== (目前最佳.rdps ?? 0)) {
      return (候選.rdps ?? 0) > (目前最佳.rdps ?? 0);
    }

    if ((候選.通關秒數 ?? Infinity) !== (目前最佳.通關秒數 ?? Infinity)) {
      return (候選.通關秒數 ?? Infinity) < (目前最佳.通關秒數 ?? Infinity);
    }

    if ((候選.adps ?? 0) !== (目前最佳.adps ?? 0)) {
      return (候選.adps ?? 0) > (目前最佳.adps ?? 0);
    }

    return 候選.角色名稱.localeCompare(目前最佳.角色名稱, "zh-Hant-TW") < 0;
  }

  // 同一角色在同一伺服器、同一職業可能因多份 report 或重抓資料重複出現。
  // 前端展示時只保留最佳列；原始歷史資料仍留在 data/rankings，不在 UI 層硬刪。
  function 只保留角色最佳成績(排行列) {
    const 最佳成績索引 = new Map();

    for (const 列 of 排行列) {
      const 鍵值 = `${列.角色名稱}@${列.伺服器}:${列.職業代碼}`;
      const 目前最佳 = 最佳成績索引.get(鍵值);

      if (成績是否較佳(列, 目前最佳)) {
        最佳成績索引.set(鍵值, 列);
      }
    }

    return Array.from(最佳成績索引.values());
  }

  // 讀取舊格式時會把 report -> fight -> player 攤平成排行榜列。
  // 這段邏輯只做呈現用正規化，不改寫 append-only 歷史資料。
  function 展開排行榜列(原始資料, 副本 = 目前副本.value) {
    const 薄索引條目 = 取得排行榜薄索引條目(原始資料);
    if (Array.isArray(薄索引條目)) {
      return 薄索引條目.map((條目) => 建立排行列(條目, 副本));
    }

    if (Array.isArray(原始資料?.ranking_entries)) {
      return 原始資料.ranking_entries.map((條目) => 建立排行列(條目, 副本));
    }

    const 報告集合 = 原始資料?.reports ?? {};
    const 報告列表 = Array.isArray(報告集合) ? 報告集合 : Object.values(報告集合);

    const 攤平排行列 = 報告列表.flatMap((報告) => {
      const 戰鬥列表 = Array.isArray(報告?.fights) ? 報告.fights : [];

      return 戰鬥列表.flatMap((戰鬥) => {
        const 玩家列表 = Array.isArray(戰鬥?.players) ? 戰鬥.players : [];
        const 通關秒數 = 轉為數字(戰鬥?.clear_time_seconds);

        return 玩家列表.map((玩家) => {
          const 版本狀態 = 取得紀錄版本狀態(
            {
              recorded_at_iso: 戰鬥.recorded_at_iso || 報告.report_start_time_iso,
            },
            副本,
          );
          return {
            id: `${報告.report_code}-${戰鬥.fight_id}-${玩家.name}-${玩家.server}`,
            reportCode: 報告.report_code,
            reportUrl: 報告.url,
            fightId: 戰鬥.fight_id ?? null,
            fflogsSourceId: 玩家.fflogs_source_id ?? 玩家.fflogs_id ?? 玩家.source_id ?? null,
            角色名稱: 玩家.name || "未知玩家",
            伺服器: 玩家.server || "未知伺服器",
            職業代碼: 玩家.job || "-",
            職業: 顯示職業名稱(玩家.job),
            rdps: 轉為數字(玩家.rdps ?? 玩家.dps),
            adps: 轉為數字(玩家.adps),
            dps: 轉為數字(玩家.dps),
            active: 計算Active百分比(玩家.active_time_ms, 通關秒數),
            gcd_coverage: 玩家.gcd_coverage ?? null,
            gcd_coverage_status: 玩家.gcd_coverage_status ?? null,
            healingStats: 建立治療統計(玩家.healing_stats),
            tankStats: 建立坦克統計(玩家.tank_stats),
            // 舊格式 fallback 沒有建置層產生的唯一配對結果；Vue 不可掃描同場玩家猜測另一坦／補。
            同場治療: null,
            同場坦克: null,
            activeTimeMs: 轉為數字(玩家.active_time_ms),
            通關秒數,
            紀錄時間: 戰鬥.recorded_at_iso || 報告.report_start_time_iso,
            重複來源數: 1,
            過版紀錄: 版本狀態.is_obsolete_record,
            versionStatus: 版本狀態.version_status,
            versionCutoffIso: 版本狀態.version_cutoff_iso,
          };
        });
      });
    });

    return 只保留角色最佳成績(攤平排行列);
  }

  return {
    排序欄位預設方向,
    排序方向文字,
    下一個排序方向,
    切換排序,
    是否目前排序,
    排序方向圖示,
    排序ARIA,
    排序按鈕標籤,
    排序數值,
    比較排行列,
    建立排行列,
    解析排行榜資料格式,
    解析排行榜詳細資料格式,
    成績是否較佳,
    只保留角色最佳成績,
    展開排行榜列,
  };
}
