import json
import pytest
from src.data.db import load_db
from src.tools.sql_tools import get_schema, run_sql, dict_lookup


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    load_db()


# get_schema

def test_schema_returns_all_tables():
    result = json.loads(get_schema(table_name="all"))
    assert "estate" in result
    assert "queues" in result
    assert "agents" in result

def test_schema_has_columns():
    result = json.loads(get_schema(table_name="estate"))
    cols = [c["name"] for c in result["estate"]["columns"]]
    assert "In" in cols
    assert "In Ans" in cols
    assert "hour" in cols
    assert "is_biz_hours" in cols

def test_schema_has_row_count():
    result = json.loads(get_schema(table_name="estate"))
    assert result["estate"]["total_rows"] == 744

def test_schema_single_table():
    result = json.loads(get_schema(table_name="queues"))
    assert "queues" in result
    assert "estate" not in result

def test_schema_has_note_about_quoting():
    result = json.loads(get_schema(table_name="estate"))
    assert "double quotes" in result["estate"]["note"]


# run_sql

def test_basic_select():
    r = json.loads(run_sql("SELECT COUNT(*) as n FROM estate"))
    assert r["results"][0]["n"] == 744

def test_select_with_filter():
    r = json.loads(run_sql("SELECT COUNT(*) as n FROM estate WHERE hour = 13"))
    assert r["results"][0]["n"] > 0

def test_quoted_column_name():
    # column names with spaces need double quotes
    r = json.loads(run_sql(
        'SELECT AVG("Avg Wait (Seconds Value)") as avg_wait FROM estate'
    ))
    assert r["results"][0]["avg_wait"] > 0

def test_group_by_returns_multiple_rows():
    r = json.loads(run_sql(
        "SELECT hour, SUM(\"In\") as total FROM estate GROUP BY hour ORDER BY hour"
    ))
    assert r["row_count"] == 24  # one row per hour

def test_top_agents_query():
    r = json.loads(run_sql("""
        SELECT agent_name, SUM("In Ans") as total_calls
        FROM agents
        GROUP BY agent_name
        ORDER BY total_calls DESC
        LIMIT 5
    """))
    assert r["row_count"] == 5
    assert "agent_name" in r["columns"]

def test_bad_column_returns_error_not_crash():
    r = json.loads(run_sql("SELECT definitely_not_a_column FROM estate"))
    assert "error" in r
    assert "hint" in r
    assert "results" not in r

def test_bad_table_returns_error_not_crash():
    r = json.loads(run_sql("SELECT * FROM made_up_table"))
    assert "error" in r

def test_non_select_blocked():
    r = json.loads(run_sql("DROP TABLE estate"))
    assert "error" in r
    assert r["error"] == "only SELECT queries allowed"

def test_update_blocked():
    r = json.loads(run_sql("UPDATE estate SET \"In\" = 0"))
    assert "error" in r

def test_result_includes_sql():
    r = json.loads(run_sql("SELECT COUNT(*) as n FROM estate"))
    assert "sql" in r

def test_business_hours_filter():
    # our is_biz_hours column should make this easy
    r = json.loads(run_sql("""
        SELECT COUNT(*) as n FROM estate WHERE is_biz_hours = 1
    """))
    biz_count = r["results"][0]["n"]
    r2 = json.loads(run_sql("SELECT COUNT(*) as n FROM estate"))
    total = r2["results"][0]["n"]
    # business hours should be less than total
    assert 0 < biz_count < total


# --- assignment questions answered with real SQL ---

def test_busiest_hour_is_during_business_hours():
    r = json.loads(run_sql("""
        SELECT hour, SUM("In") as calls
        FROM estate
        GROUP BY hour
        ORDER BY calls DESC
        LIMIT 1
    """))
    peak = r["results"][0]["hour"]
    assert 8 <= peak <= 17, f"peak hour {peak} should be business hours"

def test_top_3_queues_by_wait_biz_hours():
    r = json.loads(run_sql("""
        SELECT queue_name, AVG("Avg Wait (Seconds Value)") as avg_wait
        FROM queues
        WHERE is_biz_hours = 1
        GROUP BY queue_name
        ORDER BY avg_wait DESC
        LIMIT 3
    """))
    assert r["row_count"] == 3

def test_first_vs_second_half_comparison():
    r = json.loads(run_sql("""
        SELECT
            SUM(CASE WHEN date <= '2026-01-15' THEN "In" ELSE 0 END) as first_half,
            SUM(CASE WHEN date > '2026-01-15' THEN "In" ELSE 0 END) as second_half
        FROM estate
    """))
    row = r["results"][0]
    assert row["first_half"] > 0
    assert row["second_half"] > 0

# --- dict_lookup tool ---

def test_dict_lookup_exact():
    r = dict_lookup(term="In Ans")
    assert "answered" in r.lower()

def test_dict_lookup_concept():
    r = dict_lookup(term="abandonment")
    assert "abnd" in r.lower() or "abandon" in r.lower()

def test_dict_lookup_service_level():
    r = dict_lookup(term="service level")
    assert "svc" in r.lower() or "service" in r.lower() or "15s" in r.lower()

def test_dict_lookup_unknown():
    r = dict_lookup(term="xyzzy_not_real")
    assert "No definition found" in r or "No columns found" in r