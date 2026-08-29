# GraphCampus 内网服务器离线部署说明

> 适用场景：校园内网服务器（无外网 / 无 Docker），Linux x86_64 + Python 3.12.3
> 本包已包含：项目源码 + 全部 Linux wheel 依赖 + Embedding 模型离线缓存

## 包结构

```
graphcampus_offline_deploy/
├── agents/ config/ database/ frontend/ ...   # 项目源码
├── requirements.txt
└── deploy_offline/
    ├── pkgs/                 # 离线 wheel 依赖包（含 torch/sentence-transformers）
    ├── hf_cache/hub/         # Embedding 模型缓存（all-MiniLM-L6-v2）
    ├── install.sh            # 一键安装（建虚拟环境+离线装依赖+导入种子数据）
    ├── start.sh              # 前台启动
    ├── install_service.sh    # 安装 systemd 服务（开机自启）
    ├── graphcampus.service   # systemd 单元模板
    └── .env.example          # 密钥配置模板
```

## 部署步骤

### 1. 上传并解压
```bash
# 从本地电脑传输（在你的 Windows 电脑上执行）
scp graphcampus_offline_deploy.zip 用户名@服务器IP:~/
# 服务器上解压（示例放到 /opt）
sudo mkdir -p /opt/graphcampus
sudo unzip ~/graphcampus_offline_deploy.zip -d /opt/graphcampus --strip-components=1
sudo chown -R $USER:$USER /opt/graphcampus
cd /opt/graphcampus
```

### 2. 配置 LLM 密钥（.env 不在包里，需手动填）
```bash
cp deploy_offline/.env.example .env
vi .env     # 填入 LLM_API_KEY=sk-xxx
```

### 3. 一键安装
```bash
bash deploy_offline/install.sh
```
脚本会自动：创建 venv → 离线安装全部依赖（不访问外网）→ 导入种子数据。

> 若提示缺少 venv 模块（Ubuntu）：`sudo apt-get install python3.12-venv`
> 若无 root 装包权限，让管理员预先安装该包即可（包内已含全部依赖）。

### 4. 启动
```bash
# 方式一：前台启动（调试用）
bash deploy_offline/start.sh

# 方式二：systemd 服务（生产推荐，开机自启+崩溃自动重启）
sudo bash deploy_offline/install_service.sh
```

### 5. 验证
```bash
curl http://localhost:8501/_stcore/health    # 返回 ok 即成功
```
校园网内其他机器访问：`http://服务器IP:8501`

## 常见问题

| 问题 | 处理 |
|---|---|
| 问答返回"服务暂时不可用" | 检查 .env 的 Key 是否正确；服务器需能访问 api.llm.ustc.edu.cn（校园网通常可达） |
| 首次提问较慢 | Embedding 索引首次构建需几十秒，之后走缓存 |
| 换端口 | `PORT=9000 bash deploy_offline/start.sh`，或改 systemd 单元的 --server.port |
| 更新代码 | 重新打包上传后执行 `sudo systemctl restart graphcampus`；数据库在 data/ 下不会被覆盖 |
| 查看日志 | `journalctl -u graphcampus -f`；应用日志在 data/logs/graphcampus.log |

## 更新部署（代码升级时）

1. 本地重新打包（依赖无变化时可不重传 pkgs/ 和 hf_cache/，只更新源码）
2. 上传覆盖源码目录
3. `sudo systemctl restart graphcampus`
