# Проект live-сбора Trino

Last reviewed: 2026-05-26

Язык: [English](../../trino-live-collection-design.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме будущего дизайна live-сбора Trino.

## Статус

Это дизайн будущей работы, а не текущая поддержка. Сейчас допустимы только
синтетические или fixture-only проверки. Текущий fixture pack включает
compact event-listener проверку resource-group queue delay, но она остается
тестом intake-контракта, а не live reader. Unknown source-contract fixture
проверяет fail-closed поведение для неподдержанного source contract version.
Synthetic query-list contract probe fixture покрывает sanitized `/v1/query`
aggregate list-shape evidence: record counts, field-presence counts, safe
state/failure buckets и explicit redaction assertions. Он не делает
query-detail fetch и не отправляет SQL statements.
Statement-stats fixtures проходят такие же oversized и raw-field/text rejection
checks перед mapping. Non-finite numeric values (`NaN`, `Infinity`,
`-Infinity`) reject-ятся до mapping.
Compact summaries для connector metric, failure category и stage skew имеют
exact shape; extra fields или nested details оставляют derived fact в
`unknown`.
Nested objects и arrays проходят те же проверки, а payloads глубже accepted
maximum depth fail-closed до mapping.
Отрицательные timing/resource/count values остаются `unknown`.
Первый handoff из тестового Trino-кластера должен идти через
[чеклист evidence export](trino-test-cluster-evidence-checklist.md) и
[шаблоны evidence package](trino-evidence-package-templates.md), как
operator-exported sanitized fixtures, а не как live reader. Локальный
package-intake validator принимает только explicit `manifest`,
`redaction_note`, `samples` JSON payload и только sample source types, для
которых уже есть fixture validators: statement-statistics, event-listener и
aggregate query-list summary exports.
`scripts/validate_trino_evidence_package.py` - текущая локальная dry-run
команда для таких пакетов; она печатает только safe summary и не добавляет
live collection.

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
