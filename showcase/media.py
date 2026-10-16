"""支持 HTTP Range 的媒体文件视图。

为什么不用 ``django.views.static.serve``
----------------------------------------
Django 3.2 的 ``FileResponse`` **完全没有 Range 支持** —— 它既不返回
``Accept-Ranges``，也不处理 ``Range`` 请求头（官方文档因此把
``django.views.static.serve`` 标注为「不适合生产环境」）。

对图片这类「一次性读完整文件」的资源没影响，但对 ``<video>`` 是硬伤：
浏览器无法按字节区间请求，**进度条拖不动**（拖动时只能从头重下，
或者干脆跳回起点）。实测线上：

    GET /static/css/style.css   Range: bytes=0-99  ->  206 + Content-Range   (WhiteNoise)
    GET /media/videos/x.mp4     Range: bytes=0-99  ->  200 + 全量 2333314B    (serve)

静态文件走 WhiteNoise，Range 正常；媒体走 ``serve``，Range 失效。

本模块按 RFC 7233 实现单段 Range：

* 合法区间          -> ``206`` + ``Content-Range: bytes s-e/size``
* 语法正确但越界    -> ``416`` + ``Content-Range: bytes */size``
* 无 Range / 语法错 -> ``200`` + 全量 + ``Accept-Ranges: bytes``

刻意不做的两件事（都是可选项，不做也符合规范）：

* **多段 Range**（``bytes=0-99,200-299``）—— 遇到时按 200 全量返回，
  这是规范允许的降级。实现 ``multipart/byteranges`` 的复杂度不值得。
* **``If-Range``** —— 少了它只是失去「断点续传时校验版本」的优化。
"""

import mimetypes
import os
import re

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponseNotModified
from django.utils.http import http_date, parse_http_date_safe

CHUNK_SIZE = 64 * 1024

#: ``bytes=start-end`` / ``bytes=start-`` / ``bytes=-suffix``
_RANGE_RE = re.compile(r'^bytes=(\d*)-(\d*)$')

#: 显式钉死我们实际会发的媒体类型。
#: 只靠 ``mimetypes`` 不保险：它依赖操作系统或容器里的 MIME 数据库，
#: 精简过的 Linux 镜像常常认不出 ``.mp4`` / ``.webm``，会退化成
#: ``application/octet-stream`` —— 那样浏览器不会内联播放，而是直接下载。
_EXPLICIT_TYPES = {
    '.mp4': 'video/mp4',
    '.webm': 'video/webm',
    '.m4v': 'video/mp4',
    '.mov': 'video/quicktime',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
    '.svg': 'image/svg+xml',
    '.pdf': 'application/pdf',
}


def _content_type(fullpath):
    ext = os.path.splitext(fullpath)[1].lower()
    if ext in _EXPLICIT_TYPES:
        return _EXPLICIT_TYPES[ext]
    guessed, _ = mimetypes.guess_type(fullpath)
    return guessed or 'application/octet-stream'


def _resolve(path):
    """把请求路径解析成 ``MEDIA_ROOT`` 下的真实文件路径。

    用 ``realpath`` 而非 ``normpath``：前者会把符号链接展开，
    因此既挡得住 ``../`` 穿越，也挡得住「软链指向根目录之外」这种更隐蔽的越权。
    """
    root = os.path.realpath(str(settings.MEDIA_ROOT))
    target = os.path.realpath(os.path.join(root, path))
    if target != root and not target.startswith(root + os.sep):
        raise Http404('请求路径超出媒体根目录')
    return target


def parse_range_header(header, size):
    """解析单段 Range，返回 ``(start, end)`` 闭区间。

    返回值语义：

    * ``(start, end)`` —— 合法区间
    * ``None``         —— 头不存在、语法不合法、或是多段 Range（调用方按 200 全量处理）
    * ``'invalid'``    —— 语法合法但区间越界（调用方应回 416）
    """
    if not header:
        return None
    m = _RANGE_RE.match(header.strip())
    if not m:
        return None                      # 多段 Range 或语法错误 -> 降级为全量
    raw_start, raw_end = m.group(1), m.group(2)
    if raw_start == '' and raw_end == '':
        return None                      # 'bytes=-' 不是合法区间

    if raw_start == '':
        # bytes=-N：最后 N 个字节。N 大于文件长度时取整个文件。
        suffix = int(raw_end)
        if suffix == 0:
            return 'invalid'
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(raw_start)
        end = int(raw_end) if raw_end else size - 1
        if end >= size:
            end = size - 1

    if size == 0 or start >= size or start > end:
        return 'invalid'
    return (start, end)


def _iter_file(fh, start, length):
    """从 ``start`` 起按块产出至多 ``length`` 字节，避免整文件读进内存。

    生成器带 ``finally: fh.close()`` 是刻意的：``StreamingHttpResponse``
    会把生成器的 ``close`` 登记进 ``_resource_closers``，响应结束时调用它。
    少了这个 ``finally``，一旦客户端中途断开（视频很常见），
    打开的文件句柄就要等垃圾回收才释放 —— 高并发下会累积成 fd 泄漏。
    """
    def gen():
        try:
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk
        finally:
            fh.close()
    return gen()


def serve_media(request, path):
    """替代 ``django.views.static.serve``，额外支持 Range 请求。"""
    # 开关判断放在视图里、而不是在 urls.py 里决定要不要注册路由：
    # 路由表在**模块导入时**就建好了，之后改 settings 不会生效 ——
    # 那既是个隐蔽的坑（测试里 override_settings 不起作用），
    # 也让这条路由永远无法被测试覆盖。
    if not (settings.DEBUG or getattr(settings, 'SERVE_MEDIA', False)):
        raise Http404('媒体文件服务未启用')

    fullpath = _resolve(path)
    if not os.path.isfile(fullpath):
        raise Http404('媒体文件不存在')

    stat = os.stat(fullpath)
    size = stat.st_size
    last_modified = stat.st_mtime
    content_type = _content_type(fullpath)

    # 条件请求：客户端已是最新就回 304，省掉整段传输。
    if_modified_since = parse_http_date_safe(
        request.META.get('HTTP_IF_MODIFIED_SINCE'))
    if if_modified_since is not None and int(last_modified) <= if_modified_since:
        response = HttpResponseNotModified()
        response['Last-Modified'] = http_date(last_modified)
        response['Accept-Ranges'] = 'bytes'
        return response

    rng = parse_range_header(request.META.get('HTTP_RANGE'), size)

    if rng == 'invalid':
        response = FileResponse(
            iter(()), status=416, content_type=content_type)
        response['Content-Range'] = 'bytes */{}'.format(size)
        response['Accept-Ranges'] = 'bytes'
        response['Content-Length'] = '0'
        return response

    if rng is None:
        fh = open(fullpath, 'rb')
        response = FileResponse(
            _iter_file(fh, 0, size), content_type=content_type)
        response['Content-Length'] = str(size)
    else:
        start, end = rng
        length = end - start + 1
        fh = open(fullpath, 'rb')
        response = FileResponse(
            _iter_file(fh, start, length), status=206, content_type=content_type)
        response['Content-Range'] = 'bytes {}-{}/{}'.format(start, end, size)
        response['Content-Length'] = str(length)

    # 这一行是整件事的关键：没有它，浏览器不会尝试按区间请求。
    response['Accept-Ranges'] = 'bytes'
    response['Last-Modified'] = http_date(last_modified)
    return response
