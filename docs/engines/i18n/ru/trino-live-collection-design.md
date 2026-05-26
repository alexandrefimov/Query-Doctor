# Проект live-сбора Trino

Last reviewed: 2026-05-26

Язык: [English](../../trino-live-collection-design.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме будущего дизайна live-сбора Trino.

## Статус

Это дизайн будущей работы, а не текущая поддержка. Сейчас допустимы только
синтетические или fixture-only проверки.

## Возможные фазы

1. Offline fixture import.
2. Local event-store reader.
3. Bounded query-detail import.

Каждая фаза должна иметь явные границы доступа, authentication handling,
лимиты, redaction и тесты. Live collector нельзя подключать к продукту, пока
он не проходит те же правила безопасности, что и Impala workflow.

## Ограничение

Даже если будущий Trino источник доступен, Query Doctor не должен показывать
сырые statements, host identifiers, raw connector payloads, credentials,
локальные пути или внутренние runtime details.
