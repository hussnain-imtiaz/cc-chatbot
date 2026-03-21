import asyncio
import json
import os
import streamlit as st
from dotenv import load_dotenv
from src.agents.orchestrator import make_orchestrator
from src.agents.sql_agent import make_sql_agent
from src.agents.formatter import make_formatter
from src.agents.viz_agent import make_viz_agent
from src.memory.memory import ConversationMemory
from src.data.db import load_db
from src.agents.orchestrator import analyse
from src.agents.sql_agent import generate_sql
from src.tools.sql_tools import run_sql
from src.agents.formatter import format_response
from src.memory.memory import Turn
from src.guardrails.guardrails import check_input, is_reaction
from src.agents.viz_agent import plan_viz, build_chart

# load environment variables from .env file
load_dotenv()

st.set_page_config(page_title="CC Analytics", layout="centered", initial_sidebar_state="collapsed")

# Custom CSS to control the width of the chat interface
st.markdown("""
<style>
.block-container { max-width: 780px; padding-top: 1.5rem; padding-bottom: 5rem; }
div[data-testid="stChatInput"] { max-width: 780px; }
</style>
""", unsafe_allow_html=True)


for key, val in [
    ("messages",       []),
    ("stage",          None),
    ("stage_data",     None),
    ("last_question",  None),
    ("last_plan",      None),
    ("last_result",    None),
    ("agents_ready",   False),
]:
    if key not in st.session_state:
        st.session_state[key] = val

# Initialize agents and database connection on first run or when needed
def get_agents():
    if not st.session_state.agents_ready:
        load_db()

        st.session_state.orchestrator = make_orchestrator()
        st.session_state.sql_agent    = make_sql_agent()
        st.session_state.formatter    = make_formatter()
        st.session_state.viz_agent    = make_viz_agent()
        st.session_state.memory       = ConversationMemory()
        st.session_state.agents_ready = True

    return {
        "orchestrator": st.session_state.orchestrator,
        "sql":          st.session_state.sql_agent,
        "formatter":    st.session_state.formatter,
        "viz":          st.session_state.viz_agent,
        "memory":       st.session_state.memory,
    }

# Helper function to run async functions in Streamlit
def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            raise RuntimeError
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)

# Summarise the SQL result in a human-friendly way for memory and feedback purposes - METACOGNITION
def summarise_result(question, plan, sql_result):
    rows = sql_result.get("results", [])
    table = plan.get("table", "?")
    n = sql_result.get("row_count", 0)
    ef = plan.get("entity_filter")

    if not rows:
        return f"No results for '{question}' from {table}."

    first = rows[0]
    labels = [str(v) for k, v in first.items() if isinstance(v, str)
              and k not in ("dt", "date", "weekday", "Interval")]
    nums = [(k, v) for k, v in first.items() if isinstance(v, (int, float))]

    parts = [f"{n} rows from {table}"]
    if ef:
        parts.append(f"for {ef.get('value')}")
    if labels:
        parts.append(f"first entry: {labels[0]}")
    if nums:
        k, v = nums[0]
        parts.append(f"{k}={round(v, 2)}")

    return " | ".join(parts)

# Format the plan into a human-friendly string for display to the user before confirming the SQL generation
def format_plan_display(plan):
    lines = []
    ef = plan.get("entity_filter")

    lines.append(f"Table: {plan.get('table', '?')}")

    if ef:
        lines.append(f"Filtered to: {ef['column']} = '{ef['value']}'")

    cols = plan.get("columns_needed", [])
    if cols:
        lines.append(f"Columns: {', '.join(cols)}")

    f = plan.get("filters", {})
    if f.get("time_start") and f.get("time_end"):
        lines.append(f"Period: {f['time_start']} to {f['time_end']}")
    if f.get("business_hours_only"):
        lines.append("Filter: business hours only (08:00-17:59)")
    if plan.get("group_by"):
        lines.append(f"Group by: {plan['group_by']}")
    if plan.get("limit"):
        lines.append(f"Limit: top {plan['limit']}")
    if plan.get("plain_english_plan"):
        lines.append(f"\n{plan['plain_english_plan']}")
    if plan.get("reasoning"):
        lines.append(f"\nUnderstood as: {plan['reasoning']}")

    return "\n".join(lines)

# This will clear the current stage and data, used when the user wants to start over or after completing a stage
def clear_stage():
    st.session_state.stage = None
    st.session_state.stage_data = None

# runs orchestrates the pipeline from question to SQL generation, with clarification step
def run_pipeline(question, agents):
    memory = agents["memory"]
    plan = run_async(analyse(question, memory=memory, agent=agents["orchestrator"]))

    if plan.get("action") == "clarify":
        st.session_state.stage = "clarifying"
        st.session_state.stage_data = plan
    else:
        st.session_state.last_plan = plan
        st.session_state.stage = "plan"
        st.session_state.stage_data = plan


st.markdown("### Contact Centre Analytics")
st.caption("January 2026 — estate, queues, agents")
st.divider()

# Display the conversation history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("chart"):
            st.plotly_chart(msg["chart"], use_container_width=True)


stage = st.session_state.stage

# Depending on the current stage of the conversation, display different content and options to the user. The main stages are:
# - clarifying: the agent needs more information from the user before it can generate a plan
# - plan: the agent has generated a plan and is asking the user to confirm before generating SQL
# - sql: the agent has generated SQL and is showing it to the user, allowing them to edit before running
# - viz: the agent has generated a visualization spec and is asking the user if they want to see it
# - reaction: the user has indicated that something was wrong with the result, and the agent is asking for more details to understand what the issue was
if stage == "clarifying":
    plan = st.session_state.stage_data
    with st.chat_message("assistant"):
        st.write(plan.get("question", "Could you clarify what you're looking for?"))

elif stage == "plan":
    plan = st.session_state.stage_data
    with st.chat_message("assistant"):
        if plan.get("intent") and plan["intent"] != "unknown":
            st.markdown(f"**Intent:** {plan['intent'].title()}")
        st.markdown("Here is my query plan:")
        st.code(format_plan_display(plan), language=None)
        c1, c2 = st.columns([2, 5])
        with c1:
            if st.button("Yes, continue", type="primary", use_container_width=True):
                agents = get_agents()
                with st.spinner("Writing SQL..."):

                    sql_data = run_async(
                        generate_sql(plan, st.session_state.last_question, agent=agents["sql"])
                    )
                st.session_state.stage = "sql"
                st.session_state.stage_data = sql_data
                st.rerun()
        with c2:
            if st.button("No, start over", use_container_width=True):
                clear_stage()
                st.rerun()

elif stage == "sql":
    sql_data = st.session_state.stage_data
    sql = sql_data.get("sql", "")

    with st.chat_message("assistant"):
        st.markdown("Here is the SQL:")
        st.code(sql, language="sql")
        if sql_data.get("explanation"):
            st.caption(sql_data["explanation"])

        edited = st.text_area(
            "Edit if needed:",
            value=sql,
            height=110,
            key="sql_box",
            label_visibility="collapsed",
        )

        c1, c2 = st.columns([2, 5])
        with c1:
            run_clicked = st.button("Run query", type="primary", use_container_width=True)
        with c2:
            if st.button("Cancel", use_container_width=True):
                clear_stage()
                st.rerun()

        if run_clicked:
            agents = get_agents()
            plan = st.session_state.last_plan
            question = st.session_state.last_question
            memory = agents["memory"]

            with st.spinner("Running..."):


                raw_str = run_sql(sql=edited)
                raw = json.loads(raw_str)

                if "error" in raw:
                    msg_content = f"```sql\n{edited}\n```\n\nQuery failed: {raw['error']}\n\n{raw.get('hint', '')}"
                    st.session_state.messages.append({"role": "assistant", "content": msg_content})
                    clear_stage()
                    st.rerun()

                formatted = run_async(format_response(question, raw, plan, agent=agents["formatter"]))

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"```sql\n{edited}\n```\n\n{formatted}",
                })

                st.session_state.last_result = raw

                filters = plan.get("filters", {})
                memory.add_turn(Turn(
                    question=question,
                    table=plan.get("table"),
                    entity_filter=plan.get("entity_filter"),
                    time_start=filters.get("time_start"),
                    time_end=filters.get("time_end"),
                    biz_hours=filters.get("business_hours_only", False),
                    answer_summary=summarise_result(question, plan, raw),
                ))
                memory.update_entities_from_results(raw.get("results", []), plan.get("table", ""))

                viz_spec = run_async(plan_viz(raw, agent=agents["viz"]))
                if viz_spec:
                    st.session_state.stage = "viz"
                    st.session_state.stage_data = viz_spec
                else:
                    clear_stage()

                st.rerun()

elif stage == "viz":
    spec = st.session_state.stage_data
    with st.chat_message("assistant"):
        st.write(f"Want to see this as a {spec.get('chart_type', 'chart')}?")
        c1, c2 = st.columns([2, 5])
        with c1:
            if st.button("Show chart", use_container_width=True):

                fig = build_chart(spec, st.session_state.last_result)
                if fig:
                    st.session_state.messages.append({"role": "assistant", "content": "", "chart": fig})
                clear_stage()
                st.rerun()
        with c2:
            if st.button("No thanks", use_container_width=True):
                clear_stage()
                st.rerun()

elif stage == "reaction":
    with st.chat_message("assistant"):
        st.write("What was wrong — the numbers, the time period, the table, or the chart?")

elif stage == "reaction_answer":
    pass

# If we're not in a special stage, we treat the user input as a new question and run it through the pipeline.
user_input = st.chat_input("Ask about the January contact centre data...")

if user_input:
    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY is missing from .env")
        st.stop()

    agents = get_agents()
    memory = agents["memory"]

    st.session_state.messages.append({"role": "user", "content": user_input})


    ok, err = check_input(user_input)
    if not ok:
        st.session_state.messages.append({"role": "assistant", "content": err})
        st.rerun()

    if stage == "reaction":
        low = user_input.lower()
        if any(w in low for w in ["chart", "plot", "graph", "visual"]):
            last = st.session_state.last_result
            if last and last.get("results"):
                spec = run_async(plan_viz(last, agent=agents["viz"]))
                if spec:
                    fig = build_chart(spec, last)
                    if fig:
                        st.session_state.messages.append({"role": "assistant", "content": "", "chart": fig})
                        clear_stage()
                        st.rerun()
            st.session_state.messages.append({
                "role": "assistant",
                "content": "No alternative chart available for that data. Ask the question again and I'll re-run it.",
            })
        else:
            st.session_state.messages.append({
                "role": "assistant",
                "content": "Got it. Ask the question again with the correction and I'll run a fresh query.",
            })
        clear_stage()
        st.rerun()

    elif stage == "clarifying":
        st.session_state.last_question = user_input
        with st.spinner("Got it..."):
            run_pipeline(user_input, agents)
        st.rerun()

    elif is_reaction(user_input):
        memory.flag_last_as_feedback()
        st.session_state.messages.append({
            "role": "assistant",
            "content": "What was wrong — the numbers, the time period, the table, or the chart?",
        })
        st.session_state.stage = "reaction"
        st.session_state.stage_data = None
        st.rerun()

    else:
        st.session_state.last_question = user_input
        with st.spinner("Thinking..."):
            run_pipeline(user_input, agents)
        st.rerun()

# Some pre set Qs
with st.sidebar:
    st.markdown("**Try asking:**")
    questions = [
        "Which 5 agents handled the most calls in January?",
        "Which 3 queues had the highest average wait during business hours?",
        "Compare inbound volume: first half vs second half",
        "What was the busiest hour?",
        "How many calls were abandoned?",
        "How many rows are in each table?",
        "Which queue had the lowest service level last week?",
        "If abandonment rises 20%, how many more agents are needed?",
    ]
    for q in questions:
        if st.button(q, use_container_width=True, key=f"sb_{q[:25]}"):
            agents = get_agents()
            st.session_state.last_question = q
            st.session_state.messages.append({"role": "user", "content": q})
            with st.spinner("Thinking..."):
                run_pipeline(q, agents)
            st.rerun()

    st.divider()
    if st.button("Clear conversation", use_container_width=True):
        for k in ["messages", "stage", "stage_data", "last_question", "last_plan", "last_result"]:
            st.session_state[k] = [] if k == "messages" else None
        if "memory" in st.session_state:
            st.session_state.memory.clear()
        st.rerun()
