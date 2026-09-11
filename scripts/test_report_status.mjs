import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile } from "node:fs/promises";
import { compileScript, parse } from "@vue/compiler-sfc";
import { createRenderer, nextTick } from "vue";
import {
  Fflogs目前明確不可公開,
  Fflogs目前公開可讀,
  查詢Fflogs即時狀態,
  送出Fflogs待收錄,
} from "../src/utils/reportStatus.js";

// 僅測試 FAQ 請求，不讀正式玩家資料、不使用 OAuth，也不寫入 Google Sheet。
const reportCode = "RrzFndmX3gt6K4wV";
const publicPayload = {
  ok: true,
  report_code: reportCode,
  fflogs_access: "accessible",
  visibility: "public",
};
const jsonResponse = (payload = publicPayload) => Response.json(payload);
const flushPromises = async () => {
  for (let index = 0; index < 8; index += 1) await Promise.resolve();
};

function 等待取消(signal) {
  return new Promise((resolve, reject) => {
    signal.addEventListener("abort", () => reject(signal.reason), { once: true });
  });
}

test("以匿名 JSON 跟隨 Apps Script 轉址，移除舊 JSONP 參數", async (context) => {
  const fetchMock = context.mock.method(globalThis, "fetch", async (url, options) => {
    const parsed = new URL(url);
    assert.equal(parsed.searchParams.get("report"), reportCode);
    assert.equal(parsed.searchParams.get("action"), "status");
    assert.equal(parsed.searchParams.has("callback"), false);
    assert.equal(parsed.searchParams.has("prefix"), false);
    assert.equal(options.credentials, "omit");
    assert.equal(options.mode, "cors");
    assert.equal(options.redirect, "follow");
    assert.equal(options.cache, "no-store");
    assert.deepEqual(options.headers, { Accept: "application/json" });
    return jsonResponse();
  });
  assert.deepEqual(await 查詢Fflogs即時狀態(reportCode, {
    endpoint: "https://script.google.com/macros/s/test/exec?callback=old&prefix=old&action=enqueue",
  }), publicPayload);
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("超過舊版 12 秒的慢回應仍可完成，不額外送出請求", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let finish;
  const fetchMock = context.mock.method(globalThis, "fetch", () => new Promise((resolve) => { finish = resolve; }));
  let completed = false;
  const pending = 查詢Fflogs即時狀態(reportCode).then((payload) => { completed = true; return payload; });
  context.mock.timers.tick(15000);
  await flushPromises();
  assert.equal(completed, false);
  finish(jsonResponse());
  assert.deepEqual(await pending, publicPayload);
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("45 秒涵蓋本文下載，逾時會取消請求並保留排查指引", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let requestSignal;
  context.mock.method(globalThis, "fetch", async (url, { signal }) => {
    requestSignal = signal;
    return { ok: true, headers: new Headers({ "content-type": "application/json" }), json: () => 等待取消(signal) };
  });
  const pending = 查詢Fflogs即時狀態(reportCode);
  const checked = assert.rejects(pending, (error) => error.code === "timeout" && /45 秒.*站內收錄結果/.test(error.message));
  await flushPromises();
  context.mock.timers.tick(44999);
  assert.equal(requestSignal.aborted, false);
  context.mock.timers.tick(1);
  await checked;
  assert.equal(requestSignal.aborted, true);
});

test("查詢短暫斷線只重試一次且共用時間預算", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let attempt = 0;
  let requestSignal;
  context.mock.method(globalThis, "fetch", async (url, { signal }) => {
    requestSignal = signal;
    if (attempt++ === 0) throw new TypeError("Failed to fetch");
    return 等待取消(signal);
  });
  const pending = 查詢Fflogs即時狀態(reportCode);
  const checked = assert.rejects(pending, { code: "timeout" });
  await flushPromises();
  context.mock.timers.tick(1000);
  await flushPromises();
  assert.equal(attempt, 2);
  context.mock.timers.tick(44000);
  await checked;
  assert.equal(requestSignal.aborted, true);
  assert.equal(attempt, 2);
});

test("暫時性 HTTP 錯誤重試後可取得正常結果", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  let attempt = 0;
  context.mock.method(globalThis, "fetch", async () => attempt++ === 0
    ? new Response("暫時無法使用", { status: 503 })
    : jsonResponse());
  const pending = 查詢Fflogs即時狀態(reportCode);
  await flushPromises();
  context.mock.timers.tick(1000);
  assert.deepEqual(await pending, publicPayload);
  assert.equal(attempt, 2);
});

test("持續斷線最多兩次，回報連線失敗而非逾時", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const fetchMock = context.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  const checked = assert.rejects(查詢Fflogs即時狀態(reportCode), { code: "network_error" });
  await flushPromises();
  context.mock.timers.tick(1000);
  await checked;
  assert.equal(fetchMock.mock.callCount(), 2);
});

test("取消後重新查同一報告，舊請求不影響新請求", async (context) => {
  const controller = new AbortController();
  const fetchMock = context.mock.method(globalThis, "fetch", async (url, { signal }) => 等待取消(signal));
  const first = 查詢Fflogs即時狀態(reportCode, { signal: controller.signal });
  const checked = assert.rejects(first, { name: "AbortError" });
  controller.abort();
  fetchMock.mock.mockImplementation(async () => jsonResponse());
  assert.deepEqual(await 查詢Fflogs即時狀態(reportCode), publicPayload);
  await checked;
});

test("取消等待重試時不再打 API，預先取消也不發送", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const controller = new AbortController();
  const fetchMock = context.mock.method(globalThis, "fetch", async () => { throw new TypeError("Failed to fetch"); });
  const checked = assert.rejects(查詢Fflogs即時狀態(reportCode, { signal: controller.signal }), { name: "AbortError" });
  await flushPromises();
  controller.abort();
  await checked;
  context.mock.timers.tick(45000);
  await assert.rejects(查詢Fflogs即時狀態(reportCode, { signal: controller.signal }), { name: "AbortError" });
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("Google 一次性轉址延遲回 404 時，取得新轉址後恢復", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const urls = [];
  let finish;
  context.mock.method(globalThis, "fetch", async (url) => {
    urls.push(url);
    if (urls.length === 1) return new Promise((resolve) => { finish = resolve; });
    return jsonResponse();
  });
  const pending = 查詢Fflogs即時狀態(reportCode);
  context.mock.timers.tick(32000);
  const response = new Response("Google 暫時無法提供內容", { status: 404 });
  Object.defineProperty(response, "url", { value: "https://script.googleusercontent.com/macros/echo?user_content_key=expired" });
  finish(response);
  await flushPromises();
  context.mock.timers.tick(1000);
  assert.deepEqual(await pending, publicPayload);
  assert.equal(urls.length, 2);
  assert.notEqual(new URL(urls[0]).searchParams.get("_"), new URL(urls[1]).searchParams.get("_"));
});

for (const status of [403, 404, 429]) {
  test(`HTTP ${status} 不自動重試`, async (context) => {
    const fetchMock = context.mock.method(globalThis, "fetch", async () => new Response("失敗", { status }));
    await assert.rejects(查詢Fflogs即時狀態(reportCode), { code: `http_${status}` });
    assert.equal(fetchMock.mock.callCount(), 1);
  });
}

for (const payload of [
  { ok: false, error_code: "rate_limited", message: "FFLogs 限流" },
  { ok: false, error_code: "temporary_error", message: "FFLogs 暫時無法回應" },
  { ok: true, report_code: reportCode, fflogs_access: "private_or_deleted" },
  { ...publicPayload, visibility: "unlisted" },
  { ...publicPayload, fflogs_access: "archived_inaccessible" },
]) {
  test(`保留後端 ${payload.error_code || payload.fflogs_access + "/" + (payload.visibility || "")} 判定`, async (context) => {
    const fetchMock = context.mock.method(globalThis, "fetch", async () => jsonResponse(payload));
    const result = await 查詢Fflogs即時狀態(reportCode);
    assert.deepEqual(result, payload);
    assert.equal(Fflogs目前公開可讀(result), false);
    assert.equal(Fflogs目前明確不可公開(result), payload.ok);
    assert.equal(fetchMock.mock.callCount(), 1);
  });
}

for (const [label, makeResponse] of [
  ["登入 HTML", () => new Response("<html>登入</html>", { headers: { "content-type": "text/html" } })],
  ["破損 JSON", () => new Response("{", { headers: { "content-type": "application/json" } })],
  ["缺漏欄位", () => jsonResponse({})],
  ["空值", () => jsonResponse(null)],
  ["另一份 report", () => jsonResponse({ ...publicPayload, report_code: "OtherReport123" })],
]) {
  test(`${label} 立即回報異常，不等待到逾時或誤判公開狀態`, async (context) => {
    const fetchMock = context.mock.method(globalThis, "fetch", async () => makeResponse());
    await assert.rejects(查詢Fflogs即時狀態(reportCode), { code: "invalid_response" });
    assert.equal(fetchMock.mock.callCount(), 1);
  });
}

test("送單以 report 為單位，網路失敗不可自動重送", async (context) => {
  const fetchMock = context.mock.method(globalThis, "fetch", async (url) => {
    const params = new URL(url).searchParams;
    assert.equal(params.get("action"), "enqueue");
    assert.equal(params.get("report"), reportCode);
    assert.equal(params.get("request_type"), "retry_existing");
    assert.equal(params.get("site_status"), "found");
    assert.equal(params.has("fight"), false);
    throw new TypeError("Failed to fetch");
  });
  await assert.rejects(送出Fflogs待收錄({ reportCode, requestType: "retry_existing", siteStatus: "found" }), (error) =>
    error.code === "network_error" && /尚未確認.*是否送達/.test(error.message));
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("送單逾時不自動重送或宣稱未送達", async (context) => {
  context.mock.timers.enable({ apis: ["setTimeout"] });
  const fetchMock = context.mock.method(globalThis, "fetch", async (url, { signal }) => 等待取消(signal));
  const checked = assert.rejects(送出Fflogs待收錄({ reportCode }), (error) =>
    error.code === "timeout" && /尚未確認.*是否送達/.test(error.message));
  context.mock.timers.tick(45000);
  await checked;
  assert.equal(fetchMock.mock.callCount(), 1);
});

test("送單成功與後端拒絕仍保留原本結果", async (context) => {
  for (const queue_status of ["queued", "updated", "rejected_not_public"]) {
    const payload = { ...publicPayload, queue_status };
    context.mock.method(globalThis, "fetch", async () => jsonResponse(payload));
    assert.deepEqual(await 送出Fflogs待收錄({ reportCode }), payload);
  }
});

test("無效 report code 不呼叫遠端服務", async (context) => {
  const fetchMock = context.mock.method(globalThis, "fetch", async () => { throw new Error("不應呼叫"); });
  await assert.rejects(查詢Fflogs即時狀態("錯誤網址"), /有效/);
  await assert.rejects(送出Fflogs待收錄({ reportCode: "" }), /有效/);
  assert.equal(fetchMock.mock.callCount(), 0);
});

test("FAQ 更換報告與離開頁面時隔離查詢、送單及 A → B → A 的舊回應", async (context) => {
  // 編譯真正的 SFC setup 並以 Vue renderer 掛載，讓 watch／生命週期實際執行；
  // 只略過版面繪製，不複製頁面狀態邏輯，也不啟動開發伺服器。
  const fileUrl = new URL("../src/pages/ReportStatusPage.vue", import.meta.url);
  const { descriptor } = parse(await readFile(fileUrl, "utf8"));
  const compiled = compileScript(descriptor, { id: "faq-request-test" }).content;
  const source = compiled.replace(/from (["'])([^"']+)\1/g, (match, quote, specifier) => {
    const resolved = specifier.startsWith(".")
      ? new URL(`${specifier}.js`, fileUrl).href
      : import.meta.resolve(specifier);
    return `from ${JSON.stringify(resolved)}`;
  });
  const { default: page } = await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
  const requests = [];
  context.mock.method(globalThis, "fetch", async (url, options) => {
    if (String(url).startsWith("/data/")) return jsonResponse({ reports: [] });
    return new Promise((resolve) => requests.push({ resolve, signal: options.signal }));
  });
  let state;
  const setup = page.setup;
  const renderer = createRenderer({
    createComment: () => ({}),
    insert() {},
    remove() {},
    parentNode: () => null,
    nextSibling: () => null,
  });
  const app = renderer.createApp({
    ...page,
    setup(props, setupContext) { state = setup(props, setupContext); return state; },
    render: () => null,
  });
  app.mount({});
  let unmounted = false;
  context.after(() => { if (!unmounted) app.unmount(); });
  state.輸入文字.value = reportCode;
  await nextTick();
  const first = state.查詢即時公開狀態();
  state.輸入文字.value = "OtherReport123";
  await nextTick();
  assert.equal(requests[0].signal.aborted, true);
  state.輸入文字.value = reportCode;
  await nextTick();
  const second = state.查詢即時公開狀態();
  // 即使底層回應在取消後仍送達，舊錯誤與 finally 也不可清掉新查詢的 loading。
  requests[0].resolve(jsonResponse({ ...publicPayload, fflogs_access: "private_or_deleted" }));
  await first;
  assert.equal(state.即時狀態讀取中.value, true);
  assert.equal(state.即時狀態錯誤.value, "");
  assert.equal(state.即時狀態Payload.value, null);
  requests[1].resolve(jsonResponse());
  await second;
  assert.equal(state.可送出待收錄.value, true);

  const enqueue = state.送出待收錄需求();
  assert.equal(state.可查詢即時狀態.value, false);
  state.清除輸入();
  await nextTick();
  assert.equal(requests[2].signal.aborted, true);
  requests[2].resolve(jsonResponse({ ...publicPayload, queue_status: "queued" }));
  await enqueue;
  assert.equal(state.待收錄Payload.value, null);
  assert.equal(state.待收錄錯誤.value, "");

  state.輸入文字.value = reportCode;
  await nextTick();
  const last = state.查詢即時公開狀態();
  app.unmount();
  unmounted = true;
  assert.equal(requests[3].signal.aborted, true);
  requests[3].resolve(jsonResponse());
  await last;
  assert.equal(state.即時狀態Payload.value, null);
});
