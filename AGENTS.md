# ==========================================
# ТРИГГЕР ДЛЯ КОМАНДЫ: "смотри E:\github\kalendar"
# ==========================================
## ЖЕСТКИЕ ПРАВИЛА (нарушение = провал задачи)
1. ЗАПРЕЩЕНО использовать Linux-синтаксис: &&, ||, head, tail, echo, 2>/dev/null. ТОЛЬКО PowerShell 5.1 (; или новые строки).
2. ЗАПРЕЩЕНО писать вступления, выводы, объяснения. Только результат.
3. ЗАПРЕЩЕНО создавать временные файлы (.ps1) в C:\Users\Public\ или AppData\Temp. Все команды выполняй НАПРЯМУЮ в консоли.
4. При вставке переменной перед двоеточием ОБЯЗАТЕЛЬНО используй ${имя_переменной} или конкатенацию.

## АЛГОРИТМ (выполни молча, выдай ТОЛЬКО финальный отчет)
### ШАГ А. Чтение паспорта
Прочитай файл E:\github\kalendar\docs\ai-orchestration\machine_profile.json. Запомни root_dir и repos_to_sync.

### ШАГ Б. Синхронизация и сбор задач (выполни этот скрипт целиком):
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
    $planFile = "E:\github\kalendar\plans\$repo.json"
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
### ШАГ В. Финальный отчет
Выведи ТОЛЬКО результат выполнения скрипта выше. Никаких слов до или после.
