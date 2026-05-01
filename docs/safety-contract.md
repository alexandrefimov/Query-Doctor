# Контракт безопасности Query Doctor

Примечание: этот файл содержит обязательные safety rules; точные phrases вроде
`Do not weaken validators` и технические термины местами намеренно оставлены на
английском для точности исполнения.

## Граница фактов

- Python отвечает за факты.
- LLM отвечает только за wording.
- Любой диагностический claim должен соответствовать `supported`,
  `not_observed` или `unknown` evidence в `analysis_facts.md`.
- Не заявляйте root cause, если `analysis_facts.md` прямо не поддерживает эту
  причину.
- Report writer не должен делать inference из raw profile text, SQL, CM JSON,
  local config или external knowledge.

## Граница collection

- Broad cluster/profile/table scanning по умолчанию запрещён.
- External collection must be explicit, bounded, read-only, redacted, and safe
  by default.
- Dry-run и preflight paths не должны собирать profile text.
- Real profile collection не должен печатать raw profiles, SQL, raw CM JSON или
  credentials.
- Первый поддержанный real Impala metadata connection path - Kerberos плюс
  `impala-shell` с уже полученным TGT от `kinit`.
- Metadata collector не вызывает `kinit`, не prompt'ит passwords, не принимает
  AD/LDAP passwords и не использует impyla/Python DB API.
- Metadata collector принимает только explicit table names и read-only
  statements `SHOW CREATE TABLE`, `SHOW TABLE STATS`, `SHOW COLUMN STATS`.
- Raw `impala-shell` stdout/stderr не печатается в terminal; collected output
  bounded, redacted и пишется только под explicit `--out`.
- Generated `impala_context.md` and `impala_context.json` are local outputs and
  must not be committed.

## Git boundary

Generated/sensitive/local outputs must not be committed:

- `cases/cm-corpus/`
- `cases/cm-corpus-hostalias/`
- `analysis_facts.md`
- generated `report*.md` / `diagnosis*.md`
- `*.partial`
- local CM config
- real CM profile material
- `impala_context.md` / `impala_context.json`

Никогда не коммитьте raw hostnames, IPs, users, emails, tokens, cookies,
passwords, Authorization headers, embedded URL credentials, local config
contents или real production profile text.

## Report validation

- Validators работают fail-closed.
- Do not weaken validators to make reports pass.
- Если report rejected, уточняйте deterministic facts, prompt wording,
  sanitizer behavior или tests.
- Новые validator rules должны иметь unsafe-rejected и safe-allowed tests.
- Deterministic normalization не должна silently hide unsupported claims.
- Safe replacements должны быть explicit, narrow и tested.
- Raw LLM output буферизуется и не должен stream'иться в stdout/stderr или
  user-facing UI.
- Final report files пишутся только после normalization, sanitization,
  validation, deterministic appendix append и final validation.
- Validation failure пишет sanitized/normalized `.partial` и сохраняет
  существующий final report.

## Report structure

LLM пишет только:

- `## Короткий вывод`
- `## Подробный разбор`

Python добавляет:

- `## Факты анализатора`

Analyzer facts appendix детерминированно строится из `analysis_facts.md`. LLM не
должен писать или reinterpret эту секцию.

`## Table Metadata Context` сейчас исключён из prompt LLM и появляется только в
Python-generated appendix.

## Claim discipline

Держите эти категории отдельно:

- backend data skew
- execution skew
- cardinality / row-estimate anomaly
- memory estimate anomaly
- write-path anomaly
- diagnostic recommendation
- proven cause

Правила:

- Backend data skew означает, что parsed backend rows/records распределены
  неравномерно. Это само по себе не доказывает stale stats, cardinality
  underestimation, hot keys или один slow host.
- Execution skew требует parsed evidence, что backend/host медленнее peers.
- Write-path anomaly можно проверять, когда он `unknown`, но нельзя заявлять как
  proven cause.
- Row/cardinality underestimation требует actual rows больше estimated rows или
  ratio выше `1`.
- Memory underestimation требует actual/peak memory больше estimated memory или
  ratio выше `1`.
- Operator/profile counter time не равен query wall-clock duration, если
  `analysis_facts.md` явно не содержит wall-clock evidence.

Если сомневаетесь, пишите, что evidence missing.
