"""读路径白名单与敏感列默认集合（从 service.py 拆出）。

``SYSTEM_ALLOWED_TABLES``：本系统可查表的**名字白名单**（不含外部业务库）；
``_ONT_IMPORT_EXCLUDE``：导入本体时跳过的系统/中间表；
``_DEFAULT_SENSITIVE_COLS``：未登记资产时按列名兜底判定敏感列。
"""
from __future__ import annotations

_ONT_IMPORT_EXCLUDE: set[str] = {
    # 迁移 / 调度
    "alembic_version", "apscheduler_jobs",
    # 框架运行时（Agno 会话）
    "agno_sessions", "agno_schema_versions",
    # 纯日志
    "sys_log", "ai_call_logs", "ai_search_logs", "ai_chunk_annotation_logs",
    "ai_workflow_run_logs", "video_record_execution_logs",
    # 代码生成器脚手架
    "gen_demo", "gen_demo01",
    # 会话/消息运行时
    "ai_assistant_sessions", "ai_assistant_messages",
    # 向量 / schema 注册 / 配置 / 前端布局
    "ai_query_asset_vectors", "ai_query_schema", "ai_query_settings", "ai_query_kg_layout",
    # 纯多对多关联表
    "sys_role_menus", "sys_user_roles", "sys_user_positions", "sys_role_depts",
    "ai_knowledge_entity_chunks",
    # 调度/版本快照
    "ai_workflow_schedules", "ai_workflow_versions",
}

SYSTEM_ALLOWED_TABLES = {
    "ai_call_logs", "ai_assistant_messages", "ai_assistant_sessions", "ai_apps", "ai_agents",
    "ai_models", "ai_providers", "ai_skills", "ai_tools", "ai_prompts",
    "ai_reports", "ai_workflows", "annotation_dataset", "annotation_record",
    "annotation_task", "synthesis_job",
    "train_tasks", "train_models", "train_evals", "train_predicts", "train_deploys",
    "train_schedules", "train_model_repos",
    "video_alarm_records", "video_alarm_rules", "video_cameras",
    "video_camera_groups", "video_algorithms", "video_algorithm_tasks",
    "video_edge_devices", "video_edge_events", "video_face_gallery", "video_layouts",
    "video_record_files", "video_record_plans", "video_record_execution_logs",
    "sys_user", "sys_user_notification",
}

_DEFAULT_SENSITIVE_COLS: frozenset[str] = frozenset({
    "password", "passwd", "pwd", "secret", "token",
    "access_token", "refresh_token", "api_token",
    "api_key", "apikey", "private_key", "encrypt_key",
    "auth_secret", "credential", "salt",
    "user_passwd", "user_password", "login_password",
    "auth_key", "sign_key", "secret_key", "passkey", "passcode",
})
