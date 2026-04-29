# CM Collection Enablement Plan

## Current state

- The CM collector CLI exists, but collection is still disabled.
- `--dry-run` is plan-only.
- Non-dry-run exits with `CM API collection is not implemented yet`.
- HTTP GET transport, endpoint adapter helpers, output writer, redaction helpers, and mocked tests already exist.
- Latest known validation status: `117 passed`.

## Goal

Enable read-only collection from Cloudera Manager into local generated corpus directories for Query Doctor regression and smoke testing.

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

- Confirm exact CM API endpoints for query summaries and profile text.
- Confirm auth method: basic auth or token.
- Confirm TLS CA handling, such as `REQUESTS_CA_BUNDLE` or the urllib equivalent.
- Confirm target cluster and service names.
- Confirm the output directory is ignored, for example `cases/cm-corpus/`.
- Confirm `--redact` is enabled for the first smoke.
- Confirm `--limit` is very small, for example `1`.
- Confirm `--since-hours` is bounded.
- Confirm no generated outputs are staged.

## Proposed first real smoke command

Do not put real credentials in docs or commit them to Git. Prefer environment variables from a temporary shell session and avoid pasting secrets into shell history where possible.

```bash
CM_USERNAME=... CM_PASSWORD=... \
python3 query_doctor_collect_cm_profiles.py \
  --cm-url https://cm.example.com:7183 \
  --cluster CLUSTER_NAME \
  --service IMPALA_SERVICE_NAME \
  --since-hours 1 \
  --limit 1 \
  --min-duration-sec 60 \
  --out cases/cm-corpus \
  --redact
```

## Safe rollout steps

1. Wire the query summary endpoint with mocked tests only.
2. Wire the profile text endpoint with mocked tests only.
3. Add non-dry-run collection behind the existing CLI, still requiring bounded `--limit`.
4. Run dry-run and inspect the sanitized plan.
5. Run the first real smoke with `--limit 1` and `--redact`.
6. Inspect generated files manually.
7. Run the analyzer on the collected case.
8. Remove the generated corpus or keep it ignored locally.
9. Confirm `git status` does not include generated outputs.

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

## Rollback/cleanup

Remove only explicit generated paths after checking them first:

```bash
rm -rf cases/cm-corpus/<specific_case_dir>
```

Never use broad removal commands without confirming the path. Do not delete existing hand-curated cases. Do not delete `profile_digest.md` from committed test fixtures.

## Open questions

- Exact CM endpoints.
- Exact response shape in the installed CM version.
- Whether raw profile or digest is returned.
- Whether query profile text already includes original SQL.
- Whether query IDs should remain preserved in redacted corpus.
- Whether the first corpus should stay local-only or become a sanitized fixture candidate.
