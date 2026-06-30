# GraphCampus

基于 LangGraph 状态图的四智能体校园助手。

## Day 1 锁定内容

### AgentState
- 定义于 `models/state.py`，包含对话历史、课程图谱、RAG 索引、校园文档库等核心字段。

### Pydantic 数据模型
- `Course`：课程信息（代码、学分、先修、教师等）
- `Teacher`：教师信息
- `Lab`：实验室信息
- `Event`：讲座/竞赛
- `CampusDocument` + `Chunk`：校园非结构化文档及分块

### 配置
- `config/config.yaml`：应用全局参数
- `config/feature_flags.py`：特征开关

### 数据库
- `database/schema.sql`：SQLite 表结构（courses, documents, chunks, embeddings, cache, logs 等）

### 开发启动
```bash
git clone <repo>
cd graphcampus
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env  # 填入 API Key
streamlit run main.py