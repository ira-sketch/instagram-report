"""План на месяц из Google-таблицы (ссылка на CSV-экспорт листа)."""
from __future__ import annotations

import csv
import io
import logging
import re
from datetime import date

import requests

log = logging.getLogger(__name__)

MONTHS_RU = ["январ", "феврал", "март", "апрел", "ма", "июн", "июл", "август",
             "сентябр", "октябр", "ноябр", "декабр"]


def _num(s: str) -> float | None:
    s = re.sub(r"[^\d,.\-]", "", (s or "").replace(" ", ""))
    if not s:
        return None
    s = s.replace(",", ".")
    if s.count(".") > 1:  # 1.463.000 → 1463000
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


def _month_key(s: str) -> str | None:
    s = (s or "").strip().lower()
    m = re.match(r"^(\d{4})[-./](\d{1,2})", s)
    if m:
        return f"{m[1]}-{int(m[2]):02d}"
    m = re.match(r"^(\d{1,2})[-./](\d{4})$", s)
    if m:
        return f"{m[2]}-{int(m[1]):02d}"
    m = re.match(r"^\d{1,2}[./]\d{1,2}[./](\d{4})$", s)  # 01.10.2026
    if m:
        d, mo, y = re.split(r"[./]", s)
        return f"{y}-{int(mo):02d}"
    y = re.search(r"(\d{4})", s)
    if y:
        # «октябрь 2026»; «май» проверяем последним, чтобы не спутать с «март»
        for i in [0, 1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 4]:
            if s.startswith(MONTHS_RU[i]):
                return f"{y[1]}-{i + 1:02d}"
    return None


def parse_plan(text: str, month: date) -> dict:
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return {}
    header = [h.strip().lower() for h in rows[0]]

    def col(*keys):
        for i, h in enumerate(header):
            if any(k in h for k in keys):
                return i
        return None

    ci = {"month": col("мес", "month"), "followers": col("подпис", "follow"),
          "reach": col("охват", "reach"), "budget": col("бюдж", "budget", "расход")}
    if ci["month"] is None:
        log.warning("В таблице плана нет колонки «Месяц»")
        return {}
    want = f"{month.year}-{month.month:02d}"
    for r in rows[1:]:
        if len(r) > ci["month"] and _month_key(r[ci["month"]]) == want:
            return {k: _num(r[i]) for k, i in ci.items()
                    if k != "month" and i is not None and i < len(r) and _num(r[i])}
    log.info("В таблице плана нет строки для %s", want)
    return {}


def load_plan(url: str, month: date) -> dict:
    if not url:
        return {}
    try:
        r = requests.get(url, timeout=30)
        r.raise_for_status()
        r.encoding = "utf-8"
        return parse_plan(r.text, month)
    except Exception as e:  # план не критичен: без него отчёт всё равно уходит
        log.warning("Не удалось загрузить план: %s", e)
        return {"error": str(e)}
