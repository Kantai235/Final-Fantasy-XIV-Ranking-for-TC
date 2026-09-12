import { onBeforeUnmount, onMounted, readonly, ref } from "vue";
import { 取得台灣當日日序 } from "../utils/versionProgress.js";

/** 只推進畫面的日曆時鐘；核對日期及正式／推測版本資料保持由建置層提供。 */
export function useVersionProgressClock() {
  const 目前日 = ref(取得台灣當日日序());
  /** @type {ReturnType<typeof setInterval>|undefined} */
  let 計時器;
  const 更新日期 = () => { 目前日.value = 取得台灣當日日序(); };

  onMounted(() => {
    更新日期();
    // 常駐頁面跨日後最多 30 秒更新；背景分頁或電腦休眠後返回時立即補上日期。
    計時器 = setInterval(更新日期, 30_000);
    window.addEventListener("focus", 更新日期);
    document.addEventListener("visibilitychange", 更新日期);
  });
  onBeforeUnmount(() => {
    clearInterval(計時器);
    window.removeEventListener("focus", 更新日期);
    document.removeEventListener("visibilitychange", 更新日期);
  });
  return readonly(目前日);
}
