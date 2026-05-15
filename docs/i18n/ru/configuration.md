# Configuration Reference

Last reviewed: 2026-05-15

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

## Что нельзя хранить

Нельзя хранить passwords, tokens, cookies, Authorization headers, embedded URL
credentials, keytab contents или secret-bearing query parameters.

Полная field reference и examples находятся в
[английской configuration reference](../../configuration.md).
