# Customer Readiness Priorities

Last reviewed: 2026-06-09

This note records the near-term product-readiness backlog for making Query
Doctor easier to show to design partners and potential customers. It is public
planning material, not a private handoff or a support promise.

## Decision

Impala customer readiness comes before broadening Trino or Spark product
surfaces.

Trino and Spark work remains useful for bounded raw-free contracts, fixture
shape, and future engine seams. It should not distract from the current
customer path: Apache Impala Recent scans, Details, safe recommendations,
configuration, demo flow, and a UI that an operator can understand without
knowing the internal analyzer pipeline.

## Near-Term Product Slice

1. Demo site: use the existing `query-doctor-web --public-demo` mode as the
   first read-only click-through demo surface. Do not build a separate demo app
   until the public-demo path proves insufficient.
2. Test-cluster outreach: prepare a concise Cloudera/design-partner request for
   read-only Cloudera Manager plus Impala access. The request should ask for
   bounded Recent-scan validation, not broad data access, SQL execution, or raw
   artifact sharing.
3. Minimal config: keep a copy-pasteable Cloudera Manager starter config
   separate from advanced direct-Impala, Prometheus, metadata, and LLM settings.
4. UI/UX polish: prioritize Recent results and Details. Browser labels should
   use analyst workflow language such as `Scan details`, `Scan notes`,
   `More filters`, repeated workload details, and `Record rerun outcome`
   instead of internal analyzer concepts.
5. Documentation hygiene: keep README, demo, config, safety, roadmap, and
   support boundaries easy to find. Move deep contracts and historical material
   behind the documentation index, and avoid sending new users through the full
   knowledge base.

## Backlog Decisions To Review

| Item | Proposed action | Rationale |
| --- | --- | --- |
| Demo site | Build from `--public-demo` first | Existing synthetic demo is read-only, local-safe, and already blocks writes. |
| Cloudera test cluster request | Use [cloudera-test-cluster-request.md](cloudera-test-cluster-request.md) as the outreach template | Real Impala/CM validation is the highest-leverage way to improve the primary product. |
| Minimal config | Keep `query-doctor-config.minimal.example.json` as the first-copy example | The current full example is useful, but too broad for first launch. |
| Documentation size | Use [repository-simplification-audit.md](repository-simplification-audit.md) before pruning | The docs are now a knowledge base; the entry path needs curation. |
| Russian docs | Treat English as canonical and keep only important Russian user paths fresh | Full mirrored deep contracts can drift faster than they help. |
| UI/UX | Keep refining Recent-results and Details polish | The UI should answer analyst questions before exposing diagnostics mechanics. |
| Demo brief | Keep or shorten as outreach reference | Useful for demos, but should not be required reading. |
| Synthetic Demo Mode | Keep | It is a real public-safe product/demo workflow. |
| Demo Preflight | Keep | It protects public sharing and release safety boundaries. |
| Cluster Doctor Contract | Keep as reference, de-emphasize in entry paths | It is a future seam, not a current product. |
| Changelog | Keep readable; archive or summarize old detail | Changelog should stay a release narrative, not a working log. |
| Brand Voice And Humor Policy | Shorten or rename to product voice guidance | Humor is allowed only on safe outer surfaces and should not dominate docs. |
| README screenshots | Keep only synthetic screenshots with provenance | The images are documentation; never replace them with real-cluster captures. |
| Scripts and tests | Classify roles before deletion | Many are safety/readiness gates; classify before pruning. |

## UI Label Decisions

- `Record rerun outcome` records whether a recommendation was applied and
  whether a comparable rerun improved, regressed, or stayed unchanged.
- Repeated workload, regressed workload, and action queue labels are preferred
  over generic group language. Stable HTML anchors such as `workload-groups`
  can remain as compatibility details.
- `Scan details` is the collapsed analyst-facing container after result rows.
  Critical warnings stay visible above the table as `Scan warnings`, and
  secondary notes/metrics stay inside the collapsed details area.

## Non-Goals For This Cleanup

- Do not remove safety contracts, raw-free gates, or validation scripts just
  because they are verbose.
- Do not collapse Trino or Spark boundaries into product support wording.
- Do not move private smoke targets, generated outputs, or branch-local notes
  into committed docs.
- Do not rewrite UI copy in a way that weakens diagnostic certainty, support
  boundaries, or raw-data redaction rules.
