# Query Doctor 0.3.0 Release Notes

Release date: 2026-05-23
Package: `query-doctor` 0.3.0
Supported diagnostic engine: Apache Impala

0.3.0 is the analyst-workflow release. It turns Recent Scan and Details into a
tighter triage flow, adds workload-level views for repeated query shapes,
hardens deterministic evidence before root-cause wording, and prepares future
engine contracts without adding unsupported live engines.

## Highlights

- Recent Scan is now the primary product path: the first screen focuses on
  finished queries, running queries, and one known Query ID instead of exposing
  collector internals first.
- Details now follows the decision path analysts need: why the query deserves
  attention, where to inspect, what supported change direction to try, and how
  to verify a comparable rerun.
- Workload triage is now visible for repeated fingerprints, frequent short
  workloads, local regressions, pool/owner aggregates, action queues, and
  workload detail pages, while keeping source text and local history paths out
  of browser output.
- The Query Optimizer page is clearer and safer for pasted SQL analysis, with
  input rules in the field help, compact safety scope, and optimizer-specific
  empty/error states.
- Analyzer evidence is stricter: profile format, exec-node completeness,
  runtime admission, memory pressure, client-fetch tail, and source-locator
  facts now control when Query Doctor may promote diagnostic claims.
- The project is now Apache-2.0 licensed and the package metadata builds cleanly
  with modern Python packaging toolchains.

## Analyst Workflow

- Diagnose now uses one workflow selector for `Finished queries`, `Running
  now`, and `One Query ID`; secondary scan options are collapsed until needed.
- Recent Results keeps the default view focused on `Needs attention` and
  `Worth reviewing`, with rewrite, stats, workload, action-outcome, and scan
  context groups available under compact disclosures.
- Results tables are easier to scan on desktop and render as labeled row cards
  on mobile, avoiding horizontal clipping on narrow screens.
- Details verdicts use analyst-readable review signals such as query-shape
  review, stats gaps, runtime queueing, skew, data movement, storage follow-up,
  or processing failure instead of internal classifier labels.
- Recommended-change cards lead with safe review anchors, change direction, and
  verification metrics; score/rank metadata and lower-level evidence remain
  available below the actionable guidance.
- Clean and failed rows now fail closed for report/optimizer actions. Clean
  selected cases do not expose unsupported optimizer actions, and failed cases
  show a processing-failure follow-up until deterministic analysis succeeds.
- Known Query ID jobs now show server-owned progress steps for validation,
  profile collection, deterministic analysis, result preparation, and
  completion.
- The web UI can run in English or Russian through the non-secret `language`
  config field, with Russian static copy polished across Help, Details, and
  optimizer outcomes.

## Workload Triage

- Recent Results adds repeated workload, frequent short workload, and regressed
  workload groups from safe current-scan and local-baseline facts.
- The new Frequent short preset removes the default minimum-duration filter via
  existing bounded scan flags, helping admins find small repeated query shapes
  that matter because of aggregate impact.
- Workload detail pages show raw-free fit, current-scan impact, pool/owner
  context, primary-signal mix, limitations, representative cases, and case
  links from the server-owned scan summary.
- Workload digest and admin digest views include pool/owner aggregates, status
  issue clusters, low-value repeated group marking, signal filters, focused
  group links, and deterministic action queues.
- Action outcome rollups are now shown per workload fingerprint using only
  allowed outcome labels and whitelisted recommendation labels.

## Analyzer And Evidence

- Profile dialect detection now distinguishes Impala classic text, classic
  JSON, classic Thrift, experimental profile-v2, and unknown profiles, with
  fail-closed policy facts for unmapped profile-derived evidence.
- Incomplete or cancelled exec-node evidence now limits row/cardinality claims
  and blocks unsafe stats-primary promotion from affected profile sections.
- Runtime admission evidence now separates selected-query admission result,
  admission wait, and query-timeline admission phases from weaker pool,
  cluster, metric, event, or duration-only context.
- Memory pressure evidence now requires strong selected-query spill or scratch
  facts before promoting memory pressure; estimates, reservations, peak memory,
  daemon metrics, and runtime context stay context-only by default.
- Client-fetch-tail detection maps Impala `ClientFetchWait*` counters into
  raw-free evidence and promotes a fetch-tail bottleneck only when it dominates
  selected-query duration and no stronger backend/runtime finding outranks it.
- Recent action candidates can now carry raw-free review locations for SQL
  structure, plan operators, metadata stats, runtime admission, and owner-gated
  source coordinates without rendering raw SQL or profile text.

## Safety And Trust Boundaries

- Browser-visible pages, trusted reports, and optimizer outcomes continue to
  hide raw SQL, raw profile text, raw metadata, generated artifact filenames,
  local paths, model names, subprocess output, and secrets.
- Report and optimizer actions fail closed unless the selected case is
  server-owned and deterministic analysis facts support the action.
- Browser-display redaction, demo preflight, and staged public-safety checks now
  share the generated-artifact denylist, including canonical runtime and
  cluster context artifacts.
- Public issue, pull request, contribution, and security templates now steer
  reproductions toward synthetic data and explicitly block real-cluster
  screenshots, logs, generated artifacts, reports, and operational payloads.
- Metadata collection remains read-only, allowlisted, bounded, explicit, and
  redacted.

## Configuration And Operations

- Config discovery now prefers `~/.qdcreds/query-doctor-config.json` when no
  current-directory config is provided.
- The example config is more compact: cluster-specific Cloudera Manager and
  direct Impala settings live under `clusters[]`, and default protocol,
  redaction, recent-scan, metadata bounds, and local Ollama values are omitted
  unless an environment needs to override them.
- `query-doctor-web` can derive owner dropdown choices from simple keytab user
  names without exposing keytab paths or full principals.
- The local web wrapper now defaults Kerberos cache usage to the generic
  Query Doctor cache path and keeps Cloudera Manager auth in `cm-ro.env`.
- `batch_recent` can select a configured cluster with `--config-cluster`, so
  direct Impala, metadata, Prometheus, redaction, and owner-gated visibility
  settings come from the same cluster config used by the web UI.
- Report generation and Query LLM optimizer routes now use separate non-secret
  LLM config fields for provider, model, base URL, and optional chat path;
  API tokens stay in the local env file.

## Future Engine Groundwork

- Apache Impala remains the only implemented and supported engine in 0.3.0.
- 0.3.0 adds a raw-free normalized engine-fact contract, Impala projection,
  support-gap matrix, golden harness, and boundary payload tests so future
  engines can be compared by typed facts instead of UI-specific assumptions.
- Fixture-only Trino work now covers statement statistics, completed events,
  missing fields, blocked statements, stage skew candidates, connector metric
  presence, and failure categories.
- The Trino work is intentionally not live collection and not product support:
  there is no live Trino reader, no browser/report wiring, no SQL execution,
  and no public second-engine support claim.

## Documentation And Release Hygiene

- README, demo docs, screenshots, release readiness docs, and public navigation
  now match the current synthetic demo pack and material web UI baseline.
- Agent instructions now require a documentation drift check for every code
  change and a README/screenshot drift check for user-facing workflow, CLI,
  config, demo, packaging, or release changes.
- `scripts/worktree_status.py` reports active worktrees, dirty state,
  divergence from `main`, merged status, and conservative cleanup/merge
  recommendations for parallel-agent work.
- Package workflows now validate package metadata before build/publish jobs,
  and 0.3.0 removes the old license classifier that conflicts with SPDX
  metadata under modern setuptools.

## Upgrade Notes

- Review `docs/configuration.md` if you use local web config, LLM routes,
  owner-gated source visibility, direct Impala collection, Prometheus metrics,
  or multi-cluster `clusters[]` config.
- Existing compatibility aliases and legacy artifact read fallbacks remain for
  release-era support, but new code and docs prefer canonical query metadata
  and runtime metrics context names.
- Trino-related files in this release are fixture contracts and research
  groundwork only. Do not configure Trino as a supported production engine in
  0.3.0.
- The public license is Apache-2.0. The previous separate commercial licensing
  path has been removed from public docs.

## Release Validation

The 0.3.0 release candidate was validated with:

- `PUBLIC_RELEASE=1 scripts/local_gate.sh`
- `pre-commit run --all-files`
- package build plus `twine check`
- installed-wheel smoke for synthetic demo generation, web/report/optimizer
  command entry points, and public-release demo preflight
