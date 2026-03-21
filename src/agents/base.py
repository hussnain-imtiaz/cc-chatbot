import asyncio
import inspect
import json
from dataclasses import dataclass, field

from openai import AsyncOpenAI


# Models like o3-mini don't support temperature, so we need to check before setting it
def _model_supports_temperature(model_name):
    model_name = model_name.lower()
    # o-series models (o1, o3, o4, etc.) don't support temperature
    return not (model_name.startswith('o') and model_name[1].isdigit())


# Simple function wrapper to hold metadata and convert to OpenAI tool schema
class Tool:
    def __init__(self, fn, approval_mode="never_require"):
        self.fn = fn
        self.name = fn.__name__
        self.approval_mode = approval_mode
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

        for name, param in sig.parameters.items():
            ann = param.annotation
            description = ""
            py_type = str

            if hasattr(ann, "__metadata__"):
                py_type = ann.__args__[0]
                description = str(ann.__metadata__[0])
            elif ann is not inspect.Parameter.empty:
                py_type = ann

            type_map = {
                str: "string", int: "integer", float: "number",
                bool: "boolean", list: "array", dict: "object",
            }

            props[name] = {"type": type_map.get(py_type, "string"), "description": description}

            if param.default is inspect.Parameter.empty:
                required.append(name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {"type": "object", "properties": props, "required": required},
            },
        }


# Decorator for defining tools more easily
def tool(approval_mode="never_require"):
    def decorator(fn):
        return Tool(fn, approval_mode=approval_mode)
    return decorator


# Session class to track conversation history for an agent - Metacognition can be built on top of this by
# analyzing the session history and extra_context before each response to identify patterns or areas for improvement.
@dataclass
class AgentSession:
    messages: list = field(default_factory=list)

    def add_user(self, text):
        self.messages.append({"role": "user", "content": text})

    def add_assistant(self, text):
        self.messages.append({"role": "assistant", "content": text})

    def clear(self):
        self.messages.clear()

    def to_list(self):
        return list(self.messages)

    def last_n(self, n):
        return self.messages[-n:]

    def __len__(self):
        return len(self.messages)

# Base Agent class that can be extended for specific use cases.
# It handles the main loop of sending messages to the model, processing tool calls, and maintaining session history.
class Agent:
    def __init__(self, client, name, instructions, model,
                 tools=None, response_format=None, max_iterations=5):
        self.client = client
        self.name = name
        self.instructions = instructions
        self.model = model
        self.tools = tools or []
        self.response_format = response_format
        self.max_iterations = max_iterations
        self.last_usage = {"tokens_in": 0, "tokens_out": 0, "model": self.model}

    def create_session(self):
        return AgentSession()

    async def run(self, message, session=None, extra_context=None):
        self.last_usage = {"tokens_in": 0, "tokens_out": 0, "model": self.model}
        system = self.instructions
        if extra_context:
            system += f"\n\n{extra_context}"

        msgs = [{"role": "system", "content": system}]

        if session is not None:
            msgs.extend(session.to_list())

        msgs.append({"role": "user", "content": message})

        if session is not None:
            session.add_user(message)

        kwargs = {
            "model": self.model,
            "messages": msgs,
        }

        # Only set temperature for models that support it (not o-series)
        if _model_supports_temperature(self.model):
            kwargs["temperature"] = 0.1

        if self.tools:
            kwargs["tools"] = [t.to_openai_schema() for t in self.tools]
            kwargs["tool_choice"] = "auto"

        if self.response_format:
            kwargs["response_format"] = {"type": "json_object"}

        for _ in range(self.max_iterations):
            resp = await self.client.chat.completions.create(**kwargs)
            msg = resp.choices[0].message

            # token usage from this call
            if resp.usage:
                self.last_usage["tokens_in"] += resp.usage.prompt_tokens
                self.last_usage["tokens_out"] += resp.usage.completion_tokens
                self.last_usage["model"] = self.model

            if not msg.tool_calls:
                content = msg.content or ""
                if session is not None:
                    session.add_assistant(content)
                return content

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

                matched = next((t for t in self.tools if t.name == fn_name), None)

                if matched:
                    try:
                        result = matched(**args)
                        if asyncio.iscoroutine(result):
                            result = await result
                        result_str = str(result)
                        if not result_str or result_str.strip() in ("None", "{}"):
                            result_str = f"EMPTY_RESULT: {fn_name} returned nothing. try different parameters."
                    except Exception as e:
                        result_str = f"TOOL_ERROR in {fn_name}: {e}. try different parameters."
                else:
                    result_str = f"UNKNOWN_TOOL: {fn_name} not found."

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            kwargs["messages"] = msgs

        return "Could not reach a final answer. Please try rephrasing."
