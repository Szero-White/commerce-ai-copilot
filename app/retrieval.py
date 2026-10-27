"""Hybrid BM25 + cosine similarity (RRF). No pretend vectors: semantic mode must be enabled."""
import json
import math
from .llm import embed, embedding_enabled, llm_enabled, ModelUnavailable


def cosine(a, b):
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x*x for x in a))
    nb = math.sqrt(sum(y*y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def index_vectors(store, settings):
    if not embedding_enabled(settings):
        return {"enabled": False, "indexed": 0, "reason": "EMBEDDING_PROVIDER=off"}
    docs = [d for d in store.documents() if not d["embedding_json"] or d.get("embedding_model") != settings.embedding_model]
    spans = [s for s in store.spans() if not s["embedding_json"] or s.get("embedding_model") != settings.embedding_model]
    if not docs and not spans:
        return {"enabled": True, "indexed": 0, "spans_indexed": 0}
    count = span_count = 0
    try:
        for i in range(0, len(docs), 8):
            batch = docs[i:i+8]
            vectors = embed(settings, [d["title"] + "\n" + d["content"] for d in batch])
            for d, vec in zip(batch, vectors):
                store.update_embedding(d["id"], vec, settings.embedding_model)
                count += 1
        for i in range(0, len(spans), 8):       # sentences: the evidence a meaning-based match must point at
            batch = spans[i:i+8]
            vectors = embed(settings, [s["text"] for s in batch])
            for s, vec in zip(batch, vectors):
                store.update_span_embedding(s["doc_id"], s["idx"], vec, settings.embedding_model)
                span_count += 1
        return {"enabled": True, "indexed": count, "spans_indexed": span_count}
    except ModelUnavailable as exc:
        return {"enabled": False, "indexed": count, "spans_indexed": span_count, "reason": str(exc)}


def _valid_vector(row, settings, size):
    if not row.get("embedding_json") or row.get("embedding_model") != settings.embedding_model:
        return None
    try:
        vector = json.loads(row["embedding_json"])
        return vector if isinstance(vector, list) and len(vector) == size else None
    except (TypeError, ValueError):
        return None   # Corrupt/stale vectors must never crash a request.


def semantic_candidates(store, settings, query, query_vector, admitted):
    """Documents a meaning-based match NOMINATES, each with its best matching sentence (a hint, may be empty).

    Only used when an LLM will check the answer (see `search`): similarity says a document is RELEVANT, not that it states
    what was asked. Nomination is by rank among all documents (`gate.rank_candidates`, no absolute threshold) and every hard
    constraint of `gate.check_document` still applies; `verification.py` decides whether anything may be claimed.
    """
    from .gate import check_document, rank_candidates
    from .query import normalize
    analysis = store.analyze(query)
    if analysis.needs_referent:
        return []
    docs = {d["id"]: d for d in store.documents()}
    size = len(query_vector)
    scores, best_span = {}, {}
    for d in docs.values():
        vector = _valid_vector(d, settings, size)
        if vector:
            scores[d["id"]] = cosine(query_vector, vector)
    for s in store.spans():
        vector = _valid_vector(s, settings, size)
        if vector:
            score = cosine(query_vector, vector)
            if s["doc_id"] not in best_span or score > best_span[s["doc_id"]][0]:
                best_span[s["doc_id"]] = (score, s["text"])
    verdicts = {}

    def passes(doc_id):
        d = docs[doc_id]
        text = d["title"] + " " + d["content"]
        verdicts[doc_id] = check_document(analysis, text, normalize(text).split(), d["category"])
        return verdicts[doc_id].admitted

    found = []
    for doc_id in rank_candidates(scores, passes):
        if doc_id not in admitted:
            cond = verdicts[doc_id].condition
            found.append(({**docs[doc_id], **({"condition_status": cond} if cond else {})}, best_span.get(doc_id, (0, ""))[1]))
    return found


def search(store, settings, query, k=3, trace=None, only=None):
    """Documents that passed the evidence gate, ranked. Semantic scores only re-rank them.

    Admission is decided by the gate (`Store.fts_search` -> `gate.check_document`), never by a similarity score alone.
    With embeddings AND an LLM both enabled, `semantic_candidates` may add documents found by meaning (document and
    sentence similarity above fixed thresholds, plus every hard constraint); they are marked `evidence_basis: semantic`
    and the LLM must verify the asked fact before the answer is given.
    """
    lexical = store.fts_search(query, limit=15, trace=trace, only=only)
    ranking = {}
    admitted = {d["id"]: d for d in lexical}
    documents = admitted
    for rank, d in enumerate(lexical, 1):
        ranking[d["id"]] = ranking.get(d["id"], 0.0) + 1/(40+rank)
    semantic_active = False
    if embedding_enabled(settings):
        try:
            query_vector = embed(settings, [query])[0]
            semantic = []
            for d in admitted.values():
                if d.get("embedding_json") and d.get("embedding_model") == settings.embedding_model:
                    try:
                        vector = json.loads(d["embedding_json"])
                        if not isinstance(vector, list) or len(vector) != len(query_vector):
                            continue
                        score = cosine(query_vector, vector)
                    except (TypeError, ValueError, OverflowError):
                        continue  # Corrupt/stale vectors must never crash a request.
                    if math.isfinite(score) and score >= 0.38:
                        semantic.append((score, d["id"]))
            semantic.sort(reverse=True)
            semantic_active = bool(semantic)   # vectors of admitted documents took part in the ranking
            for rank, (_, did) in enumerate(semantic[:15], 1):
                ranking[did] = ranking.get(did, 0.0) + 1/(40+rank)
            if only is None and llm_enabled(settings):
                # Meaning-only candidates are added ONLY when an LLM will check that the documents state what was asked
                # (services.question_answer); with the LLM off nothing could verify them, so the channel stays closed.
                for rank, (doc, sentence) in enumerate(semantic_candidates(store, settings, query, query_vector, admitted), 1):
                    admitted[doc["id"]] = {**doc, "evidence_basis": "semantic", "evidence_span": sentence}
                    ranking[doc["id"]] = 1/(100+rank)          # below every lexical result
                    semantic_active = True
        except ModelUnavailable:
            pass  # Explicit degraded mode, revealed in API response.
    # A comparison that could not be confirmed never outranks one that was.
    ranked = sorted(ranking, key=lambda did: (documents[did].get("condition_status") == "unverified", -ranking[did]))[:k]
    results = []
    for did in ranked:
        item = {"id": did, "title": documents[did]["title"], "category": documents[did]["category"],
                "content": documents[did]["content"], "score": round(ranking[did], 4)}
        if documents[did].get("condition_status"):
            item["condition_status"] = documents[did]["condition_status"]
        if documents[did].get("evidence_basis"):
            item["evidence_basis"] = documents[did]["evidence_basis"]      # "semantic": found by meaning, to be verified
            item["evidence_span"] = documents[did]["evidence_span"]
        results.append(item)
    return results, ("hybrid" if semantic_active else "lexical")
