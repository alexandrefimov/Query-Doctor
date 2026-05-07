"""Recent batch subprocess argument builders."""

from __future__ import annotations

from query_doctor.recent.batch_models import BatchConfig


def append_cm_config_args(cmd: list[str], config: BatchConfig) -> None:
    if config.config_path:
        cmd.extend(["--config", config.config_path])
        return
    cmd.extend(["--cm-url", config.cm_url, "--cluster", config.cluster, "--service", config.service])
    if config.ca_bundle:
        cmd.extend(["--ca-bundle", config.ca_bundle])


def append_metadata_args(cmd: list[str], config: BatchConfig) -> None:
    cmd.extend(["--metadata-mode", config.metadata_mode])
    if config.metadata_mode == "off" or not config.metadata_coordinator:
        return
    cmd.extend(["--metadata-coordinator", config.metadata_coordinator])
    if config.metadata_impala_shell:
        cmd.extend(["--metadata-impala-shell", config.metadata_impala_shell])
    cmd.extend(["--metadata-auth", config.metadata_auth])
    cmd.extend(["--metadata-protocol", config.metadata_protocol])
    cmd.extend(["--metadata-timeout-sec", str(config.metadata_timeout_sec)])
    if config.metadata_ssl:
        cmd.append("--metadata-ssl")
    if config.metadata_ca_cert:
        cmd.extend(["--metadata-ca-cert", config.metadata_ca_cert])
    if config.metadata_max_tables is not None:
        cmd.extend(["--metadata-max-tables", str(config.metadata_max_tables)])
    if config.metadata_max_output_bytes is not None:
        cmd.extend(["--metadata-max-output-bytes", str(config.metadata_max_output_bytes)])
    if config.metadata_redact:
        cmd.append("--metadata-redact")
