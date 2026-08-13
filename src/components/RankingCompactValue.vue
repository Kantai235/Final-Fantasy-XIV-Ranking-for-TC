<script>
import { computed, ref } from "vue";

export default {
  name: "RankingCompactValue",
  props: {
    displayValue: {
      type: String,
      required: true,
    },
    fullValue: {
      type: String,
      default: "",
    },
    label: {
      type: String,
      default: "數值",
    },
    percentage: {
      type: Boolean,
      default: false,
    },
  },
  setup(props) {
    const 提示已展開 = ref(false);
    const 百分比片段 = computed(() => {
      if (!props.percentage) {
        return null;
      }
      const 符合 = String(props.displayValue).match(/^(-?\d+)\.(\d+)%$/);
      return 符合 ? { 整數: 符合[1], 小數: 符合[2] } : null;
    });
    const 有完整數值提示 = computed(
      () => Boolean(props.fullValue && props.displayValue !== props.fullValue && props.displayValue !== "-"),
    );

    function 切換提示() {
      提示已展開.value = !提示已展開.value;
    }

    function 關閉提示() {
      提示已展開.value = false;
    }

    function 關閉提示並移焦(event) {
      關閉提示();
      event.currentTarget?.blur();
    }

    return {
      提示已展開,
      百分比片段,
      有完整數值提示,
      切換提示,
      關閉提示,
      關閉提示並移焦,
    };
  },
};
</script>

<template>
  <template v-if="!有完整數值提示">
    <template v-if="百分比片段">{{ 百分比片段.整數 }}.<small class="排行榜百分比小數">{{ 百分比片段.小數 }}</small>%</template>
    <template v-else>{{ displayValue }}</template>
  </template>
  <button
    v-else
    class="排行榜縮寫數值"
    :class="{ 完整數值已展開: 提示已展開 }"
    type="button"
    :aria-label="`${label} ${displayValue}，完整數值 ${fullValue}`"
    :aria-expanded="提示已展開"
    @click.stop="切換提示"
    @blur="關閉提示"
    @keydown.esc.prevent.stop="關閉提示並移焦"
  >
    <template v-if="百分比片段">{{ 百分比片段.整數 }}.<small class="排行榜百分比小數">{{ 百分比片段.小數 }}</small>%</template>
    <span v-else>{{ displayValue }}</span>
    <span class="排行榜完整數值提示" role="tooltip">{{ fullValue }}</span>
  </button>
</template>
