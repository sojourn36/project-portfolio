"""showcase 自定义模板过滤器。"""

from django import template
from django.utils.text import Truncator

register = template.Library()

ELLIPSIS = '…'


@register.filter
def ellipsis(value, arg):
    """按字符数截断，并**强制**补上省略号。

    为什么不直接用内置的 ``truncatechars``
    ------------------------------------
    Django 3.2 的截断尾巴是走 ``pgettext('String to return when truncating text',
    '%(truncated_text)s…')`` 取的，**受当前语言影响**。而 zh-hans / zh-hant 的
    译文是空串，于是中文环境下：

        >>> from django.utils import translation
        >>> with translation.override('en'):
        ...     Truncator('abc').add_truncation_text('x')     # 'x…'
        >>> with translation.override('zh-hans'):
        ...     Truncator('abc').add_truncation_text('x')     # 'x'

    结果是 ``truncatechars`` 会**静默截断**：标题被砍掉一半却没有任何提示，
    读者根本看不出这里被截过。面包屑、相关推荐、翻页标题都中招。

    这个过滤器显式传 ``truncate='…'``，把尾巴钉死，不受语言影响。

    用法::

        {{ project.title|ellipsis:28 }}
    """
    try:
        length = int(arg)
    except (TypeError, ValueError):
        return value
    return Truncator(value).chars(length, ELLIPSIS)
