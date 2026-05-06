---
name: Feature request
about: Suggest a bounded Query Doctor capability or workflow improvement
title: "[Feature]: "
labels: enhancement
assignees: ""
---

## Problem

What diagnostic or operator problem should this solve?

## Proposed Behavior

Describe the expected user-facing behavior.

## Scope

Which area would this affect?

- [ ] Collector
- [ ] Analyzer facts
- [ ] Report validation
- [ ] Query Optimizer
- [ ] Web UI
- [ ] Cluster Doctor seam
- [ ] Documentation
- [ ] Packaging or CI

## Safety And Trust Boundary

How should the feature preserve Query Doctor's safety contract?

- [ ] Python/analyzer owns facts.
- [ ] LLM owns wording only.
- [ ] External reads are explicit, bounded, read-only, and redacted.
- [ ] Browser/trusted output does not expose raw SQL, profiles, metadata, paths,
      secrets, command output, model/runtime internals, or raw artifact names.
- [ ] Unsupported or ambiguous evidence remains `unknown` or `not_observed`.

## Alternatives

What simpler workaround or narrower version should be considered?

## Notes

Add links to public docs, sanitized examples, or synthetic cases only.
