/* 嵌入 SDK 生命周期行为测试（node 执行；pytest 通过 subprocess 调本文件）。
   覆盖：init → on 派发 → destroy（监听移除/iframe 移除/回调释放）→ 幂等 → 销毁后 API 安全。 */
const assert = require("assert");
const fs = require("fs");
const path = require("path");

// ---- 环境 mock ----
const listeners = {};
let postCount = 0;
const iframes = [];
const documentMock = {
  currentScript: null,
  getElementsByTagName: () => [],
  querySelector: () => null,
  createElement: (tag) => {
    const el = {
      tagName: tag,
      style: {},
      attrs: {},
      parentNode: null,
      contentWindow: { postMessage: () => {} },
      setAttribute(k, v) {
        this.attrs[k] = v;
      },
    };
    iframes.push(el);
    return el;
  },
};
const container = {
  children: [],
  appendChild(c) {
    this.children.push(c);
    c.parentNode = this;
  },
  removeChild(c) {
    this.children = this.children.filter((x) => x !== c);
    c.parentNode = null;
  },
};
const windowMock = {
  location: { href: "http://host.local/api/v1/ai/embed/sdk.js" },
  addEventListener(type, fn) {
    (listeners[type] = listeners[type] || []).push(fn);
  },
  removeEventListener(type, fn) {
    listeners[type] = (listeners[type] || []).filter((f) => f !== fn);
  },
  postMessage() {
    postCount += 1;
  },
};

// ---- 执行 SDK 源码（IIFE 参数为 window/document） ----
const src = fs.readFileSync(
  path.join(
    __dirname,
    "..",
    "..",
    "app",
    "plugin",
    "module_ai",
    "asset_embed",
    "static",
    "ai-assistant.js",
  ),
  "utf8",
);
new Function("window", "document", src)(windowMock, documentMock);
assert.ok(windowMock.AiAssistant, "AiAssistant 应挂到 window");
assert.deepStrictEqual(windowMock.AiAssistant.init.length >= 1, true);

// ---- init ----
const instance = windowMock.AiAssistant.init({
  container,
  token: "tk_test",
  apiBase: "http://host.local/api/v1/ai",
  webBase: "http://host.local/web",
});
["setToken", "sendMessage", "resize", "destroy", "on"].forEach((k) =>
  assert.strictEqual(typeof instance[k], "function", `缺方法 ${k}`),
);
assert.strictEqual((listeners.message || []).length, 1, "init 应注册 1 个 message 监听");
assert.strictEqual(container.children.length, 1, "init 应挂载 iframe");

// ---- 事件派发（destroy 前）----
let got = null;
instance.on("ready", (payload) => {
  got = payload;
});
const iframeEl = iframes[iframes.length - 1];
listeners.message[0]({
  data: { source: "ai-embed", event: "ready", payload: { sid: "s1" } },
  source: iframeEl.contentWindow,
  origin: "http://host.local",
});
assert.deepStrictEqual(got, { sid: "s1" }, "回调应收到 payload");

// ---- destroy：移除监听 + 移除 iframe + 幂等 ----
instance.destroy();
assert.strictEqual((listeners.message || []).length, 0, "destroy 后监听应移除");
assert.strictEqual(container.children.length, 0, "destroy 后 iframe 应移除");
instance.destroy(); // 幂等：不抛
instance.setToken("tk2");
instance.sendMessage("hi");
instance.resize(100, 100);
instance.on("ready", () => {});
instance.destroy();

// destroy 后窗口广播也不应再发生（setToken 被早退）
const before = postCount;
instance.setToken("tk3");
assert.strictEqual(postCount, before, "destroy 后 setToken 不应发 postMessage");

console.log("SDK_LIFECYCLE_OK");
