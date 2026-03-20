import json
import sqlite3
from typing import Annotated

from src.agents.base import tool
from src.data.db import get_conn
from src.data.dict_rag import build_kb, lookup_column, search_concept


@tool()
def get_schema(
    table_name: Annotated[str, "table to inspect: 'estate', 'queues', 'agents', or 'all'"] = "all",
) -> str:
    """
    Returns table names, column names with types, and one sample row.
    Always call this before writing any SQL so you know the exact column names.
    Column names with spaces or special characters must be wrapped in double quotes in SQL.
    """
    conn = get_conn()
    cursor = conn.cursor()

    tables = ["estate", "queues", "agents"] if table_name == "all" else [table_name]

    output = {}

    for t in tables:
        try:
            # get column names and types
            cursor.execute(f"PRAGMA table_info({t})")
            cols = [{"name": row[1], "type": row[2]} for row in cursor.fetchall()]

            # one sample row so the agent can see what values look like
            cursor.execute(f'SELECT * FROM "{t}" LIMIT 1')
            row = cursor.fetchone()
            col_names = [c["name"] for c in cols]
            sample = dict(zip(col_names, row)) if row else {}

            # only show a subset of the sample — too much noise otherwise
            # show the timing cols + a few key metrics
            interesting = ["Interval", "dt", "date", "hour", "weekday", "is_biz_hours",
                          "Description", "queue_name", "agent_name",
                          "In", "In Ans", "In Abnd", "Avg Wait (Seconds Value)",
                          "% Svc (Other Value)", "Avg Tlk (Seconds Value)"]
            sample_trimmed = {k: v for k, v in sample.items() if k in interesting}

            output[t] = {
                "columns": cols,
                "sample_row": sample_trimmed,
                "total_rows": conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0],
                "note": "wrap column names containing spaces/brackets in double quotes e.g. \"Avg Wait (Seconds Value)\""
            }
        except Exception as e:
            output[t] = {"error": str(e)}

    return json.dumps(output, indent=2, default=str)


@tool()
def run_sql(
    sql: Annotated[str, "the SQL SELECT query to run against the contact centre database"],
) -> str:
    """
    Executes a SQL SELECT query against the contact centre database and returns results as JSON.
    Only SELECT statements are allowed.
    If the query fails, the error message is returned so you can fix the SQL and retry.
    Tables available: estate, queues, agents.
    Always use double quotes around column names that contain spaces or special characters.
    """
    # safety: only allow SELECT — no drops, updates, inserts
    stripped = sql.strip().upper()
    if not stripped.startswith("SELECT") and not stripped.startswith("WITH"):
        return json.dumps({
            "error": "only SELECT queries allowed",
            "your_query": sql,
        })

    conn = get_conn()

    try:
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        col_names = [d[0] for d in cursor.description]

        results = [dict(zip(col_names, row)) for row in rows]

        return json.dumps({
            "sql": sql,
            "row_count": len(results),
            "columns": col_names,
            "results": results,
        }, default=str)

    except sqlite3.OperationalError as e:
        # SQL was invalid — return the error so the agent can retry
        return json.dumps({
            "error": str(e),
            "hint": "check column names with get_schema() — they may need double quotes",
            "your_query": sql,
        })
    except Exception as e:
        return json.dumps({"error": str(e), "your_query": sql})


@tool()
def dict_lookup(
    term: Annotated[str, "column name or concept to look up e.g. 'In Ans', 'abandonment', 'service level'"],
) -> str:
    """
    Looks up what a column or concept means from the data dictionary.
    Call this when you're unsure what a column measures before using it in SQL.
    Also works for concepts like 'abandonment', 'service level', 'talk time'.
    """
    kb = build_kb()

    # try exact / partial column match first
    result = lookup_column(term, kb)
    if "No definition found" not in result:
        return result

    # fall back to concept search
    return search_concept(term, kb)


ALL_TOOLS = [get_schema, run_sql, dict_lookup]