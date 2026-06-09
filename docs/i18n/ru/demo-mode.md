# Demo Mode

Last reviewed: 2026-06-06

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
и local synthetic action outcomes. Эти local synthetic action outcomes содержат
достаточно comparable rerun records с measured results, чтобы default synthetic
outcome gate проходил для admission/runtime workload aggregate. В git попадает
только safe aggregate summary, а не generated local outcome records.

Канонический public-demo запуск использует dedicated temp output path:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Основной public-demo вход: `/?query_group=workloads#workload-action-queue`.
Он показывает, какую repeated group открыть следующей; полный action plan
остается на workload Details: why, where, supported change direction, rerun
verification и local outcome history. Representative cases ведут к case Action
card, где безопасно записывать rerun feedback для выбранного case.

## Read-only public demo

Для public-style read-only demo запускайте одну команду:

```bash
query-doctor-web --public-demo
```

`--public-demo` сам генерирует fresh synthetic pack в system temp directory,
подключает `batch_summary.json` и synthetic `action_outcomes.jsonl`, включает
Python-only mode, игнорирует default local config discovery и owner-source env,
отклоняет explicitly loaded CM/Impala/Prometheus/metadata/source-owner settings
и блокирует все POST routes. Снаружи остается click-through GET UI по synthetic
pack, без collection, report generation, optimizer actions, uploads, job
cancellation и feedback writes.

## Safety

Demo pack не должен содержать real SQL, raw profiles, raw metadata, hostnames,
users, credentials, model/runtime internals или local paths из другого
окружения.

Подробности запуска: [английский demo-mode](../../demo-mode.md).
