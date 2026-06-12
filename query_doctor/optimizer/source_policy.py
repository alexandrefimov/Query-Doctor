"""Source-visibility policy for browser-visible optimizer SQL drafts."""

from __future__ import annotations

from query_doctor.optimizer.models import OptimizerRiskDecision
from query_doctor.source_visibility import (
    SOURCE_VISIBILITY_OWNER_RAW,
    normalize_source_visibility,
)


OPTIMIZER_DRAFT_BLOCKED_BY_SOURCE_VISIBILITY_REASON = "source_visibility_safe_blocks_sql_draft"
OPTIMIZER_DRAFT_BLOCKED_BY_SOURCE_VISIBILITY_FALLBACK = "source_visibility_safe"


def optimizer_sql_draft_display_allowed(source_visibility: object | None) -> bool:
    return normalize_source_visibility(source_visibility) == SOURCE_VISIBILITY_OWNER_RAW


def optimizer_source_visibility_risk_decision(
    risk_decision: OptimizerRiskDecision,
    *,
    source_visibility: object | None,
) -> OptimizerRiskDecision:
    if optimizer_sql_draft_display_allowed(source_visibility):
        return risk_decision
    reasons = list(risk_decision.reasons)
    if OPTIMIZER_DRAFT_BLOCKED_BY_SOURCE_VISIBILITY_REASON not in reasons:
        reasons.append(OPTIMIZER_DRAFT_BLOCKED_BY_SOURCE_VISIBILITY_REASON)
    return OptimizerRiskDecision(mode="recommendations_only", reasons=tuple(reasons))
