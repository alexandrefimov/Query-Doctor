# Demo Preflight

Last reviewed: 2026-05-15

Язык: [English](../../demo-preflight.md) | Русский

Английская версия является канонической. Эта companion-страница описывает
deterministic preflight перед demo или release cleanup.

## Что проверяет preflight

`query-doctor-demo-preflight` проверяет:

- git hygiene;
- safety-sensitive changed areas;
- browser/trusted-output denylist patterns;
- focused test suggestions;
- при `--public-release` - current tracked tree и git history на private-data
  markers.

## Ограничения

Preflight не вызывает LLM, network, Cloudera Manager или Impala. Он не заменяет
human review, но ловит частые ошибки до commit/release.

Подробности: [английский demo-preflight](../../demo-preflight.md).
