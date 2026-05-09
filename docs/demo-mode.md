# Synthetic Demo Mode

Query Doctor can generate a local synthetic demo pack that works without
Cloudera Manager, Impala, network access, or LLM calls.

Generate the pack under a dedicated temp directory:

```bash
query-doctor-demo --out /tmp/query-doctor-demo-pack --overwrite
```

Then launch the web UI with the generated batch summary:

```bash
query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary /tmp/query-doctor-demo-pack/batch_summary.json
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

The README screenshot at `docs/assets/query-doctor-synthetic-demo.png` should
be refreshed after material web UI or workflow layout changes. Use only the
synthetic demo pack, and keep generated demo output outside the repository:

```bash
query-doctor-demo --out /tmp/query-doctor-demo-pack --overwrite
query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary /tmp/query-doctor-demo-pack/batch_summary.json
```

Open the printed localhost URL, preferably the Optimization candidates view:

```text
http://127.0.0.1:8766/?query_group=optimization#recent-results
```

Capture the browser viewport and replace only
`docs/assets/query-doctor-synthetic-demo.png`. Do not commit the generated demo
pack, local config, local browser output, raw profiles, raw SQL, local paths, or
screenshots from real Cloudera Manager or Impala data.
