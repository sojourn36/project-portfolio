"""缩略图：路径约定 + 生成逻辑。

缩略图放在 ``MEDIA_ROOT/thumbs/<与原图同构的相对路径>``，只换扩展名
（``.jpg`` 或 ``.png``，由生成时按内容实测决定）。

为什么要有独立的一层
--------------------
详情页图集卡片在 CSS 里是 ``height: 200px`` 的小图，但 ``<img src>`` 原先直接
用 ``shot.image.url`` —— 也就是**拿原图当缩略图渲染**。线上实测代价：

    /project/yolov8-detection-desktop/      797 KB，其中 556 KB（70%）是一张
                                            用来渲染 200px 缩略图的原图
    /project/femnsic-fatigue-optimization/  823 KB，其中 770 KB 是 PNG

而真正需要全尺寸的只有「点击查看原图」那一个入口。所以拆开：
网格用缩略图，``<a href>`` 仍指向原图。

路径约定与生成逻辑放在同一个模块里，是为了让「生成端」和「读取端」不可能
对不上 —— 两边各写一遍拼接逻辑，迟早会分叉。同理，**命令行与后台共用
``build()``**：后台保存时顺手生成缩略图，就不存在「上传了图但忘了跑命令」
这种只在页面变重时才被发现的情况。

⚠️ 本模块被 ``models.py`` 在**模块级**导入，所以顶层只能依赖
``os`` / ``settings``。PIL 与 numpy 一律在函数内惰性导入 ——
否则每一条 ``manage.py`` 命令的启动都要为它付账。
"""

import os

from django.conf import settings

THUMB_PREFIX = 'thumbs/'

# 生成端只会产出这两种之一；读取端两种都找，找不到就回退原图。
THUMB_EXTS = ('.jpg', '.png')

# 默认宽度。这个数字是**量出来的，不是估的** —— 见 ``build`` 上方的说明。
DEFAULT_WIDTH = 800

# 质量下限。38 dB 对截图/图表来说通常肉眼无差；
# 达不到就退而选 PSNR 最高的方案（宁可大一点，也不糊）。
PSNR_FLOOR = 38.0


def thumb_relpath(image_name):
    """缩略图在 ``MEDIA_ROOT`` 下的相对路径（**不含扩展名**）。

    ``image_name`` 是 ``ImageField.name``，形如
    ``shots/yolov8-detection-desktop/01-desktop-gui.png``。
    """
    return THUMB_PREFIX + os.path.splitext(image_name)[0]


def find_thumb(image_name):
    """返回已存在的缩略图相对路径；不存在则返回空串。

    **找不到不算错误。** 刚克隆仓库、还没跑 ``make_thumbs``，或者原图换了
    但缩略图没重生成，都应当让页面照常显示（只是重一些），而不是裂图。
    所以调用方拿到空串时必须回退到原图 —— 这是刻意的 fail-open。
    """
    if not image_name:
        return ''
    base = thumb_relpath(image_name)
    for ext in THUMB_EXTS:
        rel = base + ext
        if os.path.isfile(os.path.join(settings.MEDIA_ROOT, rel)):
            return rel
    return ''


def thumb_url(image_name, fallback_url):
    """缩略图的对外地址；没有缩略图时返回 ``fallback_url``（原图地址）。"""
    rel = find_thumb(image_name)
    if not rel:
        return fallback_url
    return settings.MEDIA_URL + rel


# ---------------------------------------------------------------------------
# 生成
# ---------------------------------------------------------------------------

def _psnr(a, b):
    """峰值信噪比。用它而不是「看着还行」—— 肉眼在缩略图上分辨不出 38 与 42 dB。"""
    import numpy as np

    x = np.asarray(a.convert('RGB'), dtype=np.float64)
    y = np.asarray(b.convert('RGB'), dtype=np.float64)
    mse = ((x - y) ** 2).mean()
    return float('inf') if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def _encode(im, fmt, **kw):
    import io

    buf = io.BytesIO()
    im.save(buf, fmt, **kw)
    return buf.getvalue()


def _candidates(small, has_numpy):
    """返回 [(扩展名, 字节, 解码回来的图), ...]，供挑选。

    同一张图，PNG 调色板与 JPEG 谁更小**完全取决于内容**：

        · 科学图表 / 热力图（大面积平色）→ PNG 调色板常常又小又清晰
          实测热力图：PNG 256 色 68 KB / PSNR 41.9；JPEG q90 115 KB / 38.2
        · 桌面截图 / 照片（连续色调）→ JPEG 明显更小
          实测 GUI 截图：JPEG q85 38 KB / 39.7；PNG 256 色 58 KB / 38.1

    所以两种都生成、都算 PSNR，再挑 —— 不按 ``kind`` 字段硬编码规则，
    那只是把猜测换个地方放。
    """
    from PIL import Image

    out = []
    pal = small.quantize(256, Image.MEDIANCUT)
    out.append(('.png', _encode(pal, 'PNG', optimize=True), pal.convert('RGB')))
    for q in (90, 85, 80):
        data = _encode(small, 'JPEG', quality=q, optimize=True, subsampling=0)
        out.append(('.jpg', data, Image.open(_bytes_io(data))))
    return out


def _bytes_io(data):
    import io

    return io.BytesIO(data)


def _pick(small, has_numpy):
    """在 PSNR 达标的前提下挑最小的；全不达标则取 PSNR 最高的。"""
    scored = []
    for ext, data, back in _candidates(small, has_numpy):
        scored.append((ext, data, _psnr(small, back) if has_numpy else float('inf')))
    ok = [s for s in scored if s[2] >= PSNR_FLOOR]
    if ok:
        return min(ok, key=lambda s: len(s[1]))
    return max(scored, key=lambda s: s[2])


def renditions(image_name):
    """已存在的缩略图（两种扩展名都可能），返回相对 ``MEDIA_ROOT`` 的路径列表。"""
    base = thumb_relpath(image_name)
    return [base + e for e in THUMB_EXTS
            if os.path.isfile(os.path.join(settings.MEDIA_ROOT, base + e))]


def drop_renditions(image_name):
    for rel in renditions(image_name):
        os.remove(os.path.join(settings.MEDIA_ROOT, rel))


def _reusable(image_name, size_before, src_mtime, expect_w):
    """已存在的缩略图能不能直接复用。

    四个条件缺一不可，每个都对应一种真会发生的错误结果：

      · 恰好一份   —— 两份并存 = 上次换编码没清干净，得重生成顺带收掉
      · 比原图小   —— 不然复用的是个更肿的东西，还不如用原图
      · 不比源图旧 —— 源图换过就得重来
      · **宽度对得上** —— 这条最容易被漏掉：只看大小与时间的话，别人跑过一次
        ``--width 200`` 之后，那批 200px 的缩略图比源图小、又比源图新，
        就会被当成「已是最新」一路复用下去，仓库里悄悄留着 200px 的缩略图，
        而页面上明显发虚。宽度是唯一能直接验证「这份缩略图是照本次参数
        生成的」的凭据。
    """
    from PIL import Image

    existing = renditions(image_name)
    if len(existing) != 1:
        return False
    path = os.path.join(settings.MEDIA_ROOT, existing[0])
    if os.path.getsize(path) >= size_before:
        return False
    if os.path.getmtime(path) < src_mtime:
        return False
    try:
        with Image.open(path) as ex:
            return ex.width == expect_w
    except Exception:
        return False          # 打不开（截断 / 手工塞的文件）→ 重生成


# 宽度取多少：量出来的，不是估的
# ------------------------------
# ``docs/tools/measure_thumb_width.js`` 在 1440 / 1600 / 768 / 390 四种视口下
# 问浏览器要 ``getBoundingClientRect``，结论：
#
#   · 详情页图集卡片渲染 350–359 CSS px（``.shot-grid`` 是 3 列，
#     受 ``--maxw: 1140px`` 封顶），2× 屏即 700–718 设备像素
#   · 首页卡片封面渲染 347–352 CSS px，2× 即 694–704 设备像素
#   · 但 ``object-fit: cover`` 对**宽图是按高度放大的**：宽高比 1.86 的源图
#     要盖满 718×400 的框，实际需要 400 × 1.86 = 743px 宽
#
# 最初写的是 640，理由写着「卡片约 280–400px，640 够 2× 了」，直到真去量
# 才发现**每一张都在被放大 8–12%**。三档实测体量：640→492 KB / 720→577 KB /
# 800→673 KB（原图合计 2669 KB），取 800：唯一覆盖 743px 需求的一档。


def build(image_name, width=DEFAULT_WIDTH, force=False, dry_run=False):
    """为一源图生成缩略图（幂等）。

    返回 ``(状态, 原图字节, 缩略图字节)``，状态取值：

    ``'missing'``  源图不存在（库里有记录但文件没传上来是真实情况）
    ``'reused'``   已存在且仍然有效，未重做
    ``'kept'``     源图本身已经够小，生成反而更大 → 不生成，回退原图
    ``'made'``     新生成（或按 ``force`` 重写）

    ``dry_run=True`` 时判断与编码照常做，但**一个字节都不写** ——
    这样 ``--dry-run`` 报出来的数字就是真跑一遍会得到的数字，
    而不是另写一套估算逻辑（那套逻辑迟早和真实现分叉）。

    ``'kept'`` 这一支踩到过：``covers/gesture-hci-cover.jpg`` 源图 655×470 /
    48 KB，而 800 宽的「缩略图」反而 50 KB。宽度没超过目标、又早被压过一遍的
    源图，重压一次只会更肿 —— 这时什么都不生成，并把可能存在的旧缩略图删掉，
    让读取端真的回退到原图。
    """
    try:
        import numpy  # noqa: F401
        has_numpy = True
    except ImportError:
        has_numpy = False

    from PIL import Image

    src = os.path.join(settings.MEDIA_ROOT, image_name)
    if not os.path.isfile(src):
        return 'missing', 0, 0

    size_before = os.path.getsize(src)

    # 用 with 包住源图：PIL 的 open 是惰性的，句柄要显式释放，
    # 否则在 Windows 上会一直占着文件锁，直到 GC 才松手。
    with Image.open(src) as im:
        src_w, src_h = im.size
        expect_w = min(width, src_w)

        if not force and _reusable(image_name, size_before,
                                   os.path.getmtime(src), expect_w):
            rel = renditions(image_name)[0]
            return 'reused', size_before, os.path.getsize(
                os.path.join(settings.MEDIA_ROOT, rel))

        if src_w > width:
            h = max(1, round(src_h * width / src_w))
            small = im.convert('RGB').resize((width, h), Image.LANCZOS)
        else:
            small = im.convert('RGB')

    ext, data, _back = _pick(small, has_numpy)

    if len(data) >= size_before:
        if not dry_run:
            drop_renditions(image_name)
        return 'kept', size_before, size_before

    if dry_run:
        return 'made', size_before, len(data)

    dst = os.path.join(settings.MEDIA_ROOT, thumb_relpath(image_name) + ext)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'wb') as fh:
        fh.write(data)

    # 删掉换编码后残留的另一种扩展名。不删的话改宽度/换源图之后会同时留着
    # .jpg 和 .png 两份，仓库里多出一份没人引用的文件，而且 ``find_thumb``
    # 的优先级会让「哪份在生效」变得不明显。
    for rel in renditions(image_name):
        if not rel.endswith(ext):
            os.remove(os.path.join(settings.MEDIA_ROOT, rel))

    return 'made', size_before, len(data)
