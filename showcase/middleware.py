"""给对外展示页面加上内容安全策略（CSP）。

起因：一个不请自来的脚本
------------------------
站点发布到托管平台后，网关会在 HTML 里**注入**一段腾讯 Beacon 埋点：

    <script src="https://beacon.cdn.qq.com/sdk/4.5.9/beacon_web.min.js"></script>
    <script>
    (function(){ try{ var beacon = new BeaconAction({appkey:'0WEB06U85YBSLJNL', ...});
      beacon.onDirectUserAction('preview_page_view', {
        'url': location.href, 'referrer': document.referrer, 'title': document.title }); ...
    </script>

它插在 ``<link rel="stylesheet" href="/static/css/style.css">`` 之后。这段代码不在
本仓库里 —— 模板和静态文件里 grep ``beacon`` 是零命中，本地 ``runserver`` 渲染
也没有它（本地 30134 字节，线上 30877 字节，差值就是这几行）。也就是说：
**只靠读代码永远发现不了它，必须拿线上真实响应去比对。**

它对隐私的实际影响：站点每个访问者都会向 ``beacon.cdn.qq.com`` 上报
当前 URL、来源页和标题。

为什么用 CSP，而不是「删掉那段代码」
------------------------------------
删不掉 —— 它不是我们的模板产出的，是网关在响应出站时加的。能拦住它的位置只有
浏览器侧，而浏览器侧拦第三方脚本的标准手段就是 CSP。

``script-src 'self'`` 恰好同时挡住这两段：
  * 外链那段是**跨域**（beacon.cdn.qq.com），不在 'self' 里；
  * 内联那段没有 nonce、也不在 'unsafe-inline' 里。
所以一条策略同时解决两个问题，不需要分别针对。

为什么这条策略敢上「严格版」
----------------------------
不含 'unsafe-inline' 的 CSP 只有在页面确实没有内联脚本时才可用，否则要么页面坏、
要么被迫退回 'unsafe-inline'（那就等于白设）。上线前对 sitemap 里的 7 个页面
外加 4 个分类筛选页、自定义 404、robots.txt 共 **13 个 URL** 逐页核查过：

    每页 <script> 标签数 = 1，且 src 为同源 /static/js/main.js
    内联 <script> = 0     <style> 块 = 0     style= 内联样式 = 0
    on*= 内联事件 = 0     javascript: URL = 0  eval / new Function = 0
    外域资源（img/script/link）= 0

模板源码层也复核过：``grep -rc "style="`` 四个模板全为 0，
``static/js/main.js`` 只用 classList / addEventListener，不做
``setAttribute('style', ...)``（那种写法会被 ``style-src`` 拦下，CSSOM 赋值不会）。
结论：严格策略在这个站上是可用的，不是摆设。

为什么不给 /admin/ 也加
-----------------------
两条理由，都尽量落到实测而不是推断：

  * **收益为零**：admin 只有站点主人访问，CSP 想保护的那种「访问者隐私」在这里不存在。
  * **风险没验完**：严格策略成立的前提是页面上既没有内联脚本、也没有内联样式。
    实测线上（Django 5.1.15）的 ``/admin/login/`` 确实只有两个同源外链脚本
    （theme.js / nav_sidebar.js），没有内联脚本 —— 但这**只覆盖了登录页一个页面**。
    后台的变更表单、内联编辑区、自动补全控件、filter 侧栏大量使用 ``style=``
    内联样式，``style-src 'self'`` 大概率会把它们打坏。逐页验证整个后台既费事
    又没收益，所以这一块保持豁免。

  （这条注释是改过的：最初的写法是「Django admin 自带内联脚本」，属于想当然 ——
   实测发现登录页并没有。结论没变，但理由换成了经得起查的那个。）

顺带一个实测发现：网关把 beacon **也**注入了 admin 页面 —— 线上 ``/admin/login/``
一共 4 个 ``<script>``，其中唯一那个内联的就是 beacon。admin 既然豁免，那里的
beacon 依旧会加载；它只在主人自己登录后台时触发，不涉及访问者，因此这次不动它。
"""

from django.conf import settings

# 顺序即输出顺序，保持「先兜底、再具体」的阅读顺序。
_DIRECTIVES = (
    # 兜底：没被下面显式提到的类型一律只允许同源
    ('default-src', "'self'"),
    # 唯一一个 <script> 是同源的 main.js；'self' 同时挡掉跨域外链脚本和内联脚本
    ('script-src', "'self'"),
    ('style-src', "'self'"),
    # 这里**刻意不写 data:** —— 逐页核查显示全站 0 处 data-URI 图片，
    # 留着它只是白送一条用不上的放行。要用再加，并且得同时改测试。
    ('img-src', "'self'"),
    ('font-src', "'self'"),
    # 演示视频，走 /media/ 同源
    ('media-src', "'self'"),
    ('connect-src', "'self'"),
    ('form-action', "'self'"),
    # base-uri 'none'：防止注入的 <base> 把页面里所有相对地址劫持到别的域。
    # 本站没有 <base>，直接禁掉最省事。
    ('base-uri', "'none'"),
    # object-src 'none'：<object>/<embed> 是已被淘汰的插件入口，本站零使用。
    ('object-src', "'none'"),
    # frame-ancestors 'none'：X-Frame-Options: DENY 的现代等价物。
    # 注意 X-Frame-Options 只在 DEBUG=False 时才会被设上（见 settings.py），
    # 而这条在开发环境也生效，顺带把「防被嵌套」补齐了。
    ('frame-ancestors', "'none'"),
)

# 这些前缀下的响应不加 CSP。admin 是唯一的例外，原因见模块文档。
EXEMPT_PREFIXES = ('/admin/',)

HEADER = 'Content-Security-Policy'


def build_policy(request=None):
    """拼出 CSP 头。``request`` 用于判断是否 https（决定要不要加升级指令）。"""
    directives = list(_DIRECTIVES)
    if request is not None and request.is_secure():
        # 只在 https 下加：本地 http 开发时加上它会把 http 子资源强行升级，
        # 反而制造出本地才有、线上没有的假故障。
        directives.append(('upgrade-insecure-requests', ''))
    return '; '.join(
        name if not value else '{} {}'.format(name, value)
        for name, value in directives
    )


class ContentSecurityPolicyMiddleware:
    """给非 admin 响应补上 CSP 头；视图已自行设过则不覆盖。"""

    def __init__(self, get_response):
        self.get_response = get_response
        self.exempt = tuple(getattr(settings, 'CSP_EXEMPT_PREFIXES',
                                    EXEMPT_PREFIXES))

    def __call__(self, request):
        response = self.get_response(request)

        if not getattr(settings, 'CSP_ENABLED', True):
            return response
        if request.path.startswith(self.exempt):
            return response
        # 不覆盖：留出「某个视图想要更严的策略」的余地（例如以后加 report-only）
        if HEADER not in response:
            response[HEADER] = build_policy(request)
        return response
