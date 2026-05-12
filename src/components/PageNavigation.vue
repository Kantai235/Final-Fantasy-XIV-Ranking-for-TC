<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "PageNavigation",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
<nav class="頁面切換" aria-label="頁面切換">
  <button type="button" :class="{ 作用中: 頁面模式 === 'ranking' }" @click="切換到排行榜">排行榜</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'stats' }" @click="切換到全服統計">全服統計</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'user' }" @click="切換到個人成績單">個人成績單</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'compare' }" @click="切換到角色比較">玩家比較</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'teams' }" @click="切換到隊伍榜">隊伍榜</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'servers' }" @click="切換到伺服器對比">伺服器對比</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'jobs' }" @click="切換到職業分析">職業分析</button>
  <button type="button" :class="{ 作用中: 頁面模式 === 'activity' }" @click="切換到近期動態">近期動態</button>
</nav>
</template>
