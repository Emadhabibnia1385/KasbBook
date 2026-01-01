#!/usr/bin/env bash
set -e

# =========================
# KasbBook Installer
# Repo: https://github.com/Emadhabibnia1385/KasbBook
# Channel: https://t.me/KasbBook
# =========================

# Colors
N='\033[0m'
C='\033[36m'
B='\033[1m'
M='\033[35m'
G='\033[32m'
Y='\033[33m'
R='\033[31m'

header() {
  clear 2>/dev/null || true
  echo -e "${C}╔════════════════════════════════════════════════════════════════════════╗${N}"
  echo -e "${C}║${N}                                                                        ${C}║${N}"
  echo -e "${C}║${N}  ${B}${M}██╗  ██╗ █████╗ ███████╗██████╗ ██████╗  ██████╗  ██████╗ ██╗  ██╗${N}  ${C}║${N}"
  echo -e "${C}║${N}  ${B}${M}██║ ██╔╝██╔══██╗██╔════╝██╔══██╗██╔══██╗██╔═══██╗██╔═══██╗██║ ██╔╝${N}  ${C}║${N}"
  echo -e "${C}║${N}  ${B}${M}█████╔╝ ███████║███████╗██████╔╝██████╔╝██║   ██║██║   ██║█████╔╝ ${N}  ${C}║${N}"
  echo -e "${C}║${N}  ${B}${M}██╔═██╗ ██╔══██║╚════██║██╔══██╗██╔══██╗██║   ██║██║   ██║██╔═██╗ ${N}  ${C}║${N}"
  echo -e "${C}║${N}  ${B}${M}██║  ██╗██║  ██║███████║██████╔╝██████╔╝╚██████╔╝╚██████╔╝██║  ██╗${N}  ${C}║${N}"
  echo -e "${C}║${N}  ${B}${M}╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═════╝ ╚═════╝  ╚═════╝  ╚═════╝ ╚═╝  ╚═╝${N}  ${C}║${N}"
  echo -e "${C}║${N}                                                                        ${C}║${N}"
  echo -e "${C}║${N}            ${B}${G}📊 KasbBook - Finance Manager Telegram Bot${N}                 ${C}║${N}"
  echo -e "${C}║${N}                                                                        ${C}║${N}"
  echo -e "${C}║${N}   ${B}${Y}Developer:${N} t.me/EmadHabibnia1385                              ${C}║${N}"
  echo -e "${C}║${N}   ${B}${Y}Channel:${N}   t.me/KasbBook                                      ${C}║${N}"
  echo -e "${C}║${N}                                                                        ${C}║${N}"
  echo -e "${C}╚════════════════════════════════════════════════════════════════════════╝${N}"
  echo ""
}

die() {
  echo -e "${R}❌ $1${N}"
  exit 1
}

ok() {
  echo -e "${G}✅ $1${N}"
}

info() {
  echo -e "${C}ℹ️  $1${N}"
}

# =========================
# Settings
# =========================
PROJECT_NAME="KasbBook"
REPO_URL="https://github.com/Emadhabibnia1385/KasbBook.git"
INSTALL_DIR="/opt/KasbBook"
PYTHON_BIN="python3"
SERVICE_NAME="kasbbook"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# =========================
# Start
# =========================
header

# root check
if [ "$EUID" -ne 0 ]; then
  die "Please run as root: sudo bash install.sh"
fi

info "Updating system..."
apt update -y
apt upgrade -y

info "Installing system dependencies..."
apt install -y git curl build-essential ${PYTHON_BIN} ${PYTHON_BIN}-venv ${PYTHON_BIN}-pip

# Clone/update
if [ -d "${INSTALL_DIR}/.git" ]; then
  info "Repository exists. Pulling latest changes..."
  cd "$INSTALL_DIR"
  git reset --hard
  git pull
else
  info "Cloning repository to ${INSTALL_DIR} ..."
  rm -rf "$INSTALL_DIR" 2>/dev/null || true
  git clone "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi
ok "Repository ready."

# Create venv
info "Creating virtual environment..."
${PYTHON_BIN} -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

info "Upgrading pip..."
pip install --upgrade pip

# Requirements
if [ ! -f "requirements.txt" ]; then
  die "requirements.txt not found in ${INSTALL_DIR}"
fi

info "Installing python requirements..."
pip install -r requirements.txt
ok "Python requirements installed."

# env
if [ ! -f ".env" ]; then
  if [ -f ".env.example" ]; then
    info "Creating .env from .env.example ..."
    cp .env.example .env
    ok ".env created."
  else
    info "Creating empty .env ..."
    cat > .env <<EOF
BOT_TOKEN=PUT_YOUR_BOT_TOKEN_HERE
ADMIN_CHAT_ID=123456789
ADMIN_USERNAME=admin_username
EOF
    ok ".env created."
  fi

  echo ""
  echo -e "${Y}⚠️  IMPORTANT:${N} Edit your .env now:"
  echo -e "${B}nano ${INSTALL_DIR}/.env${N}"
  echo ""
fi

# systemd service
info "Creating systemd service: ${SERVICE_NAME} ..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=KasbBook Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/python BOT.py
Restart=always
RestartSec=5
User=root

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "${SERVICE_NAME}.service"
ok "Service enabled: ${SERVICE_NAME}"

echo ""
echo -e "${G}==============================${N}"
echo -e "${G}✅ Installation Finished!${N}"
echo ""
echo -e "${B}Next steps:${N}"
echo -e "1) Edit env:"
echo -e "   nano ${INSTALL_DIR}/.env"
echo ""
echo -e "2) Start bot:"
echo -e "   systemctl start ${SERVICE_NAME}"
echo ""
echo -e "3) Logs:"
echo -e "   journalctl -u ${SERVICE_NAME} -f"
echo ""
echo -e "${B}Channel:${N} https://t.me/KasbBook"
echo -e "${G}==============================${N}"
echo ""
