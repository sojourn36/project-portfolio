"""站点地图 —— 给搜索引擎用的 sitemap.xml。

只收录「值得被索引」的页面：首页 + 全部项目详情页。
后台（``/admin/``）不收录，robots.txt 里也一并屏蔽。
"""

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from .models import Project


class StaticViewSitemap(Sitemap):
    """首页 —— 站点里唯一的非模型页面。"""

    priority = 1.0
    changefreq = 'weekly'

    def items(self):
        return ['showcase:home']

    def location(self, item):
        return reverse(item)


class ProjectSitemap(Sitemap):
    """项目详情页。

    ``lastmod`` 直接取项目自身的 ``updated_at``（``auto_now`` 维护），
    这样改了项目内容，搜索引擎能感知到更新。
    """

    priority = 0.8
    changefreq = 'monthly'

    def items(self):
        return Project.objects.all()

    def lastmod(self, obj):
        return obj.updated_at
