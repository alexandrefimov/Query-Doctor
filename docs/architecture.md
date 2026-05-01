# Архитектура Query Doctor

Query Doctor держит fact extraction детерминированным, а LLM использует только
уже извлечённые факты для русскоязычной формулировки отчёта.

## Pipeline

```text
Cloudera Manager profile / profile_digest.md
  -> query_doctor_collect_cm_profiles.py
  -> ignored local case directory
  -> analyze_profile_digest.py
  -> analysis_facts.md
  -> action cards and deterministic evidence
  -> optional Table Metadata Context from local impala_context.json
  -> query_doctor_report.py
  -> sanitizer and fail-closed validator
  -> deterministic analyzer facts appendix
  -> admin/user reports
  -> local UI
```

## Компоненты

Collector:
- Выполняет explicit, bounded, read-only сбор профилей из Cloudera Manager.
- Требует redaction для real collection.
- Сохраняет analyzer-useful counters и stable safe host aliases.
- Пишет generated local cases только в ignored corpus paths.
- Сам не запускает analyzer или report writer.

Analyzer:
- Читает `profile_digest.md`.
- Извлекает deterministic facts в `analysis_facts.md`.
- Пишет operator summaries, anomaly counts, action cards, backend/host evidence,
  referenced tables и optional table metadata facts, если они есть.
- Читает local `impala_context.json`, если он есть, и добавляет
  `## Table Metadata Context`.
- Не вызывает Cloudera Manager, Ollama или report writer.

Report writer:
- Читает только `analysis_facts.md`.
- Использует LLM для narrative wording, не для fact discovery.
- Не должен делать inference из raw profile text, SQL, local config или external
  context.
- Генерирует admin/user reports для разных аудиторий, но с одной fact boundary.
- Требует LLM narrative sections `## Короткий вывод` и `## Подробный разбор`.
- Детерминированно добавляет `## Факты анализатора` из `analysis_facts.md`; LLM
  не должен писать эту appendix-секцию.
- Сейчас намеренно исключает `## Table Metadata Context` из prompt LLM.
- Показывает table metadata facts только в Python-generated
  `## Факты анализатора`.
- Буферизует raw LLM output. Финальный report пишется только после
  normalization, sanitization, narrative validation, appendix append и final
  validation.

Sanitizer и validator:
- Нормализуют узкий набор unsafe generated wording в явную safe wording.
- Отклоняют reports с unsupported claims.
- Работают fail-closed: rejected report безопаснее, чем accepted invented
  evidence.
- При validation failure пишут только sanitized/normalized `.partial` и
  сохраняют существующий final report.

Local UI:
- Показывает локальный workflow для одного explicit query id.
- Переиспользует collected cases, когда это безопасно.
- Не является источником фактов.
- Не включает broad collection.

## Текущее real-case покрытие

Локальный ignored corpus покрывает важные классы:

- `e94fbeb93feb2ad1_edd9d52c00000000`: host/backend data-skew evidence без
  доказанного execution-tail host.
- `fa469f95f6fb7286_ea9f070d00000000`: bad-query case с подтверждёнными
  row/cardinality и memory estimate anomalies.

Не добавляйте в committed docs raw SQL, raw hostnames, raw IP addresses, raw
profiles, local config или credentials.
