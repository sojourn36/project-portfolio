"""config 路由：后台 + 项目展示 + 开发期媒体文件服务。"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('showcase.urls')),
]

# 开发环境下由 Django 直接提供演示视频等媒体文件
# 静态文件（CSS/JS）由 django.contrib.staticfiles 在 runserver 时自动接管
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

admin.site.site_header = '作品集管理后台'
admin.site.site_title = '作品集管理'
admin.site.index_title = '内容管理'
