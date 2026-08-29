#!/usr/bin/env bash
# 安装 systemd 服务（需 root）
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$HERE")"
RUN_USER="$(stat -c '%U' "$APP_DIR")"

sed -e "s|^User=.*|User=$RUN_USER|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=$APP_DIR|" \
    -e "s|^Environment=HF_HOME=.*|Environment=HF_HOME=$APP_DIR/deploy_offline/hf_cache|" \
    -e "s|^ExecStart=.*|ExecStart=$APP_DIR/venv/bin/streamlit run frontend/app.py --server.address=0.0.0.0 --server.port=8501|" \
    "$HERE/graphcampus.service" > /etc/systemd/system/graphcampus.service

systemctl daemon-reload
systemctl enable graphcampus
systemctl restart graphcampus
sleep 3
systemctl status graphcampus --no-pager || true
echo ""
echo "==> 服务已安装。常用命令:"
echo "    systemctl status graphcampus   # 查看状态"
echo "    journalctl -u graphcampus -f   # 查看日志"
