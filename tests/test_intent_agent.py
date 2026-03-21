import json
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.intent_agent import detect_intent
from src.agents.base import Agent


def mock_agent_response(content):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = []
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def make_mock_agent(response_json):
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=mock_agent_response(json.dumps(response_json))
    )
    agent = Agent(
        client=client,
        name="IntentAgent",
        instructions="test",
        model="gpt-4o-mini",
        response_format=dict,
        max_iterations=1,
    )
    return agent


# clear intents

@pytest.mark.asyncio
async def test_top_agents_is_clear():
    agent = make_mock_agent({
        "intent": "top_n",
        "subject": "volume",
        "table": "agents",
        "time_start": "2026-01-01",
        "time_end": "2026-01-31",
        "business_hours_only": False,
        "n": 5,
        "is_clear": True,
        "clarification_question": None,
    })
    result = await detect_intent("which 5 agents handled the most calls?", agent=agent)
    assert result["intent"] == "top_n"
    assert result["table"] == "agents"
    assert result["is_clear"] is True
    assert result["clarification_question"] is None


@pytest.mark.asyncio
async def test_queue_wait_time_business_hours():
    agent = make_mock_agent({
        "intent": "top_n",
        "subject": "wait_time",
        "table": "queues",
        "time_start": "2026-01-01",
        "time_end": "2026-01-31",
        "business_hours_only": True,
        "n": 3,
        "is_clear": True,
        "clarification_question": None,
    })
    result = await detect_intent(
        "which 3 queues had the highest average wait time during business hours?",
        agent=agent
    )
    assert result["table"] == "queues"
    assert result["business_hours_only"] is True
    assert result["n"] == 3


@pytest.mark.asyncio
async def test_compare_halves():
    agent = make_mock_agent({
        "intent": "compare",
        "subject": "volume",
        "table": "estate",
        "time_start": "2026-01-01",
        "time_end": "2026-01-31",
        "business_hours_only": False,
        "n": None,
        "is_clear": True,
        "clarification_question": None,
    })
    result = await detect_intent(
        "compare inbound volume first half vs second half",
        agent=agent
    )
    assert result["intent"] == "compare"
    assert result["is_clear"] is True


# ambiguous intents - must ask clarification

@pytest.mark.asyncio
async def test_ambiguous_table_asks_clarification():
    agent = make_mock_agent({
        "intent": "aggregate",
        "subject": "volume",
        "table": "unclear",
        "time_start": "2026-01-01",
        "time_end": "2026-01-31",
        "business_hours_only": False,
        "n": None,
        "is_clear": False,
        "clarification_question": "Are you asking about the whole contact centre, a specific queue, or a specific agent?",
    })
    result = await detect_intent("how many unique working days are there", agent=agent)
    assert result["is_clear"] is False
    assert result["table"] == "unclear"
    assert result["clarification_question"] is not None
    assert len(result["clarification_question"]) > 0


@pytest.mark.asyncio
async def test_vague_question_asks_clarification():
    agent = make_mock_agent({
        "intent": "unknown",
        "subject": "other",
        "table": "unclear",
        "time_start": None,
        "time_end": None,
        "business_hours_only": False,
        "n": None,
        "is_clear": False,
        "clarification_question": "Could you be more specific about what you'd like to know?",
    })
    result = await detect_intent("how did we do?", agent=agent)
    assert result["is_clear"] is False
    assert result["clarification_question"] is not None


# bad JSON from model - graceful fallback

@pytest.mark.asyncio
async def test_bad_json_returns_clarification():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=mock_agent_response("this is not json at all")
    )
    agent = Agent(
        client=client, name="IntentAgent", instructions="test",
        model="gpt-4o-mini", response_format=dict, max_iterations=1,
    )
    result = await detect_intent("some question", agent=agent)
    # should not crash — should return a graceful clarification
    assert result["is_clear"] is False
    assert "clarification_question" in result


# time window resolution

@pytest.mark.asyncio
async def test_last_week_dates():
    agent = make_mock_agent({
        "intent": "aggregate",
        "subject": "abandonment",
        "table": "estate",
        "time_start": "2026-01-25",
        "time_end": "2026-01-31",
        "business_hours_only": False,
        "n": None,
        "is_clear": True,
        "clarification_question": None,
    })
    result = await detect_intent("how many calls were abandoned last week?", agent=agent)
    assert result["time_start"] == "2026-01-25"
    assert result["time_end"] == "2026-01-31"


@pytest.mark.asyncio
async def test_business_hours_flag():
    agent = make_mock_agent({
        "intent": "top_n",
        "subject": "wait_time",
        "table": "queues",
        "time_start": "2026-01-01",
        "time_end": "2026-01-31",
        "business_hours_only": True,
        "n": 3,
        "is_clear": True,
        "clarification_question": None,
    })
    result = await detect_intent(
        "which queues had longest wait during business hours?",
        agent=agent
    )
    assert result["business_hours_only"] is True