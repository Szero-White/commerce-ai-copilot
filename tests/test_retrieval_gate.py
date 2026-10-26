"""Regression tests for the lexical relevance gate (offline; no embeddings)."""
import pytest

from app.storage import Store


@pytest.fixture()
def store(tmp_path):
    return Store(tmp_path / 'gate.db')


def ids(store, query):
    return [d['id'] for d in store.fts_search(query, limit=3)]


@pytest.mark.parametrize('query', [
    'Hôm nay thời tiết thế nào?', 'bitcoin giá', 'Có khuyến mãi mùa hè không?',
    'Giá vàng hôm nay bao nhiêu?', 'Chính sách bảo hành xe máy thế nào?',
    'Có giảm 5% không?', 'Có voucher 20% cho khách mới không?', 'Có bán sofa không?',
    'Công ty có bao nhiêu nhân viên?', 'What is the weather in Hanoi?',
])
def test_out_of_scope_queries_return_no_documents(store, query):
    assert ids(store, query) == [], query


@pytest.mark.parametrize('query,expected', [
    ('Giao hàng ở thành phố Hồ Chí Minh mất bao lâu?', 'POL-001'),
    ('Bàn Oak 120 kích thước bao nhiêu?', 'PRD-101'),
    ('Sản phẩm lỗi có được đổi trong 7 ngày không?', 'POL-002'),
    ('Hoodie size nào?', 'POD-202'),
    ('Tủ Slim màu gì?', 'PRD-104'),
    ('Ghế lưng lưới Flex giá bao nhiêu?', 'PRD-102'),
])
def test_in_scope_queries_still_found(store, query, expected):
    assert expected in ids(store, query), query


def test_single_digit_number_is_checked_like_any_other_number(store):
    # "7 ngày" exists in POL-002; "5%" exists nowhere.
    assert 'POL-002' in ids(store, 'Đổi trả trong 7 ngày được không?')
    assert ids(store, 'Đổi trả trong 5 ngày được không?') == []


def test_diacritics_typed_by_user_must_match(store):
    # "nhân" (person) must not match "nhận" (receive); an unaccented query stays tolerant.
    assert ids(store, 'Có tuyển dụng nhân viên không?') == []
    assert 'POL-001' in ids(store, 'giao hang tinh khac mat bao lau')


@pytest.mark.parametrize('query', [
    'Bạn có bán điều hòa không?',            # "điều" and "hòa" occur in one policy but far apart
    'Mã giảm giá tháng này là gì?',          # only the sub-phrase "giảm giá" matches
    'Thời gian bảo hành của máy lạnh là bao lâu?',
])
def test_scattered_or_partial_matches_are_not_answers(store, query):
    assert ids(store, query) == [], query


def test_synonyms_let_a_paraphrase_match_without_loosening_the_gate(store):
    # "kích thước" never occurs in the desk record, which states "120 x 60 cm".
    assert 'PRD-101' in ids(store, 'Bàn Oak 120 kích thước bao nhiêu?')


def test_english_inflections_match(store):
    assert 'POD-POL-201' in ids(store, 'Can I return a personalized item because I changed my mind?')
    assert 'POD-202' in ids(store, 'Hoodie size nào?')


def test_cabinet_and_lamp_words_are_not_treated_as_stopwords(store):
    # "tủ" (cabinet) / "đèn" (lamp) share their unaccented form with the function words "từ" / "đến".
    assert 'PRD-104' in ids(store, 'Tủ Slim màu gì?')
    assert 'PRD-103' in ids(store, 'Đèn Focus LED giá bao nhiêu?')


def test_heldout_fixture_floor():
    """Fresh questions written before the logic change; the floor is below the measured result."""
    import json
    from app.config import ROOT
    held = json.loads((ROOT / 'tests' / 'fixtures' / 'retrieval_heldout.json').read_text(encoding='utf-8'))
    store = Store(__import__('tempfile').mkdtemp() + '/held.db')
    missed = [x['question'] for x in held['positive'] if not set(x['expected']) & set(ids(store, x['question']))]
    leaked = [q for q in held['negative'] if ids(store, q)]
    assert len(missed) <= 1, missed
    assert len(leaked) <= 1, leaked


def test_sqlite_connections_are_closed(tmp_path):
    import sqlite3
    store = Store(tmp_path / 'close.db')
    with store.connect() as cx:
        cx.execute('SELECT 1')
    with pytest.raises(sqlite3.ProgrammingError):
        cx.execute('SELECT 1')  # closed on leaving the with-block, not left to garbage collection
    store.documents(); store.fts_search('bàn Oak'); store.log('t', 'm', 1)
    (tmp_path / 'close.db').unlink()  # a leaked handle would make this fail on Windows
