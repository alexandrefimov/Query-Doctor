# Read-only collector корпуса профилей Cloudera Manager

Язык: [English](../../CM_CORPUS_COLLECTOR_DESIGN.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
сохраняет русскую companion-версию design notes для read-only Cloudera Manager
profile collector.

Текущий предпочтительный entry point: `query-doctor-collect-cm-profiles`.

Инструмент забирает один явный Impala query profile из Cloudera Manager и
сохраняет его как локальный Query Doctor case. Это отдельный read-only collector
для regression fixtures, smoke inputs и улучшения analyzer; он не является
частью core analyzer/report pipeline.

Non-dry-run profile collection намеренно ограничен explicit `--query-id` с
`--redact` и `--limit 1`. Отдельный bounded discovery mode может показать только
sanitized recent-query candidates; он не собирает profiles и не пишет case
directories.

## Цели

- Собирать явные Impala query profiles из Cloudera Manager.
- Сохранять каждый профиль как локальную Query Doctor case directory.
- Поддерживать analyzer regression tests и report smoke tests.
- Не коммитить sensitive или generated data.
- Разрешать только bounded recent-query listing для выбора явных query IDs.

## Не цели

- Нет выполнения запросов.
- Нет выполнения Impala SQL.
- Нет stats refresh.
- Нет metadata invalidation.
- Нет автоматических production changes.
- Нет LLM calls.
- Нет default commit path для collected profiles.

## Принципы безопасности

- Использовать только read-only Cloudera Manager API calls.
- Читать credentials только из environment variables или explicit local config,
  ignored by Git.
- Никогда не печатать passwords, tokens или Authorization headers.
- Считать collected profiles sensitive generated output.
- Держать output directory в `.gitignore`.
- Перед sharing или commit любого collected profile нужна
  redaction/anonymization и explicit review.
- По умолчанию ничего не upload'ить; единственная network destination - source
  Cloudera Manager API.

## Текущий CLI

Поддержанный single-query режим:

```bash
CM_USERNAME=... CM_PASSWORD=... \
query-doctor-collect-cm-profiles \
  --cm-url https://cm.example.com:7183 \
  --cluster CLUSTER_NAME \
  --service IMPALA_SERVICE_NAME \
  --query-id QUERY_ID_WITH_COLON \
  --limit 1 \
  --max-profile-bytes 52428800 \
  --out cases/cm-corpus \
  --redact
```

Bounded recent-query discovery:

```bash
CM_USERNAME=... CM_PASSWORD=... \
query-doctor-collect-cm-profiles \
  --cm-url https://cm.example.com:7183 \
  --cluster CLUSTER_NAME \
  --service IMPALA_SERVICE_NAME \
  --list-recent-queries \
  --recent-limit 100 \
  --recent-select 5 \
  --recent-window-minutes 60 \
  --recent-min-duration-sec 1 \
  --recent-order duration-desc \
  --recent-output-json /tmp/query-doctor-recent-candidates.json
```

Этот режим выполняет только read-only query-summary listing, печатает sanitized
candidates, не показывает full SQL, не fetch'ит profile text и не создаёт output
cases. JSON из `--recent-output-json` содержит только sanitized summary fields и
SQL verb, не full SQL.

Рекомендуемый workflow:

1. Запустить `--list-recent-queries`.
2. Вручную review выбранных query IDs.
3. Собрать каждый выбранный profile отдельной командой с explicit `--query-id`,
   `--limit 1` и `--redact`.

## Credentials и config

Collector читает non-secret defaults из `--config PATH`. Если `--config` не
передан, `query-doctor-config.json` загружается автоматически, когда файл есть в
current working directory. Legacy `.query-doctor-cm.local.json` remains
supported as ignored fallback.

Precedence:

1. CLI flags
2. Environment variables
3. Config file
4. Built-in defaults

Начните с committed safe template:

```bash
cp query-doctor-config.example.json query-doctor-config.json
```

Passwords, tokens, cookies, Authorization headers и другие secret-bearing fields
rejected in config. Use environment variables for secrets:

```bash
export CM_PASSWORD='...'
```

Для local service runs предпочтительна dedicated credentials directory из
`docs/credentials.md`:

```text
~/.qdcreds/cm-ro.env
~/.qdcreds/query-doctor.keytab
~/.qdcreds/cm-chain.pem
```

Use `scripts/query-doctor-web-local` to source CM credentials, refresh Kerberos
cache from keytab and start the web UI. Repository config should store only
non-secret references such as `ca_bundle` and `krb5ccname`.

Supported environment variables:

- `CM_URL`
- `CM_USERNAME`
- `CM_PASSWORD`
- `CM_TOKEN`, если target CM deployment поддерживает token auth
- `CM_CA_BUNDLE` для TLS trust
- `CM_MAX_PROFILE_BYTES`

Avoid:

- hardcoded credentials;
- credentials in Git;
- credentials in logs.

После local config и `CM_PASSWORD` bounded recent-query discovery can run
without repeating connection flags:

```bash
query-doctor-collect-cm-profiles \
  --list-recent-queries \
  --recent-output-json /tmp/query-doctor-recent-candidates.json
```

## Output layout

Текущий generated output:

```text
cases/cm-corpus/
  <query_id_or_safe_slug>/
    profile_digest.md
    cm_metadata.json
    collection_warnings.txt
```

Raw profiles сейчас не входят в safe output. Если они понадобятся позже, нужен
отдельный review:

```text
cases/cm-corpus/
  <query_id_or_safe_slug>/
    raw_profile.txt
    profile_digest.md
    cm_metadata.json
    collection_warnings.txt
```

Collected corpus является generated и sensitive. По умолчанию он должен быть
ignored, если не был явно sanitized и reviewed.

## Data minimization

Хранить только то, что нужно Query Doctor testing:

- query ID;
- start/end time, если доступны;
- duration;
- status;
- pool/admission info, если доступны;
- profile или profile digest;
- original SQL только если он уже есть в profile и нужен для test goal.

SQL, table names, users, pools, hostnames, query IDs, timestamps и literal values
могут быть sensitive.

## Redaction strategy

`--redact` должен сохранять analyzer-relevant structure и снижать
чувствительность:

- заменять usernames;
- заменять hostnames по умолчанию;
- опционально заменять database/table names;
- опционально убирать или нормализовать literal values из SQL;
- сохранять operator IDs, counters, row counts, memory values, bytes, timings и
  plan/operator shape;
- оставлять достаточно структуры для deterministic analyzer tests.

For private node-level diagnostics, host redaction can be explicitly disabled
with `--no-redact-hosts` or `"redact_hosts": false` while keeping general
`--redact` enabled. These artifacts are local-only diagnostic data and must not
be shared or committed.

Redaction по возможности должна быть deterministic, чтобы fixtures оставались
stable across runs.

## Pagination и rate limiting

- Обрабатывать Cloudera Manager API pagination.
- Поддерживать `--limit`.
- Поддерживать явное time window, например `--since-hours`.
- Не перегружать Cloudera Manager.
- Retry только safe `GET` requests.
- Использовать conservative connect/read timeouts.
- Добавлять небольшой backoff на transient API failures.

## Failure behavior

- Partial failures не должны удалять уже collected cases.
- Писать `collection_warnings.txt` для per-query failures или redaction warnings.
- Fail closed на authentication и TLS errors.
- Не пропускать safety errors silently.
- Dry-run должен показывать candidate query IDs и metadata без записи profiles.

## Git hygiene

Сгенерированные corpus outputs должны оставаться ignored:

```gitignore
cases/cm-corpus/
cases/*/raw_profile.txt
cases/*/cm_metadata.json
cases/*/collection_warnings.txt
```

Do not commit collected production profiles unless they are sanitized and
explicitly reviewed. Предпочитайте маленькие synthetic fixtures.

## Testing strategy

Tests должны mock'ать Cloudera Manager API responses. Tests не должны
использовать network access.

Покрытие должно включать:

- pagination;
- filters;
- output layout;
- credential handling без печати secrets;
- redaction;
- dry-run behavior;
- generated outputs ignored;
- partial failure behavior.

## Open questions

- Точные Cloudera Manager API endpoints для query lists и profiles.
- Хранить raw profiles, только `profile_digest.md` или оба файла.
- Строгость redaction и нужно ли включать её by default.
- Расположение output по умолчанию для corpus.
- Collector должен только собирать profiles или когда-нибудь опционально
  запускать analyzer entry points.
- Как выбрать representative query corpus по slow, failed, cancelled и
  successful queries.
- Сохранять query IDs, hash'ить или заменять в sanitized fixtures.
