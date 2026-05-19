<script>
import { injectRankingApp } from "../composables/useRankingApp";

export default {
  name: "ComparePage",
  setup() {
    return injectRankingApp();
  },
};
</script>

<template>
  <section class="使用者搜尋區" aria-label="玩家比較查詢">
    <form class="使用者搜尋表單 比較搜尋表單" :class="{ 比較搜尋表單含版本: 顯示比較版本篩選 }" @submit.prevent="提交角色比較">
      <fieldset class="比較職能選擇">
        <legend>比較職能</legend>
        <div class="比較職能按鈕列" role="radiogroup" aria-label="比較職能">
          <button
            v-for="職能 in 比較職能設定"
            :key="職能.代碼"
            type="button"
            class="比較職能按鈕"
            :class="[職業色彩類別(職能.色彩), { 作用中: 比較職能篩選 === 職能.代碼 }]"
            role="radio"
            :aria-checked="比較職能篩選 === 職能.代碼"
            @click="比較職能篩選 = 職能.代碼"
          >
            <img
              v-if="職業類型Icon路徑(職能.圖示代碼)"
              class="職業圖示 職業標籤圖示"
              :src="職業類型Icon路徑(職能.圖示代碼)"
              alt=""
              loading="lazy"
              @error="隱藏載入失敗圖片"
            />
            <span>{{ 職能.名稱 }}</span>
          </button>
        </div>
      </fieldset>

      <div class="欄位 副本選單欄位 比較副本選單欄位" @focusout="處理比較副本選單失焦">
        <span>統計範圍</span>
        <div class="副本選單">
          <button
            class="副本選單按鈕"
            type="button"
            :aria-expanded="比較副本選單開啟"
            aria-haspopup="true"
            @click="切換比較副本選單"
          >
            <span class="副本選單目前值">{{ 比較副本選單文字 }}</span>
            <span class="選單箭頭">▾</span>
          </button>

          <div v-if="比較副本選單開啟" class="副本選單面板" role="menu" aria-label="玩家比較統計範圍">
            <section class="副本分類群">
              <p class="副本分類標題">全部</p>
              <button
                class="副本選單項"
                type="button"
                :class="{ 已選取: 比較副本鍵值 === 'all' }"
                @click="選擇比較副本(null)"
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
                :class="{ 已選取: 比較副本鍵值 === 副本.key }"
                @click="選擇比較副本(副本)"
              >
                {{ 副本.name }}
              </button>
            </section>
          </div>
        </div>
      </div>

      <label v-if="顯示比較版本篩選" class="欄位">
        <span>版本紀錄</span>
        <select v-model="比較版本範圍">
          <option v-for="選項 in 版本紀錄範圍選項" :key="選項.value" :value="選項.value">
            {{ 選項.label }}
          </option>
        </select>
      </label>

      <label class="欄位 使用者搜尋欄位 比較玩家欄位">
        <span>玩家 A</span>
        <input
          v-model="比較角色左輸入"
          type="search"
          list="比較角色左搜尋建議"
          placeholder="輸入玩家名稱，或選擇「玩家 @ 伺服器」"
        />
        <datalist id="比較角色左搜尋建議">
          <option v-for="建議 in 比較角色左搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
            {{ 建議.label }}
          </option>
        </datalist>
      </label>

      <label class="欄位 使用者搜尋欄位 比較玩家欄位">
        <span>玩家 B</span>
        <input
          v-model="比較角色右輸入"
          type="search"
          list="比較角色右搜尋建議"
          placeholder="輸入玩家名稱，或選擇「玩家 @ 伺服器」"
        />
        <datalist id="比較角色右搜尋建議">
          <option v-for="建議 in 比較角色右搜尋建議" :key="`${建議.character_name}@${建議.server}`" :value="建議.value">
            {{ 建議.label }}
          </option>
        </datalist>
      </label>

      <button type="submit">比較</button>
    </form>
  </section>

  <section class="角色比較區" aria-live="polite">
    <div v-if="比較讀取中" class="狀態列">讀取玩家比較資料中</div>
    <div v-else-if="比較錯誤訊息" class="狀態列 錯誤">{{ 比較錯誤訊息 }}</div>
    <div v-else-if="!角色比較已完成" class="狀態列">輸入兩個玩家後即可比較公開成績</div>

    <template v-else>
      <section class="角色比較概要" aria-label="玩家比較概要">
        <article class="比較角色卡">
          <header>
            <span>玩家 A</span>
            <strong>{{ 比較角色左.character_name }}</strong>
            <em>{{ 比較角色左.server }}</em>
          </header>
          <div class="比較角色數據">
            <span>副本數 <strong>{{ 比較角色左.統計.副本數 }}</strong></span>
            <span>公開成績 <strong>{{ 比較角色左.統計.公開成績數 }}</strong></span>
            <span>最佳 rDPS <strong>{{ 格式化傷害數值(比較角色左.統計.最佳成績?.rdps) }}</strong></span>
            <span v-if="顯示Gcd覆蓋率">最佳 GCD <strong>{{ 格式化Gcd覆蓋率(比較角色左.統計.最高Gcd成績?.gcd_coverage) }}</strong></span>
            <span>
              最後紀錄
              <strong class="比較最後紀錄時間">
                <span>{{ 格式化紀錄日期(比較角色左.統計.最後紀錄時間) }}</span>
                <span v-if="格式化紀錄時刻(比較角色左.統計.最後紀錄時間)">
                  {{ 格式化紀錄時刻(比較角色左.統計.最後紀錄時間) }}
                </span>
              </strong>
            </span>
          </div>
        </article>

        <article class="比較角色卡">
          <header>
            <span>玩家 B</span>
            <strong>{{ 比較角色右.character_name }}</strong>
            <em>{{ 比較角色右.server }}</em>
          </header>
          <div class="比較角色數據">
            <span>副本數 <strong>{{ 比較角色右.統計.副本數 }}</strong></span>
            <span>公開成績 <strong>{{ 比較角色右.統計.公開成績數 }}</strong></span>
            <span>最佳 rDPS <strong>{{ 格式化傷害數值(比較角色右.統計.最佳成績?.rdps) }}</strong></span>
            <span v-if="顯示Gcd覆蓋率">最佳 GCD <strong>{{ 格式化Gcd覆蓋率(比較角色右.統計.最高Gcd成績?.gcd_coverage) }}</strong></span>
            <span>
              最後紀錄
              <strong class="比較最後紀錄時間">
                <span>{{ 格式化紀錄日期(比較角色右.統計.最後紀錄時間) }}</span>
                <span v-if="格式化紀錄時刻(比較角色右.統計.最後紀錄時間)">
                  {{ 格式化紀錄時刻(比較角色右.統計.最後紀錄時間) }}
                </span>
              </strong>
            </span>
          </div>
        </article>
      </section>

      <section class="統計面板 統計面板寬" aria-label="副本成績比較">
        <header class="統計面板標題">
          <h2>{{ 目前比較職能?.名稱 || "職能" }}成績比較</h2>
          <span>
            {{ 比較角色左.character_name }}・{{ 比較角色右.character_name }}・{{ 比較範圍文字 }}
            <template v-if="顯示比較版本篩選">・{{ 取得版本紀錄範圍文字(有效比較版本範圍) }}</template>
          </span>
        </header>
        <div class="統計表格外框">
          <table class="統計表格 比較表格">
            <colgroup>
              <col class="比較表格副本欄" />
              <col class="比較表格玩家欄" />
              <col class="比較表格玩家欄" />
              <col class="比較表格差異欄" />
            </colgroup>
            <thead>
              <tr>
                <th scope="col">副本</th>
                <th scope="col">{{ 比較角色左.character_name }}</th>
                <th scope="col">{{ 比較角色右.character_name }}</th>
                <th scope="col" class="數字">差異</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="列 in 角色比較列" :key="列.key">
                <td>
                  <span class="比較副本">
                    <small>{{ 列.encounter_category || "副本" }}</small>
                    <strong>{{ 列.encounter_name }}</strong>
                  </span>
                </td>
                <td>
                  <div v-if="列.左" class="比較成績格" :class="{ 過版紀錄列: 列.左.best_entry.is_obsolete_record }">
                    <span class="比較成績主列">
                      <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.左.best_entry.job))">
                        <img
                          v-if="職業Icon路徑(列.左.best_entry.job)"
                          class="職業圖示 職業標籤圖示"
                          :src="職業Icon路徑(列.左.best_entry.job)"
                          alt=""
                          loading="lazy"
                          @error="隱藏載入失敗圖片"
                        />
                        <span>{{ 顯示職業名稱(列.左.best_entry.job) }}</span>
                      </span>
                      <span v-if="列.左.best_entry.is_obsolete_record" class="版本紀錄標籤">過版紀錄</span>
                    </span>
                    <strong>{{ 格式化傷害數值(列.左.best_entry.rdps) }}</strong>
                    <span class="比較成績輔助列">
                      <small>Rank {{ 格式化排名(列.左.best_entry.job_rank ?? 列.左.best_entry.rank) }}</small>
                      <small>Active {{ 格式化Active(列.左.best_entry.active_percent) }}</small>
                      <small v-if="顯示Gcd覆蓋率">GCD {{ 格式化Gcd覆蓋率(列.左.best_entry.gcd_coverage) }}</small>
                    </span>
                  </div>
                  <span v-else>-</span>
                </td>
                <td>
                  <div v-if="列.右" class="比較成績格" :class="{ 過版紀錄列: 列.右.best_entry.is_obsolete_record }">
                    <span class="比較成績主列">
                      <span class="職業標籤" :class="職業色彩類別(職業代碼色彩(列.右.best_entry.job))">
                        <img
                          v-if="職業Icon路徑(列.右.best_entry.job)"
                          class="職業圖示 職業標籤圖示"
                          :src="職業Icon路徑(列.右.best_entry.job)"
                          alt=""
                          loading="lazy"
                          @error="隱藏載入失敗圖片"
                        />
                        <span>{{ 顯示職業名稱(列.右.best_entry.job) }}</span>
                      </span>
                      <span v-if="列.右.best_entry.is_obsolete_record" class="版本紀錄標籤">過版紀錄</span>
                    </span>
                    <strong>{{ 格式化傷害數值(列.右.best_entry.rdps) }}</strong>
                    <span class="比較成績輔助列">
                      <small>Rank {{ 格式化排名(列.右.best_entry.job_rank ?? 列.右.best_entry.rank) }}</small>
                      <small>Active {{ 格式化Active(列.右.best_entry.active_percent) }}</small>
                      <small v-if="顯示Gcd覆蓋率">GCD {{ 格式化Gcd覆蓋率(列.右.best_entry.gcd_coverage) }}</small>
                    </span>
                  </div>
                  <span v-else>-</span>
                </td>
                <td class="數字">
                  <span class="比較差異組">
                    <span class="比較差異項">
                      <small>rDPS</small>
                      <strong class="比較差異" :class="{ 左領先: 列.差異 > 0, 右領先: 列.差異 < 0 }">
                        {{ 列.差異 === null ? "-" : 格式化帶號整數(列.差異) }}
                      </strong>
                    </span>
                    <span v-if="顯示Gcd覆蓋率" class="比較差異項">
                      <small>GCD</small>
                      <strong class="比較差異" :class="{ 左領先: 列.GCD差異 > 0, 右領先: 列.GCD差異 < 0 }">
                        {{ 格式化帶號百分比(列.GCD差異) }}
                      </strong>
                    </span>
                  </span>
                </td>
              </tr>
              <tr v-if="角色比較列.length === 0">
                <td colspan="4" class="統計空列">{{ `兩個玩家目前沒有可比較的${目前比較職能?.名稱 || "職能"}共同資料` }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </template>
  </section>
</template>
