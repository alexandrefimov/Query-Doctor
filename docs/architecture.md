# Query Doctor Architecture

Query Doctor keeps fact extraction deterministic and lets the LLM write only from
those facts.

## Pipeline

```text
Cloudera Manager profile / profile_digest.md
  -> query_doctor_collect_cm_profiles.py
  -> ignored local case directory
  -> analyze_profile_digest.py
  -> analysis_facts.md
  -> action cards and deterministic evidence
  -> query_doctor_report.py
  -> sanitizer and fail-closed validator
  -> deterministic analyzer facts appendix
  -> admin/user reports
  -> local demo UI
```

## Components

Collector:
- Performs explicit, bounded, read-only Cloudera Manager profile collection.
- Requires redaction for real collection.
- Preserves analyzer-useful counters and stable safe host aliases.
- Writes generated local cases under ignored corpus paths.
- Does not run the analyzer or report writer by itself.

Analyzer:
- Reads `profile_digest.md`.
- Extracts deterministic facts into `analysis_facts.md`.
- Produces operator summaries, anomaly counts, action cards, and backend/host evidence when parsed.
- Does not call Cloudera Manager, Ollama, or the report writer.

Report writer:
- Reads only `analysis_facts.md`.
- Uses the LLM for narrative wording, not fact discovery.
- Must not infer from raw profile text, SQL, local config, or external context.
- Generates admin and user reports with different audiences but the same fact boundary.
- Requires the LLM narrative sections `## Короткий вывод` and `## Подробный разбор`.
- Appends `## Факты анализатора` deterministically from `analysis_facts.md`; the LLM must not write this appendix.
- Buffers raw LLM output internally. It writes the final report only after normalization, sanitization, narrative validation, appendix append, and final validation.

Sanitizer and validator:
- Normalize a narrow set of unsafe generated wording into explicit safe wording.
- Reject reports that make unsupported claims.
- Stay fail-closed: a rejected report is safer than accepting invented evidence.
- On validation failure, write only sanitized/normalized `.partial` output and preserve any existing final report.

Demo UI:
- Presents the local workflow for one explicit query id.
- Reuses collected cases when safe.
- Is not a source of facts.
- Does not enable broad collection.

## Current Real-Case Coverage

The local ignored corpus currently exercises these important classes:

- `e94fbeb93feb2ad1_edd9d52c00000000`: host/backend data-skew evidence with no proven execution-tail host.
- `fa469f95f6fb7286_ea9f070d00000000`: bad-query case with supported row/cardinality and memory estimate anomalies.

Do not put raw SQL, raw hostnames, raw IP addresses, raw profiles, local config,
or credentials in committed documentation.
