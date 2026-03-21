import json
import os
from src.agents.base import Agent
from src.agents.client_factory import make_client, get_model

CURRENT_DATE = os.getenv("CURRENT_DATE", "2026-01-31")

INSTRUCTIONS = f"""You are an intent classification agent for a contact centre analytics chatbot.
Today is {CURRENT_DATE}. The database has January 2026 data only.

Your only job: read the user message and classify it. Return JSON. Never answer.

You will receive recent conversation history as context above the question.
USE IT. Short follow-ups like "what about queues", "show last week", "same but
for agents" all refer to the previous topic - resolve them using history.

Return ONLY this JSON:
{{
    "intent": "aggregate | top_n | compare | peak | staffing | unknown",
    "subject": "volume | wait_time | abandonment | talk_time | service_level | availability | other",
    "table": "estate | queues | agents | all | unclear",
    "time_start": "YYYY-MM-DD",
    "time_end": "YYYY-MM-DD",
    "business_hours_only": true or false,
    "n": number or null,
    "is_clear": true or false,
    "clarification_question": "one short question or null"
}}

--- Intent types ---
aggregate: total, count, sum, average, how many, how much
top_n: top N, highest, lowest, best, worst, most, least, ranking
compare: first half vs second half, compare periods, difference between
peak: busiest, quietest, peak hour, when was highest or lowest
staffing: how many agents needed, erlang, staffing levels
unknown: truly cannot classify

--- Table ---
estate:  whole contact centre, no mention of specific queues or agents
queues:  mentions queues, queue names, queue-level
agents:  mentions agents, agent names, individual performance
all:     explicitly says all tables, all three, everything, across all
unclear: genuinely ambiguous — ask, do not default

No table mentioned - use logic:
- volume, calls, wait time, abandonment at whole-centre level → estate
- which agent, agent performance → agents
- which queue, queue service level → queues
- row count, how many rows, total records → unclear (ask)
- if even little bit of uncertainty, ask. Only default to estate/queues/agents if it's very clear.


--- Time ---
No time mentioned → 2026-01-01 to 2026-01-31, do NOT ask
"today" → 2026-01-31
"yesterday" → 2026-01-30
"last week" → 2026-01-25 to 2026-01-31
"first half" → 2026-01-01 to 2026-01-15
"second half" → 2026-01-16 to 2026-01-31
"business hours" → business_hours_only: true

--- When to set is_clear: false ---
ONLY when the answer would genuinely differ and you cannot resolve from context:
1. Table is unclear and it matters for the result
2. Time is truly ambiguous (e.g. "last period" with no history to resolve it)

Do NOT ask when:
- Context from conversation history resolves it
- No time mentioned (default January silently)
- Table is obviously implied
- The question works naturally at estate level

One question. Short. Give 2-3 options inline.
Good: "Which table: estate (whole centre), queues, or agents?"
Good: "Which period: last week (Jan 25-31), first half (Jan 1-15), or all January?"
"""

# things a person says when reacting to the previous answer
# not asking a new analytics question
FEEDBACK_SIGNALS = [
    # wrong / incorrect
    "not correct", "wrong", "incorrect", "not right", "not accurate",
    "that's wrong", "thats wrong", "not what i", "not what I",
    "that's not right", "thats not right", "doesn't look right",
    "looks wrong", "seems wrong", "that's off", "thats off",
    # dislike
    "did not like", "don't like", "dont like", "not happy",
    "not satisfied", "not good", "not useful", "not helpful",
    "same view", "still same", "same result", "same chart",
    "same plot", "same graph", "didn't change", "didnt change",
    "nothing changed", "looks the same", "still showing",
    # referring to the previous output directly
    "your plot", "that plot", "the plot", "your chart", "that chart",
    "the chart", "your graph", "that graph", "the graph",
    "your answer", "that answer", "your result", "that result",
    "the result", "the output", "your output", "this result",
    # action on previous output
    "fix it", "fix that", "fix the", "redo", "try again",
    "change the chart", "change the plot", "change it",
]

# This is a bit hacky but we want to catch when the user is giving feedback on the previous answer
def is_feedback(text):
    low = text.lower().strip()
    return any(signal in low for signal in FEEDBACK_SIGNALS)


def make_intent_agent():
    return Agent(
        client=make_client(),
        name="IntentAgent",
        instructions=INSTRUCTIONS,
        model=get_model("intent"),
        response_format=dict,
        max_iterations=1,
    )

# Classifies the user question. ConversationMemory for caching previous conversation history and context.
async def detect_intent(question, agent=None, memory=None):
    if agent is None:
        agent = make_intent_agent()

    extra = None
    if memory is not None:
        ctx = memory.build_context_for_intent_agent()
        if ctx:
            extra = ctx

    raw = await agent.run(question, extra_context=extra)

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {
            "intent": "unknown",
            "subject": "other",
            "table": "unclear",
            "time_start": "2026-01-01",
            "time_end": "2026-01-31",
            "business_hours_only": False,
            "n": None,
            "is_clear": False,
            "clarification_question": "Could you rephrase that?",
        }

    return result