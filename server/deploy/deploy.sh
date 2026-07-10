#!/bin/bash
# Agix Auth Server 部署脚本 (阿里云 ECS Ubuntu/Debian)
set -e

APP_DIR="/opt/agix-auth"
VENV_DIR="$APP_DIR/venv"
LOG_DIR="/var/log/agix-auth"

echo "=== 1. 安装系统依赖 ==="
sudo apt update
sudo apt install -y python3 python3-venv python3-pip nginx

echo "=== 2. 创建目录 ==="
sudo mkdir -p $APP_DIR $LOG_DIR
sudo chown -R $USER:$USER $APP_DIR
sudo chown -R www-data:www-data $LOG_DIR

echo "=== 3. 复制代码 ==="
cp -r ../* $APP_DIR/server/

echo "=== 4. 创建虚拟环境 ==="
python3 -m venv $VENV_DIR
$VENV_DIR/bin/pip install -r $APP_DIR/server/requirements.txt

echo "=== 5. 配置 systemd ==="
sudo cp agix-auth.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable agix-auth
sudo systemctl restart agix-auth

echo "=== 6. 配置 Nginx ==="
sudo cp nginx.conf /etc/nginx/sites-available/agix-auth
sudo ln -sf /etc/nginx/sites-available/agix-auth /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx

echo "=== 7. 开放防火墙 ==="
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

echo ""
echo "=== 部署完成 ==="
echo "服务端地址: http://$(curl -s ifconfig.me)"
echo "设置客户端: export AGIX_AUTH_SERVER=http://$(curl -s ifconfig.me)"
