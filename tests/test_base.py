import pytest
import asyncio
from typing import Annotated
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.base import tool, Tool, AgentSession, Agent


# --- @tool decorator ---

@tool()
def sample_tool(
    city: Annotated[str, "the city name"],
    limit: Annotated[int, "max results"] = 5,
) -> str:
    "Gets data for a city."
    return f"data for {city}"


def test_tool_name():
    assert sample_tool.name == "sample_tool"

def test_tool_description():
    assert sample_tool.description == "Gets data for a city."

def test_tool_callable():
    result = sample_tool(city="London", limit=3)
    assert result == "data for London"

def test_tool_schema_structure():
    schema = sample_tool.to_openai_schema()
    assert schema["type"] == "function"
    assert schema["function"]["name"] == "sample_tool"
    assert "city" in schema["function"]["parameters"]["properties"]
    assert "limit" in schema["function"]["parameters"]["properties"]

def test_tool_required_params():
    schema = sample_tool.to_openai_schema()
    required = schema["function"]["parameters"]["required"]
    # city has no default so it's required, limit has default=5 so it's not
    assert "city" in required
    assert "limit" not in required

def test_tool_param_types():
    schema = sample_tool.to_openai_schema()
    props = schema["function"]["parameters"]["properties"]
    assert props["city"]["type"] == "string"
    assert props["limit"]["type"] == "integer"

def test_tool_param_descriptions():
    schema = sample_tool.to_openai_schema()
    props = schema["function"]["parameters"]["properties"]
    assert props["city"]["description"] == "the city name"
    assert props["limit"]["description"] == "max results"


# --- AgentSession ---

def test_session_starts_empty():
    s = AgentSession()
    assert len(s) == 0

def test_session_add_user():
    s = AgentSession()
    s.add_user("hello")
    assert s.to_list() == [{"role": "user", "content": "hello"}]

def test_session_add_assistant():
    s = AgentSession()
    s.add_assistant("hi there")
    assert s.to_list() == [{"role": "assistant", "content": "hi there"}]

def test_session_multi_turn():
    s = AgentSession()
    s.add_user("q1")
    s.add_assistant("a1")
    s.add_user("q2")
    assert len(s) == 3

def test_session_clear():
    s = AgentSession()
    s.add_user("something")
    s.clear()
    assert len(s) == 0

def test_session_to_list_is_copy():
    s = AgentSession()
    s.add_user("hi")
    lst = s.to_list()
    lst.append({"role": "user", "content": "injected"})
    # original should be unchanged
    assert len(s) == 1


# --- Agent.run() with mocked OpenAI ---

def make_mock_response(content=None, tool_calls=None):
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls or []
    choice = MagicMock()
    choice.message = msg
    resp = MagicMock()
    resp.choices = [choice]
    return resp


@pytest.mark.asyncio
async def test_agent_returns_text_when_no_tools_called():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=make_mock_response(content="Paris is lovely in spring.")
    )

    agent = Agent(client=client, name="test", instructions="you are helpful",
                  model="gpt-4o-mini")
    result = await agent.run("tell me about Paris")
    assert result == "Paris is lovely in spring."


@pytest.mark.asyncio
async def test_agent_saves_response_to_session():
    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        return_value=make_mock_response(content="answer here")
    )

    agent = Agent(client=client, name="test", instructions="helpful",
                  model="gpt-4o-mini")
    session = agent.create_session()
    await agent.run("question", session=session)
    assert len(session) == 2  # user message + assistant response


@pytest.mark.asyncio
async def test_agent_calls_tool_and_returns_final():
    # simulate: model says call a tool, then after tool result says final answer
    tool_call = MagicMock()
    tool_call.id = "call_abc"
    tool_call.function.name = "sample_tool"
    tool_call.function.arguments = '{"city": "Rome"}'

    first_resp = make_mock_response(content=None, tool_calls=[tool_call])
    second_resp = make_mock_response(content="Rome has great food.")

    client = AsyncMock()
    client.chat.completions.create = AsyncMock(
        side_effect=[first_resp, second_resp]
    )

    agent = Agent(client=client, name="test", instructions="helpful",
                  model="gpt-4o-mini", tools=[sample_tool])
    result = await agent.run("tell me about Rome")
    assert result == "Rome has great food."
    # should have called OpenAI twice — once to get tool call, once for final answer
    assert client.chat.completions.create.call_count == 2