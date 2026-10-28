"""Regression tests for the generalisation audit: synthetic documents that are not in the demo catalogue, grouped by capability.
Offline, LLM off. The case file is a DEV set (written after the root-cause analysis), not an independent evaluation."""
import json
import re

import pytest

import app.services as services
from app import verification
from app.config import ROOT
from app.evidence import answer_problems, question_numbers_for
from app.query import Lexicon, analyze
from app.quantities import extract, limit_results
from app.storage import SYNONYMS
from scripts.generalization_eval import DEFAULT, load_store, run
from scripts.trace_query import trace_pipeline

SPEC = json.loads(DEFAULT.read_text(encoding="utf-8"))


def test_every_case_passes_except_the_declared_known_limits():
    report = run(SPEC)
    unexpected = [r for r in report["records"] if not r["passed"] and not r["known_limit"]]
    assert not unexpected, unexpected
    assert set(report["measures"]) == {"retrieval", "answer", "groundedness", "refusal", "multi_turn"}
    assert all(m["total"] >= 5 for m in report["measures"].values())     # each measure is really exercised


def test_the_declared_known_limit_still_fails_honestly():
    # If this starts passing, the label is stale: remove known_limit instead of keeping a false claim.
    report = run(SPEC)
    failing = {r["case"] for r in report["records"] if not r["passed"]}
    assert failing == {"para-1"}


def test_the_audit_documents_are_not_the_demo_catalogue():
    seed = (ROOT / "data" / "seed_documents.json").read_text(encoding="utf-8")
    assert not any(d["title"] in seed for d in SPEC["documents"] if d["category"] == "product")


# ---- root causes, one test each --------------------------------------------------------------------------------------
LIMIT_TEXT = "Kệ sách Linden 5 tầng, tải trọng tối đa 45 kg mỗi kệ. Nặng 18 kg. Bảo hành 24 tháng."


def test_a_stated_ceiling_is_compared_in_code_not_called_a_contradiction():
    q = extract("chịu được 80 kg")
    [result] = limit_results(q, LIMIT_TEXT)
    assert result.relation == "exceeds" and "VƯỢT" in result.detail
    assert limit_results(extract("chịu được 30 kg"), LIMIT_TEXT)[0].relation == "within"


def test_the_weight_of_the_product_is_not_taken_for_a_ceiling():
    assert limit_results(extract("Kệ nặng 20 kg"), "Nặng 18 kg. Bảo hành 24 tháng.") == []
    assert limit_results(extract("chịu được 80 kg"), "Nặng 18 kg.") == []          # no limit stated: nothing concluded


def test_two_limits_of_one_kind_conclude_nothing():
    text = "Mỗi kệ chịu tải tối đa 15 kg, cả bộ tối đa 60 kg."
    assert limit_results(extract("chịu được 40 kg"), text) == []


def test_a_minimum_is_a_minimum():
    [r] = limit_results(extract("đặt 1 ngày"), "Thời gian đặt trước tối thiểu 3 ngày.")
    assert r.relation == "below"


SRC = [{"id": "T-001", "title": "Kệ sách Linden", "content": LIMIT_TEXT, "condition_status": "limit_exceeds"}]


def test_a_correct_answer_may_repeat_the_figure_the_customer_asked_when_the_comparison_was_computed():
    answer = "Không, kệ chỉ chịu tối đa 45 kg nên không chịu được 80 kg [T-001]"
    assert answer_problems(answer, SRC)                                       # the old guard rejects it (the cause)
    assert not answer_problems(answer, SRC, question_numbers_for("chịu được 80 kg không?", SRC))


def test_the_asked_figure_is_not_allowed_without_a_computed_comparison():
    plain = [{**SRC[0], "condition_status": None}]
    assert question_numbers_for("giảm 90% đúng không", plain) == set()
    assert answer_problems("Có, giảm 90% [T-001]", plain, question_numbers_for("giảm 90% đúng không", plain))


def test_a_fabricated_figure_is_still_rejected_next_to_a_computed_comparison():
    bad = "Kệ chịu tối đa 45 kg, bảo hành 60 tháng, không chịu được 80 kg [T-001]"
    assert answer_problems(bad, SRC, question_numbers_for("chịu được 80 kg không?", SRC))


def test_verification_accepts_the_asked_figure_only_with_a_computed_comparison():
    import json as j
    reply = j.dumps({"decision": "answer", "kind": "fact", "source_id": "T-001", "quote": "tải trọng tối đa 45 kg mỗi kệ",
                     "answer": "Không, kệ chỉ chịu tối đa 45 kg nên không chịu được 80 kg."}, ensure_ascii=False)
    assert verification.verify(reply, SRC, "Kệ Linden chịu được 80 kg không?").ok
    plain = [{**SRC[0], "condition_status": None}]
    assert not verification.verify(reply, plain, "Kệ Linden chịu được 80 kg không?").ok


def test_gemini_style_answer_with_the_asked_number_is_kept_in_the_lexical_llm_path(tmp_path, monkeypatch):
    store, settings = load_store(SPEC, tmp_path)
    monkeypatch.setattr(services, "llm_enabled", lambda s: True)
    monkeypatch.setattr(services, "ollama_chat", lambda *a, **k: (
        "Không. Kệ sách Linden chỉ chịu tối đa 45 kg nên không chịu được 80 kg [T-001]", 100, 30))
    r = services.question_answer(store, settings, "Kệ sách Linden chịu được 80 kg không?")
    assert r["mode"] == "llm_rag_cited" and [s["id"] for s in r["sources"]] == ["T-001"]


def test_an_ordinary_word_typed_with_diacritics_is_not_turned_into_a_brand_name():
    lex = Lexicon(["Kệ sách Linden bảo hành 24 tháng"], known=SYNONYMS, titles=["Kệ sách Linden"])
    assert lex.correct("lien") == "linden"                                    # typed without diacritics: still a possible slip
    assert lex.correct("lien", deliberate=True) is None
    assert "linden" not in analyze("Điều kiện liên quan là gì?", lex).terms


def test_capacity_verbs_next_to_a_weight_are_searched_but_not_required():
    lex = Lexicon(["Kệ sách Linden tải trọng tối đa 45 kg"], known=SYNONYMS, titles=["Kệ sách Linden"])
    a = analyze("Kệ Linden có chịu nổi 45 kg không?", lex)
    assert "linden" in a.terms and "chiu" not in a.terms and "chiu" in a.soft


def test_the_trace_names_the_stage_that_decided(tmp_path):
    store, settings = load_store(SPEC, tmp_path)
    first = trace_pipeline(store, settings, "Chính sách đổi trả kệ sách Linden thế nào?")
    follow = trace_pipeline(store, settings, "Còn phí vận chuyển thì sao?", first["turn_context"])
    assert follow["resolution"]["action"] == "scope" and follow["analysis"]["pointer"][0] == "topic"
    assert [s["id"] for s in follow["sources"]] == ["T-003"]
    none = trace_pipeline(store, settings, "Kệ Linden chịu được 80 kg không?")
    assert none["sources"][0]["condition"] == "limit_exceeds" and "VƯỢT" in none["sources"][0]["detail"]


def test_a_follow_up_with_a_new_unknown_name_is_not_bound_to_the_old_topic(tmp_path):
    store, settings = load_store(SPEC, tmp_path)
    first = services.question_answer(store, settings, "Chính sách đổi trả kệ sách Linden thế nào?")
    r = services.question_answer(store, settings, "Còn Zephyr thì sao?", first["turn_context"])
    assert r["query_trace"]["names"] == ["zephyr"]          # read as a new, unknown name, not as a pointer to Linden
    assert r["sources"] == [] and r["mode"] == "no_evidence"
