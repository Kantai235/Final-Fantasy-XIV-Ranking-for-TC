<script>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { injectRankingApp } from "../composables/useRankingApp";
import { 顯示Telegram連結 } from "../utils/siteFeatures";

const Telegram連結 = "https://t.me/ffxiv_tc";

const 頁面切換項目 = [
  { 模式: "ranking", 名稱: "排行榜", 動作: "切換到排行榜" },
  { 模式: "stats", 名稱: "全服統計", 動作: "切換到全服統計" },
  { 模式: "user", 名稱: "個人成績單", 動作: "切換到個人成績單" },
  { 模式: "compare", 名稱: "玩家比較", 動作: "切換到角色比較" },
  { 模式: "teams", 名稱: "隊伍榜", 動作: "切換到隊伍榜" },
  { 模式: "servers", 名稱: "伺服器對比", 動作: "切換到伺服器對比" },
  { 模式: "jobs", 名稱: "職業分析", 動作: "切換到職業分析" },
  { 模式: "activity", 名稱: "近期動態", 動作: "切換到近期動態" },
];

export default {
  name: "PageNavigation",
  setup() {
    const app = injectRankingApp();
    const 手機選單開啟 = ref(false);
    const 頁面選單開關 = ref(null);
    const 頁面選單按鈕文字 = computed(() => {
      const 目前項目 = 頁面切換項目.find((項目) => 項目.模式 === app.頁面模式.value);

      return 目前項目?.名稱 || "頁面切換";
    });

    function 設定頁面選單鎖定(是否鎖定) {
      if (typeof document === "undefined") {
        return;
      }

      document.body.classList.toggle("頁面選單鎖定", 是否鎖定);
    }

    function 開啟頁面選單() {
      手機選單開啟.value = true;
    }

    function 關閉頁面選單() {
      手機選單開啟.value = false;
    }

    function 關閉頁面選單並回到開關() {
      const 原本已開啟 = 手機選單開啟.value;

      關閉頁面選單();

      if (原本已開啟 && typeof window !== "undefined") {
        window.requestAnimationFrame(() => {
          頁面選單開關.value?.focus();
        });
      }
    }

    function 切換頁面(頁面項目) {
      const 切換函式 = app[頁面項目.動作];

      if (typeof 切換函式 === "function") {
        切換函式();
      }

      關閉頁面選單並回到開關();
    }

    function 處理全域按鍵(event) {
      if (event.key === "Escape" && 手機選單開啟.value) {
        event.preventDefault();
        關閉頁面選單並回到開關();
      }
    }

    watch(手機選單開啟, 設定頁面選單鎖定);
    watch(app.頁面模式, 關閉頁面選單);

    onMounted(() => {
      document.addEventListener("keydown", 處理全域按鍵);
    });

    onBeforeUnmount(() => {
      document.removeEventListener("keydown", 處理全域按鍵);
      設定頁面選單鎖定(false);
    });

    return {
      ...app,
      頁面切換項目,
      手機選單開啟,
      頁面選單開關,
      頁面選單按鈕文字,
      Telegram連結,
      顯示Telegram連結,
      開啟頁面選單,
      關閉頁面選單,
      關閉頁面選單並回到開關,
      切換頁面,
    };
  },
};
</script>

<template>
  <div class="頁面切換容器">
    <button
      ref="頁面選單開關"
      class="頁面選單開關"
      type="button"
      aria-controls="page-navigation-drawer"
      :aria-expanded="手機選單開啟"
      @click="開啟頁面選單"
    >
      <span class="頁面選單圖示" aria-hidden="true"></span>
      <span class="頁面選單文字">頁面</span>
      <strong>{{ 頁面選單按鈕文字 }}</strong>
    </button>

    <nav class="頁面切換 桌機頁面切換" aria-label="頁面切換">
      <button
        v-for="項目 in 頁面切換項目"
        :key="項目.模式"
        type="button"
        :class="{ 作用中: 頁面模式 === 項目.模式 }"
        :aria-current="頁面模式 === 項目.模式 ? 'page' : undefined"
        @click="切換頁面(項目)"
      >
        {{ 項目.名稱 }}
      </button>
    </nav>

    <Teleport to="body">
      <div v-if="手機選單開啟" class="頁面切換遮罩" aria-hidden="true" @click="關閉頁面選單"></div>

      <nav
        id="page-navigation-drawer"
        class="頁面切換 手機頁面抽屜"
        :class="{ 展開: 手機選單開啟 }"
        aria-label="頁面切換"
      >
        <div class="頁面切換抽屜標題列">
          <span>頁面切換</span>
          <button class="頁面切換關閉" type="button" aria-label="關閉頁面選單" @click="關閉頁面選單並回到開關">×</button>
        </div>

        <button
          v-for="項目 in 頁面切換項目"
          :key="項目.模式"
          type="button"
          :class="{ 作用中: 頁面模式 === 項目.模式 }"
          :aria-current="頁面模式 === 項目.模式 ? 'page' : undefined"
          @click="切換頁面(項目)"
        >
          {{ 項目.名稱 }}
        </button>

        <a
          v-if="顯示Telegram連結"
          class="頁面切換Telegram連結"
          :href="Telegram連結"
          target="_blank"
          rel="noopener noreferrer"
          @click="關閉頁面選單"
        >
          <span aria-hidden="true">✈</span>
          <span>Telegram 交流群</span>
        </a>
      </nav>
    </Teleport>
  </div>
</template>
