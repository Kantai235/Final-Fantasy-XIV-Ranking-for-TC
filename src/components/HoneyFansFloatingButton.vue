<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "HoneyFansFloatingButton",
  setup() {
    return {
      ...injectRankingApp(),
    };
  },
};
</script>

<template>
  <button
    v-if="頁面模式 !== 'honey-fans'"
    class="蜂蜂粉絲榜浮動按鈕"
    type="button"
    aria-label="開啟 Honey B. Lovely 粉絲榜"
    @click="切換到蜂蜂粉絲榜"
  >
    <span class="蜂蜂粉絲榜浮動光暈" aria-hidden="true"></span>
    <span class="蜂蜂粉絲榜浮動愛心" aria-hidden="true"></span>
    <span class="蜂蜂粉絲榜浮動蜜蜂" aria-hidden="true">
      <span class="蜂蜂粉絲榜浮動蜜蜂翅膀 蜂蜂粉絲榜浮動蜜蜂翅膀左"></span>
      <span class="蜂蜂粉絲榜浮動蜜蜂翅膀 蜂蜂粉絲榜浮動蜜蜂翅膀右"></span>
      <span class="蜂蜂粉絲榜浮動蜜蜂身體">
        <span class="蜂蜂粉絲榜浮動蜜蜂條紋"></span>
      </span>
    </span>
    <span class="蜂蜂粉絲榜浮動文字">
      <span>Honey B.</span>
      <strong>Lovely</strong>
    </span>
  </button>
</template>
