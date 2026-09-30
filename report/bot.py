"""Слушатель команд Telegram на сервере (long polling, входящие порты не нужны).

python -m report.bot /etc/instagram-report/report1.env /etc/instagram-report/report2.env

Для каждого бота (TG_BOT_TOKEN из env-файлов) слушает команды:
  /report  — собрать и отправить отчёт сейчас (по всем отчётам этого бота и этого чата);
  /chatid  — ответить id чата и темы (для настройки).
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("bot")
ROOT = Path(__file__).resolve().parent.parent


def parse_env(path: str) -> dict[str, str]:
    out = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        out[k.strip()] = v
    return out


class BotListener(threading.Thread):
    def __init__(self, token: str, configs: list[tuple[str, dict]]):
        super().__init__(daemon=True)
        self.token = token
        self.configs = configs          # [(имя, env), ...] — отчёты этого бота
        self.running: dict[str, subprocess.Popen] = {}
        self.api = f"https://api.telegram.org/bot{token}"
        self.username = ""

    def call(self, method: str, **params):
        r = requests.post(f"{self.api}/{method}", json=params, timeout=70)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"{method}: {data.get('description')}")
        return data["result"]

    def reply(self, msg: dict, text: str):
        params = {"chat_id": msg["chat"]["id"], "text": text}
        if msg.get("message_thread_id"):
            params["message_thread_id"] = msg["message_thread_id"]
        try:
            self.call("sendMessage", **params)
        except Exception:
            log.exception("Не удалось ответить в чат")

    def start_report(self, name: str, env: dict) -> bool:
        proc = self.running.get(name)
        if proc and proc.poll() is None:
            return False  # этот отчёт уже готовится
        self.running[name] = subprocess.Popen(
            [sys.executable, "-m", "report.main", "--mode", "manual"],
            cwd=ROOT, env={**os.environ, **env})
        log.info("Запущен отчёт %s", name)
        return True

    def handle(self, msg: dict):
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return
        head = text.split()[0]
        cmd, _, target = head.partition("@")
        if target and target.lower() != self.username.lower():
            return  # команда адресована другому боту
        chat_id = str(msg["chat"]["id"])
        cmd = cmd.lower()
        if cmd == "/chatid":
            thread = msg.get("message_thread_id")
            self.reply(msg, f"chat_id: {chat_id}" + (f", id темы: {thread}" if thread else ""))
        elif cmd == "/report":
            mine = [(n, e) for n, e in self.configs if e.get("TG_CHAT_ID") == chat_id]
            if not mine:
                return  # чужой чат — молчим
            started = [n for n, e in mine if self.start_report(n, e)]
            self.reply(msg, "⏳ Готовлю отчёт, пришлю через 1–2 минуты." if started
                       else "Отчёт уже готовится, подождите пару минут.")

    def run(self):
        while True:
            try:
                self.username = self.call("getMe")["username"]
                self.call("deleteWebhook")  # на случай, если раньше был Cloudflare-вебхук
                log.info("Слушаю @%s (%s)", self.username, ", ".join(n for n, _ in self.configs))
                offset = None
                while True:
                    params = {"timeout": 50, "allowed_updates": ["message"]}
                    if offset:
                        params["offset"] = offset
                    for upd in self.call("getUpdates", **params):
                        offset = upd["update_id"] + 1
                        if upd.get("message"):
                            self.handle(upd["message"])
            except Exception:
                log.exception("Ошибка связи с Telegram, повтор через 15 с")
                time.sleep(15)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    by_token: dict[str, list] = {}
    for path in argv:
        env = parse_env(path)
        if not env.get("TG_BOT_TOKEN"):
            log.warning("%s: нет TG_BOT_TOKEN, пропускаю", path)
            continue
        by_token.setdefault(env["TG_BOT_TOKEN"], []).append((Path(path).stem, env))
    if not by_token:
        log.error("Ни в одном env-файле нет токена бота")
        return 1
    for token, configs in by_token.items():
        BotListener(token, configs).start()
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
