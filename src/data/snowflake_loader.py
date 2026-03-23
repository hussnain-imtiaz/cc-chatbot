import os
import sys
from pathlib import Path

import pandas as pd
import snowflake.connector
from snowflake.connector.pandas_tools import write_pandas


# connection details always come from env vars
def _get_conn():
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        password=os.environ["SNOWFLAKE_PASSWORD"],
        database="CC_ANALYTICS",
        schema="JANUARY",
        warehouse="CC_BOT_WH",
    )



def _prep_for_upload(df):
    df = df.copy()


    df["dt"] = df["dt"].dt.strftime("%Y-%m-%d %H:%M:%S")
    df["date"] = df["date"].apply(str)
    df["is_biz_hours"] = df["is_biz_hours"].astype(int)
    # df.columns = [c.upper() for c in df.columns]

    return df


def _fix_types_after_load(df, has_queue_name=False, has_agent_name=False):
    # df.columns = [c.lower() for c in df.columns]

    df["dt"] = pd.to_datetime(df["dt"], errors="coerce")

    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

    df["is_biz_hours"] = df["is_biz_hours"].astype(bool)

    df["hour"] = df["hour"].astype(int)

    df["queue_name"] = df["queue_name"].fillna("Unknown")

    df["agent_name"] = df["agent_name"].fillna("Unknown")

    return df


def _fetch_table(conn, table_name):
    cursor = conn.cursor()
    cursor.execute(f"SELECT * FROM {table_name}")
    # keep uppercase here - _fix_types_after_load lowercases them
    cols = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()
    cursor.close()
    return pd.DataFrame(rows, columns=cols)


def load_from_snowflake():
    """
    Load all three tables from Snowflake and return as a dict of DataFrames.
    Identical return format to load_all() in loader.py so db.py needs no changes.
    """
    print("Loading data from Snowflake...")
    conn = _get_conn()

    try:
        estate = _fix_types_after_load(_fetch_table(conn, "ESTATE"))
        queues = _fix_types_after_load(_fetch_table(conn, "QUEUES"), has_queue_name=True)
        agents = _fix_types_after_load(_fetch_table(conn, "AGENTS"), has_agent_name=True)

        print(f"  estate : {len(estate)} rows, {len(estate.columns)} cols")
        print(f"  queues : {len(queues)} rows, {len(queues.columns)} cols")
        print(f"  agents : {len(agents)} rows, {len(agents.columns)} cols")
    finally:
        conn.close()

    return {"estate": estate, "queues": queues, "agents": agents}

def _upload_table(conn, df, table_name):
    df_up = _prep_for_upload(df)

    success, nchunks, nrows, _ = write_pandas(
        conn,
        df_up,
        table_name=table_name,
        auto_create_table=True,    # creates table from the DataFrame schema - columns always exact
        overwrite=True,            # drop and recreate so re-running is always safe
        quote_identifiers=True,    # MUST be True - column names contain spaces and parentheses
                                   # e.g. "INTERVAL (MS EXCEL SERIAL VALUE)" - without quotes
                                   # Snowflake treats the parens as SQL syntax and the insert breaks
    )

    if success:
        print(f"  ✅ {table_name}: {nrows} rows uploaded")
    else:
        print(f"  ❌ {table_name}: upload failed")


def _run_upload():
    project_root = Path(__file__).parent.parent.parent
    sys.path.insert(0, str(project_root))
    from src.data.loader import load_all

    data_dir = project_root / "data"

    print(f"Reading CSVs from {data_dir} ...")
    dfs = load_all(str(data_dir))
    print(f"  estate : {len(dfs['estate'])} rows, {len(dfs['estate'].columns)} cols")
    print(f"  queues : {len(dfs['queues'])} rows, {len(dfs['queues'].columns)} cols")
    print(f"  agents : {len(dfs['agents'])} rows, {len(dfs['agents'].columns)} cols")

    print("\nConnecting to Snowflake...")
    conn = _get_conn()
    print("  ✅ Connected\n")

    print("Uploading...")
    _upload_table(conn, dfs["estate"], "ESTATE")
    _upload_table(conn, dfs["queues"], "QUEUES")
    _upload_table(conn, dfs["agents"], "AGENTS")

    conn.close()

    print("\n✅ Done. Verify in Snowflake:")
    print("   SELECT COUNT(*) FROM CC_ANALYTICS.JANUARY.ESTATE;   -- expect 744")
    print("   SELECT COUNT(*) FROM CC_ANALYTICS.JANUARY.QUEUES;   -- expect 2976")
    print("   SELECT COUNT(*) FROM CC_ANALYTICS.JANUARY.AGENTS;   -- expect 5208")


if __name__ == "__main__":
    _run_upload()