# Local Credentials Layout

Language: English | [Russian](i18n/ru/credentials.md)

Query Doctor keeps deploy-specific secrets outside the repository. In this
guide, `CM` means Cloudera Manager. The recommended local layout is:

```text
~/.qdcreds/
  cm-ro.env
  query-doctor.keytab
  cm-chain.pem
  llm-api.env
  query-doctor-config.json
```

Permissions should be strict:

```bash
chmod 700 ~/.qdcreds
chmod 600 ~/.qdcreds/cm-ro.env
chmod 600 ~/.qdcreds/query-doctor.keytab
chmod 600 ~/.qdcreds/cm-chain.pem
chmod 600 ~/.qdcreds/llm-api.env
chmod 600 ~/.qdcreds/query-doctor-config.json
```

`cm-ro.env` should contain only Cloudera Manager auth assignments:

```bash
CM_USERNAME=...
CM_PASSWORD=...
```

`CM_TOKEN` may be used instead of `CM_PASSWORD` when the target deployment
supports token authentication. Do not put passwords, tokens, keytabs, ticket
contents or Authorization headers into `query-doctor-config.json` or any
committed file.

Kerberos identity is separate from CM credentials. The local wrapper infers the
principal from the configured keytab. `QD_KRB5_PRINCIPAL` can override that for
one-off runs, but it should be exported in the shell environment rather than
stored in `cm-ro.env`. When the wrapper infers a principal from the keytab, it
uses that value only for `kinit`; it does not export it as a fixed query owner.

When `scripts/query-doctor-web-local` starts the web UI, it also exposes the
resolved keytab path to the local process through `QD_KEYTAB`. The web UI may
read simple account names from `klist -k` or `ktutil` output. Simple accounts
are sorted alphabetically for the Username filter, and the first account becomes
the owner default for `owner_raw`. It does not render the keytab path, full
Kerberos principals, ticket contents, or keytab contents.

For an external OpenAI-compatible LLM route, use a local untracked env file such
as `~/.qdcreds/llm-api.env`:

```bash
QD_LLM_API_BASE_URL=https://llm-gateway.example.com
QD_LLM_API_KEY=...
```

The URL is the base URL of your own compatible LLM gateway. Keep
organization-specific endpoints and tokens only in local untracked env files.
Do not put LLM API tokens into `query-doctor-config.json`.

Report and optimizer routes can use different non-secret model settings in
`query-doctor-config.json`, and route-specific env tokens when needed:

```bash
QD_REPORT_LLM_API_KEY=...
QD_OPTIMIZER_LLM_API_KEY=...
```

Set `QD_LLM_ENV=/path/to/llm-api.env` for an alternate env file. Use
`llm-api.env` with `QD_LLM_*` variables for OpenAI-compatible gateways.

The local Query Doctor config stores non-secret settings and file references.
For new manual runs, use `~/.qdcreds/query-doctor-config.json`. Repository-local
`query-doctor-config.json` remains supported for explicit or current-directory
overrides, and legacy ignored `.query-doctor-cm.local.json` still works as a
fallback.
See [configuration.md](configuration.md) for the full field reference and
discovery order.

```json
{
  "cm_url": "https://cm.example.net:7183/",
  "cluster": "example_cluster",
  "service": "impala",
  "ca_bundle": "~/.qdcreds/cm-chain.pem",
  "metadata_coordinator": "impala-coordinator.example.net:21000",
  "metadata_impala_shell": ".venv-impala-shell/bin/impala-shell"
}
```

Use the local bootstrap wrapper to start the web UI:

```bash
scripts/query-doctor-web-local
```

To start the same local UI with report and optimizer actions forced into
deterministic Python-only mode, use either form:

```bash
scripts/query-doctor-web-local --no-llm
scripts/query-doctor-web-local-no-llm
```

`host` and `port` can live in the local config, so the wrapper does not need
extra startup arguments for the normal local port. If Cloudera Manager (CM)
credentials are already exported and a Kerberos ticket already exists, the
server can also be started directly:

```bash
query-doctor-web
```

The wrapper:

- loads only CM auth assignments from `~/.qdcreds/cm-ro.env`;
- loads only whitelisted LLM assignments from `~/.qdcreds/llm-api.env` when it
  exists;
- maps legacy `CM_USER` to `CM_USERNAME` if needed;
- bootstraps `.venv-impala-shell/bin/impala-shell` when it is missing;
- creates or refreshes the Kerberos cache from `~/.qdcreds/query-doctor.keytab`;
- starts `query-doctor-web` with `~/.qdcreds/query-doctor-config.json`, a
  repository-local config, or the legacy ignored local config.
- forwards any extra `query-doctor-web` flags, including `--no-llm`.

The impala-shell bootstrap is intentionally isolated from the main Python
runtime because CDH6-compatible `impala_shell` has legacy dependency
constraints:

```bash
scripts/bootstrap-impala-shell
```

Supported wrapper overrides:

- `QD_CREDS_DIR`: credentials directory, default `~/.qdcreds`;
- `QD_CM_ENV`: CM env file, default `$QD_CREDS_DIR/cm-ro.env`;
- `QD_LLM_ENV`: LLM env file, default `$QD_CREDS_DIR/llm-api.env`;
- `QD_KEYTAB`: Kerberos keytab path, default `$QD_CREDS_DIR/query-doctor.keytab`;
- `QD_KRB5_PRINCIPAL`: one-off Kerberos principal override;
- `QD_IMPALA_SHELL`: expected impala-shell executable for bootstrap checks,
  default `.venv-impala-shell/bin/impala-shell`;
- `QD_IMPALA_SHELL_VENV`: bootstrap venv directory, default
  `.venv-impala-shell`;
- `QD_BOOTSTRAP_IMPALA_SHELL=0`: do not auto-bootstrap missing impala-shell;
- `KRB5CCNAME`: Kerberos credential cache, default
  `FILE:/tmp/krb5cc_query_doctor`;
- `QD_CONFIG`: local Query Doctor config override. By default the wrapper
  prefers `$QD_CREDS_DIR/query-doctor-config.json`, then repository-local
  `query-doctor-config.json`, then `.query-doctor-cm.local.json`;
- `QD_SKIP_KINIT=1`: reuse an existing Kerberos cache without running `kinit`.

All credentials remain local to the OS account. Generated cases, profiles,
reports and local configs remain ignored by Git.
