"""技能导入（SKILL.md / Zip）解析与接口测试。"""
import io
import zipfile

import pytest

from app.core.exceptions import CustomException
from app.plugin.module_ai.skill.importer import parse_skill_md, parse_zip

MD_WITH_FRONTMATTER = """---
name: 会议纪要大师
description: 把转写稿整理为决议与待办
version: 1.2
author: 张三
tags: [会议, 纪要]
---

# 会议纪要大师

按以下结构输出：会议信息 / 决议 / 待办 / 风险。
"""

MD_NO_FRONTMATTER = """# 简单技能

这是一个没有 frontmatter 的技能，用标题当名称。
"""


def test_parse_skill_md_with_frontmatter():
    """带 YAML frontmatter：字段被正确解析，正文不含 frontmatter。"""
    out = parse_skill_md(MD_WITH_FRONTMATTER)
    assert out["name"] == "会议纪要大师"
    assert out["description"] == "把转写稿整理为决议与待办"
    assert out["version"] == "1.2"
    assert out["author"] == "张三"
    assert out["tags"] == ["会议", "纪要"]
    assert out["content"].startswith("# 会议纪要大师")
    assert "---" not in out["content"].split("\n")[0]


def test_parse_skill_md_without_frontmatter():
    """无 frontmatter：用一级标题当名称，首段当描述。"""
    out = parse_skill_md(MD_NO_FRONTMATTER)
    assert out["name"] == "简单技能"
    assert "没有 frontmatter 的技能" in out["description"]
    assert out["version"] == "1.0"


def test_parse_skill_md_empty_rejected():
    with pytest.raises(CustomException):
        parse_skill_md("   ")


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_parse_zip_prefers_skill_md_and_collects_scripts():
    """Zip 内优先取 SKILL.md；附带脚本仅作为文本收集（不执行）。"""
    data = _make_zip(
        {
            "my-skill/SKILL.md": MD_WITH_FRONTMATTER,
            "my-skill/scripts/run.py": "print('hi')",
            "my-skill/README.md": "# 别的文档",
        }
    )
    out = parse_zip(data)
    assert out["name"] == "会议纪要大师"
    assert out["source_file"] == "my-skill/SKILL.md"
    assert "my-skill/scripts/run.py" in out["scripts"]
    assert "print('hi')" in out["scripts"]["my-skill/scripts/run.py"]


def test_parse_zip_without_markdown_rejected():
    """没有 Markdown 文档时拒绝导入。"""
    data = _make_zip({"a.txt": "no md here"})
    with pytest.raises(CustomException) as ei:
        parse_zip(data)
    assert "Markdown" in ei.value.msg


def test_parse_zip_invalid_bytes_rejected():
    with pytest.raises(CustomException) as ei:
        parse_zip(b"not a zip")
    assert "Zip" in ei.value.msg


# ---------------- 接口 ----------------

def test_api_import_skill_from_content(test_client, auth_headers):
    """粘贴导入：技能落库且默认停用。"""
    r = test_client.post(
        "/api/v1/ai/skills/import",
        headers=auth_headers,
        json={"content": MD_WITH_FRONTMATTER, "category": "办公效率", "source": "SkillHub"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "会议纪要大师"
    assert data["enabled"] is False, "导入后应默认停用"
    assert data["category"] == "办公效率"
    assert data["author"] == "张三"
    # 清理
    test_client.request("DELETE", "/api/v1/ai/skills/delete", json=[data["id"]], headers=auth_headers)


def test_api_import_skill_from_zip(test_client, auth_headers):
    """Zip 导入：解析 SKILL.md 并落库（脚本仅存文本）。"""
    payload = _make_zip({"SKILL.md": MD_WITH_FRONTMATTER, "scripts/tool.py": "x = 1"})
    r = test_client.post(
        "/api/v1/ai/skills/import-zip",
        headers=auth_headers,
        files={"file": ("my-skill.zip", payload, "application/zip")},
        data={"category": "导入技能", "source": "SkillHub"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["name"] == "会议纪要大师"
    assert data["enabled"] is False
    test_client.request("DELETE", "/api/v1/ai/skills/delete", json=[data["id"]], headers=auth_headers)


def test_api_import_requires_permission(test_client, auth_headers):
    """无 skill:create 权限的用户不能导入。"""
    import uuid

    suffix = uuid.uuid4().hex[:8]
    role = test_client.post(
        "/api/v1/system/role/create",
        headers=auth_headers,
        json={"name": f"pytest-imp-{suffix}", "code": f"IMP{suffix}"[:20], "order": 999, "data_scope": 1, "status": "0"},
    )
    role_id = role.json()["data"]["id"]
    username = f"imp{suffix}"
    test_client.post(
        "/api/v1/system/user/create",
        headers=auth_headers,
        json={"username": username, "name": "导入受限用户", "password": "123456", "status": "0", "role_ids": [role_id]},
    )
    login = test_client.post(
        "/api/v1/system/auth/login",
        data={"username": username, "password": "123456"},
        headers={"X-Forwarded-For": "127.0.0.1"},
    )
    limited = {
        "Authorization": f"Bearer {login.json()['data']['access_token']}",
        "X-Forwarded-For": "127.0.0.1",
    }
    r = test_client.post(
        "/api/v1/ai/skills/import",
        headers=limited,
        json={"content": MD_NO_FRONTMATTER},
    )
    assert r.status_code == 403, r.text
