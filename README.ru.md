# Query Doctor

Last reviewed: 2026-08-10

Язык: [English](README.md) | Русский

Query Doctor - локальный диагностический инструмент для Big Data-запросов,
сфокусированный на production triage для Apache Impala и bounded local Trino
production lanes. Он помогает операторам ранжировать подозрительные Recent
queries, собирать ограниченный контекст профиля, извлекать детерминированные
evidence и генерировать
проверенные отчеты без показа raw SQL или raw profiles в trusted
browser/report surfaces.
В релизе 0.11.0 добавлены supported container image, Kubernetes
manifests, Helm chart, raw-free Online History и bounded parsing одного уже
предоставленного Impala EXPLAIN artifact.

Главное правило:

```text
Python owns facts. LLM owns wording only.
```

Recent scan - основной workflow. Диагностика по Query ID вторична и рассчитана
на один известный Impala query; есть локальный Trino lane для bounded
retained-list Recent diagnosis и одного explicit Query ID, если настроены
нужные coordinator contracts. Query Optimizer отдельный, read-only, не
выполняет SQL и не показывает отправленный SQL обратно.

## Quickstart

```bash
python -m pip install query-doctor
query-doctor-self-test
query-doctor-analyze \
  --profile-text ./exported-impala-profile.txt \
  --out cases/cm-corpus
query-doctor-web --corpus-dir cases/cm-corpus
```

После установки запустите `query-doctor-self-test`: он проверяет installed
console scripts, synthetic demo generation, анализ одного профиля, fallback по
имени скачанного Impala Web UI профиля, local web rendering, deterministic
report generation и corpus smoke. Команда использует только synthetic local
data и не обращается к Cloudera Manager, impalad, Spark, Trino, Prometheus,
Ollama или external LLM services.
Package и release CI также запускают README Quickstart smoke против clean wheel
install: `query-doctor-self-test`, `query-doctor-analyze --profile-text
./exported-impala-profile.txt --out cases/cm-corpus` и
`query-doctor-web --corpus-dir cases/cm-corpus`.

Для CLI-пути анализа профиля нужен один экспортированный Impala text profile; не
нужны Cloudera Manager, Kerberos, local config, Prometheus или LLM. Direct
Impala Web UI download с именем `profile_<query-id-high>_<query-id-low>` можно
использовать как есть. Web UI автоматически открывает staged cases из
`--corpus-dir`, а local/private web sessions могут загрузить один exported text
profile прямо с Query Inbox page. Demo и Cloudera Manager варианты описаны ниже в
[Выберите первый путь](#выберите-первый-путь).

## Что это / что это не

Query Doctor это:

- локальный рабочий инструмент для Impala production triage с официальными
  bounded local Trino production lanes;
- извлекатель детерминированных diagnostic facts;
- workflow ранжирования Recent queries для операторов и администраторов;
- безопасный генератор отчетов на проверенных фактах;
- практический инструмент для решения, что смотреть, что менять и как
  проверять;
- containerized web application для read-only public demo или configured
  private operator service за trusted ingress/auth proxy;
- первый узкий слой диагностики Big Data SQL/lakehouse, где full production
  triage engine - Apache Impala, с bounded raw-free local Trino production
  lanes и preview seams для будущих движков.

Query Doctor это не:

- универсальный AI-чатбот поверх raw profiles;
- замена Impala Web UI;
- инструмент выполнения пользовательского SQL или чернового SQL из optimizer;
- инструмент, который по умолчанию отправляет сырой SQL или данные профилей во
  внешние сервисы;
- оракул первопричин;
- broad live multi-engine query-history collector.

## Что он делает

- Превращает один экспортированный текстовый профиль Apache Impala в локальный
  deterministic diagnosis через CLI staging, corpus browsing или bounded
  local/private web upload, без Cloudera Manager, Kerberos, metadata,
  Prometheus или LLM provider.
- Сканирует завершенные Recent queries как основной production workflow;
  Running queries и один explicit Known Query ID остаются сфокусированными
  вторичными режимами.
- Работает с Cloudera Manager, когда он доступен, или с ограниченными direct
  Impala daemon endpoints для non-Cloudera-Manager Impala clusters.
- Открывается на Query Inbox: safe materialized Recent cases показываются
  сразу, если они уже есть, со status strip для
  empty/ready/running/partial/stale, safe source/window/time-range/query-type
  scope chips, URL-driven source/window/time-range/workflow/query-type scope
  filters, first-screen result presets, view-only owner/pool tag и opaque
  owner/pool value filters, lifecycle, readiness и action filters для
  owner-tagged rows, pool-tagged rows, safe owner/pool values, clean analysis,
  status follow-up, metadata availability, validated reports, optimizer
  guidance и recorded action outcomes, а также New scan как вторичным control
  action.
  Если выбранные scope filters не совпадают с текущим materialized snapshot,
  Query Inbox показывает safe filtered state и New scan form вместо stale rows;
  эта форма получает prefill из выбранных safe
  source/window/time-range/workflow/query-type filters, когда они соответствуют
  поддерживаемым scan controls. Когда materialized results открыты, New scan
  получает safe source/window/time-range/workflow/query-type refresh defaults,
  чтобы повторный bounded scan не требовал заново вводить тот же scope. Safe
  scope filters сохраняются через New scan submit и job pages без echo
  произвольных query parameters; owner/pool tag и opaque owner/pool value
  filters, lifecycle/readiness/action result filters сохраняются только в
  result links, spill filtering и pagination. Window, UTC time-range и
  query-type scope теперь имеют inline controls, чтобы менять bounded lookback, exact
  finished-query range и короткий query type identifier прямо из Query Inbox
  перед materialization этого scope.
- Поддерживает bounded local Trino production lanes при явной local config:
  retained-list Recent, один explicit Query ID, raw-free materialized Details,
  deterministic Python Report и optimizer guidance over the same server-owned
  case facts.
- Запускается из supported Docker image и Kubernetes manifests для read-only
  synthetic demo или configured private web deployments.
- Опционально добавляет ограниченные Prometheus runtime summaries для direct
  Impala workflows и ограниченные read-only метаданные Impala через
  `impala-shell`.
- Ранжирует подозрительные cases и action candidates по детерминированным
  analyzer facts, а не по LLM scoring.
- Показывает Details как analyst decision page: почему запрос важен, где
  проверить, что попробовать, как проверить comparable rerun и каких evidence
  не хватает.
- Встраивает validated selected-case optimizer guidance в ту же зону
  Recommended change, когда оно доступно, но report и optimizer generation
  остаются отдельными explicit actions.
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
| Query engine | Apache Impala - full production triage engine. Trino имеет bounded local production support только для raw-free lanes ниже. |
| First-value intake | Один локальный exported Impala text profile можно загрузить из local/private web session или staged через CLI/manual inbox, затем redacted/analyzed и открыть через Known Query ID. |
| Recent scan | Cloudera Manager - полный Recent discovery/profile/metrics/events provider для Impala workflows. |
| Direct Impala | Bounded Recent scans, Running scans и один Known Query ID через impalad daemon endpoints; без Cloudera Manager events и без SQL execution. |
| Runtime metrics | Optional bounded Prometheus summaries для configured direct Impala workflows; без arbitrary PromQL from users. |
| Metadata | Read-only allowlisted Impala metadata statements через `impala-shell`; без user SQL execution и unbounded metadata crawl. |
| Reports and optimizer | Python-owned facts и validation. Known Query ID готовит deterministic Python report в explicit submit-job; LLM narratives и optimizer actions остаются explicit selected-case actions. |
| Container/Kubernetes web deployment | Supported starting point через official container image, `/healthz` и `/readyz` probes, raw-free deployment readiness summary, read-only `public-demo` manifest, configured private web manifest, synthetic self-test Job и `deploy/helm/query-doctor` chart с `helm test` hook. Kubernetes support не добавляет native auth, RBAC, sessions, multi-tenant isolation, operator/CRD, arbitrary command running, SQL execution или broader engine support. Shared configured deployments все равно требуют trusted ingress/auth proxy и те же safety gates, что любой shared/non-local web bind. |
| Trino local | Local web Trino mode может прочитать один bounded retained pruned coordinator query list для Recent diagnosis, затем bounded pruned coordinator QueryInfo payloads для выбранных rows или одного explicit Query ID, показать deterministic compact diagnosis, materialize server-owned raw-free case artifacts, открыть raw-free Details view и создать deterministic Python Report плюс optimizer guidance для этих materialized cases. `trino_support_mode=beta` сохраняет legacy beta label; `trino_support_mode=production` помечает те же bounded raw-free local lanes как local production support и убирает этот label. Без Running scans, query-history crawling, metadata collection, LLM report output, Query Optimizer jobs, generated Trino SQL, SQL execution и broader/shared Trino production triage support. |
| Spark | Только bounded compact support surfaces. Spark не является production engine support, live Recent scans, Details/trusted report output, optimizer behavior, raw event-log handling, Spark job execution или Query Doctor-generated SQL. |

Публичный GHCR release содержит Query Doctor web image.

Trino compact/dev surfaces включают offline/local raw-free imports and checks:
bounded local pruned QueryInfo import принимает one explicit compact sanitized
local pruned QueryInfo JSON через `query-doctor-trino-query-info-pruned-import`
после source-contract checks. `query-doctor-trino-coordinator-query-info-pruned-probe`
и `query-doctor-trino-coordinator-query-info-pruned-import` могут использовать
`--auth-header-file`, но safe output не печатает auth header paths или values.
Local production Trino product surfaces - local web retained-list Recent diagnosis, One
Query ID diagnosis, raw-free Details view, deterministic Python Report и optimizer guidance для
server-owned materialized cases из этих lanes. Diagnosis lanes требуют
`trino_support_mode=beta` или
`trino_support_mode=production`, `trino_coordinator_url` и
`trino_query_info_source_contract` в local config; Recent дополнительно требует
`trino_query_list_source_contract`. Legacy `trino_beta_enabled=true` остается
beta-only switch для existing local setups и не должен комбинироваться с
`trino_support_mode=production`. Startup validation проверяет local source
contracts, safe coordinator URL shape и optional auth reference
(`trino_auth_header_file` или local Kerberos/SPNEGO settings) до того, как lane
считается configured. Configured beta sources помечаются в source selector как
`Trino Beta Recent + One Query ID` или `Trino Beta One Query ID`; configured
production-mode sources используют labels без `Beta`. Diagnose Engine control
сужает Source cluster selector до Impala-capable sources или Trino-ready sources
до выбора workflow, а stale или forged Trino submits все равно fail closed до
analysis или async job creation. Этот lane не делает network read вне explicit
bounded probe/import, reject-ит raw QueryInfo fields вроде query text, session
fields, endpoint URLs, object names и stage/task detail. Details открывается
только после materialized artifacts. Python Report и optimizer guidance используют те же raw-free
facts и не показывают raw payloads, query IDs, paths, LLM report output,
Query Optimizer jobs или generated SQL; Running scans, Query Optimizer jobs и
metadata collection остаются unavailable.
Broader/shared Trino live collection и broader Trino production triage остаются unsupported.

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
query-doctor-self-test
```

`query-doctor-self-test` - confidence check установленного пакета. Он использует
synthetic local data и проверяет packaged console scripts, анализ одного
профиля, fallback по имени скачанного Impala Web UI профиля, local web
rendering, deterministic reports и corpus smoke без доступа к Cloudera Manager,
impalad, Spark, Trino, Prometheus, Ollama или external LLM services.

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

### Container and Kubernetes

После одобрения и публикации release `v0.11.0` workflow опубликует web image в
GitHub Container Registry:

```text
ghcr.io/alexandrefimov/query-doctor:0.11.0
```

После публикации image по умолчанию стартует безопасный synthetic public demo:

```bash
docker run --rm -p 127.0.0.1:8765:8765 ghcr.io/alexandrefimov/query-doctor:0.11.0
```

Из checkout можно собрать и проверить тот же shape локально:

```bash
scripts/build-image.sh query-doctor:dev
scripts/image-smoke.sh query-doctor:dev
```

С arm64 workstation собирайте amd64 image перед проверкой на amd64 Kubernetes
nodes:

```bash
QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64 scripts/build-image.sh query-doctor:dev-amd64
QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64 scripts/image-smoke.sh query-doctor:dev-amd64
```

Kubernetes manifests находятся в [deploy/kubernetes/](deploy/kubernetes/):

- `public-demo.yaml`: read-only synthetic demo без credentials и с denied pod
  egress.
- `configured-web.yaml`: private operator template с mounted config, внешне
  созданным credentials Secret, PVC для cases, persistent Recent cache и
  probes.
- `self-test-job.yaml`: synthetic package confidence check, который запускает
  только `query-doctor-self-test` без config, credentials, PVC, live engine
  access, optimizer jobs, metadata collection или SQL.

Configured Kubernetes и Helm examples ставят `recent_batch_root` в dedicated
temp-backed case-PVC cache mount. Поэтому повторные finished Recent scans могут
переиспользовать уже проанализированные profiles после pod restart, если Query
ID и explicit profile reuse contract совпадают. Results coverage показывает
только aggregate reused-profile count, а второй submit того же running
finished Recent scan возвращает существующий job вместо duplicate collection.

Web deployments expose `/healthz`, `/readyz` и
`/deployment/readiness.json`. Companion CLI
`query-doctor-deployment-readiness` печатает тот же raw-free deployment summary
без запуска сервера. Для configured или shared access ставьте Query Doctor за
trusted ingress/auth proxy; Kubernetes support не добавляет native
authentication, sessions, RBAC, tenant isolation, SQL execution или broader
engine support внутри Query Doctor. См.
[docs/kubernetes-auth-front-door.md](docs/kubernetes-auth-front-door.md) и
`scripts/audit_kubernetes_auth_front_door.py` для raw-free acceptance check
oauth2-proxy/Keycloak-style front door и NetworkPolicy isolation.

Helm chart находится в [deploy/helm/query-doctor/](deploy/helm/query-doctor/).
Он рендерит тот же safe public-demo default и configured private mode, добавляет
values schema coverage, включает synthetic `helm test` hook и поддерживает
generic user-provided pod labels и annotations без встроенного platform
controller contract.

Для disposable cluster-side checks используйте
`scripts/kubernetes-self-test-smoke.sh`: он ставит chart во временный namespace,
запускает `helm test --logs` и чистит ресурсы после synthetic self-test.

## Выберите первый путь

Берите самый короткий путь, который соответствует вашему уровню доступа.

| Дверь | Когда подходит | С чего начать |
| --- | --- | --- |
| Один экспортированный профиль | Можно получить один текстовый профиль из Impala Web UI, но live access пока недоступен. | `query-doctor-analyze --profile-text`, `query-doctor-web` upload или `query-doctor-web` с `manual_profile_dir` |
| Synthetic demo | Нужно read-only local click-through без реальных данных. | `query-doctor-web --public-demo` |
| Minimal CM scan | Есть read-only Cloudera Manager access к Impala service. | `query-doctor-web` или `query-doctor-batch-recent` |

### Дверь 1: анализ одного экспортированного профиля

Самый простой путь - один экспортированный Apache Impala text profile в один
локальный diagnosis. Он не обращается к Cloudera Manager или impalad, не требует
Kerberos, metadata collection, Prometheus или LLM provider.

```bash
query-doctor-analyze \
  --profile-text ./exported-impala-profile.txt \
  --out cases/cm-corpus
```

Команда создает collector-shaped local case под `cases/cm-corpus`, по умолчанию
редактирует users, hosts, credentials и common secret forms, пишет
`analysis_facts.md` и `analysis.json`, затем печатает output case directory.
Используйте `--redact-identifiers`, если staged local artifacts могут быть
переданы наружу. Manual profile intake принимает только exported text profiles;
JSON, Thrift и profile-v2 payloads остаются вне этого entry path. CLI берет
Query ID из header внутри exported profile или из downloaded Impala Web UI
filename строгой формы `profile_<query-id-high>_<query-id-low>`. Если ни один
источник не читается, добавьте `--query-id <query-id>`; когда есть несколько
источников Query ID, они должны совпасть до записи local case.

Чтобы открыть staged cases в local UI, запустите `query-doctor-web
--corpus-dir cases/cm-corpus` из того же workspace. Query Inbox page откроет
таблицу Exported Profiles из complete manual-profile cases в этом corpus без
Cloudera Manager settings, credentials или default local config. Вы все еще
можете выбрать `One Query ID` и ввести Query ID из staged profile, чтобы открыть
именно этот case. LLM narrative и optimizer actions остаются explicit buttons.

В local или private web session можно также выбрать `One Query ID`, ввести
matching Impala Query ID в `Profile Query ID`, выбрать один exported text
profile в `Exported profile` и нажать `Upload`. Upload path bounded через
`max_profile_bytes`, принимает ровно один multipart file, отклоняет JSON, Thrift
и profile-v2 payloads тем же analyzer path, stages server-owned case под
`corpus_dir` и удаляет временный upload file после staging. Public synthetic
demo скрывает эту форму и блокирует uploads до чтения request body.

Также можно настроить local profile inbox для web UI. Положите exported text
profile в `manual_profile_dir`, назвав файл slug-версией Query ID: замените
разделитель Query ID на `_` и сохраните как `<query-id-slug>.txt`. Затем
запустите `query-doctor-web`, выберите `One Query ID` и введите исходный Query
ID. Web path staged/analyzed этот local file через тот же text-only, bounded,
redacted analyzer path. Если файл содержит embedded Query ID другого запроса,
staging fail-closed до замены существующего case.
Для self-contained one-profile workspace задайте оба пути в ignored local
config и держите generated cases вне source tree:

```json
{
  "manual_profile_dir": "/path/to/profile-inbox",
  "corpus_dir": "/path/to/query-doctor-cases",
  "no_llm": true
}
```

Затем запустите `query-doctor-web --config ./query-doctor-one-profile.json`.
Relative `corpus_dir` в config разрешается от файла config; CLI-флаг
`--corpus-dir` разрешает relative path от current directory. Если оба способа
не заданы, web UI хранит generated Query ID cases в `./cases/cm-corpus` от
директории, где запущен `query-doctor-web`.

### Troubleshooting для одного экспортированного профиля

- `Profile text does not include a Query ID`: сохраните исходное имя скачанного
  из Impala Web UI файла, если оно имеет строгую форму
  `profile_<query-id-high>_<query-id-low>`, или передайте
  `--query-id <query-id>`. Query Doctor также принимает `Query ID:` header
  внутри text export. Если есть несколько источников Query ID, они должны
  совпасть.
- `Parsed operators: 0`: case все равно staged и может открыться в UI, но этот
  text export не содержит parseable `ExecSummary`/operator table. По возможности
  используйте сохраненный Impala text profile export; JSON, Thrift и profile-v2
  payloads остаются вне manual profile path.
- `query-doctor-web --corpus-dir cases/cm-corpus` просит Cloudera Manager
  settings: проверьте, что `query-doctor-analyze` записал complete case в тот
  же corpus directory, который передан web, и запускайте web из того же
  workspace или используйте absolute `--corpus-dir`.

### Дверь 2: synthetic demo

Synthetic demo - самый быстрый способ увидеть продукт. Он deterministic,
local-only и не содержит real SQL, profiles, metadata, hostnames, users или
credentials.

```bash
query-doctor-web --public-demo
```

Этот one-command mode описан в [docs/demo-mode.md](docs/demo-mode.md). Он сам
генерирует synthetic demo pack в dedicated temp directory, включает Python-only
mode, игнорирует default local config и блокирует все POST actions.

Если нужно вручную посмотреть или переиспользовать generated pack, используйте
lower-level commands:

```bash
query-doctor-demo-preflight
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Откройте localhost URL, который напечатает `query-doctor-web`. Начните с
`/?query_group=workloads#scan-context`, чтобы показать компактный Scan context,
workload follow-up links и local synthetic action outcomes перед открытием
Workload Details.

Локальный web UI начинается со status strip Query Inbox, safe
source/window/time-range/query-type scope, compact Filters and views disclosure
для URL-driven source/window/time-range/workflow/query-type scope filters,
result presets, view-only owner/pool tag и opaque owner/pool value filters,
lifecycle, readiness и action filters, а также synthetic Finished Queries
results, если safe materialized cases уже доступны.
Collapsed New scan form
сохраняет safe refresh defaults из этого materialized scope без automatic
collection:

Основная results table сфокусирована на решении: строки attention показывают
одну короткую детерминированную классификацию, priority, duration, owner context
и явный переход в Details. Для repeated workloads в inbox остаются priority,
p95, суммарный observed impact и top owner; p50, pool, bottleneck и supporting
evidence доступны в Workload Details.

![Synthetic Query Doctor Query Inbox status](docs/assets/demo_search.png)

![Synthetic Query Doctor finished queries results](docs/assets/demo_finished_queries.png)

Synthetic demo pack содержит eleven sanitized Impala cases: workload follow-up,
repeated patterns, trusted optimizer recommendations, stats maintenance,
storage/HDFS follow-up, frequent-short workloads, mixed signals,
unknown-but-useful limited evidence и direct-Impala compatibility. Также в нем
есть two read-only raw-free Trino Beta demo cases из static compact diagnosis
facts, без Trino coordinator, Details, reports, optimizer behavior, generated
SQL или SQL execution. Полный список scenarios:
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
Для повторных safe local runs `--reuse-analyzed-profiles-from <cache-root>`
может переиспользовать completed analyzed cases из direct child
`query-doctor-*` batch outputs, когда Query ID и explicit profile reuse
contract совпадают.

## Основные workflows

- `query-doctor-self-test --help`: local installed-package confidence check по
  synthetic data и core offline user paths.
- `query-doctor-deployment-readiness --help`: raw-free deployment summary для
  тех же settings, что использует `query-doctor-web`.
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
использовать read-only режим `query-doctor-web --public-demo`. Shared
`owner_raw` source access требует authenticated per-request viewer identity:
сейчас это явный `viewer_identity_header`, который выставляет только trusted
auth proxy или ingress после удаления входящих копий того же header.

## Safety model

- Python/analyzer-owned facts - единственное trusted diagnostic evidence.
- Raw LLM output недоверенный, пока не пройдет normalization, sanitization и
  validation.
- Trusted browser/report surfaces не должны раскрывать raw SQL, raw profiles,
  raw metadata, local paths, secrets, subprocess output, model/runtime internals
  или raw artifact filenames. Isolated owner-only selected-case source surface -
  узкое browser-исключение для raw SQL.
- External collection должен быть explicit, bounded, read-only, redacted и safe
  by default.
- Local config `privacy_mode` по умолчанию `true`; отключение может ослабить
  local artifact identifier/host masking, но trusted browser/report surfaces все
  равно не показывают raw SQL, profiles или metadata.
- Local config `no_llm=true` оставляет report и optimizer actions на
  deterministic Python-owned output.
- SQL browser exceptions остаются selected-case и owner-gated: Details может
  показать validated optimizer SQL draft для explicit optimizer action при
  `source_visibility=owner_raw`, а isolated owner-only source view может
  показать read-only original SQL для authorized query owner. На localhost raw
  viewer subjects берутся из local collectable owner users; на shared bind они
  должны приходить из authenticated per-request viewer identity. Original
  source view можно глобально отключить через
  `owner_raw_source_enabled=false` или `--disable-owner-raw-source`; каждая
  попытка пишет reason-coded raw-free server audit line. Default `safe` mode
  показывает trusted recommendations/no-rewrite guidance вместо SQL draft.
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
- [deploy/kubernetes/README.md](deploy/kubernetes/README.md): container image,
  Kubernetes manifests, probes и deployment boundaries.
- [deploy/helm/query-doctor/README.md](deploy/helm/query-doctor/README.md):
  Helm chart modes, validation и deployment boundaries.
- [docs/credentials.md](docs/credentials.md): локальная раскладка credentials.
- [docs/roadmap.md](docs/roadmap.md): implemented scope и planned seams.
- [docs/query-optimizer-contract.md](docs/query-optimizer-contract.md):
  optimizer trust boundary.
- [docs/release-checklist.md](docs/release-checklist.md): final tag,
  package-index и visibility-change checklist.

Английская документация является канонической. Русский слой ограничен этим
README и практическими user/operator инструкциями в
[docs/i18n/ru/](docs/i18n/ru/); internal, agent, research, release и engine
deep-dive docs остаются English-only.

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

Репозиторий публичный. Public source releases начинаются с `v0.4.2`; release
candidate `v0.11.0` продолжит эту public source release line после одобрения и
публикации. Older package-index releases остаются видимыми на
[query-doctor on PyPI](https://pypi.org/project/query-doctor/) для
installed-artifact history. Public license is Apache-2.0.

PyPI publishing использует GitHub OIDC Trusted Publishing. Repository-side
`testpypi` и `pypi` environments требуют maintainer approval и не используют
stored package-index API tokens.

Query Doctor web container images публикуются в GitHub Container Registry как
`ghcr.io/alexandrefimov/query-doctor:<version>` из GitHub Releases.

## Licensing

Query Doctor лицензирован под Apache License, Version 2.0 (`Apache-2.0`).
См. [LICENSE](LICENSE).

Apache, Apache Impala и Impala являются товарными знаками The Apache Software
Foundation. Query Doctor - независимый проект; он не одобрен The Apache
Software Foundation или проектом Apache Impala.
