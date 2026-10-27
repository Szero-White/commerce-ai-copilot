"""The evidence gate. Synthetic scores and vectors: they check the DECISION LOGIC, not how good any embedding is.

Passing here says nothing about real embeddings. The thresholds in SemanticParams are uncalibrated defaults.
"""
import pytest

from app import retrieval
from app.config import Settings
from app.gate import SemanticParams, admit_semantic, check_document
from app.query import Lexicon, analyze
from app.storage import SYNONYMS, Store

P = SemanticParams()


def scores(**kw):
    return dict(kw)


def spans(*ids, value=0.9):
    return {i: (value, f"sentence of {i}") for i in ids}


def allow_all(_):
    return True


def background(n=8, value=0.2):
    return {f"bg{i}": value + i * 0.001 for i in range(n)}


# ---- admit_semantic: each clause of the rule has a case that fails without it -----------------------------------------
def test_a_clear_single_winner_with_a_matching_sentence_is_admitted():
    s = {**background(), "win": 0.8}
    assert admit_semantic(s, spans("win"), True, allow_all) == [("win", "sentence of win")]


def test_without_a_matching_sentence_nothing_is_admitted():
    s = {**background(), "win": 0.8}
    assert admit_semantic(s, {}, True, allow_all) == []                      # no sentence vectors indexed: safe default
    assert admit_semantic(s, spans("win", value=0.3), True, allow_all) == []  # sentence too dissimilar


def test_scores_that_are_high_for_every_document_are_not_evidence():
    flat = {f"d{i}": 0.7 + i * 0.0001 for i in range(8)}
    assert admit_semantic(flat, spans(*flat), False, allow_all) == []        # z-score ~ 0: nothing stands out


def test_a_low_score_is_never_admitted_however_much_it_stands_out():
    s = {**background(value=0.0), "x": 0.3}
    assert admit_semantic(s, spans("x"), True, allow_all) == []


def test_two_equally_good_documents_are_not_a_single_answer():
    s = {**background(), "a": 0.80, "b": 0.79}
    assert admit_semantic(s, spans("a", "b"), True, allow_all) == []         # ask which one is meant


def test_a_list_question_admits_every_document_of_the_top_group_without_a_gap_to_the_next():
    s = {**background(), "a": 0.80, "b": 0.79, "c": 0.78, "d": 0.77}
    got = [i for i, _ in admit_semantic(s, spans("a", "b", "c", "d"), False, allow_all)]
    assert got == ["a", "b", "c", "d"]


def test_a_list_stops_at_the_tail_and_at_the_cap():
    s = {**background(), "a": 0.80, "b": 0.79, "far": 0.62}
    assert [i for i, _ in admit_semantic(s, spans("a", "b", "far"), False, allow_all)] == ["a", "b"]
    many = {**background(20), **{f"m{i}": 0.80 - i * 0.001 for i in range(9)}}
    assert len(admit_semantic(many, spans(*many), False, allow_all)) == P.max_list


def test_hard_constraints_veto_a_document_whatever_its_score():
    s = {**background(), "win": 0.9, "second": 0.82}
    assert admit_semantic(s, spans("win", "second"), False, lambda d: d != "win") == [("second", "sentence of second")]


def test_too_few_documents_give_no_distribution_to_judge_a_score_by():
    assert admit_semantic({"a": 0.9, "b": 0.1}, spans("a"), True, allow_all) == []


# ---- check_document: hard constraints that no similarity can override ---------------------------------------------
def verdict(question, text, corpus=None):
    analysis = analyze(question, Lexicon([text] + (corpus or []), known=SYNONYMS))
    return check_document(analysis, text, __import__("app.storage", fromlist=["normalize"]).normalize(text).split())


def test_check_document_applies_the_same_rules_to_any_candidate():
    text = "Ghế Nimbus mã NIM7. Giá 450.000 VND. Cao 90 cm."
    assert verdict("Ghế Nimbus mã NIM7", text).admitted
    assert not verdict("Ghế Nimbus mã NIM8", text).admitted                  # code
    assert not verdict("Ghế Nimbus Pro", text).admitted                      # unknown name
    assert not verdict("Ghế Nimbus còn hàng không", text).admitted           # stock without a figure
    assert not verdict("Ghế Nimbus giảm 5%", text).admitted                  # percentage not stated
    assert verdict("Ghế Nimbus dưới 500 nghìn", text).condition == "satisfied"
    assert not verdict("Ghế Nimbus dưới 100 nghìn", text).admitted
    unsure = verdict("Ghế Nimbus rộng hơn 50 cm", text)       # the document gives a height only
    assert unsure.admitted and unsure.condition == "unverified"


# ---- the search no longer lets a vector admit a document ------------------------------------------------------------
@pytest.fixture()
def vector_store(tmp_path):
    store = Store(tmp_path / "v.db")
    for doc in store.documents():
        store.update_embedding(doc["id"], [1.0, 0.0], "m")     # every document is "close" to every query
    settings = Settings(data_path=tmp_path / "v.db", llm_provider="off", embedding_provider="ollama", embedding_model="m")
    return store, settings


def test_hybrid_search_does_not_add_documents_the_gate_rejected(vector_store, monkeypatch):
    store, settings = vector_store
    monkeypatch.setattr(retrieval, "embed", lambda *_: [[1.0, 0.0]])
    found, mode = retrieval.search(store, settings, "personalized ceramic mug", k=5)
    assert [d["id"] for d in found] == ["POD-201"] and mode == "hybrid"       # not the 14 other "close" documents


def test_hybrid_search_cannot_answer_what_the_gate_refuses(vector_store, monkeypatch):
    store, settings = vector_store
    monkeypatch.setattr(retrieval, "embed", lambda *_: [[1.0, 0.0]])
    for question in ("quasar neutrino qubit zyzzyva", "Bàn Oak 120 còn hàng không?", "Bàn Oak 150 kích thước bao nhiêu?",
                     "Đèn bàn Focus Pro có mấy mức sáng?"):
        assert retrieval.search(store, settings, question)[0] == [], question
