# Архитектурный spike Spark

Last reviewed: 2026-06-04

Язык: [English](../../spark-architecture-spike.md) | Русский

Английская версия является канонической. Эта страница - краткое русское
резюме исследовательского контракта Spark.
Для перехода от synthetic fixtures к operator-reviewed Spark History
Server/event-log evidence используйте
[spark-test-cluster-evidence-checklist.md](spark-test-cluster-evidence-checklist.md).

## Статус

Spark не является текущим поддерживаемым движком Query Doctor. Этот документ
описывает исследовательский architecture/fact-model spike, чтобы не переносить
Impala-предположения на Spark.

Текущий уровень: `research`.

Разрешено: source/evidence contract docs, compact synthetic fixture schema,
raw-field denylist, proposed fact envelope, bounded compact Spark History
Server summary intake для explicit applications, isolated direct
compact-diagnosis page для одного explicit History Server application или уже
accepted raw-free compact JSON и тестовый план для `supported`,
`not_observed`, `unknown` и `unsupported`.

Не разрешено: запуск Spark jobs, `spark-submit`, notebooks, user SQL,
Query Doctor-generated `EXPLAIN`, live Spark History Server collection по
умолчанию или broad application crawl, engine registration, product browser
workflows, Details pages, trusted report output, optimizer behavior или UI
selector, который выглядит как поддержка Spark.

## Крупный план

Это публичный durable plan для Spark-направления. Он фиксирует цели, а не
текущее состояние веток или локальные handoff notes.

1. Research contract and public boundaries: зафиксировать, что Spark остается
   research-only без product collector, engine registration, primary UI path,
   Details/trusted report surface, optimizer behavior или support claim.
   Experimental compact History Server intake и isolated compact-diagnosis page
   остаются ниже product support.
2. Compact fixture schema and validation: добавить compact synthetic schema для
   application, SQL execution, job, stage, task, executor, data movement и
   limitations, плюс tests для rejection unsafe raw fields.
3. Fixture-only fact envelope: маппить compact fixture в raw-free Spark-specific
   facts только после того, как schema явно поддерживает `supported`,
   `not_observed`, `unknown` и `unsupported`. Текущий mapper остается
   fixture-only, переводит source-only `unsupported` markers в boundary-safe
   limitation facts и не добавляет collector, UI, reports, optimizer behavior
   или support claim.
4. Shared fact coordination: текущий coordination slice оставляет общий слой
   узким: envelope, diagnostic states, lifecycle fields, raw-free boundary и
   explicit fact namespace registry. Spark stage/task/shuffle/executor facts
   остаются `spark_*` и engine-specific; похожие attention signals
   связываются aliases, а не общими counters.
5. Promotion gate: experimental local Spark intake сейчас существует как
   bounded compact History Server summary collector и isolated direct
   compact-diagnosis page для одного explicit History Server application или
   accepted raw-free JSON. History Server collector uses the shared no-redirect
   egress policy with strict public target default и требует explicit CLI/web
   opt-in для loopback, RFC1918, carrier-grade NAT или unique-local targets.
   Shared egress target-policy violations stay fail-closed at the Spark
   collector boundary instead of optional endpoint warnings; DNS failures use a
   generic safe error. Он принимает
   application lifecycle, attempt state и attempt counts только bounded summary
   form, плюс aggregate job-state counts без job IDs, explicit checked adaptive
   execution booleans из SQL summaries без raw plan text, retried-task counts
   только из explicit aggregate retry fields в selected stage summaries, stage
   linkage через SQL-linked job IDs или parser-local job-linked stage IDs без
   записи raw IDs, aggregate runtime/task-time quantiles для skew context без
   raw task lists, executor loss/churn aggregates без executor IDs и explicit
   dynamic-allocation markers, когда executor summary их предоставляет; missing
   application
   endpoints остаются warning/unknown, Spark version strings сводятся к safe
   version-family labels, а dynamic allocation остается unknown без checked
   compact marker. Source coverage хранится только как allowlisted warning IDs
   без endpoint URLs, selectors, raw errors или response payloads; explicit SQL
   execution selector miss тоже записывается только как safe warning ID.
   Product support все еще требует parser/redaction tests, source bounds,
   provenance, browser/report safety tests и
   design-partner workload.
6. Compact readiness audit: локальный
   `scripts/audit_spark_compact_readiness.py` проверяет уже accepted compact
   JSON без вывода input paths или raw payload fragments. Audit также умеет
   aggregate suite mode для нескольких compact inputs в одном безопасном
   запуске, strict minimum input count и required source-contract coverage.
   Он фиксирует, что compact diagnosis остается `root_cause=not_claimed`,
   `support_status=experimental_compact_intake`, без Spark job execution и без
   shared-scope Spark facts; engine-specific Spark facts должны оставаться
   `spark_*`. Тот же test file держит guard против импортов Spark compact
   modules в Details, trusted report, Recent и optimizer surfaces до отдельного
   promotion slice.

## Главная модель

Spark надо моделировать как application, SQL execution, job, stage, task,
executor, event-history и log-driven систему. Это не Impala runtime profile с
другими именами полей.

Текущий slice доказывает только контракт фактов и safety boundary: compact
raw-free summaries из bounded History Server summary endpoints вместо raw event
logs, raw History Server pages, raw SQL descriptions, physical plans, driver
logs или executor logs.

Те же compact facts могут питать deterministic local compact-diagnosis JSON и
isolated direct web page. Страница может собрать summary-only History Server
JSON для одного explicit application или принять уже compact JSON summary.
Эти outputs могут содержать endpoint counts, warning IDs, attention areas,
change direction, verification prompts, state counts и explicit limitations,
включая high aggregate executor memory utilization только когда aggregate
executor memory used/capacity facts supported и utilization high, Spark-specific
Spark version family, query linkage, application lifecycle/attempt state,
adaptive execution enabled, dynamic allocation observed, aggregate input/output
row counts только из complete safe stage summaries, плюс long SQL elapsed-time
context и allowlisted safe failure category как triage context, а не root-cause
claim. Raw exception classes, messages, stack traces, endpoint details, object
names и arbitrary error text остаются rejected или unknown. Они
не должны показывать request selectors или submitted compact JSON, заявлять
root cause, рендериться в Details или trusted reports, добавлять optimizer
behavior или выглядеть как Spark engine support.
Compact diagnosis и isolated Spark compact page могут показывать supported
aggregate input/output rows, bytes, stages, tasks, shuffle, spill и elapsed time
как formatted runtime context. Этот context не является attention signal,
root-cause claim, shared metric, Details/trusted report output или Spark support
claim.

## Непереговорные правила

- Не выполнять Spark jobs, notebooks, user SQL, optimizer SQL или cluster
  actions для диагностики.
- Не хранить, не показывать и не отправлять в prompts raw event logs, raw Web
  UI pages, raw SQL execution descriptions, raw plans, driver/executor logs,
  stack traces, environment dumps, command lines, local paths, object-store
  URIs, hostnames, application IDs, users, principals, secrets или generated
  artifact filenames.
- Missing History Server, event-log, SQL execution, stage, task или executor
  fields должны становиться `unknown`, `not_observed` или `unsupported`, а не
  fake zeros.
- Spark-derived facts не должны попадать в product browser UI или trusted
  reports до parser, redaction, source-bound и browser/report safety tests.

## Возможные будущие источники

Будущие source classes: compact event-log fixture, Spark History Server REST
API, SQL execution summaries, job/stage/task/executor summaries, Structured
Streaming progress, cluster-manager context и vendor UI context.

Raw driver/executor logs остаются unsupported by default. Они могут содержать
SQL, code, paths, endpoints, secrets, stack traces и user data.

## Proposed facts

Первый compact fixture должен предложить Spark-specific envelope:

- `identity`: engine `spark`, support level `research`, source contract,
  version family и parser coverage.
- `provenance`: source family/provider, schema version, window, query linkage,
  freshness, bounds и redaction status.
- `source_capability`: accepted compact source contract и Spark version family
  без raw version strings.
- `source_coverage`: summary endpoint counts и allowlisted warning IDs без
  URLs, selectors, raw errors или payloads.
- `application_lifecycle`: application lifecycle, attempt state и bounded
  attempt count без raw IDs.
- `sql_execution`: execution state, elapsed timing, linked job count,
  plan-shape coverage и adaptive execution state без raw SQL или plan text.
- `jobs_and_stages`: bounded aggregate lifecycle/timing states и aggregate
  job-state counts без job IDs.
- `task_summary`: capped aggregate task counts, failed/retried counts,
  duration buckets и explicit unknowns.
- `data_movement`: shuffle, spill, input/output и skew candidate summaries.
- `executor_context`: executor loss/churn aggregates, explicit allocation
  markers и resource context только при явной source support, linkage и
  freshness.
- `limitations`: unsupported, unknown, redacted, missing, partial и
  source-contract states.

Shared normalized facts нельзя менять из Spark-ветки напрямую. Текущий
coordination slice изменил `query_doctor/analyzer/engine_facts.py` только для
fact namespace registry и cross-engine attention aliases. Если Spark spike
покажет нужные общие поля, их надо вносить отдельной coordination branch с
явным scope и allowed engine set.

## Первая очередь

1. Зафиксировать этот public-safe contract.
2. Добавить compact synthetic fixture schema и validator test для raw-field
   rejection. Текущий slice: `query_doctor/analyzer/spark_fixture_schema.py`,
   `tests/fixtures/engine_facts/spark_history_eventlog_compact.json` и
   `tests/test_spark_fixture_schema.py`.
3. Добавить fixture-only mapper после того, как fixture schema сможет явно
   выразить `supported`, `not_observed`, `unknown` и `unsupported`.
   Текущий slice: `query_doctor/analyzer/spark_fixture_facts.py`,
   `tests/test_spark_fixture_facts.py` и shared engine fact
   boundary/consumer harness tests.
4. Держать shared fact coordination в
   `query_doctor/analyzer/engine_facts.py`,
   `query_doctor/analyzer/engine_fact_consumer.py`,
   `tests/test_engine_fact_contract.py` и
   `tests/test_engine_fact_consumer_probe.py`. Не менять product positioning,
   UI или collector behavior до promotion gates.
5. Запускать Spark compact readiness audit для accepted compact JSON перед
   любым расширением support surface. Текущий slice:
   `scripts/audit_spark_compact_readiness.py` и
   `tests/test_audit_spark_compact_readiness.py`.
6. Держать committed compact fixtures минимум для двух accepted source
   contracts: `spark_history_eventlog_compact.json` и
   `spark_history_server_compact_source_warning.json`. Это позволяет readiness
   audit проверять suite breadth и safe source-warning aggregation без
   generated local payloads.
7. Показывать supported aggregate runtime context только через safe labels и
   formatted values, не продвигая эти Spark-specific facts в root-cause claims,
   shared facts, Details/trusted reports или product support.
8. Держать Spark History Server egress guard включенным через shared
   no-redirect policy: strict public target default, local/private targets only
   with explicit opt-in, target-policy violations fail closed, DNS failures
   generic.
