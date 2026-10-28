"""Read-only trace of how a question is read by the query analyzer (diagnosis, not a feature).

Usage: python -m scripts.trace_query "Có bàn gì?" ["another question" ...]
Runs against a throw-away database built from the seed documents; nothing is written to runtime/.
`trace_pipeline` (used by tests/test_generalization.py) traces all stages including follow-up resolution and the gate.
"""
import sys
import tempfile
from pathlib import Path

from app.storage import Store


def trace(store, question):
    """What the analyzer kept, dropped, repaired and searched, and which documents came back."""
    info = {}
    found = store.fts_search(question, limit=12, trace=info)
    return {"question": question, **info, "found": [d["id"] for d in found]}


def trace_pipeline(store, settings, question, turn_context=None):
    """Every stage for one question: analysis, how a follow-up was resolved, the gate verdicts, the comparison computed in
    code and the final mode. Answers 'at which step did this question fail?'. No model is called (LLM/embedding off)."""
    from app.dialogue import resolve
    from app.services import question_answer
    analysis = store.analyze(question)
    resolution = resolve(store, analysis, turn_context)
    result = question_answer(store, settings, question, turn_context)
    return {"question": question, "analysis": analysis.trace(),
            "resolution": {"action": resolution.action, "bound": resolution.doc_id, "scope": resolution.scope,
                           "focus": resolution.focus},
            "gate_rejected": result["query_trace"].get("gate_rejected", {}),
            "sources": [{"id": s["id"], "condition": s.get("condition_status"), "detail": s.get("condition_detail")}
                        for s in result["sources"]],
            "mode": result["mode"], "turn_context": result["turn_context"],
            "verification": result.get("verification"), "answer_check": result.get("answer_check")}


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "trace.db")
        for question in argv:
            r = trace(store, question)
            print(f"\nQ: {question}\n  intent: {r['intent']}\n  terms: {r['terms']}  soft: {r['soft_terms']}"
                  f"\n  corrections: {r['corrections']}\n  dropped: {r['dropped']}\n  found: {r['found']}")


if __name__ == "__main__":
    main(sys.argv[1:])
