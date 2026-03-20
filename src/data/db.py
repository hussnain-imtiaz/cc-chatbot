import sqlite3
import pandas as pd
from src.data.loader import load_all


# single connection reused across all tool calls
# None until load_db() is called
_conn = None


def load_db(data_dir="data"):
    global _conn

    if _conn is not None:
        return _conn

    dfs = load_all(data_dir)

    # in-memory sqlite — lives as long as the process does, zero disk setup
    _conn = sqlite3.connect(":memory:", check_same_thread=False)

    # write each dataframe as a table
    # also keep the derived columns we added in the loader (dt, date, hour, etc)
    dfs["estate"].to_sql("estate", _conn, index=False, if_exists="replace")
    dfs["queues"].to_sql("queues", _conn, index=False, if_exists="replace")
    dfs["agents"].to_sql("agents", _conn, index=False, if_exists="replace")

    # create a simple view that shows what each table contains — agent uses this
    _conn.execute("""
        CREATE VIEW IF NOT EXISTS _tables AS
        SELECT 'estate' as table_name, 'whole contact centre hourly metrics' as description
        UNION ALL
        SELECT 'queues', 'per-queue hourly metrics — use for queue-level questions'
        UNION ALL
        SELECT 'agents', 'per-agent hourly metrics — use for individual agent questions'
    """)
    _conn.commit()

    return _conn


def get_conn():
    # always call load_db first — this is just a safety getter
    if _conn is None:
        return load_db()
    return _conn