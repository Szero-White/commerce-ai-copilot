"""Meaning-based nomination + verified answers. Fake embeddings and a fake LLM: they test the WIRING and the safety logic.

Nothing here says anything about Gemini; the real check is `scripts.blind_eval --online` run by the key owner.
"""
import json

import pytest

from app import retrieval, services
from app.config import Settings
from app.ollama import ModelUnavailable
from app.storage import Store

TOPICS = ["amber", "birch", "cedar", "dune", "ember", "fjord"]


def fake_embed(settings, texts):
    """Documents/sentences point at their topic word; a question points at a topic through a cue ("amberish"), whatever
    its wording or length. This stands in for 'the same need, phrased differently'."""
    out = []
    for text in texts:
        low = text.lower()
        v = [0.0] * 8
        for i, t in enumerate(TOPICS):
            if t in low:
                v[i] = 1.0 if "item" in low else 0.9
            if t + "ish" in low:
                v[i], v[6] = 0.6, 0.15        # lower, noisier similarity than a document: no absolute threshold may depend on it
        if not any(v):
            v[7] = 1.0
        out.append(v)
    return out


def settings(tmp_path, llm="ollama", embedding="ollama"):
    return Settings(data_path=tmp_path / "s.db", llm_provider=llm, embedding_provider=embedding, embedding_model="m")


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "embed", fake_embed)
    s = Store(tmp_path / "s.db")
    s.delete_source("seed")
    s.apply([{"id": f"E-{t}", "title": f"Item {t}", "category": "product",
              "content": f"Item {t} is described here in one plain sentence about {t}."} for t in TOPICS], source="t")
    assert retrieval.index_vectors(s, settings(tmp_path))["spans_indexed"] == len(TOPICS)
    return s


QUOTE = "Item amber is described here in one plain sentence about amber."


def verdict(**kw):
    base = {"decision": "answer", "kind": "recommendation", "source_id": "E-amber", "quote": QUOTE,
            "answer": "Item amber được mô tả ngay trong tài liệu"}
    return json.dumps({**base, **kw}, ensure_ascii=False)


@pytest.fixture(autouse=True)
def restore_chat():
    original = services.ollama_chat
    yield
    services.ollama_chat = original


def ask(store, tmp_path, question, reply, seen=None, llm="ollama"):
    def chat(settings, system, user, json_output=False):
        if seen is not None:
            seen.append((user, json_output))
        if isinstance(reply, Exception):
            raise reply
        return reply, 10, 5
    services.ollama_chat = chat
    return services.question_answer(store, settings(tmp_path, llm=llm), question)


def test_sentences_are_stored_per_document_and_follow_updates_and_deletes(store, tmp_path):
    assert [s["doc_id"] for s in store.spans()] == [f"E-{t}" for t in sorted(TOPICS)]
    store.upsert({"id": "E-amber", "title": "Item amber", "category": "product",
                  "content": "Item amber was rewritten. It now has a second sentence of its own."})
    amber = [s for s in store.spans() if s["doc_id"] == "E-amber"]
    assert len(amber) == 2 and all(s["embedding_json"] is None for s in amber)           # old sentence vector dropped
    store.delete("E-amber")
    assert not [s for s in store.spans() if s["doc_id"] == "E-amber"]
    assert retrieval.index_vectors(store, settings(tmp_path))["spans_indexed"] == 0 and store.consistency_report()["ok"]


# ---- nomination ----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("question", [
    "qqq wxyz amberish need",
    "Tôi đang tìm một thứ gì đó, nói dài dòng cho vui, rồi mới nhắc tới amberish thôi, bạn có gợi ý nào không?",
    "amberish",
])
def test_the_same_need_in_other_words_nominates_the_same_document(store, tmp_path, question):
    found, mode = retrieval.search(store, settings(tmp_path), question)
    assert [d["id"] for d in found] == ["E-amber"] and found[0]["evidence_basis"] == "semantic" and mode == "hybrid"


def test_nomination_needs_an_llm_to_verify_and_stays_closed_otherwise(store, tmp_path):
    q = "qqq wxyz amberish need"
    assert retrieval.search(store, settings(tmp_path, llm="off"), q)[0] == []
    assert retrieval.search(store, settings(tmp_path, embedding="off"), q)[0] == []


def test_a_new_product_is_found_by_meaning_after_it_is_added_and_indexed(store, tmp_path):
    q = "xx fjordish yy"
    assert [d["id"] for d in retrieval.search(store, settings(tmp_path), q)[0]] == ["E-fjord"]
    store.delete("E-fjord")                                                              # withdrawn: no stale nomination
    assert retrieval.search(store, settings(tmp_path), q)[0] == []
    store.apply([{"id": "E-new", "title": "Item fjord", "category": "product",
                  "content": "Item fjord is a brand new product described here, about fjord."}], source="new")
    assert retrieval.search(store, settings(tmp_path), q)[0] == []                        # not indexed yet: no vectors, no guess
    assert retrieval.index_vectors(store, settings(tmp_path))["indexed"] == 1
    assert [d["id"] for d in retrieval.search(store, settings(tmp_path), q)[0]] == ["E-new"]


def test_hard_constraints_still_veto_a_nominated_document(store, tmp_path):
    for question in ("Zephyr Pro qqq amberish need", "qqq amberish need giảm 5%", "qqq amberish còn hàng không"):
        assert retrieval.search(store, settings(tmp_path), question)[0] == [], question


# ---- verified answers ----------------------------------------------------------------------------------------------
def test_a_verified_answer_shows_its_evidence_and_only_that_source(store, tmp_path):
    seen = []
    result = ask(store, tmp_path, "qqq wxyz amberish need", verdict(), seen=seen)
    assert result["mode"] == "llm_rag_cited" and [s["id"] for s in result["sources"]] == ["E-amber"]
    assert "[E-amber]" in result["answer"] and f"«{QUOTE}»" in result["answer"]
    user, json_output = seen[0]
    assert json_output is True and "NGUYÊN VĂN" in user and "tìm theo ngữ nghĩa" in user


def test_the_answer_is_refused_when_the_evidence_does_not_check_out(store, tmp_path):
    q = "qqq wxyz amberish need"
    for reply in (verdict(decision="decline"),                                         # the model found nothing
                  verdict(quote="Item amber has a lifetime warranty on everything."),   # invented evidence
                  verdict(quote="Item amber is described plainly."),                    # a paraphrase, not a quote
                  verdict(answer="Giá chỉ 1 VND"),                                      # a number the quote lacks
                  verdict(source_id="E-nope"),                                          # not one of the documents
                  "Dạ có ạ, sản phẩm này có bảo hành trọn đời [E-amber]",               # prose with an id pasted on
                  ""):
        result = ask(store, tmp_path, q, reply)
        assert result["mode"] == "llm_insufficient_evidence" and result["sources"] == [], reply
        assert "chưa có đủ thông tin" in result["answer"]


def test_a_lexical_answer_keeps_the_old_citation_path(store, tmp_path):
    seen = []
    result = ask(store, tmp_path, "Item birch is described here", "Item birch được mô tả [E-birch]", seen=seen)
    assert result["mode"] == "llm_rag_cited" and seen and seen[0][1] is False and "NGUYÊN VĂN" not in seen[0][0]


def test_a_nominated_source_is_never_shown_when_the_llm_is_down(store, tmp_path):
    result = ask(store, tmp_path, "qqq wxyz amberish need", ModelUnavailable("offline"))
    assert result["mode"] == "llm_unavailable_extractive" and result["sources"] == []
    lexical = ask(store, tmp_path, "Item birch is described here", ModelUnavailable("offline"))
    assert [s["id"] for s in lexical["sources"]] == ["E-birch"]             # words-admitted documents may still be read
