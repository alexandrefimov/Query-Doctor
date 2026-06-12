# Чеклист evidence из тестового Spark-кластера

Last reviewed: 2026-06-05

Язык: [English](../../spark-test-cluster-evidence-checklist.md) | Русский

Этот чеклист задает первый безопасный handoff из тестового Spark-кластера или
операторского Spark History Server в исследовательский контур Query Doctor. Это
не объявление live Spark support, не engine selector, не Recent workflow, не
Details/trusted-report surface, не optimizer path и не разрешение запускать
Spark jobs или Spark SQL через Query Doctor. Изолированная Spark
compact-diagnosis page остается experimental surface для одного explicit
History Server application или уже accepted raw-free compact JSON.

Используйте этот документ вместе с
[spark-architecture-spike.md](spark-architecture-spike.md),
[engine-support-gap-matrix.md](../../../engine-support-gap-matrix.md),
[engine-expansion-plan.md](../../../engine-expansion-plan.md) и
[test-matrix.md](../../../test-matrix.md).

## Цель

Перейти от synthetic Spark fixtures к representative operator-reviewed compact
evidence без изменения product support claim. Первый реальный evidence set
должен показать, можно ли существующие Spark History Server и event-log-derived
summaries свести к accepted raw-free compact contract и получить полезные
детерминированные attention areas.

Для этого не нужен live query execution. Нужен bounded read-only сбор или
operator export уже существующего application evidence.

## Жесткие границы

- Не запускать Spark jobs, notebooks, `spark-submit`, user SQL или optimizer
  SQL.
- Не запускать Query Doctor-generated `EXPLAIN`, `EXPLAIN ANALYZE` или Spark
  SQL plans.
- Не использовать broad History Server crawls, application discovery или
  unbounded time-window collection как первый evidence path.
- Не получать, не коммитить, не прикладывать, не вставлять в prompts и не
  рендерить raw Spark event logs, raw Web UI pages, raw SQL descriptions,
  physical plans, driver logs, executor logs, stack traces, environment dumps,
  classpaths, command lines или raw task/executor records.
- Не включать application IDs, attempt IDs, SQL execution IDs, job IDs, stage
  IDs, task IDs, executor IDs, users, principals, hostnames, endpoint URLs,
  object-store paths, local paths, artifact names, table names, column names,
  secrets, credentials, tokens или Kerberos/TLS material.
- Не использовать evidence set для расширения Spark registration за пределы
  compact-only adapter, Recent scan support, Details/trusted reports,
  optimizer behavior, README support claims или package metadata claims.

## Первый допустимый evidence

Первый evidence set должен содержать только compact evidence:

- compact Spark History Server summaries для одного explicit application,
  собранные через `query-doctor-collect-spark-history`;
- optional compact summaries для одного explicit SQL execution selector, если
  оператор знает selector и он не записывается в output;
- compact event-log-derived summaries, которые уже соответствуют
  `spark_history_eventlog_compact_v1`;
- raw-free engine fact boundary JSON из collector или mapper;
- deterministic Spark compact diagnosis JSON из accepted compact payload,
  включая raw-free `spark_compact_diagnostic_lane_v1` diagnostic-lane contract;
- manifest только с safe categories: source kind, Spark version family, source
  contract, collection time-window category, record counts, byte bounds,
  redaction status и known omissions;
- redaction note, описывающий классы удаленных полей, а не удаленные значения.

History Server collection должен оставаться explicit-application, summary-only,
bounded per endpoint, redirect-disabled и target-guarded. Private или loopback
History Server targets требуют explicit local opt-in и не должны попадать в
committed docs или prompts.

## Минимальный набор кейсов

Подготовьте минимальный безопасный representative set:

- finished Spark SQL application с accepted SQL execution linkage;
- application-only collection, где query linkage равно `same_application`;
- failed или killed application только с allowlisted safe failure category;
- missing или partial History Server endpoint coverage;
- unknown Spark version или unsupported source contract;
- spill observed;
- shuffle-heavy или data-movement-heavy stage summary;
- stage или task skew candidate;
- failed stage или failed task aggregate;
- retried task aggregate;
- long SQL elapsed-time context;
- over-one-minute task duration bucket context;
- scheduler-delay context, когда каждый selected stage summary имеет explicit
  safe value;
- adaptive execution checked enabled и checked disabled;
- dynamic allocation observed и unknown;
- executor loss или executor churn aggregate;
- high aggregate executor memory utilization при complete used/capacity values;
- missing stage, task, job или executor summaries, которые мапятся в
  `unknown`;
- oversized или over-deep payload rejection case с synthetic padding only;
- unsafe raw field rejection case с synthetic sentinel values only.

Для Spark-версий, где SQL execution-list endpoint недоступен,
application-only collection может оставаться warning-free, если bounded
application, job, stage и executor summaries читаются. Это состояние
записывается как safe `sql_execution_endpoint` compatibility limitation.
Explicit SQL execution selector строже: unavailable или missing SQL execution
evidence остаётся source warning и не должен claim-ить exact query linkage.

Для Spark-версий, где selected stage summaries читаются, но per-stage
`taskSummary` enrichment недоступен, compact collection может оставаться
warning-free. Это состояние записывается как safe `task_summary_endpoint`
compatibility limitation. Stage skew и task-duration signals должны оставаться
`unknown`, пока accepted stage summaries или task-summary quantiles не дадут
достаточно raw-free evidence.

## Граница readiness evidence

Representative Spark evidence может показать, что bounded one-application
History Server intake остается raw-free и warning-free для compact summaries,
но это остается evidence только для compact intake contract. Это не readiness
для Spark production support, Recent scans, Details/trusted reports, optimizer
behavior, broad live collection, raw event-log reads или fixture promotion.

`same_application` handoff без selected SQL execution может суммировать
readable application-level jobs, stages, scheduler delay, spill и
task-duration context без raw selectors в compact output. SQL-execution
specific timing, failure category и exact query linkage всё еще требуют
accepted SQL execution evidence и остаются `unknown` без него.

Live validation notes, private endpoints, selectors, ports, event-log
locations, output paths и one-run checkpoint details должны оставаться вне
committed docs и prompts. Public docs фиксируют только durable
source-coverage behavior, support boundaries и sanitization requirements.

## Sanitization checklist

Перед тем как файл попадет в repository, issue tracker, prompt или shared
review artifact:

- удалите raw SQL, SQL descriptions, plan descriptions и physical plans;
- удалите application, attempt, SQL execution, job, stage, task и executor
  identifiers;
- удалите users, groups, principals, queues, pools, tags, session labels и
  environment-derived metadata;
- удалите hostnames, endpoint URLs, IP addresses, object-store URIs, local
  paths, classpaths, command lines, package names и artifact names;
- удалите table, database, schema, catalog, column, partition, manifest и file
  names;
- удалите stack traces, raw exception messages, warning payloads, log lines и
  vendor UI internals;
- удалите secrets, credentials, tokens, passwords, keys, cookies, headers, TLS
  material, Kerberos caches и extra auth material;
- замените source-specific detail на compact checked booleans, durations,
  counts, bytes, ratios, safe categories, warning IDs и explicit `unknown`
  states;
- держите compact boolean markers типизированными, особенно adaptive
  execution, dynamic allocation и application/job/stage failure markers;
- reject/regenerate export, если redaction status неизвестен.

## Local validation gate

Перед выбором package sample labels выведите текущий Python-owned requirements
contract:

```bash
python3 scripts/spark_evidence_package_requirements.py --json
```

Helper не читает Spark endpoint, не является installed product CLI и печатает
только safe requirement labels: accepted sample cases, synthetic rejection
cases, required compact source contracts, diagnostic signal groups, redaction
classes, sentinel tests и boundary assertions. Используйте его, чтобы operator
handoff notes оставались согласованы с validator, а не копировали требования
вручную.

Соберите local sanitized evidence package из operator-reviewed compact samples.
Builder требует explicit redaction и sentinel-test confirmations, пишет output
только после успешной validation и не должен echo-ить sample paths или payloads:

```bash
query-doctor-build-spark-evidence-package \
  --out <sanitized-spark-package.json> \
  --package-id <safe_package_label> \
  --prepared-date-utc YYYY-MM-DD \
  --redaction-reviewed \
  --sentinel-tests-passed \
  --require-promotion-candidate \
  --sample finished_sql_exact_linkage:spark_eventlog_compact:<compact-a.json>
```

Опускайте `--require-promotion-candidate` только для early dry runs, которые
также используют `--partial-ok`. Со strict flag builder валидирует тот же
package-level readiness verdict до записи и выходит non-zero без создания
output file, если blockers еще остаются. `promotion_candidate` требует complete
minimum case set, synthetic rejection coverage, оба compact source contracts,
отсутствие source warnings, минимум один `compact_attention_ready`
diagnostic lane и required diagnostic signal groups для data movement,
failure, runtime context и adaptive plan context.

Затем провалидируйте package wrapper перед fixture conversion:

```bash
query-doctor-validate-spark-evidence-package \
  --summary-json \
  <sanitized-spark-package.json>
```

Для early dry runs можно использовать `--partial-ok`, пока minimum case set еще
неполный. Добавляйте `--summary-json`, когда agent или reviewer нужен
machine-readable package readiness verdict. Verdict должен оставаться ниже
Spark support и сообщает только `partial_evidence`,
`minimum_case_set_ready` или `promotion_candidate` с explicit blockers:
missing sample cases, missing synthetic rejection coverage, missing source
contracts, missing diagnostic signal groups, missing supported attention areas,
missing required diagnostic-lane readiness, или source warnings. Machine summary
содержит только safe diagnostic-lane schema, readiness, source-granularity и
required gate counters. Validator печатает только safe summary и не должен
echo-ить package path, sample paths, raw payload values, History Server URLs,
request selectors, SQL, log content или local output paths.

Для строгого package-level gate перед fixture или promotion-gate work добавьте
`--require-promotion-candidate`; command выходит non-zero, если package
readiness verdict не `promotion_candidate`, и при failure печатает только safe
blocker IDs.

Package validation также заново строит deterministic compact diagnosis для
каждого sample и reject-ит diagnosis-boundary или diagnostic-lane drift.
Каждый accepted sample должен сохранять
`support_status=experimental_compact_intake`, `root_cause=not_claimed`,
отсутствие Details/trusted-report surface, отсутствие optimizer behavior,
отсутствие Spark job execution и valid raw-free
`spark_compact_diagnostic_lane_v1` contract с preview-only promotion status,
accepted readiness/source-granularity labels, matching
attention/source-warning и fact-state counters, а также required
readiness/surface gates.

После успешной strict package validation экспортируйте fixture-ready compact
samples с deterministic safe filenames:

```bash
query-doctor-export-spark-evidence-fixtures \
  <sanitized-spark-package.json> \
  --out-dir <fixture-ready-dir>
```

Exporter требует `promotion_candidate` package, пишет только уже
validated compact sample payloads плюс safe
`spark_fixture_export_manifest.json`, fail-ится до overwrite и не должен echo-ить
input paths, output paths, raw filenames, package sample paths, raw payload
values, History Server URLs, request selectors, SQL, log content или local
workspace paths. Manifest содержит только safe labels: schema version,
package ID, readiness status, support-claim boundary, sample count,
deterministic file names, case names, source types и source contracts.

Запускайте Spark compact readiness audit на каждом accepted compact JSON:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  <spark-compact-a.json> <spark-compact-b.json> \
  --require-supported-attention \
  --fail-on-source-warnings \
  --require-min-inputs 2 \
  --require-min-spark-version-families 2 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-contract spark_history_eventlog_compact_v1 \
  --require-spark-version-family spark_2_4 \
  --require-spark-version-family spark_4_1 \
  --require-source-granularity fixture_compact \
  --require-source-granularity exact_sql_execution_compact \
  --require-verification-scope fixture_contract_review \
  --require-verification-scope source_coverage_review
```

После fixture export тот же audit может принимать safe export manifest, чтобы
аудируемые compact files были ровно теми файлами, которые перечислены в
`spark_fixture_export_manifest.json`:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  --fixture-export-manifest <fixture-ready-dir>/spark_fixture_export_manifest.json \
  --require-supported-attention \
  --fail-on-source-warnings \
  --require-min-inputs 2 \
  --require-min-spark-version-families 2 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-contract spark_history_eventlog_compact_v1 \
  --require-spark-version-family spark_2_4 \
  --require-spark-version-family spark_4_1 \
  --require-source-granularity fixture_compact \
  --require-source-granularity exact_sql_execution_compact \
  --require-verification-scope fixture_contract_review \
  --require-verification-scope source_coverage_review
```

Manifest-driven audit валидирует только safe manifest schema, readiness status,
support-claim boundary, sample count, deterministic relative filenames и
source-contract alignment с каждым compact payload перед запуском тех же
readiness checks.
Audit также заново считает compact diagnosis `diagnostic_lane` evidence
readiness, verification scope, fact-state counts и required-gate contract;
missing или drifted lane fields падают до retained handoff use.

Для одного operator-reviewed Spark History Server application dev-only local
wrapper может выполнить bounded summary collection, compact diagnosis, optional
raw-free boundary export и readiness gate как один path-free handoff:

```bash
python3 scripts/spark_one_application_handoff.py \
  --redaction-reviewed \
  --history-server-url <spark-history-server-url> \
  --application-id <spark-application-id> \
  --application-attempt-id <spark-application-attempt-id> \
  --compact-out <raw-free-spark-compact.json> \
  --diagnosis-out <raw-free-spark-compact-diagnosis.json> \
  --boundary-facts-out <raw-free-spark-boundary.json> \
  --summary-json <raw-free-spark-one-application-handoff-summary.json> \
  --product-surface-summary-out <raw-free-spark-surface-boundary-summary-json> \
  --require-supported-attention \
  --fail-on-source-warnings
```

Wrapper остается dev-only local readiness glue поверх того же
explicit-application History Server compact intake. Опускайте
`--application-attempt-id`, если у operator-reviewed application только одна
релевантная попытка или attempt неизвестен; если selector указан, он
используется только для bounded request paths и не записывается в compact
output, diagnosis output, boundary facts или terminal text. Wrapper не
устанавливает product CLI, не crawl-ит applications, не читает raw event logs,
не fetch-ит environment/configuration dumps, не печатает History Server URLs,
application selectors, artifact paths, filenames, raw SQL, plans, logs и не
создает Spark product support claim.

Optional `--summary-json` пишет raw-free
`spark_one_application_handoff_summary_v1` machine summary только со
schema/mode/status labels, collection endpoint counters, safe source warning
IDs, no-support boundary labels, artifact-write states и вложенным
`spark_compact_readiness_summary_v1` payload. Summary path должен отличаться
от compact, diagnosis и boundary output paths. Summary не должен содержать
History Server URLs, application selectors, SQL execution selectors, artifact
paths, filenames, raw values, SQL, plans, logs или Spark support claim.

Optional `--product-surface-summary-out` запускает dev-only Spark
product-surface boundary audit по compact и diagnosis artifacts, записанным тем
же handoff. Он пишет raw-free
`spark_product_surface_boundary_audit_v1` summary, где
`live_known_query_diagnosis=not_wired`, isolated Spark preview route остается
единственной Spark web POST surface, а static Spark support-boundary checks и
Details/trusted report/optimizer/Recent imports остаются blocked.
Он также сохраняет safe diagnostic-lane readiness, source-granularity,
verification-scope и fact-state counters, чтобы no-product-surface evidence
можно было позже проверять без reopening Spark.
Product-surface summary path должен отличаться от compact, diagnosis,
boundary и handoff summary output paths. Summary не должен содержать History
Server URLs, application selectors, SQL execution selectors, artifact paths,
filenames, raw values, SQL, plans, logs или Spark support claim.

Для retained sets of one-application handoff artifacts всегда включайте boundary
output и собирайте local manifest над raw-free compact/diagnosis/boundary
triples. Manifest kind:
`spark_one_application_handoff_suite_v1`:

```bash
python3 scripts/build_spark_one_application_handoff_suite_manifest.py \
  --redaction-reviewed \
  --compact-json <raw-free-spark-compact-a.json> \
  --diagnosis-json <raw-free-spark-compact-diagnosis-a.json> \
  --boundary-facts-json <raw-free-spark-boundary-a.json> \
  --handoff-summary-json <raw-free-spark-one-application-handoff-summary-a.json> \
  --product-surface-summary-json <raw-free-spark-surface-boundary-summary-a-json> \
  --out <spark-one-application-handoff-suite.json>
```

Затем проверяйте retained triples compact readiness gate:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  --one-application-handoff-suite-manifest <spark-one-application-handoff-suite.json> \
  --require-supported-attention \
  --fail-on-source-warnings \
  --require-min-spark-version-families 2 \
  --require-spark-version-family spark_2_4 \
  --require-spark-version-family spark_4_1 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-granularity exact_sql_execution_compact \
  --require-verification-scope comparable_sql_execution_rerun \
  --summary-json <raw-free-spark-one-application-suite-summary.json>
```

Этот suite path проверяет, что каждый retained diagnosis и boundary artifact
по-прежнему совпадает с deterministic compact payload, сохраняет no-support
boundary и печатает или пишет только safe aggregate counters, включая safe
Spark version-family labels и diagnostic-lane readiness/source-granularity/
verification-scope counters при выбранных strict breadth flags. Выбранные
labels из `--require-source-granularity` и `--require-verification-scope`
записываются в summary requirements, а отсутствующие запрошенные labels
отклоняются как path-free readiness gaps. Если manifest
содержит `handoff_summary_json`, audit также проверяет, что retained
`spark_one_application_handoff_summary_v1` artifact raw-free, path-free,
status-ok, создан с теми же strict readiness requirements и совпадает с compact
source-coverage counters и warning IDs. Если manifest содержит
`product_surface_summary_json`, compact readiness audit проверяет, что retained
`spark_product_surface_boundary_audit_v1` artifact raw-free и path-free, а
product-surface boundary audit заново считает per-entry summary, включая
diagnostic-lane readiness/source-granularity/verification-scope и fact-state
counters, и ловит drift в no-product-surface evidence до retained suite use.
Optional `--summary-json`
output пишет raw-free `spark_compact_readiness_summary_v1` machine summary:
schema/mode/status labels, selected requirements, no-support boundary labels,
aggregate counts, diagnostic-lane readiness/source-granularity/
verification-scope counters, fact-state counters и safe issue
categories/messages. Summary path
должен отличаться от manifest и каждого перечисленного compact, diagnosis,
boundary, handoff-summary или product-surface summary artifact. Он не
переоткрывает Spark, не читает raw event logs, не печатает artifact paths или
filenames и не создает product support claim.

Чтобы превратить accepted retained one-application suites в sanitized evidence
package wrapper, используйте тот же manifest и передайте один explicit package
sample case на каждую manifest entry:

```bash
python3 scripts/build_spark_evidence_package_from_one_application_suite.py \
  --handoff-suite-manifest <spark-one-application-handoff-suite.json> \
  --sample-case <spark-evidence-sample-case> \
  --out <sanitized-spark-package.json> \
  --package-id <safe_package_label> \
  --prepared-date-utc YYYY-MM-DD \
  --redaction-reviewed \
  --sentinel-tests-passed \
  --partial-ok
```

Bridge остается dev-only local package-building glue поверх retained raw-free
one-application handoff artifacts. Он сначала заново запускает
one-application suite audit, требует History Server compact source contracts,
reject-ит diagnosis/boundary drift, reject-ит SQL-specific sample-case labels,
если compact payload не содержит accepted `exact_query` SQL execution evidence,
затем собирает и валидирует sanitized package wrapper без печати manifest path,
compact/diagnosis/boundary artifact paths или filenames, package output path,
raw payload values, History Server URLs, request selectors, SQL, logs или
Spark support claim. Добавляйте
`--require-promotion-candidate` только когда retained suite и выбранные case
labels должны закрывать полный package promotion gate.

Чтобы запустить strict local handoff одним gate поверх уже sanitized package:

```bash
python3 scripts/audit_spark_evidence_handoff.py \
  <sanitized-spark-package.json> \
  --summary-json <raw-free-spark-handoff-summary.json>
```

Для early dry runs добавляйте `--partial-ok` только когда sanitized package
ожидаемо остается неполным. Audit тогда использует partial-evidence package
contract, пишет rejected raw-free blocker summary при наличии `--summary-json`,
не запускает fixture export и по-прежнему не печатает package paths, raw values,
request selectors и не создает Spark support claim. Для promotion-candidate
handoff gates не используйте `--partial-ok`.

Handoff audit требует `promotion_candidate` package, экспортирует fixture-ready
compact JSON во temporary directory, аудирует сгенерированный
`spark_fixture_export_manifest.json`, требует supported Spark attention и оба
accepted compact source contracts, fail-ится на source warnings, удаляет
temporary export на выходе и не должен echo-ить package paths, temporary paths,
manifest filenames, compact filenames, raw payload values, History Server URLs,
request selectors, SQL, log content или local output paths.

Optional `--summary-json` output пишет raw-free machine-readable handoff
readiness summary: только schema/mode/status labels, pipeline stage states,
no-support boundary labels, selected requirements, aggregate counts, safe
counters, diagnostic-lane
checked/readiness/source-granularity/verification-scope, fact-state counters и
safe issue categories/messages. Summary path должен
отличаться от package input. Audit должен печатать или писать только safe
aggregate counts и не должен echo-ить compact input paths, raw filenames, raw
payload values, History Server URLs, request selectors, SQL, log content или
local output paths. Manifest-driven audit также не должен echo-ить manifest
filenames. Retained suite audit reject-ит handoff summaries, которые не
доказывают diagnostic-lane check для каждого compact input, не сохраняют
required `compact_attention_ready` readiness counter, не сохраняют accepted
diagnostic-lane source-granularity counters, не сохраняют accepted
verification-scope counters, не satisfy-ят каждый selected
`--require-source-granularity` и `--require-verification-scope` label или
теряют fact-state counters. Retained suite summary сохраняет selected
source-granularity и verification-scope requirements и пишет missing requested
labels как path-free readiness gaps.

Raw exports держите вне repository и вне prompts. Если оператору нужно
сохранить raw event logs или History Server exports для аудита, они должны
оставаться внутри operator-controlled Spark environment, а не в Query Doctor
workspace artifacts.

## Acceptance gate

Evidence set готов для Query Doctor fixture или promotion-gate work только
когда:

- каждый sample вручную проверен как raw-free;
- каждый sample укладывается в maximum size, response и nested-depth bounds
  compact contract;
- каждый supported fact является query-linked, application-linked или явно
  context-only;
- каждый unsupported, absent, partial или intentionally redacted field имеет
  explicit `unknown`, warning ID или omission reason;
- `query-doctor-build-spark-evidence-package` собирает sanitized package
  wrapper из compact samples с `--require-promotion-candidate` без печати paths
  или raw values;
- `query-doctor-validate-spark-evidence-package` принимает тот же wrapper без
  печати paths или raw values с `--require-promotion-candidate`;
- readiness verdict сообщает required diagnostic signal groups по data
  movement, failure, runtime context и adaptive plan context, а не только
  complete case labels;
- diagnosis каждого sample сохраняет explicit no-support/no-root-cause
  boundary;
- `query-doctor-export-spark-evidence-fixtures` экспортирует fixture-ready
  compact samples и safe manifest без печати paths или raw values;
- `scripts/audit_spark_compact_readiness.py` проходит по compact sample suite
  из explicit compact JSON inputs или `--fixture-export-manifest` без печати
  paths или raw values;
- `scripts/spark_one_application_handoff.py` может прогнать один
  operator-reviewed explicit History Server application через bounded compact
  collection, raw-free compact diagnosis, optional raw-free boundary export,
  readiness audit и optional product-surface summary audit без печати URLs,
  application selectors, artifact paths, filenames, raw values или расширения
  Spark support;
- retained one-application compact/diagnosis/boundary triples можно
  сгруппировать через
  `scripts/build_spark_one_application_handoff_suite_manifest.py` и проверить
  через
  `scripts/audit_spark_compact_readiness.py
  --one-application-handoff-suite-manifest --summary-json
  <raw-free-spark-one-application-suite-summary.json>` без переоткрытия Spark,
  печати artifact paths или filenames, записи paths или filenames в summary,
  при этом optional retained `product_surface_summary_json` refs защищены от
  summary overwrite и сверяются через
  `scripts/audit_spark_product_surface_boundary.py` без раскрытия raw Spark
  version strings или расширения Spark support;
- accepted retained one-application suites можно преобразовать в sanitized
  package wrappers через
  `scripts/build_spark_evidence_package_from_one_application_suite.py` только
  после принятого suite audit на compact/diagnosis/boundary consistency, без
  печати artifact paths, filenames, package output paths, raw values или
  расширения Spark support; SQL-specific sample-case labels требуют accepted
  `exact_query` SQL execution evidence и не могут claim-иться из
  `same_application` application-level handoffs;
- `scripts/audit_spark_evidence_handoff.py` проходит по sanitized package без
  печати package paths, temporary export paths, manifest filenames, compact
  filenames или raw values; для early incomplete packages
  `--partial-ok --summary-json` может сохранить rejected raw-free blocker
  summary без запуска fixture export;
- retained raw-free handoff summaries можно сгруппировать через
  `scripts/build_spark_handoff_suite_manifest.py` и проверить через
  `scripts/audit_spark_evidence_handoff.py --handoff-suite-manifest` без
  печати summary paths или расширения Spark support;
- `scripts/audit_spark_support_boundary.py --summary-json
  <raw-free-spark-support-boundary-summary-json>` может retain-ить raw-free
  `spark_support_boundary_audit_v1` summary только с boundary labels, check
  statuses, safe counts и safe issue categories/messages перед любым Spark
  product-exposure decision, без печати summary path или расширения Spark
  support;
- не нужно расширять Spark registration за пределы compact-only adapter,
  Recent workflow, Details route, trusted report, optimizer behavior, public
  README support claim или package metadata support claim.

Следующий шаг после accepted evidence set все еще fixture и readiness work:
перевести compact samples в committed sanitized fixtures, mapper tests и
diagnosis tests. Product support идет позже, после закрытия support gates из
engine expansion plan и support gap matrix на representative evidence.
