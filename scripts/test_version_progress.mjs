import assert from "node:assert/strict";
import { test } from "node:test";
import { readFileSync, mkdtempSync, mkdirSync, writeFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { 建置版本進度, 日序, 版本進度資料插件 } from "./build_version_progress.mjs";
import { 正規化版本進度選取 } from "../src/utils/versionProgress.js";

const 設定 = JSON.parse(readFileSync(new URL("../config/version_progress.json", import.meta.url), "utf8"));
const 資料 = 建置版本進度(設定);
const 複製設定 = () => structuredClone(設定);
// 假設 7.21 有獨立更新且沒有人工預告，隔離驗證更新頻率對模型的影響。
// 正式設定的合併省略與預告行為由下方另行驗證。
const 獨立小版情境設定 = () => {
  const 值 = 複製設定();
  delete 值.forecast_policy;
  for (const 列 of 值.patches) { delete 列.tc_plan; delete 列.tc_forecast_skip; }
  delete 值.patches.find((列) => 列.patch === "7.21").tc_version_omitted;
  return 值;
};

test("Vite 靜態模組與 Windows 路徑正規化後的設定更新", () => {
  const 插件 = 版本進度資料插件();
  const 監看檔案 = [];
  const 名稱 = 插件.resolveId("virtual:version-progress");
  const 模組內容 = 插件.load.call({ addWatchFile: (檔案) => 監看檔案.push(檔案) }, 名稱);
  assert.match(模組內容, /"current_tc":"7.2"/);
  assert.equal(監看檔案.length, 1);
  let 已失效 = false;
  let 訊息;
  const 模組 = {};
  插件.handleHotUpdate({
    file: 監看檔案[0].replaceAll("\\", "/"),
    server: { moduleGraph: {
      getModuleById: (id) => { assert.equal(id, 名稱); return 模組; },
      invalidateModule: (值) => { assert.equal(值, 模組); 已失效 = true; },
    }, ws: { send: (值) => { 訊息 = 值; } } },
  });
  assert.equal(已失效, true);
  assert.deepEqual(訊息, { type: "full-reload" });
});

test("正式開服基準、同版本間隔與小版本節點各自計算", () => {
  assert.equal(資料.elapsed_days, 276);
  assert.equal(資料.views.all.rows[0].lag_days, 526);
  assert.equal(資料.previous_comparable.patch, "7.15");
  assert.equal(資料.previous_comparable.lag_days, 553);
  assert.equal(資料.latest_comparable.lag_days, 490);
  assert.equal(資料.lag_reduction, 63);
  assert.equal(資料.views.all.gap_count, 13);
  assert.equal(資料.views.major.gap_count, 3);
  assert.deepEqual(資料.views.all.tc.map((列) => 列.patch), ["7.0", "7.01", "7.05", "7.1", "7.11", "7.15", "7.2"]);
  assert.equal(資料.views.all.international[0].patch, "7.38");
  assert.equal(資料.views.all.international[0].day, 資料.start_day);
  assert.equal(資料.views.all.international[0].carried, true);
});

test("只有開服版本時不虛構前版或間隔變化", () => {
  const 開服設定 = 複製設定();
  開服設定.patches = 開服設定.patches.slice(0, 1);
  開服設定.verified_through = 開服設定.launch_date;
  const 開服資料 = 建置版本進度(開服設定);
  assert.equal(開服資料.previous_comparable, null);
  assert.equal(開服資料.latest_comparable.patch, "7.0");
  assert.equal(開服資料.latest_comparable.lag_days, 526);
  assert.equal(開服資料.lag_reduction, null);
  assert.equal(開服資料.views.all.forecast.status, "insufficient");
});

test("完整推測延伸至移動中的國際服，兩種範圍共用日期且不改寫歷史", () => {
  const 小版 = 資料.views.all.forecast;
  const 主版 = 資料.views.major.forecast;
  assert.equal(小版.next.patch, "7.25");
  assert.equal(小版.next.date, "2026-09-29");
  assert.equal(小版.next.planned, true);
  assert.equal(主版.next.patch, "7.3");
  assert.equal(主版.next.date, "2026-11-03");
  assert.equal(小版.tc_cycle_days, 100);
  assert.equal(小版.tc_historical_cycle_days, 115);
  assert.equal(小版.international_cycle_days, 133);
  assert.ok(小版.catch_up.day > 主版.catch_up.day);
  for (const f of [小版, 主版]) {
    assert.equal(f.status, "estimated");
    assert.ok(f.rows.some((列) => 列.patch === "8.1"));
    assert.equal(f.tc.at(-1).day, f.synchronization_start.day);
    assert.ok(f.rows.some((列) => 列.patch === f.continuation_major.patch));
    assert.equal(f.plot_end_day, f.synchronization_start.day);
    assert.ok(f.international.at(-1).day <= f.plot_end_day);
    assert.equal(f.days_to_catch_up, f.catch_up.day - 資料.end_day);
    // 抵達今日的國際服 7.56 不算追上：當時國際服已繼續前進。
    assert.ok(f.catch_up.day > f.rows.find((列) => 列.patch === (f === 小版 ? "7.55" : "7.5")).tc_day);
    const 階段 = f.rows.filter((列) => !列.tc_version_omitted);
    for (const [i, 列] of 階段.entries()) {
      if (列.tc_day <= 資料.end_day || 列.tc_day >= f.catch_up.day || 列.tc_day === null) continue;
      assert.ok(列.tc_day >= 階段[i + 1].international_day, `不應略過更早交會：${列.patch}`);
    }
    assert.ok(f.fast_catch_up.day < f.catch_up.day);
    assert.ok(f.slow_catch_up.day > f.catch_up.day);
  }
  for (const 列 of 主版.rows) assert.equal(列.tc_day, 小版.rows.find((項) => 項.patch === 列.patch).tc_day);
  const 計畫列 = 小版.rows.find((列) => 列.patch === "8.0");
  assert.equal(計畫列.international_month, "2027-01");
  assert.equal(計畫列.international, null);
  assert.equal(計畫列.international_released, false);
  assert.equal(計畫列.international_day, 日序("2027-01-19"));
  assert.equal(資料.views.all.rows.find((列) => 列.patch === "7.21").tc_day, null);
  assert.equal(資料.views.all.rows.find((列) => 列.patch === "7.21").tc_duration, null);
  assert.equal(資料.current_international, "7.56");
  assert.equal(資料.current_tc, "7.2");
  assert.equal(資料.views.all.rows.length, 22);
  assert.equal(資料.views.all.gap_count, 13);
  const 修改前 = JSON.stringify(設定);
  建置版本進度(設定);
  assert.equal(JSON.stringify(設定), 修改前);
});

test("推測間隔包含活動預告與雙服估算，合併版留空且不改寫實際間隔", () => {
  const 小版 = 資料.views.all.forecast;
  for (const [patch, days, estimated] of [['7.2', 490, false], ['7.25', 490, true], ['7.3', 455, true],
    ['8.0', 217, true], ['8.5', 42, true], ['8.51', 35, true], ['8.56', 21, true], ['9.0', 0, true]]) {
    const 列 = 小版.rows.find((項) => 項.patch === patch);
    assert.equal(列.lag_days, days, patch);
    assert.equal(列.lag_estimated, estimated, patch);
  }
  for (const 列 of 小版.rows.filter((項) => 項.tc_version_omitted || 項.tc_forecast_skipped)) {
    assert.equal(列.lag_days, null);
    assert.equal(列.lag_estimated, false);
  }
  for (const 列 of 資料.views.major.forecast.rows) {
    assert.equal(列.lag_days, 小版.rows.find((項) => 項.patch === 列.patch).lag_days);
  }
  assert.equal(資料.views.all.rows.find((列) => 列.patch === '7.25').lag_days, null);
  assert.equal(資料.views.all.rows.find((列) => 列.patch === '7.3').lag_days, null);
  assert.equal(資料.latest_comparable.lag_days, 490);
  assert.equal(資料.lag_reduction, 63);
  // 正式公告日期的日曆差可確定，不能僅因尚未上線就標成模型推測。
  const 公告 = 複製設定();
  const 七二五 = 公告.patches.find((列) => 列.patch === '7.25');
  delete 七二五.tc_plan;
  七二五.tc = '2026-09-29'; 七二五.tc_source = 'tc_7_2';
  const 結果 = 建置版本進度(公告);
  const 公告列 = 結果.views.all.forecast.rows.find((列) => 列.patch === '7.25');
  assert.equal(公告列.lag_days, 490);
  assert.equal(公告列.lag_estimated, false);
  assert.equal(公告列.tc_released, false);
  assert.equal(結果.views.all.rows.find((列) => 列.patch === '7.25').lag_days, null);
});

test("推測時長改用下一個情境日期，群組守恆且末版只計至觀察終點", () => {
  for (const scope of ["all", "major"]) {
    const f = 資料.views[scope].forecast;
    const 七二 = f.groups.find((組) => 組.patch === "7.2");
    assert.equal(七二.tc_duration.days, 98);
    assert.equal(七二.tc_duration.estimated, true);
    assert.equal(七二.tc_duration.ongoing, false);
    for (const 地區 of ["international", "tc"]) {
      const 時長列 = f.rows.filter((列) => 列[`${地區}_duration`]);
      assert.equal(時長列.reduce((總和, 列) => 總和 + 列[`${地區}_duration`].days, 0), f.plot_end_day - 時長列[0][`${地區}_day`]);
      assert.equal(時長列.at(-1)[`${地區}_duration`].through_horizon, true);
      assert.equal(時長列.filter((列) => 列[`${地區}_duration`].through_horizon).length, 1);
      for (const [i, 列] of 時長列.entries()) {
        assert.ok(列[`${地區}_duration`].days >= 0);
        if (i) assert.ok(列[`${地區}_day`] >= 時長列[i - 1][`${地區}_day`]);
      }
      for (const 組 of f.groups) assert.equal(組[`${地區}_duration`]?.days ?? 0, 組.rows.reduce((總和, 列) => 總和 + (列[`${地區}_duration`]?.days ?? 0), 0));
    }
    const 末版 = f.rows.findLast((列) => 列.tc_duration);
    assert.equal(末版.tc_duration.days, f.plot_end_day - 末版.tc_day);
  }
  const 小版 = 資料.views.all.forecast;
  assert.equal(小版.rows.find((列) => 列.patch === "7.2").tc_duration.days, 63);
  assert.equal(資料.views.all.groups.find((組) => 組.patch === "7.2").tc_duration.days, 46);
  for (const patch of ["7.16", "7.18", "7.21"]) {
    assert.equal(小版.rows.find((列) => 列.patch === patch).tc_day, null);
    assert.equal(小版.rows.find((列) => 列.patch === patch).tc_duration, null);
    assert.equal(小版.stages.includes(patch), false);
  }
});

test("續列 8.5 時保留繁中 8.4 的 98 天週期及 8.45 時長，兩種篩選皆可選取", () => {
  const f = 資料.views.all.forecast;
  assert.equal(f.catch_up.patch, '8.45');
  assert.equal(f.catch_up.date, '2028-10-31');
  assert.deepEqual(f.continuation_major, {patch:'8.5', end_patch:'8.56', end_day:日序('2029-04-17'), international_date:'2028-11-14', tc_date:'2028-12-26', previous_major:'8.4', tc_cycle_days:98});
  for (const scope of ['all', 'major']) {
    const 視圖 = 資料.views[scope].forecast;
    assert.deepEqual(視圖.continuation_major, f.continuation_major);
    assert.equal(視圖.plot_end_date, '2029-07-31');
    const 下版 = 視圖.rows.find((列) => 列.patch === '8.5');
    assert.equal(下版.tc_day, 日序('2028-12-26'));
    assert.equal(下版.international_day, 日序('2028-11-14'));
    assert.equal(下版.tc, null);
    assert.equal(下版.tc_released, false);
    assert.equal(下版.tc_duration.days, scope === 'all' ? 28 : 217);
    assert.equal(下版.tc_duration.through_horizon, false);
    assert.ok(視圖.stages.includes('8.5'));
    assert.equal(正規化版本進度選取(資料, {patchScope:scope, patch:'8.5', guess:true}).patch, '8.5');
    assert.equal(正規化版本進度選取(資料, {patchScope:scope, patch:'8.5', guess:false}).patch, '7.2');
    assert.equal(視圖.groups.find((組) => 組.patch === '8.4').tc_duration.days, 98);
    assert.equal(視圖.groups.find((組) => 組.patch === '8.4').international_duration.days, 133);
    assert.equal(視圖.groups.find((組) => 組.patch === '8.5').international_duration.days, 259);
    assert.equal(視圖.groups.find((組) => 組.patch === '8.5').international_duration.through_horizon, false);
    assert.deepEqual(視圖.groups.find((組) => 組.patch === '8.5').duration_outlook, {international:'unknown', tc:'may_synchronize'});
    assert.equal(視圖.groups.find((組) => 組.patch === '8.4').duration_outlook, null);
  }
  assert.equal(f.rows.find((列) => 列.patch === '8.4').tc_duration.days, 42);
  assert.equal(f.rows.find((列) => 列.patch === '8.45').tc_day, 日序('2028-10-31'));
  assert.equal(f.rows.find((列) => 列.patch === '8.45').tc_duration.days, 56);
  assert.equal(f.rows.find((列) => 列.patch === '8.45').international_duration.days, 77);
  // 延長觀察範圍後，國際服已推出的 8.51 仍需列入，不能停在較早的 8.5 日期。
  const 後續小版 = f.rows.find((列) => 列.patch === '8.51');
  assert.equal(後續小版.international_day, 日序('2028-12-19'));
  assert.equal(後續小版.international_duration.days, 56);
  assert.equal(後續小版.tc_forecast_skipped, false);
  assert.equal(後續小版.tc_day, 日序('2029-01-23'));
  assert.equal(後續小版.tc_duration.days, 49);
  assert.equal(f.international.at(-1).patch, '9.0');
  // 主要版本的首次相同時間仍在 8.3，觀察終點不改寫首次交會。
  assert.equal(資料.views.major.forecast.catch_up.patch, '8.3');
  assert.equal(資料.views.all.rows.some((列) => 列.patch === '8.5'), false);
});

test("8.51、8.55、8.56 保留獨立繁中預測日期與分享選取", () => {
  const f = 資料.views.all.forecast;
  const 五五 = f.rows.find((列) => 列.patch === '8.55');
  const 五六 = f.rows.find((列) => 列.patch === '8.56');
  assert.equal(五五.international_day, 日序('2029-02-13'));
  assert.equal(五五.tc_day, 日序('2029-03-13'));
  assert.equal(五五.tc_duration.days, 35);
  assert.equal(五五.tc_duration.through_horizon, false);
  assert.equal(五六.international_day, 日序('2029-03-27'));
  assert.equal(五六.tc_forecast_skipped, false);
  assert.equal(五六.tc_day, 日序('2029-04-17'));
  assert.equal(五六.tc_duration.days, 105);
  assert.deepEqual(f.groups.find((組) => 組.patch === '8.5').rows.map((列) => 列.patch), ['8.5', '8.51', '8.55', '8.56']);
  for (const patch of ['8.51', '8.55', '8.56']) {
    assert.ok(f.stages.includes(patch));
    assert.equal(正規化版本進度選取(資料, {patch, guess:true}).patch, patch);
    assert.equal(正規化版本進度選取(資料, {patch, guess:true, patchScope:'major'}).patch, '8.5');
    assert.equal(正規化版本進度選取(資料, {patch, guess:false}).patch, '7.2');
    assert.equal(資料.views.all.rows.some((列) => 列.patch === patch), false);
  }
  assert.equal(f.rows.some((列) => 列.patch === '9.0'), true);
  assert.equal(f.rows.some((列) => 列.patch === '9.01'), false);
  assert.equal(資料.views.all.groups.some((組) => 組.duration_outlook), false);
});

test("9.0 自然同日改版才標示可能開始同步，兩種範圍共用終點", () => {
  for (const scope of ['all', 'major']) {
    const f = 資料.views[scope].forecast;
    assert.deepEqual(f.synchronization_start, {patch:'9.0', day:日序('2029-07-31'), date:'2029-07-31'});
    const 九零 = f.rows.find((列) => 列.patch === '9.0');
    assert.equal(九零.tc_day, 九零.international_day);
    assert.equal(九零.tc_sync_candidate, true);
    assert.equal(九零.tc_released, false);
    assert.equal(九零.tc, null);
    assert.deepEqual(f.rows.filter((列) => 列.tc_sync_candidate).map((列) => 列.patch), ['9.0']);
    assert.equal(f.tc.at(-1).patch, '9.0');
    assert.equal(f.international.at(-1).patch, '9.0');
    assert.deepEqual(f.groups.at(-1).duration_outlook, {international:'unknown', tc:'may_synchronize'});
    assert.equal(正規化版本進度選取(資料, {patch:'9.0', patchScope:scope, guess:true}).patch, '9.0');
    assert.equal(正規化版本進度選取(資料, {patch:'9.0', patchScope:scope, guess:false}).patch, '7.2');
  }
});

test("同步候選不覆寫 9.0 的公告或預告日期", () => {
  for (const 預告 of [true, false]) {
    const 值 = 複製設定(); delete 值.international_plans;
    // 合成未來國際公告及延後一週的繁中 9.0，確認同步提示跟著排程重新判定。
    值.patches.push(...資料.views.all.forecast.rows.filter((列) => Number(列.patch.split('.')[0]) >= 8).map((列) => ({
      patch:列.patch, major:列.major, title:'測試未來公告', international:new Date(列.international_day * 86400000).toISOString().slice(0, 10), tc:null,
    })));
    const 九零 = 值.patches.find((列) => 列.patch === '9.0');
    if (預告) 九零.tc_plan = {date:'2029-08-07', attribution:'測試活動預告'};
    else { 九零.tc = '2029-08-07'; 九零.tc_source = 'tc_7_2'; }
    for (const 視圖 of Object.values(建置版本進度(值).views)) {
      const 列 = 視圖.forecast.rows.find((項) => 項.patch === '9.0');
      assert.equal(列.tc_day, 日序('2029-08-07'));
      assert.equal(列.tc_sync_candidate, false);
      assert.notEqual(視圖.forecast.synchronization_start?.patch, '9.0');
    }
  }
});

test("延伸下一主版仍保留公告或預告日期，不套用一般週期覆寫", () => {
  for (const 預告 of [true, false]) {
    const 值 = 複製設定(); delete 值.international_plans;
    // 將未來情境轉為測試用的國際公告，再明確設定繁中 8.5 日期。
    // 這些合成日期僅存在測試副本，不回寫正式設定或歷史來源。
    值.patches.push(...資料.views.all.forecast.rows.filter((列) => Number(列.patch.split('.')[0]) === 8).map((列) => ({
      patch:列.patch, major:列.major, title:'測試未來公告', international:new Date(列.international_day * 86400000).toISOString().slice(0, 10), tc:null,
    })));
    const 下版 = 值.patches.find((列) => 列.patch === '8.5');
    if (預告) 下版.tc_plan = {date:'2028-12-05', attribution:'測試活動預告'};
    else { 下版.tc = '2028-12-05'; 下版.tc_source = 'tc_7_2'; }
    const 結果 = 建置版本進度(值);
    assert.equal(結果.views.all.forecast.continuation_major.tc_date, '2028-12-05');
    assert.equal(結果.views.all.forecast.rows.find((列) => 列.patch === '8.5').tc_day, 日序('2028-12-05'));
    const 原列 = 結果.views.all.rows.find((列) => 列.patch === '8.5');
    assert.equal(預告 ? 原列.tc_plan.date : 原列.tc, '2028-12-05');
  }
});

test("已過估算不每日後移，公告優先但仍繼續推算其後版本", () => {
  const 過期 = 複製設定();
  過期.verified_through = "2026-10-20";
  const 過期結果 = 建置版本進度(過期).views.all.forecast;
  assert.equal(過期結果.next.date, 資料.views.all.forecast.next.date);
  assert.equal(過期結果.next.overdue, true);
  const 公告 = 獨立小版情境設定();
  const 下版 = 公告.patches.find((列) => 列.patch === "7.21");
  下版.tc = "2026-10-13";
  delete 下版.merged_into;
  const f = 建置版本進度(公告).views.all.forecast;
  assert.equal(f.next.announced, true);
  assert.equal(f.next.date, "2026-10-13");
  assert.ok(f.rows.find((列) => 列.patch === "7.25").tc_day > 日序("2026-10-13"));
  assert.ok(f.catch_up);
  const 不足 = 複製設定();
  不足.patches = 不足.patches.slice(0, 3);
  不足.patches[2].tc = null;
  assert.equal(建置版本進度(不足).views.all.forecast.status, "insufficient");
});

test("更新頻率與官方月份會改變推測；較慢模型不保證追上", () => {
  const 國際變更 = 獨立小版情境設定();
  國際變更.patches.find((列) => 列.patch === "7.21").international = "2025-04-29";
  assert.equal(建置版本進度(國際變更).views.all.forecast.next.date, "2026-10-06");
  const 繁中變更 = 獨立小版情境設定();
  繁中變更.patches.find((列) => 列.patch === "7.05").tc = "2026-03-17";
  assert.equal(建置版本進度(繁中變更).views.all.forecast.next.date, "2026-10-06");
  assert.equal(建置版本進度(繁中變更).views.major.forecast.next.date, "2026-11-20");
  const 月份變更 = 複製設定();
  月份變更.international_plans[0].month = "2027-03";
  assert.notEqual(建置版本進度(月份變更).views.all.forecast.catch_up.date, 資料.views.all.forecast.catch_up.date);
  const 慢速 = 獨立小版情境設定();
  for (const 列 of 慢速.patches) {
    if (列.tc) 列.tc = new Date((日序(慢速.launch_date) + 2 * (日序(列.tc) - 日序(慢速.launch_date))) * 86400000).toISOString().slice(0, 10);
  }
  慢速.verified_through = "2027-04-01";
  const 慢速結果 = 建置版本進度(慢速).views.all.forecast;
  assert.equal(慢速結果.status, "no_catch_up");
  assert.equal(慢速結果.catch_up, null);
  assert.equal(慢速結果.continuation_major, null);
  assert.equal(慢速結果.synchronization_start, null);
  assert.equal(慢速結果.days_to_catch_up, null);
  assert.ok(慢速結果.rows.length < 600);
});

test("月份排程驗證格式、來源與順序；沒有月份排程的舊資料仍可建置", () => {
  for (const 變更 of [
    (值) => { 值.international_plans[0].month = "2027-13"; },
    (值) => { 值.international_plans[0].month = "2026-01"; },
    (值) => { 值.international_plans[0].patch = "7.0"; },
    (值) => { 值.international_plans[0].source = "missing"; },
    (值) => { 值.international_plans.push({ ...值.international_plans[0] }); },
  ]) {
    const 值 = 複製設定();
    變更(值);
    assert.throws(() => 建置版本進度(值));
  }
  const 舊資料 = 複製設定();
  delete 舊資料.international_plans;
  assert.deepEqual(建置版本進度(舊資料).international_plans, []);
  assert.equal(建置版本進度(舊資料).views.all.forecast.status, "estimated");
});

test("記者會暨玩家見面會預告作為固定日期，可能跳版只影響繁中預測並保留國際節點", () => {
  const f = 資料.views.all.forecast;
  assert.deepEqual(f.tc.slice(0, 5).map((點) => 點.patch), ["7.2", "7.25", "7.3", "7.35", "7.4"]);
  assert.equal(f.rows.find((列) => 列.patch === "7.25").tc_day, 日序("2026-09-29"));
  assert.equal(f.rows.find((列) => 列.patch === "7.25").tc_estimated, false);
  assert.equal(f.tc.find((點) => 點.patch === "7.25").planned, true);
  assert.deepEqual(f.skipped_patches, ["7.31", "7.38", "7.41", "7.56", "8.16", "8.18", "8.21", "8.31", "8.38", "8.41"]);
  for (const patch of ["7.31", "7.38", "7.41", "7.56"]) {
    const 列 = f.rows.find((項) => 項.patch === patch);
    assert.equal(列.tc_forecast_skipped, true);
    assert.equal(列.tc_day, null);
    assert.equal(列.tc_duration, null);
    assert.ok(列.international_duration);
    assert.ok(f.stages.includes(patch));
    assert.equal(資料.views.all.rows.find((項) => 項.patch === patch).tc_version_omitted, undefined);
    assert.ok(資料.views.all.stages.includes(patch));
  }
  assert.equal(f.rows.find((列) => 列.patch === "7.25").tc_duration.days, 35);
  assert.equal(f.rows.find((列) => 列.patch === "7.3").tc_duration.days, 49);
  assert.equal(f.rows.find((列) => 列.patch === "7.35").tc_duration.days, 49);
  assert.equal(f.rows.find((列) => 列.patch === "8.31").tc_day, null);
  const 改預告 = 複製設定();
  改預告.patches.find((列) => 列.patch === "7.25").tc_plan.date = "2026-10-05";
  const 改結果 = 建置版本進度(改預告).views.all.forecast;
  assert.equal(改結果.next.date, "2026-10-05");
  assert.equal(改結果.rows.find((列) => 列.patch === "7.2").tc_duration.days, 69);
  assert.equal(改結果.groups.find((組) => 組.patch === "7.2").tc_duration.days, 98);
});

test("約百天主版週期與週二更新適用所有推測日期，合併小版仍維持總時長", () => {
  const f = 資料.views.all.forecast;
  assert.equal(f.tc_cycle_source, "scenario");
  assert.equal(f.tc_typical_cycle_days, 98);
  const 日期列 = f.rows.filter((列) => 列.tc_day !== null && 列.tc_duration);
  for (const [i, 列] of 日期列.entries()) {
    if (i) assert.ok(列.tc_day > 日期列[i - 1].tc_day, `${列.patch} 必須維持獨立更新次序`);
    if (!列.tc_estimated) continue;
    assert.equal(new Date(列.tc_day * 86400000).getUTCDay(), 2, `${列.patch} 應在星期二`);
    assert.ok(列.tc_day >= 列.international_day, `${列.patch} 不得早於國際服`);
  }
  for (const 組 of f.groups.filter((組) => 組.tc_duration?.estimated && !組.tc_duration.through_horizon)) {
    // 8.5 必須等國際新資料片推出；一般主版仍維持 98 天，不提前壓縮以求同步。
    assert.equal(組.tc_duration.days, 組.patch === '8.5' ? 217 : 98, `${組.patch} 應保留一般週期或等待國際資料片的間隔`);
  }
  assert.deepEqual(f.tc.filter((點) => ['7.4', '7.41', '7.45', '7.5', '7.51', '7.55', '7.56', '8.0'].includes(點.patch)).map((點) => 點.patch),
    ['7.4', '7.45', '7.5', '7.51', '7.55', '8.0']);
  assert.equal(f.rows.find((列) => 列.patch === '8.41').tc_day, null);
  // 使用者更正後的記者會暨玩家見面會預告為星期二，仍以預告日期作為固定排程依據。
  assert.equal(new Date(f.rows.find((列) => 列.patch === '7.25').tc_day * 86400000).getUTCDay(), 2);
  for (const 視圖 of Object.values(資料.views)) {
    for (const 交點 of [視圖.forecast.catch_up, 視圖.forecast.fast_catch_up, 視圖.forecast.slow_catch_up]) {
      assert.equal(new Date(交點.day * 86400000).getUTCDay(), 2);
    }
  }
});

test("週二對齊保留公告日期，固定日期之間不足一週時不捏造更新日", () => {
  const 值 = 複製設定();
  const 主版 = 值.patches.find((列) => 列.patch === '7.3');
  主版.tc = '2026-10-14'; // 週三的假設公告，必須保持原值。
  delete 主版.merged_into;
  const 小版 = 值.patches.find((列) => 列.patch === '7.25');
  delete 小版.tc_plan;
  const 結果 = 建置版本進度(值).views.all.forecast;
  assert.equal(結果.rows.find((列) => 列.patch === '7.3').tc_day, 日序('2026-10-14'));
  assert.equal(結果.rows.find((列) => 列.patch === '7.25').tc_day, 日序('2026-10-13'));
  // 7.2 固定週二上線；若要求兩天後的 7.25 之前再排 7.21，沒有另一個週二可用。
  delete 值.patches.find((列) => 列.patch === '7.21').tc_version_omitted;
  小版.tc_plan = { date: '2026-07-30', attribution: '測試預告' };
  assert.throws(() => 建置版本進度(值), /沒有足夠的更新日/);
});

test("排程規則驗證完整型別，舊設定仍可依歷史節奏推算", () => {
  for (const 規則 of [null, {}, {tc_main_cycle_days: 0, tc_update_weekday: 2},
    {tc_main_cycle_days: 100.5, tc_update_weekday: 2}, {tc_main_cycle_days: '100', tc_update_weekday: 2},
    {tc_main_cycle_days: 100, tc_update_weekday: 7}, {tc_main_cycle_days: 100, tc_update_weekday: null}]) {
    const 值 = 複製設定(); 值.forecast_policy = 規則;
    assert.throws(() => 建置版本進度(值), /推測規則/);
  }
  const 舊值 = 複製設定(); delete 舊值.forecast_policy;
  const 舊結果 = 建置版本進度(舊值).views.all.forecast;
  assert.equal(舊結果.tc_cycle_source, 'history');
  assert.equal(舊結果.tc_cycle_days, 115);
  assert.equal(舊結果.tc_update_weekday, null);
});

test("國際資料片上市後兩週與四週開小版，不隨一般主版週期縮放", () => {
  const 檢查上市 = (f) => {
    const 零 = f.rows.find((列) => 列.patch === '8.0');
    assert.equal(f.rows.find((列) => 列.patch === '8.01').international_day - 零.international_day, 14);
    assert.equal(f.rows.find((列) => 列.patch === '8.05').international_day - 零.international_day, 28);
    assert.equal(零.international_month, '2027-01');
    assert.equal(零.international, null);
  };
  檢查上市(資料.views.all.forecast);
  const 不同週期 = 複製設定();
  不同週期.patches.find((列) => 列.patch === '7.3').international = '2025-08-12';
  不同週期.patches.find((列) => 列.patch === '7.5').international = '2026-05-12';
  const 變更後 = 建置版本進度(不同週期).views.all.forecast;
  assert.equal(變更後.international_cycle_days, 140);
  檢查上市(變更後);
  const 規律 = 資料.views.all.forecast.international_cadence;
  assert.deepEqual(規律.minor_offsets.find((列) => 列.suffix === '01').samples.map((項) => 項.days), [14, 14, 14, 14, 14]);
  assert.deepEqual(規律.minor_offsets.find((列) => 列.suffix === '05').samples.map((項) => 項.days), [28, 28, 28, 28, 28]);
});

test("國際小版依同編號樣本取整週，歷史樣本與未來推測分開", () => {
  const f = 資料.views.all.forecast;
  const 規律 = f.international_cadence;
  for (const [suffix, days] of [['11', 14], ['15', 42], ['21', 21], ['25', 56], ['31', 28], ['35', 63], ['38', 91], ['41', 35], ['45', 56]]) {
    assert.equal(規律.minor_offsets.find((列) => 列.suffix === suffix).days, days);
    // x.15 的歷史中位數仍為 42 天；8.0 起本次情境改採 .11 後 21 天，即主版後 35 天。
    assert.equal(f.rows.find((列) => 列.patch === `8.${suffix}`).international_day - f.rows.find((列) => 列.patch === `8.${suffix[0]}`).international_day, suffix === '15' ? 35 : days);
  }
  for (const [i, 列] of f.rows.entries()) {
    if (i) assert.ok(列.international_day > f.rows[i - 1].international_day);
    if (列.international_estimated) assert.equal(new Date(列.international_day * 86400000).getUTCDay(), 2);
  }
  assert.ok(規律.minor_offsets.every((列) => 列.samples.every((項) => Number(項.patch) < 8)));
  assert.ok(資料.views.all.rows.every((列) => Number(列.patch) >= 7));
  assert.equal(資料.views.all.gap_count, 13);
  assert.equal(資料.latest_comparable.lag_days, 490);
  // 月份公告即使改變，也不回寫已核對的 7.x 日期。
  const 改月份 = 複製設定(); 改月份.international_plans[0].month = '2027-02';
  const 改後 = 建置版本進度(改月份);
  assert.deepEqual(改後.views.all.rows, 資料.views.all.rows);
  const 月零 = 改後.views.all.forecast.rows.find((列) => 列.patch === '8.0');
  assert.ok(月零.international_day >= 日序('2027-02-01') && 月零.international_day <= 日序('2027-02-28'));
});

test("兩服從 8.0 起固定前期小版時長，主版快慢情境不壓縮兩週與三週間隔", () => {
  for (const 週期 of [93, 100, 107, 300]) {
    const 值 = 複製設定(); 值.forecast_policy.tc_main_cycle_days = 週期;
    const f = 建置版本進度(值).views.all.forecast;
    for (const 代 of [8, ...(週期 === 300 ? [9] : [])]) {
      for (const [from, to, days] of [['0', '01', 14], ['01', '05', 14], ['1', '11', 14], ['11', '15', 21]]) {
        const 前 = f.rows.find((列) => 列.patch === `${代}.${from}`);
        const 後 = f.rows.find((列) => 列.patch === `${代}.${to}`);
        for (const 地區 of ['tc', 'international']) {
          assert.equal(後[`${地區}_day`] - 前[`${地區}_day`], days, `${週期} 天情境的 ${地區} ${前.patch} 時長`);
          assert.equal(前[`${地區}_duration`].days, days);
          assert.equal(new Date(後[`${地區}_day`] * 86400000).getUTCDay(), 2);
        }
      }
    }
  }
  const f = 資料.views.all.forecast;
  const 取列 = (patch) => f.rows.find((列) => 列.patch === patch);
  assert.equal(取列('8.01').tc_day, 日序('2027-09-07'));
  assert.equal(取列('8.05').tc_day, 日序('2027-09-21'));
  assert.equal(取列('8.11').tc_day, 日序('2027-12-14'));
  assert.equal(取列('8.15').tc_day, 日序('2028-01-04'));
  assert.equal(取列('8.15').international_day, 日序('2027-07-06'));
  assert.equal(取列('8.05').tc_duration.days, 70);
  assert.equal(取列('8.15').tc_duration.days, 63);
  assert.equal(f.groups.find((組) => 組.patch === '8.0').tc_duration.days, 98);
  assert.equal(f.groups.find((組) => 組.patch === '8.1').tc_duration.days, 98);
  const 舊 = 複製設定(); delete 舊.forecast_policy.shared_minor_intervals;
  const 舊資料 = 建置版本進度(舊);
  assert.deepEqual(資料.views.all.rows, 舊資料.views.all.rows);
  assert.deepEqual(f.international_cadence, 舊資料.views.all.forecast.international_cadence);
  assert.equal(舊資料.views.all.forecast.rows.find((列) => 列.patch === '8.0').tc_duration.days, 7);
  assert.equal(舊資料.views.all.forecast.rows.find((列) => 列.patch === '8.11').international_duration.days, 28);
});

test("固定小版間隔仍尊重正式日期與活動預告，後續日期改從公告起算", () => {
  // 假設未來公告刻意延後 .01：公告優先，.05 再從各服自己的 .01 起算兩週。
  const 值 = 複製設定(); delete 值.international_plans;
  值.patches.push(
    {patch:'8.0', major:true, title:'測試資料片', international:'2027-01-19', tc:'2027-08-24', tc_source:'tc_7_2'},
    {patch:'8.01', major:false, title:'測試小版', international:'2027-02-09', tc:null, tc_plan:{date:'2027-09-14', attribution:'測試活動預告'}},
    {patch:'8.05', major:false, title:'測試小版', international:'2027-02-23', tc:null},
  );
  const f = 建置版本進度(值).views.all.forecast;
  const 取列 = (patch) => f.rows.find((列) => 列.patch === patch);
  assert.equal(取列('8.01').international_day, 日序('2027-02-09'));
  assert.equal(取列('8.01').tc_day, 日序('2027-09-14'));
  assert.equal(取列('8.01').tc_estimated, false);
  assert.equal(取列('8.05').tc_day, 日序('2027-09-28'));
  assert.equal(取列('8.05').tc_estimated, true);
  assert.equal(取列('8.0').tc_duration.days, 21);
  assert.equal(取列('8.01').tc_duration.days, 14);
});

test("固定小版間隔驗證型別、順序與整週，衝突時不悄悄縮短", () => {
  for (const 變更 of [
    (值) => { 值.shared_minor_intervals = null; },
    (值) => { 值.shared_minor_intervals.from_expansion = '8'; },
    (值) => { 值.shared_minor_intervals.from_expansion = 0; },
    (值) => { 值.shared_minor_intervals.steps = []; },
    (值) => { 值.shared_minor_intervals.steps[0].from = 0; },
    (值) => { 值.shared_minor_intervals.steps[0].to = '1'; },
    (值) => { 值.shared_minor_intervals.steps[0].to = '11'; },
    (值) => { 值.shared_minor_intervals.steps[0].days = 15; },
    (值) => { 值.shared_minor_intervals.steps[0].days = '14'; },
    (值) => { 值.shared_minor_intervals.steps[0].days = 0; },
    (值) => { 值.shared_minor_intervals.steps[1].to = '01'; },
    (值) => { 值.shared_minor_intervals.steps.push({...值.shared_minor_intervals.steps[0]}); },
    (值) => { 值.shared_minor_intervals.steps[0].days = 140; },
  ]) {
    const 值 = 複製設定(); 變更(值.forecast_policy);
    assert.throws(() => 建置版本進度(值), /固定小版間隔/);
  }
});

test("資料片前空窗獨立估算，長期模板仍保留未指定略過的小版", () => {
  const 慢 = 複製設定(); 慢.forecast_policy.tc_main_cycle_days = 300;
  const f = 建置版本進度(慢).views.all.forecast;
  const 規律 = f.international_cadence;
  assert.equal(規律.expansion_cycle_days, 259);
  assert.deepEqual(規律.expansion_samples.map((列) => 列.days), [238, 273]);
  assert.equal(f.rows.find((列) => 列.patch === '9.0').international_day - f.rows.find((列) => 列.patch === '8.5').international_day, 259);
  assert.equal(f.rows.find((列) => 列.patch === '9.01').international_day - f.rows.find((列) => 列.patch === '9.0').international_day, 14);
  for (const patch of ['9.16', '9.18', '9.21', '9.31', '9.38', '9.41', '9.51', '9.56']) {
    assert.equal(f.rows.find((列) => 列.patch === patch).tc_forecast_skipped, false);
    assert.equal(f.rows.find((列) => 列.patch === patch).tc_estimated, true);
  }
  // 歷代存在的修正版號不等於未來必定推出，延伸仍使用最新已收錄結構。
  assert.equal(f.rows.some((列) => ['8.08', '8.28', '8.48', '8.58'].includes(列.patch)), false);
  assert.equal(f.rows.find((列) => 列.patch === '7.56').tc_forecast_skipped, true);
});

test("8.x 合併假設保留國際節點、重算繁中時長，較慢情境也套用末期小版", () => {
  // 慢速情境也沿用相同合併假設；8.51／8.56 已恢復獨立更新。
  const 慢 = 複製設定(); 慢.forecast_policy.tc_main_cycle_days = 300;
  const f = 建置版本進度(慢).views.all.forecast;
  for (const patch of ['8.16', '8.18', '8.21', '8.31', '8.38', '8.41']) {
    const 列 = f.rows.find((項) => 項.patch === patch);
    assert.equal(列.tc_forecast_skipped, true);
    assert.equal(列.tc_version_omitted, undefined);
    assert.equal(列.tc_day, null);
    assert.equal(列.tc_duration, null);
    assert.equal(列.tc_estimated, false);
    assert.equal(列.tc_released, false);
    assert.ok(列.international_duration);
    assert.ok(f.stages.includes(patch));
    assert.ok(f.international.some((點) => 點.patch === patch));
    assert.equal(f.tc.some((點) => 點.patch === patch), false);
  }
  const 獨立 = 複製設定(); delete 獨立.forecast_policy.tc_skipped_patches;
  const 前 = 建置版本進度(獨立);
  assert.deepEqual(資料.views.all.rows, 前.views.all.rows);
  const 後 = 資料.views.all.forecast;
  for (const 列 of 後.rows) {
    const 原列 = 前.views.all.forecast.rows.find((項) => 項.patch === 列.patch);
    if (原列) assert.equal(列.international_day, 原列.international_day);
  }
  const 八一五 = 後.rows.find((列) => 列.patch === '8.15');
  assert.equal(八一五.tc_duration.days, 後.rows.find((列) => 列.patch === '8.2').tc_day - 八一五.tc_day);
  assert.ok(八一五.tc_duration.days > 前.views.all.forecast.rows.find((列) => 列.patch === '8.15').tc_duration.days);
  assert.equal(後.groups.find((組) => 組.patch === '8.1').tc_duration.days, 98);
  assert.equal(後.groups.find((組) => 組.patch === '8.1').tc_duration.days,
    前.views.all.forecast.groups.find((組) => 組.patch === '8.1').tc_duration.days);
  assert.ok(後.tc.some((點) => 點.patch === '8.35'));
  assert.ok(後.tc.some((點) => 點.patch === '8.45'));
  assert.equal(正規化版本進度選取(資料, { patch: '8.16', guess: true }).patch, '8.16');
});

test("情境跳版清單拒絕型別錯誤、重複、主版與公告衝突，省略欄位仍保留獨立更新", () => {
  for (const 清單 of [null, '8.16', [8.16], ['8.16', '8.16'], ['8.1'], ['8.16a'], ['7.01'], ['7.25'], ['7.21']]) {
    const 值 = 複製設定(); 值.forecast_policy.tc_skipped_patches = 清單;
    assert.throws(() => 建置版本進度(值), /推測跳版/);
  }
  const 舊 = 複製設定(); delete 舊.forecast_policy.tc_skipped_patches;
  const 結果 = 建置版本進度(舊).views.all.forecast;
  assert.deepEqual(結果.skipped_patches, ['7.31', '7.38', '7.41', '7.56']);
  assert.ok(結果.rows.find((列) => 列.patch === '8.16').tc_day);
  assert.ok(結果.rows.find((列) => 列.patch === '8.41').tc_day);
});

test("國際歷史樣本拒絕錯誤日期、重複版本及無來源，缺省時仍可建置", () => {
  for (const 變更 of [
    (值) => { 值.international_history = null; },
    (值) => { 值.international_history.patches = []; },
    (值) => { 值.international_history.source = 'missing'; },
    (值) => { 值.international_history.patches[0].date = '2015-02-29'; },
    (值) => { 值.international_history.patches[0].date = '2030-01-01'; },
    (值) => { 值.international_history.patches[0].patch = '7.0'; },
    (值) => { 值.international_history.patches[0].patch = '3.01'; },
    (值) => { 值.international_history.patches[0].patch = '3.01a'; },
    (值) => { 值.international_history.patches.reverse(); },
  ]) {
    const 值 = 複製設定(); 變更(值);
    assert.throws(() => 建置版本進度(值));
  }
  const 舊 = 複製設定(); delete 舊.international_history;
  const 結果 = 建置版本進度(舊).views.all.forecast;
  assert.equal(結果.international_cadence.source_url, null);
  assert.equal(結果.international_cadence.expansion_cycle_days, null);
  assert.equal(結果.rows.find((列) => 列.patch === '8.01').international_day - 結果.rows.find((列) => 列.patch === '8.0').international_day, 14);
});

test("預告日期經過也不自動當成已上線，正式核對後才改變歷史時長", () => {
  const 值 = 複製設定();
  值.verified_through = "2026-09-29";
  const 待核對 = 建置版本進度(值);
  assert.equal(待核對.current_tc, "7.2");
  assert.equal(待核對.views.all.rows.find((列) => 列.patch === "7.25").tc_released, false);
  assert.equal(待核對.views.all.rows.find((列) => 列.patch === "7.25").tc_duration, null);
  assert.equal(待核對.views.all.forecast.next.overdue, true);
  assert.equal(待核對.latest_comparable.patch, "7.2");
  const 列 = 值.patches.find((項) => 項.patch === "7.25");
  列.tc = 列.tc_plan.date;
  列.tc_source = "tc_7_2";
  delete 列.tc_plan;
  const 已核對 = 建置版本進度(值);
  assert.equal(已核對.current_tc, "7.25");
  assert.equal(已核對.views.all.rows.find((項) => 項.patch === "7.2").tc_duration.days, 63);
});

test("預告及跳版設定拒絕無歸因、錯誤來源、倒序與互斥狀態", () => {
  for (const 變更 of [
    (列) => { 列.tc_plan.date = "2026-09-31"; },
    (列) => { 列.tc_plan.date = "2026-06-01"; },
    (列) => { 列.tc_plan.attribution = ""; },
    (列) => { 列.tc_plan.source = "missing"; },
    (列) => { 列.tc_plan.source = false; },
    (列) => { 列.tc = "2026-09-29"; },
    (列) => { 列.tc_forecast_skip = true; },
    (列) => { 列.tc_forecast_skip = "true"; },
  ]) {
    const 值 = 複製設定();
    變更(值.patches.find((列) => 列.patch === "7.25"));
    assert.throws(() => 建置版本進度(值));
  }
  const 主版 = 複製設定();
  主版.patches.find((列) => 列.patch === "7.3").tc_forecast_skip = true;
  assert.throws(() => 建置版本進度(主版));
});

test("核對到新主版後不補造較早缺漏的小版；後續月份公告不跳過中間主版", () => {
  const 新版 = 複製設定();
  新版.verified_through = "2026-12-02";
  const 列 = 新版.patches.find((項) => 項.patch === "7.3");
  列.tc = "2026-12-01";
  delete 列.merged_into;
  const 結果 = 建置版本進度(新版).views.all.forecast;
  assert.equal(結果.next.patch, "7.35");
  for (const patch of ["7.21", "7.25"]) assert.equal(結果.rows.find((項) => 項.patch === patch).tc_day, null);
  const 多個預定 = 複製設定();
  // 放慢繁中以保留檢查範圍；快速情境可能在 8.5 之前已追上而截斷視圖。
  多個預定.forecast_policy.tc_main_cycle_days = 200;
  多個預定.international_plans.push({ patch: "9.0", title: "測試月份", month: "2030-03", source: "international_8_0_plan" });
  const 多個結果 = 建置版本進度(多個預定).views.all.forecast;
  for (const patch of ["8.1", "8.2", "8.3", "8.4", "8.5"]) assert.ok(多個結果.rows.some((項) => 項.patch === patch));
});

test("日期驗證拒絕不存在日期；閏年與跨年依日曆日計算", () => {
  assert.equal(日序("2024-03-01") - 日序("2024-02-28"), 2);
  assert.equal(日序("2026-01-01") - 日序("2025-12-31"), 1);
  for (const 日期 of ["2025-02-29", "2026-13-01", "2026-2-01", null]) assert.throws(() => 日序(日期));
});

test("版本時長依各服獨立更新日計算，合併版本與未公告版本不虛構時長", () => {
  const 取列 = (版本) => 資料.views.all.rows.find((列) => 列.patch === 版本);
  assert.deepEqual(取列("7.0").international_duration, { days: 14, ongoing: false });
  assert.deepEqual(取列("7.0").tc_duration, { days: 62, ongoing: false });
  // 圖表已省略 7.16、7.18，但國際服 7.15 仍在 7.16 上線時結束。
  assert.deepEqual(取列("7.15").international_duration, { days: 35, ongoing: false });
  assert.deepEqual(取列("7.15").tc_duration, { days: 35, ongoing: false });
  assert.deepEqual(取列("7.16").international_duration, { days: 35, ongoing: false });
  assert.deepEqual(取列("7.18").international_duration, { days: 28, ongoing: false });
  for (const 版本 of ["7.16", "7.18", "7.21", "7.3", "7.56"]) assert.equal(取列(版本).tc_duration, null);
  assert.deepEqual(取列("7.2").tc_duration, { days: 46, ongoing: true });
  assert.deepEqual(取列("7.56").international_duration, { days: 4, ongoing: true });
});

test("主要版本時長涵蓋主版週期，兩種範圍的時長總和均無重複或缺漏", () => {
  const 取列 = (版本) => 資料.views.major.rows.find((列) => 列.patch === 版本);
  assert.deepEqual(取列("7.0").international_duration, { days: 133, ongoing: false });
  assert.deepEqual(取列("7.0").tc_duration, { days: 132, ongoing: false });
  assert.deepEqual(取列("7.1").tc_duration, { days: 98, ongoing: false });
  assert.deepEqual(取列("7.5").international_duration, { days: 137, ongoing: true });
  for (const 視圖 of Object.values(資料.views)) {
    for (const 地區 of ["international", "tc"]) {
      const 時長列 = 視圖.rows.filter((列) => 列[`${地區}_duration`] !== null);
      const 總天數 = 時長列.reduce((總數, 列) => 總數 + 列[`${地區}_duration`].days, 0);
      assert.equal(總天數, 日序(設定.verified_through) - 時長列[0][`${地區}_day`]);
      assert.equal(時長列.filter((列) => 列[`${地區}_duration`].ongoing).length, 1);
    }
  }
});

test("主版本分組包含完整小版，兩服總時長與各版時長一致", () => {
  const 群組 = 資料.views.all.groups;
  assert.deepEqual(群組[0].rows.map((列) => 列.patch), ["7.0", "7.01", "7.05"]);
  assert.deepEqual(群組[1].rows.map((列) => 列.patch), ["7.1", "7.11", "7.15", "7.16", "7.18"]);
  assert.deepEqual(群組[0].international_duration, { days: 133, ongoing: false });
  assert.deepEqual(群組[0].tc_duration, { days: 132, ongoing: false });
  assert.deepEqual(群組[1].international_duration, { days: 133, ongoing: false });
  assert.deepEqual(群組[1].tc_duration, { days: 98, ongoing: false });
  assert.deepEqual(群組[2].tc_duration, { days: 46, ongoing: true });
  assert.equal(群組[3].tc_duration, null);
  for (const 視圖 of Object.values(資料.views)) {
    assert.deepEqual(視圖.groups.flatMap((組) => 組.rows.map((列) => 列.patch)), 視圖.rows.map((列) => 列.patch));
    for (const 組 of 視圖.groups) {
      assert.equal(組.rows[0].patch, 組.patch);
      for (const 地區 of ["international", "tc"]) {
        const 已上線 = 組.rows.filter((列) => 列[`${地區}_duration`] !== null);
        if (!已上線.length) {
          assert.equal(組[`${地區}_duration`], null);
        } else {
          assert.equal(組[`${地區}_duration`].days, 已上線.reduce((總和, 列) => 總和 + 列[`${地區}_duration`].days, 0));
          assert.equal(組[`${地區}_duration`].ongoing, 已上線.at(-1)[`${地區}_duration`].ongoing);
        }
      }
    }
  }
  assert.equal(資料.views.major.groups.every((組) => 組.rows.length === 1), true);
});

test("截止日包含當日上線；未來公告不提早提升目前版本", () => {
  const 前一天 = 複製設定();
  前一天.verified_through = "2026-07-27";
  // 尚未上線的合併對照不得冒充既成事實。
  for (const 列 of 前一天.patches) {
    if (列.merged_into === "7.2") { delete 列.merged_into; delete 列.tc_version_omitted; }
  }
  const 前 = 建置版本進度(前一天);
  assert.equal(前.current_tc, "7.15");
  assert.equal(前.current_international, "7.51");
  assert.equal(前.views.all.forecast.next?.patch, "7.2");
  assert.equal(前.views.all.forecast.status, "insufficient");
  assert.equal(前.views.all.forecast.next.announced, true);
  assert.equal(前.previous_comparable.patch, "7.11");
  assert.equal(前.latest_comparable.patch, "7.15");
  assert.equal(前.lag_reduction, -7);
  assert.equal(前.views.all.rows.find((列) => 列.patch === "7.2").lag_days, null);
  assert.equal(前.views.all.rows.find((列) => 列.patch === "7.2").tc_duration, null);
  assert.equal(前.views.all.rows.find((列) => 列.patch === "7.55").international_duration, null);
  assert.deepEqual(前.views.all.rows.find((列) => 列.patch === "7.15").tc_duration, { days: 34, ongoing: true });
  前一天.verified_through = "2026-07-28";
  const 當天 = 建置版本進度(前一天);
  assert.equal(當天.current_tc, "7.2");
  assert.equal(當天.current_international, "7.55");
  assert.equal(當天.latest_comparable.lag_days, 490);
  assert.equal(當天.previous_comparable.patch, "7.15");
  assert.equal(當天.lag_reduction, 63);
  assert.deepEqual(當天.views.all.rows.find((列) => 列.patch === "7.15").tc_duration, { days: 35, ongoing: false });
  assert.deepEqual(當天.views.all.rows.find((列) => 列.patch === "7.2").tc_duration, { days: 0, ongoing: true });
  assert.deepEqual(當天.views.all.rows.find((列) => 列.patch === "7.55").international_duration, { days: 0, ongoing: true });
});

test("部分內容合併不虛構獨立發布日期或同版本天數差", () => {
  for (const [版本, 合併版] of [["7.16", "7.15"], ["7.18", "7.15"], ["7.21", "7.2"], ["7.3", "7.2"]]) {
    const 列 = 資料.views.all.rows.find((項) => 項.patch === 版本);
    assert.equal(列.merged_into, 合併版);
    assert.equal(列.tc, null);
    assert.equal(列.lag_days, null);
    assert.equal(列.tc_released, false);
    assert.equal(資料.views.all.tc.some((項) => 項.patch === 版本), false);
  }
  assert.equal(資料.views.major.rows.find((列) => 列.patch === "7.3").tc_released, false);
});

test("內容對照來源獨立解析，不取代發布日來源，舊格式仍可建置", () => {
  const 列 = 資料.views.all.rows.find((項) => 項.patch === "7.0");
  assert.equal(列.tc_url, 設定.sources.tc_launch);
  assert.deepEqual(列.note_links[0], { label: "繁中服 7.1 筆記（回溯 7.0）", url: 設定.sources.tc_7_1_notes });
  const 舊格式 = 複製設定();
  for (const 項 of 舊格式.patches) delete 項.note_sources;
  const 舊資料 = 建置版本進度(舊格式);
  assert.deepEqual(舊資料.views.all.rows[0].note_links, []);
  assert.equal(舊資料.views.all.gap_count, 資料.views.all.gap_count);
  for (const 來源 of [null, [], [{ label: " ", source: "tc_7_1_notes" }], [{ label: "未知來源", source: "missing" }]]) {
    const 無效 = 複製設定();
    無效.patches[0].note_sources = 來源;
    assert.throws(() => 建置版本進度(無效));
  }
});

test("省略 7.16、7.18、7.21 圖表刻度，保留面板、網址選取與正確的折線階段", () => {
  const 視圖 = 資料.views.all;
  assert.equal(視圖.rows.length, 22);
  assert.equal(視圖.stages.length, 19);
  for (const 版本 of ["7.16", "7.18", "7.21"]) {
    assert.equal(視圖.rows.find((列) => 列.patch === 版本).tc_version_omitted, true);
    assert.equal(視圖.stages.includes(版本), false);
    assert.deepEqual(正規化版本進度選取(資料, { patchScope: "all", patch: 版本 }), { patchScope: "all", patch: 版本, guess: false });
  }
  assert.equal(視圖.stages.indexOf("7.2"), 視圖.stages.indexOf("7.15") + 1);
  assert.equal(視圖.stages.indexOf("7.25"), 視圖.stages.indexOf("7.2") + 1);
  // 已確認部分功能提前的其他版本仍保留刻度，不能一律排除 merged_into。
  assert.equal(視圖.stages.includes("7.3"), true);
  for (const 地區 of ["tc", "international"]) {
    for (const 點 of 視圖[地區]) {
      assert.equal(視圖.stages[點.stage], 點.patch);
      assert.equal(["7.16", "7.18", "7.21"].includes(點.patch), false);
    }
  }
  assert.equal(視圖.gap_count, 13);
});

test("拒絕重複鍵值、倒序、遺漏來源與無效合併對照", () => {
  for (const 變更 of [
    (值) => { 值.patches[1].patch = "7.0"; },
    (值) => { 值.patches[1].international = "2024-01-01"; },
    (值) => { delete 值.patches[1].tc_source; },
    (值) => { 值.patches.find((列) => 列.patch === "7.21").merged_into = "8.0"; },
    (值) => { 值.patches[0].tc_version_omitted = "true"; },
    (值) => { 值.patches[0].tc_version_omitted = true; },
    (值) => { 值.patches.find((列) => 列.patch === "7.16").merged_into = "7.2"; },
    (值) => { 值.schema_version = 2; },
  ]) {
    const 值 = 複製設定();
    變更(值);
    assert.throws(() => 建置版本進度(值));
  }
});

test("預設小版本、無效網址回復與切換主要版本保留所屬階段", () => {
  assert.deepEqual(正規化版本進度選取(資料), { patchScope: "all", patch: "7.2", guess: false });
  assert.deepEqual(正規化版本進度選取(資料, { patchScope: "invalid", patch: "oops" }), { patchScope: "all", patch: "7.2", guess: false });
  assert.deepEqual(正規化版本進度選取(資料, { patchScope: "all", patch: "7.11" }), { patchScope: "all", patch: "7.11", guess: false });
  assert.deepEqual(正規化版本進度選取(資料, { patchScope: "major", patch: "7.11" }), { patchScope: "major", patch: "7.1", guess: false });
  assert.deepEqual(正規化版本進度選取(資料, { patchScope: "major", patch: "7.56" }), { patchScope: "major", patch: "7.5", guess: false });
  assert.deepEqual(正規化版本進度選取(資料, { patchScope: "major", patch: "7.21", guess: "1" }), { patchScope: "major", patch: "7.2", guess: true });
  for (const guess of [false, "false", "0", "invalid"]) assert.equal(正規化版本進度選取(資料, { guess }).guess, false);
  assert.equal(正規化版本進度選取(資料, { patch: "8.15", guess: "1" }).patch, "8.15");
  assert.equal(正規化版本進度選取(資料, { patch: "8.15", patchScope: "major", guess: true }).patch, "8.1");
  assert.equal(正規化版本進度選取(資料, { patch: "8.15", guess: false }).patch, "7.2");
  // 兩種篩選共用延伸主版的觀察終點，小版本選取切換後仍須回到可用的所屬主版。
  const 主版選取 = 正規化版本進度選取(資料, { patch: 資料.views.all.forecast.catch_up.patch, patchScope: "major", guess: true });
  assert.ok(資料.views.major.forecast.rows.some((列) => 列.patch === 主版選取.patch));
});

test("版本路由的查詢、歷史寫入與子路徑保留；切頁清除版本頁參數", async () => {
  // 隔離瀏覽器分享事件與功能旗標，實際執行 URL 模組，不讀玩家資料或模擬 URL 邏輯。
  const 原始碼 = readFileSync(new URL("../src/utils/urlState.js", import.meta.url), "utf8")
    .replace(/import .* from "\.\/shareMeta";/, 'const 分享網址變更事件 = "test-share-url";')
    .replace(/import .* from "\.\/siteFeatures";/, "const 顯示Honey粉絲榜 = false;");
  const 模組 = await import(`data:text/javascript;base64,${Buffer.from(原始碼).toString("base64")}`);
  const 原視窗 = globalThis.window;
  const 原事件 = globalThis.CustomEvent;
  const 視窗 = { location: new URL("https://example.test/repo/version-progress?patchScope=all&patch=7.11"),
    history: { pushState: (_a, _b, 網址) => { 視窗.location = new URL(網址); } }, dispatchEvent() {} };
  globalThis.window = 視窗;
  globalThis.CustomEvent = class {};
  try {
    assert.equal(模組.讀取目前網址狀態().page, "version-progress");
    assert.equal(模組.讀取目前網址狀態().patch, "7.11");
    模組.寫入網址狀態({ page: "version-progress", patchScope: "major", patch: "7.1", guess: true });
    assert.equal(視窗.location.pathname, "/repo/version-progress");
    assert.equal(視窗.location.searchParams.get("patch"), "7.1");
    assert.equal(模組.讀取目前網址狀態().guess, "1");
    assert.equal(正規化版本進度選取(資料, 模組.讀取目前網址狀態()).guess, true);
    模組.寫入網址狀態({ page: "version-progress", patchScope: "all", patch: "7.21", guess: false });
    assert.equal(視窗.location.searchParams.has("guess"), false);
    模組.寫入網址狀態({ page: "version-progress", guess: true });
    模組.寫入網址狀態({ page: "faq" });
    assert.equal(視窗.location.pathname, "/repo/faq");
    assert.equal(視窗.location.search, "");
  } finally {
    globalThis.window = 原視窗;
    globalThis.CustomEvent = 原事件;
  }
});

test("靜態版本路由可產生獨立 SEO、OG 與 sitemap，首頁仍為排行榜", () => {
  // 使用空白資料夾與真實 HTML 殼層驗證 postbuild，不讀正式 public/data 或玩家檔案。
  const 暫存根 = resolve(tmpdir());
  const 工作區 = mkdtempSync(join(暫存根, "ffxiv-version-progress-"));
  try {
    mkdirSync(join(工作區, "dist"));
    writeFileSync(join(工作區, "dist/index.html"), readFileSync(new URL("../index.html", import.meta.url)));
    const 結果 = spawnSync(process.execPath, [fileURLToPath(new URL("./build_spa_fallback.mjs", import.meta.url))], {
      cwd: 工作區, env: { ...process.env, FFXIV_TC_BUILD_USER_SHARE_PAGES: "false" }, encoding: "utf8", timeout: 60000,
    });
    assert.equal(結果.status, 0, 結果.stderr || 結果.error?.message);
    const 首頁 = readFileSync(join(工作區, "dist/index.html"), "utf8");
    const 版本頁 = readFileSync(join(工作區, "dist/version-progress/index.html"), "utf8");
    assert.match(首頁, /<title>FFXIV 繁中服排行榜<\/title>/);
    assert.match(版本頁, /<title>版本進度 \| FFXIV 繁中服排行榜<\/title>/);
    assert.match(版本頁, /og\/pages\/version-progress.png/);
    assert.match(readFileSync(join(工作區, "dist/sitemap.xml"), "utf8"), /version-progress/);
  } finally {
    // Windows 清理前確認絕對路徑仍在本測試建立的暫存範圍內。
    if (resolve(工作區).startsWith(`${暫存根}${sep}ffxiv-version-progress-`)) rmSync(工作區, { recursive: true, force: true });
  }
});
