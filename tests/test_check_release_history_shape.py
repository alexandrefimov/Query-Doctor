from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_release_history_shape.py"
SPEC = importlib.util.spec_from_file_location("check_release_history_shape", SCRIPT_PATH)
assert SPEC is not None
check_release_history_shape = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_release_history_shape
SPEC.loader.exec_module(check_release_history_shape)


def runner_from(results):
    def runner(args, cwd):
        key = tuple(args)
        if key not in results:
            raise AssertionError(args)
        return results[key]

    return runner


def base_results(
    *,
    commits: str = "3\n",
    merges: str = "0\n",
    log: str = "c3c3c3c Harden report validators\nb2b2b2b Add route guards\n",
    ancestor_returncode: int = 0,
):
    command_result = check_release_history_shape.CommandResult
    return {
        ("rev-parse", "--verify", "--quiet", "public/main^{commit}"): command_result(0),
        ("rev-parse", "--verify", "--quiet", "HEAD^{commit}"): command_result(0),
        ("merge-base", "--is-ancestor", "public/main", "HEAD"): command_result(ancestor_returncode),
        ("rev-list", "--count", "public/main..HEAD"): command_result(0, commits),
        ("rev-list", "--count", "--merges", "public/main..HEAD"): command_result(0, merges),
        ("log", "--format=%h %s", "public/main..HEAD"): command_result(0, log),
    }


def analyze(results, *, max_commits=80, max_merge_commits=0):
    return check_release_history_shape.analyze_history_shape(
        Path("/repo"),
        base_ref="public/main",
        head_ref="HEAD",
        max_commits=max_commits,
        max_merge_commits=max_merge_commits,
        runner=runner_from(results),
    )


def test_reviewable_non_merge_history_passes():
    shape = analyze(base_results())

    assert shape.ok
    assert shape.commits_ahead == 3
    assert shape.merge_commits_ahead == 0
    assert shape.suspicious_subjects == ()


def test_missing_public_base_ref_fails_closed():
    command_result = check_release_history_shape.CommandResult
    shape = analyze(
        {
            ("rev-parse", "--verify", "--quiet", "public/main^{commit}"): command_result(1),
        }
    )

    assert not shape.ok
    assert shape.commits_ahead is None
    assert "does not exist" in shape.findings[0]


def test_non_ancestor_public_base_fails():
    shape = analyze(base_results(ancestor_returncode=1))

    assert not shape.ok
    assert "is not an ancestor" in "\n".join(shape.findings)


def test_merge_commits_fail_release_shape():
    shape = analyze(base_results(merges="2\n"))

    assert not shape.ok
    assert "2 merge commits" in "\n".join(shape.findings)


def test_too_many_commits_fail_release_shape():
    shape = analyze(base_results(commits="12\n"), max_commits=10)

    assert not shape.ok
    assert "12 commits" in "\n".join(shape.findings)


def test_wip_and_fixup_subjects_fail_release_shape():
    shape = analyze(
        base_results(
            log=(
                "f1f1f1f fixup! Harden report validators\n"
                "d2d2d2d WIP temporary docs snapshot\n"
                "c3c3c3c Add route guards\n"
            )
        )
    )

    assert not shape.ok
    assert shape.suspicious_subjects == (
        "f1f1f1f fixup! Harden report validators",
        "d2d2d2d WIP temporary docs snapshot",
    )
    assert "WIP/fixup/draft" in "\n".join(shape.findings)


def test_render_report_includes_counts_and_suspicious_subjects():
    shape = analyze(base_results(merges="1\n", log="f1f1f1f fixup! Audit docs\n"))

    report = check_release_history_shape.render_report(shape)

    assert "Release history shape check: FAILED" in report
    assert "Base ref: public/main" in report
    assert "Merge commits ahead: 1" in report
    assert "f1f1f1f fixup! Audit docs" in report
