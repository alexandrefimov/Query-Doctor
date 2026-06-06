# Query Doctor

Last reviewed: 2026-06-03

Язык: [English](README.md) | Русский

Query Doctor - локальный диагностический инструмент для Big Data-запросов,
сфокусированный сегодня на production triage для Apache Impala. Он помогает
операторам ранжировать подозрительные Recent queries, собирать ограниченный
контекст профиля, извлекать детерминированные evidence и генерировать
проверенные отчеты без показа raw SQL или raw profiles в trusted
browser/report surfaces.

Главное правило:

```text
Python owns facts. LLM owns wording only.
```

Recent scan - основной workflow. Диагностика по Query ID вторична и рассчитана
на один известный Impala query. Query Optimizer отдельный, read-only, не
выполняет SQL и не показывает отправленный SQL обратно.

## Что это / что это не

Query Doctor это:

- локальный рабочий инструмент для Impala production triage;
- извлекатель детерминированных diagnostic facts;
- workflow ранжирования Recent queries для операторов и администраторов;
- безопасный генератор отчетов на проверенных фактах;
- практический инструмент для решения, что смотреть, что менять и как
  проверять;
- первый узкий слой диагностики Big Data SQL/lakehouse, где production triage
  engine сегодня - Apache Impala, а для Trino есть ограниченный offline
  evidence import.

Query Doctor это не:

- универсальный AI-чатбот поверх raw profiles;
- замена Impala Web UI;
- инструмент выполнения пользовательского SQL или чернового SQL из optimizer;
- инструмент, который по умолчанию отправляет сырой SQL или данные профилей во
  внешние сервисы;
- оракул первопричин;
- live multi-engine query collector сегодня.

## Что он делает

- Сканирует завершенные Recent queries как основной рабочий процесс; Running
  queries и один explicit Known Query ID остаются сфокусированными вторичными
  режимами для Apache Impala.
- Работает с Cloudera Manager, когда он доступен, или напрямую с Impala daemon
  profile/query-list endpoints для vanilla, Ambari-style и других
  non-Cloudera-Manager кластеров.
- Прямой сбор профилей Impala использует text endpoints как compatibility path
  по умолчанию; JSON profile probing опционален и откатывается к text для
  старых версий Impala. Analyzer facts сохраняют только безопасные capability
  summaries, например выбранный endpoint format и probe status.
- Direct Impala может опционально пробовать ограниченный `/profile_docs/?json`
  для меток стабильности счетчиков с fallback на HTML `/profile_docs`. Query
  Doctor сохраняет только безопасный allowlisted registry context, а не сырую
  документацию счетчиков.
- Direct Impala может опционально собирать ограниченный агрегированный контекст
  `/admission?json`. Отсутствующие старые endpoints не считаются ошибкой, а
  analyzer использует результат только как context, если нет query-specific
  evidence по admission wait/result.
- Опционально собирает ограниченные сводки runtime-метрик Prometheus для direct
  Impala workflows и ограниченные read-only метаданные Impala через
  `impala-shell`.
- Ранжирует подозрительные cases и action candidates по детерминированным
  analyzer facts, а не по LLM scoring.
- Генерирует доверенные отчеты только после детерминированной нормализации,
  очистки и проверки.
- Дает отдельный read-only Query Optimizer workflow для разбора вставленного
  SQL и отдельное Details-page optimizer action для уже разобранных сервером
  случаев.
- Импортирует уже sanitized Trino evidence packages через
  `query-doctor-trino-import`, compact sanitized local event-store records
  через `query-doctor-trino-event-store-import`, compact sanitized operator
  HTTP event archives через
  `query-doctor-trino-http-event-archive-import`, один explicit compact
  sanitized operator HTTP query-detail archive через
  `query-doctor-trino-http-query-detail-archive-import` и один explicit compact
  sanitized local query-detail JSON через
  `query-doctor-trino-query-detail-import`, а также один explicit compact
  sanitized local query-list aggregate JSON через
  `query-doctor-trino-query-list-import` и один explicit compact sanitized
  local statement-stats JSON через
  `query-doctor-trino-statement-stats-import`, плюс один explicit compact
  sanitized local pruned QueryInfo JSON через
  `query-doctor-trino-query-info-pruned-import`, плюс один explicit compact
  sanitized local metadata summary JSON через
  `query-doctor-trino-metadata-summary-import`, затем выводит только safe
  summaries или normalized raw-free fact boundaries.
- Валидирует future Trino event-source contracts через
  `query-doctor-trino-event-source-contract-check`: только source type,
  auth-reference label, schema version, bounds и redaction rules, без контакта
  с Trino и без чтения event records.
- Валидирует future one-query Trino coordinator query-info target через
  `query-doctor-trino-coordinator-query-info-target-check`: compact source
  contract, safe auth-reference label, one Query ID bound, coordinator base-URL
  shape, limits и redaction rules, без контакта с Trino, без query-info fetch и
  без echo URL или Query ID.
- Валидирует future Trino metadata allowlist source contracts через
  `query-doctor-trino-metadata-source-contract-check`: только safe source
  references, explicit relation/column allowlist shape, bounds и redaction
  rules, без контакта с Trino, без чтения metadata, без SQL submit и без echo
  object identifiers.
- Импортирует один compact sanitized local Trino metadata summary через
  `query-doctor-trino-metadata-summary-import` после accepted
  `metadata_allowlist` source contract: мапит только aggregate relation/column
  coverage и stats-completeness counts в raw-free normalized fact boundary. Не
  делает network read, не выполняет metadata SQL и reject-ит raw identifiers
  или metadata values до mapping.
- Проверяет один Trino coordinator pruned query-info endpoint через
  `query-doctor-trino-coordinator-query-info-pruned-probe`: только bounded
  `GET /v1/query/{queryId}?pruned=true` после source-contract gate. Optional
  local `--auth-header-file` может передать одну operator-managed
  `Authorization` header line для bounded read; file path и header value никогда
  не печатаются. Команда не следует HTTP redirects и выводит safe summary без
  URL, Query ID, raw QueryInfo, normalized facts, browser/report output или live
  Query ID diagnosis.
- Импортирует один Trino coordinator pruned QueryInfo response через
  `query-doctor-trino-coordinator-query-info-pruned-import` после той же
  source-contract gate: мапит только allowlisted lifecycle, timing, row/byte,
  memory/spill, blocked и task-count fields в raw-free normalized fact
  boundary. Команда поддерживает тот же optional local `--auth-header-file` для
  одной operator-managed `Authorization` header line и не хранит/не печатает raw
  QueryInfo, не следует HTTP redirects, не раскрывает URL, Query ID, query
  text, session fields, endpoint URLs, object names, stage/task detail, auth
  header paths или values, browser/report output или live Query ID diagnosis.
  Maintainers могут добавить
  `--boundary-out <raw-free-trino-boundary.json>`, чтобы записать direct
  `engine_fact_boundary_v1` payload для strict local readiness audit без echo
  output path.
- Импортирует один compact sanitized local pruned QueryInfo JSON через
  `query-doctor-trino-query-info-pruned-import` после accepted
  `coordinator_query_info` source contract: мапит только allowlisted lifecycle и
  `queryStats` fields в raw-free normalized fact boundary, не делает network read
  и reject-ит raw QueryInfo fields вроде Query IDs, query text, session fields,
  endpoint URLs, object names и stage/task detail.
- Строит deterministic Trino compact diagnosis JSON через
  `query-doctor-diagnose-trino-compact` из уже raw-free
  `engine_fact_boundary_v1` payload, из одного sample boundary, выбранного из
  Trino package boundary export через `--sample-index`, или напрямую из
  accepted single-boundary Trino imports через `--diagnosis-out`.
  `/trino/compact-diagnosis` рендерит тот же diagnosis для direct boundaries
  или selected package samples. Metadata summary boundaries reject-ятся, потому
  что это aggregate coverage evidence, а не compact diagnosis input. Output
  содержит raw-free `diagnostic_lane` summary, attention areas, change
  directions, verification prompts и limitations без root-cause claims, raw
  input echo, browser/report output, optimizer behavior, live Recent scans или
  Trino SQL execution.
- Не показывает сырой SQL, сырые профили, сырые метаданные, локальные пути,
  секреты, subprocess output, model/runtime internals и raw artifact filenames
  в browser и trusted report surfaces.

## Поддерживаемая область

| Область | Поддержано сейчас | Не является текущей поддержкой |
| --- | --- | --- |
| Query engine | Apache Impala production triage; Trino sanitized offline evidence package, bounded local event-store, bounded HTTP event archive, bounded HTTP query-detail archive, bounded local query-detail, bounded local query-list aggregate, bounded local statement-stats import, bounded local pruned QueryInfo import, bounded local metadata summary import, source-contract/target checks, metadata source-contract check, one-query pruned coordinator probe, one-query pruned coordinator fact import, local compact diagnosis из raw-free boundary JSON excluding metadata summary boundaries и isolated `/trino/compact-diagnosis` page | Trino live collection, live Trino Recent scans, live Trino Query ID diagnosis, Trino metadata collection, Trino Details/trusted report output, Trino optimizer behavior или Query Doctor-generated Trino SQL. |
| Trino offline/local import | `query-doctor-trino-import` validates already-sanitized compact packages; `query-doctor-trino-event-store-import` validates compact sanitized local event records; `query-doctor-trino-query-detail-import` validates one explicit compact sanitized local query-detail JSON; `query-doctor-trino-query-list-import` validates one explicit compact sanitized local query-list aggregate JSON; `query-doctor-trino-statement-stats-import` validates one explicit compact sanitized local statement-stats JSON; `query-doctor-trino-query-info-pruned-import` validates one explicit compact sanitized local pruned QueryInfo JSON after a source contract; `query-doctor-trino-metadata-summary-import` validates one explicit compact sanitized local metadata summary JSON after a metadata source contract; all can emit raw-free normalized fact boundaries | Direct Trino coordinator collection, raw event/query-info ingestion, live query-list crawling, `/v1/statement` collection, arbitrary package contents, raw query IDs, raw SQL, stack traces, object names, stage/task detail, raw metadata, raw identifiers или connector internals. |
| Trino compact diagnosis | `query-doctor-diagnose-trino-compact` читает один уже raw-free `engine_fact_boundary_v1` payload excluding local metadata summary boundaries или один selected sample boundary из package boundary export через `--sample-index` и пишет raw-free `diagnostic_lane` summary, deterministic attention areas, change directions, verification prompts и limitations; `/trino/compact-diagnosis` локально рендерит тот же diagnosis для accepted direct boundaries или selected package samples без echo submitted JSON | Raw Trino payload ingestion, metadata summary diagnosis, root-cause claims, Details/trusted report output, optimizer behavior, live Recent scans, live Query ID diagnosis, Query Doctor-generated SQL или arbitrary compact JSON. |
| Trino HTTP event archive import | `query-doctor-trino-http-event-archive-import` validates one explicit `http_event_listener_archive` source contract, fetches one explicit operator HTTP(S) archive URL, enforces contract bounds и emits safe summaries или raw-free normalized fact boundaries | Default network discovery, Trino coordinator query-history reading, URL echoing, credentials in URLs, endpoint/topic/database config ingestion, raw event records, SQL submission, browser/report output или live Recent scans. |
| Trino HTTP query-detail archive import | `query-doctor-trino-http-query-detail-archive-import` validates one explicit `http_query_detail_archive` source contract, fetches one explicit operator HTTP(S) archive URL, enforces contract bounds и emits safe summary или raw-free normalized fact boundary для одного compact sanitized query-detail record | Default network discovery, Trino coordinator query-info fetching, URL echoing, credentials in URLs, endpoint config ingestion, raw query-detail records, raw query IDs, SQL submission, browser/report output или live Query ID diagnosis. |
| Trino source-contract gate | `query-doctor-trino-event-source-contract-check` validates one explicit compact event-source contract JSON: source type, safe auth-reference label, accepted event schema, bounds и redaction/storage policy | Endpoint/topic/database config ingestion, credentials, raw event records, query-history collection, browser/report output или live support claims. |
| Trino coordinator query-info target gate | `query-doctor-trino-coordinator-query-info-target-check` validates one compact future query-info source contract plus one explicit coordinator base URL and Query ID shape, then emits only URL-free and Query-ID-free safe summary | Network reads, query-info fetching, broad query-history collection, URL or Query ID echoing, credentials in URLs, raw QueryInfo JSON, SQL submission, browser/report output, live Query ID diagnosis или support claims. |
| Trino metadata source-contract gate | `query-doctor-trino-metadata-source-contract-check` validates one compact future metadata allowlist contract с safe source references, explicit relation/column allowlist shape, bounds и redaction rules, then emits only path-free and identifier-free safe summary | Metadata reads, metadata SQL execution, broad object crawling, raw identifier output, raw metadata storage, browser/report output, Details/trusted reports, optimizer behavior или support claims. |
| Trino local metadata summary import | `query-doctor-trino-metadata-summary-import` validates one explicit compact sanitized aggregate metadata summary against a `metadata_allowlist` source contract and maps only relation/column coverage and stats-completeness counts into raw-free normalized facts | Network reads, metadata SQL execution, raw metadata, raw catalog/schema/table/column identifiers, metadata values, object crawling, browser/report output, Details/trusted reports, optimizer behavior, live metadata collection или support claims. |
| Trino coordinator pruned query-info probe | `query-doctor-trino-coordinator-query-info-pruned-probe` выполняет один bounded `GET /v1/query/{queryId}?pruned=true` только после accepted `coordinator_query_info` contract с operator-managed auth reference, может использовать один local `--auth-header-file` с `Authorization` header, проверяет response как bounded JSON object и выводит только safe probe summary | Mapping raw QueryInfo to facts, storing or printing raw QueryInfo, URL или Query ID echoing, auth header paths или values, credentials in URLs, broad query-history collection, SQL submission, browser/report output, live Query ID diagnosis или support claims. |
| Trino coordinator pruned query-info import | `query-doctor-trino-coordinator-query-info-pruned-import` выполняет тот же one bounded pruned query-info read, может использовать тот же local `--auth-header-file`, затем мапит только allowlisted `queryStats` и lifecycle fields в raw-free normalized facts и boundary JSON; `--boundary-out` может записать direct raw-free `engine_fact_boundary_v1` payload для local readiness audit | Raw QueryInfo storage/output, URL или Query ID echoing, auth header paths или values, credentials in URLs, query text/session/object/stage/task detail, connector internals, broad query-history collection, SQL submission, browser/report output, live Query ID diagnosis или support claims. |
| Trino local pruned query-info import | `query-doctor-trino-query-info-pruned-import` validates one explicit compact sanitized local pruned QueryInfo JSON against a `coordinator_query_info` source contract and maps only allowlisted `state` and `queryStats` fields into raw-free normalized facts | Network reads, raw QueryInfo fields, Query ID echoing, query text/session/object/stage/task detail, connector internals, broad query-history collection, SQL submission, browser/report output, live Query ID diagnosis или support claims. |
| Spark compact support surfaces | Зарегистрированный bounded compact Spark History Server summary collection для одного explicit application, Spark compact evidence-package build/validation/fixture export плюс local compact-diagnosis CLI/direct web page для raw-free contract shaping | Production Spark triage support, live Recent scans, Details/trusted report output, optimizer behavior, raw event logs, raw SQL/plans, environment/log dumps, Spark job execution или public claim шире bounded compact surfaces; no public Spark engine support. |
| Cloudera Manager | Полный Recent discovery/profile/metrics/events context для Impala workflows | Generic cluster diagnosis вне Query Doctor flow. |
| Direct Impala | Ограниченные Recent scans, Running scans и один Known Query ID через impalad daemon endpoints | Cloudera Manager events, broad log scraping или SQL execution. |
| Runtime metrics | Опциональные ограниченные Prometheus summaries для configured direct Impala workflows | Raw time-series output или arbitrary PromQL from users. |
| Metadata | Read-only allowlisted metadata statements через `impala-shell` | User SQL execution или unbounded metadata crawling. |
| Reports and optimizer | Python-owned facts, validation и explicit selected-case actions | LLM output как trusted evidence или automatic batch LLM jobs. |

Будущие Big Data SQL/lakehouse live collectors, более широкие providers,
подготовленные event/log sources и Cluster Doctor workflows остаются roadmap
seams, а не текущей поддержкой. Trino support ограничен sanitized offline
package import, bounded local event-store import, bounded HTTP event archive
import, bounded HTTP query-detail archive import, bounded local query-detail
import, bounded local query-list aggregate import и bounded local
statement-stats import, bounded local pruned QueryInfo import, а также
bounded local metadata summary import, event-source contract checking, dry-run
coordinator query-info target checking, metadata source-contract checking,
one-query pruned coordinator probe, one-query pruned coordinator fact import и
local compact diagnosis из raw-free boundary JSON; см.
[docs/engines/trino-evidence-package-templates.md](docs/engines/trino-evidence-package-templates.md).

В Apache Impala также появилась upstream работа над native AI query profile
analysis. Query Doctor выравнивается с этим направлением и остается локальным
production triage по многим queries, с детерминированными доказательствами,
безопасным enrichment и проверенными отчетами без сырых данных. См.
[docs/upstream-impala-ai-analyzer.md](docs/upstream-impala-ai-analyzer.md).

## Установка

Установка текущего публичного пакета из PyPI:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install query-doctor
```

Для локальной разработки из checkout:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pre-commit install
```

Локальная JSON-конфигурация описана в
[docs/configuration.md](docs/configuration.md). Предпочтительный путь на
рабочей станции: `~/.qdcreds/query-doctor-config.json`; secrets остаются в
environment variables или local env files.

## Запуск demo

Synthetic demo - самый быстрый способ увидеть продукт. Он deterministic,
local-only и не содержит real SQL, profiles, metadata, hostnames, users или
credentials.

```bash
query-doctor-demo-preflight
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Откройте localhost URL, который напечатает `query-doctor-web`. Начните с
`/?query_group=workloads#workload-action-queue`, чтобы показать Workloads /
Action Queue и local synthetic action outcomes перед открытием workload
Details.

Локальный web UI начинается с ограниченной формы поиска и показывает synthetic
Finished Queries results:

![Synthetic Query Doctor demo search form](docs/assets/demo_search.png)

![Synthetic Query Doctor finished queries results](docs/assets/demo_finished_queries.png)

Synthetic demo pack `0.5.0` содержит eleven sanitized cases: Workloads / Action
Queue, trusted optimizer recommendations, stats maintenance, storage/HDFS
follow-up, frequent-short workloads, mixed signals, unknown-but-useful limited
evidence и direct-Impala compatibility. Полный список scenarios:
[docs/demo-cases.md](docs/demo-cases.md).

## Product scope

| Surface | Current status |
| --- | --- |
| Query engine | Apache Impala is the only production engine support. |
| Cloudera Manager | Full Recent discovery/profile/metrics/events context для Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans и один Known Query ID через impalad daemon endpoints; no Cloudera Manager events и no SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries для configured direct Impala workflows; no arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements через `impala-shell`; no user SQL execution или unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts, validation и explicit selected-case actions; no automatic batch LLM jobs. |
| Trino private preview | Closed test-cluster smoke и sanitized evidence-package artifacts только для maintainers; no public Trino engine support, live collection, browser/report output, optimizer behavior или Query Doctor-generated SQL. |
| Spark compact support surfaces | Registered bounded compact Spark History Server summary intake и compact evidence-package build/validation/fixture export только для raw-free contract shaping; no public Spark engine support, Recent scans, Details/trusted report output, optimizer behavior, raw event logs, raw SQL/plans, environment/log dumps или Spark job execution. |

Будущие Big Data SQL/lakehouse engines, более широкие providers,
подготовленные event/log sources и Cluster Doctor workflows остаются roadmap
seams, а не текущей поддержкой. Текущий support/research boundary:
[docs/engine-support-gap-matrix.md](docs/engine-support-gap-matrix.md).

## Основные workflows

- `query-doctor-web --help`: local browser UI для Recent scan, Running now,
  одного Known Query ID, Details pages, explicit report actions и explicit
  details-page optimizer actions.
- `query-doctor-batch-recent --help`: headless Recent scan для bounded local
  collection и ranking.
- `query-doctor-analyze --help`: deterministic analyzer по collected local case
  files.
- `query-doctor-report --help`: validated report generation из Python-owned
  facts.
- `query-doctor-optimize-query --help`: read-only pasted-SQL optimizer review.

Все packaged console scripts принимают `--help`. Root-level compatibility
launchers удалены; используйте `query-doctor-*` commands или
`python -m query_doctor.cli.<command_module>` из checkout без установки.

Query Doctor поддержан как single-user, local-first tool, запускаемый
оператором со своими local Cloudera Manager, Kerberos, Impala, Prometheus и LLM
credentials. Для web UI используйте localhost или tightly controlled local
bind. Не разворачивайте текущий web UI как shared service без отдельного
дизайна authentication, authorization, tenant/job isolation, audit logging,
TLS/reverse-proxy trust и resource limits.

## Safety model

- Python/analyzer-owned facts - единственное trusted diagnostic evidence.
- Raw LLM output недоверенный, пока не пройдет normalization, sanitization и
  validation.
- Browser-visible UI и trusted reports не должны раскрывать raw SQL, raw
  profiles, raw metadata, local paths, secrets, subprocess output,
  model/runtime internals или raw artifact filenames.
- External collection должен быть explicit, bounded, read-only, redacted и safe
  by default.
- Local config `privacy_mode` по умолчанию `true`; отключение может ослабить
  local artifact identifier/host masking, но browser-visible UI и trusted
  reports все равно не показывают raw SQL, profiles или metadata.
- Local config `no_llm=true` оставляет report и optimizer actions на
  deterministic Python-owned output.
- Query Optimizer принимает только один safe read-only statement и никогда не
  выполняет pasted SQL.

Полный trust/redaction contract: [docs/safety-contract.md](docs/safety-contract.md).
Reviewer-oriented обзор: [docs/security-model.md](docs/security-model.md).

## Документация

Начинайте с [docs/README.md](docs/README.md). Он разделяет current user docs,
operations guides, architecture contracts, audit docs и supporting references.

Полезные следующие документы:

- [docs/demo-mode.md](docs/demo-mode.md): synthetic demo pack и README
  screenshot refresh path.
- [docs/DEMO.md](docs/DEMO.md): localhost UI demo runbook и talk track.
- [docs/local-smoke.md](docs/local-smoke.md): local validation и smoke checks.
- [docs/credentials.md](docs/credentials.md): локальная раскладка credentials.
- [docs/roadmap.md](docs/roadmap.md): implemented scope и planned seams.
- [docs/query-optimizer-contract.md](docs/query-optimizer-contract.md):
  optimizer trust boundary.
- [docs/release-checklist.md](docs/release-checklist.md): final tag,
  package-index и visibility-change checklist.

Английская документация является канонической. Русские companion pages живут в
[docs/i18n/ru/](docs/i18n/ru/) там, где полезны длинные operator-facing
объяснения.

## Development checks

Для обычных изменений запускайте focused tests для touched area и всегда:

```bash
git diff --check
```

Для выбора focused validation используйте
[docs/agent-quickstart.md](docs/agent-quickstart.md) и
[docs/test-matrix.md](docs/test-matrix.md). Перед release cleanup или
public-sharing work расширяйте gate до:

```bash
pre-commit run --all-files
scripts/local_gate.sh
query-doctor-demo-preflight --public-release
```

Stage only explicit files. Не commit generated cases, reports, local configs,
credentials, raw profiles, raw metadata или temporary outputs.

## Public status

Репозиторий публичный. Public source releases начинаются с `v0.4.2`; `v0.6.0`
продолжает эту public source release line. Older package-index releases
остаются видимыми на
[query-doctor on PyPI](https://pypi.org/project/query-doctor/) для
installed-artifact history. Public license is Apache-2.0.

PyPI publishing использует GitHub OIDC Trusted Publishing. Repository-side
`testpypi` и `pypi` environments требуют maintainer approval и не используют
stored package-index API tokens.

## Licensing

Query Doctor лицензирован под Apache License, Version 2.0 (`Apache-2.0`).
См. [LICENSE](LICENSE).

Apache, Apache Impala и Impala являются товарными знаками The Apache Software
Foundation. Query Doctor - независимый проект; он не одобрен The Apache
Software Foundation или проектом Apache Impala.
