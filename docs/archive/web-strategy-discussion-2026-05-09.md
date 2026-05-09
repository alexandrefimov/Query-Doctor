# Web UI & Deployment Strategy — Обсуждение

Дата: 2026-05-09
Статус: рабочие заметки из обсуждения с Claude. Не утверждённый план.
Цель: дать Codex базу для анализа и добавления релевантных пунктов в roadmap.

---

## 0. Контекст и охват

Обсуждали четыре связанных вопроса:

1. Стоит ли переписывать текущий SSR web UI на React.
2. Что нужно докрутить, если репозиторий становится публичным и продуктом начнут пользоваться компании.
3. Какая модель развертывания перспективнее: local-first (`pip install`) или централизованный сервис в k8s с auth.
4. Имеет ли смысл делать multi-tenant платной фичей.
5. Как команда из 5-10 дата-инженеров реально пользуется продуктом в local-first модели.

Все рекомендации ниже — обсуждение, не утверждённое решение. Codex должен сам отфильтровать, что попадает в roadmap, что — нет, и в каком порядке.

---

## 1. Текущее состояние web UI

### Findings

- ~12k строк в `query_doctor/web/`. SSR через `http.server.ThreadingHTTPServer`, HTML собирается конкатенацией строк в `query_doctor/web/ui/*.py`.
- Весь CSS лежит одной строкой в [`query_doctor/web/ui/layout.py:25-39`](../../query_doctor/web/ui/layout.py) — нечитаемо, диффы бесполезны.
- Inline `<script>` (~250 строк vanilla JS): theme toggle, polling прогресса job-ов, progressive disclosure, info-popovers — в [`query_doctor/web/ui/layout.py:92-352`](../../query_doctor/web/ui/layout.py).
- HTML-escaping держится на дисциплине вызова `display_safety` и `html.escape` в каждой render-функции — нет автоматического escape по умолчанию.
- Routes: `query_doctor/web/routes.py`, handler: `query_doctor/web/app.py`.
- Job store in-memory, без TTL: `query_doctor/web/jobs.py:100-106`.

### Рекомендация: НЕ переписывать на React

Ключевые причины именно для этого продукта:

1. **Safety contract против SPA.** AGENTS.md и hard rules требуют, чтобы сервер контролировал каждый байт в браузере: «never echo pasted SQL back», «never render raw paths/profiles/metadata», LLM output untrusted до валидации. SSR в одном месте — естественно ложится на этот контракт. React + JSON API удваивает поверхность аудита.
2. **Local-first продукт без realtime-нужд.** Один пользователь, локалхост, нет латентности. Динамика — только polling `/jobs/<id>/status` и пара toggle-ов. Виртуальный DOM ничего не покупает, build chain (npm/vite) ломает «no network in default local workflows».
3. **AGENTS.md прямо просит** «boring, explicit code over clever generic machinery», «keep dependency additions exceptional». React — нарушение этого принципа.

### Что стоит сделать вместо переписывания

| # | Действие | Стоимость | Польза |
|---|---|---|---|
| 1.1 | Вынести CSS из `layout.py` в `query_doctor/web/static/app.css` (с переносами и комментариями); сервить как статический asset с правильным Content-Type. | Малая | Читабельность, нормальные диффы, открывает путь к CSP. |
| 1.2 | Вынести JS (`render_client_script`, `render_theme_bootstrap_script`) в `query_doctor/web/static/app.js`. | Малая | То же + позволяет ввести CSP без `'unsafe-inline'`. |
| 1.3 | Ввести Jinja2 с `autoescape=True` для рендера. Мигрировать постепенно, начиная с одной страницы (например, `render_help_page`). | Средняя | Безопасность escape по умолчанию вместо ручной дисциплины. |
| 1.4 | Разбить `layout.py` на модули по ответственности (header, theme, client_script, css). | Малая | Файлы становятся обозримыми. |

---

## 2. Готовность к публичному репозиторию и shared-deploy

Текущая архитектура спроектирована под single-user local-first. Если её бинднуть на корп-сеть как shared-сервис — несколько серьёзных дыр. Ниже — приоритизированный список.

### Блокирующие пункты для shared-deploy

| # | Проблема | Файл/строка | Что делать |
|---|---|---|---|
| 2.1 | **Нет аутентификации.** Любой с сетевым доступом к порту получает полный контроль (`/analyze`, `/batch/run`, `/optimizer`, case detail, LLM jobs). Сервер ходит в CM/Kerberos под учёткой процесса → impersonation. | `query_doctor/web/routes.py:57` (`STATIC_POST_PATHS`) | Вариант A: задокументировать как «do not deploy as shared service». Вариант B: добавить обязательный reverse-proxy auth (OIDC/SAML), доверять `X-Forwarded-User` от proxy с trust-host-allowlist. |
| 2.2 | **Нет CSRF-защиты.** POST не проверяют `Origin`/`Referer`/токен. Cookies не используются — это спасает от классики, но не от DNS-rebinding и drive-by форм. | `query_doctor/web/app.py:63-84` | Минимум: `Origin`/`Host` allowlist в handler-е. Лучше: synchronizer-token на POST. |
| 2.3 | **`http.server.ThreadingHTTPServer` — не production-сервер.** stdlib предупреждает явно. Нет slowloris-защиты, тайм-аутов, graceful shutdown, метрик. | `query_doctor/cli/web.py:46` | Для shared-deploy: WSGI (waitress/gunicorn) с тем же handler-слоем, либо требовать reverse-proxy. |
| 2.4 | **Нет TLS.** | `query_doctor/cli/web.py:46-47` | Либо встроить TLS, либо в README зафиксировать «only behind corp reverse-proxy with TLS». |
| 2.5 | **DNS-rebinding не закрыт при non-local bind.** `validate_bind_host` только просит флаг, не валидирует `Host` header. С `--allow-nonlocal-web-bind` любой сайт, резолвящийся в IP машины, получает доступ через браузер жертвы. | `query_doctor/web/config.py:34-42` | Явный `Host` header allowlist. |
| 2.6 | **Security headers практически отсутствуют.** Только `Cache-Control: no-store`. | `query_doctor/web/app.py:93,105` | Добавить: `Content-Security-Policy` (после выноса inline JS — пп. 1.1, 1.2), `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, `Permissions-Policy: ()`. |

### Сильно желательное для multi-tenant

| # | Проблема | Файл/строка | Что делать |
|---|---|---|---|
| 2.7 | **Multi-user model отсутствует.** `WebJobStore._jobs` общий, без owner-а, без видимости «свои/чужие», без eviction. Любой пользователь видит чужие job-результаты, чужой case-detail. | `query_doctor/web/jobs.py:100-106` | Либо явно single-tenant по архитектуре, либо identity-bound store + ACL по `case_id`. |
| 2.8 | **Job-store растёт безгранично и теряется на рестарте.** | `query_doctor/web/jobs.py:100-106` | TTL-эвикшн + опциональный персистентный backend (sqlite/file). |
| 2.9 | **Нет concurrency cap / rate limit.** `/analyze` стартует subprocess без квоты. 10 вкладок = 10 параллельных CM-сканов. | `query_doctor/web/routes.py` | Глобальный pool, per-source quota, rate-limit на POST. |
| 2.10 | **Audit log отсутствует.** `BaseHTTPRequestHandler.log_message` пишет в stderr. | `query_doctor/web/app.py:113` | Структурированный audit-log (JSON-lines) с user identity (после 2.1): кто, когда, какой query_id, какой CM, какой job_id. |
| 2.11 | **Нет ulimit/timeout на подпроцессы.** `start_new_session=True` есть, но ни `resource.setrlimit`, ни жёсткого max-runtime. Тяжёлый CM-скан или зависший metadata shell могут съесть хост. | `query_doctor/web/subprocesses.py:70` | `resource.setrlimit` (CPU/RSS), wall-clock kill по тайм-ауту. |
| 2.12 | **POST size limit есть (320 KB), но GET URL длина не проверяется.** | `query_doctor/web/app.py:19` | Проверить URL-длину явно. |

---

## 3. Local-first vs Centralized k8s deployment

### Рекомендация

**Local-first как основной режим. Centralized — только опциональный reference deploy, если в конкретной компании настаивают.**

### Аргументы за local-first

1. **Авторизация уже встроена через kerberos/CM-учётку пользователя.** «Я диагностирую только то, что мне и так разрешено видеть в CM» — самая дешёвая корректная модель доступа. В централизованном варианте её придётся реконструировать через Kerberos constrained delegation или forward-keytab — сложно и corp-specific. Альтернатива (service account) → impersonation-плечо.
2. **Safety contract написан под single-tenant.** «Python owns facts, LLM owns wording», «no raw SQL/profile/paths in browser» — рассчитано на «один пользователь смотрит свои же запросы». Multi-tenant = ACL per `case_id`, изоляция артефактов между тенантами, per-user job queue → фактически второй продукт.
3. **Артефакты централизованного инстанса = новая security-перимента.** Cluster runtime context, ранкинг кейсов, validated reports на сервере → политика хранения, шифрование at rest, бэкапы, GDPR/SOC2-вопросы. У local-first ничего этого нет.
4. **Стоимость:** «harden local web» (пп. 1.1, 1.2, 2.2, 2.5, 2.6) — маленький PR. Корректный central deploy — auth + RBAC + persistence + per-user CM-делегирование + audit + ops, месяцы работы + on-call.
5. **OSS-adoption.** `pip install` — кратчайший путь до user-zero. Helm + OIDC = недели procurement в крупной компании.

### Когда central реально оправдан

- Корп-политика запрещает kerberos-тикеты на ноутбуках.
- Нужна company-wide видимость («что тормозит в этом квартале»).
- Нужно открыть инструмент нетехническим ролям (аналитики, BI).
- Нужен централизованный квотинг LLM-вызовов.

Если ничего из этого нет в явных запросах от пользователей — централизация решает проблему, которой нет.

### Третий вариант, который стоит назвать в документации

**Local-first внутри уже-существующих remote dev-environments** (Coder, Gitpod, корпоративный bastion / jumpbox). Запуск Query Doctor внутри devbox-а — всё ещё «один пользователь под своими креденшелами», но без боли с pip на каждом ноуте. С точки зрения safety-контракта неотличимо от чистого local-first.

### Прагматичный план

1. Зафиксировать в README/SECURITY.md: `Supported deployment: single-user, local-first, behind your own CM credentials.`
2. Снизить трение установки: Docker-образ + однострочный `docker run`, опционально brew/uv recipe.
3. Закрыть hardening-пункты для local web (1.1, 1.2, 2.2, 2.5, 2.6).
4. Документировать reference corp-deploy как «if you must», с явными требованиями: corporate reverse-proxy с OIDC + TLS, single-tenant-per-team инстансы, per-instance CM service account. Helm chart — позже, по запросу.
5. Не строить multi-tenant в самом коде до появления реального платящего пользователя.

---

## 4. Монетизация multi-tenant как платной фичи

### Контекст

Лицензионная инфраструктура **уже есть**: AGPL-3.0 + commercial license ([COMMERCIAL-LICENSE.md](../../COMMERCIAL-LICENSE.md)) — классический open-core / dual-license setup. AGPL сама по себе создаёт давление на компании платить (внутренний форк без раскрытия исходников = нужна коммерческая лицензия).

### Что смущает

1. **Платный ярлык не делает разработку дешевле.** Multi-tenant — те же месяцы работы. Продажа = «кто-то платит за то, чтобы построить» — нужно найти первого клиента, готового страдать с v0.1.
2. **Open-core trap.** Безопасность обязана жить в core, не в платном тире. Нельзя продавать защиту.
3. **Sales — отдельный навык.** Security questionnaires, redlined MSA, SLA, SOC2 — другой режим работы, чем OSS-maintainer.

### Предлагаемый порядок действий (до написания кода)

1. **Проверить, не работает ли AGPL уже без платных фич.** Если приходят запросы «давайте без AGPL» — это монетизация без новой строки кода.
2. **Продать сначала самые дешёвые вещи**: helm chart + reference deploy guide + support contract + SLA. Валидирует спрос на централизованное развёртывание **до** инвестиций в multi-tenant.
3. **Найти design partner до написания кода.** Letter of intent / pilot agreement / первый платящий клиент-подопытный.
4. **Чётко зафиксировать границу core ↔ enterprise:**
   - **Core (AGPL, free):** single-tenant local-first, **весь** safety contract, все аналитические фичи, single-user web, CLI, валидация репортов. Никаких намеренных degradations.
   - **Enterprise (commercial-only):** OIDC/SAML SSO, RBAC на shared job-store, multi-tenant artifact storage, audit-log export для compliance, centralized LLM-gateway с квотами и cost-attribution, helm chart + support.

   Граница **не** проходит по «безопасности» или «качеству анализа» — только по операционной обвязке для shared deploy.

### Самая дешёвая первая итерация без кода

1. В README добавить explicit «for shared corporate deployment, contact for commercial license» с честным описанием рисков shared-deploy на текущем коде.
2. Опубликовать минимальный `docs/enterprise-readiness-checklist.md` — что не покрыто текущей архитектурой (auth, ACL, persistence, audit) — одновременно honesty и lead-magnet.
3. Принимать запросы и считать. Если двое-трое за полгода — есть смысл инвестировать. Если ноль — рынок не валидирован.

---

## 5. Workflow команды дата-инженеров на local-first

### Реалистичный day-to-day для команды 5-10 человек

**Установка (один раз на инженера):**

1. Python venv + `pip install impala-query-doctor` (или внутренний package mirror).
2. Kerberos обычно уже настроен у дата-инженеров (используют impala-shell) → нулевая дополнительная цена.
3. Один shared `query-doctor-config.json` в репозитории команды (CM URL, auth mode, metadata coordinator).
4. LLM endpoint: либо локальный Ollama на ноуте (медленно, офлайн), либо команда поднимает **один shared Ollama** на внутреннем GPU-инстансе и все доктора смотрят туда. Это всё ещё local-first для самого доктора.

**Регулярные сценарии:**

1. *«Мой ETL утром медленный»* — recent scan на последние 4 часа, фильтр по своему юзеру/группе, drill-down в кейс, validated report.
2. *Дежурство* — running-scan, выявить виновника текущей деградации, тикет owner-у.
3. *Code review SQL* — Query Optimizer, deterministic candidates, опционально LLM-optimizer-action.
4. *Post-mortem* — recent scan с конкретным time bucket.

### Что реально болит в team-режиме

| # | Боль | Можно решить без кода? |
|---|---|---|
| 5.1 | **Нет shared visibility.** Открытия не накапливаются на уровне команды. | Да — shared git-репо отчётов. |
| 5.2 | **Невозможно «посмотреть, что коллега нашёл»** без re-run. | Да — git-репо отчётов или скопировать case dir. |
| 5.3 | **Дрейф версий.** У одного 0.4.1, у другого 0.5.0 → разные validation rules. | Частично — командная дисциплина «все на одном теге», или внутренний pinned mirror. |
| 5.4 | **Каждому нужен CM-доступ.** Инженеры без CM-доступа отрезаны. | Нет — это by design в local-first модели. |
| 5.5 | **Onboarding нового инженера** — Python, krb5, конфиг, опционально Ollama. | Частично — Docker-образ снимает Python и большую часть зависимостей. |

### Паттерны, которые команды наработают сами (без изменений в коде)

1. **Shared reports git-репозиторий.** `slow-query-postmortems/` — копировать validated report markdown, открывать PR. Получается searchable team knowledge base без multi-tenant.
2. **CI-driven scheduled scans.** Cron/GitHub Actions гоняет `query-doctor-batch` (CLI, headless) под service-account-ом, складывает batch-summary в shared bucket / репо. Web-UI — для drill-down. **Сильный паттерн** — детерминистичная аналитическая часть прекрасно работает headless. Даёт «дешёвый dashboard» бесплатно.
3. **Team jumpbox.** Один shared Linux-инстанс с preinstalled доктором; инженеры заходят через SSH с port-forward, используют свой kerberos-тикет. Снимает «pip на каждом ноуте», сохраняет per-user creds. Технически — всё ещё local-first.
4. **Doctor-of-the-week ротация.** Один инженер на неделю смотрит recent-scan, заводит тикеты на топ-3 кейса. Никакой технологии не нужно — процесс.
5. **Shared LLM endpoint.** Один Ollama / vLLM на внутреннем GPU-инстансе. Все доктора пишут в `local_config.json` один URL. Решает «у меня нет GPU» и даёт центральный billing/quota point.

### Inflection point

- **1-3 инженера** — local-first идеален.
- **5-10 инженеров** — работает с парой shared-конвенций (репо отчётов, общий Ollama, scheduled CI scan). Никакой код менять не нужно.
- **20+ инженеров / несколько команд** — реальные жалобы: «дайте URL», «хочу видеть что нашли соседи», «единый audit log». Здесь и появляется бизнес-кейс под платный multi-tenant.

### Маленькие коде-улучшения, которые делают local-first приятнее в команде 5-10

| # | Улучшение | Цель |
|---|---|---|
| 5.6 | Headless CLI для batch-scan + JSON/markdown output как first-class. Если есть (`query-doctor-batch`) — задокументировать team-pattern. Если нет — добавить. | Поддержка CI-driven scheduled scans. |
| 5.7 | Кнопка «Export validated report» в web-UI → отдаёт markdown-файл напрямую (для копирования в Confluence/Jira/git-репо). | Облегчает sharing. |
| 5.8 | «Open this case from URL» deep-link: `http://localhost:8765/batch/case/<id>` корректно открывается у коллеги с тем же batch_summary. Проверить, работает ли уже. | Облегчает collaboration в чате. |
| 5.9 | Раздел в README **«Team usage patterns»** — описать варианты (shared reports repo / CI scan / shared Ollama / jumpbox). | Снимает 80% вопросов «как нам этим пользоваться вдвоём». |
| 5.10 | Детерминистичный диф-режим — «прогони тот же кейс ещё раз и скажи, что изменилось в фактах». | Полезно для трекания прогресса по медленному запросу неделями. |

---

## 6. Сводный приоритизированный список (для оценки в roadmap)

Список упорядочен по принципу «дёшево + сейчас полезно» → «дорого + только если идём в shared-deploy».

### A. Низкая стоимость, высокая отдача (можно сейчас)

- **A1.** Вынести CSS из `layout.py` в `static/app.css` (см. 1.1).
- **A2.** Вынести inline JS в `static/app.js` (см. 1.2).
- **A3.** Разбить `layout.py` по ответственности (см. 1.4).
- **A4.** Базовые security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` (см. 2.6).
- **A5.** `Host` header allowlist для защиты от DNS-rebinding (см. 2.5).
- **A6.** README раздел «Team usage patterns» — описать shared reports repo, CI-driven scan, shared Ollama, jumpbox (см. 5.9).
- **A7.** README/SECURITY.md: явная фиксация «supported deployment = single-user local-first; do not deploy as shared service» с описанием рисков shared-deploy.
- **A8.** Кнопка «Export validated report» в web-UI (см. 5.7).
- **A9.** Проверить и задокументировать deep-link на case (см. 5.8).

### B. Средняя стоимость, умеренная отдача (если есть тяга)

- **B1.** CSP без `'unsafe-inline'` после A1-A2 (см. 2.6).
- **B2.** Jinja2 с `autoescape=True` — миграция начиная с одной страницы (см. 1.3).
- **B3.** CSRF-токен для POST endpoints (см. 2.2).
- **B4.** Rate-limit и concurrency cap на subprocess-launch endpoints (см. 2.9).
- **B5.** TTL-эвикшн job-store (см. 2.8).
- **B6.** `resource.setrlimit` + wall-clock kill для подпроцессов (см. 2.11).
- **B7.** Headless CLI batch-scan first-class + документация CI-driven pattern (см. 5.6).
- **B8.** Docker-образ + однострочный `docker run` для снижения onboarding-трения.
- **B9.** Детерминистичный диф-режим для повторных прогонов кейса (см. 5.10).
- **B10.** Структурированный audit-log в JSON-lines (см. 2.10).

### C. Высокая стоимость — только если идём в shared/enterprise (не делать без платящего партнёра)

- **C1.** Reverse-proxy auth (OIDC/SAML) с trust-host-allowlist на `X-Forwarded-User` (см. 2.1).
- **C2.** Identity-bound job store + ACL по `case_id` (см. 2.7).
- **C3.** Persistent job/artifact backend (sqlite/postgres) (см. 2.8).
- **C4.** WSGI runtime (waitress/gunicorn) вместо `http.server` (см. 2.3).
- **C5.** Встроенный TLS или формальное требование reverse-proxy с TLS (см. 2.4).
- **C6.** Multi-tenant artifact storage с тенант-изоляцией.
- **C7.** Centralized LLM-gateway с квотами и cost-attribution.
- **C8.** Helm chart + reference k8s deployment.
- **C9.** `docs/enterprise-readiness-checklist.md` — публичный документ с честным списком gaps для shared-deploy (lead-magnet до C1-C8).

---

## 7. Замечания для Codex по фильтрации

- Не добавлять C-пункты в roadmap без явного решения о платном multi-tenant и наличии design partner.
- A-пункты безопасны для добавления как «hardening» / «UX polish» — они улучшают и local-first сценарий.
- B-пункты — оценить по cost/benefit; некоторые из них (B1, B2, B3) усиливают safety contract и для local-first; другие (B4, B5, B6, B10) больше относятся к shared-deploy.
- Все file:line ссылки выше — snapshot на момент 2026-05-09. Перед стартом любой задачи проверить, что путь не переехал.
- При обновлении `docs/changelog.md` следовать правилу из AGENTS.md: только significant entries (workflow / safety / LLM / collector / analyzer / docs baseline).
