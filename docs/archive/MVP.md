# Historical MVP Notes

This file is an archive note for the original Query Doctor MVP planning thread.
It is not the current workflow guide and should not be used as an operational
checklist.

For the current public baseline, use:

- [../../README.md](../../README.md): product overview, install, current workflows,
  safety model and public status.
- [../README.md](../README.md): documentation map.
- [../architecture.md](../architecture.md): current component boundaries.
- [../safety-contract.md](../safety-contract.md): trust, validation and redaction
  rules.
- [../roadmap.md](../roadmap.md): implemented scope, near-term work and future seams.
- [../local-smoke.md](../local-smoke.md): local validation workflows.
- [../DEMO.md](../DEMO.md): current local UI demo notes.

## Archived Intent

The original MVP goal was a local-first Apache Impala diagnostic workflow:

```text
profile_digest.md
  -> deterministic analyzer facts
  -> validated report with Python-owned facts appendix
```

That principle remains current:

```text
Python owns facts. LLM owns wording only.
```

The implemented product has moved beyond the original MVP plan. Current
workflows include Finished Queries, Running Queries, Specific Query, details-page
LLM Report, details-page Query LLM optimizer, pasted-SQL Query Optimizer,
bounded metadata collection, CM metrics context, CM Events context artifacts and
synthetic demo data generation.

## Public Cleanup Note

The long historical checklist that previously lived here duplicated active
documentation and mixed older Russian operational notes with current behavior.
It was intentionally replaced before public release to reduce documentation
drift. Current behavior should be checked against the active baseline documents
linked above.
