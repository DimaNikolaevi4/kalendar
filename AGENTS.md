# ==========================================
# ТРИГГЕР: "смотри E:\github\kalendar"
# ==========================================
## ЖЁСТКИЕ ПРАВИЛА

1. Только PowerShell 5.1. Никакого Linux-синтаксиса (`&&`, `||`, `head`, `echo`).
2. Никакого внутреннего монолога и «сейчас проверю»: выдаётся только финальный отчёт.
3. Кириллица в консоли — артефакт отображения. Файлы читаются как UTF-8,
   перед выводом ставить `[Console]::OutputEncoding = [System.Text.Encoding]::UTF8`,
   иначе отчёт приходит кракозябрами.
4. ФАЗА 2 действует автоматически: архив обновляется, канал правится по объективным
   дефектам. Разрешения на это не спрашиваются.
5. Ручные правки владельца в канале — это сырой материал, а не эталон: их надо
   доводить до `style.md` и 4 слоёв вычитки, а не сохранять как есть.
   Источник истины для стиля — `style.md` + 4 слоя; источник фактов — канал.
6. Локальный Планировщик Windows **не используется**. Публикации ainow/catden/zabava/
   administrator идут серверным cron на хостинге Beget; na100 собирает и публикует агент
   при первом утреннем запуске по команде владельца (ФАЗА 3).

---

## ФАЗА 1. Ежедневный отчёт: синхронизация и задачи

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$profile = Get-Content "E:\github\kalendar\docs\ai-orchestration\machine_profile.json" | ConvertFrom-Json
$syncResults = @()
foreach ($repo in $profile.repos_to_sync) {
    $path = "E:\github\$repo"
    if (Test-Path $path) {
        Set-Location $path
        git stash | Out-Null
        git pull --rebase origin main | Out-Null
        $pullCode = $LASTEXITCODE
        git stash pop | Out-Null
        if ($pullCode -eq 0) { $syncResults += "${repo}: OK" } else { $syncResults += "${repo}: ОШИБКА" }
    } else {
        $syncResults += "${repo}: ОТСУТСТВУЕТ"
    }
}

$today = (Get-Date).ToString("yyyy-MM-dd")
$until = (Get-Date).AddDays(3).ToString("yyyy-MM-dd")
$tasks = @()
foreach ($repo in $profile.repos_to_sync) {
    $planFile = "E:\github\kalendar\plans\$repo.json"
    if (Test-Path $planFile) {
        $json = Get-Content $planFile -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($task in $json.tasks) {
            if ($task.when -ge $today -and $task.when -le $until -and
                $task.status -ne "done" -and $task.status -ne "backlog") {
                $ruStatus = switch ($task.status) {
                    "scheduled"   { "Запланировано" }
                    "todo"        { "К выполнению" }
                    "in-progress" { "В работе" }
                    default       { $task.status }
                }
                $tasks += [PSCustomObject]@{ Date = $task.when; Title = $task.title; Status = $ruStatus; Repo = $repo }
            }
        }
    }
}

$bad = @($syncResults | Where-Object { $_ -notmatch ': OK$' })
$syncReport = if ($bad.Count -eq 0) { "Все ОК" } else { ($bad -join ", ") }
Write-Output "✅ **СИНХРОНИЗАЦИЯ:** $syncReport"
Write-Output ""

foreach ($g in ($tasks | Group-Object Date | Sort-Object Name)) {
    $d = [datetime]::ParseExact($g.Name, "yyyy-MM-dd", $null)
    Write-Output "### 📅 $($g.Name) — $($d.ToString('dddd', [cultureinfo]'ru-RU'))"
    Write-Output "| Задача | Статус | Репозиторий |"
    Write-Output "| :--- | :--- | :--- |"
    foreach ($t in $g.Group) { Write-Output "| $($t.Title) | $($t.Status) | $($t.Repo) |" }
    Write-Output ""
}
```

---

## ФАЗА 2. Авто-аудит канала ainow за последние 2 дня

```powershell
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
py E:\github\kalendar\bin\ainow_audit.py --days 2 --apply --channel-fix
```

Скрипт `bin/ainow_audit.py` делает всё сам:

1. **Данные канала** — `GET /messages?chat_id=<ainow>&count=100`, затем
   `GET /messages/{mid}` для каждого поста: `body.text`, `body.markup`
   (strong / link / monospaced) и `body.attachments` с токенами вложений.
   Разметка восстанавливается в markdown — сравнивать plain-текст нельзя.
2. **Сверка с архивом** — по `url` (fallback: `message_id`) в
   `E:\github\MAX\roles\blogger\channels\ainow\posts\*.md`, с учётом разметки.
3. **Ручной пост без файла** — создаётся `.md` со `status: published`,
   `message_id`, `url`, `published_at` и текстом из канала.
4. **Расхождение текста** — показать diff «канал → версия по style.md» и ждать
   `ОК` владельца. Содержание берётся из канала, формат — из `style.md`.
5. **Правка канала** — `PUT /messages?chat_id=..&message_id=..` с `text`,
   `format: "markdown"` и **исходными `attachments` по токенам** (иначе
   потеряются картинки и видео). Просмотры и ссылка сохраняются.
6. **Отчёт** — ровно в формате ниже. Если правок нет, строка «нет».

### Что скрипт НЕ делает и почему

- Не правит канал без показанного diff и `ОК` владельца.
- Не публикует новые посты и не удаляет существующие.

### Дополнительная проверка архива после правок

```powershell
py E:\github\MAX\roles\blogger\tools\ainow_polish.py <файл-поста> --check
```

### Формат отчёта Фазы 2

```
✅ **АУДИТ И СИНХРОНИЗАЦИЯ ainow ЗАВЕРШЕНА**
- Проверено постов за 2 дня: N
- Добавлено в архив (ручные посты): N
- Автоматически исправлено (стиль/архив/канал): N
- Полностью соответствуют стилю: N

✏️ **Исправлено:**
- [ID/Ссылка]: [что изменено]
```

---

## ФАЗА 3. Утренний выпуск na100 (первое включение машины)

Условие: владелец первым утренним включением дал команду «смотри E:\github\kalendar»,
окно **06:00–12:00 МСК**, и метки `E:\github\kalendar\local\na100-morning-<дата>.done` нет.
Метка в gitignored `local/` обеспечивает идемпотентность: повторного выпуска в тот же день не будет.

1. Узнать состояние (скрипт только читает репозитории):

   ```powershell
   [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
   $env:PYTHONIOENCODING='utf-8'
   py E:\github\kalendar\bin\na100_morning.py
   ```

   `action`: `skip_published` / `skip_marker` / `skip_window` — публикация не нужна;
   `build_draft` → п. 2; `write_text` → п. 3; `make_cover` → п. 4; `publish_ready` → п. 5.

2. Черновик (если нет черновика и поста на сегодня):

   ```powershell
   cd E:\github\MAX
   py roles\blogger\tools\digest_build.py --channel na100
   ```

3. Текст выпуска пишет **агент сам** по `roles/blogger/channels/na100/style.md` и черновику
   `digests/<дата>-draft.json`: 5 новостей (1 РФ + 1 Китай + 3 мира; при пустом Китае —
   1 РФ + 4 мира с пометкой), хук 40–60 знаков, у каждого пункта «Что случилось» и
   «Почему важно», ≥2 цифр в подзаголовках, итог со связкой, CTA из `cta-phrases.json`
   без повторов, атрибуция иллюстрации, длина 3400–3700 (жёстко ≤4000).
   Файл `posts/<дата>-pyaterka-tehnologij.md` со `status: approved` и без `image_file`.
   Проверка: `py roles\blogger\tools\digest_polish.py <пост> --check`.

4. Обложка: повторный `digest_build.py --channel na100` сам дописывает `image_file` и
   коммитит (скрипт стандарта — `digest_cover_photo.py`, фон из пула).

5. Публикация:

   ```powershell
   $env:MAX_HTTP='python'
   $env:MAX_CA_CERT='local/russian_ca_bundle.pem'
   py roles\blogger\tools\publish_scheduled.py --channel na100 --limit 1
   ```

   - LanguageTool блокирует по ложным срабатываниям на имена/техно-сленг — добавить корни
     в `roles/blogger/channels/na100/spell-ignore.json`, закоммитить и повторить.
   - `local/publish-scheduled.lock` после прерванного запуска (PID в процессах отсутствует)
     удалить и повторить.
   - После успеха: проверить `GET /messages?chat_id=<na100>&count=3` и `status: published`
     в файле поста; закоммитить и запушить сопутствующие `plan.json`,
     `lexicon-calibration.jsonl`, `cta-phrases.json` — **поимённо, не `git add -A`**.
   - Обновить хаб: `py E:\github\kalendar\build_plan.py --push`.

6. Метка: `py E:\github\kalendar\bin\na100_morning.py --mark`.

### Формат отчёта ФАзы 3

```
✅ **NA100 ЗАВЕРШЕН**
- Выпуск: <ссылка>
- Новости: N, обложка: есть
- План обновлён: да/нет
```

Если `action` не требует публикации — одной строкой: «na100: <причина>, публикация не нужна».

---

## ФАЗА 3а. Дневной пост ainow на 12:00 (первое включение машины)

Условие: владелец первым включением дал команду «смотри E:\github\kalendar»,
окно **06:00–11:00 МСК**, метки `E:\github\kalendar\local\ainow-boot-gptoss-<дата>.done` нет.
Служебная задача — `orch-ainow-boot-gptoss-1200` (`source: kalendar`) в `MAX/plan.json`;
параметры — `E:\github\MAX\roles\blogger\config\ainow-boot-gptoss-automation.json`.
Полный протокол — `docs\ai-orchestration\prompts\05-ainow-daily-12.md`.

1. Состояние: `py E:\github\kalendar\bin\ainow_boot_gptoss.py`
   (`skip_published` / `skip_marker` / `skip_window` / `build_post` / `call_gptoss` / `proofread`).
2. Выбрать самую обсуждаемую IT-новость за сутки (Habr top + RSS из
   `MAX/roles/blogger/config/techdigest_feeds.json`), записать проверенные факты в
   gitignored `MAX/local/gptoss-news/<дата>-news.json`.
3. Собрать промт по `MAX/roles/blogger/channels/ainow/gptoss-news-prompt.md` и вызвать
   `py E:\github\MAX\roles\blogger\tools\gptoss_news_post.py --news <news.json> --out <raw.txt>`
   (модель `@cf/openai/gpt-oss-120b`; токен — только из gitignored `E:\github\ai.txt`).
4. Прогнать **четыре слоя вычитки** (§5а+ MAX/AGENTS.md): LanguageTool блокирует,
   читаемость и humanizer — WARN, затем финальная вычитка и `ainow_polish.py --check`.
   По прямому распоряжению владельца 25.11 **«ок» не требуется** — только для этой задачи;
   если блокер нельзя снять без искажения фактов — стоп, отчёт, метку не ставить.
5. Обложка ≥1,50, залить на хостинг `/0s3/public_html/blogger/covers/ainow/<дата>-cover.png`
   (FTP-доступ — из gitignored локального файла). Пост
   `MAX/roles/blogger/channels/ainow/posts/<дата>-<slug>.md` со `status: approved`,
   `publish_time: 12:00`, `format_core: 1`, `tail_mode: free` (творческая зона
   §0.11: первый абзац и произвольный порядок хвоста); коммит поимённо и пуш в GitHub `main`
   (хостинг-крон читает GitHub API, без git pull и без слоёв вычитки).
6. Метка: `py E:\github\kalendar\bin\ainow_boot_gptoss.py --mark`.
7. Отчёт в рабочем чате; в «календарь» — только план-запись
   «<дата> — 12:00 — <заголовок>: пост готов, залит на хостинг», без `notify`.

---

## Справочно: MAX Bot API (проверено 21.11.2026)

| Что | Как |
| :--- | :--- |
| База | `https://platform-api2.max.ru` |
| Авторизация | заголовок `Authorization: <token>` |
| Список сообщений | `GET /messages?chat_id=<id>&count=100` (+ `&from=<timestamp>` для страниц) |
| Идентификатор | `messages[].body.mid` (на верхнем уровне `mid` НЕТ) |
| Одно сообщение | `GET /messages/<mid>` — `body.text`, `body.markup`, `body.attachments` |
| Разметка | `body.markup[]`: `from`, `length`, `type`; `length` включает хвостовые `\n\n` |
| Вложения | `body.attachments[]`: `{type, payload:{token, photo_id, url}}` |
| Правка | `PUT /messages?chat_id=<id>&message_id=<mid>`, тело `{"text": ..., "format": "markdown", "attachments": [{"type": ..., "payload": {"token": ...}}]}` |
| Адресация по slug | `GET /messages/<slug>` → 400; работает `GET /messages?chat_id=<id>&count=1&url=<slug>` |
| Чат ainow | `-76964086179165` |

---

## Безопасность коммитов (для календаря и MAX)

Перед каждым `git commit`: `git status --short` и `git diff --cached --stat`;
любая строка `D` без намерения — стоп. Добавлять конкретные файлы, не `git add -A`.
