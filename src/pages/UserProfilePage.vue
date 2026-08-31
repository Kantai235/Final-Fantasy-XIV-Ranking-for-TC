<script>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import AchievementDescription from "../components/AchievementDescription.vue";
import AchievementHandbook from "../components/AchievementHandbook.vue";
import EncounterMenu from "../components/EncounterMenu.vue";
import JobIcon from "../components/JobIcon.vue";
import PlayerSearchHistoryPanel from "../components/PlayerSearchHistoryPanel.vue";
import RankingCompactValue from "../components/RankingCompactValue.vue";
import ReportDetailDialog from "../components/ReportDetailDialog.vue";
import { injectRankingApp } from "../composables/useRankingApp";
import { 格式化縮寫總量 } from "../utils/formatters";

export default {
  name: "UserProfilePage",
  components: {
    AchievementDescription,
    AchievementHandbook,
    EncounterMenu,
    JobIcon,
    PlayerSearchHistoryPanel,
    RankingCompactValue,
    ReportDetailDialog,
  },
  setup() {
    const app = injectRankingApp();
    const 報告彈窗資料 = ref(null);
    let 報告讀取序號 = 0;

    function 取值(可能Ref) {
      return 可能Ref && typeof 可能Ref === "object" && "value" in 可能Ref ? 可能Ref.value : 可能Ref;
    }

    function 格式化可選數值(格式化函式, 數值) {
      return 數值 === null || 數值 === undefined || 數值 === "" ? "-" : 格式化函式(數值);
    }

    function 格式化同場治療(成績) {
      const 同場治療 = 成績?.co_healer;
      if (!同場治療?.character_name || !同場治療?.server) {
        return "-";
      }
      return `${app.顯示職業名稱(同場治療.job)} · ${同場治療.character_name} @ ${同場治療.server}`;
    }

    const 個人成績數值欄位 = computed(() => {
      const rdps欄位 = {
        key: "rdps",
        sortKey: "rdps",
        label: "rDPS",
        tooltipKey: "rDPS",
        highlight: true,
        format: (成績) => app.格式化傷害數值(成績?.rdps),
      };

      if (取值(app.目前使用者支援職能) === "healer") {
        return [
          rdps欄位,
          {
            key: "healingHps",
            sortKey: "healingHps",
            label: "HPS",
            tooltipKey: "HPS",
            format: (成績) => app.格式化傷害數值(成績?.healing_stats?.hps),
          },
          {
            key: "pureHealing",
            sortKey: "pureHealing",
            label: "純治療",
            tooltipKey: "純治療",
            format: (成績) => 格式化可選數值(格式化縮寫總量, 成績?.healing_stats?.pure_healing),
            fullFormat: (成績) => 格式化可選數值(app.格式化整數, 成績?.healing_stats?.pure_healing),
          },
          {
            key: "healingProtection",
            sortKey: "healingProtection",
            label: "防護量",
            tooltipKey: "防護量",
            format: (成績) => 格式化可選數值(格式化縮寫總量, 成績?.healing_stats?.protection),
            fullFormat: (成績) => 格式化可選數值(app.格式化整數, 成績?.healing_stats?.protection),
          },
          {
            key: "overhealPercent",
            sortKey: "overhealPercent",
            label: "OH%",
            tooltipKey: "OH%",
            percentage: true,
            format: (成績) => 格式化可選數值(app.格式化百分比, 成績?.healing_stats?.overheal_percent),
          },
          {
            key: "coHealer",
            label: "同場另一補",
            companion: true,
            format: 格式化同場治療,
          },
        ];
      }

      if (取值(app.目前使用者支援職能) === "tank") {
        return [
          rdps欄位,
          {
            key: "damageTaken",
            sortKey: "damageTaken",
            label: "承傷",
            tooltipKey: "承傷",
            format: (成績) => 格式化可選數值(格式化縮寫總量, 成績?.tank_stats?.damage_taken),
            fullFormat: (成績) => 格式化可選數值(app.格式化整數, 成績?.tank_stats?.damage_taken),
          },
          {
            key: "selfHealing",
            sortKey: "selfHealing",
            label: "自補",
            tooltipKey: "自補",
            format: (成績) => 格式化可選數值(格式化縮寫總量, 成績?.tank_stats?.self_healing),
            fullFormat: (成績) => 格式化可選數值(app.格式化整數, 成績?.tank_stats?.self_healing),
          },
          {
            key: "personalProtection",
            sortKey: "personalProtection",
            label: "個人防護",
            tooltipKey: "個人防護",
            format: (成績) => 格式化可選數值(格式化縮寫總量, 成績?.tank_stats?.personal_protection),
            fullFormat: (成績) => 格式化可選數值(app.格式化整數, 成績?.tank_stats?.personal_protection),
          },
          {
            key: "teamProtection",
            sortKey: "teamProtection",
            label: "團隊防護",
            tooltipKey: "團隊防護",
            format: (成績) => 格式化可選數值(格式化縮寫總量, 成績?.tank_stats?.team_protection),
            fullFormat: (成績) => 格式化可選數值(app.格式化整數, 成績?.tank_stats?.team_protection),
          },
          {
            key: "mitigationCoverage",
            sortKey: "mitigationCoverage",
            label: "減傷覆蓋",
            tooltipKey: "減傷覆蓋",
            percentage: true,
            format: (成績) => 格式化可選數值(app.格式化百分比, 成績?.tank_stats?.mitigation_coverage_percent),
          },
        ];
      }

      return [
        {
          key: "dps",
          sortKey: "dps",
          label: "DPS",
          tooltipKey: "DPS",
          format: (成績) => app.格式化傷害數值(成績?.dps),
        },
        rdps欄位,
        {
          key: "adps",
          sortKey: "adps",
          label: "aDPS",
          tooltipKey: "aDPS",
          format: (成績) => app.格式化傷害數值(成績?.adps),
        },
      ];
    });

    function 取得個人成績欄位完整值(欄位, 成績) {
      return typeof 欄位.fullFormat === "function" ? 欄位.fullFormat(成績) : "";
    }

    function 建立個人成績報告分頁標籤(來源, index) {
      return {
        key: 來源.key || `${來源.report_code || "report"}-${來源.fight_id || index}`,
        label: `報告 ${index + 1}`,
        caption: 來源.report_code || "",
      };
    }

    function 建立個人成績報告單筆詳細資料(成績, 副本) {
      const 顯示Gcd = Boolean(取值(app.顯示Gcd覆蓋率));
      const 角色名稱 = 成績.character_name || 取值(app.使用者資料)?.character_name || "個人成績";
      const 伺服器 = 成績.server || 取值(app.使用者伺服器篩選) || "";
      const 職業名稱 = app.顯示職業名稱(成績.job);

      return {
        subtitle: 副本?.encounter_name || 成績.encounter_name || "個人成績歷史",
        title: 角色名稱,
        identity: [伺服器, 職業名稱].filter(Boolean).join(" · "),
        record: 成績,
        statusItems: [
          {
            key: "rank",
            label: "排名",
            value: app.格式化排名(成績.job_rank ?? 成績.rank),
            className: "報告彈窗排名項",
            tooltip: app.統計說明文字("職業 Rank"),
            tooltipLabel: "職業 Rank 說明",
          },
          {
            key: "percentile",
            label: "同職分位",
            value: app.格式化目前同職分位(成績.performance),
            className: ["報告彈窗分位項", app.同職分位色彩類別(成績.performance)].filter(Boolean).join(" "),
            tooltip: app.統計說明文字("同職分位"),
            tooltipLabel: "同職分位說明",
          },
          {
            key: "active",
            label: "Active",
            value: app.格式化Active(成績.active_percent),
            tooltip: app.統計說明文字("Active"),
            tooltipLabel: "Active 說明",
          },
          ...(顯示Gcd
            ? [
                {
                  key: "gcd",
                  label: "GCD",
                  value: app.格式化Gcd覆蓋率(成績.gcd_coverage),
                  tooltip: app.統計說明文字("GCD 覆蓋率"),
                  tooltipLabel: "GCD 覆蓋率說明",
                },
              ]
            : []),
          {
            key: "clearTime",
            label: "通關時間",
            value: app.格式化通關時間(成績.clear_time_seconds),
            className: "報告彈窗時間項",
          },
        ],
        damageItems: 個人成績數值欄位.value.map((欄位) => ({
          key: 欄位.key,
          label: 欄位.label,
          value: typeof 欄位.fullFormat === "function" ? 欄位.fullFormat(成績) : 欄位.format(成績),
          tooltip: 欄位.tooltipKey ? app.統計說明文字(欄位.tooltipKey) : "",
          tooltipLabel: 欄位.tooltipKey ? `${欄位.label} 說明` : "",
          className: 欄位.highlight ? "報告彈窗主要數值" : "",
        })),
        traceItems: [
          {
            key: "reportFight",
            label: "Report / Fight",
            value: `${成績.report_code || "-"}${成績.fight_id ? ` · ${成績.fight_id}` : ""}`,
          },
          {
            key: "recordedAt",
            label: "紀錄時間",
            value: app.格式化紀錄時間(成績.recorded_at_iso),
          },
        ],
      };
    }

    function 建立個人成績報告詳細資料(成績, 副本) {
      const details = 建立個人成績報告單筆詳細資料(成績, 副本);
      const 來源清單 = Array.isArray(成績.report_variants) && 成績.report_variants.length > 1 ? 成績.report_variants : [];
      if (來源清單.length === 0) {
        return details;
      }

      return {
        ...details,
        tabs: 來源清單.map((來源, index) => {
          const 分頁成績 = {
            ...成績,
            ...來源,
            report_variants: 成績.report_variants,
            duplicate_count: 成績.duplicate_count,
            source_reports: 成績.source_reports,
          };
          return {
            ...details,
            ...建立個人成績報告分頁標籤(來源, index),
            ...建立個人成績報告單筆詳細資料(分頁成績, 副本),
          };
        }),
      };
    }

    function 合併個人成績報告詳細資料(成績, 詳細資料) {
      if (!詳細資料) {
        return 成績;
      }

      return {
        ...成績,
        ...詳細資料,
      };
    }

    function 開啟個人成績報告彈窗(成績, 副本) {
      const 本次序號 = ++報告讀取序號;
      報告彈窗資料.value = 建立個人成績報告詳細資料(成績, 副本);
      if ((Array.isArray(成績.report_variants) && 成績.report_variants.length > 1) || !成績.report_detail_path) {
        return;
      }

      app.讀取個人成績報告詳細資料(成績)
        .then((詳細資料) => {
          if (本次序號 !== 報告讀取序號 || !詳細資料) {
            return;
          }
          報告彈窗資料.value = 建立個人成績報告詳細資料(合併個人成績報告詳細資料(成績, 詳細資料), 副本);
        })
        .catch(() => {});
    }

    function 關閉個人成績報告彈窗() {
      報告讀取序號 += 1;
      報告彈窗資料.value = null;
    }

    function 處理趨勢圖外部觸控(event) {
      // 觸控裝置沒有 hover 離開事件；點擊資料點以外的位置時主動收起資訊卡，
      // 桌面版則仍由趨勢圖的 mouseleave 處理，兩種操作都不會改變篩選條件。
      if (event.pointerType !== "touch" || event.target?.closest?.(".趨勢點")) {
        return;
      }

      app.清除所有使用者趨勢選取點();
    }

    onMounted(() => {
      window.addEventListener("pointerdown", 處理趨勢圖外部觸控);
    });

    onBeforeUnmount(() => {
      window.removeEventListener("pointerdown", 處理趨勢圖外部觸控);
    });

    return {
      ...app,
      個人成績數值欄位,
      取得個人成績欄位完整值,
      報告彈窗資料,
      開啟個人成績報告彈窗,
      關閉個人成績報告彈窗,
    };
  },
};
</script>

<template>
  <section class="使用者搜尋區" aria-label="個人成績單查詢">
    <form
      class="使用者搜尋表單 個人成績搜尋表單"
      :class="{
        個人成績搜尋表單簡表模式: 使用者簡表模式,
        個人成績搜尋表單簡表職業篩選: 使用者簡表模式 && 使用者有多個職業,
        個人成績搜尋表單版本篩選: !使用者簡表模式 && 顯示版本紀錄,
      }"
      @submit.prevent="提交使用者搜尋"
    >
      <div class="欄位 使用者搜尋欄位" @focusout="處理玩家搜尋歷史失焦($event, 'user')">
        <label for="個人成績玩家搜尋">玩家 / 伺服器</label>
        <div class="玩家搜尋輸入組">
          <input
            id="個人成績玩家搜尋"
            v-model="使用者搜尋關鍵字"
            type="search"
            list="使用者搜尋建議"
            placeholder="輸入玩家名稱，或選擇「玩家 @ 伺服器」"
            autocomplete="off"
            @focus="開啟玩家搜尋歷史('user')"
          />
          <PlayerSearchHistoryPanel
            field="user"
            :entries="使用者最近搜尋玩家"
            :visible="顯示使用者最近搜尋玩家"
          />
        </div>
        <datalist id="使用者搜尋建議">
          <option v-for="建議 in 使用者搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
            {{ 建議.label }}
          </option>
        </datalist>
      </div>

      <div
        v-if="!使用者簡表模式 || 使用者有多個職業"
        class="欄位 職業選單欄位"
        @focusout="處理使用者職業選單失焦"
      >
        <span>職業</span>
        <div class="職業選單">
          <button
            class="職業選單按鈕"
            type="button"
            :disabled="!使用者資料 || 使用者職業類型選項.length === 0"
            :aria-expanded="使用者職業選單開啟"
            aria-haspopup="true"
            @click="切換使用者職業選單"
          >
            <span class="職業選單目前值">
              <JobIcon
                class="職業圖示"
                :src="使用者職業選單Icon路徑"
              />
              <span>{{ 使用者職業選單文字 }}</span>
            </span>
            <span class="選單箭頭">▾</span>
          </button>

          <div v-if="使用者職業選單開啟" class="職業選單面板">
            <div class="職業選單分類欄" role="menu" aria-label="職業類型">
              <button
                class="職業選單項"
                type="button"
                :class="{ 已選取: !使用者職業類型篩選 && !使用者職業篩選 }"
                @click="清除使用者職業篩選"
              >
                全部職業
              </button>
              <button
                v-for="類型 in 使用者職業類型選項"
                :key="類型.代碼"
                class="職業選單項"
                type="button"
                :class="[職業色彩類別(類型.色彩), { 已選取: 使用者職業類型篩選 === 類型.代碼 }]"
                @click="選擇使用者職業類型(類型.代碼)"
              >
                <JobIcon
                  class="職業圖示"
                  kind="role"
                  :code="類型.代碼"
                />
                <span>{{ 類型.名稱 }}</span>
              </button>
            </div>

            <div class="職業選單職業欄" role="menu" aria-label="職業">
              <template v-if="使用者職業類型篩選 && 使用者職業選項.length > 0">
                <button
                  v-for="職業 in 使用者職業選項"
                  :key="職業.代碼"
                  class="職業選單項"
                  type="button"
                  :class="[職業色彩類別(職業.色彩), { 已選取: 使用者職業篩選 === 職業.代碼 }]"
                  @click="選擇使用者職業(職業.代碼)"
                >
                  <JobIcon
                    class="職業圖示"
                    :code="職業.代碼"
                  />
                  <span>{{ 職業.名稱 }}</span>
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div v-if="!使用者簡表模式 && 顯示版本紀錄" class="欄位 個人成績版本欄位">
        <label for="個人成績版本篩選">版本</label>
        <select
          id="個人成績版本篩選"
          v-model="使用者版本篩選"
          :disabled="!使用者資料 || 使用者版本選項.length === 0"
        >
          <option v-for="版本 in 使用者版本選項" :key="版本.value" :value="版本.value">
            {{ 版本.label }}
          </option>
        </select>
      </div>

      <div v-if="使用者簡表模式" class="欄位 簡表版本欄位">
        <label for="個人成績簡表版本">遊戲版本</label>
        <select
          id="個人成績簡表版本"
          :value="使用者簡表版本"
          @change="設定使用者簡表版本($event.target.value)"
        >
          <option
            v-for="版本 in 個人成績簡表版本選項"
            :key="版本.value"
            :value="版本.value"
            :disabled="版本.available === false"
          >
            {{ 版本.label }}{{ 版本.available === false ? "（待開放）" : "" }}
          </option>
        </select>
      </div>

      <button type="submit">查詢</button>
      <button
        class="簡表模式按鈕"
        type="button"
        :aria-pressed="使用者簡表模式"
        @click="切換使用者簡表模式"
      >
        <span>簡表模式</span>
        <strong>{{ 使用者簡表模式 ? "開啟" : "關閉" }}</strong>
      </button>
    </form>
  </section>

  <section class="個人成績區" aria-live="polite">
    <div v-if="使用者讀取中" class="狀態列">讀取個人成績單中</div>
    <div v-else-if="使用者錯誤訊息" class="狀態列 錯誤">{{ 使用者錯誤訊息 }}</div>
    <div v-else-if="!使用者資料" class="狀態列">輸入玩家名稱後即可查看個人成績單</div>
    <div v-else-if="!使用者簡表模式 && 使用者副本成績.length === 0" class="狀態列">目前沒有符合篩選條件的公開成績</div>

    <template v-else>
      <section v-if="使用者簡表模式" class="個人成績簡表" aria-label="高難副本通關簡表">
        <header class="個人成績簡表標題">
          <div>
            <h2>高難副本通關簡表 · {{ 使用者簡表版本 }}</h2>
            <p>只顯示此版本已開放副本；零式可切換已開放量級。已結束版本不含後續改版的戰鬥；量級四層皆有效通關時會亮起完成勾勾。</p>
          </div>
          <strong>{{ 使用者簡表已收錄通關數 }} / {{ 使用者簡表目標副本數 }} 已收錄</strong>
        </header>

        <div class="個人成績簡表群組列表">
          <section
            v-for="群組 in 使用者簡表群組"
            :key="群組.key"
            class="個人成績簡表群組"
            :class="`個人成績簡表群組-${群組.key}`"
          >
            <header>
              <h3>{{ 群組.name }}</h3>
            </header>
            <div
              v-if="群組.key === 'savage' && 群組.tiers?.length"
              class="零式量級切換"
              role="group"
              aria-label="零式量級"
            >
              <button
                v-for="量級 in 群組.tiers"
                :key="量級.key"
                class="零式量級按鈕"
                :class="{
                  已選取: 群組.selected_tier_key === 量級.key,
                  已完成: 量級.is_current_version_complete,
                }"
                type="button"
                :aria-pressed="群組.selected_tier_key === 量級.key"
                :aria-label="量級.is_current_version_complete
                  ? `${量級.label}：當版本四層全通關`
                  : `${量級.label}：尚未完成當版本四層通關`"
                @click="設定使用者簡表零式量級(量級.key)"
              >
                <span class="零式量級完成圖示" aria-hidden="true">{{ 量級.is_current_version_complete ? "✓" : "○" }}</span>
                <span>{{ 量級.label }}</span>
              </button>
            </div>
            <ul class="簡表副本列表">
              <li
                v-for="副本 in 群組.encounters"
                :key="副本.key"
                class="簡表副本項"
                :class="`簡表狀態-${副本.狀態}`"
              >
                <strong class="簡表副本名稱">{{ 副本.name }}</strong>
                <span v-if="副本.job" class="簡表副本職業">
                  <JobIcon
                    class="職業圖示 簡表副本職業圖示"
                    :code="副本.job"
                    alt=""
                  />
                  <span>{{ 顯示職業名稱(副本.job) }}</span>
                </span>
                <span
                  class="簡表副本狀態"
                  :class="副本.狀態 === 'pr' ? 簡表PR色彩類別(副本.pr_value) : ''"
                  :aria-label="副本.狀態 === 'pr'
                    ? `${副本.name}：${顯示職業名稱(副本.job)}，${格式化PR值(副本.pr_value)}`
                    : 副本.狀態 === 'valid-clear'
                      ? `${副本.name}：已收錄有效版本通關，尚無 PR`
                      : 副本.狀態 === 'obsolete-clear'
                        ? `${副本.name}：僅收錄過版通關`
                        : `${副本.name}：尚未收錄公開通關`"
                >
                  <template v-if="副本.狀態 === 'pr'">{{ 格式化PR值(副本.pr_value) }}</template>
                  <template v-else-if="副本.已收錄通關">✓</template>
                  <template v-else>—</template>
                </span>
              </li>
            </ul>
          </section>
        </div>
      </section>

      <template v-else>
      <section class="個人成績概要" aria-label="個人成績概要">
        <div class="概要項 概要項計數">
          <span>副本數</span>
          <strong>{{ 使用者統計.副本數 }}</strong>
        </div>
        <div class="概要項 概要項計數">
          <span>公開成績</span>
          <strong>{{ 使用者統計.公開成績數 }}</strong>
        </div>
        <div class="概要項 概要項重點">
          <span class="說明標籤">
            <span>最佳 rDPS</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="最佳 rDPS 說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("最佳 rDPS") }}</span>
            </span>
          </span>
          <strong>{{ 格式化傷害數值(使用者統計.最佳成績?.rdps) }}</strong>
        </div>
        <div v-if="顯示Gcd覆蓋率" class="概要項 概要項重點">
          <span class="說明標籤">
            <span>最佳 GCD</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
            </span>
          </span>
          <strong>{{ 格式化Gcd覆蓋率(使用者統計.最高Gcd成績?.gcd_coverage) }}</strong>
        </div>
        <div class="概要項 概要項時間">
          <span>最後紀錄</span>
          <strong>{{ 格式化紀錄時間(使用者統計.最後紀錄時間) }}</strong>
        </div>
      </section>

      <section v-if="使用者徽章.length > 0" class="使用者徽章區" aria-label="個人徽章">
        <article v-for="徽章 in 使用者徽章" :key="徽章.名稱" class="使用者徽章" :class="徽章.樣式類別">
          <strong>{{ 徽章.名稱 }}</strong>
          <AchievementDescription
            as="span"
            :text="徽章.說明"
            :segments="徽章.說明片段"
          />
        </article>
      </section>

      <section v-if="使用者分位亮點.length > 0" class="個人分位區" aria-label="個人分位亮點">
        <header class="成績趨勢標題">
          <h2>個人分位亮點</h2>
          <span>同副本同職業 rDPS 樣本比較</span>
        </header>
        <div class="個人分位列表">
          <article v-for="成績 in 使用者分位亮點" :key="成績.id" class="個人分位項">
            <span class="比較副本">
              <small>{{ 成績.encounter_category || "副本" }}</small>
              <strong>{{ 成績.encounter_name }}</strong>
            </span>
            <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
              <JobIcon
                class="職業圖示 職業標籤圖示"
                :code="成績.job"
              />
              <span>{{ 顯示職業名稱(成績.job) }}</span>
            </span>
            <span class="個人分位主值">
              <strong :class="同職分位色彩類別(成績.performance)">{{ 格式化目前同職分位(成績.performance) }}</strong>
              <small v-if="顯示版本紀錄" class="個人分位版本">{{ 取得個人成績紀錄版本(成績) || "—" }}</small>
            </span>
            <small>
              rDPS {{ 格式化傷害數值(成績.rdps) }}
              <span v-if="顯示Gcd覆蓋率">・GCD {{ 格式化Gcd覆蓋率(成績.gcd_coverage) }}</span>
              ・高於中位 {{ 格式化帶號整數(成績.performance?.delta_to_median) }}
            </small>
          </article>
        </div>
      </section>

      <section v-if="使用者趨勢副本選項.length > 0" class="成績趨勢區" aria-label="成績趨勢">
        <header class="成績趨勢標題">
          <div>
            <h2>成績趨勢</h2>
            <span>依時間排列公開成績</span>
          </div>
          <strong>{{ 使用者成績趨勢.點列表.length }} 筆紀錄</strong>
        </header>
        <div class="成績趨勢控制列">
          <div
            class="欄位 副本選單欄位 成績趨勢篩選欄位"
            @focusout="處理使用者趨勢副本選單失焦"
          >
            <span>副本</span>
            <div class="副本選單">
              <button
                class="副本選單按鈕"
                type="button"
                :aria-expanded="使用者趨勢副本選單開啟"
                aria-haspopup="true"
                @click="切換使用者趨勢副本選單"
              >
                <span class="副本選單目前值">{{ 使用者趨勢副本選單文字 }}</span>
                <span class="選單箭頭">▾</span>
              </button>

              <EncounterMenu
                v-if="使用者趨勢副本選單開啟"
                :分組="使用者趨勢副本分組"
                :選取鍵值="使用者趨勢副本範圍"
                標籤="選擇成績趨勢副本"
                @選擇="設定使用者趨勢副本範圍($event.鍵值)"
              />
            </div>
          </div>

          <div
            class="欄位 職業選單欄位 成績趨勢篩選欄位"
            @focusout="處理使用者趨勢職業選單失焦"
          >
            <span>職業範圍</span>
            <div class="職業選單">
              <button
                class="職業選單按鈕"
                type="button"
                :aria-expanded="使用者趨勢職業選單開啟"
                aria-haspopup="true"
                @click="切換使用者趨勢職業選單"
              >
                <span class="職業選單目前值">
                  <JobIcon class="職業圖示" :src="使用者趨勢職業選單Icon路徑" />
                  <span>{{ 使用者趨勢職業選單文字 }}</span>
                </span>
                <span class="選單箭頭">▾</span>
              </button>

              <div v-if="使用者趨勢職業選單開啟" class="職業選單面板">
                <div class="職業選單分類欄" role="menu" aria-label="成績趨勢職業類型">
                  <button
                    class="職業選單項"
                    type="button"
                    :class="{ 已選取: 使用者趨勢職業範圍 === 'all' }"
                    @click="清除使用者趨勢職業範圍"
                  >
                    全部職業
                  </button>
                  <button
                    v-for="職能 in 使用者趨勢職能選項"
                    :key="職能.value"
                    class="職業選單項"
                    type="button"
                    :class="[
                      職業色彩類別(職能.color),
                      {
                        已展開: 目前使用者趨勢職能?.value === 職能.value,
                        已選取: 使用者趨勢職業範圍 === 職能.value,
                      },
                    ]"
                    @click="選擇使用者趨勢職能(職能.value)"
                  >
                    <JobIcon class="職業圖示" kind="role" :code="職能.value" />
                    <span>{{ 職能.label }}</span>
                  </button>
                </div>

                <div class="職業選單職業欄" role="menu" aria-label="成績趨勢職業">
                  <button
                    v-for="職業 in 使用者趨勢目前職業選項"
                    :key="職業.value"
                    class="職業選單項"
                    type="button"
                    :class="[
                      職業色彩類別(職業.color),
                      { 已選取: 使用者趨勢職業範圍 === 職業.value },
                    ]"
                    @click="選擇使用者趨勢職業(職業.value)"
                  >
                    <JobIcon class="職業圖示" :code="職業.value" />
                    <span>{{ 職業.label }}</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          <div class="欄位 成績趨勢篩選欄位 成績趨勢時間範圍欄位">
            <label>
              <span>時間範圍</span>
              <select
                :value="使用者趨勢時間範圍"
                aria-label="成績趨勢時間範圍"
                @change="設定使用者趨勢時間範圍($event.target.value)"
              >
                <option v-for="選項 in 個人成績趨勢時間範圍選項" :key="選項.value" :value="選項.value">
                  {{ 選項.label }}
                </option>
              </select>
            </label>
            <div v-if="顯示使用者趨勢自訂日期" class="成績趨勢日期區間" aria-label="成績趨勢自訂日期區間">
              <label>
                <span>起</span>
                <input
                  :value="使用者趨勢自訂開始日期"
                  type="date"
                  aria-label="成績趨勢自訂開始日期"
                  @change="設定使用者趨勢自訂開始日期($event.target.value)"
                />
              </label>
              <span>至</span>
              <label>
                <span>迄</span>
                <input
                  :value="使用者趨勢自訂結束日期"
                  type="date"
                  aria-label="成績趨勢自訂結束日期"
                  @change="設定使用者趨勢自訂結束日期($event.target.value)"
                />
              </label>
            </div>
          </div>

          <fieldset class="成績趨勢指標欄位">
            <legend>顯示指標</legend>
            <div class="成績趨勢指標切換" role="group" aria-label="成績趨勢顯示指標">
              <button
                v-for="選項 in 個人成績趨勢指標選項"
                :key="選項.value"
                class="成績趨勢指標按鈕"
                type="button"
                :class="{ 作用中: 使用者趨勢顯示指標 === 選項.value }"
                :aria-pressed="使用者趨勢顯示指標 === 選項.value"
                @click="設定使用者趨勢顯示指標(選項.value)"
              >
                {{ 選項.label }}
              </button>
            </div>
          </fieldset>
        </div>

        <div v-if="使用者成績趨勢.點列表.length > 0" class="統一趨勢圖表">
          <div class="統一趨勢圖表標頭">
            <strong>{{ 使用者成績趨勢.指標名稱 }}</strong>
            <span>滑鼠移至標點或點擊標點查看詳細資料</span>
          </div>
          <div class="統一趨勢繪圖格">
            <div class="統一趨勢Y軸" aria-hidden="true">
              <span
                v-for="刻度 in 使用者成績趨勢.Y軸刻度列表"
                :key="刻度.key"
                :style="{ top: `${(刻度.y / 52) * 100}%` }"
              >
                {{ 使用者成績趨勢.指標 === 'rdps' ? 格式化傷害數值(刻度.value) : Math.round(刻度.value) }}
              </span>
            </div>
            <div
              class="統一趨勢圖表區"
              @mouseleave="清除使用者趨勢選取點()"
              @click="清除使用者趨勢選取點()"
            >
              <div
                class="趨勢圖 統一趨勢圖"
                :aria-label="`所有符合條件公開成績的${使用者成績趨勢.指標名稱}時間軸${使用者成績趨勢.版本切點列表.length > 0 ? `，版本更新：${使用者成績趨勢.版本切點列表.map((切點) => 切點.label).join('、')}` : ''}`"
              >
                <svg class="趨勢曲線圖" viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                  <line
                    v-for="刻度 in 使用者成績趨勢.Y軸刻度列表"
                    :key="刻度.key"
                    class="趨勢格線"
                    x1="2"
                    :y1="刻度.y"
                    x2="98"
                    :y2="刻度.y"
                  ></line>
                  <path
                    v-for="線段 in 使用者成績趨勢.線段列表"
                    :key="線段.key"
                    class="趨勢折線"
                    :class="{ 過版: 線段.過版紀錄 }"
                    :d="線段.path"
                  ></path>
                </svg>
                <span
                  v-if="使用者成績趨勢.版本切點列表.length > 0"
                  class="趨勢版本切點層"
                  aria-hidden="true"
                >
                  <span
                    v-for="(切點, 切點索引) in 使用者成績趨勢.版本切點列表"
                    :key="切點.key"
                    class="趨勢版本切點"
                    :class="{
                      版本標籤第二列: 切點索引 % 2 === 1,
                      版本標籤靠左: 切點.x < 18,
                      版本標籤靠右: 切點.x > 82,
                    }"
                    :style="{ left: `${切點.x}%` }"
                    :title="`${切點.label} 開放`"
                  >
                    <small>{{ 切點.label }}</small>
                  </span>
                </span>
                <span class="趨勢點層">
                  <button
                    v-for="點 in 使用者成績趨勢.點列表"
                    :key="點.id"
                    class="趨勢點"
                    type="button"
                    :class="{
                      過版: 點.過版紀錄,
                      選取中: 使用者趨勢選取點?.id === 點.id,
                    }"
                    :style="{ ...趨勢點樣式(點), '--趨勢點色彩': 職業比較圖色彩(點.job) }"
                    :aria-label="`${格式化紀錄時間(點.recorded_at_iso)}，${點.encounter_name}，${點.job_name}，${格式化PR值(點.pr_value)}，rDPS ${格式化傷害數值(點.rdps)}${點.過版紀錄 ? '，過版紀錄' : ''}`"
                    :aria-pressed="使用者趨勢選取點?.id === 點.id"
                    @mouseenter="設定使用者趨勢選取點(點)"
                    @focus="設定使用者趨勢選取點(點)"
                    @click.stop="設定使用者趨勢選取點(點)"
                    @keydown.esc.stop="清除使用者趨勢選取點()"
                  ></button>
                </span>
              </div>

              <aside
                v-if="使用者趨勢選取點"
                class="趨勢標點資訊"
                :class="{
                  資訊向下: 使用者趨勢選取點.y < 25,
                  資訊靠左: 使用者趨勢選取點.x < 30,
                  資訊靠右: 使用者趨勢選取點.x > 70,
                }"
                :style="趨勢點樣式(使用者趨勢選取點)"
                role="status"
                aria-live="polite"
                @click.stop
              >
                <header>
                  <small>{{ 使用者趨勢選取點.encounter_category || "副本" }}</small>
                  <strong>{{ 使用者趨勢選取點.encounter_name }}</strong>
                </header>
                <dl>
                  <div>
                    <dt>職業</dt>
                    <dd>
                      <JobIcon class="職業圖示 職業標籤圖示" :code="使用者趨勢選取點.job" />
                      <span>{{ 使用者趨勢選取點.job_name }}</span>
                    </dd>
                  </div>
                  <div>
                    <dt>PR 值</dt>
                    <dd :class="同職分位色彩類別({ score_percentile: 使用者趨勢選取點.pr_value })">
                      {{ 格式化PR值(使用者趨勢選取點.pr_value) }}
                    </dd>
                  </div>
                  <div>
                    <dt>rDPS</dt>
                    <dd>{{ 格式化傷害數值(使用者趨勢選取點.rdps) }}</dd>
                  </div>
                  <div>
                    <dt>紀錄時間</dt>
                    <dd>{{ 格式化紀錄時間(使用者趨勢選取點.recorded_at_iso) }}</dd>
                  </div>
                </dl>
              </aside>
            </div>

            <div aria-hidden="true"></div>
            <div class="統一趨勢X軸" aria-hidden="true">
              <span
                v-for="刻度 in 使用者成績趨勢.時間刻度列表"
                :key="刻度.key"
                :class="{ 左邊緣: 刻度.邊緣 === '左', 右邊緣: 刻度.邊緣 === '右' }"
                :style="{ left: `${刻度.x}%` }"
              >
                {{ 格式化紀錄日期(刻度.recorded_at_iso) }}
              </span>
            </div>
          </div>

          <p v-if="使用者成績趨勢.指標 === 'rdps'" class="成績趨勢註記">
            rDPS 會受副本與職業差異影響，請搭配標點資訊解讀。
          </p>
          <p v-if="使用者成績趨勢.略過無時間紀錄數 > 0" class="成績趨勢註記">
            {{ 使用者成績趨勢.略過無時間紀錄數 }} 筆缺少紀錄時間的舊資料未列入時間軸。
          </p>
        </div>

        <div v-else class="成績趨勢空狀態">
          目前篩選條件沒有可繪製的 {{ 使用者成績趨勢.指標名稱 }} 紀錄。
        </div>
      </section>

      <section v-if="使用者隊友列表.length > 0" class="隊友關係區" aria-label="隊友關係">
        <header class="隊友關係標題">
          <h2 class="說明標籤">
            <span>隊友關係</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="隊友關係說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("隊友關係") }}</span>
            </span>
          </h2>
          <span>{{ 使用者隊友列表.length }} 位公開同場玩家</span>
        </header>

        <div class="隊友關係版面">
          <article class="常同場隊友卡">
            <header class="隊友子面板標題">
              <h3>常同場隊友</h3>
              <span>前 {{ 常見隊友.length }} 位</span>
            </header>
            <div class="常同場隊友列表">
              <button
                v-for="隊友 in 常見隊友"
                :key="`${隊友.character_name}@${隊友.server}`"
                class="常同場隊友項"
                type="button"
                @click="開啟隊友成績單(隊友)"
              >
                <span class="常同場隊友主列">
                  <strong>{{ 隊友.character_name }}</strong>
                  <em>{{ 隊友.同場次數 }} 場</em>
                </span>
                <span class="隊友強度條" aria-hidden="true">
                  <span :style="比例條樣式(隊友.強度)"></span>
                </span>
                <span class="常同場隊友資訊">
                  <small>{{ 隊友.server }}</small>
                  <small>{{ 隊友.職業文字 || "多職業" }}</small>
                  <small v-if="隊友.副本文字">{{ 隊友.副本文字 }}</small>
                </span>
              </button>
            </div>
          </article>

          <article class="隊友洞察卡">
            <header class="隊友子面板標題">
              <h3>關係輪廓</h3>
              <span>{{ 隊友關係摘要.關係型態 }}</span>
            </header>
            <div class="隊友摘要格">
              <div class="隊友摘要項">
                <small>同場紀錄</small>
                <strong>{{ 格式化整數(隊友關係摘要.總同場次數) }}</strong>
                <em>{{ 使用者隊友列表.length }} 位玩家</em>
              </div>
              <div class="隊友摘要項">
                <small>重複同場</small>
                <strong>{{ 格式化整數(隊友關係摘要.高頻隊友數) }}</strong>
                <em>2 場以上</em>
              </div>
              <div class="隊友摘要項">
                <small>主要聚集</small>
                <strong>{{ 隊友關係摘要.主要副本?.encounter_name || "-" }}</strong>
                <em v-if="隊友關係摘要.主要副本">
                  {{ 格式化整數(隊友關係摘要.主要副本.teammate_count) }} 位隊友
                </em>
                <em v-else>-</em>
              </div>
              <div class="隊友摘要項">
                <small>最近同場</small>
                <strong>{{ 格式化紀錄時間(隊友關係摘要.最近同場時間) }}</strong>
                <em>{{ 格式化整數(隊友關係摘要.伺服器數) }} 伺服器</em>
              </div>
            </div>
            <p class="隊友洞察文字">{{ 隊友關係摘要.說明 }}</p>
            <div v-if="隊友職能分布.length > 0" class="隊友職能分布">
              <div v-for="職能 in 隊友職能分布" :key="職能.代碼" class="隊友職能項">
                <span class="隊友職能名稱">
                  <JobIcon
                    class="職業圖示"
                    kind="role"
                    :code="職能.代碼"
                    :alt="職能.名稱"
                  />
                  <strong>{{ 職能.名稱 }}</strong>
                </span>
                <em>{{ 格式化整數(職能.人數) }} 位</em>
                <span class="分布條" aria-hidden="true">
                  <span
                    class="分布條填滿"
                    :class="職業色彩類別(職能.色彩)"
                    :style="比例條樣式(職能.強度)"
                  ></span>
                </span>
              </div>
            </div>
          </article>
        </div>

        <div v-if="隊友副本交集.length > 0" class="隊友副本區">
          <header class="隊友副本標題">
            <h3 class="說明標籤">
              <span>同場副本聚集</span>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="同場副本聚集說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("同場副本聚集") }}</span>
              </span>
            </h3>
            <span>顯示同場紀錄主要集中在哪些副本</span>
          </header>
          <div class="隊友副本交集">
            <article v-for="副本 in 隊友副本交集" :key="副本.encounter_key" class="隊友副本項">
              <div class="分布列">
                <strong>{{ 副本.encounter_name }}</strong>
                <span>{{ 格式化整數(副本.co_clear_count) }} 場・{{ 格式化整數(副本.teammate_count) }} 位隊友</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :style="比例條樣式(副本.強度)"></span>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section class="個人成績列表" aria-label="各副本成績">
        <details
          v-for="副本 in 使用者副本成績"
          :key="副本.encounter_key"
          class="個人成績列"
          :class="{
            個人成績列顯示版本: 顯示版本紀錄,
            個人成績列支援職能: 目前使用者支援職能 !== 'damage',
            個人成績列治療職能: 目前使用者支援職能 === 'healer',
            個人成績列坦克職能: 目前使用者支援職能 === 'tank',
          }"
        >
          <summary class="成績列摘要">
            <span class="成績列副本">
              <small>{{ 副本.encounter_category || "副本" }}</small>
              <strong>{{ 副本.encounter_name }}</strong>
            </span>
            <span v-if="副本.best_entry" class="職業標籤 成績列職業" :class="職業色彩類別(職業代碼色彩(副本.best_entry.job))">
              <JobIcon
                class="職業圖示 職業標籤圖示"
                :code="副本.best_entry.job"
              />
              <span>{{ 顯示職業名稱(副本.best_entry.job) }}</span>
            </span>
            <span v-else class="版本紀錄標籤">無有效最佳紀錄</span>
            <span class="成績列數值 成績列數值次要">
              <small class="說明標籤">
                <span>職業 Rank</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="職業 Rank 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("職業 Rank") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化排名(副本.best_entry.job_rank ?? 副本.best_entry.rank) : "無法參考" }}</strong>
              <em
                v-if="副本.best_entry"
                :class="排名分位色彩類別(副本.best_entry.job_rank ?? 副本.best_entry.rank, 取得成績職業總數(副本.best_entry))"
              >
                {{ 格式化目前排名分位(副本.best_entry.job_rank ?? 副本.best_entry.rank, 取得成績職業總數(副本.best_entry)) }}
              </em>
            </span>
            <span class="成績列數值 成績列數值次要">
              <small class="說明標籤">
                <span>同職分位</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="同職分位說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("同職分位") }}</span>
                </span>
              </small>
              <strong :class="副本.best_entry ? 同職分位色彩類別(副本.best_entry.performance) : ''">
                {{ 副本.best_entry ? 格式化目前同職分位(副本.best_entry.performance) : "過時紀錄" }}
              </strong>
              <em v-if="副本.best_entry">中位 {{ 格式化帶號整數(副本.best_entry.performance?.delta_to_median) }}</em>
            </span>
            <span class="成績列數值 成績列數值狀態">
              <small class="說明標籤">
                <span>Active</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化Active(副本.best_entry.active_percent) : "-" }}</strong>
            </span>
            <span v-if="顯示Gcd覆蓋率" class="成績列數值 成績列數值狀態">
              <small class="說明標籤">
                <span>GCD</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化Gcd覆蓋率(副本.best_entry.gcd_coverage) : "-" }}</strong>
            </span>
            <span
              v-for="欄位 in 個人成績數值欄位"
              :key="欄位.key"
              class="成績列數值 成績列數值輸出"
              :class="{
                成績列數值主要: 欄位.highlight,
                成績列數值同場治療: 欄位.companion,
              }"
            >
              <small class="說明標籤">
                <span>{{ 欄位.label }}</span>
                <span v-if="欄位.tooltipKey" class="說明提示">
                  <button class="說明提示按鈕" type="button" :aria-label="`${欄位.label} 說明`">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字(欄位.tooltipKey) }}</span>
                </span>
              </small>
              <strong v-if="欄位.companion" class="同場治療玩家">
                <template v-if="副本.best_entry?.co_healer">
                  <JobIcon
                    class="職業圖示 職業標籤圖示"
                    :code="副本.best_entry.co_healer.job"
                  />
                  <span>{{ 副本.best_entry.co_healer.character_name }} <small>@ {{ 副本.best_entry.co_healer.server }}</small></span>
                </template>
                <template v-else>-</template>
              </strong>
              <strong v-else>
                <RankingCompactValue
                  :display-value="副本.best_entry ? 欄位.format(副本.best_entry) : '-'"
                  :full-value="副本.best_entry ? 取得個人成績欄位完整值(欄位, 副本.best_entry) : ''"
                  :label="欄位.label"
                  :percentage="欄位.percentage"
                />
              </strong>
            </span>
            <span v-if="顯示版本紀錄" class="成績列數值 成績列數值版本">
              <small>版本</small>
              <strong>{{ 副本.best_entry ? 取得個人成績紀錄版本(副本.best_entry) || "—" : "-" }}</strong>
            </span>
            <span class="成績列展開">{{ 副本.public_entries.length }} 筆</span>
          </summary>

          <div class="歷史表格外框">
            <div class="歷史排序控制">
              <label :for="`歷史排序-${副本.encounter_key}`">排序</label>
              <select
                :id="`歷史排序-${副本.encounter_key}`"
                :value="取得使用者歷史排序欄位(副本.encounter_key)"
                @change="設定使用者歷史排序欄位(副本.encounter_key, $event.target.value)"
              >
                <option value="">原始順序</option>
                <template v-for="欄位 in 使用者歷史排序欄位" :key="欄位.value">
                  <option v-if="欄位.value !== 'gameVersion' || 顯示版本紀錄" :value="欄位.value">
                    {{ 欄位.label }}
                  </option>
                </template>
              </select>
              <button
                v-if="取得使用者歷史排序欄位(副本.encounter_key)"
                class="歷史排序方向按鈕"
                type="button"
                :aria-label="`反轉${取得使用者歷史排序欄位標籤(副本.encounter_key)}排序方向`"
                @click="反轉使用者歷史排序方向(副本.encounter_key)"
              >
                {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
              </button>
            </div>
            <table
              class="歷史表格"
              :class="{
                歷史表格顯示版本: 顯示版本紀錄,
                歷史表格支援職能: 目前使用者支援職能 !== 'damage',
                歷史表格治療職能: 目前使用者支援職能 === 'healer',
                歷史表格坦克職能: 目前使用者支援職能 === 'tank',
              }"
            >
              <thead>
                <tr>
                  <th class="歷史紀錄時間欄位" scope="col" :aria-sort="使用者歷史排序ARIA(副本.encounter_key, 'recordedAt')">
                    <button
                      class="表頭排序按鈕"
                      type="button"
                      :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 'recordedAt') }"
                      :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 'recordedAt')"
                      @click="切換使用者歷史排序(副本.encounter_key, 'recordedAt')"
                    >
                      <span>紀錄時間</span>
                      <span v-if="使用者歷史是否目前排序(副本.encounter_key, 'recordedAt')" class="排序箭頭" aria-hidden="true">
                        {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                      </span>
                    </button>
                  </th>
                  <th class="歷史職業欄位" scope="col">職業</th>
                  <th scope="col" class="歷史報告欄位">報告</th>
                  <th scope="col" class="數字" :aria-sort="使用者歷史排序ARIA(副本.encounter_key, 'performance')">
                    <span class="表頭說明標籤">
                      <button
                        class="表頭排序按鈕"
                        type="button"
                        :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 'performance') }"
                        :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 'performance')"
                        @click="切換使用者歷史排序(副本.encounter_key, 'performance')"
                      >
                        <span>同職分位</span>
                        <span v-if="使用者歷史是否目前排序(副本.encounter_key, 'performance')" class="排序箭頭" aria-hidden="true">
                          {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                        </span>
                      </button>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="同職分位說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("同職分位") }}</span>
                      </span>
                    </span>
                  </th>
                  <th scope="col" class="數字" :aria-sort="使用者歷史排序ARIA(副本.encounter_key, 'active')">
                    <span class="表頭說明標籤">
                      <button
                        class="表頭排序按鈕"
                        type="button"
                        :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 'active') }"
                        :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 'active')"
                        @click="切換使用者歷史排序(副本.encounter_key, 'active')"
                      >
                        <span>Active</span>
                        <span v-if="使用者歷史是否目前排序(副本.encounter_key, 'active')" class="排序箭頭" aria-hidden="true">
                          {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                        </span>
                      </button>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                      </span>
                    </span>
                  </th>
                  <th v-show="顯示Gcd覆蓋率" scope="col" class="數字" :aria-sort="使用者歷史排序ARIA(副本.encounter_key, 'gcdCoverage')">
                    <span class="表頭說明標籤">
                      <button
                        class="表頭排序按鈕"
                        type="button"
                        :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 'gcdCoverage') }"
                        :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 'gcdCoverage')"
                        @click="切換使用者歷史排序(副本.encounter_key, 'gcdCoverage')"
                      >
                        <span>GCD</span>
                        <span v-if="使用者歷史是否目前排序(副本.encounter_key, 'gcdCoverage')" class="排序箭頭" aria-hidden="true">
                          {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                        </span>
                      </button>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
                      </span>
                    </span>
                  </th>
                  <th
                    v-for="欄位 in 個人成績數值欄位"
                    :key="欄位.key"
                    scope="col"
                    class="數字 歷史數值欄位"
                    :class="{
                      歷史主要數值欄位: 欄位.highlight,
                      歷史同場治療欄位: 欄位.companion,
                    }"
                    :aria-sort="欄位.sortKey ? 使用者歷史排序ARIA(副本.encounter_key, 欄位.sortKey) : undefined"
                  >
                    <span class="表頭說明標籤">
                      <button
                        v-if="欄位.sortKey"
                        class="表頭排序按鈕"
                        type="button"
                        :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 欄位.sortKey) }"
                        :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 欄位.sortKey)"
                        @click="切換使用者歷史排序(副本.encounter_key, 欄位.sortKey)"
                      >
                        <span>{{ 欄位.label }}</span>
                        <span v-if="使用者歷史是否目前排序(副本.encounter_key, 欄位.sortKey)" class="排序箭頭" aria-hidden="true">
                          {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                        </span>
                      </button>
                      <span v-else>{{ 欄位.label }}</span>
                      <span v-if="欄位.tooltipKey" class="說明提示">
                        <button class="說明提示按鈕" type="button" :aria-label="`${欄位.label} 說明`">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字(欄位.tooltipKey) }}</span>
                      </span>
                    </span>
                  </th>
                  <th
                    v-if="顯示版本紀錄"
                    scope="col"
                    class="數字 歷史版本欄位"
                    :aria-sort="使用者歷史排序ARIA(副本.encounter_key, 'gameVersion')"
                  >
                    <button
                      class="表頭排序按鈕"
                      type="button"
                      :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 'gameVersion') }"
                      :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 'gameVersion')"
                      @click="切換使用者歷史排序(副本.encounter_key, 'gameVersion')"
                    >
                      <span>版本</span>
                      <span v-if="使用者歷史是否目前排序(副本.encounter_key, 'gameVersion')" class="排序箭頭" aria-hidden="true">
                        {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                      </span>
                    </button>
                  </th>
                  <th scope="col" class="數字 歷史通關時間欄位" :aria-sort="使用者歷史排序ARIA(副本.encounter_key, 'clearTime')">
                    <button
                      class="表頭排序按鈕"
                      type="button"
                      :class="{ 作用中: 使用者歷史是否目前排序(副本.encounter_key, 'clearTime') }"
                      :aria-label="使用者歷史排序按鈕標籤(副本.encounter_key, 'clearTime')"
                      @click="切換使用者歷史排序(副本.encounter_key, 'clearTime')"
                    >
                      <span>通關時間</span>
                      <span v-if="使用者歷史是否目前排序(副本.encounter_key, 'clearTime')" class="排序箭頭" aria-hidden="true">
                        {{ 使用者歷史排序方向圖示(副本.encounter_key) }}
                      </span>
                    </button>
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="成績 in 排序使用者歷史成績(副本)" :key="成績.id" :class="{ 過版紀錄列: 成績.is_obsolete_record }">
                  <td class="歷史紀錄時間欄位">{{ 格式化紀錄時間(成績.recorded_at_iso) }}</td>
                  <td class="歷史職業欄位">
                    <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
                      <JobIcon
                        class="職業圖示 職業標籤圖示"
                        :code="成績.job"
                      />
                      <span>{{ 顯示職業名稱(成績.job) }}</span>
                    </span>
                  </td>
                  <td class="歷史報告欄位">
                    <button
                      v-if="成績.report_code || 成績.report_url"
                      class="報告按鈕"
                      type="button"
                      @click="開啟個人成績報告彈窗(成績, 副本)"
                    >
                      報告
                    </button>
                    <span v-else>-</span>
                  </td>
                  <td class="數字" :class="成績.is_obsolete_record ? '' : 同職分位色彩類別(成績.performance)">
                    {{ 成績.is_obsolete_record ? "過時紀錄" : 格式化目前同職分位(成績.performance) }}
                  </td>
                  <td class="數字">{{ 格式化Active(成績.active_percent) }}</td>
                  <td v-show="顯示Gcd覆蓋率" class="數字">{{ 格式化Gcd覆蓋率(成績.gcd_coverage) }}</td>
                  <td
                    v-for="欄位 in 個人成績數值欄位"
                    :key="欄位.key"
                    class="數字 歷史數值欄位"
                    :class="{
                      歷史主要數值欄位: 欄位.highlight,
                      歷史同場治療欄位: 欄位.companion,
                    }"
                    :data-label="欄位.label"
                  >
                    <span v-if="欄位.companion" class="同場治療玩家">
                      <template v-if="成績.co_healer">
                        <JobIcon
                          class="職業圖示 職業標籤圖示"
                          :code="成績.co_healer.job"
                        />
                        <span>{{ 成績.co_healer.character_name }} <small>@ {{ 成績.co_healer.server }}</small></span>
                      </template>
                      <template v-else>-</template>
                    </span>
                    <RankingCompactValue
                      v-else
                      :display-value="欄位.format(成績)"
                      :full-value="取得個人成績欄位完整值(欄位, 成績)"
                      :label="欄位.label"
                      :percentage="欄位.percentage"
                    />
                  </td>
                  <td v-if="顯示版本紀錄" class="數字 歷史版本欄位">{{ 取得個人成績紀錄版本(成績) || "—" }}</td>
                  <td class="數字 歷史通關時間欄位">{{ 格式化通關時間(成績.clear_time_seconds) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </section>
      </template>
    </template>
  </section>

  <AchievementHandbook
    v-if="使用者資料"
    :achievements="使用者成就手冊"
    :player-name="使用者資料.character_name"
    :total-users="使用者成就手冊收錄玩家數"
  />

  <ReportDetailDialog :details="報告彈窗資料" @close="關閉個人成績報告彈窗" />
</template>
