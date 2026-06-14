# Security Model

Last reviewed: 2026-06-14

Язык: [English](../../security-model.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
описывает public security and privacy model.

## Trust boundary

Core rule:

```text
Python owns facts. LLM owns wording only.
```

LLM output остается untrusted, пока не пройдут normalization, sanitization и
deterministic validation.

## Local-first

Query Doctor запускается на машине оператора или в controlled environment.
External collection должен быть explicit, bounded, read-only, redacted и safe
by default.

## Что нельзя раскрывать

Trusted browser/report surfaces не должны раскрывать raw SQL, raw profiles,
raw metadata, raw provider JSON, local paths, subprocess output, credentials,
Kerberos ticket contents, model names, runtime internals или raw artifact
filenames. Isolated owner-only selected-case source surface - узкое browser
исключение для authorized raw SQL source и должна следовать canonical
safety-contract.

## Reporting

Security vulnerabilities должны идти через GitHub private vulnerability
reporting. Public issues не должны содержать secrets или raw production data.

Полная модель: [английская версия](../../security-model.md).
