<script setup>
import { computed } from "vue";
import { 職業Icon路徑, 職業類型Icon路徑 } from "../domain/jobs";
import { 隱藏載入失敗圖片 } from "../utils/viewHelpers";

defineOptions({
  inheritAttrs: false,
});

const props = defineProps({
  code: {
    type: String,
    default: "",
  },
  kind: {
    type: String,
    default: "job",
  },
  src: {
    type: String,
    default: "",
  },
  alt: {
    type: String,
    default: "",
  },
  loading: {
    type: String,
    default: "lazy",
  },
});

const 圖示路徑 = computed(() => {
  if (props.src) {
    return props.src;
  }
  return props.kind === "role" ? 職業類型Icon路徑(props.code) : 職業Icon路徑(props.code);
});
</script>

<template>
  <img
    v-if="圖示路徑"
    v-bind="$attrs"
    :src="圖示路徑"
    :alt="alt"
    :loading="loading"
    decoding="async"
    @error="隱藏載入失敗圖片"
  />
</template>
