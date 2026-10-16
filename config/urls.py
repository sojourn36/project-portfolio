"""config 路由：后台 + 项目展示 + sitemap/robots + 开发期媒体文件服务。"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.generic import TemplateView

from showcase.sitemaps import ProjectSitemap, StaticViewSitemap

sitemaps = {
    'static': StaticViewSitemap,
    'projects': ProjectSitemap,
}

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('showcase.urls')),

    # 站点地图。Django 自带视图，URL 前缀为绝对地址（sitemap 协议要求），
    # 由 settings.SITE_URL / DJANGO_SITE_URL 决定；未配置时回退到请求域名。
    path('sitemap.xml', sitemap, {'sitemaps': sitemaps},
         name='django.contrib.sitemaps.views.sitemap'),

    # robots.txt。Django 没有内置视图，用纯文本模板渲染；
    # 模板里会通过上下文处理器拿到 site_url，拼出 Sitemap 的绝对地址。
    path('robots.txt',
         TemplateView.as_view(template_name='robots.txt', content_type='text/plain'),
         name='robots'),
]

# 开发环境下由 Django 直接提供演示视频等媒体文件
# 静态文件（CSS/JS）由 django.contrib.staticfiles 在 runserver 时自动接管
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = '作品集管理后台'
admin.site.site_title = '作品集管理'
admin.site.index_title = '内容管理'

# 自定义 404（仅在 DEBUG=False 时生效）
handler404 = 'showcase.views.page_not_found'
