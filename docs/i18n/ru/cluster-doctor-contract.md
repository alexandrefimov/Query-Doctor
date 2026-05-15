# Cluster Doctor Contract

Last reviewed: 2026-05-15

Язык: [English](../../cluster-doctor-contract.md) | Русский

Английская версия является канонической. Эта companion-страница кратко
пересказывает future Cluster Doctor seam.

## Статус

Cluster Doctor - future explicit user-run diagnostic seam. Это не текущий
browser workflow и не текущая поддержка generic cluster diagnosis.

## Safety boundary

- Inputs должны быть explicit, bounded, read-only, allowlisted where applicable
  и redacted.
- Browser/trusted reports не должны показывать raw logs, raw metrics, raw
  provider JSON, hostnames, principals, paths, URLs, credentials, timestamps,
  model/runtime internals или artifact filenames.
- Query Doctor может потреблять только normalized Python-owned facts with
  status, scope, coverage, confidence and limitations.

## Текущий use

CM Events CLI и normalized `cluster_event_context.json` являются внутренним
seam artifact, а не полноценным Cluster Doctor product.

Подробный контракт: [английская версия](../../cluster-doctor-contract.md).
