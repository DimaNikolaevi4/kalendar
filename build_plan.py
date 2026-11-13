# -*- coding: utf-8 -*-
"""build_plan.py — собрать plans/*.json в единый PLAN.md.

Секции (сверху вниз по важности):
  * Просрочено   — when < сегодня и статус не done/skipped (старейшие сверху);
  * Сегодня      — when == сегодня;
  * На неделю    — сегодня < when <= +7 дней;
  * Запланировано— позже (сворачиваемо, группировка по репо);
  * Backlog      — без даты или статус backlog;
  * Сводка       — счётчики по репозиториям.

Сборка: задача Планировщика «planner build plan», ежедневно 07:25 МСК
(утреннее окно 07:00-10:00 проверяется в bin/build_plan.ps1).

Использование:
  python build_plan.py [--push]
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent
MSK = timezone(timedelta(hours=3))
OUT = HUB / "PLAN.md"
PLANS = HUB / "plans"
WEEK = 7
STATUS_RU = {
    "scheduled": "запланировано",
    "todo": "сделать",
    "in-progress": "в работе",
    "done": "сделано",
    "skipped": "пропущено",
    "backlog": "без срока",
}
OPEN_STATUSES = {"scheduled", "todo", "in-progress"}


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], cwd=str(HUB), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        print(f"FAIL: git {' '.join(args[:2])}: "
              f"{(r.stderr or r.stdout).strip()[-300:]}")
        sys.exit(1)
    return r.stdout


def load() -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for p in sorted(PLANS.glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        repo = d.get("repo") or p.stem
        for t in d.get("tasks") or []:
            rows.append((repo, t))
    return rows


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def row(repo: str, t: dict, today: date) -> str:
    when = t.get("when") or ""
    st = STATUS_RU.get(t.get("status") or "todo", t.get("status") or "")
    link = f"[открыть]({t['link']})" if t.get("link") else "—"
    days = ""
    if when and t.get("status") in OPEN_STATUSES and date.fromisoformat(when) < today:
        days = f" (**+{(today - date.fromisoformat(when)).days} дн.**)"
    why = esc(t.get("why") or "")
    title = f"{esc(t.get('title') or '')}{days}"
    return f"| {when or '—'} | {repo} | {title} | {st} | {why} | {link} |"


def main() -> None:
    push = "--push" in sys.argv
    now = datetime.now(MSK)
    today = now.date()
    week_end = today + timedelta(days=WEEK)

    overdue: list[tuple[date, str, dict]] = []
    today_rows: list[tuple[str, dict]] = []
    week: list[tuple[date, str, dict]] = []
    later: list[tuple[date, str, dict]] = []
    backlog: list[tuple[str, dict]] = []
    done = 0
    for repo, t in load():
        st = t.get("status") or "todo"
        when = t.get("when") or ""
        if st == "done":
            done += 1
            continue
        if st == "skipped":
            continue
        if st == "backlog" or not when:
            backlog.append((repo, t))
            continue
        d = date.fromisoformat(when)
        if d < today:
            overdue.append((d, repo, t))
        elif d == today:
            today_rows.append((repo, t))
        elif d <= week_end:
            week.append((d, repo, t))
        else:
            later.append((d, repo, t))

    overdue.sort(key=lambda x: x[0])
    week.sort(key=lambda x: x[0])
    later.sort(key=lambda x: x[0])

    lines: list[str] = []
    say = lines.append
    say(f"# План по всем репозиториям `E:\\github`")
    say("")
    say(f"> Собрано автоматически: **{now:%d.%m.%Y %H:%M} МСК**, "
        f"задача «planner build plan» (07:25). Источники — `plans/*.json`,")
    say("> их «скидывают» репозитории скриптом `drop.py`; источник истины — "
        "`plan.json` в корне каждого репо. Ручные правки PLAN.md бессмысленны.")
    # подсчёт по репозиториям
    per: dict[str, dict[str, int]] = {}
    for repo, t in load():
        st = t.get("status") or "todo"
        d = per.setdefault(repo, {"всего": 0, "просрочено": 0, "сделано": 0})
        d["всего"] += 1
        if st == "done":
            d["сделано"] += 1
        elif st in OPEN_STATUSES and t.get("when") and date.fromisoformat(t["when"]) < today:
            d["просрочено"] += 1

    say("")
    say(f"Обновлено планов в хабе: **{len(list(PLANS.glob('*.json')))}** · "
        f"задач всего: **{sum(d['всего'] for d in per.values())}**")

    say("")
    say(f"Открытых задач: {len(overdue) + len(today_rows) + len(week) + len(later) + len(backlog)}"
        f" · просрочено: **{len(overdue)}** · сделано: {done}")
    say("")
    say("| репозиторий | всего | просрочено | сделано |")
    say("|---|---|---|---|")
    for repo in sorted(per):
        d = per[repo]
        say(f"| {repo} | {d['всего']} | {d['просрочено']} | {d['сделано']} |")

    def section(title: str, rows: list) -> None:
        say("")
        say(f"## {title}")
        say("")
        if not rows:
            say("пусто")
            return
        say("| когда | репо | задача | статус | зачем | ссылка |")
        say("|---|---|---|---|---|---|")
        for item in rows:
            if isinstance(item, tuple) and len(item) == 3 and isinstance(item[0], date):
                d, repo, t = item
                say(f"| {d:%d.%m.%Y} | {repo} | {esc(t.get('title') or '')} | "
                    f"{STATUS_RU.get(t.get('status') or 'todo', '')} | "
                    f"{esc(t.get('why') or '')} | "
                    + (f"[открыть]({t['link']})" if t.get("link") else "—") + " |")
            else:
                repo, t = item
                say(row(repo, t, today))

    section("Просрочено", overdue)
    section("Сегодня", today_rows)
    section(f"На неделю (до {(week_end):%d.%m.%Y})", week)

    say("")
    say(f"## Запланировано (позже {week_end:%d.%m.%Y})")
    say("")
    if later:
        say("<details><summary>задач: "
            f"{len(later)} — развернуть</summary>")
        say("")
        say("| когда | репо | задача | зачем |")
        say("|---|---|---|---|")
        for d, repo, t in later:
            say(f"| {d:%d.%m.%Y} | {repo} | {esc(t.get('title') or '')} | "
                f"{esc(t.get('why') or '')} |")
        say("")
        say("</details>")
    else:
        say("пусто")

    say("")
    say("## Backlog (без срока)")
    say("")
    if backlog:
        say("| репо | задача | зачем | ссылка |")
        say("|---|---|---|---|")
        for repo, t in backlog:
            say(f"| {repo} | {esc(t.get('title') or '')} | {esc(t.get('why') or '')} | "
                + (f"[открыть]({t['link']})" if t.get("link") else "—") + " |")
    else:
        say("пусто")
    say("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"PLAN.md: {OUT.name} написан "
          f"(просрочено {len(overdue)}, сегодня {len(today_rows)}, "
          f"неделя {len(week)}, позже {len(later)}, backlog {len(backlog)})")

    if push:
        git("add", "PLAN.md")
        st = git("status", "--porcelain", "PLAN.md")
        if st.strip():
            git("commit", "-m", f"PLAN.md: сборка {now:%d.%m.%Y %H:%M} "
                                f"(просрочено {len(overdue)})")
            git("push", "origin", "main")
            print("PLAN.md: коммит+пуш")
        else:
            print("PLAN.md: без изменений")


if __name__ == "__main__":
    main()
