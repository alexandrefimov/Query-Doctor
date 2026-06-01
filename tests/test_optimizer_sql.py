import pytest

from query_doctor.optimizer.sql import OptimizerSqlError, extract_referenced_tables


def names(sql):
    return [table.name for table in extract_referenced_tables(sql)]


def qualified(sql):
    return [table.qualified for table in extract_referenced_tables(sql)]


def test_extracts_simple_from():
    assert names("select id from example_sales.orders") == ["example_sales.orders"]


def test_extracts_join():
    sql = (
        "select * from example_sales.orders o join example_dim.customers c on o.customer_id = c.id"
    )

    assert names(sql) == ["example_sales.orders", "example_dim.customers"]


def test_extracts_multiple_joins():
    sql = """
    select f.id
    from example_mart.fact_sales f
    left join example_dim.date_dim d on f.ds = d.ds
    inner join example_dim.store s on f.store_id = s.id
    """

    assert names(sql) == ["example_mart.fact_sales", "example_dim.date_dim", "example_dim.store"]


def test_excludes_cte_name_but_keeps_tables_inside_cte():
    sql = """
    with recent as (
      select * from example_raw.events
    )
    select * from recent join example_dim.users u on recent.user_id = u.id
    """

    assert names(sql) == ["example_raw.events", "example_dim.users"]


def test_excludes_multiple_cte_names():
    sql = """
    with recent_orders as (
      select * from example_raw.orders
    ),
    active_users as (
      select * from example_raw.users
    )
    select *
    from recent_orders ro
    join active_users au on ro.user_id = au.id
    join example_mart.calendar c on ro.ds = c.ds
    """

    assert names(sql) == ["example_raw.orders", "example_raw.users", "example_mart.calendar"]


def test_excludes_nested_cte_names_but_keeps_physical_tables():
    sql = """
    with outer_cte as (
      with inner_cte as (
        select * from db.source_a
      )
      select * from inner_cte
    )
    select *
    from outer_cte
    join db.real_table t on t.id = outer_cte.id
    """

    extracted = names(sql)

    assert extracted == ["db.source_a", "db.real_table"]
    assert "inner_cte" not in extracted
    assert "outer_cte" not in extracted


def test_excludes_subquery_alias():
    sql = """
    select x.id
    from (select id from example_raw.events) x
    join example_dim.users u on x.id = u.id
    """

    assert names(sql) == ["example_raw.events", "example_dim.users"]
    assert "x" not in names(sql)


def test_extracts_backticked_and_double_quoted_identifiers():
    sql = 'select * from `example_sales`.`orders` o join "example_dim"."customers" c on o.id = c.id'

    assert names(sql) == ["example_sales.orders", "example_dim.customers"]


def test_deduplicates_preserving_stable_order():
    sql = "select * from example_sales.orders o join example_sales.orders o2 on o.id = o2.id join example_dim.users u on u.id = o.id"

    assert names(sql) == ["example_sales.orders", "example_dim.users"]


def test_unqualified_table_handling():
    sql = "select * from orders o join example_sales.customers c on o.customer_id = c.id"

    assert names(sql) == ["orders", "example_sales.customers"]
    assert qualified(sql) == [False, True]


def test_extracts_comma_separated_from_tables():
    sql = "select * from db.a, db.b where db.a.id = db.b.id"

    assert names(sql) == ["db.a", "db.b"]


def test_extracts_comma_separated_from_with_aliases_and_join():
    sql = "select * from db.a a, db.b b join db.c c on b.id = c.id"

    assert names(sql) == ["db.a", "db.b", "db.c"]


def test_comma_separated_from_skips_cte_names():
    sql = """
    with recent as (
      select * from db.source
    )
    select *
    from recent r, db.dim d
    where r.id = d.id
    """

    assert names(sql) == ["db.source", "db.dim"]


def test_allows_single_trailing_statement_separator():
    assert names("select * from example_sales.orders;") == ["example_sales.orders"]


def test_rejects_multi_statement_input():
    sql = "select * from example_sales.orders; select * from example_guarded.audit_log"

    with pytest.raises(OptimizerSqlError, match="Only one SQL statement"):
        extract_referenced_tables(sql)


@pytest.mark.parametrize(
    ("sql", "keyword"),
    [
        ("insert into example_mart.daily_sales select * from example_raw.sales", "INSERT"),
        ("create table example_mart.daily_sales as select * from example_raw.sales", "CREATE"),
        ("alter table example_mart.daily_sales add columns (x int)", "ALTER"),
        ("drop table example_mart.daily_sales", "DROP"),
        ("truncate table example_mart.daily_sales", "TRUNCATE"),
        ("merge into example_mart.daily_sales using example_raw.sales on id = id", "MERGE"),
        ("delete from example_mart.daily_sales where id = 1", "DELETE"),
        ("update example_mart.daily_sales set id = 2 where id = 1", "UPDATE"),
        ("compute stats example_mart.daily_sales", "COMPUTE"),
        ("refresh example_mart.daily_sales", "REFRESH"),
        ("invalidate metadata example_mart.daily_sales", "INVALIDATE"),
        ("msck repair table example_mart.daily_sales", "MSCK"),
        ("use mart", "USE"),
        ("set mem_limit=1g", "SET"),
    ],
)
def test_rejects_mutating_or_cluster_state_sql(sql, keyword):
    with pytest.raises(OptimizerSqlError, match=keyword):
        extract_referenced_tables(sql)


def test_rejects_explain_even_for_select():
    with pytest.raises(OptimizerSqlError, match="Only read-only SELECT/WITH"):
        extract_referenced_tables("explain select * from example_sales.orders")


def test_rejects_unsupported_keyword_after_read_only_start():
    sql = """
    with recent as (select * from example_raw.sales)
    insert into example_mart.daily_sales select * from recent
    """

    with pytest.raises(OptimizerSqlError, match="INSERT"):
        extract_referenced_tables(sql)


def test_comments_and_strings_do_not_trigger_unsafe_keywords():
    sql = """
    select 'drop table x; invalidate metadata y' as note
    from example_sales.orders
    -- delete from example_guarded.table; drop table example_other.secret_marker
    where comment_text = 'compute stats fake.table'
    """

    assert names(sql) == ["example_sales.orders"]
