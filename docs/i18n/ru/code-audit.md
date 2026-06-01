# Code Audit

Last reviewed: 2026-06-01

Язык: [English](../../code-audit.md) | Русский

Английская версия является канонической. Эта страница - русский companion для
public-safe engineering и safety risk summary.

## Назначение

`docs/code-audit.md` хранит durable public risk areas без local calibration
history, private batch measurements, generated paths или branch-specific notes.

## Как использовать

- Перед изменением trust boundary проверьте, есть ли связанный audit finding.
- Не закрывайте finding только текстом; закрытие требует code/tests/docs,
  которые устраняют риск.
- Если finding устарел из-за фактической реализации, обновите public
  conclusion; detailed validation evidence держите в local exclude-only notes.

Полный список рисков и приоритетов находится в
[английском audit](../../code-audit.md).
