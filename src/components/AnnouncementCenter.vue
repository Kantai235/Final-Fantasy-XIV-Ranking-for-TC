<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import AnnouncementMarkdown from "./AnnouncementMarkdown.vue";
import {
  取得主動公告列表,
  取得公告狀態,
  取得公告狀態文字,
  寫入已關閉公告,
  正規化公告資料,
  讀取已關閉公告,
  解析公告Markdown,
} from "../utils/announcements";
import { 讀取Json } from "../utils/fetchJson";
import { 公告資料網址 } from "../utils/publicData";

const 公告時間格式器 = new Intl.DateTimeFormat("zh-Hant-TW", {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

function 格式化公告時間(value, fallback) {
  const 時間 = new Date(value || 0).getTime();
  if (!Number.isFinite(時間) || 時間 <= 0) {
    return fallback;
  }
  return 公告時間格式器.format(new Date(時間));
}

export default {
  name: "AnnouncementCenter",
  components: {
    AnnouncementMarkdown,
  },
  setup() {
    const 公告列表 = ref([]);
    const 公告讀取中 = ref(false);
    const 公告錯誤訊息 = ref("");
    const 已關閉公告Ids = ref(new Set());
    const 目前時間毫秒 = ref(Date.now());
    const 顯示公告視窗 = ref(false);
    const 公告視窗顯示中 = ref(false);
    const 公告開啟按鈕 = ref(null);
    const 公告關閉按鈕 = ref(null);
    const 目前公告Id = ref("");
    let 公告時間計時器 = null;
    let 公告視窗關閉計時器 = null;
    let 公告視窗動畫序號 = 0;

    const 主動公告列表 = computed(() =>
      取得主動公告列表(公告列表.value, 已關閉公告Ids.value, 目前時間毫秒.value),
    );

    const 公告顯示列表 = computed(() =>
      公告列表.value.map((announcement) => {
        const status = 取得公告狀態(announcement, 目前時間毫秒.value);
        return {
          ...announcement,
          status,
          statusLabel: 取得公告狀態文字(announcement, 目前時間毫秒.value),
          periodText: `開始：${格式化公告時間(announcement.starts_at_iso, "即刻")}・期限：${格式化公告時間(announcement.expires_at_iso, "無期限")}`,
          blocks: 解析公告Markdown(announcement.details_markdown),
          highlighted: 目前公告Id.value === announcement.id,
        };
      }),
    );

    const 公告按鈕標籤 = computed(() => {
      const count = 主動公告列表.value.length;
      return count > 0 ? `所有公告，${count} 則未關閉公告` : "所有公告";
    });

    function 清除公告視窗關閉計時器() {
      if (公告視窗關閉計時器 !== null) {
        clearTimeout(公告視窗關閉計時器);
        公告視窗關閉計時器 = null;
      }
    }

    async function 讀取公告資料() {
      公告讀取中.value = true;
      公告錯誤訊息.value = "";
      try {
        const payload = await 讀取Json(公告資料網址, "讀取公告失敗");
        公告列表.value = 正規化公告資料(payload);
      } catch (error) {
        公告錯誤訊息.value = error instanceof Error ? error.message : "無法讀取公告";
      } finally {
        公告讀取中.value = false;
      }
    }

    function 開啟公告視窗(announcementId = "") {
      清除公告視窗關閉計時器();
      公告視窗動畫序號 += 1;
      const 本次動畫序號 = 公告視窗動畫序號;
      目前公告Id.value = announcementId;
      顯示公告視窗.value = true;
      公告視窗顯示中.value = false;

      nextTick(() => {
        const 啟動進場動畫 = () => {
          if (本次動畫序號 !== 公告視窗動畫序號 || !顯示公告視窗.value) {
            return;
          }
          公告視窗顯示中.value = true;
          公告關閉按鈕.value?.focus();
        };

        if (typeof window !== "undefined" && typeof window.requestAnimationFrame === "function") {
          window.requestAnimationFrame(啟動進場動畫);
        } else {
          setTimeout(啟動進場動畫, 0);
        }
      });
    }

    function 關閉公告視窗() {
      if (!顯示公告視窗.value) {
        return;
      }

      清除公告視窗關閉計時器();
      公告視窗動畫序號 += 1;
      公告視窗顯示中.value = false;
      公告視窗關閉計時器 = setTimeout(() => {
        顯示公告視窗.value = false;
        目前公告Id.value = "";
        公告視窗關閉計時器 = null;
      }, 200);
    }

    function 關閉公告視窗並回焦() {
      關閉公告視窗();
      setTimeout(() => 公告開啟按鈕.value?.focus(), 200);
    }

    function 關閉單筆公告(announcement) {
      if (!announcement?.id) {
        return;
      }
      const nextIds = new Set(已關閉公告Ids.value);
      nextIds.add(announcement.id);
      已關閉公告Ids.value = nextIds;
      寫入已關閉公告(nextIds);
    }

    onMounted(() => {
      已關閉公告Ids.value = 讀取已關閉公告();
      公告時間計時器 = setInterval(() => {
        目前時間毫秒.value = Date.now();
      }, 60 * 1000);
      讀取公告資料();
    });

    onBeforeUnmount(() => {
      清除公告視窗關閉計時器();
      if (公告時間計時器 !== null) {
        clearInterval(公告時間計時器);
        公告時間計時器 = null;
      }
    });

    return {
      公告列表,
      公告讀取中,
      公告錯誤訊息,
      主動公告列表,
      公告顯示列表,
      公告按鈕標籤,
      顯示公告視窗,
      公告視窗顯示中,
      公告開啟按鈕,
      公告關閉按鈕,
      開啟公告視窗,
      關閉公告視窗並回焦,
      關閉單筆公告,
    };
  },
};
</script>

<template>
  <div class="公告中心">
    <button
      ref="公告開啟按鈕"
      class="公告中心按鈕"
      type="button"
      aria-controls="公告中心視窗"
      :aria-expanded="顯示公告視窗 ? 'true' : 'false'"
      :aria-label="公告按鈕標籤"
      @click="開啟公告視窗()"
    >
      <svg class="標題按鈕圖示" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M18 8a6 6 0 0 0-12 0c0 7-3 8-3 8h18s-3-1-3-8"></path>
        <path d="M13.7 21a2 2 0 0 1-3.4 0"></path>
      </svg>
      <span class="標題按鈕文字">所有公告</span>
      <span v-if="主動公告列表.length > 0" class="公告中心徽章" aria-hidden="true">{{ 主動公告列表.length }}</span>
    </button>
  </div>

  <Teleport to="body">
    <section v-if="主動公告列表.length > 0" class="公告通知區" aria-label="公告通知" aria-live="polite">
      <article
        v-for="announcement in 主動公告列表"
        :key="announcement.id"
        class="公告通知"
        :data-severity="announcement.severity"
      >
        <div class="公告通知內容">
          <p class="公告通知標題">{{ announcement.title }}</p>
          <p class="公告通知摘要">{{ announcement.summary }}</p>
        </div>
        <div class="公告通知行動列">
          <button class="公告通知詳情" type="button" @click="開啟公告視窗(announcement.id)">查看詳情</button>
          <button class="公告通知關閉" type="button" :aria-label="`關閉公告：${announcement.title}`" @click="關閉單筆公告(announcement)">
            ×
          </button>
        </div>
      </article>
    </section>
  </Teleport>

  <Teleport to="body">
    <div
      v-if="顯示公告視窗"
      class="公告視窗遮罩"
      :class="{ 顯示: 公告視窗顯示中 }"
      @click.self="關閉公告視窗並回焦"
      @keydown.escape="關閉公告視窗並回焦"
    >
      <section
        id="公告中心視窗"
        class="公告視窗"
        role="dialog"
        aria-modal="true"
        aria-labelledby="公告中心標題"
        aria-describedby="公告中心說明"
      >
        <header class="公告視窗標題列">
          <div>
            <p class="公告視窗副標">FFXIV 繁中服排行榜</p>
            <h2 id="公告中心標題">所有公告</h2>
            <p id="公告中心說明">公告會依開始與有效期限決定是否主動顯示；關閉後只會保留在這裡。</p>
          </div>
          <button
            ref="公告關閉按鈕"
            class="公告視窗關閉"
            type="button"
            aria-label="關閉所有公告視窗"
            @click="關閉公告視窗並回焦"
          >
            ×
          </button>
        </header>

        <p v-if="公告讀取中" class="公告視窗狀態">公告讀取中...</p>
        <p v-else-if="公告錯誤訊息" class="公告視窗狀態 錯誤">{{ 公告錯誤訊息 }}</p>
        <p v-else-if="公告顯示列表.length === 0" class="公告視窗狀態">目前沒有公告。</p>

        <div v-else class="公告列表">
          <article
            v-for="announcement in 公告顯示列表"
            :key="announcement.id"
            class="公告項目"
            :class="{ 目前: announcement.highlighted }"
            :data-status="announcement.status"
            :data-severity="announcement.severity"
          >
            <header class="公告項目標題列">
              <div>
                <p class="公告項目期間">{{ announcement.periodText }}</p>
                <h3>{{ announcement.title }}</h3>
              </div>
              <span class="公告狀態標籤">{{ announcement.statusLabel }}</span>
            </header>
            <p class="公告項目摘要">{{ announcement.summary }}</p>
            <AnnouncementMarkdown :blocks="announcement.blocks" />
            <div v-if="announcement.links.length > 0" class="公告連結列" aria-label="公告相關連結">
              <a
                v-for="link in announcement.links"
                :key="`${announcement.id}-${link.url}`"
                class="公告連結"
                :href="link.url"
                target="_blank"
                rel="noopener noreferrer"
              >
                {{ link.label }}
              </a>
            </div>
          </article>
        </div>
      </section>
    </div>
  </Teleport>
</template>
