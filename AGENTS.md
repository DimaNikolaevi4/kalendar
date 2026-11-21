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
5. Ручные правки владельца в канале — источник истины. Если текст в канале отличается
   от архивного, архив подтягивается из канала; канал архивом НЕ перезаписывается.
   Причина: MAX API отдаёт только plain-текст без разметки, поэтому «расхождение»
   почти всегда означает правку владельца, а не дефект.

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
py E:\github\kalendar\bin\ainow_audit.py --days 2 --apply
```

Скрипт `bin/ainow_audit.py` делает всё сам:

1. **Данные канала** — `GET /messages?chat_id=<ainow>&count=100` из MAX Bot API
   (токен: `E:\github\MAX\local\tokens.json`, ключ `ainow`; отдаёт `body.mid`,
   `body.text`, `url`, `timestamp`). Разметка и вложения API не отдаёт.
2. **Сверка с архивом** — по `url` (fallback: `message_id`) в
   `E:\github\MAX\roles\blogger\channels\ainow\posts\*.md`.
3. **Ручной пост без файла** — создаётся `.md` со `status: published`,
   `message_id`, `url`, `published_at`, `source: channel-import` и текстом из канала.
4. **Расхождение текста** — канал новее: архив перезаписывается текстом канала,
   ставится `owner_edited_at` и `sync_note`. Канал не трогается.
5. **Объективные дефекты** (только они дают право на PUT в канал): длина > 4000,
   литеральные `**` / `###` / `|` в тексте, нет CTA-строки «Подписывайтесь»,
   нет вопроса в конце. Исправление — PUT
   `/messages?chat_id=..&message_id=..` с `{"text": <архив>, "format": "markdown"}`:
   так сохраняются просмотры, ссылка и вложение.
6. **Отчёт** — ровно в формате ниже. Если правок нет, строка «нет».

### Что скрипт НЕ делает и почему

- Не переписывает канал, если он просто отличается от архива: это ручная правка владельца.
- Не судит о наличии ссылок, жирного и цитаты по данным API — они не отдаются;
  перелинковку и обложку проверяет `roles/blogger/tools/ainow_polish.py --check`
  по архивному файлу.
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

## Справочно: MAX Bot API (проверено 21.11.2026)

| Что | Как |
| :--- | :--- |
| База | `https://platform-api2.max.ru` |
| Авторизация | заголовок `Authorization: <token>` |
| Список сообщений | `GET /messages?chat_id=<id>&count=100` (+ `&from=<timestamp>` для страниц) |
| Идентификатор | `messages[].body.mid` (на верхнем уровне `mid` НЕТ) |
| Одно сообщение | `GET /messages/<mid>` — но `markup` и `attachments` приходят `null` |
| Правка | `PUT /messages?chat_id=<id>&message_id=<mid>`, тело `{"text": "...", "format": "markdown"}` |
| Адресация по slug | `GET /messages/<slug>` → 400; работает `GET /messages?chat_id=<id>&count=1&url=<slug>` |
| Чат ainow | `-76964086179165` |

---

## Безопасность коммитов (для календаря и MAX)

Перед каждым `git commit`: `git status --short` и `git diff --cached --stat`;
любая строка `D` без намерения — стоп. Добавлять конкретные файлы, не `git add -A`.
