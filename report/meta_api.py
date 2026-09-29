"""Доступ к Instagram Graph API и Meta Marketing API (только чтение)."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, time, timedelta

import requests

from .config import KYIV

log = logging.getLogger(__name__)

# Коды ошибок, при которых повтор через 15 минут бессмыслен
# (токен недействителен, нет прав, неверный параметр).
NON_RETRYABLE_CODES = {10, 100, 102, 190, 200, 294, 803}


class MetaError(Exception):
    def __init__(self, message: str, code: int | None = None):
        super().__init__(message)
        self.code = code
        self.retryable = code not in NON_RETRYABLE_CODES

    @property
    def token_problem(self) -> bool:
        return self.code in (102, 190)


class Meta:
    def __init__(self, token: str, version: str):
        self.token = token
        self.base = f"https://graph.facebook.com/{version}"
        self.session = requests.Session()

    def _request(self, url: str, params: dict | None) -> dict:
        try:
            r = self.session.get(url, params=params, timeout=90)
        except requests.RequestException as e:  # сеть, таймаут
            raise MetaError(f"Meta API недоступен: {e}") from e
        try:
            data = r.json()
        except ValueError:
            raise MetaError(f"Meta API вернул не JSON (HTTP {r.status_code})")
        if "error" in data:
            err = data["error"]
            code = err.get("code")
            raise MetaError(f"{err.get('message', 'ошибка')} (code {code})", code)
        return data

    def get(self, path: str, **params) -> dict:
        params["access_token"] = self.token
        return self._request(f"{self.base}/{path}", params)

    def get_all(self, path: str, **params) -> list[dict]:
        data = self.get(path, **params)
        rows = list(data.get("data", []))
        nxt = data.get("paging", {}).get("next")
        while nxt:
            data = self._request(nxt, None)
            rows.extend(data.get("data", []))
            nxt = data.get("paging", {}).get("next")
        return rows


# ---------------------------------------------------------------- helpers

def ts(d: date) -> int:
    """Полночь по Киеву для даты d как unix-время."""
    return int(datetime.combine(d, time(0), KYIV).timestamp())


def chunks(start: date, end: date, max_days: int = 30):
    """Разбить период [start, end] на куски не длиннее max_days."""
    cur = start
    while cur <= end:
        stop = min(end, cur + timedelta(days=max_days - 1))
        yield cur, stop
        cur = stop + timedelta(days=1)


def actions_dict(row: dict) -> dict[str, float]:
    return {a["action_type"]: float(a.get("value", 0)) for a in row.get("actions", []) or []}


def pick_action(actions: dict[str, float], candidates: list[str]) -> float | None:
    for c in candidates:
        if c in actions:
            return actions[c]
    return None


# ---------------------------------------------------------------- Instagram

class Instagram:
    def __init__(self, meta: Meta, ig_user_id: str):
        self.meta = meta
        self.ig = ig_user_id

    def followers_count(self) -> int:
        return int(self.meta.get(self.ig, fields="followers_count")["followers_count"])

    def _total_values(self, metrics: list[str], start: date, end: date, **extra) -> dict:
        """metric_type=total_value за [start, end]; при сбое пробует метрики по одной."""
        params = dict(period="day", metric_type="total_value",
                      since=ts(start), until=ts(end + timedelta(days=1)), **extra)
        try:
            data = self.meta.get(f"{self.ig}/insights", metric=",".join(metrics), **params)["data"]
        except MetaError as e:
            if len(metrics) == 1 or e.token_problem:
                raise
            log.warning("Групповой запрос метрик %s не прошёл (%s), пробую по одной", metrics, e)
            data = []
            for m in metrics:
                try:
                    data += self.meta.get(f"{self.ig}/insights", metric=m, **params)["data"]
                except MetaError as e2:
                    if e2.token_problem:
                        raise
                    log.warning("Метрика %s недоступна: %s", m, e2)
        out = {}
        for item in data:
            tv = item.get("total_value") or {}
            out[item["name"]] = tv.get("value")
            if tv.get("breakdowns"):
                out[item["name"] + "__breakdown"] = {
                    "/".join(r["dimension_values"]): r["value"]
                    for b in tv["breakdowns"] for r in b.get("results", [])
                }
        return out

    def reach(self, start: date, end: date) -> tuple[int | None, bool]:
        """Уникальный охват. Если период > 30 дней — берём последние 30 (approx=True)."""
        approx = (end - start).days + 1 > 30
        if approx:
            start = end - timedelta(days=29)
        return self._total_values(["reach"], start, end).get("reach"), approx

    def period_totals(self, start: date, end: date) -> dict:
        """Суммируемые метрики за период (просмотры, взаимодействия, подписки)."""
        tot = {"views": 0, "interactions": 0, "follows": None, "unfollows": None,
               "new_followers_gross": None}
        for a, b in chunks(start, end):
            v = self._total_values(["views", "likes", "comments", "saves", "shares"], a, b)
            tot["views"] += v.get("views") or 0
            tot["interactions"] += sum(v.get(k) or 0 for k in ("likes", "comments", "saves", "shares"))
            # Нетто-прирост: подписки минус отписки
            try:
                f = self._total_values(["follows_and_unfollows"], a, b, breakdown="follow_type")
                br = f.get("follows_and_unfollows__breakdown") or {}
                if br:
                    tot["follows"] = (tot["follows"] or 0) + br.get("FOLLOWER", 0)
                    tot["unfollows"] = (tot["unfollows"] or 0) + br.get("NON_FOLLOWER", 0)
            except MetaError as e:
                if e.token_problem:
                    raise
                log.warning("follows_and_unfollows недоступна: %s", e)
        if tot["follows"] is None:
            # Запасной вариант: follower_count (новые подписчики по дням, без отписок)
            try:
                rows = self.meta.get(f"{self.ig}/insights", metric="follower_count", period="day",
                                     since=ts(max(start, end - timedelta(days=29))),
                                     until=ts(end + timedelta(days=1)))["data"]
                tot["new_followers_gross"] = sum(v.get("value", 0) for r in rows for v in r.get("values", []))
            except MetaError as e:
                if e.token_problem:
                    raise
                log.warning("follower_count недоступна: %s", e)
        return tot


# ---------------------------------------------------------------- Ads

AD_FIELDS = "ad_id,ad_name,reach,impressions,frequency,spend,actions"
DETAIL_FIELDS = "id,name,effective_status,created_time,adset{start_time,learning_stage_info}"


class Ads:
    def __init__(self, meta: Meta, ad_account_id: str):
        self.meta = meta
        self.act = ad_account_id if ad_account_id.startswith("act_") else f"act_{ad_account_id}"

    def _range(self, start: date, end: date) -> dict:
        return {"time_range": json.dumps({"since": start.isoformat(), "until": end.isoformat()})}

    def account_spend(self, start: date, end: date) -> float:
        rows = self.meta.get_all(f"{self.act}/insights", level="account", fields="spend",
                                 **self._range(start, end))
        return sum(float(r.get("spend", 0)) for r in rows)

    def ad_rows(self, start: date, end: date) -> dict[str, dict]:
        rows = self.meta.get_all(f"{self.act}/insights", level="ad", fields=AD_FIELDS,
                                 limit=500, **self._range(start, end))
        return {r["ad_id"]: r for r in rows if int(r.get("impressions", 0)) > 0}

    def active_ad_ids(self) -> list[str]:
        rows = self.meta.get_all(f"{self.act}/ads", fields="id", limit=500,
                                 effective_status=json.dumps(["ACTIVE"]))
        return [r["id"] for r in rows]

    def details(self, ids: list[str]) -> dict[str, dict]:
        out = {}
        for i in range(0, len(ids), 50):
            out.update(self.meta.get("", ids=",".join(ids[i:i + 50]), fields=DETAIL_FIELDS))
        return out

    def lifetime_rows(self, ids: list[str]) -> dict[str, dict]:
        if not ids:
            return {}
        rows = self.meta.get_all(
            f"{self.act}/insights", level="ad", fields=AD_FIELDS, limit=500,
            date_preset="maximum",
            filtering=json.dumps([{"field": "ad.id", "operator": "IN", "value": ids}]),
        )
        return {r["ad_id"]: r for r in rows}
