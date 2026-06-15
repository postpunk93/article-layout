# Changelog

Все заметные изменения проекта. Формат — Keep a Changelog.

## [Unreleased] — бета

### Добавлено
- Кроссплатформенность Windows/macOS: один репозиторий, клавиши через Playwright `ControlOrMeta`, путь к Chrome определяется по ОС, нормализация переводов строк (`.gitattributes`).
- Онбординг через Claude Code: `CLAUDE.md`, проектный скилл `layout-assistant`, bootstrap-скрипты `setup.command` / `setup.ps1`, русский `README.md`.

### Исправлено
- macOS: сохранённый вход больше не теряется. Автоматический Chrome запускался с `--use-mock-keychain` (дефолт Playwright) и не мог расшифровать cookies входа, сохранённые настоящим Chrome через Keychain, — а на старте удалял их как «битые». Теперь на macOS этот флаг отбрасывается, и автоматический Chrome берёт тот же ключ «Chrome Safe Storage». Windows (DPAPI) не затронут.

### Проверено
- e2e на macOS по всем 8 площадкам — _в процессе_ (см. план, задача A4).
