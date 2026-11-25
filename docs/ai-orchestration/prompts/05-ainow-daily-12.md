# Ежедневный пост ainow на 12:00: новость → gpt-oss → четыре слоя → хостинг

Служебная задача оркестрации `kalendar` ↔ `MAX`. Прямое распоряжение владельца
25.11.2026: этот дневной пост **ставится на 12:00 без отдельного «ок»** — агент
сам прогоняет четыре слоя вычитки и размещает пост. Исключение из общего правила
«черновик показывается человеку → «ок» → approved» действует только для этой
задачи; все остальные посты seрии по-прежнему идут через согласование.

## Триггер и идемпотентность

- Первое включение машины, владелец дал команду «смотри E:\github\kalendar».
- Окно **06:00–11:00 МСК** (до слота 12:00 должно оставаться время на вычитку).
- Метка `E:\github\kalendar\local\ainow-boot-gptoss-<дата>.done` отсутствует
  (каталог gitignored). Повторного прогона в тот же день не будет.

## Шаг 0. Состояние

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = 'utf-8'
py E:\github\kalendar\bin\ainow_boot_gptoss.py
```

`action`: `skip_published` / `skip_marker` / `skip_window` — ничего не делаем;
`build_post` — выполняем шаги 1–7.

## Шаг 1. Самая обсуждаемая IT-новость за сутки

Источники — `E:\github\MAX\roles\blogger\config\techdigest_feeds.json` (Habr,
TechCrunch, The Verge, Opennet, CNews и др.) плюс страница `https://habr.com/ru/top/`
для числа комментариев. Запрещены источники из `image_sources.json → denied`
(Reuters, AP, Getty, Shutterstock и т.п.).

Выбрать **одну** новость с максимальным сигналом обсуждения за последние 24 часа.
Если измерить обсуждаемость не удалось — верхняя запись Habr top по комментариям;
fallback — верхняя запись по скорингу `digest_build.py` за сутки.

Результат записать в gitignored `E:\github\MAX\local\gptoss-news\<дата>-news.json`:

```json
{
  "title": "...", "url": "...", "source": "...", "published_at": "...",
  "discussion": {"comments": 0, "where": "Habr top"},
  "facts": ["...", "...", "..."],
  "context_links": [
    {"anchor": "...", "url": "https://max.ru/channel_ainow/..."}
  ]
}
```

Только проверенные факты: заголовок, дата, цифры и цитаты из самого источника.
Нельзя дописывать «по данным неназванных источников» и выдуманные подробности.

## Шаг 2. Промт для gpt-oss

Шаблон: `E:\github\MAX\roles\blogger\channels\ainow\gptoss-news-prompt.md`.
Взять текст `SYSTEM:` как есть, в блок `USER:` подставить:
- `title`, `url`, `source`, `published_at`, `facts`, `discussion` из шага 1;
- 1–2 внутренние ссылки `context_links` на уже опубликованные посты ainow;
- дату проверки и текущий формат хвоста по §0 (CTA-цитата со ссылкой,
  призыв к реакциям, финальный вопрос).

Жанр зафиксирован владельцем: **очерк «есть мнение»** — не инструкция и не
дайджест. Это рабочий жанр дневного поста (прецедент — пост 24.11 12:00
«Ставки перед IPO: что читать в чужих оценках»).

## Шаг 3. Вызов модели

```powershell
cd E:\github\MAX
py roles\blogger\tools\gptoss_news_post.py --news local\gptoss-news\<дата>-news.json --out local\gptoss-news\<дата>-raw.txt
```

Модель: `@cf/openai/gpt-oss-120b`, Cloudflare Workers AI. Токен читается **только**
из gitignored `E:\github\ai.txt` / `local\cf_config.json`; в git, посты и отчёты
он не попадает ни при каких обстоятельствах. Сырой вывод сохраняется в
gitignored `local/`, служебный блок `---DECISION---` отделяется от текста поста.

## Шаг 4. Четыре слоя вычитки (агент)

1. **Язык — блокирует.** `py roles\blogger\tools\check_post.py --channel ainow <файл> --core`;
   LanguageTool режется на куски ≤900 знаков. Ложные срабатывания на сленг/имена —
   корнями в `roles/blogger/channels/ainow/spell-ignore.json`.
2. **Читаемость — WARN.** `shared/readability.py`: длинные предложения, повторы,
   канцелярит, пунктуация.
3. **Штампы — WARN.** `shared/lexicon.py` (`ru-humanizer==3.32.0`),
   исключения — `ainow/lexicon-ignore.json`.
4. **Финальная вычитка.** Сверка фактов с шагом 1, заголовок ≤60 без точки,
   воздух, жирных в абзацах ≤6, перелинковка 1–2 внутри абзаца. Первый абзац и
   хвост — «творческая зона» §0.11 MAX/AGENTS.md: в хвосте можно взять любые
   два-три элемента из «подписка / реакция / вопрос» в любом порядке, каждый —
   отдельная строка с пустой строкой между. В front matter ставится
   `tail_mode: free`.
   Дополнительно: `py roles\blogger\tools\ainow_polish.py <файл> --check`.

**Стоп-правило:** если блокер слоя 1 нельзя убрать без искажения факта или без
разрушения очерка — пост **не ставится** на 12:00; отчёт в календарь, метка не
проставляется, агент ждёт решения владельца. WARN-слои публикацию не останавливают.

## Шаг 5. Обложка

Одна картинка 16:9 или шире (минимум 1,50), проверка
`py roles\blogger\tools\media_aspect.py <файл>` — код 0. Источник: архив
`local/images/ainow/` через `pick_image.py --channel ainow` или изображение со
свободной лицензией/официальная символика. Генерация без прямого указания
запрещена. Нет подходящего кадра — стоп по §5д, не подставлять заглушку.
Атрибуция CC BY/CC BY-SA — в `media_note` front matter.

## Шаг 6. Размещение и хостинг

Файл `E:\github\MAX\roles\blogger\channels\ainow\posts\<дата>-<slug>.md`:

```yaml
---
channel: ainow
status: approved
format: markdown
notify: true
format_core: 1
tail_mode: free
publish_time: 12:00
model: cloudflare/@cf/openai/gpt-oss-120b
topic: <заголовок новости>
image_file: <путь>
---
```

Далее — коммит **именованными файлами** и пуш в GitHub `main` (чек-лист
`kalendar/README.md` «Безопасность коммитов» обязателен). Хостинг **не делает
git pull**: `deploy/post_cron.php` читает список постов через GitHub API и raw-файл
из ветки `main`, поэтому пуш обязателен. Публикация в 12:00 МСК идёт только при
`status: approved`, `publish_time: 12:00` и `gate_time = 12:00`.

Обложку надо залить на хостинг отдельно: `/0s3/public_html/blogger/covers/ainow/<дата>-cover.png`
(публичная URL `https://0s3.ru/blogger/covers/ainow/<дата>-cover.png`). Без кадра
на хостинге крон придержит пост. FTP-доступ и пароль — только из gitignored
локального файла, в репозиторий не попадают; образец кода — `MAX/local/` (скрипты
заливки на Beget). Важно: PHP-крон **не прогоняет четыре слоя вычитки** — это
дело агента на шаге 4, до пуша.

CTA-фразу записать в `ainow/cta-phrases.json`, чек-лист серии обновить.

## Шаг 7. Метка и отчёт

```powershell
py E:\github\kalendar\bin\ainow_boot_gptoss.py --mark
```

В рабочем чате — короткий отчёт: новость, заголовок поста, баллы/замечания
слоёв 1–3, путь файла, подтверждение пуша. В канал «календарь» — только
план-запись вида «<дата> — 12:00 — <заголовок>: пост готов, залит на хостинг»
(без notify, по §2г AGENTS.md MAX).
