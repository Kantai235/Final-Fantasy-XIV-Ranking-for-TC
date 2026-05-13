<script>
import { nextTick, ref } from "vue";
import { injectRankingApp } from "../composables/useRankingApp";

const Telegram連結 = "https://t.me/ffxiv_tc";
const TelegramQrCode網址 = `${import.meta.env.BASE_URL}telegram.png`;

export default {
  name: "AppHeader",
  setup() {
    const Telegram開啟按鈕 = ref(null);
    const Telegram關閉按鈕 = ref(null);
    const 顯示Telegram交流視窗 = ref(false);

    function 開啟Telegram交流視窗() {
      顯示Telegram交流視窗.value = true;
      nextTick(() => Telegram關閉按鈕.value?.focus());
    }

    function 關閉Telegram交流視窗() {
      顯示Telegram交流視窗.value = false;
    }

    function 關閉Telegram交流視窗並回焦() {
      關閉Telegram交流視窗();
      nextTick(() => Telegram開啟按鈕.value?.focus());
    }

    return {
      ...injectRankingApp(),
      Telegram連結,
      TelegramQrCode網址,
      Telegram開啟按鈕,
      Telegram關閉按鈕,
      顯示Telegram交流視窗,
      開啟Telegram交流視窗,
      關閉Telegram交流視窗並回焦,
    };
  },
};
</script>

<template>
<section class="標題區">
  <div>
    <p class="副標">{{ 頁面副標 }}</p>
    <h1>{{ 頁面標題 }}</h1>
  </div>
  <div class="標題右側">
    <p class="更新時間">
      {{ 更新時間文字 }}
    </p>
    <div class="標題操作">
      <button
        ref="Telegram開啟按鈕"
        class="Telegram交流按鈕"
        type="button"
        aria-controls="Telegram交流視窗"
        :aria-expanded="顯示Telegram交流視窗 ? 'true' : 'false'"
        @click="開啟Telegram交流視窗"
      >
        Telegram 交流群
      </button>
      <button class="分享按鈕" type="button" :disabled="正在分享" @click="分享目前頁面">
        {{ 正在分享 ? "分享中" : "分享" }}
      </button>
      <button class="主題切換" type="button" :aria-label="`切換為${主題按鈕文字}模式`" @click="切換主題">
        {{ 目前主題文字 }}
      </button>
    </div>
    <p v-if="分享狀態訊息" class="分享狀態" role="status">
      {{ 分享狀態訊息 }}
    </p>
  </div>
</section>
<Teleport to="body">
  <div
    v-if="顯示Telegram交流視窗"
    class="Telegram視窗遮罩"
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
      <figure class="TelegramQRCode">
        <img class="TelegramQRCode圖片" :src="TelegramQrCode網址" alt="FFXIV 繁中服排行榜 Telegram 交流群 QR Code" />
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
