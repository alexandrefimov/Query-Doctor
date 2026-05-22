# Engine Support Gap Matrix

Last reviewed: 2026-05-23

This matrix describes current implementation status for engine fact coverage.
It is not a public support promise. The public product remains Apache Impala
only until a second engine has collection contracts, parser/fact fixtures,
metadata allowlists, browser/report safety tests, and a documented support gap
closure plan.

## Status Legend

- `implemented`: production path exists and is tested for the current product.
- `contracted`: typed normalized fact contract exists, but production
  workflows do not consume it yet.
- `fixture-only`: synthetic or sanitized fixture mapping exists for contract
  shaping only.
- `unknown`: facts are unavailable or insufficient; do not infer a diagnosis.
- `not observed`: the signal was checked in the bounded facts and was absent.

## Current Matrix

| Fact family | Apache Impala | Trino |
| --- | --- | --- |
| Public support status | implemented | not supported |
| Live query/profile collection | implemented through Cloudera Manager and direct Impala daemon workflows | not implemented |
| Engine adapter registration | implemented | not registered |
| Engine fact contract bundle | contracted through `impala_engine_facts.py` projection | fixture-only through `trino_fixture_facts.py` |
| Golden contract harness | covered across clean finished, admission-queued, spill-observed, missing-section, and failed-query cases | covered by shared raw-free contract cases for finished/failed/failure-category/blocked/stage-skew/connector-metric statement stats and completed event fixtures |
| Lifecycle facts | projected from safe query context when available | fixture-only from synthetic finished/failed/blocked statement stats and completed event payloads |
| Failure category | projected only as failed lifecycle in the current Impala projection | fixture-only from compact checked/category safe summary; no raw exception classes, messages, stack traces, endpoint details, object names, connector internals, or live source |
| Query wall-clock / elapsed timing | projected from Query Wall Clock, profile TotalTime, and Query Timeline facts | fixture-only from statement stats |
| Planning / admission / backend-start timing | projected when Impala Query Timeline phases are available | unknown |
| Input/output bytes and rows | projected from current analyzer totals where available | fixture-only from statement stats |
| Peak memory | projected from profile resource facts where available | fixture-only from statement stats |
| Spill / scratch evidence | projected as observed count or not observed from explicit spill/scratch evidence lines | fixture-only spilled bytes |
| Connector metric signal | not applicable to current Impala profile projection | fixture-only checked/present signal from a compact safe summary; no connector names, metric names, endpoints, object names, raw connector payloads, or live connector source |
| Fragment / stage counts | projected from Impala profile format and lifecycle facts | fixture-only from rootStage shape |
| Backend / stage skew candidates | projected from current backend-tail analysis when available | fixture-only from safe aggregate per-task stage-skew summary; no raw task or worker details |
| Admission pool semantics | implemented for Impala profile/context facts | unknown |
| Metadata enrichment | implemented through explicit bounded Impala metadata collection | not implemented |
| Runtime metrics | implemented through Cloudera Manager and optional Prometheus context | not implemented |
| Cluster events | implemented through bounded Cloudera Manager events | not implemented |
| Offline event-listener fixture import | not applicable to implemented Impala workflows | fixture-only compacted completed-event mapping, missing-field `unknown` semantics, and oversized/unsafe-field rejection tests; no event store reader or live adapter |
| Live collection design | implemented for current Impala providers | documented as future-only in `trino-live-collection-design.md`; no adapter implemented |
| Browser/report boundary payload from normalized engine facts | contracted and raw-free tested; not wired into existing Impala browser/report paths | fixture-only payload tested; blocked from product surfaces until support gates exist |
| Boundary payload consumer probe | raw-free tested state-count and attention-signal probe; not wired into product ranking or UI | fixture-only probe tested; not a support claim |
| Minimum raw-free intake contract | implicit in current Impala safety/report/browser tests | documented and tested for fixture-only Trino facts; blocks live intake and product surfaces until gates close |
| Browser/report output from normalized engine facts | not wired; existing Impala browser/report paths remain unchanged | blocked until raw-free safety tests and support gates exist |

## Near-Term Closure Path

1. Keep current Impala analyzer output, scoring, browser, and report behavior
   stable while the projection is tested.
2. Keep the golden contract harness focused on shared public shape,
   `supported` / `not_observed` / `unknown` semantics, and raw-free output,
   not on pretending the engines expose the same counters. Expand Impala
   projection cases before moving product consumers to normalized facts.
3. Use the raw-free boundary payload and consumer probe as the future consumer
   seam, then move one internal consumer at a time toward normalized facts only
   after the projection proves stable on existing Impala fixtures.
4. Keep Trino fixture-only until live collection, authentication, redaction,
   metadata, raw-free intake, and browser/report safety contracts are designed
   and tested.
