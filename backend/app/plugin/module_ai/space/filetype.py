"""个人空间文件类型与文件名工具：分类、清洗、mime 推断（纯逻辑，无 IO）。"""
import re

#: 扩展名 → 预览分类
FILE_TYPE_BY_EXT: dict[str, str] = {
    # 图片
    "jpg": "image", "jpeg": "image", "png": "image", "gif": "image",
    "webp": "image", "bmp": "image", "svg": "image", "ico": "image",
    # 文档
    "pdf": "pdf", "docx": "docx", "doc": "docx",
    # 文本
    "txt": "txt", "md": "md", "markdown": "md", "csv": "csv",
    "json": "json", "jsonl": "json", "log": "txt", "yaml": "txt", "yml": "txt",
    # 视频
    "mp4": "video", "avi": "video", "mov": "video", "mkv": "video",
    "webm": "video", "flv": "video",
    # 音频
    "mp3": "audio", "wav": "audio", "flac": "audio", "m4a": "audio",
    "ogg": "audio", "aac": "audio",
}

#: 部分 mime → 分类（扩展名缺失时兜底）
FILE_TYPE_BY_MIME: dict[str, str] = {
    "image/jpeg": "image", "image/png": "image", "image/gif": "image",
    "image/webp": "image", "image/svg+xml": "image", "image/bmp": "image",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "docx",
    "text/plain": "txt", "text/markdown": "md", "text/csv": "csv",
    "application/json": "json",
    "video/mp4": "video", "video/webm": "video", "video/x-matroska": "video",
    "audio/mpeg": "audio", "audio/wav": "audio", "audio/ogg": "audio",
    "audio/flac": "audio", "audio/mp4": "audio",
}

#: 分类 → 常见 mime（下载/预览用）
MIME_BY_FILE_TYPE: dict[str, str] = {
    "image": "image/png",
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "txt": "text/plain",
    "md": "text/markdown",
    "csv": "text/csv",
    "json": "application/json",
    "video": "video/mp4",
    "audio": "audio/mpeg",
    "other": "application/octet-stream",
}


def get_ext(name: str) -> str:
    """从文件名取小写扩展名（不含点）；无扩展名返回空串。"""
    if not name or "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].lower()


def classify_file(name: str, mime: str = "") -> str:
    """按扩展名优先、mime 兜底分类文件为 image/pdf/docx/txt/md/csv/json/video/audio/other。"""
    ext = get_ext(name)
    if ext in FILE_TYPE_BY_EXT:
        return FILE_TYPE_BY_EXT[ext]
    m = (mime or "").lower()
    if m in FILE_TYPE_BY_MIME:
        return FILE_TYPE_BY_MIME[m]
    if m.startswith("image/"):
        return "image"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    if m.startswith("text/"):
        return "txt"
    return "other"


def sanitize_filename(name: str) -> str:
    """清洗文件名：去掉路径分隔符/跨目录成分/危险字符；空则返回 unnamed（保留扩展名）。"""
    if not name:
        return "unnamed"
    # 取 basename，去掉路径成分
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    # 去掉危险字符（保留中文、字母数字、点、下划线、连字符、空格）
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "", name)
    # 折叠连续点、去掉首尾空白与点
    name = re.sub(r"\.{2,}", ".", name).strip(" .")
    return name or "unnamed"


def guess_mime(ext: str) -> str:
    """扩展名 → mime；无法推断返回 application/octet-stream。"""
    e = (ext or "").lower().lstrip(".")
    direct = {
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
        "svg": "image/svg+xml", "ico": "image/x-icon",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "doc": "application/msword",
        "txt": "text/plain", "md": "text/markdown", "markdown": "text/markdown",
        "csv": "text/csv", "json": "application/json", "jsonl": "application/json",
        "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
        "mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac",
        "m4a": "audio/mp4", "ogg": "audio/ogg", "aac": "audio/aac",
    }
    return direct.get(e, "application/octet-stream")
