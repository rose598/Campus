# GraphCampus

> 基于 LangGraph 状态图的多智能体校园助手

**GraphCampus** 是一个面向本校师生的智慧校园助手，通过多智能体协作提供三大核心功能：**活动智能推送**、**校园知识问答**、**课程资料收集与总结**。

---

## ✨ 核心功能

| 功能 | 说明 | 核心算法 |
|------|------|---------|
| 📡 **活动智能推送** | 根据课程和兴趣推荐匹配的讲座、竞赛、科研机会 | Personalized PageRank |
| ❓ **校园知识问答** | 保研/转专业/选课等政策问题秒回，带来源引用 | Hybrid RAG (BM25 + Dense) |
| 📚 **课程资料总结** | 自动收集课件/大纲/期末资料，生成结构化总结 | LLM 提取 + RAG |

---

## 🏗️ 技术架构

```
┌─────────────────────────────────────────────────┐
│              Streamlit 前端 (角色 B)              │
│  app.py → 01~05 页面 + chat_ui / source_card    │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────┐
│           LangGraph 父图 (角色 A)                │
│  路由 → 情报官 / 百事通 / 学伴 (Fan-out)         │
├─────────────┬──────────────┬────────────────────┤
│  情报官子图  │  百事通子图   │   学伴子图          │
│  PPR 推荐   │  知识问答     │   课程总结          │
└──────┬──────┴──────┬───────┴──────┬─────────────┘
       │             │              │
┌──────┴─────────────┴──────────────┴─────────────┐
│                  基础设施层                        │
│  utils/ (LLM/Embedding/日志/限流/错误码)          │
│  database/ (SQLite WAL + CRUD)                   │
│  config/ (YAML + 特征开关 + .env)                 │
└─────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 |
|------|------|
| 前端 | Streamlit (多页面路由 + 组件化) |
| 智能体 | LangGraph (状态图编排) |
| 检索 | BM25 + Dense Embedding + RRF 融合 |
| 推荐 | Personalized PageRank (NetworkX) |
| 数据模型 | Pydantic v2 |
| 数据库 | SQLite (WAL 模式) |
| 配置 | YAML + .env + 特征开关 |

---

## 📁 项目结构

```
graphcampus/
├── main.py                          # 入口（待实现）
├── config/
│   ├── config.yaml                  # 全局配置（LLM/RAG/特征开关参数）
│   ├── feature_flags.py             # 特征开关字典
│   └── .env.example                 # 环境变量模板
├── models/
│   ├── agent_state.py               # AgentState 核心数据结构
│   ├── course.py                    # Course / Prerequisite
│   ├── event.py                     # Event（讲座/竞赛）
│   ├── campus_document.py           # CampusDocument / Chunk
│   ├── teacher.py                   # Teacher
│   ├── lab.py                       # Lab
│   └── log.py                       # LogEntry
├── database/
│   ├── connection.py                # SQLite 连接（WAL 模式）
│   ├── schema.py                    # 建表 DDL
│   ├── schema.sql                   # SQL 建表脚本
│   └── crud.py                      # CRUD 操作（6 张表）
├── utils/
│   ├── llm_client.py                # LLM 中枢（重试/熔断/并发/限速）
│   ├── embedding_client.py          # Embedding 封装
│   ├── config_loader.py             # 配置加载（YAML + .env + 热加载）
│   ├── rate_limiter.py              # 滑动窗口速率限制
│   ├── tracer.py                    # 结构化日志 + trace_id
│   └── error_codes.py               # 错误码体系（E001–E008）
├── frontend/
│   ├── app.py                       # Streamlit 主入口 + 路由
│   ├── state_sync.py                # 前端状态同步（session_state 封装）
│   ├── pages/
│   │   ├── 01_activity_push.py      # 📡 活动推送页
│   │   ├── 02_campus_qa.py          # ❓ 知识问答页（对话式）
│   │   ├── 03_course_materials.py   # 📚 课程资料页
│   │   ├── 04_settings.py           # ⚙️ 系统设置页
│   │   ├── 05_onboarding.py         # 🚀 冷启动引导页
│   │   └── page_course_map.py       # 🗺️ 课程地图页
│   └── components/
│       ├── chat_ui.py               # 对话 UI 组件
│       ├── source_card.py           # 来源引用卡片组件
│       ├── loading_states.py        # 通用状态组件
│       └── interrupt_modal.py       # 中断交互弹窗
├── agents/                          # 智能体（待实现）
├── knowledge_graph/                 # PPR 推荐引擎（待实现）
├── rag/                             # 混合检索引擎（待实现）
├── campus_qa/                       # 知识问答引擎（待实现）
├── data_pipeline/                   # 数据管道（待实现）
├── crawler/                         # 爬虫（待实现）
├── tests/                           # 测试（待实现）
├── data/
│   ├── mock_courses.json            # Mock 课程数据
│   └── graphcampus.db               # SQLite 数据库
└── requirements.txt
```

---

## 🚀 快速启动

```bash
# 1. 克隆仓库
git clone https://github.com/rose598/Campus.git
cd Campus

# 2. 创建虚拟环境
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp config/.env.example .env    # 填入 LLM_API_KEY

# 5. 启动前端
streamlit run frontend/app.py
```

---

## 👥 团队分工

| 角色 | 时间 | 核心职责 |
|------|------|---------|
| **A** | 6h/天 | 架构 + 核心算法（PPR/RAG）+ 工业化基建 |
| **B** | 3h/天 | Streamlit 前端 + 所有页面与交互组件 |
| **C** | 4h/天 | 校园知识问答引擎 + 爬虫 + 课程数据处理 |
| **D** | 3h/天 | 数据库 + 测试 + Docker + CI + 文档 |

---

## 📊 开发进度

### 已完成 ✅

| 模块 | 内容 | 状态 |
|------|------|------|
| **数据模型** | AgentState + 6 个 Pydantic 模型 | ✅ |
| **配置体系** | config.yaml + feature_flags + .env | ✅ |
| **数据库** | SQLite 连接 + 建表 DDL + 6 个 CRUD 类 | ✅ |
| **工具层** | LLM 客户端 / Embedding / 速率限制 / 日志 / 配置加载 / 错误码 | ✅ |
| **前端骨架** | Streamlit 多页面路由 + 侧边栏导航 | ✅ |
| **活动推送页** | 推荐列表 + 分数展示 + 推理链 + 排序筛选 | ✅ |
| **知识问答页** | 分类 Tab + 对话 UI + Mock 百事通 + 来源引用 | ✅ |
| **冷启动引导** | 4 步引导流程（欢迎→专业→兴趣→课程） | ✅ |
| **通用组件** | chat_ui / source_card / loading_states / interrupt_modal | ✅ |
| **状态管理** | state_sync 封装 + 多页面独立聊天历史 | ✅ |

### 待实现 🚧

| 模块 | 内容 |
|------|------|
| **agents/** | 父图编排 + 三子图（情报官/百事通/学伴） |
| **knowledge_graph/** | PPR 推荐引擎 |
| **rag/** | BM25 + Dense + Hybrid + Query Rewriting + 语义缓存 |
| **campus_qa/** | 意图分类 + 路由 + 时间排序 + 融合 + 引用格式化 |
| **data_pipeline/** | 文档解析 + 清洗 + 分块 + 标注 + 索引构建 |
| **crawler/** | 政策爬虫 + 活动爬虫 |
| **tests/** | 单元测试 + 集成测试 |
| **docker/** | Dockerfile + CI/CD |

---

## ⚙️ 配置说明

### config.yaml

```yaml
llm:
  model: gpt-4o-mini
  temperature: 0.3
  max_retries: 3

rag:
  bm25_top_k: 5
  dense_top_k: 5
  rrf_k: 60
  chunk_size: 512

features:
  activity_push: true
  campus_qa: true
  course_summary: true
```

### 特征开关

```python
# config/feature_flags.py
FEATURE_FLAGS = {
    "activity_push": True,    # 活动智能推送
    "campus_qa": True,        # 校园知识问答
    "course_summary": True,   # 课程资料总结
}
```

### 错误码

| 错误码 | 含义 |
|--------|------|
| E001 | LLM 调用失败 |
| E002 | Embedding 服务异常 |
| E003 | 数据库操作失败 |
| E004 | 配置加载失败 |
| E005 | 数据解析失败 |
| E006 | 检索无结果 |
| E007 | 速率限制触发 |
| E008 | 未知错误 |

---

## 📝 License

本项目为课程大作业，仅供教学演示使用。
