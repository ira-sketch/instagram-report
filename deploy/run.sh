#!/usr/bin/env bash
# Ручной запуск: sudo bash /opt/instagram-report/deploy/run.sh report1 test|manual
#   test   — показать отчёт на экране, в чат не отправлять
#   manual — отправить в чат сейчас
set -euo pipefail
NAME=${1:?укажите report1 или report2}; MODE=${2:-test}
case "$MODE" in test|manual) ;; *) echo "режим: test или manual"; exit 1;; esac
[ -f "/etc/instagram-report/$NAME.env" ] || { echo "нет файла /etc/instagram-report/$NAME.env"; exit 1; }
exec sudo -u igreport bash -c "set -a; . '/etc/instagram-report/$NAME.env'; set +a; cd /opt/instagram-report && exec .venv/bin/python -m report.main --mode $MODE"
