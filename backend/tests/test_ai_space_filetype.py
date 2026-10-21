"""个人空间文件类型工具测试（纯逻辑，PYTEST_NO_APP 快速模式）。"""
from app.plugin.module_ai.space.filetype import (
    classify_file,
    guess_mime,
    sanitize_filename,
)
from app.config.setting import settings


def test_classify_by_ext_and_mime():
    assert classify_file("a.png", "application/octet-stream") == "image"
    assert classify_file("a.pdf", "") == "pdf"
    assert classify_file("报告.docx", "") == "docx"
    assert classify_file("data.csv", "") == "csv"
    assert classify_file("notes.MD", "") == "md"
    assert classify_file("noext", "text/plain") in ("txt", "other")  # mime 兜底
    assert classify_file("noext", "video/mp4") == "video"
    assert classify_file("unknown.xyz", "") == "other"


def test_sanitize_filename_strips_path():
    assert "/" not in sanitize_filename("../../etc/passwd.txt")
    assert "\\" not in sanitize_filename("..\\evil.txt")
    assert sanitize_filename("../x.txt") == "x.txt"
    assert sanitize_filename("a/../b.txt") == "b.txt"
    assert sanitize_filename("") == "unnamed"
    assert sanitize_filename("....") == "unnamed"
    assert sanitize_filename("正常 文件.md") == "正常 文件.md"


def test_guess_mime():
    assert guess_mime("png") == "image/png"
    assert guess_mime("pdf") == "application/pdf"
    assert guess_mime("MD") == "text/markdown"
    assert guess_mime("unknown") == "application/octet-stream"


def test_settings_have_quota_defaults():
    assert settings.AI_SPACE_MAX_FILE_MB == 200
    # 默认 2GB（2026-10-21 个人空间改造：可申请扩容，管理员按用户覆盖）
    assert settings.AI_SPACE_QUOTA_MB == 2048
