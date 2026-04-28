#!/usr/bin/env python3

import argparse
import base64
import json
import os
import re
import ssl
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


CM_HOST = os.getenv("CM_HOST", "").rstrip("/")
CM_USER = os.getenv("CM_USER", "")
CM_PASS = os.getenv("CM_PASS", "")
CM_API_VERSION = os.getenv("CM_API_VERSION", "v32")
CLUSTER = os.getenv("CLUSTER", "")
SERVICE = os.getenv("SERVICE", "")

CASES_DIR = Path(os.getenv("QD_CASES_DIR", "cases"))
QUERY_DOCTOR = Path(os.getenv("QUERY_DOCTOR", "./query_doctor.py")).resolve()

VERIFY_TLS = os.getenv("CM_VERIFY_TLS", "false").lower() in ("1", "true", "yes")


def die(msg: str, code: int = 1) -> None:
    print(f"[cm_impala_case] ERROR: {msg}", file=sys.stderr)
    raise SystemExit(code)


def require_env() -> None:
    missing = []
    for name, value in [
        ("CM_HOST", CM_HOST),
        ("CM_USER", CM_USER),
        ("CM_PASS", CM_PASS),
        ("CLUSTER", CLUSTER),
        ("SERVICE", SERVICE),
    ]:
        if not value:
            missing.append(name)

    if missing:
        die("Missing env vars: " + ", ".join(missing))


def cm_url(path_parts, query=None) -> str:
    encoded_parts = [urllib.parse.quote(str(p), safe=":") for p in path_parts]
    url = f"{CM_HOST}/api/{CM_API_VERSION}/" + "/".join(encoded_parts)

    if query:
        url += "?" + urllib.parse.urlencode(query)

    return url


def cm_get_json(path_parts, query=None):
    require_env()

    url = cm_url(path_parts, query)
    token = base64.b64encode(f"{CM_USER}:{CM_PASS}".encode()).decode()

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Basic {token}",
            "Accept": "application/json",
        },
        method="GET",
    )

    ctx = None
    if not VERIFY_TLS:
        ctx = ssl._create_unverified_context()

    try:
        with urllib.request.urlopen(req, context=ctx, timeout=180) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        die(f"CM API request failed: {url}\n{e}")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        die(f"CM returned non-JSON response from {url}:\n{raw[:2000]}")


def get_first(d: dict, keys, default=None):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return default


def safe_case_name(query_id: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "_", query_id)
    return f"cm-{cleaned}"


def short_statement(stmt: str, limit: int = 160) -> str:
    stmt = re.sub(r"\s+", " ", stmt or "").strip()
    if len(stmt) <= limit:
        return stmt
    return stmt[: limit - 3] + "..."


def search_queries(args) -> None:
    data = cm_get_json(
        ["clusters", CLUSTER, "services", SERVICE, "impalaQueries"],
        {
            "from": args.time_from,
            "to": args.time_to,
            "filter": args.filter,
            "limit": args.limit,
        },
    )

    warnings = data.get("warnings") or []
    for w in warnings:
        print(f"[warning] {w}", file=sys.stderr)

    queries = data.get("queries") or data.get("items") or []

    if not queries:
        print("No queries found.")
        return

    print()
    print("idx | duration | hdfs_read | user | pool | details | queryId | statement")
    print("-" * 140)

    for i, q in enumerate(queries, 1):
        query_id = get_first(q, ["queryId", "query_id", "id"], "")
        stmt = get_first(q, ["statement", "query", "sql"], "")
        user = get_first(q, ["user", "effectiveUser", "connectedUser"], "")
        pool = get_first(q, ["pool", "resourcePool", "poolName"], "")
        details = get_first(q, ["detailsAvailable", "details_available"], "")
        duration = get_first(q, ["durationMillis", "duration", "query_duration"], "")
        hdfs_read = get_first(q, ["hdfsBytesRead", "hdfs_bytes_read"], "")

        print(
            f"{i:>3} | {duration!s:<8} | {hdfs_read!s:<9} | "
            f"{user!s:<15} | {pool!s:<20} | {details!s:<7} | "
            f"{query_id} | {short_statement(stmt)}"
        )

    print()
    print("Fetch example:")
    print(f'  ./cm_impala_case.py fetch --query-id "{get_first(queries[0], ["queryId", "query_id", "id"], "")}"')


def extract_profile(details: dict) -> str:
    # В разных версиях CM поле может называться по-разному.
    candidates = [
        "details",
        "profile",
        "runtimeProfile",
        "runtime_profile",
        "profileText",
        "profile_text",
    ]

    for key in candidates:
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value

    # Иногда profile может быть вложенным.
    for key, value in details.items():
        if isinstance(value, str) and (
            "Query Runtime Profile" in value
            or "HDFS_SCAN_NODE" in value
            or "Fragment" in value
            or "AGGREGATION_NODE" in value
        ):
            return value

    return ""


def extract_statement(details: dict) -> str:
    candidates = [
        "statement",
        "query",
        "sql",
        "queryText",
        "query_text",
    ]

    for key in candidates:
        value = details.get(key)
        if isinstance(value, str) and value.strip():
            return value

    return ""


def fetch_query(args) -> None:
    query_id = args.query_id

    details = cm_get_json(
        ["clusters", CLUSTER, "services", SERVICE, "impalaQueries", query_id],
        {
            "format": "text",
        },
    )

    case_dir = Path(args.case_dir) if args.case_dir else CASES_DIR / safe_case_name(query_id)
    case_dir.mkdir(parents=True, exist_ok=True)

    raw_path = case_dir / "cm_query_details.json"
    raw_path.write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")

    profile = extract_profile(details)
    statement = extract_statement(details)

    if statement:
        (case_dir / "sql.sql").write_text(statement.strip() + "\n", encoding="utf-8")
    else:
        (case_dir / "sql.sql").write_text(
            "-- SQL statement was not found in CM API response.\n",
            encoding="utf-8",
        )

    if profile:
        (case_dir / "profile.txt").write_text(profile.strip() + "\n", encoding="utf-8")
    else:
        (case_dir / "profile.txt").write_text(
            "Profile was not found in CM API response.\n"
            "Check cm_query_details.json and adjust extract_profile().\n",
            encoding="utf-8",
        )

    # Часть метаданных может лежать рядом с details.
    meta_keys = [
        "queryId",
        "user",
        "effectiveUser",
        "connectedUser",
        "pool",
        "resourcePool",
        "poolName",
        "startTime",
        "endTime",
        "durationMillis",
        "duration",
        "hdfsBytesRead",
        "memoryPerNodePeak",
        "admissionResult",
        "detailsAvailable",
    ]

    notes = [
        "# CM Impala Query Case",
        "",
        f"- collected_at: {datetime.now().isoformat(timespec='seconds')}",
        f"- cm_host: {CM_HOST}",
        f"- cluster: {CLUSTER}",
        f"- service: {SERVICE}",
        f"- query_id: {query_id}",
        "",
        "## Metadata",
        "",
    ]

    for key in meta_keys:
        if key in details:
            notes.append(f"- {key}: {details[key]}")

    if not any(key in details for key in meta_keys):
        notes.append("- metadata: not found at top level; inspect cm_query_details.json")

    notes.extend(
        [
            "",
            "## Problem",
            "",
            "- Запрос выбран из Cloudera Manager для анализа Query Doctor.",
            "- Симптом: долгий/дорогой Impala-запрос.",
            "",
        ]
    )

    (case_dir / "notes.md").write_text("\n".join(notes) + "\n", encoding="utf-8")

    print(f"[cm_impala_case] case created: {case_dir}")
    print(f"[cm_impala_case] raw: {raw_path}")
    print(f"[cm_impala_case] sql.sql chars: {len(statement)}")
    print(f"[cm_impala_case] profile.txt chars: {len(profile)}")

    if not profile:
        print(
            "[cm_impala_case] WARNING: profile was not extracted. Inspect cm_query_details.json keys:",
            file=sys.stderr,
        )
        print(sorted(details.keys()), file=sys.stderr)

    if args.analyze:
        if not QUERY_DOCTOR.exists():
            die(f"query_doctor.py not found: {QUERY_DOCTOR}")

        cmd = [
            str(QUERY_DOCTOR),
            str(case_dir),
        ]

        if args.model:
            cmd.extend(["--model", args.model])

        print("[cm_impala_case] running:", " ".join(cmd))
        subprocess.run(cmd, check=False)


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Query Doctor cases from Cloudera Manager Impala API")
    sub = parser.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("search", help="Search Impala queries in CM")
    s.add_argument("--from", dest="time_from", required=True)
    s.add_argument("--to", dest="time_to", required=True)
    s.add_argument("--filter", required=True)
    s.add_argument("--limit", type=int, default=20)
    s.set_defaults(func=search_queries)

    f = sub.add_parser("fetch", help="Fetch one Impala query by queryId into case directory")
    f.add_argument("--query-id", required=True)
    f.add_argument("--case-dir", default=None)
    f.add_argument("--analyze", action="store_true")
    f.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3-coder:30b"))
    f.set_defaults(func=fetch_query)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
