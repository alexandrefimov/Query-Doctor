# Demo Mode

Last reviewed: 2026-05-28

Язык: [English](../../demo-mode.md) | Русский

Английская версия является канонической. Эта страница кратко описывает
synthetic demo pack.

## Что делает demo mode

`query-doctor-demo` генерирует local synthetic demo pack. Он не вызывает
Cloudera Manager, Impala, Ollama или network. Output содержит synthetic cases и
batch summary для localhost web UI.

Текущий pack покрывает optimizer recommendations, stats maintenance,
rejected/untrusted optimizer draft, admission/runtime workload regression,
Storage/HDFS runtime follow-up, frequent-short workload handling, mixed
diagnostic signals, unknown-but-useful limitations, direct Impala compatibility
и local synthetic action outcomes.

Канонический public-demo запуск использует dedicated temp output path:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Основной public-demo вход: `/?query_group=workloads#workload-action-queue`.

## Safety

Demo pack не должен содержать real SQL, raw profiles, raw metadata, hostnames,
users, credentials, model/runtime internals или local paths из другого
окружения.

Подробности запуска: [английский demo-mode](../../demo-mode.md).
