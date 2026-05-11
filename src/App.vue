<script setup>
import { provide, proxyRefs } from "vue";
import AppHeader from "./components/AppHeader.vue";
import PageNavigation from "./components/PageNavigation.vue";
import ActivityPage from "./pages/ActivityPage.vue";
import ComparePage from "./pages/ComparePage.vue";
import GlobalStatsPage from "./pages/GlobalStatsPage.vue";
import JobAnalysisPage from "./pages/JobAnalysisPage.vue";
import RankingPage from "./pages/RankingPage.vue";
import UserProfilePage from "./pages/UserProfilePage.vue";
import { rankingAppKey, useRankingApp } from "./composables/useRankingApp";

const rankingApp = useRankingApp();
const view = proxyRefs(rankingApp);

provide(rankingAppKey, rankingApp);
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
  </main>
</template>

<style src="./styles/app.css"></style>
