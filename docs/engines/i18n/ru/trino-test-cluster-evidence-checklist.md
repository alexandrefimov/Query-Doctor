# Чеклист evidence export из тестового Trino-кластера

Last reviewed: 2026-05-26

Язык: [English](../../trino-test-cluster-evidence-checklist.md) | Русский

Английская версия является канонической. Эта страница - русское companion
резюме первого безопасного handoff из тестового Trino-кластера.

Manifest и redaction note оформляйте по
[шаблонам evidence package](trino-evidence-package-templates.md).

## Статус

Это не live collector, не support announcement, не engine selector и не
browser/report surface. Query Doctor не получает прямой доступ к Trino-кластеру
на этом этапе.

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
- query-detail exports только после удаления identifiers, object names,
  endpoints, stack traces и connector internals;
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

Если redaction status неизвестен, export надо reject-ить или пересобрать.

## Handoff package

Первый пакет должен содержать:

- один sanitized compact sample на каждый минимальный кейс;
- manifest sample set;
- redaction note с классами удалённых полей, но не с удалёнными значениями;
- known-gap note для отсутствующих connector families или source schema
  versions;
- никаких raw companion archives.

Package label должен быть safe local label: без cluster, query, user, host,
catalog, schema, table, topic, path, file или artifact names.
Локальный package-intake wrapper: `manifest`, `redaction_note`, `samples`;
accepted sample payloads остаются fixture work, а не live collection.
Перед fixture conversion запускайте
`python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>`.
Команда печатает только safe summary и не должна echo raw payloads, raw values
или input path.

Raw exports остаются только в operator-controlled Trino environment, не в Query
Doctor workspace и не в prompts.

## Acceptance gate

Пакет готов к Query Doctor fixture work только если:

- каждый sample вручную проверен как raw-free;
- каждый sample проходит maximum size и nested-depth bounds fixture contract;
- каждый supported fact query-specific или явно aggregate и version-scoped;
- каждое отсутствующее или unsupported поле имеет `unknown` или omission reason;
- не нужен browser route, trusted report, optimizer behavior, live adapter,
  public README claim или engine registration.

Следующий шаг после accepted package - всё ещё fixture work: добавить
sanitized fixtures и mapper tests. Live reader появляется позже, когда
source-contract и redaction tests докажут такую же границу на exported
evidence.
