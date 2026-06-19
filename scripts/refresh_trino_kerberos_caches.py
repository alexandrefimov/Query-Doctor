#!/usr/bin/env python3
"""Refresh local Trino Kerberos ticket caches referenced by web config."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


Runner = Callable[..., subprocess.CompletedProcess[str]]


class TrinoKerberosRefreshError(ValueError):
    """Raised when a Trino Kerberos cache cannot be refreshed safely."""


@dataclass(frozen=True)
class TrinoKerberosEntry:
    principal: str
    krb5_ccname: str
    krb5_config: Path | None = None


def load_config(config_path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise TrinoKerberosRefreshError("Local config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise TrinoKerberosRefreshError("Local config is not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise TrinoKerberosRefreshError("Local config root must be a JSON object.")
    return payload


def trino_kerberos_entries_from_config(config_path: Path) -> tuple[TrinoKerberosEntry, ...]:
    payload = load_config(config_path)
    defaults = {key: value for key, value in payload.items() if key != "clusters"}
    clusters = payload.get("clusters")
    sources: list[Mapping[str, Any]] = []
    if isinstance(clusters, list):
        sources.extend(
            merge_values(defaults, cluster) for cluster in clusters if isinstance(cluster, dict)
        )
    else:
        sources.append(defaults)

    entries: list[TrinoKerberosEntry] = []
    seen: set[TrinoKerberosEntry] = set()
    for values in sources:
        if values.get("trino_beta_enabled") is not True:
            continue
        principal = safe_nonempty_string(values.get("trino_kerberos_principal"))
        krb5_ccname = safe_nonempty_string(values.get("trino_krb5_ccname"))
        if principal is None or krb5_ccname is None:
            continue
        krb5_config = optional_config_path(
            values.get("trino_krb5_config"), base_dir=config_path.parent
        )
        entry = TrinoKerberosEntry(
            principal=principal,
            krb5_ccname=krb5_ccname,
            krb5_config=krb5_config,
        )
        if entry not in seen:
            entries.append(entry)
            seen.add(entry)
    return tuple(entries)


def merge_values(defaults: Mapping[str, Any], cluster: Mapping[str, Any]) -> dict[str, Any]:
    values = dict(defaults)
    values.update(cluster)
    return values


def safe_nonempty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or "\x00" in normalized:
        return None
    return normalized


def optional_config_path(value: object, *, base_dir: Path) -> Path | None:
    text = safe_nonempty_string(value)
    if text is None:
        return None
    path = Path(text).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path


def refresh_trino_kerberos_entries(
    entries: Sequence[TrinoKerberosEntry],
    *,
    keytab: Path,
    runner: Runner = subprocess.run,
) -> int:
    if not keytab.is_file():
        raise TrinoKerberosRefreshError("Kerberos keytab is missing.")
    refreshed = 0
    for entry in entries:
        env = os.environ.copy()
        if entry.krb5_config is not None:
            env["KRB5_CONFIG"] = str(entry.krb5_config)
        result = runner(
            ["kinit", "-c", entry.krb5_ccname, "-kt", str(keytab), entry.principal],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )
        if result.returncode != 0:
            raise TrinoKerberosRefreshError("Could not refresh Trino Kerberos ticket cache.")
        refreshed += 1
    return refreshed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Refresh Trino Kerberos ticket caches referenced by a local Query Doctor "
            "web config. Output never includes principals, cache paths, keytab paths, "
            "coordinator URLs, or auth material."
        )
    )
    parser.add_argument("--config", required=True, type=Path, help="Local Query Doctor config.")
    parser.add_argument("--keytab", required=True, type=Path, help="Local Kerberos keytab.")
    parser.add_argument("--quiet", action="store_true", help="Suppress success output.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        entries = trino_kerberos_entries_from_config(args.config.expanduser())
        refreshed = refresh_trino_kerberos_entries(
            entries,
            keytab=args.keytab.expanduser(),
        )
    except TrinoKerberosRefreshError as exc:
        print(f"Trino Kerberos cache refresh failed: {exc}", file=sys.stderr)
        return 2
    if not args.quiet:
        print(f"Trino Kerberos cache refresh: refreshed={refreshed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
