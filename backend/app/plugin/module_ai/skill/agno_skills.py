"""技能执行器：把技能表记录构造为 agno ``Skills`` 实例（脚本落临时目录）。

方案 A：直接使用 agno 原生 Skill 机制。``Agent(skills=...)`` 会自动生成
``get_skill_instructions`` / ``get_skill_reference`` / ``get_skill_script`` 三个工具，
并在 system prompt 追加技能摘要片段；``get_skill_script(execute=True)`` 走 agno
``run_script``（subprocess）真正执行脚本（Windows 按 shebang 解析解释器）。

安全边界（复用既有原则）：只加载已启用（enabled）技能；创建/导入需
``module_ai:skill:create`` 权限；脚本由 agno 原生 ``run_script`` 以子进程执行。
"""
from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from agno.skills import Skills
from agno.skills.loaders.base import SkillLoader
from agno.skills.skill import Skill


def _safe_script_name(filename: str) -> str:
    """把导入/zip 解析出的脚本名规范化为安全相对路径（禁绝对路径与 ``..`` 穿越）。

    兼容 ``scripts/foo.py`` 统一去前缀；含子目录时保留相对层级（如 ``util/helper.py``）。
    """
    raw = (filename or "").replace("\\", "/").lstrip("/")
    parts = [p for p in raw.split("/") if p and p != "." and p != ".."]
    if parts and parts[0] == "scripts":
        parts = parts[1:]
    if not parts:
        return "script.py"
    return "/".join(parts)


def _build_skill(s: dict, tmp_dirs: list[str]) -> Skill:
    """由技能表字典构造 agno ``Skill``；scripts 字典落为独立临时目录脚本文件。"""
    root = tempfile.mkdtemp(prefix="aistation_skill_")
    tmp_dirs.append(root)
    scripts: dict = s.get("scripts") or {}
    script_names: list[str] = []
    if scripts:
        scripts_dir = Path(root) / "scripts"
        for filename, code in scripts.items():
            rel = _safe_script_name(filename)
            target = scripts_dir / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(code or "", encoding="utf-8")
            script_names.append(rel)
    return Skill(
        name=s.get("name") or "未命名技能",
        description=s.get("description") or "",
        instructions=s.get("content") or "",
        source_path=root,
        scripts=script_names,
        references=[],
    )


class DBSkillLoader(SkillLoader):
    """从技能表记录列表构造 agno ``Skill`` 的加载器。

    ``load()`` 在 ``Skills`` 构造时被调用一次；``cleanup()`` 删除临时脚本目录。
    """

    def __init__(self, skills: list[dict]):
        self.skills = skills or []
        self._tmp_dirs: list[str] = []

    def load(self) -> list[Skill]:
        return [_build_skill(s, self._tmp_dirs) for s in self.skills]

    def cleanup(self) -> None:
        for d in self._tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        self._tmp_dirs.clear()


def build_agno_skills(skill_dicts: list[dict]) -> tuple[Skills | None, object]:
    """把技能表记录构造为 agno ``Skills`` 实例。

    返回 ``(Skills | None, cleanup)``；``cleanup`` 在 Agent 运行结束后调用以删除临时
    脚本目录。单个技能失败只告警跳过（agno ``_load_skills`` 特性），不影响其它技能。
    """
    if not skill_dicts:
        return None, lambda: None
    loader = DBSkillLoader(skill_dicts)
    try:
        return Skills([loader]), loader.cleanup
    except Exception:
        for d in loader._tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)
        raise
