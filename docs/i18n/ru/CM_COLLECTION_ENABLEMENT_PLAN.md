# План включения CM collection

Язык: [English](../../CM_COLLECTION_ENABLEMENT_PLAN.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
сохраняет русскую companion-версию rollout checklist для read-only Cloudera
Manager profile collector.

## Текущее состояние

- CM collector CLI поддерживает real collection только для explicit
  `--query-id`.
- `--dry-run` только строит plan.
- Broad recent-query collection не является standalone collector mode.
- Real collection требует `--redact`.
- Query-id mode ограничен `--limit 1`.
- Max profile size guard default: `52428800` bytes.
- Collector пишет только generated cases; он не запускает analyzer или report
  writer автоматически.
- HTTP GET transport, CM v32 endpoint adapter helpers, output writer, redaction
  helpers и mocked tests уже есть.
- Перед каждым rollout checkpoint запускайте full pytest suite и записывайте
  текущий результат в task/audit output.
- Historical first single-query smoke под `cases/cm-corpus/` прошёл collection,
  analyzer parsing, admin/user report generation и deterministic report
  validation.

## Цель

Включить read-only collection из Cloudera Manager в local generated corpus
directories для Query Doctor regression и smoke testing, осторожно расширяясь
от single-query collection к bounded batch/web Recent scan workflows.

## Не цели

- Нет Impala query execution.
- Нет SQL execution.
- Нет `COMPUTE STATS`.
- Нет `REFRESH`.
- Нет `INVALIDATE METADATA`.
- Нет `INSERT`, `CREATE`, `DROP`, `ALTER`, `DELETE`, `UPDATE`, `TRUNCATE`.
- Нет LLM calls.
- Нет default commit path для collected production profiles.

## Required pre-checks

Перед первым real smoke:

- Подтвердить точные CM API endpoints для query summaries и profile text в
  целевой CM version.
- Подтвердить auth method: basic auth или token.
- Подтвердить TLS CA handling через `--ca-bundle /path/to/company-ca.pem` или
  временную environment setting.
- Подтвердить target cluster и service names.
- Подтвердить, что output directory находится в ignored path, например
  `cases/cm-corpus/`.
- Подтвердить `--redact` для каждого real collection.
- Подтвердить explicit `--query-id` для текущего supported path.
- Подтвердить `--limit 1` для query-id mode.
- Подтвердить осознанное значение `--max-profile-bytes` или safe default.
- Подтвердить bounded `--since-hours`.
- Подтвердить, что generated outputs не staged.

## Supported single-query smoke command

Не помещайте real credentials в docs и не коммитьте их в Git. Предпочитайте
environment variables из временной shell session и не вставляйте secrets в shell
history.

Предпочтительный путь - packaged console script:

```bash
CM_USERNAME=... CM_PASSWORD=... \
query-doctor-collect-cm-profiles \
  --cm-url https://cm.example.com:7183 \
  --cluster CLUSTER_NAME \
  --service IMPALA_SERVICE_NAME \
  --query-id QUERY_ID_WITH_COLON \
  --since-hours 1 \
  --limit 1 \
  --min-duration-sec 60 \
  --max-profile-bytes 52428800 \
  --out cases/cm-corpus \
  --redact \
  --ca-bundle /path/to/company-ca.pem
```

Root-level compatibility launchers могут работать во время migration, но новые
docs должны использовать `query-doctor-*` console scripts.

## Safe rollout steps

Completed single-query rollout:

1. Проверен CM v32 query summary endpoint.
2. Проверен CM v32 profile text endpoint с `format=text`.
3. Добавлен bounded non-dry-run collection для explicit `--query-id`.
4. Выполнен real single-query collection с `--limit 1`, `--redact` и profile
   size guard.
5. Generated files проверены вручную.
6. Analyzer запущен на collected case.
7. Выполнен admin/user report smoke.
8. Generated `analysis_facts.md` и report files удалены после validation.
9. Подтверждено, что `cases/cm-corpus/` остаётся ignored and uncommitted.

Archived historical rollout notes, not current guidance:

These notes predate the current Recent scan batch/web workflow. Do not treat
them as rollout instructions for broad collection. Current supported paths are:

1. standalone collector listing mode for sanitized recent-query candidates, with
   no profile collection and no case output;
2. explicit `--query-id --limit 1 --redact` collection;
3. bounded Recent scan batch/web workflows that collect selected profiles and do
   not auto-run web LLM reports.

## Required generated-output checks

Запустите:

```bash
git status --short
git diff --name-status
git diff --stat
```

Проверьте:

- Нет staged files из `cases/cm-corpus`.
- В files нет credentials.
- Нет staged local config files.
- Raw profile text, SQL и raw CM JSON не печатаются в review notes.
- Production `profile_digest.md` не committed, если он не sanitized и explicitly
  reviewed.

## First-smoke quality checks

Generated case должен содержать:

- `profile_digest.md`;
- `cm_metadata.json`;
- `collection_warnings.txt`.

Проверьте:

- `profile_digest.md` redacted, если использовался `--redact`.
- `cm_metadata.json` не содержит passwords, tokens или auth headers.
- `collection_warnings.txt` не содержит secrets.
- Analyzer читает `profile_digest.md`.
- Action Cards появляются только при наличии evidence.

Historical first-smoke result:

- Ignored local case: `cases/cm-corpus/494ef9bf2699a3c5_5b65e20400000000`.
- Analyzer parsed `169` operators.
- Cardinality anomalies: `0`.
- Memory anomalies: `2`.
- Action Cards были present.
- Admin/user report generation прошёл deterministic validation.
- Generated `analysis_facts.md`, `report_admin.md`, `report_user.md` удалены
  после inspection.

Для текущего smoke status запускайте local validation commands и записывайте
текущий результат в task/audit output, а не считайте historical counts evergreen.

## Rollback/cleanup

Удаляйте только explicit generated paths после проверки:

```bash
rm -rf cases/cm-corpus/<specific_case_dir>
```

Никогда не используйте broad removal commands без подтверждения path. Не
удаляйте existing hand-curated cases. Не удаляйте `profile_digest.md` из
committed test fixtures.

## Open questions

- Exact response shape в установленной CM version.
- Возвращается raw profile или digest.
- Содержит ли query profile text original SQL.
- Сохранять ли query IDs в redacted corpus.
- Должен ли первый corpus оставаться local-only или стать sanitized fixture
  candidate.
- Как выбрать first bounded batch corpus representative queries.
- Должен ли broad collection требовать дополнительный explicit acknowledgement
  flag.
