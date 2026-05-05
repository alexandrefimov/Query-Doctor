"""Browser display redaction helpers for Query Doctor web UI."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from typing import Any

import query_doctor_collect_cm_profiles as cm_collector


LOCAL_PATH_REPLACEMENT = "<local path hidden>"
HIDDEN_FIELD_REPLACEMENT = "[hidden field]"
RAW_PROFILE_REPLACEMENT = "[raw profile hidden]"
RAW_METADATA_REPLACEMENT = "[metadata statement hidden]"
RAW_OUTPUT_REPLACEMENT = "[subprocess output hidden]"
RAW_ARTIFACT_REPLACEMENT = "[artifact name hidden]"
MODEL_REPLACEMENT = "[model setting hidden]"

FIELD_NAME_TOKENS = (
    "case_dir",
    "CM_PASSWORD",
    "CM_TOKEN",
    "KRB5CCNAME",
    "metadata_coordinator",
    "metadata_auth",
    "metadata_path",
)

RAW_ARTIFACT_FILENAME_TOKENS = (
    "profile_digest.md",
    "cm_metadata.json",
    "collection_warnings.txt",
    "analysis_facts.md",
    "diagnosis.md",
    "diagnosis.partial.md",
    "optimized_query.sql",
    "optimized_query.validated.json",
    "impala_context.md",
    "impala_context.json",
)


def redact_browser_display_text(
    value: Any,
    *,
    env: Mapping[str, str] | None = None,
    redact_field_names: bool = False,
    redact_artifact_markers: bool = False,
    redact_model_names: bool = False,
    max_chars: int | None = None,
) -> str:
    text = str(value)
    text = redact_credentials_for_display(text, env=env)
    text = redact_local_paths_for_display(text)
    if redact_field_names:
        text = redact_field_names_for_display(text)
    if redact_artifact_markers:
        text = redact_raw_artifact_markers_for_display(text)
    if redact_model_names:
        text = redact_model_names_for_display(text)
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
    text = re.sub(r"\bqwen[\w:.-]*", MODEL_REPLACEMENT, text, flags=re.IGNORECASE)
    return re.sub(r"\bollama\b", MODEL_REPLACEMENT, text, flags=re.IGNORECASE)
