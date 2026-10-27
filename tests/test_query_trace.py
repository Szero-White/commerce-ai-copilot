"""Regression tests for the Phase 1 root cause: "bàn" (desk), "bạn" (you) and "bán" (sell) all fold to "ban".

Before the query analyzer these questions were answered with no evidence because "ban" was a stopword; the strict
xfail markers that documented the defect have been removed now that the behaviour is fixed.
"""
import pytest

from app.storage import Store
from scripts.trace_query import trace


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / "trace.db")


def test_typed_with_diacritics_the_reading_decides_the_role(store):
    desk = trace(store, "Có bàn gì?")
    assert desk["terms"] == ["ban"]                 # "bàn" is a content word of this catalogue
    you = trace(store, "Bạn có bán ghế không?")
    assert you["terms"] == ["ghe"]                  # "bạn" and "bán" are function words
    assert "bạn" in you["dropped"] and "bán" in you["dropped"]


def test_plain_spelling_is_ambiguous_and_never_required_when_something_else_is_asked(store):
    mixed = trace(store, "ban co ghe khong")
    assert mixed["terms"] == ["ghe"] and mixed["soft_terms"] == ["ban"]
    alone = trace(store, "co ban nao khong")        # nothing else to search for: the ambiguous word is promoted
    assert alone["terms"] == ["ban"] and alone["soft_terms"] == []


def test_filler_words_are_not_content(store):
    assert trace(store, "Có bàn nào vậy?")["terms"] == ["ban"]


@pytest.mark.parametrize("question", ["Có bàn gì?", "Có bàn nào vậy?", "co ban nao khong", "Shop có bàn không?"])
def test_desk_discovery_finds_the_desk_products_first(store, question):
    found = trace(store, question)["found"]
    assert found[0] in {"PRD-101", "PRD-103"}       # products whose title names the desk come before passing mentions
    assert "PRD-101" in found


def test_a_specific_question_still_uses_its_specific_words(store):
    result = trace(store, "Bàn Oak 120 kích thước bao nhiêu?")
    assert {"ban", "oak", "120"} <= set(result["terms"]) and result["found"][0] == "PRD-101"
