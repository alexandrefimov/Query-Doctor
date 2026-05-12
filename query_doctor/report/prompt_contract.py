"""Python-owned report prompt assembly derived from analysis facts."""

from __future__ import annotations

from pathlib import Path

from query_doctor.impala.metadata_digest import build_metadata_facts_digest
from query_doctor.report.contract_digest import (
    FACT_APPENDIX_MAX_ITEMS,
    action_card_differentiators,
    build_report_contract_digest,
    case_summary_differentiators,
    evidence_groups,
    format_report_contract_digest,
    markdown_bullet_lines,
    markdown_subheading_titles,
    supported_summary_points,
)
from query_doctor.report.facts_extractors import (
    backend_summary_value,
    facts_cardinality_anomaly_count,
    facts_has_backend_tail_evidence,
    facts_text_for_model_prompt,
    parse_backend_tail_summary,
)
from query_doctor.report.language_contract import get_report_language_contract
from query_doctor.report.recommendation_candidates import (
    MAX_RECOMMENDATION_ITEMS,
    format_recommendation_candidates,
    recommendation_candidate_lines,
)


def _heading_label(heading: str) -> str:
    return heading.lstrip("#").strip()


def _localized(language: str, ru_text: str, en_text: str) -> str:
    return ru_text if language == "ru" else en_text


def _language_instruction(language: str) -> str:
    if language == "ru":
        return "Ответ должен быть на русском языке."
    if language == "en":
        return "Write the report in English."
    return f"Language: {language}."


def _estimate_heading_guidance(language: str) -> str:
    if language == "ru":
        return (
            '- Do not put ratio-below-1 row facts under a broad "Недооценение количества строк" / '
            '"row underestimation" heading. If the section mixes ratio-above-1 and ratio-below-1 '
            'operators, title it "Расхождения оценок строк" or "Проблемы с оценками строк".\n'
            '- For ratio-below-1 row facts, say "оценка выше факта" or '
            '"недооценка по этому оператору не подтверждена"; do not call that operator underestimated.'
        )
    return (
        '- Do not put ratio-below-1 row facts under a broad "row underestimation" heading. '
        "If the section mixes ratio-above-1 and ratio-below-1 operators, title it "
        '"row estimate mismatches" or "mixed row estimate gaps".\n'
        '- For ratio-below-1 row facts, say "the estimate is above the actual row count" or '
        '"underestimation is not supported for this operator"; do not call that operator underestimated.'
    )


def _operator_time_guidance(language: str) -> str:
    if language == "ru":
        return (
            '- Prefer "operator/profile time counter", "time counter reported for this operator", '
            '"в профиле накоплено большое operator time", or "оператор выделяется по времени в профиле".\n'
            '- Avoid "оператор выполняется X часов", "оператор выполнялся X часов", '
            '"время выполнения X", "the operator ran for X hours", and '
            '"the query ran for X because this operator took X".'
        )
    return (
        '- Prefer "operator/profile time counter", "time counter reported for this operator", '
        'or "this operator stands out by profile time counter".\n'
        '- Avoid "the operator ran for X hours", "the operator took X hours", and '
        '"the query ran for X because this operator took X".'
    )


def build_cardinality_contract(facts_text: str, *, language: str = "ru") -> str:
    count = facts_cardinality_anomaly_count(facts_text)
    if count == 0:
        safe_wording = _localized(
            language,
            '- Required safe Russian wording: "Анализатор не обнаружил подтверждённой аномалии кардинальности."\n'
            '- In Russian, forbidden positive claim wording includes "недооценка кардинальности", '
            '"фактические строки превышают оценку", "количество строк превышает оценки", '
            '"оценки были слишком низкими", "устаревшая статистика стала причиной", '
            '"перекос доказан", and "hot keys доказаны".\n'
            '- Do not put the English phrase "cardinality underestimation" in parentheses after a Russian sentence unless that exact matched phrase is itself clearly negated as unsupported.',
            '- Required safe English wording: "The analyzer did not find a confirmed cardinality anomaly."\n'
            '- Forbidden positive claim wording includes "cardinality underestimation", '
            '"actual rows exceed estimates", "estimates were too low", '
            '"stale statistics caused the issue", "skew is proven", and "hot keys are proven" '
            "unless the exact matched phrase is clearly negated as unsupported.",
        )
        return """
Cardinality evidence contract:
- analysis_facts.md says Cardinality anomalies: 0.
- No analyzer-supported cardinality anomaly was found.
- Do not claim cardinality underestimation, row-estimate underestimation, stale stats, hot keys, or proven skew.
- Do not say actual rows exceed estimates, estimated rows are too low, or low estimates caused row growth.
- Do not recommend stats maintenance from Cardinality anomalies alone when the count is 0.
- The report must explicitly say that cardinality underestimation is not supported by extracted facts.
{safe_wording}
- If separate metadata facts support a stats action, frame it as approved stats maintenance, not as a proven root cause from cardinality facts.
""".strip().format(safe_wording=safe_wording)
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


def build_backend_tail_contract(facts_text: str, mode: str, *, language: str = "ru") -> str:
    if facts_has_backend_tail_evidence(facts_text):
        summary = parse_backend_tail_summary(facts_text)
        summary_lines = f"""
Parsed Backend / Host Tail Evidence summary:
- host tail candidates: {backend_summary_value(summary, "host tail candidates")}
- data skew: {backend_summary_value(summary, "data skew")}
- execution skew: {backend_summary_value(summary, "execution skew")}
- write-path anomaly: {backend_summary_value(summary, "write-path anomaly")}
""".strip()
        if language == "en":
            shared_rules = f"""
{summary_lines}
- Keep backend data skew separate from cardinality/row-estimate anomaly.
- Backend data skew means rows/records are distributed unevenly across parsed backends; it does not prove stale stats, cardinality underestimation, optimizer row-estimate failure, or SQL hot keys.
- If Cardinality anomalies: 0, backend data skew still must not be described as cardinality underestimation or bad/missing stats.
- If data skew is yes, allowed wording is: "rows/records are distributed unevenly across backends".
- If execution skew is no or host tail candidates is 0, say no single slow backend/tail host is proven; do not claim one host is proven slow, a tail backend is proven, or execution skew is proven.
- If write-path anomaly is unknown, write/RPC/HDFS path may be listed only as a next diagnostic check, not as the proven cause.
""".strip()
            if mode == "user":
                return f"""
Backend/host-tail evidence contract:
- analysis_facts.md contains Backend / Host Tail Evidence or host-tail findings.
- Prioritize passing backend/host evidence to the platform team over SQL rewrite advice unless SQL/cardinality facts also support SQL changes.
- User-facing wording must say: "send backend/host evidence from analysis_facts.md to the platform team".
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


def build_mode_instruction(mode: str, *, language: str = "ru") -> str:
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
        stats_process = _localized(
            language,
            'Frame stats maintenance as "через утверждённый operational process".',
            'Frame stats maintenance as "through the approved operational process".',
        )
        return """
Report mode: unified.
Audience: SQL query author, analyst, or data engineer first; DBA/platform details go into the admin section.
Use Action Cards as the main structure when present, but explain them in simpler language.
Focus on concrete SQL-owner actions: approved stats maintenance, reducing intermediate rows, pre-aggregation/materialization, pushing filters earlier, and rewriting joins/window inputs when facts support those actions.
Put admin/platform checks and evidence packages only under "Follow-up checks".
Do not invent table names, join/filter column names, query id, timestamps, pool names, or commands.
Do not tell users to run COMPUTE STATS, REFRESH, or INVALIDATE METADATA as automatic actions.
{stats_process}
Do not say facts indicate stale or missing stats unless analysis_facts.md explicitly proves that.
Avoid unsupported low-level claims and vague advice such as "optimize joins", "check", "look at", or "reduce skew" unless accompanied by a concrete action.
""".strip().format(stats_process=stats_process)
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
    contract = get_report_language_contract(language)
    short_summary_label = _heading_label(contract.short_summary_heading)
    recommendations_label = _heading_label(contract.recommendations_heading)
    detailed_label = _heading_label(contract.detailed_report_heading)
    supported_findings_label = _heading_label(contract.evidence_safe_problems_heading)
    evidence_label = _heading_label(contract.evidence_heading)
    amplifiers_label = _heading_label(contract.amplifiers_heading)
    not_supported_label = _heading_label(contract.not_supported_heading)
    next_checks_label = _heading_label(contract.next_checks_heading)
    language_instruction = _language_instruction(language)
    mode_instruction = build_mode_instruction(mode, language=language)
    cardinality_contract = build_cardinality_contract(facts_text, language=language)
    backend_tail_contract = build_backend_tail_contract(facts_text, mode, language=language)
    prompt_facts_text = facts_text_for_model_prompt(facts_text)
    metadata_digest = build_metadata_facts_digest(facts_text, language=language)
    recommendation_candidates = recommendation_candidate_lines(facts_text, language=language)
    recommendation_candidate_block = format_recommendation_candidates(recommendation_candidates)
    report_contract_digest = format_report_contract_digest(facts_text, language=language)
    estimate_heading_guidance = _estimate_heading_guidance(language)
    operator_time_guidance = _operator_time_guidance(language)
    recommendation_language_instruction = _localized(
        language,
        "Paraphrase them in Russian, merge adjacent candidates, and shorten wording; do not copy candidate text verbatim unless no natural shorter wording is possible.",
        "Paraphrase them in English, merge adjacent candidates, and shorten wording; do not copy candidate text verbatim unless no natural shorter wording is possible.",
    )
    vague_recommendation_examples = _localized(
        language,
        'Do not write vague recommendations such as "проверить", "посмотреть", "проанализировать", "оптимизировать запрос" without a concrete action.',
        'Do not write vague recommendations such as "check", "look at", "analyze", "investigate", or "optimize the query" without a concrete action.',
    )
    negative_caveat_examples = _localized(
        language,
        'Do not include "нет подтверждений", "не подтверждается", "не доказано", "отсутствует evidence", or similar negative caveats here.',
        'Do not include "no confirmation", "not supported", "not proven", "evidence is absent", or similar negative caveats here.',
    )
    row_estimate_heading_guidance = _localized(
        language,
        'Use "Недооценение количества строк" only for operators whose facts show actual rows > estimated rows or ratio > 1. If the section includes mixed estimate directions, use "Расхождения оценок строк" / "Проблемы с оценками строк" instead.',
        'Use "row underestimation" only for operators whose facts show actual rows > estimated rows or ratio > 1. If the section includes mixed estimate directions, use "row estimate mismatches" or "mixed row estimate gaps" instead.',
    )
    stronger_root_cause_titles = _localized(
        language,
        '"Главная причина замедления" or "Root cause"',
        '"Main slowdown cause" or "Root cause"',
    )
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
Do not parse or infer anything from profile_digest.md, profile.txt, query_metadata.json, cm_metadata.json, raw profiles, SQL text, or external knowledge.
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
{estimate_heading_guidance}
- Memory underestimation is separate from row/cardinality underestimation.
- Memory underestimation means actual/peak memory is larger than estimated memory or actual/estimated memory ratio is above 1.
- Memory overestimation means actual/peak memory is lower than estimated memory or actual/estimated memory ratio is below 1.
- Memory estimate mismatch/gap means the direction is mixed or unclear.
- Do not call actual/estimated memory ratio below 1 memory underestimation.
- Do not call lower actual memory an overload unless absolute memory, spill, or scratch evidence supports it.
- Do not use operators with mem ratio below 1.0 as evidence for memory underestimation.
- If an operator has rows ratio above threshold but mem ratio below 1.0, use it only as cardinality/intermediate-row evidence, not memory-underestimation evidence.
- Do not present Impala operator/profile counter time as query wall-clock duration unless analysis_facts.md explicitly provides query wall-clock evidence.
{operator_time_guidance}
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
- Use Runtime Metrics Facts as the only metrics interpretation source. Do not infer from CM Time-Series Context or raw aggregates.
- Runtime Metrics Facts statuses mean exactly: observed = bounded runtime context signal, not_observed = checked below threshold, unknown = unavailable or insufficient facts.
- Use Cluster Runtime Context only as a compact Python-owned summary of runtime metrics coverage, correlated/context-only signal rollup, limitations, and bounded triage score contribution.
- Cluster Runtime Context scoring contribution explains why the deterministic triage score changed; it is not a performance-speedup estimate and not causal proof.
- Use Cluster Event Context only as a Python-owned raw-free event summary. Cluster event signals are cluster/service context and follow-up checks, not standalone root-cause proof.
- Do not claim service restarts, daemon errors, catalog errors, metastore issues, disk capacity events, HDFS/YARN events, authentication failures, or cluster events caused this query unless analysis_facts.md explicitly contains direct causal correlation.
- Do not state CPU, memory, daemon, network, HDFS, or cluster pressure as a root cause from runtime metrics alone.
- Mention observed runtime metrics in "{short_summary_label}" only when they are useful confirmed context for this query; keep not_observed and unknown metric statuses out of the short summary.
- Put unknown/not_observed runtime metric limitations under "{not_supported_label}" or "{next_checks_label}", not in the short summary.

The final markdown file is assembled by the wrapper with only:
# Query Doctor Report

Do not write "# Query Doctor Report" yourself.
Do not write source artifact names, facts sha256, model names, runtime details, or generation timestamps in the report.
Do not write "{contract.analyzer_facts_heading}"; Python appends that deterministic section after validation.
If Metadata Facts Digest is present, it is curated by Python from analysis_facts.md and may be used only as supporting evidence.
Do not read or infer from raw SHOW output, raw DDL, impala_context.md, or impala_context.json.
Do not claim metadata proves the root cause, do not claim stats are stale unless explicitly supported, and do not recommend COMPUTE STATS as required.
You must write only the report body, starting with exactly this compact structure:

{contract.short_summary_heading}

4-6 concise bullets. State only confirmed facts from analysis_facts.md. Do not write that evidence is absent, not proven, missing, or unsupported in this top section. {negative_caveat_examples} If a fact is not confirmed, omit it from the short summary.
When case_differentiators contains concrete operator IDs, ratios, memory values, or totals, include at least two of those concrete differentiators in this section instead of generic wording.

{contract.recommendations_heading}

Use only the Python-owned recommendation candidates from PYTHON-OWNED RECOMMENDATION CANDIDATES.
{recommendation_language_instruction} You must not add a new action, diagnostic task, command, platform check, or optimization target that is absent from that candidate list.
Write 1-5 concrete actions that can lead to optimization without asking the reader to perform open-ended investigation. If only one Python-owned candidate is useful, write one item instead of padding this section with generic follow-up.
{vague_recommendation_examples}
Do not put SHOW TABLE STATS, SHOW COLUMN STATS, per-host checks, spill/scratch checks, admission pool checks, CM metrics/logs, profile counters, or evidence packages in "{recommendations_label}"; those belong only under "{next_checks_label}".
If metadata stats are missing/incomplete/unknown but Cardinality anomalies is 0, the top-level action may mention approved stats maintenance only when that action appears in the Python-owned candidate list; it must not say stats explain the query problem or optimizer estimates.

"{short_summary_label}" requirements:
- Use 4-6 concise bullets unless the facts are sparse; 2-6 bullets or short paragraphs are allowed, but never more than 6.
- Combine repeated operator examples; do not list every operator in the short summary.
- Base every claim only on analysis_facts.md.
- Mention only the main supported symptom/problem and supported optimization direction.
- Do not introduce any fact that is absent from "{detailed_label}" and analysis_facts.md.
- Do not state root cause unless analysis_facts.md directly supports it.
- Do not write missing/unsupported evidence caveats in this section.
- Obey all estimate-direction, backend-skew, write-path, spill/scratch, and operator/profile-time rules below.

{contract.detailed_report_heading}
{contract.evidence_safe_problems_heading}
{contract.evidence_heading}
{contract.amplifiers_heading}
{contract.not_supported_heading}

{contract.next_checks_heading}

Section requirements:
- Preserve the detailed report structure under "{detailed_label}" using the required ### subsections listed above.
- Put absent/missing/unsupported evidence only into "{not_supported_label}", never into "{short_summary_label}".
- Put platform/admin checks only into "{next_checks_label}".
- Put read-only SHOW checks, spill/scratch checks, per-host checks, CM metrics/logs, profile counters, admission pool checks, and evidence packages only into "{next_checks_label}".
- Keep every optional section short.

Python-owned slot contract:
- Use "recommendation_candidates" as the complete allowed source for "{recommendations_label}".
- Use "supported_summary_points" as the allowed meaning space for "{short_summary_label}"; do not copy it verbatim unless it already reads naturally.
- Use "case_differentiators" to make "{short_summary_label}" specific to this query: prefer concrete operator IDs, ratios, memory values, top Action Card/Finding titles, and safe totals/counts that distinguish this case from other reports.
- Use "evidence_groups" to organize "{detailed_label}" into readable narrative. You may explain why a supported signal matters, but do not add new facts or causes.
- Use "cm_metrics" only as Python-owned bounded runtime context. Do not derive metrics claims from other sections.
- Use "cluster_event_context" only as Python-owned bounded Cluster Event Context. Put event-driven checks under "{next_checks_label}", not as recommendations unless the candidate list contains that action target.
- Use "unsupported_conclusions" only under "{not_supported_label}".
- Use "action_card_titles", "finding_titles", "summary", "totals", and "evidence_flags" to choose what is worth mentioning.
- Do not introduce a user-facing fact, unsupported conclusion, or action target that is absent from the digest or deterministic facts.

Slot freedom levels:
- Python-owned targets with LLM wording: "{recommendations_label}" must stay mapped to recommendation_candidates, but wording should be natural and case-specific.
- Deterministic/canonical: "{not_supported_label}" and "{next_checks_label}" must stay close to Python-owned candidates/checks.
- Controlled narrative: "{short_summary_label}" and "{detailed_label}" should be human wording over supported_summary_points and evidence_groups.
- Do not merely repeat analyzer lines when a concise explanation is possible; compress and explain supported facts without inventing a cause.

Recommendation ownership rules:
- Python/analyzer owns recommendation facts and allowed action targets.
- LLM owns only wording, ordering, and concision.
- Every item in "{recommendations_label}" must map to one of the Python-owned candidates below.
- Do not use Action Cards directly as recommendations unless the same action is represented in the Python-owned candidate list.
- When Cardinality anomalies: 0, omit stats maintenance unless separate metadata facts support it.
- Do not claim stats are stale or missing unless analysis_facts.md explicitly proves that.
- Do not ask whether stats were updated unless analysis_facts.md mentions a prior stats change.
- Do not claim HDFS bottleneck, network instability, external-network action, codegen problem, or spill unless the candidate list explicitly contains that target.

Report writing guidance:
- Be concise and engineering-focused.
- Separate deterministic facts from hypotheses.
- Quote concrete operators and ratios only when they appear in the facts.
- Use the subsection title "{supported_findings_label}"; do not use stronger root-cause titles such as {stronger_root_cause_titles} unless analysis_facts.md itself uses causal language.
- In "{supported_findings_label}", name cardinality estimate underestimation only for operators where facts show actual rows > estimated rows or ratio > 1.
- In "{evidence_label}", group facts separately: row estimate mismatch, memory mismatch, expensive operators, intermediate/exchange traffic.
- {row_estimate_heading_guidance}
- In "{amplifiers_label}", discuss SORT/ANALYTIC and memory underestimation only where the facts support them.
- In "{amplifiers_label}", do not call EXCHANGE a main memory bottleneck if its absolute peak memory is small; describe it as intermediate/exchange data volume only.
- In "{not_supported_label}", explicitly carry over unsupported conclusions from facts.
- In "{recommendations_label}", use only the digest recommendation_candidates.

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
