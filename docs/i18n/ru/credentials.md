# Локальная раскладка credentials

Язык: [English](../../credentials.md) | Русский

Английская версия является канонической для публичного репозитория. Эта страница
дает русский companion-перевод для операторского использования и может
отставать от английского источника.

Query Doctor держит deploy-specific secrets вне репозитория. Рекомендуемая
локальная структура:

В этом документе `CM` означает Cloudera Manager.

```text
~/.qdcreds/
  cm-ro.env
  query-doctor.keytab
  cm-chain.pem
  llm-api.env
  query-doctor-config.json
```

Права должны быть строгими:

```bash
chmod 700 ~/.qdcreds
chmod 600 ~/.qdcreds/cm-ro.env
chmod 600 ~/.qdcreds/query-doctor.keytab
chmod 600 ~/.qdcreds/cm-chain.pem
chmod 600 ~/.qdcreds/llm-api.env
chmod 600 ~/.qdcreds/query-doctor-config.json
```

`cm-ro.env` должен содержать только Cloudera Manager auth assignments:

```bash
CM_USERNAME=...
CM_PASSWORD=...
```

`CM_TOKEN` можно использовать вместо `CM_PASSWORD`, если целевой deployment
поддерживает token authentication. Не кладите passwords, tokens, keytabs,
ticket contents или Authorization headers в `query-doctor-config.json` или
любой committed file.

Kerberos identity отделен от CM credentials. Local wrapper выводит principal из
configured keytab. `QD_KRB5_PRINCIPAL` может переопределить это для one-off
runs, но его нужно export-ить в shell environment, а не хранить в `cm-ro.env`.
Если wrapper выводит principal из keytab, он использует это значение только для
`kinit` и не экспортирует его как fixed query owner.

Когда `scripts/query-doctor-web-local` запускает web UI, он передает resolved
keytab path локальному процессу через `QD_KEYTAB`. Web UI может прочитать simple
account names из `klist -k` или `ktutil` output. Simple accounts сортируются по
алфавиту для Username filter, а первый account становится owner default для
`owner_raw`. Keytab path, full Kerberos principals, ticket contents и keytab
contents не рендерятся в browser.

Для внешнего OpenAI-compatible LLM route заведите local untracked env file,
например `~/.qdcreds/llm-api.env`:

```bash
QD_LLM_API_BASE_URL=https://llm-gateway.example.com
QD_LLM_API_KEY=...
```

URL должен быть base URL вашего совместимого LLM gateway.
Organization-specific endpoints и tokens держите только в local untracked env
files. Не кладите LLM API tokens в `query-doctor-config.json`.

Report и optimizer routes могут иметь разные non-secret model settings в
`query-doctor-config.json`, а tokens при необходимости задаются route-specific
env variables:

```bash
QD_REPORT_LLM_API_KEY=...
QD_OPTIMIZER_LLM_API_KEY=...
```

Для альтернативного env file задайте `QD_LLM_ENV=/path/to/llm-api.env`. Для
OpenAI-compatible gateways используйте `llm-api.env` с переменными
`QD_LLM_*`.

Локальный Query Doctor config хранит только non-secret settings и file
references. Для новых manual runs используйте
`~/.qdcreds/query-doctor-config.json`. Repository-local
`query-doctor-config.json` остается поддержанным для explicit или
current-directory overrides, а legacy ignored `.query-doctor-cm.local.json`
работает как fallback. Полный английский reference по полям и discovery order:
[configuration.md](../../configuration.md).

```json
{
  "cm_url": "https://cm.example.net:7183/",
  "cluster": "example_cluster",
  "service": "impala",
  "ca_bundle": "~/.qdcreds/cm-chain.pem",
  "metadata_coordinator": "impala-coordinator.example.net:21050"
}
```

Для запуска web UI используйте local bootstrap wrapper:

```bash
scripts/query-doctor-web-local
```

Чтобы запустить тот же local UI в deterministic Python-only mode для report и
optimizer actions, используйте любой из вариантов:

```bash
scripts/query-doctor-web-local --no-llm
scripts/query-doctor-web-local-no-llm
```

`host` и `port` могут жить в local config, поэтому wrapper не требует
дополнительных startup arguments для обычного local port. Если CM credentials
уже экспортированы и Kerberos ticket уже существует, сервер можно запустить
напрямую:

```bash
query-doctor-web
```

Wrapper делает следующее:

- загружает из `~/.qdcreds/cm-ro.env` только CM auth assignments;
- загружает из `~/.qdcreds/llm-api.env` только allowlisted LLM assignments,
  если файл существует;
- при необходимости преобразует legacy `CM_USER` в `CM_USERNAME`;
- пробрасывает дополнительные flags `query-doctor-web`, включая `--no-llm`;
- создает или обновляет Kerberos cache из `~/.qdcreds/query-doctor.keytab`;
- запускает `query-doctor-web` с `~/.qdcreds/query-doctor-config.json`,
  repository-local config или legacy ignored local config.

Сбору metadata нужен драйвер HiveServer2, он живёт за extra `impala`. Поставьте
его один раз в окружение, где запускается web UI:

```bash
python -m pip install -e ".[impala]"
```

pykerberos собирается из исходников, поэтому нужны заголовки Kerberos
(`libkrb5-dev` в Debian/Ubuntu, `krb5-devel` в RHEL).

Поддержанные wrapper overrides:

- `QD_CREDS_DIR`: directory с credentials, default `~/.qdcreds`;
- `QD_CM_ENV`: CM env file, default `$QD_CREDS_DIR/cm-ro.env`;
- `QD_LLM_ENV`: LLM env file, default `$QD_CREDS_DIR/llm-api.env`;
- `QD_KEYTAB`: path к Kerberos keytab, default `$QD_CREDS_DIR/query-doctor.keytab`;
- `QD_KRB5_PRINCIPAL`: one-off override для Kerberos principal;
- `KRB5CCNAME`: Kerberos credential cache, default
  `FILE:/tmp/krb5cc_query_doctor`;
- `QD_CONFIG`: override для local Query Doctor config. По умолчанию wrapper
  предпочитает `$QD_CREDS_DIR/query-doctor-config.json`, затем repository-local
  `query-doctor-config.json`, затем `.query-doctor-cm.local.json`;
- `QD_SKIP_KINIT=1`: использовать существующий Kerberos cache без запуска
  `kinit`.

Все credentials остаются локальными для OS account. Generated cases, profiles,
reports и local configs остаются ignored by Git.
