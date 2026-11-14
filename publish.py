#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""publish.py — опубликовать план в канал «Календарь» (платформа MAX).

Публикует ДВА сообщения:
  1) весь план (рабочая часть по репозиториям; MAX — одной строкой, автопилот);
  2) красная зона отдельно (задачи с «красная зона» в заголовке/why).

Токен и chat_id берутся из E:\github\MAX\local\tokens.json[<канал>]
(по умолчанию канал calendar, chat_id канала «Календарь»).
Данные — из plans/*.json (сбрасываются build_plan.py / drop.py; при
--drop сперва прогнать drop для всех участников: py build_plan.py --no-drop).

Использование:
  py publish.py [--dry-run] [--channel calendar] [--token-channel calendar]
  py publish.py --text-file сообщение.md        # опубликовать свой текст

Отчёт: local/publish-<канал>.txt (UTF-8). Лимит MAX на сообщение ~4000
символов — тексты собираются короткими, при превышении скрипт падает.
"""
from __future__ import annotations

import argparse
import json
import re
import ssl
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent
GITHUB = HUB.parent
MAX_REPO = GITHUB / "MAX"
TOKENS = MAX_REPO / "local" / "tokens.json"
CA = MAX_REPO / "local" / "russian_ca_bundle.pem"
API = "https://platform-api2.max.ru"
MSK = timezone(timedelta(hours=3))
LIMIT = 3900  # запас до 4000 (лимит MAX)
STATUS_MARK = {"in-progress": "⏳", "todo": "•", "scheduled": "🕓",
               "backlog": "◇", "done": "✔", "skipped": "✖"}
REPONAME = {"demoexam-kip": "demoexam-kip (ДЭ)"}


def run_drop_all() -> None:
    r = subprocess.run([sys.executable, str(HUB / "build_plan.py"), "--no-drop"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    if r.returncode != 0:
        sys.exit(f"FAIL: build_plan (сброс планов): {(r.stderr or r.stdout)[-400:]}")


def load_plans() -> dict[str, list[dict]]:
    out = {}
    for p in sorted((HUB / "plans").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out[p.stem] = d.get("tasks") or []
    return out


def clean_title(title: str) -> str:
    """Убрать метку «красная зона» из заголовка (она уже показана значком 🔴)."""
    t = re.sub(r"\s*[,–-]?\s*красная зона\.?", "", title or "", flags=re.I)
    return t.strip(" -,")


def is_red(t: dict) -> bool:
    blob = (t.get("title") or "") + " " + (t.get("why") or "")
    return "красная зона" in blob.lower()


def ru_date(iso: str | None) -> str:
    if not iso:
        return ""
    d = datetime.fromisoformat(iso)
    return f"{d.day:02d}.{d.month:02d}"


def fmt_task(t: dict) -> str:
    mark = STATUS_MARK.get(t.get("status") or "", "•")
    when = ru_date(t.get("when"))
    prefix = f"{when} " if when else ""
    red = "🔴" if is_red(t) else ""
    title = clean_title(t.get("title") or "")
    return f"{mark} {prefix}{red}{title}".strip()


def order_key(t: dict):
    return (t.get("when") or "9999-12-31", t.get("status") or "")


def build_full(plans: dict[str, list[dict]]) -> str:
    now = datetime.now(MSK)
    open_n = sum(1 for repo, ts in plans.items() if repo != "MAX"
                 for t in ts if t.get("status") not in ("done", "skipped"))
    over_n = sum(1 for repo, ts in plans.items() if repo != "MAX"
                 for t in ts if t.get("status") not in ("done", "skipped")
                 and t.get("when") and t["when"] < now.strftime("%Y-%m-%d"))
    lines = [f"📅 План по репозиториям — {now:%d.%m.%Y}",
             f"Рабочих открытых задач: {open_n} · просрочено: {over_n} · "
             "источник — plan.json в каждом репо (полная версия: PLAN.md в kalendar)",
             ""]
    # репо с конкретными задачами (не только backlog)
    def repo_key(kv: tuple[str, list[dict]]):
        ts = kv[1]
        if not ts:
            return ("9999-12-31", 1)
        with_date = [t for t in ts if t.get("when")]
        if not with_date:
            return ("9999-12-31", 1)
        return (min(t["when"] for t in with_date), 0)

    ordered = sorted(plans.items(), key=repo_key)
    for repo, tasks in ordered:
        if not tasks:
            continue
        name = REPONAME.get(repo, repo)
        if repo == "MAX":
            sched = sum(1 for t in tasks if t.get("status") == "scheduled")
            lines.append(f"— MAX ({len(tasks)}): автопилот — публикации каналов "
                         f"по расписанию, запланировано {sched}")
            continue
        only_backlog = all(t.get("status") == "backlog" and not t.get("when")
                           and "Срочных дел нет" in (t.get("title") or "")
                           for t in tasks)
        if only_backlog:
            lines.append(f"— {name}: срочных дел нет (repo-review в свободное время)")
            continue
        lines.append(f"— {name} ({len(tasks)}):")
        for t in sorted(tasks, key=order_key):
            lines.append("   " + fmt_task(t))
    return "\n".join(lines)


def build_red(plans: dict[str, list[dict]]) -> str:
    now = datetime.now(MSK)
    reds = []
    for repo, tasks in plans.items():
        for t in tasks:
            if is_red(t) and t.get("status") not in ("done", "skipped"):
                reds.append((t.get("when") or "9999-12-31", repo, t))
    reds.sort(key=lambda x: (x[0], x[1]))
    lines = [f"🔴 КРАСНАЯ ЗОНА — {now:%d.%m.%Y}",
             "дедлайны, которые нельзя сдвинуть", ""]
    if not reds:
        lines.append("красных задач нет")
    for i, (when, repo, t) in enumerate(reds, 1):
        d = ru_date(when) if when != "9999-12-31" else "без срока"
        wd = ""
        if when != "9999-12-31":
            weekday = datetime.fromisoformat(when).weekday()
            wd = " (" + "пн вт ср чт пт сб вс".split()[weekday] + ")"
        why = (t.get("why") or "").strip()
        lines.append(f"{i}. {d}{wd} — {repo}: {clean_title(t.get('title') or '')}")
        if why:
            lines.append(f"   {why}")
    return "\n".join(lines)


def max_api(token: str, method: str, url: str, payload: dict | None = None) -> dict:
    if not url.startswith("http"):
        url = f"{API}{url}"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8") \
        if payload is not None else b"{}"
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", token)
    req.add_header("Content-Type", "application/json")
    ctx = ssl.create_default_context()
    if CA.exists():
        ctx.load_verify_locations(cafile=str(CA))
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=120) as r:
            return json.loads(r.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return {"__http_error": e.code,
                "body": e.read().decode("utf-8", errors="replace")[:300]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", default="calendar")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--text-file", default="")
    ap.add_argument("--no-drop", action="store_true",
                    help="не пересобирать plans/*.json (только что пересобрали)")
    a = ap.parse_args()

    toks = json.loads(TOKENS.read_text(encoding="utf-8"))
    tok = toks.get(a.channel) or {}
    token, chat_id = tok.get("token"), tok.get("chat_id")
    if not (token and chat_id):
        sys.exit(f"FAIL: в {TOKENS.name}[{a.channel!r}] нет token/chat_id")

    if a.text_file:
        messages = [Path(a.text_file).read_text(encoding="utf-8")]
    else:
        if not a.no_drop:
            run_drop_all()
        plans = load_plans()
        messages = [build_full(plans), build_red(plans)]

    report = [f"publish -> канал {a.channel!r} (chat_id={chat_id}), "
              f"{datetime.now(MSK):%d.%m.%Y %H:%M} МСК"]
    ok_all = True
    for i, text in enumerate(messages, 1):
        if len(text) > LIMIT:
            sys.exit(f"FAIL: сообщение {i} длиннее {LIMIT}: {len(text)}")
        if a.dry_run:
            print(f"--- сообщение {i} ({len(text)} зн.), dry-run:")
            print(text)
            print()
            continue
        resp = max_api(token, "POST", f"/messages?chat_id={chat_id}",
                       {"text": text})
        mid = resp.get("message") or resp.get("message_id")
        if resp.get("__http_error") or not mid:
            ok_all = False
            report.append(f"FAIL msg{i}: {json.dumps(resp, ensure_ascii=False)[:300]}")
            print(f"FAIL: сообщение {i}: {json.dumps(resp, ensure_ascii=False)[:300]}")
        else:
            report.append(f"ok msg{i}: message_id={mid}, {len(text)} зн.")
            print(f"ok: сообщение {i} опубликовано, message_id={mid}")

    out = HUB / "local" / f"publish-{a.channel}.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    if not ok_all:
        sys.exit(1)


if __name__ == "__main__":
    main()
