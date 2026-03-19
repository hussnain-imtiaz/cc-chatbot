import asyncio
import inspect
import json
from dataclasses import dataclass, field

from openai import AsyncOpenAI
from pydantic import BaseModel


class Tool:
    # wraps a plain python function and generates the JSON schema
    # that OpenAI needs to know the function exists and what args it takes
    def __init__(self, fn, approval_mode="never_require"):
        self.fn = fn
        self.name = fn.__name__
        self.approval_mode = approval_mode
        # first line of docstring becomes the description the LLM sees
        self.description = (fn.__doc__ or "").strip().split("\n")[0]

    def __call__(self, *args, **kwargs):
        result = self.fn(*args, **kwargs)
        if asyncio.iscoroutine(result):
            return asyncio.get_event_loop().run_until_complete(result)
        return result

    def to_openai_schema(self):
        sig = inspect.signature(self.fn)
        props = {}
        required = []

        for param_name, param in sig.parameters.items():
            ann = param.annotation
            description = ""
            py_type = str

            # handles Annotated[str, "description"] from typing
            if hasattr(ann, "__metadata__"):
                py_type = ann.__args__[0]
                description = str(ann.__metadata__[0])
            elif ann is not inspect.Parameter.empty:
                py_type = ann

            type_map = {
                str: "string", int: "integer", float: "number",
                bool: "boolean", list: "array", dict: "object",
            }

            props[param_name] = {
                "type": type_map.get(py_type, "string"),
                "description": description,
            }

            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": props,
                    "required": required,
                },
            },
        }


def tool(approval_mode="never_require"):
    #  @tool decorator
    def decorator(fn):
        return Tool(fn, approval_mode=approval_mode)
    return decorator


@dataclass
class AgentSession:
    # stores conversation history so the agent remembers what was said before
    messages: list = field(default_factory=list)

    def add_user(self, text):
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, text):
        self.messages.append({"role": "assistant", "content": text})

    def clear(self):
        self.messages.clear()

    def to_list(self):
        return list(self.messages)

    def __len__(self):
        return len(self.messages)


class Agent:
    def __init__(self, client, name, instructions, model, tools=None,
                 response_format=None, max_iterations=5):
        self.client = client
        self.name = name
        self.instructions = instructions
        self.model = model
        self.tools = tools or []
        self.response_format = response_format
        self.max_iterations = max_iterations

    def create_session(self):
        return AgentSession()

    async def run(self, message, session=None, extra_context=None):
        system = self.instructions
        if extra_context:
            system += f"\n\nExtra context:\n{extra_context}"

        msgs = [{"role": "system", "content": system}]

        if session is not None:
            msgs.extend(session.to_list())
            session.add_user(message)

        msgs.append({"role": "user", "content": message})


        kwargs = {
            "model": self.model,
            "messages": msgs,
            "temperature": 0.1,
        }

        if self.tools:
            kwargs["tools"] = [t.to_openai_schema() for t in self.tools]
            kwargs["tool_choice"] = "auto"

        if self.response_format:
            kwargs["response_format"] = {"type": "json_object"}

        # agentic loop — keep going until the model stops calling tools
        for _ in range(self.max_iterations):
            resp = await self.client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            if not msg.tool_calls:
                # no more tool calls — this is the final answer
                content = msg.content or ""
                if session is not None:
                    session.add_assistant(content)
                return content

            # model wants to call tools — execute them and feed results back
            msgs.append({
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ],
            })

            for tc in msg.tool_calls:
                fn_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    args = {}

                matched_tool = next((t for t in self.tools if t.name == fn_name), None)

                if matched_tool:
                    try:
                        result = matched_tool(**args)
                        if asyncio.iscoroutine(result):
                            result = await result
                        result_str = str(result)
                        # metacognition: flag empty results so the model knows to retry
                        if not result_str or result_str.strip() in ("None", "{}"):
                            result_str = f"EMPTY_RESULT: {fn_name} returned nothing. try different params."
                    except Exception as e:
                        result_str = f"TOOL_ERROR in {fn_name}: {e}. try different params."
                else:
                    result_str = f"UNKNOWN_TOOL: {fn_name} not found."

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            kwargs["messages"] = msgs

        return "hit max iterations without a final answer. please rephrase."


class SequentialPipeline:
    # simplified version of WorkflowBuilder
    # runs agents one after another, each gets the previous output as input
    def __init__(self, agents):
        self.agents = agents

    async def run(self, initial_message):
        results = []
        context = initial_message

        for agent in self.agents:
            output = await agent.run(context)
            results.append({"agent": agent.name, "output": output})
            context = output

        return results