"""LLM prompt assembly for Query Optimizer."""

from __future__ import annotations

import json

from query_doctor.optimizer.models import OptimizerRiskDecision
from query_doctor.optimizer.recipes import detect_optimizer_rewrite_recipe
from query_doctor.optimizer.recommendations import (
    build_optimizer_fact_digest,
    build_sql_shape_digest,
    optimizer_mode_contract,
    optimizer_prompt_rewrite_bullets,
)
from query_doctor.report.recommendation_candidates import recommendation_candidate_lines


def build_prompt(*, source_sql: str, facts_text: str, risk_decision: OptimizerRiskDecision) -> str:
    rewrite_recipe = detect_optimizer_rewrite_recipe(source_sql, facts_text)
    manual_bullets = optimizer_prompt_rewrite_bullets(facts_text, risk_decision, rewrite_recipe)
    mode_contract = optimizer_mode_contract(risk_decision, rewrite_recipe)
    if rewrite_recipe:
        manual_bullet_lines = "\n".join(f"- {bullet}" for bullet in manual_bullets)
        return f"""
You are an Apache Impala SQL optimizer.
Rewrite the SQL query exactly according to the Python-owned rewrite recipe.
Return only one complete SQL query. No markdown, no comments, no explanation.

Safety and scope:
- Output must be exactly one read-only SELECT or WITH statement.
- Do not output INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or multiple statements.
- Do not add physical tables that are absent from the input SQL.
- Preserve query semantics, final output columns, original filters, JOIN predicates, literal mappings, date ranges, and final window expressions.
- If the recipe cannot be applied exactly, return the original query with harmless formatting.

PYTHON-OWNED OPTIMIZER MODE BEGIN
{mode_contract}
PYTHON-OWNED OPTIMIZER MODE END

PYTHON-OWNED REWRITE RECIPE BEGIN
{manual_bullet_lines}
PYTHON-OWNED REWRITE RECIPE END

INPUT SQL BEGIN
{source_sql}
INPUT SQL END
""".strip()
    mode_contract = optimizer_mode_contract(risk_decision, rewrite_recipe)
    return f"""
You are a SQL rewrite assistant for Apache Impala.
Return only one complete SQL query. No markdown, no comments, no explanation.

Safety and scope:
- Output must be exactly one read-only SELECT or WITH statement.
- If the input came from INSERT or CTAS, optimize only the SELECT/WITH payload shown below.
- Do not output INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or multiple statements.
- Do not add physical tables that are absent from the input SQL.
- Preserve output columns, table set, JOIN predicates, WHERE/HAVING/GROUP/ORDER/LIMIT scope, literals, and final window expressions.
- Do not invent table names, column names, join keys, filters, partitions, or business rules.
- Runtime, metrics, and triage context are not SQL rewrite targets.
- If no safe rewrite is directly obvious within these constraints, return the original query with harmless formatting.

PYTHON-OWNED OPTIMIZER MODE BEGIN
{mode_contract}
PYTHON-OWNED OPTIMIZER MODE END

INPUT SQL BEGIN
{source_sql}
INPUT SQL END
""".strip()


def build_recommendations_prompt(*, source_sql: str, facts_text: str, risk_decision: OptimizerRiskDecision) -> str:
    candidates = recommendation_candidate_lines(facts_text, language="en")
    rewrite_recipe = detect_optimizer_rewrite_recipe(source_sql, facts_text)
    manual_bullets = optimizer_prompt_rewrite_bullets(facts_text, risk_decision, rewrite_recipe)
    digest = build_optimizer_fact_digest(facts_text, risk_decision, rewrite_recipe)
    shape_digest = build_sql_shape_digest(source_sql, risk_decision, rewrite_recipe)
    candidate_lines = "\n".join(f"- {candidate_id}: {text}" for candidate_id, text in candidates)
    manual_bullet_lines = "\n".join(f"- {bullet}" for bullet in manual_bullets)
    reasons = ", ".join(risk_decision.reasons) or "rewrite_too_risky"
    return f"""
You are a concise Apache Impala query optimization advisor.
Return only practical recommendations in Markdown. Do not return SQL.

Safety and scope:
- Python decided SQL rewrite is too risky for this case.
- Do not output SELECT, WITH, INSERT, CREATE, DROP, ALTER, REFRESH, INVALIDATE, COMPUTE STATS, SHOW, SET, USE, or code blocks.
- Do not echo source SQL, local paths, raw profile text, raw metadata, artifacts, credentials, or runtime internals.
- Use only Python-owned recommendation candidates and deterministic facts.
- Every trusted bullet must map to PYTHON-OWNED RECOMMENDATION CANDIDATES or specific Action Card context; unsupported bullets will be discarded.
- Prefer concrete Action Card operator IDs and safe plan-level advice from the optimizer fact digest.
- Use Runtime Metrics Correlation only when status is correlated; context_only or observed-only metrics must not drive recommendations.
- Use Cluster Runtime Context only to frame runtime evidence and scoring; context-only signals must remain follow-up checks, not rewrite targets.
- Do not invent table names, column names, join keys, filters, partitions, or business rules.
- Prefer concrete actions such as collecting stats, reducing projected columns, narrowing filters, splitting a risky query, or reviewing join shape only when supported by facts.
- Keep the answer under 8 bullets.

PYTHON-OWNED OPTIMIZER MODE BEGIN
mode: recommendations_only
python_owned_reasons: {reasons}
PYTHON-OWNED OPTIMIZER MODE END

PYTHON-OWNED RECOMMENDATION CANDIDATES BEGIN
{candidate_lines}
PYTHON-OWNED RECOMMENDATION CANDIDATES END

PYTHON-OWNED MANUAL REWRITE BULLETS BEGIN
{manual_bullet_lines}
PYTHON-OWNED MANUAL REWRITE BULLETS END

PYTHON-OWNED SQL SHAPE DIGEST BEGIN
{json.dumps(shape_digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED SQL SHAPE DIGEST END

PYTHON-OWNED OPTIMIZER FACT DIGEST BEGIN
{json.dumps(digest, ensure_ascii=False, indent=2, sort_keys=True)}
PYTHON-OWNED OPTIMIZER FACT DIGEST END
""".strip()
