# Synthetic Demo Mode

Last reviewed: 2026-05-21

Language: English | [Russian](i18n/ru/demo-mode.md)

Query Doctor can generate a local synthetic demo pack that works without
Cloudera Manager, Impala, network access, or LLM calls.

Generate the pack under a dedicated `query-doctor-*` temp directory. The
generator refuses repository paths, generic temp roots, and unsafe shallow
output paths:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
```

Then launch the web UI with the generated batch summary:

```bash
query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Open:

```text
http://127.0.0.1:8766/?query_group=optimization#recent-results
```

The generated pack includes synthetic Recent queries / Finished queries cases
for:

- optimizer recommendation outcomes
- stats maintenance candidate evidence
- rejected/untrusted optimizer draft behavior

The pack is intentionally local generated data, not committed fixtures. It is
safe for demos because it does not contain real profiles, real metadata, real
query text, local corpus paths from another environment, model names, or raw
runtime output. It is still demo data only and must not be used as performance
evidence.

## README Screenshot Refresh

The README screenshots at `docs/assets/demo_search.png` and
`docs/assets/demo_finished_queries.png` should be refreshed after material web
UI or workflow layout changes. Use only the synthetic demo pack, and keep
generated demo output outside the repository:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Open the printed localhost URL and capture:

- the main bounded search form for `docs/assets/demo_search.png`;
- the Finished Queries results view for `docs/assets/demo_finished_queries.png`.

For the results view, the Optimization candidates filter is a useful default:

```text
http://127.0.0.1:8766/?query_group=optimization#recent-results
```

Capture browser viewports and replace only the public synthetic screenshots.
Do not commit the generated demo pack, local config, local browser output, raw
profiles, raw SQL, local paths, or screenshots from real Cloudera Manager or
Impala data.
