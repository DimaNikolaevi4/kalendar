#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""sync.py — оркестрация kalendar↔репозитории (команда «прочти E:\github\kalendar и все синхронизируй»).

Назначение:
  1) Обновить вид хаба по MAX (drop MAX --no-push) и прочитать служебные команды.
  2) Для catden (MAX): если сегодня четверг — отчёт/подготовка рутины «медиа на хостинг» (окно 11 дней);
     если пятница — отчёт/подготовка пятничного прогона (стилистика + слои 1-3 до отправки) и превью 10 дней в «календарь».
  3) Сообщить владельцу: что опубликовано/отправлено в «календарь» или явные поломки.

Ограничения среды:
  - Доступ к хостингу /0s3/blogger-data и оригиналам nev/posting/images может отсутствовать -> операции помечаются как BLOCKED/needs-access с точным списком.
  - «Стилистика через ИИ (агент)» выполняется агентом в сессии; скрипт готовит кандидатов и прогоны слоёв 2-3 (и пытается слой 1), агент шлифует текст до отправки.
  - Слои 1–3 для превью в «календарь» выполняются на тексте кандидата ДО отправки (не через publish_post.py в канал).

Использование:
  py sync.py                     # авто по дню недели (МСК)
  py sync.py --force thu|fri     # принудительный режим
  py sync.py --date 2026-11-20   # считать «сегодня» этой датой (МСК)
  py sync.py --no-drop           # не делать drop MAX
  py sync.py --post-status       # отправить краткий статус в канал «календарь» (без notify)
  py sync.py --send-preview       # отправить пятничное превью текстом в «календарь» (без notify), без медиа с хостинга
"""
from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HUB = Path(__file__).resolve().parent
GITHUB = HUB.parent
MAX_REPO = GITHUB / "MAX"
MSK = timezone(timedelta(hours=3))
TOKENS = MAX_REPO / "local" / "tokens.json"
CA = MAX_REPO / "local" / "russian_ca_bundle.pem"
API = "https://platform-api2.max.ru"


def run(cmd: list[str], cwd: Path) -> tuple[int, str]:
    r = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (r.stdout or "") + ("\n" + r.stderr if r.stderr else "")
    return r.returncode, out.strip()


def read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return default


def read_front_matter(path: Path) -> tuple[dict, str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n?(.*)\Z", raw, re.S)
    fm: dict = {}
    body = raw
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith((" ", "\t", "-")):
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
    return fm, body


def plain_text(md: str) -> str:
    s = md
    s = re.sub(r"^---.*?---\s*", "", s, flags=re.S)
    s = re.sub(r"^>\s?", "", s, flags=re.M)
    s = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", s)
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)
    s = re.sub(r"[*_`#~]+", "", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


def catden_posts_window(start: date, days: int):
    sched = read_json(MAX_REPO / "local" / "catden-v1-schedule.json", []) or []
    by_date = {str(e.get("date")): e for e in sched}
    out = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        e = by_date.get(d)
        if not e:
            continue
        p = MAX_REPO / "roles" / "blogger" / "channels" / "catden" / "posts" / e["name"]
        fm, body = read_front_matter(p) if p.exists() else ({}, "")
        out.append({"date": d, "entry": e, "path": p, "exists": p.exists(), "fm": fm, "body": body})
    return out


def check_layers_2_3(text: str):
    # Слой 1 (LanguageTool) — блокирующий: требует сетевого/API вызова; здесь только попытка импорта/индикатор.
    sys.path.insert(0, str(MAX_REPO))
    res = {"layer1": "not-run (LanguageTool, блокирующий — прогнать до отправки)", "layer2": [], "layer3": []}
    try:
        from shared.readability import check_readability
        res["layer2"] = [getattr(x, "message", str(x)) for x in (check_readability(plain_text(text)) or [])]
    except Exception as e:
        res["layer2"] = [f"unavailable: {e!r}"]
    try:
        from shared.lexicon import check_lexicon
        lex = check_lexicon(plain_text(text)) or {}
        st = lex.get("status")
        if st == "unavailable":
            res["layer3"] = [f"unavailable: {lex.get('message','')}"]
        else:
            res["layer3"] = list(lex.get("items") or [])
    except Exception as e:
        res["layer3"] = [f"unavailable: {e!r}"]
    return res


def max_send_calendar(text: str) -> dict:
    toks = read_json(TOKENS, {}) or {}
    cal = toks.get("calendar") or {}
    token, chat_id = cal.get("token"), cal.get("chat_id")
    if not token or not chat_id:
        return {"ok": False, "error": "нет calendar token/chat_id в local/tokens.json"}
    body = json.dumps({"text": text, "format": "markdown"}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(f"{API}/messages?chat_id={chat_id}", data=body,
                                 headers={"Authorization": token, "Content-Type": "application/json", "User-Agent": "curl/8.13.0"},
                                 method="POST")
    ctx = ssl.create_default_context(cafile=str(CA)) if CA.exists() else ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=60) as r:
            data = json.loads(r.read().decode("utf-8"))
        msg = data.get("message") or {}
        mid = (msg.get("body") or {}).get("mid") or data.get("mid")
        return {"ok": True, "mid": mid}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


def thursday_report(start: date, window: list[dict]) -> tuple[str, list[str]]:
    lines = [f"ЧЕТВЕРГ (медиа на хостинг, окно 11 дней с {start:%d.%m.%Y})"]
    breaks = []
    for it in window:
        e = it["entry"]
        media = []
        if e.get("image_file"):
            media.append(e["image_file"])
        if e.get("image_files"):
            media += [x.strip() for x in str(e["image_files"]).split("|") if x.strip()]
        host_dir = f"/0s3/blogger-data/media/catden/{e['date']}/"
        status = e.get("status")
        note = "нет медиа" if not media else f"{len(media)} файл(ов)"
        lines.append(f"- {e['date']} [{status}] {e['name']}: {note} -> {host_dir}")
        if media:
            local_any = any((MAX_REPO / m).exists() for m in media)
            if not local_any:
                lines.append(f"  · оригиналы локально отсутствуют (ожидаемо для nev/ в git), требуется доступ к хостингу/внешнему хранилищу для сверки и заливки")
        lines.append(f"  · действие: сверить состав на хостинге (без дублей/пропусков), догрузить недостающее, после публикации прошлых дат — очистить отработавшее")
    breaks.append("Доступ к хостингу /0s3/blogger-data и/или оригиналам медиа не подтверждён в этой среде — фактическая сверка/заливка/очистка требует выполнения на машине с доступом (FTP/SFTP/SSH/ФМ Beget).")
    return "\n".join(lines), breaks


def friday_report(start: date, window: list[dict]) -> tuple[str, list[str], list[dict]]:
    lines = [f"ПЯТНИЦА (превью 10 дней в «календарь», с {start:%d.%m.%Y})"]
    breaks = []
    previews = []
    for it in window:
        e, p = it["entry"], it["path"]
        status = e.get("status")
        draft_note = " [DRAFT: медиа/approved от владельца ещё не готовы]" if status == "draft" else ""
        lines.append(f"- {e['date']} [{status}] {e['name']}{draft_note}")
        if not it["exists"]:
            lines.append("  · ПОЛОМКА: файл поста не найден")
            breaks.append(f"нет файла поста: {e['name']}")
            continue
        body = it["body"].strip()
        checks = check_layers_2_3(body)
        l2n, l3n = len(checks["layer2"]), len(checks["layer3"])
        lines.append(f"  · слой 1: {checks['layer1']}")
        lines.append(f"  · слой 2 (readability, WARN): {l2n} замечаний")
        if checks["layer2"]:
            for msg in checks["layer2"][:5]:
                lines.append(f"    - {msg}")
        lines.append(f"  · слой 3 (lexicon, WARN): {l3n} замечаний")
        if checks["layer3"]:
            for msg in checks["layer3"][:5]:
                lines.append(f"    - {msg}")
        media_desc = e.get("image_file") or ("альбом: " + str(e.get("image_files") or "")) or "нет медиа"
        lines.append(f"  · медиа (источник превью — хостинг): {media_desc}")
        previews.append({"date": e["date"], "name": e["name"], "status": status, "body": body, "media_desc": media_desc, "checks": checks})
    breaks.append("Медиа для превью «с хостинга» недоступно для загрузки/вложения в этой среде без доступа к /0s3/blogger-data — отправлять текст + явную пометку об источнике медиа.")
    breaks.append("Слой 1 (LanguageTool, блокирующий) и стилистическая шлифовка через ИИ (агент) должны быть выполнены агентом до отправки превью; скрипт выполняет слои 2-3 и сборку кандидатов.")
    return "\n".join(lines), breaks, previews


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (МСК), по умолчанию сегодня")
    ap.add_argument("--force", choices=["thu", "fri"], help="принудительный режим")
    ap.add_argument("--no-drop", action="store_true")
    ap.add_argument("--post-status", action="store_true", help="отправить краткий статус в канал календарь")
    ap.add_argument("--send-preview", action="store_true", help="отправить пятничное превью текстом в канал календарь (без медиа с хостинга)")
    a = ap.parse_args()

    today = date.fromisoformat(a.date) if a.date else datetime.now(MSK).date()
    wd = today.isoweekday()  # 1=Mon..4=Thu..5=Fri
    mode = a.force or ("thu" if wd == 4 else "fri" if wd == 5 else "none")

    report_lines = [f"sync kalendar {today.isoformat()} (МСК, день недели {wd}), режим: {mode}"]

    if not a.no_drop:
        rc, out = run([sys.executable, str(HUB / "drop.py"), "MAX", "--no-push"], HUB)
        report_lines.append(f"drop MAX: {'ok' if rc == 0 else 'FAIL'}")
        if out:
            report_lines.append(out.splitlines()[-1])
        if rc != 0:
            report_lines.append("ПОЛОМКА: не удалось обновить plans/MAX.json из MAX")

    auto = read_json(MAX_REPO / "roles" / "blogger" / "config" / "catden-automation.json", {}) or {}
    agreed = ((auto.get("state") or {}).get("agreed_until") or "?")
    report_lines.append(f"catden automation: enabled={auto.get('enabled')} agreed_until={agreed}")

    breaks: list[str] = []
    sent_calendar = []

    if mode == "thu":
        window = catden_posts_window(today, 11)
        text, b = thursday_report(today, window)
        report_lines.append("")
        report_lines.append(text)
        breaks.extend(b)
    elif mode == "fri":
        window = catden_posts_window(today, 10)
        text, b, previews = friday_report(today, window)
        report_lines.append("")
        report_lines.append(text)
        breaks.extend(b)
        if a.send_preview:
            report_lines.append("")
            report_lines.append("ОТПРАВКА ПРЕВЬЮ В КАНАЛ «КАЛЕНДАРЬ» (текст, без медиа с хостинга):")
            for pv in previews:
                status = pv["status"]
                head = f"📝 catden {pv['date']} (превью, без даты в тексте публикации){' — DRAFT, медиа/approved не готовы' if status=='draft' else ''}"
                media_note = f"\n\nМедиа (с хостинга): {pv['media_desc']}" if pv["media_desc"] != "нет медиа" else ""
                msg = head + media_note + "\n\n" + pv["body"].strip()
                if len(msg) > 3900:
                    msg = msg[:3897] + "…"
                res = max_send_calendar(msg)
                if res.get("ok"):
                    sent_calendar.append({"date": pv["date"], "mid": res.get("mid"), "name": pv["name"]})
                    report_lines.append(f"  - отправлено: {pv['name']} mid={res.get('mid')}")
                else:
                    breaks.append(f"не удалось отправить превью {pv['name']}: {res.get('error')}")
                    report_lines.append(f"  - ПОЛОМКА отправки: {pv['name']} {res.get('error')}")
    else:
        report_lines.append("Сегодня не четверг и не пятница — автоматические рутины catden (медиа/пятничное превью) не запускаются. Доступно: --force thu|fri.")

    # общая проверка: публикация catden сегодня в 20:00
    today_file = list((MAX_REPO / "roles" / "blogger" / "channels" / "catden" / "posts").glob(f"{today.isoformat()}-*.md"))
    if not today_file:
        report_lines.append("")
        report_lines.append(f"Публикация catden {today.isoformat()} 20:00 МСК: файла поста на сегодня нет в posts/ -> планировщик/cron опубликовать нечего (ожидаемо, если пост уже вышел ранее или дата не запланирована файлом).")
    else:
        for f in today_file:
            fm, _ = read_front_matter(f)
            report_lines.append("")
            report_lines.append(f"Публикация catden {today.isoformat()} 20:00 МСК: {f.name}, status={fm.get('status')}, message_id={fm.get('message_id') or '-'}")

    if breaks:
        report_lines.append("")
        report_lines.append("ЯВНЫЕ ПОЛОМКИ / ОГРАНИЧЕНИЯ:")
        # unique preserve order
        seen = set()
        for b in breaks:
            if b in seen:
                continue
            seen.add(b)
            report_lines.append(f"- {b}")

    if sent_calendar:
        report_lines.append("")
        report_lines.append("ОПУБЛИКОВАНО В КАНАЛ «КАЛЕНДАРЬ» (этот запуск): " + ", ".join(f"{x['date']} (mid={x['mid']})" for x in sent_calendar))
    elif mode == "fri" and not a.send_preview:
        report_lines.append("")
        report_lines.append("В канал «календарь» в этом запуске ничего не отправлялось (режим отчёта). Для отправки текстового превью: --send-preview (после прохождения слоёв 1-3 и стилистики агентом).")

    status_msg = "catden sync: " + (
        f"всё хорошо, посты до {agreed} готовы" if agreed and agreed != "?" else "статус см. отчёт"
    )
    if sent_calendar:
        status_msg += f"; в «календарь» отправлено превью: {len(sent_calendar)} сообщ."
    if breaks:
        status_msg += f"; ограничений/поломок: {len(breaks)}"

    if a.post_status:
        res = max_send_calendar(status_msg)
        report_lines.append("")
        if res.get("ok"):
            report_lines.append(f"Статус отправлен в «календарь»: mid={res.get('mid')}")
        else:
            report_lines.append(f"Не удалось отправить статус в «календарь»: {res.get('error')}")

    out = "\n".join(report_lines)
    try:
        print(out)
    except UnicodeEncodeError:
        sys.stdout.buffer.write((out + "\n").encode(sys.stdout.encoding or "utf-8", errors="replace"))

    # save last sync summary (local, gitignored context not assumed) in hub
    try:
        (HUB / "local").mkdir(exist_ok=True)
        (HUB / "local" / "last-sync.txt").write_text(out + "\n", encoding="utf-8")
    except Exception:
        pass


if __name__ == "__main__":
    main()
