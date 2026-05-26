# Матрица пробелов поддержки движков

Last reviewed: 2026-05-26

Язык: [English](../../engine-support-gap-matrix.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме матрицы поддержки движков.

## Текущий статус

Текущий реализованный движок Query Doctor - Apache Impala. Trino и другие
движки остаются исследовательскими направлениями и не являются текущей
пользовательской поддержкой.

Матрица нужна, чтобы не смешивать три разных состояния:

- `implemented`: поведение реализовано, проверено и может попадать в продукт;
- `contracted`: контракт описан, но продукт не должен заявлять поддержку;
- `fixture-only`: есть синтетические или тестовые данные, но нет live-сбора;
- `unknown`: сигнал пока не изучен;
- `not observed`: сигнал поддерживается контрактом, но в конкретном случае не
  был обнаружен.

## Практическое правило

Новые движки нельзя добавлять как "почти Impala с другими полями". Для каждого
движка нужны отдельные источники фактов, правила безопасности, fixture pack,
валидаторы и формулировки ограничений.

Для Impala нужно сохранять стабильность текущего контракта. Для Trino
допустим только исследовательский fixture-only путь, пока не появятся
безопасные, ограниченные и проверенные источники фактов.
Текущий Trino fixture-only слой уже покрывает compact resource-group
queue-delay event, но без live reader, browser/report surfaces или claims о
поддержке. Unknown source-contract event теперь отдельно фиксирует
fail-closed поведение для неподдержанного source contract version.
Statement-stats fixture input теперь тоже reject-ится при oversized payloads,
unsafe raw field names или unsafe text values до mapping.
Compact summaries для connector metric, failure category и stage skew
принимают только exact checked fields; extra fields или nested details оставляют
derived fact в `unknown`.
Nested objects/arrays проверяются теми же правилами, а payloads глубже
accepted maximum depth reject-ятся до mapping.
Non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) reject-ятся до
mapping.
Отрицательные timing/resource/count values в Trino fixture-only фактах
остаются `unknown`.
