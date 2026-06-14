"""Safe metadata collectability helpers for Recent batch cases."""

from __future__ import annotations

from pathlib import Path

from query_doctor.impala.metadata_workflow import (
    DEFAULT_METADATA_MAX_TABLES,
    build_metadata_plan,
    read_default_database_from_facts,
    read_referenced_tables_from_facts,
)
from query_doctor.recent.batch_models import BatchConfig, CaseResult


def collectable_metadata_table_count(config: BatchConfig, case: CaseResult) -> int:
    """Count allowlisted metadata tables without exposing their identifiers."""
    facts_path = _analysis_facts_path(case)
    if facts_path is None:
        return 0
    metadata_max_tables = config.metadata_max_tables or DEFAULT_METADATA_MAX_TABLES
    if metadata_max_tables <= 0:
        return 0
    plan = build_metadata_plan(
        [*case.metadata_source_tables, *read_referenced_tables_from_facts(facts_path)],
        metadata_max_tables,
        default_database=read_default_database_from_facts(facts_path),
    )
    return len(plan.selected_tables)


def update_collectable_metadata_table_count(config: BatchConfig, case: CaseResult) -> int:
    count = collectable_metadata_table_count(config, case)
    case.collectable_metadata_table_count = count
    return count


def _analysis_facts_path(case: CaseResult) -> Path | None:
    if case.actual_case_dir is None:
        return None
    facts_path = case.actual_case_dir / "analysis_facts.md"
    if not facts_path.exists():
        return None
    return facts_path
