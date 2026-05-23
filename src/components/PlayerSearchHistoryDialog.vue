<script>
import { onBeforeUnmount, onMounted } from "vue";
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "PlayerSearchHistoryDialog",
  setup() {
    const app = injectRankingApp();

    function 處理按鍵(event) {
      if (event.key === "Escape" && app.玩家搜尋歷史管理彈窗開啟.value) {
        event.preventDefault();
        app.關閉玩家搜尋歷史管理彈窗();
      }
    }

    onMounted(() => {
      document.addEventListener("keydown", 處理按鍵);
    });

    onBeforeUnmount(() => {
      document.removeEventListener("keydown", 處理按鍵);
    });

    return app;
  },
};
</script>

<template>
  <Teleport to="body">
    <div
      v-if="玩家搜尋歷史管理彈窗開啟"
      class="報告彈窗遮罩 顯示 搜尋歷程彈窗遮罩"
      role="presentation"
      @click.self="關閉玩家搜尋歷史管理彈窗"
      @pointerup.self="關閉玩家搜尋歷史管理彈窗"
    >
      <section
        class="報告彈窗 搜尋歷程彈窗"
        role="dialog"
        aria-modal="true"
        aria-labelledby="player-search-history-dialog-title"
        @click.stop
        @pointerup.stop
      >
        <header class="報告彈窗標題列">
          <div>
            <p class="報告彈窗副標">本機瀏覽器</p>
            <h2 id="player-search-history-dialog-title">搜尋歷程</h2>
            <p class="報告彈窗身份">最多保存 100 筆最近搜尋玩家</p>
          </div>
          <button
            class="報告彈窗關閉"
            type="button"
            aria-label="關閉搜尋歷程視窗"
            @click.stop="關閉玩家搜尋歷史管理彈窗"
            @pointerup.stop="關閉玩家搜尋歷史管理彈窗"
          >
            ×
          </button>
        </header>

        <div class="搜尋歷程管理列">
          <span>{{ 玩家搜尋歷史管理列表.length }} 筆歷程</span>
          <button
            class="搜尋歷程全部刪除按鈕"
            type="button"
            :disabled="玩家搜尋歷史管理列表.length === 0"
            @click="清除所有玩家搜尋歷史"
          >
            刪除所有搜尋歷程
          </button>
        </div>

        <p v-if="玩家搜尋歷史管理列表.length === 0" class="搜尋歷程空狀態">目前沒有搜尋歷程</p>

        <ul v-else class="搜尋歷程清單" aria-label="搜尋歷程清單">
          <li v-for="紀錄 in 玩家搜尋歷史管理列表" :key="紀錄.key" class="搜尋歷程清單列">
            <div class="搜尋歷程角色">
              <strong>{{ 紀錄.value }}</strong>
              <small>{{ 紀錄.label }}</small>
            </div>
            <time class="搜尋歷程時間" :datetime="紀錄.搜尋時間Iso || null">
              <span>{{ 紀錄.搜尋日期文字 }}</span>
              <span v-if="紀錄.搜尋時刻文字">{{ 紀錄.搜尋時刻文字 }}</span>
            </time>
            <button class="搜尋歷程刪除按鈕" type="button" @click="刪除單筆玩家搜尋歷史(紀錄)">刪除</button>
          </li>
        </ul>
      </section>
    </div>
  </Teleport>
</template>
