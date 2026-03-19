import pytest
import pandas as pd
from datetime import datetime
from src.data.loader import parse_string_interval, parse_excel_serial, load_all


# --- timestamp parsing ---
def test_string_interval_normal():
    result = parse_string_interval("01/01/2026 (09:00:00 - 09:59:59)")
    assert result == datetime(2026, 1, 1, 9, 0, 0)

def test_string_interval_midnight():
    result = parse_string_interval("31/01/2026 (00:00:00 - 00:59:59)")
    assert result == datetime(2026, 1, 31, 0, 0, 0)

def test_string_interval_handles_null():
    # this is the null row we saw — should not crash
    result = parse_string_interval(None)
    assert isinstance(result, datetime)

def test_excel_serial_jan1():
    # 46023 should be 2026-01-01 — verified by hand
    result = parse_excel_serial(46023.0)
    assert result.year == 2026
    assert result.month == 1
    assert result.day == 1

def test_excel_serial_handles_null():
    result = parse_excel_serial(float("nan"))
    assert isinstance(result, datetime)


# --- actual loaded dataframes ---

@pytest.fixture(scope="module")
def dfs():
    return load_all()

def test_estate_row_count(dfs):
    # 31 days * 24 hours = 744, minus 1 null row we drop
    assert len(dfs["estate"]) == 744

def test_queues_has_queue_name_col(dfs):
    assert "queue_name" in dfs["queues"].columns

def test_agents_has_agent_name_col(dfs):
    assert "agent_name" in dfs["agents"].columns

def test_all_have_biz_hours_col(dfs):
    for name, df in dfs.items():
        assert "is_biz_hours" in df.columns, f"{name} missing is_biz_hours"

def test_biz_hours_are_8_to_17(dfs):
    biz = dfs["estate"][dfs["estate"]["is_biz_hours"]]
    assert biz["hour"].min() == 8
    assert biz["hour"].max() == 17

def test_date_range_is_january_2026(dfs):
    for name, df in dfs.items():
        assert str(df["dt"].min().date()) == "2026-01-01", f"{name} starts wrong"
        assert str(df["dt"].max().date()) == "2026-01-31", f"{name} ends wrong"

def test_no_nulls_in_dt_column(dfs):
    for name, df in dfs.items():
        assert df["dt"].isna().sum() == 0, f"{name} has null dt values"

def test_caching_returns_same_object(dfs):
    # load_all() should return the same dict — not re-read the files
    dfs2 = load_all()
    assert dfs["estate"] is dfs2["estate"]