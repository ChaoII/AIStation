"""资产嵌入模块缺失表的启动幂等建表。

与 `module_ai.knowledge.schema_check` 同模式：插件表自建，**不走 alembic autogenerate**
（dev 库有大量历史影子表，autogenerate 会把它们判成待 DROP）。
"""
from __future__ import annotations

#: 资产嵌入令牌表（DDL 与 `asset_embed.model.AiAssetAccessTokenModel` 对齐）
CREATE_ASSET_TOKENS_DDL = """
CREATE TABLE IF NOT EXISTS ai_asset_access_tokens (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    status VARCHAR(1) DEFAULT '0',
    created_time TIMESTAMP DEFAULT NOW(),
    updated_time TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_time TIMESTAMP,
    kind VARCHAR(16) NOT NULL,
    target_id INTEGER NOT NULL,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    issued_by VARCHAR(16) DEFAULT 'admin',
    expires_at TIMESTAMP NOT NULL,
    revoked BOOLEAN DEFAULT FALSE,
    use_count INTEGER DEFAULT 0,
    last_used_at TIMESTAMP,
    allow_domains VARCHAR(1024),
    allow_ips VARCHAR(1024)
)
"""


#: 资产嵌入会话映射表（DDL 与 `asset_embed.model.AiAssetEmbedSessionModel` 对齐）
CREATE_ASSET_SESSIONS_DDL = """
CREATE TABLE IF NOT EXISTS ai_asset_embed_sessions (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    status VARCHAR(1) DEFAULT '0',
    created_time TIMESTAMP DEFAULT NOW(),
    updated_time TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_time TIMESTAMP,
    kind VARCHAR(16) NOT NULL,
    target_id INTEGER NOT NULL,
    sid VARCHAR(64) NOT NULL,
    session_id INTEGER NOT NULL,
    expires_at TIMESTAMP NOT NULL,
    last_active_at TIMESTAMP NOT NULL,
    CONSTRAINT uq_ai_asset_embed_sessions_asset_sid UNIQUE (kind, target_id, sid)
)
"""

#: 资产嵌入调用审计表（DDL 与 `asset_embed.model.AiAssetEmbedLogModel` 对齐）
CREATE_ASSET_LOGS_DDL = """
CREATE TABLE IF NOT EXISTS ai_asset_embed_logs (
    id SERIAL PRIMARY KEY,
    uuid VARCHAR(36) NOT NULL UNIQUE,
    status VARCHAR(1) DEFAULT '0',
    created_time TIMESTAMP DEFAULT NOW(),
    updated_time TIMESTAMP DEFAULT NOW(),
    is_deleted BOOLEAN DEFAULT FALSE,
    deleted_time TIMESTAMP,
    kind VARCHAR(16) NOT NULL,
    target_id INTEGER NOT NULL,
    session_id VARCHAR(64) DEFAULT '',
    sid VARCHAR(64) DEFAULT '',
    message VARCHAR(120) DEFAULT '',
    result_status VARCHAR(16) DEFAULT 'success',
    error VARCHAR(250),
    latency_ms INTEGER DEFAULT 0,
    token_hash12 VARCHAR(12) DEFAULT '',
    token_id INTEGER,
    client_ip VARCHAR(64) DEFAULT ''
)
"""


async def ensure_asset_embed_schema(engine) -> None:
    """建资产嵌入令牌/会话/审计表（幂等，失败仅告警）。"""
    from sqlalchemy import text

    from app.core.logger import log

    ddl_statements = [
        CREATE_ASSET_TOKENS_DDL,
        CREATE_ASSET_SESSIONS_DDL,
        CREATE_ASSET_LOGS_DDL,
        "ALTER TABLE ai_asset_access_tokens ADD COLUMN IF NOT EXISTS allow_domains VARCHAR(1024)",
        "ALTER TABLE ai_asset_access_tokens ADD COLUMN IF NOT EXISTS allow_ips VARCHAR(1024)",
        "ALTER TABLE ai_asset_embed_logs ADD COLUMN IF NOT EXISTS token_id INTEGER",
        "ALTER TABLE ai_asset_embed_logs ADD COLUMN IF NOT EXISTS client_ip VARCHAR(64) DEFAULT ''",
    ]
    for ddl in ddl_statements:
        try:
            async with engine.begin() as conn:
                await conn.execute(text(ddl))
        except Exception as e:  # noqa: BLE001
            log.warning(f"asset_embed schema: 建表失败: {e}")
