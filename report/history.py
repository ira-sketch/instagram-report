"""История отчётов и журнал запусков (data/history.json, коммитится в репозиторий)."""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

from .config import KYIV

PATH = Path(__file__).resolve().parent.parent / "data" / "history.json"
MAX_REPORTS = 400
MAX_RUNS = 300


class History:
    def __init__(self, path: Path = PATH):
        self.path = path
        self.data = {"reports": [], "runs": []}
        if path.exists():
            self.data.update(json.loads(path.read_text(encoding="utf-8")))

    def save(self):
        self.data["reports"] = self.data["reports"][-MAX_REPORTS:]
        self.data["runs"] = self.data["runs"][-MAX_RUNS:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def last_scheduled(self) -> dict | None:
        rep = [r for r in self.data["reports"] if r.get("kind") == "scheduled"]
        return rep[-1] if rep else None

    def baseline(self) -> dict | None:
        """С чем сравнивать: последний плановый отчёт (ручные /report базу не сдвигают)."""
        return self.last_scheduled()

    def is_due(self, now: datetime, hour: int, interval: int) -> tuple[bool, str]:
        if now.hour < hour:
            return False, f"ещё нет {hour}:00 по Киеву"
        last = self.last_scheduled()
        if not last:
            return True, "первый плановый отчёт"
        days = (now.date() - date.fromisoformat(last["date"])).days
        if days < interval:
            return False, f"прошло {days} дн. с последнего планового отчёта"
        return True, f"прошло {days} дн."

    def add_report(self, kind: str, data: dict, text: str):
        self.data["reports"].append({
            "date": data["today"], "kind": kind, "period_start": data["period"]["start"],
            "account": data["account"], "spend_month": data["spend_month"],
            "ads": {a["id"]: {"name": a["name"], "spend": a["spend"], "follows": a["follows"],
                              "profile_visits": a["profile_visits"], "reach": a["reach"],
                              "impressions": a["impressions"]}
                    for a in data["ads"]},
            "text": text,
        })

    def log_run(self, kind: str, status: str, detail: str = "", action_types: list | None = None):
        self.data["runs"].append({
            "at": datetime.now(KYIV).isoformat(timespec="seconds"), "kind": kind,
            "status": status, "detail": detail[:500], "action_types": action_types or [],
        })
