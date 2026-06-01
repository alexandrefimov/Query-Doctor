import json
import subprocess
import sys
from pathlib import Path

from query_doctor.analyzer.action_cards import make_runtime_admission_action_card
from query_doctor.analyzer.case_bottleneck import classify_case_primary_bottleneck
from query_doctor.analyzer.cm_metrics_correlation import build_cm_metrics_correlation
from query_doctor.analyzer.query_context import query_context
from query_doctor.analyzer.runtime_renderer import render_cm_query_context


REPO_DIR = Path(__file__).resolve().parents[1]


def test_query_context_accessor_prefers_canonical_key_with_legacy_fallback():
    canonical = {"source": "query_context", "admission_wait_ms": 2_500}
    legacy = {"source": "cm_query_context", "admission_wait_ms": 5_000}

    assert (
        query_context(
            {
                "query_context": canonical,
                "cm_query_context": legacy,
            }
        )
        is canonical
    )
    assert query_context({"cm_query_context": legacy}) is legacy
    assert query_context({}) is None


def test_analyzer_query_context_readers_accept_canonical_only_key():
    analysis = {
        "query_context": {
            "available": True,
            "status": "succeeded",
            "pool": "etl",
            "duration_ms": 100_000,
            "admission_result": "Admitted (queued)",
            "admission_wait_ms": 20_000,
        },
        "query_wall_clock": {
            "duration_ms": 100_000,
            "confidence": "high",
        },
        "profile_resources": {},
        "backend_tail": {},
        "findings": [],
        "cardinality_anomalies": [],
        "stats_metadata_quality": {
            "status": "unavailable",
            "stats_primary_bottleneck": "unknown",
            "non_stats_bottleneck_categories": "none",
        },
        "case_primary_bottleneck": {
            "label": "runtime_admission",
            "confidence": "high",
        },
        "metrics_context": {
            "available": True,
            "queries": [
                {
                    "id": "provider_specific_admission_metric",
                    "signal_id": "admission_pool_pressure",
                    "status": "ok",
                    "point_count": 3,
                    "max": 4.0,
                    "avg": 2.0,
                }
            ],
        },
    }

    bottleneck = classify_case_primary_bottleneck(analysis)
    analysis["metrics_correlation"] = build_cm_metrics_correlation(analysis)
    card = make_runtime_admission_action_card(analysis)
    rendered = "\n".join(render_cm_query_context(analysis))

    assert "cm_query_context" not in analysis
    assert bottleneck.label == "runtime_admission"
    assert "admission_wait_source_query_context" in bottleneck.reasons
    assert analysis["metrics_correlation"]["signals"][0]["correlation_status"] == "correlated"
    assert card is not None
    assert "admission wait: 20s" in card["evidence"]
    assert "## CM Query Context" in rendered
    assert "- pool: etl" in rendered
    assert "- admission_wait: 20s" in rendered


def test_analyzer_json_writes_canonical_query_context_with_legacy_alias(tmp_path):
    case_dir = tmp_path / "case"
    case_dir.mkdir()
    (case_dir / "profile_digest.md").write_text(
        """
# Synthetic digest

## ExecSummary

```text
01:SCAN HDFS  1  1s000ms  1s000ms  10  10  1.00 MB  1.00 MB
```
""",
        encoding="utf-8",
    )
    (case_dir / "query_metadata.json").write_text(
        json.dumps(
            {
                "query_id": "abc:def",
                "status": "succeeded",
                "pool": "etl",
                "duration_ms": 90_000,
                "user": "alice",
                "statement": "SELECT secret_col FROM example_guarded.table",
            }
        ),
        encoding="utf-8",
    )
    json_path = case_dir / "analysis.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "query_doctor.cli.analyze_profile",
            str(case_dir),
            "--json",
            str(json_path),
        ],
        cwd=str(REPO_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    assert result.returncode == 0, result.stderr + result.stdout
    analysis = json.loads(json_path.read_text(encoding="utf-8"))
    assert analysis["query_context"] == analysis["cm_query_context"]
    assert analysis["query_context"]["pool"] == "etl"
    assert "user" not in analysis["query_context"]
    assert "statement" not in analysis["query_context"]
