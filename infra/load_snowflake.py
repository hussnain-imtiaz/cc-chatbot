import os
import snowflake.connector
from pathlib import Path
from snowflake.connector.pandas_tools import write_pandas
from dotenv import load_dotenv
load_dotenv()

# connection details come from env vars
ACCOUNT   = os.environ["SNOWFLAKE_ACCOUNT"]
USER      = os.environ["SNOWFLAKE_USER"]
PASSWORD  = os.environ["SNOWFLAKE_PASSWORD"]
DATABASE  = "CC_ANALYTICS"
SCHEMA    = "JANUARY"
WAREHOUSE = "CC_BOT_WH"

DATA_DIR = Path(__file__).parent.parent / "data"


def get_conn():
    return snowflake.connector.connect(
        account=ACCOUNT,
        user=USER,
        password=PASSWORD,
        database=DATABASE,
        schema=SCHEMA,
        warehouse=WAREHOUSE,
    )


def upload_table(conn, df, table_name):
    """Write a pandas DataFrame to a Snowflake table using write_pandas."""

    # snowflake wants uppercase column names by default
    # df.columns = [c.upper() for c in df.columns]

    # dt and date columns need to be strings for the upload to work cleanly
    for col in ["DT", "DATE"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    success, nchunks, nrows, _ = write_pandas(
        conn,
        df,
        table_name=table_name,
        overwrite=True,   # replace all rows each time - fine for a monthly snapshot
    )

    if success:
        print(f"  {table_name}: {nrows} rows uploaded")
    else:
        print(f"  {table_name}: upload failed")


def main():
    print("Loading CSVs from disk...")

    # use the existing loader so the derived columns (dt, hour, etc) are included
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from src.data.loader import load_all

    dfs = load_all(str(DATA_DIR))
    print(f"  estate: {len(dfs['estate'])} rows")
    print(f"  queues: {len(dfs['queues'])} rows")
    print(f"  agents: {len(dfs['agents'])} rows")

    print("\nConnecting to Snowflake...")
    conn = get_conn()
    print("  ✅ Connected")

    print("\nUploading tables...")
    upload_table(conn, dfs["estate"], "ESTATE")
    upload_table(conn, dfs["queues"], "QUEUES")
    upload_table(conn, dfs["agents"], "AGENTS")

    conn.close()
    print("\n✅ All done. Your Snowflake tables are ready.")


if __name__ == "__main__":
    main()
