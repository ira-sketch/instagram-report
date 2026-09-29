"""Точка входа.

python -m report.main --mode scheduled   # по расписанию: сам решает, пора ли (раз в 3 дня, 09:00 Киев)
python -m report.main --mode manual      # команда /report — отправить сейчас
python -m report.main --mode test        # проверка: напечатать отчёт и сырые данные, в чат не отправлять
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime

from .collect import collect, periods
from .config import KYIV, Config
from .history import History
from .message import build_message
from .meta_api import MetaError
from .plan import load_plan
from .telegram import TelegramError, send

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("report")


def error_text(e: Exception, final: bool) -> str:
    if isinstance(e, MetaError) and e.token_problem:
        return ("❗ Отчёт не сформирован: токен Meta недействителен или истёк.\n"
                "Нужно выпустить новый токен и обновить секрет META_TOKEN в GitHub.\n"
                f"Детали: {e}")
    tail = "Попытки исчерпаны." if final else "Повторю позже."
    return f"❗ Отчёт не сформирован: {e}\n{tail}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["scheduled", "manual", "test"], default="test")
    ap.add_argument("--mock", help="JSON с заранее собранными данными (для проверки текста)")
    ap.add_argument("--today", help="переопределить дату (YYYY-MM-DD), для проверки")
    args = ap.parse_args(argv)

    cfg = Config()
    hist = History()
    now = datetime.now(KYIV)
    today = date.fromisoformat(args.today) if args.today else now.date()

    if args.mode == "scheduled":
        due, why = hist.is_due(now, cfg.report_hour, cfg.interval_days)
        log.info("Плановый запуск: %s", why)
        if not due:
            return 0

    if not args.mock and args.mode != "test" and cfg.missing():
        log.error("Не заданы секреты: %s", ", ".join(cfg.missing()))
        return 1

    attempts = 1 + cfg.retries
    for attempt in range(1, attempts + 1):
        try:
            data = json.load(open(args.mock, encoding="utf-8")) if args.mock else collect(cfg, today)
            plan_month = date.fromisoformat(data["period"]["end"])
            plan = load_plan(cfg.plan_csv_url, plan_month)
            text = build_message(data, hist.baseline(), plan, cfg)

            if args.mode == "test":
                print("\n" + "=" * 60 + "\n" + text + "\n" + "=" * 60)
                print("План:", plan)
                print("Типы действий в рекламе:", data.get("action_types"))
                print(json.dumps(data, ensure_ascii=False, indent=1))
                return 0

            send(cfg.tg_bot_token, cfg.tg_chat_id, text)
            hist.add_report(args.mode, data, text)
            hist.log_run(args.mode, "ok", f"попытка {attempt}", data.get("action_types"))
            hist.save()
            log.info("Отчёт отправлен:\n%s", text)
            return 0

        except (MetaError, TelegramError, OSError, KeyError, ValueError) as e:
            final = attempt == attempts or (isinstance(e, MetaError) and not e.retryable)
            log.exception("Попытка %d/%d не удалась", attempt, attempts)
            hist.log_run(args.mode, "error", f"попытка {attempt}: {e}")
            hist.save()
            if args.mode == "test":
                return 1
            # Сообщаем в чат при первой ошибке и при окончательной неудаче
            if attempt == 1 or final:
                try:
                    send(cfg.tg_bot_token, cfg.tg_chat_id, error_text(e, final))
                except TelegramError:
                    log.exception("Не удалось отправить сообщение об ошибке")
            if final:
                return 1
            time.sleep(cfg.retry_delay_sec)
    return 1


if __name__ == "__main__":
    sys.exit(main())
