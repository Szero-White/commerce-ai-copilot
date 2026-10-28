"""Multi-turn conversations over synthetic documents (not the demo catalogue): the topic is kept when the reference is clear,
a question is asked back when it is not, a newly named subject switches topic, and the answer guard's reasons are visible.
Offline; the LLM is a test double, so nothing here shows how a live model words its answers."""
import pytest

import app.services as services
from app.config import Settings
from app.documents import parse_upload
from app.evidence import answer_problems
from app.storage import Store
from tests.test_document_ingestion import make_pdf

DOCS = [
    {"id": "U-1", "title": "Tiếp nhận hàng lỗi", "category": "policy",
     "content": "Hàng nứt vỡ khi nhận cần báo trong 48 giờ kèm ảnh bao bì. Đổi trả trong 7 ngày nếu sản phẩm chưa sử dụng."},
    {"id": "U-2", "title": "Mã ưu đãi SPRING5", "category": "policy",
     "content": "Mã SPRING5 giảm 5% cho đơn từ 300.000 đồng, tối đa 40.000 đồng. Mỗi đơn chỉ dùng một mã."},
    {"id": "U-3", "title": "Tủ giày Birch", "category": "product", "content": "Tủ giày Birch 3 ngăn, tải trọng tối đa 30 kg. Bảo hành 12 tháng."},
    {"id": "U-4", "title": "Bàn học Willow", "category": "product", "content": "Bàn học Willow rộng 100 cm. Bảo hành 24 tháng."},
    {"id": "U-5", "title": "Bảo hành Tủ giày Birch", "category": "policy",
     "content": "Tủ giày Birch bảo hành 12 tháng cho lỗi sản xuất; không bảo hành nếu tự ý sửa chữa."},
    {"id": "U-6", "title": "Phí vận chuyển", "category": "policy", "content": "Phí vận chuyển nội thành 30.000 đồng, giao trong 2 ngày."},
]


@pytest.fixture()
def shop(tmp_path):
    store = Store(tmp_path / "talk.db")
    for d in store.documents():
        store.delete(d["id"])
    store.apply([{**d, "source": "talk"} for d in DOCS], source="talk")
    return store, Settings(data_path=tmp_path / "talk.db", llm_provider="off", embedding_provider="off")


def converse(shop, *questions):
    """Ask in order, carrying turn_context like the browser does; returns every result."""
    store, settings = shop
    context, results = None, []
    for q in questions:
        results.append(services.question_answer(store, settings, q, context))
        context = results[-1]["turn_context"]
    return results


def ids(result):
    return [s["id"] for s in result["sources"]]


# ---- the two observed live failures, as general conversation behaviour -----------------------------------------------------
def test_a_bare_aspect_after_a_topic_stays_on_that_topic_and_a_named_code_switches_it(shop):
    first, aspect, switched, aspect2 = converse(
        shop, "Hàng nứt vỡ khi nhận phải báo trong bao lâu?", "Có điều kiện gì không?",
        "Còn mã SPRING5 thì sao?", "Điều kiện liên quan là gì?")
    assert ids(first) == ["U-1"]
    assert ids(aspect) == ["U-1"]                      # not the discount policy, not a warranty that happens to say "điều kiện"
    assert ids(switched) == ["U-2"]                    # a new code is a new subject
    assert ids(aspect2) == ["U-2"]                     # and the next bare aspect follows the NEW subject


def test_a_bare_aspect_without_any_earlier_turn_is_asked_back_not_guessed(shop):
    [r] = converse(shop, "Có điều kiện gì không?")
    assert r["mode"] == "needs_clarification" and r["sources"] == []


def test_a_bare_aspect_after_two_different_things_is_asked_back(shop):
    store, settings = shop
    ctx = {"ids": ["U-3", "U-4"], "kind": "list"}
    r = services.question_answer(store, settings, "Có điều kiện gì không?", ctx)
    assert r["mode"] == "needs_clarification" and r["sources"] == []
    assert "Tủ giày Birch" in r["answer"] and "Bàn học Willow" in r["answer"]


def test_a_follow_up_with_nothing_in_the_topic_is_a_refusal_not_a_jump(shop):
    first, follow = converse(shop, "Hàng nứt vỡ khi nhận phải báo trong bao lâu?", "Còn phí vận chuyển thì sao?")
    assert ids(follow) == [] and follow["mode"] == "no_evidence"      # U-6 states a shipping fee, but it is another topic


def test_naming_a_new_product_switches_topic(shop):
    first, follow, again = converse(shop, "Tủ giày Birch bảo hành bao lâu?", "Còn bàn học Willow thì sao?",
                                    "Nó rộng bao nhiêu?")
    assert "U-4" in ids(follow) and "U-3" not in ids(follow)
    assert ids(again) == ["U-4"] and "100 cm" in again["answer"]       # "nó" binds to the NEW single result


def test_standalone_questions_with_their_own_subject_do_not_use_the_context(shop):
    first, own = converse(shop, "Tủ giày Birch bảo hành bao lâu?", "Điều kiện đổi trả hàng lỗi là gì?")
    assert ids(own) == ["U-1"]


def test_the_shared_label_of_a_corpus_is_not_a_named_thing(tmp_path):
    store = Store(tmp_path / "label.db")
    for d in store.documents():
        store.delete(d["id"])
    names = ["Aria", "Bora", "Cora", "Dora", "Eira"]
    docs = [{"id": f"P-{n}", "title": f"Ghế Demo {n}", "category": "product", "content": f"Ghế Demo {n} bảo hành 12 tháng."}
            for n in names]
    docs.append({"id": "L-1", "title": "Đổi trả", "category": "policy", "content": "Chính sách Demo: đổi trả trong 7 ngày."})
    store.apply([{**d, "source": "x"} for d in docs], source="x")
    assert store.entity_scope(["L-1"]) == ["L-1"]                      # not widened to every document that says "Demo"
    assert store.entity_scope(["P-Aria"]) == ["P-Aria"]


# ---- the answer guard: why a correct answer was refused, and what is still refused ----------------------------------------
def llm_replies(monkeypatch, *replies):
    queue = list(replies)
    monkeypatch.setattr(services, "llm_enabled", lambda s: True)
    monkeypatch.setattr(services, "ollama_chat", lambda *a, **k: (queue.pop(0), 50, 20))


def test_a_citation_error_is_rejected_and_its_reason_is_returned(shop, monkeypatch):
    llm_replies(monkeypatch, "Phải báo trong 72 giờ [U-1].", "Phải báo trong 48 giờ [U-9].", "Phải báo trong 48 giờ [U-1].")
    wrong_number, unknown_id, good = converse(shop, *["Hàng nứt vỡ khi nhận phải báo trong bao lâu?"] * 3)
    assert wrong_number["mode"] == "llm_citation_rejected_extractive" and "72" in wrong_number["answer_check"]["reason"] or \
        "['72']" in wrong_number["answer_check"]["reason"]
    assert "72" in wrong_number["answer_check"]["reply_excerpt"] and wrong_number["verification"] is None
    assert unknown_id["mode"] == "llm_citation_rejected_extractive" and "U-9" in unknown_id["answer_check"]["reason"]
    assert good["mode"] == "llm_rag_cited" and good["answer_check"]["reason"] == "ok"


def test_a_follow_up_answer_from_the_topic_documents_is_accepted(shop, monkeypatch):
    llm_replies(monkeypatch, "Báo trong 48 giờ [U-1].", "Có thể đổi trả trong 7 ngày [U-1].")
    first, follow = converse(shop, "Hàng nứt vỡ khi nhận phải báo trong bao lâu?", "Có điều kiện gì không?")
    assert follow["mode"] == "llm_rag_cited" and ids(follow) == ["U-1"]


def test_a_negation_inside_a_condition_does_not_make_the_policy_look_negated():
    source = [{"id": "U-1", "title": "t", "content": DOCS[0]["content"]}]
    assert not answer_problems("Khách có thể đổi trả trong 7 ngày [U-1].", source)


def test_a_negated_policy_is_still_caught_and_so_is_a_negation_before_the_condition():
    banned = [{"id": "P", "title": "t", "content": "Không đổi trả hàng khuyến mãi."}]
    assert answer_problems("Bạn được đổi trả hàng khuyến mãi [P].", banned)
    conditional = [{"id": "P", "title": "t", "content": "Không đổi trả nếu hàng đã sử dụng."}]
    assert answer_problems("Bạn được đổi trả [P].", conditional)


def test_a_page_header_with_a_negation_is_a_separate_item_not_part_of_the_next_sentence():
    source = [{"id": "P", "title": "t", "content": "KHÔNG PHẢI CHÍNH SÁCH THẬT • Đổi trả trong 7 ngày kể từ khi nhận"}]
    assert not answer_problems("Được đổi trả trong 7 ngày [P].", source)


# ---- running headers in PDFs --------------------------------------------------------------------------------------------
HEADER = "SYNTHETIC DATASET - NOT A REAL POLICY"


def pdf_chunks(pages, tmp_path):
    settings = Settings(data_path=tmp_path / "p.db", llm_provider="off", embedding_provider="off")
    return " ".join(d["content"] for d in parse_upload("spec.pdf", make_pdf(pages), settings)["documents"])


def test_a_header_repeated_on_most_pages_is_not_part_of_the_chunks(tmp_path):
    pages = [[HEADER, f"Section {i} states that item {i} ships in {i + 1} days."] for i in range(1, 6)]
    text = pdf_chunks(pages, tmp_path)
    assert "SYNTHETIC" not in text and "item 3 ships in 4 days" in text


def test_short_documents_and_headings_used_twice_keep_their_lines(tmp_path):
    assert "SYNTHETIC" in pdf_chunks([[HEADER, "Item one ships in two days."] for _ in range(3)], tmp_path)
    pages = [["Warranty terms", "Item one has a warranty of 12 months."], ["Item two has a warranty of 6 months."],
             ["Warranty terms", "Item three has a warranty of 3 months."], ["Item four has a warranty of 1 month."]]
    assert "Warranty terms" in pdf_chunks(pages, tmp_path)
