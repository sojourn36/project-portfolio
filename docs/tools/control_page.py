#!/usr/bin/env python3
"""control_page.py —— 给「页面体检脚本」做反向对照的**故意做坏**的页面。

为什么必须有它
--------------
一个「零缺陷」的报告，如果没验证过工具有抓取能力，**等于什么都没说**。
只有先拿一个确定有毛病的页面跑一遍、看它把毛病全抓出来、退出码为 1，
那份「全绿」的报告才算数。

四个页面，每个只测一件事
------------------------
| 路径 | CSP | 期望 |
|---|---|---|
| `/bad.html`       | 不设头               | 6 类缺陷全中，退出码 **1** |
| `/good.html`      | `script-src 'self'`  | 0 缺陷、0 被挡，退出码 **0** |
| `/blocked.html`   | `script-src 'none'`  | 同源被挡 → 真缺陷，退出码 **1** |
| `/crossonly.html` | `script-src 'self'`  | 跨域被挡 → **不计缺陷**，退出码 **0** |

后两个页面专门用来钉住体检脚本里**最容易做错的那个判定**：
「被策略挡下」到底算不算缺陷。跨域被挡是策略在正常工作，
同源被挡才是策略把自己的东西拦了。混为一谈的话，站点会永远判为失败。

⚠️ 夹具设计本身踩过的坑：最初把 `console.error(...)` 写在 `bad.html` 的**内联脚本**里，
而那个页面又设了 `script-src 'none'` —— 内联脚本被拦，`console.error` 压根没执行，
「控制台报错」这一类缺陷**从未被覆盖到**，可报告看起来一切正常。
**一个被自己拦掉的夹具，测不出它想测的东西。** 所以四件事拆成四页，互不干扰。

用法::

    python3 control_page.py 8899
    node audit_page.js --url http://127.0.0.1:8899/bad.html        # 期望 1
    node audit_page.js --url http://127.0.0.1:8899/good.html       # 期望 0
    node audit_page.js --url http://127.0.0.1:8899/blocked.html    # 期望 1
    node audit_page.js --url http://127.0.0.1:8899/crossonly.html  # 期望 0
"""

import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOCAL_JS = "/* 同源脚本，只为让 CSP 有东西可拦 */\nwindow.__control_ok = true;\n".encode('utf-8')

# 6 类缺陷：缺 alt / 裂图 / 横向溢出 / 空按钮 / console.error / HTTP>=400
BAD_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>对照页（故意做坏）</title>
<link rel="icon" href="data:,">
</head>
<body>
<h1>对照页</h1>

<!-- 缺陷 1：<img> 缺 alt -->
<img src="/pixel.png">

<!-- 缺陷 2：指向 404 的图（裂图） -->
<img src="/no-such-image.png" alt="裂掉的图">

<!-- 缺陷 3：2400px 宽，窄视口下横向溢出 -->
<div style="width:2400px;height:8px;background:#c00"></div>

<!-- 缺陷 4：空按钮，无文本也无 aria-label -->
<button></button>

<!-- 缺陷 5：控制台报错；缺陷 6：一次打到 404 的请求（HTTP>=400）
     这里**故意不设 CSP**：否则脚本被拦，console.error 根本不会执行，
     这一类缺陷就永远测不到（这个坑踩过一次，见模块文档）。 -->
<script>
  console.error('对照页故意制造的控制台错误');
  fetch('/no-such-api').catch(function () {});
</script>
</body></html>
""".encode('utf-8')

GOOD_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>对照页（干净）</title>
<link rel="icon" href="data:,">
</head>
<body>
<h1>干净对照页</h1>
<img src="/pixel.png" alt="一个占位像素">
<button type="button" aria-label="示例按钮">示例</button>
<script src="/local.js"></script>
</body></html>
""".encode('utf-8')

# 同源被挡（真缺陷）：script-src 'none' 连同源也挡
BLOCKED_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>对照页（同源被 CSP 挡）</title>
<link rel="icon" href="data:,">
</head>
<body>
<h1>同源脚本被 CSP 挡下</h1>
<script src="/local.js"></script>
<script>window.__inline_should_be_blocked = true;</script>
</body></html>
""".encode('utf-8')

# 跨域被挡（策略预期行为，不该算缺陷）：script-src 'self' 放行同源、挡跨域
CROSSONLY_HTML = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>对照页（跨域被 CSP 挡）</title>
<link rel="icon" href="data:,">
</head>
<body>
<h1>跨域脚本被 CSP 挡下</h1>
<script src="https://example.invalid/x.js"></script>
</body></html>
""".encode('utf-8')

# 1x1 透明 PNG
PIXEL = bytes.fromhex(
    '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4'
    '890000000a49444154789c6300010000050001'
    '0d0a2db40000000049454e44ae426082'
)

PAGES = {
    '/bad.html': (BAD_HTML, None),
    '/good.html': (GOOD_HTML, "script-src 'self'"),
    '/blocked.html': (BLOCKED_HTML, "script-src 'none'"),
    '/crossonly.html': (CROSSONLY_HTML, "script-src 'self'"),
}


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, ctype, csp=None):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        if csp:
            self.send_header('Content-Security-Policy', csp)
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split('?')[0]
        if path in PAGES:
            body, csp = PAGES[path]
            self._send(body, 'text/html; charset=utf-8', csp)
        elif path == '/local.js':
            self._send(LOCAL_JS, 'application/javascript')
        elif path == '/pixel.png':
            self._send(PIXEL, 'image/png')
        else:
            self.send_response(404)
            self.send_header('Content-Type', 'text/plain; charset=utf-8')
            self.send_header('Content-Length', '9')
            self.end_headers()
            self.wfile.write(b'not found')

    def log_message(self, *a):
        pass          # 静音，别把体检输出淹了


if __name__ == '__main__':
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print('对照页已启动:')
    print('   /bad.html        期望体检退出码 1（6 类缺陷）')
    print('   /good.html       期望体检退出码 0（干净）')
    print('   /blocked.html    期望体检退出码 1（同源被 CSP 挡 = 真缺陷）')
    print('   /crossonly.html  期望体检退出码 0（跨域被挡不计缺陷）')
    HTTPServer(('127.0.0.1', port), Handler).serve_forever()
