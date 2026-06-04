import json
from pathlib import Path

import pytest


def load_report_module():
    from query_doctor.cli import report

    return report


def test_package_entrypoint_exposes_report_api():
    from query_doctor.cli import report

    assert hasattr(report, "sanitize_report_text")
    assert hasattr(report, "validate_report_against_facts")


def test_report_cli_reexports_package_contract():
    from query_doctor.cli import report
    from query_doctor.report import contract

    assert report.REPORT_SYSTEM_PROMPT == contract.REPORT_SYSTEM_PROMPT
    assert report.REQUIRED_REPORT_SECTIONS == contract.REQUIRED_REPORT_SECTIONS
    assert report.NEXT_CHECKS_HEADING == contract.NEXT_CHECKS_HEADING


def test_report_language_contracts_keep_legacy_ru_and_define_en():
    from query_doctor.report import contract
    from query_doctor.report.language_contract import (
        get_report_language_contract,
        normalize_report_language,
    )

    ru = get_report_language_contract("ru")
    en = get_report_language_contract("en")

    assert normalize_report_language(" RU ") == "ru"
    assert get_report_language_contract(" EN ").language == "en"
    assert contract.REPORT_SYSTEM_PROMPT == ru.system_prompt
    assert contract.REQUIRED_REPORT_SECTIONS == ru.required_sections
    assert ru.short_summary_heading == "## Краткий вывод"
    assert en.short_summary_heading == "## Short Summary"
    assert en.recommendations_heading == "## Practical Recommendations"
    assert "Write in English" in en.system_prompt


def test_report_language_contract_rejects_unknown_language():
    from query_doctor.report.language_contract import normalize_report_language

    with pytest.raises(ValueError, match="unsupported report language"):
        normalize_report_language("de")


def test_analyzer_facts_appendix_uses_language_contract():
    from query_doctor.report.facts_appendix import render_analyzer_facts_appendix

    facts = """
# Analysis Facts

## Summary

- Parsed operators: 9
- Cardinality anomalies: 0

## What is NOT supported by the parsed evidence

- No spill evidence was found.
"""

    appendix = render_analyzer_facts_appendix(facts, language="en")

    assert "## Analyzer Facts" in appendix
    assert "### Summary" in appendix
    assert "### Important Limitations" in appendix
    assert "## Факты анализатора" not in appendix


def test_english_report_contract_validates_strict_shape():
    module = load_report_module()
    facts = backend_fact_text()
    report = """
# Query Doctor Report

## Short Summary

- The parsed facts show backend data skew by RowsProduced, while host tail candidates are 0.
- The query wall-clock is available as bounded Cloudera Manager context with high confidence.
- Metadata facts are available for one referenced table and show incomplete or unknown column statistics.
- Spill or scratch evidence is present as a deterministic finding, so memory-pressure wording must stay tied to that evidence.

## Practical Recommendations

- Collect statistics for the affected tables through the approved operational process where facts show missing or incomplete stats.
- Reduce spill pressure by reducing intermediate data before memory-heavy operators that are already supported by profile evidence.
- After the change, capture a new profile and compare confirmed operator evidence such as wall-clock, host-tail evidence, operator rows and memory.

## Detailed Analysis

### Supported Profile Findings

- Backend rows were parsed and RowsProduced distribution is uneven across backends.
- Spill or scratch evidence is present in the deterministic findings.

### Supporting Evidence

- Summary facts report 9 parsed operators, no confirmed cardinality anomaly, no memory anomaly, and a bounded query wall-clock.
- Backend facts report host tail candidates as 0 and execution skew as no.

### Amplifying Factors

- The available metadata context can support approved stats maintenance, but it does not prove a root cause by itself.
- Runtime context is useful only as bounded supporting context and must not be promoted into a standalone cause.

### What Is Not Supported By Facts

- analysis_facts.md has no confirmed cardinality anomaly; do not claim cardinality underestimation without a matching fact.
- A single slow backend, external network fault, HDFS fault, and write-path cause are not proven by the parsed facts.

### Follow-up checks

- Compare the next profile against this baseline using the same deterministic facts and validation boundary.
- Send backend and host-tail evidence to the platform team only as bounded follow-up context.
"""

    normalized = module.normalize_report_text(report, facts_text=facts, language="en")

    assert "## Short Summary" in normalized
    assert "## Краткий вывод" not in normalized
    assert "Prioritize Backend / Host Tail Evidence" in normalized
    assert "Приоритизировать" not in normalized
    assert "Проверить" not in normalized
    assert module.validate_report_text(normalized, facts_text=facts, language="en") == []


def test_report_source_provenance_adds_safe_coverage_wording_without_raw_limitations():
    module = load_report_module()
    facts = (
        backend_fact_text()
        + """

## Source Provenance

- guardrail: Source provenance is a raw-free coverage summary.
- engine: unknown; source=unknown; coverage=engine identity was not available from deterministic profile facts
  - limitation: raw detail SELECT secret_col FROM private.table token=secret-value
- profile: partial; source=Impala daemon profile endpoint; coverage=dialect=classic_text_profile, layout=classic, compatibility=unsupported
- metrics: partial; source=Prometheus runtime metrics; coverage=1/3 metric queries ok
- events: none; source=Cluster event context; coverage=not_collected
- metadata: unavailable; source=Impala metadata context; coverage=context_error
  - limitation: failed to read /Users/example/query-doctor/case_dir; SHOW CREATE TABLE private.customer_orders
"""
    )
    report = "# Query Doctor Report\n\n" + safe_english_model_body()

    normalized = module.normalize_report_text(report, facts_text=facts, language="en")

    assert "Source Provenance: engine=unknown, profile=partial" in normalized
    assert "runtime metrics are incomplete or unavailable" in normalized
    assert "event context is absent or incomplete" in normalized
    assert "bounded metadata is unavailable or unknown" in normalized
    assert "not root-cause proof" in normalized
    assert "secret_col" not in normalized
    assert "private.table" not in normalized
    assert "secret-value" not in normalized
    assert "/Users/example" not in normalized
    assert "SHOW CREATE TABLE" not in normalized
    assert module.validate_report_text(normalized, facts_text=facts, language="en") == []


def test_english_report_validator_rejects_cyrillic_body_text():
    module = load_report_module()
    facts = backend_fact_text()
    report = ("# Query Doctor Report\n\n" + safe_english_model_body()).replace(
        "- Runtime context is useful only as bounded supporting context and must not be promoted into a standalone cause.",
        "- Русское предложение не должно проходить в английском trusted report.",
        1,
    )

    errors = module.validate_report_text(
        report,
        facts_text=facts,
        language="en",
        min_chars=0,
        min_sections=0,
    )

    assert "English report contains Cyrillic text" in errors


def test_report_cli_reexports_package_markdown_helpers():
    from query_doctor.cli import report

    from query_doctor.report import markdown

    assert report.extract_markdown_section is markdown.extract_markdown_section
    assert report.extract_markdown_subsection is markdown.extract_markdown_subsection
    assert report.strip_markdown_section is markdown.strip_markdown_section


def test_sanitizer_removes_or_rejects_facts_not_in_analysis():
    module = load_report_module()

    assert hasattr(module, "sanitize_report_text"), (
        "Expected query_doctor.cli.report to expose sanitize_report_text(report, facts_text)"
    )

    facts = """
# Analysis Facts

- Parsed operators: 24
- Cardinality anomalies: 22
- Memory anomalies: 9
- Known operator: HASH JOIN
"""

    report = """
# Query Doctor Report

Parsed operators: 24.
Cardinality anomalies: 22.
Memory anomalies: 9.

Next checks:
- Check network packet loss.
- Restart Impala.
- Run COMPUTE STATS for all tables.
"""

    sanitized = module.sanitize_report_text(report, facts)

    assert "Parsed operators: 24" in sanitized
    assert "Cardinality anomalies: 22" in sanitized
    assert "Memory anomalies: 9" in sanitized

    assert "packet loss" not in sanitized.lower()
    assert "restart impala" not in sanitized.lower()


def test_sanitizer_rewrites_unproven_stats_freshness_claims():
    module = load_report_module()

    facts = """
# Analysis Facts

## Action Cards
- Table/column stats freshness unless parsed from context.
"""
    report = """
# Query Doctor Report

## Что НЕ подтверждается фактами

- Нет информации о статистике таблиц/столбцов, кроме того, что она может быть устаревшей или отсутствовать.
"""

    sanitized = module.sanitize_report_text(report, facts)

    assert "может быть устаревшей" not in sanitized
    assert "отсутствовать" not in sanitized
    assert "Свежесть статистики таблиц/столбцов не подтверждена в analyzer facts" in sanitized


def test_report_validator_rejects_primary_bottleneck_overclaim():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = """
# Query Doctor Report

## Краткий вывод

- Оператор 02:HASH JOIN может быть основным источником узкого места.
"""

    errors = module.validate_report_against_facts(report, facts)

    assert "primary/root bottleneck" in " ".join(errors)


def test_sanitizer_rewrites_primary_bottleneck_overclaim():
    module = load_report_module()
    facts = "# Query Doctor deterministic analysis facts\n\n## Summary\n\n- Memory anomalies: 2\n"
    report = "- Оператор 02:HASH JOIN может быть основным источником узкого места."

    sanitized = module.sanitize_report_text(report, facts)

    assert "основным источником узкого места" not in sanitized
    assert "нет прямого causal evidence" in sanitized


def sample_prompt(module, mode="admin"):
    return module.build_prompt(
        facts_text="""
# Query Doctor deterministic analysis facts

## Action Cards

### Card 1: Severe cardinality underestimation before high-cost operator

Finding:
- Severe deterministic evidence was detected for 08:HASH JOIN.
""",
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode=mode,
    )


def safe_structured_report() -> str:
    return """
# Query Doctor Report

## Краткий вывод

- Основной подтверждённый факт: оператор 00:UNION имеет 1 фактическую строку и 1 оценённую строку.
- Оценка строк для 00:UNION совпадает с фактическим количеством строк.
- Profile-level facts показывают маленький baseline без выраженной нагрузки.
- Подтверждённая оптимизационная цель для этого baseline не выделена.

## Практические рекомендации

- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.
- Не менять SQL shape по этому профилю: текущие facts не показывают дорогой оператор или рост intermediate rows.
- Запускать дальнейшие изменения только если новый профиль покажет confirmed operator evidence.

## Подробный разбор

### Основные подтверждённые проблемы по профилю

- Нет подтверждённых проблем с оценкой строк или памяти.

### Подтверждающие факты

- Оператор 00:UNION имеет 1 фактическую строку и 1 оценённую строку, соотношение 1.00x.

### Что усиливает проблему

- Нет подтверждённых факторов, усиливающих проблему.

### Что НЕ подтверждается фактами

- Анализатор не обнаружил подтверждённой аномалии кардинальности.

### Follow-up checks

- Сравнить новый analysis_facts.md с этим baseline.
"""


def safe_model_body(extra_detail: str = "") -> str:
    lines = safe_structured_report().splitlines()
    start = next(i for i, line in enumerate(lines) if line == "## Краткий вывод")
    body = "\n".join(lines[start:]).strip() + "\n"
    if extra_detail:
        body = body.replace(
            "### Подтверждающие факты\n\n",
            f"### Подтверждающие факты\n\n{extra_detail}\n",
            1,
        )
    return body


def safe_english_model_body() -> str:
    return (
        """
## Short Summary

- Backend data skew is supported by RowsProduced, while host tail candidates are 0.
- The query wall-clock is available as bounded Cloudera Manager context with high confidence.
- Metadata facts are available for one referenced table and show incomplete or unknown column statistics.
- Spill or scratch evidence is present as a deterministic finding, so memory-pressure wording stays tied to that evidence.

## Practical Recommendations

- Collect statistics for affected tables where facts show missing or incomplete stats.
- Reduce memory pressure tied to confirmed spill/scratch evidence by reducing intermediate data before memory-heavy operators.
- After the change, capture a new profile and compare confirmed facts: wall-clock, host-tail evidence, operator rows/memory, and runtime metrics context.

## Detailed Analysis

### Supported Profile Findings

- Backend rows were parsed and RowsProduced distribution is uneven across backends.
- Spill or scratch evidence is present in the deterministic findings.

### Supporting Evidence

- Summary facts report 9 parsed operators, no confirmed cardinality anomaly, no memory anomaly, and a bounded query wall-clock.
- Backend facts report host tail candidates as 0 and execution skew as no.

### Amplifying Factors

- The available metadata context can support approved stats maintenance, but it does not prove a root cause by itself.
- Runtime context is useful only as bounded supporting context and must not be promoted into a standalone cause.

### What Is Not Supported By Facts

- analysis_facts.md has no confirmed cardinality anomaly; do not claim cardinality underestimation without a matching fact.
- A single slow backend, external network fault, HDFS fault, and write-path cause are not proven by the parsed facts.

### Follow-up checks

- Compare the next profile against this baseline using the same deterministic facts and validation boundary.
- Send backend and host-tail evidence to the platform team only as bounded follow-up context.
""".strip()
        + "\n"
    )


def backend_fact_text() -> str:
    return """
# Query Doctor deterministic analysis facts

## Totals

- TotalTime: 10s
- TotalBytesRead: 1 GiB
- TotalBytesSent: 2 MiB

## Query Wall Clock

- duration: 1.50m
- source: CM Query Context
- confidence: high

## Evidence Quality

- score: 90/100
- level: high

### Strengths

- profile operators parsed: 9
- query wall-clock available from CM Query Context

### Limitations

- CM metrics context is unavailable

## Summary

- Parsed operators: 9
- Cardinality anomalies: 0
- Memory anomalies: 0
- Zero/unknown row estimate gaps: 2
- Zero/unknown memory estimate gaps: 1

## Backend / Host Tail Evidence

### Summary

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown

### Normalized tail candidates

| host | fragment | family | metric_key | worst | peer | gap | ratio |
|---|---|---|---|---:|---:|---:|---:|
| host_01 | F03 | execution | execution_time_ms | 54.00m | 26.40m | 27.60m | 2.05x |

### Host tail candidates

- none

## Referenced Tables

- `example_db1.table_a`
- `example_db2.table_b`

## Table Metadata Context

- context file: present
- table metadata facts: supported
- tables requested: 1
- read-only statements only: yes

### Table: example_db1.table_a

- SHOW CREATE TABLE status: ok
- SHOW TABLE STATS status: ok
- SHOW COLUMN STATS status: ok
- table stats rows: 123456
- table stats row-count completeness: available
- table stats size: 1.2 GiB
- column stats columns observed: 2
- column stats missing/unknown markers: 1
- column stats completeness: incomplete/unknown
- column stats columns: `id`, `amount`
- file format: PARQUET
- partition columns: `ds`

## Action Cards

No deterministic action cards were triggered from the parsed evidence.

## Findings

### Spill or scratch I/O [medium]

- Detected non-zero spill/scratch metric evidence in digest lines.

## What is NOT supported by the parsed evidence

- write-path anomaly: unknown
- status: not_observed
- No parsed actual-vs-estimated row count anomaly above threshold.
""".strip()


def metadata_fact_text_with_raw_context_noise() -> str:
    return """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 9
- Cardinality anomalies: 1
- Memory anomalies: 0

## Referenced Tables

- `example_db1.table_a`
- `example_db2.table_b`

## Table Metadata Context

- context file: present
- table metadata facts: supported
- tables requested: 2
- read-only statements only: yes

### Table: example_db1.table_a

- object type: table
- SHOW CREATE TABLE status: ok
- SHOW TABLE STATS status: ok
- SHOW COLUMN STATS status: ok
- table stats rows: unknown
- table stats row-count completeness: missing/unknown
- table stats size: 34B
- column stats columns observed: 3
- column stats missing/unknown markers: 8
- column stats completeness: incomplete/unknown
- column stats columns: `id`, `amount`
- file format: PARQUET
- partition columns: `ds`
- raw DDL: CREATE TABLE example_db1.table_a(raw_secret STRING)
- raw stats table: | #Rows | Size |
- impala_context.json: {"raw":"do not include"}

### Table: example_db2.table_b

- object type: view
- SHOW CREATE TABLE status: too_large
- SHOW TABLE STATS status: not_collected
- SHOW COLUMN STATS status: ok
- table stats rows: unknown
- table stats row-count completeness: not_available
- table stats size: unknown
- column stats columns observed: 0
- column stats missing/unknown markers: 0
- column stats completeness: not_available
- file format: unknown
- partition columns: unknown

## Action Cards

No deterministic action cards were triggered from the parsed evidence.
""".strip()


def cm_metrics_fact_text_with_timeseries_context() -> str:
    return """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 9
- Cardinality anomalies: 1
- Memory anomalies: 1

## CM Time-Series Context

- available: yes
- window: 2026-05-04T09:59:00Z to 2026-05-04T10:06:00Z

### Host network I/O

- status: ok
- point_count: 10
- min: 1048576.00
- max: 209715200.00
- avg: 20971520.00
- latest: 8388608.00

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- host_cpu_pressure: not_observed
- host_cpu_pressure_basis: host_cpu_user max=22.00 avg=5.00; host_cpu_system max=3.00
- daemon_memory_growth: observed
- daemon_memory_growth_basis: daemon memory min=10.00 GiB max=23.00 GiB delta=13.00 GiB ratio=2.30x
- daemon_memory_pressure: unknown
- daemon_memory_pressure_basis: daemon memory capacity or limit is not part of the current safe runtime metrics contract
- network_io_spike: observed
- network_io_spike_basis: host network I/O max=200.00 MiB/s avg=20.00 MiB/s ratio=10.00x

### CM metrics limitations

- CM metrics are bounded query-window context signals, not standalone proof of cause.
- Raw metric points and per-point times are intentionally excluded from trusted analysis facts.

## Action Cards

### Card 1: Severe memory underestimation at high-memory operator

Evidence:
- operator: 19:HASH JOIN
- peak memory: 43.40 GiB
- estimated peak memory: 125.81 KiB
- peak/estimated memory ratio: 361720x
""".strip()


def cluster_event_fact_text() -> str:
    return """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 9
- Cardinality anomalies: 1
- Memory anomalies: 0

## Cluster Event Context

- status: degraded_service_candidate
- available: yes
- source_status: cm_events=ok/degraded_service_candidate
- window_scope: service_scope=IMPALA-1, window_minutes=60, max_events=10, alerts_only=false, severity_filter=critical,important,informational
- signal_counts: impala_daemon_error_event=3, catalog_error_event=1
- guardrail: Cluster context is a deterministic raw-free summary. It can guide operational checks, not prove root cause.

### CM event signal rollup

- impala_daemon_error_event: status=observed, severity=critical, events=3, claim_level=cluster_candidate
- catalog_error_event: status=observed, severity=important, events=1, claim_level=cluster_candidate

### CM event next checks

- Check Impala service health, daemon errors, and affected query windows.
- Check catalog service health and metadata propagation delay.

### CM event limitations

- Raw event content, log lines, event ids, hostnames, principals, paths, and query text are excluded.
- Cluster context is not standalone root-cause proof.
""".strip()


def test_report_mode_defaults_to_admin():
    module = load_report_module()

    args = module.parse_args(["case-dir", "--dry-prompt"])

    assert args.mode == "admin"


def test_report_mode_admin_is_accepted():
    module = load_report_module()

    args = module.parse_args(["case-dir", "--mode", "admin", "--dry-prompt"])

    assert args.mode == "admin"


def test_report_mode_user_is_accepted():
    module = load_report_module()

    args = module.parse_args(["case-dir", "--mode", "user", "--dry-prompt"])

    assert args.mode == "user"


def test_report_language_arg_is_normalized_before_validation():
    module = load_report_module()

    args = module.parse_args(["case-dir", "--language", " RU ", "--dry-prompt"])

    assert args.language == "ru"


def test_report_language_arg_rejects_unknown_language():
    module = load_report_module()

    with pytest.raises(SystemExit):
        module.parse_args(["case-dir", "--language", "de", "--dry-prompt"])


def test_report_mode_invalid_is_rejected():
    module = load_report_module()

    with pytest.raises(SystemExit):
        module.parse_args(["case-dir", "--mode", "invalid", "--dry-prompt"])


def test_admin_prompt_contains_admin_specific_instructions():
    module = load_report_module()

    prompt = sample_prompt(module, mode="admin")

    assert "Report mode: unified." in prompt
    assert "Audience: SQL owner first; DBA/platform details go into the admin section." in prompt
    assert "Use Action Cards as the main structure when present." in prompt
    assert "per-host RowsProduced / PeakMemUsage" in prompt


def test_admin_prompt_requires_concrete_next_checks_section():
    module = load_report_module()

    prompt = sample_prompt(module, mode="admin")

    assert "Follow-up checks" in prompt
    assert "<details>" not in prompt
    assert "per-host RowsProduced" in prompt
    assert "PeakMemUsage" in prompt
    assert "spill/scratch" in prompt
    assert "admission pool" in prompt
    assert "CM metrics/logs" in prompt
    assert "profile counter" in prompt


def test_user_prompt_contains_user_specific_instructions():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert "Report mode: unified." in prompt
    assert (
        "Audience: SQL query author, analyst, or data engineer first; DBA/platform details go into the admin section."
        in prompt
    )
    assert "explain them in simpler language" in prompt
    assert "Put admin/platform checks and evidence packages only under" in prompt


def test_user_prompt_requires_read_only_stats_checks():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert "approved stats maintenance" in prompt
    assert "concrete SQL-owner actions" in prompt
    assert (
        "Do not tell users to run COMPUTE STATS, REFRESH, or INVALIDATE METADATA as automatic actions."
        in prompt
    )
    assert "через утверждённый operational process" in prompt


def test_user_prompt_requires_admin_escalation_package():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert "Put admin/platform checks and evidence packages only under" in prompt
    assert "analysis_facts.md" in prompt
    assert "Follow-up checks" in prompt


def test_user_prompt_forbids_inventing_missing_escalation_facts():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert (
        "Do not invent table names, join/filter column names, query id, timestamps, pool names, or commands."
        in prompt
    )


def test_user_prompt_does_not_make_state_changing_stats_automatic():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert (
        "Do not tell users to run COMPUTE STATS, REFRESH, or INVALIDATE METADATA as automatic actions."
        in prompt
    )


def test_user_prompt_forbids_unproven_stale_or_missing_stats_claims():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert (
        "Do not say facts indicate stale or missing stats unless analysis_facts.md explicitly proves that."
        in prompt
    )
    assert "через утверждённый operational process" in prompt


def test_prompt_for_zero_cardinality_anomalies_forbids_underestimation_claims():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text="""
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
""",
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="user",
    )

    assert "analysis_facts.md says Cardinality anomalies: 0." in prompt
    assert "No analyzer-supported cardinality anomaly was found." in prompt
    assert "Do not claim cardinality underestimation" in prompt
    assert (
        "Do not recommend stats maintenance from Cardinality anomalies alone when the count is 0."
        in prompt
    )
    assert "Анализатор не обнаружил подтверждённой аномалии кардинальности." in prompt
    assert "недооценка кардинальности" in prompt
    assert "omit stats maintenance unless separate metadata facts support it" in prompt


def test_prompt_contains_estimate_direction_contract_and_safe_heading():
    module = load_report_module()

    prompt = sample_prompt(module, mode="admin")

    assert (
        "Row/cardinality underestimation means actual rows are larger than estimated rows" in prompt
    )
    assert (
        "Row/cardinality overestimation means actual rows are smaller than estimated rows" in prompt
    )
    assert (
        'Use "estimate mismatch" / "estimate gap" when estimate direction is mixed or unclear.'
        in prompt
    )
    assert (
        "Do not describe an operator as row/cardinality-underestimated when its evidence line shows actual rows < estimated rows or ratio < 1."
        in prompt
    )
    assert "Memory underestimation is separate from row/cardinality underestimation." in prompt
    assert (
        "Memory underestimation means actual/peak memory is larger than estimated memory" in prompt
    )
    assert "Memory overestimation means actual/peak memory is lower than estimated memory" in prompt
    assert "Do not call actual/estimated memory ratio below 1 memory underestimation." in prompt
    assert (
        "Do not present Impala operator/profile counter time as query wall-clock duration" in prompt
    )
    assert "operator/profile time counter" in prompt
    assert "## Краткий вывод" in prompt
    assert "## Подробный разбор" in prompt
    assert "### Основные подтверждённые проблемы по профилю" in prompt
    assert '"Краткий вывод" requirements:' in prompt
    assert "## Главная причина замедления" not in prompt
    assert "Root cause" in prompt


def test_report_validator_accepts_short_and_detailed_structure_when_safe():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 00:UNION | 0ms | 1 | 1 | 1.00x | 0 B | n/a | n/a |
"""

    report = module.normalize_report_text(safe_structured_report(), facts_text=facts)
    errors = module.validate_report_text(
        report,
        facts_text=facts,
        min_chars=0,
        min_sections=0,
    )

    assert errors == []


def test_report_validator_rejects_visible_runtime_or_artifact_fingerprints():
    module = load_report_module()

    report = safe_structured_report().replace(
        "# Query Doctor Report",
        "# Query Doctor Report\n\n> Source facts: `analysis_facts.md`\n> Source metadata: `query_metadata.json`\n> Model: `qwen3-coder:30b`",
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "report contains browser-visible internal artifact/runtime fingerprint" in errors


def test_report_normalizer_removes_legacy_collapsed_detail_markup():
    module = load_report_module()

    report = (
        safe_structured_report()
        .replace(
            "## Подробный разбор",
            "<details>\n<summary>Подробный разбор</summary>\n\n## Подробный разбор",
            1,
        )
        .replace("### Follow-up checks", "</details>\n\n### Follow-up checks", 1)
    )

    normalized = module.normalize_report_text(report, facts_text="# Analysis Facts\n")

    assert "<details>" not in normalized
    assert "<summary>" not in normalized
    assert module.validate_report_text(normalized, min_chars=0, min_sections=0) == []


def test_report_validator_rejects_unapproved_raw_html():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Сравнить новый analysis_facts.md с этим baseline.",
        "- Сравнить новый analysis_facts.md с этим baseline.\n<div>unsafe</div>",
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "report contains unsupported raw HTML tag: div" in errors


def _report_with_extra_recommendation(extra_text: str) -> str:
    return safe_structured_report().replace(
        "- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
        "- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.\n"
        + extra_text,
        1,
    )


def _raw_sql_validation_errors(module, extra_text: str) -> list[str]:
    return module.validate_report_text(
        _report_with_extra_recommendation(extra_text),
        min_chars=0,
        min_sections=0,
    )


def test_report_validator_rejects_fenced_sql_code_block():
    module = load_report_module()

    errors = _raw_sql_validation_errors(
        module,
        "- Unsafe detail:\n\n```sql\nSELECT * FROM example_db.example_table\n```",
    )

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


def test_report_validator_rejects_untagged_fence_containing_select_from():
    module = load_report_module()

    errors = _raw_sql_validation_errors(
        module,
        "- Unsafe detail:\n\n```\nSELECT col_a FROM example_db.example_table WHERE col_a > 0\n```",
    )

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


def test_report_validator_rejects_inline_select_from():
    module = load_report_module()

    errors = _raw_sql_validation_errors(
        module,
        "- Unsafe detail: SELECT col_a FROM example_db.example_table WHERE col_a > 0",
    )

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


@pytest.mark.parametrize(
    "snippet",
    [
        "Unsafe prose says SELECT col_a FROM example_db.example_table WHERE col_a > 0.",
        "Unsafe prose says select col_a from example_db.example_table where col_a > 0.",
        "Unsafe prose includes SELECT col_a FROM unsafe_table WHERE col_a > 0.",
        "Unsafe prose includes WITH c AS (SELECT col_a FROM example_db.source_table) SELECT col_a FROM c.",
        "Unsafe prose includes INSERT INTO example_db.target_table SELECT col_a FROM example_db.source_table.",
        "Unsafe prose includes SHOW TABLE STATS example_db.example_table.",
    ],
)
def test_report_validator_rejects_inline_sql_like_prose(snippet):
    module = load_report_module()

    errors = _raw_sql_validation_errors(module, f"- {snippet}")

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


def test_report_validator_handles_bounded_pathological_unclosed_sql_fence():
    module = load_report_module()
    extra = "\n".join(
        ["- Unsafe detail:", "```"]
        + [f"safe diagnostic context {index}: " + ("x" * 80) for index in range(450)]
        + ["SELECT col_a FROM example_db.example_table WHERE col_a > 0"]
    )

    errors = _raw_sql_validation_errors(module, extra)

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


def test_report_validator_rejects_with_select_from():
    module = load_report_module()

    errors = _raw_sql_validation_errors(
        module,
        "- Unsafe detail: WITH c AS (SELECT col_a FROM example_db.source_table) SELECT col_a FROM c",
    )

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


@pytest.mark.parametrize(
    "snippet",
    [
        "INSERT INTO example_db.target_table SELECT col_a FROM example_db.source_table",
        "CREATE TABLE example_db.target_table AS SELECT col_a FROM example_db.source_table",
        "DROP TABLE example_db.target_table",
        "ALTER TABLE example_db.target_table RENAME TO example_db.other_table",
        "TRUNCATE TABLE example_db.target_table",
        "DELETE FROM example_db.target_table WHERE col_a = 1",
        "UPDATE example_db.target_table SET col_a = 1",
        "MERGE INTO example_db.target_table USING example_db.source_table ON id = id",
    ],
)
def test_report_validator_rejects_raw_dml_and_ddl_like_snippets(snippet):
    module = load_report_module()

    errors = _raw_sql_validation_errors(module, f"- Unsafe detail: {snippet}")

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


@pytest.mark.parametrize(
    "snippet",
    [
        "SHOW CREATE TABLE example_db.example_table",
        "SHOW TABLE STATS example_db.example_table",
        "SHOW COLUMN STATS example_db.example_table",
    ],
)
def test_report_validator_rejects_raw_show_metadata_command_snippets(snippet):
    module = load_report_module()

    errors = _raw_sql_validation_errors(module, f"- Unsafe detail: {snippet}")

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


def test_report_validator_allows_generic_sql_safety_prose():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Сравнить новый analysis_facts.md с этим baseline.",
        "- Сравнить новый analysis_facts.md с этим baseline.\n"
        + "\n".join(
            [
                "- The query may benefit from reviewing join order.",
                "- SQL text is not displayed in the report.",
                "- Query text is redacted before trusted output.",
                "- Check predicates and table statistics.",
                "- Metadata was collected using read-only allowlisted commands.",
                "- No raw SQL is included.",
                "- SHOW CREATE TABLE is part of the internal read-only metadata allowlist.",
            ]
        ),
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert errors == []


def test_report_validator_rejects_open_ended_practical_recommendations():
    module = load_report_module()

    report = _report_with_extra_recommendation(
        "\n".join(
            [
                "- Check predicates and table statistics.",
            ]
        )
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "practical recommendations contain open-ended check/analyze/optimize wording" in errors


def test_report_validator_rejects_admin_checks_in_practical_recommendations():
    module = load_report_module()

    report = _report_with_extra_recommendation("- Run SHOW TABLE STATS for the referenced table.")

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "practical recommendations contain admin-only checks" in errors


def test_report_normalizer_enforces_python_owned_practical_recommendations():
    module = load_report_module()

    report = safe_structured_report().replace(
        """- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.
- Не менять SQL shape по этому профилю: текущие facts не показывают дорогой оператор или рост intermediate rows.
- Запускать дальнейшие изменения только если новый профиль покажет confirmed operator evidence.""",
        """- Проверить, не создается ли много-ко-многим JOIN-амплификация перед SORT/ANALYTIC/AGGREGATE.
- Проверить, есть ли необходимость в переписывании формы JOIN/фильтра для уменьшения количества строк до операторов с высокой стоимостью.
- Run SHOW TABLE STATS for the referenced table.""",
        1,
    )
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 1
"""

    normalized = module.normalize_report_text(report, facts_text=facts)

    assert "Проверить, не создается ли" not in normalized
    assert "Проверить, есть ли необходимость" not in normalized
    assert "Run SHOW TABLE STATS" in normalized
    assert normalized.index("Run SHOW TABLE STATS") > normalized.index("### Follow-up checks")
    assert "Сократить рост строк" in normalized
    assert "Переписать форму JOIN/фильтра" in normalized
    assert (
        module.validate_report_text(normalized, facts_text=facts, min_chars=0, min_sections=0) == []
    )


def test_report_validator_rejects_recommendations_outside_python_owned_candidates():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
        "- Снизить сетевую задержку между Impala daemons.",
        1,
    )
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0
"""

    errors = module.validate_report_text(report, facts_text=facts, min_chars=0, min_sections=0)

    assert "practical recommendations include an action outside Python-owned candidates" in errors


def test_report_recommendations_preserve_python_owned_llm_wording():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
        "- Обновить статистику через утвержденный maintenance process для tables с estimate gaps.",
        1,
    )
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 0
"""

    normalized = module.normalize_report_text(report, facts_text=facts)

    assert (
        "- Обновить статистику через утвержденный maintenance process для tables с estimate gaps."
        in normalized
    )
    assert (
        module.validate_report_text(normalized, facts_text=facts, min_chars=0, min_sections=0) == []
    )


def test_report_recommendation_normalizer_falls_back_to_python_candidates_for_unsupported_actions():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
        "- Stats should be updated, and also rewrite the query using a new distributed cache.",
        1,
    )
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 0
"""

    normalized = module.normalize_report_text(report, facts_text=facts)

    assert "distributed cache" not in normalized
    assert "- Собрать или обновить статистику по затронутым таблицам" in normalized
    assert (
        module.validate_report_text(normalized, facts_text=facts, min_chars=0, min_sections=0) == []
    )


def test_exchange_recommendation_requires_large_data_movement_finding():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Totals

- TotalBytesSent: 2 MiB

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Findings

No large data movement finding.
"""

    candidates = module.recommendation_candidate_lines(facts)

    assert all(candidate_id != "reduce_exchange_rows" for candidate_id, _ in candidates)


def test_exchange_recommendation_ignores_negative_large_data_movement_lines():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Totals

- TotalBytesSent: 56.1 MiB

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## What is NOT supported by the parsed evidence

- TotalBytesSent was parsed below the large data-movement threshold: 56.1 MiB; do not treat it as large exchange traffic.
- No large exchange/network traffic evidence was parsed from TotalBytesSent or EXCHANGE operators.

## Findings

### Host-specific execution tail suspected [high]

- Execution skew is suspected from parsed backend execution-time counters.
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert "reduce_exchange_rows" not in candidate_ids
    assert "reduce_exchange_payload" not in candidate_ids


def test_stats_only_recommendations_do_not_add_generic_followup_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Table Metadata Context

- table metadata facts: supported
- tables requested: 1
- column stats completeness: incomplete/unknown
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert candidate_ids == ["stats_maintenance"]


def test_recommendation_candidates_use_structured_stats_quality_gap_without_legacy_metadata():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Stats Metadata Quality

- status: limited
- table_stats: available
- column_stats: incomplete/unknown
- tables_with_missing_table_stats: 0
- tables_with_incomplete_column_stats: 1
- row_estimate_evidence: not_observed
- row_estimate_issue_count: 0
- partition_coverage: available
- join_filter_column_relevance: partial
- join_filter_columns_observed: 3
- join_filter_columns_without_stats: 1
- join_filter_columns_with_complete_stats: 2
- join_filter_columns_with_ndv_missing_stats: 1
- join_filter_columns_with_size_missing_stats: 0
- join_filter_columns_with_all_missing_stats: 0
- join_filter_columns_with_unknown_stats: 0
- stats_primary_bottleneck: not_supported
- stats_context: stats_gap_without_row_estimate_evidence
- interpretation: Metadata shows missing or incomplete stats coverage.
- guardrail: Stats quality is follow-up evidence, not a standalone root cause.
"""

    candidates = module.recommendation_candidate_lines(facts, language="en")
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert candidate_ids == ["stats_maintenance"]


def test_recommendation_candidates_prefer_structured_not_applicable_stats_quality():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Stats Metadata Quality

- status: not_applicable
- table_stats: not_applicable
- column_stats: not_applicable
- row_estimate_evidence: not_observed
- row_estimate_issue_count: 0
- partition_coverage: unknown
- join_filter_column_relevance: unknown
- tables_with_missing_table_stats: 0
- tables_with_incomplete_column_stats: 0
- join_filter_columns_without_stats: 0
- join_filter_columns_with_ndv_missing_stats: 0
- join_filter_columns_with_size_missing_stats: 0
- join_filter_columns_with_all_missing_stats: 0
- join_filter_columns_with_unknown_stats: 0
- stats_primary_bottleneck: not_applicable
- stats_context: not_physical_table_stats
- interpretation: Referenced metadata is not physical-table stats evidence.

## Table Metadata Context

- table metadata facts: supported
- tables requested: 1
- column stats completeness: incomplete/unknown
"""

    candidates = module.recommendation_candidate_lines(facts, language="en")
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert "stats_maintenance" not in candidate_ids


def test_recommendation_candidates_include_safe_action_card_anchor():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 1

## Action Cards

### Card 1: Severe row growth before join

- operator: 07:HASH JOIN
- actual rows: 25.00M
- estimated rows: 10.55K
- actual/estimated ratio: 2369.67x
- peak memory: 8.00 GiB
- estimated peak memory: 256.00 MiB
- peak/estimated memory ratio: 32.00x
"""

    candidates = module.recommendation_candidate_lines(facts, language="en")
    candidate_text = "\n".join(text for _, text in candidates)

    assert "Action Card operator 07:HASH JOIN" in candidate_text
    assert "rows ratio 2369.67x" in candidate_text
    assert "memory ratio 32.00x" in candidate_text


def test_recommendation_normalizer_preserves_case_anchor_for_generic_llm_wording():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 1

## Action Cards

### Card 1: Severe row growth before join

- operator: 07:HASH JOIN
- actual/estimated ratio: 2369.67x
- peak/estimated memory ratio: 32.00x
"""
    report = safe_english_model_body().replace(
        "- Collect statistics for affected tables where facts show missing or incomplete stats.",
        "- Reduce row growth before JOIN inputs.",
        1,
    )

    normalized = module.normalize_report_text(report, facts_text=facts, language="en")

    assert "Action Card operator 07:HASH JOIN" in normalized
    assert "Reduce row growth before JOIN inputs." not in normalized


def test_large_exchange_recommendations_provide_minimum_strict_report_items():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Totals

- TotalBytesSent: 66.0 GiB

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]
    candidate_text = "\n".join(text for _, text in candidates)

    assert candidate_ids[:2] == ["reduce_exchange_rows", "reduce_exchange_payload"]
    assert "TotalBytesSent 66.0 GiB" in candidate_text
    assert len(candidates) >= 2


def test_cm_memory_growth_without_strong_memory_evidence_does_not_add_optimizer_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- host_cpu_pressure: not_observed
- daemon_memory_growth: observed
- daemon_memory_growth_basis: daemon memory min=10.00 GiB max=23.00 GiB delta=13.00 GiB ratio=2.30x
- daemon_memory_pressure: unknown
- network_io_spike: not_observed
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]
    candidate_text = "\n".join(text for _, text in candidates)

    assert "reduce_runtime_memory_footprint" not in candidate_ids
    assert candidate_ids == ["no_shape_change"]
    assert "root cause" not in candidate_text.lower()


def test_correlated_memory_metric_adds_runtime_memory_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Runtime Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed

## Runtime Metrics Correlation

- status: available
- coverage: 4/4 metrics ok, 40 points
- correlated_signals: 1
- context_only_signals: 0
- daemon_memory_growth: correlated (metric=observed, strength=moderate)
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]
    candidate_text = "\n".join(text for _, text in candidates)

    assert "reduce_runtime_memory_footprint" in candidate_ids
    assert "root cause" not in candidate_text.lower()


def test_cm_metrics_context_only_correlation_does_not_add_optimizer_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- host_cpu_pressure: not_observed
- daemon_memory_growth: observed
- daemon_memory_pressure: unknown
- network_io_spike: not_observed

## CM Metrics Correlation

- status: available
- coverage: 4/4 metrics ok, 40 points
- correlated_signals: 0
- context_only_signals: 1
- guardrail: CM metrics can strengthen profile-supported evidence, but they are not standalone root-cause proof.

- daemon_memory_growth: context_only (metric=observed, strength=weak)
  - basis: daemon memory min=10.00 GiB max=23.00 GiB delta=13.00 GiB ratio=2.30x
  - interpretation: Daemon memory growth was observed, but selected-query non-zero spill/scratch evidence was not parsed.
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert "reduce_runtime_memory_footprint" not in candidate_ids
    assert candidate_ids == ["no_shape_change"]


def test_runtime_metrics_context_only_correlation_does_not_add_optimizer_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Runtime Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed

## Runtime Metrics Correlation

- status: available
- coverage: 4/4 metrics ok, 40 points
- correlated_signals: 0
- context_only_signals: 1
- daemon_memory_growth: context_only (metric=observed, strength=weak)
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert "reduce_runtime_memory_footprint" not in candidate_ids
    assert candidate_ids == ["no_shape_change"]


def test_cm_metrics_unknown_or_not_observed_do_not_add_optimizer_candidates():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- host_cpu_pressure: not_observed
- daemon_memory_growth: unknown
- daemon_memory_pressure: unknown
- network_io_spike: not_observed
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert candidate_ids == ["no_shape_change"]


def test_cm_network_spike_requires_profile_exchange_evidence_for_optimizer_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Totals

- TotalBytesSent: 2 MiB

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Findings

No large data movement finding.

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- host_cpu_pressure: not_observed
- daemon_memory_growth: not_observed
- daemon_memory_pressure: unknown
- network_io_spike: observed
- network_io_spike_basis: host network I/O max=200.00 MiB/s avg=20.00 MiB/s ratio=10.00x
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert "align_exchange_with_network_context" not in candidate_ids
    assert candidate_ids == ["no_shape_change"]


def test_cm_network_spike_can_prioritize_profile_supported_exchange_candidate():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Totals

- TotalBytesSent: 66.0 GiB

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## Findings

### Large intermediate or exchange traffic [high]

- TotalBytesSent is large relative to the configured threshold.

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- host_cpu_pressure: not_observed
- daemon_memory_growth: not_observed
- daemon_memory_pressure: unknown
- network_io_spike: observed
- network_io_spike_basis: host network I/O max=200.00 MiB/s avg=20.00 MiB/s ratio=10.00x
"""

    candidates = module.recommendation_candidate_lines(facts)
    candidate_ids = [candidate_id for candidate_id, _ in candidates]

    assert "reduce_exchange_rows" in candidate_ids
    assert "reduce_exchange_payload" in candidate_ids
    assert "align_exchange_with_network_context" in candidate_ids


def test_relaxed_validation_allows_shape_errors_but_keeps_safety_checks():
    module = load_report_module()

    shape_broken_report = "# Query Doctor Report\n\n## Краткий вывод\n\n- One item.\n"

    assert module.validate_report_text(shape_broken_report, min_chars=0, min_sections=0)
    assert (
        module.validate_report_for_mode(
            shape_broken_report,
            validation_mode="relaxed",
        )
        == []
    )

    unsafe_report = "# Query Doctor Report\n\n## Краткий вывод\n\n- SELECT * FROM unsafe_table.\n"

    assert (
        "report contains SQL-like text that is not allowed in trusted output"
        in module.validate_report_for_mode(
            unsafe_report,
            validation_mode="relaxed",
        )
    )


def test_report_validator_raw_sql_error_does_not_echo_snippet():
    module = load_report_module()

    errors = _raw_sql_validation_errors(
        module,
        "- Unsafe detail: SELECT col_a FROM example_db.example_table WHERE col_a = 'synthetic_value'",
    )
    error_text = "\n".join(errors)

    assert "report contains SQL-like text that is not allowed in trusted output" in errors
    assert "SELECT" not in error_text
    assert "example_db" not in error_text
    assert "synthetic_value" not in error_text


def test_analyzer_facts_appendix_renderer_preserves_key_facts():
    module = load_report_module()

    appendix = module.render_analyzer_facts_appendix(backend_fact_text())

    assert appendix.strip().startswith("## Факты анализатора")
    assert "<details>" not in appendix
    assert "## Факты анализатора" in appendix
    assert "- Parsed operators: 9" in appendix
    assert "- Cardinality anomalies: 0" in appendix
    assert "- Memory anomalies: 0" in appendix
    assert "- Zero/unknown row estimate gaps: 2" in appendix
    assert "- Zero/unknown memory estimate gaps: 1" in appendix
    assert "- TotalBytesRead: 1 GiB" in appendix
    assert "- query wall-clock duration: 1.50m" in appendix
    assert "- query wall-clock source: CM Query Context" in appendix
    assert "- query wall-clock confidence: high" in appendix
    assert "### Evidence Quality" in appendix
    assert "- score: 90/100" in appendix
    assert "- level: high" in appendix
    assert "#### Strengths" in appendix
    assert "- profile operators parsed: 9" in appendix
    assert "#### Limitations" in appendix
    assert "- CM metrics context is unavailable" in appendix
    assert "- backend rows parsed: 21" in appendix
    assert "- data skew: yes (rows produced max/min ratio is 1720x)" in appendix
    assert "- execution skew: no" in appendix
    assert "- write-path anomaly: unknown" in appendix
    assert "### Normalized tail candidates" in appendix
    assert (
        "| host_01 | F03 | execution | execution_time_ms | 54.00m | 26.40m | 27.60m | 2.05x |"
        in appendix
    )
    assert "### Referenced Tables" in appendix
    assert "- `example_db1.table_a`" in appendix
    assert "- `example_db2.table_b`" in appendix
    assert "### Table Metadata Context" in appendix
    assert "- table stats rows: 123456" in appendix
    assert "- table stats row-count completeness: available" in appendix
    assert "- column stats columns observed: 2" in appendix
    assert "- column stats completeness: incomplete/unknown" in appendix
    assert "- file format: PARQUET" in appendix
    assert "not_observed" in appendix
    assert "причина" not in appendix.lower()


def test_backend_tail_summary_parser_uses_execution_tail_candidate_count():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

### Summary

- host tail candidates: 1
- execution tail candidates: 0
- read-rate tail candidates: 1
- write-path tail candidates: 1
- data skew: no
- execution skew: yes
- write-path anomaly: yes
"""

    summary = module.parse_backend_tail_summary(facts)

    assert summary["host tail candidates"] == 1
    assert summary["execution tail candidates"] == 0
    assert summary["read-rate tail candidates"] == 1
    assert summary["write-path tail candidates"] == 1
    assert module.backend_has_proven_tail(summary) is False


def test_appendix_strips_model_written_facts_section_and_appends_python_section():
    module = load_report_module()
    report = safe_structured_report() + "\n## Факты анализатора\n\n- model invented fact\n"

    final_report = module.append_analyzer_facts_appendix(report, backend_fact_text())

    assert final_report.count("## Факты анализатора") == 1
    assert "<summary>Факты анализатора</summary>" not in final_report
    assert "model invented fact" not in final_report
    assert "- Parsed operators: 9" in final_report


def test_final_report_with_python_appendix_still_validates():
    module = load_report_module()
    facts = backend_fact_text()

    final_report = module.append_analyzer_facts_appendix(
        module.normalize_report_text(safe_structured_report(), facts_text=facts),
        facts,
    )

    errors = module.validate_report_text(
        final_report,
        facts_text=facts,
        min_chars=0,
        min_sections=0,
    )

    assert errors == []
    assert "<details>" not in final_report
    assert "</details>" not in final_report


def test_report_validator_rejects_sql_in_report_body():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Сравнить новый analysis_facts.md с этим baseline.",
        "- SELECT col_a FROM db.table_a",
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "report contains SQL-like text that is not allowed in trusted output" in errors


def test_report_detects_top_level_referenced_tables_section():
    module = load_report_module()

    assert module.facts_include_referenced_tables(
        "# Facts\n\n## Referenced Tables\n\n- `example_db1.table_a`\n"
    )
    assert not module.facts_include_referenced_tables(
        "# Facts\n\n## Referenced Tables\n\n- not_observed: no referenced table names were parsed.\n"
    )


def test_report_validator_rejects_missing_short_summary_section():
    module = load_report_module()

    report = safe_structured_report().replace("## Краткий вывод", "## Вывод", 1)

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "missing required section: ## Краткий вывод" in errors


def test_report_validator_rejects_missing_detailed_section():
    module = load_report_module()

    report = safe_structured_report().replace("## Подробный разбор", "## Детали", 1)

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "missing required section: ## Подробный разбор" in errors


def test_report_validator_rejects_short_summary_with_too_few_items():
    module = load_report_module()

    report = safe_structured_report().replace(
        """- Основной подтверждённый факт: оператор 00:UNION имеет 1 фактическую строку и 1 оценённую строку.
- Оценка строк для 00:UNION совпадает с фактическим количеством строк.
- Profile-level facts показывают маленький baseline без выраженной нагрузки.
- Подтверждённая оптимизационная цель для этого baseline не выделена.""",
        """- Основной подтверждённый факт: оператор 00:UNION имеет 1 фактическую строку и 1 оценённую строку.""",
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "short summary must contain 2-6 concise items, found 1" in errors


def test_report_validator_rejects_short_summary_with_too_many_items():
    module = load_report_module()

    report = safe_structured_report().replace(
        "- Подтверждённая оптимизационная цель для этого baseline не выделена.",
        """- Подтверждённая оптимизационная цель для этого baseline не выделена.
- Безопасный пункт 5: новых фактов не добавлено.
- Безопасный пункт 6: новых фактов не добавлено.
- Безопасный пункт 7: новых фактов не добавлено.
- Безопасный пункт 8: новых фактов не добавлено.""",
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert "short summary must contain 2-6 concise items, found 8" in errors


def test_report_validator_accepts_short_summary_paragraph_items():
    module = load_report_module()

    report = safe_structured_report().replace(
        """- Основной подтверждённый факт: оператор 00:UNION имеет 1 фактическую строку и 1 оценённую строку.
- Оценка строк для 00:UNION совпадает с фактическим количеством строк.
- Profile-level facts показывают маленький baseline без выраженной нагрузки.
- Подтверждённая оптимизационная цель для этого baseline не выделена.""",
        """Основной подтверждённый факт: оператор 00:UNION имеет 1 фактическую строку и 1 оценённую строку.

Оценка строк для 00:UNION совпадает с фактическим количеством строк.

Profile-level facts показывают маленький baseline без выраженной нагрузки.

Подтверждённая оптимизационная цель для этого baseline не выделена.""",
        1,
    )

    errors = module.validate_report_text(report, min_chars=0, min_sections=0)

    assert errors == []


def test_query_wall_clock_duration_wording_is_rejected_and_normalized():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
""".strip()
    report = safe_structured_report().replace(
        "- Profile-level facts показывают маленький baseline без выраженной нагрузки.",
        "- Запрос выполнялся 9.70h.",
        1,
    )

    errors = module.validate_report_text(report, facts_text=facts, min_chars=0, min_sections=0)
    sanitized = module.sanitize_report_text(report, facts)

    assert any("operator time is presented as wall-clock duration" in error for error in errors)
    assert "Запрос выполнялся 9.70h" not in sanitized
    assert "это не обязательно равно полной wall-clock длительности запроса" in sanitized


def test_operator_name_before_russian_operator_time_is_rejected_and_normalized():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
""".strip()
    unsafe_line = "- EXCHANGE оператор (05) обрабатывает 11.41K строк, время выполнения 108ms."
    report = safe_structured_report().replace(
        "- Profile-level facts показывают маленький baseline без выраженной нагрузки.",
        unsafe_line,
        1,
    )

    errors = module.validate_report_text(report, facts_text=facts, min_chars=0, min_sections=0)
    sanitized = module.sanitize_report_text(report, facts)

    assert any("operator time is presented as wall-clock duration" in error for error in errors)
    assert "время выполнения 108ms" not in sanitized
    assert "operator/profile time counter" in sanitized


def test_streamed_report_body_is_buffered_without_stdout(monkeypatch, capsys):
    module = load_report_module()
    from query_doctor.report import llm_client

    unsafe_chunk = "запрос выполнялся 9.70h"

    class FakeResponse:
        def __init__(self):
            self.lines = [
                module.json.dumps({"message": {"content": unsafe_chunk}}).encode("utf-8"),
                module.json.dumps({"done": True}).encode("utf-8"),
            ]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self, size=-1):
            if not self.lines:
                return b""
            return self.lines.pop(0)[:size]

    monkeypatch.setattr(
        llm_client, "configured_diagnostic_urlopen", lambda *args, **kwargs: FakeResponse()
    )

    body = module.stream_ollama_report(
        prompt="prompt",
        model="model",
        ollama_url="http://localhost:11434",
        temperature=0.1,
        keep_alive="0",
    )
    captured = capsys.readouterr()

    assert body == unsafe_chunk
    assert unsafe_chunk not in captured.out
    assert unsafe_chunk not in captured.err


def test_bad_ollama_json_line_does_not_print_raw_content(monkeypatch, capsys):
    module = load_report_module()
    from query_doctor.report import llm_client

    unsafe_chunk = "запрос выполнялся 9.70h"

    class FakeResponse:
        def __init__(self):
            self.lines = [
                unsafe_chunk.encode("utf-8"),
                module.json.dumps({"done": True}).encode("utf-8"),
            ]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def readline(self, size=-1):
            if not self.lines:
                return b""
            return self.lines.pop(0)[:size]

    monkeypatch.setattr(
        llm_client, "configured_diagnostic_urlopen", lambda *args, **kwargs: FakeResponse()
    )

    body = module.stream_ollama_report(
        prompt="prompt",
        model="model",
        ollama_url="http://localhost:11434",
        temperature=0.1,
        keep_alive="0",
    )
    captured = capsys.readouterr()

    assert body == ""
    assert "bad Ollama JSON line omitted" in captured.err
    assert unsafe_chunk not in captured.out
    assert unsafe_chunk not in captured.err


def test_main_appends_python_analyzer_facts_after_successful_validation(monkeypatch, tmp_path):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    facts_text = backend_fact_text()
    (case_dir / "analysis_facts.md").write_text(facts_text, encoding="utf-8")
    extra_detail = "\n".join(
        [
            "- Дополнительный безопасный контекст: analysis_facts.md остаётся единственным источником фактов, root cause не заявляется.",
            "- Дополнительный безопасный контекст: проверка выполняется как read-only диагностика без изменения данных.",
            "- Дополнительный безопасный контекст: backend data skew отделён от execution skew и cardinality anomaly.",
            "- Дополнительный безопасный контекст: write-path anomaly остаётся unknown и используется только как следующий diagnostic check.",
            "- Дополнительный безопасный контекст: operator/profile time counter не описывается как wall-clock длительность запроса.",
        ]
    )
    model_body = safe_model_body(extra_detail=extra_detail)
    assert "## Факты анализатора" not in model_body

    monkeypatch.setattr(module, "stream_ollama_report", lambda **kwargs: model_body)

    result = module.main([str(case_dir), "--out", "report.md", "--language", "ru"])
    output_text = (case_dir / "report.md").read_text(encoding="utf-8")

    assert result == 0
    assert "## Краткий вывод" in output_text
    assert "## Подробный разбор" in output_text
    assert "## Факты анализатора" in output_text
    assert output_text.index("## Факты анализатора") > output_text.index("## Подробный разбор")
    assert "Source facts:" not in output_text
    assert "Facts sha256:" not in output_text
    assert "Model:" not in output_text
    assert "qwen3-coder" not in output_text
    assert "- Parsed operators: 9" in output_text
    assert "- data skew: yes (rows produced max/min ratio is 1720x)" in output_text
    assert module.validate_report_text(output_text, facts_text=facts_text) == []


def test_main_no_llm_builds_python_report_without_streaming(monkeypatch, tmp_path):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    facts_text = backend_fact_text()
    (case_dir / "analysis_facts.md").write_text(facts_text, encoding="utf-8")

    def fail_stream(**kwargs):
        raise AssertionError("no-llm mode must not call Ollama")

    monkeypatch.setattr(module, "stream_ollama_report", fail_stream)

    result = module.main([str(case_dir), "--out", "report.md", "--no-llm"])
    output_text = (case_dir / "report.md").read_text(encoding="utf-8")

    assert result == 0
    assert "## Short Summary" in output_text
    assert "## Analyzer Facts" in output_text
    assert "qwen3-coder" not in output_text
    assert module.validate_report_text(output_text, facts_text=facts_text, language="en") == []


def test_main_uses_deterministic_report_when_model_output_is_shape_only_invalid(
    monkeypatch, tmp_path
):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    facts_text = backend_fact_text()
    (case_dir / "analysis_facts.md").write_text(facts_text, encoding="utf-8")
    incomplete_safe_body = (
        safe_english_model_body()
        .replace("### Amplifying Factors", "### Additional Context")
        .replace("### What Is Not Supported By Facts", "### Missing Evidence")
    )

    monkeypatch.setattr(module, "stream_ollama_report", lambda **kwargs: incomplete_safe_body)

    result = module.main([str(case_dir), "--out", "report.md"])
    output_text = (case_dir / "report.md").read_text(encoding="utf-8")

    assert result == 0
    assert "## Short Summary" in output_text
    assert "## Practical Recommendations" in output_text
    assert "## Detailed Analysis" in output_text
    assert "## Analyzer Facts" in output_text
    assert "### Additional Context" not in output_text
    assert "### Missing Evidence" not in output_text
    assert not (case_dir / "report.partial.md").exists()
    assert module.validate_report_text(output_text, facts_text=facts_text, language="en") == []


def test_main_defaults_to_english_report_contract(monkeypatch, tmp_path):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    facts_text = backend_fact_text()
    (case_dir / "analysis_facts.md").write_text(facts_text, encoding="utf-8")

    monkeypatch.setattr(module, "stream_ollama_report", lambda **kwargs: safe_english_model_body())

    result = module.main([str(case_dir), "--out", "report.md"])
    output_text = (case_dir / "report.md").read_text(encoding="utf-8")

    assert result == 0
    assert "## Short Summary" in output_text
    assert "## Detailed Analysis" in output_text
    assert "## Analyzer Facts" in output_text
    assert "## Краткий вывод" not in output_text
    assert "## Факты анализатора" not in output_text
    assert module.validate_report_text(output_text, facts_text=facts_text, language="en") == []


def test_main_does_not_expose_or_save_unvalidated_report(monkeypatch, tmp_path, capsys):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
""".strip(),
        encoding="utf-8",
    )
    unsafe_body = "## Краткий вывод\n\n- запрос выполнялся 9.70h.\n"

    monkeypatch.setattr(module, "stream_ollama_report", lambda **kwargs: unsafe_body)

    result = module.main([str(case_dir), "--out", "report.md", "--language", "ru"])
    captured = capsys.readouterr()

    assert result == 4
    assert unsafe_body not in captured.out
    assert unsafe_body not in captured.err
    assert not (case_dir / "report.md").exists()
    assert (case_dir / "report.partial.md").exists()
    partial_text = (case_dir / "report.partial.md").read_text(encoding="utf-8")
    assert "запрос выполнялся 9.70h" not in partial_text
    assert "## Факты анализатора" not in partial_text


def test_main_preserves_existing_report_when_validation_fails(monkeypatch, tmp_path):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "analysis_facts.md").write_text(
        """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
""".strip(),
        encoding="utf-8",
    )
    output_path = case_dir / "report.md"
    existing_report = "previous validated report\n"
    output_path.write_text(existing_report, encoding="utf-8")

    monkeypatch.setattr(
        module,
        "stream_ollama_report",
        lambda **kwargs: "## Краткий вывод\n\n- запрос выполнялся 9.70h.\n",
    )

    result = module.main([str(case_dir), "--out", "report.md", "--language", "ru"])

    assert result == 4
    assert output_path.read_text(encoding="utf-8") == existing_report
    assert (case_dir / "report.partial.md").exists()


def test_main_preserves_existing_report_when_final_appendix_validation_fails(monkeypatch, tmp_path):
    module = load_report_module()
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    facts_text = backend_fact_text()
    (case_dir / "analysis_facts.md").write_text(facts_text, encoding="utf-8")
    output_path = case_dir / "report.md"
    existing_report = "previous validated report\n"
    output_path.write_text(existing_report, encoding="utf-8")
    extra_detail = "\n".join(
        [
            "- Безопасный дополнительный контекст: analysis_facts.md остаётся источником фактов.",
            "- Безопасный дополнительный контекст: root cause не заявляется.",
            "- Безопасный дополнительный контекст: рекомендации остаются read-only.",
            "- Безопасный дополнительный контекст: write-path anomaly остаётся unknown.",
            "- Безопасный дополнительный контекст: time counter не является wall-clock длительностью.",
        ]
    )

    monkeypatch.setattr(
        module,
        "stream_ollama_report",
        lambda **kwargs: safe_model_body(extra_detail=extra_detail),
    )
    monkeypatch.setattr(
        module,
        "append_analyzer_facts_appendix",
        lambda report_text, facts_text, **kwargs: report_text.replace(
            "## Подробный разбор", "## Детали", 1
        ),
    )

    result = module.main([str(case_dir), "--out", "report.md", "--language", "ru"])

    assert result == 4
    assert output_path.read_text(encoding="utf-8") == existing_report
    assert (case_dir / "report.partial.md").exists()


def test_short_summary_uses_same_write_path_safety_validation():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- write-path anomaly: unknown
"""
    report = safe_structured_report().replace(
        "- Profile-level facts показывают маленький baseline без выраженной нагрузки.",
        "- HDFS write path is the proven root cause.",
    )

    errors = module.validate_report_text(
        report,
        facts_text=facts,
        min_chars=0,
        min_sections=0,
    )

    assert any("write-path anomaly is not proven" in error for error in errors)


def test_short_summary_uses_same_cardinality_safety_validation():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
"""
    report = safe_structured_report().replace(
        "- Profile-level facts показывают маленький baseline без выраженной нагрузки.",
        "- Главная причина — серьезная недооценка количества строк.",
        1,
    )

    errors = module.validate_report_text(
        report,
        facts_text=facts,
        min_chars=0,
        min_sections=0,
    )

    assert errors
    assert any("Cardinality anomalies: 0" in error for error in errors)


def test_prompt_prioritizes_backend_tail_evidence_when_present():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- execution skew: yes
- write-path anomaly: yes

### Host tail candidates
| host | evidence | ratio/metric |
| worker-c.example.net | execution time: 4.33m vs peer min 40s | 6.50x |
"""

    admin_prompt = module.build_prompt(
        facts_text=facts,
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )
    user_prompt = module.build_prompt(
        facts_text=facts,
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="user",
    )

    assert "Prioritize platform/host-tail evidence" in admin_prompt
    assert "host-specific write/RPC/HDFS path should be checked" in admin_prompt
    assert "Do not claim network or HDFS is the root cause." in admin_prompt
    assert "передайте платформенной команде backend/host evidence" in user_prompt
    assert "worker-c.example.net" not in admin_prompt
    assert "worker-c.example.net" not in user_prompt
    assert "host_01" in admin_prompt
    assert "host_01" in user_prompt


def test_prompt_distinguishes_backend_data_skew_from_cardinality_skew():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 9
- Cardinality anomalies: 0
- Memory anomalies: 0

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown
"""

    prompt = module.build_prompt(
        facts_text=facts,
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="user",
    )

    assert "host tail candidates: 0" in prompt
    assert "data skew: yes" in prompt
    assert "execution skew: no" in prompt
    assert "write-path anomaly: unknown" in prompt
    assert "Keep backend data skew separate from cardinality/row-estimate anomaly." in prompt
    assert "rows/records are distributed unevenly across backends" in prompt
    assert "no single slow backend/tail host is proven" in prompt
    assert "write/RPC/HDFS path may be listed only as a next diagnostic check" in prompt


def test_shared_prompt_does_not_require_updating_stats():
    module = load_report_module()

    prompt = sample_prompt(module, mode="user")

    assert "Проверить/обновить table stats" not in prompt
    assert "Проверить/обновить stats" not in prompt
    assert "PYTHON-OWNED RECOMMENDATION CANDIDATES" in prompt
    assert (
        "Do not ask whether stats were updated unless analysis_facts.md mentions a prior stats change."
        in prompt
    )


def test_user_report_postprocess_rewrites_legacy_user_sections_to_unified_report():
    module = load_report_module()

    report = """
# Query Doctor Report

## Read-only проверки, которые можно выполнить

- Выполнить `SHOW TABLE STATS` для таблиц, участвующих в запросе.
- Выполнить `SHOW COLUMN STATS` для ключей join и фильтров, если они известны.
"""

    enforced = module.enforce_user_report_requirements(report, "# Analysis Facts\n")

    assert "### Read-only проверки, которые можно выполнить" not in enforced
    assert "### Follow-up checks" in enforced


def test_user_report_postprocess_uses_admin_checks_not_escalation_package():
    module = load_report_module()

    report = """
# Query Doctor Report

## Если проблема останется, отправьте админам/платформенной команде

- Query ID: не указан в analysis_facts.md
"""

    enforced = module.enforce_user_report_requirements(report, "# Analysis Facts\n")

    assert "### Если проблема останется, отправьте админам/платформенной команде" not in enforced
    assert "### Follow-up checks" in enforced
    assert "Проверить per-host RowsProduced" not in enforced


def test_user_report_postprocess_rewrites_english_checklist_headings_to_russian():
    module = load_report_module()

    report = """
# Query Doctor Report

## Read-only checks you can run

- Already present.

## If it still fails, send this to the admin/platform team

- Already present.
"""

    enforced = module.enforce_user_report_requirements(report, "# Analysis Facts\n")

    assert "## Read-only checks you can run" not in enforced
    assert "## If it still fails, send this to the admin/platform team" not in enforced
    assert "### Read-only проверки, которые можно выполнить" not in enforced
    assert "### Если проблема останется, отправьте админам/платформенной команде" not in enforced
    assert "### Follow-up checks" in enforced


def test_user_report_postprocess_does_not_add_legacy_validation_sections():
    module = load_report_module()

    report = """
# Query Doctor Report

## Практические рекомендации

- Проверить статистику таблиц.
"""

    enforced = module.enforce_user_report_requirements(report, "# Analysis Facts\n")

    assert "### Изменения, требующие проверки" not in enforced
    assert "### Как проверить улучшение" not in enforced
    assert "## Практические рекомендации" in enforced


def test_admin_report_postprocess_adds_required_next_checks():
    module = load_report_module()

    report = """
# Query Doctor Report

## Что проверить следующим запуском

- Проверить per-host RowsProduced.
"""

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Memory anomalies: 2

## Action Cards

### Card 1

- Finding.

## Backend / Host Tail Evidence

- execution skew: yes

## Findings

- Detected non-zero spill/scratch metric evidence in digest lines.
"""

    enforced = module.enforce_admin_report_requirements(report, facts)

    assert "Проверить per-host RowsProduced" in enforced
    assert "Проверить per-host PeakMemUsage" in enforced
    assert "Проверить spill/scratch counters" in enforced
    assert "Проверить лимиты памяти admission pool" in enforced
    assert "Проверить CM metrics/logs" in enforced
    assert "Проверить profile counters" in enforced


def test_admin_report_postprocess_keeps_inserted_checks_inside_details():
    module = load_report_module()

    report = """
# Query Doctor Report

### Follow-up checks

- Проверить per-host RowsProduced.
"""
    facts = """
# Query Doctor deterministic analysis facts

## Action Cards

### Card 1

- Finding.
"""

    enforced = module.enforce_admin_report_requirements(report, facts)

    assert "Проверить profile counters" in enforced
    assert enforced.index("Проверить profile counters") > enforced.index("### Follow-up checks")


def test_report_normalizer_moves_misplaced_admin_bullets_inside_admin_section():
    module = load_report_module()

    report = (
        safe_structured_report().rstrip()
        + "\n- Проверить CM metrics/logs на host-level resource pressure.\n"
    )

    normalized = module.normalize_report_text(report, facts_text="# Analysis Facts\n")

    assert "Проверить CM metrics/logs" in normalized
    assert normalized.index("Проверить CM metrics/logs") > normalized.index("### Follow-up checks")


def test_report_normalizer_moves_misplaced_zero_cardinality_note():
    module = load_report_module()

    report = safe_structured_report().replace(
        "### Follow-up checks\n\n",
        "### Follow-up checks\n\n"
        "- В analyzer facts нет подтверждённой аномалии кардинальности; не заявляйте недооценку кардинальности без соответствующего факта.\n",
        1,
    )

    normalized = module.normalize_report_text(report, facts_text="Cardinality anomalies: 0")
    not_supported_start = normalized.index("### Что НЕ подтверждается фактами")
    admin_start = normalized.index("### Follow-up checks")

    assert (
        normalized.index("В analyzer facts нет подтверждённой аномалии кардинальности")
        < admin_start
    )
    assert (
        normalized.index("В analyzer facts нет подтверждённой аномалии кардинальности")
        > not_supported_start
    )


def test_zero_cardinality_inserted_safety_text_is_russian():
    module = load_report_module()

    report = """
# Query Doctor Report

## Что НЕ подтверждается фактами

- Нет доказательств проблем с кардинальностью.
"""
    facts = "Cardinality anomalies: 0"

    enforced = module.enforce_report_fact_requirements(report, facts)

    assert "В analyzer facts нет подтверждённой аномалии кардинальности" in enforced
    assert "No analyzer-supported cardinality anomaly was found" not in enforced


def test_admin_report_postprocess_deduplicates_equivalent_next_checks():
    module = load_report_module()

    report = """
# Query Doctor Report

## Что проверить следующим запуском

- Сравнить per-host RowsProduced по операторам из Action Cards.
- Сравнить per-host PeakMemUsage по тем же операторам.
- Проверить spill/scratch counters в query profile.
- Проверить admission pool и очередь.
- Проверить CM metrics/logs во время окна запроса.
- Проверить profile counters по указанным операторам.
"""

    enforced = module.enforce_admin_report_requirements(report)

    assert enforced.count("per-host RowsProduced") == 1
    assert enforced.count("per-host PeakMemUsage") == 1
    assert enforced.count("spill/scratch counters") == 1
    assert enforced.count("admission pool") == 1
    assert enforced.count("CM metrics/logs") == 1
    assert enforced.count("profile counters") == 1


def test_admin_report_postprocess_rewrites_english_next_checks_heading():
    module = load_report_module()

    report = """
# Query Doctor Report

## Next checks

- Проверить per-host RowsProduced.
"""

    enforced = module.enforce_admin_report_requirements(report)

    assert "## Next checks" not in enforced
    assert "### Follow-up checks" in enforced


def test_admin_report_postprocess_adds_backend_tail_checks_when_facts_have_evidence():
    module = load_report_module()

    report = """
# Query Doctor Report

## Что проверить следующим запуском

- Проверить per-host RowsProduced.
"""
    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- execution skew: yes
- write-path anomaly: yes
"""

    enforced = module.enforce_admin_report_requirements(report, facts)

    assert "Приоритизировать Backend / Host Tail Evidence" in enforced
    assert "write/RPC/HDFS path как гипотезу" in enforced
    assert "не доказанная причина" in enforced
    assert "root cause" not in enforced


def test_admin_report_postprocess_does_not_invent_tail_host_when_absent():
    module = load_report_module()

    report = """
# Query Doctor Report

## Что проверить следующим запуском

- Проверить per-host RowsProduced.
"""
    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown
"""

    enforced = module.enforce_admin_report_requirements(report, facts)

    assert "Backend / Host Tail Evidence" in enforced
    assert "single tail host не доказан" in enforced
    assert "для tail host и соседних hosts" not in enforced


def test_user_report_postprocess_adds_backend_tail_admin_package_when_facts_have_evidence():
    module = load_report_module()

    report = """
# Query Doctor Report

## Если проблема останется, отправьте админам/платформенной команде

- analysis_facts.md.
"""
    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- execution skew: yes
"""

    enforced = module.enforce_user_report_requirements(report, facts)

    assert "Передать платформенной команде backend/host evidence" in enforced
    assert "не доказанная причина" in enforced
    assert "root cause" not in enforced


def test_sanitizer_rewrites_strong_root_cause_heading():
    module = load_report_module()

    report = """
# Query Doctor Report

## Главная причина замедления

Факты.
"""

    sanitized = module.sanitize_report_text(report, "# Analysis Facts\n")

    assert "## Главная причина замедления" not in sanitized
    assert "### Основные подтверждённые проблемы по профилю" in sanitized


def test_report_validator_blocks_cardinality_underestimation_when_zero_anomalies():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = "The main issue is cardinality underestimation at HASH JOIN."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "Cardinality anomalies: 0" in errors[0]


def test_report_validator_blocks_actual_rows_exceed_estimates_when_zero_anomalies():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = "Actual rows exceed estimates, so estimated rows are too low."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "actual rows exceed estimates" in errors[0]


@pytest.mark.parametrize(
    "facts",
    [
        "Cardinality anomalies: 0",
        "- Cardinality anomalies: 0",
        "  - Cardinality anomalies: 0",
        "* Cardinality anomalies: 0",
        "Cardinality anomalies : 0",
        "- Cardinality anomalies : 0",
    ],
)
def test_report_validator_detects_zero_cardinality_facts_formats(facts):
    module = load_report_module()

    errors = module.validate_report_against_facts("actual rows exceed estimates", facts)

    assert errors
    assert "Cardinality anomalies: 0" in errors[0]


def test_report_validator_does_not_apply_zero_rule_to_minimal_nonzero_facts():
    module = load_report_module()

    errors = module.validate_report_against_facts(
        "estimates were too low",
        "Cardinality anomalies: 1",
    )

    assert errors == []


def test_report_validator_allows_safe_zero_cardinality_wording():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = "No analyzer-supported cardinality anomaly was found."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


@pytest.mark.parametrize(
    "report",
    [
        "Cardinality underestimation is not supported by analysis_facts.md.",
        "Cardinality underestimation is not supported by the extracted facts.",
        "Cardinality underestimation is not established by the analyzer.",
    ],
)
def test_report_validator_allows_safe_cardinality_limitation_wording(report):
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_mixed_safe_and_unsafe_zero_cardinality_line():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = (
        "No analyzer-supported cardinality anomaly was found, "
        "but cardinality underestimation is still the cause."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "cardinality underestimation" in errors[0]


def test_report_validator_blocks_unsafe_zero_cardinality_claim_after_safe_sentence():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = (
        "No analyzer-supported cardinality anomaly was found. "
        "Cardinality underestimation is still the cause."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "cardinality underestimation" in errors[0]


def test_report_validator_blocks_cardinality_underestimation_still_cause_when_zero_anomalies():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = "Cardinality underestimation is still the cause."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "cardinality underestimation" in errors[0]


@pytest.mark.parametrize(
    "report",
    [
        "No cardinality anomaly was found; nevertheless, estimates were too low.",
        "Cardinality underestimation is not supported by analysis_facts.md, but it is still the cause.",
        "Cardinality underestimation is not supported by the extracted facts; nevertheless, estimates were too low.",
        "estimated rows were too low",
        "row estimates were too low",
        "optimizer estimates were too low",
        "actual rows were higher than estimated",
    ],
)
def test_report_validator_blocks_additional_zero_cardinality_unsupported_variants(report):
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors


def test_report_validator_allows_cardinality_wording_when_anomaly_exists():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 24
- Cardinality anomalies: 1
- Memory anomalies: 0
"""
    report = "The main issue is cardinality underestimation at HASH JOIN."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_allows_low_estimate_wording_when_cardinality_anomaly_exists():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 24
- Cardinality anomalies: 1
- Memory anomalies: 0
"""
    report = "estimates were too low"

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_underestimation_when_operator_ratio_is_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 25
- Cardinality anomalies: 1
- Memory anomalies: 4

## Operator Summary

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = "04:HASH JOIN shows row underestimation and should be treated as underestimated."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "04:HASH JOIN" in errors[0]
    assert "ratio is below 1" in errors[0]


def test_report_validator_allows_memory_underestimation_when_row_ratio_is_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
"""
    report = "04:HASH JOIN shows memory underestimation: peak memory is above estimated memory."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_memory_underestimation_when_memory_ratio_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 10 | 10 | 1.00x | 52.46 MiB | 167.85 MiB | 0.31x |
"""
    report = (
        "Оператор 04:HASH JOIN использовал 52.46 MiB памяти против оценки 167.85 MiB "
        "(соотношение 0.31x). Это указывает на недооценку памяти."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "memory underestimation" in errors[0]


def test_sanitizer_rewrites_memory_underestimation_when_memory_ratio_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 10 | 10 | 1.00x | 52.46 MiB | 167.85 MiB | 0.31x |
"""
    report = (
        "Оператор 04:HASH JOIN использовал 52.46 MiB памяти против оценки 167.85 MiB. "
        "Это указывает на недооценку памяти."
    )

    sanitized = module.sanitize_report_text(report, facts)

    assert "недооценку памяти" not in sanitized
    assert "расхождение оценки памяти" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_report_validator_allows_true_memory_underestimation_ratio_above_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 10 | 10 | 1.00x | 1.10 GiB | 16.16 MiB | 69.7x |
"""
    report = "04:HASH JOIN показывает недооценку памяти: peak memory выше оценки."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_allows_generic_memory_estimate_mismatch():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 10 | 10 | 1.00x | 52.46 MiB | 167.85 MiB | 0.31x |
"""
    report = "04:HASH JOIN показывает расхождение оценки памяти: peak memory ниже оценки."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_memory_overestimation_when_memory_ratio_above_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 10 | 10 | 1.00x | 1.10 GiB | 16.16 MiB | 69.7x |
"""
    report = "04:HASH JOIN показывает переоценку памяти, хотя peak memory выше оценки."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "memory overestimation" in errors[0]


def test_report_validator_blocks_memory_volume_overestimation_when_memory_ratio_above_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 07:AGGREGATE | 1.80h | 10 | 10 | 1.00x | 93.70 GiB | 122.07 MiB | 786x |
"""
    report = (
        "Оператор 07:AGGREGATE демонстрирует серьезную переоценку объема памяти: "
        "фактически 93.70 GiB против оценки 122.07 MiB (соотношение 786x)."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "memory overestimation" in errors[0]


def test_sanitizer_rewrites_memory_volume_overestimation_when_memory_ratio_above_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 07:AGGREGATE | 1.80h | 10 | 10 | 1.00x | 93.70 GiB | 122.07 MiB | 786x |
"""
    report = (
        "Оператор 07:AGGREGATE демонстрирует серьезную переоценку объема памяти: "
        "фактически 93.70 GiB против оценки 122.07 MiB (соотношение 786x)."
    )

    sanitized = module.sanitize_report_text(report, facts)

    assert "переоценку объема памяти" not in sanitized
    assert "расхождение оценки памяти" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_report_validator_allows_true_memory_overestimation_ratio_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 10 | 10 | 1.00x | 52.46 MiB | 167.85 MiB | 0.31x |
"""
    report = "04:HASH JOIN показывает переоценку памяти: peak memory ниже оценки."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_operator_time_as_wall_clock_without_evidence():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Оператор 04:HASH JOIN выполняется 4.90 часов и является bottleneck."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "wall-clock" in errors[0]


def test_report_validator_blocks_operator_time_noun_as_wall_clock_without_evidence():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Оператор 00:UNION: время выполнения 9.70 часов, обработано 41.91 млн строк."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "wall-clock" in errors[0]


def test_report_validator_blocks_parenthesized_operator_time_counter_wording():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Оператор 05:EXCHANGE имеет низкое время выполнения (108ms) и соответствующее количество строк."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "wall-clock" in errors[0]


def test_report_validator_blocks_compact_operator_time_units_without_evidence():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "\n".join(
        [
            "Оператор 00:UNION: время выполнения 9.70h, обработано 41.91 млн строк.",
            "Оператор 04:SCAN выполняется 4.83s и выделяется в профиле.",
            "Operator 14:EXCHANGE ran 38.00m and stands out in the profile.",
        ]
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "wall-clock" in errors[0]


def test_sanitizer_rewrites_operator_time_as_profile_counter():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Оператор 04:HASH JOIN выполняется около 4.90 часов и выделяется в профиле."

    sanitized = module.sanitize_report_text(report, facts)

    assert "выполняется около 4.90 часов" not in sanitized
    assert "operator/profile time counter около 4.90 часов" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_rewrites_operator_time_noun_as_profile_counter():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Оператор 00:UNION: время выполнения 9.70 часов, обработано 41.91 млн строк."

    sanitized = module.sanitize_report_text(report, facts)

    assert "время выполнения 9.70 часов" not in sanitized
    assert "operator/profile time counter 9.70 часов" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_rewrites_parenthesized_operator_time_counter_wording():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Оператор 05:EXCHANGE имеет низкое время выполнения (108ms) и соответствующее количество строк."

    sanitized = module.sanitize_report_text(report, facts)

    assert "время выполнения (108ms)" not in sanitized
    assert "operator/profile time counter 108ms" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_rewrites_compact_operator_time_units():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "\n".join(
        [
            "Оператор 00:UNION: время выполнения 9.70h, обработано 41.91 млн строк.",
            "Оператор 04:SCAN выполняется 4.83s и выделяется в профиле.",
            "Operator 14:EXCHANGE ran 38.00m and stands out in the profile.",
        ]
    )

    sanitized = module.sanitize_report_text(report, facts)

    assert "время выполнения 9.70h" not in sanitized
    assert "выполняется 4.83s" not in sanitized
    assert "ran 38.00m" not in sanitized
    assert "operator/profile time counter 9.70h" in sanitized
    assert "operator/profile time counter 4.83s" in sanitized
    assert "operator/profile time counter 38.00m" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_does_not_treat_uppercase_m_row_count_as_minutes():
    module = load_report_module()

    facts = "# Query Doctor deterministic analysis facts\n"
    report = "Operator 07:AGGREGATE ran 5M rows and used 93.70 GiB memory."

    sanitized = module.sanitize_report_text(report, facts)

    assert sanitized.strip() == report
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_report_validator_allows_row_underestimation_when_operator_ratio_is_above_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = "13:EXCHANGE shows row underestimation."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_underestimation_for_operator_type_when_all_ratios_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 05:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = "Rows are underestimated in EXCHANGE and HASH JOIN."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "HASH JOIN" in errors[0]


def test_report_validator_blocks_low_row_estimate_wording_when_ratio_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 06:HASH JOIN (INNER JOIN) | 1.80h | 5.26B | 76216.64T | 0.00x | 93.70 GiB | 50.28 GiB | 1.86x |
"""
    report = (
        "Оператор 06:HASH JOIN (INNER JOIN) имеет крайне низкую оценку строк: "
        "фактически 5.26B строк против оценки 76216.64T (соотношение 0.00x)."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "06:HASH JOIN" in errors[0]


def test_sanitizer_replaces_row_underestimation_claim_for_overestimated_operator_type():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 07:AGGREGATE | 1.80h | 5.26B | 76216.64T | 0.00x | 93.70 GiB | 122.07 MiB | 786x |
| 10:AGGREGATE | 38.00m | 59.73M | 9223372.04T | 0.00x | 5.10 GiB | 122.07 MiB | 42.8x |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = (
        "Основные проблемы связаны с операторами JOIN и AGGREGATE, "
        "где оценка количества строк была значительно занижена."
    )

    sanitized = module.sanitize_report_text(report, facts)

    assert "AGGREGATE" not in sanitized
    assert "Направление row/cardinality estimate" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_replaces_low_row_estimate_wording_when_ratio_below_one():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 06:HASH JOIN (INNER JOIN) | 1.80h | 5.26B | 76216.64T | 0.00x | 93.70 GiB | 50.28 GiB | 1.86x |
"""
    report = (
        "Оператор 06:HASH JOIN (INNER JOIN) имеет крайне низкую оценку строк: "
        "фактически 5.26B строк против оценки 76216.64T (соотношение 0.00x)."
    )

    sanitized = module.sanitize_report_text(report, facts)

    assert "низкую оценку строк" not in sanitized
    assert "Направление row/cardinality estimate" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_replaces_low_row_estimate_wording_in_english_without_cyrillic():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 06:HASH JOIN (INNER JOIN) | 1.80h | 5.26B | 76216.64T | 0.00x | 93.70 GiB | 50.28 GiB | 1.86x |
"""
    report = (
        "Operator 06:HASH JOIN (INNER JOIN) row estimates are too low: "
        "5.26B actual rows versus 76216.64T estimated rows."
    )

    sanitized = module.sanitize_report_text(report, facts, language="en")

    assert "too low" not in sanitized
    assert "row/cardinality estimate direction" in sanitized
    assert not any("\u0400" <= char <= "\u04ff" for char in sanitized)
    assert module.validate_report_safety_text(sanitized, facts_text=facts, language="en") == []


def test_sanitizer_replaces_zero_cardinality_positive_claim_with_safe_note():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
"""
    report = "Главная причина — недооценка количества строк."

    sanitized = module.sanitize_report_text(report, facts)

    assert "Главная причина" not in sanitized
    assert "В analyzer facts нет подтверждённой аномалии кардинальности" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_report_validator_blocks_underestimation_heading_with_contradicted_child_operator():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 05:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = """
- **Серьезное недооценение количества строк (cardinality underestimation)**:
  - Оператор 13:EXCHANGE: фактически 1.12B строк, оценено как 1 (соотношение 1121558192x).
  - Оператор 04:HASH JOIN (LEFT OUTER JOIN): фактически 5.26B строк, оценено как 73.59B (соотношение 0.07x).
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "04:HASH JOIN" in errors[0]


def test_report_validator_blocks_h3_underestimation_heading_with_ratio_below_one_evidence():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = """
### Недооценение количества строк
- Оператор 13:EXCHANGE: фактически 1.12B строк против оценки 1 (соотношение 1121558192x).
- Оператор 04:HASH JOIN (LEFT OUTER JOIN): фактически 5.26B строк против оценки 73.59B (соотношение 0.07x).
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "04:HASH JOIN" in errors[0]


def test_report_validator_allows_mixed_row_estimate_heading_with_ratio_below_one_evidence():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = """
### Расхождения оценок строк
- Оператор 13:EXCHANGE: фактические строки выше оценки (соотношение 1121558192x).
- Оператор 04:HASH JOIN (LEFT OUTER JOIN): оценка выше факта (соотношение 0.07x); недооценка по этому оператору не подтверждена.
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_allows_underestimation_heading_with_only_ratio_above_one_evidence():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 13:EXCHANGE | 9.50m | 1.12B | 1 | 1121558192x | 11.30 MiB | n/a | n/a |
"""
    report = """
### Недооценение количества строк
- Оператор 13:EXCHANGE: фактически 1.12B строк против оценки 1 (соотношение 1121558192x).
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_resets_underestimation_context_on_new_top_level_item():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

| operator | time | actual rows | estimated rows | rows ratio | peak mem | est. peak mem | mem ratio |
| 04:HASH JOIN (LEFT OUTER JOIN) | 1.80h | 5.26B | 73.59B | 0.07x | 1.10 GiB | 16.16 MiB | 69.7x |
"""
    report = """
- **Серьезное недооценение количества строк (cardinality underestimation)**:
  - No operator id listed here.
- **Серьезное недооценение памяти (memory underestimation)**:
  - Оператор 04:HASH JOIN (LEFT OUTER JOIN): peak memory is above estimated memory.
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_russian_cardinality_underestimation_when_zero_anomalies():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Parsed operators: 169
- Cardinality anomalies: 0
- Memory anomalies: 2
"""
    report = "Главная причина — серьезная недооценка количества строк."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "Russian cardinality underestimation" in errors[0]


def test_report_validator_allows_russian_safe_zero_cardinality_negation():
    module = load_report_module()

    facts = "Cardinality anomalies: 0"
    report = "Нет доказательств, что оценки строк были слишком низкими."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_russian_positive_zero_cardinality_claim():
    module = load_report_module()

    facts = "Cardinality anomalies: 0"
    report = "Количество строк превышает оценки."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "Russian actual rows exceed estimates" in errors[0]


def test_report_validator_allows_backend_data_skew_without_cardinality_claim():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown
"""
    report = (
        "Rows/records are distributed unevenly across backends. "
        "No single slow backend/tail host is proven. "
        "Write-path anomaly is unknown; check write/RPC/HDFS path as next diagnostic."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_negating_supported_backend_data_skew():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown
"""
    report = "Нет подтверждённых признаков перекоса данных или выполнения по хостам."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "backend data skew absence claim" in errors[0]


def test_report_validator_treats_context_only_scan_skew_as_not_supported():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Scan Skew Evidence

- status: context_only
- evidence_tier: context_only
- finding_supported: no
- primary_supported: no

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown
"""
    report = "Есть подтверждённый data skew по RowsProduced."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "backend data skew claim contradicts" in errors[0]


def test_report_validator_blocks_positive_backend_data_skew_when_not_supported():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 28
- host tail candidates: 1
- data skew: no (F03: assigned/read work appears comparable)
- execution skew: yes
- write-path anomaly: no
"""
    report = "Есть подтверждённый data skew по RowsProduced."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "backend data skew claim contradicts" in errors[0]


def test_sanitizer_rewrites_positive_backend_data_skew_when_not_supported():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 28
- host tail candidates: 1
- data skew: no (F03: assigned/read work appears comparable)
- execution skew: yes
- write-path anomaly: no
"""
    report = "Есть подтверждённый data skew по RowsProduced."

    sanitized = module.sanitize_report_text(report, facts)

    assert "Есть подтверждённый data skew" not in sanitized
    assert "Backend data skew по RowsProduced не подтверждён" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


@pytest.mark.parametrize(
    "report",
    [
        "Нет подтверждения наличия данных skew или распределения записей по бэкендам.",
        "Нет подтверждения наличия data skew.",
        "Нет подтверждения распределения записей по бэкендам.",
        "No backend skew evidence.",
        "Data skew is not confirmed.",
    ],
)
def test_report_validator_blocks_specific_negations_of_supported_backend_data_skew(report):
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 146
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1007914x)
- execution skew: no
- write-path anomaly: unknown
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "backend data skew absence claim" in errors[0]


@pytest.mark.parametrize(
    "report",
    [
        "Есть подтверждённый data skew по RowsProduced.",
        "Отдельный tail host не подтверждён.",
        "Data skew is supported, but single host tail is not confirmed.",
    ],
)
def test_report_validator_allows_supported_skew_and_safe_tail_negation(report):
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 146
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1007914x)
- execution skew: no
- write-path anomaly: unknown
"""

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_sanitizer_rewrites_negated_supported_backend_data_skew():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes (rows produced max/min ratio is 1720x)
- execution skew: no
- write-path anomaly: unknown
"""
    report = "Нет подтверждённых признаков перекоса данных или выполнения по хостам."

    sanitized = module.sanitize_report_text(report, facts)

    assert "Нет подтверждённых признаков перекоса данных" not in sanitized
    assert "Backend data skew поддержан analyzer facts" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_sanitizer_rewrites_postfixed_negation_for_supported_skew_and_spill():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- data skew: yes
- execution skew: no

## Findings

### Spill or scratch I/O [medium]

- Detected non-zero spill/scratch metric evidence in digest lines.
"""
    report = (
        "Проверить наличие перекоса данных и спилла в следующем запуске, если они не были явно подтверждены. "
        "Наличие спиллов или scratch I/O не подтверждено явно, но есть упоминание о них в анализе."
    )

    sanitized = module.sanitize_report_text(report, facts)

    assert "если они не были явно подтверждены" not in sanitized
    assert "Backend data skew поддержан analyzer facts" in sanitized
    assert "ненулевые spill/scratch metrics" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_report_validator_allows_negating_execution_skew_when_data_skew_exists():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes
- execution skew: no
- write-path anomaly: unknown
"""
    report = (
        "Rows/records are distributed unevenly across backends. "
        "Нет подтверждения одного медленного хоста или execution skew."
    )

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_backend_tail_claim_when_summary_says_no_tail():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes
- execution skew: no
- write-path anomaly: unknown
"""
    report = "One host is proven to be slow and execution skew is proven."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert any("no single slow backend" in error for error in errors)
    assert any("execution skew" in error for error in errors)


def test_report_validator_blocks_write_path_root_cause_when_unknown():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- backend rows parsed: 21
- host tail candidates: 0
- data skew: yes
- execution skew: no
- write-path anomaly: unknown
"""
    report = "HDFS write path is the proven root cause."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "write-path anomaly is not proven" in errors[0]


def test_report_validator_blocks_write_path_root_cause_even_when_line_says_check():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- write-path anomaly: unknown
"""
    report = "Check HDFS write path because it is the proven root cause."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "write-path anomaly is not proven" in errors[0]


def test_report_validator_allows_safe_write_path_negation_when_unknown():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- write-path anomaly: unknown
"""
    report = "Нет подтверждения того, что network instability или HDFS проблема является причиной."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_allows_no_evidence_write_path_appendix_wording():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Backend / Host Tail Evidence

- write-path anomaly: unknown
"""
    report = "No direct HDFS/storage candidate signal was parsed; this is not proof that HDFS is the root cause."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_validator_blocks_negating_supported_spill_scratch_evidence():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Spill or scratch I/O [medium]

- Detected non-zero spill/scratch metric evidence in digest lines.
"""
    report = "Нет явных признаков спилла или использования scratch-диска."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "spill/scratch absence claim" in errors[0]


def test_sanitizer_rewrites_negated_supported_spill_scratch_evidence():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Spill or scratch I/O [medium]

- Detected non-zero spill/scratch metric evidence in digest lines.
"""
    report = "Нет явных признаков спилла или использования scratch-диска."

    sanitized = module.sanitize_report_text(report, facts)

    assert "Нет явных признаков спилла" not in sanitized
    assert "ненулевые spill/scratch metrics" in sanitized
    assert module.validate_report_against_facts(sanitized, facts) == []


def test_report_spill_extractor_ignores_limited_memory_pressure_context():
    from query_doctor.report.facts_extractors import facts_have_spill_scratch_evidence

    facts = """
# Query Doctor deterministic analysis facts

## Memory Pressure Evidence

- status: context_only
- evidence_tier: context_only
- promotion_policy: limited
- section_mapping: limited
- finding_supported: no
- spill_or_scratch_evidence_count: 0
- limited_spill_or_scratch_counter_count: 1
- limitations:
  - Non-zero spill/scratch counters were parsed as limited context, but this profile dialect or section is not mapped for memory-pressure promotion.
"""

    assert facts_have_spill_scratch_evidence(facts) is False


def test_report_validator_allows_saying_spill_is_not_proven_cause():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Findings

### Spill or scratch I/O [medium]

- Detected non-zero spill/scratch metric evidence in digest lines.
"""
    report = "Spill/scratch evidence exists, but spill is not proven as the root cause."

    errors = module.validate_report_against_facts(report, facts)

    assert errors == []


def test_report_prompts_require_analysis_facts_only():
    module = load_report_module()

    admin_prompt = sample_prompt(module, mode="admin")
    user_prompt = sample_prompt(module, mode="user")

    for prompt in [admin_prompt, user_prompt]:
        assert "Use only facts from analysis_facts.md." in prompt
        assert (
            "Do not invent table names, join keys, row counts, memory numbers, commands" in prompt
        )
        assert "If evidence is missing, say it is missing." in prompt


def test_report_prompt_includes_curated_metadata_facts_digest_without_raw_context():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=metadata_fact_text_with_raw_context_noise(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "## Table Metadata Context" not in prompt
    assert "METADATA FACTS DIGEST BEGIN" in prompt
    assert "## Metadata Facts Digest" in prompt
    assert "Table: example_db1.table_a" in prompt
    assert "- object type: table" in prompt
    assert "- SHOW CREATE TABLE status: ok" in prompt
    assert "- SHOW TABLE STATS status: ok" in prompt
    assert "- SHOW COLUMN STATS status: ok" in prompt
    assert "- table stats rows: unknown" in prompt
    assert "- table stats row-count completeness: missing/unknown" in prompt
    assert "- table stats size: 34B" in prompt
    assert "- column stats columns observed: 3" in prompt
    assert "- column stats missing/unknown markers: 8" in prompt
    assert "- column stats completeness: incomplete/unknown" in prompt
    assert "Table: example_db2.table_b" in prompt
    assert "- object type: view" in prompt
    assert "- SHOW CREATE TABLE status: too_large" in prompt
    assert "- table stats row-count completeness: not_available" in prompt
    assert "- column stats completeness: not_available" in prompt
    assert "- file format: PARQUET" in prompt
    assert "raw_secret" not in prompt
    assert "raw stats table" not in prompt
    assert 'impala_context.json: {"raw"' not in prompt
    assert (
        "Raw SHOW output, raw DDL, impala_context.md, and impala_context.json are intentionally not included"
        in prompt
    )
    assert "Do not claim metadata proves the root cause" in prompt
    assert "Do not recommend COMPUTE STATS as required" in prompt
    assert "## Referenced Tables" in prompt
    assert "`example_db1.table_a`" in prompt


def test_report_prompt_omits_legacy_source_digest_line():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text="""
# Query Doctor deterministic analysis facts

Source digest: `/tmp/query-doctor/case/profile_digest.md`

## Summary

- Parsed operators: 1
- Cardinality anomalies: 0
- Memory anomalies: 0
""",
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "Source digest:" not in prompt
    assert "/tmp/query-doctor/case/profile_digest.md" not in prompt


def test_report_prompt_includes_python_owned_recommendation_candidates():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=metadata_fact_text_with_raw_context_noise(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN" in prompt
    assert "Python/analyzer owns recommendation facts and allowed action targets." in prompt
    assert "- stats_maintenance:" in prompt
    assert "- reduce_row_growth:" in prompt
    assert "LLM owns only wording, ordering, and concision." in prompt
    assert (
        'Every item in "Практические рекомендации" must map to one of the Python-owned candidates below.'
        in prompt
    )


def test_english_report_prompt_uses_english_contract_and_candidates():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=metadata_fact_text_with_raw_context_noise(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="en",
        mode="admin",
    )

    assert "Write the report in English." in prompt
    assert "## Short Summary" in prompt
    assert "## Practical Recommendations" in prompt
    assert "## Detailed Analysis" in prompt
    assert "### Supported Profile Findings" in prompt
    assert (
        'Every item in "Practical Recommendations" must map to one of the Python-owned candidates below.'
        in prompt
    )
    assert "- stats_maintenance: Collect or update statistics for affected tables" in prompt
    assert 'Use "case_differentiators" to make "Short Summary" specific to this query' in prompt
    assert "## Краткий вывод" not in prompt
    assert "## Практические рекомендации" not in prompt
    assert "Главная причина замедления" not in prompt
    assert "Собрать или обновить статистику" not in prompt


def test_report_prompt_includes_python_owned_contract_digest_without_raw_context():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=metadata_fact_text_with_raw_context_noise(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "PYTHON-OWNED REPORT CONTRACT DIGEST BEGIN" in prompt
    assert '"recommendation_candidates"' in prompt
    assert '"supported_summary_points"' in prompt
    assert '"case_differentiators"' in prompt
    assert '"evidence_groups"' in prompt
    assert '"unsupported_conclusions"' in prompt
    assert '"has_metadata_stats_gap": true' in prompt
    assert '"id": "stats_maintenance"' in prompt
    assert 'Use "case_differentiators" to make "Краткий вывод" specific to this query' in prompt
    assert 'Controlled narrative: "Краткий вывод" and "Подробный разбор"' in prompt
    assert "Do not merely repeat analyzer lines when a concise explanation is possible" in prompt
    assert "raw_secret" not in prompt
    assert "raw stats table" not in prompt
    assert 'impala_context.json: {"raw"' not in prompt


def test_report_prompt_requires_evidence_quality_framing():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=backend_fact_text(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "Use Evidence Quality as the confidence and coverage frame for the report" in prompt
    assert '"evidence_quality"' in prompt
    assert '"limitations": [' in prompt
    assert "CM metrics context is unavailable" in prompt
    assert "not itself a finding, recommendation, or causal signal" in prompt


def test_report_prompt_keeps_runtime_filter_evidence_context_only():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=backend_fact_text(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "Use Runtime Filter Evidence only as analyzer-owned context" in prompt
    assert "raw filter columns must not appear in trusted reports" in prompt


def test_report_prompt_uses_cm_metrics_facts_without_raw_timeseries_context():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=cm_metrics_fact_text_with_timeseries_context(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "## CM Time-Series Context" not in prompt
    assert "2026-05-04T09:59:00Z" not in prompt
    assert "- min: 1048576.00" not in prompt
    assert "## CM Metrics Facts" in prompt
    assert "- daemon_memory_growth: observed" in prompt
    assert "- network_io_spike: observed" in prompt
    assert "Use Runtime Metrics Facts as the only metrics interpretation source" in prompt
    assert "Do not infer from CM Time-Series Context or raw aggregates" in prompt
    assert "Use Cluster Runtime Context only as a compact Python-owned summary" in prompt
    assert "not a performance-speedup estimate and not causal proof" in prompt


def test_report_prompt_uses_provider_neutral_runtime_metrics_headings():
    module = load_report_module()

    facts_text = """
# Query Doctor deterministic analysis facts

## Runtime Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed
- network_io_spike: observed

## Runtime Metrics Correlation

- status: available
- correlated_signals: 1
- context_only_signals: 1
- daemon_memory_growth: correlated (metric=observed, strength=moderate)
- network_io_spike: context_only (metric=observed, strength=weak)

## Cluster Runtime Context

- status: available
- collection_status: collected
- metrics_profile: prometheus
- guardrail: Cluster runtime context is deterministic follow-up context only.
"""

    prompt = module.build_prompt(
        facts_text=facts_text,
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "## Runtime Metrics Facts" in prompt
    assert "## Runtime Metrics Correlation" in prompt
    assert "## Cluster Runtime Context" in prompt
    assert "## CM Metrics Facts" not in prompt
    assert "## CM Metrics Correlation" not in prompt
    assert "Use Runtime Metrics Facts as the only metrics interpretation source" in prompt
    assert "Use Cluster Runtime Context only as a compact Python-owned summary" in prompt
    assert "not a performance-speedup estimate and not causal proof" in prompt


def test_report_prompt_uses_cluster_event_context_as_bounded_followup_context():
    module = load_report_module()

    prompt = module.build_prompt(
        facts_text=cluster_event_fact_text(),
        facts_path=Path("analysis_facts.md"),
        facts_sha256="abc123",
        model="test-model",
        language="ru",
        mode="admin",
    )

    assert "## Cluster Event Context" in prompt
    assert "Use Cluster Event Context only as a Python-owned raw-free event summary" in prompt
    assert "Cluster event signals are cluster/service context and follow-up checks" in prompt
    assert '"cluster_event_context"' in prompt
    assert "service restarts, daemon errors, catalog errors" in prompt
    assert "RAW_" not in prompt


def test_report_contract_digest_includes_cm_metrics_facts():
    module = load_report_module()

    digest = module.build_report_contract_digest(cm_metrics_fact_text_with_timeseries_context())

    assert digest["cm_metrics"]["coverage"] == "4/4 metrics ok, 40 points"
    assert digest["cm_metrics"]["daemon_memory_growth"] == "observed"
    assert digest["cm_metrics"]["network_io_spike"] == "observed"
    assert digest["metrics_facts"] == digest["cm_metrics"]
    assert digest["metrics_correlation"] == digest["cm_metrics_correlation"]
    assert digest["cm_metrics_correlation"] == {}
    assert any("Daemon memory growth: observed" in item for item in digest["case_differentiators"])
    assert any(
        "Network I/O spike: observed" in item for item in digest["evidence_groups"]["cm_metrics"]
    )
    assert any(
        "Runtime Metrics Facts contain an observed context signal" in item
        for item in digest["supported_summary_points"]
    )


def test_report_contract_digest_includes_cluster_event_context():
    module = load_report_module()

    digest = module.build_report_contract_digest(cluster_event_fact_text())

    assert digest["cluster_event_context"]["status"] == "degraded_service_candidate"
    assert (
        digest["cluster_event_context"]["signal_counts"]
        == "impala_daemon_error_event=3, catalog_error_event=1"
    )
    assert any(
        "Cluster event context status: degraded_service_candidate" == item
        for item in digest["case_differentiators"]
    )
    assert any(
        "signal_counts: impala_daemon_error_event=3" in item
        for item in digest["evidence_groups"]["cluster_event_context"]
    )
    assert any(
        "Cluster Event Context contains bounded event summary" in item
        for item in digest["supported_summary_points"]
    )


def test_report_contract_digest_includes_evidence_quality():
    module = load_report_module()

    digest = module.build_report_contract_digest(backend_fact_text())

    assert digest["evidence_quality"] == {
        "score": "90/100",
        "level": "high",
        "strengths": [
            "profile operators parsed: 9",
            "query wall-clock available from CM Query Context",
        ],
        "limitations": ["CM metrics context is unavailable"],
    }
    assert any(
        "Evidence quality: score=90/100, level=high" == item
        for item in digest["case_differentiators"]
    )
    assert digest["evidence_groups"]["evidence_quality"] == [
        "Evidence Quality: score=90/100, level=high",
        "limitation: CM metrics context is unavailable",
        "strength: profile operators parsed: 9",
        "strength: query wall-clock available from CM Query Context",
    ]
    assert any(
        "Evidence Quality is score=90/100, level=high" in item
        for item in digest["supported_summary_points"]
    )


def test_report_normalization_inserts_evidence_quality_into_supporting_evidence():
    module = load_report_module()

    normalized = module.normalize_report_text(
        safe_structured_report(),
        facts_text=backend_fact_text(),
        language="ru",
    )

    assert "- Evidence Quality: score=90/100, level=high" in normalized
    assert "limitations: CM metrics context is unavailable" in normalized
    assert "рамку уверенности и покрытия" in normalized


def test_deterministic_report_body_uses_evidence_quality_group():
    module = load_report_module()

    body = module.deterministic_report_body(
        backend_fact_text(),
        language="en",
        mode="admin",
    )

    assert "- evidence_quality: Evidence Quality: score=90/100, level=high" in body
    assert "- evidence_quality: limitation: CM metrics context is unavailable" in body


def test_report_contract_digest_includes_cm_metrics_correlation():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
- Memory anomalies: 1

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed
- network_io_spike: observed

## CM Metrics Correlation

- status: available
- coverage: 4/4 metrics ok, 40 points
- correlated_signals: 2
- context_only_signals: 0
- guardrail: CM metrics can strengthen profile-supported evidence, but they are not standalone root-cause proof.
- daemon_memory_growth: correlated (metric=observed, strength=moderate)
- network_io_spike: correlated (metric=observed, strength=moderate)

## Cluster Runtime Context

- status: available
- collection_status: collected
- coverage: 4/4 metrics ok, 40 points
- metrics_profile: cm6
- window_scope: bounded query runtime window with 60s padding
- limit_summary: max_points_per_query=10, max_response_bytes=12345
- scoring_contribution: +4 triage score points from 2 correlated CM metric signal(s), capped at +6; context-only, unknown and not_observed signals do not add score
- guardrail: Cluster runtime context is deterministic follow-up context only.

### Signal rollup

- observed_signals: Daemon memory growth, Network I/O spike
- correlated_signals: Daemon memory growth, Network I/O spike
- context_only_signals: none
- unknown_signals: none
- not_observed_signals: none
"""

    digest = module.build_report_contract_digest(facts)

    assert digest["cm_metrics_correlation"]["correlated_signals"] == "2"
    assert digest["cm_metrics_correlation"]["daemon_memory_growth"].startswith("correlated")
    assert digest["cm_metrics_correlation"]["network_io_spike"].startswith("correlated")
    assert digest["metrics_facts"] == digest["cm_metrics"]
    assert digest["metrics_correlation"] == digest["cm_metrics_correlation"]
    assert digest["cluster_runtime_context"]["coverage"] == "4/4 metrics ok, 40 points"
    assert (
        digest["cluster_runtime_context"]["correlated_signals"]
        == "Daemon memory growth, Network I/O spike"
    )
    assert digest["cluster_runtime_context"]["scoring_contribution"].startswith(
        "+4 triage score points"
    )
    assert any(
        "Runtime metrics correlated signals: 2" == item for item in digest["case_differentiators"]
    )
    assert any(
        "Network I/O spike: correlated" in item
        for item in digest["evidence_groups"]["cm_metrics_correlation"]
    )
    assert (
        digest["evidence_groups"]["metrics_correlation"]
        == digest["evidence_groups"]["cm_metrics_correlation"]
    )
    assert any(
        "scoring_contribution: +4 triage score points" in item
        for item in digest["evidence_groups"]["cluster_runtime_context"]
    )
    assert any(
        "Runtime Metrics Correlation contains 2 correlated runtime context signal" in item
        for item in digest["supported_summary_points"]
    )
    assert any(
        "Cluster Runtime Context is a Python-owned runtime summary" in item
        for item in digest["supported_summary_points"]
    )


def test_report_contract_digest_accepts_provider_neutral_runtime_metrics_headings():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Runtime Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed
- network_io_spike: observed

## Runtime Metrics Correlation

- status: available
- coverage: 4/4 metrics ok, 40 points
- correlated_signals: 2
- context_only_signals: 0
- guardrail: Runtime metrics can strengthen profile-supported evidence, but they are not standalone root-cause proof.
- daemon_memory_growth: correlated (metric=observed, strength=moderate)
- network_io_spike: correlated (metric=observed, strength=moderate)
"""

    digest = module.build_report_contract_digest(facts)

    assert digest["cm_metrics"]["coverage"] == "4/4 metrics ok, 40 points"
    assert digest["cm_metrics"]["daemon_memory_growth"] == "observed"
    assert digest["cm_metrics_correlation"]["correlated_signals"] == "2"
    assert digest["cm_metrics_correlation"]["network_io_spike"].startswith("correlated")
    assert digest["metrics_facts"] == digest["cm_metrics"]
    assert digest["metrics_correlation"] == digest["cm_metrics_correlation"]
    assert any(
        "Runtime Metrics Facts" not in item and "Network I/O spike: observed" in item
        for item in digest["evidence_groups"]["cm_metrics"]
    )
    assert digest["evidence_groups"]["metrics_facts"] == digest["evidence_groups"]["cm_metrics"]


def test_report_normalization_inserts_cm_metrics_correlation_admin_check():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 1
- Memory anomalies: 0

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- network_io_spike: observed
- network_io_spike_basis: host network I/O max=200.00 MiB/s avg=20.00 MiB/s ratio=10.00x; series_count=4; top series max/peer max=1.25x

## CM Metrics Correlation

- status: available
- coverage: 4/4 metrics ok, 40 points
- correlated_signals: 1
- context_only_signals: 0
- guardrail: CM metrics can strengthen profile-supported evidence, but they are not standalone root-cause proof.
- network_io_spike: correlated (metric=observed, strength=moderate)
"""

    normalized = module.normalize_report_text(safe_structured_report(), facts_text=facts)

    assert (
        "Runtime metrics collected; 4/4 metrics ok, 40 points; correlated=1, context-only=0"
        in normalized
    )
    assert "observed context signals: network I/O spike" in normalized
    assert "series spread: network I/O top/peer=1.25x" in normalized
    assert "Runtime Metrics Correlation" in normalized
    assert "correlated signals использовать только как runtime context" in normalized
    assert "context-only metrics не считать root cause" in normalized


def test_report_normalization_inserts_cluster_runtime_context_evidence():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- network_io_spike: observed

## CM Metrics Correlation

- status: available
- correlated_signals: 1
- context_only_signals: 1
- network_io_spike: correlated (metric=observed, strength=moderate)

## Cluster Runtime Context

- status: available
- collection_status: collected
- coverage: 4/4 metrics ok, 40 points
- metrics_profile: cm6
- window_scope: bounded query runtime window with 60s padding
- limit_summary: max_points_per_query=10, max_response_bytes=12345
- scoring_contribution: +2 triage score points from 1 correlated CM metric signal(s), capped at +6; context-only, unknown and not_observed signals do not add score
- guardrail: Cluster runtime context is deterministic follow-up context only.

### Signal rollup

- observed_signals: Network I/O spike, Host disk I/O pressure
- correlated_signals: Network I/O spike
- context_only_signals: Host disk I/O pressure
- unknown_signals: none
- not_observed_signals: none
"""

    normalized = module.normalize_report_text(safe_structured_report(), facts_text=facts)

    assert "Cluster runtime context collected; 4/4 metrics ok, 40 points" in normalized
    assert "correlated signals: Network I/O spike" in normalized
    assert "context-only signals: Host disk I/O pressure" in normalized
    assert "+2 triage score points from 1 correlated runtime metric signal" in normalized
    assert "not standalone root-cause proof" in normalized


def test_report_normalization_inserts_cluster_event_context_evidence():
    module = load_report_module()

    normalized = module.normalize_report_text(
        safe_structured_report(), facts_text=cluster_event_fact_text()
    )

    assert "Cluster event context collected; status=degraded_service_candidate" in normalized
    assert "signals: impala_daemon_error_event=3, catalog_error_event=1" in normalized
    assert (
        "Treat Cluster Event Context as follow-up context, not standalone root-cause proof"
        in normalized
    )


def test_report_validation_rejects_causal_cluster_event_claims():
    module = load_report_module()
    report = "CM Events caused the query slowdown because an Impala daemon error event was present."

    errors = module.validate_report_against_facts(report, cluster_event_fact_text())

    assert "CM event context is described as causal" in errors


def test_analyzer_facts_appendix_includes_cluster_event_context():
    from query_doctor.report.facts_appendix import render_analyzer_facts_appendix

    appendix = render_analyzer_facts_appendix(cluster_event_fact_text(), language="en")

    assert "### Cluster Event Context" in appendix
    assert "- status: degraded_service_candidate" in appendix
    assert "#### Cluster event signal rollup" in appendix
    assert "impala_daemon_error_event" in appendix
    assert "#### Cluster event next checks" in appendix


def test_report_normalization_rewrites_cm_context_only_causal_wording():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed
- daemon_memory_growth_basis: daemon memory min=10.00 GiB max=23.00 GiB delta=13.00 GiB ratio=2.30x

## CM Metrics Correlation

- status: available
- correlated_signals: 0
- context_only_signals: 1
- daemon_memory_growth: context_only (metric=observed, strength=weak)
"""
    report = "Рост памяти демона может указывать на неправильную оценку объема данных."

    normalized = module.normalize_report_text(report, facts_text=facts)

    assert "может указывать" not in normalized
    assert "Runtime metrics context-only" in normalized
    assert module.validate_report_against_facts(normalized, facts) == []


def test_report_normalization_rewrites_cm_context_only_causal_wording_in_english():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- daemon_memory_growth: observed

## CM Metrics Correlation

- status: available
- correlated_signals: 0
- context_only_signals: 1
- daemon_memory_growth: context_only (metric=observed, strength=weak)
"""
    report = "Daemon memory growth is the root cause of the query slowdown."

    normalized = module.normalize_report_text(report, facts_text=facts, language="en")

    assert "root cause of the query slowdown" not in normalized
    assert "the observed runtime signal is not treated as a cause" in normalized
    assert not any("\u0400" <= char <= "\u04ff" for char in normalized)
    assert module.validate_report_safety_text(normalized, facts_text=facts, language="en") == []


def test_analyzer_facts_appendix_escapes_redacted_angle_bracket_placeholders():
    from query_doctor.report.facts_appendix import render_analyzer_facts_appendix

    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## Table Metadata Context

### Table: <db>.<table>

- context path: `impala_context.json`
- table stats row-count completeness: missing/unknown
- SHOW CREATE TABLE status: ok
- owner: <user>
"""

    appendix = render_analyzer_facts_appendix(facts, language="en")

    assert "&lt;db&gt;.&lt;table&gt;" in appendix
    assert "&lt;user&gt;" in appendix
    assert "<db>" not in appendix
    assert "context path" not in appendix
    assert "impala_context.json" not in appendix
    assert "SHOW CREATE TABLE" not in appendix
    assert "[metadata statement hidden] status: ok" in appendix
    assert module.validate_report_safety_text(appendix, facts_text=facts, language="en") == []


def test_report_cm_metrics_evidence_bullet_mentions_collection_limits():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## CM Metrics Facts

- status: partial
- coverage: 5/6 metrics ok, 10400 points
- network_io_spike: unknown
- network_io_spike_basis: host network I/O metric is missing or has insufficient points

### CM metrics limitations

- CM metrics collection limits: max_points_per_query=4000, max_response_bytes=3145728.
- CM metrics were truncated for: host_cpu_user, host_network_receive_rate.
- CM metrics unavailable for: host_network_transmit_rate.

## CM Metrics Correlation

- status: available
- correlated_signals: 0
- context_only_signals: 0
"""

    normalized = module.normalize_report_text(safe_structured_report(), facts_text=facts)

    assert "Runtime metrics collected; 5/6 metrics ok, 10400 points" in normalized
    assert "some metric summaries were truncated by collection limits" in normalized
    assert "some allowlisted metrics were unavailable" in normalized


def test_report_validator_blocks_cm_context_only_causal_wording():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## CM Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- network_io_spike: observed

## CM Metrics Correlation

- status: available
- correlated_signals: 0
- context_only_signals: 1
- network_io_spike: context_only (metric=observed, strength=weak)
"""
    report = "Network I/O spike может указывать на сетевую причину."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "context-only signal is described as causal" in errors[0]


def test_report_validator_blocks_runtime_metrics_context_only_causal_wording():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## Runtime Metrics Facts

- status: available
- coverage: 4/4 metrics ok, 40 points
- network_io_spike: observed

## Runtime Metrics Correlation

- status: available
- correlated_signals: 0
- context_only_signals: 1
- network_io_spike: context_only (metric=observed, strength=weak)
"""
    report = "Network I/O spike может указывать на сетевую причину."

    errors = module.validate_report_against_facts(report, facts)

    assert errors
    assert "context-only signal is described as causal" in errors[0]


def test_report_contract_digest_is_structured_and_python_owned():
    module = load_report_module()

    digest = module.build_report_contract_digest(metadata_fact_text_with_raw_context_noise())

    assert digest["summary"]["Cardinality anomalies"] == "1"
    assert digest["evidence_flags"]["has_metadata_stats_gap"] is True
    assert digest["supported_summary_points"]
    assert digest["case_differentiators"]
    assert "evidence_groups" in digest
    assert digest["recommendation_candidates"][0]["id"] == "stats_maintenance"
    assert "raw_secret" not in json.dumps(digest, ensure_ascii=False)


def test_report_contract_digest_includes_action_card_operator_differentiators():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 2
- Memory anomalies: 1

## Action Cards

### Card 1: Severe memory underestimation at high-memory operator

Evidence:
- operator: 19:NESTED LOOP JOIN (INNER JOIN)
- actual rows: 438.25M
- estimated rows: 64093.94T
- actual/estimated ratio: 0.00x
- peak memory: 43.40 GiB
- estimated peak memory: 125.81 KiB
- peak/estimated memory ratio: 361720x
"""

    digest = module.build_report_contract_digest(facts)

    serialized = json.dumps(digest["case_differentiators"], ensure_ascii=False)
    assert "19:NESTED LOOP JOIN" in serialized
    assert "peak/estimated memory ratio: 361720x" in serialized


def test_report_validator_rejects_unsupported_conclusion_in_short_summary():
    module = load_report_module()

    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0

## What is NOT supported by the parsed evidence

- No parsed actual-vs-estimated row count anomaly above threshold.
"""
    report = safe_structured_report().replace(
        "- Profile-level facts показывают маленький baseline без выраженной нагрузки.",
        "- No parsed actual-vs-estimated row count anomaly above threshold.",
        1,
    )

    errors = module.validate_report_text(report, facts_text=facts, min_chars=0, min_sections=0)

    assert (
        "short summary contains unsupported conclusion that belongs in Что НЕ подтверждается фактами"
        in errors
    )


def test_report_normalizer_removes_legacy_unclosed_collapsed_section():
    module = load_report_module()
    facts = """
# Query Doctor deterministic analysis facts

## Summary

- Cardinality anomalies: 0
- Memory anomalies: 0
"""

    report = safe_structured_report()
    report = report.replace(
        "## Подробный разбор",
        "<details>\n<summary>Подробный разбор</summary>\n\n## Подробный разбор",
        1,
    )

    normalized = module.normalize_report_text(report, facts_text=facts)

    assert "<details>" not in normalized
    assert "</details>" not in normalized
    assert (
        module.validate_report_text(normalized, facts_text=facts, min_chars=0, min_sections=0) == []
    )


def test_report_prompt_without_metadata_facts_omits_metadata_digest():
    module = load_report_module()

    prompt = sample_prompt(module, mode="admin")

    assert "METADATA FACTS DIGEST BEGIN" not in prompt
    assert "## Metadata Facts Digest" not in prompt


@pytest.mark.parametrize(
    "report",
    [
        "Причина — устаревшая статистика.",
        "Проблема вызвана устаревшей статистикой.",
        "Запрос тормозит из-за устаревшей статистики.",
        "Root cause is stale statistics.",
        "Metadata proves stale stats are the cause.",
        "COMPUTE STATS is required.",
        "Нужно выполнить COMPUTE STATS.",
        "Выполнить COMPUTE STATS.",
        "Run COMPUTE STATS for all tables.",
        "Run COMPUTE STATS on src.foo.",
        "Execute COMPUTE STATS.",
        "Recompute stats using COMPUTE STATS.",
        "You should run COMPUTE STATS.",
        "We need to run COMPUTE STATS.",
        "Запустить COMPUTE STATS.",
        "Пересчитать статистику через COMPUTE STATS.",
        "Необходимо запустить COMPUTE STATS.",
        "Статистика таблицы устарела.",
        "Metadata proves the root cause.",
        "Нет доказательств, что статистика является причиной, но нужно выполнить COMPUTE STATS.",
        "Нет подтверждения, что статистика устарела, но причина — устаревшая статистика.",
        "Нет доказательств, что статистика устарела, однако проблема вызвана устаревшей статистикой.",
        "Не подтверждено, что статистика устарела, но запрос тормозит из-за устаревшей статистики.",
        "Нет доказательств, что статистика является причиной, но root cause is stale statistics.",
        "Нет данных о том, что статистика устарела, но причина — устаревшая статистика.",
        "Нет сведений о том, что статистика устарела, однако проблема вызвана устаревшей статистикой.",
        "Нет признаков устаревшей статистики, но root cause is stale statistics.",
        "Statistics maintenance should fix the slowdown.",
        "Refreshing stats is the right fix for this query.",
        "Treat missing stats as the reason this query slowed down.",
        "Stats gaps explain the bad plan.",
        "Stats maintenance is recommended because missing stats caused the issue.",
        "The metadata gap explains why Impala chose the slow plan.",
    ],
)
def test_report_validator_rejects_unsupported_metadata_root_cause_and_compute_claims(report):
    module = load_report_module()

    errors = module.validate_report_against_facts(
        report, metadata_fact_text_with_raw_context_noise()
    )

    assert errors


@pytest.mark.parametrize(
    "report",
    [
        "Статистика по части колонок неполная/неизвестная.",
        "Это может влиять на оценки оптимизатора.",
        "Следующая проверка — посмотреть статистику по колонкам join/filter.",
        "Нет подтверждения того, что статистика таблиц устарела.",
        "Нет доказательств, что статистика таблиц устарела.",
        "Не подтверждено, что статистика таблиц устарела.",
        "В профиле нет доказательств устаревшей статистики.",
        "Нет данных о том, что статистика таблиц устарела.",
        "Нет сведений о том, что статистика таблиц устарела.",
        "Нет признаков того, что статистика таблиц устарела.",
        "В профиле нет данных об устаревшей статистике.",
        "В профиле нет сведений об устаревшей статистике.",
        "Отсутствуют данные о том, что статистика таблиц устарела.",
        "Нет доказательств, что статистика является причиной.",
        "Нет подтверждения, что проблема вызвана статистикой.",
        "Статистика по части колонок неполная/неизвестная; это стоит проверить отдельно.",
        "Неполная статистика может влиять на оценки оптимизатора, но это не подтверждённая причина.",
        "The available metadata context can support approved stats maintenance, but it does not prove a root cause by itself.",
        "Stats maintenance may be worth checking, but it is not a proven fix.",
        "The metadata gap does not explain the slowdown by itself.",
        "Refreshing stats can be a comparable-rerun experiment, not a proven fix.",
    ],
)
def test_report_validator_allows_safe_conditional_metadata_wording(report):
    module = load_report_module()

    assert (
        module.validate_report_against_facts(report, metadata_fact_text_with_raw_context_noise())
        == []
    )
