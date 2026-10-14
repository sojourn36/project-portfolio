"""导入作品集初始数据。

用法::

    python manage.py seed_projects          # 已有数据则跳过
    python manage.py seed_projects --reset  # 清空后重建

数据来源：简历 PDF + 项目代码与验收文档（均为真实数据，未做夸大）。
"""

import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from showcase.models import (
    Award, Contribution, Education, Metric, Pillar, Profile, ProfileFact,
    Project, ProjectLink, ProjectShot, SkillGroup, Stat, TechItem,
)


# ==========================================================================
# 实机素材：media/ 下已归集的运行产出（由 portfolio/collect_media.py 统一复制）
# 这里只写相对路径，不复制文件本体。
# ==========================================================================
def _media_exists(media_root, rel):
    """判断 media/ 下是否已存在该相对路径的文件。"""
    return bool(rel) and os.path.exists(
        os.path.join(media_root, rel.replace('/', os.sep)))


def _attach(project, field, target, source, media_root):
    """把素材挂到字段上：优先用 media/ 下已归集的成品，其次回退到源文件。

    只写相对路径、不复制文件——媒体本体由 collect_media.py 归集。
    """
    if not target:
        return False
    if not (_media_exists(media_root, target)
            or (source and os.path.exists(source))):
        return False
    setattr(project, field, target)
    project.save(update_fields=[field])
    return True


PROJECTS = [
    # ------------------------------------------------------------------
    # 1. ExperimentPilot AI
    # ------------------------------------------------------------------
    {
        'title': 'ExperimentPilot AI ｜ 本地科研 RAG 与冻结专家模型智能体',
        'slug': 'experimentpilot-ai',
        'badge': 'EP',
        'category': Project.CATEGORY_MATERIALS,
        'role': '核心课题负责人 / 独立开发',
        'period': '2024.09 – 2026.08',
        'order': 1,
        'is_featured': True,
        'summary': '面向材料研发中的文献检索、数据溯源与模型调用需求，构建完全本地运行的科研助手：'
                   '支持 PDF / Word / Excel 及扫描件 OCR 解析，把「结构化数据—文献语义证据—专家模型预测」'
                   '三类来源分层编排，避免大模型编造科研数值。',
        'intro': '这是一个完全本地运行的科研助手，面向材料研发中的文献检索、数据溯源与模型调用需求。\n\n'
                 '系统把三类来源严格分层：只读 SQLite 中的结构化文献数据、Chroma + Qwen3:4B 的语义检索证据、'
                 '以及封装为独立服务的冻结专家模型预测。大模型只负责理解问题与组织有证据的文本，'
                 '所有寿命数值都必须来自经哈希锁定的专家模型，从机制上杜绝"模型预测冒充实验结果"。\n\n'
                 '系统支持 PDF、Word、Excel 及扫描件 OCR 的批量解析入库，并提供受控编排层把三类来源组合成'
                 '可追溯的调查结果；证据与预测分层展示，越界成分会被直接拒绝。',
        'video_caption': '演示动图：本地文献 RAG 与专家模型的受控编排流程（确定性演示，非实时录屏）。',
        'demo_source': r'D:\pycharm\RAG\ExperimentPilot_AI\docs\assets\experimentpilot_demo.gif',
        'demo_target': 'demos/experimentpilot-demo.gif',
        'contributions': [
            '设计「SQLite 结构化数据 — Chroma/Qwen3 文献证据 — FastAPI 专家预测」三层编排，'
            '实现溯源问答、适用域（AD）判断与越界拒绝。',
            '把冻结的 Fe–Mn–Si–C 低周疲劳 XGBoost 专家模型封装为本机 API，通过确定性成分解析 + '
            '适用域检查 + 模型身份哈希，从机制上杜绝 LLM 直接生成寿命数值。',
            '设计 20 题语义与安全评测，覆盖字段命中、复合意图、引用完整性、无证据拒答、'
            '风险符号降级与越界预测；真实环境达到 20/20。',
            '建立哈希冻结清单、离线预检与一键验收流程，保证「无训练、无数据库写回、无自动实验控制」的科研边界。',
        ],
        'metrics': [
            ('20 / 20', '固定评测集通过率'),
            ('102 passed', '全项目回归测试'),
            ('4.187 s', '响应延迟 P50'),
            ('100% 本地', '断网可运行'),
        ],
        'techs': ['Python', 'RAG', 'Chroma', 'Ollama / Qwen3:4B', 'FastAPI',
                  'SQLite', 'Streamlit', 'PyMuPDF / Docling', '哈希冻结与可审计设计'],
        'links': [
            (ProjectLink.KIND_OTHER, '冻结编号 DAY6_6_FROZEN_20260831', ''),
            (ProjectLink.KIND_PAPER, '架构文档 / 答辩材料 / 演示 GIF', ''),
        ],
        'shots': [
            ('shots/experimentpilot-ai/01-structured-records.png', ProjectShot.KIND_UI,
             '结构化文献查询：只读 SQLite 主表、不接受自由 SQL；本次命中 17 条记录，'
             '可靠 17 条 / 待复核 0 条，每条记录都带来源文献可追溯。'),
            ('shots/experimentpilot-ai/02-expert-prediction.png', ProjectShot.KIND_RESULT,
             '冻结 FeMnSiC 专家模型推理：Mn 28.40 / Si 3.10 / C 0.30 → 预测寿命 11,875 cycles，'
             '适用域 CORE、AD 距离 0.457；界面明确标注「这是冻结模型预测，不是实验结果」。'),
            ('shots/experimentpilot-ai/03-quality-eval.png', ProjectShot.KIND_RESULT,
             '20 题固定评测集真实运行：通过 20/20（100.0%），响应延迟 P50 4.19 s、P95 13.47 s。'),
        ],
    },

    # ------------------------------------------------------------------
    # 2. FeMnSiC
    # ------------------------------------------------------------------
    {
        'title': 'FeMnSiC 阻尼钢 ｜ 小样本低周疲劳寿命预测与主动学习成分优化',
        'slug': 'femnsic-fatigue-optimization',
        'badge': 'Fe',
        'category': Project.CATEGORY_MATERIALS,
        'role': '核心研究 / 模型与算法实现',
        'period': '2024.09 – 2026.08',
        'order': 2,
        'is_featured': True,
        'summary': '针对 Fe–Mn–Si–C 合金低周疲劳寿命（LCF）预测与成分设计这一典型小样本材料设计问题，'
                   '构建「预测 + 反向优化」闭环，用少量实验数据支撑成分决策，'
                   '并严格区分模型预测与实验验证。',
        'intro': '硕士核心课题。研究对象是 Fe–Mn–Si–C 合金的低周疲劳寿命（LCF），'
                 '实验固定条件为应变幅 ±1%、加载频率 0.2 Hz，属于典型的小样本材料设计场景。\n\n'
                 '技术路线包含三条主线：一是把材料机理知识注入特征工程，构建物理启发特征（成分、Ceq、'
                 '层错能 SFE 代理、交互项）；二是设计多目标变换集成模型 POWER-XGB V4，'
                 '用 2 套特征空间 × 4 种寿命变换形成 8 个配方并做软加权集成；'
                 '三是搭建主动学习闭环，按 33 → 38 → 43 → 46 条数据的冻结链迭代"预测—验证—更新"。\n\n'
                 '为降低小样本外推风险，引入 CORE 适用域过滤，并用差分进化、贝叶斯优化、栅格搜索'
                 '三种算法交叉验证候选稳定性，最终得到跨模型稳定的双脊线候选结构。',
        'contributions': [
            '构建物理启发特征体系：Mn / Si / C 成分、Ceq、层错能（SFE）代理、交互项等，'
            '把材料机理知识注入特征工程。',
            '设计多目标变换集成模型 POWER-XGB V4：2 套特征空间 × 4 种寿命变换形成 8 个配方，'
            '外层 LOHO 内以 3 折 OOF 误差软加权。',
            '搭建主动学习闭环（33 → 38 → 43 → 46 条数据冻结链）：候选预测 → 实验验证 → 数据更新 → 再训练。',
            '引入 CORE 适用域（AD）过滤降低小样本外推风险；用差分进化 / 贝叶斯优化 / 栅格'
            '三算法交叉验证候选稳定性。',
        ],
        'metrics': [
            ('R² 0.804', '决定系数'),
            ('1442.9 cyc', 'RMSE'),
            ('1101.1 cyc', 'MAE'),
            ('29.52%', 'MAPE'),
        ],
        'techs': ['XGBoost', 'SVR / NuSVR', 'ExtraTrees', 'Physics-MLP', '主动学习',
                  '贝叶斯优化', '差分进化', '物理启发特征', '适用域 (AD)', 'nested-LOHO'],
        'links': [
            (ProjectLink.KIND_OTHER, '闭环迭代 33 → 38 → 43 → 46 条冻结数据', ''),
            (ProjectLink.KIND_OTHER, '跨模型稳定双脊线候选结构', ''),
        ],
        'shots': [
            ('shots/femnsic-fatigue-optimization/01-predicted-vs-measured.png',
             ProjectShot.KIND_FIGURE,
             '加权集成模型在留一交叉验证（LOOCV）下的预测寿命 vs 实测寿命，35 条样本，'
             '虚线为理想对角线；本次复算 R²=0.7437、RMSE=1600.3 cycles。'),
            ('shots/femnsic-fatigue-optimization/02-composition-candidate-map.png',
             ProjectShot.KIND_FIGURE,
             '主动学习候选点在 Mn–Si 成分空间上的投影（颜色 = 预测疲劳寿命）；'
             '推荐最优点 Mn 20.58 / Si 2.58 / C 0.53，保守预测寿命 8904.6 cycles。'),
            ('shots/femnsic-fatigue-optimization/03-loocv-model-comparison.png',
             ProjectShot.KIND_FIGURE,
             '无泄漏 LOOCV 下 9 个模型的 RMSE 对比：KRR 最优（R²=0.7877、RMSE=1456.5），'
             '加权集成次之（R²=0.7437），Huber 最差。'),
        ],
    },

    # ------------------------------------------------------------------
    # 3. Subway
    # ------------------------------------------------------------------
    {
        'title': 'Subway 智能地图 ｜ 轨道交通突发大客流研判与风险决策支持',
        'slug': 'subway-risk-decision',
        'badge': 'SUB',
        'category': Project.CATEGORY_TRANSIT,
        'role': '方案设计与原型实现 / 算法研究',
        'period': '',
        'order': 3,
        'is_featured': True,
        'summary': '面向轨交突发故障导致的运力下降、客流重分配与风险级联扩散，解决故障样本稀缺、'
                   '预测可解释性弱、静态阈值难反映动态风险的问题，输出可直接支撑调度决策的'
                   '影响范围与风险等级。',
        'intro': '以上海轨道交通 1 / 9 / 11 号线为对象，覆盖 0209、1112、0816 三起真实事故场景。\n\n'
                 '把问题拆解为三个可独立验证的子任务：短时客流预测、故障影响范围量化、动态风险分级。'
                 '用 A-LSTM 预测 10 分钟级短时客流及区间；用 DC-DCF 量化正常状态与故障状态下的 OD 差异；'
                 '再融合 DBN 路径选择模型与 ST-GCN 时空图网络推演全网客流传播，'
                 '完成站点级与网络级的动态风险计算。\n\n'
                 '风险指标体系为：二级指标 → 一级指标 C/D/I/F/P/M → 总风险 R0 → 站点动态风险 Rsta。'
                 '所有正式结果均按冻结公式独立复算，保证图表可追溯到源表、公式与绘图输入 CSV。',
        'contributions': [
            '将问题拆解为「短时客流预测 → 故障影响范围 → 动态风险分级」三个可独立验证的子任务。',
            '用 A-LSTM 预测 10 分钟级短时客流及区间；以 DC-DCF 量化正常 / 故障状态下的 OD 差异。',
            '融合 DBN 路径选择模型与 ST-GCN 时空图网络推演全网传播，完成站点与网络级动态风险计算。',
            '建立风险指标层级（二级指标 → 一级指标 C/D/I/F/P/M → 总风险 R0 → 站点动态风险 Rsta），'
            '并按冻结公式独立复算保证可追溯。',
        ],
        'metrics': [
            ('+4.76%~12.98%', 'DC-DCF 精度较基准提升'),
            ('↓ 40%~70%', '故障场景 MAPE 误差降幅'),
            ('1 / 9 / 11 号线', '真实事故场景覆盖'),
            ('10 min', '风险计算时间粒度'),
        ],
        'techs': ['A-LSTM', 'ST-GCN', 'DBN 路径选择', 'DC-DCF', '时空图神经网络',
                  'Python', '动态风险分级', '数据血缘审计'],
        'links': [
            (ProjectLink.KIND_OTHER, '输出影响范围 / 高风险站点 / 演化阶段', ''),
            (ProjectLink.KIND_OTHER, '支撑限流、疏导、运力调配与接驳决策', ''),
        ],
        'shots': [
            ('shots/subway-risk-decision/01-risk-station-ranking.png', ProjectShot.KIND_RESULT,
             '上海轨道交通 4 号线（26 站、环线）在上海火车站 2021-04-02 08:00 故障情景下的'
             '受影响车站排名，按额外聚集代理值排序，共识别 5 个风险站点。'),
            ('shots/subway-risk-decision/02-station-delta-heatmap.png', ProjectShot.KIND_FIGURE,
             '全线各站进出站客流变化热力图，18 个预测步（10 分钟粒度）。'),
            ('shots/subway-risk-decision/03-fault-station-flow.png', ProjectShot.KIND_FIGURE,
             '故障站（上海火车站）的客流曲线与恢复过程；额外聚集代理峰值 653.5，'
             '该指标是运营聚集度代理量，而非精确站内人数。'),
        ],
    },

    # ------------------------------------------------------------------
    # 4. 学生行为画像
    # ------------------------------------------------------------------
    {
        'title': '基于机器学习的学生行为画像研究 ｜ 国家级大学生创新创业训练计划',
        'slug': 'student-behavior-profiling',
        'badge': 'CV',
        'category': Project.CATEGORY_VISION,
        'role': '项目负责人',
        'period': '2022.04 – 2023.05',
        'order': 4,
        'is_featured': False,
        'summary': '面向线上线下混合教学场景，融合课堂视频与任务 / 作业记录构建学生学习画像，'
                   '在真实课堂试用，形成「识别 → 分析 → 可视化」闭环。',
        'intro': '国家级大学生创新创业训练计划项目，担任项目负责人。\n\n'
                 '面向线上线下混合教学场景，融合多模态数据构建学生学习画像：用课堂视频做人脸识别与'
                 '活体检测完成动态签到，用姿态 / 头部姿态 / 表情识别分析课堂行为，'
                 '再结合课堂互动记录与任务 / 作业成绩数据，用聚类与关联分析划分学生群体，'
                 '并通过预设规则生成个性化学习建议。\n\n'
                 '工程交付上，用 Qt 构建视频分析端、Streamlit 构建数据展示端，'
                 '形成从视频识别到画像可视化的完整闭环，并在真实课堂完成试用。',
        'contributions': [
            '作为项目负责人，完成业务场景梳理、数据处理、算法实现与原型交付。',
            '基于 YOLOv5s 结合姿态 / 头部姿态 / 表情识别分析课堂行为，'
            '融合人脸识别与活体检测完成动态签到。',
            '用 Scikit-learn 聚类与关联分析划分学生群体，并通过预设规则生成个性化学习建议。',
            '用 Qt 构建视频分析端、Streamlit 构建数据展示端，实现多模态数据的完整可视化交付。',
        ],
        'metrics': [
            ('国家级', '大学生创新创业训练计划'),
            ('YOLOv5s', '课堂行为检测模型'),
            ('Qt + Streamlit', '双端交付'),
            ('真实课堂', '落地试用'),
        ],
        'techs': ['YOLOv5s', '姿态 / 表情识别', '人脸识别 + 活体检测',
                  'Scikit-learn 聚类', '关联分析', '多模态融合', 'PyQt', 'Streamlit'],
        'links': [
            (ProjectLink.KIND_OTHER, '国家级大创项目 · 项目负责人', ''),
        ],
        'shots': [
            ('shots/student-behavior-profiling/01-kmeans-clustering.png', ProjectShot.KIND_UI,
             '成绩相关性概况：K-Means 聚类交互式组件，可调聚类数与展示特征，'
             '当前按「第一次课正答率」将学生聚为 2 类。'),
            ('shots/student-behavior-profiling/02-student-detail.png', ProjectShot.KIND_UI,
             '学生信息子页面：单生的课堂正答率 / 互动参与率、课后作业得分与阶段测试曲线'
             '（学生姓名已匿名化为编号）。'),
            ('shots/student-behavior-profiling/03-course-tracking.png', ProjectShot.KIND_UI,
             '课程信息子页面：按班级追踪上课效果（正答率均值与参与率均值合成），'
             '最近上课效果 71.875。'),
            ('shots/student-behavior-profiling/04-classroom-data.png', ProjectShot.KIND_UI,
             '课堂数据分析：由课堂视频解析出的学生行为专注度、情绪、头部姿态与群体专注度'
             '曲线（60 个时间点）。'),
        ],
    },

    # ------------------------------------------------------------------
    # 5. RenwuJiance
    # ------------------------------------------------------------------
    {
        'title': '目标检测桌面系统 ｜ YOLOv8 + PyQt5 多路视频检测与可视化',
        'slug': 'yolov8-detection-desktop',
        'badge': 'GUI',
        'category': Project.CATEGORY_DELIVERY,
        'role': '独立开发（模型训练 + 桌面端）',
        'period': '2024',
        'order': 5,
        'is_featured': False,
        'summary': '面向视频监控场景的目标检测桌面应用：自行完成 YOLOv8 模型训练，'
                   '并封装为带图形界面的可交付系统，支持多路摄像头管理、图片 / 视频检测、'
                   '目标跟踪与检测结果地图可视化。',
        'intro': '一个端到端的目标检测系统：从模型训练到桌面端交付全部独立完成。\n\n'
                 '模型侧，在自有标注数据集上完成 YOLOv8 的 100 轮训练，产出可用于推理的 best.pt 权重，'
                 '并保留 F1 曲线、PR 曲线、混淆矩阵等完整训练评估产物。\n\n'
                 '应用侧，用 PyQt5 搭建桌面端界面，支持多路摄像头的增删与切换管理、'
                 '图片与视频文件的选择和检测、实时画面播放；集成 YOLOv8 目标跟踪'
                 '（跨帧 ID 保持）输出带轨迹标注的检测视频；并用 pyecharts 构建'
                 '检测结果地图可视化页面，把检测结果落到地理视图上。',
        'contributions': [
            '在自有标注数据集上完成 YOLOv8 100 轮训练，产出可推理权重 best.pt，'
            '并保留 F1 / PR / 混淆矩阵等完整训练评估产物。',
            '用 PyQt5 搭建桌面端：多路摄像头增删管理、图片 / 视频选择与检测、实时画面播放。',
            '集成 YOLOv8 目标跟踪（跨帧 ID 保持），输出带轨迹标注的检测视频。',
            '用 pyecharts 构建检测结果地图可视化页面，把检测结果落到地理视图上。',
        ],
        'metrics': [
            ('0.9934', 'mAP@50'),
            ('0.7331', 'mAP@50-95'),
            ('0.9865', 'Precision'),
            ('0.9778', 'Recall'),
        ],
        'techs': ['YOLOv8 / Ultralytics', 'PyQt5', 'OpenCV', '目标跟踪',
                  'pyecharts', 'PyTorch', '模型训练与评估'],
        'video_caption': '演示视频：YOLOv8 检测 + 跨帧目标跟踪的实际输出（25 秒，1280×720）。',
        'video_target': 'videos/renwujiance-demo.mp4',
        'links': [
            (ProjectLink.KIND_OTHER, '桌面端：多路摄像头管理 + 检测播放', ''),
            (ProjectLink.KIND_OTHER, '检测结果地图可视化（pyecharts）', ''),
        ],
        'shots': [
            ('shots/yolov8-detection-desktop/01-desktop-gui.png', ProjectShot.KIND_GUI,
             'PyQt5 桌面端主界面：多路摄像头增删管理、图片 / 视频检测、'
             '检测画面实时播放与检测结果地图布点。'),
        ],
    },

    # ------------------------------------------------------------------
    # 6. 视觉手势人机交互
    # ------------------------------------------------------------------
    {
        'title': '视觉手势人机交互系统',
        'slug': 'gesture-hci',
        'badge': 'HCI',
        'category': Project.CATEGORY_VISION,
        'role': '独立开发',
        'period': '2023',
        'order': 6,
        'is_featured': False,
        'summary': '把摄像头采集的实时手势映射为系统控制指令，用非接触方式替代键鼠操作，'
                   '并设计状态保持与延时确认机制降低误触发。',
        'intro': '基于计算机视觉的非接触式人机交互系统。\n\n'
                 '使用 OpenCV 读取摄像头视频流，通过 MediaPipe 识别手掌关键点像素坐标，'
                 '根据拇指与食指指尖的坐标、利用勾股定理计算距离，把距离等比例映射为系统音量大小；'
                 '当拇指与食指贴合并左右滑动时，则用于调节屏幕亮度。\n\n'
                 '为提升交互稳定性，额外设计了状态保持与延时确认机制，'
                 '避免手势抖动导致的误触发。',
        'contributions': [
            '集成实时手势识别框架，将手势映射为系统音量与屏幕亮度控制。',
            '设计状态保持与延时确认机制，有效降低误触发、提升交互稳定性。',
        ],
        'metrics': [
            ('音量 + 亮度', '双维度系统控制'),
            ('实时', 'MediaPipe 手部关键点'),
            ('延时确认', '防误触发机制'),
        ],
        'techs': ['OpenCV', 'MediaPipe', '手势识别', '实时视频处理',
                  'pycaw', 'screen_brightness_control'],
        'video_caption': '演示视频：摄像头实时手势控制系统音量与屏幕亮度（20.6 秒，1280×720）。',
        'video_target': 'videos/gesture-hci-demo.mp4',
        'links': [],
    },
]


# ==========================================================================
# 首页区块：统计条 / Hero 资料卡 / 项目主线 / 教育时间线
# ==========================================================================
STATS = [
    ('6', '核心项目'),
    ('4', '竞赛奖项'),
    ('1', '软件著作权'),
    ('20/20', '系统评测通过'),
]

FACTS = [
    ('材料化工（专业硕士）· 在读',
     '上海第二工业大学 / 上海材料研究所联合培养 · 2024.09–2027.06', 'teal'),
    ('人工智能（工学学士）',
     '大连东软信息学院 · GPA 3.48（专业前 15%）· 校优秀毕业生', 'blue'),
    ('研究方向',
     '机器学习 · 目标优化 · 主动学习 · 小样本成分优化 · 计算模拟 · Agent 开发', 'violet'),
]

PILLARS = [
    ('AI × 新材料研发',
     '小样本疲劳寿命预测、主动学习闭环、成分反向优化、本地科研 RAG 智能体', 'teal'),
    ('轨道交通智能系统',
     '短时客流预测、故障影响传播、动态风险分级与可视化决策支持', 'blue'),
    ('视觉智能与系统交付',
     '多模态行为分析、YOLO 目标检测系统、手势交互、PyQt / Streamlit 桌面端与 Web 端交付', 'violet'),
]

PROFILE_ABOUT = (
    '我的项目横跨「材料研发」与「城市交通」两个真实场景，但方法论是同一条：'
    '先拆解业务问题，再选择或设计合适的模型，最后用可复现、可审计的方式交付。\n\n'
    '在材料方向，我面对的是典型的小样本难题——几十条实验数据要支撑成分设计决策。'
    '我的做法是物理启发特征 + 集成学习 + 主动学习闭环，并把「模型预测」与「实验结果」严格分层，绝不混淆。\n\n'
    '在交通方向，我把突发故障导致的客流风险问题拆成短时预测、OD 差异量化、'
    '全网传播推演与动态风险分级四步，产出能直接支撑调度决策的结果。'
)

EDUCATIONS = [
    {
        'school': '上海第二工业大学',
        'degree': '材料化工 · 专业硕士（在读）',
        'period': '2024.09 – 2027.06',
        'org': '上海材料研究所 联合培养',
        'description': '核心课题：FeMnSiC 阻尼钢成分优化，面向小样本材料数据开展'
                       '成分—性能建模与目标优化。',
        'highlights': '机器学习建模，目标优化算法，主动学习，小样本成分优化，计算模拟，Agent 开发',
        'order': 0,
    },
    {
        'school': '大连东软信息学院',
        'degree': '人工智能 · 工学学士',
        'period': '2020.09 – 2024.06',
        'org': 'GPA 3.48（专业前 15%）· 校优秀毕业生',
        'description': '核心课程覆盖 AI 主干：机器学习、深度学习、强化学习、自然语言处理、'
                       '计算机视觉与模式识别、人机交互、无人系统、分布式计算、'
                       '机器人编程软件体系架构。',
        'highlights': '机器学习，深度学习，强化学习，NLP，计算机视觉，分布式计算',
        'order': 1,
    },
]


AWARDS = [
    ('中国大学生机械工程创新创意大赛 · 失效分析赛', '国家级二等奖 · 2025', '🏆'),
    ('软件著作权《基于深度学习的商品结算系统 V1.0》', '已授权', '📄'),
    ('科技创新竞赛奖学金', '2025 年度', '🎓'),
    ('第十三届蓝桥杯程序设计竞赛', '省级二等奖 · 2021', '💻'),
    ('辽宁省计算机博弈竞赛', '省级二等奖 · 2021', '♟️'),
    ('优秀学生干部 · 校级优秀助教 · 校优秀毕业生', '综合荣誉', '⭐'),
]


SKILL_GROUPS = [
    ('编程语言与工程', 'Python（主）, C/C++, Java, Linux, Git, Qt, Streamlit, API 集成, 数据处理与可视化'),
    ('机器学习与优化', 'Scikit-learn, XGBoost, 主动学习, 贝叶斯优化, 差分进化, 小样本建模, 物理启发特征'),
    ('深度学习框架', 'PyTorch, TensorFlow, 模型搭建, 数据预处理, 训练调参, 验证测试'),
    ('计算机视觉', 'U-Net, YOLO, CNN, OpenCV, 注意力机制, 图像分割, 目标检测'),
    ('自然语言处理', 'LSTM, BERT, 词向量 / 文本向量化, 关键词提取, Neo4j 知识图谱'),
    ('大数据与软件架构', 'Spark SQL, Hadoop, Spark MLlib, Maven, SpringMVC, SpringBoot, Redis'),
    ('科研与办公', 'LaTeX, Office, 技术文档撰写, 可复现实验设计'),
]


class Command(BaseCommand):
    help = '导入作品集初始数据（个人资料、项目、荣誉、技能）'

    def add_arguments(self, parser):
        parser.add_argument('--reset', action='store_true',
                            help='先清空现有数据再导入')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['reset']:
            Project.objects.all().delete()
            Award.objects.all().delete()
            SkillGroup.objects.all().delete()
            Profile.objects.all().delete()
            Stat.objects.all().delete()
            ProfileFact.objects.all().delete()
            Pillar.objects.all().delete()
            Education.objects.all().delete()
            self.stdout.write(self.style.WARNING('已清空现有数据'))

        if Project.objects.exists() and not options['reset']:
            self.stdout.write(self.style.WARNING(
                '已有项目数据，跳过导入（如需重建请加 --reset）'))
            return

        # ---------- 个人资料 ----------
        Profile.objects.update_or_create(
            name='王猛',
            defaults={
                'headline': '求职方向 · FDE / AI 解决方案工程师',
                'tagline': '让 AI 落到真实产业场景里',
                'intro': '人工智能本科 + 材料化工硕士。具备从业务问题拆解 → 数据/算法方案 → '
                         '模型验证 → 可视化与交互交付的完整项目经验。主攻 AI 辅助新材料研发'
                         '与轨道交通智能系统，同时覆盖计算机视觉、自然语言处理与人机交互。',
                'about': PROFILE_ABOUT,
                'phone': '',
                'email': 'sojourn_wang@163.com',
                'city': '上海',
            },
        )

        # ---------- 首页区块 ----------
        for i, (value, label) in enumerate(STATS):
            Stat.objects.create(value=value, label=label, order=i)

        for i, (title, subtitle, icon) in enumerate(FACTS):
            ProfileFact.objects.create(title=title, subtitle=subtitle,
                                       icon=icon, order=i)

        for i, (title, description, icon) in enumerate(PILLARS):
            Pillar.objects.create(title=title, description=description,
                                  icon=icon, order=i)

        for data in EDUCATIONS:
            Education.objects.create(**data)

        # ---------- 项目 ----------
        media_root = settings.MEDIA_ROOT
        for data in PROJECTS:
            data = dict(data)
            contributions = data.pop('contributions', [])
            metrics = data.pop('metrics', [])
            techs = data.pop('techs', [])
            links = data.pop('links', [])
            video_source = data.pop('video_source', None)
            video_target = data.pop('video_target', None)
            demo_source = data.pop('demo_source', None)
            demo_target = data.pop('demo_target', None)
            shots = data.pop('shots', [])

            project = Project.objects.create(**data)

            for i, text in enumerate(contributions):
                Contribution.objects.create(project=project, text=text, order=i)
            for i, (value, label) in enumerate(metrics):
                Metric.objects.create(project=project, value=value, label=label, order=i)
            for i, name in enumerate(techs):
                TechItem.objects.create(project=project, name=name, order=i)
            for i, (kind, label, url) in enumerate(links):
                ProjectLink.objects.create(project=project, kind=kind, label=label,
                                           url=url, order=i)

            # 关联本地演示素材（media/ 下已归集的成品，只写相对路径不复制文件）
            if _attach(project, 'video_file', video_target, video_source, media_root):
                self.stdout.write('  视频: {}'.format(video_target))
            if _attach(project, 'demo_image', demo_target, demo_source, media_root):
                self.stdout.write('  动图: {}'.format(demo_target))

            # 实机截图 / 结果图
            n_shots = 0
            for i, (rel, kind, caption) in enumerate(shots):
                if not _media_exists(media_root, rel):
                    self.stdout.write(self.style.WARNING(
                        '  [!] 截图缺失，已跳过: {}'.format(rel)))
                    continue
                shot = ProjectShot(project=project, kind=kind,
                                   caption=caption, order=i)
                shot.image.name = rel
                shot.save()
                n_shots += 1
            if n_shots:
                self.stdout.write('  截图: {} 张'.format(n_shots))

            self.stdout.write(self.style.SUCCESS('  ✔ {}'.format(project.title)))

        # ---------- 荣誉 ----------
        for i, (title, detail, icon) in enumerate(AWARDS):
            Award.objects.create(title=title, detail=detail, icon=icon, order=i)

        # ---------- 技能 ----------
        for i, (name, items) in enumerate(SKILL_GROUPS):
            SkillGroup.objects.create(name=name, items=items, order=i)

        self.stdout.write(self.style.SUCCESS(
            '\n导入完成：{} 个项目 / {} 张实机截图 / {} 项荣誉 / {} 个技能分组 / '
            '{} 条统计 / {} 张资料卡 / {} 条主线 / {} 段教育经历'.format(
                Project.objects.count(), ProjectShot.objects.count(),
                Award.objects.count(),
                SkillGroup.objects.count(), Stat.objects.count(),
                ProfileFact.objects.count(), Pillar.objects.count(),
                Education.objects.count())))
