"""showcase 应用的冒烟测试。

覆盖：首页各区块渲染、分类筛选、详情页与演示视频、翻页、404、模型属性、
社交分享卡片（og:* / canonical）、robots.txt 与 sitemap.xml。
运行::

    python manage.py test showcase -v 2
"""

import io
import shutil
import tempfile

from PIL import Image as PILImage
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from .models import (
    Education, Pillar, Profile, ProfileFact, Project, ProjectShot, SkillGroup,
    Stat,
)


class SeedDataTestCase(TestCase):
    """统一用 seed_projects 导入真实数据，保证测试与线上数据一致。"""

    @classmethod
    def setUpTestData(cls):
        call_command('seed_projects', verbosity=0)

    # ---------- 数据完整性 ----------
    def test_seed_creates_all_blocks(self):
        self.assertEqual(Project.objects.count(), 6)
        self.assertEqual(Stat.objects.count(), 4)
        self.assertEqual(ProfileFact.objects.count(), 3)
        self.assertEqual(Pillar.objects.count(), 3)
        self.assertEqual(Education.objects.count(), 2)
        self.assertGreaterEqual(SkillGroup.objects.count(), 1)
        self.assertEqual(Profile.objects.count(), 1)

    def test_every_project_has_contributions_and_metrics(self):
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                self.assertTrue(project.contributions.exists())
                self.assertTrue(project.metrics.exists())
                self.assertTrue(project.techs.exists())
                self.assertIn(project.category, dict(Project.CATEGORY_CHOICES))

    # ---------- 模型属性 ----------
    def test_profile_about_paragraphs(self):
        profile = Profile.objects.first()
        self.assertEqual(len(profile.about_paragraphs), 3)

    def test_education_highlight_list_splits_cn_comma(self):
        edu = Education.objects.get(school='上海第二工业大学')
        self.assertIn('主动学习', edu.highlight_list)

    def test_skill_group_item_list_splits_mixed_separators(self):
        group = SkillGroup.objects.create(name='测试', items='A, B，C、D')
        self.assertEqual(group.item_list, ['A', 'B', 'C', 'D'])

    def test_project_category_key_and_demo_flags(self):
        renwu = Project.objects.get(slug='yolov8-detection-desktop')
        self.assertEqual(renwu.category_key, 'delivery')
        self.assertTrue(renwu.has_video)
        self.assertTrue(renwu.has_demo)

    def test_get_absolute_url(self):
        project = Project.objects.get(slug='gesture-hci')
        self.assertEqual(project.get_absolute_url(), '/project/gesture-hci/')

    # ---------- 首页 ----------
    def test_home_renders_all_sections(self):
        response = self.client.get(reverse('showcase:home'))
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        for anchor in ('id="about"', 'id="education"', 'id="projects"',
                       'id="awards"', 'id="skills"', 'id="contact"'):
            with self.subTest(anchor=anchor):
                self.assertIn(anchor, html)
        self.assert_no_template_syntax_leak(html)

    def assert_no_template_syntax_leak(self, html):
        """模板语法不得泄漏到输出。

        ``{#`` 也要查：Django 的花括号井号注释**只支持单行**，
        写成多行时它不会被当注释，而是原样输出到页面上 —— 这个坑很隐蔽。
        """
        for token in ('{%', '{{', '{#'):
            with self.subTest(token=token):
                self.assertNotIn(token, html)

    def test_home_lists_all_projects(self):
        response = self.client.get(reverse('showcase:home'))
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                self.assertContains(response, project.get_absolute_url())

    def test_home_category_filter(self):
        response = self.client.get(reverse('showcase:home'), {'category': 'materials'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['projects']), 2)
        self.assertEqual(response.context['active_category'], 'materials')

    def test_home_invalid_category_falls_back_to_all(self):
        response = self.client.get(reverse('showcase:home'), {'category': 'not-a-cat'})
        self.assertEqual(response.context['active_category'], '')
        self.assertEqual(len(response.context['projects']), 6)

    def test_home_filter_with_no_result_shows_hint(self):
        # 临时把 delivery 分类清空，验证空态提示
        Project.objects.filter(category=Project.CATEGORY_DELIVERY).delete()
        response = self.client.get(reverse('showcase:home'), {'category': 'delivery'})
        self.assertContains(response, '该分类下暂无项目')

    # ---------- 详情页 ----------
    def test_detail_pages_render(self):
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                response = self.client.get(project.get_absolute_url())
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, project.title)
                self.assert_no_template_syntax_leak(response.content.decode())

    def test_detail_embeds_video_for_renwujiance(self):
        response = self.client.get('/project/yolov8-detection-desktop/')
        html = response.content.decode()
        self.assertIn('<video', html)
        self.assertIn('renwujiance-demo.mp4', html)

    def test_detail_uses_placeholder_when_no_media(self):
        # 临时建一个没有任何演示素材的项目，验证占位提示
        Project.objects.create(
            title='占位测试项目', slug='placeholder-demo',
            category=Project.CATEGORY_DELIVERY, summary='用于测试空态占位。',
        )
        response = self.client.get('/project/placeholder-demo/')
        self.assertContains(response, 'video-placeholder')

    # ---------- 实机截图 / 结果图 ----------
    def test_seed_creates_shot_gallery(self):
        self.assertEqual(ProjectShot.objects.count(), 14)
        for slug in ('experimentpilot-ai', 'femnsic-fatigue-optimization',
                     'subway-risk-decision', 'student-behavior-profiling',
                     'yolov8-detection-desktop'):
            with self.subTest(project=slug):
                project = Project.objects.get(slug=slug)
                self.assertTrue(project.has_shots)
                for shot in project.shots.all():
                    self.assertTrue(shot.image.name.startswith('shots/%s/' % slug))

    def test_project_without_shots(self):
        # 手势交互只有视频、没有截图
        gesture = Project.objects.get(slug='gesture-hci')
        self.assertFalse(gesture.has_shots)
        self.assertTrue(gesture.has_video)

    def test_detail_renders_shot_gallery(self):
        response = self.client.get('/project/experimentpilot-ai/')
        html = response.content.decode()
        self.assertIn('shot-grid', html)
        self.assertIn('shots/experimentpilot-ai/01-structured-records.png', html)
        # 截图说明与类型标签都要渲染出来
        self.assertIn('结构化文献查询', html)
        self.assertIn('运行结果', html)

    def test_detail_hides_gallery_when_no_shots(self):
        response = self.client.get('/project/gesture-hci/')
        self.assertNotContains(response, 'shot-grid')

    def test_shot_ordering_and_str(self):
        project = Project.objects.get(slug='student-behavior-profiling')
        orders = list(project.shots.values_list('order', flat=True))
        self.assertEqual(orders, sorted(orders))
        first = project.shots.first()
        self.assertTrue(str(first))  # __str__ 回退到 caption / 文件名，不应报错

    # ---------- 列表卡片封面 ----------
    def test_cover_image_priority(self):
        """封面优先级：显式 cover_image → 第一张实机截图 → 演示动图 → 空串。"""
        # 1) 显式指定封面时用它
        gesture = Project.objects.get(slug='gesture-hci')
        self.assertTrue(gesture.cover_image)
        self.assertIn('covers/gesture-hci-cover.jpg', gesture.cover_image_url)
        # 2) 未指定封面时回落到第一张实机截图
        ep = Project.objects.get(slug='experimentpilot-ai')
        self.assertFalse(ep.cover_image)
        self.assertIn('shots/experimentpilot-ai/01-structured-records.png',
                      ep.cover_image_url)
        # 3) 都没有时返回空串，模板据此不渲染封面
        bare = Project.objects.create(
            title='无素材项目', slug='no-media-demo',
            category=Project.CATEGORY_DELIVERY, summary='测试封面兜底链。')
        self.assertEqual(bare.cover_image_url, '')

    def test_home_renders_card_covers(self):
        response = self.client.get('/')
        html = response.content.decode()
        # 6 个项目全部有封面（截图或显式封面图）
        self.assertEqual(html.count('class="card-cover"'), Project.objects.count())
        self.assertIn('covers/gesture-hci-cover.jpg', html)
        self.assertIn('covers/renwujiance-cover.jpg', html)
        # 封面右下角渲染分类角标（卡内重复的分类标签由 CSS 隐藏）
        self.assertIn('card-cover-tag', html)

    def test_detail_pager_links(self):
        response = self.client.get('/project/femnsic-fatigue-optimization/')
        self.assertEqual(response.context['prev_project'].slug, 'experimentpilot-ai')
        self.assertEqual(response.context['next_project'].slug, 'subway-risk-decision')

    def test_detail_related_same_category(self):
        response = self.client.get('/project/experimentpilot-ai/')
        related = list(response.context['related_projects'])
        self.assertEqual(len(related), 1)
        self.assertEqual(related[0].category, Project.CATEGORY_MATERIALS)

    def test_detail_unknown_slug_returns_404(self):
        self.assertEqual(self.client.get('/project/does-not-exist/').status_code, 404)

    @override_settings(DEBUG=False)
    def test_custom_404_page_when_debug_off(self):
        """DEBUG=False 时应渲染自定义 404 页（含站内导航与联系方式）。"""
        response = self.client.get('/project/does-not-exist/')
        self.assertEqual(response.status_code, 404)
        html = response.content.decode()
        self.assertIn('notfound-box', html)
        self.assertIn('这个页面不存在', html)
        # 四个回主入口的链接
        for anchor in ('#projects', '#about', '#contact'):
            self.assertIn('href="/%s"' % anchor, html)
        # 页头拿到 profile，不退化成占位文案
        self.assertIn('PROJECT PORTFOLIO', html)
        # 页脚邮箱来自 Profile，说明 profile 确实传进去了
        self.assertIn(Profile.objects.first().email, html)

    # ---------- 社交分享卡片 ----------
    def test_og_cover_asset_is_1200x630(self):
        """默认分享图必须存在且是 1200×630。

        base.html 在「没有覆盖 og_image」时写死了这两个数字，
        所以这里把写死的值跟真实素材绑在一起 —— 素材换了尺寸而模板没改，
        这个测试会先失败。
        """
        path = finders.find('og-cover.png')
        self.assertIsNotNone(path, 'static/og-cover.png 缺失，分享卡片会没有图')
        with PILImage.open(path) as im:
            self.assertEqual(im.size, (1200, 630))

    def test_home_share_card_meta(self):
        """首页分享卡片：绝对地址、默认图、1200×630、canonical。"""
        html = self.client.get('/').content.decode()
        name = Profile.objects.first().name
        self.assertIn('property="og:type" content="website"', html)
        self.assertIn('property="og:title" content="%s · 项目作品集"' % name, html)
        self.assertIn('property="og:site_name" content="%s · 项目作品集"' % name, html)
        self.assertIn('property="og:url" content="http://testserver/"', html)
        # 必须是绝对地址，否则微信 / 飞书抓不到图
        self.assertIn('property="og:image" content="http://testserver/static/og-cover.png"',
                      html)
        self.assertIn('property="og:image:width" content="1200"', html)
        self.assertIn('property="og:image:height" content="630"', html)
        self.assertIn('name="twitter:card" content="summary_large_image"', html)
        self.assertIn('<link rel="canonical" href="http://testserver/"', html)

    def test_home_share_card_uses_site_url_setting(self):
        """配置 DJANGO_SITE_URL 后，og:url / og:image 必须跟着换成正式域名。

        否则部署在反向代理后面时，分享出去的链接会指向内网地址。
        """
        with override_settings(SITE_URL='https://portfolio.example.com'):
            html = self.client.get('/').content.decode()
        self.assertIn('property="og:url" content="https://portfolio.example.com/"', html)
        self.assertIn(
            'property="og:image" content="https://portfolio.example.com/static/og-cover.png"',
            html)
        self.assertIn('<link rel="canonical" href="https://portfolio.example.com/"', html)

    def test_detail_share_card_uses_real_cover_size(self):
        """详情页分享图换成项目封面，宽高必须来自真实文件，不能沿用 1200×630。"""
        tmp = tempfile.mkdtemp()
        try:
            with override_settings(MEDIA_ROOT=tmp):
                buf = io.BytesIO()
                PILImage.new('RGB', (640, 360), (10, 20, 30)).save(buf, 'JPEG')
                project = Project.objects.get(slug='gesture-hci')
                project.cover_image.save(
                    'og-test.jpg',
                    SimpleUploadedFile('og-test.jpg', buf.getvalue(), 'image/jpeg'),
                    save=True)
                html = self.client.get(project.get_absolute_url()).content.decode()
                expected_url = 'http://testserver%s' % project.cover_image.url
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertIn('property="og:type" content="article"', html)
        self.assertIn('property="og:image" content="%s"' % expected_url, html)
        self.assertIn('property="og:image:width" content="640"', html)
        self.assertIn('property="og:image:height" content="360"', html)
        self.assertIn('property="og:image:alt" content="%s 封面图"' % project.title, html)

    def test_detail_share_card_falls_back_to_default_cover(self):
        """没有封面的项目：og:image 回落到默认分享图，尺寸回到 1200×630。"""
        Project.objects.create(
            title='无素材项目', slug='no-cover-demo',
            category=Project.CATEGORY_DELIVERY, summary='测试分享图兜底。')
        html = self.client.get('/project/no-cover-demo/').content.decode()
        self.assertIn('property="og:image" content="http://testserver/static/og-cover.png"',
                      html)
        self.assertIn('property="og:image:width" content="1200"', html)

    def test_cover_image_file_matches_url(self):
        """cover_image_file 与 cover_image_url 必须指向同一个文件。"""
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                f = project.cover_image_file
                self.assertEqual(project.cover_image_url, f.url if f else '')

    # ---------- 截断省略号 ----------
    def test_builtin_truncatechars_loses_ellipsis_in_chinese(self):
        """记录坑：中文下内置 truncatechars 不加省略号。

        这不是我们的代码有问题，是 Django 3.2 的截断尾巴走了本地化字符串，
        而 zh-hans / zh-hant 的译文是空串。写这个测试是为了让后来人一眼看到
        「为什么不用内置过滤器」，而不是把它当成可以随手换回去的实现细节。
        """
        from django.template.defaultfilters import truncatechars
        from django.utils import translation

        text = 'ExperimentPilot AI ｜ 本地科研 RAG 与冻结专家模型智能体'
        with translation.override('zh-hans'):
            self.assertEqual(truncatechars(text, 28), text[:28])
            self.assertNotIn('…', truncatechars(text, 28))
        with translation.override('en'):
            self.assertTrue(truncatechars(text, 28).endswith('…'))

    def test_ellipsis_filter_always_appends_ellipsis(self):
        """自定义 ellipsis 过滤器：中文环境下也必须有省略号，且总长不超过 N。"""
        from showcase.templatetags.showcase_extras import ellipsis

        text = 'ExperimentPilot AI ｜ 本地科研 RAG 与冻结专家模型智能体'
        with translation.override('zh-hans'):
            out = ellipsis(text, 28)
        self.assertTrue(out.endswith('…'))
        self.assertLessEqual(len(out), 28)
        # 没超长时原样返回，不画蛇添足
        self.assertEqual(ellipsis('短标题', 28), '短标题')
        # 参数非法时不炸
        self.assertEqual(ellipsis('abc', 'not-a-number'), 'abc')

    def test_truncated_titles_show_ellipsis_on_page(self):
        """页面上被截断的标题必须带省略号（面包屑 / 相关推荐 / 翻页）。"""
        def expect(text, n):
            # 与 Truncator.chars(n, '…') 一致：留出省略号的位置，去掉尾部空格
            return text[:n - 1].rstrip() + '…'

        project = Project.objects.get(slug='experimentpilot-ai')
        html = self.client.get(project.get_absolute_url()).content.decode()
        # 面包屑截到 28
        self.assertIn(expect(project.title, 28), html)
        # 翻页标题截到 30
        self.assertIn(expect(Project.objects.get(
            slug='femnsic-fatigue-optimization').title, 30), html)

    # ---------- robots.txt / sitemap.xml ----------
    def test_robots_txt(self):
        response = self.client.get('/robots.txt')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/plain'))
        body = response.content.decode()
        self.assertIn('User-agent: *', body)
        self.assertIn('Disallow: /admin/', body)
        self.assertIn('Sitemap: http://testserver/sitemap.xml', body)

    def test_sitemap_lists_home_and_all_projects(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        self.assertIn('<loc>http://testserver/</loc>', body)
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                self.assertIn('<loc>http://testserver%s</loc>' % project.get_absolute_url(),
                              body)
        # 后台不应被收录
        self.assertNotIn('/admin/', body)

    # ---------- 后台 ----------
    def test_admin_requires_login(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
