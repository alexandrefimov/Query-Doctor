# Security Policy

Query Doctor handles operational diagnostics and may run near sensitive query,
profile, metadata, and cluster-management systems. Treat all raw collected data
as sensitive unless it has passed the project redaction and trust boundaries.

## Supported Status

This repository is still being prepared for public release. Until a formal
release policy is added, security-sensitive reports should be handled privately
with the repository maintainers.

Preferred private reporting path, when available, is GitHub Security Advisories
for this repository. If advisories are not enabled yet, contact the maintainer
privately and share only sanitized reproduction details until a private channel
is confirmed.

## Reporting

Do not file public issues containing:

- raw SQL or query text;
- raw Impala profiles;
- raw Cloudera Manager JSON;
- raw metadata output;
- hostnames, IP addresses, usernames, emails, principals, tokens, cookies,
  passwords, Authorization headers, embedded URL credentials, local config
  contents, or production profile text;
- local paths or generated artifact contents from real environments.

When reporting a security issue, include a minimal sanitized reproduction,
affected command or workflow, expected behavior, actual behavior, and why the
output crosses a trust boundary.

For public issues, describe the affected boundary and use synthetic placeholders
only. Do not attach real generated artifacts from production environments.

## Security Boundaries

Important project invariants:

- Python/analyzer facts are the only trusted diagnostic evidence.
- Raw LLM output is untrusted unless validated.
- Browser-visible UI and trusted reports must not expose raw operational data.
- External collection must be explicit, bounded, read-only, redacted, and safe
  by default.
- Query Optimizer must not execute pasted SQL.
- Metadata collection must stay read-only and allowlisted.

See [docs/safety-contract.md](docs/safety-contract.md) for the complete
contract.
