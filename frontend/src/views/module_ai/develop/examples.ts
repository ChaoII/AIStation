// 接入文档：REST / MCP / Embed 三种接入方式的代码示例。
// 这些示例是「代码」而非可翻译文案，且含大量字面 `{}` / `@` 等 vue-i18n 保留字符，
// 若放进 i18n 消息会触发「Message compilation error」导致代码块整体不渲染。
// 故统一在此以常量给出（模板里用 {{ CONST }} 直接插值，Vue 自动转义为纯文本）。

export const REST_EXAMPLE = `# 1. 凭证校验：确认应用状态与已授权能力
curl -X GET "https://<host>/api/v1/ai/develop-api/auth/verify" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 2. 能力清单：只返回本应用**已授权**的能力
curl -X GET "https://<host>/api/v1/ai/develop-api/capabilities" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 3. 调用能力（统一入口）：code 取自能力清单，body 固定为 {"payload": {...}}
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/agent.create" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"agent_name": "外部创建助手"}}'

# 4. 对话（聚合回复，非流式）
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/chat.send" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"kind": "workflow", "target_id": 12, "message": "你好"}}'

# 5. 网页嵌入换票（浏览器面不接触 appkey）
curl -X POST "https://<host>/api/v1/ai/develop-api/auth/token" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"kind": "agent", "target_id": 123}'`;

export const MCP_EXAMPLE = `// 端点（Streamable HTTP）：https://<host>/api/v1/ai/develop-api/mcp
// 鉴权：请求头 Authorization: Bearer {appid}:{appkey}（与 REST 同一套凭证）

// 方式一：客户端原生支持自定义请求头（推荐）
{
  "mcpServers": {
    "aistation": {
      "type": "http",
      "url": "https://<host>/api/v1/ai/develop-api/mcp",
      "headers": { "Authorization": "Bearer {appid}:{appkey}" }
    }
  }
}

// 方式二：客户端只支持 stdio（用 mcp-remote 代理转发请求头）
{
  "mcpServers": {
    "aistation": {
      "command": "npx",
      "args": [
        "-y", "mcp-remote",
        "https://<host>/api/v1/ai/develop-api/mcp",
        "--header", "Authorization: Bearer {appid}:{appkey}"
      ]
    }
  }
}

// 工具 = 能力：tools/list 只返回该应用已授权的能力；每次调用都写审计。`;

export const EMBED_EXAMPLE = `<!-- 方式一：iframe 直嵌（token 由服务端换票注入） -->
<iframe src="https://<host>/web/#/embed?token={access_token}"
        width="420" height="620" style="border:0;border-radius:12px"></iframe>

<!-- 方式二：Script SDK（推荐：事件回调 + 续期） -->
<script src="https://<host>/api/v1/ai/embed/sdk.js"><\/script>
<div id="ai-assistant" style="width:420px;height:620px"></div>
<script>
  const ai = AiAssistant.init({
    container: "#ai-assistant",
    token: "{access_token}",
    apiBase: "https://<host>/api/v1/ai",
    webBase: "https://<host>/web",
    theme: { primary: "#409eff" }
  });
  ai.on("token_expired", async () => {
    ai.setToken(await fetchTokenFromYourBackend());  // 服务端重新换票
  });
<\/script>`;
