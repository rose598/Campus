# GraphCampus

基于 LangGraph 状态图的四智能体校园助手。

## Day 1 锁定内容

### AgentState
- 定义于 `models/agent_state.py`，包含对话历史、课程图谱、RAG 索引、校园文档库等核心字段。

### Pydantic 数据模型
- `Course`：课程信息（代码、学分、先修、教师等）
- `Teacher`：教师信息
- `Lab`：实验室信息
- `Event`：讲座/竞赛
- `CampusDocument` + `Chunk`：校园非结构化文档及分块
- `LogEntry`：结构化日志条目

### 配置
- `config/config.yaml`：应用全局参数
- `config/feature_flags.py`：特征开关
- `config/.env.example`：环境变量模板

### 数据库
- `database/schema.sql`：SQLite 表结构（courses, documents, chunks, embeddings, cache, logs 等）

## Day 2 产出

### LLM 调用层
- `utils/llm_client.py`：LLM 中枢，封装 OpenAI 调用 + 重试（3 次指数退避）+ 熔断器（5 失败→30s 快速失败）+ 并发控制（max=3）+ 速率限制
- `utils/embedding_client.py`：Embedding 服务封装（sentence-transformers），提供 embed / embed_batch / cosine_similarity
- `utils/rate_limiter.py`：滑动窗口速率限制（默认 10 次/分钟/用户），支持白名单

## Day 3 产出

### 结构化日志
- `utils/tracer.py`：Tracer 类，每条请求生成唯一 trace_id，提供节点计时上下文管理器，JSON 格式日志输出

### 配置中心
- `utils/config_loader.py`：YAML 加载 + 环境变量覆盖 + 运行时热加载（reload / set 方法）

### 错误码体系
- `utils/error_codes.py`：8 个标准错误码（E001–E008），统一异常基类 `GraphCampusError`

## 开发启动
```bash
git clone <repo>
cd graphcampus
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # 填入 API Key
streamlit run main.py