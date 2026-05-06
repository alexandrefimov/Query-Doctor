"""Curated static Help page for the local Query Doctor web UI."""

from __future__ import annotations

from typing import Any


def render_help_page(settings: Any) -> str:
    from query_doctor_web_ui import render_page

    return render_page(
        settings,
        active_nav="help",
        show_run_panel=False,
        extra_sections=[render_help_content()],
    )


def render_demo_guide_page(settings: Any) -> str:
    from query_doctor_web_ui import render_page

    return render_page(
        settings,
        active_nav="demo",
        show_run_panel=False,
        extra_sections=[render_demo_guide_content()],
    )


def render_help_content() -> str:
    return """
<section class="panel docs-panel" aria-label="Query Doctor help">
<h1>Help</h1>
<div class="report-body">
<p>Query Doctor помогает разбирать поведение запросов Apache Impala. Он объединяет детерминированный анализ профиля, ограниченные проверки metadata и генерацию проверенного отчета. Сейчас реализован только Apache Impala; другие SQL-движки остаются roadmap, а не готовой поддержкой.</p>

<h2>On this page</h2>
<ul>
<li><a href="#workflows">Workflows</a></li>
<li><a href="#results-table">Results table</a></li>
<li><a href="#details-actions">Details, LLM Report и Query LLM optimizer</a></li>
<li><a href="#metadata">Метаданные</a></li>
<li><a href="#safety">Safety boundary</a></li>
<li><a href="#faq">FAQ</a></li>
</ul>

<h2 id="workflows">Workflows</h2>
<ul>
<li>Начните с <strong>Finished Queries</strong>, если хотите найти подозрительные завершенные запросы в выбранном часовом окне.</li>
<li>Используйте <strong>Running Queries</strong>, если нужно проверить запросы, которые выполняются прямо сейчас.</li>
<li>Используйте <strong>Specific Query</strong>, если уже знаете конкретный Query ID и хотите разобрать только его.</li>
<li>Используйте <strong>Query Optimizer</strong>, если автору запроса нужна безопасная проверка вставленного SELECT/WITH до runtime-профиля.</li>
<li><strong>LLM Report</strong> и <strong>Query LLM optimizer</strong> запускаются только вручную из details выбранного запроса.</li>
</ul>

<details open>
<summary>Finished Queries</summary>
<p>Основной workflow для администратора. Finished Queries читает query summaries из Cloudera Manager, применяет фильтры, собирает ограниченные профили завершенных запросов, анализирует их детерминированно и показывает ranked table. Web scan не запускает LLM-отчеты автоматически.</p>
<ul>
<li><strong>Scan date</strong> и <strong>Scan Hour</strong> задают один час Cloudera Manager summaries за сегодня или предыдущие два дня.</li>
<li><strong>Minimum duration</strong>, <strong>Username</strong> и <strong>Resource pool</strong> сужают набор summaries до запуска анализа.</li>
<li><strong>Parallelism</strong> управляет параллельной загрузкой профилей и локальным анализом. <strong>Metadata parallelism</strong> отдельно ограничивает read-only metadata collection.</li>
<li>Результаты группируются как <strong>Bad queries</strong>, <strong>Suspicious queries</strong>, <strong>Optimization candidates</strong> и <strong>Stats refresh candidates</strong>.</li>
<li><strong>Optimization candidates</strong> — deterministic список запросов, где profile facts показывают query-shape review opportunity. Он не обещает ускорение и не запускает LLM или SQL.</li>
<li><strong>Stats refresh candidates</strong> — deterministic список запросов, где metadata facts, estimate mismatch и planning-sensitive runtime symptoms вместе указывают, что stats refresh may improve speed. Это prediction, а не гарантия: нужен EXPLAIN comparison и rerun under comparable load.</li>
<li><strong>Only queries with spills</strong> — display-фильтр уже полученных результатов; он не меняет параметры запуска scan.</li>
<li><strong>Collect CM metrics</strong> включает ограниченный сбор Cloudera Manager time-series summaries для выбранных запросов. По умолчанию выключен для Finished Queries.</li>
</ul>
</details>

<details>
<summary>Running Queries</summary>
<p>Running Queries устроен как Finished Queries, но ищет только запросы, которые выполняются в момент scan. У него нет фильтров Scan date и Scan Hour; остальные фильтры и analysis settings остаются теми же. CM metrics для Running Queries включены по умолчанию и сбор выполняется в bounded режиме для ограниченного окна сканирования, чтобы не перегружать кластер. Результаты отображаются той же таблицей и открывают details выбранного запроса.</p>
</details>

<details>
<summary>Specific Query</summary>
<p>Подходит, если уже известен конкретный Query ID. На странице есть только поле Query ID и кнопка Run. Запуск собирает и анализирует один запрос без автоматического LLM. После анализа Query ID очищается, а результат добавляется в таблицу <strong>Specific Query analysis</strong> с колонками Query ID, Score, Duration, STATS, META и Summary.</p>
</details>

<details>
<summary>Query Optimizer</summary>
<p>Query Optimizer — отдельная страница для pasted SQL review до runtime-профиля. Она принимает только один безопасный SELECT/WITH, валидирует его до table extraction и metadata collection, не выполняет вставленный SQL и не возвращает вставленный SQL обратно в браузер после submit.</p>
</details>

<h2 id="results-table">Results table</h2>
<ul>
<li><strong>Rank</strong> в Finished Queries — порядок проверки внутри текущей группы; это не root-cause verdict.</li>
<li><strong>Query ID</strong> открывает details по клику на строку. Из Specific Query details открывается в новой вкладке.</li>
<li><strong>User</strong> показывает sanitized CM query user, чтобы быстрее понять владельца запроса.</li>
<li><strong>Score</strong> — deterministic priority score из analyzer facts; он остается в triage groups, но не используется как главный сигнал в action-oriented groups.</li>
<li><strong>Duration</strong> показывает длительность из Cloudera Manager summary, если она доступна.</li>
<li><strong>STATS</strong> показывает доступность table stats: ✓ available, × missing/unknown/not_available, − not checked/not applicable.</li>
<li><strong>META</strong> показывает статус metadata collection.</li>
<li><strong>Optimization candidates</strong> использует колонки Candidate, Impact, Confidence и Review first вместо общего Score/STATS/META набора.</li>
<li><strong>Stats refresh candidates</strong> использует колонки Candidate, Need, Speed benefit, Confidence и Confirm.</li>
<li>Кейсы без triage severity и без Medium/High optimization или stats-refresh candidate не выводятся отдельной вкладкой, чтобы results table оставалась action-oriented.</li>
<li><strong>Summary</strong> коротко объясняет главные deterministic signals без raw evidence.</li>
</ul>

<h2 id="details-actions">Details, LLM Report и Query LLM optimizer</h2>
<p>Details показывает безопасную сводку по одному запросу. <strong>Findings</strong> раскрыт по умолчанию и содержит основные deterministic выводы; <strong>Evidence details</strong> свернут и содержит runtime, CM metrics, metadata и technical signals для проверки. <strong>LLM actions</strong> держит три явных действия в одном блоке: LLM Report, Query LLM optimizer и combined запуск report + optimizer. Результаты рендерятся прямо на странице только после validation, а optimizer может использовать только server-owned SELECT/WITH или извлеченный SELECT/WITH payload из поддержанного INSERT/CTAS.</p>
<p>Если LLM output или optimizer draft не проходит deterministic validation, partial output скрывается и показывается только безопасный статус failure.</p>

<details>
<summary>Проверенные отчеты</summary>
<p>Analyzer facts — источник истины. LLM отвечает только за формулировки. Raw LLM output не считается доверенным. Финальный отчет валидируется перед показом, а trusted report отклоняет unsupported claims и SQL-like raw output.</p>
<p>В LLM Report по умолчанию видны краткий вывод и практические рекомендации. Подробный разбор, Follow-up checks и факты анализатора остаются частью trusted report, но не подменяют deterministic analyzer facts.</p>
</details>

<details>
<summary>Pasted-SQL optimizer</summary>
<p>Он показывает deterministic extracted tables, metadata status, findings и limitations. Это не LLM chat и не автоматический rewrite engine. Unsupported SQL отклоняется безопасно и без echo исходного текста.</p>
</details>

<h2 id="metadata">Метаданные</h2>
<p>Metadata collection явная, ограниченная, без выполнения пользовательского SQL и allowlisted. Текущий allowlist:</p>
<ul>
<li>SHOW CREATE TABLE</li>
<li>SHOW TABLE STATS</li>
<li>SHOW COLUMN STATS</li>
</ul>
<p>Query Doctor не запускает SELECT, COMPUTE, REFRESH, INVALIDATE, MSCK, SHOW PARTITIONS, DESCRIBE, DDL или DML для сбора metadata. Metadata может быть unavailable или partial; это нормальное degraded state.</p>

<h2 id="safety">Safety boundary</h2>
<p>Browser UI намеренно не показывает raw query text, raw profile text, raw metadata output, локальные пути, case directory details, process output, secrets, environment secret values, runtime internals или raw evidence links. Это не недостающая функция: UI показывает safe summaries, statuses и validated outputs.</p>

<h2 id="faq">FAQ</h2>
<h3>Почему я не вижу SQL запроса?</h3>
<p>Потому что браузер не является местом для raw query text. Query Doctor показывает safe summaries и deterministic findings.</p>
<h3>Почему не показывается полный profile?</h3>
<p>Полный profile может быть большим и чувствительным. UI показывает безопасные факты и статусы, полученные analyzer.</p>
<h3>Почему metadata partial или skipped?</h3>
<p>Metadata collection bounded. Она может быть отключена, недоступна, ограничена top cases или остановлена safety limits. Profile-based findings при этом остаются применимыми.</p>
<h3>Почему Finished Queries не генерирует отчеты автоматически?</h3>
<p>Чтобы не запускать LLM массово и не создавать trusted-looking output без выбора конкретного кейса. Report generation остается явным действием.</p>
<h3>Почему Query Optimizer очищает поле после submit?</h3>
<p>Чтобы не возвращать pasted SQL обратно в браузер. Результаты строятся из безопасных extracted facts и limitations.</p>
<h3>Почему поддерживается только Impala?</h3>
<p>Текущий analyzer, collectors и validators реализованы для Apache Impala.</p>
<h3>Можно ли добавить Trino, Spark, Hive или другой engine?</h3>
<p>Да, но это отдельная работа. Нужны safe read-only collection contract, metadata allowlist, parser/profile support, browser safety tests и report validator coverage.</p>

<h2 id="roadmap">Текущие ограничения и roadmap</h2>
<p>Сейчас реализована только Impala. Будущая цель — engine-agnostic diagnostic core с engine adapters. Другие движки — planned possibilities, not implemented support.</p>
</div>
</section>
""".strip()


def render_demo_guide_content() -> str:
    return """
<section class="panel docs-panel" aria-label="Query Doctor demo guide">
<h1>Demo guide</h1>
<div class="report-body">
<p>Эта страница помогает показывать Query Doctor дата-инженерам. Она объясняет, как устроены deterministic scoring, profile analysis, metadata checks, CM metrics correlation, LLM Report и Query LLM optimizer. Это curated UI text, а не рендер документации из репозитория.</p>

<h2>On this page</h2>
<ul>
<li><a href="#demo-model">Mental model</a></li>
<li><a href="#demo-specific-path">Specific Query path</a></li>
<li><a href="#demo-profile">Profile signals</a></li>
<li><a href="#demo-triage">Triage score</a></li>
<li><a href="#demo-optimization">Optimization candidates</a></li>
<li><a href="#demo-stats">Stats refresh candidates</a></li>
<li><a href="#demo-llm">LLM boundaries</a></li>
<li><a href="#demo-scenarios">Demo scenarios</a></li>
<li><a href="#demo-qa">Q&amp;A</a></li>
</ul>

<h2 id="demo-model">Mental model</h2>
<p>Главная позиция для демо: Query Doctor — engineering diagnostic tool, а не chat wrapper. Python extracts facts and scores candidates. LLM используется только после явного действия пользователя и только для wording или draft assembly в рамках validation.</p>
<ol>
<li>Cloudera Manager summaries дают bounded список кандидатов.</li>
<li>Selected profiles собираются с redaction и safety limits.</li>
<li>Analyzer строит normalized facts.</li>
<li>Recent scan ранжирует кейсы из analyzer facts.</li>
<li>Metadata collection включается явно и остается bounded/read-only.</li>
<li>LLM Report и Query LLM optimizer запускаются только из details выбранного кейса.</li>
</ol>

<h2 id="demo-specific-path">Specific Query path</h2>
<p><strong>Specific Query</strong> — путь для одного известного Query ID. Это самый понятный workflow для объяснения end-to-end trust chain: от bounded collection до validated report или optimizer fallback.</p>

<details open>
<summary>1. Collection</summary>
<p>После submit UI валидирует Query ID и запускает single-query collection. Collector читает ровно один matching CM query summary/profile, пишет staged case под локальный corpus, включает redaction и проверяет, что collector вернул ожидаемый case для этого Query ID. Если такой case уже был, новый результат заменяет старый только после успешного collection + analysis.</p>
<p>Для explicit single-query collection bounded CM time-series summaries включены по умолчанию. Raw time-series points не пишутся в trusted facts и не показываются в browser UI: collector сохраняет только bounded aggregates по allowlisted metric queries.</p>
</details>

<details>
<summary>2. Analyzer and metadata</summary>
<p>После collection UI запускает analyzer в <code>--stop-after-analysis</code> режиме. Analyzer читает collected profile digest and safe context, строит <code>analysis_facts</code>, извлекает summary counts, Action Cards, Query Wall Clock, Backend / Host Tail Evidence, Runtime Counter Context, CM Metrics Facts и CM Metrics Correlation.</p>
<p>Если web metadata configured, pipeline включает bounded read-only metadata collection с failure policy <code>continue</code>. Metadata может улучшить stats-refresh classification, но не становится root cause сама по себе.</p>
</details>

<details>
<summary>3. CM metrics role</summary>
<p>CM metrics нужны не для отдельного cluster diagnosis, а для runtime context вокруг конкретного query window. Analyzer классифицирует metrics как observed, not_observed или unknown, а затем строит <strong>CM Metrics Correlation</strong>: совпадает ли metric signal с profile evidence.</p>
<ul>
<li>Daemon memory growth может усилить memory-pressure context, если profile facts показывают memory/spill/high-memory operators.</li>
<li>Network I/O spike может усилить data-movement context, если есть large exchange/intermediate volume.</li>
<li>CPU pressure без matching profile evidence остается context-only.</li>
</ul>
<p>Эти metrics могут повлиять на triage score только bounded bonus для correlated signals. Они не должны сами запускать optimizer actions и не должны звучать как root cause без deterministic profile support.</p>
</details>

<details>
<summary>4. Details generation</summary>
<p>После successful analysis UI строит Specific Query result row и details page из sanitized summary case. Details не читает raw profile или raw SQL для browser output. Он показывает deterministic Findings, Evidence details, metadata facts, CM metrics facts/correlation и LLM actions.</p>
<p>Score, Optimization candidate и Stats refresh candidate рассчитываются из <code>analysis_facts</code>. Поэтому Details — это не LLM summary, а browser-safe presentation layer над analyzer-owned facts.</p>
</details>

<details>
<summary>5. LLM Report prompt and validation</summary>
<p>LLM Report запускается только явной кнопкой. Report writer читает только deterministic facts, не читает raw profile text и не использует raw SQL как источник inference. Prompt содержит safe facts, Python-owned report contract digest, case differentiators и Python-owned recommendation candidates.</p>
<p>LLM получает роль report writer: писать по-русски, не изобретать evidence, не добавлять root-cause claims, не добавлять actions outside candidate list. После generation Python normalizes wording, фильтрует рекомендации обратно к Python-owned candidates, добавляет deterministic analyzer appendix и запускает strict validation. Если validation rejects output, partial report остается untrusted and hidden.</p>
</details>

<details>
<summary>6. Query LLM optimizer bullets and prompt</summary>
<p>Query LLM optimizer тоже запускается только явной кнопкой из details. Сначала Python extracts server-owned source scope: read-only SELECT/WITH или supported SELECT/WITH payload из INSERT/CTAS. Затем Python считает risk mode: <code>rewrite_allowed</code>, <code>conservative_rewrite</code> или <code>recommendations_only</code>.</p>
<p>Python формирует deterministic manual bullets из Action Cards, recommendation candidates, query-shape score, metadata/counter-signals и rewrite recipe, если она обнаружена. Для recipe-backed cases prompt intentionally narrow: instruction, Python-owned rewrite bullets и source SQL. Для broader cases prompt использует compact fact/shape digest и deterministic bullets.</p>
<p>Если risk mode <code>recommendations_only</code>, UI не пытается показать SQL draft: LLM может только переформулировать safe recommendations, а Python normalizes them back to allowed bullets.</p>
</details>

<details>
<summary>7. Optimizer response validation and fallback</summary>
<p>Если LLM вернул SQL draft, Python extracts draft and validates it before trust. Validation проверяет read-only scope, physical table set, preserved filters, joins, projection shape, DISTINCT / GROUP / ORDER / set-operation signatures, source SQL hash, facts hash, source scope and recipe-specific invariants. Marker trust requires current schema and matching hashes.</p>
<p>Если validation не проходит, raw draft не показывается. Вместо этого optimizer записывает trusted <code>no_rewrite</code> outcome with Python-owned bullets: почему draft не trusted и какие review areas можно использовать, чтобы переписать запрос manually. Пользователь видит безопасные bullets/recommendations-only guidance, а не unsafe SQL.</p>
<p>Если LLM output был incomplete, hit output budget, или draft не содержит material rewrite, UI также показывает no trusted SQL draft и безопасные bullets. Это deliberate safety behavior.</p>
</details>

<h2 id="demo-profile">Profile signals</h2>
<p>Analyzer смотрит на Impala runtime/profile facts и безопасный CM context. Основные группы сигналов:</p>
<ul>
<li><strong>Query Wall Clock</strong>: длительность из safe CM/profile context.</li>
<li><strong>Cardinality mismatch</strong>: actual rows заметно выше estimated rows.</li>
<li><strong>Memory mismatch</strong>: peak memory выше estimated memory или estimate отсутствует.</li>
<li><strong>Spill/scratch evidence</strong>: только explicit non-zero spill/scratch metrics.</li>
<li><strong>Backend / Host Tail Evidence</strong>: tail сравнивается только внутри comparable fragment instances.</li>
<li><strong>Backend data skew</strong>: неравномерная работа по backend rows/records, но не доказательство slow host само по себе.</li>
<li><strong>Runtime Counter Context</strong>: cumulative thread/CPU/wait/codegen counters остаются context, если facts не поддерживают elapsed-time interpretation.</li>
<li><strong>CM Metrics Correlation</strong>: CPU, memory или network signals усиливают context только когда совпадают с profile evidence.</li>
</ul>

<h2 id="demo-triage">Triage score</h2>
<p><strong>Score</strong> — deterministic priority score, а не вероятность root cause. Каждый positive score reason должен ссылаться на analyzer-supported facts.</p>
<table>
<thead><tr><th>Signal</th><th>Current contribution</th></tr></thead>
<tbody>
<tr><td>Cardinality estimate anomalies</td><td><code>+3</code> each, capped at <code>+12</code></td></tr>
<tr><td>Memory estimate anomalies</td><td><code>+2</code> each, capped at <code>+8</code></td></tr>
<tr><td>Zero/unknown row estimate gaps</td><td><code>+3</code> each, capped at <code>+12</code></td></tr>
<tr><td>Zero/unknown memory estimate gaps</td><td><code>+2</code> each, capped at <code>+8</code></td></tr>
<tr><td>Explicit non-zero spill/scratch evidence</td><td><code>+3</code></td></tr>
<tr><td>Host-tail candidates</td><td><code>+8</code> each, capped at <code>+12</code></td></tr>
<tr><td>Long-running query with execution tail</td><td><code>+8</code> when duration is at least 30 minutes</td></tr>
<tr><td>Backend data skew evidence</td><td><code>+2</code></td></tr>
<tr><td>Severe backend data skew ratio</td><td><code>+8</code></td></tr>
<tr><td>CM metrics correlated signals</td><td><code>+2</code> each, capped at <code>+6</code></td></tr>
<tr><td>Metadata failed / missing stats limitations</td><td>small bounded additions, used as checks and limitations</td></tr>
</tbody>
</table>
<p><strong>High</strong> severity появляется при score at least <code>30</code> или при сильных count-based signals: много cardinality/memory gaps, combined row and memory gaps, backend skew plus host tail, либо long-running query with execution-tail evidence. <strong>Suspicious</strong> означает positive score ниже high-promotion rules. <strong>Clean</strong> означает score <code>0</code>, но не доказывает, что запрос оптимален.</p>

<h2 id="demo-optimization">Optimization candidates</h2>
<p><strong>Optimization candidates</strong> — deterministic query-shape review score. Это не LLM scoring и не promise speedup.</p>
<pre><code>score = 55% impact + 45% query-shape opportunity</code></pre>
<p><strong>Impact</strong> смотрит на runtime, scan/read volume, peak memory, spill/scratch evidence и large exchange/intermediate volume. <strong>Query-shape opportunity</strong> смотрит на large scan waste, join row expansion, cardinality mismatch with join evidence, large exchange before downstream processing, memory pressure at join/aggregation/sort-style operators и spill at shape-sensitive operators.</p>
<p><strong>Counter-signals</strong> снижают score или confidence: failed/incomplete analysis, failed/cancelled query state, admission wait dominates runtime, very short query или read volume без query-shape evidence.</p>
<ul>
<li><strong>High</strong>: score at least <code>70</code> with query-shape evidence.</li>
<li><strong>Medium</strong>: score at least <code>40</code> with query-shape evidence.</li>
<li><strong>Low</strong>: weak positive signal или expensive query без достаточного shape evidence.</li>
<li><strong>Not likely</strong>: нет полезного deterministic optimization evidence.</li>
</ul>

<h2 id="demo-stats">Stats refresh candidates</h2>
<p><strong>Stats refresh candidates</strong> отвечают на вопрос: стоит ли проверять stats maintenance как possible speed-benefit action. Это не утверждение, что stats caused the slowdown.</p>
<pre><code>score =
  35% impact
+ 55% metadata evidence
+ 45% estimate mismatch
+ 45% planning-dependent runtime symptoms</code></pre>
<p>Самая сильная evidence chain: metadata показывает missing/unknown/incomplete table, partition или column stats; estimates расходятся с actual facts; runtime симптомы завязаны на planning-sensitive operators; impact достаточно большой, чтобы проверка была полезной.</p>
<p>Required confirmation: compare EXPLAIN before/after stats collection, проверить join order, join distribution, estimates, exchange, spill и memory behavior, затем rerun under comparable load.</p>
<p>Metadata status нужно объяснять аккуратно: <code>not_requested</code> означает unknown, <code>partial</code> снижает confidence, <code>failed</code> является limitation, а <code>collected</code> не доказывает полноту stats автоматически.</p>

<h2 id="demo-llm">LLM boundaries</h2>
<details open>
<summary>LLM Report</summary>
<p>LLM Report — readable narrative по analyzer-owned facts. Он должен отвечать: что supported, что not observed, что unknown из-за missing/bounded evidence и какие follow-up checks нужны. Если wording сильнее facts, validation должна reject или normalization должна сузить формулировку.</p>
</details>
<details>
<summary>Query LLM optimizer</summary>
<p>Details-page optimizer безопасен из-за Python-owned trust chain: Python extracts server-owned source, classifies risk, выбирает mode или recipe, LLM assembles draft, Python validates read-only scope, physical table set, filters, joins, projection shape, literals, result shape и recipe-specific invariants. Только validated draft показывается как trusted SQL.</p>
<p>Если validation fails, Query Doctor может показать trusted recommendations-only или no-rewrite guidance. Это safety feature, а не failed demo.</p>
</details>
<p>Правильная формулировка: analyzer selected the candidate and strategy; LLM assembled a draft; validator decided whether the draft is trusted.</p>

<h2 id="demo-scenarios">Demo scenarios</h2>
<div class="batch-metrics">
<div class="batch-metric"><span>Scenario 1</span><strong>Trusted SQL draft</strong></div>
<div class="batch-metric"><span>Scenario 2</span><strong>Rejected unsafe draft</strong></div>
<div class="batch-metric"><span>Scenario 3</span><strong>Stats refresh candidate</strong></div>
<div class="batch-metric"><span>Scenario 4</span><strong>Recommendations-only</strong></div>
</div>
<ul>
<li><strong>Trusted SQL draft</strong>: покажите Optimization candidates, Details Findings, затем trusted Query LLM optimizer result. Объясните, что draft принят только после deterministic validation.</li>
<li><strong>Rejected unsafe draft</strong>: используйте, если спрашивают про hallucination risk. Query Doctor может сказать "worth optimizing", но отказать SQL draft, который меняет semantics.</li>
<li><strong>Stats refresh candidate</strong>: покажите цепочку metadata gap + estimate mismatch + planning-sensitive symptoms + required confirmation.</li>
<li><strong>Recommendations-only</strong>: покажите, что complex SQL не вынуждает продукт показывать unsafe draft.</li>
</ul>

<h2 id="demo-qa">Q&amp;A</h2>
<h3>Почему этот case High?</h3>
<p>Показывайте visible deterministic reasons: score reasons, impact/confidence, wall-clock, estimate mismatches, host-tail evidence, spill/scratch evidence, metadata status или correlated CM metrics. Не выводите cause, которого нет в facts.</p>
<h3>Почему UI не показывает raw SQL?</h3>
<p>Browser UI показывает safe summaries. Raw SQL может содержать sensitive business logic, table names или literals. Анализ и объяснение не требуют echo raw query text.</p>
<h3>Может ли Query Doctor execute optimized SQL?</h3>
<p>Нет. Query Optimizer parse/analyze only. Details-page optimizer показывает validated draft. Любой benchmark — отдельная explicit read-only проверка вне UI workflow.</p>
<h3>Как понимать Confidence?</h3>
<p>Confidence — это полнота evidence и отсутствие counter-signals, а не гарантия speedup. High confidence означает, что несколько deterministic signals согласуются и нет сильного dominating counter-signal.</p>
<h3>Stats gap значит, что stats были root cause?</h3>
<p>Нет. Нужна evidence chain и required confirmation. Говорите "stats refresh candidate", "possible speed benefit" и "required confirmation".</p>
<h3>CM metrics являются root-cause evidence?</h3>
<p>Обычно это runtime context. Они становятся сильнее только при correlation with profile evidence и все равно не должны заменять deterministic profile facts.</p>

<h2>Wording checklist</h2>
<p><strong>Prefer:</strong> candidate, supported by parsed facts, correlated runtime context, review first, required confirmation, validated draft, recommendations-only fallback.</p>
<p><strong>Avoid:</strong> root cause без прямых facts, the LLM found, guaranteed speedup, stats caused it, cluster issue from one query, raw SQL/profile/metadata in browser.</p>
</div>
</section>
""".strip()
