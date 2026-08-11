# Query Doctor: русская навигация

Last reviewed: 2026-06-22

Язык: [English](../../README.md) | Русский

Английская документация является канонической для публичного репозитория.
Русский слой теперь намеренно узкий: это не полное зеркало всего дерева документации,
а user-facing и operator-facing документы, где русская companion страница
снижает риск неправильной настройки или неверного support claim. Deep
architecture, audit, agent, contributor, release, research и engine deep-dive
документы остаются English-only, чтобы не создавать дрейфующие дубли.

Если английская и русская страницы расходятся, английская версия считается
источником истины до обновления локализованной страницы. Технические
идентификаторы, имена команд, файлов, routes, fact ids, config keys и UI-метки
не переводятся.

## Что Читать Сначала

- [README проекта](../../../README.md): канонический публичный обзор,
  установка, workflow, safety и support boundaries.
- [Русская версия README проекта](../../../README.ru.md): краткий
  companion-перевод основного публичного README.
- [Индекс документации](../../README.md): карта всех английских canonical docs.
- [Локальный UI demo](DEMO.md): запуск localhost UI, demo storyline и
  pre-demo smoke-проверки.
- [Configuration reference](configuration.md): локальная JSON-конфигурация,
  discovery order, credential references и source visibility.
- [Credentials](credentials.md): локальная раскладка учетных данных, Kerberos
  cache, keytab и секреты вне git.
- [Локальные smoke-проверки](local-smoke.md): public-safe проверки package,
  analyzer, report, metadata и Recent scan; private targets остаются в ignored
  local notes.
- [Границы поддержки](support-boundary.md): поверхности поддержки целиком,
  Trino/Spark boundary и то, что сознательно вне области. Английский оригинал —
  [../../support-boundary.md](../../support-boundary.md).
- [Security model](security-model.md): публичная модель безопасности и
  privacy overview.
- [Safety contract](safety-contract.md): пользовательски важные trust/redaction
  границы, raw-free browser/report surfaces и owner-raw ограничения.
- [Roadmap companion](roadmap.md): узкая русская companion-страница для
  текущего roadmap pull queue, включая Owner Raw D3 Deployment Contract и
  границу live front-door validation gate.

## Demo И Setup

- [Demo Mode](demo-mode.md): генерация synthetic demo pack, local synthetic
  action outcomes и обновление public README screenshots.
- [Demo Preflight](demo-preflight.md): deterministic guard перед demo, release
  и public-sharing cleanup.
- [Demo Cases](demo-cases.md): очищенные synthetic scenarios для public demos.
- [Demo Data Engineer Brief](demo-data-engineer-brief.md): talk track по
  scoring, metadata, metrics, reports и optimizer boundaries.

## Где Читать Остальное

Русских companion-страниц для внутренних документов почти нет. Для этих тем
используйте английские canonical docs, кроме явно перечисленных узких
operator-facing companions:

- engine support и Trino/Spark boundaries:
  [engine-support-gap-matrix.md](../../engine-support-gap-matrix.md) и
  [engines/README.md](../../engines/README.md);
- architecture, audits, code ownership и validation:
  [architecture.md](../../architecture.md),
  [code-audit.md](../../code-audit.md), [code-map.md](../../code-map.md),
  [test-matrix.md](../../test-matrix.md);
- canonical roadmap:
  [roadmap.md](../../roadmap.md); русская
  [roadmap companion](roadmap.md) покрывает только operator-facing D3 boundary
  и не заменяет английский roadmap;
- agent/contributor/internal workflow:
  [../AGENTS.md](../../../AGENTS.md), [agent-quickstart.md](../../agent-quickstart.md),
  [development-practices.md](../../development-practices.md);
- release notes and release readiness:
  [changelog.md](../../changelog.md), [release-notes-0.10.0.md](../../release-notes-0.10.0.md),
  [public-release-readiness.md](../../public-release-readiness.md).

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
`Spark`, `PyPI`, `GitHub`, `Query ID`, `Details`, `Recent`, `Running now`,
`query-doctor-web`, `cluster_type`, `analysis_facts.md` и `source_visibility`
оставляются как есть. Если термин является UI-меткой, при первом упоминании
можно дать русское пояснение рядом, но не менять саму метку.

## Текущий Статус Локализации

Поддерживаются только страницы, которые помогают пользователю или оператору
запустить Query Doctor, настроить доступы, понять safety boundary или провести
public demo. Остальные русские переводы удалены намеренно. Это снижает риск
устаревших support claims, engine-boundary drift и расхождений с английскими
контрактами.

Текущий global config `language` управляет Help, deterministic body-текстом в
Recent Finding, длинными deterministic recommendation / explanation body-текстами
Details и новыми trusted reports. Details headings, compact Recent labels,
table headers, badges и технические термины остаются английскими. Английский
остается default; русский режим использует тот же language-specific report
contract, prompt, normalizer и validator tests.
