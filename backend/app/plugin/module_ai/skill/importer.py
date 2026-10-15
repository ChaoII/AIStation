"""技能导入解析：兼容 SkillHub / Claude Skills 的 ``SKILL.md`` 与 Zip 包。

设计要点（安全优先）：
- **全程只在内存解析**，Zip 内容不落盘（天然规避路径穿越/zip-slip）；
- 限制包体积与文件数量，避免解压炸弹；
- 技能内附带的脚本只作为**文本内容**保存（存 ``scripts`` 字段），**绝不执行**；
- 导入的技能默认 ``enabled=False``，由用户在技能广场检查后再启用。
"""
from __future__ import annotations

import io
import re
import zipfile

from app.core.exceptions import CustomException

#: 单个 Zip 最大体积（字节）
MAX_ZIP_BYTES = 20 * 1024 * 1024
#: Zip 内最多处理的文件数
MAX_FILES = 200
#: 单个文本文件最大读取量（字节）
MAX_TEXT_BYTES = 512 * 1024

_FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\r?\n(.*?)\r?\n---\s*\r?\n?", re.S)
_TEXT_SUFFIXES = (".md", ".markdown", ".txt", ".py", ".js", ".ts", ".sh", ".json", ".yaml", ".yml", ".toml")


def _first_paragraph(body: str) -> str:
    """取正文首个非空、非标题段落作为描述。"""
    for line in (body or "").splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("---"):
            return s[:200]
    return ""


def parse_skill_md(text: str, fallback_name: str = "") -> dict:
    """解析 ``SKILL.md``：返回 ``{name, description, content, author, version, tags}``。

    frontmatter（YAML）为可选；缺失时用标题/首段兜底。
    """
    if not (text or "").strip():
        raise CustomException(msg="技能内容不能为空")

    meta: dict = {}
    body = text
    m = _FRONTMATTER_RE.match(text)
    if m:
        try:
            import yaml

            loaded = yaml.safe_load(m.group(1))
            if isinstance(loaded, dict):
                meta = loaded
        except Exception:  # noqa: BLE001  frontmatter 非法时按无 frontmatter 处理
            meta = {}
        body = text[m.end() :]

    name = str(meta.get("name") or "").strip()
    if not name:
        # 兜底：首个一级标题
        for line in body.splitlines():
            s = line.strip()
            if s.startswith("#"):
                name = s.lstrip("#").strip()
                break
    name = name or fallback_name or "未命名技能"

    description = str(meta.get("description") or "").strip() or _first_paragraph(body)

    tags = meta.get("tags") or meta.get("keywords") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]
    if not isinstance(tags, list):
        tags = []

    return {
        "name": name[:128],
        "description": description[:2000],
        "content": body.strip(),
        "author": str(meta.get("author") or meta.get("owner") or "").strip()[:64],
        "version": str(meta.get("version") or "1.0").strip()[:16],
        "tags": [str(t)[:32] for t in tags][:10],
    }


def parse_zip(data: bytes, fallback_name: str = "") -> dict:
    """从 Zip 包解析技能：优先 ``SKILL.md``，否则取首个 Markdown；附带脚本仅存文本。"""
    if not data:
        raise CustomException(msg="Zip 内容为空")
    if len(data) > MAX_ZIP_BYTES:
        raise CustomException(msg=f"Zip 过大（>{MAX_ZIP_BYTES // 1024 // 1024}MB）")

    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        raise CustomException(msg=f"不是有效的 Zip 包：{e}") from e

    names = [n for n in zf.namelist() if not n.endswith("/")]
    if len(names) > MAX_FILES:
        raise CustomException(msg=f"Zip 内文件过多（>{MAX_FILES}）")

    # 主文档：优先名为 SKILL.md 的文件（取路径最浅的），否则第一个 .md
    md_candidates = [n for n in names if n.lower().endswith((".md", ".markdown"))]
    if not md_candidates:
        raise CustomException(msg="Zip 内未找到 Markdown 技能文档（如 SKILL.md）")
    md_candidates.sort(key=lambda n: (n.count("/"), len(n)))
    main_name = next(
        (n for n in md_candidates if n.split("/")[-1].lower() == "skill.md"),
        md_candidates[0],
    )

    try:
        raw = zf.read(main_name)
    except Exception as e:  # noqa: BLE001
        raise CustomException(msg=f"读取 {main_name} 失败：{e}") from e
    text = raw[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")

    parsed = parse_skill_md(text, fallback_name=fallback_name or main_name.split("/")[-1])

    # 附带脚本/资源：只保存文本内容（不执行），排除主文档本身
    scripts: dict[str, str] = {}
    for n in names:
        if n == main_name or not n.lower().endswith(_TEXT_SUFFIXES):
            continue
        try:
            content = zf.read(n)[:MAX_TEXT_BYTES].decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            continue
        scripts[n] = content
        if len(scripts) >= 50:
            break

    parsed["scripts"] = scripts
    parsed["source_file"] = main_name
    return parsed
