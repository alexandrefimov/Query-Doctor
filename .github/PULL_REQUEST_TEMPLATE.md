## Summary

<!-- Briefly describe the change and why it is needed. -->

## Type

- [ ] Bug fix
- [ ] Feature or workflow change
- [ ] Safety or trust-boundary change
- [ ] Documentation
- [ ] CI, packaging, or release
- [ ] Tests only

## Safety Checklist

- [ ] No raw production SQL, profiles, metadata, local paths, hostnames, secrets, subprocess output, model/runtime internals, or raw artifact filenames are introduced.
- [ ] Browser-visible UI and trusted reports remain sanitized.
- [ ] External collection changes, if any, are explicit, bounded, read-only, and redacted by default.
- [ ] Query Optimizer changes, if any, do not execute user SQL or optimizer draft SQL.
- [ ] LLM-facing changes, if any, keep Python/analyzer facts as the source of truth.
- [ ] Unsupported evidence remains `unknown`, `not_observed`, or explicitly unsupported.
- [ ] No screenshots, logs, generated reports, or browser captures from real clusters are added.

## Validation

- [ ] Focused tests for touched behavior:
- [ ] Broader safety tests, if a trust boundary changed:
- [ ] `pre-commit run --all-files`
- [ ] `git diff --check`
- [ ] Release gate, if release-facing: `PUBLIC_RELEASE=1 scripts/local_gate.sh`

## Documentation

- [ ] Public docs are updated, or this change does not affect documented behavior.
- [ ] `docs/changelog.md` is updated for significant user-facing, collector, analyzer, report, optimizer, or safety changes.
- [ ] New examples, fixtures, screenshots, or logs are synthetic and sanitized.
