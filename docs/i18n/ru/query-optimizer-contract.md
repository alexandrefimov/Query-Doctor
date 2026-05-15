# Query Optimizer Contract

Last reviewed: 2026-05-15

Язык: [English](../../query-optimizer-contract.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
главные trust rules для optimizer.

## Основные правила

- Никогда не выполнять user SQL или optimizer draft SQL.
- Pasted SQL не должен echo back в browser после submit.
- Trusted SQL draft возможен только через Python-owned recipe,
  deterministic execution и strict validation.
- Unsupported или high-risk cases должны возвращать trusted no-rewrite или
  recommendations-only guidance.
- Raw LLM output остается untrusted до deterministic validation.

## Surfaces

- Query Optimizer: pasted SQL, read-only analyze.
- Details-page Query LLM optimizer: explicit action на server-owned analyzed
  case.

## Validation

Validation binds source hash, analyzer facts hash, output hash, marker schema,
source scope and risk mode. Stale или mismatched artifacts are untrusted.

Полный контракт: [английская версия](../../query-optimizer-contract.md).
