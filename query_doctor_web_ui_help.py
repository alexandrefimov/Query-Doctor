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
<li>Результаты группируются как <strong>Bad queries</strong>, <strong>Suspicious queries</strong> и <strong>Good queries</strong>.</li>
<li><strong>Only queries with spills</strong> — display-фильтр уже полученных результатов; он не меняет параметры запуска scan.</li>
<li><strong>Collect CM metrics</strong> включает ограниченный сбор Cloudera Manager time-series summaries для выбранных запросов. По умолчанию выключен для Finished Queries.</li>
</ul>
</details>

<details>
<summary>Running Queries</summary>
<p>Running Queries устроен как Finished Queries, но ищет только запросы, которые выполняются в момент scan. У него нет фильтров Scan date и Scan Hour; остальные фильтры и analysis settings остаются теми же. CM metrics для Running Queries собираются по умолчанию, потому что набор running-запросов обычно небольшой. Результаты отображаются той же таблицей и открывают details выбранного запроса.</p>
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
<li><strong>Score</strong> — deterministic priority score из analyzer facts.</li>
<li><strong>Duration</strong> показывает длительность из Cloudera Manager summary, если она доступна.</li>
<li><strong>STATS</strong> показывает доступность table stats: ✓ available, × missing/unknown/not_available, − not checked/not applicable.</li>
<li><strong>META</strong> показывает статус metadata collection.</li>
<li><strong>Summary</strong> коротко объясняет главные deterministic signals без raw evidence.</li>
</ul>

<h2 id="details-actions">Details, LLM Report и Query LLM optimizer</h2>
<p>Details показывает безопасную сводку по одному запросу. <strong>Analysis details</strong> свернут по умолчанию и содержит deterministic runtime, metadata и technical signals. <strong>LLM Report</strong> доступен для запросов не из Good group и рендерится прямо на странице только после validation. <strong>Query LLM optimizer</strong> — отдельное ручное действие для исходника, который уже собран Query Doctor: он может использовать SELECT/WITH или извлеченный SELECT/WITH payload из поддержанного INSERT/CTAS, но trusted draft всегда должен быть безопасным SELECT/WITH без выполнения SQL.</p>
<p>Если LLM output или optimizer draft не проходит deterministic validation, partial output скрывается и показывается только безопасный статус failure.</p>

<details>
<summary>Проверенные отчеты</summary>
<p>Analyzer facts — источник истины. LLM отвечает только за формулировки. Raw LLM output не считается доверенным. Финальный отчет валидируется перед показом, а trusted report отклоняет unsupported claims и SQL-like raw output.</p>
<p>В LLM Report по умолчанию видны краткий вывод и практические рекомендации. Подробный разбор, админские проверки и факты анализатора остаются частью trusted report, но не подменяют deterministic analyzer facts.</p>
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
