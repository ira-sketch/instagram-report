"""Текст висновків через API Claude (Anthropic Messages API)."""
from __future__ import annotations

import html
import json
import logging
import re

import requests

log = logging.getLogger(__name__)

API = "https://api.anthropic.com/v1/messages"

COMMON = """Ти — аналітик SMM-агенції RED&Ko. Пишеш короткі висновки до звіту для робочої Telegram-групи.
Пиши українською. Формат: Telegram HTML, дозволені лише теги <b> та <i>; символи < > & поза тегами екрануй.
До 1500 символів. Перший рядок — заголовок (дано нижче). Далі 3–4 пункти, кожен з нового рядка, через порожній рядок:
емодзі + <b>коротка теза</b> + 1–2 речення з конкретними цифрами з даних і конкретною рекомендацією.
Використовуй лише цифри з даних. Якщо якихось даних немає (null або є помилка) — не вигадуй, коротко про це скажи.
Числа: пробіл між тисячами, кома в десяткових. Без вступу і без підсумкових фраз — лише заголовок і пункти."""

RULES = {
    ("buro", "weekly"): """Звіт Redko Buro (Instagram @redko_buro + реклама Meta, валюта €).
Оцінюй органіку (охоплення, взаємодії, дописи тижня) і рекламу (витрати, кліки, ціна кліку, CTR, CPM) у порівнянні з попереднім тижнем.
Якщо реклама не працювала — скажи про це одним пунктом і запропонуй, що просувати.""",
    ("veryvery", "weekly"): """Звіт Veryvery (Instagram @veryvery.ua + реклама Meta, валюта ₴).
Цілі — охоплення і підписники, а також план з Content Plan: підписники, охоплення, перегляди, взаємодії, промо-бюджет.
Кліки, ціна кліку і CTR — НЕ мета: не оцінюй і не рекомендуй за ними.
Обов'язкові пункти: (1) що відстає від плану тижня і що зробити, щоб наздогнати;
(2) підписники і кампанії — ціна підписника по кампаніях, які вимкнути/продовжити;
(3) «Що просувати на наступному тижні (дати дано)» — 1–2 конкретні дописи з posts_30d під показник, що найбільше відстає:
для охоплення/переглядів — з найбільшим органічним охопленням і переглядами; для підписників — механіки з найнижчою ціною підписника.
Якщо кампанія має мету на кліки/трафік (LINK_CLICKS, OUTCOME_TRAFFIC) — нагадай, що для охоплення краща мета «Впізнаваність / Охоплення»;
(4) бюджет: виконання тижневої частки, перевитрата/недовитрата, залишок місячного бюджету.""",
    ("veryvery", "monthly"): """Місячний звіт Veryvery «план / факт» (₴).
3–4 пункти: що виконано і що відстає від плану, з причиною; підсумок по рекламі; рекомендація на наступний місяць з урахуванням його плану.""",
}


def clean_html(text: str) -> str:
    """Лишаємо тільки <b>, <i>; усе інше екрануємо, щоб Telegram не відхилив повідомлення."""
    parts = re.split(r"(</?[bi]>)", text.strip())
    return "".join(p if re.fullmatch(r"</?[bi]>", p) else html.escape(html.unescape(p), quote=False)
                   for p in parts)


def write(api_key: str, model: str, brand: str, kind: str, header: str, data: dict,
          benchmarks: str = "") -> str:
    system = COMMON + "\n\n" + RULES.get((brand, kind), RULES[("buro", "weekly")])
    if benchmarks:
        system += "\n\nОрієнтири з попередніх місяців:\n" + benchmarks
    user = (f"Заголовок (перший рядок, як є): {header}\n\nДані звіту (JSON):\n"
            + json.dumps(data, ensure_ascii=False, default=str))
    r = requests.post(API, timeout=120, headers={
        "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 1500, "system": system,
              "messages": [{"role": "user", "content": user}]})
    if not r.ok:
        raise RuntimeError(f"API Claude: HTTP {r.status_code} {r.text[:300]}")
    text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise RuntimeError("API Claude повернув порожню відповідь")
    return clean_html(text)


def short_names(api_key: str, model: str, posts: list[dict], campaigns: list[str]) -> dict:
    """Короткі назви дописів (за підписом) і кампаній для таблиці: {id або назва: коротко}."""
    if not api_key or (not posts and not campaigns):
        return {}
    items = {"posts": [{"id": p["id"], "type": p.get("type"), "caption": (p.get("caption") or "")[:200]}
                       for p in posts], "campaigns": campaigns}
    prompt = ("Дай короткі назви (2–4 слова, до 26 символів) для рядків таблиці звіту. "
              "Для дописів — суть за підписом мовою підпису (якщо підпису немає — тип: Reel, Карусель, Фото). "
              "Для кампаній — скорочена назва кампанії, без дат і службових слів. "
              "Відповідь — лише JSON-об'єкт {\"<id допису або повна назва кампанії>\": \"коротка назва\"}.\n\n"
              + json.dumps(items, ensure_ascii=False))
    try:
        r = requests.post(API, timeout=60, headers={
            "x-api-key": api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": model, "max_tokens": 800, "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        text = "".join(b.get("text", "") for b in r.json().get("content", []) if b.get("type") == "text")
        m = re.search(r"\{.*\}", text, re.S)
        return {str(k): str(v) for k, v in json.loads(m.group(0)).items()} if m else {}
    except Exception as e:  # назви — не головне: без них лишається обрізаний підпис
        log.warning("Короткі назви не отримано: %s", e)
        return {}
