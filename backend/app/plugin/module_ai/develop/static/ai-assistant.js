/**
 * AIStation 对话嵌入 SDK（v1）——零依赖、IIFE，挂载到 window.AiAssistant。
 *
 * 用法（宿主页）：
 *   <script src="https://<host>/api/v1/ai/embed/sdk.js"></script>
 *   <script>
 *     const ai = AiAssistant.init({
 *       container: "#chat",                 // 挂载点（选择器或元素）
 *       token: "<access_token>",            // 由宿主「服务端」换票获取
 *       apiBase: "https://<host>/api/v1/ai",// 可省：默认取本脚本 src 去掉 /embed/sdk.js
 *       webBase: "https://<host>/web",      // 可省：默认 apiBase 的 origin + /web
 *       theme: { primary: "#409eff" }       // 可省：品牌主色
 *     });
 *     ai.on("reply_done", (payload) => console.log(payload.text));
 *   </script>
 *
 * 安全约定：
 * - **切勿把 appkey 写进网页**：token 必须由宿主服务端的 appid:appkey 换票后注入；
 * - 过期续期：收到 token_expired 后，宿主服务端重新换票，再调用 ai.setToken(新票)；
 * - 上行事件校验来源：仅接受来自嵌入页 iframe 且 origin 等于 webBase 来源的消息。
 */
(function (global) {
  "use strict";

  var VERSION = 1;
  var EMBED_EVENTS = [
    "ready",
    "user_message",
    "reply_start",
    "reply_delta",
    "reply_done",
    "error",
    "token_expired",
  ];

  /** 取当前脚本地址（可用于推导默认 apiBase）。 */
  function currentScriptSrc() {
    var s = document.currentScript;
    if (!s) {
      var all = document.getElementsByTagName("script");
      s = all[all.length - 1];
    }
    return s && s.src ? s.src : "";
  }

  /** 默认 apiBase = 脚本 src 去掉 "/embed/sdk.js" 后缀。 */
  function defaultApiBase() {
    var src = currentScriptSrc();
    if (!src) return "/api/v1/ai";
    return src.replace(/\/embed\/sdk\.js(\?.*)?$/i, "");
  }

  function originOf(url) {
    try {
      return new URL(url, global.location.href).origin;
    } catch (e) {
      return "";
    }
  }

  function resolveContainer(container) {
    if (!container) throw new Error("AiAssistant.init: 缺少 container");
    if (typeof container === "string") {
      var el = document.querySelector(container);
      if (!el) throw new Error("AiAssistant.init: 找不到容器 " + container);
      return el;
    }
    return container;
  }

  /**
   * 创建嵌入实例。
   * @param {{container: string|Element, token: string, apiBase?: string, webBase?: string, theme?: {primary?: string}}} opts
   * @returns {{setToken: Function, sendMessage: Function, resize: Function, destroy: Function, on: Function}}
   */
  function init(opts) {
    opts = opts || {};
    if (!opts.token) throw new Error("AiAssistant.init: 缺少 token（请由服务端换票后注入）");

    var el = resolveContainer(opts.container);
    var apiBase = (opts.apiBase || defaultApiBase()).replace(/\/+$/, "");
    var webBase = (opts.webBase || originOf(apiBase) + "/web").replace(/\/+$/, "");
    var webOrigin = originOf(webBase);
    var theme = opts.theme || {};

    var iframe = document.createElement("iframe");
    iframe.setAttribute("title", "AIStation 对话");
    iframe.setAttribute("allow", "clipboard-write");
    iframe.style.cssText =
      "border:0;width:100%;height:100%;min-height:420px;border-radius:12px;background:transparent;display:block;";

    function buildSrc(token) {
      var url =
        webBase +
        "/#/embed?token=" +
        encodeURIComponent(token);
      if (theme.primary) url += "&primary=" + encodeURIComponent(theme.primary);
      return url;
    }

    var token = opts.token;
    var destroyed = false;
    iframe.src = buildSrc(token);
    el.appendChild(iframe);

    var handlers = {};
    EMBED_EVENTS.forEach(function (name) {
      handlers[name] = [];
    });

    function dispatch(event, payload) {
      (handlers[event] || []).forEach(function (cb) {
        try {
          cb(payload, event);
        } catch (e) {
          /* 宿主回调异常不影响 SDK 自身 */
        }
      });
    }

    function onMessage(ev) {
      var data = ev.data;
      if (!data || typeof data !== "object" || data.source !== "ai-embed") return;
      // 只接受来自本实例 iframe、且来源等于嵌入页来源的消息
      if (ev.source !== iframe.contentWindow) return;
      if (webOrigin && ev.origin !== webOrigin) return;
      dispatch(String(data.event || ""), data.payload || {});
      // 同时向 window 再广播同一信封，纯监听者（不走回调）也可订阅
      try {
        global.postMessage(data, "*");
      } catch (e) {
        /* ignore */
      }
    }
    global.addEventListener("message", onMessage);

    function sendCommand(command, payload) {
      var win = iframe.contentWindow;
      if (!win) return;
      win.postMessage(
        { source: "ai-host", version: VERSION, command: command, payload: payload || {} },
        "*"
      );
    }

    return {
      /** 更替访问令牌（过期续期用）：嵌入页会自动重取 meta 并保持会话。 */
      setToken: function (next) {
        if (destroyed || !next) return;
        token = next;
        sendCommand("setToken", { token: next });
      },
      /** 以宿主身份追加一条用户消息。 */
      sendMessage: function (text) {
        if (destroyed || !text) return;
        sendCommand("sendMessage", { text: String(text) });
      },
      /** 调整 iframe 尺寸（像素）。 */
      resize: function (width, height) {
        if (destroyed) return;
        if (width) iframe.style.width = Number(width) + "px";
        if (height) iframe.style.height = Number(height) + "px";
      },
      /** 销毁实例并移除 iframe（幂等：重复调用安全）。 */
      destroy: function () {
        if (destroyed) return;
        destroyed = true;
        global.removeEventListener("message", onMessage);
        if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
        // 释放宿主注册的回调引用（长驻页面多次 init/destroy 时不残留闭包）
        handlers = {};
      },
      /** 订阅上行事件，返回取消订阅函数。 */
      on: function (event, cb) {
        if (!handlers[event]) handlers[event] = [];
        handlers[event].push(cb);
        return function () {
          handlers[event] = handlers[event].filter(function (fn) {
            return fn !== cb;
          });
        };
      },
    };
  }

  global.AiAssistant = { init: init, version: VERSION, events: EMBED_EVENTS.slice() };
})(window);
