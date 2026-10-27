"""Facts a catalogue of descriptions does not hold unless a document states them: stock, offers, private data / actions.

Found by the B1 diagnosis: a question like "does chair X have a discount?" is semantically very close to chair X's document,
so a meaning-based match would admit it. The constraint must therefore sit in the gate, independent of how a document was found.
"""
import pytest

from app.gate import check_document
from app.query import Lexicon, analyze, states_offer
from app.storage import SYNONYMS, Store

LEX = Lexicon(["Ghế Lumi bảo hành 12 tháng"], known=SYNONYMS)


def flags(question):
    a = analyze(question, LEX)
    return a.asks_stock, a.asks_offer, a.asks_private


@pytest.mark.parametrize("question,expected", [
    ("Ghế Lumi còn hàng không?", (True, False, False)),
    ("Ghế Lumi có sẵn trong kho không?", (True, False, False)),
    ("Bao giờ có hàng mới về?", (True, False, False)),
    ("Hôm nay ghế Lumi có khuyến mãi gì?", (False, True, False)),
    ("Cho tôi mã giảm giá", (False, True, False)),
    ("Is there a discount code?", (False, True, False)),
    ("Mua ghế có được tặng kèm đèn không?", (False, True, False)),
    ("Đơn hàng của tôi đang ở đâu?", (False, False, True)),
    ("Cho tôi số điện thoại của khách hàng", (False, False, True)),
    ("Hoàn tiền cho tôi ngay", (False, False, True)),
    ("What sizes are available for the hoodie?", (False, False, False)),
    ("Ghế Lumi bảo hành bao lâu?", (False, False, False)),
])
def test_questions_are_classified_by_language_cues(question, expected):
    assert flags(question) == expected


def test_a_document_states_an_offer_only_with_a_figure_next_to_a_discount_word():
    assert states_offer("giam 20 cho don dau".split()) and states_offer("voucher 50 000 vnd".split())
    assert not states_offer("khong co giam gia nao duoc phe duyet".split())


@pytest.fixture()
def store(tmp_path):
    s = Store(tmp_path / "c.db")
    s.delete_source("seed")
    s.apply([
        {"id": "P-1", "title": "Ghế Lumi", "category": "product", "content": "Ghế Lumi màu xám, giá niêm yết 900.000 VND."},
        {"id": "P-2", "title": "Ghế Mira", "category": "product", "content": "Ghế Mira màu đen. Ưu đãi giảm 20% cho đơn đầu tiên."},
        {"id": "R-1", "title": "Hỗ trợ đơn hàng", "category": "policy",
         "content": "Muốn biết đơn hàng của tôi đang ở đâu cần xác minh qua kênh chăm sóc khách hàng; chatbot không tra cứu đơn."},
    ], source="t")
    return s


def ids(store, q):
    return [d["id"] for d in store.fts_search(q, limit=5)]


def test_offer_questions_need_a_document_that_states_an_offer(store):
    assert ids(store, "Ghế Lumi có khuyến mãi không?") == []
    assert ids(store, "Ghế Mira có ưu đãi giảm không?") == ["P-2"]        # it states "ưu đãi giảm 20%"


def test_private_data_and_order_actions_are_answered_by_policy_only(store):
    assert ids(store, "Đơn hàng của tôi đang ở đâu?") == ["R-1"]
    assert ids(store, "Ghế Lumi đơn hàng của tôi ở đâu?") == []         # a product description can never answer it


def test_the_same_checks_apply_to_any_candidate(store):
    a = analyze("Ghế Lumi có khuyến mãi không?", store._corpus()["lexicon"])
    assert not check_document(a, "Ghế Lumi màu xám", "ghe lumi mau xam".split(), "product").admitted
    assert check_document(a, "Ghế Lumi giảm 10%", "ghe lumi giam 10".split(), "product").admitted
