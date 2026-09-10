from datetime import datetime, timezone

from analytics.etl import run


class Cursor:
    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def execute(self, sql, args=()):
        self.calls.append((sql, args))

    def fetchone(self):
        return ("analytics",)


class Connection:
    def __init__(self):
        self.cursor_obj = Cursor()
        self.commits = 0
        self.rollbacks = 0

    def cursor(self):
        return self.cursor_obj

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FailingCursor(Cursor):
    def execute(self, sql, args=()):
        self.calls.append((sql, args))
        if "refresh_warehouse" in sql:
            raise RuntimeError("refresh failed; secret=should-not-be-logged")


class FailingConnection(Connection):
    def __init__(self):
        super().__init__()
        self.cursor_obj = FailingCursor()


def test_runner_invokes_deterministic_refresh_and_commits():
    connection = Connection()
    run_id = "00000000-0000-0000-0000-000000000001"
    result = run(
        connection,
        run_id=run_id,
        snapshot_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
    )
    assert result == run_id
    assert connection.cursor_obj.calls[0][0] == (
        "SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"
    )
    assert "refresh_warehouse" in connection.cursor_obj.calls[2][0]
    assert connection.commits == 1


def test_runner_records_failed_run_after_rollback():
    connection = FailingConnection()
    try:
        run(connection, run_id="00000000-0000-0000-0000-000000000002")
    except RuntimeError:
        pass
    else:
        raise AssertionError("refresh failure should propagate")
    assert connection.rollbacks == 1
    assert connection.commits == 1
    assert "etl_run" in connection.cursor_obj.calls[-1][0]
    assert "should-not-be-logged" not in connection.cursor_obj.calls[-1][0]
    assert "should-not-be-logged" not in repr(connection.cursor_obj.calls[-1][1])
    assert (
        "WHERE analytics.etl_run.status <> 'SUCCEEDED'"
        in connection.cursor_obj.calls[-1][0]
    )


def test_schema_has_no_passenger_or_actor_columns():
    from pathlib import Path

    code = (Path(__file__).parents[1] / "etl.py").read_text()
    assert "passengers" not in code.lower()
    assert "actor_id" not in code.lower()
    assert "database-url" in code


def test_glue_entrypoint_uses_jdbc_transaction_and_full_url_fallback():
    from pathlib import Path

    code = (Path(__file__).parents[1] / "glue_job.py").read_text()
    assert "fullUrl" in code and "DriverManager" in code
    assert "source_connection_name" in code
    assert "target_connection_name" in code
    assert "target_schema" in code
    assert "source_catalog_database" in code and "target_catalog_database" in code
    assert "failed.setString(3, _safe_error(error))" in code
    assert "failed.setString(4" not in code
    assert "TRANSACTION_REPEATABLE_READ" in code
    assert "setAutoCommit(False)" in code and "conn.rollback()" in code
    assert "print(target" not in code
