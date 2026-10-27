"""The evidence check of a meaning-found answer is done by code, not by trusting a pasted citation id."""
import json

import pytest

from app.gate import CandidateParams, rank_candidates
from app.verification import parse, verify

DOC = {"id": "P-1", "title": "Đèn Lumi", "category": "product",
       "content": "Đèn Lumi có ba mức sáng, nguồn USB-C 5V. Giá niêm yết 390.000 VND. Bảo hành 6 tháng."}
QUOTE = "Đèn Lumi có ba mức sáng, nguồn USB-C 5V."


def reply(**kw):
    base = {"decision": "answer", "kind": "recommendation", "source_id": "P-1", "quote": QUOTE,
            "answer": "Đèn Lumi có ba mức sáng, hợp để học ban đêm"}
    return json.dumps({**base, **kw}, ensure_ascii=False)


def test_a_supported_answer_passes_and_the_citation_is_appended_by_the_code():
    ok, reason, text, source, quote = verify(reply(), [DOC])
    assert ok and reason == "ok" and text.endswith("[P-1]") and source is DOC and quote == QUOTE


def test_the_quote_may_differ_in_case_and_diacritics_but_not_in_words():
    assert verify(reply(quote="đèn lumi CÓ BA MỨC SÁNG"), [DOC])[0]
    assert verify(reply(quote="den lumi co ba muc sang"), [DOC])[0]
    assert not verify(reply(quote="Đèn Lumi có nhiều mức sáng, nguồn USB-C 5V."), [DOC])[0]


@pytest.mark.parametrize("kw,reason", [
    ({"decision": "decline"}, "declined"),
    ({"quote": "Đèn Lumi chống nước hoàn toàn."}, "the quoted sentence is not in the document"),
    ({"quote": "Đèn Lumi"}, "the quoted sentence is not in the document"),                  # too short to be evidence
    ({"source_id": "P-9"}, "source id is not one of the documents"),
    ({"answer": ""}, "no usable answer"),
    ({"answer": "Đèn Lumi có 3 mức sáng"}, "a number in the answer is not in the quoted sentence"),
    ({"answer": "Giá 390.000 VND"}, "a number in the answer is not in the quoted sentence"),   # true in the document, not in the quote
    ({"answer": "Miễn phí giao hàng toàn quốc"}, "the answer fails the evidence check"),
])
def test_an_unsupported_answer_is_refused_with_a_reason(kw, reason):
    ok, why, text, *_ = verify(reply(**kw), [DOC])
    assert not ok and why == reason and text == ""


@pytest.mark.parametrize("raw", ["", "không phải json", "[1, 2]", "null", "Có ạ [P-1]"])
def test_an_unreadable_reply_is_not_enough_information(raw):
    assert verify(raw, [DOC])[:2] == (False, "unreadable reply")


def test_a_reply_wrapped_in_a_code_fence_is_still_read():
    assert parse("```json\n" + reply() + "\n```")["source_id"] == "P-1"


# ---- candidate generation by rank --------------------------------------------------------------------------------
def allow(_):
    return True


def test_the_same_ranking_nominates_the_same_document_whatever_the_scale_of_the_scores():
    chatty = {"a": 0.64, "b": 0.58, "c": 0.575, "d": 0.57, "e": 0.55, "f": 0.54, "g": 0.53, "h": 0.52}
    shouted = {k: v + 0.12 for k, v in chatty.items()}               # a short, direct question: everything scores higher
    assert rank_candidates(chatty, allow) == rank_candidates(shouted, allow) == ["a"]


def test_a_flat_profile_nominates_nothing_and_a_close_runner_up_is_nominated_too():
    assert rank_candidates({k: 0.6 + 0.001 * i for i, k in enumerate("abcdefgh")}, allow) == []
    scores = {"a": 0.80, "b": 0.78, "c": 0.45, "d": 0.44, "e": 0.43, "f": 0.42, "g": 0.41}
    assert rank_candidates(scores, allow) == ["a", "b"]
    assert rank_candidates(scores, allow, CandidateParams(max_candidates=1)) == ["a"]


def test_hard_constraints_remove_a_candidate_before_any_other_rule():
    scores = {"a": 0.9, "b": 0.88, "c": 0.4, "d": 0.4, "e": 0.41, "f": 0.39}
    assert rank_candidates(scores, lambda d: d != "a") == ["b"]
    assert rank_candidates({"a": 0.9, "b": 0.5}, allow) == []         # too few documents to say what stands out
