"""阶段 3b：MCP 服务器外部 OAuth 绑定列 / schema 测试。"""


def test_mcp_model_instantiate(test_client):
    from app.plugin.module_ai.mcp.model import AiMcpServerModel

    s = AiMcpServerModel(name="svc", transport="streamable-http", oauth_ext_service_id=3)
    assert s.oauth_ext_service_id == 3


def test_mcp_create_schema_accepts_binding(test_client):
    from app.plugin.module_ai.mcp.schema import McpCreateSchema, McpUpdateSchema

    c = McpCreateSchema(name="x", oauth_ext_service_id=5)
    assert c.oauth_ext_service_id == 5
    u = McpUpdateSchema(oauth_ext_service_id=7)
    assert u.oauth_ext_service_id == 7
