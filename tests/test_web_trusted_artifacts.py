from query_doctor.web import trusted_artifacts


def test_trusted_artifacts_exposes_optimizer_artifact_status_helpers():
    assert trusted_artifacts.optimizer_artifact_status_for_case({}) == "unknown"
    assert trusted_artifacts.OPTIMIZER_STATUS_ORDER["trusted_draft"] > trusted_artifacts.OPTIMIZER_STATUS_ORDER["not_run"]
