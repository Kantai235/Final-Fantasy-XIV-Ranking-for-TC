<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

defineOptions({
  name: "AppFooter",
});

const 作者圖片網址 = `${import.meta.env.BASE_URL}author.png`;
const 作者Facebook網址 = "https://www.facebook.com/kantai.zeng";
const 作者角色名稱 = "乾太";
const 作者伺服器 = "鳳凰";
const 作者成績單網址 = `${import.meta.env.BASE_URL}user/${encodeURIComponent(作者角色名稱)}?server=${encodeURIComponent(作者伺服器)}`;
const 作者互動區 = ref(null);
const 顯示作者卡 = ref(false);
const 作者卡正在收回 = ref(false);
const 作者卡已釘選 = ref(false);
let 收回作者卡計時器 = null;

function 清除收回計時器() {
  if (收回作者卡計時器 === null) {
    return;
  }

  window.clearTimeout(收回作者卡計時器);
  收回作者卡計時器 = null;
}

function 開啟作者卡() {
  清除收回計時器();
  作者卡正在收回.value = false;
  顯示作者卡.value = true;
}

function 關閉作者卡() {
  if (!顯示作者卡.value && !作者卡正在收回.value) {
    return;
  }

  顯示作者卡.value = false;
  作者卡正在收回.value = true;
  作者卡已釘選.value = false;
  清除收回計時器();
  收回作者卡計時器 = window.setTimeout(() => {
    作者卡正在收回.value = false;
    收回作者卡計時器 = null;
  }, 420);
}

function 游標離開作者區() {
  if (!作者卡已釘選.value) {
    顯示作者卡.value = false;
  }
}

function 切換作者卡() {
  if (作者卡已釘選.value) {
    關閉作者卡();
    return;
  }

  作者卡已釘選.value = true;
  顯示作者卡.value = true;
}

function 點擊作者區外側(event) {
  if ((!顯示作者卡.value && !作者卡正在收回.value) || 作者互動區.value?.contains(event.target)) {
    return;
  }

  關閉作者卡();
}

onMounted(() => {
  document.addEventListener("pointerdown", 點擊作者區外側);
});

onBeforeUnmount(() => {
  清除收回計時器();
  document.removeEventListener("pointerdown", 點擊作者區外側);
});
</script>

<template>
<footer class="頁尾宣告" aria-label="網站宣告">
  <p>FINAL FANTASY XIV © SQUARE ENIX CO., LTD. All Rights Reserved.</p>
  <p>本網站為非官方社群工具，資料來自 FFLogs 公開報告，與 SQUARE ENIX CO., LTD. 無從屬或背書關係。</p>
  <div class="頁尾作者列">
    <span>力量來自於</span>
    <span ref="作者互動區" class="頁尾作者互動" @mouseenter="開啟作者卡" @mouseleave="游標離開作者區">
      <button
        class="頁尾作者按鈕"
        type="button"
        aria-controls="作者浮出面板"
        :aria-expanded="顯示作者卡 ? 'true' : 'false'"
        @click="切換作者卡"
        @focus="開啟作者卡"
        @blur="游標離開作者區"
        @keydown.escape="關閉作者卡"
      >
        乾太
      </button>
      <aside
        id="作者浮出面板"
        class="作者浮出面板"
        :class="{ 顯示: 顯示作者卡, 收回: 作者卡正在收回 }"
        role="dialog"
        aria-label="乾太的自我介紹"
        :aria-hidden="顯示作者卡 || 作者卡正在收回 ? 'false' : 'true'"
      >
        <figure class="作者形象區">
          <img class="作者形象圖" :src="作者圖片網址" alt="乾太的形象圖" />
          <figcaption class="作者圖片署名">
            <a href="https://x.com/fwfwdog" target="_blank" rel="noopener noreferrer">🎨 by 猋ポチ︎︎</a>
          </figcaption>
        </figure>
        <div class="作者對話框">
          <p>嗨囉！我是乾太 🦊</p>
          <p>在鳳凰伺服器蹦蹦跳跳，</p>
          <p>偶爾會打些高難副本，</p>
          <p>歡迎來找我玩玩～</p>
          <div class="作者行動列" aria-label="乾太相關連結">
            <a class="作者行動按鈕" :href="作者Facebook網址" target="_blank" rel="noopener noreferrer">
              我有事情想找乾太 👉👈
            </a>
            <a class="作者行動按鈕" :href="作者成績單網址">我想偷看乾太的成績單 👀✨</a>
          </div>
        </div>
      </aside>
    </span>
  </div>
</footer>
</template>
