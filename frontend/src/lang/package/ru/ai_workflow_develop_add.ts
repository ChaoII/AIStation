export default {
  // ===== develop (开放平台) =====
  develop_tabApps: "Приложения",
  develop_tabLogs: "Журналы вызовов",
  develop_tabMcp: "MCP-сессии",
  develop_tabUsage: "Использование",
  develop_tabApprovals: "Согласования",
  develop_tabDocs: "Документация по доступу",
  develop_keyword: "Ключевое слово",
  develop_keywordPlaceholder: "Название / AppID",
  develop_query: "Запрос",
  develop_alertExpiringTitle: "{count} приложений скоро истекут",
  develop_expiringItem: "{name} истекает в {expire}",
  develop_etc: ", и т.д.",
  develop_hintCreateApp:
    "Предоставляйте возможности внешним вызывающим; управляйте ключами, квотами и согласованием.",
  develop_appTotal: "Всего приложений: {total}",
  develop_newApp: "Новое приложение",
  develop_name: "Название",
  develop_namePlaceholder: "Уникальное имя приложения",
  develop_nameRequired: "Введите название",
  develop_copyAppid: "Скопировать AppID",
  develop_status: "Статус",
  develop_enabled: "Включено",
  develop_enabledMsg: "Включено",
  develop_disabledMsg: "Отключено",
  develop_expireTime: "Время истечения",
  develop_expirePlaceholder: "Оставьте пустым, чтобы срок не истекал",
  develop_forever: "Навсегда",
  develop_capabilities: "Возможности",
  develop_callCount: "Вызовы",
  develop_noData: 'Приложений пока нет. Создайте с помощью «Новое приложение»',
  develop_action: "Действия",
  develop_detail: "Детали",
  develop_edit: "Изменить",
  develop_editAppTitle: "Изменить приложение · {name}",
  develop_delete: "Удалить",
  develop_deleteConfirm:
    'Это удалит приложение «{name}», и его AppKey станет недействительным немедленно; это действие необратимо. Продолжить?',
  develop_deleteConfirmTitle: "Подтверждение удаления",
  develop_deleteSuccess: "Приложение удалено",
  develop_deleteFail: "Ошибка удаления",
  develop_embed: "Встраивание",
  develop_try: "Попробовать",
  develop_tryTitle: "Попробовать возможность",
  develop_tryAlert: "Отправьте тестовый вызов с учётными данными приложения, чтобы увидеть необработанный ответ.",
  develop_selectCapability: "Выберите возможность",
  develop_selectCapabilityRequired: "Пожалуйста, выберите возможность",
  develop_payloadJson: "Полезная нагрузка (JSON)",
  develop_payloadPlaceholder: 'Полезная нагрузка запроса, например {"agent_name": "..."}',
  develop_invalidJson: "Неверный JSON",
  develop_result: "Результат",
  develop_rawResponse: "Необработанный ответ",
  develop_response: "Ответ",
  develop_send: "Отправить",
  develop_close: "Закрыть",
  develop_trySuccess: "Вызов успешен",
  develop_tryError: "[{code}] {msg}",
  develop_tryFailMsg: "Ошибка запроса",
  develop_resultTaskId: "ID задачи",
  develop_resultDeletedId: "Удалённый ID",
  develop_resultName: "Название",
  develop_resultReply: "Ответ",
  develop_resultSid: "SID",
  develop_resultSessionId: "ID сессии",
  develop_resultTotal: "Всего",
  develop_resultStatus: "Статус",
  develop_resultEnabled: "Включено",
  develop_resultSourceApp: "Исходное приложение",
  develop_resultItemsCount: "Элементы",
  develop_itemsUnit: "элементов",
  develop_yes: "Да",
  develop_no: "Нет",
  develop_opFail: "Ошибка операции",
  develop_save: "Сохранить",
  develop_saveSuccess: "Приложение сохранено",
  develop_saveFail: "Ошибка сохранения",
  develop_loadFail: "Не удалось загрузить",
  develop_cancel: "Отмена",
  develop_copied: "Скопировано",
  develop_copyFailManual: "Ошибка копирования, скопируйте вручную",
  develop_desc: "Описание",
  develop_descPlaceholder: "Для чего используется это приложение",
  develop_authCaps: "Авторизованные возможности",
  develop_requiresApproval: "Требуется согласование",
  develop_requiresApprovalTip: "Чувствительные возможности должны быть одобрены перед выполнением.",
  develop_dailyQuota: "Дневная квота",
  develop_quotaTip: "0 = без ограничений; квота считается за календарный день.",
  develop_unlimited: "Без ограничений",
  develop_todayUsage: "Сегодня {usage}",
  develop_catTrain: "Обучение",
  develop_catAgent: "Агент",
  develop_catChat: "Чат",
  develop_catBot: "Бот",
  develop_catEmbed: "Встраивание",
  develop_keyTitle: "{name} · AppKey",
  develop_keyEncrypted: "Зашифрован",
  develop_resetKey: "Сбросить AppKey",
  develop_resetKeyTitle: "Сбросить AppKey",
  develop_resetKeyConfirm:
    'Сброс немедленно сделает текущий AppKey приложения «{name}» недействительным; новый ключ вступает в силу сразу, и это действие необратимо. Продолжить?',
  develop_reset: "Сбросить",
  develop_keyResetSuccess: "AppKey сброшен",
  develop_keyResetFail: "Ошибка сброса",
  develop_createSuccessTitle: "Успешно создано",
  develop_saveKeyAlert: "Сохраните AppKey сейчас",
  develop_saveKeyDesc:
    "AppKey показывается только один раз; после закрытия вы не сможете его снова увидеть. Храните его надёжно.",
  develop_iSaved: "Я его сохранил",
  develop_statTodayCalls: "Вызовы сегодня",
  develop_statSuccessRate: "Доля успешных",
  develop_statAvgLatency: "Средняя задержка",
  develop_statPending: "Ожидающие согласования",
  develop_suffixCount: "вызовов",
  develop_suffixRecords: "записей",
  develop_suffixItems: "элементов",
  develop_appLabel: "Приложение",
  develop_all: "Все",
  develop_category: "Категория",
  develop_method: "Метод",
  develop_success: "Успешно",
  develop_failed: "Ошибка",
  develop_denied: "Отказано",
  develop_timeRange: "Диапазон времени",
  develop_to: "до",
  develop_startTime: "Время начала",
  develop_endTime: "Время окончания",
  develop_capability: "Возможность",
  develop_exportCsv: "Экспорт CSV",
  develop_time: "Время",
  develop_latency: "Задержка",
  develop_latencyTokens: "Задержка / токены",
  develop_requestPath: "Путь запроса",
  develop_resultSummary: "Сводка результата",
  develop_noLogs: "Журналов вызовов пока нет",
  develop_recent7: "Последние 7 дней",
  develop_recent30: "Последние 30 дней",
  develop_today: "Сегодня",
  develop_sparkTitle: "{date}: {calls} вызовов",
  develop_topCapabilities: "Топ возможностей",
  develop_topCapabilitiesShort: "Топ возможностей",
  develop_filterCapabilityTitle: "Фильтр по {capability}",
  develop_logDetailTitle: "Детали журнала вызовов",
  develop_methodStatus: "Метод / статус",
  develop_requestBody: "Тело запроса",
  develop_requestBodyShort: "Полезная нагрузка",
  develop_errorStatus: "Ошибка",
  develop_error: "Ошибка",
  develop_successRate: "Доля успешных",
  develop_quotaHits: "Попадания в квоту",
  develop_rateLimited: "Ограничение частоты",
  develop_noUsage: "Нет данных об использовании",
  develop_usageRange: "Диапазон",
  develop_recentDays: "Последние {days} дней",
  develop_recentDaysValue: "{days}д",
  develop_calls: "Вызовы",
  develop_usageLoadFail: "Не удалось загрузить данные об использовании",
  develop_sessionId: "ID сессии",
  develop_transport: "Транспорт",
  develop_transportStreamable: "Streamable HTTP",
  develop_transportStdio: "stdio",
  develop_client: "Клиент",
  develop_duration: "Длительность (с)",
  develop_toolCalls: "Вызовы инструментов",
  develop_closeReason: "Причина закрытия",
  develop_noMcp: "Нет MCP-сессий",
  develop_mcpStatSessions: "Сессии",
  develop_mcpStatToolCalls: "Вызовы инструментов",
  develop_mcpStatAvgDuration: "Средняя длительность (с)",
  develop_mcpSparkTitle: "{date}: {sessions} сессий · {toolCalls} вызовов инструментов",
  develop_approvalHint:
    'Чувствительные возможности — это «одобрять перед выполнением»; просмотрите ожидающие заявки ниже.',
  develop_approvalPending: "{count} ожидают",
  develop_approvalPendingStatus: "Ожидает",
  develop_approve: "Одобрить",
  develop_approveExecute: "Одобрить и выполнить",
  develop_reject: "Отклонить",
  develop_approvedStatus: "Одобрено",
  develop_pendingStatus: "Ожидает",
  develop_rejectedStatus: "Отклонено",
  develop_expiredStatus: "Истекло",
  develop_execFailStatus: "Ошибка",
  develop_batchApprove: "Пакетно одобрить ({count})",
  develop_batchApproveTitle: "Пакетно одобрить {count}",
  develop_batchApproveConfirm:
    "Это одобрит и выполнит {count} ожидающих вызовов возможностей. Продолжить?",
  develop_batchApproveSuccess: "Одобрено запросов: {count}",
  develop_batchApprovePartial: "{ok} одобрено, {failed} ошибок. {msg}",
  develop_batchApproveFail: "Ошибка пакетного одобрения",
  develop_applyTime: "Время подачи",
  develop_reviewTime: "Время рассмотрения",
  develop_reviewNote: "Примечание рецензента",
  develop_noApprovals: "Нет согласований",
  develop_approvalLoadFail: "Не удалось загрузить согласования",
  develop_approvalDetailTitle: "Детали согласования",
  develop_reviewApproveAction: "Одобрить",
  develop_reviewConfirmTitle: "{action}?",
  develop_reviewApproveConfirm:
    'Одобрить вызов возможности «{capability}» приложения {appid} и выполнить его?',
  develop_reviewRejectConfirm: 'Отклонить вызов возможности «{capability}»?',
  develop_processed: "Обработано",
  develop_processFail: "Ошибка обработки",
  develop_execResult: "Результат выполнения",
  develop_execFailTitle: "Ошибка выполнения: {error}",
  develop_notifyCfg: "Конфигурация уведомлений",
  develop_notifyCfgTitle: "Уведомление о согласовании",
  develop_notifyAlert:
    "Выберите, какие каналы отправляют уведомления о согласовании, и укажите их JSON-конфигурацию.",
  develop_enableChannels: "Включённые каналы",
  develop_channelConfig: "Конфигурация {name}",
  develop_notifyInvalidJson: "Неверный JSON для {name}",
  develop_notifyLoadFail: "Не удалось загрузить конфигурацию уведомлений",
  develop_notifyBroken: "Нерабочая конфигурация канала: {broken}",
  develop_saved: "Сохранено",
  develop_docsCredTitle: "Учётные данные",
  develop_docsCredDesc:
    'У каждого приложения есть AppID + AppKey. Вызывающие аутентифицируются через «Bearer {appid}:{appkey}»; никогда не раскрывайте AppKey на стороне браузера.',
  develop_docsApprovalTitle: "Согласование не требуется?",
  develop_docsApprovalDesc:
    'Чувствительные возможности требуют согласования на уровне приложения при первом вызове; включите его в настройках «Авторизованные возможности» и «Дневная квота» приложения.',
  develop_restCard: "REST",
  develop_restDesc: "Единая точка входа возможностей: используйте код возможности для вызова любой возможности.",
  develop_capListCard: "Список возможностей",
  develop_capDesc:
    "Все открытые возможности, предоставляемые платформой, с необходимыми правами и именами MCP-инструментов.",
  develop_capCount: "{count} возможностей",
  develop_capabilityName: "Название",
  develop_capabilityCode: "Код",
  develop_requiredPerm: "Необходимое право",
  develop_mcpToolName: "MCP-инструмент",
  develop_noCapabilities: "Нет возможностей",
  develop_capLoadFail: "Не удалось загрузить возможности",
  develop_mcpCard: "MCP",
  develop_mcpDesc: "Предоставляйте те же возможности через MCP (Streamable HTTP); каждый вызов аудируется.",
  develop_embedCard: "Встраивание в веб",
  develop_embedDesc:
    "Встраивайте беседу на свою страницу через iframe или Script SDK. Токены обмениваются вашим сервером.",
  develop_postMessageEvents: "События postMessage",
  develop_embedFoot:
    'Используйте эти имена событий и команды setToken / sendMessage / resize / destroy из диалога «Встраивание».',
  develop_eventReady: "Страница встраивания инициализирована (включая имя цели и время истечения)",
  develop_eventUserMessage: "Пользователь отправил сообщение",
  develop_eventReplyStart: "Начало потокового ответа",
  develop_eventReplyDelta: "Дельта потокового текста (высокая частота)",
  develop_eventReplyDone: "Ответ завершён (полный текст)",
  develop_eventError: "Бизнес- / сетевая / ошибка ограничения частоты",
  develop_eventTokenExpired: "Учётные данные истекли; хост должен повторно обменять и вызвать setToken",
  develop_exportFail: "Ошибка экспорта",
  develop_downloadStarted: "Скачивание началось",
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
  develop_embedTitle: "Встраивание чата · {name}",
  develop_embedKind: "Тип встраивания",
  develop_embedApp: "ИИ-приложение",
  develop_embedWorkflow: "Рабочий процесс",
  develop_embedTarget: "Цель встраивания",
  develop_embedTargetPlaceholder: "Выберите цель для встраивания",
  develop_embedCode: "Код встраивания",
  develop_embedTabIframe: "Встраивание iframe",
  develop_embedCopyCode: "Скопировать код",
  develop_embedMintToken: "Создать пробный токен (2 ч)",
  develop_embedCredTitle: "Примечание об учётных данных",
  develop_embedCredDesc:
    "{access_token} — это заполнитель краткосрочного токена: ваш бэкенд должен обменять его через POST {apiBase}/develop-api/auth/token с использованием appid/appkey. Никогда не записывайте AppKey в веб-страницу. Когда токен истечёт, обменяйте его заново и вызовите setToken() для продления.",
  develop_embedIssuedTokens: "Выданные токены",
  asset_embed_noTokens: "Выпущенных токенов нет",
  asset_embed_issuer: "Эмитент",
  asset_embed_expireTime: "Время истечения",
  asset_embed_usage: "Использование",
  asset_embed_status: "Статус",
  asset_embed_action: "Действие",
  asset_embed_valid: "Действителен",
  asset_embed_revoked: "Отозван",
  asset_embed_revoke: "Отозвать",
  asset_embed_revokeTitle: "Отозвать токен",
  asset_embed_revokeConfirm:
    "После отзыва токен сразу становится недействительным; встроенная страница, использующая его, больше не сможет общаться, и это необратимо. Продолжить?",
  asset_embed_revokeFail: "Ошибка отзыва",
  asset_embed_revealTitle: "Токен создан",
  asset_embed_revealAlertTitle: "Скопируйте и вставьте в код сейчас",
  asset_embed_revealAlertDesc: "Токен отображается здесь только один раз; при истечении перевыпустите его.",
  asset_embed_applyCode: "Вставить в код",
  asset_embed_applySuccess: "Вставлено в код, готово к копированию",
  asset_embed_mint: "Создать токен",
  asset_embed_issued: "Выпущенные токены",
  asset_embed_tokenHint: "Примечание о доступе",
  asset_embed_mintFail: "Ошибка выпуска",
  develop_embedNoTokens: "Нет токенов (обменянные и пробные появятся здесь)",
  develop_embedKindShort: "Тип",
  develop_embedTrialTicket: "Пробный",
  develop_embedIssuedTicket: "Обмен",
  develop_embedTargetShort: "Цель",
  develop_embedExpireTime: "Время истечения",
  develop_embedUsage: "Использование",
  develop_embedStatus: "Статус",
  develop_embedRevoked: "Отозван",
  develop_embedValid: "Действителен",
  develop_embedAction: "Действие",
  develop_embedRevoke: "Отозвать",
  develop_embedRevokeFail: "Ошибка отзыва",
  develop_embedRevokeTitle: "Отозвать токен",
  develop_embedRevokeConfirm:
    "После отзыва токен немедленно становится недействительным; встроенная страница, использующая его, больше не сможет вести чат, и это действие необратимо. Продолжить?",
  develop_embedEvents: "Контракт событий",
  develop_embedEventsNote:
    'Источник конверта сверху = ai-embed / версия = 1; полная полезная нагрузка и нижестоящие команды находятся на вкладке «Документация по доступу».',
  develop_embedRevealTitle: "Пробный токен",
  develop_embedRevealAlertTitle: "Скопируйте и вставьте в свой код сейчас",
  develop_embedRevealAlertDesc: "Токен здесь показывается только один раз; просто перевыпустите его при истечении.",
  develop_embedApplyCode: "Вставить в код",
  develop_embedApplySuccess: "Вставлено в код, готово к копированию",
  develop_embedIframeTitle: "ИИ-чат",
  develop_embedTargetsLoadFail: "Не удалось загрузить список целей",
  develop_embedMintFail: "Ошибка создания токена",

  // ===== embed (公开嵌入页) =====
  embed_brand: "ИИ-ассистент",
  embed_missingTitle: "Отсутствует токен доступа",
  embed_missingDesc:
    "Эта страница требует одноразовый токен доступа. Сгенерируйте его на своём бэкенде и откройте URL с ?token=...",
  embed_conversation: "Беседа",
  embed_aiAssistant: "ИИ-ассистент",
  embed_you: "Вы",
  embed_welcome: "Здравствуйте, чем могу помочь?",
  embed_hint: "Введите ваш вопрос ниже, чтобы начать чат",
  embed_inputPlaceholder: "Введите ваш вопрос...",
  embed_send: "Отправить",
  embed_stopGenerate: "Остановить генерацию",
  embed_sourcesCount: "{count} источников",
  embed_knowledgePiece: "Знания",
  embed_retry: "Повторить",
  embed_metaLoadFail: "Не удалось загрузить беседу",
  embed_noPermMsg: "Нет прав на доступ к этой беседе",
  embed_rateLimitedMsg: "Слишком много запросов, попробуйте позже",
  embed_rateLimitedNotice: "Слишком много запросов, попробуйте позже",
  embed_notFoundMsg: "Цель не найдена",
  embed_notFoundNotice: "Цель не найдена",
  embed_networkMsg: "Сетевая ошибка, попробуйте снова",
  embed_networkNotice: "Сетевая ошибка, попробуйте снова",
  embed_expiredTitle: "Срок действия токена доступа истёк",
  embed_expiredDesc:
    "Срок действия токена доступа истёк. Попросите хост повторно обменять его и вызвать setToken().",
  embed_forbiddenTitle: "Нет прав",
  embed_forbiddenDesc: "У вас нет прав на доступ к этой беседе.",
};
