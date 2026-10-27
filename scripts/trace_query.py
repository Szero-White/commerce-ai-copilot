"""Read-only trace of how a question is read by the query analyzer (diagnosis, not a feature).

Usage: python -m scripts.trace_query "Có bàn gì?" ["another question" ...]
Runs against a throw-away database built from the seed documents; nothing is written to runtime/.
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
