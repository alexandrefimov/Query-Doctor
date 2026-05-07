"""Python-owned recommendation context for Query Optimizer prompts."""

from __future__ import annotations

import os
import re

from query_doctor.cli.report import (
    build_report_contract_digest,
    canonical_recommendation_bullets,
    extract_markdown_section as extract_report_markdown_section,
    first_bullet_value as first_report_bullet_value,
    recommendation_candidate_lines,
)
from query_doctor.optimizer.models import OptimizerActionCard, OptimizerRewriteRecipe, OptimizerRiskDecision
from query_doctor.optimizer.sql import collect_cte_names
from query_doctor.optimizer.sql_shape import (
    dedupe_preserve_order,
    extract_statement_tokens,
    top_level_join_signature,
    top_level_keyword_count,
)


TOP_LEVEL_SET_OPERATORS = ("UNION", "EXCEPT", "INTERSECT")
MAX_OPTIMIZER_RECOMMENDATION_ITEMS = int(os.getenv("QD_OPTIMIZER_MAX_RECOMMENDATION_ITEMS", "8"))


def optimizer_mode_contract(
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> str:
    if risk_decision.mode == "recommendations_only":
        reasons = ", ".join(risk_decision.reasons) or "rewrite_too_risky"
        return "\n".join(
            [
                "mode: recommendations_only",
                f"python_owned_reasons: {reasons}",
                "rules:",
                "- Do not produce a SQL draft.",
                "- Return concise practical optimization recommendations only.",
            ]
        )
    if risk_decision.mode == "conservative_rewrite":
        reasons = ", ".join(risk_decision.reasons) or "risk_noted"
        if rewrite_recipe:
            return "\n".join(
                [
                    "mode: conservative_rewrite",
                    f"python_owned_reasons: {reasons}",
                    f"python_owned_rewrite_recipe: {rewrite_recipe.recipe_id}",
                    "rules:",
                    "- A bounded structural rewrite is allowed only when it follows PYTHON-OWNED MANUAL REWRITE BULLETS.",
                    "- Preserve the CTE list exactly: do not add, remove, rename, reorder, inline, or split CTEs.",
                    "- You may change CTE bodies only for the named rewrite recipe.",
                    "- Preserve every physical table, JOIN predicate, WHERE filter, literal mapping, final output column, and final SELECT/window expression.",
                    "- If the recipe cannot be applied exactly, return the original query with harmless formatting.",
                ]
            )
        return "\n".join(
            [
                "mode: conservative_rewrite",
                f"python_owned_reasons: {reasons}",
                "rules:",
                "- Do not perform a structural rewrite.",
                "- Preserve the CTE list exactly: do not add, remove, rename, reorder, inline, or split CTEs.",
                "- Preserve top-level JOIN structure exactly: do not add, remove, reorder, or change JOIN types.",
                "- Preserve projection count, projection names, WHERE, HAVING, GROUP BY, ORDER BY, LIMIT, and set operations.",
                "- Return the original query with harmless formatting if any improvement would require structural changes.",
                "- Allowed changes are whitespace, indentation, and clearly equivalent parenthesization only.",
            ]
        )
    return "\n".join(
        [
            "mode: rewrite_allowed",
            "rules:",
            "- A bounded rewrite is allowed when directly supported by Python-owned facts.",
            "- Preserve result shape, filter scope, table set, CTE shape, and JOIN shape.",
        ]
    )


def optimizer_temperature(requested_temperature: float, risk_decision: OptimizerRiskDecision) -> float:
    if risk_decision.mode in {"conservative_rewrite", "recommendations_only"}:
        return 0.0
    return requested_temperature


def optimizer_prompt_rewrite_bullets(
    facts_text: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None,
) -> list[str]:
    bullets: list[str] = []
    if rewrite_recipe:
        bullets.extend(rewrite_recipe.prompt_bullets)
        return dedupe_preserve_order(bullets)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS + 4]
    bullets.extend(bullet.lstrip("- ").strip() for bullet in optimizer_specific_recommendation_bullets(facts_text, risk_decision))
    return dedupe_preserve_order(bullets)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS + 4]


def build_optimizer_fact_digest(
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> dict[str, object]:
    digest = build_report_contract_digest(facts_text)
    result = {
        "summary": digest.get("summary", {}),
        "evidence_flags": digest.get("evidence_flags", {}),
        "cm_metrics_correlation": digest.get("cm_metrics_correlation", {}),
        "recommendation_candidates": digest.get("recommendation_candidates", []),
        "specific_recommendation_context": optimizer_specific_recommendation_bullets(
            facts_text,
            risk_decision,
            rewrite_recipe,
        ),
        "action_card_titles": digest.get("action_card_titles", []),
        "finding_titles": digest.get("finding_titles", []),
    }
    if rewrite_recipe:
        result["rewrite_recipe"] = {
            "id": rewrite_recipe.recipe_id,
            "title": rewrite_recipe.title,
            "source_cte": rewrite_recipe.source_cte,
            "aggregate_cte": rewrite_recipe.aggregate_cte,
        }
    return result


def build_sql_shape_digest(
    source_sql: str,
    risk_decision: OptimizerRiskDecision,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> dict[str, object]:
    tokens = extract_statement_tokens(source_sql)
    result = {
        "cte_count": len(collect_cte_names(tokens)),
        "top_level_join_count": len(top_level_join_signature(source_sql)),
        "set_operator_count": sum(top_level_keyword_count(source_sql, operator) for operator in TOP_LEVEL_SET_OPERATORS),
        "statement_token_count": len(tokens),
        "risk_mode": risk_decision.mode,
        "risk_reasons": list(risk_decision.reasons),
    }
    if rewrite_recipe:
        result["rewrite_recipe_id"] = rewrite_recipe.recipe_id
    return result


def optimizer_action_cards(facts_text: str, *, limit: int = 3) -> list[OptimizerActionCard]:
    lines = extract_report_markdown_section(facts_text, "## Action Cards")
    cards: list[OptimizerActionCard] = []
    current_title = ""
    current_evidence: dict[str, str] = {}
    in_evidence = False

    def flush() -> None:
        nonlocal current_title, current_evidence, in_evidence
        operator = current_evidence.get("operator", "")
        if current_title and operator and len(cards) < limit:
            cards.append(OptimizerActionCard(title=current_title, operator=operator, evidence=dict(current_evidence)))
        current_title = ""
        current_evidence = {}
        in_evidence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### Card "):
            flush()
            current_title = stripped[4:].strip()
            continue
        if not current_title:
            continue
        if stripped == "Evidence:":
            in_evidence = True
            continue
        if stripped.endswith(":") and stripped != "Evidence:":
            in_evidence = False
            continue
        if not in_evidence:
            continue
        match = re.match(r"^-\s*(?P<label>[A-Za-z/ ]+):\s*(?P<value>.+?)\s*$", stripped)
        if match:
            current_evidence[match.group("label").strip().lower()] = match.group("value").strip()
    flush()
    return cards


def optimizer_specific_recommendation_bullets(
    facts_text: str,
    risk_decision: OptimizerRiskDecision | None = None,
    rewrite_recipe: OptimizerRewriteRecipe | None = None,
) -> list[str]:
    cards = optimizer_action_cards(facts_text)
    bullets: list[str] = []
    if rewrite_recipe:
        bullets.extend(rewrite_recipe.safe_bullets)
    for card in cards[:2]:
        bullets.append(action_card_recommendation_bullet(card))
    if risk_decision and "cte_body_validation_not_proven" in risk_decision.reasons:
        bullets.append(
            "- Для CTE-запроса SQL draft будет принят только если строгая проверка не увидит изменения CTE body: "
            "безопасный ручной путь - менять один CTE за раз, не переименовывать CTE, не менять JOIN keys/filter scope "
            "и проверять совпадение выходных колонок после каждого шага."
        )
    if any("EXCHANGE" in card.operator.upper() for card in cards) or facts_have_finding(facts_text, "Large intermediate or exchange traffic"):
        bullets.append(
            "- Сначала сокращать rows/payload до EXCHANGE или другого data movement: переносить безопасную фильтрацию, "
            "предварительную агрегацию или отсечение лишних промежуточных колонок раньше, сохраняя итоговые колонки и filter scope."
        )
    if any(keyword in card.operator.upper() for card in cards for keyword in ("JOIN", "NESTED LOOP")):
        bullets.append(
            "- Для JOIN-участков проверить many-to-many amplification и входные cardinality до дорогого оператора; "
            "join keys и join type не менять без отдельной проверки плана и результата."
        )
    if facts_have_cardinality_or_stats_gap(facts_text):
        bullets.append(
            "- Перед ручным rewrite проверить и при необходимости обновить table/column stats по затронутым таблицам и join/filter колонкам; "
            "после этого сравнить новый профиль, потому что часть cardinality mismatch может уйти без изменения SQL shape."
        )
    if not bullets:
        bullets.extend(canonical_recommendation_bullets(recommendation_candidate_lines(facts_text))[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS])
    return dedupe_preserve_order(bullets)[:MAX_OPTIMIZER_RECOMMENDATION_ITEMS]


def action_card_recommendation_bullet(card: OptimizerActionCard) -> str:
    details: list[str] = []
    actual_rows = card.evidence.get("actual rows")
    estimated_rows = card.evidence.get("estimated rows")
    rows_ratio = card.evidence.get("actual/estimated ratio")
    peak_memory = card.evidence.get("peak memory")
    memory_ratio = card.evidence.get("peak/estimated memory ratio")
    if actual_rows and estimated_rows:
        ratio_text = f", ratio {rows_ratio}" if rows_ratio else ""
        details.append(f"rows: фактически {actual_rows} vs оценка {estimated_rows}{ratio_text}")
    if peak_memory:
        memory_text = f", ratio {memory_ratio}" if memory_ratio else ""
        details.append(f"memory: peak {peak_memory}{memory_text}")
    evidence = f" ({'; '.join(details)})" if details else ""
    target = rewrite_target_for_operator(card.operator)
    return (
        f"- Начать с {card.title} на операторе {card.operator}{evidence}: {target}. "
        "Не менять результат запроса; проверять тот же набор выходных колонок, тот же filter scope и тот же table set."
    )


def rewrite_target_for_operator(operator: str) -> str:
    upper = operator.upper()
    if "EXCHANGE" in upper:
        return "цель ручной правки - уменьшить rows/payload до перераспределения данных"
    if "JOIN" in upper:
        return "цель ручной правки - уменьшить входы JOIN через раннюю фильтрацию или предварительную агрегацию без смены join keys"
    if "SORT" in upper:
        return "цель ручной правки - уменьшить количество строк или ширину строк до SORT"
    if "AGGREGATE" in upper:
        return "цель ручной правки - уменьшить входные rows до AGGREGATE или проверить возможность более ранней агрегации"
    if "ANALYTIC" in upper:
        return "цель ручной правки - уменьшить входные rows/columns до ANALYTIC"
    return "цель ручной правки - уменьшить входные rows или intermediate payload до этого оператора"


def facts_have_finding(facts_text: str, title_fragment: str) -> bool:
    return title_fragment.lower() in "\n".join(extract_report_markdown_section(facts_text, "## Findings")).lower()


def facts_have_cardinality_or_stats_gap(facts_text: str) -> bool:
    summary_lines = extract_report_markdown_section(facts_text, "## Summary")
    for label in ("Cardinality anomalies", "Zero/unknown row estimate gaps"):
        value = first_report_bullet_value(summary_lines, label)
        if value and value.strip().split(maxsplit=1)[0] not in {"0", "0/0"}:
            return True
    lowered = facts_text.lower()
    return "missing/incomplete stats" in lowered or "table metadata facts: partial" in lowered
