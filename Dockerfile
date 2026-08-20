# GraphCampus —— 校园 AI 助手
# 多阶段构建：builder 编译依赖，runtime 精简运行
FROM python:3.11-slim AS builder

WORKDIR /app

# 系统依赖：编译 wheel 所需工具
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# 非 root 运行
RUN useradd -m -u 10001 graphcampus

COPY --from=builder /install /usr/local
COPY . .

# 数据目录（SQLite + 日志），挂载卷持久化
RUN mkdir -p /app/data/logs && chown -R graphcampus:graphcampus /app
USER graphcampus

# 运行期配置覆盖（config_loader 支持环境变量）
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_PORT=8501

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8501/_stcore/health')" || exit 1

CMD ["streamlit", "run", "frontend/app.py", "--server.address=0.0.0.0"]
