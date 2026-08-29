# Query Doctor Helm Chart

Last reviewed: 2026-08-10

This chart is the supported upstream Helm entry point for the Query Doctor web
UI. It complements the raw Kubernetes manifests under `deploy/kubernetes/` and
keeps the same support boundary: Kubernetes support means a containerized web
deployment starting point, not native auth, RBAC, sessions, multi-tenant
isolation, an operator/CRD, arbitrary command running, SQL execution, or
broader engine support.

## Modes

`mode: publicDemo` is the default. It renders:

- Deployment running `query-doctor-web --public-demo`;
- ServiceAccount with `automountServiceAccountToken=false`;
- ClusterIP Service;
- NetworkPolicy with `egress: []`;
- synthetic `helm test` Job running only `query-doctor-self-test`;
- Helm NOTES with port-forward, probe, readiness, and self-test commands;
- non-root pod/container security context, read-only root filesystem, dropped
  capabilities, writable `/tmp`, and `/healthz`/`/readyz` probes.

`mode: configured` renders the private operator shape. It requires:

- `config.create=true` with `config.inlineJson`, or `config.existingConfigMap`;
- `persistence.enabled=true` or `persistence.existingClaim`;
- a trusted ingress/auth proxy for shared access.

Configured mode may reference `credentials.existingSecret`, but the chart never
renders Kubernetes `Secret` objects and never accepts inline credential values.
The configured example intentionally leaves `ingress.enabled=false`: for shared
deployments, expose Query Doctor through a platform-owned auth front door such
as oauth2-proxy/Keycloak/SSO, and route that front door to the chart Service.
Do not publish the configured web Service directly unless authentication and
inbound header stripping are enforced before requests reach Query Doctor.

The chart web pod resource baseline is sized for configured Recent scans:
`requests.cpu=250m`, `requests.memory=512Mi`, `limits.cpu=2`, and
`limits.memory=2Gi`. Keep that as the minimum for configured private installs
and raise it for larger Recent windows, higher parallelism, or retained case
volumes with heavier profiles.

For non-local configured web binds, the web server defaults to a conservative
Recent shape unless overridden in config: profile analysis limit `50`, overall
Recent parallelism `4`, metadata parallelism `2`, and metadata top limit `10`.
If you increase those values, increase resources and rerun the configured
metadata or release gate smoke.

Configured mode can persist finished-query Recent reuse across pod restarts by
matching the web config `recent_batch_root` with
`persistence.recentBatchMountPath`. The packaged configured example uses
the chart's dedicated temp-backed cache mount, mounted from the same case PVC,
so repeated safe redacted Recent scans can reuse prior analyzed cases when the
Query ID and explicit profile reuse contract match. Keep custom roots under a
dedicated Query Doctor temp-backed path; chart validation, web startup, and the
batch CLI all reject unsafe batch roots.

The packaged configured example also enables the default Online history lane by
setting `recent_history_backend=sqlite` and storing the raw-free summary index
under the case PVC. That path is for retained summary rows, profile job state,
analysis-cache metadata, and profile-artifact fingerprints only; it does not
store raw SQL or profile text. The web Query Inbox can render those retained
summaries as a read-only Online History view before Details are materialized.
The example includes bounded retention days so a long-running configured
install does not grow the SQLite store indefinitely. Move to
`recent_history_backend=postgres` for shared/multi-pod installs or
operator-managed retention jobs.

Configured mode can also pass the optional Postgres Recent summary-history DSN
from an existing Secret without putting the DSN in chart values or JSON config:

```yaml
recentHistory:
  postgres:
    enabled: true
    existingSecret: query-doctor-recent-history-postgres
    dsnKey: dsn
    dsnEnvName: QUERY_DOCTOR_RECENT_HISTORY_POSTGRES_DSN
```

The non-secret Query Doctor config must still explicitly set
`recent_history_backend=postgres` and, when using a non-default env name,
`recent_history_postgres_dsn_env`. The chart does not create the Secret and
does not accept an inline DSN. Build or select an image that includes the
optional Postgres driver extra. If chart NetworkPolicy is enabled, add bounded
egress to the CNPG/Postgres service yourself.
After the pod has the Secret-provided DSN env, run
`query-doctor-recent-history-postgres-readiness --json` in that runtime
environment to verify schema initialization. The command reports only raw-free
status/check ids/issue codes and does not print the DSN, host, password, local
paths, Query IDs, or raw payloads. By default, configured chart installs with
`recentHistory.postgres.enabled=true` run the same command as a web pod
initContainer with `--fail-on-warning`, so the pod does not become ready until
the DSN env is present and the history schema initializes. Set
`recentHistory.postgres.readiness.enabled=false` only for an operator-managed
rollout that gates the same check outside the chart.
The same configured image can run `query-doctor-recent-profile-worker` with the
batch/config flags to process source-filtered queued Recent profile jobs. The
worker writes only raw-free cache/artifact metadata to the history backend and
does not run LLM reports, optimizer jobs, metadata SQL collection, or raw
profile storage in the database.
The chart can render a configured-mode scheduled Recent summary collector after
Postgres history is enabled by setting `recentSummaryCollector.enabled=true`:

```yaml
recentSummaryCollector:
  enabled: true
  schedule: "*/10 * * * *"
  progressJsonl: /var/lib/query-doctor/recent-history/collector-progress.jsonl
```

That CronJob runs `query-doctor-batch-recent --discover-only` with
`--metadata-mode off`, `--top-reports 0`, and
`--recent-history-backend postgres`. It reads the same config, credential
Secret, Kerberos cache settings, and Postgres DSN Secret as the web pod, then
writes only raw-free retained summary rows and planned profile jobs to the
history backend plus a raw-free collector run summary and progress JSONL stream
to the case PVC. `recentSummaryCollector.summaryJson` and
`recentSummaryCollector.progressJsonl` must both stay under the persistence
mount and must point at different files. Point the web config
`recent_history_collector_summary_json` at the retained summary to show the
allowlisted producer status, age, recorded-row, and planned-job counters in
Query Inbox. The CronJob does not collect profiles, run metadata SQL, run LLM
reports, run optimizer jobs, or write operator-readiness summaries.
The chart can render the profile worker as a separate configured-mode CronJob
after Postgres history is enabled by setting `recentProfileWorker.enabled=true`:

```yaml
recentProfileWorker:
  enabled: true
  schedule: "*/5 * * * *"
  maxJobs: 1
```

The CronJob reads the same config, credential Secret, Kerberos cache settings,
case PVC, and Postgres DSN Secret as the web pod, writes temporary worker cases
under `/tmp/query-doctor-profile-worker`, and runs with `--metadata-mode off`,
`--top-reports 0`, and raw-free JSON output. It stays behind the same
NetworkPolicy egress mode as the web pod. Configure bounded egress to
Postgres/CNPG and the accepted Impala source endpoints before enabling it.
Profile-artifact metadata is `fingerprint_only`; storage kinds that would
retain profile bytes, local paths, object names, or external artifact
references are rejected until a bounded delete implementation exists.
For operator handoff evidence, the chart can retain and aggregate the raw-free
readiness summaries on the case PVC:

```yaml
recentHistory:
  operatorReadiness:
    enabled: true
```

This requires configured mode, `recentHistory.postgres.enabled=true`,
`recentHistory.postgres.readiness.enabled=true`, and
`recentProfileWorker.enabled=true`. Set
`recentHistory.operatorReadiness.enabled=true` to render the audit CronJob.
When enabled, the optional scheduled Recent summary collector writes retained
summary rows, planned profile jobs, and its producer summary, the web pod
Postgres readiness initContainer writes the Postgres readiness summary, the
profile worker CronJob writes the profile-worker summary, the optional
collector producer summary is included when
`recentHistory.operatorReadiness.collectorSummaryJson` is set, the optional
retention CronJob writes a retention summary when `retentionSummaryJson` is
set, and the optional
profile-remediation CronJob can write a dry-run-only summary when
`profileRemediationSummaryJson` is set. The separate
`query-doctor-recent-history-operator-readiness` CronJob then reads only those
retained raw-free JSON summaries and writes one path-free
`query_doctor_recent_history_operator_readiness_v1` handoff summary. Point the
web config `recent_history_operator_readiness_summary_json` at that output path
to show the allowlisted readiness, collector producer, retention, and
profile-remediation projection in Query Inbox. See
`examples/configured-postgres-operator-readiness-values.yaml` for the complete
configured Postgres, worker, retention, and operator-readiness wiring.

The operator-readiness CronJob mounts only the case PVC. It does not mount Query
Doctor config, collection credentials, the Postgres DSN Secret, Kerberos
material, or source endpoint configuration. It does not contact Postgres, Kubernetes.
It also does not contact query engines or profile collectors. With
`--fail-on-warning`, missing, wrong-kind, or unsafe retained summaries still
write a safe blocked summary when possible, then fail the job without printing
input paths or raw JSON.

The chart can also render a Postgres-only dry-run remediation summary producer:

```yaml
recentHistory:
  postgres:
    profileRemediation:
      enabled: true
      schedule: "*/15 * * * *"
      maxJobs: 50
```

This CronJob runs `query-doctor-recent-profile-remediation --json
--fail-on-warning --dry-run --backend postgres` with only the DSN Secret
environment variable and the case PVC mounted. It writes the raw-free summary
to `recentHistory.operatorReadiness.profileRemediationSummaryJson` for the
operator-readiness audit. It does not mount Query Doctor config, collection
credentials, Kerberos material, or source endpoint configuration, and the chart
does not render an apply/requeue remediation job.
The chart can also render a Postgres-only retention CronJob that runs no
discovery or profile collection:

```yaml
recentHistory:
  postgres:
    retention:
      enabled: true
      schedule: "0 3 * * *"
      summaryRetentionDays: 30
      profileJobRetentionDays: 14
      analysisCacheRetentionDays: 45
      profileArtifactRetentionDays: 60
```

That CronJob runs `query-doctor-recent-history-retention --json
--fail-on-warning --backend postgres` with only the DSN Secret environment
variable mounted. It does not mount Query Doctor config, collection
credentials, Kerberos material, or case PVCs, and it does not contact query
engines, discover queries, collect profiles, run metadata SQL, run LLM reports,
run optimizer jobs, or delete external artifact objects.

If the CloudNativePG operator and CRDs are already installed, the chart can
optionally render a configured-mode `Cluster` for the same Recent history
backend:

```yaml
recentHistory:
  postgres:
    enabled: true
    existingSecret: query-doctor-history-app
    dsnKey: uri
    cnpg:
      enabled: true
      name: query-doctor-history
      instances: 1
      database: query_doctor
      owner: query_doctor
      storage:
        size: 20Gi
```

When `cnpg.existingOwnerSecret` is empty, the CNPG controller creates its
standard operator-generated application Secret named `<cluster-name>-app`.
That Secret includes a `uri` key, so Query Doctor can consume it directly by
setting `postgres.existingSecret` to that name and `postgres.dsnKey=uri`. The
web pod may wait for CNPG to create the Secret and make Postgres ready; the
existing readiness initContainer keeps the web process from starting early.

For externally managed database credentials, set `cnpg.existingOwnerSecret`
to a `kubernetes.io/basic-auth` bootstrap Secret and keep using a separate
Query Doctor DSN Secret. The chart does not install the CNPG operator, render
Secret objects, or accept inline usernames, passwords, or DSNs.

The upstream image includes Kerberos client tools and the HiveServer2 metadata
driver. To enable metadata refresh in configured mode, provide explicit metadata
coordinator settings on the coordinator's HiveServer2 port and a valid Kerberos
ticket cache through the private deployment environment; do not put keytabs or
ticket contents in chart values.

For deployments that need the chart to prepare the metadata Kerberos cache,
enable the optional Secret-reference flow:

```yaml
kerberos:
  enabled: true
  existingSecret: query-doctor-kerberos
  principalKey: principal
  keytabKey: query-doctor.keytab
  krb5ConfKey: krb5.conf
  renewer:
    enabled: true
    refreshIntervalSeconds: 1800
```

That renders a `kerberos-kinit` initContainer using the same image. The
initContainer reads the principal/keytab from the referenced Secret, writes a
ticket cache under `/tmp/query-doctor-krb5/`, and the long-lived web pod also
runs a `kerberos-ticket-renewer` sidecar by default. The sidecar reacquires the
ticket from the same keytab at the bounded interval and updates the shared
cache. It suppresses raw Kerberos command output and emits only a generic
success or failure line. The web container receives only `KRB5CCNAME`, the
shared cache volume, and `krb5.conf` when `krb5ConfKey` is set; it never mounts
the principal or keytab. Set `kerberos.renewer.enabled=false` only when an
external process owns refresh of the same cache.

The scheduled summary collector and profile worker remain finite CronJobs.
Each Job uses its existing `kerberos-kinit` initContainer to obtain a fresh
ticket for that run; the long-lived renewer sidecar is intentionally not added
to Jobs because it would prevent them from completing.

## Local Validation

```bash
helm lint deploy/helm/query-doctor
helm template query-doctor deploy/helm/query-doctor --namespace query-doctor
helm template query-doctor deploy/helm/query-doctor \
  --namespace query-doctor \
  -f deploy/helm/query-doctor/examples/configured-values.yaml
```

Run the project wrapper to render both modes, configured maintenance shapes,
and the synthetic self-test hook, audit the rendered manifests, and run
kubeconform when it is available:

```bash
scripts/helm-chart-smoke.sh
```

After installing the chart, `helm test` can run the synthetic package
confidence check inside the cluster:

```bash
helm test query-doctor --namespace query-doctor
kubectl -n query-doctor logs job/query-doctor-self-test
```

The web process also exposes a raw-free deployment summary:

```bash
kubectl -n query-doctor port-forward svc/query-doctor 8765:80
curl -fsS http://127.0.0.1:8765/deployment/readiness.json
```

For an installed configured release with metadata enabled, run the bounded
metadata smoke against the live Service:

```bash
QUERY_DOCTOR_K8S_METADATA_SMOKE_NAMESPACE=query-doctor \
QUERY_DOCTOR_K8S_METADATA_SMOKE_RELEASE=query-doctor-full \
scripts/kubernetes-configured-metadata-smoke.sh
```

The smoke verifies the web pod's Kerberos cache, `klist`, and the importable
impyla and kerberos modules, then submits a one-case Recent scan
with `metadata_top_limit=1`. It requires collected or partial metadata with
table context, and output is limited to aggregate job, metadata status, and
table-context counters. The service scan is not published as the latest UI
batch result.

Before releasing a chart change that affects Kerberos refresh, use a staging
release with `kerberos.renewer.refreshIntervalSeconds=60`, then run the bounded
cache-refresh smoke:

```bash
QUERY_DOCTOR_K8S_KERBEROS_SMOKE_NAMESPACE=<namespace> \
QUERY_DOCTOR_K8S_KERBEROS_SMOKE_RELEASE=<release> \
scripts/kubernetes-kerberos-renewer-smoke.sh
```

The smoke requires a valid cache before and after one refresh interval and
compares only the cache file modification time. It does not print principal,
ticket, keytab, cache path, KDC, or `klist` output. Restore the production
refresh interval after the staging check.

After installing a candidate with Postgres history, the summary collector,
profile worker, and operator-readiness CronJobs enabled but temporarily
`suspend: true`, run one explicit Online History staging cycle:

```bash
QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_NAMESPACE=<namespace> \
QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_RELEASE=<release> \
QUERY_DOCTOR_K8S_ONLINE_HISTORY_SMOKE_EXPECTED_IMAGE=<candidate-image> \
scripts/kubernetes-online-history-smoke.sh
```

This smoke creates one temporary Job from each installed CronJob, waits for
them in collector/worker/readiness order, verifies that all use the candidate
web image, and checks the raw-free Online History UI through a local
port-forward. It does not print Job logs or retained page contents and removes
only the temporary Jobs it created. Run it only against an intentional staging
or otherwise approved configured environment because the collector and worker
perform their normal bounded external reads. Unsuspend the schedules only after
the isolated cycle passes.

The same summary is available before server start through:

```bash
query-doctor-deployment-readiness --config ./query-doctor-web.json --json
```

The test hook is not an arbitrary command runner. It does not mount live
configuration, credentials, runtime bundles, or case storage, and it never runs
Recent scans, optimizer jobs, metadata collection, engine probes, or SQL.

When an intentional disposable Kubernetes context and a pullable pre-release
image are available, run the public-demo live smoke without changing chart
defaults:

```bash
QUERY_DOCTOR_K8S_SMOKE_IMAGE_REPOSITORY=registry.example.com/query-doctor \
QUERY_DOCTOR_K8S_SMOKE_IMAGE_TAG=0.11.0-rc \
scripts/kubernetes-public-demo-smoke.sh
```

For a narrower chart self-test smoke without port-forwarding the web Service:

```bash
QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_REPOSITORY=registry.example.com/query-doctor \
QUERY_DOCTOR_K8S_SELF_TEST_IMAGE_TAG=0.11.0-rc \
scripts/kubernetes-self-test-smoke.sh
```

## Boundaries

- The upstream chart is platform-neutral. Use generic `podLabels` and
  `podAnnotations` for local integration; controller-specific labels, rollout
  metadata, and runtime-bundle wiring belong in downstream overlays. Both maps
  accept string values only. `podLabels` must not override the selector-owned
  `app.kubernetes.io/name`, `app.kubernetes.io/instance`, or
  `app.kubernetes.io/component` keys.
- Public demo mode must not reference credentials or config.
- Configured mode must persist cases on a PVC or existing claim.
- `recentHistory.postgres.enabled` only references an existing Secret key and
  requires configured mode; the DSN value must not appear in chart values or
  Query Doctor JSON config.
- `recentHistory.postgres.cnpg.enabled` renders only a CloudNativePG `Cluster`;
  it does not install the CNPG CRDs/operator or render Secret objects. Query
  Doctor may reference the application Secret generated by CNPG, or an
  operator-managed DSN Secret when external owner credentials are used.
- Shared/non-local configured mode must run behind a trusted ingress/auth
  proxy; Query Doctor does not implement native OIDC, SAML, SPNEGO, Kerberos,
  LDAP, password, MFA, sessions, groups, RBAC, or token auth.
- `source_visibility=owner_raw` remains behind the owner-raw D3 gates.
- Query Doctor never executes user SQL or optimizer draft SQL.
- The self-test Job may run only the fixed synthetic `query-doctor-self-test`
  command and must not be repurposed for live diagnostics or platform smoke
  jobs.
