"""Core graph assembly and reporting for scripts/agent_code_graph.py."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import tempfile
from collections import Counter, defaultdict, deque
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Sequence

from agent_code_graph_extractors import (
    CODE_SUFFIXES,
    CONFIG_SUFFIXES,
    DOC_SUFFIXES,
    GO_SUFFIXES,
    PY_SUFFIXES,
    SCRIPT_SUFFIXES,
    SPECIAL_FILENAMES,
    SUPPORT_SUFFIXES,
    TS_SUFFIXES,
    Edge,
    dedupe_edges,
    extract_chart_edges,
    extract_doc_edges,
    extract_file_reference_edges,
    extract_go_edges,
    extract_python_analysis,
    extract_ts_edges,
    infer_test_edges,
    iter_files,
    rel,
)


HUB_DEGREE_THRESHOLD = 30
HUB_FILENAMES = {"AGENTS.md", "Makefile", "README.md", "README.ru.md", "pyproject.toml"}
USAGE_SCHEMA = "agent_code_graph_usage_v1"
CONTEXT_LEDGER_SCHEMA = "agent_code_graph_context_ledger_v1"
USAGE_DIR = Path("tmp") / "agent-code-graph"
USAGE_LOG_NAME = "usage.jsonl"
USAGE_STATE_DIR = "agent-code-graph-usage"
MAX_CONTEXT_LINE_CHARS = 500


def is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def node_kind(node: str) -> str:
    if node.startswith("pkg:"):
        return "package"
    if node.startswith("external:"):
        return "external"
    if node.endswith(".md"):
        return "doc"
    if "/test" in node or node.startswith("tests/") or node.endswith("_test.go"):
        return "test"
    name = Path(node).name
    suffix = Path(node).suffix
    if node.startswith("scripts/") or suffix in SCRIPT_SUFFIXES or name in SPECIAL_FILENAMES:
        return "script"
    if node.startswith("cmd/"):
        return "entrypoint"
    if suffix in CONFIG_SUFFIXES:
        return "config"
    if node.endswith(CODE_SUFFIXES):
        return "code"
    return "node"


def area_for(node: str) -> str:
    if node.startswith("pkg:"):
        node = node.removeprefix("pkg:")
    if node.startswith("external:"):
        return "external"
    if node.endswith(".md"):
        return "docs"
    parts = Path(node).parts
    if not parts:
        return node
    if parts[0] == "query_doctor" and len(parts) >= 2:
        return f"query_doctor.{parts[1]}"
    if parts[0] == "query_doctor_engines" and len(parts) >= 2:
        return f"query_doctor_engines.{parts[1]}"
    if parts[0] in {"docs", "scripts", "tests"}:
        return parts[0]
    if parts[0] == "deploy" and len(parts) >= 2:
        return f"deploy/{parts[1]}"
    if parts[0] in {"schemas", "examples"}:
        return parts[0]
    if parts[0] in {"cmd", "internal", "pkg"}:
        return parts[0] if len(parts) == 1 else f"{parts[0]}/{parts[1]}"
    if parts[0] == "web":
        return "web"
    return parts[0]


def connected_components(nodes: set[str], edges: list[Edge]) -> list[list[str]]:
    graph: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        graph[node]
    for edge in edges:
        graph[edge.source].add(edge.target)
        graph[edge.target].add(edge.source)
    seen: set[str] = set()
    components: list[list[str]] = []
    for node in sorted(nodes):
        if node in seen:
            continue
        queue = deque([node])
        seen.add(node)
        component: list[str] = []
        while queue:
            current = queue.popleft()
            component.append(current)
            for nxt in sorted(graph[current]):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        components.append(sorted(component))
    return sorted(components, key=lambda item: (-len(item), item))


def entrypoints(nodes: set[str]) -> list[str]:
    result = []
    for node in nodes:
        name = Path(node).name
        if node_kind(node) == "test":
            continue
        if (
            node.startswith("scripts/")
            or node.startswith("cmd/")
            or node.startswith("query_doctor/cli/")
            or node in {"web/src/main.tsx", "web/src/main.ts", "web/src/App.tsx"}
            or name in {"main.go", "Dockerfile", "Makefile", "pyproject.toml"}
        ):
            result.append(node)
    return sorted(result)[:80]


def summarize(nodes: set[str], edges: list[Edge], max_items: int) -> dict:
    degree = Counter()
    inbound = Counter()
    outbound = Counter()
    relation_counts = Counter(edge.relation for edge in edges)
    confidence_counts = Counter(edge.confidence for edge in edges)
    area_edges = Counter()
    tests_by_target: dict[str, set[str]] = defaultdict(set)

    for edge in edges:
        degree[edge.source] += 1
        degree[edge.target] += 1
        outbound[edge.source] += 1
        inbound[edge.target] += 1
        source_area = area_for(edge.source)
        target_area = area_for(edge.target)
        if source_area != target_area:
            area_edges[(source_area, target_area)] += 1
        if node_kind(edge.source) == "test" and node_kind(edge.target) != "test":
            tests_by_target[edge.target].add(edge.source)

    components = connected_components(nodes, edges)
    top_nodes = [
        {
            "node": node,
            "degree": count,
            "inbound": inbound[node],
            "outbound": outbound[node],
            "kind": node_kind(node),
            "area": area_for(node),
        }
        for node, count in degree.most_common(max_items)
    ]
    high_degree_without_tests = []
    for node, count in degree.most_common(max_items * 4):
        if node_kind(node) == "code" and node not in tests_by_target:
            high_degree_without_tests.append(
                {
                    "node": node,
                    "degree": count,
                    "inbound": inbound[node],
                    "outbound": outbound[node],
                }
            )
        if len(high_degree_without_tests) >= max_items:
            break

    return {
        "node_count": len(nodes),
        "edge_count": len(edges),
        "component_count": len(components),
        "relation_counts": dict(sorted(relation_counts.items())),
        "confidence_counts": dict(sorted(confidence_counts.items())),
        "largest_components": [
            {"size": len(component), "sample": component[:12]} for component in components[:5]
        ],
        "top_nodes": top_nodes,
        "top_area_edges": [
            {"source_area": src, "target_area": dst, "count": count}
            for (src, dst), count in area_edges.most_common(max_items)
        ],
        "top_test_targets": [
            {"target": target, "test_count": len(tests), "tests": sorted(tests)[:8]}
            for target, tests in sorted(
                tests_by_target.items(), key=lambda item: (-len(item[1]), item[0])
            )[:max_items]
        ],
        "high_degree_without_direct_tests": high_degree_without_tests,
        "entrypoints": entrypoints(nodes),
    }


def normalize_graph_path(path: str) -> str:
    return path.strip().replace("\\", "/").removeprefix("./")


def degree_counts(payload: dict) -> Counter[str]:
    degree: Counter[str] = Counter()
    for edge in payload["edges"]:
        degree[edge["source"]] += 1
        degree[edge["target"]] += 1
    return degree


def candidate_nodes_for_path(payload: dict, path: str) -> list[str]:
    nodes = {node["id"] for node in payload["nodes"]}
    normalized = normalize_graph_path(path)
    candidates: list[str] = []
    if normalized in nodes:
        candidates.append(normalized)
    if normalized.startswith("pkg:") and normalized in nodes:
        candidates.append(normalized)
    else:
        path_obj = Path(normalized)
        if path_obj.suffix == ".go" and path_obj.parent.as_posix() != ".":
            package_node = f"pkg:{path_obj.parent.as_posix()}"
            if package_node in nodes:
                candidates.append(package_node)
    return sorted(set(candidates))


def node_record(payload: dict, node: str) -> dict:
    for item in payload["nodes"]:
        if item["id"] == node:
            return item
    return {"id": node, "kind": node_kind(node), "area": area_for(node)}


def file_like_node(node: str) -> bool:
    return not node.startswith(("pkg:", "external:", "parse-error:"))


def is_hub_node(node: str, degree: int) -> bool:
    return degree >= HUB_DEGREE_THRESHOLD or Path(node).name in HUB_FILENAMES


def edge_weight(edge: dict) -> int:
    relation_weight = {
        "imports": 7,
        "test_name_targets": 7,
        "file_ref": 5,
        "chart_schema": 4,
        "chart_values": 4,
        "chart_member": 3,
        "doc_link": 3,
    }
    return relation_weight.get(edge["relation"], 1)


def kind_weight(kind: str) -> int:
    return {
        "test": 8,
        "entrypoint": 6,
        "config": 5,
        "script": 5,
        "doc": 4,
        "code": 4,
        "package": 2,
    }.get(kind, 1)


def hub_penalty(node: str, kind: str, degree: int) -> int:
    if not is_hub_node(node, degree):
        return 0
    if kind in {"doc", "script", "config"}:
        return 8
    return 3


def related_node_rows(payload: dict, candidates: set[str], max_items: int) -> list[dict]:
    degree = degree_counts(payload)
    rows: dict[str, dict] = {}
    for edge in payload["edges"]:
        source = edge["source"]
        target = edge["target"]
        if source in candidates and target not in candidates:
            other = target
            direction = "out"
        elif target in candidates and source not in candidates:
            other = source
            direction = "in"
        else:
            continue
        record = node_record(payload, other)
        score = (
            edge_weight(edge)
            + kind_weight(record["kind"])
            - hub_penalty(other, record["kind"], degree[other])
        )
        row = rows.setdefault(
            other,
            {
                "node": other,
                "kind": record["kind"],
                "area": record["area"],
                "degree": degree[other],
                "hub": is_hub_node(other, degree[other]),
                "score": 0,
                "reasons": [],
            },
        )
        row["score"] += score
        row["reasons"].append(
            {
                "direction": direction,
                "relation": edge["relation"],
                "confidence": edge["confidence"],
                "via": source if direction == "in" else target,
            }
        )
    return sorted(rows.values(), key=lambda item: (-item["score"], item["node"]))[:max_items]


def group_related_rows(rows: Sequence[dict]) -> dict[str, list[dict]]:
    groups = {"tests": [], "docs": [], "entrypoints": [], "support": [], "code": []}
    for row in rows:
        kind = row["kind"]
        if kind == "test":
            groups["tests"].append(row)
        elif kind == "doc":
            groups["docs"].append(row)
        elif kind == "entrypoint":
            groups["entrypoints"].append(row)
        elif kind in {"config", "script"}:
            groups["support"].append(row)
        elif kind in {"code", "package"}:
            groups["code"].append(row)
    return groups


def direct_edges_for(payload: dict, candidates: set[str], max_items: int) -> list[dict]:
    edges = [
        edge
        for edge in payload["edges"]
        if edge["source"] in candidates or edge["target"] in candidates
    ]
    return sorted(
        edges,
        key=lambda edge: (
            -edge_weight(edge),
            edge["relation"],
            edge["source"],
            edge["target"],
        ),
    )[:max_items]


def explain_path(payload: dict, path: str, *, max_items: int = 20) -> dict:
    normalized = normalize_graph_path(path)
    candidates = set(candidate_nodes_for_path(payload, normalized))
    related = related_node_rows(payload, candidates, max_items=max_items)
    return {
        "path": normalized,
        "matched_nodes": [node_record(payload, node) for node in sorted(candidates)],
        "direct_edges": direct_edges_for(payload, candidates, max_items=max_items),
        "related": related,
        "groups": group_related_rows(related),
        "validation_hints": validation_hints_for_paths([normalized]),
        "unmapped": not candidates,
    }


def _symbol_query_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^A-Za-z0-9]+|_+", value.lower())
        if len(token) >= 2 and token not in {"test", "tests"}
    }


def symbol_match_score(symbol: dict, query: str) -> int:
    name = str(symbol.get("name") or "")
    qualified = ".".join(item for item in (str(symbol.get("parent") or ""), name) if item)
    query_lower = query.lower()
    if qualified == query or name == query:
        return 120
    if qualified.lower() == query_lower or name.lower() == query_lower:
        return 110
    if query_lower in qualified.lower() or query_lower in name.lower():
        return 80
    query_tokens = _symbol_query_tokens(query)
    symbol_tokens = _symbol_query_tokens(qualified)
    overlap = len(query_tokens & symbol_tokens)
    return overlap * 15


def matching_symbols(payload: dict, query: str, *, max_items: int = 20) -> list[dict]:
    rows = []
    for symbol in payload.get("symbols", []):
        score = symbol_match_score(symbol, query)
        if score <= 0:
            continue
        rows.append({**symbol, "score": score})
    return sorted(
        rows,
        key=lambda item: (
            -int(item["score"]),
            0 if str(item["path"]).startswith("tests/") == query.lower().startswith("test") else 1,
            str(item["path"]),
            int(item["start"]),
        ),
    )[:max_items]


def explain_symbol(payload: dict, query: str, *, max_items: int = 20) -> dict:
    matches = matching_symbols(payload, query, max_items=max_items)
    if not matches:
        return {"query": query, "symbol_matches": [], "unmapped": True}
    result = explain_path(payload, str(matches[0]["path"]), max_items=max_items)
    result["query"] = query
    result["symbol_matches"] = matches
    related_paths = {row["node"] for row in result["related"] if file_like_node(row["node"])}
    context_paths = {result["path"], *related_paths}
    context_symbols = []
    for symbol in payload.get("symbols", []):
        if symbol.get("path") not in context_paths:
            continue
        score = symbol_match_score(symbol, query)
        if score > 0:
            context_symbols.append({**symbol, "score": score})
    result["context_symbols"] = sorted(
        context_symbols,
        key=lambda item: (-int(item["score"]), str(item["path"]), int(item["start"])),
    )
    return result


def context_candidate_rows(repo: Path, result: dict, *, max_items: int = 20) -> list[dict]:
    """Return graph-ranked repository files, with the requested path first."""
    repo = repo.resolve()
    ranked: list[tuple[str, str, int | None]] = [(result["path"], "target", None)]
    ranked.extend((node["id"], "matched", None) for node in result["matched_nodes"])
    ranked.extend((row["node"], "related", int(row.get("score", 0))) for row in result["related"])
    rows: list[dict] = []
    seen: set[str] = set()
    for raw_path, source, score in ranked:
        path = normalize_graph_path(raw_path)
        if path in seen or not file_like_node(path):
            continue
        resolved = (repo / path).resolve()
        if not is_relative_to(resolved, repo) or not resolved.is_file():
            continue
        seen.add(path)
        rows.append({"path": path, "source": source, "score": score})
        if len(rows) >= max_items:
            break
    return rows


def _file_sha256(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def read_context_ledger(ledger_path: Path, repo: Path) -> dict[str, list[tuple[int, int]]]:
    """Read source ranges previously emitted for this repository."""
    if not ledger_path.exists():
        return {}
    key = repo_usage_key(repo)
    seen: dict[str, list[tuple[int, int]]] = defaultdict(list)
    current_digests: dict[str, str | None] = {}
    try:
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return {}
    for line in lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if (
            not isinstance(record, dict)
            or record.get("schema") != CONTEXT_LEDGER_SCHEMA
            or record.get("repo_key") != key
        ):
            continue
        for item in record.get("ranges", []):
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            start = item.get("start")
            end = item.get("end")
            expected_digest = item.get("sha256")
            if (
                isinstance(path, str)
                and isinstance(start, int)
                and isinstance(end, int)
                and isinstance(expected_digest, str)
                and 1 <= start <= end
            ):
                resolved = (repo.resolve() / path).resolve()
                if not is_relative_to(resolved, repo.resolve()) or not resolved.is_file():
                    continue
                current_digest = current_digests.setdefault(path, _file_sha256(resolved))
                if current_digest == expected_digest:
                    seen[path].append((start, end))
    return dict(seen)


def _unseen_line_numbers(
    line_count: int,
    seen_ranges: Sequence[tuple[int, int]],
    limit: int,
) -> list[int]:
    if limit <= 0:
        return []
    seen = [False] * line_count
    for start, end in seen_ranges:
        for index in range(max(1, start) - 1, min(line_count, end)):
            seen[index] = True
    return [index + 1 for index, was_seen in enumerate(seen) if not was_seen][:limit]


def _contiguous_ranges(numbers: Sequence[int]) -> list[tuple[int, int]]:
    if not numbers:
        return []
    ranges: list[tuple[int, int]] = []
    start = previous = numbers[0]
    for number in numbers[1:]:
        if number == previous + 1:
            previous = number
            continue
        ranges.append((start, previous))
        start = previous = number
    ranges.append((start, previous))
    return ranges


def _clip_context_line(line: str) -> tuple[str, bool]:
    if len(line) <= MAX_CONTEXT_LINE_CHARS:
        return line, False
    return f"{line[:MAX_CONTEXT_LINE_CHARS]}... <line clipped>", True


def build_context_bundle(
    repo: Path,
    result: dict,
    *,
    detail: str,
    line_budget: int,
    seen_ranges: dict[str, list[tuple[int, int]]] | None = None,
    max_items: int = 20,
) -> dict:
    """Build bounded source context from graph-ranked files."""
    if detail not in {"fold", "preview", "full"}:
        raise ValueError("detail must be one of: fold, preview, full")
    if line_budget <= 0:
        raise ValueError("line budget must be positive")
    repo = repo.resolve()
    candidates = context_candidate_rows(repo, result, max_items=max_items)
    bundle = {
        "schema": "agent_code_graph_context_v1",
        "path": result["path"],
        "detail": detail,
        "line_budget": line_budget,
        "candidate_count": len(candidates),
        "candidates": candidates,
        "sections": [],
        "emitted_line_count": 0,
        "files_emitted_count": 0,
        "skipped_seen_count": 0,
        "unreadable_count": 0,
        "clipped_line_count": 0,
        "symbol_query": result.get("query"),
        "symbol_matches": result.get("symbol_matches", []),
    }
    if detail == "fold":
        return bundle

    seen_ranges = seen_ranges or {}
    per_file_limit = (
        max(1, min(40, line_budget // max(1, len(candidates))))
        if detail == "preview"
        else line_budget
    )
    emitted_paths: set[str] = set()
    for candidate in candidates:
        remaining = line_budget - bundle["emitted_line_count"]
        if remaining <= 0:
            break
        path = candidate["path"]
        try:
            source_lines = (repo / path).read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError):
            bundle["unreadable_count"] += 1
            continue
        limit = min(remaining, per_file_limit) if detail == "preview" else remaining
        numbers: list[int] = []
        symbol_scoped = False
        if detail == "preview" and result.get("query"):
            file_symbols = [
                item for item in result_symbol_rows(result, path) if int(item.get("score") or 0) > 0
            ]
            symbol_scoped = bool(file_symbols)
            seen = seen_ranges.get(path, [])
            for symbol in file_symbols:
                preferred = list(
                    range(
                        max(1, int(symbol["start"]) - 2),
                        min(len(source_lines), int(symbol["end"]) + 2) + 1,
                    )
                )
                numbers.extend(
                    number
                    for number in preferred
                    if number not in numbers
                    and not any(start <= number <= end for start, end in seen)
                )
                if len(numbers) >= limit:
                    numbers = numbers[:limit]
                    break
        if not numbers and not symbol_scoped:
            numbers = _unseen_line_numbers(len(source_lines), seen_ranges.get(path, []), limit)
        if not numbers:
            if source_lines and seen_ranges.get(path):
                bundle["skipped_seen_count"] += 1
            continue
        for start, end in _contiguous_ranges(numbers):
            lines = []
            for number in range(start, end + 1):
                text, clipped = _clip_context_line(source_lines[number - 1])
                bundle["clipped_line_count"] += int(clipped)
                lines.append({"number": number, "text": text})
            bundle["sections"].append({"path": path, "start": start, "end": end, "lines": lines})
            bundle["emitted_line_count"] += len(lines)
        emitted_paths.add(path)
    bundle["files_emitted_count"] = len(emitted_paths)
    return bundle


def result_symbol_rows(result: dict, path: str) -> list[dict]:
    query = str(result.get("query") or "")
    rows = []
    for item in result.get("context_symbols", result.get("symbol_matches", [])):
        if item.get("path") != path:
            continue
        score = symbol_match_score(item, query)
        if score > 0:
            rows.append({**item, "score": score})
    return sorted(rows, key=lambda item: (-int(item["score"]), int(item["start"])))


def append_context_ledger(bundle: dict, ledger_path: Path, repo: Path) -> Path:
    """Append only emitted repository paths and line ranges, never source text."""
    ranges = []
    digests: dict[str, str | None] = {}
    for section in bundle.get("sections", []):
        path = section["path"]
        digest = digests.setdefault(path, _file_sha256(repo.resolve() / path))
        if digest is None:
            continue
        ranges.append(
            {
                "path": path,
                "start": section["start"],
                "end": section["end"],
                "sha256": digest,
            }
        )
    if not ranges:
        return ledger_path
    record = {
        "schema": CONTEXT_LEDGER_SCHEMA,
        "recorded_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "repo_key": repo_usage_key(repo),
        "ranges": ranges,
    }
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return ledger_path


def changed_scope(payload: dict, changed_paths: Sequence[str], *, max_items: int = 30) -> dict:
    normalized_paths = sorted(
        {normalize_graph_path(path) for path in changed_paths if path.strip()}
    )
    matched: dict[str, list[dict]] = {}
    candidates: set[str] = set()
    unmapped: list[str] = []
    for path in normalized_paths:
        path_candidates = candidate_nodes_for_path(payload, path)
        if not path_candidates:
            unmapped.append(path)
            continue
        candidates.update(path_candidates)
        matched[path] = [node_record(payload, node) for node in path_candidates]
    related = related_node_rows(payload, candidates, max_items=max_items)
    return {
        "changed_paths": normalized_paths,
        "matched": matched,
        "matched_nodes": [node_record(payload, node) for node in sorted(candidates)],
        "unmapped": unmapped,
        "related": related,
        "groups": group_related_rows(related),
        "validation_hints": validation_hints_for_paths(normalized_paths),
    }


def area_counts_for_paths(paths: Sequence[str]) -> Counter[str]:
    return Counter(area_for(normalize_graph_path(path)) for path in paths if path.strip())


def merge_risk(
    payload: dict,
    current_paths: Sequence[str],
    main_paths: Sequence[str],
    sibling_scopes: Sequence[dict],
    *,
    max_items: int = 20,
) -> dict:
    current = sorted({normalize_graph_path(path) for path in current_paths if path.strip()})
    main = sorted({normalize_graph_path(path) for path in main_paths if path.strip()})
    current_set = set(current)
    current_areas = area_counts_for_paths(current)
    main_areas = area_counts_for_paths(main)
    main_exact = sorted(current_set & set(main))
    main_area_overlap = sorted(set(current_areas) & set(main_areas))
    siblings = []
    for scope in sibling_scopes:
        sibling_paths = sorted(
            {normalize_graph_path(path) for path in scope.get("paths", []) if path.strip()}
        )
        sibling_areas = area_counts_for_paths(sibling_paths)
        exact = sorted(current_set & set(sibling_paths))
        areas = sorted(set(current_areas) & set(sibling_areas))
        if not sibling_paths and not scope.get("error"):
            continue
        siblings.append(
            {
                "label": scope.get("label") or "unknown",
                "changed_files_count": len(sibling_paths),
                "exact_overlap": exact[:max_items],
                "exact_overlap_count": len(exact),
                "area_overlap": areas[:max_items],
                "area_overlap_count": len(areas),
                "error": scope.get("error"),
            }
        )
    siblings = sorted(
        siblings,
        key=lambda item: (
            -item["exact_overlap_count"],
            -item["area_overlap_count"],
            item["label"],
        ),
    )[:max_items]
    scope = changed_scope(payload, current, max_items=max_items)
    validation_paths = sorted({*current, *main_exact})
    return {
        "current_changed_paths": current,
        "current_changed_files_count": len(current),
        "current_areas": dict(sorted(current_areas.items())),
        "main_changed_files_count": len(main),
        "main_exact_overlap": main_exact[:max_items],
        "main_exact_overlap_count": len(main_exact),
        "main_area_overlap": main_area_overlap[:max_items],
        "main_area_overlap_count": len(main_area_overlap),
        "siblings": siblings,
        "sibling_count": len(siblings),
        "worktrees_with_exact_overlap_count": sum(
            1 for item in siblings if item["exact_overlap_count"]
        ),
        "worktrees_with_area_overlap_count": sum(
            1 for item in siblings if item["area_overlap_count"]
        ),
        "total_sibling_exact_overlap_count": sum(item["exact_overlap_count"] for item in siblings),
        "current_scope": scope,
        "validation_hints": validation_hints_for_paths(validation_paths),
    }


def add_hint(hints: list[str], command: str) -> None:
    if command not in hints:
        hints.append(command)


def validation_hints_for_paths(paths: Sequence[str]) -> list[str]:
    hints: list[str] = []
    if not paths:
        return hints
    add_hint(hints, "git diff --check")
    for path in paths:
        if path == "AGENTS.md" or path.endswith(".md") or path.startswith("docs/"):
            add_hint(hints, "python3 scripts/audit_public_docs.py")
            add_hint(hints, "python3 scripts/check_active_docs.py")
            add_hint(hints, "python3 scripts/check_markdown_links.py")
        if path.startswith("scripts/agent_") or path.startswith("tests/test_agent_"):
            add_hint(
                hints,
                "python3 -m pytest -q tests/test_agent_code_graph.py tests/test_agent_preflight.py",
            )
        if path.startswith(("deploy/kubernetes/", "deploy/helm/")):
            add_hint(
                hints,
                "python3 -m pytest -q tests/test_kubernetes_packaging.py tests/test_deployment_readiness.py",
            )
            add_hint(hints, "scripts/helm-chart-smoke.sh")
        if path.startswith(("query_doctor/web/", "web/")):
            add_hint(
                hints,
                "python3 -m pytest -q tests/test_web_server.py tests/test_web_ui_home.py",
            )
        if path.startswith("query_doctor/optimizer/"):
            add_hint(
                hints,
                "python3 -m pytest -q tests/test_query_optimizer.py tests/test_optimizer_sql.py",
            )
        if path.startswith("query_doctor/report/"):
            add_hint(
                hints,
                "python3 -m pytest -q tests/test_report_sanitizer.py tests/test_web_ui_report.py",
            )
        if path.startswith("query_doctor/cm/"):
            add_hint(hints, "python3 -m pytest -q tests/test_cm_*")
        if path.startswith("query_doctor/impala/"):
            add_hint(hints, "python3 -m pytest -q tests/test_impala_* tests/test_metadata_*")
    return hints


def build_graph(
    repo: Path,
    *,
    include_docs: bool = True,
    include_symbols: bool = False,
    max_items: int = 20,
) -> dict:
    repo = repo.resolve()
    py_paths = iter_files(repo, PY_SUFFIXES)
    go_paths = iter_files(repo, GO_SUFFIXES)
    ts_paths = iter_files(repo, TS_SUFFIXES)
    doc_paths = iter_files(repo, DOC_SUFFIXES) if include_docs else []
    support_paths = iter_files(repo, (*SUPPORT_SUFFIXES, ""))
    graph_paths = [*py_paths, *go_paths, *ts_paths, *doc_paths, *support_paths]
    python_edges, symbols = extract_python_analysis(repo, py_paths, include_symbols=include_symbols)

    nodes = {rel(repo, path) for path in graph_paths}
    edges = [
        *python_edges,
        *extract_go_edges(repo, go_paths),
        *extract_ts_edges(repo, ts_paths),
        *extract_doc_edges(repo, doc_paths),
        *extract_file_reference_edges(repo, support_paths, graph_paths),
        *extract_chart_edges(repo, support_paths),
    ]
    edges.extend(infer_test_edges(repo, [*py_paths, *go_paths, *ts_paths], edges))
    edges = dedupe_edges(edges)
    for edge in edges:
        nodes.add(edge.source)
        nodes.add(edge.target)

    return {
        "schema": "agent_code_graph_v1",
        "repo": repo.name,
        "scope": {
            "python_files": len(py_paths),
            "python_symbols": len(symbols),
            "go_files": len(go_paths),
            "typescript_files": len(ts_paths),
            "markdown_files": len(doc_paths),
            "config_files": len([path for path in support_paths if path.suffix in CONFIG_SUFFIXES]),
            "script_files": len(
                [
                    path
                    for path in support_paths
                    if path.suffix in SCRIPT_SUFFIXES
                    or path.name in SPECIAL_FILENAMES
                    or (not path.suffix and rel(repo, path).startswith("scripts/"))
                ]
            ),
            "docs_included": include_docs,
        },
        "nodes": [
            {"id": node, "kind": node_kind(node), "area": area_for(node)} for node in sorted(nodes)
        ],
        "edges": [asdict(edge) for edge in edges],
        "symbols": [asdict(symbol) for symbol in symbols],
        "summary": summarize(nodes, edges, max_items=max_items),
    }


def render_summary(payload: dict) -> str:
    summary = payload["summary"]
    scope = payload["scope"]
    lines = [
        f"# Agent Code Graph: {payload['repo']}",
        "",
        "Local deterministic orientation map. Verify graph-derived leads against code and tests before relying on them.",
        "",
        "## Scope",
        f"- Python files: {scope['python_files']}",
        f"- Python symbols: {scope.get('python_symbols', 0)}",
        f"- Go files: {scope['go_files']}",
        f"- TypeScript/JavaScript files: {scope['typescript_files']}",
        f"- Markdown files: {scope['markdown_files']}",
        f"- Config/deploy files: {scope['config_files']}",
        f"- Shell/build files: {scope['script_files']}",
        f"- Nodes: {summary['node_count']}",
        f"- Edges: {summary['edge_count']}",
        f"- Components: {summary['component_count']}",
        "",
        "## Relations",
    ]
    for name, count in summary["relation_counts"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Confidence"])
    for name, count in summary["confidence_counts"].items():
        lines.append(f"- {name}: {count}")
    lines.extend(["", "## Top Nodes"])
    for item in summary["top_nodes"]:
        lines.append(
            f"- {item['node']}: degree={item['degree']} "
            f"in={item['inbound']} out={item['outbound']} area={item['area']}"
        )
    lines.extend(["", "## Top Cross-Area Edges"])
    for item in summary["top_area_edges"]:
        lines.append(f"- {item['source_area']} -> {item['target_area']}: {item['count']}")
    lines.extend(["", "## Top Test Targets"])
    for item in summary["top_test_targets"]:
        lines.append(f"- {item['target']}: tests={item['test_count']}")
    lines.extend(["", "## High-Degree Code Without Direct Test Edges"])
    for item in summary["high_degree_without_direct_tests"]:
        lines.append(
            f"- {item['node']}: degree={item['degree']} in={item['inbound']} out={item['outbound']}"
        )
    lines.extend(["", "## Entrypoints"])
    for item in summary["entrypoints"]:
        lines.append(f"- {item}")
    lines.append("")
    return "\n".join(lines)


def reason_text(row: dict) -> str:
    reasons = sorted({f"{item['relation']}:{item['direction']}" for item in row["reasons"]})
    return ", ".join(reasons[:4])


def selected_rows(
    rows: Sequence[dict], *, limit: int | None = None, prefer_non_hubs: bool = False
) -> list[dict]:
    visible = [row for row in rows if file_like_node(row["node"])]
    if prefer_non_hubs:
        non_hubs = [row for row in visible if not row.get("hub")]
        if non_hubs:
            visible = non_hubs
    return visible[:limit] if limit is not None else visible


def render_rows(
    rows: Sequence[dict],
    *,
    empty: str = "- <none>",
    limit: int | None = None,
    prefer_non_hubs: bool = False,
) -> list[str]:
    visible = selected_rows(rows, limit=limit, prefer_non_hubs=prefer_non_hubs)
    if not visible:
        return [empty]
    result = []
    for row in visible:
        hub = ", hub" if row.get("hub") else ""
        result.append(
            f"- {row['node']} ({row['kind']}{hub}, area={row['area']}, "
            f"degree={row['degree']}; {reason_text(row)})"
        )
    return result


def render_validation_hints(hints: Sequence[str]) -> list[str]:
    if not hints:
        return ["- <none>"]
    return [f"- `{hint}`" for hint in hints]


def render_compact_rows(rows: Sequence[dict], *, limit: int = 5) -> list[str]:
    return render_rows(rows, limit=limit, prefer_non_hubs=True)


def render_compact_changed_scope(result: dict) -> str:
    groups = result["groups"]
    read_first = [*groups["code"], *groups["entrypoints"], *groups["support"]]
    lines = [
        "# Agent Code Graph Changed Scope",
        "",
        "Compact graph-derived hint. Verify against current code and tests.",
        "",
        "## Changed",
    ]
    lines.extend(f"- {path}" for path in result["changed_paths"][:8])
    if len(result["changed_paths"]) > 8:
        lines.append(f"- ... {len(result['changed_paths']) - 8} more")
    lines.extend(["", "## Read First", *render_compact_rows(read_first)])
    lines.extend(["", "## Likely Tests", *render_compact_rows(groups["tests"])])
    lines.extend(["", "## Validation Hints", *render_validation_hints(result["validation_hints"])])
    if result["unmapped"]:
        lines.extend(["", "## Unmapped", *[f"- {path}" for path in result["unmapped"][:8]]])
    lines.append("")
    return "\n".join(lines)


def render_compact_explain(result: dict) -> str:
    groups = result["groups"]
    support = [*groups["entrypoints"], *groups["support"]]
    lines = [
        f"# Agent Code Graph Explain: {result['path']}",
        "",
        "Compact graph-derived hint. Verify against current code and tests.",
    ]
    if result.get("query"):
        lines.extend(["", f"Symbol query: `{result['query']}`", "", "## Symbol Matches"])
        matches = result.get("symbol_matches", [])
        lines.extend(
            f"- {item['path']}:{item['start']}-{item['end']} {item['kind']} "
            f"{item['name']} (score={item['score']})"
            for item in matches[:5]
        )
    lines.extend(["", "## Matched"])
    if result["matched_nodes"]:
        lines.extend(
            f"- {node['id']} ({node['kind']}, area={node['area']})"
            for node in result["matched_nodes"]
        )
    else:
        lines.append("- <none>")
    lines.extend(["", "## Related Code", *render_compact_rows(groups["code"])])
    lines.extend(["", "## Likely Tests", *render_compact_rows(groups["tests"])])
    lines.extend(["", "## Support", *render_compact_rows(support)])
    lines.extend(["", "## Validation Hints", *render_validation_hints(result["validation_hints"])])
    lines.append("")
    return "\n".join(lines)


def render_context_bundle(bundle: dict) -> str:
    lines = [
        f"# Agent Code Graph Context: {bundle['path']}",
        "",
        "Graph-ranked repository context. Verify important behavior in current code and tests.",
        "",
        f"- Detail: {bundle['detail']}",
        f"- Source-line budget: {bundle['line_budget']}",
        f"- Source lines emitted: {bundle['emitted_line_count']}",
        f"- Candidate files: {bundle['candidate_count']}",
        "",
        "## Ranked Paths",
    ]
    if bundle.get("symbol_query"):
        lines.insert(4, f"- Symbol query: `{bundle['symbol_query']}`")
    if bundle["candidates"]:
        for index, candidate in enumerate(bundle["candidates"], start=1):
            score = candidate.get("score")
            score_text = f", score={score}" if score is not None else ""
            lines.append(f"{index}. {candidate['path']} ({candidate['source']}{score_text})")
    else:
        lines.append("- <none>")
    if bundle["detail"] == "fold":
        lines.extend(
            [
                "",
                "Fold mode emits ranked paths only. Use preview or full when source text is needed.",
                "",
            ]
        )
        return "\n".join(lines)
    lines.extend(["", "## Source Context"])
    if not bundle["sections"]:
        lines.append("- <none; the selected ranges may already be present in the session ledger>")
    for section in bundle["sections"]:
        lines.extend(
            [
                "",
                f"### {section['path']} (lines {section['start']}-{section['end']})",
                "",
            ]
        )
        lines.extend(f"{item['number']:>6} | {item['text']}" for item in section["lines"])
    if bundle["clipped_line_count"]:
        lines.extend(
            [
                "",
                f"Long source lines clipped: {bundle['clipped_line_count']}",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def render_explain(result: dict) -> str:
    lines = [
        f"# Agent Code Graph Explain: {result['path']}",
        "",
        "Graph-derived read-scope hint. Verify edges against current code and tests before relying on them.",
    ]
    if result.get("query"):
        lines.extend(["", f"Symbol query: `{result['query']}`", "", "## Symbol Matches"])
        lines.extend(
            f"- {item['path']}:{item['start']}-{item['end']} {item['kind']} "
            f"{item['name']} (score={item['score']})"
            for item in result.get("symbol_matches", [])
        )
    lines.extend(["", "## Matched Nodes"])
    if result["matched_nodes"]:
        for node in result["matched_nodes"]:
            lines.append(f"- {node['id']} ({node['kind']}, area={node['area']})")
    else:
        lines.append("- <none>")
    lines.extend(["", "## Direct Edges"])
    if result["direct_edges"]:
        for edge in result["direct_edges"]:
            lines.append(
                f"- {edge['source']} -> {edge['target']} ({edge['relation']}, {edge['confidence']})"
            )
    else:
        lines.append("- <none>")
    groups = result["groups"]
    lines.extend(["", "## Likely Tests", *render_rows(groups["tests"])])
    lines.extend(["", "## Related Code", *render_rows(groups["code"])])
    lines.extend(["", "## Related Docs", *render_rows(groups["docs"])])
    lines.extend(
        [
            "",
            "## Entrypoints And Support",
            *render_rows([*groups["entrypoints"], *groups["support"]]),
        ]
    )
    lines.extend(["", "## Validation Hints", *render_validation_hints(result["validation_hints"])])
    lines.append("")
    return "\n".join(lines)


def render_changed_scope(result: dict) -> str:
    lines = [
        "# Agent Code Graph Changed Scope",
        "",
        "Graph-derived read-scope hint for changed files. Verify edges against current code and tests before relying on them.",
        "",
        "## Changed Files",
    ]
    if result["changed_paths"]:
        for path in result["changed_paths"]:
            match_count = len(result["matched"].get(path, []))
            suffix = f"matched_nodes={match_count}" if match_count else "unmapped"
            lines.append(f"- {path} ({suffix})")
    else:
        lines.append("- <none>")
    lines.extend(["", "## Matched Graph Nodes"])
    if result["matched_nodes"]:
        for node in result["matched_nodes"]:
            lines.append(f"- {node['id']} ({node['kind']}, area={node['area']})")
    else:
        lines.append("- <none>")
    groups = result["groups"]
    lines.extend(
        [
            "",
            "## Read First",
            *render_rows([*groups["code"], *groups["entrypoints"], *groups["support"]]),
        ]
    )
    lines.extend(["", "## Likely Tests", *render_rows(groups["tests"])])
    lines.extend(["", "## Related Docs", *render_rows(groups["docs"])])
    lines.extend(["", "## Validation Hints", *render_validation_hints(result["validation_hints"])])
    lines.extend(["", "## Unmapped Changed Files"])
    if result["unmapped"]:
        lines.extend(f"- {path}" for path in result["unmapped"])
    else:
        lines.append("- <none>")
    lines.append("")
    return "\n".join(lines)


def render_count_map(items: dict[str, int], *, limit: int = 8) -> list[str]:
    if not items:
        return ["- <none>"]
    rows = sorted(items.items(), key=lambda item: (-item[1], item[0]))[:limit]
    return [f"- {name}: {count}" for name, count in rows]


def render_merge_risk(result: dict) -> str:
    lines = [
        "# Agent Code Graph Merge Risk",
        "",
        "Graph-derived pre-merge hint. Exact overlaps are conflict risks; area overlaps are coordination risks.",
        "",
        "## Current Branch",
        f"- Changed files: {result['current_changed_files_count']}",
        "",
        "## Current Areas",
        *render_count_map(result["current_areas"]),
        "",
        "## Main Drift",
        f"- Files changed on base since branch point: {result['main_changed_files_count']}",
        f"- Exact overlaps with current branch: {result['main_exact_overlap_count']}",
        f"- Area overlaps with current branch: {result['main_area_overlap_count']}",
    ]
    if result["main_exact_overlap"]:
        lines.extend(["", "### Main Exact Overlaps"])
        lines.extend(f"- {path}" for path in result["main_exact_overlap"])
    if result["main_area_overlap"]:
        lines.extend(["", "### Main Area Overlaps"])
        lines.extend(f"- {area}" for area in result["main_area_overlap"])
    lines.extend(["", "## Sibling Worktrees"])
    if result["siblings"]:
        for sibling in result["siblings"]:
            lines.append(
                f"- {sibling['label']}: files={sibling['changed_files_count']} "
                f"exact={sibling['exact_overlap_count']} areas={sibling['area_overlap_count']}"
            )
            if sibling.get("error"):
                lines.append(f"  error: {sibling['error']}")
            if sibling["exact_overlap"]:
                lines.extend(f"  exact: {path}" for path in sibling["exact_overlap"])
            elif sibling["area_overlap"]:
                lines.extend(f"  area: {area}" for area in sibling["area_overlap"])
    else:
        lines.append("- <none>")
    scope = result["current_scope"]
    groups = scope["groups"]
    lines.extend(
        [
            "",
            "## Read Before Merge",
            *render_compact_rows([*groups["code"], *groups["entrypoints"], *groups["support"]]),
            "",
            "## Likely Tests",
            *render_compact_rows(groups["tests"]),
            "",
            "## Validation Hints",
            *render_validation_hints(result["validation_hints"]),
            "",
        ]
    )
    return "\n".join(lines)


def default_out_dir(repo: Path) -> Path:
    return Path(tempfile.gettempdir()) / f"{repo.resolve().name}-agent-code-graph"


def safe_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value.strip()).strip("-._")
    return slug or "repo"


def git_common_dir(repo: Path) -> Path:
    result = subprocess.run(
        ["git", "rev-parse", "--git-common-dir"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return repo.resolve()
    raw_path = Path(result.stdout.strip())
    if not raw_path.is_absolute():
        raw_path = repo / raw_path
    return raw_path.resolve()


def repo_usage_key(repo: Path) -> str:
    common_dir = git_common_dir(repo)
    repo_name = common_dir.parent.name if common_dir.name == ".git" else repo.resolve().name
    digest = hashlib.sha256(str(common_dir).encode("utf-8")).hexdigest()[:12]
    return f"{safe_slug(repo_name)}-{digest}"


def default_usage_root() -> Path:
    return Path(tempfile.gettempdir()) / USAGE_STATE_DIR


def default_usage_path(repo: Path) -> Path:
    return default_usage_root() / repo_usage_key(repo) / USAGE_LOG_NAME


def validate_output_dir(repo: Path, out_dir: Path, allow_repo_output: bool) -> None:
    repo = repo.resolve()
    out_dir = out_dir.resolve()
    if is_relative_to(out_dir, repo) and not allow_repo_output:
        raise ValueError(
            "refusing to write generated graph output inside the repository; "
            "use an external --out path or pass --allow-repo-output for an ignored local path"
        )
    if is_relative_to(out_dir, repo) and allow_repo_output:
        relative = out_dir.relative_to(repo).as_posix()
        if relative != "tmp/agent-code-graph" and not relative.startswith("tmp/agent-code-graph/"):
            raise ValueError(
                "repo-local graph output is limited to tmp/agent-code-graph/; "
                "use an external --out path for other locations"
            )


def validate_usage_log_path(repo: Path, usage_path: Path) -> None:
    repo = repo.resolve()
    usage_path = usage_path.resolve()
    if not is_relative_to(usage_path, repo):
        return
    relative = usage_path.relative_to(repo).as_posix()
    if relative.startswith(f"{USAGE_DIR.as_posix()}/"):
        return
    raise ValueError(
        "repo-local usage logs are limited to tmp/agent-code-graph/; "
        "use an external --usage-log path for other locations"
    )


def validate_context_ledger_path(repo: Path, ledger_path: Path) -> None:
    repo = repo.resolve()
    ledger_path = ledger_path.resolve()
    if not is_relative_to(ledger_path, repo):
        return
    relative = ledger_path.relative_to(repo).as_posix()
    if relative.startswith(f"{USAGE_DIR.as_posix()}/"):
        return
    raise ValueError(
        "repo-local context ledgers are limited to tmp/agent-code-graph/; "
        "use an external --context-ledger path for other locations"
    )


def write_outputs(payload: dict, out_dir: Path) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / "SUMMARY.md"
    graph_path = out_dir / "graph.json"
    summary_path.write_text(render_summary(payload), encoding="utf-8")
    graph_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path, graph_path


def build_usage_record(
    repo: Path,
    *,
    mode: str,
    compact: bool,
    runtime_ms: int,
    payload: dict | None = None,
    result: dict | None = None,
    output_files_count: int = 0,
) -> dict:
    summary = (payload or {}).get("summary", {})
    scope = (payload or {}).get("scope", {})
    record = {
        "schema": USAGE_SCHEMA,
        "recorded_at_utc": datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "repo": repo.resolve().name,
        "mode": mode,
        "compact": bool(compact),
        "runtime_ms": max(0, int(runtime_ms)),
        "node_count": int(summary.get("node_count", 0) or 0),
        "edge_count": int(summary.get("edge_count", 0) or 0),
        "docs_included": bool(scope.get("docs_included", False)),
    }
    if mode == "changed":
        result = result or {}
        groups = result.get("groups", {})
        record.update(
            {
                "changed_files_count": len(result.get("changed_paths", [])),
                "matched_paths_count": len(result.get("matched", {})),
                "matched_nodes_count": len(result.get("matched_nodes", [])),
                "related_count": len(result.get("related", [])),
                "likely_tests_count": len(groups.get("tests", [])),
                "validation_hints_count": len(result.get("validation_hints", [])),
                "unmapped_count": len(result.get("unmapped", [])),
            }
        )
    elif mode == "explain":
        result = result or {}
        groups = result.get("groups", {})
        record.update(
            {
                "matched_nodes_count": len(result.get("matched_nodes", [])),
                "direct_edges_count": len(result.get("direct_edges", [])),
                "related_count": len(result.get("related", [])),
                "likely_tests_count": len(groups.get("tests", [])),
                "validation_hints_count": len(result.get("validation_hints", [])),
                "unmapped": bool(result.get("unmapped", False)),
            }
        )
    elif mode == "context":
        result = result or {}
        record.update(
            {
                "detail": str(result.get("detail", "unknown")),
                "line_budget": int(result.get("line_budget", 0) or 0),
                "emitted_line_count": int(result.get("emitted_line_count", 0) or 0),
                "candidate_count": int(result.get("candidate_count", 0) or 0),
                "files_emitted_count": int(result.get("files_emitted_count", 0) or 0),
                "skipped_seen_count": int(result.get("skipped_seen_count", 0) or 0),
            }
        )
    elif mode == "merge-risk":
        result = result or {}
        record.update(
            {
                "changed_files_count": int(result.get("current_changed_files_count", 0) or 0),
                "main_changed_files_count": int(result.get("main_changed_files_count", 0) or 0),
                "main_exact_overlap_count": int(result.get("main_exact_overlap_count", 0) or 0),
                "main_area_overlap_count": int(result.get("main_area_overlap_count", 0) or 0),
                "sibling_count": int(result.get("sibling_count", 0) or 0),
                "worktrees_with_exact_overlap_count": int(
                    result.get("worktrees_with_exact_overlap_count", 0) or 0
                ),
                "worktrees_with_area_overlap_count": int(
                    result.get("worktrees_with_area_overlap_count", 0) or 0
                ),
                "total_sibling_exact_overlap_count": int(
                    result.get("total_sibling_exact_overlap_count", 0) or 0
                ),
                "validation_hints_count": len(result.get("validation_hints", [])),
            }
        )
    else:
        record["output_files_count"] = max(0, int(output_files_count))
    return record


def append_usage_record(record: dict, usage_path: Path) -> Path:
    usage_path.parent.mkdir(parents=True, exist_ok=True)
    with usage_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    return usage_path


def read_usage_records(usage_path: Path) -> list[dict]:
    if not usage_path.exists():
        return []
    records: list[dict] = []
    for line in usage_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict) and record.get("schema") == USAGE_SCHEMA:
            records.append(record)
    return records


def _average(records: Sequence[dict], key: str) -> float | None:
    values = [record[key] for record in records if isinstance(record.get(key), (int, float))]
    if not values:
        return None
    return round(sum(values) / len(values), 1)


def _parse_utc_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    normalized = value.removesuffix("Z") + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def local_main_merge_event_times(repo: Path) -> list[datetime]:
    result = subprocess.run(
        [
            "git",
            "reflog",
            "show",
            "--date=iso-strict",
            "--format=%gd%x00%gs",
            "refs/heads/main",
        ],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    events: list[datetime] = []
    for line in result.stdout.splitlines():
        if "\x00" not in line:
            continue
        selector, subject = line.split("\x00", 1)
        if "merge" not in subject.lower():
            continue
        match = re.search(r"\@\{([^}]+)\}", selector)
        if not match:
            continue
        timestamp = _parse_utc_timestamp(match.group(1))
        if timestamp is not None:
            events.append(timestamp)
    return sorted(events)


def _daily_usage(records: Sequence[dict]) -> list[dict]:
    buckets: dict[str, list[dict]] = defaultdict(list)
    for record in records:
        timestamp = _parse_utc_timestamp(record.get("recorded_at_utc"))
        if timestamp is None:
            continue
        buckets[timestamp.date().isoformat()].append(record)
    days: list[dict] = []
    for day, day_records in sorted(buckets.items()):
        mode_counts = Counter(str(record.get("mode", "unknown")) for record in day_records)
        runtimes = [
            int(record["runtime_ms"])
            for record in day_records
            if isinstance(record.get("runtime_ms"), int)
        ]
        days.append(
            {
                "date": day,
                "record_count": len(day_records),
                "mode_counts": dict(sorted(mode_counts.items())),
                "compact_count": sum(1 for record in day_records if record.get("compact") is True),
                "avg_runtime_ms": round(sum(runtimes) / len(runtimes), 1) if runtimes else None,
            }
        )
    return days


def _merge_risk_coverage(
    records: Sequence[dict],
    merge_event_times: Sequence[datetime],
    *,
    window_hours: int,
) -> dict:
    record_times = sorted(
        timestamp
        for record in records
        for timestamp in [_parse_utc_timestamp(record.get("recorded_at_utc"))]
        if timestamp is not None
    )
    merge_risk_times = sorted(
        timestamp
        for record in records
        if record.get("mode") == "merge-risk"
        for timestamp in [_parse_utc_timestamp(record.get("recorded_at_utc"))]
        if timestamp is not None
    )
    first_record_time = record_times[0] if record_times else None
    scoped_merge_events = [
        event_time.astimezone(timezone.utc)
        for event_time in merge_event_times
        if first_record_time is not None
        and event_time.astimezone(timezone.utc) >= first_record_time
    ]
    window = timedelta(hours=window_hours)
    covered = 0
    for event_time in scoped_merge_events:
        if any(event_time - window <= run_time <= event_time for run_time in merge_risk_times):
            covered += 1
    total = len(scoped_merge_events)
    return {
        "schema": "agent_code_graph_merge_risk_coverage_v1",
        "window_hours": window_hours,
        "since_recorded_at_utc": first_record_time.isoformat().replace("+00:00", "Z")
        if first_record_time is not None
        else None,
        "local_main_merge_events": total,
        "covered_events": covered,
        "coverage_percent": round((covered / total) * 100, 1) if total else None,
        "merge_risk_runs": len(merge_risk_times),
    }


def summarize_usage(
    records: Sequence[dict],
    *,
    merge_event_times: Sequence[datetime] | None = None,
    merge_window_hours: int = 6,
) -> dict:
    accepted = [record for record in records if record.get("schema") == USAGE_SCHEMA]
    mode_counts = Counter(str(record.get("mode", "unknown")) for record in accepted)
    runtimes = [
        int(record["runtime_ms"])
        for record in accepted
        if isinstance(record.get("runtime_ms"), int)
    ]
    return {
        "schema": "agent_code_graph_usage_summary_v1",
        "record_count": len(accepted),
        "mode_counts": dict(sorted(mode_counts.items())),
        "compact_count": sum(1 for record in accepted if record.get("compact") is True),
        "latest_recorded_at_utc": max(
            (
                str(record.get("recorded_at_utc"))
                for record in accepted
                if record.get("recorded_at_utc")
            ),
            default=None,
        ),
        "avg_runtime_ms": round(sum(runtimes) / len(runtimes), 1) if runtimes else None,
        "max_runtime_ms": max(runtimes) if runtimes else None,
        "avg_changed_files": _average(accepted, "changed_files_count"),
        "avg_related": _average(accepted, "related_count"),
        "avg_unmapped": _average(accepted, "unmapped_count"),
        "avg_validation_hints": _average(accepted, "validation_hints_count"),
        "avg_likely_tests": _average(accepted, "likely_tests_count"),
        "avg_main_exact_overlaps": _average(accepted, "main_exact_overlap_count"),
        "avg_main_area_overlaps": _average(accepted, "main_area_overlap_count"),
        "avg_sibling_exact_overlaps": _average(accepted, "total_sibling_exact_overlap_count"),
        "avg_worktrees_with_exact_overlap": _average(
            accepted, "worktrees_with_exact_overlap_count"
        ),
        "daily": _daily_usage(accepted),
        "merge_risk_coverage": _merge_risk_coverage(
            accepted,
            merge_event_times or [],
            window_hours=merge_window_hours,
        ),
    }


def display_usage_path(usage_path: Path, repo: Path | None) -> str:
    resolved = usage_path.resolve()
    if repo is not None:
        repo = repo.resolve()
        if is_relative_to(resolved, repo):
            return resolved.relative_to(repo).as_posix()
    usage_root = default_usage_root().resolve()
    if is_relative_to(resolved, usage_root):
        return f"local-state/{resolved.relative_to(usage_root).as_posix()}"
    return "<external>"


def render_usage_summary(
    summary: dict,
    *,
    usage_path: Path | None = None,
    repo: Path | None = None,
) -> str:
    lines = [
        "# Agent Code Graph Usage Summary",
        "",
        "Safe aggregate local telemetry. It records counts and runtime only, not file paths or graph output.",
        "",
    ]
    if usage_path is not None:
        lines.append(f"- Usage log: `{display_usage_path(usage_path, repo)}`")
    lines.extend(
        [
            f"- Records: {summary['record_count']}",
            f"- Compact runs: {summary['compact_count']}",
            f"- Latest: {summary['latest_recorded_at_utc'] or '<none>'}",
            "",
            "## Modes",
        ]
    )
    if summary["mode_counts"]:
        for mode, count in summary["mode_counts"].items():
            lines.append(f"- {mode}: {count}")
    else:
        lines.append("- <none>")
    lines.extend(["", "## Daily Activity"])
    if summary["daily"]:
        for day in summary["daily"]:
            mode_bits = ", ".join(f"{mode}: {count}" for mode, count in day["mode_counts"].items())
            runtime = day["avg_runtime_ms"]
            runtime_text = "<none>" if runtime is None else str(runtime)
            lines.append(
                f"- {day['date']}: records {day['record_count']}; "
                f"compact {day['compact_count']}; modes {mode_bits}; "
                f"avg runtime ms {runtime_text}"
            )
    else:
        lines.append("- <none>")
    coverage = summary["merge_risk_coverage"]
    lines.extend(["", "## Merge Risk Before Merge"])
    if coverage["local_main_merge_events"]:
        lines.append(
            "- Local main merge events with prior merge-risk run: "
            f"{coverage['covered_events']}/{coverage['local_main_merge_events']} "
            f"({coverage['coverage_percent']}%)"
        )
        lines.append(f"- Window hours: {coverage['window_hours']}")
        lines.append(f"- Since first usage record: {coverage['since_recorded_at_utc']}")
        lines.append(f"- Merge-risk runs considered: {coverage['merge_risk_runs']}")
        lines.append(
            "- Source: local `main` reflog aggregate; branch names and paths are not shown."
        )
    else:
        lines.append("- <none>")
        lines.append("- Source: local `main` reflog aggregate; no merge events found.")
    lines.extend(["", "## Runtime"])
    if summary["avg_runtime_ms"] is None:
        lines.append("- <none>")
    else:
        lines.append(f"- Average runtime ms: {summary['avg_runtime_ms']}")
        lines.append(f"- Max runtime ms: {summary['max_runtime_ms']}")
    lines.extend(["", "## Scope Quality"])
    quality_rows = [
        ("Average changed files", summary["avg_changed_files"]),
        ("Average related nodes", summary["avg_related"]),
        ("Average unmapped files", summary["avg_unmapped"]),
        ("Average validation hints", summary["avg_validation_hints"]),
        ("Average likely tests", summary["avg_likely_tests"]),
        ("Average main exact overlaps", summary["avg_main_exact_overlaps"]),
        ("Average main area overlaps", summary["avg_main_area_overlaps"]),
        ("Average sibling exact overlaps", summary["avg_sibling_exact_overlaps"]),
        (
            "Average sibling worktrees with exact overlap",
            summary["avg_worktrees_with_exact_overlap"],
        ),
    ]
    visible_rows = [(label, value) for label, value in quality_rows if value is not None]
    if visible_rows:
        for label, value in visible_rows:
            lines.append(f"- {label}: {value}")
    else:
        lines.append("- <none>")
    lines.append("")
    return "\n".join(lines)
