# Configuration Reference

Last reviewed: 2026-05-19

Язык: [English](../../configuration.md) | Русский

Английская версия является канонической. Эта companion-страница описывает
основной смысл local JSON configuration.

## Назначение

Query Doctor читает non-secret settings из JSON config. Secrets должны жить в
environment variables или local env files, описанных в
[credentials](credentials.md).

## Discovery order

Типичный preferred path:

- `~/.qdcreds/query-doctor-config.json`;
- explicit `--config`;
- repository-local `query-doctor-config.json`;
- legacy ignored `.query-doctor-cm.local.json`.

## Что можно хранить в config

- web `host` и `port`;
- Cloudera Manager base URL without credentials;
- cluster/service selection;
- `ca_bundle` path;
- `krb5ccname`;
- metadata coordinator and `impala-shell` settings;
- direct Impala profile/query source settings;
- optional bounded Prometheus settings;
- privacy controls such as `privacy_mode` and `no_llm`.

## CM env files

Cloudera Manager credentials держите в environment, а не в JSON config. Direct
web и batch CLI могут загрузить local env file из `QD_CM_ENV`,
`$QD_CREDS_DIR/cm-ro.env` или `~/.qdcreds/cm-ro.env`.

Файл читается whitelist-only, без shell evaluation. Разрешены только
`CM_USERNAME`, `CM_USER`, `CM_PASSWORD`, `CM_TOKEN`, `KRB5CCNAME` и
`KRB5_PRINCIPAL`. Уже exported environment variables имеют приоритет над file
values.

## Recent batch metadata

Для Cloudera Manager Recent batches metadata refresh может использовать real
table references, извлеченные из discovery statements до profile identifier
redaction. Эти identifiers передаются только во внутренний bounded metadata
subprocess; progress, summaries, trusted reports и pipeline plan output должны
оставаться raw-free.

`recent_metadata_top_limit` означает maximum number of top collectable cases,
eligible for metadata refresh. Placeholder-only/generic references не должны
тратить этот budget.

## Что нельзя хранить

Нельзя хранить passwords, tokens, cookies, Authorization headers, embedded URL
credentials, keytab contents или secret-bearing query parameters.

Полная field reference и examples находятся в
[английской configuration reference](../../configuration.md).
