"""General fixes made after an independent diagnostic trial. Invented data: none of it comes from the trial files."""
import pytest

from app.query import Lexicon, analyze
from app.quantities import cut_scenario_amounts, evaluate, extract, parse_conditions
from app.storage import SYNONYMS, Store


@pytest.fixture()
def shop(tmp_path):
    s = Store(tmp_path / "t.db")
    s.delete_source("seed")
    s.apply([
        {"id": "P1", "title": "Tủ hồ sơ Harbor H6", "category": "product",
         "content": "Tủ hồ sơ Harbor H6 gồm bốn ngăn kéo. Cao 120 cm, rộng 46 cm. Giá 1.450.000 VND. Bảo hành 12 tháng."},
        {"id": "P2", "title": "Bàn nâng hạ Motora M7", "category": "product",
         "content": "Bàn Motora M7 nâng hạ bằng điện, chiều cao điều chỉnh trong khoảng 72–118 cm. Giá 6.750.000 VND."},
        {"id": "L1", "title": "Dịch vụ lắp đặt", "category": "policy",
         "content": "Đơn từ 3.000.000 VND được lắp đặt miễn phí. Đơn dưới mức đó thu phí lắp 120.000 VND."},
    ], source="t")
    return s


def found(store, q):
    return [(d["id"], d.get("condition_status")) for d in store.fts_search(q, limit=5)]


def test_a_wrong_number_for_a_named_product_returns_it_flagged_so_the_real_figure_shows(shop):
    assert found(shop, "Tủ Harbor H6 có 8 ngăn chứ?") == [("P1", "premise_mismatch")]
    assert found(shop, "Bàn Motora M7 giá 5 triệu đúng không?") == [("P2", "premise_mismatch")]
    assert found(shop, "Tủ Harbor H6 có bốn ngăn không?") == [("P1", None)]          # a true premise is not flagged


def test_a_wrong_number_is_still_refused_without_a_named_thing_or_for_codes_and_discounts(shop):
    assert found(shop, "Tủ Harbor H7 có bốn ngăn không?") == []                       # another model code
    assert found(shop, "Tủ Harbor H6 giảm 5% không?") == []                           # a percentage / offer
    assert found(shop, "Có cái nào 8 ngăn không?") == []                              # no named thing to correct


def test_order_size_in_a_question_is_a_scenario_not_a_claim(shop):
    assert cut_scenario_amounts("Lắp kệ cho đơn 2 triệu hết bao nhiêu?").count("2") == 0
    assert "2" in cut_scenario_amounts("Ghế này giá 2 triệu đúng không?")            # a price claim stays
    assert found(shop, "Đơn 2 triệu có phải trả phí lắp đặt không?")[0][0] == "L1"


def test_request_frames_and_chat_abbreviations_are_not_content(shop):
    assert found(shop, "Tủ Harbor H6 giá niêm yết bao nhiêu?")[0][0] == "P1"
    assert found(shop, "tu harbor h6 co bon ngan ko")[0][0] == "P1"                   # "ko" = không


def test_a_short_misspelt_brand_is_repaired_but_an_ordinary_word_is_not(shop):
    lex = shop._corpus()["lexicon"]
    assert analyze("ban mota m7", lex).corrections == {"mota": "motora"}
    assert analyze("giá vàng", Lexicon(["Văn phòng Vận chuyển"], known=SYNONYMS, titles=["Ghế Văn phòng Flex"])).corrections == {}


def test_a_range_in_a_document_is_compared_and_a_straddling_one_is_unverified():
    doc = "chiều cao điều chỉnh trong khoảng 72–118 cm"
    assert [q.value for q in extract(doc)] == [72, 118]
    (cond,), _ = parse_conditions("cao hơn 100 cm")
    assert evaluate(cond, doc) == "unknown"                                          # 72 fails, 118 passes
    (low,), _ = parse_conditions("cao hơn 50 cm")
    assert evaluate(low, doc) == "yes"
    (cheap,), _ = parse_conditions("giá thấp hơn 1,2 triệu")
    assert cheap.op == "<" and cheap.hi == 1_200_000 and extract("chạy 9 tiếng")[0].unit == "hour"
