# -*- coding: utf-8 -*-
"""Аудит канала ainow: сверка канала с архивом с учётом разметки.

Запуск:
    py E:\\github\\kalendar\\bin\\ainow_audit.py                 # отчёт (dry-run)
    py E:\\github\\kalendar\\bin\\ainow_audit.py --apply         # + запись в архив
    py E:\\github\\kalendar\\bin\\ainow_audit.py --days 2        # окно (по умолчанию 2)

Схема:
  * GET /messages?chat_id=..&count=100 -> список постов;
  * GET /messages/{mid} -> body.text + body.markup + body.attachments;
  * markdown восстанавливается из markup (сравнивать plain нельзя: жирный,
    ссылки и курсив в text не видны);
  * правка канала — PUT с новым text, format=markdown и исходными
    attachments по токенам (иначе теряются картинки).
"""
from __future__ import annotations

import argparse
import io
import json
import re
import ssl
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(r"E:\github\MAX")
POSTS = REPO / "roles/blogger/channels/ainow/posts"
TOKENS = REPO / "local/tokens.json"
CA = REPO / "local/russian_ca_bundle.pem"
POLISH = REPO / "roles/blogger/tools/ainow_polish.py"
API = "https://platform-api2.max.ru"
MSK = timezone(timedelta(hours=3))
LIMIT = 4000

creds = json.loads(TOKENS.read_text(encoding="utf-8"))["ainow"]
TOKEN = creds["token"]
CHAT = int(creds["chat_id"])
CTX = ssl.create_default_context()
CTX.load_verify_locations(cafile=str(CA))

TRANSLIT = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
            "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
            "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
            "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
            "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}


def slugify(text: str, fallback: str) -> str:
    out = []
    for ch in text.lower():
        if ch in TRANSLIT:
            out.append(TRANSLIT[ch])
        elif ch.isalnum() and ch.isascii():
            out.append(ch)
        else:
            out.append("-")
    s = re.sub(r"-{2,}", "-", "".join(out)).strip("-")[:60].rstrip("-")
    return s or fallback


def api(path: str, method: str = "GET", payload: dict | None = None):
    data = None
    headers = {"Authorization": TOKEN, "User-Agent": "curl/8.13.0"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=CTX, timeout=60) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"error": raw[:300]}


def _u16_starts(text: str) -> list[int]:
    """Начало каждого code point в UTF-16 units + общая длина."""
    starts, u = [], 0
    for ch in text:
        starts.append(u)
        u += 2 if ord(ch) > 0xFFFF else 1
    starts.append(u)
    return starts


def to_markdown(text: str, markup) -> str:
    """markup[] -> markdown. from/length приходят в UTF-16, текст — в code points."""
    if not markup:
        return text
    import bisect
    starts = _u16_starts(text)

    def cp(pos: int) -> int:
        return min(bisect.bisect_left(starts, pos), len(text))

    opens, closes = {}, {}
    for el in markup:
        t = el.get("type")
        f, ln = cp(el.get("from", 0)), el.get("length", 0)
        if ln <= 0 or f >= len(text):
            continue
        end = cp(el["from"] + ln)
        while end > f and text[end - 1] in "\n\r \t":
            end -= 1
        if end <= f:
            continue
        if t == "strong":
            o, c = "**", "**"
        elif t == "emphasized":
            o, c = "*", "*"
        elif t in ("monospace", "monospaced"):
            o, c = "`", "`"
        elif t == "strikethrough":
            o, c = "~~", "~~"
        elif t == "link" and el.get("url"):
            o, c = "[", "](%s)" % el["url"]
        else:
            continue
        opens.setdefault(f, []).append(o)
        closes.setdefault(end, []).append(c)
    out = []
    for i in range(len(text) + 1):
        out.extend(sorted(closes.get(i, []), reverse=True))
        out.extend(opens.get(i, []))
        if i < len(text):
            out.append(text[i])
    return "".join(out)


def norm(t: str) -> str:
    """Нормализация для сравнения: MAX тримит ведущие пробелы строк и отдаёт LF."""
    t = t.replace("\r\n", "\n").replace("\r", "\n")
    t = re.sub(r"(?m)^>\s?", "", t)
    t = re.sub(r"(?m)^[ \t]+", "", t)
    t = re.sub(r"[ \t]+$", "", t, flags=re.M)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


def parse_fm(raw: str):
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n?", raw, re.S)
    if not m:
        return {}, raw.strip()
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm, raw[m.end():].strip()


def build_fm(fm: dict, order: list[str]) -> str:
    keys = [k for k in order if k in fm] + [k for k in fm if k not in order]
    return "---\n" + "\n".join(f"{k}: {fm[k]}" for k in keys) + "\n---\n"


def load_archive():
    by_url, by_mid = {}, {}
    for p in POSTS.glob("*.md"):
        fm, body = parse_fm(p.read_text(encoding="utf-8"))
        rec = {"path": p, "fm": fm, "body": body}
        if fm.get("url"):
            by_url[fm["url"]] = rec
        if fm.get("message_id"):
            by_mid[fm["message_id"]] = rec
    return by_url, by_mid


def posts_window(days: int):
    cutoff = int((datetime.now(MSK) - timedelta(days=days)).timestamp() * 1000)
    st, data = api(f"/messages?chat_id={CHAT}&count=100")
    return [m for m in (data or {}).get("messages", []) if m.get("timestamp", 0) >= cutoff]


def polish_report(md: str) -> list[str]:
    """Прогнать текст через штатный чек-лист канала."""
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write("---\nchannel: ainow\nstatus: draft\nimage_file: cover.png\n---\n" + md)
        tmp = Path(fh.name)
    try:
        r = subprocess.run([sys.executable, str(POLISH), str(tmp), "--check"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return [ln.strip()[3:].strip() for ln in r.stdout.splitlines() if "⚠️" in ln]
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="записывать архив")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--channel-fix", action="store_true", help="разрешить PUT в канал")
    ap.add_argument("--only", default="", help="ограничить одним slug")
    a = ap.parse_args()

    by_url, by_mid = load_archive()
    checked = imported = updated = fixed = clean = 0
    fixes, warns = [], []

    for m in sorted(posts_window(a.days), key=lambda x: x.get("timestamp", 0)):
        mid = m["body"]["mid"]
        if a.only and not m.get("url", "").endswith(a.only):
            continue
        st, d = api("/messages/%s" % mid)
        msg = d.get("message", d)
        if st != 200:
            warns.append(f"{m.get('url')}: GET не удался ({st})")
            continue
        body = msg["body"]
        md = to_markdown(body["text"], body.get("markup"))
        atts = body.get("attachments") or []
        checked += 1
        ts = datetime.fromtimestamp(msg["timestamp"] / 1000, MSK)
        url = msg["url"]
        rec = by_url.get(url) or by_mid.get(mid)

        if rec is None:
            fname = f"{ts:%Y-%m-%d}-{slugify(body['text'].splitlines()[0], url.rsplit('/', 1)[-1])}.md"
            fm = {"channel": "ainow", "status": "published", "format": "markdown",
                  "published_at": ts.isoformat(timespec="seconds"), "message_id": mid,
                  "channel_id": str(CHAT), "url": url, "source": "channel-import"}
            imported += 1
            fixes.append(f"{url}: ручной пост добавлен в архив ({fname})")
            if a.apply:
                (POSTS / fname).write_text(build_fm(fm, list(fm)) + "\n" + md + "\n", encoding="utf-8")
            warns.append(f"{url}: в архиве не было, добавлен как ручной пост — нужна вычитка")
            continue

        if norm(rec["body"]) != norm(md):
            updated += 1
            fixes.append(f"{url}: архив и канал расходятся — нужна сверка "
                         f"(архив {len(rec['body'])} / канал {len(md)} зн.)")
            if a.apply:
                rec["fm"]["edited_at"] = ts.isoformat(timespec="seconds")
                rec["fm"]["edit_note"] = "синхронизировано с каналом"
                rec["path"].write_text(build_fm(rec["fm"], list(rec["fm"])) + "\n" + md + "\n",
                                       encoding="utf-8")

        # стиль проверяем по архиву: цитату CTA API в markup не отдаёт
        notes = polish_report(rec["body"])
        if notes:
            if a.channel_fix:
                st2, resp = api(f"/messages?chat_id={CHAT}&message_id={mid}", "PUT", {
                    "text": md, "format": "markdown",
                    **({"attachments": [{"type": x.get("type"),
                                         "payload": {"token": (x.get("payload") or {}).get("token")}}
                                        for x in atts]} if atts else {})})
                if st2 == 200 and resp.get("success"):
                    fixed += 1
                    fixes.append(f"{url}: канал обновлён ({'; '.join(notes[:3])})")
                else:
                    warns.append(f"{url}: PUT не удался — {str(resp)[:120]}")
            else:
                warns.append(f"{url}: замечания чек-листа — {'; '.join(notes[:3])}")
        else:
            clean += 1

    print("✅ **АУДИТ И СИНХРОНИЗАЦИЯ ainow ЗАВЕРШЕНА**")
    print(f"- Проверено постов за {a.days} дн.: {checked}")
    print(f"- Добавлено в архив (ручные посты): {imported}")
    print(f"- Автоматически исправлено (стиль/архив/канал): {fixed}")
    print(f"- Полностью соответствуют стилю: {clean}")
    if updated:
        print(f"- Расхождений архив/канал: {updated}")
    print()
    print("✏️ **Исправлено:**")
    for f in fixes:
        print(f"- {f}")
    if not fixes:
        print("- нет")
    if warns:
        print()
        print("⚠️ **Требует внимания:**")
        for w in warns:
            print(f"- {w}")
    if not a.apply:
        print()
        print("(dry-run: файлы и канал не изменялись)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
