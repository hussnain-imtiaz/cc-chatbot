MAX_INPUT_LENGTH = 1000

INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "forget everything",
    "you are now",
    "act as",
    "pretend you are",
    "system prompt",
    "jailbreak",
    "override instructions",
]

OFF_TOPIC_PATTERNS = [
    "password", "credit card", "social security",
    "hack ", "exploit", "malware", "rm -rf",
    "drop table", "delete from", "truncate",
]


def check_input(text: str):
    if not text or not text.strip():
        return False, "Please type a question."

    if len(text) > MAX_INPUT_LENGTH:
        return False, f"That's a bit long. Could you keep it under {MAX_INPUT_LENGTH} characters?"

    low = text.lower()

    for pattern in INJECTION_PATTERNS:
        if pattern in low:
            return False, "I can only help with contact centre analytics questions."

    for pattern in OFF_TOPIC_PATTERNS:
        if pattern in low:
            return False, "I can only help with contact centre analytics questions."

    return True, None


REACTION_SIGNALS = [
    "not correct", "wrong", "incorrect", "not right", "not accurate",
    "that's wrong", "thats wrong", "not what i", "not what I",
    "that's not right", "doesn't look right", "looks wrong", "seems wrong",
    "did not like", "don't like", "dont like", "not happy",
    "not satisfied", "same view", "still same", "same result",
    "same chart", "same plot", "nothing changed", "looks the same",
    "your plot", "that plot", "the plot", "your chart", "that chart",
    "your graph", "your answer", "that answer", "your result",
    "that result", "the result", "fix it", "fix that", "redo",
    "try again", "change the chart", "change the plot",
    "didn't change", "didnt change", "still showing",
]


def is_reaction(text: str) -> bool:
    low = text.lower().strip()
    return any(s in low for s in REACTION_SIGNALS)
