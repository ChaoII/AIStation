# 个人工作空间（Personal Workspace）实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 AI 管理下新增「个人工作空间」：按用户隔离的多级文件夹文件空间（上传/下载/预览/配额），智能体可保存/列出/读取空间文件，对话可选空间文件作为输入。

**Architecture:** 独立新插件模块 `backend/app/plugin/module_ai/space/`（路由 `/ai/space`），元信息存 `ai_space_files`/`ai_space_folders` 两张新表，二进制存 RustFS/S3（复用 `app/utils/s3_client.py`）；智能体工具注册进 `assistant/tools.py::TOOL_REGISTRY`（agno 自动包装，user_id 走 ContextVar）。

**Tech Stack:** FastAPI + SQLAlchemy 2.0 + Pydantic v2 + Alembic；agno；Vue 3 + Element Plus + TypeScript；boto3/RustFS。

**Spec:** `docs/superpowers/specs/2026-10-19-personal-workspace-design.md`（本计划依据该设计，执行者须同读）。

## Global Constraints

- 所有用户可见回复/文档/代码注释用中文；提交信息 `类型(模块): 中文描述`。
- 权限码 `module_ai:space:{query,upload,download,delete,manage}`；每个接口 `Depends(AuthPermission([...]))`。
- 查询强制 `user_id == 当前用户`；越权一律返回「文件不存在」（404 语义，不暴露存在性）。
- 配额默认：单文件 `AI_SPACE_MAX_FILE_MB=200`，单用户总量 `AI_SPACE_QUOTA_MB=10240`（`config/setting.py` 新增，环境可覆盖）。
- 删除类前端一律 `ElMessageBox.confirm`（写数量与不可逆）；按钮 `v-hasPerm`；后端/前端权限都不省。
- 迁移手写（禁 autogenerate），`has_table()` 守卫；插件表由 `create_all` 兜底（绿库）。
- 测试基建：`backend/tests/conftest.py` 提供 `test_client`（FastAPI TestClient + SQLite 真库 + lifespan 建表种子）与 `auth_headers`（admin Bearer；请求需带 `X-Forwarded-For: 127.0.0.1`）。S3 一律 `monkeypatch.setattr("app.utils.s3_client.s3_client.<method>", ...)`。
- 快速模式：纯逻辑测试用 `PYTEST_NO_APP=1 uv run pytest tests/test_xxx.py -k ... -q`；需要应用的用例会自动 skip。
- 前端严禁自定义字体/主题色；用 `--el-*` 变量；参照 `module_ai/knowledge/index.vue` 与 `module_system/param`。
- 上传/预览/下载与知识库一致：PDF 前端 `vue-pdf-embed`（blob → objectURL），docx 前端 `mammoth.convertToHtml`，文本类后端返回 content。

## Review Focus

以下输入/失败模式是 spec 未逐项约束但最可能咬人的点，每条已钉入所属任务的测试：

1. 空文件、无扩展名、未知扩展名上传 → 返回 400 明确中文错误（Task 4）。
2. 同目录重名上传 → 允许（对象 key 用 uuid，不覆盖、不报错）（Task 4）。
3. 删除文件夹的级联删除必须同时清 S3 对象；S3 删除失败仅记日志不阻塞 DB 删除（Task 3/4）。
4. 智能体保存文件名含路径分隔符/`..` → 清洗为纯文件名（Task 6）。
5. 预览/读取超大文本 → 截断（read 100KB / preview 500KB 上限）并返回截断标记（Task 4/6）。
6. 移动文件到自身目录或跨用户目录 → 拒绝（Task 4）。
7. 对话 files 引用 workspace 文件超拉取上限（20MB）或不属于当前用户 → 跳过该文件不阻断对话（Task 7）。
8. 未带 `module_ai:space:*` 权限的请求 → 401/403（Task 2 起所有接口测试带 auth_headers 已覆盖；不另立测试）。

---

### Task 1: 配置文件与文件类型工具

**Files:**
- Modify: `backend/app/config/setting.py`（新增 `AI_SPACE_MAX_FILE_MB`、`AI_SPACE_QUOTA_MB`）
- Create: `backend/app/plugin/module_ai/space/__init__.py`（空文件）
- Create: `backend/app/plugin/module_ai/space/filetype.py`
- Test: `backend/tests/test_ai_space_filetype.py`

**Interfaces:**
- Produces:
  - `settings.AI_SPACE_MAX_FILE_MB: int`（默认 200）
  - `settings.AI_SPACE_QUOTA_MB: int`（默认 10240）
  - `classify_file(name: str, mime: str) -> str`：返回 `image/pdf/txt/md/csv/json/docx/video/audio/other`（按扩展名优先、mime 兜底）
  - `sanitize_filename(name: str) -> str`：去路径分隔符/`..`，空则 `"unnamed"`，保留原始扩展名
  - `guess_mime(ext: str) -> str`：扩展名 → mime（参照 knowledge/controller.py 的 media 映射，补全常用）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_space_filetype.py
def test_classify_by_ext_and_mime():
    assert classify_file("a.png", "application/octet-stream") == "image"
    assert classify_file("a.pdf", "") == "pdf"
    assert classify_file("报告.docx", "") == "docx"
    assert classify_file("noext", "text/plain") in ("txt", "other")  # mime 兜底
def test_sanitize_filename_strips_path():
    assert "/" not in sanitize_filename("../../etc/passwd.txt")
    assert sanitize_filename("../x.txt") == "x.txt"
    assert sanitize_filename("") == "unnamed"
def test_settings_have_quota_defaults():
    from app.config.setting import settings
    assert settings.AI_SPACE_MAX_FILE_MB == 200
    assert settings.AI_SPACE_QUOTA_MB == 10240
```

- [ ] **Step 2: 运行验证失败**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_ai_space_filetype.py -q`
Expected: FAIL（ImportError：模块不存在）

- [ ] **Step 3: 实现 `filetype.py` 与 `setting.py`**

`filetype.py` 三个纯函数（无 IO）；`setting.py` 仿照 `UPLOAD_FILE_MAX_MB` 类字段加两个整型配置。

- [ ] **Step 4: 运行验证通过**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_ai_space_filetype.py -q`
Expected: PASS（4 passed）

- [ ] **Step 5: 提交**

```bash
git add backend/app/config/setting.py backend/app/plugin/module_ai/space/__init__.py backend/app/plugin/module_ai/space/filetype.py backend/tests/test_ai_space_filetype.py
git commit -m "feat(ai-space): 新增个人空间配置文件与文件类型工具"
```

---

### Task 2: 数据模型与迁移

**Files:**
- Create: `backend/app/plugin/module_ai/space/model.py`
- Create: `backend/app/alembic/versions/2026_10_19_ai_space_tables.py`
- Test: `backend/tests/test_ai_space_models.py`

**Interfaces:**
- Produces:
  - `AiSpaceFolderModel`（表 `ai_space_folders`，`ModelMixin` + `UserMixin` 风格手工列，见下）
  - `AiSpaceFileModel`（表 `ai_space_files`，同）
  - 列（以 spec 4.2 为准）：folders=`id/name/user_id/parent_id/status/created_time/updated_time/is_deleted/deleted_time`；files=`id/uuid/folder_id/user_id/name/ext/file_type/mime_type/size/object_key/source/status/created_time/updated_time/is_deleted/deleted_time`。

- [ ] **Step 1: 写失败测试（真库事务）**

```python
# backend/tests/test_ai_space_models.py
import asyncio
from sqlalchemy import select
from app.core.database import async_db_session
from app.plugin.module_ai.space.model import AiSpaceFolderModel, AiSpaceFileModel

def test_folders_and_files_persist(test_client):
    async def _run():
        async with async_db_session.begin() as db:
            f = AiSpaceFolderModel(name="报告", user_id=1)
            db.add(f); await db.flush()
            fl = AiSpaceFileModel(uuid="u1", folder_id=f.id, user_id=1, name="a.txt",
                                  ext="txt", file_type="txt", mime_type="text/plain",
                                  size=10, object_key="ai-space/1/20261019/u1.txt", source="upload")
            db.add(fl); await db.flush()
            fid, fdid = f.id, fl.id
        async with async_db_session() as db:
            row = await db.get(AiSpaceFileModel, fdid)
            return row.name, row.folder_id, fid
    name, fid2, fid1 = asyncio.run(_run())
    assert name == "a.txt" and fid2 == fid1
```

- [ ] **Step 2: 运行验证失败**

Run: `uv run pytest tests/test_ai_space_models.py -q`
Expected: FAIL（ImportError：`space.model` 不存在）

- [ ] **Step 3: 实现 `space/model.py`**

仿 `module_ai/workspace/model.py` 风格：`ModelMixin` + 显式 `user_id`（`BigInteger` + `index=True`，不建 FK 到 sys_user，保持隔离查询简单）；`parent_id`/`folder_id` 用 `ForeignKey(..., ondelete="SET NULL")`；`__table_args__ = ({"comment": ...},)`。

- [ ] **Step 4: 实现迁移 `2026_10_19_ai_space_tables.py`**

手写 `upgrade()`：`insp = sa.inspect(bind)`；若 `"ai_space_folders" not in insp.get_table_names()` 才 `op.create_table(...)`（files 同理，注意 folders 先建）；`downgrade()` 对称删除。revision 自定（如 `a1b2c3d4e5f6`），`down_revision` 用当前 head（实现时 `uv run main.py revision --env=dev` 看 head 再手写，或用 `alembic heads`）。

- [ ] **Step 5: 运行验证通过**

Run: `uv run pytest tests/test_ai_space_models.py -q`
Expected: PASS（SQLite 建表经 `create_all`，模型可读写）

- [ ] **Step 6: 提交**

```bash
git add backend/app/plugin/module_ai/space/model.py backend/app/alembic/versions/2026_10_19_ai_space_tables.py backend/tests/test_ai_space_models.py
git commit -m "feat(ai-space): 新增个人空间数据模型与迁移"
```

---

### Task 3: 文件夹 CRUD（服务 + API）

**Files:**
- Create: `backend/app/plugin/module_ai/space/schema.py`
- Create: `backend/app/plugin/module_ai/space/service.py`（本任务只实现文件夹方法）
- Create: `backend/app/plugin/module_ai/space/controller.py`（本任务只挂文件夹路由）
- Test: `backend/tests/test_ai_space.py`（本任务含文件夹用例）

**Interfaces:**
- Consumes: Task 1 `filetype.py`、Task 2 模型。
- Produces:
  - `SpaceFolderCreateSchema(name: str, parent_id: int | None = None)`
  - `SpaceFolderUpdateSchema(name: str)`
  - `SpaceService.create_folder(name, parent_id, user_id) -> dict`（parent 必须属于该用户，否则 ValueError）
  - `SpaceService.folder_tree(user_id) -> list[dict]`（嵌套 children；只含未删）
  - `SpaceService.rename_folder(folder_id, name, user_id) -> bool`
  - `SpaceService.delete_folder(folder_id, user_id) -> dict`（`{"deleted_files": n}`；级联：统计文件夹内全部文件（递归子文件夹）→ DB 软删 folders+files → `s3_client.delete_objects` 清对象；S3 失败仅 log）
  - `GET /ai/space/folders/tree`、`POST /ai/space/folders/create`、`PUT /ai/space/folders/update/{id}`、`DELETE /ai/space/folders/delete`（body `folder_id`）——权限 `module_ai:space:query`/`manage`/`manage`/`manage`。

- [ ] **Step 1: 写失败测试（HTTP）**

```python
# backend/tests/test_ai_space.py（本任务部分）
def test_folder_crud_and_tree(test_client, auth_headers, monkeypatch):
    deleted = {}
    def _del(keys, *a, **k):
        deleted["keys"] = keys
        return len(keys)
    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_objects", _del)
    h = auth_headers
    r = test_client.post("/api/v1/ai/space/folders/create", json={"name": "资料"}, headers=h)
    assert r.status_code == 200, r.text
    fid = r.json()["data"]["id"]
    r2 = test_client.post(f"/api/v1/ai/space/folders/create", json={"name": "子目录", "parent_id": fid}, headers=h)
    assert r2.status_code == 200
    # 级联：文件夹内先放一个文件（直接走 DB 插入，S3 不落盘）
    import asyncio
    from app.core.database import async_db_session
    from app.plugin.module_ai.space.model import AiSpaceFileModel
    async def _seed():
        async with async_db_session.begin() as db:
            f = AiSpaceFileModel(uuid="u1", folder_id=fid, user_id=1, name="a.txt", ext="txt",
                                 file_type="txt", mime_type="text/plain", size=1,
                                 object_key="ai-space/1/x/u1.txt", source="upload")
            db.add(f)
    asyncio.run(_seed())
    tree = test_client.get("/api/v1/ai/space/folders/tree", headers=h).json()["data"]
    assert any(n["id"] == fid and n["children"] for n in tree)
    upd = test_client.put(f"/api/v1/ai/space/folders/update/{fid}", json={"name": "资料2"}, headers=h)
    assert upd.json()["data"]["name"] == "资料2"
    dele = test_client.request("DELETE", "/api/v1/ai/space/folders/delete", json={"folder_id": fid}, headers=h)
    assert dele.status_code == 200
    assert deleted["keys"] == ["ai-space/1/x/u1.txt"]  # 级联删除 S3 对象
    tree2 = test_client.get("/api/v1/ai/space/folders/tree", headers=h).json()["data"]
    assert all(n["id"] != fid for n in tree2)
def test_folder_parent_must_belong_to_user(test_client, auth_headers):
    # 用不存在/他人 parent 创建 → 400
    r = test_client.post("/api/v1/ai/space/folders/create", json={"name": "x", "parent_id": 999999}, headers=auth_headers)
    assert r.status_code == 400
```

- [ ] **Step 2: 运行验证失败**

Run: `uv run pytest tests/test_ai_space.py -q`
Expected: FAIL（404 路由不存在）

- [ ] **Step 3: 实现 `schema.py` + `service.py`（文件夹部分）+ `controller.py`**

`controller.py` 仿 `module_ai/workspace/controller.py`（`OperationLogRoute`、`SuccessResponse/ErrorResponse`、`AuthPermission`）。service 内事务用 `async_db_session.begin()`；树构建用 `traversal_to_tree`（`app/utils/common_util.py`，参考 workspace service 用法）。

- [ ] **Step 4: 运行验证通过**

Run: `uv run pytest tests/test_ai_space.py -k folder -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/space/schema.py backend/app/plugin/module_ai/space/service.py backend/app/plugin/module_ai/space/controller.py backend/tests/test_ai_space.py
git commit -m "feat(ai-space): 新增个人空间文件夹 CRUD 接口"
```

---

### Task 4: 文件 上传/列表/下载/预览/移动/删除/配额（服务 + API）

**Files:**
- Modify: `backend/app/plugin/module_ai/space/service.py`（追加文件方法）
- Modify: `backend/app/plugin/module_ai/space/controller.py`（追加文件路由）
- Modify: `backend/tests/test_ai_space.py`（追加文件用例）

**Interfaces:**
- Consumes: Task 3 的 service/controller 模式、`s3_client`、`filetype.py`。
- Produces（签名）：
  - `SpaceService.quota(user_id) -> dict`：`{"used_bytes": int, "quota_bytes": int, "max_file_bytes": int}`
  - `SpaceService.upload_file(user_id, filename, data: bytes, folder_id=None, source="upload") -> dict`（校验：folder 归属、size ≤ max_file_bytes、SUM+size ≤ quota；object_key=`ai-space/{user_id}/{YYYYMMDD}/{uuid4().hex}{ext}`；`asyncio.to_thread(s3_client.upload_fileobj, io.BytesIO(data), key, content_type=...)`；返回文件 dict）
  - `SpaceService.list_files(user_id, folder_id=None, keyword=None, file_type=None, page_no=1, page_size=20) -> dict`（`{items,total,has_next,page_no,page_size}`；keyword 对 name like；按 id 倒序）
  - `SpaceService.get_file(file_id, user_id) -> dict`（不存在/越权 → ValueError「文件不存在」）
  - `SpaceService.get_file_bytes(user_id, file_id) -> dict`：`{"data": bytes, "mime_type": str, "name": str, "file_type": str}`（越权/不存在 → ValueError；>20MB → ValueError；供智能体读取与对话引用共用）
  - `SpaceService.rename_file(file_id, name, user_id) -> dict`
  - `SpaceService.move_file(file_id, folder_id, user_id) -> dict`（folder 归属校验；目标为自身所在目录 → ValueError）
  - `SpaceService.delete_files(file_ids, user_id) -> dict`（`{"deleted": n}`；软删 + 对象删除）
  - `SpaceService.download_file(file_id, user_id) -> dict`：`{"object_key","name","mime_type"}`（controller 做 StreamingResponse，参照 knowledge/download_document）
  - `SpaceService.preview_file(file_id, user_id) -> dict`：文本类返回 `{"kind":"text","content":...}`（>500KB 截断 + `"truncated": true`）；图片/PDF/docx 返回 `{"kind": file_type}`（controller 对 image/pdf/docx 直接流式返回对象字节，前端 PDF vue-pdf-embed / docx mammoth —— 与知识库一致）；其它返回 400「该类型暂不支持预览」
  - 路由：`GET /files/list`、`POST /files/upload`（`UploadFile` + `Form(folder_id)`）、`GET /files/{id}/download`、`GET /files/{id}/preview`、`PUT /files/rename`、`POST /files/move`、`DELETE /files/delete`、`GET /space/quota`。

- [ ] **Step 1: 写失败测试（HTTP + S3 mock）**

```python
# 追加到 test_ai_space.py
def _upload(test_client, h, name="a.txt", content=b"hello", **kw):
    return test_client.post("/api/v1/ai/space/files/upload",
        files={"file": (name, content, "text/plain")}, data=kw, headers=h)

def test_file_upload_list_download_preview(test_client, auth_headers, monkeypatch):
    calls = {}
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj",
        lambda *a, **k: calls.setdefault("key", a[1]))
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
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    assert _upload(test_client, auth_headers, name="x.xyz", content=b"abc").status_code == 400
    assert _upload(test_client, auth_headers, name="empty.txt", content=b"").status_code == 400
def test_upload_quota_limit(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    from app.config.setting import settings
    monkeypatch.setattr(settings, "AI_SPACE_MAX_FILE_MB", 1)  # 临时降限避免构造 200MB
    big = b"x" * (1024 * 1024 + 1)
    assert _upload(test_client, auth_headers, name="big.txt", content=big).status_code == 400
def test_rename_move_delete_flow(test_client, auth_headers, monkeypatch):
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    monkeypatch.setattr("app.utils.s3_client.s3_client.delete_objects", lambda *a, **k: 0)
    h = auth_headers
    fid = _upload(test_client, h).json()["data"]["id"]
    folder = test_client.post("/api/v1/ai/space/folders/create", json={"name": "f"}, headers=h).json()["data"]["id"]
    mv = test_client.post("/api/v1/ai/space/files/move", json={"file_id": fid, "folder_id": folder}, headers=h)
    assert mv.status_code == 200 and mv.json()["data"]["folder_id"] == folder
    # 移动到自身目录 → 400
    self_mv = test_client.post("/api/v1/ai/space/files/move", json={"file_id": fid, "folder_id": folder}, headers=h)
    assert self_mv.status_code == 400
    rn = test_client.put("/api/v1/ai/space/files/rename", json={"file_id": fid, "name": "b.txt"}, headers=h)
    assert rn.status_code == 200
    dele = test_client.request("DELETE", "/api/v1/ai/space/files/delete", json=[fid], headers=h)
    assert dele.status_code == 200 and dele.json()["data"]["deleted"] == 1
def test_duplicate_name_allowed(test_client, auth_headers, monkeypatch):
    """同目录重名上传：允许（uuid 对象 key），不覆盖。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    h = auth_headers
    _upload(test_client, h, name="dup.txt"); _upload(test_client, h, name="dup.txt")
    lst = test_client.get("/api/v1/ai/space/files/list", headers=h).json()["data"]
    assert lst["total"] == 2
def test_preview_truncates_large_text(test_client, auth_headers, monkeypatch):
    """预览 600KB 文本 → 截断标记。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    fid = _upload(test_client, auth_headers, name="big.txt", content=b"x" * (600 * 1024)).json()["data"]["id"]
    pv = test_client.get(f"/api/v1/ai/space/files/{fid}/preview", headers=auth_headers).json()["data"]
    assert pv["truncated"] is True
def test_get_file_rejects_other_user(test_client, auth_headers, monkeypatch):
    """用户隔离：以其他 user_id 直接调服务读取 → 抛 ValueError（不影响他人记录）。"""
    monkeypatch.setattr("app.utils.s3_client.s3_client.upload_fileobj", lambda *a, **k: None)
    fid = _upload(test_client, auth_headers).json()["data"]["id"]
    import asyncio
    import pytest
    from app.plugin.module_ai.space.service import SpaceService
    with pytest.raises(ValueError):
        asyncio.run(SpaceService.get_file(fid, user_id=999999))
def test_no_auth_rejected(test_client):
    r = test_client.get("/api/v1/ai/space/files/list")
    assert r.status_code in (401, 403)
```
（注：隔离用例创建一个「第二用户」比较复杂——conftest 只有 admin；简化：用不存在的 user_id 直接调 service 断言 ValueError，或注册第二个用户后登录。实现时选后者或 service 级 mock。以「service 级越权测试」兜底。）

- [ ] **Step 2: 运行验证失败**

Run: `uv run pytest tests/test_ai_space.py -k "file or upload or quota or rename" -q`
Expected: FAIL（路由不存在）

- [ ] **Step 3: 实现文件方法与路由**

按上方接口。`delete_files` 先查对象 key 列表再软删，最后 `asyncio.to_thread(s3_client.delete_objects, keys)`（失败 log 不抛）；move 校验；upload 先 `sanitize_filename` + `classify_file`；quota 用 `select(func.sum(size))`。

- [ ] **Step 4: 运行验证通过**

Run: `uv run pytest tests/test_ai_space.py -q`
Expected: PASS（含 Task 3 文件夹用例全部）

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/space/ backend/tests/test_ai_space.py
git commit -m "feat(ai-space): 新增个人空间文件上传下载预览与配额接口"
```

---

### Task 5: 菜单与权限注册

**Files:**
- Modify: `backend/app/scripts/init_app.py`（`AI_BUTTON_PERMS` 追加 5 条；`pages` 追加一行）
- Test: `backend/tests/test_ai_menus.py`（追加断言）

**Interfaces:**
- `pages` 追加：`("个人工作空间", "AiPersonalSpace", "/ai/space", "module_ai/space/index", "module_ai:space:query", 7, "el-icon-FolderOpened")`（order 视现有冲突调整，保持与「工作台」相邻）。
- `AI_BUTTON_PERMS` 追加：`module_ai:space:{query,upload,download,delete,manage}` 5 条（中文名：查看个人空间/上传文件/下载文件/删除文件/管理文件夹）。

- [ ] **Step 1: 追加失败断言**

```python
# test_ai_menus.py 追加到 test_ai_menus_collapsed 内或新测试
def test_ai_space_menu_registered(test_client):
    from app.scripts import init_app
    import asyncio
    asyncio.run(init_app._ensure_ai_menus())
    menus = _fetch_menus()
    m = menus["AiPersonalSpace"]
    assert m.hidden is False and m.route_path == "/ai/space"
    assert m.component_path == "module_ai/space/index"
    perms = {c for c, _ in init_app.AI_BUTTON_PERMS}
    assert {"module_ai:space:query","module_ai:space:upload","module_ai:space:download","module_ai:space:delete","module_ai:space:manage"} <= perms
```

- [ ] **Step 2: 运行验证失败**

Run: `uv run pytest tests/test_ai_menus.py::test_ai_space_menu_registered -q`
Expected: FAIL

- [ ] **Step 3: 修改 `init_app.py`**

在 `pages` 列表「工作台」后插入；`AI_BUTTON_PERMS` 末尾追加。注意 `_ensure_ai_menus` 对存在菜单 `continue`，新库由本函数创建，无需手工 SQL。

- [ ] **Step 4: 运行验证通过（含回归）**

Run: `uv run pytest tests/test_ai_menus.py -q`
Expected: PASS（原有用例不破坏；新菜单不被 REMOVED/AI_MERGED_INTO_MARKET 误伤）

- [ ] **Step 5: 提交**

```bash
git add backend/app/scripts/init_app.py backend/tests/test_ai_menus.py
git commit -m "feat(ai-space): 注册个人空间菜单与按钮权限"
```

---

### Task 6: 智能体工具（保存/列出/读取）

**Files:**
- Modify: `backend/app/plugin/module_ai/assistant/tools.py`（TOOL_REGISTRY 注册 3 工具）
- Modify: `backend/app/plugin/module_ai/agno_tools/business.py`（新增 `build_workspace_tools()`）
- Modify: `backend/app/plugin/module_ai/assistant/agno_service.py`（`run_agno_tool_stream` 合并 workspace 工具）
- Test: `backend/tests/test_ai_space_tools.py`

**Interfaces:**
- `SpaceService.save_agent_file(user_id, name, content: str, file_type: str | None = None) -> dict`（service.py 追加：`sanitize_filename` 后编码 utf-8 bytes 走 `upload_file(..., source="agent")`；内容超 `max_file_bytes` 返回错误）
- `SpaceService.read_for_agent(user_id, file_id) -> str`（经 `get_file_bytes` 取字节：文本类原文；pdf/docx 用 `_extract_doc_text` 同款抽取（可 import `agno_service._extract_doc_text`），图片抛 ValueError「图片文件请直接查看」；>100KB 截断并加 `"\n…（内容过长已截断）"`）
- `SpaceService.list_for_agent(user_id, keyword=None, limit=20) -> list[dict]`（name/ext/file_type/size/created_time）
- TOOL_REGISTRY 新增（`business.py` 自动包装；`kind="action"`/`"read"`）：
  - `workspace_save_file(name, content, file_type?)` → 返回 `{file_id,name,size}`
  - `workspace_list_files(keyword?, limit?)` → 列表
  - `workspace_read_file(file_id)` → 文本内容
- `business.build_workspace_tools() -> list`：过滤 `TOOL_REGISTRY` 中 name 以 `workspace_` 开头者并包装（复用 `_build_agno_tool`）。
- `run_agno_tool_stream`：`tools = build_dynamic_tools(...) or []` 后追加 `business.build_workspace_tools()`。

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_ai_space_tools.py（纯逻辑 + mock）
def test_registry_contains_workspace_tools():
    from app.plugin.module_ai.assistant.tools import TOOL_REGISTRY
    names = {k for k in TOOL_REGISTRY if k.startswith("workspace_")}
    assert {"workspace_save_file","workspace_list_files","workspace_read_file"} <= names
def test_build_workspace_tools_nonempty():
    from app.plugin.module_ai.agno_tools.business import build_workspace_tools
    tools = build_workspace_tools()
    assert len(tools) == 3
    assert all(t.name.startswith("workspace_") for t in tools)
def test_save_agent_file_sanitizes_name(monkeypatch):
    """文件名清洗：'../x.md' → 'x.md'，且 source='agent'。"""
    import asyncio
    from app.plugin.module_ai.space import service as svc
    captured = {}
    async def fake_upload(user_id, filename, data, folder_id=None, source="upload"):
        captured["filename"] = filename
        captured["source"] = source
        return {"id": 1, "name": filename}
    monkeypatch.setattr(svc.SpaceService, "upload_file", staticmethod(fake_upload))
    from app.plugin.module_ai.assistant.tools import workspace_save_file
    asyncio.run(workspace_save_file(name="../x.md", content="hi", user_id=7))
    assert captured["filename"] == "x.md" and captured["source"] == "agent"
def test_read_for_agent_truncates_long_text(monkeypatch):
    """读取 200KB 文本 → 返回 ≤100KB 且含截断标记。"""
    import asyncio
    from app.plugin.module_ai.space import service as svc
    async def fake_bytes(user_id, file_id):
        return {"data": b"x" * (200 * 1024), "mime_type": "text/plain", "name": "t.txt", "file_type": "txt"}
    monkeypatch.setattr(svc.SpaceService, "get_file_bytes", staticmethod(fake_bytes))
    from app.plugin.module_ai.assistant.tools import workspace_read_file
    out = asyncio.run(workspace_read_file(file_id=1, user_id=7))
    assert len(out) <= 100 * 1024 + 100 and "截断" in out
```

- [ ] **Step 2: 运行验证失败**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_ai_space_tools.py -q`
Expected: FAIL

- [ ] **Step 3: 实现工具注册与合并**

`tools.py` 添加三个 `@tool(...)` 装饰函数（函数体调 `SpaceService.*_for_agent/save_agent_file`，`user_id=USER_ID_CONTEXT.get()`）；`business.py` 加 `build_workspace_tools`；`agno_service.run_agno_tool_stream` 中合并（注意 import 放函数内避免循环）。

- [ ] **Step 4: 运行验证通过**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_ai_space_tools.py -q`；再跑 `uv run pytest tests/test_ai_space.py -q`（回归）
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/assistant/tools.py backend/app/plugin/module_ai/agno_tools/business.py backend/app/plugin/module_ai/assistant/agno_service.py backend/tests/test_ai_space_tools.py
git commit -m "feat(ai-space): 智能体新增空间文件保存/列出/读取工具"
```

---

### Task 7: 对话引用工作空间文件

**Files:**
- Modify: `backend/app/plugin/module_ai/assistant/agno_service.py`（`_process_uploaded_files` 支持 `{"type":"workspace","file_id":...}`，签名加 `user_id=None`）
- Modify: `backend/tests/test_ai_assistant_files.py`（追加用例）
- Modify: `backend/tests/test_ai_space.py`（可选：集成断言）

**Interfaces:**
- Consumes: `SpaceService.get_file_bytes(user_id, file_id)`（Task 4 已定义）。
- `agno_service._resolve_workspace_file(file_id, user_id) -> dict | None`：内部 import `SpaceService` 调 `get_file_bytes`；任何异常返回 None（该文件跳过，不阻断对话）。
- `_process_uploaded_files(files, user_id=None)`：遇 dict 含 `type == "workspace"` 且 `file_id` → `_resolve_workspace_file` → 图片走 `Image`、其余走 `_extract_doc_text`。
- `run_agno_stream` 调用处：`_process_uploaded_files(files, user_id=user_id)`。

- [ ] **Step 1: 写失败测试**

```python
def test_process_files_workspace_image(monkeypatch):
    import app.plugin.module_ai.assistant.agno_service as svc
    async def fake(file_id, user_id):
        return {"data": b"img", "mime_type": "image/png", "name": "a.png", "file_type": "image"}
    monkeypatch.setattr(svc, "_resolve_workspace_file", fake)
    imgs, doc = _process_uploaded_files([{"type":"workspace","file_id":1,"name":"a.png"}], user_id=7)
    assert len(imgs) == 1 and doc == ""
def test_process_files_workspace_doc_extracts_text(monkeypatch):
    import app.plugin.module_ai.assistant.agno_service as svc
    async def fake(file_id, user_id):
        return {"data": "这是文档内容".encode(), "mime_type": "text/plain", "name": "说明.txt", "file_type": "txt"}
    monkeypatch.setattr(svc, "_resolve_workspace_file", fake)
    imgs, doc = _process_uploaded_files([{"type":"workspace","file_id":1}], user_id=7)
    assert imgs == [] and "这是文档内容" in doc
def test_process_files_workspace_missing_skipped(monkeypatch):
    import app.plugin.module_ai.assistant.agno_service as svc
    async def fake(file_id, user_id):
        return None
    monkeypatch.setattr(svc, "_resolve_workspace_file", fake)
    imgs, doc = _process_uploaded_files([{"type":"workspace","file_id":999}], user_id=7)
    assert imgs == [] and doc == ""
```

- [ ] **Step 2: 运行验证失败**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_ai_assistant_files.py -q`
Expected: FAIL

- [ ] **Step 3: 实现**

`_resolve_workspace_file`（函数内 import `SpaceService` 防顶层循环依赖）；`_process_uploaded_files` 在循环内新增 `type == "workspace"` 分支（该分支跳过 dataUrl 解析）；`run_agno_stream` 传入 `user_id`。

- [ ] **Step 4: 运行验证通过**

Run: `PYTEST_NO_APP=1 uv run pytest tests/test_ai_assistant_files.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/plugin/module_ai/assistant/agno_service.py backend/tests/test_ai_assistant_files.py
git commit -m "feat(ai-space): 助手对话支持引用个人空间文件"
```

---

### Task 8: 前端 API 封装与个人空间页面

**Files:**
- Create: `frontend/src/api/module_ai/space.ts`
- Create: `frontend/src/views/module_ai/space/index.vue`
- Test: `pnpm run type-check` + `pnpm run lint`

**Interfaces:**
- `frontend/src/api/module_ai/space.ts` 导出（仿 `frontend/src/api/module_ai/workspace.ts` 风格，axios 封装）：`getSpaceFolderTree` / `createSpaceFolder` / `updateSpaceFolder` / `deleteSpaceFolder` / `getSpaceFileList` / `uploadSpaceFile` / `downloadSpaceFile` / `previewSpaceFile` / `renameSpaceFile` / `moveSpaceFile` / `deleteSpaceFiles` / `getSpaceQuota`。
- `index.vue` 单根 `div.app-container`（注意 `<Transition>` 单根陷阱），结构：
  - 左 `el-card`：`el-tree` 文件夹树（默认展开一级，节点操作：新建/重命名/删除，`@node-click` 切换目录）
  - 右：面包屑（`el-breadcrumb`）+ 搜索（`el-input`）+ 类型筛选（`el-select`，选项=file_type 枚举）+ 上传（`el-upload` 拖拽 + 按钮，`http-request` 走 `uploadSpaceFile`，单文件逐传，逐项进度局部更新）+ 配额 `el-progress`
  - `el-table`：名称（类型图标 + 文本；点击名称预览）、类型、大小（`formatSize`）、来源（`el-tag`：AI 生成 / 用户上传）、更新时间、操作列（预览/下载/重命名/移动/删除），`v-hasPerm` 控制按钮
  - 预览 `el-dialog`：文本 `pre` 或 `v-html`；图片 `<img :src>`（经下载接口 blob → objectURL）；PDF `vue-pdf-embed`（blob objectURL，`import VuePdfEmbed from "vue-pdf-embed"`，项目已装）；docx 用 `mammoth.convertToHtml`（blob → HTML，知识库同款；knowledge/index.vue 已 import）
  - 删除/级联：`ElMessageBox.confirm`（文案含数量与不可恢复；按钮「删除/取消」）
  - 移动：`el-dialog` + 文件夹 `el-tree` 单选
  - 样式：全部 `--el-*` 变量；参照 `module_ai/knowledge/index.vue`。

- [ ] **Step 1: 写 `space.ts`（API 封装，先实现后接页面）**

无独立单测（前端以 type-check/lint 为准）；按 workspace.ts 同样式实现即可。

- [ ] **Step 2: 实现 `index.vue`**

按上述结构；注意：列表局部刷新（当前目录变更/上传完成/删除后仅重新拉当前目录）；预览优先级：文本/图片/PDF/docx（docx 走 mammoth，与知识库一致）。

- [ ] **Step 3: 验证**

Run: `pnpm run type-check && pnpm run lint`
Expected: 无新增错误（既有 LivePlayer 等预存 lint 错误除外）

- [ ] **Step 4: 提交**

```bash
git add frontend/src/api/module_ai/space.ts frontend/src/views/module_ai/space/index.vue
git commit -m "feat(ai-space): 新增个人工作空间前端页面"
```

---

### Task 9: SpaceFilePicker 组件并接入助手对话

**Files:**
- Create: `frontend/src/views/module_ai/space/components/SpaceFilePicker.vue`
- Modify: `frontend/src/components/AiAssistant/index.vue`（助手对话加「个人空间」按钮 + 选文件；files 载荷 `{type:"workspace",file_id,name}`）
- Test: `pnpm run type-check` + `pnpm run lint`

**Interfaces:**
- `SpaceFilePicker` props：`visible: boolean`，`multiple?: boolean`；emit：`update:visible`、`confirm(files: {file_id:number,name:string,file_type:string}[])`。
- 组件内部复用 `getSpaceFolderTree` + `getSpaceFileList`，树 + 表 + 多选（`el-table` selection）。
- `AiAssistant/index.vue`：在输入区增加「个人空间」`el-button`（`v-hasPerm="'module_ai:space:query'"`），打开 picker，确认后把引用并入 `chat.send` 的 files 参数（参照现有 `AiChatFilePayload` 的组装，确认 useAiChat 支持额外 file payload 合并）。

- [ ] **Step 1: 实现组件与接入**

- [ ] **Step 2: 验证**

Run: `pnpm run type-check && pnpm run lint`
Expected: 无新增错误

- [ ] **Step 3: 提交**

```bash
git add frontend/src/views/module_ai/space/components/SpaceFilePicker.vue frontend/src/components/AiAssistant/index.vue
git commit -m "feat(ai-space): 助手对话支持从个人空间选择文件"
```

---

### Task 10: 全量验证与文档收尾

**Files:**
- Create: `docs/ai-personal-workspace.md`（使用说明，仿 `docs/ai-capability-market.md`）
- Test: 全量相关测试 + lint

- [ ] **Step 1: 跑后端相关测试与全量回归**

Run: `cd backend && uv run pytest tests/test_ai_space.py tests/test_ai_space_tools.py tests/test_ai_models.py tests/test_ai_assistant_files.py tests/test_ai_menus.py tests/test_ai_assistant.py tests/test_ai_apps.py -q`
Expected: PASS
（提交前再跑一次全量 `uv run pytest -q -n 4`，确认无回归。）

- [ ] **Step 2: 后端 lint**

Run: `cd backend && uv run ruff check`
Expected: 0 error（既有文件仅新增代码）

- [ ] **Step 3: 写使用说明 `docs/ai-personal-workspace.md`**

含：功能入口、上传/下载/预览、文件夹、配额说明、智能体生成文件去向（来源=AI 生成）、对话引用空间文件、权限码表。

- [ ] **Step 4: 前端回归验证**

Run: `cd frontend && pnpm run type-check && pnpm run lint`
Expected: 无新增错误

- [ ] **Step 5: 提交**

```bash
git add docs/ai-personal-workspace.md
git commit -m "docs(ai): 新增个人工作空间使用说明"
```

---

## 验收（对应用户需求）

1. AI 管理下出现「个人工作空间」菜单，可进入（需 `module_ai:space:query`）。
2. 上传文件 → 列表可见 → 各类型预览 → 下载（文件名正确含中文）。
3. 多级文件夹：新建/重命名/移动/级联删除（确认文案含数量）。
4. 配额：单文件超 200MB 拒绝；总量超 10GB 拒绝并提示。
5. 智能体对话「生成文件」→ 空间出现该文件，来源=「AI 生成」；智能体可列出/读取。
6. 对话前从空间勾选文件（图片/文本/PDF）→ 智能体正确引用。
7. 用户隔离：他人文件不可见/不可下载（后端 404）。
