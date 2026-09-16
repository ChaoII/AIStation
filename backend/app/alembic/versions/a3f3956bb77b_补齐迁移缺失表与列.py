"""补齐迁移路径缺失的模型表与列（对齐 MappedBase.metadata）

Revision ID: a3f3956bb77b
Revises: b2c3d4e5f6a7
Create Date: 2026-09-16

背景：base 迁移（0dfa7af72c50）由早期模型自动生成，未包含 AI/标注/边缘设备/预测/
录制执行日志等模块的表，也缺少后续模型新增的列；纯迁移建库会在查询时
`UndefinedTable` / `UndefinedColumn` 500。

本迁移一次性把「迁移路径」补齐到与模型元数据一致，并且**幂等**：
- 建表用 `CREATE TABLE IF NOT EXISTS`，建索引用 `CREATE INDEX IF NOT EXISTS`；
- 补列用 `ADD COLUMN IF NOT EXISTS`；
- 外键按「约束列」探测后再建。
因此「先重启应用（兜底补列/兜底建表）、再跑迁移」与「先迁移、再重启」两种顺序都成立，
不会出现 DuplicateTable / DuplicateColumn。
"""
import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

from app.alembic.dialect_compat import (
    dialect_name,
    is_postgres,
    is_sqlite,
    portable_add_column,
)

# revision identifiers, used by Alembic.
revision: str = "a3f3956bb77b"
down_revision: str | Sequence[str] | None = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# 新增表用到的 PG 枚举类型；base 迁移未创建，需先建（幂等）
_ENUM_DDL: list[str] = [
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'imagestatus') THEN
            CREATE TYPE imagestatus AS ENUM ('UNANNOTATED', 'IN_PROGRESS', 'ANNOTATED');
        END IF;
    END
    $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'annotationtype') THEN
            CREATE TYPE annotationtype AS ENUM (
                'DETECTION', 'ROTATED_DETECTION', 'SEGMENTATION',
                'KEYPOINT', 'OCR', 'CLASSIFICATION'
            );
        END IF;
    END
    $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'trainframework') THEN
            CREATE TYPE trainframework AS ENUM (
                'PADDLEX', 'ULTRALYTICS', 'PYTORCH_OCR_DET', 'PYTORCH_OCR_REC'
            );
        END IF;
    END
    $$;
    """,
    """
    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'trainstatus') THEN
            CREATE TYPE trainstatus AS ENUM (
                'PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED'
            );
        END IF;
    END
    $$;
    """,
]

# 迁移路径缺失的表（按 FK 依赖排序；标注表需先于其引用者创建）
_TABLE_DDL: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS annotation_dataset (
        name VARCHAR(128) NOT NULL,
        description TEXT,
        bucket_name VARCHAR(64) NOT NULL,
        image_count INTEGER NOT NULL,
        annotated_count INTEGER NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_created_id ON annotation_dataset (created_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_created_time ON annotation_dataset (created_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_deleted_id ON annotation_dataset (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_deleted_time ON annotation_dataset (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_id ON annotation_dataset (id);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_is_deleted ON annotation_dataset (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_status ON annotation_dataset (status);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_updated_id ON annotation_dataset (updated_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_dataset_updated_time ON annotation_dataset (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_dataset_uuid ON annotation_dataset (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS annotation_image (
        dataset_id INTEGER NOT NULL,
        filename VARCHAR(255) NOT NULL,
        object_key VARCHAR(512) NOT NULL,
        width INTEGER NOT NULL,
        height INTEGER NOT NULL,
        status imagestatus NOT NULL,
        locked_by INTEGER,
        locked_at TIMESTAMP WITHOUT TIME ZONE,
        annotation_count INTEGER NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(dataset_id) REFERENCES annotation_dataset (id),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_annotation_image_created_id ON annotation_image (created_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_created_time ON annotation_image (created_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_deleted_id ON annotation_image (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_deleted_time ON annotation_image (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_id ON annotation_image (id);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_is_deleted ON annotation_image (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_updated_id ON annotation_image (updated_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_image_updated_time ON annotation_image (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_image_uuid ON annotation_image (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS annotation_task (
        dataset_id INTEGER NOT NULL,
        name VARCHAR(128) NOT NULL,
        task_type annotationtype NOT NULL,
        status VARCHAR(16) NOT NULL,
        assignees JSONB NOT NULL,
        classes JSONB NOT NULL,
        classification_mode VARCHAR(20),
        progress INTEGER NOT NULL,
        completed_at TIMESTAMP WITHOUT TIME ZONE,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(dataset_id) REFERENCES annotation_dataset (id),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_annotation_task_created_id ON annotation_task (created_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_created_time ON annotation_task (created_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_deleted_id ON annotation_task (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_deleted_time ON annotation_task (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_id ON annotation_task (id);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_is_deleted ON annotation_task (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_updated_id ON annotation_task (updated_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_task_updated_time ON annotation_task (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_task_uuid ON annotation_task (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS annotation_record (
        task_id INTEGER NOT NULL,
        image_id INTEGER NOT NULL,
        annotation_data JSONB NOT NULL,
        version INTEGER NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(task_id) REFERENCES annotation_task (id),
        FOREIGN KEY(image_id) REFERENCES annotation_image (id),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_annotation_record_created_id ON annotation_record (created_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_created_time ON annotation_record (created_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_deleted_id ON annotation_record (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_deleted_time ON annotation_record (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_id ON annotation_record (id);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_is_deleted ON annotation_record (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_status ON annotation_record (status);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_updated_id ON annotation_record (updated_id);
    CREATE INDEX IF NOT EXISTS ix_annotation_record_updated_time ON annotation_record (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_annotation_record_uuid ON annotation_record (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_providers (
        name VARCHAR(128) NOT NULL,
        protocol VARCHAR(32) NOT NULL,
        base_url VARCHAR(512) NOT NULL,
        api_key VARCHAR(512) NOT NULL,
        extra_headers JSONB,
        enabled BOOLEAN NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (name),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_ai_providers_created_id ON ai_providers (created_id);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_created_time ON ai_providers (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_deleted_id ON ai_providers (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_deleted_time ON ai_providers (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_id ON ai_providers (id);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_is_deleted ON ai_providers (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_status ON ai_providers (status);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_updated_id ON ai_providers (updated_id);
    CREATE INDEX IF NOT EXISTS ix_ai_providers_updated_time ON ai_providers (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_providers_uuid ON ai_providers (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_models (
        name VARCHAR(128) NOT NULL,
        provider VARCHAR(32) NOT NULL,
        provider_id INTEGER,
        usage VARCHAR(16) NOT NULL,
        capabilities JSONB,
        context_window INTEGER,
        base_url VARCHAR(512) NOT NULL,
        api_key VARCHAR(512) NOT NULL,
        model VARCHAR(128) NOT NULL,
        temperature FLOAT NOT NULL,
        max_tokens INTEGER NOT NULL,
        enabled BOOLEAN NOT NULL,
        is_default BOOLEAN NOT NULL,
        extra_headers JSONB,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (name),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_ai_models_created_id ON ai_models (created_id);
    CREATE INDEX IF NOT EXISTS ix_ai_models_created_time ON ai_models (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_models_deleted_id ON ai_models (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_ai_models_deleted_time ON ai_models (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_models_id ON ai_models (id);
    CREATE INDEX IF NOT EXISTS ix_ai_models_is_deleted ON ai_models (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_models_provider_id ON ai_models (provider_id);
    CREATE INDEX IF NOT EXISTS ix_ai_models_status ON ai_models (status);
    CREATE INDEX IF NOT EXISTS ix_ai_models_updated_id ON ai_models (updated_id);
    CREATE INDEX IF NOT EXISTS ix_ai_models_updated_time ON ai_models (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_models_uuid ON ai_models (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_prompts (
        name VARCHAR(128) NOT NULL,
        category VARCHAR(32) NOT NULL,
        blocks JSONB,
        variables JSONB,
        version INTEGER NOT NULL,
        enabled BOOLEAN NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (name),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_created_id ON ai_prompts (created_id);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_created_time ON ai_prompts (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_deleted_id ON ai_prompts (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_deleted_time ON ai_prompts (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_id ON ai_prompts (id);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_is_deleted ON ai_prompts (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_status ON ai_prompts (status);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_updated_id ON ai_prompts (updated_id);
    CREATE INDEX IF NOT EXISTS ix_ai_prompts_updated_time ON ai_prompts (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_prompts_uuid ON ai_prompts (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_apps (
        name VARCHAR(128) NOT NULL,
        icon VARCHAR(64) NOT NULL,
        model_id INTEGER,
        prompt_id INTEGER,
        tools JSONB,
        output_format VARCHAR(16) NOT NULL,
        input_schema JSONB,
        enabled BOOLEAN NOT NULL,
        "order" INTEGER NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (name),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_ai_apps_created_id ON ai_apps (created_id);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_created_time ON ai_apps (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_deleted_id ON ai_apps (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_deleted_time ON ai_apps (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_id ON ai_apps (id);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_is_deleted ON ai_apps (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_status ON ai_apps (status);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_updated_id ON ai_apps (updated_id);
    CREATE INDEX IF NOT EXISTS ix_ai_apps_updated_time ON ai_apps (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_apps_uuid ON ai_apps (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_sessions (
        app_id INTEGER,
        user_id INTEGER,
        title VARCHAR(255) NOT NULL,
        message_count INTEGER NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        PRIMARY KEY (id)
    );
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_app_id ON ai_sessions (app_id);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_created_time ON ai_sessions (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_deleted_time ON ai_sessions (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_id ON ai_sessions (id);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_is_deleted ON ai_sessions (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_status ON ai_sessions (status);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_updated_time ON ai_sessions (updated_time);
    CREATE INDEX IF NOT EXISTS ix_ai_sessions_user_id ON ai_sessions (user_id);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_sessions_uuid ON ai_sessions (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_messages (
        session_id INTEGER NOT NULL,
        app_id INTEGER,
        role VARCHAR(16) NOT NULL,
        parts JSONB,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        PRIMARY KEY (id)
    );
    CREATE INDEX IF NOT EXISTS ix_ai_messages_created_time ON ai_messages (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_messages_deleted_time ON ai_messages (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_messages_id ON ai_messages (id);
    CREATE INDEX IF NOT EXISTS ix_ai_messages_is_deleted ON ai_messages (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_messages_session_id ON ai_messages (session_id);
    CREATE INDEX IF NOT EXISTS ix_ai_messages_status ON ai_messages (status);
    CREATE INDEX IF NOT EXISTS ix_ai_messages_updated_time ON ai_messages (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_messages_uuid ON ai_messages (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_call_logs (
        model_name VARCHAR(128) NOT NULL,
        usage VARCHAR(32) NOT NULL,
        latency_ms INTEGER NOT NULL,
        result VARCHAR(16) NOT NULL,
        error TEXT,
        app_id INTEGER,
        user_id INTEGER,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        PRIMARY KEY (id)
    );
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_created_time ON ai_call_logs (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_deleted_time ON ai_call_logs (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_id ON ai_call_logs (id);
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_is_deleted ON ai_call_logs (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_status ON ai_call_logs (status);
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_updated_time ON ai_call_logs (updated_time);
    CREATE INDEX IF NOT EXISTS ix_ai_call_logs_user_id ON ai_call_logs (user_id);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_call_logs_uuid ON ai_call_logs (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_reports (
        title VARCHAR(255) NOT NULL,
        content TEXT NOT NULL,
        source JSONB,
        app_id INTEGER,
        session_id INTEGER,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_ai_reports_created_id ON ai_reports (created_id);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_created_time ON ai_reports (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_deleted_id ON ai_reports (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_deleted_time ON ai_reports (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_id ON ai_reports (id);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_is_deleted ON ai_reports (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_status ON ai_reports (status);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_updated_id ON ai_reports (updated_id);
    CREATE INDEX IF NOT EXISTS ix_ai_reports_updated_time ON ai_reports (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_reports_uuid ON ai_reports (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS ai_tools (
        name VARCHAR(128) NOT NULL,
        kind VARCHAR(16) NOT NULL,
        source VARCHAR(16) NOT NULL,
        config JSONB,
        method VARCHAR(8) NOT NULL,
        url VARCHAR(512) NOT NULL,
        headers JSONB,
        params_schema JSONB,
        enabled BOOLEAN NOT NULL,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        status VARCHAR(10) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (name),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_ai_tools_created_id ON ai_tools (created_id);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_created_time ON ai_tools (created_time);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_deleted_id ON ai_tools (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_deleted_time ON ai_tools (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_id ON ai_tools (id);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_is_deleted ON ai_tools (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_status ON ai_tools (status);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_updated_id ON ai_tools (updated_id);
    CREATE INDEX IF NOT EXISTS ix_ai_tools_updated_time ON ai_tools (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_ai_tools_uuid ON ai_tools (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS sys_user_notification (
        id SERIAL NOT NULL,
        user_id INTEGER NOT NULL,
        title VARCHAR(128) NOT NULL,
        content TEXT,
        type VARCHAR(32) NOT NULL,
        module VARCHAR(32) NOT NULL,
        module_id INTEGER,
        is_read BOOLEAN NOT NULL,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES sys_user (id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_sys_user_notification_user_id ON sys_user_notification (user_id);
    """,
    """
    CREATE TABLE IF NOT EXISTS train_predicts (
        model_repo_id INTEGER NOT NULL,
        model_id INTEGER NOT NULL,
        framework trainframework NOT NULL,
        source_type VARCHAR(16) NOT NULL,
        source_dataset_id INTEGER,
        source_images JSONB,
        result_images JSONB,
        result_zip_path VARCHAR(512),
        hyperparams JSONB,
        status trainstatus NOT NULL,
        progress INTEGER NOT NULL,
        started_at TIMESTAMP WITHOUT TIME ZONE,
        finished_at TIMESTAMP WITHOUT TIME ZONE,
        log TEXT,
        error_log TEXT,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_train_predicts_created_id ON train_predicts (created_id);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_created_time ON train_predicts (created_time);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_deleted_id ON train_predicts (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_deleted_time ON train_predicts (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_id ON train_predicts (id);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_is_deleted ON train_predicts (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_updated_id ON train_predicts (updated_id);
    CREATE INDEX IF NOT EXISTS ix_train_predicts_updated_time ON train_predicts (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_train_predicts_uuid ON train_predicts (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS video_edge_devices (
        name VARCHAR(128) NOT NULL,
        code VARCHAR(64) NOT NULL,
        control_url VARCHAR(512),
        secret VARCHAR(128),
        capabilities JSONB,
        metrics JSONB,
        status VARCHAR(16) NOT NULL,
        last_heartbeat TIMESTAMP WITHOUT TIME ZONE,
        id SERIAL NOT NULL,
        uuid VARCHAR(64) NOT NULL,
        description TEXT,
        created_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        updated_time TIMESTAMP WITHOUT TIME ZONE NOT NULL,
        is_deleted BOOLEAN NOT NULL,
        deleted_time TIMESTAMP WITHOUT TIME ZONE,
        created_id INTEGER,
        updated_id INTEGER,
        deleted_id INTEGER,
        PRIMARY KEY (id),
        UNIQUE (code),
        FOREIGN KEY(created_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(updated_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE,
        FOREIGN KEY(deleted_id) REFERENCES sys_user (id) ON DELETE SET NULL ON UPDATE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_created_id ON video_edge_devices (created_id);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_created_time ON video_edge_devices (created_time);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_deleted_id ON video_edge_devices (deleted_id);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_deleted_time ON video_edge_devices (deleted_time);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_id ON video_edge_devices (id);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_is_deleted ON video_edge_devices (is_deleted);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_updated_id ON video_edge_devices (updated_id);
    CREATE INDEX IF NOT EXISTS ix_video_edge_devices_updated_time ON video_edge_devices (updated_time);
    CREATE UNIQUE INDEX IF NOT EXISTS ix_video_edge_devices_uuid ON video_edge_devices (uuid);
    """,
    """
    CREATE TABLE IF NOT EXISTS video_record_execution_logs (
        id SERIAL NOT NULL,
        plan_id INTEGER NOT NULL,
        camera_id INTEGER NOT NULL,
        stream_id VARCHAR(64),
        trigger_type VARCHAR(16) NOT NULL,
        start_time TIMESTAMP WITHOUT TIME ZONE,
        end_time TIMESTAMP WITHOUT TIME ZONE,
        duration INTEGER,
        status VARCHAR(16) NOT NULL,
        error_msg VARCHAR(512),
        file_count INTEGER NOT NULL,
        created_at TIMESTAMP WITHOUT TIME ZONE,
        updated_at TIMESTAMP WITHOUT TIME ZONE,
        PRIMARY KEY (id),
        FOREIGN KEY(plan_id) REFERENCES video_record_plans (id) ON DELETE CASCADE,
        FOREIGN KEY(camera_id) REFERENCES video_cameras (id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS ix_video_record_execution_logs_camera_id ON video_record_execution_logs (camera_id);
    CREATE INDEX IF NOT EXISTS ix_video_record_execution_logs_plan_id ON video_record_execution_logs (plan_id);
    """,
]

# 既有表缺失的列（幂等补列，与模型 server_default 一致：均无 server_default）
_COLUMN_DDL: list[str] = [
    "ALTER TABLE video_alarm_rules ADD COLUMN IF NOT EXISTS conditions JSONB;",
    "ALTER TABLE video_algorithm_tasks ADD COLUMN IF NOT EXISTS edge_device_id INTEGER;",
    "ALTER TABLE video_algorithm_tasks ADD COLUMN IF NOT EXISTS runtime_overrides JSONB;",
    "ALTER TABLE video_algorithm_tasks ADD COLUMN IF NOT EXISTS params_overrides JSONB;",
    "ALTER TABLE video_algorithm_tasks ADD COLUMN IF NOT EXISTS error_log TEXT;",
    "ALTER TABLE video_algorithms ADD COLUMN IF NOT EXISTS scene_type VARCHAR(64);",
    "ALTER TABLE video_algorithms ADD COLUMN IF NOT EXISTS model_file_config JSONB;",
    "ALTER TABLE video_algorithms ADD COLUMN IF NOT EXISTS runtime_config JSONB;",
    "ALTER TABLE video_algorithms ADD COLUMN IF NOT EXISTS preset_params JSONB;",
    "ALTER TABLE video_cameras ADD COLUMN IF NOT EXISTS reachable BOOLEAN;",
    "CREATE INDEX IF NOT EXISTS ix_video_algorithm_tasks_edge_device_id ON video_algorithm_tasks (edge_device_id);",
]

# video_layouts 历史漂移修复：base 迁移建表缺 ModelMixin/UserMixin 列，且多出
# created_at/updated_at（模型已不使用）。逐列补齐并回填，最后删除遗留列。
_LAYOUT_MIGRATION: list[str] = [
    # 1) 可空添加 + 回填（兼容生产已存在行）
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS uuid VARCHAR(64);",
    "UPDATE video_layouts SET uuid = md5(random()::text || clock_timestamp()::text) WHERE uuid IS NULL;",
    "ALTER TABLE video_layouts ALTER COLUMN uuid SET NOT NULL;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS status VARCHAR(10);",
    "UPDATE video_layouts SET status = '0' WHERE status IS NULL;",
    "ALTER TABLE video_layouts ALTER COLUMN status SET NOT NULL;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS created_time TIMESTAMP;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS updated_time TIMESTAMP;",
    "UPDATE video_layouts SET created_time = COALESCE(created_time, created_at, NOW()) WHERE created_time IS NULL;",
    "UPDATE video_layouts SET updated_time = COALESCE(updated_time, updated_at, created_time, NOW()) WHERE updated_time IS NULL;",
    "ALTER TABLE video_layouts ALTER COLUMN created_time SET NOT NULL;",
    "ALTER TABLE video_layouts ALTER COLUMN updated_time SET NOT NULL;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS is_deleted BOOLEAN;",
    "UPDATE video_layouts SET is_deleted = FALSE WHERE is_deleted IS NULL;",
    "ALTER TABLE video_layouts ALTER COLUMN is_deleted SET NOT NULL;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS deleted_time TIMESTAMP;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS created_id INTEGER;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS updated_id INTEGER;",
    "ALTER TABLE video_layouts ADD COLUMN IF NOT EXISTS deleted_id INTEGER;",
    # 2) 索引（与模型 index=True 对齐）
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_created_id ON video_layouts (created_id);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_created_time ON video_layouts (created_time);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_deleted_id ON video_layouts (deleted_id);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_deleted_time ON video_layouts (deleted_time);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_id ON video_layouts (id);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_is_deleted ON video_layouts (is_deleted);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_status ON video_layouts (status);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_updated_id ON video_layouts (updated_id);",
    "CREATE INDEX IF NOT EXISTS ix_video_layouts_updated_time ON video_layouts (updated_time);",
    "CREATE UNIQUE INDEX IF NOT EXISTS ix_video_layouts_uuid ON video_layouts (uuid);",
    # 3) 删除遗留列（模型已无此二列）
    "ALTER TABLE video_layouts DROP COLUMN IF EXISTS created_at;",
    "ALTER TABLE video_layouts DROP COLUMN IF EXISTS updated_at;",
]

# video_layouts 到 sys_user 的审计外键：按「约束列」探测，避免与既有约束重名/重复
_LAYOUT_FKS: list[tuple[str, tuple[str, ...]]] = [
    ("video_layouts_created_id_fkey_aistation", ("created_id",)),
    ("video_layouts_updated_id_fkey_aistation", ("updated_id",)),
    ("video_layouts_deleted_id_fkey_aistation", ("deleted_id",)),
]


def _split(statements: list[str]) -> list[str]:
    """把含多条 SQL 的块拆成单条语句（块内不含 `$$` 或字符串分号）。"""
    out: list[str] = []
    for block in statements:
        for part in block.split(";"):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _existing_fk_columns(table: str) -> set[tuple[str, ...]]:
    """返回表上现有外键的「约束列」元组集合（按列判定，规避匿名约束名差异）。"""
    insp = sa.inspect(op.get_bind())
    if not insp.has_table(table):
        return set()
    return {tuple(fk.get("constrained_columns") or ()) for fk in insp.get_foreign_keys(table)}


_ADD_COLUMN_RE = re.compile(
    r"^ALTER TABLE (\S+) ADD COLUMN IF NOT EXISTS (\w+) (.+?);?$", re.IGNORECASE
)
_SET_NOT_NULL_RE = re.compile(
    r"^ALTER TABLE (\S+) ALTER COLUMN (\w+) SET NOT NULL;?$", re.IGNORECASE
)
_DROP_COLUMN_RE = re.compile(
    r"^ALTER TABLE (\S+) DROP COLUMN IF EXISTS (\w+);?$", re.IGNORECASE
)


def _render_type(sql: str, dialect: str) -> str:
    """按方言降级 DDL 中的 PG 专属类型/函数。"""
    sql = sql.replace("JSONB", "JSON")
    sql = sql.replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")
    sql = sql.replace("NOW()", "CURRENT_TIMESTAMP")
    if dialect == "sqlite":
        sql = sql.replace("SERIAL", "INTEGER")
        sql = sql.replace(
            "md5(random()::text || clock_timestamp()::text)",
            "lower(hex(randomblob(16)))",
        )
    elif dialect == "mysql":
        sql = sql.replace(
            "md5(random()::text || clock_timestamp()::text)",
            "REPLACE(UUID(), '-', '')",
        )
    return sql


def _exec_portable(sql: str) -> None:
    """按方言执行单条 DDL：PG 原样执行，SQLite/MySQL 做语法与类型降级。"""
    stmt = sql.strip().rstrip(";")
    if not stmt:
        return
    bind = op.get_bind()
    if is_postgres(bind):
        op.execute(stmt)
        return

    dialect = dialect_name(bind)

    # SQLite/MySQL 无 ALTER COLUMN ... SET NOT NULL（列已由补列/回填保证有值）
    if _SET_NOT_NULL_RE.match(stmt):
        return

    # ADD COLUMN IF NOT EXISTS → 探测后添加
    m = _ADD_COLUMN_RE.match(stmt)
    if m:
        portable_add_column(m.group(1), m.group(2), _render_type(m.group(3), dialect))
        return

    # DROP COLUMN IF EXISTS → 探测后删除
    m = _DROP_COLUMN_RE.match(stmt)
    if m:
        insp = sa.inspect(bind)
        table, col = m.group(1), m.group(2)
        if insp.has_table(table) and col in {c["name"] for c in insp.get_columns(table)}:
            op.execute(f"ALTER TABLE {table} DROP COLUMN {col}")
        return

    op.execute(_render_type(stmt, dialect))


def _ensure_layout_foreign_keys() -> None:
    """幂等补建 video_layouts 到 sys_user 的外键（探测列）"""
    existing = _existing_fk_columns("video_layouts")
    pending = [(name, cols) for name, cols in _LAYOUT_FKS if cols not in existing]
    if not pending:
        return
    if is_sqlite(op.get_bind()):
        # SQLite 无法 ALTER ADD CONSTRAINT，走 batch 重建表
        with op.batch_alter_table("video_layouts") as batch_op:
            for name, cols in pending:
                batch_op.create_foreign_key(
                    name,
                    "sys_user",
                    list(cols),
                    ["id"],
                    ondelete="SET NULL",
                    onupdate="CASCADE",
                )
        return
    for name, cols in pending:
        op.create_foreign_key(
            name,
            "video_layouts",
            "sys_user",
            list(cols),
            ["id"],
            ondelete="SET NULL",
            onupdate="CASCADE",
        )


def upgrade() -> None:
    # 枚举类型仅 PostgreSQL 需要（SQLite/MySQL 将 ENUM 渲染为 VARCHAR/CHECK）
    if is_postgres(op.get_bind()):
        for stmt in _ENUM_DDL:
            op.execute(stmt)
    # 建表与补列合并后逐条执行（每条按方言降级）
    for stmt in _split(_TABLE_DDL + _COLUMN_DDL + _LAYOUT_MIGRATION):
        _exec_portable(stmt)
    _ensure_layout_foreign_keys()


def downgrade() -> None:
    # 逆序回滚：仅删除本迁移新增的列/表；video_layouts 遗留列不回补（数据已迁移）
    insp = sa.inspect(op.get_bind())
    if insp.has_table("video_layouts"):
        existing = {fk.get("name") for fk in insp.get_foreign_keys("video_layouts")}
        for name, _cols in reversed(_LAYOUT_FKS):
            if name in existing:
                op.drop_constraint(name, "video_layouts", type_="foreignkey")
    for idx in (
        "ix_video_layouts_uuid",
        "ix_video_layouts_updated_time",
        "ix_video_layouts_updated_id",
        "ix_video_layouts_status",
        "ix_video_layouts_is_deleted",
        "ix_video_layouts_id",
        "ix_video_layouts_deleted_time",
        "ix_video_layouts_deleted_id",
        "ix_video_layouts_created_time",
        "ix_video_layouts_created_id",
        "ix_video_algorithm_tasks_edge_device_id",
    ):
        op.execute(f"DROP INDEX IF EXISTS {idx};")
    for col in ("deleted_id", "updated_id", "created_id", "deleted_time", "is_deleted",
                "updated_time", "created_time", "status", "uuid"):
        op.execute(f"ALTER TABLE video_layouts DROP COLUMN IF EXISTS {col};")
    for col in ("preset_params", "runtime_config", "model_file_config", "scene_type"):
        op.execute(f"ALTER TABLE video_algorithms DROP COLUMN IF EXISTS {col};")
    op.execute("ALTER TABLE video_cameras DROP COLUMN IF EXISTS reachable;")
    for col in ("error_log", "params_overrides", "runtime_overrides", "edge_device_id"):
        op.execute(f"ALTER TABLE video_algorithm_tasks DROP COLUMN IF EXISTS {col};")
    op.execute("ALTER TABLE video_alarm_rules DROP COLUMN IF EXISTS conditions;")

    for table in reversed(
        [
            "video_record_execution_logs",
            "video_edge_devices",
            "train_predicts",
            "sys_user_notification",
            "ai_tools",
            "ai_reports",
            "ai_call_logs",
            "ai_messages",
            "ai_sessions",
            "ai_apps",
            "ai_prompts",
            "ai_models",
            "ai_providers",
            "annotation_record",
            "annotation_task",
            "annotation_image",
            "annotation_dataset",
        ]
    ):
        op.execute(f"DROP TABLE IF EXISTS {table};")
