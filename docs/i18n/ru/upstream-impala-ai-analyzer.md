# Upstream AI-анализатор профилей Impala

Last reviewed: 2026-05-26

Язык: [English](../../upstream-impala-ai-analyzer.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме watchlist по upstream Impala AI profile analyzer.

## Позиционирование

В Apache Impala идет работа над встроенным AI-анализатором профилей. Query
Doctor не должен позиционироваться как еще одна кнопка "AI analyze" для одного
профиля.

Практическое отличие Query Doctor:

- local-first workflow рядом с учетными данными оператора;
- детерминированный analyzer сначала, LLM только для формулировок;
- доверенные отчеты без сырых данных;
- пакетный Recent scan и triage многих запросов;
- интеграция с Cloudera Manager и bounded context collection;
- safety/redaction как продуктовый контракт;
- операторский workflow вне одной кнопки WebUI.

## Watchlist

Upstream работу нужно отслеживать как источник полезных идей и совместимости,
но не копировать поведение без отдельного контракта фактов, безопасности и
валидации.
