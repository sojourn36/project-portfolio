# 上传路径改为「按项目分目录」：shots/<slug>/ 与 covers/<slug>-。
# 纯 upload_to 变更，不动数据库结构 —— 但 Django 仍要求一条迁移来记录字段定义。

from django.db import migrations, models
import showcase.models


class Migration(migrations.Migration):

    dependencies = [
        ('showcase', '0004_project_cover_image'),
    ]

    operations = [
        migrations.AlterField(
            model_name='project',
            name='cover_image',
            field=models.ImageField(blank=True, help_text='首页卡片封面。留空则自动取第一张实机截图，再退到演示动图；两者都无则不显示封面。用于「第一张截图不适合当封面」时手工指定。建议宽高比 2:1 左右（卡片是 172px 高的横条）。', null=True, upload_to=showcase.models._cover_upload_to, verbose_name='列表封面图（可选）'),
        ),
        migrations.AlterField(
            model_name='projectshot',
            name='image',
            field=models.ImageField(upload_to=showcase.models._shot_upload_to, verbose_name='图片'),
        ),
    ]
