"""Trusted report text normalization and validation boundary."""

from __future__ import annotations

import os
import re
from pathlib import Path

from query_doctor.report.claim_validation import (
    find_unsupported_metadata_claim_errors,
    find_zero_cardinality_unsupported_claims,
)
from query_doctor.report.contract import ANALYZER_FACTS_HEADING
from query_doctor.report.estimate_validation import (
    find_contradicted_memory_overestimation_claims,
    find_contradicted_memory_underestimation_claims,
    find_contradicted_row_underestimation_claims,
    normalize_contradicted_estimate_direction,
)
from query_doctor.report.facts_extractors import (
    backend_has_proven_tail,
    cluster_event_context_report_evidence_bullet,
    cluster_runtime_context_report_evidence_bullet,
    cm_metrics_correlation_summary,
    cm_metrics_report_evidence_bullet,
    evidence_quality_report_evidence_bullet,
    facts_cardinality_anomaly_count,
    facts_has_backend_tail_evidence,
    facts_have_action_cards,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
    parse_backend_tail_summary,
)
from query_doctor.report.language_contract import (
    ReportLanguageContract,
    get_report_language_contract,
)
from query_doctor.report.llm_client import PROGRESS_PREFIX
from query_doctor.report.markdown import strip_markdown_section
from query_doctor.report.recommendations import (
    has_unsupported_recommendation_topic,
    insert_bullets_into_section,
    insert_required_bullets_into_section,
    normalize_practical_recommendations,
)
from query_doctor.report.runtime_claim_validation import (
    SPILL_SCRATCH_NEXT_CHECK,
    facts_have_admission_or_pool_evidence,
    find_backend_tail_claim_errors,
    find_cluster_event_context_claim_errors,
    find_cm_context_only_claim_errors,
    find_primary_bottleneck_overclaim_errors,
    find_spill_scratch_claim_errors,
    find_unsafe_operator_time_wording,
    normalize_cm_context_only_overclaim,
    normalize_operator_time_wording,
    normalize_primary_bottleneck_overclaim,
    normalize_supported_evidence_contradiction,
    should_rewrite_spill_storage_line,
    should_rewrite_stats_freshness_claim,
    stats_freshness_missing_evidence_note,
)
from query_doctor.report.safety_validation import (
    REPORT_INTERNAL_FINGERPRINT_RE,
    contains_raw_sql_like_text,
    validate_report_html_safety,
    validate_report_internal_fingerprints,
    validate_report_language_safety,
)
from query_doctor.report.text_postprocess import (
    move_misplaced_admin_bullets_into_admin_section,
    move_misplaced_zero_cardinality_note,
    normalize_report_headings,
    remove_negative_caveats_from_short_summary,
    remove_report_html_blocks,
)
from query_doctor.report.validation_shape import (
    count_report_section_items,
    validate_recommendations_against_candidates,
    validate_recommendations_section,
    validate_unsupported_conclusions_slot,
)


MIN_REPORT_CHARS = int(os.getenv("QD_MIN_REPORT_CHARS", "900"))
MIN_MARKDOWN_SECTIONS = int(os.getenv("QD_MIN_MARKDOWN_SECTIONS", "8"))


def should_drop_zero_cardinality_positive_claim(line: str, facts_text: str) -> bool:
    return facts_cardinality_anomaly_count(facts_text) == 0 and bool(
        find_zero_cardinality_unsupported_claims(line)
    )


def strip_unsupported_prose(
    line: str,
    current_section: str,
    facts_text: str = "",
    *,
    report_contract: ReportLanguageContract | None = None,
) -> str | None:
    contract = report_contract or get_report_language_contract("ru")
    stripped = line.lstrip()
    is_list_item = stripped.startswith(("-", "*")) or bool(re.match(r"^\d+\.\s+", stripped))
    if should_rewrite_spill_storage_line(line):
        if current_section == contract.next_checks_heading:
            return SPILL_SCRATCH_NEXT_CHECK
        return None
    if current_section in {contract.recommendations_heading, contract.next_checks_heading}:
        return None

    if is_list_item:
        total_sent_match = re.search(
            r"TotalBytesSent\s*[:=]\s*(?P<value>\d[\d.]*\s*(?:KiB|MiB|GiB|TiB|KB|MB|GB|TB|B))",
            line,
            flags=re.IGNORECASE,
        )
        if total_sent_match:
            return f"- TotalBytesSent: {total_sent_match.group('value')} — объем intermediate/exchange данных."
        return None

    sentences = re.split(r"(?<=[.!?])\s+", line)
    kept = [
        sentence
        for sentence in sentences
        if sentence and not has_unsupported_recommendation_topic(sentence, facts_text)
    ]
    result = " ".join(kept).strip()
    return result or None


def sanitize_report_text(report_text: str, facts_text: str, *, language: str = "ru") -> str:
    """Return report text with unsupported recommendations removed.

    Pure helper for tests and callers: no file I/O, no network, no Ollama calls.
    """
    contract = get_report_language_contract(language)
    report_text = normalize_report_headings(report_text, contract.root_cause_heading_rewrite)
    report_text = normalize_report_headings(report_text, contract.detail_heading_rewrite)
    report_text = strip_markdown_section(report_text, contract.analyzer_facts_heading)
    if contract.analyzer_facts_heading != ANALYZER_FACTS_HEADING:
        report_text = strip_markdown_section(report_text, ANALYZER_FACTS_HEADING)
    lines = [line for line in report_text.splitlines() if not line.startswith(PROGRESS_PREFIX)]

    # The wrapper owns the top-level title and fingerprint. Some local models
    # still repeat them; strip a repeated model-produced header block while
    # keeping the wrapper header intact.
    h1_indexes = [i for i, line in enumerate(lines) if line.strip() == "# Query Doctor Report"]
    if len(h1_indexes) > 1:
        duplicate_start = h1_indexes[1]
        next_section = None
        for i in range(duplicate_start + 1, len(lines)):
            if lines[i].startswith("## "):
                next_section = i
                break
        if next_section is not None:
            lines = lines[:duplicate_start] + lines[next_section:]

    normalized: list[str] = []
    current_section = ""
    for line in lines:
        if REPORT_INTERNAL_FINGERPRINT_RE.search(line):
            continue
        if line.startswith("## ") or line.startswith("### "):
            current_section = line.strip()
        if should_rewrite_stats_freshness_claim(line):
            line = stats_freshness_missing_evidence_note(language)
        line = normalize_primary_bottleneck_overclaim(line, language=language)
        line = normalize_cm_context_only_overclaim(line, facts_text, language=language)
        line = normalize_operator_time_wording(line, facts_text, language=language)
        line = normalize_supported_evidence_contradiction(line, facts_text, language=language)
        direction_normalized = normalize_contradicted_estimate_direction(
            line, facts_text, language=language
        )
        if direction_normalized is None:
            continue
        line = direction_normalized
        is_not_supported = current_section == contract.not_supported_heading
        is_structure_line = line.startswith("#") or line.startswith(">") or not line.strip()
        if (
            not is_structure_line
            and not is_not_supported
            and should_drop_zero_cardinality_positive_claim(line, facts_text)
        ):
            line = contract.zero_cardinality_not_supported_bullet
        if (
            not is_structure_line
            and not is_not_supported
            and (
                has_unsupported_recommendation_topic(line, facts_text)
                or should_rewrite_spill_storage_line(line)
            )
        ):
            stripped = strip_unsupported_prose(
                line, current_section, facts_text, report_contract=contract
            )
            if stripped is None:
                continue
            line = stripped
        normalized.append(line)

    return "\n".join(normalized).rstrip() + "\n"


def facts_include_referenced_tables(facts_text: str) -> bool:
    lines = facts_text.splitlines()
    in_section = False
    for line in lines:
        stripped = line.strip()
        if stripped in {"## Referenced Tables", "### Referenced Tables"}:
            in_section = True
            continue
        if in_section and stripped.startswith("#"):
            break
        if (
            in_section
            and stripped.startswith("- ")
            and "missing" not in stripped.lower()
            and "not_observed" not in stripped.lower()
            and "none parsed" not in stripped.lower()
            and "unknown" not in stripped.lower()
        ):
            return True
    return False


def validate_report_against_facts(
    report_text: str, facts_text: str, *, language: str = "ru"
) -> list[str]:
    contract = get_report_language_contract(language)
    errors: list[str] = []
    cardinality_count = facts_cardinality_anomaly_count(facts_text)
    if cardinality_count == 0:
        claims = find_zero_cardinality_unsupported_claims(report_text)
        if claims:
            errors.append(
                "report contains unsupported cardinality/stats/skew claim(s) while "
                f"analyzer facts say Cardinality anomalies: 0: {', '.join(claims)}"
            )
    errors.extend(find_contradicted_row_underestimation_claims(report_text, facts_text))
    errors.extend(find_contradicted_memory_underestimation_claims(report_text, facts_text))
    errors.extend(find_contradicted_memory_overestimation_claims(report_text, facts_text))
    errors.extend(find_unsafe_operator_time_wording(report_text, facts_text))
    errors.extend(find_backend_tail_claim_errors(report_text, facts_text))
    errors.extend(find_spill_scratch_claim_errors(report_text, facts_text))
    errors.extend(find_cluster_event_context_claim_errors(report_text, facts_text))
    errors.extend(find_cm_context_only_claim_errors(report_text, facts_text))
    errors.extend(find_primary_bottleneck_overclaim_errors(report_text))
    errors.extend(find_unsupported_metadata_claim_errors(report_text))
    errors.extend(
        validate_recommendations_against_candidates(
            report_text,
            facts_text,
            recommendations_heading=contract.recommendations_heading,
            language=language,
        )
    )
    errors.extend(
        validate_unsupported_conclusions_slot(
            report_text,
            facts_text,
            short_summary_heading=contract.short_summary_heading,
        )
    )
    return errors


def enforce_report_fact_requirements(text: str, facts_text: str, *, language: str = "ru") -> str:
    contract = get_report_language_contract(language)
    if facts_cardinality_anomaly_count(facts_text) == 0:
        text = insert_bullets_into_section(
            text,
            contract.not_supported_heading,
            [contract.zero_cardinality_not_supported_bullet],
        )
    return text


def enforce_user_report_requirements(text: str, facts_text: str, *, language: str = "ru") -> str:
    contract = get_report_language_contract(language)
    text = normalize_report_headings(text, contract.user_heading_rewrite)
    text = normalize_report_headings(
        text,
        {
            contract.user_read_only_heading: contract.next_checks_heading,
            contract.user_admin_package_heading: contract.next_checks_heading,
            contract.user_validation_heading: contract.recommendations_heading,
            contract.user_verify_heading: contract.next_checks_heading,
        },
    )
    if facts_has_backend_tail_evidence(facts_text):
        backend_bullet = (
            "- Передать платформенной команде backend/host evidence из analyzer facts; host/network/HDFS/RPC path — это проверки, не доказанная причина."
            if language == "ru"
            else "- Send backend/host evidence from analyzer facts to the platform team; host/network/HDFS/RPC path items are checks, not a proven cause."
        )
        text = insert_bullets_into_section(
            text,
            contract.next_checks_heading,
            [backend_bullet],
        )
    return enforce_admin_report_requirements(text, facts_text, language=language)


def enforce_admin_report_requirements(
    text: str, facts_text: str = "", *, language: str = "ru"
) -> str:
    contract = get_report_language_contract(language)

    def localized(ru_text: str, en_text: str) -> str:
        return ru_text if language == "ru" else en_text

    text = normalize_report_headings(text, contract.root_cause_heading_rewrite)
    text = normalize_report_headings(
        text,
        {
            "## Next checks": contract.next_checks_heading,
            "## What to check next": contract.next_checks_heading,
            "## Checks for next run": contract.next_checks_heading,
            "### Next checks": contract.next_checks_heading,
            "### What to check next": contract.next_checks_heading,
            "### Checks for next run": contract.next_checks_heading,
            "## Что проверить следующим запуском": contract.next_checks_heading,
            "## Админские проверки": contract.next_checks_heading,
            "### Админские проверки": contract.next_checks_heading,
        },
    )
    metrics_evidence_bullet = cm_metrics_report_evidence_bullet(facts_text)
    if metrics_evidence_bullet:
        text = insert_bullets_into_section(
            text, contract.evidence_heading, [metrics_evidence_bullet]
        )
    cluster_runtime_bullet = cluster_runtime_context_report_evidence_bullet(facts_text)
    if cluster_runtime_bullet:
        text = insert_bullets_into_section(
            text, contract.evidence_heading, [cluster_runtime_bullet]
        )
    cluster_event_bullet = cluster_event_context_report_evidence_bullet(facts_text)
    if cluster_event_bullet:
        text = insert_bullets_into_section(text, contract.evidence_heading, [cluster_event_bullet])
    evidence_quality_bullet = evidence_quality_report_evidence_bullet(
        facts_text,
        language=language,
    )
    if evidence_quality_bullet:
        text = insert_bullets_into_section(
            text,
            contract.evidence_heading,
            [evidence_quality_bullet],
        )
    admin_bullet_rules: list[tuple[str, tuple[str, ...]]] = []
    if facts_has_backend_tail_evidence(facts_text):
        admin_bullet_rules.extend(
            [
                (
                    localized(
                        "- Проверить per-host RowsProduced для операторов из Action Cards.",
                        "- Check per-host RowsProduced for operators from Action Cards.",
                    ),
                    (r"per-host\s+RowsProduced",),
                ),
                (
                    localized(
                        "- Проверить per-host PeakMemUsage для тех же операторов.",
                        "- Check per-host PeakMemUsage for the same operators.",
                    ),
                    (r"per-host\s+PeakMemUsage",),
                ),
                (
                    localized(
                        "- Проверить CM metrics/logs на host-level resource pressure во время окна запроса.",
                        "- Check CM metrics/logs for host-level resource pressure during the query window.",
                    ),
                    (r"CM\s+metrics/logs|CM\s+metrics|CM\s+logs|host-level\s+resource\s+pressure",),
                ),
            ]
        )
    if facts_have_spill_scratch_evidence(facts_text):
        admin_bullet_rules.append(
            (
                localized(
                    "- Проверить spill/scratch counters в query profile.",
                    "- Check spill/scratch counters in the query profile.",
                ),
                (r"spill/scratch\s+counters|spill.*scratch|scratch.*spill",),
            )
        )
    memory_count = facts_memory_anomaly_count(facts_text)
    if facts_have_admission_or_pool_evidence(facts_text) or (
        memory_count is not None and memory_count > 0
    ):
        admin_bullet_rules.append(
            (
                localized(
                    "- Проверить лимиты памяти admission pool и поведение очереди.",
                    "- Check admission pool memory limits and queue behavior.",
                ),
                (r"admission\s+pool|лимит\w*\s+памят\w+.*очеред",),
            )
        )
    if facts_have_action_cards(facts_text):
        admin_bullet_rules.append(
            (
                localized(
                    "- Проверить profile counters по указанным операторам, прежде чем считать предполагаемые проблемы доказанными причинами.",
                    "- Check profile counters for the listed operators before treating suspected issues as proven causes.",
                ),
                (r"profile\s+counters|сч[её]тчик\w+\s+profile",),
            )
        )
    cm_correlation = cm_metrics_correlation_summary(facts_text)
    if cm_correlation.get("status") == "available":
        admin_bullet_rules.append(
            (
                localized(
                    "- Сопоставить Runtime Metrics Correlation с profile evidence: correlated signals использовать только как runtime context, context-only metrics не считать root cause.",
                    "- Compare Runtime Metrics Correlation with profile evidence: use correlated signals only as runtime context and do not treat context-only metrics as root cause.",
                ),
                (r"correlated\s+signals.*runtime\s+context|context-only\s+metrics.*root\s+cause",),
            )
        )
    if facts_has_backend_tail_evidence(facts_text):
        backend_summary = parse_backend_tail_summary(facts_text)
        if backend_has_proven_tail(backend_summary):
            backend_tail_bullet = localized(
                (
                    "- Приоритизировать Backend / Host Tail Evidence: сравнить per-host runtime/profile time, "
                    "RowsProduced, BytesRead/BytesWritten и rates для tail host и соседних hosts."
                ),
                (
                    "- Prioritize Backend / Host Tail Evidence: compare per-host runtime/profile time, "
                    "RowsProduced, BytesRead/BytesWritten and rates for the tail host and peers."
                ),
            )
            backend_tail_patterns = (
                r"Backend\s*/\s*Host\s+Tail\s+Evidence|execution\s+tail|tail\s+host",
            )
        else:
            backend_tail_bullet = localized(
                (
                    "- Приоритизировать Backend / Host Tail Evidence: сравнить per-host RowsProduced, "
                    "BytesRead/BytesWritten и rates; single tail host не доказан parsed facts."
                ),
                (
                    "- Prioritize Backend / Host Tail Evidence: compare per-host RowsProduced, "
                    "BytesRead/BytesWritten and rates; parsed facts do not prove a single tail host."
                ),
            )
            backend_tail_patterns = (
                r"Backend\s*/\s*Host\s+Tail\s+Evidence|single\s+tail\s+host\s+не\s+доказан",
            )
        admin_bullet_rules = [
            (
                backend_tail_bullet,
                backend_tail_patterns,
            ),
            (
                localized(
                    "- Проверить host-specific write/RPC/HDFS path как гипотезу; это не доказанная причина без внешних host/network/HDFS метрик.",
                    "- Check host-specific write/RPC/HDFS path as a hypothesis; it is not a proven cause without external host/network/HDFS metrics.",
                ),
                (r"write/RPC/HDFS|HDFS/RPC/write|host-specific.*write",),
            ),
        ] + admin_bullet_rules
    return insert_required_bullets_into_section(
        text,
        contract.next_checks_heading,
        admin_bullet_rules,
    )


def normalize_report_file(
    path: Path, *, facts_text: str = "", mode: str = "admin", language: str = "ru"
) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    text = normalize_report_text(text, facts_text=facts_text, mode=mode, language=language)
    path.write_text(text, encoding="utf-8")


def normalize_report_text(
    text: str, *, facts_text: str = "", mode: str = "admin", language: str = "ru"
) -> str:
    contract = get_report_language_contract(language)
    text = sanitize_report_text(text, facts_text, language=language)
    text = normalize_report_headings(text, contract.detail_heading_rewrite)
    text = remove_report_html_blocks(text)
    text = remove_negative_caveats_from_short_summary(
        text, short_summary_heading=contract.short_summary_heading
    )
    text = normalize_practical_recommendations(
        text,
        facts_text,
        recommendations_heading=contract.recommendations_heading,
        next_checks_heading=contract.next_checks_heading,
        language=language,
    )
    text = move_misplaced_admin_bullets_into_admin_section(
        text, next_checks_heading=contract.next_checks_heading
    )
    text = move_misplaced_zero_cardinality_note(
        text,
        not_supported_heading=contract.not_supported_heading,
        zero_cardinality_bullet=contract.zero_cardinality_not_supported_bullet,
    )
    if mode == "user":
        text = enforce_user_report_requirements(text, facts_text, language=language)
    if mode == "admin":
        text = enforce_admin_report_requirements(text, facts_text, language=language)
    text = enforce_report_fact_requirements(text, facts_text, language=language)
    text = normalize_practical_recommendations(
        text,
        facts_text,
        recommendations_heading=contract.recommendations_heading,
        next_checks_heading=contract.next_checks_heading,
        language=language,
    )
    text = move_misplaced_admin_bullets_into_admin_section(
        text, next_checks_heading=contract.next_checks_heading
    )
    text = move_misplaced_zero_cardinality_note(
        text,
        not_supported_heading=contract.not_supported_heading,
        zero_cardinality_bullet=contract.zero_cardinality_not_supported_bullet,
    )
    text = remove_report_html_blocks(text)
    return text


def validate_report_text(
    text: str,
    *,
    facts_text: str = "",
    min_chars: int = MIN_REPORT_CHARS,
    min_sections: int = MIN_MARKDOWN_SECTIONS,
    language: str = "ru",
) -> list[str]:
    contract = get_report_language_contract(language)
    errors: list[str] = []
    stripped = text.strip()
    if len(stripped) < min_chars:
        errors.append(f"report is too short: {len(stripped)} chars, minimum is {min_chars}")

    section_lines = [line.strip() for line in text.splitlines() if line.startswith("#")]
    if len(section_lines) < min_sections:
        errors.append(
            f"report has too few markdown sections: {len(section_lines)}, minimum is {min_sections}"
        )

    for required in contract.required_sections:
        if required not in section_lines:
            errors.append(f"missing required section: {required}")

    if section_lines.count(contract.title_heading) != 1:
        errors.append(
            f"expected exactly one {contract.title_heading!r} heading, found {section_lines.count(contract.title_heading)}"
        )

    short_summary_items = count_report_section_items(text, contract.short_summary_heading)
    if short_summary_items is not None and not 2 <= short_summary_items <= 6:
        errors.append(f"short summary must contain 2-6 concise items, found {short_summary_items}")
    errors.extend(validate_report_html_safety(text))
    errors.extend(validate_report_internal_fingerprints(text))
    errors.extend(validate_report_language_safety(text, language=language))
    errors.extend(
        validate_recommendations_section(
            text, recommendations_heading=contract.recommendations_heading
        )
    )

    if contains_raw_sql_like_text(text):
        errors.append("report contains SQL-like text that is not allowed in trusted output")

    if facts_text:
        errors.extend(validate_report_against_facts(text, facts_text, language=language))

    return errors


def validate_report_safety_text(
    text: str, *, facts_text: str = "", language: str = "ru"
) -> list[str]:
    errors: list[str] = []
    errors.extend(validate_report_html_safety(text))
    errors.extend(validate_report_internal_fingerprints(text))
    errors.extend(validate_report_language_safety(text, language=language))
    if contains_raw_sql_like_text(text):
        errors.append("report contains SQL-like text that is not allowed in trusted output")
    if facts_text:
        errors.extend(validate_report_against_facts(text, facts_text, language=language))
    return errors


def validate_report_for_mode(
    text: str,
    *,
    facts_text: str = "",
    validation_mode: str = "strict",
    language: str = "ru",
) -> list[str]:
    if validation_mode == "off":
        return []
    if validation_mode == "relaxed":
        return validate_report_safety_text(text, facts_text=facts_text, language=language)
    return validate_report_text(text, facts_text=facts_text, language=language)


def validate_report_file(
    output_path: Path, *, facts_text: str = "", language: str = "ru"
) -> list[str]:
    text = output_path.read_text(encoding="utf-8", errors="replace")
    return validate_report_text(text, facts_text=facts_text, language=language)
