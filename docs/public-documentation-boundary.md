# Public Documentation Boundary

Last reviewed: 2026-06-01

This document defines what belongs in committed Query Doctor documentation and
what must stay local. The goal is to keep the public repository useful to
contributors without publishing private workstation state or agent continuation
notes.

## Rule

Committed documentation is public documentation. If a note only helps the next
local agent session, a private workstation, or a private smoke run, keep it
in local exclude-only notes instead of `docs/`, `AGENTS.md`, or root Markdown
files. Configure those notes in `.git/info/exclude` or a personal global Git
exclude, not in the tracked repository ignore file.

The committed agent docs may describe durable safety rules, validation paths,
review expectations, and sanitized runbooks. They must not carry current branch
state, chat-specific instructions, private cluster selectors, local output
paths, generated case locations, or raw validation evidence.

## Public Documents

| Area | Public content allowed | Keep local |
| --- | --- | --- |
| Root docs | Product overview, contribution rules, security policy, durable agent hard rules. | Private handoff notes, branch queues, local hostnames, local config details. |
| `docs/` contracts | Safety, architecture, optimizer, analyzer, engine, config, demo, release, and validation contracts. | Raw profiles, raw metadata, raw SQL, private evidence packages, generated artifact paths. |
| Agent docs | Stable read path, safety constraints, worktree and validation rules, public-safe product baseline. | Per-chat continuation plans, active branch state, local smoke target names, workstation-specific setup. |
| Runbooks | Generic commands with placeholders or synthetic examples. | Real endpoints, real cluster IDs, real query IDs, private output directories. |
| Validation summaries | Path-free aggregate results and tested command lists. | Raw batch-summary paths, case directories, raw command output, private logs. |
| Model evaluation | Route scoring protocol, strict validation requirements, placeholder commands. | Local model rankings, latency/pass-rate tables, provider setup, private prompts/completions. |
| Changelog and release notes | Significant product, safety, workflow, and public baseline changes. | Local agent hygiene, private branch cleanup, per-run scratch details. |

## Local Notes

Use local exclude-only notes for ignored working notes. The path is a
workstation choice and should not be standardized in public docs. Keep it in
`.git/info/exclude` or a personal global Git exclude.

Local notes may mention private cluster selectors, temporary directories, and
per-run setup only when they remain ignored and are not copied into public
handoff text.

## Audit Checks

Use these checks before committing documentation changes:

```bash
python3 scripts/check_staged_public_safety.py
python3 scripts/check_staged_public_safety.py --changed
python3 scripts/audit_public_docs.py
python3 scripts/check_active_docs.py
python3 scripts/check_markdown_links.py
git diff --check
```

`scripts/audit_public_docs.py` scans committed public Markdown for local-only
agent and workstation markers that the general public-safety scanner does not
classify.

## Current Audit

The public/local split is:

- `AGENTS.md` and `docs/codex-handoff.md` are public-safe agent baselines.
- `docs/README.md` is the public documentation index and must list every
  committed current doc.
- Local exclude-only notes are the home for transient agent handoffs and
  private smoke notes.
- Public runbooks may keep generic local workflow examples, but workstation
  selectors and private output paths are excluded.
- Public validation logs may keep path-free gate summaries and commands, but
  not raw local batch-summary paths, case IDs, or private run journals.
- Public model-route docs may keep protocol and decision rules, but not local
  bake-off result tables or provider-specific tuning notes.

When a future documentation change needs local context to be reproducible, add
a public-safe placeholder or aggregate summary to committed docs and keep the
full local evidence in local exclude-only notes.
