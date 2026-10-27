"""B1: does a real embedding model help questions that share no words with the answer, and can the gate keep it safe?

    python -m scripts.embedding_experiment --dry-run      # texts and requests that WOULD be sent; no key, no network
    python -m scripts.embedding_experiment --cache-only   # analyse vectors already in the cache; refuses to call anything
    python -m scripts.embedding_experiment --run          # embeds the missing texts (Gemini, free tier) then analyses

`--run` is started through `run_gemini_live.ps1 -Task embedding-dev` by the owner of the API key (hidden key prompt, free-tier
confirmation, budgets). It embeds the 15 synthetic documents, their sentences and the DEV and near-miss questions only
(never the locked holdout), through the cached and rate-limited path of app/gemini.py, so a rerun costs nothing.

What is measured, all on DEV data: lexical retrieval alone versus lexical + `gate.admit_semantic` over a grid of thresholds
(zero leaks on negatives and near-misses is the calibration target; the most conservative stable point is chosen), an ablation
of each gate clause at the chosen point, and the pre-registered decision rule (see decide()). Scores and a matching sentence are
evidence of RELEVANCE only; this experiment does not claim any answer is true. The result may well be "do not enable".
"""
import argparse
import itertools
import json
import math
import os
import re
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

HARNESS_ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = HARNESS_ROOT / "data" / "eval_v4"
SPAN_MIN_CHARS = 20
EMBED_TEXT_BUDGET = 180          # refuse to start when more NEW texts than this would be sent
EMBED_BATCH = 8
REPORT = HARNESS_ROOT / "reports" / "b1_embedding_dev.json"
EXTERNAL_REPORT = HARNESS_ROOT / "reports" / "b1_embedding_external.json"
EXTERNAL_TEXT_BUDGET = 400      # an external set is larger than the dev set; still a hard refusal above this

GRID = {
    "tau": [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80],
    "tau_span": [0.40, 0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80],
    "z_min": [2.0, 3.0, 4.0],
    "delta": [0.03, 0.05, 0.08],
    "gap_min": [0.02, 0.04],
}
# Rule fixed BEFORE any real result existed (PLAN V3 section 8): enable hybrid only if all of these hold.
RULE_MIN_GAIN_POINTS = 15.0       # synonym/need group Hit@3 gain over lexical, absolute percentage points (dev)
RULE_MAX_REQUESTS = 25


def split_sentences(text):
    parts = re.split(r"(?<=[.!?;])\s+", text.strip())
    return [p.strip() for p in parts if len(p.strip()) >= SPAN_MIN_CHARS]


def doc_text(doc):
    return doc["title"] + "\n" + doc["content"]      # the same text retrieval.index_vectors embeds


def load_cases():
    cases = []
    for name in ("dev.json", "near_miss.json"):      # the locked holdout is never read here
        cases += json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))["cases"]
    return cases


def plan_texts(docs, cases):
    spans = {d["id"]: split_sentences(d["content"]) for d in docs}
    ordered = [doc_text(d) for d in docs] + [s for d in docs for s in spans[d["id"]]] + [c["question"] for c in cases]
    return {"spans": spans, "texts": list(dict.fromkeys(ordered))}


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na, nb = math.sqrt(sum(x * x for x in a)), math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def score_case(question, docs, spans, vectors):
    """Similarity of a question to every document, and to each document's best sentence."""
    q = vectors[question]
    doc_scores = {d["id"]: cosine(q, vectors[doc_text(d)]) for d in docs}
    span_best = {}
    for d in docs:
        best = max(((cosine(q, vectors[s]), s) for s in spans[d["id"]]), default=None)
        if best:
            span_best[d["id"]] = best
    return doc_scores, span_best


class CaseContext:
    """Everything one case needs, computed once: lexical result, hard-constraint verdicts, similarities."""

    def __init__(self, case, store, docs_by_id, vectors, spans):
        from app.gate import check_document
        from app.query import normalize
        self.case = case
        info = {}
        found = store.fts_search(case["question"], limit=15, trace=info)
        self.lexical = [d["id"] for d in found]
        # a document flagged "premise_mismatch" corrects a wrong number in the question: it supports nothing, so it is no leak
        self.premise = {d["id"] for d in found if d.get("condition_status") == "premise_mismatch"}
        self.analysis = store.analyze(case["question"])
        self.single = not (self.analysis.discovery or self.analysis.catalog or self.analysis.conditions)
        self.docs = list(docs_by_id.values())
        self.doc_scores, self.span_best = score_case(case["question"], self.docs, spans, vectors)
        self.hard = {}
        for d in self.docs:
            text = d["title"] + " " + d["content"]
            self.hard[d["id"]] = check_document(self.analysis, text, normalize(text).split(), d["category"]).admitted


def decide_case(ctx, params, clauses=("tau", "z", "span", "delta", "gap", "hard"), k=3):
    """Document ids returned for one case: the lexical ones, then those admitted by meaning. `clauses` allows ablation."""
    from app.gate import SemanticParams, admit_semantic
    p = SemanticParams(
        tau=params["tau"] if "tau" in clauses else -1.0, z_min=params["z_min"] if "z" in clauses else -1e9,
        gap_min=params["gap_min"] if "gap" in clauses else -1.0, delta=params["delta"] if "delta" in clauses else 1e9,
        tau_span=params["tau_span"] if "span" in clauses else -1.0)
    spans = ctx.span_best if "span" in clauses else {i: (1.0, "(no sentence required)") for i in ctx.doc_scores}
    passes = (lambda i: ctx.hard[i]) if "hard" in clauses else (lambda i: True)
    if ctx.analysis.needs_referent:
        return ctx.lexical[:k]
    extra = [i for i, _ in admit_semantic(ctx.doc_scores, spans, ctx.single, passes, p) if i not in ctx.lexical]
    return (ctx.lexical + extra)[:k]


def score_config(contexts, params, clauses=("tau", "z", "span", "delta", "gap", "hard")):
    """Metrics over all cases for one parameter set (params=None is lexical retrieval alone)."""
    leaks, hits, by_group, synonym = 0, 0, {}, [0, 0]
    positives = 0
    for ctx in contexts:
        case = ctx.case
        found = ctx.lexical[:3] if params is None else decide_case(ctx, params, clauses)
        if case["type"] == "hit":
            positives += 1
            ok = (len(set(case["ids"]) & set(found)) >= case.get("min", 1)
                  and not (set(case.get("exclude", ())) & set(found)))
            hits += ok
            g = by_group.setdefault(case["group"], [0, 0]); g[0] += ok; g[1] += 1
            if case["group"] == "synonym_need":
                synonym[0] += ok; synonym[1] += 1
        elif case["type"] == "none":
            leaks += bool(set(found) - set(case.get("allow", ())) - ctx.premise)
        else:  # none_or_clarify: any returned source is a leak (the lexical path abstains on these)
            leaks += bool(set(found) - ctx.premise)
    return {"leaks": leaks, "hits": hits, "positives": positives, "synonym_hits": synonym[0], "synonym_total": synonym[1],
            "by_group": {k: f"{v[0]}/{v[1]}" for k, v in sorted(by_group.items())}}


def all_configs():
    keys = list(GRID)
    for values in itertools.product(*(GRID[k] for k in keys)):
        yield dict(zip(keys, values))


def _neighbours(params):
    for key, values in GRID.items():
        i = values.index(params[key])
        for j in (i - 1, i + 1):
            if 0 <= j < len(values):
                yield {**params, key: values[j]}


def choose_conservative_point(contexts):
    """Zero-leak configurations whose grid neighbours are also zero-leak (a plateau, not a lucky point); among them the
    best synonym/need recall, then the most conservative thresholds. Returns (params or None, how many configs were scanned)."""
    cache = {}

    def leaks(p):
        key = tuple(p.values())
        if key not in cache:
            cache[key] = score_config(contexts, p)
        return cache[key]

    zero = [p for p in all_configs() if leaks(p)["leaks"] == 0]
    stable = [p for p in zero if all(leaks(n)["leaks"] == 0 for n in _neighbours(p))]
    scanned = len(cache)
    if not stable:
        return None, scanned, {"zero_leak_configs": len(zero), "stable_configs": 0}
    best = max(stable, key=lambda p: (leaks(p)["synonym_hits"], leaks(p)["hits"], p["tau"] + p["tau_span"] + p["z_min"]))
    return best, scanned, {"zero_leak_configs": len(zero), "stable_configs": len(stable)}


def ablation(contexts, params):
    full = score_config(contexts, params)
    rows = {}
    for clause in ("tau", "z", "span", "delta", "gap", "hard"):
        without = tuple(c for c in ("tau", "z", "span", "delta", "gap", "hard") if c != clause)
        m = score_config(contexts, params, without)
        rows[clause] = {"leaks_without": m["leaks"], "synonym_hits_without": m["synonym_hits"],
                        "has_measured_effect": m["leaks"] > full["leaks"]}
    return full, rows


def decide(lexical, chosen, chosen_metrics, ablated, requests_made):
    """The pre-registered rule. Every reason is reported; hybrid may be enabled only when all hold (still default OFF)."""
    reasons = []
    gain = None
    if chosen is None:
        reasons.append("(b) no zero-leak configuration with stable neighbours exists on the grid")
    else:
        total = chosen_metrics["synonym_total"] or 1
        gain = 100.0 * (chosen_metrics["synonym_hits"] - lexical["synonym_hits"]) / total
        if gain < RULE_MIN_GAIN_POINTS:
            reasons.append(f"(a) synonym/need Hit@3 gain {gain:.1f} points < {RULE_MIN_GAIN_POINTS}")
        if chosen_metrics["leaks"] != 0:
            reasons.append("(b) leaks on negatives/near-misses are not zero")
        idle = [c for c, r in ablated.items() if not r["has_measured_effect"]]
        if idle:
            reasons.append(f"(c) no measured effect on dev leaks when removing: {', '.join(idle)}")
    if requests_made is not None and requests_made > RULE_MAX_REQUESTS:
        reasons.append(f"(d) {requests_made} requests > {RULE_MAX_REQUESTS}")
    return {"enable_hybrid_allowed": not reasons, "synonym_gain_points": gain, "unmet": reasons,
            "note": "Even when allowed, hybrid stays OFF by default and its quality on the holdout is unproven."}


def analyse(store, cases, vectors, spans, requests_made=None):
    docs_by_id = {d["id"]: d for d in store.documents()}
    contexts = [CaseContext(c, store, docs_by_id, vectors, spans) for c in cases]
    lexical = score_config(contexts, None)
    chosen, scanned, plateau = choose_conservative_point(contexts)
    chosen_metrics, ablated = (None, {})
    if chosen:
        chosen_metrics, ablated = ablation(contexts, chosen)
    relevant = [max(c.doc_scores[i] for i in c.case["ids"] if i in c.doc_scores) for c in contexts if c.case["type"] == "hit"]
    irrelevant = [max(c.doc_scores.values()) for c in contexts if c.case["type"] == "none"]
    return {"lexical_only": lexical, "chosen_params": chosen, "configs_scanned": scanned, **plateau,
            "chosen_metrics": chosen_metrics, "ablation": ablated,
            "decision": decide(lexical, chosen, chosen_metrics, ablated, requests_made),
            "score_summary": {
                "best_score_of_the_expected_document (hit cases): min/median/max": _mmm(relevant),
                "best_score_of_any_document (negative cases): min/median/max": _mmm(irrelevant)},
            "cases_with_chosen_params": None if not chosen else [
                {"id": c.case["id"], "group": c.case["group"], "question": c.case["question"], "lexical": c.lexical[:3],
                 "final": decide_case(c, chosen)} for c in contexts]}


RULE_MAX_REQUESTS_EXTERNAL = 45
RULE_MAX_NEW_LEAKS = 0


def case_ok(ctx, found):
    """(kind, ok): a hit case is ok when its expected documents are returned; an unanswerable one when nothing unsupported is."""
    case = ctx.case
    if case["type"] == "hit":
        return "hit", (len(set(case["ids"]) & set(found)) >= case.get("min", 1)
                       and not (set(case.get("exclude", ())) & set(found)))
    allowed = set(case.get("allow", ())) | ctx.premise
    return "none", not (set(found) - allowed)


def ranking_before_the_gate(contexts):
    """How well the embedding alone ranks the expected documents (all documents, no gate, no thresholds)."""
    rows, by_group = [], {}
    for ctx in contexts:
        if ctx.case["type"] != "hit":
            continue
        order = sorted(ctx.doc_scores, key=ctx.doc_scores.get, reverse=True)
        rank = min((order.index(i) + 1 for i in ctx.case["ids"] if i in order), default=None)
        rows.append(rank)
        g = by_group.setdefault(ctx.case["group"], [])
        g.append(rank)

    def share(ranks, k):
        return f"{sum(1 for r in ranks if r and r <= k)}/{len(ranks)}"
    return {"questions": len(rows), "top1": share(rows, 1), "top3": share(rows, 3), "top5": share(rows, 5),
            "mrr": round(sum(1 / r for r in rows if r) / len(rows), 3) if rows else None,
            "by_group_top3": {k: share(v, 3) for k, v in sorted(by_group.items())}}


def analyse_external(store, cases, vectors, spans, params, requests_made=None):
    """Independent set: thresholds are FIXED beforehand (calibrated on the dev set), never chosen on these data."""
    docs_by_id = {d["id"]: d for d in store.documents()}
    contexts = [CaseContext(c, store, docs_by_id, vectors, spans) for c in cases]
    lexical = score_config(contexts, None)
    semantic = score_config(contexts, params)
    moved = {"gained": [], "lost": [], "new_unsupported_sources": []}
    for ctx in contexts:
        l_kind, l_ok = case_ok(ctx, ctx.lexical[:3])
        final = decide_case(ctx, params)
        s_kind, s_ok = case_ok(ctx, final)
        item = {"id": ctx.case["id"], "group": ctx.case["group"], "question": ctx.case["question"],
                "lexical": ctx.lexical[:3], "with_semantic": final}
        if s_ok and not l_ok:
            moved["gained"].append(item)
        elif l_ok and not s_ok:
            moved["lost" if s_kind == "hit" else "new_unsupported_sources"].append(item)
    hit_best = [max(ctx.doc_scores[i] for i in ctx.case["ids"] if i in ctx.doc_scores) for ctx in contexts if ctx.case["type"] == "hit"]
    none_best = [max((s for i, s in ctx.doc_scores.items() if ctx.hard[i]), default=0.0) for ctx in contexts if ctx.case["type"] != "hit"]
    reasons = []
    gain = None
    if semantic["synonym_total"]:
        gain = 100.0 * (semantic["synonym_hits"] - lexical["synonym_hits"]) / semantic["synonym_total"]
    overall_gain = 100.0 * (semantic["hits"] - lexical["hits"]) / (lexical["positives"] or 1)
    if overall_gain < RULE_MIN_GAIN_POINTS:
        reasons.append(f"(a) Hit@3 gain over the lexical result {overall_gain:.1f} points < {RULE_MIN_GAIN_POINTS}")
    if len(moved["new_unsupported_sources"]) > RULE_MAX_NEW_LEAKS or semantic["leaks"] > lexical["leaks"]:
        reasons.append("(b) the semantic channel added sources to questions that the documents cannot answer")
    if moved["lost"]:
        reasons.append("(b2) the semantic channel displaced an expected document")
    if requests_made is not None and requests_made > RULE_MAX_REQUESTS_EXTERNAL:
        reasons.append(f"(d) {requests_made} requests > {RULE_MAX_REQUESTS_EXTERNAL}")
    return {"mode": "external set, FIXED thresholds (no selection on these data)", "params": params,
            "ranking_before_the_gate": ranking_before_the_gate(contexts),
            "after_the_gate": {"lexical_only": lexical, "lexical_plus_semantic": semantic},
            "moved": {k: v for k, v in moved.items()},
            "separation": {"best_score_of_the_expected_document (hit cases): min/median/max": _mmm(hit_best),
                           "best_score_among_documents_the_hard_gate_lets_through (unanswerable): min/median/max": _mmm(none_best)},
            "decision": {"enable_hybrid_allowed": not reasons, "hit_gain_points": round(overall_gain, 1),
                         "synonym_need_gain_points": gain, "unmet": reasons,
                         "note": "A pass here would still be one set and one author: it would justify a sealed confirmation run, not use."}}


def _mmm(values):
    values = sorted(values)
    return [round(values[0], 3), round(values[len(values) // 2], 3), round(values[-1], 3)] if values else None


class CacheOnly(Exception):
    pass


def embed_function(settings, mode):
    """Vectors for texts. cache-only mode never sends anything."""
    from app import gemini
    from app.embedding_cache import EmbeddingCache

    def cached_only(texts):
        known = EmbeddingCache(gemini.CACHE_PATH).get_many(settings.embedding_model, texts)
        missing = [t for t in dict.fromkeys(texts) if t not in known]
        if missing:
            raise CacheOnly(f"{len(missing)} of {len(set(texts))} texts are not in the embedding cache; run with --run to embed them")
        return [known[t] for t in texts]

    return cached_only if mode == "cache-only" else (lambda texts: gemini.embed(settings, texts))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true")
    group.add_argument("--cache-only", action="store_true")
    group.add_argument("--run", action="store_true")
    ap.add_argument("--out", default=None)
    ap.add_argument("--docs", nargs="+", help="EXTERNAL set: document files (csv / md / txt / json, see scripts/blind_eval.py)")
    ap.add_argument("--questions", help="EXTERNAL set: question file written by the evaluator (json / csv)")
    ap.add_argument("--category", default="knowledge", help="category of .md/.txt document files")
    ap.add_argument("--params-from", default=str(REPORT),
                    help="report whose chosen_params are used UNCHANGED on the external set (default: the dev experiment)")
    ap.add_argument("--max-texts", type=int, default=None, help="refuse to send more NEW texts than this")
    args = ap.parse_args(argv)
    external = bool(args.docs)
    if external != bool(args.questions):
        print("--docs and --questions go together. Nothing was sent.")
        return 2
    out_path = args.out or str(EXTERNAL_REPORT if external else REPORT)
    budget = args.max_texts or (EXTERNAL_TEXT_BUDGET if external else EMBED_TEXT_BUDGET)
    params = None
    if external:
        try:
            params = json.loads(Path(args.params_from).read_text(encoding="utf-8"))["chosen_params"]
            assert params
        except (OSError, KeyError, ValueError, AssertionError):
            print(f"No fixed thresholds in {args.params_from}: run the dev experiment first. Nothing was sent.")
            return 2

    from app.config import Settings
    from app.storage import Store
    base = Settings()
    with tempfile.TemporaryDirectory() as tmp:
        settings = replace(base, data_path=Path(tmp) / "b1.db", llm_provider="off",
                           embedding_provider="gemini", embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", "gemini-embedding-001"))
        store = Store(settings.data_path)
        if external:
            from scripts import blind_eval as be
            try:
                docs, _ = be.load_documents(args.docs, args.category)
                cases = be.resolve_refs(be.validate_cases(be.load_questions(args.questions)), docs)
            except (be.InputError, OSError, ValueError) as exc:
                print(f"Input refused: {exc}. Nothing was sent.")
                return 2
            store.delete_source("seed")           # only the evaluator's documents
            for source in sorted({d["source"] for d in docs}):
                store.apply([{k: v for k, v in d.items() if k != "source"} for d in docs if d["source"] == source], source=source)
        else:
            cases = load_cases()
        planned = plan_texts(store.documents(), cases)
        texts = planned["texts"]
        from app import gemini
        from app.embedding_cache import EmbeddingCache
        known = EmbeddingCache(gemini.CACHE_PATH).get_many(settings.embedding_model, texts)
        new = [t for t in texts if t not in known]
        requests = math.ceil(len(new) / EMBED_BATCH)
        print(f"texts: {len(texts)} (documents {len(store.documents())}, sentences "
              f"{sum(len(v) for v in planned['spans'].values())}, questions {len(cases)}); already cached: {len(known)}; "
              f"new: {len(new)} -> about {requests} embedding requests, {math.ceil(len(new) * 60 / gemini.EMBED_TEXTS_PER_MINUTE)} s at "
              f"{gemini.EMBED_TEXTS_PER_MINUTE} texts/min. Holdout questions are not included.")
        if args.dry_run:
            print("Dry run: nothing was sent.")
            return 0
        if len(new) > budget:
            print(f"Refusing: {len(new)} new texts exceed the budget of {budget}. Nothing was sent.")
            return 2
        if args.run:
            if os.environ.get("GEMINI_CONFIRM_FREE_TIER", "").lower() != "yes" or not os.environ.get("GEMINI_API_KEY"):
                print("Set GEMINI_API_KEY and GEMINI_CONFIRM_FREE_TIER=yes (run_gemini_live.ps1 does this). Nothing was sent.")
                return 2
            gemini.reset_budget()
        try:
            vectors_list = embed_function(settings, "cache-only" if args.cache_only else "run")(texts)
        except CacheOnly as exc:
            print(exc)
            return 3
        except Exception as exc:   # ModelUnavailable: quota, budget, network; the cache keeps whatever was embedded
            print(f"Stopped: {exc}. Texts embedded so far are cached; rerun to continue. Nothing was retried elsewhere.")
            return 1
        vectors = dict(zip(texts, vectors_list))
        made = gemini.requests_made() if args.run else 0
        if external:
            report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(),
                      "experiment": "embedding on an EXTERNAL set, thresholds fixed from the dev experiment",
                      "embedding_model": settings.embedding_model, "documents": len(store.documents()), "questions": len(cases),
                      "document_files": [Path(p).name for p in args.docs], "questions_file": Path(args.questions).name,
                      "texts": len(texts), "new_texts": len(new), "requests_made": made,
                      "caveat": "Similarity and matching sentences show relevance, not truth. One external set by one author: "
                                "a pass would justify a sealed confirmation run, not use. The set is no longer blind once its failures drive a fix.",
                      **analyse_external(store, cases, vectors, planned["spans"], params, made if args.run else None)}
        else:
            report = {"observed_at_utc": datetime.now(timezone.utc).isoformat(), "experiment": "B1 embedding on DEV data",
                      "embedding_model": settings.embedding_model, "data": "synthetic only; dev + near-miss questions; no holdout",
                      "texts": len(texts), "new_texts": len(new), "requests_made": made,
                      "caveat": "Similarity and matching sentences show relevance, not truth. Dev is small (65 cases) and was "
                                "written by the same person as the holdout. A positive result still needs the locked holdout.",
                      **analyse(store, cases, vectors, planned["spans"], made if args.run else None)}
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    d = report["decision"]
    if external:
        r, a = report["ranking_before_the_gate"], report["after_the_gate"]
        print(f"before the gate (embedding alone): top1 {r['top1']}, top3 {r['top3']}, top5 {r['top5']}, MRR {r['mrr']}")
        for name, m in (("lexical only", a["lexical_only"]), ("lexical + semantic", a["lexical_plus_semantic"])):
            print(f"after the gate, {name}: {m['hits']}/{m['positives']} hits, {m['leaks']} unanswerable questions given a source")
        print(f"semantic gained {len(report['moved']['gained'])}, displaced {len(report['moved']['lost'])}, "
              f"added sources to {len(report['moved']['new_unsupported_sources'])} unanswerable question(s)")
        print("hybrid allowed by the rule:", d["enable_hybrid_allowed"], "| unmet:", d["unmet"] or "none")
        print(f"report: {out}")
        return 0
    print(f"lexical only: {report['lexical_only']['hits']}/{report['lexical_only']['positives']} hits, "
          f"{report['lexical_only']['leaks']} leaks, synonym {report['lexical_only']['synonym_hits']}/{report['lexical_only']['synonym_total']}")
    if report["chosen_params"]:
        m = report["chosen_metrics"]
        print(f"chosen {report['chosen_params']}: {m['hits']}/{m['positives']} hits, {m['leaks']} leaks, synonym {m['synonym_hits']}/{m['synonym_total']}")
    print("hybrid allowed by the rule:", d["enable_hybrid_allowed"], "| unmet:", d["unmet"] or "none")
    print(f"report: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
