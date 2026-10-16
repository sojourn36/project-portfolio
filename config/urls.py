"""config 路由：后台 + 项目展示 + sitemap/robots + 媒体文件服务。"""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path, re_path
from django.views.generic import TemplateView

from showcase.media import serve_media
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

# 媒体文件（演示视频 / 实机截图）统一交给 showcase.media.serve_media。
#
# 两点说明：
#  1. 路由**总是**注册，是否真的对外提供由视图内的 settings.DEBUG /
#     settings.SERVE_MEDIA 决定。不在 urls.py 里判断，是因为路由表在模块
#     导入时就建好了 —— 之后改 settings 不生效，且这条路由会变成测不到的代码。
#  2. 开发与生产共用同一个视图。Django 自带的 django.views.static.serve
#     （以及 DEBUG 下的 static()）底层是 FileResponse，而 FileResponse
#     不支持 Range 请求 —— 结果是视频进度条拖不动。若开发用它、生产用别的，
#     就会出现「本地好好的、上线才发现拖不动」这种只在部署后暴露的差异。
urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', serve_media, name='serve-media'),
]

admin.site.site_header = '作品集管理后台'
admin.site.site_title = '作品集管理'
admin.site.index_title = '内容管理'

# 自定义 404（仅在 DEBUG=False 时生效）
handler404 = 'showcase.views.page_not_found'
