import os
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


DB_PATH = "llmops/traces.db"

# pricing per 1M tokens, input/output
MODEL_PRICING = {
    "gpt-5.4":      (2.50, 15.00),
    "gpt-5.4-mini": (0.75,  4.50),
    "gpt-5.4-nano": (0.20,  1.25),
    "gpt-5.4-pro":  (30.00, 180.00),
    "gpt-4.1":      (2.00,  8.00),
    "gpt-4.1-mini": (0.40,  1.60),
    "gpt-4.1-nano": (0.10,  0.40),
    "o4-mini":      (1.10,  4.40),
    "gpt-4o":       (2.50, 10.00),
    "gpt-4o-mini":  (0.15,  0.60),
    "o3-mini":      (1.10,  4.40),
}

# set up Azure Application Insights if the connection string is present
# if not set, we just skip it silently - local dev works the same way
_insights_client = None

def _get_insights_client():
    global _insights_client
    if _insights_client is not None:
        return _insights_client

    conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if not conn_str:
        return None

    try:
        from azure.monitor.opentelemetry.exporter import AzureMonitorTraceExporter
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        exporter = AzureMonitorTraceExporter(connection_string=conn_str)
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _insights_client = trace.get_tracer("cc-chatbot")
        print("Azure Application Insights connected")
    except Exception as e:
        # if the azure package is not installed or credentials are wrong, just skip it
        # we don't want monitoring to break the app
        print(f"App Insights setup skipped: {e}")
        _insights_client = None

    return _insights_client


@dataclass
class TraceRecord:
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    question: str = ""
    table_selected: Optional[str] = None
    intent: Optional[str] = None
    entity_filter: Optional[str] = None
    sql_generated: Optional[str] = None
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0
    models_used: str = ""
    error: Optional[str] = None
    ts: float = field(default_factory=time.time)

    def add_usage(self, model, tokens_in, tokens_out):
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        pricing = MODEL_PRICING.get(model, (2.50, 10.00))
        self.cost_usd += (tokens_in / 1_000_000 * pricing[0]
                          + tokens_out / 1_000_000 * pricing[1])
        if model not in self.models_used:
            self.models_used = (self.models_used + "," + model).strip(",")


def _ensure_db(path=DB_PATH):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY,
                ts REAL,
                question TEXT,
                table_selected TEXT,
                intent TEXT,
                entity_filter TEXT,
                sql_generated TEXT,
                tokens_in INTEGER,
                tokens_out INTEGER,
                cost_usd REAL,
                latency_ms INTEGER,
                models_used TEXT,
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS eval_runs (
                run_id TEXT,
                ts REAL,
                question_id TEXT,
                question TEXT,
                expected_table TEXT,
                expected_intent TEXT,
                got_table TEXT,
                got_intent TEXT,
                table_correct INTEGER,
                intent_correct INTEGER,
                error TEXT
            )
        """)
        conn.commit()

# writes a trace record to Azure Application Insights, if connected
def _write_to_insights(record: TraceRecord):
    tracer = _get_insights_client()
    if tracer is None:
        return

    try:
        with tracer.start_as_current_span("cc_chatbot_trace") as span:
            # custom attributes that we can query in the Azure portal
            span.set_attribute("question", record.question[:200])
            span.set_attribute("table_selected", record.table_selected or "")
            span.set_attribute("intent", record.intent or "")
            span.set_attribute("tokens_in", record.tokens_in)
            span.set_attribute("tokens_out", record.tokens_out)
            span.set_attribute("cost_usd", round(record.cost_usd, 6))
            span.set_attribute("latency_ms", record.latency_ms)
            span.set_attribute("models_used", record.models_used)
            span.set_attribute("has_error", bool(record.error))
    except Exception:
        # never let monitoring break the main app
        pass


def write_trace(record: TraceRecord, path=DB_PATH):
    # always write to local SQLite (works in dev and in the container)
    _ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            INSERT OR REPLACE INTO traces
            (trace_id, ts, question, table_selected, intent, entity_filter,
             sql_generated, tokens_in, tokens_out, cost_usd, latency_ms,
             models_used, error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            record.trace_id, record.ts, record.question, record.table_selected,
            record.intent, record.entity_filter,
            (record.sql_generated or "")[:500],
            record.tokens_in, record.tokens_out,
            round(record.cost_usd, 6), record.latency_ms,
            record.models_used, record.error,
        ))
        conn.commit()

    # also send to App Insights if connected - dual write, zero coupling
    _write_to_insights(record)


def write_eval_result(run_id, question_id, question, expected_table,
                      expected_intent, got_table, got_intent,
                      error=None, path=DB_PATH):
    _ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.execute("""
            INSERT INTO eval_runs
            (run_id, ts, question_id, question, expected_table, expected_intent,
             got_table, got_intent, table_correct, intent_correct, error)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_id, time.time(), question_id, question,
            expected_table, expected_intent,
            got_table, got_intent,
            int(got_table == expected_table),
            int(got_intent == expected_intent),
            error,
        ))
        conn.commit()


def read_traces(limit=100, path=DB_PATH):
    _ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM traces ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


def read_eval_runs(path=DB_PATH):
    _ensure_db(path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM eval_runs ORDER BY ts DESC"
        ).fetchall()
    return [dict(r) for r in rows]
