"""工作流「工作台分类」字段（category_id）。

背景：`AiWorkflowModel.category_id` 列一直存在，但 Create/Update schema 未暴露 →
工作流永远挂不上分类（工作台分类树对工作流这一半空转）。本文件锁住：

1. 创建时可带 `category_id` 并原样回读；
2. 更新时 `category_id` 支持**显式清空**（传 null → None），与其它字段「None=不修改」语义区分；
3. 更新不传 `category_id` 时保持原值。

需要应用（`test_client`）的用例在 ``PYTEST_NO_APP=1`` 快速模式下自动 skip。
"""

import uuid


def _name() -> str:
    return f"pytest-wf-cat-{uuid.uuid4().hex[:6]}"


def _create_workflow(test_client, auth_headers, category_id=None) -> dict:
    payload = {
        "name": _name(),
        "description": "分类字段用例",
        "graph": {
            "nodes": [
                {"id": "start", "type": "start", "data": {"variables": []}},
                {"id": "end", "type": "end", "data": {"output_template": "ok"}},
            ],
            "edges": [{"id": "e1", "source": "start", "target": "end"}],
        },
        "enabled": True,
    }
    if category_id is not None:
        payload["category_id"] = category_id
    r = test_client.post("/api/v1/ai/workflows/create", json=payload, headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]


def test_workflow_create_with_category(test_client, auth_headers):
    """创建时带 category_id → 详情原样回读。"""
    data = _create_workflow(test_client, auth_headers, category_id=3)
    try:
        assert data["category_id"] == 3
        detail = test_client.get(
            f"/api/v1/ai/workflows/detail/{data['id']}", headers=auth_headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["data"]["category_id"] == 3
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=[data["id"]], headers=auth_headers
        )


def test_workflow_update_can_clear_category(test_client, auth_headers):
    """更新传 null → 清空分类（显式清空语义）；不传 → 保持原值。"""
    data = _create_workflow(test_client, auth_headers, category_id=5)
    wid = data["id"]
    try:
        # 不传 category_id：保持 5
        r = test_client.put(
            f"/api/v1/ai/workflows/update/{wid}",
            json={"name": data["name"]},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["category_id"] == 5

        # 显式传 null：清空
        r = test_client.put(
            f"/api/v1/ai/workflows/update/{wid}",
            json={"category_id": None},
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["data"]["category_id"] is None
    finally:
        test_client.request(
            "DELETE", "/api/v1/ai/workflows/delete", json=[wid], headers=auth_headers
        )
