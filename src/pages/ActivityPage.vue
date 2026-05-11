<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "ActivityPage",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="近期動態區" aria-live="polite">
    <div v-if="!使用者索引 && !使用者錯誤訊息" class="狀態列">讀取近期動態中</div>
    <div v-else-if="使用者錯誤訊息" class="狀態列 錯誤">{{ 使用者錯誤訊息 }}</div>

    <template v-else>
      <section class="統計概要" aria-label="近期動態概要">
        <div v-for="項目 in 近期動態概要" :key="項目.標籤" class="概要項">
          <span>{{ 項目.標籤 }}</span>
          <strong>{{ 項目.數值 }}</strong>
        </div>
      </section>

      <section class="統計面板 統計面板寬" aria-label="最近有紀錄的角色">
        <header class="統計面板標題">
          <h2>最近有紀錄的角色</h2>
          <span>依公開紀錄時間排序</span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格 近期動態表格">
            <thead>
              <tr>
                <th scope="col">角色</th>
                <th scope="col">伺服器</th>
                <th scope="col" class="數字">副本數</th>
                <th scope="col" class="數字">公開成績</th>
                <th scope="col" class="數字">最佳 rDPS</th>
                <th scope="col">最後紀錄</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="使用者 in 近期動態角色列表" :key="使用者.character_name">
                <td>
                  <button class="文字連結" type="button" @click="載入使用者成績(使用者.character_name, 使用者.servers?.[0] || '')">
                    {{ 使用者.character_name }}
                  </button>
                </td>
                <td>{{ (使用者.servers || []).join(" / ") || "-" }}</td>
                <td class="數字">{{ 格式化整數(使用者.encounter_count) }}</td>
                <td class="數字">{{ 格式化整數(使用者.public_entry_count) }}</td>
                <td class="數字">{{ 格式化傷害數值(使用者.best_rdps) }}</td>
                <td>{{ 格式化紀錄時間(使用者.last_recorded_at_iso) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
