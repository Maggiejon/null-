#!/bin/bash
# ============================================================
#  本地执行：将部署包上传到服务器并自动运行
#  用法：bash push-to-server.sh <服务器IP> [SSH用户] [SSH端口]
#  示例：bash push-to-server.sh 1.2.3.4
#         bash push-to-server.sh 1.2.3.4 ubuntu 22
# ============================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC}   $*"; }
error()   { echo -e "${RED}[ERR]${NC}  $*"; exit 1; }

# -------- 参数 --------
SERVER_IP="${1:-}"
SSH_USER="${2:-root}"
SSH_PORT="${3:-22}"
REMOTE_DIR="/opt/odoo-deploy"

[[ -z "$SERVER_IP" ]] && error "用法: bash push-to-server.sh <服务器IP> [用户名=root] [端口=22]"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# -------- 检查 .env --------
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
    error ".env 文件不存在！\n请先执行：\n  cd $(basename $SCRIPT_DIR)\n  cp .env.example .env\n  nano .env   # 填写你的配置"
fi

SSH_OPTS="-p $SSH_PORT -o StrictHostKeyChecking=no -o ConnectTimeout=10"

info "测试 SSH 连接 $SSH_USER@$SERVER_IP:$SSH_PORT ..."
ssh $SSH_OPTS ${SSH_USER}@${SERVER_IP} "echo 'SSH OK'" || error "SSH 连接失败，请检查 IP/用户名/端口/密钥"

info "在服务器创建部署目录 $REMOTE_DIR ..."
ssh $SSH_OPTS ${SSH_USER}@${SERVER_IP} "mkdir -p $REMOTE_DIR"

info "上传部署文件..."
rsync -az --progress \
    -e "ssh $SSH_OPTS" \
    --exclude='.git' \
    --exclude='*.pyc' \
    "$SCRIPT_DIR/" \
    "${SSH_USER}@${SERVER_IP}:${REMOTE_DIR}/"

info "设置脚本权限..."
ssh $SSH_OPTS ${SSH_USER}@${SERVER_IP} "chmod +x $REMOTE_DIR/deploy.sh"

info "在服务器执行部署脚本..."
ssh $SSH_OPTS -t ${SSH_USER}@${SERVER_IP} "cd $REMOTE_DIR && sudo bash deploy.sh"

success "全部完成！"
