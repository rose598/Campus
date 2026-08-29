#!/usr/bin/env bash
# GraphCampus 前台启动脚本
HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$HERE")"
cd "$APP_DIR"

source venv/bin/activate

# Embedding 模型离线缓存（内网无 HuggingFace 访问）
export HF_HOME="$HERE/hf_cache"
export HF_HUB_OFFLINE=1

exec streamlit run frontend/app.py --server.address=0.0.0.0 --server.port="${PORT:-8501}"
