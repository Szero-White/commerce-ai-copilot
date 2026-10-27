"""Follow-up questions: resolved only when unambiguous, otherwise a question back. Offline, LLM off."""
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.query import Lexicon, analyze
from app.storage import SYNONYMS, Store


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(data_path=tmp_path / "chat.db", settings=Settings(
        data_path=tmp_path / "chat.db", llm_provider="off", embedding_provider="off")))


def ask(client, question, context=None):
    body = {"question": question}
    if context is not None:
        body["turn_context"] = context
    response = client.post("/api/chat", json=body)
    assert response.status_code == 200, response.text
    return response.json()


def ids(result):
    return [s["id"] for s in result["sources"]]


# ---- what counts as a pointer ----------------------------------------------------------------------------------------
LEX = Lexicon(["Bàn Oak giá 1.890.000 VND, bảo hành 12 tháng", "Ghế Flex"], known=SYNONYMS, titles=["Bàn Oak", "Ghế Flex"])


@pytest.mark.parametrize("question,pointer", [
    ("Nó cao bao nhiêu?", ("pronoun", None)), ("Cái này giá bao nhiêu?", ("pronoun", None)),
    ("Sản phẩm đó bảo hành thế nào?", ("pronoun", None)), ("How much is it?", ("pronoun", None)),
    ("Cái thứ hai giá bao nhiêu?", ("ordinal", 2)), ("Mẫu thứ ba giá bao nhiêu?", ("ordinal", 3)),
    ("Cái đầu tiên bảo hành bao lâu?", ("ordinal", 1)), ("Cái cuối cùng giá sao?", ("ordinal", -1)),
    ("What is the price of the second one?", ("ordinal", 2)),
])
def test_pointers_are_recognised(question, pointer):
    a = analyze(question, LEX)
    assert a.pointer == pointer and a.needs_referent


@pytest.mark.parametrize("question", [
    "Giao hàng thứ hai được không?",              # Monday, not "the second one"
    "Cho tôi mã giảm giá cho đơn đầu tiên",       # the first order, not the first product
    "Bàn Oak cái này giá bao nhiêu?",             # names its own subject
])
def test_questions_that_only_look_like_pointers_are_standalone(question):
    assert not analyze(question, LEX).needs_referent


# ---- resolution through the API --------------------------------------------------------------------------------------
def test_a_pronoun_after_a_single_result_is_bound_to_that_document(client):
    first = ask(client, "Ghế Flex giá bao nhiêu?")
    assert ids(first) == ["PRD-102"] and first["turn_context"] == {"ids": ["PRD-102"], "kind": "single"}
    follow = ask(client, "Nó bảo hành thế nào?", first["turn_context"])
    assert ids(follow) == ["PRD-102"] and "Bảo hành 12 tháng" in follow["answer"]
    assert "Ghế văn phòng Flex" in follow["answer"].splitlines()[0]          # says what it understood
    assert follow["turn_context"] == {"ids": ["PRD-102"], "kind": "single"}


def test_an_ordinal_follows_the_order_of_the_sources_panel(client):
    listing = ask(client, "Cho mình xem các sản phẩm đang bán")
    assert listing["turn_context"]["kind"] == "list" and len(listing["turn_context"]["ids"]) >= 2
    assert listing["answer"].count("\n1. [") == 1 and "\n2. [" in listing["answer"]          # numbered like the panel
    second = ask(client, "Cái thứ hai giá bao nhiêu?", listing["turn_context"])
    assert ids(second) == [listing["turn_context"]["ids"][1]] and second["mode"] != "needs_clarification"
    last = ask(client, "Cái cuối cùng giá bao nhiêu?", listing["turn_context"])
    assert ids(last) == [listing["turn_context"]["ids"][-1]]


def test_an_ambiguous_pointer_is_a_question_back_not_a_guess(client):
    listing = ask(client, "Cho mình xem các sản phẩm đang bán")
    answer = ask(client, "Nó giá bao nhiêu?", listing["turn_context"])
    assert answer["mode"] == "needs_clarification" and answer["sources"] == []
    assert "1. " in answer["answer"] and answer["turn_context"]["kind"] == "clarify"
    # ... and the numbered options can be answered with an ordinal
    picked = ask(client, "Cái thứ hai giá bao nhiêu?", answer["turn_context"])
    assert ids(picked) == [answer["turn_context"]["ids"][1]]


def test_no_context_means_asking(client):
    for question in ("Nó cao bao nhiêu?", "Cái thứ hai giá bao nhiêu?"):
        result = ask(client, question)
        assert result["mode"] == "needs_clarification" and result["sources"] == []
        assert result["turn_context"] == {"ids": [], "kind": "none"}


def test_an_ordinal_needs_a_list_and_a_pronoun_needs_exactly_one_document(client):
    single = {"ids": ["PRD-101"], "kind": "single"}
    assert ask(client, "Cái thứ hai giá bao nhiêu?", single)["mode"] == "needs_clarification"
    assert ask(client, "Cái thứ hai giá bao nhiêu?", {"ids": ["PRD-101", "PRD-102"], "kind": "single"})["mode"] == "needs_clarification"
    assert ask(client, "Cái thứ năm giá bao nhiêu?", {"ids": ["PRD-101", "PRD-102"], "kind": "list"})["mode"] != "x"


def test_context_ids_are_untrusted(client):
    forged = {"ids": ["NOPE-1", "../../etc/passwd"], "kind": "single"}
    assert ask(client, "Nó giá bao nhiêu?", forged)["mode"] == "needs_clarification"
    # a real id is a public catalogue document, but the text still comes from the database, never from the client
    result = ask(client, "Nó có màu gì?", {"ids": ["PRD-101", "NOPE-1"], "kind": "list"})
    assert ids(result) == ["PRD-101"]
    too_many = {"ids": [f"D{i}" for i in range(6)], "kind": "list"}
    assert client.post("/api/chat", json={"question": "Nó giá bao nhiêu?", "turn_context": too_many}).status_code == 422
    assert client.post("/api/chat", json={"question": "Nó giá bao nhiêu?", "turn_context": {"ids": [], "kind": "x"}}).status_code == 422


def test_a_question_that_names_its_subject_ignores_the_context(client):
    context = {"ids": ["PRD-103"], "kind": "single"}
    with_context = ask(client, "Ghế Flex giá bao nhiêu?", context)
    without = ask(client, "Ghế Flex giá bao nhiêu?")
    assert ids(with_context) == ids(without) == ["PRD-102"] and with_context["answer"] == without["answer"]


def test_a_follow_up_the_document_cannot_answer_says_so_and_keeps_the_subject(client):
    first = ask(client, "Tủ hồ sơ Slim giá bao nhiêu?")
    follow = ask(client, "Nó có khóa không?", first["turn_context"])
    assert follow["mode"] == "no_evidence" and follow["sources"] == []
    assert "Tủ hồ sơ Slim" in follow["answer"]                      # states which product it assumed
    assert follow["turn_context"] == {"ids": ["PRD-104"], "kind": "single"}


def test_requests_without_context_keep_the_old_contract(client):
    result = ask(client, "Bàn Oak 120 kích thước bao nhiêu?")
    assert ids(result) == ["PRD-101"] and result["mode"] == "extractive_demo"
    assert {"answer", "mode", "retrieval_mode", "sources", "latency_ms", "tokens_in", "tokens_out",
            "citation_ids_checked", "grounding_note", "token_note"} <= set(result)
