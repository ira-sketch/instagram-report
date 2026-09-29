"""Сбор всех цифр для отчёта в один словарь (сериализуемый в JSON)."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from .config import KYIV, Config
from .meta_api import Ads, Instagram, Meta, actions_dict, pick_action

log = logging.getLogger(__name__)

STATUS_RU = {
    "ACTIVE": "активна", "PAUSED": "на паузе", "ADSET_PAUSED": "на паузе",
    "CAMPAIGN_PAUSED": "на паузе", "PENDING_REVIEW": "на проверке", "IN_PROCESS": "в обработке",
    "DISAPPROVED": "отклонена", "WITH_ISSUES": "есть проблемы", "ARCHIVED": "в архиве",
    "DELETED": "удалена", "PENDING_BILLING_INFO": "ждёт оплаты",
}


def month_start(d: date) -> date:
    return d.replace(day=1)


def prev_month_range(d: date) -> tuple[date, date]:
    end = month_start(d) - timedelta(days=1)
    return month_start(end), end


def periods(today: date) -> dict:
    """Основной период и (в первые 3 дня месяца) итоги прошлого месяца."""
    yesterday = today - timedelta(days=1)
    if today.day == 1:  # текущий месяц ещё пуст — отчёт за весь прошлый месяц
        s, e = prev_month_range(today)
        return {"start": s, "end": e, "full_month": True, "prev": None}
    return {"start": month_start(today), "end": yesterday, "full_month": False,
            "prev": prev_month_range(today) if today.day <= 3 else None}


def _parse_dt(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("+0000", "+00:00")).astimezone(KYIV).date()
    except ValueError:
        return None


def _f(row: dict | None, key: str) -> float:
    return float((row or {}).get(key, 0) or 0)


def collect(cfg: Config, today: date) -> dict:
    meta = Meta(cfg.meta_token, cfg.graph_version)
    ig = Instagram(meta, cfg.ig_user_id)
    ads = Ads(meta, cfg.ad_account_id)
    p = periods(today)
    start, end = p["start"], p["end"]
    rate = cfg.currency_rate
    yesterday = today - timedelta(days=1)

    # --- Аккаунт
    reach, reach_approx = ig.reach(start, end)
    totals = ig.period_totals(start, end)
    reach_3d, _ = ig.reach(yesterday - timedelta(days=2), yesterday)
    reach_prev3d, _ = ig.reach(yesterday - timedelta(days=5), yesterday - timedelta(days=3))
    prof = ig.profile()
    account = {
        "followers": prof["followers"], "username": prof["username"],
        "reach": reach, "reach_approx": reach_approx,
        "views": totals["views"], "interactions": totals["interactions"],
        "follows": totals["follows"], "unfollows": totals["unfollows"],
        "new_followers_gross": totals["new_followers_gross"],
        "reach_3d": reach_3d, "reach_prev3d": reach_prev3d,
    }

    # --- Реклама
    month_rows = ads.ad_rows(start, end)
    ids = sorted(set(month_rows) | set(ads.active_ad_ids()))
    details = ads.details(ids) if ids else {}
    life = ads.lifetime_rows(ids)
    action_types: set[str] = set()
    ad_list = []
    for ad_id in ids:
        d = details.get(ad_id, {})
        lr = life.get(ad_id) or month_rows.get(ad_id) or {}
        acts = actions_dict(lr)
        action_types |= set(acts)
        adset = d.get("adset") or {}
        learning = (adset.get("learning_stage_info") or {}).get("status")
        eff = d.get("effective_status", "")
        status = STATUS_RU.get(eff, eff.lower() or "—")
        if eff == "ACTIVE" and learning == "LEARNING":
            status = "на обучении"
        launch = max(filter(None, [_parse_dt(adset.get("start_time")), _parse_dt(d.get("created_time"))]),
                     default=None)
        reach_l, impr_l = _f(lr, "reach"), _f(lr, "impressions")
        ad_list.append({
            "id": ad_id,
            "name": d.get("name") or lr.get("ad_name") or ad_id,
            "status": status, "active": eff == "ACTIVE",
            "launch": launch.isoformat() if launch else None,
            "days": (today - launch).days if launch else None,
            "reach": reach_l, "impressions": impr_l,
            "frequency": (impr_l / reach_l) if reach_l else None,
            "profile_visits": pick_action(acts, cfg.profile_visit_actions),
            "follows": pick_action(acts, cfg.follow_actions),
            "spend": _f(lr, "spend") * rate,
            "spend_month": _f(month_rows.get(ad_id), "spend") * rate,
        })
    ad_list.sort(key=lambda a: (not a["active"], -a["spend_month"]))

    data = {
        "today": today.isoformat(),
        "period": {"start": start.isoformat(), "end": end.isoformat(), "full_month": p["full_month"]},
        "account": account,
        "ads": ad_list,
        "spend_month": ads.account_spend(start, end) * rate,
        "action_types": sorted(action_types),
        "prev": None,
    }

    # --- Итоги прошлого месяца (1–3 число)
    if p["prev"]:
        ps, pe = p["prev"]
        pr, pr_approx = ig.reach(ps, pe)
        pt = ig.period_totals(ps, pe)
        data["prev"] = {
            "start": ps.isoformat(), "end": pe.isoformat(),
            "reach": pr, "reach_approx": pr_approx, "views": pt["views"],
            "interactions": pt["interactions"],
            "net_followers": (pt["follows"] - pt["unfollows"]) if pt["follows"] is not None else None,
            "spend": ads.account_spend(ps, pe) * rate,
        }
    return data
