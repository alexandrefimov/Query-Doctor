# Owner Raw D3 Deployment Contract

Last reviewed: 2026-06-14

This document defines the only supported shared/non-local deployment shape for
`source_visibility=owner_raw`. It is a deployment contract, not an invitation to
turn Query Doctor into a general multi-tenant service.

## Scope

`owner_raw` has two separate identities:

- C1 collection credential: the local process, Kerberos ticket, keytab, or
  service account used to collect bounded Recent/Running cases.
- C2 viewer identity: the authenticated human viewer allowed to open the
  isolated owner-only original source page for a selected case.

Raw source reveal is authorized only by C2 and `query.user`. It must never be
authorized by C1, by the keytab owner set, or by the account running the web
process.

D3 means Query Doctor is reachable over a non-local bind only behind a trusted
auth front door. Local-first mode may intentionally map collectable owners to
the local viewer. D3 must not do that.

## Reference Shape

Use this order:

1. Client connects over TLS to a trusted ingress or reverse proxy.
2. The ingress authenticates the request with the site-approved identity
   provider.
3. The ingress strips any inbound copy of the configured viewer header.
4. The ingress sets exactly one viewer header containing the normalized simple
   owner user.
5. Query Doctor receives the request and derives C2 from that header.
6. Query Doctor compares C2 to the selected case `query.user` before showing
   the isolated raw source page.

In a Kubernetes-style deployment, the pod keytab or service account remains C1
only. It may allow collection across configured owner users, but it must not
grant raw reveal to viewers.

## Required Configuration

For shared `owner_raw`, configure all of these:

```json
{
  "host": "0.0.0.0",
  "source_visibility": "owner_raw",
  "viewer_identity_header": "X-Query-Doctor-Viewer",
  "owner_raw_source_enabled": true
}
```

Start the web process only with an explicit non-local bind review:

```bash
query-doctor-web --allow-nonlocal-web-bind
```

The header name may be provided in local config or with
`--viewer-identity-header`. Use `--disable-owner-raw-source`, or set
`owner_raw_source_enabled=false`, as the immediate kill switch for the isolated
original source page.

## Header Rules

The proxy or ingress must:

- authenticate every request before forwarding it;
- remove inbound copies of `viewer_identity_header`;
- set one trusted viewer header after authentication;
- set a simple owner user, not an email address, opaque subject, service
  principal, host principal, group name, role, or display name;
- avoid forwarding raw identity-provider tokens or authorization material to
  Query Doctor unless a separate non-secret field explicitly needs them.

Query Doctor treats missing, invalid, service-principal, and host-principal
viewer header values as unauthenticated. If the HTTP request exposes duplicate
viewer header values, Query Doctor also treats the viewer as unauthenticated.
Raw source access then fails closed.

## Runtime Checks

Before enabling non-local `owner_raw`, verify:

- `query-doctor-web` refuses to start without authenticated viewer identity
  configuration.
- Requests without the viewer header receive no owner-raw source link and no
  source page.
- Requests with duplicate viewer header values receive no owner-raw source link
  and no source page, even if one value matches the query owner.
- Requests with a mismatched viewer header receive no owner-raw source link and
  no source page.
- Requests with a matching viewer header can open only the isolated source page
  for that viewer's own selected case.
- `owner_raw_source_enabled=false` hides the source link and blocks the source
  page without changing collection owner filters or optimizer policy.
- Owner-raw audit lines appear for source-page attempts and include only
  request id, route source, HTTP status, reason code, viewer mode/source, and
  switch state.
- Audit lines do not contain raw SQL, query ids, case ids, query users, local
  paths, header values, secrets, model names, runtime internals, or raw artifact
  filenames.

## Operator Response

If the auth proxy, identity mapping, audit pipeline, or ownership mapping is in
doubt:

1. Disable the original source page with `--disable-owner-raw-source` or
   `owner_raw_source_enabled=false`.
2. Keep `source_visibility=owner_raw` only if the collection owner filter is
   still needed and safe for the local process.
3. Switch to `source_visibility=safe` if owner-scoped collection is also in
   doubt.
4. Review reason-coded audit lines without using them as raw evidence.

Do not use a silent downgrade for a broken D3 auth front door. A missing or
invalid viewer identity must fail closed.

## Non-Goals

- No admin role bypasses owner raw access.
- No group, role, or delegated-subject expansion is implied by this contract.
- No raw source appears in Details, Recent tables, trusted reports, report
  downloads, optimizer prompts, handoff exports, or audit logs.
- No public demo should run with owner-raw collection or raw source reveal.
- No deployment-specific hostnames, cluster ids, keytab paths, or identity
  provider secrets belong in committed docs.

## Related Contracts

- [safety-contract.md](safety-contract.md): canonical trust and redaction
  contract.
- [configuration.md](configuration.md): `source_visibility`,
  `viewer_identity_header`, and `owner_raw_source_enabled` reference.
- [../README.md](../README.md): public safety summary and support boundary.
