"""Phase 1 root-cause evidence for false abstention on short discovery questions.

The xfail(strict=True) tests state the DESIRED behaviour. They fail today (documenting the defect) and must be
un-marked, not edited, when the query analyzer lands: strict xfail turns an unexpected pass into a failure so the
marker cannot be forgotten.
"""
import pytest

from app.storage import Store
from scripts.trace_query import trace


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "trace.db")


def _fate(result, raw):
    return next(w["fate"] for w in result["words"] if w["raw"] == raw)


def test_ban_collision_is_the_cause_of_empty_terms(store):
    # "bàn" (desk) and "bạn" (you) are both "ban" once diacritics are removed, and "ban" is a stopword.
    result = trace(store, "Có bàn gì?")
    assert _fate(result, "bàn") == "dropped: stopword"
    assert result["terms"] == []
    assert result["found"] == []
    assert "no query terms left" in result["stage"]


def test_filler_word_leaves_a_term_that_matches_nothing(store):
    result = trace(store, "Có bàn nào vậy?")
    assert result["terms"] == ["vay"]
    assert result["found"] == []
    assert "no document passed" in result["stage"]


def test_specific_question_only_works_because_of_other_terms(store):
    result = trace(store, "Bàn Oak 120 kích thước bao nhiêu?")
    assert _fate(result, "bàn") == "dropped: stopword"      # the word "bàn" contributes nothing even here
    assert "oak" in result["terms"] and "PRD-101" in result["found"]


@pytest.mark.xfail(strict=True, reason="Phase 3: 'bàn' is dropped as the pronoun 'bạn' (desired: desk documents found)")
@pytest.mark.parametrize("question", ["Có bàn gì?", "Có bàn nào vậy?"])
def test_desk_discovery_should_find_desk_documents(store, question):
    found = trace(store, question)["found"]
    assert {"PRD-101", "PRD-103"} & set(found)
