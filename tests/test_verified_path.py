"""Mixed turns: a document admitted by words AND a document found only by meaning (hybrid retrieval), checked per cited source.

Fake embeddings with chosen vectors and a fake LLM: these test the WIRING and the safety logic, not what Gemini writes.
Pinned here: the meaning-only nominee stays in the context; a failure never silently drops the documents the gate admitted
(they are shown, labelled as NOT a verified answer); a meaning-only document is never shown unverified; the wording check
(`verification._unsupported`) is unchanged."""
import json

import pytest

from app import retrieval, services
from app.config import Settings
from app.storage import Store

TOPICS = ["amber", "birch", "cedar", "dune", "ember", "fjord"]
MIXED = "Item birch is described here"            # words admit E-birch; the vector also points at E-amber (a nominee)
ONLY_MEANING = "qqq wxyz amberish need"
NOTHING = "zzz"
QUERIES = {MIXED: ("birch", "amber"), ONLY_MEANING: ("amber",), NOTHING: ()}


def vector(topics):
    v = [0.0] * 8
    for t in topics:
        v[TOPICS.index(t)] = 1.0
    if not topics:
        v[7] = 1.0
    return v


def fake_embed(settings, texts):
    return [vector(QUERIES[t]) if t in QUERIES else vector([x for x in TOPICS if x in t.lower()][:1]) for t in texts]


def settings(tmp_path):
    return Settings(data_path=tmp_path / "v.db", llm_provider="ollama", embedding_provider="ollama", embedding_model="m")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "embed", fake_embed)
    original = services.ollama_chat
    s = Store(tmp_path / "v.db")
    s.delete_source("seed")
    s.apply([{"id": f"E-{t}", "title": f"Item {t}", "category": "product",
              "content": f"Item {t} is described here in one plain sentence about {t}."} for t in TOPICS], source="t")
    retrieval.index_vectors(s, settings(tmp_path))
    yield s
    services.ollama_chat = original


def quote(topic):
    return f"Item {topic} is described here in one plain sentence about {topic}."


def verdict(topic="birch", **kw):
    base = {"decision": "answer", "kind": "fact", "source_id": f"E-{topic}", "quote": quote(topic),
            "answer": f"Item {topic} is described here"}
    return json.dumps({**base, **kw}, ensure_ascii=False)


def ask(store, tmp_path, question, reply, seen=None):
    def chat(settings, system, user, json_output=False):
        if seen is not None:
            seen.append(user)
        return reply, 10, 5
    services.ollama_chat = chat
    return services.question_answer(store, settings(tmp_path), question)


def ids(result):
    return [s["id"] for s in result["sources"]]


# ---- the setting itself: a lexical document and a meaning-only nominee in the same context ---------------------------------
def test_the_mixed_turn_really_has_a_lexical_hit_and_a_meaning_only_nominee(store, tmp_path):
    found, mode = retrieval.search(store, settings(tmp_path), MIXED)
    basis = {d["id"]: d.get("evidence_basis", "lexical") for d in found}
    assert basis == {"E-birch": "lexical", "E-amber": "semantic"} and mode == "hybrid"


# ---- lexical right / semantic wrong ----------------------------------------------------------------------------------------
def test_a_correct_citation_of_the_lexical_document_is_verified_and_the_nominee_stays_in_the_context(store, tmp_path):
    seen = []
    r = ask(store, tmp_path, MIXED, verdict("birch"), seen=seen)
    assert r["mode"] == "llm_rag_cited" and ids(r) == ["E-birch"]
    v = r["verification"]
    assert v["reason"] == "ok" and v["cited_basis"] == "lexical" and v["lexical_documents"] == ["E-birch"]
    assert v["checks"] == {"citation": True, "quote": True, "numbers": True, "guard": True, "wording": True}
    assert "[E-amber]" in seen[0] and "tìm theo ngữ nghĩa" in seen[0]          # hybrid retrieval is kept: the model still sees it


# ---- lexical wrong / semantic right ----------------------------------------------------------------------------------------
def test_a_correct_citation_of_the_meaning_found_document_is_verified_and_shows_only_it(store, tmp_path):
    r = ask(store, tmp_path, MIXED, verdict("amber"))
    assert r["mode"] == "llm_rag_cited" and ids(r) == ["E-amber"]
    assert r["verification"]["cited_basis"] == "semantic" and r["verification"]["checks"]["quote"] is True


# ---- the model declines, or fabricates -------------------------------------------------------------------------------------
def test_a_decline_shows_the_gate_admitted_document_labelled_unverified_and_never_the_nominee(store, tmp_path):
    r = ask(store, tmp_path, MIXED, verdict(decision="decline"))
    assert r["mode"] == "llm_citation_rejected_extractive" and ids(r) == ["E-birch"]
    assert r["answer"].startswith("CHƯA có câu trả lời được xác minh") and "E-amber" not in r["answer"]
    assert r["grounding_note"].startswith("Đây chưa phải câu trả lời được xác minh")
    assert r["verification"]["reason"] == "declined" and r["verification"]["lexical_documents"] == ["E-birch"]


@pytest.mark.parametrize("reply,failed", [
    (verdict("birch", answer="Giá chỉ 1 VND"), "numbers"),                                     # a figure the quote lacks
    (verdict("birch", source_id="E-nope"), "citation"),                                         # not one of the documents
    (verdict("birch", quote="Item birch is described plainly, nobody wrote this."), "quote"),    # invented / paraphrased evidence
    (verdict("birch", answer="Item birch was approved by the board"), "wording"),               # unchanged strict wording rule
])
def test_a_fabricated_or_unsupported_answer_is_not_shown_as_verified(store, tmp_path, reply, failed):
    r = ask(store, tmp_path, MIXED, reply)
    assert r["mode"] == "llm_citation_rejected_extractive" and ids(r) == ["E-birch"]
    assert "CHƯA có câu trả lời được xác minh" in r["answer"]
    assert "1 VND" not in r["answer"] and "approved" not in r["answer"]
    assert r["verification"]["checks"][failed] is False


def test_a_failed_citation_of_the_nominee_shows_the_lexical_document_not_the_nominee(store, tmp_path):
    r = ask(store, tmp_path, MIXED, verdict("amber", quote="Item amber has a lifetime warranty on everything."))
    assert r["mode"] == "llm_citation_rejected_extractive" and ids(r) == ["E-birch"]
    assert r["verification"]["cited_basis"] == "semantic" and "[E-amber]" not in r["answer"]


def test_a_negated_policy_is_still_not_affirmed_in_a_mixed_turn(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "embed", fake_embed)
    s = Store(tmp_path / "n.db")
    s.delete_source("seed")
    s.apply([{"id": "E-birch", "title": "Item birch", "category": "product",
              "content": "Item birch is described here. Hoàn tiền không được áp dụng cho Item birch."},
             {"id": "E-amber", "title": "Item amber", "category": "product", "content": "Item amber is described here about amber."},
             {"id": "E-cedar", "title": "Item cedar", "category": "product", "content": "Item cedar is described here about cedar."}], source="t")
    retrieval.index_vectors(s, Settings(data_path=tmp_path / "n.db", llm_provider="ollama", embedding_provider="ollama", embedding_model="m"))
    r = ask(s, tmp_path, MIXED, json.dumps({"decision": "answer", "kind": "fact", "source_id": "E-birch",
                                             "quote": "Item birch is described here", "answer": "Bạn sẽ được hoàn tiền"}))
    assert r["mode"] != "llm_rag_cited" and "Bạn sẽ được hoàn tiền" not in r["answer"]


# ---- no evidence at all ----------------------------------------------------------------------------------------------------
def test_a_nominee_alone_that_the_model_declines_still_gives_no_sources(store, tmp_path):
    r = ask(store, tmp_path, ONLY_MEANING, verdict("amber", decision="decline"))
    assert r["mode"] == "llm_insufficient_evidence" and r["sources"] == []
    assert r["verification"]["lexical_documents"] == []


def test_a_question_with_no_candidate_does_not_reach_the_model(store, tmp_path):
    seen = []
    r = ask(store, tmp_path, NOTHING, verdict("birch"), seen=seen)
    assert r["mode"] == "no_evidence" and r["sources"] == [] and seen == []


def test_the_checks_are_reported_level_by_level():
    from app.verification import verify
    src = [{"id": "E-birch", "title": "Item birch", "content": quote("birch")}]
    assert verify(verdict(decision="decline"), src, "q").info["checks"] == dict.fromkeys(("citation", "quote", "numbers", "guard", "wording"))
    assert verify(verdict(), src, "q").info["checks"] == {"citation": True, "quote": True, "numbers": True, "guard": True, "wording": True}
