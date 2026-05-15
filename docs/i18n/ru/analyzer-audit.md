# Analyzer Audit

Last reviewed: 2026-05-15

Язык: [English](../../analyzer-audit.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
смысл analyzer audit без замены подробного английского источника.

## Назначение

Analyzer audit описывает риски и порядок работ в deterministic analysis layer:
profile parsing, scoring, action candidates, runtime diagnosis, metadata facts,
metrics/event facts и ограничения confidence.

## Принципы

- Analyzer owns facts; LLM owns wording only.
- Root-cause claims возможны только при прямой deterministic support.
- Missing metadata, missing metrics или low-signal profile не должны
  превращаться в уверенное объяснение.
- Runtime, event и metrics context являются supporting context, а не proof by
  themselves.

## Когда читать

Читайте [английский analyzer audit](../../analyzer-audit.md), если меняете:

- profile facts или score reasons;
- bottleneck routing;
- action candidates;
- metadata/runtime diagnosis;
- browser/report rendering of analyzer facts.
