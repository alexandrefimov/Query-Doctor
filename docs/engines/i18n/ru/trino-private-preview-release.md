# Trino private preview release path

Last reviewed: 2026-06-16

Язык: [English](../../trino-private-preview-release.md) | Русский

Английская версия является канонической. Эта страница описывает, как показывать
Trino в релизе как раннюю закрытую интеграцию с тестовым кластером, не заявляя
live product support.

## Статус

Это не live collector, не production engine selector, не Details/trusted-report
surface, не optimizer workflow и не разрешение выполнять user SQL через Query
Doctor. Trino browser surfaces - isolated local `/trino/compact-diagnosis` page
для already raw-free direct boundary JSON excluding local metadata summary
boundaries или selected sample boundary из package boundary export, плюс local
Trino Beta retained-list Recent lane over one bounded retained pruned
coordinator query-list read and selected pruned QueryInfo reads, плюс local
Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read,
both with the same raw-free compact diagnosis.
Production triage остается Apache Impala. Trino support ограничен sanitized
offline evidence package import, bounded local event-store import, bounded
HTTP event archive import, bounded HTTP query-detail archive import, bounded
local query-detail/query-list aggregate import и bounded local statement-stats
import, bounded local pruned QueryInfo import, plus event-source contract
checking, dry-run coordinator query-info target checking, metadata
source-contract checking, bounded local metadata summary import, plus one-query
pruned coordinator query-info probing/import, dev-only package-to-boundary
evidence handoff audit, dev-only product-surface boundary audit over retained
raw-free compact artifacts, dev-only one-query handoff and handoff-suite
readiness over raw-free handoff artifacts, dev-only support-gap audit coverage
for source-type registry и engine fact promotion policy, local compact
diagnosis over raw-free direct boundary JSON excluding local metadata summary
boundaries или selected package sample boundaries, isolated local
`/trino/compact-diagnosis` page over the same already raw-free inputs, local web
Trino Beta retained-list Recent lane over one bounded retained pruned
coordinator query-list read and selected pruned QueryInfo reads, и local web
Trino Beta One Query ID lane over one bounded pruned coordinator QueryInfo read,
both with the same raw-free compact diagnosis.
Отдельный event-source contract check остается source gate для event archive
readers, coordinator query-info target check остается dry-run gate, а pruned
coordinator query-info probe остается probe-only; metadata source-contract check
остается dry-run relation/column allowlist gate; local metadata summary import
мапит только aggregate coverage counts из operator-prepared sanitized file;
pruned query-info import мапит только allowlisted facts и может feed-ить только
explicit Trino Beta Recent/One Query ID lanes или raw-free local artifacts.
Compact diagnosis читает только уже raw-free direct boundary JSON excluding
local metadata summary boundaries или selected sample boundary из package export;
isolated page и Recent/One Query ID beta lanes рендерят только sanitized
diagnosis fields. Они остаются вне Details/trusted reports, optimizer behavior,
Running scans, metadata collection, query-history crawling, SQL execution и
production Query ID support.

Для local UI beta show-readiness gate используйте
[trino-beta-ui-readiness.md](../../../trino-beta-ui-readiness.md); он фиксирует
showable Recent and One Query ID beta surfaces, required UI behavior, blocked claims,
release gates и screenshot-refresh boundary без расширения Trino support.

Trino можно называть private preview только если есть безопасные сигналы:

- bounded Kerberos/SPNEGO smoke against approved test cluster;
- sanitized evidence-package intake для operator-exported compact samples;
- sanitized local event-store intake для compact event-listener records;
- sanitized HTTP event archive intake для operator-controlled compact archive;
- sanitized HTTP query-detail archive intake для operator-controlled compact
  query-detail archive;
- sanitized local query-detail intake для одного compact query-detail JSON;
- sanitized local query-list aggregate intake для одного compact aggregate JSON;
- sanitized local statement-stats intake для одного compact
  `QueryResults.statementStats` / `rootStage` JSON.
- sanitized local pruned QueryInfo intake для одного compact JSON с
  allowlisted `state` и `queryStats` fields.
- dev-only package-to-boundary evidence handoff audit для sanitized packages.
- event-source contract check для archive reader, без broader Trino coordinator reader.
- `query-doctor-trino-coordinator-query-info-target-check` для future
  coordinator query-info target contract, без `/v1/query` request и без live
  Query ID diagnosis.
- `query-doctor-trino-metadata-source-contract-check` для future explicit
  relation/column allowlist contract, без metadata read, metadata SQL, object
  identifier output или metadata collection support.
- `query-doctor-trino-metadata-summary-import` для одного compact sanitized
  aggregate metadata summary JSON после accepted metadata source contract, без
  metadata read, metadata SQL, object identifiers, metadata values или compact
  diagnosis output.
- `query-doctor-trino-coordinator-query-info-pruned-probe` для одного bounded
  `GET /v1/query/{queryId}?pruned=true` после accepted contract, без raw
  QueryInfo output, HTTP redirects, auth header path/value, fact mapping или
  live Query ID diagnosis.
- `query-doctor-trino-coordinator-query-info-pruned-import` для одного bounded
  pruned QueryInfo read после accepted contract, с raw-free boundary из
  allowlisted lifecycle и `queryStats` fields, без raw QueryInfo output, HTTP
  redirects, auth header path/value или live Query ID diagnosis.
- dev-only `scripts/trino_one_query_live_handoff.py` может использовать
  explicit Kerberos/SPNEGO curl fetch mode из already prepared local ticket
  cache для того же single bounded pruned QueryInfo read, без печати principal,
  ticket-cache path, coordinator URL, Query ID, curl stderr, raw QueryInfo или
  live Query ID diagnosis.
- `query-doctor-trino-query-info-pruned-import` для одного local compact
  sanitized pruned QueryInfo JSON после accepted contract, с raw-free boundary
  из allowlisted `state` и `queryStats` fields, без network read, raw QueryInfo
  fields, Query IDs или live Query ID diagnosis.

Эти сигналы остаются вне live product workflows Query Doctor. Trino остается
unsupported для Details, trusted reports, optimizer, metadata и live collection.

## Что показывать

1. Fixture walkthrough:

   ```bash
   python3 scripts/demo_trino_evidence_package.py
   ```

   Он показывает package shape, parser coverage, safe source summary и case
   counts без сети и без raw payloads.

2. Closed-cluster smoke command shape только с placeholders:

   ```bash
   python3 scripts/trino_kerberos_smoke.py \
     --server https://<test-trino-endpoint> \
     --client-user <client-user> \
     --kerberos-principal <principal@EXAMPLE.COM> \
     --service-name HTTP \
     --count-table <catalog.schema.table> \
     --sample-table <catalog.schema.table> \
     --out <local-smoke-output-dir>
   ```

   Это dev-only smoke для тестового кластера. Он использует только built-in
   allowlisted read-only statement shapes, bounded Trino protocol pages и safe
   summary. Его нельзя подключать к product workflows.

3. Sanitized handoff:

   ```bash
   python3 scripts/build_trino_evidence_package.py \
     --out <sanitized-package.json> \
     --package-id <safe-package-label> \
     --prepared-date-utc YYYY-MM-DD \
     --export-window-start-utc YYYY-MM-DDTHH:00:00Z \
     --export-window-end-utc YYYY-MM-DDTHH:00:00Z \
     --redaction-reviewed \
     --sentinel-tests-passed \
     --sample <case>:<source_type>:<sanitized-sample-json>

   python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
   python3 scripts/audit_trino_evidence_handoff.py \
     <sanitized-package.json> \
     --summary-json <raw-free-trino-package-handoff-summary.json>
   query-doctor-trino-import --format boundary-json <sanitized-package.json>
   ```

   Команды работают только с already-sanitized compact samples. Dev-only
   package handoff audit валидирует package, converts accepted samples to
   raw-free boundary payloads in memory, запускает compact readiness suite и
   может писать `trino_evidence_handoff_summary_v1` machine summary. Для full
   evidence packages он по умолчанию не требует supported attention или known
   parser coverage для каждого sample, потому что unknown и unsupported samples
   входят в package contract. Retained handoff-suite audits требуют
   diagnostic-lane source, readiness, verification и fact-state counters и
   reject-ят source-granularity или fact-state counter drift между
   `diagnostic_lane` и top-level retained summary counters. Strict retained
   suites могут также требовать selected safe source-contract labels, например
   `synthetic_trino_event_listener_v1`, из retained package source summaries,
   плюс selected source-granularity labels, например `one_query_boundary` или
   `aggregate_query_list`, и selected verification-scope labels, например
   `comparable_one_query_rerun`, `representative_query_selection` или
   `source_contract_review`, из уже retained diagnostic-lane counters без
   reopening packages. Они также reject-ят duplicate retained handoff-summary
   artifact references, включая path aliases, чтобы suite-width counts не могли
   reuse one summary. Audit output не должен печатать paths, raw payloads, SQL,
   URLs, Query IDs или Trino identifiers и не является support claim.
   Остальные команды не должны
   печатать input paths, raw payloads, raw values, query identifiers, users,
   hostnames, object names, connector details или rejected record contents.

   Package `--format boundary-json` output — это envelope с
   `sample_fact_boundaries`. Диагностируйте ровно один packaged sample,
   передавая этот export плюс `--sample-index <zero-based-index>`;
   multi-sample package exports reject-ятся без explicit index. Direct
   single-boundary imports не требуют sample index.

   Любой resulting direct raw-free boundary JSON можно диагностировать локально:

   ```bash
   query-doctor-diagnose-trino-compact \
     --boundary-json <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json>
   query-doctor-diagnose-trino-compact \
     --boundary-json <trino-package-boundary-export.json> \
     --sample-index <zero-based-index> \
     --diagnosis-out <raw-free-trino-diagnosis.json>
   ```

   Это только deterministic compact diagnosis. Он читает один уже raw-free
   `engine_fact_boundary_v1` payload или один selected sample boundary из
   package boundary export, reject-ит non-Trino boundaries, пишет attention
   areas, change directions, verification prompts, limitations, parser
   coverage, lifecycle, state counts и raw-free `diagnostic_lane` summary с
   source granularity, evidence readiness, verification scope и required audit
   gates, но не ingest-ит raw Trino payloads, не
   копирует input summaries или string metric values, не делает root-cause
   claims, не submit-ит SQL, не запускает live Recent scans, не collect-ит live
   Query ID diagnosis и не добавляет browser/report/optimizer output.
   Тот же accepted direct boundary или package boundary export плюс sample
   index можно вставить в isolated local `/trino/compact-diagnosis` page; page
   не echo-ит submitted boundary JSON и не render-ит source schema, fact-group,
   Query ID, URL, path, raw SQL или source-contract fields.
   Single-boundary local query-detail, local query-list aggregate, local
   statement-stats, local pruned QueryInfo, HTTP query-detail archive и
   pruned coordinator query-info import commands также могут писать тот же
   diagnosis напрямую через
   `--diagnosis-out <raw-free-trino-diagnosis.json>` после accepted boundary.
   Путь diagnosis output должен отличаться от input или source-contract path,
   а при использовании auth-header file — и от этого пути.

4. Optional local event-store intake:

   ```bash
   query-doctor-trino-event-store-import \
     --redaction-reviewed \
     <sanitized-event-store.json-or-ndjson>
   query-doctor-trino-event-store-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-event-store.json-or-ndjson>
   ```

   Это local import only: команда читает один explicit JSON/NDJSON file,
   validates compact event records, выводит только safe summary или raw-free
   fact boundaries и не контактирует с Trino.

5. Optional HTTP event archive intake:

   ```bash
   query-doctor-trino-http-event-archive-import \
     --redaction-reviewed \
     --source-contract <sanitized-event-source-contract.json> \
     --archive-url https://<operator-event-archive>
   query-doctor-trino-http-event-archive-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-event-source-contract.json> \
     --archive-url https://<operator-event-archive>
   ```

   Это bounded archive import only: команда требует accepted
   `http_event_listener_archive` source contract, читает один explicit operator
   HTTP(S) archive URL, выводит только safe summary или raw-free fact
   boundaries, не контактирует с Trino coordinator, не discovers endpoints, не
   echo-ит URL, не принимает URL credentials и не submit-ит SQL.

6. Optional local query-detail intake:

   ```bash
   query-doctor-trino-query-detail-import \
     --redaction-reviewed \
     <sanitized-query-detail.json>
   query-doctor-trino-query-detail-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-query-detail.json>
   query-doctor-trino-query-detail-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     <sanitized-query-detail.json>
   ```

   Это local import only: команда читает один explicit compact sanitized JSON
   object, validates query-detail source contract, выводит только safe summary
   или raw-free fact boundaries и не контактирует с Trino.

7. Optional HTTP query-detail archive intake:

   ```bash
   query-doctor-trino-http-query-detail-archive-import \
     --redaction-reviewed \
     --source-contract <sanitized-query-detail-archive-contract.json> \
     --archive-url https://<operator-query-detail-archive>
   query-doctor-trino-http-query-detail-archive-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-query-detail-archive-contract.json> \
     --archive-url https://<operator-query-detail-archive>
   query-doctor-trino-http-query-detail-archive-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --source-contract <sanitized-query-detail-archive-contract.json> \
     --archive-url https://<operator-query-detail-archive>
   ```

   Это bounded query-detail archive import only: команда требует accepted
   `http_query_detail_archive` source contract, fetch-ит один explicit
   operator archive URL, выводит только safe summary или raw-free fact
   boundaries, не контактирует с Trino coordinator, не fetch-ит query-info by
   Query ID, не echo-ит URL, не принимает URL credentials и не submit-ит SQL.

8. Optional local query-list aggregate intake:

   ```bash
   query-doctor-trino-query-list-import \
     --redaction-reviewed \
     <sanitized-query-list-aggregate.json>
   query-doctor-trino-query-list-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-query-list-aggregate.json>
   query-doctor-trino-query-list-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     <sanitized-query-list-aggregate.json>
   ```

   Это local aggregate import only: команда читает один explicit compact
   sanitized aggregate JSON object, validates query-list contract probe, выводит
   только safe summary или raw-free fact boundaries и не контактирует с Trino.

9. Optional local statement-stats intake:

   ```bash
   query-doctor-trino-statement-stats-import \
     --redaction-reviewed \
     <sanitized-statement-stats.json>
   query-doctor-trino-statement-stats-import \
     --redaction-reviewed \
     --format boundary-json \
     <sanitized-statement-stats.json>
   query-doctor-trino-statement-stats-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     <sanitized-statement-stats.json>
   ```

   Это local import only: команда читает один explicit compact sanitized JSON
   object, validates statement-statistics contract, выводит только safe summary
   или raw-free fact boundaries, не контактирует с Trino, не вызывает
   `/v1/statement` и не submit-ит SQL.

10. Optional event-source contract checking:

   ```bash
   query-doctor-trino-event-source-contract-check \
     --redaction-reviewed \
     <sanitized-event-source-contract.json>
   query-doctor-trino-event-source-contract-check \
     --redaction-reviewed \
     --format summary-json \
     <sanitized-event-source-contract.json>
   ```

   Это contract validation only: команда проверяет source type, safe
   auth-reference label, accepted event schema, bounds и redaction/storage
   policy, отклоняет endpoints, topics, database names, credentials, raw event
   records и raw SQL до archive-reader contact.

11. Optional coordinator query-info target checking:

   ```bash
   query-doctor-trino-coordinator-query-info-target-check \
     --redaction-reviewed \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   ```

   Это dry-run target validation only: команда проверяет compact source
   contract, safe auth-reference label, one-query bound, coordinator base URL
   shape, Query ID shape, safe `trino_version_family`, bounds и
   redaction/storage policy, не печатает URL или Query ID, не контактирует с
   Trino, не вызывает `/v1/query`, не fetch-ит query-info JSON, не submit-ит SQL
   и не добавляет browser/report output.

12. Optional metadata source-contract checking:

   ```bash
   query-doctor-trino-metadata-source-contract-check \
     --redaction-reviewed \
     <sanitized-metadata-source-contract.json>
   query-doctor-trino-metadata-source-contract-check \
     --redaction-reviewed \
     --format summary-json \
     <sanitized-metadata-source-contract.json>
   ```

   Это dry-run allowlist validation only: команда проверяет compact
   `metadata_allowlist` source contract, safe auth-reference label, explicit
   relation/column allowlist shape, bounds и redaction policy, не печатает
   object identifiers или input paths. Она не контактирует с Trino, не читает
   metadata, не выполняет metadata SQL, не crawl-ит objects, не хранит raw
   metadata, не собирает metadata facts и не добавляет browser/report output.

13. Optional local metadata summary import:

   ```bash
   query-doctor-trino-metadata-summary-import \
     --redaction-reviewed \
     --source-contract <sanitized-metadata-source-contract.json> \
     <sanitized-metadata-summary.json>
   query-doctor-trino-metadata-summary-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-metadata-source-contract.json> \
     <sanitized-metadata-summary.json>
   ```

   Это local aggregate import only: команда проверяет accepted
   `metadata_allowlist` source contract, validates relation/column counts
   against that contract, мапит только coverage и stats-completeness counts в
   raw-free boundary JSON и не печатает object identifiers, metadata values,
   input paths или raw metadata. Она не контактирует с Trino, не выполняет
   metadata SQL, не crawl-ит objects, не собирает live metadata, не добавляет
   browser/report output и не пишет compact diagnosis output.

14. Optional one-query pruned coordinator query-info probing:

   ```bash
   query-doctor-trino-coordinator-query-info-pruned-probe \
     --redaction-reviewed \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   ```

   Это one bounded probe only: команда проверяет тот же compact source
   contract и operator-managed auth reference, делает ровно один
   `GET /v1/query/{queryId}?pruned=true`, валидирует bounded JSON object и не
   печатает auth header path/value, URL, Query ID, raw QueryInfo, query text,
   session fields, endpoint URLs, object names или raw payload content и не
   следует HTTP redirects. Она не мапит QueryInfo в facts, не crawl-ит query
   history, не submit-ит SQL, не делает live Query ID diagnosis и не добавляет
   browser/report output.

15. Optional local pruned QueryInfo fact import:

   ```bash
   query-doctor-trino-query-info-pruned-import \
     --redaction-reviewed \
     --format boundary-json \
     --source-contract <sanitized-query-info-target-contract.json> \
     <sanitized-pruned-query-info.json>
   query-doctor-trino-query-info-pruned-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --source-contract <sanitized-query-info-target-contract.json> \
     <sanitized-pruned-query-info.json>
   ```

   Это local fact import only: команда проверяет тот же compact source
   contract, не делает network read, мапит только allowlisted `state` и
   `queryStats` fields в raw-free boundary JSON и reject-ит raw QueryInfo
   fields вроде Query IDs, query text, session fields, endpoint URLs, object
   names и stage/task detail. Она не crawl-ит query history, не submit-ит SQL,
   не делает live Query ID diagnosis и не добавляет browser/report output.

16. Optional one-query pruned coordinator query-info fact import:

   ```bash
   query-doctor-trino-coordinator-query-info-pruned-import \
     --redaction-reviewed \
     --boundary-out <raw-free-trino-boundary.json> \
     --format boundary-json \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   query-doctor-trino-coordinator-query-info-pruned-import \
     --redaction-reviewed \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id <trino-query-id>
   ```

   Это one bounded fact import only: команда проверяет тот же compact source
   contract и operator-managed auth reference, делает ровно один
   `GET /v1/query/{queryId}?pruned=true`, мапит только allowlisted lifecycle и
   `queryStats` fields в raw-free boundary JSON и не печатает URL, Query ID,
   raw QueryInfo, query text, session fields, endpoint URLs, object names,
   stage/task identifiers, workers, raw failures, connector internals, auth
   header path/value, output boundary path или raw payload content. Файл
   `--boundary-out` - direct `engine_fact_boundary_v1` payload для
   `scripts/audit_trino_compact_readiness.py <raw-free-trino-boundary.json> --require-one-query-boundary`.
   Если тот же run пишет `--diagnosis-out <raw-free-trino-diagnosis.json>`,
   передавайте `--require-source-version trino_coordinator_query_info_target_v1`
   и `--diagnosis-json <raw-free-trino-diagnosis.json>` в audit: source
   contract и сохраненный compact diagnosis artifact сверяются с deterministic
   diagnosis из boundary без печати actual source-version values или artifact
   paths.
   Если handoff также включает dev-only Kerberos/SPNEGO smoke summary,
   передавайте
   `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`, чтобы
   retained smoke artifact проходил shape-check, а dry-run plan не считался
   executed test-cluster smoke.
   Она не crawl-ит query history, не submit-ит SQL, не делает live Query ID
   diagnosis и не добавляет browser/report output.

17. Optional dev-only one-query live handoff wrapper для той же readiness path:

   ```bash
   python3 scripts/trino_one_query_live_handoff.py \
     --redaction-reviewed \
     --auth-header-file <operator-auth-header-file> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id-file <operator-query-id-file> \
     --boundary-out <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --readiness-summary-out <raw-free-trino-readiness-summary-json> \
     --handoff-summary-out <raw-free-trino-one-query-handoff-summary-json> \
     --product-surface-summary-out <raw-free-trino-product-surface-summary-json>

   python3 scripts/trino_one_query_live_handoff.py \
     --redaction-reviewed \
     --kerberos-principal <principal@EXAMPLE.COM> \
     --krb5-ccname FILE:<local-ticket-cache> \
     --source-contract <sanitized-query-info-target-contract.json> \
     --coordinator-url https://<trino-coordinator> \
     --query-id-file <operator-query-id-file> \
     --boundary-out <raw-free-trino-boundary.json> \
     --diagnosis-out <raw-free-trino-diagnosis.json> \
     --readiness-summary-out <raw-free-trino-readiness-summary-json> \
     --handoff-summary-out <raw-free-trino-one-query-handoff-summary-json> \
     --product-surface-summary-out <raw-free-trino-product-surface-summary-json>
   ```

   Wrapper не является installed product CLI. Он запускает тот же one-query
   pruned coordinator import, пишет только raw-free boundary и compact
   diagnosis artifacts и сразу выполняет strict
   `--require-one-query-boundary`,
   `--require-source-version trino_coordinator_query_info_target_v1` и
   `--diagnosis-json <raw-free-trino-diagnosis.json>` readiness checks без
   печати coordinator URLs, Query IDs, auth headers, raw QueryInfo, output
   paths или filenames. Kerberos/SPNEGO form использует `curl --negotiate`
   только для того же single `GET /v1/query/{queryId}?pruned=true` read,
   требует already prepared local ticket cache, mutually exclusive с
   `--auth-header-file` и не печатает principal, ticket-cache path, curl
   stderr, raw QueryInfo или auth material. Если handoff включает executed
   Kerberos/SPNEGO smoke summary, передавайте
   `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`.
   Для live runs предпочитайте `--query-id-file <operator-query-id-file>`,
   чтобы selected Query ID не попадал в shell history и process args; файл
   должен содержать ровно один supported Trino Query ID, rejected как output
   target и никогда не печатается. Finished QueryInfo может быть evicted раньше,
   чем старые QueryMonitor timeline entries исчезнут из logs, поэтому
   выбирайте current или very recent Query ID для этого single read. HTTP 404
   или 410 от любого one-query coordinator fetch path сообщается только как
   redacted stale-QueryInfo hint, без echo response body, coordinator URL, Query
   ID, auth material, curl stderr или local artifact paths. Если HTTP 401 или
   403 reject-ит one-query read, те же paths сообщают только redacted
   auth-rejected hint, чтобы обновить auth reference или ticket, без echo
   rejected auth material, principal, endpoint, response body или local artifact
   paths. Если передан `--readiness-summary-out`, wrapper также пишет
   `trino_compact_readiness_summary_v1` raw-free machine evidence со
   structured `diagnostic_lane` block для source granularity, evidence
   readiness, verification scope и fact-state counters, без печати summary
   path. Если передан `--handoff-summary-out`, wrapper также пишет
   `trino_one_query_handoff_summary_v1` raw-free machine evidence только с
   accepted pipeline states, path-free artifact states и тем же deterministic
   readiness evidence, без печати summary path. Если передан
   `--product-surface-summary-out`, wrapper также
   запускает product-surface boundary audit по записанным boundary/diagnosis
   artifacts и пишет `trino_product_surface_boundary_audit_v1` raw-free
   machine evidence без печати summary path. Он не crawl-ит query history, не
   submit-ит SQL, не делает live Query ID diagnosis и не добавляет
   browser/report output.

16. Для нескольких retained one-query handoff results соберите local
    `trino_one_query_handoff_suite_v1` manifest, где entries ссылаются на
    raw-free boundary JSON и optional compact diagnosis, smoke-summary и
    per-entry readiness-summary/handoff-summary/product-surface-summary
    artifacts, затем запустите strict suite gate:

   ```bash
   python3 scripts/build_trino_handoff_suite_manifest.py \
     --redaction-reviewed \
     --boundary-json <raw-free-trino-boundary-1.json> \
     --diagnosis-json <raw-free-trino-diagnosis-1.json> \
     --smoke-summary <trino_smoke_summary.json> \
     --readiness-summary-json <raw-free-trino-readiness-summary-1.json> \
     --handoff-summary-json <raw-free-trino-one-query-handoff-summary-json> \
     --product-surface-summary-json <raw-free-trino-product-surface-summary-json> \
     --out <trino-one-query-handoff-suite.json>

   python3 scripts/audit_trino_compact_readiness.py \
     --handoff-suite-manifest <trino-one-query-handoff-suite.json> \
     --require-diagnosis-json \
     --require-executed-smoke \
     --require-readiness-summary-json \
     --require-handoff-summary-json \
     --require-one-query-boundary \
     --require-source-version trino_coordinator_query_info_target_v1 \
     --fail-on-unknown-parser-coverage \
     --require-min-trino-version-families <minimum-trino-version-family-count> \
     --require-trino-version-family <safe-trino-version-family> \
     --require-min-inputs <minimum-retained-query-count> \
     --summary-json <raw-free-trino-suite-summary.json>
   ```

   Builder не является installed product CLI. Он требует explicit
   redaction-review confirmation, пишет только local handoff metadata с
   safe relative `*.json` artifact references, поддерживает one shared smoke
   summary или one per boundary, принимает one readiness summary per boundary,
   one handoff summary per boundary и one product-surface summary per boundary,
   reject-ит output/input overlap, unsafe
   absolute/parent/current-directory/backslash references и duplicate
   boundary/diagnosis/readiness-summary/handoff-summary/product-surface-summary
   references including path aliases. Он still allows one shared smoke summary
   across entries, но rejects any smoke summary artifact that overlaps a
   boundary, diagnosis, readiness-summary, handoff-summary, or product-surface
   summary artifact. Strict executed-smoke gate требует, чтобы every smoke
   check имел known `ok` status, а retained smoke summary сохранял
   statement-count/check-count consistency, known safe error categories,
   internally consistent planned/executed counters, explicit `not_written`
   redaction assertions и dev-only/no-product-support limitations. Builder
   печатает только aggregate counts и relative-reference mode без paths или
   filenames. Manifest остается
   local handoff metadata, а не committed artifact. Audit печатает только
   aggregate counts и safe issue categories, может требовать matching
   `trino_compact_readiness_summary_v1` artifact из one-query wrapper для
   каждой manifest entry и matching `trino_one_query_handoff_summary_v1`
   artifact из one-query wrapper, и может записать тот же raw-free aggregate
   evidence как `trino_compact_readiness_summary_v1` JSON. Summary записывает
   source-version requirements только counts/flags и Trino version-family
   coverage только safe broad-label counters, без raw version strings или
   operator-provided source-version values. Когда retained readiness summaries
   присутствуют, suite audit также валидирует их structured `diagnostic_lane`
   blocks и reject-ит missing или drifted source-granularity, readiness,
   verification-scope или fact-state counters через safe issue categories.
   Когда retained handoff summaries присутствуют, он также reject-ит drifted
   pipeline states, path-free artifact states или embedded readiness evidence
   через safe issue categories.
   Ни text output, ни summary не
   содержат coordinator URLs, Query IDs, auth headers, raw QueryInfo, local
   paths или filenames. Он не fetch-ит дополнительные queries, не
   crawl-ит query history, не submit-ит SQL, не делает live Query ID diagnosis
   и не добавляет browser/report output.

17. Перед любым product-surface promotion decision запустите dev-only
    product-surface boundary audit over retained raw-free compact artifacts:

   ```bash
   python3 scripts/audit_trino_product_surface_boundary.py \
     <raw-free-trino-boundary.json> \
     --diagnosis-json <raw-free-trino-diagnosis.json> \
     --summary-json <raw-free-trino-product-surface-summary-json>

   python3 scripts/audit_trino_product_surface_boundary.py \
     --handoff-suite-manifest <trino-one-query-handoff-suite.json> \
     --summary-json <raw-free-trino-product-surface-summary-json>
   ```

   Он проверяет deterministic compact diagnosis artifacts или каждую
   boundary/diagnosis entry из handoff-suite manifest, pin-ит
   `live_known_query_diagnosis=one_query_pruned_query_info_beta` и
   `live_recent_scan=retained_query_list_beta`, валидирует, что allowed Trino
   web registry остается ограничен compact preview surfaces plus the local
   Recent and One Query ID beta surfaces и что Trino CLI stays preview/dev-only, проверяет, что
   retained `diagnostic_lane` остается `preview_only` с deterministic source
   granularity, evidence readiness, verification scope, supported-attention
   count, fact-state counts и required audit gates, пишет только
   `trino_product_surface_boundary_audit_v1` raw-free machine evidence и не
   делает production support claim. Manifest mode требует compact diagnosis artifact для
   каждой entry, валидирует retained per-entry product-surface summaries when
   present и не печатает manifest или artifact paths.
   Product-surface summary output должен отличаться от manifest и каждого
   referenced boundary, diagnosis, smoke-summary, readiness-summary,
   handoff-summary или product-surface-summary artifact.
   Passing audit
   означает, что retained artifacts соблюдают текущий beta-only
   product-surface boundary; он не делает Trino Details/trusted-report,
   optimizer, Recent, metadata, query-history, SQL execution или production
   Query ID workflow.

## Release gates

Перед релизной формулировкой "Trino private preview":

- `python3 scripts/demo_trino_evidence_package.py` проходит и печатает только
  safe summary.
- Dev-only Kerberos/SPNEGO smoke запускался against approved test cluster с
  explicit read-only smoke tables; для handoff остается только safe summary.
- Retained Trino compact diagnosis artifacts, используемые для обсуждения
  product-surface readiness, проходят
  `python3 scripts/audit_trino_product_surface_boundary.py
  <raw-free-trino-boundary.json> --diagnosis-json
  <raw-free-trino-diagnosis.json> --summary-json
  <raw-free-trino-product-surface-summary-json>` или тот же audit через
  `--handoff-suite-manifest <trino-one-query-handoff-suite.json>` с
  `trino_product_surface_boundary_audit_v1`, path-free output, required
  diagnosis artifacts в manifest mode, optional retained product-surface
  summary drift checks, retained handoff summaries treated as protected input
  artifacts, checked `diagnostic_lane` source granularity, evidence readiness,
  verification scope, supported-attention count, fact-state counts и
  `live_known_query_diagnosis=one_query_pruned_query_info_beta`;
  aggregate metadata-summary boundaries
  должны reject-иться как coverage evidence, а не product-surface diagnosis
  artifacts.
- Минимум один operator-exported evidence package проходит
  `scripts/validate_trino_evidence_package.py` без `--partial-ok`, или package
  handoff audit проходит
  `python3 scripts/audit_trino_evidence_handoff.py <sanitized-package.json>
  --summary-json <raw-free-trino-package-handoff-summary.json>` с только
  raw-free machine evidence, или один
  operator-exported compact sanitized local event-store file проходит
  `query-doctor-trino-event-store-import --redaction-reviewed`, или один
  operator-exported compact sanitized HTTP event archive plus accepted
  `http_event_listener_archive` source contract проходит
  `query-doctor-trino-http-event-archive-import --redaction-reviewed`, или один
  operator-exported compact sanitized HTTP query-detail archive plus accepted
  `http_query_detail_archive` source contract проходит
  `query-doctor-trino-http-query-detail-archive-import --redaction-reviewed`, или один
  operator-exported compact sanitized local query-detail file проходит
  `query-doctor-trino-query-detail-import --redaction-reviewed`, или один
  operator-exported compact sanitized local query-list aggregate file проходит
  `query-doctor-trino-query-list-import --redaction-reviewed`, или один
  operator-exported compact sanitized local statement-stats file проходит
  `query-doctor-trino-statement-stats-import --redaction-reviewed`, или один
  operator-approved compact metadata allowlist source contract проходит
  `query-doctor-trino-metadata-source-contract-check --redaction-reviewed`, или
  один operator-exported compact sanitized local metadata summary file plus
  accepted `metadata_allowlist` source contract проходит
  `query-doctor-trino-metadata-summary-import --redaction-reviewed`, или
  один
  operator-approved pruned QueryInfo source contract plus one explicit query
  проходит pruned import command с boundary JSON output и, перед расширением
  любого Trino support surface, retained set of one-query handoff results
  проходит `trino_one_query_handoff_suite_v1` manifest gate с diagnosis,
  executed-smoke, per-entry readiness-summary, per-entry handoff-summary,
  one-query, source-version, version-family breadth, parser-coverage и
  supported-attention requirements, configured minimum retained input count и
  raw-free machine summary artifact;
  иначе release note прямо говорит, что Trino evidence пока synthetic-only.
- README и release docs говорят, что Trino support ограничен sanitized offline
  evidence package import, bounded local event-store import, bounded local
  HTTP event archive import, bounded HTTP query-detail archive import, bounded
  local query-detail/query-list aggregate import и bounded local statement-stats
  import, bounded local pruned QueryInfo import, bounded local metadata summary
  import, plus event-source contract checking, dry-run coordinator query-info
  target checking, metadata source-contract checking и one-query pruned
  coordinator query-info probing/import, dev-only package-to-boundary evidence
  handoff audit, dev-only product-surface boundary audit over retained raw-free
  compact artifacts, dev-only one-query handoff and handoff-suite readiness
  over raw-free handoff artifacts, local compact
  diagnosis over raw-free direct boundary JSON excluding metadata summary
  boundaries или selected package sample boundaries, isolated local
  compact-diagnosis page over the same already raw-free inputs и local web
  Trino Beta One Query ID lane.
- Перед любым broader Trino support-surface decision запускайте
  `python3 scripts/audit_trino_support_gap_matrix.py --summary-json
  <raw-free-trino-support-gap-summary-json>`, чтобы registered Trino fact
  families, source-type registry coverage, engine fact promotion-policy
  coverage, neutral `no_*` gaps, blocked product adapter flags и
  `trino_support_gap_matrix_audit_v1` evidence оставались согласованы с
  support-gap matrix.
- Не добавлены production Trino engine selector, Details/trusted report path,
  optimizer behavior, metadata collector, query-history reader, production
  support claim или browser workflow beyond the isolated compact-diagnosis page
  and Recent/One Query ID beta lanes.

## Что остается после private preview

Private preview не равен product support. Следующие gates: превратить accepted
test-cluster packages в committed sanitized fixtures и mapper tests, держать
`scripts/audit_trino_support_gap_matrix.py` green при закрытии support-gap
matrix, включая source-type registry и engine fact promotion-policy coverage,
доказать source contracts для дополнительных readers и добавить browser/report
boundary tests до попадания Trino-derived facts в product surfaces.
