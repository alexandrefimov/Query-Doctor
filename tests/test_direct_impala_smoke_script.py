import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional


REPO_DIR = Path(__file__).resolve().parents[1]
SCRIPT = REPO_DIR / "scripts" / "query-doctor-direct-impala-smoke"


def run_smoke(args, *, home: Path, env: Optional[dict[str, str]] = None):
    merged_env = dict(os.environ)
    for name in (
        "QD_CONFIG",
        "KRB5CCNAME",
        "QD_CREDS_DIR",
        "QD_KEYTAB",
        "QD_KRB5_PRINCIPAL",
        "KRB5_PRINCIPAL",
    ):
        merged_env.pop(name, None)
    merged_env["HOME"] = str(home)
    if env:
        merged_env.update(env)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=REPO_DIR,
        env=merged_env,
        text=True,
        capture_output=True,
        check=False,
    )


def write_config(home: Path, payload: dict) -> Path:
    config_dir = home / ".qdcreds"
    config_dir.mkdir(parents=True)
    config = config_dir / "query-doctor-config.json"
    config.write_text(json.dumps(payload), encoding="utf-8")
    return config


def test_direct_impala_smoke_auto_selects_single_direct_cluster(tmp_path):
    home = tmp_path / "home"
    write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-impala",
                    "label": "Direct Impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                }
            ]
        },
    )

    result = run_smoke(
        ["--dry-run", "--no-metadata", "--out", str(tmp_path / "out")],
        home=home,
    )

    assert result.returncode == 0, result.stderr
    assert os.access(SCRIPT, os.X_OK)
    assert "--config-cluster direct-impala" in result.stdout
    assert "--metadata-mode off" in result.stdout
    assert "--query-type query" in result.stdout


def test_direct_impala_smoke_requires_cluster_when_multiple_direct_clusters(tmp_path):
    home = tmp_path / "home"
    write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-a",
                    "label": "Primary direct",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-a.example.test"],
                },
                {
                    "id": "direct-b",
                    "label": "Secondary direct",
                    "cluster_type": "impala",
                    "impala_profile_hosts": ["impalad-b.example.test"],
                },
            ]
        },
    )

    result = run_smoke(["--dry-run", "--no-metadata"], home=home)

    assert result.returncode == 2
    assert "choose one with --cluster" in result.stderr
    assert "direct-a (Primary direct)" in result.stderr
    assert "direct-b (Secondary direct)" in result.stderr
    assert "impalad-a.example.test" not in result.stderr
    assert "impalad-b.example.test" not in result.stderr


def test_direct_impala_smoke_require_metadata_uses_keytab_without_echoing_secrets(tmp_path):
    home = tmp_path / "home"
    write_config(
        home,
        {
            "clusters": [
                {
                    "id": "direct-impala",
                    "query_profile_source": "impala",
                    "impala_profile_hosts": ["impalad-1.example.com"],
                }
            ]
        },
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    keytab = tmp_path / "query-doctor.keytab"
    keytab.write_text("placeholder", encoding="utf-8")
    cache = f"FILE:{tmp_path / 'krb5cc_test_marker'}"
    principal = "analyst@EXAMPLE.COM"
    (fake_bin / "klist").write_text(
        "#!/usr/bin/env bash\n"
        'if [[ "$1" == "-s" ]]; then\n'
        '  [[ -f "${KLIST_READY_FILE:-}" ]] && exit 0 || exit 1\n'
        "fi\n"
        'if [[ "$1" == "-k" ]]; then\n'
        f"  echo '   1 {principal}'\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n",
        encoding="utf-8",
    )
    (fake_bin / "kinit").write_text(
        '#!/usr/bin/env bash\ntouch "$KLIST_READY_FILE"\nexit 0\n',
        encoding="utf-8",
    )
    os.chmod(fake_bin / "klist", 0o755)
    os.chmod(fake_bin / "kinit", 0o755)
    ready_file = tmp_path / "ready"

    result = run_smoke(
        [
            "--dry-run",
            "--require-metadata",
            "--out",
            str(tmp_path / "out"),
        ],
        home=home,
        env={
            "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
            "QD_KEYTAB": str(keytab),
            "KRB5CCNAME": cache,
            "KLIST_READY_FILE": str(ready_file),
        },
    )

    combined_output = result.stdout + result.stderr
    assert result.returncode == 0, combined_output
    assert "--metadata-mode on" in result.stdout
    assert principal not in combined_output
    assert str(keytab) not in combined_output
    assert "krb5cc_test_marker" not in combined_output
