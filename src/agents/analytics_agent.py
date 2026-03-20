import json
import os
from src.agents.base import Agent
from src.agents.client_factory import make_client, get_model
from src.tools.sql_tools import ALL_TOOLS
from src.data.db import load_db


INSTRUCTIONS = """You are a contact centre analytics assistant.
You have access to three tables in a SQLite database:
- estate: whole contact centre hourly metrics for January 2026
- queues: per-queue hourly metrics
- agents: per-agent hourly metrics

The current date is 31 January 2026. All data covers January 2026.

Time references:
- "today" = 2026-01-31
- "yesterday" = 2026-01-30
- "last week" = 2026-01-25 to 2026-01-31
- "first half" = 2026-01-01 to 2026-01-15
- "second half" = 2026-01-16 to 2026-01-31
- "business hours" = use WHERE is_biz_hours = 1

How to answer questions:
1. Call get_schema() to see the exact column names for the relevant table
2. If unsure what a column measures, call dict_lookup()
3. Write a SQL query using the real column names you saw in the schema
4. Call run_sql() with that query
5. If run_sql returns an error, fix the SQL and try again
6. Return a clear answer with the key numbers

IMPORTANT: You MUST call run_sql() to get real data before answering.
Never state numbers without running a query first.
Always include the SQL you ran in your response.
"""


# these phrases appear when a model describes tool calls as text
# instead of actually calling them — dead giveaway of hallucination
HALLUCINATION_SIGNALS = [
    '"name": "run_sql"',
    '"name": "get_schema"',
    '{"name":',
    '"parameters":',
    '"arguments":',
    'i would call',
    'we can use the following query',
    'the query would be',
    'running this sql',
    'this query should return',
    'here\'s another attempt',
]


def looks_hallucinated(response):
    # if the model described a tool call as text instead of running it,
    # the JSON syntax leaks into the response
    low = response.lower()
    return any(signal.lower() in low for signal in HALLUCINATION_SIGNALS)


def make_agent():
    load_db()
    return Agent(
        client=make_client(),
        name="AnalyticsAgent",
        instructions=INSTRUCTIONS,
        model=get_model("sql"),
        tools=ALL_TOOLS,
        max_iterations=8,
    )


async def run_analytics(question, agent=None, session=None):
    if agent is None:
        agent = make_agent()

    response = await agent.run(question, session=session)

    if looks_hallucinated(response):
        return (
            "❌ Query failed to execute against real data. "
            "No answer given.\n\n"
            "Try switching to OpenAI (`LLM_PROVIDER=openai` in `.env`) "
            "or a larger Ollama model."
        )

    return response