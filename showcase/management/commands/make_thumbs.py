"""为实机截图 / 卡片封面生成缩略图。

    python manage.py make_thumbs [--force] [--width 800] [--dry-run] [--prune]

为什么需要
----------
详情页图集卡片在 CSS 里是 ``height: 200px`` 的小图，但 ``<img src>`` 原先直接
用原图 —— **拿原图当缩略图渲染**。线上实测（滚完整页）：

    /project/yolov8-detection-desktop/      797 KB，其中 556 KB（70%）
                                            是一张用来渲染 200px 缩略图的原图
    /project/femnsic-fatigue-optimization/  823 KB，其中 770 KB 是 PNG

而真正需要全尺寸的只有「点击查看原图」那一个入口。

编码怎么选、宽度取多少、什么时候干脆不生成 —— 这三件事的判断依据与实测数据
都写在 ``showcase/thumbs.py`` 的 ``build()`` 里。本命令只负责「遍历 + 汇报」，
与**后台保存时调用的是同一个函数**，不存在两套逻辑各自漂移的可能。

什么时候要跑
------------
批量换图、或者从别人那里拿到一份 ``media/`` 之后。日常在后台单张上传时，
``ProjectAdmin.save_related()`` 已经顺手生成了，不需要再手动跑。

为什么缩略图要提交进仓库
------------------------
不放在部署时生成。理由与 ``showcase/media.py`` 里那条一样：本地与线上必须
看到同一份东西。部署时才生成的话，本地 ``runserver`` 会回退到原图，
于是「本地好好的、上线才发现不一样」—— 那正是要避免的差异。
源图换了记得重跑本命令（``--force``）。
"""

from django.core.management.base import BaseCommand

from showcase.models import Project, ProjectShot
from showcase.thumbs import DEFAULT_WIDTH, build


class Command(BaseCommand):
    help = '为实机截图与卡片封面生成缩略图（详情页图集 / 首页卡片用）'

    # 源图可能的扩展名。``--prune`` 用它判断「源图还在不在」。
    SOURCE_EXTS = ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp')

    def add_arguments(self, parser):
        parser.add_argument('--force', action='store_true',
                            help='已存在也重新生成（源图换过时用）')
        parser.add_argument('--width', type=int, default=DEFAULT_WIDTH,
                            help='缩略图最大宽度，默认 %d' % DEFAULT_WIDTH)
        parser.add_argument('--dry-run', action='store_true',
                            help='只报告会生成什么，不写文件')
        parser.add_argument('--prune', action='store_true',
                            help='顺便删掉「源图已经不在了」的孤儿缩略图')

    def handle(self, *args, **opts):
        if opts['prune']:
            n = self._prune(opts['dry_run'])
            self.stdout.write('孤儿缩略图 %d 个%s' % (
                n, '（--dry-run，未删）' if opts['dry_run'] and n else ''))
            self.stdout.write('')

        # 两处都要缩略图：
        #   · ProjectShot.image —— 详情页图集网格（卡片 ~350–360px 宽）
        #   · Project.cover_image —— 首页列表卡片封面（~350px 宽）
        # 不处理 demo_image：它兼作 <video poster>，需要按视频宽度显示，
        # 800px 的缩略图对它偏小。
        sources = []
        for shot in (ProjectShot.objects.exclude(image='')
                     .select_related('project').order_by('project__slug', 'order', 'id')):
            sources.append(('截图', shot.image.name))
        for project in Project.objects.exclude(cover_image='').order_by('slug'):
            sources.append(('卡片封面', project.cover_image.name))

        if not sources:
            self.stdout.write('没有可处理的图片。')
            return

        total_before = total_after = 0
        counts = {'made': 0, 'reused': 0, 'missing': 0, 'kept': 0}

        for label, name in sources:
            state, before, after = build(name, width=opts['width'],
                                         force=opts['force'],
                                         dry_run=opts['dry_run'])
            counts[state] += 1
            total_before += before
            total_after += after

            if state == 'missing':
                self.stdout.write(self.style.WARNING('  跳过（源图不存在）: %s' % name))
            elif state == 'reused':
                continue
            elif state == 'kept':
                self.stdout.write('  [%s] %-52s %6.0f KB ->  用原图（缩略图反而更大）' % (
                    label, name, before / 1024))
            else:
                self.stdout.write('  [%s] %-52s %6.0f KB -> %5.0f KB  %s' % (
                    label, name, before / 1024, after / 1024,
                    '(dry-run)' if opts['dry_run'] else ''))

        self.stdout.write('')
        self.stdout.write('生成 %d 张 / 复用 %d 张 / 源图缺失 %d 张 / 源图已足够小 %d 张'
                          % (counts['made'], counts['reused'],
                             counts['missing'], counts['kept']))
        if total_before:
            # 措辞刻意是「页面需传」而不是「缩略图总量」：标记为「源图已足够小」
            # 的那些最终是按**原图**发出去的，把它们漏掉会把这个数字说小。
            self.stdout.write('页面需传 %.0f KB（原图合计 %.0f KB，省 %.0f%%）' % (
                total_after / 1024, total_before / 1024,
                100 * (1 - total_after / total_before)))

    def _prune(self, dry_run):
        """删掉「源图已经不在了」的孤儿缩略图，返回处理个数。

        为什么是**显式开关**而不是「删记录时自动删」：曾经在
        ``ProjectShot`` 上挂过 ``post_delete`` 信号去删缩略图，结果它把**真实**
        文件删了 —— 测试里有一条「清空 delivery 分类验证空态」的用例，级联删除
        截图时信号照常触发，而那个测试类用的是真实 ``MEDIA_ROOT``，
        于是跑一次测试，仓库里就少一张图。

        教训：把「删数据」和「删文件」绑在一起很危险，因为删数据的场景
        （测试、重置种子、导入脚本）远比想象的多。Django 自己不在 delete 时
        删文件，就是这个原因。孤儿缩略图只是浪费几百 KB，误删是真丢东西 ——
        两者不对等，所以清理必须是**有人明确要求**的动作。
        """
        import os

        from django.conf import settings

        from showcase.thumbs import THUMB_PREFIX

        root = os.path.join(settings.MEDIA_ROOT, THUMB_PREFIX)
        if not os.path.isdir(root):
            return 0

        pruned = 0
        for dirpath, _dirs, files in os.walk(root):
            for filename in files:
                path = os.path.join(dirpath, filename)
                rel = os.path.relpath(path, settings.MEDIA_ROOT).replace(os.sep, '/')
                stem = os.path.splitext(rel[len(THUMB_PREFIX):])[0]
                # 只按「源图文件是否还在」判断，不去看数据库 —— 库里没有但文件还在，
                # 说明可能正要重新导入种子数据，那种不该删。
                if any(os.path.isfile(os.path.join(settings.MEDIA_ROOT, stem + e))
                       for e in self.SOURCE_EXTS):
                    continue
                pruned += 1
                self.stdout.write('  清理孤儿缩略图: %s' % rel)
                if not dry_run:
                    os.remove(path)
        return pruned
