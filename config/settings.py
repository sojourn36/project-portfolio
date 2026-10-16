"""
Django settings — 项目展示界面（作品集）
基于 Django 3.2 / Python 3.8
"""

import importlib.util
import os
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------------
# 基础
# --------------------------------------------------------------------------
# 本地开发用占位值；生产环境请通过环境变量 DJANGO_SECRET_KEY 注入
SECRET_KEY = os.environ.get(
    'DJANGO_SECRET_KEY',
    'django-insecure-portfolio-showcase-local-dev-only-key',
)

# 本地演示用；部署时通过环境变量 DJANGO_ALLOWED_HOSTS 注入（逗号分隔）
# testserver 供 Django 测试客户端使用
ALLOWED_HOSTS = [
    h.strip() for h in os.environ.get(
        'DJANGO_ALLOWED_HOSTS',
        '127.0.0.1,localhost,0.0.0.0,testserver',
    ).split(',') if h.strip()
]

# 生产环境请设置 DJANGO_DEBUG=0
DEBUG = os.environ.get('DJANGO_DEBUG', '1') == '1'

# --------------------------------------------------------------------------
# 应用
# --------------------------------------------------------------------------
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    # 本项目
    'showcase',
]

def _build_middleware():
    """组装 MIDDLEWARE 链，按「是否装了 whitenoise」决定插不插静态文件中间件。

    为什么要这样写：本地开发环境（Anaconda python38 + Django 3.2）没有
    whitenoise 也能正常跑，而部署环境会从 requirements.txt 把它装上。
    硬写 'whitenoise.middleware.WhiteNoiseMiddleware' 的话，
    没装的机器一启动就 ModuleNotFoundError。
    """
    chain = ['django.middleware.security.SecurityMiddleware']
    if importlib.util.find_spec('whitenoise') is not None:
        # 紧跟 SecurityMiddleware：让应用自己在单端口内托管 /static/，
        # 部署时不必再挂一个 Nginx 只为发静态文件。
        chain.append('whitenoise.middleware.WhiteNoiseMiddleware')
    chain += [
        'django.contrib.sessions.middleware.SessionMiddleware',
        'django.middleware.common.CommonMiddleware',
        'django.middleware.csrf.CsrfViewMiddleware',
        'django.contrib.auth.middleware.AuthenticationMiddleware',
        'django.contrib.messages.middleware.MessageMiddleware',
        'django.middleware.clickjacking.XFrameOptionsMiddleware',
        # 放在链尾：响应阶段它是**最先**跑的那个，随后外层中间件（如
        # XFrameOptionsMiddleware）仍有机会调整自己的头，互不干扰。
        'showcase.middleware.ContentSecurityPolicyMiddleware',
    ]
    return chain


MIDDLEWARE = _build_middleware()

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                # 分享卡片需要的绝对地址（og:url / og:image）
                'showcase.context_processors.site_meta',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --------------------------------------------------------------------------
# 数据库
# --------------------------------------------------------------------------
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# --------------------------------------------------------------------------
# 密码校验（本项目无用户注册，保留默认）
# --------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# --------------------------------------------------------------------------
# 国际化
# --------------------------------------------------------------------------
LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'
USE_I18N = True
USE_L10N = True
USE_TZ = True

# --------------------------------------------------------------------------
# 静态文件与媒体文件
# --------------------------------------------------------------------------
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

# WhiteNoise：装了才生效（见 _build_middleware）。
# 这两个开关是为「部署到单端口沙箱、不方便先跑 collectstatic」准备的 ——
# 直接走 staticfiles finders 从 STATICFILES_DIRS 找文件。
# 正式上 Nginx / CDN 的部署请关掉它们，改跑 collectstatic。
WHITENOISE_USE_FINDERS = os.environ.get('DJANGO_WHITENOISE_FINDERS', '0') == '1'
WHITENOISE_AUTOREFRESH = WHITENOISE_USE_FINDERS

# 演示视频等上传文件
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# 由 Django 自己托管 /media/。默认只在 DEBUG 下开（见 config/urls.py）；
# 部署到单端口沙箱、前面没有 Nginx 时需要显式打开。
SERVE_MEDIA = os.environ.get('DJANGO_SERVE_MEDIA', '0') == '1'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# 大文件上传（演示视频）
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024   # 200 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024

# --------------------------------------------------------------------------
# 内容安全策略（CSP）
# --------------------------------------------------------------------------
# 为什么需要它，见 showcase/middleware.py 的模块文档 —— 一句话版本：
# 发布平台会在网关层往 HTML 里注入一段腾讯 Beacon 埋点（上报 url/referrer/title），
# 代码不在本仓库里、grep 不到，只能靠浏览器侧的 CSP 拦。
# script-src 'self' 同时挡住它的外链段（跨域）和内联段（无 nonce）。
#
# DJANGO_CSP=0 可整体关掉（排查「页面某处不生效」时用来快速二分）。
CSP_ENABLED = os.environ.get('DJANGO_CSP', '1') == '1'
# /admin/ 豁免：它不是对外面，加 CSP 零收益；且后台大量用 style= 内联样式，
# 严格策略会打坏它。豁免是刻意的（理由与实测依据见 showcase/middleware.py）。
CSP_EXEMPT_PREFIXES = ('/admin/',)

# --------------------------------------------------------------------------
# 站点绝对地址（社交分享卡片 og:url / og:image / sitemap.xml 用）
# --------------------------------------------------------------------------
# 例：DJANGO_SITE_URL=https://portfolio.example.com
# 留空则回退到「当前请求的绝对地址」——本地开发够用，但**上线后请显式配置**：
# 反向代理后面 request.build_absolute_uri() 可能拿到内网 IP 或 http。
SITE_URL = os.environ.get('DJANGO_SITE_URL', '').rstrip('/')

# --------------------------------------------------------------------------
# 生产环境安全项（DJANGO_DEBUG=0 时自动生效）
# --------------------------------------------------------------------------
if not DEBUG:
    SECURE_CONTENT_TYPE_NOSNIFF = True
    # SECURE_BROWSER_XSS_FILTER 在 Django 4.0 已被移除（现代浏览器不需要它了）。
    # 只在旧版本上设置，免得在 4.x / 5.x 上凭空多一条无意义的告警。
    if django.VERSION < (4, 0):
        SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'

    # 反向代理终止 TLS 时，代理会用这个头告诉 Django「原始请求是 https」。
    # 不配它的话 request.is_secure() 永远是 False，
    # 一旦开了 SECURE_SSL_REDIRECT 就会 301 → 301 死循环。
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # HSTS：告诉浏览器「以后这个域名只准走 https」。
    # 注意 SECURE_HSTS_SECONDS 一旦被浏览器记住，在到期前**撤不掉**。
    # 因此绑到环境变量上，域名还没定下来时可以先设 0 关掉。
    SECURE_HSTS_SECONDS = int(os.environ.get('DJANGO_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
    # HSTS preload 指令：只有带上它，域名才能被提交到浏览器的预加载列表
    # （属强承诺，一旦收录撤销很慢）。不想用可设 DJANGO_HSTS_PRELOAD=0。
    SECURE_HSTS_PRELOAD = (
        SECURE_HSTS_SECONDS > 0
        and os.environ.get('DJANGO_HSTS_PRELOAD', '1') == '1'
    )

    # 若前置了反向代理并已终止 TLS，可设 DJANGO_SECURE_SSL_REDIRECT=0 关闭。
    # 没配 SECURE_PROXY_SSL_HEADER 而代理又没转发原始协议时，
    # 开着它会造成重定向死循环 —— 拿不准就先关。
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'
