"""标注图片处理：尺寸探测、缩略图生成与 Content-Type 映射。"""
import io

from PIL import Image, ImageOps

ALLOWED_IMAGE_EXTENSIONS: set[str] = {
    ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff",
}

_EXT_CONTENT_TYPE: dict[str, str] = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}

THUMBNAIL_MAX_SIDE = 512
THUMBNAIL_QUALITY = 85


def content_type_for(ext: str) -> str:
    """按扩展名返回 Content-Type，未知类型回退 octet-stream。"""
    return _EXT_CONTENT_TYPE.get(ext.lower(), "application/octet-stream")


def process_image(content: bytes) -> tuple[int, int, bytes | None]:
    """返回 (width, height, thumbnail_jpeg_bytes)。

    无法解析的图片返回 ``(0, 0, None)``，不抛异常。
    """
    try:
        with Image.open(io.BytesIO(content)) as opened:
            img = ImageOps.exif_transpose(opened)
            width, height = img.size
            thumb = img.copy()
            thumb.thumbnail((THUMBNAIL_MAX_SIDE, THUMBNAIL_MAX_SIDE))
            if thumb.mode not in ("RGB", "L"):
                thumb = thumb.convert("RGB")
            buf = io.BytesIO()
            thumb.save(buf, format="JPEG", quality=THUMBNAIL_QUALITY)
            return width, height, buf.getvalue()
    except Exception:
        return 0, 0, None
