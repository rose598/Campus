#!/usr/bin/env bash
# GraphCampus 内网离线安装脚本
# 用法: bash deploy_offline/install.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(dirname "$HERE")"
cd "$APP_DIR"

echo "==> 项目目录: $APP_DIR"

# 1. 选择 Python（服务器为 3.12.3）
PY=python3.12
command -v "$PY" >/dev/null 2>&1 || PY=python3
echo "==> Python: $($PY --version 2>&1)"

# 2. 创建虚拟环境并离线安装全部依赖（适配 Ubuntu 缺失 python3.12-venv 的情况）
if $PY -m venv venv 2>/dev/null; then
    echo "==> 虚拟环境创建成功"
else
    echo "==> venv 模块不完整（Ubuntu 未装 python3.12-venv），改用 --without-pip 模式"
    rm -rf venv
    $PY -m venv --without-pip venv
    echo "==> 从离线包引导安装 pip ..."
    $PY "$HERE/pkgs/pip-26.2.1-py3-none-any.whl/pip" install --no-index \
        --find-links="$HERE/pkgs" pip setuptools --target="./venv/lib/python3.12/site-packages"
    PIP_BIN="$(ls -d "$APP_DIR"/venv/lib/python3.*/site-packages 2>/dev/null | head -1)/pip"
    printf '#!/usr/bin/env bash\nexec "%s" -m pip "$@"\n' "$APP_DIR/venv/bin/python" > venv/bin/pip
    chmod +x venv/bin/pip
fi
echo "==> 离线安装依赖（--no-index，不访问外网）..."
./venv/bin/pip install --no-index --find-links="$HERE/pkgs" -r requirements.txt

# 3. 配置 LLM 密钥（若 .env 不存在则从模板生成，需手动填入 Key）
if [ ! -f .env ]; then
    cp "$HERE/.env.example" .env
    echo "!! 请编辑 .env 填入 LLM_API_KEY 后再启动服务"
fi

# 4. 导入种子数据（离线，不依赖 LLM）
export HF_HOME="$HERE/hf_cache"
export HF_HUB_OFFLINE=1
./venv/bin/python scripts/seed_mock_data.py --reset

echo ""
echo "==> 安装完成！"
echo "    前台启动: bash deploy_offline/start.sh"
echo "    系统服务: sudo bash deploy_offline/install_service.sh"
