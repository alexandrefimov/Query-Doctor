import os
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_DIR / "scripts"


def test_local_web_script_forwards_query_doctor_web_flags():
    script = SCRIPTS_DIR / "query-doctor-web-local"
    text = script.read_text(encoding="utf-8")

    assert os.access(script, os.X_OK)
    assert 'exec python3 -m query_doctor.cli.web --config "$CONFIG" "$@"' in text


def test_no_llm_local_web_script_delegates_to_local_wrapper():
    script = SCRIPTS_DIR / "query-doctor-web-local-no-llm"
    text = script.read_text(encoding="utf-8")

    assert os.access(script, os.X_OK)
    assert 'exec "$ROOT_DIR/scripts/query-doctor-web-local" --no-llm "$@"' in text
