"""AI 办公室：组长派活的运行状态链路。

覆盖的是"状态机"，不是模型能力：
1. 派活时组长打点 → 办公室立刻把组长标成工作中；
2. Team 事件里出现组员名字 → 该组员打点，名牌上带"组长派单"文案；
3. 结论只取组长的汇总内容。

agno Team 与 build_agent 都被替身接管，因此**不需要模型/网络**。
"""

import uuid
from types import SimpleNamespace


def _name(prefix: str = "pytest_office") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:6]}"


class _FakeEvent:
    def __init__(self, event: str, content: str = "", tool=None):
        self.event = event
        self.content = content
        self.tool = tool


class _FakeTeam:
    """替身 Team：先"派活"给第一个组员，再给汇总结论。"""

    last_members: list = []

    def __init__(self, members=None, mode=None, name=None, description=None, instructions=None, **kw):
        _FakeTeam.last_members = list(members or [])
        self.members = list(members or [])

    def arun(self, text, stream=True):
        member_name = self.members[0].name if self.members else "nobody"

        async def _gen():
            yield _FakeEvent("TeamRunStarted")
            # 组长通过工具把活派给组员：payload 里带组员名字
            yield _FakeEvent(
                "TeamToolCallStarted",
                tool={
                    "tool_name": "delegate_task_to_members",
                    "tool_args": {"tasks": [{"member_id": member_name, "description": text}]},
                },
            )
            yield _FakeEvent("TeamRunContent", content="汇总结论：")
            yield _FakeEvent("TeamRunContent", content="已完成，口径以本结论为准。")
            yield _FakeEvent("TeamRunCompleted")

        return _gen()


def _create_agent(test_client, auth_headers, name: str, role: str) -> int:
    r = test_client.post(
        "/api/v1/ai/agents/create",
        json={
            "agent_name": name,
            "agent_role": role,
            "description": f"{name} 的描述",
            "enabled": True,
            "markdown": True,
            "order": 0,
            "tool_ids": [],
            "knowledge_ids": [],
        },
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    return int(r.json()["data"]["id"])


def _delete_agents(test_client, auth_headers, ids) -> None:
    for i in ids:
        test_client.request(
            "DELETE", "/api/v1/ai/agents/delete", json=[i], headers=auth_headers
        )


def _office(test_client, auth_headers) -> dict[int, dict]:
    r = test_client.get("/api/v1/ai/agents/office", headers=auth_headers)
    assert r.status_code == 200, r.text
    return {a["id"]: a for a in r.json()["data"]}


def test_office_dispatch_marks_leader_and_delegate(monkeypatch, test_client, auth_headers):
    leader_name = _name("leader")
    member_name = _name("member")

    # build_agent 会被替换，这里只要一个带 name 的对象
    monkeypatch.setattr(
        "app.plugin.module_ai.agno_tools.agent_factory.build_agent",
        lambda **kw: SimpleNamespace(name=kw.get("name") or "member"),
    )
    monkeypatch.setattr("agno.team.Team", _FakeTeam)

    ids = [
        _create_agent(test_client, auth_headers, leader_name, "主控 · 调度"),
        _create_agent(test_client, auth_headers, member_name, "研究员"),
    ]
    try:
        r = test_client.post(
            "/api/v1/ai/agents/office/dispatch",
            json={"text": "出一份竞品周报"},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["ok"] is True, data
        assert data["leader"], "必须返回组长名"
        # 结论只取组长汇总，不拼组员原始输出
        assert "已完成" in data["content"]
        assert member_name in data["members"]

        office = _office(test_client, auth_headers)
        # 组长与组员都被点亮
        leader = next(a for a in office.values() if a["name"] == data["leader"])
        assert leader["status"] == "busy"

        member = office[ids[1]]
        assert member["status"] == "busy"
        assert "组长派单" in member["task"]
    finally:
        _delete_agents(test_client, auth_headers, ids)


def test_office_view_marks_leader_flag(monkeypatch, test_client, auth_headers):
    """角色含"主控"的智能体应被标成组长（is_leader）。"""
    leader_name = _name("leader2")
    ids = [_create_agent(test_client, auth_headers, leader_name, "主控")]
    try:
        office = _office(test_client, auth_headers)
        leaders = [a for a in office.values() if a.get("is_leader")]
        assert leaders, "至少应有一个组长"
        assert any(a["id"] == ids[0] for a in leaders)
        # 组长唯一
        assert len(leaders) == 1
    finally:
        _delete_agents(test_client, auth_headers, ids)
