#!/usr/bin/env python3
"""
Query Doctor report writer.

This script reads only deterministic analysis facts and asks a local Ollama
model to turn those facts into a human-readable markdown report. It never reads
profile_digest.md, profile.txt, or other raw profile files.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

# Compatibility monkeypatch seam; llm_client uses the same urllib module object.
import urllib.request
from pathlib import Path
from typing import Any

from query_doctor.impala.metadata_digest import build_metadata_facts_digest
from query_doctor.report.contract import (
    AMPLIFIERS_HEADING,
    ANALYZER_FACTS_HEADING,
    CM_METRICS_CORRELATION_HEADING,
    CM_METRICS_FACTS_HEADING,
    CM_TIMESERIES_CONTEXT_HEADING,
    DETAILED_REPORT_HEADING,
    DETAIL_HEADING_REWRITE,
    EVIDENCE_HEADING,
    EVIDENCE_SAFE_PROBLEMS_HEADING,
    NEXT_CHECKS_HEADING,
    NOT_SUPPORTED_HEADING,
    RECOMMENDATIONS_HEADING,
    REPORT_SYSTEM_PROMPT,
    REPORT_TITLE_HEADING,
    REQUIRED_REPORT_SECTIONS,
    ROOT_CAUSE_HEADING_REWRITE,
    SHORT_SUMMARY_HEADING,
    TABLE_METADATA_CONTEXT_HEADING,
    USER_ADMIN_PACKAGE_HEADING,
    USER_HEADING_REWRITE,
    USER_READ_ONLY_HEADING,
    USER_VALIDATION_HEADING,
    USER_VERIFY_HEADING,
)
from query_doctor.report.markdown import (
    extract_markdown_section,
    extract_markdown_subsection,
    strip_markdown_section,
)
from query_doctor.report.claim_validation import (
    find_unsupported_metadata_claim_errors,
    find_zero_cardinality_unsupported_claims,
    has_unnegated_metadata_claim,
    is_negated_metadata_claim,
)
from query_doctor.report.estimate_validation import (
    find_contradicted_memory_overestimation_claims,
    find_contradicted_memory_underestimation_claims,
    find_contradicted_row_underestimation_claims,
    line_contains_memory_ratio_above_one,
    line_contains_memory_ratio_below_one,
    line_has_memory_overestimation_claim,
    line_has_memory_underestimation_claim,
    line_has_row_underestimation_claim,
    mentions_contradicted_memory_overestimated_operator,
    mentions_contradicted_memory_underestimated_operator,
    mentions_contradicted_row_underestimated_operator,
    normalize_contradicted_estimate_direction,
    starts_new_top_level_item,
)
from query_doctor.report.report_files import (
    move_failed_report_to_partial,
    partial_report_path,
    read_required_facts,
    report_header,
    resolve_case_file,
    write_failed_report_to_partial,
)
from query_doctor.report.safety_validation import (
    REPORT_INTERNAL_FINGERPRINT_RE,
    contains_raw_sql_like_text,
    validate_report_html_safety,
    validate_report_internal_fingerprints,
)
from query_doctor.report.runtime_claim_validation import (
    SPILL_SCRATCH_NEXT_CHECK,
    STATS_FRESHNESS_MISSING_EVIDENCE,
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
)
from query_doctor.report.text_postprocess import (
    ZERO_CARDINALITY_NOT_SUPPORTED_BULLET,
    move_misplaced_admin_bullets_into_admin_section,
    move_misplaced_zero_cardinality_note,
    normalize_report_headings,
    remove_negative_caveats_from_short_summary,
    remove_report_html_blocks,
)
from query_doctor.report.validation_shape import (
    count_report_section_items,
    extract_report_section_lines,
    validate_recommendations_against_candidates,
    validate_recommendations_section,
    validate_unsupported_conclusions_slot,
)
from query_doctor.report.facts_appendix import (
    append_analyzer_facts_appendix,
    append_fact_bullet,
    first_bullet_value,
    limited_nonempty_lines,
    render_analyzer_facts_appendix,
)
from query_doctor.report.facts_extractors import (
    backend_has_proven_tail,
    backend_summary_value,
    cluster_event_context_points,
    cluster_event_context_report_evidence_bullet,
    cluster_event_context_summary,
    cm_metrics_correlation_points,
    cm_metrics_correlation_status,
    cm_metrics_correlation_summary,
    cm_metrics_facts_summary,
    cm_metrics_observed_points,
    cm_metrics_profile_supported,
    cm_metrics_report_evidence_bullet,
    cm_metrics_signal_observed,
    facts_cardinality_anomaly_count,
    facts_has_backend_tail_evidence,
    facts_have_action_cards,
    facts_have_cluster_event_context,
    facts_have_large_intermediate_or_exchange,
    facts_have_metadata_stats_gap,
    facts_have_spill_scratch_evidence,
    facts_memory_anomaly_count,
    facts_summary_count,
    facts_text_for_model_prompt,
    parse_backend_tail_summary,
    parse_ratio_value,
)
from query_doctor.report.language_contract import (
    SUPPORTED_REPORT_LANGUAGES,
    get_report_language_contract,
)
from query_doctor.report.contract_digest import (
    action_card_differentiators,
    build_report_contract_digest,
    case_summary_differentiators,
    evidence_groups,
    format_report_contract_digest,
    markdown_bullet_lines,
    markdown_subheading_titles,
    supported_summary_points,
)
from query_doctor.report.prompt_contract import (
    build_backend_tail_contract,
    build_cardinality_contract,
    build_mode_instruction,
    build_prompt,
)
from query_doctor.report.recommendation_candidates import (
    format_recommendation_candidates,
    recommendation_candidate_lines,
)
from query_doctor.report.recommendations import (
    ADMIN_ONLY_RECOMMENDATION_RE,
    GENERIC_OPTIMIZE_RE,
    MAX_RECOMMENDATION_ITEMS,
    VAGUE_RECOMMENDATION_RE,
    canonical_recommendation_bullets,
    has_unsupported_recommendation_topic,
    insert_bullets_into_section,
    insert_required_bullets_into_section,
    normalize_practical_recommendations,
    recommendation_bullet_body,
    recommendation_candidate_id_for_bullet,
)
from query_doctor.report.llm_client import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    NUM_CTX,
    NUM_PREDICT,
    PROGRESS_PREFIX,
    StreamedLLMResponse,
    ollama_api_url,
    ollama_base_url,
    ollama_chat_url,
    parse_ollama_ps_models,
    stop_other_ollama_models,
    stream_ollama_report,
    stream_ollama_report_with_meta,
)
from query_doctor.report.trusted_text import (
    MIN_MARKDOWN_SECTIONS,
    MIN_REPORT_CHARS,
    enforce_admin_report_requirements,
    enforce_report_fact_requirements,
    enforce_user_report_requirements,
    facts_include_referenced_tables,
    normalize_report_file,
    normalize_report_text,
    sanitize_report_text,
    should_drop_zero_cardinality_positive_claim,
    strip_unsupported_prose,
    validate_report_against_facts,
    validate_report_file,
    validate_report_for_mode,
    validate_report_safety_text,
    validate_report_text,
)


DEFAULT_VALIDATION_MODE = os.getenv("QD_REPORT_VALIDATION_MODE", "strict")
FACT_APPENDIX_MAX_ITEMS = 8


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write a Query Doctor markdown report from deterministic analysis facts only."
    )
    parser.add_argument("case_dir", help="Case directory containing analysis_facts.md")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument(
        "--mode",
        choices=("admin", "user"),
        default="admin",
        help="Report audience mode. Default: %(default)s",
    )
    parser.add_argument(
        "--facts",
        default="analysis_facts.md",
        help="Facts file path, relative to CASE_DIR by default",
    )
    parser.add_argument(
        "--out",
        default="diagnosis_report.md",
        help="Output report path. Relative paths are resolved under CASE_DIR; absolute paths are used as-is. Default: %(default)s",
    )
    parser.add_argument(
        "--language",
        choices=SUPPORTED_REPORT_LANGUAGES,
        default="en",
        help="Report language. Default: %(default)s",
    )
    parser.add_argument(
        "--dry-prompt",
        action="store_true",
        help="Print the final prompt and exit without calling Ollama",
    )
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument(
        "--keep-alive",
        default=DEFAULT_KEEP_ALIVE,
        help="Ollama keep_alive value for the report model. Use 0 to unload after generation. Default: %(default)s",
    )
    parser.add_argument(
        "--stop-other-models",
        action="store_true",
        help="Before generation, unload other currently loaded Ollama models with `ollama ps` and `ollama stop MODEL`.",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Debug only: skip all post-generation report validation, including safety checks.",
    )
    parser.add_argument(
        "--validation-mode",
        choices=("strict", "relaxed", "off"),
        default=DEFAULT_VALIDATION_MODE,
        help=(
            "Report validation mode. strict enforces full report contract; relaxed keeps browser safety and "
            "fact-consistency checks but ignores report shape; off skips validation. Default: %(default)s"
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    report_contract = get_report_language_contract(args.language)
    validation_mode = "off" if args.no_validate else args.validation_mode

    case_dir = Path(args.case_dir).expanduser().resolve()
    if not case_dir.exists() or not case_dir.is_dir():
        print(f"ERROR: case directory not found: {case_dir}", file=sys.stderr)
        return 2

    facts_path = resolve_case_file(case_dir, args.facts).resolve()
    output_path = resolve_case_file(case_dir, args.out).resolve()

    try:
        facts_text, facts_sha256 = read_required_facts(facts_path)
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    prompt = build_prompt(
        facts_text=facts_text,
        facts_path=facts_path,
        facts_sha256=facts_sha256,
        model=args.model,
        language=args.language,
        mode=args.mode,
    )

    if args.dry_prompt:
        print(prompt)
        return 0

    print(f"{PROGRESS_PREFIX} case: {case_dir}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts: {facts_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} facts sha256: {facts_sha256}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} model: {args.model}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} mode: {args.mode}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} validation mode: {validation_mode}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} resolved output path: {output_path}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
    print(f"{PROGRESS_PREFIX} keep_alive: {args.keep_alive}", file=sys.stderr)

    if args.stop_other_models:
        stopped = stop_other_ollama_models(
            target_model=args.model,
        )
        if stopped:
            print(f"{PROGRESS_PREFIX} stopped other models: {', '.join(stopped)}", file=sys.stderr)
        else:
            print(f"{PROGRESS_PREFIX} no other loaded models to stop", file=sys.stderr)

    output_path.parent.mkdir(parents=True, exist_ok=True)

    generated_body = stream_ollama_report(
        prompt=prompt,
        model=args.model,
        ollama_url=args.ollama_url,
        temperature=args.temperature,
        keep_alive=args.keep_alive,
        system_prompt=report_contract.system_prompt,
    )

    narrative_text = normalize_report_text(
        report_header(facts_path, facts_sha256, args.model) + generated_body,
        facts_text=facts_text,
        mode=args.mode,
        language=args.language,
    )

    if validation_mode != "off":
        validation_errors = validate_report_for_mode(
            narrative_text,
            facts_text=facts_text,
            validation_mode=validation_mode,
            language=args.language,
        )
        if validation_errors:
            partial_path = write_failed_report_to_partial(output_path, narrative_text)
            print(f"{PROGRESS_PREFIX} ERROR: generated report failed validation", file=sys.stderr)
            for error in validation_errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} partial report saved to: {partial_path}", file=sys.stderr)
            return 4

    final_report_text = append_analyzer_facts_appendix(
        narrative_text, facts_text, language=args.language
    )

    if validation_mode != "off":
        validation_errors = validate_report_for_mode(
            final_report_text,
            facts_text=facts_text,
            validation_mode=validation_mode,
            language=args.language,
        )
        if validation_errors:
            partial_path = write_failed_report_to_partial(output_path, final_report_text)
            print(f"{PROGRESS_PREFIX} ERROR: final report failed validation", file=sys.stderr)
            for error in validation_errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} partial report saved to: {partial_path}", file=sys.stderr)
            return 4

    output_path.write_text(final_report_text, encoding="utf-8")

    print(f"{PROGRESS_PREFIX} done: {output_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
