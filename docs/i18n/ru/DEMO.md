# Локальный UI demo Query Doctor

Last reviewed: 2026-06-19

Язык: [English](../../DEMO.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
сохраняет русскую companion-навигацию по локальному demo guide и может отставать
от английского источника.

`query-doctor-web` запускает небольшой localhost-only UI для Query Doctor.
Текущая навигация строится вокруг Diagnose, Details pages, Help,
автогенерации Python report для Known Query ID и explicit selected-case LLM
report/optimizer actions. В Diagnose находятся Recent queries и вторичный
режим Known Query ID.

Это не production UI. Для публичных repeatable demo используйте
`query-doctor-web --public-demo`; запускайте `query-doctor-demo` напрямую
только когда нужно посмотреть или переиспользовать generated pack. Не
используйте старые prepared-pack case IDs, account names, local deep links или
environment-specific query IDs.

## Synthetic demo startup

Для обычного read-only public demo запускайте одну команду:

```bash
query-doctor-web --public-demo
```

Она сама генерирует fresh synthetic pack в system temp directory, подключает
web UI к этому pack, включает Python-only mode, игнорирует default local config
и owner-source environment hints, отклоняет explicitly loaded external source
settings и блокирует все POST routes. Pack также содержит static read-only
Trino Beta demo cases из raw-free compact diagnosis facts; они не обращаются к
Trino coordinator и не включают Details, trusted reports, optimizer behavior,
generated SQL или SQL execution.

Если нужно вручную посмотреть или переиспользовать generated pack:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Откройте localhost URL, который напечатает `query-doctor-web`. Demo generator
требует dedicated `query-doctor-*` temp output path; generated pack держите вне
репозитория. Полезные фильтры:

```text
/?query_group=workloads#scan-context
/?query_group=workloads#recent-results
/?query_group=optimization#recent-results
/?query_group=stats#recent-results
/?query_group=frequent_short#recent-results
```

Synthetic pack не вызывает Cloudera Manager, Impala, Prometheus, local
generation backend или network и не является performance evidence. Trino Beta
demo section показывает bounded compact diagnosis demo, а не production Trino
support.

## Read-only public demo

Не передавайте real local config, Kerberos material, cluster credentials или
cases из real environments в public demo.

## Запуск

Используйте ignored local config и credentials из environment variables. Для
Cloudera Manager (CM) workflow Query Doctor ожидает read-only CM credentials в
`~/.qdcreds/cm-ro.env`. Для direct Impala workflow храните daemon hosts,
Prometheus URLs, Kerberos service names и metadata coordinator settings в
`~/.qdcreds/query-doctor-config.json` или другом ignored local config. Значения
секретов не хранятся в репозитории и не попадают в committed config.

Предпочтительный локальный запуск:

```bash
scripts/query-doctor-web-local
```

Для local Python-only session, где selected-case report и optimizer actions не
вызывают LLM:

```bash
scripts/query-doctor-web-local-no-llm
```

Ручной запуск:

```bash
mkdir -p ~/.qdcreds
cp query-doctor-config.example.json ~/.qdcreds/query-doctor-config.json
# Отредактируйте config под CM или direct Impala / Prometheus / metadata.
set -a
source ~/.qdcreds/cm-ro.env
set +a
query-doctor-web \
  --config ~/.qdcreds/query-doctor-config.json \
  --host 127.0.0.1 \
  --port 8765
```

Откройте:

```text
http://127.0.0.1:8765
```

Для CLI single-query collection используйте тот же env-файл:

```bash
set -a
source ~/.qdcreds/cm-ro.env
set +a
DEMO_CASE_OUT="$(mktemp -d)"
query-doctor-collect-cm-profiles \
  --query-id QUERY_ID_WITH_COLON \
  --limit 1 \
  --out "$DEMO_CASE_OUT" \
  --redact \
  --ca-bundle ~/.qdcreds/cm-chain.pem
```

## Основные поверхности

- **Diagnose / Recent queries**: bounded scan завершенных queries из
  настроенного источника, CM summaries или direct Impala daemon query-list,
  selected profile collection, deterministic ranking, no automatic LLM reports.
- **Diagnose / Running now**: тот же result shape для running queries, без
  date/hour filters и с lower-confidence live evidence.
- **Diagnose / Known Query ID**: один explicit Impala query ID, deterministic
  Python report в том же submit-job, без automatic LLM или optimizer jobs; по
  умолчанию используется Cloudera Manager, либо direct Impala daemon profile
  endpoints при соответствующем local config. Input очищается после submit,
  результат добавляется в Known Query ID analysis table.
- **Details**: deterministic details, generated Python report when available,
  плюс explicit LLM Report / Query LLM optimizer actions.
- **Help**: workflow, safety boundaries и ссылки на GitHub documentation внутри
  продукта.

Direct route **Query Optimizer** остается read-only compatibility/safety-test
surface для одного safe `SELECT` / `WITH ... SELECT`; pasted SQL не выполняется
и не echo'ится после submit. Сейчас это не primary demo navigation item.

## Безопасность

- Сервер по умолчанию слушает только `127.0.0.1`.
- Non-local bind требует explicit `--allow-nonlocal-web-bind`.
- Не публикуйте ordinary local mode наружу. Для public synthetic demo
  используйте `query-doctor-web --public-demo`.
- Web forms не принимают CM URLs, credentials или local config contents.
- Credentials остаются только в environment процесса web server.
- Known Query ID collection explicit и redacted. Direct Impala Known Query ID
  не выполняет SQL и не собирает Cloudera Manager events. Direct Impala
  Recent/Running может читать bounded daemon query-list endpoints, а
  Prometheus runtime metrics доступны только как optional bounded context.
- Raw profile text, raw SQL, raw provider API responses, raw metadata и
  credentials не должны появляться в UI, logs, docs или reports.

Generated local case data может оставаться sensitive даже после redaction. Не
коммитьте generated cases, reports, metadata, local config, browser output,
screenshots from real clusters или credentials.

## Demo storyline

Показывайте Query Doctor как engineering diagnostic and validation tool:

1. Scan context workload follow-up как первый экран ценности;
2. deterministic candidate ranking from generated profile/analyzer facts;
3. Details page before any report or optimizer action;
4. explicit trusted report, который формулирует Python-owned facts;
5. explicit Query LLM optimizer с trusted recommendations, trusted no-rewrite
   guidance или validated SQL draft только там, где это поддержано;
6. statistics-maintenance candidate evidence с required confirmation steps;
7. mixed-signal и unknown-but-useful cases без false certainty;
8. direct Impala compatibility с non-fatal optional endpoint gaps;
9. rejected/partial optimizer output остается untrusted и hidden.

Synthetic scenarios описаны в [demo-cases.md](demo-cases.md); detailed
talk-track для data engineers - в
[demo-data-engineer-brief.md](demo-data-engineer-brief.md).

Не показывайте raw SQL, raw profiles, raw metadata, local artifact paths,
model/runtime internals, command output, account names, real query IDs или
local config details в demo.

## Pre-demo smoke

```bash
python3 -m pytest -q tests/test_demo_data.py tests/test_web_ui_home.py tests/test_web_ui_help.py
python3 -m pytest -q tests/test_web_server.py tests/test_web_optimizer.py tests/test_query_optimizer.py
git diff --check
```
