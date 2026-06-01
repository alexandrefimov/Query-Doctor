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

Английский `Unreleased` сейчас включает разделение committed public docs и
ignored local agent notes: durable agent baseline остается в public docs,
private continuation notes живут в local exclude-only notes, а
`scripts/audit_public_docs.py` ловит common local handoff markers перед commit.
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
