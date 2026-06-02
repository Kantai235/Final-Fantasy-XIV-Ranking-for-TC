<script>
import { nextTick, onBeforeUnmount, ref } from "vue";
import AnnouncementCenter from "./AnnouncementCenter.vue";
import PageNavigation from "./PageNavigation.vue";
import { injectRankingApp } from "../composables/useRankingApp";
import { 顯示Telegram連結 } from "../utils/siteFeatures";

const Telegram連結 = "https://t.me/ffxiv_tc";
const TelegramQrCode網址 = `${import.meta.env.BASE_URL}telegram.png`;

export default {
  name: "AppHeader",
  components: {
    AnnouncementCenter,
    PageNavigation,
  },
  setup() {
    const Telegram開啟按鈕 = ref(null);
    const Telegram關閉按鈕 = ref(null);
    const 顯示Telegram交流視窗 = ref(false);
    const Telegram交流視窗顯示中 = ref(false);
    const TelegramQrCode載入中 = ref(true);
    let Telegram關閉計時器 = null;
    let Telegram動畫序號 = 0;

    function 清除Telegram關閉計時器() {
      if (Telegram關閉計時器 !== null) {
        clearTimeout(Telegram關閉計時器);
        Telegram關閉計時器 = null;
      }
    }

    function 開啟Telegram交流視窗() {
      if (!顯示Telegram連結) {
        return;
      }

      清除Telegram關閉計時器();
      Telegram動畫序號 += 1;
      const 本次動畫序號 = Telegram動畫序號;
      TelegramQrCode載入中.value = true;
      顯示Telegram交流視窗.value = true;
      Telegram交流視窗顯示中.value = false;

      nextTick(() => {
        const 啟動進場動畫 = () => {
          if (本次動畫序號 !== Telegram動畫序號 || !顯示Telegram交流視窗.value) {
            return;
          }

          Telegram交流視窗顯示中.value = true;
          Telegram關閉按鈕.value?.focus();
        };

        if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
          window.requestAnimationFrame(啟動進場動畫);
        } else {
          setTimeout(啟動進場動畫, 0);
        }
      });
    }

    function 關閉Telegram交流視窗() {
      if (!顯示Telegram交流視窗.value) {
        return;
      }

      清除Telegram關閉計時器();
      Telegram動畫序號 += 1;
      Telegram交流視窗顯示中.value = false;
      // 和報告彈窗一樣保留 DOM 到離場動畫結束，避免關閉時瞬間消失。
      Telegram關閉計時器 = setTimeout(() => {
        顯示Telegram交流視窗.value = false;
        Telegram關閉計時器 = null;
      }, 200);
    }

    function 關閉Telegram交流視窗並回焦() {
      關閉Telegram交流視窗();
      setTimeout(() => Telegram開啟按鈕.value?.focus(), 200);
    }

    function 標記TelegramQrCode載入完成() {
      TelegramQrCode載入中.value = false;
    }

    onBeforeUnmount(() => {
      清除Telegram關閉計時器();
    });

    return {
      ...injectRankingApp(),
      Telegram連結,
      TelegramQrCode網址,
      顯示Telegram連結,
      Telegram開啟按鈕,
      Telegram關閉按鈕,
      顯示Telegram交流視窗,
      Telegram交流視窗顯示中,
      TelegramQrCode載入中,
      開啟Telegram交流視窗,
      關閉Telegram交流視窗並回焦,
      標記TelegramQrCode載入完成,
    };
  },
};
</script>

<template>
<section class="標題區">
  <PageNavigation />
  <div class="標題文字">
    <p class="副標">{{ 頁面副標 }}</p>
    <h1>{{ 頁面標題 }}</h1>
  </div>
  <div class="標題右側">
    <p class="更新時間">
      {{ 更新時間文字 }}
    </p>
    <div class="標題操作">
      <button
        v-if="顯示Telegram連結"
        ref="Telegram開啟按鈕"
        class="Telegram交流按鈕"
        type="button"
        aria-controls="Telegram交流視窗"
        :aria-expanded="顯示Telegram交流視窗 ? 'true' : 'false'"
        @click="開啟Telegram交流視窗"
      >
        <span class="標題按鈕圖示" aria-hidden="true">✈</span>
        <span class="標題按鈕文字">Telegram 交流群</span>
      </button>
      <button class="分享按鈕" type="button" :aria-label="正在分享 ? '分享中' : '分享目前頁面'" :disabled="正在分享" @click="分享目前頁面">
        <span v-if="正在分享" class="標題按鈕圖示" aria-hidden="true">…</span>
        <svg v-else class="標題按鈕圖示" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="18" cy="5" r="3"></circle>
          <circle cx="6" cy="12" r="3"></circle>
          <circle cx="18" cy="19" r="3"></circle>
          <path d="M8.7 10.6 15.3 6.4"></path>
          <path d="M8.7 13.4 15.3 17.6"></path>
        </svg>
        <span class="標題按鈕文字">{{ 正在分享 ? "分享中" : "分享" }}</span>
      </button>
      <button
        class="主題切換"
        type="button"
        :disabled="停用主題切換"
        :aria-label="停用主題切換 ? 'Honey B. Lovely 粉絲榜固定由演出控制亮暗模式' : `切換為${主題按鈕文字}模式`"
        :title="停用主題切換 ? 'Honey B. Lovely 粉絲榜固定由演出控制亮暗模式' : ''"
        @click="切換主題"
      >
        <svg v-if="主題模式 === 'dark'" class="標題按鈕圖示" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="4"></circle>
          <path d="M12 2v2"></path>
          <path d="M12 20v2"></path>
          <path d="m4.9 4.9 1.4 1.4"></path>
          <path d="m17.7 17.7 1.4 1.4"></path>
          <path d="M2 12h2"></path>
          <path d="M20 12h2"></path>
          <path d="m4.9 19.1 1.4-1.4"></path>
          <path d="m17.7 6.3 1.4-1.4"></path>
        </svg>
        <svg v-else class="標題按鈕圖示" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M20.4 14.5A8.5 8.5 0 0 1 9.5 3.6 8.7 8.7 0 1 0 20.4 14.5Z"></path>
        </svg>
        <span class="標題按鈕文字">{{ 目前主題文字 }}</span>
      </button>
      <div class="分位顯示切換" role="group" :aria-label="分位顯示切換標籤">
        <button
          v-for="選項 in 分位顯示模式選項"
          :key="選項.value"
          class="分位顯示切換選項"
          type="button"
          :class="{ 作用中: 分位顯示模式 === 選項.value }"
          :aria-pressed="分位顯示模式 === 選項.value ? 'true' : 'false'"
          :title="`同職分位顯示為${選項.label}`"
          @click="設定分位顯示模式(選項.value)"
        >
          {{ 選項.label }}
        </button>
      </div>
      <button
        v-if="頁面模式 === 'honey-fans'"
        class="蜂蜂背景音樂切換"
        type="button"
        :aria-pressed="蜂蜂背景音樂啟用 ? 'true' : 'false'"
        @click="切換蜂蜂背景音樂"
      >
        <svg class="標題按鈕圖示" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M9 18V5l12-2v13"></path>
          <circle cx="6" cy="18" r="3"></circle>
          <circle cx="18" cy="16" r="3"></circle>
        </svg>
        <span class="標題按鈕文字">{{ 蜂蜂背景音樂啟用 ? "關閉背景音樂" : "開啟背景音樂" }}</span>
      </button>
      <AnnouncementCenter />
    </div>
    <p v-if="分享狀態訊息" class="分享狀態" role="status">
      {{ 分享狀態訊息 }}
    </p>
  </div>
</section>
<Teleport to="body">
  <div
    v-if="顯示Telegram連結 && 顯示Telegram交流視窗"
    class="Telegram視窗遮罩"
    :class="{ 顯示: Telegram交流視窗顯示中 }"
    @click.self="關閉Telegram交流視窗並回焦"
    @keydown.escape="關閉Telegram交流視窗並回焦"
  >
    <section
      id="Telegram交流視窗"
      class="Telegram視窗"
      role="dialog"
      aria-modal="true"
      aria-labelledby="Telegram交流標題"
      aria-describedby="Telegram交流說明"
    >
      <button
        ref="Telegram關閉按鈕"
        class="Telegram視窗關閉"
        type="button"
        aria-label="關閉 Telegram 交流群視窗"
        @click="關閉Telegram交流視窗並回焦"
      >
        ×
      </button>
      <div class="Telegram視窗標頭">
        <p class="Telegram視窗副標">FFXIV 繁中服排行榜</p>
        <h2 id="Telegram交流標題">Telegram 交流群</h2>
        <p id="Telegram交流說明">排行榜更新、資料回報與高難度副本交流都會集中在這裡。</p>
      </div>
      <figure class="TelegramQRCode" :class="{ 載入中: TelegramQrCode載入中 }">
        <span v-if="TelegramQrCode載入中" class="TelegramQRCode載入動畫" aria-hidden="true"></span>
        <img
          class="TelegramQRCode圖片"
          :class="{ 載入完成: !TelegramQrCode載入中 }"
          :src="TelegramQrCode網址"
          alt="FFXIV 繁中服排行榜 Telegram 交流群 QR Code"
          @load="標記TelegramQrCode載入完成"
          @error="標記TelegramQrCode載入完成"
        />
      </figure>
      <div class="Telegram視窗行動列">
        <a class="Telegram主要連結" :href="Telegram連結" target="_blank" rel="noopener noreferrer">
          開啟 Telegram 交流群
        </a>
      </div>
    </section>
  </div>
</Teleport>
</template>
