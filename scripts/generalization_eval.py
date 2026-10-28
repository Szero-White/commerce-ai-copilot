"""Capability-grouped evaluation on a throw-away database (offline: LLM and embeddings OFF, nothing is sent anywhere).

Usage:  python -m scripts.generalization_eval [--cases data/eval_generalization/dev.json] [--out reports/x.json]

The cases file carries its own synthetic `documents` (and optional `uploads`), so a NEW file of questions about NEW documents
can be run without touching the code. Five measures are reported SEPARATELY and never merged into one accuracy number:
* retrieval        - turns with `hit` / `hit_any` / `hit_prefix`: the expected document is among the sources (Hit@3)
* answer           - turns with `contains` / `not_contains`: facts the shown answer must (not) state
* groundedness     - turns with `forbid`: no source outside the expected subject (wrong product / wrong policy)
* refusal          - turns with `refuse` / `clarify`: no source and "not enough information", or a question back
* multi_turn       - every checked turn of cases in the group "6 multi-turn" (context carried by the previous turn_context)
Both passes AND failures are written to the report. This measures the retrieval/gate/dialogue code on the extractive answer; it
does NOT say anything about a live model's wording (use scripts/live_eval.py with a key for that).
"""
import argparse
import json
import sys
import tempfile
from pathlib import Path

from app.config import ROOT, Settings
from app.documents import parse_upload
from app.services import question_answer
from app.storage import Store

DEFAULT = ROOT / "data" / "eval_generalization" / "dev.json"
MULTI_TURN = "6 multi-turn"


def load_store(spec, tmp):
    store = Store(Path(tmp) / "eval.db")
    for d in store.documents():                      # only the case file's documents: nothing of the demo catalogue
        store.delete(d["id"])
    settings = Settings(data_path=Path(tmp) / "eval.db", llm_provider="off", embedding_provider="off")
    store.apply([{**d, "source": "eval"} for d in spec.get("documents", [])], source="eval")
    for up in spec.get("uploads", []):
        parsed = parse_upload(up["filename"], up["text"].encode("utf-8"), settings)
        store.apply(parsed["documents"], source=parsed["source"], replace=True)
    return store, settings


def check_turn(turn, result):
    """{measure: (passed, why)} for the measures this turn declares."""
    ids = [s["id"] for s in result["sources"]]
    answer = result["answer"]
    checks = {}
    if any(k in turn for k in ("hit", "hit_any", "hit_prefix")):
        ok = all(i in ids for i in turn.get("hit", [])) and (not turn.get("hit_any") or any(i in ids for i in turn["hit_any"])) \
            and (not turn.get("hit_prefix") or any(i.startswith(turn["hit_prefix"]) for i in ids))
        checks["retrieval"] = (ok, f"sources={ids}")
    if "contains" in turn or "not_contains" in turn:
        missing = [t for t in turn.get("contains", []) if t not in answer]
        present = [t for t in turn.get("not_contains", []) if t in answer]
        checks["answer"] = (not missing and not present, f"missing={missing} unexpected={present}")
    if "forbid" in turn:
        wrong = [i for i in turn["forbid"] if i in ids]
        checks["groundedness"] = (not wrong, f"wrong sources={wrong}")
    if turn.get("refuse"):
        checks["refusal"] = (not ids and result["mode"] in ("no_evidence", "needs_clarification"), f"mode={result['mode']} sources={ids}")
    if turn.get("clarify"):
        checks["refusal"] = (result["mode"] == "needs_clarification" and not ids, f"mode={result['mode']} sources={ids}")
    return checks


def run(spec):
    tally = {k: [0, 0] for k in ("retrieval", "answer", "groundedness", "refusal", "multi_turn")}
    records = []
    with tempfile.TemporaryDirectory() as tmp:
        store, settings = load_store(spec, tmp)
        for case in spec["cases"]:
            context = None
            for n, turn in enumerate(case["turns"], 1):
                result = question_answer(store, settings, turn["q"], context)
                context = result.get("turn_context")
                for measure, (ok, why) in check_turn(turn, result).items():
                    for key in (measure, "multi_turn" if case["group"] == MULTI_TURN else None):
                        if key:
                            tally[key][0] += ok
                            tally[key][1] += 1
                    records.append({"case": case["id"], "group": case["group"], "turn": n, "question": turn["q"],
                                    "measure": measure, "passed": bool(ok), "why": why, "mode": result["mode"],
                                    "known_limit": case.get("known_limit"),
                                    "answer": result["answer"][:300]})
    return {"measures": {k: {"passed": p, "total": t} for k, (p, t) in tally.items()}, "records": records}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=str(DEFAULT))
    parser.add_argument("--out")
    args = parser.parse_args(argv)
    spec = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    report = {"cases_file": args.cases, "label": spec.get("_label", ""), **run(spec)}
    for name, m in report["measures"].items():
        print(f"{name:13s} {m['passed']}/{m['total']}")
    failed = [r for r in report["records"] if not r["passed"]]
    for r in failed:
        tag = "KNOWN LIMIT" if r["known_limit"] else "FAIL"
        print(f"{tag} [{r['group']}] {r['case']}#{r['turn']} {r['measure']}: {r['question']} -> {r['why']}")
    failed = [r for r in failed if not r["known_limit"]]
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
