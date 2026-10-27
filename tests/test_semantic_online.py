"""Meaning-based candidates + LLM verification. Fake embeddings and a fake LLM: they test the WIRING and the safety logic.

Nothing here says anything about Gemini; the real check is `scripts.blind_eval --online` run by the key owner.
"""
import pytest

from app import retrieval, services
from app.config import Settings
from app.storage import Store

TOPICS = ["amber", "birch", "cedar", "dune", "ember", "fjord"]


def fake_embed(settings, texts):
    out = []
    for text in texts:
        low = text.lower()
        v = [0.0] * 8
        for i, t in enumerate(TOPICS):
            if t in low:
                v[i] = 1.0 if "item" in low else 0.9
        if "amberish" in low:
            v[0], v[6] = 0.9, 0.1
        if "cedarish" in low:
            v[2], v[7] = 0.5, 0.8              # only vaguely close: must stay below the thresholds
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


def ask(store, tmp_path, question, llm="ollama", reply=None, monkeypatch=None, seen=None):
    def chat(settings, system, user, json_output=False):
        if seen is not None:
            seen.append(user)
        return reply or "Item amber is described here [E-amber]", 10, 5
    services.ollama_chat = chat
    return services.question_answer(store, settings(tmp_path, llm=llm), question)


@pytest.fixture(autouse=True)
def restore_chat():
    original = services.ollama_chat
    yield
    services.ollama_chat = original


def test_sentences_are_stored_per_document_and_follow_updates_and_deletes(store, tmp_path):
    assert [s["doc_id"] for s in store.spans()] == [f"E-{t}" for t in sorted(TOPICS)]
    store.upsert({"id": "E-amber", "title": "Item amber", "category": "product",
                  "content": "Item amber was rewritten. It now has a second sentence of its own."})
    amber = [s for s in store.spans() if s["doc_id"] == "E-amber"]
    assert len(amber) == 2 and all(s["embedding_json"] is None for s in amber)           # old sentence vector dropped
    store.delete("E-amber")
    assert not [s for s in store.spans() if s["doc_id"] == "E-amber"]
    assert retrieval.index_vectors(store, settings(tmp_path))["spans_indexed"] == 0 and store.consistency_report()["ok"]


def test_a_meaning_match_is_added_only_when_an_llm_will_verify_it(store, tmp_path):
    q = "qqq wxyz amberish need"
    found, mode = retrieval.search(store, settings(tmp_path), q)
    assert [d["id"] for d in found] == ["E-amber"] and found[0]["evidence_basis"] == "semantic" and mode == "hybrid"
    assert "tìm theo ngữ nghĩa" not in found[0]["content"]
    assert retrieval.search(store, settings(tmp_path, llm="off"), q)[0] == []             # no verifier: channel closed
    assert retrieval.search(store, settings(tmp_path, embedding="off"), q)[0] == []


def test_the_llm_is_told_to_state_only_what_the_documents_say_and_its_answer_is_checked(store, tmp_path):
    seen = []
    result = ask(store, tmp_path, "qqq wxyz amberish need", seen=seen)
    assert result["mode"] == "llm_rag_cited" and [s["id"] for s in result["sources"]] == ["E-amber"]
    assert "NGỮ NGHĨA" in seen[0] and "chưa có đủ thông tin" in seen[0] and "tìm theo ngữ nghĩa" in seen[0]
    seen.clear()
    ask(store, tmp_path, "Item birch is described here", seen=seen)                      # a lexical hit: no verification text
    assert seen and "NGỮ NGHĨA" not in seen[0]


def test_when_the_llm_finds_the_documents_insufficient_nothing_is_claimed_and_no_source_is_shown(store, tmp_path):
    result = ask(store, tmp_path, "qqq wxyz amberish need", reply="Tôi chưa có đủ thông tin trong tài liệu để xác nhận")
    assert result["mode"] == "llm_insufficient_evidence" and result["sources"] == []
    assert "chưa có đủ thông tin" in result["answer"] and result["citation_ids_checked"] is True


def test_a_meaning_only_source_is_never_shown_when_the_llm_could_not_verify_it(store, tmp_path):
    from app.ollama import ModelUnavailable

    def down(settings, system, user, json_output=False):
        raise ModelUnavailable("offline")
    services.ollama_chat = down
    result = services.question_answer(store, settings(tmp_path), "qqq wxyz amberish need")
    assert result["mode"] == "llm_unavailable_extractive" and result["sources"] == []
    assert "chưa có đủ thông tin" in result["answer"]
    # a document the gate admitted BY WORDS is still shown for the user to read
    lexical = services.question_answer(store, settings(tmp_path), "Item birch is described here")
    assert lexical["mode"] == "llm_unavailable_extractive" and [s["id"] for s in lexical["sources"]] == ["E-birch"]
    # an answer that fails the citation check does not smuggle the meaning-only source in either
    services.ollama_chat = lambda *a, **k: ("Item amber is described here [E-nope]", 1, 1)
    rejected = services.question_answer(store, settings(tmp_path), "qqq wxyz amberish need")
    assert rejected["mode"] == "llm_citation_rejected_extractive" and rejected["sources"] == []


def test_hard_constraints_still_veto_a_meaning_match(store, tmp_path):
    for question in ("Zephyr Pro qqq amberish need", "qqq amberish need giảm 5%", "qqq amberish còn hàng không"):
        assert retrieval.search(store, settings(tmp_path), question)[0] == [], question


def test_a_vaguely_similar_question_stays_below_the_thresholds(store, tmp_path):
    assert retrieval.search(store, settings(tmp_path), "qqq wxyz cedarish need")[0] == []
