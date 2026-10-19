"""个人空间 API 测试：文件夹 CRUD + 文件能力（跨 Task 3/4 逐步补充）。"""
import asyncio

import pytest
from sqlalchemy import delete, select

from app.core.database import async_db_session
from app.plugin.module_ai.space.model import AiSpaceFileModel, AiSpaceFolderModel


@pytest.fixture(autouse=True)
def _clean_space():
    """用例间清理个人空间表（物理删除），保证断言不受前序用例污染。"""

    async def _clean():
        async with async_db_session.begin() as db:
            await db.execute(delete(AiSpaceFileModel))
            await db.execute(delete(AiSpaceFolderModel))

    asyncio.run(_clean())
    yield


def _admin_id(test_client, auth_headers) -> int:
    """管理员用户 ID：直接查库（不依赖 current/info——其菜单输出会被菜单类测试构造的脏行影响）。"""
    from sqlalchemy import select

    from app.api.v1.module_system.user.model import UserModel
    from app.core.database import async_db_session

    async def _run():
        async with async_db_session() as db:
            u = await db.scalar(select(UserModel).where(UserModel.username == "admin"))
            assert u is not None, "admin 用户不存在（种子数据未初始化）"
            return u.id

    return asyncio.run(_run())


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


# ---------------------------------------------------------------- #
# 文件
# ---------------------------------------------------------------- #
class _FakeBody:
    """s3 get_object 返回体：支持 read(n) 分块。"""

    def __init__(self, data: bytes):
        self._d = data
        self._pos = 0

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = len(self._d)
        chunk = self._d[self._pos:self._pos + n]
        self._pos += len(chunk)
        return chunk


def _mock_s3(monkeypatch, content: bytes = b"hello"):
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_objects", lambda *a, **k: 0)

    def _get(key, **k):
        return {"Body": _FakeBody(content), "ContentLength": len(content), "ContentType": "text/plain"}

    monkeypatch.setattr("app.utils.s3_client.s3_client.get_object", _get)


def _upload(test_client, h, name="a.txt", content=b"hello", **kw):
    return test_client.post(
        "/api/v1/ai/space/files/upload",
        files={"file": (name, content, "text/plain")},
        data=kw,
        headers=h,
    )


def test_file_upload_list_download_preview(test_client, auth_headers, monkeypatch):
    _mock_s3(monkeypatch)
    h = auth_headers
    r = _upload(test_client, h)
    assert r.status_code == 200 and r.json()["data"]["source"] == "upload"
    fid = r.json()["data"]["id"]
    lst = test_client.get("/api/v1/ai/space/files/list", headers=h).json()["data"]
    assert lst["total"] == 1 and lst["items"][0]["name"] == "a.txt"
    pv = test_client.get(f"/api/v1/ai/space/files/{fid}/preview", headers=h).json()["data"]
    assert pv["content"] == "hello"
    dl = test_client.get(f"/api/v1/ai/space/files/{fid}/download", headers=h)
    assert dl.status_code == 200 and b"hello" in dl.content
    q = test_client.get("/api/v1/ai/space/quota", headers=h).json()["data"]
    assert q["used_bytes"] == 5 and q["max_file_bytes"] == 200 * 1024 * 1024


def test_upload_rejects_unknown_ext_and_empty(test_client, auth_headers, monkeypatch):
    _mock_s3(monkeypatch)
    assert _upload(test_client, auth_headers, name="x.xyz", content=b"abc").status_code == 400
    assert _upload(test_client, auth_headers, name="empty.txt", content=b"").status_code == 400


def test_upload_quota_limit(test_client, auth_headers, monkeypatch):
    _mock_s3(monkeypatch)
    from app.config.setting import settings

    monkeypatch.setattr(settings, "AI_SPACE_MAX_FILE_MB", 1)  # 临时降限避免构造 200MB
    big = b"x" * (1024 * 1024 + 1)
    assert _upload(test_client, auth_headers, name="big.txt", content=big).status_code == 400


def test_rename_move_delete_flow(test_client, auth_headers, monkeypatch):
    _mock_s3(monkeypatch)
    h = auth_headers
    fid = _upload(test_client, h).json()["data"]["id"]
    folder = test_client.post(
        "/api/v1/ai/space/folders/create", json={"name": "f"}, headers=h
    ).json()["data"]["id"]
    mv = test_client.post(
        "/api/v1/ai/space/files/move", json={"file_id": fid, "folder_id": folder}, headers=h
    )
    assert mv.status_code == 200 and mv.json()["data"]["folder_id"] == folder
    # 移动到自身目录 → 400
    self_mv = test_client.post(
        "/api/v1/ai/space/files/move", json={"file_id": fid, "folder_id": folder}, headers=h
    )
    assert self_mv.status_code == 400
    rn = test_client.put(
        "/api/v1/ai/space/files/rename", json={"file_id": fid, "name": "b.txt"}, headers=h
    )
    assert rn.status_code == 200
    dele = test_client.request("DELETE", "/api/v1/ai/space/files/delete", json=[fid], headers=h)
    assert dele.status_code == 200 and dele.json()["data"]["deleted"] == 1


def test_duplicate_name_allowed(test_client, auth_headers, monkeypatch):
    """同目录重名上传：允许（uuid 对象 key），不覆盖。"""
    _mock_s3(monkeypatch)
    h = auth_headers
    _upload(test_client, h, name="dup.txt")
    _upload(test_client, h, name="dup.txt")
    lst = test_client.get("/api/v1/ai/space/files/list", headers=h).json()["data"]
    assert lst["total"] == 2


def test_preview_truncates_large_text(test_client, auth_headers, monkeypatch):
    """预览 600KB 文本 → 截断标记。"""
    _mock_s3(monkeypatch, content=b"x" * (600 * 1024))
    fid = _upload(test_client, auth_headers, name="big.txt", content=b"x" * (600 * 1024)).json()["data"]["id"]
    pv = test_client.get(f"/api/v1/ai/space/files/{fid}/preview", headers=auth_headers).json()["data"]
    assert pv["truncated"] is True


def test_preview_md_and_json_content(test_client, auth_headers, monkeypatch):
    """md/csv/json 属文本类：预览应返回真实内容（_extract_doc_text 需支持）。"""
    _mock_s3(monkeypatch, content="# 标题\n正文".encode())
    fid = _upload(test_client, auth_headers, name="note.md", content="# 标题\n正文".encode()).json()["data"]["id"]
    pv = test_client.get(f"/api/v1/ai/space/files/{fid}/preview", headers=auth_headers).json()["data"]
    assert pv["kind"] == "text" and "正文" in pv["content"]


def test_get_file_rejects_other_user(test_client, auth_headers, monkeypatch):
    """用户隔离：以其他 user_id 直接调服务读取 → 抛 ValueError（不影响他人记录）。"""
    _mock_s3(monkeypatch)
    fid = _upload(test_client, auth_headers).json()["data"]["id"]
    import asyncio

    import pytest

    from app.plugin.module_ai.space.service import SpaceService

    with pytest.raises(ValueError):
        asyncio.run(SpaceService.get_file(fid, user_id=999999))


def test_no_auth_rejected(test_client):
    r = test_client.get("/api/v1/ai/space/files/list")
    assert r.status_code in (401, 403)
