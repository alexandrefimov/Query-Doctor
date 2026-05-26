# Security Model

Last reviewed: 2026-05-26

This document is the public security and privacy overview for Query Doctor. The
mandatory implementation contract lives in [safety-contract.md](safety-contract.md).

## Trust Boundary

Query Doctor is a local-first diagnostic tool. The core safety rule is:

```text
Python owns facts. LLM owns wording only.
```

Deterministic Python analyzers extract facts from bounded local inputs. LLM
output is treated as untrusted until it passes normalization, sanitization, and
deterministic validation. A rejected report or optimizer draft is a valid safety
outcome.

## Local-First Operation

Query Doctor is designed to run on the operator's machine or controlled
environment. It does not require a hosted backend for current workflows.

External collection paths must be:

- explicit;
- bounded;
- read-only;
- redacted;
- safe by default.

Current external collection support is Impala-only:

- Cloudera Manager can provide full Recent discovery, profile, runtime metrics,
  and event context for Impala workflows.
- Direct Impala daemon endpoints can provide bounded Recent scans, Running
  scans, and one explicit Known Query ID without Cloudera Manager events.
- Direct Impala JSON profile, `/profile_docs`, and `/admission?json` collection
  are optional bounded probes; missing old-cluster endpoints degrade to
  unavailable or unknown rather than forcing unsupported claims.
- Optional Prometheus runtime metrics can provide bounded context for configured
  direct Impala workflows.
- Impala metadata collection uses allowlisted read-only metadata statements.

Future source providers must keep the same safety properties before they become
supported product behavior.

## Data That Must Not Be Exposed

Browser-visible UI and trusted reports must not expose:

- raw SQL or pasted query text after submit;
- raw profile text;
- raw metadata output;
- raw provider JSON, including Cloudera Manager, direct Impala, or Prometheus
  responses;
- local paths or `case_dir`;
- subprocess stdout/stderr;
- credentials, tokens, cookies, Authorization headers, or embedded URL secrets;
- Kerberos ticket contents;
- model names or runtime internals;
- raw generated artifact filenames.

Terminal diagnostics may mention generic failure categories, but they must not
print sensitive raw payloads.

## Report Trust Chain

Trusted reports are written only after this chain succeeds:

1. Analyzer writes a deterministic facts artifact.
2. Report prompt receives analyzer-owned facts only.
3. LLM output is buffered, not streamed directly to browser output.
4. Python normalizes and sanitizes the draft.
5. Validator rejects unsupported claims, raw SQL-like output, raw HTML, runtime
   fingerprints, and unsafe recommendations.
6. Python appends the deterministic analyzer facts appendix.
7. Final validation passes before the trusted report file is written.

If validation fails, Query Doctor preserves the previous trusted report when
one exists and writes only sanitized partial output for local debugging.

## Optimizer Trust Chain

The Query Optimizer and details-page Query LLM optimizer are read-only analysis
tools. They must not execute SQL.

The pasted-query optimizer accepts only a single read-only statement and does
not echo submitted text back to the browser after submit.

The details-page optimizer may use server-owned analyzed case input, including
read-only payloads extracted from supported source statements. A generated SQL
draft becomes trusted only after deterministic validation binds:

- validation mode and marker schema;
- source query hash;
- analyzer facts hash;
- draft or recommendation artifact hash;
- source scope and risk mode.

High-risk, incomplete, no-benefit, or validation-failed outcomes should produce
safe recommendations-only/no-rewrite guidance instead of trusted SQL.

## Metadata And Cluster Context

Impala metadata collection is allowlisted to read-only metadata statements and
bounded table sets. It must not execute user SQL or mutation statements.

Future Cluster Doctor inputs, including metrics and prepared log/event
summaries, must enter reports only as normalized Python-owned facts with status,
scope, coverage, confidence, and limitations. Raw metrics, raw logs, raw event
payloads, raw provider JSON, hostnames, principals, paths, URLs, credentials,
and raw timestamps must stay out of browser-visible and trusted report output.

## Security Reports

Use GitHub's private "Report a vulnerability" flow for exploitable
vulnerabilities or trust-boundary failures. For non-exploitable safety concerns,
open a minimal public issue using the safety concern template without including
secrets, raw production SQL, raw profiles, raw metadata, or private cluster
details.

## Release Hygiene

Before cutting a tag, changing repository visibility, or announcing a public
release, run:

```bash
query-doctor-demo-preflight --public-release
```

This deterministic guard scans both the current tracked tree and git history
for common private-data markers. It does not replace a final human review, and
it does not prove that no secret has ever existed in the repository. A history
blocker means the affected history must be cleaned with a dedicated history
rewrite or replaced by a clean public branch before release or future visibility
changes.
