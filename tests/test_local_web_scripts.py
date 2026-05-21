import os
from pathlib import Path


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_DIR / "scripts"


def test_local_web_script_forwards_query_doctor_web_flags():
    script = SCRIPTS_DIR / "query-doctor-web-local"
    text = script.read_text(encoding="utf-8")

    assert os.access(script, os.X_OK)
    assert 'export QD_KEYTAB="$KEYTAB"' in text
    assert 'source "$CM_ENV"' not in text
    assert '"CM_USERNAME", "CM_USER", "CM_PASSWORD", "CM_TOKEN"' in text
    assert 'explicit_principal="${QD_KRB5_PRINCIPAL:-${KRB5_PRINCIPAL:-}}"' in text
    assert 'export KRB5_PRINCIPAL="$principal"' not in text
    assert 'exec python3 -m query_doctor.cli.web --config "$CONFIG" "$@"' in text


def test_no_llm_local_web_script_delegates_to_local_wrapper():
    script = SCRIPTS_DIR / "query-doctor-web-local-no-llm"
    text = script.read_text(encoding="utf-8")

    assert os.access(script, os.X_OK)
    assert 'exec "$ROOT_DIR/scripts/query-doctor-web-local" --no-llm "$@"' in text
