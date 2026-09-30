#!/usr/bin/env bash
# Установка отчётов на сервер (Ubuntu / Debian). Запуск: sudo bash /opt/instagram-report/deploy/install.sh
set -euo pipefail
APP=/opt/instagram-report
CONF=/etc/instagram-report
DATA=/var/lib/instagram-report

[ "$(id -u)" = 0 ] || { echo "Запустите через sudo"; exit 1; }
[ -f "$APP/report/main.py" ] || { echo "Код должен лежать в $APP (git clone ... $APP)"; exit 1; }

echo "== Пакеты"
apt-get update -qq
apt-get install -y -qq python3 python3-venv git tzdata >/dev/null

echo "== Пользователь igreport (без входа в систему)"
id igreport >/dev/null 2>&1 || useradd --system --home-dir "$DATA" --shell /usr/sbin/nologin igreport
install -d -o igreport -g igreport -m 700 "$DATA"
install -d -o root -g igreport -m 750 "$CONF"

echo "== Python-окружение"
python3 -m venv "$APP/.venv"
"$APP/.venv/bin/pip" install -q --upgrade pip
"$APP/.venv/bin/pip" install -q -r "$APP/requirements.txt"

echo "== Файлы настроек"
for r in report1 report2; do
  if [ ! -f "$CONF/$r.env" ]; then
    install -o root -g igreport -m 640 "$APP/deploy/$r.env.example" "$CONF/$r.env"
    echo "   создан $CONF/$r.env — впишите токены"
  else
    echo "   $CONF/$r.env уже есть, не трогаю"
  fi
done

echo "== Службы systemd"
install -m 644 "$APP"/deploy/systemd/ig-report@.service "$APP"/deploy/systemd/ig-report@.timer \
  "$APP"/deploy/systemd/ig-report-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now ig-report@report1.timer ig-report@report2.timer >/dev/null
systemctl enable ig-report-bot.service >/dev/null

if grep -q '^TG_BOT_TOKEN=.\+' "$CONF"/*.env; then
  systemctl restart ig-report-bot.service
  echo "   бот /report запущен"
else
  echo "   бот /report запустится после того, как впишете токены (sudo systemctl restart ig-report-bot)"
fi

cat <<MSG

Готово. Дальше:
  1) sudo nano $CONF/report1.env   и   sudo nano $CONF/report2.env   — впишите токены
  2) sudo bash $APP/deploy/run.sh report1 test      — пробный отчёт (в чат не уходит)
  3) sudo systemctl restart ig-report-bot           — включить команду /report
  4) systemctl list-timers 'ig-report*'             — когда следующий запуск
MSG
