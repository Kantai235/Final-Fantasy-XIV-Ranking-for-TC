<script setup>
import { provide, proxyRefs } from "vue";
import AppFooter from "./components/AppFooter.vue";
import AppHeader from "./components/AppHeader.vue";
import PageNavigation from "./components/PageNavigation.vue";
import ActivityPage from "./pages/ActivityPage.vue";
import ComparePage from "./pages/ComparePage.vue";
import GlobalStatsPage from "./pages/GlobalStatsPage.vue";
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

    <AppFooter />
  </main>
</template>

<style src="./styles/app.css"></style>
