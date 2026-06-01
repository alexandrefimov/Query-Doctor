"""Browser display redaction helpers for Query Doctor web UI."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

from query_doctor.cli import collect_cm_profiles as cm_collector
from query_doctor.safety.artifact_names import RAW_ARTIFACT_FILENAMES
from query_doctor.safety import redaction as shared_redaction


LOCAL_PATH_REPLACEMENT = "<local path hidden>"
HIDDEN_FIELD_REPLACEMENT = "[hidden field]"
RAW_PROFILE_REPLACEMENT = "[raw profile hidden]"
RAW_METADATA_REPLACEMENT = "[metadata statement hidden]"
RAW_OUTPUT_REPLACEMENT = "[subprocess output hidden]"
RAW_ARTIFACT_REPLACEMENT = "[artifact name hidden]"
MODEL_REPLACEMENT = "[model setting hidden]"
SQL_SNIPPET_REPLACEMENT = "[SQL hidden]"

FIELD_NAME_TOKENS = (
    "case_dir",
    "CM_PASSWORD",
    "CM_TOKEN",
    "KRB5CCNAME",
    "metadata_coordinator",
    "metadata_auth",
    "metadata_path",
)

RAW_ARTIFACT_FILENAME_TOKENS = RAW_ARTIFACT_FILENAMES

MODEL_NAME_RE = re.compile(
    r"\b(?:"
    r"qwen[\w:.-]*|"
    r"gpt-oss[\w:.-]*|"
    r"gpt[_-]"
    r"lst[\w:.-]*|"
    r"codestral[\w:.-]*|"
    r"deepseek[\w:.-]*|"
    r"internal[_-]model[\w:.-]*|"
    r"sqlcoder[\w:.-]*|"
    r"mistral[\w:.-]*|"
    r"magistral[\w:.-]*|"
    r"devstral[\w:.-]*|"
    r"codellama[\w:.-]*|"
    r"llama[\w:.-]*|"
    r"ollama"
    r")\b",
    re.IGNORECASE,
)
BROWSER_USER_LABEL_RE = re.compile(
    r"\b(User|Username|Effective User|Connected User|Delegated User)([ \t]*[:=][ \t]*)"
    r"([^ \t\r\n,;]+)",
    re.IGNORECASE,
)
BROWSER_HOST_LABEL_RE = re.compile(
    r"\b(Host|Hostname|Coordinator|Coordinator Host|Daemon|Impala Daemon|Impalad|Server)"
    r"([ \t]*[:=][ \t]*)([^ \t\r\n,;]+)",
    re.IGNORECASE,
)


def redact_browser_display_text(
    value: Any,
    *,
    env: Mapping[str, str] | None = None,
    redact_field_names: bool = False,
    redact_artifact_markers: bool = False,
    redact_model_names: bool = False,
    redact_sql_snippets: bool = False,
    redact_infrastructure: bool = False,
    max_chars: int | None = None,
) -> str:
    # Central browser-visible boundary: opt into narrower redaction flags per surface.
    text = str(value)
    text = redact_credentials_for_display(text, env=env)
    text = redact_local_paths_for_display(text)
    if redact_infrastructure:
        text = redact_infrastructure_identifiers_for_display(text)
    if redact_field_names:
        text = redact_field_names_for_display(text)
    if redact_artifact_markers:
        text = redact_raw_artifact_markers_for_display(text)
    if redact_model_names:
        text = redact_model_names_for_display(text)
    if redact_sql_snippets:
        text = redact_sql_snippets_for_display(text)
    return text[:max_chars] if max_chars is not None else text


def redact_credentials_for_display(text: str, *, env: Mapping[str, str] | None = None) -> str:
    effective_env = os.environ if env is None else env
    for secret in (effective_env.get("CM_PASSWORD"), effective_env.get("CM_TOKEN")):
        if secret:
            text = text.replace(secret, "<secret>")
    text = cm_collector.AUTH_HEADER_RE.sub(r"\1<redacted>", text)
    text = cm_collector.BEARER_BASIC_RE.sub(r"\1 <redacted>", text)
    text = cm_collector.URL_CREDENTIAL_RE.sub(r"\1<redacted>@", text)
    text = cm_collector.SECRET_VALUE_RE.sub(r"\1\2\3<redacted>\5", text)
    return text


def redact_local_paths_for_display(text: str) -> str:
    text = re.sub(r"(?<![\w/])(?:/private)?/tmp/[^\s<>'\"]+", LOCAL_PATH_REPLACEMENT, text)
    text = re.sub(r"(?<![\w/])/Users/[^\s<>'\"]+", LOCAL_PATH_REPLACEMENT, text)
    text = re.sub(r"(?<![\w/])/var/folders/[^\s<>'\"]+", LOCAL_PATH_REPLACEMENT, text)
    text = re.sub(r"(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+", LOCAL_PATH_REPLACEMENT, text)
    return text


def redact_infrastructure_identifiers_for_display(text: str) -> str:
    host_redactor = shared_redaction.HostAliasRedactor()

    def replace_host_label(match: re.Match[str]) -> str:
        alias = host_redactor.redact_host_value(match.group(3))
        return f"{match.group(1)}{match.group(2)}{alias}"

    text = shared_redaction.EMAIL_RE.sub("<email>", text)
    text = shared_redaction.USER_FIELD_RE.sub(r"\1<user>", text)
    text = BROWSER_USER_LABEL_RE.sub(r"\1\2<user>", text)
    text = BROWSER_HOST_LABEL_RE.sub(replace_host_label, text)
    text = shared_redaction.USER_KV_RE.sub(r"\1\2<user>", text)
    return shared_redaction.redact_host_identifiers(text, host_redactor)


def redact_field_names_for_display(text: str) -> str:
    for token in FIELD_NAME_TOKENS:
        text = text.replace(token, HIDDEN_FIELD_REPLACEMENT)
    return text


def redact_raw_artifact_markers_for_display(text: str) -> str:
    for token in ("BEGIN PROFILE", "Query Timeline"):
        text = text.replace(token, RAW_PROFILE_REPLACEMENT)
    for token in RAW_ARTIFACT_FILENAME_TOKENS:
        text = text.replace(token, RAW_ARTIFACT_REPLACEMENT)
    text = text.replace("SHOW CREATE TABLE", RAW_METADATA_REPLACEMENT)
    text = text.replace("raw stdout", RAW_OUTPUT_REPLACEMENT)
    text = text.replace("raw stderr", RAW_OUTPUT_REPLACEMENT)
    return text


def redact_model_names_for_display(text: str) -> str:
    return MODEL_NAME_RE.sub(MODEL_REPLACEMENT, text)


def redact_sql_snippets_for_display(text: str) -> str:
    # Intentionally coarse and fail-closed; hiding extra text is safer than echoing a query fragment.
    statement_pattern = (
        r"\b(?:"
        r"SELECT\b(?=[^.;\n<]{0,120}\bFROM\b)|"
        r"INSERT\s+INTO\b|"
        r"UPSERT\s+INTO\b|"
        r"DELETE\s+FROM\b|"
        r"CREATE\s+(?:TABLE|VIEW)\b|"
        r"DROP\s+(?:TABLE|VIEW)\b|"
        r"ALTER\s+(?:TABLE|VIEW)\b|"
        r"COMPUTE\s+STATS\b|"
        r"INVALIDATE\s+METADATA\b|"
        r"REFRESH\b(?=\s+[A-Za-z_`\"]|[^.;\n<]{0,40}\.)|"
        r"SHOW\s+(?:CREATE\s+TABLE|TABLE\s+STATS|COLUMN\s+STATS)\b"
        r")"
        r"[^.;\n<]{0,220}"
    )
    cte_pattern = (
        r"\bWITH\s+(?:[A-Za-z_][\w$]*|\"[^\"]+\"|`[^`]+`)\s+AS\b"
        r"[^.;\n<]{0,220}"
    )
    text = re.sub(statement_pattern, SQL_SNIPPET_REPLACEMENT, text, flags=re.IGNORECASE)
    return re.sub(cte_pattern, SQL_SNIPPET_REPLACEMENT, text, flags=re.IGNORECASE)
