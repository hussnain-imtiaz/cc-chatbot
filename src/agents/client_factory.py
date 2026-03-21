import os
from openai import AsyncOpenAI

# Basically idea here is to be able to expand this in the future to support multiple LLM providers, but for now we just have OpenAI.
# So we can have a single function that creates the client, and then we can have a function that gets the model based on the role of the agent.
def make_client():
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_model(role):
    return {
        "orchestrator": os.getenv("MODEL_MAIN", "gpt-4.1"),
        "sql":          os.getenv("MODEL_COMPLEX", "o4-mini"),
        "formatter":    os.getenv("MODEL_MINI", "gpt-4.1-mini"),
        "viz":          os.getenv("MODEL_NANO", "gpt-4.1-nano"),
    }.get(role, "gpt-4.1")
