from __future__ import annotations

import json
import re
import struct
from pathlib import Path
from typing import Any


REPO_DIR = Path(__file__).resolve().parents[1]
PROVENANCE_PATH = REPO_DIR / "docs" / "assets" / "readme-screenshot-provenance.json"
README_FILES = ("README.md", "README.ru.md")
LOCAL_README_IMAGE_RE = re.compile(r"!\[(?P<alt>[^\]]*)\]\((?P<path>docs/assets/[^)]+)\)")


def read_png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    assert header.startswith(b"\x89PNG\r\n\x1a\n"), path
    return struct.unpack(">II", header[16:24])


def load_manifest() -> dict[str, Any]:
    payload = json.loads(PROVENANCE_PATH.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert payload["source"] == "query-doctor-demo synthetic demo pack"
    assert payload["demo_pack_version"] == "0.4.3"
    assert 'query-doctor-demo --out "$DEMO_PACK" --overwrite' in payload["demo_pack_command"]
    assert '--batch-summary "$DEMO_PACK/batch_summary.json"' in payload["web_command"]
    return payload


def normalized_shell_text(text: str) -> str:
    return " ".join(text.replace("\\\n", " ").split())


def readme_local_images() -> dict[str, list[tuple[str, str]]]:
    images: dict[str, list[tuple[str, str]]] = {}
    for readme in README_FILES:
        text = (REPO_DIR / readme).read_text(encoding="utf-8")
        images[readme] = [
            (match.group("alt"), match.group("path"))
            for match in LOCAL_README_IMAGE_RE.finditer(text)
        ]
    return images


def test_readme_screenshot_provenance_manifest_matches_readmes_and_assets():
    manifest = load_manifest()
    entries = manifest["screenshots"]
    manifest_paths = {entry["path"] for entry in entries}
    images_by_readme = readme_local_images()

    assert manifest_paths == {
        image_path for images in images_by_readme.values() for _alt_text, image_path in images
    }

    for entry in entries:
        screenshot_path = REPO_DIR / entry["path"]
        assert screenshot_path.is_file(), entry["path"]
        viewport = entry["viewport"]
        assert read_png_dimensions(screenshot_path) == (viewport["width"], viewport["height"])
        assert entry["route"].startswith("/")
        assert entry["readme_files"] == list(README_FILES)
        for readme in README_FILES:
            assert (entry["alt_text"], entry["path"]) in images_by_readme[readme]


def test_readme_screenshot_provenance_is_tied_to_documented_demo_refresh_path():
    manifest = load_manifest()
    demo_mode_text = (REPO_DIR / "docs" / "demo-mode.md").read_text(encoding="utf-8")
    normalized_demo_mode_text = normalized_shell_text(demo_mode_text)

    assert "Use only the synthetic demo pack" in demo_mode_text
    assert manifest["demo_pack_command"] in demo_mode_text
    assert manifest["web_command"] in normalized_demo_mode_text
    for entry in manifest["screenshots"]:
        assert entry["path"] in demo_mode_text
        assert entry["route"] in demo_mode_text or entry["route"] == "/"
