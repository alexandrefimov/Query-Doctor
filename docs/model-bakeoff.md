# Model Route Evaluation Protocol

This public document defines the safety protocol for comparing model routes
inside Query Doctor. It intentionally does not publish local bake-off results,
model latency tables, case IDs, private provider setup, or historical
workstation decisions. Keep those details in local exclude-only notes.

Query Doctor's contract does not change during model comparison:

- Python/analyzer owns facts.
- LLM output owns wording only unless deterministic validation accepts a
  Python-owned artifact.
- Trusted SQL drafts require a Python-owned recipe, deterministic execution,
  and strict validation.
- Browser-visible UI and trusted reports must not expose model names, raw SQL,
  raw profiles, raw metadata, local paths, process logs, or raw artifact
  filenames.

Public configuration docs may list current default values where they are part
of the user-facing config contract. This protocol should not become a history
of local model rankings.

## What Belongs Here

Allowed in committed docs:

- route-specific scoring definitions;
- required validation modes and safety gates;
- placeholder command shapes;
- artifact schemas that are already raw-free;
- decision rules for changing defaults.

Keep local:

- specific local model rankings, pass rates, latency, and failure examples;
- real or real-looking case IDs;
- generated `cases/` roots, batch-summary paths, and output directories;
- provider endpoints, gateway names, credentials, and workstation setup;
- raw prompts, raw completions, and untrusted model output.

## Query LLM Optimizer Route

Optimizer evaluation is separate from report-writer evaluation. Report quality
does not prove SQL rewrite quality.

Score trusted outcomes by route:

- `trusted_outcome_rate`: any trusted route result.
- `trusted_sql_draft_rate`: validated SQL draft with deterministic marker.
- `trusted_no_rewrite_rate`: safe no-rewrite outcome.
- `trusted_recommendations_rate`: recommendations-only outcome.
- `partial_untrusted_rate`: model returned a draft that validation rejected.

Use model-comparable summaries only for model-influenced outcomes. Do not let
deterministic recipe or deterministic no-rewrite cases inflate model quality.
The product funnel still matters, but it answers a different question: whether
the whole optimizer route produced a trusted safe outcome.

For recommendations-only cases, compare trusted outcome rate with raw-free
recommendation normalization telemetry. `recommendation candidate match`
measures overlap with Python-owned recommendation candidates.
`recommendation fallback` is safe product behavior, but it is weak evidence for
model quality because normalization replaced unsupported or unmatched text.

Placeholder fixture comparison:

```bash
python3 scripts/compare_optimizer_models.py \
  --models <model-a> <model-b> \
  --fixture-corpus \
  --fixture-expected-output-kind recommendations_only \
  --optimizer-num-predict 4096 \
  --repeat 3 \
  --out-dir <ignored-output-dir>
```

Placeholder local-case comparison:

```bash
python3 scripts/compare_optimizer_models.py \
  --models <model-a> <model-b> \
  --optimizer-num-predict 4096 \
  --cases-root <ignored-cases-root> \
  --cases-file <ignored-case-list> \
  --out-dir <ignored-output-dir>
```

The cases file must stay untracked when it contains real case names or private
case paths.

## Report-Writer Route

Report-writer comparison evaluates trusted diagnostic reports generated from the
deterministic analyzer facts file. It must not use raw profile input as the
report-writer facts source.

Rules:

- Use the deterministic analyzer facts file after analyzer execution.
- Do not use raw profiles or profile digests as the model facts source for
  real-case remote comparison.
- Use strict validation when making default decisions.
- Use multiple runs per case/model pair when making a default decision.
- Count only strict validation pass as trusted-pass quality.
- Use relaxed validation only to diagnose compatibility after strict failure.
- Keep provider credentials, endpoints, transport errors, and model-specific
  tuning in ignored local notes.

Placeholder comparison:

```bash
python3 scripts/compare_ollama_models.py \
  --provider <provider> \
  --models <model-a> <model-b> \
  --facts <deterministic-facts-file> \
  --mode admin \
  --validation-mode strict \
  --cases-root <ignored-cases-root> \
  --cases-file <ignored-case-list> \
  --parallel-workers 1 \
  --repeat 3 \
  --out-dir <ignored-output-dir> \
  tests/fixtures/backend_tail_case \
  tests/fixtures/scan_or_exchange_heavy_case \
  tests/fixtures/missing_estimates_case
```

## Public Artifacts

Comparison scripts should write raw-free summaries suitable for local review,
but generated summaries are still treated as local evidence by default. Before
copying any result into committed docs, verify that it contains no raw SQL, raw
profile text, raw metadata, local paths, case IDs, model-internal output,
credentials, endpoints, or private provider details.

## Default-Change Rule

Do not change a model default from a single run or a prompt-only impression.
Require:

- route-specific comparison;
- strict validation;
- enough repeated cases for the route being changed;
- no increase in untrusted partial output;
- a deterministic explanation of why the new route is safer or more useful;
- updated tests and config documentation for the changed default.

Record the public decision as a short config or changelog note. Keep the full
local bake-off evidence in local exclude-only notes.
