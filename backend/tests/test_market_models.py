"""市场/MCP/插件数据模型：表与列定义校验（纯逻辑，PYTEST_NO_APP=1 可跑）。"""
import pytest

from app.core.base_model import MappedBase, ModelMixin, UserMixin
from app.plugin.module_ai.market.model import (
    AiMarketItemModel,
    AiMarketRelationModel,
    AiMarketShareModel,
)
from app.plugin.module_ai.mcp.model import AiMcpServerModel
from app.plugin.module_ai.plugins.model import AiPluginModel
from app.plugin.module_ai.tools_catalog.model import AiToolModel
from app.plugin.module_ai.agent.model import AiAgentModel


def _cols(model):
    return set(MappedBase.metadata.tables[model.__tablename__].columns.keys())


def test_market_item_table_and_columns():
    """市场商品表含关键业务列与 ModelMixin 公共列。"""
    cols = _cols(AiMarketItemModel)
    for c in (
        "asset_type",
        "name",
        "description",
        "icon",
        "category",
        "tags",
        "version",
        "owner_id",
        "is_official",
        "featured",
        "status",
        "payload",
        "source_id",
        "install_count",
        "favorite_count",
        "audit_remark",
        "audit_user",
        "audit_time",
        "id",
        "uuid",
        "created_time",
        "updated_time",
        "is_deleted",
        "deleted_time",
    ):
        assert c in cols, f"ai_market_items 缺少列 {c}"


def test_market_relation_and_share_tables():
    """关系表/分享表含外键列与状态列。"""
    rel_cols = _cols(AiMarketRelationModel)
    assert {"user_id", "item_id", "kind"} <= rel_cols
    share_cols = _cols(AiMarketShareModel)
    assert {"item_id", "from_user_id", "to_user_id", "status", "message"} <= share_cols


def test_mcp_server_table():
    """MCP 服务器表含传输/鉴权配置列，且带用户审计字段。"""
    cols = _cols(AiMcpServerModel)
    for c in (
        "name",
        "transport",
        "command",
        "args",
        "env",
        "url",
        "headers",
        "auth_type",
        "enabled",
        "description",
        "created_id",
        "updated_id",
        "deleted_id",
    ):
        assert c in cols, f"ai_mcp_servers 缺少列 {c}"


def test_plugin_table():
    """插件表含 key/label/kind/config/config_schema/executor_ready/enabled。"""
    cols = _cols(AiPluginModel)
    for c in ("key", "label", "kind", "config", "config_schema", "executor_ready", "enabled"):
        assert c in cols, f"ai_plugins 缺少列 {c}"


def test_tool_model_script_fields():
    """ai_tools 增加 code/timeout 列，kind 注释支持 script。"""
    cols = _cols(AiToolModel)
    assert "code" in cols and "timeout" in cols
    # kind 默认仍为 builtin
    assert AiToolModel.__table__.c.kind.default.arg == "builtin"


def test_agent_model_mcp_ids():
    """ai_agents 增加 mcp_ids JSONB 列。"""
    cols = _cols(AiAgentModel)
    assert "mcp_ids" in cols


def test_mixins_used():
    """市场/关系/分享继承 ModelMixin；MCP/插件继承 ModelMixin+UserMixin。"""
    assert issubclass(AiMarketItemModel, ModelMixin)
    assert issubclass(AiMarketRelationModel, ModelMixin)
    assert issubclass(AiMarketShareModel, ModelMixin)
    assert issubclass(AiMcpServerModel, UserMixin)
    assert issubclass(AiPluginModel, UserMixin)
