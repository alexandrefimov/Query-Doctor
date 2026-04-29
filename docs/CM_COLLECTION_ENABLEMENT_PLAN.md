# CM Collection Enablement Plan

## Current state

- The CM collector CLI supports real collection only for an explicit `--query-id`.
- `--dry-run` is plan-only.
- Broad recent-query collection is still disabled.
- Real collection requires `--redact`.
- Query-id mode is limited to `--limit 1`.
- The max profile size guard defaults to `52428800` bytes.
- The collector writes generated cases only; it does not run the analyzer or report writer automatically.
- HTTP GET transport, CM v32 endpoint adapter helpers, output writer, redaction helpers, and mocked tests already exist.
- Latest known validation status: `219 passed`.
- A real ignored single-query smoke under `cases/cm-corpus/` passed collection, analyzer parsing, admin/user report generation, and deterministic report validation.

## Goal

Enable read-only collection from Cloudera Manager into local generated corpus directories for Query Doctor regression and smoke testing, expanding cautiously from single-query collection to bounded broad collection.

## Non-goals

- No Impala query execution.
- No SQL execution.
- No `COMPUTE STATS`.
- No `REFRESH`.
- No `INVALIDATE METADATA`.
- No `INSERT`, `CREATE`, `DROP`, `ALTER`, `DELETE`, `UPDATE`, or `TRUNCATE`.
- No LLM calls.
- No committing collected production profiles by default.

## Required pre-checks before first real smoke

- Confirm exact CM API endpoints for query summaries and profile text in the target CM version.
- Confirm auth method: basic auth or token.
- Confirm TLS CA handling with `--ca-bundle /path/to/company-ca.pem` or a temporary environment setting.
- Confirm target cluster and service names.
- Confirm the output directory is ignored, for example `cases/cm-corpus/`.
- Confirm `--redact` is enabled for every real collection.
- Confirm `--query-id` is explicit for the current supported path.
- Confirm `--limit 1` is used for query-id mode.
- Confirm `--max-profile-bytes` is set deliberately or left at the safe default.
- Confirm `--since-hours` is bounded.
- Confirm no generated outputs are staged.

## Supported single-query smoke command

Do not put real credentials in docs or commit them to Git. Prefer environment variables from a temporary shell session and avoid pasting secrets into shell history where possible.

```bash
CM_USERNAME=... CM_PASSWORD=... \
python3 query_doctor_collect_cm_profiles.py \
  --cm-url https://cm.example.com:7183 \
  --cluster CLUSTER_NAME \
  --service IMPALA_SERVICE_NAME \
  --query-id QUERY_ID_WITH_COLON \
  --since-hours 1 \
  --limit 1 \
  --min-duration-sec 60 \
  --max-profile-bytes 52428800 \
  --out cases/cm-corpus \
  --redact \
  --ca-bundle /path/to/company-ca.pem
```

## Safe rollout steps

Completed single-query rollout:

1. Verified CM v32 query summary endpoint.
2. Verified CM v32 profile text endpoint with `format=text`.
3. Added bounded non-dry-run collection for explicit `--query-id`.
4. Ran real single-query collection with `--limit 1`, `--redact`, and the profile size guard.
5. Inspected generated files manually.
6. Ran the analyzer on the collected case.
7. Ran admin/user report smoke.
8. Removed generated `analysis_facts.md` and report files after validation.
9. Confirmed `cases/cm-corpus/` remains ignored and uncommitted.

Next bounded broad-collection rollout:

1. Keep `--redact` required.
2. Use a very small `--limit`, for example `2` or `3`.
3. Keep `--since-hours` bounded.
4. Keep `--max-profile-bytes` enabled.
5. Do not auto-run analyzer or reports from the collector.
6. Run analyzer/report smoke manually after collection.
7. Confirm generated corpus files remain ignored and unstaged.

## Required generated-output checks

Run:

```bash
git status --short
git diff --name-status
git diff --stat
```

Check:

- No `cases/cm-corpus` files are staged.
- No credentials are present in files.
- No local config files are staged.
- Raw profile text, SQL, and raw CM JSON are not printed in review notes.
- No production `profile_digest.md` is committed unless sanitized and explicitly reviewed.

## First-smoke quality checks

Generated case should contain:

- `profile_digest.md`
- `cm_metadata.json`
- `collection_warnings.txt`

Check:

- `profile_digest.md` is redacted if `--redact` was used.
- `cm_metadata.json` does not contain passwords, tokens, or auth headers.
- `collection_warnings.txt` does not contain secrets.
- The analyzer can read `profile_digest.md`.
- Action Cards are generated only if evidence exists.

Latest real smoke result:

- Ignored local case: `cases/cm-corpus/494ef9bf2699a3c5_5b65e20400000000`.
- Analyzer parsed `169` operators.
- Cardinality anomalies: `0`.
- Memory anomalies: `2`.
- Action Cards were present.
- Admin and user report generation passed deterministic validation.
- Generated `analysis_facts.md`, `report_admin.md`, and `report_user.md` were removed after inspection.

## Rollback/cleanup

Remove only explicit generated paths after checking them first:

```bash
rm -rf cases/cm-corpus/<specific_case_dir>
```

Never use broad removal commands without confirming the path. Do not delete existing hand-curated cases. Do not delete `profile_digest.md` from committed test fixtures.

## Open questions

- Exact response shape in the installed CM version.
- Whether raw profile or digest is returned.
- Whether query profile text already includes original SQL.
- Whether query IDs should remain preserved in redacted corpus.
- Whether the first corpus should stay local-only or become a sanitized fixture candidate.
- How to select the first bounded broad corpus of representative queries.
- Whether broad collection should require an additional explicit acknowledgement flag.
