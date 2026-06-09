"""CLI entry point for the local Query Doctor web server."""

from __future__ import annotations

import sys
from http.server import ThreadingHTTPServer
from pathlib import Path

from query_doctor.cli import collect_cm_profiles as cm_collector
from query_doctor.web.app import make_handler
from query_doctor.web.config import (
    LOCAL_BIND_HOSTS,
    build_web_settings,
    validate_bind_host,
    validate_public_demo_settings,
    validate_web_startup_config,
)
from query_doctor.web.models import WebError
from query_doctor.web.public_demo import prepare_public_demo_runtime
from query_doctor.web.server_args import parse_args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        settings = build_web_settings(args, cwd=Path.cwd())
        public_demo_runtime = prepare_public_demo_runtime(settings)
        if public_demo_runtime is not None:
            settings = public_demo_runtime.settings
        validate_bind_host(settings.host, allow_nonlocal_web_bind=settings.allow_nonlocal_web_bind)
        validate_public_demo_settings(settings)
        startup_warnings = validate_web_startup_config(
            settings.config,
            cwd=Path.cwd(),
            require_cm=settings.batch_summary is None,
        )
    except WebError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    except cm_collector.ConfigError as exc:
        print(f"[Query Doctor web] ERROR: {exc}", file=sys.stderr)
        return 2
    if settings.host not in LOCAL_BIND_HOSTS:
        print(
            "[Query Doctor web] WARNING: non-local bind requested for a local web server.",
            file=sys.stderr,
        )
    for warning in startup_warnings:
        print(f"[Query Doctor web] WARNING: {warning}", file=sys.stderr)

    handler = make_handler(settings)
    server = ThreadingHTTPServer((settings.host, settings.port), handler)
    print(f"[Query Doctor web] listening on http://{settings.host}:{settings.port}")
    print(
        "[Query Doctor web] credentials and CM config are read only by local subprocesses; they are not shown in the UI."
    )
    if settings.public_demo:
        print("[Query Doctor web] public demo mode: POST actions are disabled.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Query Doctor web] stopped")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
