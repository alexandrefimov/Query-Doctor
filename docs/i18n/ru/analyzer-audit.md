# Analyzer Audit

Last reviewed: 2026-06-01

Язык: [English](../../analyzer-audit.md) | Русский

Английская версия является канонической. Эта companion-страница фиксирует
смысл public-safe analyzer audit без private case identifiers и local smoke
history.

## Назначение

Analyzer audit описывает durable risks в deterministic analysis layer: profile
parsing, scoring, action candidates, runtime diagnosis, metadata facts,
metrics/event facts и confidence limits.

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
