"""第 5 项：技能执行器（agno 原生 Skill 机制）测试。

验证把技能表记录（name/content/scripts 字典）构造为 agno ``Skills`` 实例，
脚本落临时目录后可由 agno ``run_script`` 真正执行（含 Windows shebang 处理）。
纯逻辑测试，无需应用构造（``PYTEST_NO_APP=1`` 快速模式）。
"""
import json
import os
from pathlib import Path

from agno.skills import Skills

from app.plugin.module_ai.skill.agno_skills import (
    DBSkillLoader,
    build_agno_skills,
)


def _skill_dict(name: str, content: str = "指令", scripts: dict | None = None) -> dict:
    return {
        "id": 1,
        "name": name,
        "description": f"{name} 描述",
        "content": content,
        "skill_type": "instruction",
        "scripts": scripts,
        "enabled": True,
    }


def _py_script(body: str) -> str:
    return "#!/usr/bin/env python3\n" + body


def test_build_skills_from_dicts():
    """构造 Skills 实例：记录技能名与指令内容。"""
    skills, cleanup = build_agno_skills(
        [_skill_dict("alpha", content="指令A"), _skill_dict("beta", content="指令B")]
    )
    try:
        assert isinstance(skills, Skills)
        assert skills.get_skill_names() == ["alpha", "beta"]
        assert skills.get_skill("alpha").instructions == "指令A"
        assert skills.get_skill("beta").description == "beta 描述"
    finally:
        cleanup()


def test_build_skills_empty():
    """无技能时返回 None，不报错。"""
    skills, cleanup = build_agno_skills([])
    assert skills is None
    cleanup()


def test_script_materialized_to_dir():
    """scripts 字典落为临时目录中的脚本文件，Skill.scripts 记录相对路径。"""
    scripts = {"hello.py": _py_script("print('hi')")}
    skills, cleanup = build_agno_skills([_skill_dict("demo", scripts=scripts)])
    try:
        skill = skills.get_skill("demo")
        assert skill.scripts == ["hello.py"]
        script_file = Path(skill.source_path) / "scripts" / "hello.py"
        assert script_file.exists()
        assert "print('hi')" in script_file.read_text(encoding="utf-8")
    finally:
        cleanup()


def test_get_skill_instructions_returns_json():
    """``get_skill_instructions`` 返回含 instructions 的 JSON。"""
    skills, cleanup = build_agno_skills([_skill_dict("alpha", content="详细指令")])
    try:
        # 直接调用工具方法
        out = json.loads(skills._get_skill_instructions("alpha"))
        assert out["skill_name"] == "alpha"
        assert out["instructions"] == "详细指令"
    finally:
        cleanup()


def test_run_script_executes_script():
    """``get_skill_script(execute=True)`` 通过 agno ``run_script`` 真正执行脚本。"""
    scripts = {"hello.py": _py_script("print('exec-ok')")}
    skills, cleanup = build_agno_skills([_skill_dict("run", scripts=scripts)])
    try:
        out = json.loads(skills._get_skill_script("run", "hello.py", execute=True))
        assert out["returncode"] == 0
        assert "exec-ok" in out["stdout"]
    finally:
        cleanup()


def test_cleanup_removes_temp_dir():
    """cleanup 删除临时脚本目录，避免残留。"""
    loader = DBSkillLoader([_skill_dict("tmp", scripts={"a.py": _py_script("pass")})])
    Skills([loader])
    before = set(loader._tmp_dirs)
    assert before
    loader.cleanup()
    for d in before:
        assert not os.path.exists(d)


def test_skill_validation_does_not_reject():  # noqa: D401  中文名/下划线不应被拒
    """中文 / 含下划线的技能名不应被 agno 校验拒绝（dataclass 不强制校验）。"""
    skills, cleanup = build_agno_skills([_skill_dict("数据清洗", content="x")])
    try:
        assert "数据清洗" in skills.get_skill_names()
    finally:
        cleanup()
