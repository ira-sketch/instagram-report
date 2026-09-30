#!/usr/bin/env bash
# Обновление кода с GitHub: sudo bash /opt/instagram-report/deploy/update.sh
set -euo pipefail
cd /opt/instagram-report
git pull --ff-only
.venv/bin/pip install -q -r requirements.txt
install -m 644 deploy/systemd/ig-report@.service deploy/systemd/ig-report@.timer \
  deploy/systemd/ig-report-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl restart ig-report-bot.service || true
echo "Обновлено: $(git log -1 --format='%h %s')"
