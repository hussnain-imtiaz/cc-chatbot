import json
from src.agents.base import Agent
from src.agents.client_factory import make_client, get_model
import pandas as pd
import plotly.express as px

INSTRUCTIONS = """You decide if query results can be usefully visualised as a chart.

Rules:
- Only offer if there are 2 or more rows
- Must have at least one numeric column AND one label or time column
- Single-value results → should_offer: false
- Rankings with labels + numbers → bar chart
- Time-based data (hour, date) + metric → line chart
- Comparisons between two groups → bar chart

Return ONLY this JSON:
{
    "should_offer": true or false,
    "chart_type": "bar | line | null",
    "x_column": "column name or null",
    "y_column": "column name or null",
    "title": "short chart title or null"
}
"""


def make_viz_agent():
    return Agent(
        client=make_client(),
        name="VizAgent",
        instructions=INSTRUCTIONS,
        model=get_model("viz"),
        response_format=dict,
        max_iterations=1,
    )


async def plan_viz(sql_result, agent=None):
    if agent is None:
        agent = make_viz_agent()

    results = sql_result.get("results", [])
    columns = sql_result.get("columns", [])

    if len(results) <= 1 or len(columns) < 2:
        return None

    if results:
        has_numeric = any(isinstance(results[0].get(c), (int, float)) for c in columns)
        if not has_numeric:
            return None

    prompt = f"""Columns: {columns}
Rows: {len(results)}
Sample:
{json.dumps(results[:5], indent=2, default=str)}
"""

    raw = await agent.run(prompt)

    try:
        spec = json.loads(raw)
    except json.JSONDecodeError:
        return None

    return spec if spec.get("should_offer") else None


def build_chart(spec, sql_result):
    try:
        results = sql_result.get("results", [])
        if not results:
            return None

        df = pd.DataFrame(results)
        x = spec.get("x_column")
        y = spec.get("y_column")
        title = spec.get("title", "")
        chart_type = spec.get("chart_type", "bar")

        if not x or not y or x not in df.columns or y not in df.columns:
            return None

        df[y] = pd.to_numeric(df[y], errors="coerce")

        if chart_type == "line":
            fig = px.line(df, x=x, y=y, title=title, markers=True)
        else:
            fig = px.bar(df, x=x, y=y, title=title)

        fig.update_layout(
            plot_bgcolor="white",
            paper_bgcolor="white",
            margin=dict(l=20, r=20, t=40, b=20),
            font=dict(size=13),
        )
        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridcolor="#f0f0f0")

        return fig

    except Exception:
        return None
