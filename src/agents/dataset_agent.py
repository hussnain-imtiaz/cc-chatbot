import json
from src.agents.base import Agent
from src.agents.client_factory import make_client, get_model
from src.tools.sql_tools import dict_lookup, get_schema


INSTRUCTIONS = """You are a dataset and column selection agent for a CONTACT CENTRE database.

CRITICAL: This is CC data. You MUST select columns needed for CC-specific analysis:
- For staffing/capacity: need "In", "In Ans", "In Abnd", "Avg Tlk (Seconds Value)", agent counts
- For abandonment analysis: need "In Abnd", "In", date/time columns
- For service level: need "Avg Wait (Seconds Value)", "% Svc (Other Value)", "In Ans"
- For Erlang calculations: need traffic (calls), handle time, agent count, period
- For agent/queue analysis: need specific agent_name or queue_name filters
- Never assume generic metrics — CC analysis is precise and formula-based.

You receive a classified intent as JSON. You return a query plan as JSON.

Your job:
1. Pick which table(s) to query - pick all those that are relevant, but no more than needed. If intent is unclear, ask for clarification. Do not guess.
2. Identify the exact columns needed — think about what CC formula needs these inputs
3. Call get_schema() to confirm exact column names — never guess
4. Call dict_lookup() if you're unsure what a column measures
5. Return a query plan

If table is "all", plan a UNION query across estate, queues, and agents.
For a UNION plan, pick one meaningful metric that exists in all three tables
(e.g. COUNT(*) as row_count) and include table name as a column.

Return ONLY this JSON:
{
    "table": "estate | queues | agents | all",
    "query_type": "single | union",
    "columns_needed": ["exact column name from schema"],
    "filters": {
        "time_start": "YYYY-MM-DD",
        "time_end": "YYYY-MM-DD",
        "business_hours_only": true or false
    },
    "group_by": "column name or null",
    "order_by": "column name or null",
    "limit": number or null,
    "plain_english_plan": "one or two sentence what this will do"
}

Always call get_schema() first. Use exact column names as they appear.
Column names with spaces must be wrapped in double quotes in SQL.
No markdown, no explanation — just the JSON.
"""


def make_dataset_agent():
    return Agent(
        client=make_client(),
        name="DatasetAgent",
        instructions=INSTRUCTIONS,
        model=get_model("dataset"),
        tools=[dict_lookup, get_schema],
        response_format=dict,
        max_iterations=4,
    )


async def select_dataset(intent_result, agent=None):
    if agent is None:
        agent = make_dataset_agent()

    prompt = f"Build a query plan for this intent:\n\n{json.dumps(intent_result, indent=2)}"

    raw = await agent.run(prompt)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # safe fallback so downstream doesn't crash
        table = intent_result.get("table", "estate")
        return {
            "table": table,
            "query_type": "union" if table == "all" else "single",
            "columns_needed": [],
            "filters": {
                "time_start": intent_result.get("time_start", "2026-01-01"),
                "time_end": intent_result.get("time_end", "2026-01-31"),
                "business_hours_only": intent_result.get("business_hours_only", False),
            },
            "group_by": None,
            "order_by": None,
            "limit": None,
            "plain_english_plan": "query based on your question",
        }
