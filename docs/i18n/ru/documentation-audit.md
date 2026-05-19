# Documentation Audit

Last updated: 2026-05-19

Язык: [English](../../documentation-audit.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
фиксирует результаты аудита документации.

## Sensitive information

Текущий tracked tree проходит public-release text scan: в текущих docs нет
organization-specific LLM/infrastructure endpoints, private keys,
high-confidence tokens, embedded URL credentials или private local user paths.

Full git history scan все еще требует отдельного cleanup: старый
production-looking LLM endpoint присутствовал в истории credentials docs. Это
нельзя удалить обычным follow-up commit; нужен clean public branch или
deliberate history rewrite.

## Russian localization

После текущего cleanup все current non-archived English docs имеют русскую
companion-страницу. Полные дословные переводы остаются неравномерными:
приоритеты - configuration, security model, query optimizer contract, local
smoke и model bake-off.

Подробный audit: [английская версия](../../documentation-audit.md).
