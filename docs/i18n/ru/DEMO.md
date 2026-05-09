# Локальный UI demo Query Doctor

Язык: [English](../../DEMO.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
сохраняет русскую companion-навигацию по локальному demo guide и может отставать
от английского источника.

`query-doctor-web` запускает небольшой localhost-only UI для Query Doctor.
Текущая навигация строится вокруг Diagnose, Details pages, Help и explicit
selected-case LLM actions. В Diagnose находятся Recent queries и вторичный
режим Known Query ID.

Это не production UI.

## Запуск

Используйте ignored local Cloudera Manager (CM) config и credentials из
environment variables. На локальной машине Query Doctor ожидает read-only CM
credentials в
`~/.qdcreds/cm-ro.env`; значения секретов не хранятся в репозитории и не
попадают в committed config.

Предпочтительный локальный запуск:

```bash
scripts/query-doctor-web-local
```

Ручной запуск:

```bash
cp query-doctor-config.example.json query-doctor-config.json
set -a
source ~/.qdcreds/cm-ro.env
set +a
query-doctor-web \
  --config query-doctor-config.json \
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
query-doctor-collect-cm-profiles \
  --query-id QUERY_ID_WITH_COLON \
  --limit 1 \
  --out /tmp/query-doctor-demo-case \
  --redact \
  --ca-bundle ~/.qdcreds/cm-chain.pem
```

## Основные поверхности

- **Diagnose / Recent queries**: bounded scan завершенных Cloudera Manager (CM)
  summaries по умолчанию, selected profile collection, deterministic ranking,
  no automatic LLM reports.
- **Diagnose / Running now**: тот же result shape для running queries, без
  date/hour filters и с lower-confidence live evidence.
- **Diagnose / Known Query ID**: один explicit Impala query ID без automatic
  LLM; по умолчанию используется Cloudera Manager, либо direct Impala daemon
  profile endpoints при соответствующем local config. Input очищается после
  submit, результат добавляется в Known Query ID analysis table.
- **Details**: deterministic details плюс explicit LLM Report / Query LLM
  optimizer actions.
- **Help**: workflow, safety boundaries и ссылки на GitHub documentation внутри
  продукта.

Direct route **Query Optimizer** остается read-only compatibility/safety-test
surface для одного safe `SELECT` / `WITH ... SELECT`; pasted SQL не выполняется
и не echo'ится после submit. Сейчас это не primary demo navigation item.

## Безопасность

- Сервер по умолчанию слушает только `127.0.0.1`.
- Non-local bind требует explicit `--allow-nonlocal-web-bind`.
- Не публикуйте этот сервер наружу.
- Web forms не принимают CM URLs, credentials или local config contents.
- Credentials остаются только в environment процесса web server.
- Known Query ID collection explicit и redacted; direct Impala mode does not
  discover queries, collect metrics/events, or execute SQL.
- Raw profile text, raw SQL, raw CM JSON и credentials не должны появляться в
  UI, logs, docs или reports.

## Generated files

UI пишет ignored local files under the configured corpus directory:

```text
cases/cm-corpus/<safe_query_slug>/
  profile_digest.md
  cm_metadata.json
  collection_warnings.txt
  analysis_facts.md
  diagnosis.md
  optimized_query.sql
```

Эти файлы generated и могут оставаться sensitive даже после redaction. Не
коммитьте их и local config files.

## Demo storyline

Показывайте Query Doctor как engineering diagnostic and validation tool:

1. deterministic candidate ranking from CM/profile facts;
2. Details page before any LLM action;
3. explicit LLM Report, который формулирует Python-owned facts;
4. explicit Query LLM optimizer с validated SQL draft или safe no-draft outcome;
5. optional external read-only Impala smoke benchmark для одного validated
   draft.

Prepared case pack описан в `docs/demo-cases.md`; detailed talk-track для data
engineers - в `docs/demo-data-engineer-brief.md`.

Не показывайте raw SQL, raw profiles, raw metadata, local artifact paths,
model/runtime internals или subprocess output в demo.

## Pre-demo smoke

```bash
python3 -m pytest -q tests/test_analyzer_cli.py tests/test_report_sanitizer.py tests/test_query_optimizer.py tests/test_optimizer_sql.py
python3 -m pytest -q tests/test_web_server.py tests/test_web_optimizer.py tests/test_web_ui_home.py tests/test_web_ui_help.py
git diff --check
```
