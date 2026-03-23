import json
from src.agents.base import Agent
from src.agents.client_factory import make_client, get_model
from src.tools.sql_tools import get_schema, dict_lookup

INSTRUCTIONS = """You are a SQL expert for a contact centre SQLite database.

CRITICAL: This is CONTACT CENTRE data. You MUST write queries that extract data for CC-specific formulas:
- Traffic Intensity needs: call count, average handle time, period
- Erlang C needs: traffic intensity, number of agents, target service level
- Abandonment analysis needs: total calls, abandoned calls, trends by period
- Service Level needs: calls answered within threshold, total calls answered
- Staffing calculations need: current workload, desired service level metrics
- Never write generic aggregations — every SELECT must feed a CC formula.

Tables: estate, queues, agents. All data is January 2026 hourly rows.

You receive a confirmed query plan and write the SQL to execute it.

Rules:
- SELECT only. Never INSERT, UPDATE, DELETE, DROP.
- Always call get_schema() first to see exact column names.
- Wrap all column names containing spaces or brackets in double quotes.
  e.g. "Avg Wait (Seconds Value)", "% Svc (Other Value)", "In Ans"
- For business hours: WHERE is_biz_hours = 1
- For date ranges: WHERE date >= '2026-01-01' AND date <= '2026-01-31'
- For first half vs second half: use CASE WHEN date <= '2026-01-15' inside SUM()
- If entity_filter is present, add WHERE {column} = '{value}' to narrow to that entity.
  This is critical — if the plan says filter to agent_name='Nina Reed', the query MUST
  include WHERE agent_name = 'Nina Reed'
- Call dict_lookup() if unsure what a column measures.
- When asked for "stats" or "all metrics" for a specific entity, select the most
  meaningful 10-15 columns — not SELECT *. Good defaults for agents:
  agent_name, SUM("In Ans"), SUM("In"), SUM("In Abnd"), AVG("Avg Tlk (Seconds Value)"),
  SUM("Tot Tlk (Seconds Value)"), SUM("Handling (Seconds Value)"),
  SUM("Available (Seconds Value)"), SUM("Busy (Seconds Value)"),
  SUM("Ans <= 15s"), MAX("Max Concr")
  Always group by the entity column.

For UNION queries (table=all):
SELECT 'estate' as source, COUNT(*) as row_count FROM estate
UNION ALL
SELECT 'queues', COUNT(*) FROM queues
UNION ALL
SELECT 'agents', COUNT(*) FROM agents

Return ONLY this JSON:
{
    "sql": "complete SQL",
    "tables_used": ["table"],
    "columns_used": ["col1", "col2"],
    "explanation": "one plain-english sentence"
}
"""

### Can be used as a strict reference for not allowing the main problem of entirely in what the SQL agent is allowed to freely decide.
# MANDATORY CC FORMULA EXPRESSIONS - use these exact SQL fragments every time:
#
# Service level:
#   ROUND(100.0 * SUM("Ans <= 15s") / NULLIF(SUM("In"), 0), 1)
#   - denominator is ALWAYS "In" (total offered), NEVER "In Ans"
#   - NEVER use AVG("% Svc (Other Value)") — this column is unreliable in the estate table
#
# Abandonment rate:
#   ROUND(100.0 * SUM("In Abnd") / NULLIF(SUM("In"), 0), 2)
#   - denominator is ALWAYS "In" (total offered), NEVER "In Ans"
#
# AHT (Average Handle Time):
#   ROUND(SUM("Tot Tlk (Seconds Value)") / NULLIF(SUM("In Ans"), 0), 1)
#
# Traffic Intensity (Erlangs):
#   SUM("In") * (AVG("Avg Tlk (Seconds Value)") + AVG("Avg Held (Seconds Value)")) / 3600.0
#
# Utilisation:
#   ROUND(SUM("Handling (Seconds Value)") / NULLIF(SUM("Available (Seconds Value)") + SUM("Handling (Seconds Value)"), 0) * 100, 1)
#
# FORBIDDEN:
#   AVG("% Svc (Other Value)")  - always 100% in estate, meaningless, instead calculate service level from "Ans <= 15s" and "In"
#   "Int Agt ID"                - entirely null, never select this
#
# When writing any query involving service level, abandonment, AHT, or utilisation,
# you MUST copy the exact expression from FORMULA_CONSTANTS above.
# Do not derive your own version of these formulas.

def make_sql_agent():
    return Agent(
        client=make_client(),
        name="SQLAgent",
        instructions=INSTRUCTIONS,
        model=get_model("sql"),
        tools=[get_schema, dict_lookup],
        response_format=dict,
        max_iterations=6,
    )


async def generate_sql(plan, original_question, agent=None):
    if agent is None:
        agent = make_sql_agent()

    entity_note = ""
    if plan.get("entity_filter"):
        ef = plan["entity_filter"]
        entity_note = f"\nIMPORTANT: Filter results to where {ef['column']} = '{ef['value']}'"

    prompt = f"""Original question: {original_question}
    {entity_note}
    Query plan:
    {json.dumps(plan, indent=2)}
    
    Call get_schema() to verify column names, then write the SQL.
    """

    raw = await agent.run(prompt)

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {
            "sql": raw.strip(),
            "tables_used": [plan.get("table", "estate")],
            "columns_used": [],
            "explanation": "generated from query plan",
        }
