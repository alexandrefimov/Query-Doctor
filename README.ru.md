# Query Doctor

Last reviewed: 2026-05-26

Язык: [English](README.md) | Русский

Query Doctor - локальный диагностический инструмент для Big Data-запросов,
сфокусированный сегодня на разборе рабочих запросов Apache Impala. Он
помогает операторам ранжировать подозрительные запросы из Recent, собирать
ограниченный контекст профиля, извлекать детерминированные диагностические
сигналы, опционально обогащать их безопасными метаданными и генерировать
проверенные отчеты без показа сырого SQL или сырых профилей в доверенном UI и
отчетах.

Инструмент работает рядом с учетными данными оператора, собирает ограниченный
контекст только для чтения из Cloudera Manager или прямых endpoints демонов
Impala, извлекает детерминированные факты в Python и может генерировать
проверенные отчеты, не считая LLM источником истины. Общий параметр `language`
управляет Help, статическим текстом Details и новыми доверенными отчетами;
русский вывод использует тот же language-specific prompt, normalizer и границу
валидатора.

Главное правило:

```text
Python owns facts. LLM owns wording only.
```

Recent scan - основной рабочий процесс. Диагностика по Query ID вторична и
предназначена для одного известного запроса Impala. Query Optimizer отдельный,
только для чтения, не выполняет SQL и не показывает отправленный SQL обратно
после submit. Генерация отчета использует LLM только для формулировок на
основе фактов, которыми владеет Python.

## Что Query Doctor делает / не делает

Query Doctor это:

- локальный рабочий инструмент для разбора рабочих запросов Impala;
- извлекатель детерминированных диагностических сигналов;
- рабочий процесс ранжирования Recent queries для операторов и
  администраторов;
- безопасный генератор отчетов на проверенных фактах;
- практический инструмент для решения, что смотреть, что менять и как
  проверять;
- первый узкий слой диагностики Big Data SQL/lakehouse, где реализованный
  движок сегодня - Apache Impala.

Query Doctor это не:

- универсальный AI-чатбот поверх сырых профилей;
- замена Impala Web UI;
- инструмент выполнения пользовательского SQL или чернового SQL из optimizer;
- инструмент, который по умолчанию отправляет сырой SQL или данные профилей во
  внешние сервисы;
- оракул первопричин;
- multi-engine продукт сегодня.

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
- Direct Impala может опционально пробовать ограниченный `/profile_docs` для
  меток стабильности счетчиков. Query Doctor сохраняет только безопасный
  allowlisted registry context, а не сырую документацию счетчиков.
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
- Не показывает сырой SQL, сырые профили, сырые метаданные, локальные пути,
  секреты, subprocess output, model/runtime internals и raw artifact filenames
  в browser и trusted report surfaces.

## Поддерживаемая область

| Область | Поддержано сейчас | Не является текущей поддержкой |
| --- | --- | --- |
| Query engine | Apache Impala | Другие engines остаются только roadmap seams. |
| Trino private preview | Closed test-cluster smoke и sanitized evidence-package artifacts для maintainers | Public Trino engine support, live collection, browser/report output, optimizer behavior или Query Doctor-generated SQL. |
| Cloudera Manager | Полный Recent discovery/profile/metrics/events context для Impala workflows | Generic cluster diagnosis вне Query Doctor flow. |
| Direct Impala | Ограниченные Recent scans, Running scans и один Known Query ID через impalad daemon endpoints | Cloudera Manager events, broad log scraping или SQL execution. |
| Runtime metrics | Опциональные ограниченные Prometheus summaries для configured direct Impala workflows | Raw time-series output или arbitrary PromQL from users. |
| Metadata | Read-only allowlisted metadata statements через `impala-shell` | User SQL execution или unbounded metadata crawling. |
| Reports and optimizer | Python-owned facts, validation и explicit selected-case actions | LLM output как trusted evidence или automatic batch LLM jobs. |

Будущие Big Data SQL/lakehouse engines, более широкие providers,
подготовленные event/log sources и Cluster Doctor workflows остаются roadmap
seams, а не текущей поддержкой.
Trino private-preview artifacts - только closed test-cluster groundwork; см.
[docs/engines/trino-private-preview-release.md](docs/engines/trino-private-preview-release.md).

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

Для локальной разработки из checkout используйте editable install:

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
```

Для инструментов разработки установите development extra:

```bash
python -m pip install -e ".[dev]"
pre-commit install
```

В окружении с ограниченной сетью устанавливайте из готового wheel или
убедитесь, что зависимости сборки уже доступны локально:

```bash
python -m pip install .
```

Локальная JSON-конфигурация описана в
[docs/configuration.md](docs/configuration.md). Предпочтительный путь на
рабочей станции: `~/.qdcreds/query-doctor-config.json`. Секреты остаются в
environment variables или local env files.

## Quickstart smoke

Сначала запустите детерминированные локальные проверки. Они не вызывают
Cloudera Manager, Impala, Ollama или сеть:

```bash
query-doctor-demo-preflight
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Откройте localhost URL, который напечатает `query-doctor-web`. Synthetic demo
pack локальный и не содержит настоящих SQL-запросов, профилей, метаданных,
hostnames, users или credentials.

Локальный web UI начинается с ограниченной формы поиска и показывает synthetic
Finished Queries results для разбора:

![Synthetic Query Doctor demo search form](docs/assets/demo_search.png)

![Synthetic Query Doctor finished queries results](docs/assets/demo_finished_queries.png)

Видео: [45-second synthetic demo](https://youtu.be/rtBmnmS-Y10).

## Console scripts

После установки используйте packaged entry points:

```bash
query-doctor-analyze --help
query-doctor-batch-recent --help
query-doctor-cleanup-generated --help
query-doctor-cm-events --help
query-doctor-cm-sample-smoke --help
query-doctor-collect-cm-profiles --help
query-doctor-collect-impala-context --help
query-doctor-collect-impala-profile --help
query-doctor-corpus-smoke --help
query-doctor-demo --help
query-doctor-demo-preflight --help
query-doctor-optimize-query --help
query-doctor-pipeline --help
query-doctor-report --help
query-doctor-web --help
```

Root-level compatibility launchers удалены. Используйте `query-doctor-*`
commands или `python -m query_doctor.cli.<command_module>` при запуске прямо из
checkout без установки console scripts.

## Основные workflows

### Web UI

```bash
query-doctor-web --help
```

Local web UI содержит:

- `Diagnose`: основной экран Recent Scan triage по многим queries.
  `Finished queries` - target по умолчанию; `Running now` доступен как
  lower-confidence live context.
- `Known Query ID`: вторичный режим внутри `Diagnose` для одного explicit
  Impala query ID. По умолчанию использует Cloudera Manager или direct Impala
  daemon profile endpoints, когда настроен `cluster_type=impala`.
- Details pages с deterministic findings, evidence context и explicit LLM
  Report / Query LLM optimizer actions.
- `Help`: curated workflow, safety и documentation guidance внутри продукта.

Pasted-SQL `Query Optimizer` остается read-only compatibility route и test
surface. Он не выполняет SQL и не показывает submitted SQL обратно после
submit, но не продвигается как primary navigation item, пока основной продукт
сфокусирован на profile-backed diagnosis.

Validated reports и details-page optimizer drafts генерируются только явным
действием пользователя для выбранных cases.

### CLI and headless use

Packaged CLI entry points покрывают analyzer runs, batch Recent scans, profile
collection, metadata collection, reports, optimizer review, demo generation и
cleanup. Они предназначены для локальной диагностики, automation в controlled
environment и CI-style smoke checks.

Для team workflows лучше использовать pinned project version и общие соглашения:
reports repository, scheduled headless scans под controlled service account,
team jumpbox или shared local LLM endpoint. Query Doctor остается local-first и
single-user, пока отдельный shared-deploy design не добавит authentication,
authorization, tenant/job isolation, audit logging, TLS trust и resource limits.

### Analyzer

```bash
query-doctor-analyze CASE_DIR
```

Analyzer читает collected local case files и пишет deterministic facts. Он не
вызывает Cloudera Manager, Impala, Ollama или report writer.

### Pipeline

```bash
query-doctor-pipeline CASE_DIR --stop-after-analysis
```

Pipeline mode запускается analyzer-first, может опционально собрать bounded
metadata при наличии configuration и генерирует reports только по запросу.

### Query Optimizer

```bash
query-doctor-optimize-query --help
```

Query Optimizer принимает один safe read-only `SELECT` или `WITH` statement для
analysis. Он никогда не выполняет SQL, не echo pasted SQL после submit и
доверяет SQL drafts только когда Python-owned recipes и validation доказывают
поддерживаемую transform.

### Demo Preflight

```bash
query-doctor-demo-preflight
```

Demo preflight полностью deterministic и local. Он проверяет git hygiene,
safety-sensitive changed areas, browser/trusted-output denylist patterns и
focused test suggestions без LLM, network, Cloudera Manager или Impala access.

## Supported deployment

Query Doctor поддержан как single-user, local-first tool, запускаемый оператором
со своими локальными Cloudera Manager, Kerberos, Impala, Prometheus и LLM
credentials. Для web UI используйте localhost или tightly controlled local
bind.

Не разворачивайте текущий web UI как shared service для команды или компании.
Shared deployments требуют отдельного дизайна authentication, authorization,
tenant/job isolation, audit logging, TLS/reverse-proxy trust и resource limits.

## Почему не chat wrapper

В operational diagnostics неподдержанная уверенность хуже честного "unknown".
Chat wrapper над raw profiles слишком легко превращает wording модели в
случайное evidence.

Вместо этого:

- collectors собирают bounded, read-only, redacted inputs;
- analyzers извлекают deterministic facts;
- reports используют LLM только для формулировки этих facts;
- validators отклоняют unsupported claims и unsafe output;
- browser surfaces показывают trusted summaries, а не raw operational artifacts.

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
- Local config `no_llm=true` переводит report и optimizer actions на
  deterministic Python-owned output без вызова local generation backend.
- Impala metadata collection allowlisted и read-only.
- Query Optimizer принимает только один safe read-only statement и никогда не
  выполняет pasted SQL.

Полный контракт: [docs/safety-contract.md](docs/safety-contract.md). Публичный
reviewer-oriented обзор: [docs/security-model.md](docs/security-model.md).

## Licensing

Query Doctor лицензирован под Apache License, Version 2.0 (`Apache-2.0`).
См. [LICENSE](LICENSE).

Apache, Apache Impala и Impala являются товарными знаками The Apache Software
Foundation. Query Doctor - независимый проект; он не одобрен The Apache
Software Foundation или проектом Apache Impala.

## Документация

Начинайте с [docs/README.md](docs/README.md). Он разделяет current user docs,
операторские guides, architecture contracts, текущие audit docs и supporting
references.

Английский язык является каноническим для документации. Русские companion pages
живут в [docs/i18n/ru/](docs/i18n/ru/) там, где полезны длинные
operator-facing explanations. Если английская и русская версии расходятся,
английская страница остается источником истины до обновления перевода.

Public demo и release paths:

- [docs/demo-mode.md](docs/demo-mode.md): generation synthetic demo pack и
  refresh path для README screenshots.
- [docs/DEMO.md](docs/DEMO.md): localhost UI demo runbook и talk track.
- [docs/demo-cases.md](docs/demo-cases.md): sanitized public demo scenarios.
- [docs/demo-preflight.md](docs/demo-preflight.md): deterministic demo и
  public-release guard.
- [docs/public-release-readiness.md](docs/public-release-readiness.md):
  checklist готовности публичного release.
- [docs/release-checklist.md](docs/release-checklist.md): final tag,
  package-index и visibility-change checklist.

Полезные ссылки:

- [docs/local-smoke.md](docs/local-smoke.md): локальные validation и smoke
  checks.
- [docs/credentials.md](docs/credentials.md): локальная раскладка credentials.
- [docs/repository-hardening.md](docs/repository-hardening.md): repository
  security, CI hardening, release automation и backlog сильных проверок.
- [docs/architecture.md](docs/architecture.md): текущие и будущие component
  boundary diagrams.
- [docs/upstream-impala-ai-analyzer.md](docs/upstream-impala-ai-analyzer.md):
  alignment с Apache Impala native AI profile-analysis direction.
- [docs/roadmap.md](docs/roadmap.md): реализованный scope и planned seams.
- [docs/query-optimizer-contract.md](docs/query-optimizer-contract.md):
  trust boundary оптимизатора.

## Development checks

Перед commit:

```bash
pre-commit run --all-files
scripts/local_gate.sh
python -m ruff check query_doctor tests
python -m ruff format --check query_doctor tests scripts
python3 -m pytest -q
git diff --check
query-doctor-demo-preflight
git status --short
```

Stage only explicit files. Не commit сгенерированные cases, reports, local
configs, credentials, raw profiles, raw metadata или temporary outputs.

## Public status

Репозиторий публичный. `v0.1.0` - initial public GitHub release baseline,
`v0.1.1` - первый PyPI release, а package metadata и release notes для `0.4.0`
готовы к следующему package-index release: [query-doctor on PyPI](https://pypi.org/project/query-doctor/)
показывает текущий package-index status. Public license is Apache-2.0.

PyPI publishing использует GitHub OIDC Trusted Publishing. Repository-side
`testpypi` и `pypi` environments требуют maintainer approval и не используют
stored package-index API tokens.

Перед новым tag, package-index publish или public release announcement запускайте
public-release guard из clean working tree:

```bash
query-doctor-demo-preflight --public-release
```

Полный checklist: [docs/release-checklist.md](docs/release-checklist.md).
