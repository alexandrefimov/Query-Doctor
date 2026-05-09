#!/usr/bin/env python3
"""Generate a validated optimized query draft for one Query Doctor case."""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from collections.abc import Iterable
from pathlib import Path

from query_doctor.optimizer.models import (
    CteDefinition,
    CteParseResult,
    OptimizerActionCard,
    OptimizerRiskDecision,
    ProjectionSignature,
)
from query_doctor.optimizer.artifacts import (
    MARKER_NAME,
    MARKER_SCHEMA_VERSION,
    OPTIMIZER_NUM_PREDICT,
    OUTPUT_NAME,
    PARTIAL_NAME,
    RECOMMENDATIONS_NAME,
    VALIDATION_MODE,
    file_sha256,
    llm_generation_metadata,
    remove_stale_trusted_optimizer_outputs,
    text_sha256,
    write_marker,
    write_recommendations_marker,
)
from query_doctor.optimizer.deterministic_rewrites import deterministic_recipe_draft
from query_doctor.optimizer.prompts import build_prompt, build_recommendations_prompt
from query_doctor.optimizer.recommendations import (
    action_card_recommendation_bullet,
    build_optimizer_fact_digest,
    build_sql_shape_digest,
    facts_have_cardinality_or_stats_gap,
    facts_have_finding,
    optimizer_action_cards,
    optimizer_mode_contract,
    optimizer_prompt_rewrite_bullets,
    optimizer_specific_recommendation_bullets,
    optimizer_temperature,
    rewrite_target_for_operator,
)
from query_doctor.optimizer.recipes import (
    build_final_union_distinct_rollup_recipe,
    build_post_union_aggregate_pushdown_recipe,
    detect_optimizer_rewrite_recipe,
)
from query_doctor.optimizer.source_sql import (
    MAX_SOURCE_SQL_BYTES,
    OptimizableSourceSql,
    QueryOptimizationError,
    enforce_text_size,
    extract_ctas_payload_sql,
    extract_optimizable_source_sql,
    extract_top_level_payload_sql,
    extract_with_insert_payload_sql,
    find_top_level_keyword_offset,
    is_sql_identifier_char,
    is_sql_identifier_start,
    read_bounded_text,
    read_source_sql,
    skip_block_comment_text,
    skip_line_comment_text,
    skip_quoted_text,
    trim_source_statement_tokens,
)
from query_doctor.optimizer.sql import (
    OptimizerSqlError,
    collect_cte_names,
    extract_referenced_tables,
    tokenize_sql,
    validate_optimizer_sql_tokens,
)
from query_doctor.optimizer.sql_shape import (
    aggregate_fragment_supported_for_final_distinct_rollup,
    aggregate_input_projection_names,
    aggregate_input_rollup_shape_is_supported,
    aggregate_projection_fragments,
    aggregate_projection_names,
    clean_projection_identifier,
    clause_signature,
    count_distinct_key_names,
    cte_predicate_pushdown_shape_is_candidate,
    cte_definition_map,
    cte_name_signature,
    dedupe_preserve_order,
    draft_has_material_change,
    extract_statement_tokens,
    final_distinct_rollup_aggregate_shape_is_supported,
    find_top_level_token,
    has_union_all,
    identifier_name_referenced,
    identifier_referenced,
    keyword_at,
    keyword_count_any_depth,
    lower_sql_outside_quoted_text,
    main_select_has_distinct,
    matching_parenthesis_offset,
    nested_query_signatures,
    non_aggregate_projection_names,
    normalize_sql_signature_fragment,
    normalized_statement_signature,
    parse_with_query,
    projection_expression_signature,
    projection_item_fragments,
    projection_name_for_fragment,
    post_union_aggregate_input_rollup_names,
    projection_output_name,
    projection_signature,
    read_sql_identifier,
    skip_sql_whitespace_and_comments,
    split_top_level_projection_items,
    split_top_level_sql_fragments,
    split_top_level_union_all_fragments,
    sql_has_keyword,
    table_names,
    top_level_join_condition_signature,
    top_level_join_signature,
    top_level_keyword_count,
    union_projection_names,
    unwrap_sql_fragment_parentheses,
)
from query_doctor.optimizer.validation import (
    all_clause_signatures,
    all_predicate_signatures,
    complete_quoted_text_end,
    counter_is_subset,
    extract_draft_sql,
    extract_recommendations,
    has_non_inner_join_modifier,
    lexical_sql_completeness,
    no_rewrite_recommendations,
    no_supported_rewrite_recommendations,
    normalize_optimizer_recommendations,
    normalized_trusted_draft_sql,
    output_limit_no_rewrite_recommendations,
    parse_between_predicate_signature,
    post_union_unused_detail_projection_names,
    post_union_where_predicates_preserved,
    predicate_join_equalities,
    sql_business_numeric_literal_counter,
    sql_clause_signature_counter,
    sql_completeness_errors,
    sql_predicate_signature_counter,
    sql_string_literal_counter,
    split_top_level_conjunct_fragments,
    token_depths_before,
    transitive_inner_join_where_predicate_counter,
    trim_statement_tokens_for_completeness,
    validate_draft_sql,
    validate_final_union_distinct_rollup_branch_shape,
    validate_final_union_distinct_rollup_rewrite,
    validate_optimizer_recommendations_text,
    validate_post_union_aggregate_branch_shape,
    validate_recipe_backed_cte_rewrite,
    validate_unrelated_cte_bodies_preserved,
    validation_failed_no_rewrite_recommendations,
    where_predicates_preserved_or_safely_extended,
    where_predicates_preserved_or_safely_extended_by_union_branch,
)
from query_doctor.report.facts_extractors import first_bullet_value as first_report_bullet_value
from query_doctor.report.markdown import extract_markdown_section as extract_report_markdown_section
from query_doctor.report.contract_digest import build_report_contract_digest
from query_doctor.report.recommendation_candidates import recommendation_candidate_lines
from query_doctor.report.recommendations import (
    canonical_recommendation_bullets,
    recommendation_candidate_id_for_bullet,
)
from query_doctor.report.llm_client import (
    DEFAULT_KEEP_ALIVE,
    DEFAULT_MODEL,
    DEFAULT_OLLAMA_URL,
    PROGRESS_PREFIX,
    StreamedLLMResponse,
    ollama_chat_url,
    stream_ollama_report_with_meta as _stream_ollama_report_with_meta,
)


UNSAFE_RECOMMENDATION_TOKENS = (
    "```",
    "profile_digest.md",
    "query_metadata.json",
    "cm_metadata.json",
    "analysis_facts.md",
    "diagnosis.md",
    "diagnosis.partial.md",
    "optimized_query.sql",
    "optimized_query.validated.json",
    "optimized_query.partial.txt",
    "ollama",
)
UNSAFE_RECOMMENDATION_SQL_LINE_RE = re.compile(
    r"^\s*(?:[-*]|\d+\.)?\s*"
    r"(?:select|insert|create|drop|alter|refresh|invalidate|compute\s+stats|show|set|use)\b",
    re.IGNORECASE | re.MULTILINE,
)
UNSAFE_RECOMMENDATION_CTE_RE = re.compile(r"\bwith\s+[A-Za-z_][\w$]*\s+as\b", re.IGNORECASE)
MAX_DRAFT_SQL_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_DRAFT_SQL_BYTES", "262144"))
MAX_RECOMMENDATIONS_BYTES = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATIONS_BYTES", "65536"))
SQL_FENCE_RE = re.compile(r"```(?:sql)?\s*(?P<sql>.*?)```", re.IGNORECASE | re.DOTALL)
TOP_LEVEL_SHAPE_KEYWORDS = ("GROUP", "ORDER")
TOP_LEVEL_SET_OPERATORS = ("UNION", "EXCEPT", "INTERSECT")
CLAUSE_SIGNATURE_KEYWORDS = ("WHERE", "GROUP", "HAVING", "ORDER", "LIMIT")
CLAUSE_SIGNATURE_BOUNDARIES = (
    "WHERE",
    "GROUP",
    "HAVING",
    "ORDER",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "QUALIFY",
    "DISTRIBUTE",
    "SORT",
    "CLUSTER",
)
JOIN_MODIFIER_KEYWORDS = {"LEFT", "RIGHT", "FULL", "INNER", "OUTER", "CROSS", "SEMI", "ANTI"}
CONSERVATIVE_CTE_THRESHOLD = int(os.getenv("QD_OPTIMIZER_CONSERVATIVE_CTE_THRESHOLD", "2"))
CONSERVATIVE_JOIN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_CONSERVATIVE_JOIN_THRESHOLD", "6"))
CONSERVATIVE_TOKEN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_CONSERVATIVE_TOKEN_THRESHOLD", "1000"))
RECOMMENDATIONS_ONLY_CTE_THRESHOLD = int(os.getenv("QD_OPTIMIZER_RECOMMENDATIONS_ONLY_CTE_THRESHOLD", "5"))
RECOMMENDATIONS_ONLY_JOIN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_RECOMMENDATIONS_ONLY_JOIN_THRESHOLD", "10"))
RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD = int(os.getenv("QD_OPTIMIZER_RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD", "2000"))
MAX_OPTIMIZER_RECOMMENDATION_ITEMS = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATION_ITEMS", "8"))
INCOMPLETE_TRAILING_TOKENS = {
    ",",
    ".",
    "(",
    "AS",
    "BY",
    "FROM",
    "JOIN",
    "ON",
    "USING",
    "WHERE",
    "AND",
    "OR",
    "GROUP",
    "ORDER",
    "HAVING",
    "LIMIT",
    "UNION",
    "EXCEPT",
    "INTERSECT",
    "WITH",
    "SELECT",
}
INCOMPLETE_TRAILING_CHARS = {",", ".", "(", "+", "-", "*", "/", "=", "<", ">"}


def stream_ollama_report(**kwargs: object) -> StreamedLLMResponse | str:
    return _stream_ollama_report_with_meta(**kwargs)  # type: ignore[arg-type]


def stream_optimizer_response(**kwargs: object) -> StreamedLLMResponse:
    response = stream_ollama_report(**kwargs)
    if isinstance(response, StreamedLLMResponse):
        return response
    return StreamedLLMResponse(text=str(response), done_reason="", eval_count=None, prompt_eval_count=None)



def decide_optimizer_risk_mode(source_sql: str) -> OptimizerRiskDecision:
    tokens = extract_statement_tokens(source_sql)
    recommendations_only_reasons: list[str] = []
    conservative_reasons: list[str] = []
    cte_count = len(collect_cte_names(tokens))
    join_count = len(top_level_join_signature(source_sql))
    token_count = len(tokens)
    set_operator_count = sum(top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS)
    if cte_count:
        conservative_reasons.append("cte_body_validation_not_proven")
    if not cte_count and nested_query_signatures(source_sql):
        conservative_reasons.append("nested_query_body_validation_not_proven")
    if (
        cte_count > RECOMMENDATIONS_ONLY_CTE_THRESHOLD
        and not cte_predicate_pushdown_shape_is_candidate(source_sql)
    ):
        recommendations_only_reasons.append("too_many_ctes_for_safe_rewrite")
    if join_count > RECOMMENDATIONS_ONLY_JOIN_THRESHOLD:
        recommendations_only_reasons.append("too_many_top_level_joins_for_safe_rewrite")
    if token_count > RECOMMENDATIONS_ONLY_TOKEN_THRESHOLD:
        recommendations_only_reasons.append("sql_payload_too_large_for_safe_rewrite")
    if recommendations_only_reasons:
        return OptimizerRiskDecision(
            mode="recommendations_only",
            reasons=tuple(conservative_reasons + recommendations_only_reasons),
        )
    if cte_count > CONSERVATIVE_CTE_THRESHOLD:
        conservative_reasons.append("many_ctes")
    if join_count > CONSERVATIVE_JOIN_THRESHOLD:
        conservative_reasons.append("many_top_level_joins")
    if token_count > CONSERVATIVE_TOKEN_THRESHOLD:
        conservative_reasons.append("long_sql_payload")
    if set_operator_count:
        conservative_reasons.append("set_operations")
    if conservative_reasons:
        return OptimizerRiskDecision(mode="conservative_rewrite", reasons=tuple(conservative_reasons))
    return OptimizerRiskDecision(mode="rewrite_allowed", reasons=())


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a validated optimized query draft for one case.")
    parser.add_argument("case_dir")
    parser.add_argument("--out", default=OUTPUT_NAME)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--ollama-url", default=DEFAULT_OLLAMA_URL)
    parser.add_argument("--temperature", type=float, default=0.1)
    parser.add_argument("--keep-alive", default=DEFAULT_KEEP_ALIVE)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    case_dir = Path(args.case_dir).expanduser().resolve()
    facts_path = case_dir / "analysis_facts.md"
    if not case_dir.is_dir():
        print(f"{PROGRESS_PREFIX} ERROR: case directory is unavailable", file=sys.stderr)
        return 2
    if not facts_path.is_file():
        print(f"{PROGRESS_PREFIX} ERROR: analysis_facts.md is required", file=sys.stderr)
        return 2
    try:
        source_sql = extract_optimizable_source_sql(read_source_sql(case_dir))
        extract_referenced_tables(source_sql.sql)
        facts_text = facts_path.read_text(encoding="utf-8", errors="replace")
        risk_decision = decide_optimizer_risk_mode(source_sql.sql)
        rewrite_recipe = detect_optimizer_rewrite_recipe(source_sql.sql, facts_text)
        print(f"{PROGRESS_PREFIX} optimized query source: available", file=sys.stderr)
        print(f"{PROGRESS_PREFIX} optimized query scope: {source_sql.scope}", file=sys.stderr)
        print(f"{PROGRESS_PREFIX} optimizer risk mode: {risk_decision.mode}", file=sys.stderr)
        deterministic_draft = deterministic_recipe_draft(source_sql.sql, rewrite_recipe)
        if deterministic_draft:
            errors = validate_draft_sql(source_sql.sql, deterministic_draft, rewrite_recipe)
            if not errors and draft_has_material_change(source_sql.sql, deterministic_draft):
                output_name = Path(args.out).name
                if output_name != args.out:
                    raise QueryOptimizationError("Output must be a filename inside the case directory.")
                output_path = case_dir / output_name
                output_path.write_text(normalized_trusted_draft_sql(deterministic_draft), encoding="utf-8")
                write_marker(
                    case_dir,
                    output_name,
                    source_sql=source_sql.sql,
                    facts_text=facts_text,
                    source_scope=source_sql.scope,
                    risk_decision=risk_decision,
                    rewrite_recipe=rewrite_recipe,
                    generation_metadata={
                        "generator": "deterministic_recipe",
                        "prompt_chars": 0,
                        "source_sql_chars": len(source_sql.sql),
                        "generated_chars": len(deterministic_draft),
                    },
                )
                print(f"{PROGRESS_PREFIX} optimizer deterministic recipe draft done", file=sys.stderr)
                return 0
        if risk_decision.mode == "recommendations_only":
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_prompt = build_recommendations_prompt(
                source_sql=source_sql.sql,
                facts_text=facts_text,
                risk_decision=risk_decision,
            )
            print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
            response = stream_optimizer_response(
                prompt=recommendations_prompt,
                model=args.model,
                ollama_url=args.ollama_url,
                temperature=optimizer_temperature(args.temperature, risk_decision),
                keep_alive=args.keep_alive,
                num_predict=OPTIMIZER_NUM_PREDICT,
            )
            generated = response.text
            recommendations = normalize_optimizer_recommendations(generated, facts_text, risk_decision, rewrite_recipe)
            generation_metadata = llm_generation_metadata(
                response,
                prompt=recommendations_prompt,
                source_sql=source_sql.sql,
                generated=generated,
            )
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(recommendations.rstrip() + "\n", encoding="utf-8")
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                generation_metadata=generation_metadata,
            )
            print(f"{PROGRESS_PREFIX} optimizer recommendations done", file=sys.stderr)
            return 0
        if rewrite_recipe is None:
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                no_supported_rewrite_recommendations(risk_decision, facts_text) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=None,
                output_kind="no_rewrite",
                fallback_reason="no_python_owned_recipe",
                generation_metadata={
                    "generator": "deterministic_no_rewrite",
                    "prompt_chars": 0,
                    "source_sql_chars": len(source_sql.sql),
                    "generated_chars": 0,
                },
            )
            print(f"{PROGRESS_PREFIX} optimizer no supported rewrite recipe", file=sys.stderr)
            return 0
        prompt = build_prompt(
            source_sql=source_sql.sql,
            facts_text=facts_text,
            risk_decision=risk_decision,
        )
        print(f"{PROGRESS_PREFIX} ollama: {ollama_chat_url(args.ollama_url)}", file=sys.stderr)
        response = stream_optimizer_response(
            prompt=prompt,
            model=args.model,
            ollama_url=args.ollama_url,
            temperature=optimizer_temperature(args.temperature, risk_decision),
            keep_alive=args.keep_alive,
            num_predict=OPTIMIZER_NUM_PREDICT,
        )
        generated = response.text
        generation_metadata = llm_generation_metadata(response, prompt=prompt, source_sql=source_sql.sql, generated=generated)
        if response.done_reason == "length":
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                output_limit_no_rewrite_recommendations(facts_text, risk_decision, rewrite_recipe) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                output_kind="no_rewrite",
                fallback_reason="output_limit",
                generation_metadata=generation_metadata,
            )
            print(
                f"{PROGRESS_PREFIX} optimizer output budget reached before complete trusted draft",
                file=sys.stderr,
            )
            return 0
        draft_sql = extract_draft_sql(generated)
        errors = validate_draft_sql(source_sql.sql, draft_sql, rewrite_recipe)
        if errors:
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                validation_failed_no_rewrite_recommendations(errors, risk_decision, facts_text, rewrite_recipe) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                output_kind="no_rewrite",
                fallback_reason="validation_failed",
                validation_errors=errors,
                generation_metadata=generation_metadata,
            )
            for error in errors:
                print(f"{PROGRESS_PREFIX} ERROR: {error}", file=sys.stderr)
            print(f"{PROGRESS_PREFIX} optimizer no rewrite recommended after validation failure", file=sys.stderr)
            return 0
        if not draft_has_material_change(source_sql.sql, draft_sql):
            remove_stale_trusted_optimizer_outputs(case_dir, Path(args.out).name)
            recommendations_path = case_dir / RECOMMENDATIONS_NAME
            recommendations_path.write_text(
                no_rewrite_recommendations(risk_decision, facts_text, rewrite_recipe) + "\n",
                encoding="utf-8",
            )
            write_recommendations_marker(
                case_dir,
                RECOMMENDATIONS_NAME,
                source_sql=source_sql.sql,
                facts_text=facts_text,
                source_scope=source_sql.scope,
                risk_decision=risk_decision,
                rewrite_recipe=rewrite_recipe,
                output_kind="no_rewrite",
                fallback_reason="no_material_change",
                generation_metadata=generation_metadata,
            )
            print(f"{PROGRESS_PREFIX} optimizer no rewrite recommended", file=sys.stderr)
            return 0
        output_name = Path(args.out).name
        if output_name != args.out:
            raise QueryOptimizationError("Output must be a filename inside the case directory.")
        output_path = case_dir / output_name
        output_path.write_text(normalized_trusted_draft_sql(draft_sql), encoding="utf-8")
        write_marker(
            case_dir,
            output_name,
            source_sql=source_sql.sql,
            facts_text=facts_text,
            source_scope=source_sql.scope,
            risk_decision=risk_decision,
            rewrite_recipe=rewrite_recipe,
            generation_metadata=generation_metadata,
        )
        print(f"{PROGRESS_PREFIX} optimized query draft done", file=sys.stderr)
        return 0
    except (OSError, OptimizerSqlError, QueryOptimizationError) as exc:
        print(f"{PROGRESS_PREFIX} ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
