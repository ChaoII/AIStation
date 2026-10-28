export default {
  // ===== develop (开放平台) =====
  develop_tabApps: "앱",
  develop_tabLogs: "호출 로그",
  develop_tabMcp: "MCP 세션",
  develop_tabUsage: "사용량",
  develop_tabApprovals: "승인",
  develop_tabDocs: "접근 문서",
  develop_keyword: "키워드",
  develop_keywordPlaceholder: "이름 / AppID",
  develop_query: "조회",
  develop_alertExpiringTitle: "{count}개 앱이 곧 만료됩니다",
  develop_expiringItem: "{name} ({expire}에 만료)",
  develop_etc: ", 등",
  develop_hintCreateApp:
    "외부 호출자에게 역량을 승인하고 키, 할당량, 승인을 관리합니다.",
  develop_appTotal: "총 {total}개 앱",
  develop_newApp: "새 앱",
  develop_name: "이름",
  develop_namePlaceholder: "고유 앱 이름",
  develop_nameRequired: "이름을 입력하세요",
  develop_copyAppid: "AppID 복사",
  develop_status: "상태",
  develop_enabled: "활성화됨",
  develop_enabledMsg: "활성화됨",
  develop_disabledMsg: "비활성화됨",
  develop_expireTime: "만료 시간",
  develop_expirePlaceholder: "비우면 만료 없음",
  develop_forever: "영구",
  develop_capabilities: "역량",
  develop_callCount: "호출",
  develop_noData: '아직 앱이 없습니다. "새 앱"으로 생성하세요',
  develop_action: "작업",
  develop_detail: "상세",
  develop_edit: "편집",
  develop_editAppTitle: "앱 편집 · {name}",
  develop_delete: "삭제",
  develop_deleteConfirm:
    '앱 "{name}"을(를) 삭제하면 AppKey가 즉시 무효화됩니다. 되돌릴 수 없습니다. 계속하시겠습니까?',
  develop_deleteConfirmTitle: "삭제 확인",
  develop_deleteSuccess: "앱 삭제됨",
  develop_deleteFail: "삭제 실패",
  develop_embed: "임베드",
  develop_try: "시험",
  develop_tryTitle: "역량 시험",
  develop_tryAlert: "앱의 자격 증명으로 테스트 호출을 보내 원시 응답을 확인합니다.",
  develop_selectCapability: "역량 선택",
  develop_selectCapabilityRequired: "역량을 선택하세요",
  develop_payloadJson: "페이로드 (JSON)",
  develop_payloadPlaceholder: '요청 페이로드, 예: {"agent_name": "..."}',
  develop_invalidJson: "잘못된 JSON",
  develop_result: "결과",
  develop_rawResponse: "원시 응답",
  develop_response: "응답",
  develop_send: "전송",
  develop_close: "닫기",
  develop_trySuccess: "호출 성공",
  develop_tryError: "[{code}] {msg}",
  develop_tryFailMsg: "요청 실패",
  develop_resultTaskId: "작업 ID",
  develop_resultDeletedId: "삭제된 ID",
  develop_resultName: "이름",
  develop_resultReply: "답변",
  develop_resultSid: "SID",
  develop_resultSessionId: "세션 ID",
  develop_resultTotal: "총",
  develop_resultStatus: "상태",
  develop_resultEnabled: "활성화됨",
  develop_resultSourceApp: "원본 앱",
  develop_resultItemsCount: "항목",
  develop_itemsUnit: "항목",
  develop_yes: "예",
  develop_no: "아니요",
  develop_opFail: "작업 실패",
  develop_save: "저장",
  develop_saveSuccess: "앱 저장됨",
  develop_saveFail: "저장 실패",
  develop_loadFail: "로드 실패",
  develop_cancel: "취소",
  develop_copied: "복사됨",
  develop_copyFailManual: "복사 실패, 수동으로 복사하세요",
  develop_desc: "설명",
  develop_descPlaceholder: "이 앱이 무엇에 쓰이는지",
  develop_authCaps: "승인된 역량",
  develop_requiresApproval: "승인 필요",
  develop_requiresApprovalTip: "민감한 역량은 실행 전에 승인되어야 합니다.",
  develop_dailyQuota: "일일 할당량",
  develop_quotaTip: "0 = 무제한; 할당량은 자연일 기준으로 집계됩니다.",
  develop_unlimited: "무제한",
  develop_todayUsage: "오늘 {usage}",
  develop_catTrain: "학습",
  develop_catAgent: "에이전트",
  develop_catChat: "채팅",
  develop_catBot: "봇",
  develop_catEmbed: "임베드",
  develop_keyTitle: "{name} · AppKey",
  develop_keyEncrypted: "암호화됨",
  develop_resetKey: "AppKey 재설정",
  develop_resetKeyTitle: "AppKey 재설정",
  develop_resetKeyConfirm:
    '재설정하면 "{name}"의 현재 AppKey가 즉시 무효화되며, 새 키가 즉시 적용됩니다. 되돌릴 수 없습니다. 계속하시겠습니까?',
  develop_reset: "재설정",
  develop_keyResetSuccess: "AppKey 재설정됨",
  develop_keyResetFail: "재설정 실패",
  develop_createSuccessTitle: "생성 성공",
  develop_saveKeyAlert: "지금 AppKey를 저장하세요",
  develop_saveKeyDesc:
    "AppKey는 한 번만 표시되며, 닫으면 다시 볼 수 없습니다. 안전하게 보관하세요.",
  develop_iSaved: "저장했어요",
  develop_statTodayCalls: "오늘 호출",
  develop_statSuccessRate: "성공률",
  develop_statAvgLatency: "평균 지연",
  develop_statPending: "승인 대기",
  develop_suffixCount: "회",
  develop_suffixRecords: "건",
  develop_suffixItems: "건",
  develop_appLabel: "앱",
  develop_all: "전체",
  develop_category: "카테고리",
  develop_method: "메서드",
  develop_success: "성공",
  develop_failed: "실패",
  develop_denied: "거부됨",
  develop_timeRange: "시간 범위",
  develop_to: "~",
  develop_startTime: "시작 시간",
  develop_endTime: "종료 시간",
  develop_capability: "역량",
  develop_exportCsv: "CSV 내보내기",
  develop_time: "시간",
  develop_latency: "지연",
  develop_latencyTokens: "지연 / 토큰",
  develop_requestPath: "요청 경로",
  develop_resultSummary: "결과 요약",
  develop_noLogs: "아직 호출 로그가 없습니다",
  develop_recent7: "최근 7일",
  develop_recent30: "최근 30일",
  develop_today: "오늘",
  develop_sparkTitle: "{date}: {calls}회 호출",
  develop_topCapabilities: "상위 역량",
  develop_topCapabilitiesShort: "상위 역량",
  develop_filterCapabilityTitle: "{capability}로 필터링",
  develop_logDetailTitle: "호출 로그 상세",
  develop_methodStatus: "메서드 / 상태",
  develop_requestBody: "요청 본문",
  develop_requestBodyShort: "페이로드",
  develop_errorStatus: "오류",
  develop_error: "오류",
  develop_successRate: "성공률",
  develop_quotaHits: "할당량 적중",
  develop_rateLimited: "요율 제한",
  develop_noUsage: "사용량 데이터 없음",
  develop_usageRange: "범위",
  develop_recentDays: "최근 {days}일",
  develop_recentDaysValue: "{days}일",
  develop_calls: "호출",
  develop_usageLoadFail: "사용량 로드 실패",
  develop_sessionId: "세션 ID",
  develop_transport: "전송",
  develop_transportStreamable: "Streamable HTTP",
  develop_transportStdio: "stdio",
  develop_client: "클라이언트",
  develop_duration: "지속 (초)",
  develop_toolCalls: "도구 호출",
  develop_closeReason: "닫기 사유",
  develop_noMcp: "MCP 세션이 없습니다",
  develop_mcpStatSessions: "세션",
  develop_mcpStatToolCalls: "도구 호출",
  develop_mcpStatAvgDuration: "평균 지속 (초)",
  develop_mcpSparkTitle: "{date}: {sessions}개 세션 · {toolCalls}회 도구 호출",
  develop_approvalHint:
    '민감한 역량은 "실행 전 승인"입니다. 아래의 대기 요청을 검토하세요.',
  develop_approvalPending: "{count}건 대기",
  develop_approvalPendingStatus: "대기",
  develop_approve: "승인",
  develop_approveExecute: "승인 및 실행",
  develop_reject: "거부",
  develop_approvedStatus: "승인됨",
  develop_pendingStatus: "대기",
  develop_rejectedStatus: "거부됨",
  develop_expiredStatus: "만료됨",
  develop_execFailStatus: "실패",
  develop_batchApprove: "일괄 승인 ({count})",
  develop_batchApproveTitle: "일괄 승인 {count}",
  develop_batchApproveConfirm:
    "{count}건의 대기 역량 호출을 승인하고 실행합니다. 계속하시겠습니까?",
  develop_batchApproveSuccess: "{count}건 승인됨",
  develop_batchApprovePartial: "{ok}건 승인, {failed}건 실패. {msg}",
  develop_batchApproveFail: "일괄 승인 실패",
  develop_applyTime: "신청 시간",
  develop_reviewTime: "검토 시간",
  develop_reviewNote: "검토 메모",
  develop_noApprovals: "승인 없음",
  develop_approvalLoadFail: "승인 로드 실패",
  develop_approvalDetailTitle: "승인 상세",
  develop_reviewApproveAction: "승인",
  develop_reviewConfirmTitle: "{action}?",
  develop_reviewApproveConfirm:
    '앱 {appid}의 역량 "{capability}"에 대한 호출을 승인하고 실행하시겠습니까?',
  develop_reviewRejectConfirm: '역량 "{capability}"에 대한 호출을 거부하시겠습니까?',
  develop_processed: "처리됨",
  develop_processFail: "처리 실패",
  develop_execResult: "실행 결과",
  develop_execFailTitle: "실행 실패: {error}",
  develop_notifyCfg: "알림 구성",
  develop_notifyCfgTitle: "승인 알림",
  develop_notifyAlert:
    "승인 알림을 보낼 채널을 선택하고 JSON 구성을 제공하세요.",
  develop_enableChannels: "채널 활성화",
  develop_channelConfig: "{name} 구성",
  develop_notifyInvalidJson: "{name}에 대한 잘못된 JSON",
  develop_notifyLoadFail: "알림 구성 로드 실패",
  develop_notifyBroken: "손상된 채널 구성: {broken}",
  develop_saved: "저장됨",
  develop_docsCredTitle: "자격 증명",
  develop_docsCredDesc:
    '각 앱에는 AppID + AppKey가 있습니다. 호출자는 "Bearer {appid}:{appkey}"로 인증하며, 브라우저 측에 AppKey를 노출하지 마세요.',
  develop_docsApprovalTitle: "승인이 필요하지 않나요?",
  develop_docsApprovalDesc:
    '민감한 역량은 첫 호출 시 앱 수준 승인이 필요합니다. 앱의 "승인된 역량" 및 "일일 할당량" 설정에서 활성화하세요.',
  develop_restCard: "REST",
  develop_restDesc: "통합 역량 진입점: 역량 코드로 어떤 역량이든 호출합니다.",
  develop_capListCard: "역량 목록",
  develop_capDesc:
    "플랫폼이 노출하는 모든 공개 역량, 필요한 권한 및 MCP 도구 이름.",
  develop_capCount: "{count}개 역량",
  develop_capabilityName: "이름",
  develop_capabilityCode: "코드",
  develop_requiredPerm: "필요 권한",
  develop_mcpToolName: "MCP 도구",
  develop_noCapabilities: "역량 없음",
  develop_capLoadFail: "역량 로드 실패",
  develop_mcpCard: "MCP",
  develop_mcpDesc: "같은 역량을 MCP(Streamable HTTP)로 노출합니다; 각 호출이 감사됩니다.",
  develop_embedCard: "웹 임베드",
  develop_embedDesc:
    "iframe 또는 Script SDK로 대화를 페이지에 임베드합니다. 토큰은 서버에서 교환됩니다.",
  develop_postMessageEvents: "postMessage 이벤트",
  develop_embedFoot:
    '"임베드" 대화상자의 이벤트 이름과 setToken / sendMessage / resize / destroy 명령을 사용하세요.',
  develop_eventReady: "임베드 페이지 초기화됨 (대상 이름과 만료 시간 포함)",
  develop_eventUserMessage: "사용자가 메시지를 보냄",
  develop_eventReplyStart: "스트리밍 답변 시작",
  develop_eventReplyDelta: "스트리밍 델타 텍스트 (고빈도)",
  develop_eventReplyDone: "답변 완료 (전체 텍스트)",
  develop_eventError: "업무 / 네트워크 / 요율 제한 오류",
  develop_eventTokenExpired: "자격 증명 만료; 호스트가 재교환하고 setToken을 호출해야 함",
  develop_exportFail: "내보내기 실패",
  develop_downloadStarted: "다운로드 시작됨",
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
  develop_embedTitle: "채팅 임베드 · {name}",
  develop_embedKind: "임베드 유형",
  develop_embedApp: "AI 앱",
  develop_embedWorkflow: "워크플로우",
  develop_embedTarget: "임베드 대상",
  develop_embedTargetPlaceholder: "임베드할 대상 선택",
  develop_embedCode: "임베드 코드",
  develop_embedTabIframe: "iframe 임베드",
  develop_embedCopyCode: "코드 복사",
  develop_embedMintToken: "시험 토큰 발급 (2시간)",
  develop_embedCredTitle: "자격 증명 메모",
  develop_embedCredDesc:
    "{access_token}은(는) 단기 자격 증명 자리 표시자입니다: 호스트 백엔드가 appid/appkey로 POST {apiBase}/develop-api/auth/token을 통해 교환하세요. 웹 페이지에 AppKey를 절대 쓰지 마세요. 만료되면 재교환하고 setToken()을 호출해 갱신하세요.",
  develop_embedIssuedTokens: "발급된 토큰",
  asset_embed_noTokens: "발급된 토큰 없음",
  asset_embed_issuer: "발급자",
  asset_embed_expireTime: "만료 시간",
  asset_embed_usage: "사용",
  asset_embed_status: "상태",
  asset_embed_action: "작업",
  asset_embed_valid: "유효",
  asset_embed_revoked: "취소됨",
  asset_embed_revoke: "취소",
  asset_embed_revokeTitle: "토큰 취소",
  asset_embed_revokeConfirm:
    "취소 후 토큰은 즉시 무효화되며, 이를 사용하는 임베드 페이지는 더 이상 대화할 수 없고 되돌릴 수 없습니다. 계속하시겠습니까?",
  asset_embed_revokeFail: "취소 실패",
  asset_embed_revealTitle: "토큰 생성됨",
  asset_embed_revealAlertTitle: "지금 코드에 복사하여 붙여넣으세요",
  asset_embed_revealAlertDesc: "토큰은 여기에 한 번만 표시됩니다. 만료 후 재발급하세요.",
  asset_embed_applyCode: "코드에 삽입",
  asset_embed_applySuccess: "코드에 삽입됨, 복사 가능",
  asset_embed_mint: "토큰 생성",
  asset_embed_issued: "발급된 토큰",
  asset_embed_tokenHint: "자격 증명 설명",
  asset_embed_mintFail: "발급 실패",
  develop_embedNoTokens: "토큰 없음 (교환 및 시험 토큰이 여기에 표시됨)",
  develop_embedKindShort: "종류",
  develop_embedTrialTicket: "시험",
  develop_embedIssuedTicket: "교환",
  develop_embedTargetShort: "대상",
  develop_embedExpireTime: "만료 시간",
  develop_embedUsage: "사용",
  develop_embedStatus: "상태",
  develop_embedRevoked: "회수됨",
  develop_embedValid: "유효",
  develop_embedAction: "작업",
  develop_embedRevoke: "회수",
  develop_embedRevokeFail: "회수 실패",
  develop_embedRevokeTitle: "토큰 회수",
  develop_embedRevokeConfirm:
    "회수 후 토큰이 즉시 무효화되며, 이를 사용하는 임베드 페이지는 더 이상 채팅할 수 없습니다. 되돌릴 수 없습니다. 계속하시겠습니까?",
  develop_embedEvents: "이벤트 계약",
  develop_embedEventsNote:
    '업스트림 봉투 출처 = ai-embed / 버전 = 1; 전체 페이로드와 다운스트림 명령은 "접근 문서" 탭에 있습니다.',
  develop_embedRevealTitle: "시험 토큰",
  develop_embedRevealAlertTitle: "지금 코드에 복사하여 붙여넣으세요",
  develop_embedRevealAlertDesc: "토큰은 여기서 한 번만 표시됩니다; 만료 시 재발급하면 됩니다.",
  develop_embedApplyCode: "코드에 채우기",
  develop_embedApplySuccess: "코드에 채워짐, 복사 준비 완료",
  develop_embedIframeTitle: "AI 채팅",
  develop_embedTargetsLoadFail: "대상 목록 로드 실패",
  develop_embedMintFail: "발급 실패",

  // ===== embed (公开嵌入页) =====
  embed_brand: "AI 어시스턴트",
  embed_missingTitle: "접근 토큰 누락",
  embed_missingDesc:
    "이 페이지에는 일회성 접근 토큰이 필요합니다. 백엔드에서 생성하고 ?token=...로 URL을 여세요.",
  embed_conversation: "대화",
  embed_aiAssistant: "AI 어시스턴트",
  embed_you: "나",
  embed_welcome: "안녕하세요, 무엇을 도와드릴까요?",
  embed_hint: "아래에 질문을 입력하여 채팅하세요",
  embed_inputPlaceholder: "질문을 입력하세요...",
  embed_send: "전송",
  embed_stopGenerate: "생성 중지",
  embed_sourcesCount: "{count}개 출처",
  embed_knowledgePiece: "지식",
  embed_retry: "재시도",
  embed_metaLoadFail: "대화 로드 실패",
  embed_noPermMsg: "이 대화에 접근할 권한이 없습니다",
  embed_rateLimitedMsg: "요청이 너무 많습니다, 나중에 다시 시도하세요",
  embed_rateLimitedNotice: "요청이 너무 많습니다, 나중에 다시 시도하세요",
  embed_notFoundMsg: "대상을 찾을 수 없습니다",
  embed_notFoundNotice: "대상을 찾을 수 없습니다",
  embed_networkMsg: "네트워크 오류, 다시 시도하세요",
  embed_networkNotice: "네트워크 오류, 다시 시도하세요",
  embed_expiredTitle: "접근 토큰 만료",
  embed_expiredDesc:
    "접근 토큰이 만료되었습니다. 호스트에게 재교환 후 setToken()을 호출하도록 요청하세요.",
  embed_forbiddenTitle: "권한 없음",
  embed_forbiddenDesc: "이 대화에 접근할 권한이 없습니다.",
};
