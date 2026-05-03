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
<h1>Справка</h1>
<div class="report-body">
<p>Query Doctor помогает разбирать поведение запросов Apache Impala. Он объединяет детерминированный анализ профиля, ограниченные проверки metadata и генерацию проверенного отчета. Сейчас реализован только Apache Impala; другие SQL-движки остаются roadmap, а не готовой поддержкой.</p>

<h2>Быстрый старт</h2>
<ul>
<li>Начните с <strong>Recent scan</strong>, если хотите найти подозрительные запросы в кластере.</li>
<li>Используйте <strong>Query ID</strong>, если уже знаете конкретный запрос.</li>
<li>Используйте <strong>Query Optimizer</strong>, если автору запроса нужны подсказки по конкретному SQL.</li>
<li>Report generation запускается явно и только для выбранного кейса.</li>
</ul>

<details open>
<summary>Скан последних запросов / Recent scan</summary>
<p>Лучший старт для администратора. Recent scan сначала читает query summaries из Cloudera Manager, затем собирает ограниченное число выбранных профилей, ранжирует кейсы детерминированно и собирает metadata только для top cases, если это включено. Web Recent scan не запускает LLM-отчеты автоматически.</p>
<ul>
<li><strong>Scan date</strong> и <strong>Hour bucket</strong> задают один час Cloudera Manager summaries за сегодня или предыдущие два дня.</li>
<li>Web Recent scan анализирует все подходящие query profiles из выбранного часового окна, оставаясь под внутренним safety cap.</li>
<li><strong>Metadata top cases</strong> ограничивает, сколько top-ranked cases получат metadata enrichment.</li>
<li><strong>Min duration</strong> отсекает короткие запросы; пустое значение означает отсутствие этого фильтра.</li>
<li><strong>Jobs</strong> задает параллелизм и остается ограниченным safety caps.</li>
<li><strong>Fast scan</strong> быстрее и опирается на summary-level сигналы; <strong>Full scan</strong> добавляет bounded profile analysis и, если включено, metadata для top cases.</li>
</ul>
</details>

<details open>
<summary>Как читать результаты</summary>
<ul>
<li><strong>Rank</strong> — это приоритет для проверки, а не финальный root-cause verdict.</li>
<li><strong>Main reason</strong> — candidate signal, который объясняет, почему кейс поднялся выше.</li>
<li><strong>Evidence count</strong> показывает, сколько deterministic observations поддерживают ranking.</li>
<li><strong>Metadata status</strong> показывает, доступны ли table metadata: available, partial, skipped или failed.</li>
<li>Degraded metadata не отменяет profile-based findings, но metadata-based advice может быть ограничен.</li>
<li>Перед генерацией отчета откройте case detail и проверьте observed, not observed и unknown signals.</li>
</ul>
</details>

<details>
<summary>Диагностика по Query ID</summary>
<p>Подходит, если уже известен конкретный Query ID. Workflow собирает и анализирует один явно выбранный кейс. Report generation остается явным действием пользователя. Browser UI не показывает SQL text, profile text или локальные пути.</p>
</details>

<details>
<summary>Query Optimizer</summary>
<p>Подходит автору SQL-запроса, которому нужны подсказки по оптимизации. Query Optimizer принимает только один безопасный SELECT/WITH, валидирует его до table extraction и metadata collection, не выполняет вставленный SQL и не возвращает вставленный SQL обратно в браузер после submit.</p>
<p>Он использует deterministic extracted tables, metadata status, findings и limitations. Это не LLM chat и не автоматический SQL rewrite engine. Unsupported SQL отклоняется безопасно и без echo исходного текста.</p>
</details>

<details>
<summary>Метаданные</summary>
<p>Metadata collection явная, ограниченная, read-only и allowlisted. Текущий allowlist:</p>
<ul>
<li>SHOW CREATE TABLE</li>
<li>SHOW TABLE STATS</li>
<li>SHOW COLUMN STATS</li>
</ul>
<p>Query Doctor не запускает SELECT, COMPUTE, REFRESH, INVALIDATE, MSCK, SHOW PARTITIONS, DESCRIBE, DDL или DML для сбора metadata. Metadata может быть unavailable или partial; это нормальное degraded state.</p>
</details>

<details>
<summary>Проверенные отчеты</summary>
<p>Analyzer facts — источник истины. LLM отвечает только за формулировки. Raw LLM output не считается доверенным. Финальный отчет валидируется перед показом, а trusted report отклоняет unsupported claims и SQL-like raw output. Если validation fails, output нельзя считать trusted report.</p>
</details>

<details>
<summary>Что намеренно не показывается в браузере</summary>
<p>Browser UI намеренно не показывает raw query text, raw profile text, raw metadata output, локальные пути, case directory details, process output, secrets, environment secret values, runtime internals или raw evidence links. Это не недостающая функция: UI показывает safe summaries, statuses и validated outputs.</p>
</details>

<details>
<summary>FAQ</summary>
<h3>Почему я не вижу SQL запроса?</h3>
<p>Потому что браузер не является местом для raw query text. Query Doctor показывает safe summaries и deterministic findings.</p>
<h3>Почему не показывается полный profile?</h3>
<p>Полный profile может быть большим и чувствительным. UI показывает безопасные факты и статусы, полученные analyzer.</p>
<h3>Почему metadata partial или skipped?</h3>
<p>Metadata collection bounded. Она может быть отключена, недоступна, ограничена top cases или остановлена safety limits. Profile-based findings при этом остаются применимыми.</p>
<h3>Почему web Recent scan не генерирует отчеты автоматически?</h3>
<p>Чтобы не запускать LLM массово и не создавать trusted-looking output без выбора конкретного кейса. Report generation остается явным действием.</p>
<h3>Почему Query Optimizer очищает поле после submit?</h3>
<p>Чтобы не возвращать pasted SQL обратно в браузер. Результаты строятся из безопасных extracted facts и limitations.</p>
<h3>Почему поддерживается только Impala?</h3>
<p>Текущий analyzer, collectors и validators реализованы для Apache Impala.</p>
<h3>Можно ли добавить Trino, Spark, Hive или другой engine?</h3>
<p>Да, но это отдельная работа. Нужны safe read-only collection contract, metadata allowlist, parser/profile support, browser safety tests и report validator coverage.</p>
</details>

<h2>Текущие ограничения и roadmap</h2>
<p>Сейчас реализована только Impala. Будущая цель — engine-agnostic diagnostic core с engine adapters. Другие движки — planned possibilities, not implemented support.</p>
</div>
</section>
""".strip()
