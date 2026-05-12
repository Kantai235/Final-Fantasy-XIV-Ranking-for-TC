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
  <div class="標題右側">
    <p class="更新時間">
      {{ 更新時間文字 }}
    </p>
    <div class="標題操作">
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
</template>
