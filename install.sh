#!/bin/bash

REPO="https://github.com/Emadhabibnia1385/KasbBook.git"
DIR="/opt/kasbbook"
SERVICE="kasbbook"

R='\033[31m'; G='\033[32m'; Y='\033[33m'; C='\033[36m'; M='\033[35m'; B='\033[1m'; N='\033[0m'

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
  echo -e "${C}║${N}              ${B}📊 KasbBook - Finance Manager Telegram Bot${N}                ${C}║${N}"
  echo -e "${C}║${N}                                                                        ${C}║${N}"
  echo -e "${C}║${N}                 ${B}Developer:${N} t.me/EmadHabibnia1385                       ${C}║${N}"
  echo -e "${C}║${N}                 ${B}Channel:${N}  t.me/KasbBook                                ${C}║${N}"
  echo -e "${C}║${N}                                                                        ${C}║${N}"
  echo -e "${C}╚════════════════════════════════════════════════════════════════════════╝${N}"
  echo ""
}

err() { echo -e "${R}✗ $*${N}" >&2; exit 1; }
ok() { echo -e "${G}✓ $*${N}"; }
info() { echo -e "${Y}➜ $*${N}"; }

check_root() {
  if [[ $EUID -ne 0 ]]; then
    err "Please run with sudo or as root"
  fi
}

ask_config() {
  echo ""
  info "KasbBook Configuration (required)"

  echo -n "Enter Telegram Bot TOKEN: "
  read -r BOT_TOKEN
  [[ -z "$BOT_TOKEN" ]] && err "TOKEN cannot be empty"

  echo -n "Enter Primary Admin ID (numeric): "
  read -r ADMIN_CHAT_ID
  [[ ! "$ADMIN_CHAT_ID" =~ ^[0-9]+$ ]] && err "Admin ID must be numeric"

  echo -n "Enter Primary Admin Username (example: @EmadHabibnia1385): "
  read -r ADMIN_USERNAME
  [[ -z "$ADMIN_USERNAME" ]] && err "Admin username cannot be empty"
  [[ "$ADMIN_USERNAME" != @* ]] && ADMIN_USERNAME="@${ADMIN_USERNAME}"
}

write_env() {
  cat > "$DIR/.env" << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_CHAT_ID=$ADMIN_CHAT_ID
ADMIN_USERNAME=${ADMIN_USERNAME#@}
EOF
  chmod 600 "$DIR/.env"
}

install_bot() {
  info "Installing prerequisites..."
  apt-get update -qq 2>/dev/null
  apt-get install -y -qq git python3 python3-venv python3-pip sqlite3 curl 2>/dev/null

  info "Downloading KasbBook..."
  if [[ -d "$DIR/.git" ]]; then
    cd "$DIR" && git pull -q
  else
    rm -rf "$DIR"
    git clone -q "$REPO" "$DIR"
  fi

  info "Setting up Python environment..."
  if [[ ! -d "$DIR/venv" ]]; then
    python3 -m venv "$DIR/venv"
  fi

  "$DIR/venv/bin/pip" install -q --upgrade pip wheel 2>/dev/null

  info "Installing requirements..."
  if [[ -f "$DIR/requirements.txt" ]]; then
    "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt" 2>/dev/null
  else
    # fallback (should not happen)
    "$DIR/venv/bin/pip" install -q python-telegram-bot==20.7 python-dotenv==1.0.1 jdatetime==5.0.0 pytz==2025.2 2>/dev/null
  fi

  # ✅ خواسته تو: بعد از نصب پکیج‌ها یک بار صفحه پاک بشه و منو دوباره بیاد
  clear 2>/dev/null || true
  header
  ok "Packages installed successfully!"
  echo ""

  ask_config
  write_env

  info "Creating systemd service..."
  cat > "/etc/systemd/system/$SERVICE.service" << EOF
[Unit]
Description=KasbBook Telegram Bot
After=network.target

[Service]
Type=simple
WorkingDirectory=$DIR
EnvironmentFile=$DIR/.env
ExecStart=$DIR/venv/bin/python $DIR/BOT.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload
  systemctl enable "$SERVICE" >/dev/null 2>&1
  systemctl restart "$SERVICE"

  echo ""
  ok "KasbBook installed successfully!"
  echo ""
  systemctl status "$SERVICE" --no-pager -l
}

update_bot() {
  info "Updating KasbBook from GitHub..."
  if [[ ! -d "$DIR/.git" ]]; then
    err "KasbBook not installed. Please install first."
  fi

  cd "$DIR" && git pull -q
  if [[ -f "$DIR/requirements.txt" ]]; then
    "$DIR/venv/bin/pip" install -q -r "$DIR/requirements.txt" 2>/dev/null
  fi
  systemctl restart "$SERVICE"
  ok "Updated successfully!"
}

edit_config() {
  if [[ ! -f "$DIR/.env" ]]; then
    err "Config file not found. Please install first."
  fi

  nano "$DIR/.env"
  systemctl restart "$SERVICE"
  ok "Configuration updated and bot restarted!"
}

remove_bot() {
  echo -n "Are you sure you want to remove KasbBook? (yes/no): "
  read -r confirm
  if [[ "$confirm" != "yes" ]]; then
    info "Cancelled"
    return
  fi

  systemctl stop "$SERVICE" 2>/dev/null
  systemctl disable "$SERVICE" 2>/dev/null
  rm -f "/etc/systemd/system/$SERVICE.service"
  systemctl daemon-reload
  rm -rf "$DIR"
  ok "KasbBook removed completely"
}

show_menu() {
  echo -e "${B}1)${N} Install / Reinstall"
  echo -e "${B}2)${N} Update from GitHub"
  echo -e "${B}3)${N} Edit Config (.env)"
  echo -e "${B}4)${N} Start Bot"
  echo -e "${B}5)${N} Stop Bot"
  echo -e "${B}6)${N} Restart Bot"
  echo -e "${B}7)${N} View Live Logs"
  echo -e "${B}8)${N} Bot Status"
  echo -e "${B}9)${N} Uninstall"
  echo -e "${B}0)${N} Exit"
  echo ""
}

main() {
  check_root

  while true; do
    header
    show_menu

    echo -n "Select option [0-9]: "
    read -r choice

    case $choice in
      1)
        install_bot
        echo ""
        read -p "Press Enter to continue..."
        ;;
      2)
        update_bot
        echo ""
        read -p "Press Enter to continue..."
        ;;
      3)
        edit_config
        echo ""
        read -p "Press Enter to continue..."
        ;;
      4)
        systemctl start "$SERVICE"
        ok "Bot started"
        echo ""
        read -p "Press Enter to continue..."
        ;;
      5)
        systemctl stop "$SERVICE"
        ok "Bot stopped"
        echo ""
        read -p "Press Enter to continue..."
        ;;
      6)
        systemctl restart "$SERVICE"
        ok "Bot restarted"
        echo ""
        read -p "Press Enter to continue..."
        ;;
      7)
        echo -e "${Y}Press Ctrl+C to exit logs${N}"
        sleep 2
        journalctl -u "$SERVICE" -f
        ;;
      8)
        systemctl status "$SERVICE" --no-pager -l
        echo ""
        read -p "Press Enter to continue..."
        ;;
      9)
        remove_bot
        echo ""
        read -p "Press Enter to continue..."
        ;;
      0)
        echo "Goodbye!"
        exit 0
        ;;
      *)
        err "Invalid option"
        sleep 1
        ;;
    esac
  done
}

main
