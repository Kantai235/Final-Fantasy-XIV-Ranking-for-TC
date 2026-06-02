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

      <section v-if="近期動態日誌圖表資料" class="統計面板 統計面板寬 近期日誌趨勢面板" aria-label="Logs 趨勢">
        <header class="統計面板標題">
          <h2>Logs 趨勢</h2>
          <span>{{ 近期動態日誌範圍文字 }}</span>
        </header>
        <div class="近期日誌面板內容">
          <div class="近期日誌工具列">
            <div class="欄位 副本選單欄位" @focusout="處理近期動態日誌副本選單失焦">
              <span>副本</span>
              <div class="副本選單">
                <button
                  class="副本選單按鈕"
                  type="button"
                  :aria-expanded="近期動態日誌副本選單開啟"
                  aria-haspopup="true"
                  @click="切換近期動態日誌副本選單"
                >
                  <span class="副本選單目前值">{{ 近期動態日誌副本選單文字 }}</span>
                  <span class="選單箭頭">▾</span>
                </button>

                <div v-if="近期動態日誌副本選單開啟" class="副本選單面板" role="menu" aria-label="近期日誌副本">
                  <section v-for="分組 in 近期動態日誌副本分組" :key="分組.分類" class="副本分類群">
                    <p class="副本分類標題">{{ 分組.分類 }}</p>
                    <button
                      v-for="副本 in 分組.副本列表"
                      :key="副本.value"
                      class="副本選單項"
                      type="button"
                      :class="{ 已選取: 近期動態日誌有效副本鍵值 === 副本.value }"
                      @click="選擇近期動態日誌副本(副本.value)"
                    >
                      {{ 副本.label }}
                    </button>
                  </section>
                </div>
              </div>
            </div>
            <div class="欄位 近期日誌時間範圍欄位">
              <label class="近期日誌範圍模式">
                <span>時間範圍</span>
                <select v-model="近期動態日誌時間範圍" aria-label="時間範圍">
                  <option v-for="選項 in 近期動態日誌時間範圍選項" :key="選項.value" :value="選項.value">
                    {{ 選項.label }}
                  </option>
                </select>
              </label>
              <div v-if="顯示近期動態日誌自訂日期" class="近期日誌日期區間" aria-label="自訂日期區間">
                <label>
                  <span>起</span>
                  <input v-model="近期動態日誌自訂開始日期" type="date" aria-label="自訂開始日期" />
                </label>
                <span class="近期日誌日期區間分隔">至</span>
                <label>
                  <span>迄</span>
                  <input v-model="近期動態日誌自訂結束日期" type="date" aria-label="自訂結束日期" />
                </label>
              </div>
            </div>
            <label class="欄位">
              <span>數量口徑</span>
              <select v-model="近期動態日誌指標" aria-label="數量口徑">
                <option v-for="選項 in 近期動態日誌指標選項" :key="選項.key" :value="選項.key">
                  {{ 選項.label }}
                </option>
              </select>
            </label>
          </div>
          <div class="近期日誌摘要列" aria-label="Logs 趨勢摘要">
            <span v-for="項目 in 近期動態日誌摘要" :key="項目.標籤">
              <small>{{ 項目.標籤 }}</small>
              <strong>{{ 項目.數值 }}</strong>
            </span>
          </div>
          <div v-if="近期動態日誌圖表資料.category_legend?.length" class="近期日誌分類圖例" aria-label="Logs 分類占比">
            <span
              v-for="分類 in 近期動態日誌圖表資料.category_legend"
              :key="分類.category"
              class="近期日誌分類圖例項"
              :class="分類.color_class"
            >
              <i class="近期日誌分類圖例色塊" aria-hidden="true"></i>
              <strong>{{ 分類.label }}</strong>
              <small>{{ 分類.percentage_text }}・{{ 分類.value_text }}</small>
            </span>
          </div>
          <div
            class="近期日誌圖表"
            role="group"
            :aria-label="`${近期動態日誌圖表資料.encounter_name} ${近期動態日誌指標標籤} 趨勢，${近期動態日誌範圍文字}`"
            @keydown.esc="清除近期動態日誌提示"
          >
            <div class="近期日誌繪圖區">
              <svg class="近期日誌曲線圖" viewBox="0 0 100 52" preserveAspectRatio="none" aria-hidden="true">
                <line class="近期日誌格線" x1="0" y1="10" x2="100" y2="10"></line>
                <line class="近期日誌格線" x1="0" y1="26" x2="100" y2="26"></line>
                <line class="近期日誌格線" x1="0" y1="44" x2="100" y2="44"></line>
                <path
                  v-for="分類 in 近期動態日誌圖表資料.category_layers"
                  :key="分類.category"
                  class="近期日誌分類面積"
                  :class="分類.color_class"
                  :d="分類.path"
                ></path>
                <path v-if="近期動態日誌圖表資料.area_path && !近期動態日誌圖表資料.category_layers?.length" class="近期日誌面積" :d="近期動態日誌圖表資料.area_path"></path>
                <path v-if="近期動態日誌圖表資料.line_path" class="近期日誌折線" :d="近期動態日誌圖表資料.line_path"></path>
              </svg>
              <span v-if="近期動態日誌圖表資料.annotations?.length" class="近期日誌標註層" role="list" aria-label="Logs 趨勢時間標註">
                <span
                  v-for="標註 in 近期動態日誌圖表資料.annotations"
                  :key="標註.key"
                  class="近期日誌時間標註"
                  :class="標註.class_names"
                  role="listitem"
                  :style="{ left: `${標註.x}%` }"
                >
                  <span class="近期日誌時間標註線"></span>
                  <span class="近期日誌時間標註內容">
                    <i class="近期日誌時間標註角標遮罩" aria-hidden="true"></i>
                    <strong>{{ 標註.title }}</strong>
                    <span>{{ 標註.detail }}</span>
                  </span>
                </span>
              </span>
              <div class="近期日誌點層">
                <button
                  v-for="點 in 近期動態日誌圖表資料.points"
                  :key="點.id"
                  class="近期日誌點"
                  :class="{ 近期日誌點作用中: 近期動態日誌提示資料?.id === 點.id }"
                  type="button"
                  :style="趨勢點樣式(點)"
                  :title="`${點.label}・${近期動態日誌指標標籤} ${格式化整數(點.count)}`"
                  :aria-label="`${點.label}，${近期動態日誌指標標籤} ${格式化整數(點.count)}`"
                  :aria-pressed="近期動態日誌提示鎖定 && 近期動態日誌提示資料?.id === 點.id"
                  @mouseenter="顯示近期動態日誌提示(點)"
                  @focus="顯示近期動態日誌提示(點)"
                  @mouseleave="隱藏近期動態日誌提示"
                  @blur="隱藏近期動態日誌提示"
                  @click.stop="固定近期動態日誌提示(點)"
                ></button>
                <div
                  v-if="近期動態日誌提示資料"
                  class="近期日誌提示"
                  :class="{ 近期日誌提示固定: 近期動態日誌提示鎖定 }"
                  :style="近期動態日誌提示資料.style"
                  role="status"
                >
                  <small>{{ 近期動態日誌提示資料.label }}</small>
                  <strong>{{ 近期動態日誌提示資料.metric_label }}：{{ 近期動態日誌提示資料.value_text }}</strong>
                </div>
              </div>
              <div class="近期日誌刻度" aria-hidden="true">
                <span>{{ 格式化整數(近期動態日誌圖表資料.max_count) }}</span>
                <span>0</span>
              </div>
            </div>
            <div class="近期日誌月份軸" aria-hidden="true">
              <span
                v-for="月份 in 近期動態日誌圖表資料.month_ticks"
                :key="月份.key"
                class="近期日誌月份刻度"
                :class="{
                  近期日誌月份刻度起點: 月份.align === 'start',
                  近期日誌月份刻度終點: 月份.align === 'end',
                }"
                :style="{ left: `${月份.x}%` }"
              >
                {{ 月份.label }}
              </span>
            </div>
          </div>
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
                  <template v-else>
                    <span :class="同職分位色彩類別(成績.performance)">{{ 格式化目前同職分位(成績.performance) }}</span>
                  </template>
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
