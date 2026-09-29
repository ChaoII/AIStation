"""车牌数据合成器（全面版）。

覆盖国内常见车牌类型与合成扰动：
- 类型（GA36-2018 附录B 式样）：小型/大型汽车（蓝/黄）、小型/大型新能源（绿/左黄右绿）、
  挂车与大型汽车后牌（双层黄）、涉外/特殊（黑）、使馆/领馆/港澳（黑底红使/领/港·澳）、
  教练（黄含学）、警用（白红警）、普通/轻便摩托、使馆/领馆/教练/警用摩托、低速车（双层）。
- 扰动：透视（近大远小梯形）、旋转、高斯/椒盐噪点、污渍/锈斑、遮挡带、高斯模糊、运动模糊、
  亮度/对比度/饱和度、投影等。
- 标注：车牌外框归一化 bbox（AxisAlignedBox，含变换后包围盒）+ 号牌字符串 + 字符框。
- 依赖 numpy 做噪点，PIL 渲染；中文字体跨平台兜底。
"""
import io
import math
import os
import random
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

# ---- 号牌字符池 ----
_PROVINCES = list("京津沪渝冀豫云辽黑湘皖鲁新苏浙赣鄂桂甘晋蒙陕吉闽贵粤青藏川宁琼")
_LETTERS = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # 去掉易混淆 I/O
# 新能源号牌序号能源标志位字母（表5/表6）：纯电 D/A/B/C/E，非纯电 F/G/H/J/K，即 A~K 去 I
_NEV_MARK = "ABCDEFGHJK"
_DIGITS = "0123456789"
_WORD = _LETTERS + _DIGITS


# --------------------------------------------------------------------------- #
# 车牌类型规格
# --------------------------------------------------------------------------- #
@dataclass
class _PlateSpec:
    key: str
    label: str
    kind: str  # "single" | "double"（双层=上小字下大字）
    aw: int  # 号牌宽度（mm，按 GA36-2018 表1）
    ah: int  # 号牌高度（mm）
    bg: str  # "blue" | "green_grad" | "split" | "yellow" | "black" | "white"
    text_color: tuple
    frame: tuple
    chars: int = 6  # 主行字符数（不含省份汉字，见 gen_text）
    mark: str = ""  # 附加标记字（警/使/领/学/挂）
    mark_color: tuple = (200, 30, 30)
    dot_after: int | None = None  # 单排间隔符·所在字符下标（None=无间隔符）
    top_len: int = 2  # 双层上排取 text 前几个字符（默认 2=省+发牌机关）
    top_mark: str = ""  # 双层上排附加字符（如领馆摩托「领」在省后）
    top_mark_color: tuple = (200, 30, 30)
    top_dot_after: int | None = None  # 双层上排间隔符位（默认 None -> 上排≥2字时在省后）


# GA36-2018 表1：号牌的分类、规格、颜色及适用范围
_PLATE_SPECS: dict[str, _PlateSpec] = {
    "blue": _PlateSpec("blue", "小型汽车号牌(蓝)", "single", 440, 140, "blue", (255, 255, 255), (255, 255, 255), 6, dot_after=1),
    "green": _PlateSpec("green", "小型新能源汽车号牌(绿)", "single", 480, 140, "green_grad", (0, 0, 0), (0, 0, 0), 6, dot_after=None),
    "green_large": _PlateSpec("green_large", "大型新能源汽车号牌(黄绿)", "single", 480, 140, "split", (0, 0, 0), (0, 0, 0), 6, dot_after=None),
    "yellow": _PlateSpec("yellow", "大型汽车号牌(黄)", "single", 440, 140, "yellow", (0, 0, 0), (0, 0, 0), 6, dot_after=1),
    "yellow_double": _PlateSpec("yellow_double", "挂车号牌(双层黄)", "double", 440, 220, "yellow", (0, 0, 0), (0, 0, 0), 6, mark="挂", mark_color=(0, 0, 0), top_dot_after=0),
    "large_rear": _PlateSpec("large_rear", "大型汽车后号牌(双层黄)", "double", 440, 220, "yellow", (0, 0, 0), (0, 0, 0), 6, top_dot_after=0),
    "black": _PlateSpec("black", "涉外/特殊号牌(黑)", "single", 440, 140, "black", (255, 255, 255), (255, 255, 255), 6, dot_after=1),
    "embassy": _PlateSpec("embassy", "使馆汽车号牌(黑底白使)", "single", 440, 140, "black", (255, 255, 255), (255, 255, 255), 6, mark="使", mark_color=(255, 255, 255), dot_after=2),
    "consulate": _PlateSpec("consulate", "领馆汽车号牌(黑底白领)", "single", 440, 140, "black", (255, 255, 255), (255, 255, 255), 6, mark="领", mark_color=(255, 255, 255), dot_after=3),
    "hk_mo": _PlateSpec("hk_mo", "港澳入出境汽车号牌(黑)", "single", 440, 140, "black", (255, 255, 255), (255, 255, 255), 6, dot_after=1),
    "coach": _PlateSpec("coach", "教练汽车号牌(黄含学)", "single", 440, 140, "yellow", (0, 0, 0), (0, 0, 0), 6, mark="学", mark_color=(0, 0, 0), dot_after=1),
    "police": _PlateSpec("police", "警用汽车号牌(白红警)", "single", 440, 140, "white", (15, 20, 35), (0, 0, 0), 6, mark="警", mark_color=(200, 30, 30), dot_after=0),
    "motorcycle": _PlateSpec("motorcycle", "普通摩托车号牌(黄)", "double", 220, 140, "yellow", (0, 0, 0), (0, 0, 0), 6, top_dot_after=0),
    "light_motorcycle": _PlateSpec("light_motorcycle", "轻便摩托车号牌(蓝)", "double", 220, 140, "blue", (255, 255, 255), (255, 255, 255), 6, top_dot_after=0),
    "embassy_motor": _PlateSpec("embassy_motor", "使馆摩托车号牌(黑)", "double", 220, 140, "black", (255, 255, 255), (255, 255, 255), 6, top_len=3, top_dot_after=None, mark="使", mark_color=(255, 255, 255)),
    "consulate_motor": _PlateSpec("consulate_motor", "领馆摩托车号牌(黑)", "double", 220, 140, "black", (255, 255, 255), (255, 255, 255), 6, top_len=1, top_mark="领", top_mark_color=(255, 255, 255), top_dot_after=0),
    "coach_motor": _PlateSpec("coach_motor", "教练摩托车号牌(黄)", "double", 220, 140, "yellow", (0, 0, 0), (0, 0, 0), 6, mark="学", mark_color=(0, 0, 0), top_dot_after=0),
    "police_motor": _PlateSpec("police_motor", "警用摩托车号牌(白)", "double", 220, 140, "white", (15, 20, 35), (0, 0, 0), 6, mark="警", mark_color=(200, 30, 30), top_dot_after=0),
    "low_speed": _PlateSpec("low_speed", "低速车号牌(黄)", "double", 300, 165, "yellow", (0, 0, 0), (0, 0, 0), 6, top_dot_after=0),
}


def gen_text(spec: _PlateSpec, rng: random.Random) -> str:
    """按类型生成号牌字符串（GA36-2018 图B.1~B.17 式样）。"""
    prov = rng.choice(_PROVINCES)
    letter = rng.choice(_LETTERS)

    # 新能源（小型，前牌）：省 + 发牌机关 + 序号(以能源标志字母开头)。  例：京A·D12345
    if spec.key == "green":
        marker = rng.choice(_NEV_MARK)
        return f"{prov}{letter}{marker}" + "".join(rng.choice(_WORD) for _ in range(5))
    # 大型新能源（后牌）：序号以能源标志字母结尾  例：京A12345D
    if spec.key == "green_large":
        marker = rng.choice(_NEV_MARK)
        return f"{prov}{letter}" + "".join(rng.choice(_WORD) for _ in range(5)) + marker
    # 使馆（汽车/摩托）：驻华机构号(3 位) + 序号(3 位)  例：224·578，末尾加红「使」
    if spec.key in ("embassy", "embassy_motor"):
        return "".join(rng.choice(_DIGITS) for _ in range(3)) + "".join(rng.choice(_DIGITS) for _ in range(3))
    # 领馆汽车：省简称 + 领馆号(3 位) + 序号(2 位)  例：沪224·78，末尾加红「领」；领馆摩托为省简称+5 位序号
    if spec.key == "consulate":
        return f"{prov}" + "".join(rng.choice(_DIGITS) for _ in range(3)) + "".join(rng.choice(_DIGITS) for _ in range(2))
    if spec.key == "consulate_motor":
        return f"{prov}" + "".join(rng.choice(_DIGITS) for _ in range(5))
    # 港澳入出境：省简称 + 发牌机关(Z) + 序号(4 位) + 港/澳  例：粤Z·F023港
    if spec.key == "hk_mo":
        return f"{prov}{letter}" + "".join(rng.choice(_WORD) for _ in range(4)) + rng.choice("港澳")
    # 教练/警用/挂车/教练摩托/警用摩托：省 + 发牌机关 + 序号(4 位)，末尾加特种字
    if spec.key in ("coach", "police", "coach_motor", "police_motor", "yellow_double"):
        return f"{prov}{letter}" + "".join(rng.choice(_WORD) for _ in range(4))
    # 默认（蓝/黄/黑/大型汽车后/摩托/轻便摩托/低速车）：省 + 发牌机关 + 序号(5 位)  例：京A·F0236
    return f"{prov}{letter}" + "".join(rng.choice(_WORD) for _ in range(5))


def _full_text(spec: _PlateSpec, text: str) -> str:
    """构造号牌完整字符串（含上下排特种字，供标注/OCR 与板面对齐，不含间隔符）。"""
    if spec.kind == "double":
        return text[: spec.top_len] + spec.top_mark + text[spec.top_len:] + spec.mark
    return text + spec.mark


# --------------------------------------------------------------------------- #
# 号牌专用字体（随模块打包，已子集化）
# --------------------------------------------------------------------------- #
_FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")
_FONT_CN = os.path.join(_FONT_DIR, "plate_cn.ttf")     # 汉字（省简称/特种字）
_FONT_EN = os.path.join(_FONT_DIR, "platechar.ttf")   # 数字/字母（号牌专用字体）
_FONT_CACHE: dict = {}


def _get_font(ch: str, size: int) -> ImageFont.ImageFont:
    """按字符选择号牌专用字体：汉字用 plate_cn，字母数字用 platechar。"""
    path = _FONT_EN if ch.isascii() and ch.isalnum() else _FONT_CN
    key = (path, size)
    if key not in _FONT_CACHE:
        _FONT_CACHE[key] = ImageFont.truetype(path, size)
    return _FONT_CACHE[key]


# --------------------------------------------------------------------------- #
# 新能源号牌专用字体（绿牌）：与蓝牌号牌字体不同，逐字符图片取自公开车牌生成仓库
# --------------------------------------------------------------------------- #
_GREEN_DIR = os.path.join(_FONT_DIR, "green")
_GREEN_CACHE: dict = {}


def _get_green_mask(ch: str) -> Image.Image | None:
    """加载新能源号牌字体某个字符的灰度字形（黑字白底），没有则返回 None。"""
    if ch in _GREEN_CACHE:
        return _GREEN_CACHE[ch]
    fn = os.path.join(_GREEN_DIR, f"{ord(ch):04x}.png")
    m = None
    if os.path.exists(fn):
        try:
            m = Image.open(fn).convert("L")
        except Exception:
            m = None
    _GREEN_CACHE[ch] = m
    return m


def _green_glyph_tile(ch: str, glyph_h: int, color) -> Image.Image | None:
    """把新能源字体字形渲染成指定高度、指定颜色的透明 tile（保持其高瘦比例）。"""
    mask = _get_green_mask(ch)
    if mask is None:
        return None
    nh = int(glyph_h)
    nw = max(1, int(mask.width * (glyph_h / mask.height)))
    m = mask.resize((nw, nh), Image.LANCZOS)
    alpha = m.point(lambda p: 255 - p)  # 黑字不透明、白底透明
    rgb = Image.new("RGB", (nw, nh), color)
    tile = Image.new("RGBA", (nw, nh))
    tile.paste(rgb, (0, 0))
    tile.putalpha(alpha)
    return tile


# --------------------------------------------------------------------------- #
# 车牌板面绘制（反光膜 + 等宽字符 + 间隔符）
# --------------------------------------------------------------------------- #
# 大型新能源黄绿分色：左黄区占总宽比例（图7：省+发牌机关区 120/480=0.25）
_SPLIT_RATIO = 0.25

# --------------------------------------------------------------------------- #
# GA 36-2018 号牌版面尺寸表（单位：毫米），依据标准第5章式样图：
#   图1  440x140（大型汽车前/小型汽车/港澳/教练）   字符90 字距12 间隔符10 边距15 R10
#   图2  使馆汽车（440x140）                        220=机构编号·序号 使
#   图4/5 警用汽车（440x140）                       省·发牌机关 序号 警
#   图6  440x220（大型汽车后/挂车）双排             上排60 下排110 字距15 边距27.5
#   图7/8 480x140（小型新能源/大型新能源汽车）      字符90 字距9 组间距49 边距15.5
#   图9~12 220x140（摩托车）双排                     上排50 下排60 字距10 边距15 R8
#   图19 300x165（低速车）双排                       字符90 字距12 间隔符20 边距15
# 字符宽 = 高 x 0.5（45/90）。
# --------------------------------------------------------------------------- #
_GA36 = {
    "auto":   {"aw": 440, "ah": 140, "r": 10, "ch": 90, "gap": 12, "dot": 10, "margin": 15.0, "group": 0,
               "top_ch": 0, "top_margin": 25.0, "row_gap": 0, "bot_margin": 25.0},
    "double": {"aw": 440, "ah": 220, "r": 10, "ch": 110, "gap": 15, "dot": 10, "margin": 27.5, "group": 0,
               "top_ch": 60, "top_margin": 15.0, "row_gap": 15, "bot_margin": 20.0},
    "nev":    {"aw": 480, "ah": 140, "r": 10, "ch": 90, "gap": 9, "dot": 0, "margin": 15.5, "group": 49,
               "top_ch": 0, "top_margin": 25.0, "row_gap": 0, "bot_margin": 25.0},
    "moto":   {"aw": 220, "ah": 140, "r": 8, "ch": 60, "gap": 10, "dot": 10, "margin": 15.0, "group": 0,
               "top_ch": 50, "top_margin": 10.0, "row_gap": 10, "bot_margin": 10.0},
    "low":    {"aw": 300, "ah": 165, "r": 10, "ch": 90, "gap": 12, "dot": 20, "margin": 15.0, "group": 0,
               "top_ch": 50, "top_margin": 10.0, "row_gap": 10, "bot_margin": 5.0},
}


def _ga_of(spec: _PlateSpec) -> dict:
    """按号牌外廓尺寸映射到 GA36 版式尺寸表。"""
    if spec.aw == 480:
        return _GA36["nev"]
    if spec.aw == 440 and spec.ah == 220:
        return _GA36["double"]
    if spec.aw == 220:
        return _GA36["moto"]
    if spec.aw == 300:
        return _GA36["low"]
    return _GA36["auto"]


# --------------------------------------------------------------------------- #
# 真实反光膜背景模板：圆角/边框/安装孔自带，取自公开车牌生成仓库（更真实）
# --------------------------------------------------------------------------- #
_TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
_TEMPLATE_MAP = {
    "blue": "blue_440x140.png",
    "green": "green_car_480.png",
    "green_large": "green_truck_480.png",
    "yellow": "yellow_440x140.png",
    "yellow_double": "yellow_double_440x220.png",
    "large_rear": "yellow_double_440x220.png",
    "black": "black_140.png",
    "embassy": "embassy_440x140.png",
    "consulate": "consulate_440x140.png",
    "hk_mo": "hkmo_440x140.png",
    "coach": "yellow_440x140.png",
    "police": "white_140.png",
    # 摩托车（220×140，R8）
    "motorcycle": "moto_yellow.png",
    "light_motorcycle": "moto_blue.png",
    "coach_motor": "moto_yellow.png",
    "embassy_motor": "moto_black.png",
    "consulate_motor": "moto_black2.png",
    "police_motor": "moto_white.png",
    # 低速车（300×165）
    "low_speed": "low_300x165.png",
}
_TEMPLATE_CACHE: dict = {}


def _strip_white_matte(img: Image.Image) -> Image.Image:
    """去掉模板四周的纯色遮罩（白/灰），只保留圆角内的板面（真透明圆角）。"""
    import numpy as np
    from PIL import ImageDraw

    rgba = img.convert("RGBA")
    # 四角已是透明（如用户提供的模板）则无需处理
    if rgba.getpixel((0, 0))[3] == 0 and rgba.getpixel((rgba.width - 1, 0))[3] == 0:
        return rgba
    probe = rgba.convert("RGB").copy()
    w, h = rgba.size
    for xy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        r, g, b = probe.getpixel(xy)
        if max(r, g, b) - min(r, g, b) <= 24 and r >= 90:  # 灰/白遮罩
            ImageDraw.floodfill(probe, xy, (255, 0, 255), thresh=26)
    arr = np.array(probe)
    matte = (arr[:, :, 0] > 250) & (arr[:, :, 1] < 5) & (arr[:, :, 2] > 250)
    alpha = np.array(rgba.split()[3])
    alpha[matte] = 0
    rgba.putalpha(Image.fromarray(alpha))
    return rgba


def _get_template(spec_key: str) -> Image.Image | None:
    """加载号牌真实反光膜模板（RGBA，去除白边后圆角透明）；无对应模板返回 None。"""
    fn = _TEMPLATE_MAP.get(spec_key)
    if not fn:
        return None
    path = os.path.join(_TEMPLATE_DIR, fn)
    if path not in _TEMPLATE_CACHE:
        try:
            _TEMPLATE_CACHE[path] = _strip_white_matte(Image.open(path).convert("RGBA")) if os.path.exists(path) else None
        except Exception:
            _TEMPLATE_CACHE[path] = None
    return _TEMPLATE_CACHE[path]


def _plate_background(spec: _PlateSpec, w: int, h: int) -> Image.Image:
    """绘制反光膜底：优先用真实模板（圆角/边框/安装孔），否则合成渐变 + 高光 + 暗角。"""
    tpl = _get_template(spec.key)
    if tpl is not None:
        return tpl.resize((w, h), Image.LANCZOS)

    img = Image.new("RGB", (w, h), (0, 0, 0))
    d = ImageDraw.Draw(img)
    if spec.bg == "split":
        # 左黄右绿（大型新能源，图B.4）：左侧黄区放省简称+发牌机关，右侧绿区放序号
        split_x = int(w * _SPLIT_RATIO)
        yellow = (250, 196, 86)
        green = (16, 158, 100)
        for x in range(w):
            d.line([(x, 0), (x, h)], fill=yellow if x < split_x else green)
    else:
        palettes = {
            "blue": ((38, 80, 158), (14, 34, 88)),
            "yellow": ((250, 210, 72), (204, 148, 24)),
            "green_grad": ((22, 156, 100), (0, 92, 58)),
            "black": ((44, 44, 48), (8, 8, 10)),
            "white": ((252, 252, 254), (198, 200, 208)),
        }
        top, bottom = palettes.get(spec.bg, palettes["blue"])
        for y in range(h):
            t = y / max(1, h - 1)
            c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
            d.line([(0, y), (w, y)], fill=c)

    # 斜向反光高光带
    sheen = Image.new("L", (w, h), 0)
    sd = ImageDraw.Draw(sheen)
    step = max(6, w // 40)
    x = -h
    while x < w + h:
        alpha = 26 if (x // step) % 2 == 0 else 6
        sd.line([(x, h), (x + h, 0)], fill=alpha, width=max(4, w // 120))
        x += step // 2
    sheen = sheen.filter(ImageFilter.GaussianBlur(max(4, w // 60)))
    light = Image.new("RGB", (w, h), (255, 255, 255))
    img = Image.composite(light, img, sheen.point(lambda p: int(p * 0.8)))

    # 轻微暗角
    vig = Image.new("L", (w, h), 0)
    vd = ImageDraw.Draw(vig)
    vd.rectangle([0, 0, w, h], fill=18)
    vd.rectangle([int(w * 0.04), int(h * 0.04), int(w * 0.96), int(h * 0.96)], fill=0)
    vig = vig.filter(ImageFilter.GaussianBlur(max(2, h // 6)))
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    img = Image.composite(dark, img, vig)

    # 圆角 + 边框（无真实模板时的兜底，保证所有号牌都圆润、带边框）
    img = img.convert("RGBA")
    rad = max(4, h // 12)
    mask = Image.new("L", (w, h), 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle([0, 0, w - 1, h - 1], radius=rad, fill=255)
    img.putalpha(mask)
    bd = ImageDraw.Draw(img)
    fw = max(3, h // 42)
    bd.rounded_rectangle([0, 0, w - 1, h - 1], radius=rad, outline=spec.frame, width=fw)
    return img


def _glyph_tile(ch: str, glyph_h: int, color, green: bool = False) -> Image.Image:
    """把单个字符按固定字高渲染成透明图。
    字母/数字按号牌字体的高瘦比例压缩（宽≈高*0.5，国标约 43/90mm）；汉字保持方形。
    green=True 时用新能源号牌专用字体（绿牌），与蓝牌字体不同。
    """
    if green:
        t = _green_glyph_tile(ch, glyph_h, color)
        if t is not None:
            return t
    font = _get_font(ch, int(glyph_h * 1.4))
    canvas_h = int(glyph_h * 1.6) + 12
    big_w = int(glyph_h * 1.9) + 12
    tmp = Image.new("RGBA", (big_w, canvas_h), (0, 0, 0, 0))
    td = ImageDraw.Draw(tmp)
    bb = td.textbbox((0, 0), ch, font=font)
    tw = bb[2] - bb[0]
    th = bb[3] - bb[1]
    td.text(((big_w - tw) / 2 - bb[0], (canvas_h - th) / 2 - bb[1]), ch,
            font=font, fill=color)
    box = tmp.getbbox()
    if box is None:
        return Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    g = tmp.crop(box)
    nh = max(1, int(glyph_h))
    base = g.width * (glyph_h / g.height)
    # 图1：号牌字符宽 = 高×0.5（45/90mm），汉字/字母/数字一致；窄字符(1/I)保持天然细长
    if ch in ("1", "I"):
        nw = max(1, int(base))
    else:
        nw = max(1, int(glyph_h * 0.5))
    return g.resize((nw, nh), Image.LANCZOS)


def _draw_row(tile: Image.Image, items: list, y0: float, y1: float, dot_after: int | None,
              scale: float, ch_mm: float, gap_mm: float, dot_mm: float,
              green: bool = False, x_start_mm: float | None = None,
              region: tuple | None = None, draw_dot: bool = False) -> None:
    """按 GA 36-2018 尺寸排布一行字符（尺寸单位 mm，scale=像素/毫米）。
    x_start_mm 给定时自该处左对齐起排，否则在 region 或整板内水平居中。
    items 为 [(字符, 颜色)]，dot_after 为间隔符所在字符下标。
    draw_dot=True 时才绘制间隔符；底图已固定间隔符的牌型传 False（只留空位）。
    """
    w, h = tile.size
    if not items:
        return
    glyph_h = max(1, int(ch_mm * scale))
    interval = max(1, int(gap_mm * scale))
    n = len(items)
    glyphs = [(ch, _glyph_tile(ch, glyph_h, color, green)) for ch, color in items]
    dot_w = max(1, int(dot_mm * scale)) if (dot_after is not None and dot_after < n - 1) else 0
    total = sum(g.width for _, g in glyphs) + (n - 1) * interval + dot_w
    rx0, rx1 = region if region is not None else (0, w)
    rw = rx1 - rx0
    if total > rw * 0.98:
        sc = (rw * 0.98) / total
        glyphs = [(ch, g.resize((max(1, int(g.width * sc)), max(1, int(g.height * sc))), Image.LANCZOS))
                  for ch, g in glyphs]
        interval = max(1, int(interval * sc))
        dot_w = max(1, int(dot_w * sc)) if dot_w else 0
        total = sum(g.width for _, g in glyphs) + (n - 1) * interval + dot_w
    x = (rx0 + x_start_mm * scale) if x_start_mm is not None else (rx0 + (rw - total) / 2)
    gh = glyphs[0][1].height
    y = y0 + (y1 - y0 - gh) / 2
    d = ImageDraw.Draw(tile) if draw_dot else None
    for i, (_ch, g) in enumerate(glyphs):
        tile.paste(g, (int(x), int(y)), g)
        x += g.width
        if i == dot_after and dot_after is not None:
            # 底图已固定间隔符时不绘制，仅留出空位（识别文本不含点）
            if draw_dot:
                dot_cx = x + interval + dot_w / 2
                dot_cy = y + g.height / 2
                dr = max(2, int(gh * 0.06))
                d.ellipse([dot_cx - dr, dot_cy - dr, dot_cx + dr, dot_cy + dr], fill=items[0][1])
            x += interval + dot_w
        elif i < n - 1:
            x += interval


def _draw_emblem(tile: Image.Image, cx: int, cy: int, r: int) -> None:
    """在黄绿分界处画一个简化国徽（金环 + 红底 + 金星），对应图B.4。"""
    d = ImageDraw.Draw(tile)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(235, 200, 60))
    ir = int(r * 0.76)
    d.ellipse([cx - ir, cy - ir, cx + ir, cy + ir], fill=(185, 32, 32))
    star_r = int(r * 0.42)
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = star_r if i % 2 == 0 else star_r * 0.42
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    d.polygon(pts, fill=(235, 200, 60))


def _plate_surface(spec: _PlateSpec, w: int, h: int, text: str) -> Image.Image:
    """绘制一张不含旋转/透视的车牌 RGBA 板面（GA36 尺寸 + 真实反光膜模板）。"""
    tile = _plate_background(spec, w, h).convert("RGBA")
    has_tpl = _get_template(spec.key) is not None
    color = spec.text_color
    is_green = spec.key in ("green", "green_large")
    ga = _ga_of(spec)
    scale = h / spec.ah  # 像素/毫米
    ch, gap, dot, margin = ga["ch"], ga["gap"], ga["dot"], ga["margin"]

    top_mm, bot_mm = ga["top_margin"], ga["bot_margin"]

    if is_green:
        # 新能源（图7/图8）：省简称+发牌机关（京A）| 组间距49 + 国徽 | 序号(D..)
        y0, y1 = top_mm * scale, (spec.ah - bot_mm) * scale
        prefix, suffix = text[:2], text[2:]
        _draw_row(tile, [(c, color) for c in prefix], y0, y1, None, scale, ch, gap, dot,
                  green=True, x_start_mm=margin)
        pw_mm = sum(_glyph_tile(c, int(ch * scale), color, True).width for c in prefix) / scale
        gap_l_mm = gap * (len(prefix) - 1)
        sx = margin + pw_mm + gap_l_mm + ga["group"]
        _draw_row(tile, [(c, color) for c in suffix], y0, y1, None, scale, ch, gap, dot,
                  green=True, x_start_mm=sx)
        if not has_tpl:
            split_x = int((margin + pw_mm + gap_l_mm + ga["group"] / 2) * scale)
            _draw_emblem(tile, split_x, h // 2, max(3, int(h * 0.15)))
    elif spec.kind == "double":
        # 双层（图6/图9~12/图19）：上排小字（省·发牌机关），下排大字（序号+特种字）
        # 上下边距/行距/行高按 GA36
        top_ch = ga["top_ch"] or ch
        t0, t1 = top_mm * scale, (top_mm + top_ch) * scale
        b0 = (top_mm + top_ch + ga["row_gap"]) * scale
        b1 = (spec.ah - bot_mm) * scale
        top = [(c, color) for c in text[: spec.top_len]]
        if spec.top_mark:
            top.append((spec.top_mark, spec.top_mark_color))
        dot_after = spec.top_dot_after if spec.top_dot_after is not None else (0 if len(top) >= 2 else None)
        _draw_row(tile, top, t0, t1, dot_after, scale, top_ch, gap, dot)
        bottom = [(c, color) for c in text[spec.top_len:]]
        if spec.mark:
            bottom.append((spec.mark, spec.mark_color))
        _draw_row(tile, bottom, b0, b1, None, scale, ch, gap, dot)
    else:
        items = [(c, color) for c in text]
        if spec.mark:
            items.append((spec.mark, spec.mark_color))
        y0, y1 = top_mm * scale, (spec.ah - bot_mm) * scale
        _draw_row(tile, items, y0, y1, spec.dot_after, scale, ch, gap, dot, green=is_green,
                  x_start_mm=margin)
    return tile


# --------------------------------------------------------------------------- #
# 角点变换（旋转 + 透视）与 QUAD 映射
# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
# 扰动参数定义（前端据此渲染可调区间；键 -> 默认 [下限, 上限]）
# --------------------------------------------------------------------------- #
DISTURBANCE_DEFS = [
    {"key": "perspective", "label": "透视", "params": [
        {"key": "persp_angle", "label": "旋转角度(°)", "lo": -16, "hi": 16, "min": -180, "max": 180, "step": 1},
        {"key": "persp_strength", "label": "透视强度", "lo": 0.0, "hi": 0.22, "min": 0, "max": 1, "step": 0.01},
    ]},
    {"key": "noise", "label": "噪点", "params": [
        {"key": "noise_sigma", "label": "噪声强度σ", "lo": 3, "hi": 12, "min": 0, "max": 80, "step": 0.5},
        {"key": "noise_salt", "label": "椒盐比例", "lo": 0.0, "hi": 0.003, "min": 0, "max": 0.05, "step": 0.0005},
        {"key": "noise_salt_prob", "label": "椒盐触发概率", "lo": 0.4, "hi": 0.4, "min": 0, "max": 1, "step": 0.05},
    ]},
    {"key": "mottle", "label": "污渍", "params": [
        {"key": "mottle_count", "label": "斑点数", "lo": 2, "hi": 7, "min": 0, "max": 40, "step": 1},
        {"key": "mottle_size", "label": "斑点大小占比", "lo": 0.03, "hi": 0.08, "min": 0.005, "max": 0.5, "step": 0.005},
        {"key": "mottle_alpha", "label": "斑透明度", "lo": 20, "hi": 90, "min": 0, "max": 255, "step": 5},
    ]},
    {"key": "occlusion", "label": "遮挡", "params": [
        {"key": "occl_height", "label": "遮挡带高占比", "lo": 0.06, "hi": 0.16, "min": 0.01, "max": 1, "step": 0.01},
        {"key": "occl_alpha", "label": "遮挡透明度", "lo": 120, "hi": 200, "min": 0, "max": 255, "step": 5},
    ]},
    {"key": "blur", "label": "模糊", "params": [
        {"key": "blur_radius", "label": "模糊半径", "lo": 0.4, "hi": 1.5, "min": 0, "max": 10, "step": 0.1},
    ]},
    {"key": "motion_blur", "label": "运动模糊", "params": [
        {"key": "mb_kernel", "label": "拖影长度(px)", "lo": 4, "hi": 10, "min": 2, "max": 40, "step": 1},
    ]},
    {"key": "photon", "label": "光照", "params": [
        {"key": "photon_brightness", "label": "亮度", "lo": 0.75, "hi": 1.18, "min": 0.1, "max": 3, "step": 0.01},
        {"key": "photon_contrast", "label": "对比度", "lo": 0.85, "hi": 1.2, "min": 0.1, "max": 3, "step": 0.01},
        {"key": "photon_color", "label": "饱和度", "lo": 0.7, "hi": 1.25, "min": 0, "max": 3, "step": 0.01},
        {"key": "photon_fog", "label": "雾浓度", "lo": 0.08, "hi": 0.3, "min": 0, "max": 1, "step": 0.01},
        {"key": "photon_fog_prob", "label": "起雾概率", "lo": 0.35, "hi": 0.35, "min": 0, "max": 1, "step": 0.05},
    ]},
    {"key": "shadow", "label": "投影", "params": [
        {"key": "shadow_height", "label": "阴影高占比", "lo": 0.15, "hi": 0.35, "min": 0.02, "max": 1, "step": 0.01},
        {"key": "shadow_alpha", "label": "阴影浓度", "lo": 40, "hi": 120, "min": 0, "max": 255, "step": 5},
    ]},
]


def _pv(rng: random.Random, params: dict, key: str, lo: float, hi: float) -> float:
    """从 params[key]=[下限,上限] 取随机值；缺失/非法则用默认 [lo,hi]。"""
    v = params.get(key)
    if v and len(v) == 2:
        try:
            lo, hi = float(v[0]), float(v[1])
        except (TypeError, ValueError):
            pass
    if hi < lo:
        lo, hi = hi, lo
    return rng.uniform(lo, hi)


def _transform_plate(tile: Image.Image, canvas_w: int, canvas_h: int, rng: random.Random,
                     want_perspective: bool, params: dict | None = None) -> tuple[Image.Image, tuple]:
    """将车牌 tile 旋转/透视后贴到背景，返回 (合成后的透明层, 四角包围盒归一化)。

    bbox 采用四角最小/最大归一化坐标，保证覆盖变换后的车牌。用 OpenCV warpPerspective 实现透视，
    比 PIL QUAD 更稳定（不会出现全黑）。
    """
    import cv2

    w, h = tile.size
    params = params or {}
    cx = canvas_w * rng.uniform(0.32, 0.68)
    cy = canvas_h * rng.uniform(0.42, 0.66)
    # 透视开关同时控制旋转与透视：关闭时得到正对车牌的干净直牌
    angle = math.radians(_pv(rng, params, "persp_angle", -16, 16)) if want_perspective else 0.0

    # 未旋转四角（以中心为原点）：TL,TR,BR,BL
    corners = [(-w / 2, -h / 2), (w / 2, -h / 2), (w / 2, h / 2), (-w / 2, h / 2)]

    # 透视（梯形）：顶边收窄、底边加宽，形成近大远小
    strength = _pv(rng, params, "persp_strength", 0.0, 0.22) if want_perspective else 0.0
    scale_top = 1 - strength
    scale_bottom = 1 + strength
    y_shift = strength * h * 0.12
    scaled = []
    for (x, y) in corners:
        if y < 0:
            sx = x * scale_top
            yy = y + y_shift
        else:
            sx = x * scale_bottom
            yy = y - y_shift
        scaled.append((sx, yy))
    # 轻微随机抖动
    jitter = rng.uniform(0.0, 0.02) * w
    scaled = [(x + rng.uniform(-jitter, jitter), y + rng.uniform(-jitter, jitter))
              for x, y in scaled]

    # 旋转
    cos_a = math.cos(angle)
    sin_a = math.sin(angle)
    rot = []
    for x, y in scaled:
        rot.append((x * cos_a - y * sin_a + cx, x * sin_a + y * cos_a + cy))
    tl, tr, br, bl = rot

    # OpenCV 透视变换
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = np.float32([tl, tr, br, bl])
    m = cv2.getPerspectiveTransform(src, dst)
    rgb = np.asarray(tile.convert("RGB"))
    alpha = np.asarray(tile.split()[3])
    out_rgb = cv2.warpPerspective(rgb, m, (canvas_w, canvas_h), borderValue=(0, 0, 0))
    out_a = cv2.warpPerspective(alpha, m, (canvas_w, canvas_h), borderValue=0)
    transformed = np.dstack([out_rgb, out_a]).astype(np.uint8)
    transformed_img = Image.fromarray(transformed, "RGBA")

    xs = [tl[0], tr[0], br[0], bl[0]]
    ys = [tl[1], tr[1], br[1], bl[1]]
    bbox = (
        min(xs) / canvas_w, min(ys) / canvas_h,
        max(xs) / canvas_w, max(ys) / canvas_h,
    )
    return transformed_img, bbox


# --------------------------------------------------------------------------- #
# 扰动增强
# --------------------------------------------------------------------------- #
def _apply_noise(img: Image.Image, rng: random.Random, params: dict | None = None) -> Image.Image:
    params = params or {}
    arr = np.asarray(img).astype(np.float32)
    sigma = _pv(rng, params, "noise_sigma", 3, 12)
    arr = arr + np.random.normal(0, sigma, arr.shape)
    # 椒盐
    if rng.random() < _pv(rng, params, "noise_salt_prob", 0.4, 0.4):
        p = _pv(rng, params, "noise_salt", 0.0, 0.003)
        if p > 0:
            mask = np.random.random(arr.shape[:2])
            arr[mask < p] = 0
            arr[mask > 1 - p] = 255
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


def _apply_mottle(img: Image.Image, rng: random.Random, params: dict | None = None) -> Image.Image:
    """污渍 / 锈斑 / 反光。"""
    params = params or {}
    w, h = img.size
    cnt = int(_pv(rng, params, "mottle_count", 2, 7))
    size_ratio = _pv(rng, params, "mottle_size", 0.03, 0.08)
    alpha = int(_pv(rng, params, "mottle_alpha", 20, 90))
    colors = [(120, 90, 60), (90, 60, 50), (150, 130, 110), (220, 220, 210), (70, 70, 70)]
    for _ in range(max(0, cnt)):
        r = max(3, int(min(w, h) * size_ratio))
        x = rng.randint(-r, w)
        y = rng.randint(-r, h)
        overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        od = ImageDraw.Draw(overlay)
        od.ellipse([x, y, x + 2 * r, y + 2 * r], fill=rng.choice(colors) + (alpha,))
        img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    return img


def _apply_occlusion(img: Image.Image, rng: random.Random, params: dict | None = None) -> Image.Image:
    """遮挡带（模拟被护栏/雨刮等遮挡）。"""
    params = params or {}
    w, h = img.size
    hr = _pv(rng, params, "occl_height", 0.06, 0.16)
    band_h = max(2, int(h * hr))
    y0 = rng.randint(0, max(0, h - band_h))
    color = rng.choice([(40, 40, 45), (70, 70, 75), (110, 110, 115)])
    alpha = int(_pv(rng, params, "occl_alpha", 120, 200))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rectangle([0, y0, w, y0 + band_h], fill=color + (alpha,))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _apply_motion_blur(img: Image.Image, rng: random.Random, params: dict | None = None) -> Image.Image:
    params = params or {}
    k = max(2, int(_pv(rng, params, "mb_kernel", 4, 10)))
    arr = np.asarray(img).astype(np.float32)
    pad = k // 2
    padded = np.pad(arr, ((0, 0), (pad, pad), (0, 0)), mode="edge")
    # 水平滑动平均
    out = np.zeros_like(arr)
    for i in range(k):
        out += padded[:, i:i + arr.shape[1], :] * (1.0 / k)
    out = np.clip(out, 0, 255).astype(np.uint8)
    return Image.fromarray(out, "RGB")


def _apply_photon(img: Image.Image, rng: random.Random, params: dict | None = None) -> Image.Image:
    """亮度 / 对比度 / 饱和度 / 色调扰动 + 雨雾感。"""
    params = params or {}
    img = ImageEnhance.Brightness(img).enhance(_pv(rng, params, "photon_brightness", 0.75, 1.18))
    img = ImageEnhance.Contrast(img).enhance(_pv(rng, params, "photon_contrast", 0.85, 1.2))
    img = ImageEnhance.Color(img).enhance(_pv(rng, params, "photon_color", 0.7, 1.25))
    if rng.random() < _pv(rng, params, "photon_fog_prob", 0.35, 0.35):
        # 雾 / 泛白
        overlay = Image.new("RGB", img.size, (225, 228, 232))
        img = Image.blend(img, overlay, _pv(rng, params, "photon_fog", 0.08, 0.3))
    return img


def _apply_shadow(img: Image.Image, rng: random.Random, params: dict | None = None) -> Image.Image:
    params = params or {}
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    # 底部阴影渐变
    grad_h = max(2, int(h * _pv(rng, params, "shadow_height", 0.15, 0.35)))
    amax = int(_pv(rng, params, "shadow_alpha", 40, 120))
    for i in range(grad_h):
        alpha = int(amax * (1 - i / grad_h))
        od.line([(0, h - grad_h + i), (w, h - grad_h + i)], fill=(0, 0, 0, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


# --------------------------------------------------------------------------- #
# 主入口
# --------------------------------------------------------------------------- #
@dataclass
class PlateResult:
    image: Image.Image
    width: int
    height: int
    plate_type: str = "blue"
    label: str = "plate"
    text: str = ""
    bbox: dict = field(default_factory=dict)
    char_boxes: list = field(default_factory=list)


def render_license_plate(
    seed: int | None = None,
    canvas_w: int = 1280,
    canvas_h: int = 720,
    plate_type: str = "blue",
    text: str | None = None,
    disturbances: dict | None = None,
    params: dict | None = None,
) -> PlateResult:
    """渲染一张车牌合成图。

    disturbances：各扰动开关（noise/mottle/occlusion/blur/motion_blur/photon/perspective/shadow），布尔。
    params：各扰动参数区间 {参数名: [下限, 上限]}，键见 DISTURBANCE_DEFS；缺省用默认区间。
    """
    rng = random.Random(seed)
    spec = _PLATE_SPECS.get(plate_type, _PLATE_SPECS["blue"])
    if text is None:
        text = gen_text(spec, rng)

    d = disturbances or {}
    p = params or {}

    def want(k):
        return d.get(k, True)

    pad = 6
    # 按号牌规格的宽高比设板面尺寸（GA36-2018）；占比适当放大以保证字符清晰可辨
    plate_h = int(canvas_h * rng.uniform(0.18, 0.28))
    plate_w = int(plate_h * (spec.aw / spec.ah))

    # 画板面（不含旋转）
    tile = _plate_surface(spec, plate_w, plate_h, text)
    # 垫边，避免 QUAD 边缘裁切
    padded = Image.new("RGBA", (plate_w + pad * 2, plate_h + pad * 2), (0, 0, 0, 0))
    padded.paste(tile, (pad, pad))

    # 背景渐变
    # 背景：优先用真实车尾实拍图（backgrounds/），没有则合成
    bg = _load_scene_background(canvas_w, canvas_h, rng) or _make_background(canvas_w, canvas_h, rng)
    # 旋转 + 透视
    want_perspective = want("perspective")
    transformed, bbox = _transform_plate(padded, canvas_w, canvas_h, rng, want_perspective, p)
    # 仅粘贴非透明部分
    bg = Image.alpha_composite(bg.convert("RGBA"), transformed).convert("RGB")

    # 扰动（开关打开即生效；参数区间可在 params 里调）
    if want("blur"):
        bg = bg.filter(ImageFilter.GaussianBlur(radius=_pv(rng, p, "blur_radius", 0.4, 1.5)))
    if want("motion_blur"):
        bg = _apply_motion_blur(bg, rng, p)
    if want("photon"):
        bg = _apply_photon(bg, rng, p)
    if want("noise"):
        bg = _apply_noise(bg, rng, p)
    if want("mottle"):
        bg = _apply_mottle(bg, rng, p)
    if want("occlusion"):
        bg = _apply_occlusion(bg, rng, p)
    if want("shadow"):
        bg = _apply_shadow(bg, rng, p)

    bbox_dict = {"x1": bbox[0], "y1": bbox[1], "x2": bbox[2], "y2": bbox[3]}
    return PlateResult(
        image=bg,
        width=canvas_w,
        height=canvas_h,
        plate_type=spec.key,
        text=_full_text(spec, text),
        bbox=bbox_dict,
    )


# 真实场景背景图目录（用户可放入车尾实拍图；为空则回退到合成背景）
_BG_DIR = os.path.join(os.path.dirname(__file__), "backgrounds")


def _load_scene_background(canvas_w: int, canvas_h: int, rng: random.Random) -> Image.Image | None:
    """从 backgrounds/ 随机取一张真实场景图，等比缩放 + 居中裁剪到画布；无图返回 None。"""
    if not os.path.isdir(_BG_DIR):
        return None
    files = [f for f in os.listdir(_BG_DIR)
             if f.lower().endswith((".jpg", ".jpeg", ".png", ".bmp", ".webp"))]
    if not files:
        return None
    try:
        img = Image.open(os.path.join(_BG_DIR, rng.choice(files))).convert("RGB")
    except Exception:
        return None
    sw, sh = img.size
    s = max(canvas_w / sw, canvas_h / sh)
    img = img.resize((max(1, int(sw * s)), max(1, int(sh * s))), Image.LANCZOS)
    x = (img.width - canvas_w) // 2
    y = (img.height - canvas_h) // 2
    return img.crop((x, y, x + canvas_w, y + canvas_h))


def _make_background(canvas_w: int, canvas_h: int, rng: random.Random) -> Image.Image:
    """生成车尾背景：上为环境/天空、下为深色车身，整体平滑过渡 + 车漆反光 + 暗角。"""
    bg = Image.new("RGB", (canvas_w, canvas_h))
    draw = ImageDraw.Draw(bg)
    sky = rng.choice([(120, 130, 142), (108, 118, 133), (136, 128, 112), (100, 106, 118),
                      (128, 118, 104), (96, 112, 128)])
    body = (rng.randint(24, 38), rng.randint(26, 42), rng.randint(30, 50))
    body_top = int(canvas_h * rng.uniform(0.28, 0.40))
    trans = max(10, int(canvas_h * 0.16))  # 天空→车身柔和过渡带宽，避免硬边形成"黑线"
    for y in range(canvas_h):
        k = min(1.0, max(0.0, (y - (body_top - trans)) / (2 * trans)))
        c = tuple(int(sky[i] + (body[i] - sky[i]) * k) for i in range(3))
        draw.line([(0, y), (canvas_w, y)], fill=c)

    # 车漆反光横向亮条（很轻，模拟金属漆高光）
    for _ in range(rng.randint(2, 4)):
        yy = rng.randint(body_top, canvas_h - 1)
        shade = tuple(min(255, v + rng.randint(8, 20)) for v in body)
        draw.line([(0, yy), (canvas_w, yy)], fill=shade, width=max(1, canvas_h // 160))
    # 轻微暗角
    vig = Image.new("L", (canvas_w, canvas_h), 0)
    vd = ImageDraw.Draw(vig)
    vd.rectangle([0, 0, canvas_w, canvas_h], fill=16)
    vd.rectangle([int(canvas_w * 0.05), int(canvas_h * 0.05),
                  int(canvas_w * 0.95), int(canvas_h * 0.95)], fill=0)
    vig = vig.filter(ImageFilter.GaussianBlur(max(2, canvas_h // 8)))
    dark = Image.new("RGB", (canvas_w, canvas_h), (0, 0, 0))
    bg = Image.composite(dark, bg, vig)
    return bg


def to_png_bytes(result: PlateResult) -> bytes:
    buf = io.BytesIO()
    result.image.save(buf, format="PNG")
    return buf.getvalue()


PLATE_TYPE_OPTIONS = [
    {"key": k, "label": spec.label}
    for k, spec in _PLATE_SPECS.items()
]

PROVIDERS = [
    {
        "key": "license_plate",
        "label": "车牌合成",
        "description": "生成国内各类车牌（蓝/新能源/黄/双层/黑/教练/警用），带透视、旋转、噪点、污渍、遮挡、模糊等扰动，产出检测框+号牌标注",
        "task_type": "detection",
        "classes": ["plate"],
        "plate_types": PLATE_TYPE_OPTIONS,
        "disturbances": DISTURBANCE_DEFS,
    },
]
