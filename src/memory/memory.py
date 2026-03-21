from dataclasses import dataclass, field
from typing import Optional


KEEP_RECENT = 5
COMPRESS_AFTER = 10


# This is a simple in-memory conversation memory that tracks the last few turns of the conversation,
# along with some entity tracking to resolve pronouns and references.
@dataclass
class Turn:
    question: str
    table: Optional[str] = None
    entity_filter: Optional[dict] = None
    time_start: Optional[str] = None
    time_end: Optional[str] = None
    biz_hours: bool = False
    answer_summary: Optional[str] = None
    was_feedback: bool = False


@dataclass
class ConversationMemory:
    turns: list = field(default_factory=list)
    old_summary: Optional[str] = None

    # entity registry - tracks named things found in answers
    # so "her", "that queue", "same agent" can be resolved
    last_agent: Optional[str] = None
    last_queue: Optional[str] = None
    last_table: Optional[str] = None
    last_time_start: Optional[str] = None
    last_time_end: Optional[str] = None
    last_biz_hours: bool = False

    def add_turn(self, turn: Turn):
        self.turns.append(turn)
        if turn.table:
            self.last_table = turn.table
        if turn.time_start:
            self.last_time_start = turn.time_start
        if turn.time_end:
            self.last_time_end = turn.time_end
        self.last_biz_hours = turn.biz_hours

        if len(self.turns) > COMPRESS_AFTER:
            self._compress()

    def update_entities_from_results(self, results, table):
        if not results:
            return
        first = results[0]
        if table == "agents" and "agent_name" in first:
            self.last_agent = first["agent_name"]
        elif table == "queues" and "queue_name" in first:
            self.last_queue = first["queue_name"]
        elif table == "queues" and "Description" in first:
            self.last_queue = first["Description"]

    def _compress(self):
        to_compress = self.turns[:-KEEP_RECENT]
        self.turns = self.turns[-KEEP_RECENT:]
        lines = []
        for t in to_compress:
            parts = [f"Q: '{t.question}'"]
            if t.table:
                parts.append(f"table={t.table}")
            if t.entity_filter:
                parts.append(f"filtered to {t.entity_filter.get('value')}")
            if t.answer_summary:
                parts.append(f"result: {t.answer_summary}")
            lines.append(" | ".join(parts))
        chunk = "\n".join(lines)
        self.old_summary = (self.old_summary + "\n" + chunk) if self.old_summary else chunk

    def build_context(self):
        parts = []

        if self.old_summary:
            parts.append("Earlier in this session:")
            parts.append(self.old_summary)
            parts.append("")

        if self.turns:
            parts.append("Recent conversation:")
            for t in self.turns:
                parts.append(f"User asked: \"{t.question}\"")
                if t.entity_filter:
                    parts.append(f"  Filtered to: {t.entity_filter.get('column')} = '{t.entity_filter.get('value')}'")
                if t.table:
                    details = [f"table={t.table}"]
                    if t.time_start and t.time_end:
                        details.append(f"period={t.time_start} to {t.time_end}")
                    if t.biz_hours:
                        details.append("business hours")
                    parts.append(f"  Queried: {', '.join(details)}")
                if t.answer_summary:
                    parts.append(f"  Answer: {t.answer_summary}")
                if t.was_feedback:
                    parts.append("  (user gave feedback on this)")
                parts.append("")

        entity_lines = []
        if self.last_agent:
            entity_lines.append(f"last_agent = \"{self.last_agent}\"")
        if self.last_queue:
            entity_lines.append(f"last_queue = \"{self.last_queue}\"")
        if self.last_table:
            entity_lines.append(f"last_table = \"{self.last_table}\"")
        if self.last_time_start and self.last_time_end:
            entity_lines.append(f"last_period = {self.last_time_start} to {self.last_time_end}")
        if self.last_biz_hours:
            entity_lines.append("last_biz_hours = true")

        if entity_lines:
            parts.append("Entity registry (use to resolve pronouns like 'her', 'that queue', 'same period'):")
            parts.extend(entity_lines)

        return "\n".join(parts) if parts else None

    def flag_last_as_feedback(self):
        if self.turns:
            self.turns[-1].was_feedback = True

    def last_turn(self):
        return self.turns[-1] if self.turns else None

    def clear(self):
        self.turns.clear()
        self.old_summary = None
        self.last_agent = None
        self.last_queue = None
        self.last_table = None
        self.last_time_start = None
        self.last_time_end = None
        self.last_biz_hours = False
