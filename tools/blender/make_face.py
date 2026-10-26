"""生成 6 张表情脸（同一套五官坐标，只有眉眼嘴不同）。

产物：frontend/public/office/face_{normal,talk,happy,think,busy,tired}.png
three.js 里按状态换贴图（说话时在 normal/talk 之间切），就是 v1 那套"有表情"的效果。
"""

import math
import os

from PIL import Image, ImageDraw

ROOT = r"C:\Users\aichao\.local\share\opencode\worktree\ce637a15bb0a57b0b07a4b910025d9e2c851dcf4\lively-ferret"
OUT_DIR = os.path.join(ROOT, "frontend", "public", "office")

W, H = 512, 640
LINE = (46, 34, 30, 255)
IRIS = (48, 34, 28, 255)
HILITE = (255, 255, 255, 255)
BLUSH = (236, 148, 138, 58)

EX, EY = 0.285, 0.385      # 眼睛中心（比例）
BW, BH = 63, 40            # 眼睛半径


def eye(d, cx, cy, w, h, mode="normal", flip=1):
    if mode == "happy":
        # 弯月眼（^ ^）：只画一条上弧 + 睫毛
        pts = []
        for t in range(0, 21):
            a = math.pi + t / 20 * math.pi
            pts.append((cx + math.cos(a) * w, cy + math.sin(a) * h * 0.9 + h * 0.55))
        d.line(pts, fill=LINE, width=int(max(6, h * 0.22)), joint="curve")
        return

    if mode == "half":
        # 半睁（困）：细长眼 + 小瞳
        d.ellipse([cx - w, cy - h * 0.45, cx + w, cy + h * 0.45], fill=(252, 248, 244, 255))
        d.ellipse([cx - w * 0.5, cy - h * 0.42, cx + w * 0.5, cy + h * 0.42], fill=IRIS)
        d.ellipse([cx - w * 0.3, cy - h * 0.3, cx - w * 0.02, cy - h * 0.02], fill=HILITE)
        d.line([(cx - w * 1.02, cy - h * 0.42), (cx + w * 1.02, cy - h * 0.42)],
               fill=LINE, width=int(max(5, h * 0.16)))
        return

    # normal / narrow / talk 都是杏眼，只有高度和眼线不同
    hh = h * (0.72 if mode == "narrow" else 1.0)
    d.ellipse([cx - w, cy - hh, cx + w, cy + hh], fill=(252, 248, 244, 255))
    d.ellipse([cx - w * 0.62, cy - hh * 0.92, cx + w * 0.62, cy + hh * 0.92], fill=IRIS)
    d.ellipse([cx - w * 0.34, cy - hh * 0.62, cx - w * 0.02, cy - hh * 0.22], fill=HILITE)
    d.ellipse([cx + w * 0.16, cy + hh * 0.34, cx + w * 0.4, cy + hh * 0.58], fill=(255, 255, 255, 170))
    pts = []
    for t in range(0, 21):
        a = math.pi + t / 20 * math.pi
        pts.append((cx + math.cos(a) * w * 1.02, cy + math.sin(a) * hh * 0.98 - math.sin(t / 20 * math.pi) * 2))
    d.line(pts, fill=LINE, width=int(max(5, hh * 0.16)), joint="curve")
    d.line([(cx + flip * w * 1.02, cy - 2), (cx + flip * w * 1.22, cy - hh * 0.30)],
           fill=LINE, width=int(max(4, hh * 0.12)))
    d.arc([cx - w * 0.9, cy - hh * 0.2, cx + w * 0.9, cy + hh * 1.25], 20, 160, fill=(120, 96, 86, 120), width=3)


def brow(d, cx, mode="normal"):
    y = H * 0.205
    tilt = {"normal": 0, "happy": -6, "think": -14, "busy": 10, "tired": 4, "talk": -2, "narrow": 6}[mode]
    pts = []
    for t in range(0, 15):
        a = math.pi + t / 14 * math.pi
        pts.append((cx + math.cos(a) * 72, y + math.sin(a) * 10 + tilt * (t / 14 - 0.5) * 1.2))
    d.line(pts, fill=(58, 42, 36, 235), width=7, joint="curve")


def mouth(d, mode="normal"):
    cx, cy = W * 0.5, H * 0.70
    if mode == "talk":
        d.ellipse([cx - 22, cy - 16, cx + 22, cy + 18], fill=(120, 60, 58, 245))
        d.ellipse([cx - 15, cy + 2, cx + 15, cy + 15], fill=(196, 96, 96, 255))
    elif mode == "happy":
        d.arc([cx - 46, cy - 30, cx + 46, cy + 34], 10, 170, fill=(150, 78, 72, 240), width=8)
    elif mode == "think":
        d.ellipse([cx - 11, cy - 9, cx + 11, cy + 11], fill=(140, 78, 74, 230))
    elif mode == "busy":
        d.line([(cx - 26, cy + 2), (cx + 26, cy + 2)], fill=(140, 78, 74, 235), width=6)
    elif mode == "tired":
        d.arc([cx - 30, cy - 6, cx + 30, cy + 22], 20, 160, fill=(150, 84, 78, 225), width=5)
    else:
        d.arc([cx - 34, cy - 18, cx + 34, cy + 18], 15, 165, fill=(150, 84, 78, 235), width=6)


def build(mood):
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    eye_mode = {"happy": "happy", "tired": "half", "busy": "narrow"}.get(mood, "normal")
    eye(d, W * EX, H * EY, BW, BH, eye_mode, -1)
    eye(d, W * (1 - EX), H * EY, BW, BH, eye_mode, 1)
    brow(d, W * EX, mood)
    brow(d, W * (1 - EX), mood)
    d.line([(W * 0.50 - 6, H * 0.615), (W * 0.50 + 4, H * 0.640)],
           fill=(176, 126, 100, 180), width=4)
    mouth(d, mood)
    bl = 80 if mood == "happy" else 58
    for cx in (W * 0.20, W * 0.80):
        d.ellipse([cx - 31, H * 0.49, cx + 31, H * 0.545], fill=(236, 148, 138, bl))
    path = os.path.join(OUT_DIR, "face_%s.png" % mood)
    im.save(path)
    print("[face]", mood, path)


os.makedirs(OUT_DIR, exist_ok=True)
for m in ("normal", "talk", "happy", "think", "busy", "tired"):
    build(m)

# 默认脸仍然叫 face.png（GLB 里内嵌的就是它，Blender 重新导出时用这张）
import shutil

shutil.copyfile(os.path.join(OUT_DIR, "face_normal.png"), os.path.join(OUT_DIR, "face.png"))
print("done")
