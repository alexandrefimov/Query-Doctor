"""Query LLM optimizer validation helpers for web details pages."""

from __future__ import annotations

from pathlib import Path

from query_doctor.web.form_helpers import first_form_value
from query_doctor.optimizer.sql import OptimizerSqlError
from query_doctor.cli.optimize_query import (
    QueryOptimizationError,
    decide_optimizer_risk_mode,
    dedupe_preserve_order,
    detect_optimizer_rewrite_recipe,
    draft_has_material_change,
    extract_optimizable_source_sql,
    optimizer_specific_recommendation_bullets,
    read_source_sql,
    validate_draft_sql,
    validate_optimizer_recommendations_text,
)
from query_doctor.web.trusted_artifacts import load_case_analyzer_facts_text


EXTERNAL_REWRITE_SQL_FIELD = "rewritten_sql"
MAX_EXTERNAL_REWRITE_SQL_BYTES = 256 * 1024


def read_analysis_facts_text(case_dir: Path) -> str:
    facts_text = load_case_analyzer_facts_text(case_dir)
    if facts_text is None:
        raise QueryOptimizationError("Analyzer facts are unavailable for optimizer validation.")
    return facts_text


def optimizer_manual_guidance(
    case_dir: Path | None, *, reason: str = "no_trusted_draft"
) -> str | None:
    if case_dir is None:
        return None
    try:
        facts_text = read_analysis_facts_text(case_dir)
        source = extract_optimizable_source_sql(read_source_sql(case_dir))
        risk_decision = decide_optimizer_risk_mode(source.sql)
        rewrite_recipe = detect_optimizer_rewrite_recipe(source.sql, facts_text)
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        return None
    reason_bullets = {
        "failed": "- No trusted SQL rewrite is shown because optimizer generation did not complete with a validated outcome.",
        "partial_untrusted": "- No trusted SQL rewrite is shown because the generated draft remained untrusted.",
        "not_run": "- No trusted SQL rewrite is shown yet. Use the bullets below as manual rewrite guidance.",
    }
    bullets = [reason_bullets.get(reason, "- No trusted SQL rewrite is shown for this case.")]
    bullets.append(
        "- The bullets below are deterministic manual rewrite guidance from Python-owned analysis facts."
    )
    bullets.extend(
        optimizer_specific_recommendation_bullets(facts_text, risk_decision, rewrite_recipe)
    )
    text = "\n".join(bullets)
    return text if not validate_optimizer_recommendations_text(text) else None


def optimizer_manual_rewrite_allowed(state: dict[str, object]) -> bool:
    status = str(state.get("status") or "")
    if status == "partial_untrusted":
        return True
    if status == "generated" and str(state.get("fallback_reason") or "") == "validation_failed":
        return True
    if (
        status == "failed"
        and "failed deterministic validation" in str(state.get("error") or "").lower()
    ):
        return True
    return False


def validate_external_optimizer_rewrite(
    case_dir: Path | None, form: dict[str, list[str]]
) -> dict[str, object]:
    draft_sql = first_form_value(form, EXTERNAL_REWRITE_SQL_FIELD)
    if not draft_sql:
        return {
            "status": "not_ok",
            "title": "External rewrite validation failed",
            "items": ["Pasted rewrite is empty."],
        }
    if len(draft_sql.encode("utf-8")) > MAX_EXTERNAL_REWRITE_SQL_BYTES:
        return {
            "status": "not_ok",
            "title": "External rewrite validation failed",
            "items": ["Pasted rewrite exceeds the bounded validation limit."],
        }
    if case_dir is None:
        return {
            "status": "unavailable",
            "title": "External rewrite validation unavailable",
            "items": ["Source case is unavailable."],
        }
    try:
        facts_text = read_analysis_facts_text(case_dir)
        source = extract_optimizable_source_sql(read_source_sql(case_dir))
        rewrite_recipe = detect_optimizer_rewrite_recipe(source.sql, facts_text)
        errors = validate_draft_sql(source.sql, draft_sql, rewrite_recipe)
        if not errors and not draft_has_material_change(source.sql, draft_sql):
            errors = ["optimized draft does not materially change source SQL"]
    except (OSError, OptimizerSqlError, QueryOptimizationError):
        return {
            "status": "unavailable",
            "title": "External rewrite validation unavailable",
            "items": ["Source SQL is unavailable or outside optimizer validation scope."],
        }
    if errors:
        return {
            "status": "not_ok",
            "title": "External rewrite validation failed",
            "items": safe_optimizer_validation_categories(errors),
        }
    return {
        "status": "ok",
        "title": "External rewrite validation passed",
        "items": [
            "Read-only SQL scope passed.",
            "Physical table set was preserved.",
            "Filter, join, projection and result-shape checks passed.",
            "Run EXPLAIN comparison and rerun under comparable load before using it.",
        ],
    }


def safe_optimizer_validation_categories(errors: list[str]) -> list[str]:
    categories: list[str] = []
    for error in errors:
        lowered = error.lower()
        if "empty" in lowered:
            categories.append("Pasted rewrite is empty.")
        elif "incomplete" in lowered or "missing its final" in lowered:
            categories.append("Pasted rewrite appears incomplete.")
        elif "outside optimizer scope" in lowered or "final sql safety validation" in lowered:
            categories.append("Pasted rewrite is outside read-only optimizer scope.")
        elif "adds physical tables" in lowered or "physical table set changed" in lowered:
            categories.append("Physical table set changed.")
        elif "removes source where" in lowered or "where predicates changed" in lowered:
            categories.append("Source filter scope changed.")
        elif "removes source having" in lowered:
            categories.append("Source HAVING scope changed.")
        elif "removes source limit" in lowered:
            categories.append("Source LIMIT scope changed.")
        elif "distinct" in lowered:
            categories.append("DISTINCT output shape changed.")
        elif "join on" in lowered or "join predicates changed" in lowered:
            categories.append("JOIN conditions changed.")
        elif "join shape" in lowered:
            categories.append("JOIN shape changed.")
        elif "cte" in lowered:
            categories.append("CTE shape or body changed outside a supported recipe.")
        elif "top-level where expression" in lowered:
            categories.append("Top-level WHERE expression changed.")
        elif "top-level having expression" in lowered:
            categories.append("Top-level HAVING expression changed.")
        elif "top-level group" in lowered:
            categories.append("Top-level GROUP BY shape changed.")
        elif "top-level order" in lowered:
            categories.append("Top-level ORDER BY shape changed.")
        elif "projection" in lowered:
            categories.append("Output projection changed.")
        elif "materially change" in lowered:
            categories.append("Rewrite does not materially change the source query.")
        else:
            categories.append("Deterministic validator rejected the rewrite.")
    return dedupe_preserve_order(categories)[:8]
