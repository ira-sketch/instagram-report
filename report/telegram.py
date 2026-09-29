"""Отправка в Telegram через Bot API."""
from __future__ import annotations

import requests


class TelegramError(Exception):
    pass


def send(token: str, chat_id: str, text: str, thread_id: str = "") -> None:
    # Лимит Telegram — 4096 символов; длинный отчёт режем по строкам
    parts, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > 4000:
            parts.append(cur)
            cur = ""
        cur += line + "\n"
    parts.append(cur)
    for p in parts:
        try:
            payload = {"chat_id": chat_id, "text": p.strip(), "disable_web_page_preview": True}
            if thread_id:  # тема в группе-форуме
                payload["message_thread_id"] = int(thread_id)
            r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                              json=payload, timeout=30)
            ok = r.json().get("ok")
        except Exception as e:
            raise TelegramError(f"Telegram недоступен: {e}") from e
        if not ok:
            raise TelegramError(f"Telegram отказал: {r.text[:300]}")
