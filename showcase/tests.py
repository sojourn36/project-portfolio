"""showcase 应用的冒烟测试。

覆盖：首页各区块渲染、分类筛选、详情页与演示视频、翻页、404、模型属性、
社交分享卡片（og:* / canonical）、robots.txt 与 sitemap.xml。
运行::

    python manage.py test showcase -v 2
"""

import io
import os
import shutil
import tempfile
import unittest

import django
from PIL import Image as PILImage
from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.http import HttpResponse
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import translation

from .models import (
    Education, Pillar, Profile, ProfileFact, Project, ProjectLink, ProjectShot,
    SkillGroup, Stat,
)


def _url_stem(url):
    """把 ``/media/thumbs/shots/x/01-y.png`` 归一成 ``shots/x/01-y``。

    依次去掉 ``/media/`` 前缀、``thumbs/`` 这一层、以及扩展名 ——
    用来判断「卡片缩略图」与「原图」是不是同一张图（rendition 不同、来源相同）。
    """
    rel = url.split('/media/', 1)[-1]
    if rel.startswith('thumbs/'):
        rel = rel[len('thumbs/'):]
    return os.path.splitext(rel)[0]


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

    def test_detail_hero_shows_demo_link(self):
        """在线演示入口要出现在**头部**（.hero-cta），不能只沉在页尾。

        为什么单独钉住位置：详情页很长（视频 + 指标 + 图集），「相关链接」区块
        在最下面。把这条链接的 kind 从 demo 改掉、或者模板里的 hero-cta 被误删，
        页面看起来都还正常 —— 只是那个按钮没人看得到。
        """
        project = Project.objects.get(slug='experimentpilot-ai')
        response = self.client.get(project.get_absolute_url())
        html = response.content.decode()
        self.assertIn('hero-cta', html)
        self.assertIn('cta-btn', html)
        self.assertIn(project.demo_links[0].url, html)

    def test_demo_links_excludes_entries_without_url(self):
        """只有文字、没有地址的「相关链接」条目不该变成按钮。

        同一个项目里既有 kind=demo 的在线演示，也有「冻结编号 …」这类纯陈述，
        后者渲染成按钮会让人以为点得动。
        """
        project = Project.objects.get(slug='experimentpilot-ai')
        demo = project.demo_links
        self.assertEqual(len(demo), 1)
        self.assertEqual(demo[0].kind, ProjectLink.KIND_DEMO)
        self.assertTrue(demo[0].url)
        self.assertFalse([link for link in demo if not link.url])
        # 纯陈述条目仍然在「相关链接」里，只是不进入 demo_links
        self.assertGreaterEqual(project.links.count(), 2)

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
        self.assertEqual(ProjectShot.objects.count(), 15)
        for slug in ('experimentpilot-ai', 'femnsic-fatigue-optimization',
                     'subway-risk-decision', 'student-behavior-profiling',
                     'yolov8-detection-desktop'):
            with self.subTest(project=slug):
                project = Project.objects.get(slug=slug)
                self.assertTrue(project.has_shots)
                for shot in project.shots.all():
                    self.assertTrue(shot.image.name.startswith('shots/%s/' % slug))
        # Qt 端那张单独标成「桌面端界面」，与同一个项目里的 Streamlit 界面区分开 ——
        # 类型标签是读者判断「这是哪个端」的唯一线索，退回 'ui' 就看不出来了。
        qt = ProjectShot.objects.get(
            image='shots/student-behavior-profiling/05-qt-realtime-analysis.png')
        self.assertEqual(qt.kind, ProjectShot.KIND_GUI)

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
        """封面优先级：显式 cover_image → 第一张实机截图 → 演示动图 → 空串。

        注意断言里**不带扩展名**：卡片取的是 ``thumbs/`` 下的缩略图，而缩略图的
        扩展名由生成时按内容实测决定（图表选 PNG、截图选 JPEG），
        写死 ``.png`` 就等于把那个决策钉死，反而测错了东西。
        """
        # 1) 显式指定封面时用它
        gesture = Project.objects.get(slug='gesture-hci')
        self.assertTrue(gesture.cover_image)
        self.assertIn('covers/gesture-hci-cover', gesture.cover_image_url)
        # 2) 未指定封面时回落到第一张实机截图
        ep = Project.objects.get(slug='experimentpilot-ai')
        self.assertFalse(ep.cover_image)
        self.assertIn('experimentpilot-ai/01-structured-records',
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

    def test_cover_url_is_a_smaller_rendition_of_the_same_picture(self):
        """``cover_image_file``（原图，给 og:image）与 ``cover_image_url``（卡片缩略图）
        必须指向**同一张图**，但允许是不同 rendition。

        这条断言原来写的是「两个 URL 完全相同」。加了缩略图之后那不再成立 ——
        卡片用的是 ``thumbs/`` 下的缩小版。与其放宽，不如把它换成更强的不变量：

          ① 同一张源图（去掉 ``thumbs/`` 前缀与扩展名后，路径主体必须一致）
          ② 两者都指向 ``MEDIA_ROOT`` 下真实存在的文件
          ③ **若**有缩略图，它必须确实更小（否则这层缩略图就是白加的）

        ③ 特意写成条件式的：没有缩略图、直接用原图，是一条**设计内的合法路径**
        （``make_thumbs`` 对「源图已足够小、重压反而更大」的图就不生成缩略图，
        实测 ``covers/gesture-hci-cover.jpg``：源图 48 KB，800 宽的缩略图 50 KB）。
        把「必须更小」写死会把这条例外判成失败，而它恰恰是省流量的正确做法。

        写死 URL 相等则会让「缩略图生效」本身变成失败 —— 那种测试只会被删掉。
        """
        for project in Project.objects.all():
            with self.subTest(project=project.slug):
                f = project.cover_image_file
                if not f:
                    self.assertEqual(project.cover_image_url, '')
                    continue

                url = project.cover_image_url
                # ① 同一张图：URL 去掉前缀与扩展名后必须一致
                self.assertEqual(_url_stem(url), _url_stem(f.url),
                                 '卡片缩略图与原图不是同一张图')

                # ② 都真实存在
                thumb_rel = url[len(settings.MEDIA_URL):]
                orig_rel = f.url[len(settings.MEDIA_URL):]
                thumb_path = os.path.join(settings.MEDIA_ROOT, thumb_rel)
                orig_path = os.path.join(settings.MEDIA_ROOT, orig_rel)
                self.assertTrue(os.path.isfile(thumb_path), '卡片图不存在: %s' % thumb_rel)
                self.assertTrue(os.path.isfile(orig_path), '原图文件不存在: %s' % orig_rel)

                # ③ 有缩略图时必须更小；用原图时两者本就是同一个文件，跳过
                if thumb_rel.startswith('thumbs/'):
                    self.assertLess(os.path.getsize(thumb_path),
                                    os.path.getsize(orig_path),
                                    '缩略图并不比原图小: %s' % thumb_rel)
                else:
                    self.assertEqual(thumb_rel, orig_rel,
                                     '既不在 thumbs/ 下，又不是原图，说不清是什么')

    # ---------- 截断省略号 ----------
    @unittest.skipUnless(django.VERSION[:2] == (3, 2),
                         '记录的是 Django 3.2 的具体行为，换版本请重新评估')
    def test_builtin_truncatechars_loses_ellipsis_in_chinese(self):
        """记录坑：Django 3.2 + 中文环境下，内置 truncatechars 不加省略号。

        这不是我们的代码有问题，是截断尾巴走了本地化字符串
        （pgettext('String to return when truncating text', '%(truncated_text)s…')），
        而 zh-hans / zh-hant 的译文是空串。

        写这个测试是为了让后来人一眼看到「为什么不用内置过滤器」，
        而不是把它当成可以随手换回去的实现细节。
        升级 Django 后这个测试会自动跳过 —— 那时请重新确认一次。
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


@override_settings(SERVE_MEDIA=True)
class MediaRangeTestCase(TestCase):
    """媒体文件的 Range 支持 —— 视频进度条能不能拖，全看这个。

    背景：Django 3.2 的 FileResponse **完全不支持 Range**，
    django.views.static.serve 只是它的薄包装。实测线上
    ``GET /media/videos/x.mp4  Range: bytes=0-99`` 返回 ``200`` + 全量 2333314B，
    而同样条件下静态文件（WhiteNoise 托管）返回 ``206`` + ``Content-Range``。
    本组测试锁死 showcase.media.serve_media 的行为。
    """

    PAYLOAD = bytes(range(256)) * 4          # 1024 字节，逐字节可校验

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp()
        cls.override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.override.enable()
        os.makedirs(os.path.join(cls.media_root, 'videos'))
        cls.video_rel = 'videos/demo.mp4'
        with open(os.path.join(cls.media_root, cls.video_rel), 'wb') as fh:
            fh.write(cls.PAYLOAD)

    @classmethod
    def tearDownClass(cls):
        cls.override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def _get(self, rel=None, **extra):
        return self.client.get('/media/' + (rel or self.video_rel), **extra)

    @staticmethod
    def _body(response):
        """取出流式响应体，并缓存 —— 流式响应只能消费一次。

        不缓存的话，同一个 response 断言两次时第二次会读到空
        （生成器已耗尽），表现为莫名其妙的 ``b'' != b'...'``。
        踩过一次，所以把幂等性做进辅助函数里，而不是靠调用方自觉。
        """
        if not hasattr(response, '_cached_body'):
            response._cached_body = b''.join(response.streaming_content)
        return response._cached_body

    # ---------- 完整请求 ----------
    def test_full_get_returns_200_and_advertises_accept_ranges(self):
        response = self._get()
        self.assertEqual(response.status_code, 200)
        # 这一行是整件事的关键：没有 Accept-Ranges，浏览器不会尝试区间请求
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(response['Content-Length'], str(len(self.PAYLOAD)))
        self.assertNotIn('Content-Range', response)
        self.assertEqual(self._body(response), self.PAYLOAD)

    def test_content_type_is_pinned_for_mp4(self):
        """不能退化成 application/octet-stream —— 那样浏览器会下载而不是内联播放。

        只靠 mimetypes 不保险：它依赖操作系统的 MIME 数据库，
        精简过的 Linux 容器常认不出 .mp4。
        """
        self.assertEqual(self._get()['Content-Type'], 'video/mp4')

    def test_head_request_does_not_need_range_support(self):
        response = self.client.head('/media/' + self.video_rel)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Length'], str(len(self.PAYLOAD)))

    # ---------- 区间请求 ----------
    def test_range_first_bytes_returns_206(self):
        response = self._get(HTTP_RANGE='bytes=0-99')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 0-99/1024')
        self.assertEqual(response['Content-Length'], '100')
        self.assertEqual(response['Accept-Ranges'], 'bytes')
        self.assertEqual(self._body(response), self.PAYLOAD[:100])

    def test_range_middle_returns_exact_slice(self):
        response = self._get(HTTP_RANGE='bytes=500-599')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 500-599/1024')
        self.assertEqual(self._body(response), self.PAYLOAD[500:600])

    def test_open_ended_range_runs_to_end_of_file(self):
        response = self._get(HTTP_RANGE='bytes=1000-')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 1000-1023/1024')
        self.assertEqual(self._body(response), self.PAYLOAD[1000:])

    def test_suffix_range_returns_last_n_bytes(self):
        """``bytes=-N`` 取末尾 N 字节 —— 播放器读 moov atom 时常这么请求。"""
        response = self._get(HTTP_RANGE='bytes=-100')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 924-1023/1024')
        self.assertEqual(self._body(response), self.PAYLOAD[-100:])

    def test_suffix_range_larger_than_file_clamps_to_whole_file(self):
        response = self._get(HTTP_RANGE='bytes=-99999')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 0-1023/1024')
        self.assertEqual(self._body(response), self.PAYLOAD)

    def test_range_end_beyond_size_is_clamped(self):
        response = self._get(HTTP_RANGE='bytes=0-99999')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(response['Content-Range'], 'bytes 0-1023/1024')

    def test_single_byte_range(self):
        response = self._get(HTTP_RANGE='bytes=7-7')
        self.assertEqual(response.status_code, 206)
        self.assertEqual(self._body(response), self.PAYLOAD[7:8])

    # ---------- 越界与降级 ----------
    def test_unsatisfiable_range_returns_416(self):
        response = self._get(HTTP_RANGE='bytes=1024-')
        self.assertEqual(response.status_code, 416)
        self.assertEqual(response['Content-Range'], 'bytes */1024')
        self.assertEqual(self._body(response), b'')

    def test_reversed_range_returns_416(self):
        response = self._get(HTTP_RANGE='bytes=500-100')
        self.assertEqual(response.status_code, 416)

    def test_zero_suffix_range_returns_416(self):
        response = self._get(HTTP_RANGE='bytes=-0')
        self.assertEqual(response.status_code, 416)

    def test_multi_range_degrades_to_full_body(self):
        """多段 Range 按 200 全量返回 —— 规范允许的降级，不做 multipart/byteranges。"""
        response = self._get(HTTP_RANGE='bytes=0-9,20-29')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self._body(response), self.PAYLOAD)

    def test_malformed_range_degrades_to_full_body(self):
        for header in ('bytes=abc', 'items=0-10', 'bytes=', 'bytes=-'):
            with self.subTest(header=header):
                response = self._get(HTTP_RANGE=header)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(self._body(response), self.PAYLOAD)

    # ---------- 条件请求 ----------
    def test_not_modified_when_if_modified_since_is_fresh(self):
        first = self._get()
        response = self._get(HTTP_IF_MODIFIED_SINCE=first['Last-Modified'])
        self.assertEqual(response.status_code, 304)
        self.assertEqual(response['Accept-Ranges'], 'bytes')

    # ---------- 安全与开关 ----------
    def test_missing_file_returns_404(self):
        self.assertEqual(self._get('videos/nope.mp4').status_code, 404)

    def test_path_traversal_is_blocked(self):
        """``..`` 穿越与「软链指向根目录外」都要挡住，所以用 realpath 而非 normpath。"""
        from django.http import Http404

        from .media import _resolve
        for bad in ('../manage.py', 'videos/../../manage.py', '..\\manage.py'):
            with self.subTest(path=bad):
                with self.assertRaises(Http404):
                    _resolve(bad)

    def test_symlink_escape_is_blocked(self):
        """目录内的软链指向根目录之外时也必须拒绝。"""
        from django.http import Http404

        from .media import _resolve
        outside = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, outside, True)
        secret = os.path.join(outside, 'secret.txt')
        with open(secret, 'w', encoding='utf-8') as fh:
            fh.write('不该被读到')
        link = os.path.join(self.media_root, 'escape.txt')
        try:
            os.symlink(secret, link)
        except (OSError, NotImplementedError):
            self.skipTest('当前环境不支持创建软链')
        with self.assertRaises(Http404):
            _resolve('escape.txt')

    @override_settings(SERVE_MEDIA=False, DEBUG=False)
    def test_media_route_is_gated_by_settings(self):
        """路由总是注册，但没开开关时必须 404，而不是把文件发出去。"""
        self.assertEqual(self._get().status_code, 404)

    # ---------- 解析器单测 ----------
    def test_parse_range_header_edges(self):
        from .media import parse_range_header
        cases = [
            (None, 1024, None),
            ('', 1024, None),
            ('bytes=0-99', 1024, (0, 99)),
            ('bytes=0-', 1024, (0, 1023)),
            ('bytes=-100', 1024, (924, 1023)),
            ('bytes=1023-1023', 1024, (1023, 1023)),
            ('bytes=1023-', 1024, (1023, 1023)),
            ('bytes=1024-', 1024, 'invalid'),
            ('bytes=2000-3000', 1024, 'invalid'),
            ('bytes=500-100', 1024, 'invalid'),
            ('bytes=-0', 1024, 'invalid'),
            ('bytes=0-10,20-30', 1024, None),
            ('bytes=abc', 1024, None),
            ('bytes=-', 1024, None),
            ('BYTES=0-9', 1024, None),          # 单位大小写敏感，按规范降级
        ]
        for header, size, expected in cases:
            with self.subTest(header=header):
                self.assertEqual(parse_range_header(header, size), expected)

    def test_empty_file_range_is_invalid(self):
        from .media import parse_range_header
        self.assertEqual(parse_range_header('bytes=0-', 0), 'invalid')

    def test_multi_chunk_streaming_is_not_truncated(self):
        """夹具必须**大于一个 CHUNK_SIZE**，否则「只发一块」的 bug 根本测不出来。

        踩过：本类其余用例的夹具是 1024 字节，小于 CHUNK_SIZE（64 KiB），
        所以哪怕生成器只 yield 第一块、后面的都漏掉，所有断言照样通过。
        而真实视频 2.3 MB 要跨 36 个块 —— 用大夹具才覆盖得到这条路径。
        """
        from .media import CHUNK_SIZE

        size = CHUNK_SIZE * 2 + 1234
        big = bytes((i * 7 + 3) % 256 for i in range(size))
        rel = 'videos/big.mp4'
        with open(os.path.join(self.media_root, rel), 'wb') as fh:
            fh.write(big)

        full = self.client.get('/media/' + rel)
        body = self._body(full)
        self.assertEqual(len(body), size)
        self.assertEqual(body, big)
        self.assertEqual(full['Content-Length'], str(size))

        # 跨块区间：起点落在第一块内，终点落在第三块内
        start, end = CHUNK_SIZE - 10, CHUNK_SIZE * 2 + 10
        part = self.client.get('/media/' + rel,
                               HTTP_RANGE='bytes=%d-%d' % (start, end))
        self.assertEqual(part.status_code, 206)
        # 流式响应**只能消费一次** —— 这里必须先存下来再断言两次，
        # 否则第二次读到的是空（生成器已耗尽）。
        part_body = self._body(part)
        self.assertEqual(len(part_body), end - start + 1)
        self.assertEqual(part_body, big[start:end + 1])

    def test_chunk_size_is_used_as_the_streaming_unit(self):
        """钉住块大小本身：它决定「大文件是否被切块发送」，不该被悄悄改掉。"""
        from .media import CHUNK_SIZE
        self.assertEqual(CHUNK_SIZE, 64 * 1024)

    # ---------- 端到端：真实种子视频 ----------
    @override_settings(MEDIA_ROOT=settings.MEDIA_ROOT, SERVE_MEDIA=True)
    def test_seeded_video_supports_range(self):
        """用仓库里真实的演示视频跑一遍，确认发出去的确实是 206。

        这个类不继承 SeedDataTestCase，库里默认是空的 ——
        必须自己导入种子数据，否则这条测试会静默变成 skip 而不是真的验证。
        """
        call_command('seed_projects', verbosity=0)
        project = Project.objects.exclude(video_file='').first()
        self.assertIsNotNone(project, '种子数据里应当有带视频的项目')
        url = project.video_file.url
        full = self.client.get(url)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full['Accept-Ranges'], 'bytes')

        size = int(full['Content-Length'])
        self.assertGreater(size, 0)
        part = self.client.get(url, HTTP_RANGE='bytes=0-1023')
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part['Content-Range'], 'bytes 0-1023/%d' % size)
        self.assertEqual(len(self._body(part)), 1024)


class ContentSecurityPolicyTestCase(TestCase):
    """CSP 头的行为与内容。

    背景：发布平台会在网关层往 HTML 注入一段腾讯 Beacon 埋点，代码不在本仓库里。
    拦它的唯一位置是浏览器侧，而 ``script-src 'self'`` 同时挡住它的外链段
    （跨域）和内联段（无 nonce）。这些用例钉住的就是这条策略别被悄悄放松。

    这里**不继承 SeedDataTestCase**：那样会把这 38 个种子用例再跑一遍
    （Django 报的用例数会凭空多 38 条，既慢又掩盖真实覆盖面）。
    本类只在需要真实项目的地方自己导数据。
    """

    HEADER = 'Content-Security-Policy'

    @classmethod
    def setUpTestData(cls):
        # 详情页要有一条真实项目才测得到真页面，否则测到的是 404 页
        call_command('seed_projects', verbosity=0)

    def _policy(self, url, **kwargs):
        response = self.client.get(url, **kwargs)
        self.assertIn(self.HEADER, response, '响应缺少 CSP 头: %s' % url)
        return response[self.HEADER]

    def _directives(self, policy):
        """把 CSP 头解析成 {指令名: 值} —— 顺便验证它本身是合法可解析的。"""
        out = {}
        for part in policy.split(';'):
            part = part.strip()
            if not part:
                continue
            name, _, value = part.partition(' ')
            self.assertNotIn(name, out, '指令重复: %s' % name)
            self.assertEqual(name, name.lower(), '指令名必须小写: %s' % name)
            out[name] = value.strip()
        return out

    # ---------- 存在性与覆盖面 ----------
    def test_home_carries_csp(self):
        self.assertIn("script-src 'self'", self._policy(reverse('showcase:home')))

    def test_every_public_surface_is_covered(self):
        """首页 / 详情页 / 404 / robots / sitemap 都要带上，别只覆盖首页。"""
        urls = [
            reverse('showcase:home'),
            reverse('showcase:detail', args=['subway-risk-decision']),
            '/robots.txt',
            '/sitemap.xml',
            '/no-such-page/',
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertIn(self.HEADER, self.client.get(url))

    def test_category_filter_page_is_covered(self):
        """分类筛选走的是同一个视图但换了 query string，别被绕过。"""
        policy = self._policy(reverse('showcase:home') + '?category=materials')
        self.assertIn("script-src 'self'", policy)

    # ---------- 内容：策略到底严不严 ----------
    def test_policy_has_no_escape_hatches(self):
        """钉住「没有后门」：这几个词只要出现一个，整条策略基本就废了。"""
        policy = self._policy(reverse('showcase:home'))
        for banned in ("'unsafe-inline'", "'unsafe-eval'", 'data:', 'blob:',
                       "'strict-dynamic'", 'http:', 'https:'):
            with self.subTest(banned=banned):
                self.assertNotIn(banned, policy)

    def test_no_source_expression_names_a_third_party_host(self):
        """整条策略里不该出现任何具体主机名。

        这是「能否挡住 beacon.cdn.qq.com」的静态证明：策略里没有任何
        允许第三方主机的源表达式，所以任何非本站的脚本来源都进不来。
        """
        policy = self._policy(reverse('showcase:home'))
        for token in policy.replace("'", ' ').split():
            if token.startswith(('http://', 'https://', '//', '*')):
                self.fail('策略里出现了第三方来源: %s' % token)

    def test_script_style_and_framing_are_locked_down(self):
        d = self._directives(self._policy(reverse('showcase:home')))
        self.assertEqual(d['script-src'], "'self'")
        self.assertEqual(d['style-src'], "'self'")
        self.assertEqual(d['default-src'], "'self'")
        self.assertEqual(d['base-uri'], "'none'")
        self.assertEqual(d['object-src'], "'none'")
        self.assertEqual(d['frame-ancestors'], "'none'")

    def test_directive_set_is_pinned(self):
        """把指令集合整体钉住：少一条（比如有人顺手删了 object-src）就报错。"""
        d = self._directives(self._policy(reverse('showcase:home')))
        expected = {
            'default-src', 'script-src', 'style-src', 'img-src', 'font-src',
            'media-src', 'connect-src', 'form-action', 'base-uri',
            'object-src', 'frame-ancestors',
        }
        self.assertEqual(set(d) - {'upgrade-insecure-requests'}, expected)

    def test_policy_parses_without_empty_directives(self):
        policy = self._policy(reverse('showcase:home'))
        for part in policy.split(';'):
            self.assertTrue(part.strip(), '出现空指令（多余的 ; ）: %r' % policy)

    # ---------- https 才加升级指令 ----------
    def test_https_gets_upgrade_insecure_requests(self):
        policy = self._policy(reverse('showcase:home'), secure=True)
        self.assertIn('upgrade-insecure-requests', policy)

    def test_http_omits_upgrade_insecure_requests(self):
        """本地 http 开发不能带这条 —— 它会把 http 子资源强行升级，
        制造出「本地才有、线上没有」的假故障。"""
        self.assertNotIn('upgrade-insecure-requests',
                         self._policy(reverse('showcase:home')))

    # ---------- 豁免与开关 ----------
    def test_admin_is_exempt(self):
        """admin 必须豁免：它不是对外面，加 CSP 零收益，且后台的内联样式
        会让 ``style-src 'self'`` 打坏页面。豁免是刻意的，别顺手"修"掉。"""
        response = self.client.get('/admin/login/')
        self.assertNotIn(self.HEADER, response)

    def test_can_be_disabled_by_settings(self):
        with override_settings(CSP_ENABLED=False):
            response = self.client.get(reverse('showcase:home'))
        self.assertNotIn(self.HEADER, response)

    def test_existing_header_is_not_overwritten(self):
        """视图若自己设过更严的策略，中间件不该覆盖它。"""
        from django.test import RequestFactory

        from .middleware import ContentSecurityPolicyMiddleware

        response = HttpResponse("x")
        response[self.HEADER] = "default-src 'none'"
        mw = ContentSecurityPolicyMiddleware(lambda request: response)
        out = mw(RequestFactory().get('/'))
        self.assertEqual(out[self.HEADER], "default-src 'none'")

    # ---------- 别把媒体流打坏 ----------
    @override_settings(SERVE_MEDIA=True)
    def test_media_range_still_works_with_csp(self):
        """CSP 是加头，不该影响流式响应 —— 但「不该」得验，不能假设。"""
        project = Project.objects.exclude(video_file='').first()
        self.assertIsNotNone(project)
        url = project.video_file.url
        full = self.client.get(url)
        self.assertEqual(full.status_code, 200)
        self.assertEqual(full['Accept-Ranges'], 'bytes')
        self.assertIn(self.HEADER, full)

        part = self.client.get(url, HTTP_RANGE='bytes=0-99')
        self.assertEqual(part.status_code, 206)
        self.assertEqual(len(b''.join(part.streaming_content)), 100)


class ThumbTestCase(TestCase):
    """缩略图层：路径约定、缺失回退、生成命令的幂等性。

    **为什么「回退」要单独测**：缩略图是**可选产物** —— 刚克隆仓库、还没跑
    ``make_thumbs``，或者源图换了但缩略图没重生成，页面都必须照常显示（用原图），
    而不是裂图。这种「缺失时降级」的路径最容易被忽略，也最容易只在别人机器上炸。

    **为什么不用 ``seed_projects`` 造数据**（踩过：10 项测试一起挂）：seed 只在
    ``media/`` 下文件**真实存在**时才建 ``ProjectShot`` 记录，而本类把
    ``MEDIA_ROOT`` 指到临时目录 —— 于是 seed 一条图片记录都建不出来，所有断言
    都变成「记录是 None」，看起来像缩略图功能坏了，其实只是夹具没建起来。
    改成自建最小夹具：要测哪张图、就放哪张图，记录与文件一一对应，测试意图
    不必再靠猜 seed 数据的形状来表达。附带好处：``make_thumbs`` 只遍历这两条
    记录，跑得快。

    生成命令一律写进临时 ``MEDIA_ROOT``，不碰仓库里已提交的 ``media/thumbs/``。
    """

    # 用仓库里两张**真实**图片：一张大面积平色的图表、一张连续色调的 GUI 截图。
    # 编码决策那条测试依赖它们的真实内容 —— 换成合成图就测不到真实结论了。
    CHART = 'shots/femnsic-fatigue-optimization/03-loocv-model-comparison.png'
    SHOT = 'shots/yolov8-detection-desktop/01-desktop-gui.png'

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='wb-thumb-test-')
        self.override = override_settings(MEDIA_ROOT=self.tmp)
        self.override.enable()

        self.project = Project.objects.create(
            title='缩略图夹具', slug='thumb-fixture',
            category=Project.CATEGORY_MATERIALS,
            summary='仅用于缩略图测试', order=1)
        # 两条记录都建出来，但**源图默认不落地**：需要真实文件的测试自己调
        # ``_place()``。这样「记录在、文件不在」也就成了一种自然状态，
        # 不用特意去删文件才能测到缺图那条分支。
        self.chart = self._add_shot(self.CHART, order=0)
        self.shot = self._add_shot(self.SHOT, order=1)

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    # ---------- 夹具 ----------
    def _add_shot(self, rel, order=0):
        shot = ProjectShot(project=self.project, kind=ProjectShot.KIND_FIGURE,
                           order=order)
        shot.image.name = rel
        shot.save()
        return shot

    def _place(self, rel):
        """把仓库里的真实源图复制进临时 MEDIA_ROOT，返回其字节数。"""
        src = os.path.join(settings.BASE_DIR, 'media', rel)
        dst = os.path.join(self.tmp, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copyfile(src, dst)
        return os.path.getsize(dst)

    def _thumb_of(self, rel):
        """已生成的缩略图绝对路径；扩展名由内容决定，两种都找。没有则 None。"""
        base = 'thumbs/' + os.path.splitext(rel)[0]
        for ext in ('.png', '.jpg'):
            path = os.path.join(self.tmp, base + ext)
            if os.path.isfile(path):
                return path
        return None

    # ---------- 路径约定与回退 ----------
    def test_falls_back_to_original_when_thumb_missing(self):
        """没有缩略图时必须回退原图 —— 这是 fail-open，不是错误。"""
        from .thumbs import find_thumb, thumb_url

        self.assertEqual(find_thumb(self.CHART), '')
        self.assertEqual(thumb_url(self.CHART, '/media/' + self.CHART),
                         '/media/' + self.CHART)

    def test_finds_thumb_regardless_of_extension(self):
        """生成端可能产出 .jpg 或 .png，读取端两种都要认。"""
        from .thumbs import find_thumb

        base = 'thumbs/shots/demo/01-x'
        for ext in ('.png', '.jpg'):
            rel = base + ext
            os.makedirs(os.path.dirname(os.path.join(self.tmp, rel)), exist_ok=True)
            with open(os.path.join(self.tmp, rel), 'wb') as fh:
                fh.write(b'x')
            self.assertEqual(find_thumb('shots/demo/01-x.png'), rel)
            os.remove(os.path.join(self.tmp, rel))

    def test_empty_image_name_is_safe(self):
        from .thumbs import find_thumb, thumb_url

        self.assertEqual(find_thumb(''), '')
        self.assertEqual(thumb_url('', '/media/fallback.png'), '/media/fallback.png')

    def test_project_shot_thumb_url_prefers_thumb(self):
        """有缩略图时 ``thumb_url`` 指向它，``image.url`` 仍指向原图。"""
        self.assertEqual(self.chart.thumb_url, self.chart.image.url)  # 没缩略图 -> 原图

        rel = 'thumbs/' + os.path.splitext(self.CHART)[0] + '.png'
        os.makedirs(os.path.dirname(os.path.join(self.tmp, rel)), exist_ok=True)
        with open(os.path.join(self.tmp, rel), 'wb') as fh:
            fh.write(b'x')

        self.assertEqual(self.chart.thumb_url, settings.MEDIA_URL + rel)
        self.assertIn('shots/', self.chart.image.url)                 # 原图路径没变

    # ---------- 生成命令 ----------
    def test_make_thumbs_generates_smaller_files(self):
        sizes = {rel: self._place(rel) for rel in (self.CHART, self.SHOT)}

        call_command('make_thumbs', verbosity=0)

        for rel, before in sizes.items():
            with self.subTest(source=rel):
                thumb = self._thumb_of(rel)
                self.assertIsNotNone(thumb, '应生成缩略图')
                self.assertLess(os.path.getsize(thumb), before)

    def test_make_thumbs_picks_encoding_by_content(self):
        """图表选 PNG、连续色调截图选 JPEG —— 实测结论，别退化成硬编码规则。"""
        for rel in (self.CHART, self.SHOT):
            self._place(rel)

        call_command('make_thumbs', verbosity=0)

        chart = 'thumbs/' + os.path.splitext(self.CHART)[0] + '.png'
        shot = 'thumbs/' + os.path.splitext(self.SHOT)[0] + '.jpg'
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, chart)),
                        '大面积平色的图表应当选 PNG 调色板（实测更小且更清晰）')
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, shot)),
                        '连续色调截图应当选 JPEG（实测更小且 PSNR 更高）')

    def test_make_thumbs_is_idempotent(self):
        """跑第二遍不该重做 —— 否则每次部署都要多花一遍时间。

        判据是「文件没被改写」：记下第一遍产物的字节与 mtime，第二遍之后两者都
        必须原封不动。这比只断言输出文字更硬 —— 命令嘴上说「复用」、背地里重写，
        光查输出是查不出来的。

        （早先这里试过「往缩略图里写个标记再跑」的写法，但复用判断现在会**打开
        文件核对像素宽度**，一个装标记的假文件本来就不该被复用 —— 新逻辑把它
        正确地拒掉了，于是那条路走不通，判据换回字节 + mtime。）
        """
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0)
        thumb = self._thumb_of(self.CHART)
        self.assertIsNotNone(thumb)
        with open(thumb, 'rb') as fh:
            first = fh.read()
        mtime = os.path.getmtime(thumb)

        out = io.StringIO()
        call_command('make_thumbs', verbosity=0, stdout=out)

        with open(thumb, 'rb') as fh:
            self.assertEqual(fh.read(), first, '第二遍重写了文件')
        self.assertEqual(os.path.getmtime(thumb), mtime, '第二遍动了 mtime')
        self.assertIn('生成 0 张', out.getvalue())
        self.assertIn('复用 1 张', out.getvalue())

    def test_make_thumbs_force_regenerates(self):
        """``--force`` 要真的重写，而不只是「不跳过」。

        同样用**文件内容**做判据而不是 mtime：先把缩略图弄坏，``--force`` 之后
        它必须变回一张真图。mtime 的时钟粒度在不同文件系统上不一样，同一时刻写完
        再写会得出「没变」的假失败。
        """
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0)
        thumb = self._thumb_of(self.CHART)
        self.assertIsNotNone(thumb)
        with open(thumb, 'rb') as fh:
            good = fh.read()

        with open(thumb, 'wb') as fh:                  # 先把它弄坏
            fh.write(b'not an image')

        out = io.StringIO()
        call_command('make_thumbs', verbosity=0, force=True, stdout=out)

        self.assertIn('生成 1 张', out.getvalue())
        with open(thumb, 'rb') as fh:
            self.assertEqual(fh.read(), good, '--force 没有重写文件')

    def test_make_thumbs_dry_run_writes_nothing(self):
        self._place(self.CHART)

        call_command('make_thumbs', verbosity=0, dry_run=True)

        self.assertFalse(os.path.isdir(os.path.join(self.tmp, 'thumbs')),
                         '--dry-run 不该产生任何文件')

    def test_make_thumbs_survives_missing_source(self):
        """源图缺失只跳过、不抛异常 —— 库里有记录但文件没传上来是真实情况。"""
        self._place(self.CHART)          # 只放图表；SHOT 记录在、文件不在

        out = io.StringIO()
        call_command('make_thumbs', verbosity=0, stdout=out)

        text = out.getvalue()
        self.assertIn('源图缺失 1 张', text)
        self.assertIn(self.SHOT, text)
        self.assertIsNone(self._thumb_of(self.SHOT))
        self.assertIsNotNone(self._thumb_of(self.CHART), '一张缺图不该拖累另一张')

    def test_make_thumbs_respects_width(self):
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0, width=200)

        thumb = self._thumb_of(self.CHART)
        self.assertIsNotNone(thumb)
        with PILImage.open(thumb) as im:
            self.assertEqual(im.width, 200)

    def test_make_thumbs_skips_when_source_already_smaller(self):
        """源图已经比缩略图小时**不生成**，并清掉可能存在的旧缩略图。

        实测踩到：``covers/gesture-hci-cover.jpg`` 源图 48 KB，而 800 宽的
        「缩略图」反而 50 KB —— 生成它纯属**增加**流量。这时正确的做法是什么都不
        生成，让 ``thumb_url`` 那套 fail-open 回退到原图。

        这里把源图造成「400 宽 + JPEG q5」：宽度低于目标宽度（不会被缩放），
        质量又低到任何 q80/90 重编码的 PSNR 都够不到 38 dB 的门槛 ——
        于是命令只能挑 PSNR 最高的那个候选，也就是**最大**的那个，
        必然超过源图体积。触发条件因此是确定的，不靠碰运气。
        """
        src = os.path.join(self.tmp, self.SHOT)
        os.makedirs(os.path.dirname(src), exist_ok=True)
        with PILImage.open(os.path.join(settings.BASE_DIR, 'media', self.SHOT)) as im:
            w = 400
            im.convert('RGB').resize(
                (w, max(1, round(im.height * w / im.width))), PILImage.LANCZOS
            ).save(src, 'JPEG', quality=5)
        before = os.path.getsize(src)

        # 预置一份"上次生成的缩略图"：是张真图，但**比源图还大** ——
        # 正是要修的那个情形（重压低质量源图反而更肿）
        stale = os.path.join(self.tmp, 'thumbs',
                             os.path.splitext(self.SHOT)[0] + '.png')
        os.makedirs(os.path.dirname(stale), exist_ok=True)
        with PILImage.open(src) as im:
            im.save(stale, 'PNG')
        self.assertGreater(os.path.getsize(stale), before, '夹具前提：旧缩略图应当比源图大')

        out = io.StringIO()
        call_command('make_thumbs', verbosity=0, stdout=out)

        self.assertIn('源图已足够小 1 张', out.getvalue())
        self.assertIsNone(self._thumb_of(self.SHOT), '不该留下缩略图')
        self.assertEqual(os.path.getsize(src), before, '不该动源图')

    def test_make_thumbs_ignores_thumb_at_wrong_width(self):
        """别人跑过 ``--width 200`` 留下的缩略图，默认跑时不该被当成「已是最新」。

        只看大小与时间的复用判断会放它过去 —— 200px 的缩略图当然比源图小、
        也比源图新。于是仓库里会一直留着 200px 的缩略图，页面上明显发虚，
        而且第二次跑还会理直气壮地报「复用 16 张」。宽度是唯一能验证
        「这份缩略图是照本次参数生成的」的凭据。
        """
        from .management.commands.make_thumbs import DEFAULT_WIDTH

        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0, width=200)
        with PILImage.open(self._thumb_of(self.CHART)) as im:
            self.assertEqual(im.width, 200)

        out = io.StringIO()
        call_command('make_thumbs', verbosity=0, stdout=out)

        self.assertIn('生成 1 张', out.getvalue())
        with PILImage.open(self._thumb_of(self.CHART)) as im:
            self.assertEqual(im.width, DEFAULT_WIDTH)

    def test_make_thumbs_removes_stale_other_extension(self):
        """换编码后必须把旧的另一种扩展名删掉。

        不删的话仓库里会同时留着 .jpg 与 .png 两份缩略图 —— 多出一份没人引用的
        文件，而且 ``find_thumb`` 的优先级会让「哪份在生效」变得不明显。

        这不是假想：默认宽度从 640 改到 800 时，``experimentpilot-ai/01`` 那张
        就从 JPEG 翻到了 PNG（截图里大块平色区让 PNG 的体量增长慢于 JPEG，
        两条曲线在中间某处交叉）。
        """
        self._place(self.CHART)
        base = os.path.join(self.tmp, 'thumbs', os.path.splitext(self.CHART)[0])
        os.makedirs(os.path.dirname(base), exist_ok=True)
        for ext in ('.jpg', '.png'):
            with open(base + ext, 'wb') as fh:
                fh.write(b'stale')

        call_command('make_thumbs', verbosity=0)

        left = [e for e in ('.jpg', '.png') if os.path.isfile(base + e)]
        self.assertEqual(len(left), 1, '应当只剩一份缩略图，实际: %s' % left)
        with open(base + left[0], 'rb') as fh:
            self.assertNotEqual(fh.read(), b'stale', '留下的那份应当是刚生成的')

    def test_default_width_covers_2x_cards(self):
        """默认宽度必须覆盖卡片在 2× 屏上的**实际**渲染宽度。

        实测（``docs/tools/measure_thumb_width.js``，1440 / 1600 / 768 / 390 四种
        视口）：图集卡片渲染 350–359 CSS px，2× 即 700–718 设备像素；而
        ``object-fit: cover`` 对**宽图是按高度放大的**，最宽的那张源图
        （宽高比 1.86）实际需要 400 × 1.86 = 743px。

        这条测试存在的意义：640 曾经「看起来够用」（注释里就写着「640 宽足够
        覆盖 2× DPR」），直到真去量才发现每一张都在被放大 8–12%。把下限钉在
        这里，谁想调小就得先解释为什么。
        """
        from .management.commands.make_thumbs import DEFAULT_WIDTH

        self.assertGreaterEqual(DEFAULT_WIDTH, 768)

    # ---------- 后台接线 ----------
    def test_upload_path_is_grouped_by_project(self):
        """后台上传的图必须落到 ``shots/<slug>/``，不能平铺在 ``shots/``。

        平铺的话文件名一撞就被 Django 自动加随机后缀（``01.png`` →
        ``01_Ab3xY9.png``），``media/shots/`` 很快变得没法看，而且
        「这张图属于哪个项目」只能靠数据库反查。
        """
        shot = ProjectShot(project=self.project, kind=ProjectShot.KIND_UI, order=9)
        shot.image = SimpleUploadedFile('01-x.png', b'x', content_type='image/png')
        shot.save()
        self.assertEqual(shot.image.name, 'shots/thumb-fixture/01-x.png')

        self.project.cover_image = SimpleUploadedFile('cover.jpg', b'x',
                                                     content_type='image/jpeg')
        self.project.save()
        self.assertEqual(self.project.cover_image.name,
                         'covers/thumb-fixture-cover.jpg')

    def test_admin_save_generates_thumb(self):
        """后台保存项目后，新上传的图应当已经有缩略图 —— 不靠人记得跑命令。

        这条测的是「接线」而不是「生成」：生成逻辑由 ``thumbs.build()`` 那组
        测试覆盖。这里只确认 ``ProjectAdmin.save_related`` 真的把项目下的图片
        都过了一遍 —— 漏了这条线，后果是**页面悄悄变重**，几乎不会有人发现。
        """
        from django.contrib.admin.sites import site
        from django.test import RequestFactory

        from .admin import ProjectAdmin

        self._place(self.CHART)
        self.assertIsNone(self._thumb_of(self.CHART), '夹具前提：此时还没有缩略图')

        class _Form(object):
            instance = self.project

            def save_m2m(self):
                pass

        ProjectAdmin(Project, site).save_related(
            RequestFactory().get('/admin/'), _Form(), [], False)

        self.assertIsNotNone(self._thumb_of(self.CHART), '保存后应当已有缩略图')

    def test_deleting_shot_does_not_touch_files(self):
        """删记录**不该**删文件 —— 这是 Django 的默认行为，也是刻意的。

        曾经在 ``ProjectShot`` 上挂过 ``post_delete`` 信号，让删截图时顺手删掉
        它的缩略图（为了不留孤儿文件）。结果它把**真实**缩略图删了：
        ``SeedDataTestCase`` 里有一条「清空 delivery 分类验证空态」的用例，
        级联删除截图时信号照常触发，而那个测试类用的是真实 ``MEDIA_ROOT`` ——
        于是跑一次测试，仓库里就少一张图，而且没有任何提示。

        教训：把「删数据」和「删文件」绑在一起很危险，因为删数据的场景
        （测试、重置种子、导入脚本）远比想象的多。Django 自己不在 delete 时
        删文件，就是这个原因。孤儿缩略图改用显式的 ``make_thumbs --prune`` 清理。

        这条测试就是那次事故的墓碑：谁再想把信号加回来，先看这里。
        """
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0)
        thumb = self._thumb_of(self.CHART)
        self.assertIsNotNone(thumb)

        self.chart.delete()

        self.assertTrue(os.path.exists(thumb), '删记录不该动文件')

    def test_make_thumbs_prune_removes_only_orphans(self):
        """``--prune`` 删源图已不存在的缩略图；默认不删；源图还在的不动。"""
        # 一个孤儿：源图从来没存在过
        orphan = os.path.join(self.tmp, 'thumbs', 'shots', 'gone', '01-x.jpg')
        os.makedirs(os.path.dirname(orphan), exist_ok=True)
        with open(orphan, 'wb') as fh:
            fh.write(b'x')

        # 一个正常的：源图在、缩略图已生成
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0)
        alive = self._thumb_of(self.CHART)
        self.assertIsNotNone(alive)

        call_command('make_thumbs', verbosity=0)          # 不带 --prune
        self.assertTrue(os.path.exists(orphan), '默认不该删任何东西')

        call_command('make_thumbs', verbosity=0, prune=True)
        self.assertFalse(os.path.exists(orphan), '--prune 应当删掉孤儿')
        self.assertTrue(os.path.exists(alive), '源图还在的缩略图不能被误删')

    # ---------- 模板接线 ----------
    def test_detail_gallery_uses_thumb_for_img_and_original_for_link(self):
        """网格 ``<img>`` 用缩略图，点开的 ``<a href>`` 用原图 —— 两边都要对。"""
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0)

        html = self.client.get('/project/thumb-fixture/').content.decode()
        self.assertIn('/media/thumbs/', self.chart.thumb_url)
        self.assertIn('src="%s"' % self.chart.thumb_url, html)
        self.assertIn('href="%s"' % self.chart.image.url, html)

    def test_home_card_uses_thumb(self):
        """首页卡片封面同样走缩略图，别只改了详情页。

        夹具项目**没有** ``cover_image``，于是走 ``shots.first()`` 这条回退 ——
        正好把「封面优先级链」里非首项的那条也覆盖到。
        """
        self._place(self.CHART)
        call_command('make_thumbs', verbosity=0)

        url = self.project.cover_image_url
        self.assertIn('/media/thumbs/', url)
        self.assertIn('src="%s"' % url, self.client.get('/').content.decode())
