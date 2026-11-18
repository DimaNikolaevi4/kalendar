# Планировщик Windows: сборка глобального календаря (07:25 МСК).
# Рендерит plans/*.json в PLAN.md, коммитит и пушит хаб.
# «Только утром»: StartWhenAvailable может догнать пропущенный запуск при
# включении ПК днём — вне утреннего окна (07:00-10:00) ничего не делаем.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath 'E:\github\kalendar'
$OutputEncoding = [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false
$env:PYTHONIOENCODING = 'utf-8'

New-Item -ItemType Directory -Force -Path 'logs' | Out-Null
$log = 'E:\github\kalendar\logs\build_plan.console.log'

$now = Get-Date
if ($now.Hour -lt 7 -or $now.Hour -ge 10) {
    "вне утреннего окна 07:00-10:00, запуск пропущен: $(Get-Date -Format 'dd.MM HH:mm:ss')" |
        Out-File -Append -Encoding UTF8 $log
    exit 0
}

& py 'E:\github\kalendar\build_plan.py' --push 2>&1 |
    Out-File -Append -Encoding UTF8 $log
exit $LASTEXITCODE
