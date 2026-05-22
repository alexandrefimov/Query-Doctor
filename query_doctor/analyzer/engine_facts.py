"""Typed normalized engine facts for contract-shaping work.

This module is intentionally narrower than a full analyzer abstraction. It
defines the raw-free fact object that future parser outputs can target before
Recent ranking, reports, or browser presenters consume them.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal, Union

from query_doctor.safety import redaction


DiagnosticState = Literal["supported", "not_observed", "unknown"]
MetricValue = Union[bool, float, int, str, None]

VALID_DIAGNOSTIC_STATES = frozenset({"supported", "not_observed", "unknown"})
ENGINE_FACT_BOUNDARY_SCHEMA_VERSION = "engine_fact_boundary_v1"


class EngineFactContractError(ValueError):
    """Raised when a normalized engine fact violates the local contract."""


@dataclass(frozen=True)
class MetricFact:
    fact_id: str
    state: DiagnosticState
    value: MetricValue = None
    unit: str | None = None
    summary: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.fact_id, "fact_id")
        _validate_state(self.state)
        if self.unit is not None:
            _validate_identifier(self.unit, "unit")
        if self.state == "unknown" and self.value is not None:
            raise EngineFactContractError("unknown metric facts must not carry values")

    def to_public_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.fact_id,
            "state": self.state,
        }
        if self.value is not None:
            payload["value"] = self.value
        if self.unit:
            payload["unit"] = self.unit
        if self.summary:
            payload["summary"] = self.summary
        return payload


@dataclass(frozen=True)
class LimitationFact:
    fact_id: str
    state: DiagnosticState
    summary: str

    def __post_init__(self) -> None:
        _validate_identifier(self.fact_id, "fact_id")
        _validate_state(self.state)
        if not self.summary.strip():
            raise EngineFactContractError("limitation facts need a summary")

    def to_public_dict(self) -> dict[str, str]:
        return {
            "id": self.fact_id,
            "state": self.state,
            "summary": self.summary,
        }


@dataclass(frozen=True)
class EngineIdentityFacts:
    engine: str
    source: str
    parser_coverage: DiagnosticState
    source_version: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.engine, "engine")
        _validate_identifier(self.source, "source")
        _validate_state(self.parser_coverage)
        if self.source_version is not None:
            _validate_safe_label(self.source_version, "source_version")

    def to_public_dict(self) -> dict[str, str]:
        payload = {
            "engine": self.engine,
            "source": self.source,
            "parser_coverage": self.parser_coverage,
        }
        if self.source_version:
            payload["source_version"] = self.source_version
        return payload


@dataclass(frozen=True)
class QueryLifecycleFacts:
    state: DiagnosticState
    lifecycle: str
    blocked: DiagnosticState = "unknown"
    failure: DiagnosticState = "unknown"

    def __post_init__(self) -> None:
        _validate_state(self.state)
        _validate_safe_label(self.lifecycle, "lifecycle")
        _validate_state(self.blocked)
        _validate_state(self.failure)

    def to_public_dict(self) -> dict[str, str]:
        return {
            "state": self.state,
            "lifecycle": self.lifecycle,
            "blocked": self.blocked,
            "failure": self.failure,
        }


@dataclass(frozen=True)
class EngineFactBundle:
    identity: EngineIdentityFacts
    lifecycle: QueryLifecycleFacts
    timing: tuple[MetricFact, ...] = ()
    resources: tuple[MetricFact, ...] = ()
    stages: tuple[MetricFact, ...] = ()
    limitations: tuple[LimitationFact, ...] = ()

    def facts_by_id(self) -> dict[str, MetricFact | LimitationFact]:
        facts: dict[str, MetricFact | LimitationFact] = {}
        for fact in self.timing + self.resources + self.stages + self.limitations:
            if fact.fact_id in facts:
                raise EngineFactContractError(f"duplicate engine fact id: {fact.fact_id}")
            facts[fact.fact_id] = fact
        return facts

    def to_public_dict(self) -> dict[str, Any]:
        self.facts_by_id()
        return {
            "identity": self.identity.to_public_dict(),
            "lifecycle": self.lifecycle.to_public_dict(),
            "timing": [fact.to_public_dict() for fact in self.timing],
            "resources": [fact.to_public_dict() for fact in self.resources],
            "stages": [fact.to_public_dict() for fact in self.stages],
            "limitations": [fact.to_public_dict() for fact in self.limitations],
        }


LOCAL_PATH_RE = re.compile(
    r"(?<![\w/])(?:/private)?/(?:Users|home|tmp|var|etc)/[^\s<>'\"]+"
    r"|(?<![\w/])[A-Za-z]:\\[^\s<>'\"]+"
)
URL_RE = re.compile(r"\bhttps?://\S+", re.IGNORECASE)
SQL_SNIPPET_RE = re.compile(
    r"\b(?:SELECT|WITH|INSERT|UPDATE|DELETE|CREATE|DROP|ALTER)\b"
    r"(?=[\s\S]{0,160}\b(?:FROM|JOIN|TABLE|INTO)\b)",
    re.IGNORECASE,
)


def public_engine_facts_text(bundle: EngineFactBundle) -> str:
    return json.dumps(bundle.to_public_dict(), ensure_ascii=True, sort_keys=True)


def engine_fact_boundary_payload(bundle: EngineFactBundle) -> dict[str, Any]:
    violations = validate_engine_fact_bundle_raw_free(bundle)
    if violations:
        joined = ", ".join(violations)
        raise EngineFactContractError(
            f"engine fact bundle is not safe for report/browser boundary: {joined}"
        )

    public = bundle.to_public_dict()
    identity = public["identity"]
    boundary_identity = {
        "engine": identity["engine"],
        "parser_coverage": identity["parser_coverage"],
    }
    if "source_version" in identity:
        boundary_identity["source_version"] = identity["source_version"]

    return {
        "schema_version": ENGINE_FACT_BOUNDARY_SCHEMA_VERSION,
        "identity": boundary_identity,
        "lifecycle": public["lifecycle"],
        "fact_groups": {
            "timing": public["timing"],
            "resources": public["resources"],
            "stages": public["stages"],
            "limitations": public["limitations"],
        },
    }


def engine_fact_boundary_text(bundle: EngineFactBundle) -> str:
    return json.dumps(engine_fact_boundary_payload(bundle), ensure_ascii=True, sort_keys=True)


def validate_engine_fact_bundle_raw_free(
    bundle: EngineFactBundle,
    *,
    forbidden_tokens: tuple[str, ...] = (),
) -> list[str]:
    text = public_engine_facts_text(bundle)
    lower_text = text.lower()
    violations: list[str] = []

    if redaction.EMAIL_RE.search(text):
        violations.append("email")
    if redaction.IPV4_RE.search(text):
        violations.append("ipv4")
    if redaction.HOSTLIKE_FQDN_RE.search(text):
        violations.append("hostname")
    if URL_RE.search(text):
        violations.append("url")
    if LOCAL_PATH_RE.search(text):
        violations.append("local_path")
    if redaction.SECRET_VALUE_RE.search(text):
        violations.append("secret")
    if SQL_SNIPPET_RE.search(text):
        violations.append("sql")

    for token in forbidden_tokens:
        if token and token.lower() in lower_text:
            violations.append(f"forbidden_token:{token}")

    return sorted(set(violations))


def _validate_state(state: str) -> None:
    if state not in VALID_DIAGNOSTIC_STATES:
        raise EngineFactContractError(f"unsupported diagnostic state: {state}")


def _validate_identifier(value: str, field_name: str) -> None:
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise EngineFactContractError(f"{field_name} must be a lower-case snake_case identifier")


def _validate_safe_label(value: str, field_name: str) -> None:
    if not value.strip():
        raise EngineFactContractError(f"{field_name} must not be empty")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise EngineFactContractError(f"{field_name} must not contain control characters")
