<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import RankingCompactValue from "./RankingCompactValue.vue";
import ReportExternalLinks from "./ReportExternalLinks.vue";

export default {
  name: "ReportDetailDialog",
  components: {
    RankingCompactValue,
    ReportExternalLinks,
  },
  props: {
    details: {
      type: Object,
      default: null,
    },
  },
  emits: ["close"],
  setup(props, { emit }) {
    const 目前內容 = ref(null);
    const 目前分頁序號 = ref(0);
    const 顯示中 = ref(false);
    const 關閉按鈕 = ref(null);
    let 關閉計時器 = null;
    let 動畫序號 = 0;

    const 彈窗分頁 = computed(() => {
      const tabs = Array.isArray(目前內容.value?.tabs) ? 目前內容.value.tabs.filter(Boolean) : [];
      return tabs.length > 0 ? tabs : [];
    });

    const 目前分頁內容 = computed(() => {
      const base = 目前內容.value;
      if (!base) {
        return null;
      }
      const tabs = 彈窗分頁.value;
      if (tabs.length === 0) {
        return base;
      }
      const index = Math.min(Math.max(目前分頁序號.value, 0), tabs.length - 1);
      return {
        ...base,
        ...tabs[index],
        tabs,
      };
    });

    function 清除關閉計時器() {
      if (關閉計時器 !== null) {
        clearTimeout(關閉計時器);
        關閉計時器 = null;
      }
    }

    function 開啟彈窗(內容) {
      清除關閉計時器();
      動畫序號 += 1;
      const 本次動畫序號 = 動畫序號;
      目前內容.value = 內容;
      目前分頁序號.value = 0;
      顯示中.value = false;

      nextTick(() => {
        const 啟動進場動畫 = () => {
          if (本次動畫序號 !== 動畫序號 || !目前內容.value) {
            return;
          }
          顯示中.value = true;
          關閉按鈕.value?.focus();
        };

        if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
          window.requestAnimationFrame(啟動進場動畫);
        } else {
          setTimeout(啟動進場動畫, 0);
        }
      });
    }

    function 播放關閉動畫() {
      if (!目前內容.value) {
        return;
      }

      清除關閉計時器();
      動畫序號 += 1;
      顯示中.value = false;
      // DOM 保留到離場動畫結束，避免快速開關時 Vue transition class 卡在半途。
      關閉計時器 = setTimeout(() => {
        目前內容.value = null;
        關閉計時器 = null;
      }, 200);
    }

    function 請求關閉() {
      emit("close");
      播放關閉動畫();
    }

    function 切換分頁(index) {
      if (index >= 0 && index < 彈窗分頁.value.length) {
        目前分頁序號.value = index;
      }
    }

    function 處理分頁按鍵(index, event) {
      const count = 彈窗分頁.value.length;
      if (count <= 1) {
        return;
      }

      const keyToIndex = {
        ArrowLeft: (index - 1 + count) % count,
        ArrowRight: (index + 1) % count,
        Home: 0,
        End: count - 1,
      };
      const nextIndex = keyToIndex[event.key];
      if (nextIndex === undefined) {
        return;
      }

      event.preventDefault();
      切換分頁(nextIndex);
      nextTick(() => {
        document.getElementById(`report-detail-tab-${nextIndex}`)?.focus();
      });
    }

    function 處理按鍵(event) {
      if (event.key === "Escape" && 目前內容.value) {
        event.preventDefault();
        請求關閉();
      }
    }

    function 處理指標(event) {
      const target = event.target;
      if (!目前內容.value || !(target instanceof Element)) {
        return;
      }

      if (target.closest(".報告彈窗關閉") || target.classList.contains("報告彈窗遮罩")) {
        請求關閉();
      }
    }

    watch(
      () => props.details,
      (內容) => {
        if (內容) {
          開啟彈窗(內容);
        } else {
          播放關閉動畫();
        }
      },
      { immediate: true },
    );

    onMounted(() => {
      document.addEventListener("keydown", 處理按鍵);
      document.addEventListener("click", 處理指標, true);
      document.addEventListener("pointerup", 處理指標, true);
    });

    onBeforeUnmount(() => {
      清除關閉計時器();
      document.removeEventListener("keydown", 處理按鍵);
      document.removeEventListener("click", 處理指標, true);
      document.removeEventListener("pointerup", 處理指標, true);
    });

    return {
      目前內容,
      目前分頁內容,
      目前分頁序號,
      彈窗分頁,
      顯示中,
      關閉按鈕,
      請求關閉,
      切換分頁,
      處理分頁按鍵,
    };
  },
};
</script>

<template>
  <Teleport to="body">
    <div
      v-if="目前內容"
      class="報告彈窗遮罩"
      :class="{ 顯示: 顯示中 }"
      role="presentation"
      @click.self="請求關閉"
      @pointerup.self="請求關閉"
    >
      <section
        class="報告彈窗"
        role="dialog"
        aria-modal="true"
        aria-labelledby="report-detail-dialog-title"
        @click.stop
        @pointerup.stop
      >
        <header class="報告彈窗標題列">
          <div>
            <p class="報告彈窗副標">{{ 目前分頁內容.subtitle || "報告紀錄" }}</p>
            <h2 id="report-detail-dialog-title">{{ 目前分頁內容.title }}</h2>
            <p v-if="目前分頁內容.identity" class="報告彈窗身份">{{ 目前分頁內容.identity }}</p>
          </div>
          <button
            ref="關閉按鈕"
            class="報告彈窗關閉"
            type="button"
            aria-label="關閉報告視窗"
            @click.stop="請求關閉"
            @pointerup.stop="請求關閉"
          >
            ×
          </button>
        </header>

        <div v-if="彈窗分頁.length > 1" class="報告彈窗分頁列" role="tablist" aria-label="報告來源">
          <button
            v-for="(分頁, index) in 彈窗分頁"
            :id="`report-detail-tab-${index}`"
            :key="分頁.key || index"
            class="報告彈窗分頁"
            :class="{ 目前: index === 目前分頁序號 }"
            type="button"
            role="tab"
            :aria-selected="index === 目前分頁序號"
            :tabindex="index === 目前分頁序號 ? 0 : -1"
            @click="切換分頁(index)"
            @keydown="處理分頁按鍵(index, $event)"
          >
            <span>{{ 分頁.label || `報告 ${index + 1}` }}</span>
            <small v-if="分頁.caption">{{ 分頁.caption }}</small>
          </button>
        </div>

        <dl class="報告彈窗數值格">
          <div v-if="目前分頁內容.statusItems?.length" class="報告彈窗數值列 報告彈窗狀態列">
            <div v-for="項目 in 目前分頁內容.statusItems" :key="項目.key || 項目.label" class="報告彈窗數值項" :class="項目.className">
              <dt :class="{ 報告彈窗標籤列: 項目.tooltip }">
                <span>{{ 項目.label }}</span>
                <span v-if="項目.tooltip" class="說明提示 報告彈窗提示">
                  <button class="說明提示按鈕" type="button" :aria-label="項目.tooltipLabel || `${項目.label} 說明`">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 項目.tooltip }}</span>
                </span>
              </dt>
              <dd>
                <RankingCompactValue
                  :display-value="項目.value"
                  :label="項目.label"
                  :percentage="項目.percentage"
                />
              </dd>
            </div>
          </div>

          <div v-if="目前分頁內容.damageItems?.length" class="報告彈窗數值列 報告彈窗傷害列">
            <div v-for="項目 in 目前分頁內容.damageItems" :key="項目.key || 項目.label" class="報告彈窗數值項" :class="項目.className">
              <dt :class="{ 報告彈窗標籤列: 項目.tooltip }">
                <span>{{ 項目.label }}</span>
                <span v-if="項目.tooltip" class="說明提示 報告彈窗提示">
                  <button class="說明提示按鈕" type="button" :aria-label="項目.tooltipLabel || `${項目.label} 說明`">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 項目.tooltip }}</span>
                </span>
              </dt>
              <dd>
                <RankingCompactValue
                  :display-value="項目.value"
                  :label="項目.label"
                  :percentage="項目.percentage"
                />
              </dd>
            </div>
          </div>

          <div v-if="目前分頁內容.traceItems?.length" class="報告彈窗數值列 報告彈窗追溯列">
            <div v-for="項目 in 目前分頁內容.traceItems" :key="項目.key || 項目.label" class="報告彈窗數值項" :class="項目.className">
              <dt>{{ 項目.label }}</dt>
              <dd>{{ 項目.value }}</dd>
            </div>
          </div>
        </dl>

        <div class="報告彈窗連結區">
          <span>外部工具</span>
          <ReportExternalLinks class="報告彈窗工具連結" :record="目前分頁內容.record" aria-label="報告外部工具連結" />
        </div>
      </section>
    </div>
  </Teleport>
</template>
