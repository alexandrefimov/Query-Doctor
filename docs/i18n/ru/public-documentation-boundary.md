# Public Documentation Boundary

Last reviewed: 2026-06-01

Язык: [English](../../public-documentation-boundary.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
фиксирует границу между committed public docs и ignored local notes.

## Правило

Все committed Markdown-файлы считаются публичной документацией. Durable safety
rules, contracts, runbooks с placeholders, release notes и path-free aggregate
validation summaries можно коммитить.

Private branch notes, workstation-specific smoke details, local cluster
selectors, generated artifact paths, raw evidence и chat-local reminders должны
оставаться в local exclude-only notes. Настраивайте такие notes через
`.git/info/exclude` или personal global Git exclude, а не через tracked
`.gitignore`.

## Локальные заметки

Path для local notes - workstation choice. Не фиксируйте его в public docs;
храните его в `.git/info/exclude` или personal global Git exclude.

## Проверки

Перед commit для agent docs, runbooks, validation logs или release docs:

```bash
python3 scripts/check_staged_public_safety.py
python3 scripts/check_staged_public_safety.py --changed
python3 scripts/audit_public_docs.py
python3 scripts/check_active_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

Полный контракт находится в
[английском документе](../../public-documentation-boundary.md).
