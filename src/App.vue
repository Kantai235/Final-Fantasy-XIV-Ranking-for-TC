<script setup>
import { defineAsyncComponent, onMounted, onUnmounted, provide, proxyRefs } from "vue";
import AppFooter from "./components/AppFooter.vue";
import AppHeader from "./components/AppHeader.vue";
import HoneyFansFloatingButton from "./components/HoneyFansFloatingButton.vue";
import PlayerSearchHistoryDialog from "./components/PlayerSearchHistoryDialog.vue";
import { rankingAppKey, useRankingApp } from "./composables/useRankingApp";
import { 預熱職業Icon快取 } from "./domain/jobs";
import { useShareMeta } from "./utils/shareMeta";

const RankingPage = defineAsyncComponent(() => import("./pages/RankingPage.vue"));
const GlobalStatsPage = defineAsyncComponent(() => import("./pages/GlobalStatsPage.vue"));
const JobAnalysisPage = defineAsyncComponent(() => import("./pages/JobAnalysisPage.vue"));
const ActivityPage = defineAsyncComponent(() => import("./pages/ActivityPage.vue"));
const UserProfilePage = defineAsyncComponent(() => import("./pages/UserProfilePage.vue"));
const ComparePage = defineAsyncComponent(() => import("./pages/ComparePage.vue"));
const TeamRankingsPage = defineAsyncComponent(() => import("./pages/TeamRankingsPage.vue"));
const ServerComparePage = defineAsyncComponent(() => import("./pages/ServerComparePage.vue"));
const HoneyFansPage = defineAsyncComponent(() => import("./pages/HoneyFansPage.vue"));

const rankingApp = useRankingApp();
const view = proxyRefs(rankingApp);
let 取消職業Icon預熱 = null;

provide(rankingAppKey, rankingApp);
useShareMeta(rankingApp.分享資訊);

onMounted(() => {
  取消職業Icon預熱 = 預熱職業Icon快取();
});

onUnmounted(() => {
  取消職業Icon預熱?.();
});
</script>

<template>
  <div v-if="view.頁面模式 === 'honey-fans' && view.蜂蜂觀眾粉絲列表.length" class="粉絲榜全頁背景觀眾席" aria-hidden="true">
    <div class="粉絲榜全頁觀眾舞池">
      <span v-for="粉絲 in view.蜂蜂觀眾粉絲列表" :key="粉絲.id" class="粉絲榜觀眾蜜蜂" :style="粉絲.style">
        <span>{{ 粉絲.character_name }}</span>
      </span>
    </div>
  </div>
  <div v-if="view.頁面模式 === 'honey-fans'" class="粉絲榜全頁愛心層" aria-hidden="true">
    <span v-for="愛心 in view.粉絲榜愛心列表" :key="愛心.id" :style="愛心.style"></span>
  </div>

  <main class="頁面" :data-accent="view.主色模式">
    <AppHeader />

    <RankingPage v-if="view.頁面模式 === 'ranking'" />
    <GlobalStatsPage v-else-if="view.頁面模式 === 'stats'" />
    <JobAnalysisPage v-else-if="view.頁面模式 === 'jobs'" />
    <ActivityPage v-else-if="view.頁面模式 === 'activity'" />
    <UserProfilePage v-else-if="view.頁面模式 === 'user'" />
    <ComparePage v-else-if="view.頁面模式 === 'compare'" />
    <TeamRankingsPage v-else-if="view.頁面模式 === 'teams'" />
    <ServerComparePage v-else-if="view.頁面模式 === 'servers'" />
    <HoneyFansPage v-else-if="view.頁面模式 === 'honey-fans'" />

    <AppFooter />
    <PlayerSearchHistoryDialog />
  </main>

  <HoneyFansFloatingButton />
</template>

<style src="./styles/app.css"></style>
