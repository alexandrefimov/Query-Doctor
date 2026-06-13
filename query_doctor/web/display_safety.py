"""Browser-visible display sanitizers for dynamic web text."""

from __future__ import annotations

from query_doctor.safety.browser_display import redact_browser_display_text


HIDDEN_FIELD_REPLACEMENT = "[hidden field]"
BROWSER_ERROR_FIELD_NAME_TOKENS = (
    "case_dir",
    "KRB5CCNAME",
    "metadata_coordinator",
    "metadata_auth",
    "metadata_kerberos_host_fqdn",
    "metadata_path",
)


def sanitize_browser_error_text(value: object, *, max_chars: int | None = 1200) -> str:
    text = redact_browser_display_text(
        value,
        redact_artifact_markers=True,
        redact_model_names=True,
        redact_sql_snippets=True,
        redact_infrastructure=True,
        max_chars=max_chars,
    )
    for token in BROWSER_ERROR_FIELD_NAME_TOKENS:
        text = text.replace(token, HIDDEN_FIELD_REPLACEMENT)
    return text
