# Матрица пробелов поддержки движков

Last reviewed: 2026-06-03

Язык: [English](../../engine-support-gap-matrix.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме матрицы поддержки движков. Матрица является source of truth для текущих
engine support, fixture-only и research statuses в репозитории, но не является
public support promise.

## Текущий статус

Текущий production triage engine Query Doctor - Apache Impala. Trino
поддержан только как sanitized offline evidence package import, bounded local
event-store import, bounded HTTP event archive import, bounded HTTP
query-detail archive import, bounded local query-detail import, bounded local
query-list aggregate import, bounded local statement-stats import,
event-source contract checking, dry-run coordinator query-info target checking
и one-query pruned coordinator query-info probing/import, plus raw-free
normalized fact boundaries; pruned coordinator import может писать direct
`--boundary-out` для local readiness audits. Spark и другие движки остаются
исследовательскими
направлениями и не являются текущей пользовательской поддержкой.

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

Для Impala нужно сохранять стабильность текущего контракта. Для Trino текущая
граница - offline evidence package import, bounded local event-store import,
bounded HTTP event archive import, bounded HTTP query-detail archive import,
bounded local query-detail/query-list aggregate import и bounded local
statement-stats import, плюс event-source contract checking и dry-run
coordinator query-info target checking, plus one-query pruned coordinator
query-info probing/import с direct `--boundary-out` для local readiness audits;
broader Trino coordinator reader, metadata, browser/report surfaces, optimizer
behavior и generated Trino SQL остаются неподдержанными, пока не появятся
безопасные, ограниченные и проверенные источники фактов.
Текущий Trino слой уже покрывает compact resource-group queue-delay event без
live reader или browser/report surfaces. Unknown source-contract event теперь
отдельно фиксирует fail-closed поведение для неподдержанного source contract
version.
Compact query-detail fixtures покрывают blocked, failure-category,
spill-observed, stage-skew, queued lifecycle/timing и connector-metric
supported/not-observed variants только как offline import mapping, без raw
query-detail records или live query-info fetch.
Coordinator query-info target check валидирует только compact source contract,
coordinator base-URL shape и один Query ID shape. Он не делает network read,
не fetch-ит query-info JSON, не echo-ит URL/Query ID и не является live Query ID
diagnosis.
Pruned coordinator query-info probe может после accepted contract сделать
ровно один bounded `GET /v1/query/{queryId}?pruned=true`, проверить только
bounded JSON object и вывести safe summary. Optional local `--auth-header-file`
может содержать только одну operator-managed `Authorization` header line; auth
header path/value не печатаются, HTTP redirects не follow-ятся. Он не мапит
QueryInfo в facts, не печатает URL/Query ID/raw payload content и не является
live Query ID diagnosis.
Pruned coordinator query-info import использует тот же bounded read после
accepted contract, мапит только allowlisted lifecycle и `queryStats` fields в
raw-free normalized facts и boundary JSON. `--boundary-out` может записать
direct `engine_fact_boundary_v1` payload для strict local readiness audit без
печати output path. Он не следует HTTP redirects, не печатает URL/Query ID/raw
payload content, не раскрывает query text, session fields, object names,
stage/task details, connector internals или auth header path/value и не
является live Query ID diagnosis.
Trino compact diagnosis теперь может читать один уже raw-free
`engine_fact_boundary_v1` payload или один selected sample boundary из package
boundary export и писать deterministic local JSON с attention areas, change
directions, verification prompts и limitations, включая planning-heavy timing и
high peak memory только из supported facts после conservative thresholds.
Isolated local `/trino/compact-diagnosis` page принимает тот же direct boundary
или selected package sample без echo submitted JSON. High-memory attention area
использует тот же 100 GiB conservative threshold, что и query-list memory
bucket. Diagnosis не читает raw Trino payloads, не echo-ит input strings, не
делает root-cause claims, не добавляет browser/report output, optimizer
behavior, live Recent workflow или Trino SQL execution.
Statement-stats fixture input теперь тоже reject-ится при oversized payloads,
unsafe raw field names или unsafe text values до mapping.
Compact summaries для connector metric, failure category и stage skew
принимают только exact checked fields; extra fields или nested details оставляют
derived fact в `unknown`.
Nested objects/arrays проверяются теми же правилами, а payloads глубже
accepted maximum depth reject-ятся до mapping.
Non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) reject-ятся до
mapping.
Отрицательные timing/resource/count values в Trino offline import фактах
остаются `unknown`.

Spark сейчас имеет compact synthetic fixture schema, fixture-only fact mapper,
experimental compact Spark History Server intake для explicit applications и
local compact evidence-package build/validation/fixture export для already
accepted compact samples. History Server path читает только bounded summary `/api/v1` JSON, включая
application lifecycle, attempt state и attempt counts при доступном explicit
application endpoint и aggregate job-state counts при доступных job summaries.
Executor summaries дают только aggregate executor loss/churn state; dynamic
allocation остается unknown без explicit compact source support. Missing
application endpoints остаются warning/unknown, attempt counts ограничены
отдельным bound, а Spark version strings сводятся только к safe version-family
labels. Raw event logs, raw SQL/plans/environment, application IDs, attempt
IDs, job IDs, executor IDs, users и raw version strings не записываются. Этот
path не добавляет Spark engine registration, Recent workflow, browser/report
output, optimizer behavior или support claim. Evidence-package builder/validator/exporter
печатает только path-free safe summaries и не принимает raw event logs или raw
History Server exports. Compact facts также могут
записываться в deterministic local compact-diagnosis JSON с raw-free attention
areas, change directions, verification prompts и limitations, но без root-cause
claims и без product surfaces. Следующий шаг требует отдельной coordination
slice перед изменением shared normalized facts или product workflow.
