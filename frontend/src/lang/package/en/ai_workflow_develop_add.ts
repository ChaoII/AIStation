export default {
  // ===== develop (开放平台) =====
  develop_tabApps: "Apps",
  develop_tabLogs: "Call Logs",
  develop_tabAudit: "Call Audit",
  develop_tabMcp: "MCP Sessions",
  develop_tabUsage: "Usage",
  develop_tabApprovals: "Approvals",
  develop_tabDocs: "Access Docs",
  develop_keyword: "Keyword",
  develop_keywordPlaceholder: "Name / AppID",
  develop_query: "Query",
  develop_alertExpiringTitle: "{count} apps will expire soon",
  develop_expiringItem: "{name} expires at {expire}",
  develop_etc: ", etc.",
  develop_hintCreateApp:
    "Authorize capabilities to external callers; manage keys, quotas and approval.",
  develop_appTotal: "{total} apps total",
  develop_newApp: "New App",
  develop_name: "Name",
  develop_namePlaceholder: "Unique app name",
  develop_nameRequired: "Please enter a name",
  develop_copyAppid: "Copy AppID",
  develop_status: "Status",
  develop_enabled: "Enabled",
  develop_enabledMsg: "Enabled",
  develop_disabledMsg: "Disabled",
  develop_expireTime: "Expire Time",
  develop_expirePlaceholder: "Leave empty to never expire",
  develop_forever: "Forever",
  develop_capabilities: "Capabilities",
  develop_callCount: "Calls",
  develop_noData: 'No apps yet. Create one with "New App"',
  develop_action: "Actions",
  develop_detail: "Detail",
  develop_edit: "Edit",
  develop_editAppTitle: "Edit App · {name}",
  develop_delete: "Delete",
  develop_deleteConfirm:
    'This will delete the app "{name}" and its AppKey will become invalid immediately; this cannot be undone. Continue?',
  develop_deleteConfirmTitle: "Delete Confirmation",
  develop_deleteSuccess: "App deleted",
  develop_deleteFail: "Delete failed",
  develop_embed: "Embed",
  develop_try: "Try",
  develop_tryTitle: "Try Capability",
  develop_tryAlert: "Send a test call with the app's credential to see the raw response.",
  develop_selectCapability: "Select a capability",
  develop_selectCapabilityRequired: "Please select a capability",
  develop_payloadJson: "Payload (JSON)",
  develop_payloadPlaceholder: 'Request payload, e.g. {"agent_name": "..."}',
  develop_invalidJson: "Invalid JSON",
  develop_result: "Result",
  develop_rawResponse: "Raw Response",
  develop_response: "Response",
  develop_send: "Send",
  develop_close: "Close",
  asset_embed: "Embed",
  asset_embed_title: "Embed · {name}",
  asset_embed_form: "Embed form",
  asset_embed_chatBubble: "Chat bubble",
  asset_embed_runApi: "Run API",
  asset_embed_code: "Code",
  asset_embed_mint: "Generate token",
  asset_embed_issued: "Issued tokens",
  asset_embed_tokenHint: "Credential",
  asset_embed_tokenHintDesc:
    "{token} is a short-lived asset token placeholder bound to this asset: generated in the workbench, no appid/appkey exchange needed. Paste it directly. Regenerate and call setToken() on expiry.",
  asset_embed_mintFail: "Failed to issue token",
  develop_trySuccess: "Call succeeded",
  develop_tryError: "[{code}] {msg}",
  develop_tryFailMsg: "Request failed",
  develop_resultTaskId: "Task ID",
  develop_resultDeletedId: "Deleted ID",
  develop_resultName: "Name",
  develop_resultReply: "Reply",
  develop_resultSid: "SID",
  develop_resultSessionId: "Session ID",
  develop_resultTotal: "Total",
  develop_resultStatus: "Status",
  develop_resultEnabled: "Enabled",
  develop_resultSourceApp: "Source App",
  develop_resultItemsCount: "Items",
  develop_itemsUnit: "items",
  develop_yes: "Yes",
  develop_no: "No",
  develop_opFail: "Operation failed",
  develop_save: "Save",
  develop_saveSuccess: "App saved",
  develop_saveFail: "Save failed",
  develop_loadFail: "Failed to load",
  develop_cancel: "Cancel",
  develop_copied: "Copied",
  develop_copyFailManual: "Copy failed, please copy manually",
  develop_desc: "Description",
  develop_descPlaceholder: "What this app is used for",
  develop_authCaps: "Authorized Capabilities",
  develop_requiresApproval: "Requires Approval",
  develop_requiresApprovalTip: "Sensitive capabilities must be approved before they execute.",
  develop_dailyQuota: "Daily Quota",
  develop_quotaTip: "0 = unlimited; quota is counted per natural day.",
  develop_unlimited: "Unlimited",
  develop_todayUsage: "Today {usage}",
  develop_catTrain: "Training",
  develop_catAgent: "Agent",
  develop_catChat: "Chat",
  develop_catBot: "Bot",
  develop_catEmbed: "Embed",
  develop_keyTitle: "{name} · AppKey",
  develop_keyEncrypted: "Encrypted",
  develop_resetKey: "Reset AppKey",
  develop_resetKeyTitle: "Reset AppKey",
  develop_resetKeyConfirm:
    'Resetting will immediately invalidate the current AppKey of "{name}"; the new key takes effect right away and this cannot be undone. Continue?',
  develop_reset: "Reset",
  develop_keyResetSuccess: "AppKey reset",
  develop_keyResetFail: "Reset failed",
  develop_createSuccessTitle: "Created Successfully",
  develop_saveKeyAlert: "Save the AppKey now",
  develop_saveKeyDesc:
    "The AppKey is shown only once; after closing you cannot view it again. Store it securely.",
  develop_iSaved: "I've Saved It",
  develop_statTodayCalls: "Today's Calls",
  develop_statSuccessRate: "Success Rate",
  develop_statAvgLatency: "Avg Latency",
  develop_statPending: "Pending Approvals",
  develop_suffixCount: "calls",
  develop_suffixRecords: "records",
  develop_suffixItems: "items",
  develop_appLabel: "App",
  develop_all: "All",
  develop_category: "Category",
  develop_method: "Method",
  develop_success: "Success",
  develop_failed: "Failed",
  develop_denied: "Denied",
  develop_timeRange: "Time Range",
  develop_to: "to",
  develop_startTime: "Start Time",
  develop_endTime: "End Time",
  develop_capability: "Capability",
  develop_exportCsv: "Export CSV",
  develop_time: "Time",
  develop_latency: "Latency",
  develop_latencyTokens: "Latency / Tokens",
  develop_requestPath: "Request Path",
  develop_resultSummary: "Result Summary",
  develop_noLogs: "No call logs yet",
  develop_recent7: "Last 7 days",
  develop_trendTitle: "Call Trend",
  develop_recent30: "Last 30 days",
  develop_today: "Today",
  develop_sparkTitle: "{date}: {calls} calls",
  develop_topCapabilities: "Top Capabilities",
  develop_topCapabilitiesShort: "Top Capabilities",
  develop_filterCapabilityTitle: "Filter by {capability}",
  develop_logDetailTitle: "Call Log Detail",
  develop_methodStatus: "Method / Status",
  develop_requestBody: "Request Body",
  develop_requestBodyShort: "Payload",
  develop_errorStatus: "Error",
  develop_error: "Error",
  develop_successRate: "Success Rate",
  develop_quotaHits: "Quota Hits",
  develop_rateLimited: "Rate Limited",
  develop_noUsage: "No usage data",
  develop_usageRange: "Range",
  develop_recentDays: "Last {days} days",
  develop_recentDaysValue: "{days}d",
  develop_calls: "Calls",
  develop_usageLoadFail: "Failed to load usage",
  develop_sessionId: "Session ID",
  develop_transport: "Transport",
  develop_transportStreamable: "Streamable HTTP",
  develop_transportStdio: "stdio",
  develop_client: "Client",
  develop_duration: "Duration (s)",
  develop_toolCalls: "Tool Calls",
  develop_closeReason: "Close Reason",
  develop_noMcp: "No MCP sessions",
  develop_usedTools: "Used tools",
  develop_noCalls: "No calls",
  develop_mcpDetail: "MCP Session Detail",
  develop_toolDetail: "Tool Calls",
  develop_quotaHit: "Quota hit",
  develop_permDenied: "No permission",
  develop_authToolsTitle: "Authorized MCP tools",
  develop_authToolsEmpty: "No MCP tools authorized for this app",
  develop_authToolCount: "{count} tools in total",
  develop_sessionDuration: "Duration",
  develop_mcpStatSessions: "Sessions",
  develop_mcpStatToolCalls: "Tool Calls",
  develop_mcpStatAvgDuration: "Avg Duration (s)",
  develop_mcpSparkTitle: "{date}: {sessions} sessions · {toolCalls} tool calls",
  develop_approvalHint:
    'Sensitive capabilities are "approve before execute"; review the pending requests below.',
  develop_approvalPending: "{count} pending",
  develop_approvalPendingStatus: "Pending",
  develop_approve: "Approve",
  develop_approveExecute: "Approve & Execute",
  develop_reject: "Reject",
  develop_approvedStatus: "Approved",
  develop_pendingStatus: "Pending",
  develop_rejectedStatus: "Rejected",
  develop_expiredStatus: "Expired",
  develop_execFailStatus: "Failed",
  develop_batchApprove: "Batch Approve ({count})",
  develop_batchApproveTitle: "Batch Approve {count}",
  develop_batchApproveConfirm:
    "This will approve and execute {count} pending capability calls. Continue?",
  develop_batchApproveSuccess: "Approved {count} requests",
  develop_batchApprovePartial: "{ok} approved, {failed} failed. {msg}",
  develop_batchApproveFail: "Batch approve failed",
  develop_applyTime: "Apply Time",
  develop_reviewTime: "Review Time",
  develop_reviewNote: "Review Note",
  develop_noApprovals: "No approvals",
  develop_approvalLoadFail: "Failed to load approvals",
  develop_approvalDetailTitle: "Approval Detail",
  develop_reviewApproveAction: "Approve",
  develop_reviewConfirmTitle: "{action}?",
  develop_reviewApproveConfirm:
    'Approve the call for capability "{capability}" of app {appid} and execute it?',
  develop_reviewRejectConfirm: 'Reject the call for capability "{capability}"?',
  develop_processed: "Processed",
  develop_processFail: "Processing failed",
  develop_execResult: "Execution Result",
  develop_execFailTitle: "Execution failed: {error}",
  develop_notifyCfg: "Notification Config",
  develop_notifyCfgTitle: "Approval Notification",
  develop_notifyAlert:
    "Choose which channels send approval notifications and provide their JSON config.",
  develop_enableChannels: "Enable Channels",
  develop_channelConfig: "{name} Config",
  develop_notifyInvalidJson: "Invalid JSON for {name}",
  develop_notifyLoadFail: "Failed to load notification config",
  develop_notifyBroken: "Broken channel config: {broken}",
  develop_saved: "Saved",
  develop_docsCredTitle: "Credentials",
  develop_docsCredDesc:
    'Each app has an AppID + AppKey. Callers authenticate with "Bearer {appid}:{appkey}"; never expose AppKey on the browser side.',
  develop_docsApprovalTitle: "Approval not required?",
  develop_docsApprovalDesc:
    'Sensitive capabilities require app-level approval on first call; enable it in the app\'s "Authorized Capabilities" and "Daily Quota" settings.',
  develop_restCard: "REST",
  develop_restDesc: "Unified capability entry: use the capability code to call any capability.",
  develop_capListCard: "Capability List",
  develop_capDesc:
    "All open capabilities exposed by the platform, with required permissions and MCP tool names.",
  develop_capCount: "{count} capabilities",
  develop_capabilityName: "Name",
  develop_capabilityCode: "Code",
  develop_requiredPerm: "Required Permission",
  develop_mcpToolName: "MCP Tool",
  develop_noCapabilities: "No capabilities",
  develop_capLoadFail: "Failed to load capabilities",
  develop_mcpCard: "MCP",
  develop_mcpDesc: "Expose the same capabilities over MCP (Streamable HTTP); each call is audited.",
  develop_embedCard: "Web Embed",
  develop_embedDesc:
    "Embed the conversation into your page via iframe or the Script SDK. Tokens are exchanged by your server.",
  develop_postMessageEvents: "postMessage Events",
  develop_embedFoot:
    'Use these event names and the setToken / sendMessage / resize / destroy commands from the "Embed" dialog.',
  develop_eventReady: "Embed page initialized (includes target name and expire time)",
  develop_eventUserMessage: "User sent a message",
  develop_eventReplyStart: "Streaming reply started",
  develop_eventReplyDelta: "Streaming delta text (high frequency)",
  develop_eventReplyDone: "Reply completed (full text)",
  develop_eventError: "Business / network / rate-limit error",
  develop_eventTokenExpired: "Credential expired; the host must re-exchange and call setToken",
  develop_exportFail: "Export failed",
  develop_downloadStarted: "Download started",
  develop_restExample: `# 1. Credential check: confirm app status and authorized capabilities
curl -X GET "https://<host>/api/v1/ai/develop-api/auth/verify" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 2. Capability list: returns only the app's **authorized** capabilities
curl -X GET "https://<host>/api/v1/ai/develop-api/capabilities" \\
  -H "Authorization: Bearer {appid}:{appkey}"

# 3. Invoke a capability (unified entry): code from the capability list, body fixed as {"payload": {...}}
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/agent.create" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"agent_name": "外部创建助手"}}'

# 4. Chat (aggregated reply, non-streaming)
curl -X POST "https://<host>/api/v1/ai/develop-api/capabilities/chat.send" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"payload": {"kind": "workflow", "target_id": 12, "message": "你好"}}'

# 5. Web embed token exchange (browser never touches AppKey)
curl -X POST "https://<host>/api/v1/ai/develop-api/auth/token" \\
  -H "Authorization: Bearer {appid}:{appkey}" \\
  -H "Content-Type: application/json" \\
  -d '{"kind": "agent", "target_id": 123}'`,
  develop_mcpExample: `// Endpoint (Streamable HTTP): https://<host>/api/v1/ai/develop-api/mcp
// Auth: header Authorization: Bearer {appid}:{appkey} (same credentials as REST)

// Way 1: client natively supports custom headers (recommended)
{
  "mcpServers": {
    "aistation": {
      "type": "http",
      "url": "https://<host>/api/v1/ai/develop-api/mcp",
      "headers": { "Authorization": "Bearer {appid}:{appkey}" }
    }
  }
}

// Way 2: client supports only stdio (forward headers via mcp-remote)
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

// Tool = capability: tools/list only returns the app's authorized capabilities; every call is audited.`,
  develop_embedExample:
    `<!-- Way 1: direct iframe embed (token injected by server-side exchange) -->
<iframe src="https://<host>/web/#/embed?token={access_token}"
        width="420" height="620" style="border:0;border-radius:12px"></iframe>

<!-- Way 2: Script SDK (recommended: event callbacks + renewal) -->
<script src="https://<host>/api/v1/ai/embed/sdk.js"></scr` +
    `ipt>
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
</scr` +
    `ipt>`,

  // ===== develop_embed (嵌入弹窗) =====
  develop_embedTitle: "Embed Chat · {name}",
  develop_embedKind: "Embed Type",
  develop_embedApp: "AI App",
  develop_embedWorkflow: "Workflow",
  develop_embedTarget: "Embed Target",
  develop_embedTargetPlaceholder: "Select the target to embed",
  develop_embedCode: "Embed Code",
  develop_embedTabIframe: "iframe Embed",
  develop_embedCopyCode: "Copy Code",
  develop_embedMintToken: "Mint Trial Token (2h)",
  develop_embedCredTitle: "Credential Note",
  develop_embedCredDesc:
    "{access_token} is a short-lived credential placeholder: have your host backend exchange it via POST {apiBase}/develop-api/auth/token using appid/appkey. Never write AppKey into the web page. When it expires, re-exchange and call setToken() to renew.",
  develop_embedIssuedTokens: "Issued Tokens",
  develop_embedNoTokens: "No tokens (exchanged and trial tokens appear here)",
  develop_embedKindShort: "Kind",
  develop_embedTrialTicket: "Trial",
  develop_embedIssuedTicket: "Exchange",
  develop_embedTargetShort: "Target",
  develop_embedExpireTime: "Expire Time",
  develop_embedUsage: "Use",
  develop_embedStatus: "Status",
  develop_embedRevoked: "Revoked",
  develop_embedValid: "Valid",
  develop_embedAction: "Action",
  develop_embedRevoke: "Revoke",
  develop_embedRevokeFail: "Revoke failed",
  develop_embedRevokeTitle: "Revoke Token",
  develop_embedRevokeConfirm:
    "After revocation the token becomes invalid immediately; the embedded page using it can no longer chat and this cannot be undone. Continue?",
  develop_embedEvents: "Event Contract",
  develop_embedEventsNote:
    'Upstream envelope source = ai-embed / version = 1; full payload and downstream commands are in the "Access Docs" tab.',
  develop_embedRevealTitle: "Trial Token",
  develop_embedRevealAlertTitle: "Copy and paste into your code now",
  develop_embedRevealAlertDesc: "The token is shown only once here; just re-issue when it expires.",
  develop_embedApplyCode: "Fill into Code",
  develop_embedApplySuccess: "Filled into code, ready to copy",
  develop_embedIframeTitle: "AI Chat",
  develop_embedTargetsLoadFail: "Failed to load target list",
  develop_embedMintFail: "Mint failed",

  // ===== embed (公开嵌入页) =====
  embed_brand: "AI Assistant",
  embed_missingTitle: "Missing Access Token",
  embed_missingDesc:
    "This page requires a one-time access token. Generate it on your backend and open the URL with ?token=...",
  embed_conversation: "Conversation",
  embed_aiAssistant: "AI Assistant",
  embed_you: "You",
  embed_welcome: "Hello, how can I help you?",
  embed_hint: "Enter your question below to chat",
  embed_inputPlaceholder: "Type your question...",
  embed_send: "Send",
  embed_stopGenerate: "Stop generating",
  embed_sourcesCount: "{count} sources",
  embed_knowledgePiece: "Knowledge",
  embed_retry: "Retry",
  embed_metaLoadFail: "Failed to load the conversation",
  embed_noPermMsg: "No permission to access this conversation",
  embed_rateLimitedMsg: "Too many requests, please try again later",
  embed_rateLimitedNotice: "Too many requests, please try again later",
  embed_notFoundMsg: "The target was not found",
  embed_notFoundNotice: "The target was not found",
  embed_networkMsg: "Network error, please try again",
  embed_networkNotice: "Network error, please try again",
  embed_expiredTitle: "Access Token Expired",
  embed_expiredDesc:
    "The access token has expired. Ask the host to re-exchange and call setToken().",
  embed_forbiddenTitle: "No Permission",
  embed_forbiddenDesc: "You do not have permission to access this conversation.",
};
