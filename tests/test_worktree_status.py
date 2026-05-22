from pathlib import Path

from scripts.worktree_status import (
    CommandResult,
    WorktreeStatus,
    build_statuses,
    parse_worktree_porcelain,
    recommendation_for,
    render_table,
)


def test_parse_worktree_porcelain_uses_short_branch_names():
    text = "\n".join(
        [
            "worktree /repo",
            "HEAD abc123",
            "branch refs/heads/main",
            "",
            "worktree /repo-wt",
            "HEAD def456",
            "branch refs/heads/feature/audit",
            "",
        ]
    )

    entries = parse_worktree_porcelain(text)

    assert [(entry.path, entry.head, entry.branch) for entry in entries] == [
        ("/repo", "abc123", "main"),
        ("/repo-wt", "def456", "feature/audit"),
    ]


def test_recommendation_for_common_worktree_states():
    assert (
        recommendation_for(
            branch="main",
            main_ref="main",
            dirty="clean",
            main_only=0,
            branch_only=0,
            merged="yes",
        )
        == "main workspace"
    )
    assert (
        recommendation_for(
            branch="feature",
            main_ref="main",
            dirty="dirty",
            main_only=0,
            branch_only=2,
            merged="no",
        )
        == "active: dirty worktree"
    )
    assert (
        recommendation_for(
            branch="feature",
            main_ref="main",
            dirty="clean",
            main_only=0,
            branch_only=2,
            merged="no",
        )
        == "merge candidate"
    )
    assert (
        recommendation_for(
            branch="feature",
            main_ref="main",
            dirty="clean",
            main_only=3,
            branch_only=2,
            merged="no",
        )
        == "refresh/review: diverged from main"
    )
    assert (
        recommendation_for(
            branch="old",
            main_ref="main",
            dirty="clean",
            main_only=4,
            branch_only=0,
            merged="yes",
        )
        == "cleanup candidate"
    )


def test_build_statuses_reports_dirty_merge_and_cleanup_candidates():
    worktree_text = "\n".join(
        [
            "worktree /repo",
            "HEAD aaaaaa",
            "branch refs/heads/main",
            "",
            "worktree /repo-feature",
            "HEAD bbbbbb",
            "branch refs/heads/feature",
            "",
            "worktree /repo-done",
            "HEAD cccccc",
            "branch refs/heads/done",
            "",
            "worktree /repo-dirty",
            "HEAD dddddd",
            "branch refs/heads/dirty",
            "",
        ]
    )

    def runner(args, cwd):
        if args == ["worktree", "list", "--porcelain"]:
            return CommandResult(0, worktree_text)
        if args[:2] == ["-C", "/repo"]:
            return CommandResult(0, "")
        if args[:2] == ["-C", "/repo-feature"]:
            return CommandResult(0, "")
        if args[:2] == ["-C", "/repo-done"]:
            return CommandResult(0, "")
        if args[:2] == ["-C", "/repo-dirty"]:
            return CommandResult(0, " M docs/a.md\n?? tmp.txt\n")
        if args == ["rev-list", "--left-right", "--count", "main...main"]:
            return CommandResult(0, "0\t0\n")
        if args == ["rev-list", "--left-right", "--count", "main...feature"]:
            return CommandResult(0, "0\t2\n")
        if args == ["rev-list", "--left-right", "--count", "main...done"]:
            return CommandResult(0, "5\t0\n")
        if args == ["rev-list", "--left-right", "--count", "main...dirty"]:
            return CommandResult(0, "1\t1\n")
        if args == ["merge-base", "--is-ancestor", "feature", "main"]:
            return CommandResult(1, "")
        if args == ["merge-base", "--is-ancestor", "done", "main"]:
            return CommandResult(0, "")
        if args == ["merge-base", "--is-ancestor", "dirty", "main"]:
            return CommandResult(1, "")
        raise AssertionError(args)

    statuses = build_statuses(Path("/repo"), runner=runner)
    by_branch = {status.branch: status for status in statuses}

    assert by_branch["main"].recommendation == "main workspace"
    assert by_branch["feature"].recommendation == "merge candidate"
    assert by_branch["done"].recommendation == "cleanup candidate"
    assert by_branch["dirty"].recommendation == "active: dirty worktree"
    assert by_branch["dirty"].dirty == "dirty:2"


def test_render_table_includes_recommendation_and_divergence():
    rendered = render_table(
        [
            WorktreeStatus(
                path="/repo-feature",
                branch="feature",
                head="abc123",
                dirty="clean:0",
                dirty_count=0,
                main_only=0,
                branch_only=2,
                merged="no",
                recommendation="merge candidate",
            )
        ]
    )

    assert "branch" in rendered
    assert "branch_only" in rendered
    assert "merge candidate" in rendered
    assert "/repo-feature" in rendered
