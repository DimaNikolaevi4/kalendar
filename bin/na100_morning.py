# -*- coding: utf-8 -*-
"""na100_morning.py — состояние утреннего выпуска na100 для оркестратора kalendar.

Только читает репозитории; единственное изменение — метка выполнения в
gitignored-каталоге E:\\github\\kalendar\\local\\.

Использование:
  py E:\\github\\kalendar\\bin\\na100_morning.py            # состояние и следующий шаг
  py E:\\github\\kalendar\\bin\\na100_morning.py --mark     # отметить выпуск сделанным
  py E:\\github\\kalendar\\bin\\na100_morning.py --reset    # снять метку (повторный прогон)
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

MSK = timezone(timedelta(hours=3))
HUB = Path(__file__).resolve().parents[1]
MAX = HUB.parent / "MAX"
NA100 = MAX / "roles" / "blogger" / "channels" / "na100"
WINDOW_START, WINDOW_END = 6, 12  # МСК: утреннее окно первого включения машины


def front_matter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        return {}
    out = {}
    for line in text[3:end].splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def state(now: datetime) -> dict:
    today = now.date().isoformat()
    marker_path = HUB / "local" / f"na100-morning-{today}.done"
    posts = sorted((NA100 / "posts").glob(f"{today}-*.md"))
    post = posts[0] if posts else None
    fm = front_matter(post) if post else {}
    draft = NA100 / "digests" / f"{today}-draft.json"
    plan = json.loads((MAX / "plan.json").read_text(encoding="utf-8"))
    task = next((t for t in plan.get("tasks") or []
                 if t.get("id") == f"max-{today}-pyaterka-tehnologij"), None)

    if fm.get("status") == "published" and fm.get("message_id"):
        action, hint = "skip_published", "выпуск уже в канале; при необходимости --mark"
    elif marker_path.exists():
        action, hint = "skip_marker", "метка сегодняшнего утреннего прогона уже есть"
    elif not (WINDOW_START <= now.hour < WINDOW_END):
        action, hint = "skip_window", "вне утреннего окна 06:00–12:00 МСК"
    elif post and fm.get("status") == "approved" and fm.get("image_file"):
        action, hint = "publish_ready", "пост готов с обложкой — публиковать"
    elif post and fm.get("status") == "approved":
        action, hint = "make_cover", "текст есть — прогнать digest_build для обложки"
    elif draft.exists():
        action, hint = "write_text", "черновик есть — написать текст по style.md"
    else:
        action, hint = "build_draft", "нет черновика — прогнать digest_build"

    return {
        "now_msk": now.isoformat(timespec="seconds"),
        "today": today,
        "morning_window": WINDOW_START <= now.hour < WINDOW_END,
        "marker": str(marker_path) if marker_path.exists() else None,
        "post": str(post.relative_to(MAX)) if post else None,
        "post_status": fm.get("status"),
        "message_id": fm.get("message_id"),
        "url": fm.get("url"),
        "draft": str(draft.relative_to(MAX)) if draft.exists() else None,
        "plan_task_status": task.get("status") if task else None,
        "action": action,
        "hint": hint,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    now = datetime.now(MSK)
    today = now.date().isoformat()
    marker_path = HUB / "local" / f"na100-morning-{today}.done"

    if args.reset:
        marker_path.unlink(missing_ok=True)
        print(json.dumps({"reset": str(marker_path), "exists": False}, ensure_ascii=False))
        return
    if args.mark:
        s = state(now)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps({
            "at": now.isoformat(timespec="seconds"),
            "post": s["post"], "url": s["url"], "message_id": s["message_id"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"marked": str(marker_path), "state": s}, ensure_ascii=False, indent=2))
        return
    print(json.dumps(state(now), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
