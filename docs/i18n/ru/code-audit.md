# Code Audit

Last reviewed: 2026-06-04

Язык: [English](../../code-audit.md) | Русский

Английская версия является канонической. Эта страница - русский companion для
public-safe engineering и safety risk summary.

## Назначение

`docs/code-audit.md` хранит durable public risk areas без local calibration
history, private batch measurements, generated paths или branch-specific notes.

## Как использовать

- Перед изменением trust boundary проверьте, есть ли связанный audit finding.
- Не закрывайте finding только текстом; закрытие требует code/tests/docs,
  которые устраняют риск.
- Если finding устарел из-за фактической реализации, обновите public
  conclusion; detailed validation evidence держите в local exclude-only notes.

## Актуальные public findings

- Outbound HTTP clients теперь используют shared no-redirect egress policy:
  strict public targets, configured diagnostic targets, DNS-resolved target
  validation, private/loopback opt-in только там, где это явно нужно,
  mandatory byte caps и guard tests для unsafe destinations. Spark History
  Server compact preview держит strict public target default, local/private
  opt-in и fail-closed mapping для shared egress violations. Maintenance risk:
  новые HTTP clients не должны обходить эту policy, response byte caps или
  добавлять raw `urlopen` paths.
- Report validators теперь reject-ят indirect unsupported root-cause wording,
  soft stats-maintenance recommendations, English stats-maintenance
  fix/explanation overclaims, flexible row/cardinality estimate phrasing и
  compact EN/RU parity matrix для memory estimate direction, backend data skew,
  primary bottleneck, CM context-only metrics и CM event context, сохраняя
  nearby safe wording allowed. Public report-language keys теперь
  нормализуются через shared report-language registry, а unknown languages
  fail closed на config/CLI boundaries без silent fallback. Raw SQL-like text
  rejection теперь покрывает fenced snippets, line/item-level SQL и inline
  prose с SQL-like `SELECT`, `WITH`, DML/DDL или metadata `SHOW` statements на
  trust gate, а не только browser/download display scrubbing. Под этим finding
  сейчас нет remaining guard work; adversarial report-validator corpus нужно
  держать в focused validation при изменениях report wording/trusted markers.
- Query Optimizer rewrite prompts должны явно framing-ить `INPUT SQL` как
  untrusted data; нужны guard tests, где prompt-injection внутри source SQL
  приводит только к validator rejection, trusted `no_rewrite` или safe
  recommendations, но не к trusted unsafe draft.
- Fail-closed trusted-output paths требуют прямого regression coverage:
  browser/trusted markers должны reject-ить non-strict validation modes, а
  defensive web catch-all handlers должны возвращать redacted fallback без raw
  SQL, paths, subprocess output или artifact names. Report и optimizer trusted
  markers теперь bound к current marker schema version, чтобы старые weaker
  marker contracts не переживали upgrade молча.
- Redaction adversarial corpus покрывает free-text host/secret варианты:
  bare FQDNs, one-label hostnames, explicit host fields, URL hosts,
  credential/passphrase/private-key/auth assignments и normal IPs. Он также
  фиксирует false-positive boundary для curated SQL/table/pool/file
  identifiers, чтобы они не превращались в host aliases. Alternate IP encodings
  и IDN/Unicode-like host text остаются lower-priority defense-in-depth gaps.
  Trusted reports и browser должны по-прежнему опираться на raw-free
  Python-owned facts.
- ReDoS/resource-bound follow-up: текущие inputs capped before regex-heavy
  paths и regex style выглядит bounded. Теперь есть bounded
  pathological-input guard coverage для redaction/browser/report/optimizer
  validation paths; при расширении этих regex surfaces нужно сохранять такие
  tests на completion и safe rejection/redaction. Parent-side subprocess
  stdout/stderr capture остаётся bounded even for real subprocess calls and
  defensive custom-runner returns.
- Pre-push history hygiene является release/public-sharing gate: локальная
  merge-heavy history должна быть переписана в reviewable semantic commits до
  любого push/review branch handoff; нельзя публиковать local `main` as-is.
- Trino preview source-contract registry теперь является владельцем accepted
  preview `source_type` values, raw policy, required bounds, network-access
  classes и promotion gate. Support-gap audit проверяет registry coverage и
  reject-ит включение product surfaces, Details/trusted reports, Recent scans,
  optimizer behavior, SQL execution, raw storage, browser/report output или
  metadata identifier output. Remaining architecture backlog больше не считает
  этот registry будущей задачей.
- Cross-engine fact-promotion policy теперь находится в
  `query_doctor/analyzer/engine_fact_promotion_policy.py`. Support-gap audit
  проверяет coverage для Trino-visible shared/distributed/source/support
  boundary facts, `allowed_engines`, scope alignment, raw-free policy,
  disabled product surfaces и explicit promotion gates. Remaining architecture
  backlog больше не считает shared/distributed fact-promotion будущей задачей.
- Shared dev-only handoff artifact helpers теперь находятся в
  `query_doctor/safety/handoff_artifacts.py`. Trino/Spark handoff scripts
  используют их для path overlap checks и ASCII/sorted JSON writes, но
  engine-specific redaction guards, readiness gates и below-support wording
  остаются в owning scripts.
- Packaging metadata теперь использует `[project].version` в `pyproject.toml`
  как canonical source; legacy `setup.py` shim читает это значение и остается
  покрыт package metadata/console-script tests.
- Demo fixture/screenshot provenance guard: committed text fixtures under
  `tests/fixtures/` покрыты public-release provenance pytest scan, а README
  screenshots теперь pinned в
  `docs/assets/readme-screenshot-provenance.json` вместе с synthetic demo-pack
  version, capture route, viewport, README usage и PNG dimensions.
- Case lifecycle guard: transient replacement/refresh staging directories
  теперь имеют explicit ignore coverage и staged public-safety regression
  checks для non-default corpus. Новые generated staging dir families должны
  добавляться и в `.gitignore`, и в staged public-safety checks.
- Browser/artifact boundary guard: current route/path boundary теперь pinned
  route-level traversal/symlink tests для batch и Specific Query report export
  routes, включая encoded path-shaped IDs, symlinked reports outside case dir и
  fixed markdown download filenames. Browser-display tests для current
  model/runtime-name variants тоже есть; новые internal fingerprints должны
  добавляться в этот corpus до rendering.

Полный список рисков и приоритетов находится в
[английском audit](../../code-audit.md).
