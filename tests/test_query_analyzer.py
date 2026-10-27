"""Query analyzer: word roles come from the indexed documents, never from product names or sample questions.

These tests use small invented catalogues so they cannot pass by remembering the seed data.
"""
import pytest

from app.query import Lexicon, analyze, states_stock
from app.storage import SYNONYMS, Store


def lex(*texts):
    return Lexicon(texts, known=SYNONYMS)


def terms(query, *texts):
    a = analyze(query, lex(*texts))
    return a.terms, a.soft


DESK = ("Bàn học gỗ thông cho học sinh, mặt bàn rộng", "Ghế gaming có tựa đầu")
NO_DESK = ("Ghế gaming có tựa đầu", "Kệ sách gỗ")


def test_typed_diacritics_decide_between_desk_you_and_sell():
    assert terms("Có bàn nào?", *DESK)[0] == ["ban"]
    assert terms("Bạn có bán ghế không?", *DESK)[0] == ["ghe"]


def test_plain_spelling_is_only_content_when_the_documents_use_that_word():
    assert terms("co ban nao khong", *DESK)[0] == ["ban"]            # alone and attested: promoted
    assert terms("ban co ghe khong", *DESK) == (["ghe"], ["ban"])    # attested but not required
    assert terms("ban co ghe khong", *NO_DESK) == (["ghe"], [])      # catalogue has no such word: just "you"


def test_other_homographs_follow_the_same_rule():
    machines = ("Máy in laser đen trắng", "Da bò thật")
    assert "may" in terms("Máy in giá bao nhiêu?", *machines)[0]      # "máy" is not the function word "mấy"
    assert "da" in sum(terms("bọc da bò", *machines), [])             # leather, typed "da": searched, not required
    assert "da" not in sum(terms("đã giao chưa", *machines), [])      # "đã" is the function word


def test_english_function_words_stay_function_words():
    a = analyze("What sizes are available for the hoodie?", lex("Hoodie sizes S M L; the print is custom"))
    assert "the" not in a.terms and "the" not in a.soft and "hoodie" in a.terms


def test_typo_repair_uses_the_vocabulary_and_only_swaps_or_slips():
    corpus = ("Bảo hành 12 tháng cho ghế văn phòng", "Đèn LED bàn")
    assert analyze("bảo hnàh", lex(*corpus)).corrections == {"hnàh": "hanh"}   # swapped letters
    assert analyze("khuyến mãi", lex("Chuyển khoản ngân hàng")).corrections == {}  # a different word, not a typo
    assert analyze("vàng", lex("Vận chuyển nhanh")).corrections == {}               # short words are not guessed
    assert analyze("ship nhanh", lex("Cửa hàng shop nhỏ")).corrections == {}        # known domain word is untouched


def test_typo_repair_is_capped_and_refuses_ties():
    corpus = ("Ghế văn phòng", "Giá bán")
    assert analyze("gehz vanw phogn", lex(*corpus)).corrections.keys() <= {"gehz", "vanw", "phogn"}
    assert len(analyze("xyzq qxzy zxqy", lex(*corpus)).corrections) <= 2
    assert analyze("mua", lex("mud", "mup")).corrections == {}   # two equally close words: do not guess


def test_stock_questions_need_a_stored_figure():
    assert analyze("Ghế này còn hàng không?", lex("Ghế")).asks_stock
    assert analyze("Which sizes are available?", lex("sizes")).asks_stock is False
    assert states_stock("ton kho 12 chiec".split()) and not states_stock("khong cam ket ton kho".split())


@pytest.fixture()
def shop(tmp_path):
    store = Store(tmp_path / "x.db")
    store.upsert({"id": "K-1", "title": "Kệ sách Linen K5", "category": "product",
                  "content": "Kệ sách Linen K5 năm tầng, khung thép, giá 1.200.000 VND. Tồn kho: 14 chiếc."})
    return store


def ids(store, q):
    return [d["id"] for d in store.fts_search(q, limit=5)]


def test_new_documents_are_found_without_changing_any_code(shop):
    assert ids(shop, "Có kệ nào không ạ?")[:1] == ["K-1"]
    assert ids(shop, "ke sach linen k5 gia bao nhieu")[:1] == ["K-1"]
    assert ids(shop, "Kệ sách Linen K5 còn hàng không?")[:1] == ["K-1"]   # this document states a stock figure


def test_stock_question_is_refused_when_no_document_states_a_figure(tmp_path):
    store = Store(tmp_path / "y.db")
    store.upsert({"id": "K-2", "title": "Kệ sách Oslo", "category": "product", "content": "Kệ sách Oslo ba tầng, khung gỗ."})
    assert ids(store, "Kệ sách Oslo còn hàng không?") == []
    assert ids(store, "Kệ sách Oslo có mấy tầng?")[:1] == ["K-2"]


def test_request_frames_are_not_content_words(shop):
    # Post-evaluation fix (found by the fresh data, see reports/PHASE_LOG.md): "what are its features?" names no feature.
    assert ids(shop, "Kệ sách Linen K5 có đặc điểm gì?")[:1] == ["K-1"]
    assert ids(shop, "cho tôi thông tin chi tiết về kệ sách Linen K5")[:1] == ["K-1"]
    assert terms("đặc điểm gì?", "Kệ sách")[0] == []


def test_a_bare_csv_price_is_read_as_vnd_so_price_comparisons_work(tmp_path):
    from scripts.ingest import ingest_file
    store = Store(tmp_path / "p.db")
    store.delete_source("seed")
    path = tmp_path / "shop.csv"
    path.write_text("sku,name,price,description\nA-1,Đèn cây Alto,780000,Đèn cây ánh sáng ấm\nB-2,Ghế Brio,2.500.000 VND,Ghế gỗ\n", encoding="utf-8")
    ingest_file(store, path)
    assert "780000 VND" in store.documents()[0]["content"] + store.documents()[1]["content"]
    assert [d["id"] for d in store.fts_search("Có món nào giá dưới 1 triệu không?")] == [d["id"] for d in store.documents() if "Alto" in d["title"]]


def test_catalogue_question_lists_products_only_when_no_content_word_remains(shop):
    listed = ids(shop, "Cho mình xem các sản phẩm đang bán")
    assert "K-1" in listed and all(shop.document(i)["category"] == "product" for i in listed)
    assert ids(shop, "Sản phẩm quasar neutrino") == []
