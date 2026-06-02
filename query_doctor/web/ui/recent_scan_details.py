"""Recent query scan case detail and metadata fact rendering helpers."""

from __future__ import annotations

import html
from typing import Any

from query_doctor.web.presenters.recent_scan import (
    RecentScanCaseDetailView,
    RecentScanScoreReasonView,
    RecentScanScoreReasonsView,
    RecentScanStatusCardView,
    RecentScanStatusSummaryView,
    RecentScanTechnicalDetailsView,
    present_recent_scan_score_reasons,
    present_recent_scan_status_summary,
    present_recent_scan_technical_details,
    present_report_action,
)
from query_doctor.web.presenters.recent_scan_diagnostic_facts import (
    diagnostic_fact_by_id,
    verdict_chip_facts,
    verdict_kpi_facts,
)
from query_doctor.web.presenters.recent_scan_diagnostic_questions import (
    present_recent_scan_diagnostic_questions,
)
from query_doctor.web.presenters.recent_scan_models import (
    RecentScanDiagnosticFactView,
    RecentScanDiagnosticQuestionGroupView,
    RecentScanDiagnosticQuestionsView,
)
from query_doctor.web.ui.html_helpers import (
    SafeHtml,
    escape_value,
    metadata_rows,
    report_badge,
    status_badge,
)
from query_doctor.web.ui.i18n import text as ui_text
from query_doctor.web.ui.action_candidates import (
    render_action_candidate_findings,
)
from query_doctor.web.ui.llm_actions import (
    OptimizedQueryActionView,
    OPTIMIZER_RESULT_ANCHOR_ID,
    actions_section_id,
    render_llm_actions_block,
)
from query_doctor.web.ui.metadata_details import (
    render_metadata_facts_section,
)
from query_doctor.web.ui.report_actions import (
    render_llm_report_failure,
    render_llm_report_progress,
)
from query_doctor.web.ui.runtime_metrics import (
    render_cluster_runtime_context_section,
    render_cm_metrics_section,
    render_data_movement_evidence_section,
    render_query_context_section,
    render_runtime_diagnosis_details,
    render_runtime_diagnosis_summary,
    render_runtime_signals,
    render_runtime_verdict,
)


def render_recent_scan_case_detail_view(
    view: RecentScanCaseDetailView,
    *,
    optimized_query_state: OptimizedQueryActionView | None = None,
    trusted_report_html: SafeHtml | str | None = None,
    llm_report_state: dict[str, Any] | None = None,
    trusted_llm_report_html: SafeHtml | str | None = None,
    trusted_optimized_query: str | None = None,
    trusted_optimizer_recommendations: str | None = None,
    optimizer_manual_guidance: str | None = None,
    optimizer_validation_result: dict[str, Any] | None = None,
    workflow_title: str = "Finished Queries",
    list_href: str = "/#recent-results",
    detail_base_path: str = "/batch/case",
    llm_enabled: bool = True,
    language: str = "en",
) -> str:
    localized_workflow_title = ui_text(
        language,
        workflow_title,
        {
            "Finished Queries": "Завершенные запросы",
            "Running Queries": "Выполняющиеся запросы",
        }.get(workflow_title, workflow_title),
    )
    safe_workflow_title = html.escape(localized_workflow_title)
    details_title = ui_text(
        language,
        f"{localized_workflow_title} details",
        {
            "Finished Queries": "Детали завершенного запроса",
            "Running Queries": "Детали выполняющегося запроса",
        }.get(workflow_title, f"Детали: {localized_workflow_title}"),
    )
    safe_details_title = html.escape(details_title)
    safe_list_href = html.escape(list_href, quote=True)
    escaped_case_id_for_url = html.escape(view.case_id, quote=True)
    report_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/python-report"
    report_export_url = f"{report_url}.md"
    llm_report_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/llm-report"
    llm_report_export_url = f"{llm_report_url}.md"
    optimized_query_url = (
        f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/optimized-query"
    )
    optimizer_validation_url = (
        f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/validate-rewrite"
    )
    actions_id = actions_section_id(llm_enabled=llm_enabled)
    actions_url = f"{detail_base_path.rstrip('/')}/{escaped_case_id_for_url}/{actions_id}"
    llm_report_view = present_report_action(llm_report_state) if llm_report_state else None
    return (
        f'<section class="panel batch-panel case-detail-panel" aria-label="{safe_details_title}">'
        f'<div class="breadcrumb"><a href="{safe_list_href}">{safe_workflow_title}</a><span>/</span>'
        f"<span>{html.escape(view.case_id)}</span></div>"
        f'<div class="batch-head"><div><h1>{safe_details_title}</h1>'
        f"<p>{html.escape(ui_text(language, 'Start with the verdict and recommended changes, then expand evidence only when needed.', 'Начните с вердикта и рекомендуемых изменений; раскрывайте доказательства только когда они нужны.'))}</p></div>"
        '<div class="batch-head-actions">'
        f'<a class="button primary" href="/#new-scan" data-open-new-scan>{html.escape(ui_text(language, "New scan", "Новый скан"))}</a>'
        f'<span class="badge blue">{html.escape(view.case_id)}</span></div></div>'
        f"{render_case_verdict(view, language=language)}"
        f"{render_case_action_plan(view, detail_base_path=detail_base_path, language=language)}"
        f"{render_case_diagnostics(view, llm_enabled=llm_enabled, language=language)}"
        f"{render_llm_actions_block(view.case_id, view.report_action, optimized_query_state, report_enabled=report_generation_enabled(view), report_disabled_reason=report_generation_disabled_reason(view, language=language), report_action_url=report_url, report_open_url=report_url, report_export_url=report_export_url, llm_report_view=llm_report_view, llm_report_action_url=llm_report_url, llm_report_open_url=llm_report_url, llm_report_export_url=llm_report_export_url, trusted_llm_report_html=trusted_llm_report_html, optimizer_action_url=optimized_query_url, optimizer_open_url=f'#{OPTIMIZER_RESULT_ANCHOR_ID}', optimizer_validation_url=optimizer_validation_url, combined_action_url=actions_url, trusted_report_html=trusted_report_html, trusted_optimized_query=trusted_optimized_query, trusted_optimizer_recommendations=trusted_optimizer_recommendations, optimizer_manual_guidance=optimizer_manual_guidance, optimizer_validation_result=optimizer_validation_result, llm_enabled=llm_enabled, language=language)}"
        "</section>"
    )


def report_generation_enabled(view: RecentScanCaseDetailView) -> bool:
    return str(view.score_severity or "").strip().lower() in {"high", "suspicious"}


def report_generation_disabled_reason(
    view: RecentScanCaseDetailView, *, language: str = "en"
) -> str:
    if str(view.score_severity or "").strip().lower() == "failed":
        return ui_text(
            language,
            "Re-run analysis successfully before generating reports for this case.",
            "Сначала успешно перезапустите анализ, затем генерируйте отчеты для этого кейса.",
        )
    return ""


def render_case_verdict(view: RecentScanCaseDetailView, *, language: str = "en") -> str:
    main_signal = diagnostic_fact_value(view, "main_signal", default="Not classified")
    title, signal_detail = case_verdict_title_parts(main_signal)
    kpis = verdict_kpi_facts(view.diagnostic_facts)
    chips = render_case_verdict_chips(view)
    return (
        '<section id="case-overview" class="case-verdict" aria-label="Case verdict">'
        '<div class="case-verdict-head">'
        "<div>"
        f'<span class="case-verdict-label">{html.escape(ui_text(language, "Verdict", "Вердикт"))}</span>'
        f'<h2 class="case-verdict-title">{escape_value(title)}</h2>'
        f"{render_case_verdict_signal_detail(signal_detail)}"
        "</div>"
        f"{verdict_priority_badge(view)}"
        "</div>"
        f"{render_case_verdict_meta(view, kpis)}"
        f"{chips}"
        "</section>"
    )


def case_verdict_title_parts(value: Any) -> tuple[Any, Any]:
    text = str(value or "").strip()
    if ":" not in text:
        return value, ""
    title, detail = (part.strip() for part in text.split(":", 1))
    if not title or not detail:
        return value, ""
    return title, detail


def render_case_verdict_signal_detail(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return f'<p class="case-verdict-signal">{escape_value(text)}</p>'


def render_case_verdict_meta(
    view: RecentScanCaseDetailView,
    facts: tuple[RecentScanDiagnosticFactView, ...],
) -> str:
    items = [
        render_case_verdict_meta_item("Query ID", view.query_id, "query"),
        *(render_case_verdict_meta_item(fact.label, fact.value) for fact in facts),
    ]
    return f'<div class="case-verdict-meta" aria-label="Case summary">{"".join(items)}</div>'


def render_case_verdict_meta_item(label: str, value: Any, kind: str = "text") -> str:
    class_name = "case-verdict-meta-item"
    if kind == "query":
        class_name += " case-verdict-meta-item--query"
    return (
        f'<div class="{class_name}">'
        f"<span>{html.escape(label)}</span>"
        f"<strong>{escape_value(value)}</strong>"
        "</div>"
    )


def diagnostic_fact_value(
    view: RecentScanCaseDetailView,
    fact_id: str,
    *,
    default: str,
) -> Any:
    fact = diagnostic_fact_by_id(view.diagnostic_facts, fact_id)
    return fact.value if fact else default


def verdict_priority_badge(view: RecentScanCaseDetailView) -> str:
    priority_fact = diagnostic_fact_by_id(view.diagnostic_facts, "priority")
    severity = (
        str(priority_fact.severity if priority_fact is not None else view.score_severity or "")
        .strip()
        .lower()
    )
    class_name = {
        "failed": "batch-severity--failed",
        "high": "batch-severity--high",
        "suspicious": "batch-severity--suspicious",
        "warning": "batch-status--warning",
        "clean": "batch-severity--clean",
    }.get(severity, "batch-severity--clean")
    priority_value = diagnostic_fact_value(view, "priority", default="Unknown priority")
    return (
        f'<span class="batch-mini-badge case-verdict-priority {class_name}">'
        f"{escape_value(compact_verdict_priority_badge_value(priority_value))}</span>"
    )


def compact_verdict_priority_badge_value(value: Any) -> Any:
    text = str(value or "").strip()
    if "follow-up" in text.lower() and " · score " in text:
        return text.split(" · score ", 1)[0]
    return value


def render_case_verdict_chips(view: RecentScanCaseDetailView) -> str:
    chips = verdict_chip_facts(view.diagnostic_facts)
    rendered = "".join(
        '<span class="case-verdict-chip">'
        f"{render_case_verdict_chip_label(fact)}{escape_value(fact.value)}"
        "</span>"
        for fact in chips
    )
    return f'<div class="case-verdict-chips">{rendered}</div>' if rendered else ""


def render_case_verdict_chip_label(fact: RecentScanDiagnosticFactView) -> str:
    safe_label = html.escape(fact.label)
    if fact.source_anchor:
        safe_anchor = html.escape(f"#{fact.source_anchor}", quote=True)
        safe_label = f'<a href="{safe_anchor}">{safe_label}</a>'
    title = f' title="{html.escape(fact.question, quote=True)}"' if fact.question else ""
    return f"<strong{title}>{safe_label}</strong>"


def render_case_status_summary(
    view: RecentScanCaseDetailView, *, llm_enabled: bool = True, language: str = "en"
) -> str:
    return render_case_status_summary_view(
        present_recent_scan_status_summary(
            view, report_label="LLM report" if llm_enabled else "Python report"
        ),
        technical_details_html=render_technical_details(view),
        language=language,
    )


def render_case_status_summary_view(
    view: RecentScanStatusSummaryView,
    *,
    technical_details_html: str = "",
    language: str = "en",
) -> str:
    contents = render_case_status_summary_contents(
        view, technical_details_html=technical_details_html
    )
    return (
        '<section id="pipeline-status" class="pipeline-status-section" '
        'aria-label="Pipeline status">'
        '<details class="panel docs-panel pipeline-status-details">'
        f"<summary>{html.escape(ui_text(language, 'Pipeline status', 'Статус обработки'))}</summary>"
        '<div class="report-body">'
        f"{contents}"
        "</div>"
        "</details>"
        "</section>"
    )


def render_case_status_summary_contents(
    view: RecentScanStatusSummaryView,
    *,
    technical_details_html: str = "",
) -> str:
    cards = "".join(
        '<div class="case-summary-card">'
        f"<span>{html.escape(card.label)}</span><strong>{render_case_status_card_value(card)}</strong>"
        "</div>"
        for card in view.cards
    )
    return (
        f'<div class="case-summary-grid case-summary-grid--pipeline">{cards}</div>'
        f"{technical_details_html}"
    )


def render_case_status_card_value(card: RecentScanStatusCardView) -> str:
    if card.value_kind == "status":
        return status_badge(card.value)
    if card.value_kind == "report":
        return report_badge(str(card.value))
    return escape_value(card.value)


def render_case_diagnostics(
    view: RecentScanCaseDetailView, *, llm_enabled: bool = True, language: str = "en"
) -> str:
    status = present_recent_scan_status_summary(
        view, report_label="LLM report" if llm_enabled else "Python report"
    )
    return (
        '<section id="diagnostics" class="diagnostics-section" '
        'aria-label="Diagnostics and evidence">'
        '<details class="panel docs-panel diagnostics-details">'
        f"<summary>{html.escape(ui_text(language, 'Diagnostics and evidence', 'Диагностика и доказательства'))}</summary>"
        '<div class="report-body diagnostics-body diagnostics-body--flat">'
        f"{render_diagnostic_questions_section(view, language=language)}"
        f"{render_pipeline_diagnostics_section(view, status, language=language)}"
        f"{render_runtime_diagnostics_section(view, language=language)}"
        f"{render_metrics_diagnostics_section(view, language=language)}"
        f"{render_metadata_diagnostics_section(view, language=language)}"
        f"{render_score_diagnostics_section(view, language=language)}"
        "</div>"
        "</details>"
        "</section>"
    )


def render_diagnostic_questions_section(
    view: RecentScanCaseDetailView, *, language: str = "en"
) -> str:
    return render_diagnostic_questions_view(
        present_recent_scan_diagnostic_questions(view), language=language
    )


def render_diagnostic_questions_view(
    view: RecentScanDiagnosticQuestionsView, *, language: str = "en"
) -> str:
    if not view.groups:
        return ""
    groups = "".join(render_diagnostic_question_group(group) for group in view.groups)
    return (
        '<section id="diagnostic-questions" class="diagnostics-subsection diagnostic-questions" '
        'aria-label="Diagnostic questions">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Diagnostic questions", "Диагностические вопросы"))}</h2>'
        '<p class="diagnostic-questions-intro">'
        f"{html.escape(ui_text(language, 'Technical facts grouped by the questions they answer, followed by source evidence for deeper review.', 'Технические факты сгруппированы по вопросам, на которые они отвечают; ниже остаются источники для углубленной проверки.'))}"
        "</p>"
        f'<div class="diagnostic-question-grid">{groups}</div>'
        "</section>"
    )


def render_diagnostic_question_group(group: RecentScanDiagnosticQuestionGroupView) -> str:
    facts = "".join(render_diagnostic_question_fact(fact) for fact in group.facts)
    return (
        '<article class="diagnostic-question-card">'
        f"<h3>{html.escape(group.title)}</h3>"
        f"<p>{html.escape(group.prompt)}</p>"
        f'<ul class="diagnostic-question-facts">{facts}</ul>'
        "</article>"
    )


def render_diagnostic_question_fact(fact: RecentScanDiagnosticFactView) -> str:
    label = html.escape(fact.label)
    if fact.source_anchor:
        anchor = html.escape(f"#{fact.source_anchor}", quote=True)
        label = f'<a href="{anchor}">{label}</a>'
    title = f' title="{html.escape(fact.question, quote=True)}"' if fact.question else ""
    return (
        f'<li class="diagnostic-question-fact diagnostic-question-fact--{html.escape(fact.severity, quote=True)}">'
        f"<span{title}>{label}</span>"
        f"<strong>{escape_value(fact.value)}</strong>"
        "</li>"
    )


def render_pipeline_diagnostics_section(
    view: RecentScanCaseDetailView,
    status: RecentScanStatusSummaryView,
    *,
    language: str = "en",
) -> str:
    return (
        '<section id="pipeline-status" class="diagnostics-subsection" '
        'aria-label="Pipeline status">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Pipeline", "Обработка"))}</h2>'
        f"{render_case_status_summary_contents(status, technical_details_html=render_technical_details(view))}"
        "</section>"
    )


def render_runtime_diagnostics_section(
    view: RecentScanCaseDetailView, *, language: str = "en"
) -> str:
    runtime_verdict_html = (
        ""
        if view.runtime_verdict.title == "Runtime context not collected"
        else render_runtime_verdict(view.runtime_verdict)
    )
    return (
        '<section id="runtime-evidence" class="diagnostics-subsection" '
        'aria-label="Runtime evidence">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Runtime", "Runtime"))}</h2>'
        f"{runtime_verdict_html}"
        f"{render_runtime_diagnosis_summary(view.runtime_diagnosis)}"
        '<div class="analysis-details-body">'
        f"{render_query_context_section(view.query_context)}"
        f"{render_runtime_diagnosis_details(view.runtime_diagnosis)}"
        f"{render_data_movement_evidence_section(view.data_movement)}"
        f"{render_cluster_runtime_context_section(view.cluster_runtime_context)}"
        f"{render_runtime_signals(view)}"
        "</div>"
        "</section>"
    )


def render_metrics_diagnostics_section(
    view: RecentScanCaseDetailView, *, language: str = "en"
) -> str:
    metrics_html = render_cm_metrics_section(view.cm_metrics)
    if not metrics_html:
        return ""
    return (
        '<section id="metrics-evidence" class="diagnostics-subsection" '
        'aria-label="Runtime metrics evidence">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Metrics", "Метрики"))}</h2>'
        '<div class="analysis-details-body">'
        f"{metrics_html}"
        "</div>"
        "</section>"
    )


def render_metadata_diagnostics_section(
    view: RecentScanCaseDetailView, *, language: str = "en"
) -> str:
    return (
        '<section id="metadata-evidence" class="diagnostics-subsection" '
        'aria-label="Metadata evidence">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Metadata", "Метаданные"))}</h2>'
        '<div class="analysis-details-body">'
        f"{render_metadata_facts_section(view.metadata)}"
        "</div>"
        "</section>"
    )


def render_score_diagnostics_section(
    view: RecentScanCaseDetailView, *, language: str = "en"
) -> str:
    return (
        '<section id="score-evidence" class="diagnostics-subsection findings-panel" '
        'aria-label="Score evidence">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Score", "Оценка"))}</h2>'
        f"{render_score_reason_explanations(view)}"
        "</section>"
    )


def render_case_action_plan(
    view: RecentScanCaseDetailView,
    *,
    detail_base_path: str = "/batch/case",
    language: str = "en",
) -> str:
    action_cards = render_action_candidate_findings(
        view, detail_base_path=detail_base_path, language=language
    )
    if not action_cards:
        action_cards = (
            '<ul class="reason-list action-candidate-list">'
            '<li class="reason-card">'
            f"<strong>{html.escape(ui_text(language, 'No prioritized rewrite or stats action', 'Нет приоритетного действия по rewrite или stats'))}</strong>"
            f"<p>{html.escape(ui_text(language, 'Deterministic analysis did not find a Medium/High query optimization, stats refresh, or runtime admission action candidate for this case.', 'Детерминированный анализ не нашел для этого кейса кандидата Medium/High на оптимизацию запроса, обновление статистики или runtime/admission действие.'))}</p>"
            "</li>"
            "</ul>"
        )
    return (
        '<section id="action-plan" class="panel docs-panel action-plan-panel" '
        'aria-label="Recommended changes">'
        f'<h2 class="section-title">{html.escape(ui_text(language, "Recommended changes", "Рекомендуемые изменения"))}</h2>'
        '<div class="report-body">'
        '<p class="action-plan-intro">'
        f"{html.escape(ui_text(language, 'Inspect the named query area, apply only the supported change direction, then verify with a comparable rerun.', 'Проверьте указанную область запроса, применяйте только поддержанное направление изменения и подтверждайте результат сопоставимым повторным запуском.'))}"
        "</p>"
        f"{action_cards}"
        "</div>"
        "</section>"
    )


def render_technical_details(view: RecentScanCaseDetailView) -> str:
    return render_technical_details_view(present_recent_scan_technical_details(view))


def render_technical_details_view(view: RecentScanTechnicalDetailsView) -> str:
    if not view.fields:
        return ""
    rows = metadata_rows(list(view.fields))
    return (
        '<details class="analysis-subdetails technical-details">'
        "<summary>Query Doctor processing timings</summary>"
        f'<div class="report-body"><div class="meta-list">{rows}</div></div>'
        "</details>"
    )


def render_score_reason_explanations(view: RecentScanCaseDetailView) -> str:
    return render_score_reason_explanations_view(present_recent_scan_score_reasons(view))


def render_score_reason_explanations_view(view: RecentScanScoreReasonsView) -> str:
    if not view.reasons:
        reason_cards = (
            '<li class="reason-card"><strong>No positive deterministic score reasons</strong>'
            "<p>Batch score does not contain a suspicious analyzer signal for this case.</p></li>"
        )
    else:
        reason_cards = "".join(render_score_reason_card_view(reason) for reason in view.reasons)
    return f'<ul class="reason-list findings-list" aria-label="Why this query is suspicious">{reason_cards}</ul>'


def render_score_reason_card_view(reason: RecentScanScoreReasonView) -> str:
    return (
        '<li class="reason-card">'
        f"<strong>{html.escape(reason.title)}</strong>"
        f"<p>{html.escape(reason.explanation)}</p>"
        "</li>"
    )
