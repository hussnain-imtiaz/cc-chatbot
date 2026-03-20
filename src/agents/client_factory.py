import os
from openai import AsyncOpenAI


def make_client(provider=None):
    return AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def get_model(agent_role, provider=None):

    openai_models = {
        "intent":    os.getenv("MODEL_MINI", "gpt-4o-mini"),
        "dataset":   os.getenv("MODEL_MINI", "gpt-4o-mini"),
        "sql":       os.getenv("MODEL_MAIN", "gpt-4o"),
        "formatter": os.getenv("MODEL_MINI", "gpt-4o-mini"),
    }


    bank = openai_models
    return bank.get(agent_role, "gpt-4o-mini")