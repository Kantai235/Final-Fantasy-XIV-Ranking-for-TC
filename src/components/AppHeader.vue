<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "AppHeader",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
<section class="標題區">
  <div>
    <p class="副標">{{ 頁面副標 }}</p>
    <h1>{{ 頁面標題 }}</h1>
  </div>
  <p class="更新時間">
    {{ 更新時間文字 }}
  </p>
  <button class="主題切換" type="button" :aria-label="`切換為${主題按鈕文字}模式`" @click="切換主題">
    {{ 目前主題文字 }}
  </button>
</section>
</template>
