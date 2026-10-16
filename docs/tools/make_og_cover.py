#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""生成社交分享大图 static/og-cover.png（1200×630，Open Graph 标准尺寸）。

为什么要脚本而不是直接放一张图
------------------------------
卡片上的姓名、定位、统计数字都会随 ``seed_projects.py`` 里的资料变化。
留一个可重跑的生成器，资料改了直接再跑一次，不用手工开设计软件。

用法
----
    python docs/tools/make_og_cover.py

依赖：Pillow（见 requirements.txt）。字体优先用系统自带的微软雅黑，
找不到会退到其他候选字体 / PIL 默认字体。

兼容性说明：本机 python38 环境是 Pillow 8.0.1，而
``ImageDraw.rounded_rectangle`` 到 Pillow 8.2 才提供 —— 所以这里自带一套
「两个矩形 + 四个圆」的圆角蒙版实现，描边用蒙版差集得到，新旧版本都能跑。
"""

from __future__ import annotations

import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---------------------------------------------------------------- 画布参数
W, H = 1200, 630
PAD = 72

BG = (255, 255, 255)
INK = (15, 23, 42)          # slate-900
MUTED = (100, 116, 139)     # slate-500
LINE = (226, 232, 240)      # slate-200
CARD_BG = (248, 250, 252)   # slate-50
BRAND_A = (37, 99, 235)     # #2563eb
BRAND_C = (13, 148, 136)    # #0d9488
BRAND_SKY = (56, 189, 248)  # #38bdf8

# ------------------------------------------------- 文案（与 seed_projects.py 对齐）
NAME = '王猛'
KICKER = 'PROJECT PORTFOLIO'
HEADLINE = '让 AI 落到真实产业场景里'
SUBTITLE = '求职方向 · FDE / AI 解决方案工程师'
STATS = [('6', '核心项目'), ('20-20', '评测通过'), ('0.804', 'R²')]
FOOTER = 'sojourn_wang@163.com · 上海'

FONT_CANDIDATES = {
    'bold': [
        ('C:/Windows/Fonts/msyhbd.ttc', 0),
        ('C:/Windows/Fonts/simhei.ttf', None),
        ('/System/Library/Fonts/PingFang.ttc', 1),
        ('/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc', 0),
    ],
    'regular': [
        ('C:/Windows/Fonts/msyh.ttc', 0),
        ('C:/Windows/Fonts/simsun.ttc', 0),
        ('/System/Library/Fonts/PingFang.ttc', 0),
        ('/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc', 0),
    ],
}


def load_font(kind, size):
    """按候选列表找第一个存在的字体；全都没有就退到 PIL 默认位图字体。"""
    for path, index in FONT_CANDIDATES[kind]:
        if os.path.exists(path):
            try:
                if index is None:
                    return ImageFont.truetype(path, size)
                return ImageFont.truetype(path, size, index=index)
            except OSError:
                continue
    return ImageFont.load_default()


def h_gradient(width, height, left, right):
    """横向线性渐变（用 2×1 小图拉伸，避免逐像素循环）。"""
    base = Image.new('RGB', (2, 1))
    base.putpixel((0, 0), left)
    base.putpixel((1, 0), right)
    return base.resize((width, height), Image.BILINEAR)


def rounded_mask(size, radius):
    """圆角矩形蒙版。

    Pillow < 8.2 没有 ``ImageDraw.rounded_rectangle``，用
    「中间十字矩形 + 四角圆」拼出同样的形状。
    """
    w, h = max(int(size[0]), 1), max(int(size[1]), 1)
    mask = Image.new('L', (w, h), 0)
    d = ImageDraw.Draw(mask)
    if hasattr(d, 'rounded_rectangle'):
        d.rounded_rectangle([0, 0, w - 1, h - 1], radius=radius, fill=255)
        return mask
    r = int(min(radius, w // 2, h // 2))
    if r <= 0:
        d.rectangle([0, 0, w - 1, h - 1], fill=255)
        return mask
    d.rectangle([r, 0, w - r - 1, h - 1], fill=255)
    d.rectangle([0, r, w - 1, h - r - 1], fill=255)
    for cx, cy in ((r, r), (w - r - 1, r), (r, h - r - 1), (w - r - 1, h - r - 1)):
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=255)
    return mask


def rounded_box(img, box, radius, fill=None, outline=None, width=1):
    """在 img 上画圆角矩形。实心与描边都用蒙版贴图实现，不依赖新 API。"""
    x0, y0, x1, y1 = [int(round(v)) for v in box]
    w, h = max(x1 - x0, 1), max(y1 - y0, 1)
    if fill is not None:
        img.paste(Image.new('RGB', (w, h), fill), (x0, y0), rounded_mask((w, h), radius))
    if outline is not None and width > 0:
        outer = rounded_mask((w, h), radius)
        iw, ih = max(w - width * 2, 1), max(h - width * 2, 1)
        inner = rounded_mask((iw, ih), max(radius - width, 0))
        ring = Image.new('L', (w, h), 0)
        ring.paste(inner, (width, width))
        ring = ImageChops.subtract(outer, ring)
        img.paste(Image.new('RGB', (w, h), outline), (x0, y0), ring)


def draw_kicker(draw, xy, text, font, fill, tracking=3):
    """带字距的小标题（PIL 没有 letter-spacing，手动逐字推进）。"""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += draw.textlength(ch, font=font) + tracking
    return x


def add_glow(base, center, radius, color, opacity, blur=None):
    """以 ``center`` 为中心，在 base 上叠一团柔和的径向光晕。

    两个坑，都踩过：

    1. 蒙版层必须比光晕本体大一圈（``pad``）。如果椭圆半径等于图层半径，
       高斯模糊还没衰减到 0 就被图层边界切断 —— 画面上会出现一条笔直的
       硬边，看起来像一个半透明矩形而不是光晕。
    2. 蒙版要显式取 ``getchannel('A')``，不要把 RGBA 图直接当蒙版传：
       Pillow 会把非 L/1 模式的蒙版按亮度解释。
    """
    blur = blur if blur is not None else radius * 0.45
    pad = int(blur * 2.4)
    side = int(radius * 2 + pad * 2)
    layer = Image.new('RGBA', (side, side), color + (0,))
    d = ImageDraw.Draw(layer)
    c = side / 2.0
    d.ellipse([c - radius, c - radius, c + radius, c + radius],
              fill=color + (opacity,))
    layer = layer.filter(ImageFilter.GaussianBlur(blur))
    base.paste(layer.convert('RGB'),
               (int(center[0] - c), int(center[1] - c)),
               layer.getchannel('A'))


def main():
    out = os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), '..', '..', 'static', 'og-cover.png'))

    canvas = Image.new('RGB', (W, H), BG)

    # ---- 背景装饰光晕 ----
    add_glow(canvas, (W - 120, -60), 380, BRAND_SKY, 62)
    add_glow(canvas, (40, H - 30), 420, BRAND_A, 42)

    # ---- 顶部品牌渐变条 ----
    canvas.paste(h_gradient(W, 8, BRAND_A, BRAND_C), (0, 0))

    # ---- 品牌标记：圆角方块 + 姓名首字 ----
    mark = 84
    canvas.paste(h_gradient(mark, mark, BRAND_A, BRAND_C),
                 (PAD, 60), rounded_mask((mark, mark), 22))

    draw = ImageDraw.Draw(canvas)
    f_mark = load_font('bold', 46)
    ch = NAME[0]
    tw = draw.textlength(ch, font=f_mark)
    bbox = f_mark.getbbox(ch)
    draw.text((PAD + mark / 2 - tw / 2,
               60 + mark / 2 - (bbox[1] + bbox[3]) / 2),
              ch, font=f_mark, fill=(255, 255, 255))

    # ---- 姓名 + 小标题 ----
    draw.text((PAD + mark + 26, 66), NAME, font=load_font('bold', 46), fill=INK)
    draw_kicker(draw, (PAD + mark + 30, 124), KICKER,
                load_font('regular', 17), MUTED, tracking=3.2)

    # ---- 主标题 / 副标题 ----
    draw.text((PAD, 214), HEADLINE, font=load_font('bold', 60), fill=INK)
    draw.text((PAD, 306), SUBTITLE, font=load_font('regular', 26), fill=MUTED)

    # ---- 统计卡片 ----
    card_h, gap = 112, 22
    card_w = (W - PAD * 2 - gap * (len(STATS) - 1)) // len(STATS)
    top = 382
    for i, (value, label) in enumerate(STATS):
        x = PAD + i * (card_w + gap)
        rounded_box(canvas, [x, top, x + card_w, top + card_h], 16,
                    fill=CARD_BG, outline=LINE, width=1)

    # 贴图会改动画布，这里重新取一次 draw 更稳妥
    draw = ImageDraw.Draw(canvas)
    f_num, f_lab = load_font('bold', 40), load_font('regular', 20)
    for i, (value, label) in enumerate(STATS):
        x = PAD + i * (card_w + gap)
        draw.text((x + 28, top + 22), value, font=f_num, fill=BRAND_A)
        draw.text((x + 28, top + 72), label, font=f_lab, fill=MUTED)

    # ---- 页脚 ----
    draw.text((PAD, 546), FOOTER, font=load_font('regular', 21), fill=MUTED)

    os.makedirs(os.path.dirname(out), exist_ok=True)
    canvas.save(out, 'PNG', optimize=True)
    print('[OK] {} ({}×{}, {:.1f} KB)'.format(
        out, W, H, os.path.getsize(out) / 1024))
    return 0


if __name__ == '__main__':
    sys.exit(main())
