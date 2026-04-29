import importlib.util
import sys
from pathlib import Path

import pytest


REPO_DIR = Path(__file__).resolve().parents[1]


def load_collector_module():
    path = REPO_DIR / "query_doctor_collect_impala_context.py"
    spec = importlib.util.spec_from_file_location("query_doctor_collect_impala_context", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_extract_original_sql_from_profile_digest_sql_block():
    module = load_collector_module()

    digest = """
# Impala Query Profile Digest

## SQL

```sql
SELECT *
FROM db1.table_a a
JOIN table_b b ON a.id = b.id;
```

## ExecSummary
"""

    sql = module.extract_original_sql(digest)

    assert sql == "SELECT *\nFROM db1.table_a a\nJOIN table_b b ON a.id = b.id\n"


def test_extract_referenced_tables_from_from_and_join():
    module = load_collector_module()

    sql = """
WITH cte AS (
    SELECT * FROM `db1`.`table_a`
)
SELECT *
FROM cte
JOIN table_b b ON cte.id = b.id
LEFT JOIN db2.table_c c ON b.id = c.id
"""

    extraction = module.extract_referenced_tables(sql, default_database="default_db")

    assert extraction.tables == ["db1.table_a", "default_db.table_b", "db2.table_c"]
    assert any("CTE names" in warning for warning in extraction.warnings)


@pytest.mark.parametrize(
    "command",
    [
        "SHOW CREATE TABLE db1.table_a",
        "SHOW TABLE STATS db1.table_a",
        "SHOW COLUMN STATS db1.table_a",
        "DESCRIBE FORMATTED db1.table_a",
        "EXPLAIN SELECT * FROM db1.table_a GROUP BY id",
    ],
)
def test_validate_impala_command_allows_metadata_commands(command):
    module = load_collector_module()

    module.validate_impala_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "SELECT COUNT(*) FROM db1.table_a",
        "SHOW TABLES",
        "COMPUTE STATS db1.table_a",
        "COMPUTE INCREMENTAL STATS db1.table_a",
        "REFRESH db1.table_a",
        "INVALIDATE METADATA db1.table_a",
        "INSERT INTO db1.table_a SELECT * FROM db1.table_b",
        "CREATE TABLE db1.new_table (id int)",
        "DROP TABLE db1.table_a",
        "ALTER TABLE db1.table_a ADD COLUMNS (x int)",
        "DELETE FROM db1.table_a WHERE id = 1",
        "UPDATE db1.table_a SET id = 2",
        "TRUNCATE TABLE db1.table_a",
        "EXPLAIN INSERT INTO db1.table_a SELECT * FROM db1.table_b",
        "EXPLAIN CREATE TABLE db1.new_table AS SELECT * FROM db1.table_a",
        "EXPLAIN SELECT * FROM db1.table_a; SELECT COUNT(*) FROM db1.table_a",
        "SHOW TABLE STATS db1.table_a; REFRESH db1.table_a",
    ],
)
def test_validate_impala_command_rejects_dangerous_commands(command):
    module = load_collector_module()

    with pytest.raises(ValueError):
        module.validate_impala_command(command)
