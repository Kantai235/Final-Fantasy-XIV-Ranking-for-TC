<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import 版本資料 from "virtual:version-progress";
import VersionTrendHint from "../components/VersionTrendHint.vue";
import VersionForecastSummary from "../components/VersionForecastSummary.vue";
import { 寫入網址狀態, 讀取目前網址狀態 } from "../utils/urlState";
import { 格式化版本日期 as 日期, 正規化版本進度選取, 僅顯示版本同步 } from "../utils/versionProgress";

const 選取 = ref(正規化版本進度選取(版本資料, 讀取目前網址狀態()));
const 實際視圖 = computed(() => 版本資料.views[選取.value.patchScope]);
const 推測 = computed(() => 實際視圖.value.forecast);
const 顯示推測 = computed(() => 選取.value.guess && Boolean(推測.value.rows));
const 視圖 = computed(() => 顯示推測.value ? 推測.value : 實際視圖.value);
const 國際預定 = computed(() => 顯示推測.value ? 版本資料.international_plans.filter((計畫) => 視圖.value.stages.includes(計畫.patch)) : []);
const 圖表截止日 = computed(() => 顯示推測.value ? 推測.value.plot_end_day : 版本資料.end_day);
const 圖表階段 = computed(() => 視圖.value.stages);
const 選取列 = computed(() => 視圖.value.rows.find((列) => 列.patch === 選取.value.patch));
const 同步提示版本 = computed(() => new Set(視圖.value.rows.filter(僅顯示版本同步).map((列) => 列.patch)));
const 同步提示終點 = computed(() => 顯示推測.value && 推測.value.synchronization_start?.day === 圖表截止日.value
  && 同步提示版本.value.has(推測.value.synchronization_start.patch));
const 同步提示群組 = (群組) => 群組.rows.length === 1 && 僅顯示版本同步(群組.rows[0]);
// 主要版本的末期週期涵蓋尚未確定的 9.0，只調整呈現，不改動模型日期與計算。
/** @param {{patch:string}} 項 */
const 隱藏末期主版時長 = (項) => 顯示推測.value && 選取.value.patchScope === 'major' && 項.patch === '8.5';
// 未上線版本只提示公告狀態；提前收錄內容留在已上線版本的說明中。
const 顯示內容對照 = computed(() => 選取列.value.tc_released || 選取列.value.tc_version_omitted);
const 圖表容器 = ref(null);
const 容器寬度 = ref(1000);
let 尺寸觀察器;
const 圖寬 = computed(() => Math.max(620, 容器寬度.value));
const 圖高 = computed(() => Math.max(310, 圖表階段.value.length * 23 + 66));
const 左界 = 52;
const 右界 = computed(() => 圖寬.value - 116);
const 底界 = computed(() => 圖高.value - 48);
const x = (日) => 左界 + (日 - 版本資料.start_day) / Math.max(1, 圖表截止日.value - 版本資料.start_day) * (右界.value - 左界);
const y = (階段) => 底界.value - 階段 / Math.max(1, 圖表階段.value.length - 1) * (底界.value - 32);
const 線條 = computed(() => [
  { key: "international", name: "國際服", points: 實際視圖.value.international },
  { key: "tc", name: "繁中服", points: 實際視圖.value.tc },
]);
// 只有隨容器尺寸變化的座標投影留在 Vue；日期差與階段順序由建置層提供。
function 階梯路徑(點列, 終點 = 版本資料.end_day) {
  return 點列.map((點, i) => i === 0
    ? `M${x(點.day)},${y(點.stage)}` : `H${x(點.day)}V${y(點.stage)}`).join("") + `H${x(終點)}`;
}
const 推測線條 = computed(() => 顯示推測.value ? [
  { key: "international", name: "國際服", points: 推測.value.international },
  { key: "tc", name: "繁中服", points: 推測.value.tc },
] : []);
const 日期刻度 = computed(() => {
  const 間隔數 = 圖寬.value >= 850 ? 4 : 2;
  return Array.from({ length: 間隔數 + 1 }, (_, i) => {
    const 日 = 版本資料.start_day + Math.round((圖表截止日.value - 版本資料.start_day) * i / 間隔數);
    return { day: 日, label: i === 間隔數 && 同步提示終點.value ? '後續' : 日期(new Date(日 * 86400000).toISOString().slice(0, 10)) };
  });
});
function 更新選取(狀態) {
  選取.value = 正規化版本進度選取(版本資料, { ...選取.value, ...狀態 });
  寫入網址狀態({ page: "version-progress", ...選取.value });
}
function 套用網址() {
  選取.value = 正規化版本進度選取(版本資料, 讀取目前網址狀態());
}
function 繁中狀態(列) {
  if (列.tc_released) return "已上線";
  if (列.tc) return "已公告・尚未上線";
  if (列.tc_version_omitted) return "與小版本合併，\n因此無此版本號。";
  return "尚未公告改版日期";
}
function 上線文字(列, 地區) {
  if (列[地區]) return 日期(列[地區]);
  if (地區 === 'tc' && 列.tc_plan) return `預定 ${日期(列.tc_plan.date)}`;
  if (地區 === 'tc' && 列.tc_forecast_skipped) return '推測與其他版本合併';
  if (地區 === 'international' && 列.international_month) return `預定 ${日期(列.international_month)}`;
  if (列[`${地區}_estimated`]) return `推測約 ${日期(new Date(列[`${地區}_day`] * 86400000).toISOString().slice(0, 10))}`;
  return 地區 === 'tc' ? 繁中狀態(列) : '尚未公告改版日期';
}
function 時長備註(時長) {
  if (時長?.through_horizon) return '計至推測終點';
  if (時長?.estimated) return '推測';
  return 時長?.ongoing ? '持續增加中' : '';
}
/** @param {{days: number, ongoing: boolean, estimated?:boolean, through_horizon?:boolean}|null} 時長 */
function 時長文字(時長) {
  return 時長 ? `${時長.estimated ? '約 ' : ''}${時長.days} 天${時長備註(時長) ? `・${時長備註(時長)}` : ''}` : '—';
}
function 顯示單版時長(列, 地區) {
  const 時長 = 列[`${地區}_duration`];
  return Boolean(時長) && !隱藏末期主版時長(列) && !(列.patch === '8.56' && 時長.estimated);
}
/** @param {{lag_days: number|null, lag_estimated?:boolean}} 列 */
function 相隔文字(列) {
  return 列.lag_days !== null ? `${列.lag_estimated ? '約 ' : ''}${列.lag_days} 天` : '—';
}
function 推測節點標籤(點, 服名) {
  return 同步提示版本.value.has(點.patch) ? `${服名} ${點.patch}，可能與國際服同步，查看版本詳情`
    : `${點.planned ? '預告' : 點.estimated ? '推測' : '已公告'}${服名} ${點.patch} ${日期(點.date)}，查看版本詳情`;
}
/** @param {{patch:string, duration_outlook?:{international:string, tc:string}|null}} 群組 @param {'international'|'tc'} 地區 */
function 主版時長提示(群組, 地區) {
  if (隱藏末期主版時長(群組)) return '—';
  const 狀態 = 群組.duration_outlook?.[地區];
  return 狀態 === 'may_synchronize' ? '可能與國際服同步' : 狀態 === 'unknown' ? '—' : null;
}
onMounted(() => {
  尺寸觀察器 = new ResizeObserver(([項]) => { 容器寬度.value = Math.floor(項.contentRect.width); });
  尺寸觀察器.observe(圖表容器.value);
  window.addEventListener("popstate", 套用網址);
});
onBeforeUnmount(() => {
  尺寸觀察器?.disconnect();
  window.removeEventListener("popstate", 套用網址);
});
</script>

<template>
  <div class="版本進度內容">
    <section class="版本摘要" aria-label="兩服版本進度摘要">
      <div class="版本雙服">
        <div class="版本繁中"><span>繁中服</span><strong>{{ 版本資料.current_tc }}</strong></div>
        <div class="版本國際"><span>國際服</span><strong>{{ 版本資料.current_international }}</strong></div>
      </div>
      <div class="版本節點差">
        <span>版本標籤相隔</span>
        <p><strong>{{ 實際視圖.gap_count }}</strong><span>個{{ 選取.patchScope === 'all' ? '更新節點' : '主要版本' }}</span></p>
        <small>{{ 選取.patchScope === 'all' ? '包含小版本，依官方發布順序計算' : '僅計算 7.0、7.1…等主要版本' }}</small>
      </div>
      <div class="版本天數差">
        <span>同版本上線間隔</span>
        <p class="版本間隔數值"><strong><template v-if="版本資料.previous_comparable">{{ 版本資料.previous_comparable.lag_days }}<span> → </span></template>{{ 版本資料.latest_comparable.lag_days }}</strong> 天<VersionTrendHint id="版本間隔趨勢提示" direction="up" label="上線間隔上升說明" text="相隔的日期正在逐漸上升當中。" /></p>
        <small v-if="版本資料.previous_comparable" class="版本間隔變化">{{ 版本資料.previous_comparable.patch }} 至 {{ 版本資料.latest_comparable.patch }}，{{ 版本資料.lag_reduction >= 0 ? '縮短' : '增加' }} {{ Math.abs(版本資料.lag_reduction) }} 天<VersionTrendHint v-if="版本資料.lag_reduction > 0" id="版本縮短趨勢提示" direction="down" label="縮短天數下降說明" text="縮短的日期正在逐漸減少當中。" /></small>
        <small v-else>{{ 版本資料.latest_comparable.patch }}・尚無前版可比較</small>
      </div>
      <p class="版本摘要註記">節點差不等於待更新次數；部分內容已合併推出。天數差不代表追上所需時間。</p>
    </section>

    <section class="版本面板" aria-labelledby="版本歷程標題">
      <div class="版本面板標題">
        <div><h2 id="版本歷程標題">開服以來的追趕歷程</h2><p>橫軸是日期，縱軸是{{ 選取.patchScope === 'all' ? '包含小版本的' : '主要' }}版本階段。</p></div>
        <div class="版本面板操作"><p class="版本開服天數">開服至核對日 <strong>{{ 版本資料.elapsed_days }}</strong> 天</p><button class="版本猜測開關" type="button" role="switch" :aria-checked="選取.guess" aria-label="追趕歷程猜測模式" @click="更新選取({ guess: !選取.guess })"><span>猜測模式</span><span class="版本開關軌道" aria-hidden="true"></span><span aria-hidden="true">{{ 選取.guess ? '開啟' : '關閉' }}</span></button></div>
      </div>
      <div class="版本工具列">
        <div class="版本圖例"><span class="版本繁中">● 繁中服</span><span class="版本國際">● 國際服</span><span v-if="顯示推測" class="版本推測圖例">┄◇ 推測・{{ 推測.continuation_major ? '延伸至後續版本' : '虛線延伸至進度交會' }}</span></div>
        <div class="版本範圍切換" role="group" aria-label="版本顯示範圍">
          <button type="button" :aria-pressed="選取.patchScope === 'all'" @click="更新選取({ patchScope: 'all' })">包含小版本</button>
          <button type="button" :aria-pressed="選取.patchScope === 'major'" @click="更新選取({ patchScope: 'major' })">主要版本</button>
        </div>
      </div>
      <VersionForecastSummary v-if="選取.guess" :forecast="推測" :major="選取.patchScope === 'major'" />
      <p v-for="計畫 in 國際預定" :key="計畫.patch" class="版本國際預定說明">國際服 {{ 計畫.patch }}・官方預定 {{ 日期(計畫.month) }}，確切日期待公告。<a :href="計畫.url" target="_blank" rel="noopener noreferrer">官方來源 ↗</a></p>
      <p class="版本手機圖提示">左右滑動查看完整時間軸，也可由下方選單查看每個版本。</p>
      <div ref="圖表容器" class="版本圖表捲動" tabindex="0" role="region" aria-label="兩服版本時間軸，可左右捲動">
        <svg :width="圖寬" :height="圖高" :viewBox="`0 0 ${圖寬} ${圖高}`" class="版本時間軸" role="group" aria-labelledby="版本圖標題 版本圖說明">
          <title id="版本圖標題">繁中服與國際服版本階梯時間軸</title>
          <desc id="版本圖說明">版本階段等距排列，不代表內容量。點選節點可查看日期；完整資料也列於下方對照表。{{ 顯示推測 ? '虛線與菱形為兩服後續更新情境，並非已發布或官方公告。' : '' }}{{ 顯示推測 && 推測.synchronization_start ? '圖表包含繁中服可能開始與國際服同步更新的主版本。' : 顯示推測 && 推測.continuation_major ? '圖表延伸至首次追上後的下一個主版及所屬小版本。' : '' }}</desc>
          <g v-for="(版本, i) in 圖表階段" :key="版本" class="版本格線" :class="{ '版本格線選取': 選取.patch === 版本 }">
            <line :x1="左界" :x2="右界" :y1="y(i)" :y2="y(i)" />
            <text :x="左界 - 12" :y="y(i) + 4" text-anchor="end">{{ 版本 }}</text>
          </g>
          <g v-for="(刻度, i) in 日期刻度" :key="刻度.day" class="版本日期軸">
            <line :x1="x(刻度.day)" :x2="x(刻度.day)" y1="20" :y2="底界 + 8" />
            <text :x="x(刻度.day)" :y="底界 + 32" :text-anchor="i === 0 ? 'start' : i === 日期刻度.length - 1 ? 'end' : 'middle'">{{ 刻度.label }}</text>
          </g>
          <g v-for="線 in 線條" :key="線.key" :class="`版本線-${線.key}`">
            <path class="版本折線" :d="階梯路徑(線.points)" />
            <g v-for="點 in 線.points" :key="點.patch" class="版本節點" :class="{ '版本節點選取': 選取.patch === 點.patch }"
              role="button" tabindex="0" :aria-pressed="選取.patch === 點.patch" :aria-label="`${線.name} ${點.patch}，${日期(點.date)}${點.carried ? '，開服時已在此版本' : ' 上線'}`"
              @click="更新選取({ patch: 點.patch })" @keydown.enter.prevent="更新選取({ patch: 點.patch })" @keydown.space.prevent="更新選取({ patch: 點.patch })">
              <title>{{ 線.name }} {{ 點.patch }}・{{ 日期(點.date) }}</title>
              <circle class="版本節點觸控" :cx="x(點.day)" :cy="y(點.stage)" r="13" />
              <circle class="版本節點圓" :cx="x(點.day)" :cy="y(點.stage)" r="4" />
            </g>
            <text class="版本線端點" :x="x(版本資料.end_day) + 10" :y="y(線.points.at(-1).stage) + 4">{{ 線.name }} {{ 線.points.at(-1).patch }}</text>
          </g>
          <g v-if="顯示推測" class="版本推測圖層">
            <line class="版本推測核對線" :x1="x(版本資料.end_day)" :x2="x(版本資料.end_day)" y1="20" :y2="底界 + 8" />
            <text class="版本推測核對字" :x="x(版本資料.end_day) - 6" y="14" text-anchor="end">核對日</text>
            <g v-for="線 in 推測線條" :key="線.key" :class="`版本線-${線.key}`">
              <path class="版本推測折線" :d="階梯路徑(線.points, 圖表截止日)" />
              <g v-for="點 in 線.points.slice(1)" :key="點.patch" class="版本推測節點" role="button" tabindex="0" :aria-label="推測節點標籤(點, 線.name)" :aria-pressed="選取.patch === 點.patch" @click="更新選取({ patch: 點.patch })" @keydown.enter.prevent="更新選取({ patch: 點.patch })" @keydown.space.prevent="更新選取({ patch: 點.patch })">
                <circle class="版本推測觸控" :cx="x(點.day)" :cy="y(點.stage)" r="11" />
                <path :d="`M${x(點.day)},${y(點.stage) - 5}l5,5l-5,5l-5,-5Z`" />
              </g>
            </g>
            <text class="版本推測端點" :x="右界 + 10" :y="y(圖表階段.length - 1) - 10">{{ 推測.synchronization_start?.day === 推測.plot_end_day ? '可能開始同步' : 推測.continuation_major ? '推測終點' : 推測.catch_up ? '推測追上' : '推算終點' }}</text>
            <text v-if="!同步提示終點" class="版本推測端點" :x="右界 + 10" :y="y(圖表階段.length - 1) + 7">{{ 日期(推測.plot_end_date) }}</text>
          </g>
          <g v-for="計畫 in 國際預定" :key="計畫.patch" class="版本預定圖層" role="img" :aria-label="`國際服 ${計畫.patch} 官方預定 ${日期(計畫.month)}，確切日期待公告`">
            <rect :x="x(計畫.start_day)" :y="y(圖表階段.indexOf(計畫.patch)) - 6" :width="x(計畫.end_day) - x(計畫.start_day)" height="12" rx="2" />
            <text :x="右界 + 10" :y="y(圖表階段.indexOf(計畫.patch)) + 4">{{ 計畫.patch }} 預定 {{ 日期(計畫.month) }}</text>
          </g>
        </svg>
      </div>
      <div class="版本選取詳情" aria-live="polite">
        <label for="版本節點選單">查看版本
          <select id="版本節點選單" :value="選取.patch" @change="更新選取({ patch: $event.target.value })">
            <option v-for="列 in 視圖.rows" :key="列.patch" :value="列.patch">{{ 列.patch }} {{ 列.title }}</option>
          </select>
        </label>
        <strong v-if="僅顯示版本同步(選取列)" class="版本同步提示">可能與國際服同步</strong>
        <div v-else class="版本詳情日期"><span class="版本國際">國際服 {{ 上線文字(選取列, 'international') }}</span><span class="版本繁中">繁中服 <span class="版本繁中狀態" :class="{ '版本合併狀態': 選取列.tc_forecast_skipped }">{{ 上線文字(選取列, 'tc') }}</span></span></div>
        <p v-if="選取列.tc_plan" class="版本選取推測">{{ 選取列.tc_plan.attribution }}{{ 選取列.tc_plan_day <= 版本資料.end_day ? '；預告日期已過，仍待核對實際更新。' : '；實際更新仍以後續公告為準。' }}</p>
        <p v-if="選取列.tc_forecast_skipped" class="版本選取推測">本次情境假設繁中服略過 {{ 選取列.patch }}，尚未正式確認。</p>
        <p v-if="!僅顯示版本同步(選取列) && (選取列.tc_estimated || 選取列.international_estimated)" class="版本選取推測">推測日期依更新節奏與排程假設計算，非官方公告。{{ 選取列.merged_into ? `部分內容已隨 ${選取列.merged_into} 推出，此處假設仍有獨立更新。` : '' }}</p>
        <strong v-if="顯示內容對照 || (顯示推測 && 選取列.lag_days !== null && !僅顯示版本同步(選取列))">{{ 選取列.lag_days !== null ? `相隔 ${相隔文字(選取列)}` : '尚無同版本間隔' }}</strong>
        <p v-if="顯示內容對照 && 選取列.note" class="版本內容註記">{{ 選取列.note }}</p>
        <nav v-if="顯示內容對照 && 選取列.note_links.length" class="版本註記來源" :aria-label="`${選取列.patch} 內容對照來源`">
          <span>內容對照來源</span>
          <a v-for="來源 in 選取列.note_links" :key="來源.url" :href="來源.url" target="_blank" rel="noopener noreferrer" :aria-label="`${來源.label}（另開分頁）`">{{ 來源.label }} ↗</a>
        </nav>
      </div>
      <p class="版本面板註記">{{ 日期(版本資料.early_access_date) }} 搶先體驗；比較基準採 {{ 日期(版本資料.launch_date) }} 正式上市。版本階段等距排列，不代表內容量。</p>
    </section>

    <section class="版本面板" aria-labelledby="版本表標題">
      <div class="版本面板標題"><div><h2 id="版本表標題">每一版，走了多久</h2><p>{{ 選取.patchScope === 'all' ? '主要版本與小版本完整對照' : '目前僅顯示主要版本' }}・{{ 視圖.rows.length }} 個{{ 顯示推測 ? '實際與推測節點' : '已收錄節點' }}</p></div><div class="版本面板操作"><span class="版本核對標籤">核對至 {{ 日期(版本資料.verified_through) }}</span><button class="版本猜測開關" type="button" role="switch" :aria-checked="選取.guess" aria-label="版本面板猜測模式" @click="更新選取({ guess: !選取.guess })"><span>猜測模式</span><span class="版本開關軌道" aria-hidden="true"></span><span aria-hidden="true">{{ 選取.guess ? '開啟' : '關閉' }}</span></button></div></div>
      <p class="版本時長說明">日期下方為該版時長；主版本總時長包含所屬小版本。{{ 顯示推測 ? '推測時長會算至下一版；最後一版僅計至推測終點，並非完整週期。' : '標示「持續增加中」的時長計至核對日。' }}</p>
      <VersionForecastSummary v-if="選取.guess" :forecast="推測" :major="選取.patchScope === 'major'" />
      <table class="版本對照表">
        <caption class="版本輔助文字">兩服版本上線日期、各版時長、跨列的主版本總時長與同版本間隔；點選版本可同步查看圖表詳情。</caption>
        <thead><tr><th scope="col">版本</th><th scope="col">國際服<br>上線日期</th><th scope="col">國際服<br>主版本總時長</th><th scope="col">繁中服<br>上線日期</th><th scope="col">繁中服<br>主版本總時長</th><th scope="col">相隔天數</th><th scope="col">來源</th></tr></thead>
        <tbody v-for="群組 in 視圖.groups" :key="群組.patch" :aria-label="`${群組.patch} 主版本`">
          <tr v-if="同步提示群組(群組)" :class="{ '版本列選取': 選取.patch === 群組.patch }">
            <th scope="row"><button type="button" :aria-pressed="選取.patch === 群組.patch" @click="更新選取({ patch: 群組.patch })"><strong>{{ 群組.patch }}</strong><span>{{ 群組.rows[0].title }}</span></button></th>
            <td colspan="5" class="版本同步合併"><strong>繁中服可能於此版本開始與國際服同步更新。</strong></td>
            <td class="版本來源欄">情境推測</td>
          </tr>
          <template v-else>
          <tr class="版本群組摘要">
            <th colspan="7" scope="rowgroup">
              <strong>{{ 群組.patch }} 主版本總時長</strong>
              <div class="版本群組雙服"><span>國際服<strong>{{ 主版時長提示(群組, 'international') ?? 時長文字(群組.international_duration) }}</strong></span><span>繁中服<strong>{{ 主版時長提示(群組, 'tc') ?? 時長文字(群組.tc_duration) }}</strong></span></div>
            </th>
          </tr>
          <tr v-for="(列, i) in 群組.rows" :key="列.patch" :class="{ '版本列選取': 選取.patch === 列.patch, '版本列尚待': !列.tc_released }">
            <th scope="row"><button type="button" :aria-pressed="選取.patch === 列.patch" @click="更新選取({ patch: 列.patch })"><strong>{{ 列.patch }}</strong><span>{{ 列.title }}</span><small v-if="列.patch === 版本資料.current_tc">繁中現行</small></button></th>
            <td data-label="國際服上線"><span :class="{ '版本表推測': 列.international_estimated }">{{ 上線文字(列, 'international') }}</span><small v-if="顯示單版時長(列, 'international')" class="版本單版時長">時長 {{ 時長文字(列.international_duration) }}</small><small v-if="列.international_month">確切日期待公告</small><small v-else-if="列.international && !列.international_released">已公告・尚未上線</small></td>
            <td v-if="i === 0" :rowspan="群組.rows.length" class="版本主版時長" :aria-label="`${群組.patch} 國際服主版本總時長：${主版時長提示(群組, 'international') ?? 時長文字(群組.international_duration)}`"><span>{{ 群組.patch }}</span><strong v-if="主版時長提示(群組, 'international')" class="版本主版提示">{{ 主版時長提示(群組, 'international') }}</strong><template v-else><strong>{{ 群組.international_duration ? `${群組.international_duration.estimated ? '約 ' : ''}${群組.international_duration.days} 天` : '—' }}</strong><small v-if="時長備註(群組.international_duration)">{{ 時長備註(群組.international_duration) }}</small></template></td>
            <td data-label="繁中服上線"><span class="版本繁中狀態" :class="{ '版本表推測': !列.tc_forecast_skipped && (列.tc_estimated || 列.tc_plan), '版本合併狀態': 列.tc_forecast_skipped }">{{ 上線文字(列, 'tc') }}</span><small v-if="列.tc_plan">{{ 列.tc_plan.attribution }}</small><small v-if="顯示單版時長(列, 'tc')" class="版本單版時長">時長 {{ 時長文字(列.tc_duration) }}</small><small v-if="列.tc && !列.tc_released">已公告・尚未上線</small></td>
            <td v-if="i === 0" :rowspan="群組.rows.length" class="版本主版時長" :aria-label="`${群組.patch} 繁中服主版本總時長：${主版時長提示(群組, 'tc') ?? 時長文字(群組.tc_duration)}`"><span>{{ 群組.patch }}</span><strong v-if="主版時長提示(群組, 'tc')" class="版本主版提示">{{ 主版時長提示(群組, 'tc') }}</strong><template v-else><strong>{{ 群組.tc_duration ? `${群組.tc_duration.estimated ? '約 ' : ''}${群組.tc_duration.days} 天` : '—' }}</strong><small v-if="時長備註(群組.tc_duration)">{{ 時長備註(群組.tc_duration) }}</small></template></td>
            <td data-label="同版本間隔" class="版本間隔欄">{{ 相隔文字(列) }}</td>
            <td class="版本來源欄"><a v-if="列.international_url" :href="列.international_url" target="_blank" rel="noopener noreferrer" :aria-label="`${列.patch} 國際服官方來源（另開分頁）`">國際服 ↗</a><a v-if="列.tc_url && (列.tc || 列.tc_version_omitted)" :href="列.tc_url" target="_blank" rel="noopener noreferrer" :aria-label="`${列.patch} 繁中服官方來源（另開分頁）`">繁中服 ↗</a><a v-if="列.tc_plan_url" :href="列.tc_plan_url" target="_blank" rel="noopener noreferrer" :aria-label="`${列.patch} 繁中服預告來源（另開分頁）`">預告 ↗</a><span v-if="!列.international_url && !列.tc_url && !列.tc_plan_url">情境推測</span></td>
          </tr>
          </template>
        </tbody>
      </table>
    </section>
    <div class="版本資料說明">
      <p>同版本上線間隔＝繁中服上線日－國際服上線日。一般模式只比較已核對的上線日期；猜測模式另依雙服情境日期計算相隔天數。未核對到日期不代表內容未開放。猜測模式依更新節奏與排程假設延伸兩服更新，顯示首次進度交會、後續小版及可能開始同步的主版本，並重算各版及主版總時長；非官方公告，不納入摘要的已上線統計。</p>
      <details><summary>資料來源與比較方式</summary><p>以雙方官方公告及 The Lodestone 更新紀錄核對發布日，收錄有獨立版本號的更新；一般維護與修正不另計節點。繁中服未單獨發布或合併的版本保留國際服節點，並標示已核對的合併內容。部分功能、任務或獎勵調整可能提前收錄；請選取版本查看具體範圍與雙方更新筆記。內容對照是逐項比對公告的結果，不代表兩服整版完全相同，節點差也不能解讀為尚待推出的內容數量。</p><p>版本資料核對日：{{ 日期(版本資料.verified_through) }}。</p></details>
    </div>
  </div>
</template>
