"""A merge queue only works if every required check also runs on merge_group.

A required context that never reports leaves the queue waiting forever, so the
workflows behind the required checks are pinned here rather than left to be
remembered when someone adds the next one.
"""

from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
WORKFLOWS = REPO_DIR / ".github" / "workflows"

# Workflow -> the required status checks it produces.
REQUIRED_CHECK_WORKFLOWS = {
    "ci.yml": (
        "Deterministic safety checks / Python 3.10",
        "Deterministic safety checks / Python 3.11",
        "Full test suite / Python 3.11",
    ),
    "codeql.yml": ("CodeQL / Python",),
    "package.yml": ("Build, check, and install wheel",),
    "web-e2e.yml": ("Web E2E / Chromium",),
    "docs.yml": ("Docs health checks",),
    "dependency-review.yml": ("Dependency Review",),
}


def workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def trigger_block(text: str) -> str:
    start = text.index("\non:\n")
    rest = text[start + len("\non:\n") :]
    end = rest.find("\n\n")
    return rest if end == -1 else rest[:end]


def test_every_workflow_behind_a_required_check_runs_on_merge_group():
    missing = [
        name
        for name in REQUIRED_CHECK_WORKFLOWS
        if "merge_group:" not in trigger_block(workflow_text(name))
    ]

    assert missing == [], f"these produce required checks but never run in a merge group: {missing}"


def test_dependency_review_is_given_the_merge_group_refs():
    text = workflow_text("dependency-review.yml")

    # The action defaults these from the pull request, which a merge group has not got.
    assert "base-ref: ${{ github.event.merge_group.base_sha }}" in text
    assert "head-ref: ${{ github.event.merge_group.head_sha }}" in text


def test_web_e2e_scope_detection_handles_a_merge_group():
    text = workflow_text("web-e2e.yml")

    assert 'elif [[ "${{ github.event_name }}" == "merge_group" ]]; then' in text
    assert 'base_sha="${{ github.event.merge_group.base_sha }}"' in text
    # An empty base must run the suite rather than reach git diff with no argument.
    assert 'if [[ -z "$base_sha" || "$base_sha" =~ ^0+$ ]]; then' in text


def test_docs_age_check_does_not_enforce_inside_the_merge_queue():
    text = workflow_text("docs.yml")

    # Enforcing on merge_group would put calendar rot back in the way of merging,
    # which is what warning on pull requests was meant to stop.
    assert "github.event_name == 'push' || github.event_name == 'workflow_dispatch'" in text
    assert "&& 'enforce' || 'warn' }}" in text
