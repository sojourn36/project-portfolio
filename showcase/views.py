"""视图：首页项目列表 + 项目详情页 + 自定义 404。"""

from django.shortcuts import render, get_object_or_404

from .models import (
    Award, Education, Pillar, Profile, ProfileFact, Project, SkillGroup, Stat,
)


def home(request):
    """首页：整体介绍 + 教育 + 项目列表 + 荣誉 + 技能，支持按分类筛选。"""
    valid_categories = [key for key, _label in Project.CATEGORY_CHOICES]
    active_category = request.GET.get('category', '').strip()
    if active_category not in valid_categories:
        active_category = ''

    projects = (Project.objects
                .prefetch_related('contributions', 'metrics', 'techs', 'shots'))
    if active_category:
        projects = projects.filter(category=active_category)

    context = {
        'profile': Profile.objects.first(),
        'stats': Stat.objects.all(),
        'facts': ProfileFact.objects.all(),
        'pillars': Pillar.objects.all(),
        'educations': Education.objects.all(),
        'projects': projects,
        'project_total': Project.objects.count(),
        'categories': Project.CATEGORY_CHOICES,
        'active_category': active_category,
        'awards': Award.objects.all(),
        'skill_groups': SkillGroup.objects.all(),
    }
    return render(request, 'showcase/home.html', context)


def detail(request, slug):
    """详情页：完整介绍 + 可播放的演示视频。"""
    project = get_object_or_404(
        Project.objects.prefetch_related('contributions', 'metrics', 'techs',
                                         'links', 'shots'),
        slug=slug,
    )

    # 上一个 / 下一个项目（按 order, id 顺序）
    ordered = list(Project.objects.all())
    index = next((i for i, item in enumerate(ordered) if item.pk == project.pk), None)
    prev_project = ordered[index - 1] if index not in (None, 0) else None
    next_project = (ordered[index + 1]
                    if index is not None and index + 1 < len(ordered) else None)

    # 同类推荐
    related = (Project.objects
               .filter(category=project.category)
               .exclude(pk=project.pk)[:3])

    context = {
        'profile': Profile.objects.first(),
        'project': project,
        'prev_project': prev_project,
        'next_project': next_project,
        'related_projects': related,
        'categories': Project.CATEGORY_CHOICES,
    }
    return render(request, 'showcase/detail.html', context)


def page_not_found(request, exception):
    """自定义 404。

    只在 ``DEBUG=False`` 时生效（DEBUG 打开时 Django 显示调试页）。
    这里显式传 ``profile``，否则 base.html 的页头会退化成占位文案。
    """
    return render(request, '404.html',
                  {'profile': Profile.objects.first()}, status=404)
