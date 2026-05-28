<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "PlayerSearchHistoryPanel",
  props: {
    field: {
      type: String,
      required: true,
    },
    entries: {
      type: Array,
      default: () => [],
    },
    visible: {
      type: Boolean,
      default: false,
    },
  },
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <div v-if="visible" class="玩家搜尋歷史面板" aria-label="最近搜尋玩家">
    <header class="玩家搜尋歷史標題列">
      <span>搜尋歷程</span>
      <button
        class="玩家搜尋歷史編輯按鈕"
        type="button"
        @mousedown.prevent
        @click.stop="開啟玩家搜尋歷史管理彈窗"
      >
        編輯
      </button>
    </header>

    <div class="玩家搜尋歷史列表" role="listbox" aria-label="最近搜尋玩家">
      <button
        v-for="建議 in entries"
        :key="建議.key || `${建議.character_name}@${建議.server}`"
        class="玩家搜尋歷史列"
        type="button"
        role="option"
        @mousedown.prevent
        @click="選擇最近搜尋玩家(field, 建議)"
      >
        <span>{{ 建議.value }}</span>
        <small>{{ 建議.label }}</small>
      </button>
    </div>
  </div>
</template>
