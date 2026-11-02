"""Налаштування беруться зі змінних середовища (/etc/instagram-report/weekly-*.env)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


@dataclass
class WConfig:
    # Який звіт: buro або veryvery (визначає секції таблиці та правила висновків)
    brand: str = field(default_factory=lambda: _env("BRAND", "buro"))
    brand_title: str = field(default_factory=lambda: _env("BRAND_TITLE", "Redko Buro"))
    ig_handle: str = field(default_factory=lambda: _env("IG_HANDLE", "redko_buro"))

    meta_token: str = field(default_factory=lambda: _env("META_TOKEN"))
    graph_version: str = field(default_factory=lambda: _env("GRAPH_VERSION", "v23.0"))
    ig_user_id: str = field(default_factory=lambda: _env("IG_USER_ID"))
    ad_account_id: str = field(default_factory=lambda: _env("AD_ACCOUNT_ID"))
    currency: str = field(default_factory=lambda: _env("CURRENCY", "€"))

    tg_bot_token: str = field(default_factory=lambda: _env("TG_BOT_TOKEN"))
    tg_chat_id: str = field(default_factory=lambda: _env("TG_CHAT_ID"))
    tg_thread_id: str = field(default_factory=lambda: _env("TG_THREAD_ID"))

    anthropic_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-sonnet-5-5"))

    # Content Plan (xlsx на Google Drive, відкритий за посиланням) — лише для Veryvery
    plan_file_id: str = field(default_factory=lambda: _env("PLAN_FILE_ID"))
    plan_sheet: str = field(default_factory=lambda: _env("PLAN_SHEET", "Metrics"))

    state_file: str = field(default_factory=lambda: _env("STATE_FILE", "/var/lib/instagram-report/weekly-state.json"))
    # Підписники з останнього звіту на комп'ютері — для першого порівняння на сервері
    initial_followers: str = field(default_factory=lambda: _env("INITIAL_FOLLOWERS"))
    # Орієнтири для висновків (вільний текст, необов'язково)
    benchmarks: str = field(default_factory=lambda: _env("BENCHMARKS"))

    retries: int = field(default_factory=lambda: int(_env("RETRIES", "2")))
    retry_delay_sec: int = field(default_factory=lambda: int(_env("RETRY_DELAY_SEC", "600")))

    @property
    def act(self) -> str:
        a = self.ad_account_id
        return a if a.startswith("act_") else f"act_{a}"

    def missing(self, need_send: bool) -> list[str]:
        need = {"META_TOKEN": self.meta_token, "IG_USER_ID": self.ig_user_id,
                "AD_ACCOUNT_ID": self.ad_account_id}
        if need_send:
            need.update({"TG_BOT_TOKEN": self.tg_bot_token, "TG_CHAT_ID": self.tg_chat_id})
        return [k for k, v in need.items() if not v]
