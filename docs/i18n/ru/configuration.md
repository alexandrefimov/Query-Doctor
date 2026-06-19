# Справочник конфигурации

Last reviewed: 2026-06-19

Язык: [English](../../configuration.md) | Русский

Английская версия является канонической. Эта сопроводительная страница
описывает основной смысл локальной JSON-конфигурации.

## Назначение

Query Doctor читает non-secret settings из JSON config. Секреты должны жить в
environment variables или local env files, описанных в
[credentials](credentials.md).

## Порядок discovery

Типичный порядок, когда `--config` не указан:

1. `query-doctor-config.json` в current working directory;
2. `~/.qdcreds/query-doctor-config.json`;
3. repository-local `query-doctor-config.json`, если команда разрешает
   repository default;
4. legacy ignored `.query-doctor-cm.local.json`.

Явный `--config` всегда имеет приоритет. Для обычной рабочей станции
предпочтительный путь остается `~/.qdcreds/query-doctor-config.json`.

## Что можно хранить в config

- web `host` и `port`;
- Cloudera Manager base URL without credentials;
- cluster/service selection;
- `ca_bundle` path;
- `krb5ccname`;
- metadata coordinator and `impala-shell` settings;
- direct Impala profile/query source settings, including optional JSON profile
  probing with text fallback and optional safe `/profile_docs` counter-stability
  probing;
- direct Impala Recent и Running scans видят только историю, которую еще
  отдают daemon query-list endpoints координаторов. В upstream Impala
  coordinator query log по умолчанию хранит `--query_log_size=200` записей и
  дополнительно ограничен `--query_log_size_in_bytes`; для большей истории
  нужно осознанно увеличить эти настройки на каждом coordinator-impalad;
- более глубокая direct Impala history может развиваться тремя отдельными
  путями: увеличить retention query log на coordinator web endpoints, добавить
  будущий read-only ingestion profile-log directories с allowlisted
  mount/local paths, либо добавить future bounded external history source вроде
  Loki или OpenSearch через operator-owned source contract; последние два пути
  не являются текущей product support;
- optional direct Impala `/admission?json` aggregate context collection;
- `cluster_type` для различения `cm` и direct `impala` clusters;
- общий language mode: `language` = `en` или `ru`; он показывается в web
  header и управляет Help, deterministic body-текстом в Recent Finding,
  длинными deterministic recommendation / explanation body-текстами в Details,
  а также новыми trusted reports; Details headings, compact Recent labels,
  table headers, badges и технические термины остаются английскими;
- `recent_window_minutes` задает bounded Search depth для CLI Recent и web
  Finished-query scans across Cloudera Manager и direct Impala sources; большие
  окна могут увеличивать нагрузку на Cloudera Manager, direct Impala UI
  endpoints и optional Prometheus collection, поэтому используйте filters, если
  можно;
- `recent_scan_timezone`, например `UTC`; поле сохранено для explicit
  date/hour helper paths, а web Finished-query scans по умолчанию используют
  `recent_window_minutes`;
- non-secret LLM route settings: `report_llm_provider`,
  `report_llm_model`, `optimizer_llm_provider`, `optimizer_llm_model` и
  provider base URLs;
- optional bounded Prometheus settings;
- privacy controls such as `privacy_mode` and `no_llm`.
- `source_visibility`; для local web обычно не нужно фиксировать
  `source_owner_user` в JSON, потому что Query Doctor может вывести simple user
  из `QD_SOURCE_OWNER_USER`, Kerberos principal или simple principals в
  `QD_KEYTAB`. Keytab users сортируются по алфавиту, первый становится
  Username default.
- `viewer_identity_header` для shared/non-local `owner_raw` deployments behind
  trusted auth front door. Front door authenticates request, strips inbound
  copies и выставляет ровно один normalized simple owner value; Query Doctor
  использует header только как C2 viewer identity для owner check.
- `owner_raw_source_enabled`; kill switch для isolated owner-only original
  source page/link. Он не должен тихо менять collection owner filters или
  optimizer policy.

## Trino Beta Recent и One Query ID

Trino Beta в web UI является local lane для bounded retained-list Recent
diagnosis и одного explicit Query ID. Recent читает один bounded pruned
coordinator query list после принятого local query-list source contract, затем
читает bounded pruned coordinator QueryInfo payloads через QueryInfo source
contract для выбранных retained rows. One Query ID использует тот же bounded
QueryInfo path для одного explicit ID. Оба пути строят raw-free boundary in
memory и показывают deterministic compact diagnosis. Это не production Trino
support.

Минимальные non-secret JSON fields:

```json
{
  "engine": "trino",
  "trino_beta_enabled": true,
  "trino_coordinator_url": "https://trino-coordinator.example.com",
  "trino_query_info_source_contract": "./trino-query-info-contract.json",
  "trino_query_list_source_contract": "./trino-query-list-contract.json",
  "trino_kerberos_principal": "sa@EXAMPLE.COM",
  "trino_krb5_ccname": "FILE:/tmp/krb5cc_query_doctor_trino"
}
```

Auth mode выбирается локально: либо `trino_auth_header_file` указывает на local
file с одним operator-managed `Authorization:` header line, либо
`trino_kerberos_principal` включает Kerberos/SPNEGO GET path. Не комбинируйте
эти режимы. Для SPNEGO можно добавить `trino_kerberos_service_name` (default
`HTTP`), `trino_krb5_ccname`, `trino_krb5_config`, `trino_kerberos_ca_cert` и
local test-cluster override `trino_kerberos_insecure_tls`. Secret values и
ticket contents не хранятся в JSON. Для auth-header mode используйте JSON key
`"trino_auth_header_file"` вместо Kerberos keys.
Cluster entries могут иметь отдельные Trino Beta keys для разных local targets.
Web UI помечает configured sources как `Trino Beta Recent + One Query ID`,
`Trino Beta Recent` или `Trino Beta One Query ID`. Diagnose Engine control
сужает Source cluster selector до Impala-capable sources или Trino Beta-ready
sources до выбора workflow. Web UI не показывает coordinator URLs, auth
reference paths/values, local source-contract paths, raw QueryInfo, raw
query-list payloads или raw SQL, и fail-closed для stale или forged Trino
submits до analysis или async job creation.

Trino Beta не включает Running scans, query-history crawling, metadata
collection, Details/trusted reports, optimizer behavior, generated Trino SQL
или SQL execution.

## Owner Raw и D3 viewer header

Для local-first `owner_raw` Query Doctor может намеренно сопоставлять
collectable owner users с локальным viewer. Для shared/non-local D3 это
запрещено: raw reveal должен зависеть от authenticated human viewer, а не от
collection credential, web process account или keytab owner set.

D3 поддерживает один application contract:

```text
trusted auth front door -> exactly one normalized viewer header -> Query Doctor owner check
```

OIDC/SSO, SAML, SPNEGO/Kerberos, LDAP/AD, MFA, session, logout, token и
group/RBAC handling должны завершаться на ingress/proxy/front door. Query
Doctor не реализует native auth modes для owner-raw access и не принимает raw
identity-provider tokens. Он читает только configured `viewer_identity_header`
с already normalized simple owner value и сравнивает его с `query.user`
выбранного case. Missing, duplicate, invalid, UPN/email-style,
distinguished-name, group/role-like, opaque-subject, display-name,
comma-separated, service-principal и host-principal values должны fail-closed
для raw source access.

Канонический deployment checklist находится в
[owner-raw-d3-deployment.md](../../owner-raw-d3-deployment.md).

## CM env files

Cloudera Manager credentials держите в environment, а не в JSON config. Direct
web и batch CLI могут загрузить local env file из `QD_CM_ENV`,
`$QD_CREDS_DIR/cm-ro.env` или `~/.qdcreds/cm-ro.env`.

Файл читается только по allowlist, без shell evaluation. Разрешены только
`CM_USERNAME`, `CM_USER`, `CM_PASSWORD` и `CM_TOKEN`. Уже exported environment
variables имеют приоритет над file values. `username` в JSON config остается
supported как non-secret fallback, но для local web лучше держать CM auth user
рядом с CM auth secret в `cm-ro.env`. Kerberos cache и principal должны идти из
shell environment, wrapper defaults, keytab inference или JSON config, а не из
`cm-ro.env`.

## Метаданные Recent batch

Для Cloudera Manager Recent batches metadata refresh может использовать real
table references, извлеченные из discovery statements до profile identifier
redaction. Эти identifiers передаются только во внутренний bounded metadata
subprocess; progress, summaries, trusted reports и pipeline plan output должны
оставаться raw-free.

`recent_metadata_top_limit` означает maximum number of top collectable cases,
eligible for metadata refresh. Placeholder-only/generic references не должны
тратить этот бюджет.

## Что нельзя хранить

Нельзя хранить passwords, tokens, cookies, Authorization headers, LLM API keys,
embedded URL credentials, keytab contents или query parameters с секретами.
External LLM tokens должны жить в `~/.qdcreds/llm-api.env`, а не в JSON.

Полный field reference и examples находятся в
[английской configuration reference](../../configuration.md).
