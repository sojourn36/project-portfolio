"""showcase 应用的冒烟测试。

覆盖：首页各区块渲染、分类筛选、详情页与演示视频、翻页、404、模型属性。
运行::

    python manage.py test showcase -v 2
"""

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import (
    Education, Pillar, Profile, ProfileFact, Project, SkillGroup, Stat,
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
        response = self.client.get('/project/gesture-hci/')
        self.assertContains(response, 'video-placeholder')

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

    # ---------- 后台 ----------
    def test_admin_requires_login(self):
        response = self.client.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/admin/login/', response['Location'])
