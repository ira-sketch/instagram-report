"""План з «Content Plan VeryVery» (xlsx на Google Drive, вкладка Metrics). Лише читання.

Рядок 2 — назви місяців англійською, рядок 3 — Plan/Fact (Fact — колонка праворуч від Plan).
Рядки показників: 5 підписники (на кінець місяця), 7 публікації, 8 охоплення, 9 перегляди,
10 взаємодії, 16 промо-бюджет.
"""
from __future__ import annotations

import io
import logging
from calendar import month_name
from datetime import date

import requests

log = logging.getLogger(__name__)

ROWS = {"followers": 5, "posts": 7, "reach": 8, "views": 9, "interactions": 10, "budget": 16}


def download(file_id: str) -> bytes:
    """Файл відкритий «усім, хто має посилання» — завантажуємо без авторизації."""
    urls = [f"https://drive.google.com/uc?export=download&id={file_id}",
            f"https://docs.google.com/spreadsheets/d/{file_id}/export?format=xlsx"]
    last = None
    for url in urls:
        try:
            r = requests.get(url, timeout=60)
            if r.ok and r.content[:2] == b"PK":  # xlsx — це zip
                return r.content
            last = f"HTTP {r.status_code}, не xlsx (можливо, файл закритий для доступу за посиланням)"
        except requests.RequestException as e:
            last = str(e)
    raise RuntimeError(f"Content Plan не завантажився: {last}")


def _val(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse(content: bytes, sheet: str = "Metrics") -> dict[str, dict[str, dict]]:
    """{'October': {'plan': {...}, 'fact': {...}}, ...}"""
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), data_only=True, read_only=True)
    ws = wb[sheet]
    grid = [list(r) for r in ws.iter_rows(min_row=1, max_row=max(ROWS.values()), values_only=True)]
    months = {m.lower(): m for m in month_name if m}
    out: dict[str, dict] = {}
    header = grid[1]
    for col, cell in enumerate(header):
        name = str(cell or "").strip().lower()
        if name not in months:
            continue
        plan_col, fact_col = col, col + 1
        out[months[name]] = {
            "plan": {k: _val(grid[r - 1][plan_col]) for k, r in ROWS.items()},
            "fact": {k: _val(grid[r - 1][fact_col]) if fact_col < len(grid[r - 1]) else None
                     for k, r in ROWS.items()},
        }
    return out


def load(file_id: str, sheet: str = "Metrics") -> dict | None:
    if not file_id:
        return None
    return parse(download(file_id), sheet)


def month_key(d: date) -> str:
    return month_name[d.month]
