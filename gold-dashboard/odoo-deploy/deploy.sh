#!/bin/bash
# ============================================================
#  Odoo 17 一键部署脚本
#  运行环境：Ubuntu 22.04 服务器
#  用法：bash deploy.sh
# ============================================================

set -euo pipefail

# -------- 颜色输出 --------
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

DEPLOY_DIR="$(cd "$(dirname "$0")" && pwd)"

# ============================================================
# 1. 检查 root 权限
# ============================================================
[[ $EUID -ne 0 ]] && error "请用 root 或 sudo 运行此脚本"

# ============================================================
# 2. 读取 .env 配置
# ============================================================
ENV_FILE="$DEPLOY_DIR/.env"
[[ ! -f "$ENV_FILE" ]] && error ".env 文件不存在，请先执行：cp .env.example .env 并填写配置"

source "$ENV_FILE"

[[ -z "${DB_USER:-}"       ]] && error ".env 缺少 DB_USER"
[[ -z "${DB_PASSWORD:-}"   ]] && error ".env 缺少 DB_PASSWORD"
[[ -z "${DOMAIN:-}"        ]] && error ".env 缺少 DOMAIN"
[[ -z "${ADMIN_PASSWD:-}"  ]] && error ".env 缺少 ADMIN_PASSWD"

info "部署域名：$DOMAIN"

# ============================================================
# 3. 安装 Docker & Docker Compose
# ============================================================
install_docker() {
    info "安装 Docker..."
    apt-get update -qq
    apt-get install -y -qq ca-certificates curl gnupg lsb-release

    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
      > /etc/apt/sources.list.d/docker.list

    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable --now docker
    success "Docker 安装完成"
}

if ! command -v docker &>/dev/null; then
    install_docker
else
    success "Docker 已安装：$(docker --version)"
fi

# Docker Compose v2
if ! docker compose version &>/dev/null; then
    apt-get install -y -qq docker-compose-plugin
fi
success "Docker Compose：$(docker compose version)"

# ============================================================
# 4. 申请 SSL 证书（Let's Encrypt / Certbot）
#    如果 DOMAIN 是 IP 地址则跳过，使用 HTTP 模式
# ============================================================
SSL_DIR="$DEPLOY_DIR/nginx/ssl"
mkdir -p "$SSL_DIR"

is_ip() {
    [[ "$1" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]
}

USE_HTTPS=true
if is_ip "$DOMAIN"; then
    warn "DOMAIN 是 IP 地址，跳过 SSL，使用 HTTP 模式"
    USE_HTTPS=false
fi

if $USE_HTTPS; then
    if [[ ! -f "$SSL_DIR/fullchain.pem" ]]; then
        info "申请 Let's Encrypt SSL 证书..."
        apt-get install -y -qq certbot

        # 临时放行 80 端口（若 Nginx 已运行先停）
        docker compose -f "$DEPLOY_DIR/docker-compose.yml" stop nginx 2>/dev/null || true

        certbot certonly --standalone \
            --non-interactive \
            --agree-tos \
            --email "admin@${DOMAIN}" \
            -d "$DOMAIN"

        cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem "$SSL_DIR/"
        cp /etc/letsencrypt/live/$DOMAIN/privkey.pem   "$SSL_DIR/"
        success "SSL 证书已申请并复制"

        # 自动续期 cron
        (crontab -l 2>/dev/null; echo "0 3 * * * certbot renew --quiet && \
            cp /etc/letsencrypt/live/$DOMAIN/fullchain.pem $SSL_DIR/ && \
            cp /etc/letsencrypt/live/$DOMAIN/privkey.pem $SSL_DIR/ && \
            docker compose -f $DEPLOY_DIR/docker-compose.yml restart nginx") | crontab -
        success "SSL 自动续期已配置"
    else
        success "SSL 证书已存在，跳过申请"
    fi
fi

# ============================================================
# 5. 替换配置文件中的占位符
# ============================================================
info "写入运行时配置..."

# odoo.conf
sed \
    -e "s|ADMIN_PASSWD_PLACEHOLDER|${ADMIN_PASSWD}|g" \
    -e "s|DB_USER_PLACEHOLDER|${DB_USER}|g" \
    -e "s|DB_PASSWORD_PLACEHOLDER|${DB_PASSWORD}|g" \
    "$DEPLOY_DIR/odoo.conf" > "$DEPLOY_DIR/odoo.conf.runtime"
mv "$DEPLOY_DIR/odoo.conf.runtime" "$DEPLOY_DIR/odoo.conf"

# nginx 配置
NGINX_CONF="$DEPLOY_DIR/nginx/odoo.conf"
if $USE_HTTPS; then
    sed -i "s|DOMAIN_PLACEHOLDER|${DOMAIN}|g" "$NGINX_CONF"
else
    # HTTP only 模式：覆盖 nginx 配置
    cat > "$NGINX_CONF" <<NGINXEOF
upstream odoo_backend     { server odoo:8069; }
upstream odoo_longpolling { server odoo:8072; }

server {
    listen 80;
    server_name ${DOMAIN};
    client_max_body_size 200m;
    proxy_read_timeout   720s;
    proxy_connect_timeout 300s;

    proxy_set_header Host              \$host;
    proxy_set_header X-Real-IP         \$remote_addr;
    proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto \$scheme;

    location /longpolling/ { proxy_pass http://odoo_longpolling; }
    location / {
        proxy_pass http://odoo_backend;
        proxy_redirect off;
    }
    location ~* /web/static/ {
        proxy_pass http://odoo_backend;
        expires 864000;
        add_header Cache-Control "public, immutable";
    }
}
NGINXEOF
    warn "已生成 HTTP only Nginx 配置（无 SSL）"
fi

# ============================================================
# 6. 创建 addons 目录（自定义插件）
# ============================================================
mkdir -p "$DEPLOY_DIR/addons"

# ============================================================
# 7. 启动服务
# ============================================================
info "拉取 Docker 镜像（首次较慢，请耐心等待）..."
cd "$DEPLOY_DIR"
docker compose pull

info "启动所有服务..."
docker compose up -d --remove-orphans

# ============================================================
# 8. 等待 Odoo 就绪
# ============================================================
info "等待 Odoo 启动..."
MAX_WAIT=120
WAITED=0
until curl -sf http://127.0.0.1:8069/web/health &>/dev/null; do
    sleep 3
    WAITED=$((WAITED + 3))
    if [[ $WAITED -ge $MAX_WAIT ]]; then
        warn "Odoo 启动超时，请检查日志：docker compose logs odoo"
        break
    fi
    echo -n "."
done
echo ""

# ============================================================
# 9. 完成提示
# ============================================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN}  Odoo 17 部署完成！${NC}"
echo -e "${GREEN}============================================${NC}"
if $USE_HTTPS; then
    echo -e "  访问地址：${BLUE}https://${DOMAIN}${NC}"
else
    echo -e "  访问地址：${BLUE}http://${DOMAIN}${NC}"
fi
echo ""
echo -e "  常用命令："
echo -e "    查看日志：  ${YELLOW}docker compose logs -f odoo${NC}"
echo -e "    重启服务：  ${YELLOW}docker compose restart${NC}"
echo -e "    停止服务：  ${YELLOW}docker compose down${NC}"
echo -e "    更新镜像：  ${YELLOW}docker compose pull && docker compose up -d${NC}"
echo -e "${GREEN}============================================${NC}"
