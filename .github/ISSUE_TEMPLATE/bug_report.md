---
name: Bug report
about: Report incorrect behavior in a local Query Doctor workflow
title: "[Bug]: "
labels: bug
assignees: ""
---

## Summary

Describe the behavior that looks wrong.

## Affected Workflow

Which workflow was affected?

- [ ] Recent scan
- [ ] Running scan
- [ ] Known Query ID
- [ ] Query Optimizer
- [ ] LLM Report
- [ ] Query LLM optimizer
- [ ] Demo mode
- [ ] CLI
- [ ] Documentation

## Expected Behavior

What did you expect to happen?

## Actual Behavior

What happened instead?

## Reproduction

List the smallest local reproduction steps using sanitized or synthetic inputs.

```bash
# commands, with secrets and raw production inputs removed
```

## Environment

- Query Doctor version or commit:
- Python version:
- Operating system:
- Impala version, if relevant:
- Collection mode, if relevant: Cloudera Manager / direct Impala / demo

## Safety Check

Do not include raw production SQL, raw profiles, raw metadata, hostnames,
usernames, local paths, credentials, tokens, Authorization headers, Kerberos
ticket data, subprocess output, raw artifact filenames, or model/runtime
internals.
