<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "GlobalStatsPage",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="統計工具列" aria-label="全服統計篩選">
    <div class="欄位 副本選單欄位" @focusout="處理統計副本選單失焦">
      <span>統計範圍</span>
      <div class="副本選單">
        <button
          class="副本選單按鈕"
          type="button"
          :aria-expanded="統計副本選單開啟"
          aria-haspopup="true"
          @click="切換統計副本選單"
        >
          <span class="副本選單目前值">{{ 統計副本選單文字 }}</span>
          <span class="選單箭頭">▾</span>
        </button>

        <div v-if="統計副本選單開啟" class="副本選單面板" role="menu" aria-label="統計範圍">
          <section class="副本分類群">
            <p class="副本分類標題">全部</p>
            <button
              class="副本選單項"
              type="button"
              :class="{ 已選取: 統計副本鍵值 === 'all' }"
              @click="選擇統計副本(null)"
            >
              全部副本
            </button>
          </section>
          <section v-for="分組 in 副本分組" :key="分組.分類" class="副本分類群">
            <p class="副本分類標題">{{ 分組.分類 }}</p>
            <button
              v-for="副本 in 分組.副本列表"
              :key="副本.key"
              class="副本選單項"
              type="button"
              :class="{ 已選取: 統計副本鍵值 === 副本.key }"
              @click="選擇統計副本(副本)"
            >
              {{ 副本.name }}
            </button>
          </section>
        </div>
      </div>
    </div>
    <label class="欄位">
      <span>伺服器</span>
      <select v-model="統計伺服器篩選">
        <option value="">全部伺服器</option>
        <option v-for="伺服器 in 統計伺服器選項" :key="伺服器" :value="伺服器">
          {{ 伺服器 }}
        </option>
      </select>
    </label>
    <div class="欄位 職業選單欄位" @focusout="處理統計職業選單失焦">
      <span>職業範圍</span>
      <div class="職業選單">
        <button
          class="職業選單按鈕"
          type="button"
          :aria-expanded="統計職業選單開啟"
          aria-haspopup="true"
          @click="切換統計職業選單"
        >
          <span class="職業選單目前值">
            <img
              v-if="統計職業選單Icon路徑"
              class="職業圖示"
              :src="統計職業選單Icon路徑"
              alt=""
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
            <span>{{ 統計職業選單文字 }}</span>
          </span>
          <span class="選單箭頭">▾</span>
        </button>

        <div v-if="統計職業選單開啟" class="職業選單面板">
          <div class="職業選單分類欄" role="menu" aria-label="統計職業類型">
            <button
              class="職業選單項"
              type="button"
              :class="{ 已選取: 統計職業範圍 === 'all' }"
              @click="清除統計職業範圍"
            >
              全部職業
            </button>
            <button
              v-for="類型 in 統計職業類型選項"
              :key="類型.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(類型.色彩), { 已選取: 統計職業範圍類型代碼 === 類型.代碼 }]"
              @click="選擇統計職業類型(類型.代碼)"
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

          <div class="職業選單職業欄" role="menu" aria-label="統計職業">
            <template v-if="統計職業範圍類型代碼 && 統計職業選項.length > 0">
              <button
                v-for="職業 in 統計職業選項"
                :key="職業.代碼"
                class="職業選單項"
                type="button"
                :class="[職業色彩類別(職業.色彩), { 已選取: 統計職業範圍職業代碼 === 職業.代碼 }]"
                @click="選擇統計職業(職業.代碼)"
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
    <label class="欄位">
      <span>伺服器佔比拆分</span>
      <select v-model="伺服器拆分模式">
        <option value="none">不拆分</option>
        <option value="role">依職業類型</option>
        <option value="job">依各職業</option>
      </select>
    </label>
  </section>

  <section class="全服統計區" aria-live="polite">
    <div v-if="全服統計讀取中" class="狀態列">讀取全服統計中</div>
    <div v-else-if="全服統計錯誤訊息" class="狀態列 錯誤">{{ 全服統計錯誤訊息 }}</div>
    <div v-else-if="!全服統計資料" class="狀態列">正在準備全服統計資料</div>

    <template v-else>
      <section class="統計概要" aria-label="全服統計概要">
        <div v-for="項目 in 全服概要項目" :key="項目.標籤" class="概要項">
          <span class="說明標籤">
            <span>{{ 項目.標籤 }}</span>
            <span v-if="統計說明文字(項目.標籤)" class="說明提示">
              <button class="說明提示按鈕" type="button" :aria-label="`${項目.標籤}說明`">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字(項目.標籤) }}</span>
            </span>
          </span>
          <strong>{{ 項目.數值 }}</strong>
        </div>
      </section>

      <section
        v-if="顯示零式進度漏斗 && 零式進度漏斗.length > 0"
        class="統計面板 統計面板寬 零式漏斗面板"
        aria-label="零式進度漏斗"
      >
        <header class="統計面板標題">
          <h2 class="說明標籤">
            <span>零式進度漏斗</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="零式進度漏斗說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("零式進度漏斗") }}</span>
            </span>
          </h2>
          <span>{{ 零式漏斗條件文字 }}</span>
        </header>
        <div class="零式漏斗列表">
          <article v-for="項目 in 零式進度漏斗" :key="項目.encounter_key" class="零式漏斗項">
            <div class="漏斗副本列">
              <span class="漏斗層級">{{ 項目.層級文字 }}</span>
              <strong>{{ 項目.encounter_name }}</strong>
            </div>
            <div class="漏斗數值列">
              <strong>{{ 格式化整數(項目.顯示數量) }} {{ 零式漏斗單位 }}</strong>
              <span>相對首層 {{ 格式化百分比(項目.相對首層比例) }}</span>
            </div>
            <div class="漏斗條" aria-hidden="true">
              <span :style="比例條樣式(項目.相對首層比例)"></span>
            </div>
            <div class="漏斗補充列">
              <span v-if="項目.索引 === 0">基準層</span>
              <span v-else>較上一層 {{ 格式化帶號整數(項目.較上一層差異) }}・{{ 格式化百分比(項目.上一層比例) }}</span>
            </div>
          </article>
        </div>
      </section>

      <section v-if="職業傷害比較列.length > 0" class="統計面板 統計面板寬 職業傷害比較面板" aria-label="全職業輸出比較">
        <header class="統計面板標題 職業傷害比較標題">
          <h2 class="說明標籤">
            <span>全職業輸出比較</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="全職業輸出比較說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("全職業輸出比較") }}</span>
            </span>
          </h2>
          <div class="傷害指標切換" role="tablist" aria-label="傷害指標">
            <button
              v-for="選項 in 傷害比較指標選項"
              :key="選項.value"
              type="button"
              :class="{ 作用中: 統計傷害指標 === 選項.value }"
              :aria-selected="統計傷害指標 === 選項.value"
              role="tab"
              @click="統計傷害指標 = 選項.value"
            >
              {{ 選項.label }}
            </button>
          </div>
        </header>
        <div class="職業傷害比較說明列">
          <span>{{ 職業傷害比較條件文字 }}</span>
          <strong>Rank by {{ 傷害比較指標標籤 }}</strong>
        </div>
        <div class="職業傷害比較圖">
          <div class="職業傷害比較刻度列" aria-hidden="true">
            <span></span>
            <div class="職業傷害比較刻度軌">
              <span v-for="刻度 in 職業傷害比較刻度" :key="刻度.數值" class="職業傷害比較刻度" :style="{ left: 刻度.位置 }">
                {{ 格式化傷害數值(刻度.數值) }}
              </span>
            </div>
            <span></span>
          </div>
          <div class="職業傷害比較列表">
            <article
              v-for="列 in 職業傷害比較列"
              :key="列.job"
              class="職業傷害比較列"
              :class="{ 顯示提示: 職業傷害提示作用職業 === 列.job }"
              :style="列.樣式"
              tabindex="0"
              :aria-label="職業傷害提示文字(列)"
              :title="職業傷害提示文字(列)"
              @mouseenter="顯示職業傷害提示(列.job)"
              @mouseleave="隱藏職業傷害提示(列.job)"
              @focus="顯示職業傷害提示(列.job)"
              @blur="隱藏職業傷害提示(列.job)"
              @click="切換職業傷害提示(列.job)"
              @keydown.enter.prevent="切換職業傷害提示(列.job)"
              @keydown.space.prevent="切換職業傷害提示(列.job)"
            >
              <div class="職業傷害比較職業">
                <img
                  v-if="職業Icon路徑(列.job)"
                  class="職業圖示"
                  :src="職業Icon路徑(列.job)"
                  alt=""
                  loading="lazy"
                  @error="隱藏載入失敗圖片"
                />
                <span>{{ 顯示職業名稱(列.job) }}</span>
              </div>
              <div class="職業傷害比較軌道" aria-hidden="true">
                <span class="職業傷害比較鬚線"></span>
                <span class="職業傷害比較盒"></span>
                <span class="職業傷害比較中位線"></span>
                <span class="職業傷害比較平均點"></span>
                <span class="職業傷害比較最高點"></span>
                <span class="職業傷害比較提示" aria-hidden="true">
                  <span>
                    <em>最小</em>
                    <strong>{{ 格式化傷害數值(列.min) }}</strong>
                  </span>
                  <span>
                    <em>中位</em>
                    <strong>{{ 格式化傷害數值(列.median) }}</strong>
                  </span>
                  <span>
                    <em>平均</em>
                    <strong>{{ 格式化傷害數值(列.average) }}</strong>
                  </span>
                  <span>
                    <em>最大</em>
                    <strong>{{ 格式化傷害數值(列.max) }}</strong>
                  </span>
                </span>
              </div>
              <div class="職業傷害比較數值">
                <strong>{{ 格式化傷害數值(列.median) }}</strong>
                <span>{{ 格式化整數(列.count) }} 筆・最高 {{ 格式化傷害數值(列.max) }}</span>
              </div>
            </article>
          </div>
        </div>
      </section>

      <section class="統計版面" aria-label="伺服器與職業佔比">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2 class="說明標籤">
              <span>伺服器佔比</span>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="伺服器佔比說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("伺服器佔比") }}</span>
              </span>
            </h2>
            <span>{{ 統計條件文字 }}</span>
          </header>
          <div class="分布列表">
            <div v-for="項目 in 伺服器佔比列表" :key="項目.server" class="分布項">
              <div class="分布列">
                <strong>{{ 項目.server }}</strong>
                <span>{{ 格式化整數(項目.顯示數量) }} {{ 伺服器佔比單位 }}・{{ 格式化百分比(項目.顯示比例) }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span class="分布條填滿" :style="比例條樣式(項目.顯示比例)"></span>
              </div>
              <div v-if="取得伺服器拆分列表(項目).length > 0" class="分布子列表">
                <span
                  v-for="拆分 in 取得伺服器拆分列表(項目)"
                  :key="拆分.role || 拆分.job"
                  class="分布子項"
                  :class="職業色彩類別(拆分.job ? 職業代碼色彩(拆分.job) : 職業類型色彩(拆分.role))"
                >
                  <img
                    v-if="拆分.job && 職業Icon路徑(拆分.job)"
                    class="職業圖示"
                    :src="職業Icon路徑(拆分.job)"
                    alt=""
                    loading="lazy"
                    @error="隱藏載入失敗圖片"
                  />
                  <span>{{ 拆分.顯示名稱 }}</span>
                  <em>{{ 格式化百分比(拆分.顯示比例) }}</em>
                </span>
              </div>
            </div>
          </div>
        </article>

        <article class="統計面板">
          <header class="統計面板標題">
            <h2 class="說明標籤">
              <span>職業佔比</span>
              <span class="說明提示">
                <button class="說明提示按鈕" type="button" aria-label="職業佔比說明">?</button>
                <span class="說明提示內容" role="tooltip">{{ 統計說明文字("職業佔比") }}</span>
              </span>
            </h2>
            <span>{{ 職業佔比標題文字 }}</span>
          </header>
          <div class="職業佔比分組">
            <article v-for="群組 in 職業佔比分組" :key="群組.role" class="職業佔比群組" :class="職業色彩類別(群組.色彩)">
              <header class="職業佔比群組標題">
                <strong>{{ 群組.role_name }}</strong>
                <span>{{ 格式化整數(群組.clear_count) }} 紀錄・{{ 格式化百分比(群組.percentage) }}</span>
              </header>
              <div class="分布條" aria-hidden="true">
                <span
                  class="分布條填滿"
                  :class="職業色彩類別(群組.色彩)"
                  :style="比例條樣式(群組.percentage)"
                ></span>
              </div>
              <div class="職業佔比職業列表">
                <div v-for="職業 in 群組.jobs" :key="職業.job" class="職業佔比職業">
                  <span class="分布職業">
                    <img
                      v-if="職業Icon路徑(職業.job)"
                      class="職業圖示"
                      :src="職業Icon路徑(職業.job)"
                      alt=""
                      loading="lazy"
                      @error="隱藏載入失敗圖片"
                    />
                    <span>{{ 顯示職業名稱(職業.job) }}</span>
                  </span>
                  <strong>{{ 格式化整數(職業.clear_count) }}</strong>
                  <small>{{ 格式化百分比(職業.percentage) }}</small>
                </div>
              </div>
            </article>
          </div>
        </article>
      </section>

      <section v-if="伺服器生態矩陣.length > 0" class="統計面板 統計面板寬" aria-label="伺服器生態比較">
        <header class="統計面板標題">
          <h2 class="說明標籤">
            <span>伺服器生態比較</span>
            <span class="說明提示">
              <button class="說明提示按鈕" type="button" aria-label="伺服器生態比較說明">?</button>
              <span class="說明提示內容" role="tooltip">{{ 統計說明文字("伺服器生態比較") }}</span>
            </span>
          </h2>
          <span>{{ 統計範圍文字 }}</span>
        </header>
        <div class="生態矩陣外框">
          <table class="生態矩陣">
            <thead>
              <tr>
                <th scope="col">伺服器</th>
                <th v-for="欄位 in 伺服器生態欄位" :key="欄位.role" scope="col">{{ 欄位.label }}</th>
                <th scope="col">主要傾向</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="列 in 伺服器生態矩陣" :key="列.server">
                <th scope="row">{{ 列.server }}</th>
                <td v-for="欄位 in 列.欄位" :key="欄位.role">
                  <span class="熱力格" :class="職業色彩類別(欄位.色彩)" :style="熱力格樣式(欄位.比例)">
                    <strong>{{ 格式化百分比(欄位.比例) }}</strong>
                    <small>{{ 格式化整數(欄位.數量) }}</small>
                  </span>
                </td>
                <td>
                  <span v-if="列.最高欄位" class="職業標籤" :class="職業色彩類別(列.最高欄位.色彩)">
                    {{ 列.最高欄位.label }}
                  </span>
                  <span v-else>-</span>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section v-if="顯示副本通關概覽" class="統計面板 統計面板寬" aria-label="副本通關概覽">
        <header class="統計面板標題">
          <h2>副本通關概覽</h2>
          <span>{{ 統計條件文字 }}</span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格">
            <thead>
              <tr>
                <th scope="col">副本</th>
                <th scope="col">分類</th>
                <th scope="col" class="數字">
                  <span class="表頭說明標籤">
                    <span>{{ 職業範圍類型(統計職業範圍) === "all" ? "通關角色" : "通關紀錄" }}</span>
                    <span class="說明提示">
                      <button
                        class="說明提示按鈕"
                        type="button"
                        :aria-label="`${職業範圍類型(統計職業範圍) === 'all' ? '通關角色' : '通關紀錄'}說明`"
                      >
                        ?
                      </button>
                      <span class="說明提示內容" role="tooltip">
                        {{ 統計說明文字(職業範圍類型(統計職業範圍) === "all" ? "通關角色" : "通關紀錄") }}
                      </span>
                    </span>
                  </span>
                </th>
                <th scope="col" class="數字">
                  <span class="表頭說明標籤">
                    <span>範圍佔比</span>
                    <span class="說明提示">
                      <button class="說明提示按鈕" type="button" aria-label="範圍佔比說明">?</button>
                      <span class="說明提示內容" role="tooltip">{{ 統計說明文字("範圍佔比") }}</span>
                    </span>
                  </span>
                </th>
                <th scope="col">最高伺服器</th>
                <th scope="col">最高職業</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="副本 in 副本通關概覽" :key="副本.encounter_key">
                <td>
                  <button class="文字連結" type="button" @click="統計副本鍵值 = 副本.encounter_key">
                    {{ 副本.encounter_name }}
                  </button>
                </td>
                <td>{{ 副本.encounter_category || "-" }}</td>
                <td class="數字">{{ 格式化整數(副本.顯示數量) }}</td>
                <td class="數字">{{ 格式化百分比(副本.顯示比例) }}</td>
                <td>
                  <span v-if="統計伺服器篩選">{{ 統計伺服器篩選 }}</span>
                  <span v-else-if="副本.最高伺服器">
                    {{ 副本.最高伺服器.server }}・{{ 格式化百分比(副本.最高伺服器.顯示比例) }}
                  </span>
                  <span v-else>-</span>
                </td>
                <td>
                  <span v-if="副本.最高職業" class="職業標籤" :class="職業色彩類別(職業代碼色彩(副本.最高職業.job))">
                    <img
                      v-if="職業Icon路徑(副本.最高職業.job)"
                      class="職業圖示 職業標籤圖示"
                      :src="職業Icon路徑(副本.最高職業.job)"
                      alt=""
                      loading="lazy"
                      @error="隱藏載入失敗圖片"
                    />
                    <span>{{ 顯示職業名稱(副本.最高職業.job) }}</span>
                  </span>
                  <span v-else>-</span>
                </td>
              </tr>
              <tr v-if="副本通關概覽.length === 0">
                <td colspan="6" class="統計空列">目前沒有符合條件的副本統計</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="統計面板 統計面板寬" aria-label="資料收集狀態">
        <header class="統計面板標題">
          <h2>資料收集狀態</h2>
          <span>{{ 格式化整數(資料狀態列表.filter((副本) => 副本.有資料).length) }} / {{ 格式化整數(資料狀態列表.length) }} 副本已有資料</span>
        </header>
        <div class="資料狀態分組列表">
          <section v-for="分組 in 資料狀態分組" :key="分組.分類" class="資料狀態分組">
            <header class="資料狀態分組標題">
              <span>
                <strong>{{ 分組.分類 }}</strong>
                <small>{{ 格式化整數(分組.已收錄數) }} / {{ 格式化整數(分組.總數) }} 已收錄</small>
              </span>
              <em>{{ 格式化百分比(分組.收錄比例) }}</em>
            </header>
            <div class="分布條" aria-hidden="true">
              <span class="分布條填滿" :style="比例條樣式(分組.收錄比例)"></span>
            </div>
            <div class="資料狀態列表">
              <article
                v-for="副本 in 分組.副本列表"
                :key="副本.encounter_key"
                class="資料狀態項"
                :class="{ 已收錄: 副本.有資料 }"
              >
                <span>
                  <small>{{ 副本.encounter_category || "副本" }}</small>
                  <strong>{{ 副本.encounter_name }}</strong>
                </span>
                <em>{{ 副本.狀態文字 }}</em>
                <small>{{ 副本.有資料 ? `${格式化整數(副本.character_count)} 角色` : "尚無公開成績" }}</small>
              </article>
            </div>
          </section>
        </div>
      </section>
    </template>
  </section>
</template>
