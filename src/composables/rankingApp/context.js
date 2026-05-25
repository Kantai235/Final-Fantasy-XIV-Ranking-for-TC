import { inject } from "vue";

export const rankingAppKey = Symbol("ranking-app-context");

export function injectRankingApp() {
  const app = inject(rankingAppKey);

  if (!app) {
    throw new Error("缺少排行榜應用程式脈絡，請確認 App.vue 已提供 useRankingApp()。");
  }

  return app;
}
