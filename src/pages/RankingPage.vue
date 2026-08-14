<script>
import { computed, ref } from "vue";
import EncounterMenu from "../components/EncounterMenu.vue";
import JobIcon from "../components/JobIcon.vue";
import PlayerSearchHistoryPanel from "../components/PlayerSearchHistoryPanel.vue";
import RankingCompactValue from "../components/RankingCompactValue.vue";
import ReportDetailDialog from "../components/ReportDetailDialog.vue";
import { injectRankingApp } from "../composables/useRankingApp";
import { 格式化縮寫總量 } from "../utils/formatters";

export default {
  name: "RankingPage",
  components: {
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

    const 排行榜數值欄位 = computed(() => {
      const 狀態欄位 = [
        {
          key: "active",
          label: "Active",
          tooltipKey: "Active",
          columnClass: "active欄",
          group: "status",
          percentage: true,
          format: (列) => app.格式化Active(列.active),
        },
        ...(取值(app.顯示Gcd覆蓋率)
          ? [
              {
                key: "gcdCoverage",
                label: "GCD",
                tooltipKey: "GCD 覆蓋率",
                columnClass: "gcd欄",
                group: "status",
                percentage: true,
                format: (列) => app.格式化Gcd覆蓋率(列.gcd_coverage),
              },
            ]
          : []),
      ];
      const rdps欄位 = {
        key: "rdps",
        label: "rDPS",
        tooltipKey: "rDPS",
        columnClass: "傷害欄",
        group: "primary",
        highlight: true,
        format: (列) => app.格式化傷害數值(列.rdps),
      };

      if (取值(app.顯示坦克排行榜欄位)) {
        return [
          ...狀態欄位,
          rdps欄位,
          {
            key: "damageTaken",
            label: "承傷",
            tooltipKey: "承傷",
            columnClass: "支援總量欄",
            group: "primary",
            format: (列) => 格式化可選數值(格式化縮寫總量, 列.tankStats?.damageTaken),
            fullFormat: (列) => 格式化可選數值(app.格式化整數, 列.tankStats?.damageTaken),
          },
          {
            key: "selfHealing",
            label: "自補",
            tooltipKey: "自補",
            columnClass: "支援總量欄",
            group: "primary",
            format: (列) => 格式化可選數值(格式化縮寫總量, 列.tankStats?.selfHealing),
            fullFormat: (列) => 格式化可選數值(app.格式化整數, 列.tankStats?.selfHealing),
          },
          {
            key: "personalProtection",
            label: "個人防護",
            tooltipKey: "個人防護",
            columnClass: "支援總量欄",
            group: "primary",
            format: (列) => 格式化可選數值(格式化縮寫總量, 列.tankStats?.personalProtection),
            fullFormat: (列) => 格式化可選數值(app.格式化整數, 列.tankStats?.personalProtection),
          },
          {
            key: "teamProtection",
            label: "團隊防護",
            tooltipKey: "團隊防護",
            columnClass: "支援總量欄",
            group: "primary",
            format: (列) => 格式化可選數值(格式化縮寫總量, 列.tankStats?.teamProtection),
            fullFormat: (列) => 格式化可選數值(app.格式化整數, 列.tankStats?.teamProtection),
          },
          {
            key: "mitigationCoverage",
            label: "減傷覆蓋",
            tooltipKey: "減傷覆蓋",
            columnClass: "支援百分比欄",
            group: "primary",
            percentage: true,
            format: (列) => 格式化可選數值(app.格式化百分比, 列.tankStats?.mitigationCoveragePercent),
          },
        ];
      }

      if (取值(app.顯示治療排行榜欄位)) {
        return [
          ...狀態欄位,
          rdps欄位,
          {
            key: "healingHps",
            label: "HPS",
            tooltipKey: "HPS",
            columnClass: "傷害欄",
            group: "primary",
            format: (列) => app.格式化傷害數值(列.healingStats?.hps),
          },
          {
            key: "pureHealing",
            label: "純治療",
            tooltipKey: "純治療",
            columnClass: "支援總量欄",
            group: "primary",
            format: (列) => 格式化可選數值(格式化縮寫總量, 列.healingStats?.pureHealing),
            fullFormat: (列) => 格式化可選數值(app.格式化整數, 列.healingStats?.pureHealing),
          },
          {
            key: "healingProtection",
            label: "防護量",
            tooltipKey: "防護量",
            columnClass: "支援總量欄",
            group: "primary",
            format: (列) => 格式化可選數值(格式化縮寫總量, 列.healingStats?.protection),
            fullFormat: (列) => 格式化可選數值(app.格式化整數, 列.healingStats?.protection),
          },
          {
            key: "overhealPercent",
            label: "OH%",
            tooltipKey: "OH%",
            columnClass: "支援百分比欄",
            group: "primary",
            percentage: true,
            format: (列) => 格式化可選數值(app.格式化百分比, 列.healingStats?.overhealPercent),
          },
        ];
      }

      return [
        ...狀態欄位,
        {
          key: "dps",
          label: "DPS",
          tooltipKey: "DPS",
          columnClass: "傷害欄",
          group: "primary",
          format: (列) => app.格式化傷害數值(列.dps),
        },
        rdps欄位,
        {
          key: "adps",
          label: "aDPS",
          tooltipKey: "aDPS",
          columnClass: "傷害欄",
          group: "primary",
          format: (列) => app.格式化傷害數值(列.adps),
        },
      ];
    });

    const 手機主要排行榜欄位 = computed(() => 排行榜數值欄位.value.filter((欄位) => 欄位.group === "primary"));
    const 手機狀態排行榜欄位 = computed(() => 排行榜數值欄位.value.filter((欄位) => 欄位.group === "status"));

    function 取得排行榜欄位完整值(欄位, 列) {
      return typeof 欄位.fullFormat === "function" ? 欄位.fullFormat(列) : "";
    }

    function 是否顯示排行榜欄位完整值提示(欄位, 列) {
      const 完整值 = 取得排行榜欄位完整值(欄位, 列);
      return Boolean(完整值 && 完整值 !== "-" && 完整值 !== 欄位.format(列));
    }

    function 取得同場職能玩家(列) {
      return 取值(app.顯示坦克排行榜欄位) ? 列.同場坦克 : 列.同場治療;
    }

    function 是否顯示同場職能玩家(列) {
      if (取值(app.顯示坦克排行榜欄位)) {
        return Boolean(取值(app.顯示同場坦克職業) && 列.同場坦克);
      }
      return Boolean(取值(app.顯示治療排行榜欄位) && 取值(app.顯示同場治療職業) && 列.同場治療);
    }

    function 建立排行報告詳細資料(列, 排名 = null) {
      const 顯示Gcd = Boolean(取值(app.顯示Gcd覆蓋率));
      const 實際排名 = 排名 ?? 列.原始排名 ?? null;
      const 目前副本 = 取值(app.目前副本);
      const 狀態項目 = [
        {
          key: "rank",
          label: "排名",
          value: app.格式化排名(實際排名),
          className: "報告彈窗排名項",
        },
        {
          key: "active",
          label: "Active",
          value: app.格式化Active(列.active),
          tooltip: app.統計說明文字("Active"),
          tooltipLabel: "Active 說明",
        },
        ...(顯示Gcd
          ? [
              {
                key: "gcd",
                label: "GCD",
                value: app.格式化Gcd覆蓋率(列.gcd_coverage),
                tooltip: app.統計說明文字("GCD 覆蓋率"),
                tooltipLabel: "GCD 覆蓋率說明",
              },
            ]
          : []),
        {
          key: "clearTime",
          label: "通關時間",
          value: app.格式化通關時間(列.通關秒數),
          className: "報告彈窗時間項",
        },
      ];

      return {
        subtitle: 目前副本?.name || "排行榜成績",
        title: 列.角色名稱,
        identity: `${列.伺服器} · ${列.職業}`,
        record: 列,
        statusItems: 狀態項目,
        damageItems: 排行榜數值欄位.value
          .filter((欄位) => 欄位.group === "primary")
          .map((欄位) => ({
            key: 欄位.key,
            label: 欄位.label,
            value: typeof 欄位.fullFormat === "function" ? 欄位.fullFormat(列) : 欄位.format(列),
            tooltip: app.統計說明文字(欄位.tooltipKey),
            tooltipLabel: `${欄位.label} 說明`,
            className: 欄位.highlight ? "報告彈窗主要數值" : "",
          })),
        traceItems: [
          ...(取值(app.顯示版本紀錄) && 列.gameVersion
            ? [
                {
                  key: "gameVersion",
                  label: "繁中服版本",
                  value: app.取得排行榜遊戲版本文字(列.gameVersion),
                },
              ]
            : []),
          {
            key: "reportFight",
            label: "Report / Fight",
            value: `${列.reportCode || "-"}${列.fightId ? ` · ${列.fightId}` : ""}`,
          },
          {
            key: "recordedAt",
            label: "紀錄時間",
            value: app.格式化紀錄時間(列.紀錄時間),
          },
        ],
      };
    }

    function 合併排行列詳細資料(列, 詳細條目) {
      if (!詳細條目) {
        return 列;
      }

      const 詳細列 = app.建立排行列(詳細條目, 取值(app.目前副本));
      return {
        ...列,
        ...詳細列,
        原始排名: 列.原始排名 ?? 詳細列.原始排名,
        職業排名: 列.職業排名 ?? 詳細列.職業排名,
        過版紀錄: 列.過版紀錄,
        versionStatus: 列.versionStatus,
        versionCutoffIso: 列.versionCutoffIso,
        gameVersion: 列.gameVersion || 詳細列.gameVersion,
        healingStats: 詳細列.healingStats || 列.healingStats,
        tankStats: 詳細列.tankStats || 列.tankStats,
        同場治療: 詳細列.同場治療 || 列.同場治療,
        同場坦克: 詳細列.同場坦克 || 列.同場坦克,
        detailId: 列.detailId || 詳細列.detailId,
        hasReportDetail: 列.hasReportDetail || 詳細列.hasReportDetail,
      };
    }

    function 開啟排行報告彈窗(列, 排名 = null) {
      const 本次序號 = ++報告讀取序號;
      報告彈窗資料.value = 建立排行報告詳細資料(列, 排名);
      if (!列.hasReportDetail || 列.reportCode || 列.reportUrl) {
        return;
      }

      app.讀取排行列報告詳細資料(列)
        .then((詳細條目) => {
          if (本次序號 !== 報告讀取序號 || !詳細條目) {
            return;
          }
          報告彈窗資料.value = 建立排行報告詳細資料(合併排行列詳細資料(列, 詳細條目), 排名);
        })
        .catch(() => {});
    }

    function 關閉排行報告彈窗() {
      報告讀取序號 += 1;
      報告彈窗資料.value = null;
    }

    return {
      ...app,
      排行榜數值欄位,
      手機主要排行榜欄位,
      手機狀態排行榜欄位,
      取得排行榜欄位完整值,
      是否顯示排行榜欄位完整值提示,
      取得同場職能玩家,
      是否顯示同場職能玩家,
      報告彈窗資料,
      開啟排行報告彈窗,
      關閉排行報告彈窗,
    };
  },
};
</script>

<template>
<section class="工具列" aria-label="排行榜篩選">
  <div class="欄位 副本選單欄位" @focusout="處理副本選單失焦">
    <span>副本</span>
    <div class="副本選單">
      <button
        class="副本選單按鈕"
        type="button"
        :aria-expanded="副本選單開啟"
        aria-haspopup="true"
        @click="切換副本選單"
      >
        <span class="副本選單目前值">{{ 副本選單文字 }}</span>
        <span class="選單箭頭">▾</span>
      </button>

      <EncounterMenu
        v-if="副本選單開啟"
        :分組="副本分組"
        :選取鍵值="副本鍵值"
        標籤="選擇副本"
        @選擇="選擇副本($event.原始資料)"
      />
    </div>
  </div>

  <label v-if="顯示排行榜版本紀錄" class="欄位">
    <span>版本紀錄</span>
    <select v-model="排行榜遊戲版本選取值">
      <option v-for="選項 in 排行榜遊戲版本選項" :key="選項.patch" :value="選項.patch">
        {{ 選項.label }}
      </option>
    </select>
  </label>

  <label v-if="顯示排行榜紀錄時效" class="欄位">
    <span>紀錄時效</span>
    <select v-model="排行榜版本範圍">
      <option v-for="選項 in 版本紀錄範圍選項" :key="選項.value" :value="選項.value">
        {{ 選項.label }}
      </option>
    </select>
  </label>

  <label class="欄位 排行榜伺服器欄位">
    <span>伺服器</span>
    <select v-model="伺服器篩選">
      <option value="">全部伺服器</option>
      <option v-for="伺服器 in 伺服器選項" :key="伺服器" :value="伺服器">
        {{ 伺服器 }}
      </option>
    </select>
  </label>

  <div class="欄位 職業選單欄位" @focusout="處理職業選單失焦">
    <span>職業</span>
    <div class="職業選單">
      <button
        class="職業選單按鈕"
        type="button"
        :aria-expanded="職業選單開啟"
        aria-haspopup="true"
        @click="切換職業選單"
      >
        <span class="職業選單目前值">
          <JobIcon
            class="職業圖示"
            :src="職業選單Icon路徑"
          />
          <span>{{ 職業選單文字 }}</span>
        </span>
        <span class="選單箭頭">▾</span>
      </button>

      <div v-if="職業選單開啟" class="職業選單面板">
        <div class="職業選單分類欄" role="menu" aria-label="職業類型">
          <button
            class="職業選單項"
            type="button"
            :class="{ 已選取: !職業類型篩選 && !職業篩選 }"
            @click="清除職業篩選"
          >
            全部職業
          </button>
          <button
            v-for="類型 in 職業類型選項"
            :key="類型.代碼"
            class="職業選單項"
            type="button"
            :class="[職業色彩類別(類型.色彩), { 已選取: 職業類型篩選 === 類型.代碼 }]"
            @click="選擇職業類型(類型.代碼)"
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
          <template v-if="職業類型篩選 && 職業選項.length > 0">
            <button
              v-for="職業 in 職業選項"
              :key="職業.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(職業.色彩), { 已選取: 職業篩選 === 職業.代碼 }]"
              @click="選擇職業(職業.代碼)"
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

  <label v-if="顯示坦克排行榜欄位" class="欄位 同場職能切換欄位">
    <span>同場坦克職業</span>
    <span class="核取選項">
      <input v-model="顯示同場坦克職業" type="checkbox" />
      <span>顯示另一位坦克職業</span>
    </span>
  </label>

  <label v-else-if="顯示治療排行榜欄位" class="欄位 同場職能切換欄位">
    <span>同場治療職業</span>
    <span class="核取選項">
      <input v-model="顯示同場治療職業" type="checkbox" />
      <span>顯示另一位治療職業</span>
    </span>
  </label>

  <div class="欄位 搜尋欄位" @focusout="處理玩家搜尋歷史失焦($event, 'ranking')">
    <label for="排行榜玩家搜尋">玩家名稱</label>
    <div class="玩家搜尋輸入組">
      <input
        id="排行榜玩家搜尋"
        v-model="搜尋關鍵字"
        type="search"
        placeholder="搜尋玩家名稱"
        autocomplete="off"
        @focus="開啟玩家搜尋歷史('ranking')"
        @change="記錄排行榜搜尋歷史"
      />
      <PlayerSearchHistoryPanel
        field="ranking"
        :entries="排行榜最近搜尋玩家"
        :visible="顯示排行榜最近搜尋玩家"
      />
    </div>
  </div>
</section>

<section class="表格區" aria-live="polite">
  <div v-if="讀取中" class="狀態列">讀取排行榜資料中</div>
  <div v-else-if="錯誤訊息" class="狀態列 錯誤">{{ 錯誤訊息 }}</div>
  <div v-else-if="過濾後排行列.length === 0" class="狀態列">{{ 排行榜空狀態訊息 }}</div>

  <template v-else>
    <div class="分頁資訊列">
      <p>顯示第 {{ 顯示起始排名 }}-{{ 顯示結束排名 }} 名，共 {{ 過濾後排行列.length }} 筆</p>
      <div class="分頁控制 分頁控制頂部" aria-label="排行榜分頁">
        <button type="button" :disabled="!有上一頁" @click="前一頁">上一頁</button>
        <div class="頁碼群組">
          <label>
            <span>頁碼</span>
            <input
              v-model.number="目前頁碼"
              type="number"
              min="1"
              :max="總頁數"
              inputmode="numeric"
              @change="前往頁碼(目前頁碼)"
            />
          </label>
          <span class="頁數文字">/ {{ 總頁數 }}</span>
        </div>
        <button type="button" :disabled="!有下一頁" @click="下一頁">下一頁</button>
      </div>
    </div>

    <table
      class="排行榜表格"
      :class="{
        坦克排行表格: 顯示坦克排行榜欄位,
        治療排行表格: 顯示治療排行榜欄位,
        支援排行表格: 顯示支援排行榜欄位,
      }"
    >
      <colgroup>
        <col class="排名欄" />
        <col v-if="顯示支援排行榜欄位" class="玩家欄" />
        <col v-if="!顯示支援排行榜欄位" class="玩家名稱欄" />
        <col v-if="!顯示支援排行榜欄位" class="伺服器欄" />
        <col class="職業欄" />
        <col v-for="欄位 in 排行榜數值欄位" :key="欄位.key" :class="欄位.columnClass" />
        <col class="通關時間欄" />
        <col v-show="顯示版本紀錄" class="版本欄" />
        <col class="紀錄時間欄" />
      </colgroup>
      <thead>
        <tr>
          <th class="排行榜排名表頭" scope="col" :aria-sort="排序ARIA('rank')">
            <button
              class="表頭排序按鈕"
              type="button"
              :class="{ 作用中: 是否目前排序('rank') }"
              :aria-label="排序按鈕標籤('rank')"
              @click="切換排序('rank')"
            >
              <span>排名</span>
              <span v-if="是否目前排序('rank')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("rank") }}</span>
            </button>
          </th>
          <th v-if="顯示支援排行榜欄位" class="排行榜玩家表頭" scope="col">玩家</th>
          <th v-if="!顯示支援排行榜欄位" class="排行榜玩家名稱表頭" scope="col">玩家名稱</th>
          <th v-if="!顯示支援排行榜欄位" class="排行榜伺服器表頭" scope="col">伺服器</th>
          <th class="排行榜職業表頭" scope="col">職業</th>
          <th
            v-for="欄位 in 排行榜數值欄位"
            :key="欄位.key"
            scope="col"
            :class="['數字', 欄位.columnClass]"
            :aria-sort="排序ARIA(欄位.key)"
          >
            <span class="表頭說明標籤">
              <button
                class="表頭排序按鈕"
                type="button"
                :class="{ 作用中: 是否目前排序(欄位.key) }"
                :aria-label="排序按鈕標籤(欄位.key)"
                @click="切換排序(欄位.key)"
              >
                <span>{{ 欄位.label }}</span>
                <span v-if="是否目前排序(欄位.key)" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示(欄位.key) }}</span>
              </button>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" :aria-label="`${欄位.label} 說明`">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字(欄位.tooltipKey) }}</span>
              </span>
            </span>
          </th>
          <th class="數字 排行榜通關時間表頭" scope="col" :aria-sort="排序ARIA('clearTime')">
            <button
              class="表頭排序按鈕"
              type="button"
              :class="{ 作用中: 是否目前排序('clearTime') }"
              :aria-label="排序按鈕標籤('clearTime')"
              @click="切換排序('clearTime')"
            >
              <span>通關時間</span>
              <span v-if="是否目前排序('clearTime')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("clearTime") }}</span>
            </button>
          </th>
          <th v-show="顯示版本紀錄" class="排行榜版本表頭" scope="col">版本</th>
          <th class="排行榜紀錄時間表頭" scope="col" :aria-sort="排序ARIA('recordedAt')">
            <button
              class="表頭排序按鈕"
              type="button"
              :class="{ 作用中: 是否目前排序('recordedAt') }"
              :aria-label="排序按鈕標籤('recordedAt')"
              @click="切換排序('recordedAt')"
            >
              <span>紀錄時間</span>
              <span v-if="是否目前排序('recordedAt')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("recordedAt") }}</span>
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        <template v-for="(列, index) in 當頁排行列" :key="列.id">
          <tr :class="{ 過版紀錄列: 列.過版紀錄 }">
          <td class="排名" :class="排名色彩類別(排行列顯示排名(index))">
            <span class="排名徽章" :aria-label="格式化排名(排行列顯示排名(index))">
              <span
                v-if="格式化排名(排行列顯示排名(index)).startsWith('#')"
                class="排名井號"
                aria-hidden="true"
              >
                #
              </span>
              <span class="排名數字">{{ 格式化排名(排行列顯示排名(index)).replace(/^#/, "") }}</span>
            </span>
          </td>
          <td class="排行榜角色欄位">
            <button class="文字連結 排行榜玩家連結" type="button" @click="開啟個人成績單(列)">
              <span class="排行榜玩家名稱">{{ 列.角色名稱 }}</span><span v-if="顯示支援排行榜欄位" class="排行榜玩家伺服器">&nbsp;@&nbsp;{{ 列.伺服器 }}</span>
            </button>
            <span v-if="列.過版紀錄" class="版本紀錄標籤">過版紀錄</span>
            <span v-if="顯示作者相關標示 && 是網站作者(列.角色名稱)" class="說明提示 作者提示">
              <button class="說明提示按鈕 作者勾勾按鈕" type="button" aria-label="網站作者說明">✓</button>
              <span class="說明提示內容" role="tooltip">{{ 作者說明文字 }}</span>
            </span>
            <button
              v-if="列.hasReportDetail || 列.reportCode || 列.reportUrl"
              class="次要連結 報告按鈕"
              type="button"
              @click="開啟排行報告彈窗(列, 排行列顯示排名(index))"
            >
              報告
            </button>
            <div class="手機排行卡">
              <div class="手機排行主列">
                <span class="手機排行職業" :title="列.職業">
                  <JobIcon
                    class="職業圖示"
                    :code="列.職業代碼"
                  />
                </span>
                <div class="手機排行身份列">
                  <span class="手機排行角色名稱列">
                    <button class="文字連結 手機排行角色名稱 排行榜玩家連結" type="button" @click="開啟個人成績單(列)">
                      <span class="排行榜玩家名稱">{{ 列.角色名稱 }}</span><span class="排行榜玩家伺服器 手機排行伺服器">&nbsp;@&nbsp;{{ 列.伺服器 }}</span>
                    </button>
                    <span v-if="列.過版紀錄" class="版本紀錄標籤">過版紀錄</span>
                    <span v-if="顯示作者相關標示 && 是網站作者(列.角色名稱)" class="說明提示 作者提示">
                      <button class="說明提示按鈕 作者勾勾按鈕" type="button" aria-label="網站作者說明">✓</button>
                      <span class="說明提示內容" role="tooltip">{{ 作者說明文字 }}</span>
                    </span>
                  </span>
                </div>
              </div>
              <div class="手機排行傷害列">
                <span
                  v-for="欄位 in 手機主要排行榜欄位"
                  :key="欄位.key"
                  :class="{
                    手機排行重點傷害: 欄位.highlight,
                    包含完整數值提示: 是否顯示排行榜欄位完整值提示(欄位, 列),
                  }"
                >
                  <em>{{ 欄位.label }}</em>
                  <strong>
                    <RankingCompactValue
                      :display-value="欄位.format(列)"
                      :full-value="取得排行榜欄位完整值(欄位, 列)"
                      :label="欄位.label"
                      :percentage="欄位.percentage"
                    />
                  </strong>
                </span>
              </div>
              <div
                class="手機排行資訊列 手機排行完整資訊列"
                :class="{ 顯示手機版本: 顯示版本紀錄 }"
              >
                <span v-for="欄位 in 手機狀態排行榜欄位" :key="欄位.key">
                  <em>{{ 欄位.label }}</em>
                  <strong>
                    <RankingCompactValue
                      :display-value="欄位.format(列)"
                      :percentage="欄位.percentage"
                    />
                  </strong>
                </span>
                <span>
                  <em>通關</em>
                  <strong>{{ 格式化通關時間(列.通關秒數) }}</strong>
                </span>
                <span v-show="顯示版本紀錄">
                  <em>版本</em>
                  <strong>{{ 列.gameVersion || "—" }}</strong>
                </span>
                <span>
                  <em>紀錄</em>
                  <time :datetime="列.紀錄時間 || undefined" :title="格式化紀錄時間(列.紀錄時間)">
                    {{ 格式化紀錄日期(列.紀錄時間) }} {{ 格式化紀錄時刻(列.紀錄時間) }}
                  </time>
                </span>
                <button
                  v-if="列.hasReportDetail || 列.reportCode || 列.reportUrl"
                  class="報告按鈕"
                  type="button"
                  @click="開啟排行報告彈窗(列, 排行列顯示排名(index))"
                >
                  報告
                </button>
              </div>
            </div>
          </td>
          <td v-if="!顯示支援排行榜欄位" class="排行榜伺服器欄位">{{ 列.伺服器 }}</td>
          <td>
            <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.職業代碼))">
              <JobIcon
                class="職業圖示 職業標籤圖示"
                :code="列.職業代碼"
              />
              <span>{{ 列.職業 }}</span>
            </span>
          </td>
          <td
            v-for="欄位 in 排行榜數值欄位"
            :key="欄位.key"
            class="數字"
            :class="{ 包含完整數值提示: 是否顯示排行榜欄位完整值提示(欄位, 列) }"
          >
            <RankingCompactValue
              :display-value="欄位.format(列)"
              :full-value="取得排行榜欄位完整值(欄位, 列)"
              :label="欄位.label"
              :percentage="欄位.percentage"
            />
          </td>
          <td class="數字 排行榜通關時間欄位">{{ 格式化通關時間(列.通關秒數) }}</td>
          <td v-show="顯示版本紀錄" class="數字 排行榜版本欄">{{ 列.gameVersion || "—" }}</td>
          <td>
            <time
              class="緊湊紀錄時間"
              :datetime="列.紀錄時間 || undefined"
              :title="格式化紀錄時間(列.紀錄時間)"
              :aria-label="`紀錄時間 ${格式化紀錄時間(列.紀錄時間)}`"
            >
              <span>{{ 格式化紀錄日期(列.紀錄時間) }}</span>
              <span>{{ 格式化紀錄時刻(列.紀錄時間) }}</span>
            </time>
          </td>
        </tr>
          <tr
            v-if="是否顯示同場職能玩家(列)"
            class="同場職能列"
            :class="{ 過版紀錄列: 列.過版紀錄 }"
          >
          <td class="排名" aria-hidden="true"></td>
          <td class="排行榜角色欄位">
            <button class="文字連結 排行榜玩家連結" type="button" @click="開啟個人成績單(取得同場職能玩家(列))">
              <span class="排行榜玩家名稱">{{ 取得同場職能玩家(列).角色名稱 }}</span><span class="排行榜玩家伺服器">&nbsp;@&nbsp;{{ 取得同場職能玩家(列).伺服器 }}</span>
            </button>
            <div class="手機排行卡 同場職能手機卡">
              <div class="手機排行主列">
                <span class="手機排行職業" :title="取得同場職能玩家(列).職業">
                  <JobIcon class="職業圖示" :code="取得同場職能玩家(列).職業代碼" />
                </span>
                <div class="手機排行身份列">
                  <button class="文字連結 手機排行角色名稱 排行榜玩家連結" type="button" @click="開啟個人成績單(取得同場職能玩家(列))">
                    <span class="排行榜玩家名稱">{{ 取得同場職能玩家(列).角色名稱 }}</span><span class="排行榜玩家伺服器 手機排行伺服器">&nbsp;@&nbsp;{{ 取得同場職能玩家(列).伺服器 }}</span>
                  </button>
                </div>
              </div>
              <div class="手機排行傷害列">
                <span
                  v-for="欄位 in 手機主要排行榜欄位"
                  :key="欄位.key"
                  :class="{
                    手機排行重點傷害: 欄位.highlight,
                    包含完整數值提示: 是否顯示排行榜欄位完整值提示(欄位, 取得同場職能玩家(列)),
                  }"
                >
                  <em>{{ 欄位.label }}</em>
                  <strong>
                    <RankingCompactValue
                      :display-value="欄位.format(取得同場職能玩家(列))"
                      :full-value="取得排行榜欄位完整值(欄位, 取得同場職能玩家(列))"
                      :label="欄位.label"
                      :percentage="欄位.percentage"
                    />
                  </strong>
                </span>
              </div>
              <div class="手機排行資訊列">
                <span v-for="欄位 in 手機狀態排行榜欄位" :key="欄位.key">
                  <em>{{ 欄位.label }}</em>
                  <strong>
                    <RankingCompactValue
                      :display-value="欄位.format(取得同場職能玩家(列))"
                      :percentage="欄位.percentage"
                    />
                  </strong>
                </span>
                <span v-show="顯示版本紀錄">
                  <em>版本</em>
                  <strong>{{ 列.gameVersion || "—" }}</strong>
                </span>
              </div>
            </div>
          </td>
          <td>
            <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(取得同場職能玩家(列).職業代碼))">
              <JobIcon class="職業圖示 職業標籤圖示" :code="取得同場職能玩家(列).職業代碼" />
              <span>{{ 取得同場職能玩家(列).職業 }}</span>
            </span>
          </td>
          <td
            v-for="欄位 in 排行榜數值欄位"
            :key="欄位.key"
            class="數字"
            :class="{
              包含完整數值提示: 是否顯示排行榜欄位完整值提示(欄位, 取得同場職能玩家(列)),
            }"
          >
            <RankingCompactValue
              :display-value="欄位.format(取得同場職能玩家(列))"
              :full-value="取得排行榜欄位完整值(欄位, 取得同場職能玩家(列))"
              :label="欄位.label"
              :percentage="欄位.percentage"
            />
          </td>
          <td class="同場職能重複欄位" aria-hidden="true"></td>
          <td v-show="顯示版本紀錄" class="數字 排行榜版本欄">{{ 列.gameVersion || "—" }}</td>
          <td class="同場職能重複欄位" aria-hidden="true"></td>
          </tr>
        </template>
      </tbody>
    </table>

    <div class="分頁資訊列 分頁資訊列底部">
      <p>每頁 {{ 每頁筆數 }} 筆</p>
      <div class="分頁控制 分頁控制底部" aria-label="排行榜底部分頁">
        <button type="button" :disabled="!有上一頁" @click="前一頁">上一頁</button>
        <span class="頁數文字">第 {{ 安全目前頁碼 }} / {{ 總頁數 }} 頁</span>
        <button type="button" :disabled="!有下一頁" @click="下一頁">下一頁</button>
      </div>
    </div>
  </template>
</section>

<ReportDetailDialog :details="報告彈窗資料" @close="關閉排行報告彈窗" />
</template>
