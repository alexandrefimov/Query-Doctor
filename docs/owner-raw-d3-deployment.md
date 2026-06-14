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

Query Doctor supports one D3 application contract:

```text
trusted auth front door -> exactly one normalized viewer header -> Query Doctor owner check
```

The front door may use the site's approved authentication mechanism, such as
OIDC/SSO, SAML, SPNEGO/Kerberos, or an enterprise gateway. Query Doctor does
not perform native OIDC, SAML, SPNEGO, Kerberos, LDAP, password, MFA, session,
logout, token-refresh, or group/RBAC authentication for `owner_raw`. Those
responsibilities stay at the trusted front door. Query Doctor accepts only the
already authenticated, already normalized simple owner value in
`viewer_identity_header`.

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

## Auth Front Door Recipes

These are deployment recipes for producing the same header contract, not
separate Query Doctor auth modes.

### OIDC/SSO At Ingress

Use this as the default D3 shape when a corporate identity provider, MFA,
device policy, logout, and session lifecycle already exist outside Query Doctor:

1. The ingress or auth proxy completes OIDC/SSO authentication and policy
   checks.
2. The ingress maps the authenticated subject to the query-owner namespace,
   preferably an Active Directory `sAMAccountName` or the same simple account
   name used by Impala `query.user`.
3. The ingress strips inbound copies of `viewer_identity_header`.
4. The ingress sets exactly one `viewer_identity_header` with that simple owner
   value.
5. Query Doctor treats the header as C2 only and still checks it against the
   selected case `query.user`.

Do not forward ID tokens, access tokens, refresh tokens, email addresses,
opaque OIDC subjects, groups, roles, or display names as the viewer header.

### SPNEGO/Kerberos At Ingress

Use this when the target environment is already Kerberos/AD-heavy:

1. The ingress or reverse proxy completes SPNEGO/Kerberos authentication.
2. The ingress derives the human account primary from the authenticated
   principal, rejecting service and host principals.
3. The ingress strips inbound copies of `viewer_identity_header`.
4. The ingress sets exactly one `viewer_identity_header` with the simple human
   owner value, for example `analyst_one`, not
   `analyst_one@EXAMPLE.COM` and not `impala/host@EXAMPLE.COM`.

Do not move SPNEGO negotiation into Query Doctor. The web process should not
receive Kerberos tickets, keytab material, or raw proxy auth state as browser
visible or trusted-report data.

### AD/LDAP

Use AD/LDAP as an identity source behind the front door only. Do not configure
Query Doctor to bind to LDAP, collect user passwords, or manage login sessions.
If the site uses LDAP-backed authentication, the proxy or identity provider
must authenticate the request and emit the same normalized simple owner header.

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
- set an already normalized simple owner user, such as an Active Directory
  `sAMAccountName` or Kerberos primary, not a UPN/email address, distinguished
  name, opaque subject, service principal, host principal, group name, role, or
  display name;
- avoid forwarding raw identity-provider tokens or authorization material to
  Query Doctor unless a separate non-secret field explicitly needs them.

Query Doctor treats missing, invalid, service-principal, and host-principal
viewer header values as unauthenticated. UPN/email-style values, distinguished
names, group/role-like values, opaque subjects, whitespace-separated display
names, and comma-separated subjects are also unauthenticated. If the HTTP
request exposes duplicate viewer header values, Query Doctor also treats the
viewer as unauthenticated. Raw source access then fails closed.

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

## Policy Simulator

Use the dev-only `scripts/owner_raw_policy_simulator.py` helper to audit the
owner-raw source allow/deny matrix without opening cases or reading SQL:

```bash
python3 scripts/owner_raw_policy_simulator.py \
  --source-visibility owner_raw \
  --host 0.0.0.0 \
  --allow-nonlocal-web-bind \
  --viewer-identity-header-configured \
  --viewer-header-value sample_owner \
  --query-user sample_owner
```

The output is raw-free JSON: it includes the allow/deny result, reason code,
route class, source visibility, source switch, viewer mode, bind scope, and
input shape booleans/counts. It does not echo viewer values, query users, header
values, SQL, case ids, paths, or secrets. The simulator is an audit aid for the
policy matrix; it is not an auth proxy, deployment check, or substitute for the
runtime checks above.

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
- No native OIDC, SAML, SPNEGO, Kerberos, LDAP, password, MFA, session, logout,
  or token lifecycle inside Query Doctor for owner-raw access.
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
