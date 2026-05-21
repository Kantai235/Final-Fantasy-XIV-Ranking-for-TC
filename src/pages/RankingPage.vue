<script>
import { ref } from "vue";
import ReportDetailDialog from "../components/ReportDetailDialog.vue";
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "RankingPage",
  components: {
    ReportDetailDialog,
  },
  setup() {
    const app = injectRankingApp();
    const 報告彈窗資料 = ref(null);

    function 取值(可能Ref) {
      return 可能Ref && typeof 可能Ref === "object" && "value" in 可能Ref ? 可能Ref.value : 可能Ref;
    }

    function 建立排行報告詳細資料(列, 排名 = null) {
      const 顯示Gcd = Boolean(取值(app.顯示Gcd覆蓋率));
      const 實際排名 = 排名 ?? 列.原始排名 ?? null;
      const 目前副本 = 取值(app.目前副本);
      const 狀態項目 = [
        {
          key: "rank",
          label: "排名",
          value: app.格式化排名(實際排名),
          className: "報告彈窗排名項",
        },
        {
          key: "active",
          label: "Active",
          value: app.格式化Active(列.active),
          tooltip: app.統計說明文字("Active"),
          tooltipLabel: "Active 說明",
        },
        ...(顯示Gcd
          ? [
              {
                key: "gcd",
                label: "GCD",
                value: app.格式化Gcd覆蓋率(列.gcd_coverage),
                tooltip: app.統計說明文字("GCD 覆蓋率"),
                tooltipLabel: "GCD 覆蓋率說明",
              },
            ]
          : []),
        {
          key: "clearTime",
          label: "通關時間",
          value: app.格式化通關時間(列.通關秒數),
          className: "報告彈窗時間項",
        },
      ];

      return {
        subtitle: 目前副本?.name || "排行榜成績",
        title: 列.角色名稱,
        identity: `${列.伺服器} · ${列.職業}`,
        record: 列,
        statusItems: 狀態項目,
        damageItems: [
          {
            key: "dps",
            label: "DPS",
            value: app.格式化傷害數值(列.dps),
            tooltip: app.統計說明文字("DPS"),
            tooltipLabel: "DPS 說明",
          },
          {
            key: "rdps",
            label: "rDPS",
            value: app.格式化傷害數值(列.rdps),
            tooltip: app.統計說明文字("rDPS"),
            tooltipLabel: "rDPS 說明",
            className: "報告彈窗主要數值",
          },
          {
            key: "adps",
            label: "aDPS",
            value: app.格式化傷害數值(列.adps),
            tooltip: app.統計說明文字("aDPS"),
            tooltipLabel: "aDPS 說明",
          },
        ],
        traceItems: [
          {
            key: "reportFight",
            label: "Report / Fight",
            value: `${列.reportCode || "-"}${列.fightId ? ` · ${列.fightId}` : ""}`,
          },
          {
            key: "recordedAt",
            label: "紀錄時間",
            value: app.格式化紀錄時間(列.紀錄時間),
          },
        ],
      };
    }

    function 開啟排行報告彈窗(列, 排名 = null) {
      報告彈窗資料.value = 建立排行報告詳細資料(列, 排名);
    }

    function 關閉排行報告彈窗() {
      報告彈窗資料.value = null;
    }

    return {
      ...app,
      報告彈窗資料,
      開啟排行報告彈窗,
      關閉排行報告彈窗,
    };
  },
};
</script>

<template>
<section class="工具列" aria-label="排行榜篩選">
  <div class="欄位 副本選單欄位" @focusout="處理副本選單失焦">
    <span>副本</span>
    <div class="副本選單">
      <button
        class="副本選單按鈕"
        type="button"
        :aria-expanded="副本選單開啟"
        aria-haspopup="true"
        @click="切換副本選單"
      >
        <span class="副本選單目前值">{{ 副本選單文字 }}</span>
        <span class="選單箭頭">▾</span>
      </button>

      <div v-if="副本選單開啟" class="副本選單面板" role="menu" aria-label="副本">
        <section v-for="分組 in 副本分組" :key="分組.分類" class="副本分類群">
          <p class="副本分類標題">{{ 分組.分類 }}</p>
          <button
            v-for="副本 in 分組.副本列表"
            :key="副本.key"
            class="副本選單項"
            type="button"
            :class="{ 已選取: 副本鍵值 === 副本.key }"
            @click="選擇副本(副本)"
          >
            {{ 副本.name }}
          </button>
        </section>
      </div>
    </div>
  </div>

  <label v-if="顯示排行榜版本篩選" class="欄位">
    <span>版本紀錄</span>
    <select v-model="排行榜版本範圍">
      <option v-for="選項 in 版本紀錄範圍選項" :key="選項.value" :value="選項.value">
        {{ 選項.label }}
      </option>
    </select>
  </label>

  <label class="欄位 排行榜伺服器欄位">
    <span>伺服器</span>
    <select v-model="伺服器篩選">
      <option value="">全部伺服器</option>
      <option v-for="伺服器 in 伺服器選項" :key="伺服器" :value="伺服器">
        {{ 伺服器 }}
      </option>
    </select>
  </label>

  <div class="欄位 職業選單欄位" @focusout="處理職業選單失焦">
    <span>職業</span>
    <div class="職業選單">
      <button
        class="職業選單按鈕"
        type="button"
        :aria-expanded="職業選單開啟"
        aria-haspopup="true"
        @click="切換職業選單"
      >
        <span class="職業選單目前值">
          <img
            v-if="職業選單Icon路徑"
            class="職業圖示"
            :src="職業選單Icon路徑"
            alt=""
            loading="lazy"
            @error="隱藏載入失敗圖片"
          />
          <span>{{ 職業選單文字 }}</span>
        </span>
        <span class="選單箭頭">▾</span>
      </button>

      <div v-if="職業選單開啟" class="職業選單面板">
        <div class="職業選單分類欄" role="menu" aria-label="職業類型">
          <button
            class="職業選單項"
            type="button"
            :class="{ 已選取: !職業類型篩選 && !職業篩選 }"
            @click="清除職業篩選"
          >
            全部職業
          </button>
          <button
            v-for="類型 in 職業類型選項"
            :key="類型.代碼"
            class="職業選單項"
            type="button"
            :class="[職業色彩類別(類型.色彩), { 已選取: 職業類型篩選 === 類型.代碼 }]"
            @click="選擇職業類型(類型.代碼)"
          >
            <img
              v-if="職業類型Icon路徑(類型.代碼)"
              class="職業圖示"
              :src="職業類型Icon路徑(類型.代碼)"
              alt=""
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
            <span>{{ 類型.名稱 }}</span>
          </button>
        </div>

        <div class="職業選單職業欄" role="menu" aria-label="職業">
          <template v-if="職業類型篩選 && 職業選項.length > 0">
            <button
              v-for="職業 in 職業選項"
              :key="職業.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(職業.色彩), { 已選取: 職業篩選 === 職業.代碼 }]"
              @click="選擇職業(職業.代碼)"
            >
              <img
                v-if="職業Icon路徑(職業.代碼)"
                class="職業圖示"
                :src="職業Icon路徑(職業.代碼)"
                alt=""
                loading="lazy"
                @error="隱藏載入失敗圖片"
              />
              <span>{{ 職業.名稱 }}</span>
            </button>
          </template>
        </div>
      </div>
    </div>
  </div>

  <label class="欄位 搜尋欄位">
    <span>玩家名稱</span>
    <input v-model="搜尋關鍵字" type="search" placeholder="搜尋玩家名稱" />
  </label>
</section>

<p v-if="排行榜版本說明文字" class="版本紀錄說明">{{ 排行榜版本說明文字 }}</p>

<section class="表格區" aria-live="polite">
  <div v-if="讀取中" class="狀態列">讀取排行榜資料中</div>
  <div v-else-if="錯誤訊息" class="狀態列 錯誤">{{ 錯誤訊息 }}</div>
  <div v-else-if="過濾後排行列.length === 0" class="狀態列">目前沒有符合條件的排行榜資料</div>

  <template v-else>
    <div class="分頁資訊列">
      <p>顯示第 {{ 顯示起始排名 }}-{{ 顯示結束排名 }} 名，共 {{ 過濾後排行列.length }} 筆</p>
      <div class="分頁控制 分頁控制頂部" aria-label="排行榜分頁">
        <button type="button" :disabled="!有上一頁" @click="前一頁">上一頁</button>
        <div class="頁碼群組">
          <label>
            <span>頁碼</span>
            <input
              v-model.number="目前頁碼"
              type="number"
              min="1"
              :max="總頁數"
              inputmode="numeric"
              @change="前往頁碼(目前頁碼)"
            />
          </label>
          <span class="頁數文字">/ {{ 總頁數 }}</span>
        </div>
        <button type="button" :disabled="!有下一頁" @click="下一頁">下一頁</button>
      </div>
    </div>

    <table class="排行榜表格">
      <colgroup>
        <col class="排名欄" />
        <col class="角色欄" />
        <col class="伺服器欄" />
        <col class="職業欄" />
        <col class="active欄" />
        <col v-show="顯示Gcd覆蓋率" class="gcd欄" />
        <col class="傷害欄" />
        <col class="傷害欄" />
        <col class="傷害欄" />
        <col class="通關時間欄" />
        <col class="紀錄時間欄" />
      </colgroup>
      <thead>
        <tr>
          <th scope="col" :aria-sort="排序ARIA('rank')">
            <button
              class="表頭排序按鈕"
              type="button"
              :class="{ 作用中: 是否目前排序('rank') }"
              :aria-label="排序按鈕標籤('rank')"
              @click="切換排序('rank')"
            >
              <span>排名</span>
              <span v-if="是否目前排序('rank')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("rank") }}</span>
            </button>
          </th>
          <th scope="col">玩家名稱</th>
          <th scope="col">伺服器</th>
          <th scope="col">職業</th>
          <th scope="col" class="數字" :aria-sort="排序ARIA('active')">
            <span class="表頭說明標籤">
              <button
                class="表頭排序按鈕"
                type="button"
                :class="{ 作用中: 是否目前排序('active') }"
                :aria-label="排序按鈕標籤('active')"
                @click="切換排序('active')"
              >
                <span>Active</span>
                <span v-if="是否目前排序('active')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("active") }}</span>
              </button>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="Active 說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("Active") }}</span>
              </span>
            </span>
          </th>
          <th v-show="顯示Gcd覆蓋率" scope="col" class="數字" :aria-sort="排序ARIA('gcdCoverage')">
            <span class="表頭說明標籤">
              <button
                class="表頭排序按鈕"
                type="button"
                :class="{ 作用中: 是否目前排序('gcdCoverage') }"
                :aria-label="排序按鈕標籤('gcdCoverage')"
                @click="切換排序('gcdCoverage')"
              >
                <span>GCD</span>
                <span v-if="是否目前排序('gcdCoverage')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("gcdCoverage") }}</span>
              </button>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="GCD 覆蓋率說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("GCD 覆蓋率") }}</span>
              </span>
            </span>
          </th>
          <th scope="col" class="數字" :aria-sort="排序ARIA('dps')">
            <span class="表頭說明標籤">
              <button
                class="表頭排序按鈕"
                type="button"
                :class="{ 作用中: 是否目前排序('dps') }"
                :aria-label="排序按鈕標籤('dps')"
                @click="切換排序('dps')"
              >
                <span>DPS</span>
                <span v-if="是否目前排序('dps')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("dps") }}</span>
              </button>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="DPS 說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("DPS") }}</span>
              </span>
            </span>
          </th>
          <th scope="col" class="數字" :aria-sort="排序ARIA('rdps')">
            <span class="表頭說明標籤">
              <button
                class="表頭排序按鈕"
                type="button"
                :class="{ 作用中: 是否目前排序('rdps') }"
                :aria-label="排序按鈕標籤('rdps')"
                @click="切換排序('rdps')"
              >
                <span>rDPS</span>
                <span v-if="是否目前排序('rdps')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("rdps") }}</span>
              </button>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="rDPS 說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("rDPS") }}</span>
              </span>
            </span>
          </th>
          <th scope="col" class="數字" :aria-sort="排序ARIA('adps')">
            <span class="表頭說明標籤">
              <button
                class="表頭排序按鈕"
                type="button"
                :class="{ 作用中: 是否目前排序('adps') }"
                :aria-label="排序按鈕標籤('adps')"
                @click="切換排序('adps')"
              >
                <span>aDPS</span>
                <span v-if="是否目前排序('adps')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("adps") }}</span>
              </button>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="aDPS 說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("aDPS") }}</span>
              </span>
            </span>
          </th>
          <th scope="col" class="數字" :aria-sort="排序ARIA('clearTime')">
            <button
              class="表頭排序按鈕"
              type="button"
              :class="{ 作用中: 是否目前排序('clearTime') }"
              :aria-label="排序按鈕標籤('clearTime')"
              @click="切換排序('clearTime')"
            >
              <span>通關時間</span>
              <span v-if="是否目前排序('clearTime')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("clearTime") }}</span>
            </button>
          </th>
          <th scope="col" :aria-sort="排序ARIA('recordedAt')">
            <button
              class="表頭排序按鈕"
              type="button"
              :class="{ 作用中: 是否目前排序('recordedAt') }"
              :aria-label="排序按鈕標籤('recordedAt')"
              @click="切換排序('recordedAt')"
            >
              <span>紀錄時間</span>
              <span v-if="是否目前排序('recordedAt')" class="排序箭頭" aria-hidden="true">{{ 排序方向圖示("recordedAt") }}</span>
            </button>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(列, index) in 當頁排行列" :key="列.id" :class="{ 過版紀錄列: 列.過版紀錄 }">
          <td class="排名" :class="排名色彩類別(排行列顯示排名(index))">
            <span class="排名徽章" :aria-label="格式化排名(排行列顯示排名(index))">
              <span
                v-if="格式化排名(排行列顯示排名(index)).startsWith('#')"
                class="排名井號"
                aria-hidden="true"
              >
                #
              </span>
              <span class="排名數字">{{ 格式化排名(排行列顯示排名(index)).replace(/^#/, "") }}</span>
            </span>
          </td>
          <td class="排行榜角色欄位">
            <button class="文字連結" type="button" @click="開啟個人成績單(列)">
              {{ 列.角色名稱 }}
            </button>
            <span v-if="列.過版紀錄" class="版本紀錄標籤">過版紀錄</span>
            <span v-if="顯示作者相關標示 && 是網站作者(列.角色名稱)" class="說明提示 作者提示">
              <button class="說明提示按鈕 作者勾勾按鈕" type="button" aria-label="網站作者說明">✓</button>
              <span class="說明提示內容" role="tooltip">{{ 作者說明文字 }}</span>
            </span>
            <button
              v-if="列.reportCode || 列.reportUrl"
              class="次要連結 報告按鈕"
              type="button"
              @click="開啟排行報告彈窗(列, 排行列顯示排名(index))"
            >
              報告
            </button>
            <div class="手機排行卡">
              <div class="手機排行主列">
                <span class="手機排行職業" :title="列.職業">
                  <img
                    v-if="職業Icon路徑(列.職業代碼)"
                    class="職業圖示"
                    :src="職業Icon路徑(列.職業代碼)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                </span>
                <div class="手機排行身份列">
                  <span class="手機排行角色名稱列">
                    <button class="文字連結 手機排行角色名稱" type="button" @click="開啟個人成績單(列)">
                      {{ 列.角色名稱 }}
                    </button>
                    <span v-if="列.過版紀錄" class="版本紀錄標籤">過版紀錄</span>
                    <span v-if="顯示作者相關標示 && 是網站作者(列.角色名稱)" class="說明提示 作者提示">
                      <button class="說明提示按鈕 作者勾勾按鈕" type="button" aria-label="網站作者說明">✓</button>
                      <span class="說明提示內容" role="tooltip">{{ 作者說明文字 }}</span>
                    </span>
                  </span>
                  <span class="手機排行伺服器">@{{ 列.伺服器 }}</span>
                </div>
              </div>
              <div class="手機排行傷害列">
                <span>
                  <em>DPS</em>
                  <strong>{{ 格式化傷害數值(列.dps) }}</strong>
                </span>
                <span class="手機排行重點傷害">
                  <em>rDPS</em>
                  <strong>{{ 格式化傷害數值(列.rdps) }}</strong>
                </span>
                <span>
                  <em>aDPS</em>
                  <strong>{{ 格式化傷害數值(列.adps) }}</strong>
                </span>
              </div>
              <div class="手機排行資訊列">
                <span v-if="顯示Gcd覆蓋率">
                  <em>GCD</em>
                  <strong>{{ 格式化Gcd覆蓋率(列.gcd_coverage) }}</strong>
                </span>
                <span>
                  <em>通關</em>
                  <strong>{{ 格式化通關時間(列.通關秒數) }}</strong>
                </span>
                <span>
                  <em>紀錄</em>
                  <time :datetime="列.紀錄時間 || undefined" :title="格式化紀錄時間(列.紀錄時間)">
                    {{ 格式化紀錄日期(列.紀錄時間) }} {{ 格式化紀錄時刻(列.紀錄時間) }}
                  </time>
                </span>
                <button
                  v-if="列.reportCode || 列.reportUrl"
                  class="報告按鈕"
                  type="button"
                  @click="開啟排行報告彈窗(列, 排行列顯示排名(index))"
                >
                  報告
                </button>
              </div>
            </div>
          </td>
          <td>{{ 列.伺服器 }}</td>
          <td>
            <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.職業代碼))">
              <img
                v-if="職業Icon路徑(列.職業代碼)"
                class="職業圖示 職業標籤圖示"
                :src="職業Icon路徑(列.職業代碼)"
                alt=""
                loading="lazy"
                @error="隱藏載入失敗圖片"
              />
              <span>{{ 列.職業 }}</span>
            </span>
          </td>
          <td class="數字">{{ 格式化Active(列.active) }}</td>
          <td v-show="顯示Gcd覆蓋率" class="數字">{{ 格式化Gcd覆蓋率(列.gcd_coverage) }}</td>
          <td class="數字">{{ 格式化傷害數值(列.dps) }}</td>
          <td class="數字">{{ 格式化傷害數值(列.rdps) }}</td>
          <td class="數字">{{ 格式化傷害數值(列.adps) }}</td>
          <td class="數字">{{ 格式化通關時間(列.通關秒數) }}</td>
          <td>
            <time
              class="緊湊紀錄時間"
              :datetime="列.紀錄時間 || undefined"
              :title="格式化紀錄時間(列.紀錄時間)"
              :aria-label="`紀錄時間 ${格式化紀錄時間(列.紀錄時間)}`"
            >
              <span>{{ 格式化紀錄日期(列.紀錄時間) }}</span>
              <span>{{ 格式化紀錄時刻(列.紀錄時間) }}</span>
            </time>
          </td>
        </tr>
      </tbody>
    </table>

    <div class="分頁資訊列 分頁資訊列底部">
      <p>每頁 {{ 每頁筆數 }} 筆</p>
      <div class="分頁控制 分頁控制底部" aria-label="排行榜底部分頁">
        <button type="button" :disabled="!有上一頁" @click="前一頁">上一頁</button>
        <span class="頁數文字">第 {{ 安全目前頁碼 }} / {{ 總頁數 }} 頁</span>
        <button type="button" :disabled="!有下一頁" @click="下一頁">下一頁</button>
      </div>
    </div>
  </template>
</section>

<ReportDetailDialog :details="報告彈窗資料" @close="關閉排行報告彈窗" />
</template>
