<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "TeamRankingsPage",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="隊伍榜工具列" aria-label="隊伍榜篩選">
    <label class="欄位">
      <span>副本</span>
      <select :value="隊伍榜副本鍵值" @change="選擇隊伍榜副本($event.target.value)">
        <option value="all">全部副本最速</option>
        <option v-for="副本 in 隊伍榜副本列表" :key="副本.encounter_key" :value="副本.encounter_key">
          {{ 副本.encounter_name }}
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
          <h2>{{ 目前隊伍榜副本?.encounter_name || "全部副本最速" }}</h2>
          <span>依通關時間排序，同場 8 人公開紀錄</span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格 隊伍榜表格">
            <thead>
              <tr>
                <th scope="col" class="數字">排名</th>
                <th scope="col">副本</th>
                <th scope="col" class="數字">通關時間</th>
                <th scope="col" class="數字">隊伍 rDPS</th>
                <th scope="col">隊伍成員</th>
                <th scope="col">報告</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="紀錄 in 隊伍榜列" :key="紀錄.id">
                <td class="數字">{{ 格式化排名(紀錄.顯示排名) }}</td>
                <td>
                  <span class="比較副本">
                    <small>{{ 紀錄.encounter_category || "副本" }}</small>
                    <strong>{{ 紀錄.encounter_name }}</strong>
                  </span>
                </td>
                <td class="數字">{{ 格式化通關時間(紀錄.clear_time_seconds) }}</td>
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
                      <img
                        v-if="職業Icon路徑(成員.job)"
                        class="職業圖示"
                        :src="職業Icon路徑(成員.job)"
                        alt=""
                        loading="lazy"
                        @error="隱藏載入失敗圖片"
                      />
                      <span>{{ 成員.character_name }}</span>
                      <small>{{ 成員.server }}</small>
                    </button>
                  </div>
                </td>
                <td>
                  <a v-if="紀錄.report_url" :href="紀錄.report_url" target="_blank" rel="noreferrer">FFLogs</a>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
