# ==========================================
# ТРИГГЕР: "смотри E:\github\kalendar"
# ==========================================
## ЖЕСТКИЕ ПРАВИЛА (нарушение = провал)
1. ЗАПРЕЩЕНО использовать Linux-синтаксис (&&, ||, head, echo). Только PowerShell 5.1.
2. ЗАПРЕЩЕНО писать внутренний монолог, объяснения или "процесс отладки". Выдай ТОЛЬКО финальный отчет.
3. ЗАПРЕЩЕНО паниковать из-за артефактов отображения кириллицы в выводе консоли. Команда `ConvertFrom-Json` читает UTF-8 файлы корректно. Игнорируй визуальные артефакты консоли.
4. Если репозитория нет локально, просто запиши "ОТСУТСТВУЕТ" и иди дальше. Не пытайся клонировать его в этом скрипте.

## АЛГОРИТМ (выполни молча, выдай ТОЛЬКО финальный отчет)
### ШАГ А. Чтение паспорта
Прочитай `E:\github\kalendar\docs\ai-orchestration\machine_profile.json`.

### ШАГ Б. Выполнение скрипта (НЕ ИЗМЕНЯЙ ЕГО, НЕ ДОБАВЛЯЙ ПРОВЕРКИ):
```powershell
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
        if ($pullCode -eq 0) { $syncResults += "${repo}: OK" } 
        else { $syncResults += "${repo}: ОШИБКА" }
    } else {
        $syncResults += "${repo}: ОТСУТСТВУЕТ"
    }
}
$tasks = @()
foreach ($repo in $profile.repos_to_sync) {
    $planFile = "E:\github\kalendar/plans/$repo.json"
    if (Test-Path $planFile) {
        $json = Get-Content $planFile -Raw | ConvertFrom-Json
        foreach ($task in $json.tasks) {
            if ($task.when -ge "2026-11-21" -and $task.when -le "2026-11-24" -and $task.status -ne "done" -and $task.status -ne "backlog") {
                $tasks += [PSCustomObject]@{ Date = $task.when; Title = $task.title; Status = $task.status; Repo = $repo }
            }
        }
    }
}
$syncReport = if ($syncResults -notmatch "ОШИБКА|ОТСУТСТВУЕТ") { "Все ОК" } else { ($syncResults -match "ОШИБКА|ОТСУТСТВУЕТ" -join ", ") }
Write-Output "✅ **СИНХРОНИЗАЦИЯ:** $syncReport

📅 **ЗАДАЧИ (Сегодня + 3 дня):**

| Дата | Задача | Статус | Репозиторий |
| :--- | :--- | :--- | :--- |"
foreach ($t in $tasks) { Write-Output "| $($t.Date) | $($t.Title) | $($t.Status) | $($t.Repo) |" }
```

### ШАГ В. Вывод
Выведи ТОЛЬКО результат выполнения скрипта выше. Никаких слов до или после.
