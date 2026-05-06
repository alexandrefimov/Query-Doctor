"""Static LLM report contract headings and prompt policy."""

REPORT_TITLE_HEADING = "# Query Doctor Report"
REPORT_SYSTEM_PROMPT = (
    "You are only a report writer. Use only supplied deterministic facts. "
    "Write in Russian. Do not invent unsupported evidence or recommendations. "
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

SHORT_SUMMARY_HEADING = "## Краткий вывод"
RECOMMENDATIONS_HEADING = "## Практические рекомендации"
DETAILED_REPORT_HEADING = "## Подробный разбор"
ANALYZER_FACTS_HEADING = "## Факты анализатора"
TABLE_METADATA_CONTEXT_HEADING = "## Table Metadata Context"
CM_TIMESERIES_CONTEXT_HEADING = "## CM Time-Series Context"
CM_METRICS_FACTS_HEADING = "## CM Metrics Facts"
CM_METRICS_CORRELATION_HEADING = "## CM Metrics Correlation"
EVIDENCE_SAFE_PROBLEMS_HEADING = "### Основные подтверждённые проблемы по профилю"
EVIDENCE_HEADING = "### Подтверждающие факты"
AMPLIFIERS_HEADING = "### Что усиливает проблему"
NOT_SUPPORTED_HEADING = "### Что НЕ подтверждается фактами"
NEXT_CHECKS_HEADING = "### Follow-up checks"
REQUIRED_REPORT_SECTIONS = [
    REPORT_TITLE_HEADING,
    SHORT_SUMMARY_HEADING,
    RECOMMENDATIONS_HEADING,
    DETAILED_REPORT_HEADING,
    EVIDENCE_SAFE_PROBLEMS_HEADING,
    EVIDENCE_HEADING,
    AMPLIFIERS_HEADING,
    NOT_SUPPORTED_HEADING,
    NEXT_CHECKS_HEADING,
]
ROOT_CAUSE_HEADING_REWRITE = {
    "## Главная причина замедления": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "### Главная причина замедления": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "## Root cause": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "### Root cause": EVIDENCE_SAFE_PROBLEMS_HEADING,
}
DETAIL_HEADING_REWRITE = {
    "## Короткий вывод": SHORT_SUMMARY_HEADING,
    "### Короткий вывод": SHORT_SUMMARY_HEADING,
    "### Краткий вывод": SHORT_SUMMARY_HEADING,
    "## Основные подтверждённые проблемы по профилю": EVIDENCE_SAFE_PROBLEMS_HEADING,
    "## Подтверждающие факты": EVIDENCE_HEADING,
    "## Что усиливает проблему": AMPLIFIERS_HEADING,
    "## Что НЕ подтверждается фактами": NOT_SUPPORTED_HEADING,
    "### Практические рекомендации": RECOMMENDATIONS_HEADING,
    "## Что проверить следующим запуском": NEXT_CHECKS_HEADING,
    "### Что проверить следующим запуском": NEXT_CHECKS_HEADING,
    "## Админские проверки": NEXT_CHECKS_HEADING,
    "### Админские проверки": NEXT_CHECKS_HEADING,
    "## Follow-up checks": NEXT_CHECKS_HEADING,
}
USER_READ_ONLY_HEADING = "### Read-only проверки, которые можно выполнить"
USER_ADMIN_PACKAGE_HEADING = "### Если проблема останется, отправьте админам/платформенной команде"
USER_VALIDATION_HEADING = "### Изменения, требующие проверки"
USER_VERIFY_HEADING = "### Как проверить улучшение"
USER_HEADING_REWRITE = {
    "## Read-only checks you can run": USER_READ_ONLY_HEADING,
    "### Read-only checks you can run": USER_READ_ONLY_HEADING,
    "## Safe checks for the SQL owner": USER_READ_ONLY_HEADING,
    "### Safe checks for the SQL owner": USER_READ_ONLY_HEADING,
    "## Read-only проверки, которые можно выполнить": USER_READ_ONLY_HEADING,
    "## If it still fails, send this to the admin/platform team": USER_ADMIN_PACKAGE_HEADING,
    "### If it still fails, send this to the admin/platform team": USER_ADMIN_PACKAGE_HEADING,
    "## Если проблема останется, отправьте админам/платформенной команде": USER_ADMIN_PACKAGE_HEADING,
    "## Changes requiring validation": USER_VALIDATION_HEADING,
    "### Changes requiring validation": USER_VALIDATION_HEADING,
    "## Изменения, требующие проверки": USER_VALIDATION_HEADING,
    "## How to verify improvement": USER_VERIFY_HEADING,
    "### How to verify improvement": USER_VERIFY_HEADING,
    "## Как проверить улучшение": USER_VERIFY_HEADING,
}
