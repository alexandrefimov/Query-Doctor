#!/usr/bin/env python3
"""Build a compact local code graph for agent orientation."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from agent_code_graph_core import (  # noqa: E402
    append_context_ledger,
    append_usage_record,
    build_context_bundle,
    build_usage_record,
    build_graph,
    changed_scope,
    default_out_dir,
    default_usage_path,
    display_usage_path,  # noqa: F401 - re-exported for tests and agent helpers.
    explain_path,
    explain_symbol,
    is_relative_to,  # noqa: F401 - re-exported for tests and agent helpers.
    merge_risk,
    local_main_merge_event_times,
    read_usage_records,
    read_context_ledger,
    render_changed_scope,
    render_compact_changed_scope,
    render_compact_explain,
    render_context_bundle,
    render_explain,
    render_merge_risk,
    render_usage_summary,
    summarize_usage,
    validation_hints_for_paths,  # noqa: F401 - re-exported for tests and agent helpers.
    validate_output_dir,
    validate_context_ledger_path,
    validate_usage_log_path,
    write_outputs,
)


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path("."), help="repository root")
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="output directory; defaults to the system temporary directory",
    )
    parser.add_argument("--no-docs", action="store_true", help="skip Markdown link edges")
    parser.add_argument("--max-items", type=int, default=20, help="items per summary section")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--changed",
        action="store_true",
        help="print a graph-derived read-scope for git changes instead of writing graph files",
    )
    mode.add_argument(
        "--explain",
        metavar="PATH",
        help="print graph neighbors and read-scope hints for one repository path",
    )
    mode.add_argument(
        "--symbol",
        metavar="NAME",
        help="find a Python class, function, or method and print its graph-ranked scope",
    )
    mode.add_argument(
        "--merge-risk",
        action="store_true",
        help="print pre-merge overlap risk against base and sibling worktrees",
    )
    parser.add_argument(
        "--base",
        help="with --changed, also include committed files changed since this git ref",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="with --changed, --explain, or --symbol, print a shorter read-scope hint",
    )
    parser.add_argument(
        "--context",
        action="store_true",
        help="with --explain or --symbol, emit bounded source context from graph-ranked files",
    )
    parser.add_argument(
        "--detail",
        choices=("fold", "preview", "full"),
        default="preview",
        help="with --context, choose ranked paths only, short excerpts, or full files",
    )
    parser.add_argument(
        "--line-budget",
        type=int,
        default=200,
        help="with --context, maximum source lines to emit (default: 200)",
    )
    parser.add_argument(
        "--context-ledger",
        type=Path,
        default=None,
        help="with --context, skip emitted ranges and append new ranges to this JSONL ledger",
    )
    parser.add_argument(
        "--allow-repo-output",
        action="store_true",
        help="allow --out inside the repository, limited to tmp/agent-code-graph/",
    )
    parser.add_argument(
        "--record-usage",
        action="store_true",
        default=None,
        help="append safe aggregate usage metrics; enabled by default for graph runs",
    )
    parser.add_argument(
        "--no-record-usage",
        action="store_false",
        dest="record_usage",
        help="disable safe aggregate usage recording for this run",
    )
    parser.add_argument(
        "--usage-summary",
        action="store_true",
        help="print aggregate usage metrics and exit",
    )
    parser.add_argument(
        "--usage-log",
        type=Path,
        default=None,
        help="usage log path; defaults to shared local state outside the repository",
    )
    return parser.parse_args(argv)


def repo_relative_path(repo: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if path.is_absolute():
        try:
            return path.resolve().relative_to(repo).as_posix()
        except ValueError:
            return raw_path
    return raw_path


def git_changed_paths(repo: Path, base: str | None) -> list[str]:
    commands = []
    if base:
        commands.append(["git", "diff", "--name-only", "--diff-filter=ACMR", f"{base}...HEAD"])
    commands.extend(
        [
            ["git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD"],
            ["git", "ls-files", "--others", "--exclude-standard"],
        ]
    )
    paths: set[str] = set()
    for command in commands:
        result = subprocess.run(command, cwd=repo, text=True, capture_output=True, check=False)
        if result.returncode != 0:
            detail = result.stderr.strip() or "git command failed"
            raise RuntimeError(detail)
        paths.update(line.strip() for line in result.stdout.splitlines() if line.strip())
    return sorted(paths)


def git_diff_paths(repo: Path, revspec: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=ACMR", revspec],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git diff failed"
        raise RuntimeError(detail)
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip())


def git_main_drift_paths(repo: Path, base: str) -> list[str]:
    return git_diff_paths(repo, f"HEAD...{base}")


def git_worktrees(repo: Path) -> list[dict]:
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git worktree list failed"
        raise RuntimeError(detail)
    worktrees: list[dict] = []
    current: dict | None = None
    for line in result.stdout.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = {"path": line.removeprefix("worktree ").strip()}
        elif current is not None and line.startswith("branch "):
            branch = line.removeprefix("branch ").strip()
            current["branch"] = branch.removeprefix("refs/heads/")
        elif current is not None and line == "detached":
            current["detached"] = True
        elif current is not None and line == "prunable":
            current["prunable"] = True
    if current is not None:
        worktrees.append(current)
    return worktrees


def sibling_worktree_scopes(repo: Path, base: str) -> list[dict]:
    current_repo = repo.resolve()
    scopes: list[dict] = []
    for item in git_worktrees(repo):
        raw_path = item.get("path")
        if not raw_path:
            continue
        path = Path(raw_path).resolve()
        if path == current_repo or item.get("prunable"):
            continue
        label = item.get("branch") or path.name
        try:
            paths = git_changed_paths(path, base)
        except RuntimeError as exc:
            scopes.append({"label": label, "paths": [], "error": str(exc)})
            continue
        if paths:
            scopes.append({"label": label, "paths": paths})
    return scopes


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo = args.repo.resolve()
    if not repo.exists():
        print(f"error: repo does not exist: {repo}", file=sys.stderr)
        return 2
    if args.context and not (args.explain or args.symbol):
        print("error: --context requires --explain PATH or --symbol NAME", file=sys.stderr)
        return 2
    if args.context_ledger is not None and not args.context:
        print("error: --context-ledger requires --context", file=sys.stderr)
        return 2
    if args.line_budget <= 0:
        print("error: --line-budget must be positive", file=sys.stderr)
        return 2
    usage_path = args.usage_log.resolve() if args.usage_log else default_usage_path(repo)
    try:
        validate_usage_log_path(repo, usage_path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    ledger_path = args.context_ledger.resolve() if args.context_ledger else None
    if ledger_path is not None:
        try:
            validate_context_ledger_path(repo, ledger_path)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.usage_summary:
        records = read_usage_records(usage_path)
        summary = summarize_usage(records, merge_event_times=local_main_merge_event_times(repo))
        print(render_usage_summary(summary, usage_path=usage_path, repo=repo), end="")
        return 0
    started_at = time.monotonic()
    payload = build_graph(
        repo,
        include_docs=not args.no_docs,
        include_symbols=bool(args.symbol),
        max_items=args.max_items,
    )
    record_usage_enabled = args.record_usage is not False
    record_usage_strict = args.record_usage is True or args.usage_log is not None

    def record_usage(mode: str, *, result: dict | None = None, output_files_count: int = 0) -> bool:
        if not record_usage_enabled:
            return True
        record = build_usage_record(
            repo,
            mode=mode,
            compact=args.compact,
            runtime_ms=int((time.monotonic() - started_at) * 1000),
            payload=payload,
            result=result,
            output_files_count=output_files_count,
        )
        try:
            append_usage_record(record, usage_path)
        except OSError as exc:
            detail = f"unable to record usage: {exc}"
            if record_usage_strict:
                print(f"error: {detail}", file=sys.stderr)
                return False
            print(f"warning: {detail}", file=sys.stderr)
        return True

    if args.explain or args.symbol:
        result = (
            explain_path(
                payload,
                repo_relative_path(repo, args.explain),
                max_items=args.max_items,
            )
            if args.explain
            else explain_symbol(payload, args.symbol, max_items=args.max_items)
        )
        if args.symbol and result.get("unmapped"):
            print(f"error: symbol not found: {args.symbol}", file=sys.stderr)
            return 2
        if args.context:
            seen_ranges = read_context_ledger(ledger_path, repo) if ledger_path else None
            context = build_context_bundle(
                repo,
                result,
                detail=args.detail,
                line_budget=args.line_budget,
                seen_ranges=seen_ranges,
                max_items=args.max_items,
            )
            if ledger_path is not None:
                try:
                    append_context_ledger(context, ledger_path, repo)
                except OSError as exc:
                    print(f"error: unable to update context ledger: {exc}", file=sys.stderr)
                    return 2
            if not record_usage("context", result=context):
                return 2
            print(render_context_bundle(context), end="")
            return 0
        renderer = render_compact_explain if args.compact else render_explain
        if not record_usage("symbol" if args.symbol else "explain", result=result):
            return 2
        print(renderer(result), end="")
        return 0
    if args.changed:
        try:
            changed_paths = git_changed_paths(repo, args.base)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        scope = changed_scope(payload, changed_paths, max_items=args.max_items)
        renderer = render_compact_changed_scope if args.compact else render_changed_scope
        if not record_usage("changed", result=scope):
            return 2
        print(renderer(scope), end="")
        return 0
    if args.merge_risk:
        base = args.base or "main"
        try:
            current_paths = git_changed_paths(repo, base)
            main_paths = git_main_drift_paths(repo, base)
            sibling_scopes = sibling_worktree_scopes(repo, base)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        result = merge_risk(
            payload,
            current_paths,
            main_paths,
            sibling_scopes,
            max_items=args.max_items,
        )
        if not record_usage("merge-risk", result=result):
            return 2
        print(render_merge_risk(result), end="")
        return 0
    out_dir = args.out.resolve() if args.out else default_out_dir(repo)
    try:
        validate_output_dir(repo, out_dir, args.allow_repo_output)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    summary_path, graph_path = write_outputs(payload, out_dir)
    if not record_usage("summary", output_files_count=2):
        return 2
    print(f"summary: {summary_path}")
    print(f"graph: {graph_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
