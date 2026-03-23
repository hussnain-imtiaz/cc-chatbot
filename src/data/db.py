import os
import sqlite3

# DATA_SOURCE env var controls where data comes from:
#   csv       → load from CSV files in the data/ folder (default, local dev)
#   snowflake → load from Snowflake (production)
DATA_SOURCE = os.getenv("DATA_SOURCE", "csv")

# single connection reused across all tool calls
# None until load_db() is called
_conn = None


def load_db(data_dir="data"):
    global _conn

    if _conn is not None:
        return _conn

    # choose data source based on env var
    if DATA_SOURCE == "snowflake":
        from src.data.snowflake_loader import load_from_snowflake
        dfs = load_from_snowflake()
    else:
        from src.data.loader import load_all
        dfs = load_all(data_dir)

    # in-memory sqlite - lives as long as the process does, zero disk setup
    # whether data came from CSV or Snowflake, it ends up here
    # this means all SQL tools work exactly the same way in both environments
    _conn = sqlite3.connect(":memory:", check_same_thread=False)

    dfs["estate"].to_sql("estate", _conn, index=False, if_exists="replace")
    dfs["queues"].to_sql("queues", _conn, index=False, if_exists="replace")
    dfs["agents"].to_sql("agents", _conn, index=False, if_exists="replace")

    # a simple view that shows what each table contains - the SQL agent uses this
    _conn.execute("""
        CREATE VIEW IF NOT EXISTS _tables AS
        SELECT 'estate' as table_name, 'whole contact centre hourly metrics' as description
        UNION ALL
        SELECT 'queues', 'per-queue hourly metrics — use for queue-level questions'
        UNION ALL
        SELECT 'agents', 'per-agent hourly metrics — use for individual agent questions'
    """)
    _conn.commit()

    source_label = "Snowflake" if DATA_SOURCE == "snowflake" else "CSV files"
    print(f"Database loaded from {source_label}")

    return _conn


def get_conn():
    # always call load_db first - this is just a safety getter
    if _conn is None:
        return load_db()
    return _conn
