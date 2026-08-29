"""Fakes standing in for the HiveServer2 driver in metadata tests."""

from __future__ import annotations

from query_doctor.impala.hs2_runner import StatementRows


class FakeHs2Cursor:
    def __init__(self, connection: "FakeHs2Connection") -> None:
        self._connection = connection
        self._outcome: object = None
        self._busy_polls = 0
        self.closed = False

    def execute_async(self, sql: str) -> None:
        self._connection.calls.append(sql)
        self._busy_polls = self._connection.busy_polls
        self._outcome = self._connection.responder(sql)

    def is_executing(self) -> bool:
        if self._busy_polls <= 0:
            return False
        self._busy_polls -= 1
        return True

    def cancel_operation(self) -> None:
        self._connection.cancelled.append(True)

    def fetchall(self) -> list[list[object]]:
        # impyla settles the operation state inside fetchall(), so a statement
        # that failed on the coordinator raises from here.
        if isinstance(self._outcome, BaseException):
            raise self._outcome
        return [list(row) for row in self._outcome.rows]

    @property
    def description(self):
        if isinstance(self._outcome, BaseException):
            return None
        return [(name, None) for name in self._outcome.columns]

    def close(self) -> None:
        self.closed = True


class FakeHs2Connection:
    def __init__(self, responder, *, busy_polls: int = 0) -> None:
        self.responder = responder
        self.busy_polls = busy_polls
        self.calls: list[str] = []
        self.cancelled: list[bool] = []
        self.cursors: list[FakeHs2Cursor] = []
        self.closed = False

    def cursor(self) -> FakeHs2Cursor:
        cursor = FakeHs2Cursor(self)
        self.cursors.append(cursor)
        return cursor

    def close(self) -> None:
        self.closed = True


class FakeHs2Connector:
    """Stands in for impyla connect(); records the settings it was handed."""

    def __init__(self, responder, *, busy_polls: int = 0) -> None:
        self._responder = responder
        self._busy_polls = busy_polls
        self.connections: list[FakeHs2Connection] = []
        self.settings: list[object] = []

    def __call__(self, settings) -> FakeHs2Connection:
        self.settings.append(settings)
        connection = FakeHs2Connection(self._responder, busy_polls=self._busy_polls)
        self.connections.append(connection)
        return connection


class TTransportException(Exception):
    """Shaped and named exactly as thrift names it, which is what the runner matches.

    Keeping the double here means the suite exercises the reconnect decision on
    an interpreter without impyla installed.
    """

    def __init__(self, message: str = "lost transport", type: int = 0) -> None:
        super().__init__(message)
        self.type = type


def text_rows(text: str) -> StatementRows:
    return StatementRows(columns=("result",), rows=((text,),))


def table_rows(columns, *rows) -> StatementRows:
    return StatementRows(columns=tuple(columns), rows=tuple(tuple(row) for row in rows))
