import { createApp } from "vue";
import App from "./App.vue";
import { initAnalytics } from "./analytics";

initAnalytics();
createApp(App).mount("#app");
