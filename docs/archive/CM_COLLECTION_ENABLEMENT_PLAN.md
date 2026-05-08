# Cloudera Manager Collection Enablement Plan

Language: English | [Russian](i18n/ru/CM_COLLECTION_ENABLEMENT_PLAN.md)

This document is a rollout checklist for the read-only Cloudera Manager profile
collector. It covers local generated corpus inputs for regression and smoke
testing, not production runtime behavior.

Archived status: this note preserves the original single-query Cloudera Manager
collector rollout. For current operator workflows, use
[credentials.md](../credentials.md), [local-smoke.md](../local-smoke.md),
[DEMO.md](../DEMO.md), and [roadmap.md](../roadmap.md). Do not treat the
historical rollout sequence below as the current Recent scan or web workflow.

## Current State

- The Cloudera Manager (CM) collector CLI supports real profile collection only
  for an explicit `--query-id`.
- `--dry-run` builds a plan only.
- Broad recent-query collection is not a standalone collector mode.
- Real collection requires `--redact`.
- Query-id mode is limited to `--limit 1`.
- The default max profile size guard is `52428800` bytes.
- The collector writes generated cases only; it does not automatically run the
  analyzer or report writer.
- HTTP GET transport, CM v32 endpoint adapter helpers, output writer, redaction
  helpers and mocked tests exist.
- Run the full pytest suite before every rollout checkpoint and record the
  current result in task or audit output.
- The historical first single-query smoke under `cases/cm-corpus/` completed
  collection, analyzer parsing and deterministic report validation.

## Goal

Enable read-only collection from Cloudera Manager into local generated corpus
directories for Query Doctor regression and smoke testing, expanding carefully
from single-query collection to bounded batch/web Recent scan workflows.

## Non-Goals

- No Impala query execution.
- No SQL execution.
- No `COMPUTE STATS`.
- No `REFRESH`.
- No `INVALIDATE METADATA`.
- No `INSERT`, `CREATE`, `DROP`, `ALTER`, `DELETE`, `UPDATE` or `TRUNCATE`.
- No LLM calls.
- No default commit path for collected production profiles.

## Required Pre-Checks

Before first real smoke:

- Confirm the exact CM API endpoints for query summaries and profile text in the
  target CM version.
- Confirm the auth method: basic auth or token.
- Confirm TLS CA handling through `--ca-bundle /path/to/company-ca.pem` or a
  temporary environment setting.
- Confirm target cluster and service names.
- Confirm the output directory is ignored, for example `cases/cm-corpus/`.
- Confirm `--redact` for every real collection.
- Confirm explicit `--query-id` for the current supported path.
- Confirm `--limit 1` for query-id mode.
- Confirm the intended `--max-profile-bytes` value or the safe default.
- Confirm bounded `--since-hours`.
- Confirm generated outputs are not staged.

## Supported Single-Query Smoke

Do not put real credentials in docs or commit them to Git. Prefer environment
variables from a temporary shell session and do not paste secrets into shell
history.

Prefer the packaged console script:

```bash
CM_USERNAME=... CM_PASSWORD=... \
query-doctor-collect-cm-profiles \
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

Root-level compatibility launchers have been removed. Use `query-doctor-*`
console scripts, or `python -m query_doctor.cli.collect_cm_profiles` when
running directly from a checkout without installed entry points.

## Safe Rollout Steps

Completed single-query rollout:

1. Confirmed the CM v32 query summary endpoint.
2. Confirmed the CM v32 profile text endpoint with `format=text`.
3. Added bounded non-dry-run collection for explicit `--query-id`.
4. Ran real single-query collection with `--limit 1`, `--redact` and the profile
   size guard.
5. Reviewed generated files manually.
6. Ran the analyzer on the collected case.
7. Ran report validation smoke.
8. Removed generated `analysis_facts.md` and report files after validation.
9. Confirmed `cases/cm-corpus/` remained ignored and uncommitted.

Archived historical rollout notes, not current guidance:

These notes predate the current Recent scan batch/web workflow. Do not treat
them as rollout instructions for broad collection. Current supported paths are:

1. standalone collector listing mode for sanitized recent-query candidates, with
   no profile collection and no case output;
2. explicit `--query-id --limit 1 --redact` collection;
3. bounded Recent scan batch/web workflows that collect selected profiles and do
   not auto-run web LLM reports.

## Generated Output Checks

Run:

```bash
git status --short
git diff --name-status
git diff --stat
```

Check:

- No staged files from `cases/cm-corpus`.
- No credentials in files.
- No staged local config files.
- Raw profile text, SQL and raw CM JSON are not printed in review notes.
- Production `profile_digest.md` is not committed unless it is sanitized and
  explicitly reviewed.

## First-Smoke Quality Checks

The generated case should contain:

- `profile_digest.md`;
- `cm_metadata.json`;
- `collection_warnings.txt`.

Check:

- `profile_digest.md` is redacted when `--redact` was used.
- `cm_metadata.json` does not contain passwords, tokens or auth headers.
- `collection_warnings.txt` does not contain secrets.
- Analyzer reads `profile_digest.md`.
- Action Cards appear only when evidence exists.

The original first-smoke counts and local case identifier were intentionally
removed from this public archive because they are not evergreen and are not
needed for current agent or operator work. For current smoke status, run local
validation commands and record the current result in task or audit output.

## Rollback And Cleanup

Remove only explicit generated paths after review:

```bash
rm -rf cases/cm-corpus/<specific_case_dir>
```

Never use broad removal commands without confirming the path. Do not delete
existing hand-curated cases. Do not delete `profile_digest.md` from committed
test fixtures.

## Remaining Useful Questions

- How to grow sanitized fixtures without committing raw production profiles,
  raw SQL, raw Cloudera Manager payloads, hostnames, paths or secrets.
- How to choose representative generated cases for analyzer and optimizer
  regression work while keeping generated corpus output ignored by Git.
- Which future source-provider seams need separate contracts before expanding
  beyond the current Cloudera Manager based Impala collection path.
