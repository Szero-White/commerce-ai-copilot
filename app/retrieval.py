"""Hybrid BM25 + cosine similarity (RRF). No pretend vectors: semantic mode must be enabled."""
import json
import math
from .llm import embed, embedding_enabled, ModelUnavailable


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
    if not docs:
        return {"enabled": True, "indexed": 0}
    count = 0
    try:
        for i in range(0, len(docs), 8):
            batch = docs[i:i+8]
            vectors = embed(settings, [d["title"] + "\n" + d["content"] for d in batch])
            for d, vec in zip(batch, vectors):
                store.update_embedding(d["id"], vec, settings.embedding_model)
                count += 1
        return {"enabled": True, "indexed": count}
    except ModelUnavailable as exc:
        return {"enabled": False, "indexed": count, "reason": str(exc)}


def search(store, settings, query, k=3):
    lexical = store.fts_search(query, limit=15)
    ranking = {}
    documents = {d["id"]: d for d in store.documents()}
    for rank, d in enumerate(lexical, 1):
        ranking[d["id"]] = ranking.get(d["id"], 0.0) + 1/(40+rank)
    semantic_active = False
    if embedding_enabled(settings):
        try:
            query_vector = embed(settings, [query])[0]
            semantic = []
            for d in documents.values():
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
            semantic_active = bool(semantic)
            for rank, (_, did) in enumerate(semantic[:15], 1):
                ranking[did] = ranking.get(did, 0.0) + 1/(40+rank)
        except ModelUnavailable:
            pass  # Explicit degraded mode, revealed in API response.
    ranked = sorted(ranking, key=lambda did: ranking[did], reverse=True)[:k]
    return [{"id": did,"title":documents[did]["title"],"category":documents[did]["category"],
             "content":documents[did]["content"],"score":round(ranking[did],4)} for did in ranked], (
             "hybrid" if semantic_active else "lexical")
