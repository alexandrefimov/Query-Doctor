"""Registered Query Doctor engine adapters."""

from __future__ import annotations

from query_doctor.engines.base import EngineAdapter
from query_doctor.engines.impala import IMPALA_ADAPTER
from query_doctor.engines.trino import TRINO_ADAPTER


DEFAULT_ENGINE_NAME = "impala"


class UnknownEngineError(ValueError):
    pass


_ADAPTERS: dict[str, EngineAdapter] = {
    IMPALA_ADAPTER.engine_name: IMPALA_ADAPTER,
    TRINO_ADAPTER.engine_name: TRINO_ADAPTER,
}


def get_engine_adapter(engine_name: str) -> EngineAdapter:
    normalized = engine_name.strip().lower()
    try:
        return _ADAPTERS[normalized]
    except KeyError as exc:
        supported = ", ".join(sorted(_ADAPTERS))
        raise UnknownEngineError(
            f"Unsupported Query Doctor engine {engine_name!r}. Supported engines: {supported}."
        ) from exc


def get_default_engine_adapter() -> EngineAdapter:
    return get_engine_adapter(DEFAULT_ENGINE_NAME)


def list_engine_adapters() -> list[EngineAdapter]:
    return [_ADAPTERS[name] for name in sorted(_ADAPTERS)]
