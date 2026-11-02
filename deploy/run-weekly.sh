#!/usr/bin/env bash
# Ручний запуск (від root): bash /opt/instagram-report/deploy/run-weekly.sh buro|veryvery weekly|monthly test|manual
#   test   — зібрати звіт, зберегти картинку і текст у /var/lib/instagram-report/out/<brand>/, у чат не слати
#   manual — надіслати в чат зараз
set -euo pipefail
BRAND=${1:?вкажіть buro або veryvery}; KIND=${2:-weekly}; MODE=${3:-test}
case "$KIND" in weekly|monthly) ;; *) echo "вид: weekly або monthly"; exit 1;; esac
case "$MODE" in test|manual) ;; *) echo "режим: test або manual"; exit 1;; esac
ENV=/etc/instagram-report/weekly-$BRAND.env
[ -f "$ENV" ] || { echo "немає файлу $ENV"; exit 1; }
exec runuser -u igreport -- bash -c "set -a; . '$ENV'; set +a; cd /opt/instagram-report && exec .venv/bin/python -m weekly.main --kind $KIND --mode $MODE"
