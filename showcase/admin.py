"""后台管理：在 Admin 中直接维护项目、贡献点、指标、技术栈与演示视频。"""

from django.contrib import admin, messages
from django.utils.html import format_html

from .models import (
    Award, Contribution, Education, Metric, Pillar, Profile, ProfileFact,
    Project, ProjectLink, ProjectShot, SkillGroup, Stat, TechItem,
)


class ContributionInline(admin.TabularInline):
    model = Contribution
    extra = 1


class MetricInline(admin.TabularInline):
    model = Metric
    extra = 1


class TechItemInline(admin.TabularInline):
    model = TechItem
    extra = 1


class ProjectLinkInline(admin.TabularInline):
    model = ProjectLink
    extra = 1


class ProjectShotInline(admin.TabularInline):
    """实机截图 / 结果图：一个项目可挂多张，按 order 排序。"""

    model = ProjectShot
    extra = 1
    fields = ('order', 'kind', 'image', 'caption', 'image_preview')
    readonly_fields = ('image_preview',)
    ordering = ('order', 'id')

    @admin.display(description='预览')
    def image_preview(self, obj):
        if not obj.pk or not obj.image:
            return '—'
        return format_html(
            '<img src="{}" style="height:72px;border-radius:4px;'
            'border:1px solid #d4d4d8" />', obj.image.url)


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'role', 'order',
                    'is_featured', 'video_status', 'shot_count', 'updated_at')
    list_filter = ('category', 'is_featured')
    list_editable = ('order', 'is_featured')
    search_fields = ('title', 'summary', 'intro', 'role')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ContributionInline, MetricInline, TechItemInline,
               ProjectLinkInline, ProjectShotInline]
    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'slug', 'badge', 'category', 'role', 'period',
                       'order', 'is_featured')
        }),
        ('文案', {
            'fields': ('summary', 'intro')
        }),
        ('演示素材', {
            'fields': ('video_file', 'video_external_url', 'video_caption',
                       'demo_image', 'cover_image'),
            'description': '优先播放上传的视频文件；若只填外部链接则用 iframe 嵌入；'
                           '都没有时展示占位提示。'
                           '「列表封面图」留空时自动取第一张实机截图、再退到演示动图。'
        }),
        ('实机截图 / 结果图', {
            'fields': (),
            'description': '在下方「实机截图 / 结果图」内联区逐张添加。'
                           '这些是项目真实运行产出的界面截图与结果图，'
                           '会以图集形式展示在详情页。'
        }),
    )

    def video_status(self, obj):
        if obj.video_file:
            return format_html('<span style="color:#0d9488">✔ 本地视频</span>')
        if obj.video_external_url:
            return format_html('<span style="color:#2563eb">✔ 外链</span>')
        if obj.demo_image:
            return format_html('<span style="color:#7c3aed">✔ 动图</span>')
        return format_html('<span style="color:#b45309">— 待补充</span>')

    video_status.short_description = '演示素材'

    @admin.display(description='实机截图')
    def shot_count(self, obj):
        n = obj.shots.count()
        if not n:
            return format_html('<span style="color:#b45309">— 无</span>')
        return format_html('<span style="color:#0d9488">✔ {} 张</span>', n)

    # ---- 保存时顺手生成缩略图 ----
    def save_related(self, request, form, formsets, change):
        """内联表保存完之后，为该项目的图片补上缩略图。

        为什么放在这里而不是让模型 ``save()`` 去做：缩略图缺失**不会**让页面坏掉
        （``thumb_url`` 会回退到原图），所以「传了图但没跑 ``make_thumbs``」的后果
        只是**页面悄悄变重** —— 几乎不可能被人注意到。与其指望记得，不如保存时
        就做掉，而且用的是与命令行同一个 ``build()``，不会出现两套行为。

        失败只提示、不阻断保存：缩略图是优化，不是内容。
        """
        super().save_related(request, form, formsets, change)

        from .thumbs import build

        names = [shot.image.name for shot in form.instance.shots.all() if shot.image]
        if form.instance.cover_image:
            names.append(form.instance.cover_image.name)

        failed = []
        for name in names:
            try:
                build(name)
            except Exception as exc:                      # pragma: no cover
                failed.append('{}（{}）'.format(name, exc))
        if failed:
            messages.warning(
                request,
                '以下图片的缩略图生成失败，页面会回退到原图（较慢但不会裂图）：{}'
                .format('、'.join(failed)))


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'headline', 'phone', 'email', 'city')
    fieldsets = (
        ('基本', {'fields': ('name', 'headline', 'tagline', 'phone', 'email', 'city')}),
        ('文案', {'fields': ('intro', 'about'),
                  'description': 'intro 用于首页顶部；about 用于「关于」区块，空行分段。'}),
    )

    def has_add_permission(self, request):
        # 单例：已有记录时不再允许新增
        return not Profile.objects.exists()


@admin.register(Stat)
class StatAdmin(admin.ModelAdmin):
    list_display = ('value', 'label', 'order')
    list_editable = ('order',)


@admin.register(ProfileFact)
class ProfileFactAdmin(admin.ModelAdmin):
    list_display = ('title', 'subtitle', 'icon', 'order')
    list_editable = ('order',)
    list_filter = ('icon',)


@admin.register(Pillar)
class PillarAdmin(admin.ModelAdmin):
    list_display = ('title', 'description', 'icon', 'order')
    list_editable = ('order',)
    list_filter = ('icon',)


@admin.register(Education)
class EducationAdmin(admin.ModelAdmin):
    list_display = ('school', 'degree', 'period', 'order')
    list_editable = ('order',)
    search_fields = ('school', 'degree', 'org', 'description')


@admin.register(Award)
class AwardAdmin(admin.ModelAdmin):
    list_display = ('title', 'detail', 'icon', 'order')
    list_editable = ('order',)


@admin.register(SkillGroup)
class SkillGroupAdmin(admin.ModelAdmin):
    list_display = ('name', 'items', 'order')
    list_editable = ('order',)
