<script setup>
import { provide, proxyRefs } from "vue";
import AppFooter from "./components/AppFooter.vue";
import AppHeader from "./components/AppHeader.vue";
import PageNavigation from "./components/PageNavigation.vue";
import ActivityPage from "./pages/ActivityPage.vue";
import ComparePage from "./pages/ComparePage.vue";
import GlobalStatsPage from "./pages/GlobalStatsPage.vue";
import HoneyFansPage from "./pages/HoneyFansPage.vue";
import JobAnalysisPage from "./pages/JobAnalysisPage.vue";
import RankingPage from "./pages/RankingPage.vue";
import ServerComparePage from "./pages/ServerComparePage.vue";
import TeamRankingsPage from "./pages/TeamRankingsPage.vue";
import UserProfilePage from "./pages/UserProfilePage.vue";
import { rankingAppKey, useRankingApp } from "./composables/useRankingApp";
import { useShareMeta } from "./utils/shareMeta";

const rankingApp = useRankingApp();
const view = proxyRefs(rankingApp);

provide(rankingAppKey, rankingApp);
useShareMeta(rankingApp.分享資訊);
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
    <PageNavigation />

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
  </main>
</template>

<style src="./styles/app.css"></style>
