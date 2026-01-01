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

err() { echo -e "${R}✗ $*${N}" >&2; read -p "Press Enter to continue..." _; return 1; }
ok() { echo -e "${G}✓ $*${N}"; }
info() { echo -e "${Y}➜ $*${N}"; }

pause() { echo ""; read -p "Press Enter to continue..." _; }

check_root() {
  if [[ $EUID -ne 0 ]]; then
    echo -e "${R}✗ Please run with sudo or as root${N}"
    exit 1
  fi
}

run_silent() {
  # run command silently; if fails, show error
  "$@" >/dev/null 2>&1
}

ask_config() {
  echo ""
  info "KasbBook Configuration (required)"

  echo -n "Enter Telegram Bot TOKEN: "
  read -r BOT_TOKEN
  [[ -z "$BOT_TOKEN" ]] && { err "TOKEN cannot be empty"; return 1; }

  echo -n "Enter Primary Admin ID (numeric): "
  read -r ADMIN_CHAT_ID
  [[ ! "$ADMIN_CHAT_ID" =~ ^[0-9]+$ ]] && { err "Admin ID must be numeric"; return 1; }

  echo -n "Enter Primary Admin Username (example: @EmadHabibnia1385): "
  read -r ADMIN_USERNAME
  [[ -z "$ADMIN_USERNAME" ]] && { err "Admin username cannot be empty"; return 1; }
  [[ "$ADMIN_USERNAME" != @* ]] && ADMIN_USERNAME="@${ADMIN_USERNAME}"

  return 0
}

write_env() {
  cat > "$DIR/.env" << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_CHAT_ID=$ADMIN_CHAT_ID
ADMIN_USERNAME=${ADMIN_USERNAME#@}
EOF
  chmod 600 "$DIR/.env" >/dev/null 2>&1 || true
}

create_service() {
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

  run_silent systemctl daemon-reload || return 1
  run_silent systemctl enable "$SERVICE" || return 1
  run_silent systemctl restart "$SERVICE" || return 1
  return 0
}

install_bot() {
  info "Installing prerequisites..."
  run_silent apt-get update -qq || { err "apt update failed"; return 1; }
  run_silent apt-get install -y -qq git python3 python3-venv python3-pip sqlite3 curl || { err "apt install failed"; return 1; }

  info "Downloading KasbBook..."
  if [[ -d "$DIR/.git" ]]; then
    (cd "$DIR" && run_silent git pull -q) || { err "git pull failed"; return 1; }
  else
    run_silent rm -rf "$DIR"
    run_silent git clone -q "$REPO" "$DIR" || { err "git clone failed"; return 1; }
  fi

  info "Setting up Python environment..."
  if [[ ! -d "$DIR/venv" ]]; then
    run_silent python3 -m venv "$DIR/venv" || { err "venv create failed"; return 1; }
  fi

  run_silent "$DIR/venv/bin/pip" install --upgrade pip wheel || { err "pip upgrade failed"; return 1; }

  info "Installing requirements..."
  if [[ -f "$DIR/requirements.txt" ]]; then
    run_silent "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" || { err "requirements install failed"; return 1; }
  else
    run_silent "$DIR/venv/bin/pip" install python-telegram-bot==20.7 python-dotenv==1.0.1 jdatetime==5.0.0 pytz==2025.2 || { err "pip install failed"; return 1; }
  fi

  # ✅ خواسته تو: بعد از نصب پکیج‌ها یک بار صفحه پاک شود و منو دوباره بیاد
  header
  ok "Packages downloaded & installed successfully!"
  echo ""

  ask_config || return 1
  write_env

  create_service || { err "service create/restart failed"; return 1; }

  echo ""
  ok "KasbBook installed successfully!"
  echo ""
  systemctl status "$SERVICE" --no-pager -l
  return 0
}

update_bot() {
  info "Updating KasbBook from GitHub..."
  [[ -d "$DIR/.git" ]] || { err "Not installed. Install first."; return 1; }

  (cd "$DIR" && run_silent git pull -q) || { err "git pull failed"; return 1; }

  info "Updating requirements..."
  if [[ -f "$DIR/requirements.txt" ]]; then
    run_silent "$DIR/venv/bin/pip" install -r "$DIR/requirements.txt" || { err "requirements update failed"; return 1; }
  fi

  run_silent systemctl restart "$SERVICE" || { err "restart failed"; return 1; }

  header
  ok "Updated successfully!"
  return 0
}

edit_config() {
  [[ -f "$DIR/.env" ]] || { err "Config not found. Install first."; return 1; }
  nano "$DIR/.env"
  run_silent systemctl restart "$SERVICE" || { err "restart failed"; return 1; }
  header
  ok "Configuration updated and bot restarted!"
  return 0
}

remove_bot() {
  echo -n "Are you sure you want to remove KasbBook? (yes/no): "
  read -r confirm
  if [[ "$confirm" != "yes" ]]; then
    info "Cancelled"
    return 0
  fi

  run_silent systemctl stop "$SERVICE"
  run_silent systemctl disable "$SERVICE"
  run_silent rm -f "/etc/systemd/system/$SERVICE.service"
  run_silent systemctl daemon-reload
  run_silent rm -rf "$DIR"

  header
  ok "KasbBook removed completely"
  return 0
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
      1) install_bot; pause ;;
      2) update_bot; pause ;;
      3) edit_config; pause ;;
      4) run_silent systemctl start "$SERVICE" && header && ok "Bot started"; pause ;;
      5) run_silent systemctl stop "$SERVICE" && header && ok "Bot stopped"; pause ;;
      6) run_silent systemctl restart "$SERVICE" && header && ok "Bot restarted"; pause ;;
      7)
        echo -e "${Y}Press Ctrl+C to exit logs${N}"
        sleep 2
        journalctl -u "$SERVICE" -f
        ;;
      8)
        systemctl status "$SERVICE" --no-pager -l
        pause
        ;;
      9) remove_bot; pause ;;
      0) echo "Goodbye!"; exit 0 ;;
      *) header; echo -e "${R}Invalid option${N}"; sleep 1 ;;
    esac
  done
}

main
