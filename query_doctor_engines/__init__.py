"""Engine adapter registry for Query Doctor."""

from query_doctor_engines.base import EngineAdapter
from query_doctor_engines.registry import (
    UnknownEngineError,
    get_default_engine_adapter,
    get_engine_adapter,
    list_engine_adapters,
)

__all__ = [
    "EngineAdapter",
    "UnknownEngineError",
    "get_default_engine_adapter",
    "get_engine_adapter",
    "list_engine_adapters",
]
