#!/usr/bin/env bash
# تثبيت نظام حجز القاعات للجمعية على الخادم (Ubuntu): آمن للتكرار، ولا يمسح بيانات.
#   curl -fsSL https://raw.githubusercontent.com/AcsVe/nues/main/deploy/install_server.sh | bash
# يضع النظام في /opt/ras/ACS ويشغّله خدمة اسمها acs-ras على المنفذ 8110.
set -euo pipefail

DIR=/opt/ras/ACS
SERVICE=acs-ras
PORT=8110
REPO=https://github.com/AcsVe/nues.git
RUN_USER="$(id -un)"

echo "==> Folder"
sudo mkdir -p /opt/ras
sudo chown "$RUN_USER":"$RUN_USER" /opt/ras

echo "==> Code"
if [ -d "$DIR/.git" ]; then
  git -C "$DIR" pull --ff-only origin main
else
  git clone "$REPO" "$DIR"
fi

echo "==> Python environment"
cd "$DIR"
[ -d .venv ] || python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt

echo "==> Settings file"
if [ ! -f .env ]; then
  cp .env.example .env
  sed -i "s/^PORT=.*/PORT=$PORT/" .env
  chmod 600 .env
  echo "Created .env (edit it to add the Microsoft 365 mail values)."
fi

echo "==> Service"
sudo tee /etc/systemd/system/$SERVICE.service >/dev/null <<UNIT
[Unit]
Description=ACS venue booking
After=network.target

[Service]
User=$RUN_USER
WorkingDirectory=$DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$DIR/.venv/bin/python serve.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
UNIT
sudo systemctl daemon-reload
sudo systemctl enable --now $SERVICE
sudo systemctl restart $SERVICE

echo "==> Daily backup (03:15)"
CRON="15 3 * * * $DIR/.venv/bin/python $DIR/ops/backup.py >> $DIR/logs/backup.log 2>&1"
mkdir -p "$DIR/logs"
{ crontab -l 2>/dev/null | grep -v "ops/backup.py" || true; echo "$CRON"; } | crontab -

sleep 3
echo "==> Check"
systemctl is-active $SERVICE
curl -s -o /dev/null -w 'health=%{http_code}\n' http://127.0.0.1:$PORT/healthz
echo
echo "Next: create the administrator (hidden password):"
echo "  cd $DIR && IAJ_LANG=en .venv/bin/python ops/reset_password.py --create"
