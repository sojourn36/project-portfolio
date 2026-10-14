<div align="center">

# 项目作品集 · Project Portfolio

**一个用 Django 构建的个人项目作品集网站**

从业务问题拆解 → 数据 / 算法方案 → 模型验证 → 可视化与交互交付

<sub>AI × 新材料研发 ｜ 轨道交通智能系统 ｜ 视觉智能与系统交付</sub>

</div>

---

## 项目截图

<p align="center">
  <img src="docs/screenshots/home-desktop.png" width="100%" alt="首页：Hero、Quick Profile、统计数字、整体介绍与教育背景">
</p>

<p align="center">
  <img src="docs/screenshots/home-projects.png" width="100%" alt="项目列表：按方向分类的卡片网格">
</p>

<p align="center">
  <img src="docs/screenshots/project-detail.png" width="100%" alt="项目详情页：演示视频、介绍、贡献、指标与翻页">
</p>

<p align="center">
  <img src="docs/screenshots/home-mobile.png" width="42%" alt="移动端首页">
</p>

---

## 功能特性

- **完整介绍页** — 首页一次性呈现个人定位、整体介绍、项目主线、教育背景、项目列表、
  荣誉与技能，导航锚点可直达各区块。
- **项目详情页** — 每个项目独立页面，包含完整介绍、我的角色与主要贡献、量化指标、
  技术栈、相关链接，以及**可播放的演示视频**。
- **三种演示素材自动降级** — 本地视频文件 → 外部嵌入链接 → GIF 动图 → 占位提示，
  按优先级自动选择渲染方式，缺素材也不会破版。
- **分类筛选** — 项目按「AI × 材料 / 轨道交通 / 视觉 · 人机交互 / 系统交付」四类组织，
  支持 URL 参数筛选（`?category=materials`），可分享具体筛选结果。
- **数据全部后台可维护** — 项目、贡献点、指标、技术栈、链接、首页各区块文案
  均在 Django Admin 中维护，无需改代码；项目下的四类明细用内联表格批量编辑。
- **响应式布局** — 桌面端 / 平板 / 移动端三档断点，移动端为汉堡菜单 + 单列布局。
- **零前端依赖** — 原生 HTML / CSS / JavaScript，无框架、无 CDN，**可完全离线运行**。
- **19 项自动化测试** — 覆盖首页各区块、分类筛选与非法参数回退、空态提示、
  6 个详情页渲染、视频嵌入、翻页与同类推荐、404、后台登录保护。

---

## 技术栈

| 层次 | 选型 |
|---|---|
| 后端框架 | Django 3.2（LTS） |
| 语言 / 运行时 | Python 3.8+ |
| 数据库 | SQLite（开箱即用，可平滑换 PostgreSQL） |
| 模板 | Django Template Language |
| 前端 | 原生 HTML5 / CSS3（变量 + Grid + Flex）/ ES6，无任何第三方依赖 |
| 媒体服务 | Django `MEDIA_URL` / `MEDIA_ROOT` 静态媒体托管 |
| 测试 | Django `TestCase` |

---

## 快速开始

```bash
# 1. 克隆
git clone <仓库地址>
cd project-portfolio

# 2. 创建虚拟环境（推荐）
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. 安装依赖
pip install -r requirements.txt

# 4. 建库
python manage.py migrate

# 5. 导入作品集数据（6 个项目 + 首页各区块 + 荣誉 + 技能）
python manage.py seed_projects

# 6. 启动
python manage.py runserver
```

打开 <http://127.0.0.1:8000/>

> **关于数据**：`db.sqlite3` 未纳入版本库。执行 `migrate` + `seed_projects` 后，
> 网站内容与演示素材即可完整复现。
> 如需重置数据：`python manage.py seed_projects --reset`

### 进入后台管理

```bash
python manage.py createsuperuser
```

登录 <http://127.0.0.1:8000/admin/> 即可维护全部内容。

---

## 项目结构

```text
project-portfolio/
├── manage.py
├── requirements.txt
├── config/                          # 项目配置
│   ├── settings.py                  # 模板 / 静态 / 媒体 / 中文 / 上传上限 / 生产安全项
│   ├── urls.py                      # 路由入口（含媒体文件服务）
│   ├── asgi.py
│   └── wsgi.py
├── showcase/                        # 核心应用
│   ├── models.py                    # 数据模型
│   ├── views.py                     # home() 首页聚合 + detail() 详情页
│   ├── urls.py                      # 应用路由（app_name = showcase）
│   ├── admin.py                     # 后台管理（项目含 4 个内联表）
│   ├── tests.py                     # 19 项冒烟测试
│   ├── migrations/
│   ├── management/commands/
│   │   └── seed_projects.py         # 数据导入命令（支持 --reset）
│   └── templates/showcase/
│       ├── base.html                # 公共骨架（导航锚点 / 页脚联系）
│       ├── home.html                # 首页
│       └── detail.html              # 详情页
├── static/
│   ├── css/style.css                # 全部样式（含响应式断点）
│   └── js/main.js                   # 移动端菜单 / 滚动状态 / 回到顶部
├── media/
│   ├── videos/                      # 演示视频（mp4）
│   └── demos/                       # 演示动图（gif）
└── docs/screenshots/                # 界面截图
```

---

## 路由

| 地址 | 视图 | 说明 |
|---|---|---|
| `/` | `showcase:home` | 首页，列出全部项目与各介绍区块 |
| `/?category=<key>` | `showcase:home` | 按分类筛选 |
| `/project/<slug>/` | `showcase:detail` | 项目详情页（含演示视频、翻页、同类推荐） |
| `/admin/` | Django Admin | 后台管理 |

分类键：`materials`（AI × 材料）、`transit`（轨道交通）、
`vision`（视觉 · 人机交互）、`delivery`（系统交付）。

---

## 首页区块与数据来源

| 区块 | 锚点 | 数据模型 |
|---|---|---|
| Hero 标语 / 简介 | — | `Profile.tagline` / `Profile.intro` |
| Quick Profile 资料卡 | — | `ProfileFact` |
| 统计数字条 | — | `Stat` |
| 整体介绍 | `#about` | `Profile.about`（空行分段） |
| 项目主线 | `#about` | `Pillar` |
| 教育背景 | `#education` | `Education` |
| 项目经历 | `#projects` | `Project`（+ 贡献 / 指标 / 技术栈 / 链接） |
| 荣誉奖项 | `#awards` | `Award` |
| 技能清单 | `#skills` | `SkillGroup` |
| 联系方式 | `#contact` | `Profile.phone` / `email` / `city` |

---

## 数据模型

```text
Profile (单例：Hero + 关于 + 联系方式)
Stat / ProfileFact / Pillar / Education          # 首页展示区块
Award / SkillGroup                               # 荣誉 / 技能

Project ──┬── Contribution (贡献点)
          ├── Metric       (量化指标)
          ├── TechItem     (技术栈)
          └── ProjectLink  (相关链接)
```

`Project` 的演示素材有三个字段，详情页按优先级自动选择：

1. `video_file` → HTML5 `<video>` 播放器（本地文件）
2. `video_external_url` → `<iframe>` 嵌入（B站 / YouTube 等）
3. `demo_image` → GIF 动图
4. 都没有 → 「演示视频待补充」占位提示

**当前素材情况：**

| 项目 | 演示素材 |
|---|---|
| ExperimentPilot AI | 演示动图（GIF） |
| 目标检测桌面系统 | 演示视频（mp4） |
| FeMnSiC / Subway / 学生行为画像 / 手势交互 | 待补充 |

补充方式：把视频放进 `media/videos/`，在后台对应项目的「演示视频」字段选择该文件。

---

## 后台管理

登录 `/admin/` 后可：

- 维护项目基本信息、完整介绍、角色与时间；
- 通过**内联表格**直接编辑该项目的贡献点、量化指标、技术栈、相关链接；
- 上传 / 替换**演示视频**、填**外部视频链接**、或上传**演示动图**；
- 维护首页各区块：`Stat`（统计数字）、`ProfileFact`（资料卡）、
  `Pillar`（项目主线）、`Education`（教育经历，关键词用逗号分隔）；
- 维护个人资料（单例，含 `about` 正文）、荣誉奖项、技能分组。

---

## 测试

```bash
python manage.py test showcase -v 2
```

覆盖范围：seed 数据完整性、模型属性（分段 / 关键词拆分）、首页各锚点渲染、
分类筛选与非法分类回退、空态提示、6 个详情页渲染、视频嵌入、翻页与同类推荐、
404、后台登录保护。

---

## 响应式断点

| 断点 | 适配 |
|---|---|
| `> 980px` | 桌面端：Hero 双栏、详情页双栏（主内容 + 侧栏吸顶） |
| `≤ 980px` | 平板：Hero / 关于 / 详情页转单栏，统计条两列 |
| `≤ 720px` | 移动端：汉堡菜单、单列卡片、统计条单列、时间线收窄 |
| `≤ 400px` | 小屏：指标 / 卡片指标单列 |

---

## 部署

生产环境注意事项：

1. **注入环境变量**（不要把密钥写进代码）：

   | 变量 | 说明 |
   |---|---|
   | `DJANGO_SECRET_KEY` | 密钥，务必更换 |
   | `DJANGO_DEBUG` | 设为 `0` 关闭调试 |
   | `DJANGO_ALLOWED_HOSTS` | 逗号分隔的域名列表 |
   | `DJANGO_SECURE_SSL_REDIRECT` | 已由反向代理终止 TLS 时设为 `0` |

   `DJANGO_DEBUG=0` 时会自动启用 HSTS、Secure Cookie、`X_FRAME_OPTIONS=DENY` 等安全项。

2. **收集静态文件**：`python manage.py collectstatic`

3. **换用生产数据库**：把 `DATABASES` 切到 PostgreSQL 等，并重新执行 `migrate` + `seed_projects`。

4. **媒体与静态文件**由 Nginx / 对象存储托管，不要让 Django 在 `DEBUG=False` 下直接服务。

---

## 说明

- 本项目为**个人作品集展示**用途。仓库内的 `SECRET_KEY` 为开发占位值，
  生产部署请务必通过环境变量替换。
- 演示视频文件约 15 MB，直接纳入版本库以便克隆后即可播放；
  如需瘦身可改用 Git LFS 或改为外部视频链接（`video_external_url`）。
- 若本机设置了系统代理，访问 `127.0.0.1` 可能被代理拦截返回 502，
  需将 `127.0.0.1,localhost` 加入 `NO_PROXY` 环境变量（curl 可用 `--noproxy '*'`）。
