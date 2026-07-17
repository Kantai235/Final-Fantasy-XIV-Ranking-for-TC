<script>
import { computed, ref, watch } from "vue";

export default {
  name: "EncounterMenu",
  props: {
    分組: {
      type: Array,
      default: () => [],
    },
    選取鍵值: {
      type: String,
      default: "",
    },
    標籤: {
      type: String,
      default: "副本類型",
    },
  },
  emits: ["選擇"],
  setup(props, { emit }) {
    const 展開分類 = ref("");

    const 目前分類 = computed(() => {
      return props.分組.find((分組) => 分組.分類 === 展開分類.value) || props.分組[0] || null;
    });

    // 每次開啟選單時，優先把目前選取的副本所在類型放在右側；使用者仍可在左欄
    // 切換到其他類型瀏覽。這與職業選單「類型在左、項目在右」的操作方式一致。
    watch(
      () => [props.分組, props.選取鍵值],
      () => {
        const 選取分類 = props.分組.find((分組) => (
          分組.子分組.some((子分組) => 子分組.項目.some((項目) => 項目.鍵值 === props.選取鍵值))
        ));
        展開分類.value = 選取分類?.分類 || props.分組[0]?.分類 || "";
      },
      { immediate: true },
    );

    function 選擇項目(項目) {
      if (項目?.鍵值) {
        emit("選擇", 項目);
      }
    }

    return {
      展開分類,
      目前分類,
      選擇項目,
    };
  },
};
</script>

<template>
  <div class="副本選單面板 副本階層選單面板" role="menu" :aria-label="標籤">
    <div class="副本選單分類欄" role="menu" aria-label="副本類型">
      <button
        v-for="分類 in 分組"
        :key="分類.分類"
        class="副本選單項 副本分類選單項"
        type="button"
        :class="{ 已展開: 展開分類 === 分類.分類 }"
        :aria-pressed="展開分類 === 分類.分類"
        @click="展開分類 = 分類.分類"
      >
        <span>{{ 分類.顯示名稱 }}</span>
        <svg aria-hidden="true" viewBox="0 0 16 16" focusable="false">
          <path d="m6 3 5 5-5 5" />
        </svg>
      </button>
    </div>

    <div v-if="目前分類" class="副本選單內容欄" role="menu" :aria-label="目前分類.顯示名稱">
      <section v-for="子分組 in 目前分類.子分組" :key="子分組.鍵值" class="副本分類群">
        <p v-if="子分組.顯示標題" class="副本分類標題">{{ 子分組.名稱 }}</p>
        <button
          v-for="副本 in 子分組.項目"
          :key="副本.鍵值"
          class="副本選單項"
          type="button"
          :class="{ 已選取: 選取鍵值 === 副本.鍵值 }"
          @click="選擇項目(副本)"
        >
          {{ 副本.名稱 }}
        </button>
      </section>
    </div>
  </div>
</template>
