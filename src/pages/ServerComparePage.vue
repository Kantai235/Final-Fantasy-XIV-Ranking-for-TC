<script>
import JobIcon from "../components/JobIcon.vue";
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "ServerComparePage",
  components: {
    JobIcon,
  },
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="伺服器對比工具列" aria-label="伺服器對比篩選">
    <label class="欄位 伺服器對比選擇欄位">
      <span>左側伺服器</span>
      <select v-model="伺服器對比左伺服器">
        <option v-for="伺服器 in 伺服器對比選項" :key="`left-${伺服器}`" :value="伺服器">
          {{ 伺服器 }}
        </option>
      </select>
    </label>
    <button class="伺服器交換按鈕" type="button" @click="交換伺服器對比">交換</button>
    <label class="欄位 伺服器對比選擇欄位">
      <span>右側伺服器</span>
      <select v-model="伺服器對比右伺服器">
        <option v-for="伺服器 in 伺服器對比選項" :key="`right-${伺服器}`" :value="伺服器">
          {{ 伺服器 }}
        </option>
      </select>
    </label>
  </section>

  <section class="伺服器對比區" aria-live="polite">
    <div v-if="伺服器對比讀取中" class="狀態列">讀取伺服器對比資料中</div>
    <div v-else-if="伺服器對比錯誤訊息" class="狀態列 錯誤">{{ 伺服器對比錯誤訊息 }}</div>
    <div v-else-if="!伺服器對比資料" class="狀態列">正在準備伺服器對比資料</div>
    <div v-else-if="!伺服器對比已完成" class="狀態列">選擇兩個伺服器後即可比較公開資料</div>

    <template v-else>
      <section class="伺服器對比主卡列" aria-label="伺服器概要">
        <article class="伺服器對比主卡">
          <header>
            <span>左側</span>
            <strong>{{ 伺服器對比左資料.server }}</strong>
          </header>
          <div class="伺服器對比主數據">
            <span>收錄玩家 <strong>{{ 格式化整數(伺服器對比左資料.unique_player_count) }}</strong></span>
            <span>副本通關 <strong>{{ 格式化整數(伺服器對比左資料.encounter_clear_count) }}</strong></span>
            <span>rDPS 中位 <strong>{{ 格式化傷害數值(伺服器對比左資料.rdps_stats?.median) }}</strong></span>
          </div>
        </article>

        <article class="伺服器對比主卡">
          <header>
            <span>右側</span>
            <strong>{{ 伺服器對比右資料.server }}</strong>
          </header>
          <div class="伺服器對比主數據">
            <span>收錄玩家 <strong>{{ 格式化整數(伺服器對比右資料.unique_player_count) }}</strong></span>
            <span>副本通關 <strong>{{ 格式化整數(伺服器對比右資料.encounter_clear_count) }}</strong></span>
            <span>rDPS 中位 <strong>{{ 格式化傷害數值(伺服器對比右資料.rdps_stats?.median) }}</strong></span>
          </div>
        </article>
      </section>

      <section class="統計版面" aria-label="伺服器對比指標">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2>關鍵指標</h2>
            <span>{{ 伺服器對比左資料.server }}・{{ 伺服器對比右資料.server }}</span>
          </header>
          <div class="伺服器對比指標列表">
            <div
              v-for="指標 in 伺服器對比概要"
              :key="指標.標籤"
              class="伺服器對比指標"
              :class="{ 左領先: 指標.勝方 === 'left', 右領先: 指標.勝方 === 'right' }"
            >
              <span>{{ 指標.標籤 }}</span>
              <strong :data-server-label="伺服器對比左資料.server">{{ 指標.左文字 }}</strong>
              <em :data-server-label="伺服器對比右資料.server">{{ 指標.右文字 }}</em>
            </div>
          </div>
        </article>

        <article class="統計面板">
          <header class="統計面板標題">
            <h2>職能分布</h2>
            <span>以伺服器內部職業紀錄比例比較</span>
          </header>
          <div class="伺服器職能對比列表">
            <div v-for="職能 in 伺服器對比職能列" :key="職能.role" class="伺服器職能對比項">
              <span class="隊友職能名稱">
                <JobIcon
                  class="職業圖示"
                  kind="role"
                  :code="職能.role"
                />
                <strong>{{ 職能.名稱 }}</strong>
              </span>
              <div class="伺服器雙向條" aria-hidden="true">
                <span class="左側" :class="職業色彩類別(職能.色彩)" :style="比例條樣式(職能.左比例)"></span>
                <span class="右側" :class="職業色彩類別(職能.色彩)" :style="比例條樣式(職能.右比例)"></span>
              </div>
              <div class="伺服器職能數值">
                <span>{{ 伺服器對比左資料.server }} {{ 格式化百分比(職能.左比例) }}</span>
                <span>{{ 伺服器對比右資料.server }} {{ 格式化百分比(職能.右比例) }}</span>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="統計版面 伺服器熱門職業版面" aria-label="熱門職業">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2>{{ 伺服器對比左資料.server }} 熱門職業</h2>
            <span>前 {{ 伺服器對比職業亮點.left.length }} 個職業</span>
          </header>
          <div class="分布列表">
            <div v-for="職業 in 伺服器對比職業亮點.left" :key="職業.job" class="分布項">
              <div class="分布列">
                <span class="分布職業">
                  <JobIcon
                    class="職業圖示"
                    :code="職業.job"
                  />
                  <strong>{{ 職業.名稱 }}</strong>
                </span>
                <span>{{ 格式化整數(職業.clear_count) }}・{{ 格式化百分比(職業.percentage) }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :class="職業色彩類別(職業.色彩)" :style="比例條樣式(職業.percentage)"></span>
              </div>
            </div>
          </div>
        </article>

        <article class="統計面板">
          <header class="統計面板標題">
            <h2>{{ 伺服器對比右資料.server }} 熱門職業</h2>
            <span>前 {{ 伺服器對比職業亮點.right.length }} 個職業</span>
          </header>
          <div class="分布列表">
            <div v-for="職業 in 伺服器對比職業亮點.right" :key="職業.job" class="分布項">
              <div class="分布列">
                <span class="分布職業">
                  <JobIcon
                    class="職業圖示"
                    :code="職業.job"
                  />
                  <strong>{{ 職業.名稱 }}</strong>
                </span>
                <span>{{ 格式化整數(職業.clear_count) }}・{{ 格式化百分比(職業.percentage) }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :class="職業色彩類別(職業.色彩)" :style="比例條樣式(職業.percentage)"></span>
              </div>
            </div>
          </div>
        </article>
      </section>

      <section class="統計面板 統計面板寬" aria-label="副本對比">
        <header class="統計面板標題">
          <h2>副本對比</h2>
          <span>各副本收錄玩家與全服占比</span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格 伺服器對比表格">
            <thead>
              <tr>
                <th scope="col">副本</th>
                <th scope="col">{{ 伺服器對比左資料.server }}</th>
                <th scope="col">{{ 伺服器對比右資料.server }}</th>
                <th scope="col">差異</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="副本 in 伺服器對比副本列" :key="副本.encounter_key">
                <td>
                  <span class="比較副本">
                    <small>{{ 副本.encounter_category || "副本" }}</small>
                    <strong>{{ 副本.encounter_name }}</strong>
                  </span>
                </td>
                <td
                  class="數字"
                  :class="{ 較低數值: (副本.left?.character_count || 0) < (副本.right?.character_count || 0) }"
                  :data-mobile-label="伺服器對比左資料.server"
                >
                  <strong>{{ 格式化整數(副本.left?.character_count) }}</strong>
                  <small>占比 {{ 格式化百分比(副本.left?.clear_share_percent) }}</small>
                </td>
                <td
                  class="數字"
                  :class="{ 較低數值: (副本.right?.character_count || 0) < (副本.left?.character_count || 0) }"
                  :data-mobile-label="伺服器對比右資料.server"
                >
                  <strong>{{ 格式化整數(副本.right?.character_count) }}</strong>
                  <small>占比 {{ 格式化百分比(副本.right?.clear_share_percent) }}</small>
                </td>
                <td class="數字">
                  <strong>{{ 格式化帶號整數((副本.left?.character_count || 0) - (副本.right?.character_count || 0)) }}</strong>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
