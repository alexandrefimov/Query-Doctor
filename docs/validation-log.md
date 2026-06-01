# Validation Log

Last updated: 2026-06-01

This public log records only path-free validation baselines that are useful to
contributors and release reviewers. It is not a local run journal. Detailed
agent notes, private smoke setup, raw command output, generated case locations,
model comparison tables, and case-specific evidence belong in local exclude-only notes.

## Public Scope

Keep entries here when they change or confirm a public contract:

- release or public-sharing readiness;
- broad safety, redaction, and trust-boundary gates;
- deterministic demo-pack and package-install validation;
- documentation boundary and public-doc audit baselines;
- path-free compatibility summaries that do not imply unsupported production
  support.

Do not record:

- branch handoff notes or next-session plans;
- local output roots, batch-summary paths, case directories, or query IDs;
- private cluster selectors, endpoints, port-forward commands, namespaces, or
  workstation details;
- raw profiles, raw SQL, raw metadata, raw process logs, or secrets;
- local model bake-off results, latency tables, or provider-specific tuning
  notes.

## 2026-06-01 Public Documentation Boundary

The public documentation baseline separates committed public docs from ignored
local notes:

- `AGENTS.md` and `docs/codex-handoff.md` describe durable agent rules and
  safety-sensitive product context without per-chat continuation state.
- `docs/public-documentation-boundary.md` defines what can be committed and
  what must stay in local exclude-only notes.
- Public runbooks use placeholders for private targets, case aliases, and
  ignored output directories.
- Public validation and model-route docs describe gates and protocols, not raw
  local evidence or model result history.

Validation performed for this baseline:

```bash
python3 scripts/check_active_docs.py
python3 scripts/check_markdown_links.py
python3 scripts/check_staged_public_safety.py
python3 scripts/check_staged_public_safety.py --changed
python3 scripts/audit_public_docs.py
python3 -m pytest -q tests/test_agent_preflight.py tests/test_check_active_docs.py tests/test_check_staged_public_safety.py tests/test_audit_public_docs.py
python3 -m ruff check scripts tests
git diff --check
python3 -m query_doctor.cli.demo_preflight --public-release
```

The public-release preflight completed with no findings and no generated-file
drift.

## Standing Release Gates

Before public sharing, run the focused gate suggested by
`scripts/agent_preflight.py` for touched paths, then the documentation/public
release checks above. Broaden to `scripts/local_gate.sh` for release-candidate
work or safety-sensitive behavior changes.

For local real-cluster, large-batch, or model-route validation, summarize only
the public-safe result here. Keep the full evidence, paths, commands, and
operator notes in local exclude-only notes.
