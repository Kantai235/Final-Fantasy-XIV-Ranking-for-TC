<script setup>
import { computed } from 'vue';
import { 格式化版本日期 as 日期, 格式化版本星期 as 星期, 僅顯示版本同步, 取得版本日期提示, 取得版本追上提示 } from '../utils/versionProgress';
// 兩處摘要共用頁面的台灣時鐘，避免各自建立計時器、跨日時顯示不同天數。
const props = defineProps({ forecast: { type: Object, required: true }, major: { type: Boolean, default: false }, today: { type: Number, required: true } });
const 追上提示 = computed(() => 取得版本追上提示(props.forecast.catch_up, props.today));
const 下版提示 = computed(() => props.forecast.next ? 取得版本日期提示(props.forecast.next.day, props.today,
  props.forecast.next.planned ? 'planned' : props.forecast.next.announced ? 'announced' : 'estimated', true) : null);
function 節奏結果(結果) {
  if (!結果) return `${props.forecast.horizon_years} 年內未交會`;
  return 僅顯示版本同步(props.forecast.rows?.find((列) => 列.patch === 結果.patch))
    ? `於 ${結果.patch} 追上` : `約 ${日期(結果.date)} 追上`;
}
</script>

<template>
  <div class="版本推測摘要" aria-live="polite">
    <template v-if="forecast.rows">
      <p v-if="forecast.catch_up" class="版本推測結論"><span class="版本推測標籤">推測</span><span>{{ forecast.catch_up.already ? '核對時已追上' : (追上提示?.overdue ? '原推測約 ' : '約 ') + 日期(forecast.catch_up.date) + ' 追上' }}{{ major ? '主版進度' : '含小版本進度' }}</span><strong>{{ forecast.catch_up.patch }}</strong></p>
      <p v-else class="版本推測結論">依目前節奏，在 {{ forecast.horizon_years }} 年推算範圍內尚未交會。</p>
      <p v-if="forecast.catch_up"><span v-if="追上提示" :class="{ '版本推測過期': 追上提示.overdue }">{{ 追上提示.text }}・</span>開服至追上約 {{ forecast.elapsed_to_catch_up }} 天。{{ major ? '主版相同時即視為追上，小版本可能仍有差距。' : '繁中服抵達當時國際服最新的小版本時，才視為追上。' }}</p>
      <p v-if="forecast.continuation_major">延伸至下一主版 <strong>{{ forecast.continuation_major.patch }}</strong> 及所屬小版本（至 {{ forecast.continuation_major.end_patch }}）：該主版國際服約 <strong>{{ 日期(forecast.continuation_major.international_date) }}</strong>、繁中服約 <strong>{{ 日期(forecast.continuation_major.tc_date) }}</strong>。繁中服 {{ forecast.continuation_major.previous_major }} 主版總時長約 {{ forecast.continuation_major.tc_cycle_days }} 天。</p>
      <p v-if="forecast.synchronization_start"><strong>{{ forecast.synchronization_start.patch }}：可能與國際服同步</strong></p>
      <p v-if="forecast.next">下一個{{ major ? '主版本' : '更新節點' }}・繁中服 <strong>{{ forecast.next.patch }}</strong> {{ forecast.next.planned ? '預定' : forecast.next.announced ? '已公告' : '推測約' }} {{ 日期(forecast.next.date) }}<span v-if="forecast.next.planned">・{{ forecast.next.attribution }}</span><span v-if="下版提示" :class="{ '版本推測過期': 下版提示.overdue }">・{{ 下版提示.text }}</span></p>
      <p v-if="forecast.skipped_patches?.length">跳版假設：繁中服略過 {{ forecast.skipped_patches.join('、') }}，待官方確認。</p>
      <p v-if="forecast.tc_cycle_source === 'scenario'">繁中服主版以約 {{ forecast.tc_cycle_days }} 天為目標，推測更新固定{{ 星期(forecast.tc_update_weekday) }}，一般週期為 {{ forecast.tc_typical_cycle_days }} 天；已公告與活動預告日期優先。</p>
      <details>
        <summary>推測依據與不同節奏的結果</summary>
        <p>繁中服歷史主版週期中位數 {{ forecast.tc_historical_cycle_days }} 天，國際服一般主版約 {{ forecast.international_cycle_days }} 天。{{ forecast.tc_cycle_source === 'scenario' ? '本次繁中推測改採上方指定的目標週期，歷史數值僅供參考。' : '本次採兩服歷史中位數推算。' }}國際服也持續更新，直到兩服進度首次交會。</p>
        <ul><li v-for="sample in forecast.tc_samples" :key="'tc' + sample.to_patch">繁中服 {{ sample.from_patch }} → {{ sample.to_patch }}：{{ sample.days }} 天。</li><li v-for="sample in forecast.international_samples" :key="'intl' + sample.to_patch">國際服 {{ sample.from_patch }} → {{ sample.to_patch }}：{{ sample.days }} 天。</li></ul>
        <p>已知日期與活動預告優先作為排程依據；沒有固定間隔的下一個小版採近期繁中／國際更新間隔比例，其餘小版依國際服在主版週期中的位置分配日期。已確認省略及本次假設略過的版本，不配置繁中獨立更新日期。</p>
        <p v-if="forecast.shared_minor_intervals">兩服從 {{ forecast.shared_minor_intervals.from_expansion }}.0 起採固定小版間隔：<span v-for="(step, i) in forecast.shared_minor_intervals.steps" :key="step.to">{{ i ? '；' : '' }}x.{{ step.from }} → x.{{ step.to }} 為 {{ step.days }} 天</span>。這些間隔優先於歷史中位數與主版比例；其餘版本分配剩餘時間，主版總週期仍依各服設定。</p>
        <template v-if="forecast.international_cadence">
          <p>國際服 .01／.05 依歷代上市節奏，分別排在資料片正式上市後第 2／4 週；未指定固定間隔的小版使用近三個資料片同編號的歷史間隔中位數，取整週後對齊星期二，不隨主版總時長縮放。實際日期與版本編號仍以公告為準。</p>
          <p v-if="forecast.international_cadence.expansion_cycle_days">.5 至下一個資料片另估約 {{ forecast.international_cadence.expansion_cycle_days }} 天，依據：<span v-for="(sample, i) in forecast.international_cadence.expansion_samples" :key="sample.from_patch">{{ i ? '、' : '' }}{{ sample.from_patch }} → {{ sample.to_patch }} 為 {{ sample.days }} 天</span>。</p>
          <p v-else>目前缺少已完成的資料片間隔樣本，.5 至下一資料片暫沿用一般主版週期。</p>
          <details>
            <summary>國際服小版本間隔與樣本</summary>
            <p>以下為歷史樣本的中位數，天數從所屬主版起算，例如 x.25 從 x.2 起算；本次另有指定固定間隔時，以固定間隔為準。只有一筆樣本者只是暫用落點；不同內容安排可能改變時程。</p>
            <ul><li v-for="rule in forecast.international_cadence.minor_offsets" :key="rule.suffix"><strong>x.{{ rule.suffix }}</strong>：約 {{ rule.days }} 天；{{ rule.samples.map(sample => `${sample.patch}：${sample.days} 天`).join('、') }}。</li></ul>
            <p v-if="forecast.international_cadence.source_url">歷史日期參考：<a :href="forecast.international_cadence.source_url" target="_blank" rel="noopener noreferrer">灰機 Wiki 版本時間表 ↗</a>（以正式上市日計算）。</p>
          </details>
        </template>
        <p>僅公告月份的版本，取該月中間附近的星期二作圖表情境錨點，並非正式上線日。未公告的後續版本暫沿用 .0～.5 的順序與已收錄小版結構，不把歷代曾出現的所有修正版號都加入未來排程。</p>
        <p>較快節奏：{{ 節奏結果(forecast.fast_catch_up) }}；較慢節奏：{{ 節奏結果(forecast.slow_catch_up) }}。{{ forecast.tc_cycle_source === 'scenario' ? `繁中目標週期分別採 ${forecast.fast_tc_cycle_days}／${forecast.slow_tc_cycle_days} 天，再對齊${星期(forecast.tc_update_weekday)}` : '分別採歷史最短／最長繁中週期' }}，搭配公告月份兩端與小版更新比例上下界，屬敏感度情境，並非信賴區間。</p>
      </details>
      <p class="版本推測聲明">依更新節奏與排程假設推測，非官方公告；後續版本與合併排程尚未確定。</p>
    </template>
    <template v-else><p v-if="forecast.next">繁中服 {{ forecast.next.patch }} {{ forecast.next.planned ? '預定' : '已公告於' }} {{ 日期(forecast.next.date) }} 更新。{{ forecast.next.attribution }}<span v-if="下版提示" :class="{ '版本推測過期': 下版提示.overdue }">・{{ 下版提示.text }}</span></p><p>目前完整主版週期的紀錄不足，暫時無法推算追上日期。</p></template>
  </div>
</template>
