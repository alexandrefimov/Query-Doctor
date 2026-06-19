# Чеклист evidence export из тестового Trino-кластера

Last reviewed: 2026-05-29

Язык: [English](../../trino-test-cluster-evidence-checklist.md) | Русский

Английская версия является канонической. Эта страница - русское companion
резюме первого безопасного handoff из тестового Trino-кластера.

Manifest и redaction note оформляйте по
[шаблонам evidence package](trino-evidence-package-templates.md). Для
release-facing private preview wording используйте
[Trino private preview release path](trino-private-preview-release.md).

## Статус

Это не live collector, не support announcement, не engine selector и не
Details/trusted-report surface. Separate isolated compact-diagnosis page
принимает только already raw-free direct boundary JSON excluding local metadata
summary boundaries или selected sample boundary из package boundary export. Query Doctor не получает
прямой доступ к Trino-кластеру на этом этапе.

## Цель

Перейти от synthetic fixtures к operator-exported sanitized evidence. Первый
пакет должен проверить, можно ли уже произведённые Trino events/query details
сжать до raw-free fixture contract без SQL execution и без raw payloads.

## Запрещено

- Не запускать Trino SQL через Query Doctor.
- Не использовать `POST /v1/statement` как путь сбора.
- Не запускать Query Doctor-generated `EXPLAIN ANALYZE`.
- Не передавать raw Web UI pages, raw event dumps, raw query-info JSON, logs,
  stack traces, object-storage paths или connector payloads.
- Не включать query text, query IDs, users, groups, hostnames, endpoint URLs,
  catalog/schema/table/column names, session properties, headers, trace tokens,
  credentials, local paths, artifact names или connector internals.

## Что можно экспортировать первым

Первый пакет должен содержать только compact evidence:

- completed event-listener records, сведённые к accepted compact fields;
- resource-group queue timing только как query-specific duration/count facts;
- statement-statistics snippets с lifecycle, timing, resource, stage, blocked,
  spill и compact summary fields;
- sanitized `/v1/query` list summary exports только как aggregate contract
  probes, где raw records, query text, identities, locations, object context и
  failure details удалены до handoff;
- compact query-detail exports только после удаления identifiers, object
  names, endpoints, stack traces, raw stage/task records и connector
  internals;
- metadata allowlist source-contract summaries только после
  `query-doctor-trino-metadata-source-contract-check --redaction-reviewed`;
  raw relation/column allowlist остается local, а в handoff идет только
  path-free и identifier-free summary;
- compact metadata summary exports только как aggregate relation/column coverage
  и stats-completeness counts после удаления raw identifiers и metadata values;
  проверяйте их через
  `query-doctor-trino-metadata-summary-import --redaction-reviewed`;
- manifest с source type, Trino version, source schema version, connector
  family category, export window, record count, byte count, redaction status и
  known omissions.

## Минимальный набор кейсов

Нужны самые маленькие безопасные samples для:

- successful completed query;
- failed query только с allowlisted failure category;
- queued или resource-group delayed query;
- blocked query;
- spill observed;
- stage/task skew candidate;
- connector metric present и absent;
- missing-field case;
- unknown или unsupported source-contract version;
- sanitized query-list contract probe aggregate;
- compact query-detail stage/task summary case;
- oversized или over-deep rejection case на synthetic padding;
- unsafe raw field rejection case на synthetic sentinel values.

## Sanitization gate

Перед repo или issue attachment нужно удалить:

- raw SQL и prepared statements;
- query IDs, trace tokens, transaction IDs, session IDs и request headers;
- users, groups, roles, client tags, client info и source labels;
- hostnames, endpoint URLs, object-storage paths, local paths, topic names,
  database names, file names и artifact names;
- catalog/schema/table/column/partition/manifest/object names;
- stack traces, raw exception messages, warning payloads и connector internals;
- secrets, credentials, tokens, passwords, keys, cookies, TLS material,
  Kerberos caches и extra credentials.

Compact boolean markers должны оставаться booleans. Например, `fullyBlocked` и
resource `queued` могут использоваться как blocked или queue-absence evidence
только в typed boolean форме.

Если redaction status неизвестен, export надо reject-ить или пересобрать.

## Handoff package

Первый пакет должен содержать:

- один sanitized compact sample на каждый минимальный кейс;
- manifest sample set;
- redaction note с классами удалённых полей, но не с удалёнными значениями;
- optional metadata source-contract summary output, но не raw allowlist contract
  с relation или column names;
- optional compact metadata summary import output, но не raw metadata values или
  object identifiers;
- known-gap note для отсутствующих connector families или source schema
  versions;
- никаких raw companion archives.

Package label должен быть safe local label: без cluster, query, user, host,
catalog, schema, table, topic, path, file или artifact names.
Локальный package-intake wrapper: `manifest`, `redaction_note`, `samples`;
accepted sample payloads остаются fixture work, а не live collection.
Перед планированием operator sample labels запускайте
`python3 scripts/trino_evidence_package_requirements.py --json`: helper печатает
Python-owned accepted sample cases, package/sample source types, known fixture
contract/version labels, redaction classes, rejection reasons, sentinel tests,
boundary assertions и size limits. Он не читает Trino endpoint и не создает
support claim.
Перед fixture conversion запускайте
`python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>`.
Команда печатает только safe summary и не должна echo raw payloads, raw values
или input path.
Для retained package-level handoff evidence сначала запускайте
`python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json> --summary-json <raw-free-trino-package-handoff-summary.json>`.
Затем группируйте уже raw-free summaries через
`python3 scripts/build_trino_evidence_handoff_suite_manifest.py --redaction-reviewed --handoff-summary-json <summary-a.json> --handoff-summary-json <summary-b.json> --out <trino-evidence-handoff-suite.json>`
и проверяйте их командой
`python3 scripts/audit_trino_evidence_handoff.py --handoff-suite-manifest <trino-evidence-handoff-suite.json> --require-min-inputs <minimum-retained-package-count> --summary-json <raw-free-trino-evidence-handoff-suite-summary.json>`.
Suite path повторно открывает только retained raw-free summaries, не packages и
не raw exports. Builder и audit требуют safe relative `*.json` references,
reject-ят output/input overlap, missing или duplicate summary artifacts, unsafe
references, drifted manifest schema/redaction/no-support metadata и raw-like
retained summary content, а suite summary остается aggregate-only machine
evidence с fixed count, diagnostic-lane, issue-category и requirement sections,
не artifact references или paths.
Если handoff содержит compact sanitized local event-listener store без package
wrapper, запускайте
`query-doctor-trino-event-store-import --redaction-reviewed <sanitized-event-store.json-or-ndjson>`.
Команда читает один explicit local JSON/NDJSON file, validates compact event
records и печатает только safe summary или raw-free boundary JSON.
Для одного explicit real-cluster query-info handoff dev-only
`scripts/trino_one_query_live_handoff.py` может использовать либо local
operator-managed `--auth-header-file`, либо explicit Kerberos/SPNEGO fetch из
already prepared local ticket cache через `--kerberos-principal` и
`--krb5-ccname`. Kerberos form остается одним bounded
`GET /v1/query/{queryId}?pruned=true` read, не submit-ит SQL, не читает
Kubernetes secrets и не печатает principal, ticket-cache path, coordinator URL,
Query ID, curl stderr, auth material, raw QueryInfo или output paths.
Для live handoff runs предпочитайте
`--query-id-file <operator-query-id-file>`, чтобы selected Query ID не попадал
в shell history и process arguments. Файл должен содержать ровно один supported
Trino Query ID, оставаться local to operator environment и не использоваться
как output artifact. Finished QueryInfo может исчезнуть из coordinator раньше,
чем QueryMonitor logs age out, поэтому выбирайте current или very recent Query
ID. HTTP 404 или 410 от любого one-query coordinator fetch path трактуется как
stale QueryInfo и сообщается только redacted operator hint; не сохраняйте и не
echo-ите response body, coordinator URL, Query ID, auth material, curl stderr или
local artifact paths. HTTP 401 или 403 трактуется как auth rejected и сообщается
только redacted operator hint, чтобы обновить auth reference или ticket; не
сохраняйте и не echo-ите rejected auth material, principal, response body,
coordinator URL, Query ID, curl stderr или local artifact paths.
Retained one-query handoff suites должны запускать
`scripts/audit_trino_compact_readiness.py --handoff-suite-manifest` с
`--require-readiness-summary-json`,
`--require-min-trino-version-families <minimum-trino-version-family-count>` и
повторяемым `--require-trino-version-family <safe-trino-version-family>`, если
нужно доказать конкретную broad Trino version family. Manifest entries могут
ссылаться только на safe relative per-entry readiness summary JSON artifacts из
one-query wrapper. Summary может записывать только safe broad-label counters,
без raw version strings, coordinator URLs, Query IDs, auth material, raw
QueryInfo или artifact paths.

Raw exports остаются только в operator-controlled Trino environment, не в Query
Doctor workspace и не в prompts.

## Acceptance gate

Пакет готов к Query Doctor fixture work только если:

- каждый sample вручную проверен как raw-free;
- каждый sample проходит maximum size и nested-depth bounds fixture contract;
- каждый supported fact query-specific или явно aggregate и version-scoped;
- каждое отсутствующее или unsupported поле имеет `unknown` или omission reason;
- не нужен Details route, trusted report, optimizer behavior, live adapter или
  public README live-support claim; packaged offline import остается raw-free.
  Separate isolated compact-diagnosis page принимает только already raw-free
  direct boundary JSON excluding local metadata summary boundaries или selected
  sample boundary из package boundary export.

Следующий шаг после accepted package - raw-free import/fixture work: добавить
sanitized fixtures и mapper tests. Live reader появляется позже, когда
source-contract и redaction tests докажут такую же границу на exported
evidence.
