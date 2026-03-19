from pathlib import Path

try:
    from docx import Document
    HAS_DOCX = True
except ImportError:
    HAS_DOCX = False


# hardcoded fallback
FALLBACK = {
    "In": "Total inbound calls received in the hour.",
    "In Ans": "Number of inbound calls answered.",
    "In Abnd": "Number of inbound calls abandoned before answer.",
    "In Abnd Unique": "Unique abandoned calls (where applicable).",
    "Out": "Total outbound call attempts.",
    "Out Ans": "Outbound calls successfully answered.",
    "Out Fail": "Outbound calls not answered or failed.",
    "All": "Total calls (Inbound + Outbound).",
    "All Ans": "Total answered calls (Inbound + Outbound).",
    "Avg Wait (Seconds Value)": "Average wait time before answer.",
    "Max Wait (Seconds Value)": "Maximum observed wait time.",
    "Ans <= 15s": "Calls answered within 15 seconds (service level numerator).",
    "Abnd <= 60s": "Calls abandoned within 60 seconds.",
    "% Svc (Other Value)": "Service level percentage (typically based on 15s threshold).",
    "Avg Tlk (Seconds Value)": "Average talk time for answered calls.",
    "Tot Tlk (Seconds Value)": "Total talk time across all answered calls.",
    "Avg Call (Seconds Value)": "Average total call duration (talk + hold + ring).",
    "Tot Call (Seconds Value)": "Total call duration across all calls.",
    "Avg Held (Seconds Value)": "Average hold time.",
    "Tot Held (Seconds Value)": "Total hold time.",
    "Max Talk (Seconds Value)": "Longest talk time recorded.",
    "Max Call (Seconds Value)": "Longest total call duration recorded.",
    "Handling (Seconds Value)": "Time spent actively handling calls.",
    "Alerting (Seconds Value)": "Time calls were alerting/ringing before answer.",
    "Busy (Seconds Value)": "Time agent or queue was in a busy state.",
    "Available (Seconds Value)": "Time available for incoming calls.",
    "N/A (Seconds Value)": "Time not available (e.g. offline, break, admin).",
    "Max Concr": "Maximum concurrent calls observed in the interval.",
    "Esc": "Escalated calls.",
    "Trans In": "Calls transferred in.",
    "Trans Out": "Calls transferred out.",
    "OvrFd In": "Inbound calls overflowed to another destination.",
    "OvrFd Off": "Overflow calls not answered.",
    "Avg In Ans (Seconds Value)": "Average time to answer inbound calls.",
    "Avg Abnd (Seconds Value)": "Average time before abandonment.",
    "Avg Rng (In/Out) (Seconds Value)": "Average ringing duration for inbound and outbound.",
    "Tot Rng (Seconds Value)": "Total ringing duration.",
    "Avg Answer (Other Value)": "Average answer speed.",
}

# module-level cache — only parse the docx once
_kb = None


def build_kb(docx_path="data/data_dictionary.docx"):
    global _kb
    if _kb is not None:
        return _kb

    path = Path(docx_path)
    if not path.exists() or not HAS_DOCX:
        _kb = dict(FALLBACK)
        return _kb

    try:
        doc = Document(str(path))
        found = {}

        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                continue
            if " – " in text:
                col, definition = text.split(" – ", 1)
                found[col.strip()] = definition.strip()
            elif " - " in text and len(text) < 200:
                col, definition = text.split(" - ", 1)
                found[col.strip()] = definition.strip()

        # merge: docx definitions win, fallback fills any gaps
        _kb = {**FALLBACK, **found}
        return _kb

    except Exception:
        _kb = dict(FALLBACK)
        return _kb


def lookup_column(col_name, kb):
    if col_name in kb:
        return f"'{col_name}': {kb[col_name]}"

    # case-insensitive
    lower = {k.lower(): (k, v) for k, v in kb.items()}
    if col_name.lower() in lower:
        k, v = lower[col_name.lower()]
        return f"'{k}': {v}"

    # partial — does the search term appear inside the column name
    hits = [
        f"'{k}': {v}"
        for k, v in kb.items()
        if col_name.lower() in k.lower()
    ]
    if hits:
        return "\n".join(hits[:3])

    return f"No definition found for '{col_name}'."


def search_concept(concept, kb):
    # search by keyword in the definition text whic is used for "abandonment", "service level" etc
    hits = [
        f"'{k}': {v}"
        for k, v in kb.items()
        if concept.lower() in v.lower() or concept.lower() in k.lower()
    ]
    if not hits:
        return f"No columns found related to '{concept}'."
    return "\n".join(hits[:5])