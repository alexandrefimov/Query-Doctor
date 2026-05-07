"""Python-owned report prompt contract derived from analysis facts."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from query_doctor.impala.metadata_digest import build_metadata_facts_digest
from query_doctor.report.facts_extractors import (
    backend_data_skew_is_supported,
    backend_has_proven_tail,
    backend_summary_value,
    cm_metrics_correlation_points,
    cm_metrics_correlation_summary,
    cm_metrics_facts_summary,
    cm_metrics_observed_points,
    cm_metrics_profile_supported,
    facts_cardinality_anomaly_count,
    facts_has_backend_tail_evidence,
    facts_have_action_cards,
    facts_have_large_intermediate_or_exchange,
    facts_have_metadata_stats_gap,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
    facts_text_for_model_prompt,
    first_bullet_value,
    parse_backend_tail_summary,
)
from query_doctor.report.markdown import extract_markdown_section, extract_markdown_subsection


MAX_RECOMMENDATION_ITEMS = 5
FACT_APPENDIX_MAX_ITEMS = 8


def build_cardinality_contract(facts_text: str) -> str:
    count = facts_cardinality_anomaly_count(facts_text)
    if count == 0:
        return """
Cardinality evidence contract:
- analysis_facts.md says Cardinality anomalies: 0.
- No analyzer-supported cardinality anomaly was found.
- Do not claim cardinality underestimation, row-estimate underestimation, stale stats, hot keys, or proven skew.
- Do not say actual rows exceed estimates, estimated rows are too low, or low estimates caused row growth.
- Do not recommend stats maintenance from Cardinality anomalies alone when the count is 0.
- The report must explicitly say that cardinality underestimation is not supported by extracted facts.
- Required safe Russian wording: "Анализатор не обнаружил подтверждённой аномалии кардинальности."
- In Russian, forbidden positive claim wording includes "недооценка кардинальности", "фактические строки превышают оценку", "количество строк превышает оценки", "оценки были слишком низкими", "устаревшая статистика стала причиной", "перекос доказан", and "hot keys доказаны".
- Do not put the English phrase "cardinality underestimation" in parentheses after a Russian sentence unless that exact matched phrase is itself clearly negated as unsupported.
- If separate metadata facts support a stats action, frame it as approved stats maintenance, not as a proven root cause from cardinality facts.
""".strip()
    if count and count > 0:
        return """
Cardinality evidence contract:
- analysis_facts.md contains one or more cardinality anomalies.
- Cardinality wording must use only the operator IDs, row counts, ratios, and evidence present in analysis_facts.md.
- Use row/cardinality underestimation only for operators where actual rows > estimated rows or actual/estimated ratio > 1.
- Use row/cardinality overestimation only for operators where actual rows < estimated rows or actual/estimated ratio < 1.
- Use "estimate mismatch" / "estimate gap" when the direction is mixed or unclear.
- Do not describe an operator as row/cardinality-underestimated if its evidence line shows actual rows < estimated rows or ratio < 1.
- Memory underestimation is separate from row/cardinality underestimation; do not infer row underestimation from peak-memory evidence.
- Do not invent join keys, table names, hot keys, or stale statistics.
""".strip()
    return """
Cardinality evidence contract:
- Use cardinality wording only when analysis_facts.md explicitly contains cardinality anomaly evidence.
- If cardinality evidence is absent or unclear, say it is not supported by extracted facts.
- Direction rule still applies: underestimation means actual > estimated; overestimation means actual < estimated.
""".strip()


def build_backend_tail_contract(facts_text: str, mode: str) -> str:
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        summary_lines = f"""
Parsed Backend / Host Tail Evidence summary:
- host tail candidates: {backend_summary_value(summary, "host tail candidates")}
- data skew: {backend_summary_value(summary, "data skew")}
- execution skew: {backend_summary_value(summary, "execution skew")}
- write-path anomaly: {backend_summary_value(summary, "write-path anomaly")}
""".strip()
        shared_rules = f"""
{summary_lines}
- Keep backend data skew separate from cardinality/row-estimate anomaly.
- Backend data skew means rows/records are distributed unevenly across parsed backends; it does not prove stale stats, cardinality underestimation, optimizer row-estimate failure, or SQL hot keys.
- If Cardinality anomalies: 0, backend data skew still must not be described as cardinality underestimation or bad/missing stats.
- If data skew is yes, allowed wording is: "rows/records are distributed unevenly across backends".
- If data skew is yes, safe Russian wording is: "Есть подтверждённый data skew по RowsProduced".
- If data skew is yes, do not say data skew or data distribution skew is absent; only execution skew / single tail host may be absent when the summary says so.
- If data skew is yes, do not say backend row/record distribution evidence is absent.
- If execution skew is no or host tail candidates is 0, say no single slow backend/tail host is proven; do not claim one host is proven slow, a tail backend is proven, or execution skew is proven.
- If write-path anomaly is unknown, write/RPC/HDFS path may be listed only as a next diagnostic check, not as the proven cause.
""".strip()
        if mode == "user":
            return f"""
Backend/host-tail evidence contract:
- analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- Prioritize passing backend/host evidence to the platform team over SQL rewrite advice unless SQL/cardinality facts also support SQL changes.
- User-facing wording must say: "передайте платформенной команде backend/host evidence из analysis_facts.md".
- Host/network/HDFS/RPC/write-path items are checks for admins, not proven root causes.
- Do not claim network or HDFS is the root cause.
{shared_rules}
""".strip()
        return f"""
Backend/host-tail evidence contract:
- analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- Prioritize platform/host-tail evidence and admin checks before generic SQL rewrite advice unless SQL/cardinality facts also support SQL changes.
- Use conservative wording: "execution tail suspected" and "host-specific write/RPC/HDFS path should be checked".
- Host/network/HDFS/RPC/write-path items are checks, not proven root causes.
- Do not claim network or HDFS is the root cause.
{shared_rules}
""".strip()
    return """
Backend/host-tail evidence contract:
- Do not add host-tail, network, HDFS, or RPC-path diagnosis unless analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- If absent, keep host/network/HDFS checks out of primary findings unless another deterministic fact supports them.
""".strip()


def build_mode_instruction(mode: str) -> str:
    if mode == "admin":
        return """
Report mode: unified.
Audience: SQL owner first; DBA/platform details go into the admin section.
Use Action Cards as the main structure when present.
Keep the visible top report short and action-oriented.
Mention operator IDs/names, actual vs estimated rows, memory estimation gaps, bytes read/sent, spill/scratch/admission checks only when mentioned in facts.
Put per-host RowsProduced / PeakMemUsage, admission pool, CM metrics/logs, and profile counter checks only under "Follow-up checks".
Do not say skew is proven unless analysis_facts.md contains deterministic per-host skew evidence.
Do not claim stats are stale unless analysis_facts.md proves it.
Do not claim exact join keys unless analysis_facts.md contains them.
Avoid generic advice such as "optimize the query", "optimize joins", "check", "look at", or "reduce skew" unless accompanied by a concrete action.
""".strip()
    if mode == "user":
        return """
Report mode: unified.
Audience: SQL query author, analyst, or data engineer first; DBA/platform details go into the admin section.
Use Action Cards as the main structure when present, but explain them in simpler language.
Focus on concrete SQL-owner actions: approved stats maintenance, reducing intermediate rows, pre-aggregation/materialization, pushing filters earlier, and rewriting joins/window inputs when facts support those actions.
Put admin/platform checks and evidence packages only under "Follow-up checks".
Do not invent table names, join/filter column names, query id, timestamps, pool names, or commands.
Do not tell users to run COMPUTE STATS, REFRESH, or INVALIDATE METADATA as automatic actions.
Frame stats maintenance as "через утверждённый operational process".
Do not say facts indicate stale or missing stats unless analysis_facts.md explicitly proves that.
Avoid unsupported low-level claims and vague advice such as "optimize joins", "check", "look at", or "reduce skew" unless accompanied by a concrete action.
""".strip()
    raise ValueError(f"unsupported report mode: {mode}")


def build_prompt(
    *,
    facts_text: str,
    facts_path: Path,
    facts_sha256: str,
    model: str,
    language: str,
    mode: str = "admin",
) -> str:
    language_instruction = "Ответ должен быть на русском языке." if language == "ru" else f"Language: {language}."
    mode_instruction = build_mode_instruction(mode)
    cardinality_contract = build_cardinality_contract(facts_text)
    backend_tail_contract = build_backend_tail_contract(facts_text, mode)
    prompt_facts_text = facts_text_for_model_prompt(facts_text)
    metadata_digest = build_metadata_facts_digest(facts_text)
    recommendation_candidates = recommendation_candidate_lines(facts_text)
    recommendation_candidate_block = format_recommendation_candidates(recommendation_candidates)
    report_contract_digest = format_report_contract_digest(facts_text)
    metadata_digest_block = (
        f"\n\nMETADATA FACTS DIGEST BEGIN\n{metadata_digest}\nMETADATA FACTS DIGEST END"
        if metadata_digest
        else ""
    )

    return f"""
You are only a report writer.
Use only facts from analysis_facts.md.
Use only facts provided below.
The PYTHON-OWNED REPORT CONTRACT DIGEST is the authoritative slot contract for the report.
Use the longer deterministic facts only for wording details that support that contract.
When the digest and longer deterministic facts appear to conflict, follow the digest for report slot selection.
Do not parse or infer anything from profile_digest.md, profile.txt, raw profiles, SQL text, or external knowledge.
Do not invent metrics, operator IDs, root causes, timings, row counts, memory values, table names, columns, or SQL rewrites.
If something is not present in facts, say it is not supported by parsed evidence.
Preserve the "What is NOT supported" conclusions.
Do not recommend HDFS block size, replication factor, external network fixes, disabling codegen, or spill tuning unless facts explicitly support it.
Do not output hidden reasoning, chain-of-thought, or <think> blocks.
Do not call any operator, JOIN, EXCHANGE, table, metric, or estimate gap the main/root/primary bottleneck, source, or cause unless analysis_facts.md explicitly uses causal wording for that exact item.
Prefer Action Cards when present. If Action Cards are absent, fall back to the other deterministic facts.
Do not invent table names, join keys, row counts, memory numbers, commands, or remediation steps outside analysis_facts.md.
If evidence is missing, say it is missing.

{language_instruction}

{mode_instruction}

{cardinality_contract}

{backend_tail_contract}

Engineering interpretation rules:
- The report must distinguish cardinality mismatch from memory mismatch.
- Row/cardinality underestimation means actual rows are larger than estimated rows or actual/estimated ratio is above 1.
- Row/cardinality overestimation means actual rows are smaller than estimated rows or actual/estimated ratio is below 1.
- Use "estimate mismatch" / "estimate gap" when estimate direction is mixed or unclear.
- Do not describe an operator as row/cardinality-underestimated when its evidence line shows actual rows < estimated rows or ratio < 1.
- Do not put ratio-below-1 row facts under a broad "Недооценение количества строк" / "row underestimation" heading. If the section mixes ratio-above-1 and ratio-below-1 operators, title it "Расхождения оценок строк" or "Проблемы с оценками строк".
- For ratio-below-1 row facts, say "оценка выше факта" or "недооценка по этому оператору не подтверждена"; do not call that operator underestimated.
- Memory underestimation is separate from row/cardinality underestimation.
- Memory underestimation means actual/peak memory is larger than estimated memory or actual/estimated memory ratio is above 1.
- Memory overestimation means actual/peak memory is lower than estimated memory or actual/estimated memory ratio is below 1.
- Memory estimate mismatch/gap means the direction is mixed or unclear.
- Do not call actual/estimated memory ratio below 1 memory underestimation.
- Do not call lower actual memory an overload unless absolute memory, spill, or scratch evidence supports it.
- Do not use operators with mem ratio below 1.0 as evidence for memory underestimation.
- If an operator has rows ratio above threshold but mem ratio below 1.0, use it only as cardinality/intermediate-row evidence, not memory-underestimation evidence.
- Do not present Impala operator/profile counter time as query wall-clock duration unless analysis_facts.md explicitly provides query wall-clock evidence.
- Prefer "operator/profile time counter", "time counter reported for this operator", "в профиле накоплено большое operator time", or "оператор выделяется по времени в профиле".
- Avoid "оператор выполняется X часов", "оператор выполнялся X часов", "время выполнения X", "the operator ran for X hours", and "the query ran for X because this operator took X".
- Evidence-safe summary wording may mention actual rows in millions vs estimated rows around 10.55K only when analysis_facts.md contains that cardinality anomaly evidence.
- Keep backend data skew, execution skew, cardinality/row-estimate anomaly, memory estimate anomaly, and write-path anomaly as separate categories.
- Do not use backend data skew as evidence for cardinality underestimation, stale stats, or optimizer row-estimate failure.
- Do not claim a single slow backend/tail host unless Backend / Host Tail Evidence has host tail candidates above zero and execution skew is yes.
- Distinguish "large intermediate/exchange traffic" from external network instability.
- Do not recommend checking external network based only on TotalBytesSent.
- TotalBytesSent means intermediate/exchange data volume unless facts explicitly say network fault.
- Do not describe EXCHANGE as a main memory bottleneck when absolute peak memory is small.
- For memory impact, prefer operators with large absolute peak memory, especially GiB-scale SORT/HASH JOIN.
- Treat skew and spill only as established causes if the facts explicitly contain skew evidence or non-zero spill/scratch metrics.
- If skew/spill evidence is absent, mention them only under "Follow-up checks".
- If analysis_facts.md contains a Spill or scratch I/O finding, do not say spill/scratch evidence is absent; say non-zero spill/scratch metric evidence exists and keep causal wording separate.
- Use CM Metrics Facts as the only metrics interpretation source. Do not infer from CM Time-Series Context or raw aggregates.
- CM Metrics Facts statuses mean exactly: observed = bounded runtime context signal, not_observed = checked below threshold, unknown = unavailable or insufficient facts.
- Do not state CPU, memory, daemon, network, HDFS, or cluster pressure as a root cause from CM metrics alone.
- Mention observed CM metrics in "Краткий вывод" only when they are useful confirmed context for this query; keep not_observed and unknown metric statuses out of the short summary.
- Put unknown/not_observed CM metric limitations under "Что НЕ подтверждается фактами" or "Follow-up checks", not in the short summary.

The final markdown file is assembled by the wrapper with only:
# Query Doctor Report

Do not write "# Query Doctor Report" yourself.
Do not write source artifact names, facts sha256, model names, runtime details, or generation timestamps in the report.
Do not write "## Факты анализатора"; Python appends that deterministic section after validation.
If Metadata Facts Digest is present, it is curated by Python from analysis_facts.md and may be used only as supporting evidence.
Do not read or infer from raw SHOW output, raw DDL, impala_context.md, or impala_context.json.
Do not claim metadata proves the root cause, do not claim stats are stale unless explicitly supported, and do not recommend COMPUTE STATS as required.
You must write only the report body, starting with exactly this compact structure:

## Краткий вывод

4-6 concise bullets. State only confirmed facts from analysis_facts.md. Do not write that evidence is absent, not proven, missing, or unsupported in this top section. Do not include "нет подтверждений", "не подтверждается", "не доказано", "отсутствует evidence", or similar negative caveats here. If a fact is not confirmed, omit it from the short summary.
When case_differentiators contains concrete operator IDs, ratios, memory values, or totals, include at least two of those concrete differentiators in this section instead of generic wording.

## Практические рекомендации

Use only the Python-owned recommendation candidates from PYTHON-OWNED RECOMMENDATION CANDIDATES.
Paraphrase them in Russian, merge adjacent candidates, and shorten wording; do not copy candidate text verbatim unless no natural shorter wording is possible. You must not add a new action, diagnostic task, command, platform check, or optimization target that is absent from that candidate list.
Write 2-5 concrete actions that can lead to optimization without asking the reader to perform open-ended investigation.
Do not write vague recommendations such as "проверить", "посмотреть", "проанализировать", "оптимизировать запрос" without a concrete action.
Do not put SHOW TABLE STATS, SHOW COLUMN STATS, per-host checks, spill/scratch checks, admission pool checks, CM metrics/logs, profile counters, or evidence packages in "Практические рекомендации"; those belong only under "Follow-up checks".
If metadata stats are missing/incomplete/unknown but Cardinality anomalies is 0, the top-level action may mention approved stats maintenance only when that action appears in the Python-owned candidate list; it must not say stats explain the query problem or optimizer estimates.

"Краткий вывод" requirements:
- Use 4-6 concise bullets unless the facts are sparse; 2-6 bullets or short paragraphs are allowed, but never more than 6.
- Combine repeated operator examples; do not list every operator in the short summary.
- Base every claim only on analysis_facts.md.
- Mention only the main supported symptom/problem and supported optimization direction.
- Do not introduce any fact that is absent from "Подробный разбор" and analysis_facts.md.
- Do not state root cause unless analysis_facts.md directly supports it.
- Do not write missing/unsupported evidence caveats in this section.
- Obey all estimate-direction, backend-skew, write-path, spill/scratch, and operator/profile-time rules below.

## Подробный разбор
### Основные подтверждённые проблемы по профилю
### Подтверждающие факты
### Что усиливает проблему
### Что НЕ подтверждается фактами

### Follow-up checks

Section requirements:
- Preserve the detailed report structure under "Подробный разбор" using the required ### subsections listed above.
- Put absent/missing/unsupported evidence only into "Что НЕ подтверждается фактами", never into "Краткий вывод".
- Put platform/admin checks only into "Follow-up checks".
- Put read-only SHOW checks, spill/scratch checks, per-host checks, CM metrics/logs, profile counters, admission pool checks, and evidence packages only into "Follow-up checks".
- Keep every optional section short.

Python-owned slot contract:
- Use "recommendation_candidates" as the complete allowed source for "Практические рекомендации".
- Use "supported_summary_points" as the allowed meaning space for "Краткий вывод"; do not copy it verbatim unless it already reads naturally.
- Use "case_differentiators" to make "Краткий вывод" specific to this query: prefer concrete operator IDs, ratios, memory values, top Action Card/Finding titles, and safe totals/counts that distinguish this case from other reports.
- Use "evidence_groups" to organize "Подробный разбор" into readable narrative. You may explain why a supported signal matters, but do not add new facts or causes.
- Use "cm_metrics" only as Python-owned bounded runtime context. Do not derive metrics claims from other sections.
- Use "unsupported_conclusions" only under "Что НЕ подтверждается фактами".
- Use "action_card_titles", "finding_titles", "summary", "totals", and "evidence_flags" to choose what is worth mentioning.
- Do not introduce a user-facing fact, unsupported conclusion, or action target that is absent from the digest or deterministic facts.

Slot freedom levels:
- Python-owned targets with LLM wording: "Практические рекомендации" must stay mapped to recommendation_candidates, but wording should be natural and case-specific.
- Deterministic/canonical: "Что НЕ подтверждается фактами" and "Follow-up checks" must stay close to Python-owned candidates/checks.
- Controlled narrative: "Краткий вывод" and "Подробный разбор" should be human wording over supported_summary_points and evidence_groups.
- Do not merely repeat analyzer lines when a concise explanation is possible; compress and explain supported facts without inventing a cause.

Recommendation ownership rules:
- Python/analyzer owns recommendation facts and allowed action targets.
- LLM owns only wording, ordering, and concision.
- Every item in "Практические рекомендации" must map to one of the Python-owned candidates below.
- Do not use Action Cards directly as recommendations unless the same action is represented in the Python-owned candidate list.
- When Cardinality anomalies: 0, omit stats maintenance unless separate metadata facts support it.
- Do not claim stats are stale or missing unless analysis_facts.md explicitly proves that.
- Do not ask whether stats were updated unless analysis_facts.md mentions a prior stats change.
- Do not claim HDFS bottleneck, network instability, external-network action, codegen problem, or spill unless the candidate list explicitly contains that target.

Report writing guidance:
- Be concise and engineering-focused.
- Separate deterministic facts from hypotheses.
- Quote concrete operators and ratios only when they appear in the facts.
- Use the subsection title "Основные подтверждённые проблемы по профилю"; do not use stronger root-cause titles such as "Главная причина замедления" or "Root cause" unless analysis_facts.md itself uses causal language.
- In "Основные подтверждённые проблемы по профилю", name cardinality estimate underestimation only for operators where facts show actual rows > estimated rows or ratio > 1.
- In "Подтверждающие факты", group facts separately: row estimate mismatch, memory mismatch, expensive operators, intermediate/exchange traffic.
- Use "Недооценение количества строк" only for operators whose facts show actual rows > estimated rows or ratio > 1. If the section includes mixed estimate directions, use "Расхождения оценок строк" / "Проблемы с оценками строк" instead.
- In "Что усиливает проблему", discuss SORT/ANALYTIC and memory underestimation only where the facts support them.
- In "Что усиливает проблему", do not call EXCHANGE a main memory bottleneck if its absolute peak memory is small; describe it as intermediate/exchange data volume only.
- In "Что НЕ подтверждается фактами", explicitly carry over unsupported conclusions from facts.
- In "Практические рекомендации", use only the digest recommendation_candidates.

DETERMINISTIC FACTS BEGIN
{prompt_facts_text}
DETERMINISTIC FACTS END

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{recommendation_candidate_block}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

PYTHON-OWNED REPORT CONTRACT DIGEST BEGIN
{report_contract_digest}
PYTHON-OWNED REPORT CONTRACT DIGEST END{metadata_digest_block}
""".strip()

def recommendation_candidate_lines(facts_text: str) -> list[tuple[str, str]]:
    """Return Python-owned optimization actions derived only from deterministic facts."""
    candidates: list[tuple[str, str]] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    memory_count = facts_memory_anomaly_count(facts_text)

    def add(candidate_id: str, text: str) -> None:
        if all(existing_text != text for _, existing_text in candidates):
            candidates.append((candidate_id, text))

    if (cardinality_count and cardinality_count > 0) or facts_have_metadata_stats_gap(facts_text):
        add(
            "stats_maintenance",
            "Собрать или обновить статистику по затронутым таблицам, "
            "где в фактах отмечены cardinality anomalies или missing/incomplete stats.",
        )

    if cardinality_count and cardinality_count > 0:
        add(
            "reduce_row_growth",
            "Сократить рост строк перед доминирующими JOIN/AGGREGATE/EXCHANGE операторами: "
            "применить раннюю фильтрацию или предварительную агрегацию на входах из Action Cards.",
        )
        add(
            "rewrite_join_filter",
            "Переписать форму JOIN/фильтра так, чтобы уменьшить intermediate rows перед операторами "
            "с высокой стоимостью.",
        )

    if memory_count and memory_count > 0:
        add(
            "reduce_memory_input",
            "Уменьшить объём данных, поступающих в оператор с memory estimate gap, через меньший "
            "intermediate result до JOIN/AGGREGATE.",
        )

    if facts_have_large_intermediate_or_exchange(facts_text):
        add(
            "reduce_exchange_rows",
            "Снизить объём intermediate/exchange rows до перераспределения данных: отфильтровать, "
            "агрегировать или материализовать меньший промежуточный результат раньше.",
        )
        add(
            "reduce_exchange_payload",
            "Сократить payload до EXCHANGE/data movement: оставить в промежуточном результате только "
            "нужные колонки и перенести безопасные фильтры или агрегацию раньше.",
        )
        if cm_metrics_profile_supported(facts_text, "network_io_spike"):
            add(
                "align_exchange_with_network_context",
                "Учитывать observed CM network I/O spike как runtime context и приоритизировать "
                "сокращение exchange payload только там, где профиль уже показывает large data movement.",
            )

    if facts_have_spill_scratch_evidence(facts_text):
        add(
            "reduce_spill_pressure",
            "Снизить memory pressure, связанный с подтверждённым spill/scratch evidence, за счёт "
            "уменьшения intermediate data до memory-heavy operators.",
        )

    if cm_metrics_profile_supported(facts_text, "daemon_memory_growth") or cm_metrics_profile_supported(
        facts_text,
        "daemon_memory_pressure",
    ):
        add(
            "reduce_runtime_memory_footprint",
            "Снизить runtime memory footprint запроса: убрать лишние intermediate columns, сузить "
            "partition/filter scope и уменьшить входы JOIN/AGGREGATE/SORT без изменения результата.",
        )

    if cm_metrics_profile_supported(facts_text, "host_cpu_pressure") and (
        cardinality_count and cardinality_count > 0 or facts_have_large_intermediate_or_exchange(facts_text)
    ):
        add(
            "reduce_cpu_work_with_profile_evidence",
            "Снизить CPU work только в местах, где profile facts уже показывают row growth или "
            "large intermediate/exchange traffic: фильтровать, агрегировать или сокращать payload раньше.",
        )

    if candidates and all(candidate_id != "rerun_after_change" for candidate_id, _ in candidates):
        add(
            "rerun_after_change",
            "После изменения снять новый профиль и сравнить подтверждённые факты: "
            "wall-clock, host-tail evidence, operator rows/memory и runtime metrics context.",
        )

    if not candidates:
        add(
            "baseline",
            "Использовать этот результат как baseline для сравнения с новым профилем после изменения запроса.",
        )
        add(
            "no_shape_change",
            "Не менять SQL shape по этому профилю: текущие facts не показывают дорогой оператор "
            "или рост intermediate rows.",
        )
        add(
            "rerun_after_change",
            "Запускать дальнейшие изменения только если новый профиль покажет confirmed operator evidence.",
        )

    return candidates[:MAX_RECOMMENDATION_ITEMS]


def format_recommendation_candidates(candidates: list[tuple[str, str]]) -> str:
    return "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)


def markdown_bullet_lines(lines: list[str], *, limit: int = FACT_APPENDIX_MAX_ITEMS) -> list[str]:
    bullets = [line.strip() for line in lines if line.lstrip().startswith("- ")]
    return bullets[:limit]


def markdown_subheading_titles(lines: list[str], *, prefix: str = "### ", limit: int = FACT_APPENDIX_MAX_ITEMS) -> list[str]:
    titles = [line[len(prefix) :].strip() for line in lines if line.startswith(prefix)]
    return titles[:limit]


def supported_summary_points(facts_text: str) -> list[str]:
    points: list[str] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    memory_count = facts_memory_anomaly_count(facts_text)
    if cardinality_count and cardinality_count > 0:
        points.append(
            "В parsed facts есть подтверждённые cardinality estimate anomalies; "
            "описание должно сохранять направление estimate mismatch."
        )
    if memory_count and memory_count > 0:
        points.append(
            "В parsed facts есть memory estimate anomalies; это отдельный сигнал от cardinality mismatch."
        )
    if facts_have_large_intermediate_or_exchange(facts_text):
        points.append(
            "В parsed facts есть large intermediate/exchange traffic; описывать как data movement volume, "
            "не как external network instability."
        )
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        if backend_data_skew_is_supported(summary):
            points.append(
                "Backend facts support data skew по RowsProduced; это не доказывает cardinality underestimation."
            )
        if backend_has_proven_tail(summary):
            points.append("Backend facts support execution skew / host-tail evidence.")
        else:
            points.append("Backend facts do not prove a single slow tail host unless execution skew is yes.")
    if facts_have_spill_scratch_evidence(facts_text):
        points.append(
            "Parsed findings contain non-zero spill/scratch metric evidence; keep causal wording separate."
        )
    if facts_have_metadata_stats_gap(facts_text):
        points.append(
            "Metadata digest shows table/column stats gaps; frame stats work as approved maintenance, not proven root cause."
        )
    for point in cm_metrics_observed_points(facts_text):
        points.append(
            f"CM Metrics Facts contain an observed context signal: {point}. "
            "Use it as bounded runtime context, not as standalone root cause."
        )
    cm_correlation = cm_metrics_correlation_summary(facts_text)
    correlated_signals = cm_correlation.get("correlated_signals")
    context_only_signals = cm_correlation.get("context_only_signals")
    if correlated_signals and correlated_signals != "0":
        points.append(
            f"CM Metrics Correlation contains {correlated_signals} correlated runtime context signal(s); "
            "these may strengthen profile-supported evidence, not standalone root-cause claims."
        )
    elif context_only_signals and context_only_signals != "0":
        points.append(
            f"CM Metrics Correlation contains {context_only_signals} context-only signal(s); "
            "keep them out of root-cause wording and SQL optimizer actions."
        )
    if not points:
        points.append("Parsed facts do not select a confirmed optimization target; use this report as a baseline.")
    return points[:FACT_APPENDIX_MAX_ITEMS]


def action_card_differentiators(action_card_lines: list[str], *, limit: int = 3) -> list[str]:
    differentiators: list[str] = []
    current_title: str | None = None
    current_values: dict[str, str] = {}

    def flush() -> None:
        if len(differentiators) >= limit or not current_title:
            return
        operator = current_values.get("operator")
        if not operator:
            return
        details = [f"Action Card operator: {operator}", current_title]
        for label in (
            "actual rows",
            "estimated rows",
            "actual/estimated ratio",
            "peak memory",
            "estimated peak memory",
            "peak/estimated memory ratio",
        ):
            value = current_values.get(label)
            if value:
                details.append(f"{label}: {value}")
        differentiators.append("; ".join(details))

    for line in action_card_lines:
        stripped = line.strip()
        if stripped.startswith("### Card "):
            flush()
            current_title = stripped[4:].strip()
            current_values = {}
            continue
        match = re.match(r"^-\s*(?P<label>[A-Za-z/ ]+):\s*(?P<value>.+?)\s*$", stripped)
        if match and current_title:
            current_values[match.group("label").strip()] = match.group("value").strip()
    flush()
    return differentiators


def case_summary_differentiators(facts_text: str) -> list[str]:
    """Return safe case-specific facts that help the LLM avoid generic summaries."""
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    query_wall_clock_lines = extract_markdown_section(facts_text, "## Query Wall Clock")
    evidence_quality_lines = extract_markdown_section(facts_text, "## Evidence Quality")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    backend_summary = parse_backend_tail_summary(facts_text)
    backend_lines = extract_markdown_section(facts_text, "## Backend / Host Tail Evidence")
    backend_normalized_lines = extract_markdown_subsection(backend_lines, "### Normalized tail candidates")
    cm_metrics = cm_metrics_facts_summary(facts_text)

    differentiators: list[str] = []
    for label in (
        "Parsed operators",
        "Cardinality anomalies",
        "Memory anomalies",
        "Zero/unknown row estimate gaps",
        "Zero/unknown memory estimate gaps",
    ):
        value = first_bullet_value(summary_lines, label)
        if value:
            differentiators.append(f"{label}: {value}")
    wall_clock = first_bullet_value(query_wall_clock_lines, "duration")
    wall_clock_source = first_bullet_value(query_wall_clock_lines, "source")
    wall_clock_confidence = first_bullet_value(query_wall_clock_lines, "confidence")
    if wall_clock:
        detail_parts = [wall_clock]
        if wall_clock_source:
            detail_parts.append(f"source={wall_clock_source}")
        if wall_clock_confidence:
            detail_parts.append(f"confidence={wall_clock_confidence}")
        differentiators.append(f"Query wall-clock: {', '.join(detail_parts)}")
    evidence_quality_score = first_bullet_value(evidence_quality_lines, "score")
    evidence_quality_level = first_bullet_value(evidence_quality_lines, "level")
    if evidence_quality_score or evidence_quality_level:
        parts = []
        if evidence_quality_score:
            parts.append(f"score={evidence_quality_score}")
        if evidence_quality_level:
            parts.append(f"level={evidence_quality_level}")
        differentiators.append(f"Evidence quality: {', '.join(parts)}")
    for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent"):
        value = first_bullet_value(totals_lines, label)
        if value:
            differentiators.append(f"{label}: {value}")

    differentiators.extend(action_card_differentiators(action_card_lines))
    for title in markdown_subheading_titles(action_card_lines, limit=3):
        if len(differentiators) >= FACT_APPENDIX_MAX_ITEMS:
            break
        differentiators.append(f"Action Card: {title}")
    for title in markdown_subheading_titles(findings_lines, limit=3):
        differentiators.append(f"Finding: {title}")

    for label in (
        "host tail candidates",
        "execution tail candidates",
        "read-rate tail candidates",
        "write-path tail candidates",
        "data skew",
        "execution skew",
        "write-path anomaly",
    ):
        value = backend_summary_value(backend_summary, label)
        if value != "unknown":
            differentiators.append(f"Backend {label}: {value}")
    for line in backend_normalized_lines:
        stripped = line.strip()
        if not stripped.startswith("|") or stripped.startswith("|---") or "metric_key" in stripped:
            continue
        differentiators.append(f"Backend normalized tail candidate: {stripped}")
        break

    if cm_metrics.get("coverage"):
        differentiators.append(f"CM metrics coverage: {cm_metrics['coverage']}")
    for point in cm_metrics_observed_points(facts_text):
        differentiators.append(f"CM metric signal: {point}")
    cm_correlation = cm_metrics_correlation_summary(facts_text)
    if cm_correlation.get("correlated_signals"):
        differentiators.append(f"CM metrics correlated signals: {cm_correlation['correlated_signals']}")
    for point in cm_metrics_correlation_points(facts_text):
        differentiators.append(f"CM metric correlation: {point}")

    return differentiators[:FACT_APPENDIX_MAX_ITEMS]


def evidence_groups(facts_text: str) -> dict[str, list[str]]:
    groups: dict[str, list[str]] = {}
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )
    action_cards = markdown_subheading_titles(action_card_lines)
    findings = markdown_subheading_titles(findings_lines)
    unsupported = markdown_bullet_lines(limitation_lines)
    cm_metric_points = cm_metrics_observed_points(facts_text)
    cm_metric_correlation_points = cm_metrics_correlation_points(facts_text)
    if action_cards:
        groups["action_cards"] = action_cards
    if findings:
        groups["findings"] = findings
    if cm_metric_points:
        groups["cm_metrics"] = cm_metric_points
    if cm_metric_correlation_points:
        groups["cm_metrics_correlation"] = cm_metric_correlation_points
    if unsupported:
        groups["unsupported"] = unsupported
    return groups


def build_report_contract_digest(facts_text: str) -> dict[str, Any]:
    """Return a compact Python-owned contract for LLM report slots."""
    summary_lines = extract_markdown_section(facts_text, "## Summary")
    totals_lines = extract_markdown_section(facts_text, "## Totals")
    evidence_quality_lines = extract_markdown_section(facts_text, "## Evidence Quality")
    action_card_lines = extract_markdown_section(facts_text, "## Action Cards")
    findings_lines = extract_markdown_section(facts_text, "## Findings")
    limitation_lines = extract_markdown_section(
        facts_text,
        "## What is NOT supported by the parsed evidence",
    )
    backend_summary = parse_backend_tail_summary(facts_text)
    cm_metrics = cm_metrics_facts_summary(facts_text)
    cm_metrics_correlation = cm_metrics_correlation_summary(facts_text)
    return {
        "summary": {
            label: first_bullet_value(summary_lines, label)
            for label in (
                "Parsed operators",
                "Cardinality anomalies",
                "Memory anomalies",
                "Zero/unknown row estimate gaps",
                "Zero/unknown memory estimate gaps",
            )
            if first_bullet_value(summary_lines, label) is not None
        },
        "totals": {
            label: first_bullet_value(totals_lines, label)
            for label in ("TotalTime", "TotalBytesRead", "TotalBytesSent")
            if first_bullet_value(totals_lines, label) is not None
        },
        "evidence_flags": {
            "has_action_cards": facts_have_action_cards(facts_text),
            "has_backend_tail_evidence": facts_has_backend_tail_evidence(facts_text),
            "has_spill_scratch_evidence": facts_have_spill_scratch_evidence(facts_text),
            "has_metadata_stats_gap": facts_have_metadata_stats_gap(facts_text),
            "has_large_intermediate_or_exchange": facts_have_large_intermediate_or_exchange(facts_text),
        },
        "backend_summary": backend_summary,
        "cm_metrics": cm_metrics,
        "cm_metrics_correlation": cm_metrics_correlation,
        "evidence_quality": {
            label: first_bullet_value(evidence_quality_lines, label)
            for label in ("score", "level")
            if first_bullet_value(evidence_quality_lines, label) is not None
        },
        "supported_summary_points": supported_summary_points(facts_text),
        "case_differentiators": case_summary_differentiators(facts_text),
        "evidence_groups": evidence_groups(facts_text),
        "recommendation_candidates": [
            {"id": candidate_id, "text": text}
            for candidate_id, text in recommendation_candidate_lines(facts_text)
        ],
        "action_card_titles": markdown_subheading_titles(action_card_lines),
        "finding_titles": markdown_subheading_titles(findings_lines),
        "unsupported_conclusions": markdown_bullet_lines(limitation_lines),
    }


def format_report_contract_digest(facts_text: str) -> str:
    return json.dumps(
        build_report_contract_digest(facts_text),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
