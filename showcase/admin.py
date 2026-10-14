"""后台管理：在 Admin 中直接维护项目、贡献点、指标、技术栈与演示视频。"""

from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Award, Contribution, Education, Metric, Pillar, Profile, ProfileFact,
    Project, ProjectLink, SkillGroup, Stat, TechItem,
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


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'role', 'order',
                    'is_featured', 'video_status', 'updated_at')
    list_filter = ('category', 'is_featured')
    list_editable = ('order', 'is_featured')
    search_fields = ('title', 'summary', 'intro', 'role')
    prepopulated_fields = {'slug': ('title',)}
    inlines = [ContributionInline, MetricInline, TechItemInline, ProjectLinkInline]
    fieldsets = (
        ('基本信息', {
            'fields': ('title', 'slug', 'badge', 'category', 'role', 'period',
                       'order', 'is_featured')
        }),
        ('文案', {
            'fields': ('summary', 'intro')
        }),
        ('演示视频', {
            'fields': ('video_file', 'video_external_url', 'video_caption', 'demo_image'),
            'description': '优先播放上传的视频文件；若只填外部链接则用 iframe 嵌入；'
                           '都没有时展示占位提示。'
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
