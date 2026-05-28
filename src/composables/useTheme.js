import { computed, ref } from "vue";

export const 主題儲存鍵 = "ffxiv-tc-rankings-theme";

function 偵測初始主題() {
  if (typeof window === "undefined") {
    return "dark";
  }

  const 已儲存主題 = window.localStorage.getItem(主題儲存鍵);
  if (已儲存主題 === "light" || 已儲存主題 === "dark") {
    return 已儲存主題;
  }

  if (window.matchMedia?.("(prefers-color-scheme: light)").matches) {
    return "light";
  }

  if (window.matchMedia?.("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }

  return "dark";
}

export function useTheme() {
  const 主題模式 = ref("dark");

  function 套用主題狀態(主題, { 寫入偏好 = true } = {}) {
    const 有效主題 = 主題 === "light" ? "light" : "dark";
    主題模式.value = 有效主題;

    if (typeof document !== "undefined") {
      document.documentElement.dataset.theme = 有效主題;
      document.documentElement.style.colorScheme = 有效主題;
    }

    if (寫入偏好 && typeof window !== "undefined") {
      window.localStorage.setItem(主題儲存鍵, 有效主題);
    }
  }

  function 套用主題(主題) {
    套用主題狀態(主題);
  }

  // Honey B. Lovely 的演出轉場需要暫時切換全站亮暗色，但不能覆寫使用者原本偏好。
  function 套用暫時主題(主題) {
    套用主題狀態(主題, { 寫入偏好: false });
  }

  function 初始化主題() {
    套用主題(偵測初始主題());
  }

  function 切換主題() {
    套用主題(主題模式.value === "dark" ? "light" : "dark");
  }

  const 主題按鈕文字 = computed(() => {
    return 主題模式.value === "dark" ? "亮色" : "暗色";
  });

  const 目前主題文字 = computed(() => {
    return 主題模式.value === "dark" ? "暗色模式" : "亮色模式";
  });

  return {
    主題模式,
    主題儲存鍵,
    主題按鈕文字,
    目前主題文字,
    初始化主題,
    套用主題,
    套用暫時主題,
    切換主題,
  };
}
