"""Збір цифр з Instagram Graph API і Meta Marketing API (лише читання)."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta

from report.meta_api import Meta, MetaError, actions_dict, pick_action

from .config import TZ, WConfig

log = logging.getLogger(__name__)

IG_METRICS = ["reach", "views", "accounts_engaged", "total_interactions", "likes", "comments",
              "shares", "saves", "profile_views", "website_clicks"]
FOLLOW_ACTIONS = ["onsite_conversion.ig_follow", "ig_follow", "instagram_profile_follow", "follow"]
AD_FIELDS = "spend,impressions,reach,inline_link_clicks,actions"


def ts(d: date) -> int:
    return int(datetime.combine(d, time(0), TZ).timestamp())


def last_week(today: date) -> tuple[date, date, date, date]:
    """Минулий тиждень пн–нд, що закінчився до today, і тиждень перед ним."""
    end = today - timedelta(days=today.weekday() + 1)  # неділя
    start = end - timedelta(days=6)
    return start, end, start - timedelta(days=7), start - timedelta(days=1)


def prev_month(today: date) -> tuple[date, date]:
    end = today.replace(day=1) - timedelta(days=1)
    return end.replace(day=1), end


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


class Collector:
    def __init__(self, cfg: WConfig):
        self.cfg = cfg
        self.meta = Meta(cfg.meta_token, cfg.graph_version)
        self.errors: list[str] = []

    # ------------------------------------------------------------ Instagram
    def followers(self) -> int | None:
        try:
            return int(self.meta.get(self.cfg.ig_user_id, fields="followers_count")["followers_count"])
        except MetaError as e:
            if e.token_problem:
                raise
            self.errors.append(f"підписники: {e}")
            return None

    def ig_totals(self, start: date, end: date, metrics: list[str] = IG_METRICS) -> dict:
        """Сумарні показники акаунта за [start, end] (не довше 30 днів)."""
        params = dict(period="day", metric_type="total_value", since=ts(start),
                      until=ts(end + timedelta(days=1)))
        out: dict = {}
        for m in metrics:  # по одній: недоступна метрика не ламає решту
            try:
                for item in self.meta.get(f"{self.cfg.ig_user_id}/insights", metric=m, **params)["data"]:
                    out[item["name"]] = (item.get("total_value") or {}).get("value")
            except MetaError as e:
                if e.token_problem:
                    raise
                log.warning("Метрика %s недоступна: %s", m, e)
                out[m] = None
        return out

    def net_follows(self, start: date, end: date) -> int | None:
        try:
            data = self.meta.get(f"{self.cfg.ig_user_id}/insights", metric="follows_and_unfollows",
                                 period="day", metric_type="total_value", breakdown="follow_type",
                                 since=ts(start), until=ts(end + timedelta(days=1)))["data"]
            res = {r["dimension_values"][0]: r["value"] for item in data
                   for b in (item.get("total_value") or {}).get("breakdowns", [])
                   for r in b.get("results", [])}
            if res:
                return int(res.get("FOLLOWER", 0) - res.get("NON_FOLLOWER", 0))
        except MetaError as e:
            if e.token_problem:
                raise
            log.warning("follows_and_unfollows недоступна: %s", e)
        return None

    def posts(self, start: date, end: date, insights: bool = True) -> list[dict]:
        """Дописи з timestamp у [start, end] з охопленням, переглядами, взаємодіями."""
        try:
            rows = self.meta.get_all(f"{self.cfg.ig_user_id}/media", limit=50,
                                     fields="id,caption,timestamp,media_type,media_product_type,permalink",
                                     since=ts(start), until=ts(end + timedelta(days=1)))
        except MetaError as e:
            if e.token_problem:
                raise
            self.errors.append(f"дописи: {e}")
            return []
        out = []
        for r in rows:
            day = datetime.fromisoformat(r["timestamp"].replace("+0000", "+00:00")).astimezone(TZ).date()
            if not (start <= day <= end):
                continue
            ins = {}
            for m in () if not insights else ("reach", "views", "total_interactions", "shares", "saved", "likes", "comments"):
                try:
                    d = self.meta.get(f"{r['id']}/insights", metric=m)["data"]
                    ins[m] = d[0]["values"][0]["value"] if d and d[0].get("values") else \
                        (d[0].get("total_value") or {}).get("value") if d else None
                except MetaError as e:
                    if e.token_problem:
                        raise
                    ins[m] = None
            out.append({"id": r["id"], "date": day.isoformat(), "type": r.get("media_product_type") or r.get("media_type"),
                        "caption": (r.get("caption") or "").strip()[:200], "permalink": r.get("permalink"), **ins})
        return out

    # ------------------------------------------------------------ Ads
    def _range(self, start: date, end: date) -> dict:
        return {"time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()})}

    def _ads_row(self, r: dict) -> dict:
        acts = actions_dict(r)
        link = _num(r.get("inline_link_clicks")) or acts.get("link_click", 0.0)
        follows = pick_action(acts, FOLLOW_ACTIONS)
        spend, imp, reach = _num(r.get("spend")), _num(r.get("impressions")), _num(r.get("reach"))
        return {
            "spend": round(spend, 2), "impressions": int(imp), "reach": int(reach),
            "link_clicks": int(link), "follows": int(follows) if follows is not None else 0,
            "cpc": round(spend / link, 4) if link else None,
            "ctr": round(link / imp * 100, 2) if imp else None,
            "cpm": round(spend / imp * 1000, 2) if imp else None,
            "cost_per_1000_reach": round(spend / reach * 1000, 2) if reach else None,
            "cost_per_follow": round(spend / follows, 2) if follows else None,
        }

    def ads_account(self, start: date, end: date) -> dict | None:
        try:
            rows = self.meta.get_all(f"{self.cfg.act}/insights", level="account", fields=AD_FIELDS,
                                     **self._range(start, end))
        except MetaError as e:
            if e.token_problem:
                raise
            self.errors.append(f"реклама: {e}")
            return None
        return self._ads_row(rows[0]) if rows else self._ads_row({})

    def ads_campaigns(self, start: date, end: date) -> list[dict]:
        try:
            rows = self.meta.get_all(f"{self.cfg.act}/insights", level="campaign", limit=100,
                                     fields="campaign_id,campaign_name,objective," + AD_FIELDS,
                                     **self._range(start, end))
        except MetaError as e:
            if e.token_problem:
                raise
            self.errors.append(f"кампанії: {e}")
            return []
        out = []
        for r in rows:
            row = self._ads_row(r)
            if row["spend"] <= 0:
                continue
            out.append({"name": r.get("campaign_name", ""), "objective": r.get("objective"), **row})
        return out


def collect_week(cfg: WConfig, today: date, with_posts_30d: bool = False) -> dict:
    c = Collector(cfg)
    s, e, ps, pe = last_week(today)
    data = {
        "kind": "weekly", "brand": cfg.brand, "today": today.isoformat(),
        "week": {"start": s.isoformat(), "end": e.isoformat()},
        "prev_week": {"start": ps.isoformat(), "end": pe.isoformat()},
        "currency": cfg.currency,
        "followers": c.followers(),
        "ig": c.ig_totals(s, e),
        "net_follows_week": c.net_follows(s, e),
        "posts": c.posts(s, e),
        "ads_week": c.ads_account(s, e),
        "ads_prev_week": c.ads_account(ps, pe),
        "campaigns": c.ads_campaigns(s, e),
    }
    if with_posts_30d:  # кандидати на просування
        data["posts_30d"] = c.posts(today - timedelta(days=30), today - timedelta(days=1))
    data["errors"] = c.errors
    return data


def collect_month(cfg: WConfig, today: date) -> dict:
    c = Collector(cfg)
    s, e = prev_month(today)
    # API віддає охоплення максимум за 30 днів: для 31-денного місяця — останні 30 днів
    ig_start = max(s, e - timedelta(days=29))
    data = {
        "kind": "monthly", "brand": cfg.brand, "today": today.isoformat(),
        "month": {"start": s.isoformat(), "end": e.isoformat()},
        "ig_window": {"start": ig_start.isoformat(), "end": e.isoformat()},
        "currency": cfg.currency,
        "followers": c.followers(),
        "ig": c.ig_totals(ig_start, e, ["reach", "views", "total_interactions"]),
        "posts_count": len(c.posts(s, e, insights=False)),
        "ads_month": c.ads_account(s, e),
        "campaigns": c.ads_campaigns(s, e),
    }
    data["errors"] = c.errors
    return data
