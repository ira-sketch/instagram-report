"""Відправка картинки і тексту в Telegram (Bot API)."""
from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


class TgError(Exception):
    pass


def _call(token: str, method: str, data: dict, files: dict | None = None) -> None:
    try:
        r = requests.post(f"https://api.telegram.org/bot{token}/{method}", data=data, files=files, timeout=60)
        ok = r.json().get("ok")
    except Exception as e:
        raise TgError(f"Telegram недоступний: {e}") from e
    if not ok:
        raise TgError(f"Telegram відмовив ({method}): {r.text[:300]}")


def send_report(token: str, chat: str, png: str, text: str, thread: str = "") -> None:
    base = {"chat_id": chat}
    if thread:
        base["message_thread_id"] = thread
    with open(png, "rb") as f:
        try:
            _call(token, "sendPhoto", base, {"photo": ("report.png", f, "image/png")})
        except TgError as e:  # дуже висока картинка може не пройти як фото — шлемо файлом
            log.warning("sendPhoto не пройшов (%s), відправляю як документ", e)
            f.seek(0)
            _call(token, "sendDocument", base, {"document": ("report.png", f, "image/png")})
    _call(token, "sendMessage", {**base, "text": text, "parse_mode": "HTML",
                                 "disable_web_page_preview": "true"})


def send_text(token: str, chat: str, text: str, thread: str = "") -> None:
    data = {"chat_id": chat, "text": text}
    if thread:
        data["message_thread_id"] = thread
    _call(token, "sendMessage", data)
