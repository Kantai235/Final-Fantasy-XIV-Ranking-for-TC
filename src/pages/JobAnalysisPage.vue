<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "JobAnalysisPage",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="職業分析工具列" aria-label="職業分析篩選">
    <div class="欄位 職業選單欄位" @focusout="處理職業分析選單失焦">
      <span>職業</span>
      <div class="職業選單">
        <button
          class="職業選單按鈕"
          type="button"
          :aria-expanded="職業分析選單開啟"
          aria-haspopup="true"
          @click="切換職業分析選單"
        >
          <span class="職業選單目前值">
            <img
              v-if="職業分析選單Icon路徑"
              class="職業圖示"
              :src="職業分析選單Icon路徑"
              alt=""
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
            <span>{{ 職業分析選單文字 }}</span>
          </span>
          <span class="選單箭頭">▾</span>
        </button>

        <div v-if="職業分析選單開啟" class="職業選單面板">
          <div class="職業選單分類欄" role="menu" aria-label="職業類型">
            <button
              v-for="類型 in 職業分析類型選項"
              :key="類型.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(類型.色彩), { 已選取: 職業分析目前類型代碼 === 類型.代碼 }]"
              @click="選擇職業分析類型(類型.代碼)"
            >
              <img
                v-if="職業類型Icon路徑(類型.代碼)"
                class="職業圖示"
                :src="職業類型Icon路徑(類型.代碼)"
                alt=""
                loading="lazy"
                @error="隱藏載入失敗圖片"
              />
              <span>{{ 類型.名稱 }}</span>
            </button>
          </div>

          <div class="職業選單職業欄" role="menu" aria-label="職業">
            <button
              v-for="職業 in 職業分析可選職業"
              :key="職業.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(職業.色彩), { 已選取: 職業分析目前職業代碼 === 職業.代碼 }]"
              @click="選擇職業分析職業(職業.代碼)"
            >
              <img
                v-if="職業Icon路徑(職業.代碼)"
                class="職業圖示"
                :src="職業Icon路徑(職業.代碼)"
                alt=""
                loading="lazy"
                @error="隱藏載入失敗圖片"
              />
              <span>{{ 職業.名稱 }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="職業分析區" aria-live="polite">
    <div v-if="全服統計讀取中" class="狀態列">讀取職業分析資料中</div>
    <div v-else-if="全服統計錯誤訊息" class="狀態列 錯誤">{{ 全服統計錯誤訊息 }}</div>
    <div v-else-if="!全服統計資料" class="狀態列">正在準備職業分析資料</div>
    <div v-else-if="!職業分析目前職業" class="狀態列">目前沒有可分析的職業資料</div>

    <template v-else>
      <section class="職業焦點卡" aria-label="職業概要">
        <header class="職業焦點標題">
          <span class="職業焦點圖示" :class="職業色彩類別(職業代碼色彩(職業分析目前職業.job))">
            <img
              v-if="職業Icon路徑(職業分析目前職業.job)"
              :src="職業Icon路徑(職業分析目前職業.job)"
              :alt="顯示職業名稱(職業分析目前職業.job)"
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
          </span>
          <span>
            <small>{{ 職業分析目前職業.role_name }}</small>
            <strong>{{ 顯示職業名稱(職業分析目前職業.job) }}</strong>
          </span>
        </header>

        <div class="職業分析概要">
          <div v-for="項目 in 職業分析概要" :key="項目.標籤" class="概要項">
            <span>{{ 項目.標籤 }}</span>
            <strong>{{ 項目.數值 }}</strong>
          </div>
        </div>
      </section>

      <section class="統計版面" aria-label="職業副本與伺服器分析">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2>副本分布</h2>
            <span>該職業公開通關分布</span>
          </header>
          <div class="分布列表">
            <div v-for="副本 in 職業分析副本列" :key="副本.encounter_key" class="分布項">
              <div class="分布列">
                <strong>{{ 副本.encounter_name }}</strong>
                <span>{{ 格式化整數(副本.數量) }} 紀錄・{{ 格式化百分比(副本.職業內佔比) }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span
                  class="分布條填滿"
                  :class="職業色彩類別(職業代碼色彩(職業分析目前職業.job))"
                  :style="比例條樣式(副本.職業內佔比)"
                ></span>
              </div>
              <small class="職業分析補充">副本內佔比 {{ 格式化百分比(副本.副本內佔比) }}</small>
            </div>
          </div>
        </article>

        <article class="統計面板">
          <header class="統計面板標題">
            <h2>伺服器分布</h2>
            <span>該職業全服落點</span>
          </header>
          <div class="分布列表">
            <div v-for="伺服器 in 職業分析伺服器列" :key="伺服器.server" class="分布項">
              <div class="分布列">
                <strong>{{ 伺服器.server }}</strong>
                <span>{{ 格式化整數(伺服器.數量) }} 紀錄・{{ 格式化百分比(伺服器.全職業佔比) }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span
                  class="分布條填滿"
                  :class="職業色彩類別(職業代碼色彩(職業分析目前職業.job))"
                  :style="比例條樣式(伺服器.全職業佔比)"
                ></span>
              </div>
              <small class="職業分析補充">伺服器內佔比 {{ 格式化百分比(伺服器.伺服器內佔比) }}</small>
            </div>
          </div>
        </article>
      </section>
    </template>
  </section>
</template>
