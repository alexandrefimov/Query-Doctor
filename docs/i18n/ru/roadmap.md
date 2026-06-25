# Roadmap companion

Last reviewed: 2026-06-22

Язык: [English](../../roadmap.md) | Русский

Английский [roadmap](../../roadmap.md) остается каноническим источником для
очереди работ, support boundaries и product decisions. Эта русская страница -
узкая operator-facing companion page для текущего D3 owner-raw boundary. Это
не полный перевод roadmap и не общий shared-deploy support claim.

## Текущий D3 owner-raw pull

Следующий D3 шаг - live validation gate.

Application-side contract уже описан в
[Owner Raw D3 Deployment Contract](../../owner-raw-d3-deployment.md): trusted
auth front door должен аутентифицировать viewer, удалить входящие копии
viewer header, выставить ровно один normalized simple owner value и заблокировать
direct browser access к Query Doctor web process.

Оставшееся доказательство должно проходить в реальном target deployment:
real TLS/auth, direct-network blocking, real identity claim mapping,
header stripping/replacement и raw-free audit evidence. До такой live проверки
shared/non-local `owner_raw` остается узким isolated source-surface contract,
not a general shared-deploy support claim.

## Что нельзя расширять этим шагом

- Query Doctor не реализует native auth modes: OIDC/SSO, SAML,
  SPNEGO/Kerberos, LDAP, passwords, MFA, sessions, tokens, groups или RBAC.
- Collection credential, web process account и keytab owner set не являются
  viewer authorization для raw source reveal.
- Live gate не должен публиковать raw SQL, query ids, case ids, users,
  header values, local paths, secrets или private target details.
- Retain only raw-free validation evidence: safe check names, pass/fail
  counters, safe issue categories и remediation wording.

## Где читать детали

- [owner-raw-d3-deployment.md](../../owner-raw-d3-deployment.md): canonical D3
  deployment checklist, pre-proxy readiness checklist и live front-door
  validation gate.
- [safety-contract.md](safety-contract.md): русская companion-страница для
  trust/redaction boundary.
- [configuration.md](configuration.md): `viewer_identity_header`,
  `source_visibility=owner_raw` и kill switch.
