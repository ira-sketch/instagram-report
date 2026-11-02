"""Точка входу тижневих і місячних звітів «картинка + висновки».

python -m weekly.main --kind weekly  --mode scheduled   # за розкладом (не шле двічі за той самий тиждень)
python -m weekly.main --kind weekly  --mode manual      # надіслати зараз
python -m weekly.main --kind weekly  --mode test        # зібрати і зберегти картинку/текст, у чат не слати
python -m weekly.main --kind monthly --mode ...         # місячний «план / факт» (Veryvery)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from report.meta_api import MetaError

from . import build, conclusions, plan_xlsx
from .collect import collect_month, collect_week
from .config import TZ, WConfig
from .render_report import render
from .telegram import TgError, send_report, send_text

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("weekly")


# ------------------------------------------------------------------ стан
class State:
    def __init__(self, path: str):
        self.path = Path(path)
        self.data = {"sent": {}, "followers": [], "runs": []}
        if self.path.exists():
            self.data.update(json.loads(self.path.read_text(encoding="utf-8")))

    def save(self):
        self.data["runs"] = self.data["runs"][-200:]
        self.data["followers"] = self.data["followers"][-200:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=1), encoding="utf-8")

    def prev_followers(self, before: str) -> int | None:
        rows = [r for r in self.data["followers"] if r["date"] < before]
        return rows[-1]["followers"] if rows else None

    def log(self, kind: str, mode: str, status: str, detail: str = ""):
        self.data["runs"].append({"at": datetime.now(TZ).isoformat(timespec="seconds"), "kind": kind,
                                  "mode": mode, "status": status, "detail": detail[:500]})


# ------------------------------------------------------------------ запасні висновки
def fallback_text(header: str, extra: dict, d: dict) -> str:
    """Якщо API Claude недоступний — короткі висновки без ШІ, щоб звіт усе одно пішов."""
    lines = [header, "", "<i>Автоматичні висновки недоступні, нижче — короткий підсумок.</i>"]
    for row in extra.get("план_тижня", []):
        if row.get("виконання_%") is not None:
            mark = "✅" if row["виконання_%"] >= 100 else "⚠️"
            lines.append(f"{mark} {row['показник']}: {row['виконання_%']}% від плану тижня")
    if d.get("errors"):
        lines.append("❗ Частина даних недоступна: " + "; ".join(d["errors"])[:300])
    return "\n".join(lines)


def run_once(cfg: WConfig, kind: str, today: date, state: State, out_dir: Path) -> tuple[Path, str, dict, str]:
    plan, plan_err = None, ""
    if cfg.plan_file_id:
        for attempt in range(2):
            try:
                plan = plan_xlsx.load(cfg.plan_file_id, cfg.plan_sheet)
                break
            except Exception as e:
                plan_err = str(e)
                log.warning("Content Plan: %s", e)
                time.sleep(5)

    if kind == "weekly":
        d = collect_week(cfg, today, with_posts_30d=cfg.brand == "veryvery")
        period_key = d["week"]["start"]
        names = conclusions.short_names(cfg.anthropic_key, cfg.anthropic_model, d["posts"],
                                        [c["name"] for c in d.get("campaigns") or []])
        prev = state.prev_followers(today.isoformat())
        if prev is None and cfg.initial_followers.isdigit():
            prev = int(cfg.initial_followers)
        spec, extra = build.weekly_spec(d, cfg, prev, names, plan)
        nxt_s = date.fromisoformat(d["week"]["end"]) + timedelta(days=1)
        extra["наступний_тиждень"] = f"{build.ddmm(nxt_s.isoformat())}–{build.ddmm((nxt_s + timedelta(days=6)).isoformat())}"
        brand_part = f" · {cfg.brand_title}," if cfg.brand != "buro" else " ·"
        header = (f"💡 <b>Висновки{brand_part} тиждень "
                  f"{build.ddmm(d['week']['start'])}–{build.ddmm(d['week']['end'])}</b>")
        fname = f"report_{today.isoformat()}"
    else:
        d = collect_month(cfg, today)
        period_key = d["month"]["start"]
        names = conclusions.short_names(cfg.anthropic_key, cfg.anthropic_model, [],
                                        [c["name"] for c in d.get("campaigns") or []])
        spec, extra = build.monthly_spec(d, cfg, plan, names)
        m = date.fromisoformat(d["month"]["start"])
        header = f"💡 <b>Підсумки {build.UA_MONTHS_GEN[m.month - 1]} · {cfg.brand_title}</b>"
        fname = f"report_{today.isoformat()}_month"
    if plan_err and not plan:
        extra["помилка_плану"] = plan_err

    out_dir.mkdir(parents=True, exist_ok=True)
    png = out_dir / f"{fname}.png"
    render(spec, str(png))
    (out_dir / f"{fname}.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")

    # Для висновків — компактні дані: без довгих підписів, кандидати на просування — лише головне
    raw = dict(d)
    raw["posts"] = [{k: p.get(k) for k in ("date", "type", "reach", "views", "total_interactions", "shares", "saved")}
                    | {"назва": names.get(p["id"]) or (p.get("caption") or "")[:60]} for p in d.get("posts", [])]
    if "posts_30d" in d:
        top = sorted(d["posts_30d"], key=lambda p: p.get("reach") or 0, reverse=True)[:8]
        raw["posts_30d"] = [{"дата": p["date"], "тип": p.get("type"), "охоплення": p.get("reach"),
                             "перегляди": p.get("views"), "підпис": (p.get("caption") or "")[:80]} for p in top]
    for_ai = {"таблиця": spec, "сирі_дані": raw, "додатково": extra}
    try:
        if not cfg.anthropic_key:
            raise RuntimeError("немає ANTHROPIC_API_KEY")
        text = conclusions.write(cfg.anthropic_key, cfg.anthropic_model, cfg.brand, kind, header,
                                 for_ai, cfg.benchmarks)
    except Exception as e:
        log.warning("Висновки через API Claude не вдалися: %s", e)
        text = fallback_text(header, extra, d)
    (out_dir / f"{fname}.txt").write_text(text, encoding="utf-8")
    return png, text, d, period_key


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["weekly", "monthly"], default="weekly")
    ap.add_argument("--mode", choices=["scheduled", "manual", "test"], default="test")
    ap.add_argument("--today", help="перевизначити дату (YYYY-MM-DD)")
    ap.add_argument("--out", help="куди зберегти картинку і текст")
    args = ap.parse_args(argv)

    cfg = WConfig()
    today = date.fromisoformat(args.today) if args.today else datetime.now(TZ).date()
    state = State(cfg.state_file)
    out_dir = Path(args.out) if args.out else Path(cfg.state_file).parent / "out" / cfg.brand
    sending = args.mode != "test"

    miss = cfg.missing(sending)
    if miss:
        log.error("Не задано: %s", ", ".join(miss))
        return 1

    attempts = 1 + (cfg.retries if sending else 0)
    for attempt in range(1, attempts + 1):
        try:
            png, text, d, period_key = run_once(cfg, args.kind, today, state, out_dir)
            sent_key = f"{args.kind}:{period_key}"
            if args.mode == "test":
                print(f"\nКартинка: {png}\n" + "=" * 60 + "\n" + text + "\n" + "=" * 60)
                if d.get("errors"):
                    print("Помилки даних:", d["errors"])
                return 0
            if args.mode == "scheduled" and sent_key in state.data["sent"]:
                log.info("Звіт %s уже надіслано %s — пропускаю", sent_key, state.data["sent"][sent_key])
                return 0
            send_report(cfg.tg_bot_token, cfg.tg_chat_id, str(png), text, cfg.tg_thread_id)
            state.data["sent"][sent_key] = datetime.now(TZ).isoformat(timespec="seconds")
            if d.get("followers") is not None:
                state.data["followers"].append({"date": today.isoformat(), "followers": d["followers"]})
            state.log(args.kind, args.mode, "ok", f"спроба {attempt}")
            state.save()
            log.info("Звіт надіслано: %s", png)
            return 0
        except (MetaError, TgError, OSError, KeyError, ValueError, RuntimeError) as e:
            final = attempt == attempts or (isinstance(e, MetaError) and not e.retryable)
            log.exception("Спроба %d/%d не вдалася", attempt, attempts)
            state.log(args.kind, args.mode, "error", f"спроба {attempt}: {e}")
            state.save()
            if not sending:
                return 1
            if final:
                msg = (f"❗ {cfg.brand_title}: {'місячний' if args.kind == 'monthly' else 'тижневий'} звіт не сформовано.\n")
                if isinstance(e, MetaError) and e.token_problem:
                    msg += "Токен Meta недійсний або прострочений — потрібно оновити META_TOKEN на сервері.\n"
                msg += f"Деталі: {e}"
                try:
                    send_text(cfg.tg_bot_token, cfg.tg_chat_id, msg, cfg.tg_thread_id)
                except TgError:
                    log.exception("Не вдалося надіслати повідомлення про помилку")
                return 1
            time.sleep(cfg.retry_delay_sec)
    return 1


if __name__ == "__main__":
    sys.exit(main())
