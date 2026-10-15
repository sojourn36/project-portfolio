"""showcase 应用的冒烟测试。

覆盖：首页各区块渲染、分类筛选、详情页与演示视频、翻页、404、模型属性。
运行::

    python manage.py test showcase -v 2
"""

from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

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
        # 模板语法不得泄漏到输出
        self.assertNotIn('{%', html)
        self.assertNotIn('{{', html)

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
                self.assertNotIn('{%', response.content.decode())

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

    # ---------- 后台 ----------
    def test_admin_requires_login(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
