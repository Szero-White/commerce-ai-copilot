"""Offline quality harness: measures retrieval, answer, citation and unsupported-answer behaviour on synthetic sets.

    python -m scripts.quality_eval --set dev                      # development cases (free to inspect)
    python -m scripts.quality_eval --set near_miss                # development near-miss negatives
    python -m scripts.quality_eval --set legacy                   # the older benchmarks (tuned on: contaminated)
    python -m scripts.quality_eval --set holdout --final          # locked holdout, final session only
    python -m scripts.quality_eval --set dev --root PATH_TO_OTHER_CHECKOUT --label baseline --out reports/x.json

Always runs with LLM and embeddings OFF, on a throw-away database built from the seed documents (plus any
`--extra-docs` files for the fresh-data session), so it never calls a model and never touches runtime/.
`--root` evaluates the application code of another checkout (for example a worktree of the baseline commit) with the
SAME data sets and metrics, so before/after numbers come from one script. Offline numbers say nothing about a real LLM.
"""
import argparse
import hashlib
import json
import math
import re
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = HARNESS_ROOT / "data" / "eval_v4"
CITATION = re.compile(r"\[([A-Za-z0-9-]+)\]")


def _git(root, *args):
    try:
        out = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=20)
        return out.stdout.strip() if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def wilson(successes, n, z=1.96):
    """95% Wilson score interval; honest about how little a tiny set can say."""
    if n == 0:
        return [None, None]
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def rate(successes, n):
    return {"passed": successes, "total": n, "rate": round(successes / n, 3) if n else None, "ci95": wilson(successes, n)}


def _fold(text, normalize):
    return " ".join(normalize(text).split())


def judge(case, response, normalize):
    """Score one case from the service response. All expectations come from the data set, not from the code."""
    sources = response["sources"]
    found = [s["id"] for s in sources]
    answer = response["answer"]
    kind = case["type"]
    out = {"id": case["id"], "group": case["group"], "question": case["question"], "type": kind,
           "found": found, "mode": response["mode"]}
    if kind == "hit":
        expected, need = set(case["ids"]), case.get("min", 1)
        got = expected & set(found)
        excluded = set(case.get("exclude", ())) & set(found)
        out["retrieval_hit"] = len(got) >= need and not excluded
        out["abstained"] = not found
        out["wrong_source_only"] = bool(found) and not got
        out["excluded_returned"] = sorted(excluded)
        wanted = case.get("must_contain", [])
        if wanted:
            folded = _fold(answer, normalize)
            out["answer_ok"] = bool(out["retrieval_hit"]) and all(_fold(w, normalize) in folded for w in wanted)
        cited = set(CITATION.findall(answer))
        out["citation_ok"] = bool(found) and cited <= set(found) and len(cited & expected) >= need
        out["pass"] = bool(out["retrieval_hit"])
    elif kind == "none":
        leaked = sorted(set(found) - set(case.get("allow", ())))
        out["leaked"] = leaked
        out["pass"] = not leaked
    elif kind == "none_or_clarify":
        out["pass"] = not found or response["mode"] == "needs_clarification"
    else:
        raise ValueError(f"unknown case type {kind!r}")
    return out


def summarize(results, latencies):
    hits = [r for r in results if r["type"] == "hit"]
    nones = [r for r in results if r["type"] == "none"]
    clar = [r for r in results if r["type"] == "none_or_clarify"]
    with_text = [r for r in hits if "answer_ok" in r]
    summary = {
        "cases": len(results),
        "retrieval_hit_at_3": rate(sum(r["retrieval_hit"] for r in hits), len(hits)),
        "false_abstention": rate(sum(r["abstained"] for r in hits), len(hits)),
        "wrong_source_only": rate(sum(r["wrong_source_only"] for r in hits), len(hits)),
        "answer_correctness_must_contain": rate(sum(r["answer_ok"] for r in with_text), len(with_text)),
        "citation_correctness": rate(sum(r["citation_ok"] for r in hits if r["retrieval_hit"]),
                                     sum(1 for r in hits if r["retrieval_hit"])),
        "unsupported_answer_leaks": rate(sum(1 for r in nones if r["leaked"]), len(nones)),
        "clarify_or_abstain_ok": rate(sum(r["pass"] for r in clar), len(clar)),
        "latency_ms": {"p50": round(statistics.median(latencies), 2),
                       "p95": round(sorted(latencies)[max(0, math.ceil(0.95 * len(latencies)) - 1)], 2)}
        if latencies else None,
    }
    groups = {}
    for r in results:
        g = groups.setdefault(r["group"], [0, 0])
        g[0] += bool(r["pass"])
        g[1] += 1
    summary["by_group"] = {k: rate(v[0], v[1]) for k, v in sorted(groups.items())}
    return summary


def build_store(tmp, extra_docs):
    from app.storage import Store
    store = Store(Path(tmp) / "quality.db")
    for path in extra_docs:
        for doc in json.loads(Path(path).read_text(encoding="utf-8")):
            store.upsert(doc)
    return store


def run_cases(cases, store, settings):
    from app.services import question_answer
    from app.storage import normalize
    results, latencies = [], []
    for case in cases:
        start = time.perf_counter()
        response = question_answer(store, settings, case["question"])
        latencies.append((time.perf_counter() - start) * 1000)
        results.append(judge(case, response, normalize))
    return results, latencies


def run_legacy(store, settings):
    """The pre-v4 benchmarks, re-measured. They were used for tuning, so they are NOT unbiased."""
    from app.services import question_answer
    root = HARNESS_ROOT
    positives = json.loads((root / "data" / "eval_set.json").read_text(encoding="utf-8"))
    negatives = json.loads((root / "data" / "negative_eval_set.json").read_text(encoding="utf-8"))
    old = json.loads((root / "tests" / "fixtures" / "retrieval_heldout.json").read_text(encoding="utf-8"))

    def found(question):
        return [s["id"] for s in question_answer(store, settings, question)["sources"]]

    pos = sum(item["expected_source"] in found(item["question"]) for item in positives)
    neg = sum(not found(item["question"]) for item in negatives)
    old_pos = sum(bool(set(item["expected"]) & set(found(item["question"]))) for item in old["positive"])
    old_neg = sum(not found(q) for q in old["negative"])
    return {"dev_positives_hit_at_3": rate(pos, len(positives)),
            "dev_negatives_correctly_rejected": rate(neg, len(negatives)),
            "old_heldout_positives_hit_at_3": rate(old_pos, len(old["positive"])),
            "old_heldout_negatives_correctly_rejected": rate(old_neg, len(old["negative"])),
            "caveat": "These sets were used while tuning; the old held-out set was looked at before the last logic change."}


def load_set(name):
    path = {"dev": "dev.json", "near_miss": "near_miss.json", "holdout": "holdout.json", "fresh": "fresh/cases.json"}[name]
    full = EVAL_DIR / path
    return json.loads(full.read_text(encoding="utf-8"))["cases"], full


def check_holdout_lock():
    recorded = (EVAL_DIR / "HOLDOUT.sha256").read_text(encoding="utf-8").split()[0]
    actual = sha256_file(EVAL_DIR / "holdout.json")
    if recorded != actual:
        raise SystemExit(f"holdout.json does not match HOLDOUT.sha256 ({actual} != {recorded}); the holdout is no longer independent")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True, choices=["dev", "near_miss", "holdout", "fresh", "legacy"])
    ap.add_argument("--root", default=str(HARNESS_ROOT), help="checkout whose application code is evaluated")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", help="write the full JSON report here")
    ap.add_argument("--final", action="store_true", help="required for the locked holdout (final session only)")
    ap.add_argument("--extra-docs", nargs="*", default=[], help="JSON document files loaded into the temporary DB (fresh session)")
    args = ap.parse_args(argv)

    if args.set == "holdout":
        if not args.final:
            raise SystemExit("The holdout is locked: use --final in the final evaluation session only.")
        check_holdout_lock()

    root = Path(args.root).resolve()
    sys.path.insert(0, str(root))          # evaluate that checkout's `app` package
    from app.config import Settings
    settings_kwargs = {"llm_provider": "off", "embedding_provider": "off"}

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(data_path=Path(tmp) / "quality.db", **settings_kwargs)
        store = build_store(tmp, args.extra_docs)
        report = {"schema": 1, "label": args.label, "set": args.set,
                  "date_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                  "code_root": str(root), "code_commit": _git(root, "rev-parse", "HEAD"),
                  "code_dirty": bool(_git(root, "status", "--porcelain", "--untracked-files=no")),
                  "harness_commit": _git(HARNESS_ROOT, "rev-parse", "HEAD"),
                  "config": {"llm": "off", "embedding": "off", "k": 3},
                  "extra_docs": [Path(p).name for p in args.extra_docs]}
        if args.set == "legacy":
            report["results"] = run_legacy(store, settings)
        else:
            cases, path = load_set(args.set)
            report["dataset_sha256"] = sha256_file(path)
            results, latencies = run_cases(cases, store, settings)
            report["summary"] = summarize(results, latencies)
            if args.set != "holdout" or args.final:
                report["failures"] = [r for r in results if not r["pass"]]
            if args.set != "holdout":
                report["cases"] = results
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    summary = report.get("summary") or report["results"]
    print(json.dumps({k: v for k, v in summary.items() if k != "by_group"}, ensure_ascii=False, indent=2))
    if "by_group" in summary:
        print("by group:", {g: f"{v['passed']}/{v['total']}" for g, v in summary["by_group"].items()})


if __name__ == "__main__":
    main()
