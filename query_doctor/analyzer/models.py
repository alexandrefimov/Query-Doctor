"""Analyzer data models for parsed Impala profile facts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class OperatorObservation:
    time_ms: float | None = None
    actual_rows: float | None = None
    estimated_rows: float | None = None
    peak_mem_bytes: float | None = None
    estimated_peak_mem_bytes: float | None = None
    evidence_lines: list[str] = field(default_factory=list)


def observation_rows_ratio(observation: OperatorObservation) -> float | None:
    if (
        observation.actual_rows is None
        or observation.estimated_rows is None
        or observation.estimated_rows <= 0
    ):
        return None
    return observation.actual_rows / observation.estimated_rows


def observation_mem_ratio(observation: OperatorObservation) -> float | None:
    if (
        observation.peak_mem_bytes is None
        or observation.estimated_peak_mem_bytes is None
        or observation.estimated_peak_mem_bytes <= 0
    ):
        return None
    return observation.peak_mem_bytes / observation.estimated_peak_mem_bytes


def observation_has_zero_row_estimate_gap(observation: OperatorObservation) -> bool:
    return (
        observation.actual_rows is not None
        and observation.actual_rows > 0
        and observation.estimated_rows is not None
        and observation.estimated_rows <= 0
    )


def observation_has_zero_memory_estimate_gap(observation: OperatorObservation) -> bool:
    return (
        observation.peak_mem_bytes is not None
        and observation.peak_mem_bytes > 0
        and observation.estimated_peak_mem_bytes is not None
        and observation.estimated_peak_mem_bytes <= 0
    )


def observation_has_row_pair(observation: OperatorObservation) -> bool:
    return observation.actual_rows is not None and observation.estimated_rows is not None


def observation_has_memory_pair(observation: OperatorObservation) -> bool:
    return (
        observation.peak_mem_bytes is not None and observation.estimated_peak_mem_bytes is not None
    )


@dataclass
class OperatorFact:
    operator_id: str
    operator_name: str
    time_ms: float | None = None
    actual_rows: float | None = None
    estimated_rows: float | None = None
    peak_mem_bytes: float | None = None
    estimated_peak_mem_bytes: float | None = None
    join_kind: str | None = None
    is_partitioned: bool = False
    evidence_lines: list[str] = field(default_factory=list)
    observations: list[OperatorObservation] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.observations:
            self.observations.append(
                OperatorObservation(
                    time_ms=self.time_ms,
                    actual_rows=self.actual_rows,
                    estimated_rows=self.estimated_rows,
                    peak_mem_bytes=self.peak_mem_bytes,
                    estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                    evidence_lines=list(self.evidence_lines),
                )
            )

    def best_rows_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_rows_ratio(observation) is not None
        ]
        if not candidates and not any(
            observation_has_row_pair(observation) for observation in self.observations
        ):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_rows_ratio(fallback) is not None:
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation_rows_ratio(observation) or 0)

    def best_memory_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_mem_ratio(observation) is not None
        ]
        if not candidates and not any(
            observation_has_memory_pair(observation) for observation in self.observations
        ):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_mem_ratio(fallback) is not None:
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation_mem_ratio(observation) or 0)

    def best_zero_row_estimate_gap_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_has_zero_row_estimate_gap(observation)
        ]
        if not candidates and not any(
            observation_has_row_pair(observation) for observation in self.observations
        ):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_has_zero_row_estimate_gap(fallback):
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation.actual_rows or 0)

    def best_zero_memory_estimate_gap_observation(self) -> OperatorObservation | None:
        candidates = [
            observation
            for observation in self.observations
            if observation_has_zero_memory_estimate_gap(observation)
        ]
        if not candidates and not any(
            observation_has_memory_pair(observation) for observation in self.observations
        ):
            fallback = OperatorObservation(
                time_ms=self.time_ms,
                actual_rows=self.actual_rows,
                estimated_rows=self.estimated_rows,
                peak_mem_bytes=self.peak_mem_bytes,
                estimated_peak_mem_bytes=self.estimated_peak_mem_bytes,
                evidence_lines=list(self.evidence_lines),
            )
            if observation_has_zero_memory_estimate_gap(fallback):
                candidates.append(fallback)
        if not candidates:
            return None
        return max(candidates, key=lambda observation: observation.peak_mem_bytes or 0)

    @property
    def rows_ratio(self) -> float | None:
        observation = self.best_rows_observation()
        if observation is None:
            return None
        return observation_rows_ratio(observation)

    @property
    def mem_ratio(self) -> float | None:
        observation = self.best_memory_observation()
        if observation is None:
            return None
        return observation_mem_ratio(observation)

    @property
    def has_zero_row_estimate_gap(self) -> bool:
        return self.best_zero_row_estimate_gap_observation() is not None

    @property
    def has_zero_memory_estimate_gap(self) -> bool:
        return self.best_zero_memory_estimate_gap_observation() is not None

    @property
    def is_join(self) -> bool:
        return "JOIN" in self.operator_name.upper()

    @property
    def is_sort(self) -> bool:
        return self.operator_name.upper() in {"SORT", "TOP-N"}

    @property
    def is_analytic(self) -> bool:
        return "ANALYTIC" in self.operator_name.upper()

    @property
    def is_scan(self) -> bool:
        return "SCAN" in self.operator_name.upper()


@dataclass
class BackendHostFact:
    host: str
    fragment_instance: str | None = None
    fragment_group: str | None = None
    scan_bytes_assigned: float | None = None
    bytes_read: float | None = None
    bytes_written: float | None = None
    rows_produced: float | None = None
    read_rate_bps: float | None = None
    write_rate_bps: float | None = None
    hdfs_write_time_ms: float | None = None
    hdfs_write_sec_per_gib: float | None = None
    scanner_wait_time_ms: float | None = None
    materialize_time_ms: float | None = None
    parse_time_ms: float | None = None
    peak_scanner_concurrency: float | None = None
    execution_time_ms: float | None = None
    evidence_lines: list[str] = field(default_factory=list)

    def has_metric(self) -> bool:
        return any(
            value is not None
            for value in (
                self.scan_bytes_assigned,
                self.bytes_read,
                self.bytes_written,
                self.rows_produced,
                self.read_rate_bps,
                self.write_rate_bps,
                self.hdfs_write_time_ms,
                self.hdfs_write_sec_per_gib,
                self.scanner_wait_time_ms,
                self.materialize_time_ms,
                self.parse_time_ms,
                self.peak_scanner_concurrency,
                self.execution_time_ms,
            )
        )
