<script>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from "vue";
import AchievementDescription from "./AchievementDescription.vue";
import { 成就手冊分類定義 } from "../utils/userProfileBadges";

const 台灣整數格式 = new Intl.NumberFormat("zh-TW", { maximumFractionDigits: 0 });
const 預設手冊分類 = "savage";

export default {
  name: "AchievementHandbook",
  components: {
    AchievementDescription,
  },
  props: {
    achievements: {
      type: Array,
      default: () => [],
    },
    playerName: {
      type: String,
      default: "",
    },
    totalUsers: {
      type: Number,
      default: 0,
    },
  },
  setup(props) {
    const 成就手冊開啟 = ref(false);
    const 目前分類Id = ref(預設手冊分類);
    const 開啟按鈕 = ref(null);
    const 關閉按鈕 = ref(null);

    function 取得進度群組(成就) {
      return 成就?.手冊進度群組 || 成就?.id || "";
    }

    function 建立成就進度(成就列表) {
      const 全部群組 = new Set();
      const 已獲得群組 = new Set();
      for (const 成就 of Array.isArray(成就列表) ? 成就列表 : []) {
        const 群組 = 取得進度群組(成就);
        if (!群組) {
          continue;
        }
        全部群組.add(群組);
        if (成就?.已獲得) {
          已獲得群組.add(群組);
        }
      }
      return {
        已獲得數: 已獲得群組.size,
        總數: 全部群組.size,
      };
    }

    const 全部成就進度 = computed(() => 建立成就進度(props.achievements));
    const 已獲得成就數 = computed(() => 全部成就進度.value.已獲得數);
    const 總成就數 = computed(() => 全部成就進度.value.總數);
    const 可用分類 = computed(() => 成就手冊分類定義
      .map((分類) => {
        const 分類成就 = props.achievements.filter((成就) => 成就?.手冊分類 === 分類.id);
        return {
          ...分類,
          成就: 分類成就,
          ...建立成就進度(分類成就),
        };
      })
      .filter((分類) => 分類.成就.length > 0));
    const 目前分類 = computed(() => (
      可用分類.value.find((分類) => 分類.id === 目前分類Id.value)
      || 可用分類.value[0]
      || null
    ));
    const 目前分類群組 = computed(() => {
      const 群組索引 = new Map();
      for (const 成就 of 目前分類.value?.成就 || []) {
        const 群組Id = 成就?.手冊群組 || 目前分類.value.id;
        let 群組 = 群組索引.get(群組Id);
        if (!群組) {
          群組 = {
            id: 群組Id,
            名稱: 成就?.手冊群組名稱 || 目前分類.value.名稱,
            成就: [],
          };
          群組索引.set(群組Id, 群組);
        }
        群組.成就.push(成就);
      }
      return Array.from(群組索引.values()).map((群組) => {
        if (目前分類.value?.id !== "savage") {
          return {
            ...群組,
            區段: [{ id: "standard", 名稱: "", 說明: "", 成就: 群組.成就 }],
          };
        }

        // 零式量級同時有互斥的五階進度與可獨立取得的分位成就。區段結構由
        // 工具層的穩定類型建立，避免模板依成就名稱猜測並誤標成「其他階段」。
        const 階段成就 = 群組.成就.filter((成就) => 成就?.手冊項目類型 === "stage");
        const 額外成就 = 群組.成就.filter((成就) => 成就?.手冊項目類型 === "bonus");
        return {
          ...群組,
          區段: [
            { id: "stage", 名稱: "五階進度", 說明: "同量級只計最高階一項", 成就: 階段成就 },
            { id: "bonus", 名稱: "額外成就", 說明: "可獨立取得", 成就: 額外成就 },
          ].filter((區段) => 區段.成就.length > 0),
        };
      });
    });

    function 確保目前分類可用() {
      if (!可用分類.value.some((分類) => 分類.id === 目前分類Id.value)) {
        目前分類Id.value = 可用分類.value[0]?.id || 預設手冊分類;
      }
    }

    function 開啟成就手冊() {
      確保目前分類可用();
      成就手冊開啟.value = true;
      nextTick(() => 關閉按鈕.value?.focus());
    }

    function 關閉成就手冊() {
      if (!成就手冊開啟.value) {
        return;
      }
      成就手冊開啟.value = false;
      nextTick(() => 開啟按鈕.value?.focus());
    }

    function 切換分類(分類Id, 聚焦 = false) {
      if (!可用分類.value.some((分類) => 分類.id === 分類Id)) {
        return;
      }
      目前分類Id.value = 分類Id;
      if (聚焦) {
        nextTick(() => document.getElementById(`achievement-tab-${分類Id}`)?.focus());
      }
    }

    function 處理分頁按鍵(event, 分類索引) {
      const 最後索引 = 可用分類.value.length - 1;
      let 下一個索引 = null;
      if (event.key === "ArrowRight") {
        下一個索引 = 分類索引 === 最後索引 ? 0 : 分類索引 + 1;
      } else if (event.key === "ArrowLeft") {
        下一個索引 = 分類索引 === 0 ? 最後索引 : 分類索引 - 1;
      } else if (event.key === "Home") {
        下一個索引 = 0;
      } else if (event.key === "End") {
        下一個索引 = 最後索引;
      }

      if (下一個索引 === null || !可用分類.value[下一個索引]) {
        return;
      }
      event.preventDefault();
      切換分類(可用分類.value[下一個索引].id, true);
    }

    function 處理按鍵(event) {
      if (event.key === "Escape" && 成就手冊開啟.value) {
        event.preventDefault();
        關閉成就手冊();
      }
    }

    function 取得成就狀態(成就) {
      if (成就?.手冊階段狀態?.標籤) {
        return 成就.手冊階段狀態.標籤;
      }
      if (成就?.已獲得) {
        return "已取得";
      }
      return "未取得";
    }

    function 取得成就狀態圖示(成就) {
      if (成就?.手冊階段狀態?.圖示) {
        return 成就.手冊階段狀態.圖示;
      }
      if (成就?.已獲得) {
        return "✓";
      }
      return "·";
    }

    function 格式化人數(數值) {
      return Number.isFinite(Number(數值)) ? 台灣整數格式.format(Number(數值)) : "—";
    }

    function 格式化獲得占比(數值) {
      if (數值 === null || 數值 === undefined || 數值 === "") {
        return "統計待更新";
      }
      const 百分比 = Number(數值);
      return Number.isFinite(百分比) ? `${百分比.toFixed(2)}%` : "統計待更新";
    }

    function 成就占比樣式(數值) {
      if (數值 === null || 數值 === undefined || 數值 === "") {
        return { width: "0%" };
      }
      const 百分比 = Number(數值);
      return {
        width: `${Number.isFinite(百分比) ? Math.min(100, Math.max(0, 百分比)) : 0}%`,
      };
    }

    onMounted(() => document.addEventListener("keydown", 處理按鍵));
    onBeforeUnmount(() => document.removeEventListener("keydown", 處理按鍵));

    return {
      成就手冊開啟,
      目前分類Id,
      目前分類,
      目前分類群組,
      可用分類,
      已獲得成就數,
      總成就數,
      開啟按鈕,
      關閉按鈕,
      開啟成就手冊,
      關閉成就手冊,
      切換分類,
      處理分頁按鍵,
      取得成就狀態,
      取得成就狀態圖示,
      格式化人數,
      格式化獲得占比,
      成就占比樣式,
    };
  },
};
</script>

<template>
  <button
    v-if="achievements.length > 0"
    ref="開啟按鈕"
    class="成就手冊浮動按鈕"
    type="button"
    aria-controls="achievement-handbook-dialog"
    :aria-expanded="成就手冊開啟"
    :aria-label="`開啟${playerName || '玩家'}的成就手冊，已取得 ${已獲得成就數} 項`"
    @click="開啟成就手冊"
  >
    <span class="成就手冊浮動光環" aria-hidden="true"></span>
    <svg class="成就手冊浮動書本" viewBox="0 0 64 64" aria-hidden="true">
      <path class="成就手冊書封" d="M11 13.5c8.1-2.1 14.5-.8 21 3.9v35.1c-6.5-4.7-12.9-6-21-3.9V13.5Z" />
      <path class="成就手冊書封" d="M53 13.5c-8.1-2.1-14.5-.8-21 3.9v35.1c6.5-4.7 12.9-6 21-3.9V13.5Z" />
      <path class="成就手冊書頁" d="M15 18.2c5.4-1 9.6.1 14 3.1v24.9c-4.4-2.7-8.8-3.5-14-2.4V18.2Z" />
      <path class="成就手冊書頁" d="M49 18.2c-5.4-1-9.6.1-14 3.1v24.9c4.4-2.7 8.8-3.5 14-2.4V18.2Z" />
      <path class="成就手冊書脊" d="M32 17.6v35" />
      <path class="成就手冊書紋" d="M18.5 25.5c3.6-.2 6.4.6 9 2.2M18.5 32c3.6-.2 6.4.6 9 2.2M45.5 25.5c-3.6-.2-6.4.6-9 2.2M45.5 32c-3.6-.2-6.4.6-9 2.2" />
    </svg>
    <span class="成就手冊浮動進度" aria-hidden="true">{{ 已獲得成就數 }}/{{ 總成就數 }}</span>
    <span class="成就手冊浮動提示" aria-hidden="true">成就手冊</span>
  </button>

  <Teleport to="body">
    <div
      v-if="成就手冊開啟"
      class="報告彈窗遮罩 顯示 成就手冊遮罩"
      role="presentation"
      @click.self="關閉成就手冊"
    >
      <section
        id="achievement-handbook-dialog"
        class="報告彈窗 成就手冊彈窗"
        role="dialog"
        aria-modal="true"
        aria-labelledby="achievement-handbook-title"
        aria-describedby="achievement-handbook-description"
        @click.stop
      >
        <header class="報告彈窗標題列 成就手冊標題列">
          <div>
            <p class="報告彈窗副標">角色累積紀錄</p>
            <h2 id="achievement-handbook-title">成就手冊</h2>
            <p id="achievement-handbook-description" class="報告彈窗身份">
              {{ playerName || "目前玩家" }} · 分類查看成就與全站稀有度
            </p>
          </div>
          <button
            ref="關閉按鈕"
            class="報告彈窗關閉"
            type="button"
            aria-label="關閉成就手冊"
            @click="關閉成就手冊"
          >
            ×
          </button>
        </header>

        <section class="成就手冊摘要" aria-label="成就取得進度">
          <div class="成就手冊摘要印章" aria-hidden="true">
            <strong>{{ 已獲得成就數 }}</strong>
            <span>/ {{ 總成就數 }}</span>
          </div>
          <div>
            <strong>已取得 {{ 已獲得成就數 }} 項成就</strong>
            <span v-if="totalUsers > 0">獲得率以本站收錄的 {{ 格式化人數(totalUsers) }} 位玩家為分母</span>
            <span v-else>全站獲得率統計等待資料更新</span>
          </div>
        </section>

        <nav class="成就手冊分頁列" aria-label="成就分類" role="tablist">
          <button
            v-for="(分類, 分類索引) in 可用分類"
            :id="`achievement-tab-${分類.id}`"
            :key="分類.id"
            class="成就手冊分頁"
            :class="{ 作用中: 目前分類?.id === 分類.id }"
            type="button"
            role="tab"
            :aria-selected="目前分類?.id === 分類.id"
            :aria-controls="`achievement-panel-${分類.id}`"
            :aria-label="`${分類.名稱}，已取得 ${分類.已獲得數}／${分類.總數}`"
            :tabindex="目前分類?.id === 分類.id ? 0 : -1"
            @click="切換分類(分類.id)"
            @keydown="處理分頁按鍵($event, 分類索引)"
          >
            <strong>{{ 分類.名稱 }}</strong>
            <span aria-hidden="true">{{ 分類.已獲得數 }}/{{ 分類.總數 }}</span>
          </button>
        </nav>

        <section
          v-if="目前分類"
          :id="`achievement-panel-${目前分類.id}`"
          class="成就手冊內容區"
          role="tabpanel"
          :aria-labelledby="`achievement-tab-${目前分類.id}`"
          tabindex="0"
        >
          <header class="成就手冊分類標題">
            <div>
              <h3>{{ 目前分類.名稱 }}成就</h3>
              <p>{{ 目前分類.說明 }}</p>
            </div>
            <span>{{ 目前分類.已獲得數 }} / {{ 目前分類.總數 }}</span>
          </header>

          <div
            class="成就手冊階段群組列表"
            :class="{ 零式分組: 目前分類Id === 'savage' }"
          >
            <section
              v-for="群組 in 目前分類群組"
              :key="群組.id"
              class="成就手冊階段群組"
              :aria-labelledby="目前分類Id === 'savage' ? `achievement-group-${群組.id}` : undefined"
            >
              <header v-if="目前分類Id === 'savage'" class="成就手冊階段群組標題">
                <h4 :id="`achievement-group-${群組.id}`">{{ 群組.名稱 }}</h4>
                <span>量級成就</span>
              </header>

              <section
                v-for="區段 in 群組.區段"
                :key="區段.id"
                class="成就手冊量級區段"
                :class="`成就手冊量級區段-${區段.id}`"
              >
                <header v-if="區段.名稱" class="成就手冊量級區段標題">
                  <strong>{{ 區段.名稱 }}</strong>
                  <span>{{ 區段.說明 }}</span>
                </header>

                <ol class="成就手冊清單" :aria-label="`${群組.名稱}${區段.名稱 || '成就'}`">
                  <li
                    v-for="成就 in 區段.成就"
                    :key="成就.id"
                    class="成就手冊項目"
                    :class="{
                      已取得: 成就.已獲得,
                      尚未取得: !成就.已獲得,
                      目前目標: 成就.手冊階段狀態?.id === 'current',
                      已無法獲得: 成就.手冊階段狀態?.id === 'unavailable',
                      其他階段: 成就.手冊階段狀態?.id === 'future',
                    }"
                  >
                    <span class="成就手冊狀態圖示" aria-hidden="true">{{ 取得成就狀態圖示(成就) }}</span>
                    <div class="成就手冊項目內容">
                      <div class="成就手冊項目標題">
                        <span class="成就手冊分類">{{ 成就.分類 }}</span>
                        <strong>{{ 成就.名稱 }}</strong>
                        <span class="成就手冊取得狀態">{{ 取得成就狀態(成就) }}</span>
                      </div>
                      <AchievementDescription
                        as="p"
                        :text="成就.說明"
                        :segments="成就.說明片段"
                      />
                      <div class="成就手冊稀有度">
                        <span>
                          <strong>{{ 成就.獲得人數 === null ? "—" : 格式化人數(成就.獲得人數) }}</strong>
                          人獲得
                        </span>
                        <span>{{ 格式化獲得占比(成就.獲得占比) }}</span>
                      </div>
                      <span class="成就手冊占比軌道" aria-hidden="true">
                        <span :style="成就占比樣式(成就.獲得占比)"></span>
                      </span>
                    </div>
                  </li>
                </ol>
              </section>
            </section>
          </div>
        </section>

        <p class="成就手冊資料說明">
          成就依本站收錄的公開 FFLogs 通關紀錄判定；零式五階互斥，炒股仔則依有效版本內各層的本站同職 PR 獨立判定。未取得只代表目前沒有符合條件的公開資料。
        </p>
      </section>
    </div>
  </Teleport>
</template>
