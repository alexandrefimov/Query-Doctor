# Community Starter Issues

This backlog gives maintainers ready-to-open public issues. Each item is scoped
to sanitized examples, synthetic demo data, or docs-only changes. Do not attach
raw production query text, profiles, metadata output, hostnames, usernames,
local paths, credentials, command output, model/runtime internals, or raw
artifact names. Do not use screenshots, logs, generated reports, or browser
captures from real clusters.

Optimizer trust-boundary work, scoring calibration, and broad product routing
belong in maintainer-owned roadmap or audit items unless a maintainer has first
split out a narrow reviewed contributor slice.

## Label Intent

- `good first issue`: tiny contribution-ready task. It should not require
  product, architecture, trust-boundary, or scoring design.
- `help wanted`: contribution-ready task with maintainer-approved scope and
  clear acceptance criteria. A contributor should still comment first when the
  issue asks for a fixture shape, docs structure, or any choice that affects
  safety boundaries.
- `maintainer-owned`: do not open a PR without maintainer discussion or
  approval. Use this for architecture, product routing, optimizer recipes,
  scoring calibration, trust-boundary work, and release positioning.

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
context, or stats-estimate mismatch.

Contributors should comment with the proposed fixture shape before opening a
PR. Maintainers may redirect the scope if the proposed fixture would touch a
trust boundary, require real production data, or overlap a current calibration
task. The fixture must be synthetic or fully anonymized before it enters the
repository.

Acceptance criteria:

- The fixture contains no raw production identifiers or local paths.
- Analyzer assertions prove the intended deterministic facts.
- Browser/trusted-output safety tests still pass.

## Maintainer-Owned Public Issues

These issues may be public, but they are not drive-by contribution tasks.
Contributors should comment with an approach and wait for maintainer agreement
before opening a PR.

### Add A Lightweight Architecture Diagram Update

Labels: `maintainer-owned`, `documentation`, `web-ui`

Update the public architecture diagram when the web/report/optimizer flow
changes. The diagram should show collector, analyzer, validator, report, and UI
boundaries without implying unsupported engines or automatic LLM execution.
Update or consolidate the existing architecture diagrams rather than adding a
second overlapping diagram.

Acceptance criteria:

- The diagram matches implemented behavior.
- Future seams are clearly marked as roadmap, not current support.
- The docs remain English-first, with companion-page drift handled.
- The change does not duplicate an existing architecture diagram.
