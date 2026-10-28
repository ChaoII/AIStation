// 接入文档：REST / MCP 两种接入方式的 Markdown 内容。
// 这些内容含大量字面 `{}` / `<host>` / `@` 等 vue-i18n 保留字符，
// 若放进 i18n 消息会触发「Message compilation error」导致整体不渲染。
// 故统一在此以常量给出（模板里经 MarkdownRenderer 渲染，代码块用带语言的围栏代码块走语法高亮）。

export const REST_MD = `**步骤 1｜凭证校验**——确认应用状态与已授权能力

\`\`\`bash
curl -X GET "https://<host>/api/v1/ai/develop-api/auth/verify" \\
  -H "Authorization: Bearer {appid}:{appkey}"
\`\`\`

**步骤 2｜能力清单**——只返回本应用**已授权**的能力

\`\`\`bash
curl -X GET "https://<host>/api/v1/ai/develop-api/capabilities" \\
  -H "Authorization: Bearer {appid}:{appkey}"
\`\`\`

**步骤 3｜调用能力**（统一入口）——\`code\` 取自能力清单，body 固定为 \`{"payload": {...}}\`

\`\`\`bash
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/agent.create" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"agent_name": "外部创建助手"}}'
\`\`\`

**步骤 4｜对话**（聚合回复，非流式）

\`\`\`bash
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/chat.send" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"kind": "workflow", "target_id": 12, "message": "你好"}}'
\`\`\``;

export const MCP_MD = `**端点**：\`https://<host>/api/v1/ai/develop-api/mcp\`（Streamable HTTP）

**鉴权**：请求头 \`Authorization: Bearer {appid}:{appkey}\`，与 REST 同一套凭证。

#### 客户端配置

**方式一｜自定义请求头**（推荐）

\`\`\`json
{
  "mcpServers": {
    "aistation": {
      "type": "http",
      "url": "https://<host>/api/v1/ai/develop-api/mcp",
      "headers": { "Authorization": "Bearer {appid}:{appkey}" }
    }
  }
}
\`\`\`

**方式二｜只支持 stdio 的客户端**（用 \`mcp-remote\` 代理转发请求头）

\`\`\`json
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
\`\`\`

#### 工具调用

**工具 = 能力**：先 \`tools/list\` 确认本应用已授权哪些工具（未授权的不暴露），返回工具名 + \`inputSchema\`，参数与能力入参一一对应。

\`\`\`js
const assistant = client.getTool("agent_list");      // 列出智能体
const agents    = await assistant.call({});

const chat      = client.getTool("chat_send");       // 对话（非流式聚合回复）
const reply     = await chat.call({ kind: "workflow", target_id: 12, message: "你好" });
\`\`\`

#### 资源与审计

**能力资源**：\`aistation://capabilities\` 返回该应用已授权能力的完整清单（含能力码 / 权限点 / MCP 工具名 / 是否需审批）。

\`\`\`js
const caps = await client.readResource("aistation://capabilities");
\`\`\`

**审批与审计**：敏感能力若开启「需人工审批」，调用返回 \`pending_approval\`；所有调用都写平台审计（成功 / 拒绝 / 限流 / 配额命中），\`appid:appkey\` 只能放服务端请求头。`;
