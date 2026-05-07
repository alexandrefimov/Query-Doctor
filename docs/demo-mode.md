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
http://127.0.0.1:8766/?query_group=optimizer_ready#recent-results
```

The generated pack includes synthetic Finished Queries cases for:

- optimizer-ready recommendations
- stats maintenance candidate evidence
- rejected/untrusted optimizer draft behavior

The pack is intentionally local generated data, not committed fixtures. It is
safe for demos because it does not contain real profiles, real metadata, real
query text, local corpus paths from another environment, model names, or raw
runtime output. It is still demo data only and must not be used as performance
evidence.
