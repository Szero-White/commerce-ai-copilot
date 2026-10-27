"""Blind evaluation: score the system on documents and questions written by SOMEONE ELSE.

    python -m scripts.blind_eval --docs products.csv policies.md --questions questions.json [--out-dir reports/blind_eval]

This tool never writes a question or an expected answer. Everything it scores comes from the files you pass in:
* `--docs`: one or more .csv / .md / .txt files (same rules as scripts.ingest: CSV sku,name,description[,price,category];
  --category applies to .md/.txt) or .json files holding a list of {"id","title","category","content"}.
* `--questions`: a .json file ({"cases":[...]} or a list) or a .csv file, each case written by the evaluator with its expectation.

Case fields: id, question, type = hit | none | none_or_clarify. For `hit`: ids (expected documents; "@SKU" means the document
imported from the CSV row with that sku, "@policy:<file stem>:<n>" the n-th chunk of an .md/.txt file), optional min (how many
of them must be returned), exclude (must NOT be returned), must_contain / must_not_contain (text of the answer), group, tag.
For `none`: the question cannot be answered from the documents; optional allow (documents that may be returned).
CSV questions use the same column names; list columns separate items with "|".

Everything runs on a throw-away database (nothing in runtime/ is read or written), with LLM and embeddings OFF and no network.
Results per question: source found, answer check, correct refusal, and hallucination flags. Offline answers are quoted
document text, so "answer correct" only checks the facts you listed; it is not a judgement of language quality.
"""
import argparse
import csv
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
TYPES = {"hit", "none", "none_or_clarify"}
LIST_FIELDS = ("ids", "exclude", "allow", "must_contain", "must_not_contain")
KNOWN = {"id", "question", "type", "group", "tag", "min", *LIST_FIELDS}


class InputError(ValueError):
    """The evaluator's files are not usable; nothing was evaluated."""


def load_documents(paths, category="knowledge"):
    from scripts.ingest import parse_file
    docs, sources = [], {}
    for path in map(Path, paths):
        if path.suffix.lower() == ".json":
            items = json.loads(path.read_text(encoding="utf-8-sig"))
            items = items.get("documents", items) if isinstance(items, dict) else items
            for i, d in enumerate(items):
                missing = {"id", "title", "category", "content"} - set(d)
                if missing:
                    raise InputError(f"{path.name} item {i}: missing {sorted(missing)}")
                docs.append({**{k: str(d[k]) for k in ("id", "title", "category", "content")}, "source": path.stem})
            sources[path.stem] = path.name
        else:
            parsed, source = parse_file(path, category=category)
            docs += [{**d, "source": source} for d in parsed]
            sources[source] = path.name
    ids = [d["id"] for d in docs]
    if len(ids) != len(set(ids)):
        raise InputError("duplicate document ids across the document files")
    if not docs:
        raise InputError("no documents given")
    return docs, sources


def _split(value):
    return [x.strip() for x in str(value).split("|") if x.strip()]


def load_questions(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as f:
            raw = list(csv.DictReader(f))
        cases = []
        for row in raw:
            case = {k: v.strip() for k, v in row.items() if k and v and v.strip()}
            for k in LIST_FIELDS:
                if k in case:
                    case[k] = _split(case[k])
            if "min" in case:
                case["min"] = int(case["min"])
            cases.append(case)
    else:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        cases = data.get("cases", data) if isinstance(data, dict) else data
    return cases


def validate_cases(cases):
    problems, seen = [], set()
    for n, c in enumerate(cases, 1):
        label = c.get("id") or f"#{n}"
        if not c.get("id"):
            problems.append(f"case {label}: missing id")
        elif c["id"] in seen:
            problems.append(f"case {label}: duplicate id")
        seen.add(c.get("id"))
        if len(str(c.get("question", ""))) < 3:
            problems.append(f"case {label}: question missing or shorter than 3 characters")
        if c.get("type") not in TYPES:
            problems.append(f"case {label}: type must be one of {sorted(TYPES)}")
        if c.get("type") == "hit" and not c.get("ids"):
            problems.append(f"case {label}: a 'hit' case needs ids (the expected documents)")
        if c.get("type") == "hit" and not isinstance(c.get("ids"), list):
            problems.append(f"case {label}: ids must be a list")
    if not cases:
        problems.append("no questions given")
    if problems:
        raise InputError("; ".join(problems))
    return [{**c, "group": c.get("group") or "ungrouped"} for c in cases]


def resolve_refs(cases, docs):
    """'@SKU' and '@policy:<stem>:<n>' to document ids; plain ids must exist. Fails before anything is scored."""
    by_title = {d["title"]: d["id"] for d in docs}
    ids = {d["id"] for d in docs}
    unresolved = []

    def one(ref, case_id):
        if ref in ids:
            return ref
        if ref.startswith("@policy:"):
            try:
                _, source, n = ref.split(":")
                return by_title[f"{source} / phần {n}"]
            except (ValueError, KeyError):
                pass
        elif ref.startswith("@"):
            hit = [i for t, i in by_title.items() if t.endswith(f" - {ref[1:]}")]
            if len(hit) == 1:
                return hit[0]
        unresolved.append(f"{case_id}: {ref}")
        return ref

    out = [{**c, **{k: [one(x, c["id"]) for x in c[k]] for k in ("ids", "exclude", "allow") if k in c}} for c in cases]
    if unresolved:
        raise InputError("expected documents that were not found in --docs: " + "; ".join(unresolved))
    return out


def evaluate(docs, cases, with_seed=False, online=False, only=None):
    """Score every case on a temporary database; returns (per-case records, summary).

    `online` (owner-run, free tier): embeddings AND the LLM come from the environment (run_gemini_live.ps1 -Task online-check);
    the documents are indexed (cache hits when the embedding experiment ran on the same files) and only the cases in `only`
    are asked, one every few seconds. Offline (default) both are off and nothing touches the network.
    """
    sys.path.insert(0, str(HARNESS_ROOT))
    from app.config import Settings
    from app.evidence import answer_problems
    from app.services import question_answer
    from app.storage import Store, normalize
    from scripts import quality_eval as qe

    records, latencies = [], []
    with tempfile.TemporaryDirectory() as tmp:
        if online:
            import os
            from app import gemini, retrieval
            base = Settings()
            if base.llm_provider != "gemini" or base.embedding_provider != "gemini" or not os.environ.get("GEMINI_API_KEY") \
                    or os.environ.get("GEMINI_CONFIRM_FREE_TIER", "").lower() != "yes":
                raise InputError("online mode needs LLM_PROVIDER=gemini, EMBEDDING_PROVIDER=gemini, GEMINI_API_KEY and "
                                 "GEMINI_CONFIRM_FREE_TIER=yes (use run_gemini_live.ps1 -Task online-check)")
            gemini.reset_budget()
            settings = Settings(data_path=Path(tmp) / "blind.db")
        else:
            settings = Settings(data_path=Path(tmp) / "blind.db", llm_provider="off", embedding_provider="off")
        store = Store(settings.data_path)
        if not with_seed:
            store.delete_source("seed")
        for source in sorted({d["source"] for d in docs}):
            store.apply([{k: v for k, v in d.items() if k != "source"} for d in docs if d["source"] == source], source=source)
        cases = resolve_refs(cases, store.documents() if with_seed else docs)
        if only:
            wanted, known = set(only), {c["id"] for c in cases}
            if wanted - known:
                raise InputError("--only names unknown cases: " + ", ".join(sorted(wanted - known)))
            cases = [c for c in cases if c["id"] in wanted]
        import time
        if online:
            indexed = retrieval.index_vectors(store, settings)
            if not indexed.get("enabled"):
                raise InputError(f"indexing stopped: {indexed.get('reason')}")
        for case in cases:
            if online:
                time.sleep(6.5)      # free-tier generation limit: stay well below the per-minute quota
            started = time.perf_counter()
            response = question_answer(store, settings, case["question"])
            latencies.append((time.perf_counter() - started) * 1000)
            base = qe.judge(case, response, normalize)
            # A hallucination is an ASSERTION the documents do not support. Returning a source is not one: offline the answer is
            # quoted document text, so it only asserts what the document says. Three outcomes are told apart:
            #   refused                 no source returned (safe refusal)
            #   sourced_no_assertion    a source returned for a question marked unanswerable, and nothing forbidden is said
            #   hallucination           forbidden text, an excluded document, or an answer failing the evidence check
            flags = []
            if base.get("excluded_returned"):
                flags.append("excluded document returned: " + ", ".join(base["excluded_returned"]))
            folded = " ".join(normalize(response["answer"]).split())
            forbidden = [t for t in case.get("must_not_contain", []) if " ".join(normalize(t).split()) in folded]
            if forbidden:
                flags.append("forbidden text in the answer: " + ", ".join(forbidden))
            if response["sources"]:
                # Leading list numbers ("1. [ID] ...") are layout, not claims.
                body = "\n".join(re.sub(r"^\s*\d+\.\s+", "", line) for line in response["answer"].splitlines())
                problems = answer_problems(body, response["sources"])
                if problems:
                    flags.append("answer fails the evidence check: " + "; ".join(problems))
            if base["type"] in ("none", "none_or_clarify"):
                outcome = "refused" if base["pass"] else ("hallucination" if flags else "sourced_no_assertion")
            else:
                outcome = "hallucination" if flags else ("answered" if base["pass"] else "abstained" if base["abstained"] else "wrong_source")
            record = {"id": case["id"], "group": case["group"], "question": case["question"], "type": case["type"],
                      "mode": response["mode"], "returned": base["found"], "answer": response["answer"], "flags": flags,
                      "found_by_meaning": [s["id"] for s in response["sources"] if s.get("evidence_basis") == "semantic"],
                      "retrieval_mode": response["retrieval_mode"], "verification": response.get("verification"),
                      "outcome": outcome, "needs_human_review": case.get("tag") == "llm_rubric"}
            if case["type"] == "hit":
                record["source_found"] = base["retrieval_hit"]
                record["abstained"] = base["abstained"]
                if "answer_ok" in base:
                    record["answer_correct"] = base["answer_ok"] and not forbidden
                elif case.get("must_not_contain"):
                    record["answer_correct"] = base["retrieval_hit"] and not forbidden
            else:
                record["refused_correctly"] = base["pass"]                 # strict: no source at all
                record["no_false_claim"] = outcome in ("refused", "sourced_no_assertion")
            # An unanswerable question passes when nothing unsupported is asserted (a refusal OR a source that asserts nothing).
            ok = base["pass"] if base["type"] == "hit" else record["no_false_claim"]
            record["pass"] = bool(ok) and not flags and record.get("answer_correct", True)
            records.append(record)
    return records, summarize(records, latencies, qe)


def summarize(records, latencies, qe):
    hits = [r for r in records if r["type"] == "hit"]
    refusals = [r for r in records if r["type"] != "hit"]
    with_answer = [r for r in hits if "answer_correct" in r]
    groups = {}
    for r in records:
        g = groups.setdefault(r["group"], [0, 0])
        g[0] += r["pass"]
        g[1] += 1
    return {
        "cases": len(records),
        "source_found": qe.rate(sum(r["source_found"] for r in hits), len(hits)),
        "false_abstention": qe.rate(sum(r["abstained"] for r in hits), len(hits)),
        "answer_correct (only where must_contain / must_not_contain was given)": qe.rate(sum(r["answer_correct"] for r in with_answer), len(with_answer)),
        "refused_correctly (strict: no source returned)": qe.rate(sum(r["refused_correctly"] for r in refusals), len(refusals)),
        "no_false_claim (refused, or a source that asserts nothing unsupported)": qe.rate(sum(r["no_false_claim"] for r in refusals), len(refusals)),
        "sourced_no_assertion": sum(r["outcome"] == "sourced_no_assertion" for r in records),
        "cases_with_hallucination_flags": qe.rate(sum(bool(r["flags"]) for r in records), len(records)),
        "all_checks_passed": qe.rate(sum(r["pass"] for r in records), len(records)),
        "needs_human_review": sum(r["needs_human_review"] for r in records),
        "latency_ms": {"p50": round(sorted(latencies)[len(latencies) // 2], 2),
                       "max": round(max(latencies), 2)} if latencies else None,
        "by_group": {k: qe.rate(v[0], v[1]) for k, v in sorted(groups.items())},
        "note": "Offline run: LLM and embeddings off. Answer text is quoted document text; the judgement of an LLM answer needs a human rubric.",
    }


def write_outputs(out_dir, records, summary, meta):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n", encoding="utf-8")
    columns = ["id", "group", "type", "question", "outcome", "source_found", "answer_correct", "refused_correctly", "no_false_claim",
               "abstained", "mode", "returned", "flags", "pass"]
    with (out / "results.csv").open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for r in records:
            writer.writerow({**{c: r.get(c, "") for c in columns}, "returned": "|".join(r["returned"]), "flags": " || ".join(r["flags"])})
    (out / "summary.json").write_text(json.dumps({**meta, "summary": summary}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--docs", nargs="+", required=True)
    ap.add_argument("--questions", required=True)
    ap.add_argument("--category", default="knowledge", help="category for .md/.txt document files (e.g. policy)")
    ap.add_argument("--with-seed", action="store_true", help="also keep the built-in synthetic seed documents in the temporary database")
    ap.add_argument("--out-dir", default=str(HARNESS_ROOT / "reports" / "blind_eval"))
    ap.add_argument("--validate-only", action="store_true", help="check the files and stop")
    ap.add_argument("--online", action="store_true",
                    help="owner-run: use Gemini embeddings + LLM from the environment (see run_gemini_live.ps1 -Task online-check)")
    ap.add_argument("--only", nargs="+", help="ask only these case ids (online mode keeps the number of requests small)")
    args = ap.parse_args(argv)
    try:
        docs, sources = load_documents(args.docs, args.category)
        cases = validate_cases(load_questions(args.questions))
        if args.validate_only:
            print(f"OK: {len(docs)} documents, {len(cases)} questions; nothing was evaluated.")
            return 0
        records, summary = evaluate(docs, cases, args.with_seed, args.online, args.only)
    except (InputError, OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Input refused, nothing was evaluated: {exc}")
        return 2
    meta = {"observed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "documents": len(docs),
            "document_files": sources, "questions_file": Path(args.questions).name, "with_seed": args.with_seed,
            "config": ({"llm": "gemini (hosted, free tier)", "embedding": "gemini (hosted)", "network": "Google AI API", "k": 3,
                        "only": args.only} if args.online else {"llm": "off", "embedding": "off", "network": "none", "k": 3})}
    write_outputs(args.out_dir, records, summary, meta)
    for key, v in summary.items():
        if isinstance(v, dict) and "passed" in v and key != "by_group":
            print(f"{key}: {v['passed']}/{v['total']}")
    print(f"sourced_no_assertion: {summary['sourced_no_assertion']}")
    for r in records:
        if not r["pass"]:
            print(f"  FAIL {r['id']} [{r['group']}] {r['question']} -> returned {r['returned'] or r['mode']}" + (f" | {r['flags'][0]}" if r["flags"] else ""))
    print(f"results: {args.out_dir}\\results.csv, results.jsonl, summary.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
