<script>
import JobIcon from "../components/JobIcon.vue";
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "ActivityPage",
  components: {
    JobIcon,
  },
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="近期動態區" aria-live="polite">
    <div v-if="近期動態讀取中" class="狀態列">讀取近期動態中</div>
    <div v-else-if="近期動態錯誤訊息" class="狀態列 錯誤">{{ 近期動態錯誤訊息 }}</div>
    <div v-else-if="!近期動態資料 && !使用者索引" class="狀態列">正在準備近期動態資料</div>

    <template v-else>
      <section class="統計概要" aria-label="近期動態概要">
        <div v-for="項目 in 近期動態概要" :key="項目.標籤" class="概要項">
          <span>{{ 項目.標籤 }}</span>
          <strong>{{ 項目.數值 }}</strong>
        </div>
      </section>

      <section v-if="近期刷新紀錄列表.length > 0" class="統計面板 統計面板寬" aria-label="近期刷新個人最佳">
        <header class="統計面板標題">
          <h2>刷新個人最佳</h2>
          <span>依 rDPS 提升幅度排序</span>
        </header>
        <p v-if="近期刷新版本說明文字" class="版本紀錄說明">{{ 近期刷新版本說明文字 }}</p>
        <div class="統計表格外框">
          <table class="統計表格 近期動態表格 近期刷新表格">
            <thead>
              <tr>
                <th scope="col">玩家</th>
                <th scope="col">副本</th>
                <th scope="col">職業</th>
                <th scope="col" class="數字">rDPS 提升</th>
                <th scope="col" class="數字">同職分位</th>
                <th v-show="顯示Gcd覆蓋率" scope="col" class="數字 gcd參考文字">GCD</th>
                <th scope="col">紀錄時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="成績 in 近期刷新紀錄列表" :key="成績.id" :class="{ 過版紀錄列: 成績.is_obsolete_record }">
                <td>
                  <button class="文字連結" type="button" @click="載入使用者成績(成績.character_name, 成績.server)">
                    {{ 成績.character_name }}
                  </button>
                  <small class="表格補充文字">{{ 成績.server }}</small>
                </td>
                <td>
                  <span class="比較副本">
                    <small>{{ 成績.encounter_category || "副本" }}</small>
                    <strong>{{ 成績.encounter_name }}</strong>
                  </span>
                </td>
                <td>
                  <span v-if="成績.job" class="職業標籤 近期動態職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
                    <JobIcon
                      class="職業圖示 職業標籤圖示"
                      :code="成績.job"
                    />
                    <span>{{ 顯示職業名稱(成績.job) }}</span>
                  </span>
                  <span v-else>-</span>
                </td>
                <td class="數字">{{ 格式化帶號整數(成績.rdps_gain) }}</td>
                <td class="數字">
                  <span v-if="成績.is_obsolete_record" class="版本紀錄標籤">過版紀錄</span>
                  <template v-else>{{ 格式化前段百分位(成績.performance?.rank, 成績.performance?.sample_count) }}</template>
                </td>
                <td v-show="顯示Gcd覆蓋率" class="數字 gcd參考文字">{{ 格式化Gcd覆蓋率(成績.gcd_coverage) }}</td>
                <td>{{ 格式化紀錄時間(成績.recorded_at_iso) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="統計面板 統計面板寬" aria-label="最近公開成績">
        <header class="統計面板標題">
          <h2>最近公開成績</h2>
          <span>依公開紀錄時間排序</span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格 近期動態表格 近期公開表格">
            <thead>
              <tr>
                <th scope="col">玩家</th>
                <th scope="col">伺服器</th>
                <th scope="col">副本</th>
                <th scope="col">職業</th>
                <th scope="col" class="數字">rDPS</th>
                <th v-show="顯示Gcd覆蓋率" scope="col" class="數字 gcd參考文字">GCD</th>
                <th scope="col">紀錄時間</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="成績 in 近期動態最新成績列表" :key="成績.id || `${成績.character_name}@${成績.server}:${成績.recorded_at_iso}`">
                <td>
                  <button class="文字連結" type="button" @click="載入使用者成績(成績.character_name, 成績.server)">
                    {{ 成績.character_name }}
                  </button>
                </td>
                <td>{{ 成績.server || "-" }}</td>
                <td>{{ 成績.encounter_name || "-" }}</td>
                <td>
                  <span v-if="成績.job" class="職業標籤 近期動態職業標籤" :class="職業色彩類別(職業代碼色彩(成績.job))">
                    <JobIcon
                      class="職業圖示 職業標籤圖示"
                      :code="成績.job"
                    />
                    <span>{{ 顯示職業名稱(成績.job) }}</span>
                  </span>
                  <span v-else>-</span>
                </td>
                <td class="數字">{{ 格式化傷害數值(成績.rdps) }}</td>
                <td v-show="顯示Gcd覆蓋率" class="數字 gcd參考文字">{{ 格式化Gcd覆蓋率(成績.gcd_coverage) }}</td>
                <td>{{ 格式化紀錄時間(成績.recorded_at_iso || 成績.last_recorded_at_iso) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="近期洞察版面" aria-label="近期活躍分布">
        <article v-if="近期伺服器活躍列表.length > 0" class="統計面板">
          <header class="統計面板標題">
            <h2>伺服器活躍</h2>
            <span>近 {{ 近期動態資料?.window_days || 7 }} 天</span>
          </header>
          <div class="分布列表">
            <div v-for="伺服器 in 近期伺服器活躍列表" :key="伺服器.server" class="分布項">
              <div class="分布列">
                <strong>{{ 伺服器.server }}</strong>
                <span>{{ 格式化整數(伺服器.entry_count) }} 筆・{{ 格式化整數(伺服器.character_count) }} 人</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :style="比例條樣式((伺服器.entry_count / (近期伺服器活躍列表[0]?.entry_count || 1)) * 100)"></span>
              </div>
              <small class="職業分析補充">刷新最佳 {{ 格式化整數(伺服器.personal_best_count) }} 筆</small>
            </div>
          </div>
        </article>

        <article v-if="近期副本活躍列表.length > 0" class="統計面板">
          <header class="統計面板標題">
            <h2>副本活躍</h2>
            <span>公開紀錄量</span>
          </header>
          <div class="分布列表">
            <div v-for="副本 in 近期副本活躍列表" :key="副本.encounter_key" class="分布項">
              <div class="分布列">
                <strong>{{ 副本.encounter_name }}</strong>
                <span>{{ 格式化整數(副本.entry_count) }} 筆・{{ 格式化整數(副本.character_count) }} 人</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :style="比例條樣式((副本.entry_count / (近期副本活躍列表[0]?.entry_count || 1)) * 100)"></span>
              </div>
              <small class="職業分析補充">刷新最佳 {{ 格式化整數(副本.personal_best_count) }} 筆</small>
            </div>
          </div>
        </article>
      </section>

      <section v-if="近期新角色列表.length > 0" class="統計面板 統計面板寬" aria-label="新收錄玩家">
        <header class="統計面板標題">
          <h2>新收錄玩家</h2>
          <span>首次出現在公開資料的玩家</span>
        </header>
        <div class="近期新角色列表">
          <button
            v-for="角色 in 近期新角色列表"
            :key="`${角色.character_name}@${角色.server}`"
            class="近期新角色項"
            type="button"
            @click="載入使用者成績(角色.character_name, 角色.server)"
          >
            <strong>{{ 角色.character_name }}</strong>
            <span>
              {{ 角色.server }}・{{ 格式化整數(角色.encounter_count) }} 副本・rDPS {{ 格式化傷害數值(角色.best_entry?.rdps) }}
              <span v-if="顯示Gcd覆蓋率" class="gcd參考文字">・GCD {{ 格式化Gcd覆蓋率(角色.best_entry?.gcd_coverage) }}</span>
            </span>
          </button>
        </div>
      </section>
    </template>
  </section>
</template>
