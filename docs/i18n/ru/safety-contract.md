# Контракт безопасности Query Doctor

Last reviewed: 2026-05-19

Язык: [English](../../safety-contract.md) | Русский

Английская версия является канонической для публичного репозитория. Эта
страница - русская companion-версия для операторов и разработчиков. Имена
файлов, команд, секций отчетов и проверяемые идентификаторы оставлены на
английском там, где они являются частью интерфейса или тестового контракта.

## Граница фактов

- Python/analyzer отвечает за факты.
- LLM отвечает только за формулировку.
- Любое диагностическое утверждение должно соответствовать evidence в
  `analysis_facts.md`: `supported`, `not_observed` или `unknown`.
- Нельзя заявлять root cause, если `analysis_facts.md` прямо не поддерживает
  такую причину.
- Report writer не должен делать выводы из raw profile text, SQL, raw Cloudera
  Manager JSON, local config или external knowledge.

## Граница сбора данных

- Широкое cluster/profile/table scanning по умолчанию запрещено.
- Любой внешний сбор должен быть explicit, bounded, read-only, redacted и safe
  by default.
- Dry-run и preflight paths не должны собирать profile text.
- Real profile collection не должен печатать raw profiles, SQL, raw Cloudera
  Manager JSON или credentials.
- Первый поддержанный путь Impala metadata connection - Kerberos плюс
  `impala-shell` с уже полученным TGT от `kinit`.
- Metadata collector не вызывает `kinit`, не запрашивает passwords, не
  принимает AD/LDAP passwords и не использует impyla/Python DB API.
- Metadata collector принимает только bounded table references из explicit CLI
  input или Python-owned selected-case extraction. Он выполняет только
  read-only statements: `SHOW CREATE TABLE`, `SHOW TABLE STATS`,
  `SHOW COLUMN STATS`.
- Raw `impala-shell` stdout/stderr не печатается в terminal; collected output
  bounded, redacted и пишется только в explicit `--out`.
- Generated `impala_context.md` и `impala_context.json` являются local outputs
  и не должны попадать в commit.

## Git boundary

Generated, sensitive и local outputs не должны попадать в commit:

- `cases/cm-corpus/`;
- `cases/cm-corpus-hostalias/`;
- `analysis_facts.md`;
- generated `report*.md` / `diagnosis*.md`;
- `*.partial`;
- local Cloudera Manager config;
- real Cloudera Manager profile material;
- `query_metadata.json`;
- `impala_context.md` / `impala_context.json`.

Нельзя коммитить raw hostnames, IPs, users, emails, tokens, cookies, passwords,
Authorization headers, embedded URL credentials, local config contents или real
production profile text.

## Report validation

- Validators работают fail-closed.
- Нельзя ослаблять validators только ради того, чтобы report проходил проверку.
- Если report rejected, исправляйте deterministic facts, prompt wording,
  sanitizer behavior или tests.
- Новые validator rules должны иметь unsafe-rejected и safe-allowed tests.
- Deterministic normalization не должна незаметно прятать unsupported claims.
- Safe replacements должны быть explicit, narrow и covered tests.
- Raw LLM output буферизуется и не должен stream'иться в stdout/stderr или
  user-facing UI.
- Final report files пишутся только после normalization, sanitization,
  narrative validation, appendix append и final validation.
- Trusted final reports не должны содержать raw SQL-like text, SQL fenced code
  blocks, pasted query fragments или raw metadata command snippets, включая
  table-specific `SHOW CREATE TABLE`, `SHOW TABLE STATS`, `SHOW COLUMN STATS`.
- Partial или invalid report output остается untrusted и не должен
  отображаться как final diagnosis.

## Browser display boundary

- Browser-visible UI не должен показывать raw SQL, raw profiles, raw metadata,
  stdout/stderr, local paths, `case_dir`, credentials, secret values, Kerberos
  ticket contents, metadata connection details, model names или Ollama
  internals.
- Любой dynamic browser-visible text должен проходить shared browser display
  redaction policy перед rendering.
- Web Recent scan не должен автоматически запускать LLM reports или optimizer
  jobs; validated report generation и Query LLM optimizer generation являются
  explicit actions для одного selected case.
- Details-page Query LLM optimizer должен показывать только validated read-only
  draft, safe recommendations/no-rewrite guidance, validation-failure-only
  external rewrite validation categories и safe status fields.
- Partial drafts, raw source SQL и externally pasted SQL должны оставаться
  скрытыми.

## Future Cluster Doctor

- Cluster Doctor - будущий explicit user-run seam для диагностики
  cluster/service/workload, а не текущая поддержка продукта.
- Query Doctor может использовать будущий Cluster Doctor output только как
  normalized Python-owned facts со status, scope, coverage, confidence,
  limitations и deterministic correlation.
- Cluster Doctor должен оставаться read-only: он может рекомендовать checks или
  operational follow-up, но не должен выполнять service control, configuration
  changes, data changes или remediation automation.
- Все current и future providers, включая Cloudera Manager, direct Impala,
  Prometheus, prepared metric stores и log/event stores, должны быть explicit,
  bounded, read-only, allowlisted where applicable, redacted и tested до того,
  как их факты попадут в reports или browser UI.
- Future log/event support должен потреблять только prepared event summaries.
  Raw log lines, stack traces, raw alert text, principals, usernames, query text
  и raw parser payloads не должны попадать в browser-visible UI, trusted
  reports или LLM prompts.
- CM Events MVP CLI read-only и bounded. Он может печатать normalized event
  counts, severities и signal ids, но не raw CM event payloads, raw log lines,
  event ids, hostnames, principals, paths, query text или raw provider JSON.
- `cluster_event_context.json` - schema-versioned internal Cluster Doctor seam
  artifact, построенный только из normalized CM event summaries. Он должен
  whitelist exported fields и исключать raw provider payloads, raw log lines,
  event ids, hostnames, principals, paths, query text, URLs, local paths,
  secrets, command output, model/runtime names и raw artifact filenames.
- `cluster_context.json` - schema-versioned aggregate Cluster Doctor seam
  artifact, построенный только из safe context artifacts. Он может включать
  source status, product status, normalized signal counts, limitations и next
  checks, но не raw provider payloads или browser-forbidden details.
- Raw metric series, raw logs, raw provider JSON, raw alert text, raw
  timestamps, hostnames, entity IDs, URLs, paths, credentials, artifact names,
  command-stream details, model names и runtime internals не должны
  отображаться в trusted reports или browser-visible UI.
- Cluster-wide root-cause или incident claims требуют отдельного deterministic
  claim registry, fixtures, report validation и browser safety tests.

## Report structure

LLM пишет user-facing narrative sections:

- `## Краткий вывод`;
- `## Практические рекомендации`;
- `## Подробный разбор`;
- `## Админские проверки`.

Python добавляет deterministic appendix:

- `## Факты анализатора`.

LLM не должен писать appendix section. Report validator должен отклонять raw
SQL-like output, unsafe recommendations, unsupported root-cause claims и
browser-forbidden details.
