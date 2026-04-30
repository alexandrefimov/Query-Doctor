# Query Doctor Safety Contract

## Fact Boundary

- Python owns facts.
- The LLM owns wording only.
- Every diagnostic claim should map to `supported`, `not_observed`, or `unknown` evidence in `analysis_facts.md`.
- Do not state root cause unless `analysis_facts.md` directly supports that cause.
- Do not infer from raw profile text, SQL, CM JSON, local config, or external knowledge in the report writer.

## Collection Boundary

- No broad cluster/profile/table scanning by default.
- External collection must be explicit, bounded, read-only, redacted, and safe by default.
- Dry-run and preflight paths must not collect profile text.
- Real profile collection must not print raw profiles, SQL, raw CM JSON, or credentials.

## Git Boundary

Generated, sensitive, and local outputs must not be committed:

- `cases/cm-corpus/`
- `cases/cm-corpus-hostalias/`
- `analysis_facts.md`
- generated `report*.md` / `diagnosis*.md`
- `*.partial`
- local CM config
- real CM profile material

Never commit raw hostnames, IPs, users, emails, tokens, cookies, passwords,
Authorization headers, embedded URL credentials, local config contents, or real
production profile text.

## Report Validation

- Validators are fail-closed.
- Do not weaken validators to make reports pass.
- If a report is rejected, tighten deterministic facts, prompt wording, sanitizer behavior, or tests.
- Unsafe-rejected and safe-allowed tests should accompany new validator rules.
- Deterministic normalization must not hide unsupported claims silently.
- Safe replacements must be explicit, narrow, and tested.

## Claim Discipline

Keep these categories separate:

- backend data skew
- execution skew
- cardinality / row-estimate anomaly
- memory estimate anomaly
- write-path anomaly
- diagnostic recommendation
- proven cause

Specific rules:

- Backend data skew means parsed backend rows/records are unevenly distributed. It does not by itself prove stale stats, cardinality underestimation, hot keys, or one slow host.
- Execution skew requires parsed evidence that a backend or host is slower than peers.
- A write-path anomaly may be checked when unknown, but it must not be stated as a proven cause.
- Row/cardinality underestimation requires actual rows greater than estimated rows or ratio above `1`.
- Memory underestimation requires actual/peak memory greater than estimated memory or ratio above `1`.
- Operator/profile counter time is not query wall-clock duration unless `analysis_facts.md` explicitly provides wall-clock evidence.

When in doubt, say the evidence is missing.
