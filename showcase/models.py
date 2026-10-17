"""项目展示界面的数据模型。

设计说明：
- ``Project`` 为项目主表；贡献点、量化指标、技术栈、外链拆成独立的关联表，
  便于在 Admin 中逐条维护与排序。
- ``Profile`` 为个人简介单例（首页顶部 + 关于区块）。
- ``Award`` / ``SkillGroup`` 用于首页的荣誉与技能展示。
"""

from django.db import models
from django.urls import reverse

from .thumbs import thumb_url as _thumb_url


def _shot_upload_to(instance, filename):
    """截图按项目分目录：``shots/<项目 slug>/<文件名>``。

    ``upload_to='shots/'`` 会把所有项目的图**平铺**在同一个目录里：文件名一撞
    就由 Django 自动加随机后缀（``01.png`` → ``01_Ab3xY9.png``），
    ``media/shots/`` 很快变得没法看。种子数据用的是 ``shots/<slug>/xx.png``，
    这里保持一致 —— 后台传的图和命令行归集的图应当落在同一种结构里。
    """
    # 新建内联行时 project 已由 formset 赋好；万一是程序里直接构造且没设，
    # RelatedObjectDoesNotExist 是 AttributeError 的子类，会被 getattr 吞掉。
    slug = getattr(instance.project, 'slug', '') or 'misc'
    return 'shots/{}/{}'.format(slug, filename)


def _cover_upload_to(instance, filename):
    """卡片封面带上项目 slug：``covers/<slug>-<文件名>``。

    沿用仓库里已有的命名（``covers/gesture-hci-cover.jpg``），
    让「这张封面属于哪个项目」从路径上就能看出来。
    """
    return 'covers/{}-{}'.format(instance.slug or 'misc', filename)


# ==========================================================================
# 项目
# ==========================================================================
class Project(models.Model):
    CATEGORY_MATERIALS = 'materials'
    CATEGORY_TRANSIT = 'transit'
    CATEGORY_VISION = 'vision'
    CATEGORY_DELIVERY = 'delivery'

    CATEGORY_CHOICES = [
        (CATEGORY_MATERIALS, 'AI × 材料'),
        (CATEGORY_TRANSIT, '轨道交通'),
        (CATEGORY_VISION, '视觉 · 人机交互'),
        (CATEGORY_DELIVERY, '系统交付'),
    ]

    # 分类 → 前端配色键（供模板使用）
    CATEGORY_KEYS = {
        CATEGORY_MATERIALS: 'materials',
        CATEGORY_TRANSIT: 'transit',
        CATEGORY_VISION: 'vision',
        CATEGORY_DELIVERY: 'delivery',
    }

    title = models.CharField('项目名称', max_length=140)
    slug = models.SlugField('URL 标识', max_length=140, unique=True,
                            help_text='仅字母/数字/连字符，用于详情页地址')
    badge = models.CharField('卡片角标', max_length=6, blank=True,
                             help_text='2-4 个字符，如 EP / Fe / SUB')
    category = models.CharField('分类', max_length=20, choices=CATEGORY_CHOICES,
                                default=CATEGORY_MATERIALS)
    role = models.CharField('我的角色', max_length=140, blank=True)
    period = models.CharField('项目时间', max_length=60, blank=True)
    summary = models.TextField('简介（列表页展示）')
    intro = models.TextField('完整介绍（详情页展示）', blank=True)
    order = models.PositiveIntegerField('排序', default=0, help_text='数字越小越靠前')
    is_featured = models.BooleanField('主打项目', default=False)

    # ---- 演示视频 ----
    video_file = models.FileField('演示视频文件', upload_to='videos/', blank=True, null=True,
                                  help_text='建议 mp4 / webm 格式')
    video_external_url = models.URLField('外部视频链接', blank=True,
                                         help_text='B站 / YouTube 等嵌入地址')
    video_caption = models.CharField('视频说明', max_length=200, blank=True)
    demo_image = models.ImageField('演示动图 / 截图', upload_to='demos/', blank=True, null=True,
                                   help_text='没有视频时可放 GIF 动图')
    cover_image = models.ImageField('列表封面图（可选）', upload_to=_cover_upload_to,
                                    blank=True, null=True,
                                    help_text='首页卡片封面。留空则自动取第一张实机截图，'
                                              '再退到演示动图；两者都无则不显示封面。'
                                              '用于「第一张截图不适合当封面」时手工指定。'
                                              '建议宽高比 2:1 左右（卡片是 172px 高的横条）。')

    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '项目'
        verbose_name_plural = '项目'

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return reverse('showcase:detail', kwargs={'slug': self.slug})

    @property
    def category_key(self):
        """前端 CSS 类名用的分类键。"""
        return self.CATEGORY_KEYS.get(self.category, 'materials')

    @property
    def has_video(self):
        return bool(self.video_file or self.video_external_url)

    @property
    def has_demo(self):
        return bool(self.video_file or self.video_external_url or self.demo_image)

    @property
    def has_shots(self):
        """是否配置了实机截图 / 结果图。"""
        return bool(self.shots.exists()) if self.pk else False

    @property
    def cover_image_file(self):
        """``cover_image_url`` 实际取到的那个图片字段（可能为 ``None``）。

        优先级：显式指定的 ``cover_image`` → 第一张实机截图 → 演示动图。
        单独暴露出来，是为了让调用方能顺手读到图片的真实宽高
        （社交分享卡片要写 ``og:image:width`` / ``height``，
        写死尺寸在封面尺寸不固定时是错的）。
        注意：调用方应先 ``prefetch_related('shots')``。
        """
        if self.cover_image:
            return self.cover_image
        shot = self.shots.first() if self.pk else None
        if shot and shot.image:
            return shot.image
        if self.demo_image:
            return self.demo_image
        return None

    @property
    def cover_image_url(self):
        """列表卡片封面**缩略图**地址；无封面时返回空串（模板据此决定是否渲染）。

        与 ``cover_image_file`` 的分工：后者返回原图字段 —— 社交分享卡片
        （``og:image``）需要全尺寸，那条路继续用原图；而列表卡片在页面上只有
        ~380px 宽，用原图纯属浪费。线上实测首页滚全页 780 KB，其中卡片封面
        就占了 190 / 171 / 147 / 98 / 57 KB 五张。

        缩略图缺失时自动回退到原图（见 ``showcase/thumbs.py``）。
        优先级与 ``cover_image_file`` 完全一致，只是逐项换成了 rendition。
        """
        if self.cover_image:
            return _thumb_url(self.cover_image.name, self.cover_image.url)
        shot = self.shots.first() if self.pk else None
        if shot and shot.image:
            return shot.thumb_url
        if self.demo_image:
            return self.demo_image.url
        return ''

    @property
    def cover_caption(self):
        """封面图的替代文字：显式封面图 → 截图说明 → 项目名。"""
        if self.cover_image:
            return '{} 封面图'.format(self.title)
        shot = self.shots.first() if self.pk else None
        if shot and shot.caption:
            return shot.caption
        return self.title


class ProjectShot(models.Model):
    """项目详情页的实机截图 / 结果图。

    与 ``demo_image`` 的区别：``demo_image`` 是「单张演示图」，
    而本表用于承载**多张**真实运行产出（界面截图、模型输出图、检测结果等），
    支持逐张配文字说明与排序。
    """

    KIND_UI = 'ui'
    KIND_RESULT = 'result'
    KIND_FIGURE = 'figure'
    KIND_GUI = 'gui'

    KIND_CHOICES = [
        (KIND_UI, '界面截图'),
        (KIND_RESULT, '运行结果'),
        (KIND_FIGURE, '图表 / 曲线'),
        (KIND_GUI, '桌面端界面'),
    ]

    project = models.ForeignKey(Project, related_name='shots',
                                on_delete=models.CASCADE, verbose_name='所属项目')
    image = models.ImageField('图片', upload_to=_shot_upload_to)
    caption = models.CharField('图片说明', max_length=160, blank=True)
    kind = models.CharField('类型', max_length=10, choices=KIND_CHOICES,
                            default=KIND_UI)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '实机截图 / 结果图'
        verbose_name_plural = '实机截图 / 结果图'

    def __str__(self):
        return self.caption or (self.image.name if self.image else '未命名截图')

    @property
    def thumb_url(self):
        """网格卡片用的缩略图地址；缩略图不存在时**回退到原图**。

        为什么要有它：卡片在 CSS 里是 ``height: 200px`` 的小图，而原先 ``<img src>``
        直接用原图 —— 等于拿一张 555 KB 的图去渲染 200px 缩略图。线上实测
        yolov8 详情页 797 KB 里有 556 KB 是这么浪费掉的。

        回退是刻意的 fail-open：刚克隆仓库、还没跑 ``make_thumbs``，或者原图换了
        但缩略图没重生成，页面都应当照常显示（只是重一些），而不是裂图。
        """
        if not self.image:
            return ''
        return _thumb_url(self.image.name, self.image.url)


class Contribution(models.Model):
    """项目中的「我的角色与主要贡献」条目。"""

    project = models.ForeignKey(Project, related_name='contributions',
                                on_delete=models.CASCADE, verbose_name='所属项目')
    text = models.TextField('贡献描述')
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '主要贡献'
        verbose_name_plural = '主要贡献'

    def __str__(self):
        return self.text[:40]


class Metric(models.Model):
    """量化成果，例如 R²=0.804 / 20-20。"""

    project = models.ForeignKey(Project, related_name='metrics',
                                on_delete=models.CASCADE, verbose_name='所属项目')
    value = models.CharField('数值', max_length=40)
    label = models.CharField('说明', max_length=80)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '量化指标'
        verbose_name_plural = '量化指标'

    def __str__(self):
        return '{} — {}'.format(self.value, self.label)


class TechItem(models.Model):
    """技术栈 / 方法标签。"""

    project = models.ForeignKey(Project, related_name='techs',
                                on_delete=models.CASCADE, verbose_name='所属项目')
    name = models.CharField('技术 / 方法', max_length=60)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '技术标签'
        verbose_name_plural = '技术标签'

    def __str__(self):
        return self.name


class ProjectLink(models.Model):
    """项目相关链接（代码仓库 / 论文 / 演示）。"""

    KIND_CODE = 'code'
    KIND_PAPER = 'paper'
    KIND_DEMO = 'demo'
    KIND_OTHER = 'other'
    KIND_CHOICES = [
        (KIND_CODE, '代码仓库'),
        (KIND_PAPER, '论文 / 文档'),
        (KIND_DEMO, '在线演示'),
        (KIND_OTHER, '其他'),
    ]

    project = models.ForeignKey(Project, related_name='links',
                                on_delete=models.CASCADE, verbose_name='所属项目')
    kind = models.CharField('类型', max_length=10, choices=KIND_CHOICES, default=KIND_OTHER)
    label = models.CharField('链接文字', max_length=80)
    url = models.URLField('链接地址', blank=True)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '相关链接'
        verbose_name_plural = '相关链接'

    def __str__(self):
        return '{}: {}'.format(self.get_kind_display(), self.label)


# ==========================================================================
# 个人资料 / 荣誉 / 技能
# ==========================================================================
class Profile(models.Model):
    """个人简介单例（首页顶部与「关于」区块）。"""

    name = models.CharField('姓名', max_length=40)
    headline = models.CharField('求职定位', max_length=120, blank=True)
    tagline = models.CharField('一句话标语', max_length=160, blank=True)
    intro = models.TextField('Hero 简介', blank=True,
                             help_text='首页顶部的一句话介绍')
    about = models.TextField('整体介绍正文', blank=True,
                             help_text='「关于」区块正文，空行分段')
    phone = models.CharField('电话', max_length=40, blank=True)
    email = models.EmailField('邮箱', blank=True)
    city = models.CharField('城市', max_length=40, blank=True)

    class Meta:
        verbose_name = '个人资料'
        verbose_name_plural = '个人资料'

    def __str__(self):
        return self.name

    @property
    def about_paragraphs(self):
        """按空行切分成段落，供模板逐段渲染。"""
        return [p.strip() for p in self.about.split('\n\n') if p.strip()]


class Stat(models.Model):
    """首页 Hero 下方的统计数字。"""

    value = models.CharField('数值', max_length=30)
    label = models.CharField('说明', max_length=40)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '首页统计'
        verbose_name_plural = '首页统计'

    def __str__(self):
        return '{} {}'.format(self.value, self.label)


class ProfileFact(models.Model):
    """Hero 右侧 Quick Profile 卡片条目。"""

    ICON_BLUE = 'blue'
    ICON_TEAL = 'teal'
    ICON_VIOLET = 'violet'
    ICON_CHOICES = [
        (ICON_BLUE, '蓝色'),
        (ICON_TEAL, '青色'),
        (ICON_VIOLET, '紫色'),
    ]

    title = models.CharField('标题', max_length=80)
    subtitle = models.CharField('说明', max_length=200, blank=True)
    icon = models.CharField('配色', max_length=10, choices=ICON_CHOICES,
                            default=ICON_BLUE)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = 'Hero 资料卡'
        verbose_name_plural = 'Hero 资料卡'

    def __str__(self):
        return self.title


class Pillar(models.Model):
    """「关于」区块的三条项目主线。"""

    ICON_TEAL = 'teal'
    ICON_BLUE = 'blue'
    ICON_VIOLET = 'violet'
    ICON_CHOICES = [
        (ICON_TEAL, '青色'),
        (ICON_BLUE, '蓝色'),
        (ICON_VIOLET, '紫色'),
    ]

    title = models.CharField('主线名称', max_length=60)
    description = models.CharField('说明', max_length=200, blank=True)
    icon = models.CharField('配色', max_length=10, choices=ICON_CHOICES,
                            default=ICON_TEAL)
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '项目主线'
        verbose_name_plural = '项目主线'

    def __str__(self):
        return self.title


class Education(models.Model):
    """教育经历（首页时间线）。"""

    school = models.CharField('学校', max_length=100)
    degree = models.CharField('学历 / 专业', max_length=100)
    period = models.CharField('时间', max_length=40, blank=True)
    org = models.CharField('院系 / 联合培养单位', max_length=160, blank=True)
    description = models.TextField('说明', blank=True)
    highlights = models.TextField('关键词', blank=True,
                                  help_text='用中文或英文逗号分隔')
    order = models.PositiveIntegerField('排序', default=0,
                                        help_text='数字越小越靠前（最新的放前面）')

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '教育经历'
        verbose_name_plural = '教育经历'

    def __str__(self):
        return '{} · {}'.format(self.school, self.degree)

    @property
    def highlight_list(self):
        raw = self.highlights.replace('，', ',').replace('、', ',')
        return [x.strip() for x in raw.split(',') if x.strip()]


class Award(models.Model):
    """竞赛奖项与荣誉。"""

    title = models.CharField('奖项名称', max_length=160)
    detail = models.CharField('级别 / 说明', max_length=80, blank=True)
    icon = models.CharField('图标', max_length=8, default='🏆',
                            help_text='可直接填 emoji')
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '荣誉奖项'
        verbose_name_plural = '荣誉奖项'

    def __str__(self):
        return self.title


class SkillGroup(models.Model):
    """技能分组，条目用逗号分隔存放，便于快速维护。"""

    name = models.CharField('分组名称', max_length=60)
    items = models.TextField('技能条目', help_text='用中文或英文逗号分隔')
    order = models.PositiveIntegerField('排序', default=0)

    class Meta:
        ordering = ['order', 'id']
        verbose_name = '技能分组'
        verbose_name_plural = '技能分组'

    def __str__(self):
        return self.name

    @property
    def item_list(self):
        raw = self.items.replace('，', ',').replace('、', ',')
        return [x.strip() for x in raw.split(',') if x.strip()]
