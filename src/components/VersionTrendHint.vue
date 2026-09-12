<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

defineProps({
  id: { type: String, required: true },
  direction: { type: String, required: true, validator: (值) => ["up", "down"].includes(值) },
  label: { type: String, required: true },
  text: { type: String, required: true },
});

const 容器 = ref(null);
const 已展開 = ref(false);
const 已固定 = ref(false);
const 提示位置 = ref({});

function 開啟提示() {
  const 邊界 = 容器.value.getBoundingClientRect();
  const 寬度 = Math.min(240, document.documentElement.clientWidth - 32);
  // 符號可能位於手機畫面的左右邊緣，提示仍須完整留在可視範圍內。
  const 左側 = Math.max(16, Math.min(邊界.left + 邊界.width / 2 - 寬度 / 2, document.documentElement.clientWidth - 寬度 - 16));
  提示位置.value = { width: `${寬度}px`, left: `${左側 - 邊界.left}px` };
  已展開.value = true;
}
function 關閉提示() {
  已展開.value = false;
  已固定.value = false;
}
function 切換提示() {
  if (已固定.value) 關閉提示();
  else { 已固定.value = true; 開啟提示(); }
}
function 點擊外側(事件) {
  if (!容器.value?.contains(事件.target)) 關閉提示();
}
onMounted(() => {
  document.addEventListener("pointerdown", 點擊外側);
  window.addEventListener("resize", 關閉提示);
});
onBeforeUnmount(() => {
  document.removeEventListener("pointerdown", 點擊外側);
  window.removeEventListener("resize", 關閉提示);
});
</script>

<template>
  <span ref="容器" class="版本趨勢提示" :class="`版本趨勢-${direction}`"
    @pointerenter="$event.pointerType === 'mouse' && 開啟提示()"
    @pointerleave="!已固定 && 關閉提示()">
    <button type="button" class="版本趨勢按鈕" :aria-label="label" :aria-expanded="已展開"
      :aria-describedby="已展開 ? id : undefined" :aria-controls="id"
      @focus="開啟提示" @blur="關閉提示" @click.stop="切換提示" @keydown.esc.prevent.stop="關閉提示">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path :d="direction === 'up' ? 'M4 17L10 11L14 15L21 6M14 6H21V13' : 'M4 7L10 13L14 9L21 18M14 18H21V11'" /></svg>
    </button>
    <span v-if="已展開" :id="id" class="版本趨勢提示內容" role="tooltip" :style="提示位置">{{ text }}</span>
  </span>
</template>
