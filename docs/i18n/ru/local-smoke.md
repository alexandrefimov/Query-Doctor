# Локальные smoke workflow

Last reviewed: 2026-06-01

Язык: [English](../../local-smoke.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
дает русскую companion-навигацию по основным smoke-проверкам и может отставать
от английского источника.

## Общие правила

- Начинайте с понятного состояния: `git status --short`.
- Используйте только ignored local cases.
- Не stage'ите и не коммитьте generated reports, metadata outputs, local config
  или реальные профили.
- Для новых команд используйте packaged `query-doctor-*` console scripts.
  Root-level compatibility launchers удалены; без установленных console scripts
  используйте `python -m query_doctor.cli.<module>` из checkout.
- Не копируйте в issues/docs raw profiles, raw SQL, raw metadata, hostnames,
  IPs, credentials или production identifiers.

## Packaging smoke

Проверяйте package entry points в отдельном venv:

```bash
python3 -m venv /tmp/query-doctor-pkg-smoke-venv
/tmp/query-doctor-pkg-smoke-venv/bin/python -m pip install -e .
```

Если окружение без сети и editable install пытается скачать PEP 517 build
dependencies, используйте committed legacy editable-install shim:

```bash
/tmp/query-doctor-pkg-smoke-venv/bin/python setup.py develop
```

Минимальные проверки:

```bash
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-demo-preflight
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-analyze --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-pipeline --help
/tmp/query-doctor-pkg-smoke-venv/bin/query-doctor-web --help
```

Если editable install создал `query_doctor.egg-info/`, удалите этот generated
artifact перед commit.

## Analyzer и report smoke

Analyzer-only:

```bash
CASE="cases/cm-corpus-hostalias/<host-skew-case>"
query-doctor-analyze "$CASE"
```

Report smoke:

```bash
query-doctor-pipeline "$CASE" --mode admin --out diagnosis_smoke.md
```

Проверяйте только summary/evidence и trusted report sections. Не печатайте full
profiles. Generated report files остаются внутри ignored case directories.

## Corpus smoke

```bash
query-doctor-corpus-smoke cases/cm-corpus
query-doctor-corpus-smoke cases/cm-corpus-hostalias
```

Corpus smoke локальный и analyzer-only: он не вызывает Cloudera Manager,
Impala, Ollama или report generation.

## Real Impala metadata smoke

Запускайте только если намеренно проверяете explicit metadata collector против
real Impala coordinator. Output держите под `/tmp` и не коммитьте.

Ключевые предусловия:

- Kerberos ticket уже должен существовать.
- Для reproducible subprocess smoke используйте `KRB5CCNAME=FILE:...`.
- Secrets остаются только в environment или `~/.qdcreds/`.
- Local config хранит только non-secret references.
- Collector выполняет только `SHOW CREATE TABLE`, `SHOW TABLE STATS`,
  `SHOW COLUMN STATS`.

Collector smoke:

```bash
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-collect-impala-context \
  --table scratch_db.query_doctor_meta_probe \
  --out /tmp/query-doctor-impala-collector-smoke-test-table \
  --coordinator impala-coordinator.example.net:21050 \
  --auth kerberos \
  --protocol hs2 \
  --timeout-sec 30 \
  --max-output-bytes 200000 \
  --redact
```

Pipeline metadata smoke:

```bash
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-pipeline "$SMOKE_OUT" \
  --metadata-mode on \
  --metadata-coordinator impala-coordinator.example.net:21050 \
  --metadata-protocol hs2 \
  --metadata-max-tables 1 \
  --metadata-redact \
  --stop-after-analysis
```

`--stop-after-analysis` проверяет analyzer/metadata path без LLM wording.

## Trino Kerberos smoke

Запускайте только как operator-only development smoke для проверки
Kerberos/SPNEGO-доступа к Trino coordinator. Trino path в Query Doctor
ограничен sanitized offline evidence package import, bounded local event-store
import, bounded HTTP event archive import, bounded HTTP query-detail archive
import, bounded local query-detail import, bounded local query-list aggregate
import, bounded local statement-stats import, event-source contract checking и
dry-run coordinator query-info target checking, plus bounded pruned
coordinator query-info probing/import:
это не live Trino collector, не live engine selector, не UI route, не report
surface, не optimizer path, не metadata path и не live support claim.

Скрипт выполняет только built-in read-only smoke statements:

- actor identity check;
- source listing check;
- optional count check для одного явного `catalog.schema.table`;
- optional one-row sample check для одного явного `catalog.schema.table`.

Скрипт не принимает arbitrary SQL. Он пишет только безопасный
`trino_smoke_summary.json` со statuses, row counts, field counts, page counts,
safe error categories и redaction assertions. Он не пишет statement text,
result values, query identifiers, actor identity values, coordinator hostnames,
object names или raw failure details.

Сначала подготовьте Kerberos cache. Если HTTP service principal coordinator
находится в realm, отличном от client principal, используйте локальный
`KRB5_CONFIG`, который мапит coordinator host на service realm.

```bash
KRB5_CONFIG=/tmp/query-doctor-trino-krb5.conf \
  kinit -kt /path/to/user.keytab \
  -c FILE:/tmp/query-doctor-trino-smoke-krb5cc \
  user@EXAMPLE.COM
```

Запустите smoke с явными table arguments для table-specific checks:

```bash
rm -rf /tmp/query-doctor-trino-smoke

python3 scripts/trino_kerberos_smoke.py \
  --server https://trino-coordinator.example.net \
  --client-user user \
  --kerberos-principal user@EXAMPLE.COM \
  --service-name HTTP \
  --krb5-config /tmp/query-doctor-trino-krb5.conf \
  --krb5-ccname FILE:/tmp/query-doctor-trino-smoke-krb5cc \
  --count-table sample_catalog.sample_schema.sample_table \
  --sample-table sample_catalog.sample_schema.sample_table \
  --out /tmp/query-doctor-trino-smoke
```

Expected smoke behavior:

- uses `curl` with Kerberos/SPNEGO и configured service name;
- sends Trino client user только в protocol header;
- submits только built-in allowlisted smoke statements;
- follows bounded Trino protocol pages;
- prints только per-check safe status lines;
- writes только `trino_smoke_summary.json` under selected `/tmp` output
  directory.

## Bounded Recent scan smoke

Первый проход без metadata и LLM:

```bash
CM_PASSWORD=... \
KRB5CCNAME=FILE:/tmp/krb5cc_query_doctor_user \
query-doctor-batch-recent \
  --out /tmp/query-doctor-recent-batch-example \
  --recent-window-minutes 1440 \
  --cm-inspect-limit 5000 \
  --triage-profile-limit 5000 \
  --min-duration-sec 10 \
  --order duration-desc \
  --metadata-mode off \
  --top-reports 0 \
  --cm-jobs 20 \
  --jobs 4 \
  --metadata-jobs 1 \
  --overwrite
```

`--metadata-jobs` имеет default `5` и hard cap `5`; в conservative smoke
examples его можно снижать до `1`. `--allow-high-jobs` нужен только когда
analyzer `--jobs` выше обычного cap, а metadata refresh все равно ограничен
отдельным `--metadata-jobs <= 5`.

Если metadata включена, `--metadata-top-limit` расходуется на top collectable
cases. Для Cloudera Manager Recent batches реальные table references могут
передаваться во внутренний bounded metadata subprocess из discovery statements,
но progress, summaries и report-visible output остаются raw-free.

Batch workflow остается двухэтапным:

- bounded CM discovery или direct Impala daemon query-list discovery для
  настроенного direct Impala cluster;
- explicit per-query-id profile collection;
- analyzer scoring from `analysis_facts.md`;
- full reports только для явно выбранных/top-ranked suspicious cases.

## Direct Impala / Prometheus smoke

Для Ambari-style или vanilla Impala кластеров без Cloudera Manager держите real
hosts, Prometheus URL и Kerberos service names только в ignored local config.
Текущий поддержанный direct Impala baseline:

- bounded Recent и Running scans читают daemon query-list endpoints и потом
  собирают selected profiles;
- Known Query ID собирает один explicit query ID через daemon profile endpoints;
- direct Impala не добавляет Cloudera Manager events и не выполняет SQL;
- Prometheus runtime metrics опциональны, bounded, allowlisted и пишутся только
  как normalized runtime context.

Daemon query-list history у direct Impala маленькая и может быстро заполниться
metadata/validation statement-ами (`SET`, `SHOW`). Если endpoint уже на
retained-log лимите, большой Search depth не вернет более старые entries. Для
metadata-path проверки используйте свежий table-backed `SELECT` и сразу
запускайте Known Query ID smoke; за load balancer или ingress настраивайте
explicit daemon profile hosts, когда они доступны.

Для current-upstream Impala follow-up используйте канонический английский
runbook в [local-smoke.md](../../local-smoke.md). Public docs должны оставаться
generic: local cluster selector, connectivity command, real endpoints,
generated cases, query IDs, raw profiles и smoke output хранятся только в
ignored local notes или config.
После no-LLM scan запускайте
`scripts/audit_profile_evidence_gates.py --fail-on-issues`.

Для Ambari deployments, где Impala использует service principal `hive`,
указывайте `impala_kerberos_service_name` и `metadata_kerberos_service_name` в
ignored local config или соответствующих CLI flags.

## Финальные проверки

```bash
pre-commit run --all-files
python3 -m pytest -q
git diff --check
query-doctor-demo-preflight
git status --short
```

Если preflight предупреждает о raw artifact names или secret-like tokens внутри
самого smoke/credentials документа, проверьте, что это intentional safety
documentation, а не browser-visible product output.
