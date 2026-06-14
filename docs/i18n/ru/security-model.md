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
safety-contract. Isolated owner-raw source surface остается за kill switch и
пишет только reason-coded raw-free audit lines.

## Owner Raw Shared Access

Shared/non-local `owner_raw` использует один application contract:

```text
trusted auth front door -> exactly one normalized viewer header -> Query Doctor owner check
```

OIDC/SSO, SAML, SPNEGO/Kerberos, LDAP/AD, MFA, session, logout, token и
group/RBAC handling остаются на trusted ingress/proxy/front door. Query Doctor
не реализует эти auth-механизмы нативно для owner-raw access. Он принимает
только уже authenticated и already normalized simple owner value из
`viewer_identity_header`, а затем сравнивает его с `query.user` выбранного
case. Collection credential, web process account и keytab owner set не
являются viewer authorization и не могут разрешать raw reveal.

## Reporting

Security vulnerabilities должны идти через GitHub private vulnerability
reporting. Public issues не должны содержать secrets или raw production data.

Полная модель: [английская версия](../../security-model.md).
