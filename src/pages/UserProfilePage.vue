<script>
import { ref } from "vue";
import JobIcon from "../components/JobIcon.vue";
import PlayerSearchHistoryPanel from "../components/PlayerSearchHistoryPanel.vue";
import ReportDetailDialog from "../components/ReportDetailDialog.vue";
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "UserProfilePage",
  components: {
    JobIcon,
    PlayerSearchHistoryPanel,
    ReportDetailDialog,
  },
  setup() {
    const app = injectRankingApp();
    const 報告彈窗資料 = ref(null);
    let 報告讀取序號 = 0;

    function 取值(可能Ref) {
      return 可能Ref && typeof 可能Ref === "object" && "value" in 可能Ref ? 可能Ref.value : 可能Ref;
    }

    function 建立個人成績報告分頁標籤(來源, index) {
      return {
        key: 來源.key || `${來源.report_code || "report"}-${來源.fight_id || index}`,
        label: `報告 ${index + 1}`,
        caption: 來源.report_code || "",
      };
    }

    function 建立個人成績報告單筆詳細資料(成績, 副本) {
      const 顯示Gcd = Boolean(取值(app.顯示Gcd覆蓋率));
      const 角色名稱 = 成績.character_name || 取值(app.使用者資料)?.character_name || "個人成績";
      const 伺服器 = 成績.server || 取值(app.使用者伺服器篩選) || "";
      const 職業名稱 = app.顯示職業名稱(成績.job);

      return {
        subtitle: 副本?.encounter_name || 成績.encounter_name || "個人成績歷史",
        title: 角色名稱,
        identity: [伺服器, 職業名稱].filter(Boolean).join(" · "),
        record: 成績,
        statusItems: [
          {
            key: "rank",
            label: "排名",
            value: app.格式化排名(成績.job_rank ?? 成績.rank),
            className: "報告彈窗排名項",
            tooltip: app.統計說明文字("職業 Rank"),
            tooltipLabel: "職業 Rank 說明",
          },
          {
            key: "percentile",
            label: "同職分位",
            value: app.格式化目前同職分位(成績.performance),
            className: ["報告彈窗分位項", app.同職分位色彩類別(成績.performance)].filter(Boolean).join(" "),
            tooltip: app.統計說明文字("同職分位"),
            tooltipLabel: "同職分位說明",
          },
          {
            key: "active",
            label: "Active",
            value: app.格式化Active(成績.active_percent),
            tooltip: app.統計說明文字("Active"),
            tooltipLabel: "Active 說明",
          },
          ...(顯示Gcd
            ? [
                {
                  key: "gcd",
                  label: "GCD",
                  value: app.格式化Gcd覆蓋率(成績.gcd_coverage),
                  tooltip: app.統計說明文字("GCD 覆蓋率"),
                  tooltipLabel: "GCD 覆蓋率說明",
                  className: "gcd參考文字",
                },
              ]
            : []),
          {
            key: "clearTime",
            label: "通關時間",
            value: app.格式化通關時間(成績.clear_time_seconds),
            className: "報告彈窗時間項",
          },
        ],
        damageItems: [
          {
            key: "dps",
            label: "DPS",
            value: app.格式化傷害數值(成績.dps),
            tooltip: app.統計說明文字("DPS"),
            tooltipLabel: "DPS 說明",
          },
          {
            key: "rdps",
            label: "rDPS",
            value: app.格式化傷害數值(成績.rdps),
            tooltip: app.統計說明文字("rDPS"),
            tooltipLabel: "rDPS 說明",
            className: "報告彈窗主要數值",
          },
          {
            key: "adps",
            label: "aDPS",
            value: app.格式化傷害數值(成績.adps),
            tooltip: app.統計說明文字("aDPS"),
            tooltipLabel: "aDPS 說明",
          },
        ],
        traceItems: [
          {
            key: "reportFight",
            label: "Report / Fight",
            value: `${成績.report_code || "-"}${成績.fight_id ? ` · ${成績.fight_id}` : ""}`,
          },
          {
            key: "recordedAt",
            label: "紀錄時間",
            value: app.格式化紀錄時間(成績.recorded_at_iso),
          },
        ],
      };
    }

    function 建立個人成績報告詳細資料(成績, 副本) {
      const details = 建立個人成績報告單筆詳細資料(成績, 副本);
      const 來源清單 = Array.isArray(成績.report_variants) && 成績.report_variants.length > 1 ? 成績.report_variants : [];
      if (來源清單.length === 0) {
        return details;
      }

      return {
        ...details,
        tabs: 來源清單.map((來源, index) => {
          const 分頁成績 = {
            ...成績,
            ...來源,
            report_variants: 成績.report_variants,
            duplicate_count: 成績.duplicate_count,
            source_reports: 成績.source_reports,
          };
          return {
            ...details,
            ...建立個人成績報告分頁標籤(來源, index),
            ...建立個人成績報告單筆詳細資料(分頁成績, 副本),
          };
        }),
      };
    }

    function 合併個人成績報告詳細資料(成績, 詳細資料) {
      if (!詳細資料) {
        return 成績;
      }

      return {
        ...成績,
        ...詳細資料,
      };
    }

    function 開啟個人成績報告彈窗(成績, 副本) {
      const 本次序號 = ++報告讀取序號;
      報告彈窗資料.value = 建立個人成績報告詳細資料(成績, 副本);
      if ((Array.isArray(成績.report_variants) && 成績.report_variants.length > 1) || !成績.report_detail_path) {
        return;
      }

      app.讀取個人成績報告詳細資料(成績)
        .then((詳細資料) => {
          if (本次序號 !== 報告讀取序號 || !詳細資料) {
            return;
          }
          報告彈窗資料.value = 建立個人成績報告詳細資料(合併個人成績報告詳細資料(成績, 詳細資料), 副本);
        })
        .catch(() => {});
    }

    function 關閉個人成績報告彈窗() {
      報告讀取序號 += 1;
      報告彈窗資料.value = null;
    }

    return {
      ...app,
      報告彈窗資料,
      開啟個人成績報告彈窗,
      關閉個人成績報告彈窗,
    };
  },
};
</script>

<template>
  <section class="使用者搜尋區" aria-label="個人成績單查詢">
    <form class="使用者搜尋表單 個人成績搜尋表單" @submit.prevent="提交使用者搜尋">
      <div class="欄位 使用者搜尋欄位" @focusout="處理玩家搜尋歷史失焦($event, 'user')">
        <label for="個人成績玩家搜尋">玩家 / 伺服器</label>
        <div class="玩家搜尋輸入組">
          <input
            id="個人成績玩家搜尋"
            v-model="使用者搜尋關鍵字"
            type="search"
            list="使用者搜尋建議"
            placeholder="輸入玩家名稱，或選擇「玩家 @ 伺服器」"
            autocomplete="off"
            @focus="開啟玩家搜尋歷史('user')"
          />
          <PlayerSearchHistoryPanel
            field="user"
            :entries="使用者最近搜尋玩家"
            :visible="顯示使用者最近搜尋玩家"
          />
        </div>
        <datalist id="使用者搜尋建議">
          <option v-for="建議 in 使用者搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
            {{ 建議.label }}
          </option>
        </datalist>
      </div>

      <div class="欄位 職業選單欄位" @focusout="處理使用者職業選單失焦">
        <span>職業</span>
        <div class="職業選單">
          <button
            class="職業選單按鈕"
            type="button"
            :disabled="!使用者資料 || 使用者職業類型選項.length === 0"
            :aria-expanded="使用者職業選單開啟"
            aria-haspopup="true"
            @click="切換使用者職業選單"
          >
            <span class="職業選單目前值">
              <JobIcon
                class="職業圖示"
                :src="使用者職業選單Icon路徑"
              />
              <span>{{ 使用者職業選單文字 }}</span>
            </span>
            <span class="選單箭頭">▾</span>
          </button>

          <div v-if="使用者職業選單開啟" class="職業選單面板">
            <div class="職業選單分類欄" role="menu" aria-label="職業類型">
              <button
                class="職業選單項"
                type="button"
                :class="{ 已選取: !使用者職業類型篩選 && !使用者職業篩選 }"
                @click="清除使用者職業篩選"
              >
                全部職業
              </button>
              <button
                v-for="類型 in 使用者職業類型選項"
                :key="類型.代碼"
                class="職業選單項"
                type="button"
                :class="[職業色彩類別(類型.色彩), { 已選取: 使用者職業類型篩選 === 類型.代碼 }]"
                @click="選擇使用者職業類型(類型.代碼)"
              >
                <JobIcon
                  class="職業圖示"
                  kind="role"
                  :code="類型.代碼"
                />
                <span>{{ 類型.名稱 }}</span>
              </button>
            </div>

            <div class="職業選單職業欄" role="menu" aria-label="職業">
              <template v-if="使用者職業類型篩選 && 使用者職業選項.length > 0">
                <button
                  v-for="職業 in 使用者職業選項"
                  :key="職業.代碼"
                  class="職業選單項"
                  type="button"
                  :class="[職業色彩類別(職業.色彩), { 已選取: 使用者職業篩選 === 職業.代碼 }]"
                  @click="選擇使用者職業(職業.代碼)"
                >
                  <JobIcon
                    class="職業圖示"
                    :code="職業.代碼"
                  />
                  <span>{{ 職業.名稱 }}</span>
                </button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <button type="submit">查詢</button>
    </form>
  </section>

  <section class="個人成績區" aria-live="polite">
    <div v-if="使用者讀取中" class="狀態列">讀取個人成績單中</div>
    <div v-else-if="使用者錯誤訊息" class="狀態列 錯誤">{{ 使用者錯誤訊息 }}</div>
    <div v-else-if="!使用者資料" class="狀態列">輸入玩家名稱後即可查看個人成績單</div>
    <div v-else-if="使用者副本成績.length === 0" class="狀態列">目前沒有符合篩選條件的公開成績</div>

    <template v-else>
      <section class="個人成績概要" aria-label="個人成績概要">
        <div class="概要項 概要項計數">
          <span>副本數</span>
          <strong>{{ 使用者統計.副本數 }}</strong>
        </div>
        <div class="概要項 概要項計數">
          <span>公開成績</span>
          <strong>{{ 使用者統計.公開成績數 }}</strong>
        </div>
        <div class="概要項 概要項重點">
          <span class="說明標籤">
            <span>最佳 rDPS</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="最佳 rDPS 說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("最佳 rDPS") }}</span>
            </span>
          </span>
          <strong>{{ 格式化傷害數值(使用者統計.最佳成績?.rdps) }}</strong>
        </div>
        <div v-if="顯示Gcd覆蓋率" class="概要項 概要項重點 gcd參考文字">
          <span class="說明標籤">
            <span>最佳 GCD</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
            </span>
          </span>
          <strong>{{ 格式化Gcd覆蓋率(使用者統計.最高Gcd成績?.gcd_coverage) }}</strong>
        </div>
        <div class="概要項 概要項時間">
          <span>最後紀錄</span>
          <strong>{{ 格式化紀錄時間(使用者統計.最後紀錄時間) }}</strong>
        </div>
      </section>

      <section v-if="使用者徽章.length > 0" class="使用者徽章區" aria-label="個人徽章">
        <article v-for="徽章 in 使用者徽章" :key="徽章.名稱" class="使用者徽章" :class="徽章.樣式類別">
          <strong>{{ 徽章.名稱 }}</strong>
          <span>{{ 徽章.說明 }}</span>
        </article>
      </section>

      <section v-if="使用者分位亮點.length > 0" class="個人分位區" aria-label="個人分位亮點">
        <header class="成績趨勢標題">
          <h2>個人分位亮點</h2>
          <span>同副本同職業 rDPS 樣本比較</span>
        </header>
        <div class="個人分位列表">
          <article v-for="成績 in 使用者分位亮點" :key="成績.id" class="個人分位項">
            <span class="比較副本">
              <small>{{ 成績.encounter_category || "副本" }}</small>
              <strong>{{ 成績.encounter_name }}</strong>
            </span>
            <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
              <JobIcon
                class="職業圖示 職業標籤圖示"
                :code="成績.job"
              />
              <span>{{ 顯示職業名稱(成績.job) }}</span>
            </span>
            <strong :class="同職分位色彩類別(成績.performance)">{{ 格式化目前同職分位(成績.performance) }}</strong>
            <small>
              rDPS {{ 格式化傷害數值(成績.rdps) }}
              <span v-if="顯示Gcd覆蓋率" class="gcd參考文字">・GCD {{ 格式化Gcd覆蓋率(成績.gcd_coverage) }}</span>
              ・高於中位 {{ 格式化帶號整數(成績.performance?.delta_to_median) }}
            </small>
          </article>
        </div>
      </section>

      <section v-if="使用者成績趨勢.length > 0" class="成績趨勢區" aria-label="成績趨勢">
        <header class="成績趨勢標題">
          <h2>成績趨勢</h2>
          <span>公開 rDPS 歷史</span>
        </header>
        <div class="成績趨勢列表">
          <article v-for="趨勢 in 使用者成績趨勢" :key="趨勢.key" class="趨勢項">
            <header class="趨勢項標題">
              <div class="趨勢標題文字">
                <small>{{ 趨勢.encounter_category || "副本" }}</small>
                <strong>{{ 趨勢.encounter_name }}</strong>
                <span v-if="!趨勢.多職業" class="職業標籤 趨勢職業標籤" :class="職業色彩類別(趨勢.job_color)">
                  <JobIcon
                    class="職業圖示 職業標籤圖示"
                    :code="趨勢.job"
                  />
                  <span>{{ 趨勢.job_name || 顯示職業名稱(趨勢.job) }}</span>
                </span>
              </div>
              <em :class="{ 上升: 趨勢.變化 > 0, 下降: 趨勢.變化 < 0 }">{{ 格式化帶號整數(趨勢.變化) }}</em>
            </header>
            <div v-if="趨勢.多職業" class="趨勢職業切換列" role="group" :aria-label="`${趨勢.encounter_name} 職業切換`">
              <button
                v-for="選項 in 趨勢.職業選項"
                :key="`${趨勢.encounter_key}-${選項.代碼}`"
                class="趨勢職業按鈕"
                type="button"
                :class="[職業色彩類別(選項.色彩), { 作用中: 選項.已選取 }]"
                :aria-pressed="選項.已選取"
                @click="選擇使用者趨勢職業(趨勢.encounter_key, 選項.代碼)"
              >
                <JobIcon
                  class="職業圖示 職業標籤圖示"
                  :code="選項.代碼"
                />
                <span>{{ 選項.名稱 }}</span>
                <small>{{ 選項.紀錄數 }} 筆</small>
              </button>
            </div>
            <div class="趨勢摘要">
              <span>最新 {{ 格式化傷害數值(趨勢.最新?.rdps) }}</span>
              <span>最佳 {{ 趨勢.最佳 ? 格式化傷害數值(趨勢.最佳?.rdps) : "-" }}</span>
              <span>{{ 趨勢.點列表.length }} 筆</span>
            </div>
            <div class="趨勢圖" role="img" :aria-label="`${趨勢.encounter_name} rDPS 趨勢`">
              <svg class="趨勢曲線圖" viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                <line class="趨勢格線" x1="0" y1="10" x2="100" y2="10"></line>
                <line class="趨勢格線" x1="0" y1="26" x2="100" y2="26"></line>
                <line class="趨勢格線" x1="0" y1="42" x2="100" y2="42"></line>
                <path
                  v-for="區塊 in 趨勢.填色區塊列表"
                  :key="區塊.key"
                  class="趨勢面積"
                  :class="{ 過版: 區塊.過版紀錄 }"
                  :d="區塊.path"
                ></path>
                <path
                  v-for="線段 in 趨勢.線段列表"
                  :key="線段.key"
                  class="趨勢折線"
                  :class="{ 過版: 線段.過版紀錄 }"
                  :d="線段.path"
                ></path>
              </svg>
              <span class="趨勢點層" aria-hidden="true">
                <span
                  v-for="點 in 趨勢.點列表"
                  :key="點.id"
                  class="趨勢點"
                  :class="{ 過版: 點.過版紀錄 }"
                  :style="趨勢點樣式(點)"
                  :title="`${格式化紀錄時間(點.recorded_at_iso)}・${顯示職業名稱(點.job)}・rDPS ${格式化傷害數值(點.rdps)}${顯示Gcd覆蓋率 ? `・GCD ${格式化Gcd覆蓋率(點.gcd_coverage)}` : ''}${點.過版紀錄 ? '・過版紀錄' : ''}`"
                ></span>
              </span>
              <div class="趨勢刻度" aria-hidden="true">
                <span>{{ 格式化傷害數值(趨勢.最高) }}</span>
                <span>{{ 格式化傷害數值(趨勢.最低) }}</span>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section v-if="使用者隊友列表.length > 0" class="隊友關係區" aria-label="隊友關係">
        <header class="隊友關係標題">
          <h2 class="說明標籤">
            <span>隊友關係</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="隊友關係說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("隊友關係") }}</span>
            </span>
          </h2>
          <span>{{ 使用者隊友列表.length }} 位公開同場玩家</span>
        </header>

        <div class="隊友關係版面">
          <article class="常同場隊友卡">
            <header class="隊友子面板標題">
              <h3>常同場隊友</h3>
              <span>前 {{ 常見隊友.length }} 位</span>
            </header>
            <div class="常同場隊友列表">
              <button
                v-for="隊友 in 常見隊友"
                :key="`${隊友.character_name}@${隊友.server}`"
                class="常同場隊友項"
                type="button"
                @click="開啟隊友成績單(隊友)"
              >
                <span class="常同場隊友主列">
                  <strong>{{ 隊友.character_name }}</strong>
                  <em>{{ 隊友.同場次數 }} 場</em>
                </span>
                <span class="隊友強度條" aria-hidden="true">
                  <span :style="比例條樣式(隊友.強度)"></span>
                </span>
                <span class="常同場隊友資訊">
                  <small>{{ 隊友.server }}</small>
                  <small>{{ 隊友.職業文字 || "多職業" }}</small>
                  <small v-if="隊友.副本文字">{{ 隊友.副本文字 }}</small>
                </span>
              </button>
            </div>
          </article>

          <article class="隊友洞察卡">
            <header class="隊友子面板標題">
              <h3>關係輪廓</h3>
              <span>{{ 隊友關係摘要.關係型態 }}</span>
            </header>
            <div class="隊友摘要格">
              <div class="隊友摘要項">
                <small>同場紀錄</small>
                <strong>{{ 格式化整數(隊友關係摘要.總同場次數) }}</strong>
                <em>{{ 使用者隊友列表.length }} 位玩家</em>
              </div>
              <div class="隊友摘要項">
                <small>重複同場</small>
                <strong>{{ 格式化整數(隊友關係摘要.高頻隊友數) }}</strong>
                <em>2 場以上</em>
              </div>
              <div class="隊友摘要項">
                <small>主要聚集</small>
                <strong>{{ 隊友關係摘要.主要副本?.encounter_name || "-" }}</strong>
                <em v-if="隊友關係摘要.主要副本">
                  {{ 格式化整數(隊友關係摘要.主要副本.teammate_count) }} 位隊友
                </em>
                <em v-else>-</em>
              </div>
              <div class="隊友摘要項">
                <small>最近同場</small>
                <strong>{{ 格式化紀錄時間(隊友關係摘要.最近同場時間) }}</strong>
                <em>{{ 格式化整數(隊友關係摘要.伺服器數) }} 伺服器</em>
              </div>
            </div>
            <p class="隊友洞察文字">{{ 隊友關係摘要.說明 }}</p>
            <div v-if="隊友職能分布.length > 0" class="隊友職能分布">
              <div v-for="職能 in 隊友職能分布" :key="職能.代碼" class="隊友職能項">
                <span class="隊友職能名稱">
                  <JobIcon
                    class="職業圖示"
                    kind="role"
                    :code="職能.代碼"
                    :alt="職能.名稱"
                  />
                  <strong>{{ 職能.名稱 }}</strong>
                </span>
                <em>{{ 格式化整數(職能.人數) }} 位</em>
                <span class="分布條" aria-hidden="true">
                  <span
                    class="分布條填滿"
                    :class="職業色彩類別(職能.色彩)"
                    :style="比例條樣式(職能.強度)"
                  ></span>
                </span>
              </div>
            </div>
          </article>
        </div>

        <div v-if="隊友副本交集.length > 0" class="隊友副本區">
          <header class="隊友副本標題">
            <h3 class="說明標籤">
              <span>同場副本聚集</span>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="同場副本聚集說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("同場副本聚集") }}</span>
              </span>
            </h3>
            <span>顯示同場紀錄主要集中在哪些副本</span>
          </header>
          <div class="隊友副本交集">
            <article v-for="副本 in 隊友副本交集" :key="副本.encounter_key" class="隊友副本項">
              <div class="分布列">
                <strong>{{ 副本.encounter_name }}</strong>
                <span>{{ 格式化整數(副本.co_clear_count) }} 場・{{ 格式化整數(副本.teammate_count) }} 位隊友</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :style="比例條樣式(副本.強度)"></span>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section class="個人成績列表" aria-label="各副本成績">
        <details v-for="副本 in 使用者副本成績" :key="副本.encounter_key" class="個人成績列">
          <summary class="成績列摘要">
            <span class="成績列副本">
              <small>{{ 副本.encounter_category || "副本" }}</small>
              <strong>{{ 副本.encounter_name }}</strong>
            </span>
            <span v-if="副本.best_entry" class="職業標籤 成績列職業" :class="職業色彩類別(職業代碼色彩(副本.best_entry.job))">
              <JobIcon
                class="職業圖示 職業標籤圖示"
                :code="副本.best_entry.job"
              />
              <span>{{ 顯示職業名稱(副本.best_entry.job) }}</span>
            </span>
            <span v-else class="版本紀錄標籤">無有效最佳紀錄</span>
            <span class="成績列數值 成績列數值次要">
              <small class="說明標籤">
                <span>職業 Rank</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="職業 Rank 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("職業 Rank") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化排名(副本.best_entry.job_rank ?? 副本.best_entry.rank) : "無法參考" }}</strong>
              <em
                v-if="副本.best_entry"
                :class="排名分位色彩類別(副本.best_entry.job_rank ?? 副本.best_entry.rank, 取得成績職業總數(副本.best_entry))"
              >
                {{ 格式化目前排名分位(副本.best_entry.job_rank ?? 副本.best_entry.rank, 取得成績職業總數(副本.best_entry)) }}
              </em>
            </span>
            <span class="成績列數值 成績列數值次要">
              <small class="說明標籤">
                <span>同職分位</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="同職分位說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("同職分位") }}</span>
                </span>
              </small>
              <strong :class="副本.best_entry ? 同職分位色彩類別(副本.best_entry.performance) : ''">
                {{ 副本.best_entry ? 格式化目前同職分位(副本.best_entry.performance) : "過時紀錄" }}
              </strong>
              <em v-if="副本.best_entry">中位 {{ 格式化帶號整數(副本.best_entry.performance?.delta_to_median) }}</em>
            </span>
            <span class="成績列數值 成績列數值狀態">
              <small class="說明標籤">
                <span>Active</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化Active(副本.best_entry.active_percent) : "-" }}</strong>
            </span>
            <span v-if="顯示Gcd覆蓋率" class="成績列數值 成績列數值狀態 gcd參考文字">
              <small class="說明標籤">
                <span>GCD</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化Gcd覆蓋率(副本.best_entry.gcd_coverage) : "-" }}</strong>
            </span>
            <span class="成績列數值 成績列數值輸出">
              <small class="說明標籤">
                <span>DPS</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="DPS 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("DPS") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化傷害數值(副本.best_entry.dps) : "-" }}</strong>
            </span>
            <span class="成績列數值 成績列數值輸出 成績列數值主要">
              <small class="說明標籤">
                <span>rDPS</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="rDPS 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("rDPS") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化傷害數值(副本.best_entry.rdps) : "-" }}</strong>
            </span>
            <span class="成績列數值 成績列數值輸出">
              <small class="說明標籤">
                <span>aDPS</span>
                <span class="說明提示">
                  <button class="說明提示按鈕" type="button" aria-label="aDPS 說明">?</button>
                  <span class="說明提示內容" role="tooltip">{{ 統計說明文字("aDPS") }}</span>
                </span>
              </small>
              <strong>{{ 副本.best_entry ? 格式化傷害數值(副本.best_entry.adps) : "-" }}</strong>
            </span>
            <span class="成績列展開">{{ 副本.public_entries.length }} 筆</span>
          </summary>

          <div class="歷史表格外框">
            <table class="歷史表格">
              <thead>
                <tr>
                  <th scope="col">紀錄時間</th>
                  <th scope="col">職業</th>
                  <th scope="col" class="歷史報告欄位">報告</th>
                  <th scope="col" class="數字">
                    <span class="表頭說明標籤">
                      <span>同職分位</span>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="同職分位說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("同職分位") }}</span>
                      </span>
                    </span>
                  </th>
                  <th scope="col" class="數字">
                    <span class="表頭說明標籤">
                      <span>Active</span>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
                      </span>
                    </span>
                  </th>
                  <th v-show="顯示Gcd覆蓋率" scope="col" class="數字 gcd參考文字">
                    <span class="表頭說明標籤">
                      <span>GCD</span>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
                      </span>
                    </span>
                  </th>
                  <th scope="col" class="數字">
                    <span class="表頭說明標籤">
                      <span>DPS</span>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="DPS 說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("DPS") }}</span>
                      </span>
                    </span>
                  </th>
                  <th scope="col" class="數字">
                    <span class="表頭說明標籤">
                      <span>rDPS</span>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="rDPS 說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("rDPS") }}</span>
                      </span>
                    </span>
                  </th>
                  <th scope="col" class="數字">
                    <span class="表頭說明標籤">
                      <span>aDPS</span>
                      <span class="說明提示">
                        <button class="說明提示按鈕" type="button" aria-label="aDPS 說明">?</button>
                        <span class="說明提示內容" role="tooltip">{{ 統計說明文字("aDPS") }}</span>
                      </span>
                    </span>
                  </th>
                  <th scope="col" class="數字">通關時間</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="成績 in 副本.public_entries" :key="成績.id" :class="{ 過版紀錄列: 成績.is_obsolete_record }">
                  <td>{{ 格式化紀錄時間(成績.recorded_at_iso) }}</td>
                  <td>
                    <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
                      <JobIcon
                        class="職業圖示 職業標籤圖示"
                        :code="成績.job"
                      />
                      <span>{{ 顯示職業名稱(成績.job) }}</span>
                    </span>
                  </td>
                  <td class="歷史報告欄位">
                    <button
                      v-if="成績.report_code || 成績.report_url"
                      class="報告按鈕"
                      type="button"
                      @click="開啟個人成績報告彈窗(成績, 副本)"
                    >
                      報告
                    </button>
                    <span v-else>-</span>
                  </td>
                  <td class="數字" :class="成績.is_obsolete_record ? '' : 同職分位色彩類別(成績.performance)">
                    {{ 成績.is_obsolete_record ? "過時紀錄" : 格式化目前同職分位(成績.performance) }}
                  </td>
                  <td class="數字">{{ 格式化Active(成績.active_percent) }}</td>
                  <td v-show="顯示Gcd覆蓋率" class="數字 gcd參考文字">{{ 格式化Gcd覆蓋率(成績.gcd_coverage) }}</td>
                  <td class="數字">{{ 格式化傷害數值(成績.dps) }}</td>
                  <td class="數字">{{ 格式化傷害數值(成績.rdps) }}</td>
                  <td class="數字">{{ 格式化傷害數值(成績.adps) }}</td>
                  <td class="數字">{{ 格式化通關時間(成績.clear_time_seconds) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </details>
      </section>
    </template>
  </section>

  <ReportDetailDialog :details="報告彈窗資料" @close="關閉個人成績報告彈窗" />
</template>
