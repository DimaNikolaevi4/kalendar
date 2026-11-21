# -*- coding: utf-8 -*-
"""Аудит канала ainow: сверка канала с архивом, импорт ручных постов,
проверка стиля и точечное исправление технических дефектов.

Запуск:
    py E:\\github\\kalendar\\bin\\ainow_audit.py               # только отчёт (dry-run)
    py E:\\github\\kalendar\\bin\\ainow_audit.py --apply       # + запись в архив и PUT в канал
    py E:\\github\\kalendar\\bin\\ainow_audit.py --days 2      # окно (по умолчанию 2 дня)

Принципы (важно):
  * Канал — источник истины по тексту: если пост правили вручную, архив
    обновляется из канала, а не наоборот.
  * Правка в канале (PUT) допускается только по объективным дефектам,
    которые видно в plain-тексте: литеральные `**`/`###`/`|`, длина > 4000,
    отсутствие CTA-строки. Стилистические придирки канал не трогают.
  * MAX API не отдаёт разметку (markup) и вложения в списке сообщений,
    поэтому наличие ссылок и картинок проверяется только по архиву.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO = Path(r"E:\github\MAX")
POSTS = REPO / "roles/blogger/channels/ainow/posts"
TOKENS = REPO / "local/tokens.json"
CA = REPO / "local/russian_ca_bundle.pem"
API = "https://platform-api2.max.ru"
MSK = timezone(timedelta(hours=3))
LIMIT = 4000

TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch", "ъ": "",
    "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}


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


def parse_fm(raw: str) -> tuple[dict, str, bool]:
    m = re.match(r"\A---\r?\n(.*?)\r?\n---\r?\n?", raw, re.S)
    if not m:
        return {}, raw.strip(), False
    fm = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t")):
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip('"')
    return fm, raw[m.end():].strip(), True


def build_fm(fm: dict, order: list[str]) -> str:
    keys = [k for k in order if k in fm] + [k for k in fm if k not in order]
    return "---\n" + "\n".join(f"{k}: {fm[k]}" for k in keys) + "\n---\n"


def plain(text: str) -> str:
    """Markdown -> plain, как его отдаёт MAX API."""
    t = re.sub(r"\[([^\]]+)\]\((?:[^)]+)\)", r"\1", text)
    t = t.replace("**", "").replace("__", "")
    t = re.sub(r"^>\s?", "", t, flags=re.M)
    t = t.replace("`", "")
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    return t.strip()


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
        return e.code, {"error": e.read().decode("utf-8")[:300]}


creds = json.loads(TOKENS.read_text(encoding="utf-8"))
TOKEN = creds["ainow"]["token"]
CHAT = int(creds["ainow"]["chat_id"])
CTX = ssl.create_default_context()
CTX.load_verify_locations(cafile=str(CA))


def load_archive() -> tuple[dict, dict]:
    by_url, by_mid = {}, {}
    for p in POSTS.glob("*.md"):
        fm, body, ok = parse_fm(p.read_text(encoding="utf-8"))
        rec = {"path": p, "fm": fm, "body": body, "has_fm": ok}
        if fm.get("url"):
            by_url[fm["url"]] = rec
        if fm.get("message_id"):
            by_mid[fm["message_id"]] = rec
    return by_url, by_mid


def channel_messages(days: int) -> list[dict]:
    cutoff = int((datetime.now(MSK) - timedelta(days=days)).timestamp() * 1000)
    out, marker = [], None
    for _ in range(5):
        path = f"/messages?chat_id={CHAT}&count=100"
        if marker:
            path += f"&from={marker}"
        st, data = api(path)
        msgs = (data or {}).get("messages") or []
        if st != 200 or not msgs:
            break
        for m in msgs:
            if m.get("timestamp", 0) >= cutoff:
                out.append(m)
        marker = msgs[-1].get("timestamp")
        if msgs[-1].get("timestamp", 0) < cutoff:
            break
    return out


def defects(text: str, has_archive: bool) -> list[str]:
    """Только объективные дефекты, видимые в plain-тексте канала."""
    out = []
    if len(text) > LIMIT:
        out.append(f"длина {len(text)} > {LIMIT}")
    for name, rx in (("`**`", r"\*\*"), ("`###`", r"(?m)^#{1,6} "), ("таблица `|`", r"(?m)^\|")):
        n = len(re.findall(rx, text))
        if n:
            out.append(f"литеральные {name}: {n}")
    if "Подписывайтесь" not in text:
        out.append("нет CTA-строки «Подписывайтесь»")
    if "?" not in text[-400:]:
        out.append("нет вопроса к читателю в конце")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="записывать архив и править канал")
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--channel-fix", action="store_true",
                    help="разрешить PUT в канал (по умолчанию только архив)")
    a = ap.parse_args()

    by_url, by_mid = load_archive()
    msgs = channel_messages(a.days)

    checked = imported = fixed = clean = 0
    fixes: list[str] = []
    warnings: list[str] = []

    for m in sorted(msgs, key=lambda x: x.get("timestamp", 0)):
        body = m.get("body") or {}
        mid = body.get("mid") or ""
        text = (body.get("text") or "").strip()
        url = m.get("url") or ""
        if not text or not mid:
            continue
        checked += 1
        ts = datetime.fromtimestamp(m["timestamp"] / 1000, MSK)
        rec = by_url.get(url) or by_mid.get(mid)
        d = defects(text, bool(rec))

        if rec is None:
            fname = f"{ts:%Y-%m-%d}-{slugify(text.split(chr(10))[0], url.rsplit('/', 1)[-1])}.md"
            path = POSTS / fname
            fm = {
                "channel": "ainow",
                "status": "published",
                "format": "markdown",
                "published_at": ts.isoformat(timespec="seconds"),
                "message_id": mid,
                "channel_id": str(CHAT),
                "url": url,
                "source": "channel-import",
            }
            imported += 1
            if a.apply:
                path.write_text(build_fm(fm, ["channel", "status", "format", "published_at",
                                              "message_id", "channel_id", "url", "source"])
                                + "\n" + text + "\n", encoding="utf-8")
            fixes.append(f"{url}: импортирован ручной пост в архив ({fname})")
            continue

        archived = plain(rec["body"])
        if archived != plain(text):
            rec["fm"]["owner_edited_at"] = ts.isoformat(timespec="seconds")
            rec["fm"]["sync_note"] = "текст канала отличается: канал — источник истины"
            if a.apply:
                rec["path"].write_text(
                    build_fm(rec["fm"], ["channel", "status", "format", "published_at",
                                         "message_id", "channel_id", "url",
                                         "owner_edited_at", "sync_note"]) + "\n" + text + "\n",
                    encoding="utf-8")
            fixed += 1
            fixes.append(f"{url}: архив обновлён из канала (правка владельца, канал не тронут)")
            continue

        if d:
            if a.apply and a.channel_fix:
                st, resp = api(f"/messages?chat_id={CHAT}&message_id={mid}", "PUT",
                               {"text": rec["body"], "format": "markdown"})
                if st == 200 and resp.get("success"):
                    fixed += 1
                    fixes.append(f"{url}: канал исправлен по эталону архива ({'; '.join(d)})")
                else:
                    warnings.append(f"{url}: PUT не удался — {str(resp)[:120]}")
            else:
                warnings.append(f"{url}: требует правки канала — {'; '.join(d)}")
            continue

        clean += 1

    print("✅ **АУДИТ И СИНХРОНИЗАЦИЯ ainow ЗАВЕРШЕНА**")
    print(f"- Проверено постов за {a.days} дн.: {checked}")
    print(f"- Добавлено в архив (ручные посты): {imported}")
    print(f"- Автоматически исправлено (стиль/архив/канал): {fixed}")
    print(f"- Полностью соответствуют стилю: {clean}")
    print()
    print("✏️ **Исправлено:**")
    for f in fixes:
        print(f"- {f}")
    if not fixes:
        print("- нет")
    if warnings:
        print()
        print("⚠️ **Требует внимания:**")
        for w in warnings:
            print(f"- {w}")
    if not a.apply:
        print()
        print("(dry-run: файлы и канал не изменялись; для записи — --apply)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
