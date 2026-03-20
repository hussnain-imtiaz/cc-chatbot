import asyncio
import os
import streamlit as st
from dotenv import load_dotenv
from src.agents.analytics_agent import run_analytics

load_dotenv()

st.set_page_config(page_title="CC Chatbot", page_icon="📞", layout="wide")

# Initialize session state early — before any code tries to access it
if "messages" not in st.session_state:
    st.session_state.messages = []
if "agent" not in st.session_state:
    from src.agents.analytics_agent import make_agent
    from src.agents.base import AgentSession
    st.session_state.agent = make_agent()
    st.session_state.session = AgentSession()

st.title("📞 Contact Centre Analytics")
st.caption("January 2026 data — estate, queues, agents")


# lazy load — only create the agent once per session
def get_agent():
    return st.session_state.agent, st.session_state.session


def run_async(coro):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# --- chat history ---
for msg in st.session_state.get("messages", []):
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])


# --- input ---
user_input = st.chat_input("Ask something — e.g. which 5 agents handled the most calls?")

if user_input:
    if not os.getenv("OPENAI_API_KEY"):
        st.error("OPENAI_API_KEY not set — check your .env file")
        st.stop()

    agent, session = get_agent()

    # show user message
    with st.chat_message("user"):
        st.markdown(user_input)
    st.session_state.messages.append({"role": "user", "content": user_input})

    # run agent
    with st.chat_message("assistant"):
        with st.spinner("thinking..."):
            try:
                # response = run_async(agent.run(user_input, session=session))
                response = run_async(run_analytics(user_input, agent=agent, session=session))
                st.markdown(response)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except Exception as e:
                err = f"something went wrong: {e}"
                st.error(err)
                st.session_state.messages.append({"role": "assistant", "content": err})


# --- sidebar ---
with st.sidebar:
    st.markdown("### Try these")
    questions = [
        "What was the busiest hour in January?",
        "Which 5 agents handled the most calls?",
        "Which 3 queues had the highest average wait time during business hours?",
        "Compare inbound volume: first half vs second half of January",
        "Which queue had the lowest service level last week?",
        "How many calls were abandoned in January?",
    ]
    for q in questions:
        if st.button(q, use_container_width=True):
            # inject as if user typed it
            st.session_state.messages.append({"role": "user", "content": q})
            agent, session = get_agent()
            with st.spinner("thinking..."):
                try:
                    response = run_async(agent.run(q, session=session))
                    st.session_state.messages.append({"role": "assistant", "content": response})
                except Exception as e:
                    st.session_state.messages.append({"role": "assistant", "content": str(e)})
            st.rerun()

    st.divider()
    if st.button("clear chat", use_container_width=True):
        st.session_state.messages = []
        if "session" in st.session_state:
            st.session_state.session.clear()
        st.rerun()