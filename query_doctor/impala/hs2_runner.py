"""Read-only Impala metadata statements over HiveServer2, through impyla.

One coordinator connection is opened per collector run and reused by every
planned statement. The rows that come back are typed, so this module renders
them into the same delimited table text the metadata fact parser and
``impala_context.md`` already read.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass


DEFAULT_HTTP_PATH = "cliservice"
DEFAULT_HS2_PORT = 21050
# impyla's own default when the config leaves the service name unset.
DEFAULT_KERBEROS_SERVICE_NAME = "impala"
SHOW_CREATE_TABLE = "SHOW CREATE TABLE"
_MIN_POLL_SEC = 0.01
_MAX_POLL_SEC = 0.25
_ROW_SEPARATOR = "+---+"
_WHITESPACE_RUN_RE = re.compile(r"\s+")


class ImpalaDriverUnavailableError(RuntimeError):
    """Raised when impyla is not installed in the running environment."""


class ImpalaStatementError(RuntimeError):
    """Raised when a read-only metadata statement fails on the coordinator."""


class ImpalaStatementTimeoutError(ImpalaStatementError):
    """Raised when a statement outlives its deadline and is cancelled."""


@dataclass(frozen=True)
class Hs2ConnectionSettings:
    host: str
    port: int = DEFAULT_HS2_PORT
    kerberos_service_name: str | None = None
    kerberos_host_fqdn: str | None = None
    use_ssl: bool = False
    ca_cert: str | None = None
    use_http_transport: bool = False
    http_path: str = DEFAULT_HTTP_PATH
    timeout_sec: int = 30


@dataclass(frozen=True)
class StatementRows:
    columns: tuple[str, ...]
    rows: tuple[tuple[object, ...], ...]


Connector = Callable[[Hs2ConnectionSettings], object]


def connect_kwargs(settings: Hs2ConnectionSettings) -> dict[str, object]:
    """Return the impyla ``connect()`` keywords for these settings."""
    kwargs: dict[str, object] = {
        "host": settings.host,
        "port": settings.port,
        "auth_mechanism": "GSSAPI",
        "timeout": settings.timeout_sec,
        "use_ssl": settings.use_ssl,
    }
    if settings.ca_cert:
        kwargs["ca_cert"] = settings.ca_cert
    if settings.kerberos_service_name:
        kwargs["kerberos_service_name"] = settings.kerberos_service_name
    if settings.kerberos_host_fqdn:
        # impyla builds the SPN from krb_host when it is set, and from host otherwise.
        kwargs["krb_host"] = settings.kerberos_host_fqdn
    if settings.use_http_transport:
        kwargs["use_http_transport"] = True
        kwargs["http_path"] = settings.http_path
    return kwargs


def driver_available() -> bool:
    """True when impyla can be imported in this environment."""
    try:
        import impala.dbapi  # noqa: F401
    except ImportError:
        return False
    return True


def default_connector(settings: Hs2ConnectionSettings) -> object:
    try:
        from impala.dbapi import connect
    except ImportError as exc:  # pragma: no cover - exercised by the packaging tests
        raise ImpalaDriverUnavailableError(
            "Impala metadata collection needs the impyla driver; install query-doctor[impala]."
        ) from exc
    return connect(**connect_kwargs(settings))


def _thrift_timed_out() -> int:
    try:
        from thrift.transport.TTransport import TTransportException
    except ImportError:
        return 3  # TTransportException.TIMED_OUT
    return TTransportException.TIMED_OUT


def _is_lost_transport(exc: BaseException) -> bool:
    """True when a second attempt on a fresh connection is worth making.

    The driver's exception classes are recognised by name so that this module
    stays importable without impyla, which every install that skips the impala
    extra depends on.
    """
    names = {klass.__name__ for klass in type(exc).__mro__}
    if "DisconnectedError" in names:
        return True
    if "TTransportException" not in names:
        return False
    # A read that ran out of time already spent the statement's budget.
    return getattr(exc, "type", None) != _thrift_timed_out()


# A missing driver is a property of the run, not of one statement, so it is not
# turned into a per-statement failure.
_PASS_THROUGH_ERRORS = (ImpalaStatementError, ImpalaDriverUnavailableError)


def _statement_error(exc: BaseException) -> ImpalaStatementError:
    return ImpalaStatementError(str(exc).strip() or type(exc).__name__)


class Hs2MetadataSession:
    """A coordinator connection shared by every statement of one collector run."""

    def __init__(
        self,
        settings: Hs2ConnectionSettings,
        *,
        connector: Connector | None = None,
    ) -> None:
        self._settings = settings
        self._connector = connector
        self._connection: object | None = None

    def __enter__(self) -> "Hs2MetadataSession":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            connection.close()
        except Exception:
            # A connection that cannot be closed is already unusable, and the
            # reason belongs to no statement result.
            pass

    def run(self, sql: str, *, timeout_sec: int | None = None) -> StatementRows:
        budget = self._settings.timeout_sec if timeout_sec is None else timeout_sec
        try:
            return self._run_once(sql, budget=budget)
        except _PASS_THROUGH_ERRORS:
            raise
        except Exception as exc:
            if not _is_lost_transport(exc):
                raise _statement_error(exc) from exc
            self.close()
            try:
                return self._run_once(sql, budget=budget)
            except _PASS_THROUGH_ERRORS:
                raise
            except Exception as retry_exc:
                raise _statement_error(retry_exc) from retry_exc

    def _connection_or_connect(self) -> object:
        if self._connection is None:
            connector = self._connector or default_connector
            self._connection = connector(self._settings)
        return self._connection

    def _run_once(self, sql: str, *, budget: int) -> StatementRows:
        cursor = self._connection_or_connect().cursor()
        try:
            cursor.execute_async(sql)
            self._await_completion(cursor, budget=budget)
            # fetchall() settles the operation state first and raises the
            # coordinator's own error message when the statement failed.
            rows = cursor.fetchall() or []
            columns = tuple(str(item[0]) for item in (cursor.description or ()))
            return StatementRows(
                columns=columns,
                rows=tuple(tuple(row) for row in rows),
            )
        finally:
            try:
                cursor.close()
            except Exception:
                pass

    def _await_completion(self, cursor: object, *, budget: int) -> None:
        deadline = time.monotonic() + budget
        poll = _MIN_POLL_SEC
        while cursor.is_executing():
            if time.monotonic() >= deadline:
                try:
                    cursor.cancel_operation()
                finally:
                    raise ImpalaStatementTimeoutError(f"statement timed out after {budget}s")
            time.sleep(poll)
            poll = min(poll * 2, _MAX_POLL_SEC)


def render_cell(value: object) -> str:
    if value is None:
        return "NULL"
    text = _WHITESPACE_RUN_RE.sub(" ", str(value)).strip()
    # The delimiter belongs to the rendering, so a value carrying one is
    # rewritten rather than allowed to split its own row.
    return text.replace("|", "/")


def render_delimited_table(result: StatementRows) -> str:
    if not result.columns:
        return ""
    lines = [_ROW_SEPARATOR, _render_row(result.columns), _ROW_SEPARATOR]
    lines.extend(_render_row(row) for row in result.rows)
    lines.append(_ROW_SEPARATOR)
    return "\n".join(lines) + "\n"


def _render_row(cells: Sequence[object]) -> str:
    return "| " + " | ".join(render_cell(cell) for cell in cells) + " |"


def render_statement_output(label: str, result: StatementRows) -> str:
    """Render fetched rows the way the metadata fact parser reads them."""
    if label == SHOW_CREATE_TABLE:
        # The DDL arrives as text with its own line breaks; boxing it would
        # destroy them and the object type with them.
        parts = [
            str(cell).rstrip()
            for row in result.rows
            for cell in row
            if cell is not None and str(cell).strip()
        ]
        return ("\n".join(parts) + "\n") if parts else ""
    return render_delimited_table(result)
