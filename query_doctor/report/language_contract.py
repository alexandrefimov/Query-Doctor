"""Language-specific trusted report contracts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReportLanguageContract:
    """Trusted report structure for one output language."""

    language: str
    system_prompt: str
    title_heading: str
    short_summary_heading: str
    recommendations_heading: str
    detailed_report_heading: str
    analyzer_facts_heading: str
    evidence_safe_problems_heading: str
    evidence_heading: str
    amplifiers_heading: str
    not_supported_heading: str
    next_checks_heading: str
    summary_appendix_heading: str
    limitations_appendix_heading: str
    user_read_only_heading: str
    user_admin_package_heading: str
    user_validation_heading: str
    user_verify_heading: str
    zero_cardinality_not_supported_bullet: str
    root_cause_heading_rewrite: dict[str, str]
    detail_heading_rewrite: dict[str, str]
    user_heading_rewrite: dict[str, str]

    @property
    def required_sections(self) -> list[str]:
        return [
            self.title_heading,
            self.short_summary_heading,
            self.recommendations_heading,
            self.detailed_report_heading,
            self.evidence_safe_problems_heading,
            self.evidence_heading,
            self.amplifiers_heading,
            self.not_supported_heading,
            self.next_checks_heading,
        ]


def _system_prompt(language_instruction: str) -> str:
    return (
        "You are only a report writer. Use only supplied deterministic facts. "
        f"{language_instruction} Do not invent unsupported evidence or recommendations. "
        "Keep cardinality mismatch separate from memory mismatch. "
        "Use row underestimation only when actual rows are greater than estimated rows. "
        "Use row overestimation when actual rows are lower than estimated rows. "
        "Use memory underestimation only when actual or peak memory is above estimated memory. "
        "Use memory overestimation when actual or peak memory is below estimated memory. "
        "Do not treat mem ratio below 1.0 as memory underestimation evidence. "
        "Do not present Impala operator/profile counter time as query wall-clock duration unless facts explicitly provide wall-clock evidence. "
        "Use operator/profile time counter wording instead of saying an operator ran for X hours. "
        "Keep backend data skew separate from cardinality/row-estimate anomalies and execution skew. "
        "Do not claim a single slow backend/tail host unless host-tail facts explicitly support it. "
        "Do not recommend external network checks based only on TotalBytesSent. "
        "Treat TotalBytesSent as intermediate/exchange data volume unless facts explicitly say network fault. "
        "Do not call low-memory EXCHANGE operators memory bottlenecks. "
        "Do not claim HDFS, external network, codegen, skew, or spill causes unless facts explicitly support them."
    )


RU_REPORT_CONTRACT = ReportLanguageContract(
    language="ru",
    system_prompt=_system_prompt("Write in Russian."),
    title_heading="# Query Doctor Report",
    short_summary_heading="## Краткий вывод",
    recommendations_heading="## Практические рекомендации",
    detailed_report_heading="## Подробный разбор",
    analyzer_facts_heading="## Факты анализатора",
    evidence_safe_problems_heading="### Основные подтверждённые проблемы по профилю",
    evidence_heading="### Подтверждающие факты",
    amplifiers_heading="### Что усиливает проблему",
    not_supported_heading="### Что НЕ подтверждается фактами",
    next_checks_heading="### Follow-up checks",
    summary_appendix_heading="### Сводка",
    limitations_appendix_heading="### Важные ограничения",
    user_read_only_heading="### Read-only проверки, которые можно выполнить",
    user_admin_package_heading="### Если проблема останется, отправьте админам/платформенной команде",
    user_validation_heading="### Изменения, требующие проверки",
    user_verify_heading="### Как проверить улучшение",
    zero_cardinality_not_supported_bullet=(
        "- В analysis_facts.md нет подтверждённой аномалии кардинальности; не заявляйте "
        "недооценку кардинальности без соответствующего факта."
    ),
    root_cause_heading_rewrite={
        "## Главная причина замедления": "### Основные подтверждённые проблемы по профилю",
        "### Главная причина замедления": "### Основные подтверждённые проблемы по профилю",
        "## Root cause": "### Основные подтверждённые проблемы по профилю",
        "### Root cause": "### Основные подтверждённые проблемы по профилю",
    },
    detail_heading_rewrite={
        "## Короткий вывод": "## Краткий вывод",
        "### Короткий вывод": "## Краткий вывод",
        "### Краткий вывод": "## Краткий вывод",
        "## Основные подтверждённые проблемы по профилю": "### Основные подтверждённые проблемы по профилю",
        "## Подтверждающие факты": "### Подтверждающие факты",
        "## Что усиливает проблему": "### Что усиливает проблему",
        "## Что НЕ подтверждается фактами": "### Что НЕ подтверждается фактами",
        "### Практические рекомендации": "## Практические рекомендации",
        "## Что проверить следующим запуском": "### Follow-up checks",
        "### Что проверить следующим запуском": "### Follow-up checks",
        "## Админские проверки": "### Follow-up checks",
        "### Админские проверки": "### Follow-up checks",
        "## Follow-up checks": "### Follow-up checks",
    },
    user_heading_rewrite={
        "## Read-only checks you can run": "### Read-only проверки, которые можно выполнить",
        "### Read-only checks you can run": "### Read-only проверки, которые можно выполнить",
        "## Safe checks for the SQL owner": "### Read-only проверки, которые можно выполнить",
        "### Safe checks for the SQL owner": "### Read-only проверки, которые можно выполнить",
        "## Read-only проверки, которые можно выполнить": "### Read-only проверки, которые можно выполнить",
        "## If it still fails, send this to the admin/platform team": "### Если проблема останется, отправьте админам/платформенной команде",
        "### If it still fails, send this to the admin/platform team": "### Если проблема останется, отправьте админам/платформенной команде",
        "## Если проблема останется, отправьте админам/платформенной команде": "### Если проблема останется, отправьте админам/платформенной команде",
        "## Changes requiring validation": "### Изменения, требующие проверки",
        "### Changes requiring validation": "### Изменения, требующие проверки",
        "## Изменения, требующие проверки": "### Изменения, требующие проверки",
        "## How to verify improvement": "### Как проверить улучшение",
        "### How to verify improvement": "### Как проверить улучшение",
        "## Как проверить улучшение": "### Как проверить улучшение",
    },
)


EN_REPORT_CONTRACT = ReportLanguageContract(
    language="en",
    system_prompt=_system_prompt("Write in English."),
    title_heading="# Query Doctor Report",
    short_summary_heading="## Short Summary",
    recommendations_heading="## Practical Recommendations",
    detailed_report_heading="## Detailed Analysis",
    analyzer_facts_heading="## Analyzer Facts",
    evidence_safe_problems_heading="### Supported Profile Findings",
    evidence_heading="### Supporting Evidence",
    amplifiers_heading="### Amplifying Factors",
    not_supported_heading="### What Is Not Supported By Facts",
    next_checks_heading="### Follow-up checks",
    summary_appendix_heading="### Summary",
    limitations_appendix_heading="### Important Limitations",
    user_read_only_heading="### Read-only checks you can run",
    user_admin_package_heading="### If the issue remains, send this to the admin/platform team",
    user_validation_heading="### Changes requiring validation",
    user_verify_heading="### How to verify improvement",
    zero_cardinality_not_supported_bullet=(
        "- analysis_facts.md has no confirmed cardinality anomaly; do not claim "
        "cardinality underestimation without a matching fact."
    ),
    root_cause_heading_rewrite={
        "## Root cause": "### Supported Profile Findings",
        "### Root cause": "### Supported Profile Findings",
        "## Main slowdown cause": "### Supported Profile Findings",
        "### Main slowdown cause": "### Supported Profile Findings",
        "## Главная причина замедления": "### Supported Profile Findings",
        "### Главная причина замедления": "### Supported Profile Findings",
    },
    detail_heading_rewrite={
        "## Brief Summary": "## Short Summary",
        "### Brief Summary": "## Short Summary",
        "### Short Summary": "## Short Summary",
        "## Supported Profile Findings": "### Supported Profile Findings",
        "## Supporting Evidence": "### Supporting Evidence",
        "## Amplifying Factors": "### Amplifying Factors",
        "## What Is Not Supported By Facts": "### What Is Not Supported By Facts",
        "## What is NOT supported by facts": "### What Is Not Supported By Facts",
        "### Practical Recommendations": "## Practical Recommendations",
        "## Follow-up checks": "### Follow-up checks",
        "## Admin checks": "### Follow-up checks",
        "### Admin checks": "### Follow-up checks",
        "## Краткий вывод": "## Short Summary",
        "## Практические рекомендации": "## Practical Recommendations",
        "## Подробный разбор": "## Detailed Analysis",
        "### Основные подтверждённые проблемы по профилю": "### Supported Profile Findings",
        "### Подтверждающие факты": "### Supporting Evidence",
        "### Что усиливает проблему": "### Amplifying Factors",
        "### Что НЕ подтверждается фактами": "### What Is Not Supported By Facts",
    },
    user_heading_rewrite={
        "## Read-only checks you can run": "### Read-only checks you can run",
        "### Safe checks for the SQL owner": "### Read-only checks you can run",
        "## Safe checks for the SQL owner": "### Read-only checks you can run",
        "## If it still fails, send this to the admin/platform team": "### If the issue remains, send this to the admin/platform team",
        "### If it still fails, send this to the admin/platform team": "### If the issue remains, send this to the admin/platform team",
        "## Changes requiring validation": "### Changes requiring validation",
        "## How to verify improvement": "### How to verify improvement",
        "## Read-only проверки, которые можно выполнить": "### Read-only checks you can run",
        "### Read-only проверки, которые можно выполнить": "### Read-only checks you can run",
        "## Если проблема останется, отправьте админам/платформенной команде": "### If the issue remains, send this to the admin/platform team",
        "### Если проблема останется, отправьте админам/платформенной команде": "### If the issue remains, send this to the admin/platform team",
        "## Изменения, требующие проверки": "### Changes requiring validation",
        "### Изменения, требующие проверки": "### Changes requiring validation",
        "## Как проверить улучшение": "### How to verify improvement",
        "### Как проверить улучшение": "### How to verify improvement",
    },
)


REPORT_LANGUAGE_CONTRACTS = {
    RU_REPORT_CONTRACT.language: RU_REPORT_CONTRACT,
    EN_REPORT_CONTRACT.language: EN_REPORT_CONTRACT,
}
SUPPORTED_REPORT_LANGUAGES = tuple(REPORT_LANGUAGE_CONTRACTS)


def get_report_language_contract(language: str) -> ReportLanguageContract:
    try:
        return REPORT_LANGUAGE_CONTRACTS[language]
    except KeyError as exc:
        supported = ", ".join(SUPPORTED_REPORT_LANGUAGES)
        raise ValueError(
            f"unsupported report language: {language}; supported: {supported}"
        ) from exc
