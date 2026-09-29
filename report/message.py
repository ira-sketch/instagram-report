"""Текст сообщения для Telegram и правила-предупреждения."""
from __future__ import annotations

import calendar
from datetime import date

from .config import Config

MONTHS_GEN = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
              "сентября", "октября", "ноября", "декабря"]
MONTHS_NOM = ["январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
              "сентябрь", "октябрь", "ноябрь", "декабрь"]


def n(x, dec: int = 0) -> str:
    """1 234 567 / 1,7 — формат для телефона."""
    if x is None:
        return "н/д"
    s = f"{x:,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


def signed(x: float) -> str:
    return ("+" if x > 0 else "−" if x < 0 else "±") + n(abs(x))


def pct(a, b) -> str:
    if not a or not b:
        return ""
    return f"{round(a / b * 100)}%"


def change(cur, prev) -> float | None:
    if cur is None or not prev:
        return None
    return (cur - prev) / prev


def dm(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}"


def follower_growth(acc: dict) -> tuple[float | None, str]:
    if acc.get("follows") is not None:
        return acc["follows"] - (acc.get("unfollows") or 0), ""
    if acc.get("new_followers_gross") is not None:
        return acc["new_followers_gross"], " новых"
    return None, ""


def warnings(data: dict, baseline: dict | None, plan: dict, cfg: Config) -> list[str]:
    out = []
    acc = data["account"]
    cur = cfg.currency

    # 1. Охваты за последние 3 дня против предыдущих 3 дней
    ch = change(acc.get("reach_3d"), acc.get("reach_prev3d"))
    if ch is not None and ch < -cfg.reach_drop:
        out.append(f"⚠ Охваты за 3 дня упали на {round(-ch * 100)}% "
                   f"({n(acc['reach_3d'])} против {n(acc['reach_prev3d'])}).")

    base_ads = (baseline or {}).get("ads", {})
    for ad in data["ads"]:
        name = f"«{ad['name']}»"
        # 2. Частота
        if ad["active"] and ad["frequency"] and ad["frequency"] > cfg.max_frequency:
            out.append(f"⚠ {name}: частота {n(ad['frequency'], 1)} — аудитория выгорает.")
        # 3. Стоимость подписчика за период с прошлого отчёта против накопленной на тот момент
        b = base_ads.get(ad["id"])
        if not b or ad["follows"] is None or (ad["days"] is not None and ad["days"] < 3):
            continue
        b_cpf = b["spend"] / b["follows"] if b.get("follows") else None
        d_spend = ad["spend"] - b["spend"]
        d_follows = ad["follows"] - (b.get("follows") or 0)
        if b_cpf is None or d_spend <= 0:
            continue
        if d_follows >= cfg.min_follows_for_cpf:
            cpf_now = d_spend / d_follows
            if cpf_now > b_cpf * (1 + cfg.cpf_growth):
                out.append(f"⚠ {name}: стоимость подписчика выросла до {n(cpf_now)} {cur} "
                           f"(было {n(b_cpf)} {cur}).")
        elif d_follows <= 0 and d_spend >= 2 * b_cpf:
            out.append(f"⚠ {name}: с прошлого отчёта потрачено {n(d_spend)} {cur}, "
                       f"новых подписчиков нет.")

    # 4. Расход отстаёт от графика (только для текущего месяца)
    budget = plan.get("budget")
    if budget and not data["period"]["full_month"]:
        end = date.fromisoformat(data["period"]["end"])
        days_in_month = calendar.monthrange(end.year, end.month)[1]
        expected = budget * end.day / days_in_month
        if data["spend_month"] < expected * (1 - cfg.pace_lag):
            lag = 1 - data["spend_month"] / expected
            out.append(f"⚠ Расход отстаёт от графика на {round(lag * 100)}% "
                       f"({n(data['spend_month'])} из {n(expected)} {cur} к этой дате).")
    return out


def build_message(data: dict, baseline: dict | None, plan: dict, cfg: Config) -> str:
    acc = data["account"]
    per = data["period"]
    cur = cfg.currency
    end = date.fromisoformat(per["end"])
    L = [f"📊 Отчёт {dm(data['today'])} ({dm(per['start'])}–{dm(per['end'])})"]
    if per["full_month"]:
        L[0] += f" · итоги за {MONTHS_NOM[end.month - 1]}"

    # --- Аккаунт
    L += ["", "АККАУНТ"]
    reach_line = f"Охваты: {'≈' if acc.get('reach_approx') else ''}{n(acc['reach'])}"
    ch = change(acc.get("reach_3d"), acc.get("reach_prev3d"))
    if acc.get("reach_3d") is not None:
        reach_line += f" · за 3 дн. {n(acc['reach_3d'])}"
        if ch is not None:
            reach_line += f" ({'+' if ch >= 0 else '−'}{abs(round(ch * 100))}%)"
    L.append(reach_line)
    growth, label = follower_growth(acc)
    L.append(f"Подписчики: {n(acc['followers'])}"
             + (f" ({signed(growth)}{label})" if growth is not None else ""))
    L.append(f"Показы (просмотры): {n(acc['views'])}")
    L.append(f"Взаимодействия: {n(acc['interactions'])}")
    pf = []
    if plan.get("followers"):
        pf.append(f"подписчики {n(acc['followers'])} / {n(plan['followers'])} "
                  f"({pct(acc['followers'], plan['followers'])})")
    if plan.get("reach") and acc.get("reach"):
        pf.append(f"охваты {n(acc['reach'])} / {n(plan['reach'])} ({pct(acc['reach'], plan['reach'])})")
    if pf:
        L.append("План/факт: " + " · ".join(pf))

    # --- Реклама
    L += ["", "РЕКЛАМА"]
    if not data["ads"]:
        L.append("Активной рекламы и показов в периоде нет.")
    for ad in data["ads"]:
        head = f"▪ «{ad['name']}» · {ad['status']}"
        if ad["days"] is not None:
            head += f", {ad['days']} дн."
            if ad["active"] and ad["days"] < 3:
                head += " (рано оценивать)"
        L.append(head)
        if not ad["impressions"]:
            L.append("Показов пока нет")
            continue
        L.append(f"Охваты {n(ad['reach'])} · Показы {n(ad['impressions'])} · "
                 f"Freq {n(ad['frequency'], 1)}")
        L.append(f"Переходы в профиль {n(ad['profile_visits'])} · Подписчики {n(ad['follows'])}")
        cpf = (ad["spend"] / ad["follows"]) if ad["follows"] else None
        spend = f"Потрачено {n(ad['spend'])} {cur}"
        if cpf:
            spend += f" ({n(cpf)} {cur}/подп.)"
        if abs(ad["spend_month"] - ad["spend"]) >= 1:
            spend += f", в этом месяце {n(ad['spend_month'])}"
        L.append(spend)

    # --- Бюджет
    budget = plan.get("budget")
    spent = data["spend_month"]
    days_in_month = calendar.monthrange(end.year, end.month)[1]
    forecast = spent if per["full_month"] else spent / end.day * days_in_month
    L.append("")
    if budget:
        line = f"Бюджет: потрачено {n(spent)} из {n(budget)} {cur}"
        if not per["full_month"]:
            line += f", прогноз {n(forecast)}"
        line += f", остаток {n(budget - spent)}"
    else:
        line = f"Расход за период: {n(spent)} {cur}" + (
            "" if per["full_month"] else f", прогноз на месяц {n(forecast)}")
    L.append(line)
    if plan.get("error"):
        L.append("(план из таблицы не загрузился)")

    # --- Прошлый месяц
    pv = data.get("prev")
    if pv:
        pm = date.fromisoformat(pv["start"]).month
        parts = []
        if pv.get("net_followers") is not None:
            parts.append(f"подписчики {signed(pv['net_followers'])}")
        parts += [f"охваты {'≈' if pv.get('reach_approx') else ''}{n(pv['reach'])}",
                  f"показы {n(pv['views'])}", f"взаимод. {n(pv['interactions'])}",
                  f"реклама {n(pv['spend'])} {cur}"]
        L += ["", f"Итоги за {MONTHS_NOM[pm - 1]}: " + " · ".join(parts)]

    # --- Предупреждения
    warn = warnings(data, baseline, plan, cfg)
    if warn:
        L += [""] + warn
    return "\n".join(L)
