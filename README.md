# Календарь — общий план по всем репозиториям `E:\github`

Один файл `PLAN.md` отвечает на вопросы «что нужно делать, когда и зачем»
по всем проектам. Раньше его собирала задача Windows «kalendar build plan»
ежедневно в **07:25 МСК**; на текущей машине локальный планировщик отключён,
поэтому сборку (`build_plan.py --push`) запускает агент по команде владельца —
см. `AGENTS.md`, ФАЗА 1 и ФАЗА 3.

## Модель: календарь = оркестратор

1. **Источник истины** — `plan.json` в корне каждого репозитория
   (хранится в git самого репо, правится автоматикой или агентом/владельцем).
   Задачи не живут отдельно в календаре — они записаны в самих репо.
2. **Запись задачи (обратный ход)** — `task.py`:
   `py E:\github\kalendar\task.py <REPO> add --title "..." --when 2026-11-18`
   — пишет задачу в `plan.json` репо, коммитит, пушит и скидывает в хаб.
   Так же: `status <id> --set done`, `remove <id>`, `list`.
3. **Авто-сборка** — `build_plan.py` перед рендером сам делает
   `drop.py <REPO> --no-push` для всех репо из `participants.txt` и рендерит
   `PLAN.md`: Просрочено → Сегодня → На неделю → Запланировано → Backlog →
   Сводка (со свежестью планов).
4. **Автопилот** — задачи репо решаются автоматикой, где возможно: у MAX это
   публикации по Планировщику (07:00–07:30), у агентов — сессии по
   `in-progress` задачам. Статус меняется той же командой `task.py status`.
5. **Синхронизация по команде (оркестрация)** — протокол `SYNC.md` и скрипт `sync.py`.
   Команда владельца «прочти E:\github\kalendar и все синхронизируй»: агент читает хаб,
   обновляет планы (drop/build), читает служебные команды репозиториев и выполняет
   действия по расписанию (для MAX/catden: четверг — медиа на хостинг 11 дней,
   пятница — агентный прогон стилистика+слои 1-3 и превью 10 дней в канал «календарь»),
   затем сообщает, что отправлено в «календарь» или какие явные поломки/ограничения.
   Служебные команды могут храниться в репо в tracked-файлах состояния
   (напр. `roles/blogger/channels/catden/automation.json` в MAX) и/или как задачи
   `source: kalendar|orchestrator` / `id: orch-*` в `plan.json` (MAX `export_plan.py`
   такие задачи сохраняет при регенерации).

Расписание публикаций — cron на хостинге Beget (локальный Планировщик Windows
не используется): `15,30,32,45 7 * *` — утренний прогон и статистика,
`0 9 * * 2` — administrator («Цифра недели», вторник), `0 12 * *` — ainow Format 1,
`30 19 * *` — zabava, `0 20 * *` — catden, `30 21 * *` — ainow. Серверный
`post_cron.php` читает посты из GitHub `DimaNikolaevi4/MAX` (main), состояния —
`0s3/blogger-data/state/` на хостинге. Канал `na100` сервер не обслуживает: его
формирует и публикует агент при первом утреннем запуске по команде владельца
«смотри E:\github\kalendar» (ФАЗА 3 в `AGENTS.md`, `bin/na100_morning.py`).

## Схема задачи в `plan.json`

```json
{
  "tasks": [
    {"id": "уникальный-ид", "title": "Что сделать",
     "when": "2026-11-24", "time": null, "status": "todo",
     "why": "зачем — одна фраза", "link": "путь-к-детаям.md",
     "source": "owner"}
  ]
}
```

| Поле | Значение |
|---|---|
| `when` | дата `YYYY-MM-DD` или пусто (тогда задача в Backlog) |
| `status` | `scheduled` (автомат доведёт до done) · `todo` · `in-progress` · `done` · `skipped` · `backlog` |
| `why` | зачем — одно предложение, почему это важно |
| `source` | `owner` (решение владельца) · `agent` (предложение агента) · `auto` (автоматика) · `kalendar`/`orchestrator` (служебная команда оркестрации; в MAX сохраняется при `export_plan`) |

Просроченным считается `todo`/`in-progress`/`scheduled` с датой в прошлом —
такие задачи поднимаются в секцию «Просрочено» с пометкой возраста.

## Участники

Список — `participants.txt` в корне хаба: MAX, Konkurs, YMK, cit-calck.rf, demoexam-kip,
bardakov.rf, vol, ii-monolit, avtosite, AvtoOtvety-Seller, moodle, videosite (12 репозиториев).
Новый участник = добавить строку в `participants.txt` и завести в его репо `plan.json`.

Вне календаря: `Veronika` (исключена владельцем 13.11.2026), `BPLA` (нет `plan.json`),
`cross-autoposting` (приватный, задач нет). Удалены и потому убраны из списка: `site`
(17.11.2026, дубль cit-calck.rf), `al` (код перенесён в `ii-monolit/products/ai-tutor`), `al-agent` (17.11.2026).

## Безопасность коммитов — обязательно перед каждым коммитом

Правило введено 18.11.2026 после инцидента в `vol`: коммит `1539bf0`
(14.11.2026) под сообщением «plan: задача add [passport-methodology] todo»
удалил 328 отслеживаемых файлов — фактически всё дерево репозитория. Причина:
`git add -A` / `git rm -r --cached .` подготовили удаления в индексе, а
`git status` и `git diff --cached --stat` перед коммитом не смотрели. Восстановили
откатом на `c8217fa`.

Чек-лист перед **каждым** `git commit` в любом репозитории `E:\github`,
даже если меняется один файл:

1. `git status --short` — увидеть, что именно изменилось.
2. `git diff --cached --stat` — подтвердить, что в индексе только то, что хотели.
   Любая строка `D` без явного намерения — стоп, разобраться до коммита.
3. Добавлять конкретный файл: `git add plan.json`, **не** `git add -A`, если в
   репозитории много untracked- или отсутствующих файлов.
4. Нужно убрать файлы из Git, но оставить на диске — `git rm -r --cached .`
   **отдельным коммитом** с честным сообщением, не вместе с правкой плана.
5. Увидели «файлов нет» или ссылку на несуществующий путь — сразу
   `git log --oneline --diff-filter=D --name-only` и восстановить из родительского
   коммита, а не делать вид, что «документы ведутся вне git».

Агент обязан прогонять этот чек-лист перед любым коммитом и не пушить,
пока в `git diff --cached --stat` нет неожиданных удалений.

## ИИ-модели через Cloudflare API (проверено 26.11.2026)

На этой машине доступен вывод моделей через **Cloudflare Workers AI** — это отдельный
канал ИИ, не связанный с публикациями в MAX.

- Токен: `E:\github\kalendar\local\cloudflare-token.txt` (каталог `local/` в `.gitignore`,
  в git не попадает). Исходная заметка `E:\github\ai.txt` теперь содержит только ссылку
  на панель токенов и путь к файлу — секрета в ней нет.
- Account ID (не секрет) — из URL панели в `E:\github\ai.txt`; в командах ниже `<ACCOUNT_ID>`.
- Endpoint: `POST https://api.cloudflare.com/client/v4/accounts/<ACCOUNT_ID>/ai/run/<model>`.
- Проверенная модель: `@cf/meta/llama-3.1-8b-instruct` (фактически отдаётся
  `@cf/meta/llama-3.1-8b-fast-v2`). Тело запроса — `{"messages":[{"role":"user","content":"..."}]}`;
  формат `{"prompt":"..."}` тоже принимается, но ответ менее предсказуем.
- Права токена: только Workers AI Inference. `/accounts` и `/zones` возвращают пустые
  списки, `/user` — `403 / 9109`. Для DNS и зональных операций нужен отдельный токен.
- Проверка 26.11.2026: `HTTP 200`, `success: true`, ответ модели получен.

Пример (PowerShell 5.1):

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$token = (Get-Content 'E:\github\kalendar\local\cloudflare-token.txt' -Raw).Trim()
$acc = (Get-Content 'E:\github\ai.txt' | Where-Object { $_ -match 'cloudflare\.com' }).Split('/')[3]
$body = @{ messages = @(@{ role='user'; content='Привет! Ответь кратко.' }) } | ConvertTo-Json -Depth 5
$r = Invoke-RestMethod -Method Post `
  -Uri "https://api.cloudflare.com/client/v4/accounts/$acc/ai/run/@cf/meta/llama-3.1-8b-instruct" `
  -Headers @{ Authorization = "Bearer $token" } -ContentType 'application/json' -Body $body
$r.result.response
```

## Ручные команды

```powershell
py E:\github\kalendar\build_plan.py        # drop всех участников + пересборка PLAN.md
py E:\github\kalendar\build_plan.py --push # то же + коммит + пуш
py E:\github\kalendar\build_plan.py --no-drop --push # пересборка без обновления планов
py E:\github\kalendar\drop.py MAX          # скинуть план одного репо (с пушем)
py E:\github\kalendar\sync.py              # оркестрация по дню недели (МСК): чтение команд, отчёт/действия, см. SYNC.md
py E:\github\kalendar\sync.py --force fri --post-status  # пример: пятничный прогон + статус в «календарь»
py E:\github\kalendar\bin\na100_morning.py              # состояние утреннего выпуска na100 и следующий шаг
py E:\github\kalendar\bin\na100_morning.py --mark       # отметить выпуск выполненным
py E:\github\kalendar\bin\na100_morning.py --reset      # снять метку для повторного прогона
```
