/**
 * SSE（Server-Sent Events）流的读取与解析。
 *
 * 为什么不用原生 `EventSource`
 * --------------------------
 * 原生 `EventSource` **无法设置请求头**，而本项目的鉴权只认
 * `Authorization: Bearer`（无 cookie 认证、也不接受 `?token=`），
 * 于是指标流在浏览器里恒定 401 —— 页面上的指标其实一直靠 5 秒轮询撑着，
 * 实时流从未真正工作过。`EventSource` 的 `withCredentials` 只对 cookie 生效。
 *
 * 为什么自己解析而不用 eventsource-parser
 * --------------------------------------
 * 项目约定「流式/解析这类通用能力要用成熟库」，首选 `eventsource-parser`
 * （MIT、零依赖、Vercel AI SDK 自己就在用）。本仓库当前装不上：
 * `pnpm add` 会先重解析整棵树，而 lockfile 里 `mpegts.js@1.8.0` 带了一个
 * `git+ssh://git@github.com/xqq/webworkify-webpack.git` 依赖——该机器 GitHub
 * 需走 127.0.0.1:7890 代理而代理未启动，`pnpm add` 直接 128 退出。
 *
 * 这里是刻意的临时偏离：本项目服务端发出的帧格式是**固定且最简**的一种
 * （`event:` / `id:` / `data:` / `: keepalive` 注释），下面的解析器已经覆盖
 * 完整帧 + 跨 chunk 拆包 + CRLF + 多行 data。等依赖装得上时，把
 * {@link createSSEParser} 内部换成 `eventsource-parser` 的 `createParser` 即可，
 * 外部接口不变。
 */

/** 一帧已解析完的 SSE 事件。 */
export interface SSEEvent {
  /** 事件名；服务端未给 `event:` 时为空串（按 SSE 规范等价于 `message`）。 */
  event: string;
  /** 拼接后的 `data:` 内容（多行以 `\n` 连接）。 */
  data: string;
  /** `id:` 字段。本项目用它做断点续传的 offset。 */
  id?: string;
  /** `retry:` 字段（毫秒）。 */
  retry?: number;
}

const FIELD_SEP = ":";

/**
 * 增量式 SSE 解析器。
 *
 * 必须做成"喂一坨、吐若干帧"而不是"等整个响应结束再解析"：chunk 边界与
 * 帧边界无关，一个 `data:` 行完全可能断在两次 `feed` 之间。
 */
export interface SSEParser {
  /** 喂入一段文本（通常来自 `TextDecoder` 的解码结果）。 */
  feed(chunk: string): void;
  /** 流结束时冲刷残余缓冲。服务端以事件结尾时不需要调用；留作兜底。 */
  flush(): void;
}

/** 从一行里切出 `字段名` 与 `值`。注释行（`:` 开头）与无冒号行返回 null。 */
function parseLine(line: string): { field: string; value: string } | null {
  if (!line || line.startsWith(FIELD_SEP)) return null; // 空行是帧分隔符，注释行忽略
  const i = line.indexOf(FIELD_SEP);
  if (i < 0) return null; // 规范：未知行整行忽略
  const field = line.slice(0, i);
  let value = line.slice(i + 1);
  // 规范规定冒号后**恰好一个**前导空格要去掉；多个空格只去一个
  if (value.startsWith(" ")) value = value.slice(1);
  return { field, value };
}

/**
 * 创建一个增量解析器，每解析完一帧就调 `onEvent`。
 *
 * @param onEvent 每帧回调；`data` 为空（只有 `event:`/`id:`）的帧也会回调，
 *   由调用方决定是否忽略。
 */
export function createSSEParser(onEvent: (e: SSEEvent) => void): SSEParser {
  let buffer = "";
  // 一帧的累积字段
  let eventName = "";
  let dataLines: string[] = [];
  let lastId: string | undefined;
  let retry: number | undefined;

  function reset() {
    eventName = "";
    dataLines = [];
    // 规范：id 不随帧重置（断线重连沿用最后收到的 id）；retry 同理
  }

  function emit() {
    // SSE 规范：只有带过 data 的帧才触发事件。纯 `id:` 或纯 `retry:` 的帧不触发。
    if (dataLines.length === 0) {
      reset();
      return;
    }
    onEvent({
      event: eventName,
      data: dataLines.join("\n"),
      id: lastId,
      retry,
    });
    reset();
  }

  function consumeLine(raw: string) {
    const line = raw.endsWith("\r") ? raw.slice(0, -1) : raw;
    if (line === "") {
      emit(); // 空行 = 一帧结束
      return;
    }
    const kv = parseLine(line);
    if (!kv) return;
    switch (kv.field) {
      case "event":
        eventName = kv.value;
        break;
      case "data":
        dataLines.push(kv.value);
        break;
      case "id":
        // 规范：含 NUL 的 id 要忽略
        if (!kv.value.includes("\0")) lastId = kv.value;
        break;
      case "retry": {
        const n = Number(kv.value);
        if (Number.isFinite(n) && n >= 0) retry = n;
        break;
      }
      default:
        break; // 未知字段整行忽略
    }
  }

  return {
    feed(chunk: string) {
      buffer += chunk;
      // 帧分隔符可能是 \n\n / \r\n\r\n / \r\r。统一按"空行"切：
      // 这里只找 \n，因为 CRLF 的 \r 已被 consumeLine 剥掉，
      // 剩下的问题只是「最后一个 chunk 末尾那条不完整的行」。
      let idx: number;
      while ((idx = buffer.indexOf("\n")) >= 0) {
        const line = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 1);
        consumeLine(line);
      }
    },
    flush() {
      if (buffer) {
        const rest = buffer;
        buffer = "";
        consumeLine(rest);
      }
      emit();
    },
  };
}

/** {@link streamSSE} 的选项。 */
export interface StreamSSEOptions {
  /** 额外的请求头（鉴权头靠这个传——这正是不能用 EventSource 的原因）。 */
  headers?: Record<string, string>;
  /** 中断信号；`stopMetricStream` 靠它收流。 */
  signal: AbortSignal;
  /** 收到响应头即回调。 */
  onOpen?: (resp: Response) => void;
  /** 每帧回调。 */
  onEvent: (e: SSEEvent) => void;
}

/**
 * 用 `fetch` + `ReadableStream` 消费一个 SSE 端点。
 *
 * 正常返回 = 服务端主动收流（作业终结时后端会补一帧 `end` 后关闭）。
 * 抛错 = 网络中断 / 被 abort / 响应异常，由调用方决定是否重连。
 */
export async function streamSSE(url: string, opts: StreamSSEOptions): Promise<void> {
  const resp = await fetch(url, {
    headers: { Accept: "text/event-stream", ...(opts.headers || {}) },
    signal: opts.signal,
    // SSE 是长连接，不能被常见的 30s 超时掐断
    cache: "no-store",
  });
  opts.onOpen?.(resp);
  if (!resp.ok) {
    throw new Error(`SSE ${resp.status} ${resp.statusText}`);
  }
  if (!resp.body) {
    throw new Error("SSE 响应没有 body（当前环境不支持 ReadableStream）");
  }
  const reader = resp.body.getReader();
  const decoder = new TextDecoder("utf-8");
  const parser = createSSEParser(opts.onEvent);
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      parser.feed(decoder.decode(value, { stream: true }));
    }
    // 最后一个 chunk 可能是多字节字符的一半
    const tail = decoder.decode();
    if (tail) parser.feed(tail);
    parser.flush();
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* 已释放 */
    }
  }
}
