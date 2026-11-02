"""Складання JSON-опису картинки (формат render_report.py) із зібраних даних."""
from __future__ import annotations

import calendar
from datetime import date

UA_MONTHS = ["січень", "лютий", "березень", "квітень", "травень", "червень", "липень",
             "серпень", "вересень", "жовтень", "листопад", "грудень"]
UA_MONTHS_GEN = ["січня", "лютого", "березня", "квітня", "травня", "червня", "липня",
                 "серпня", "вересня", "жовтня", "листопада", "грудня"]
MINUS = "−"


# ------------------------------------------------------------------ формат чисел
def n(v, digits: int = 0) -> str:
    """1 234 / 9,85; None → «н/д»."""
    if v is None:
        return "н/д"
    s = f"{float(v):,.{digits}f}".replace(",", " ").replace(".", ",")
    return s.replace("-", MINUS)


def money(v, cur: str, digits: int | None = None) -> str:
    if v is None:
        return "н/д"
    if digits is None:
        digits = 2 if cur == "€" else 0
    return f"{n(v, digits)} {cur}"


def signed(v) -> str:
    if v is None:
        return "н/д"
    return ("+" if v > 0 else MINUS if v < 0 else "") + n(abs(v))


def pct_change(prev, cur) -> str:
    if prev in (None, 0) or cur is None:
        return "—"
    p = (cur - prev) / prev * 100
    return ("+" if p > 0 else MINUS if p < 0 else "") + f"{abs(p):,.0f}".replace(",", " ") + "%"


def done(fact, plan) -> str:
    if not plan or fact is None:
        return "—"
    p = round(fact / plan * 100)
    return f"{'▲' if p >= 100 else '▼'} {p}%"


def ddmm(d: str) -> str:
    y, m, dd = d.split("-")
    return f"{dd}.{m}"


def week_label(s: str, e: str) -> str:
    return f"{ddmm(s)}–{ddmm(e)}.{e[:4]}"


TYPE_UA = {"REELS": "Reel", "VIDEO": "Відео", "IMAGE": "Фото", "CAROUSEL_ALBUM": "Карусель",
           "FEED": "Допис", "STORY": "Сторіс"}


def short(text: str, limit: int = 30) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit - 1].rstrip() + "…"


# ------------------------------------------------------------------ секції
def ig_grid(handle: str, d: dict, followers_change) -> dict:
    ig = d["ig"]
    return {
        "title": f"Instagram @{handle}",
        "columns": [["Показник", "l"], ["", "r"], ["Показник", "l"], ["", "r"]],
        "widths": [30, 12, 30, 12],
        "rows": [
            ["Підписники", n(d["followers"]), "Зміна підписників", signed(followers_change)],
            ["Охоплення", n(ig.get("reach")), "Перегляди", n(ig.get("views"))],
            ["Залучені акаунти", n(ig.get("accounts_engaged")), "Взаємодії", n(ig.get("total_interactions"))],
            ["Поширення", n(ig.get("shares")), "Збереження", n(ig.get("saves"))],
            ["Перегляди профілю", n(ig.get("profile_views")), "Переходи на сайт", n(ig.get("website_clicks"))],
        ],
    }


def posts_section(d: dict, names: dict, brand: str) -> dict:
    posts = sorted(d["posts"], key=lambda p: p.get("reach") or 0, reverse=True)[:6]
    title = f"Дописи тижня: {len(d['posts'])}"
    if brand == "veryvery":
        cols, widths = [["Допис", "l"], ["Охоплення", "r"], ["Перегляди", "r"], ["Поширення", "r"]], [40, 18, 18, 16]
        row = lambda p: [p["label"], n(p.get("reach")), n(p.get("views")), n(p.get("shares"))]
    else:
        cols, widths = [["Допис", "l"], ["Охоплення", "r"], ["Взаємодії", "r"], ["ER", "r"]], [40, 18, 18, 16]

        def row(p):
            er = (p.get("total_interactions") or 0) / p["reach"] * 100 if p.get("reach") else None
            return [p["label"], n(p.get("reach")), n(p.get("total_interactions")),
                    f"{n(er, 1)}%" if er is not None else "—"]
    for p in posts:
        p["label"] = f"{short(names.get(p['id']) or p.get('caption') or TYPE_UA.get(p.get('type'), 'Допис'), 26)} · {ddmm(p['date'])}"
    sec = {"title": title, "columns": cols, "widths": widths, "rows": [row(p) for p in posts]}
    if posts:
        sec["highlight"] = [0]
    else:
        sec["rows"] = [["Нових дописів не було"] + [""] * (len(cols) - 1)]
    return sec


def ads_compare(d: dict, brand: str, cur: str) -> dict:
    a, b = d.get("ads_prev_week"), d.get("ads_week")
    title = "Реклама Meta · порівняння з попереднім тижнем"
    if a is None or b is None:
        return {"title": title, "columns": [["Показник", "l"], ["", "r"]],
                "rows": [["Дані реклами недоступні", "н/д"]]}
    if not a["spend"] and not b["spend"]:
        return {"title": title, "columns": [["Показник", "l"], ["", "r"]],
                "rows": [["Реклама не працювала", money(0, cur, 0)]]}
    if brand == "veryvery":
        spec = [("Витрати", "spend", lambda v: money(v, cur)), ("Охоплення", "reach", n),
                ("Ціна 1000 охоплення", "cost_per_1000_reach", lambda v: money(v, cur)),
                ("Покази", "impressions", n), ("Підписки з реклами", "follows", n),
                ("Ціна підписника", "cost_per_follow", lambda v: money(v, cur, 2))]
        inverse, widths = ["Ціна 1000 охоплення", "Ціна підписника"], [34, 22, 24, 14]
    else:
        spec = [("Витрати", "spend", lambda v: money(v, cur)), ("Покази", "impressions", n),
                ("Кліки за посиланням", "link_clicks", n), ("Ціна кліку", "cpc", lambda v: money(v, cur, 3)),
                ("CTR", "ctr", lambda v: f"{n(v, 2)}%" if v is not None else "—"),
                ("CPM", "cpm", lambda v: money(v, cur))]
        inverse, widths = ["Ціна кліку", "CPM"], [34, 22, 24, 20]
    rows = [[label, fmt(a.get(k)) if a.get(k) is not None else "—",
             fmt(b.get(k)) if b.get(k) is not None else "—", pct_change(a.get(k), b.get(k))]
            for label, k, fmt in spec]
    return {"title": title, "widths": widths, "change_col": 3, "inverse_rows": inverse,
            "columns": [["Показник", "l"], ["Попередній", "r"], ["Цей тиждень", "r"], ["Зміна", "r"]],
            "rows": rows}


def campaigns_section(camps: list[dict], names: dict, brand: str, cur: str) -> dict | None:
    if not camps:
        return None
    if brand == "veryvery":
        key, cols = "cost_per_follow", [["Кампанія", "l"], [f"Витрати, {cur}", "r"], ["Підписки", "r"], [f"{cur} / підписник", "r"]]
        cnt = "follows"
    else:
        key, cols = "cpc", [["Кампанія", "l"], [f"Витрати, {cur}", "r"], ["Кліки", "r"], [f"{cur} / клік", "r"]]
        cnt = "link_clicks"
    with_val = sorted([c for c in camps if c.get(key)], key=lambda c: c[key])
    without = [c for c in camps if not c.get(key)]
    digits = 3 if (brand == "buro") else 2
    rows = [[short(names.get(c["name"]) or c["name"], 26), n(c["spend"], 2 if cur == "€" else 0), n(c[cnt]),
             n(c[key], digits) if c.get(key) else "—"] for c in with_val + without]
    sec = {"title": "Кампанії", "columns": cols, "widths": [40, 20, 16, 16], "rows": rows}
    if with_val:
        sec["highlight"] = [0]
    return sec


# ------------------------------------------------------------------ план (Veryvery)
def week_plan(plan: dict, plan_month: date, d: dict, followers_change) -> tuple[dict | None, list]:
    """Тижнева частка місячного плану. Повертає (секцію, рядки-дані для висновків)."""
    key = calendar.month_name[plan_month.month]
    prev_key = calendar.month_name[(plan_month.month - 2) % 12 + 1]
    if not plan or key not in plan:
        return None, []
    p, prev = plan[key]["plan"], plan.get(prev_key, {"plan": {}, "fact": {}})
    days = calendar.monthrange(plan_month.year, plan_month.month)[1]
    k = 7 / days
    base = prev["fact"].get("followers") or prev["plan"].get("followers")
    fol_plan = (p["followers"] - base) if p.get("followers") is not None and base is not None else None
    items = [("Приріст підписників", fol_plan, followers_change, n),
             ("Охоплення", p.get("reach"), d["ig"].get("reach"), n),
             ("Перегляди", p.get("views"), d["ig"].get("views"), n),
             ("Взаємодії", p.get("interactions"), d["ig"].get("total_interactions"), n),
             ("Промо-бюджет", p.get("budget"), (d.get("ads_week") or {}).get("spend"),
              lambda v: money(v, "₴"))]
    rows, info = [], []
    for label, month_plan, fact, fmt in items:
        if month_plan is None:
            continue
        wp = month_plan * k
        rows.append([label, fmt(wp), fmt(fact), done(fact, wp)])
        info.append({"показник": label, "план_місяця": month_plan, "план_тижня": round(wp),
                     "факт_тижня": fact, "виконання_%": round(fact / wp * 100) if fact is not None and wp else None})
    if not rows:
        return None, []
    return {"title": f"План місяця · {UA_MONTHS[plan_month.month - 1]} (тижнева частка)",
            "columns": [["Показник", "l"], ["План тижня", "r"], ["Факт", "r"], ["Виконання", "r"]],
            "widths": [34, 22, 22, 16], "change_col": 3, "inverse_rows": ["Промо-бюджет"],
            "rows": rows}, info


# ------------------------------------------------------------------ тижневий звіт
def weekly_spec(d: dict, cfg, prev_followers, names: dict, plan: dict | None) -> tuple[dict, dict]:
    """Повертає (spec для картинки, додаткові дані для висновків)."""
    cur = cfg.currency
    if prev_followers is not None and d.get("followers") is not None:
        change = d["followers"] - prev_followers
    else:
        change = d.get("net_follows_week")
    sections = [ig_grid(cfg.ig_handle, d, change)]
    extra = {"зміна_підписників": change}
    if cfg.brand == "veryvery":
        thu = date.fromordinal(date.fromisoformat(d["week"]["start"]).toordinal() + 3)
        plan_month = thu.replace(day=1)
        sec, info = week_plan(plan, plan_month, d, change)
        if sec:
            sections.append(sec)
            extra["план_тижня"] = info
        else:
            extra["план"] = "не вдалося прочитати Content Plan" if cfg.plan_file_id else "немає"
    sections.append(posts_section(d, names, cfg.brand))
    sections.append(ads_compare(d, cfg.brand, cur))
    camp = campaigns_section(d.get("campaigns") or [], names, cfg.brand, cur)
    if camp:
        sections.append(camp)
    note = "Зелений — покращення, червоний — погіршення. Виділено найкращий результат."
    if cfg.brand == "veryvery":
        note += (" Цілі — охоплення і підписники за планом з Content Plan (Metrics); план тижня = "
                 "місячний план ÷ днів у місяці × 7; для бюджету ▲ — перевитрата.")
    spec = {"title": f"Тижневий звіт · {cfg.brand_title}",
            "subtitle": f"Тиждень {week_label(d['week']['start'], d['week']['end'])}",
            "followers": d.get("followers"), "sections": sections, "note": note}
    return spec, extra


# ------------------------------------------------------------------ місячний звіт (Veryvery)
def monthly_spec(d: dict, cfg, plan: dict | None, names: dict) -> tuple[dict, dict]:
    m_start = date.fromisoformat(d["month"]["start"])
    key = calendar.month_name[m_start.month]
    prev_key = calendar.month_name[(m_start.month - 2) % 12 + 1]
    next_key = calendar.month_name[m_start.month % 12 + 1]
    p = (plan or {}).get(key, {}).get("plan", {})
    prev_fact = (plan or {}).get(prev_key, {}).get("fact", {})
    ads = d.get("ads_month") or {}
    base = prev_fact.get("followers")
    growth = d["followers"] - base if d.get("followers") is not None and base is not None else None
    growth_plan = p["followers"] - base if p.get("followers") is not None and base is not None else None
    ig = d["ig"]
    items = [("Підписники", p.get("followers"), d.get("followers"), n),
             ("Приріст підписників", growth_plan, growth, signed),
             ("Публікації", p.get("posts"), d.get("posts_count"), n),
             ("Охоплення", p.get("reach"), ig.get("reach"), n),
             ("Перегляди", p.get("views"), ig.get("views"), n),
             ("Взаємодії", p.get("interactions"), ig.get("total_interactions"), n),
             ("Промо-бюджет", p.get("budget"), ads.get("spend"), lambda v: money(v, "₴"))]
    rows = []
    for label, pl, fact, fmt in items:
        if label == "Публікації" and pl is None:
            continue
        rows.append([label, fmt(pl) if pl is not None else "—", fmt(fact), done(fact, pl)])
    sections = [{"title": "План / факт", "columns": [["Показник", "l"], ["План", "r"], ["Факт", "r"], ["Виконання", "r"]],
                 "widths": [34, 22, 22, 16], "change_col": 3, "inverse_rows": ["Промо-бюджет"], "rows": rows}]
    cur = cfg.currency
    sections.append({"title": "Реклама Meta за місяць", "columns": [["Показник", "l"], ["Значення", "r"]], "rows": [
        ["Витрати", money(ads.get("spend"), cur)], ["Кліки за посиланням", n(ads.get("link_clicks"))],
        ["Ціна кліку", money(ads.get("cpc"), cur, 2)],
        ["CTR", f"{n(ads.get('ctr'), 2)}%" if ads.get("ctr") is not None else "—"],
        ["CPM", money(ads.get("cpm"), cur)]]})
    camps = sorted([c for c in d.get("campaigns") or [] if c.get("cpc")], key=lambda c: c["cpc"]) + \
        [c for c in d.get("campaigns") or [] if not c.get("cpc")]
    if camps:
        sections.append({"title": "Кампанії", "highlight": [0],
                         "columns": [["Кампанія", "l"], [f"Витрати, {cur}", "r"], ["Кліки", "r"], [f"{cur} / клік", "r"]],
                         "rows": [[short(names.get(c["name"]) or c["name"], 26), n(c["spend"]), n(c["link_clicks"]),
                                   n(c["cpc"], 2) if c.get("cpc") else "—"] for c in camps]})
    nxt = (plan or {}).get(next_key, {}).get("plan", {})
    next_month_ua = UA_MONTHS[m_start.month % 12]
    nrows = [[lbl, fmt(nxt[k])] for lbl, k, fmt in [
        ("Підписники", "followers", n), ("Охоплення", "reach", n), ("Перегляди", "views", n),
        ("Взаємодії", "interactions", n), ("Промо-бюджет", "budget", lambda v: money(v, "₴"))] if nxt.get(k) is not None]
    if nrows:
        sections.append({"title": f"План на {next_month_ua}", "columns": [["Показник", "l"], ["План", "r"]], "rows": nrows})
    spec = {"title": f"Підсумки місяця · {cfg.brand_title}",
            "subtitle": f"{UA_MONTHS[m_start.month - 1].capitalize()} {m_start.year} · план / факт",
            "followers": d.get("followers"), "sections": sections,
            "note": "Зелений — план виконано, червоний — ні; для бюджету ▲ — перевитрата. Instagram-метрики — останні 30 днів."}
    extra = {"план_місяця": p, "план_наступного_місяця": nxt, "приріст_підписників": growth,
             "план_приросту": growth_plan, "план_прочитано": bool(plan)}
    return spec, extra
