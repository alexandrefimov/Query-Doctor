---
name: Safety concern
about: Report a possible privacy, redaction, validation, or trust-boundary issue
title: "[Safety]: "
labels: safety
assignees: ""
---

## Do Not Include Sensitive Data

Do not paste secrets, raw production SQL, raw profiles, raw metadata, raw CM
JSON, local paths, hostnames, usernames, emails, tokens, cookies, Authorization
headers, Kerberos ticket data, or private cluster details.

If GitHub security advisories are enabled for this repository, use a private
advisory for exploitable vulnerabilities.

## Summary

What safety boundary may be affected?

- [ ] Raw SQL or pasted query text exposure
- [ ] Raw profile exposure
- [ ] Raw metadata or provider JSON exposure
- [ ] Local path or artifact filename exposure
- [ ] Secret or credential exposure
- [ ] Model/runtime internals exposure
- [ ] Unsupported report claim accepted as trusted
- [ ] Unsafe optimizer draft accepted as trusted
- [ ] External collection not explicit, bounded, read-only, or redacted
- [ ] Other

## Minimal Sanitized Example

Describe the issue using synthetic placeholders only.

```text
example_db.example_table
synthetic_query_id
[local path hidden]
[secret hidden]
```

## Expected Safe Behavior

What should Query Doctor hide, reject, redact, or mark as untrusted?

## Observed Behavior

What did it do instead?

## Affected Surface

- [ ] Terminal output
- [ ] Browser UI
- [ ] Trusted report
- [ ] Optimizer output
- [ ] Generated local artifact
- [ ] Documentation
- [ ] Unknown

## Environment

- Query Doctor version or commit:
- Python version:
- Operating system:
