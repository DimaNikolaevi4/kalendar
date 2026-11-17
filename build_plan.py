# -*- coding: utf-8 -*-
"""build_plan.py — собрать plans/*.json в единый PLAN.md.

Перед сборкой «скидывает» планы участников (список — participants.txt):
для каждого репо запускается drop.py <REPO> --no-push, так что хаб всегда
собирается из свежих plan.json. Сбои одного репо не ломают сборку.

Секции (сверху вниз по важности):
  * Просрочено   — when < сегодня и статус не done/skipped (старейшие сверху);
  * Сегодня      — when == сегодня;
  * На неделю    — сегодня < when <= +7 дней;
  * Запланировано— позже (сворачиваемо, группировка по репо);
  * Backlog      — без даты или статус backlog;
  * Сводка       — счётчики по репозиториям и свежесть их планов.

Сборка: задача Планировщика «Календарь build plan», ежедневно 07:25 МСК
(утреннее окно 07:00-10:00 проверяется в bin/build_plan.ps1).

Использование:
  python build_plan.py [--push] [--no-drop]
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent
GITHUB = HUB.parent
MSK = timezone(timedelta(hours=3))
OUT = HUB / "PLAN.md"
PLANS = HUB / "plans"
PARTNERS = HUB / "participants.txt"
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


def drop_partners() -> list[str]:
    """drop.py <REPO> --no-push для каждого участника (см. participants.txt).

    Пуш не нужен: build_plan.py --push в конце отправляет в GitHub и планы,
    и PLAN.md одним пушем. Сбой одного репо не прерывает сборку.
    """
    if "--no-drop" in sys.argv or not PARTNERS.is_file():
        return []
    repos = [ln.strip() for ln in
             PARTNERS.read_text(encoding="utf-8").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    out: list[str] = []
    for repo in repos:
        r = subprocess.run(
            [sys.executable, str(HUB / "drop.py"), repo, "--no-push"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=120)
        line = ((r.stdout or "").strip().splitlines() or [""])[-1]
        if r.returncode != 0:
            err = ((r.stderr or r.stdout or "").strip().splitlines() or ["?"])
            line = f"FAIL {repo}: {err[-1][-200:]}"
        out.append(line)
    return out


def participants() -> set[str]:
    """Имена репозиториев-участников из participants.txt (нижний регистр)."""
    try:
        raw = PARTNERS.read_text(encoding="utf-8").splitlines()
    except OSError:
        return set()
    return {ln.strip().lower() for ln in raw if ln.strip() and not ln.strip().startswith("#")}


def valid_plan(p) -> bool:
    """План учитывается, только если репозиторий есть в участниках и папка на диске."""
    repo = p.stem
    if repo.lower() not in participants():
        return False
    return (GITHUB / repo).is_dir()


def plan_meta() -> dict[str, str]:
    """repo -> updated_at из plans/*.json (свежесть плана репо)."""
    out: dict[str, str] = {}
    for p in sorted(PLANS.glob("*.json")):
        if not valid_plan(p):
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out[d.get("repo") or p.stem] = (d.get("updated_at") or "")
    return out


def hub_url() -> str | None:
    """Базовый URL хаба на GitHub (по remote.origin.url хаба)."""
    try:
        url = subprocess.run(
            ["git", "-C", str(HUB), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15).stdout.strip()
    except Exception:
        return None
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"https://github.com/{m.group(1)}/{m.group(2)}" if m else None


def load() -> list[tuple[str, dict]]:
    rows: list[tuple[str, dict]] = []
    for p in sorted(PLANS.glob("*.json")):
        if not valid_plan(p):
            print(f"  SKIP plans/{p.name}: репозитория нет среди участников или нет папки — план игнорируется")
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        repo = d.get("repo") or p.stem
        for t in d.get("tasks") or []:
            rows.append((repo, t))
    return rows


def github_link(repo: str, rel: str | None) -> str | None:
    """Ссылка на файл в GitHub-репозитории (по remote.origin.url и ветке).
    Если remote не разобрать — None (ссылка останется сырой)."""
    if not rel:
        return None
    from urllib.parse import quote
    rel = quote(rel)
    src = GITHUB / repo
    try:
        url = subprocess.run(
            ["git", "-C", str(src), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15).stdout.strip()
        branch = subprocess.run(
            ["git", "-C", str(src), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=15).stdout.strip()
    except Exception:
        return None
    m = re.search(r"github\.com[/:]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    if not m or not branch:
        return None
    return f"https://github.com/{m.group(1)}/{m.group(2)}/blob/{branch}/{rel}"


def esc(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def fmt_date(s: str) -> str:
    return f"{date.fromisoformat(s):%d.%m.%Y}" if s else "—"


def fmt_updated(raw: str) -> str:
    """updated_at ISO -> '13.11 21:03' (год опускаем — всегда текущий)."""
    if not raw:
        return "?"
    try:
        return f"{datetime.fromisoformat(raw):%d.%m %H:%M}"
    except ValueError:
        return raw[:16].replace("T", " ")


def when_md(t: dict) -> str:
    s = fmt_date(t.get("when") or "")
    if t.get("when") and t.get("time"):
        s += f" {t['time']}"
    return s


def link_md(repo: str, t: dict) -> str:
    raw = t.get("link") or ""
    if not raw:
        return "—"
    gh = github_link(repo, raw)
    return f"[открыть]({gh})" if gh else f"[открыть]({esc(raw)})"


def row(repo: str, t: dict, today: date) -> str:
    when = t.get("when") or ""
    st = STATUS_RU.get(t.get("status") or "todo", t.get("status") or "")
    days = ""
    if when and t.get("status") in OPEN_STATUSES and date.fromisoformat(when) < today:
        days = f" (**+{(today - date.fromisoformat(when)).days} дн.**)"
    why = esc(t.get("why") or "")
    title = f"{esc(t.get('title') or '')}{days}"
    return f"| {when_md(t)} | {repo} | {title} | {st} | {why} | {link_md(repo, t)} |"


def main() -> None:
    push = "--push" in sys.argv
    now = datetime.now(MSK)
    today = now.date()
    week_end = today + timedelta(days=WEEK)

    dropped = drop_partners()
    if dropped:
        print("DROP:")
        for line in dropped:
            print(f"  {line}")

    meta = plan_meta()
    base = hub_url()

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
    today_rows.sort(key=lambda x: (x[1].get("when") or "", x[1].get("time") or ""))
    week.sort(key=lambda x: (x[0], x[2].get("time") or ""))
    later.sort(key=lambda x: (x[0], x[2].get("time") or ""))

    lines: list[str] = []
    say = lines.append
    say(f"# План по всем репозиториям `E:\\github`")
    say("")
    say(f"> Собрано автоматически: **{now:%d.%m.%Y %H:%M} МСК**, "
        f"задача «Календарь build plan» (07:25). Источники — `plans/*.json`,")
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
    valid_count = sum(1 for _p in PLANS.glob('*.json') if valid_plan(_p))
    say(f"Обновлено планов в хабе: **{valid_count}** · "
        f"задач всего: **{sum(d['всего'] for d in per.values())}**")

    say("")
    say(f"Открытых задач: {len(overdue) + len(today_rows) + len(week) + len(later) + len(backlog)}"
        f" · просрочено: **{len(overdue)}** · сделано: {done}")
    say("")
    say("| репозиторий | план обновлён | всего | просрочено | сделано |")
    say("|---|---|---|---|---|")
    for repo in sorted(per):
        d = per[repo]
        name = f"[{repo}]({base}/blob/main/plans/{repo}.json)" if base else repo
        say(f"| {name} | {fmt_updated(meta.get(repo, ''))} | "
            f"{d['всего']} | {d['просрочено']} | {d['сделано']} |")

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
                say(f"| {when_md(t)} | {repo} | {esc(t.get('title') or '')} | "
                    f"{STATUS_RU.get(t.get('status') or 'todo', '')} | "
                    f"{esc(t.get('why') or '')} | {link_md(repo, t)} |")
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
            say(f"| {when_md(t)} | {repo} | {esc(t.get('title') or '')} | "
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
                f"{link_md(repo, t)} |")
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
