"""模板上下文处理器 —— 为社交分享卡片提供**绝对**地址。

为什么必须绝对
--------------
``og:url`` / ``og:image`` 里放相对路径时，微信、飞书、LinkedIn、X 这些平台
抓不到图片，分享出去的卡片会退化成一条纯文字链接。所以这两个值必须由
服务端算出完整 URL。

这里刻意**不查数据库**：站点每个视图本来就取了 ``Profile``，处理器再查一次
只是白白多一次查询。分享文案的兜底交给模板里的 ``{% firstof %}``，
需要更精细文案的页面由视图直接传 ``og_title`` / ``og_description``。
"""

from django.conf import settings
from django.templatetags.static import static


def site_meta(request):
    """注入 ``site_url`` 与默认分享图 ``og_image_url``。

    ``site_url`` 优先取 ``settings.SITE_URL``（由 ``DJANGO_SITE_URL`` 环境变量
    注入）。部署在反向代理后面时**必须**显式配置 —— 否则
    ``request.build_absolute_uri`` 可能拿到内网地址或 http，
    分享出去的链接就会指向错误的地方。
    未配置时回退到当前请求，保证本地开发也不会出现 ``example.com`` 这种假域名。
    """
    site_url = (getattr(settings, 'SITE_URL', '') or '').rstrip('/')
    if not site_url:
        site_url = request.build_absolute_uri('/').rstrip('/')

    return {
        'site_url': site_url,
        # 分享图也拼在 site_url 上 —— 只让 og:url 换域名而 og:image 仍指向
        # 请求域名，是最容易漏的一种错配（代理后面就抓不到图了）。
        'og_image_url': site_url + static('og-cover.png'),
    }
