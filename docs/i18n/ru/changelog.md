# Changelog

Last updated: 2026-06-01

Язык: [English](../../changelog.md) | Русский

Английский changelog является каноническим. Эта страница объясняет, как читать
и обновлять changelog на русском.

## Что фиксируется

`docs/changelog.md` хранит только значимые изменения:

- product/workflow behavior;
- safety и trust-boundary changes;
- report или optimizer behavior;
- collector/analyzer behavior;
- major documentation baseline changes.

Minor copy edits, CSS polish, tests и internal refactors обычно не требуют
changelog entry, если они не меняют behavior или safety.

## Текущий порядок

- Новые записи добавляются в `## Unreleased`.
- Используйте короткие bullets по категориям: Engineering, Product, Safety,
  Documentation.
- Для точного текста и истории релизов смотрите
  [английский changelog](../../changelog.md).

## Текущий Unreleased summary

Английский `Unreleased` теперь фиксирует deterministic-first /
no-LLM-capable roadmap posture: core diagnosis, Details, Python reports,
trusted optimizer outcomes, demos и validation должны оставаться полезными при
`no_llm=true`, а LLM-backed wording остается optional selected-case extension.
Следующий UI/Help wording cleanup должен двигаться к нейтральным `Report` /
`Query optimizer` labels без скрытия backend status (`Python-owned`,
`LLM-backed`, `no_llm=true`).
Report validators теперь имеют adversarial EN/RU corpus для indirect
unsupported stale-statistics root-cause wording, soft `COMPUTE STATS`
recommendation wording, row/cardinality estimate-direction wording и integrated
parity coverage для memory estimate direction, backend data skew, primary
bottleneck, CM context-only metrics и CM event context. Trust gate reject-ит
такие unsupported claims до trusted marker, а nearby neutral investigation
wording остается allowed.
Report language handling теперь использует shared report-language registry для
config, web settings и report/pipeline CLI boundaries. Case-insensitive public
keys вроде `RU` нормализуются в `ru`, а unknown languages fail closed до report
generation вместо fallback wording.
Trusted report SQL-like text validation теперь reject-ит inline prose, где
внутри предложения embedded `SELECT`, `WITH`, DML/DDL или metadata `SHOW`
statements. Это закрывает gap, где raw SQL-like text ловился в fenced snippets
или list items, но не в surrounding sentence.
Английский `Unreleased` сейчас включает разделение committed public docs и
ignored local agent notes: durable agent baseline остается в public docs,
private continuation notes живут в local exclude-only notes, а
`scripts/audit_public_docs.py` ловит common local handoff markers перед commit.
Английский `Unreleased` теперь также фиксирует Trino offline/local import:
`query-doctor-trino-import` валидирует уже sanitized compact packages, а
`query-doctor-trino-event-store-import` читает один explicit local JSON/NDJSON
event-store файл с redaction-review confirmation. Последующие bounded local
commands добавляют query-detail, query-list aggregate и statement-stats import
для одного explicit already-sanitized compact JSON payload. Эти пути могут
выводить raw-free normalized fact boundary JSON, но live Recent scans, Query ID
fetch, `/v1/statement`, metadata, browser/report, optimizer behavior и
generated Trino SQL остаются неподдержанными.
Добавлен также `query-doctor-trino-event-source-contract-check`: он валидирует
source contract для source type, safe auth-reference label, accepted event
schema, bounds и redaction/storage policy, не читает event records и не
контактирует с Trino coordinator. Добавлен
`query-doctor-trino-http-event-archive-import`: он читает один explicit
operator HTTP(S) archive URL после accepted `http_event_listener_archive`
contract, выводит только safe summary или raw-free boundary JSON, не echo-ит
URL, не принимает URL credentials и не submit-ит SQL.
Добавлен также `query-doctor-trino-http-query-detail-archive-import`: он
читает один explicit operator HTTP(S) archive URL после accepted
`http_query_detail_archive` contract, выводит только safe summary или raw-free
boundary JSON для одного compact sanitized query-detail record, не
контактирует с Trino coordinator, не fetch-ит query-info by Query ID, не
echo-ит URL, не принимает URL credentials и не submit-ит SQL.
Добавлен также `query-doctor-trino-coordinator-query-info-target-check`: он
валидирует один compact future `coordinator_query_info` source contract,
coordinator base URL shape и Query ID shape, выводит только safe summary без
URL/Query ID, не контактирует с Trino, не вызывает `/v1/query`, не fetch-ит
query-info JSON и не делает live Query ID diagnosis.
Добавлен также `query-doctor-trino-coordinator-query-info-pruned-probe`: он
валидирует тот же `coordinator_query_info` source contract с
operator-managed auth reference, делает ровно один bounded
`GET /v1/query/{queryId}?pruned=true`, проверяет response как bounded JSON
object и выводит только safe summary. Он не печатает и не хранит URL, Query ID,
raw QueryInfo, query text, session fields, endpoint URLs или object names, не
мапит QueryInfo в facts, не crawl-ит query history, не submit-ит SQL и не
делает browser/report/optimizer output или live Query ID diagnosis.
Pruned coordinator QueryInfo probe/import reads теперь не следуют HTTP
redirects для single bounded `GET /v1/query/{queryId}?pruned=true`, чтобы
explicit coordinator target не расширялся в redirected egress path.
Trino compact readiness audit теперь имеет strict
`--require-one-query-boundary` gate: aggregate `query_list_*` boundaries не
могут засчитываться как one-query Trino diagnosis readiness.
Он также принимает `--diagnosis-json <raw-free-trino-diagnosis.json>` для
artifact, записанного из той же boundary: audit сравнивает файл с
deterministic compact diagnosis из boundary, reject-ит raw-like diagnosis text и
не печатает local paths или filenames.
Тот же audit теперь принимает dev-only Kerberos/SPNEGO
`trino_smoke_summary.json` через `--smoke-summary`; strict release-facing dry
runs могут добавлять `--require-executed-smoke`, чтобы dry-run plan не считался
executed test-cluster smoke.
Pruned coordinator QueryInfo import теперь поддерживает
`--boundary-out <raw-free-trino-boundary.json>`: direct
`engine_fact_boundary_v1` payload можно записать для local readiness audit без
печати output path; пересечение с source contract, auth-header file или
diagnosis output reject-ится.
`query-doctor-diagnose-trino-compact` теперь может диагностировать один
selected sample boundary из Trino package boundary export, созданного через
`query-doctor-trino-import --format boundary-json`. Multi-sample package
exports требуют `--sample-index <zero-based-index>`, direct boundary JSON
работает без index, а isolated `/trino/compact-diagnosis` page принимает тот
же direct boundary или selected package sample без echo submitted JSON. Raw
payloads, non-Trino boundaries, SQL execution, browser/report output и live
Query ID diagnosis остаются неподдержанными.
Английский `Unreleased` также фиксирует новые open trust-boundary follow-ups:
Query Optimizer prompt-injection framing/guard tests для delimited `INPUT SQL`
и fail-closed regression coverage для trusted-output validation modes,
browser/trusted markers и defensive web fallback handlers.
Дополнительно английский `Unreleased` фиксирует defense-in-depth follow-ups:
adversarial redaction corpus для free-text host/secret variants в local/log/
browser fallback surfaces и pathological-within-cap regression coverage для
regex resource-bound paths.
Свежий English `Unreleased` также добавляет explicit ignore coverage и staged
public-safety guards для generated staging directories: `.replace-*`,
`.query-refresh-*` и `.cm-timeseries-refresh-*` теперь защищены и вне
default corpus roots.
Также добавлены route-level traversal/symlink guards для batch и Specific Query
report export routes: encoded path-shaped IDs не выбирают case, symlinked
reports outside case dir остаются hidden, а fixed markdown download filenames
остаются pinned.
Committed text fixtures under `tests/fixtures/` теперь проходят dedicated
public-release provenance pytest scan, так что новые fixture families должны
оставаться synthetic, example-only или явно redacted.
README screenshot provenance теперь machine-checkable через
`docs/assets/readme-screenshot-provenance.json`: manifest связывает public
README screenshots с synthetic demo pack, documented capture route, viewport,
README usage и PNG dimensions.
Также английский `Unreleased` фиксирует release-hygiene follow-up: перед public
branch handoff merge-heavy local history должна быть очищена в semantic review
commits. Package version metadata уже использует `pyproject.toml`
`[project].version` как canonical source для legacy `setup.py` shim.
Round-2 audit follow-ups теперь тоже зафиксированы public-safe: report
validators требуют adversarial coverage для indirect unsupported claims,
browser display должен скрывать model/runtime
fingerprints, generated case staging dirs требуют explicit ignore coverage, а
traversal/symlink artifact guards должны быть pinned tests. Subprocess output
capture follow-up из этого audit теперь реализован в английском `Unreleased`;
остальные пункты остаются open hardening work.
Свежий English `Unreleased` также фиксирует shared outbound egress policy,
false-positive-calibrated redaction для safe table/pool/file identifiers,
browser model-name redaction для `gpt-4`/`gpt-4o` variants и context-only
resource-trace fallback без primary-bottleneck promotion.
Report validators теперь reject-ят soft English stats-maintenance overclaims,
где stats refresh/maintenance заявлены как fix, reason или explanation.
Trusted report markers теперь bind-ятся к current marker schema version и
reject-ят missing/stale schema markers before browser display.
Public docs дополнительно сокращены: validation log, model route protocol,
code/analyzer audits, repository-hardening, architecture и smoke docs больше не
публикуют local run journals, model bake-off tables, real-looking case IDs,
private connectivity commands, generated output paths или detailed maintainer
evidence.
Английский `Unreleased` также включает документационный baseline pass для
опубликованного релиза `0.4.0`, проверку актуальности README screenshots и
обновление русской документации: все текущие английские Markdown-документы имеют русскую
сопроводительную страницу, а русская навигация фиксирует правила терминологии.
Synthetic demo pack расширен с трех до одиннадцати cases: теперь он начинается
с Workloads / Action Queue и покрывает optimizer recommendations, stats
maintenance, rejected optimizer draft, admission/runtime workload regression,
Storage/HDFS runtime follow-up, frequent short workload, mixed diagnostic
signals, unknown-but-useful limited evidence, direct Impala compatibility и
local synthetic action outcomes без LLM, network, Cloudera Manager, Impala или
private artifacts.
Trusted optimizer `no_rewrite` и recommendations-only outcomes теперь прямо
объясняют no-draft boundary: это manual review guidance, а не trusted SQL
draft; перед claim о пользе нужно сравнить EXPLAIN и comparable rerun.
Optimizer roadmap / validation log / code audit / handoff / agent playbook
теперь фиксируют candidate-calibration baseline и правило следующего среза:
сначала raw-free funnel/shape audits, затем no-draft guidance, fixtures или
Python-owned recipe только при доказанном validation boundary.
Добавлен Trino test-cluster evidence export checklist: он описывает первый
operator-exported sanitized handoff package для будущих real-cluster fixtures
без live collector, engine selector, browser/report surface или claims о
поддержке Trino. Добавлены Trino evidence package templates для manifest и
redaction note: они фиксируют safe package labels, redaction assertions и
fixture-only acceptance gate без live collector, UI/report surface или public
support claim.
Добавлен Trino private-preview release path для closed test-cluster работы:
runbook фиксирует allowed/forbidden release wording, dev-only Kerberos/SPNEGO
smoke, sanitized evidence-package intake и release gates, сохраняя Apache
Impala единственным production engine support.
Current-upstream Impala smoke в английских docs теперь описан generic direct
Impala placeholders и follow-up gates для будущего усиления wording по
поддержке актуальной Impala без hostnames, local config, target selectors,
query IDs, raw profiles, generated case paths или smoke artifacts.
Добавлен repeatable fixture-only Trino evidence-package walkthrough для
committed synthetic fixtures. Локальная demo-команда собирает и валидирует
package shape, может опционально записать sanitized demo package и печатает
только path-free safe summary без live collection, SQL execution, credential
access, engine registration, UI/report output, optimizer behavior или support
claims.
Добавлен fixture-only Trino evidence package builder для already-sanitized
compact sample JSON files. Локальный script собирает package wrapper, требует
explicit redaction-review и sentinel-test confirmations, validates before
writing output и печатает только path-free safe summaries без live collection,
engine registration, UI/report output, optimizer behavior или support claims.
Добавлен локальный Trino evidence package validator script:
`python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>`
проверяет fixture-only package intake gate и печатает только safe package /
manifest source summary или safe rejection message, без raw payloads, file
paths, raw values, SQL text, identifiers, hostnames, object names, connector
details или rejected record contents. Package wrapper теперь reject-ит
unsupported top-level sections.
Добавлен fixture-only Trino evidence package intake validator: локальный
sanitized wrapper `manifest` / `redaction_note` / `samples` fail-closed
проверяет safe package labels, redaction assertions, sentinel-test coverage,
declared bounds, sample counts, raw-free payloads и существующие
statement-statistics/event-listener fixture validators без live Trino
collection, engine selector, UI/report output или support claim.
Добавлен dev-only Trino Kerberos/SPNEGO smoke script: он использует `curl` с
явным Kerberos service name, выполняет только built-in read-only smoke
statement shapes, следует bounded Trino protocol pages и пишет safe summary без
statement text, result values, query identifiers, actor identity values,
coordinator hostnames, object names или raw failure details. Скрипт не
подключен к product workflows Query Doctor и не добавляет live Trino
collection, engine selector, UI/report output, optimizer behavior или support
claim.
Также добавлен raw-free offline audit для profile evidence gates на существующих
Recent `batch_summary.json`, а analyzer теперь выводит context-only Resource
Trace Facts для безопасных агрегатов CPU, диска и сети из профиля Impala без
primary-bottleneck promotion. Fixture-only Trino event-listener coverage теперь
также включает compact resource-group queue-delay event без live reader,
browser/report surfaces или claims о поддержке Trino. Добавлен unknown
source-contract event gate: неподдержанный compact source contract оставляет
parser coverage и факты в `unknown`.
Compact summary shapes для Trino connector metric, failure category и stage
skew теперь остаются `unknown`, если присутствуют extra fields или nested
details.
Дополнительно tightened statement-stats fixture intake: oversized payloads,
unsafe raw field names и unsafe text values теперь reject-ятся до mapping.
JSON shape guards для Trino fixtures теперь явно покрывают nested
objects/arrays и maximum-depth rejection до mapping.
Non-finite numeric values (`NaN`, `Infinity`, `-Infinity`) теперь reject-ятся
до mapping для statement-stats и event-listener fixtures.
Отрицательные Trino timing/resource/count values теперь остаются `unknown`
вместо supported facts или fake zeros.
