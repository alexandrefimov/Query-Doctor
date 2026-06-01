# Trino private preview release path

Last reviewed: 2026-05-26

Язык: [English](../../trino-private-preview-release.md) | Русский

Английская версия является канонической. Эта страница описывает, как показывать
Trino в релизе как раннюю закрытую интеграцию с тестовым кластером, не заявляя
публичную поддержку.

## Статус

Это не public support announcement, не live collector, не engine selector, не
browser/report surface, не optimizer workflow и не разрешение выполнять user
SQL через Query Doctor. Production engine support остается Apache Impala only.

Trino можно называть private preview только если есть два безопасных сигнала:

- bounded Kerberos/SPNEGO smoke against approved test cluster;
- sanitized evidence-package intake для operator-exported compact samples.

Оба сигнала остаются вне product workflows Query Doctor. Trino остается
unsupported для web UI, reports, optimizer и live collection.

## Что показывать

1. Fixture walkthrough:

   ```bash
   python3 scripts/demo_trino_evidence_package.py
   ```

   Он показывает package shape, parser coverage, safe source summary и case
   counts без сети и без raw payloads.

2. Closed-cluster smoke command shape только с placeholders:

   ```bash
   python3 scripts/trino_kerberos_smoke.py \
     --server https://<test-trino-endpoint> \
     --client-user <client-user> \
     --kerberos-principal <principal@EXAMPLE.COM> \
     --service-name HTTP \
     --count-table <catalog.schema.table> \
     --sample-table <catalog.schema.table> \
     --out <local-smoke-output-dir>
   ```

   Это dev-only smoke для тестового кластера. Он использует только built-in
   allowlisted read-only statement shapes, bounded Trino protocol pages и safe
   summary. Его нельзя подключать к product workflows.

3. Sanitized handoff:

   ```bash
   python3 scripts/build_trino_evidence_package.py \
     --out <sanitized-package.json> \
     --package-id <safe-package-label> \
     --prepared-date-utc YYYY-MM-DD \
     --export-window-start-utc YYYY-MM-DDTHH:00:00Z \
     --export-window-end-utc YYYY-MM-DDTHH:00:00Z \
     --redaction-reviewed \
     --sentinel-tests-passed \
     --sample <case>:<source_type>:<sanitized-sample-json>

   python3 scripts/validate_trino_evidence_package.py <sanitized-package.json>
   ```

   Команды работают только с already-sanitized compact samples и не должны
   печатать input paths, raw payloads, raw values, query identifiers, users,
   hostnames, object names, connector details или rejected record contents.

## Release gates

Перед релизной формулировкой "Trino private preview":

- `python3 scripts/demo_trino_evidence_package.py` проходит и печатает только
  safe summary.
- Dev-only Kerberos/SPNEGO smoke запускался against approved test cluster с
  explicit read-only smoke tables; для handoff остается только safe summary.
- Минимум один operator-exported evidence package проходит
  `scripts/validate_trino_evidence_package.py` без `--partial-ok`, или release
  note прямо говорит, что evidence package пока synthetic-only.
- README и release docs продолжают говорить, что Apache Impala - единственный
  production engine support.
- Не добавлены Trino engine adapter, public engine selector, browser route,
  trusted report path, optimizer behavior, metadata collector, query-history
  reader или public support claim.

## Что остается после private preview

Private preview не равен product support. Следующие gates: превратить accepted
test-cluster packages в committed sanitized fixtures и mapper tests, закрыть
support-gap matrix, доказать source contracts для future reader и добавить
browser/report boundary tests до попадания Trino-derived facts в product
surfaces.
