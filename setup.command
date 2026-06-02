#!/bin/sh
# Установка зависимостей для верстальщика (macOS). Двойной клик или: sh setup.command
set -e
cd "$(dirname "$0")"
echo "▸ Проверяю Python…"
python3 --version
echo "▸ Ставлю зависимости (pip)…"
python3 -m pip install -r requirements.txt
echo "▸ Доустанавливаю браузер Playwright (Chromium)…"
python3 -m playwright install chromium
echo "✓ Готово. Дальше: открой проект в VS Code и напиши Claude Code «настрой меня»."
