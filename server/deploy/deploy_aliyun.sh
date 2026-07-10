#!/bin/bash
# Agix Auth Server 部署脚本 (Alibaba Cloud Linux 3 / RHEL 系)
set -e

APP_DIR="/opt/agix-auth"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/agix-auth"

echo "=== 1. 安装系统依赖 ==="
dnf install -y python3 python3-pip python3-devel nginx

echo "=== 2. 创建目录和用户 ==="
mkdir -p $APP_DIR $LOG_DIR $APP_DIR/server
# nginx 在 alinux 上用户是 nginx
mkdir -p /var/log/nginx
chown -R nginx:nginx $LOG_DIR /var/log/nginx

echo "=== 3. 创建虚拟环境 ==="
python3 -m venv $VENV_DIR

echo "=== 4. 安装 Python 依赖 ==="
$VENV_DIR/bin/pip install flask gunicorn -i https://mirrors.aliyun.com/pypi/simple/

echo "=== 5. 创建 systemd 服务 ==="
cat > /etc/systemd/system/agix-auth.service << 'SVC'
[Unit]
Description=Agix Auth Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/agix-auth/server
ExecStart=/opt/agix-auth/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 --access-logfile /var/log/agix-auth/access.log --error-logfile /var/log/agix-auth/error.log --log-level info app:app
Restart=always
RestartSec=5
Environment=AGIX_TOKEN_EXPIRE_SECONDS=2592000
Environment=AGIX_DB_PATH=/opt/agix-auth/server/tokens.db

[Install]
WantedBy=multi-user.target
SVC

echo "=== 6. 配置 Nginx ==="
cat > /etc/nginx/conf.d/agix-auth.conf << 'NGX'
server {
    listen 80;
    server_name _;

    access_log /var/log/nginx/agix-auth-access.log;
    error_log  /var/log/nginx/agix-auth-error.log;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
NGX

echo "=== 7. 开放防火墙 ==="
firewall-cmd --add-port=80/tcp --permanent 2>/dev/null || true
firewall-cmd --reload 2>/dev/null || true

echo "=== 8. 启动服务 ==="
systemctl daemon-reload
systemctl enable agix-auth nginx
systemctl restart agix-auth nginx

echo ""
echo "========================================="
echo "  部署完成！"
echo "  服务端地址: http://8.130.188.188"
echo ""
echo "  Flet 客户端设置:"
echo "  export AGIX_AUTH_SERVER=http://8.130.188.188"
echo ""
echo "  查看状态:"
echo "  systemctl status agix-auth nginx"
echo "========================================="
