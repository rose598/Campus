# GraphCampus 项目规划书

> 基于状态图的多智能体校园助手 —— 双人协同开发版（[学校名]定制）

---

## 目录

1. [项目概述](#1-项目概述)
2. [数据来源](#2-数据来源)
3. [团队分工](#3-团队分工)
4. [技术架构](#4-技术架构)
5. [核心功能](#5-核心功能)
6. [冷启动引导（新用户首次体验）](#6-冷启动引导新用户首次体验)
7. [工业化设计](#7-工业化设计)
8. [兜底设计（失败路径处理）](#8-兜底设计失败路径处理)
9. [隐私设计](#9-隐私设计)
10. [未来展望（不作本次开发承诺）](#10-未来展望不作本次开发承诺)
11. [6 周协同开发计划](#11-周协同开发计划双人版-42天)
12. [交付物清单](#12-交付物清单)
13. [协作规范](#13-协作规范)
14. [答辩策略](#14-答辩策略)

---

## 1. 项目概述

### 1.1 一句话概括

**GraphCampus** 是一个基于状态图的多智能体校园助手，由"规划师""情报官""学伴"三个 AI 智能体组成。它能自动解析各专业课的大纲内容、梳理课程间的先修与知识依赖关系、根据你的专业方向推荐最优学习路径、课后帮你把笔记关联到课程知识体系，并主动推送与你所学课程相关的讲座、竞赛和科研机会。

### 1.2 解决的问题

| 场景 | 痛点 |
|------|------|
| 选课迷茫 | 只看到课程名，不知道具体讲什么、难不难、需要什么基础 |
| 先修关系不清 | 选了某门课才发现跟不上 |
| 学完不知道下一步 | 不知道后续该学什么 |
| 想了解课程细节 | 想问问题但没人及时回答 |
| 课程与资源脱节 | 不知道这门课对应什么研究方向、实验室机会 |
| 信息茧房 | 讲座/竞赛存在但自己不知道 |

### 1.3 本校化定位

- 仅服务 **本校**，数据来源于本校培养方案和课程大纲
- 知识图谱预置本校教师、课程、实验室、研究方向
- 开发与演示均使用本校真实数据

---

## 2. 数据来源

| 数据 | 来源 | 获取方式 |
|------|------|---------|
| 专业课列表 | 教务处官网 / 培养方案 PDF | 手动下载 → 结构化 |
| 课程大纲 | 学院网站 / 教师提供 | LLM 辅助提取 + 模板填空 |
| 先修关系 | 课程大纲 + Node2Vec 预测 | 双路 LLM 交叉验证 + 链路预测补全 |
| 授课教师 | 教务处 / 课程大纲 | 与课程一起录入 |
| 实验室 / 研究方向 | 学院官网、教师主页 | BeautifulSoup 爬取 |
| 讲座 / 竞赛 | 官网 / 公众号 | 预置 JSON（主）+ 爬虫（辅） |
| 课堂笔记 | 学生上传 | 文本粘贴 → LLM + Embedding |
| 已修课程 | 学生手动标记 | 界面勾选 |

---

## 3. 团队分工

### 角色 A：后端算法（Agent + 图谱 + RAG + 工业化基建）

| 职责 | 具体内容 |
|------|---------|
| LangGraph 工作流 | 父图子图、并行节点、中断点、异步编排 |
| 双路交叉验证 | 两个独立 LLM 并行提取 → Jaccard 比对 → 置信度分级决策 |
| Node2Vec 链路预测 | 学习课程节点嵌入 → 预测缺失先修关系 → 推荐给用户确认 |
| Hybrid RAG | BM25 + Dense Embedding 混合检索 + RRF 融合 + Query Rewriting |
| PPR 推荐 | 定制的 Personalized PageRank 实现 |
| 语义缓存 | LLM 调用结果缓存（相同/相似请求命中缓存） |
| 工业化基建 | Pydantic 校验层、结构化日志 + 性能追踪、pytest 测试框架 |
| LLM 提示词工程 | 7 套提示词模板（提取 / 验证 / 问答 / 改写 / 共情 / 摘要 / 幻觉过滤） |

### 角色 B：全栈前端 + 数据 + DevOps

| 职责 | 具体内容 |
|------|---------|
| Streamlit 前端 | 路由、组件、状态同步、冷启动引导 |
| 图谱可视化 | Pyvis 课程关系图（支持搜索 / 高亮 / 缩放） |
| 异步任务 UI | LLM 调用时的进度条 + 状态通知（Streamlit 原生 + 自建轮询） |
| RAG 问答界面 | 对话 UI + BM25 / 向量双栏展示 + 引用标注 |
| 校园信息抓取 | BeautifulSoup 爬虫 + JSON 数据维护 |
| 数据库 | SQLite 表设计 + CRUD + Embedding 存储 + 缓存表 |
| 课程数据录入 | 预置一个完整专业（~40 门课）+ 双路验证标注 |
| DevOps | Docker 镜像、GitHub Actions CI |
| 演示准备 | 剧本、PPT、视频录制 |

### 公共模块

- AgentState 定义 + JSON Schema（Day 1 锁死）
- LLM 中枢封装（含重试 / 降级 / 缓存）
- Embedding 服务封装
- 结构化日志接口（统一 correlation_id）
- Pydantic model 层

---

## 4. 技术架构

### 4.1 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                     Streamlit 前端                             │
│  课程地图  课程详情  RAG问答  推送面板  课后复习  对话面板     │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────┴───────────────────────────────────────┐
│                   LangGraph 工作流引擎                        │
│                                                            │
│   ┌────────────┐  ┌────────────┐  ┌────────────┐          │
│   │ 规划师子图   │  │ 情报官子图  │  │ 学伴子图    │          │
│   │ ·双路验证    │  │ ·PPR推荐   │  │ ·Hybrid RAG│          │
│   │ ·Node2Vec   │  │ ·路径溯源   │  │ ·Query     │          │
│   │ ·拓扑排序    │  │            │  │  Rewrite   │          │
│   │ ·课后复习    │  │            │  │ ·语义缓存   │          │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘          │
│          └────────────────┼────────────────┘                 │
│                           │                                  │
│                    ┌──────┴──────┐                           │
│                    │ AgentState  │                           │
│                    │ 滑动窗口+摘要│                           │
│                    └──────┬──────┘                           │
└───────────────────────────┼──────────────────────────────────┘
                            │
┌───────────────────────────┼──────────────────────────────────┐
│                           │                                  │
│  ┌────────────────────────┴────────────────────────┐        │
│  │            LLM + Embedding 服务层                  │        │
│  │  OpenAI / 国产大模型 + sentence-transformers      │        │
│  │  重试 (3次, 指数退避)   熔断 (5错误→停30s)         │        │
│  │  语义缓存 (Sim>0.92 命中)  并发控制 (max=3)        │        │
│  └───────────────────────────────────────────────────┘        │
│                            │                                  │
│  ┌───────┐ ┌───────┐ ┌──────┐ ┌──────┐ ┌──────┐            │
│  │SQLite │ │NetworkX│ │BM25  │ │ 日志  │ │ 缓存  │            │
│  │ 数据   │ │ 图谱    │ │ 倒排  │ │(结构  │ │(语义  │            │
│  │ +向量  │ │ +PPR   │ │ 索引  │ │ 化)   │ │ 桶)   │            │
│  │ WAL   │ │ +NVec  │ │      │ │trace │ │      │            │
│  └───────┘ └───────┘ └──────┘ └──────┘ └──────┘            │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  工业化基础设施                                               │
│  Pydantic校验  │  异步Task队列  │  CI(GitHub Actions)  │  结构化日志  │
│  p.测试(>80%)  │  Docker       │  .env.example       │  pre-commit  │
└──────────────────────────────────────────────────────────────┘
```

### 4.2 技术栈选型

| 层次 | 选型 | 说明 |
|------|------|------|
| 前端 | **Streamlit** | 快速迭代 |
| 工作流 | **LangGraph** | 并行 / 中断 / 异步 |
| LLM | **OpenAI / 国产大模型** | 调用层：重试 + 熔断 + 缓存 + 并发控制 |
| Embedding | **sentence-transformers** | 本地运行，零 API 成本 |
| 混合检索 | **BM25（rank_bm25）+ Dense（余弦）** | RRF 融合，工业级 RAG 标配 |
| Query Rewriting | **LLM 改写** | 多轮对话上下文压缩 |
| 知识图谱 | **NetworkX** | PPR / Node2Vec / 拓扑排序 |
| Node2Vec | **Node2Vec 库** | 链路预测发现缺失先修 |
| 语义缓存 | **自建（余弦相似度 + TTL）** | 相同/相似请求命中缓存 |
| 数据库 | **SQLite（WAL 模式）** | 高并发读取 |
| 校验 | **Pydantic v2** | 所有 I/O 运行时校验 |
| 日志 | **structlog + 自建 tracer** | JSON 格式 + correlation_id + 节点耗时 |
| 测试 | **pytest + pytest-cov** | 单元测试 > 80% 覆盖率 |
| CI | **GitHub Actions** | PR 自动 lint + test + build |
| 容器 | **Docker** | 多阶段构建，镜像 < 500MB |

### 4.3 关键技术算法

#### 4.3.1 双路交叉验证 + 置信度分级

```
输入: 课程大纲文本

LLM-A 提取先修          LLM-B 提取先修
   │                       │
   └────────┬──────────────┘
            │
     Jaccard 相似度计算
            │
    ┌───────┼───────┐
    │       │       │
  =1.0   0.5-0.99  <0.5
    │       │       │
  自动写入  中断确认  强制手动
  图谱     争议项    编辑
```

- **高置信度**（J=1.0）：自动写入图谱，记录 `confidence: 1.0`
- **中置信度**（J=0.5~0.99）：中断展示两路差异项，用户勾选确认
- **低置信度**（J<0.5）：完整中断，表单手动编辑
- 幻觉过滤叠加：课程名不在预置列表中 → 打回；检测到循环依赖 → 打回

#### 4.3.2 Node2Vec 链路预测（发现缺失先修）

对于已录入的课程图谱，用 Node2Vec 学习每个课程节点的向量表示，然后：

1. 对每对未直接连接的课程 (u, v)，计算其在嵌入空间中的余弦相似度
2. 相似度高于阈值（如 0.85）且符合学期逻辑（先修课早于后继课）→ 作为"潜在先修关系"推荐给用户
3. 用户确认后加入图谱

**价值**：教师可能漏写了先修关系，算法自动补全，答辩时可以展示"系统发现了一个你可能没注意到的先修关系"。

#### 4.3.3 Hybrid RAG（BM25 + Dense + RRF）

学生提问 → Query Rewriting（多轮）→ 同时检索两条路：

```
用户问题
   │
 Query Rewriting (LLM 改写)
   │
   ├──→ BM25 稀疏检索 (关键词匹配)
   │       │
   │       └──→ Top-5
   │
   └──→ Dense 稠密检索 (语义匹配)
           │
           └──→ Top-5
                   │
            Reciprocal Rank Fusion (RRF)
                   │
              Top-3 → LLM 生成回答
```

- **Query Rewriting**：多轮对话时，LLM 将历史上下文压缩到当前问题中，如"用什么教材？"→"数据结构这门课用什么教材？"
- **BM25**：关键词精确匹配，召回包含"教材""课本"等关键词的段落
- **Dense**：语义匹配，召回语义相似但关键词不重叠的段落
- **RRF**：`score = Σ 1/(k + rank)` 融合两个排序，k=60

#### 4.3.4 Personalized PageRank

在包含课程 / 教师 / 实验室 / 研究方向 / 讲座 五类节点的异构图上运行。personalization vector 以用户当前关注的课程或研究方向为中心分配权重。迭代收敛后，取分数最高的推荐机会。

#### 4.3.5 语义缓存

- **Key**：`(system_prompt_hash, user_message_embedding)`
- **命中条件**：余弦相似度 > 0.92
- **TTL**：3600s（1 小时）
- **存储**：SQLite 缓存表
- **价值**：同一门课的不同学生问"这门课难吗？"→ 第二次直接命中缓存，零延迟

### 4.4 LangGraph 状态图设计

```
ParentGraph
│
├── Input: 课程大纲 / 笔记 / 问答 / 已修标记
│
├── Node 1: 解析节点 (Parse)
│   ├── SubNode: 双路 LLM 提取 (LLM-A + LLM-B)
│   ├── SubNode: 交叉验证 (Jaccard + 置信度)
│   │    ├── 高 → 直接入库
│   │    ├── 中 → [interrupt_before] 用户确认
│   │    └── 低 → [interrupt_before] 手动编辑
│   ├── SubNode: Node2Vec 链路预测 (推荐缺失先修 → 用户确认)
│   ├── SubNode: 幻觉过滤 (名校验 + 循环依赖)
│   └── SubNode: 笔记→Embedding (课后复习场景)
│
├── Node 2: Fan-out 并行调度
│   ├── → 规划师 (图谱 / 路径 / 复习)
│   ├── → 情报官 (PPR / 推送)
│   └── → 学伴 (RAG / 共情)
│
├── Node 3: 各子图执行 (并行)
│   │
│   ├── Agent_1: 规划师
│   │   ├── 图谱更新 + Node2Vec 增量训练
│   │   ├── 学习路径 (拓扑 → 学期约束 → 备用)
│   │   └── 课后复习 (知识点→图谱标注)
│   │
│   ├── Agent_2: 情报官
│   │   ├── PPR 初始化 (personalization)
│   │   ├── PPR 迭代 → Top-K
│   │   └── 推理链生成 (路径溯源)
│   │
│   └── Agent_3: 学伴
│       ├── Query Rewriting (多轮)
│       ├── Hybrid RAG (BM25+Dense → RRF → LLM)
│       ├── 语义缓存查/写
│       └── LLM 共情生成
│
├── Node 4: Fan-in 聚合
│   └── 合并 → 响应
│
└── Output: 响应 + 结构化日志 (含各节点耗时)

AgentState:
{
  "user_id": str,
  "messages": List[BaseMessage],         // 滑动窗口 20 轮
  "chat_summary": str,                   // LLM 摘要
  "courses": Dict[str, Course],
  "course_graph": Graph,                 // NetworkX 图
  "node2vec_model": Optional[Model],     // Node2Vec 模型 (增量更新)
  "bm25_index": Optional[BM25],          // 倒排索引
  "dense_index": Dict[str, List[float]], // {chunk_id: embedding}
  "cache_pool": Dict[str, str],          // 语义缓存 (key: hash+emb, value: response)
  "user_progress": Dict,
  "learning_path": Optional[List[str]],
  "alt_paths": List[List[str]],
  "ppr_scores": Optional[Dict],
  "current_notes": Optional[Dict],
  "knowledge_graph": Graph,
  "behavior_logs": List[Log],
  "pending_questions": List[str],
  "privacy_mode": bool,
  "interrupt_flag": bool,
  "extraction_confidence": float,
  "trace_id": str                        // 每次请求的追踪 ID
}
```

---

## 5. 核心功能

### 5.1 规划师 Agent

- **双路交叉验证提取**：两个独立 LLM 并行提取课程信息 → Jaccard 比对 → 置信度分级决策
- **Node2Vec 链路预测**：发现缺失的先修关系，主动推荐给用户确认
- **知识图谱**：NetworkX 建模课程 / 教师 / 实验室 / 研究方向
- **课程详情**：信息卡 + 先修链 + 后继课程 + 相关教授
- **路径推荐**：拓扑排序 → 学期约束 → 备用路径（用户标记冲突后自动切换）
- **课后复习**：笔记 → LLM + Embedding 匹配 → 图谱高亮标注

### 5.2 情报官 Agent

- **Personalized PageRank 推荐**：以用户当前课程/方向为起点，异构图上 PPR 传播，发现多跳关联
- **推送排序**：PPR 分数排行 + 推理链溯源展示
- **数据**：预置 JSON（主）+ 爬虫（辅）

### 5.3 学伴 Agent（Hybrid RAG + 共情）

- **Hybrid RAG 问答**：
  - Query Rewriting（多轮上下文压缩）
  - BM25 + Dense Embedding 双路检索
  - RRF 融合排序
  - LLM 生成带引用的回答
- **语义缓存**：相似问题秒回，零 LLM 调用
- **并行协作**：焦虑场景三路 Fan-out
- **共情生成**：LLM + 行为上下文

### 5.4 交互场景：Hybrid RAG 问答

```
用户: "这门课怎么样？"
系统: "你是指《数据结构》对吧？我来查一下。"

[内部: Query Rewriting → "数据结构这门课的教学内容、难度和评价如何？"]
[内部: BM25 Top-5 + Dense Top-5 → RRF → Top-3]
[内部: 语义缓存检查 → 未命中 → LLM 生成]

系统: "
根据课程大纲，数据结构包含以下内容：
1. 线性表、栈、队列、树、图等核心数据结构
2. 配套 3 个编程项目：表达式求值、哈夫曼编码、图遍历
3. 教材：严蔚敏《数据结构（C语言版）》
4. 先修课程：C语言程序设计
[来源: 数据结构课程大纲 第2-5节]
"
```

### 5.5 交互场景：Node2Vec 链路预测

```
系统: "我分析了一下已录入的课程关系，发现《机器学习》和《概率论》
       在内容上有较强的前后置关联（相关性 0.91），是否将《概率论》
       设为《机器学习》的先修课程？"
用户: "确认"
系统: "已加入图谱。当前《机器学习》的先修链更新为：
       高等数学 → 概率论 → 机器学习"
```

---

## 6. 冷启动引导（新用户首次体验）

| 步骤 | 操作 | 系统行为 |
|------|------|---------|
| 1 | 选择专业 | 展示本校专业列表 |
| 2 | 浏览课程体系 | 展示完整课程列表，按学期分组 |
| 3 | 标记已修 | 勾选已学完的课程 |
| 4 | 图谱渲染 | 渲染图谱 + Node2Vec 发现缺失先修 → 提示确认 |
| 5 | 进入主界面 | 课程地图 + 推荐路径 + RAG 问答入口 |

---

## 7. 工业化设计

### 7.1 Pydantic 校验层

所有 I/O 数据用 Pydantic v2 定义，运行时强制校验：

```python
class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., pattern=r"^[A-Z]+\d{4}$")
    credits: float = Field(..., ge=0.5, le=30)
    prerequisites: list[str] = Field(default_factory=list)
    semester: Literal["春季", "秋季", "春秋季"]
    teacher: str = Field(..., min_length=1)
```

- AgentState 进出 LangGraph 节点时自动校验
- 数据库写入前校验
- API 入参出参校验

### 7.2 LLM 调用层（重试 + 熔断 + 缓存 + 并发控制）

```
LLM.call()
  ├── 语义缓存查询 (相似度 > 0.92? → 直接返回)
  ├── 并发槽检查 (当前并行 < 3? → 继续; 否 → 排队)
  ├── 熔断器状态 (连续 5 次失败? → 30s 快速失败)
  ├── 重试 (3 次, 指数退避: 1s → 2s → 4s)
  ├── 计时 (写入结构化日志: prompt_tokens, latency)
  └── 语义缓存写入 (TTL=3600s)
```

### 7.3 结构化日志 + 性能追踪

每条请求生成 `trace_id`，贯穿所有节点。日志格式：

```json
{
  "ts": "2026-06-20T10:30:00.123Z",
  "level": "INFO",
  "trace_id": "abc123",
  "node": "dual_validation",
  "latency_ms": 2340,
  "detail": {
    "llm_a_tokens": 142,
    "llm_b_tokens": 156,
    "jaccard": 0.83,
    "confidence": "medium"
  }
}
```

- LangGraph 每个节点执行前后自动打点
- 可视化各节点耗时分布（答辩展示用）

### 7.4 测试体系

| 层级 | 工具 | 覆盖 |
|------|------|------|
| 单元测试 | pytest | 每个 Pydantic model、每个 Node 函数 |
| 集成测试 | pytest + SQLite in-memory | 子图全流程（Mock LLM） |
| 端到端 | pytest + Streamlit test | 用户操作路径 |
| CI | GitHub Actions | push/PR 触发，lint + test + build |

### 7.5 Docker + CI

```dockerfile
# 多阶段构建
FROM python:3.11-slim AS base
# ...
FROM base AS runtime
COPY --from=base /app /app
CMD ["streamlit", "run", "main.py"]
```

```yaml
# .github/workflows/ci.yml
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest --cov=./ --cov-fail-under=80
      - run: docker build -t graphcampus .
```

---

## 8. 兜底设计（失败路径处理）

| 场景 | 兜底 |
|------|------|
| 双路 LLM 都提取错误 | 低置信度 → 强制手动编辑 |
| 单路提取错误 | 中置信度 → 展示争议项确认 |
| LLM 幻觉编造课程名 | 课程名校验（不在列表中→拒绝）+ 循环依赖检测 |
| Node2Vec 预测错误 | 预测结果仅"推荐"级别，需用户确认后才写入 |
| Hybrid RAG 检索不到 | BM25+Dense 双路同时空的概率极低；RRF 无结果 → "未找到" |
| RAG 检索分数低 | 低于阈值时提示换个问法 |
| Embedding 服务不可用 | 回退到纯 BM25 关键词检索 |
| LLM API 超时/失败 | 重试 3 次 → 熔断 → 降级为规则回复 |
| 语义缓存污染 | TTL+LRU 淘汰，缓存表定期清理 |

---

## 9. 隐私设计

| 数据 | 存储 | 上传 |
|------|------|------|
| 课程信息 | 本地 SQLite (WAL) | ❌ |
| 先修关系 | 本地 SQLite | ❌ |
| 已修标记 | 本地 SQLite | ❌ |
| 课堂笔记 | 本地处理 | ❌ |
| 行为日志 | 本地 SQLite | ❌ |
| LLM 调用 | 临时内存 | ✅ 仅结构化文本 |
| Embedding 调用 | 临时内存 | ✅ 仅文本片段，无身份 |

**隐私模式**：
- 离线模式：无 LLM，纯规则 + BM25 检索
- 标准模式：默认，缓存命中优先
- 严格模式：每次 LLM 调用前确认

---

## 10. 未来展望

| 方向 | 描述 |
|------|------|
| 学习小组匹配 | 基于课程图谱匹配同学 |
| 历史 QA 语料扩充 | 积累问答对，提升 RAG 覆盖率 |
| 教师评价分析 | 基于公开数据 |
| 知识图谱自动爬取 | 动态更新 |

---

## 11. 6 周协同开发计划（双人版 · 42 天）

> 每天 4-6 小时，每周日同步。

### 第 1 周：基建 + 接口锁死

| 天 | 角色 A | 角色 B |
|----|--------|--------|
| **Day 1** | **接口锁死：共写 AgentState + JSON Schema + Pydantic models + Mock 数据 + 表结构 → README** |
| 2 | LLM 调用封装（重试 / 熔断 / 并发控制） | Streamlit 骨架 + 路由 + 基础布局 |
| 3 | 结构化日志系统（tracer + trace_id） | 数据库建表 + CRUD + WAL 模式 |
| 4 | 单路 LLM 提取节点 + Pydantic 校验 | 中断交互组件（弹窗 + 确认/编辑） |
| 5 | NetworkX 图谱构建 + Pyvis 序列化 | 课程详情页 + 图谱可视化 |
| 6 | 拓扑排序 + Node2Vec 基础链路 | 冷启动引导（选专业 → 课程列表） |
| 7 | **周联调**：录入→中断→图谱→前端 | 预置 15 门课 Mock 数据 |

### 第 2 周：双路验证 + Node2Vec + PPR

| 天 | 角色 A | 角色 B |
|----|--------|--------|
| 8 | 双路 LLM 提取 (LLM-A + LLM-B 并行) | 双路结果 UI 展示（对比视图） |
| 9 | Jaccard 比对 + 置信度三级决策 | 置信度标签（红/黄/绿） |
| 10 | Node2Vec 链路预测（缺失先修发现） | 链路预测推荐弹窗 + 确认 |
| 11 | Personalized PageRank 实现 | PPR 推荐结果前端（分数 + 排序） |
| 12 | 拓扑 + 学期约束 + 备用路径 | 路径规划前端（方案 A/B 切换） |
| 13 | 幻觉过滤（名校验 + 循环检测） | 冷启动内集成链路预测 |
| 14 | **本周联调 + Bug 清理** | 预置 40 门课完整数据 |

### 第 3 周：Hybrid RAG + 语义缓存

| 天 | 角色 A | 角色 B |
|----|--------|--------|
| 15 | BM25 倒排索引构建 | RAG 问答界面（对话 UI） |
| 16 | Dense Embedding 索引 + 余弦检索 | 双栏展示（BM25 / Dense 各自结果） |
| 17 | RRF 融合排序 + LLM 生成（引用） | 引用标注前端（来源高亮） |
| 18 | Query Rewriting（多轮上下文压缩） | 多轮对话 UI（上下文展示） |
| 19 | 语义缓存（相似度 > 0.92 + TTL） | 缓存命中提示 + 清零机制 |
| 20 | RAG + 缓存 + Query Rewriting 联调 | RAG 全流程测试 + fallback 测试 |
| 21 | **学伴子图完整化**：RAG + 共情 + 行为统计 | 学伴对话界面 + 行为日志埋点 |

### 第 4 周：课后复习 + 并行 + 隐私

| 天 | 角色 A | 角色 B |
|----|--------|--------|
| 22 | 课后复习：笔记 LLM 提取 + Embedding 匹配 | 课后复习界面（粘贴 / 上传） |
| 23 | 知识点→图谱位置标注（前后继关联） | 图谱高亮 + 复习/预习建议卡 |
| 24 | 滑动窗口 + 摘要（max_turns=20） | 摘要提示 UI |
| 25 | Fan-out / Fan-in 并行节点 | 并行协作前端（聚合展示） |
| 26 | 隐私模式（离线 / 标准 / 严格） | 隐私控制 + 数据流向信息卡 |
| 27 | 隐私模式下降级验证 | 全功能集成测试 |
| 28 | **完整联调** | UI 统一打磨 |

### 第 5 周：工业化 + 边界测试

| 天 | 角色 A | 角色 B |
|----|--------|--------|
| 29 | 测试框架：pytest + 单元测试（Model / Node） | 测试框架：集成测试 + 端到端 |
| 30 | LLM 调用层边界（超时 / 空响应 / 异常） | 兜底交互全面对齐 |
| 31 | Hybrid RAG 质量调优（chunk / Top-K / RRF k） | 图谱交互增强（搜索 / 高亮） |
| 32 | PPR / Node2Vec 性能测试（40 节点） | UI 统一（配色 / 间距 / 字体） |
| 33 | 全场景回归 + 边界覆盖 | 移动端适配 |
| 34 | Docker 多阶段构建 + GitHub Actions | Docker + CI 联调 |
| 35 | **最终 Bug 清理 + 测试覆盖率 > 80%** | 演示数据 + 剧本 |

### 第 6 周：文档 + 答辩

| 天 | 协同 |
|----|------|
| 36 | 互相黑盒测试 |
| 37 | 最终修 Bug |
| 38 | 技术白皮书（架构图 / 算法 / 工业化设计） |
| 39 | 录制 5 分钟演示视频 |
| 40 | PPT + 模拟答辩 |
| 41 | 第二轮模拟答辩 |
| 42 | 提交 |

---

## 12. 交付物清单

### 代码

| 模块 | 说明 |
|------|------|
| `main.py` | 入口 |
| `agents/` | LangGraph 子图 + 父图 |
| `curriculum/` | 双路验证 + 置信度 + Node2Vec |
| `knowledge_graph/` | NetworkX + PPR + NVec |
| `rag/` | BM25 + Dense + RRF + Rewrite + 缓存 |
| `review/` | 课后复习 |
| `crawler/` | 爬虫 + JSON 数据 |
| `database/` | 建表 + CRUD + WAL |
| `onboarding/` | 冷启动 |
| `utils/` | LLM 中枢（重试/熔断/缓存）、tracer、日志 |
| `models/` | Pydantic v2 定义 |
| `tests/` | pytest 测试 |
| `docker/` | Dockerfile + .dockerignore |
| `.github/` | GitHub Actions CI |

### 文档

| 交付物 | 说明 |
|--------|------|
| `README.md` | 项目简介 + Day 1 接口定义 |
| `项目规划书.md` | 本文档 |
| `技术白皮书.pdf` | 架构 / 算法 / 工业化设计 / 性能数据 |
| `演示视频.mp4` | 5 分钟 |
| `答辩PPT.pptx` | |

---

## 13. 协作规范

- **Git**：GitHub 私有库，`feat/xxx` 分支，PR review 后合并
- **Day 1 锁死**：AgentState + Schema + Pydantic models + Mock 数据 → README
- **日志**：统一 `trace_id`，JSON 格式
- **沟通**：每日 10 分钟站会，周日 30 分钟同步

---

## 14. 答辩策略

### 角色

| 角色 | 主讲 |
|------|------|
| **A** | 双路验证 / Node2Vec / PPR / Hybrid RAG / 工业化设计 |
| **B** | 痛点 / 交互 / 兜底 / 隐私 / 演示操作 |

### 演示流程（5 分钟）

| 时间 | 环节 |
|------|------|
| 0:00-0:30 | 痛点（B） |
| 0:30-1:00 | 冷启动（B 操作，A 解说） |
| 1:00-2:00 | **亮点 1：双路验证 + Node2Vec 链路预测**（A）— 展示两路提取对比 + 置信度标签 + 系统推荐缺失先修 |
| 2:00-2:45 | **亮点 2：PPR 推荐**（A）— 展示推理链溯源 |
| 2:45-3:30 | **亮点 3：Hybrid RAG 问答**（B）— 现场提问 + BM25/Dense 双栏 + 引用标注 + 语义缓存秒回 |
| 3:30-4:00 | 课后复习（B） |
| 4:00-4:30 | 工业化 + 兜底 + 隐私（A）— 展示结构化日志 / 测试覆盖率 / 熔断降级 |
| 4:30-5:00 | 总结（A+B） |

### Q&A

| 问题 | 要点 |
|------|------|
| 先修关系怎么保证准确？ | 双路 LLM 交叉验证 + 幻觉过滤 + Node2Vec 辅助发现 |
| 推荐为什么用 PPR？ | 多跳隐性关联 + 天然排序，比规则灵活 |
| RAG 比直接问 LLM 好在哪？ | BM25+Dense 双路检索 + RRF | 引用可溯源 | 语义缓存零延迟 |
| 你们和百度文库的区别？ | 图谱关系 + PPR + RAG，不是一个维度 |
| Node2Vec 是什么？ | 图嵌入 + 链路预测，主动发现缺失的先修关系 |
| 工业化体现在哪？ | Pydantic 校验、重试熔断缓存、结构化日志、>80% 测试覆盖、Docker + CI |

---

## 附录 A：快速环境配置

```bash
git clone https://github.com/your-org/graphcampus.git
cd graphcampus
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# 填入 LLM_API_KEY
streamlit run main.py
```

## 附录 B：依赖清单

```
streamlit>=1.28
langgraph>=0.0.20
langchain>=0.1.0
openai>=1.6
networkx>=3.1
pyvis>=0.3.1
sentence-transformers>=2.2
rank-bm25>=0.2.2
node2vec>=0.4.0
pydantic>=2.0
structlog>=24.0
pytest>=8.0
pytest-cov>=5.0
pillow>=10.0
beautifulsoup4>=4.12
```

## 附录 C：本校数据源（待填）

| 数据源 | URL | 状态 |
|--------|-----|------|
| 教务处培养方案 | 待填 | ⏳ |
| 课程大纲 | 待填 | ⏳ |
| 教师主页 | 待填 | ⏳ |
| 讲座公告 | 待填 | ⏳ |

## 附录 D：Day 1 锁死清单

| 产出 | 说明 | 状态 |
|------|------|------|
| AgentState | 含 trace_id / 缓存 / 图模型引用 | ⏳ |
| JSON Schema | 三 Agent 入参出参 | ⏳ |
| Pydantic models | Course / Teacher / Lab / Event / Log | ⏳ |
| Mock 数据 | 15 门课 + Embedding 样例 | ⏳ |
| 表结构 | courses / teachers / labs / events / logs / cache / embeddings | ⏳ |
| README | 以上全部写入 | ⏳ |

---

> 本文档由团队共同维护，随项目推进持续更新。
> 最后更新：2026 年 6 月
