# Query Doctor

Last reviewed: 2026-06-11

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
  engine сегодня - Apache Impala, с ограниченными raw-free preview seams для
  будущих движков.

Query Doctor это не:

- универсальный AI-чатбот поверх raw profiles;
- замена Impala Web UI;
- инструмент выполнения пользовательского SQL или чернового SQL из optimizer;
- инструмент, который по умолчанию отправляет сырой SQL или данные профилей во
  внешние сервисы;
- оракул первопричин;
- live multi-engine query collector сегодня.

## Что он делает

- Превращает один экспортированный текстовый профиль Apache Impala в локальный
  deterministic diagnosis без Cloudera Manager, Kerberos, metadata,
  Prometheus, browser upload или LLM provider.
- Сканирует завершенные Recent queries как основной production workflow;
  Running queries и один explicit Known Query ID остаются сфокусированными
  вторичными режимами.
- Работает с Cloudera Manager, когда он доступен, или с ограниченными direct
  Impala daemon endpoints для non-Cloudera-Manager Impala clusters.
- Опционально добавляет ограниченные Prometheus runtime summaries для direct
  Impala workflows и ограниченные read-only метаданные Impala через
  `impala-shell`.
- Ранжирует подозрительные cases и action candidates по детерминированным
  analyzer facts, а не по LLM scoring.
- Показывает Details как analyst decision page: почему запрос важен, где
  проверить, что попробовать, как проверить comparable rerun и каких evidence
  не хватает.
- Генерирует доверенные отчеты только после детерминированной нормализации,
  очистки и проверки.
- Дает отдельный read-only Query Optimizer workflow для разбора вставленного
  SQL и explicit selected-case optimizer actions для уже разобранных сервером
  случаев.
- Не показывает сырой SQL, сырые профили, сырые метаданные, локальные пути,
  секреты, subprocess output, model/runtime internals и raw artifact filenames
  в browser и trusted report surfaces.

## Граница поддержки

| Surface | Current status |
| --- | --- |
| Query engine | Apache Impala - production triage engine. |
| First-value intake | Один локальный экспортированный Impala text profile можно staged/redacted/analyzed и открыть через Known Query ID. |
| Recent scan | Cloudera Manager - полный Recent discovery/profile/metrics/events provider для Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans и один Known Query ID через impalad daemon endpoints; без Cloudera Manager events и без SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries для configured direct Impala workflows; без arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements через `impala-shell`; без user SQL execution и unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts, validation и explicit selected-case actions; без automatic batch LLM jobs. |
| Trino and Spark | Только bounded raw-free preview/compact surfaces. Это не production engine support, не live Recent scans, не Details/trusted report output, не optimizer behavior и не Query Doctor-generated SQL. |

Trino preview surfaces остаются offline/local boundary, а не public support:
bounded local pruned QueryInfo import принимает one explicit compact sanitized
local pruned QueryInfo JSON через `query-doctor-trino-query-info-pruned-import`
после source-contract checks. `query-doctor-trino-coordinator-query-info-pruned-probe`
и `query-doctor-trino-coordinator-query-info-pruned-import` могут использовать
`--auth-header-file`, но safe output не печатает auth header paths или values,
не делает network read вне explicit bounded probe/import, reject-ит raw
QueryInfo fields вроде Query ID, query text, session fields, endpoint URLs,
object names и stage/task detail, и не дает live collection,
Details/trusted report output, optimizer behavior или Query Doctor-generated
Trino SQL.

Spark compact support surfaces остаются только compact History Server intake,
compact evidence-package build/validation и compact diagnosis; no public Spark
engine support, без Recent scans, Details/trusted report output, optimizer
behavior, raw event logs или Spark job execution.

Будущие Big Data SQL/lakehouse live collectors, более широкие providers,
подготовленные event/log sources и Cluster Doctor workflows остаются roadmap
seams, а не текущей поддержкой. Detailed Trino/Spark preview command catalog:
[docs/engines/README.md](docs/engines/README.md). Текущий support/research
boundary: [docs/engine-support-gap-matrix.md](docs/engine-support-gap-matrix.md).

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

## Выберите первый путь

Берите самый короткий путь, который соответствует вашему уровню доступа.

| Дверь | Когда подходит | С чего начать |
| --- | --- | --- |
| Один экспортированный профиль | Можно получить один текстовый профиль из Impala Web UI, но live access пока недоступен. | `query-doctor-analyze --profile-text` |
| Synthetic demo | Нужно read-only local click-through без реальных данных. | `query-doctor-web --public-demo` |
| Minimal CM scan | Есть read-only Cloudera Manager access к Impala service. | `query-doctor-web` или `query-doctor-batch-recent` |

### Дверь 1: анализ одного экспортированного профиля

Самый простой путь - один экспортированный Apache Impala text profile в один
локальный diagnosis. Он не обращается к Cloudera Manager или impalad, не требует
Kerberos, metadata collection, Prometheus или LLM provider и не загружает raw
profile через browser.

```bash
QUERY_ID="aaaaaaaaaaaaaaaa:0000000000000001"
query-doctor-analyze \
  --profile-text ./exported-impala-profile.txt \
  --query-id "$QUERY_ID" \
  --out cases/cm-corpus
```

Команда создает collector-shaped local case под `cases/cm-corpus`, по умолчанию
редактирует users, hosts, credentials и common secret forms, пишет
`analysis_facts.md` и `analysis.json`, затем печатает output case directory.
Используйте `--redact-identifiers`, если staged local artifacts могут быть
переданы наружу. Manual profile intake принимает только exported text profiles;
JSON, Thrift и profile-v2 payloads остаются вне этого entry path.

Чтобы открыть staged case в local UI, запустите `query-doctor-web`, выберите
`One Query ID` и введите тот же Query ID. Known Query ID analysis переиспользует
complete manual-profile staged cases вместо recollection.

### Дверь 2: synthetic demo

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

Для read-only click-through demo, которое совпадает с public synthetic UI,
используйте one-command mode из [docs/demo-mode.md](docs/demo-mode.md):
`query-doctor-web --public-demo`. Он сам генерирует synthetic demo pack в
dedicated temp directory, включает Python-only mode, игнорирует default local
config и блокирует все POST actions.

Откройте localhost URL, который напечатает `query-doctor-web`. Начните с
`/?query_group=workloads#scan-context`, чтобы показать компактный Scan context,
workload follow-up links и local synthetic action outcomes перед открытием
Workload Details.

Локальный web UI начинается с ограниченной формы поиска и показывает synthetic
Finished Queries results:

![Synthetic Query Doctor demo search form](docs/assets/demo_search.png)

![Synthetic Query Doctor finished queries results](docs/assets/demo_finished_queries.png)

Synthetic demo pack `0.5.0` содержит eleven sanitized cases: workload
follow-up, repeated patterns, trusted optimizer recommendations, stats
maintenance, storage/HDFS follow-up, frequent-short workloads, mixed signals,
unknown-but-useful limited evidence и direct-Impala compatibility. Полный
список scenarios:
[docs/demo-cases.md](docs/demo-cases.md).

### Дверь 3: minimal Cloudera Manager scan

Используйте этот путь, если есть read-only Cloudera Manager access к Impala
service. Secrets держите в shell environment или local env file, не в JSON
config. Перед `source` создайте `~/.qdcreds/cm-ro.env` с `CM_USERNAME` плюс
`CM_PASSWORD` или `CM_TOKEN`.

```bash
mkdir -p ~/.qdcreds
cp query-doctor-config.minimal.example.json ~/.qdcreds/query-doctor-config.json
# Отредактируйте CM URL, cluster, service и CA bundle при необходимости.
set -a
source ~/.qdcreds/cm-ro.env
set +a
query-doctor-web \
  --config ~/.qdcreds/query-doctor-config.json \
  --host 127.0.0.1 \
  --port 8765
```

Headless bounded Recent scan без automatic LLM reports:

```bash
query-doctor-batch-recent \
  --config ~/.qdcreds/query-doctor-config.json \
  --recent-window-minutes 60 \
  --triage-profile-limit 10 \
  --top-reports 0
```

Minimal path использует Cloudera Manager для Impala Recent discovery и profile
collection. Metadata, CM time-series, direct Impala, Prometheus или LLM settings
лучше добавлять только после того, как базовый scan path заработал. См.
[docs/configuration.md](docs/configuration.md) и
[docs/credentials.md](docs/credentials.md).

## Основные workflows

- `query-doctor-web --help`: local browser UI для Recent scan, Running now,
  одного Known Query ID, Details pages, explicit report actions и explicit
  details-page optimizer actions.
- `query-doctor-batch-recent --help`: headless Recent scan для bounded local
  collection и ranking.
- `query-doctor-analyze --help`: deterministic analyzer по collected local case
  files или одному staged local exported Impala text profile.
- `query-doctor-report --help`: validated report generation из Python-owned
  facts.
- `query-doctor-optimize-query --help`: read-only pasted-SQL optimizer review.

Все packaged console scripts принимают `--help`. Root-level compatibility
launchers удалены; используйте `query-doctor-*` commands или
`python -m query_doctor.cli.<command_module>` из checkout без установки.

Query Doctor поддержан как single-user, local-first tool, запускаемый
оператором со своими local Cloudera Manager, Kerberos, Impala, Prometheus и LLM
credentials. Для web UI используйте localhost или tightly controlled local
bind. Не разворачивайте ordinary local mode как shared service без отдельного
дизайна authentication, authorization, tenant/job isolation, audit logging,
TLS/reverse-proxy trust и resource limits. Shared public demos должны
использовать read-only режим `query-doctor-web --public-demo`.

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
