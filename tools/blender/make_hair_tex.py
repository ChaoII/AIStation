"""生成发丝贴图（透明底，灰度发丝，靠材质颜色染色）。

为什么用灰度：每个人发色不同，贴图只负责"形状+透明度"，颜色由材质的 baseColor 乘上去，
这样一张贴图能配 6 种发色，而且不会有色差。

产物：frontend/public/office/hair_strand.png（256×512）
"""

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter

OUT = os.path.join(
    r"C:\Users\aichao\.local\share\opencode\worktree\ce637a15bb0a57b0b07a4b910025d9e2c851dcf4\lively-ferret",
    "frontend", "public", "office", "hair_strand.png",
)

W, H = 256, 512
random.seed(7)


def strand(d, x0, y0, x1, y1, w_top, w_bot, shade, curve):
    """一根发丝：上粗下细，带一点 S 形弯曲。"""
    pts_l, pts_r = [], []
    steps = 24
    for i in range(steps + 1):
        t = i / steps
        x = x0 + (x1 - x0) * t + math.sin(t * math.pi * curve) * 10
        y = y0 + (y1 - y0) * t
        w = w_top + (w_bot - w_top) * t
        pts_l.append((x - w / 2, y))
        pts_r.append((x + w / 2, y))
    d.polygon(pts_l + pts_r[::-1], fill=(shade, shade, shade, 255))


def main():
    # 透明区填深灰：发片（用 alpha）看不出来，发帽（不用 alpha）看到的是发缝而不是纯黑
    im = Image.new("RGBA", (W, H), (152, 146, 142, 0))
    d = ImageDraw.Draw(im)

    # 主体：9 根粗一点的发束
    for i in range(5):
        x0 = 44 + i * (W - 88) / 3 + random.uniform(-8, 8)
        x1 = x0 + random.uniform(-16, 16)
        strand(d, x0, -10, x1, H + 10,
               random.uniform(38, 52), random.uniform(8, 16),
               random.randint(190, 255), random.uniform(-1.2, 1.2))

    # 细碎发丝，增加层次
    for i in range(5):
        x0 = random.uniform(6, W - 6)
        strand(d, x0, random.uniform(-20, 40), x0 + random.uniform(-20, 20), H + 10,
               random.uniform(5, 9), random.uniform(1, 3),
               random.randint(150, 235), random.uniform(-1.5, 1.5))

    # 顶部（发根）压暗一点，发尾稍微透
    px = im.load()
    for y in range(H):
        k = 1.0
        if y < H * 0.10:
            k = 0.72 + 0.28 * (y / (H * 0.10))
        if y > H * 0.86:
            k = 1.0 - 0.55 * ((y - H * 0.86) / (H * 0.14))
        for x in range(W):
            r, g, b, a = px[x, y]
            if a:
                px[x, y] = (int(r * k), int(g * k), int(b * k), a)

    # 稍微模糊一下边缘，避免硬锯齿
    im = im.filter(ImageFilter.GaussianBlur(0.6))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    im.save(OUT)
    print("[hair-tex]", OUT, im.size)


main()
