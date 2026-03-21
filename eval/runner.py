import asyncio
import json
import time
import uuid
import os
import sys
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from src.agents.orchestrator import analyse
from src.memory.memory import ConversationMemory
from src.llmops.tracer import write_eval_result
from src.data.db import load_db

# gets synthetic questions from eval/golden_qa.json
def load_questions(path="eval/golden_qa.json"):
    with open(path) as f:
        return json.load(f)

# runs the eval and writes results to eval_results.jsonl
async def run_eval(subset=None, qa_path="eval/golden_qa.json"):
    questions = load_questions(qa_path)
    if subset:
        questions = [q for q in questions if q["id"] in subset]

    load_db()

    run_id = f"eval_{int(time.time())}_{str(uuid.uuid4())[:4]}"
    results = []

    print(f"\nRunning eval — {len(questions)} questions — run_id: {run_id}\n")

    for q in questions:
        try:
            plan = await analyse(q["question"], memory=ConversationMemory())

            got_table = plan.get("table", "")
            got_intent = plan.get("intent", "")

            table_ok = got_table == q["expected_table"]
            intent_ok = got_intent == q["expected_intent"]

            status = "PASS" if (table_ok and intent_ok) else "FAIL"
            print(f"  {status}  {q['id']}  table={got_table}({'+' if table_ok else '-'})  intent={got_intent}({'+' if intent_ok else '-'})")

            write_eval_result(
                run_id=run_id,
                question_id=q["id"],
                question=q["question"],
                expected_table=q["expected_table"],
                expected_intent=q["expected_intent"],
                got_table=got_table,
                got_intent=got_intent,
            )

            results.append({
                "id": q["id"],
                "table_correct": table_ok,
                "intent_correct": intent_ok,
            })

            await asyncio.sleep(0.3)

        except Exception as e:
            print(f"  ERROR  {q['id']}  {e}")
            traceback.print_exc()
            write_eval_result(
                run_id=run_id,
                question_id=q["id"],
                question=q["question"],
                expected_table=q["expected_table"],
                expected_intent=q["expected_intent"],
                got_table="",
                got_intent="",
                error=str(e),
            )
            results.append({"id": q["id"], "table_correct": False, "intent_correct": False})

    n = len(results)
    table_acc = sum(1 for r in results if r["table_correct"]) / n * 100
    intent_acc = sum(1 for r in results if r["intent_correct"]) / n * 100
    both_acc = sum(1 for r in results if r["table_correct"] and r["intent_correct"]) / n * 100

    print(f"\nResults:")
    print(f"  Table accuracy:   {table_acc:.1f}%")
    print(f"  Intent accuracy:  {intent_acc:.1f}%")
    print(f"  Both correct:     {both_acc:.1f}%")
    print(f"  Gate (>=90%):     {'PASS' if both_acc >= 90 else 'FAIL'}")

    return {
        "run_id": run_id,
        "n": n,
        "table_accuracy": round(table_acc, 1),
        "intent_accuracy": round(intent_acc, 1),
        "both_correct": round(both_acc, 1),
        "passed": both_acc >= 90,
        "results": results,
    }


if __name__ == "__main__":
    subset = sys.argv[1:] or None
    summary = asyncio.run(run_eval(subset=subset))
    if not summary["passed"]:
        sys.exit(1)