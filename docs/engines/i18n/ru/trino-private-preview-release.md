# Trino private preview release path

Last reviewed: 2026-06-03

Язык: [English](../../trino-private-preview-release.md) | Русский

Английская версия является канонической. Эта страница описывает, как показывать
Trino в релизе как раннюю закрытую интеграцию с тестовым кластером, не заявляя
live product support.

## Статус

Это не live collector, не live engine selector, не Details/trusted-report
surface, не optimizer workflow и не разрешение выполнять user SQL через Query
Doctor. Единственная Trino browser surface - isolated local
`/trino/compact-diagnosis` page для already raw-free direct boundary JSON или
selected sample boundary из package boundary export.
Production triage остается Apache Impala. Trino support ограничен sanitized
offline evidence package import, bounded local event-store import, bounded
HTTP event archive import, bounded HTTP query-detail archive import, bounded
local query-detail/query-list aggregate import и bounded local statement-stats
import, bounded local pruned QueryInfo import, plus event-source contract
checking и dry-run coordinator query-info target checking, plus one-query
pruned coordinator query-info probing/import, local compact diagnosis over
raw-free direct boundary JSON или selected package sample boundaries и isolated
local `/trino/compact-diagnosis` page over the same already raw-free inputs.
Отдельный event-source contract check остается source gate для event archive
readers, coordinator query-info target check остается dry-run gate, а pruned
coordinator query-info probe остается probe-only; pruned query-info import
мапит только allowlisted facts и не становится browser/report collection.
Compact diagnosis читает только уже raw-free direct boundary JSON или selected
sample boundary из package export; isolated page рендерит только sanitized
diagnosis fields. Оба остаются вне Details/trusted reports, optimizer behavior,
live Recent scans и live Query ID diagnosis.

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
- event-source contract check для archive reader, без broader Trino coordinator reader.
- `query-doctor-trino-coordinator-query-info-target-check` для future
  coordinator query-info target contract, без `/v1/query` request и без live
  Query ID diagnosis.
- `query-doctor-trino-coordinator-query-info-pruned-probe` для одного bounded
  `GET /v1/query/{queryId}?pruned=true` после accepted contract, без raw
  QueryInfo output, HTTP redirects, auth header path/value, fact mapping или
  live Query ID diagnosis.
- `query-doctor-trino-coordinator-query-info-pruned-import` для одного bounded
  pruned QueryInfo read после accepted contract, с raw-free boundary из
  allowlisted lifecycle и `queryStats` fields, без raw QueryInfo output, HTTP
  redirects, auth header path/value или live Query ID diagnosis.
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
   query-doctor-trino-import --format boundary-json <sanitized-package.json>
   ```

   Команды работают только с already-sanitized compact samples и не должны
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
   coverage, lifecycle и state counts, но не ingest-ит raw Trino payloads, не
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
   shape, Query ID shape, bounds и redaction/storage policy, не печатает URL
   или Query ID, не контактирует с Trino, не вызывает `/v1/query`, не fetch-ит
   query-info JSON, не submit-ит SQL и не добавляет browser/report output.

12. Optional one-query pruned coordinator query-info probing:

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

13. Optional local pruned QueryInfo fact import:

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

14. Optional one-query pruned coordinator query-info fact import:

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
   передавайте `--diagnosis-json <raw-free-trino-diagnosis.json>` в audit:
   сохраненный compact diagnosis artifact сверяется с deterministic diagnosis
   из boundary без печати artifact paths.
   Если handoff также включает dev-only Kerberos/SPNEGO smoke summary,
   передавайте
   `--smoke-summary <trino_smoke_summary.json> --require-executed-smoke`, чтобы
   retained smoke artifact проходил shape-check, а dry-run plan не считался
   executed test-cluster smoke.
   Она не crawl-ит query history, не submit-ит SQL, не делает live Query ID
   diagnosis и не добавляет browser/report output.

## Release gates

Перед релизной формулировкой "Trino private preview":

- `python3 scripts/demo_trino_evidence_package.py` проходит и печатает только
  safe summary.
- Dev-only Kerberos/SPNEGO smoke запускался against approved test cluster с
  explicit read-only smoke tables; для handoff остается только safe summary.
- Минимум один operator-exported evidence package проходит
  `scripts/validate_trino_evidence_package.py` без `--partial-ok`, или один
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
  operator-approved pruned QueryInfo source contract plus one explicit query
  проходит pruned import command с boundary JSON output, или release
  note прямо говорит, что Trino evidence пока synthetic-only.
- README и release docs говорят, что Trino support ограничен sanitized offline
  evidence package import, bounded local event-store import, bounded local
  HTTP event archive import, bounded HTTP query-detail archive import, bounded
  local query-detail/query-list aggregate import и bounded local statement-stats
  import, bounded local pruned QueryInfo import, plus event-source contract
  checking, dry-run coordinator query-info target checking и one-query pruned
  coordinator query-info probing/import, local compact diagnosis over raw-free
  direct boundary JSON или selected package sample boundaries и isolated local
  compact-diagnosis page over the same already raw-free inputs.
- Не добавлены live Trino engine selector, Details/trusted report path,
  optimizer behavior, metadata collector, query-history reader, live support
  claim или browser workflow beyond the isolated compact-diagnosis page.

## Что остается после private preview

Private preview не равен product support. Следующие gates: превратить accepted
test-cluster packages в committed sanitized fixtures и mapper tests, закрыть
support-gap matrix, доказать source contracts для дополнительных readers и
добавить browser/report boundary tests до попадания Trino-derived facts в
product surfaces.
