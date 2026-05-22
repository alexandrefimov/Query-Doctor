"""Safe Kerberos ticket preflight for explicit metadata collection."""

from __future__ import annotations

import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass


KerberosCheckRunner = Callable[..., subprocess.CompletedProcess[bytes]]
DEFAULT_KERBEROS_CHECK_TIMEOUT_SEC = 5


@dataclass(frozen=True)
class KerberosTicketCheck:
    ok: bool
    reason: str | None = None


def check_kerberos_ticket_cache(
    env: Mapping[str, str],
    *,
    runner: KerberosCheckRunner = subprocess.run,
    timeout_sec: int = DEFAULT_KERBEROS_CHECK_TIMEOUT_SEC,
) -> KerberosTicketCheck:
    """Return a raw-free status for the current Kerberos ticket cache."""

    if not str(env.get("KRB5CCNAME") or "").strip():
        return KerberosTicketCheck(
            False,
            "KRB5CCNAME is required before metadata collection can use Kerberos.",
        )
    try:
        result = runner(
            ["klist", "-s"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=dict(env),
            timeout=timeout_sec,
        )
    except FileNotFoundError:
        return KerberosTicketCheck(
            False,
            "Kerberos ticket preflight could not run because klist is not available.",
        )
    except subprocess.TimeoutExpired:
        return KerberosTicketCheck(
            False,
            "Kerberos ticket preflight timed out before metadata collection started.",
        )
    except OSError:
        return KerberosTicketCheck(
            False,
            "Kerberos ticket preflight could not inspect the ticket cache.",
        )

    if result.returncode == 0:
        return KerberosTicketCheck(True)
    return KerberosTicketCheck(
        False,
        "Kerberos ticket cache is missing or expired; refresh it before metadata collection.",
    )
