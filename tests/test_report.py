"""Проверка без доступа к Meta: подменяем ответы API и смотрим на итоговый текст."""
import json
from datetime import date, datetime

import pytest

from report import meta_api
from report.collect import collect, periods
from report.config import KYIV, Config
from report.history import History
from report.message import build_message
from report.plan import parse_plan


def fake_request(self, url, params):
    p = params or {}
    if url.endswith("/17841478636477289") and p.get("fields") == "followers_count":
        return {"followers_count": 1333}
    if url.endswith("17841478636477289/insights"):
        m = p["metric"]
        if m == "reach":
            day = datetime.fromtimestamp(p["since"], KYIV).day
            return {"data": [{"name": "reach", "total_value": {"value": {1: 69427, 26: 8210, 23: 12070}[day]}}]}
        if m.startswith("views"):
            vals = {"views": 162223, "likes": 2500, "comments": 300, "saves": 320, "shares": 200}
            return {"data": [{"name": k, "total_value": {"value": v}} for k, v in vals.items()]}
        if m == "follows_and_unfollows":
            return {"data": [{"name": m, "total_value": {"value": 700, "breakdowns": [{"results": [
                {"dimension_values": ["FOLLOWER"], "value": 650},
                {"dimension_values": ["NON_FOLLOWER"], "value": 63}]}]}}]}
    if url.endswith("act_1508132533752052/insights"):
        if p.get("level") == "account":
            return {"data": [{"spend": "8300.50"}]}
        rows = [
            {"ad_id": "1", "ad_name": "Ролик 1 (UGC)", "reach": "18400", "impressions": "31200",
             "spend": "1620", "actions": [{"action_type": "ig_profile_visit", "value": "640"},
                                          {"action_type": "onsite_conversion.ig_follow", "value": "95"}]},
            {"ad_id": "2", "ad_name": "Ролик 2", "reach": "9000", "impressions": "30000",
             "spend": "2400", "actions": [{"action_type": "onsite_conversion.ig_follow", "value": "80"}]},
        ]
        return {"data": rows}
    if url.endswith("act_1508132533752052/ads"):
        return {"data": [{"id": "1"}, {"id": "3"}]}
    if url.endswith("graph.facebook.com/v23.0/"):
        return {
            "1": {"id": "1", "name": "Ролик 1 (UGC)", "effective_status": "ACTIVE",
                  "created_time": "2026-09-23T10:00:00+0000",
                  "adset": {"start_time": "2026-09-23T10:00:00+0300", "learning_stage_info": {"status": "SUCCESS"}}},
            "2": {"id": "2", "name": "Ролик 2", "effective_status": "ACTIVE",
                  "created_time": "2026-09-10T10:00:00+0000", "adset": {"learning_stage_info": {"status": "LEARNING"}}},
            "3": {"id": "3", "name": "Новый ролик", "effective_status": "ACTIVE",
                  "created_time": "2026-09-28T10:00:00+0000", "adset": {}},
        }
    raise AssertionError(f"неожиданный запрос {url} {p}")


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr(meta_api.Meta, "_request", fake_request)
    c = Config()
    c.meta_token = "x"
    return c


def test_full_report(cfg, tmp_path):
    data = collect(cfg, date(2026, 9, 29))
    json.dumps(data)  # сериализуется
    hist = History(tmp_path / "h.json")
    baseline = {"ads": {"2": {"spend": 1500, "follows": 70}}}  # было 21 грн/подп, стало 90 за 10
    plan = {"followers": 1463, "reach": 80000, "budget": 13500}
    text = build_message(data, baseline, plan, cfg)
    print(text)
    assert "Охваты: 69 427 · за 3 дн. 8 210 (−32%)" in text
    assert "Подписчики: 1 333 (+587)" in text
    assert "Взаимодействия: 3 320" in text
    assert "«Ролик 1 (UGC)» · активна, 6 дн." in text
    assert "Переходы в профиль 640 · Подписчики 95" in text
    assert "Потрачено 1 620 грн (17 грн/подп.)" in text
    assert "«Ролик 2» · на обучении" in text
    assert "«Новый ролик» · активна, 1 дн. (рано оценивать)" in text
    assert "Бюджет: потрачено 8 300 из 13 500 грн" in text
    assert "⚠ Охваты за 3 дня упали на 32%" in text
    assert "⚠ «Ролик 2»: частота 3,3" in text
    assert "⚠ «Ролик 2»: стоимость подписчика выросла до 90 грн" in text
    assert "⚠ Расход отстаёт от графика на 34% (8 300 из 12 600 грн к этой дате)." in text
    assert "Показов пока нет" in text


def test_periods():
    p = periods(date(2026, 10, 1))
    assert p["full_month"] and p["start"] == date(2026, 9, 1) and p["end"] == date(2026, 9, 30)
    p = periods(date(2026, 10, 3))
    assert p["prev"] == (date(2026, 9, 1), date(2026, 9, 30)) and p["end"] == date(2026, 10, 2)
    assert periods(date(2026, 10, 4))["prev"] is None


def test_schedule(tmp_path):
    h = History(tmp_path / "h.json")
    at = lambda d, hr: datetime(2026, 10, d, hr, 5, tzinfo=KYIV)
    assert not h.is_due(at(1, 8), 9, 3)[0]
    assert h.is_due(at(1, 9), 9, 3)[0]
    h.data["reports"].append({"date": "2026-10-01", "kind": "scheduled"})
    h.data["reports"].append({"date": "2026-10-02", "kind": "manual"})
    assert not h.is_due(at(1, 10), 9, 3)[0]
    assert not h.is_due(at(3, 9), 9, 3)[0]
    assert h.is_due(at(4, 9), 9, 3)[0]


def test_plan_parse():
    csv = "Месяц,Подписчики (цель на конец месяца),Охваты,Бюджет рекламы грн\n" \
          "2026-09,1 463,80000,\"13 500\"\nОктябрь 2026,1700,90000,15000\n"
    assert parse_plan(csv, date(2026, 9, 28)) == {"followers": 1463, "reach": 80000, "budget": 13500}
    assert parse_plan(csv, date(2026, 10, 2))["budget"] == 15000
    assert parse_plan(csv, date(2026, 11, 2)) == {}


def test_plan_real_sheet_header():
    csv = ("Месяц,Подписчики — цель на конец месяца (всего),Охваты за месяц,"
           "Бюджет рекламы за месяц (грн),Комментарий\n"
           "Сентябрь 2026,1463,80000,13500,заметка\nОктябрь 2026,,,,\n")
    assert parse_plan(csv, date(2026, 9, 5)) == {"followers": 1463, "reach": 80000, "budget": 13500}
    assert parse_plan(csv, date(2026, 10, 5)) == {}
