"""个人空间 API 测试：文件夹 CRUD + 文件能力（跨 Task 3/4 逐步补充）。"""
import asyncio

from sqlalchemy import select

from app.core.database import async_db_session
from app.plugin.module_ai.space.model import AiSpaceFileModel


def _admin_id(test_client, auth_headers) -> int:
    r = test_client.get("/api/v1/system/user/current/info", headers=auth_headers)
    assert r.status_code == 200, r.text
    return r.json()["data"]["id"]


# ---------------------------------------------------------------- #
# 文件夹
# ---------------------------------------------------------------- #
def test_folder_crud_and_tree(test_client, auth_headers, monkeypatch):
    deleted = {}

    def _del(keys, *a, **k):
        deleted["keys"] = keys
        return len(keys)

    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_objects", _del)
    h = auth_headers
    uid = _admin_id(test_client, h)

    r = test_client.post("/api/v1/ai/space/folders/create", json={"name": "资料"}, headers=h)
    assert r.status_code == 200, r.text
    fid = r.json()["data"]["id"]
    r2 = test_client.post(
        "/api/v1/ai/space/folders/create", json={"name": "子目录", "parent_id": fid}, headers=h
    )
    assert r2.status_code == 200

    # 级联：文件夹内先放一个文件（直接走 DB 插入，S3 不落盘）
    async def _seed():
        async with async_db_session.begin() as db:
            f = AiSpaceFileModel(
                uuid="u1", folder_id=fid, user_id=uid, name="a.txt", ext="txt",
                file_type="txt", mime_type="text/plain", size=1,
                object_key="ai-space/1/x/u1.txt", source="upload",
            )
            db.add(f)

    asyncio.run(_seed())

    tree = test_client.get("/api/v1/ai/space/folders/tree", headers=h).json()["data"]
    assert any(n["id"] == fid and n["children"] for n in tree)

    upd = test_client.put(
        f"/api/v1/ai/space/folders/update/{fid}", json={"name": "资料2"}, headers=h
    )
    assert upd.json()["data"]["name"] == "资料2"

    dele = test_client.request(
        "DELETE", "/api/v1/ai/space/folders/delete", json=fid, headers=h
    )
    assert dele.status_code == 200
    assert deleted["keys"] == ["ai-space/1/x/u1.txt"]  # 级联删除 S3 对象

    tree2 = test_client.get("/api/v1/ai/space/folders/tree", headers=h).json()["data"]
    assert all(n["id"] != fid for n in tree2)

    # 该文件应已软删
    async def _check():
        async with async_db_session() as db:
            rows = (
                await db.execute(
                    select(AiSpaceFileModel).where(
                        AiSpaceFileModel.user_id == uid, AiSpaceFileModel.is_deleted.is_(False)
                    )
                )
            ).scalars().all()
            return len(rows)

    assert asyncio.run(_check()) == 0


def test_folder_parent_must_belong_to_user(test_client, auth_headers):
    h = auth_headers
    r = test_client.post(
        "/api/v1/ai/space/folders/create", json={"name": "x", "parent_id": 999999}, headers=h
    )
    assert r.status_code == 400
