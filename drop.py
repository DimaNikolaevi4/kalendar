# -*- coding: utf-8 -*-
"""drop.py <REPO> — «скинуть» план репозитория в хаб planner.

Модель: источник истины — `E:\github\<REPO>\plan.json`, он хранится в git
самого репозитория. Этот скрипт копирует его в `plans/<REPO>.json` хаба,
коммитит и пушит. Так в хабе видно, кто и когда обновил план.

Использование:
  python E:\\github\\planner\\drop.py <REPO> [--file <путь>] [--no-push]

Валидация: JSON разбор, уникальность id, допустимые статусы, формат дат.
"""
from __future__ import annotations

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


def git(*args: str, cwd: Path = HUB) -> str:
    r = subprocess.run(["git", *args], cwd=str(cwd), capture_output=True,
                       text=True, encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die(f"git {' '.join(args[:2])}: {(r.stderr or r.stdout).strip()[-300:]}")
    return r.stdout


def check_date(value: str, task_id: str) -> None:
    try:
        date.fromisoformat(value)
    except ValueError:
        die(f"задача {task_id!r}: when={value!r} не дата YYYY-MM-DD")


def main() -> None:
    args = sys.argv[1:]
    if not args:
        die("usage: drop.py <REPO> [--file <path>] [--no-push]")
    repo = args[0].strip("\\/ ")
    if not repo or "/" in repo or "\\" in repo:
        die(f"имя репозитория кривое: {repo!r}")
    push = "--no-push" not in args

    src = GITHUB / repo / "plan.json"
    if "--file" in args:
        i = args.index("--file")
        src = Path(args[i + 1])
    if not src.is_file():
        die(f"нет файла источника: {src}")

    try:
        data = json.loads(src.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"JSON невалиден: {e}")

    tasks = data.get("tasks") or []
    ids = [t.get("id") for t in tasks]
    if len(ids) != len(set(ids)):
        die("id задач не уникальны")
    for t in tasks:
        tid = t.get("id") or "<без id>"
        if t.get("status") not in STATUSES:
            die(f"задача {tid!r}: статус {t.get('status')!r} "
                f"не из {sorted(STATUSES)}")
        if not t.get("title"):
            die(f"задача {tid!r}: нет title")
        if t.get("when"):
            check_date(t["when"], tid)

    out = {
        "repo": repo,
        "updated_at": datetime.now(MSK).isoformat(timespec="seconds"),
        "source_file": str(src),
        "tasks": tasks,
    }
    dest = HUB / "plans" / f"{repo}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    before = dest.read_text(encoding="utf-8") if dest.exists() else ""
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    if dest.read_text(encoding="utf-8") == before:
        print(f"DROP {repo}: без изменений (задач {len(tasks)})")
        return

    rel = str(dest.relative_to(HUB))
    git("add", rel)
    now = datetime.now(MSK).strftime("%d.%m.%Y %H:%M")
    git("commit", "-m", f"drop {repo}: {len(tasks)} задач ({now})")
    if push:
        git("push", "origin", "main")
    print(f"DROP {repo}: задач {len(tasks)} -> plans/{repo}.json"
          + (", коммит+пуш" if push else ", коммит (без пуша)"))


if __name__ == "__main__":
    main()
