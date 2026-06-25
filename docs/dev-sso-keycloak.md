# Dev Keycloak SSO Smoke

Last reviewed: 2026-06-24

This is a developer-only SSO front-door smoke for Query Doctor. It exists to
unblock local OIDC wiring and owner-viewer header validation while a real site
Keycloak or ingress owner is unavailable. It is not production SSO support and
does not change the Query Doctor application contract:

```text
trusted auth front door -> exactly one normalized viewer header -> Query Doctor owner check
```

Query Doctor still does not implement native OIDC, SAML, SPNEGO/Kerberos,
LDAP, passwords, MFA, session, logout, token lifecycle, groups, roles, or RBAC.
Those stay at the trusted front door. Query Doctor only receives the already
authenticated, already normalized viewer user through `viewer_identity_header`.

## What The Harness Starts

`dev/sso/compose.yaml` starts three services:

- `keycloak`: local development Keycloak realm import at
  `http://query-doctor-sso.localhost:18080`.
- `oauth2-proxy`: OIDC front door at
  `http://query-doctor-sso.localhost:4180`.
- `query-doctor`: Query Doctor web process inside the compose network only.

The browser can reach Keycloak and oauth2-proxy. The Query Doctor upstream port
is not published to the host. The Query Doctor container generates a synthetic
demo pack in `/tmp/query-doctor-dev-sso-demo` at container startup, then opens
that raw-free `batch_summary.json` with the dev Query Doctor config:

```json
{
  "source_visibility": "owner_raw",
  "viewer_identity_header": "X-Forwarded-Preferred-Username",
  "owner_raw_source_enabled": false,
  "no_llm": true
}
```

`oauth2-proxy` is the trusted front door for this local smoke. It strips
inbound `X-Forwarded-*` auth headers, sets its own
`X-Forwarded-Preferred-Username` header from the Keycloak OIDC session, and
does not forward access tokens, ID tokens, Basic auth, or Authorization bearer
headers upstream.

The original source page remains disabled by default through
`owner_raw_source_enabled=false`. Turn it on only after validating the front
door and only in a local throwaway smoke.

## Run

From the repository root:

```bash
docker compose -f dev/sso/compose.yaml up --pull missing
```

Open `http://query-doctor-sso.localhost:4180`. The imported local realm has two
synthetic users:

| User | Login secret |
| --- | --- |
| `analyst_one` | `analyst-one-dev-login` |
| `other_owner` | `other-owner-dev-login` |

The Keycloak admin console is at
`http://query-doctor-sso.localhost:18080/admin`. The default admin credentials
are synthetic and local to this compose project:

```text
admin / dev-only-admin
```

To change ports or dev secrets without editing tracked files:

```bash
cp dev/sso/env.example dev/sso/.env
docker compose --env-file dev/sso/.env -f dev/sso/compose.yaml up
```

`dev/sso/.env` is ignored by git. Keep any real IdP hostnames, realm names,
client secrets, certificates, proxy logs, screenshots, and local validation
evidence out of committed files.

## Validate The Contract

Before treating the local smoke as useful, run the application-side raw-free
checks:

```bash
python3 scripts/owner_raw_front_door_smoke.py --compact
python3 scripts/owner_raw_policy_simulator.py \
  --source-visibility owner_raw \
  --host 0.0.0.0 \
  --allow-nonlocal-web-bind \
  --viewer-identity-header-configured \
  --viewer-header-value sample_owner \
  --query-user sample_owner \
  --fail-on-deny
docker compose -f dev/sso/compose.yaml config
```

With the compose stack running, run the dev-only live smoke:

```bash
python3 scripts/dev_sso_keycloak_smoke.py --compact
```

The live smoke verifies that oauth2-proxy redirects unauthenticated requests to
Keycloak, Keycloak discovery is reachable, the Query Doctor upstream port is
not reachable from the host, and the imported synthetic login lands back on
Query Doctor. Its output is raw-free: it prints only pass/fail state, safe
status classes, safe target labels, and safe error categories, never URLs,
cookies, tokens, usernames, login secrets, `code`, or `state` values.

After a real proxy or ingress exists, use the live review gate from
[owner-raw-d3-deployment.md](owner-raw-d3-deployment.md).
Do not use this dev compose file as production evidence. It does not prove
corporate TLS, MFA, device policy, identity lifecycle, audit transport,
direct-network blocking in the target environment, or production Keycloak
operations.

## Production Handoff

When the real SSO owner is available, replace only the front door:

1. Keep Query Doctor configured with one `viewer_identity_header`.
2. Strip inbound copies of that header at the ingress or proxy.
3. Map the authenticated SSO subject to the same simple owner namespace as
   Impala `query.user`, such as `sAMAccountName` or a Kerberos human primary.
4. Forward exactly one normalized simple owner value to Query Doctor.
5. Do not forward OIDC tokens, SAML assertions, Kerberos tickets, cookies,
   groups, roles, display names, emails, UPNs, or opaque subjects as Query
   Doctor authorization inputs.
6. Keep direct browser access to the Query Doctor upstream blocked.
7. Keep `owner_raw_source_enabled=false` until the live front-door validation
   gate passes.

Record only raw-free pass/fail evidence through the live review summary gate.
