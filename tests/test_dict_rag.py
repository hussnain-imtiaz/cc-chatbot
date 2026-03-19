import pytest
from src.data.dict_rag import build_kb, lookup_column, search_concept


@pytest.fixture(scope="module")
def kb():
    return build_kb()


# --- kb loading ---

def test_kb_has_entries(kb):
    assert len(kb) >= 30

def test_kb_has_key_columns(kb):
    must_have = ["In", "In Ans", "In Abnd", "Avg Wait (Seconds Value)", "% Svc (Other Value)"]
    for col in must_have:
        assert col in kb, f"Missing: {col}"

def test_kb_caches(kb):
    kb2 = build_kb()
    assert kb is kb2  # same object, not re-parsed


# --- exact lookup ---

def test_exact_match(kb):
    result = lookup_column("In Ans", kb)
    assert "In Ans" in result
    assert "answered" in result.lower()

def test_exact_match_svc(kb):
    result = lookup_column("% Svc (Other Value)", kb)
    assert "service" in result.lower() or "svc" in result.lower()


# --- case insensitive ---

def test_case_insensitive(kb):
    result = lookup_column("in ans", kb)
    assert "No definition found" not in result

def test_case_insensitive_uppercase(kb):
    result = lookup_column("IN ANS", kb)
    assert "No definition found" not in result


# --- partial match ---

def test_partial_match_wait(kb):
    result = lookup_column("wait", kb)
    assert "wait" in result.lower()

def test_partial_match_talk(kb):
    result = lookup_column("talk", kb)
    assert "talk" in result.lower()


# --- concept search ---

def test_concept_search_abandonment(kb):
    result = search_concept("abandonment", kb)
    assert "abnd" in result.lower() or "abandon" in result.lower()

def test_concept_search_service_level(kb):
    result = search_concept("service level", kb)
    assert "svc" in result.lower() or "service" in result.lower() or "15s" in result.lower()

def test_concept_not_found(kb):
    result = search_concept("xyzzy_not_real", kb)
    assert "No columns found" in result

def test_unknown_column(kb):
    result = lookup_column("definitely_not_a_column", kb)
    assert "No definition found" in result