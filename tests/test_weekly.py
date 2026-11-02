"""Тижневі/місячні звіти без доступу до Meta, Telegram і Claude: підміняємо відповіді API."""
import io
import json
from datetime import date

import openpyxl
import pytest

from report import meta_api
from weekly import build, conclusions, main as wmain, plan_xlsx
from weekly.collect import last_week, prev_month

IG = "17841478636477289"
ACT = "act_1508132533752052"


def fake_request(self, url, params):
    p = params or {}
    if url.endswith(f"/{IG}") and p.get("fields") == "followers_count":
        return {"followers_count": 3100}
    if url.endswith(f"{IG}/insights"):
        m = p["metric"]
        if m == "follows_and_unfollows":
            return {"data": [{"name": m, "total_value": {"breakdowns": [{"results": [
                {"dimension_values": ["FOLLOWER"], "value": 120},
                {"dimension_values": ["NON_FOLLOWER"], "value": 20}]}]}}]}
        vals = {"reach": 12000, "views": 30000, "accounts_engaged": 450, "total_interactions": 900,
                "likes": 700, "comments": 50, "shares": 40, "saves": 60, "profile_views": 600,
                "website_clicks": 20}
        if m == "website_clicks":
            raise meta_api.MetaError("metric not available", 100)
        return {"data": [{"name": m, "total_value": {"value": vals[m]}}]}
    if url.endswith(f"{IG}/media"):
        return {"data": [
            {"id": "p1", "caption": "Ідеальна трійка смаків <3 & кава", "timestamp": "2026-10-28T09:00:00+0000",
             "media_product_type": "REELS"},
            {"id": "p2", "caption": "", "timestamp": "2026-10-30T09:00:00+0000", "media_type": "IMAGE"},
            {"id": "old", "caption": "старий", "timestamp": "2026-09-01T09:00:00+0000", "media_type": "IMAGE"},
        ]}
    if url.endswith("/insights") and ("p1" in url or "p2" in url):
        v = {"reach": 1500 if "p1" in url else 300, "views": 2200, "total_interactions": 80,
             "shares": 5, "saved": 3, "likes": 60, "comments": 4}[p["metric"]]
        return {"data": [{"name": p["metric"], "values": [{"value": v}]}]}
    if url.endswith(f"{ACT}/insights"):
        tr = json.loads(p["time_range"])
        this = tr["since"] == "2026-10-26"
        if p["level"] == "account":
            return {"data": [{"spend": "2305" if this else "4039", "impressions": "12749" if this else "28362",
                              "reach": "8924" if this else "19965", "inline_link_clicks": "300",
                              "actions": [{"action_type": "onsite_conversion.ig_follow",
                                           "value": "220" if this else "421"}]}]}
        return {"data": [
            {"campaign_id": "1", "campaign_name": "Розіграш Halloween 2026 | OUTCOME_ENGAGEMENT", "objective": "OUTCOME_ENGAGEMENT",
             "spend": "2138", "impressions": "11000", "reach": "8000", "inline_link_clicks": "100",
             "actions": [{"action_type": "onsite_conversion.ig_follow", "value": "217"}]},
            {"campaign_id": "2", "campaign_name": "Батончики трафік", "objective": "OUTCOME_TRAFFIC",
             "spend": "167", "impressions": "1749", "reach": "1500", "inline_link_clicks": "85", "actions": []},
        ]}
    raise AssertionError(f"неочікуваний запит {url} {p}")


def plan_xlsx_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Metrics"
    ws.cell(2, 2, "September"); ws.cell(2, 4, "October"); ws.cell(2, 6, "November")
    for c in (2, 4, 6):
        ws.cell(3, c, "Plan"); ws.cell(3, c + 1, "Fact")
    vals = {5: (2000, 2400, 2755, 3012, 3200, None), 7: (12, 10, 14, 12, 15, None),
            8: (60000, 50000, 84000, 70000, 92407, None), 9: (150000, 0, 198000, 0, 210000, None),
            10: (3000, 0, 3850, 0, 4000, None), 16: (12000, 11000, 13500, 13575, 14000, None)}
    for row, (a, b, c, d, e, f) in vals.items():
        for col, v in zip(range(2, 8), (a, b, c, d, e, f)):
            ws.cell(row, col, v)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setattr(meta_api.Meta, "_request", fake_request)
    monkeypatch.setattr(plan_xlsx, "download", lambda fid: plan_xlsx_bytes())
    monkeypatch.setattr(conclusions, "short_names", lambda *a, **k: {"p1": "Ідеальна трійка"})
    monkeypatch.setenv("META_TOKEN", "x")
    monkeypatch.setenv("IG_USER_ID", IG)
    monkeypatch.setenv("AD_ACCOUNT_ID", ACT)
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_periods():
    assert last_week(date(2026, 11, 2)) == (date(2026, 10, 26), date(2026, 11, 1),
                                            date(2026, 10, 19), date(2026, 10, 25))
    assert last_week(date(2026, 11, 4))[0] == date(2026, 10, 26)
    assert prev_month(date(2026, 11, 1)) == (date(2026, 10, 1), date(2026, 10, 31))


def test_formatting():
    assert build.n(13023) == "13 023"
    assert build.money(9.85, "₴", 2) == "9,85 ₴"
    assert build.money(96.354, "€") == "96,35 €"
    assert build.signed(-7) == "−7"
    assert build.pct_change(100, 55) == "−45%"
    assert build.done(299, 107) == "▲ 279%"
    assert conclusions.clean_html("<b>Теза</b> <3 & <script>") == "<b>Теза</b> &lt;3 &amp; &lt;script&gt;"


def test_veryvery_weekly(env, monkeypatch, capsys):
    monkeypatch.setenv("BRAND", "veryvery")
    monkeypatch.setenv("BRAND_TITLE", "Veryvery")
    monkeypatch.setenv("IG_HANDLE", "veryvery.ua")
    monkeypatch.setenv("CURRENCY", "₴")
    monkeypatch.setenv("PLAN_FILE_ID", "abc")
    monkeypatch.setenv("INITIAL_FOLLOWERS", "2892")
    assert wmain.main(["--kind", "weekly", "--mode", "test", "--today", "2026-11-02",
                       "--out", str(env / "out")]) == 0
    spec = json.loads((env / "out" / "report_2026-11-02.json").read_text())
    titles = [s["title"] for s in spec["sections"]]
    assert titles == ["Instagram @veryvery.ua", "План місяця · жовтень (тижнева частка)", "Дописи тижня: 2",
                      "Реклама Meta · порівняння з попереднім тижнем", "Кампанії"]
    assert spec["sections"][0]["rows"][0] == ["Підписники", "3 100", "Зміна підписників", "+208"]
    assert spec["sections"][0]["rows"][4][3] == "н/д"
    plan = spec["sections"][1]["rows"]
    assert plan[0][0] == "Приріст підписників" and plan[0][1] == "80"  # (2755−2400)÷31×7
    assert spec["sections"][2]["rows"][0][0] == "Ідеальна трійка · 28.10"
    assert spec["sections"][4]["rows"][0][3] == "9,85"
    assert spec["sections"][4]["rows"][-1][3] == "—"
    text = (env / "out" / "report_2026-11-02.txt").read_text()
    assert text.startswith("💡 <b>Висновки · Veryvery, тиждень 26.10–01.11</b>")


def test_buro_weekly_no_ads(env, monkeypatch):
    def no_ads(self, url, params):
        if url.endswith(f"{ACT}/insights"):
            return {"data": []}
        return fake_request(self, url, params)
    monkeypatch.setattr(meta_api.Meta, "_request", no_ads)
    monkeypatch.setenv("CURRENCY", "€")
    assert wmain.main(["--kind", "weekly", "--mode", "test", "--today", "2026-11-02",
                       "--out", str(env / "out")]) == 0
    spec = json.loads((env / "out" / "report_2026-11-02.json").read_text())
    assert spec["sections"][-1]["rows"] == [["Реклама не працювала", "0 €"]]
    assert spec["sections"][0]["rows"][0][3] == "+100"  # без історії — нетто за тиждень


def test_veryvery_monthly(env, monkeypatch):
    monkeypatch.setenv("BRAND", "veryvery")
    monkeypatch.setenv("BRAND_TITLE", "Veryvery")
    monkeypatch.setenv("CURRENCY", "₴")
    monkeypatch.setenv("PLAN_FILE_ID", "abc")
    assert wmain.main(["--kind", "monthly", "--mode", "test", "--today", "2026-11-01",
                       "--out", str(env / "out")]) == 0
    spec = json.loads((env / "out" / "report_2026-11-01_month.json").read_text())
    rows = {r[0]: r for r in spec["sections"][0]["rows"]}
    assert rows["Підписники"][1:] == ["2 755", "3 100", "▲ 113%"]
    assert rows["Приріст підписників"][1:3] == ["+355", "+700"]
    assert spec["sections"][-1]["title"] == "План на листопад"
    assert spec["subtitle"] == "Жовтень 2026 · план / факт"


def test_scheduled_not_twice(env, monkeypatch):
    sent = []
    monkeypatch.setattr(wmain, "send_report", lambda *a, **k: sent.append(a))
    monkeypatch.setenv("TG_BOT_TOKEN", "t")
    monkeypatch.setenv("TG_CHAT_ID", "-1")
    args = ["--kind", "weekly", "--mode", "scheduled", "--today", "2026-11-02", "--out", str(env / "o")]
    assert wmain.main(args) == 0
    assert wmain.main(args) == 0
    assert len(sent) == 1
