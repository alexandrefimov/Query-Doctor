# Query Doctor Safety Contract

Last reviewed: 2026-05-08

Language: English | [Russian](i18n/ru/safety-contract.md)

This file contains mandatory safety rules. Exact phrases such as `Do not weaken
validators` are intentionally kept precise because they define review and
implementation boundaries.

## Fact Boundary

- Python owns facts.
- The LLM owns wording only.
- Every diagnostic claim must map to `supported`, `not_observed`, or `unknown`
  evidence in `analysis_facts.md`.
- Do not state root cause unless `analysis_facts.md` directly supports that
  cause.
- The report writer must not infer facts from raw profile text, SQL, Cloudera
  Manager JSON, local config, or external knowledge.

## Collection Boundary

- Broad cluster, profile, or table scanning is disabled by default.
- External collection must be explicit, bounded, read-only, redacted, and safe
  by default.
- Dry-run and preflight paths must not collect profile text.
- Real profile collection must not print raw profiles, SQL, raw Cloudera
  Manager (CM) JSON, or credentials.
- The first supported real Impala metadata connection path is Kerberos plus
  `impala-shell` with an already available TGT from `kinit`.
- The metadata collector does not call `kinit`, does not prompt for passwords,
  does not accept AD/LDAP passwords, and does not use impyla or a Python DB API.
- The metadata collector accepts only explicit table names and read-only
  statements: `SHOW CREATE TABLE`, `SHOW TABLE STATS`, and
  `SHOW COLUMN STATS`.
- Raw `impala-shell` stdout/stderr must not be printed to the terminal.
  Collected output is bounded, redacted, and written only under explicit
  `--out`.
- Generated `impala_context.md` and `impala_context.json` are local outputs and
  must not be committed.

## Git Boundary

Generated, sensitive, or local outputs must not be committed:

- `cases/cm-corpus/`
- `cases/cm-corpus-hostalias/`
- `analysis_facts.md`
- generated `report*.md` / `diagnosis*.md`
- `*.partial`
- local Cloudera Manager (CM) config
- real CM profile material
- `query_metadata.json`
- `impala_context.md` / `impala_context.json`

Never commit raw hostnames, IP addresses, users, emails, tokens, cookies,
passwords, Authorization headers, embedded URL credentials, local config
contents, or real production profile text.

## Report Validation

- Validators are fail-closed.
- Do not weaken validators to make reports pass.
- If a report is rejected, improve deterministic facts, prompt wording,
  sanitizer behavior, or tests.
- New validator rules must include unsafe-rejected and safe-allowed tests.
- Deterministic normalization must not silently hide unsupported claims.
- Safe replacements must be explicit, narrow, and tested.
- Raw LLM output is buffered and must not stream to stdout/stderr or
  user-facing UI.
- Final report files are written only after normalization, sanitization,
  validation, deterministic appendix append, and final validation.
- Validation failure writes only a sanitized/normalized `.partial` and preserves
  the existing final report.
- Trusted final reports must not contain raw SQL-like text, SQL fenced code
  blocks, pasted query fragments, or raw metadata command snippets such as
  table-specific `SHOW CREATE TABLE`, `SHOW TABLE STATS`, or
  `SHOW COLUMN STATS`.
- Partial or invalid report output is untrusted and must not be displayed as
  the final diagnosis.

## Browser Display Boundary

- Browser-visible UI must not render raw SQL, raw profiles, raw metadata,
  stdout/stderr, local paths, `case_dir`, credentials, secret values, Kerberos
  ticket contents, metadata connection details, model names, or Ollama
  internals.
- Dynamic browser-visible text should use the shared browser display redaction
  policy before rendering.
- Web Recent scan must not auto-run LLM reports or optimizer jobs. Validated
  report and Query LLM optimizer generation are explicit for one selected case.
- Details-page Query LLM optimizer must render only a validated read-only draft,
  safe recommendations/no-rewrite guidance, validation-failure-only external
  rewrite validation categories, and safe status fields. Partial drafts, raw
  source SQL, and externally pasted SQL stay hidden.

## Future Cluster Doctor

- Cluster Doctor is a future explicit user-run cluster/service/workload
  diagnostic seam, not current product support.
- Query Doctor may consume future Cluster Doctor output only as normalized
  Python-owned facts with status, scope, coverage, confidence, limitations, and
  deterministic correlation.
- Cluster Doctor must stay read-only: it may recommend checks or operational
  follow-up, but must not execute service control, configuration changes, data
  changes, or remediation automation.
- Future providers such as Cloudera Manager, Prometheus, prepared metric stores,
  or log/event stores must be explicit, bounded, read-only, allowlisted,
  redacted, and tested before their facts enter reports or browser UI.
- Future log/event support must consume prepared event summaries only. Raw log
  lines, stack traces, raw alert text, principals, usernames, query text, and
  raw parser payloads must not enter browser-visible UI, trusted reports, or LLM
  prompts.
- The CM Events MVP CLI is read-only and bounded. It may print normalized event
  counts, severities, and signal ids, but must not print raw CM event payloads,
  raw log lines, event ids, hostnames, principals, paths, query text, or raw
  provider JSON.
- `cluster_event_context.json` is a schema-versioned internal Cluster Doctor
  seam artifact built only from normalized CM event summaries. It must whitelist
  exported fields and omit raw provider payloads, raw log lines, event ids,
  hostnames, principals, paths, query text, URLs, local paths, secrets, command
  output, model/runtime names, and raw artifact filenames.
- `cluster_context.json` is a schema-versioned aggregate Cluster Doctor seam
  artifact built only from safe context artifacts. It may include source status,
  product status, normalized signal counts, limitations, and next checks, but
  it must not include raw provider payloads or browser-forbidden details.
- Raw metric series, raw logs, raw provider JSON, raw alert text, raw
  timestamps, hostnames, entity IDs, URLs, paths, credentials, artifact names,
  command-stream details, model names, and runtime internals must not be
  rendered in trusted reports or browser-visible UI.
- Cluster-wide root-cause or incident claims require their own deterministic
  claim registry, fixtures, report validation, and browser safety tests.

## Report Structure

The LLM writes localized user-facing narrative sections for summary, practical
recommendations, detailed findings, and follow-up checks.

Python appends a localized analyzer facts appendix.

The analyzer facts appendix is built deterministically from `analysis_facts.md`.
The LLM must not write or reinterpret that section.

`## Table Metadata Context` is currently excluded from the LLM prompt and
appears only in the Python-generated appendix.

## Query LLM Optimizer

- Pasted-SQL Query Optimizer accepts only one safe SELECT/WITH statement and
  must not execute or echo pasted SQL after submit.
- Details-page Query LLM optimizer may use only server-owned analyzed case
  sources.
- Details-page external rewrite validation is shown only after an LLM optimizer
  validation failure and accepts pasted SQL only for bounded in-memory
  validation against the server-owned source. It must not execute the pasted
  SQL, persist it as a raw artifact, or echo it back into browser output.
- Supported details-page source scopes are read-only SELECT/WITH and SELECT/WITH
  payloads extracted from supported INSERT/CTAS statements.
- Generated optimizer SQL output must still be a read-only SELECT/WITH
  statement. If no useful rewrite is validated, the trusted optimizer output may
  be a safe recommendations-only/no-rewrite outcome instead of SQL.
- Python validation owns trust: physical tables, filters, projection, DISTINCT,
  top-level GROUP/ORDER/set operations, CTE shape, and top-level JOIN shape must
  remain within validated scope.
- Prompt constraints are not enough for safety. High-risk cases should fall back
  to safe recommendations instead of accepting an unsafe SQL draft, and
  no-benefit drafts should not be presented as optimized SQL.

## Claim Discipline

Keep these categories separate:

- backend data skew
- execution skew
- cardinality / row-estimate anomaly
- memory estimate anomaly
- write-path anomaly
- diagnostic recommendation
- proven cause

Rules:

- Backend data skew means parsed backend rows/records are unevenly distributed.
  It does not prove stale stats, cardinality underestimation, hot keys, or one
  slow host by itself.
- Execution skew requires parsed evidence that a backend or host is slower than
  peers.
- Write-path anomaly can be checked when it is `unknown`, but must not be stated
  as a proven cause.
- Row/cardinality underestimation requires actual rows greater than estimated
  rows or a ratio above `1`.
- Memory underestimation requires actual/peak memory greater than estimated
  memory or a ratio above `1`.
- Operator/profile counter time is not query wall-clock duration unless
  `analysis_facts.md` explicitly contains wall-clock evidence.

When in doubt, say evidence is missing.
