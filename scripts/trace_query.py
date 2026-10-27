"""Read-only trace of how a question is turned into search terms (diagnosis, not a feature).

Usage: python -m scripts.trace_query "Có bàn gì?" ["another question" ...]
Runs against a throw-away database built from the seed documents; nothing is written to runtime/.
"""
import sys
import tempfile
from pathlib import Path

from app.storage import ALIASES, STOP, STOP_ACCENTED, Store, _raw_tokens, normalize


def trace(store, question):
    """Explain each query word: dropped (and why) or kept, then what the lexical search returns."""
    spoken = " ".join(normalize(question).split())
    for alias, canonical in ALIASES.items():
        spoken = spoken.replace(alias, canonical)
    words = []
    for raw in _raw_tokens(question):
        norm = normalize(raw).strip()
        if raw in STOP_ACCENTED:
            fate = "dropped: accented question word"
        elif norm in STOP:
            fate = "dropped: stopword"
        elif len(norm) < 2 and not norm.isdigit():
            fate = "dropped: too short"
        else:
            fate = "kept"
        words.append({"raw": raw, "normalized": norm, "fate": fate})
    kept = [w["normalized"] for w in words if w["fate"] == "kept"]
    found = store.fts_search(question, limit=12)
    if not kept:
        stage = "no query terms left after stopword filtering (search never ran)"
    elif not found:
        stage = "terms searched but no document passed the lexical relevance gate"
    else:
        stage = "documents found"
    return {"question": question, "normalized": spoken, "words": words, "terms": kept,
            "found": [d["id"] for d in found], "stage": stage}


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        store = Store(Path(tmp) / "trace.db")
        for question in argv:
            result = trace(store, question)
            print(f"\nQ: {question}\n  normalized: {result['normalized']}")
            for w in result["words"]:
                print(f"  {w['raw']!r:>12} -> {w['normalized']!r:<10} {w['fate']}")
            print(f"  terms: {result['terms']}\n  found: {result['found']}\n  stage: {result['stage']}")


if __name__ == "__main__":
    main(sys.argv[1:])
