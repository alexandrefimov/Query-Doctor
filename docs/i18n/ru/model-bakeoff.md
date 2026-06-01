# Model Route Evaluation Protocol

Язык: [English](../../model-bakeoff.md) | Русский

Английская версия является канонической. Эта страница кратко описывает
публичный protocol для проверки model routes без публикации локальных
bake-off результатов.

## Что остается публичным

В committed docs можно хранить:

- route-specific scoring definitions;
- strict validation rules;
- placeholder command shapes;
- raw-free artifact schema;
- правила изменения defaults.

Не публикуйте:

- конкретные локальные rankings, pass rates, latency или failure examples;
- реальные или реальные на вид case IDs;
- generated case roots, batch-summary paths и output directories;
- provider endpoints, gateway names, credentials и workstation setup;
- raw prompts, raw completions и untrusted model output.

## Контракт

- Python/analyzer owns facts.
- LLM owns wording only.
- Trusted SQL drafts требуют Python-owned recipe, deterministic execution и
  strict validation.
- Browser-visible UI и trusted reports не должны показывать model names, raw
  SQL, raw profiles, raw metadata, local paths, process logs или raw
  artifact filenames.

## Как сравнивать routes

Optimizer route и report-writer route сравниваются отдельно. Report pass-rate
не доказывает SQL rewrite quality.

Для optimizer route смотрите trusted outcome rate, trusted SQL draft rate,
trusted no-rewrite rate, trusted recommendations rate и partial untrusted rate.
Model-comparable summary должен исключать deterministic recipe/no-rewrite
cases, чтобы не завышать model quality.

Для report-writer route используйте deterministic analyzer facts file, strict
validation, несколько повторов на case/model pair и только trusted-pass
результаты для default decisions.

## Где держать детали

Локальные case lists, output directories, provider notes, latency/pass-rate
таблицы и полные выводы сравнения храните в local exclude-only notes. В публичный
changelog попадает только короткое решение, если изменился user-facing default
или safety contract.
