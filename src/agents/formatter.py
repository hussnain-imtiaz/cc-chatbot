import json
from src.agents.base import Agent
from src.agents.client_factory import make_client, get_model


INSTRUCTIONS = """You are a senior contact centre analyst presenting findings to a business audience.

CRITICAL: This is CONTACT CENTRE data. You MUST present results using CC-specific metrics and formulas:
- Traffic Intensity (Erlangs): not just raw call counts
- Erlang C implications: probability of wait/queue formation
- Abandonment Rate: as a percentage and business impact
- Average Handle Time (AHT): consistent metric for workload
- Service Level: with specific threshold times (e.g. 80% in 20 seconds)
- Staffing: use Erlang calculations, not linear scaling
- Never present this as generic tabular data. Every number has CC meaning.

You receive a question, the SQL that ran, and the raw results.
Write a clear, insightful response. Sound like an expert who actually understands the business.

Style:
- Lead with the most important finding
- For rankings, use a numbered list
- Convert raw seconds to readable format: 154s → 2m 34s
- Round percentages to 1 decimal place
- Highlight anything notable or surprising
- Keep it focused — no padding, no waffle
- Warm professional tone, not robotic
- Always remember data and domain is contact centre so always use accurate and consistent domain-specific knowledge and metrics, do not treat it like generic tabular data.
- Must flag when results seem unreliable or counterintuitive, e.g. "The abandonment rate appears unusually high at 25% or The average service level being 100.0%. which may indicate an issue with the data or a significant problem in the contact centre operations."
- Balance precision with accessibility — explain what the numbers mean for the business, not just what they are while noting caveats or limitations in the data quality or scope.
- Do not write too much — be concise and impactful. The user can ask follow-ups if they want more detail.
- No need to mention 'From a contact centre perspective' — just present the insights as a knowledgeable analyst would.

Always close with a clean provenance block:

---
Source: [table]
Period: [date range]
Filter: [business hours / all hours]
Rows: [count]
---

Never invent numbers. Only state what is in the results.
If results are empty, say so clearly and suggest what might have caused it.
"""


def make_formatter():
    return Agent(
        client=make_client(),
        name="Formatter",
        instructions=INSTRUCTIONS,
        model=get_model("formatter"),
        max_iterations=1,
    )


async def format_response(question, sql_result, plan, agent=None):
    if agent is None:
        agent = make_formatter()

    entity = plan.get("entity_filter")

    entity_note = ""
    if entity:
        entity_note = f"(filtered to {entity['column']} = '{entity['value']}')"

    results = sql_result.get("results", [])
    row_count = sql_result.get("row_count", 0)

    # truncate results to avoid context overflow
    MAX_ROWS = 20
    MAX_COLS = 15
    truncated = []
    for row in results[:MAX_ROWS]:
        items = list(row.items())[:MAX_COLS]
        truncated.append(dict(items))

    results_note = ""
    if len(results) > MAX_ROWS:
        results_note = f"\n(showing first {MAX_ROWS} of {row_count} rows)"
    if results and len(list(results[0].items())) > MAX_COLS:
        results_note += f"\n(showing first {MAX_COLS} of {len(results[0])} columns)"

    prompt = f"""Question: {question}
    SQL that ran:
    {sql_result.get("sql", "")}
    
    Results ({row_count} rows) {entity_note}:{results_note}
    {json.dumps(truncated, indent=2, default=str)}
    
    Provenance:
    Source: {plan.get("table", "unknown")}
    Period: {plan.get("time_start")} to {plan.get("time_end")}
    Filter: {"business hours only (08:00-17:59)" if plan.get("business_hours_only") else "all hours"}
    Rows: {row_count}
    """

    return await agent.run(prompt)
