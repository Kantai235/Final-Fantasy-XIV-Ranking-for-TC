<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";

const 台灣整數格式 = new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 });

export default {
  name: "AchievementHandbook",
  props: {
    achievements: {
      type: Array,
      default: () => [],
    },
    playerName: {
      type: String,
      default: "",
    },
    totalUsers: {
      type: Number,
      default: 0,
    },
  },
  setup(props) {
    const 成就手冊開啟 = ref(false);
    const 開啟按鈕 = ref(null);
    const 關閉按鈕 = ref(null);

    const 已獲得成就數 = computed(() => props.achievements.filter((成就) => 成就?.已獲得).length);

    function 開啟成就手冊() {
      成就手冊開啟.value = true;
      nextTick(() => 關閉按鈕.value?.focus());
    }

    function 關閉成就手冊() {
      if (!成就手冊開啟.value) {
        return;
      }
      成就手冊開啟.value = false;
      nextTick(() => 開啟按鈕.value?.focus());
    }

    function 處理按鍵(event) {
      if (event.key === "Escape" && 成就手冊開啟.value) {
        event.preventDefault();
        關閉成就手冊();
      }
    }

    function 格式化人數(數值) {
      return Number.isFinite(Number(數值)) ? 台灣整數格式.format(Number(數值)) : "—";
    }

    function 格式化獲得占比(數值) {
      if (數值 === null || 數值 === undefined || 數值 === "") {
        return "統計待更新";
      }
      const 百分比 = Number(數值);
      return Number.isFinite(百分比) ? `${百分比.toFixed(2)}%` : "統計待更新";
    }

    function 成就占比樣式(數值) {
      if (數值 === null || 數值 === undefined || 數值 === "") {
        return { width: "0%" };
      }
      const 百分比 = Number(數值);
      return {
        width: `${Number.isFinite(百分比) ? Math.min(100, Math.max(0, 百分比)) : 0}%`,
      };
    }

    onMounted(() => document.addEventListener("keydown", 處理按鍵));
    onBeforeUnmount(() => document.removeEventListener("keydown", 處理按鍵));

    return {
      成就手冊開啟,
      已獲得成就數,
      開啟按鈕,
      關閉按鈕,
      開啟成就手冊,
      關閉成就手冊,
      格式化人數,
      格式化獲得占比,
      成就占比樣式,
    };
  },
};
</script>

<template>
  <button
    v-if="achievements.length > 0"
    ref="開啟按鈕"
    class="成就手冊浮動按鈕"
    type="button"
    aria-controls="achievement-handbook-dialog"
    :aria-expanded="成就手冊開啟"
    :aria-label="`開啟${playerName || '玩家'}的成就手冊，已取得 ${已獲得成就數} 項`"
    @click="開啟成就手冊"
  >
    <span class="成就手冊浮動光環" aria-hidden="true"></span>
    <svg class="成就手冊浮動書本" viewBox="0 0 64 64" aria-hidden="true">
      <path class="成就手冊書封" d="M11 13.5c8.1-2.1 14.5-.8 21 3.9v35.1c-6.5-4.7-12.9-6-21-3.9V13.5Z" />
      <path class="成就手冊書封" d="M53 13.5c-8.1-2.1-14.5-.8-21 3.9v35.1c6.5-4.7 12.9-6 21-3.9V13.5Z" />
      <path class="成就手冊書頁" d="M15 18.2c5.4-1 9.6.1 14 3.1v24.9c-4.4-2.7-8.8-3.5-14-2.4V18.2Z" />
      <path class="成就手冊書頁" d="M49 18.2c-5.4-1-9.6.1-14 3.1v24.9c4.4-2.7 8.8-3.5 14-2.4V18.2Z" />
      <path class="成就手冊書脊" d="M32 17.6v35" />
      <path class="成就手冊書紋" d="M18.5 25.5c3.6-.2 6.4.6 9 2.2M18.5 32c3.6-.2 6.4.6 9 2.2M45.5 25.5c-3.6-.2-6.4.6-9 2.2M45.5 32c-3.6-.2-6.4.6-9 2.2" />
    </svg>
    <span class="成就手冊浮動進度" aria-hidden="true">{{ 已獲得成就數 }}/{{ achievements.length }}</span>
    <span class="成就手冊浮動提示" aria-hidden="true">成就手冊</span>
  </button>

  <Teleport to="body">
    <div
      v-if="成就手冊開啟"
      class="報告彈窗遮罩 顯示 成就手冊遮罩"
      role="presentation"
      @click.self="關閉成就手冊"
    >
      <section
        id="achievement-handbook-dialog"
        class="報告彈窗 成就手冊彈窗"
        role="dialog"
        aria-modal="true"
        aria-labelledby="achievement-handbook-title"
        aria-describedby="achievement-handbook-description"
        @click.stop
      >
        <header class="報告彈窗標題列 成就手冊標題列">
          <div>
            <p class="報告彈窗副標">角色累積紀錄</p>
            <h2 id="achievement-handbook-title">成就手冊</h2>
            <p id="achievement-handbook-description" class="報告彈窗身份">
              {{ playerName || "目前玩家" }} · 查看目前適用成就與全站稀有度
            </p>
          </div>
          <button
            ref="關閉按鈕"
            class="報告彈窗關閉"
            type="button"
            aria-label="關閉成就手冊"
            @click="關閉成就手冊"
          >
            ×
          </button>
        </header>

        <section class="成就手冊摘要" aria-label="成就取得進度">
          <div class="成就手冊摘要印章" aria-hidden="true">
            <strong>{{ 已獲得成就數 }}</strong>
            <span>/ {{ achievements.length }}</span>
          </div>
          <div>
            <strong>已取得 {{ 已獲得成就數 }} 項成就</strong>
            <span v-if="totalUsers > 0">獲得率以本站收錄的 {{ 格式化人數(totalUsers) }} 位玩家為分母</span>
            <span v-else>全站獲得率統計等待資料更新</span>
          </div>
        </section>

        <ol class="成就手冊清單" aria-label="目前適用成就">
          <li
            v-for="成就 in achievements"
            :key="成就.id"
            class="成就手冊項目"
            :class="{ 已取得: 成就.已獲得, 尚未取得: !成就.已獲得 }"
          >
            <span class="成就手冊狀態圖示" aria-hidden="true">{{ 成就.已獲得 ? "✓" : "◇" }}</span>
            <div class="成就手冊項目內容">
              <div class="成就手冊項目標題">
                <span class="成就手冊分類">{{ 成就.分類 }}</span>
                <strong>{{ 成就.名稱 }}</strong>
                <span class="成就手冊取得狀態">{{ 成就.已獲得 ? "已取得" : "未取得" }}</span>
              </div>
              <p>{{ 成就.說明 }}</p>
              <div class="成就手冊稀有度">
                <span>
                  <strong>{{ 成就.獲得人數 === null ? "—" : 格式化人數(成就.獲得人數) }}</strong>
                  人獲得
                </span>
                <span>{{ 格式化獲得占比(成就.獲得占比) }}</span>
              </div>
              <span class="成就手冊占比軌道" aria-hidden="true">
                <span :style="成就占比樣式(成就.獲得占比)"></span>
              </span>
            </div>
          </li>
        </ol>

        <p class="成就手冊資料說明">
          成就依本站收錄的公開 FFLogs 通關紀錄判定；未取得只代表目前個人成績單沒有符合條件的公開資料。
        </p>
      </section>
    </div>
  </Teleport>
</template>
