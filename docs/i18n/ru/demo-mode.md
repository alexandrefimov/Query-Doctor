# Demo Mode

Last reviewed: 2026-06-19

Язык: [English](../../demo-mode.md) | Русский

Английская версия является канонической. Эта страница кратко описывает
synthetic demo pack.

## Что делает demo mode

`query-doctor-demo` генерирует local synthetic demo pack. Он не вызывает
Cloudera Manager, Impala, Ollama или network. Output содержит synthetic cases и
batch summary для localhost web UI.

Текущий pack покрывает Impala optimizer recommendations, stats maintenance,
rejected/untrusted optimizer draft, admission/runtime workload regression,
Storage/HDFS runtime follow-up, frequent-short workload handling, mixed
diagnostic signals, unknown-but-useful limitations, direct Impala compatibility
и local synthetic action outcomes. Он также содержит two read-only Trino Beta
demo cases в `trino_demo.json`: UI рендерит их из static raw-free compact
diagnosis facts без Trino coordinator, metadata collection, Details, reports,
optimizer behavior, generated SQL или SQL execution. Local synthetic action
outcomes содержат достаточно comparable rerun records с measured results, чтобы
default synthetic outcome gate проходил для admission/runtime workload
aggregate. В git попадает только safe aggregate summary, а не generated local
outcome records.

Основной public-demo запуск:

```bash
query-doctor-web --public-demo
```

`--public-demo` сам генерирует fresh synthetic pack в system temp directory,
подключает `batch_summary.json`, synthetic `action_outcomes.jsonl` и static
`trino_demo.json`, включает Python-only mode, игнорирует default local config
discovery и owner-source env, отклоняет explicitly loaded
CM/Impala/Prometheus/metadata/Trino local source/source-owner settings и
блокирует все POST routes.

Если нужно вручную посмотреть или переиспользовать generated pack, используйте
dedicated temp output path:

```bash
DEMO_PACK="${TMPDIR:-/tmp}/query-doctor-demo-pack"
query-doctor-demo --out "$DEMO_PACK" --overwrite
QUERY_DOCTOR_ACTION_OUTCOMES_PATH="$DEMO_PACK/action_outcomes.jsonl" \
  query-doctor-web --host 127.0.0.1 --port 8766 --batch-summary "$DEMO_PACK/batch_summary.json"
```

Основной public-demo вход: `/?query_group=workloads#scan-context`.
Он показывает Scan context и какую repeated pattern открыть следующей;
полный decision path остается на Workload Details: why, where, supported
change direction, rerun verification и local outcome history. Representative
cases ведут к case Action card, где безопасно записывать rerun feedback для
выбранного case.

## Read-only public demo

Снаружи остается click-through GET UI по synthetic pack, без collection, report
generation, optimizer actions, uploads, job cancellation и feedback writes.

## Safety

Demo pack не должен содержать real SQL, raw profiles, raw metadata, hostnames,
users, credentials, model/runtime internals или local paths из другого
окружения.

Подробности запуска: [английский demo-mode](../../demo-mode.md).
