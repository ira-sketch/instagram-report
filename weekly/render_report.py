#!/usr/bin/env python3
"""Рисует картинку-таблицу для отчёта Redko Buro из JSON-описания.

Использование:  python3 render_report.py report.json report.png

Формат JSON:
{
  "title": "Тижневий звіт · Redko Buro",
  "subtitle": "Тиждень 28.09–04.10.2026",
  "sections": [
    {
      "title": "Instagram @redko_buro",
      "columns": [["Показник","l"],["","r"],["Показник","l"],["","r"]],   # l / r = выравнивание
      "widths": [40, 0, 42, 0],        # необязательно: доля ширины под текстовые столбцы
      "rows": [["Підписники","1 402","Нові підписки","+50"], ...],
      "change_col": 3,                 # необязательно: номер столбца с изменением (+/− окрашиваются)
      "inverse_rows": ["Ціна кліку","CPM"],   # строки, где рост = плохо
      "highlight": [0],                # необязательно: подсветить строки
      "total_last": true               # необязательно: последняя строка — итог (жирным)
    }
  ],
  "note": "текст мелким шрифтом внизу"
}
"""
import json
import sys
import textwrap

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams["font.family"] = "DejaVu Sans"

INK, MUTED, LINE = "#1F2A44", "#6B7280", "#E5E7EB"
UP, DOWN, HEAD, ACC = "#15803D", "#B91C1C", "#F3F4F6", "#FDF2E9"

ROW_H = 5.0      # высота строки в условных единицах
FS_BODY, FS_HEAD, FS_TITLE, FS_SUB, FS_SEC, FS_NOTE = 15.5, 12.5, 24, 14, 17, 12
LEFT, RIGHT = 5, 95


def col_positions(cols, widths=None):
    """Первый столбец — слева, остальные распределяются справа налево."""
    n = len(cols)
    if widths and any(widths):
        xs, x = [], LEFT
        total = sum(w if w else 12 for w in widths)
        scale = (RIGHT - LEFT) / total
        for (name, align), w in zip(cols, widths):
            w = (w if w else 12) * scale
            if align == "l":
                xs.append(x if x == LEFT else x + 3)   # отступ от предыдущего столбца
            else:
                xs.append(x + w - (3 if x + w < RIGHT - 0.5 else 0))
            x += w
        return xs
    if n == 1:
        return [LEFT]
    first_w = 40 if n >= 4 else 55
    rest = (RIGHT - LEFT - first_w) / (n - 1)
    return [LEFT] + [LEFT + first_w + rest * (i + 1) for i in range(n - 1)]


def height_needed(spec):
    h = 15
    for s in spec["sections"]:
        h += 5.5 + ROW_H * (len(s["rows"]) + 1) + 3.5
    note_lines = len(textwrap.wrap(spec.get("note", ""), 74)) if spec.get("note") else 0
    return h + (2 + 3.2 * note_lines if note_lines else 2)


def render(spec, out):
    H = height_needed(spec)
    fig = plt.figure(figsize=(8, 8 * H / 100), dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, H)
    ax.axis("off")

    y = H - 4
    ax.text(4, y, spec["title"], fontsize=FS_TITLE, weight="bold", color=INK, va="top")
    if spec.get("subtitle"):
        ax.text(4, y - 5.5, spec["subtitle"], fontsize=FS_SUB, color=MUTED, va="top")
    y -= 12

    for s in spec["sections"]:
        ax.text(4, y, s["title"], fontsize=FS_SEC, weight="bold", color=INK, va="top")
        y -= 5.5
        cols = s["columns"]
        xs = col_positions(cols, s.get("widths"))
        ha = ["left" if a == "l" else "right" for _, a in cols]
        ax.add_patch(plt.Rectangle((3, y - ROW_H), 94, ROW_H, color=HEAD, lw=0))
        for x, h, (name, _) in zip(xs, ha, cols):
            ax.text(x, y - ROW_H / 2, name, fontsize=FS_HEAD, color=MUTED, weight="bold", va="center", ha=h)
        y -= ROW_H
        cc = s.get("change_col")
        inv = set(s.get("inverse_rows", []))
        hi = set(s.get("highlight", []))
        total_last = s.get("total_last", False)   # последняя строка — итог (жирным, с фоном)
        for i, row in enumerate(s["rows"]):
            is_total = total_last and i == len(s["rows"]) - 1
            if i in hi:
                ax.add_patch(plt.Rectangle((3, y - ROW_H), 94, ROW_H, color=ACC, lw=0))
            if is_total:
                ax.add_patch(plt.Rectangle((3, y - ROW_H), 94, ROW_H, color=HEAD, lw=0))
            for j, (x, h, val) in enumerate(zip(xs, ha, row)):
                val = str(val)
                color, weight = INK, "normal"
                if cc is not None and j == cc:
                    weight = "bold"
                    good = val.startswith("+") or val.startswith("▲")
                    bad = val.startswith("−") or val.startswith("-") or val.startswith("▼")
                    if row[0] in inv:
                        good, bad = bad, good
                    color = UP if good else DOWN if bad else INK
                if is_total:
                    weight = "bold"
                ax.text(x, y - ROW_H / 2, val, fontsize=FS_BODY, color=color, weight=weight, va="center", ha=h)
            ax.plot([3, 97], [y - ROW_H, y - ROW_H], color=LINE, lw=0.8)
            y -= ROW_H
        y -= 3.5

    if spec.get("note"):
        ax.text(4, y, "\n".join(textwrap.wrap(spec["note"], 74)), fontsize=FS_NOTE, color=MUTED, va="top", linespacing=1.4)
    fig.savefig(out, facecolor="white")


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        render(json.load(f), sys.argv[2])
    print("ok", sys.argv[2])
