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
    last_used_at TIMESTAMP
)
"""


async def ensure_asset_embed_schema(engine) -> None:
    """建资产嵌入令牌表（幂等，失败仅告警）。"""
    from sqlalchemy import text

    from app.core.logger import log

    try:
        async with engine.begin() as conn:
            await conn.execute(text(CREATE_ASSET_TOKENS_DDL))
    except Exception as e:  # noqa: BLE001
        log.warning(f"asset_embed schema: 建 ai_asset_access_tokens 失败: {e}")
