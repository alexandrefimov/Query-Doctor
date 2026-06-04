# Чеклист evidence из тестового Spark-кластера

Last reviewed: 2026-06-04

Язык: [English](../../spark-test-cluster-evidence-checklist.md) | Русский

Этот чеклист задает первый безопасный handoff из тестового Spark-кластера или
операторского Spark History Server в исследовательский контур Query Doctor. Это
не объявление live Spark support, не engine selector, не Recent workflow, не
Details/trusted-report surface, не optimizer path и не разрешение запускать
Spark jobs или Spark SQL через Query Doctor. Изолированная Spark
compact-diagnosis page остается experimental surface для одного explicit
History Server application или уже accepted raw-free compact JSON.

Используйте этот документ вместе с
[spark-architecture-spike.md](spark-architecture-spike.md),
[engine-support-gap-matrix.md](../../../engine-support-gap-matrix.md),
[engine-expansion-plan.md](../../../engine-expansion-plan.md) и
[test-matrix.md](../../../test-matrix.md).

## Цель

Перейти от synthetic Spark fixtures к representative operator-reviewed compact
evidence без изменения product support claim. Первый реальный evidence set
должен показать, можно ли существующие Spark History Server и event-log-derived
summaries свести к accepted raw-free compact contract и получить полезные
детерминированные attention areas.

Для этого не нужен live query execution. Нужен bounded read-only сбор или
operator export уже существующего application evidence.

## Жесткие границы

- Не запускать Spark jobs, notebooks, `spark-submit`, user SQL или optimizer
  SQL.
- Не запускать Query Doctor-generated `EXPLAIN`, `EXPLAIN ANALYZE` или Spark
  SQL plans.
- Не использовать broad History Server crawls, application discovery или
  unbounded time-window collection как первый evidence path.
- Не получать, не коммитить, не прикладывать, не вставлять в prompts и не
  рендерить raw Spark event logs, raw Web UI pages, raw SQL descriptions,
  physical plans, driver logs, executor logs, stack traces, environment dumps,
  classpaths, command lines или raw task/executor records.
- Не включать application IDs, attempt IDs, SQL execution IDs, job IDs, stage
  IDs, task IDs, executor IDs, users, principals, hostnames, endpoint URLs,
  object-store paths, local paths, artifact names, table names, column names,
  secrets, credentials, tokens или Kerberos/TLS material.
- Не использовать evidence set для Spark engine registration, Recent scan
  support, Details/trusted reports, optimizer behavior, README support claims
  или package metadata claims.

## Первый допустимый evidence

Первый evidence set должен содержать только compact evidence:

- compact Spark History Server summaries для одного explicit application,
  собранные через `query-doctor-collect-spark-history`;
- optional compact summaries для одного explicit SQL execution selector, если
  оператор знает selector и он не записывается в output;
- compact event-log-derived summaries, которые уже соответствуют
  `spark_history_eventlog_compact_v1`;
- raw-free engine fact boundary JSON из collector или mapper;
- deterministic Spark compact diagnosis JSON из accepted compact payload;
- manifest только с safe categories: source kind, Spark version family, source
  contract, collection time-window category, record counts, byte bounds,
  redaction status и known omissions;
- redaction note, описывающий классы удаленных полей, а не удаленные значения.

History Server collection должен оставаться explicit-application, summary-only,
bounded per endpoint, redirect-disabled и target-guarded. Private или loopback
History Server targets требуют explicit local opt-in и не должны попадать в
committed docs или prompts.

## Минимальный набор кейсов

Подготовьте минимальный безопасный representative set:

- finished Spark SQL application с accepted SQL execution linkage;
- application-only collection, где query linkage равно `same_application`;
- failed или killed application только с allowlisted safe failure category;
- missing или partial History Server endpoint coverage;
- unknown Spark version или unsupported source contract;
- spill observed;
- shuffle-heavy или data-movement-heavy stage summary;
- stage или task skew candidate;
- failed stage или failed task aggregate;
- retried task aggregate;
- long SQL elapsed-time context;
- scheduler-delay context, когда каждый selected stage summary имеет explicit
  safe value;
- adaptive execution checked enabled и checked disabled;
- dynamic allocation observed и unknown;
- executor loss или executor churn aggregate;
- high aggregate executor memory utilization при complete used/capacity values;
- missing stage, task, job или executor summaries, которые мапятся в
  `unknown`;
- oversized или over-deep payload rejection case с synthetic padding only;
- unsafe raw field rejection case с synthetic sentinel values only.

## Sanitization checklist

Перед тем как файл попадет в repository, issue tracker, prompt или shared
review artifact:

- удалите raw SQL, SQL descriptions, plan descriptions и physical plans;
- удалите application, attempt, SQL execution, job, stage, task и executor
  identifiers;
- удалите users, groups, principals, queues, pools, tags, session labels и
  environment-derived metadata;
- удалите hostnames, endpoint URLs, IP addresses, object-store URIs, local
  paths, classpaths, command lines, package names и artifact names;
- удалите table, database, schema, catalog, column, partition, manifest и file
  names;
- удалите stack traces, raw exception messages, warning payloads, log lines и
  vendor UI internals;
- удалите secrets, credentials, tokens, passwords, keys, cookies, headers, TLS
  material, Kerberos caches и extra auth material;
- замените source-specific detail на compact checked booleans, durations,
  counts, bytes, ratios, safe categories, warning IDs и explicit `unknown`
  states;
- держите compact boolean markers типизированными, особенно adaptive
  execution, dynamic allocation и application/job/stage failure markers;
- reject/regenerate export, если redaction status неизвестен.

## Local validation gate

Соберите local sanitized evidence package из operator-reviewed compact samples.
Builder требует explicit redaction и sentinel-test confirmations, пишет output
только после успешной validation и не должен echo-ить sample paths или payloads:

```bash
query-doctor-build-spark-evidence-package \
  --out <sanitized-spark-package.json> \
  --package-id <safe_package_label> \
  --prepared-date-utc YYYY-MM-DD \
  --redaction-reviewed \
  --sentinel-tests-passed \
  --sample finished_sql_exact_linkage:spark_eventlog_compact:<compact-a.json>
```

Затем провалидируйте package wrapper перед fixture conversion:

```bash
query-doctor-validate-spark-evidence-package <sanitized-spark-package.json>
```

Для early dry runs можно использовать `--partial-ok`, пока minimum case set еще
неполный. Validator печатает только safe summary и не должен echo-ить package
path, sample paths, raw payload values, History Server URLs, request selectors,
SQL, log content или local output paths.

Запускайте Spark compact readiness audit на каждом accepted compact JSON:

```bash
python3 scripts/audit_spark_compact_readiness.py \
  <spark-compact-a.json> <spark-compact-b.json> \
  --require-supported-attention \
  --require-min-inputs 2 \
  --require-source-contract spark_history_server_compact_v1 \
  --require-source-contract spark_history_eventlog_compact_v1
```

Для более строгого promotion-candidate набора добавляйте
`--fail-on-source-warnings` только после осознанного закрытия missing endpoint
coverage. Audit должен печатать только safe aggregate counts и не должен
echo-ить compact input paths, raw filenames, raw payload values, History Server
URLs, request selectors, SQL, log content или local output paths.

Raw exports держите вне repository и вне prompts. Если оператору нужно
сохранить raw event logs или History Server exports для аудита, они должны
оставаться внутри operator-controlled Spark environment, а не в Query Doctor
workspace artifacts.

## Acceptance gate

Evidence set готов для Query Doctor fixture или promotion-gate work только
когда:

- каждый sample вручную проверен как raw-free;
- каждый sample укладывается в maximum size, response и nested-depth bounds
  compact contract;
- каждый supported fact является query-linked, application-linked или явно
  context-only;
- каждый unsupported, absent, partial или intentionally redacted field имеет
  explicit `unknown`, warning ID или omission reason;
- `query-doctor-build-spark-evidence-package` собирает sanitized package
  wrapper из compact samples без печати paths или raw values;
- `query-doctor-validate-spark-evidence-package` принимает тот же wrapper без
  печати paths или raw values;
- `scripts/audit_spark_compact_readiness.py` проходит по compact sample suite
  без печати paths или raw values;
- не нужен Spark engine registration, Recent workflow, Details route, trusted
  report, optimizer behavior, public README support claim или package metadata
  support claim.

Следующий шаг после accepted evidence set все еще fixture и readiness work:
перевести compact samples в committed sanitized fixtures, mapper tests и
diagnosis tests. Product support идет позже, после закрытия support gates из
engine expansion plan и support gap matrix на representative evidence.
