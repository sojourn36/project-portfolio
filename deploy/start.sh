#!/usr/bin/env bash
#
# 部署启动脚本 —— 在「单端口 HTTP 服务」环境里把作品集跑起来。
#
# 为什么要有这个文件
# ------------------
# 生产模式的启动涉及七八个环境变量（DEBUG / ALLOWED_HOSTS / HSTS / 媒体托管…），
# 靠部署时现敲一串临时变量既容易漏、也没法本地复现。这里把它固化下来，
# 本地想验证生产模式直接跑同一个脚本即可。
#
# 用法
# ----
#     PORT=8000 bash deploy/start.sh
#
# 依赖：Django / Pillow / whitenoise / gunicorn（见 requirements.txt）
set -euo pipefail

cd "$(dirname "$0")/.."

# 有的环境只有 python3，有的只有 python
PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if command -v python3 >/dev/null 2>&1; then PY=python3; else PY=python; fi
fi

export DJANGO_DEBUG="${DJANGO_DEBUG:-0}"
export DJANGO_ALLOWED_HOSTS="${DJANGO_ALLOWED_HOSTS:-*}"

# 前置反向代理已终止 TLS：Django 自己不要再做 http → https 跳转。
# 开着它而代理又没转发原始协议时，会造成 301 死循环。
export DJANGO_SECURE_SSL_REDIRECT="${DJANGO_SECURE_SSL_REDIRECT:-0}"

# HSTS 一旦被浏览器记住，在到期前撤不掉。域名还没最终定下来时先关着。
export DJANGO_HSTS_SECONDS="${DJANGO_HSTS_SECONDS:-0}"

# 单端口部署、前面没有 Nginx，/media/ 下的演示视频与截图交给 Django 自己发。
export DJANGO_SERVE_MEDIA="${DJANGO_SERVE_MEDIA:-1}"

# 站点绝对地址（og:url / og:image / sitemap 用）。留空则回退到请求域名，
# 部署域名确定后建议注入，例：DJANGO_SITE_URL=https://xxx.example.com
export DJANGO_SITE_URL="${DJANGO_SITE_URL:-}"

# 密钥不写进仓库：没注入就现场生成一个。
# 本项目没有登录功能，重启换钥匙没有副作用。
if [ -z "${DJANGO_SECRET_KEY:-}" ]; then
  export DJANGO_SECRET_KEY="$("$PY" -c \
    'from django.core.management.utils import get_random_secret_key as g; print(g())')"
fi

echo "[i] migrate"
"$PY" manage.py migrate --noinput

# 数据库为空（例如 db.sqlite3 没跟着传上来）时补一次种子数据，否则页面会是空的
COUNT="$("$PY" manage.py shell -c \
  'from showcase.models import Project; print(Project.objects.count())' 2>/dev/null | tail -1)"
if [ "${COUNT:-0}" = "0" ]; then
  echo "[i] 数据库为空，导入种子数据"
  "$PY" manage.py seed_projects
fi

echo "[i] collectstatic"
"$PY" manage.py collectstatic --noinput >/dev/null

# 逃生口：gunicorn 跑不了 Windows，本地想验证「生产模式」时
# 可以用它换成 runserver（记得加 --insecure，否则 DEBUG=0 下不发静态文件）：
#     SERVER_CMD="python manage.py runserver 0.0.0.0:8000 --insecure" bash deploy/start.sh
if [ -n "${SERVER_CMD:-}" ]; then
  echo "[i] 使用自定义启动命令：$SERVER_CMD"
  # shellcheck disable=SC2086
  exec $SERVER_CMD
fi

echo "[i] 启动 gunicorn，监听 0.0.0.0:${PORT:-8000}"
exec gunicorn config.wsgi:application \
  --bind "0.0.0.0:${PORT:-8000}" \
  --workers "${WEB_CONCURRENCY:-2}" \
  --threads 2 \
  --timeout 120 \
  --access-logfile - \
  --error-logfile -
