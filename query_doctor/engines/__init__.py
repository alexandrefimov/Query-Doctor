"""Engine adapter registry for Query Doctor."""

from query_doctor.engines.base import EngineAdapter
from query_doctor.engines.capabilities import (
    EngineCapability,
    adapter_flag_capabilities,
    adapter_flags_for_engine,
    capability_ids,
    cli_role_capabilities,
    cli_roles_for_engine,
    engine_capabilities,
    product_adapter_flags,
    script_paths_for_engine,
    second_engine_cli_roles,
    unsupported_product_capabilities,
)
from query_doctor.engines.registry import (
    UnknownEngineError,
    get_default_engine_adapter,
    get_engine_adapter,
    list_engine_adapters,
)

__all__ = [
    "EngineCapability",
    "EngineAdapter",
    "UnknownEngineError",
    "adapter_flag_capabilities",
    "adapter_flags_for_engine",
    "capability_ids",
    "cli_role_capabilities",
    "cli_roles_for_engine",
    "engine_capabilities",
    "get_default_engine_adapter",
    "get_engine_adapter",
    "list_engine_adapters",
    "product_adapter_flags",
    "script_paths_for_engine",
    "second_engine_cli_roles",
    "unsupported_product_capabilities",
]
