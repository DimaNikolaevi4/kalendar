# -*- coding: utf-8 -*-
"""ainow_boot_gptoss.py — состояние ежедневного поста ainow на 12:00.

Только читает репозитории; единственное изменение — метка выполнения в
gitignored-каталоге E:\\github\\kalendar\\local\\.

Использование:
  py E:\\github\\kalendar\\bin\\ainow_boot_gptoss.py             # состояние и шаг
  py E:\\github\\kalendar\\bin\\ainow_boot_gptoss.py --mark      # отметить сделанным
  py E:\\github\\kalendar\\bin\\ainow_boot_gptoss.py --reset     # снять метку
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

MSK = timezone(timedelta(hours=3))
HUB = Path(__file__).resolve().parents[1]
MAX = HUB.parent / "MAX"
AINOW = MAX / "roles" / "blogger" / "channels" / "ainow"
WINDOW_START, WINDOW_END = 6, 11  # МСК: до слота 12:00 нужно время на вычитку


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
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def state(now: datetime) -> dict:
    today = now.date().isoformat()
    marker_path = HUB / "local" / f"ainow-boot-gptoss-{today}.done"
    posts = sorted((AINOW / "posts").glob(f"{today}-*.md"))
    post = posts[0] if posts else None
    fm = front_matter(post) if post else {}
    news = MAX / "local" / "gptoss-news" / f"{today}-news.json"
    raw = MAX / "local" / "gptoss-news" / f"{today}-raw.txt"

    if fm.get("status") == "published" and fm.get("message_id"):
        action, hint = "skip_published", "пост уже в канале; при необходимости --mark"
    elif marker_path.exists():
        action, hint = "skip_marker", "метка сегодняшнего прогона уже есть"
    elif not (WINDOW_START <= now.hour < WINDOW_END):
        action, hint = "skip_window", "вне окна 06:00–11:00 МСК — в 12:00 уже не успеть"
    elif post and fm.get("status") in ("approved", "draft"):
        action, hint = "proofread", "пост есть — прогнать четыре слоя и заменить файл"
    elif raw.exists():
        action, hint = "proofread", "сырой текст gpt-oss есть — вычитать и оформить файл"
    elif news.exists():
        action, hint = "call_gptoss", "новость выбрана — собрать промт и вызвать модель"
    else:
        action, hint = "build_post", "нет новости — выбрать самую обсуждаемую за сутки"

    return {
        "now_msk": now.isoformat(timespec="seconds"),
        "today": today,
        "window": [WINDOW_START, WINDOW_END],
        "in_window": WINDOW_START <= now.hour < WINDOW_END,
        "marker": str(marker_path) if marker_path.exists() else None,
        "post": str(post.relative_to(MAX)) if post else None,
        "post_status": fm.get("status"),
        "publish_time": fm.get("publish_time"),
        "message_id": fm.get("message_id"),
        "news": str(news.relative_to(MAX)) if news.exists() else None,
        "raw": str(raw.relative_to(MAX)) if raw.exists() else None,
        "action": action,
        "hint": hint,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--reset", action="store_true")
    args = ap.parse_args()
    now = datetime.now(MSK)
    marker_path = HUB / "local" / f"ainow-boot-gptoss-{now.date().isoformat()}.done"

    if args.reset:
        marker_path.unlink(missing_ok=True)
        print(json.dumps({"reset": str(marker_path), "exists": False}, ensure_ascii=False))
        return
    if args.mark:
        s = state(now)
        marker_path.parent.mkdir(parents=True, exist_ok=True)
        marker_path.write_text(json.dumps({
            "at": now.isoformat(timespec="seconds"),
            "post": s["post"], "message_id": s["message_id"],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"marked": str(marker_path), "state": s}, ensure_ascii=False, indent=2))
        return
    print(json.dumps(state(now), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
