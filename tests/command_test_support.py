from __future__ import annotations

from collections.abc import Sequence
from query_doctor.cli.commands import command_spec


def command_uses_role(command: Sequence[object], role: str) -> bool:
    spec = command_spec(role)
    parts = [str(part) for part in command]
    if not parts:
        return False
    if parts[0] == spec.console_script:
        return True
    if len(parts) >= 3 and parts[1] == "-m" and parts[2] == spec.module:
        return True
    return False


def command_args(command: Sequence[object], role: str) -> list[str]:
    spec = command_spec(role)
    parts = [str(part) for part in command]
    if parts and parts[0] == spec.console_script:
        return parts[1:]
    if len(parts) >= 3 and parts[1] == "-m" and parts[2] == spec.module:
        return parts[3:]
    raise AssertionError(f"command does not use Query Doctor CLI role {role!r}: {parts!r}")
