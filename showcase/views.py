"""视图：首页项目列表 + 项目详情页 + 自定义 404。"""

from django.shortcuts import render, get_object_or_404

from .models import (
    Award, Education, Pillar, Profile, ProfileFact, Project, SkillGroup, Stat,
)

FALLBACK_TITLE = '项目作品集'


def _share_title(profile, suffix=None):
    """分享卡片标题：「姓名 · 后缀」，缺姓名时退到「项目作品集」。"""
    name = getattr(profile, 'name', '') or ''
    if not name:
        return suffix or FALLBACK_TITLE
    return '{} · {}'.format(name, suffix) if suffix else name


def _share_description(profile):
    """分享卡片描述：优先 tagline，其次 headline，最后空串（模板会留空）。"""
    if not profile:
        return ''
    return profile.tagline or profile.headline or ''


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

    profile = Profile.objects.first()
    context = {
        'profile': profile,
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
        # ---- 社交分享卡片（base.html 里优先用这两个，缺了才回退 profile）----
        'og_title': _share_title(profile, FALLBACK_TITLE),
        'og_description': _share_description(profile),
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

    profile = Profile.objects.first()

    # 分享图用项目封面；相对路径要转成绝对地址，否则平台抓不到图。
    # cover_image_file 依赖 prefetch 过的 shots，这里已 prefetch，不会多查。
    share_image = share_image_w = share_image_h = share_alt = ''
    cover = project.cover_image_file
    if cover:
        share_image = request.build_absolute_uri(cover.url)
        share_alt = '{} 封面图'.format(project.title)
        try:
            # ImageFieldFile.width/height 会打开文件读一次头部（有缓存）。
            # 文件缺失时抛异常 —— 那就别写尺寸，交给平台自己取。
            share_image_w, share_image_h = cover.width, cover.height
        except (OSError, ValueError):
            share_image_w = share_image_h = ''

    context = {
        'profile': profile,
        'project': project,
        'prev_project': prev_project,
        'next_project': next_project,
        'related_projects': related,
        'categories': Project.CATEGORY_CHOICES,
        # ---- 社交分享卡片 ----
        'og_type': 'article',
        'og_title': '{} · {}'.format(project.title, _share_title(profile)),
        'og_description': project.summary or _share_description(profile),
        'og_image': share_image,
        'og_image_width': share_image_w,
        'og_image_height': share_image_h,
        'og_image_alt': share_alt,
    }
    return render(request, 'showcase/detail.html', context)


def page_not_found(request, exception):
    """自定义 404。

    只在 ``DEBUG=False`` 时生效（DEBUG 打开时 Django 显示调试页）。
    这里显式传 ``profile``，否则 base.html 的页头会退化成占位文案。
    """
    profile = Profile.objects.first()
    return render(request, '404.html', {
        'profile': profile,
        'og_title': '页面不存在 · {}'.format(_share_title(profile)),
    }, status=404)
