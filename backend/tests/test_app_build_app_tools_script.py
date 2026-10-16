"""``_build_app_tools`` 对 script 源工具产出 schema（DB 集成，test_client 起临时库）。"""
import asyncio

from app.core.database import async_db_session
from app.plugin.module_ai.apps.service import _build_app_tools
from app.plugin.module_ai.tools_catalog.model import AiToolModel


async def _insert_script_tool(name: str) -> None:
    async with async_db_session.begin() as db:
        row = AiToolModel(
            name=name,
            kind="script",
            source="script",
            enabled=True,
            params_schema={
                "type": "object",
                "properties": {"q": {"type": "string"}},
                "required": ["q"],
            },
            code="def run(q):\n    return q",
            description=f"脚本工具：{name}",
            created_id=1,
            updated_id=1,
        )
        db.add(row)
        await db.flush()


def test_build_app_tools_script_source():
    """script 源工具应被解析为可下发的 schema。"""
    asyncio.run(_insert_script_tool("s_weather"))
    schemas, http_tools = asyncio.run(_build_app_tools(["s_weather"]))
    assert schemas, "script 工具应产出 schema"
    names = {s.get("function", {}).get("name") for s in schemas}
    assert "s_weather" in names
