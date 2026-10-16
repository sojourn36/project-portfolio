"""
Django settings — 项目展示界面（作品集）
基于 Django 3.2 / Python 3.8
"""

from pathlib import Path
import os

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

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

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

# 演示视频等上传文件
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.AutoField'

# 大文件上传（演示视频）
DATA_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024   # 200 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 200 * 1024 * 1024

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
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    # HSTS preload 指令：只有带上它，域名才能被提交到浏览器的预加载列表
    # （属强承诺，一旦收录撤销很慢）。不想用可设 DJANGO_HSTS_PRELOAD=0。
    SECURE_HSTS_PRELOAD = os.environ.get('DJANGO_HSTS_PRELOAD', '1') == '1'
    # 若前置了反向代理并已终止 TLS，可设 DJANGO_SECURE_SSL_REDIRECT=0 关闭
    SECURE_SSL_REDIRECT = os.environ.get('DJANGO_SECURE_SSL_REDIRECT', '1') == '1'
