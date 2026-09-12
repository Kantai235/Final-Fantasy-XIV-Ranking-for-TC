const 日期 = (日) => new Date(日 * 86400000).toISOString().slice(0, 10);
const 中位數 = (值) => {
  const 排序 = [...值].sort((a, b) => a - b);
  const 中間 = Math.floor(排序.length / 2);
  return 排序.length % 2 ? 排序[中間] : (排序[中間 - 1] + 排序[中間]) / 2;
};
const 整週 = (天) => Math.max(7, Math.round(天 / 7) * 7);
// 日序 0 為週四；國際服歷史排程以週二為主，推測也採週二，但不改動正式日期。
const 國際週二 = (日, 最早 = -Infinity, 最晚 = Infinity) => {
  const 起 = Math.ceil((最早 + 2) / 7) * 7 - 2;
  const 迄 = Math.floor((最晚 + 2) / 7) * 7 - 2;
  if (起 > 迄) throw new Error('國際推測日期之間沒有足夠的星期二');
  return Math.max(起, Math.min(Math.round((日 + 2) / 7) * 7 - 2, 迄));
};

/**
 * 同編號的內容延後推出天數不隨整個主版週期伸縮：例如 .01 是上市後兩週。
 * .01／.05 核對 3.0 起的上市節奏；其他小版取最近三個資料片同編號樣本。
 * 資料片前的 .5 空窗獨立使用最近兩次已完成週期，避免混入一般主版中位數。
 * @param {{patch:string, day:number}[]} 歷史列
 * @param {string|null} 來源
 */
function 建立國際規律(歷史列, 來源) {
  const 最新資料片 = Math.max(...歷史列.map((列) => Number(列.patch.split('.')[0])));
  const 近期起始 = Math.max(5, 最新資料片 - 2);
  const 主版 = 歷史列.filter((列) => /^\d+\.[0-5]$/.test(列.patch));
  const 間隔 = 主版.slice(1).flatMap((列, i) => {
    const 前 = 主版[i];
    const [代, 版] = 前.patch.split('.').map(Number);
    const 一般 = 列.patch === `${代}.${版 + 1}`;
    const 資料片 = 版 === 5 && 列.patch === `${代 + 1}.0`;
    return 一般 || 資料片 ? [{ from_patch: 前.patch, to_patch: 列.patch, days: 列.day - 前.day, expansion: 資料片 }] : [];
  });
  const 一般樣本 = 間隔.filter((項) => !項.expansion).slice(-3);
  const 資料片樣本 = 間隔.filter((項) => 項.expansion && Number(項.from_patch.split('.')[0]) >= 5).slice(-2);
  const 後綴 = [...new Set(歷史列.filter((列) => /^\d+\.[0-5]\d$/.test(列.patch)).map((列) => 列.patch.split('.')[1]))].sort();
  const 小版規律 = 後綴.flatMap((suffix) => {
    const 上市 = ['01', '05'].includes(suffix);
    const 樣本 = 歷史列.filter((列) => 列.patch.split('.')[1] === suffix && Number(列.patch.split('.')[0]) >= (上市 ? 3 : 近期起始))
      .flatMap((列) => {
        const base_patch = `${列.patch.split('.')[0]}.${suffix[0]}`;
        const 起 = 主版.find((項) => 項.patch === base_patch);
        return 起 && 列.day > 起.day ? [{ patch: 列.patch, base_patch, days: 列.day - 起.day }] : [];
      }).slice(上市 ? -5 : -3);
    return 樣本.length ? [{ suffix, days: 整週(中位數(樣本.map((項) => 項.days))), samples: 樣本,
      min_days: Math.min(...樣本.map((項) => 項.days)), max_days: Math.max(...樣本.map((項) => 項.days)) }] : [];
  });
  return { source_url: 來源, update_weekday: 2, recent_expansion_from: 近期起始,
    regular_samples: 一般樣本, expansion_samples: 資料片樣本, minor_offsets: 小版規律,
    expansion_cycle_days: 資料片樣本.length ? 整週(中位數(資料片樣本.map((項) => 項.days))) : null };
}

/**
 * 推測只存在於獨立情境，原始日期、released 旗標與歷史統計不變。
 * 國際主版分一般週期／資料片空窗，小版採同編號歷史天數；繁中優先採站務指定的目標週期與更新星期，
 * 未設定時才沿用歷史週期。月份公告用月中／月初／月底作情境錨點，
 * 絕不升格成正式發布日期或歷史樣本。Vue 只讀取結果，不執行推測運算。
 * @param {Array<import('./build_version_progress.mjs').版本設定 & {order:number,
 * international_day:number, tc_day:number|null, tc_plan_day?:number|null, international_released:boolean, tc_released:boolean}>} 原始列
 * @param {{patch:string,title:string,month:string,url:string,start_day:number,end_day:number}[]} 預定
 * @param {number} 開服日
 * @param {number} 截止日
 * @param {{tc_main_cycle_days:number, tc_update_weekday:number, tc_skipped_patches?:string[],
 * shared_minor_intervals?:{from_expansion:number, steps:{from:string,to:string,days:number}[]}}} [規則]
 * @param {{url:string, patches:{patch:string, day:number}[]}} [國際歷史]
 */
export function 建置追趕推測(原始列, 預定, 開服日, 截止日, 規則, 國際歷史) {
  // 使用完整版本號比對，讓 8.x 合併假設不隨小版模板複製到 9.x 之後。
  // 清單也保留交會點之後的假設，較慢情境延伸至該版本時仍會一致套用。
  const 跳版 = new Set([...原始列.filter((列) => 列.tc_forecast_skip).map((列) => 列.patch), ...(規則?.tc_skipped_patches || [])]);
  const 固定間隔 = 規則?.shared_minor_intervals;
  // 時長描述前版到下版的完整間隔，例如 .11 的 21 天代表 .15 在 .11 後三週。
  // 兩服各從自己的前版日期起算，不以主版壓縮比例縮短；公告日不經過此推測入口。
  const 固定小版日 = (patch, 地區, 列表) => {
    const [代, 後綴] = patch.split('.');
    if (!固定間隔 || Number(代) < 固定間隔.from_expansion) return null;
    const 段 = 固定間隔.steps.find((項) => 項.to === 後綴);
    const 前版 = 段 && 列表.find((列) => 列.patch === `${代}.${段.from}`);
    // 前版合併而沒有獨立繁中日期時，不借用國際日或合併目標捏造固定間隔。
    return 前版?.[`${地區}_day`] != null ? 前版[`${地區}_day`] + 段.days : null;
  };
  const 主要列 = 原始列.filter((列) => 列.major);
  const 週期 = (地區) => {
    const 已發布 = 主要列.filter((列) => 列[`${地區}_released`]);
    return 已發布.slice(1).map((列, i) => ({
      from_patch: 已發布[i].patch, to_patch: 列.patch,
      days: 列[`${地區}_day`] - 已發布[i][`${地區}_day`],
    })).filter((項) => 項.days > 0).slice(-3);
  };
  const 繁中樣本 = 週期('tc');
  const 國際規律 = 建立國際規律([...(國際歷史?.patches || []), ...原始列.filter((列) => 列.international_released)
    .map((列) => ({ patch: 列.patch, day: 列.international_day }))], 國際歷史?.url || null);
  const 國際樣本 = 國際規律.regular_samples;
  if (繁中樣本.length < 2 || 國際樣本.length < 2) {
    return Object.fromEntries(['all', 'major'].map((範圍) => {
      const 目前 = 原始列.findLast((列) => 列.tc_released);
      const 下一版 = 原始列.find((列) => 列.order > 目前.order && !列.tc_version_omitted && !跳版.has(列.patch) && (範圍 === 'all' || 列.major));
      return [範圍, { status: 'insufficient', next: 下一版?.tc || 下一版?.tc_plan ? { patch: 下一版.patch, date: 下一版.tc || 下一版.tc_plan.date,
        announced: Boolean(下一版.tc), planned: Boolean(下一版.tc_plan), attribution: 下一版.tc_plan?.attribution } : null }];
    }));
  }
  const 繁中歷史週期 = Math.round(中位數(繁中樣本.map((項) => 項.days)));
  const 繁中週期 = 規則?.tc_main_cycle_days ?? 繁中歷史週期;
  const 國際週期 = 整週(中位數(國際樣本.map((項) => 項.days)));
  // UTC 日序 0 是星期四。只調整推測日期，公告與活動預告須保留原始日曆日。
  const 星期偏移 = (規則?.tc_update_weekday ?? 4) - 4;
  const 向前更新日 = (日) => 規則 ? Math.floor((日 - 星期偏移) / 7) * 7 + 星期偏移 : 日;
  const 向後更新日 = (日) => 規則 ? Math.ceil((日 - 星期偏移) / 7) * 7 + 星期偏移 : 日;
  const 對齊更新日 = (目標日, 最早日, 最晚日 = Infinity) => {
    const 起 = 向後更新日(最早日); const 迄 = 向前更新日(最晚日);
    if (起 > 迄) throw new Error('繁中已知日期之間沒有足夠的更新日可安排小版本');
    const 最近 = 規則 ? Math.round((目標日 - 星期偏移) / 7) * 7 + 星期偏移 : 目標日;
    return Math.max(起, Math.min(最近, 迄));
  };
  const 已發布 = 原始列.filter((列) => 列.tc_released && 列.international_released);
  const 目前版本 = 已發布.at(-1);
  const 小版樣本 = 已發布.slice(1).flatMap((列, i) => {
    const 前版 = 已發布[i];
    const 國際天數 = 列.international_day - 前版.international_day;
    const 繁中天數 = 列.tc_day - 前版.tc_day;
    return !列.major && 國際天數 > 0 && 繁中天數 > 0
      ? [{ from_patch: 前版.patch, to_patch: 列.patch, international_days: 國際天數, tc_days: 繁中天數, ratio: 繁中天數 / 國際天數 }] : [];
  }).slice(-3);
  // 上限只防止無交會的模型無限延伸，不將它冒充保證追上的日期。
  const 上限日 = 截止日 + 365 * 20;

  function 模擬(繁中間距, 月位置, 小版比例) {
    const 列表 = 原始列.map((列) => ({ ...列, international_estimated: false, tc_estimated: false,
      // 預告只作現行版之後的情境錨點，不回頭補造漏收的歷史發布日期。
      tc_day: 列.tc_day ?? (列.order > 目前版本.order ? (列.tc_plan_day ?? null) : null),
      tc_planned: Boolean(列.tc_plan && 列.order > 目前版本.order),
      tc_forecast_skipped: 跳版.has(列.patch),
    }));
    const 月日 = (計畫) => 國際週二(計畫.start_day + (計畫.end_day - 計畫.start_day) * 月位置, 計畫.start_day, 計畫.end_day);
    // 未公告編號只作延伸模板；每個資料片暫依 .0～.5 接下一個 .0。
    // 公告月份在行進到對應版本時套用，後續新增 9.0 排程也不會跳過 8.x。
    let 前版 = 列表.findLast((列) => 列.major);
    const 最後已知日 = Math.max(...列表.map((列) => 列.international_day));
    while (前版.international_day <= 上限日 + 國際週期) {
      const [資料片, 主版] = 前版.patch.split('.').map(Number);
      const patch = 主版 >= 5 ? `${資料片 + 1}.0` : `${資料片}.${主版 + 1}`;
      const 計畫 = 預定.find((項) => 項.patch === patch);
      // 缺少月份公告時，不可把推測新主版排到已知的小版之前。
      const 間距 = 主版 >= 5 ? (國際規律.expansion_cycle_days ?? 國際週期) : 國際週期;
      const 國際日 = 計畫 ? 月日(計畫) : 國際週二(前版.international_day + 間距, 最後已知日 + 1);
      if (國際日 <= 前版.international_day) throw new Error('預定月份與推測版本順序衝突');
      前版 = { patch, title: 計畫?.title || '後續版本（推測）', major: true, international: null, tc: null,
        international_day: 國際日, tc_day: null, international_month: 計畫?.month,
        international_estimated: true, tc_estimated: false, international_released: false,
        tc_released: false, international_url: 計畫?.url || null, note_links: [], lag_days: null };
      列表.push(前版);
    }
    const 全部主版 = 列表.filter((列) => 列.major);
    for (let i = 0; i < 全部主版.length - 1; i++) {
      const 主版 = 全部主版[i];
      const 下一版 = 全部主版[i + 1];
      if (!主版.international_estimated) continue;
      const 模板 = 主要列.findLast((列) => 列.patch.split('.')[1] === 主版.patch.split('.')[1]);
      if (!模板) continue;
      const 模板末 = 全部主版[全部主版.findIndex((列) => 列.patch === 模板.patch) + 1].international_day;
      const 模板小版 = 原始列.filter((列) => !列.major && 列.order > 模板.order && 列.international_day < 模板末);
      let 前小版日 = 主版.international_day;
      for (const [j, 小版] of 模板小版.entries()) {
        const 後綴 = 小版.patch.split('.')[1];
        const 歷史規律 = 國際規律.minor_offsets.find((項) => 項.suffix === 後綴);
        const 延後 = 歷史規律?.days ?? 整週(小版.international_day - 模板.international_day);
        // 相同編號的中位數偶爾可能重疊；保留獨立週二並預留其後小版位置。
        // 國際 .01／.05 固定天數也因此不會被 133 天主版或 .5 空窗按比例壓縮。
        const patch = `${主版.patch}${小版.patch.slice(模板.patch.length)}`;
        const 固定日 = 固定小版日(patch, 'international', 列表);
        const 小版日 = 國際週二(固定日 ?? 主版.international_day + 延後, 前小版日 + 1,
          下一版.international_day - (模板小版.length - j) * 7);
        if (固定日 !== null && 小版日 !== 固定日) throw new Error(`固定小版間隔與國際排程衝突：${patch}`);
        列表.push({ patch, title: '後續小版本（推測）', major: false,
          international: null, tc: null, international_day: 小版日,
          tc_day: null, international_estimated: true, tc_estimated: false, international_released: false,
          tc_forecast_skipped: 跳版.has(patch),
          tc_released: false, international_url: null, note_links: [], lag_days: null });
        前小版日 = 小版日;
      }
    }
    列表.sort((a, b) => a.international_day - b.international_day);
    列表.forEach((列, i) => { 列.order = i; });
    const 主版列 = 列表.filter((列) => 列.major);
    const 目前順序 = 列表.find((列) => 列.patch === 已發布.at(-1).patch).order;
    let 前繁中主版;
    for (const 列 of 主版列) {
      if (列.tc_day === null && 列.order > 目前順序 && 前繁中主版) {
        const 已知小版末日 = Math.max(-Infinity, ...列表.filter((項) => 項.order > 前繁中主版.order && 項.order < 列.order && 項.tc_day !== null).map((項) => 項.tc_day));
        列.tc_day = 對齊更新日(前繁中主版.tc_day + 繁中間距,
          Math.max(列.international_day, 前繁中主版.tc_day + 1, 已知小版末日 + 1));
        列.tc_estimated = true;
      }
      if (列.tc_day !== null) 前繁中主版 = 列;
    }
    const 繁中目前 = 已發布.at(-1);
    const 下一小版 = 列表.find((列) => 列.order > 目前順序 && !列.tc_version_omitted && !列.tc_forecast_skipped);
    for (let i = 0; i < 主版列.length - 1; i++) {
      const 主版 = 主版列[i]; const 下主版 = 主版列[i + 1];
      if (主版.tc_day === null || 下主版.tc_day === null) continue;
      const 小版列 = 列表.filter((列) => 列.order > 主版.order && 列.order < 下主版.order && !列.tc_version_omitted && !列.tc_forecast_skipped);
      // 固定日期先分隔區間。先倒推保留每個小版可用的更新日，再依序靠近估算落點，
      // 避免週二取整造成兩版同日、超過下個主版，或改動記者會暨玩家見面會預告等固定日期。
      const 錨點 = [主版, ...小版列.filter((列) => 列.tc_day !== null), 下主版];
      for (let j = 0; j < 錨點.length - 1; j++) {
        const 起 = 錨點[j]; const 迄 = 錨點[j + 1];
        const 待排 = 小版列.filter((項) => 項.order > 起.order && 項.order < 迄.order && 項.order > 目前順序);
        let 最晚 = 迄.tc_day;
        const 上界 = new Map();
        for (const 列 of 待排.toReversed()) { 最晚 = 向前更新日(最晚 - 1); 上界.set(列.patch, 最晚); }
        let 前更新日 = 起.tc_day;
        for (const 列 of 待排) {
          const 比例 = (列.international_day - 起.international_day) / (迄.international_day - 起.international_day);
          const 固定日 = 固定小版日(列.patch, 'tc', 列表);
          const 目標日 = 固定日 ?? (列 === 下一小版 && 小版比例 !== null
            ? 繁中目前.tc_day + Math.round((列.international_day - 繁中目前.international_day) * 小版比例)
            : 起.tc_day + Math.round((迄.tc_day - 起.tc_day) * 比例));
          列.tc_day = 對齊更新日(目標日, Math.max(列.international_day, 前更新日 + 1), 上界.get(列.patch));
          if (固定日 !== null && 列.tc_day !== 固定日) throw new Error(`固定小版間隔與繁中排程衝突：${列.patch}`);
          列.tc_estimated = true;
          前更新日 = 列.tc_day;
        }
      }
    }
    return 列表;
  }
  const 小版比例 = 小版樣本.length >= 2 ? 中位數(小版樣本.map((項) => 項.ratio)) : null;
  const 中央列 = 模擬(繁中週期, .5, 小版比例);
  const 現行順序 = 中央列.find((列) => 列.patch === 目前版本.patch).order;
  const 快速週期 = 規則 ? Math.max(7, 繁中週期 - 7) : Math.min(...繁中樣本.map((項) => 項.days));
  const 緩慢週期 = 規則 ? 繁中週期 + 7 : Math.max(...繁中樣本.map((項) => 項.days));
  const 快速列 = 模擬(快速週期, 1, 小版樣本.length >= 2 ? Math.min(...小版樣本.map((項) => 項.ratio)) : null);
  const 緩慢列 = 模擬(緩慢週期, 0, 小版樣本.length >= 2 ? Math.max(...小版樣本.map((項) => 項.ratio)) : null);
  function 交會(列表, 範圍) {
    const 節點 = 列表.filter((列) => !列.tc_version_omitted && (範圍 === 'all' || 列.major));
    const 現行繁中 = 節點.findLast((列) => 列.tc_released);
    const 現行國際 = 節點.findLast((列) => 列.international_released);
    if (現行繁中?.patch === 現行國際?.patch) return { patch: 現行繁中.patch, day: 截止日, date: 日期(截止日), already: true };
    const 點 = 節點.find((列, i) => 列.tc_day !== null && 列.tc_day >= 截止日 && 列.tc_day <= 上限日
      && 列.tc_day >= 列.international_day && 列.tc_day < (節點[i + 1]?.international_day ?? -Infinity));
    return 點 ? { patch: 點.patch, day: 點.tc_day, date: 日期(點.tc_day) } : null;
  }
  // 首次追上只代表當日的版本相同，不能據此提前下一主版、壓縮既有內容週期。
  // 延伸顯示下一主版及所屬小版時直接沿用完整模擬的雙服日期；這裡只決定觀察終點。
  // 國際服可能在繁中抵達下一主版前繼續推出小版，也必須列入同一時間範圍。
  const 完整交點 = 交會(中央列, 'all');
  const 延伸主版 = (() => {
    if (!完整交點) return null;
    const 交會列 = 中央列.find((列) => 列.patch === 完整交點.patch);
    const 下主版 = 中央列.find((列) => 列.major && 列.order > 交會列.order && 列.international_day > 完整交點.day);
    if (下主版?.tc_day == null) return null;
    const 再下主版 = 中央列.find((列) => 列.major && 列.order > 下主版.order);
    const 同組版本 = 中央列.filter((列) => 列.order >= 下主版.order && 列.order < (再下主版?.order ?? Infinity));
    // 納入整組的小版，例如 8.55／8.56；合併版只有國際日期，不能補造繁中更新。
    const 終點 = Math.max(...同組版本.flatMap((列) => [列.international_day, 列.tc_day].filter((日) => 日 !== null)));
    if (終點 > 上限日) return null;
    const 前主版 = 中央列.findLast((列) => 列.major && 列.order < 下主版.order && 列.tc_day !== null);
    return { patch: 下主版.patch, end_patch: 同組版本.at(-1).patch, end_day: 終點,
      international_date: 日期(下主版.international_day), tc_date: 日期(下主版.tc_day),
      previous_major: 前主版.patch, tc_cycle_days: 下主版.tc_day - 前主版.tc_day };
  })();
  // 同步候選必須由既有排程自然得到同日的主版，不能為了對齊而壓縮前版週期。
  // 首次追上小版進度後仍可能短暫落後；延伸至此節點，才呈現「可能開始同步」。
  const 同步列 = 完整交點 && 中央列.find((列) => 列.major && 列.tc_day > 截止日 && 列.tc_day >= 完整交點.day
    && 列.tc_day <= 上限日 && 列.tc_day === 列.international_day);
  const 同步起點 = 同步列 ? { patch: 同步列.patch, day: 同步列.tc_day, date: 日期(同步列.tc_day) } : null;
  return Object.fromEntries(['all', 'major'].map((範圍) => {
    const 交點 = 交會(中央列, 範圍);
    // 兩種篩選共用延伸主版與同步候選的觀察終點；首次交會統計仍各自保留。
    const 終點 = Math.max(延伸主版?.end_day ?? 交點?.day ?? 上限日, 同步起點?.day ?? -Infinity);
    const 列表 = 中央列.filter((列) => (範圍 === 'all' || 列.major) && 列.international_day <= 終點)
      .map((列) => {
        // 情境間隔使用同一列的雙服日期；合併版缺少獨立日期時不能補成 0 天。
        // 只更新情境副本，已上線摘要與一般模式仍使用原始列的實際間隔。
        const 可比較 = Number.isFinite(列.tc_day) && Number.isFinite(列.international_day);
        return { ...列, tc_sync_candidate: 列.patch === 同步起點?.patch,
          lag_days: 可比較 ? 列.tc_day - 列.international_day : null,
          lag_estimated: 可比較 && Boolean(列.tc_estimated || 列.international_estimated || 列.tc_planned),
        };
      });
    for (const 地區 of ['international', 'tc']) {
      const 有日期 = 列表.filter((列) => 列[`${地區}_day`] !== null && 列[`${地區}_day`] <= 終點);
      列表.forEach((列) => { 列[`${地區}_duration`] = null; });
      有日期.forEach((列, i) => {
        const 下一版 = 有日期[i + 1];
        列[`${地區}_duration`] = { days: (下一版?.[`${地區}_day`] ?? 終點) - 列[`${地區}_day`], ongoing: false,
          estimated: Boolean(列[`${地區}_estimated`] || 下一版?.[`${地區}_estimated`] || !列[`${地區}_released`] || !下一版?.[`${地區}_released`]), through_horizon: !下一版 };
      });
    }
    const 主版 = 列表.filter((列) => 列.major);
    const 群組 = 主版.map((列, i) => {
      const rows = 列表.filter((項) => 項.order >= 列.order && 項.order < (主版[i + 1]?.order ?? Infinity));
      // 最後一組只累計到情境終點，不冒充尚未走完的完整主版週期。
      const 時長 = (地區) => {
        const 有時長 = rows.filter((項) => 項[`${地區}_duration`]);
        return 有時長.length ? { days: 有時長.reduce((總和, 項) => 總和 + 項[`${地區}_duration`].days, 0), ongoing: false,
          estimated: 有時長.some((項) => 項[`${地區}_duration`].estimated), through_horizon: 有時長.at(-1)[`${地區}_duration`].through_horizon } : null;
      };
      // 接近同步的末期主版與同步候選主版，其週期仍依賴未來排程。
      // 依顯示規則保留未定提示；天數留作內部守恆檢查，不宣稱已確定同步。
      const duration_outlook = 列.patch === 延伸主版?.patch || 列.tc_sync_candidate
        ? { international: 'unknown', tc: 'may_synchronize' } : null;
      return { patch: 列.patch, rows, international_duration: 時長('international'), tc_duration: 時長('tc'), duration_outlook };
    });
    const 階段 = 列表.filter((列) => !列.tc_version_omitted);
    const 時間線 = (地區) => {
      const 可用 = 階段.filter((列) => 列[`${地區}_day`] !== null && 列[`${地區}_day`] <= 終點);
      const 最後實際 = 可用.findLast((列) => 列[`${地區}_released`]);
      return 可用.filter((列) => 列.order >= 最後實際.order).map((列) => ({
        patch: 列.patch, day: 列 === 最後實際 ? Math.min(截止日, 可用.find((項) => 項.order > 列.order)?.[`${地區}_day`] ?? 截止日) : 列[`${地區}_day`],
        date: 日期(列[`${地區}_day`]), stage: 階段.indexOf(列), estimated: 列[`${地區}_estimated`], planned: 地區 === 'tc' && 列.tc_planned,
      }));
    };
    const 下一版 = 列表.find((列) => 列.order > 現行順序 && !列.tc_version_omitted && !列.tc_forecast_skipped && 列.tc_day !== null);
    return [範圍, { status: 交點 ? 'estimated' : 'no_catch_up', method: 'moving-release-cadence-v9',
      rows: 列表, groups: 群組, stages: 階段.map((列) => 列.patch), tc: 時間線('tc'), international: 時間線('international'),
      catch_up: 交點, fast_catch_up: 交會(快速列, 範圍), slow_catch_up: 交會(緩慢列, 範圍), horizon_years: 20,
      continuation_major: 延伸主版,
      synchronization_start: 同步起點,
      plot_end_day: 終點, plot_end_date: 日期(終點), days_to_catch_up: 交點 ? 交點.day - 截止日 : null,
      elapsed_to_catch_up: 交點 ? 交點.day - 開服日 : null,
      tc_cycle_days: 繁中週期, international_cycle_days: 國際週期, tc_samples: 繁中樣本, international_samples: 國際樣本, minor_samples: 小版樣本,
      international_cadence: 國際規律,
      shared_minor_intervals: 固定間隔 ?? null,
      tc_cycle_source: 規則 ? 'scenario' : 'history', tc_historical_cycle_days: 繁中歷史週期,
      tc_update_weekday: 規則?.tc_update_weekday ?? null,
      tc_typical_cycle_days: 規則 ? Math.round(繁中週期 / 7) * 7 : 繁中週期,
      fast_tc_cycle_days: 快速週期, slow_tc_cycle_days: 緩慢週期,
      skipped_patches: [...跳版],
      next: 下一版 ? { patch: 下一版.patch, date: 日期(下一版.tc_day), announced: Boolean(下一版.tc), overdue: 下一版.tc_day <= 截止日,
        planned: Boolean(下一版.tc_planned), attribution: 下一版.tc_plan?.attribution,
        merged_into: 下一版.merged_into || null } : null,
    }];
  }));
}
