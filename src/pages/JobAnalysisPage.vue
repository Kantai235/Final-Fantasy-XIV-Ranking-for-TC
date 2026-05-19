<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "JobAnalysisPage",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="職業分析工具列" aria-label="職業分析篩選">
    <div class="欄位 職業選單欄位" @focusout="處理職業分析選單失焦">
      <span>分析範圍</span>
      <div class="職業選單">
        <button
          class="職業選單按鈕"
          type="button"
          :aria-expanded="職業分析選單開啟"
          aria-haspopup="true"
          @click="切換職業分析選單"
        >
          <span class="職業選單目前值">
            <img
              v-if="職業分析選單Icon路徑"
              class="職業圖示"
              :src="職業分析選單Icon路徑"
              alt=""
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
            <span>{{ 職業分析選單文字 }}</span>
          </span>
          <span class="選單箭頭">▾</span>
        </button>

        <div v-if="職業分析選單開啟" class="職業選單面板 職業分析選單面板">
          <div class="職業選單分類欄" role="menu" aria-label="職業類型">
            <button
              v-for="分組 in 職業分析職業分組"
              :key="分組.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(分組.色彩), { 已展開: 職業分析展示類型代碼 === 分組.代碼, 已選取: 職業分析目前範圍代碼 === 分組.代碼 }]"
              @click="選擇職業分析類型(分組.代碼)"
            >
              <img
                v-if="職業類型Icon路徑(分組.代碼)"
                class="職業圖示"
                :src="職業類型Icon路徑(分組.代碼)"
                alt=""
                loading="lazy"
                @error="隱藏載入失敗圖片"
              />
              <span>{{ 分組.名稱 }}</span>
            </button>
          </div>

          <div class="職業選單職業欄" role="menu" aria-label="職業">
            <button
              v-for="職業 in 職業分析展示職業"
              :key="職業.代碼"
              class="職業選單項"
              type="button"
              :class="[職業色彩類別(職業.色彩), { 已選取: 職業分析目前範圍代碼 === 職業.代碼 }]"
              @click="選擇職業分析職業(職業.代碼)"
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
          </div>
        </div>
      </div>
    </div>
  </section>

  <section class="職業分析區" aria-live="polite">
    <div v-if="全服統計讀取中" class="狀態列">讀取職業分析資料中</div>
    <div v-else-if="全服統計錯誤訊息" class="狀態列 錯誤">{{ 全服統計錯誤訊息 }}</div>
    <div v-else-if="!全服統計資料" class="狀態列">正在準備職業分析資料</div>
    <div v-else-if="!職業分析目前範圍" class="狀態列">目前沒有可分析的職業資料</div>

    <template v-else>
      <section v-if="職業分析分位亮點列.length > 0" class="職業分位亮點區" aria-label="職業分位亮點">
        <header class="職業分位亮點標題">
          <span>
            <small>{{ 職業分析分位亮點條件文字 }}</small>
            <strong>{{ 職業分析分位亮點標題 }}</strong>
          </span>
        </header>

        <article class="職業分位亮點卡">
          <div class="職業分位亮點列表">
            <button
              v-for="列 in 職業分析分位亮點列"
              :key="列.job"
              class="職業分位亮點列"
              type="button"
              :class="{ 已選取: 職業分析目前範圍代碼 === 列.job }"
              :style="列.樣式"
              :aria-label="`查看${顯示職業名稱(列.job)}職業分析`"
              @click="選擇職業分析職業(列.job)"
            >
              <span class="職業分位亮點職業">
                <img
                  v-if="職業Icon路徑(列.job)"
                  class="職業圖示"
                  :src="職業Icon路徑(列.job)"
                  alt=""
                  loading="lazy"
                  @error="隱藏載入失敗圖片"
                />
                <strong>{{ 顯示職業名稱(列.job) }}</strong>
              </span>
              <span class="職業分位亮點數值 職業分位亮點主值">
                <small>前段 25%</small>
                <strong>{{ 格式化傷害數值(列.前段值) }}</strong>
              </span>
              <span class="職業分位亮點數值 職業分位亮點中位值">
                <small>中位</small>
                <strong>{{ 格式化傷害數值(列.中位數) }}</strong>
              </span>
              <span class="職業分位亮點數值 職業分位亮點最高值">
                <small>最高</small>
                <strong>{{ 格式化傷害數值(列.最高值) }}</strong>
              </span>
              <span class="職業分位亮點樣本">{{ 格式化整數(列.樣本數) }} 筆</span>
              <span class="職業分位亮點強度條" aria-hidden="true">
                <span></span>
              </span>
            </button>
          </div>
        </article>
      </section>

      <section class="職業焦點卡" aria-label="職業概要">
        <header class="職業焦點標題">
          <span class="職業焦點圖示" :class="職業色彩類別(職業分析目前範圍.色彩)">
            <img
              v-if="職業分析目前範圍.Icon路徑"
              :src="職業分析目前範圍.Icon路徑"
              :alt="職業分析目前範圍.名稱"
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
            <span v-else>全</span>
          </span>
          <span>
            <small>{{ 職業分析目前範圍.副標 }}</small>
            <strong>{{ 職業分析目前範圍.名稱 }}</strong>
          </span>
        </header>

        <div class="職業分析概要">
          <div v-for="項目 in 職業分析概要" :key="項目.標籤" class="概要項">
            <span>{{ 項目.標籤 }}</span>
            <strong>{{ 項目.數值 }}</strong>
          </div>
        </div>
      </section>

      <section v-if="職業分析詳細" class="職業深化版面" aria-label="職業深入分析">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2>副本別 rDPS</h2>
            <span>Active 達標樣本中位</span>
          </header>
          <div class="職業副本輸出列表">
            <div v-for="副本 in 職業分析副本輸出列" :key="副本.key" class="職業副本輸出項">
              <span class="職業副本輸出名稱">
                <small>{{ 副本.分類 }}</small>
                <strong>{{ 副本.名稱 }}</strong>
              </span>
              <span class="職業副本輸出數值">
                <small>中位</small>
                <strong>{{ 格式化傷害數值(副本.中位數) }}</strong>
              </span>
              <span class="職業副本輸出數值">
                <small>前段 25%</small>
                <strong>{{ 格式化傷害數值(副本.上四分位) }}</strong>
              </span>
              <span class="職業副本輸出數值">
                <small>最高</small>
                <strong>{{ 格式化傷害數值(副本.最高值) }}</strong>
              </span>
              <span class="職業副本輸出樣本">{{ 格式化整數(副本.樣本數) }} 筆</span>
              <span class="職業副本輸出條" aria-hidden="true">
                <span :style="比例條樣式(副本.強度)"></span>
              </span>
            </div>
          </div>
        </article>
      </section>

      <section v-if="職業分析代表紀錄.length > 0" class="職業代表紀錄列" aria-label="代表紀錄">
        <article v-for="紀錄 in 職業分析代表紀錄" :key="紀錄.標籤" class="職業代表紀錄卡">
          <span>{{ 紀錄.標籤 }}</span>
          <strong>{{ 紀錄.主要數值 }}</strong>
          <em>{{ 紀錄.補充 }}</em>
          <small>{{ 紀錄.成績.encounter_name }}・{{ 格式化紀錄日期(紀錄.成績.recorded_at_iso) }}</small>
        </article>
      </section>

      <section class="統計版面" aria-label="職業副本與伺服器分析">
        <article class="統計面板">
          <header class="統計面板標題">
            <h2>副本分布</h2>
            <span>{{ 職業分析目前範圍.名稱 }}公開通關分布</span>
          </header>
          <div class="分布列表">
            <div v-for="副本 in 職業分析副本列" :key="副本.encounter_key" class="分布項">
              <div class="分布列">
                <strong>{{ 副本.encounter_name }}</strong>
                <span>{{ 格式化整數(副本.數量) }} 紀錄・{{ 副本.主要百分比文字 }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span
                  class="分布條填滿"
                  :class="職業色彩類別(職業分析目前範圍.色彩)"
                  :style="比例條樣式(副本.範圍內佔比)"
                ></span>
              </div>
              <small class="職業分析補充">{{ 副本.補充 }}</small>
              <div v-if="副本.職業分布列?.length > 0" class="職能職業分布列表">
                <div class="職能職業分布堆疊條" aria-hidden="true">
                  <span
                    v-for="職業 in 副本.職業分布列"
                    :key="職業.job"
                    class="職能職業分布堆疊段"
                    :style="職業.樣式"
                  ></span>
                </div>
                <div class="職能職業分布標籤列">
                  <span
                    v-for="職業 in 副本.職業分布列"
                    :key="職業.job"
                    class="職能職業分布標籤"
                    :style="職業.樣式"
                    :title="`${顯示職業名稱(職業.job)} ${格式化整數(職業.數量)} 紀錄・${格式化百分比(職業.佔比)}`"
                  >
                    <img
                      v-if="職業Icon路徑(職業.job)"
                      class="職業圖示"
                      :src="職業Icon路徑(職業.job)"
                      alt=""
                      loading="lazy"
                      @error="隱藏載入失敗圖片"
                    />
                    <strong>{{ 顯示職業名稱(職業.job) }}</strong>
                    <em>{{ 格式化百分比(職業.佔比) }}</em>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </article>

        <article class="統計面板">
          <header class="統計面板標題">
            <h2>伺服器分布</h2>
            <span>{{ 職業分析目前範圍.名稱 }}全服落點</span>
          </header>
          <div class="分布列表">
            <div v-for="伺服器 in 職業分析伺服器列" :key="伺服器.server" class="分布項">
              <div class="分布列">
                <strong>{{ 伺服器.server }}</strong>
                <span>{{ 格式化整數(伺服器.數量) }} 紀錄・{{ 伺服器.主要百分比文字 }}</span>
              </div>
              <div class="分布條" aria-hidden="true">
                <span
                  class="分布條填滿"
                  :class="職業色彩類別(職業分析目前範圍.色彩)"
                  :style="比例條樣式(伺服器.全職業佔比)"
                ></span>
              </div>
              <small class="職業分析補充">{{ 伺服器.補充 }}</small>
              <div v-if="伺服器.職業分布列?.length > 0" class="職能職業分布列表">
                <div class="職能職業分布堆疊條" aria-hidden="true">
                  <span
                    v-for="職業 in 伺服器.職業分布列"
                    :key="職業.job"
                    class="職能職業分布堆疊段"
                    :style="職業.樣式"
                  ></span>
                </div>
                <div class="職能職業分布標籤列">
                  <span
                    v-for="職業 in 伺服器.職業分布列"
                    :key="職業.job"
                    class="職能職業分布標籤"
                    :style="職業.樣式"
                    :title="`${顯示職業名稱(職業.job)} ${格式化整數(職業.數量)} 紀錄・${格式化百分比(職業.佔比)}`"
                  >
                    <img
                      v-if="職業Icon路徑(職業.job)"
                      class="職業圖示"
                      :src="職業Icon路徑(職業.job)"
                      alt=""
                      loading="lazy"
                      @error="隱藏載入失敗圖片"
                    />
                    <strong>{{ 顯示職業名稱(職業.job) }}</strong>
                    <em>{{ 格式化百分比(職業.佔比) }}</em>
                  </span>
                </div>
              </div>
            </div>
          </div>
        </article>
      </section>
    </template>
  </section>
</template>
