#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""task.py — оркестратор «Календаря»: записать задачу в репозиторий.

Календарь — не только сбор данных, но и оркестратор: выяснили задачу и срок —
записываем ОДНОЙ командой и в план репозитория (E:\github\<REPO>\plan.json,
коммит+пуш), и в хаб (drop без пуша — попадёт в PLAN.md на утренней сборке).
Источник истины по-прежнему plan.json в репо; хаб — витрина.

Использование:
  py task.py <REPO> add    --title "Что сделать" [--when ГГГГ-ММ-ДД]
           [--status todo] [--why "зачем"] [--link путь] [--source agent]
           [--id свой-идентификатор]
  py task.py <REPO> status <id> --set todo|in-progress|done|skipped|backlog|scheduled
           [--when ГГГГ-ММ-ДД]   # сменить статус/дату существующей задачи
  py task.py <REPO> remove <id>
  py task.py <REPO> list

Опции: --no-push (не пушить репо), --no-drop (не скидывать в хаб).
Если id не задан — генерируется из даты и хеша заголовка; повторное add с тем
же заголовком обновляет существующую задачу, а не дублирует её.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent
GITHUB = HUB.parent
MSK = timezone(timedelta(hours=3))
STATUSES = {"scheduled", "todo", "in-progress", "done", "skipped", "backlog"}


def die(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def git(args: list[str], cwd: Path) -> None:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die(f"git {' '.join(args[:2])} @ {cwd.name}: "
            f"{(r.stderr or r.stdout).strip()[-300:]}")


def git_out(args: list[str], cwd: Path) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                          text=True, encoding="utf-8",
                          errors="replace").stdout.strip()


def repo_dir(repo: str) -> Path:
    p = GITHUB / repo
    if not (p / ".git").is_dir():
        die(f"нет репозитория: {p}")
    return p


def slug_id(title: str, when: str | None) -> str:
    h = hashlib.md5(title.encode("utf-8")).hexdigest()[:6]
    d = when or datetime.now(MSK).strftime("%Y-%m-%d")
    return f"t{d.replace('-', '')}-{h}"


def load_plan(repo_path: Path) -> dict:
    f = repo_path / "plan.json"
    if f.is_file():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            die(f"{f}: JSON невалиден: {e}")
    return {"tasks": []}


def save_plan(repo_path: Path, plan: dict) -> None:
    plan.setdefault("tasks", [])
    f = repo_path / "plan.json"
    f.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n",
                 encoding="utf-8")


def drop(repo: str) -> None:
    r = subprocess.run([sys.executable, str(HUB / "drop.py"), repo,
                        "--no-push"], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    line = ((r.stdout or "").strip().splitlines() or [""])[-1]
    print(f"  {line if r.returncode == 0 else 'drop FAIL: ' + line}")


def main() -> None:
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument("repo")
    ap.add_argument("command", choices=["add", "status", "remove", "list"])
    ap.add_argument("task_id", nargs="?", default="")
    ap.add_argument("--id", dest="forced_id", default="")
    ap.add_argument("--title", default="")
    ap.add_argument("--when", default=None)
    ap.add_argument("--status", default=None)
    ap.add_argument("--set", dest="set_status", default=None)
    ap.add_argument("--why", default=None)
    ap.add_argument("--link", default=None)
    ap.add_argument("--source", default="agent")
    ap.add_argument("--no-push", action="store_true")
    ap.add_argument("--no-drop", action="store_true")
    a = ap.parse_args()

    now = datetime.now(MSK)
    repo_path = repo_dir(a.repo)
    plan = load_plan(repo_path)
    tasks = plan.get("tasks") or []

    if a.command == "list":
        if not tasks:
            print(f"{a.repo}: задач нет (plan.json создастся первым add)")
            return
        for t in tasks:
            when = t.get("when") or "—"
            print(f"{when} | {t.get('status') or '?'} | {t.get('id')} | "
                  f"{t.get('title')}")
        return

    if a.command == "add":
        if not a.title:
            die("add требует --title")
        tid = a.forced_id or slug_id(a.title, a.when)
        if not a.title.strip():
            die("пустой заголовок")
        existing = next((t for t in tasks if t.get("id") == tid), None)
        entry = {"id": tid, "title": a.title.strip(),
                 "when": a.when, "time": None,
                 "status": a.status or "todo",
                 "why": a.why or "", "link": a.link or "",
                 "source": a.source}
        if a.status and a.status not in STATUSES:
            die(f"статус {a.status!r} не из {sorted(STATUSES)}")
        if a.when:
            try:
                date.fromisoformat(a.when)
            except ValueError:
                die(f"when={a.when!r} не дата ГГГГ-ММ-ДД")
        if existing:
            if a.status is None:
                entry["status"] = existing.get("status") or "todo"
            tasks[tasks.index(existing)] = entry
            verb = "обновлена"
        else:
            tasks.append(entry)
            verb = "добавлена"
    elif a.command == "status":
        if not a.task_id:
            die("status требует <id>")
        if not a.set_status:
            die("status требует --set <статус>")
        target = next((t for t in tasks if t.get("id") == a.task_id), None)
        if not target:
            die(f"задача {a.task_id!r} не найдена (task.py {a.repo} list)")
        if a.set_status not in STATUSES:
            die(f"статус {a.set_status!r} не из {sorted(STATUSES)}")
        target["status"] = a.set_status
        if a.when is not None:
            target["when"] = a.when or None
        verb = f"статус -> {a.set_status}"
        tid = a.task_id
    else:  # remove
        if not a.task_id:
            die("remove требует <id>")
        before = len(tasks)
        tasks = [t for t in tasks if t.get("id") != a.task_id]
        if len(tasks) == before:
            die(f"задача {a.task_id!r} не найдена (task.py {a.repo} list)")
        plan["tasks"] = tasks
        verb = "удалена"
        tid = a.task_id

    if a.command != "remove":
        plan["tasks"] = tasks
    save_plan(repo_path, plan)

    if a.command != "list":
        git(["add", "plan.json"], repo_path)
        ts = now.strftime("%d.%m.%Y %H:%M")
        git(["commit", "-m",
             f"plan: задача {a.command} [{tid}] {a.status or ''} ({ts})"],
            repo_path)
        if not a.no_push:
            git(["push", "origin",
                 git_out(["rev-parse", "--abbrev-ref", "HEAD"], repo_path)],
                repo_path)
            pushed = ", пуш"
        else:
            pushed = ", без пуша"
        if not a.no_drop:
            print(f"{a.repo}: задача «{a.command}» — {verb}{pushed};")
            drop(a.repo)
        else:
            print(f"{a.repo}: задача «{a.command}» — {verb}{pushed}, "
                  "без drop")


if __name__ == "__main__":
    main()
