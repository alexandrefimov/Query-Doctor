# Query Doctor: русская навигация

Last reviewed: 2026-06-14

Язык: [English](../../README.md) | Русский

Английская документация является канонической для публичного репозитория.
Русские страницы в `docs/i18n/ru/` - это выборочный пользовательский и
операторский companion layer, а не полное зеркало всего дерева документации.
Их задача - помогать обычным пользователям, операторам demo/local setup и
читателям safety boundaries, не дублировать каждый agent/internal документ.

Если английская и русская страницы расходятся, английская версия считается
источником истины до обновления локализованной страницы. В канонических
публичных документах русские фразы должны оставаться только там, где они
являются частью текущего продукта, например в названиях секций русскоязычного
отчета.

Для работы агентов и решений по реализации используйте английские базовые
документы: project README, `docs/README.md`, safety contract, architecture,
roadmap, development practices, codex handoff и code audit. Русские страницы
служат навигационным и операторским слоем и не должны перебивать текущий
английский контракт. Agent/internal pages на русском могут оставаться краткими
указателями или резюме, если полная локализация не нужна обычному пользователю.

## Что читать сначала

- [README проекта](../../../README.md): краткий публичный обзор, установка,
  workflow, безопасность и лицензирование.
- [Русская версия README проекта](../../../README.ru.md): companion-перевод
  основного публичного README.
- [Индекс документации](../../README.md): карта всех актуальных и справочных
  документов.
- [Brand voice](brand-voice.md): правила для безопасного тона продукта и
  юмора.
- [Локальные smoke-проверки](local-smoke.md): public-safe проверки package,
  analyzer, report, metadata и Recent scan; private targets остаются в
  ignored local notes.
- [Credentials](credentials.md): локальная раскладка учетных данных, keytab,
  Cloudera Manager (CM) env и Kerberos cache.
- [Configuration reference](configuration.md): русская страница по JSON config,
  порядку discovery и группам параметров.
- [Контракт безопасности](safety-contract.md): обязательные границы доверия,
  redaction и validator rules.
- [Owner Raw D3 Deployment Contract](../../owner-raw-d3-deployment.md):
  канонический английский deployment contract для shared/non-local
  `owner_raw`: trusted auth front door выставляет ровно один нормализованный
  viewer header, а Query Doctor делает только owner check.
- [Архитектура](architecture.md): границы collector, analyzer, report,
  optimizer и UI.
- [Локальный UI demo](DEMO.md): запуск localhost UI, demo storyline и
  pre-demo smoke-проверки.
- [Model route protocol](model-bakeoff.md): правила сравнения model routes без
  публикации local bake-off результатов.
- [Roadmap](roadmap.md): что реализовано сейчас и какие seams являются
  будущей работой.
- [Development practices](development-practices.md): локальный gate,
  pre-commit hooks, staged public-safety check и общие правила разработки.
- [Public documentation boundary](public-documentation-boundary.md): что
  можно коммитить в public docs, а что должно оставаться в local exclude-only notes.
- [Матрица поддержки движков](engine-support-gap-matrix.md): что реализовано
  для Impala и почему Trino и Spark остаются ниже product support.
- [Ограничения счетчиков профиля Impala](impala-profile-counter-caveats.md):
  будущий контракт стабильности счетчиков, диалекты профилей и правила
  доказательств.
- [Заметки к релизу 0.6.0](release-notes-0.6.0.md): краткое описание Spark
  compact intake, Trino raw-free handoff gates и Impala diagnostic-loop
  calibration.
- [Заметки к релизу 0.5.0](release-notes-0.5.0.md): краткое описание
  diagnostic-loop hardening и raw-free evidence handoff gates.
- [Заметки к релизу 0.4.3](release-notes-0.4.3.md): краткое описание
  report-mode и web UI polish.
- [Заметки к релизу 0.4.2](release-notes-0.4.2.md): краткое описание public
  release baseline.
- [Заметки к релизу 0.4.1](release-notes-0.4.1.md): краткое описание
  synthetic demo update.
- [Заметки к релизу 0.4.0](release-notes-0.4.0.md): краткое описание
  предыдущего опубликованного релиза.
- [Заметки к релизу 0.3.0](release-notes-0.3.0.md): краткое описание
  предыдущего опубликованного релиза.
- [UI/UX аудит](ui-ux-audit.md): принятые выводы по Details, Results и
  пользовательскому пути.

## Public demo и release paths

- [Demo Mode](demo-mode.md): генерация synthetic demo pack, local synthetic
  action outcomes и обновление public README screenshots.
- [Локальный UI demo](DEMO.md): localhost UI demo runbook, основные экраны,
  правила безопасности и public demo storyline.
- [Demo Cases](demo-cases.md): очищенные synthetic scenarios для public demos.
- [Demo Data Engineer Brief](demo-data-engineer-brief.md): talk track по
  scoring, metadata, metrics, reports и optimizer boundaries.
- [Demo Preflight](demo-preflight.md): deterministic guard перед demo, release
  и public-sharing cleanup.
- [Public Release Readiness](public-release-readiness.md): snapshot готовности
  к релизу и P0 gates.
- [Заметки к релизу 0.6.0](release-notes-0.6.0.md): Spark compact intake,
  Trino handoff gates и Impala diagnostic-loop calibration.
- [Заметки к релизу 0.5.0](release-notes-0.5.0.md): diagnostic-loop
  hardening и raw-free evidence handoff gates.
- [Заметки к релизу 0.4.3](release-notes-0.4.3.md): report-mode и web UI
  polish release notes.
- [Заметки к релизу 0.4.2](release-notes-0.4.2.md): public release baseline
  release notes.
- [Заметки к релизу 0.4.1](release-notes-0.4.1.md): synthetic demo update
  release notes.
- [Release Checklist](release-checklist.md): final release-candidate, tag,
  package-index и visibility-change procedure.
- [Upstream AI-анализатор Impala](upstream-impala-ai-analyzer.md): watchlist
  по встроенному AI-анализатору профилей Impala и позиционированию Query
  Doctor.

## Исследовательские и будущие направления

- [Trino discovery spike](trino-discovery-spike.md): первый fixture-only срез
  второго движка без текущей поддержки live-сбора.
- [Диагностический контракт Trino](../../engines/i18n/ru/trino-diagnostic-contract.md):
  исследовательские границы будущей Trino-диагностики.
- [Проект live-сбора Trino](../../engines/i18n/ru/trino-live-collection-design.md):
  будущий дизайн безопасного bounded сбора, не текущая функция.
- [Чеклист evidence export из тестового Trino-кластера](../../engines/i18n/ru/trino-test-cluster-evidence-checklist.md):
  безопасный handoff для первых operator-exported sanitized fixtures.
- [Шаблоны Trino evidence package](../../engines/i18n/ru/trino-evidence-package-templates.md):
  manifest, redaction note, local event-store, operator HTTP archive, local
  query-detail, local query-list/statement-stats, pruned query-info и compact
  diagnosis формат для sanitized handoff.
- [Trino private preview release path](../../engines/i18n/ru/trino-private-preview-release.md):
  как показывать Trino как closed test-cluster private preview без public
  support claim.
- [Архитектурный spike Spark](../../engines/i18n/ru/spark-architecture-spike.md):
  bounded compact research контракт для Spark History Server/event-log fact
  model, compact-only adapter и isolated compact-diagnosis page без public
  support claim.
- [Чеклист evidence из тестового Spark-кластера](../../engines/i18n/ru/spark-test-cluster-evidence-checklist.md):
  безопасный handoff для operator-reviewed compact Spark History Server/event-log
  evidence без live Spark support claim.
- [Журнал диагностических пробелов](../../research/i18n/ru/diagnostic-gap-log.md):
  безопасный шаблон для production gaps без сырых данных.
- [Мониторинг upstream-сигналов](../../research/i18n/ru/upstream-watch.md):
  как отслеживать Impala, Trino и внешние сигналы без заявлений о поддержке.

## Локальная автоматизация

Перед handoff, release-проверками или публикацией удобно запускать один общий
gate:

```bash
scripts/local_gate.sh
```

Для публичной ветки добавляйте `PUBLIC_RELEASE=1`, чтобы включить проверку
tracked tree и git history на приватные маркеры:

```bash
PUBLIC_RELEASE=1 scripts/local_gate.sh
```

Для commit-time guardrail установите hooks:

```bash
pre-commit install
```

Перед public-sharing cleanup или release-веткой запускайте полный набор hooks:

```bash
pre-commit run --all-files
```

Хук `check_staged_public_safety.py` блокирует staged local configs,
сгенерированные case/report/profile artifacts, caches, virtualenv paths,
приватные host/domain markers, user home paths и high-confidence secrets до
попадания в историю. Полный pre-commit run также проверяет ruff check, ruff
format, whitespace и Markdown links. Это быстрый guardrail, а не замена
финальной проверке перед публичным релизом.

## Терминология

Русский слой должен быть понятным оператору, а не механической смесью
английских существительных с русскими окончаниями. Английский термин стоит
оставлять без перевода, если это точное имя продукта, UI-метка, команда,
конфигурационный ключ, route, fact id, тестовый маркер или путь к файлу.

Обычные слова в тексте лучше переводить:

| English | Русский вариант |
| --- | --- |
| workflow | рабочий процесс / сценарий |
| bounded | ограниченный |
| raw-free | без сырых данных |
| trusted report | доверенный отчет |
| evidence | доказательства / диагностические сигналы |
| guardrail | защитное правило / ограничение |
| source | источник |
| checklist | контрольный список |
| release readiness | готовность к релизу |
| smoke check | smoke-проверка / быстрая проверка |

Идентификаторы вроде `Query Doctor`, `Impala`, `Cloudera Manager`, `Trino`,
`PyPI`, `GitHub`, `Query ID`, `Details`, `Recent`, `Running now`,
`query-doctor-web`, `cluster_type`, `analysis_facts.md` и `source_visibility`
оставляются как есть. Если термин является UI-меткой, при первом упоминании
можно дать русское пояснение рядом, но не менять саму метку.

## Текущий статус локализации

Русские сопроводительные документы не обязаны покрывать каждый английский
Markdown-документ. Для длинных документов это не всегда дословный перевод:
часть страниц является кратким русским резюме со ссылкой на канонический
английский источник.

Приоритет дальнейшей локализации:

- поддерживать в первую очередь user-facing и operator-facing документы:
  README, demo/local setup, credentials, configuration, security model,
  safety contract и основные workflow descriptions;
- полные переводы делать только там, где документ нужен обычному пользователю,
  оператору или задает важную границу доверия;
- для deep architecture, roadmap, audit, agent handoff, тестовых матриц и
  research-документов достаточно краткого русского резюме или ссылки на
  английский источник, если это не меняет пользовательскую безопасность;
- сначала поддерживать `safety-contract`, `configuration`, `security-model`,
  `query-optimizer-contract` и основные demo/setup pages;
- не переводить технические идентификаторы, имена команд, файлов, секций и
  validator markers, если они являются частью интерфейса или тестового
  контракта.

Текущий global config `language` управляет Help, Details static UI copy и
новыми trusted reports. Английский остается default; русский режим использует
тот же language-specific report contract, prompt, normalizer и validator tests.
Смена языка остается общей для web copy и новых reports, а не отдельным
переключателем только prompt текста.
