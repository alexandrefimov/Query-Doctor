# Query Doctor 0.11.0 Release Notes

Release date: 2026-08-10
Package: `query-doctor` 0.11.0
Container image: `ghcr.io/alexandrefimov/query-doctor:0.11.0`
Release focus: Kubernetes-ready web deployment, container image support,
Helm chart support, synthetic Kubernetes self-test, raw-free deployment
readiness, health probes, one-profile web intake, persistent Recent profile
reuse, raw-free Online History, bounded Impala EXPLAIN artifact analysis, and
release-grade image validation

0.11.0 is the release where Query Doctor becomes practical to run as a
containerized web service. The Python package remains the primary local-first
operator tool, and Apache Impala remains the full production triage engine, but
the web UI now has a supported Docker image, Kubernetes deployment manifests,
a Helm chart, liveness/readiness probes, a bounded local/private one-profile web
upload path, and container CI.
It also adds a Kubernetes self-test Job, Helm test hook, and raw-free
deployment readiness summary for narrow cluster-side and pre-start confidence
checks.

The Query Inbox is now the primary web workflow for retained Recent results.
It combines raw-free Online History, bounded profile-job planning and worker
state, materialized Details snapshots, workload grouping, filters, and safe
view presets without turning browser refresh into synchronous profile, report,
optimizer, metadata SQL, or SQL-execution work.

This is not a hidden expansion of the security or engine boundary. Kubernetes
support means a supported web deployment starting point. It does not add native
authentication, authorization, sessions, RBAC, multi-tenant isolation, an
operator/CRD, arbitrary command running, SQL execution, or broader engine
support inside Query Doctor.

## Kubernetes-Ready Web Deployment

- Added a root `Dockerfile` for the Query Doctor web UI.
- The image runs as fixed non-root UID/GID `10001:10001`.
- The default image command starts the safe read-only synthetic demo:
  `query-doctor-web --host 0.0.0.0 --port 8765 --allow-nonlocal-web-bind --public-demo`.
- The image exposes port `8765` and includes a Docker healthcheck against
  `/healthz`.
- The image runs Query Doctor on supported Python 3.10 and includes Kerberos
  client tools plus the isolated
  `/opt/query-doctor/.venv-impala-shell/bin/impala-shell` runtime for
  configured Impala metadata refresh. Credentials, keytabs, ticket caches, and
  metadata coordinator settings still stay outside the image.
- The Helm chart can optionally run a configured-mode `kerberos-kinit`
  initContainer from an existing Secret and a bounded
  `kerberos-ticket-renewer` sidecar for the long-lived web pod. They write and
  refresh a shared ticket cache under `/tmp/query-doctor-krb5/`; the web
  container receives the cache and optional `krb5.conf`, not the principal or
  keytab. Finite collector and worker CronJobs continue to obtain one fresh
  ticket per Job instead of receiving a non-terminating sidecar.
- Added bounded staging smoke gates for one Kerberos cache refresh and one
  installed Online History collector/worker/operator-readiness cycle. The
  gates compare only raw-free status, cache timestamps, Job completion, image
  consistency, and allowlisted UI markers; they do not print tickets, Job logs,
  SQL, profiles, or retained page contents.
- Web deployments expose `/deployment/readiness.json` for a raw-free operator
  summary of mode, bind scope, source-type counts, probe endpoints, and safety
  boundary status.
- `.dockerignore` now excludes local configs, credentials, generated cases,
  reports, raw profiles, raw SQL, logs, caches, virtualenvs, and repository
  internals from the image build context.

## Kubernetes Manifests

Kubernetes assets now live in `deploy/kubernetes/`.

- `public-demo.yaml` runs the read-only synthetic public demo with no
  credentials.
- The public-demo pod uses a non-root security context, drops Linux
  capabilities, disables service-account token mounting, uses a read-only root
  filesystem, mounts writable `/tmp`, and denies pod egress with a
  `NetworkPolicy`.
- `configured-web.yaml` is a private operator template for real configured
  web use. It mounts a Query Doctor config, reads credentials from a
  pre-created Kubernetes Secret, stores generated cases on a PVC, and exposes a
  ClusterIP Service plus example Ingress.
- Configured web pods use a heavier Recent-ready resource baseline than the
  public demo: `250m`/`512Mi` requests and `2`/`2Gi` limits.
- Non-local configured web binds use conservative Recent defaults unless the
  private config overrides them: profile analysis limit `50`, overall Recent
  parallelism `4`, metadata parallelism `2`, and metadata top limit `10`.
- Finished-query web Recent scans reuse already analyzed local cases when the
  Query ID matches a previous successful safe redacted batch output. Reused
  cases are copied into the new batch output, counted in the summary, and skip
  duplicate profile collection and deterministic analysis. Prior summaries must
  carry the same explicit profile reuse contract before artifacts are reused.
  Results coverage shows the aggregate reused-profile count, and a second
  submit for the same running finished Recent scan returns the existing job
  instead of launching duplicate collection.
- `configured-web.yaml` sets `recent_batch_root` to the dedicated temp-backed
  case-PVC cache mount, so configured Kubernetes deployments can preserve the
  finished-query Recent reuse cache across pod restarts without exposing raw
  SQL or raw profiles in trusted browser/report surfaces.
- Batch Recent can also write an optional local SQLite `recent_history_db`
  containing raw-free summary history for all discovered candidates. The store
  records bounded summary signals, selected/suspicion reason codes, and profile
  status without retaining raw SQL or profile text. `--discover-only` history
  runs also plan pending profile jobs for suspicious or selected summaries
  under the existing Recent profile budget. Batch summaries record only
  aggregate history-store status, summary count, and planned-job count.
- Configured web Query Inbox can render that retained history as a bounded
  read-only Online History view. It uses only raw-free summary fields, hides raw
  SQL/profile text/local store paths/raw artifact names, and keeps rows without
  materialized case artifacts read-only until a scan or profile worker creates
  Details artifacts. History-backed web refreshes use discover-only Recent
  scans, so they update retained summaries and profile-job planning without
  synchronous profile analysis, metadata SQL collection, LLM reports, optimizer
  jobs, generated SQL, or SQL execution.
- Helm configured installs can also render a disabled-by-default
  `recentSummaryCollector` CronJob for the same discover-only Recent planning
  loop against Postgres history. It writes retained summary rows and planned
  profile jobs plus a raw-free collector run summary without collecting
  profiles, running metadata SQL, LLM reports, optimizer jobs, or
  operator-readiness audits.
- Online History now overlays current Recent profile worker lifecycle state for
  retained rows, including pending, processing, retry-pending, analyzed, and
  failed. The Query Inbox status banner summarizes those states as aggregate
  profile-loop and Details-ready metrics. The status remains raw-free, keeps
  rows read-only until the analysis cache is materialized, and is not reset to
  not-collected by rediscovery.
- The same Online History banner now shows Recent summary collector freshness
  from the latest retained planning timestamp. This flags stale discover-only
  producers separately from profile-worker backlog health and derives safe
  next-step text without exposing Query IDs, source keys, local paths, raw
  collector payloads, or retained free-form text. Configured web installs can
  also point `recent_history_collector_summary_json` at a retained
  `query_doctor_recent_history_collector_v1` summary so Query Inbox shows the
  producer's last allowlisted status, age, recorded-row, and planned-job
  counters while invalid or unsafe summaries degrade to safe status. Batch
  Recent mirrors the same allowlisted collector summary fields into optional
  `--progress-jsonl` events for recorded, disabled, warning, and failed
  producer states without exposing raw SQL, Query IDs, local paths, raw errors,
  or retained free-form text. Helm configured installs wire the scheduled
  `recentSummaryCollector` CronJob to retain that progress JSONL stream on the
  case PVC through `recentSummaryCollector.progressJsonl`, with chart
  validation keeping it under `persistence.mountPath` and separate from
  `summaryJson`.
- Configured Online History can also point
  `recent_history_operator_readiness_summary_json` at an already retained
  `query_doctor_recent_history_operator_readiness_v1` summary. Query Inbox
  projects only allowlisted readiness, evidence, reason-code labels, schema,
  worker, and retention counters into the status banner. Invalid, wrong-kind,
  or unsafe summaries degrade to a safe blocked/unavailable status without
  exposing the configured path, raw JSON, raw SQL, profile text, local store
  paths, or raw artifact names.
- Analyzed Online History rows can now open a raw-free Details snapshot when
  the history store has a ready `recent_analysis_cache` payload linked through
  available `fingerprint_only` profile-artifact metadata. Rows without that
  materialized cache stay read-only. The snapshot includes only allowlisted
  score, recommendation, aggregate metadata coverage, and processing timing
  fields; it does not expose profile bytes, profile fingerprints, storage keys,
  local paths, LLM reports, optimizer jobs, generated SQL, or SQL execution.
- Batch Recent can also write the same raw-free summary history to Postgres by
  setting `recent_history_backend=postgres`. The DSN is read from a
  Secret/env-provided variable, not JSON config, and the container image can be
  built with `QUERY_DOCTOR_INSTALL_EXTRAS=postgres` to include the optional
  driver. The Helm chart can reference that DSN from an existing Secret key in
  configured mode without rendering Secret objects.
- The Helm chart can optionally render a configured-mode CloudNativePG
  `Cluster` for Recent history Postgres. The chart does not install the CNPG
  operator, render Secret objects, or accept inline database passwords or DSNs.
  Query Doctor can consume the standard application Secret generated by CNPG
  through its `uri` key; external owner credentials and a separate DSN Secret
  remain supported.
- Recent history storage now has raw-free `recent_profile_job`,
  `recent_analysis_cache`, and `recent_profile_artifact` metadata tables plus a
  deterministic planner that turns retained summary records into pending
  profile jobs under an explicit budget. The planner ranks by suspicion score,
  selected-candidate status, and duration; discover-only Recent runs enqueue
  those jobs for the shared worker.
- Pending profile jobs can now be claimed atomically with a safe lease owner and
  lease deadline. SQLite uses a local transaction lock; Postgres uses
  `FOR UPDATE SKIP LOCKED` for CNPG workers. Claims can be filtered by
  engine/source/source key, and leased jobs also have owner-guarded lease
  renewal, completion, retryable failure, and terminal failure transitions.
  Stored failure reasons are safe error codes only.
- `query-doctor-recent-profile-worker` now processes queued Recent profile jobs
  from SQLite or Postgres/CNPG. It claims only jobs for the configured source,
  collects bounded profiles through existing Impala Recent collectors, runs
  deterministic analysis with metadata mode off, and writes raw-free
  analysis-cache plus profile-artifact metadata. It does not run LLM reports,
  Query Optimizer jobs, generated SQL, metadata SQL collection, browser raw
  source rendering, or raw profile storage in the history database.
- The Helm chart can optionally render that worker as a configured-mode
  `recentProfileWorker` CronJob after Postgres history is enabled. The CronJob
  uses the same external Secret/config/PVC/Kerberos wiring as the web pod and
  keeps raw-free JSON output, metadata collection off, and top reports
  disabled. The chart can also render a Postgres-only
  `recentHistory.postgres.retention` CronJob that runs only raw-free retention
  pruning with the DSN Secret env and does not mount Query Doctor config,
  collection credentials, Kerberos material, or case PVCs.
- The `recent_analysis_cache` table now has SQLite and Postgres upsert/load
  APIs keyed by engine/source, Query ID, profile fingerprint, and analyzer
  contract. Cached payloads are sanitized as raw-free JSON and scrub dangerous
  raw-key fields before storage, preparing durable analyzed-profile reuse
  without storing raw SQL, raw profile text, local paths, artifact names, model
  names, or secrets.
- The `recent_profile_artifact` table now stores raw-free selected-profile
  artifact metadata: compatibility keys, status, size, a `fingerprint_only`
  storage kind, and an opaque fingerprint key. It rejects path-like keys and
  storage kinds that would retain profile bytes, local paths, object names, or
  external artifact references until a bounded delete implementation exists.
- The shared Recent profile worker now removes its own temporary local
  `profile-worker-cases/job-*` directory after each processed job without
  changing the raw-free history-storage contract or adding external artifact
  deletion.
- Recent history storage now has explicit SQLite and Postgres retention
  pruning for old summary rows, terminal profile jobs, analysis-cache records,
  and profile-artifact metadata. The API returns only aggregate delete counts
  and intentionally does not prune pending or leased profile jobs. Batch Recent
  can opt in with positive `recent_history_*_retention_days` config fields or
  matching CLI flags, and `query-doctor-recent-history-retention` provides a
  standalone raw-free maintenance command for scheduled pruning without query
  discovery or profile collection.
- `query-doctor-recent-history-postgres-readiness` checks the configured
  Recent history Postgres DSN env and schema initialization from the target
  runtime environment. It reports only raw-free status, check ids, issue codes,
  and aggregate booleans, not DSNs, hostnames, credentials, paths, Query IDs, or
  raw payloads.
- `query-doctor-recent-history-operator-readiness` validates retained raw-free
  Postgres readiness and profile-worker summary JSON files, plus an optional
  collector summary, retention summary, and profile-remediation summary, and
  writes one path-free operator handoff summary with accepted raw-free
  operation counters for schema readiness, collector producer status/freshness,
  profile-worker jobs and materialized records, retention deletes, and
  remediation dry-run/apply counts. The audit rejects unsafe retained fields or
  values and does not contact Postgres, Kubernetes, query engines, or profile
  collectors.
- The Helm chart can optionally render that audit as a configured-mode
  `recentHistory.operatorReadiness` CronJob after Recent history Postgres,
  Postgres readiness, and the Recent profile worker are enabled. The chart has
  the Postgres readiness initContainer, profile-worker CronJob, and optional
  retention CronJob retain their raw-free summaries on the case PVC, then runs
  the operator-readiness CronJob over only those summaries. The audit CronJob
  does not mount Query Doctor config, collection credentials, the Postgres DSN
  Secret, Kerberos material, or source endpoint configuration.
- Helm configured deployments that enable Recent history Postgres run that
  readiness command as a web pod initContainer by default with
  `--fail-on-warning`, so the pod waits for Secret/env DSN handoff and schema
  initialization before startup. The check does not contact query engines or
  run profile collection.
- `self-test-job.yaml` runs only
  `query-doctor-self-test --json --timeout-sec 120` as a synthetic package
  confidence check.
- Configured/shared deployments still require a trusted ingress or auth proxy
  for authentication, MFA, sessions, TLS, inbound-header stripping, and viewer
  identity injection. Query Doctor consumes `viewer_identity_header` only after
  those front-door duties are satisfied.

## Helm Chart

- Added `deploy/helm/query-doctor` as the upstream Helm entry point for web
  deployments.
- The default chart render is the same safe public-demo shape: no credentials,
  denied pod egress, non-root runtime, read-only root filesystem, probes, and
  service-account token automount disabled.
- Configured chart mode requires explicit config and persistent case storage.
- The chart web pod resources default to the same Recent-ready configured
  baseline: `250m`/`512Mi` requests and `2`/`2Gi` limits.
- The chart exposes `persistence.recentBatchMountPath`; when it matches the
  web config `recent_batch_root`, configured installs persist the finished
  Recent analyzed-profile reuse cache on the case PVC. The configured example
  uses the chart's dedicated temp-backed cache mount.
- The configured chart example leaves chart-owned ingress disabled. Shared
  deployments should expose a platform-owned SSO/auth front door, such as
  oauth2-proxy/Keycloak, and route that front door to the chart Service instead
  of publishing the configured web Service directly.
- Added a Kubernetes auth-front-door runbook and raw-free audit script for
  oauth2-proxy/Keycloak-style configured deployments. The audit checks that
  Ingress points at the auth proxy, the expected issuer/client and PKCE method
  are configured, cookie-backed sessions stay compact for large AD group claims,
  the proxy upstream points at Query Doctor, Secret values are not inlined,
  token and Basic auth forwarding flags are disabled, NetworkPolicy isolates
  the ingress-controller-to-auth-proxy and auth-proxy-to-Query-Doctor hops when
  strict mode is requested, and deployment readiness remains configured-private,
  SQL-disabled, and raw-output-disabled without printing hostnames, issuer URLs,
  redirect URLs, client IDs, Secret names, paths, users, label values, or case
  identifiers.
- The chart ships `values.schema.json` and fail-closed validation for unsafe
  public-demo/configured combinations.
- The chart is platform-neutral. It supports generic user-provided pod labels
  and annotations without embedding controller-specific labels, rollout
  metadata, or runtime-bundle contracts.
- The chart includes a synthetic `helm test` hook for
  `query-doctor-self-test`.
- Helm NOTES now print the port-forward, probe, deployment-readiness, and
  self-test commands after install.
- `scripts/helm-chart-smoke.sh` renders public-demo, configured, and synthetic
  self-test chart shapes, runs the raw-free Kubernetes deployment audit, and
  runs kubeconform when available.

## Synthetic Kubernetes Self-Test

- Added a raw Kubernetes self-test Job and matching Helm test hook.
- The self-test pod has no live config, credentials, PVC, Service, Deployment,
  Ingress, service-account token, or egress allowance.
- The command is fixed to `query-doctor-self-test --json --timeout-sec ...`.
- The self-test is not an arbitrary command runner and must not be repurposed
  for Recent scans, Running scans, Known Query ID, optimizer jobs, metadata
  collection, Trino/Spark probing, SQL execution, or platform smoke jobs.
- Added `scripts/kubernetes-self-test-smoke.sh` for a disposable Helm-based
  self-test smoke with pre-release image overrides and separate synthetic Job
  log capture.

## Deployment Readiness Summary

- Added `GET /deployment` and `GET /deployment/readiness.json` to the web UI.
- Added `query-doctor-deployment-readiness` for pre-start checks over the same
  startup settings used by `query-doctor-web`.
- The readiness summary is raw-free: it reports safe labels for mode, bind
  scope, source-type counts, probe routes, source visibility, owner-raw gate
  state, profile-upload state, LLM action state, and Kubernetes boundary
  reminders.
- The summary does not print config paths, endpoint URLs, hostnames, ports,
  users, viewer header names, local paths, model names, secrets, subprocess
  output, raw artifact names, raw SQL, raw profiles, or raw metadata.

## Health And Readiness Probes

- Added raw-free JSON `GET /healthz` for liveness.
- Added raw-free JSON `GET /readyz` for readiness.
- Probe responses include only safe service/probe status plus explicit
  `raw_output=false` and `sql_execution=false` flags.
- Probe tests assert that no raw SQL, local paths, or private runtime detail
  leaks into those responses.

## One-Profile Web Intake

- Local/private web sessions can now upload one exported Apache Impala text
  profile directly from `One Query ID`.
- The upload route is multipart-only, bounded by `max_profile_bytes`, accepts
  exactly one file, and rejects unsupported JSON, Thrift, and profile-v2 payloads
  through the same manual-profile analyzer path.
- The uploaded profile is staged into a server-owned case under `corpus_dir`,
  the deterministic Python report is generated in the explicit submit job, and
  the temporary upload file is removed after staging.
- Trusted browser surfaces do not render the uploaded profile text, uploaded
  filename, local path, subprocess output, temporary upload artifact, model name,
  or raw artifact filenames.
- Public demo mode hides the upload form and blocks upload POSTs before reading
  the request body.

## Bounded Impala EXPLAIN Artifact Analysis

- Query Doctor can parse one already-provided Impala EXPLAIN artifact from a
  case-contained, byte/line/node/fragment-bounded loader. It does not generate
  EXPLAIN or execute SQL.
- The parser retains only allowlisted raw-free optimizer-intent, estimate,
  coverage, limitation, and conservative structural-link facts. Raw plan text,
  relation names, predicate values, literals, paths, and engine-local
  identities are discarded.
- Missing, ambiguous, malformed, oversized, unsafe, or partially mapped input
  degrades without failing profile analysis. EXPLAIN facts do not change
  scoring, primary diagnosis, report trust, engine selection, or browser raw
  source boundaries.

## Container CI And Release Publishing

- Added `scripts/build-image.sh` and platform-aware `scripts/image-smoke.sh`
  for repeatable local image validation, including explicit
  `QUERY_DOCTOR_IMAGE_PLATFORM=linux/amd64` checks for amd64 Kubernetes smoke
  from arm64 workstations.
- Added `scripts/image-smoke.sh` to run the image, check `/healthz`, check
  `/readyz`, verify `/deployment/readiness.json`, and verify that the
  public-demo home page renders. The smoke also checks the configured
  `impala-shell` runtime path, `klist`, and the native `sasl` import required
  by metadata-capable deployments.
- Added `scripts/kubernetes-configured-metadata-smoke.sh` for installed
  configured releases. It verifies Kerberos/runtime readiness in the web pod,
  submits one bounded Recent scan with `metadata_top_limit=1`, and requires
  collected or partial metadata with table context without printing raw query,
  case, table, or path values. The smoke marks its service scan as
  non-publishing so it does not replace the latest analyst-visible UI batch
  result.
- Added `scripts/audit_kubernetes_deployment.py` for raw-free static checks
  over raw manifests or Helm-rendered manifests.
- Added `scripts/audit_kubernetes_auth_front_door.py` for raw-free configured
  Kubernetes auth-front-door checks over Ingress, Service, Deployment,
  NetworkPolicy, and optional `/deployment/readiness.json` output.
- Added `scripts/kubernetes_auth_front_door_smoke.py` for raw-free live
  unauthenticated ingress/OIDC redirect checks before release handoff.
- Added `scripts/kubernetes-configured-release-gate.sh` to compose the
  configured metadata smoke, external auth redirect smoke, and raw-free
  auth-front-door audit for installed configured releases.
- Added `scripts/kubernetes-public-demo-smoke.sh` for disposable live-cluster
  public-demo smoke when an operator intentionally points it at a Kubernetes
  context.
- Added `scripts/kubernetes-self-test-smoke.sh` for disposable live-cluster
  Helm self-test smoke when an operator intentionally points it at a Kubernetes
  context.
- Added Container CI to build and smoke the image on pull requests.
- Published GitHub Releases now publish
  `ghcr.io/alexandrefimov/query-doctor:<version>` and `latest`.
- Release docs now require kubeconform over the Kubernetes manifests and image
  smoke before tagging container-enabled releases.

## What Did Not Change

- Apache Impala remains the full production triage engine.
- Cloudera Manager remains the full Recent discovery/profile/metrics/events
  provider for Impala workflows.
- Direct Impala remains bounded to Recent, Running, and one Known Query ID
  through daemon endpoints, without SQL execution.
- Trino remains officially supported only for the bounded local raw-free
  production lanes introduced in 0.10.0: retained-list Recent, one explicit
  Query ID, raw-free materialized Details, deterministic Python Report, and
  optimizer guidance over those materialized web cases.
- Trino still does not support Running scans, query-history crawling, product
  metadata collection, LLM report output, Query Optimizer jobs, generated Trino
  SQL, SQL execution, or broader/shared Trino production triage.
- Spark remains compact support only, not production Spark triage.

## Documentation And Positioning

- README and README.ru now describe the 0.11.0 container/Kubernetes path and the
  bounded local/private one-profile web upload.
- `deploy/kubernetes/README.md` documents the supported raw manifests, probes,
  deployment readiness summary, local image build/smoke commands, credential
  handling, the synthetic self-test Job, and deployment boundaries.
- `docs/kubernetes-auth-front-door.md` documents the configured Kubernetes
  auth-proxy contract, post-Keycloak acceptance checklist, and raw-free
  oauth2-proxy/Keycloak-style audit path.
- `deploy/helm/query-doctor/README.md` documents chart modes, validation, Helm
  NOTES, deployment readiness, the synthetic `helm test` hook, and deployment
  boundaries.
- `docs/README.md`, `docs/release-checklist.md`, `docs/test-matrix.md`, and
  `docs/public-release-readiness.md` now include the container/Kubernetes
  release surface.
- Package metadata now describes Query Doctor as local-first Big Data query
  diagnostics for Apache Impala production triage, bounded local Trino lanes,
  and containerized web deployment.

Suggested repository description:

```text
Local-first Big Data query diagnostics for Apache Impala, bounded local Trino lanes, and Kubernetes-ready web deployment.
```

## Validation

The 0.11.0 release candidate should be validated with:

- focused probe and packaging tests:
  `python3 -m pytest -q tests/test_kubernetes_packaging.py tests/test_deployment_readiness.py tests/test_web_app.py::test_health_probe_routes_are_raw_free_json`;
- Kubernetes conformance:
  `kubeconform -strict -summary deploy/kubernetes/public-demo.yaml deploy/kubernetes/configured-web.yaml deploy/kubernetes/self-test-job.yaml`;
- Helm chart render smoke:
  `scripts/helm-chart-smoke.sh`;
- configured Kubernetes auth-front-door audit:
  `python3 scripts/audit_kubernetes_auth_front_door.py --resources-json <ignored-auth-front-door-resources.json> --namespace <namespace> --query-doctor-service <query-doctor-service> --auth-proxy-service <auth-proxy-service> --expected-host <query-doctor-host> --deployment-readiness-json <ignored-deployment-readiness.json>`;
- retained Recent history operator-readiness gate when configured-environment
  summaries are available, or the equivalent Helm
  `recentHistory.operatorReadiness` render path:
  `query-doctor-recent-history-operator-readiness --postgres-readiness-summary-json <raw-free-postgres-readiness.json> --profile-worker-summary-json <raw-free-profile-worker.json> --collector-summary-json <raw-free-collector.json> --retention-summary-json <raw-free-retention.json> --fail-on-warning`;
- optional disposable cluster-side self-test smoke:
  `scripts/kubernetes-self-test-smoke.sh`;
- container build and smoke:
  `scripts/build-image.sh query-doctor:release-candidate` and
  `scripts/image-smoke.sh query-doctor:release-candidate`;
- standard public release gate: required external private marker fingerprints,
  full test suite, ruff, active-doc checks, Markdown links, public-doc audit,
  release-history shape check, demo pack generation, public-release preflight,
  package build/check, clean-wheel smoke, TestPyPI, GitHub Release, PyPI, and
  production install smoke. Marker-derived hashes and normalized lengths stay
  in private release configuration rather than the public repository.

README screenshots were reviewed for 0.11.0. The new one-profile upload form is
hidden from the public synthetic demo, and the self-test Job is a non-browser
install check, so this release does not change the first-screen public demo
workflow captured by the existing synthetic screenshots.

## Upgrade Notes

- Upgrade the Python package with `pip install --upgrade query-doctor` after
  0.11.0 is published.
- Run `query-doctor-self-test` after upgrading.
- Run `query-doctor-deployment-readiness --json` to inspect the raw-free
  deployment summary before starting a configured web process.
- Use `query-doctor-web --public-demo` or the container image for a read-only
  synthetic demo.
- Use `deploy/kubernetes/public-demo.yaml` for a credential-free Kubernetes
  demo.
- Use `deploy/kubernetes/self-test-job.yaml` or `helm test` for a synthetic
  cluster-side package confidence check.
- Use `deploy/helm/query-doctor` for Helm-based installs.
- Use `deploy/kubernetes/configured-web.yaml` only after replacing placeholder
  config, creating credentials outside git, and putting shared access behind a
  trusted ingress/auth proxy.
