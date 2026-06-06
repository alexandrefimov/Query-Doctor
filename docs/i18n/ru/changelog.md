# Changelog

Last updated: 2026-06-06

Язык: [English](../../changelog.md) | Русский

Английский changelog является каноническим. Эта страница объясняет, как читать
и обновлять changelog на русском.

## Что фиксируется

`docs/changelog.md` хранит только значимые изменения:

- product/workflow behavior;
- safety и trust-boundary changes;
- report или optimizer behavior;
- collector/analyzer behavior;
- major documentation baseline changes.

Minor copy edits, CSS polish, tests и internal refactors обычно не требуют
changelog entry, если они не меняют behavior или safety.

## Текущий порядок

- Новые записи добавляются в `## Unreleased`.
- Используйте короткие bullets по категориям: Engineering, Product, Safety,
  Documentation.
- Для точного текста и истории релизов смотрите
  [английский changelog](../../changelog.md).
- Curated release notes для `0.6.0` находятся в
  [английской версии](../../release-notes-0.6.0.md) и русском companion-файле
  [release-notes-0.6.0.md](release-notes-0.6.0.md).

## Summary 0.6.0

Английский `0.6.0` фиксирует, что Trino retained package-level
handoff suites могут требовать selected source contracts через
`--require-source-contract`, diagnostic-lane source granularities через
`--require-source-granularity` и verification scopes через
`--require-verification-scope`. Suite audit принимает только safe labels,
reject-ит missing retained evidence без печати paths или rejected
user-supplied values и сохраняет retained package evidence ниже Trino product
support.
Английский `0.6.0` фиксирует local retained-suite manifest для
Impala north-star calibration. `build_impala_north_star_suite_manifest.py`
собирает redaction-reviewed manifest из raw-free loop summaries, а
`audit_impala_north_star_gate.py --suite-manifest` требует minimum retained
batch breadth и пишет safe trend без paths, artifact filenames, raw cases,
SQL, profiles, workload fingerprints или action-outcome records.
Английский `0.6.0` фиксирует safe unknown-category rollup в
retained Impala north-star summaries: `unknown_primary_category_counts` и
`top_unknown_primary_categories` помогают выбирать next deterministic evidence
work по вкладу unknown, не раскрывая raw cases и не усиливая diagnosis wording.
Английский `0.6.0` фиксирует sanitized
`unknown_primary_resolution_counts` в retained diagnostic-loop summaries и
resolution-class rollup в north-star aggregate, чтобы отделять deterministic
evidence gaps от clean/out-of-scope boundaries.
Английский `0.6.0` также фиксирует, что committed synthetic Impala
north-star aggregate хранит такой же unknown-primary resolution-class split:
CI защищает не только passing unknown-rate, но и то, что оставшиеся unknown
являются clean boundaries, а не deterministic evidence backlog.
Английский `0.6.0` фиксирует, что Trino one-query handoff
wrappers могут писать optional `trino_one_query_handoff_summary_v1` raw-free
machine evidence. Retained handoff-suite manifests могут ссылаться на эти
summaries, а compact readiness gate reject-ит drifted pipeline,
artifact-boundary или embedded readiness evidence, сохраняя path-free
no-product-support boundary.
Английский `0.6.0` фиксирует optional `--summary-json` для
Spark support-boundary audit. Retained `spark_support_boundary_audit_v1`
summary хранит только no-support boundary labels, check statuses, safe counts
и safe issue categories/messages без печати paths или расширения Spark за
compact support surfaces.
Английский `0.6.0` фиксирует, что Spark retained package
handoff-suite audits могут требовать явные diagnostic-lane
source-granularity labels через `--require-source-granularity`. Suite summary
JSON сохраняет выбранные source-granularity requirements, а отсутствующие
запрошенные labels отклоняются как path-free readiness gaps без reopening
packages или Spark support claim.
Английский `0.6.0` фиксирует, что Spark compact-readiness suite
audits могут требовать явные diagnostic-lane source-granularity labels через
`--require-source-granularity` для direct compact inputs, fixture-export
manifests и retained one-application handoff-suite manifests. Summary JSON
сохраняет выбранные source-granularity requirements, а отсутствующие
запрошенные labels отклоняются как path-free readiness gaps.
Английский `0.6.0` фиксирует, что Spark product-surface audit
summaries сохраняют diagnostic-lane readiness, source-granularity,
verification-scope и fact-state counters. Retained one-application suite
audits заново считают эти counters, чтобы ловить no-product-surface summary
drift без reopening Spark или расширения Spark за compact preview lanes.
Английский `0.6.0` фиксирует, что Spark compact-readiness
summaries сохраняют diagnostic-lane source-granularity и verification-scope
counters рядом с readiness и fact-state counters, чтобы retained
one-application suite evidence доказывал и lane readiness, и comparable
verification scope без reopening Spark.
Английский `0.6.0` фиксирует, что Spark compact-readiness suite
audits могут требовать явные diagnostic-lane verification-scope labels через
`--require-verification-scope` для direct compact inputs, fixture-export
manifests и retained one-application handoff-suite manifests. Summary JSON
сохраняет выбранные scope requirements, а отсутствующие запрошенные scopes
отклоняются как path-free readiness gaps.
Английский `0.6.0` фиксирует, что Spark package handoff summaries
сохраняют diagnostic-lane checked, readiness, source-granularity,
verification-scope и fact-state counters. Retained handoff suite audits
reject-ят summaries, которые теряют required `compact_attention_ready`
evidence, accepted source-granularity counters или accepted verification-scope
counters, оставаясь path-free и ниже Spark product support.
Английский `0.6.0` фиксирует, что retained Spark package handoff
suite audits могут требовать явные diagnostic-lane verification-scope labels
через `--require-verification-scope`. Suite summary JSON сохраняет выбранные
scope requirements, а missing requested scopes fail-ятся как path-free readiness
gaps без reopening Spark и без расширения Spark за compact preview lanes.
Английский `0.6.0` фиксирует optional
`--product-surface-summary-json` для Spark one-application handoff-suite
manifest. Readiness gate считает эти refs retained artifacts и защищает
summary outputs от overwrite, а Spark product-surface audit заново считает
per-entry summary, чтобы ловить no-product-surface evidence drift без печати
paths или raw payloads.
Английский `0.6.0` фиксирует optional
`--product-surface-summary-out` для Spark one-application handoff. Dev-only
wrapper запускает Spark product-surface boundary audit по только что
записанным compact/diagnosis artifacts, пишет raw-free/path-free
`spark_product_surface_boundary_audit_v1` summary и не ослабляет failed exit
status, если strict compact readiness падает.
Английский `0.6.0` фиксирует, что Trino preview source types имеют
checked source-contract registry для accepted bounded source kinds,
raw-storage policy, required bounds, network access classes и promotion gates.
Support-gap audit reject-ит missing registry coverage и любые registry entries,
которые включают product surfaces, Details/trusted reports, Recent scans,
optimizer behavior, SQL execution, raw storage, browser/report output или
metadata identifier output.
Английский `0.6.0` фиксирует, что public code-audit и Codex
handoff baselines больше не называют Trino source-contract registry будущей
задачей: они записывают его как owner accepted preview source kinds, raw
policy, bounds, network-access classes и promotion gates. Remaining broad
Trino/Spark architecture backlog оставляет только shared readiness/handoff
helpers.
Английский `0.6.0` фиксирует, что cross-engine normalized facts
имеют checked promotion-policy registry для shared, distributed-SQL-family,
source-boundary и support-boundary fact IDs, visible to Trino preview lanes.
Support-gap audit reject-ит missing policy coverage, mismatched
allowed-engine/scope contract, enabled product surfaces, weakened raw-free
policy или missing explicit promotion gate.
Английский `0.6.0` фиксирует, что Trino и Spark dev-only handoff
scripts имеют shared handoff artifact helpers для path-overlap checks и
ASCII/sorted JSON writes. Engine-specific redaction guards, readiness gates и
below-support wording остаются в owning scripts.
Английский `0.6.0` фиксирует, что Trino retained one-query
handoff suites могут хранить optional per-entry
`trino_compact_readiness_summary_v1` refs. Manifest builder держит refs safe и
relative, suite gate может требовать их через
`--require-readiness-summary-json`, а audit сверяет каждую retained summary с
deterministic one-query boundary/diagnosis/smoke readiness result без печати
artifact paths, filenames, coordinator URLs, Query IDs, auth material, raw
QueryInfo, SQL или support claims.
Английский `0.6.0` фиксирует, что Trino one-query compact
readiness переносит safe `trino_version_family` fact из accepted coordinator
QueryInfo source contract в raw-free boundary payload. Dev-only one-query
handoff требует минимум одну non-unknown version family, а retained
handoff-suite audit может требовать minimum version-family breadth или
конкретные safe version-family labels без печати coordinator URLs, Query IDs,
auth material, raw QueryInfo, artifact paths или raw version strings.
Английский `0.6.0` фиксирует, что Spark History Server
application-only collection трактует unavailable SQL execution-list endpoint
как safe `sql_execution_endpoint` compatibility limitation, а не
source-coverage warning, и при этом может суммировать readable
application-level jobs, stages, scheduler delay, spill и task duration buckets
как raw-free `same_application` context. SQL execution timing, failure category
и exact query linkage остаются `unknown`, пока accepted SQL execution summary
не поддержит их напрямую. Exact SQL execution selectors остаются strict: если
explicit endpoint недоступен или execution не найден, collector всё ещё пишет
safe source warning IDs и оставляет query linkage `same_application`.
Английский `0.6.0` фиксирует, что Spark compact evidence-package
validation требует от `application_only_same_application` promotion sample
warning-free History Server compact evidence с `same_application` provenance,
supported application-level job/stage/task и task-duration context, без claimed
SQL execution timing или failure facts. Gate остается preview/readiness-only и
не создает Spark support claim.
Английский `0.6.0` фиксирует, что Spark
one-application-suite-to-package bridge reject-ит SQL-specific sample-case
labels, если retained compact History Server payload не содержит accepted
`exact_query` SQL execution evidence. Это не дает `same_application`
application-level handoffs перелabelивать в exact SQL, long-elapsed,
failure-category или adaptive-execution samples и сохраняет Spark ниже support.
Английский `0.6.0` фиксирует, что Spark compact diagnosis пишет
raw-free `spark_compact_diagnostic_lane_v1` contract с source granularity,
evidence readiness, verification scope, fact-state counts и required
readiness/surface gates. Compact-readiness audit заново считает и валидирует
этот lane contract, поэтому retained handoffs fail-closed при missing/drifted
lane evidence без wiring Spark в Details, reports, optimizer, Recent или
support claims.
Английский `0.6.0` фиксирует, что Spark compact evidence-package
validation валидирует тот же `spark_compact_diagnostic_lane_v1` contract для
каждого accepted sample и включает safe diagnostic-lane
readiness/source-granularity counters в package summaries и readiness JSON.
Package promotion gate теперь требует минимум один `compact_attention_ready`
lane, оставаясь preview-only и ниже Spark support.
Английский `0.6.0` фиксирует, что isolated Spark
compact-diagnosis page рендерит raw-free diagnostic lane как first-class
preview block: evidence readiness, source granularity, verification scope,
supported-attention count и source-warning count видны без echo submitted
compact JSON, History Server selectors, lane schema internals,
Details/trusted report wiring, optimizer behavior, Recent workflow behavior
или Spark support claim.
Английский `0.6.0` фиксирует, что Spark History Server compact
collection трактует unavailable per-stage `taskSummary` enrichment reads как
safe `task_summary_endpoint` compatibility context, а не source-coverage
warning. Stage skew и task-duration signals остаются `unknown`, пока accepted
stage summaries или task-summary quantiles не дадут достаточно raw-free
evidence.
Английский `0.6.0` фиксирует, что Spark compact diagnosis мапит
supported over-one-minute task duration bucket evidence в
`spark_task_duration_tail` attention area. Сигнал value-gated, остается
raw-free и не claim-ит Spark root cause, Details/trusted-report wiring,
optimizer behavior, Spark job execution или product support.
Английский `0.6.0` фиксирует, что Trino coordinator QueryInfo
source contracts требуют safe `trino_version_family` вместе с
source-contract и QueryInfo schema versions. Target check, pruned probe,
pruned import и dev-only one-query handoff summaries показывают только этот
broad safe label, reject-ят URL/path-like version values и по-прежнему не
печатают coordinator URLs, Query IDs, auth material, raw QueryInfo или Trino
support claim.
Английский `0.6.0` фиксирует, что Spark compact diagnosis
использует supported application lifecycle как safe fallback, когда SQL
execution lifecycle недоступен в application-only History Server evidence.
Это улучшает Spark 2.4-style compact diagnosis context, но SQL failure,
failure-category, root-cause, Details/trusted-report, optimizer, Spark job
execution и support claims остаются unclaimed без прямых SQL/failure facts.
Английский `0.6.0` фиксирует, что Spark History Server compact
collection пропускает per-stage `taskSummary` reads, когда stage summary уже
содержит task runtime quantiles, и не делает task-summary reads для zero-task
stages. Это держит optional task enrichment bounded и уменьшает ложные
source-coverage warnings без task lists, raw stage identifiers, task details,
URLs, logs, SQL или изменения Spark no-support boundary.
Английский `0.6.0` фиксирует explicit `--partial-ok` dry-run mode
для Spark evidence handoff audit. Он нужен только для sanitized packages с
ожидаемо неполным sample/case coverage: audit использует partial-evidence
contract standalone validator-а, может записать rejected raw-free blocker
summary и по-прежнему не запускает fixture export, не печатает package paths,
raw values, request selectors и не создает Spark support claim.
Английский `0.6.0` фиксирует, что dev-only Trino one-query live
handoff может использовать explicit Kerberos/SPNEGO curl fetch mode для одного
bounded `GET /v1/query/{queryId}?pruned=true`, если оператор уже подготовил
local ticket cache. Режим mutually exclusive с `--auth-header-file`, сохраняет
source-contract/readiness gates, reject-ит output overlap с Kerberos local
inputs и не печатает coordinator URLs, Query IDs, principals, ticket-cache
paths, auth material, raw QueryInfo, local paths, filenames или Trino support
claim.
Английский `0.6.0` фиксирует, что Trino one-query live handoff
может писать optional raw-free `trino_compact_readiness_summary_v1` через
`--readiness-summary-out` в том же dev-only запуске, который пишет boundary и
compact diagnosis JSON. Wrapper использует strict one-query/source-version
readiness gate, reject-ит overlap summary output с input/output artifacts и не
печатает coordinator URLs, Query IDs, auth headers, raw QueryInfo, local paths,
filenames или Trino support claim.
Английский `0.6.0` фиксирует dev-only
`scripts/trino_evidence_package_requirements.py`: helper печатает требования
Trino evidence package прямо из Python-контракта: safe package/source-type
labels, fixture contract/version labels, redaction/rejection classes, sentinel
tests, boundary assertions и size limits. Он не читает Trino endpoint, не
является installed product CLI и не создает Trino support claim.
Английский `0.6.0` фиксирует dev-only
`scripts/build_trino_evidence_handoff_suite_manifest.py` и
`scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest`: retained
Trino evidence-package handoff summaries можно группировать и проверять без
повторного открытия packages. Suite принимает только raw-free
`trino_evidence_handoff_summary_v1` с accepted package/boundary/readiness
pipeline, может писать raw-free machine summary, reject-ит output/input overlap
и не печатает paths, filenames, package payloads, SQL, URLs, Query IDs или
support claim.
Английский `0.6.0` фиксирует dev-only
`scripts/spark_evidence_package_requirements.py`: helper печатает требования
Spark evidence package прямо из Python-контракта: safe case labels,
source-contract labels, diagnostic signal groups, redaction classes, sentinel
tests и boundary assertions. Он не читает Spark endpoint, не является
installed product CLI и не создает Spark support claim.
Английский `0.6.0` фиксирует `--application-attempt-id` для Spark
History Server compact intake: selector поддержан в installed collector,
isolated compact web page и dev-only one-application handoff wrapper. Он
используется только в bounded request paths и не записывается в compact output,
diagnosis output, boundary facts, terminal output или browser results.
Английский `0.6.0` фиксирует optional `--summary-json` для Spark
one-application handoff: wrapper пишет raw-free
`spark_one_application_handoff_summary_v1` с collection counters, safe warning
IDs, no-support boundary labels, artifact-write states и nested compact
readiness summary, reject-ит output overlap и не пишет paths/selectors/raw
values/support claim.
Английский `0.6.0` фиксирует, что Spark one-application retained
suite manifest может ссылаться на matching
`spark_one_application_handoff_summary_v1`; readiness gate проверяет такой
summary на raw-free/path-free status-ok evidence, те же strict requirements,
source-coverage counters, warning IDs и no-support boundary labels.
Английский `0.6.0` фиксирует, что browser/log host redaction
использует linear token scanner для free-text FQDNs, host-like single-label
names и bare `host:port` values вместо regex substitutions с backtracking
risk. Stable host aliases сохраняются, safe filenames и version-like tokens не
скрываются.
Английский `0.6.0` фиксирует, что Spark compact diagnosis добавляет
safe task-duration bucket counts в `runtime_context`, когда accepted compact
facts их предоставляют. Это только aggregate context values: без Spark
root-cause claims, shared facts, Details/trusted-report output, optimizer
behavior или Spark product support.
Английский `0.6.0` фиксирует Spark compact evidence-package
readiness verdict: safe summary, optional `--summary-json` и
`--require-promotion-candidate` gate различают `partial_evidence`,
`minimum_case_set_ready` и `promotion_candidate` без echo package paths, sample
paths или payload values. Package builder теперь может применить тот же
promotion-candidate gate до записи output, fixture-ready compact sample export
требует тот же gate перед записью deterministic safe files плюс safe export
manifest, а Spark compact readiness audit теперь может читать этот manifest и
проверять safe filenames, sample count и source-contract alignment до аудита
перечисленных compact JSON files. Local Spark evidence handoff audit теперь
собирает package validation, temporary fixture export, manifest-driven readiness
audit и cleanup temporary output в один path-free strict gate. Package
validation также reject-ит per-sample compact diagnosis boundary drift,
сохраняя experimental / no-support и no-root-cause boundary для Spark. Handoff
audit теперь может писать optional raw-free `--summary-json` с
machine-readable readiness evidence без path echo.
Английский `0.6.0` фиксирует, что Spark evidence-package
`promotion_candidate` readiness требует diagnostic signal-group breadth по data
movement, failure, runtime context и adaptive plan context. Одних complete case
labels больше недостаточно для promotion-ready package; raw-free summaries
показывают missing signal groups только как safe blocker IDs и не меняют
Spark no-support boundary.
Английский `0.6.0` фиксирует, что Spark evidence-package summaries,
readiness JSON, compact readiness suite output и strict handoff summary JSON
добавляют safe `source_warning_counts` по allowlisted Spark warning ID рядом с
общим warning count. Это делает warning-driven promotion blockers понятнее без
History Server endpoints, file paths, raw logs, SQL text или изменения Spark
no-support boundary.
Английский `0.6.0` фиксирует registered bounded compact Spark
engine adapter для Spark History Server compact-intake CLI, compact
evidence-package validation/export и raw-free compact diagnosis. Default
production triage engine остается Impala; Spark adapter не включает Recent
scans, Query ID product diagnosis, metadata collection, Details/trusted
reports, optimizer behavior, raw event-log handling, raw SQL/plan display,
environment/log dumps или Spark job execution.
Английский `0.6.0` фиксирует
`scripts/audit_spark_support_boundary.py`: static Spark support-boundary audit
держит Spark adapter compact-only, Spark CLI roles, README/support-matrix
wording и Details/report/optimizer/recent imports ниже production support до
любого расширения Spark product exposure.
Английский `0.6.0` фиксирует dev-only retained-suite gate для
Spark evidence handoff: `scripts/build_spark_handoff_suite_manifest.py`
собирает local `spark_evidence_handoff_suite_v1` manifest поверх уже raw-free
handoff summary JSON, а `scripts/audit_spark_evidence_handoff.py
--handoff-suite-manifest` проверяет retained summaries и optional raw-free
suite summary JSON без чтения Spark, повторного открытия packages, печати
artifact paths, product surfaces или расширения Spark support за пределы
compact-only adapter.
Английский `0.6.0` фиксирует, что Spark compact readiness audits
могут писать optional raw-free `spark_compact_readiness_summary_v1` JSON через
`--summary-json`, включая one-application handoff-suite mode. Summary содержит
только schema/mode/status labels, strictness requirements, no-support boundary
labels, aggregate counters, source-contract counts и safe issue
categories/messages, а output path не может совпадать с input artifacts.
Английский `0.6.0` фиксирует, что Spark compact readiness suites
могут требовать raw-free Spark version-family breadth через
`--require-min-spark-version-families` и повторяемый
`--require-spark-version-family`. Audit считает только safe `spark_*` labels из
accepted compact provenance, пишет aggregate counters в
`spark_compact_readiness_summary_v1` и не раскрывает raw Spark version strings,
request selectors, paths или Spark support claim.
Английский `0.6.0` фиксирует, что Spark retained one-application
History Server handoff suites можно передавать в dev-only sanitized
evidence-package builder через
`scripts/build_spark_evidence_package_from_one_application_suite.py`. Bridge
заново запускает compact/diagnosis/boundary suite validation перед сборкой
package wrapper, требует explicit sample-case labels, reject-ит drift и
output/input overlap и не печатает artifact paths, filenames, raw payload
values или Spark support claims.
Английский `0.6.0` фиксирует dev-only one-application wrapper для
Spark live evidence handoff: `scripts/spark_one_application_handoff.py`
связывает bounded History Server summary collection, raw-free compact
diagnosis, optional raw-free boundary export и Spark compact readiness audit
для одного explicit application без установки product CLI, broad crawl, raw
event-log/environment reads, печати selectors/artifact paths или Spark support
claim.
Английский `0.6.0` фиксирует dev-only retained-artifact suite для
Spark one-application handoff: manifest builder группирует raw-free compact,
deterministic diagnosis и engine fact boundary JSON triples, а compact
readiness gate сверяет diagnosis/boundary consistency без повторного открытия
Spark, печати paths/filenames/raw payload values или Spark support claim.
Английский `0.6.0` фиксирует, что Spark History Server compact
executor summaries помечают executor section как `supported`, когда принят
непустой executor summary list. При этом executor-loss, memory, churn и
dynamic-allocation substates остаются независимыми, поэтому partial executor
evidence не backfill-ит fake memory или loss signals.
Agent-facing release instructions теперь pin-ят Spark compact boundary как
experimental research only: без public Spark support, Recent scans,
Details/trusted-report output, optimizer behavior, engine registration, raw
event-log handling, raw SQL/plan display, environment/log dumps или Spark job
execution.
Английский `0.6.0` фиксирует deterministic-first /
no-LLM-capable roadmap posture: core diagnosis, Details, Python reports,
trusted optimizer outcomes, demos и validation должны оставаться полезными при
`no_llm=true`, а LLM-backed wording остается optional selected-case extension.
Следующий UI/Help wording cleanup должен двигаться к нейтральным `Report` /
`Query optimizer` labels без скрытия backend status (`Python-owned`,
`LLM-backed`, `no_llm=true`).
Report validators теперь имеют adversarial EN/RU corpus для indirect
unsupported stale-statistics root-cause wording, soft `COMPUTE STATS`
recommendation wording, row/cardinality estimate-direction wording и integrated
parity coverage для memory estimate direction, backend data skew, primary
bottleneck, CM context-only metrics и CM event context. Trust gate reject-ит
такие unsupported claims до trusted marker, а nearby neutral investigation
wording остается allowed.
Report language handling теперь использует shared report-language registry для
config, web settings и report/pipeline CLI boundaries. Case-insensitive public
keys вроде `RU` нормализуются в `ru`, а unknown languages fail closed до report
generation вместо fallback wording.
Trusted report SQL-like text validation теперь reject-ит inline prose, где
внутри предложения embedded `SELECT`, `WITH`, DML/DDL или metadata `SHOW`
statements. Это закрывает gap, где raw SQL-like text ловился в fenced snippets
или list items, но не в surrounding sentence.
Английский `0.6.0` включает разделение committed public docs и
ignored local agent notes: durable agent baseline остается в public docs,
private continuation notes живут в local exclude-only notes, а
`scripts/audit_public_docs.py` ловит common local handoff markers перед commit.
Английский `0.6.0` также фиксирует Trino offline/local import:
`query-doctor-trino-import` валидирует уже sanitized compact packages, а
`query-doctor-trino-event-store-import` читает один explicit local JSON/NDJSON
event-store файл с redaction-review confirmation. Последующие bounded local
commands добавляют query-detail, query-list aggregate и statement-stats import
для одного explicit already-sanitized compact JSON payload. Эти пути могут
выводить raw-free normalized fact boundary JSON, но live Recent scans, Query ID
fetch, `/v1/statement`, metadata, browser/report, optimizer behavior и
generated Trino SQL остаются неподдержанными.
Добавлен также `query-doctor-trino-event-source-contract-check`: он валидирует
source contract для source type, safe auth-reference label, accepted event
schema, bounds и redaction/storage policy, не читает event records и не
контактирует с Trino coordinator. Добавлен
`query-doctor-trino-http-event-archive-import`: он читает один explicit
operator HTTP(S) archive URL после accepted `http_event_listener_archive`
contract, выводит только safe summary или raw-free boundary JSON, не echo-ит
URL, не принимает URL credentials и не submit-ит SQL.
Добавлен также `query-doctor-trino-http-query-detail-archive-import`: он
читает один explicit operator HTTP(S) archive URL после accepted
`http_query_detail_archive` contract, выводит только safe summary или raw-free
boundary JSON для одного compact sanitized query-detail record, не
контактирует с Trino coordinator, не fetch-ит query-info by Query ID, не
echo-ит URL, не принимает URL credentials и не submit-ит SQL.
Английский `0.6.0` также фиксирует, что Trino network-backed
private-preview readers используют общий configured diagnostic HTTP egress
helper: HTTP event archive, HTTP query-detail archive и one-query pruned
coordinator QueryInfo readers получают shared target validation и no-redirect
behavior без расширения Trino product-support claim.
Добавлен также `query-doctor-trino-coordinator-query-info-target-check`: он
валидирует один compact future `coordinator_query_info` source contract,
coordinator base URL shape и Query ID shape, выводит только safe summary без
URL/Query ID, не контактирует с Trino, не вызывает `/v1/query`, не fetch-ит
query-info JSON и не делает live Query ID diagnosis.
Добавлен также `query-doctor-trino-coordinator-query-info-pruned-probe`: он
валидирует тот же `coordinator_query_info` source contract с
operator-managed auth reference, делает ровно один bounded
`GET /v1/query/{queryId}?pruned=true`, проверяет response как bounded JSON
object и выводит только safe summary. Он не печатает и не хранит URL, Query ID,
raw QueryInfo, query text, session fields, endpoint URLs или object names, не
мапит QueryInfo в facts, не crawl-ит query history, не submit-ит SQL и не
делает browser/report/optimizer output или live Query ID diagnosis.
Pruned coordinator QueryInfo probe/import reads теперь не следуют HTTP
redirects для single bounded `GET /v1/query/{queryId}?pruned=true`, чтобы
explicit coordinator target не расширялся в redirected egress path.
Английский `0.6.0` также фиксирует
`scripts/trino_one_query_live_handoff.py`: dev-only wrapper для real-cluster
one-query handoff. Он запускает существующий pruned coordinator QueryInfo
import, пишет raw-free boundary и compact diagnosis JSON, сразу применяет
strict one-query/source-version/diagnosis readiness audit и optional
executed-smoke check, но не печатает coordinator URL, Query ID, auth header,
raw QueryInfo, output paths или filenames. Это не installed product CLI, не
live Query ID workflow, не Details/trusted-report surface, не optimizer
workflow и не support claim.
Dev-only Trino one-query handoff wrapper теперь может писать
`trino_product_surface_boundary_audit_v1` summary из retained
boundary/diagnosis artifacts. Это привязывает real-cluster handoff evidence к
no-product-surface gate без live Query ID diagnosis, Details/trusted reports,
optimizer behavior или support claim.
Trino product-surface boundary audit теперь может читать
`trino_one_query_handoff_suite_v1` manifest напрямую. Retained one-query suites
используют один manifest для strict readiness и no-product-surface evidence,
при этом compact diagnosis artifact обязателен для каждой entry, а manifest
paths, artifact paths, URLs, Query IDs и support claims не попадают в output.
Trino handoff-suite manifests теперь принимают только safe relative `*.json`
artifact references без absolute paths, parent traversal, current-directory
segments или backslashes. Builder и readiness audit reject-ят duplicate
boundary/diagnosis references, чтобы suite-width gates не считали один artifact
несколько раз; shared smoke summary остается разрешенным.
Trino product-surface boundary audit теперь также статически проверяет Python
imports в product-surface web/report/optimizer modules. Guard разрешает только
isolated compact-diagnosis route/page imports и path-free падает, если
Details, trusted reports, optimizer, Recent или другой product module импортит
Trino preview diagnosis code.
Trino compact readiness audit теперь принимает
`--handoff-suite-manifest <manifest.json>` для набора dev-only one-query
handoff results. Manifest с kind `trino_one_query_handoff_suite_v1` ссылается
на raw-free boundary JSON и optional compact diagnosis / smoke-summary
artifacts для каждой entry; strict gates могут требовать diagnosis artifact,
executed all-`ok` smoke summary, one-query granularity, known source version,
supported attention и supported parser coverage для каждой entry. Suite output
остается path-free/filename-free и печатает только aggregate counts плюс safe
issue categories. Тот же audit теперь поддерживает
`--require-min-inputs <n>` для representative handoff width и
`--summary-json <summary.json>` для raw-free machine summary, где
source-version requirements записываются только counts/flags, без
operator-provided values.
Английский `0.6.0` также фиксирует
`scripts/build_trino_handoff_suite_manifest.py`: dev-only local manifest
builder для retained one-query Trino handoff artifacts. Он требует explicit
redaction-review confirmation, пишет `trino_one_query_handoff_suite_v1` с
relative artifact references, поддерживает one shared smoke summary или one per
boundary, reject-ит output/input overlap и печатает только path-free aggregate
counts.
Английский `0.6.0` также фиксирует
`scripts/audit_trino_evidence_handoff.py`: dev-only package-to-boundary
readiness audit для sanitized Trino evidence packages. Он валидирует package,
конвертирует accepted samples в raw-free boundary payloads in memory, запускает
compact readiness suite, может писать `trino_evidence_handoff_summary_v1`, не
печатает paths, raw payloads, SQL или Trino identifiers и не делает support
claim.
Английский `0.6.0` также фиксирует
`scripts/audit_trino_product_surface_boundary.py`: dev-only gate для retained
Trino compact boundary/diagnosis artifacts перед любым product-surface
promotion decision. Он проверяет deterministic diagnosis artifacts, pin-ит
`live_known_query_diagnosis=not_wired`, валидирует, что allowed Trino web/CLI
registry ограничен compact preview surfaces, может писать
`trino_product_surface_boundary_audit_v1` и держит output path-free и
support-claim-free.
Английский `0.6.0` также фиксирует
`scripts/audit_trino_support_gap_matrix.py`: dev-only static gate, который
сверяет Trino fact-family coverage с registered engine-fact namespace и engine
adapter flags. Он может писать raw-free
`trino_support_gap_matrix_audit_v1`, держит product surfaces заблокированными и
ловит accidental promotion Trino в Recent, live Query ID diagnosis,
Details/trusted reports, metadata collection или support claim до broader
support work.
Trino compact readiness audit теперь имеет strict
`--require-one-query-boundary` gate: aggregate `query_list_*` boundaries не
могут засчитываться как one-query Trino diagnosis readiness. Strict handoff
также может передавать `--require-source-version <version>`, чтобы требовать
accepted boundary `identity.source_version` без печати фактического значения.
Он также принимает `--diagnosis-json <raw-free-trino-diagnosis.json>` для
artifact, записанного из той же boundary: audit сравнивает файл с
deterministic compact diagnosis из boundary, reject-ит raw-like diagnosis text и
не печатает local paths или filenames.
Тот же audit теперь принимает dev-only Kerberos/SPNEGO
`trino_smoke_summary.json` через `--smoke-summary`; strict release-facing dry
runs могут добавлять `--require-executed-smoke`, чтобы dry-run plan не считался
executed test-cluster smoke. Strict executed-smoke mode теперь требует, чтобы
каждый smoke check завершился известным status `ok`; planned, failed или
unknown statuses не проходят evidence gate.
Pruned coordinator QueryInfo import теперь поддерживает
`--boundary-out <raw-free-trino-boundary.json>`: direct
`engine_fact_boundary_v1` payload можно записать для local readiness audit без
печати output path; пересечение с source contract, auth-header file или
diagnosis output reject-ится.
`query-doctor-diagnose-trino-compact` теперь может диагностировать один
selected sample boundary из Trino package boundary export, созданного через
`query-doctor-trino-import --format boundary-json`. Multi-sample package
exports требуют `--sample-index <zero-based-index>`, direct boundary JSON
работает без index, а isolated `/trino/compact-diagnosis` page принимает тот
же direct boundary или selected package sample без echo submitted JSON. Raw
payloads, non-Trino boundaries, SQL execution, browser/report output и live
Query ID diagnosis остаются неподдержанными.
Английский `0.6.0` также фиксирует новые open trust-boundary follow-ups:
Query Optimizer prompt-injection framing/guard tests для delimited `INPUT SQL`
и fail-closed regression coverage для trusted-output validation modes,
browser/trusted markers и defensive web fallback handlers.
Дополнительно английский `0.6.0` фиксирует defense-in-depth follow-ups:
adversarial redaction corpus для free-text host/secret variants в local/log/
browser fallback surfaces и pathological-within-cap regression coverage для
regex resource-bound paths.
English `0.6.0` также добавляет explicit ignore coverage и staged
public-safety guards для generated staging directories: `.replace-*`,
`.query-refresh-*` и `.cm-timeseries-refresh-*` теперь защищены и вне
default corpus roots.
Также добавлены route-level traversal/symlink guards для batch и Specific Query
report export routes: encoded path-shaped IDs не выбирают case, symlinked
reports outside case dir остаются hidden, а fixed markdown download filenames
остаются pinned.
Committed text fixtures under `tests/fixtures/` теперь проходят dedicated
public-release provenance pytest scan, так что новые fixture families должны
оставаться synthetic, example-only или явно redacted.
README screenshot provenance теперь machine-checkable через
`docs/assets/readme-screenshot-provenance.json`: manifest связывает public
README screenshots с synthetic demo pack, documented capture route, viewport,
README usage и PNG dimensions.
Также английский `0.6.0` фиксирует release-hygiene follow-up: перед public
branch handoff merge-heavy local history должна быть очищена в semantic review
commits. Package version metadata уже использует `pyproject.toml`
`[project].version` как canonical source для legacy `setup.py` shim.
Round-2 audit follow-ups теперь тоже зафиксированы public-safe: report
validators требуют adversarial coverage для indirect unsupported claims,
browser display должен скрывать model/runtime
fingerprints, generated case staging dirs требуют explicit ignore coverage, а
traversal/symlink artifact guards должны быть pinned tests. Subprocess output
capture follow-up из этого audit реализован в английском `0.6.0`;
остальные пункты остаются open hardening work.
English `0.6.0` также фиксирует shared outbound egress policy,
false-positive-calibrated redaction для safe table/pool/file identifiers,
browser model-name redaction для `gpt-4`/`gpt-4o` variants и context-only
resource-trace fallback без primary-bottleneck promotion.
Report validators теперь reject-ят soft English stats-maintenance overclaims,
где stats refresh/maintenance заявлены как fix, reason или explanation.
Trusted report markers теперь bind-ятся к current marker schema version и
reject-ят missing/stale schema markers before browser display.
Public docs дополнительно сокращены: validation log, model route protocol,
code/analyzer audits, repository-hardening, architecture и smoke docs больше не
публикуют local run journals, model bake-off tables, real-looking case IDs,
private connectivity commands, generated output paths или detailed maintainer
evidence.
Английский `0.6.0` также включает документационный baseline pass для
опубликованного релиза `0.4.0`, проверку актуальности README screenshots и
обновление русской документации: все текущие английские Markdown-документы имеют русскую
сопроводительную страницу, а русская навигация фиксирует правила терминологии.
Synthetic demo pack расширен с трех до одиннадцати cases: теперь он начинается
с Workloads / Action Queue и покрывает optimizer recommendations, stats
maintenance, rejected optimizer draft, admission/runtime workload regression,
Storage/HDFS runtime follow-up, frequent short workload, mixed diagnostic
signals, unknown-but-useful limited evidence, direct Impala compatibility и
local synthetic action outcomes без LLM, network, Cloudera Manager, Impala или
private artifacts.
Trusted optimizer `no_rewrite` и recommendations-only outcomes теперь прямо
объясняют no-draft boundary: это manual review guidance, а не trusted SQL
draft; перед claim о пользе нужно сравнить EXPLAIN и comparable rerun.
Optimizer roadmap / validation log / code audit / handoff / agent playbook
теперь фиксируют candidate-calibration baseline и правило следующего среза:
сначала raw-free funnel/shape audits, затем no-draft guidance, fixtures или
Python-owned recipe только при доказанном validation boundary.
Добавлен Trino test-cluster evidence export checklist: он описывает первый
operator-exported sanitized handoff package для будущих real-cluster fixtures
без live collector, engine selector, browser/report surface или claims о
поддержке Trino. Добавлены Trino evidence package templates для manifest и
redaction note: они фиксируют safe package labels, redaction assertions и
fixture-only acceptance gate без live collector, UI/report surface или public
support claim.
Добавлен Trino private-preview release path для closed test-cluster работы:
runbook фиксирует allowed/forbidden release wording, dev-only Kerberos/SPNEGO
smoke, sanitized evidence-package intake и release gates, сохраняя Apache
Impala единственным production engine support.
Current-upstream Impala smoke в английских docs теперь описан generic direct
Impala placeholders и follow-up gates для будущего усиления wording по
поддержке актуальной Impala без hostnames, local config, target selectors,
query IDs, raw profiles, generated case paths или smoke artifacts.
Добавлен repeatable fixture-only Trino evidence-package walkthrough для
committed synthetic fixtures. Локальная demo-команда собирает и валидирует
package shape, может опционально записать sanitized demo package и печатает
только path-free safe summary без live collection, SQL execution, credential
access, engine registration, UI/report output, optimizer behavior или support
claims.
Добавлен fixture-only Trino evidence package builder для already-sanitized
compact sample JSON files. Локальный script собирает package wrapper, требует
explicit redaction-review и sentinel-test confirmations, validates before
writing output и печатает только path-free safe summaries без live collection,
engine registration, UI/report output, optimizer behavior или support claims.
Добавлен локальный Trino evidence package validator script:
`python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>`
проверяет fixture-only package intake gate и печатает только safe package /
manifest source summary или safe rejection message, без raw payloads, file
paths, raw values, SQL text, identifiers, hostnames, object names, connector
details или rejected record contents. Package wrapper теперь reject-ит
unsupported top-level sections.
Добавлен fixture-only Trino evidence package intake validator: локальный
sanitized wrapper `manifest` / `redaction_note` / `samples` fail-closed
проверяет safe package labels, redaction assertions, sentinel-test coverage,
declared bounds, sample counts, raw-free payloads и существующие
statement-statistics/event-listener fixture validators без live Trino
collection, engine selector, UI/report output или support claim.
Добавлен dev-only Trino Kerberos/SPNEGO smoke script: он использует `curl` с
явным Kerberos service name, выполняет только built-in read-only smoke
statement shapes, следует bounded Trino protocol pages и пишет safe summary без
statement text, result values, query identifiers, actor identity values,
coordinator hostnames, object names или raw failure details. Скрипт не
подключен к product workflows Query Doctor и не добавляет live Trino
collection, engine selector, UI/report output, optimizer behavior или support
claim.
Также добавлен raw-free offline audit для profile evidence gates на существующих
Recent `batch_summary.json`, а analyzer теперь выводит context-only Resource
Trace Facts для безопасных агрегатов CPU, диска и сети из профиля Impala без
primary-bottleneck promotion. Fixture-only Trino event-listener coverage теперь
также включает compact resource-group queue-delay event без live reader,
browser/report surfaces или claims о поддержке Trino. Добавлен unknown
source-contract event gate: неподдержанный compact source contract оставляет
parser coverage и факты в `unknown`.
Compact summary shapes для Trino connector metric, failure category и stage
skew теперь остаются `unknown`, если присутствуют extra fields или nested
details.
Дополнительно tightened statement-stats fixture intake: oversized payloads,
unsafe raw field names и unsafe text values теперь reject-ятся до mapping.
JSON shape guards для Trino fixtures теперь явно покрывают nested
objects/arrays и maximum-depth rejection до mapping.
Non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) теперь reject-ятся
до mapping для statement-stats и event-listener fixtures.
Отрицательные Trino timing/resource/count values теперь остаются `unknown`
вместо supported facts или fake zeros.
