# Community Starter Issues

This backlog gives maintainers ready-to-open public issues. Each item is scoped
to sanitized examples, synthetic demo data, or docs-only changes. Do not attach
raw production query text, profiles, metadata output, hostnames, usernames,
local paths, credentials, command output, model/runtime internals, or raw
artifact names.

## Good First Issues

### Split One Focused Web Presenter Test

Labels: `good first issue`, `tests`, `web-ui`, `refactor`

Find one small group of assertions in a large web UI test file and move it into
a focused test module without changing behavior. Prefer presenter-level tests
over server-level tests when no HTTP behavior is involved.

Acceptance criteria:

- The moved test still covers the same public behavior.
- No production fixtures or raw artifacts are added.
- The relevant focused test command passes.

### Add One Synthetic Demo Case Note

Labels: `good first issue`, `documentation`, `analyzer`

Add a short docs note explaining one existing synthetic demo scenario from an
operator perspective: what deterministic evidence appears, what action is
suggested, and what remains unknown.

Acceptance criteria:

- The note uses only synthetic case labels.
- It does not claim a root cause without analyzer-owned evidence.
- It links to the synthetic demo mode docs.

## Help Wanted

### Expand Sanitized Fixture Coverage

Labels: `help wanted`, `tests`, `analyzer`, `safety`

Add a new sanitized fixture that exercises one currently underrepresented
diagnostic shape, such as long writer tail, scan/storage context, exchange wait
context, or stats-estimate mismatch. The fixture must be synthetic or fully
anonymized before it enters the repository.

Acceptance criteria:

- The fixture contains no raw production identifiers or local paths.
- Analyzer assertions prove the intended deterministic facts.
- Browser/trusted-output safety tests still pass.

### Add A Lightweight Architecture Diagram Update

Labels: `help wanted`, `documentation`, `web-ui`

Update the public architecture diagram when the web/report/optimizer flow
changes. The diagram should show collector, analyzer, validator, report, and UI
boundaries without implying unsupported engines or automatic LLM execution.

Acceptance criteria:

- The diagram matches implemented behavior.
- Future seams are clearly marked as roadmap, not current support.
- The docs remain English-first.

### Improve Optimizer Usefulness With Python-Owned Recipes

Labels: `help wanted`, `optimizer`, `analyzer`, `safety`

Design one narrow optimizer recipe where Query Doctor can prove a safe rewrite
shape deterministically. Do not loosen prompt-only rewrite permission. The
validator must prove table set, filters, joins, literals, and output shape are
preserved or intentionally transformed by the recipe.

Acceptance criteria:

- The recipe has focused parser and validator tests.
- Unsafe or ambiguous drafts remain untrusted.
- Browser output does not echo pasted or server-owned query text.
