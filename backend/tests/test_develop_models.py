# tests/test_develop_models.py （PYTEST_NO_APP=1）
from app.plugin.module_ai.develop.model import (
    AiIntegrationAppModel, AiIntegrationCallLogModel, AiIntegrationMcpSessionModel,
)


def test_app_model_columns():
    cols = set(AiIntegrationAppModel.__table__.columns.keys())
    assert {"id", "uuid", "appid", "appkey_hash", "name", "enabled", "expire_at",
            "capabilities", "quota", "requires_approval", "source_type",
            "last_call_at", "call_count", "created_id", "updated_id"}.issubset(cols)


def test_call_log_model_has_no_soft_delete():
    cols = set(AiIntegrationCallLogModel.__table__.columns.keys())
    assert "is_deleted" not in cols and "deleted_time" not in cols
    assert {"id", "created_time", "app_id", "log_type", "method", "status"}.issubset(cols)


def test_mcp_session_model_columns():
    cols = set(AiIntegrationMcpSessionModel.__table__.columns.keys())
    assert {"session_id", "transport", "started_at", "tool_calls"}.issubset(cols)
