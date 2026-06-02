# Установка зависимостей (Windows). Запуск: powershell -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location -Path $PSScriptRoot
Write-Host "> Проверяю Python..."
python --version
Write-Host "> Ставлю зависимости (pip)..."
python -m pip install -r requirements.txt
Write-Host "> Доустанавливаю браузер Playwright (Chromium)..."
python -m playwright install chromium
Write-Host "Готово. Дальше: открой проект в VS Code и напиши Claude Code «настрой меня»."
