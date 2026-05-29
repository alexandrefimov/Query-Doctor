# Query Optimizer Contract

Last reviewed: 2026-05-28

Язык: [English](../../query-optimizer-contract.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
главные trust rules для optimizer.

## Основные правила

- Никогда не выполнять user SQL или optimizer draft SQL.
- Pasted SQL не должен echo back в browser после submit.
- Trusted SQL draft возможен только через Python-owned recipe,
  deterministic execution и strict validation.
- `cte_union_branch_filter_pushdown` теперь является narrow trusted recipe:
  final `WHERE` predicates могут копироваться внутрь branches одного
  `UNION ALL` CTE только когда Python доказывает simple branch projection
  mapping и validator сохраняет branch count/order, filters, literals,
  physical tables и final SELECT shape.
- `single_derived_table_projection_alias_predicate_pushdown` является narrow
  trusted recipe для одного top-level derived table: outer `WHERE` predicate
  можно скопировать внутрь derived body только через simple projection alias
  вида `source_col AS output_col`, с сохранением outer filter и strict
  validation.
- Unsupported или high-risk cases должны возвращать trusted no-rewrite или
  recommendations-only guidance.
- LLM может формулировать wording и guidance, но не является trusted SQL
  writer.
- Raw LLM output остается untrusted.

## Surfaces

- Query Optimizer: pasted SQL, read-only analyze.
- Details-page Query LLM optimizer: explicit action на server-owned analyzed
  case.

## Validation

Validation binds source hash, analyzer facts hash, output hash, marker schema,
source scope and risk mode. Stale или mismatched artifacts are untrusted.

Полный контракт: [английская версия](../../query-optimizer-contract.md).
