<script>
import { ref } from "vue";
import EncounterMenu from "../components/EncounterMenu.vue";
import JobIcon from "../components/JobIcon.vue";
import ReportDetailDialog from "../components/ReportDetailDialog.vue";
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "TeamRankingsPage",
  components: {
    EncounterMenu,
    JobIcon,
    ReportDetailDialog,
  },
  setup() {
    const app = injectRankingApp();
    const 報告彈窗資料 = ref(null);

    function 建立隊伍榜報告Record(紀錄) {
      return {
        report_code: 紀錄.report_code,
        report_url: 紀錄.report_url,
        fight_id: 紀錄.fight_id,
      };
    }

    function 建立隊伍榜報告詳細資料(紀錄) {
      return {
        subtitle: "隊伍榜紀錄",
        title: 紀錄.encounter_name || "隊伍榜",
        identity: `${app.格式化排名(紀錄.顯示排名)} · ${紀錄.players?.length || 0} 人隊伍`,
        record: 建立隊伍榜報告Record(紀錄),
        statusItems: [
          {
            key: "rank",
            label: "排名",
            value: app.格式化排名(紀錄.顯示排名),
            className: "報告彈窗排名項",
          },
          {
            key: "players",
            label: "隊伍成員",
            value: `${紀錄.players?.length || 0} 人`,
          },
          {
            key: "clearTime",
            label: "通關時間",
            value: app.格式化通關時間(紀錄.clear_time_seconds),
            className: "報告彈窗時間項",
          },
        ],
        damageItems: [
          {
            key: "teamRdps",
            label: "隊伍 rDPS",
            value: app.格式化傷害數值(紀錄.total_rdps),
            tooltip: app.統計說明文字("rDPS"),
            tooltipLabel: "rDPS 說明",
            className: "報告彈窗主要數值 報告彈窗全寬項",
          },
        ],
        traceItems: [
          {
            key: "reportFight",
            label: "Report / Fight",
            value: `${紀錄.report_code || "-"}${紀錄.fight_id ? ` · ${紀錄.fight_id}` : ""}`,
          },
          {
            key: "recordedAt",
            label: "紀錄時間",
            value: app.格式化紀錄時間(紀錄.recorded_at_iso),
          },
        ],
      };
    }

    function 開啟隊伍榜報告彈窗(紀錄) {
      報告彈窗資料.value = 建立隊伍榜報告詳細資料(紀錄);
    }

    function 關閉隊伍榜報告彈窗() {
      報告彈窗資料.value = null;
    }

    return {
      ...app,
      報告彈窗資料,
      開啟隊伍榜報告彈窗,
      關閉隊伍榜報告彈窗,
    };
  },
};
</script>

<template>
  <section class="隊伍榜工具列" aria-label="隊伍榜篩選">
    <div class="欄位 副本選單欄位" @focusout="處理隊伍榜副本選單失焦">
      <span>副本</span>
      <div class="副本選單">
        <button
          class="副本選單按鈕"
          type="button"
          :aria-expanded="隊伍榜副本選單開啟"
          aria-haspopup="true"
          @click="切換隊伍榜副本選單"
        >
          <span class="副本選單目前值">{{ 隊伍榜副本選單文字 }}</span>
          <span class="選單箭頭">▾</span>
        </button>

        <EncounterMenu
          v-if="隊伍榜副本選單開啟"
          :分組="隊伍榜副本分組"
          :選取鍵值="隊伍榜副本鍵值"
          標籤="選擇隊伍榜副本"
          @選擇="選擇隊伍榜副本($event.鍵值)"
        />
      </div>
    </div>
    <label v-if="顯示隊伍榜版本篩選" class="欄位">
      <span>版本紀錄</span>
      <select v-model="隊伍榜版本範圍">
        <option v-for="選項 in 版本紀錄範圍選項" :key="選項.value" :value="選項.value">
          {{ 選項.label }}
        </option>
      </select>
    </label>
  </section>

  <section class="隊伍榜區" aria-live="polite">
    <div v-if="隊伍榜讀取中" class="狀態列">讀取隊伍榜中</div>
    <div v-else-if="隊伍榜錯誤訊息" class="狀態列 錯誤">{{ 隊伍榜錯誤訊息 }}</div>
    <div v-else-if="!隊伍榜資料" class="狀態列">正在準備隊伍榜資料</div>
    <div v-else-if="隊伍榜列.length === 0" class="狀態列">目前沒有可顯示的隊伍紀錄</div>

    <template v-else>
      <section class="統計概要" aria-label="隊伍榜概要">
        <div v-for="項目 in 隊伍榜概要" :key="項目.標籤" class="概要項">
          <span>{{ 項目.標籤 }}</span>
          <strong>{{ 項目.數值 }}</strong>
        </div>
      </section>

      <section class="統計面板 統計面板寬" aria-label="隊伍通關紀錄">
        <header class="統計面板標題">
          <h2>{{ 目前隊伍榜副本?.encounter_name || "隊伍榜" }}</h2>
          <span>
            依通關時間排序，同場 8 人公開紀錄
            <template v-if="顯示隊伍榜版本篩選">・{{ 取得版本紀錄範圍文字(有效隊伍榜版本範圍) }}</template>
          </span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格 隊伍榜表格">
            <thead>
              <tr>
                <th scope="col" class="數字">排名</th>
                <th scope="col">副本</th>
                <th scope="col" class="數字">隊伍 rDPS</th>
                <th scope="col">隊伍成員</th>
                <th scope="col" class="數字">通關時間</th>
                <th scope="col">紀錄時間</th>
                <th scope="col">報告</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="紀錄 in 隊伍榜列" :key="紀錄.id" :class="{ 過版紀錄列: 紀錄.is_obsolete_record }">
                <td class="數字 排名 隊伍榜排名" :class="排名色彩類別(紀錄.顯示排名)">
                  <span class="排名徽章" :aria-label="格式化排名(紀錄.顯示排名)">
                    <span v-if="格式化排名(紀錄.顯示排名).startsWith('#')" class="排名井號" aria-hidden="true">
                      #
                    </span>
                    <span class="排名數字">{{ 格式化排名(紀錄.顯示排名).replace(/^#/, "") }}</span>
                  </span>
                </td>
                <td>
                  <span class="比較副本">
                    <small>{{ 紀錄.encounter_category || "副本" }}</small>
                    <strong>{{ 紀錄.encounter_name }}</strong>
                  </span>
                </td>
                <td class="數字">{{ 格式化傷害數值(紀錄.total_rdps) }}</td>
                <td class="隊伍成員欄位">
                  <div class="隊伍成員列表">
                    <button
                      v-for="成員 in 紀錄.players"
                      :key="`${紀錄.id}:${成員.character_name}@${成員.server}:${成員.job}`"
                      class="隊伍成員"
                      type="button"
                      @click="載入使用者成績(成員.character_name, 成員.server)"
                    >
                      <JobIcon
                        class="職業圖示"
                        :code="成員.job"
                      />
                      <span>{{ 成員.character_name }}</span>
                      <small>{{ 成員.server }}</small>
                      <small v-if="顯示Gcd覆蓋率" class="gcd參考文字">GCD {{ 格式化Gcd覆蓋率(成員.gcd_coverage) }}</small>
                    </button>
                  </div>
                </td>
                <td class="數字">{{ 格式化通關時間(紀錄.clear_time_seconds) }}</td>
                <td>
                  <span class="緊湊紀錄時間">
                    <span>{{ 格式化紀錄日期(紀錄.recorded_at_iso) }}</span>
                    <span>{{ 格式化紀錄時刻(紀錄.recorded_at_iso) }}</span>
                  </span>
                </td>
                <td>
                  <button
                    v-if="紀錄.report_code || 紀錄.report_url"
                    class="報告按鈕"
                    type="button"
                    @click="開啟隊伍榜報告彈窗(紀錄)"
                  >
                    報告
                  </button>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>

  <ReportDetailDialog :details="報告彈窗資料" @close="關閉隊伍榜報告彈窗" />
</template>
