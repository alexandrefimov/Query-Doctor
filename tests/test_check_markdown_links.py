from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_markdown_links.py"
SPEC = importlib.util.spec_from_file_location("check_markdown_links", SCRIPT_PATH)
assert SPEC is not None
check_markdown_links = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = check_markdown_links
SPEC.loader.exec_module(check_markdown_links)


def test_markdown_files_include_deploy_docs(tmp_path):
    root_doc = tmp_path / "README.md"
    docs_doc = tmp_path / "docs" / "guide.md"
    deploy_doc = tmp_path / "deploy" / "kubernetes" / "README.md"
    ignored_doc = tmp_path / "tests" / "README.md"
    for path in (root_doc, docs_doc, deploy_doc, ignored_doc):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# Guide\n", encoding="utf-8")

    assert check_markdown_links.markdown_files(tmp_path) == [
        root_doc,
        deploy_doc,
        docs_doc,
    ]


def test_markdown_anchors_match_github_headings_duplicates_and_html_ids(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text(
        "\n".join(
            [
                "# Release & Readiness",
                "## [Repeated](elsewhere.md)",
                "## Repeated",
                "Setext Heading",
                "--------------",
                '<a id="manual-check"></a>',
                "<section id='single-quoted'></section>",
                '<a name="named-anchor"></a>',
            ]
        ),
        encoding="utf-8",
    )

    assert check_markdown_links.markdown_anchors(path) == {
        "release--readiness",
        "repeated",
        "repeated-1",
        "setext-heading",
        "manual-check",
        "single-quoted",
        "named-anchor",
    }


def test_github_heading_slug_removes_markup_and_non_space_punctuation():
    assert (
        check_markdown_links.github_heading_slug(
            "This'll be a _Helpful_ Section About the Greek Letter Θ!"
        )
        == "thisll-be-a-helpful-section-about-the-greek-letter-θ"
    )
    assert check_markdown_links.github_heading_slug("snake_case") == "snake_case"


def test_markdown_anchors_ignore_fenced_headings_and_ids(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text(
        "\n".join(
            [
                "# Visible",
                "---",
                "```markdown",
                "## Hidden",
                '<a id="hidden-id"></a>',
                "```",
                "    Fake Setext Heading",
                "---",
                "\t# Tab-indented ATX heading",
            ]
        ),
        encoding="utf-8",
    )

    assert check_markdown_links.markdown_anchors(path) == {"visible"}


def test_unfenced_lines_require_matching_commonmark_fence_closer(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text(
        "\n".join(
            [
                "````markdown",
                "[Hidden](missing-one.md)",
                "```",
                "[Still hidden](missing-two.md)",
                "~~~~",
                "````",
                "    ```",
                "[Visible](present.md)",
                "    ```",
            ]
        ),
        encoding="utf-8",
    )

    assert list(check_markdown_links.iter_targets(path)) == [(8, "present.md")]


def test_iter_targets_ignores_multiline_inline_and_indented_code(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text(
        "\n".join(
            [
                "`multiline code starts",
                "[Inline hidden](missing-inline.md)",
                "[inline-ref]: missing-reference.md",
                "and ends here`",
                "    [Indented hidden](missing-indented.md)",
                "    [indented-ref]: missing-indented-reference.md",
                "[Visible](present.md)",
                "[visible-ref]: present-reference.md",
            ]
        ),
        encoding="utf-8",
    )

    assert list(check_markdown_links.iter_targets(path)) == [
        (7, "present.md"),
        (8, "present-reference.md"),
    ]


def test_markdown_anchors_ignore_inline_and_indented_code_html_ids(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text(
        "\n".join(
            [
                '`<a id="inline-fake"></a>`',
                '    <a id="indented-fake"></a>',
                '   \t<a id="tab-indented-fake"></a>',
                '``<a id="multiline-inline-fake"></a>',
                "continues here``",
                '<a id="real-anchor"></a>',
            ]
        ),
        encoding="utf-8",
    )

    assert check_markdown_links.markdown_anchors(path) == {"real-anchor"}


def test_check_markdown_links_validates_same_file_and_cross_file_anchors(tmp_path):
    readme = tmp_path / "README.md"
    guide = tmp_path / "docs" / "guide.md"
    guide.parent.mkdir()
    readme.write_text(
        "\n".join(
            [
                "# Home",
                "[Home](#home)",
                "[First](docs/guide.md#repeated)",
                "[Second](docs/guide.md#repeated-1)",
                "[Manual](docs/guide.md#manual-check)",
                "[Encoded](docs/guide.md#manual%2Dcheck)",
            ]
        ),
        encoding="utf-8",
    )
    guide.write_text(
        "\n".join(
            [
                "# Repeated",
                "# Repeated",
                '<a id="manual-check"></a>',
            ]
        ),
        encoding="utf-8",
    )

    assert check_markdown_links.check_markdown_links(tmp_path) == []


def test_check_markdown_links_handles_balanced_and_escaped_parentheses(tmp_path):
    readme = tmp_path / "README.md"
    guide = tmp_path / "docs" / "guide_(v2).md"
    guide.parent.mkdir()
    readme.write_text(
        "\n".join(
            [
                "[Balanced](docs/guide_(v2).md#api)",
                r"[Escaped](docs/guide_\(v2\).md#api)",
            ]
        ),
        encoding="utf-8",
    )
    guide.write_text("# [API](guide_(v2).md)\n", encoding="utf-8")

    assert check_markdown_links.markdown_anchors(guide) == {"api"}
    assert check_markdown_links.check_markdown_links(tmp_path) == []


def test_check_markdown_links_reports_missing_anchor_and_target(tmp_path):
    readme = tmp_path / "README.md"
    guide = tmp_path / "docs" / "guide.md"
    guide.parent.mkdir()
    readme.write_text(
        "[Missing anchor](docs/guide.md#not-there)\n[Missing file](docs/missing.md#heading)\n",
        encoding="utf-8",
    )
    guide.write_text("# Present\n", encoding="utf-8")

    assert check_markdown_links.check_markdown_links(tmp_path) == [
        "README.md:1: missing local Markdown anchor '#not-there' in target: "
        "docs/guide.md#not-there",
        "README.md:2: missing local link target: docs/missing.md#heading",
    ]


def test_check_markdown_links_skips_external_and_fenced_links(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "[External](https://example.com/guide.md#missing)",
                "[URN](urn:isbn:9780140328721)",
                "[Data](data:text/plain,not-a-local-file)",
                "[Custom](query-doctor:local-action)",
                "`[Inline code](missing-inline.md)`",
                "```markdown",
                "[Fenced](missing.md#missing)",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    assert check_markdown_links.check_markdown_links(tmp_path) == []


def test_check_markdown_links_rejects_target_outside_repository(tmp_path):
    readme = tmp_path / "README.md"
    outside = tmp_path.parent / "outside.md"
    readme.write_text("[Outside](../outside.md#outside)\n", encoding="utf-8")
    outside.write_text("# Outside\n", encoding="utf-8")

    assert check_markdown_links.check_markdown_links(tmp_path) == [
        "README.md:1: local link target resolves outside repository: ../outside.md#outside"
    ]
