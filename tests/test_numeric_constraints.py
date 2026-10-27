"""Numbers in questions: exact values, units and comparisons are decided by code from the documents' own numbers."""
import pytest

from app.quantities import evaluate, exact_matches, extract, parse_conditions, parse_number
from app.query import Lexicon, analyze
from app.storage import SYNONYMS, Store


@pytest.mark.parametrize("text,value", [("1.890.000", 1890000), ("390,000", 390000), ("18.00", 18.0), ("1,5", 1.5), ("120", 120)])
def test_numbers_use_vietnamese_and_english_separators(text, value):
    assert parse_number(text) == value


def kinds(text):
    return [(q.family, q.unit, q.value) for q in extract(text)]


def test_quantities_carry_their_unit_family_and_base_value():
    assert kinds("Giá niêm yết giả lập 1.890.000 VND") == [("money", "vnd", 1890000)]
    assert kinds("dưới 2 triệu hoặc 500k hay 300 nghìn") == [("money", "vnd", 2e6), ("money", "vnd", 5e5), ("money", "vnd", 3e5)]
    assert kinds("Price: example USD 18.00, not real") == [("money", "usd", 18.0)]
    assert kinds("11oz, 7 ngày, 12 tháng, 5%") == [("volume", "oz", 11), ("time", "day", 7), ("time", "month", 12), ("percent", "%", 5)]
    assert kinds("mặt bàn 120 x 60 cm") == [("length", "cm", 120), ("length", "cm", 60)]
    assert all(q.in_dimensions for q in extract("80 x 40 x 160 cm"))


def test_numbers_without_a_unit_are_not_quantities():
    assert kinds("nguồn USB-C 5V, ba mức sáng, mã 120, 5 mức") == []


def test_comparison_phrases_become_conditions_and_leave_the_rest_of_the_question():
    for text, op, field, value, attr in [
        ("giá dưới 2 triệu", "<", "hi", 2e6, "gia"), ("đắt hơn 2 triệu", ">", "lo", 2e6, "gia"),
        ("rẻ hơn 500k", "<", "hi", 5e5, "gia"), ("cao hơn 70 cm", ">", "lo", 70, "cao"),
        ("mặt rộng hơn 100cm", ">", "lo", 100, "rong"), ("không quá 500 nghìn", "<=", "hi", 5e5, None),
        ("tối thiểu 3 tháng", ">=", "lo", 3, None), ("under 20 USD", "<", "hi", 20, None),
    ]:
        conditions, cleaned = parse_conditions("Có " + text + " không?")
        assert len(conditions) == 1, text
        c = conditions[0]
        assert (c.op, getattr(c, field), c.attr) == (op, value, attr), text
        assert text.split()[-1] not in cleaned and "Có" in cleaned and "không" in cleaned


def test_a_range_is_one_condition():
    (c,), cleaned = parse_conditions("giá từ 500k đến 1 triệu")
    assert (c.op, c.lo, c.hi) == ("between", 5e5, 1e6) and "triệu" not in cleaned


def test_exact_quantities_need_the_same_value_and_the_same_unit_family():
    assert exact_matches(extract("giảm 5%"), "Giảm 5% cho đơn đầu tiên")
    assert not exact_matches(extract("giảm 5%"), "nguồn USB-C 5V")                 # 5 is there, but not 5 percent
    assert exact_matches(extract("trong 7 ngày"), "đổi trả trong 7 ngày kể từ ngày nhận")
    assert not exact_matches(extract("trong 7 ngày"), "bảo hành 7 tháng")
    assert exact_matches(extract("giá 390.000 đồng"), "Giá niêm yết 390.000 VND")
    assert not exact_matches(extract("giá 18 usd"), "Giá 18.000 VND")


DESK = "Bàn Oak: mặt bàn 120 x 60 cm, chiều cao 75 cm. Giá niêm yết giả lập 1.890.000 VND."
SHELF = "Kệ: cao 180 cm, rộng 60 cm. Giá niêm yết 2.350.000 VND."
IMPORTED = "Mug 11oz. Price: example USD 18.00."


def cond(text):
    return parse_conditions(text)[0][0]


@pytest.mark.parametrize("question,doc,expected", [
    ("dưới 2 triệu", DESK, "yes"), ("trên 2 triệu", DESK, "no"), ("đắt hơn 2 triệu", SHELF, "yes"),
    ("dưới 500 nghìn", IMPORTED, "unknown"),          # only a USD price: cannot be compared with VND
    ("dưới 2 triệu", "Không có giá ở đây", "no"),      # nothing to show for this question
    ("cao hơn 70 cm", DESK, "yes"), ("cao hơn 80 cm", DESK, "no"),
    ("rộng hơn 100 cm", DESK, "unknown"),             # "120 x 60 cm" does not say which side is the width
    ("cao hơn 150 cm", SHELF, "yes"), ("rộng hơn 50 cm", SHELF, "yes"), ("rộng hơn 80 cm", SHELF, "no"),
    ("dài hơn 10 cm", SHELF, "unknown"),
    ("từ 1 triệu đến 2 triệu", DESK, "yes"), ("từ 100k đến 500k", DESK, "no"),
])
def test_conditions_are_computed_from_the_documents_numbers(question, doc, expected):
    assert evaluate(cond(question), doc) == expected


# ---- through the search -------------------------------------------------------------------------------------------
@pytest.fixture()
def shop(tmp_path):
    store = Store(tmp_path / "shop.db")
    store.apply([
        {"id": "S-1", "title": "Ghế Alba - mã ALBA1", "category": "product", "content": "Ghế Alba mã ALBA1. Giá niêm yết 450.000 VND. Cao 90 cm."},
        {"id": "S-2", "title": "Ghế Borea - mã BOR2", "category": "product", "content": "Ghế Borea mã BOR2. Giá niêm yết 1.500.000 VND. Cao 110 cm."},
        {"id": "S-3", "title": "Ghế Cirro - mã CIR3", "category": "product", "content": "Ghế Cirro mã CIR3. Giá niêm yết 3.200.000 VND. Cao 100 cm."},
        {"id": "S-4", "title": "Imported chair Dune", "category": "product", "content": "Imported chair Dune. Price: example USD 40.00."},
    ], source="shop")
    store.delete_source("seed")      # only the invented catalogue, so nothing else can match
    return store


def found(store, question):
    info = {}
    docs = store.fts_search(question, limit=10, trace=info)
    return [(d["id"], d.get("condition_status")) for d in docs], info


def test_price_conditions_list_only_products_that_satisfy_them(shop):
    docs, _ = found(shop, "Có món nào dưới 2 triệu không?")
    ids = [i for i, _ in docs]
    assert ids[:2] == ["S-1", "S-2"] and "S-3" not in ids
    assert dict(docs)["S-1"] == "satisfied"
    assert ("S-4", "unverified") in docs and ids.index("S-4") > ids.index("S-2")   # USD price: shown last, flagged


def test_a_condition_with_a_product_word_searches_first_and_then_filters(shop):
    docs, _ = found(shop, "Ghế nào cao hơn 105 cm?")
    assert docs == [("S-2", "satisfied")]
    docs, _ = found(shop, "ghe nao giá đắt hơn 3 triệu")
    assert [i for i, _ in docs] == ["S-3"]


def test_nothing_is_returned_when_every_document_fails_the_condition(shop):
    assert found(shop, "Ghế nào cao hơn 500 cm?")[0] == []
    _, info = found(shop, "Ghế nào cao hơn 500 cm?")
    assert info["gate_rejected"]


def test_codes_and_names_must_match_exactly(shop):
    assert found(shop, "Ghế Alba mã ALBA1 giá bao nhiêu?")[0][0][0] == "S-1"
    assert found(shop, "Ghế Alba mã ALBA2 giá bao nhiêu?")[0] == []               # code not in the document
    assert found(shop, "Ghế Zephyr có không?")[0] == []                              # a capitalised word nobody has seen
    assert found(shop, "Có ghế Alba Pro không?")[0] == []                             # "Pro" is not part of the product


def test_a_percentage_is_not_satisfied_by_another_number_5(tmp_path):
    store = Store(tmp_path / "p.db")
    store.upsert({"id": "L-1", "title": "Đèn Lumen", "category": "product", "content": "Đèn Lumen nguồn USB-C 5V, giá 390.000 VND."})
    assert found(store, "Đèn Lumen nguồn 5V")[0][0][0] == "L-1"
    assert found(store, "Đèn Lumen giảm 5% không?")[0] == []


def test_pointer_words_without_a_subject_do_not_search(shop):
    for q in ("Cái đó giá bao nhiêu?", "Nó bảo hành thế nào?", "Cái thứ hai thì sao?"):
        docs, info = found(shop, q)
        assert docs == [] and info["needs_referent"], q
    assert found(shop, "Ghế Alba cái đó giá bao nhiêu?")[0][0][0] == "S-1"        # a subject is named: search as usual


def test_analysis_separates_conditions_quantities_and_names():
    lex = Lexicon(["Ghế Alba mã ALBA1 giá 450.000 VND"], known=SYNONYMS)
    a = analyze("Ghế Alba Pro dưới 2 triệu bảo hành 12 tháng", lex)
    assert [c.op for c in a.conditions] == ["<"] and [q.unit for q in a.quantities] == ["month"]
    assert a.names == ["pro"] and "2" not in a.terms and "trieu" not in a.terms
