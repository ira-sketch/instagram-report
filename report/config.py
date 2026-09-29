"""Настройки берутся из переменных окружения (секретов GitHub)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")


def _list(name: str, default: str) -> list[str]:
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


@dataclass
class Config:
    meta_token: str = field(default_factory=lambda: os.getenv("META_TOKEN", ""))
    ig_user_id: str = field(default_factory=lambda: os.getenv("IG_USER_ID", "17841478636477289"))
    ad_account_id: str = field(default_factory=lambda: os.getenv("AD_ACCOUNT_ID", "1508132533752052"))
    graph_version: str = field(default_factory=lambda: os.getenv("GRAPH_VERSION", "v23.0"))
    tg_bot_token: str = field(default_factory=lambda: os.getenv("TG_BOT_TOKEN", ""))
    tg_chat_id: str = field(default_factory=lambda: os.getenv("TG_CHAT_ID", ""))
    plan_csv_url: str = field(default_factory=lambda: os.getenv("PLAN_CSV_URL", ""))

    currency: str = field(default_factory=lambda: os.getenv("CURRENCY", "грн"))
    # Курс пересчёта валюты кабинета в гривну (1 — кабинет уже в гривне)
    currency_rate: float = field(default_factory=lambda: float(os.getenv("CURRENCY_RATE", "1")))

    report_hour: int = field(default_factory=lambda: int(os.getenv("REPORT_HOUR", "9")))
    interval_days: int = field(default_factory=lambda: int(os.getenv("REPORT_INTERVAL_DAYS", "3")))
    retries: int = field(default_factory=lambda: int(os.getenv("RETRIES", "3")))
    retry_delay_sec: int = field(default_factory=lambda: int(os.getenv("RETRY_DELAY_SEC", "900")))

    # Пороги предупреждений
    cpf_growth: float = 0.30        # стоимость подписчика выросла > 30 %
    reach_drop: float = 0.25        # охваты упали > 25 %
    max_frequency: float = 3.0      # частота выше 3
    pace_lag: float = 0.20          # расход отстаёт от графика > 20 %
    min_follows_for_cpf: int = 3    # минимум новых подписчиков для сравнения стоимости

    # Типы действий Marketing API; первый найденный используется.
    # После первого запуска сверяем с журналом (data/history.json → runs → action_types).
    profile_visit_actions: list[str] = field(default_factory=lambda: _list(
        "PROFILE_VISIT_ACTIONS",
        "ig_profile_visit,onsite_conversion.ig_profile_visit,instagram_profile_visit,profile_visit"))
    follow_actions: list[str] = field(default_factory=lambda: _list(
        "FOLLOW_ACTIONS",
        "onsite_conversion.ig_follow,ig_follow,instagram_profile_follow,follow"))

    def missing(self) -> list[str]:
        need = {"META_TOKEN": self.meta_token, "TG_BOT_TOKEN": self.tg_bot_token,
                "TG_CHAT_ID": self.tg_chat_id}
        return [k for k, v in need.items() if not v]
